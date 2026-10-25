"""The engine layer of the argument diagnosis (``engine/argument.py``, rules argdiag-1): R0 and every engine-layer pattern
rule, with a positive case and a clean control for each code, and the bounds, the caps and determinism.

The positives and controls of the development cases run through the public hub (``tests/argdiag_hub.py``): the recorded
proposal is translated by the real translator, its groundings are checked in this process, and the diagnostics read here
are the engine's own, signed with its result. The constructed problems go to ``engine.verify`` directly. Every result
concerns the encoding only: a diagnostic says which shape the encoding has, never that a premise is true or false.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Optional

import pytest

from epinoic_logic.engine import SolverConfig, sign_result, verify, verify_signature
from epinoic_logic.engine import argument as argument_module
from epinoic_logic.engine import argument_cues as cues
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.named import is_blocking
from epinoic_logic.version import ARG_RULES_VERSION

from epinoic_logic.translate.grounding import check_problem_grounding

from .. import argdiag_cases as C
from ..argdiag_hub import run_case

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
KEY = b"argdiag-engine-test-key-0123456789abcd"


# ----------------------------------------------------------------------------------------------- builders

def V(name: str) -> dict:
    return {"op": "var", "name": name}


def NOT(a: dict) -> dict:
    return {"op": "not", "arg": a}


def AND(*args: dict) -> dict:
    return {"op": "and", "args": list(args)}


def OR(*args: dict) -> dict:
    return {"op": "or", "args": list(args)}


def IMP(a: dict, b: dict) -> dict:
    return {"op": "implies", "left": a, "right": b}


def IFF(a: dict, b: dict) -> dict:
    return {"op": "iff", "left": a, "right": b}


def CMP(op: str, a: dict, b: dict) -> dict:
    return {"op": op, "left": a, "right": b}


def R(value) -> dict:
    return {"op": "real", "value": str(value)}


def P(pid: str, expr: dict, label: str = "", kind: Optional[str] = "specialist_inference", verified: Optional[bool] = None, note: Optional[str] = None) -> dict:
    out: dict = {"id": pid, "expr": expr}
    if label:
        out["label"] = label
    if kind is not None:
        g: dict = {"kind": kind}
        if verified is not None:
            g["verified"] = verified
        if note:
            g["note"] = note
        out["grounding"] = g
    return out


def problem(premises: list[dict], conclusion: dict, symbols: dict[str, tuple[str, str]], *, label: str = "the point") -> Problem:
    """``symbols``: ``{name: (sort, meaning)}``. A Problem object is passed to the engine as the application holds it, so a
    ``verified`` flag here stands for a check of this process."""
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": "p-argdiag", "request_id": "req-argdiag", "claim_id": "c1", "query": "entailment",
        "symbols": [{"name": n, "sort": s, **({"meaning": m} if m else {})} for n, (s, m) in symbols.items()],
        "premises": premises, "conclusion": {"id": "C", "expr": conclusion, "label": label}})


def B(**meanings: str) -> dict[str, tuple[str, str]]:
    return {n: ("Bool", m) for n, m in meanings.items()}


def run(p: Problem, **kw):
    return verify(p, CFG, **kw)


def codes(result) -> dict[str, str]:
    """``{code: severity}`` of a result's named diagnostics."""
    return {d.code: d.severity for d in (result.named_diagnostics or [])}


def warnings(diags) -> list[str]:
    return sorted({d.code for d in diags if is_blocking(d)})


# ----------------------------------------------------------------------------------------------- the development cases

@lru_cache(maxsize=None)
def _delivered(case_id: str, mode: str):
    return run_case(case_id, mode)


def translated(case_id: str, mode: str = "text"):
    """The outcomes of the case's translated claims (a problem, or a translation refused as invalid)."""
    r = _delivered(case_id, mode)
    return [o for o in r.outcomes.values() if o.translation.problem is not None or o.translation.status.value == "INVALID_FORMALIZATION"]


def engine_named(case_id: str, mode: str = "text") -> list:
    """The engine's named diagnostics (the signed copy) of the case's one translated claim."""
    [out] = translated(case_id, mode)
    assert out.verification is not None and out.verification.argument_rules == ARG_RULES_VERSION
    return list(out.verification.named_diagnostics or [])


def by_code(diags, code: str):
    found = [d for d in diags if d.code == code]
    assert found, (code, [d.code for d in diags])
    return found[0]


def test_f01_no_reason_touches_the_point_ns_001():
    d = by_code(engine_named("f01_non_sequitur"), "ARG-NS-001")
    assert d.severity == "warning" and d.defect == "leap_in_logic" and d.derivation == "ir_structure"
    assert "no premise mentions any symbol of the point" in d.message


def test_f01b_the_writers_so_is_the_missing_link_link_001_at_info():
    diags = engine_named("f01b_non_sequitur_so")
    d = by_code(diags, "ARG-LINK-001")
    assert d.severity == "info" and d.assertion_ids == ["l_so"] and d.derivation == "engine_recheck"
    assert d.missing_link.text.startswith("if the Wall Street Crash of 1929 caused mass unemployment in Germany then the Treaty of Versailles")
    assert d.missing_link.expr == {"op": "implies", "left": {"op": "var", "name": "crash"}, "right": {"op": "var", "name": "versailles_main"}}
    assert len(d.derived_problem_digests) >= 2 and all(len(x) == 64 for x in d.derived_problem_digests)
    assert warnings(diags) == []                                       # structure alone cannot name f01b: info, never a warning
    [out] = translated("f01b_non_sequitur_so")
    assert out.display_status is S.ENTAILED and not out.release.permitted  # the status is unchanged, and it is not releasable


def test_f02_the_bridge_is_the_missing_link_ns_002():
    d = by_code(engine_named("f02_missing_link"), "ARG-NS-002")
    assert d.severity == "warning" and d.assertion_ids == ["e_dir", "l_vel_acc"]
    assert d.missing_link.text == "if the satellite's direction of motion changes continuously then the satellite's velocity changes"
    assert d.missing_link.expr == {"op": "implies", "left": {"op": "var", "name": "dir_changes"}, "right": {"op": "var", "name": "vel_changes"}}


def test_f03_affirming_the_consequent_counterexample_form():
    diags = engine_named("f03_affirming_consequent")
    d = by_code(diags, "ARG-AC-001")
    assert d.defect == "affirming_the_consequent" and d.derivation == "engine_recheck"
    assert d.missing_link.text == "if the observed cell has a cell wall then the observed cell is a plant cell"
    assert "ARG-INV-001" not in {x.code for x in diags}                 # the specific pattern, never the generic one


def test_f03b_affirming_the_consequent_writers_link_form():
    diags = engine_named("f03b_affirming_consequent_so")
    d = by_code(diags, "ARG-AC-001")
    assert d.assertion_ids == ["l_so", "l_plant_wall"] and "converse of the stated rule l_plant_wall" in d.message
    assert by_code(diags, "ARG-LINK-001").severity == "info"


def test_f04_denying_the_antecedent_counterexample_form():
    d = by_code(engine_named("f04_denying_antecedent"), "ARG-DA-001")
    assert d.defect == "denying_the_antecedent" and d.assertion_ids == ["l_raise_falls", "e_not_raise", "point"]
    assert d.missing_link.expr == IMP(NOT(V("raise")), NOT(V("falls")))


def test_f04b_not_p_so_not_q_denying_the_antecedent_writers_link_form():
    p = problem([P("l_rule", IMP(V("raise"), V("falls")), "if the central bank raises interest rates, then inflation falls", kind="general_knowledge", note="rule"),
                 P("e_not", NOT(V("raise")), "the central bank has not raised interest rates", kind="task_setting", verified=True),
                 P("l_so", IMP(NOT(V("raise")), NOT(V("falls"))), "the bank has not raised rates, so inflation will not fall", note="link: so")],
                NOT(V("falls")), {"raise": ("Bool", "the central bank raises interest rates"), "falls": ("Bool", "inflation falls")})
    r = run(p)
    assert r.status is S.ENTAILED and codes(r)["ARG-DA-001"] == "warning"
    d = by_code(r.named_diagnostics, "ARG-DA-001")
    assert d.assertion_ids == ["l_so", "l_rule"] and "inverse of the stated rule l_rule" in d.message


def test_f05_contradictory_premises_contra_001_names_the_core():
    d = by_code(engine_named("f05_contradictory_premises"), "ARG-CONTRA-001")
    assert d.severity == "error" and d.derivation == "engine_status" and set(d.assertion_ids) == {"e_endo", "l_endo_abs", "e_releases"}


def test_f06_the_refused_circular_translation_and_its_engine_form_circ_001():
    [out] = translated("f06_circular_direct")
    assert out.translation.status.value == "INVALID_FORMALIZATION"
    claim_layer = by_code(out.named_diagnostics, "ARG-CIRC-001")       # the claim form: the pipeline refused it as circular
    assert claim_layer.layer == "claim" and claim_layer.assertion_ids == ["s_restate"]
    # the engine form: the same problem verified directly carries E112, and the engine names it
    problem_data = out.translation.problem
    assert problem_data is None                                         # a refused translation keeps no problem
    p = problem([P("s_restate", V("unreliable"), "eyewitness testimony is unreliable")], V("unreliable"),
                B(unreliable="eyewitness testimony is unreliable"))
    r = run(p)
    assert "E112" in {d.code for d in r.diagnostics} and codes(r) == {"ARG-CIRC-001": "warning"}
    assert by_code(r.named_diagnostics, "ARG-CIRC-001").derivation == "engine_status"


def test_f07_a_joined_quotation_no_check_established_is_circular_circ_001():
    """f07 restates the point inside a quoted conjunction. Rewritten to the merged rule (the evidence family's grounding rule
    together with the authority rule of policy 2026.10-v5): the excerpt verifies one atom, so the conjunction that joins it
    to the writer's own proposition stays unverified, and the translator itself refuses the translation as circular (E112,
    INVALID_FORMALIZATION) with the claim form of ARG-CIRC-001 naming the restating premise. The engine form is kept: the
    recorded proposal, grounded by this process's checks, verified directly carries E112 and the engine names
    ARG-CIRC-001."""
    [out] = translated("f07_circular_joined_quote")
    assert out.translation.status.value == "INVALID_FORMALIZATION" and out.translation.problem is None
    assert any(": E112: circular: premise(s) ev_line_shows (quotation) restate" in t for t in out.translation.diagnostics)
    claim_layer = by_code(out.named_diagnostics, "ARG-CIRC-001")
    assert (claim_layer.layer, claim_layer.severity, claim_layer.assertion_ids) == ("claim", "warning", ["ev_line_shows"])
    case = C.load_case("f07_circular_joined_quote")
    proposal = C.proposal_for(case, "The speaker feels trapped.")
    grounded, _checks = check_problem_grounding(Problem.model_validate(proposal["problem"]), C.supplied_texts(case))
    [joined] = [pr for pr in grounded.premises if pr.id == "ev_line_shows"]
    assert joined.expr.op == "and" and joined.grounding.verified is None     # the excerpt locates, but verifies only an atom
    r = run(grounded)
    assert "E112" in {d.code for d in r.diagnostics}
    assert by_code(r.named_diagnostics, "ARG-CIRC-001").severity == "warning"


def _restated(kind: Optional[str], label: str, verified: Optional[bool] = None) -> Problem:
    return problem([P("p_yr", CMP("eq", V("yr"), {"op": "int", "value": "1817"}), label, kind=kind, verified=verified)],
                   CMP("eq", V("yr"), {"op": "int", "value": "1817"}), {"yr": ("Int", "the year the sonnet was written")},
                   label="the sonnet was written in 1817")


@pytest.mark.parametrize("kind, verified", [("specialist_inference", None), ("assumption", None), (None, None), ("quotation", None),
                                             ("arithmetic_fact", None), ("supplied_text", False)])
def test_a_restatement_by_the_writers_step_or_an_unchecked_quotation_or_figure_is_circular(kind, verified):
    r = run(_restated(kind, "the sonnet was written in 1817", verified))
    assert "E112" in {d.code for d in r.diagnostics} and codes(r)["ARG-CIRC-001"] == "warning"


@pytest.mark.parametrize("kind", ["task_setting", "supplied_text", "rubric_rule"])
def test_a_restated_task_or_text_premise_is_a_circle_unless_a_check_validated_it(kind):
    """Rewritten to the stricter authority rule of policy 2026.10-v5 (``engine.authority.assumed_grounding`` is ``not
    has_authority``: only a check in this process confers authority, for circularity too). A premise that only carries a
    task or text label restates the point with nothing a check established behind it: E112, and the engine names
    ARG-CIRC-001. The same premise validated by a check (``verified`` as this process sets it) is a transcription of the
    source: no E112 and no circularity code."""
    r = run(_restated(kind, "the sonnet was written in 1817"))
    assert "E112" in {d.code for d in r.diagnostics} and codes(r)["ARG-CIRC-001"] == "warning"
    checked = run(_restated(kind, "the sonnet was written in 1817", verified=True))
    assert "E112" not in {d.code for d in checked.diagnostics} and "ARG-CIRC-001" not in codes(checked)


def test_a_bare_fact_restated_from_subject_knowledge_is_a_record_not_a_circle():
    """A factual sentence ("Shelley's sonnet was written in 1817 ...") that the translation restates from facts it marks as
    subject knowledge offers no reason: E112 withholds the verdict, and the code records it at info."""
    r = run(_restated("general_knowledge", "the sonnet was written in 1817 (the poem's own date)"))
    assert "E112" in {d.code for d in r.diagnostics} and codes(r) == {"ARG-CIRC-001": "info"}
    reasoned = run(_restated("general_knowledge", "the sonnet was written in 1817, as shown by the fact that it was written in 1817"))
    assert codes(reasoned)["ARG-CIRC-001"] == "warning"                 # offered as its own reason: the circle


def test_f06b_paraphrase_circ_003():
    d = by_code(engine_named("f06b_circular_paraphrase"), "ARG-CIRC-003")
    assert d.assertion_ids == ["l_so", "s_cannot"] and d.derivation == "ir_glosses"
    assert "'eyewitness testimony cannot be relied upon'" in d.message


def test_f08_vacuous_vac_001():
    [out] = translated("f08_vacuous")
    assert out.display_status.value == "INVALID_FORMALIZATION"
    assert codes(out.verification) == {"ARG-VAC-001": "warning"}


def test_a_counterexample_over_no_premise_is_a_record_never_a_vacuous_argument():
    """E108 on a COUNTEREXAMPLE says only that nothing the claim rests on was encoded ("The turning point was 1930." with
    its reasons in other sentences): the code records it at info and accuses nothing."""
    r = run(problem([], V("turning"), B(turning="the turning point was 1930")))
    assert r.status is S.COUNTEREXAMPLE and "E108" in {d.code for d in r.diagnostics}
    assert codes(r) == {"ARG-VAC-001": "info"} and "the claim's reasons are not in the encoding" in r.named_diagnostics[0].message


def test_a_proof_over_no_premise_is_a_record_never_a_vacuous_argument():
    """E108 on an ENTAILED proof over no premise at all says only that the point is a logical truth: the requested identity
    "Show that A·B + A·NOT B = A" holds by its form, and no reason of the claim is in the encoding to go unused. The code
    records it at info; E108 still withholds the verdict (repair round 4, E2E-CS-IDENTITY-PROOF-NAMED-VACUOUS)."""
    identity = IFF(OR(AND(V("a"), V("b")), AND(V("a"), NOT(V("b")))), V("a"))
    r = run(problem([], identity, B(a="the Boolean variable A", b="the Boolean variable B"), label="A·B + A·NOT B = A"))
    assert r.status is S.ENTAILED and "E108" in {d.code for d in r.diagnostics}
    assert codes(r) == {"ARG-VAC-001": "info"} and "logical truth" in r.named_diagnostics[0].message
    # control: the same identity with a premise the proof does not use is still the vacuous argument, at warning
    idle = run(problem([P("p_law", IMP(V("a"), V("a")), "A implies A")], identity, B(a="the Boolean variable A", b="the Boolean variable B")))
    assert idle.status is S.ENTAILED and codes(idle) == {"ARG-VAC-001": "warning"}


@pytest.mark.parametrize("case_id, assertion", [("f09_hasty_generalisation", "e_loftus"), ("f09b_hasty_generalisation_so", "l_so")])
def test_f09_and_f09b_hasty_generalisation_suppresses_the_generic_ns_001(case_id, assertion):
    diags = engine_named(case_id)
    d = by_code(diags, "ARG-HG-001")
    assert d.severity == "warning" and assertion in d.assertion_ids and "'all ...'" in d.message
    assert "ARG-NS-001" not in {x.code for x in diags}


def test_f10_false_dilemma_fd_001():
    d = by_code(engine_named("f10_false_dilemma"), "ARG-FD-001")
    assert d.assertion_ids == ["d_either"] and d.missing_link.text == "either the firm cuts its prices or the firm goes bankrupt, and nothing else"


@pytest.mark.parametrize("mode", ["report", "text"])
def test_i02_causal_leap_cl_001(mode):
    d = by_code(engine_named("i02_post_hoc", mode), "ARG-CL-001")
    assert d.assertion_ids == ["L_cause"] and "one quantity at two times" in d.message


@pytest.mark.parametrize("mode", ["report", "text"])
def test_i03a_one_symbol_two_senses_eq_003(mode):
    d = by_code(engine_named("i03a_equivocation_one_symbol", mode), "ARG-EQ-003")
    assert d.assertion_ids == ["L_guess"] and "(scientific theory)" in d.message


@pytest.mark.parametrize("mode", ["report", "text"])
def test_i03b_the_bridge_joins_two_senses_eq_002_and_is_not_capped(mode):
    [out] = translated("i03b_equivocation_flagged", mode)
    assert out.translation.status.value == "AMBIGUOUS_TRANSLATION"
    diags = list(out.verification.named_diagnostics or [])
    d = by_code(diags, "ARG-EQ-002")
    assert d.severity == "warning" and d.capped_from is None              # the ambiguity is the defect: never capped
    assert d.missing_link.text == "the two senses of 'theory' are the same"
    assert "ARG-NS-002" not in {x.code for x in diags}                 # the generic bridge gives way to the equivocation


@pytest.mark.parametrize("mode", ["report", "text"])
def test_e06b_the_verified_table_refutes_the_point_refute_001(mode):
    d = by_code(engine_named("e06b_cherry_picked_trend_table_encoding", mode), "ARG-REFUTE-001")
    assert d.defect == "contradiction" and d.assertion_ids == ["P19", "P20", "P22", "P23", "C"]


def test_either_p_or_q_so_p_is_a_leap_inv_001():
    p = problem([P("d", OR(V("p"), V("q")), "either the reform passed or the strike ended")], V("p"),
                B(p="the reform passed", q="the strike ended"))
    r = run(p)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == {"ARG-INV-001": "warning"}


@pytest.mark.parametrize("premise, conclusion", [
    (NOT(OR(NOT(V("a")), NOT(V("b")))), AND(V("a"), V("b"))),
])
def test_an_equivalent_restatement_is_circular_circ_002(premise, conclusion):
    """Rewritten to the stricter rule of repair round 2 (fidelity-4 variant): a De Morgan form is beyond the engine's normal
    form, but the engine's E112 now decides the equivalence itself (``runner.equivalent_premises``), so the ENTAILED is no
    verdict and the circle is named ARG-CIRC-001 from E112 (before, only the argument rule ARG-CIRC-002 named it)."""
    syms = {"x": ("Real", "the reading in volts"), **B(a="the test passed", b="the sample was pure")}
    p = problem([P("w", premise, "the point in other words")], conclusion, syms)
    r = run(p)
    assert r.status is S.ENTAILED and "E112" in {d.code for d in r.diagnostics}
    assert codes(r)["ARG-CIRC-001"] == "warning"


def test_a_restatement_in_the_engines_normal_form_is_named_like_the_same_text():
    """Rewritten to the stricter rule of the re-run review (fidelity-4): ``5 < x`` for ``x > 5`` is the same statement in the
    engine's normal form (circular_premises), so it is E112 with ARG-CIRC-001, exactly as the identical text is; ARG-CIRC-002
    is left to an equivalence the normal form does not read (De Morgan, above)."""
    syms = {"x": ("Real", "the reading in volts")}
    for premise in (CMP("lt", R(5), V("x")), CMP("gt", V("x"), R(5))):
        r = run(problem([P("w", premise, "the point in other words")], CMP("gt", V("x"), R(5)), syms))
        assert r.status is S.ENTAILED and "E112" in {d.code for d in r.diagnostics}
        assert codes(r).get("ARG-CIRC-001") == "warning" and "ARG-CIRC-002" not in codes(r)


# ----------------------------------------------------------------------------------------------- controls

CONTROLS = [("c01_modus_ponens", "text"), ("c02_modus_tollens", "text"), ("c03_true_dichotomy", "text"), ("c04_quoted_transcription", "text"),
            ("c05_consistent_chemistry", "text"), ("c02_control_history_quotes", "report"), ("c02_control_history_quotes", "text"),
            ("c03_control_psych_study", "report"), ("c03_control_psych_study", "text"), ("c04_control_english_quote", "report"),
            ("c04_control_english_quote", "text"), ("i00_control_valid_rule", "report"), ("i00_control_valid_rule", "text"),
            ("i02c_control_rct_cause", "report"), ("i02c_control_rct_cause", "text")]


@pytest.mark.parametrize("case_id, mode", CONTROLS)
def test_the_controls_get_no_argument_warning(case_id, mode):
    """No argument code warns on a control, in the engine's signed copy or on the outcome. Rewritten for the merged evidence
    family: the outcome of a control may also carry evidence records (EVD-*) about premises no check established; outside a
    source-bound task each is shown at info, capped from warning (``capped_from``), so it is never shown as a warning and
    still keeps the claim from release, as the cap rule requires. Every argument code is asserted exactly as before."""
    outs = translated(case_id, mode)
    assert outs or case_id == "i02c_control_rct_cause"
    for out in outs:
        engine = list(out.verification.named_diagnostics or []) if out.verification is not None else []
        assert warnings(engine) == [] and [c for c in warnings(out.named_diagnostics) if not c.startswith("EVD-")] == [], (case_id, mode, out.claim_id)
        evidence = [d for d in out.named_diagnostics if d.code.startswith("EVD-")]
        assert all(d.severity == "info" and (d.capped_from is None or d.cap_reason == "not_source_bound") for d in evidence), (case_id, mode, out.claim_id)
        if any(is_blocking(d) for d in evidence):
            assert out.release is not None and not out.release.permitted, (case_id, mode, out.claim_id)
    receipt = _delivered(case_id, mode).receipt
    assert not [d.code for d in receipt.named_diagnostics if d.code.startswith("ARG-") and is_blocking(d)]


def test_c03_dich_gives_no_false_dilemma_and_i02c_no_causal_leap_and_c04_quote_no_paraphrase():
    for case_id, mode, code in [("c03_true_dichotomy", "text", "ARG-FD-001"), ("i02c_control_rct_cause", "report", "ARG-CL-001"),
                                ("c04_quoted_transcription", "text", "ARG-CIRC-003")]:
        for out in translated(case_id, mode):
            assert code not in {d.code for d in out.verification.named_diagnostics or []}, (case_id, code)


def test_a_valid_interpretive_link_is_an_info_record_never_a_warning():
    """c04-eng and c03-psych rest on one writer's link to the point (a valid interpretive step); structure alone cannot tell
    it from f01b, so the record is info: the result is not releasable and never accused."""
    for case_id in ("c04_control_english_quote", "c03_control_psych_study"):
        diags = [d for out in translated(case_id, "report") for d in (out.verification.named_diagnostics or [])]
        assert "ARG-LINK-001" in {d.code for d in diags} and warnings(diags) == []


def test_a_biconditional_stated_both_ways_is_no_affirming_the_consequent():
    meanings = B(plant="the observed cell is a plant cell", wall="the observed cell has a cell wall")
    both_rules = problem([P("r1", IMP(V("plant"), V("wall")), "a plant cell has a cell wall", kind="general_knowledge", note="rule"),
                          P("r2", IMP(V("wall"), V("plant")), "a cell with a cell wall is a plant cell", kind="general_knowledge", note="rule"),
                          P("e", V("wall"), "the observed cell has a cell wall", kind="task_setting", verified=True)], V("plant"), meanings)
    one_iff = problem([P("r", IFF(V("plant"), V("wall")), "a cell is a plant cell exactly when it has a cell wall", note="link: exactly when"),
                       P("e", V("wall"), "the observed cell has a cell wall", kind="task_setting", verified=True)], V("plant"), meanings)
    for p in (both_rules, one_iff):
        r = run(p)
        assert r.status is S.ENTAILED and "ARG-AC-001" not in codes(r) and warnings(r.named_diagnostics) == []


def test_all_three_is_a_closed_enumeration_never_a_hasty_generalisation():
    meanings = B(a="part (a) of the answer is correct", b="part (b) of the answer is correct", c="part (c) of the answer is correct",
                 all3="all three parts of the answer are correct")
    p = problem([P("ea", V("a"), "part (a) is correct"), P("eb", V("b"), "part (b) is correct"), P("ec", V("c"), "part (c) is correct"),
                 P("l", IMP(AND(V("a"), V("b"), V("c")), V("all3")), "so all three parts are correct", note="link: so")], V("all3"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-HG-001" not in codes(r)
    unlinked = problem([P("ea", V("a"), "part (a) is correct")], V("all3"), meanings)
    assert "ARG-HG-001" not in codes(run(unlinked))


def test_a_bridge_between_two_meanings_of_one_head_noun_without_a_sense_marker_is_ns_002_not_eq_002():
    meanings = B(e="evolution is a well-tested theory", t="evolution is a theory that is merely a guess", g="evolution is an unproven guess")
    p = problem([P("e1", V("e"), "evolution is a well-tested theory"), P("l1", IMP(V("t"), V("g")), "a theory that is a guess is unproven")], V("g"), meanings)
    r = run(p)
    assert r.status is S.COUNTEREXAMPLE and codes(r) == {"ARG-NS-002": "warning"}


def test_a_qualified_symbol_used_consistently_gives_no_eq_003():
    meanings = B(sci="evolution by natural selection is a scientific theory", expl="evolution is a well-substantiated explanation")
    p = problem([P("e", V("sci"), "evolution by natural selection is a scientific theory"),
                 P("l", IMP(V("sci"), V("expl")), "a scientific theory is a well-substantiated explanation", note="link: so")], V("expl"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-EQ-003" not in codes(r)


def test_a_parenthetical_gloss_of_a_sense_marks_the_sense_for_eq_003():
    meanings = B(evo="evolution is a theory (well-substantiated explanation)", guess="evolution is an unproven guess")
    p = problem([P("e", V("evo"), "evolution is a theory"), P("l", IMP(V("evo"), V("guess")), "a theory is an unproven guess", note="link: so")],
                V("guess"), meanings)
    assert codes(run(p))["ARG-EQ-003"] == "warning"


def test_a_parenthetical_naming_a_referent_and_a_the_x_is_label_give_no_eq_003():
    """A parenthetical that identifies what a noun refers to (a date, a name, a title) fixes no sense, and "the X is ..."
    predicates something of one X: neither is the two-senses shape (the e2e history answer's correct claim)."""
    meanings = {"y_peak": ("Int", "year of the highest bread price in the table (1923)"),
                "y_surge": ("Int", "year of the electoral surge (the 1930 Reichstag election)"),
                **B(sep="the electoral surge came after the inflation peak", not_main="hyperinflation was not the main reason people voted Nazi")}
    p = problem([P("pk", CMP("eq", V("y_peak"), {"op": "int", "value": "1923"}), "the inflation peak falls in 1923", kind="supplied_text", verified=True),
                 P("su", CMP("eq", V("y_surge"), {"op": "int", "value": "1930"}), "the electoral surge came in the 1930 Reichstag election",
                   kind="general_knowledge"),
                 P("sep", IFF(V("sep"), CMP("gt", V("y_surge"), V("y_peak"))), "the surge is separated from the peak: it came later"),
                 P("lk", IMP(V("sep"), V("not_main")), "dates separated from the peak mean hyperinflation was not the main reason")],
                V("not_main"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-EQ-003" not in codes(r) and warnings(r.named_diagnostics) == []
    head = problem([P("e", V("s"), "the surge is large"), P("l", IMP(V("s"), V("t")), "the surge is a sign of anger", note="link: so")], V("t"),
                   B(s="the surge (a sudden rise in votes) is large", t="voters were angry"))
    assert "ARG-EQ-003" not in codes(run(head))                        # "the surge is ..." defines nothing


def test_if_then_is_no_sequence_in_time_for_the_causal_leap():
    meanings = B(inst="40 CCTV cameras were installed in the town centre", caused="the CCTV cameras caused the fall in burglaries")
    p = problem([P("e", V("inst"), "cameras were installed"),
                 P("l", IMP(V("inst"), V("caused")), "if the cameras were installed then they caused the fall", note="link: so")], V("caused"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-CL-001" not in codes(r)
    later = problem([P("e", V("inst"), "cameras were installed"),
                     P("l", IMP(V("inst"), V("caused")), "cameras were installed and burglaries then fell, so the cameras caused the fall", note="link: so")],
                    V("caused"), meanings)
    assert codes(run(later))["ARG-CL-001"] == "warning"


# ----------------------------------------------------------------------------------------------- bounds, caps, determinism

def _chain(n: int, extra: int = 0) -> Problem:
    """x0, x0 -> x1, ..., x(n-2) -> x(n-1) |= x(n-1): every premise the writer's own, ``extra`` duplicated links on top."""
    syms = B(**{f"x{i}": f"step {i} of the argument holds" for i in range(n)})
    prem = [P("f0", V("x0"), "the first step holds")] + [P(f"l{i}", IMP(V(f"x{i}"), V(f"x{i + 1}")), f"step {i} gives step {i + 1}") for i in range(n - 1)]
    prem += [P(f"d{i}", IMP(V(f"x{i % (n - 1)}"), V(f"x{i % (n - 1) + 1}")), "the same step again") for i in range(extra)]
    return problem(prem, V(f"x{n - 1}"), syms)


def test_a_128_premise_problem_with_every_premise_unverified_stays_within_the_budget():
    p = _chain(64, extra=64)
    assert len(p.premises) == 128
    t0 = time.perf_counter()
    r = run(p)
    elapsed = (time.perf_counter() - t0) * 1000.0
    per_run, total = argument_module.run_budget_ms(CFG)
    assert r.status is S.ENTAILED and r.argument_rules == ARG_RULES_VERSION              # it finished: complete
    stage = [t.ms for t in r.timings if t.stage == "diagnose"]
    assert stage and stage[0] < total and elapsed < total + 2 * CFG.timeout_ms
    link = [d for d in r.named_diagnostics if d.code == "ARG-LINK-001"]
    assert link and all("partly minimised (the first 16 were tested)" in d.message for d in link)
    assert all(len(d.derived_problem_digests) <= argument_module.MAX_DERIVED_RUNS for d in r.named_diagnostics)


@pytest.mark.parametrize("bound", ["MAX_DERIVED_RUNS", "TOTAL_BUDGET_MS"])
def test_a_budget_of_zero_records_incomplete_and_fires_nothing(monkeypatch, bound):
    monkeypatch.setattr(argument_module, bound, 0)
    for p in (_chain(3), problem([P("d", OR(V("p"), V("q"))), P("e", V("q"), kind="task_setting", verified=True)], V("p"), B(p="", q=""))):
        r = run(p)
        assert r.argument_rules.startswith(f"{ARG_RULES_VERSION}/incomplete:") and r.named_diagnostics is None
        assert r.status in (S.ENTAILED, S.COUNTEREXAMPLE)                                 # the status is the engine's, unchanged


def test_two_runs_give_identical_diagnostics():
    p = _chain(4)
    a, b = run(p), run(p)
    assert a.argument_rules == b.argument_rules == ARG_RULES_VERSION
    assert [d.model_dump(mode="json") for d in a.named_diagnostics] == [d.model_dump(mode="json") for d in b.named_diagnostics]


def test_a_derived_timeout_fires_nothing(monkeypatch):
    original = argument_module._Runs.entail

    def undecided(self, *args, **kwargs):
        decided = original(self, *args, **kwargs)
        self._missing("derived_undecided")
        return argument_module._Run(digest=decided.digest)

    monkeypatch.setattr(argument_module._Runs, "entail", undecided)
    entailed = run(_chain(3))
    assert entailed.status is S.ENTAILED and entailed.named_diagnostics is None
    assert entailed.argument_rules == f"{ARG_RULES_VERSION}/incomplete:derived_undecided"
    leap = run(problem([P("d", OR(V("p"), V("q"))), P("e", V("q"), kind="task_setting", verified=True)], V("p"), B(p="the reform passed", q="the strike ended")))
    assert leap.status is S.COUNTEREXAMPLE and leap.named_diagnostics is None           # no generic leap while a derived run is undecided


def test_a_derived_run_decides_as_the_engine_decides_its_derived_problem(monkeypatch):
    """Each derived problem, decided on the bound problem's compiled terms, gets the status ``engine.verify`` gives the same
    problem on its own, and passes the validator. Rewritten in repair round 1 (re-run review ADV-08), which no longer
    re-validates a run made only of the bound problem's premises and conclusion: the derived problems are now captured at
    their digest, which every decided run computes, and the test also asserts that each of them passes the validator (the
    re-validation the engine left out is checked here), so it captures at least as many runs as before."""
    from epinoic_logic.engine.validator import validate_problem
    from epinoic_logic.ir.schema import DEFAULT_LIMITS
    seen: list = []
    original_digest = argument_module.problem_digest
    original_entail = argument_module._Runs.entail

    def spy_digest(problem):
        seen.append(problem)
        return original_digest(problem)

    def spy_entail(self, *args, **kwargs):
        before = len(seen)
        decided = original_entail(self, *args, **kwargs)
        if len(seen) > before:
            seen[-1] = (seen[-1], decided.status)
        return decided

    monkeypatch.setattr(argument_module, "problem_digest", spy_digest)
    monkeypatch.setattr(argument_module._Runs, "entail", spy_entail)
    run(_chain(4))
    run(problem([P("r", IMP(V("plant"), V("wall")), kind="general_knowledge"), P("e", V("wall"), kind="task_setting", verified=True)], V("plant"),
                B(plant="the cell is a plant cell", wall="the cell has a wall")))
    pairs = [x for x in seen if isinstance(x, tuple)]
    assert len(pairs) >= 4
    monkeypatch.undo()
    for derived, status in pairs:
        assert validate_problem(derived, DEFAULT_LIMITS).ok
        assert verify(derived, CFG, diagnose=False).status is status


def test_severity_cap_gives_info_with_capped_from_inside_the_signature():
    p = problem([P("r", IMP(V("plant"), V("wall")), "a plant cell has a cell wall", kind="general_knowledge"),
                 P("e", V("wall"), "the cell has a cell wall", kind="task_setting", verified=True)], V("plant"),
                B(plant="the cell is a plant cell", wall="the cell has a wall"))
    plain = verify(p, CFG, signing_key=KEY, key_id="t")
    capped = verify(p, CFG, signing_key=KEY, key_id="t", severity_cap=("info", "ambiguous_translation"))
    assert codes(plain)["ARG-AC-001"] == "warning"
    d = by_code(capped.named_diagnostics, "ARG-AC-001")
    assert (d.severity, d.capped_from, d.cap_reason) == ("info", "warning", "ambiguous_translation") and is_blocking(d)
    assert verify_signature(capped, KEY)
    tampered = capped.model_copy(update={"named_diagnostics": [d.model_copy(update={"capped_from": None, "cap_reason": None})]})
    assert not verify_signature(tampered, KEY)
    assert verify_signature(sign_result(tampered, KEY, "t"), KEY)                     # only a key holder can re-sign


def test_the_engine_never_changes_the_status_or_the_dependency_lists():
    for p in (_chain(3), problem([P("d", OR(V("p"), V("q")))], V("p"), B(p="", q=""))):
        on, off = verify(p, CFG), verify(p, CFG, diagnose=False)
        assert on.status is off.status and on.premises_relied_on == off.premises_relied_on
        assert on.ungrounded_dependencies == off.ungrounded_dependencies and on.unverified_dependencies == off.unverified_dependencies
        assert [d.code for d in on.diagnostics] == [d.code for d in off.diagnostics]
        assert off.argument_rules is None and off.named_diagnostics is None


# ----------------------------------------------------------------------------------------------- the cue tables are data

def test_the_cue_tables_are_pinned():
    assert cues.UNIVERSAL.phrases == (("all",), ("every",), ("always",), ("never",), ("none",), ("no", "one"), ("nobody",), ("everyone",),
                                      ("everybody",), ("everything",), ("any",), ("each",), ("in", "general"), ("universally",),
                                      ("without", "exception"), ("in", "every", "case"), ("in", "all", "cases"))
    assert cues.INSTANCE.phrases == (("in", "this", "case"), ("in", "that", "case"), ("in", "one", "case"), ("this",), ("one",), ("a",), ("an",),
                                     ("the", "study"), ("this", "study"), ("the", "experiment"), ("the", "participants"), ("a", "participant"),
                                     ("in", "the", "study"), ("in", "this", "study"), ("the", "sample"), ("in", "the", "sample"), ("the", "trial"))
    assert cues.CAUSAL.phrases[:6] == (("caused",), ("causes",), ("cause", "of"), ("causing",), ("led", "to"), ("leads", "to"))
    # repair round 2: the verb's plain form "cause" is added data (a cause read into a correlation: "sales cause drownings")
    assert ("made", "*", "rise") in cues.CAUSAL.phrases and cues.CAUSAL.phrases[25] == ("cause",)
    # repair round 3 (ADV3-05, ADV3-07): verbs that say one thing brought another about are added data, pinned exactly
    assert len(cues.CAUSAL.phrases) == 38 and cues.CAUSAL.phrases[26:] == (
        ("cured",), ("cures",), ("healed",), ("heals",), ("triggered",), ("triggers",), ("sparked",), ("sparks",), ("provoked",), ("provokes",),
        ("induced",), ("induces",))
    assert cues.SEQUENCE.phrases == (("after",), ("then",), ("following",), ("subsequently",), ("afterwards",), ("before",), ("later",))
    # re-run review ADV-06: a bare "control", "controlled", "controls" or "trial" is no control cue ("took control of the press");
    # only the phrases of a controlled comparison are, and a negated cue or a comparison with another time states none
    assert cues.CONTROL.phrases == (("random",), ("randomly",), ("randomised",), ("randomized",), ("randomisation",), ("randomization",),
                                    ("control", "group"), ("control", "groups"), ("control", "condition"), ("control", "sample"), ("a", "control"),
                                    ("the", "control"), ("controlled", "trial"), ("controlled", "trials"), ("controlled", "experiment"),
                                    ("controlled", "experiments"), ("controlled", "study"), ("controlled", "for"), ("controlling", "for"),
                                    ("controls", "for"), ("compared", "with"), ("compared", "to"), ("comparison", "group"), ("matched",), ("placebo",),
                                    ("double", "blind"), ("blind", "trial"))
    assert {"no", "not", "without", "lacked"} <= cues.CONTROL_NEGATORS and {"before", "previous", "last", "april"} <= cues.TIME_WORDS
    assert cues.SAMPLE.phrases[:4] == (("some",), ("several",), ("a", "few"), ("few",)) and len(cues.SAMPLE.phrases) == 16
    assert {"metres", "per", "years", "million"} <= cues.MEASURE_WORDS and "cyclists" not in cues.MEASURE_WORDS
    # repair round 3 (ADV3-05): repeated sessions of one treatment are a measure, not a sample of cases (added data)
    assert {"sessions", "doses", "lessons", "visits", "rounds", "sittings", "attempts", "repetitions", "laps"} <= cues.MEASURE_WORDS
    # repair round 3 (ADV3-04): closed partitions and order words of exhaustive options (added data, pinned exactly)
    assert len(cues.EXHAUSTIVE_PARTITIONS) == 13 and cues.EXHAUSTIVE_PARTITIONS[0] == (("positive",), ("negative",), ("zero", "0"))
    assert (("exothermic",), ("endothermic",)) in cues.EXHAUSTIVE_PARTITIONS and (("heads",), ("tails",)) in cues.EXHAUSTIVE_PARTITIONS
    assert all(len(p) >= 2 and all(slot for slot in p) for p in cues.EXHAUSTIVE_PARTITIONS)
    assert len(cues.ORDER_WORDS) == 25 and cues.ORDER_WORDS[0] == ("greater than or equal to", "ge") and ("at most", "le") in cues.ORDER_WORDS
    assert [sorted(t.forms) for t in cues.EQUIVOCAL_TERMS][:3] == [["theories", "theory"], ["fit", "fitness", "fitter", "fittest"],
                                                                   ["work", "worked", "works"]]
    # repair round 2: the 'light' term (mass / radiation), the majority cues, the frequency and other synonym groups, the 'flood'
    # definition and the verb pair 'converge diverge' are added data, pinned here with the rest
    assert len(cues.EQUIVOCAL_TERMS) == 13 and all(t.technical != t.everyday for t in cues.EQUIVOCAL_TERMS)
    assert [sorted(t.forms) for t in cues.EQUIVOCAL_TERMS if "light" in t.forms] == [["light", "lights"]]
    assert cues.MAJORITY.phrases[:3] == (("most",), ("the", "majority", "of"), ("a", "majority", "of")) and len(cues.MAJORITY.phrases) == 10
    assert ("often", "frequently", "frequent", "regularly", "repeatedly") in cues.SYNONYM_GROUPS and len(cues.SYNONYM_GROUPS) == 18
    # repair round 5 (ADV5-15 c): an evaluation restated in another word is added data, pinned exactly
    assert cues.SYNONYM_GROUPS[-1] == ("boring", "tedious", "dull", "monotonous")
    # repair round 4 (ADV4-08): "work" read as "effective", and "light" as radiation where it is what travels, are added data,
    # pinned exactly
    assert cues.SYNONYM_GROUPS[10] == ("effective", "work", "works", "worked", "effectual")
    light = next(t for t in cues.EQUIVOCAL_TERMS if "light" in t.forms)
    assert len(light.technical_cues.phrases) == 29 and light.technical_cues.phrases[13:] == (
        ("light", "travels"), ("light", "travel"), ("light", "travelled"), ("light", "traveled"), ("light", "moves"),
        ("light", "is", "refracted"), ("light", "is", "reflected"), ("ray", "of", "light"), ("rays", "of", "light"), ("light", "ray"),
        ("light", "rays"), ("beam", "of", "light"), ("light", "beam"), ("light", "beams"), ("light", "wave"), ("light", "waves"))
    assert cues.DEFINITIONS["flood"][0] == ("overflow", "bank") and frozenset({"converge", "diverge"}) in cues.COMPLEMENTARY_PAIRS
    assert cues.DEFINITIONS["success"][0] == ("achieve", "aims") and {"lacked", "without"} <= cues.NEGATING_WORDS
    assert frozenset({"even", "odd"}) in cues.COMPLEMENTARY_PAIRS and cues.COMPLEMENTARY_CONTEXT[frozenset({"0", "1"})] >= {"bit", "binary"}
    assert cues.SENSE_QUALIFIERS == frozenset({"scientific", "everyday", "ordinary", "colloquial", "legal", "technical", "mathematical", "statistical",
                                               "literal", "figurative", "biological", "economic"})
    assert cues.DEFINITION_DETERMINERS == frozenset({"a", "an", "every", "all", "any", "each"})
    assert cues.WRITER_STEP_KINDS == frozenset({"specialist_inference", "assumption", None})
    assert cues.REASON_CONNECTIVES.phrases[:8] == (("because",), ("since",), ("so",), ("therefore",), ("thus",), ("hence",), ("given", "that"),
                                                   ("due", "to", "the", "fact", "that"))
    assert ("as", "*", "*", "*", "suggests") in cues.REASON_CONNECTIVES.phrases and len(cues.REASON_CONNECTIVES.phrases) == 29
    assert cues.KNOWLEDGE_KIND == "general_knowledge"
    assert set(cues.TABLES) == {"universal", "number_words", "instance", "causal", "sequence", "control", "sense_qualifiers", "sense_excluded_heads",
                                "definition_determiners", "definition_verbs", "months", "reason_connectives", "writer_step_kinds",
                                # re-run review: hasty generalisation from samples, control cues, equivocal terms, paraphrases, complements
                                "sample", "measure_words", "irregular_plurals", "control_negators", "time_words", "equivocal_terms",
                                "negating_words", "not_prefixed", "definitions",
                                "synonym_groups", "complementary_pairs", "complementary_context", "majority",
                                # repair round 2: a cause read into a correlation
                                "correlation", "comparatives", "populations",
                                # repair round 2 (resumed): a sample's finding stated of a wider whole (added data, pinned below)
                                "sample_participles", "sampling_units", "representative",
                                # repair round 3: exhaustive options (pinned above)
                                "exhaustive_partitions", "order_words"}
    assert {"sampled", "interviewed", "surveyed"} <= cues.SAMPLE_PARTICIPLES and {"quadrat", "survey", "sample"} <= cues.SAMPLING_UNITS
    assert ("random",) in cues.REPRESENTATIVE.phrases and ("representative",) in cues.REPRESENTATIVE.phrases
    assert ("associated", "with") in cues.CORRELATION.phrases and {"more", "higher"} <= cues.COMPARATIVES and "later" not in cues.COMPARATIVES
    assert {"countries", "students", "towns"} <= cues.POPULATIONS and "gases" not in cues.POPULATIONS


def test_no_message_carries_a_success_word():
    from epinoic_logic.named import SUCCESS_WORDS
    import re
    diags = [d for case_id in ("f01b_non_sequitur_so", "f03_affirming_consequent", "f10_false_dilemma", "i02_post_hoc")
             for d in engine_named(case_id, "text")]
    for d in diags:
        words = set(re.findall(r"[a-z]+", d.message.casefold()))
        assert not words & set(SUCCESS_WORDS), (d.code, words & set(SUCCESS_WORDS))
