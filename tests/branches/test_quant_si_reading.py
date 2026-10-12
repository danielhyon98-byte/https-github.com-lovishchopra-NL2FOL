"""The SI reading of the prose arithmetic extractor and the core pack (docs/STEM_DESIGN.md, section 12), and the
proof that the general reading is unchanged byte for byte on the History, English, Economics and Business corpora."""
from __future__ import annotations

import hashlib
import json
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.branches.quant import GENERAL, QuantReading, _analyse, extract_quant_checks, undecided_quant_statements
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.stem.si_reading import SI_READING
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
REFERENCE = json.loads((Path(__file__).parent / "data" / "quant_general_reference.json").read_text(encoding="utf-8"))


def _digest(text: str) -> str:
    """Exactly the digest the reference was computed with (before QuantReading existed)."""
    out: dict = {}
    qc = extract_quant_checks(text, request_id="req", claim_id="rep:core")
    out["quant"] = [[q.check_id, q.kind, q.sentence, q.problem.model_dump(mode="json"), q.rule, q.basis, q.expected_if_consistent] for q in qc]
    out["undecided"] = [[u.paragraph, u.sentence, u.sentence_text, u.phrase, u.reason] for u in undecided_quant_statements(text)]
    try:
        rep = GenericTextParser("specialist").parse_response(text, request_id="req", task_id="task", report_id="rep", subject="History", task_type="essay")
    except Exception as exc:
        out["core"] = repr(type(exc).__name__)
        return hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    pack = CorePack()
    out["core_checks"] = [f.model_dump(mode="json") for f in pack.checks(rep, "Explain the figures.")]
    out["core_formal"] = [[fc.check_id, fc.kind, fc.description, fc.problem.model_dump(mode="json"), fc.expected_if_sound] for fc in pack.formal_checks(rep)]
    return hashlib.sha256(json.dumps(out, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def test_general_reading_is_byte_identical_on_the_reference_corpus():
    items = REFERENCE["items"]
    assert len(items) >= 500 and sum(i["quant_checks"] for i in items) > 50 and sum(i["undecided"] for i in items) > 5
    mismatched = [i["text"][:80] for i in items if _digest(i["text"]) != i["sha256"]]
    assert mismatched == []


def test_general_is_the_default_and_its_reading_is_inert():
    assert GENERAL.si is False and GENERAL.for_profile("physics") is GENERAL
    assert CorePack().reading is GENERAL
    text = "Output rose from 100 in 1929 to 120 in 1930, a rise of 20 per cent."
    assert [q.problem for q in extract_quant_checks(text, request_id="r", claim_id="c")] == \
           [q.problem for q in extract_quant_checks(text, request_id="r", claim_id="c", reading=GENERAL)]


def test_the_reading_is_part_of_the_cache_key():
    text = "The extension rose from 500 mm to 2 m, a fourfold increase."
    _analyse.cache_clear()
    general = _analyse(text, Fraction(1, 20))
    si = _analyse(text, Fraction(1, 20), SI_READING)
    assert general is not si and _analyse.cache_info().currsize == 2
    assert hash(SI_READING) == hash(QuantReading(name="si", si=True, profile="stem"))


def test_si_reading_for_profile():
    assert SI_READING.for_profile("chemistry").profile == "chemistry" and SI_READING.for_profile("chemistry").si
    assert SI_READING.for_profile("history").profile == "stem" and SI_READING.for_profile(None).profile == "stem"
    assert SI_READING.for_profile("stem") is SI_READING


def _statuses(text: str, reading=SI_READING) -> list[tuple[str, str]]:
    return [(q.kind, verify(q.problem, CFG).status.value) for q in extract_quant_checks(text, request_id="r", claim_id="c", reading=reading)]


def _undecided(text: str, reading=SI_READING) -> list[str]:
    return [u.reason for u in undecided_quant_statements(text, reading=reading)]


# ------------------------------------------------------------------------------------------------------- false errors fixed


@pytest.mark.parametrize("text,kind", [
    ("The extension rose from 500 mm to 2 m, a fourfold increase.", "fold_change"),
    ("The mass rose from 500 g to 1.0 kg, a doubling.", "fold_change"),
    ("The mass fell from 2 kg to 500 g, a fall of 75 per cent.", "percent_change"),
    ("The length fell from 2 m to 50 cm, a fall of 75 per cent.", "percent_change"),
    ("The current fell from 3.0 A to 1.5 A, a fall of 50 per cent.", "percent_change"),
    ("The temperature rose from 300 K to 450 K, a rise of 50 per cent.", "percent_change"),
    ("The population fell from 800 to 200: it halved twice.", "fold_change"),
    ("The colony was doubled three times, growing from 50 to 400.", "fold_change"),
    ("The charge rose from 1.5e-6 C to 3.0e-6 C, a doubling.", "fold_change"),
    ("The field rose from 6.67 × 10⁻¹¹ N to 1.334 × 10⁻¹⁰ N, a doubling.", "fold_change"),
])
def test_si_reading_passes_correct_prose_arithmetic(text, kind):
    assert _statuses(text) == [(kind, "ENTAILED")], (text, _undecided(text))


@pytest.mark.parametrize("text", [
    "The extension rose from 500 mm to 2 m, a fourfold increase.",
    "The mass rose from 500 g to 1.0 kg, a doubling.",
    "The mass fell from 2 kg to 500 g, a fall of 75 per cent.",
    "The population fell from 800 to 200: it halved twice.",
])
def test_the_general_reading_misreads_what_the_si_reading_fixes(text):
    # today's reading (unchanged for every non-STEM branch) gets these wrong; the SI reading is what the STEM branches use
    assert any(s == "COUNTEREXAMPLE" for _k, s in _statuses(text, GENERAL))


@pytest.mark.parametrize("text", [
    "The efficiency rose from 60 per cent to 75 per cent after servicing, a rise of 15 per cent.",
    "The mass rose from 500 g to 1.0 kg, a tripling.",
    "The population fell from 800 to 100: it halved twice.",
    "The velocity changed from -4.0 m/s to -2.0 m/s, a fall of 50 per cent.",
    "The extension rose from 500 mm to 2 m, a doubling.",
])
def test_si_reading_still_catches_wrong_prose_arithmetic(text):
    assert ("COUNTEREXAMPLE" in [s for _k, s in _statuses(text)]), text


def test_negative_and_signed_changes():
    # a rise from -4.0 to -2.0 is a rise of 50 per cent of the earlier figure's magnitude
    assert _statuses("The velocity changed from −4.0 m/s to −2.0 m/s, a rise of 50 per cent.") == [("percent_change", "ENTAILED")]
    # a stated change with a U+2212 sign reverses its direction: 'a rise of −20 per cent' is a fall of 20
    assert _statuses("Sales went from 100 kg to 80 kg, a rise of −20 per cent.") == [("percent_change", "ENTAILED")]
    assert _statuses("Sales went from 100 kg to 80 kg, a rise of 20 per cent.") == [("percent_change", "COUNTEREXAMPLE")]


def test_a_stated_zero_change_is_decided_by_the_band():
    assert _statuses("The reading went from 10 to 10, a change of 0 per cent.") == [("percent_change", "ENTAILED")]
    assert _statuses("The reading went from 10 to 12, a change of 0 per cent.") == [("percent_change", "COUNTEREXAMPLE")]


def test_the_si_band_is_sign_aware_and_encoded_with_ite():
    q = extract_quant_checks("The velocity changed from -4.0 m/s to -2.0 m/s, a rise of 50 per cent.", request_id="r", claim_id="c", reading=SI_READING)[0]
    concl = q.problem.conclusion.model_dump(mode="json")["expr"]
    assert json.dumps(concl).count('"ite"') >= 2  # |computed - stated| and |computed|
    general = extract_quant_checks("Output rose from 100 to 120, a rise of 20 per cent.", request_id="r", claim_id="c")[0]
    assert '"ite"' not in json.dumps(general.problem.conclusion.model_dump(mode="json"))


@pytest.mark.parametrize("text,needle", [
    ("The mass rose from 2 kg to 3 m, a rise of 50 per cent.", "different dimensions"),
    ("The temperature rose from 20 °C to 40 °C, a doubling.", "offset temperature scale"),
    ("The temperature rose from 20 °F to 40 °F, a rise of 100 per cent.", "offset temperature scale"),
    ("Masses of 2.0 kg and 500 m, a total of 3.5 kg.", "different kinds or dimensions"),
])
def test_incomparable_figures_are_undecided_with_the_reason(text, needle):
    assert _statuses(text) == []
    assert any(needle in r for r in _undecided(text)), _undecided(text)


def test_totals_and_shares_convert_units():
    assert _statuses("Masses of 2.0 kg and 500 g, a total of 2.5 kg.") == [("total", "ENTAILED")]
    assert _statuses("Masses of 2.0 kg and 500 g, a total of 3.5 kg.") == [("total", "COUNTEREXAMPLE")]


def test_math_spans_are_masked_so_prose_and_maths_are_never_checked_twice():
    text = "The force rose from 2.0 N to 3.0 N, a rise of 50 per cent.\n$F = 2.0 \\times 3.0 = 6.0$ and the share 50% of 10 kg = 5 kg."
    kinds = [q.kind for q in extract_quant_checks(text, request_id="r", claim_id="c", reading=SI_READING)]
    assert kinds == ["percent_change"]


def test_undecided_statement_numbers_are_the_stem_claim_ids():
    text = "Using a = (v - u)/t:\na = (20 - 0)/4.0 = 5.0 m s⁻²\nThe mass rose from 2 kg to 3 m, a rise of 50 per cent."
    u = undecided_quant_statements(text, reading=SI_READING)
    assert [(x.paragraph, x.sentence) for x in u] == [(1, 3)]  # the third statement of paragraph 1: claim s1.3


def test_scale_words_are_spelled_out_only():
    # 'm' and 'k' are units in the SI reading: 300 K is a temperature, not 300,000
    assert _statuses("The gas went from 300 K to 600 K, a doubling.") == [("fold_change", "ENTAILED")]
    assert _statuses("Turnover rose from 2 million to 3 million, a rise of 50 per cent.") == [("percent_change", "ENTAILED")]
    assert _statuses("Turnover rose from 2 bn to 3 bn, a rise of 50 per cent.") == [("percent_change", "ENTAILED")]


# ------------------------------------------------------------------------------------------------- the core pack in SI


def _report(text: str, subject: str = "Physics", claims=None) -> SpecialistReport:
    claims = claims or [dict(claim_id="s1.1", claim_text=text, claim_role="quantitative")]
    return SpecialistReport(report_id="rep", request_id="req", task_id="task", agent_id="science-specialist", subject=subject, task_type="short_answer",
                            original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(request_id="req", task_id="task", report_id="rep", agent_id="science-specialist", subject=subject, task_type="short_answer", **c) for c in claims])


@pytest.mark.parametrize("text", [
    'The ruler is 12" long and the angle is 30′ wide.',
    'The rod is 0.5" thick and the arc is 12″ wide.',
])
def test_core_si_inch_marks_are_not_quotation_marks(text):
    rep = _report(text)
    # the general reading (every non-STEM branch, unchanged) reads the inch mark as a dangling quotation mark
    if '"' in text:
        assert any(f.code == "CORE-SRC-004" for f in CorePack().checks(rep))
    si = CorePack(reading=SI_READING).checks(rep)
    assert [f for f in si if f.code in ("CORE-SRC-003", "CORE-SRC-004")] == []


def test_core_si_closing_mark_after_a_year_stays_a_quotation_mark():
    rep = _report('The textbook says "the law was first stated in 1802" and nothing more.')
    si = CorePack(reading=SI_READING).checks(rep)
    assert not any(f.code == "CORE-SRC-004" for f in si)
    assert any(f.code == "CORE-SRC-003" and "first stated in 1802" in f.message for f in si)


def test_core_si_still_reads_genuine_quotations():
    rep = _report('The textbook says "energy is conserved in every collision" and the ruler is 12" long.')
    si = CorePack(reading=SI_READING).checks(rep)
    assert any(f.code == "CORE-SRC-003" and "energy is conserved" in f.message for f in si)
    assert not any(f.code == "CORE-SRC-004" for f in si)


def test_core_si_temperature_is_never_a_year():
    rep = _report("The furnace reached 1500 K before the sample melted at 1200 K, after it had been heated in 1990.")
    si = CorePack(reading=SI_READING)
    assert [f for f in si.formal_checks(rep) if f.kind == "chronology"] == []
    assert [f for f in si.checks(rep) if f.code == "CORE-CHR-001"] == []


def test_core_si_names_the_claim_of_a_prose_relation():
    text = "Using a = (v - u)/t:\na = (20 - 0)/4.0 = 5.0 m s⁻²\nThe force rose from 2.0 N to 3.0 N, a rise of 25 per cent."
    claims = [dict(claim_id="s1.1", claim_text="Using a = (v - u)/t:", claim_role="evidence"),
              dict(claim_id="s1.2", claim_text="a = (20 - 0)/4.0 = 5.0 m s⁻²", claim_role="quantitative"),
              dict(claim_id="s1.3", claim_text="The force rose from 2.0 N to 3.0 N, a rise of 25 per cent.", claim_role="quantitative")]
    rep = _report(text, claims=claims)
    formal = CorePack(reading=SI_READING).formal_checks(rep)
    assert [(f.kind, f.claim_ids) for f in formal] == [("percent_change", ("s1.3",))]
    assert verify(formal[0].problem, CFG).status.value == "COUNTEREXAMPLE"


def test_core_si_undecided_arithmetic_names_the_stem_claim():
    text = "Given: m = 2.0 kg\nThe mass rose from 2 kg to 3 m, a rise of 50 per cent."
    claims = [dict(claim_id="s1.1", claim_text="Given: m = 2.0 kg", claim_role="evidence"),
              dict(claim_id="s1.2", claim_text="The mass rose from 2 kg to 3 m, a rise of 50 per cent.", claim_role="quantitative")]
    found = [f for f in CorePack(reading=SI_READING).checks(_report(text, claims=claims)) if f.code == "CORE-QNT-001"]
    assert len(found) == 1 and found[0].claim_ids == ["s1.2"] and "different dimensions" in found[0].message
