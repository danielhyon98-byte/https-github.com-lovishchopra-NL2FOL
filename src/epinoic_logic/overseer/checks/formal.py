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

* the branch packs are re-run on the journaled report and request text (``branch.run_packs``); every STEM structural
  finding they give (rule ``stem-structural``, STEM completion: the ``ST-*`` codes, which the STEM pack emits at warning or
  info severity only, compared as a multiset of code, severity, claims and message with the receipt's, since the channel
  copies them unchanged) must be on the receipt, else RCPT-004 (an error or a warning), and one the receipt carries that
  the packs do not give is RCPT-005; each pack check the receipt carries is stated as the channel states it (rule
  ``check-statements``, STEM completion): its claims and its ``detail`` are what the channel's own statement of the check
  (``TranslatorChannel._check_claims_named``, bound at import) and its signed run give, and the finding naming its result
  (INT-SUBJ-001, INT-SUBJ-004 or INT-SUBJ-002) names those claims and carries the channel's message, the engine's
  computed and stated values (``_model_note``) taken from the signed result, else RCPT-007; every error-level
  STRUCTURAL finding they give (after the channel's covered / form-covered suppression, read from the receipt's
  INT-REQ-003 and INT-REQ-010 findings, and, by rule ``request-quotation`` (the translator merge), for the claims whose
  cited excerpt the journaled request holds, which the merged channel covers with no finding) must be on the receipt
  with its INT-SUBJ-003, else RCPT-004; each pack check's
  problem digest is compared with the stored problem behind the receipt's formal check of the same id (pack ids are
  deterministic); a pack check absent from the receipt is FORM-004, a digest mismatch FORM-003;
* rule ``identity-statement`` (STEM repair 12, decision 72): a branch check decided on an identity step, a step from the
  trivially true premise ``PREV`` (its two sides the same: a derivative, an antiderivative, a definite integral's bracket, a
  Given function against the request's, a factorisation), states a relation for every value of its variable, so its
  problem may give no symbol a value or a formula (no ``B_*`` binding and no ``FORMULA`` premise). One that does and whose
  signed status is the success its pack expects is FORM-005 (an error): the identity was decided at the value bound, so
  its result shows nothing of the identity, and a wrong one is shown holding (``d/dt (6 − 6t) = −6t`` with the request's
  ``t = 1`` bound: −6 = −6(1), ENTAILED). The rule reads the signed problem, never the pack's code, so a pack that binds
  the variable is named although the re-derivation reproduces its problem exactly (FORM-003 compares digests only);
* request word and paragraph bounds are recounted from the journaled ``original_response`` with the channel's own
  counters, as the merged channel measures them (rule ``merged-measure``): words with ``measure_answer_words`` under the
  constraint's own ``excludes`` (the working or the diagram a request sets outside the bound) and on the branch's
  word-count view when its hub hooks lend one (the STEM branches: a maths span or a code block is one word), paragraphs
  with ``count_paragraphs``; and compared with the stored constraint problem: the MEASURED premise's value and the BOUND
  conclusion's operator and value (the problem id, which carries a random suffix, is not compared). A minimum and a
  maximum stated by one span ("about 250 words", "between 300 and 400 words") are decided by the channel as ONE range
  problem when the measurement lies within both (``_formal_range``: BOUND is an ``and`` of ``ge`` and ``le``), which both
  constraints cite; R2 accepts that form for exactly that pair (rule ``range-bound``). A mismatch is FORM-003; a bound
  with no formal constraint result is FORM-004;
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
import re
from typing import Any, Optional

from collections import Counter

from ...channel.bus import _DETAIL_MAX, TranslatorChannel
from ...channel.request_parser import count_paragraphs, measure_answer_words
from ...engine.statuses import VerificationStatus as S, is_definitive
from ...ir.canonical import canonical_json, problem_digest
from ...translate.common import truncate
from ..view import Transfer
from . import CheckContext, Rederived

__all__ = ["check_formal_status", "rederive", "check_branch_satisfied", "constraint_problem_mismatch", "R2_KINDS", "branch_image", "live_branch_image",
           "check_rules_of", "identity_bindings", "identity_variables", "IDENTITY_RULE"]

#: Rule ``identity-statement`` (STEM repair 12): an identity step's problem gives no symbol a value or a formula.
IDENTITY_RULE = "identity-statement"

#: Transfers whose receipts carry pack checks and constraint results (delivered reports).
R2_KINDS = ("response", "response_text", "relay_report")
#: The channel's own statement of a branch check, bound when this module is imported (rule ``check-statements``): a
#: channel whose class is patched later states its checks with the patch, the re-derivation with the rule as shipped.
_CHANNEL_CHECK_CLAIMS = TranslatorChannel._check_claims_named
#: The claims the channel names on a failed branch check's finding (its statement's, then the claims stating values it relies
#: on: STEM repair 1), bound at import like the statement itself.
_CHANNEL_FAILURE_CLAIMS = TranslatorChannel._failure_claims
_CHANNEL_MODEL_NOTE = TranslatorChannel._model_note
#: The STEM branches' own structural codes (rule ``stem-structural``).
_STEM_CODE_PREFIX = "ST-"
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


def _range_conclusion(expr: Any, low: str, high: str) -> bool:
    """Rule ``range-bound``: ``expr`` is the merged channel's range BOUND, ``and(n >= low, n <= high)``."""
    try:
        if expr.get("op") != "and" or len(expr.get("args") or []) != 2:
            return False
        ge, le = expr["args"]
        return (ge.get("op") == "ge" and str(ge["right"].get("value")) == str(low) and ge["left"].get("op") == "var"
                and le.get("op") == "le" and str(le["right"].get("value")) == str(high) and le["left"].get("op") == "var"
                and ge["left"].get("name") == le["left"].get("name"))
    except (KeyError, TypeError, AttributeError):
        return False


def constraint_problem_mismatch(problem: dict, op: str, value: str, measured: int, *, range_bounds: Optional[tuple[str, str]] = None) -> list[str]:
    """Why a stored constraint problem is not ``measured <op> value`` (empty when it is). With ``range_bounds`` (the
    ``(low, high)`` of the minimum and maximum one span states, when the measurement lies within both) the channel's
    range problem for that pair is accepted too (rule ``range-bound``)."""
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
        if range_bounds is not None and _range_conclusion(expr, *range_bounds):
            pass
        elif expr.get("op") == "and":
            why.append(f"BOUND is a range {json.dumps(expr, sort_keys=True)[:160]} but the request's bound is {op} {value}"
                       + (f" (the span's range is {range_bounds[0]} to {range_bounds[1]})" if range_bounds else " and no span of the request states a range the response lies within"))
        elif expr.get("op") != op or str(expr["right"].get("value")) != str(value):
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


#: Rule ``identity-statement``: the variables an identity check's statement says it holds for ("for every value of t (rule derivative)", "an
#: identity, stated for every value of t, x: …"); never "the variable" or "its variable"
_IDENTITY_VARS_RE = re.compile(r"for every value of ((?:(?!the\b|its\b)[^\s,:;()]+)(?:, (?:(?!the\b|its\b)[^\s,:;()]+))*)")


def identity_variables(detail: Any) -> list[str]:
    """Rule ``identity-statement`` (STEM repair 12): the variables a branch check's statement (its ``detail``, data only) says the check
    holds for every value of, in order of first mention."""
    out: list[str] = []
    for m in _IDENTITY_VARS_RE.finditer(str(detail or "")):
        for v in m.group(1).split(", "):
            if v and v not in out:
                out.append(v)
    return out


def identity_bindings(problem_obj: Any, detail: Any) -> list[str]:
    """Rule ``identity-statement`` (STEM repair 12): the premises of a branch check's problem (IR JSON, data only) that give a value
    (a ``B_*`` binding) or a formula (a ``FORMULA`` premise) to a variable its statement ``detail`` says the check holds for every value
    of, when the problem is an identity step: a step from the trivially true premise ``PREV``, an ``eq`` whose two sides are the same
    expression (compared as canonical JSON). Such a step holds only when it holds for every value of that variable, so a binding of it
    decides the identity at one value. A symbol the identity does not quantify (a constant the answer gives a value) may be bound, and
    every other problem may bind the values it substitutes: empty for each. The variable is read from the statement's own words, the
    binding by the symbol it binds (its declaration's meaning names the report's symbol) or by its label."""
    if not isinstance(problem_obj, dict):
        return []
    premises = [p for p in problem_obj.get("premises") or [] if isinstance(p, dict)]
    prev = next((p for p in premises if p.get("id") == "PREV"), None)
    e = prev.get("expr") if prev is not None else None
    if not (isinstance(e, dict) and e.get("op") == "eq" and isinstance(e.get("left"), dict) and isinstance(e.get("right"), dict)
            and canonical_json(e["left"]) == canonical_json(e["right"])):
        return []
    names = identity_variables(detail)
    if not names:
        return []
    declared = {str(s.get("name")): str(s.get("meaning") or "") for s in problem_obj.get("symbols") or [] if isinstance(s, dict)}
    quantified = {n for n, meaning in declared.items() if any(meaning == f"the symbol '{v}' as written in the report" for v in names)}
    out: list[str] = []
    for p in premises:
        pid, label = str(p.get("id") or ""), str(p.get("label") or "")
        if pid.startswith("B_") and (pid[2:] in quantified or any(label.startswith(f"{v} = ") for v in names)):
            out.append(pid)
        elif pid.startswith("FORMULA") and any(label.startswith(f"the formula {v} = ") for v in names):
            out.append(pid)
    return out


def _identity_statement(held: Any, fc: Any, stored: Any, pj: Optional[str], ids: dict) -> list:
    """Rule ``identity-statement`` for one branch check with its held problem ``pj``: FORM-005 when the problem is an identity
    step that binds the variable its statement says it holds for every value of, and the signed status is the success the pack
    expects (a failure at the bound value is a failure for every value too, so it stands)."""
    from ..codes import ovs_finding
    if not pj:
        return []
    try:
        obj = json.loads(pj)
    except ValueError:
        return []
    # the statement the pack derives (the receipt's detail is set against it by rule check-statements)
    detail = " ".join(str(x or "") for x in (getattr(fc, "description", None), getattr(held, "detail", None)))
    bound = identity_bindings(obj, detail)
    if not bound or str(getattr(stored, "status", "")) != str(getattr(fc, "expected_if_sound", "ENTAILED")):
        return []
    labels = [str(p.get("label") or p.get("id"))[:80] for p in obj.get("premises") or [] if isinstance(p, dict) and str(p.get("id")) in bound]
    return [ovs_finding("OVS-FORM-005", f"formal check {fc.check_id} is an identity, a step from the trivially true premise that holds only when it holds "
                                        f"for every value of {', '.join(identity_variables(detail))}, but its problem gives that variable a value or a formula "
                                        f"({'; '.join(labels[:3])}), so its signed {getattr(stored, 'status', '')} was decided at that value only and shows "
                                        f"nothing of the identity (rule {IDENTITY_RULE})", claim_ids=list(getattr(held, "claim_ids", None) or getattr(fc, "claim_ids", ()) or []),
                        formal_result_id=held.formal_result_id, **ids)]


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


def request_quoted_claims(rep: Any, req: Any) -> set[str]:
    """Rule ``request-quotation`` (the translator merge): the claims of ``rep`` with a cited excerpt that its document does
    not hold but the journaled request does (a phrase of the question, a true/false statement), which the merged channel
    counts as covered by the request with no finding and no branch ``-SRC-001`` error (``TranslatorChannel.
    _source_findings``: a quotation of the request is no invented quotation). Re-derived with the channel's own source
    check (``translate.grounding.check_claim_sources``) and locator (``channel.bus._located``) on the texts the channel
    checks against (the request's, else the report's)."""
    if req is None or not (getattr(req, "user_input", None) or "").strip():
        return set()
    from ...channel.bus import _located
    from ...translate.grounding import check_claim_sources
    supplied = list(req.supplied_texts) or list(rep.supplied_texts)
    out: set[str] = set()
    for c in rep.claims:
        for ref, g in zip(c.source_refs, check_claim_sources(c, supplied)):
            if g.verified is False and (ref.excerpt or "").strip() and g.method != "locator_exists" and _located(ref.excerpt or "", req.user_input):
                out.add(c.claim_id)
    return out


def _structural_implied(rc, t: Transfer, branch_key: str, structural, ids: dict, request_quoted: frozenset = frozenset()) -> list:
    """RCPT-004 for every error-level structural finding the branch packs re-derive from the journaled report that the
    receipt lacks, or whose INT-SUBJ-003 it lacks, after the channel's own suppression rules: a claim whose excerpt the
    receipt already reports (INT-REQ-003 not found, INT-REQ-010 form differs) has no CORE-SRC-001 of its own, and a claim
    covered only by INT-REQ-010 has no ``-SRC-001`` error at all (``TranslatorChannel._branch_checks``). The covered sets
    are read from the journaled receipt (a superset of the channel's, so the rule never expects more than it raises),
    with the claims the request's own words cover (``request_quoted``, rule ``request-quotation``: covered and
    form-covered, as the merged channel counts them, with no finding to read)."""
    from ..codes import ovs_finding
    covered: set[str] = set()
    not_found: set[str] = set()
    if t.kind != "relay_report":  # the relay path runs the packs with nothing covered
        for f in rc.findings:
            if f.code in ("INT-REQ-003", "INT-REQ-010"):
                covered.update(f.claim_ids)
            if f.code == "INT-REQ-003":
                not_found.update(f.claim_ids)
        covered |= set(request_quoted)
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


def _st_key(sf: Any) -> tuple:
    return (sf.code, sf.severity, tuple(sorted(sf.claim_ids)), sf.message)


def _stem_structural(rc, t: Transfer, branch_key: str, structural, ids: dict) -> list:
    """Rule ``stem-structural`` (STEM completion, decision 60): the ``ST-*`` structural findings the branch packs re-derive
    from the journaled report against the receipt's, as multisets of (code, severity, claims, message). The STEM pack emits
    them at warning or info severity only, so the error-level rule (:func:`_structural_implied`) never reads them, and the
    shadow compares integrity findings only: a dropped ST warning (a dimension error, a relation left unchecked) otherwise
    left the receipt the image of its own contents. The channel copies the packs' ST findings to the receipt unchanged (its
    covered and refuted filters apply to source codes only), so the multisets are equal on every genuine receipt."""
    from ..codes import ovs_finding
    want = Counter(_st_key(sf) for sf in structural if sf.code.startswith(_STEM_CODE_PREFIX))
    have = Counter(_st_key(sf) for sf in rc.structural_findings if sf.code.startswith(_STEM_CODE_PREFIX))
    out = []
    for k, n in want.items():
        if have.get(k, 0) < n and k[1] in ("error", "warning"):
            got = have.get(k, 0)
            out.append(ovs_finding("OVS-RCPT-004", f"receipt {rc.receipt_id} of {t.kind} {t.message_id} implies the {k[1]} structural finding {k[0]} (claims {list(k[2])[:6]}) "
                                   + ("but lacks it" if not got else f"{n} times but carries it {got} times")
                                   + f": the branch {branch_key!r} packs re-derive it from the journaled report (R2, rule stem-structural)",
                                   claim_ids=list(k[2]), **ids))
    for k, n in have.items():
        if want.get(k, 0) < n:
            out.append(ovs_finding("OVS-RCPT-005", f"receipt {rc.receipt_id} of {t.kind} {t.message_id} carries the {k[1]} structural finding {k[0]} (claims {list(k[2])[:6]}), "
                                   f"which the branch {branch_key!r} packs do not re-derive from the journaled report (R2, rule stem-structural)",
                                   claim_ids=list(k[2]), **ids))
    return out


def _first_difference(a: str, b: str) -> str:
    i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    return f"first difference at character {i}: {a[max(0, i - 30):i + 50]!r} vs {b[max(0, i - 30):i + 50]!r}"


def _check_statement(ctx: CheckContext, t: Transfer, rc, rep, fc: Any, held: Any, ids: dict) -> list:
    """Rule ``check-statements`` (STEM completion, decision 60) for one branch check the receipt carries with a signed run:
    the check's claims and ``detail``, and the message and claims of the finding naming its result, are what the channel
    states for that check and that run (``TranslatorChannel._decide_branch_check``: the claims holding the statement, the
    clause quoted, the pack's description, the solver status; for a failure the engine's computed and stated values from
    the result's counterexample). A detail that says ENTAILED for a COUNTEREXAMPLE, a check moved to another claim, or a
    failure finding whose values were rewritten is RCPT-007: the receipt states something its structured fields and the
    signed result do not support."""
    from ..codes import ovs_finding
    res = ctx.store.parsed(held.formal_result_id)
    if res is None:
        return []
    cids, where, quoted = _CHANNEL_CHECK_CLAIMS(fc, rep)
    status = getattr(res.status, "value", res.status)
    vacuous = any(d.code == "E108" for d in res.diagnostics)
    detail = truncate(f"{fc.kind}{where}: {quoted}{fc.description}; solver {status}" + (" (vacuous: E108)" if vacuous else ""), _DETAIL_MAX)
    why: list[str] = []
    if list(held.claim_ids) != list(cids):
        why.append(f"it names claims {list(held.claim_ids)[:6]} where the check's statement is in {list(cids)[:6]}")
    if held.detail != detail:
        why.append("its detail is not the channel's statement of the check and its signed run (" + _first_difference(held.detail or "", detail) + ")")
    model = _CHANNEL_MODEL_NOTE(fc, res)
    undecided = status + ("; vacuous: E108" if vacuous else "") + ("; inconsistent premises are undecided for this check" if status == S.INCONSISTENT_PREMISES.value else "")
    expected = {
        "INT-SUBJ-001": f"the report's own {fc.kind} statement{where} does not hold{model}: {quoted}{fc.description}",
        "INT-SUBJ-004": (f"the report's own {fc.kind} statement{where} does not hold under a reading the report did not state (a warning, not an error){model}: "
                         f"{quoted}{fc.description}"),
        "INT-SUBJ-002": f"{fc.kind} check{where} undecided ({undecided}): {quoted}{fc.description}",
    }
    failure_cids = _CHANNEL_FAILURE_CLAIMS(fc, list(cids), rep) if cids else list(cids)
    for f in rc.findings:
        if f.formal_result_id != held.formal_result_id or f.code not in expected:
            continue
        want = failure_cids if f.code in ("INT-SUBJ-001", "INT-SUBJ-004") else list(cids)
        if list(f.claim_ids) != list(want):
            if want == list(cids):
                why.append(f"its {f.code} names claims {list(f.claim_ids)[:6]} where the check's statement is in {list(cids)[:6]}")
            else:
                why.append(f"its {f.code} names claims {list(f.claim_ids)[:6]} where the check's statement is in {list(cids)[:6]} and the values it "
                           f"relies on are stated in {[c for c in want if c not in cids][:6]}")
        if f.message != expected[f.code]:
            why.append(f"its {f.code} message is not the channel's statement of the check and its signed run (" + _first_difference(f.message, expected[f.code]) + ")")
    if not why:
        return []
    return [ovs_finding("OVS-RCPT-007", f"receipt {rc.receipt_id} of {t.kind} {t.message_id}, formal check {fc.check_id}: " + "; ".join(why)
                        + " (R2, rule check-statements)", formal_result_id=held.formal_result_id, **ids)]


def _word_view(branch: Any, profile: Any):
    """The word-count view the merged channel measures a word bound on: the branch's hub hook when it lends one (the
    STEM branches), a failing hook falling back to the text itself, as the channel's ``_hook`` does; None otherwise."""
    hooks = getattr(branch, "hub_hooks", None)
    if not hooks:
        return None
    from ...channel.bus import TranslatorChannel
    key = getattr(profile, "key", "")
    return lambda text: TranslatorChannel._hook(lambda: hooks.word_count_view(text, key), text)


def _range_pairs(constraints: list, words_for, paras: int) -> dict[str, tuple[str, str]]:
    """Rule ``range-bound``: constraint id -> ``(low, high)`` for each minimum and maximum one span states ("about 250
    words": the same ``text``) whose decimal values bound the measurement on both sides, as the merged channel pairs them
    for ``_formal_range``."""
    out: dict[str, tuple[str, str]] = {}
    for unit in ("words", "paragraphs"):
        spans: dict[str, dict[str, Any]] = {}
        for c in constraints:
            if c.kind in (f"min_{unit}", f"max_{unit}") and c.value is not None:
                spans.setdefault(c.text, {})[c.kind[:3]] = c
        for pair in spans.values():
            if "min" not in pair or "max" not in pair or not (str(pair["min"].value).isdecimal() and str(pair["max"].value).isdecimal()):
                continue
            measured = words_for(next(iter(pair.values()))) if unit == "words" else paras
            if int(pair["min"].value) <= measured <= int(pair["max"].value):
                for c in pair.values():
                    out[c.constraint_id] = (str(pair["min"].value), str(pair["max"].value))
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
    branch, profile = registry.for_subject(subject)
    req = ctx.view.by_seq[t.request_seq].request if (t.kind != "relay_report" and t.request_seq is not None and t.request_seq in ctx.view.by_seq) else None
    request_text = req.user_input if req is not None else None
    structural, formal = branch.run_packs(rep, request_text)
    red.findings.extend(_structural_implied(rc, t, branch.key, structural, ids, frozenset(request_quoted_claims(rep, req))))
    red.findings.extend(_stem_structural(rc, t, branch.key, structural, ids))
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
        red.findings.extend(_check_statement(ctx, t, rc, rep, fc, held, ids))
        pd, _pj = _held_problem(ctx, held.formal_result_id)
        if pd is None and ctx.view.degraded:
            continue  # a degraded view holds no capture: AUDIT-002 says so
        if pd is None:
            red.findings.append(ovs_finding("OVS-AUDIT-005", f"formal check {fc.check_id}: the problem its result {held.formal_result_id} was decided on is held neither by the "
                                            "store nor by the journaled capture, so the pack's problem cannot be compared with it (R2)", formal_result_id=held.formal_result_id, **ids))
        elif pd != problem_digest(fc.problem):
            red.findings.append(ovs_finding("OVS-FORM-003", f"formal check {fc.check_id} was decided on a problem other than the one the branch pack derives from the report",
                                            formal_result_id=held.formal_result_id, **ids))
        red.findings.extend(_identity_statement(held, fc, stored, _pj, ids))
    derived_ids = {fc.check_id for fc in formal}
    for c in rc.formal_checks:
        if c.constraint_id not in derived_ids:
            red.findings.append(ovs_finding("OVS-FORM-003", f"formal check {c.constraint_id} on the receipt is not one the branch pack derives from report {rep.report_id}",
                                            formal_result_id=c.formal_result_id, **ids))
    if req is not None:
        view = _word_view(branch, profile)
        measures: dict[tuple[str, ...], int] = {}

        def words_for(c: Any) -> int:
            key = tuple(sorted(getattr(c, "excludes", None) or ()))
            if key not in measures:
                measures[key] = measure_answer_words(rep.original_response, excludes=key, view=view)[0]
            return measures[key]
        paras = count_paragraphs(rep.original_response)
        ranges = _range_pairs(req.constraints, words_for, paras)
        held_c = {c.constraint_id: c for c in rc.constraint_results}
        for c in req.constraints:
            if c.kind not in _BOUND_OPS or c.value is None:
                continue
            measured = words_for(c) if c.kind.endswith("words") else paras
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
            why = constraint_problem_mismatch(json.loads(pj), _BOUND_OPS[c.kind], c.value, measured, range_bounds=ranges.get(c.constraint_id))
            if why:
                red.findings.append(ovs_finding("OVS-FORM-003", f"constraint {c.constraint_id} was decided on a problem the response does not yield: {why}",
                                                formal_result_id=cr.formal_result_id, **ids))
    return red
