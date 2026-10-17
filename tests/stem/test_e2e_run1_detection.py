"""The six injected faults the end-to-end simulation (run1: the website-to-backend flow with all sixteen specialists) did
not name, rebuilt from its genuine answers (tests/channel/data/e2e_run1_material.json, copied verbatim). Each was traced
to its cause.

Real detection gaps, fixed in the checks: the same fault written into the same line is named with its code on its claim,
and the genuine answer gains no error.

* ch-e1b, ``stem_arithmetic_slip`` on s1.2 (``[H⁺] = 10^(−8.2) = 9.31 × 10⁻⁹``): a power with a decimal exponent was
  outside the encodings ('a fractional or decimal power', ST-UNDEC-001), so no check read the pH lines. A closed base
  with no unit raised to a closed exponent that is no integer is now one value (``RealPower``), decided through an
  enclosure of exp(x·ln b) in Form S.
* ch-e1b, ``stem_substitution`` on s1.2: the same gap, and a harness defect behind it. The harness moved the exponent's
  leading digit (8.2 → 5.2): a change of exactly 10³ in the power, which the documented SI reading of the stated
  mol dm⁻³ absorbs (10^(−5.2) mol m⁻³ is 6.31 × 10⁻⁹ mol dm⁻³). An exponent of ten now changes in its first decimal
  digit (8.2 → 8.5: a factor 10^0.3, which no rounding and no unit factor absorbs).
* mai-e1, ``stem_arithmetic_slip`` on m10.1 (``21\\,131.40 - 18\\,000 = 6131.40``): the LaTeX thin space between digit
  groups was not read, so every operand written with it was cut ("unexpected '131.40' after an operand") and the answer
  had no check at all.
* hi-e1a, ``altered_quotation`` on h1.5 (``The Mathematics specialist states that "the model is not aly good fit for
  1923"``): the relayed report of mathematics-aa-specialist was named only "mathematics aa specialist", so "the
  Mathematics specialist" (the router's own name for it in the hand-off) credited the misquotation to no text: only
  unverifiable (CORE-SRC-003, a warning) where the colleague's report refutes it (INT-REQ-003).

Harness defects, fixed in scripts/arena: each variant is reported NOT APPLICABLE with its reason, neither a detection nor
a miss, because the changed figure lies in an expression holding a symbol no statement gives a value AND the change moves
none of the receipt's formal checks (a change in symbols that moves one stays a miss when unnamed).

* maa-e1a, ``stem_substitution`` (``(b) P(t + 1) = P₀e^(k(t + 1))`` → ``P(t + 4)``): the figure lies in an identity in
  the symbols P, t and k (a function of an unknown and symbolic powers, outside the encodings by design), no written
  calculation of figures; and the marker kept the part label "(b) ", which no claim carries.
* mai-e1, ``stem_substitution`` (``18\\,000 = M \\times \\frac{1-…}`` → ``\\frac{4-…}``): the '1' is no value the request
  gives (the question number and a mark), and the figure lies in an equation in the unknown M, no written calculation of
  figures.
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


def test_ch_e1b_substitution_moves_the_exponent_by_a_non_integer_and_is_named_on_s1_2():
    it = SPEC["ch-e1b"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker == "10^(−8.5)"
    assert "10^(−5.2)" not in inj.text and inj.text.replace("10^(−8.5)", "10^(−8.2)", 1) == it["response_text"]
    assert sm.not_applicable(inj) == ""  # a written calculation of figures with a stated value
    reply, rc = receive("ch-e1b", inj.text)
    claims = carrying(reply, inj.marker)
    assert claims == {"s1.2"} and named(rc, "INT-SUBJ-001", claims)


def test_ch_e1b_genuine_decimal_powers_are_checked_and_hold():
    _reply, rc = receive("ch-e1b")
    by_claim = {c: [fc for fc in rc.formal_checks if f"claim {c}:" in fc.detail or f"claim {c} " in fc.detail] for c in ("s1.2", "s1.3")}
    for claim, checks in by_claim.items():
        assert checks and all(fc.satisfied is True and fc.formal_status == "SATISFIABLE" for fc in checks), (claim, checks)
    assert not errors_on(rc, {"s1.2", "s1.3"})
    assert not [f for f in rc.structural_findings if "decimal power" in f.message]


def test_an_exponent_change_of_exactly_three_is_absorbed_by_the_si_reading_of_the_stated_unit():
    """The harness defect behind the ch-e1b substitution: 10^(−5.2) is exactly 10³ times 10^(−8.2), the factor between
    mol m⁻³ and mol dm⁻³, so under the documented reading of a unitless calculation stated in a unit (section 6.4: the
    stated value is read both as written and in SI) the changed line holds. Without the unit the same power is refuted:
    the decimal power itself is decided."""
    with_unit = "At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹ mol dm⁻³"
    _r, rc = receive("ch-e1b", with_unit)
    assert not errors_on(rc, {"s1.1"}) and [fc for fc in rc.formal_checks if fc.satisfied is True]
    _r, rc = receive("ch-e1b", "At pH 8.2: [H⁺] = 10^(−5.2) = 6.31 × 10⁻⁹")
    assert errors_on(rc, {"s1.1"})


@pytest.mark.parametrize("text, at, expected", [
    ("[H⁺] = 10^(−8.2) = 6.31", "8.2", "8.5"),       # the units digit of an exponent of ten: its first decimal digit moves instead
    ("10^{-7.8} = 1.58", "7.8", "7.5"),
    ("10**-12.5 = 3.2e-13", "12.5", "12.8"),
    ("10^0.4 = 2.51", "0.4", "0.7"),                  # the leading digit is a decimal one already: a factor 10^0.3
    ("10^(−8) = 1e-8", "8", None),                    # an integer exponent of ten: every change is a unit factor, no site
    ("(8.2 − 1) × 100 = 720", "8.2", "5.2"),          # not an exponent: the leading digit moves as before
    ("2^(1.5) = 2.83", "1.5", "4.5"),                 # an exponent of another base: the leading digit moves as before
    ("[H+] = 6.31e-9 mol dm-3", "9", None),           # the exponent of e-notation is an exponent of ten too
    ("E = 4.2E6 J", "6", None),
    ("the 9 cases = 9", "9", "6"),                    # a figure after a word ending in e is no exponent
])
def test_an_exponent_of_ten_never_changes_by_an_exact_power_of_ten(text, at, expected):
    a = text.index(at)
    assert sm.figure_change(text, a, a + len(at)) == expected


# --------------------------------------------------------------------------- mai-e1: the LaTeX thin space


def test_mai_e1_slip_between_thin_space_groups_is_named_on_m10_1():
    it = SPEC["mai-e1"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_arithmetic_slip")
    assert inj is not None and inj.marker == "21\\,131.40 - 18\\,000 = 6131.40" and sm.not_applicable(inj) == ""
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


# --------------------------------------------------------------------------- harness: not applicable


def test_maa_e1a_substitution_lies_in_an_identity_in_symbols_and_is_not_applicable():
    it = SPEC["maa-e1a"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker == "P(t + 4)"  # the part label "(b) " is left out, as every claim leaves it out
    why = sm.not_applicable(inj, it["question"])
    assert "no written calculation" in why and "'P'" in why and "'t'" in why
    # t has stated values (t = 0, t = 10, t = 6); the function P has none, so the identity is in a symbol with no value
    assert "no value is stated for 'P')" in why
    reply, _rc = receive("maa-e1a", inj.text)
    assert carrying(reply, inj.marker) == {"m3.1"}


def test_mai_e1_substitution_lies_in_an_equation_in_an_unknown_and_is_not_applicable():
    it = SPEC["mai-e1"]
    inj = sm.mutate_stem(it["response_text"], it["question"], "stem_substitution")
    assert inj is not None and inj.marker.startswith("M \\times \\frac{4-")
    why = sm.not_applicable(inj, it["question"])
    assert "no written calculation" in why and "no value is stated for 'M')" in why


@pytest.mark.parametrize("text, question, kind, applicable", [
    ("a = (20 - 0)/4.0 = 5.0 m s⁻²", "from rest to 20 m s⁻¹ in 4.0 s", "stem_arithmetic_slip", True),
    ("a = (20 - 0)/4.0 = 5.0 m s⁻²", "from rest to 20 m s⁻¹ in 4.0 s", "stem_substitution", True),
    ("v = d/t = 120 m / 8.0 s = 15 m s⁻¹.", "A runner covers 120 m in 8.0 s.", "stem_substitution", True),
    ("a percentage increase of (421 − 280) ÷ 280 × 100 = 50.4%, so about 50%.", "from 280 to 421 ppm", "stem_arithmetic_slip", True),
    ("x = 2y + 3 = 7", "Take 3 as given", "stem_substitution", False),   # the figure is a term of an expression in y, which has no value
    ("so low = mid + 1 is safe.", "Take 1 item", "stem_substitution", False),   # an update rule in symbols with no value
    ("Exact: k = (1/10) ln(8.04 × 10⁸) = 2.05", "Use 10 months.", "stem_arithmetic_slip", True),
    # a symbol with a value stated in the answer or in the request is a value: the expression is a written calculation
    ("y = 2, so x = 2y + 3 = 7", "Take 3 as given", "stem_substitution", True),
    ("x = k + 3 = 5", "Take k = 2 and 3 as given", "stem_substitution", True),
    ("x = k + 3 = 5", "Take 3 as given", "stem_substitution", False),
    ("so low = mid + 1 is safe. With mid = 1 the next low is 2.", "Take 1 item", "stem_substitution", True),
    ("y = 2, so x = 2y + 3 = 7", "", "stem_arithmetic_slip", True),
    ("x = 2y + 3 = 7", "", "stem_arithmetic_slip", False),
    # a calculation of figures counts whether or not a value is stated beside it (a stem-sub check reads it against the
    # symbols' bindings, and a chain may go on in the next line)
    ("v = u + at = 3 + 2 × 4", "It starts at 3 m s⁻¹ and accelerates at 2 m s⁻² for 4 s.", "stem_substitution", True),
    ("Total repaid $= 60 \\times 352.19$ (M1)\n\n$= 21\\,131.40$", "60 monthly payments", "stem_substitution", True),
])
def test_applicability_is_read_from_the_answer_text(text, question, kind, applicable):
    inj = sm.mutate_stem(text, question, kind)
    assert inj is not None
    assert (sm.not_applicable(inj, question) == "") is applicable, sm.not_applicable(inj, question)


def test_the_symbols_with_a_stated_value_are_read_from_the_answer_and_the_request():
    bound = sm.bound_symbols("P₀ = 250 and t = 10; λ = 0.087 h⁻¹, v_0 = 2.0 m s⁻¹, R_{1} = 4.0 Ω, so x = 2 or x = 3", "Take \\lambda \\approx 0.1")
    assert {"P_0", "t", "λ", "v_0", "R_1", "x", "\\lambda"} <= bound
    # no value is stated: prose, an equation in x, a function's value, a formula
    assert not sm.bound_symbols("Total = 5", "2x = 6", "P(6) = 250", "P = P₀e^(kt)") & {"Total", "tal", "x", "P"}
    assert sm._symbol_key("P₀") == sm._symbol_key("P_0") == sm._symbol_key("P_{0}") == "P_0"


def test_every_round7_symbolic_site_a_check_names_is_applicable():
    """The round-7 identities in symbols (low = mid + 4, 800 = 1600 e^(−5k), 6 − 9t, ln 5/λ, 4/R, ∫6t dt = 6t²) move a
    stem-sub, stem-alg or stem-sol check and are named: their symbols have stated values, so the reading counts them, and
    they would be misses if a finding did not name them."""
    r7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
    sites = [(tid, kind, sm.not_applicable(inj, it["question"])) for tid, it in sorted(r7["specialists"].items()) if sm.is_stem_subject(it["subject"])
             for kind in ("stem_arithmetic_slip", "stem_substitution") if (inj := sm.mutate_stem(it["response_text"], it["question"], kind)) is not None]
    assert {(t, k) for t, k, _w in sites} >= {("cs-t13", "stem_substitution"), ("maa-t13", "stem_arithmetic_slip"), ("maa-t13", "stem_substitution"),
                                               ("ph-p7b", "stem_substitution"), ("ph-t13", "stem_substitution"), ("maa-p7b", "stem_substitution")}
    assert [(t, k, w) for t, k, w in sites if w] == []


def test_moved_checks_compares_the_formal_checks_with_the_genuine_receipt():
    genuine = [("stem-alg-1", "ENTAILED", True), ("stem-eq-1", "ENTAILED", True)]
    assert ra.moved_checks(None, genuine) is None  # no genuine receipt: nothing can be said, nothing is excused
    assert ra.moved_checks(genuine, list(reversed(genuine))) == []
    assert ra.moved_checks(genuine, [("stem-alg-1", "COUNTEREXAMPLE", False), ("stem-eq-1", "ENTAILED", True)]) == ["stem-alg-1: ENTAILED -> COUNTEREXAMPLE"]
    assert ra.moved_checks(genuine, genuine[:1]) == ["stem-eq-1: ENTAILED -> absent"]


def _contained_round(tmp_path):
    (tmp_path / "specialists").mkdir()
    for tid in RUN1["order"]:
        (tmp_path / "specialists" / f"{tid}.json").write_text(json.dumps(SPEC[tid], ensure_ascii=False), encoding="utf-8")
    return ra.run_round(tmp_path)


def test_a_contained_round_names_the_four_gaps_and_reports_the_two_substitutions_not_applicable(tmp_path):
    out = _contained_round(tmp_path)
    recs = {(r["task_id"], r["variant"]): r for r in out["records"]}
    for key, code, claim in ((("ch-e1b", "stem_arithmetic_slip"), "INT-SUBJ-001", "s1.2"), (("ch-e1b", "stem_substitution"), "INT-SUBJ-001", "s1.2"),
                             (("mai-e1", "stem_arithmetic_slip"), "INT-SUBJ-001", "m10.1"), (("hi-e1a", "altered_quotation"), "INT-REQ-003", "h1.5")):
        rec = recs[key]
        assert rec["functional"] is True and not rec.get("not_applicable"), (key, rec.get("failure_reasons"))
        assert [f for f in rec["named_by"] if f["code"] == code and claim in f["claim_ids"]], (key, rec["named_by"])
    na = {(n["task_id"], n["variant"]): n for n in out["not_applicable_injections"]}
    assert set(na) == {("maa-e1a", "stem_substitution"), ("mai-e1", "stem_substitution")}
    assert "'P'" in na[("maa-e1a", "stem_substitution")]["reason"] and "'M'" in na[("mai-e1", "stem_substitution")]["reason"]
    for key, n in na.items():  # granted only because the change also moved none of the receipt's formal checks
        g = recs[(key[0], "genuine")]
        assert "moved none of the receipt's" in n["reason"] and recs[key]["formal_checks"] == g["formal_checks"], (key, n["reason"])
        assert "ST-UNDEC-001" in n["reason"]  # the receipt itself leaves the injected claim undecided, as it leaves the genuine one
    for key in na:
        rec = recs[key]
        assert rec["not_applicable"] is True and rec["functional"] is None and rec not in out["failures"]
    assert not [r for r in out["failures"] if r["variant"] != "genuine"], [(r["file"], r["variant"], r.get("failure_reasons")) for r in out["failures"]]
    assert out["transmissions"] == len(out["records"]) - 2
    assert out["metrics"]["transport"]["injected_faults"]["not_applicable"] == 2
    assert out["by_variant"]["stem_substitution"]["total"] == 1  # ch-e1b only: the two not applicable are in no count
    summary = (tmp_path / "summary.md").read_text()
    assert "## Injected faults not applicable" in summary and "maa-e1a.json [stem_substitution]" in summary and "mai-e1.json [stem_substitution]" in summary


def test_an_unnamed_change_in_symbols_that_moved_a_formal_check_is_a_miss_never_not_applicable(tmp_path, monkeypatch):
    """The harness's reading is only a candidate: with every STEM change read as one in symbols and no finding allowed to
    name anything, the changes that moved a formal check (the four gaps above) are misses, and only the two that moved
    none are reported not applicable."""
    monkeypatch.setattr(ra, "stem_not_applicable", lambda text, question, kind: "read as a change in symbols" if kind in sm.STEM_MUTATIONS else "")
    monkeypatch.setattr(ra, "findings_naming_injection", lambda *a, **k: [])
    out = _contained_round(tmp_path)
    recs = {(r["task_id"], r["variant"]): r for r in out["records"]}
    for key in (("ch-e1b", "stem_arithmetic_slip"), ("ch-e1b", "stem_substitution"), ("mai-e1", "stem_arithmetic_slip"), ("maa-e1a", "stem_arithmetic_slip")):
        rec = recs[key]
        assert not rec.get("not_applicable") and rec["functional"] is False and rec in out["failures"], key
        assert any("moved formal checks" in why and "so this is a miss" in why for why in rec["failure_reasons"]), (key, rec["failure_reasons"])
    assert {(n["task_id"], n["variant"]) for n in out["not_applicable_injections"]} == {("maa-e1a", "stem_substitution"), ("mai-e1", "stem_substitution")}


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

