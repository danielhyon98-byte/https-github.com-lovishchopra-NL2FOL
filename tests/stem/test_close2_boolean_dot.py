"""Close round 2 of the argument-diagnosis regression review, DIFF-04: the Computer Science AND dot and Boolean constants.

A wrong Boolean step written with the AND dot and a constant ('Since P.0 = P, we get P.Q + P.0 = P.Q + P = P.': the step
P.0 = P is false) was checked on the committed base, whose full stops between letters are full stops, and named INT-SUBJ-001.
Once the AND dot was read (re-run review stem-soundness-4) the dot before the constant stayed a decimal point to the lexer,
so the expression was read only in part, and the guard against a relation cut from a longer expression withheld what was
left: the working went unchecked. An answer that writes a Boolean constant with the AND dot (``lexer.writes_constant_dot``)
is now read as before both readings; every other answer keeps the AND dot, so a correct absorption written with it stays
checked and clean. What this gives up (docs/ARGUMENT_DIAGNOSTICS.md, section 7): the committed base's reading of those full
stops also charges a correct step written with a constant and the AND dot ('Since A.1 = A, ...'), as on the base.

Wording of this round's own; each positive was checked to fail on the tree before the round."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.lexer import writes_constant_dot

KEY = b"argdiag-stem-test-key-close2-0123456789"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
ASK = "Simplify the Boolean expression A.B + A.0 and justify each step."


def _receipt(answer: str, request: str = ASK):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Computer Science", task_type="short_answer",
                           selected_agent_ids=["cs-specialist"]))
    m, _req, _rq = hub.dispatch("t", "cs-specialist", request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="cs-specialist", report_id="r1")
    return rc


def _errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


def _bool_checks(rc) -> list[tuple[str, object]]:
    return [(c.constraint_id, c.satisfied) for c in rc.formal_checks if c.constraint_id.startswith("stem-bool")]


@pytest.mark.parametrize("text, expected", [
    ("Since A.0 = A, the sum is A.", True), ("Then B.1 = B.", True), ("(A + B).0 = 0", True), ("so AB.1 = AB", True),
    ("A.B + A = A", False), ("x = 3.0", False), ("see Fig.1 below", False), ("ABC.0 is a label", False), ("A.01 and A.10", False),
    ("the value x.0", False), ("A.B + 0 = A.B", False), (".0 alone", False),
])
def test_a_boolean_constant_written_with_the_and_dot_is_recognised(text, expected):
    assert writes_constant_dot(text) is expected


def test_a_wrong_step_with_a_constant_and_the_and_dot_is_checked_and_fails():
    rc = _receipt("Since A.0 = A, we get A.B + A.0 = A.B + A = A.")
    assert _errors(rc), [(f.code, f.message[:120]) for f in rc.findings]
    assert any(ok is False for _cid, ok in _bool_checks(rc))


def test_control_a_correct_absorption_with_the_and_dot_stays_checked_and_clean():
    rc = _receipt("We get A.B + A = A by absorption.", "Simplify the Boolean expression A.B + A and justify each step.")
    assert not _errors(rc)
    assert _bool_checks(rc) and all(ok is True for _cid, ok in _bool_checks(rc))


def test_control_a_correct_step_with_a_constant_raises_no_error():
    rc = _receipt("Since A.0 = 0, we get A.B + A.0 = A.B + 0 = A.B.")
    assert not _errors(rc), [(f.code, f.message[:120]) for f in rc.findings]
