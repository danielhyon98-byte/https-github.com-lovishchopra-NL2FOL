"""Integration gate 4 (blocker, critical): a branch or STEM check's verdict is read from the check's own decision.

``claim_entries`` set a branch or STEM formal check's verdict ``formal`` to the raw engine status (``fc.formal_status``)
and ignored the check's polarity (``expected_if_sound``, folded into ``fc.satisfied`` by the channel). Checks whose sound
status is UNSATISFIABLE were inverted: stem-bool (Boolean identities and evaluations) and stem-op (a stated operation on
both sides). A correct answer was counted blocking and refused (KIT-DL-010); a failing check was counted positive; an
undecided check (vacuous E108 with the expected status, inconsistent premises the check does not count as a failure) was
shown as its raw definitive status. ``routing_features.output_features`` had the same raw mapping, so the flash router
escalated correct Boolean answers as negative.

``claims.branch_check_formal`` now maps by ``satisfied``: True is a positive status (the raw one when positive, else
ENTAILED), False a negative status (the raw one when negative, else COUNTEREXAMPLE), None with a definitive raw status
UNKNOWN (undecided), None with no status NOT_ATTEMPTED (not run), any other status as it is.
"""
from __future__ import annotations

import pytest

from epinoic_logic.channel.contracts import ConstraintResult
from epinoic_logic.integration.checks_port import check_request
from epinoic_logic.integration.claims import branch_check_formal, claim_entries, excerpt_of
from epinoic_logic.integration.delivery import count_claims
from epinoic_logic.integration.protocol import INCOMPLETE_STATUSES, NEGATIVE, POSITIVE
from epinoic_logic.integration.routing_features import OutputRecord, output_features
from epinoic_logic.translate.contracts import ClaimRecord
from tests.integration.helpers import answer_envelope, turn_request
from tests.integration.test_turn_checker import _checker

CS = ("Computer Science", "computer-science", "Simplify NOT (A AND B).")
MATHS = ("Mathematics: Analysis and Approaches", "mathematics-aa", "Solve 2x - 4 = 6.")
DE_MORGAN = "NOT (A AND B) = NOT A OR NOT B"
WRONG_DE_MORGAN = "NOT (A AND B) = NOT A AND NOT B"
STEP = "$2x - 4 = 6$. Adding 4 to both sides gives $2x = 10$, so $x = 5$."
WRONG_STEP = "$2x - 4 = 6$. Adding 4 to both sides gives $2x = 12$, so $x = 6$."


def _verdict(subject: tuple[str, str, str], answer: str, policy: str) -> dict:
    subj, slug, question = subject
    rt, _port = _checker()
    envs = [answer_envelope(1, agent_id=slug, answer=answer, slug=slug)]
    raw = turn_request(envs, user_text=question, policy=policy, route=None, slug=slug, subject=subj)
    return rt.checker.check(check_request(raw, rt.request_limits, service_env="sim"))


def _entry(verdict: dict, cid: str) -> dict:
    return next(c for c in verdict["claims"] if c["claim_id"] == cid)


@pytest.mark.parametrize("policy", ["verified-v1", "verified-v1-qualify"])
def test_a_correct_boolean_identity_is_a_positive_check_and_is_delivered(policy):
    v = _verdict(CS, DE_MORGAN, policy)
    assert _entry(v, "stem-bool-1")["formal"] == "ENTAILED"
    assert v["counts"]["blocking"] == 0 and v["counts"]["positive"] == 1
    assert v["delivery"]["decision"] == "deliver" and "KIT-DL-010" not in v["delivery"]["reasons"]


@pytest.mark.parametrize("policy", ["verified-v1", "verified-v1-qualify"])
def test_a_wrong_boolean_identity_is_never_counted_positive(policy):
    v = _verdict(CS, WRONG_DE_MORGAN, policy)
    assert _entry(v, "stem-bool-1")["formal"] in NEGATIVE
    assert v["counts"]["positive"] == 0 and v["counts"]["blocking"] == 1
    assert v["delivery"]["decision"] == "refuse_unresolved" and "KIT-DL-010" in v["delivery"]["reasons"]


def test_a_correct_stated_operation_is_a_positive_check():
    for policy, decision in (("verified-v1", "refuse_incomplete"), ("verified-v1-qualify", "deliver")):
        v = _verdict(MATHS, STEP, policy)
        assert _entry(v, "stem-op-1")["formal"] == "ENTAILED"
        assert v["counts"]["blocking"] == 0 and "KIT-DL-010" not in v["delivery"]["reasons"]
        # the material translation claim m1.1 has no outcome in the corpus: rows 5 to 7 decide (KIT-DL-011 under verified-v1)
        assert v["delivery"]["decision"] == decision


def test_a_wrong_stated_operation_is_blocking():
    v = _verdict(MATHS, WRONG_STEP, "verified-v1-qualify")
    assert _entry(v, "stem-op-1")["formal"] in NEGATIVE and _entry(v, "stem-alg-1")["formal"] in NEGATIVE
    assert v["counts"]["positive"] == 0 and v["counts"]["blocking"] == 2
    assert v["delivery"]["decision"] == "refuse_unresolved" and "KIT-DL-010" in v["delivery"]["reasons"]


@pytest.mark.parametrize("satisfied,raw,formal", [
    (True, "UNSATISFIABLE", "ENTAILED"), (True, "ENTAILED", "ENTAILED"), (True, "SATISFIABLE", "SATISFIABLE"),
    (False, "SATISFIABLE", "COUNTEREXAMPLE"), (False, "COUNTEREXAMPLE", "COUNTEREXAMPLE"), (False, "UNSATISFIABLE", "UNSATISFIABLE"),
    (None, "ENTAILED", "UNKNOWN"), (None, "UNSATISFIABLE", "UNKNOWN"), (None, "INCONSISTENT_PREMISES", "UNKNOWN"),
    (None, "TIMEOUT", "TIMEOUT"), (None, "UNKNOWN", "UNKNOWN"),
    # a holding check with no definitive engine status (the channel never builds one) is undecided, never positive
    (True, "TIMEOUT", "TIMEOUT"), (True, None, "UNKNOWN"), (True, "INTERNAL_ERROR", "INTERNAL_ERROR"),
])
def test_the_verdict_is_read_from_the_check_s_decision(satisfied, raw, formal):
    fc = ConstraintResult(constraint_id="stem-bool-1", satisfied=satisfied, method="formal", detail="d", formal_status=raw)
    assert branch_check_formal(fc, stem=True) == (formal, "attempted")
    if satisfied is not True:
        assert formal not in POSITIVE, "a failed or undecided check is never positive"
    if satisfied is not False:
        assert formal not in NEGATIVE, "a correct or undecided check is never blocking"


def test_a_check_that_was_not_run_is_not_attempted():
    fc = ConstraintResult(constraint_id="stem-eq-1", satisfied=None, method="formal", detail="not run: budget")
    assert branch_check_formal(fc, stem=True) == ("NOT_ATTEMPTED", "stem_budget")
    assert branch_check_formal(fc, stem=False) == ("NOT_ATTEMPTED", "skipped_budget")


def _claim(cid: str, text: str) -> ClaimRecord:
    return ClaimRecord(claim_id=cid, request_id="req", task_id="task", report_id="rep", agent_id="computer-science-specialist",
                       subject="Computer Science", task_type="short_answer", claim_text=text, claim_role="other", materiality="material")


class _Receipt:
    branch = "computer_science"
    outcomes: list = []

    def __init__(self, checks):
        self.formal_checks = checks


@pytest.mark.parametrize("raw", ["ENTAILED", "UNSATISFIABLE", "INCONSISTENT_PREMISES"])
def test_an_undecided_check_is_counted_unavailable_never_positive_or_blocking(raw):
    """A vacuous check (E108) with the expected status, or inconsistent premises the check does not count as a failure:
    satisfied None with a definitive raw status."""
    fc = ConstraintResult(constraint_id="stem-bool-1", satisfied=None, method="formal", detail="d", formal_status=raw, claim_ids=["c1.1"])
    claims = [_claim("c1.1", DE_MORGAN)]
    entries, fields = claim_entries(_Receipt([fc]), claims, DE_MORGAN)
    check = next(e for e in entries if e["claim_id"] == "stem-bool-1")
    assert check["formal"] in INCOMPLETE_STATUSES
    counts = count_claims(fields)
    assert counts["positive"] == 0 and counts["blocking"] == 0 and counts["unavailable"] == 1


def test_the_routing_features_read_the_same_verdict():
    """The flash router's planner escalates on a negative status: a correct Boolean answer is no negative output."""
    fcs = [ConstraintResult(constraint_id="stem-bool-1", satisfied=True, method="formal", detail="d", formal_status="UNSATISFIABLE"),
           ConstraintResult(constraint_id="stem-bool-2", satisfied=False, method="formal", detail="d", formal_status="SATISFIABLE")]

    class _R(_Receipt):
        findings: list = []

        class status:
            value = "ACCEPTED"
    rec = OutputRecord(transfer_key="t1", role="answer", agent_id="computer-science", subject="Computer Science", receipt=_R(fcs), claims=[], text=DE_MORGAN)
    statuses = output_features(rec)["engine_statuses"]
    assert statuses == {"ENTAILED": 1, "COUNTEREXAMPLE": 1}


# ===================================================================================== the class sweep (integration gate 4)
# The handoff fixer's paths include integration/claims.py and integration/routing_features.py: each public entry point is
# fed the standard hostile runs (about 20,000 characters of one shape, followed by a character that defeats a match) as the
# answer, the claim texts and the output's text, and must read them in linear time. Measured: at most 0.4 s per call.
from types import SimpleNamespace

from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.routing_features import build_routing_request

from ..core_hostile import SHAPES, one, sweep


class _HostileReceipt:
    branch = "computer_science"
    outcomes: list = []
    findings: list = []

    class status:
        value = "ACCEPTED"

    def __init__(self, claim_ids):
        self.formal_checks = [ConstraintResult(constraint_id=f"stem-bool-{k}", satisfied=(None if k % 3 == 2 else k % 3 == 0), method="formal",
                                               detail="d", formal_status=("UNSATISFIABLE" if k % 2 else "SATISFIABLE"), claim_ids=[cid])
                              for k, cid in enumerate(claim_ids)]


def _hostile_claims(text: str) -> list[ClaimRecord]:
    out = []
    for i in range(8):
        body = (text[i * 500:i * 500 + 3900].strip() or "x")[:4000]
        out.append(_claim(f"c1.{i}", body))
    return out


def _claims_entries(text: str):
    """integration/claims.py: excerpt_of, claim_entries and branch_check_formal."""
    claims = _hostile_claims(text)
    receipt = _HostileReceipt([c.claim_id for c in claims])
    words = " ".join(text.split()[:40])
    yield "excerpt_of (found)", lambda: excerpt_of(text, text)
    yield "excerpt_of (not found)", lambda: excerpt_of(text + "y", text)
    yield "excerpt_of (forty words, then a miss)", lambda: excerpt_of(words + " zz", text)
    yield "excerpt_of (a claim at the cap in the run)", lambda: excerpt_of(text[:4000], text)
    yield "claim_entries", lambda: claim_entries(receipt, claims, text)
    yield "branch_check_formal", lambda: [branch_check_formal(fc, stem=True) for fc in receipt.formal_checks]


def _routing_entries(text: str):
    """integration/routing_features.py: output_features and build_routing_request."""
    claims = _hostile_claims(text)
    receipt = _HostileReceipt([c.claim_id for c in claims])
    rec = OutputRecord(transfer_key="t1", role="answer", agent_id="computer-science", subject="Computer Science", receipt=receipt, claims=claims, text=text)
    yield "output_features", lambda: output_features(rec)
    task_request = SimpleNamespace(items=[], constraints=[], supplied_texts=[SimpleNamespace(document_id="d1", text=text)], task_type="short_answer",
                                   course_level="HL", user_input_sha256="0" * 64)
    yield "build_routing_request", lambda: build_routing_request(task_id="t", request_id="r", task_request=task_request, subjects=["Computer Science"],
                                                                 outputs=[rec], topology={"kind": "single", "sources": [], "synthesis": None}, max_instances=4,
                                                                 profiles=["standard"])


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_integration_claims(shape):
    """integration/claims.py on every hostile shape, one test per shape; the CPU bound per call is the gate-2 sweep's (4 s)."""
    assert not sweep(_claims_entries, texts=one(shape))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_integration_routing_features(shape):
    """integration/routing_features.py on every hostile shape, one test per shape; a refusal of the routing request
    (IntegrationError, ValueError) is an answer, any other exception a crash. The CPU bound per call is 4 s."""
    assert not sweep(_routing_entries, refusals=(ValueError, IntegrationError), texts=one(shape))
