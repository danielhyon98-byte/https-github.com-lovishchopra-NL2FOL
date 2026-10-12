"""Genuine round-7 STEM answers raised engine errors (INT-SUBJ-001) that named no fault once the STEM branches read them
(the STEM merge into the round-7 development branch). Each cause is fixed where the reading went wrong, never by
silencing the check, and the same fault written into the same line is still named:

* a thousands group inside brackets was read as two numbers (``(1,000 ÷ 2^10 = 0.98)`` checked ``000 ÷ 2^10``);
* a stated value with its absolute uncertainty (``1620 − 20 = 1600 ± 32 counts min⁻¹``) was read as two stated values;
* a run stopped before a power written after a value (``800 = 1600 e^(−8k)`` was read as ``800 = 1600``);
* a line that writes the preceding relation with values put in (``1/R = 1/R₁ + 1/R₂`` then ``1/R = 1/4.0 Ω + 1/6.0 Ω``)
  was checked as an algebra step for every value of R₁ and R₂;
* a symbol reused in a later part for a quantity the request gives (``R = 2.4 Ω`` in (a), ``P = (9.93 V)² / 6.0 Ω`` for
  "the 6.0 ohm resistor" in (d)) was checked against the other part's binding;
* the order relations of a sentence stated under a condition (``For 2 < t ≤ 3, 2 − t is negative, so v < 0.``) were
  checked against the values stated for t and v elsewhere;
* a prose value after "so" was set against an older chain than the last one before it (``… > 6000, so the answer is 12
  years`` against a chain two paragraphs up) or against a value stated for a symbol (``mid = 4``)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.lexer import lex
from epinoic_logic.translate.contracts import SuppliedText

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
STEM_TASKS = sorted(tid for tid, it in SPEC.items() if default_registry().for_subject(it["subject"])[0].key in ("sciences", "mathematics", "computer_science"))
KEY = b"round7-stem-false-errors-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def receive(subject: str, answer: str, request: str = "Answer the question.", docs=()):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch("t", agent, request, list(docs))
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def engine_errors(rc) -> list:
    return [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


@pytest.mark.parametrize("tid", STEM_TASKS)
def test_a_genuine_round7_stem_answer_carries_no_engine_error(tid):
    it = SPEC[tid]
    docs = [SuppliedText(**t) for t in it.get("supplied_texts", [])]
    if it.get("peer_of"):
        peer = SPEC[it["peer_of"]]
        docs.append(SuppliedText(document_id=f"peer:{it['peer_of']}", title="peer report", author=peer["agent_id"], text=peer["response_text"]))
    rc = receive(it["subject"], it["response_text"], it["question"], docs)
    assert not engine_errors(rc), [f.message[:200] for f in engine_errors(rc)]


def test_a_thousands_group_inside_bracketed_arithmetic_is_one_number():
    assert [t.text for t in lex("(1,000 ÷ 2^10 = 0.98)").tokens if t.kind == "NUM"] == ["1,000", "2", "10", "0.98"]
    assert [t.text for t in lex("(2 × 1,000)").tokens if t.kind == "NUM"] == ["2", "1,000"]
    # a list or a pair stays separate numbers, as before
    for pair, nums in (("[100,200]", ["100", "200"]), ("(1,000)", ["1", "000"]), ("(3,000, 4,000)", ["3", "000", "4", "000"])):
        assert [t.text for t in lex(pair).tokens if t.kind == "NUM"] == nums, pair
    assert not engine_errors(receive("Computer Science", "That is 10 passes (1,000 ÷ 2^10 = 0.98)."))
    [slip] = engine_errors(receive("Computer Science", "That is 10 passes (1,000 ÷ 2^10 = 0.68)."))
    assert "1,000 ÷ 2^10 = 0.68" in slip.message


def test_a_stated_value_with_its_uncertainty_is_a_band_not_two_values():
    assert not engine_errors(receive("Physics", "t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹"))
    [slip] = engine_errors(receive("Physics", "t = 0 h: 1620 − 20 = 4600 ± 32 counts min⁻¹"))
    assert "1620 − 20 = 4600 ± 32" in slip.message
    assert engine_errors(receive("Physics", "t = 8 h: 820 − 20 = 900 ± 16 counts min⁻¹"))  # 800 lies outside 900 ± 16
    # a ± on both sides writes two values of a formula: both sign choices must hold, as before
    assert not engine_errors(receive("Mathematics: Analysis and Approaches", "(2 ± 4)/2 = 1 ± 2"))
    assert engine_errors(receive("Mathematics: Analysis and Approaches", "(2 ± 4)/2 = 1 ± 3"))


def test_a_power_written_after_a_value_belongs_to_the_run():
    text = "800 = 1600 e^(−8k)  M1"
    doc = build_document(text, None, "mathematics_aa")
    assert [text[r.start:r.end] for r in doc.relations] == ["800 = 1600 e^(−8k)"]
    assert not any(r.is_check for r in doc.relations)
    assert not engine_errors(receive("Mathematics: Analysis and Approaches", "800 = 1600 e^(−8k)  M1\ne^(−8k) = 1/2"))


def test_a_line_that_substitutes_into_the_preceding_relation_reads_the_written_values():
    genuine = "For resistors in parallel: 1/R = 1/R₁ + 1/R₂\n1/R = 1/4.0 Ω + 1/6.0 Ω = 0.250 Ω⁻¹ + 0.167 Ω⁻¹ = 0.417 Ω⁻¹\nR = 2.4 Ω"
    assert not engine_errors(receive("Physics", genuine))
    doc = build_document(genuine, None, "physics")
    assert {b.value for b in doc.substitutions["R_1"]} == {4} and {b.value for b in doc.substitutions["R_2"]} == {6}
    # the same line under a formula written wrongly does not follow from it
    [step] = engine_errors(receive("Physics", genuine.replace("1/R = 1/R₁", "4/R = 1/R₁")))
    assert set(step.claim_ids) == {"s1.1", "s1.2"} and "stem_algebra" in step.message


def test_a_symbol_reused_in_a_later_part_for_a_value_the_request_gives_is_read_there():
    request = ("Two resistors of 4.0 ohm and 6.0 ohm are in parallel across a 12 V battery. (a) Calculate the total resistance. [2] "
               "(b) Calculate the power dissipated in the 6.0 ohm resistor. [2]")
    answer = "(a) [2]\nR = 2.4 Ω\n\n(b) [2]\nThe potential difference is 9.93 V.\nP = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W"
    assert not engine_errors(receive("Physics", answer, request))
    # a value the request does not give is still checked against the binding of the other part
    wrong = engine_errors(receive("Physics", answer.replace("/ 6.0 Ω = 16.4 W", "/ 9.0 Ω = 10.96 W"), request))
    assert wrong and any("stem_substitution" in f.message and "9.0 Ω" in f.message for f in wrong)


def test_the_order_relations_of_a_sentence_under_a_condition_are_no_checks_against_stated_values():
    answer = ("(a) At t = 1: a = 6 − 6(1) = 0\n\n(b) At rest means v = 0:\nt = 0 or t = 2\nBoth values lie in 0 ≤ t ≤ 3.\n\n"
              "(c) From (b), v = 3t(2 − t). For 0 < t < 2, both 3t and 2 − t are positive, so v > 0.\nFor 2 < t ≤ 3, 2 − t is negative, so v < 0.")
    doc = build_document(answer, None, "mathematics_aa")
    conditional = [r for r in doc.relations if answer[r.start:r.end] in ("v > 0", "2 < t", "v < 0", "0 < t", "t < 2")]
    assert conditional and all(r.outcome == "context" for r in conditional)
    stated = [r for r in doc.relations if answer[r.start:r.end] in ("0 ≤ t", "t ≤ 3") and r.statement_ids[0].startswith("s2")]
    assert stated and all(r.kind == "cmp" and r.outcome == "check" for r in stated)  # a claim about the stated values stays a check
    assert not engine_errors(receive("Mathematics: Analysis and Approaches", answer))
    # an order relation that is no condition is still checked against the stated values
    assert engine_errors(receive("Mathematics: Analysis and Approaches", "t = 1 so a = 6 − 6t = 0.\nTherefore t > 3."))


def test_a_prose_restatement_restates_the_last_chain_that_computes_a_value():
    kept = build_document("a = (20 − 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 5.0 m s⁻².", None, "physics")
    assert [r.kind for r in kept.checks].count("res") == 1
    [slip] = engine_errors(receive("Physics", "a = (20 − 0)/4.0 = 5.0 m s⁻². The acceleration is therefore 6.0 m s⁻²."))
    assert "stem_result" in slip.message
    older = build_document("The value is 4000(1.036)^{12} = 6114.73.\n\nSolving, n > 11.28\nThe value first exceeds 6000 after 12 whole years, so the answer is 12 years.",
                           None, "mathematics_ai")
    assert not [r for r in older.relations if r.kind == "res"]          # the last chain ends on an order relation: nothing restated
    stated = build_document("The passes test mid = 4, 1 and 2. The loop ends, so 20 is not in the list and the function returns -1.", None,
                            "computer_science")
    assert not [r for r in stated.relations if r.kind == "res"]         # 'mid = 4' states a value, it computes none
