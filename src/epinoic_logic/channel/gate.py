"""The response gate (E2E B13): what the student is shown for one request, decided from the channel's receipts alone.

``assess_response(receipts, synthesis_receipt=None, *, synthesis_required, threshold=0.90) -> ResponseGate``

The gate reads the receipts of the transmissions an answer rests on (the specialist reports' arrivals, a relayed peer
report, the request itself) and, when the plan routes the answer through a combinator (``synthesis_required``), the
receipt of the combinator's synthesis. It never re-runs a check and never trusts an agent's word: it classifies every
check the receipts carry as **passed**, **failed**, **unresolved** or **not required** by the rules below, and decides:

* ``VERIFIED`` (label "verified"): every required check passed, at least one of them a formal one (a claim the engine
  verified, or a branch formal check of the report's own statement).
* ``DELIVERED_UNVERIFIED`` (label "not verified", never "checked" or "verified"): otherwise, when some answer was
  delivered and its accuracy, passed / (passed + failed), is above ``threshold``. Unresolved checks stay unresolved: they
  are neither passed nor failed, and they keep the answer from being VERIFIED.
* ``WITHHELD``: otherwise (nothing delivered, or the accuracy at or below the threshold).

CHECK RULES (``GateCheck.rule`` names the one that decided):

* ``delivery``: a receipt REJECTED is failed (nothing of it was delivered), else passed.
* ``constraint``: a request constraint satisfied (a signed engine result on a measured count, or the deterministic citing
  check) is passed, one not satisfied is failed, one not checkable on its scope is unresolved.
* ``coverage``: an addressed request item is passed; an unaddressed one is unresolved (the coverage reading is a heuristic,
  INT-REQ-004, and never fails an answer), or not required when the request listed it as an instruction on form only.
* ``branch_check``: a branch formal check of the report's own statement that holds is passed; one that fails is failed,
  except when it fails only under a reading the report did not state (INT-SUBJ-004, a warning) or when its claim's two
  encodings disagree (INT-XENC-001): then it is unresolved, as is an undecided check.
* ``claim``: a claim displayed COUNTEREXAMPLE, INCONSISTENT_PREMISES or UNSATISFIABLE is failed; NOT_ELIGIBLE,
  AMBIGUOUS_TRANSLATION, UNSUPPORTED, INVALID_FORMALIZATION and every engine non-result are unresolved (the gate cannot
  tell a claim that needs no check from one whose check lies with an evaluator it does not read, such as the evidence
  service or a subject evaluator a NOT_ELIGIBLE claim is routed to, so a claim without a verdict is never passed and
  never set aside as not required). A positive
  display (ENTAILED, CONSISTENT, SATISFIABLE) is passed only when its engine result rests on no ungrounded or unverified
  premise, no named diagnostic of the claim is a warning or an error by effective severity (a capped warning is still a
  warning: ``named.effective_severity``), its release is not refused and its two encodings do not disagree; otherwise
  it is unresolved; so is one that a warning or error diagnosis of the receipt itself names (a report-level rule, or a
  finding's named diagnostic). A claim of an INT-XENC-001 finding is unresolved whatever its display.
* ``finding``: an error the engine established (it carries a ``formal_result_id``) or a deterministic source-integrity
  error is failed, as is any other error a check decided; heuristic findings (INT-REQ-004, every ``*-STR-*`` code,
  CORE-QNT-001, INT-GLOSSARY-005, INT-XENC-001), argument diagnoses (INT-ARG-001), checks that did not run
  (INT-INTERNAL-*) and every warning are unresolved, never failed; info findings are no checks. A finding that restates a
  check already classified (INT-REQ-004 and INT-REQ-005 of a coverage or constraint record, INT-SUBJ-001/002/004 of a
  branch check, INT-SUBJ-003 of a subject finding, INT-HIST-001 carried from a receipt the gate also reads) is not
  counted twice. A finding carried from an earlier receipt the gate does not read (INT-HIST-001) is classified as the
  finding it carries.
* ``synthesis``: with ``synthesis_required``, a missing or REJECTED synthesis receipt is failed and a delivered one is read
  like every other receipt; without it (the fast path) no synthesis is required and a synthesis receipt given anyway is
  not read: the student is shown the reports.

``assess_response`` never raises: a receipt it cannot read, a threshold that is no number between 0 and 1 or any internal
error withholds the answer (fail closed) and says why. Its decisions obey :meth:`ResponseGate.invariants`; a decision
that would break one is withheld instead.

SCOPE. The gate decides what is shown from what the receipts say was checked. VERIFIED means that every check the
receipts carry passed; each formal result concerns only its encoding, under its premises (the engine's scope statement),
and the coverage and layout readings are heuristics. It does not establish that the answer is true.
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ..engine.statuses import SCOPE_STATEMENT, VerificationStatus as S
from ..named import is_blocking
from ..version import ARG_RULES_VERSION
from .contracts import HISTORY_CODE, TransmissionReceipt, TransmissionStatus, carried_finding, carried_subject_finding

__all__ = ["CheckResult", "GateCheck", "GateDisplay", "ResponseGate", "assess_response", "DEFAULT_THRESHOLD",
           "POSITIVE_DISPLAYS", "NEGATIVE_DISPLAYS"]

CheckResult = Literal["passed", "failed", "unresolved", "not_required"]
GateDisplay = Literal["VERIFIED", "DELIVERED_UNVERIFIED", "WITHHELD"]
GateRule = Literal["delivery", "constraint", "coverage", "branch_check", "claim", "finding", "synthesis", "gate"]

#: An answer is delivered (not verified) only above this accuracy.
DEFAULT_THRESHOLD = 0.90
#: Displays that are a positive verdict on the encoding, and displays that are a negative one.
POSITIVE_DISPLAYS = frozenset({S.ENTAILED, S.CONSISTENT, S.SATISFIABLE})
NEGATIVE_DISPLAYS = frozenset({S.COUNTEREXAMPLE, S.INCONSISTENT_PREMISES, S.UNSATISFIABLE})

#: Findings that are readings of a heuristic: unresolved at any severity, never failed.
_HEURISTIC_CODES = frozenset({"INT-REQ-004", "CORE-QNT-001", "INT-GLOSSARY-005", "INT-XENC-001"})
_HEURISTIC_RE = re.compile(r"^[A-Z]+-STR-\d{3}$")
#: Deterministic source-integrity errors: a quotation or a credited source that the supplied texts contradict.
_SOURCE_INTEGRITY = frozenset({"INT-REQ-003", "CORE-SRC-005", "INT-LEDGER-025"})
#: Findings restating a record the gate classifies itself.
_RECORD_CODES = frozenset({"INT-REQ-004", "INT-REQ-005"})
_CHECK_CODES = frozenset({"INT-SUBJ-001", "INT-SUBJ-002", "INT-SUBJ-004"})
_HISTORY = HISTORY_CODE
_XENC = "INT-XENC-001"
#: The unaddressed item an INT-REQ-004 message names ("request item i3 appears unaddressed: ...").
_ITEM_RE = re.compile(r"^request item (?P<item>\S+) appears unaddressed")
_DETAIL_MAX = 600
_RANK = {"passed": 0, "not_required": 1, "unresolved": 2, "failed": 3}


class GateCheck(BaseModel):
    """One check the gate classified: what it is, where it comes from, and the rule that decided it."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    check: str = Field(max_length=300)
    result: CheckResult
    rule: GateRule
    receipt_id: Optional[str] = None
    detail: str = Field(default="", max_length=_DETAIL_MAX)
    claim_ids: list[str] = Field(default_factory=list, max_length=64)
    code: Optional[str] = None
    display_status: Optional[str] = Field(default=None, description="for a claim check: the claim's displayed status")


class ResponseGate(BaseModel):
    """The gate's decision on one request: what is shown, with every check that decided it and the counts."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    display_status: GateDisplay
    label: str
    delivered: bool = Field(description="the answer is shown to the student (VERIFIED or DELIVERED_UNVERIFIED)")
    answer_available: bool = Field(description="some receipt the gate read was delivered: there is an answer to show")
    required: int = Field(ge=0)
    passed: int = Field(ge=0)
    failed: int = Field(ge=0)
    unresolved: int = Field(ge=0)
    not_required: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0, description="passed / (passed + failed); 0 when nothing was decided")
    threshold: float
    synthesis_required: bool
    checks: list[GateCheck] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list, description="why the answer is not VERIFIED, or why it is withheld")
    scope: str

    def invariants(self) -> dict[str, bool]:
        """What the student is shown never reads better than the checks: these hold for every decision."""
        claims = [c for c in self.checks if c.rule == "claim" and c.display_status is not None]
        counts = {r: sum(1 for c in self.checks if c.result == r) for r in _RANK}
        return {
            "no_verified_with_failed_or_unresolved_check": not (self.display_status == "VERIFIED" and (self.failed or self.unresolved)),
            "verified_needs_a_passed_required_check": self.display_status != "VERIFIED" or (self.required > 0 and self.passed == self.required),
            "verified_needs_a_formal_check": self.display_status != "VERIFIED" or any(c.result == "passed" and c.rule in ("claim", "branch_check") for c in self.checks),
            "no_non_success_display_counted_as_passed": all(c.display_status in {s.value for s in POSITIVE_DISPLAYS} for c in claims if c.result == "passed"),
            "every_negative_or_undecided_display_kept": all(c.result != "passed" for c in claims if c.display_status not in {s.value for s in POSITIVE_DISPLAYS}),
            "delivered_unverified_labelled_not_verified": self.display_status != "DELIVERED_UNVERIFIED" or self.label == "not verified",
            "delivered_unverified_only_above_threshold": self.display_status != "DELIVERED_UNVERIFIED" or self.accuracy > self.threshold,
            "withheld_only_at_or_below_threshold_or_unavailable": self.display_status != "WITHHELD" or not self.answer_available or self.accuracy <= self.threshold,
            "shown_only_when_available": self.display_status == "WITHHELD" or self.answer_available,
            "delivered_matches_display": self.delivered is (self.display_status != "WITHHELD"),
            "counts_match_checks": (counts["passed"], counts["failed"], counts["unresolved"], counts["not_required"]) == (self.passed, self.failed, self.unresolved, self.not_required)
                                   and self.required == self.passed + self.failed + self.unresolved,
        }


def _cut(text: str, limit: int = _DETAIL_MAX) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _withheld(threshold: float, synthesis_required: bool, reason: str, checks: Iterable[GateCheck] = ()) -> ResponseGate:
    """A fail-closed decision: nothing is shown, and the reason says why."""
    t = threshold if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and math.isfinite(threshold) else DEFAULT_THRESHOLD
    return ResponseGate(display_status="WITHHELD", label=_cut(f"withheld: {reason}", 300), delivered=False, answer_available=False, required=0, passed=0, failed=0,
                        unresolved=0, not_required=0, accuracy=0.0, threshold=float(t), synthesis_required=bool(synthesis_required),
                        checks=[], reasons=[_cut(reason)] + [_cut(f"{c.check}: {c.result}") for c in list(checks)[:8]], scope=_SCOPE)


_SCOPE = ("The gate decides what is shown from the checks the receipts carry; VERIFIED means every one of them passed. "
          + SCOPE_STATEMENT + " Coverage and layout readings are heuristic.")


def _finding_result(code: str, severity: str, formal_result_id: Optional[str]) -> Optional[tuple[CheckResult, str]]:
    """``(result, why)`` of a finding by its code and severity, or None for an info finding (no check)."""
    if severity not in ("error", "warning"):
        return None
    if code in _HEURISTIC_CODES or _HEURISTIC_RE.match(code):
        return "unresolved", "a heuristic reading: unresolved, never failed"
    if code == "INT-ARG-001":
        return "unresolved", "an argument diagnosis: it leaves its claim unresolved and never fails it on its own"
    if code.startswith("INT-INTERNAL-"):
        return "unresolved", "a check that did not run: what it would have found is not known"
    if severity == "warning":
        return "unresolved", "a warning: unresolved"
    if formal_result_id:
        return "failed", f"an error the engine established (result {formal_result_id})"
    if code in _SOURCE_INTEGRITY:
        return "failed", "a deterministic source-integrity error"
    return "failed", "an error a check decided"


def _receipt_checks(rc: TransmissionReceipt, *, given: set[str], xenc_claims: set[str], xenc_results: set[str],
                    outcome_seen: dict[tuple[str, str], int], out: list[GateCheck]) -> None:
    """Append the checks of one receipt to ``out`` (claims already classified from another receipt are merged, keeping
    the worse result)."""
    rid = rc.receipt_id
    if rc.status is TransmissionStatus.REJECTED:
        errors = sorted({f.code for f in rc.findings if f.severity == "error"})
        out.append(GateCheck(check=f"{rc.direction} transmission", result="failed", rule="delivery", receipt_id=rid,
                             detail=_cut(f"REJECTED: nothing of it was delivered ({', '.join(errors[:8]) or 'no error named'})")))
        return
    out.append(GateCheck(check=f"{rc.direction} transmission", result="passed", rule="delivery", receipt_id=rid, detail=f"{rc.status.value} via branch {rc.branch}"))
    for c in rc.constraint_results:
        res: CheckResult = "passed" if c.satisfied is True else "failed" if c.satisfied is False else "unresolved"
        out.append(GateCheck(check=f"constraint {c.constraint_id}", result=res, rule="constraint", receipt_id=rid, detail=_cut(f"{c.method}: {c.detail}")))
    optional_items = {m.group("item") for f in rc.findings if f.code == "INT-REQ-004" and f.severity == "info" and (m := _ITEM_RE.match(f.message))}
    for cov in rc.coverage:
        if cov.addressed:
            res = "passed"
        else:
            res = "not_required" if cov.item_id in optional_items else "unresolved"
        out.append(GateCheck(check=f"request item {cov.item_id}", result=res, rule="coverage", receipt_id=rid,
                             detail=_cut(f"{cov.method}; addressed by {cov.addressed_by_claim_ids[:12]}"), claim_ids=list(cov.addressed_by_claim_ids)[:64]))
    codes_by_result: dict[str, set[str]] = {}
    for f in rc.findings:
        if f.formal_result_id:
            codes_by_result.setdefault(f.formal_result_id, set()).add(f.code)
    check_results = {fc.formal_result_id for fc in rc.formal_checks if fc.formal_result_id}
    for fc in rc.formal_checks:
        codes = codes_by_result.get(fc.formal_result_id or "", set())
        disagree = bool(fc.formal_result_id and fc.formal_result_id in xenc_results)
        if disagree and fc.satisfied is not None:
            res, why = "unresolved", "its claim's two encodings disagree (INT-XENC-001)"
        elif fc.satisfied is True:
            res, why = "passed", "holds"
        elif fc.satisfied is False:
            if "INT-SUBJ-004" in codes and "INT-SUBJ-001" not in codes:
                res, why = "unresolved", "fails only under a reading the report did not state (INT-SUBJ-004)"
            else:
                res, why = "failed", "does not hold"
        else:
            res, why = "unresolved", "undecided"
        out.append(GateCheck(check=f"branch check {fc.constraint_id}", result=res, rule="branch_check", receipt_id=rid,
                             detail=_cut(f"{why}; {fc.formal_status or 'no status'}: {fc.detail}"), claim_ids=list(fc.claim_ids)[:64]))
    named_on: dict[str, set[str]] = {}  # the receipt's own diagnoses (report level and from findings) by the claims they name
    for d in rc.named_diagnostics:
        if is_blocking(d):
            for cid in d.claim_ids:
                named_on.setdefault(cid, set()).add(d.code)
    for o in rc.outcomes:
        res, why = _claim_result(o, xenc_claims, named_on.get(o.claim_id, set()))
        check = GateCheck(check=f"claim {o.claim_id} of report {o.report_id}", result=res, rule="claim", receipt_id=rid,
                          detail=_cut(why), claim_ids=[o.claim_id], display_status=o.display_status.value)
        key = (o.report_id, o.claim_id)
        if key in outcome_seen:
            k = outcome_seen[key]
            if _RANK[res] > _RANK[out[k].result]:
                out[k] = check
            continue
        outcome_seen[key] = len(out)
        out.append(check)
    for f in rc.findings:
        code, severity, frid = f.code, f.severity, f.formal_result_id
        if code in _RECORD_CODES or code == "INT-SUBJ-003":
            continue
        if code in _CHECK_CODES and frid in check_results:
            continue
        if code == _HISTORY:
            originals = _carried_originals(rc, f)
            if originals and all(orig_rid in given for _c, orig_rid in originals):
                continue  # the gate reads that receipt itself
            if originals:
                # the finding the channel carried, recognised only by making the carried finding again from the receipt's
                # structured history (never by reading its message, which holds an agent's report id: repair round 3, ADV3-02);
                # its severity is the carried finding's own, and of several exact matches the worse classification counts
                worst: Optional[tuple[CheckResult, str, str]] = None
                for orig_code, orig_rid in originals:
                    if orig_rid in given:
                        continue
                    got = (("unresolved", "a coverage or constraint result of an earlier receipt the gate does not read") if orig_code in _RECORD_CODES
                           else _finding_result(orig_code, severity, frid))
                    if got is not None and (worst is None or _RANK[got[0]] > _RANK[worst[0]]):
                        worst = (got[0], got[1], orig_code)
                if worst is None:
                    continue
                out.append(GateCheck(check=f"carried {worst[2]}", result=worst[0], rule="finding", receipt_id=rid, detail=_cut(f"{worst[1]}: {f.message}"),
                                     claim_ids=list(f.claim_ids)[:64], code=worst[2]))
                continue
            # a carried finding the receipt's history does not hold is classified as itself, at its own severity: a carried
            # error is failed (an aggregate "and N more" line too)
        decided = _finding_result(code, severity, frid)
        if decided is None:
            continue
        label = f"finding {code}" if f.code != _HISTORY else f"carried {code}"
        out.append(GateCheck(check=label, result=decided[0], rule="finding", receipt_id=rid, detail=_cut(f"{decided[1]}: {f.message}"),
                             claim_ids=list(f.claim_ids)[:64], code=code))
    for sf in rc.structural_findings:
        decided = _finding_result(sf.code, sf.severity, None)
        if decided is None:
            continue
        out.append(GateCheck(check=f"subject finding {sf.code}", result=decided[0], rule="finding", receipt_id=rid, detail=_cut(f"{decided[1]}: {sf.message}"),
                             claim_ids=list(sf.claim_ids)[:64], code=sf.code))


def _carried_originals(rc: TransmissionReceipt, f) -> list[tuple[str, str]]:
    """``(original code, receipt id of the original)`` for each unresolved finding of ``rc.history`` whose carried finding,
    made again by the channel's own constructor (``contracts.carried_finding``, ``carried_subject_finding``), is exactly
    ``f``: the same severity, claims, message ids, signed result and message. Nothing of the message is parsed; a finding
    no reference of the history makes is no carried original (an empty list)."""
    out: list[tuple[str, str]] = []
    first = f.message_ids[0] if f.message_ids else None
    for ref in rc.history:
        if first is not None and ref.message_id != first:
            continue
        for o in ref.unresolved_findings:
            if o.severity != f.severity or list(o.claim_ids) != list(f.claim_ids) or o.formal_result_id != f.formal_result_id:
                continue
            again = carried_finding(ref, o)
            if again.message == f.message and again.message_ids == list(f.message_ids):
                out.append((o.code, ref.receipt_id))
        for sf in ref.unresolved_subject_findings:
            if list(sf.claim_ids) != list(f.claim_ids):
                continue
            again = carried_subject_finding(ref, sf)
            if again.severity == f.severity and again.message == f.message and again.message_ids == list(f.message_ids):
                out.append((sf.code, ref.receipt_id))
    return out


def _claim_result(o, xenc_claims: set[str], named_on_claim: set[str]) -> tuple[CheckResult, str]:
    """``(result, why)`` of one claim outcome (the ``claim`` rule); ``named_on_claim`` are the codes of the receipt's own
    warning or error diagnoses that name the claim (report-level rules, findings)."""
    display = o.display_status
    if o.claim_id in xenc_claims:
        return "unresolved", f"display {display.value}; its two encodings reach opposite definitive answers (INT-XENC-001)"
    if display in NEGATIVE_DISPLAYS:
        return "failed", f"display {display.value}: a negative verdict on the encoding"
    if display is S.NOT_ELIGIBLE:
        route = getattr(o.translation.eligibility, "route_to", None)
        return "unresolved", f"display NOT_ELIGIBLE: the engine was not asked" + (f"; its check lies with the {route.replace('_', ' ')}, which the gate does not read" if route and route != "unresolved" else "")
    if display not in POSITIVE_DISPLAYS:
        return "unresolved", f"display {display.value}: no verdict on the claim"
    v = o.verification
    if v is None:
        return "unresolved", f"display {display.value} with no engine result behind it"
    rests = list(v.ungrounded_dependencies) + list(v.unverified_dependencies)
    if rests:
        return "unresolved", f"display {display.value}, but it rests on premises not established: {rests[:8]}"
    diags = list(o.named_diagnostics) + list(v.named_diagnostics or [])
    blocking = sorted({d.code for d in diags if is_blocking(d)} | set(named_on_claim))
    if blocking:
        return "unresolved", f"display {display.value}, but the argument diagnosis names {blocking[:8]} (warning or error by effective severity)"
    # a diagnosis not computed or not finished is never read as none found (repair round 3, INV-7): the engine's rules must
    # have run to the end on this result, and every claim and report rule of the outcome too
    if getattr(v, "argument_rules", None) != ARG_RULES_VERSION:
        return "unresolved", f"display {display.value}, but the engine's argument diagnosis was not computed or did not finish ({getattr(v, 'argument_rules', None)!r})"
    if list(getattr(o, "diagnosis_incomplete", None) or []):
        return "unresolved", f"display {display.value}, but its argument diagnosis is incomplete ({'; '.join(list(o.diagnosis_incomplete)[:3])})"
    if o.release is None:
        return "unresolved", f"display {display.value}, but no release assessment was made for it"
    if not o.release.permitted:
        return "unresolved", f"display {display.value}, but its release is refused ({'; '.join(o.release.unresolved[:4]) or o.release.fidelity})"
    return "passed", f"display {display.value} on established premises"


def assess_response(receipts, synthesis_receipt=None, *, synthesis_required: bool, threshold: float = DEFAULT_THRESHOLD) -> ResponseGate:
    """Decide what the student is shown for one request (module docstring). Never raises."""
    try:
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
            return _withheld(DEFAULT_THRESHOLD, bool(synthesis_required), f"the delivery threshold {threshold!r} is not a number between 0 and 1")
        threshold = float(threshold)
        if not isinstance(synthesis_required, bool):
            return _withheld(threshold, False, "synthesis_required is not a boolean: whether the plan routes to a combinator is not known")
        try:
            given_receipts = list(receipts) if receipts is not None else []
        except TypeError:
            return _withheld(threshold, synthesis_required, "the receipts are not a list of transmission receipts")
        if any(not isinstance(r, TransmissionReceipt) for r in given_receipts):
            return _withheld(threshold, synthesis_required, "a receipt given is not a transmission receipt")
        if synthesis_receipt is not None and not isinstance(synthesis_receipt, TransmissionReceipt):
            return _withheld(threshold, synthesis_required, "the synthesis receipt given is not a transmission receipt")
        if not given_receipts:
            return _withheld(threshold, synthesis_required, "no receipt: nothing was delivered")
        read = given_receipts + ([synthesis_receipt] if synthesis_required and synthesis_receipt is not None else [])
        given = {r.receipt_id for r in read}
        xenc_claims = {cid for r in read for f in r.findings if f.code == _XENC for cid in f.claim_ids}
        xenc_results = {rid for r in read for f in r.findings if f.code == _XENC for rid in ([f.formal_result_id] if f.formal_result_id else []) + list(f.related_result_ids)}
        checks: list[GateCheck] = []
        seen: dict[tuple[str, str], int] = {}
        for r in given_receipts:
            _receipt_checks(r, given=given, xenc_claims=xenc_claims, xenc_results=xenc_results, outcome_seen=seen, out=checks)
        reasons: list[str] = []
        if synthesis_required:
            if synthesis_receipt is None:
                checks.append(GateCheck(check="combinator synthesis", result="failed", rule="synthesis", detail="the plan routes the answer to a combinator, and no synthesis receipt was given"))
            else:
                _receipt_checks(synthesis_receipt, given=given, xenc_claims=xenc_claims, xenc_results=xenc_results, outcome_seen=seen, out=checks)
        else:
            checks.append(GateCheck(check="combinator synthesis", result="not_required", rule="synthesis",
                                    detail="the plan routes the answer to no combinator (fast path): the student is shown the delivered reports"))
        n = {r: sum(1 for c in checks if c.result == r) for r in _RANK}
        required = n["passed"] + n["failed"] + n["unresolved"]
        decided = n["passed"] + n["failed"]
        accuracy = (n["passed"] / decided) if decided else 0.0
        delivered_any = any(r.status is not TransmissionStatus.REJECTED for r in given_receipts)
        formal_passed = any(c.result == "passed" and c.rule in ("claim", "branch_check") for c in checks)
        if required and n["failed"] == 0 and n["unresolved"] == 0 and delivered_any and formal_passed:
            display, label = "VERIFIED", "verified"
        elif delivered_any and accuracy > threshold:
            display, label = "DELIVERED_UNVERIFIED", "not verified"
        else:
            display = "WITHHELD"
            why = "nothing was delivered" if not delivered_any else f"accuracy {accuracy:.3f} is not above the delivery threshold {threshold:.2f}"
            label = f"withheld: {why}"
            reasons.append(why)
        if display != "VERIFIED":
            if not formal_passed:
                reasons.append("no claim or statement of the answer was verified by the engine")
            if n["failed"]:
                reasons.append(f"{n['failed']} check(s) failed: " + "; ".join(c.check for c in checks if c.result == "failed")[:400])
            if n["unresolved"]:
                reasons.append(f"{n['unresolved']} check(s) unresolved: " + "; ".join(c.check for c in checks if c.result == "unresolved")[:400])
        gate = ResponseGate(display_status=display, label=label, delivered=display != "WITHHELD", answer_available=delivered_any, required=required, passed=n["passed"], failed=n["failed"],
                            unresolved=n["unresolved"], not_required=n["not_required"], accuracy=accuracy, threshold=threshold,
                            synthesis_required=synthesis_required, checks=checks, reasons=[_cut(r) for r in reasons], scope=_SCOPE)
        broken = [k for k, ok in gate.invariants().items() if not ok]
        if broken:  # never shown: a decision that reads better than its checks
            return _withheld(threshold, synthesis_required, f"the decision would break the gate's invariants {broken}", checks)
        return gate
    except Exception as exc:  # noqa: BLE001 - the gate fails closed and never raises
        return _withheld(threshold if isinstance(threshold, float) else DEFAULT_THRESHOLD, synthesis_required is True,
                         f"the gate could not assess the receipts ({type(exc).__name__})")
