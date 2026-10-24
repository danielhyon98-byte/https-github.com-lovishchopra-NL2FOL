"""STEM repair 10 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 41).

* the STEM probes of repair 10 (the tenth independent test's plants, each class with its clean control, and the shapes of the same classes
  found closing them): rule prose-conversion (a conversion followed by another statement), rule table-operands (a line in the column its
  own words name), rule row-value (a value at a row in any order of its clause, at a numbered row, in a column told apart by its number;
  a difference, a ratio, a processed or another quantity at a row never failed), rule table-data (the value's own statement chooses the
  column), rule named-component, rule condition-result, rule prose-base, rule definite-integral (signed and plain-text limits too), rule
  operand-precision for the request's exact data and rule ellipsis-rounding (a plain '…' too);
* the STEM receipt cases T23bb to T23bi, each on the probe that plants its fault;
* the pack beside the code: D31's new readings, the paragraph after D32's table, I97, the master prompt and the mistakes rows, every new
  statement executed against the STEM front end.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stem_probes as SP  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer.pack import installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402
from .test_stem_repair8 import _failing, _holds, _with  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-t13": "mathematics_aa", "mai-t13": "mathematics_ai", "ess-t13": "ess", "ch-t13": "chemistry",
           "cs-t13": "computer_science"}
#: the recorded working the pack's statements extend
ES_W = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
PB_E = "Both effects make the count rate smaller than the activity."
CH_R = "Two reminders."
MA_END = "Marks shown are a provisional allocation."
MI_END = "Next step: rework (a)"
PH_E = "from 9.9 V to 10.7 V."
CS_END = "Next step: trace"


def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _new(tid: str, text: str) -> list:
    """The checks (kind, status, statement) ``text`` has beyond the recorded answer's."""
    def key(c):
        return (c[0], c[1], c[2].split(" [claims")[0])
    checks, _f = _task(tid, text)
    base = [key(c) for c in _task(tid, R7[tid]["response_text"])[0]]
    out = []
    for c in checks:
        if key(c) in base:
            base.remove(key(c))
        else:
            out.append(c)
    return out


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule})" in c[2] or f"rule {rule};" in c[2] or f"rule {rule}," in c[2]]


# ============================================================================================ the probes and the tamper cases
#: each plant of the tenth independent test, and of the shapes of its classes found closing them, with the code that must name it
REPAIR10_PROBES = {
    # rule prose-conversion: a conversion followed by another statement
    "units-prose-conversion-followed": ("INT-SUBJ-001",), "units-prose-conversion-equal-followed": ("INT-SUBJ-001",),
    "units-prose-conversion-gives-followed": ("INT-SUBJ-001",), "units-prose-conversion-about-followed": ("INT-SUBJ-001",),
    "units-prose-conversion-same-line": ("INT-SUBJ-001",),
    # rule table-operands: the line's own column
    "wrong_given-line-column": ("INT-SUBJ-004",), "wrong_given-line-column-fall": ("INT-SUBJ-004",), "wrong_given-line-column-decrease": ("INT-SUBJ-004",),
    # rule row-value: the tester's shapes, the clause reading, numbered rows and columns told apart by a number
    "givens-row-has-value": ("INT-SUBJ-004",), "givens-row-label-run": ("INT-SUBJ-004",), "givens-row-number-verb": ("INT-SUBJ-004",),
    "givens-row-value-column-at": ("INT-SUBJ-004",), "givens-row-column-of": ("INT-SUBJ-004",), "givens-row-has-quantity": ("INT-SUBJ-004",),
    "givens-row-coordinated": ("INT-SUBJ-004",), "givens-row-ellipsis": ("INT-SUBJ-004",), "givens-row-clause-after": ("INT-SUBJ-004",),
    "givens-row-clause-no-comma": ("INT-SUBJ-004",), "givens-row-clause-apposition": ("INT-SUBJ-004",), "givens-row-clause-adverb": ("INT-SUBJ-004",),
    "givens-row-clause-possessive": ("INT-SUBJ-004",), "givens-row-clause-of": ("INT-SUBJ-004",), "givens-row-numbered-of": ("INT-SUBJ-004",),
    "givens-row-numbered-label": ("INT-SUBJ-004",), "givens-row-numbered-clause": ("INT-SUBJ-004",), "givens-row-numbered-symbol": ("INT-SUBJ-004",),
    "givens-row-trial": ("INT-SUBJ-004",), "givens-row-trial-time": ("INT-SUBJ-004",),
    # rule table-data: the value's own statement chooses the column
    "wrong_given-table-data-neighbour": ("INT-SUBJ-004",),
    # rule named-component
    "wrong_given-named-component": ("INT-SUBJ-004",), "wrong_given-named-component-current": ("INT-SUBJ-004",),
    # rule condition-result
    "formulas-condition-result": ("INT-SUBJ-004",), "formulas-condition-result-leading": ("INT-SUBJ-004",),
    # rule prose-base
    "boolean-base-prose": ("INT-SUBJ-001",), "boolean-base-prose-words": ("INT-SUBJ-001",), "boolean-base-prose-denary": ("INT-SUBJ-001",),
    "boolean-base-prose-representation": ("INT-SUBJ-001",), "boolean-base-prose-hex": ("INT-SUBJ-001",),
    # rule definite-integral
    "maths-definite-bracket": ("INT-SUBJ-001",), "maths-definite-value": ("INT-SUBJ-001",), "maths-definite-antiderivative": ("INT-SUBJ-001",),
    "maths-definite-decimal": ("INT-SUBJ-001",), "maths-definite-recorded-bracket": ("INT-SUBJ-001",), "maths-definite-signed": ("INT-SUBJ-001",),
    "maths-definite-caret": ("INT-SUBJ-001",),
    # rule operand-precision for the request's exact data
    "arithmetic-given-exact-power": ("INT-SUBJ-001",), "arithmetic-given-exact-power-cent": ("INT-SUBJ-001",), "arithmetic-given-exact-cube": ("INT-SUBJ-001",),
    "arithmetic-given-exact-ph": ("INT-SUBJ-001",), "arithmetic-given-exact-digit": ("INT-SUBJ-001",),
    # rule ellipsis-rounding
    "rounding-ellipsis-nearest": ("INT-SUBJ-001",), "rounding-ellipsis-bare": ("INT-SUBJ-001",), "rounding-ellipsis-plain": ("INT-SUBJ-001",),
    "rounding-ellipsis-latex": ("INT-SUBJ-001",),
}
#: the correct writing of each, which must stay clean (the false failures the classes gave correct working among them)
REPAIR10_CONTROLS = (
    "units-prose-conversion-followed-control", "units-prose-conversion-same-line-control", "units-prose-conversion-comparison-control",
    "wrong_given-line-column-control", "wrong_given-line-column-decrease-control", "wrong_given-line-column-oxygen-control",
    "givens-row-has-value-control", "givens-row-label-run-control", "givens-row-number-verb-control", "givens-row-value-column-at-control",
    "givens-row-column-of-control", "givens-row-clause-after-control", "givens-row-clause-possessive-control", "givens-row-difference-control",
    "givens-row-ratio-control", "givens-row-numbered-of-control", "givens-row-corrected-control", "givens-row-corrected-change-control",
    "givens-row-other-quantity-control", "givens-row-trial-control", "wrong_given-table-data-neighbour-control",
    "wrong_given-named-component-control", "wrong_given-named-component-total-control", "wrong_given-named-component-sum-control",
    "formulas-condition-result-control", "formulas-condition-result-leading-control", "boolean-base-prose-control", "boolean-base-prose-denary-control",
    "boolean-base-prose-hex-control", "maths-definite-bracket-control", "maths-definite-value-control", "maths-definite-decimal-control",
    "maths-definite-signed-control", "maths-definite-caret-control", "arithmetic-given-exact-cube-control", "arithmetic-stated-expression-control",
    "arithmetic-given-exact-ph-control", "rounding-ellipsis-bare-control", "rounding-ellipsis-plain-control", "rounding-ellipsis-cut-control",
)
#: the controls the staged tree failed: a difference, a ratio, a processed and another quantity at a row (row-value, table-data,
#: named-change), and a value written with its digits cut in plain text (read as rounded)
FALSE_FAILURES_BEFORE = ("givens-row-difference-control", "givens-row-ratio-control", "givens-row-corrected-control", "givens-row-corrected-change-control",
                         "givens-row-other-quantity-control", "rounding-ellipsis-plain-control", "rounding-ellipsis-cut-control")
#: the tester's plants (t10-units-min, t10b-wg-ess, t10-giv-ess-nym, t10b-giv-ess-nym9, t10-wg-ph-4ohm, t10-form-decay, t10b-cs-bin,
#: t10-ma-int, t10b-ma-int-eq, t10-ar-mi, t10-round-mi), each named now
TESTER_PLANTS = ("units-prose-conversion-followed", "wrong_given-line-column", "givens-row-coordinated", "givens-row-ellipsis", "wrong_given-named-component",
                 "formulas-condition-result", "boolean-base-prose", "maths-definite-bracket", "maths-definite-value", "arithmetic-given-exact-power",
                 "rounding-ellipsis-nearest")


def test_every_plant_of_the_tenth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR10_PROBES) == len(REPAIR10_PROBES) + len(REPAIR10_CONTROLS) == 94
    assert {p.probe_id for p in SP.REPAIR10_PROBES} == set(REPAIR10_PROBES) | set(REPAIR10_CONTROLS)
    for pid, expected in REPAIR10_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR10_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(TESTER_PLANTS) <= set(REPAIR10_PROBES) and set(FALSE_FAILURES_BEFORE) <= set(REPAIR10_CONTROLS)
    for cls in ("units", "wrong_given", "givens", "formulas", "boolean", "maths", "arithmetic", "rounding"):
        assert {p.kind for p in SP.REPAIR10_PROBES if p.fault_class == cls} == {"answer", "control"}, cls
    assert SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES and len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_10_tamper_cases_are_registered_on_their_targets():
    """T23bb to T23bi, each on the probe that plants its fault (the suite runs them in tests/overseer/test_stem_completion.py, each on its
    planted copy, the planted copy clean); T23bg on two targets, a numbered row of p7b and a trial column of ch-t13."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23bb", "finding_missing"), ("T23bc", "receipt_altered"), ("T23bd", "formal_status_wrong"), ("T23be", "finding_missing"),
                      ("T23bf", "receipt_altered"), ("T23bg", "finding_missing"), ("T23bh", "formal_status_wrong"), ("T23bi", "receipt_altered")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # each is its class's last case before those STEM repair 11 (design section 42) and STEM repair 12 (design section 43) appended, and
    # only those follow it
    later = {"T23bj", "T23bk", "T23bl", "T23bm", "T23bn", "T23bo", "T23bp", "T23bq", "T23br", "T23bs", "T23bt"}
    for cls, case in (("units", "T23bb"), ("wrong_given", "T23bc"), ("formulas", "T23bd"), ("boolean", "T23be"), ("maths", "T23bf"), ("givens", "T23bg"),
                      ("rounding", "T23bh"), ("arithmetic", "T23bi")):
        cases = SP.TAMPER_CASES[cls]
        assert [c for c in cases if c not in later][-1] == case and set(cases[cases.index(case) + 1:]) <= later, cls


def test_the_tolerance_widening_tampering_widens_any_written_tau():
    """T23k widens a STEM band's τ·|C| to 1/2: τ of any written value now (rule operand-precision gives '(9.93 V)² / 6.0 Ω' τ = 403/200000, the
    request's 6.0 being exact), never only 1/100 or 1/20 (that check had been left untampered and the case skipped on ph-t13)."""
    band = {"op": "add", "args": [{"op": "real", "value": "0.05"}, {"op": "mul", "args": [{"op": "real", "value": "403/200000"}, {
        "op": "ite", "cond": {"op": "ge", "left": {"op": "var", "name": "c"}, "right": {"op": "real", "value": "0"}}, "then": {"op": "var", "name": "c"},
        "otherwise": {"op": "neg", "arg": {"op": "var", "name": "c"}}}]}]}
    assert T._widen_tau(band) == 1 and band["args"][1]["args"][0]["value"] == "1/2"
    assert T._widen_tau(band) == 0  # already 1/2: nothing left to widen
    assert T._widen_tau({"op": "mul", "args": [{"op": "real", "value": "1/100"}, {"op": "var", "name": "c"}]}) == 0  # no |C|: no band's slack


@pytest.mark.timeout(2400)
def test_the_repair_10_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the staged tree's false failures among them), no forbidden code."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR10_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid, expected in REPAIR10_PROBES.items():
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
        assert set(expected) & set(r["named_by"]), (pid, r["named_by"])
    for pid in REPAIR10_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ the pack beside the code
@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


@pytest.mark.parametrize("tid, old, new, quote, status", [
    # rule prose-conversion, in its own statement
    ("ch-t13", CH_R, "A time of 45 s is 0.45 min.\n\n" + CH_R, '"A time of 45 s is 0.45 min." before "Two reminders." fails', "COUNTEREXAMPLE"),
    # rule named-component
    ("ph-t13", PH_E, PH_E + "\nThe power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W.",
     '"The power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W." fails', "COUNTEREXAMPLE"),
    # rule condition-result
    ("ph-p7b", PB_E, PB_E + "\nUsing C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h.",
     '"Using C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h." fails', "COUNTEREXAMPLE"),
    # rule prose-base
    ("cs-t13", CS_END, "The binary number 110010₂ is 48 in denary.\n\n" + CS_END, '"The binary number 110010₂ is 48 in denary." fails', "COUNTEREXAMPLE"),
    ("cs-t13", CS_END, "10 in binary is 1011.\n\n" + CS_END, '"10 in binary is 1011" fails', "COUNTEREXAMPLE"),
    ("cs-t13", CS_END, "10 in binary is 1010.\n\n" + CS_END, '"10 in binary is 1010" and "1010 in binary is 10" hold', "ENTAILED"),
    ("cs-t13", CS_END, "1010 in binary is 10.\n\n" + CS_END, '"10 in binary is 1010" and "1010 in binary is 10" hold', "ENTAILED"),
    # rule definite-integral
    ("maa-t13", MA_END, "Also ∫₀¹ 6t dt = 6.\n\n" + MA_END, '"∫₀¹ 6t dt = 6" fails', "COUNTEREXAMPLE"),
    ("maa-t13", MA_END, "Also ∫₋₁¹ 3t² dt = 0.\n\n" + MA_END, '"∫₋₁¹ 3t² dt = 0" fails', "COUNTEREXAMPLE"),
    # rule ellipsis-rounding
    ("maa-t13", MA_END, "Also 8/3 = 2.66… = 2.6, to 2 s.f.\n\n" + MA_END, '"Also 8/3 = 2.66… = 2.6, to 2 s.f." fails', "COUNTEREXAMPLE"),
    ("maa-t13", MA_END, "Also 8/3 = 2.68…\n\n" + MA_END, '"8/3 = 2.68…" and "8/3 ≈ 2.86…" fail', "COUNTEREXAMPLE"),
    ("maa-t13", MA_END, "Also 8/3 ≈ 2.86…\n\n" + MA_END, '"8/3 = 2.68…" and "8/3 ≈ 2.86…" fail', "COUNTEREXAMPLE"),
    ("maa-t13", MA_END, "Also 8/3 = 2.66…\n\n" + MA_END, '"8/3 = 2.66…", "8/3 = 2.67…" and "0.333… = 1/3" hold', "ENTAILED"),
    ("maa-t13", MA_END, "Also 8/3 = 2.67…\n\n" + MA_END, '"8/3 = 2.66…", "8/3 = 2.67…" and "0.333… = 1/3" hold', "ENTAILED"),
    ("maa-t13", MA_END, "Also 0.333… = 1/3.\n\n" + MA_END, '"8/3 = 2.66…", "8/3 = 2.67…" and "0.333… = 1/3" hold', "ENTAILED"),
    # rule operand-precision, the request's data exact
    ("ph-t13", PH_E, PH_E + "\nAlso (12 V)² / 4.0 Ω = 36.3 W.", '"Also (12 V)² / 4.0 Ω = 36.3 W." fails (36)', "COUNTEREXAMPLE"),
    ("mai-t13", MI_END, "Check: 4000 × 1.036⁵ = 4773.7406, so 4773.74 euros to the nearest cent.\n\n" + MI_END,
     '"4000 × 1.036⁵ = 4773.7406" fails in its fourth decimal (4773.7401)', "COUNTEREXAMPLE"),
    # rule row-value: any order, a numbered row, a column told apart by its number
    ("ess-t13", ES_W, "Dissolved oxygen was 3.9 mg dm⁻³ at site C.", '"Dissolved oxygen was 3.9 mg dm⁻³ at site C."', "COUNTEREXAMPLE"),
    ("ess-t13", ES_W, "Site C's dissolved oxygen is only 3.9 mg dm⁻³.", '"Site C\'s dissolved oxygen is only 3.9 mg dm⁻³."', "COUNTEREXAMPLE"),
    ("ph-p7b", PB_E, PB_E + "\nThe measured count rate at t = 12 h is 568 counts min⁻¹.", '"The measured count rate at t = 12 h is 568 counts min⁻¹."',
     "COUNTEREXAMPLE"),
    ("ch-t13", CH_R, "At 30.0 °C, trial 2 took 43.0 s.\n\n" + CH_R, '"At 30.0 °C, trial 2 took 43.0 s." fails against 34.0', "COUNTEREXAMPLE"),
])
def test_d31_states_each_new_reading_as_the_code_decides_it(d31, tid, old, new, quote, status):
    """Each D31 statement of this repair, quoted, and executed on the recorded answer it extends: the one new check of its rule has the
    status D31 says (the arithmetic or substitution of the line, where it has one, holds)."""
    assert quote in d31, quote
    got = [c for c in _new(tid, _with(tid, old, new)) if c[0] != "eq" or "rule rounded-digits" not in c[2]]
    if status == "ENTAILED":
        assert got and not _failing(got), got
    else:
        assert len(_failing(got)) == 1 and _failing(got)[0][1] == status, got


@pytest.mark.parametrize("tid, line", [
    ("ess-t13", "Dissolved oxygen at site C is 5.8 mg dm⁻³ lower than at A."), ("ess-t13", "Nitrate at B is 7 times that at A."),
    ("ph-p7b", "The corrected count rate at 12 h is 566 counts min⁻¹."), ("ph-p7b", "The decay rate at 12 h is 0.087 h⁻¹."),
    ("ph-p7b", "The corrected rate falls from 1131 counts min⁻¹ at 4 h to 566 counts min⁻¹ at 12 h."),
    ("ess-t13", "If nitrate at site B fell to 4.0 mg dm⁻³, oxygen there might rise."),
    ("ess-t13", "A target of 9.0 mg dm⁻³ of dissolved oxygen at site C would need less sewage."),
    ("ess-t13", "Dissolved oxygen at site C is below 4.0 mg dm⁻³."),
])
def test_d31_says_what_is_no_cell_and_the_code_fails_none_of_it(d31, tid, line):
    """D31's 'Not read' list for rule row-value, each of whose shapes had been set against the cell and failed: none fails now."""
    quote = {"If nitrate at site B fell to 4.0 mg dm⁻³, oxygen there might rise.": '"If nitrate at site B fell to 4.0 mg dm⁻³, …"',
             "A target of 9.0 mg dm⁻³ of dissolved oxygen at site C would need less sewage.":
                 '"A target of 9.0 mg dm⁻³ of dissolved oxygen at site C would …"',
             "Dissolved oxygen at site C is below 4.0 mg dm⁻³.": '"is below 4.0 mg dm⁻³"'}.get(line, line)
    assert quote in d31, quote
    text = _with(tid, ES_W, line) if tid == "ess-t13" else _with(tid, PB_E, PB_E + "\n" + line)
    assert not _failing(_new(tid, text))


def test_d32_says_which_integrals_and_ellipses_are_checked():
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert ("Two of ST-UNDEC-001's constructs are checked where D31 reads them: a definite integral of a polynomial in one variable with "
            "whole-number limits, and its evaluation bracket") in d32
    assert ('set equal or approximately equal to a closed expression on either side or restated as a value, in a relation that holds no other '
            'construct outside the encodings ("8/3 = 2.66…", "0.333… = 1/3"') in d32
    assert ('Every other integral and ellipsis (a cut value inside an expression, "0.333… × 3 = 1", or set equal to a symbol, "x = 2.66…"), and a '
            'cut value after a power beyond 12, stays ST-UNDEC-001.') in d32
    for text, kind, status in (("∫₀¹ 6t dt = [3t²]₀¹ = 3", None, "ENTAILED"), ("8/3 = 2.66…", "eq", "ENTAILED"), ("0.333… = 1/3", "eq", "ENTAILED")):
        checks, findings = _decided(text, "mathematics_aa")
        assert checks and all(_holds(k, s) for k, s, _d in checks) and not findings, (text, checks, findings)
    for text in ("∫₀¹ √x dx = 2/3", "$1 + 2 + \\cdots + 10 = 55$", "$A = 4787.58\\ldots$", "0.333… × 3 = 1", "x = 2.66…"):
        checks, findings = _decided(text, "mathematics_aa")
        assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-001"], (text, findings)


def test_i97_the_master_prompt_and_the_mistakes_rows_name_the_new_rules():
    i97 = _section(_pack_text("03-inspection.md"), "**I97 ", "\n- **I98")
    prompt, examples = _pack_text("master_prompt.txt"), _pack_text("07-examples.md")
    for rule in ("named-component", "condition-result", "definite-integral", "ellipsis-rounding", "prose-base", "row-value", "operand-precision"):
        assert f"rule {rule}" in i97 and f"rule {rule}" in prompt, rule
    for rule in ("prose-conversion", "table-operands"):
        assert f"rule {rule}" in prompt, rule
    for row in ('| `finding_missing` because "Also ∫₀¹ 6t dt = [3t²]₀¹ = 3." carries no ST-UNDEC-001 |',
                "| `receipt_altered`, or a fault of the claim, because a check naming rule named-component fails",
                '| `formal_status_wrong` because "8/3 = 2.66…" holds though 8/3 is 2.67 to 2 d.p. |',
                '| `receipt_altered` because "(12 V)² / 4.0 Ω = 36.3 W" fails though it is within 1/100 of 36 |'):
        assert row in examples, row
    # each mistake the rows name is decided as they say
    checks, findings = _decided("Also ∫₀¹ 6t dt = [3t²]₀¹ = 3.", "mathematics_aa")
    assert sorted(k for k, _s, _d in checks) == ["alg", "eq"] and all(_holds(k, s) for k, s, _d in checks) and not findings
    assert _rule(_new("ph-t13", _with("ph-t13", PH_E, PH_E + "\nThe power dissipated in the 4.0 Ω resistor is P = (9.93 V)² / 6.0 Ω = 16.4 W.")),
                 "named-component")


def test_the_common_mistakes_rows_say_what_the_code_decides():
    """The dossier guide's three rows and the inspection guide's one for the readings of this repair, each quote executed."""
    dossier = _section(_pack_text("02-dossier.md"), "## 15. Common mistakes", "\nPack version")
    inspection = _section(_pack_text("03-inspection.md"), "## 13. Common mistakes", "\nPack version")
    for row in ('| Expecting a value at a supplied table\'s row to be checked only when the line names the row first ("At site C, dissolved oxygen = '
                '3.9 mg dm⁻³.") | A value its own clause states at exactly one row and one column, in any order',
                '| Reading a value restated from a decimal written with its digits cut ("= 4787.58…", then "= 4788 euros, to the nearest euro") as '
                'undecided | It is set against the cut digits with the rounding the prose states (rule ellipsis-rounding)',
                '| Taking τ = 1/100 for "=" in arithmetic whose numerals write the request\'s own data ("(12 V)² / 4.0 Ω = 36.3 W") | A numeral that '
                'writes a value the request states is exact (R3)'):
        assert row in dossier, row
    assert ('| `formal_status_wrong` or `receipt_altered` for a named-component or condition-result check that fails as a warning while the line\'s '
            'own substitution and arithmetic hold |') in inspection
    # a value at a row in any order of its clause, against the cell (3.8 at C; 586 at 12 h)
    for tid, old, new in (("ess-t13", ES_W, "At site C, dissolved oxygen = 3.9 mg dm⁻³."), ("ess-t13", ES_W, "Site C's dissolved oxygen is only 3.9 mg dm⁻³."),
                          ("ph-p7b", PB_E, PB_E + "\nThe measured count rate was 568 counts min⁻¹ at 12 h.")):
        got = _rule(_new(tid, _with(tid, old, new)), "row-value")
        assert len(got) == 1 and got[0][1] == "COUNTEREXAMPLE", (new, got)
    # a value restated from a cut decimal with the rounding the prose states
    for text, status in (("4787.58… = 4788, to the nearest euro", "ENTAILED"), ("4787.58… = 4787, to the nearest euro", "COUNTEREXAMPLE")):
        checks, findings = _decided(text, "mathematics_ai")
        assert [(k, s) for k, s, _d in checks] == [("res", status)] and "rule ellipsis-rounding" in checks[0][2] and not findings, (text, checks)
    # the request's data exact: τ = 0, the detail saying so
    got = _rule(_new("ph-t13", _with("ph-t13", PH_E, PH_E + "\nAlso (12 V)² / 4.0 Ω = 36.3 W.")), "operand-precision")
    assert len(got) == 1 and got[0][1] == "COUNTEREXAMPLE" and "τ = 0" in got[0][2], got
    # a condition-result check failing while the line's substitution and arithmetic hold
    got = _new("ph-p7b", _with("ph-p7b", PB_E, PB_E + "\nUsing C = C₀ − λt, C = 1600 − 0.087 × 32 = 1597 counts min⁻¹ at 32 h."))
    assert sorted((k, st) for k, st, _d in got) == [("eq", "ENTAILED"), ("res", "COUNTEREXAMPLE"), ("sub", "ENTAILED")], got
    assert _rule(got, "condition-result") and _rule(got, "condition-result")[0][1] == "COUNTEREXAMPLE"
