"""A correct conversion of a stated figure into its unit's SI unit, or into the unit without its prefix, is the stated figure.

Integration gate, round 1 added the introduced-figure check (``pipeline.introduced_figures``: an assignment premise whose
figure no source states makes the translation AMBIGUOUS_TRANSLATION when the conclusion follows only with it). It read a
source's figures as written and scaled only (``quantities.literal_matches`` with no conversion), so a translation that
encodes the method's "50.0 cm³" of thiosulfate in m³ (0.0000500), the answer's own number (Inspection I91), was graded
an introduced figure, and the contained run's control probe ``units-translation-base-control`` lost its verdict
(INT-REQ-006). The readers that ask whether a figure is one a source STATES (the introduced-figure check, the claim's
figures the problem encodes, the conclusion label's figures, the coverage of a source's figures) now read a figure
converted by the STEM unit table's exact factor into its SI unit or into its unit without the prefix
(``quantities.unit_conversions``); every power as written (``cm³``, ``cm^3``, ``cm**3``, and the ASCII ``cm3`` and ``dm-3``
glued to their atom after a number, as the STEM parser reads them there). A figure converted by any other factor is still
introduced. The transcription check of a quotation (``grounding``, ``figures_in_excerpt``) is not one of those readers:
it stays a check of the figure as quoted (``tests/overseer/test_stem_repair1.py``), and the overseer's rule
``excerpt-prefix-units`` reads its conversions.

No recorded round is needed: the control's translation is rebuilt here from its shape.
"""
from __future__ import annotations

import json as _json
from fractions import Fraction

import pytest

from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.engine.statuses import VerificationStatus as S
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, TranslationStatus, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator, introduced_figures, label_beyond_expression, unencoded_claim_figures
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider
from epinoic_logic.translate.quantities import SourceText, figures_in, literal_matches, unit_conversions

from ..timing import measure

KEY = b"arena-signing-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)

METHOD = ("Effect of temperature on the time for the cross to disappear\n\nEach trial: 50.0 cm3 of 0.10 mol dm-3 sodium thiosulfate "
          "solution and 5.0 cm3 of 2.0 mol dm-3 hydrochloric acid, in a conical flask over a cross drawn on paper.")
EXCERPT = "Each trial: 50.0 cm3 of 0.10 mol dm-3 sodium thiosulfate solution and 5.0 cm3 of 2.0 mol dm-3 hydrochloric acid"
CLAIM = "Your method mixes 50.0 cm³ of thiosulfate with 5.0 cm³ of acid."
DOC = SuppliedText(document_id="doc-thio", title="Method", author="Student", text=METHOD)


def V(name: str) -> dict:
    return {"op": "var", "name": name}


def R(value: str) -> dict:
    return {"op": "real", "value": value}


def _quote() -> dict:
    return {"kind": "quotation", "source_refs": [{"document_id": "doc-thio", "excerpt": EXCERPT}], "certainty": "established"}


def control_problem(thio: str = "0.0000500", acid: str = "5.0") -> dict:
    """The shape of the recorded chemistry translation of the method claim, the thiosulfate volume encoded as ``thio``
    (premise and conclusion alike) and the acid volume as ``acid``."""
    return {"ir_version": "1.0", "problem_id": "ch-g5.1", "request_id": "req-ch", "claim_id": "g5.1", "query": "entailment",
            "symbols": [{"name": "vol_thio", "sort": "Real", "meaning": "volume of 0.10 mol dm-3 thiosulfate per trial (cm3)", "grounding": _quote()},
                        {"name": "vol_acid", "sort": "Real", "meaning": "volume of 2.0 mol dm-3 hydrochloric acid per trial (cm3)", "grounding": _quote()}],
            "premises": [{"id": "d_thio", "expr": {"op": "eq", "left": V("vol_thio"), "right": R(thio)}, "label": "50.0 cm3 of thiosulfate per trial",
                          "materiality": "material", "grounding": _quote()},
                         {"id": "d_acid", "expr": {"op": "eq", "left": V("vol_acid"), "right": R(acid)}, "label": "5.0 cm3 of acid per trial",
                          "materiality": "material", "grounding": _quote()}],
            "conclusion": {"id": "g5.1", "expr": {"op": "and", "args": [{"op": "eq", "left": V("vol_thio"), "right": R(thio)},
                                                                        {"op": "eq", "left": V("vol_acid"), "right": R(acid)}]},
                           "label": CLAIM, "materiality": "material", "grounding": {"kind": "supplied_text", "source_refs": [], "certainty": "established"}}}


def _claim() -> ClaimRecord:
    return ClaimRecord(claim_id="g5.1", request_id="req-ch", task_id="ch-t", report_id="rep-ch-0", agent_id="chemistry-specialist", subject="Chemistry",
                       task_type="structured_question", claim_text=CLAIM, claim_role="quantitative", proposed_claim_kind="arithmetic", materiality="material")


def _report(claim: ClaimRecord) -> SpecialistReport:
    text = "(e) Method.\n\n" + CLAIM
    return SpecialistReport(report_id="rep-ch-0", request_id="req-ch", task_id="ch-t", agent_id="chemistry-specialist", subject="Chemistry",
                            task_type="structured_question", original_response=text, response_sha256=sha256_text(text), supplied_texts=[DOC], claims=[claim],
                            created_at="2026-11-02T09:00:00Z")


def _sources() -> list[SourceText]:
    return [SourceText("claim", "g5.1", CLAIM), SourceText("supplied_text", "doc-thio", METHOD)]


def _verify(problem: dict):
    claim = _claim()
    proposal = {"problem": problem, "interpretation": {"reading": "the volumes of the method line, per trial", "glossary": [], "ambiguity_flags": []},
                "ambiguous": False, "unsupported_reason": None}
    provider = FixtureTranslationProvider({claim.claim_id: [_json.dumps(proposal), _json.dumps(proposal)]})
    return verify_claim(claim, _report(claim), Translator(provider), config=CFG, signing_key=KEY)


# ------------------------------------------------------------------------------------------------- the control
def test_the_control_s_conversion_into_cubic_metres_introduces_nothing_and_encodes_the_claim():
    problem = Problem.model_validate(control_problem())
    assert introduced_figures(problem, _sources()) == []
    assert unencoded_claim_figures(problem, _claim()) == []
    assert label_beyond_expression(problem) == []


def test_the_control_is_translated_and_keeps_the_engine_s_verdict():
    out = _verify(control_problem())
    notes = out.translation.diagnostics
    assert out.translation.status is TranslationStatus.TRANSLATED and out.display_status is S.ENTAILED, notes
    flags = [f.code for f in out.translation.interpretation.ambiguity_flags]
    assert "introduced_figure" not in flags
    assert not [n for n in notes if n.startswith(("introduced figure", "part of the claim only", "conclusion label states"))], notes
    # the quotation's transcription check reads the excerpt's figure as quoted (by design: the overseer's rule
    # excerpt-prefix-units reads its conversions), so it is the one check that names 0.0000500, and decides nothing
    failed = [c for c in out.translation.grounding_checks if c.verified is False]
    assert [(c.target_id, c.method) for c in failed] == [("d_thio", "figures_in_excerpt")]


def test_the_figure_as_written_is_unchanged():
    out = _verify(control_problem(thio="50.0"))
    assert out.translation.status is TranslationStatus.TRANSLATED and out.display_status is S.ENTAILED
    assert not [c for c in out.translation.grounding_checks if c.verified is False]


@pytest.mark.parametrize("thio", ["0.000500", "0.5", "0.0500"])
def test_a_wrong_factor_is_still_an_introduced_figure(thio):
    """50.0 cm³ is 0.0000500 m³: a factor of 10⁻⁵ (0.000500), 10⁻² (0.5) or the litre's 10⁻³ (0.0500, no conversion into
    the SI unit or the unit without its prefix) is the translation's own figure, and the conclusion rests on it."""
    problem = Problem.model_validate(control_problem(thio=thio))
    assert introduced_figures(problem, _sources()) == [f"d_thio (vol_thio = {thio})"]
    assert unencoded_claim_figures(problem, _claim()) == ["'50.0 cm³'"]
    out = _verify(control_problem(thio=thio))
    assert out.translation.status is TranslationStatus.AMBIGUOUS_TRANSLATION and out.display_status is not S.ENTAILED
    assert "introduced_figure" in [f.code for f in out.translation.interpretation.ambiguity_flags]
    assert any(n.startswith("introduced figure") and f"vol_thio = {thio}" in n for n in out.translation.diagnostics)


def test_another_prefix_is_no_base_unit_conversion():
    """5.0 cm³ as 0.0050 (in dm³): a conversion under another prefix is not read (the overseer names it as a warning)."""
    problem = Problem.model_validate(control_problem(acid="0.0050"))
    assert introduced_figures(problem, _sources()) == ["d_acid (vol_acid = 0.0050)"]


# ------------------------------------------------------------------------------------------------- the swept forms
#: (the figure as a source writes it, the literal of its correct conversion into the SI unit or the unit without its prefix)
CORRECT = [
    ("50.0 cm³", "0.0000500"), ("50.0 cm3", "0.0000500"), ("50.0 cm^3", "0.0000500"), ("50.0 cm**3", "0.0000500"),
    ("2.50 dm³", "0.00250"), ("2.50 dm3", "0.00250"), ("2.50 dm^3", "0.00250"),
    ("25.0 mL", "0.0250"), ("25.0 mL", "0.0000250"), ("25.0 ml", "0.0250"),
    ("500 g", "0.5"), ("3.2 kg", "3200"), ("4.0 mm", "0.0040"), ("2.5 km", "2500"),
    ("72 km/h", "20"), ("72 km h⁻¹", "20"), ("72 km h-1", "20"), ("72 km h^-1", "20"), ("72 km h**-1", "20"),
    ("15 cm²", "0.0015"), ("15 cm2", "0.0015"), ("15 cm^2", "0.0015"), ("0.10 mol dm-3", "100"), ("0.10 mol dm⁻³", "100"),
]
#: the same figures converted by a wrong factor (or into another prefix, which is no base-unit conversion)
WRONG = [
    ("50.0 cm³", "0.000500"), ("50.0 cm3", "0.5"), ("50.0 cm**3", "0.0000050"), ("2.50 dm3", "0.0250"), ("25.0 mL", "0.250"),
    ("500 g", "5"), ("3.2 kg", "320"), ("4.0 mm", "0.04"), ("72 km/h", "259.2"), ("72 km h-1", "200"), ("15 cm2", "0.15"), ("5.0 cm³", "0.0050"),
]


def _assignment(value: str, grounding: dict) -> Problem:
    return Problem.model_validate({"ir_version": "1.0", "problem_id": "p", "request_id": "r", "claim_id": "c", "query": "entailment",
                                   "symbols": [{"name": "q", "sort": "Real", "meaning": "the measured quantity"}],
                                   "premises": [{"id": "P", "expr": {"op": "eq", "left": V("q"), "right": R(value)}, "grounding": grounding}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": V("q"), "right": R(value)}}})


@pytest.mark.parametrize("written,literal", CORRECT)
def test_a_correct_conversion_is_the_stated_figure_in_every_written_form(written, literal):
    text = f"Each trial used {written} of the solution."
    [figure] = figures_in(SourceText("supplied_text", "doc", text))
    assert figure.written == written
    [match] = literal_matches(Fraction(literal), [figure], conversions=True)[0]
    assert match.derivation.startswith(f"{written} = ")
    # the readers that ask whether a source states the figure: the introduced-figure check and the claim's encoded figures
    p = _assignment(literal, {"kind": "supplied_text", "source_refs": [], "certainty": "established"})
    assert introduced_figures(p, [SourceText("supplied_text", "doc", text)]) == []
    claim = _claim().model_copy(update={"claim_text": f"The method uses {written} of the solution."})
    assert unencoded_claim_figures(p, claim) == []


@pytest.mark.parametrize("written,literal", WRONG)
def test_a_wrong_conversion_stays_named(written, literal):
    text = f"Each trial used {written} of the solution."
    assert literal_matches(Fraction(literal), figures_in(SourceText("supplied_text", "doc", text)), conversions=True)[0] == []
    p = _assignment(literal, {"kind": "supplied_text", "source_refs": [], "certainty": "established"})
    assert introduced_figures(p, [SourceText("supplied_text", "doc", text)]) == [f"P (q = {literal})"]


def test_the_conversion_factors_come_from_the_unit_table():
    assert unit_conversions("cm³") == unit_conversions("cm3") == unit_conversions("cm^3") == unit_conversions("cm**3") == ((Fraction(1, 10 ** 6), "its SI unit"),)
    assert dict((how, f) for f, how in unit_conversions("mL")) == {"its SI unit": Fraction(1, 10 ** 6), "its unit without the prefix": Fraction(1, 1000)}
    assert unit_conversions("g") == ((Fraction(1, 1000), "its SI unit"),)
    assert unit_conversions("kg") == ((Fraction(1000), "its unit without the prefix"),)
    assert dict((how, f) for f, how in unit_conversions("km/h")) == {"its SI unit": Fraction(5, 18), "its unit without the prefix": Fraction(1000)}
    for unit in ("m", "m³", "m s⁻¹", "kg", "°C", "%", "rad"):  # already SI, an offset, dimensionless or an angle: no SI factor
        assert all(how != "its SI unit" for _f, how in unit_conversions(unit)), unit


def test_a_declared_unit_admits_only_the_conversion_into_it():
    """A symbol whose meaning declares its unit keeps the declared reading: the figure in m³ for a symbol declared in cm³ is
    no match (the declared unit's own conversion is read, as before)."""
    from epinoic_logic.translate.quantities import declared_reading
    [figure] = figures_in(SourceText("supplied_text", "doc", "Each trial used 50.0 cm³ of the solution."))
    assert literal_matches(Fraction("0.0000500"), [figure], declared_reading("volume (cm³)"), conversions=True)[0] == []
    assert literal_matches(Fraction("0.0000500"), [figure], declared_reading("volume in m³"), conversions=True)[0]
    assert literal_matches(Fraction("0.0000500"), [figure])[0] == []  # without conversions: as written and scaled only, as before


@pytest.mark.parametrize("text,unit", [
    ("a 2 m2 plot", None),  # a one-letter atom's glued digit is no exponent (m₂, a formula's H2)
    ("x = 5 m-3 m", None),  # a subtraction of two lengths, not m⁻³
    ("at 300 K-273", None),  # more digits: no exponent
    ("**50 cm** of tape", "cm"),  # a bold run's close ends the unit
    ("50.0 cm3 of water", "cm3"), ("0.10 mol dm-3 acid", "mol dm-3"), ("3 m s-1 east", "m s-1"), ("9 cm**3 left", "cm**3"),
])
def test_an_ascii_exponent_is_read_only_where_the_stem_parser_reads_one(text, unit):
    first = figures_in(SourceText("supplied_text", "doc", text))[0]
    assert first.unit == unit, first


def test_the_unit_reader_stays_linear():
    """The unit token keeps a bounded run (at most 16 characters, ``**`` only before a digit): a long run of unit characters
    or of ``*`` after a figure is read in linear time, and a text of many figures with ASCII exponents costs what one of
    as many figures with superscript powers does (about 55 µs a figure on the reference machine, before and after)."""
    for text in ("1 " + "cm" * 200_000, "1 cm" + "*" * 400_000, "1 c" + "**" * 200_000 + "3", "1 cm3 " * 20_000, "1 mol dm-3 " * 20_000):
        timing = measure(lambda t=text: figures_in(SourceText("supplied_text", "doc", t)), bound=3.0, label=text[:12])
        assert timing.holds, timing
