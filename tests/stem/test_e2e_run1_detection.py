"""The six injected faults the end-to-end simulation (run1: the website-to-backend flow with all sixteen specialists) did
not name, rebuilt from its genuine answers (tests/channel/data/e2e_run1_material.json, copied verbatim). Each was traced
to its cause.

Real detection gaps, fixed in the checks: the same fault written into the same line is named with its code on its claim,
and the genuine answer gains no error.

* ch-e1b, ``stem_arithmetic_slip`` on s1.2 (``[H⁺] = 10^(−8.2) = 9.31 × 10⁻⁹``): a power with a decimal exponent was
  outside the encodings ('a fractional or decimal power', ST-UNDEC-001), so no check read the pH lines. A closed base
  with no unit raised to a closed exponent that is no integer is now one value (``RealPower``), decided through an
  enclosure of exp(x·ln b) in Form S.
* ch-e1b, ``stem_substitution`` on s1.2 (the pH substituted as 5.2: ``10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³``): the same gap, and
  a reading behind it. 10^(−5.2) is exactly 10³ times 10^(−8.2), the factor between mol m⁻³ and mol dm⁻³, so a power read
  as a bare number in SI matched the stated value in mol m⁻³. An antilogarithm stated as a concentration is now the
  concentration in mol dm⁻³, the unit the pH scale is defined in, so the recorded injection is named as recorded; the
  injection itself is the base one (every figure's leading digit moved by 3, an exponent of ten included).
* mai-e1, ``stem_arithmetic_slip`` on m10.1 (``21\\,131.40 - 18\\,000 = 6131.40``): the LaTeX thin space between digit
  groups was not read, so every operand written with it was cut ("unexpected '131.40' after an operand") and the answer
  had no check at all.
* hi-e1a, ``altered_quotation`` on h1.5 (``The Mathematics specialist states that "the model is not aly good fit for
  1923"``): the relayed report of mathematics-aa-specialist was named only "mathematics aa specialist", so "the
  Mathematics specialist" (the router's own name for it in the hand-off) credited the misquotation to no text: only
  unverifiable (CORE-SRC-003, a warning) where the colleague's report refutes it (INT-REQ-003).
* mai-e1, ``stem_substitution`` on m3.1 (``18\\,000 = M \\times \\frac{1-…}`` → ``\\frac{4-…}``): two gaps. The power
  ``(1 + 0.065/12)^{-60}`` was an integer power beyond 12, outside the encodings (ST-UNDEC-001), although its base is a
  closed value; it is now one value (a ``RealPower`` with an integer exponent: exact when it fits a literal, else the
  outward-rounded interval power). And the answer states M's value only in prose, under the name it gave the symbol
  ("Let $M$ be the monthly payment in euros." … "Her monthly payment is €352.19."): such a value is now a stated root of
  the equation in M (stem-sol, within the '=' band), so the changed equation is refuted on m3.1 and m5.1.

Every injection no finding names is a miss, counted as one: the harness never excuses it (an earlier attempt reported the
two substitutions "not applicable", which an independent verification showed excuses real misses; that rule is gone).

* maa-e1a, ``stem_substitution`` on m3.1 (``(b) P(t + 1) = P₀e^(k(t + 1))`` → ``P(t + 4)``): a harness defect (the marker
  kept the part label "(b) ", which no claim carries) and a gap of the encodings. ``P(t + 4)`` was read as the product
  P·(t + 4) and every power of e of an unknown was outside the encodings, so m3.1 was undecided on both answers. The
  request's model ``P = P₀e^(kt)`` is now a model whose variable the answer's applications name (t), an application
  ``P(t + 4)`` is the model at t + 4, and the link is a ``mod`` check (``stem/models.py``): some value of t, with P₀ and
  k within their stated values (250; 2.05 to 3 s.f.), must satisfy ``P₀e^(k(t + 4)) = P₀e^(k(t + 1))``. Read through
  positive variables (e^k and e^(kt)) it asks e^(3k) = 1, which no stated k allows: INT-SUBJ-001 on m3.1.
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from epinoic_logic.adapters.english_specialist.parser import documents_named
from epinoic_logic.adapters.sources import specialist_names
from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.enclosures import Interval, cross_check, enclose, exact_real_power
from epinoic_logic.stem.nodes import RealPower, Unsupported, walk
from epinoic_logic.stem.numbers import scan_number
from epinoic_logic.stem.relations import named_quantities
from epinoic_logic.translate.contracts import SuppliedText

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402
import stem_mutations as sm  # noqa: E402

RUN1 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "e2e_run1_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = RUN1["specialists"]
KEY = b"e2e-run1-detection-key-0123456789abcd"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
CHEM, MATH_AA, MATH_AI = "Chemistry", "Mathematics: Analysis and Approaches", "Mathematics: Applications and Interpretation"


def _docs(tid: str) -> list[SuppliedText]:
    """The texts the task supplies; a peer-dependent task also gets its peer's report as the arena relays it."""
    it = SPEC[tid]
    docs = [SuppliedText(**t) for t in it.get("supplied_texts", [])]
    if it.get("peer_of"):
        peer = SPEC[it["peer_of"]]
        docs.append(SuppliedText(document_id=f"peer:{it['peer_of']}", title=f"{peer['agent_id']} report rep-{it['peer_of']}-0 relayed through the hub",
                                 author=peer["agent_id"], text=peer["response_text"]))
    return docs


def receive(tid: str, answer: str | None = None, *, subject: str | None = None, request: str | None = None, docs=None):
    it = SPEC.get(tid, {})
    agent = it.get("agent_id", "stem-specialist")
    docs = _docs(tid) if docs is None else docs
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject or it["subject"], task_type="short_answer",
                           selected_agent_ids=[agent], allowed_document_ids=[d.document_id for d in docs]))
    m, _, _ = hub.dispatch("t", agent, request if request is not None else it["question"], list(docs))
    reply, rc = hub.receive("t", m.message_id, answer if answer is not None else it["response_text"], agent_id=agent, report_id="rep-t-0")
    return reply, rc


def norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def carrying(reply, marker: str) -> set[str]:
    return {c["claim_id"] for c in reply.payload["claims"] if norm(marker) in norm(c["claim_text"])}


def named(rc, code: str, claims: set[str]) -> list:
    return [f for f in list(rc.findings) + list(rc.structural_findings) if f.code == code and set(f.claim_ids) & claims]


def errors_on(rc, claims: set[str]) -> list:
    return [f for f in rc.findings if f.severity == "error" and f.code.startswith("INT-SUBJ") and set(f.claim_ids) & claims]


# --------------------------------------------------------------------------- ch-e1b: decimal powers of ten


def test_ch_e1b_slip_in_a_decimal_power_of_ten_is_named_on_s1_2():
    it = SPEC["ch-e1b"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_arithmetic_slip")
    assert inj is not None and inj.marker == "10^(−8.2) = 9.31"
    assert inj.text.replace("= 9.31 × 10⁻⁹", "= 6.31 × 10⁻⁹", 1) == it["response_text"]
    reply, rc = receive("ch-e1b", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"s1.2"}
    hits = named(rc, "INT-SUBJ-001", claims)
    assert hits and "10^(−8.2) = 9.31 × 10⁻⁹" in hits[0].message, [(f.code, f.claim_ids) for f in rc.findings]
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False and "claim s1.2" in fc.detail]
    assert failed and all(fc.constraint_id.startswith("stem-eq-") and fc.formal_status == "UNSATISFIABLE" for fc in failed)


def test_ch_e1b_substitution_of_the_recorded_round_is_named_on_s1_2():
    """The recorded fault, as 22d6a5b injects it: the request's pH 8.2 substituted as 5.2 with the genuine
    6.31 × 10⁻⁹ mol dm⁻³ kept. The power of ten is the concentration in mol dm⁻³, so the line holds in no reading."""
    it = SPEC["ch-e1b"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker == "10^(−5.2)"
    assert "At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³ [1]" in inj.text
    assert inj.text.replace("10^(−5.2)", "10^(−8.2)", 1) == it["response_text"]
    reply, rc = receive("ch-e1b", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"s1.2"}
    hits = named(rc, "INT-SUBJ-001", claims)
    assert hits and "10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³" in hits[0].message, [(f.code, f.claim_ids) for f in rc.findings]
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False and "claim s1.2" in fc.detail]
    assert failed and all(fc.constraint_id.startswith("stem-eq-") and fc.formal_status == "UNSATISFIABLE" for fc in failed)
    assert all("the power of ten read in mol dm⁻³" in fc.detail for fc in failed)


def test_ch_e1b_genuine_decimal_powers_are_checked_and_hold():
    _reply, rc = receive("ch-e1b")
    by_claim = {c: [fc for fc in rc.formal_checks if f"claim {c}:" in fc.detail or f"claim {c} " in fc.detail] for c in ("s1.2", "s1.3")}
    for claim, checks in by_claim.items():
        assert checks and all(fc.satisfied is True and fc.formal_status == "SATISFIABLE" for fc in checks), (claim, checks)
    assert not errors_on(rc, {"s1.2", "s1.3"})
    assert not [f for f in rc.structural_findings if "decimal power" in f.message]


@pytest.mark.parametrize("line", [
    "At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³",   # the recorded injection: 10^(−5.2) mol m⁻³ would be 6.31 × 10⁻⁹ mol dm⁻³
    "At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹",            # no unit: the power itself is decided
    "At pH 8.2: [H⁺] = 10^(−8.2) = 6.31 × 10⁻¹² mol dm⁻³",  # the stated value 10³ too small, the same factor the other way
    "[H+] = 10^(-11.2) = 6.31e-9 mol dm-3",                 # an exponent 3 too large, ASCII units
    "[OH⁻] = 10^{-2.8} = 1.58 \\times 10^{-6} mol dm⁻³",       # pOH 5.8 substituted as 2.8
    "6.31 × 10⁻⁹ mol dm⁻³ = 10^(−5.2)",                     # the sides the other way round
    "[H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ M",                     # molar, in chemistry: mol dm⁻³
    "[H⁺] = 10^(−4) = 1.0 × 10⁻⁷ mol dm⁻³",                 # an integer pH (7) substituted as 4
    "[H⁺] = 10⁻⁴ = 1.0 × 10⁻⁷ mol dm⁻³",
])
def test_an_exponent_change_by_a_unit_prefix_factor_is_named_in_a_concentration(line):
    """An integer change of the exponent changes the power by an integer power of ten, the factor of a unit prefix. The
    stated concentration is compared with the power read in mol dm⁻³, never with the power read as a bare number in SI,
    so such a change is an error like any other (it was absorbed: 10^(−5.2) mol m⁻³ is 6.31 × 10⁻⁹ mol dm⁻³)."""
    _r, rc = receive("ch-e1b", line)
    assert errors_on(rc, {"s1.1"}), [(f.code, f.message[:120]) for f in rc.findings]
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False]
    # an enclosed power is decided in Form S (UNSATISFIABLE), an exact one in Form E (COUNTEREXAMPLE)
    assert failed and all(fc.formal_status in ("UNSATISFIABLE", "COUNTEREXAMPLE") for fc in failed)
    if "mol" in line or line.endswith(" M"):  # stated as a concentration: the power is read in mol dm⁻³ (else decided as written)
        assert all("the power of ten read in mol dm⁻³" in fc.detail for fc in failed)


@pytest.mark.parametrize("line", [
    "At pH 8.2: [H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³",
    "[H+] = 10^(-3.3) = 5.01e-4 mol dm-3",
    "[H+] = 10^(-3.3) = 0.000501 mol dm-3",
    "[H+] = 10^(-3.3) = 5.01 × 10^-4 mol dm-3",
    "[H+] = 10^(-3.3) = 5.01e-4 mol/dm3",
    "[H+] = 10^(-3.3) = 5.01e-4 mol L-1",
    "[H⁺] = 10^(−3.3) = 5.01 × 10⁻⁴ M",
    "[H+] = 10^(-3.3) = 0.501 mmol dm-3",                    # the same concentration in mmol dm⁻³
    "[H+] = 10^(-8.2) = 6.31e-6 mol m-3",                     # and in mol m⁻³
    "6.31 × 10⁻⁹ mol dm⁻³ = 10^(−8.2)",
    "[H⁺] = 10^(−7) = 1.0 × 10⁻⁷ mol dm⁻³",                  # an integer pH
    "c = 10^(−3) = 1 mmol dm⁻³",
])
def test_an_antilogarithm_read_as_a_concentration_holds_in_every_unit_of_concentration(line):
    _r, rc = receive("ch-e1b", line)
    assert not errors_on(rc, {"s1.1"}), [(f.code, f.message[:160]) for f in rc.findings if f.severity == "error"]
    checks = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-eq-")]
    assert checks and all(fc.satisfied is True for fc in checks)


@pytest.mark.parametrize("subject, line", [
    ("Physics", "d = 20 × 25 = 0.5 km"),             # section 6.4: a unitless calculation stated in a unit is read as written and in SI
    ("Physics", "E = 10^(13.8) = 63 TJ"),             # an antilogarithm of another scale (energy in J): both readings, as before
    ("Chemistry", "x = 10^(−0.1) = 79.4%"),           # a per cent is no concentration
    ("Physics", "[H+] = 10^(-3.3) = 5.01e-4 M"),      # M is molar or mega in physics: no concentration in every reading
    ("Chemistry", "V = 10^(−3) = 1 dm³"),             # a volume: a unit factor written out, read in SI as before
])
def test_the_dual_reading_of_section_6_4_is_unchanged_outside_concentration_antilogarithms(subject, line):
    _r, rc = receive("ch-e1b", line, subject=subject, request="Evaluate.")
    assert not errors_on(rc, {"s1.1"})
    checks = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-eq-")]
    assert checks and all(fc.satisfied is True and "the power of ten read in mol dm⁻³" not in fc.detail for fc in checks)


@pytest.mark.parametrize("question, line, changed", [
    ("At pH 8.2, calculate [H+] in seawater.", "At pH 8.2: [H⁺] = 10^(−8.2) = 6.31 × 10⁻⁹ mol dm⁻³", "10^(−5.2)"),
    ("At pH 7.4, calculate [H+] in blood.", "[H⁺] = 10^(−7.4) = 3.98 × 10⁻⁸ mol dm⁻³", "10^(−4.4)"),
    ("When pOH = 5.8, calculate [OH-].", "[OH⁻] = 10^{-5.8} = 1.58 \\times 10^{-6} mol dm⁻³", "10^{-8.8}"),
    ("At pH 3.3, calculate [H+].", "[H+] = 10^(-3.3) = 5.01e-4 mol dm-3", "10^(-6.3)"),
])
def test_the_substitution_moves_the_leading_digit_of_an_exponent_of_ten_like_any_figure_and_is_named(question, line, changed):
    """The injection is the base one for every figure: an exponent of ten given by the request moves its leading digit by
    3 (a factor of exactly 10³ in the power), and the checks name it in a concentration stated in any unit."""
    inj = sm.mutate_stem(line, question, "stem_substitution")
    assert inj is not None and changed in inj.text and inj.marker == changed
    reply, rc = receive("ch-e1b", inj.text, request=question)
    claims = carrying(reply, inj.marker)
    assert claims and named(rc, "INT-SUBJ-001", claims), [(f.code, f.claim_ids) for f in rc.findings]


# --------------------------------------------------------------------------- mai-e1: the LaTeX thin space


def test_mai_e1_slip_between_thin_space_groups_is_named_on_m10_1():
    it = SPEC["mai-e1"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_arithmetic_slip")
    assert inj is not None and inj.marker == "21\\,131.40 - 18\\,000 = 6131.40"
    reply, rc = receive("mai-e1", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"m10.1"}
    hits = named(rc, "INT-SUBJ-001", claims)
    assert hits and "c = 15657/5, r = 30657/5" in hits[0].message  # 3131.40 computed, 6131.40 stated


def test_mai_e1_genuine_thin_space_arithmetic_is_checked_and_holds():
    _reply, rc = receive("mai-e1")
    checks = {fc.detail.split(":")[1].strip() if ":" in fc.detail else fc.detail: fc for fc in rc.formal_checks}
    held = [fc for fc in rc.formal_checks if fc.satisfied is True]
    assert any("21\\,131.40 - 18\\,000 = 3131.40" in fc.detail for fc in held), list(checks)
    assert any("20\\,491.72 - 9000.61 = 11\\,491.11" in fc.detail for fc in held)
    assert not [f for f in rc.findings if f.severity == "error" and f.code.startswith("INT-SUBJ")]
    assert not [f for f in rc.structural_findings if "after an operand" in f.message and ("131.40" in f.message or "'000'" in f.message)]


@pytest.mark.parametrize("text, end, value", [
    ("21\\,131.40", 10, Fraction(10565700, 500)), ("18\\,000", 7, Fraction(18000)), ("1\\,000\\,000", 11, Fraction(1_000_000)),
    ("12\\,5", 2, Fraction(12)),            # a group of one digit: no thousands group
    ("1234\\,567", 4, Fraction(1234)),      # four digits before the first separator: no thousands group
    ("0\\,123", 1, Fraction(0)),            # a leading zero: no thousands group
    ("5\\,\\mathrm{m}", 1, Fraction(5)),    # a thin space before a unit is a space
    ("1,000\\,000", 5, Fraction(1000)),     # one kind of separator throughout
])
def test_the_latex_thin_space_separates_thousands_groups_only(text, end, value):
    scan = scan_number(text, 0)
    assert scan is not None and scan.end == end and scan.number.value == value


# --------------------------------------------------------------------------- hi-e1a: the relayed Mathematics specialist


def test_hi_e1a_altered_quotation_of_the_mathematics_specialist_is_refuted_on_h1_5():
    it = SPEC["hi-e1a"]
    texts = _docs("hi-e1a")
    mutated, expected = ra.mutate(it["response_text"], "altered_quotation", texts)
    assert expected == "INT-REQ-003" and "the model is not aly good fit for 1923" in mutated
    reply, rc = receive("hi-e1a", mutated)
    claims = carrying(reply, "the model is not aly good fit for 1923")
    assert claims == {"h1.5"}
    hits = named(rc, "INT-REQ-003", claims)
    assert hits and "peer:maa-e1a holds all of its words but 'aly'" in hits[0].message
    h15 = next(c for c in reply.payload["claims"] if c["claim_id"] == "h1.5")
    assert {"document_id": "peer:maa-e1a", "excerpt": "the model is not aly good fit for 1923"} in h15["source_refs"]


@pytest.mark.parametrize("name", ["The Maths specialist", "The Math specialist", "The mathematics-aa-specialist"])
def test_the_same_misquotation_credited_by_another_name_of_the_colleague_is_refuted(name):
    it = SPEC["hi-e1a"]
    mutated, _expected = ra.mutate(it["response_text"], "altered_quotation", _docs("hi-e1a"))
    text = mutated.replace('The Mathematics specialist states that "the model is not aly', f'{name} states that "the model is not aly', 1)
    assert text != mutated
    reply, rc = receive("hi-e1a", text)
    claims = carrying(reply, "the model is not aly good fit for 1923")
    assert claims and named(rc, "INT-REQ-003", claims), [(f.code, f.claim_ids) for f in list(rc.findings) + list(rc.structural_findings)]


def test_hi_e1a_genuine_quotations_of_the_mathematics_specialist_stay_clean():
    reply, rc = receive("hi-e1a")
    h15 = next(c for c in reply.payload["claims"] if c["claim_id"] == "h1.5")
    assert [r["document_id"] for r in h15["source_refs"]] == ["peer:maa-e1a", "peer:maa-e1a"]
    assert not [f for f in list(rc.findings) + list(rc.structural_findings) if f.code in ("INT-REQ-003", "CORE-SRC-003", "CORE-SRC-005", "HI-SRC-001")]


def test_a_relayed_specialist_is_named_by_its_subject_word():
    assert specialist_names("mathematics-aa-specialist") == ["mathematics aa specialist", "mathematics specialist", "maths specialist", "math specialist"]
    assert specialist_names("english-a-lang-lit-specialist") == ["english a lang lit specialist", "english specialist"]
    assert specialist_names("history-specialist") == ["history specialist"]   # one word: unchanged
    assert specialist_names("Thomas Hardy") == [] and specialist_names("") == []
    docs = {d.document_id: d for d in _docs("hi-e1a")}
    assert documents_named("The Mathematics specialist states that X.", docs) == ["peer:maa-e1a"]
    assert documents_named("The Maths specialist states that X.", docs) == ["peer:maa-e1a"]
    assert documents_named("The Physics specialist states that X.", docs) == []
    assert documents_named("The textbook table shows prices rising fastest.", docs) == []


def test_a_misquotation_whose_sentence_names_no_text_is_still_only_unverifiable():
    """Control: the rule that a quotation credited to no text is refuted only by an own supplied text holding all its
    words but one or two (bus._uncredited_quotations) is unchanged; only the naming of the colleague changed."""
    it = SPEC["hi-e1a"]
    text = it["response_text"].replace('The Mathematics specialist states that "the model is not a good fit for 1923"',
                                       'It is said that "the model is not aly good fit for 1923"', 1)
    assert text != it["response_text"]
    reply, rc = receive("hi-e1a", text)
    claims = carrying(reply, "the model is not aly good fit for 1923")
    assert claims and named(rc, "CORE-SRC-003", claims) and not named(rc, "INT-REQ-003", claims)


# --------------------------------------------------------------------------- mai-e1: a power beyond 12 and a payment stated in prose


def test_mai_e1_substitution_in_the_annuity_equation_is_named_on_m3_1():
    """The changed constant (1 → 4 in ``\frac{1-(1+0.065/12)^{-60}}{0.065/12}``) makes the equation in M give 29.75, not
    the €352.19 the answer states for the monthly payment it named M: the stated root is refuted (stem-sol)."""
    it = SPEC["mai-e1"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker.startswith("M \\times \\frac{4-")
    reply, rc = receive("mai-e1", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"m3.1"}
    hits = named(rc, "INT-SUBJ-001", claims)
    assert hits and set(hits[0].claim_ids) == {"m3.1", "m5.1"} and "Her monthly payment is €352.19" in hits[0].message, \
        [(f.code, f.claim_ids) for f in rc.findings]
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False]
    assert [(fc.constraint_id, fc.formal_status) for fc in failed] == [("stem-sol-1", "UNSATISFIABLE")]
    assert not [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "m3.1" in f.claim_ids]


def test_mai_e1_genuine_payment_is_a_root_of_the_annuity_equation_and_holds():
    _reply, rc = receive("mai-e1")
    sol = [fc for fc in rc.formal_checks if fc.constraint_id == "stem-sol-1"]
    assert [(fc.formal_status, fc.satisfied) for fc in sol] == [("SATISFIABLE", True)]
    assert "the quantity it names M" in sol[0].detail and "'=' band" in sol[0].detail
    assert not [f for f in rc.findings if f.severity == "error"]
    # the power itself is read: m3.1 is no longer named undecided ('an integer power beyond 12 (-60)')
    assert not [f for f in rc.structural_findings if "integer power beyond" in f.message]


# --------------------------------------------------------------------------- integer powers beyond 12 of a closed value


@pytest.mark.parametrize("line, status", [
    ("$x = 2^{20} = 1048576$", "ENTAILED"),                    # exact: it fits a literal
    ("q = 3¹³ = 1594323", "ENTAILED"),                          # a superscript exponent
    ("z = (−1.5)^{13} = −194.6", "ENTAILED"),                   # a negative base: an odd power is negative
    ("$y = (2/3)^{-30} = 191751.06$", "ENTAILED"),
    ("$1.05^{20} = 2.6533$", "SATISFIABLE"),                   # exact but too long for a literal: the interval power
    ("$4000(1.003)^{132} = 5939.95$", "SATISFIABLE"),
    ("$4000(1.003)^{144} = 6157.36$", "SATISFIABLE"),
    ("v = 0^{20} = 0", "ENTAILED"),
])
def test_an_integer_power_beyond_12_of_a_closed_value_is_one_checked_value(line, status):
    _r, rc = receive("x", line, subject=MATH_AI, request="Evaluate.", docs=[])
    assert [(fc.formal_status, fc.satisfied) for fc in rc.formal_checks] == [(status, True)], [(fc.formal_status, fc.detail[:200]) for fc in rc.formal_checks]
    assert not [f for f in rc.findings if f.severity == "error"]


@pytest.mark.parametrize("wrong, shows", [
    ("$x = 2^{20} = 1048577$", "c = 1048576, r = 1048577"),
    ("z = (−1.5)^{13} = 194.6", "c = -1594323/8192"),
    ("$1.05^{20} = 2.9533$", ""),
    ("$4000(1.003)^{132} = 8939.95$", ""),
])
def test_a_wrong_value_of_an_integer_power_beyond_12_is_an_engine_error(wrong, shows):
    _r, rc = receive("x", wrong, subject=MATH_AI, request="Evaluate.", docs=[])
    hits = [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]
    assert hits and shows in hits[0].message


def test_an_integer_power_beyond_12_stays_outside_the_encodings_where_it_must():
    """A power of an expression in symbols is a polynomial of that degree (the bound holds); zero under a negative power
    is undefined; a value beyond about 10^±300 is never computed."""
    doc = build_document("y = x^{13} + 1 = 9", None, "mathematics_aa")
    assert any(r.outcome == "undecided" and "integer power beyond 12 (13)" in r.reason for r in doc.relations)
    _r, rc = receive("x", "w = 0^{-20} = 0", subject=MATH_AI, request="Evaluate.", docs=[])
    assert not rc.formal_checks and [f for f in rc.structural_findings if f.code == "ST-UNDEF-001"]
    _r, rc = receive("x", "u = 7^{900} = 1", subject=MATH_AI, request="Evaluate.", docs=[])
    assert not rc.formal_checks and [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "beyond the bounds" in f.message]


@pytest.mark.parametrize("answer, decided", [
    ("x² = 1.003^{60}\nx = ±1.094", False),     # an enclosed power in a step: undecided, as an irrational one
    ("A = P × 1.003^{60}\nA = 1.1969P", False),
    ("x² = 2^{14}\nx = ±128", True),           # an exact one: the step is proved
    ("A = P × 2^{14}\nA = 16384P", True),
])
def test_a_step_through_an_integer_power_beyond_12_is_decided_only_when_the_power_is_exact(answer, decided):
    _r, rc = receive("x", answer, subject=MATH_AA, request="Solve the equation.", docs=[])
    steps = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-alg")]
    assert not [f for f in rc.findings if f.severity == "error"]
    if decided:
        assert [(fc.formal_status, fc.satisfied) for fc in steps] == [("ENTAILED", True)]
    else:
        assert not steps and [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "encoded through an enclosure" in f.message]


# --------------------------------------------------------------------------- a value stated in prose for a named quantity

ANNUITY = "$$18\\,000 = M \\times \\frac{1-\\left(1+\\frac{0.065}{12}\\right)^{-60}}{\\frac{0.065}{12}}$$"
LET_M = "(a) Let $M$ be the monthly payment in euros.\n\n" + ANNUITY + "\n\n"


@pytest.mark.parametrize("answer, expected", [
    (LET_M + "Her monthly payment is €352.19.", "holds"),
    (LET_M + "The monthly payment is €352.19 (2 d.p.).", "holds"),
    (LET_M + "So the monthly payment is 352.19 euros.", "holds"),
    (LET_M + "The monthly payment is €352.20.", "holds"),                     # within the '=' band
    (LET_M + "Her monthly payment is €382.19.", "refuted"),                   # the leading digits moved
    ("(a) Let $x$ be the width of the garden in metres.\n\n$x(x + 3) = 40$\n\nThe width of the garden is 5.0.", "holds"),
    ("(a) Let $x$ be the width of the garden in metres.\n\n$x(x + 3) = 40$\n\nThe width of the garden is 6.0.", "refuted"),
    ("(a) $40 = x(x + 3)$, where $x$ is the width of the garden.\n\nThe width of the garden is 5.0.", "holds"),
    ("(a) Let $g$ be the gradient.\n\n$3g + 1.5 = 0$\n\nThe gradient is −0.50.", "holds"),
    ("(a) Let $g$ be the gradient.\n\n$3g + 1.5 = 0$\n\nThe gradient is −0.80.", "refuted"),
    ("(a) Let $L$ be the minimum length in metres.\n\n$4L = 9.72$\n\nThe minimum length is 2.45.", "holds"),   # 2.43, rounded
    ("(a) Let x be the width of the garden in metres.\n\nx(x + 3) = 40\n\nThe width of the garden is 5.0.", "holds"),   # plain text
    ("(a) Let x be the width of the garden in metres.\n\nx(x + 3) = 40\n\nThe width of the garden is 6.0.", "refuted"),
    ("(a) $x$ is the width of the garden.\n\n$x(x + 3) = 40$\n\nThe width of the garden is 5.0.", "holds"),
    ("(a) $3g + 1.5 = 0$, with $g$ the gradient.\n\nThe gradient is −0.50.", "holds"),
    ("(a) Let x be the width and y the length.\n\nx(x + 3) = 40\n\nThe width is 5.0.", "holds"),
    ("(a) Let $M$ be the monthly payment in euros.\n\n$18\\,000 = 51.108679M$, so the monthly payment is €352.19.", "holds"),
    ("(a) Let $M$ be the monthly payment in euros.\n\n$18\\,000 = 51.108679M$, so the monthly payment is €452.19.", "refuted"),
])
def test_a_value_stated_in_prose_for_a_named_quantity_is_a_root_of_its_equation(answer, expected):
    _r, rc = receive("x", answer, subject=MATH_AI, request="Find it.", docs=[])
    sol = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-sol") and "the quantity it names" in fc.detail]
    assert len(sol) == 1, [(fc.constraint_id, fc.detail[:120]) for fc in rc.formal_checks]
    errors = [f for f in rc.findings if f.severity == "error"]
    if expected == "holds":
        assert sol[0].satisfied is True and not errors
    else:
        # the error names the claims of the equation and of the value (one claim when one statement holds both)
        assert sol[0].satisfied is False and [f for f in errors if f.code == "INT-SUBJ-001" and set(f.claim_ids) == set(sol[0].claim_ids)]


@pytest.mark.parametrize("answer, why", [
    (LET_M + "If the monthly payment is €400.50, she pays more.", "a condition"),
    (LET_M + "If the rate is 5%, the monthly payment is €400.50.", "a condition before a comma"),
    (LET_M + "Although the monthly payment is €400.50, she pays.", "a concession"),
    (LET_M + "The monthly payment is not €400.50.", "a negation"),
    (LET_M + "The monthly payment is about €350.50.", "a qualifier"),
    (LET_M + "The monthly payment is 40.50 more than last year.", "a comparison after the value"),
    (LET_M + "The monthly payment is 400.50 when the rate doubles.", "a condition after the value"),
    (LET_M + "The total monthly payment is €400.50.", "another quantity"),
    (LET_M + "(b) Her monthly payment is €400.50.", "another part"),
    (LET_M + "What is the monthly payment?", "a question"),
    (LET_M + "$M = 352.19$\n\nHer monthly payment is €400.50.", "a value stated in maths"),
    (LET_M + "The monthly payment is €352.", "a whole number (a count the context may round up or down)"),
    ("(a) Let $n$ be the number of buses.\n\n$45n = 690$\n\nThe number of buses is 16.", "a whole number (16 buses for 15.3)"),
    ("(a) Let $x$ be the width of the garden in metres.\n\n$x(x + 3) = 40$\n\nThe width of the garden is 6.0 m.", "a value with a unit"),
    ("(a) Let $x$ be the width of the garden.\n\nThe width of the garden is 6.0.\n\n$x(x + 3) = 40$", "no equation before the value"),
    ("(a) Let $t$ be the time in years.\n\n$1000(1.05)^t = 2000$\n\nThe time is 14.2 years.", "an equation outside the encodings"),
    ("(a) " + ANNUITY + "\n\nHer monthly payment is €400.50.", "no name given to M"),
])
def test_a_prose_value_is_read_as_a_root_only_when_every_condition_holds(answer, why):
    """Each sentence fails one condition of the reading (docs/STEM_DESIGN.md, section 33, item 4), so no root is read
    and nothing is decided from it: no error, whatever the value."""
    doc = build_document(answer, "Find it.", "mathematics_ai")
    assert not [r for r in doc.relations if r.kind == "sol" and r.described], why
    _r, rc = receive("x", answer, subject=MATH_AI, request="Find it.", docs=[])
    assert not [f for f in rc.findings if f.severity == "error"], (why, [(f.code, f.message[:120]) for f in rc.findings if f.severity == "error"])


@pytest.mark.parametrize("statement, named", [
    ("Let $M$ be the monthly payment in euros.", [("M", {"monthly payment in euros", "monthly payment"})]),
    ("Let x be the width of the garden in metres.", [("x", {"width of the garden in metres", "width of the garden"})]),
    ("$40 = x(x + 3)$, where $x$ is the width of the garden.", [("x", {"width of the garden"})]),
    ("The energy is E = ½kx², with k the spring constant and x the extension.", [("k", {"spring constant"})]),
    ("$n$ is the number of years.", [("n", {"number of years"})]),
    ("Q = mL, where Q is the useful energy that vaporises the water.", [("Q", {"useful energy"})]),
    ("Let T be the half-life, so C(T) = ½C0:", [("T", {"half-life"})]),
    ("Let $X$ be the height of a sunflower in cm, with $X \\sim N(170, 12^2)$.", [("X", {"height of a sunflower in cm", "height of a sunflower"})]),
    ("Let us find the payment.", []),                    # no symbol
    ("Let M = 352.19.", []),                             # a value, not a description
    ("x is 5.", []),                                     # no determiner and description
])
def test_the_names_an_answer_gives_its_symbols(statement, named):
    assert [(sym, set(v)) for sym, v in named_quantities(statement)] == named


# --------------------------------------------------------------------------- harness: every unnamed injection is a miss


def test_maa_e1a_substitution_is_named_on_m3_1_by_the_model_evaluation():
    it = SPEC["maa-e1a"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker == "P(t + 4)"  # the part label "(b) " is left out, as every claim leaves it out
    assert "(b) P(t + 4) = P₀e^(k(t + 1))" in inj.text
    reply, rc = receive("maa-e1a", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"m3.1"}
    hits = named(rc, "INT-SUBJ-001", claims)
    assert hits and "the model evaluation" in hits[0].message and "P(t + 4) = P₀e^(k(t + 1))" in hits[0].message
    failed = [fc for fc in rc.formal_checks if fc.satisfied is False and "claim m3.1" in fc.detail]
    assert failed and all(fc.constraint_id.startswith("stem-mod-") and fc.formal_status == "UNSATISFIABLE" for fc in failed)
    assert all("stated in the request" in fc.detail and "variables (any real value): t" in fc.detail for fc in failed)


def test_maa_e1a_genuine_model_evaluations_are_checked_and_hold():
    _reply, rc = receive("maa-e1a")
    mods = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-mod-")]
    assert {c for fc in mods for c in ("m3.1", "m5.2") if f"claim {c}" in fc.detail} == {"m3.1", "m5.2"}  # P(t + 1) = …, P(6) = 250e^(6k)
    assert all(fc.satisfied is True and fc.formal_status == "SATISFIABLE" for fc in mods)
    assert not [f for f in rc.findings if f.severity == "error" and set(f.claim_ids) & {"m3.1", "m5.2"}]


#: the independent verification's probe round (wf/e2e-fixes/verify/rounds/na-probe): two misses a reading of "x = value"
#: bindings had excused as not applicable, with g, m and k stated in the request's prose
PROBE_ROUND = {
    "ma-n4": {"task_id": "ma-n4", "subject": MATH_AA, "agent_id": "mathematics-aa-specialist", "kb": "mathematics-aa", "task_type": "worked_solution",
              "question": "The radius of a circle is 3 cm. Find its area to 3 s.f.", "supplied_texts": [],
              "response_text": "The area is A = πr² where the radius is 3 cm.\nA = π × r² = π × 9 = 28.3 cm²"},
    "ph-n1": {"task_id": "ph-n1", "subject": "Physics", "agent_id": "physics-specialist", "kb": "physics", "task_type": "worked_solution",
              "question": "A ball of mass 0.50 kg falls from rest through a height of 20 m. Take g = 9.81 m s⁻². Find the kinetic energy it gains.",
              "supplied_texts": [], "response_text": "The kinetic energy gained equals the potential energy lost.\nE = m × 9.81 × 20 = 98.1 J\nSo the ball gains 98.1 J."},
    "ph-n2": {"task_id": "ph-n2", "subject": "Physics", "agent_id": "physics-specialist", "kb": "physics", "task_type": "worked_solution",
              "question": "A trolley of mass 2.0 kg is pushed with a force of 6.0 N for 4.0 s from rest. Find its final speed.", "supplied_texts": [],
              "response_text": "Acceleration: a = F / m = 6.0 / 2.0 = 3.0 m s⁻²\nFinal speed: v = a × 4.0 = 12 m s⁻¹"},
    "ph-n3": {"task_id": "ph-n3", "subject": "Physics", "agent_id": "physics-specialist", "kb": "physics", "task_type": "worked_solution",
              "question": "A spring of constant 200 N m⁻¹ is stretched by 0.15 m. Find the elastic energy stored.", "supplied_texts": [],
              "response_text": "The elastic energy is E = ½ k x² with k the spring constant.\nE = 0.5 × k × 0.15² = 2.25 J"},
}


def _contained(tmp_path, items: dict[str, dict], order):
    (tmp_path / "specialists").mkdir()
    for tid in order:
        (tmp_path / "specialists" / f"{tid}.json").write_text(json.dumps(items[tid], ensure_ascii=False), encoding="utf-8")
    return ra.run_round(tmp_path)


def test_the_verifiers_probe_misses_are_counted_as_misses(tmp_path):
    """A substitution of the request's g (9.81 → 6.81 with m stated only as 'a ball of mass 0.50 kg') and a slip in
    'E = 0.5 × k × 0.15² = 5.25 J' (k stated only as 'a spring of constant 200 N m⁻¹') are not named: two misses, counted
    as failures of the transport measure, exactly as on 22d6a5b. Nothing is reported not applicable."""
    out = _contained(tmp_path, PROBE_ROUND, sorted(PROBE_ROUND))
    assert (out["functional"], out["transmissions"]) == (27, 29)
    assert sorted((r["task_id"], r["variant"]) for r in out["failures"]) == [("ph-n1", "stem_substitution"), ("ph-n3", "stem_arithmetic_slip")]
    assert all(r["failure_reasons"][0].startswith("no INT-SUBJ-001 finding names the injected claims") for r in out["failures"])
    assert "not_applicable_injections" not in out and not any("not_applicable" in r for r in out["records"])
    assert "injected_faults" in out["metrics"]["transport"] and "not_applicable" not in out["metrics"]["transport"]["injected_faults"]
    summary = (tmp_path / "summary.md").read_text()
    assert "Injected faults not applicable" not in summary and "ph-n1.json [stem_substitution]" in summary.split("## Failures")[1]


def test_a_contained_round_names_all_six_faults(tmp_path):
    out = _contained(tmp_path, SPEC, RUN1["order"])
    recs = {(r["task_id"], r["variant"]): r for r in out["records"]}
    for key, code, claim in ((("ch-e1b", "stem_arithmetic_slip"), "INT-SUBJ-001", "s1.2"), (("ch-e1b", "stem_substitution"), "INT-SUBJ-001", "s1.2"),
                             (("mai-e1", "stem_arithmetic_slip"), "INT-SUBJ-001", "m10.1"), (("mai-e1", "stem_substitution"), "INT-SUBJ-001", "m3.1"),
                             (("maa-e1a", "stem_substitution"), "INT-SUBJ-001", "m3.1"), (("hi-e1a", "altered_quotation"), "INT-REQ-003", "h1.5")):
        rec = recs[key]
        assert rec["functional"] is True, (key, rec.get("failure_reasons"))
        assert [f for f in rec["named_by"] if f["code"] == code and claim in f["claim_ids"]], (key, rec["named_by"])
    assert recs[("maa-e1a", "stem_substitution")]["injected_claim_ids"] == ["m3.1"]
    assert [(r["task_id"], r["variant"]) for r in out["failures"] if r["variant"] != "genuine"] == []
    assert out["transmissions"] == len(out["records"]) and "not_applicable_injections" not in out
    assert out["by_variant"]["stem_substitution"] == {"functional": 3, "total": 3}  # ch-e1b, mai-e1 and maa-e1a named


def test_no_unnamed_stem_injection_is_ever_excused(tmp_path, monkeypatch):
    """With no finding allowed to name anything, every injection of the round is a failure: the harness has no rule that
    takes a miss out of the count, whatever the receipt says about the injected claim."""
    monkeypatch.setattr(ra, "findings_naming_injection", lambda *a, **k: [])
    out = _contained(tmp_path, SPEC, RUN1["order"])
    injected = [r for r in out["records"] if r["variant"] in ra.INJECTED_VARIANTS]
    assert injected and all(r["functional"] is False and r in out["failures"] for r in injected)
    assert out["transmissions"] == len(out["records"])
    undecided = [r for r in injected if r.get("undecided_on_injected_claims")]
    assert undecided  # diagnosed where the receipt says so, never excused
    for r in undecided:  # the failure reason quotes the receipt's own ST-UNDEC findings and still counts the miss
        reason = r["failure_reasons"][0]
        assert reason.startswith("no ") and f"names the injected claims {r['injected_claim_ids']}" in reason, reason
        assert all(u.startswith("ST-UNDEC-") and u in reason for u in r["undecided_on_injected_claims"]), reason
        assert "the receipt names the injected claims undecided: ST-UNDEC-" in reason and reason.endswith("counted as a miss)"), reason


# --------------------------------------------------------------------------- the RealPower reading


def _relations(line: str, profile: str = "chemistry"):
    doc = build_document(line, None, profile)
    return doc, [r for r in doc.relations if r.kind in ("eq", "link")]


@pytest.mark.parametrize("line", ["x = 10^(−8.2) = 6.31 × 10⁻⁹", "$x = 10^{-8.2} = 6.31 \\times 10^{-9}$", "x = 10**-8.2 = 6.31e-9",
                                  "x = 10^(8.2 − 7.8) = 2.51", "x = (3465/250)^(1/6) ≈ 1.55", "$q = 2^{\\frac{1}{3}} = 1.26$", "w = 2 × 10^0.5 = 6.32"])
def test_a_closed_power_with_a_non_integer_exponent_is_one_checked_value(line):
    doc, _rels = _relations(line, "mathematics_aa")
    eqs = [r for r in doc.relations if r.kind == "eq" and r.outcome == "check"]
    assert eqs, [(r.kind, r.outcome, r.reason) for r in doc.relations]
    assert any(isinstance(n, RealPower) for r in eqs for n in walk(r.left.readings[0]))
    _r, rc = receive("x", line, subject=MATH_AA, request="Evaluate.", docs=[])
    assert [fc for fc in rc.formal_checks if fc.satisfied is True] and not [fc for fc in rc.formal_checks if fc.satisfied is False]


@pytest.mark.parametrize("line, reason", [
    ("[H⁺] = 10^(−pH) = 1e-7", "a symbolic power"),            # an exponent with a symbol
    ("y = x^0.5 = 3", "a fractional or decimal power"),        # a base with a symbol
    ("s = (4.0 m)^0.5 = 2.0", "a fractional or decimal power"),  # a base with a unit
    ("t = 10^0.5^2 = 10", "a nested power"),
])
def test_a_non_integer_power_of_anything_but_a_closed_value_stays_undecided(line, reason):
    doc = build_document(line, None, "mathematics_aa")
    assert any(r.outcome == "undecided" and reason in r.reason for r in doc.relations), [(r.kind, r.outcome, r.reason) for r in doc.relations]
    assert not any(isinstance(n, RealPower) for r in doc.relations for op in (r.left, r.right) if op is not None and op.readings
                   for n in walk(op.readings[0]))


def test_a_non_integer_power_of_a_negative_or_zero_base_builds_no_check():
    _r, rc = receive("x", "s = (−8)^(1/3) = −2", subject=MATH_AA, request="Evaluate.", docs=[])
    assert not rc.formal_checks and [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "negative or zero" in f.message]
    _r, rc = receive("x", "z = 0^(0.5) = 0", subject=MATH_AA, request="Evaluate.", docs=[])
    assert [fc.satisfied for fc in rc.formal_checks] == [True]
    _r, rc = receive("x", "z = 0^(−0.5) = 0", subject=MATH_AA, request="Evaluate.", docs=[])
    assert not rc.formal_checks and [f for f in rc.structural_findings if f.code == "ST-UNDEF-001"]


@pytest.mark.parametrize("wrong", ["w = 2 × 10^0.5 = 9.32", "x = 10^{0.4} = 2.91", "x = (3465/250)^(1/6) ≈ 1.85"])
def test_a_wrong_value_of_a_real_power_is_an_engine_error(wrong):
    _r, rc = receive("x", wrong, subject=MATH_AA, request="Evaluate.", docs=[])
    assert [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]


def test_the_enclosure_of_a_real_power_contains_its_value_and_is_tight():
    b, x = Interval.point(Fraction(10)), Interval.point(Fraction(-41, 5))
    iv = enclose("exp", enclose("ln", b) * x)
    # 10^(−41/5) is the positive fifth root of 10^(−41): exact, with no float in the comparison
    assert iv.lo > 0 and iv.lo ** 5 <= Fraction(1, 10 ** 41) <= iv.hi ** 5
    assert iv.width <= Fraction(1, 10 ** 15) * abs(iv.mid)
    assert cross_check("pow", b, iv, exponent=x)
    assert not cross_check("pow", b, Interval.point(Fraction(631, 10 ** 11)), exponent=x)  # 6.31e-9 is not 10^(−8.2) to 10⁻⁹


def test_the_parser_records_an_unsupported_node_for_a_symbolic_exponent_only():
    doc = build_document("x = 10^(−pH) = 2", None, "chemistry")
    nodes = [n for r in doc.relations for op in (r.left, r.right) if op is not None and op.readings for n in walk(op.readings[0])]
    assert any(isinstance(n, Unsupported) and n.reason == "a symbolic power" for n in nodes)


# --------------------------------------------------------------------------- exact rational powers; steps never fail correct work

F = Fraction


@pytest.mark.parametrize("base, exponent, value", [
    (16, F(3, 4), 8), (4, F(3, 2), 8), (8, F(1, 3), 2), (27, F(2, 3), 9), (F(8, 27), F(2, 3), F(4, 9)), (8, F(-2, 3), F(1, 4)),
    (1, F(7, 10), 1), (10, F(2), 100), (F(1, 4), F(3, 2), F(1, 8)),
    (10, F(2, 5), None), (2, F(-7, 2), None), (F(3465, 250), F(1, 6), None),   # irrational: the encoder encloses it
    (0, F(1, 2), None), (-8, F(1, 3), None),                                      # no positive base: the encoder's own rules apply
    (2 ** 60, F(201, 2), None),                                                   # more than 30 digits: enclosed instead
])
def test_a_rational_power_has_its_exact_value(base, exponent, value):
    assert exact_real_power(F(base), exponent) == (None if value is None else F(value))


@pytest.mark.parametrize("line", ["$16^{3/4} = 8$", "y = 27^{2/3} = 9", "z = (8/27)^{-2/3} = 2.25", "w = 10^{2.0} = 100", "x = 8^{1/3} = 2"])
def test_a_rational_power_is_decided_exactly(line):
    _r, rc = receive("x", line, subject=MATH_AA, request="Evaluate.", docs=[])
    assert [(fc.formal_status, fc.satisfied) for fc in rc.formal_checks] == [("ENTAILED", True)], [(fc.formal_status, fc.detail) for fc in rc.formal_checks]
    assert "(exact)" in rc.formal_checks[0].detail and "enclosure" not in rc.formal_checks[0].detail


def test_a_wrong_rational_power_shows_the_exact_value_beside_the_stated_one():
    _r, rc = receive("x", "y = 27^{2/3} = 6", subject=MATH_AA, request="Evaluate.", docs=[])
    hits = [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]
    assert hits and "c = 9, r = 6" in hits[0].message


@pytest.mark.parametrize("answer", ["x² = 4^{1.5}, so x = 2√2 or x = −2√2.", "x² = 16^{3/4}\nx = ±2√2"])
def test_a_step_and_its_roots_through_a_rational_power_are_proved_exactly(answer):
    """16^(3/4) is exactly 8: the step x² = 8 ⇒ x = ±2√2 and its roots are proved, as they are for x² = 8 (an enclosure
    of 8 could never be shown equal to (2√2)², which made both checks false errors)."""
    _r, rc = receive("x", answer, subject=MATH_AA, request="Solve the equation.", docs=[])
    kinds = {fc.constraint_id.rsplit("-", 1)[0] for fc in rc.formal_checks}
    assert {"stem-alg", "stem-sol"} <= kinds and all(fc.formal_status == "ENTAILED" for fc in rc.formal_checks), [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks]
    assert not [f for f in rc.findings if f.severity == "error"]


@pytest.mark.parametrize("subject, answer", [
    ("Physics", "I = I₀ × 2^(−3.5) = 0.088 I₀"),      # 2^(−3.5) = 0.0884: correct to the 2 s.f. written
    ("Physics", "I = I₀ × 2^(−3.5)\nI = 0.0884 I₀"),
    ("Physics", "y = x × 10^{0.5}\ny = 3.16x"),
    (MATH_AA, "x² = 10^{0.4}\nx = ±1.585"),
])
def test_an_algebra_step_holding_an_irrational_power_is_never_a_false_error(subject, answer):
    """Correct work. A step is compared exactly (only a side that is one written value gets a band), so a step that holds
    an enclosed power stays undecided and is named, as every such step was before the power was read; the power's own
    arithmetic is still decided where it is written with figures (the roots of x² = 10^0.4 here)."""
    _r, rc = receive("x", answer, subject=subject, request="Show your working.", docs=[])
    assert not [f for f in rc.findings if f.severity == "error"], [(f.code, f.message[:160]) for f in rc.findings]
    assert not [fc for fc in rc.formal_checks if fc.constraint_id.startswith("stem-alg")]
    assert [f for f in rc.structural_findings if f.code == "ST-UNDEC-001" and "irrational value" in f.message]
    assert all(fc.satisfied is True for fc in rc.formal_checks)


def test_the_step_guard_concerns_enclosed_powers_only():
    """Control: the same step written with the decimal itself is decided as before (the guard changes no other step)."""
    _r, rc = receive("x", "I = I₀ × 0.0884\nI = 0.0884 I₀", subject="Physics", request="Show your working.", docs=[])
    assert [(fc.constraint_id, fc.formal_status) for fc in rc.formal_checks] == [("stem-alg-1", "ENTAILED")]

