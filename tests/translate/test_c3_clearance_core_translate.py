"""Translation fidelity found wanting by the round-10 clearance overseers (integrated round c3), fixed by the core fixer: four
encodings that are not the claim's were displayed ENTAILED with no finding naming the fault (the translation-fidelity lens's
reference, causes F, S, CIRC and D):

* sp-t16 g1.22 concluded a premise restated and a rule's consequent while the claim's point, the correction 'vemos' -> 'veamos',
  sat in a declared symbol nothing used (flag ``consequence_unchecked``);
* ess-t16 s7.1 asserted its conjunct 'its costs fall on particular groups' as a writer's premise on the conjunct's own symbol,
  though the supporting claim s10.2 states the costs (flag ``conjunct_asserted``);
* bm-t16 g15.3 asserted the claim's own two conditionals as premises and concluded a weakening of one (the translator's E112,
  rule link-weakening);
* ph-t16 s2.8 ("A gas-law ratio needs kelvin, so the ratio is 308/290, not 35/17") checked only 308/290 != 35/17 (flag
  ``reason_not_encoded``).

Each now reaches the router as no verdict on the claim, with the reason named. The controls keep faithful encodings of the same
shapes as they were. The recorded material is in ``tests/channel/data/c3_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate import fidelity as F
from epinoic_logic.translate.contracts import ClaimRecord
from epinoic_logic.translate.restatement import semantic_restatement

from ..channel.c3_core_support import C3, deliver_c3, translations
from ..core_hostile import SHAPES, one, sweep


def outcome(rc, cid: str):
    return next(o for o in rc.outcomes if o.claim_id.split("@")[0] == cid)


def flags(o) -> list[str]:
    interp = o.translation.interpretation
    return [f.code for f in (interp.ambiguity_flags if interp else [])]


@pytest.mark.parametrize("task,cid,status,flag", [
    ("sp-t16", "g1.22", "AMBIGUOUS_TRANSLATION", "consequence_unchecked"),
    ("ess-t16", "s7.1", "AMBIGUOUS_TRANSLATION", "conjunct_asserted"),
    ("ph-t16", "s2.8", "AMBIGUOUS_TRANSLATION", "reason_not_encoded"),
    ("bm-t16", "g15.3", "INVALID_FORMALIZATION", None),
])
def test_the_four_c3_encodings_that_are_not_their_claims_are_no_verdict(task, cid, status, flag):
    hub, _ch, _reply, rc = deliver_c3(task, translations(task))
    hub.close()
    o = outcome(rc, cid)
    assert o.display_status.value == status, (o.display_status, flags(o), o.translation.diagnostics[:3] if hasattr(o.translation, "diagnostics") else None)
    if flag is not None:
        assert flag in flags(o)
    # a claim that is no verdict is never shown as one on the receipt
    assert any(f.code == "INT-REQ-006" and any(c.split("@")[0] == cid for c in f.claim_ids) for f in rc.findings)


def _problem(premises, conclusion, symbols, *, claim_id="c1") -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": claim_id, "query": "entailment", "symbols": symbols,
                                   "premises": premises, "conclusion": conclusion})


def _b(name: str) -> dict:
    return {"op": "var", "name": name}


def _claim(text: str, cid: str = "c1", role: str = "point", supports=()) -> ClaimRecord:
    return ClaimRecord.model_validate({"claim_id": cid, "request_id": "r", "task_id": "t", "report_id": "rep", "agent_id": "a", "subject": "Business Management",
                                       "task_type": "short_answer", "claim_text": text, "claim_role": role, "materiality": "material",
                                       "supporting_claim_ids": list(supports)})


def test_link_weakening_is_e112_and_a_conditional_derived_from_two_links_is_not():
    g = {"kind": "specialist_inference"}
    syms = [{"name": n, "sort": "Bool"} for n in ("t", "a", "e")]
    weakened = _problem([{"id": "link_a", "expr": {"op": "implies", "left": {"op": "not", "arg": _b("t")}, "right": _b("a")}, "grounding": g},
                         {"id": "link_b", "expr": {"op": "implies", "left": _b("a"), "right": _b("e")}, "grounding": g}],
                        {"id": "C", "expr": {"op": "implies", "left": {"op": "not", "arg": _b("t")}, "right": {"op": "implies", "left": _b("a"), "right": _b("e")}}}, syms)
    found = semantic_restatement(weakened)
    assert found is not None and found.kind == "full" and found.premises == ("link_b",) and "link-weakening" in found.how[0][1]
    # control: the chain ¬t -> a, a -> e gives ¬t -> e, which no single link states: the engine decides it, as before
    chained = weakened.model_copy(update={"conclusion": weakened.conclusion.model_copy(update={"expr": Problem.model_validate({
        "problem_id": "q", "request_id": "r", "claim_id": "c1", "query": "consistency", "symbols": syms,
        "premises": [{"id": "x", "expr": {"op": "implies", "left": {"op": "not", "arg": _b("t")}, "right": _b("e")}}]}).premises[0].expr})})
    assert semantic_restatement(chained) is None
    # control: a link packed with its antecedent argues (it is no link of this kind), as before
    packed = _problem([{"id": "p", "expr": {"op": "and", "args": [_b("a"), {"op": "implies", "left": _b("a"), "right": _b("e")}]}, "grounding": g}],
                      {"id": "C", "expr": _b("e")}, syms)
    assert semantic_restatement(packed) is None


def test_controls_the_new_readers_leave_faithful_shapes_alone():
    # a reason the encoding checks itself ("The division is exact, so no extra packet is needed": 6000000 mod 1500 = 0, c2 cs-t15 c4.5)
    file6 = {"op": "var", "name": "file6"}
    p = _problem([{"id": "f", "expr": {"op": "eq", "left": file6, "right": {"op": "int", "value": "6000000"}}, "grounding": {"kind": "arithmetic_fact"}}],
                 {"id": "C", "expr": {"op": "eq", "left": {"op": "mod", "left": file6, "right": {"op": "int", "value": "1500"}}, "right": {"op": "int", "value": "0"}},
                  "label": "the division is exact and no extra packet is needed"},
                 [{"name": "file6", "sort": "Int", "meaning": "the file in bytes"}])
    assert F.reason_not_encoded(p, _claim("The division is exact, so no extra packet is needed.")) is None
    # an unused symbol the conclusion's label states no consequence for (c3 ch-t16 s4.2's 'c_dil', faithful)
    c = {"op": "var", "name": "c"}
    p = _problem([{"id": "d", "expr": {"op": "eq", "left": c, "right": {"op": "div", "left": {"op": "real", "value": "0.00224"}, "right": {"op": "real", "value": "0.025"}}},
                   "grounding": {"kind": "arithmetic_fact"}}],
                 {"id": "C", "expr": {"op": "eq", "left": c, "right": {"op": "real", "value": "0.0896"}}, "label": "c(diluted) = 2.24 x 10^-3 / 0.02500 = 0.0896 mol dm^-3"},
                 [{"name": "c", "sort": "Real", "meaning": "the quotient"}, {"name": "c_dil", "sort": "Real", "meaning": "concentration of the diluted vinegar",
                                                                                 "grounding": {"kind": "specialist_inference"}}])
    assert F.consequence_unchecked(p, _claim("c(diluted) = 2.24 x 10^-3 / 0.02500 = 0.0896 mol dm^-3")) is None
    # a conjunct asserted by the writer that no supporting claim states (the writer's own judgement, not the support's content)
    syms = [{"name": "plausible", "sort": "Bool", "meaning": "the biological conclusion is plausible"}, {"name": "tested", "sort": "Bool"}, {"name": "done", "sort": "Bool"}]
    p = _problem([{"id": "pl", "expr": _b("plausible"), "grounding": {"kind": "specialist_inference"}},
                  {"id": "t", "expr": _b("tested"), "grounding": {"kind": "quotation", "verified": True}},
                  {"id": "l", "expr": {"op": "implies", "left": _b("tested"), "right": _b("done")}, "grounding": {"kind": "specialist_inference"}}],
                 {"id": "C", "expr": {"op": "and", "args": [_b("plausible"), _b("done")]}}, syms)
    support = [_claim("A t test of the adrenaline increase gives t = 5.41.", cid="g5.2", role="analysis")]
    assert F.conjunct_asserted(p, _claim("The conclusion is plausible but not established.", supports=["g5.2"]), support) is None


def _entries(text: str):
    text = "x " + text  # a claim and a label are never blank
    claim = _claim(text[:4000])
    syms = [{"name": "r", "sort": "Real", "meaning": text[:1000]}, {"name": "unused", "sort": "Bool", "meaning": text[:1000]},
            {"name": "k", "sort": "Bool", "meaning": text[:1000]}]
    r = {"op": "var", "name": "r"}
    p = _problem([{"id": "d", "expr": {"op": "eq", "left": r, "right": {"op": "real", "value": "2"}}, "label": text[:1000]},
                  {"id": "k", "expr": _b("k"), "label": text[:1000]}],
                 {"id": "C", "expr": {"op": "and", "args": [{"op": "gt", "left": r, "right": {"op": "real", "value": "1"}}, _b("k")]}, "label": text[:1000]}, syms)
    support = [_claim(text[:4000], cid="s2", role="analysis")]
    yield "consequence_unchecked", lambda: F.consequence_unchecked(p, claim)
    yield "conjunct_asserted", lambda: F.conjunct_asserted(p, claim, support)
    yield "reason_not_encoded", lambda: F.reason_not_encoded(p, claim)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c3_fidelity_readers(shape):
    """The readers this pass added, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


# ------------------------------------------------------------------ minors of this pass (cheap and safe)

def test_partial_encoding_skips_a_reading_that_names_another_claim_by_its_id():
    """c1 bug r8-17 (still open in c3): hi-p10b h1.1 'Supporting claims h1.2 (quota, price setting) and h1.6 (famine) are not encoded
    here' and mai-t16 m26.1 'its nonlinear derivation in m24.1 is not encoded' were withheld though the claims are fully encoded."""
    from epinoic_logic.translate.contracts import Interpretation
    from epinoic_logic.translate.pipeline import partial_encoding
    p = _problem([{"id": "a", "expr": _b("a")}], {"id": "C", "expr": _b("a")}, [{"name": "a", "sort": "Bool"}])
    h11 = ("Under War Communism (1918-1921) the Bolshevik government tried to control grain by abolishing the free market in it: a state monopoly "
           "was declared, private grain trade was banned, and food detachments seized surplus grain from peasants.")
    m261 = "Total saving on $2.5 \\times 10^6$ cans $= 2.5 \\times 10^6 \\times 6.2330\\ldots = 1.5583 \\times 10^7$ cm²"
    for cid, text, reading in (("h1.1", h11, "The three measures as premises. Supporting claims h1.2 (quota, price setting) and h1.6 (famine) are not encoded here."),
                               ("m26.1", m261, "The per-can saving is taken as the specialist's stated value (its nonlinear derivation in m24.1 is not encoded), "
                                               "and the total is checked against 1.5583 x 10^7.")):
        assert partial_encoding(p, _claim(text, cid=cid), Interpretation(reading=reading)) is None, cid
    # control: a part of this claim named beside another claim's id is still this claim's part (ge-t16 g5.2, a fair withhold)
    g52 = ("More than 130 deaths in two collapsed buildings suggest that building standards protect only as well as they are enforced on each "
           "building, whereas Haiti had no codes to enforce at all.")
    flag = partial_encoding(p, _claim(g52, cid="g5.2"), Interpretation(reading="The whereas clause (Haiti had no codes to enforce) restates a fact that is "
                                                                                 "carried in g5.1 and is not encoded here as a separate relation."))
    assert flag is not None and flag.code == "partial_encoding"
    # control: a part of the claim itself left out is still named, the claim's own id included
    flag = partial_encoding(p, _claim("x", cid="h1.1"), Interpretation(reading="The 'likely cause' of h1.1 is an interpretation and is not encoded."))
    assert flag is not None and flag.code == "partial_encoding"


@pytest.mark.parametrize("text,flagged", [
    ("A time slice that is too short means the processor spends more time switching, so throughput falls.", False),   # cs-t16 c13.1
    ("A small k, such as k = 1, classifies each item by its nearest neighbour, so the boundary follows the noise.", False),  # cs-p10a c10.1
    ("Fewer products and more reactants are present at equilibrium, so Kc falls.", True),                              # the c2 control, ch-t15 s15.4
    ("A 5% rise adds $375, so it covers only part of the outflow.", True),                                             # a figure: no generic subject
])
def test_a_generic_statement_is_conditional_in_its_meaning(text, flagged):
    from epinoic_logic.translate.pipeline import conditional_conclusion
    p = _problem([{"id": "l", "expr": {"op": "implies", "left": _b("a"), "right": _b("b")}}], {"id": "C", "expr": {"op": "implies", "left": _b("a"), "right": _b("b")}},
                 [{"name": "a", "sort": "Bool"}, {"name": "b", "sort": "Bool"}])
    assert (conditional_conclusion(p, _claim(text)) is not None) is flagged


def test_a_month_name_states_its_number_only_for_a_symbol_about_a_date():
    """cs-t16: every premise 'P1 burst time is 5 ms' was validated by the request's 'May' (in 'my exams are in May 2027'); the task's
    own '5 ms' validates it now, and a symbol about a month is still validated by the month's name."""
    from epinoic_logic.translate.contracts import TaskRecord
    from epinoic_logic.translate.grounding import check_problem_grounding
    task = TaskRecord.of("t", "r", "My exams are in May 2027. Process P1 has a burst time of 5 ms and P2 of 3 ms.")
    p = _problem([{"id": "tb1", "expr": {"op": "eq", "left": {"op": "var", "name": "tb1"}, "right": {"op": "int", "value": "5"}}, "grounding": {"kind": "task_setting"}},
                  {"id": "mo", "expr": {"op": "eq", "left": {"op": "var", "name": "exam_month"}, "right": {"op": "int", "value": "5"}}, "grounding": {"kind": "task_setting"}}],
                 {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "tb1"}, "right": {"op": "int", "value": "3"}}},
                 [{"name": "tb1", "sort": "Int", "meaning": "P1 burst time, ms"}, {"name": "exam_month", "sort": "Int", "meaning": "the month of the exams"}])
    checks = {c.target_id: c for c in check_problem_grounding(p, [], task=task)[1]}
    assert checks["tb1"].verified is True and "'5 ms'" in checks["tb1"].detail and "'May'" not in checks["tb1"].detail, checks["tb1"].detail
    assert checks["mo"].verified is True and "'May'" in checks["mo"].detail, checks["mo"].detail
