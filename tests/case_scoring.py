"""Run and score one case of the argument-diagnostics case format (``argdiag-corpus/1``) the way production runs an
answer, for the regression tests of the repair rounds (``tests/contract/test_repair_round1_cases.py``).

The case runs through the public pipeline: a ``RouterHub`` opened on its ``WorkPlan``; the request dispatched through the
channel; the answer received as raw text (the subject branch's own parser makes the claims) or as the structured report
the case gives; every claim the channel hands to its verifier translated by the real ``Translator`` from the case's
recorded proposal (served by the fixture provider as the untrusted JSON text a model would return), decided by the
engine, reviewed by a fixture reviewer and composed into its outcome; and the combinator's synthesis relayed when the
mode asks for it. Nothing in a case is executed: proposals are JSON data passed to the translator.

Scoring (per mode, then per case): a signal at warning or error severity flags; a defect case is ``named`` when a signal
names its expected (or an acceptable) label at warning or error severity, or any signal names it while the case is
refused, flagged or not releasable; else ``caught_unnamed`` when it is refused, flagged or not releasable; else
``missed``. A control is a ``false_alarm`` when it is refused or flagged, else ``control_clean``. Existing codes map to
labels by one table, ``CODE_LABELS``; a new diagnostic names its label in its ``defect`` field.
"""
from __future__ import annotations

import inspect
import json
import re
import time
import traceback
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Optional

from epinoic_logic import branches as _branches
from epinoic_logic import engine as _engine
from epinoic_logic import integrity as _integrity
from epinoic_logic.ir import schema as _schema
from epinoic_logic.translate import contracts as _contracts
from epinoic_logic.translate import outcome as _outcome
from epinoic_logic.translate import pipeline as _pipeline
from epinoic_logic.translate import review as _review
from epinoic_logic.translate.providers import fixture as _fixture

RUNNER_VERSION = "argdiag-runner/1"
CASE_FORMAT = "argdiag-corpus/1"
KEY = b"argdiag-corpus-engine-key-0123456789abcdef"
SECRET = b"argdiag-corpus-overseer-secret-0123456789abcdef"
COMB = "combinator"

CANONICAL = (
    "leap_in_logic", "affirming_the_consequent", "denying_the_antecedent", "hasty_generalisation", "false_dilemma", "circular_reasoning", "equivocation",
    "causal_leap", "bare_assertion", "contradiction", "vacuous_argument", "lack_of_evidence", "unchecked_source", "source_mismatch", "altered_quotation",
    "invented_figure", "cherry_picked_data", "uncheckable_authority", "stem_wrong_formula", "stem_unit_error", "stem_dimension_error", "stem_arithmetic_slip",
    "stem_invalid_step", "stem_rounding_changes_conclusion", "stem_extrapolation", "stem_missing_working", "stem_contradictory_givens", "stem_symbol_conflict",
)

# ----------------------------------------------------------------------------------------------- THE code -> label table
#: (code regex, message regex or None, label or None). First matching row wins; None means the code names no defect
#: (it may still flag). Pseudo-codes: DISPLAY:<status>, GROUNDING:FAILED, FORMAL:<check id prefix>.
CODE_LABELS: tuple[tuple[str, Optional[str], Optional[str]], ...] = (
    # contradiction
    (r"INT-REQ-007", None, "contradiction"),                          # the claim rests on premises that contradict each other
    (r"INT-CONFLICT-00[1-4]", None, "contradiction"),                  # specialist claims contradict each other
    (r"DISPLAY:INCONSISTENT_PREMISES", None, "contradiction"),         # the engine's unsat core over the premises
    # engine diagnostics that name a defect of the argument
    (r"E108", None, "vacuous_argument"),                               # vacuous: no premise used / tautological conclusion
    (r"E112", None, "circular_reasoning"),                             # a premise restates the conclusion
    (r"E505", None, "unchecked_source"),                               # an asserted verified flag was discarded
    (r"E11[01]|W11[01]", None, None),                                  # coverage: unasserted figure / unencoded reason
    # STEM checks of the report's own statements (INT-SUBJ-001 error, INT-SUBJ-004 warning): by check kind
    (r"INT-SUBJ-00[14]", r"own stem_conversion\b", "stem_unit_error"),
    (r"INT-SUBJ-00[14]", r"own stem_algebra\b", "stem_invalid_step"),
    (r"INT-SUBJ-00[14]", r"own stem_given\b", "stem_contradictory_givens"),
    (r"INT-SUBJ-00[14]", r"own (stem_comparison|stem_target|stem_balance)\b", None),
    (r"INT-SUBJ-00[14]", r"own (stem_[a-z_]+|arithmetic|pair_direction|percentage|[a-z_]*arith[a-z_]*)\b", "stem_arithmetic_slip"),
    (r"INT-SUBJ-00[14]", None, None),
    (r"FORMAL:stem-cnv", None, "stem_unit_error"),
    (r"FORMAL:stem-alg", None, "stem_invalid_step"),
    (r"FORMAL:stem-giv", None, "stem_contradictory_givens"),
    (r"FORMAL:stem-(eq|res|sub|sol|tt|bool|base)", None, "stem_arithmetic_slip"),
    (r"FORMAL:.*", None, None),
    (r"ST-DIM-00[12]", None, "stem_dimension_error"),                  # the sides or terms have different dimensions
    (r"ST-SCOPE-001", None, "stem_symbol_conflict"),                   # a symbol bound again to another value
    # quotations, sources and attributions
    (r"INT-REQ-003", r"altered quotation", "altered_quotation"),
    (r"INT-REQ-003", None, "source_mismatch"),                          # quotation or citation not found in the supplied text
    (r"(ES|CORE|GEN)-SRC-001", r"altered", "altered_quotation"),
    (r"(ES|CORE|GEN)-SRC-001", None, "source_mismatch"),                # cited excerpt not found
    (r"CORE-SRC-005|ES-SRC-008", None, "source_mismatch"),             # credited to one source, found only in another
    (r"INT-LEDGER-025", None, "source_mismatch"),                       # synthesis quotes or credits words its sources lack
    (r"GROUNDING:FAILED", None, "source_mismatch"),                     # a grounding check found the source does not state it
    (r"CORE-SRC-003", None, "unchecked_source"),                        # quotations no supplied text holds, no from-memory label
    (r"CORE-SRC-002|HI-SRC-004", None, "lack_of_evidence"),             # figures stated with no source (info)
    (r"PS-SRC-001|HI-SRC-003", None, "uncheckable_authority"),          # a study / historian attributed with no grounding
    (r"CORE-SELF-001", None, "unchecked_source"),                       # self-certification language
    # overseer codes (trees that carry epinoic_logic.overseer)
    (r"OVS-TRN-004|OVS-FID-00[24]", None, "source_mismatch"),
    (r"OVS-TRN-003|OVS-FID-00[59]", None, "unchecked_source"),
    (r"OVS-TRN-005", None, "invented_figure"),
    (r"OVS-TRN-006|OVS-TRN-011", None, "circular_reasoning"),
    # everything else names no defect (it may still flag)
    (r".*", None, None),
)
_CODE_RULES = [(re.compile(c + r"\Z"), re.compile(m) if m else None, lab) for c, m, lab in CODE_LABELS]

#: Codes that describe how this runner ran a check, not the case: never a flag, never a label (recorded in the run).
#: OVS-AUDIT-002: the runner replays the overseer's FINAL audit inline (in this process), as the audit's probe harnesses did.
#: INT-SYNTH-012: the 'merged' mode's synthesis is built by this runner (the whole answer as one merged claim, with no formal
#: conclusion), so the channel rightly says the merge was not formally checked; that is a property of the runner's synthesis.
ENVIRONMENT_CODES = frozenset({"OVS-AUDIT-002", "INT-SYNTH-012"})

#: Flags that report coverage, format, bookkeeping or a check that could not run. On a control they are false alarms like any
#: other flag; on a defect case they never count as catching the defect (they say nothing about the reasoning).
NON_DEFECT_CODES = re.compile(r"(INT-REQ-00[458]|INT-REQ-01[01]|(ES|HI|PS|BM|EC|GEN|CORE)-STR-\d{3}|ES-STY-\d{3}|ES-META-001|CORE-QNT-001|ST-PARSE-\d{3}|"
                              r"ST-UNDEC-\d{3}|ST-UNDEF-001|ST-UNIT-00[12]|ST-LIM-\d{3}|INT-SUBJ-002|INT-LEDGER-020|INT-GLOSSARY-\d{3}|INT-REQ-016|CONSTRAINT:.*)\Z")

#: Displays that say the point does not follow or the premises contradict each other. INVALID_FORMALIZATION, INTERNAL_ERROR,
#: AMBIGUOUS_TRANSLATION, UNSUPPORTED and NOT_ELIGIBLE say nothing was verified: they leave the claim unresolved (not
#: releasable) but accuse nothing; a vacuous or circular encoding flags through its own E108 / E112 diagnostic.
FLAG_DISPLAYS = ("COUNTEREXAMPLE", "INCONSISTENT_PREMISES")
_TR_CODE_RE = re.compile(r"\b([EW]\d{3}):")
SEV_RANK = {"info": 0, "warning": 1, "error": 2}
RANK = {"missed": 0, "caught_unnamed": 1, "named": 2}


def label_for(code: str, message: str = "") -> Optional[str]:
    """The canonical label the table gives ``code`` (INT-SUBJ-003 wraps a subject-pack finding: its inner code decides)."""
    if code == "INT-SUBJ-003":
        m = re.match(r"\[[^\]]*\]\s*([A-Z]+-[A-Z]+-\d{3}):\s*(.*)", message or "", re.S)
        if m:
            return label_for(m.group(1), m.group(2))
    for crx, mrx, lab in _CODE_RULES:
        if crx.match(code) and (mrx is None or mrx.search(message or "")):
            return lab
    return None


# ----------------------------------------------------------------------------------------------- the package under test
#: The package's public pieces the runner uses, by the names the scoring code reads them under (``T.RouterHub``, ...).
T = SimpleNamespace(
    RouterHub=_branches.RouterHub, SolverConfig=_engine.SolverConfig, WorkPlan=_integrity.WorkPlan, AgentRole=_integrity.AgentRole,
    Synthesis=_integrity.Synthesis, SynthesizedClaim=_integrity.SynthesizedClaim, SourceRef=_schema.SourceRef, ClaimRecord=_contracts.ClaimRecord,
    SpecialistReport=_contracts.SpecialistReport, SuppliedText=_contracts.SuppliedText, sha256_text=_contracts.sha256_text,
    verify_claim=_outcome.verify_claim, Translator=_pipeline.Translator, FixtureTranslationProvider=_fixture.FixtureTranslationProvider,
    FixtureReviewProvider=_fixture.FixtureReviewProvider, SemanticReviewer=_review.SemanticReviewer, overseer=None)
Tree = SimpleNamespace


# ----------------------------------------------------------------------------------------------- running one mode
def norm(s: str) -> str:
    return " ".join((s or "").split())


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def supplied(T: Tree, raw: list[dict]) -> list:
    return [T.SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"], locator_scheme=t.get("locator_scheme", "none")) for t in raw]


class Matcher:
    """Binds recorded translations to delivered claims: exact normalised text, else substring, else claim id."""

    def __init__(self, translations: list[dict]) -> None:
        self.items = translations
        self.served: dict[int, list[str]] = {}

    def find(self, claim) -> Optional[tuple[int, dict]]:
        text = norm(claim.claim_text)
        for i, t in enumerate(self.items):
            if t.get("claim_text") is not None and norm(t["claim_text"]) == text:
                return i, t
        for i, t in enumerate(self.items):
            if t.get("contains") and norm(t["contains"]) in text:
                return i, t
        for i, t in enumerate(self.items):
            if t.get("claim_text") is None and t.get("contains") is None and t.get("claim_id") == claim.claim_id:
                return i, t
        return None


def make_verify_fn(T: Tree, matcher: Matcher, cfg, fidelity: str, log: list):
    def verify_fn(claim, report, task=None):
        hit = matcher.find(claim)
        if hit is None:
            return None
        i, item = hit
        matcher.served.setdefault(i, []).append(claim.claim_id)
        obj = json.loads(json.dumps(item["proposal"]))
        if isinstance(obj, dict) and isinstance(obj.get("problem"), dict):
            obj["problem"]["claim_id"] = claim.claim_id
            obj["problem"]["request_id"] = claim.request_id
        translator = T.Translator(T.FixtureTranslationProvider({claim.claim_id: json.dumps(obj, ensure_ascii=False)}))
        reviewer = T.SemanticReviewer(T.FixtureReviewProvider({claim.claim_id: json.dumps({"verdict": fidelity, "issues": []})}))
        kw = dict(reviewer=reviewer, config=cfg, signing_key=KEY, key_id="channel")
        if task is not None and "task" in inspect.signature(T.verify_claim).parameters:
            kw["task"] = task
        out = T.verify_claim(claim, report, translator, **kw)
        log.append({"claim_id": claim.claim_id, "translation": i})
        return out
    return verify_fn


def accepts(fn, name: str) -> bool:
    try:
        return name in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def structured_report(T: Tree, case: dict, plan, docs: list):
    text = case["answer"]
    rid = case["ids"].get("report_id", "rep-1")
    claims = []
    for c in case.get("report_claims", []):
        if c["text"] not in text:
            raise ValueError(f"report claim {c['claim_id']} is not a substring of the answer")
        claims.append(T.ClaimRecord(request_id=plan.request_id, task_id=plan.task_id, report_id=rid, agent_id=case["agent_id"], subject=case["subject"],
                                    task_type=case["task_type"], claim_id=c["claim_id"], claim_text=c["text"], claim_role=c.get("role", "other"),
                                    proposed_claim_kind=c.get("kind", "unknown"), materiality=c.get("materiality", "material"), certainty=c.get("certainty", "established"),
                                    source_refs=[T.SourceRef(**r) for r in c.get("source_refs", [])], supporting_claim_ids=c.get("supporting", []),
                                    assumptions=c.get("assumptions", []), advisory_verification_status=c.get("advisory_status"),
                                    advisory_verification_eligibility=c.get("advisory_eligible")))
    return T.SpecialistReport(report_id=rid, request_id=plan.request_id, task_id=plan.task_id, agent_id=case["agent_id"], subject=case["subject"],
                              task_type=case["task_type"], original_response=text, response_sha256=T.sha256_text(text), supplied_texts=docs, claims=claims,
                              created_at=now())


def dump(model) -> Any:
    return model.model_dump(mode="json") if hasattr(model, "model_dump") else model


def finding_rec(f, source: str) -> dict:
    d = dump(f)
    return {"source": source, "kind": "finding", "code": d.get("code"), "severity": d.get("severity", "warning"), "claim_ids": list(d.get("claim_ids") or []),
            "message": str(d.get("message", ""))[:1200]}


def defect_fields(obj: Any, path: str = "") -> list[dict]:
    """Every ``defect`` field anywhere in a dumped receipt (new diagnostics carry their canonical label there)."""
    out: list[dict] = []
    if isinstance(obj, dict):
        if "defect" in obj and obj["defect"]:
            labs = obj["defect"] if isinstance(obj["defect"], list) else [obj["defect"]]
            out.append({"path": path, "labels": [str(x) for x in labs], "severity": obj.get("severity", "warning"), "code": obj.get("code"),
                        "claim_ids": list(obj.get("claim_ids") or ([obj["claim_id"]] if obj.get("claim_id") else [])), "message": str(obj.get("message", ""))[:600]})
        for k, v in obj.items():
            if k in ("problem", "original_response", "supplied_texts", "raw_text"):
                continue
            out.extend(defect_fields(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(defect_fields(v, f"{path}[{i}]"))
    return out


def receipt_signals(rc, source: str, claim_text: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """(signals, outcome records) of one receipt."""
    sig: list[dict] = []
    for f in rc.findings:
        sig.append(finding_rec(f, source))
    for f in rc.structural_findings:
        sig.append(finding_rec(f, source + ":subject"))
    for c in rc.constraint_results:
        if c.satisfied is False:
            sig.append({"source": source, "kind": "constraint", "code": f"CONSTRAINT:{c.constraint_id}", "severity": "warning", "claim_ids": list(getattr(c, "claim_ids", []) or []),
                        "message": str(c.detail or c.description or "")[:600]})
    for c in rc.formal_checks:
        if c.satisfied is False:
            prefix = re.sub(r"-\d+$", "", c.constraint_id)
            sig.append({"source": source, "kind": "formal_check", "code": f"FORMAL:{prefix}", "check_id": c.constraint_id, "severity": "warning",
                        "status": str(getattr(c.formal_status, "value", c.formal_status)), "claim_ids": list(getattr(c, "claim_ids", []) or []), "message": str(c.detail or "")[:600]})
    outs = []
    for o in rc.outcomes:
        v, tr = o.verification, o.translation
        disp = o.display_status.value
        rel = getattr(o, "release", None)
        rec = {"claim_id": o.claim_id, "claim_text": claim_text.get(o.claim_id, "")[:300], "display_status": disp, "translation_status": tr.status.value,
               "engine_status": v.status.value if v else None, "engine_diagnostics": [d.code for d in v.diagnostics] if v else [],
               "ungrounded": list(v.ungrounded_dependencies) if v else [], "unverified": list(v.unverified_dependencies) if v else [],
               "grounding_failed": sorted({gc.target_id for gc in tr.grounding_checks if gc.verified is False}),
               "grounding_failed_detail": [{"target": gc.target_id, "kind": gc.kind, "method": gc.method, "detail": str(gc.detail or "")[:300]}
                                           for gc in tr.grounding_checks if gc.verified is False][:6],
               "translation_diagnostics": [str(x)[:400] for x in list(tr.diagnostics or [])[:6]],
               "release_permitted": getattr(rel, "permitted", None), "release_unresolved": list(getattr(rel, "unresolved", []) or [])[:8],
               "ambiguity_flags": [dump(a) for a in (tr.interpretation.ambiguity_flags if getattr(tr, "interpretation", None) else [])][:6]}
        outs.append(rec)
        if disp in FLAG_DISPLAYS:
            sig.append({"source": source, "kind": "display", "code": f"DISPLAY:{disp}", "severity": "error", "claim_ids": [o.claim_id], "message": f"claim displayed {disp}"})
        elif disp in ("UNSATISFIABLE",) and tr.problem is not None and tr.problem.query == "satisfiability":
            sig.append({"source": source, "kind": "display", "code": f"DISPLAY:{disp}", "severity": "error", "claim_ids": [o.claim_id], "message": f"claim displayed {disp}"})
        for code in rec["engine_diagnostics"]:
            sev = "error" if code in ("E108", "E112") else "info"
            sig.append({"source": source, "kind": "engine_diagnostic", "code": code, "severity": sev, "claim_ids": [o.claim_id], "message": ""})
        # the translation layer's own diagnostics name engine codes in text ("<tag>: E112: circular: ..."); a rejected
        # translation's circularity or vacuity code is error-level, every other one is a note
        for text in list(tr.diagnostics or [])[:64]:
            for code in sorted(set(_TR_CODE_RE.findall(str(text)))):
                rejected = tr.status.value in ("INVALID_FORMALIZATION",) and code in ("E108", "E112")
                sig.append({"source": source, "kind": "engine_diagnostic", "code": code, "severity": "error" if rejected else "info", "claim_ids": [o.claim_id],
                            "message": str(text)[:400], "via": "translation_diagnostics"})
        if rec["grounding_failed"]:
            sig.append({"source": source, "kind": "grounding", "code": "GROUNDING:FAILED", "severity": "warning", "claim_ids": [o.claim_id],
                        "message": "failed grounding checks: " + ", ".join(rec["grounding_failed"])})
        for f in o.structural_findings:
            r = finding_rec(f, source + ":outcome")
            r["claim_ids"] = r["claim_ids"] or [o.claim_id]
            sig.append(r)
        if rel is not None and rel.permitted is False:
            sig.append({"source": source, "kind": "release", "code": "RELEASE:NOT_PERMITTED", "severity": "info", "claim_ids": [o.claim_id], "message": "; ".join(rel.unresolved[:4])[:600]})
    for d in defect_fields(dump(rc)):
        sig.append({"source": source, "kind": "defect_field", "code": d.get("code") or "DEFECT", "severity": d["severity"], "claim_ids": d["claim_ids"],
                    "message": d["message"], "labels": d["labels"], "path": d["path"]})
    return sig, outs


def run_mode(T: Tree, case: dict, mode: dict, cfg) -> dict:
    rec: dict[str, Any] = {"mode": mode["name"]}
    t0 = time.perf_counter()
    auditor = None
    try:
        ids = case.get("ids") or {}
        docs = supplied(T, case.get("supplied_texts", []))
        plan_fields = dict(plan_id=ids.get("plan_id", f"plan-{case['id']}"), request_id=ids.get("request_id", f"req-{case['id']}"), task_id=ids.get("task_id", f"task-{case['id']}"),
                           subject=case["subject"], task_type=case["task_type"], selected_agent_ids=[case["agent_id"], COMB],
                           allowed_document_ids=sorted({d.document_id for d in docs}))
        plan_fields.update(case.get("plan") or {})
        plan = T.WorkPlan(**plan_fields)
        hub_kw: dict[str, Any] = dict(signing_key=KEY, key_id="hub", config=cfg)
        if T.overseer is not None:
            O = T.overseer
            keyring = O["KeyRing"]({k: O["EngineKey"](KEY) for k in ("hub", "channel", "default", "integrity", "t")}, SECRET)
            auditor = O["TransferAuditor"](keyring, replay_mode="inline", eager=True, shadow="off", inline_final_release=True)
            if accepts(T.RouterHub.__init__, "auditor"):
                hub_kw["auditor"] = auditor
        hub = T.RouterHub(**hub_kw)
        ch = hub.open_task(plan)
        task = plan.task_id
        signals: list[dict] = []
        claim_text: dict[str, str] = {}
        rec["peers"] = []
        extra_docs = []
        # ---- peers (e2e): delivered first, then relayed router -> the answering specialist on the same ledger
        for peer in case.get("peers", []):
            pm_log: list = []
            pmatch = Matcher(peer.get("translations", []))
            ch.verify_claim_fn = make_verify_fn(T, pmatch, cfg, peer.get("fidelity_review", case.get("fidelity_review", "faithful")), pm_log)
            pdocs = supplied(T, peer.get("supplied_texts", []))
            m, _req, rq = hub.dispatch(task, peer["agent_id"], peer["request"], pdocs)
            if m is None:
                raise RuntimeError(f"peer request to {peer['agent_id']} rejected: {[f.code for f in rq.findings]}")
            preply, prc = hub.receive(task, m.message_id, peer["answer"], agent_id=peer["agent_id"], report_id=peer.get("report_id", f"rep-{peer['agent_id']}"))
            prow = {"agent_id": peer["agent_id"], "status": prc.status.value, "codes": sorted({f.code for f in prc.findings} | {f.code for f in prc.structural_findings}),
                    "translations_served": len(pmatch.served), "translations_total": len(pmatch.items)}
            if preply is not None and peer.get("relay_to_main"):
                prep = T.SpecialistReport.model_validate(preply.payload)
                relayed, rr = ch.relay("router", T.AgentRole.ROUTER, case["agent_id"], T.AgentRole.SPECIALIST, prep, in_reply_to=preply.message_id)
                prow["relay_status"] = rr.status.value
                if relayed is not None:
                    extra_docs.append(T.SuppliedText(document_id=peer["peer_document_id"], title=peer.get("peer_document_title"), author=peer["agent_id"],
                                                     text=peer.get("peer_document_text") or prep.original_response))
            rec["peers"].append(prow)
        # ---- the answering specialist
        vlog: list = []
        matcher = Matcher(case.get("translations", []))
        ch.verify_claim_fn = make_verify_fn(T, matcher, cfg, case.get("fidelity_review", "faithful"), vlog)
        m, _req, rq = hub.dispatch(task, case["agent_id"], case["request"], [*docs, *extra_docs])
        for f in rq.findings:
            signals.append(finding_rec(f, "request"))
        rec["request_status"] = rq.status.value
        if m is None:
            rec.update(refused=True, refused_why=["request rejected"])
            raise _Stop()
        if mode["delivery"] == "report":
            payload = structured_report(T, case, plan, [*docs, *extra_docs])
            reply, rc = hub.receive(task, m.message_id, payload)
        else:
            reply, rc = hub.receive(task, m.message_id, case["answer"], agent_id=case["agent_id"], report_id=ids.get("report_id", f"rep-{case['id']}"))
        delivered = T.SpecialistReport.model_validate(reply.payload) if reply is not None else None
        if delivered is not None:
            claim_text = {c.claim_id: c.claim_text for c in delivered.claims}
            rec["claims"] = [{"claim_id": c.claim_id, "role": c.claim_role, "text": c.claim_text[:300]} for c in delivered.claims]
        rsig, outs = receipt_signals(rc, "receipt", claim_text)
        signals.extend(rsig)
        rec.update(receipt_status=rc.status.value, branch=rc.branch, outcomes=outs, summary=rc.summary[:2500],
                   translations_served=len(matcher.served), translations_total=len(matcher.items),
                   translations_unmatched=[i for i in range(len(matcher.items)) if i not in matcher.served])
        refused_why = []
        if rc.status.value == "REJECTED" or reply is None:
            refused_why.append(f"report {rc.status.value}{'' if reply is not None else ', not delivered'}")
        # ---- overseer clearance of the report (trees with an overseer)
        if T.overseer is not None and T.overseer.get("check_before_acting") is not None:
            clr = T.overseer["check_before_acting"](hub, task, rc, wait_ms=0)
            rec["clearance"] = {"allowed": clr.allowed, "reason": str(clr.reason)[:400], "state": str(clr.state)}
            if not clr.allowed:
                refused_why.append("overseer clearance refused")
        # ---- the combinator's synthesis
        syn_receipt = None
        ms = None
        if delivered is not None and mode.get("synthesis", "none") != "none":
            if mode["synthesis"] == "merged":
                refs = [r for c in delivered.claims for r in c.source_refs]
                s_claims = [T.SynthesizedClaim(claim_id="syn-c0", text=delivered.original_response, certainty="established", materiality="material",
                                               source_claim_ids=[c.claim_id for c in delivered.claims], transformation="merged", evidence_refs=refs)]
            else:
                s_claims = [T.SynthesizedClaim(claim_id=f"syn-c{i}", text=c.claim_text, certainty=c.certainty, materiality=c.materiality, source_claim_ids=[c.claim_id],
                                               transformation="carried", evidence_refs=list(c.source_refs)) for i, c in enumerate(delivered.claims)]
            text = " ".join(c.text for c in s_claims)
            syn = T.Synthesis(synthesis_id=f"syn-{case['id']}", request_id=plan.request_id, task_id=task, combinator_agent_id=COMB, source_report_ids=[delivered.report_id],
                              claims=s_claims, ledger=[], text=text, text_sha256=T.sha256_text(text), created_at=now())
            ms, syn_receipt = ch.relay(COMB, T.AgentRole.COMBINATOR, "router", T.AgentRole.ROUTER, syn)
            ssig, _ = receipt_signals(syn_receipt, "synthesis", claim_text)
            signals.extend(ssig)
            rec["synthesis_status"] = syn_receipt.status.value
            if syn_receipt.status.value == "REJECTED" or ms is None:
                refused_why.append(f"synthesis {syn_receipt.status.value}")
        # ---- overseer audit and release decision
        if T.overseer is not None and hasattr(hub, "close_task"):
            audit = hub.close_task(task)
            if audit is not None:
                for f in audit.report.findings:
                    signals.append(finding_rec(f, "audit"))
                rec["audit_state"] = str(getattr(audit.state, "value", audit.state))
                if syn_receipt is not None and ms is not None and T.overseer.get("release_decision") is not None:
                    d = T.overseer["release_decision"](syn_receipt, audit, auditor.keyring, audits=auditor.audits(ch.channel_uid), journal=auditor.journal(ch.channel_uid), message=ms)
                    rec["overseer_release"] = {"allowed": d.allowed, "reason": str(d.reason)[:400]}
                    if not d.allowed:
                        refused_why.append("overseer release refused")
        rec["refused"] = bool(refused_why)
        rec["refused_why"] = refused_why
        rec["signals"] = signals
    except _Stop:
        rec.setdefault("signals", [])
    except Exception as exc:  # a crash is recorded, never hidden
        rec["crash"] = f"{type(exc).__name__}: {exc}"
        rec["traceback"] = traceback.format_exc()[-4000:]
        rec.setdefault("signals", [])
    finally:
        if auditor is not None and hasattr(auditor, "close"):
            try:
                auditor.close()
            except Exception:
                pass
    rec["elapsed_s"] = round(time.perf_counter() - t0, 3)
    return rec


class _Stop(Exception):
    pass


# ----------------------------------------------------------------------------------------------- scoring
def signal_labels(s: dict) -> list[str]:
    if s.get("labels"):
        return [x for x in s["labels"] if x in CANONICAL]
    lab = label_for(s.get("code") or "", s.get("message") or "")
    return [lab] if lab else []


def in_scope(s: dict, scope: Optional[dict], scoped_ids: set[str]) -> bool:
    if not scope:
        return True
    kind_to_check = {"finding": "findings", "constraint": "constraints", "formal_check": "formal_checks", "display": "display", "grounding": "grounding",
                     "engine_diagnostic": "display", "defect_field": "findings", "release": "release"}
    checks = scope.get("checks")
    if checks and kind_to_check.get(s["kind"]) not in checks:
        return False
    if s["source"].startswith("peer"):
        return False
    is_constraint_any = s["kind"] == "constraint" and scope.get("constraint_any")
    if not is_constraint_any and SEV_RANK.get(s.get("severity", "warning"), 1) < SEV_RANK[scope.get("min_severity", "warning")]:
        return False
    if s["kind"] == "constraint":
        want = scope.get("constraint_detail_contains")
        if want and not any(w in (s.get("message") or "") for w in want):
            return False
    else:
        codes = scope.get("codes")
        if codes and s.get("code") not in codes:
            return False
        want = scope.get("message_contains")
        if want and s["kind"] == "finding" and not any(w in (s.get("message") or "") for w in want):
            return False
    ids = set(s.get("claim_ids") or [])
    if scope.get("claim_texts") is not None:
        if ids & scoped_ids:
            return True
        return bool(scope.get("request_level")) and not ids
    return bool(scope.get("request_level", True))


def score_mode(case: dict, rec: dict) -> dict:
    expected = case["expected_label"]
    wanted = {expected, *case.get("acceptable_labels", [])} - {"none"}
    scope = case.get("scope")
    texts = (rec.get("claims") or [])
    scoped_ids: set[str] = set()
    if scope and scope.get("claim_texts") is not None:
        for c in texts:
            full = c["text"]
            if any(norm(t) in norm(full) for t in scope["claim_texts"]):
                scoped_ids.add(c["claim_id"])
        # claim texts are cut to 300 characters in the record: match outcome texts too
        for o in rec.get("outcomes") or []:
            if any(norm(t) in norm(o.get("claim_text", "")) for t in scope["claim_texts"]):
                scoped_ids.add(o["claim_id"])
    sigs = [s for s in rec.get("signals", []) if s.get("code") not in ENVIRONMENT_CODES and in_scope(s, scope, scoped_ids)]
    flags = [s for s in sigs if s["kind"] != "release" and SEV_RANK.get(s.get("severity", "warning"), 1) >= 1]
    if scope and scope.get("constraint_any"):
        flags += [s for s in sigs if s["kind"] == "constraint" and s not in flags]
    outs = rec.get("outcomes") or []
    if scope and scope.get("claim_texts") is not None:
        outs = [o for o in outs if o["claim_id"] in scoped_ids]
    not_releasable = any(o.get("release_permitted") is False for o in outs) if outs else None
    if rec.get("overseer_release") is not None and not rec["overseer_release"]["allowed"]:
        not_releasable = True
    refused = bool(rec.get("refused"))
    crashed = "crash" in rec
    hits = []
    for s in sigs:
        for lab in signal_labels(s):
            hits.append({"label": lab, "code": s.get("code"), "severity": s.get("severity"), "source": s["source"], "claim_ids": s.get("claim_ids", [])[:6],
                         "message": (s.get("message") or "")[:240]})
    defect_flags = [s for s in flags if not NON_DEFECT_CODES.match(s.get("code") or "")]
    caught = refused or bool(defect_flags) or bool(not_releasable)
    if expected == "none":
        verdict = "false_alarm" if (crashed or refused or flags) else "control_clean"
    elif crashed:
        verdict = "missed"
    else:
        strong = [h for h in hits if h["label"] in wanted and SEV_RANK.get(h["severity"] or "warning", 1) >= 1]
        weak = [h for h in hits if h["label"] in wanted]
        if strong or (weak and caught):
            verdict = "named"
        elif caught:
            verdict = "caught_unnamed"
        else:
            verdict = "missed"
    return {"mode": rec["mode"], "verdict": verdict, "refused": refused, "refused_why": rec.get("refused_why", []), "flagged": bool(flags),
            "not_releasable": not_releasable, "crashed": crashed, "defect_flags": len(defect_flags),
            "flags": [{"code": s.get("code"), "severity": s.get("severity"), "kind": s["kind"], "source": s["source"], "claim_ids": s.get("claim_ids", [])[:6],
                       "message": (s.get("message") or "")[:240]} for s in flags][:40],
            "labels_hit": hits[:40], "wanted_labels": sorted(wanted),
            "other_labels": sorted({h["label"] for h in hits} - wanted),
            "scoped_claim_ids": sorted(scoped_ids) if scope else None}


def score_case(case: dict, mode_scores: list[dict]) -> str:
    if case["expected_label"] == "none":
        return "false_alarm" if any(m["verdict"] == "false_alarm" for m in mode_scores) else "control_clean"
    return min((m["verdict"] for m in mode_scores), key=lambda v: RANK[v]) if mode_scores else "missed"


def summarise(results: list[dict]) -> dict:
    fams: dict[str, dict] = {}
    for r in results:
        f = fams.setdefault(r["family"], {"cases": 0, "defects": 0, "controls": 0, "named": 0, "caught_unnamed": 0, "missed": 0, "false_alarm": 0, "control_clean": 0,
                                          "controls_not_releasable": 0, "crashed": 0})
        f["cases"] += 1
        f["defects" if r["expected_label"] != "none" else "controls"] += 1
        f[r["verdict"]] += 1
        if r["expected_label"] == "none" and any(m.get("not_releasable") for m in r["modes"]):
            f["controls_not_releasable"] += 1
        if any(m.get("crashed") for m in r["modes"]):
            f["crashed"] += 1
    total = {k: sum(f[k] for f in fams.values()) for k in next(iter(fams.values())).keys()} if fams else {}
    by_label: dict[str, dict] = {}
    for r in results:
        if r["expected_label"] == "none":
            continue
        b = by_label.setdefault(r["expected_label"], {"named": 0, "caught_unnamed": 0, "missed": 0, "cases": []})
        b[r["verdict"]] += 1
        b["cases"].append(r["id"])
    fa_codes: dict[str, int] = {}
    for r in results:
        if r["verdict"] == "false_alarm":
            for code in sorted({fl["code"] for m in r["modes"] for fl in m["flags"]} | ({"CRASH"} if any(m["crashed"] for m in r["modes"]) else set())):
                fa_codes[code] = fa_codes.get(code, 0) + 1
    return {"by_family": fams, "total": total, "by_expected_label": by_label, "false_alarm_codes": dict(sorted(fa_codes.items(), key=lambda kv: -kv[1])),
            "lists": {v: [r["id"] for r in results if r["verdict"] == v] for v in ("named", "caught_unnamed", "missed", "false_alarm", "control_clean")}}


def run_case(case: dict, timeout_ms: int = 4000) -> dict:
    """Run every mode of ``case`` and score it: ``{"verdict": ..., "modes": [...]}`` (the per-mode records keep their flags
    and label hits, and the crash traceback of a mode that crashed)."""
    cfg = T.SolverConfig(timeout_ms=timeout_ms, memory_max_mb=None)
    modes = []
    for mode in case["modes"]:
        rec = run_mode(T, case, mode, cfg)
        modes.append({**score_mode(case, rec), "crash": rec.get("crash"), "traceback": rec.get("traceback")})
    return {"verdict": score_case(case, modes), "modes": modes}
