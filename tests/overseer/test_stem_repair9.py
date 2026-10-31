"""STEM repair 9 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 40).

* the STEM probes of repair 9 (the ninth independent test's plants, each class with its clean control): rule part-answer (a correct
  check line or a line naming another quantity at the end of a part took the part's question words: the tester's three false
  INT-SUBJ-004), rule named-result (a wrong rearrangement evaluated for a quantity the request names), rule given-function (a Given of a
  function's value or of a function, neither checked nor named while the pack said every Given has one or the other), rule row-terms (a
  trial copied wrongly into a row's mean), rule decay-law (a decay over stated half-lives divided by their number), rule statistics (a
  wrong median in any form) and rule rounded-digits (a value restated at a rounding it is not written to);
* the STEM receipt cases T23au (the INT-SUBJ-004 of a failed named-result check dropped), T23av (a failed given-function check restated as
  holding), T23aw (a failed row-terms check reported as holding), T23ax (the ST-UNDEC-003 of an undefined Given function dropped), T23ay
  (a failed decay-law check restated as holding), T23az (the INT-SUBJ-004 of a failed rounded-digits check dropped) and T23ba (a failed
  statistics check restated as holding);
* the pack beside the code: D31's opening list one kind of relation to a bullet and its paragraphs one statement to a line (the ninth
  test found a 14,871-byte line and a 2,506-character I97 bullet), with the new readings, D32's ST-UNDEC-001 and ST-UNDEC-003 rows, I97,
  I98, the master prompt, the mistakes rows and Example 40, every new statement executed against the STEM front end and the example
  regenerated through the channel.
"""
from __future__ import annotations

import json
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
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402
from .test_stem_repair8 import _failing, _holds, _with  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-t13": "mathematics_aa", "bi-t13": "biology", "ess-t13": "ess", "ch-t13": "chemistry",
           "mai-t13": "mathematics_ai"}
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-9-test-key-0123456789abcdef"
#: the recorded working the pack's statements extend
PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PH_E = "from 9.9 V to 10.7 V."
MA_END = "Marks shown are a provisional allocation."
CH_R = "Two reminders."
PB_D = "32 h is 4 half-lives, so C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹."
BI_END = "which makes ATP. [1 spare]"
ES_A = "= 60.4% decrease [1]"


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def _rule(checks, rule: str) -> list:
    return [c for c in checks if f"rule {rule})" in c[2] or f"rule {rule};" in c[2]]


def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _new(tid: str, text: str) -> tuple[list, list]:
    """The checks (kind, status, statement) and the findings (code, message) ``text`` has beyond the recorded answer's."""
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


# ============================================================================================ the probes and the tamper cases
#: each plant of the ninth independent test (and of the shapes of its classes found closing them), with the code that must name it
REPAIR9_PROBES = {
    # rule part-answer: a change stated from a wrong value is still set against the part's answer
    "physics-part-answer-change-slip": ("INT-SUBJ-004",),
    # rule named-result
    "equations-named-result-rearranged": ("INT-SUBJ-004",), "equations-named-result-symbol": ("INT-SUBJ-004",),
    "equations-named-result-words": ("INT-SUBJ-004",), "givens-named-result-emf": ("INT-SUBJ-004",), "givens-named-result-stated": ("INT-SUBJ-004",),
    "givens-named-result-label": ("INT-SUBJ-004",),
    # rule given-function
    "givens-function-value": ("INT-SUBJ-004",), "givens-function": ("INT-SUBJ-004",), "givens-function-undefined": ("ST-UNDEC-003",),
    "givens-function-formula": ("INT-SUBJ-004",), "givens-function-value-bare": ("INT-SUBJ-004",), "givens-function-value-undefined": ("ST-UNDEC-003",),
    # rule row-terms
    "wrong_given-row-repeat": ("INT-SUBJ-004",), "wrong_given-row-repeat-bare": ("INT-SUBJ-004",), "wrong_given-row-other": ("INT-SUBJ-004",),
    # rule decay-law
    "formulas-decay-divided": ("INT-SUBJ-004",), "formulas-decay-factor": ("INT-SUBJ-004",),
    # rule statistics
    "maths-median-prose": ("INT-SUBJ-004",), "maths-median-column": ("INT-SUBJ-004",), "maths-median-list": ("INT-SUBJ-004",),
    "maths-median-even": ("INT-SUBJ-004",), "maths-range": ("INT-SUBJ-004",), "maths-mode": ("INT-SUBJ-004",), "maths-mean-list": ("INT-SUBJ-004",),
    "maths-statistic-unchecked": ("ST-UNDEC-001",), "maths-median-maa": ("INT-SUBJ-004",),
    # rule rounded-digits
    "precision-rounded-digits-which": ("INT-SUBJ-004",), "precision-rounded-digits-so": ("INT-SUBJ-004",),
    "precision-rounded-digits-finer": ("INT-SUBJ-004",), "precision-rounded-digits-prose": ("INT-SUBJ-004",),
    "precision-rounded-digits-symbol": ("INT-SUBJ-004",),
}
#: the correct writing of each, which must stay clean (the tester's three false INT-SUBJ-004 on correct physics working among them)
REPAIR9_CONTROLS = ("physics-part-answer-check-control", "physics-part-answer-lost-volts-control", "physics-part-answer-emf-words-control",
                    "physics-part-answer-symbol-control", "physics-part-answer-other-pd-control", "physics-part-answer-changed-current-control",
                    "equations-named-result-rearranged-control", "equations-named-result-words-control", "givens-function-value-control",
                    "givens-function-control", "givens-function-renamed-control", "givens-function-value-si-control",
                    "wrong_given-row-reordered-control", "formulas-decay-divided-control", "formulas-decay-power-two-control",
                    "maths-median-prose-control", "maths-median-column-control", "maths-median-list-control", "maths-median-even-control",
                    "maths-range-control", "maths-mode-control", "maths-mean-list-control", "maths-median-maa-control",
                    "precision-rounded-digits-which-control", "precision-rounded-digits-prose-control")
#: the tester's three controls that had a false INT-SUBJ-004 (u9d-fa-check-eps, u9d-fa-lost-volts, u9c-emf-chain)
TESTER_CONTROLS = ("physics-part-answer-check-control", "physics-part-answer-lost-volts-control", "physics-part-answer-emf-words-control")
#: the tester's plants named by nothing before (u9-eq-ph-r-eval, u9b-eq-r-value, u9b-eq-r-value-prose, the Given of v(1), u9-giv-ma-fn,
#: u9b-giv-ma-a, u9b-wg-ch-cell, u9-form-pb-div, the three medians, u9-prec-ess-sf, u9b-prec-so, u9b-prec-ph-3sf)
TESTER_PLANTS = ("equations-named-result-rearranged", "equations-named-result-symbol", "equations-named-result-words", "givens-function-value",
                 "givens-function", "givens-function-undefined", "wrong_given-row-repeat", "formulas-decay-divided", "maths-median-prose",
                 "maths-median-column", "maths-median-list", "precision-rounded-digits-which", "precision-rounded-digits-so",
                 "precision-rounded-digits-prose")


def test_every_plant_of_the_ninth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR9_PROBES) == len(REPAIR9_PROBES) + len(REPAIR9_CONTROLS) == 57
    assert {p.probe_id for p in SP.REPAIR9_PROBES} == set(REPAIR9_PROBES) | set(REPAIR9_CONTROLS)
    for pid, expected in REPAIR9_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR9_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(TESTER_CONTROLS) <= set(REPAIR9_CONTROLS) and set(TESTER_PLANTS) <= set(REPAIR9_PROBES)
    for cls in ("physics", "equations", "givens", "wrong_given", "formulas", "maths", "precision"):
        assert {p.kind for p in SP.REPAIR9_PROBES if p.fault_class == cls} == {"answer", "control"}, cls
    assert SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES and len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_9_tamper_cases_are_registered_on_their_targets():
    """T23au to T23ba, each on the probe that plants its fault (the suite runs them in tests/overseer/test_stem_completion.py, each on its
    planted copy, the planted copy clean)."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23au", "finding_missing"), ("T23av", "receipt_altered"), ("T23aw", "formal_status_wrong"), ("T23ax", "finding_missing"),
                      ("T23ay", "receipt_altered"), ("T23az", "finding_missing"), ("T23ba", "receipt_altered")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # STEM repair 10 (design section 41) appended T23bg to givens, T23bc to wrong_given, T23bd to formulas and T23bf to maths, after these
    # STEM repair 11 (design section 42) appended T23bo, T23bp, T23bm, T23bl, T23bj and T23bk after these, and STEM repair 12 (design
    # section 43) T23bq and T23br to maths
    assert SP.TAMPER_CASES["equations"][-3:] == ("T23au", "T23bo", "T23bp") and SP.TAMPER_CASES["givens"][-4:] == ("T23av", "T23ax", "T23bg", "T23bm")
    assert SP.TAMPER_CASES["wrong_given"][-3:] == ("T23aw", "T23bc", "T23bl") and SP.TAMPER_CASES["formulas"][-3:] == ("T23ay", "T23bd", "T23bj")
    assert SP.TAMPER_CASES["precision"][-1] == "T23az" and SP.TAMPER_CASES["maths"][-5:] == ("T23ba", "T23bf", "T23bk", "T23bq", "T23br")


@pytest.mark.timeout(1500)
def test_the_repair_9_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the tester's three false INT-SUBJ-004 among them), no forbidden code."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR9_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid, expected in REPAIR9_PROBES.items():
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
        assert set(expected) & set(r["named_by"]), (pid, r["named_by"])
    for pid in REPAIR9_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ the pack beside the code
@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_the_stem_rules_are_written_one_point_to_a_line():
    """The ninth test found D31's list of what the branch checks one line of 14,871 bytes and an I97 bullet of 2,506 characters, which a
    cheapest-tier agent is unlikely to read reliably. D30 to D32, I91 to I98 and the master prompt now hold no line longer than 1,300
    characters but a table row (a Markdown row is one line), and no table row longer than 1,500; D31's opening list is one kind of
    relation to a bullet."""
    dossier = _pack_text("02-dossier.md")
    regions = {"D30 to D32": _section(dossier, "- **D30 ", "\n## "), "I91 to I98": _section(_pack_text("03-inspection.md"), "- **I91 ", "\n## "),
               "the master prompt": _pack_text("master_prompt.txt")}
    for name, text in regions.items():
        for line in text.split("\n"):
            limit = 1500 if line.lstrip().startswith("|") else 1300
            assert len(line) <= limit, (name, len(line), line[:120])
    head = _section(dossier, "- **D31 ", "\n\n  Each one is an entry of the receipt's `formal_checks`.")
    kinds = [line for line in head.split("\n") if line.startswith("  - ")]
    assert len(kinds) >= 20 and len(head.split("\n")[0]) < 400, kinds
    for kind in ("  - **arithmetic links**", "  - **substitutions**:", "  - **algebra steps**:", "  - **unit conversions**:",
                 "  - **results restated in prose**:", "  - **Given values** against the request", "  - **a statistic** stated for the values",
                 "  - **truth tables**"):
        assert any(line.startswith(kind) for line in kinds), kind


def test_d31_states_rule_part_answer_as_the_code_decides_it(d31):
    for words in ('The value stated for a quantity that a part\'s question names is that part\'s answer, the last value the part computes that is no '
                  'check and names no other quantity', '("As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.")',
                  '("The lost volts are 4.14 A × 0.50 Ω = 2.07 V.")', 'so "… rises, from 9.9 V to 10.7 V" is still set against its 9.9 V, rule '
                  'part-answer'):
        assert words in d31, words
    for line in ("As a check, ε = 9.93 V + 4.14 A × 0.50 Ω = 12.0 V.", "The lost volts are 4.14 A × 0.50 Ω = 2.07 V."):
        checks, _f = _task("ph-t13", _with("ph-t13", PH_C, PH_C + "\n" + line))
        change = [c for c in _rule(checks, "named-change") if "'9.9 V'" in c[2]]
        assert len(change) == 1 and _holds(change[0][0], change[0][1]) and "[claims s3.2, s5.4]" in change[0][2], (line, change)
        got, _f = _new("ph-t13", _with("ph-t13", PH_C, PH_C + "\n" + line))
        assert not _failing(got), (line, got)


def test_d31_states_rule_named_result_and_the_request_s_names_as_the_code_decides_them(d31):
    for words in ('"rule named-result": the line names the quantity by the prose right before its value ("So the internal resistance is (12 V + 9.93 '
                  'V)/4.14 A = 5.3 Ω." fails against "internal resistance 0.50 ohm"), by its label ("Internal resistance: r = (12 V + 9.93 V)/4.14 A = '
                  '5.3 Ω") or by its lone symbol',
                  '("r = (12 V + 9.93 V)/4.14 A = 5.3 Ω" and "So r = 5.3 Ω." after "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", which put the request\'s '
                  '0.50 ohm for r)', '("a battery of emf 12 V" names the emf)', 'words that end in a preposition and an article right before the value ("of a", '
                  '"in the") name nothing ("the horizontal component of a 10 N force", "the power dissipated in the 6.0 ohm resistor")'):
        assert words in d31, words
    for line in ("So the internal resistance is (12 V + 9.93 V)/4.14 A = 5.3 Ω.", "Internal resistance: r = (12 V + 9.93 V)/4.14 A = 5.3 Ω",
                 "r = (12 V + 9.93 V)/4.14 A = 5.3 Ω", "So r = 5.3 Ω."):
        got, f = _new("ph-t13", _with("ph-t13", PH_C, PH_C + "\n" + line))
        named = _rule(got, "named-result")
        assert [(k, s) for k, s, _d in named] == [("giv", "COUNTEREXAMPLE")] and "failure severity warning" in named[0][2] and f == [], (line, got, f)
        assert "the value the answer gives the internal resistance against the request's internal resistance" in named[0][2]
    got, _f = _new("ph-t13", _with("ph-t13", PH_C, PH_C + "\nSo the internal resistance is (12 V − 9.93 V)/4.14 A = 0.50 Ω."))
    assert [(k, s) for k, s, _d in _rule(got, "named-result")] == [("giv", "ENTAILED")] and not _failing(got)
    # the request names a quantity after a preposition, and nothing by words ending in a preposition and an article
    checks, _f = _decided("The emf is 9.0 V.", "physics", "A battery of emf 12 V drives a current through a resistor.")
    assert [(k, s) for k, s, d in checks if "rule named-given" in d] == [("giv", "COUNTEREXAMPLE")], checks
    checks, _f = _decided("The horizontal component is 10 N × cos 30° = 8.7 N.", "physics", "Find the horizontal component of a 10 N force at 30° to "
                          "the horizontal.")
    assert not [c for c in checks if "rule named-given" in c[2] or "rule named-result" in c[2]], checks


def test_d31_states_rule_given_function_as_the_code_decides_it(d31):
    for words in ('A Given of a function\'s value ("Given: v(1) = 4 m s⁻¹.", "Given: v(1) = 4.") is set against the request\'s function at the Given\'s '
                  'argument, a number however it is written ("v(1/2)", "v(−1)")', '("Given: v(1) = 300 cm s⁻¹." holds)',
                  'A Given function ("Given: v(t) = 6t − 2t².", "Given: v(t) = 4.", or "Given: v = 6t − 2t²." for the function\'s own symbol)',
                  '("Given: v(x) = 6x − 3x²." holds)', '"the request\'s function at the Given\'s argument, against the Given value"',
                  '"the Given function against the request\'s function"', '("Given: f(2) = 6.") is checked as the written arithmetic of the application',
                  '("So v(2) = 6(2) − 3(2)² = 0" after "Given: v(1) = 3." is the line\'s arithmetic alone)',
                  '("Given: a(t) = 6 − 4t.", "Given: a(1) = 0.")', '("Given: v(t + 1) = 4 m s⁻¹.") or a unit ("v(1 s)")'):
        assert words in d31, words
    end = MA_END
    for line, kind, status in (("Given: v(1) = 4 m s⁻¹.", "eq", "COUNTEREXAMPLE"), ("Given: v(1) = 4.", "eq", "COUNTEREXAMPLE"),
                               ("Given: v(1) = 300 cm s⁻¹.", "eq", "ENTAILED"), ("Given: v(1/2) = 2.25 m s⁻¹.", "eq", "ENTAILED"),
                               ("Given: v(−1) = −9.", "eq", "ENTAILED"), ("Given: v(t) = 6t − 2t².", "alg", "COUNTEREXAMPLE"),
                               ("Given: v(t) = 4.", "alg", "COUNTEREXAMPLE"), ("Given: v = 6t − 2t².", "alg", "COUNTEREXAMPLE"),
                               ("Given: v(x) = 6x − 3x².", "alg", "ENTAILED")):
        got, f = _new("maa-t13", _with("maa-t13", end, end + "\n" + line))
        assert [(k, s) for k, s, _d in got] == [(kind, status)] and f == [], (line, got, f)  # f: (code, message) pairs
        assert "(rule given-function)" in got[0][2] and "failure severity warning" in got[0][2], (line, got)
    for line in ("Given: a(t) = 6 − 4t.", "Given: a(1) = 0.", "Given: v(t + 1) = 4 m s⁻¹.", "Given: v(1 s) = 3 m s⁻¹."):
        got, f = _new("maa-t13", _with("maa-t13", end, end + "\n" + line))
        assert got == [] and [c for c, _m in f] == ["ST-UNDEC-003"], (line, got, f)


def test_d31_states_rules_row_terms_decay_law_statistics_and_rounded_digits_as_the_code_decides_them(d31):
    for words in ('("Mean time at 30.0 °C = (33.1 s + 43.0 s + 32.5 s) ÷ 3 = 36.2 s" fails against trial 2\'s 34.0, its arithmetic holding)',
                  '("Mean time at 30.0 °C = (33.1 s + 17.6 s + 32.5 s) ÷ 3 = 27.7 s" fails, the 17.6 being the 40.0 °C row\'s)',
                  '"At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹" fails (the law gives 50)',
                  '"… ÷ 32 = 50 counts min⁻¹" and "… ÷ 2⁵ = 50 counts min⁻¹" hold', 'the three medians of 61 fail (the median is 58)',
                  'a standard deviation, a variance, a quartile, a percentile, an interquartile range, and a mode the values do not have as one value, '
                  'are named ST-UNDEC-001, unchecked', '"= 60.4% decrease, which is 60.4% to 2 s.f.", ", so 60.4% to 2 s.f.", "To 3 s.f. the external '
                  'resistance is 2.4 Ω." and "To 3 s.f., R = 2.4 Ω." fail', '("60% to 2 s.f." and "4780 to the nearest ten euros" hold)'):
        assert words in d31, words
    for line, term in (("Mean time at 30.0 °C = (33.1 s + 43.0 s + 32.5 s) ÷ 3 = 36.2 s.", "'43.0 s'"),
                       ("Mean time at 30.0 °C = (33.1 s + 17.6 s + 32.5 s) ÷ 3 = 27.7 s.", "'17.6 s'")):
        got, f = _new("ch-t13", _with("ch-t13", CH_R, line + "\n\n" + CH_R))
        rows = _rule(got, "row-terms")
        assert [(k, s) for k, s, _d in rows] == [("giv", "COUNTEREXAMPLE")] and term in rows[0][2], (line, got)
    for line, status in (("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 5 = 320 counts min⁻¹.", "COUNTEREXAMPLE"),
                         ("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 32 = 50 counts min⁻¹.", "ENTAILED"),
                         ("At t = 40 h, 5 half-lives, C = 1600 counts min⁻¹ ÷ 2⁵ = 50 counts min⁻¹.", "ENTAILED")):
        got, _f = _new("ph-p7b", _with("ph-p7b", PB_D, PB_D + "\n" + line))
        assert [s for _k, s, _d in _rule(got, "decay-law")] == [status], (line, got)
    for line in ("The median of 18, 27, 40, 58, 80, 92 and 61 is 61.", "Median of 18, 27, 40, 58, 80, 92 and 61 = 61",
                 "Median uptake = 61 mm³ per g per hour"):
        got, _f = _new("bi-t13", _with("bi-t13", BI_END, BI_END + "\n" + line))
        assert [s for _k, s, _d in _rule(got, "statistics")] == ["COUNTEREXAMPLE"], (line, got)
    got, f = _new("bi-t13", _with("bi-t13", BI_END, BI_END + "\nThe standard deviation of 18, 27 and 40 is 9.0."))
    assert got == [] and [c for c, _m in f] == ["ST-UNDEC-001"], (got, f)
    for old, new, status in ((ES_A, "= 60.4% decrease, which is 60.4% to 2 s.f. [1]", "COUNTEREXAMPLE"),
                             (ES_A, "= 60.4% decrease, so 60.4% to 2 s.f. [1]", "COUNTEREXAMPLE"),
                             (ES_A, "= 60.4% decrease, which is 60% to 2 s.f. [1]", "ENTAILED")):
        got, _f = _new("ess-t13", _with("ess-t13", old, new))
        assert [s for _k, s, _d in _rule(got, "rounded-digits")] == [status], (new, got)
    for line, status in (("To 3 s.f. the external resistance is 2.4 Ω.", "COUNTEREXAMPLE"), ("To 3 s.f., R = 2.4 Ω.", "COUNTEREXAMPLE"),
                         ("To 3 s.f. the external resistance is 2.40 Ω.", "ENTAILED")):
        got, _f = _new("ph-t13", _with("ph-t13", PH_E, PH_E + "\n" + line))
        assert [s for _k, s, _d in _rule(got, "rounded-digits")] == [status], (line, got)


def test_d32_i97_i98_the_master_prompt_and_the_mistakes_rows_state_the_new_readings():
    dossier, inspection, prompt = _pack_text("02-dossier.md"), _pack_text("03-inspection.md"), _pack_text("master_prompt.txt")
    d32 = _section(dossier, "**D32 ", "\n## ")
    assert ('a statistic the branch does not form (a standard deviation, a variance, a quartile, a percentile, an interquartile range, or a mode the '
            'values do not have as one value: rule statistics, D31), a ratio set against a number ("4.0 : 6.0 = 0.67"); the reason is named and the '
            'relation is not checked |') in d32
    assert ('or it is a Given of a function\'s value or of a function that the request does not define, or that cannot be set against the request\'s '
            'function') in d32
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    for words in ("rule named-result (the value a line gives a quantity the request names, against the request's value of it)",
                  "rule given-function (a Given of a function's value or of a function, against the request's function)",
                  "rule row-terms (a term of a sum over a row's repeats, against the row's repeats)",
                  "rule decay-law (a value computed over a stated number of half-lives, against the decay law)",
                  "rule statistics (a median, a mode, a range or a mean the branch forms from the listed values or a supplied column, against the stated value)",
                  "rule rounded-digits (the place a stated rounding names, against the place the value is written to)",
                  "(rule part-answer)"):
        assert words in i97, words
    i98 = _section(inspection, "**I98 ", "\n## ")
    assert ("a stem_arithmetic or stem_algebra entry whose `detail` names rule given-function and quotes the Given (\"the request's function at the "
            "Given's argument, against the Given value: 'v(1) = 4 m s⁻¹'\": Examples, Example 40)") in i98
    assert ("or for f, g or h applied to a number the written arithmetic of the application of the function the request or the answer defines "
            "(\"the written arithmetic: 'f(2) = 6'\")") in i98
    for words in ("Some STEM checks set a value against what the answer did not write itself, each at severity warning, its `detail` naming its rule",
                  "(rule part-answer)", "and so is a Given of a function's value or of a function (\"Given: v(1) = 4 m s⁻¹.\", \"Given: v(t) = 6t − 2t².\")",
                  "(Dossier guide D31; Examples, Example 40)."):
        assert words in prompt, words
    for row in ("| Looking for a check whose `detail` begins \"stem_given\" for a Given of a function's value", "rule part-answer); the change is set against it",
                "(rule named-result) | D31 |", "(rule statistics); another statistic is ST-UNDEC-001 | D31, D32 |", "(rule rounded-digits) | D31 |",
                "(rule decay-law) | D31 |", "(rule row-terms) | D31 |"):
        assert row in dossier, row
    for row in ("| `finding_missing` for a Given of a function's value or of a function because no check's `detail` begins \"stem_given\" |",
                "| `formal_status_wrong` or `receipt_altered` for a statistics check because the answer wrote no working for its statistic |",
                "| `formal_status_wrong` or `receipt_altered` for a rounded-digits check that fails as a warning"):
        assert row in inspection, row
    examples = _pack_text("07-examples.md")
    assert ("| `finding_missing` for \"Given: v(1) = 4 m s⁻¹.\" because no check's `detail` begins \"stem_given\" |" in examples
            and "| 40 | genuine, fault already named by the receipt | STEM response receipt | none |" in examples)


def test_example_40_is_the_receipt_the_channel_gives():
    """Example 40's request and answer through the channel: the receipt carries the given-function check of m1.1 and the arithmetic of m2.1,
    detail for detail, and the INT-SUBJ-004 that names the failed one; its verdict accuses nothing. Had the Given stated v(1) = 3 m s⁻¹, every
    check would hold and the receipt would carry no finding."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 40)
    assert table[40] == ("genuine, fault already named by the receipt", "none") and ex.type == "genuine, fault already named by the receipt."
    request = ex.value("/transfers/0/payload/user_input")
    claims = [ex.value(f"/transfers/1/payload/claims/{i}/claim_text") for i in range(2)]

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Mathematics: Analysis and Approaches", task_type="short_answer",
                               selected_agent_ids=["stem-specialist"]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
        return hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")

    reply, rc = receipt("\n\n".join(claims))
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
    assert "(rule given-function)" in rc.formal_checks[0].detail and rc.formal_checks[0].detail.startswith("stem_arithmetic in claim m1.1:")
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, right = receipt("\n\n".join(claims).replace("v(1) = 4 m s⁻¹", "v(1) = 3 m s⁻¹"))
    assert right.status.value == "ACCEPTED" and all(fc.satisfied for fc in right.formal_checks) and list(right.findings) == []
    assert [fc.constraint_id for fc in right.formal_checks] == ["stem-eq-1", "stem-eq-2"]
