"""STEM repair 5: the fifth independent test of the STEM completion found false errors on correct physics and computer-science
working, relations the branch read but neither checked nor named, conversions and restated roundings it missed, and a false
warning on correct uncertainty working. Each is fixed at its cause in the STEM front end, for its whole class, and every new
reading has a clean control (correct working is never flagged):

* rule ``rearranged-formula``: after a correct rearrangement ('P = V²/R', 'From P = V²/R, R = V²/P.' or 'Rearranging, R = V²/P.';
  'V = ε − Ir', 'Rearranging, I = (ε − V)/r.'), the next line that evaluates the formula ('P = (9.93 V)² / 6.0 Ω', or 'P = 16.4 W')
  was read as an algebra step from the rearrangement, its other symbols pinned to values of other parts (R = 2.4 Ω, V = 9.9 V), and
  failed (INT-SUBJ-001); it is the formula's evaluation, checked by its substitution, as it is right after the formula itself;
* rule ``part-value``: a symbol reused in a part for another quantity ('As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W.', the
  current in the 6.0 Ω resistor, after the battery's 'I = 4.1 A' of part (b)) was set against the other part's value and failed;
  when every binding of the symbol stands in another part and the chain's quantity has a value its part states before the line, the
  symbol's value also matches when the line's numeric side gives that value;
* the last chain a restatement restates (rule ``inline-restatement``'s companion): a value after a chain of its own statement that
  is no restatement of it ('Also log₂ 1000 ≈ 9.97, so 10 passes.') was set against a chain two paragraphs before ('1,000 ÷ 2^10 =
  0.98'); the statement's own computing chain is the last chain, so nothing older is reached for;
* rule ``bound-relation``: a maths run the prose gives as the value of a quantity it names, with only symbols that have stated
  values ('The battery's power output is 12 V × I = 60 W.', 'The lost volts are 0.50 Ω × I = 3.0 V.'), was read as an equation in an
  unknown (no check, no ST code) while 'P = 12 V × I = 60 W' was checked; it is the symbolic side under the stated bindings, unless
  its part solves it for one of its symbols ('The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A.');
* a '×' with a space before it and a symbol after it is a product ('E = 0.5 × k × 0.04 = 1.0 J'), never a magnification suffix
  '0.5×' (the relation had been cut and E bound to 0.5): the unknown k is named, ST-UNDEC-002, as for 'E = k × 0.04 = 1.0 J';
* rule ``prose-conversion``: a value the prose restates right after it in another unit ('55.0 cm³, that is 0.550 dm³', '55.0 cm³
  (0.550 dm³)') had no check; it is a unit conversion;
* rule ``rounding-cue`` for a value stated for a symbol, with rule ``same-place``: 'To 3 s.f., P = 16.5 W.' after 'P = … = 16.4 W'
  had no check (and the prose 'To 3 s.f., the power is 16.5 W.' held by adding the two half-widths); a value stated for a symbol
  with a rounding restates its last computed value, and a restatement rounded to the place the value it restates is written to must
  equal it;
* rule ``processed-data``: a line that takes a percentage of the raw cell ('2% of 1620 is 0.02 × 1620 = 32.4 counts min⁻¹', the
  uncertainty of the measured value by the answer's own rule) or a ratio of it to another value of its quantity ('1620/820 = 1.98')
  was set against the processed value (a false INT-SUBJ-004); it is not read. Found closing it: '1620 × 2% = 32.4 counts min⁻¹' was a
  false INT-SUBJ-001 (as written read 2% as 2, SI converted one side's unit only): a per cent taken of a number is also read as its
  fraction with the units as written.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks

R7 = json.loads((Path(__file__).parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))
SPEC: dict[str, dict] = R7["specialists"]
CORPUS = {it["id"]: it for it in json.loads((Path(__file__).parent / "data" / "stem_corpus.json").read_text(encoding="utf-8"))["items"]}
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-t13": "mathematics_aa", "maa-p7b": "mathematics_aa", "mai-t13": "mathematics_ai",
           "bi-t13": "biology", "ess-t13": "ess", "ch-t13": "chemistry", "cs-t13": "computer_science"}
HOLDS = {"bool": "UNSATISFIABLE"}
#: the anchor in ph-t13's part (d), right after its power line
PH_D = "= 16.4 W, so 16 W"


def _data(tid: str) -> tuple[str, ...]:
    return tuple(t["text"] for t in SPEC[tid].get("supplied_texts") or [])


def decide(text: str, request, profile: str, data: tuple = ()):
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.failure_severity, pc.description) for pc in plan.checks]
    return checks, [(f.code, f.severity, f.message) for f in list(doc.findings) + list(plan.findings)]


def task(tid: str, text: str):
    return decide(text, SPEC[tid]["question"], PROFILE[tid], _data(tid))


def holds(check) -> bool:
    kind, status = check[0], check[1]
    return status == HOLDS.get(kind, "ENTAILED") or (kind != "bool" and status == "SATISFIABLE")


def new(tid: str, text: str):
    """The checks and findings ``text`` has beyond the recorded answer's (by kind, status, severity and statement head)."""
    def key(c):
        return (c[0], c[1], c[2], c[3].split(" [claims")[0])
    base_c, base_f = task(tid, SPEC[tid]["response_text"])
    got_c, got_f = task(tid, text)
    bc = [key(c) for c in base_c]
    out_c = []
    for c in got_c:
        if key(c) in bc:
            bc.remove(key(c))
        else:
            out_c.append(c)
    bf = [(c, s, m.split(" in s")[0]) for c, s, m in base_f]
    out_f = []
    for c, s, m in got_f:
        k = (c, s, m.split(" in s")[0])
        if k in bf:
            bf.remove(k)
        else:
            out_f.append((c, s, m))
    return out_c, out_f


def replaced(tid: str, old: str, new_text: str) -> str:
    text = SPEC[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new_text)


def after(tid: str, anchor: str, line: str, sep: str = "\n") -> str:
    return replaced(tid, anchor, anchor + sep + line)


def before(tid: str, anchor: str, line: str, sep: str = "\n\n") -> str:
    return replaced(tid, anchor, line + sep + anchor)


def failing(checks) -> list:
    return [c for c in checks if not holds(c)]


def warnings(findings) -> list:
    return [f for f in findings if f[1] in ("warning", "error")]


def clean(tid: str, text: str) -> None:
    """No new failing check and no new warning or error finding (an info note is no flag)."""
    c, f = new(tid, text)
    assert not failing(c) and not warnings(f), (failing(c), warnings(f))


def named(tid: str, text: str, kind: str, severity: str = "error") -> list:
    """The new failing checks of ``kind`` (at ``severity``); at least one."""
    c, _f = new(tid, text)
    bad = [x for x in failing(c) if x[0] == kind and x[2] == severity]
    assert bad, (failing(c), c)
    return bad


# ============================================================================================ rule rearranged-formula
REARRANGED = [
    ("P = V²/R\n", "P = V²/R\nFrom P = V²/R, R = V²/P.\n", "'R = V²/P'"),
    ("P = V²/R\n", "P = V²/R\nRearranging, R = V²/P.\n", "'R = V²/P'"),
    ("P = V²/R\n", "P = V²/R\nP = V²/R, so R = V²/P.\n", "'R = V²/P'"),
    ("V = ε − Ir\n", "V = ε − Ir\nRearranging, I = (ε − V)/r.\n", "'I = (ε − V)/r'"),
    ("V = ε − Ir\n", "V = ε − Ir\nFrom V = ε − Ir, r = (ε − V)/I.\n", "'r = (ε − V)/I'"),
]


@pytest.mark.parametrize("old,new_text,step", REARRANGED)
def test_a_correct_rearrangement_never_makes_the_formula_s_evaluation_a_step(old, new_text, step):
    """The tester's ph-t13 plants (and the same with 'so' and with another symbol solved for): the rearrangement is checked as a step
    and holds, and the next line, which evaluates the formula, adds no check and no finding (it had failed as a step from the
    rearrangement: INT-SUBJ-001 on 'P = (9.93 V)² / 6.0 Ω' with R = 2.4 Ω and V = 9.9 V pinned)."""
    text = replaced("ph-t13", old, new_text)
    c, f = new("ph-t13", text)
    assert not failing(c) and not warnings(f), (failing(c), f)
    steps = [x for x in c if x[0] == "alg"]
    assert steps and all(holds(x) for x in steps) and [x for x in steps if f"the algebraic step: {step}" in x[3]], c
    assert not [x for x in steps if "the algebraic step: 'P = (9.93" in x[3] or "the algebraic step: 'V = 12 V" in x[3]], c


def test_a_value_stated_after_a_rearrangement_is_no_step_from_it():
    """'P = 16.4 W' right after 'From P = V²/R, R = V²/P.' gives P its value; it is no consequence of the rearrangement (it had failed
    as a step: INT-SUBJ-001)."""
    text = replaced("ph-t13", "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "P = V²/R\nFrom P = V²/R, R = V²/P.\nP = 16.4 W")
    checks, _f = task("ph-t13", text)
    assert not failing(checks), failing(checks)
    assert [x for x in checks if x[0] == "alg" and "'R = V²/P'" in x[3]] and not [x for x in checks if x[0] == "alg" and "'P = 16.4 W'" in x[3]]


def test_a_wrong_rearrangement_and_a_slip_after_a_correct_one_still_fail():
    """The rule never hides a fault: the wrong rearrangement 'R = P/V²' fails as the step it is, and after a correct rearrangement a
    substitution slip (9.39 V for 9.93 V) fails its substitution and arithmetic."""
    bad = named("ph-t13", replaced("ph-t13", "P = V²/R\n", "P = V²/R\nFrom P = V²/R, R = P/V².\n"), "alg")
    assert "'R = P/V²'" in bad[0][3] and bad[0][1] == "COUNTEREXAMPLE"
    slip = replaced("ph-t13", "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nRearranging, R = V²/P.\nP = (9.39 V)² / 6.0 Ω = 16.4 W")
    c, _f = new("ph-t13", slip)
    kinds = {x[0] for x in failing(c)}
    assert {"sub", "eq"} <= kinds, failing(c)


def test_a_step_that_solves_an_equation_is_still_checked():
    """Only the evaluation of a formula after its rearrangement stops being a step: a line that solves an equation stays a step
    ('2x + 3 = 7' then 'x = 2' holds, 'x = 3' fails)."""
    ok, _f = decide("2x + 3 = 7\nx = 2\n", "Solve 2x + 3 = 7.", "mathematics_aa")
    bad, _f = decide("2x + 3 = 7\nx = 3\n", "Solve 2x + 3 = 7.", "mathematics_aa")
    assert [x[1] for x in ok if x[0] == "alg"] == ["ENTAILED"] and [x[1] for x in bad if x[0] == "alg"] == ["COUNTEREXAMPLE"]


# ============================================================================================ rule part-value
@pytest.mark.parametrize("line", [
    "As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W.",
    "As a check, P = I²R = (1.66 A)² × 6.0 Ω = 16.5 W.",
    "As a check, P = VI = 9.93 V × 1.655 A = 16.4 W.",
])
def test_a_symbol_reused_for_another_quantity_matches_the_value_its_part_gives(line):
    """The tester's plant and two variants: I is the current in the 6.0 Ω resistor (its every binding, 4.1 A, stands in part (b)), and
    the line re-derives part (d)'s P = 16.4 W, so the substitution holds by rule part-value (it had failed: INT-SUBJ-001 on c4.4)."""
    text = after("ph-t13", PH_D, line)
    c, f = new("ph-t13", text)
    assert not failing(c) and not warnings(f), (failing(c), f)
    subs = [x for x in c if x[0] == "sub"]
    assert subs and all("rule part-value" in x[3] and "P = 16.4 W (s4.3)" in x[3] for x in subs), subs


@pytest.mark.parametrize("line", ["As a check, P = I²R = (1.565 A)² × 6.0 Ω = 14.7 W.", "As a check, P = I²R = (1.565 A)² × 6.0 Ω = 16.4 W."])
def test_a_wrong_value_of_a_reused_symbol_still_fails(line):
    """1.565 A matches neither a binding of I nor, through the line, the part's P = 16.4 W: the substitution fails (with a consistent
    result as with an inconsistent one)."""
    bad = named("ph-t13", after("ph-t13", PH_D, line), "sub")
    assert "rule part-value" in bad[0][3]


def test_without_a_value_its_part_states_a_reused_symbol_is_set_against_its_bindings_alone():
    """Rule part-value needs the part's own earlier value of the chain's quantity: part (d)'s first power line has none, so its V is
    set against part (c)'s 9.9 V as before, and a wrong V fails."""
    c, _f = new("ph-t13", replaced("ph-t13", "P = (9.93 V)² / 6.0 Ω = 16.4 W", "P = (9.39 V)² / 6.0 Ω = 14.7 W"))
    subs = [x for x in failing(c) if x[0] == "sub"]
    assert subs and not any("rule part-value" in x[3] for x in subs), failing(c)
    recorded, _f = task("ph-t13", SPEC["ph-t13"]["response_text"])
    assert not any("rule part-value" in x[3] for x in recorded)


# ============================================================================================ the last chain a restatement restates
def test_a_consequence_after_its_own_statement_s_chain_restates_no_older_chain():
    """'Also log₂ 1000 ≈ 9.97, so 10 passes.': the statement's own chain is the last chain before the value, and the value is no inline
    restatement of it (a count of passes), so nothing is planned for it (it had been set against '1,000 ÷ 2^10 = 0.98': INT-SUBJ-001
    naming the recorded claim c8.3)."""
    text = before("cs-t13", "Next step: trace", "Also log₂ 1000 ≈ 9.97, so 10 passes.")
    c, f = new("cs-t13", text)
    assert not failing(c) and not warnings(f) and not [x for x in c if x[0] == "res"], c


def test_an_inline_restatement_of_its_own_statement_s_chain_is_still_checked():
    ok, _f = new("cs-t13", before("cs-t13", "Next step: trace", "Also log₂ 1000 ≈ 9.97, so 10."))
    bad, _f = new("cs-t13", before("cs-t13", "Next step: trace", "Also log₂ 1000 ≈ 9.97, so 9."))
    assert [x[1] for x in ok if x[0] == "res"] == ["ENTAILED"] and [x[1] for x in bad if x[0] == "res"] == ["COUNTEREXAMPLE"]


@pytest.mark.parametrize("item,value", [("stem-math-012", "'5'"), ("stem-math-013", "'10'")])
def test_a_condition_or_a_formula_in_the_restating_sentence_is_no_chain_it_restates(item, value):
    """'So the gradient of the curve at $x = 1$ is 5.' and 'The area between the curve y = 3x² + 1 and the x-axis from x = 0 to x = 2 is
    therefore 10 square units.' restate the chain of the statement before, as they did: the sentence's own 'x = 1' and 'y = 3x² + 1'
    name a condition and an object, never a computation."""
    it = CORPUS[item]
    checks, _f = decide(it["response_text"], it["question"], "mathematics_aa")
    res = [x for x in checks if x[0] == "res"]
    assert len(res) == 1 and res[0][1] == "ENTAILED" and f"the restated result: {value}" in res[0][3], res


# ============================================================================================ rule bound-relation
@pytest.mark.parametrize("line,shown", [
    ("The battery's power output is 12 V × I = 60 W.", "12 V × I = 60 W"),
    ("The battery's power output is I × 12 V = 60 W.", "I × 12 V = 60 W"),
    ("The lost volts are 0.50 Ω × I = 3.0 V.", "0.50 Ω × I = 3.0 V"),
])
def test_a_relation_the_prose_gives_as_a_quantity_s_value_is_checked_under_the_stated_values(line, shown):
    """The tester's plants: every symbol has a stated value (I = 4.1 A), so the relation is no equation in an unknown; it is checked like
    'P = 12 V × I = 60 W' and fails (before: neither a check nor an ST code)."""
    bad = named("ph-t13", after("ph-t13", PH_D, line), "sub")
    head = "battery power output" if "battery" in line else "lost volt"
    assert f"the substitution: '{shown}'" in bad[0][3] and "rule bound-relation" in bad[0][3] and f"the value of the {head}" in bad[0][3], bad


@pytest.mark.parametrize("line", ["The battery's power output is 12 V × I = 49.7 W.", "The lost volts are 0.50 Ω × I = 2.07 V."])
def test_the_same_relation_written_correctly_holds(line):
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "sub" and "rule bound-relation" in x[3]], c


@pytest.mark.parametrize("line", ["The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A.", "So 16.4 W = I² × 6.0 Ω, giving a current of 1.65 A.",
                                  "The equation is 12 V × I = 60 W."])
def test_an_equation_its_part_solves_or_that_the_prose_calls_an_equation_stays_unchecked(line):
    """A relation its part solves for a symbol ('so I = 1.65 A'), one with no quantity named before it, and one the prose calls an
    equation are equations, as before: no check (the reused I is the current in the 6.0 Ω resistor)."""
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and not [x for x in c if "rule bound-relation" in x[3]], c


@pytest.mark.parametrize("item", ["stem-math-011"])
def test_a_maths_equation_in_a_symbol_bound_earlier_stays_an_equation(item):
    it = CORPUS[item]
    checks, _f = decide(it["response_text"], it["question"], "mathematics_aa")
    assert not [x for x in checks if "rule bound-relation" in x[3]]


# ============================================================================================ a '×' before a symbol is a product
@pytest.mark.parametrize("text", ["E = 0.5 × k × 0.04 = 1.0 J", "E = k × 0.04 = 1.0 J", "E = 0.5 × x × 0.04 = 1.0 J", "F = 2 × k = 6 N"])
def test_a_product_with_an_unknown_after_a_spaced_times_sign_is_named_unchecked(text):
    """'0.5 × k' had been read as the magnification '0.5×', the relation cut and E bound to 0.5 (ST-PARSE-001); the unknown is named."""
    checks, findings = decide(text, None, "physics")
    codes = [c for c, _s, _m in findings]
    assert "ST-UNDEC-002" in codes and "ST-PARSE-001" not in codes and not checks, (checks, findings)


@pytest.mark.parametrize("text,stated", [("magnification = 2500 µm ÷ 50 µm = 50×", "50×"), ("magnification = 2500 µm ÷ 50 µm = 50 ×", "50×")])
def test_a_magnification_suffix_is_read_as_before(text, stated):
    checks, findings = decide(text, None, "biology")
    assert [x[0] for x in checks] == ["eq"] and holds(checks[0]) and not warnings(findings), (checks, findings)


# ============================================================================================ rule prose-conversion
@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³, that is 0.550 dm³.", "The mixture is 55.0 cm³ (0.550 dm³).", "The mixture is 55.0 cm³, or 0.550 dm³.",
                                  "The mixture is 55.0 cm³, i.e. 0.550 L.", "The mixture is 55.0 cm³, or about 0.55 dm³."])
def test_a_wrong_conversion_the_prose_states_fails(line):
    bad = named("ch-t13", after("ch-t13", "so I cannot give one yet.", line, "\n\n"), "cnv")
    assert "the unit conversion the prose states:" in bad[0][3] and "rule prose-conversion" in bad[0][3]


@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³, that is 0.0550 dm³.", "The mixture is 55.0 cm³ (0.0550 dm³).", "The mixture is 55.0 cm³, or 0.0550 dm³.",
                                  "The mixture is 55.0 cm³, i.e. 0.0550 L.", "The mixture is 55.0 cm³, or about 0.055 dm³.", "At 30.0 °C (303.2 K) the time is 33.1 s."])
def test_a_correct_conversion_the_prose_states_holds(line):
    c, f = new("ch-t13", after("ch-t13", "so I cannot give one yet.", line, "\n\n"))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "cnv" and "rule prose-conversion" in x[3]], c


@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³ or 0.0550 dm³.", "It was heated from 20.0 °C to 60.0 °C, that is 40.0 K.", "Use a 10 Ω or 1 kΩ resistor."])
def test_two_values_that_may_be_alternatives_or_a_range_are_not_read_as_a_conversion(line):
    c, f = new("ch-t13", after("ch-t13", "so I cannot give one yet.", line, "\n\n"))
    assert not [x for x in c if "rule prose-conversion" in x[3]] and not failing(c), c


# ============================================================================================ rules rounding-cue and same-place
@pytest.mark.parametrize("line", ["To 3 s.f., P = 16.5 W.", "P = 17 W to 2 s.f.", "To 2 s.f., P = 17 W.", "To 3 s.f., the power is 16.5 W.",
                                  "To the nearest watt, P = 17 W."])
def test_a_restatement_with_a_stated_rounding_that_contradicts_the_result_fails(line):
    """The tester's 'To 3 s.f., P = 16.5 W.' (no check before), and the prose twin that held before by adding the two half-widths:
    16.5 is rounded to the place 16.4 is written to, so it must equal it (rule same-place)."""
    bad = named("ph-t13", after("ph-t13", PH_D, line), "res")
    assert "the restated result:" in bad[0][3]


@pytest.mark.parametrize("line", ["To 3 s.f., P = 16.4 W.", "To 2 s.f., P = 16 W.", "P = 16 W to 2 s.f.", "Rounded to 3 s.f., P = 16.4 W.", "To 1 d.p., P = 16.4 W.",
                                  "To the nearest watt, P = 16 W.", "To 3 s.f., the power is 16.4 W."])
def test_a_restatement_with_a_stated_rounding_that_agrees_holds(line):
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "res"], c


def test_same_place_needs_a_stated_rounding():
    """Without a rounding the prose states, R8 is unchanged: '60.5%' restates '60.4%' within h(S) + h(S′), as D31 states it."""
    chain60 = "D = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4%\n"
    plain, _f = decide(chain60 + "Therefore the decrease is 60.5%.", None, "biology")
    stated, _f = decide(chain60 + "To 3 s.f., the decrease is 60.5%.", None, "biology")
    assert [x[1] for x in plain if x[0] == "res"] == ["ENTAILED"] and "rule same-place" not in plain[-1][3]
    assert [x[1] for x in stated if x[0] == "res"] == ["COUNTEREXAMPLE"] and any("rule same-place" in x[3] for x in stated)


# ============================================================================================ rule processed-data and the per cent reading
PB_D = "A measured rate would be about 120"


@pytest.mark.parametrize("line", ["2% of 1620 is 0.02 × 1620 = 32.4 counts min⁻¹.", "The uncertainty in 1620 is 0.02 × 1620 = 32.4 counts min⁻¹.",
                                  "The uncertainty is 1620 × 2% = 32.4 counts min⁻¹.", "The ratio 1620/820 = 1.98 is about 2.",
                                  "The background is 20/1620 = 0.012 of the first reading.", "The fraction left is (1620 − 20)/1620 = 0.988."])
def test_a_percentage_or_a_ratio_of_the_raw_cell_is_not_read_as_its_processed_value(line):
    """The tester's ph-p7b part (d) plant and its class: the line takes the measured value on purpose (it had been set against the
    corrected 1600: INT-SUBJ-004 by rule processed-data; '1620 × 2% = 32.4 counts min⁻¹' also a false INT-SUBJ-001)."""
    c, f = new("ph-p7b", before("ph-p7b", PB_D, line, "\n"))
    assert not failing(c) and not warnings(f), (failing(c), f)


@pytest.mark.parametrize("line", ["C = 1620 counts min⁻¹ × (1/2)⁴ = 101 counts min⁻¹.", "C = 1620 ÷ 16 = 101 counts min⁻¹.", "C = 1620 counts min⁻¹ × 0.0625 = 101 counts min⁻¹."])
def test_the_raw_cell_taken_for_the_corrected_value_is_still_named(line):
    bad = named("ph-p7b", before("ph-p7b", PB_D, line, "\n"), "giv", "warning")
    assert "rule processed-data" in bad[0][3]


@pytest.mark.parametrize("text,status", [("u = 1620 × 2% = 32.4 counts min⁻¹", "ENTAILED"), ("u = 2% × 1620 = 32.4 counts min⁻¹", "ENTAILED"),
                                         ("u = 1620 × 2% = 33.4 counts min⁻¹", "COUNTEREXAMPLE"), ("u = 1620 × 2% = 32.4", "ENTAILED")])
def test_a_per_cent_taken_of_a_number_is_read_as_its_fraction(text, status):
    checks, _f = decide(text, None, "physics")
    assert [x[1] for x in checks if x[0] == "eq"] == [status], checks
    if "counts" in text:
        assert "as written, per cent as a fraction" in checks[0][3]


def test_a_percentage_a_ratio_makes_keeps_its_two_readings():
    checks, _f = decide("Percentage yield = 4.5 g / 6.0 g × 100 = 75%.", None, "chemistry")
    assert [x[1] for x in checks] == ["ENTAILED"] and "per cent as a fraction" not in checks[0][3]


# ============================================================================================ the recorded answers
@pytest.mark.parametrize("tid", sorted(PROFILE))
def test_no_recorded_round_7_answer_gets_a_reading_of_this_repair(tid):
    """On every recorded STEM answer the new readings plan nothing and change nothing: no check of rules bound-relation, part-value,
    prose-conversion or same-place, and no failing check."""
    checks, findings = task(tid, SPEC[tid]["response_text"])
    for rule in ("rule bound-relation", "rule part-value", "rule prose-conversion", "rule same-place", "per cent as a fraction",
                 # the third pass over the classes
                 "rule rearranged-formula", "the prose restates right after the value it states"):
        assert not [x for x in checks if rule in x[3]], (tid, rule)
    assert not [f for f in findings if "a ratio set against a number" in f[2]], tid


# ============================================================================================ the classes, closed whole
# Found closing the four problems: the same causes in other shapes of their classes, each fixed at the same cause with its control.

#: rule rearranged-formula: a rearrangement need not be solved for a lone symbol ('V² = P × R', 'I × r = ε − V')
NON_LONE = [
    ("P = V²/R\n", "P = V²/R\nV² = P × R\n", "'V² = P × R'"),
    ("P = V²/R\n", "P = V²/R\nP × R = V²\n", "'P × R = V²'"),
    ("P = V²/R\n", "P = V²/R\nV²/P = R\n", "'V²/P = R'"),
    ("P = V²/R\n", "P = V²/R\nV² = PR\n", "'V² = PR'"),
    ("V = ε − Ir\n", "V = ε − Ir\nI × r = ε − V\n", "'I × r = ε − V'"),
    ("V = ε − Ir\n", "V = ε − Ir\nε − V = Ir\n", "'ε − V = Ir'"),
    ("ε = I(R + r), so I = ε/(R + r)\n", "ε = I(R + r), so I = ε/(R + r)\nR + r = ε/I\n", "'R + r = ε/I'"),
]


@pytest.mark.parametrize("old,new_text,step", NON_LONE)
def test_a_rearrangement_with_no_lone_symbol_never_makes_the_formula_s_evaluation_a_step(old, new_text, step):
    """'V² = P × R' after 'P = V²/R', then 'P = (9.93 V)² / 6.0 Ω': the rearrangement is a step that holds, and the evaluation is the
    formula's substitution (it had failed as a step from the rearrangement, R and V pinned to other parts' values)."""
    c, f = new("ph-t13", replaced("ph-t13", old, new_text))
    assert not failing(c) and not warnings(f), (failing(c), f)
    steps = [x for x in c if x[0] == "alg"]
    assert [x for x in steps if f"the algebraic step: {step}" in x[3]] and all(holds(x) for x in steps), c


def test_a_slip_after_a_rearrangement_with_no_lone_symbol_still_fails():
    slip = replaced("ph-t13", "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nV² = PR\nP = (9.39 V)² / 6.0 Ω = 16.4 W")
    c, _f = new("ph-t13", slip)
    assert {"sub", "eq"} <= {x[0] for x in failing(c)} and not [x for x in failing(c) if x[0] == "alg"], failing(c)


#: rule part-value: the chain's quantity need not be its lone head, and the reused symbol's value may be a result its part computes
PART_D = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"


@pytest.mark.parametrize("text", [
    after("ph-t13", PH_D, "As a check, I²R = (1.655 A)² × 6.0 Ω = 16.4 W."),
    replaced("ph-t13", PART_D, "The power is 9.93² ÷ 6.0 = 16.4 W.\nAs a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W."),
    replaced("ph-t13", PART_D, "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),
    replaced("ph-t13", PART_D, "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A, so P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),
])
def test_a_reused_symbol_matches_a_result_its_part_gives_with_or_without_a_head(text):
    c, f = new("ph-t13", text)
    assert not failing(c) and not warnings(f), (failing(c), f)
    assert [x for x in c if x[0] == "sub" and "rule part-value" in x[3]], c


@pytest.mark.parametrize("text", [
    after("ph-t13", PH_D, "As a check, I²R = (1.565 A)² × 6.0 Ω = 14.7 W."),
    replaced("ph-t13", PART_D, "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.\nP = I²R = (1.565 A)² × 6.0 Ω = 14.7 W, so 15 W"),
])
def test_a_reused_symbol_whose_value_no_result_of_its_part_gives_still_fails(text):
    bad = named("ph-t13", text, "sub")
    assert "rule part-value" in bad[0][3]


def test_a_reused_symbol_whose_value_matches_a_binding_reads_nothing_new():
    """4.1 A matches I's own binding: the substitution holds as before, with no part-value reading in its statement."""
    c, _f = new("ph-t13", after("ph-t13", PH_D, "As a check, P = I²R = (4.1 A)² × 6.0 Ω = 101 W."))
    subs = [x for x in c if x[0] == "sub"]
    assert subs and all(holds(x) for x in subs) and not [x for x in subs if "rule part-value" in x[3]], subs


# rule adjacent-restatement: a bare number restates a chain of its own statement or of the statement right before it
@pytest.mark.parametrize("line", ["With n = 1000 items, so 10 passes are needed.", "As n = 1000, the search therefore takes 10 passes.",
                                  "Also 2^10 = 1024 ≥ 1000, so 10 passes suffice."])
def test_a_count_after_a_condition_or_an_order_restates_no_older_chain(line):
    """Each had been set against '1,000 ÷ 2^10 = 0.98' three statements before (INT-SUBJ-001 naming its genuine claim c8.3)."""
    c, f = new("cs-t13", before("cs-t13", "Next step: trace", line))
    assert not failing(c) and not warnings(f) and not [x for x in c if x[0] == "res"], c


def test_a_bare_restatement_of_the_statement_right_before_is_still_checked():
    ok, _f = new("cs-t13", before("cs-t13", "Next step: trace", "Also 2^10 = 1024.\n\nSo the bound is 1024."))
    bad, _f = new("cs-t13", before("cs-t13", "Next step: trace", "Also 2^10 = 1024.\n\nSo the bound is 1025."))
    assert [x[1] for x in ok if x[0] == "res"] == ["ENTAILED"] and [x[1] for x in bad if x[0] == "res"] == ["COUNTEREXAMPLE"]


def test_a_value_with_a_unit_still_restates_the_last_chain_of_its_part():
    """The rule bounds bare numbers only: a power restated two statements after its chain is set against it, its dimension guarding the
    pairing."""
    bad = named("ph-t13", after("ph-t13", PH_D, "The resistor gets warm.\nThe power is therefore 16.6 W."), "res")
    assert "the restated result: '16.6 W'" in bad[0][3]


# rule bound-relation: an equation in a symbol the part reuses, or that it solves in prose, is no claim; an unknown is named
@pytest.mark.parametrize("line", ["The power is 16.4 W = I² × 6.0 Ω.", "The power in it is I² × 6.0 Ω = 16.4 W.",
                                  "The power is 16.4 W = I² × 6.0 Ω, giving a current of 1.65 A."])
def test_an_equation_for_a_reused_symbol_about_its_part_s_result_stays_unchecked(line):
    """I is bound only in part (b); in part (d) the line is an equation for the current in the 6.0 Ω resistor (its numeric side is the
    part's own P = 16.4 W, or the prose solves it): checked against part (b)'s 4.1 A it had failed (INT-SUBJ-001)."""
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and not [x for x in c if "rule bound-relation" in x[3]], c


def test_an_equation_its_prose_solves_stays_unchecked_on_the_part_s_first_line():
    c, f = new("ph-t13", replaced("ph-t13", PART_D, "The power in the resistor is 16.4 W = I² × 6.0 Ω, giving a current of 1.65 A."))
    assert not failing(c) and not warnings(f) and not [x for x in c if "rule bound-relation" in x[3]], c


@pytest.mark.parametrize("line", ["The power output of the battery is then 12 V × I = 60 W.", "The battery's power output is therefore 12 V × I = 60 W.",
                                  "The battery's power output is 12 V × I = 60 W, so the current is 4.1 A."])
def test_a_relation_given_as_a_quantity_s_value_after_a_cue_word_or_with_its_stated_value_restated_is_checked(line):
    bad = named("ph-t13", after("ph-t13", PH_D, line), "sub")
    assert "rule bound-relation" in bad[0][3]


def test_a_relation_given_as_a_quantity_s_value_in_a_symbol_with_no_value_is_named():
    """'The energy is 0.5 × k × 0.04 = 1.0 J.' is named ST-UNDEC-002, as 'E = 0.5 × k × 0.04 = 1.0 J' is (before: neither a check nor an
    ST code); solved for k in its statement, or written as a function applied ('C(12)'), it names nothing."""
    c, f = new("ph-t13", after("ph-t13", PH_D, "The energy is 0.5 × k × 0.04 = 1.0 J."))
    assert not c and [x[0] for x in f] == ["ST-UNDEC-002"] and "'k' has no stated value" in f[0][2], (c, f)
    for line in ("The energy is 0.5 × k × 0.04 = 1.0 J, so the spring constant is 50 N m⁻¹.", "The energy is 0.5 × k × 0.04 = 1.0 J, so k = 50 N m⁻¹."):
        c, f = new("ph-t13", after("ph-t13", PH_D, line))
        assert not failing(c) and not warnings(f), (line, c, f)
    it = CORPUS["mai-func-1"]
    checks, findings = decide(it["response_text"], it["question"], "mathematics_ai")
    # STEM repair 11 (rule function-value): 'C(12) = 40 + 2.5 × 12' is also set against the function C(x) the answer states, at 12, and holds
    assert [x[1] for x in checks] == ["ENTAILED", "ENTAILED"] and "the function's value at the written argument" in checks[0][3] \
        and not [x for x in findings if x[0] == "ST-UNDEC-002"], (checks, findings)


# rule prose-conversion: a bracket with 'or', and 'is', 'equals', 'is equal to' when the restated value ends its clause
CH_END = "so I cannot give one yet."


@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³ (or 0.550 dm³).", "The volume of 55.0 cm³ is 0.550 dm³.", "The volume, 55.0 cm³, is equal to 0.550 dm³.",
                                  "The volume of 55.0 cm³ equals 0.550 dm³."])
def test_a_wrong_conversion_the_prose_states_with_a_verb_or_a_bracketed_or_fails(line):
    bad = named("ch-t13", after("ch-t13", CH_END, line, "\n\n"), "cnv")
    assert "rule prose-conversion" in bad[0][3]


@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³ (or 0.0550 dm³).", "The volume of 55.0 cm³ is 0.0550 dm³.", "The flask holds 55.0 cm³ (about 0.06 dm³).",
                                  "The time of 33.1 s is 0.552 min."])
def test_a_correct_conversion_the_prose_states_with_a_verb_or_a_bracketed_or_holds(line):
    c, f = new("ch-t13", after("ch-t13", CH_END, line, "\n\n"))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "cnv" and "rule prose-conversion" in x[3]], c


@pytest.mark.parametrize("line", ["A length of 2.0 km is 500 m more than 1.5 km.", "The 50.0 cm³ portion is 0.0500 dm³ of the solution."])
def test_a_value_its_clause_goes_on_after_is_no_conversion(line):
    c, _f = new("ch-t13", after("ch-t13", CH_END, line, "\n\n"))
    assert not [x for x in c if "rule prose-conversion" in x[3]], c


# rule rounding-cue: a precision in brackets after the value, and a rounding before it whose 's.f.' ends with a full stop
@pytest.mark.parametrize("line", ["P = 16.5 W (3 s.f.)", "To 3 s.f. the power is 16.5 W.", "To 3 s.f. the power P = 16.5 W."])
def test_a_rounding_in_brackets_or_before_the_value_without_a_comma_is_read(line):
    bad = named("ph-t13", after("ph-t13", PH_D, line), "res")
    assert "the restated result: '16.5 W'" in bad[0][3]


@pytest.mark.parametrize("line", ["P = 16.4 W (3 s.f.)", "To 3 s.f. the power is 16.4 W.", "To 3 s.f. the power P = 16.4 W."])
def test_the_same_roundings_written_right_hold(line):
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "res"], c


# rule processed-data: a percentage taken as a division, a ratio to the raw cell, and a '±' per cent
@pytest.mark.parametrize("line", ["The uncertainty is 1620/50 = 32.4 counts min⁻¹.", "The fractional uncertainty is 32.4/1620 = 0.020.",
                                  "The uncertainty in 1620 is ±2% × 1620 = ±32.4 counts min⁻¹."])
def test_a_percentage_by_division_a_ratio_to_the_raw_cell_and_a_plus_minus_per_cent_are_not_read(line):
    c, f = new("ph-p7b", before("ph-p7b", PB_D, line, "\n"))
    assert not failing(c) and not warnings(f), (failing(c), f)


def test_a_plus_minus_per_cent_taken_of_a_number_is_read_as_its_fraction():
    checks, _f = decide("u = ±2% × 1620 = ±32.4 counts min⁻¹", None, "physics")
    bad, _f = decide("u = ±2% × 1620 = ±34.2 counts min⁻¹", None, "physics")
    assert [x[1] for x in checks if x[0] == "eq"] == ["ENTAILED"] and "per cent as a fraction" in checks[0][3]
    assert [x[1] for x in bad if x[0] == "eq"] == ["COUNTEREXAMPLE"]


# ============================================================================================ the classes, closed whole: a second pass
# Found measuring each class again on the repaired front end: further phrasings of the same causes, each fixed at the same cause, each
# with its clean control.

#: rule rearranged-formula: a rearrangement stated after 'Making R the subject', 'Solving for R' or 'Transposing' is a step from the
#: formula (it had been read as no step at all once the evaluation after it was no longer a step: a wrong rearrangement passed)
STEP_PHRASES = ["Making R the subject, ", "Make R the subject: ", "Solving for R, ", "Transposing, "]


@pytest.mark.parametrize("phrase", STEP_PHRASES)
def test_a_wrong_rearrangement_after_a_phrase_that_states_one_fails_as_a_step(phrase):
    bad = named("ph-t13", replaced("ph-t13", "P = V²/R\n", f"P = V²/R\n{phrase}R = P/V².\n"), "alg")
    assert "the algebraic step: 'R = P/V²'" in bad[0][3] and bad[0][1] == "COUNTEREXAMPLE"


@pytest.mark.parametrize("phrase", STEP_PHRASES)
def test_a_correct_rearrangement_after_a_phrase_that_states_one_holds_and_the_evaluation_after_it_stays_clean(phrase):
    c, f = new("ph-t13", replaced("ph-t13", "P = V²/R\n", f"P = V²/R\n{phrase}R = V²/P.\n"))
    assert not failing(c) and not warnings(f), (failing(c), f)
    assert [x for x in c if x[0] == "alg" and "the algebraic step: 'R = V²/P'" in x[3] and holds(x)], c


def test_a_rearrangement_after_any_words_before_the_formula_s_evaluation_is_a_step_from_the_formula():
    """Rewritten in the third pass (it asserted that no step is read after 'Subject to the same supply,' or 'Equivalently,'): the
    staged tree before this repair caught both wrong rearrangements, through the evaluation after them read as a step from them, so
    asserting no step pinned a lost check. The rearrangement is now the step it is, from the formula, whatever words state it: wrong,
    it fails, naming rule rearranged-formula; right, it holds, and the evaluation after it stays the formula's substitution."""
    for line in ("Subject to the same supply, R = P/V².", "Equivalently, R = P/V²."):
        bad = named("ph-t13", replaced("ph-t13", "P = V²/R\n", f"P = V²/R\n{line}\n"), "alg")
        assert "the algebraic step: 'R = P/V²'" in bad[0][3] and "rule rearranged-formula" in bad[0][3] and bad[0][1] == "COUNTEREXAMPLE", bad
        c, f = new("ph-t13", replaced("ph-t13", "P = V²/R\n", f"P = V²/R\n{line.replace('P/V²', 'V²/P')}\n"))
        assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "alg" and "'R = V²/P'" in x[3] and holds(x)], (line, c)
        assert not [x for x in c if x[0] == "alg" and "'P = (9.93" in x[3]], c


#: rule bound-relation: the verbs 'equal' (the plural of 'equals'), 'is equal to' and 'is given by' give the run as the quantity's value too
@pytest.mark.parametrize("line", ["The lost volts equal 0.50 Ω × I = 3.0 V.", "The lost volts are equal to 0.50 Ω × I = 3.0 V.",
                                  "The battery's power output is given by 12 V × I = 60 W."])
def test_a_relation_given_as_a_quantity_s_value_after_equal_or_given_by_is_checked(line):
    bad = named("ph-t13", after("ph-t13", PH_D, line), "sub")
    assert "rule bound-relation" in bad[0][3], bad


@pytest.mark.parametrize("line", ["The lost volts equal 0.50 Ω × I = 2.07 V.", "The lost volts are equal to 0.50 Ω × I = 2.07 V.",
                                  "The battery's power output is given by 12 V × I = 49.7 W."])
def test_the_same_relations_after_equal_or_given_by_written_correctly_hold(line):
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "sub" and "rule bound-relation" in x[3]], c


#: rule prose-conversion: 'which equals', a semicolon or a dash before 'that is', ', about', 'converts to'
@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³, which equals 0.550 dm³.", "The mixture is 55.0 cm³; that is 0.550 dm³.",
                                  "The mixture is 55.0 cm³ — that is, 0.550 dm³.", "The mixture is 55.0 cm³, about 0.6 dm³.",
                                  "The volume, 55.0 cm³, converts to 0.550 dm³.", "The mixture is 55.0 cm³, equivalent to 0.550 dm³."])
def test_a_wrong_conversion_after_further_connectives_fails(line):
    bad = named("ch-t13", after("ch-t13", CH_END, line, "\n\n"), "cnv")
    assert "rule prose-conversion" in bad[0][3]


@pytest.mark.parametrize("line", ["The mixture is 55.0 cm³, which equals 0.0550 dm³.", "The mixture is 55.0 cm³; that is 0.0550 dm³.",
                                  "The mixture is 55.0 cm³ — that is, 0.0550 dm³.", "The mixture is 55.0 cm³, about 0.06 dm³.",
                                  "The volume, 55.0 cm³, converts to 0.0550 dm³.", "The mixture is 55.0 cm³, equivalent to 0.0550 dm³."])
def test_a_correct_conversion_after_further_connectives_holds(line):
    c, f = new("ch-t13", after("ch-t13", CH_END, line, "\n\n"))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "cnv" and "rule prose-conversion" in x[3]], c


def test_a_value_after_a_comma_and_about_that_its_clause_goes_on_after_is_no_conversion():
    c, _f = new("ch-t13", after("ch-t13", CH_END, "A length of 2.0 km, about 500 m more than the other, was walked.", "\n\n"))
    assert not [x for x in c if "rule prose-conversion" in x[3]], c


#: rule processed-data: the cell processed inside the line, a share of it in any arithmetic form, and the bounds of the measured value
@pytest.mark.parametrize("line", ["C = (1620 − 20) × (1/2)⁴ = 100 counts min⁻¹.", "C = (1620 − 20) counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹.",
                                  "The uncertainty is 1620 × 2 ÷ 100 = 32.4 counts min⁻¹.", "The uncertainty is 1620 ÷ 100 × 2 = 32.4 counts min⁻¹.",
                                  "The upper bound is 1620 + 32.4 = 1652.4 counts min⁻¹.", "The upper bound is 1620 × 1.02 = 1652.4 counts min⁻¹.",
                                  "The upper bound is 1620 + 0.02 × 1620 = 1652.4 counts min⁻¹.", "The lower bound is 1620 × 0.98 = 1587.6 counts min⁻¹."])
def test_the_cell_processed_in_the_line_a_share_of_it_and_its_bounds_are_not_read_as_its_processed_value(line):
    """Each takes the measured value on purpose, or processes it in the line itself: before, each was set against the corrected 1600
    (a false INT-SUBJ-004 by rule processed-data)."""
    c, f = new("ph-p7b", before("ph-p7b", PB_D, line, "\n"))
    assert not failing(c) and not warnings(f), (failing(c), f)


@pytest.mark.parametrize("line", ["C = 1620 × (1/2)⁴ = 101 counts min⁻¹.", "C = 1620 × 0.0625 = 101 counts min⁻¹.", "C = 1620 / 16 = 101 counts min⁻¹.",
                                  "C = (1620 − 10) × (1/2)⁴ = 101 counts min⁻¹.", "C = 1620 × 1.5 = 2430 counts min⁻¹."])
def test_the_raw_cell_for_the_corrected_value_in_any_of_these_forms_is_still_named(line):
    """No stated percentage gives these coefficients (1/16, 1.5) and '1620 − 10' is not the processed 1600: the raw cell taken for the
    corrected value is still named, INT-SUBJ-004."""
    bad = named("ph-p7b", before("ph-p7b", PB_D, line, "\n"), "giv", "warning")
    assert "rule processed-data" in bad[0][3]


# ============================================================================================ the classes, closed whole: a third pass
# Found measuring each class again on the resumed tree: a wrong rearrangement in words no step reads, which the staged tree before
# this repair caught through the evaluation after it (rule rearranged-formula had left it with no check), a reused symbol shown by its
# part's prose, another part's value of the chain's quantity or a computation in the line, a prose relation that is its part's
# answer, a value after 'so' that follows its own statement's value or is a part of it, a rounding of a value the prose states,
# measured values taken on purpose, a ratio set against a number, a conversion to a unit the prose names, and a symbol written as
# applied that no definition makes a function. Each is fixed at the same cause as its class, with its clean control.

#: rule rearranged-formula: the rearrangement before the formula's evaluation is a step from the formula, whatever words state it
RETRO = [
    ("P = V²/R\n", "P = V²/R\nThis rearranges to {}.\n", "R = P/V²", "R = V²/P"),
    ("P = V²/R\n", "P = V²/R, i.e. {}\n", "R = P/V²", "R = V²/P"),
    ("P = V²/R\n", "P = V²/R\nor {}\n", "R = P/V²", "R = V²/P"),
    ("P = V²/R\n", "P = V²/R\nRe-arranged: {}.\n", "R = P/V²", "R = V²/P"),
    ("P = V²/R\n", "P = V²/R\nAlternatively, {}.\n", "R = P/V²", "R = V²/P"),
    ("P = V²/R\n", "P = V²/R\nThat is, {}.\n", "V² = P/R", "V² = PR"),
    ("V = ε − Ir\nV = 12 V", "V = ε − Ir\nThis rearranges to {}.\nV = 12 V", "I = (ε + V)/r", "I = (ε − V)/r"),
]


@pytest.mark.parametrize("old,template,wrong,right", RETRO)
def test_a_wrong_rearrangement_before_the_formula_s_evaluation_fails_as_a_step_from_the_formula(old, template, wrong, right):
    """The staged tree before this repair failed each wrong form through the evaluation after it (read as a step from it); after rule
    rearranged-formula read that evaluation as the formula's substitution, nothing checked these: each is a step from the formula
    now, the right form holding with no finding."""
    bad = named("ph-t13", replaced("ph-t13", old, template.format(wrong)), "alg")
    assert f"the algebraic step: '{wrong}'" in bad[0][3] and "rule rearranged-formula" in bad[0][3] and bad[0][1] == "COUNTEREXAMPLE", bad
    c, f = new("ph-t13", replaced("ph-t13", old, template.format(right)))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "alg" and f"'{right}'" in x[3] and holds(x)], (failing(c), f, c)


def test_a_relation_with_the_variables_swapped_for_the_inverse_is_no_step():
    """'Swap x and y: x = 2y + 1.' after 'y = 2x + 1' is the inverse's equation (it had failed as a step: INT-SUBJ-001, on the staged
    tree before this repair too); the step after it is still checked."""
    request = "f(x) = 2x + 1. Find the inverse function."
    for text in ("y = 2x + 1\nSwap x and y: x = 2y + 1.\nSo y = (x − 1)/2.", "y = 2x + 1\nFor the inverse, x = 2y + 1, so y = (x − 1)/2.",
                 "y = 2x + 1\nSwapping x and y gives x = 2y + 1.\ny = 2 × 3 + 1 = 7"):
        checks, findings = decide(text, request, "mathematics_aa")
        assert not failing(checks) and not warnings(findings), (text, checks, findings)
        assert not [x for x in checks if x[0] == "alg" and "'x = 2y + 1'" in x[3]], checks
    bad, _f = decide("y = 2x + 1\nSwap x and y: x = 2y + 1.\nSo y = (x + 1)/2.", request, "mathematics_aa")
    assert [x[1] for x in bad if x[0] == "alg"] == ["COUNTEREXAMPLE"]
    wrong, _f = decide("y = 2x + 1\nSo x = (y + 1)/2.", request, "mathematics_aa")
    assert [x[1] for x in wrong if x[0] == "alg"] == ["COUNTEREXAMPLE"]  # a rearrangement with no swap is still a step


#: rule part-value: the part's prose names another quantity for the value, the line re-derives another part's value of its head, or
#: the line computes the reused symbol's value itself
@pytest.mark.parametrize("text", [
    replaced("ph-t13", PART_D, "The current in the 6.0 Ω resistor is 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),
    replaced("ph-t13", PART_D, "The 6.0 Ω resistor carries 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"),
    replaced("ph-t13", PART_D, "V = IR = 1.655 A × 6.0 Ω = 9.93 V\nP = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"),
])
def test_a_reused_symbol_shown_by_its_part_s_prose_or_another_part_s_value_of_its_head_holds(text):
    """Each had failed against part (b)'s I = 4.1 A (INT-SUBJ-001) on correct working."""
    c, f = new("ph-t13", text)
    assert not failing(c) and not warnings(f), (failing(c), f)
    assert [x for x in c if x[0] == "sub" and "rule part-value" in x[3] and holds(x)], c


@pytest.mark.parametrize("text", [
    replaced("ph-t13", PART_D, "The current in the 6.0 Ω resistor is 1.655 A.\nP = I²R = (1.565 A)² × 6.0 Ω = 14.7 W, so 15 W"),
    replaced("ph-t13", PART_D, "V = IR = 1.565 A × 6.0 Ω = 9.39 V\nP = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"),
])
def test_a_reused_symbol_whose_value_neither_its_part_nor_its_head_gives_still_fails(text):
    bad = named("ph-t13", text, "sub")
    assert "rule part-value" in bad[0][3]


def test_a_value_its_part_names_only_by_the_stated_quantity_s_words_is_not_taken():
    """'The current in it is 1.655 A.' names nothing but a current, which part (b) states (its question: the current in the battery):
    it may restate that quantity, so the substitution is still set against it and fails, as D31 states; 'the terminal potential
    difference, 9.93 V' is never taken for part (c)'s V either (STEM repair 1's related-statements test)."""
    bad = named("ph-t13", replaced("ph-t13", PART_D, "The current in it is 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"), "sub")
    assert "rule part-value" not in bad[0][3]


def test_a_reused_symbol_written_as_a_computation_in_the_line_is_read_from_it():
    """'P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω' computes the current in the 6.0 Ω resistor in the line: it is read for I there, not set
    against part (b)'s 4.1 A (INT-SUBJ-001 before); the line's arithmetic is still checked, and a single value written for I is still
    set against part (b)'s."""
    c, f = new("ph-t13", replaced("ph-t13", PART_D, "P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 16.4 W, so 16 W"))
    assert not failing(c) and not warnings(f) and [x for x in c if x[0] == "eq" and holds(x)] and not [x for x in c if x[0] == "sub"], c
    named("ph-t13", replaced("ph-t13", PART_D, "P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 20.4 W, so 20 W"), "eq")
    bad = named("ph-t13", replaced("ph-t13", "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (4.41 A × 0.50 Ω) = 9.8 V"), "sub")
    assert "the substitution: 'V = 12 V − (4.41 A × 0.50 Ω)'" in bad[0][3]


#: rule bound-relation: a prose relation that gives its part's asked quantity, in a symbol stated only in other parts, is its answer
def test_a_relation_that_gives_its_part_s_asked_quantity_in_a_reused_symbol_stays_unread():
    """'The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W.' as part (d)'s answer (its question: the power dissipated in the 6.0
    ohm resistor) is an equation for the current there: checked under part (b)'s I it had failed (INT-SUBJ-001); a relation that
    names another quantity than the part asks for is still checked."""
    c, f = new("ph-t13", replaced("ph-t13", PART_D, "The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W."))
    assert not failing(c) and not warnings(f) and not [x for x in c if "rule bound-relation" in x[3]], (c, f)
    bad = named("ph-t13", replaced("ph-t13", PART_D, "The battery's power output is 12 V × I = 60 W."), "sub")
    assert "rule bound-relation" in bad[0][3]


#: rule adjacent-restatement: a value after 'so' that follows its own statement's other value, or that is a part of the quantity
@pytest.mark.parametrize("tid,anchor,line", [
    ("ph-p7b", PB_D, "The measured rate at t = 0 h is 1620 counts min⁻¹, so the corrected rate is 1600 counts min⁻¹.\n"),
    ("ph-t13", PH_D, "\nSo 4.4 W of it is lost as heat in the wires."),
])
def test_a_value_after_so_that_follows_its_own_statement_s_value_or_is_a_part_of_it_restates_no_chain(tid, anchor, line):
    """Each had been set against the last chain of its part (INT-SUBJ-001: '1600' against '= 100 counts min⁻¹', '4.4 W' against
    '= 16.4 W')."""
    text = before(tid, anchor, line, "") if tid == "ph-p7b" else after(tid, anchor, line.lstrip("\n"))
    c, f = new(tid, text)
    assert not failing(c) and not warnings(f) and not [x for x in c if x[0] == "res"], (c, f)


@pytest.mark.parametrize("line", ["The power is 16.4 W, so 18 W to 2 s.f.", "So the resistor dissipates 18 W of power.", "The resistor therefore dissipates 18 W."])
def test_a_restatement_after_its_own_statement_s_matching_value_or_with_a_tail_is_still_checked(line):
    bad = named("ph-t13", after("ph-t13", PH_D, line), "res")
    assert "the restated result: '18 W'" in bad[0][3]


#: rule rounding-cue: a value the prose restates right after a value it states, with a stated rounding
@pytest.mark.parametrize("line,status", [("The power is 16.4 W, so 16 W to 2 s.f.", "ENTAILED"), ("The power is 16.4 W, so 17 W to 2 s.f.", "COUNTEREXAMPLE"),
                                         ("The power is 16.4 W, which is 16 W to two significant figures.", "ENTAILED"),
                                         ("The power is 16.4 W, which is 17 W to two significant figures.", "COUNTEREXAMPLE"),
                                         ("The power is 16.4 W, so 16.5 W to 3 s.f.", "COUNTEREXAMPLE")])
def test_a_value_the_prose_restates_with_a_stated_rounding_is_checked(line, status):
    """Before, nothing was read: 'The power is 16.4 W, so 17 W to 2 s.f.' passed."""
    c, _f = new("ph-t13", after("ph-t13", PH_D, line))
    res = [x for x in c if x[0] == "res" and "against the value the prose states right before it" in x[3] and "(rule rounding-cue)" in x[3]]
    assert [x[1] for x in res] == [status], c


def test_a_value_the_prose_restates_with_no_stated_rounding_is_not_read():
    c, f = new("ph-t13", after("ph-t13", PH_D, "The power is 16.4 W, so about 16 W."))
    assert not [x for x in c if x[0] == "res"] and not warnings(f), c


#: rule processed-data: a ratio of the raw cell to its processed value, and a line that names the measured quantity itself
@pytest.mark.parametrize("line", ["The ratio 1620/1600 = 1.0125.", "The measured rate fell by 1620 − 820 = 800 counts min⁻¹ in 8 h.",
                                  "The mean of the first two measured rates is (1620 + 1151)/2 = 1385.5 counts min⁻¹."])
def test_a_ratio_to_the_processed_value_or_a_line_naming_the_measured_quantity_is_not_read(line):
    """Each had been set against the corrected 1600 (a false INT-SUBJ-004 by rule processed-data)."""
    c, f = new("ph-p7b", before("ph-p7b", PB_D, line, "\n"))
    assert not failing(c) and not warnings(f), (failing(c), f)


@pytest.mark.parametrize("line", ["The corrected rate is 1620 × (1/2)⁴ = 101 counts min⁻¹.",
                                  "From the measured 1620, the corrected rate is 1620 × (1/2)⁴ = 101 counts min⁻¹."])
def test_the_raw_cell_taken_for_the_corrected_value_beside_the_word_measured_is_still_named(line):
    bad = named("ph-p7b", before("ph-p7b", PB_D, line, "\n"), "giv", "warning")
    assert "rule processed-data" in bad[0][3]


#: D31: what the branch reads and cannot check, it names: a ratio set against a number
@pytest.mark.parametrize("line", ["The ratio of the resistances is 4.0 : 6.0 = 0.67.", "The ratio of the resistances is 4.0 : 6.0 = 0.76."])
def test_a_ratio_set_against_a_number_is_named_unchecked(line):
    """It had neither a check nor an ST code."""
    c, f = new("ph-t13", after("ph-t13", PH_D, line))
    assert not c and [x[0] for x in f] == ["ST-UNDEC-001"] and "a ratio set against a number" in f[0][2], (c, f)


def test_a_ratio_given_a_name_or_set_against_a_ratio_is_read_as_before():
    checks, findings = decide("Mole ratio = 1 : 2", None, "chemistry")
    assert not checks and not [f for f in findings if f[0].startswith("ST-")], (checks, findings)
    c, _f = new("ph-t13", after("ph-t13", PH_D, "The ratio of the currents is 2 : 3 = 4 : 5."))
    assert [x[1] for x in c if x[0] == "eq"] == ["COUNTEREXAMPLE"]


#: rule prose-conversion: a value restated in a unit the prose names ('to dm³ gives', 'in dm³ is', 'which in dm³ is')
@pytest.mark.parametrize("line,status", [("Converting 55.0 cm³ to dm³ gives 0.550 dm³.", "COUNTEREXAMPLE"),
                                         ("Converting 55.0 cm³ to dm³ gives 0.0550 dm³.", "ENTAILED"),
                                         ("The mixture is 55.0 cm³, which in dm³ is 0.550 dm³.", "COUNTEREXAMPLE"),
                                         ("The mixture is 55.0 cm³, which in dm³ is 0.0550 dm³.", "ENTAILED"),
                                         ("The volume of 55.0 cm³ in dm³ is 0.550 dm³.", "COUNTEREXAMPLE"),
                                         ("The volume of 55.0 cm³ in dm³ is 0.0550 dm³.", "ENTAILED")])
def test_a_conversion_to_a_unit_the_prose_names_is_checked(line, status):
    c, _f = new("ch-t13", after("ch-t13", CH_END, line, "\n\n"))
    assert [x[1] for x in c if x[0] == "cnv" and "rule prose-conversion" in x[3]] == [status], c


@pytest.mark.parametrize("line", ["The volume of 55.0 cm³ in a flask of 0.250 dm³ is enough.", "Adding 5.0 cm³ to 0.050 dm³ gives 0.055 dm³."])
def test_two_values_with_other_words_or_another_unit_named_between_them_are_no_conversion(line):
    c, _f = new("ch-t13", after("ch-t13", CH_END, line, "\n\n"))
    assert not [x for x in c if "rule prose-conversion" in x[3]], c


#: rule bound-relation: a symbol written as applied is a function only where the answer or the request defines it as one
def test_a_symbol_written_as_applied_with_no_definition_is_named_unchecked():
    """'The energy is ½k(0.20)² = 1.0 J.' had neither a check nor an ST code (k read as a function applied), while 'E = ½k(0.20)² = 1.0
    J' was named ST-UNDEC-002; 'C(12)' after 'C(x) = 40 + 2.5x' is still the function applied."""
    for line in ("The energy is ½k(0.20)² = 1.0 J.", "E = ½k(0.20)² = 1.0 J"):
        c, f = new("ph-t13", after("ph-t13", PH_D, line))
        assert not c and [x[0] for x in f] == ["ST-UNDEC-002"], (line, c, f)
    it = CORPUS["mai-func-1"]
    checks, findings = decide(it["response_text"], it["question"], "mathematics_ai")
    # STEM repair 11 (rule function-value): 'C(12) = 40 + 2.5 × 12' is also set against the function C(x) the answer states, at 12, and holds
    assert [x[1] for x in checks] == ["ENTAILED", "ENTAILED"] and "the function's value at the written argument" in checks[0][3] \
        and not [x for x in findings if x[0] == "ST-UNDEC-002"], (checks, findings)
