"""Unit exponents written in ASCII with no caret (``m s-1``, ``mol dm-3``, ``J kg-1 K-1``, ``cm3``, ``mol/dm3``, ``m/s2``).

Before this reading the parser read ``3 m s-1`` as ``3 m s − 1``: a subtraction of a bare number from a quantity, so correct
work stated in ASCII units was an error (``v = 6 ÷ 2 = 3 m s-1`` was refuted with c = 3, r = 2, and ``c = 0.5 × 2 = 1 mol dm-3``
with r = −2), and a decimal power of ten stated that way (``[H+] = 10^(-3.3) = 5.01e-4 mol dm-3``) was refuted as soon as the
power was read. An exponent glued to its atom is now the atom's power: a hyphen-minus (or plus) and one digit, or one digit
2 to 9 after an atom of two or more letters (``cm3``) or after a slash (``m/s2``). The exponent reading is the parser's alone
(``parse_unit(..., ascii_exponents=True)``); every other caller of the unit table reads a digit inside a unit as before.
"""
from __future__ import annotations

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.nodes import BinOp, Quantity, Sym, walk
from epinoic_logic.stem.units import dimension_name, parse_unit

KEY = b"ascii-unit-exponents-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def receive(answer: str, subject: str = "Chemistry"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["stem-specialist"],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", "stem-specialist", "Calculate the value.", [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="stem-specialist", report_id="rep-t-0")
    return rc


def errors(rc) -> list:
    return [f for f in rc.findings if f.severity == "error"]


def stem_checks(rc) -> list:
    return [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-")]


@pytest.mark.parametrize("subject, answer", [
    ("Chemistry", "c = 0.5 × 2 = 1 mol dm-3"),             # an error at 22d6a5b (r = 1 − 3)
    ("Physics", "v = 6 ÷ 2 = 3 m s-1"),                   # an error at 22d6a5b (c = 3, r = 2)
    ("Chemistry", "c = 0.0005 × 1 = 0.0005 mol dm-3"),
    ("Chemistry", "c = 2 ÷ 4 = 0.5 mol dm-3"),
    ("Chemistry", "k = 0.693 / 30 = 0.0231 s-1"),
    ("Physics", "c = 4200 × 1 = 4200 J kg-1 K-1"),
    ("Physics", "a = 19.62 / 2 = 9.81 m/s2"),
    ("Physics", "rho = 2000 / 2 = 1000 kg/m3"),
    ("Chemistry", "V = 2 × 12.5 = 25 cm3"),
    ("Chemistry", "c = 0.5 / 2 = 0.25 mol/dm3"),
    ("Chemistry", "Kw = 1.0 × 10^-7 × 1.0 × 10^-7 = 1.0 × 10^-14 mol2 dm-6"),
    ("Physics", "v = 72 km h-1 = 20 m s-1"),               # a conversion between two ASCII units
    ("Chemistry", "[H+] = 10^(-3.3) = 5.01e-4 mol dm-3"),   # the verification's decimal powers with ASCII units
    ("Chemistry", "[H+] = 10^(-3.3) = 0.000501 mol dm-3"),
    ("Chemistry", "[H+] = 10^(-3.3) = 5.01 × 10^-4 mol dm-3"),
    ("Chemistry", "[H+] = 10^(-3.3) = 0.000501 mol/dm3"),
    ("Physics", "v = 10^(0.5) = 3.16 m s-1"),
    ("Physics", "x = 2^(1.5) = 2.83 m s-1"),
])
def test_correct_work_with_ascii_unit_exponents_is_checked_and_holds(subject, answer):
    rc = receive(answer, subject)
    assert not errors(rc), [(f.code, f.message[:200]) for f in errors(rc)]
    checks = stem_checks(rc)
    assert checks and all(fc.satisfied is True for fc in checks), [(fc.constraint_id, fc.formal_status) for fc in checks]


@pytest.mark.parametrize("subject, answer", [
    ("Chemistry", "c = 0.5 × 2 = 4 mol dm-3"),             # the arena's slip: a subtraction reading would have rescued it (4 − 3 = 1)
    ("Physics", "v = 6 ÷ 2 = 4 m s-1"),
    ("Chemistry", "k = 0.693 / 30 = 0.0531 s-1"),
    ("Physics", "rho = 2000 / 2 = 4000 kg/m3"),
    ("Chemistry", "V = 2 × 12.5 = 55 cm3"),
    ("Chemistry", "c = 0.5 / 2 = 0.55 mol/dm3"),
    ("Chemistry", "Kw = 1.0 × 10^-7 × 1.0 × 10^-7 = 4.0 × 10^-14 mol2 dm-6"),
    ("Physics", "v = 72 km h-1 = 25 m s-1"),
    ("Chemistry", "[H+] = 10^(-3.3) = 8.01e-4 mol dm-3"),
    ("Chemistry", "[H+] = 10^(-6.3) = 5.01e-4 mol dm-3"),   # an exponent 3 too large: no unit prefix absorbs it
])
def test_a_fault_stated_in_ascii_units_is_an_engine_error(subject, answer):
    rc = receive(answer, subject)
    assert [f for f in errors(rc) if f.code == "INT-SUBJ-001"], [(f.code, f.message[:120]) for f in rc.findings]


@pytest.mark.parametrize("answer, unit, dimension", [
    ("v = 3 m s-1", "m s-1", "speed"),
    ("a = 9.81 m s-2", "m s-2", "acceleration"),
    ("c = 0.10 mol dm-3", "mol dm-3", "concentration"),
    ("c = 0.10 mol/dm3", "mol/dm3", "concentration"),
    ("V = 25.0 cm3", "cm3", "volume"),
    ("a = 9.81 m/s2", "m/s2", "acceleration"),
    ("p = 1.2 kg m s-1", "kg m s-1", "momentum"),
])
def test_the_unit_is_read_with_its_ascii_exponent(answer, unit, dimension):
    doc = build_document(answer, None, "physics")
    quantities = [n for it in doc.items for ch in it.chains for op in ch.operands for r in op.readings for n in walk(r) if isinstance(n, Quantity)]
    assert [q.unit.text for q in quantities] == [unit]
    assert dimension_name(quantities[0].unit.dim) == dimension


@pytest.mark.parametrize("answer, profile", [
    ("T = 300 K-273 = 27", "physics"),        # more than one digit: a subtraction, as before
    ("x = 5 m-3 m = 2 m", "physics"),         # the same dimension follows the sign: a subtraction of two lengths
    ("x = 5 m - 3 m = 2 m", "physics"),       # spaced: a subtraction
])
def test_a_subtraction_glued_to_a_unit_stays_a_subtraction(answer, profile):
    doc = build_document(answer, None, profile)
    eq = [r for r in doc.relations if r.kind == "eq"]
    assert len(eq) == 1 and isinstance(eq[0].left.readings[0], BinOp) and eq[0].left.readings[0].op == "-"
    rc = receive(answer, "Physics")
    assert not errors(rc) and all(fc.satisfied is True for fc in stem_checks(rc))


def test_a_one_letter_symbol_with_a_glued_digit_after_a_number_is_not_read_as_a_unit_power():
    """'2 m2' may be 2·m₂ (a second mass), and 'H2' is a formula: the lexer reads the digit as a subscript, and only a
    denominator ('m/s2', 'kg/m3') reads it as a power."""
    doc = build_document("F = 2 m2 + 3", None, "physics")
    syms = {n.name for it in doc.items for ch in it.chains for op in ch.operands for r in op.readings for n in walk(r) if isinstance(n, Sym)}
    assert "m_2" in syms
    assert not [n for it in doc.items for ch in it.chains for op in ch.operands for r in op.readings for n in walk(r) if isinstance(n, Quantity)]


@pytest.mark.parametrize("text", ["m s-1", "mol dm-3", "cm3", "kg/m3", "J kg-1 K-1"])
def test_the_unit_table_reads_ascii_exponents_only_when_the_parser_asks(text):
    assert parse_unit(text) is None                       # the translator, the SI reading and the segmenter: unchanged
    expr = parse_unit(text, ascii_exponents=True)
    assert expr is not None and expr.known and expr.dim is not None


@pytest.mark.parametrize("text", ["m s-10", "m s-0", "cm1", "m-x", "kg-m", "dm3.5"])
def test_an_ascii_exponent_is_one_digit_glued_to_its_atom(text):
    assert parse_unit(text, ascii_exponents=True) is None
