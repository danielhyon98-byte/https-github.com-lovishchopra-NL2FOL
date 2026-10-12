"""``stem.hub_hooks.STEM_HOOKS``: coverage words from dimensions and computations, the echo exemption, the STEM
imperatives and the word-count view (docs/STEM_DESIGN.md, section 11.2). Every hook is total: on agent text it never
raises, and a failure falls back to the channel's own reading."""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches.base import BranchHooks
from epinoic_logic.channel.request_parser import count_answer_words, extract_items
from epinoic_logic.stem import hub_hooks as hooks_module
from epinoic_logic.stem.hub_hooks import STEM_HOOKS, STEM_IMPERATIVES, dimension_terms
from epinoic_logic.stem.units import parse_unit


def test_the_hooks_satisfy_the_branch_protocol():
    assert isinstance(STEM_HOOKS, BranchHooks)
    assert STEM_HOOKS.request_imperatives == STEM_IMPERATIVES
    assert set(STEM_IMPERATIVES) == {"determine", "deduce", "derive", "state", "find", "solve", "sketch", "estimate", "predict", "verify", "show"}


@pytest.mark.parametrize("unit,word", [("m s⁻²", "acceleration"), ("N", "force"), ("N", "weight"), ("J", "energy"), ("J", "work"), ("W", "power"),
                                        ("m/s", "velocity"), ("Pa", "pressure"), ("mol dm⁻³", "concentration"), ("kg m s⁻¹", "momentum"), ("Ω", "resistance")])
def test_dimension_terms(unit, word):
    assert word in dimension_terms(parse_unit(unit).dim)


def test_dimension_terms_of_nothing():
    assert dimension_terms(None) == ()


def test_coverage_terms_name_the_dimensions_of_a_claims_quantities():
    text = "a = (20 - 0)/4.0 = 5.0 m s⁻²"
    terms = STEM_HOOKS.coverage_terms(text, text, "Calculate the acceleration.", "physics")
    assert "acceleration" in terms and "calculate" in terms  # a computing claim offers the computing command words


def test_coverage_terms_of_bound_symbols():
    text = "Given: F = 12 N and m = 3.0 kg.\na = F/m = 12/3.0 = 4.0"
    terms = STEM_HOOKS.coverage_terms("a = F/m = 12/3.0 = 4.0", text, None, "physics")
    assert "force" in terms and "mass" in terms


def test_a_claim_with_no_maths_offers_nothing_extra():
    text = "Energy is conserved because no external force acts."
    assert STEM_HOOKS.coverage_terms(text, text, None, "physics") == frozenset()


def test_coverage_terms_never_raise():
    assert STEM_HOOKS.coverage_terms("not in the text", "x = 1", None, "physics") == frozenset()
    assert STEM_HOOKS.coverage_terms("", "", None, "no-such-profile") == frozenset()


def test_echo_exemption():
    request = "Show that 36 g of water is 2.0 mol."
    assert STEM_HOOKS.echo_exempt("n = m/M = 36 g / 18 g mol⁻¹ = 2.0 mol", request, "chemistry")
    assert not STEM_HOOKS.echo_exempt("Show that 36 g of water is 2.0 mol.", request, "chemistry")
    # a computation the request itself states is no answer of the specialist's
    assert not STEM_HOOKS.echo_exempt("2 + 2 = 4", "Explain why 2 + 2 = 4.", "mathematics")


def test_hooks_fall_back_on_an_internal_failure(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("injected")
    monkeypatch.setattr(hooks_module, "build_document", boom)
    assert STEM_HOOKS.echo_exempt("x = 1 + 1 = 2", "Compute.", "physics") is False
    assert STEM_HOOKS.coverage_terms("x = 2", "x = 2", None, "physics") == frozenset()
    assert STEM_HOOKS.word_count_view("$x = 2$ words", "physics") == "$x = 2$ words"


def test_word_count_view():
    answer = "The energy is $E_k = \\frac{1}{2} m v^2 = \\frac{1}{2}(2.0)(3.0)^2 = 9.0\\,\\text{J}$, so the mass carries 9.0 J."
    view = STEM_HOOKS.word_count_view(answer, "physics")
    assert "\\frac" not in view and view.count("Xmath") == 1
    words = count_answer_words(answer, view=lambda t: STEM_HOOKS.word_count_view(t, "physics"))[0]
    assert words == len("The energy is X , so the mass carries 9.0 J.".replace(",", "").split())
    assert count_answer_words("```python\nprint(1)\n```", view=lambda t: STEM_HOOKS.word_count_view(t, "computer_science"))[0] == 1
    assert count_answer_words("```python\nprint(1)\n```")[0] == 0  # the default view: a code block has no words
    assert STEM_HOOKS.word_count_view("\\alpha particles \\cdot are fast", "physics").split() == ["particles", "are", "fast"]


def test_word_count_view_keeps_paragraphs():
    answer = "First paragraph with $x = 1$.\n\nSecond paragraph."
    assert STEM_HOOKS.word_count_view(answer, "physics").count("\n\n") == 1


def test_stem_imperatives_make_items():
    request = "A car accelerates from rest.\n(a) Determine its speed after 2.0 s.\n(b) Find the distance.\n(c) State one assumption."
    items = extract_items(request, extra_imperatives=STEM_IMPERATIVES)
    assert [i.text for i in items] == ["(a) Determine its speed after 2.0 s.", "(b) Find the distance.", "(c) State one assumption."]
    assert len(extract_items(request)) == 1  # the default reading is unchanged
    # an imperative inside a sentence is not one: 'the state of matter' is no instruction
    assert [i.text for i in extract_items("Water is in a liquid state. Determine its density.", extra_imperatives=STEM_IMPERATIVES)] == ["Determine its density."]


def test_default_extract_items_is_unchanged_by_the_new_keyword():
    for text in ("Calculate the profit margin and recommend whether to proceed.", "To what extent was the Depression responsible? Explain with dated evidence.",
                 "Write no more than 200 words and give a judgement on which effect mattered most."):
        assert extract_items(text) == extract_items(text, extra_imperatives=())


@pytest.mark.parametrize("text", ["$" * 20_000, "x = " + "(" * 500 + "1" + ")" * 500, "\\frac{" * 3000, "```\n" * 3000, "y = 10^10^10 = " + "10^" * 2000 + "10"],
                         ids=["dollar_storm", "nesting_500", "frac_storm", "fences", "tower"])
def test_hooks_on_adversarial_text_stay_bounded(text):
    t0 = time.perf_counter()
    STEM_HOOKS.word_count_view(text, "mathematics_aa")
    STEM_HOOKS.coverage_terms(text[:100], text, None, "mathematics_aa")
    STEM_HOOKS.echo_exempt(text, "Solve it.", "mathematics_aa")
    assert time.perf_counter() - t0 < 5.0
