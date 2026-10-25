"""STEM repair 1: the independent test of the overseer's STEM completion found STEM faults the translator's reading did not
see, and one false alarm on correct working. Each is fixed at its cause in the STEM front end, for its whole class, and every
new reading has a clean control (correct working is never flagged):

* units: a Latin SI prefix written before a Greek unit symbol (``kΩ``, ``MΩ``, ``mΩ``) is one prefixed unit (the lexer reads
  the Greek letter as a token of its own, so ``2.4 Ω = 0.0024 kΩ`` was read ``2.4 Ω = 0.0024`` and failed); English words a
  rare prefix reads as a unit (``as``, ``am``, ``at``) are no units after a number; ``counts`` is a count (``counts min⁻¹``);
* dimensions (rule ``bare-factor``): a bare number beside a quantity counts as a pure factor unless the answer gives it a
  unit, so ``0.693 × 8.0 h = 5.5 h⁻¹`` is ST-DIM-001;
* receipts: a combination or permutation count (``⁵C₂``, ``5C2``, ``nCr``, ``C(5, 2)``) is named undecided (ST-UNDEC-001),
  never silently unchecked;
* rounding (rules ``rounding-cue`` and ``inline-restatement``): a value restated with a rounding the prose states, or after
  ", so" on the line of working, is checked against the chain's value, with the stated rounding as its half-width;
* givens: a quantity named by the word before it in the request (``a battery of emf 12 V``) is read, so a Given that
  contradicts it is named on the Given;
* prose working (rules ``named-change`` and ``table-data``): the value a change starts from is set against the value stated
  for the quantity it names, and a value the prose takes from a supplied table against the table's cells (warnings: the
  quantity and the rows are a reading);
* formulas (rule ``related-statements``): a failed substitution names the statement whose stated value it contradicts too,
  so a wrong formula applied consistently is named where its value is stated.
"""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.datatables import parse_data_tables
from epinoic_logic.stem.lexer import COMBINATION, PERMUTATION, combination_at
from epinoic_logic.stem.units import GREEK_PREFIXABLE, english_word_atom, is_unit_atom, lookup_atom, prefixed_greek_unit
from epinoic_logic.translate.contracts import SuppliedText

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-1-test-key-0123456789abcdef"


def results(text: str, profile: str = "physics", request: str = None, data: tuple = ()):
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    out = {}
    for pc in plan.checks:
        res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy))
        out[pc.check_id] = (pc, res.status.value)
    return doc, plan, out


def statuses(text: str, profile: str = "physics", **kw) -> dict[str, str]:
    return {cid: st for cid, (_pc, st) in results(text, profile, **kw)[2].items()}


def codes(text: str, profile: str = "physics", **kw) -> list[str]:
    doc, plan, _ = results(text, profile, **kw)
    return [f.code for f in doc.findings] + [f.code for f in plan.findings]


def receive(subject: str, answer: str, request: str = "Answer the question.", docs=()):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent],
                           allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch("t", agent, request, list(docs))
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def recorded(tid: str) -> tuple[str, str, list[SuppliedText]]:
    it = SPEC[tid]
    return it["response_text"], it["question"], [SuppliedText(**t) for t in it.get("supplied_texts", [])]


# ============================================================================================ units
@pytest.mark.parametrize("line", ["R = 2400 Ω = 2.4 kΩ", "R = 2.2 kΩ = 2200 Ω", "R = 3.3 MΩ = 3300000 Ω", "R = 0.50 mΩ = 0.00050 Ω",
                                  "R = 2.4 Ω = 0.0024 kΩ", "R = 2.2kΩ = 2200 Ω", "R = 4.7 μΩ = 0.0000047 Ω", "R = 1.5 GΩ = 1500000000 Ω",
                                  "R = 4.7 kΩ = 4700 Ω"])
def test_a_prefixed_ohm_is_one_unit_and_a_correct_conversion_holds(line):
    got = statuses(line)
    assert got and set(got.values()) == {"ENTAILED"}, got
    assert not {"ST-UNDEC-002", "ST-UNIT-001"} & set(codes(line))


@pytest.mark.parametrize("line", ["R = 2.4 Ω = 0.024 kΩ", "R = 2.2 kΩ = 220 Ω", "R = 3.3 MΩ = 330000 Ω", "R = 0.50 mΩ = 0.0050 Ω"])
def test_a_wrong_prefixed_ohm_conversion_is_named(line):
    doc, plan, out = results(line)
    assert [st for _cid, (pc, st) in out.items() if pc.relation_kind == "cnv"] == ["COUNTEREXAMPLE"], out


def test_the_prefixed_ohm_class_and_its_bindings():
    assert GREEK_PREFIXABLE == frozenset({"Ω"})
    assert prefixed_greek_unit("k", "Ω") and prefixed_greek_unit("M", "Ω") and prefixed_greek_unit("m", "Ω") and prefixed_greek_unit("G", "Ω")
    assert not prefixed_greek_unit("x", "Ω") and not prefixed_greek_unit("k", "ε") and not prefixed_greek_unit("da", "Å")
    doc = build_document("x = 2.4 kΩ", None, "physics")
    [b] = doc.bindings["x"]
    assert b.unit is not None and b.unit.text == "kΩ" and b.unit.readings[0].factor == 1000
    assert statuses("I = 12 V / 2.4 kΩ = 0.0050 A") == {"stem-eq-1": "ENTAILED"}
    assert statuses("I = 12 V / 2.4 kΩ = 0.050 A") == {"stem-eq-1": "COUNTEREXAMPLE"}


def test_english_words_after_a_number_are_no_atto_prefixed_units():
    # the table keeps the atoms (tests/stem/test_units.py::test_atoms); a word written apart after a number is no unit
    assert is_unit_atom("as") and lookup_atom("as")[0].prefix == "a"
    assert all(english_word_atom(w) for w in ("as", "am", "at")) and not english_word_atom("ms")
    doc = build_document("x = 5 as before, so y = 2x = 10.", None, "ess")
    [b] = doc.bindings["x"]
    assert b.unit is None and b.number.value == 5
    for text, profile in (("The count falls to 5 at D and 22 at E.", "ess"), ("The value is 10 am in the morning.", "physics")):
        assert all(getattr(pv.node, "unit", None) is None for pv in build_document(text, None, profile).prose_values), text
    # a real unit after a value is still read, and a glued millisecond too
    assert statuses("t = 2.0 ms = 0.0020 s") == {"stem-cnv-1": "ENTAILED"}


def test_counts_is_a_count_so_a_count_rate_line_is_checked():
    # STEM repair 3 (rule half-lives): the power of ½ is also set against the 4 half-lives the prose states (stem-eq-2, after the arithmetic)
    assert statuses("32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹.") == {"stem-eq-1": "ENTAILED", "stem-eq-2": "ENTAILED"}
    assert statuses("32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 200 counts min⁻¹.") == {"stem-eq-1": "COUNTEREXAMPLE", "stem-eq-2": "ENTAILED"}
    assert statuses("t = 0 h: 1620 − 20 = 1600 ± 32 counts min⁻¹") == {"stem-eq-1": "ENTAILED"}


# ============================================================================================ dimensions: rule bare-factor
@pytest.mark.parametrize("line", ["λ = 0.693 × 8.0 h = 5.5 h⁻¹", "x = 2.0 s × 3.0 = 6.0 m", "y = 3.0 s × 2 = 6.0 s⁻¹", "f = 1 / 2.0 s = 0.50 s"])
def test_a_bare_factor_beside_one_quantity_gives_the_side_its_dimension(line):
    assert "ST-DIM-001" in codes(line), codes(line)


@pytest.mark.parametrize("line", ["λ = 0.693/8.0 h = 0.087 h⁻¹", "v = 72 km h⁻¹ ÷ 3.6 = 20 m s⁻¹", "F = 2.0 kg × 9.8 = 19.6 N",
                                  "v = 3.0 m s⁻¹. x = 2.0 s × 3.0 = 6.0 m", "a = 120 / 8 = 15 m s⁻¹", "V = 12 V − 4.14 × 0.50 = 9.9 V",
                                  "F = ma = 2.0 × 3.0 m s⁻² = 6.0 N", "E = ½ × 2.0 kg × (3.0 m s⁻¹)² = 9.0 J", "f = 1 / 0.020 s = 50 Hz",
                                  "P = 2 × 3.0 V × 1.5 A = 9.0 W"])
def test_a_bare_factor_that_a_stated_value_or_a_constant_explains_raises_nothing(line):
    assert "ST-DIM-001" not in codes(line), codes(line)


# ============================================================================================ receipts: combination counts
@pytest.mark.parametrize("text", ["⁵C₂ = 10", "5C2 = 10", "C(5, 2) = 10", "nCr = 10", "10C3 = 120", "ⁿCᵣ = n!/(r!(n − r)!)", "₅C₂ = 10", "C(n, k) = 10"])
def test_a_combination_count_is_named_undecided_never_silent(text):
    doc = build_document(f"The number of ways is {text}.", None, "mathematics_aa")
    undecided = [r for r in doc.relations if r.outcome == "undecided" and r.code == "ST-UNDEC-001"]
    assert undecided and any("binomial coefficient" in r.reason for r in undecided), [(r.kind, r.outcome, r.reason) for r in doc.relations]
    assert any(f.code == "ST-UNDEC-001" for f in doc.findings)


def test_a_permutation_count_and_the_latex_forms_are_named_too():
    assert combination_at("₅P₂ = 20", 0, 8) == (3, PERMUTATION) and combination_at("^{5}C_{2}", 0, 9, "latex") == (9, COMBINATION)
    doc = build_document("So $^{5}C_{2} = 10$ and there are ₅P₂ = 20 orders.", None, "mathematics_aa")
    reasons = [r.reason for r in doc.relations if r.outcome == "undecided"]
    assert any("binomial coefficient" in x for x in reasons) and any("permutation count" in x for x in reasons), reasons


@pytest.mark.parametrize("text, profile", [("The point C(2, 3) lies on the line.", "mathematics_aa"), ("C2H4 + 3O2 → 2CO2 + 2H2O", "chemistry"),
                                           ("H₂C₂O₄ is oxalic acid.", "chemistry"), ("x = 2.5C", "physics"),
                                           ("The cost is C(x, y) = 3x + 2y.", "mathematics_ai"), ("Let C(x, y) be a point on the circle.", "mathematics_aa"),
                                           ("The vertices are A(0, 0), B(4, 0) and C(4, 3), so AC = √(4² + 3²) = 5.", "mathematics_aa")])
def test_no_binomial_is_read_where_there_is_none(text, profile):
    doc = build_document(text, None, profile)
    assert not [r for r in doc.relations if "binomial" in r.reason or "permutation" in r.reason]


# ============================================================================================ rounding
CHAIN = "D = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4%\n"


@pytest.mark.parametrize("restated, status", [("To the nearest whole number, the decrease is 61%.", "COUNTEREXAMPLE"),
                                              ("To the nearest whole number, the decrease is 60%.", "ENTAILED"),
                                              ("The decrease is 60%, to 1 s.f.", "ENTAILED"),
                                              ("The decrease is 70%, to 1 s.f.", "COUNTEREXAMPLE"),
                                              ("Correct to 2 significant figures, the decrease is 60%.", "ENTAILED")])
def test_a_rounding_the_prose_states_is_checked_with_its_half_width(restated, status):
    doc, _plan, out = results(CHAIN + restated)
    res = [(pc, st) for _cid, (pc, st) in out.items() if pc.relation_kind == "res"]
    assert [st for _pc, st in res] == [status], out
    assert res[0][0].failure_severity == "error" and "rounded as the prose states" in res[0][0].description


CHAIN64 = "D = (9.6 − 3.42) ÷ 9.6 × 100 = 64.4%\n"


@pytest.mark.parametrize("restated, status", [("To 2 s.f., the decrease is 60%.", "COUNTEREXAMPLE"), ("To the nearest whole number, the decrease is 60%.", "COUNTEREXAMPLE"),
                                              ("To 1 s.f., the decrease is 60%.", "ENTAILED"), ("To the nearest whole number, the decrease is 64%.", "ENTAILED"),
                                              ("The decrease is 64%, to 2 s.f.", "ENTAILED"), ("Therefore the decrease is 60%.", "ENTAILED")])
def test_a_stated_rounding_says_which_zeros_of_a_whole_number_count(restated, status):
    # 64.4% is 64% to two significant figures and to the nearest whole number, 60% to one; without a stated rounding none of 60's
    # zeros count (h 5), as before
    out = results(CHAIN64 + restated)[2]
    assert [st for _cid, (pc, st) in out.items() if pc.relation_kind == "res"] == [status], out


def test_the_figure_of_a_rounding_phrase_is_no_restated_value():
    doc, _plan, out = results(CHAIN + "The answer, 60.4%, is 60% to 2 s.f.")
    assert [st for _cid, (pc, st) in out.items() if pc.relation_kind == "res"] == ["ENTAILED"]  # 60%, never the 2 of "2 s.f."


@pytest.mark.parametrize("line, status", [("P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "ENTAILED"), ("P = (9.93 V)² / 6.0 Ω = 16.4 W, so 17 W", "COUNTEREXAMPLE")])
def test_an_inline_restatement_after_so_is_checked(line, status):
    out = results(line)[2]
    assert [st for _cid, (pc, st) in out.items() if pc.relation_kind == "res"] == [status]


def test_a_consequence_after_so_is_no_restatement():
    out = results("F = 3.0 × 2.0 N = 6.0 N, so 12 N in total")[2]
    assert not [1 for _cid, (pc, _st) in out.items() if pc.relation_kind == "res"]


# ============================================================================================ givens stated in the request's words
def test_a_quantity_named_by_the_word_before_it_is_read_in_the_request():
    text, question, _docs = recorded("ph-t13")
    doc = build_document("Given: ε = 9.0 V.\n\n" + text, question, "physics")
    assert any(str(n.number.value) == "12" for n, _a, _b in doc.request.quantities if getattr(n, "unit", None) is not None)
    giv = [r for r in doc.checks if r.kind == "giv"]
    assert giv and giv[0].statement_ids == ("s1.1",)
    _doc, _plan, out = results("Given: ε = 9.0 V.\n\n" + text, request=question)
    assert [st for _c, (pc, st) in out.items() if pc.relation_kind == "giv"] == ["COUNTEREXAMPLE"]
    _doc, _plan, out = results("Given: ε = 12 V.\n\n" + text, request=question)
    assert [st for _c, (pc, st) in out.items() if pc.relation_kind == "giv"] == ["ENTAILED"]


# ============================================================================================ prose working: rule named-change
def test_the_start_of_a_change_restates_the_value_stated_for_the_quantity_it_names():
    text, question, _docs = recorded("ph-t13")
    doc, _plan, out = results(text, request=question)
    named = {pc.check_id: (pc.claim_ids, st, pc.failure_severity) for _c, (pc, st) in out.items() if pc.relation_kind == "res" and "named-change" in pc.description}
    # external resistance (s1.3), total resistance (s1.4), current (part b), terminal p.d. (part c): every one holds on the recorded answer
    assert sorted(v[0] for v in named.values()) == [("s1.3", "s5.2"), ("s1.4", "s5.2"), ("s2.2", "s5.3"), ("s3.2", "s5.4")]
    assert {v[1] for v in named.values()} == {"ENTAILED"} and {v[2] for v in named.values()} == {"warning"}
    doc, _plan, out = results(text.replace("rises from 2.4 Ω to 4.0 Ω", "rises from 2.9 Ω to 4.0 Ω"), request=question)
    bad = [(pc.claim_ids, st) for _c, (pc, st) in out.items() if pc.relation_kind == "res" and st != "ENTAILED"]
    assert bad == [(("s1.3", "s5.2"), "COUNTEREXAMPLE")]


def test_a_named_change_with_two_candidate_values_is_not_read():
    text = ("R = 2.4 Ω (the external resistance)\nR = 3.0 Ω (the external resistance)\n\nThe external resistance rises from 2.4 Ω to 4.0 Ω.")
    doc = build_document(text, None, "physics")
    assert not [r for r in doc.relations if r.named]


def test_a_named_change_reading_never_changes_a_claim_role():
    from epinoic_logic.adapters.stem_specialist import StemTextParser
    text, question, docs = recorded("ph-t13")
    rep = StemTextParser("physics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Physics", task_type="short_answer",
                                                               request_text=question, supplied_texts=docs)
    roles = {c.claim_id: c.claim_role for c in rep.claims}
    # the roles the parser gave the recorded answer before the named-change reading existed, every one unchanged
    assert roles == {"s1.1": "quantitative", "s1.2": "quantitative", "s1.3": "quantitative", "s1.4": "point", "s2.1": "analysis", "s2.2": "point",
                     "s3.1": "analysis", "s3.2": "point", "s4.1": "quantitative", "s4.2": "analysis", "s4.3": "point", "s5.1": "point",
                     "s5.2": "quantitative", "s5.3": "quantitative", "s5.4": "judgement"}, roles


# ============================================================================================ prose working: rule table-data
def test_the_supplied_tables_are_read_with_their_key_and_columns():
    _text, _q, docs = recorded("bi-t13")
    [table] = parse_data_tables(tuple(d.text for d in docs))
    assert [c.name for c in table.columns] == ["Temperature", "Mean oxygen uptake"] and table.columns[0].unit_text == "°C"
    assert table.row_for("25", Fraction(25)) is not None and table.value_columns() == [1]
    _text, _q, docs = recorded("ess-t13")
    [table] = parse_data_tables(tuple(d.text for d in docs))
    assert table.row_for("C", None) == 2 and len(table.value_columns()) == 3


def test_a_value_taken_from_the_supplied_table_is_set_against_its_cells():
    text, question, docs = recorded("bi-t13")
    data = tuple(d.text for d in docs)
    out = results(text, "biology", request=question, data=data)[2]
    giv = sorted((pc.claim_ids, st, pc.failure_severity) for _c, (pc, st) in out.items() if pc.relation_kind == "giv")
    # STEM repair 2 (rule table-operands) adds the two values part (a)'s working takes from the table (80 and 40, s2.1), each holding
    assert giv == [(("s2.1",), "ENTAILED", "warning")] * 2 + [(("s3.1",), "ENTAILED", "warning")] * 2 + [(("s3.2",), "ENTAILED", "warning")] * 2
    assert sorted((pc.claim_ids, st, pc.failure_severity) for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" not in pc.description) \
        == [(("s3.1",), "ENTAILED", "warning")] * 2 + [(("s3.2",), "ENTAILED", "warning")] * 2  # the four of rule table-data, exactly as before
    assert sum(1 for _c, (pc, _st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" in pc.description) == 2
    out = results(text.replace("an increase of 22 mm³", "an increase of 24 mm³"), "biology", request=question, data=data)[2]
    assert sorted(st for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" not in pc.description) == \
        ["COUNTEREXAMPLE", "ENTAILED", "ENTAILED", "ENTAILED"]
    assert [st for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" in pc.description] == ["ENTAILED"] * 2
    # the column is the one the clause names when the table has several
    text, question, docs = recorded("ess-t13")
    out = results(text.replace("to 8.4 mg dm⁻³ at B", "to 6.1 mg dm⁻³ at B"), "ess", request=question, data=tuple(d.text for d in docs))[2]
    # STEM repair 4: rule row-value adds the six values the answer gives at a site (each holding); rule table-data's two are as before.
    # STEM repair 10: rule row-value also reads 'the most nymphs (34)' and 'only 9' of part (b): eight, each holding
    assert sorted(st for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" not in pc.description
                  and "rule row-value" not in pc.description) == ["COUNTEREXAMPLE", "ENTAILED"]
    assert [st for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" in pc.description] == ["ENTAILED"] * 2
    assert [st for _c, (pc, st) in out.items() if pc.relation_kind == "giv" and "rule row-value" in pc.description] == ["ENTAILED"] * 8


def test_no_table_reading_without_a_table_or_for_a_row_it_does_not_have():
    text, question, docs = recorded("bi-t13")
    assert not [r for r in build_document(text, question, "biology").checks if r.kind == "giv"]  # no data: nothing read
    moved = text.replace("between 25 °C and 30 °C", "between 26 °C and 31 °C")
    out = results(moved, "biology", request=question, data=tuple(d.text for d in docs))[2]
    # the rows 26 and 31 are no rows: that change is not read (3 checks of rule table-data, and part (a)'s two of rule table-operands, STEM repair 2)
    assert len([1 for _c, (pc, _st) in out.items() if pc.relation_kind == "giv" and "rule table-operands" not in pc.description]) == 3
    assert len([1 for _c, (pc, _st) in out.items() if pc.relation_kind == "giv"]) == 5


def test_the_statements_are_the_same_with_and_without_the_supplied_data():
    text, question, docs = recorded("bi-t13")
    a = build_document(text, question, "biology")
    b = build_document(text, question, "biology", data=tuple(d.text for d in docs))
    assert [(s.id, s.start, s.end) for s in a.statements] == [(s.id, s.start, s.end) for s in b.statements]


# ============================================================================================ formulas: rule related-statements
def test_a_failed_substitution_names_the_statement_whose_value_it_contradicts():
    text, question, docs = recorded("ph-t13")
    planted = text.replace("V = ε − Ir\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = ε + Ir\nV = 12 V + (4.14 A × 0.50 Ω) = 14.1 V")
    doc = build_document(planted, question, "physics")
    sub = next(r for r in doc.checks if r.kind == "sub" and "9.93" in planted[r.start:r.end])
    assert sub.statement_ids == ("s4.3",) and "s3.2" in sub.related_ids
    rc = receive("Physics", planted, question, docs)
    failed = [f for f in rc.findings if f.code == "INT-SUBJ-001" and "P = (9.93 V)²" in f.message]
    assert failed and failed[0].claim_ids[0] == "s4.3" and "s3.2" in failed[0].claim_ids, [(f.claim_ids, f.message[:80]) for f in failed]
    # the formal check itself still names the statement it quotes
    fc = next(x for x in rc.formal_checks if x.formal_result_id == failed[0].formal_result_id)
    assert fc.claim_ids == ["s4.3"]


def test_a_substitution_names_no_related_statement_on_a_guess():
    # one statement states the value: it is named (both symbols, latest first)
    doc = build_document("I = 4.1 A\nR = 2.0 Ω\nV = IR = 4.5 A × 3.0 Ω = 13.5 V", None, "physics")
    assert [r.related_ids for r in doc.checks if r.kind == "sub"] == [("s1.2", "s1.1")]
    # two statements state a value of the symbol: which one the substitution contradicts is not read
    doc = build_document("I = 4.1 A\nThe current is I = 4.2 A.\nV = IR = 4.5 A × 2.0 Ω = 9.0 V", None, "physics")
    assert [r.related_ids for r in doc.checks if r.kind == "sub"] == [()]
    # the step's own clause states the value it uses (a Computer Science trace step): no earlier statement is named
    text, question, _docs = recorded("cs-t13")
    doc = build_document(text, question, "computer_science")
    assert [(r.statement_ids, r.related_ids) for r in doc.checks if r.kind == "sub"] == [(("s6.3", "s6.5"), ())]


def test_a_passing_or_unrelated_check_names_only_its_statement():
    text, question, docs = recorded("ph-t13")
    rc = receive("Physics", text, question, docs)
    assert not [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    rc = receive("Physics", "a = (20 - 0)/4.0 = 6.0 m s⁻²", "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration.")
    [f] = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert f.claim_ids == ["s1.1"]
