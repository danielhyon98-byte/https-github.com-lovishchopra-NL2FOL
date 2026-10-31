"""Integration gate, round 1: the translator's findings.

Parser safety (critical, previous parser-safety-9): ``parse_json_object``'s lenient path searched a lazy DOTALL fence
pattern from every opener with no closer, which is quadratic in provider output (12 s at 80 KB, no result within 120 s at
320 KB; hours at the 2 MB limit). The strict path the overseer's verdict intake uses was cubic on a run of spaces (22 s at
4 KB). Both now read the text in linear time; their results are unchanged (a differential test against the replaced
patterns, kept here as the specification).
"""
from __future__ import annotations

import itertools
import random
import re

import pytest

from epinoic_logic.translate import parsing
from epinoic_logic.translate.parsing import ProviderOutputError, parse_json_object, strip_code_fences

from ..timing import measure

# The replaced patterns, kept as the specification the linear readers must match (they are quadratic or worse only on long
# adversarial inputs; the differential test below runs them on short ones).
_OLD_FENCE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.DOTALL)
_OLD_INLINE = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*(.*?)```", re.DOTALL)
_OLD_STRICT = re.compile(r"```[A-Za-z0-9_+-]*[ \t]*(?:\r?\n)?(?P<body>.*?)(?:\r?\n)?[ \t]*```", re.DOTALL)


def _old_strip(text: str) -> str:
    m = _OLD_FENCE.search(text) or _OLD_INLINE.search(text)
    return text if m is None else m.group(1)


def _old_strict(stripped: str):
    m = _OLD_STRICT.fullmatch(stripped)
    return None if m is None else m.group("body")


def test_the_linear_fence_readers_match_the_replaced_patterns_exhaustively_on_short_texts():
    for length in range(0, 8):
        for chars in itertools.product("`a \r\n", repeat=length):
            text = "".join(chars)
            assert strip_code_fences(text) == _old_strip(text), repr(text)
            assert parsing._strict_fence_body(text.strip()) == _old_strict(text.strip()), repr(text)


def test_the_linear_fence_readers_match_the_replaced_patterns_on_random_texts():
    rng = random.Random(20261031)
    alphabet = ["`", "`", "`", "a", "j", "+", " ", "\t", "\r", "\n", "x", "{", "}", "-", "é"]
    for _ in range(60_000):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 28)))
        assert strip_code_fences(text) == _old_strip(text), repr(text)
        assert parsing._strict_fence_body(text.strip()) == _old_strict(text.strip()), repr(text)


@pytest.mark.parametrize("text,expected", [
    ('Here it is:\n```json\n{"a": 1}\n```\nThanks', '{"a": 1}'),
    ('```\r\n{"a": 1}\r\n```', '{"a": 1}'),
    ('prose ```{"a": 1}``` prose', '{"a": 1}'),
    ("no fence at all", "no fence at all"),
    ("```json\n{}\n``` and ```\n[]\n```", "{}"),
])
def test_fence_bodies_are_read_as_before(text, expected):
    assert strip_code_fences(text) == expected


# The finding's inputs: openers with no closer, 80 KB and 320 KB; and the same shapes at the 2 MB limit.
WORST = {
    "x```LF x 16,000 (80 KB)": "x```\n" * 16_000,
    "x```LF x 64,000 (320 KB)": "x```\n" * 64_000,
    "x```LF to the 2 MB limit": "x```\n" * 399_000,
    "an opener and 2 MB of tag characters": "```" + "a" * 1_990_000,
    "an opener and 2 MB of spaces before one character": "```" + " " * 1_990_000 + "x",
    "2 MB of backticks": "`" * 1_990_000,
    "four backticks and a tag, repeated to 2 MB": "````x" * 398_000,
    "an opener and line breaks with blanks to 2 MB": "```\n" + ("\n" + " " * 50) * 39_000,
}


@pytest.mark.parametrize("name", list(WORST))
@pytest.mark.parametrize("strict", [False, True])
def test_provider_output_with_unclosed_fences_is_refused_in_linear_time(name, strict):
    text = WORST[name]

    def parse():
        try:
            parse_json_object(text, strict=strict)
        except ProviderOutputError as exc:
            return "refused", str(exc)[:40]
        return "accepted", None

    timing = measure(parse, bound=1.0, repeat=3, label=f"parse_json_object(strict={strict}): {name}")
    assert timing.holds, timing  # before the fix: 10.6 s at 80 KB and no result within 120 s at 320 KB (lenient); 22 s at 4 KB (strict)
    assert all(r[0] == "refused" for r in timing.results)


def test_a_fenced_object_after_prose_is_still_parsed():
    assert parse_json_object('Some prose first.\n```json\n{"a": 1}\n```') == {"a": 1}
    text = "x```\n" * 2_000 + '```json\n{"a": 1}\n```'
    assert strip_code_fences(text) == _old_strip(text)  # the first line opener and the first closer after it, as before


# ================================================================================================= fidelity findings
import json as _json

from epinoic_logic.branches import default_registry
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SuppliedText, TranslationStatus
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator, label_beyond_expression
from epinoic_logic.translate.precision import collect_sites
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText
from epinoic_logic.translate.stated_rules import stated_rule

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
TOWN = "In 2010 Lowtown had 200 residents. In 2020 Lowtown had 310 residents."
GROWTH_CLAIM = "(a) The population of Lowtown grew by about 100% between 2010 and 2020, so it roughly doubled.\n"


def V(n):
    return {"op": "var", "name": n}


def Rl(v):
    return {"op": "real", "value": str(v)}


GROWTH = {"op": "div", "left": {"op": "to_real", "arg": {"op": "sub", "left": V("p2020"), "right": V("p2010")}}, "right": Rl(200)}


def _quote(text):
    return {"kind": "quotation", "source_refs": [{"document_id": "doc-town", "excerpt": text}], "certainty": "established"}


def _growth_problem(conclusion: dict, p2010: str = "200", p2010_grounding=None) -> dict:
    return {"problem": {"ir_version": "1.0", "problem_id": "pr2", "request_id": "req-pr-2", "claim_id": "g1.1@geography-specialist", "query": "entailment",
                        "symbols": [{"name": "p2010", "sort": "Int", "meaning": "Lowtown residents in 2010 (count)", "grounding": _quote("In 2010 Lowtown had 200 residents")},
                                    {"name": "p2020", "sort": "Int", "meaning": "Lowtown residents in 2020 (count)", "grounding": _quote("In 2020 Lowtown had 310 residents")}],
                        "premises": [{"id": "ev1", "expr": {"op": "eq", "left": V("p2010"), "right": {"op": "int", "value": p2010}}, "label": "In 2010 Lowtown had 200 residents",
                                      "grounding": p2010_grounding or _quote("In 2010 Lowtown had 200 residents"), "materiality": "material"},
                                     {"id": "ev2", "expr": {"op": "eq", "left": V("p2020"), "right": {"op": "int", "value": "310"}}, "label": "In 2020 Lowtown had 310 residents",
                                      "grounding": _quote("In 2020 Lowtown had 310 residents"), "materiality": "material"}],
                        "conclusion": {"id": "concl", "expr": conclusion, "label": "the population grew by about 100%", "materiality": "material"}},
            "interpretation": {"reading": "growth rate from the census figures", "glossary": [], "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}


def _verify_growth(proposal: dict):
    branch, _profile = default_registry().for_subject("Geography")
    texts = [SuppliedText(document_id="doc-town", title="Census", text=TOWN)]
    report = branch.parser().parse_response(GROWTH_CLAIM, request_id="req-pr-2", task_id="pr-2", report_id="rep-pr-2-0", subject="Geography",
                                            task_type="structured_question", supplied_texts=texts, agent_id="geography-specialist")
    [claim] = [c for c in report.claims if "about 100%" in c.claim_text]
    provider = FixtureTranslationProvider({claim.claim_id: [_json.dumps(proposal), _json.dumps(proposal)]})
    return verify_claim(claim, report, Translator(provider), config=CFG, signing_key=KEY)


def _bounds(*parts):
    return {"op": "and", "args": list(parts)}


WIDE = [{"op": "ge", "left": GROWTH, "right": Rl("0.5")}, {"op": "lt", "left": GROWTH, "right": Rl("1.5")}]


@pytest.mark.parametrize("conclusion", [
    _bounds(*WIDE),                                                                             # the control: refused before
    _bounds(*WIDE, {"op": "ge", "left": GROWTH, "right": Rl("0")}),                             # plus a non-negativity bound
    _bounds({"op": "not", "arg": {"op": "lt", "left": GROWTH, "right": Rl("0.5")}}, WIDE[1]),  # a bound written as not(lt)
    _bounds(*WIDE, {"op": "gt", "left": GROWTH, "right": Rl("-1")}),                            # plus another domain bound
], ids=["wide", "wide+nonneg", "wide-as-not-lt", "wide+extra"])
def test_a_widened_about_100_percent_is_refused_whatever_bounds_ride_with_it(conclusion):
    out = _verify_growth(_growth_problem(conclusion))
    assert out.translation.status is TranslationStatus.INVALID_FORMALIZATION and out.display_status is S.INVALID_FORMALIZATION
    assert any("precision" in d for d in out.translation.diagnostics), out.translation.diagnostics


def test_two_intervals_on_one_term_are_two_sites():
    pct = V("pct_rep")
    concl = _bounds({"op": "ge", "left": pct, "right": Rl("25.85")}, {"op": "lt", "left": pct, "right": Rl("25.95")},
                    {"op": "ge", "left": pct, "right": Rl("25.5")}, {"op": "lt", "left": pct, "right": Rl("26.5")})
    p = Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "s2.1", "query": "entailment",
                                "symbols": [{"name": "pct_rep", "sort": "Real"}], "premises": [{"id": "P", "expr": {"op": "eq", "left": pct, "right": Rl("25.9")}}],
                                "conclusion": {"id": "C", "expr": concl}})
    sites = [(s.lo, s.hi) for s in collect_sites(p) if s.in_conclusion and s.kind == "interval"]
    from fractions import Fraction as F
    assert sites == [(F("25.85"), F("25.95")), (F("25.5"), F("26.5"))]


# ------------------------------------------------------------------------------------------------- stated rules
TAX = {"tax": ("Bool", "taxes rise"), "cons": ("Bool", "consumption falls")}


def _rule_reading(text: str, syms=TAX, expr=None):
    expr = expr or {"op": "implies", "left": V("tax"), "right": V("cons")}
    p = Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                "symbols": [{"name": n, "sort": s, "meaning": m} for n, (s, m) in syms.items()],
                                "premises": [{"id": "w", "expr": expr}], "conclusion": {"id": "C", "expr": V(list(syms)[1])}})
    r = stated_rule(p.premises[0].expr, {s.name: s for s in p.symbols}, SourceText("supplied_text", "d", text), (0, len(text)))
    return None if r is None else ("stated" if r.qualifier is None else "qualified")


@pytest.mark.parametrize("text", [
    "If taxes rise, consumption rises, and savings fall.", "If taxes rise, consumption hardly falls.", "If taxes rise, consumption fails to fall.",
    "If taxes rise, consumption falls; this was disproved in 2020.", "If taxes rise, consumption falls (a claim later refuted).",
    "If taxes rise, consumption falls, according to a rumour.", "If taxes rise, consumption is expected to fall.", "If taxes rise, consumption falls in theory.",
])
def test_a_source_that_does_not_state_the_rule_never_verifies_it(text):
    assert _rule_reading(text) != "stated"


def test_hardly_any_is_no_universal_rule():
    syms = {"big": ("Bool", "the firm has more than 50 employees"), "levy": ("Bool", "the new levy applies to the firm")}
    expr = {"op": "implies", "left": V("big"), "right": V("levy")}
    assert _rule_reading("The new levy applies to every firm with more than 50 employees.", syms, expr) == "stated"
    assert _rule_reading("The new levy applies to hardly any firm with more than 50 employees.", syms, expr) != "stated"


@pytest.mark.parametrize("text", ["If taxes rise, consumption falls.", "Consumption falls if taxes rise."])
def test_a_rule_the_source_states_is_still_stated(text):
    assert _rule_reading(text) == "stated"


# ------------------------------------------------------------------------------------------------- partial encodings
def test_a_weakened_encoding_shows_the_part_of_the_claim_it_does_not_check():
    out = _verify_growth(_growth_problem({"op": "gt", "left": GROWTH, "right": Rl("0")}))  # 'about 100%' encoded as growth > 0
    assert any(line.startswith("Note: part of the claim only") and "100%" in line for line in out.summary.splitlines()), out.summary


# ------------------------------------------------------------------------------------------------- introduced figures
@pytest.mark.parametrize("grounding", [{"kind": "specialist_inference", "certainty": "established"}, {"kind": "supplied_text", "certainty": "established"}])
def test_a_figure_the_translation_introduces_never_makes_the_claim_entailed(grounding):
    narrow = _bounds({"op": "ge", "left": GROWTH, "right": Rl("0.995")}, {"op": "lt", "left": GROWTH, "right": Rl("1.005")})
    out = _verify_growth(_growth_problem(narrow, p2010="110", p2010_grounding=grounding))  # the text states 200 for 2010
    assert out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION and out.display_status is not S.ENTAILED
    flags = [f.code for f in out.translation.interpretation.ambiguity_flags]
    assert "introduced_figure" in flags


def test_the_faithful_encoding_is_unchanged():
    narrow = _bounds({"op": "ge", "left": GROWTH, "right": Rl("0.995")}, {"op": "lt", "left": GROWTH, "right": Rl("1.005")})
    out = _verify_growth(_growth_problem(narrow))
    assert out.translation.status is TranslationStatus.TRANSLATED and out.display_status is S.COUNTEREXAMPLE  # 55% is not about 100%


# ------------------------------------------------------------------------------------------------- label notes
def _labelled(label: str, conclusion: dict) -> Problem:
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "g", "sort": "Real", "meaning": "growth"}], "premises": [{"id": "P", "expr": {"op": "eq", "left": V("g"), "right": Rl(1)}}],
                                   "conclusion": {"id": "C", "expr": conclusion, "label": label}})


@pytest.mark.parametrize("label,lo,hi", [("grew by about 100%", "0.995", "1.005"), ("rose about 30%", "0.295", "0.305"), ("about 26%", "25.5", "26.5")])
def test_an_integer_figure_read_at_its_stated_interval_is_checked(label, lo, hi):
    concl = _bounds({"op": "ge", "left": V("g"), "right": Rl(lo)}, {"op": "lt", "left": V("g"), "right": Rl(hi)})
    assert label_beyond_expression(_labelled(label, concl)) == []


def test_a_precision_count_is_no_figure_and_an_unchecked_figure_is_still_named():
    concl = {"op": "ge", "left": V("g"), "right": Rl("0.5")}
    assert label_beyond_expression(_labelled("g is at least 0.50 to 2 decimal places", concl)) == []
    assert label_beyond_expression(_labelled("g is at least 0.5 and at most 7", concl))  # 7 is checked by nothing


def test_a_figure_bearing_clause_the_conclusion_does_not_check_is_named_beside_the_verdict():
    branch, _profile = default_registry().for_subject("Geography")
    texts = [SuppliedText(document_id="doc-town", title="Census", text=TOWN + " Lowtown has 4 schools.")]
    answer = "(a) The population of Lowtown grew by about 55% between 2010 and 2020, but the town has 4 schools.\n"
    report = branch.parser().parse_response(answer, request_id="req-pr-2", task_id="pr-2", report_id="rep-pr-2-0", subject="Geography",
                                            task_type="structured_question", supplied_texts=texts, agent_id="geography-specialist")
    [claim] = [c for c in report.claims if "55%" in c.claim_text]
    concl = _bounds({"op": "ge", "left": GROWTH, "right": Rl("0.545")}, {"op": "lt", "left": GROWTH, "right": Rl("0.555")})
    proposal = _growth_problem(concl)
    proposal["problem"]["claim_id"] = claim.claim_id
    out = verify_claim(claim, report, Translator(FixtureTranslationProvider({claim.claim_id: [_json.dumps(proposal)] * 2})), config=CFG, signing_key=KEY)
    # the verdict covers the clause the conclusion checks; the summary beside it names the clause it does not check
    notes = [line for line in out.summary.splitlines() if line.startswith("Note: part of the claim only")]
    assert any("4 schools" in n for n in notes), out.summary


# ------------------------------------------------------------------------------------------------- E2E B8: unlinked judgement
_INFERENCE = {"kind": "specialist_inference", "certainty": "probable"}
_FROM_MEMORY = {"kind": "general_knowledge", "certainty": "probable", "note": "stated from memory"}


def _judgement_problem(grounding) -> Problem:
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "rose", "sort": "Bool"},
                                               {"name": "significant", "sort": "Bool", **({"grounding": grounding} if grounding else {})}],
                                   "premises": [{"id": "P", "expr": V("rose"), "grounding": _quote("In 2020 Lowtown had 310 residents")}],
                                   "conclusion": {"id": "C", "expr": {"op": "and", "args": [V("rose"), V("significant")]}}})


def test_a_counterexample_that_falsifies_only_an_unlinked_judgement_is_not_decided():
    """E2E B8: the falsified conjunct is the specialist's own inference ('significant') that no premise mentions while the
    premises reach the rest of the conclusion: not decided (AMBIGUOUS_TRANSLATION), never a failed check."""
    from epinoic_logic.engine.runner import verify as engine_verify
    from epinoic_logic.translate.outcome import unlinked_judgement
    p = _judgement_problem(_INFERENCE)
    r = engine_verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and unlinked_judgement(r, p)  # displayed AMBIGUOUS_TRANSLATION by display_status_for
    assert not unlinked_judgement(r, None), "without the problem the rule never applies"
    # a counterexample over a conclusion the premises link to keeps its verdict
    linked = Problem.model_validate({**p.model_dump(mode="json", exclude_none=True),
                                     "premises": [{"id": "P", "expr": {"op": "implies", "left": V("rose"), "right": V("significant")}}]})
    r2 = engine_verify(linked, CFG)
    assert r2.status is S.COUNTEREXAMPLE and not unlinked_judgement(r2, linked)


@pytest.mark.parametrize("grounding", [_FROM_MEMORY, _quote("Lowtown grew significantly"), None], ids=["general_knowledge", "quotation", "no_grounding"])
def test_a_counterexample_on_an_unlinked_fact_stands(grounding):
    """Control: an unlinked atom that states a fact (from memory, a quotation, or with no grounding at all) is what the
    premises fail to establish, so the COUNTEREXAMPLE stands (the arena's History claim whose census figure is not a
    premise is refuted)."""
    from epinoic_logic.engine.runner import verify as engine_verify
    from epinoic_logic.translate.outcome import unlinked_judgement
    p = _judgement_problem(grounding)
    r = engine_verify(p, CFG)
    assert r.status is S.COUNTEREXAMPLE and any(d.code == "W111" for d in r.diagnostics)
    assert not unlinked_judgement(r, p)


@pytest.mark.parametrize("case_id", ["e2e-B8-en", "e2e-B8-ps"])
def test_the_recorded_b8_answers_are_no_longer_failed_by_an_unlinked_judgement(case_id):
    import sys
    from pathlib import Path
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)
    from tests import argdiag_cases as C
    from tests import case_scoring as Sc
    assert Sc.run_case(C.load_cases([case_id])[0])["verdict"] == "control_clean"
