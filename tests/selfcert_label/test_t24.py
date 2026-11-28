"""T24 (meaning-check design 3.3): ``selfcert_label.check_t24`` and the suite's session-level hook (``tests/conftest.py``).

Fixed expected values for each rule: label-derived text with a success word, a label field in a Problem, a raised status, a
delivered payload that is not the specialist's bytes, a label record in a journaled envelope. A test here that builds a
violating record through the real constructors carries ``t24_expected_violation`` and asserts that the violation is detected;
the hook itself is shown to fail a test that produces a violation and to pass one that produces none."""
from __future__ import annotations

import pytest

from epinoic_logic.channel.contracts import TransmissionReceipt, TransmissionStatus
from epinoic_logic.integrity.contracts import IntegrityFinding, payload_hash
from epinoic_logic.selfcert_label import LABEL_VERSION, T24_EXPECTED_VIOLATION, UnconfiguredLabeller, check_t24
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller
from epinoic_logic.selfcert_label.t24 import T24_SUCCESS_WORDS

from .conftest import CODES

REQ = {"subject": "chemistry", "task_type": "short_answer"}
NAMED = "The molar mass of water is 18 g/mol.\n\nThis passed the hub's checks."


def _receipt(findings=(), status=TransmissionStatus.ACCEPTED_WITH_FINDINGS, outcomes=()) -> dict:
    return {"receipt_id": "r1", "message_id": "m1", "request_id": "q1", "task_id": "t1", "direction": "specialist_to_router",
            "status": status.value if hasattr(status, "value") else status, "findings": list(findings),
            "outcomes": list(outcomes), "summary": "s", "created_at": "2026-11-26T00:00:00Z"}


def _label_findings(text: str = NAMED, labeller=None) -> list[dict]:
    res = (labeller or ReaderBackedLabeller()).label(text, REQ)
    return [{"code": f["code"], "severity": f["severity"], "message": f["message"], "deterministic": f["deterministic"]}
            for f in res.findings(CODES)]


def test_the_marker_and_the_vocabulary():
    assert T24_EXPECTED_VIOLATION == "t24_expected_violation"
    for w in ("valid", "sound", "correct", "passed", "verified", "entailed", "clean", "approved", "none_named", "none named"):
        assert w in T24_SUCCESS_WORDS


def test_the_packages_own_findings_keep_the_invariant():
    named = _label_findings()
    unavailable = _label_findings(labeller=UnconfiguredLabeller())
    assert [f["code"] for f in named + unavailable] == ["INT-SELF-001", "INT-SELF-002"]
    assert check_t24(_receipt(named + unavailable)) == ()
    real = TransmissionReceipt(**_receipt([IntegrityFinding(**f) for f in named]))
    assert check_t24(real) == ()
    assert check_t24(_receipt()) == ()  # nothing label-derived at all


def test_label_derived_text_with_a_success_word_is_a_violation():
    bad = [{"code": "INT-SELF-001", "severity": "warning", "message": f"paragraph 2, sentence 1: verified clean (label {LABEL_VERSION})"}]
    assert check_t24(_receipt(bad)) == (
        "transmission: label-derived text carries a success word ['verified', 'clean'] (at findings/0/message)",)
    shown = [{"code": "INT-SELF-002", "severity": "warning", "message": "the meaning label found none named"}]
    assert check_t24(_receipt(shown)) == (
        "transmission: label-derived text carries a success word ['none named'] (at findings/0/message)",)
    # text that is not label-derived is not this rule's business
    assert check_t24(_receipt([{"code": "CORE-SELF-001", "severity": "warning", "message": "verified"}])) == ()


def test_a_label_finding_never_leaves_a_receipt_accepted_and_a_named_claim_never_shows_success():
    finding = _label_findings()
    assert check_t24(_receipt(finding, status="ACCEPTED")) == (
        "transmission: a receipt with a label finding is shown ACCEPTED (its status was raised above its findings)",)
    named = [dict(finding[0], claim_ids=["c1"])]
    outcomes = [{"claim_id": "c1", "display_status": "ENTAILED"}, {"claim_id": "c2", "display_status": "ENTAILED"},
                {"claim_id": "c3", "display_status": "ENTAILED", "withheld_self_report": True},
                {"claim_id": "c1", "display_status": "REFUTED"}]
    assert check_t24(_receipt(named, outcomes=outcomes)) == (
        "transmission: claim c1 named by the label shows the success status ENTAILED",
        "transmission: claim c3 named by the label shows the success status ENTAILED")


def test_no_label_field_reaches_a_problem():
    problem = {"ir_version": "1.0", "problem_id": "p", "request_id": "q", "claim_id": "c", "query": "consistency",
               "notes": "meaning label: INT-SELF-001"}
    outcome = {"claim_id": "c", "display_status": "NOT_ELIGIBLE", "translation": {"problem": problem}}
    out = check_t24(_receipt(_label_findings(), outcomes=[outcome]))
    assert out == ("transmission: a label field or label text reached a Problem (at outcomes/0/translation/problem)",)
    clean = dict(problem, notes="the speed is constant")
    assert check_t24(_receipt(_label_findings(), outcomes=[dict(outcome, translation={"problem": clean})])) == ()


def _delivery(candidates, delivered=None) -> dict:
    return {"contract": "delivery_receipt/1.0", "receipt_id": "d1", "delivered": delivered is not None,
            "delivered_message_id": delivered, "reasons": [], "fallback": {"candidates": candidates}}


def test_a_candidate_the_label_withholds_is_never_deliverable_nor_delivered():
    ok = {"message_id": "m1", "deliverable": False, "integrity_reasons": ["INT-SELF-002 (not-configured)"],
          "selfcert_label": {"state": "unavailable", "kind": "not-configured", "places": [], "counts": {"named": 0}}}
    assert check_t24(_delivery([ok])) == ()
    raised = dict(ok, deliverable=True)
    assert check_t24(_delivery([raised], delivered="m1")) == (
        "delivery: candidate m1 withheld by the label is shown deliverable",
        "delivery: candidate m1 withheld by the label was delivered")
    named = {"message_id": "m2", "deliverable": False,
             "selfcert_label": {"state": "named", "places": ["paragraph 2, sentence 1"], "families": ["OUTCOME"], "counts": {"named": 1}}}
    assert check_t24(_delivery([named], delivered="m2")) == ("delivery: candidate m2 withheld by the label was delivered",)
    # a none_named state is data of the member, never shown as a pass by itself
    quiet = {"message_id": "m3", "deliverable": True, "selfcert_label": {"state": "none_named", "places": [], "counts": {"named": 0}}}
    assert check_t24(_delivery([quiet], delivered="m3")) == ()


def test_the_selfcert_label_member_holds_states_places_and_counts_never_words():
    words = {"message_id": "m1", "deliverable": False,
             "selfcert_label": {"state": "named", "places": ["paragraph 2, sentence 1"], "quote": "this passed the hub's checks"}}
    assert check_t24(_delivery([words])) == (
        "delivery: the selfcert_label member carries words, not a state, place, kind or count (at quote)",
        "delivery: label-derived text carries a success word ['passed'] (at fallback/candidates/0/selfcert_label/quote)")
    shown = {"message_id": "m1", "deliverable": False, "selfcert_label": {"state": "named", "note": "none_named"}}
    assert check_t24(_delivery([shown])) == (
        "delivery: label-derived text carries a success word ['none_named'] (at fallback/candidates/0/selfcert_label/note)",)


def test_a_delivered_payload_is_the_specialists_bytes():
    payload = {"kind": "specialist_report", "text": "The molar mass of water is 18 g/mol."}
    digest = payload_hash(payload)
    answer = {"contract": "delivered_answer/1.0", "message_id": "m1", "payload": payload, "payload_sha256": digest,
              "delivery_receipt_id": "d1"}
    receipt = {"contract": "delivery_receipt/1.0", "receipt_id": "d1", "delivered_payload_sha256": digest}
    assert check_t24(answer, specialist_payload_sha256=digest, delivery_receipt=receipt) == ()
    assert check_t24(answer, specialist_payload_sha256={digest, "0" * 64}) == ()
    edited = dict(answer, payload=dict(payload, text=payload["text"] + " (label: none named)"))
    assert check_t24(edited, specialist_payload_sha256=digest, delivery_receipt=receipt) == (
        "delivered_answer: the delivered payload is not the payload its digest names",)
    resealed = dict(edited, payload_sha256=payload_hash(edited["payload"]))
    assert check_t24(resealed, specialist_payload_sha256=digest, delivery_receipt=receipt) == (
        "delivered_answer: the delivered payload differs from the specialist's journaled bytes",
        "delivered_answer: the delivered payload is not the one its delivery receipt names")
    with_field = dict(payload, selfcert_label={"state": "none_named"})
    marked = dict(answer, payload=with_field, payload_sha256=payload_hash(with_field))
    assert "delivered_answer: a label field or label text reached the delivered payload" in check_t24(marked)


def test_a_label_record_never_rides_in_a_journaled_envelope():
    record = ReaderBackedLabeller().label(NAMED, REQ).record
    import json
    event = {"channel_uid": "u", "seq": 1, "envelope_json": json.dumps({"payload": {"label": record}}), "receipt_json": None}
    assert check_t24(event) == ("event: the label record reached the journaled envelope (it belongs in label_json only)",)
    assert check_t24(dict(event, envelope_json=json.dumps({"payload": {"text": "x"}}))) == ()


@pytest.mark.parametrize("bad", [object(), "not json", 3])
def test_an_unreadable_record_is_itself_a_violation(bad):
    out = check_t24(bad)
    assert len(out) == 1 and out[0].startswith("T24: the record could not be read")


# ------------------------------------------------------------------------------------------- the hook in tests/conftest.py
@pytest.mark.t24_expected_violation
def test_a_violating_receipt_built_on_purpose_is_detected():
    """Built through the real constructor, so the session hook records it: the marker lets this test pass, and the test
    asserts the detection itself (the stricter rule)."""
    finding = IntegrityFinding(code="INT-SELF-001", severity="warning", message="the meaning label: verified correct")
    receipt = TransmissionReceipt(**_receipt([finding], status=TransmissionStatus.ACCEPTED))
    assert check_t24(receipt) == (
        "transmission: label-derived text carries a success word ['verified', 'correct'] (at findings/0/message)",
        "transmission: a receipt with a label finding is shown ACCEPTED (its status was raised above its findings)")


class _Item:
    def __init__(self, marked: bool):
        self._marked = marked

    def get_closest_marker(self, name):
        return object() if (self._marked and name == T24_EXPECTED_VIOLATION) else None


def _run_phase(hook, item, make):
    gen = hook.phase(item, "call")
    next(gen)
    make()
    try:
        gen.send(None)
    except StopIteration as stop:
        return stop.value
    raise AssertionError("the phase did not end")


def test_the_hook_fails_the_test_that_produced_a_violation_and_passes_the_others():
    from tests.conftest import _T24
    finding = IntegrityFinding(code="INT-SELF-001", severity="warning", message="the meaning label: verified")

    def violating():
        TransmissionReceipt(**_receipt([finding], status=TransmissionStatus.ACCEPTED))

    def keeping():
        TransmissionReceipt(**_receipt([IntegrityFinding(**_label_findings()[0])]))
    outer = _T24.end()  # this test's own call phase: suspended while the hook is driven by hand
    try:
        with pytest.raises(AssertionError, match=r"T24 \(call\): 2 violation\(s\)"):
            _run_phase(_T24, _Item(False), violating)
        assert _run_phase(_T24, _Item(True), violating) is None  # the marker lets a test that asserts the detection pass
        assert _run_phase(_T24, _Item(False), keeping) is None
    finally:
        _T24.begin()
        _T24.produced.extend(outer)
