"""Accuracy round 1, STEM misses (B items): each wrong answer below was delivered with no named defect before the round, and
each control stays clean. Every case is written for this round in wording of its own; nothing from a case is executed.

* ADV6-03: quantities the request gives in different units, combined in a working that substitutes into no symbol
  ('Total = 1.5 + 200 = 201.5 J' for 1.5 kJ and 200 J; 'A = 40 × 25 = 1000 m²' for a poster of 40 cm by 25 cm), or a bare
  result worked from them and then used as if in SI ('A = 10 × 10 = 100' for a plate of side 10 cm, then 'p = 80/100 =
  0.8 Pa'), are a missing conversion (stem_unit_error, the traced ST-UNIT-003 companion at warning); the same working with
  the conversion, or stated in the request's own units, is clean.
* ADV6-04: a bare value the working uses in place of the request's quantity of that dimension, the one its other values leave
  unused ('(10 − 6.0)/3.0' for a cyclist that speeds up from 4.0 m s⁻¹ to 10 m s⁻¹; '6.00/180' for 9.00 g of glucose;
  'ΔT = 65 − 25' for water heated from 15 °C to 65 °C), is a contradictory given (stem_contradictory_givens); the request's
  own values, a start from rest, a constant and a combined mass are clean.
* ADV6-05: a conclusion drawn from a value the answer rounds in words the round-5 reading did not cover ('which rounds to',
  'to the nearest whole number is', a predicate the request makes conditional with 'can safely' or 'exceeds') is
  stem_rounding_changes_conclusion; a rounding that keeps the conclusion's truth is clean."""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan

KEY = b"argdiag-stem-test-key-accuracy1-012345"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
AGENTS = {"Chemistry": "chemistry-specialist", "Physics": "physics-specialist", "Mathematics: Analysis and Approaches": "maths-specialist",
          "Biology": "biology-specialist"}
MAA = "Mathematics: Analysis and Approaches"


def _receipt(subject: str, request: str, answer: str):
    agent = AGENTS[subject]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _req, _rq = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="r1")
    return rc


def _defects(rc) -> set[str]:
    return {d.defect for d in (rc.named_diagnostics or []) if d.severity in ("warning", "error")}


def _stem_flags(rc) -> list:
    out = [(f.code, f.severity) for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    out += [(c.constraint_id, "failed") for c in rc.formal_checks if c.satisfied is False and c.constraint_id.startswith("stem-")]
    return out


# ------------------------------------------------------------------------------- ADV6-03: quantities combined unconverted

HEATER = ("A heater supplies 1.5 kJ of energy to a room and a fan supplies 200 J of energy to the same room. Calculate the total "
          "energy supplied in joules. [1 mark]")
POSTER = "A poster measures 40 cm by 25 cm. Calculate its area in m². [2 marks]"
PLATE = "A force of 80 N acts on a square plate of side 10 cm. Calculate the pressure on the plate in pascals. [2 marks]"
UNCONVERTED = [
    ("Physics", HEATER, "Total = 1.5 + 200 = 201.5 J."),
    (MAA, POSTER, "A = 40 × 25 = 1000 m²."),
    ("Physics", PLATE, "A = 10 × 10 = 100. p = F/A = 80 / 100 = 0.8 Pa."),
]


@pytest.mark.parametrize("subject, request_text, answer", UNCONVERTED, ids=["kJ-plus-J", "cm-sides-in-m2", "bare-cm2-area-in-Pa"])
def test_quantities_combined_without_their_conversion_are_a_unit_error(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert "stem_unit_error" in _defects(rc)
    assert [c for c in rc.formal_checks if c.constraint_id.startswith("stem-") and c.constraint_id.endswith("u") and c.satisfied is False]
    # the units are the request's, read by inference: a warning (INT-SUBJ-004), never an error charged as fact (INT-SUBJ-001)
    assert [f.severity for f in rc.findings if f.code == "INT-SUBJ-004"] and not [f for f in rc.findings if f.code == "INT-SUBJ-001"]


CONVERTED = [
    ("Physics", HEATER, "Total = 1500 + 200 = 1700 J."),
    (MAA, POSTER, "A = 0.40 × 0.25 = 0.10 m²."),
    (MAA, POSTER.replace("in m²", "in cm²"), "A = 40 × 25 = 1000 cm²."),
    ("Physics", PLATE, "Side = 0.10 m, so A = 0.10 × 0.10 = 0.010 m².\np = F/A = 80 / 0.010 = 8000 Pa."),
    ("Physics", PLATE, "A = 10 × 10 = 100. p = F/A = 80 / 100 = 0.8 N cm⁻²."),
    ("Physics", HEATER.replace("200 J", "0.30 kJ").replace("in joules", "in kJ"), "Total = 1.5 + 0.30 = 1.8 kJ."),
]


@pytest.mark.parametrize("subject, request_text, answer", CONVERTED,
                         ids=["converted-sum", "converted-area", "area-in-the-requests-units", "converted-pressure", "pressure-in-N-per-cm2",
                              "sum-in-one-unit"])
def test_control_the_converted_working_or_the_requests_own_units_are_clean(subject, request_text, answer):
    assert _stem_flags(_receipt(subject, request_text, answer)) == []


# ------------------------------------------------------------------------------- ADV6-04: a request value replaced

CYCLIST = "A cyclist speeds up from 4.0 m s⁻¹ to 10 m s⁻¹ in 3.0 s. Calculate the acceleration. [2 marks]"
GLUCOSE = "Calculate the amount of glucose in 9.00 g of the solid (M = 180 g mol⁻¹). [1 mark]"
KETTLE = "Water of mass 0.20 kg is heated from 15 °C to 65 °C (c = 4180 J kg⁻¹ K⁻¹). Calculate the energy supplied. [2 marks]"
REPLACED = [
    ("Physics", CYCLIST, "a = (v − u)/t = (10 − 6.0)/3.0 = 1.3 m s⁻²."),
    ("Chemistry", GLUCOSE, "n = m/M = 6.00 / 180 = 0.0333 mol."),
    ("Chemistry", KETTLE, "ΔT = 65 − 25 = 40 K.\nQ = mcΔT = 0.20 × 4180 × 40 = 33440 J."),
]


@pytest.mark.parametrize("subject, request_text, answer", REPLACED, ids=["initial-speed", "mass", "temperature-end"])
def test_a_bare_value_in_place_of_the_requests_quantity_is_a_contradictory_given(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert "stem_contradictory_givens" in _defects(rc)
    assert [c for c in rc.formal_checks if c.constraint_id.startswith("stem-giv") and c.satisfied is False]
    # the identity of a symbol across the request and the answer is a reading: a warning, never an error
    assert [f.severity for f in rc.findings if f.code == "INT-SUBJ-004"] and not [f for f in rc.findings if f.code == "INT-SUBJ-001"]


KEPT = [
    ("Physics", CYCLIST, "a = (v − u)/t = (10 − 4.0)/3.0 = 2.0 m s⁻²."),
    ("Chemistry", GLUCOSE, "n = m/M = 9.00 / 180 = 0.0500 mol."),
    ("Chemistry", KETTLE, "ΔT = 65 − 15 = 50 K.\nQ = mcΔT = 0.20 × 4180 × 50 = 41800 J."),
    ("Physics", "A trolley accelerates from rest to 10 m s⁻¹ in 2.5 s. Calculate the acceleration. [2 marks]", "a = (v − u)/t = (10 − 0)/2.5 = 4.0 m s⁻²."),
    ("Physics", "A 3.0 kg box is lifted through 2.0 m. Calculate the gain in gravitational potential energy. [2 marks]",
     "ΔEp = mgΔh = 3.0 × 9.81 × 2.0 = 58.9 J."),
    ("Physics", "Trolleys of mass 1.5 kg and 2.5 kg move off together at 0.50 m s⁻¹. Calculate their total momentum. [2 marks]",
     "p = mv = 4.0 × 0.50 = 2.0 kg m s⁻¹."),
    ("Chemistry", GLUCOSE, "n = m/M = 9.0 / 180 = 0.050 mol."),
    # a result carried on and converted, which the front end reads as a substitution into E = Pt: no substitution of the
    # request's givens, so none of its values is read as one
    ("Physics", "A 1.5 kW kettle runs for 2.0 hours. Calculate the energy transferred in kW h and in J. [2 marks]",
     "E = Pt = 1.5 × 2.0 = 3.0 kW h. In joules, E = 3.0 × 3.6 × 10⁶ = 1.08 × 10⁷ J."),
]


@pytest.mark.parametrize("subject, request_text, answer", KEPT,
                         ids=["requests-speeds", "requests-mass", "requests-temperatures", "from-rest", "a-constant", "a-combined-mass", "a-rounding",
                              "a-result-converted"])
def test_control_the_requests_own_values_a_start_from_rest_a_constant_and_a_combined_mass_are_clean(subject, request_text, answer):
    assert _stem_flags(_receipt(subject, request_text, answer)) == []


# ------------------------------------------------------------------------------- ADV6-05: rounding worded otherwise

RIVER = ("A river is polluted if its phosphate concentration exceeds 0.10 mg dm⁻³. A sample of 0.250 dm³ contains {m} mg of "
         "phosphate. Is the river polluted? [2 marks]")
GREENHOUSE = ("A greenhouse heater switches on when the temperature falls below 12.0 °C. The thermometer reads {t} °C. Does the heater "
              "switch on? [2 marks]")
FUSE = "A fuse can safely carry a current of at most 5 A. Two lamps draw {a} A and {b} A. Is the fuse safe? [2 marks]"
TURNED = [
    ("Chemistry", RIVER.format(m="0.026"),
     "c = 0.026 / 0.250 = 0.104 mg dm⁻³, which rounds to 0.10 mg dm⁻³, so the concentration does not exceed the limit and the river is not polluted."),
    ("Biology", GREENHOUSE.format(t="11.6"), "11.6 °C to the nearest whole number is 12 °C, so the temperature is not below 12.0 °C and the heater stays off."),
    ("Physics", FUSE.format(a="2.6", b="2.7"), "I = 2.6 + 2.7 = 5.3 A, which is 5 A to 1 s.f., so the fuse is safe."),
]


@pytest.mark.parametrize("subject, request_text, answer", TURNED, ids=["which-rounds-to", "to-the-nearest-whole-number", "can-safely"])
def test_a_conclusion_drawn_from_a_rounding_worded_otherwise_is_named(subject, request_text, answer):
    rc = _receipt(subject, request_text, answer)
    assert "stem_rounding_changes_conclusion" in _defects(rc)


HELD = [
    ("Chemistry", RIVER.format(m="0.021"),
     "c = 0.021 / 0.250 = 0.084 mg dm⁻³, which rounds to 0.08 mg dm⁻³, so the concentration does not exceed the limit and the river is not polluted."),
    ("Biology", GREENHOUSE.format(t="11.4"), "11.4 °C to the nearest whole number is 11 °C, so the temperature is below 12.0 °C and the heater switches on."),
    ("Physics", FUSE.format(a="2.1", b="2.3"), "I = 2.1 + 2.3 = 4.4 A, which is 4 A to 1 s.f., so the fuse is safe."),
    ("Physics", FUSE.format(a="2.6", b="2.7"), "I = 2.6 + 2.7 = 5.3 A. This is more than 5 A, so the fuse is not safe."),
    ("Physics", "Calculate the mean of the readings 4.5 cm, 4.6 cm and 4.6 cm. [1 mark]", "Mean = (4.5 + 4.6 + 4.6)/3 = 4.567 cm, which rounds to 4.6 cm."),
    ("Chemistry", "A gas is heated from 20 °C to 30 °C. State the rise in temperature. [1 mark]", "The temperature rises from 20 °C to 30 °C, a rise of 10 °C."),
]


@pytest.mark.parametrize("subject, request_text, answer", HELD,
                         ids=["rounding-keeps-the-truth", "nearest-whole-number-keeps-it", "sf-keeps-it", "unrounded-conclusion", "no-conclusion",
                              "a-range-is-no-rounding"])
def test_control_a_rounding_that_keeps_the_conclusions_truth_is_clean(subject, request_text, answer):
    assert _stem_flags(_receipt(subject, request_text, answer)) == []


# ------------------------------------------------------------------------------- the round's readings are linear

def test_the_rounds_stem_readings_are_linear():
    """The request-traced unit reading, the bare-given reading, the derived unit of a bare result, the prose rounding source
    and the further request conditions are read once per relation or prose value, each bounded (at most 12 numerals, 16
    values of a substitution, 64 characters between a value and its rounding, the request's first 4000 characters): two sizes
    of one answer cost in proportion (``tests/growth.py``; a ratio of CPU times, never a wall-clock bound)."""
    from epinoic_logic import lexis
    from epinoic_logic.stem import build_document
    from epinoic_logic.stem.document import clear_document_cache

    from ..growth import growth

    def clear() -> None:  # no call is served from the document memo or the token cache
        clear_document_cache()
        lexis._cached_token_spans.cache_clear()

    lines = {
        "unit": (HEATER, "Total = 1.5 + 200 = 201.5 J.\n", "physics"),
        "given": (CYCLIST, "a = (v − u)/t = (10 − 6.0)/3.0 = 1.3 m s⁻².\n", "physics"),
        "derived": (PLATE, "A = 10 × 10 = 100. p = F/A = 80 / 100 = 0.8 Pa.\n", "physics"),
        "rounding": (GREENHOUSE.format(t="11.6"), "11.6 °C to the nearest whole number is 12 °C, so the temperature is not below 12.0 °C.\n", "biology"),
        "condition": (FUSE.format(a="2.6", b="2.7") + " A cable can safely carry it." * 40, "I = 2.6 + 2.7 = 5.3 A, which is 5 A to 1 s.f., so the fuse is safe.\n", "physics"),
    }
    for name, (request_text, line, profile) in lines.items():
        def read(answer: str, request_text=request_text, profile=profile):
            return build_document(answer, request_text, profile)
        ratio, small, large = growth(read, line * 6, line * 24, repeat=2, clear=clear)
        assert ratio < 8.0, (name, ratio, small, large)
