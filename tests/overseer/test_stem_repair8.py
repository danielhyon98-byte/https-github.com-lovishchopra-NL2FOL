"""STEM repair 8 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 39).

* the STEM probes of repair 8 (the eighth independent test's plants, each class with its clean control): rule value-at for a computing
  chain and rules name-list and item-label (a value a run computes under a condition, after the list or the range that names it, or for a
  numbered item is the named quantity's value: the tester's seven false INT-SUBJ-001 on correct working, four with ST-DIM-001), with rules
  condition-value and name-list's check of the values the computation takes; rule table-terms (a value copied wrongly from the supplied
  table, or a wrong background, its arithmetic consistent: the tester's four plants, neither checked nor named while D31 said a value
  the working takes from the table is set against its row); rule law-values (a law its evaluation does not follow, named by nothing) and
  the law named by a failed substitution of its evaluation; and rule inline-restatement with describing words before ', so';
* the STEM receipt cases T23ao (a failed law-values check restated as holding), T23ap (the INT-SUBJ-004 of a failed table-terms check
  dropped), T23aq (a failed condition-value check reported as holding), T23ar (an ST-DIM-001 the packs do not derive added on a value
  computed under its condition), T23as (the INT-SUBJ-001 of a restatement after describing words dropped) and T23at (a failed name-list
  check restated as holding);
* the pack beside the code: D31's two new paragraphs, its table paragraph and its opening list, I97, the master prompt, the mistakes rows
  and Example 39, every statement executed against the STEM front end, the example regenerated through the channel.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stem_probes as SP  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.branches import RouterHub  # noqa: E402
from epinoic_logic.engine import SolverConfig  # noqa: E402
from epinoic_logic.integrity import WorkPlan  # noqa: E402
from epinoic_logic.overseer.pack import installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "bi-t13": "biology", "ess-t13": "ess", "ch-t13": "chemistry", "mai-t13": "mathematics_ai"}
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-8-test-key-0123456789abcdef"
#: the recorded working the pack's statements rewrite
PH_C = "(c) [1]\nV = ε − Ir"
PH_PC = PH_C + "\nV = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PH_D = "P = V²/R\nP = (9.93 V)²"
PB_12 = "t = 12 h: 586 − 20 = 566 ± 12 counts min⁻¹"
PB_24 = "t = 24 h: 220 − 20 = 200 ± 4 counts min⁻¹"
BI_END = "which makes ATP. [1 spare]"
ES_A = "(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease [1]"


def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


# ============================================================================================ the probes and the tamper cases
#: each plant of the eighth independent test (and of the shapes of its classes found closing them), with the code that must name it
REPAIR8_PROBES = {
    # rule value-at for a computing chain, rules name-list and item-label: a slip in the computation is still named on it
    "chemistry-value-at-mean-slip": ("INT-SUBJ-001",), "chemistry-value-at-rate-slip": ("INT-SUBJ-001",), "maths-name-list-mean-slip": ("INT-SUBJ-001",),
    "arithmetic-value-at-uptake-slip": ("INT-SUBJ-001",), "physics-value-at-current-slip": ("INT-SUBJ-001",), "physics-value-at-rate-slip": ("INT-SUBJ-001",),
    "chemistry-item-label-slip": ("INT-SUBJ-001",), "maths-item-label-year-slip": ("INT-SUBJ-001",),
    # rules condition-value and name-list's check
    "wrong_given-name-list-term": ("INT-SUBJ-004",), "wrong_given-condition-value-after": ("INT-SUBJ-004",), "wrong_given-condition-value-in": ("INT-SUBJ-004",),
    "wrong_given-name-list-range-term": ("INT-SUBJ-004",),
    # rule table-terms
    "wrong_given-table-row-12": ("INT-SUBJ-004",), "wrong_given-table-row-4": ("INT-SUBJ-004",), "wrong_given-table-row-20": ("INT-SUBJ-004",),
    "wrong_given-table-background": ("INT-SUBJ-004",), "wrong_given-table-units-background": ("INT-SUBJ-004",), "wrong_given-table-value-at": ("INT-SUBJ-004",),
    "wrong_given-table-ess-consistent": ("INT-SUBJ-004",), "wrong_given-table-bio-row": ("INT-SUBJ-004", "INT-SUBJ-001"),
    "wrong_given-prose-background": ("INT-SUBJ-004",),
    # rule law-values, and the law named by a failed substitution of its evaluation
    "formulas-law-sign": ("INT-SUBJ-004",), "formulas-law-evaluation-sign": ("INT-SUBJ-004", "INT-SUBJ-001"), "formulas-law-same-line": ("INT-SUBJ-004",),
    "formulas-law-so": ("INT-SUBJ-004",), "formulas-law-using": ("INT-SUBJ-004",), "formulas-law-power": ("INT-SUBJ-001",),
    "formulas-law-power-half": ("INT-SUBJ-001",),
    # rule inline-restatement with describing words
    "rounding-inline-words": ("INT-SUBJ-001",), "rounding-inline-words-which": ("INT-SUBJ-001",), "rounding-inline-words-unit": ("INT-SUBJ-001",),
    "rounding-inline-words-phrase": ("INT-SUBJ-001",),
}
#: the correct writing of each, which must stay clean (the tester's seven false INT-SUBJ-001 on correct working among them)
REPAIR8_CONTROLS = ("chemistry-value-at-mean-control", "chemistry-value-at-rate-control", "chemistry-value-at-bare-control", "maths-name-list-mean-control",
                    "arithmetic-value-at-uptake-control", "physics-value-at-current-control", "physics-value-at-rate-control", "physics-value-at-when-control",
                    "physics-value-after-control", "physics-value-in-control", "chemistry-name-list-range-control", "chemistry-item-label-control",
                    "chemistry-item-label-plain-control", "maths-item-label-year-control", "maths-name-list-between-control",
                    "wrong_given-table-background-control", "wrong_given-table-units-control", "wrong_given-table-value-at-control",
                    "wrong_given-table-bound-control", "wrong_given-table-back-control", "wrong_given-prose-background-control", "formulas-law-sign-control",
                    "formulas-law-same-line-control", "formulas-law-so-control", "formulas-law-using-control", "formulas-other-law-control",
                    "formulas-law-computed-term-control", "rounding-inline-words-control", "rounding-inline-words-unit-control",
                    "rounding-inline-words-phrase-control")
#: the tester's seven controls that had a false INT-SUBJ-001 (four with ST-DIM-001), each as a probe of its class
TESTER_CONTROLS = ("chemistry-value-at-mean-control", "chemistry-value-at-rate-control", "physics-value-at-current-control", "physics-value-at-rate-control",
                   "arithmetic-value-at-uptake-control", "physics-value-after-control", "maths-name-list-mean-control")
#: the tester's four plants of a value from the supplied data, neither checked nor named before
TESTER_TABLE_PLANTS = ("wrong_given-table-row-12", "wrong_given-table-row-4", "wrong_given-table-row-20", "wrong_given-table-background")


def test_every_plant_of_the_eighth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR8_PROBES) == len(REPAIR8_PROBES) + len(REPAIR8_CONTROLS) == 62
    assert {p.probe_id for p in SP.REPAIR8_PROBES} == set(REPAIR8_PROBES) | set(REPAIR8_CONTROLS)
    for pid, expected in REPAIR8_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR8_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(TESTER_CONTROLS) <= set(REPAIR8_CONTROLS) and set(TESTER_TABLE_PLANTS) <= set(REPAIR8_PROBES)
    # the slip of a run computed under a condition is named by its arithmetic alone: the condition's row is the row of its result
    assert SP.probe("arithmetic-value-at-uptake-slip").forbidden == ("INT-SUBJ-004",)
    # the classes the four problems lie in have their answers and their controls
    for cls in ("chemistry", "maths", "arithmetic", "physics", "wrong_given", "formulas", "rounding"):
        assert {p.kind for p in SP.REPAIR8_PROBES if p.fault_class == cls} == {"answer", "control"}, cls
    assert SP.PROBES[393:455] == SP.REPAIR8_PROBES and SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_8_tamper_cases_are_registered_on_their_targets():
    """T23ao restates a failed law-values check as holding (r7/ph-t13), T23ap drops the INT-SUBJ-004 of a failed table-terms check (r7/p7b),
    T23aq reports a failed condition-value check as holding (r7/ph-t13), T23ar adds an ST-DIM-001 the packs do not derive on a mean computed
    under its condition (r7/ch-t13), T23as drops the INT-SUBJ-001 of a restatement after describing words (r7/ph-t13) and T23at restates a
    failed name-list check as holding (r7/ch-t13); the suite runs them in tests/overseer/test_stem_completion.py, each on its planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23ao", "receipt_altered"), ("T23ap", "finding_missing"), ("T23aq", "formal_status_wrong"), ("T23ar", "infrastructure"),
                      ("T23as", "finding_missing"), ("T23at", "receipt_altered")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # STEM repair 10 (design section 41) appended T23bd to formulas, T23bh to rounding and T23bc to wrong_given, after these
    # STEM repair 11 (design section 42) appended T23bj to the formulas class and T23bl to the wrong-given class; STEM repair 12 (design
    # section 43) T23bt to the rounding class
    assert SP.TAMPER_CASES["formulas"] == ("T23a", "T23p", "T23ao", "T23ay", "T23bd", "T23bj")
    assert SP.TAMPER_CASES["rounding"][-3:] == ("T23as", "T23bh", "T23bt")
    assert SP.TAMPER_CASES["wrong_given"][-6:] == ("T23ap", "T23aq", "T23at", "T23aw", "T23bc", "T23bl")
    assert SP.TAMPER_CASES["chemistry"] == ("T23b", "T23d", "T23j", "T23ar")


@pytest.mark.timeout(1200)
def test_the_repair_8_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the tester's seven false INT-SUBJ-001 on correct working among them), no forbidden code;
    the tester's four table plants and every check of the new rules are named by their warning (INT-SUBJ-004)."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR8_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid in REPAIR8_PROBES:
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
    for pid in REPAIR8_PROBES:
        if pid.startswith(("wrong_given-", "formulas-law-")) and pid not in ("formulas-law-power", "formulas-law-power-half"):
            assert "INT-SUBJ-004" in rows[pid]["named_by"], (pid, rows[pid]["named_by"])
    for pid in REPAIR8_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ the pack beside the code
def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _with(tid: str, old: str, new: str) -> str:
    text = R7[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _holds(kind: str, status: str) -> bool:
    return status in ("ENTAILED", "SATISFIABLE") if kind != "bool" else status == "UNSATISFIABLE"


def _new(tid: str, text: str) -> tuple[list, list]:
    """The checks and findings ``text`` has beyond the recorded answer's (multiset differences by kind, status and statement head)."""
    def key(c):
        return (c[0], c[1], c[2].split(" [claims")[0])
    checks, findings = _task(tid, text)
    base, base_f = _task(tid, R7[tid]["response_text"])
    left = Counter(key(c) for c in base)
    out = []
    for c in checks:
        if left[key(c)]:
            left[key(c)] -= 1
        else:
            out.append(c)
    return out, list((Counter(findings) - Counter(base_f)).elements())


def _failing(checks) -> list:
    return [c for c in checks if not _holds(c[0], c[1])]


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_the_value_a_run_computes_under_a_condition_as_the_code_decides_it(d31):
    """D31's new paragraph, executed: each run it names gives its quantity's value (nothing fails, no check takes the condition, the list's
    last value or the item's number as a side, the computation's arithmetic holding); each value it says fails against the condition or the
    list fails at warning severity; the uptake slip fails its arithmetic alone; the conversion reads as before, and the bare list states a
    statistic when a statistic names it (STEM repair 9: the paragraph, one statement to a line, runs to the next paragraph's head)."""
    para = _section(d31, "  - **A value a run computes under a condition, after a list or for a numbered item.** ", "\n  - **")
    for words in ('A maths run right after a condition word ("at", "when", "after", "before", "during", "within", "until", "for", "in") that opens with '
                  'the condition and then computes the named quantity\'s value',
                  'the condition, the list\'s last value and the item\'s number are part of its name, never a side of a relation, and the computation\'s '
                  'links are checked as in any chain (rules value-at, name-list and item-label',
                  'When the computation takes exactly one value of the condition\'s dimension, that value is set against the condition, every written '
                  'digit counting (rule condition-value',
                  'a condition with no exact SI value, "at 30 °C", is set against nothing',
                  'each at severity warning: which value stands for the condition or for a listed value is a reading (INT-SUBJ-004)'):
        assert words in para, words
    # (the run D31 names, profile, its computation, the left side the run had been read to start a relation with)
    for text, profile, computation, side in (
            ("Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s", "chemistry", "(33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s", "30.0 °C ="),
            ("I at t = 5 s = 12 V / 4.5 Ω = 2.7 A", "physics", "12 V / 4.5 Ω = 2.7 A", "5 s ="),
            ("Speed after 2.0 s = 9.8 m s⁻² × 2.0 s = 19.6 m s⁻¹", "physics", "9.8 m s⁻² × 2.0 s = 19.6 m s⁻¹", "2.0 s ="),
            ("Uptake at 30 °C = 2 × 40 = 80", "biology", "2 × 40 = 80", "30 °C ="),
            ("Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3", "biology", "(18 + 27 + 40) ÷ 3 = 28.3", "40 ="),
            ("The rise from 20.0 °C to 30.0 °C = 30.0 − 20.0 = 10.0 K", "chemistry", "30.0 − 20.0 = 10.0 K", "30.0 °C ="),
            ("Rate for trial 2 = 1/60.8 s = 0.0164 s⁻¹", "chemistry", "1/60.8 s = 0.0164 s⁻¹", "2 ="),
            ("Year 2 = 4000 × 1.036² = 4293.18 euros", "mathematics_ai", "4000 × 1.036² = 4293.18", "2 =")):
        assert f'"{text}' in para, text
        checks, findings = _decided(text, profile)
        assert not _failing(checks) and findings == [], (text, checks, findings)
        assert [k for k, _s, d in checks if f"'{computation}'" in d] == ["eq"], (text, checks)
        assert not [d for _k, _s, d in checks if f"'{side}" in d], (text, checks)
    for text, profile, value in (("The charge that flows after 2.0 s = 4.1 A × 3.0 s = 12.3 C", "physics", "3.0 s"),
                                 ("The energy dissipated in 10 s = 16.4 W × 20 s = 328 J", "physics", "20 s"),
                                 ("Mean of 18, 27 and 40 = (18 + 27 + 41) ÷ 3 = 28.7", "biology", "41")):
        assert f'"{text}' in para, text
        checks, _f = _decided(text, profile)
        bad = _failing(checks)
        assert [k for k, _s, _d in bad] == ["giv"] and f"'{value}'" in bad[0][2] and "failure severity warning" in bad[0][2], (text, checks)
        assert ("rule condition-value" if "Mean" not in text else "rule name-list") in bad[0][2]
    checks, _f = _decided("Uptake at 30 °C = 2 × 40 = 80", "biology")
    assert not [c for c in checks if "rule condition-value" in c[2]]  # a condition with no exact SI value is set against nothing
    # the row of the run's result: the uptake slip fails its arithmetic, and the 40 is not set against the 30 °C row
    assert '("Uptake at 30 °C = 2 × 40 = 90": its arithmetic fails, and the 40 is not set against the 30 °C row)' in para
    bad, _f = _new("bi-t13", _with("bi-t13", BI_END, BI_END + "\nUptake at 30 °C = 2 × 40 = 90"))
    assert [(k, s) for k, s, d in _failing(bad)] == [("eq", "COUNTEREXAMPLE")] and "'2 × 40 = 90'" in _failing(bad)[0][2], bad
    # a conversion of the condition reads as before; a list with no computation after it states a statistic of the listed values when a
    # statistic names it (STEM repair 9, rule statistics: before, ST-PARSE-001 and unchecked), and is still a relation written partly in
    # words after any other name
    assert 'A run that converts the condition itself ("at 25 °C = 298 K") is a conversion, as before.' in para
    assert ('A list with no computation after it states a statistic of the listed values when a statistic names it ("Mean of 18, 27 and 40 = '
            '28.3" holds and "Mean of 18, 27 and 40 = 29.3" fails: rule statistics, above), and is a relation written partly in words after any '
            'other name ("Sum of 18, 27 and 40 = 85": ST-PARSE-001).') in para
    checks, _f = _decided("The rate constant at 25 °C = 298 K is 0.040 s⁻¹.", "chemistry")
    assert [k for k, _s, _d in checks] == ["cnv"] and all(_holds(k, s) for k, s, _d in checks)
    for text, status in (("Mean of 18, 27 and 40 = 28.3", "ENTAILED"), ("Mean of 18, 27 and 40 = 29.3", "COUNTEREXAMPLE")):
        checks, findings = _decided(text, "biology")
        assert [(k, s) for k, s, _d in checks] == [("eq", status)] and findings == [], (text, checks, findings)
        assert "(rule statistics)" in checks[0][2] and "failure severity warning" in checks[0][2], (text, checks)
    checks, findings = _decided("Sum of 18, 27 and 40 = 85", "biology")
    assert checks == [] and [c for c, _m in findings] == ["ST-PARSE-001"], (checks, findings)


def test_d31_states_rule_table_terms_as_the_code_decides_it(d31):
    """The table paragraph's rule table-terms, executed on the recorded answers: each number it says is set against a row's cell or the
    background fails at warning severity; the line that computes a cell, the bound and the factor plan no table-terms check; the row of a
    line's result is no row its working takes from. The prose background is compared every digit counting."""
    para = _section(d31, "  - **A value a line of working takes from a supplied table** ", "\n  - **")  # STEM repair 9: one statement to a line
    for words in ('A number the working adds to or takes from the column\'s values that is none of them is read too (rule table-terms)',
                  '("t = 12 h: 568 − 20 = 548 ± 11 counts min⁻¹" against the 12 h row\'s 586, "(9.6 − 3.9) ÷ 9.6 × 100" against site C\'s 3.8)',
                  '("t = 24 h: 220 − 25 = 195 ± 4 counts min⁻¹" against the background of 20 counts per minute), unless the line computes a cell or such '
                  'a value itself ("566 + 20 = 586") or the number is a stated percentage of the cell (a bound: "586 + 11.72")',
                  'nothing is read when two numbers or two rows\' values are unaccounted for, or for a factor ("Uptake at 30 °C = 2 × 41 = 82": only its '
                  'arithmetic is checked)'):
        assert words in para, words
    for tid, old, new, term in (("ph-p7b", PB_12, "t = 12 h: 568 − 20 = 548 ± 11 counts min⁻¹", "568"),
                                ("ph-p7b", PB_24, "t = 24 h: 220 − 25 = 195 ± 4 counts min⁻¹", "25"),
                                ("ess-t13", ES_A, "(a) Percentage decrease = (9.6 − 3.9) ÷ 9.6 × 100\n= 59.4% decrease [1]", "3.9")):
        got, _f = _new(tid, _with(tid, old, new))
        bad = [c for c in _failing(got) if "rule table-terms" in c[2]]
        assert len(bad) == 1 and f"'{term}'" in bad[0][2] and "failure severity warning" in bad[0][2], (new, got)
    for tid, old, new in (("ph-p7b", PB_12, "t = 12 h: 566 + 20 = 586 counts min⁻¹"), ("ph-p7b", PB_12, PB_12 + " (upper bound 586 + 11.72 = 597.72 counts min⁻¹)"),
                          ("bi-t13", BI_END, BI_END + "\nUptake at 30 °C = 2 × 41 = 82"), ("bi-t13", BI_END, BI_END + "\nUptake at 30 °C = 2 × 40 = 80")):
        got, findings = _new(tid, _with(tid, old, new))
        assert not [c for c in got if "rule table-terms" in c[2] or "rule table-operands" in c[2]] and not _failing(got), (new, got)
    # the prose background, every digit counting (it had held by the 20's trailing zero)
    assert '"the background count rate of 25 counts min⁻¹" fails against the supplied "20 counts per minute"' in d31
    got, _f = _new("ph-p7b", _with("ph-p7b", "the background of 20 counts min⁻¹ is constant", "the background count rate of 25 counts min⁻¹ is constant"))
    assert [(k, s) for k, s, _d in _failing(got)] == [("giv", "COUNTEREXAMPLE")] and "'25 counts min⁻¹'" in _failing(got)[0][2], got
    got, _f = _new("ph-p7b", _with("ph-p7b", "the background of 20 counts min⁻¹ is constant", "the background count rate of 20 counts min⁻¹ is constant"))
    assert not _failing(got), got


def test_d31_states_rule_law_values_as_the_code_decides_it(d31):
    """The law paragraph, executed: 'V = ε + Ir' before the recorded evaluation fails the law-values check at warning severity, its detail as
    D31 quotes it and its arithmetic holding; the right law is its substitution; the computed term and another relation plan no law-values
    check; a failed substitution names the law's statement."""
    para = _section(d31, "  - **A law and the line that evaluates it.** ", "\n  - **")  # STEM repair 9: one statement to a line
    for words in ('is set against the law at the values the line puts in, each value written with a unit paired with the law\'s symbol of its dimension',
                  'the law gives 14.07 V where the line states 9.9 V, so the check fails, its `detail` saying "the law stated in" its statement "at the '
                  'values the line puts in" and "rule law-values", at severity warning',
                  'Written with the law the line follows ("V = ε − Ir"), the line is that law\'s substitution, read as before.',
                  'A failed substitution names the claim that states the law it evaluates beside the line\'s'):
        assert words in para, words
    checks, _f = _task("ph-t13", _with("ph-t13", PH_C, "(c) [1]\nV = ε + Ir"))
    law = [c for c in checks if "rule law-values" in c[2]]
    assert len(law) == 1 and law[0][1] == "COUNTEREXAMPLE" and "the law stated in s3.1 at the values the line puts in" in law[0][2], checks
    assert "(ε = 12 [V], I = 4.14 [A], r = 0.50 [Ω])" in law[0][2] and "failure severity warning" in law[0][2]
    assert [s for k, s, d in checks if "the written arithmetic: '12 V − (4.14 A × 0.50 Ω) = 9.9 V'" in d] == ["ENTAILED"]
    checks, _f = _task("ph-t13", R7["ph-t13"]["response_text"])
    assert [s for k, s, d in checks if k == "sub" and "'V = 12 V − (4.14 A × 0.50 Ω)'" in d] == ["ENTAILED"] and not [c for c in checks if "rule law-values" in c[2]]
    for old, new in ((PH_PC, PH_C + "\nV = 12 V − 2.07 V = 9.93 V"), ("P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W", "P = V²/R\nP = 9.93 V × 1.655 A = 16.4 W")):
        assert new.split("\n")[-1].split(" = ", 1)[1].split(" = ")[0] in para, new
        got, findings = _new("ph-t13", _with("ph-t13", old, new))
        assert not [c for c in got if "rule law-values" in c[2]] and not _failing(got), (new, got)
    # the failed substitution of 'P = V/R' names the law's statement among the statements it relies on: its claims in the probe
    # (formulas-law-power) are the law's, the line's and V's
    from epinoic_logic.stem import build_document, clear_document_cache
    from epinoic_logic.stem.checks import build_checks
    clear_document_cache()
    doc = build_document(_with("ph-t13", PH_D, "P = V/R\nP = (9.93 V)²"), R7["ph-t13"]["question"], "physics")
    sub = [pc for pc in build_checks(doc, report_id="r", request_id="q").checks if pc.relation_kind == "sub" and "'P = (9.93 V)² / 6.0 Ω'" in pc.description]
    assert len(sub) == 1 and sub[0].related_ids[0] == re.search(r"the formula of 'P' stated in (s[\d.]+)", sub[0].description).group(1), sub


def test_d31_states_the_restatement_after_describing_words_as_the_code_decides_it(d31):
    assert ('up to three words describing the value may stand between the chain\'s value and the comma before the cue, "= 60.4% decrease, so 61% to 2 '
            's.f." and "= 9.93 V across the resistors, so 9.8 V to 2 s.f." fail, while "= 60.4% decrease, so 60% to 2 s.f." holds') in d31
    for tid, old, new, holds in (("ess-t13", "= 60.4% decrease [1]", "= 60.4% decrease, so 61% to 2 s.f. [1]", False),
                                 ("ess-t13", "= 60.4% decrease [1]", "= 60.4% decrease, so 60% to 2 s.f. [1]", True),
                                 ("ph-t13", "(4.14 A × 0.50 Ω) = 9.9 V", "(4.14 A × 0.50 Ω) = 9.93 V across the resistors, so 9.8 V to 2 s.f.", False)):
        got, _f = _new(tid, _with(tid, old, new))
        res = [c for c in got if c[0] == "res"]
        assert res and all(_holds(k, s) for k, s, _d in res) == holds and (holds or _failing(got) == [c for c in res if not _holds(c[0], c[1])]), (new, got)


def test_i97_the_master_prompt_and_the_mistakes_rows_say_what_the_code_does():
    inspection, prompt, dossier, examples = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt"), _pack_text("02-dossier.md"), _pack_text("07-examples.md")
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    assert ('Nor accuse the absence of a check between a run\'s condition, the last value of the list that names its quantity or an item\'s number and the '
            'computation after it (rules value-at, name-list and item-label: they name the quantity, and only a value the computation takes for the '
            'condition or for a listed value is checked), or a check whose `detail` says "rule law-values" that fails, at severity warning, while the '
            'line\'s arithmetic holds (the line does not evaluate the law its part states: Examples, Example 39), or a number the working takes beside a '
            'supplied table\'s cells set against a row\'s cell or a stated value (rule table-terms).') in i97
    assert ('A run that computes a quantity\'s value under a condition, after the list that names it or for a numbered item gives that value, never a '
            'relation of the condition, the list or the number (rules value-at, name-list and item-label); a law its part states is set against the line '
            'that evaluates it at the values that line puts in (rule law-values), and a number the working takes beside a supplied table\'s cells that is '
            'none of them against the named row\'s cell or the stated value of its quantity (rule table-terms), each at severity warning (Dossier guide '
            'D31; Examples, Example 39).') in prompt
    for row in ('| Reading "Mean time at 30.0 °C = (33.1 s + 34.0 s + 32.5 s) ÷ 3 = 33.2 s" or "Mean of 18, 27 and 40 = (18 + 27 + 40) ÷ 3 = 28.3" as a '
                'relation between the condition, or the list\'s last value, and the computation |',
                '| Reading a check whose `detail` says "the law stated in" and "rule law-values" that fails while the line\'s arithmetic holds as two checks '
                'contradicting each other |',
                '| Expecting only the cells of a supplied table to be checked in a line of working |'):
        assert row in dossier, row
    for row in ('| `finding_missing` for a check of the condition, the list\'s last value or the item\'s number of a run that computes the named quantity',
                '| `formal_status_wrong` or `receipt_altered` for a law-values check that fails as a warning while the line\'s arithmetic check holds |'):
        assert row in inspection, row
    assert ('| `formal_status_wrong` or `receipt_altered` because stem-eq-1 of Example 39 fails while stem-eq-2 holds on the same line |' in examples
            and "| 39 | genuine, fault already named by the receipt | STEM formal check | none |" in examples)


def test_example_39_is_the_receipt_the_channel_gives():
    """Example 39's request and answer through the channel: the receipt carries the law-values check and the line's arithmetic, detail for
    detail, and the INT-SUBJ-004 that names the failed one on both claims; its verdict accuses nothing. Had the law been V = ε − Ir, the
    line would follow it: no law-values check, every check holding, no finding."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 39)
    assert table[39] == ("genuine, fault already named by the receipt", "none") and ex.type == "genuine, fault already named by the receipt."
    request = ex.value("/transfers/0/payload/user_input")
    claims = [ex.value(f"/transfers/1/payload/claims/{i}/claim_text") for i in range(2)]

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["stem-specialist"]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
        return hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")

    reply, rc = receipt("\n".join(claims))
    assert rc.status.value == ex.value("/transfers/1/receipt/status") == "ACCEPTED_WITH_FINDINGS"
    assert [c["claim_text"] for c in reply.payload["claims"]] == claims
    assert [(c["claim_id"], c["claim_role"]) for c in reply.payload["claims"]] == [
        (ex.value(f"/transfers/1/payload/claims/{i}/claim_id"), ex.value(f"/transfers/1/payload/claims/{i}/claim_role")) for i in range(2)]
    assert [fc.detail for fc in rc.formal_checks] == [ex.value(f"/transfers/1/receipt/formal_checks/{i}/detail") for i in range(2)]
    assert [(fc.constraint_id, list(fc.claim_ids), fc.satisfied, fc.formal_status) for fc in rc.formal_checks] == [
        (ex.value(f"/transfers/1/receipt/formal_checks/{i}/constraint_id"), ex.value(f"/transfers/1/receipt/formal_checks/{i}/claim_ids"),
         ex.value(f"/transfers/1/receipt/formal_checks/{i}/satisfied"), ex.value(f"/transfers/1/receipt/formal_checks/{i}/formal_status")) for i in range(2)]
    assert [(f.code, f.severity, list(f.claim_ids), f.message) for f in rc.findings] == [
        (ex.value("/transfers/1/receipt/findings/0/code"), ex.value("/transfers/1/receipt/findings/0/severity"),
         ex.value("/transfers/1/receipt/findings/0/claim_ids"), ex.value("/transfers/1/receipt/findings/0/message"))]
    assert rc.findings[0].formal_result_id == rc.formal_checks[0].formal_result_id
    assert list(rc.structural_findings) == [] == ex.value("/transfers/1/receipt/structural_findings")
    assert "rule law-values" in rc.formal_checks[0].detail and "the law stated in s1.1 at the values the line puts in" in rc.formal_checks[0].detail
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, right = receipt("\n".join(claims).replace("V = ε + Ir", "V = ε − Ir"))
    assert right.status.value == "ACCEPTED" and all(fc.satisfied for fc in right.formal_checks) and list(right.findings) == []
    assert not [fc for fc in right.formal_checks if "rule law-values" in fc.detail]
