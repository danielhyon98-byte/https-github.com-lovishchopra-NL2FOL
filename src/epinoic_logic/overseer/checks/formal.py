"""L4 formal checks and R2 re-derivation: does the receipt report each engine verdict as the signed result has it,
and is each checked problem the one the payload yields?

L4 (live, from the receipt and the stored result):

* FORM-001: ``formal_status`` on a constraint result or a branch formal check equals the stored result's status.
* FORM-002: ``satisfied`` is the image of the stored status. Constraints: ENTAILED gives true, COUNTEREXAMPLE false,
  anything else null. Branch checks (rule ``branch-image/2``, STEM readiness: the channel's own mapping, read from the
  check the branch pack re-derives in R2): ``status == expected_if_sound`` gives true (a satisfiability check may expect
  SATISFIABLE or UNSATISFIABLE, a Boolean identity's success is UNSATISFIABLE); any other definitive status gives false,
  except INCONSISTENT_PREMISES on a check that declares ``inconsistent_is_failure`` false (the STEM checks: undecided,
  null); anything else null. A run carrying the vacuity diagnostic E108 with ``status == expected_if_sound`` may be
  written true or null (a channel that withholds a vacuous verdict writes null; one that does not, true; neither shows
  a failure as success). A check that declares neither field is a pre-STEM check (``inconsistent_is_failure`` true).
  ``expected_if_sound`` and the declarations come from R2; until R2 has run, only a status whose image is the same
  under every expectation a pack sets (ENTAILED, SATISFIABLE, UNSATISFIABLE) is checked: an undecided status (null)
  and COUNTEREXAMPLE (false). The rest waits for R2 (the transfer is pending until R2 has run).
* Rule ``failure-severity`` (with R2): a branch check written ``satisfied`` false needs its failure finding naming its
  result: INT-SUBJ-001 (error), or INT-SUBJ-004 (warning) for a check whose pack declares ``failure_severity`` warning
  (the STEM checks that fail only under a reading the report did not state). The live receipt check accepts either;
  R2 requires INT-SUBJ-001 at error for every check the pack declares at error (RCPT-004 otherwise).

R2 (deterministic code on journaled data; nothing in agent text is executed):

* the branch packs are re-run on the journaled report and request text (``branch.run_packs``); every error-level
  STRUCTURAL finding they give (after the channel's covered / form-covered suppression, read from the receipt's
  INT-REQ-003 and INT-REQ-010 findings) must be on the receipt with its INT-SUBJ-003, else RCPT-004; each pack check's
  problem digest is compared with the stored problem behind the receipt's formal check of the same id (pack ids are
  deterministic); a pack check absent from the receipt is FORM-004, a digest mismatch FORM-003;
* request word and paragraph bounds are recounted from the journaled ``original_response`` with the channel's own
  counters (``count_answer_words``, ``count_paragraphs``) and compared with the stored constraint problem: the
  MEASURED premise's value and the BOUND conclusion's operator and value (the problem id, which carries a random
  suffix, is not compared). A mismatch is FORM-003; a bound with no formal constraint result is FORM-004;
* the signed status of each bound's result is compared with the recount by integer arithmetic (the problem
  ``n = measured`` entails ``n <op> bound`` exactly when the comparison holds): a definitive status the arithmetic
  contradicts is RES-007, decided without the stored problem, so a re-signed status is exposed in R2 (the transfer is
  pending until R2 has run) rather than only by a sampled replay; an undecided status on a bound the arithmetic shows
  violated is RES-007 too (rule ``decidable-bound``, review round 3: a starved budget never turns a violated limit into
  an unchecked one);
* the problem a pack check or a constraint result was decided on is read from the store or, once the store has evicted
  it, from the journaled capture of its event (``_held_problem``); with neither, OVS-AUDIT-005, never a silent skip.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ...channel.request_parser import count_answer_words, count_paragraphs
from ...engine.statuses import VerificationStatus as S, is_definitive
from ...ir.canonical import problem_digest
from ..view import Transfer
from . import CheckContext, Rederived

__all__ = ["check_formal_status", "rederive", "check_branch_satisfied", "constraint_problem_mismatch", "R2_KINDS", "branch_image", "live_branch_image",
           "check_rules_of"]

#: Transfers whose receipts carry pack checks and constraint results (delivered reports).
R2_KINDS = ("response", "response_text", "relay_report")
_BOUND_OPS = {"max_words": "le", "min_words": "ge", "max_paragraphs": "le", "min_paragraphs": "ge"}


def _constraint_image(status: str) -> Optional[bool]:
    return True if status == S.ENTAILED.value else False if status == S.COUNTEREXAMPLE.value else None


def _definitive(status: Optional[str]) -> bool:
    try:
        return is_definitive(S(status))
    except ValueError:
        return False


def live_branch_image(status: Optional[str]) -> Optional[frozenset]:
    """Rule ``branch-image/2`` before R2: the ``satisfied`` values a branch check with this signed status may carry under
    EVERY expectation a pack sets (ENTAILED, SATISFIABLE, UNSATISFIABLE), or None when the image depends on the check
    (its expectation, ``inconsistent_is_failure``, the vacuity of its run) and waits for R2. An undecided status is never
    satisfied; COUNTEREXAMPLE is a failure under every expectation."""
    if not _definitive(status):
        return frozenset({None})
    if status == S.COUNTEREXAMPLE.value:
        return frozenset({False})
    return None


def branch_image(status: Optional[str], expected_if_sound: str, *, inconsistent_is_failure: bool = True, vacuous: Optional[bool] = False) -> frozenset:
    """Rule ``branch-image/2``: the ``satisfied`` values the channel may write for a branch check whose signed run has
    ``status``, given what the branch pack declares for the check (module docstring). ``vacuous``: the run carries E108
    (None when the run's diagnostics are not held: read as possibly vacuous, so a null is not accused)."""
    if status == expected_if_sound:
        return frozenset({True}) if vacuous is False else frozenset({True, None})
    if _definitive(status) and not (status == S.INCONSISTENT_PREMISES.value and not inconsistent_is_failure):
        return frozenset({False})
    return frozenset({None})


def _shown(accepted: frozenset) -> str:
    return " or ".join(str(v) for v in sorted(accepted, key=lambda v: {True: 0, False: 1, None: 2}[v]))


def check_rules_of(fc: Any) -> dict[str, Any]:
    """What a re-derived branch check declares for its decision (rule ``branch-image/2``): ``inconsistent_is_failure`` and
    ``failure_severity`` as the pack sets them; a check that declares neither (every pre-STEM check) counts
    INCONSISTENT_PREMISES as a failure at severity error."""
    return {"inconsistent_is_failure": getattr(fc, "inconsistent_is_failure", True) is not False,
            "failure_severity": "warning" if getattr(fc, "failure_severity", "error") == "warning" else "error"}


def _vacuous(ctx: CheckContext, rid: str) -> Optional[bool]:
    """Whether the signed run ``rid`` carries the vacuity diagnostic E108: from the stored result, else its journaled
    capture; None when neither holds it."""
    res = ctx.store.parsed(rid)
    if res is not None:
        return any(d.code == "E108" for d in res.diagnostics)
    from .results import journaled_capture
    jc = journaled_capture(ctx.view, rid)
    if jc is None:
        return None
    try:
        data = json.loads(jc[1].result_json)
        return any(isinstance(d, dict) and d.get("code") == "E108" for d in (data.get("diagnostics") or []))
    except Exception:
        return None


def _branch_form002(ctx: CheckContext, t: Transfer, c: Any, status: str, exp: Optional[str], accepted: frozenset) -> None:
    ctx.ovs(t.seq, "OVS-FORM-002", f"formal check {c.constraint_id} states satisfied={c.satisfied} but the signed status {status}"
            + (f" with expected_if_sound {exp}" if exp else "") + f" gives {_shown(accepted)}", formal_result_id=c.formal_result_id, **t.ids())


def _accepted_for(ctx: CheckContext, red: Optional[Rederived], c: Any, status: str) -> tuple[Optional[str], Optional[frozenset]]:
    """(expectation, accepted ``satisfied`` values) for a branch check: R2's when it re-derived the check, else the live
    rule's (None: waits for R2)."""
    live = live_branch_image(status)
    if live is not None:
        return (red.expected_if_sound.get(c.constraint_id) if red is not None else None), live
    if red is None or c.constraint_id not in red.expected_if_sound:
        return None, None
    exp = red.expected_if_sound[c.constraint_id]
    rules = red.check_rules.get(c.constraint_id) or {}
    vac = _vacuous(ctx, c.formal_result_id) if status == exp else False
    return exp, branch_image(status, exp, inconsistent_is_failure=rules.get("inconsistent_is_failure", True), vacuous=vac)


def check_formal_status(ctx: CheckContext, t: Transfer) -> None:
    """FORM-001 and FORM-002 (constraints, and the branch checks whose status alone decides)."""
    rc = t.receipt
    if rc is None:
        return
    ids = t.ids()
    for coll, label in ((rc.constraint_results, "constraint"), (rc.formal_checks, "formal check")):
        for c in coll:
            if c.method != "formal" or not c.formal_result_id:
                continue
            stored = ctx.store.get(c.formal_result_id)
            if stored is None:
                continue  # unresolved ids are decided by L3
            status = stored.status
            if c.formal_status != status:
                ctx.ovs(t.seq, "OVS-FORM-001", f"{label} {c.constraint_id} states formal_status {c.formal_status} but its signed result {c.formal_result_id} has {status}",
                        formal_result_id=c.formal_result_id, **ids)
            if label == "constraint":
                img = _constraint_image(status)
                if c.satisfied is not img:
                    ctx.ovs(t.seq, "OVS-FORM-002", f"constraint {c.constraint_id} states satisfied={c.satisfied} but the signed status {status} gives {img}",
                            formal_result_id=c.formal_result_id, **ids)
            else:
                exp, accepted = _accepted_for(ctx, ctx.rederived.get(t.seq), c, status)
                if accepted is not None and c.satisfied not in accepted:
                    _branch_form002(ctx, t, c, status, exp, accepted)


def check_branch_satisfied(ctx: CheckContext, t: Transfer) -> None:
    """FORM-002 for branch checks once R2 has supplied ``expected_if_sound`` and the check's declarations (rule
    ``branch-image/2``; run after :func:`rederive`), and rule ``failure-severity``."""
    rc = t.receipt
    red = ctx.rederived.get(t.seq)
    if rc is None or red is None:
        return
    for c in rc.formal_checks:
        if not c.formal_result_id or c.constraint_id not in red.expected_if_sound:
            continue
        stored = ctx.store.get(c.formal_result_id)
        if stored is None:
            continue
        if live_branch_image(stored.status) is not None:
            continue  # already decided live
        exp, accepted = _accepted_for(ctx, red, c, stored.status)
        if accepted is not None and c.satisfied not in accepted:
            _branch_form002(ctx, t, c, stored.status, exp, accepted)
    # rule failure-severity: the live receipt check accepts INT-SUBJ-001 (error) or INT-SUBJ-004 (warning) for a failed
    # check; a check the pack declares at severity error needs INT-SUBJ-001 at error
    from .receipts import _present
    for c in rc.formal_checks:
        if c.method != "formal" or not c.formal_result_id or c.satisfied is not False:
            continue
        rules = red.check_rules.get(c.constraint_id)
        if rules is None or rules.get("failure_severity") != "error":
            continue
        how = _present(rc.findings, "INT-SUBJ-001", "error", formal_result_id=c.formal_result_id)
        if how and _present(rc.findings, "INT-SUBJ-004", "warning", formal_result_id=c.formal_result_id) is None:
            ctx.ovs(t.seq, "OVS-RCPT-004", f"receipt {t.receipt_id} of {t.kind} {t.message_id} implies INT-SUBJ-001 but "
                    + ("lacks it" if how == "absent" else f"carries it at severity {how}")
                    + f": formal check {c.constraint_id} is not satisfied and the branch pack declares its failure severity error (R2), so the channel "
                    "raises INT-SUBJ-001 (error) naming it; the receipt carries only INT-SUBJ-004 (warning), the severity of a check the pack declares at warning",
                    formal_result_id=c.formal_result_id, **t.ids())


def constraint_problem_mismatch(problem: dict, op: str, value: str, measured: int) -> list[str]:
    """Why a stored constraint problem is not ``measured <op> value`` (empty when it is)."""
    why = []
    try:
        prem = next(p for p in problem.get("premises", []) if p.get("id") == "MEASURED")
        right = prem["expr"]["right"]
        if prem["expr"].get("op") != "eq" or str(right.get("value")) != str(measured):
            why.append(f"MEASURED is {prem['expr'].get('op')} {right.get('value')} but the response measures {measured}")
    except (StopIteration, KeyError, TypeError, AttributeError):
        why.append("the problem has no MEASURED premise")
    try:
        concl = problem["conclusion"]
        if concl.get("id") != "BOUND":
            why.append("the conclusion is not BOUND")
        expr = concl["expr"]
        if expr.get("op") != op or str(expr["right"].get("value")) != str(value):
            why.append(f"BOUND is {expr.get('op')} {expr['right'].get('value')} but the request's bound is {op} {value}")
    except (KeyError, TypeError, AttributeError):
        why.append("the problem has no BOUND conclusion")
    return why


def _bound_status_contradicts(status: Optional[str], op: str, value: str, measured: int) -> Optional[str]:
    """Why a signed constraint status contradicts the bound re-derived from the response (None when it does not): the
    constraint problem is ``n = measured`` entails ``n <op> value``, so its only definitive statuses are ENTAILED when
    the comparison holds and COUNTEREXAMPLE when it does not. Decided by integer arithmetic, without the stored problem,
    so a status re-signed with the engine key (and emitted with or without its problem) is exposed before replay."""
    if status is None:
        return None
    try:
        bound = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    holds = measured <= bound if op == "le" else measured >= bound
    expected = S.ENTAILED.value if holds else S.COUNTEREXAMPLE.value
    if status not in (S.ENTAILED.value, S.COUNTEREXAMPLE.value):
        if holds:
            return None  # an undecided run of a bound that holds hides nothing from the router
        # rule ``decidable-bound``: integer arithmetic decides the bound, and it FAILS, so an undecided signed status
        # (a starved budget) turns a violated word or paragraph limit into an unchecked one
        return (f"the response measures {measured}, so 'n {op} {bound}' fails and the constraint problem's only status is {expected}, but the signed "
                f"result states {status}: a violated bound reported as undecided (re-derived from the journaled response by integer arithmetic, R2)")
    if status == expected:
        return None
    return (f"the response measures {measured}, so 'n {op} {bound}' {'holds' if holds else 'fails'} and the only status of the constraint problem is "
            f"{expected}, but the signed result states {status} (re-derived from the journaled response, R2)")


def _held_problem(ctx: CheckContext, rid: str) -> tuple[Optional[str], Optional[str]]:
    """(problem digest, problem JSON) of the problem result ``rid`` was decided on: from the store while it holds the
    result, else from the journaled capture of its event (the journal keeps it after the store evicted the result, so
    an eviction never turns a comparison into a silent skip). (None, None) when neither holds it."""
    from ...ir.canonical import sha256_hex
    from .results import journaled_capture
    rec = ctx.store.live(rid)
    if rec is not None and (rec.problem_digest or rec.problem_json):
        return rec.problem_digest or sha256_hex(rec.problem_json), rec.problem_json
    jc = journaled_capture(ctx.view, rid)
    if jc is not None:
        c = jc[1]
        if c.problem_digest or c.problem_json:
            return c.problem_digest or sha256_hex(c.problem_json), c.problem_json
    return None, None


def _structural_implied(rc, t: Transfer, branch_key: str, structural, ids: dict) -> list:
    """RCPT-004 for every error-level structural finding the branch packs re-derive from the journaled report that the
    receipt lacks, or whose INT-SUBJ-003 it lacks, after the channel's own suppression rules: a claim whose excerpt the
    receipt already reports (INT-REQ-003 not found, INT-REQ-010 form differs) has no CORE-SRC-001 of its own, and a claim
    covered only by INT-REQ-010 has no ``-SRC-001`` error at all (``TranslatorChannel._branch_checks``). The covered sets
    are read from the journaled receipt (a superset of the channel's, so the rule never expects more than it raises)."""
    from ..codes import ovs_finding
    covered: set[str] = set()
    not_found: set[str] = set()
    if t.kind != "relay_report":  # the relay path runs the packs with nothing covered
        for f in rc.findings:
            if f.code in ("INT-REQ-003", "INT-REQ-010"):
                covered.update(f.claim_ids)
            if f.code == "INT-REQ-003":
                not_found.update(f.claim_ids)
    form_covered = covered - not_found
    out = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for sf in structural:
        if sf.severity != "error":
            continue
        cids = tuple(sorted(sf.claim_ids))
        if covered and sf.code == "CORE-SRC-001" and sf.claim_ids and set(sf.claim_ids) <= covered:
            continue
        if form_covered and sf.code.endswith("-SRC-001") and sf.claim_ids and set(sf.claim_ids) <= form_covered:
            continue
        key = (sf.code, cids)
        if key in seen:
            continue
        seen.add(key)
        on_receipt = any(x.code == sf.code and tuple(sorted(x.claim_ids)) == cids and x.severity == "error" for x in rc.structural_findings)
        if not on_receipt:
            out.append(ovs_finding("OVS-RCPT-004", f"receipt {rc.receipt_id} of {t.kind} {t.message_id} implies the error-level structural finding {sf.code} "
                                   f"(claims {list(cids)[:6]}) but lacks it: the branch {branch_key!r} packs re-derive it from the journaled report (R2)",
                                   claim_ids=list(cids), **ids))
        if sf.code.endswith("-SRC-001") and sf.claim_ids and set(sf.claim_ids) <= covered:
            continue  # the excerpt is already an INT-REQ-003 / INT-REQ-010 finding naming the branch rule
        has_subj = any(x.code == "INT-SUBJ-003" and x.severity == "error" and tuple(sorted(x.claim_ids)) == cids and f"{sf.code}:" in x.message for x in rc.findings)
        if not has_subj:
            out.append(ovs_finding("OVS-RCPT-004", f"receipt {rc.receipt_id} of {t.kind} {t.message_id} implies INT-SUBJ-003 (error) for the structural finding "
                                   f"{sf.code} (claims {list(cids)[:6]}) but lacks it: the channel raises INT-SUBJ-003 for every error-level branch finding (R2)",
                                   claim_ids=list(cids), **ids))
    return out


def rederive(ctx: CheckContext, t: Transfer) -> Optional[Rederived]:
    """R2 for one delivered report transfer: pack checks and constraint encodings re-derived from journaled content."""
    if t.kind not in R2_KINDS or not t.delivered or t.receipt is None or t.report is None or t.digest_only:
        return None
    red = Rederived(seq=t.seq)
    rc = t.receipt
    rep = t.report
    ids = t.ids()
    from ..codes import ovs_finding
    plan = ctx.view.plan_at(t.seq)
    registry = ctx.registry
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    subject = plan.agent_subjects.get(rep.agent_id, plan.subject) if plan is not None else rep.subject
    branch = registry.for_subject(subject)[0]
    req = ctx.view.by_seq[t.request_seq].request if (t.kind != "relay_report" and t.request_seq is not None and t.request_seq in ctx.view.by_seq) else None
    request_text = req.user_input if req is not None else None
    structural, formal = branch.run_packs(rep, request_text)
    red.findings.extend(_structural_implied(rc, t, branch.key, structural, ids))
    by_id = {c.constraint_id: c for c in rc.formal_checks}
    for fc in formal:
        red.expected_if_sound[fc.check_id] = fc.expected_if_sound
        red.check_rules[fc.check_id] = check_rules_of(fc)
        held = by_id.get(fc.check_id)
        if held is None:
            red.findings.append(ovs_finding("OVS-FORM-004", f"the branch pack re-derives formal check {fc.check_id} ({fc.kind}: {fc.description[:120]}) from report {rep.report_id}, but the receipt does not carry it", **ids))
            continue
        stored = ctx.store.get(held.formal_result_id) if held.formal_result_id else None
        if stored is None:
            continue  # an unresolved result id is decided by L3
        pd, _pj = _held_problem(ctx, held.formal_result_id)
        if pd is None and ctx.view.degraded:
            continue  # a degraded view holds no capture: AUDIT-002 says so
        if pd is None:
            red.findings.append(ovs_finding("OVS-AUDIT-005", f"formal check {fc.check_id}: the problem its result {held.formal_result_id} was decided on is held neither by the "
                                            "store nor by the journaled capture, so the pack's problem cannot be compared with it (R2)", formal_result_id=held.formal_result_id, **ids))
        elif pd != problem_digest(fc.problem):
            red.findings.append(ovs_finding("OVS-FORM-003", f"formal check {fc.check_id} was decided on a problem other than the one the branch pack derives from the report",
                                            formal_result_id=held.formal_result_id, **ids))
    derived_ids = {fc.check_id for fc in formal}
    for c in rc.formal_checks:
        if c.constraint_id not in derived_ids:
            red.findings.append(ovs_finding("OVS-FORM-003", f"formal check {c.constraint_id} on the receipt is not one the branch pack derives from report {rep.report_id}",
                                            formal_result_id=c.formal_result_id, **ids))
    if req is not None:
        words, _notes = count_answer_words(rep.original_response)
        paras = count_paragraphs(rep.original_response)
        held_c = {c.constraint_id: c for c in rc.constraint_results}
        for c in req.constraints:
            if c.kind not in _BOUND_OPS or c.value is None:
                continue
            measured = words if c.kind.endswith("words") else paras
            cr = held_c.get(c.constraint_id)
            if cr is None or cr.method != "formal" or not cr.formal_result_id:
                red.findings.append(ovs_finding("OVS-FORM-004", f"request constraint {c.constraint_id} ({c.kind} {c.value}) has no formal result on the receipt", **ids))
                continue
            held_rec = ctx.store.get(cr.formal_result_id)
            wrong = _bound_status_contradicts(getattr(held_rec, "status", None), _BOUND_OPS[c.kind], c.value, measured)
            if wrong:
                red.findings.append(ovs_finding("OVS-RES-007", f"constraint {c.constraint_id}: {wrong}", formal_result_id=cr.formal_result_id, **ids))
            if held_rec is None:
                continue  # an unresolved result id is decided by L3
            _pd, pj = _held_problem(ctx, cr.formal_result_id)
            if not pj and ctx.view.degraded:
                continue  # a degraded view holds no capture: AUDIT-002 says so
            if not pj:
                red.findings.append(ovs_finding("OVS-AUDIT-005", f"constraint {c.constraint_id}: the problem its result {cr.formal_result_id} was decided on is held neither by "
                                                "the store nor by the journaled capture, so the recount cannot be compared with it (R2)", formal_result_id=cr.formal_result_id, **ids))
                continue
            why = constraint_problem_mismatch(json.loads(pj), _BOUND_OPS[c.kind], c.value, measured)
            if why:
                red.findings.append(ovs_finding("OVS-FORM-003", f"constraint {c.constraint_id} was decided on a problem the response does not yield: {why}",
                                                formal_result_id=cr.formal_result_id, **ids))
    return red
