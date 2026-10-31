"""Integration step before arena round 8: the overseer understands everything the merged translator emits.

* **The code tables** (``overseer.emitted``) against the translator's own sources: every receipt code with every severity
  it is raised at (the channel's, the subject packs' and the STEM branches'), every named diagnostic with its label,
  severity, layers and caps, the 28 labels, every engine status and diagnostic code, every reason of the engine's release
  check (rules 1 to 9) and of the outcome's release assessment, the named engine policies, the blocking prefixes and the
  named rejections (INT-SYNTH-014 among them). Every code constant the translator's source names is known.
* **The audit**, one family at a time, each with a positive case and a clean control: a named defect (INT-ARG-001 dropped),
  a load-bearing writer's assumption (ARG-LINK-001 dropped from the receipt), an unchecked source (EVD-SRC-001 dropped from
  an outcome or uncapped), a STEM method error (ST-REF-001's label dropped, or the finding; a failed STEM check's own label,
  stem_unit_error, replaced by its kind's or dropped: R2 compares it with the re-derived check), a release refusal dropped,
  two encodings that disagree (INT-XENC-001 dropped), the named rejection INT-SYNTH-014 dropped; each fails the transfer,
  and the genuine transfer raises nothing.
* **The dossier** shows the receipt's and the signed result's argument diagnosis; **the pool** reads every risk signal and
  only ever escalates oversight; **the knowledge pack** (1.4) lists every code with its severity (the completeness test,
  with a control that it is not vacuous).

No model is called; every result is the engine's, signed and checked."""
from __future__ import annotations

import ast
import itertools
import pathlib
import re
from types import SimpleNamespace

import pytest

import epinoic_logic
from epinoic_logic import named as N
from epinoic_logic.channel.bus import _BLOCKING_PREFIXES, TranslatorChannel
from epinoic_logic.channel.contracts import TransmissionStatus
from epinoic_logic.engine import errors as engine_errors
from epinoic_logic.engine.policies import NAMED_POLICIES as ENGINE_POLICIES
from epinoic_logic.engine.statuses import DEFINITIVE, VerificationStatus
from epinoic_logic.overseer import emitted as E
from epinoic_logic.overseer.checks.receipts import FIXED_SEVERITY, VARIABLE_SEVERITY
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir
from epinoic_logic.overseer.pool import PoolConfig, PoolItem, plan_pool
from epinoic_logic.overseer.verdicts import PackIdentity
from epinoic_logic.stem.relations import ST_SEVERITY
from epinoic_logic.translate.contracts import TranslationStatus

from .conftest import (
    EN_INPUT, DOC, codes_of, english_report, findings, make_auditor, make_plan, new_channel, run_task,
)
from .delivery_support import ESSAY, ESSAY_QUESTION, essay_report

SRC = pathlib.Path(epinoic_logic.__file__).resolve().parent
_CODE = re.compile(r"^[A-Z]{2,7}-[A-Z]{2,10}-\d{3}$")
_FAMILIES = ("INT-", "CORE-", "ES-", "HI-", "GEN-", "PS-", "EC-", "BM-", "PACK-", "BR-", "ST-", "ARG-", "EVD-")
_SEV = {"error", "warning", "info"}
_BRANCH = ("CORE-", "ES-", "HI-", "GEN-", "PS-", "EC-", "BM-", "PACK-", "BR-")


# ============================================================================================ scanning the translator
def _modules():
    for p in sorted(SRC.rglob("*.py")):
        rel = p.relative_to(SRC)
        if "overseer" in rel.parts:
            continue
        yield rel, ast.parse(p.read_text(encoding="utf-8"))


def _docstrings(tree) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body and isinstance(node.body[0], ast.Expr) \
                and isinstance(node.body[0].value, ast.Constant):
            out.add(id(node.body[0].value))
    return out


def _sevs(node) -> set[str]:
    """The severity literals a severity expression can take (a constant, or either branch of a conditional)."""
    if isinstance(node, ast.Constant) and node.value in _SEV:
        return {node.value}
    if isinstance(node, ast.IfExp):
        return _sevs(node.body) | _sevs(node.orelse)
    return set()


def scanned_codes() -> tuple[set[str], dict[str, set[str]]]:
    """``(every code constant the translator names outside docstrings, {code: severities its emission sites give})``:
    a call whose ``code=`` (or first positional argument) is a code constant and whose ``severity=`` (or a positional
    argument) is a severity literal, or either branch of a conditional; and a function whose keyword parameter defaults to
    a code and builds a finding with ``code=<that parameter>`` at a literal severity, with every call that passes another
    code for that parameter (the shared quotation and structure checks of the packs)."""
    named: set[str] = set()
    sev: dict[str, set[str]] = {}
    params: dict[str, dict[str, set[str]]] = {}  # function -> {parameter: severities}
    defaults: dict[str, dict[str, str]] = {}     # function -> {parameter: default code}
    calls: list[tuple[str, dict[str, str]]] = []
    for _rel, tree in _modules():
        docs = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _CODE.match(node.value) and id(node) not in docs:
                named.add(node.value)
            if isinstance(node, ast.FunctionDef):
                args = node.args
                kw_defaults = dict(zip([a.arg for a in args.kwonlyargs], args.kw_defaults))
                pos = args.args[len(args.args) - len(args.defaults):] if args.defaults else []
                kw_defaults.update(dict(zip([a.arg for a in pos], args.defaults)))
                codes = {a: d.value for a, d in kw_defaults.items() if isinstance(d, ast.Constant) and isinstance(d.value, str) and _CODE.match(d.value)}
                if codes:
                    defaults[node.name] = codes
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.Call):
                            kw = {k.arg: k.value for k in sub.keywords if k.arg}
                            c, s = kw.get("code"), kw.get("severity")
                            if isinstance(c, ast.Name) and c.id in codes and s is not None:
                                params.setdefault(node.name, {}).setdefault(c.id, set()).update(_sevs(s))
            if not isinstance(node, ast.Call):
                continue
            kw = {k.arg: k.value for k in node.keywords if k.arg}
            fname = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else None
            overrides = {k: v.value for k, v in kw.items() if isinstance(v, ast.Constant) and isinstance(v.value, str) and _CODE.match(v.value) and k.endswith("code")}
            if fname and overrides:
                calls.append((fname, overrides))
            code = kw.get("code")
            if not (isinstance(code, ast.Constant) and isinstance(code.value, str) and _CODE.match(code.value)):
                code = node.args[0] if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str) and _CODE.match(node.args[0].value) else None
            if code is None:
                continue
            got = set()
            if "severity" in kw:
                got |= _sevs(kw["severity"])
            for a in node.args[1:]:
                got |= _sevs(a)
            if got:
                sev.setdefault(code.value, set()).update(got)
    for fname, codes in defaults.items():
        for param, code in codes.items():
            sev.setdefault(code, set()).update(params.get(fname, {}).get(param, set()))
    for fname, overrides in calls:
        for param, code in overrides.items():
            if fname in params and param in params[fname]:
                sev.setdefault(code, set()).update(params[fname][param])
    return named, {c: s for c, s in sev.items() if s}


@pytest.fixture(scope="module")
def scan():
    return scanned_codes()


# ============================================================================================ the code tables
def test_the_int_rows_are_the_receipts_check_tables():
    """The channel and integrity codes of the table are the receipts check's FIXED_SEVERITY and VARIABLE_SEVERITY (each kept
    identical to what the channel emits by its own drift test): a fixed code with its one severity, a variable one with more."""
    ints = {c: e for c, e in E.RECEIPT_CODES.items() if c.startswith("INT-")}
    assert set(ints) == set(FIXED_SEVERITY) | set(VARIABLE_SEVERITY)
    for c, e in ints.items():
        if c in VARIABLE_SEVERITY:
            assert len(e.severities) > 1, c
        else:
            assert e.severities == {FIXED_SEVERITY[c]}, c


def test_the_branch_and_stem_rows_are_what_the_code_raises(scan):
    _named, sev = scan
    branch = {c: e.severities for c, e in E.RECEIPT_CODES.items() if c.startswith(_BRANCH)}
    assert {c: s for c, s in sev.items() if c.startswith(_BRANCH)} == branch
    assert {c: next(iter(e.severities)) for c, e in E.RECEIPT_CODES.items() if c.startswith("ST-")} == ST_SEVERITY
    for c, e in E.RECEIPT_CODES.items():
        if c.startswith("INT-") and c in sev:
            assert sev[c] <= set(e.severities), (c, sev[c])  # every literal severity of an emission site is in the table


def test_every_code_the_translator_names_is_known_and_every_row_is_raised(scan):
    names, sev = scan
    family = {c for c in names if c.startswith(_FAMILIES)}
    unknown = sorted(c for c in family if c not in E.RECEIPT_CODES and c not in E.NAMED_DIAGNOSTIC_CODES and c not in E.NAMED_ONLY)
    assert unknown == [], unknown
    assert set(E.RECEIPT_CODES) | set(E.NAMED_DIAGNOSTIC_CODES) | set(E.NAMED_ONLY) <= names  # no stale row: the translator names each
    # a code named only is never raised by this build: no emission site gives it a severity
    assert not set(E.NAMED_ONLY) & {c for c, s in sev.items() if s and not c.startswith("INT-REQ-017")} - {"INT-REQ-017"}
    assert all(E.known_code(c) for c in family)


def test_the_named_code_table_is_named_codes():
    """Every named code with its label, highest severity, layers and caps; the receipt-only codes are receipt codes."""
    ours = {c: (n.defect, n.max_severity, tuple(sorted(n.layers)), n.ambiguous_cap, n.scope) for c, n in E.NAMED_DIAGNOSTIC_CODES.items()}
    theirs = {c: (s.defect, s.max_severity, tuple(sorted(s.layers)), s.capped_on_ambiguous, s.warning_scope) for c, s in N.NAMED_CODES.items() if not s.finding_only}
    assert ours == theirs
    finding_only = {c: s.max_severity for c, s in N.NAMED_CODES.items() if s.finding_only}
    assert finding_only == {"INT-ARG-001": "error", "INT-REQ-017": "warning", "INT-XENC-001": "warning"}
    assert E.RECEIPT_CODES["INT-ARG-001"].severities == {"error", "warning"} and E.RECEIPT_CODES["INT-XENC-001"].severities == {"warning"}
    assert "INT-REQ-017" in E.NAMED_ONLY and E.ARGUMENT_RULES == N.ARG_RULES_VERSION


def test_the_labels_and_the_labelled_codes_are_the_translators():
    assert E.DEFECT_LABELS == N.DEFECT_LABELS and len(E.DEFECT_LABELS) == 28
    assert {n.defect for n in E.NAMED_DIAGNOSTIC_CODES.values()} <= set(N.DEFECT_LABELS)
    # every label DEFECT_OF_CODE gives an existing code is one the overseer's table lets that code carry, and no more
    expected: dict[str, set[str]] = {}
    for code in list(E.RECEIPT_CODES) + list(E.NAMED_ONLY):
        for crx, _mrx, label in N.DEFECT_OF_CODE:
            if label is not None and re.fullmatch(crx, code):
                expected.setdefault(code, set()).add(label)
    for code in ("INT-SUBJ-001", "INT-SUBJ-004"):  # a failed STEM check carries its own STEM label (or its kind's)
        expected[code] = {lab for lab in N.DEFECT_LABELS if lab.startswith("stem_")}
    got = {c: set(e.defects) for c, e in E.RECEIPT_CODES.items() if e.defects}
    assert {c: s for c, s in expected.items() if c in E.RECEIPT_CODES} == got
    assert E.STEM_DEFECTS == {lab for lab in N.DEFECT_LABELS if lab.startswith("stem_")}


def test_every_status_and_engine_code_is_known():
    assert set(E.ENGINE_STATUSES) == {s.value for s in VerificationStatus}
    assert {s for s, k in E.ENGINE_STATUSES.items() if k == "definitive"} == {s.value for s in DEFINITIVE}
    assert E.TRANSLATION_STATUSES == tuple(s.value for s in TranslationStatus)
    assert E.RECEIPT_STATUSES == tuple(s.value for s in TransmissionStatus)
    assert set(E.ENGINE_DIAGNOSTICS) == {c.value for c in engine_errors.DiagnosticCode}
    assert E.NO_VERDICT_CODES == engine_errors.NO_VERDICT_CODES and E.ADVISORY_CODES == engine_errors.ADVISORY_CODES


def _reason_leads(module_path: pathlib.Path, func: str, target: str) -> list[str]:
    """The literal start of every item a function appends or extends onto ``target`` (an f-string's first constant part)."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func)
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ("append", "extend") \
                and isinstance(node.func.value, ast.Name) and node.func.value.id == target and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.GeneratorExp):
                arg = arg.elt
            if isinstance(arg, ast.BinOp):
                arg = arg.left
            if isinstance(arg, ast.JoinedStr) and arg.values and isinstance(arg.values[0], ast.Constant):
                out.append(arg.values[0].value)
            elif isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                out.append(arg.value)
    return out


def test_every_release_refusal_has_its_rule():
    """Every reason the engine's release check appends starts with a lead of one of the nine rules (rules 8 and 9 are the
    argument diagnosis), and every unresolved item of the outcome's release assessment has a class."""
    leads = _reason_leads(SRC / "engine" / "release.py", "release_check", "reasons")
    assert len(leads) >= 12
    assert all(E.release_rule_of(x) is not None for x in leads), [x for x in leads if E.release_rule_of(x) is None]
    assert {E.release_rule_of(x) for x in leads} == {1, 2, 3, 4, 5, 6, 7, 9}  # rule 8's lines come from named.blocking_release_lines
    d = N.named_diagnostic("ARG-AC-001", claim_ids=["c"], derivation="engine_recheck", message="m")
    capped = N.cap([N.named_diagnostic("EVD-LACK-001", claim_ids=["c"], derivation="grounding_record", message="m")], "info", "not_source_bound")
    lines = N.blocking_release_lines([d, *capped], "named defect", 16)
    assert len(lines) == 2 and all(E.release_rule_of(x) == 8 for x in lines)
    outcome = _reason_leads(SRC / "translate" / "outcome.py", "assess_release", "unresolved")
    assert len(outcome) >= 15 and all(E.outcome_reason_of(x) is not None for x in outcome), [x for x in outcome if E.outcome_reason_of(x) is None]
    assert E.outcome_reason_of(N.blocking_release_lines([d], "named defect on this claim", 8)[0]) == "named_defect"
    assert E.release_rule_of("everything is fine") is None and E.outcome_reason_of("released") is None  # never read as a pass


def test_the_named_policies_blocking_prefixes_and_named_rejections_are_the_translators():
    assert E.NAMED_POLICIES == tuple(sorted(ENGINE_POLICIES)) and E.BLOCKING_PREFIXES == _BLOCKING_PREFIXES
    for code in E.NAMED_REJECTIONS:
        if code.startswith("INT-"):
            assert E.RECEIPT_CODES[code].severities == {"error"} and code.startswith(_BLOCKING_PREFIXES) or code == "INT-SYNTH-014"
        else:
            assert E.ENGINE_DIAGNOSTICS[code] in ("invalid", "limits", "service"), code
    assert E.risk_of("INT-SYNTH-014", "error") == "rejection" and E.risk_of("INT-REQ-009", "error") == "rejection"
    from epinoic_logic.engine.policies import UnknownPolicyError, named_policy
    from epinoic_logic.engine import SolverConfig
    with pytest.raises(UnknownPolicyError):
        named_policy("nonlinear ", SolverConfig())  # a name that is not exactly an allowlisted one is refused before anything runs


# ============================================================================================ the audit, family by family
def _essay_channel(auditor):
    plan = make_plan(plan_id="plan-ess", request_id=ESSAY["request_id"], task_id=ESSAY["task_id"], subject=ESSAY["subject"], task_type=ESSAY["task_type"],
                     selected_agent_ids=["writer-1"], allowed_document_ids=[], agent_subjects={}, agent_task_types={})
    ch = new_channel(auditor, plan)
    m, _req, _rq = ch.request("router", "writer-1", ESSAY_QUESTION, [])
    return ch, m


def _essay(auditor):
    ch, m = _essay_channel(auditor)
    _reply, rc = ch.respond(m.message_id, essay_report("writer-1", "rep-writer-1", 3, prefix="w1"))
    return ch, rc


def _rcpt004(audit, needle: str) -> list:
    return [f for f in findings(audit, "OVS-RCPT-004") if needle in f.message]


def test_control_a_genuine_named_defect_is_on_the_receipt_and_raises_nothing():
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _essay(aud)
        arg = [f for f in rc.findings if f.code == "INT-ARG-001"]
        assert arg and all(f.severity == "warning" and f.defect == "bare_assertion" for f in arg)
        audit = aud.audit(ch.uid)
        assert not findings(audit, "OVS-RCPT-004") and audit.transfer_states[rc.message_id] != "AUDIT_FAILED"
    finally:
        aud.close()


def test_a_dropped_named_defect_fails_the_transfer(monkeypatch):
    """A receipt whose INT-ARG-001 for a report-level named defect (ARG-BARE-001, warning) is dropped: the overseer re-runs
    the report-level diagnosis on the journaled report and names it (rule argument-image)."""
    orig = TranslatorChannel._argument_diagnosis

    def drop(self, *a, **k):
        named, arg, info = orig(self, *a, **k)
        return named, [], info
    monkeypatch.setattr(TranslatorChannel, "_argument_diagnosis", drop)
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _essay(aud)
        assert not [f for f in rc.findings if f.code == "INT-ARG-001"] and any(d.code == "ARG-BARE-001" for d in rc.named_diagnostics)
        clr = aud.clearance(ch.uid, rc.message_id, receipt=rc)
        assert clr.state == "AUDIT_FAILED" and "OVS-RCPT-004" in clr.codes
        assert _rcpt004(aud.audit(ch.uid), "INT-ARG-001") and _rcpt004(aud.audit(ch.uid), "ARG-BARE-001")
    finally:
        aud.close()


def test_a_lowered_named_defect_fails_the_transfer(monkeypatch):
    orig = TranslatorChannel._argument_diagnosis

    def lower(self, *a, **k):
        named, arg, info = orig(self, *a, **k)
        return named, [f.model_copy(update={"severity": "info"}) for f in arg], info
    monkeypatch.setattr(TranslatorChannel, "_argument_diagnosis", lower)
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _essay(aud)
        assert {f.severity for f in rc.findings if f.code == "INT-ARG-001"} == {"info"}
        assert [f for f in _rcpt004(aud.audit(ch.uid), "INT-ARG-001") if "severity info" in f.message]
    finally:
        aud.close()


def test_control_a_load_bearing_writers_assumption_is_carried_and_raises_nothing():
    aud = make_auditor(shadow="off")
    try:
        task = run_task(aud)
        rc = task.receipts["rep_en"]
        assert any(d.code == "ARG-LINK-001" and d.severity == "info" for d in rc.named_diagnostics)
        assert not [f for f in rc.findings if f.code == "INT-ARG-001"]  # an info record is never a finding
        assert not findings(task.audit(), "OVS-RCPT-004") and not findings(task.audit(), "OVS-TRN-007")
    finally:
        aud.close()


def test_a_writers_assumption_dropped_from_the_receipt_fails_the_transfer(monkeypatch):
    orig = TranslatorChannel._argument_diagnosis

    def drop(self, *a, **k):
        named, arg, info = orig(self, *a, **k)
        return [d for d in named if d.code != "ARG-LINK-001"], arg, info
    monkeypatch.setattr(TranslatorChannel, "_argument_diagnosis", drop)
    aud = make_auditor(shadow="off")
    try:
        task = run_task(aud)
        rc = task.receipts["rep_en"]
        assert not any(d.code == "ARG-LINK-001" for d in rc.named_diagnostics)
        hits = [f for f in _rcpt004(task.audit(), "named diagnostics absent") if "ARG-LINK-001" in f.message]
        assert hits and task.audit().transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


def _outcome_tamper(fn):
    """A verify_claim_fn that tampers with the genuine outcome of the English point (the summary left as composed)."""
    from .conftest import outcome_for, point_problem

    def verify(claim, report):
        if claim.claim_id != "en-point":
            return None
        out = outcome_for(claim, report, point_problem())
        return fn(out)
    return verify


def test_control_an_unchecked_source_is_carried_capped_and_raises_nothing():
    aud = make_auditor(shadow="off")
    try:
        ch = new_channel(aud, verify_claim_fn=_outcome_tamper(lambda o: o))
        m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report())
        [o] = rc.outcomes
        evd = [d for d in o.named_diagnostics if d.code == "EVD-SRC-001"]
        assert evd and evd[0].severity == "info" and evd[0].capped_from == "warning" and o.release is not None and not o.release.permitted
        audit = aud.audit(ch.uid)
        assert not findings(audit, "OVS-TRN-007") and not findings(audit, "OVS-RCPT-004")
    finally:
        aud.close()


@pytest.mark.parametrize("tamper", ["dropped", "uncapped_lower", "release_permitted"])
def test_an_unchecked_source_or_a_release_refusal_dropped_from_an_outcome_fails_the_transfer(tamper):
    """The outcome's own named diagnostics or release assessment altered, its summary left as composed: rule diagnosis-image
    (OVS-TRN-007) derives them again from the translation and the signed result. A release refusal dropped (the outcome
    says permitted while a capped unchecked source still blocks release) is the same fault."""
    def fn(o):
        if tamper == "dropped":
            return o.model_copy(update={"named_diagnostics": [d for d in o.named_diagnostics if d.code != "EVD-SRC-001"]})
        if tamper == "uncapped_lower":  # the cap's record removed: shown at info and no longer blocking (a downgrade)
            return o.model_copy(update={"named_diagnostics": [d.model_copy(update={"capped_from": None, "cap_reason": None}) if d.code == "EVD-SRC-001" else d
                                                              for d in o.named_diagnostics]})
        return o.model_copy(update={"release": o.release.model_copy(update={"permitted": True, "unresolved": []})})
    aud = make_auditor(shadow="off")
    try:
        ch = new_channel(aud, verify_claim_fn=_outcome_tamper(fn))
        m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
        _reply, rc = ch.respond(m.message_id, english_report())
        audit = aud.audit(ch.uid)
        hit = [f for f in findings(audit, "OVS-TRN-007") if "rule diagnosis-image" in f.message]
        assert hit and audit.transfer_states[rc.message_id] == "AUDIT_FAILED" and hit[0].claim_ids == ["en-point"]
    finally:
        aud.close()


PHYSICS_REQUEST = "A trolley of mass 2.0 kg moves at 3.0 m s⁻¹. Calculate its kinetic energy. Show your working."
WRONG_LAW = "Using E_k = ½mv, E_k = 0.5 × 2.0 × 3.0 = 3.0 J.\n\nThe kinetic energy is 3.0 J."
RIGHT_LAW = "Using E_k = ½mv², E_k = 0.5 × 2.0 × 3.0² = 9.0 J.\n\nThe kinetic energy is 9.0 J."


def _physics(auditor, text):
    plan = make_plan(plan_id="plan-ph", subject="Physics", task_type="calculation", selected_agent_ids=["physics-specialist"], allowed_document_ids=[],
                     agent_subjects={}, agent_task_types={})
    ch = new_channel(auditor, plan)
    m, _r, _q = ch.request("router", "physics-specialist", PHYSICS_REQUEST, [])
    _msg, rc = ch.respond_text(m.message_id, text, agent_id="physics-specialist", report_id="rep-ph-1")
    return ch, rc


def test_control_a_stem_method_error_is_named_and_a_correct_law_raises_nothing():
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _physics(aud, WRONG_LAW)
        ref = [f for f in rc.structural_findings if f.code == "ST-REF-001"]
        assert ref and ref[0].defect == "stem_wrong_formula" and any(d.code == "ST-REF-001" for d in rc.named_diagnostics)
        assert not findings(aud.audit(ch.uid), "OVS-RCPT-004")
        ch2, rc2 = _physics(aud, RIGHT_LAW)
        assert not [f for f in rc2.structural_findings if f.code.startswith("ST-REF")] and not findings(aud.audit(ch2.uid), "OVS-RCPT-004")
    finally:
        aud.close()


@pytest.mark.parametrize("tamper", ["label", "finding"])
def test_a_stem_method_error_dropped_or_unlabelled_fails_the_transfer(monkeypatch, tamper):
    """ST-REF-001 (stem_wrong_formula) with its label stripped (so the receipt names no diagnostic for it) or dropped
    outright: the overseer's label rule and the STEM packs' re-derivation (rule stem-structural) name it."""
    orig = TranslatorChannel._finish

    def fin(self, msg, direction, findings_, *a, structural=(), **kw):
        if tamper == "label":
            structural = [f.model_copy(update={"defect": None}) if f.code == "ST-REF-001" else f for f in structural]
        else:
            structural = [f for f in structural if f.code != "ST-REF-001"]
        return orig(self, msg, direction, findings_, *a, structural=structural, **kw)
    monkeypatch.setattr(TranslatorChannel, "_finish", fin)
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _physics(aud, WRONG_LAW)
        assert not any(d.code == "ST-REF-001" for d in rc.named_diagnostics)
        audit = aud.audit(ch.uid)
        assert _rcpt004(audit, "ST-REF-001") and audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
        if tamper == "label":
            assert _rcpt004(audit, "finding labels absent")
    finally:
        aud.close()


RUNNER = "A runner covers 2.5 km in 10 min. Calculate the runner's average speed in m s⁻¹. [2 marks]"
UNIT_SLIP = "Using v = d/t, v = 2.5 km / 10 min = 0.25 m s⁻¹."  # holds as written, fails in SI: the check's own label


def _runner(auditor, text=UNIT_SLIP):
    plan = make_plan(plan_id="plan-run", subject="Physics", task_type="short_answer", selected_agent_ids=["physics-specialist"], allowed_document_ids=[],
                     agent_subjects={}, agent_task_types={})
    ch = new_channel(auditor, plan)
    m, _r, _q = ch.request("router", "physics-specialist", RUNNER, [])
    _msg, rc = ch.respond_text(m.message_id, text, agent_id="physics-specialist", report_id="rep-run-1")
    return ch, rc


def _subject_labels(rc) -> list:
    return [(f.code, f.defect) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]


def test_control_a_failed_checks_own_label_is_accepted_though_the_receipt_does_not_journal_it():
    """Regression (integration step): the unit companion's own label (stem_unit_error on a check whose kind reads as an
    arithmetic slip) is the label the channel gives; the receipt carries no FormalCheck, so the live rule took the kind's
    label as the only truth and raised a false RCPT-004 on genuine STEM transfers (probes units-task-only, units-prefix).
    The receipt check now leaves a carried label to R2, which compares it with the re-derived check: nothing is raised."""
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _runner(aud)
        assert _subject_labels(rc) == [("INT-SUBJ-001", "stem_unit_error")]
        assert N.defect_of("INT-SUBJ-001", next(f.message for f in rc.findings if f.code == "INT-SUBJ-001")) == "stem_arithmetic_slip"
        assert any(d.code == "INT-SUBJ-001" and d.defect == "stem_unit_error" for d in rc.named_diagnostics)
        audit = aud.audit(ch.uid)
        assert not findings(audit, "OVS-RCPT-004") and audit.transfer_states[rc.message_id] != "AUDIT_FAILED"
    finally:
        aud.close()


@pytest.mark.parametrize("tamper", ["relabelled", "dropped"])
def test_a_failed_checks_label_changed_or_dropped_fails_the_transfer(monkeypatch, tamper):
    """The unit error relabelled as the arithmetic slip its kind reads as (finding and named diagnostic agree, so only
    the re-derived check shows it: R2, rule argument-image), or left unlabelled (the receipt check sees that a check of
    this kind always carries a label, and R2 names the one it lacks)."""
    orig_finish, orig_labelled = TranslatorChannel._finish, TranslatorChannel._labelled

    def fin(self, msg, direction, findings_, *a, **kw):
        new = "stem_arithmetic_slip" if tamper == "relabelled" else None
        findings_ = [f.model_copy(update={"defect": new}) if f.code == "INT-SUBJ-001" else f for f in findings_]
        return orig_finish(self, msg, direction, findings_, *a, **kw)
    monkeypatch.setattr(TranslatorChannel, "_finish", fin)
    if tamper == "dropped":
        monkeypatch.setattr(TranslatorChannel, "_labelled", staticmethod(lambda f: f if f.code == "INT-SUBJ-001" else orig_labelled(f)))
    aud = make_auditor(shadow="off")
    try:
        ch, rc = _runner(aud)
        assert _subject_labels(rc) == [("INT-SUBJ-001", "stem_arithmetic_slip" if tamper == "relabelled" else None)]
        audit = aud.audit(ch.uid)
        r2 = _rcpt004(audit, "rule argument-image")
        assert r2 and "implies the defect label 'stem_unit_error'" in r2[0].message
        assert ("carries 'stem_arithmetic_slip'" if tamper == "relabelled" else "lacks it") in r2[0].message
        assert bool(_rcpt004(audit, "finding labels absent")) is (tamper == "dropped")
        assert audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


def _xenc_run(monkeypatch, drop: bool):
    """End-to-end B20 (two encodings of one claim, opposite answers) on an audited hub: s01's kinetic-energy check fails
    while a translation that drops the 1/2 entails 18 J."""
    from functools import partial
    from epinoic_logic.branches import RouterHub
    from epinoic_logic.overseer import EngineKey, KeyRing, TransferAuditor
    from ..channel import dev_case_hub as dev
    from ..channel.test_encoding_disagreement_b20 import kinetic_energy_proposal
    from .conftest import HAND_BUILT_TRANSLATORS, SECRET
    keyring = KeyRing({"channel": EngineKey(dev.KEY)}, SECRET)
    aud = TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="off", hand_built_translators=HAND_BUILT_TRANSLATORS, inline_final_release=True)
    monkeypatch.setattr(dev, "RouterHub", partial(RouterHub, auditor=aud))
    if drop:
        monkeypatch.setattr(TranslatorChannel, "_encoding_disagreements", lambda self, *a, **k: [])
    from ..argdiag_cases import load_case
    case = load_case("s01_arith_slip")
    case["translations"] = [{"contains": "0.5 × 2.0 × 3.0² = 18 J", "proposal": kinetic_energy_proposal(keep_half=False, stated="18")}]
    return aud, dev.run_case("s01_arith_slip", case=case)


@pytest.mark.parametrize("drop", [False, True])
def test_two_encodings_that_disagree_are_named_and_the_drop_fails_the_transfer(monkeypatch, drop):
    try:
        aud, run = _xenc_run(monkeypatch, drop)
    except (KeyError, FileNotFoundError, StopIteration) as exc:  # the development case is part of the repository's data
        pytest.fail(f"the B20 development case could not be built: {exc!r}")
    try:
        uid = run.channel.channel_uid
        xenc = [f for f in run.receipt.findings if f.code == "INT-XENC-001"]
        audit = aud.audit(uid)
        if not drop:
            assert xenc and not _rcpt004(audit, "INT-XENC-001")  # control: the genuine receipt names the disagreement
        else:
            assert not xenc and _rcpt004(audit, "INT-XENC-001") and audit.transfer_states[run.receipt.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


def _bad_vocabulary_synthesis(auditor, *, as_mapping: bool = False):
    """The overseer fixture task, then the combinator's synthesis whose transformation is free text (the end-to-end
    simulation's bug 7): an object built around validation (``model_copy``), which the journal holds as the synthesis it
    claims to be, or (``as_mapping``) a mapping, which the channel journals as an unreadable payload by its digest only."""
    from epinoic_logic.integrity import AgentRole
    from .conftest import default_synthesis
    task = run_task(auditor, synthesis=False)
    good = default_synthesis()
    bad = good.model_copy(update={"claims": [good.claims[0].model_copy(update={"transformation": "rewrote the claim in plainer words"}), *good.claims[1:]]})
    payload = bad.model_dump(mode="json") if as_mapping else bad
    _m, rc = task.ch.relay("combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    return task, rc, payload


def test_control_a_named_rejection_is_on_the_receipt_and_raises_nothing():
    aud = make_auditor(shadow="off")
    try:
        task, rc, _syn = _bad_vocabulary_synthesis(aud)
        assert rc.status is TransmissionStatus.REJECTED and {"INT-REQ-009", "INT-SYNTH-014"} <= {f.code for f in rc.findings}
        assert not _rcpt004(task.audit(), "INT-SYNTH-014")
        assert E.risk_reading(aud.view(task.uid))[0] and "rejection" in E.risk_reading(aud.view(task.uid))[0]
    finally:
        aud.close()


def test_a_named_rejection_dropped_fails_the_transfer(monkeypatch):
    """INT-SYNTH-014 dropped from the receipt of a synthesis the contract refuses (INT-REQ-009 kept, so it is still REJECTED):
    the overseer re-runs the synthesis contract on the journaled payload and names the missing rejection."""
    orig = TranslatorChannel._finish

    def fin(self, msg, direction, findings_, *a, **kw):
        return orig(self, msg, direction, [f for f in findings_ if f.code != "INT-SYNTH-014"], *a, **kw)
    monkeypatch.setattr(TranslatorChannel, "_finish", fin)
    aud = make_auditor(shadow="off")
    try:
        task, rc, _syn = _bad_vocabulary_synthesis(aud)
        assert rc.status is TransmissionStatus.REJECTED and "INT-SYNTH-014" not in {f.code for f in rc.findings}
        audit = task.audit()
        assert _rcpt004(audit, "INT-SYNTH-014") and audit.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


def test_a_named_rejection_of_an_unreadable_mapping_is_known_but_not_rederived(monkeypatch):
    """The limit of the journal: a mapping that does not validate is journaled by its digest and type only (an unreadable
    payload), so no check can re-derive the name of its rejection; the rejection itself (REJECTED, INT-REQ-009, nothing
    delivered) is still held by the status and delivery rules, and the risk reading still sees a rejection."""
    aud = make_auditor(shadow="off")
    try:
        task, rc, _payload = _bad_vocabulary_synthesis(aud, as_mapping=True)
        assert rc.status is TransmissionStatus.REJECTED and {"INT-REQ-009", "INT-SYNTH-014"} <= {f.code for f in rc.findings}
        view = aud.view(task.uid)
        t = view.by_message[rc.message_id]
        assert "synthesis_id" not in t.payload and t.payload.get("payload_sha256")  # only the digest is journaled
        assert not _rcpt004(task.audit(), "INT-SYNTH-014") and "rejection" in E.risk_reading(view)[0]
    finally:
        aud.close()


# ============================================================================================ risk signals and the pool
def _receipt(**kw):
    base = dict(status=TransmissionStatus.ACCEPTED, findings=[], structural_findings=[], named_diagnostics=[], outcomes=[], named_overflow=0,
                diagnosis_incomplete=[])
    base.update(kw)
    return SimpleNamespace(**base)


def _view(*receipts):
    return SimpleNamespace(transfers=[SimpleNamespace(receipt=r) for r in receipts])


def _f(code, severity, defect=None):
    return SimpleNamespace(code=code, severity=severity, defect=defect)


def _d(code, severity, capped_from=None):
    return N.named_diagnostic(code, severity=severity, claim_ids=["c"], derivation="engine_recheck", message="m") if capped_from is None else \
        N.cap([N.named_diagnostic(code, claim_ids=["c"], derivation="grounding_record", message="m")], "info", "not_source_bound")[0]


@pytest.mark.parametrize("receipt, signals, records", [
    (_receipt(findings=[_f("INT-ARG-001", "warning", "bare_assertion")]), ("named_defect",), ()),
    (_receipt(named_diagnostics=[_d("ARG-LINK-001", "info")]), (), ("writer_assumption",)),
    (_receipt(named_diagnostics=[_d("EVD-SRC-001", "info", capped_from="warning")]), ("unchecked_source",), ()),  # capped: still blocking
    (_receipt(structural_findings=[_f("ST-REF-001", "warning", "stem_wrong_formula")]), ("stem_method",), ()),
    (_receipt(structural_findings=[_f("ST-STEP-002", "info", "stem_invalid_step")]), (), ("stem_method",)),
    (_receipt(findings=[_f("INT-XENC-001", "warning")]), ("encoding_conflict",), ()),
    (_receipt(status=TransmissionStatus.REJECTED, findings=[_f("INT-REQ-009", "error"), _f("INT-SYNTH-014", "error")]), ("rejection",), ()),
    (_receipt(outcomes=[SimpleNamespace(named_diagnostics=[], diagnosis_incomplete=[], verification=SimpleNamespace(
        diagnostics=[SimpleNamespace(code="E112")], argument_rules="argdiag-2"))]), ("withheld_verdict",), ()),
    (_receipt(outcomes=[SimpleNamespace(named_diagnostics=[], diagnosis_incomplete=[], verification=SimpleNamespace(diagnostics=[], argument_rules="argdiag-2/incomplete:x"))]),
     ("diagnosis_incomplete",), ()),
    (_receipt(findings=[_f("INT-REQ-004", "warning"), _f("CORE-QNT-001", "warning")], named_diagnostics=[]), (), ()),  # clean control: heuristics
])
def test_every_family_is_read_as_a_risk_signal_or_record(receipt, signals, records):
    assert E.risk_reading(_view(receipt)) == (signals, records)


PACK_ID = PackIdentity(name="overseer-knowledge-docs", version=PACK_VERSION, sha256="ab" * 32)


def test_a_signal_sends_the_dossier_to_two_instances_and_a_clean_one_to_one():
    cfg = PoolConfig()
    clean = plan_pool([PoolItem(key="a")], cfg, PACK_ID)
    assert clean.instances == ["overseer-pool-1"] and clean.reasons == ["one instance by default"]  # control
    risky = plan_pool([PoolItem(key="a", risk_signals=("named_defect",))], cfg, PACK_ID)
    assert risky.assignments["a"] == ["overseer-pool-1", "overseer-pool-2"] and "risk signals (named_defect)" in risky.reasons[-1]
    records = plan_pool([PoolItem(key="a", risk_records=("writer_assumption",)), PoolItem(key="b")], PoolConfig(per_instance_quota=2), PACK_ID)
    assert records.review_units == 3 and len(records.instances) == 2 and any("risk records only" in r for r in records.reasons)
    with pytest.raises(ValueError):
        PoolItem(key="a", risk_signals=("not_a_class",))


def test_risk_signals_only_ever_escalate_oversight():
    """Over every subset of a batch carrying signals and records: the plan never has fewer instances, nor gives any dossier
    fewer reviewers, than the same batch without them, and never grows past the maximum."""
    keys = [f"k{i}" for i in range(6)]
    for cfg in (PoolConfig(), PoolConfig(per_instance_quota=2), PoolConfig(max_instances=2, per_instance_quota=1)):
        base = plan_pool([PoolItem(key=k) for k in keys], cfg, PACK_ID)
        for n in range(len(keys) + 1):
            for chosen in itertools.combinations(keys, n):
                for kind in ("signals", "records"):
                    items = [PoolItem(key=k, **({"risk_signals": ("stem_method",)} if kind == "signals" else {"risk_records": ("writer_assumption",)}))
                             if k in chosen else PoolItem(key=k) for k in keys]
                    p = plan_pool(items, cfg, PACK_ID)
                    assert len(p.instances) >= len(base.instances) and len(p.instances) <= cfg.max_instances
                    assert all(len(p.assignments[k]) >= len(base.assignments[k]) for k in keys)
                    if kind == "signals":
                        assert all(len(p.assignments[k]) == 2 for k in chosen)


def test_the_hub_reads_the_risk_signals_of_each_task_from_its_journal():
    from .conftest import KEY  # noqa: F401  (the fixture task's keys)
    from epinoic_logic.overseer.pool import OverseerPool
    from epinoic_logic.overseer.pack import installed_pack
    aud = make_auditor(shadow="off")
    try:
        task = run_task(aud)
        seen = {}

        class Silent:
            def __init__(self, agent_id):
                self.agent_id = agent_id
                self.calls = []

            def complete(self, request):
                raise RuntimeError("no model in this test")
        pool = OverseerPool(installed_pack(), lambda agent_id: seen.setdefault(agent_id, Silent(agent_id)))
        from epinoic_logic.branches import RouterHub  # noqa: F401
        signals, records = E.risk_reading(aud.view(task.uid))
        assert signals == ("unchecked_source",) and records == ("writer_assumption",)  # the capped EVD-SRC-001 still blocks release
        plan = pool.plan([PoolItem(key=task.uid, risk_signals=signals, risk_records=records)])
        assert plan.assignments[task.uid] == ["overseer-pool-1", "overseer-pool-2"]
    finally:
        aud.close()


# ============================================================================================ the dossier
def test_the_dossier_shows_the_receipts_and_the_signed_results_diagnosis():
    from epinoic_logic.overseer.dossier import build_dossier
    aud = make_auditor(shadow="off")
    try:
        task = run_task(aud)
        d = build_dossier(aud.view(task.uid), mode="blind", lens="general", agent_id="overseer-general-1", pack=PACK_ID)
        rep = next(t for t in d["transfers"] if t["message_id"] == task.mids["rep_en"])
        assert [x["code"] for x in rep["receipt"]["named_diagnostics"]] == [x.code for x in task.receipts["rep_en"].named_diagnostics]
        req = next(t for t in d["transfers"] if t["message_id"] == task.mids["req_en"])
        assert "named_diagnostics" not in req["receipt"]  # control: a receipt that names none shows nothing new
        rid = task.receipts["rep_en"].outcomes[0].verification.result_id
        assert d["results"][rid]["argument_rules"] == "argdiag-2"
        assert [x["code"] for x in d["results"][rid]["named_diagnostics"]] == ["ARG-LINK-001", "ARG-FACT-001"]
    finally:
        aud.close()


# ============================================================================================ the knowledge pack
def _pack(name: str, d=None) -> str:
    return ((d or installed_pack_dir(PACK_VERSION)) / name).read_text(encoding="utf-8")


def pack_completeness(d=None) -> list[str]:
    """What the pack does not say of the overseer's code tables (empty when complete)."""
    out: list[str] = []
    kinds = _pack("06-kinds-and-codes.md", d)
    sec = kinds.split("## 8. Every code the translator and the channel emit", 1)
    if len(sec) != 2:
        return ["Kinds and codes has no §8 table of every code"]
    sec = sec[1].split("\n## ", 1)[0]
    rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| ([A-Z]{2,7}-[A-Z]{2,10}-\d{3}) \| ([a-z, ]+) \|", sec, re.M)}
    for code, e in E.RECEIPT_CODES.items():
        if code not in rows:
            out.append(f"§8 does not list the receipt code {code}")
        elif set(rows[code].split(", ")) != set(e.severities):
            out.append(f"§8 gives {code} the severities {rows[code]}, not {sorted(e.severities)}")
    for code, n in E.NAMED_DIAGNOSTIC_CODES.items():
        row = re.search(rf"^\| {re.escape(code)} \| ([a-z]+) \| ([a-z_]+) \|", sec.split("**Named diagnostics**", 1)[-1], re.M)
        if row is None or (row.group(1), row.group(2)) != (n.max_severity, n.defect):
            out.append(f"§8 does not list the named code {code} at {n.max_severity} as {n.defect}")
    for code in E.NAMED_ONLY:
        if f"| {code} |" not in sec.split("**Named only.**", 1)[-1]:
            out.append(f"§8 does not list the code {code} named only")
    dossier = _pack("02-dossier.md", d)
    d34 = dossier.split("**D34 ", 1)[-1].split("- **D35", 1)[0]
    for label in E.DEFECT_LABELS:
        if f"`{label}`:" not in d34:
            out.append(f"D34 does not list the label {label}")
    d36 = dossier.split("**D36 ", 1)[-1].split("- **D37", 1)[0]
    for rule in E.RELEASE_RULES:
        if f"{rule.number} " not in d36 or not any(lead.split(" (")[0].rstrip(":( ") in d36 for lead in rule.leads):
            out.append(f"D36 does not state release rule {rule.number} ({rule.name})")
    d37 = dossier.split("**D37 ", 1)[-1].split("\n", 1)[0]
    for code in ("E100", "E108", "E110", "E111", "E112", "W110", "W111", "E505", "E900", "INT-SYNTH-014", "INT-REQ-009"):
        if code not in d37 and code not in dossier.split("**D23 ", 1)[-1].split("\n", 1)[0]:
            out.append(f"D37 does not name {code}")
    for policy in E.NAMED_POLICIES:
        if f" {policy} (" not in d37:
            out.append(f"D37 does not name the engine policy {policy}")
    for status in E.TRANSLATION_STATUSES:
        if status not in d37:
            out.append(f"D37 does not name the translation status {status}")
    if E.ARGUMENT_RULES not in dossier.split("**D33 ", 1)[-1].split("- **D34", 1)[0]:
        out.append("D33 does not name the argument rules")
    return out


def test_the_installed_pack_lists_every_code_status_rule_and_policy_the_translator_emits():
    """The completeness test: pack 1.4 knows every code of the overseer's tables, with its severity and label."""
    assert PACK_VERSION == "1.4" and pack_completeness() == []


@pytest.mark.parametrize("cut", ["| INT-ARG-001 | error, warning |", "| ST-REF-001 | warning |", "`stem_symbol_conflict`:", "argdiag-2"])
def test_a_pack_that_drops_a_code_is_seen(tmp_path, cut):
    """Control: the completeness check is not vacuous."""
    from .test_knowledge_pack import copy_pack
    d = copy_pack(tmp_path)
    for name in ("02-dossier.md", "06-kinds-and-codes.md"):
        text = (d / name).read_text(encoding="utf-8")
        if cut in text:
            (d / name).write_text(text.replace(cut, "| X |" if cut.startswith("|") else "removed"), encoding="utf-8")
    assert pack_completeness(d)


def test_the_pinned_older_packs_never_change():
    """Pack 1.3 is pinned to the digest it was released under (b44776a1...): the argument-diagnostics port's in-place
    correction (0fdf8581...) is released as 1.4, and 1.3's D32 is the table it had (the thirteen ST codes of the STEM method
    faults are 1.4's)."""
    from epinoic_logic.overseer.pack import PACK_DIGESTS, load_pack
    assert load_pack(installed_pack_dir("1.3")).identity.sha256 == PACK_DIGESTS[("overseer-knowledge-docs", "1.3")] == \
        "b44776a1d76a0ee1ac8b02cd9e3596c832ee3dbfe51fff76d8c09ec4970c6f67"
    old = _pack("02-dossier.md", installed_pack_dir("1.3"))
    new = _pack("02-dossier.md")
    assert "| ST-REF-001 |" not in old and "| ST-REF-001 |" in new and "**D33 " not in old and "**D33 " in new
