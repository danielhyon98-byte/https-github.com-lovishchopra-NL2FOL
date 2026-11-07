"""The translator's circularity check beyond a restatement as written (round-8 clearance, integrated round c1; critical).

The transfer auditor confirmed seven genuine translations circular (OVS-TRN-006) that the channel had displayed ENTAILED
with no diagnostic: cs-t14 c18.2 and c25.1, ph-p8b s1.1, maa-t14 m6.1, bi-t14 s1.2 and s4.7, ch-t14 s2.12 (and ph-t14
s3.2, round-7 bug 1: the same equation rearranged). ``translate.restatement`` now reads a conclusion restated by its
Boolean structure or by the arithmetic of its own symbols, by premises no check verified, and part of a conclusion restated
by a task figure no check verified on which the result rests: the pipeline's E112, so the verdict is withheld before it is
displayed (and the auditor, which agrees with the translator's E112, has nothing left to refute).

Rewritten on the clearance's second pass (6 November) to the corrected rule, stated per test: the translation-fidelity
lens of the round, judging claim by claim with the strongest tier, found maa-t14 m6.1 and cs-t14 c18.2 faithful checks of the
claim's own step (the auditor's labels on them false), and the first pass's rule also withheld the committed end-to-end
fixture cs_entailed and the argument-diagnosis cases packed in one premise (tests/e2e/test_multi_subject_e2e.py,
tests/contract/test_repair_round2_cases.py). A premise that only NAMES an expression the conclusion is an identity of
(c18.2, c25.1, cs_entailed), or that is the input of the step the claim states (m6.1, "Domain: x + 4 > 0 and x − 4 > 0, so x
> 4"), is now no restatement, as the transfer auditor's rules definitional-identity and stated-step read it; a premise's own
link is an argument, never a restatement. The other five stay withheld, and the four encodings the lens found circular
(hi-t14 h1.12, ph-p8b s6.2, ph-t14 s3.2 and s4.4) are withheld.

The recorded translations are served as the arena harness serves them (``tests/channel/c1_core_support.py``)."""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.restatement import MAX_RESTATEMENT_CHECKS, semantic_restatement

from ..channel.c1_core_support import C1, deliver
from ..core_hostile import SHAPES, one, sweep
from ..timing import measure


def outcome_of(task: str, claim: str, translations: dict):
    _hub, _ch, _reply, rc = deliver(task, translations=translations)
    return next(o for o in rc.outcomes if o.claim_id.split("@")[0] == claim)


@pytest.mark.parametrize("task,claim,kind", [
    ("ph-t14", "s3.2", "arithmetic"),                 # "g × R² = G × M" rearranged to "g = G × M / R²"
    ("ph-p8b", "s1.1", "part of the conclusion"),     # "k = 50", an unverified task figure, restated in the conclusion
    ("bi-t14", "s1.2", "part of the conclusion"),     # "each quadrat is 1 m²"
    ("bi-t14", "s4.7", "part of the conclusion"),     # "20 quadrats had both species"
    ("ch-t14", "s2.12", "part of the conclusion"),    # "1 × e_h = 6" restated by the unverified count "e_h = 6"
])
def test_the_circular_c1_translations_are_withheld_never_displayed_entailed(task, claim, kind):
    o = outcome_of(task, claim, C1["translations"][task])
    assert o.display_status is not S.ENTAILED and o.display_status is S.INVALID_FORMALIZATION
    diag = " ".join(o.translation.diagnostics)
    assert "E112" in diag and "rule semantic-restatement" in diag and kind in diag, diag[:600]


@pytest.mark.parametrize("task,claim,why", [
    ("maa-t14", "m6.1", "stated step"),             # "Domain: x + 4 > 0 and x − 4 > 0, so x > 4": the step from its stated input
    ("cs-t14", "c18.2", "definitional identity"),   # X named by its expression; the case analysis is an identity of it
    ("cs-t14", "c25.1", "definitional identity"),   # the original expression named; its simplification to NOT B is an identity
])
def test_a_stated_step_and_a_definitional_identity_are_checked_steps_never_circles(task, claim, why):
    """The first pass of this clearance withheld these three as circular (the transfer auditor's labels); the round's
    translation-fidelity lens judged m6.1 and c18.2 faithful checks of the claim's own step, and the auditor now exempts all
    three by its rules stated-step and definitional-identity: the engine's ENTAILED is displayed with no E112."""
    from epinoic_logic.translate.restatement import _definitional_identity, _stated_step, _Checker, _dump, _nnf_conjuncts
    o = outcome_of(task, claim, C1["translations"][task])
    assert o.display_status is S.ENTAILED and not any("E112" in d for d in o.translation.diagnostics), o.translation.diagnostics
    p = Problem.model_validate(C1["translations"][task][claim]["problem"])
    exprs = {pr.id: _dump(pr.expr) for pr in p.premises}
    if why == "stated step":
        text = next(c for c in SPEC_CLAIMS[task] if c.startswith("Domain:"))
        assert _stated_step(text, exprs["domain"], _nnf_conjuncts(_dump(p.conclusion.expr)))
    else:
        assert any(_definitional_identity(p, pid, exprs, _Checker(p)) for pid in exprs)


#: The claim texts the tests above read (the delivered claims of the recorded replies).
SPEC_CLAIMS = {"maa-t14": ["Domain: x + 4 > 0 and x − 4 > 0, so x > 4."]}


@pytest.mark.parametrize("task,claim", [("maa-t14", "m7.7")])
def test_controls_keep_their_verdicts(task, claim):
    """m7.7 assigns the candidate it tests (its own reasoning, no task figure).

    Rewritten to a stricter rule (round-8 clearance c1, the translation-fidelity lens's finding on four encodings that prove
    nothing about their claim): this test first kept ph-t14 s4.4 here as a control, displayed ENTAILED. Its premise 'cube'
    asserts the very result the claim's written calculation states ('(5.000 × 10⁶ m)³ = 1.250 × 10²⁰ m³') as an
    arithmetic_fact, so the engine only checked that 1.25 × 10²⁰ rounds to itself and never computed the cube: s4.4 is now
    withheld (E112, rule result-asserted; :func:`test_the_encodings_that_assume_the_claim_are_withheld`), and the control is
    the same claim with the cube left to the engine (:func:`test_a_cube_the_engine_computes_keeps_its_verdict`)."""
    o = outcome_of(task, claim, C1["translations"][task])
    assert o.display_status is S.ENTAILED, o.translation.diagnostics


# ----------------------------------------------- the translation-fidelity lens: encodings that assume their claim (major)


@pytest.mark.parametrize("task,claim,rule,premise", [
    ("hi-t14", "h1.12", "rule consequence-asserted", "h1.12-reason"),   # the main clause the claim reaches by "therefore", asserted
    ("ph-p8b", "s6.2", "rule consequence-asserted", "e-is-pe"),         # "so the total energy is elastic potential energy", asserted
    ("ph-t14", "s4.4", "rule result-asserted", "cube"),                 # the cube the claim computes, asserted as an arithmetic_fact
])
def test_the_encodings_that_assume_the_claim_are_withheld(task, claim, rule, premise):
    o = outcome_of(task, claim, C1["translations"][task])
    assert o.display_status is S.INVALID_FORMALIZATION, o.display_status
    diag = " ".join(o.translation.diagnostics)
    assert "E112" in diag and rule in diag and f"premise(s) {premise} (" in diag, diag[:700]
    assert o.verification is None  # no engine verdict is displayed on the claim


def _with(task: str, claim: str, edit) -> dict:
    """The recorded translation of ``claim`` with ``edit`` applied to its problem (a dict), as a fixture for that claim only."""
    import json
    rec = json.loads(json.dumps(C1["translations"][task][claim]))
    edit(rec["problem"])
    return {claim: rec}


def test_a_cube_the_engine_computes_keeps_its_verdict():
    """The control of s4.4: the same encoding with the cube written as the product the engine computes."""
    def computed(p):
        cube = next(x for x in p["premises"] if x["id"] == "cube")
        cube["expr"] = {"op": "eq", "left": {"op": "var", "name": "r_cube"},
                        "right": {"op": "mul", "args": [{"op": "real", "value": "5000000"}] * 3}}
    o = outcome_of("ph-t14", "s4.4", _with("ph-t14", "s4.4", computed))
    assert o.display_status is S.ENTAILED, o.translation.diagnostics


def test_a_consequence_derived_from_its_stated_reason_keeps_its_verdict():
    """The control of s6.2: the stated reason encoded (the speed is zero, so the kinetic energy is zero) with the energy
    law stated from subject knowledge; the consequence is derived, not asserted."""
    def derived(p):
        p["symbols"] += [{"name": "speed_ms", "sort": "Real", "meaning": "speed at maximum displacement, in m/s"},
                         {"name": "ke_j", "sort": "Real", "meaning": "kinetic energy at maximum displacement, in joules"}]
        law = {"kind": "general_knowledge", "certainty": "established"}
        p["premises"] = [
            {"id": "speed", "expr": {"op": "eq", "left": {"op": "var", "name": "speed_ms"}, "right": {"op": "real", "value": "0"}},
             "label": "at maximum displacement the speed is zero", "grounding": {"kind": "specialist_inference", "certainty": "established"}},
            {"id": "ke-zero", "expr": {"op": "implies", "left": {"op": "eq", "left": {"op": "var", "name": "speed_ms"}, "right": {"op": "real", "value": "0"}},
                                       "right": {"op": "eq", "left": {"op": "var", "name": "ke_j"}, "right": {"op": "real", "value": "0"}}},
             "label": "the kinetic energy is zero when the speed is zero", "grounding": law},
            {"id": "energy-law", "expr": {"op": "eq", "left": {"op": "var", "name": "energy_j"},
                                          "right": {"op": "add", "args": [{"op": "var", "name": "ke_j"}, {"op": "var", "name": "pe_max_j"}]}},
             "label": "the total energy is the kinetic energy plus the elastic potential energy", "grounding": law},
            next(x for x in p["premises"] if x["id"] == "pe-formula")]
    o = outcome_of("ph-p8b", "s6.2", _with("ph-p8b", "s6.2", derived))
    assert o.display_status is S.ENTAILED, o.translation.diagnostics


def test_a_therefore_step_encoded_from_its_supporting_claims_keeps_its_verdict():
    """The control of h1.12: the main clause derived from the supporting claims h1.10 and h1.11 by the claim's "therefore"
    link instead of asserted."""
    def derived(p):
        reason = next(x for x in p["premises"] if x["id"] == "h1.12-reason")
        reason["expr"] = {"op": "implies", "left": {"op": "and", "args": [{"op": "var", "name": "talks_dates"}, {"op": "var", "name": "no_reunif"},
                                                                          {"op": "var", "name": "armistice_38"}]},
                          "right": {"op": "var", "name": "war_3y1m_ended"}}
        reason["label"] = "h1.12: therefore (from h1.10 and h1.11) the war ended with the original aims of both sides abandoned"
    o = outcome_of("hi-t14", "h1.12", _with("hi-t14", "h1.12", derived))
    assert o.display_status is S.ENTAILED and not any("E112" in d for d in o.translation.diagnostics), o.translation.diagnostics


# --------------------------------------------------------------------------------------------------- the rule itself


def V(n):
    return {"op": "var", "name": n}


def R(v):
    return {"op": "real", "value": v}


def problem(premises, conclusion, symbols=(("x", "Real"),)):
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": n, "sort": s} for n, s in symbols],
                                   "premises": premises, "conclusion": {"id": "C", "expr": conclusion}})


def premise(pid, expr, kind=None, verified=None):
    out = {"id": pid, "expr": expr}
    if kind is not None:
        out["grounding"] = {"kind": kind, "certainty": "established", **({"verified": verified} if verified is not None else {})}
    return out


def test_a_term_moved_across_is_a_restatement_a_new_figure_is_a_computation():
    moved = problem([premise("D", {"op": "gt", "left": {"op": "sub", "left": V("x"), "right": R("4")}, "right": R("0")}, "general_knowledge")],
                    {"op": "gt", "left": V("x"), "right": R("4")})
    assert semantic_restatement(moved).kind == "full"
    computed = problem([premise("P", {"op": "eq", "left": V("x"), "right": R("1.60")})], {"op": "eq", "left": {"op": "mul", "args": [V("x"), R("100")]}, "right": R("160")})
    assert semantic_restatement(computed) is None  # 1.60 × 100 = 160 is arithmetic the engine checks
    working = problem([premise("P", {"op": "eq", "left": V("x"), "right": {"op": "div", "left": {"op": "sub", "left": R("20"), "right": R("0")}, "right": R("4.0")}})],
                      {"op": "eq", "left": V("x"), "right": R("5.0")})
    assert semantic_restatement(working) is None  # a line of working on numbers alone
    weaker = problem([premise("P", {"op": "eq", "left": V("x"), "right": R("5")}, "general_knowledge")], {"op": "gt", "left": V("x"), "right": R("3")})
    assert semantic_restatement(weaker) is None  # entailed, not equivalent: a derivation


def test_a_restating_premise_a_check_verified_or_located_is_data():
    p = problem([premise("D", {"op": "gt", "left": {"op": "sub", "left": V("x"), "right": R("4")}, "right": R("0")}, "task_setting", True)],
                {"op": "gt", "left": V("x"), "right": R("4")})
    assert semantic_restatement(p) is None
    q = problem([premise("Q", {"op": "eq", "left": V("x"), "right": R("4")}, "quotation")], {"op": "eq", "left": {"op": "mul", "args": [R("1"), V("x")]}, "right": R("4")})
    assert semantic_restatement(q) is not None and semantic_restatement(q, {"Q"}) is None


def test_a_label_on_figures_stays_an_unverified_dependency_and_a_label_on_boolean_content_is_the_writers_own():
    # "limit = 350" under a task label no check verified: listed as an unverified dependency, as before (never assumed)
    figure = problem([premise("L", {"op": "eq", "left": V("x"), "right": R("350")}, "task_setting")], {"op": "eq", "left": {"op": "mul", "args": [R("1"), V("x")]}, "right": R("350")})
    assert semantic_restatement(figure) is None
    # Boolean content under the same label that restates the conclusion: no check reads it in the task, so the claim is assumed
    restating = problem([premise("X", {"op": "or", "args": [{"op": "and", "args": [V("x"), V("a")]}, {"op": "and", "args": [V("x"), V("b")]}]}, "task_setting")],
                        V("x"), symbols=(("x", "Bool"), ("a", "Bool"), ("b", "Bool")))
    assert semantic_restatement(restating).kind == "full"
    # rewritten to the corrected rule (second pass): a Boolean DEFINITION under that label only names an expression the
    # conclusion is an identity of (rule definitional-identity, as the transfer auditor reads it): no restatement
    definition = problem([premise("X", {"op": "iff", "left": V("x"), "right": {"op": "and", "args": [V("a"), V("b")]}}, "task_setting")],
                         {"op": "implies", "left": V("a"), "right": {"op": "iff", "left": V("x"), "right": V("b")}}, symbols=(("x", "Bool"), ("a", "Bool"), ("b", "Bool")))
    assert semantic_restatement(definition) is None
    # the same definition with the named symbol used by another premise defines nothing new: still assumed
    reused = problem([premise("X", {"op": "iff", "left": V("x"), "right": {"op": "and", "args": [V("a"), V("b")]}}, "task_setting"),
                      premise("Y", {"op": "or", "args": [V("x"), V("b")]}, "task_setting")],
                     {"op": "implies", "left": V("a"), "right": {"op": "iff", "left": V("x"), "right": V("b")}}, symbols=(("x", "Bool"), ("a", "Bool"), ("b", "Bool")))
    assert semantic_restatement(reused) is not None
    # a source label on the same content stays an unverified dependency
    sourced = problem([premise("X", {"op": "iff", "left": V("x"), "right": {"op": "and", "args": [V("a"), V("b")]}}, "supplied_text")],
                      {"op": "implies", "left": V("a"), "right": {"op": "iff", "left": V("x"), "right": V("b")}}, symbols=(("x", "Bool"), ("a", "Bool"), ("b", "Bool")))
    assert semantic_restatement(sourced) is None


def test_a_partial_restatement_counts_only_a_task_figure_the_result_rests_on():
    givens = [premise("K", {"op": "eq", "left": V("k"), "right": R("50")}, "arithmetic_fact"),
              premise("A", {"op": "eq", "left": V("a"), "right": {"op": "mul", "args": [R("2"), V("k")]}}, "specialist_inference")]
    p = problem(givens, {"op": "and", "args": [{"op": "eq", "left": V("k"), "right": R("50")}, {"op": "eq", "left": V("a"), "right": R("100")}]}, symbols=(("k", "Real"), ("a", "Real")))
    found = semantic_restatement(p)
    assert found is not None and found.kind == "partial" and found.premises == ("K",)
    # the same with the figure verified: a transcription
    givens[0]["grounding"]["verified"] = True
    assert semantic_restatement(problem(givens, p.conclusion.expr.model_dump(mode="json", exclude_none=True), symbols=(("k", "Real"), ("a", "Real")))) is None
    # a relation under a task label is a step the engine checks, never a figure presented as given
    rel = [premise("K", {"op": "le", "left": V("k"), "right": {"op": "mul", "args": [R("2"), V("a")]}}, "arithmetic_fact"),
           premise("A", {"op": "eq", "left": V("a"), "right": R("30")}, "specialist_inference")]
    assert semantic_restatement(problem(rel, {"op": "and", "args": [{"op": "le", "left": V("k"), "right": {"op": "mul", "args": [R("2"), V("a")]}},
                                                                   {"op": "le", "left": V("k"), "right": R("60")}]}, symbols=(("k", "Real"), ("a", "Real")))) is None


def test_the_rule_is_bounded_on_the_largest_problem_the_schema_allows():
    n = 120
    symbols = tuple((f"v{i}", "Real") for i in range(n))
    premises = [premise(f"P{i}", {"op": "gt", "left": {"op": "sub", "left": V(f"v{i}"), "right": R(str(i))}, "right": R("0")}, "general_knowledge") for i in range(n)]
    conclusion = {"op": "and", "args": [{"op": "gt", "left": V(f"v{i}"), "right": R(str(i))} for i in range(30)]}
    p = problem(premises, conclusion, symbols=symbols)
    t = measure(lambda: semantic_restatement(p), 20.0, repeat=1, label="restatement on 120 premises and 30 conjuncts")
    assert t.holds, t
    assert MAX_RESTATEMENT_CHECKS <= 200


# ------------------------------------------------------------------- sweep: the readers this clearance added or changed


def _entries(text):
    from epinoic_logic.engine.argument import _PRESENTED_CAUSE_RE, _STATED_PAIR_RE, _causal
    from epinoic_logic.translate.eligibility import figure_text
    from epinoic_logic.translate.grounding import _LETTER_NAME_RE, locate_excerpt, trim_trailing_punctuation
    from epinoic_logic.translate.restatement import calculation_results, consequence_clauses
    doc = "MOTHER: Just the A. " + text
    labelled = _consequence_problem(label=text[:1000])
    return [("locate_excerpt", lambda: locate_excerpt(text[:4000] + ".", doc)), ("trim_trailing_punctuation", lambda: trim_trailing_punctuation(text)),
            ("figure_text", lambda: figure_text(text)), ("letter names", lambda: _LETTER_NAME_RE.findall(text)),
            ("presented cause", lambda: _PRESENTED_CAUSE_RE.search(text)), ("stated pair", lambda: _STATED_PAIR_RE.search(text)),
            ("_causal", lambda: _causal(text)), ("mark codes", lambda: figure_text("M1 " * 5000 + text)),
            ("consequence_clauses", lambda: consequence_clauses(text)), ("consequence_clauses(after a reason)", lambda: consequence_clauses("The speed is zero, so " + text)),
            ("calculation_results", lambda: calculation_results(text)), ("calculation_results(after a calculation)", lambda: calculation_results("r = 2 × 3 = " + text)),
            ("semantic_restatement(claim text)", lambda: semantic_restatement(labelled, claim_text=text)),
            ("semantic_restatement(label)", lambda: semantic_restatement(labelled, claim_text="The speed is zero, so the total energy is elastic potential energy."))]


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c1_translate_readers(shape):
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("text", ["made to look " * 3000 + "x", "presents " + "word " * 4000 + "as the cause", "M1A1" * 5000 + "x", "the A " * 4000,
                                  ", so " * 4000 + "x", "therefore " * 3000 + "x", "because " * 3000 + "x", "a, so b. " * 2500, "x = 2 × 3 = 6 " * 1500,
                                  "= " * 10000 + "1", "h1.12: " * 3000 + "x", "so that " * 3000 + "x", "it follows that " * 1500 + "x",
                                  "so " * 7000 + "x", "a so " * 5000 + "x", ("x" + " " * 50 + "so ") * 380 + "x"])
def test_the_new_translate_readers_are_linear_on_their_own_worst_inputs(text):
    assert not sweep(_entries, texts={"worst": text})


# ------------------------------------------------------------------- the rules result-asserted and consequence-asserted


def _consequence_problem(*, label: str = "at maximum displacement the speed is zero, so the total energy is the elastic potential energy",
                         kind: str = "specialist_inference") -> Problem:
    """ph-p8b s6.2's shape: the energy relation asserted under the claim's link label, and the potential-energy formula."""
    return problem([premise("e-is-pe", {"op": "eq", "left": V("energy_j"), "right": V("pe_max_j")}, kind) | {"label": label},
                    premise("pe-formula", {"op": "eq", "left": V("pe_max_j"), "right": R("0.04")}, "general_knowledge") | {"label": "the elastic potential energy is (1/2) k A^2"}],
                   {"op": "eq", "left": V("energy_j"), "right": R("0.04")},
                   symbols=(("energy_j", "Real"), ("pe_max_j", "Real")))


def test_consequence_clauses_read_the_consequence_on_its_side_of_the_connective():
    from epinoic_logic.translate.restatement import consequence_clauses
    reason, consequence, shown = consequence_clauses("At maximum displacement the speed is zero, so the total energy is elastic potential energy: E = ½kA².")
    assert {"speed", "zero"} <= reason and {"total", "energy", "elastic", "potential"} <= consequence
    assert shown == ("the total energy is elastic potential energy: E = ½kA²",)
    reason, consequence, shown = consequence_clauses("Demand fell because the price rose sharply.")
    assert "demand" in consequence and "price" in reason and shown == ("Demand fell",)
    # mid-clause "therefore": the consequence is the rest of the sentence
    _r, consequence, shown = consequence_clauses("A war of three years and one month therefore ended with the original aims abandoned.")
    assert shown == ("ended with the original aims abandoned",)
    # no connective: "so that", "so far", "because of", a degree "so", and a "so" inside a quotation
    for text in ("They saved so that they could invest.", "So far the price is stable.", "The price rose because of the drought.",
                 "The price rose so much that demand fell.", 'The poem says "so the river ran dry" in its last line.'):
        assert consequence_clauses(text) is None, text


def test_the_consequence_rule_names_only_an_asserted_consequence_the_conclusion_needs():
    text = "At maximum displacement the speed is zero, so the total energy is elastic potential energy: E = ½kA²."
    found = semantic_restatement(_consequence_problem(), claim_text=text)
    assert found is not None and found.kind == "consequence" and found.premises == ("e-is-pe",)
    # the same premise under a label that states the reason, or a law stated from subject knowledge, is no asserted consequence
    assert semantic_restatement(_consequence_problem(label="at maximum displacement the speed is zero"), claim_text=text) is None
    assert semantic_restatement(_consequence_problem(kind="general_knowledge"), claim_text=text) is None
    # a premise a check verified is data
    assert semantic_restatement(_consequence_problem(), {"e-is-pe"}, claim_text=text) is None
    # a claim with no consequence connective, and no claim text at all
    assert semantic_restatement(_consequence_problem(), claim_text="The total energy is elastic potential energy: E = ½kA².") is None
    assert semantic_restatement(_consequence_problem()) is None
    # a label naming a supporting claim is that claim's content
    assert semantic_restatement(_consequence_problem(label="s6.1 (supporting): the total energy is the elastic potential energy"), claim_text=text) is None


def test_stated_figures_of_the_consequence_are_data_for_its_arithmetic():
    """"The price fell, so revenue fell from $10m to $8m, a fall of 20%": the figures the consequence states are value
    assignments the engine computes with, never the consequence assumed."""
    p = problem([premise("before", {"op": "eq", "left": V("rev0"), "right": R("10")}, "specialist_inference") | {"label": "revenue fell from $10m"},
                 premise("after", {"op": "eq", "left": V("rev1"), "right": R("8")}, "specialist_inference") | {"label": "revenue fell to $8m"}],
                {"op": "eq", "left": {"op": "mul", "args": [V("fall"), R("10")]}, "right": {"op": "sub", "left": V("rev0"), "right": V("rev1")}},
                symbols=(("rev0", "Real"), ("rev1", "Real"), ("fall", "Real")))
    assert semantic_restatement(p, claim_text="The price fell, so revenue fell from $10m to $8m, a fall of 20%.") is None


def test_ec_p8a_g13_4_assumes_its_consequence_too():
    """The same shape on ec-p8a g13.4: 'the Pw line moves up to Pw + t' asserted as 'pw_plus_t = world + tariff' under the
    writer's own label, the stated reason ('the tariff raises the import price by $150') encoded beside it."""
    p = Problem.model_validate(C1["translations"]["ec-p8a"]["g13.4"]["problem"])
    text = "Change: the tariff raises the import price by $150, so the Pw line moves up to Pw + t (arrow from Pw to Pw + t)"
    found = semantic_restatement(p, {"pin-world", "pin-tariff"}, claim_text=text)
    assert found is not None and found.kind == "consequence" and found.premises == ("link-line",)


def test_a_result_used_for_a_further_quantity_or_a_further_bound_is_no_asserted_result():
    from epinoic_logic.translate.restatement import calculation_results
    assert [w for _v, w in calculation_results("r³ = (5.000 × 10⁶ m)³ = 1.250 × 10²⁰ m³")] == ["1.250 × 10²⁰ m³"]
    assert calculation_results("The radius is 5.000 × 10⁶ m.") == ()
    band = {"op": "and", "args": [{"op": "ge", "left": V("x"), "right": R("4.95")}, {"op": "lt", "left": V("x"), "right": R("5.05")}]}
    asserted = problem([premise("P", {"op": "eq", "left": V("x"), "right": R("5")}, "arithmetic_fact")], band)
    assert semantic_restatement(asserted, claim_text="x = 10/2 = 5.0").kind == "full"
    assert semantic_restatement(asserted, claim_text="x = 5.0") is None          # no calculation written: a transcription
    further = problem([premise("P", {"op": "eq", "left": V("x"), "right": R("5")}, "arithmetic_fact")], {"op": "gt", "left": V("x"), "right": R("3")})
    assert semantic_restatement(further, claim_text="x = 10/2 = 5, so x > 3") is None   # a bound the engine derives from the value
    force = problem([premise("A", {"op": "eq", "left": V("a"), "right": R("5")}, "arithmetic_fact"),
                     premise("F", {"op": "eq", "left": V("f"), "right": {"op": "mul", "args": [R("2"), V("a")]}}, "general_knowledge")],
                    {"op": "eq", "left": V("f"), "right": R("10")}, symbols=(("a", "Real"), ("f", "Real")))
    assert semantic_restatement(force, claim_text="a = 20/4 = 5 m s⁻², so F = 2 × 5 = 10 N") is None   # the engine computes F from a
    labelled = problem([premise("P", {"op": "eq", "left": V("x"), "right": R("5")}, "task_setting")], band)
    assert semantic_restatement(labelled, claim_text="x = 10/2 = 5.0") is None   # a task label on a figure stays an unverified dependency
