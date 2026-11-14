"""Translation behaviour found wanting by the round-9 clearance overseers (integrated round c2), fixed by the core fixer:

* critical: 18 encodings that never compute the claim's own calculation were displayed ENTAILED on an invented anchor
  premise 'unit = 1' ("one equals one", arithmetic_fact) that a stray '1' anywhere in the task 'verified'. A task-authority
  premise that only gives a symbol the structural value 0 or 1 is no longer validated by a figure found anywhere in the
  task (only a located excerpt verifies it), so the anchor that restates a conclusion conjunct is the writer's own and the
  claim is withheld (E112) instead of ENTAILED on an invented premise listed as task data;
* critical: a conclusion that checks a fraction the translation computed itself (-20800/943 for the written
  "(294.0 − 377.2) ÷ 377.2 × 100", ge-t15 g2.5, g3.2) is named an introduced figure (AMBIGUOUS_TRANSLATION);
* critical: a premise that is the conclusion scaled by figures the translation computed itself (ph-t15 s2.4: "6000 × vsq =
  54096", general knowledge, proved "vsq = 9.016" for the claim "v² = 2 × 9.8 × 0.46 = 9.016", which the transfer
  auditor confirms circular, OVS-TRN-006) restates it (rule unstated-scaling): the claim is withheld (E112);
* critical: a written calculation none of whose operands the encoding encodes (ph-t15 s3.3: "(1.2 × 10⁴ kg)(3.0 m s⁻¹) +
  (8.0 × 10³ kg)(0) = ..." encoded as "36000 = 20000 × v", the next line's figures) is flagged
  ``unencoded_calculation`` (AMBIGUOUS_TRANSLATION), never displayed ENTAILED;
* minor: the figure reader now reads a LaTeX fraction ("\\frac{45}{11}" is 45/11: mai-t15 m11.1 and m13.1 were withheld for
  a false introduced figure), a clock time ("09:30" is 9.5 hours) and a month named in full ("September" is month 9: hi-t15
  h1.8).

The recorded material is in ``tests/channel/data/c2_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TaskRecord
from epinoic_logic.translate.grounding import SourceText, check_problem_grounding
from epinoic_logic.translate.pipeline import introduced_conclusion_figures
from epinoic_logic.translate.pipeline import unencoded_calculation as _unencoded_calculation
from epinoic_logic.translate.quantities import figures_in

from ..channel.c2_core_support import C2, deliver
from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def outcome(rc, cid: str):
    return next(o for o in rc.outcomes if o.claim_id.split("@")[0] == cid.split("@")[0])


# ----------------------------------------------------------------------- critical: the 'unit = 1' anchors (E112)


@pytest.mark.parametrize("task,cid", [("mai-t15", "m14.1"), ("ge-p9c", "g3.1@geography-specialist")])
def test_an_anchor_one_equals_one_is_no_task_fact_and_the_claim_is_withheld(task, cid):
    hub, _ch, _reply, rc = deliver(task, translations={cid: C2["translations"][task][cid]})
    hub.close()
    o = outcome(rc, cid)
    assert o.display_status.value == "INVALID_FORMALIZATION" and o.translation.status.value == "INVALID_FORMALIZATION", (o.display_status, o.translation.diagnostics[:2])
    assert any("E112" in d and "p_unit" in d for d in o.translation.diagnostics)
    [check] = [c for c in o.translation.grounding_checks if c.target_id == "p_unit" and c.method == "numeric_in_task"]
    assert check.verified is None and "structural figure" in check.detail


def _premise_problem(value: str, *, kind: str = "arithmetic_fact", refs=None) -> Problem:
    g = {"kind": kind, "certainty": "established", **({"source_refs": refs} if refs else {})}
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "v", "sort": "Real", "meaning": "the quantity"}],
                                   "premises": [{"id": "pv", "expr": {"op": "eq", "left": {"op": "var", "name": "v"}, "right": {"op": "real", "value": value}},
                                                 "label": f"v = {value}", "grounding": g}],
                                   "conclusion": {"id": "c", "expr": {"op": "ge", "left": {"op": "var", "name": "v"}, "right": {"op": "real", "value": "0"}}}})


TASK = TaskRecord.of(task_id="t", request_id="r", text="Question 1 [1 mark]: the tank holds 5 litres; find the volume after 1 hour.", issued_by="router")


@pytest.mark.parametrize("value", ["1", "0", "-1"])
def test_a_structural_figure_found_anywhere_in_the_task_never_validates_a_task_premise(value):
    _p, checks = check_problem_grounding(_premise_problem(value), [], TASK)
    [c] = [x for x in checks if x.target_id == "pv"]
    assert c.verified is None and "structural figure" in c.detail


def test_controls_a_task_figure_still_validates_and_a_located_excerpt_still_verifies_a_one():
    _p, checks = check_problem_grounding(_premise_problem("5"), [], TASK)
    assert any(c.target_id == "pv" and c.verified is True for c in checks)
    doc = SuppliedText(document_id="d", text="Each plot has an area of 1 m² and the tank holds 5 litres.")
    p, _checks = check_problem_grounding(_premise_problem("1", kind="supplied_text", refs=[{"document_id": "d", "excerpt": "an area of 1 m²"}]), [doc], TASK)
    assert p.premises[0].grounding.verified is True


def test_a_faithful_step_check_is_untouched():
    """maa-t15 m7.3 ('x = −5' from '2x + 2 = x − 3 (from 7.2)'): the claim's own step, decided as before."""
    hub, _ch, _reply, rc = deliver("maa-t15", translations={"m7.3": C2["translations"]["maa-t15"]["m7.3"]})
    hub.close()
    assert outcome(rc, "m7.3").display_status.value == "ENTAILED"


# -------------------------------------------- critical: a premise scaled by figures the translation computed itself (E112)


def _scaled_problem(premise: tuple[str, str] = ("6000", "54096"), kind: str = "general_knowledge") -> Problem:
    vsq = {"op": "var", "name": "vsq"}
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "vsq", "sort": "Real", "meaning": "square of the speed at the bottom of the slope"}],
                                   "premises": [{"id": "s24-energy", "label": "energy balance with the scenario values",
                                                 "expr": {"op": "eq", "left": {"op": "mul", "args": [{"op": "real", "value": premise[0]}, vsq]},
                                                          "right": {"op": "real", "value": premise[1]}},
                                                 "grounding": {"kind": kind, "certainty": "established"}}],
                                   "conclusion": {"id": "c", "expr": {"op": "eq", "left": vsq, "right": {"op": "real", "value": "9.016"}}}})


S24 = "Substitution: v² = 2 × 9.8 m s⁻² × 0.46 m = 9.016 m² s⁻²"


def test_ph_t15_s2_4_a_premise_scaled_by_figures_no_source_states_is_the_claim_assumed():
    """The recorded ph-t15 s2.4 encoding: withheld as circular (E112, rule unstated-scaling), never displayed ENTAILED."""
    hub, _ch, _reply, rc = deliver("ph-t15", translations={"s2.4": C2["translations"]["ph-t15"]["s2.4"]})
    hub.close()
    o = outcome(rc, "s2.4")
    assert o.display_status.value == "INVALID_FORMALIZATION" and o.translation.status.value == "INVALID_FORMALIZATION", (o.display_status, o.translation.diagnostics[:2])
    assert any("E112" in d and "s24-energy" in d and "unstated-scaling" in d for d in o.translation.diagnostics), o.translation.diagnostics[:2]


def test_the_unstated_scaling_rule_reads_only_figures_no_source_states():
    from epinoic_logic.translate.pipeline import unstated_values
    from epinoic_logic.translate.restatement import semantic_restatement
    claim = SourceText("claim", "c", S24)
    found = semantic_restatement(_scaled_problem(), claim_text=S24, unstated=unstated_values([claim]))
    assert found is not None and found.kind == "full" and found.premises == ("s24-energy",) and "unstated-scaling" in found.how[0][1]
    # controls: without the sources (the rule's earlier reading) nothing is named; a source that states the premise's figures
    # makes it a derivation the engine checks; a premise a check located in a supplied text is data, never the claim assumed
    # (an unverified arithmetic_fact is the writer's own, as general knowledge is);
    # and the claim's own computation (2 × 9.8 × 0.46, figures the claim states) is never read as a restatement
    assert semantic_restatement(_scaled_problem(), claim_text=S24) is None
    stated = SourceText("supporting_claim", "s2.3", "Energy: 6000 kg × v² = 54096 J for the wagon.")
    assert semantic_restatement(_scaled_problem(), claim_text=S24, unstated=unstated_values([claim, stated])) is None
    assert semantic_restatement(_scaled_problem(kind="supplied_text"), {"s24-energy"}, claim_text=S24, unstated=unstated_values([claim])) is None
    assert semantic_restatement(_scaled_problem(kind="arithmetic_fact"), claim_text=S24, unstated=unstated_values([claim])) is not None
    computed = _scaled_problem().model_copy(update={"premises": [_scaled_problem().premises[0].model_copy(update={"expr": Problem.model_validate({
        "problem_id": "q", "request_id": "r", "claim_id": "c", "query": "consistency", "symbols": [{"name": "vsq", "sort": "Real"}],
        "premises": [{"id": "x", "expr": {"op": "eq", "left": {"op": "var", "name": "vsq"}, "right": {"op": "mul", "args": [
            {"op": "real", "value": "2"}, {"op": "real", "value": "9.8"}, {"op": "real", "value": "0.46"}]}}}]}).premises[0].expr})]})
    assert semantic_restatement(computed, claim_text=S24, unstated=unstated_values([claim])) is None


# ----------------------------------- critical: a written calculation none of whose operands the encoding encodes


S33 = "(1.2 × 10⁴ kg)(3.0 m s⁻¹) + (8.0 × 10³ kg)(0) = (1.2 × 10⁴ kg + 8.0 × 10³ kg)v"


def _momentum_problem(left: dict, right: dict) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "v", "sort": "Real"}, {"name": "p_before", "sort": "Real"}],
                                   "premises": [{"id": "pb", "expr": {"op": "eq", "left": {"op": "var", "name": "p_before"}, "right": left}}],
                                   "conclusion": {"id": "c", "expr": {"op": "eq", "left": {"op": "var", "name": "p_before"}, "right": right}}})


def test_ph_t15_s3_3_a_calculation_whose_operands_are_not_encoded_is_no_verdict():
    """The recorded ph-t15 s3.3 encoding checks the next line's figures (36000 = 20000 v) with the products asserted, never
    the written calculation: AMBIGUOUS_TRANSLATION with the unencoded_calculation flag, not ENTAILED."""
    hub, _ch, _reply, rc = deliver("ph-t15", translations={"s3.3": C2["translations"]["ph-t15"]["s3.3"]})
    hub.close()
    o = outcome(rc, "s3.3")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION", (o.display_status, o.translation.diagnostics[:3])
    assert any(f.code == "unencoded_calculation" for f in o.translation.interpretation.ambiguity_flags)


def test_the_unencoded_calculation_rule_reads_only_a_calculation_none_of_whose_operands_is_encoded():
    from epinoic_logic.translate.pipeline import unencoded_calculation
    R = lambda v: {"op": "real", "value": v}
    V = lambda n: {"op": "var", "name": n}
    computed = _momentum_problem(R("36000"), {"op": "mul", "args": [R("20000"), V("v")]})
    flag = unencoded_calculation(computed, _claim(S33))
    assert flag is not None and flag.code == "unencoded_calculation" and "3.0 m s⁻¹" in flag.message
    # controls: the written operands encoded (the engine computes the calculation); a Boolean encoding (no figure: the notes
    # name the figures); a claim that writes no calculation; one operand of the calculation encoded as a bare figure; and the
    # calculation computed from the figures its operands come from (c2 bm-t15 g6.2: "$90,000 + $16,000" as 0.6 × 150000 +
    # 0.4 × 40000; c2 ch-p9b s3.1: "144.12 + 22.22 + 176.00" as 12 × mass_c + ... beside "mass_c = 12.01"), which the engine
    # computes
    faithful = _momentum_problem({"op": "add", "args": [{"op": "mul", "args": [R("12000"), R("3.0")]}, {"op": "mul", "args": [R("8000"), R("0")]}]},
                                 {"op": "mul", "args": [{"op": "add", "args": [R("12000"), R("8000")]}, V("v")]})
    assert unencoded_calculation(faithful, _claim(S33)) is None
    boolean = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment", "symbols": [{"name": "kept", "sort": "Bool"}],
                                      "premises": [{"id": "k", "expr": V("kept")}], "conclusion": {"id": "c", "expr": V("kept")}})
    assert unencoded_calculation(boolean, _claim(S33)) is None
    assert unencoded_calculation(computed, _claim("The coupled wagons move off at 1.8 m s⁻¹ in the original direction.")) is None
    one = _momentum_problem(R("12000"), {"op": "mul", "args": [R("20000"), V("v")]})
    assert unencoded_calculation(one, _claim(S33)) is None
    deeper = _momentum_problem({"op": "add", "args": [{"op": "mul", "args": [R("0.6"), R("150000")]}, {"op": "mul", "args": [R("0.4"), R("40000")]}]}, R("106000"))
    assert unencoded_calculation(deeper, _claim("EV(A) = $90,000 + $16,000 = $106,000")) is None
    # the figures taken from elsewhere (none the claim states) are flagged; an encoding that checks the result the claim states
    # ("$106,000", as tests/translate/test_evidence_diagnostics.py reads "120 × $8 = $960, so ...") is rule result-asserted's
    ev = _claim("EV(A) = $90,000 + $16,000 = $106,000")
    assert unencoded_calculation(_momentum_problem(R("150000"), R("40000")), ev) is not None
    assert unencoded_calculation(_momentum_problem(R("150000"), R("106000")), ev) is None
    molar = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                    "symbols": [{"name": "mass_c", "sort": "Real"}, {"name": "mass_h", "sort": "Real"}],
                                    "premises": [{"id": "c", "expr": {"op": "eq", "left": V("mass_c"), "right": R("12.01")}},
                                                 {"id": "h", "expr": {"op": "eq", "left": V("mass_h"), "right": R("1.01")}}],
                                    "conclusion": {"id": "m", "expr": {"op": "eq", "left": {"op": "add", "args": [
                                        {"op": "mul", "args": [R("12"), V("mass_c")]}, {"op": "mul", "args": [R("22"), V("mass_h")]}]}, "right": R("166.34")}}})
    assert unencoded_calculation(molar, _claim("M = 144.12 + 22.22 = 166.34 g mol⁻¹")) is None
    # c1 maa-p8b m8.12: "20√3 cm s⁻¹" as 0.2 × s3 beside the bounds 1.7320 < s3 < 1.7321 is the calculation computed in SI
    root = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "s3", "sort": "Real"}, {"name": "v", "sort": "Real"}],
                                   "premises": [{"id": "b", "expr": {"op": "and", "args": [{"op": "gt", "left": V("s3"), "right": R("1.7320")},
                                                                                        {"op": "lt", "left": V("s3"), "right": R("1.7321")}]}},
                                                {"id": "v", "expr": {"op": "eq", "left": V("v"), "right": {"op": "mul", "args": [R("0.2"), V("s3")]}}}],
                                   "conclusion": {"id": "c", "expr": {"op": "lt", "left": V("v"), "right": R("0.3465")}}})
    assert unencoded_calculation(root, _claim("Here 20√3 cm s⁻¹ = (√3/5) m s⁻¹ ≈ 0.346 m s⁻¹.")) is None


# -------------------------------------------------------- critical: a fraction the translation computed itself


def _conclusion_problem(value: str) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "pct", "sort": "Real"}],
                                   "premises": [{"id": "d", "expr": {"op": "eq", "left": {"op": "var", "name": "pct"}, "right": {"op": "real", "value": value}}}],
                                   "conclusion": {"id": "c", "expr": {"op": "and", "args": [
                                       {"op": "ge", "left": {"op": "real", "value": value}, "right": {"op": "real", "value": "-22.15"}},
                                       {"op": "lt", "left": {"op": "real", "value": value}, "right": {"op": "real", "value": "-22.05"}}]}}})


def test_a_conclusion_fraction_no_source_states_is_an_introduced_figure():
    claim = SourceText("claim", "g2.5", "Coal supply fell by 22.1%, from 377.2 PJ in 2005 to 294.0 PJ in 2025.")
    assert introduced_conclusion_figures(_conclusion_problem("-20800/943"), [claim]) == ["-20800/943"]
    # controls: a decimal is no such figure, and a fraction a source states (in digits or in LaTeX) is stated
    assert introduced_conclusion_figures(_conclusion_problem("-22.1"), [claim]) == []
    assert introduced_conclusion_figures(_conclusion_problem("45/11"), [SourceText("claim", "m", "so x = \\frac{45}{11}")]) == []
    assert introduced_conclusion_figures(_conclusion_problem("45/11"), [SourceText("claim", "m", "so x = 45/11")]) == []


# --------------------------------------------------------------------------- minor: the figure reader's new forms


@pytest.mark.parametrize("text,value,unit", [
    ("so x = \\frac{45}{11} km", Fraction(45, 11), "km"), ("x = \\dfrac{52}{11}", Fraction(52, 11), None),
    ("the lag ran from 09:30", Fraction(19, 2), "h"), ("the invasion began in August, not September", Fraction(9), None),
])
def test_the_figure_reader_reads_latex_fractions_clock_times_and_months(text, value, unit):
    figs = figures_in(SourceText("claim", "c", text))
    assert any(f.value == value and f.unit == unit for f in figs), [(f.numeral, f.value, f.unit) for f in figs]


@pytest.mark.parametrize("text", ["May I add a note", "the ratio 1:2:3", "at 12:30:15", "25:61"])
def test_controls_no_month_or_clock_time_is_read_where_none_is_written(text):
    figs = figures_in(SourceText("claim", "c", text))
    assert not any(f.unit == "h" for f in figs) and not any(f.numeral == "May" for f in figs)


# ------------------------------------------------------------------------------------- the new readers are linear


def _entries(text: str):
    yield "figures_in", lambda: figures_in(SourceText("claim", "c", text))
    yield "figures_in(frac)", lambda: figures_in(SourceText("claim", "c", "\\frac{1}{2} " + text + " \\frac{" * 100))
    yield "figures_in(clock)", lambda: figures_in(SourceText("claim", "c", "09:30 " + text + " 1:2" * 100))
    yield "introduced_conclusion_figures", lambda: introduced_conclusion_figures(_conclusion_problem("-20800/943"), [SourceText("claim", "c", text)])
    yield "unencoded_calculation", lambda: _unencoded_calculation(_momentum_problem({"op": "real", "value": "36000"}, {"op": "real", "value": "20000"}),
                                                                   _claim("2 × 3 = " + text + " = 4 × 5" * 40))


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c2_translate_readers(shape):
    """The readers this clearance added to the translation layer, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("text", ["\\frac{1}{" * 3000 + "x", "09:3" * 5000, "September " * 2000, "1:2:" * 5000])
def test_the_new_translate_readers_are_linear_on_their_own_worst_inputs(text):
    assert not sweep(_entries, texts={"worst": text})


# ----------------------------------------------- critical: a conditional conclusion for a categorical claim (fidelity)


def _claim(text: str):
    from epinoic_logic.translate.contracts import ClaimRecord
    return ClaimRecord(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Chemistry", task_type="short_answer", claim_id="c", claim_text=text,
                       claim_role="point", materiality="material")


def _link_problem() -> Problem:
    V = lambda n: {"op": "var", "name": n}
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "shift_left", "sort": "Bool"}, {"name": "kc_falls", "sort": "Bool"}],
                                   "premises": [{"id": "p1", "expr": {"op": "implies", "left": V("shift_left"), "right": V("kc_falls")}}],
                                   "conclusion": {"id": "c", "expr": {"op": "implies", "left": V("shift_left"), "right": V("kc_falls")}}})


def test_ch_t15_s15_4_a_categorical_consequence_encoded_as_a_link_is_named():
    from epinoic_logic.translate.pipeline import conditional_conclusion
    flag = conditional_conclusion(_link_problem(), _claim("Fewer products and more reactants are present at equilibrium, so Kc falls."))
    assert flag is not None and flag.code == "conditional_conclusion"
    # controls: a conditional claim is faithfully a link, and a categorical conclusion is no link
    assert conditional_conclusion(_link_problem(), _claim("If the temperature rises, Kc falls.")) is None
    assert conditional_conclusion(_link_problem(), _claim("A lower temperature would give a higher yield, so the rate would be slow.")) is None
    categorical = _link_problem().model_copy(update={"conclusion": _link_problem().conclusion.model_copy(update={"expr": _link_problem().premises[0].expr.right})})
    assert conditional_conclusion(categorical, _claim("Fewer products are present, so Kc falls.")) is None


def test_the_recorded_s15_4_encoding_is_not_displayed_as_a_verdict():
    hub, _ch, _reply, rc = deliver("ch-t15", translations={"s15.4": C2["translations"]["ch-t15"]["s15.4"]})
    hub.close()
    o = outcome(rc, "s15.4")
    assert o.display_status.value == "AMBIGUOUS_TRANSLATION" and any(f.code == "conditional_conclusion" for f in o.translation.interpretation.ambiguity_flags)


def test_the_task_record_is_within_every_formalizations_scope():
    """translate_v3 rule 9 grounds a task fact in the document id 'task': never INT-HANDOFF-004 (ess-p9c s2.1 ... s3.4)."""
    from epinoic_logic.integrity import WorkPlan, run_integrity_checks
    plan = WorkPlan(plan_id="p", request_id="r", task_id="t", subject="ESS", task_type="short_answer", selected_agent_ids=["a"], allowed_document_ids=["doc"])

    def grounded_in(doc: str) -> Problem:
        return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "consistency",
                                       "symbols": [{"name": "x", "sort": "Real"}],
                                       "premises": [{"id": "p1", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "5"}},
                                                     "grounding": {"kind": "task_setting", "source_refs": [{"document_id": doc, "excerpt": "5"}]}}]})
    assert "INT-HANDOFF-004" not in [f.code for f in run_integrity_checks(plan, [], formalized={"c": grounded_in("task")}).findings]
    assert "INT-HANDOFF-004" in [f.code for f in run_integrity_checks(plan, [], formalized={"c": grounded_in("elsewhere")}).findings]


def test_a_figure_another_claim_of_the_report_states_is_not_introduced():
    """c1 bug r8-19 (c2 ch-t15 s15.1): a figure the report states in a claim other than the supporting ones is the report's own,
    never an introduced figure that withholds the verdict."""
    hub, _ch, _reply, rc = deliver("ch-t15", translations={"s15.1": C2["translations"]["ch-t15"]["s15.1"]})
    hub.close()
    o = outcome(rc, "s15.1")
    assert not [f for f in o.translation.interpretation.ambiguity_flags if f.code == "introduced_figure"], o.translation.diagnostics[:3]
