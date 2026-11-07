"""Minor findings of the round-8 clearance (integrated round c1) fixed by the core fixer, each with a positive case from
the round and a control:

* false argument warnings on correct answers: an "each" over a stated pair read as an open universal (bi-t14 s5.1,
  ARG-HG-001), a cause the text is said to present read as the writer's causal claim (ll-t14 p1-point, ARG-CL-001), a
  letter named in a quotation ("Just the A", en-t14 p2-point) read as a placeholder, and a number word of the text's
  language ("con catorce alumnos", sp-t14 g3.1) read as no figure (both EVD-SRC-003 through the grounding check);
* mark-scheme codes ("M1", "A1") counted as figures, so a mark annotation became a QUANTITATIVE_CLAIM;
* a numeral with a base-ten subscript ("181₁₀") read as no figure by the synthesis ledger;
* an altered quotation of the request's own words, with no text supplied, named only as unverifiable (ps-t14).
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.integrity import ledger as L
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SuppliedText
from epinoic_logic.translate.eligibility import decide_eligibility, figure_text
from epinoic_logic.translate.grounding import check_problem_grounding

from .test_argument_diagnostics import B, IMP, P, V, codes, problem, run
from ..channel.c1_core_support import SPEC, deliver


# ----------------------------------------------------------------------------------------------------- argument rules


def test_each_over_a_stated_pair_is_no_hasty_generalisation():
    meanings = B(shared="both species may need the same abiotic conditions, such as soil moisture or pH",
                 more_likely="each species is more likely to occur where the other is found")
    p = problem([P("sp-shared", V("shared"), "both species may need the same abiotic conditions"),
                 P("link-likely", IMP(V("shared"), V("more_likely")), "so each is more likely to occur where the other is found", note="link: so")],
                V("more_likely"), meanings)
    r = run(p)
    assert r.status is S.ENTAILED and "ARG-HG-001" not in codes(r)
    # control: an "each" drawn from one instance with no pair stated is still a hasty generalisation
    control = B(seen="the one quadrat sampled in 2023 contained orchids", each="each quadrat of the meadow contains orchids")
    q = problem([P("e", V("seen"), "the one quadrat sampled in 2023 contained orchids"),
                 P("l", IMP(V("seen"), V("each")), "so each quadrat of the meadow contains orchids", note="link: so")], V("each"), control)
    assert codes(run(q)).get("ARG-HG-001") == "warning"


def test_a_cause_the_text_presents_is_no_causal_leap():
    meanings = B(e710="the heading '7 IN 10' appears", e23="the heading '+23 MINUTES' appears before bed",
                 cause="the phone is made to look like the cause of lost sleep")
    p = problem([P("ev-710", V("e710"), "'7 IN 10' is the first figure heading", kind="quotation", verified=True),
                 P("ev-23", V("e23"), "'+23 MINUTES' is a figure heading about phone use before bed", kind="quotation", verified=True),
                 P("link-cause", IMP({"op": "and", "args": [V("e710"), V("e23")]}, V("cause")), "the figures present the phone as the cause of lost sleep", note="link: so")],
                V("cause"), meanings)
    assert "ARG-CL-001" not in codes(run(p))
    # control: the writer's own causal reading of a sequence is still a leap
    control = B(before="students used phones before bed in 2023", worse="phone use caused worse sleep in 2024")
    q = problem([P("e", V("before"), "students used phones before bed in 2023", kind="quotation", verified=True),
                 P("l", IMP(V("before"), V("worse")), "after that, phone use caused worse sleep", note="link: so")], V("worse"), control)
    assert codes(run(q)).get("ARG-CL-001") == "warning"


# ----------------------------------------------------------------------------------------------------- grounding readings


def _grounded(premise_expr: dict, meaning: str, document: str, excerpt: str, *, sort: str = "Bool", name: str = "q"):
    doc = SuppliedText(document_id="doc", text=document)
    p = Problem.model_validate({
        "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
        "symbols": [{"name": name, "sort": sort, "meaning": meaning}],
        "premises": [{"id": "ev", "expr": premise_expr, "label": meaning,
                      "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc", "excerpt": excerpt}], "certainty": "established"}}],
        "conclusion": {"id": "C", "expr": premise_expr}})
    g, checks = check_problem_grounding(p, [doc])
    return g.premises[0].grounding.verified, [c for c in checks if c.target_id == "ev"]


def test_a_letter_named_in_a_quotation_is_content_not_a_placeholder():
    verified, checks = _grounded(V("q"), "the mother says 'Just the A'", "MOTHER: Just the A. Nothing else matters.", "Just the A")
    assert verified is True, [c.detail for c in checks]
    # control: an excerpt of function words alone is still a placeholder
    verified, checks = _grounded(V("q"), "the mother praises the result", "MOTHER: Just the A. Nothing else matters.", "Just the")
    assert verified is False and any("placeholder" in (c.detail or "") for c in checks)


def test_a_number_word_of_the_texts_language_grounds_its_figure():
    eq14 = {"op": "eq", "left": V("pupils"), "right": {"op": "int", "value": "14"}}
    text = "La escuela reabrió en 2020 con catorce alumnos y una maestra."
    verified, checks = _grounded(eq14, "pupils at the school when it reopened", text, "con catorce alumnos", sort="Int", name="pupils")
    assert verified is True, [c.detail for c in checks]
    eq15 = {"op": "eq", "left": V("pupils"), "right": {"op": "int", "value": "15"}}
    verified, checks = _grounded(eq15, "pupils at the school when it reopened", text, "con catorce alumnos", sort="Int", name="pupils")
    assert verified is False and any("does not state the premise's figures" in (c.detail or "") for c in checks)


# ----------------------------------------------------------------------------------------------------- eligibility


@pytest.mark.parametrize("text", ["M1 for substituting into the formula, A1 for the correct answer.", "B1 for the axes; M1A1 for the gradient.", "Award A1ft."])
def test_mark_scheme_codes_are_no_figures(text):
    claim = ClaimRecord(claim_id="m1", request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics: Analysis and Approaches",
                        task_type="structured_question", claim_text=text, claim_role="quantitative", materiality="material")
    assert not decide_eligibility(claim).eligible
    assert not any(ch.isdigit() for ch in figure_text(text))


def test_a_claim_with_figures_beside_its_mark_codes_stays_quantitative():
    claim = ClaimRecord(claim_id="m1", request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Mathematics: Analysis and Approaches",
                        task_type="structured_question", claim_text="M1 for 3 × 4 = 12, A1 for the answer 12.", claim_role="quantitative", materiality="material")
    assert decide_eligibility(claim).eligible
    assert "B12" in figure_text("Vitamin B12 is needed.")


# ----------------------------------------------------------------------------------------------------- the ledger's figures


def test_a_base_ten_subscript_numeral_is_a_figure():
    assert [f.label for f in L._figures("The answer is 181₁₀ in denary.")] == ["181"] == [f.label for f in L._figures("The answer is 181 in denary.")]
    assert [f.label for f in L._figures("10110101₂ is 181₁₀.")] == ["181"]  # a numeral in another base stays unread
    assert [f.label for f in L._figures("CO₂ rose to 420 ppm")] == ["420"]


# ----------------------------------------------------------------------------------------------------- the request's own words


def test_an_altered_quotation_of_the_request_is_named_when_no_text_was_supplied():
    text = SPEC["ps-t14"]["response_text"]
    assert "his hands sweat" in text
    _h, _c, _r, rc = deliver("ps-t14", text.replace("his hands sweat", "his handsly sweat", 1))
    [f] = [x for x in rc.findings if x.code == "INT-REQ-003"]
    assert "the request holds all of its words but 'handsly'" in f.message and "nor in the request" in f.message
    assert any(sf.code == "CORE-SRC-003" for sf in rc.structural_findings)  # kept beside it: no supplied text holds it either
    _h, _c, _r, rc0 = deliver("ps-t14")
    assert "INT-REQ-003" not in [x.code for x in rc0.findings]
