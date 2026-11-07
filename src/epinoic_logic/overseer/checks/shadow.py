"""B5 shadow-channel replay: a fresh channel fed the journaled inputs must issue the same receipts.

A fresh ``TranslatorChannel`` is built from the journaled plan and configuration, with the channel's branch registry
and the auditor's run key (``overseer-run``; never an engine key). Its ``verify_claim_fn`` serves the journaled
``TranslationResult`` of each claim (by report id, claim id and claim-text digest) and re-verifies its problem with
the engine; the translator model is never called. The outcome is composed as the live verifier composed it (rule
``composition``, round-8 clearance c1): without the report and the task record, as a hand-built fixture composes it, or,
when that composition's argument diagnosis is not the journaled outcome's, with them, as production's
``translate.outcome.verify_claim`` composes it (its evidence rules read the supplied texts and the task record). The
journaled transfers are re-issued in sequence order:

* requests with the journaled call (items and constraints given, the user input and supplied texts);
* raw texts the hub refused are re-sent as raw text; a raw text that was parsed is re-issued as the delivered report
  through ``respond`` with the same stated sender (exactly what ``respond_text`` does after parsing), so later
  forwards of it compare against the same payload;
* the journaled reports, forwards and syntheses, with message ids mapped to the shadow's.

Per sequence number the status, the MULTISET of ``(code, severity, claim_ids, report_ids)`` finding tuples (two
INT-REQ-004 naming nothing count twice), the coverage records, the constraint results and the outcomes' display statuses
are compared (review round 3).
Excluded: time-dependent codes (INT-HANDOFF-005, 016, 017) and the codes a journal cannot reproduce because their
cause never reaches a receipt (INT-STALE-011, a stale translation the channel dropped; INT-REQ-006 and INT-SYNTH-013,
hooks that raised). When the channel had a synthesis-formalization hook, synthesis transfers are not comparable (the
hook is a model call) and coverage says so.

* An error or a warning the shadow raises more often than the receipt is RCPT-004; a receipt finding the shadow does
  not raise is RCPT-005 (warning); a different status, coverage, constraint results or display statuses is RCPT-008.
* When an undecided engine run (TIMEOUT, UNKNOWN) on either side explains a difference, it is RES-008 instead: the
  environment's nondeterminism never becomes an accusation. Only a run under the channel's pinned configuration (or
  the same with unsat cores on) explains anything: an undecided run under a configuration swapped in later is the
  fault itself.
* Rule ``budget-cut`` (integration gate round 4, decision 87): the channel decides a report's STEM checks under a
  wall-clock budget (``channel.bus.STEM_CHECK_BUDGET_S``, or the smaller per-channel ``stem_budget_s`` the integration
  checks port sets from what its deadline leaves); every STEM check left when it is spent is stated not run
  (``satisfied`` null, no result, INT-SUBJ-002 "check budget"), never success. No replay can reproduce where a clock ran
  out, so the comparison replays the receipt's cut instead of accusing it: each check the receipt states not run under
  its budget is compared in that form (the shadow's findings on that check's run give way to the INT-SUBJ-002 the
  channel writes for a check its budget left), and everything else is compared as before, so a cut whose INT-SUBJ-002
  was dropped is still RCPT-004. The receipt's cut is replayed only when it is the image of the channel's budget rule:
  every check it names is a STEM check the branch packs derive from the journaled report, of the kind they derive; it is
  the end of the report's STEM checks in the packs' order (no STEM check after the first one it names was decided); its
  checks state one budget, written as the channel writes it, at most the module budget; and the journal does not put
  the whole transfer within less time of the transfer before it than that budget. A cut that is not is compared as the
  shadow decides it (a hidden failure stays RCPT-004) and a note says why; a not-run statement in no form the channel
  writes (a budget above the module's, or written otherwise than ``{:g}``) is not read as a cut at all and is compared the
  same way. A cut under the module budget, or under a smaller one the plan's deadline accounts for, is a note (the audit
  verdict does not depend on machine load); a cut under a smaller budget the plan's deadline does not account for is
  RES-008, never an accusation (the journal does not record a channel's budget, so a budget starved between transfers
  cannot be told apart). Checks the shadow's own budget left undecided that the receipt decided are compared in the
  not-run form too, with RES-008 (the auditor's environment).

Limit (stated, not hidden): this shadow runs in the auditor's process with the repository's channel code. It catches
channel STATE corrupted between transfers, dropped or added findings, and environment nondeterminism; a patch to the
channel's CODE that is still active when the shadow runs is executed by the shadow too and is invisible to it. The
receipt-level rules (RCPT-002, RCPT-007) and the batch re-derivations with their own functions (B2-B4) cover that case;
a shadow in a separate process (the design's section 15 mitigation) is not built in this stage.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from ...channel.bus import _DETAIL_MAX, STEM_CHECK_BUDGET_S
from ...channel.contracts import Constraint, RequestItem, TransmissionStatus
from ...engine.results import VerificationResult
from ...engine.runner import verify
from ...engine.sink import capture_results
from ...engine.statuses import VerificationStatus as S
from ...ir.canonical import canonical_json
from ...integrity.contracts import AgentRole, Synthesis, parse_rfc3339
from ...translate.contracts import SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from ...translate.outcome import compose_outcome
from ..keys import RUN_KEY_ID
from ..faithful import faithful
from ..view import Transfer
from . import CheckContext

__all__ = ["run_shadow", "SHADOW_EXCLUDED", "budget_cut_checks"]

SHADOW_EXCLUDED = frozenset({"INT-HANDOFF-005", "INT-HANDOFF-016", "INT-HANDOFF-017", "INT-STALE-011", "INT-REQ-006", "INT-SYNTH-013"})
_UNDECIDED = (S.TIMEOUT.value, S.UNKNOWN.value)

# ------------------------------------------------------------------ rule budget-cut (integration gate round 4)
#: How the channel states a branch check its report's STEM check budget left undecided (``TranslatorChannel._branch_checks``):
#: the check's ``detail`` is "<kind><where>: <clause><description>" followed by the first pair below around the budget, and
#: the INT-SUBJ-002 naming it is "<kind> check<where>" followed by the second pair around the budget; the budget is written
#: ``{:g}``. Held equal to the channel's text by the tests (a channel run under a budget of 0 s).
_CUT_DETAIL = ("; not run: the report's STEM check budget (", " s) was spent")
_CUT_MESSAGE = (" undecided (check budget: the report's STEM checks ran past ", " s; not run): ")
#: The module's STEM check budget, bound at import: the upper bound of every channel's budget (``channel.bus.stem_budget_s``),
#: so a budget a receipt states above it is none the channel can have used.
_MODULE_BUDGET_S = float(STEM_CHECK_BUDGET_S)
#: The codes of the findings the channel derives from one decided branch check's signed run, each naming that run's result
#: id (``_decide_branch_check``: INT-SUBJ-001, -002, -004; ``_encoding_disagreements``: INT-XENC-001).
_CHECK_CODES = frozenset({"INT-SUBJ-001", "INT-SUBJ-002", "INT-SUBJ-004", "INT-XENC-001"})
#: The channel times its budget with ``time.perf_counter``, the journal stamps events with ``time.monotonic_ns``.
_CLOCK_TOLERANCE_S = 0.05
#: The plan's ``deadline_at`` is written to the second by the integration checks port, and a wall clock may step.
_DEADLINE_TOLERANCE_S = 2.0
#: A check kind at the start of a branch check's ``detail`` (``stem_arithmetic``, ``chronology``): anchored and bounded.
_KIND_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")
_BUDGET_TEXT_MAX = 32


def _diagnosis_of(outcome: Any) -> list[str]:
    """An outcome's argument diagnosis, as compared by rule ``composition``: its named diagnostics in canonical form."""
    try:
        return [canonical_json(d.model_dump(mode="json")) for d in getattr(outcome, "named_diagnostics", None) or ()]
    except Exception:
        return []


def _tuples(findings) -> Counter:
    """The receipt's findings as a multiset of ``(code, severity, claim_ids, report_ids)``: two findings of one code
    that name nothing (one INT-REQ-004 per unaddressed item) count twice, so deleting one of them is a difference."""
    out: Counter = Counter()
    for f in findings:
        if f.code in SHADOW_EXCLUDED:
            continue
        out[_tuple(f)] += 1
    return out


def _tuple(f) -> tuple:
    return (f.code, f.severity, tuple(sorted(f.claim_ids)), tuple(sorted(f.report_ids)))


def _where(claim_ids) -> str:
    """The channel's statement of where a branch check's statement is (``TranslatorChannel._check_claims_named``)."""
    cids = [str(c) for c in claim_ids]
    return (f" in claim {', '.join(cids)}" if len(cids) == 1 else f" in claims {', '.join(cids)}") if cids else ""


def _kind(cr) -> Optional[str]:
    """The kind a branch check's ``detail`` starts with (every form the channel writes starts with it), or None."""
    m = _KIND_RE.match(cr.detail or "")
    return m.group(0) if m else None


def _budget_value(text: Optional[str]) -> Optional[float]:
    """The budget a cut states, when it is one the channel can have used and is written as the channel writes it (``{:g}``):
    at least 0 s and at most the module budget. None otherwise."""
    if not text or len(text) > _BUDGET_TEXT_MAX:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    if not (0.0 <= value <= _MODULE_BUDGET_S) or format(value, "g") != text:
        return None
    return value


def _cut_statements(findings) -> dict[str, list[tuple[str, tuple]]]:
    """``"<kind> check<where>"`` -> ``[(budget text, finding tuple)]`` for every INT-SUBJ-002 in the channel's form for a
    check its report's STEM check budget left undecided (one pass over the findings; each message is searched once, and the
    budget only within the few characters after the marker)."""
    out: dict[str, list[tuple[str, tuple]]] = {}
    head, tail = _CUT_MESSAGE
    for f in findings:
        if f.code != "INT-SUBJ-002" or f.formal_result_id:
            continue
        msg = f.message or ""
        i = msg.find(head)
        if i <= 0:
            continue
        start = i + len(head)
        j = msg.find(tail, start, start + _BUDGET_TEXT_MAX + len(tail))
        if j < 0:
            continue
        out.setdefault(msg[:i], []).append((msg[start:j], _tuple(f)))
    return out


def budget_cut_checks(receipt) -> dict[str, tuple[str, str]]:
    """Rule ``budget-cut``: check id -> ``(kind, budget text)`` for every branch check ``receipt`` states, in the channel's
    form, as not run because its report's STEM check budget was spent: ``satisfied`` null, method ``formal``, no result id
    and no status, a ``stem_*`` kind, its claims as the detail names them, and the budget read from the end of the detail
    (or, when the detail was cut at the contract length, from the INT-SUBJ-002 naming the check), one the channel can have
    used (:func:`_budget_value`)."""
    out: dict[str, tuple[str, str]] = {}
    statements: Optional[dict] = None
    head, tail = _CUT_DETAIL
    for cr in receipt.formal_checks:
        if cr.satisfied is not None or cr.method != "formal" or cr.formal_result_id or cr.formal_status:
            continue
        kind = _kind(cr)
        if kind is None or not kind.startswith("stem_"):
            continue
        where = _where(cr.claim_ids)
        detail = cr.detail or ""
        if not detail.startswith(f"{kind}{where}: "):
            continue
        budget: Optional[str] = None
        if detail.endswith(tail):
            i = detail.rfind(head)
            if i >= 0:
                budget = detail[i + len(head):len(detail) - len(tail)]
        elif len(detail) >= _DETAIL_MAX and detail.endswith("..."):
            if statements is None:
                statements = _cut_statements(receipt.findings)
            found = statements.get(f"{kind} check{where}")
            budget = found[0][0] if found else None
        if _budget_value(budget) is not None:
            out[cr.constraint_id] = (kind, budget)
    return out


@dataclass
class _BudgetCut:
    """What the comparison of one transfer replays of the two sides' STEM check budgets (rule ``budget-cut``)."""
    #: the checks the receipt states not run under its budget, when that cut is the channel's budget rule's image
    receipt_cut: list = field(default_factory=list)
    budget: Optional[str] = None
    #: why a cut under a reduced budget is not accounted for by the plan's deadline (RES-008), or None
    unexplained: Optional[str] = None
    #: why the receipt's cut is not the image of the channel's budget rule (compared as the shadow decides it), or None
    refused: Optional[str] = None
    refused_checks: int = 0
    #: the checks the shadow's own budget left undecided that the receipt decided (RES-008)
    shadow_cut: list = field(default_factory=list)
    shadow_budget: Optional[str] = None
    #: what the journal bounds the transfer's duration by
    timing: str = ""


def _replay_cut(counter: Counter, findings, result_ids: set, adds: list) -> None:
    """State, in ``counter`` (one side's finding tuples), the checks whose runs are ``result_ids`` as the channel states a
    check its budget left undecided: the findings the channel derives from those runs give way to ``adds``."""
    for f in findings:
        if f.formal_result_id and f.formal_result_id in result_ids and f.code in _CHECK_CODES and f.code not in SHADOW_EXCLUDED:
            k = _tuple(f)
            if counter.get(k, 0) > 0:
                counter[k] -= 1
                if not counter[k]:
                    del counter[k]
    for k in adds:
        counter[k] += 1


def _cut_tuple(claim_ids, report_id: Optional[str], statements: dict, kind: str) -> tuple:
    """The finding tuple of the INT-SUBJ-002 the channel writes for a check its budget left undecided: the claims holding its
    statement and the report. A check whose statement no delivered claim holds is named by the pack's own claim ids, which
    only the side that cut it states: its next such statement of that kind (``statements``, the side's
    :func:`_cut_statements`, consumed in order)."""
    cids = tuple(sorted(str(c) for c in claim_ids))
    if cids:
        return ("INT-SUBJ-002", "warning", cids, (report_id,) if report_id else ())
    found = statements.get(f"{kind} check")
    return found.pop(0)[1] if found else ("INT-SUBJ-002", "warning", (), ())


def _deadline_unexplained(ctx: CheckContext, t: Transfer, value: float) -> Optional[str]:
    """Why a cut under a budget ``value`` below the module budget is not what the plan's deadline left (None when it is).
    The integration checks port sets a channel's budget to ``min(STEM_CHECK_BUDGET_S, time left)`` before the transfer, so
    at the transfer's end (its journaled ``created_at``) the plan's ``deadline_at`` leaves at most that budget, within the
    tolerance of the second the deadline is written to."""
    plan = ctx.view.plan
    deadline = parse_rfc3339(getattr(plan, "deadline_at", None)) if plan is not None else None
    if deadline is None:
        return "the plan states no deadline"
    end = parse_rfc3339(t.event.created_at)
    if end is None:
        return "the transfer's journaled time cannot be read against the plan's deadline"
    left = max(0.0, (deadline - end).total_seconds())
    if value + _DEADLINE_TOLERANCE_S < min(_MODULE_BUDGET_S, left):
        return f"the plan's deadline left {left:.1f} s at the end of the transfer"
    return None


def _budget_cuts(ctx: CheckContext, t: Transfer, prev: Optional[Transfer], rc, ours: Counter, theirs: Counter) -> tuple[_BudgetCut, Any, Any]:
    """Rule ``budget-cut`` for one transfer (module docstring): replays the receipt's cut on the shadow's finding tuples
    (``ours``) when it is the image of the channel's budget rule, and the shadow's own cut on the receipt's (``theirs``),
    both in place. Returns the record and the shadow's and the receipt's statuses as compared: a status ACCEPTED on a side
    the replay gave a not-run check is ACCEPTED_WITH_FINDINGS, as the channel's status rule makes it for any finding."""
    out = _BudgetCut()
    receipt = t.receipt
    s_status, r_status = rc.status, receipt.status
    cut_r, cut_h = budget_cut_checks(receipt), budget_cut_checks(rc)
    if not cut_r and not cut_h:
        return out, s_status, r_status
    shadow_by: dict[str, Any] = {}
    for c in rc.formal_checks:
        shadow_by.setdefault(c.constraint_id, c)
    receipt_by: dict[str, Any] = {}
    for c in receipt.formal_checks:
        receipt_by.setdefault(c.constraint_id, c)
    order = list(shadow_by)  # the packs' order: the order the channel decides a report's checks in
    position = {cid: n for n, cid in enumerate(order)}
    rid = t.report_id
    if cut_r:
        why: Optional[str] = None
        budgets = sorted({b for _k, b in cut_r.values()})
        stray = [cid for cid in cut_r if cid not in shadow_by]
        other_kind = [cid for cid, (k, _b) in cut_r.items() if cid in shadow_by and _kind(shadow_by[cid]) != k]
        if len(budgets) != 1:
            why = f"its checks state different budgets ({', '.join(b + ' s' for b in budgets[:4])})"
        elif stray:
            why = f"it names checks the branch packs do not derive from the journaled report ({', '.join(stray[:4])})"
        elif other_kind:
            why = f"it names checks of another kind than the packs derive ({', '.join(other_kind[:4])})"
        else:
            first = min(position[cid] for cid in cut_r)
            after = [cid for cid in order[first:] if cid not in cut_r and cid in receipt_by and (_kind(shadow_by[cid]) or "").startswith("stem_")]
            if after:
                why = (f"STEM checks after the first one it names are stated otherwise ({', '.join(after[:4])}), and the budget leaves every STEM check after "
                       "the first one it leaves undecided")
        value = _budget_value(budgets[0]) if budgets else None
        if why is None and prev is not None:
            elapsed = (t.event.monotonic_ns - prev.event.monotonic_ns) / 1e9
            out.timing = f"; the journal puts the transfer within {elapsed:.2f} s of the transfer before it"
            if value is None or elapsed + _CLOCK_TOLERANCE_S < value:
                why = f"the journal puts the whole transfer within {elapsed:.2f} s of the transfer before it, less than the {budgets[0]} s budget it states spent"
        elif why is None:
            out.timing = "; no earlier transfer is journaled, so the transfer's duration is not bounded"
        if why is not None:
            out.refused, out.refused_checks = why, len(cut_r)
        else:
            out.budget = budgets[0]
            out.receipt_cut = [cid for cid in order if cid in cut_r]
            if value is not None and value < _MODULE_BUDGET_S:
                out.unexplained = _deadline_unexplained(ctx, t, value)
            statements = _cut_statements(receipt.findings)
            result_ids, adds = set(), []
            for cid in out.receipt_cut:
                scr = shadow_by[cid]
                if cid in cut_h or not scr.formal_result_id:
                    continue  # the shadow cut it too (the same statement on both sides), or decided it in no run (compared as it is)
                result_ids.add(scr.formal_result_id)
                adds.append(_cut_tuple(scr.claim_ids, rid, statements, cut_r[cid][0]))
            if adds:
                _replay_cut(ours, rc.findings, result_ids, adds)
                if s_status is TransmissionStatus.ACCEPTED:
                    s_status = TransmissionStatus.ACCEPTED_WITH_FINDINGS
    if cut_h:
        statements = _cut_statements(rc.findings)
        result_ids, adds = set(), []
        for cid in order:
            if cid not in cut_h or cid in cut_r:
                continue
            rcr = receipt_by.get(cid)
            if rcr is None or not rcr.formal_result_id:
                continue  # absent from the receipt, or decided in no run there: compared as it is
            kind, out.shadow_budget = cut_h[cid]
            result_ids.add(rcr.formal_result_id)
            adds.append(_cut_tuple(shadow_by[cid].claim_ids, rid, statements, kind))
            out.shadow_cut.append(cid)
        if adds:
            _replay_cut(theirs, receipt.findings, result_ids, adds)
            if r_status is TransmissionStatus.ACCEPTED:
                r_status = TransmissionStatus.ACCEPTED_WITH_FINDINGS
    return out, s_status, r_status


def _structured(rc) -> dict[str, list]:
    """The receipt's structured results the shadow compares besides its findings: coverage records, constraint results
    and the outcomes' display statuses."""
    return {
        "coverage": sorted((c.item_id, c.addressed, tuple(sorted(c.addressed_by_claim_ids))) for c in rc.coverage),
        "constraint_results": sorted((c.constraint_id, c.satisfied, c.method, c.formal_status) for c in rc.constraint_results),
        "outcome display statuses": sorted((o.report_id, o.claim_id, getattr(o.display_status, "value", o.display_status)) for o in rc.outcomes),
    }


def _undecided(items, allowed=None) -> bool:
    """True when any captured run is undecided (TIMEOUT or UNKNOWN) under a configuration the channel runs under
    (``allowed``: the pinned configuration, and the same with unsat cores on; None accepts any). An undecided run under
    another configuration (a starved budget swapped in) explains nothing: it is the fault, not the environment."""
    import json
    for c in items:
        try:
            data = json.loads(c.result_json) if c.result_json else None
            if not data or data.get("status") not in _UNDECIDED:
                continue
            if allowed is not None and faithful(VerificationResult, data).solver_config not in allowed:
                continue
            return True
        except Exception:
            continue
    return False


def run_shadow(ctx: CheckContext) -> str:
    """Run the shadow channel over the view; returns the coverage state (``run``, ``skipped``)."""
    view = ctx.view
    if view.degraded or not view.transfers:
        ctx.note("shadow replay skipped: no journaled transfers")
        return "skipped"
    if any(t.digest_only for t in view.transfers):
        ctx.note("shadow replay skipped: the journal holds digest-only entries, so the inputs cannot be re-issued")
        return "skipped"
    if len(view.plans) > 1:
        ctx.note("shadow replay uses the first journaled plan; the plan changed during the task")
    from ...channel.bus import TranslatorChannel
    plan = view.plan
    first = view.transfers[0].seq
    info = view.info_at(first)
    cfg = view.config_at(first)
    allowed = [cfg, cfg.model_copy(update={"produce_unsat_core": True})]
    registry = ctx.registry
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    runs_key = ctx.keyring.subkey("runs")
    from ...channel.bus import CLAIM_OUT_OF_SCOPE
    translations: dict[tuple[str, str], list] = {}
    journaled_named: dict[tuple[str, str], list[list[str]]] = {}  # the argument diagnosis of each journaled outcome (rule composition)
    # The claims the live channel named NOT_ATTEMPTED (INT-REQ-006: its verifier produced no outcome for a material,
    # deterministically eligible claim). The shadow leaves exactly these unserved, so it names them too; every other claim
    # with no journaled outcome was outside the live verifier's scope (no verifier, or one that declared it out of scope)
    # and is declared out of scope here, so the shadow never names a claim the live channel did not. A verification that
    # RAISED stays unreproducible (its INT-REQ-006 is excluded from the comparison, SHADOW_EXCLUDED).
    unserved: set[tuple[str, str]] = set()
    for t in view.transfers:
        if t.receipt is None:
            continue
        for o in t.receipt.outcomes:
            translations.setdefault((o.report_id, o.claim_id), []).append(o.translation)
            journaled_named.setdefault((o.report_id, o.claim_id), []).append(_diagnosis_of(o))
        for f in t.receipt.findings:
            if f.code == "INT-REQ-006" and "produced no outcome: NOT_ATTEMPTED" in (f.message or ""):
                for rid in f.report_ids:
                    for cid in f.claim_ids:
                        unserved.add((rid, cid))

    def serve(claim, report, task=None):
        cands = translations.get((report.report_id, claim.claim_id), [])
        digest = sha256_text(claim.claim_text)
        tr = next((x for x in cands if x.claim_text_sha256 == digest), None) or next((x for x in cands if x.claim_text_sha256 is None), None)
        if tr is None:
            return None if (report.report_id, claim.claim_id) in unserved else CLAIM_OUT_OF_SCOPE
        ver: Optional[VerificationResult] = None
        if tr.problem is not None and tr.status in (TranslationStatus.TRANSLATED, TranslationStatus.AMBIGUOUS_TRANSLATION):
            # as translate.outcome.verify_claim runs it: on an ambiguous translation the argument diagnosis is capped at
            # info on the assumed reading (capped_from keeps the uncapped severity)
            cap = ("info", "ambiguous_translation") if tr.status is TranslationStatus.AMBIGUOUS_TRANSLATION else None
            ver = verify(tr.problem, cfg, signing_key=runs_key, key_id=RUN_KEY_ID, severity_cap=cap)
        # Rule composition (round-8 clearance c1, handoff fixer): the outcome is composed as the live verifier composed it. A
        # verifier that composes without the report and the task record (a hand-built fixture) is reproduced first, as before; a
        # production verifier (translate.outcome.verify_claim) composes with the report it verifies and the task record the
        # channel passes, and its argument diagnosis reads them (EVD-AUTH-001: "as the data show" is attributed when a text was
        # supplied). The composition whose argument diagnosis is the journaled outcome's is the one served; with neither, the
        # first, so a tampered diagnosis is still compared against a composition the auditor makes itself. The genuine c1 p8a
        # channel failed its audit on this alone (OVS-RCPT-004, INT-ARG-001 EVD-AUTH-001 on g1.2@economics-specialist).
        bare = compose_outcome(claim, tr, ver, signing_key=runs_key, key_id=RUN_KEY_ID)
        recorded = journaled_named.get((report.report_id, claim.claim_id), [])
        if recorded and _diagnosis_of(bare) not in recorded:
            produced = compose_outcome(claim, tr, ver, signing_key=runs_key, key_id=RUN_KEY_ID, report=report, task=task)
            if _diagnosis_of(produced) in recorded:
                return produced
        return bare

    shadow = TranslatorChannel(plan, signing_key=runs_key, key_id=RUN_KEY_ID, verify_claim_fn=serve, config=cfg, registry=registry)
    hook = bool(info.get("formalize_synthesis_hook"))
    if hook:
        ctx.note("shadow replay: synthesis transfers not comparable (the channel had a synthesis-formalization hook)")
    mid_map: dict[str, str] = {}

    def m(x: Optional[str]) -> Optional[str]:
        return mid_map.get(x, x) if x else x

    for i, t in enumerate(view.transfers):
        if t.receipt is None or t.payload is None:
            continue
        prev = view.transfers[i - 1] if i else None  # the journaled transfer before this one: rule budget-cut's timing bound
        call = t.call
        try:
            with capture_results() as cap:
                if t.kind == "request":
                    req = t.request
                    items = [faithful(RequestItem, i) for i in call["items"]] if call.get("items") is not None else None
                    cons = [faithful(Constraint, c) for c in call["constraints"]] if call.get("constraints") is not None else None
                    msg, _req, rc = shadow.request(req.from_agent_id, req.to_agent_id, req.user_input, list(req.supplied_texts), items=items, constraints=cons)
                elif t.kind == "response_text" and t.withheld is not None:
                    texts = [faithful(SuppliedText, s) for s in call["supplied_texts"]] if call.get("supplied_texts") is not None else None
                    msg, rc = shadow.respond_text(m(call.get("request_message_id")), t.raw_text or "", agent_id=call.get("agent_id") or t.withheld.get("agent_id"),
                                                  report_id=call.get("report_id") or t.withheld.get("report_id"), supplied_texts=texts, agent_version=call.get("agent_version"))
                elif t.kind in ("response", "response_text"):
                    report = faithful(SpecialistReport, t.payload)
                    sender = call.get("sender_agent_id") if t.kind == "response" else call.get("agent_id")
                    msg, rc = shadow.respond(m(call.get("request_message_id") or t.in_reply_to), report, sender_agent_id=sender)
                elif t.kind in ("relay_forward", "relay_report", "relay_synthesis"):
                    obj: Any = faithful(Synthesis, t.payload) if t.kind == "relay_synthesis" else faithful(SpecialistReport, t.payload)
                    msg, rc = shadow.relay(call.get("from_agent_id"), AgentRole(call.get("from_role")), call.get("to_agent_id"), AgentRole(call.get("to_role")), obj,
                                           in_reply_to=m(call.get("in_reply_to")))
                else:
                    continue
        except Exception as exc:
            ctx.note(f"shadow replay of transfer {t.seq} ({t.kind}) could not be re-issued ({type(exc).__name__}); later transfers are compared against a partial shadow")
            continue
        if t.message_id and rc is not None:
            mid_map[t.message_id] = rc.message_id
        if t.kind == "relay_synthesis" and hook:
            continue
        undecided = _undecided(t.event.captured, allowed) or _undecided(cap.items, allowed)
        ours, theirs = _tuples(rc.findings), _tuples(t.receipt.findings)
        ids = t.ids()
        # rule budget-cut: the checks a STEM check budget left undecided are compared as the channel states them, on both sides
        cut, shadow_status, receipt_status = _budget_cuts(ctx, t, prev, rc, ours, theirs)
        if cut.refused:
            ctx.note(f"shadow replay (rule budget-cut): {t.kind} {t.message_id} states {cut.refused_checks} STEM check(s) not run under its STEM check budget, but "
                     f"{cut.refused}: that is not the channel's budget rule, so the shadow compares those checks as it decides them")
        if cut.receipt_cut:
            what = (f"{t.kind} {t.message_id} left {len(cut.receipt_cut)} STEM check(s) undecided under a STEM check budget of {cut.budget} s"
                    f" ({', '.join(cut.receipt_cut[:4])}{', ...' if len(cut.receipt_cut) > 4 else ''}){cut.timing}")
            if cut.unexplained:
                ctx.ovs(t.seq, "OVS-RES-008", f"{what}; that budget is below the module's {_MODULE_BUDGET_S:g} s and {cut.unexplained}, and the journal does not record a "
                        "channel's budget, so a budget starved between transfers cannot be told from one a deadline set: the shadow compares those checks as "
                        "not run, as the receipt states them, and vouches for nothing about them (rule budget-cut)", **ids)
            else:
                ctx.note(f"shadow replay (rule budget-cut): {what}; no replay reproduces where a clock ran out, so the shadow compared those checks as not "
                         "run, as the receipt states them, and everything else as it decides it")
        if cut.shadow_cut:
            ctx.ovs(t.seq, "OVS-RES-008", f"the shadow channel's own STEM check budget ({cut.shadow_budget} s) left {len(cut.shadow_cut)} check(s) of {t.kind} {t.message_id} "
                    f"undecided that its receipt decided ({', '.join(cut.shadow_cut[:4])}{', ...' if len(cut.shadow_cut) > 4 else ''}): the auditor's environment, so "
                    "those checks are not compared (rule budget-cut)", **ids)
        # every finding the shadow raises more often than the receipt (an error or a warning: a deleted warning hides as much
        # from the router as a deleted error), and every receipt finding the shadow raises less often
        missing = [(k, ours[k] - theirs.get(k, 0)) for k in ours if ours[k] > theirs.get(k, 0) and k[1] in ("error", "warning")]
        extra = [k for k in theirs if theirs[k] > ours.get(k, 0)]
        status_differs = shadow_status is not receipt_status
        mine, journaled = _structured(rc), _structured(t.receipt)
        fields = [name for name in mine if mine[name] != journaled[name]]
        if undecided and (missing or extra or status_differs or fields):
            ctx.ovs(t.seq, "OVS-RES-008", f"the shadow channel's receipt for {t.kind} {t.message_id} differs ({'status ' + rc.status.value + ' vs ' + t.receipt.status.value + '; ' if status_differs else ''}"
                    f"codes {sorted({k[0] for k, _n in missing} | {k[0] for k in extra})}{'; ' + ', '.join(fields) if fields else ''}) and an undecided engine run under the channel's "
                    "configuration explains it", **ids)
            continue
        for k, n in missing:
            ctx.ovs(t.seq, "OVS-RCPT-004", f"re-derived on the journaled inputs, {t.kind} {t.message_id} raises {k[0]} ({k[1]}) for claims {list(k[2])}"
                    + (f" {ours[k]} times, where its receipt carries it {theirs.get(k, 0)} times" if ours[k] > 1 or theirs.get(k, 0) else ", which its receipt lacks"),
                    claim_ids=list(k[2]), message_ids=ids["message_ids"], report_ids=ids["report_ids"] + list(k[3]), agent_ids=ids["agent_ids"])
        for k in extra:
            ctx.ovs(t.seq, "OVS-RCPT-005", f"receipt {t.receipt_id} carries {k[0]} ({k[1]}) for claims {list(k[2])}, which the shadow channel does not reproduce on the journaled inputs",
                    claim_ids=list(k[2]), message_ids=ids["message_ids"], report_ids=ids["report_ids"] + list(k[3]), agent_ids=ids["agent_ids"])
        if status_differs:
            ctx.ovs(t.seq, "OVS-RCPT-008", f"the shadow channel fed the journaled inputs issues {rc.status.value} for {t.kind} {t.message_id}, whose receipt states {t.receipt.status.value}", **ids)
        if fields:
            ctx.ovs(t.seq, "OVS-RCPT-008", f"the shadow channel fed the journaled inputs issues other {', '.join(fields)} for {t.kind} {t.message_id} than its receipt states", **ids)
    return "run"
