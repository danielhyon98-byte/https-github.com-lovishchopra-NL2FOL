"""STEM repair 5 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 36).

* the STEM probes of repair 5 (the fifth independent test's plants, each class with its clean control, and the shapes of the same
  classes found closing them);
* the STEM receipt cases T23aa (a bound-relation INT-SUBJ-001 dropped), T23ab (a failed part-value substitution restated as holding),
  T23ac (a failed prose-conversion check reported as holding), T23ad (a failed same-place restatement restated with the two
  half-widths added), T23ae (the ST-UNDEC-002 of a prose-headed run in a symbol with no value dropped), and, from the third pass,
  T23af (a failed rearranged-formula step restated as holding) and T23ag (the ST-UNDEC-001 of a ratio set against a number dropped);
* the pack beside the code: D31's new readings and the relations it says are left unread, D32's ST-UNDEC-002 row, I97, the master
  prompt and the mistakes rows executed against the STEM front end, and Example 37 regenerated through the channel. The independent
  test found D31 saying "What the branch reads and cannot check, it names" while a relation the branch read had neither a check nor an
  ST code: every relation D31 now says is checked has its check, every one it says is named has its ST code, and every one it lists as
  silent has neither.
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

from epinoic_logic.branches import RouterHub  # noqa: E402
from epinoic_logic.engine import SolverConfig  # noqa: E402
from epinoic_logic.integrity import WorkPlan  # noqa: E402
from epinoic_logic.ir.schema import Problem  # noqa: E402
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-5-test-key-0123456789abcdef"
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-p7b": "mathematics_aa", "mai-t13": "mathematics_ai", "ess-t13": "ess", "ch-t13": "chemistry",
           "cs-t13": "computer_science"}
PH_D = "= 16.4 W, so 16 W"
CH_END = "so I cannot give one yet."
CS_END = "Next step: trace"
PB_D = "A measured rate would be about 120"


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


# ============================================================================================ the probes and the tamper cases
#: each plant of the fifth independent test (and of the shapes of its classes found closing them), with the code that must name it
REPAIR5_PROBES = {
    "equations-rearranged-wrong": ("INT-SUBJ-001",), "equations-rearranged-then-slip": ("INT-SUBJ-001",), "physics-reused-symbol": ("INT-SUBJ-001",),
    "rounding-own-chain": ("INT-SUBJ-001",), "wrong-given-prose-power": ("INT-SUBJ-001",), "arithmetic-prose-lost-volts": ("INT-SUBJ-001",),
    "receipts-unknown-after-number": ("ST-UNDEC-002",), "units-prose-conversion": ("INT-SUBJ-001",), "units-prose-conversion-bracket": ("INT-SUBJ-001",),
    "rounding-stated-symbol": ("INT-SUBJ-001",), "rounding-stated-prose": ("INT-SUBJ-001",), "arithmetic-percent-of-cell": ("INT-SUBJ-001",),
    "physics-reused-headless": ("INT-SUBJ-001",), "physics-reused-part-result": ("INT-SUBJ-001",), "wrong-given-prose-power-then": ("INT-SUBJ-001",),
    "receipts-unknown-prose-head": ("ST-UNDEC-002",), "units-prose-verb": ("INT-SUBJ-001",), "units-prose-bracket-or": ("INT-SUBJ-001",),
    "rounding-bracket-precision": ("INT-SUBJ-001",), "rounding-sf-no-comma": ("INT-SUBJ-001",),
    # the second pass over the classes
    "equations-rearranged-solving-wrong": ("INT-SUBJ-001",), "arithmetic-prose-lost-volts-equal": ("INT-SUBJ-001",), "units-prose-which-equals": ("INT-SUBJ-001",),
    "units-prose-semicolon": ("INT-SUBJ-001",), "wrong-given-measured-sixteenth": ("INT-SUBJ-004",),
    # the third pass over the classes
    "equations-rearranges-to-wrong": ("INT-SUBJ-001",), "equations-or-form-wrong": ("INT-SUBJ-001",), "equations-ie-form-wrong": ("INT-SUBJ-001",),
    "maths-inverse-swap-step": ("INT-SUBJ-001",), "physics-reused-prose-named": ("INT-SUBJ-001",), "rounding-prose-value": ("INT-SUBJ-001",),
    "receipts-ratio-number": ("ST-UNDEC-001",), "receipts-applied-unknown": ("ST-UNDEC-002",), "units-prose-to-unit": ("INT-SUBJ-001",),
}
#: the correct writing of each, which must stay clean (the false errors and warnings of the independent test among them)
REPAIR5_CONTROLS = ("equations-rearranged-formula-control", "equations-rearranging-control", "equations-rearranged-current-control",
                    "equations-rearranged-value-control", "physics-reused-symbol-control", "physics-reused-symbol-vi-control", "rounding-consequence-control",
                    "wrong-given-prose-power-control", "arithmetic-prose-lost-volts-control", "equations-prose-solved-control", "units-prose-conversion-control",
                    "units-prose-range-control", "rounding-stated-symbol-control", "rounding-stated-coarser-control", "precision-percent-of-cell-control",
                    "precision-percent-sign-control", "precision-ratio-of-cells-control", "equations-rearranged-product-control",
                    "equations-rearranged-difference-control", "physics-reused-headless-control", "physics-reused-part-result-control",
                    "rounding-count-after-condition-control", "rounding-count-after-order-control", "equations-prose-reused-control", "units-prose-verb-control",
                    "rounding-bracket-precision-control", "precision-ratio-to-cell-control", "precision-percent-by-division-control",
                    "precision-plus-minus-percent-control",
                    # the second pass over the classes
                    "equations-rearranged-subject-control", "arithmetic-prose-lost-volts-equal-control", "units-prose-which-equals-control",
                    "precision-inline-correction-control", "precision-upper-bound-control", "precision-share-by-hundred-control",
                    # the third pass over the classes
                    "equations-rearranges-to-control", "maths-inverse-swap-control", "physics-reused-prose-named-control",
                    "physics-reused-head-other-part-control", "physics-reused-inline-control", "wrong-given-prose-asked-control", "rounding-own-value-control",
                    "rounding-part-of-it-control", "rounding-prose-value-control", "precision-raw-processed-ratio-control", "precision-measured-named-control",
                    "units-prose-to-unit-control")
#: the independent test's four false findings on correct working, and its false warning: each now a clean control
TESTER_CONTROLS = ("equations-rearranged-formula-control", "equations-rearranged-current-control", "physics-reused-symbol-control", "rounding-consequence-control",
                   "precision-percent-of-cell-control")


def test_every_plant_of_the_fifth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR5_PROBES) == len(REPAIR5_PROBES) + len(REPAIR5_CONTROLS) == 81
    assert {p.probe_id for p in SP.REPAIR5_PROBES} == set(REPAIR5_PROBES) | set(REPAIR5_CONTROLS)
    for pid, expected in REPAIR5_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR5_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert set(TESTER_CONTROLS) <= set(REPAIR5_CONTROLS)
    assert SP.probe("receipts-unknown-after-number").forbidden == ("ST-PARSE-001",)  # the magnification reading, never again
    # STEM repair 6 (design section 37) appended its 49 probes after these, STEM repair 7 (design section 38) its 41 after those and
    # STEM repair 8 (design section 39) its 62 after those: repair 5's stay at the same positions
    assert SP.PROBES[222:303] == SP.REPAIR5_PROBES and SP.PROBES[303:352] == SP.REPAIR6_PROBES and SP.PROBES[352:393] == SP.REPAIR7_PROBES
    assert SP.PROBES[393:455] == SP.REPAIR8_PROBES and SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_5_tamper_cases_are_registered_on_their_targets():
    """T23aa drops a bound-relation INT-SUBJ-001 (r7/ph-t13), T23ab restates a failed part-value substitution as holding (r7/ph-t13),
    T23ac reports a failed prose-conversion check as holding (r7/ch-t13), T23ad restates a failed same-place restatement with the two
    half-widths (r7/ph-t13), T23ae drops the ST-UNDEC-002 of a prose-headed run in a symbol with no value (r7/ph-t13); the suite runs
    them in tests/overseer/test_stem_completion.py, each on its planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23aa", "finding_missing"), ("T23ab", "receipt_altered"), ("T23ac", "formal_status_wrong"), ("T23ad", "receipt_altered"),
                      ("T23ae", "finding_missing"), ("T23af", "receipt_altered"), ("T23ag", "finding_missing")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    assert "T23aa" in SP.TAMPER_CASES["wrong_given"] and "T23ab" in SP.TAMPER_CASES["physics"] and "T23ac" in SP.TAMPER_CASES["units"]
    assert "T23ad" in SP.TAMPER_CASES["rounding"] and "T23ae" in SP.TAMPER_CASES["receipts"]
    # the third pass: T23af restates a failed rearranged-formula step as holding, T23ag drops the ST-UNDEC-001 of a ratio set against a number;
    # STEM repair 7 (design section 38) appended T23al to the equations class and T23am to the receipts class, after these, and STEM repair
    # 11 (design section 42) T23bo and T23bp to the equations class
    assert SP.TAMPER_CASES["equations"] == ("T23d", "T23af", "T23al", "T23au", "T23bo", "T23bp") and SP.TAMPER_CASES["receipts"][-3:] == ("T23ae", "T23ag", "T23am")


@pytest.mark.timeout(1200)
def test_the_repair_5_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing
    and the dossier showing it, every control clean (the independent test's four false errors and its false warning among them), no
    forbidden code."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR5_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid in REPAIR5_PROBES:
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
    for pid in REPAIR5_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ the pack beside the code
def _decided(text: str, profile: str, request: str = None, data: tuple = ()):
    from epinoic_logic.engine.policies import policy_config, policy_limits
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.stem import build_document, clear_document_cache
    from epinoic_logic.stem.checks import build_checks
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.description) for pc in plan.checks]
    return checks, [(f.code, f.message) for f in list(doc.findings) + list(plan.findings)]


def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _beyond(tid: str, text: str):
    """The checks and findings ``text`` has beyond the recorded answer's (kind, status, statement head)."""
    def key(c):
        return (c[0], c[1], c[2].split(" [claims")[0])
    checks, findings = _task(tid, text)
    base, base_f = _task(tid, R7[tid]["response_text"])
    left = [key(c) for c in base]
    out = []
    for c in checks:
        if key(c) in left:
            left.remove(key(c))
        else:
            out.append(c)
    bf = [c for c, _m in base_f]
    new_f = []
    for c, _m in findings:
        if c in bf:
            bf.remove(c)
        else:
            new_f.append(c)
    return out, new_f


def _with(tid: str, old: str, new: str) -> str:
    text = R7[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _after(tid: str, anchor: str, line: str, sep: str = "\n") -> str:
    return _with(tid, anchor, anchor + sep + line)


def _status(got: list, kind: str) -> list[str]:
    return [st for k, st, _d in got if k == kind]


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_rule_part_value_as_the_code_decides_it(d31):
    for words in ('"As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W" after "P = … = 16.4 W"', '"As a check, I²R = (1.655 A)² × 6.0 Ω = 16.4 W"',
                  '"The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A." before "P = I²R = (1.655 A)² × 6.0 Ω": rule part-value',
                  'A value the part\'s prose names only by the stated quantity\'s words is no such value, since it may restate the other part\'s quantity'):
        assert words in d31, words
    for line in ("As a check, P = I²R = (1.655 A)² × 6.0 Ω = 16.4 W.", "As a check, I²R = (1.655 A)² × 6.0 Ω = 16.4 W."):
        got, f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        assert _status(got, "sub") == ["ENTAILED"] and f == [] and "rule part-value" in [d for k, _s, d in got if k == "sub"][0], (line, got)
    part_d = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"
    got, f = _beyond("ph-t13", _with("ph-t13", part_d, "The current in it is 9.93 V ÷ 6.0 Ω = 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"))
    assert _status(got, "sub") == ["ENTAILED"] and f == []
    # what D31 says of a value the prose only states: set against the stated values, and it fails
    got, _f = _beyond("ph-t13", _with("ph-t13", part_d, "The current in it is 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W"))
    assert _status(got, "sub") == ["COUNTEREXAMPLE"]
    got, _f = _beyond("ph-t13", _after("ph-t13", PH_D, "As a check, P = I²R = (1.565 A)² × 6.0 Ω = 14.7 W."))
    assert _status(got, "sub") == ["COUNTEREXAMPLE"]


def test_d31_states_rule_bound_relation_and_the_equations_it_leaves_as_the_code_reads_them(d31):
    for words in ('"The battery\'s power output is 12 V × I = 60 W", like "P = 12 V × I = 60 W", rule bound-relation',
                  'after "is", "are", "was", "were", "equals" or "equal" (also "is then", "is therefore", "is equal to", "is given by")',
                  '("…, giving a current of 1.65 A")',
                  '"The power in it is I² × 6.0 Ω = 16.4 W" after "P = … = 16.4 W": that is an equation for the symbol in this part',
                  '"So 12 V × I = 60 W."', '"The energy is 0.5 × k × 0.04 = 1.0 J." when its statement does not go on to solve it: ST-UNDEC-002'):
        assert words in d31, words
    for line, status in (("The battery's power output is 12 V × I = 60 W.", "UNSATISFIABLE"), ("The battery's power output is 12 V × I = 49.7 W.", "SATISFIABLE"),
                         ("The power output of the battery is then 12 V × I = 60 W.", "UNSATISFIABLE"),
                         ("The lost volts equal 0.50 Ω × I = 3.0 V.", "UNSATISFIABLE"), ("The lost volts are equal to 0.50 Ω × I = 2.07 V.", "SATISFIABLE"),
                         ("The battery's power output is given by 12 V × I = 60 W.", "UNSATISFIABLE")):
        got, _f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        assert _status(got, "sub") == [status] and "rule bound-relation" in [d for k, _s, d in got if k == "sub"][0], (line, got)
    # every equation D31 lists as unread: neither a check nor an ST code
    for line in ("So 12 V × I = 60 W.", "The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A.", "The power is 16.4 W = I² × 6.0 Ω, giving a current of 1.65 A.",
                 "The power in it is I² × 6.0 Ω = 16.4 W.", "The equation is 12 V × I = 60 W."):
        got, f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        assert not [x for x in got if x[0] == "sub"] and f in ([], ["ST-SCOPE-001"]), (line, got, f)
    got, f = _beyond("ph-t13", _after("ph-t13", PH_D, "The energy is 0.5 × k × 0.04 = 1.0 J."))
    assert got == [] and f == ["ST-UNDEC-002"]


def test_d31_states_rearrangements_conversions_roundings_and_restatements_as_the_code_reads_them(d31):
    for words in ('after "P = V²/R" and "From P = V²/R, R = V²/P." or "V² = P × R", "P = (9.93 V)² / 6.0 Ω" is checked against P = V²/R',
                  'or after "is", "equals", "is equal to", "is equivalent to", "is the same as", "converts to" or "is converted to", or after a comma and '
                  '"about", when the restated value ends its clause', '"55.0 cm³; that is 0.0550 dm³", "55.0 cm³, which equals 0.0550 dm³"',
                  '"Solving for R, R = P/V²" after "P = V²/R" fails',
                  '"The volume of 55.0 cm³ is 0.0550 dm³."', '"2.0 km is 500 m more than 1.5 km"', '"P = 16.4 W (3 s.f.)"',
                  'the full stop of "s.f." or "d.p." ends no sentence: "To 3 s.f. the power is 16.4 W"', 'rule adjacent-restatement',
                  '"With n = 1000 items, so 10 passes are needed." and "Also 2^10 = 1024 ≥ 1000, so 10 passes suffice." restate nothing',
                  'h is 0, and the `detail` says "rule same-place"'):
        assert words in d31, words
    for old, new in (("P = V²/R\n", "P = V²/R\nFrom P = V²/R, R = V²/P.\n"), ("P = V²/R\n", "P = V²/R\nV² = P × R\n"),
                     ("P = V²/R\n", "P = V²/R\nSolving for R, R = V²/P.\n"), ("P = V²/R\n", "P = V²/R\nMaking R the subject, R = V²/P.\n")):
        got, f = _beyond("ph-t13", _with("ph-t13", old, new))
        assert _status(got, "alg") == ["ENTAILED"] and f == [] and len(got) == 1, (new, got)
    for new in ("P = V²/R\nSolving for R, R = P/V².\n", "P = V²/R\nTransposing, R = P/V².\n"):
        got, _f = _beyond("ph-t13", _with("ph-t13", "P = V²/R\n", new))
        assert _status(got, "alg") == ["COUNTEREXAMPLE"], (new, got)
    for line, status in (("The volume of 55.0 cm³ is 0.0550 dm³.", "ENTAILED"), ("The volume of 55.0 cm³ is 0.550 dm³.", "COUNTEREXAMPLE"),
                         ("The mixture is 55.0 cm³ (or 0.550 dm³).", "COUNTEREXAMPLE"), ("The mixture is 55.0 cm³, that is 0.0550 dm³.", "ENTAILED"),
                         ("The mixture is 55.0 cm³; that is 0.0550 dm³.", "ENTAILED"), ("The mixture is 55.0 cm³, which equals 0.550 dm³.", "COUNTEREXAMPLE"),
                         ("The mixture is 55.0 cm³, about 0.06 dm³.", "ENTAILED"), ("The volume, 55.0 cm³, converts to 0.550 dm³.", "COUNTEREXAMPLE")):
        got, _f = _beyond("ch-t13", _after("ch-t13", CH_END, line, "\n\n"))
        assert _status(got, "cnv") == [status], (line, got)
    got, _f = _beyond("ch-t13", _after("ch-t13", CH_END, "A length of 2.0 km is 500 m more than 1.5 km.", "\n\n"))
    assert not [x for x in got if x[0] == "cnv"]
    for line, status in (("To 3 s.f., P = 16.5 W.", "COUNTEREXAMPLE"), ("To 2 s.f., P = 16 W.", "ENTAILED"), ("P = 16.5 W (3 s.f.)", "COUNTEREXAMPLE"),
                         ("To 3 s.f. the power is 16.4 W.", "ENTAILED"), ("To 3 s.f. the power is 16.5 W.", "COUNTEREXAMPLE")):
        got, _f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        assert _status(got, "res") == [status], (line, got)
    for line in ("With n = 1000 items, so 10 passes are needed.", "Also 2^10 = 1024 ≥ 1000, so 10 passes suffice.", "Also log₂ 1000 ≈ 9.97, so 10 passes."):
        got, f = _beyond("cs-t13", _with("cs-t13", CS_END, line + "\n\n" + CS_END))
        assert not [x for x in got if x[0] == "res"] and all(st in ("ENTAILED", "SATISFIABLE") for _k, st, _d in got) and f == [], (line, got)


def test_d31_states_the_processed_data_exemptions_and_the_per_cent_reading_as_the_code_reads_them(d31):
    for words in ('"±2% × 1620" too', '"1620/50 = 32.4 counts min⁻¹"', '"32.4/1620 = 0.020"', '"±2% × 1620 = ±32.4 counts min⁻¹"',
                  '"1620 × 2 ÷ 100 = 32.4 counts min⁻¹"', '("1620 + 32.4 = 1652.4 counts min⁻¹", "1620 × 1.02 = 1652.4 counts min⁻¹")',
                  '("C = (1620 − 20) × (1/2)⁴ = 100 counts min⁻¹")'):
        assert words in d31, words
    for line in ("2% of 1620 is 0.02 × 1620 = 32.4 counts min⁻¹.", "The uncertainty is 1620/50 = 32.4 counts min⁻¹.", "The fractional uncertainty is 32.4/1620 = 0.020.",
                 "The uncertainty in 1620 is ±2% × 1620 = ±32.4 counts min⁻¹.", "The ratio 1620/820 = 1.98 is about 2.",
                 "The uncertainty is 1620 × 2 ÷ 100 = 32.4 counts min⁻¹.", "The upper bound is 1620 + 32.4 = 1652.4 counts min⁻¹.",
                 "The upper bound is 1620 × 1.02 = 1652.4 counts min⁻¹.", "C = (1620 − 20) × (1/2)⁴ = 100 counts min⁻¹."):
        got, f = _beyond("ph-p7b", _with("ph-p7b", PB_D, line + "\n" + PB_D))
        assert not [x for x in got if x[0] == "giv"] and all(st in ("ENTAILED", "SATISFIABLE") for _k, st, _d in got) and f == [], (line, got, f)
    got, _f = _beyond("ph-p7b", _with("ph-p7b", PB_D, "C = 1620 counts min⁻¹ × (1/2)⁴ = 101 counts min⁻¹.\n" + PB_D))
    assert _status(got, "giv") == ["COUNTEREXAMPLE"]  # the raw cell for the corrected value is still named
    checks, _f = _decided("u = ±2% × 1620 = ±32.4 counts min⁻¹", "physics")
    assert [(k, st) for k, st, _d in checks] == [("eq", "ENTAILED")] and "as written, per cent as a fraction" in checks[0][2]


def test_d32_i97_the_master_prompt_and_the_mistakes_rows_say_what_the_code_does():
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert '| ST-UNDEC-002 | warning | a numeric relation depends on a symbol with no stated value ("E = 0.5 × k × 0.04 = 1.0 J", "The energy is 0.5 × k × 0.04 = 1.0 J."); it is not checked |' in d32
    inspection, prompt, dossier = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt"), _pack_text("02-dossier.md")
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    assert "or the value is a result its part computes with the symbol's dimension: Examples, Example 37" in i97
    assert 'and no restatement check for a bare number after "so" that follows no chain of its own statement or of the one before (rule adjacent-restatement)' in i97
    assert "or the value is a result its part computes with the symbol's dimension, and the signed status decides it (Inspection I97; Examples, Example 37)" in prompt
    assert '| Expecting a restatement check for a bare number after "so" that follows no chain of its own statement or of the one before |' in dossier
    assert '| Looking for an algebra step from a rearrangement to the line that evaluates the formula |' in dossier
    assert '| `finding_missing` for an equation about its part\'s own result in a symbol whose stated values stand in other parts' in inspection
    assert '| `finding_missing` for an equation the answer solves ("The power is 16.4 W = I² × 6.0 Ω, so I = 1.65 A") that no check names |' in inspection


def test_example_37_is_the_receipt_the_channel_gives():
    """Example 37's request and answer through the channel: the receipt carries the three checks the example shows, detail for detail,
    the part-value substitution among them, and no finding; its verdict accuses nothing. Had the answer substituted 1.565 A, the
    substitution would fail, named by its INT-SUBJ-001."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 37)
    assert table[37] == ("genuine", "none") and ex.type == "genuine."
    request = ex.value("/transfers/0/payload/user_input")
    claims = [ex.value(f"/transfers/1/payload/claims/{i}/claim_text") for i in range(3)]
    answer = "(b) [1]\n" + claims[0] + "\n\n(d) [2]\n" + claims[1] + "\n" + claims[2]

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["stem-specialist"]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
        return hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")

    reply, rc = receipt(answer)
    assert rc.status.value == ex.value("/transfers/1/receipt/status") == "ACCEPTED"
    assert [fc.detail for fc in rc.formal_checks] == [ex.value(f"/transfers/1/receipt/formal_checks/{i}/detail") for i in range(3)]
    assert [(fc.constraint_id, list(fc.claim_ids), fc.satisfied, fc.formal_status) for fc in rc.formal_checks] == [
        (ex.value(f"/transfers/1/receipt/formal_checks/{i}/constraint_id"), ex.value(f"/transfers/1/receipt/formal_checks/{i}/claim_ids"), True, "ENTAILED")
        for i in range(3)]
    assert list(rc.findings) == [] and list(rc.structural_findings) == [] == ex.value("/transfers/1/receipt/structural_findings")
    assert [c["claim_text"] for c in reply.payload["claims"]] == claims
    assert "rule part-value: I may be reused in this part for another quantity" in rc.formal_checks[1].detail
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, wrong = receipt(answer.replace("(1.655 A)² × 6.0 Ω = 16.4 W.", "(1.565 A)² × 6.0 Ω = 14.7 W."))
    assert ("stem-sub-1", False, "COUNTEREXAMPLE") in [(fc.constraint_id, fc.satisfied, fc.formal_status) for fc in wrong.formal_checks]
    assert ("INT-SUBJ-001", "error") in [(f.code, f.severity) for f in wrong.findings]


# ============================================================================================ the third pass, the pack beside the code
def test_d31_states_the_third_pass_readings_as_the_code_decides_them(d31):
    """Each statement the third pass added to D31, executed against the front end: the rearrangement before the formula's evaluation is
    a step from the formula whatever words state it, the inverse's swapped equation is no step, a reused symbol takes a value its
    part's prose names otherwise, another part's value of the line's quantity or a computation in its place (a single value no
    statement of its part gives still fails, and a value named only by the stated quantity's words is not taken), a prose relation that
    gives its part's asked quantity stays unread, a value after 'so' following its own statement's value or a part of it restates
    nothing, a prose value restated with a stated rounding is checked, a conversion to a unit the prose names is checked, a ratio of
    the raw cell to its processed value and a line naming the measured quantity are not read, a ratio set against a number is named
    ST-UNDEC-001, and a symbol written as applied that no definition makes a function is named ST-UNDEC-002."""
    for words in ('"This rearranges to R = P/V².", "P = V²/R, i.e. R = P/V²", "or R = P/V²" and "Equivalently, R = P/V²." fail when "P = (9.93 V)² / 6.0 Ω" follows',
                  '"Swap x and y: x = 2y + 1." after "y = 2x + 1", is no step', '"The current in the 6.0 Ω resistor is 1.655 A." (current, resistor;',
                  '("V = IR = 1.655 A × 6.0 Ω = 9.93 V" in part (d), V = 9.9 V stated in part (c))', '("P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 16.4 W")',
                  'as part (d)\'s first line, "P = VI = 9.93 V × 1.655 A = 16.4 W" fails against part (b)\'s I = 4.1 A',
                  '"The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W." in the part that asks for the power dissipated in the 6.0 ohm resistor',
                  '"So 4.4 W of it is lost as heat in the wires."', '"The power is 16.4 W, so 16 W to 2 s.f." holds and "The power is 16.4 W, so 17 W to 2 s.f." fails',
                  '"Converting 55.0 cm³ to dm³ gives 0.0550 dm³."', '"1620/1600 = 1.0125"', '"The measured rate fell by 1620 − 820 = 800 counts min⁻¹"',
                  '("The ratio of the resistances is 4.0 : 6.0 = 0.67.": ST-UNDEC-001)', 'so "The energy is ½k(0.20)² = 1.0 J." names k, ST-UNDEC-002'):
        assert words in d31, words
    part_d = "P = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W"
    for new in ("P = V²/R\nThis rearranges to R = P/V².\n", "P = V²/R, i.e. R = P/V²\n", "P = V²/R\nor R = P/V²\n", "P = V²/R\nEquivalently, R = P/V².\n"):
        got, _f = _beyond("ph-t13", _with("ph-t13", "P = V²/R\n", new))
        assert _status(got, "alg") == ["COUNTEREXAMPLE"] and "a rearrangement of the formula, which the next line evaluates" in got[0][2], (new, got)
    checks, findings = _decided("y = 2x + 1\nSwap x and y: x = 2y + 1.\nSo y = (x − 1)/2.", "mathematics_aa", "f(x) = 2x + 1. Find the inverse.")
    assert [(k, st) for k, st, _d in checks] == [("alg", "ENTAILED")] and "'y = (x − 1)/2'" in checks[0][2], checks
    for text, status in (("The current in the 6.0 Ω resistor is 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W", "ENTAILED"),
                         ("V = IR = 1.655 A × 6.0 Ω = 9.93 V\nP = V²/R\nP = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", "ENTAILED"),
                         ("The current in it is 1.655 A.\nP = I²R = (1.655 A)² × 6.0 Ω = 16.4 W, so 16 W", "COUNTEREXAMPLE"),
                         ("P = VI = 9.93 V × 1.655 A = 16.4 W, so 16 W", "COUNTEREXAMPLE")):
        got, _f = _beyond("ph-t13", _with("ph-t13", part_d, text))
        assert _status(got, "sub") == [status], (text, got)
    got, f = _beyond("ph-t13", _with("ph-t13", part_d, "P = I²R = (9.93 V ÷ 6.0 Ω)² × 6.0 Ω = 16.4 W, so 16 W"))
    assert not [x for x in got if x[0] == "sub"] and _status(got, "eq") == ["ENTAILED"] and f == [], (got, f)
    got, f = _beyond("ph-t13", _with("ph-t13", part_d, "The power in the 6.0 Ω resistor is 9.93 V × I = 16.4 W."))
    assert not [x for x in got if x[0] == "sub"] and f == [], (got, f)
    for line in ("So 4.4 W of it is lost as heat in the wires.",):
        got, f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        assert not [x for x in got if x[0] == "res"] and f == [], (line, got)
    got, f = _beyond("ph-p7b", _with("ph-p7b", PB_D, "The measured rate at t = 0 h is 1620 counts min⁻¹, so the corrected rate is 1600 counts min⁻¹.\n" + PB_D))
    assert not [x for x in got if x[0] == "res"] and f == [], (got, f)
    for line, status in (("The power is 16.4 W, so 16 W to 2 s.f.", "ENTAILED"), ("The power is 16.4 W, so 17 W to 2 s.f.", "COUNTEREXAMPLE")):
        got, _f = _beyond("ph-t13", _after("ph-t13", PH_D, line))
        res = [x for x in got if x[0] == "res" and "against the value the prose states right before it" in x[2]]
        assert [st for _k, st, _d in res] == [status], (line, got)
    for line, status in (("Converting 55.0 cm³ to dm³ gives 0.0550 dm³.", "ENTAILED"), ("Converting 55.0 cm³ to dm³ gives 0.550 dm³.", "COUNTEREXAMPLE")):
        got, _f = _beyond("ch-t13", _after("ch-t13", CH_END, line, "\n\n"))
        assert _status(got, "cnv") == [status], (line, got)
    for line in ("The ratio 1620/1600 = 1.0125.", "The measured rate fell by 1620 − 820 = 800 counts min⁻¹ in 8 h."):
        got, f = _beyond("ph-p7b", _with("ph-p7b", PB_D, line + "\n" + PB_D))
        assert not [x for x in got if x[0] == "giv"] and f == [], (line, got, f)
    got, f = _beyond("ph-t13", _after("ph-t13", PH_D, "The ratio of the resistances is 4.0 : 6.0 = 0.67."))
    assert got == [] and f == ["ST-UNDEC-001"]
    got, f = _beyond("ph-t13", _after("ph-t13", PH_D, "The energy is ½k(0.20)² = 1.0 J."))
    assert got == [] and f == ["ST-UNDEC-002"]


def test_d32_and_the_mistakes_rows_say_what_the_third_pass_does():
    dossier = _pack_text("02-dossier.md")
    d32 = _section(dossier, "**D32 ", "\n## ")
    assert 'a ratio set against a number ("4.0 : 6.0 = 0.67"); the reason is named and the relation is not checked |' in d32
    assert ('| Reading a step whose `detail` says "a rearrangement of the formula, which the next line evaluates" as a step from the wrong relation |'
            in dossier)
    i97 = _section(_pack_text("03-inspection.md"), "**I97 ", "\n- **I98")
    assert "or a value its part's prose states for a quantity named otherwise, another part's value of the quantity the line computes, or a computation" in i97
    assert "that line is the formula's substitution, and the rearrangement is the step from the formula" in i97
