"""Integrity behaviour found wanting by the round-9 clearance overseers (integrated round c2), fixed by the core fixer:

* critical: a real contradiction was not charged when the two translations glossed the shared symbol with synonyms ('Kc
  decreases' against 'Kc falls': INT-GLOSSARY-005 and INT-CONFLICT-004), and paraphrased glosses of one quantity filled the
  receipts with INT-GLOSSARY-005 ('worst-case net outcome' against 'worst outcome' with one figure, 'the distilled-water
  cylinder' against 'distilled water', 'more surface runoff occurs' against 'more rain runs straight off the surface');
* critical: a value a claim evaluates or checks at ("at x = 0", maa-t15 m5.3) was pooled as an assertion about the unknown
  another claim solves for (rule evaluation-point);
* critical: the student-facing text's list marker '3)' was read as a figure no claim states (INT-LEDGER-023, hi-t15);
* major: a figure written in Spanish words and changed by the combinator ('tres de la madrugada' as 'dos de la madrugada')
  crossed with no figure finding;
* minor: several locator-less excerpts of one document carried verbatim were charged INT-LEDGER-020.

The recorded material is in ``tests/channel/data/c2_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.cross_check import (
    check_cross_report_consistency, evaluation_points, gloss_content, gloss_difference, gloss_reading, rename_evaluation_points_apart,
)
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
C2 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "c2_core_material.json").read_text())


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def conflicts(findings) -> list[tuple[str, str, list[str]]]:
    return [(f.code, f.severity, sorted(f.claim_ids)) for f in findings if f.code.startswith("INT-CONFLICT")]


# ------------------------------------------------------------ critical: synonyms and paraphrases are one quantity


@pytest.mark.parametrize("a,b", [
    ("Kc decreases", "Kc falls"),                                                            # ch-t15 kc_falls
    ("option A's worst-case net outcome (-$20,000)", "option A's worst outcome (-$20,000)"),   # bm-t15 a_worst
    ("option B's worst-case net outcome (-$5,000)", "option B's worst outcome (-$5,000)"),     # bm-t15 b_worst
    ("percentage change in mass of the distilled-water cylinder", "percentage change in mass, distilled water"),  # bi-p9b pct_dw
    ("more surface runoff occurs", "more rain runs straight off the surface"),                # ge-p9c, ess-p9c runoff_up
    ("the price rises", "the price increases"), ("output drops", "output declines"), ("Kc decreases when the temperature rises", "Kc decreases"),
])
def test_synonyms_and_paraphrases_of_one_quantity_are_one_gloss(a, b):
    assert gloss_difference(a, b) is None and gloss_difference(b, a) is None


@pytest.mark.parametrize("a,b,why", [
    ("Kc increases", "Kc decreases", "role words"),           # synonyms fold to the two members of one role group, never to one
    ("the price rises", "the price falls", "role words"),
    ("pre-tariff price", "post-tariff price", "role words"),
    ("non-renewable resources", "renewable resources", "negates"),
    ("marks allocated to part (a)", "marks allocated to part (c)", "part labels"),
    ("speed of the cart", "speed of the ball", "content"),
    ("the Price of Steel in 2019", "the price of copper in 2019", "content"),
    ("option A's worst outcome (-$20,000)", "option A's worst outcome (-$25,000)", "figures"),
])
def test_glosses_of_different_quantities_still_stay_apart(a, b, why):
    found = gloss_difference(a, b)
    assert found is not None and why in found, found


def _bool_claim(cid: str, meaning: str, positive: bool, name: str = "kc_falls") -> Problem:
    e = {"op": "var", "name": name}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": name, "sort": "Bool", "meaning": meaning}],
                                   "premises": [{"id": "pr", "expr": e if positive else {"op": "not", "arg": e}}]})


@pytest.mark.parametrize("g1,g2", [("Kc decreases when the temperature rises", "Kc decreases when the temperature rises"), ("Kc decreases", "Kc falls")])
def test_e8_kc_decreases_against_kc_does_not_fall_is_int_conflict_001_with_synonym_glosses(g1, g2):
    """exchanges9 E8: s15.1 'Kc decreases.' against a closing line that denies it ('so Kc does not fall', s15.4)."""
    _res, f = check_cross_report_consistency([_bool_claim("s15.1", g1, True), _bool_claim("s15.4", g2, False)], request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["s15.1", "s15.4"])] and "INT-GLOSSARY-005" not in codes(f)


@pytest.mark.parametrize("gloss", ["the bus boycott began on 5 December 1955", "the Montgomery bus boycott began on 5 December 1955"])
def test_x17_both_round_8_forms_stay_int_conflict_001(gloss):
    _res, f = check_cross_report_consistency([_bool_claim("h1.2", "the bus boycott began on 5 December 1955", True, "b"), _bool_claim("p4-s04", gloss, False, "b")],
                                             request_id="req-x", config=CFG)
    assert conflicts(f) == [("INT-CONFLICT-001", "error", ["h1.2", "p4-s04"])]


def test_a_part_label_difference_is_still_read_apart():
    _res, f = check_cross_report_consistency([_bool_claim("m1", "marks allocated to part (a)", True, "marks_ok"), _bool_claim("m2", "marks allocated to part (c)", False, "marks_ok")],
                                             request_id="req-x", config=CFG)
    assert "INT-CONFLICT-001" not in codes(f) and "INT-GLOSSARY-005" in codes(f)


def test_the_recorded_c2_glosses_read_as_one_quantity():
    for task, cid in (("ch-t15", "s15.1"), ("ch-t15", "s15.4")):
        p = Problem.model_validate(C2["translations"][task][cid]["problem"])
        assert any(s.name == "kc_falls" for s in p.symbols)
    a = Problem.model_validate(C2["translations"]["ch-t15"]["s15.1"]["problem"])
    b = Problem.model_validate(C2["translations"]["ch-t15"]["s15.4"]["problem"])
    _res, f = check_cross_report_consistency([a, b], request_id="req-ch-t15", config=CFG)
    assert "INT-GLOSSARY-005" not in codes(f), [x.message[:200] for x in f if x.code == "INT-GLOSSARY-005"]


def test_gloss_content_folds_hyphens_synonyms_and_fillers():
    assert gloss_content("Kc decreases") == gloss_content("Kc falls") == frozenset({"kc", "fall"})
    assert {"distill", "water"} <= gloss_content("the distilled-water cylinder")
    assert "occur" not in gloss_content("more surface runoff occurs")
    assert gloss_reading("non-renewable stock").negated is True


# ----------------------------------------------------------------------------- critical: a value a claim checks at


def _recorded(task: str, cid: str) -> Problem:
    return Problem.model_validate(C2["translations"][task][cid]["problem"])


def test_maa_t15_m5_3_checks_at_a_point_and_m7_1_solves_for_the_unknown():
    m53, m71 = _recorded("maa-t15", "m5.3"), _recorded("maa-t15", "m7.1")
    assert evaluation_points(m53) == {"x": ("q5-x0", 0)} and evaluation_points(m71) == {}
    renamed, info = rename_evaluation_points_apart([m53, m71])
    assert renamed[1] is m71 and info == {"m5.3": [("x", "x_at_0", "q5-x0")]}
    assert {s.name for s in renamed[0].symbols} == {"x_at_0", "gx_at_0", "hg_x_at_0"}  # g and h at the point, read apart with it
    _res, f = check_cross_report_consistency([m53, m71], request_id="req-maa-t15", config=CFG)
    assert [c[:2] for c in conflicts(f)] == [("INT-CONFLICT-004", "warning")]
    [u] = [x for x in f if x.code == "INT-CONFLICT-004"]
    assert sorted(u.claim_ids) == ["m5.3", "m7.1"] and "rule evaluation-point" in u.message


def _point(cid: str, value: str, result: str, *, label: str = "at x = {v}, f(x) = {r}", prem: str = "the check is made at x = {v}") -> Problem:
    x, fx = {"op": "var", "name": "x"}, {"op": "var", "name": "fx"}
    return Problem.model_validate({
        "problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": "x", "sort": "Real", "meaning": "the free variable of f"}, {"name": "fx", "sort": "Real", "meaning": "f(x) = 2x + 3"}],
        "premises": [{"id": "pt", "expr": {"op": "eq", "left": x, "right": {"op": "real", "value": value}}, "label": prem.format(v=value)},
                     {"id": "def", "expr": {"op": "eq", "left": fx, "right": {"op": "add", "args": [{"op": "mul", "args": [{"op": "real", "value": "2"}, x]},
                                                                                                    {"op": "real", "value": "3"}]}}}],
        "conclusion": {"id": "c", "expr": {"op": "eq", "left": fx, "right": {"op": "real", "value": result}}, "label": label.format(v=value, r=result)}})


def _solve(cid: str, value: str) -> Problem:
    x = {"op": "var", "name": "x"}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": "x", "sort": "Real", "meaning": "the free variable of f"}],
                                   "premises": [{"id": "sol", "expr": {"op": "eq", "left": x, "right": {"op": "real", "value": value}}, "label": f"the root is x = {value}"}]})


def test_the_evaluation_point_rule_keeps_every_real_contradiction():
    # two checks at the same point that disagree share the point: still the specialists' contradiction
    _res, f = check_cross_report_consistency([_point("m1", "0", "3"), _point("m2", "0", "4")], request_id="req-x", config=CFG)
    assert ("INT-CONFLICT-001", "error", ["m1", "m2"]) in conflicts(f) or ("INT-CONFLICT-005", "error", ["m2"]) in conflicts(f)
    # a check that refutes itself is still the specialist's (INT-CONFLICT-005)
    _res, f = check_cross_report_consistency([_point("m1", "0", "5"), _solve("m7", "-5")], request_id="req-x", config=CFG)
    assert ("INT-CONFLICT-005", "error", ["m1"]) in conflicts(f)
    # the same encoding with no word of an evaluation point is an assertion about the unknown: INT-CONFLICT-001
    plain = _point("m1", "0", "3", label="f(x) = {r}", prem="x is {v}")
    assert evaluation_points(plain) == {}
    _res, f = check_cross_report_consistency([plain, _solve("m7", "-5")], request_id="req-x", config=CFG)
    assert ("INT-CONFLICT-001", "error", ["m1", "m7"]) in conflicts(f)
    # a check at a point beside the root another claim states: no contradiction charged
    _res, f = check_cross_report_consistency([_point("m1", "0", "3"), _solve("m7", "-5")], request_id="req-x", config=CFG)
    assert not [c for c in conflicts(f) if c[0] == "INT-CONFLICT-001"]


# ------------------------------------------------------------------------------ critical: list markers (hi-t15)


def _synthesis(claims: list[str], sid: str = "syn-hi-t15") -> Synthesis:
    text = " ".join(claims)
    return Synthesis(synthesis_id=sid, request_id="req", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=["rep"],
                     claims=[SynthesizedClaim(claim_id=f"s{i}", text=t, certainty="probable", source_claim_ids=[f"h{i}"], transformation="carried") for i, t in enumerate(claims)],
                     ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-11-09T09:00:00Z")


def test_the_hi_t15_synthesis_text_is_its_claims_joined_and_draws_no_int_ledger_023():
    claims = [c["text"] for c in C2["syntheses"]["hi-t15"]["claims"]]
    assert any(c.startswith("3) ") for c in claims)
    assert "INT-LEDGER-023" not in codes(L._text_coverage(_synthesis(claims)))
    # the minimal pair of the audit: the marker is read alike in the claim and in the joined text
    assert L.figure_tokens("3) Replace X.") == set() and L.figure_tokens(L.without_claim_markers("... timing. 3) Replace X with Y.", ["... timing.", "3) Replace X with Y."])) == set()
    assert "INT-LEDGER-023" not in codes(L._text_coverage(_synthesis(["The plan is late on timing.", "3) Replace X with Y."])))
    assert "INT-LEDGER-023" not in codes(L._text_coverage(_synthesis(["The plan is late on timing.", "3. Replace X with Y."])))
    # controls: a figure the text adds, and a number that opens no claim, are still figures
    s = _synthesis(claims)
    text = s.text + " About 650,000 troops took part."
    [f] = [x for x in L._text_coverage(s.model_copy(update={"text": text, "text_sha256": sha256_text(text)})) if x.code == "INT-LEDGER-023"]
    assert "650000" in f.message or "650,000" in f.message
    assert L.without_claim_markers("The score was 7 (2) Do B.", ["The score was 7", "Do B."]) == "The score was 7 (2) Do B."


# ------------------------------------------------------------------------------- major: Spanish number words


@pytest.mark.parametrize("text,figures", [
    ("hasta las tres de la madrugada", {"3"}), ("hasta las dos de la madrugada", {"2"}), ("a la una", {"1"}), ("catorce viviendas", {"14"}),
    ("dos mil trescientos cuarenta y cinco turistas", {"2345"}), ("más de cinco familias", {"5"}),
    ("una casa con dos plantas", set()), ("once a year", set()), ("the mil-spec part", set()),
])
def test_spanish_number_words_are_figures(text, figures):
    assert L.figure_tokens(text) == figures


def _sp_report(text: str) -> SpecialistReport:
    ids = dict(request_id="req", task_id="t", report_id="rep", agent_id="language-b-spanish-specialist", subject="Language B: Spanish", task_type="written_task")
    return SpecialistReport.model_validate(dict(ids, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-09T09:00:00Z",
                                                claims=[dict(ids, claim_id="g1.1", claim_text=text, claim_role="point", materiality="material")]))


@pytest.mark.parametrize("transformation", ["carried", "paraphrased"])
def test_sp_t15_a_changed_hour_in_words_is_int_ledger_023_whatever_the_label(transformation):
    source = "Tampoco es razonable que el ruido de las terrazas continúe hasta las tres de la madrugada."
    changed = source.replace("las tres", "las dos")
    s = Synthesis(synthesis_id="syn", request_id="req", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=["rep"],
                  claims=[SynthesizedClaim(claim_id="s0", text=changed, certainty="established", source_claim_ids=["g1.1"], transformation=transformation)],
                  ledger=[], text=changed, text_sha256=sha256_text(changed), created_at="2026-11-09T09:00:00Z")
    f = L.check_synthesis_ledger([_sp_report(source)], s)
    assert "INT-LEDGER-023" in codes(f), [(x.code, x.message[:160]) for x in f]
    faithful = s.model_copy(update={"claims": [s.claims[0].model_copy(update={"text": source})], "text": source, "text_sha256": sha256_text(source)})
    assert "INT-LEDGER-023" not in codes(L.check_synthesis_ledger([_sp_report(source)], faithful))


# -------------------------------------------------------------------- minor: excerpts compared per document as a set


def test_several_locator_less_excerpts_of_one_document_carried_verbatim_are_no_altered_excerpt():
    text = "The cylinders in distilled water gained mass and those in 1.0 mol dm-3 sucrose lost mass."
    ids = dict(request_id="req", task_id="t", report_id="rep", agent_id="biology-specialist", subject="Biology", task_type="data_based_question")
    refs = [{"document_id": "doc-osmosis", "excerpt": e} for e in ("distilled water", "1.0 mol dm-3 sucrose", "gained mass", "lost mass")]
    rep = SpecialistReport.model_validate(dict(ids, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-09T09:00:00Z",
                                               claims=[dict(ids, claim_id="s2.1", claim_text=text, claim_role="point", materiality="material", source_refs=refs)]))
    s = Synthesis(synthesis_id="syn", request_id="req", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=["rep"],
                  claims=[SynthesizedClaim(claim_id="s0", text=text, certainty="established", source_claim_ids=["s2.1"], transformation="carried", evidence_refs=refs)],
                  ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-11-09T09:00:00Z")
    assert "INT-LEDGER-020" not in codes(L.check_synthesis_ledger([rep], s))
    # control: an excerpt the synthesis rewrites is still named
    altered = [*refs[:3], {"document_id": "doc-osmosis", "excerpt": "lost a lot of mass"}]
    s2 = s.model_copy(update={"claims": [s.claims[0].model_copy(update={"evidence_refs": [r for r in s.claims[0].evidence_refs][:3] + [s.claims[0].evidence_refs[3].model_copy(update={"excerpt": "lost a lot of mass"})]})]})
    assert altered and "INT-LEDGER-020" in codes(L.check_synthesis_ledger([rep], s2))


# --------------------------------------------------------------------------------- the new readers are linear


def _labelled(text: str) -> Problem:
    return Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "x", "sort": "Real", "meaning": text[:1000]}],
                                   "premises": [{"id": "pt", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0"}}, "label": text[:1000]}],
                                   "conclusion": {"id": "c", "expr": {"op": "ge", "left": {"op": "var", "name": "x"}, "right": {"op": "real", "value": "0"}}, "label": text[:1000]}})


def _entries(text: str):
    labelled = _labelled(text)
    yield "gloss_content", lambda: gloss_content(text)
    yield "gloss_difference", lambda: gloss_difference(text, "Kc falls - worst-case run-off")
    yield "evaluation_points", lambda: evaluation_points(labelled)
    yield "rename_evaluation_points_apart", lambda: rename_evaluation_points_apart([labelled, labelled])
    yield "without_claim_markers", lambda: L.without_claim_markers(text, [text[:200], "3) x", text[-50:]])
    yield "without_claim_markers(markers)", lambda: L.without_claim_markers("3) " * 2000 + text, ["3) x", "x"])
    yield "figure_tokens", lambda: L.figure_tokens(text)
    yield "figure_tokens(Spanish)", lambda: L.figure_tokens("hasta las " + text + " dos mil " * 50)
    yield "contained_claims", lambda: L.contained_claims([f'"{text[:3990]}"', text, text])


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c2_integrity_readers(shape):
    """Every reader this clearance added to the integrity layer, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))


@pytest.mark.parametrize("text", ["dos mil " * 3000, "las " * 6000 + "tres", "veinte y " * 3000, "3) " * 7000, "at x = " * 4000 + "0", '"' * 20000])
def test_the_new_integrity_readers_are_linear_on_their_own_worst_inputs(text):
    assert not sweep(_entries, texts={"worst": text})


@pytest.mark.parametrize("text,claims", [
    ("a. 1) a" * 60_000, ["a"] * 512),                                                   # a short claim at every one of 60,000 markers
    (". 1) The student wrote x" * 20_000, [f"The student wrote x {i}" for i in range(512)]),  # 512 claims sharing their first words
])
def test_the_claim_marker_reader_is_linear_in_the_text(text, claims):
    import time
    t0 = time.process_time()
    L.without_claim_markers(text, claims)
    assert time.process_time() - t0 < 2.0
