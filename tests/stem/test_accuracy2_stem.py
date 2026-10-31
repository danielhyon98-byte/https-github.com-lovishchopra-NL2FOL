"""Accuracy round 2, STEM: the false alarms round 1's readings raised on correct answers are gone and the wrong answers stay
named. Every case is written for this round in wording of its own; nothing from a case is executed.

* V1I-04: an answer that mentions a rounding and then draws its conclusion from the value before the rounding ('802.8 kg,
  which rounds to 800 kg; but 802.8 kg exceeds 800 kg') compares the value itself with the bound: clean. The conclusion
  drawn from the rounded value stays stem_rounding_changes_conclusion.
* V1-STEM-GIV-FA: a value of the answer's own that the subject supplies (the boiling point of water beside a kitchen at
  22 °C, the speed of sound beside a train at 30 m s⁻¹) is no replaced given: a miscopy has the given's digits, one changed
  or in another order, and its size. A miscopied given stays stem_contradictory_givens.
* V1I-06: on a general branch (Geography), a worked sum or product of the request's quantities in different units ('2.4 +
  450' for 2.4 km and 450 m; '40 × 15' for 15 mm of rain on 40 m²) is stem_unit_error, read by the companions of the request's
  quantities (``branches.packs.request_unit_formal_checks``); the converted working, a rate per 1,000 and a percentage are
  clean."""
from __future__ import annotations

from fractions import Fraction

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem.relations import _miscopied

KEY = b"argdiag-stem-test-key-accuracy2-012345"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = {"Chemistry": "chemistry-specialist", "Physics": "physics-specialist", "Geography": "geography-specialist"}


def _receipt(subject: str, request: str, answer: str):
    agent = AGENTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _defects(rc) -> set[str]:
    return {d.defect for d in (rc.named_diagnostics or []) if d.severity in ("warning", "error")}


def _flags(rc) -> list:
    """Every STEM or subject-check flag at warning or above, and every failed formal check."""
    out = [(f.code, f.severity) for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    out += [(c.constraint_id, "failed") for c in rc.formal_checks if c.satisfied is False]
    return out


# ------------------------------------------------------------------------------- V1I-04: a rounding, then the value itself

LIFT = "A lift is overloaded if its load exceeds 800 kg. Nine people of mean mass 89.2 kg get in. Is the lift overloaded? [2 marks]"
POND = ("A pond is polluted if its ammonia concentration exceeds 2.0 mg dm⁻³. A 0.250 dm³ sample contains 0.52 mg of ammonia. Is the pond "
        "polluted? [2 marks]")
FUSE = "A fuse melts if the current through it is greater than 3 A. A heater draws a current of 3.2 A. Does the fuse melt? [1 mark]"
UNROUNDED = [
    ("Physics", LIFT, "m = 9 × 89.2 = 802.8 kg, which rounds to 800 kg; but 802.8 kg exceeds 800 kg, so the lift is overloaded."),
    ("Chemistry", POND, "c = 0.52 / 0.250 = 2.08 mg dm⁻³, which is 2 mg dm⁻³ to 1 s.f.; however, 2.08 mg dm⁻³ is more than 2.0 mg dm⁻³, so the "
                        "pond is polluted."),
    ("Physics", FUSE, "3.2 A to the nearest whole number is 3 A, but the current itself, 3.2 A, is greater than 3 A, so the fuse melts."),
]
ROUNDED = [
    ("Physics", LIFT, "m = 9 × 89.2 = 802.8 kg, which rounds to 800 kg, so the lift is not overloaded."),
    ("Chemistry", POND, "c = 0.52 / 0.250 = 2.08 mg dm⁻³, which is 2 mg dm⁻³ to 1 s.f., so the concentration does not exceed 2.0 mg dm⁻³ and "
                        "the pond is not polluted."),
    ("Physics", FUSE, "3.2 A to the nearest whole number is 3 A, so the current is not greater than 3 A and the fuse does not melt."),
]


@pytest.mark.parametrize("subject, request_text, answer", UNROUNDED, ids=["which-rounds-to-but", "to-1-sf-however", "nearest-whole-number-but"])
def test_a_conclusion_drawn_from_the_value_before_its_rounding_is_clean(subject, request_text, answer):
    assert _flags(_receipt(subject, request_text, answer)) == []


@pytest.mark.parametrize("subject, request_text, answer", ROUNDED, ids=["which-rounds-to", "to-1-sf", "nearest-whole-number"])
def test_twin_a_conclusion_drawn_from_the_rounded_value_is_still_named(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert "stem_rounding_changes_conclusion" in _defects(rc)


# ------------------------------------------------------------------------------- V1-STEM-GIV-FA: a value the subject supplies

PAN = ("1.5 kg of water at 15 °C is heated in a pan until it boils. The kitchen is at 22 °C. The specific heat capacity of water is "
       "4200 J kg⁻¹ °C⁻¹. Calculate the energy needed to bring the water to the boil. [3 marks]")
TRAIN = "A train moves at 30 m s⁻¹ while its whistle sounds at a frequency of 850 Hz. Calculate the wavelength of the sound in air. [2 marks]"
RUNNER = "A runner speeds up from 4.0 m s⁻¹ to 10 m s⁻¹ in 3.0 s. Calculate the acceleration. [2 marks]"
SALT = "Calculate the amount of potassium chloride in 7.45 g of the solid (M = 74.5 g mol⁻¹). [1 mark]"
KNOWLEDGE = [
    ("Physics", PAN, "ΔT = 100 − 15 = 85 °C.\nE = mcΔT = 1.5 × 4200 × 85 = 535500 J."),
    ("Physics", TRAIN, "λ = v/f = 340/850 = 0.40 m."),
    ("Physics", RUNNER, "a = (v − u)/t = (10 − 4.0)/3.0 = 2.0 m s⁻²."),
    ("Chemistry", SALT, "n = m/M = 7.45 / 74.5 = 0.100 mol."),
]
MISCOPIED = [
    ("Physics", RUNNER, "a = (v − u)/t = (10 − 7.0)/3.0 = 1.0 m s⁻²."),  # one digit changed
    ("Chemistry", SALT, "n = m/M = 4.75 / 74.5 = 0.0638 mol."),  # the digits in another order
]


@pytest.mark.parametrize("subject, request_text, answer", KNOWLEDGE, ids=["boiling-point-beside-a-room", "speed-of-sound-beside-a-train",
                                                                          "the-requests-speeds", "the-requests-mass"])
def test_a_value_the_subject_supplies_beside_a_given_of_its_dimension_is_clean(subject, request_text, answer):
    assert _flags(_receipt(subject, request_text, answer)) == []


@pytest.mark.parametrize("subject, request_text, answer", MISCOPIED, ids=["one-digit-changed", "digits-in-another-order"])
def test_twin_a_miscopied_given_is_still_a_contradictory_given(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert "stem_contradictory_givens" in _defects(rc)
    assert [c for c in rc.formal_checks if c.constraint_id.startswith("stem-giv") and c.satisfied is False]


def test_a_miscopy_has_the_givens_digits_and_size():
    F = Fraction
    assert _miscopied("8.55", "5.85", F(855, 100), F(585, 100))  # the digits in another order
    assert _miscopied("7.0", "4.0", F(7), F(4)) and _miscopied("15", "10", F(15), F(10))  # one digit changed
    assert not _miscopied("340", "20", F(340), F(20))  # another number of digits: the speed of sound
    assert not _miscopied("100", "25", F(100), F(25))  # the boiling point
    assert not _miscopied("3.0 × 10⁸", "20", F(3 * 10**8), F(20))  # the digits of a miscopy, the size of another value
    assert not _miscopied("−6.0", "4.0", F(-6), F(4))  # the other sign
    assert not _miscopied("4.0", "4.0", F(4), F(4))  # the value itself


# ------------------------------------------------------------------------------- V1I-06: a general branch reads the units

HIKE = "A hiker walks 2.4 km along a ridge and then 450 m down into a valley. Calculate the total distance walked in metres. [1 mark]"
STORM = ("During a storm, 15 mm of rain falls on a car park of area 40 m². Calculate the volume of rain that falls on the car park in m³. "
         "[2 marks]")
TOWN = "A town of 25,000 people has 300 births in a year. Calculate the birth rate per 1,000 people. [2 marks]"
SURVEY = "Of the 1,200 households surveyed, 300 recycle their glass. Calculate the percentage of households that recycle their glass. [1 mark]"
UNCONVERTED = [
    ("Geography", HIKE, "Total distance = 2.4 + 450 = 452.4 m."),
    ("Geography", STORM, "V = 40 × 15 = 600 m³."),
]
CONVERTED = [
    ("Geography", HIKE, "Total distance = 2400 + 450 = 2850 m."),
    ("Geography", STORM, "V = 40 × 0.015 = 0.6 m³."),
    ("Geography", TOWN, "Birth rate = 300 / 25,000 × 1,000 = 12 per 1,000."),
    ("Geography", SURVEY, "Percentage = 300 / 1,200 × 100 = 25%."),
]


@pytest.mark.parametrize("subject, request_text, answer", CONVERTED, ids=["converted-sum", "converted-volume", "rate-per-1000", "percentage"])
def test_control_the_converted_working_a_rate_and_a_percentage_are_clean(subject, request_text, answer):
    assert _flags(_receipt(subject, request_text, answer)) == []


# ------------------------------------------------------------------------------- the round's STEM readings are linear

def test_the_rounds_stem_readings_are_linear():
    """The rounding reading with the value before it compared and the bare-given reading with its miscopy test are read once per
    relation: two sizes of one answer cost in proportion (``tests/growth.py``; a ratio of CPU times, never a wall-clock bound).
    Port onto the integrated translator: the request's unit companions on a general branch are not ported
    (docs/ARGUMENT_DIAGNOSTICS.md section 20.4), so their half of this test is not either."""
    from epinoic_logic import lexis
    from epinoic_logic.stem import build_document
    from epinoic_logic.stem.document import clear_document_cache

    from ..growth import growth

    def clear() -> None:  # no call is served from a memo or the token cache
        clear_document_cache()
        lexis._cached_token_spans.cache_clear()

    lines = {
        "unrounded": (LIFT, "m = 9 × 89.2 = 802.8 kg, which rounds to 800 kg; but 802.8 kg exceeds 800 kg.\n", "physics"),
        "miscopied": (RUNNER, "a = (v − u)/t = (10 − 7.0)/3.0 = 1.0 m s⁻².\n", "physics"),
    }
    for name, (request_text, line, profile) in lines.items():
        def read(answer: str, request_text=request_text, profile=profile):
            return build_document(answer, request_text, profile)
        ratio, small, large = growth(read, line * 6, line * 24, repeat=2, clear=clear)
        assert ratio < 8.0, (name, ratio, small, large)

