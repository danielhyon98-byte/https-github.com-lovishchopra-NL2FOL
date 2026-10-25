"""STEM repair 7 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 38).

* the STEM probes of repair 7 (the seventh independent test's plants, each class with its clean control): rule solved-law (a line that
  gives a symbol a value right after a law that states it but not on its own evaluates the law solved for it, never an algebra step
  from it: the tester's two false INT-SUBJ-001 on correct working), rules leibniz and prime-derivative (a derivative in any Leibniz form
  or as a primed letter applied to a bracket is named ST-UNDEC-001, and its value at a point is set against the answer's own formula of
  it) and rule finer-restatement (a value restated with a rounding finer than the chain's value is set against the chain's written
  arithmetic, at warning severity);
* the STEM receipt cases T23al (a failed solved-law substitution restated as holding), T23am (the ST-UNDEC-001 of a derivative dropped)
  and T23an (the INT-SUBJ-004 of a failed finer-restatement check dropped);
* the pack beside the code: D31's rule solved-law and the tolerance rule's finer restatement, D32's ST-UNDEC-001 and ST-ALG-001 rows,
  I97, the master prompt and the mistakes rows, every statement executed against the STEM front end. The independent test found D32
  saying ST-UNDEC-001 names a derivative while "v'(t)" and "d²v/dt²" had neither a check nor an ST code: every statement below is what
  the code decides.

STEM repair 11 (rule derivative, ``docs/OVERSEER_DESIGN.md`` section 42): a derivative of a polynomial the answer or the request defines is
set against the one the power rule forms, so the plants of a wrong derivative are named by the failed check (INT-SUBJ-001) and the right
ones are controls that must stay clean; a derivative of anything else ("dN/dt = −λN") stays named ST-UNDEC-001, never failed, and T23am
drops that ST code (on r7/p7b). The pack's statements below are the repair-11 texts, executed the same way.
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

from epinoic_logic.overseer.pack import installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-t13": "mathematics_aa"}
#: the recorded working the pack's examples rewrite
PH_PART_B = "ε = I(R + r), so I = ε/(R + r)\nI = 12 V / 2.9 Ω = 4.1 A"
PH_PART_D = "P = V²/R\nP = (9.93 V)² / 6.0 Ω"
PH_C = "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V"
PB_REARR = "T½ = ln 2/λ, so λ = ln 2/T½"
PB_PART_C = "T½ = ln 2/λ, so λ = ln 2/T½\nλ = 0.693/8.0 h = 0.087 h⁻¹"
MA_DIST = "Distance travelled = 8 m  A1"


def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


# ============================================================================================ the probes and the tamper cases
#: each plant of the seventh independent test (and of the shapes of its classes found closing them), with the code that must name it
REPAIR7_PROBES = {
    # rule solved-law: the faults the evaluation of a solved law still names
    "equations-law-sum-evaluation-slip": ("INT-SUBJ-001",), "equations-product-evaluation-wrong-given": ("INT-SUBJ-001",),
    "equations-product-value-wrong": ("INT-SUBJ-001",), "equations-squared-law-wrong-given": ("INT-SUBJ-004",),
    "givens-after-law-contradiction": ("INT-SUBJ-004",), "equations-amount-law-slip": ("INT-SUBJ-001",),
    # rules leibniz and prime-derivative, and since STEM repair 11 rule derivative: a wrong derivative of the answer's polynomial fails, a
    # derivative of anything else is named unchecked (never failed), a derivative's value against its formula
    "receipts-derivative-prime": ("INT-SUBJ-001",), "receipts-derivative-prime-premise": ("INT-SUBJ-001",),
    "receipts-derivative-second": ("INT-SUBJ-001",), "receipts-derivative-caret": ("INT-SUBJ-001",), "receipts-derivative-latex": ("INT-SUBJ-001",),
    "receipts-derivative-value": ("INT-SUBJ-001",), "receipts-derivative-letter": ("ST-UNDEC-001",),
    "maths-derivative-evaluation": ("INT-SUBJ-001",),
    # rule finer-restatement
    "rounding-finer-zero": ("INT-SUBJ-004", "INT-SUBJ-001"), "rounding-finer-digit": ("INT-SUBJ-004", "INT-SUBJ-001"),
    "rounding-finer-bracket": ("INT-SUBJ-004", "INT-SUBJ-001"), "rounding-finer-inline": ("INT-SUBJ-004", "INT-SUBJ-001"),
    "rounding-finer-prose": ("INT-SUBJ-004", "INT-SUBJ-001"), "rounding-finer-unit": ("INT-SUBJ-004", "INT-SUBJ-001"),
    "rounding-finer-constant": ("INT-SUBJ-004", "INT-SUBJ-001"), "rounding-finer-power": ("INT-SUBJ-004", "INT-SUBJ-001"),
}
#: the correct writing of each, which must stay clean (the tester's two false INT-SUBJ-001 among them)
REPAIR7_CONTROLS = ("equations-law-then-evaluation-control", "equations-law-same-line-control", "equations-law-sum-evaluation-control",
                    "equations-product-rearrangement-control", "equations-product-only-control", "equations-product-value-control",
                    "equations-squared-law-control", "equations-sum-law-control", "equations-amount-law-control", "equations-given-after-law-control",
                    "rounding-finer-control", "rounding-finer-inline-control", "rounding-finer-prose-control", "rounding-finer-unit-control",
                    "rounding-finer-constant-control", "rounding-finer-power-control",
                    # STEM repair 11 (rule derivative): the right derivatives of the answer's polynomial, checked and holding
                    "receipts-derivative-prime-correct", "receipts-derivative-second-correct", "maths-derivative-evaluation-correct")
#: a derivative of what is no polynomial the answer or the request defines: named unchecked, never failed
DERIVATIVE_NAMED = ("receipts-derivative-letter",)
#: STEM repair 11 (rule derivative): the wrong derivatives of the answer's polynomial, in every notation, failed by the power rule's check
DERIVATIVE_DECIDED = ("receipts-derivative-prime", "receipts-derivative-prime-premise", "receipts-derivative-second", "receipts-derivative-caret",
                      "receipts-derivative-latex", "receipts-derivative-value")


def test_every_plant_of_the_seventh_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR7_PROBES) == len(REPAIR7_PROBES) + len(REPAIR7_CONTROLS) == 41
    assert {p.probe_id for p in SP.REPAIR7_PROBES} == set(REPAIR7_PROBES) | set(REPAIR7_CONTROLS)
    for pid, expected in REPAIR7_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR7_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    # a derivative outside the power rule is named unchecked, never failed: each such probe forbids the failure codes
    for pid in DERIVATIVE_NAMED:
        assert SP.probe(pid).forbidden == ("INT-SUBJ-001", "INT-SUBJ-004"), pid
    # STEM repair 11: a wrong derivative of the answer's polynomial is failed (an error), and nothing is forbidden
    for pid in DERIVATIVE_DECIDED:
        assert SP.probe(pid).expected == ("INT-SUBJ-001",) and SP.probe(pid).forbidden == (), pid
    # the classes the three problems lie in have their answers and their controls (since STEM repair 11 a derivative has its controls too)
    for cls in ("equations", "rounding", "receipts", "maths"):
        assert {p.kind for p in SP.REPAIR7_PROBES if p.fault_class == cls} == {"answer", "control"}, cls
    # STEM repair 8 (design section 39) appended its 62 probes after these, and STEM repair 11 (design section 42) its 35 after repair 10's:
    # repair 7's stay at the same positions
    assert SP.PROBES[352:393] == SP.REPAIR7_PROBES and SP.PROBES[393:455] == SP.REPAIR8_PROBES and SP.PROBES[455:512] == SP.REPAIR9_PROBES
    assert SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_7_tamper_cases_are_registered_on_their_targets():
    """T23al restates the failed solved-law substitution as holding (r7/p7b), T23am drops the ST-UNDEC-001 of a derivative (since STEM repair
    11 one the branch does not check, "dN/dt = −λN", on r7/p7b: a derivative of the answer's polynomial is checked now), T23an drops the
    INT-SUBJ-004 of a failed finer-restatement check (r7/ph-t13); the suite runs them in tests/overseer/test_stem_completion.py, each on its
    planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23al", "receipt_altered"), ("T23am", "finding_missing"), ("T23an", "finding_missing")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # STEM repair 8 (design section 39) appended T23as to the rounding class, after T23an, and STEM repair 10 (design section 41) T23bh;
    # STEM repair 11 (design section 42) T23bo and T23bp to the equations class; STEM repair 12 (design section 43) T23bt to rounding
    assert SP.TAMPER_CASES["equations"] == ("T23d", "T23af", "T23al", "T23au", "T23bo", "T23bp")
    assert T.CASES and {c.name: c for c in T.CASES}["T23am"].targets == T.STEM_TARGETS
    assert SP.probe("receipts-derivative-letter").expected == ("ST-UNDEC-001",)
    assert SP.TAMPER_CASES["rounding"] == ("T23i", "T23ad", "T23an", "T23as", "T23bh", "T23bt")
    assert SP.TAMPER_CASES["receipts"][-1] == "T23am"


@pytest.mark.timeout(1200)
def test_the_repair_7_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the tester's two false INT-SUBJ-001 on correct working among them), no forbidden code;
    a finer restatement is named by its warning (INT-SUBJ-004), a derivative by ST-UNDEC-001 alone."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR7_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid in REPAIR7_PROBES:
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
        if pid.startswith("rounding-finer-"):
            assert "INT-SUBJ-004" in r["named_by"], (pid, r["named_by"])
    for pid in DERIVATIVE_NAMED:
        assert rows[pid]["named_by"] == ["ST-UNDEC-001"], (pid, rows[pid]["named_by"])
    for pid in DERIVATIVE_DECIDED:
        assert rows[pid]["named_by"] == ["INT-SUBJ-001"], (pid, rows[pid]["named_by"])
    for pid in REPAIR7_CONTROLS:
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


def _quoting(checks: list, text: str) -> list:
    """The checks whose statement quotes ``text``."""
    return [c for c in checks if f"'{text}" in c[2].split(" [claims")[0]]


def _holds(status: str) -> bool:
    return status in ("ENTAILED", "SATISFIABLE")


def _new_findings(tid: str, text: str) -> list[tuple[str, str]]:
    """The findings ``text`` has beyond the recorded answer's (a multiset difference)."""
    _c, findings = _task(tid, text)
    _b, base = _task(tid, R7[tid]["response_text"])
    return list((Counter(findings) - Counter(base)).elements())


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_rule_solved_law_as_the_code_decides_it(d31):
    """D31's algebra steps, executed: the line after a law that states its symbol but not on its own evaluates the law solved for it (its
    substitution checked, its detail saying "solved for", no step); a symbol with no stated value is set against the values substituted
    before; an equation in the symbol alone and a value solving a law whose other symbols are stated are steps as before; a value after a
    law with another unknown is no step; mathematics names the principal root; a Given statement is data."""
    for words in ('a line that gives a symbol a value by a written expression right after a law that states the symbol but not on its own, where a step '
                  'would be read, evaluates the law solved for that symbol by exact inverse operations and is never a step from it, rule solved-law: after '
                  '"ε = I(R + r)", "I = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A" is checked against I = ε/(R + r), after "T½ = ln 2/λ, so λT½ = ln 2", "λ = '
                  '0.693/8.0 h = 0.087 h⁻¹" against λ = ln 2/T½, and after "V² = PR", "P = (9.93 V)² / 6.0 Ω" against P = V²/R, each exactly as after that '
                  'formula stated, its `detail` saying the line evaluates the law "solved for" the symbol ("I = 12 V / 2.9 Ω = 4.1 A" is the evaluation '
                  'too, its arithmetic checked, as after I = ε/(R + r);',
                  'a symbol of the law with no stated value is set against the values substituted for it before the line ("ω = 2πf so f = 3.0/(2π)" '
                  'after "T = 2π/ω = 2π/4.0" fails)',
                  'Read as before: a law in which the symbol occurs twice or under a function, a law with no other symbol ("2x + 3 = 11" then "x = '
                  '(11 − 3)/2", a step), and a value alone after a law whose every other symbol has a stated value, the law\'s solution ("λ = 0.097 h⁻¹" '
                  'after "λT½ = ln 2" with T½ = 8.0 h stated fails as a step), while a value alone after a law with another symbol that has no stated '
                  'value is a value stated for the symbol, never a step from the law ("F = ma" then "a = 4.0 m s⁻²", F and m stated nowhere: as a step '
                  'it failed whatever the value)',
                  'in mathematics, solving for a squared symbol takes its non-negative square root, which ST-ALG-001 names when no domain restriction '
                  'is stated ("A = πr²" then "r = √(50/π) = 3.99")',
                  'and a Given statement (one that begins "Given", "Data", "Known" or "We know", or the list a line "Given:" opens) states data, '
                  'never a step from the relation before it ("Given: ε = 12 V." after "I = ε/(R + r)" is a Given value)'):
        assert words in d31, words
    # the three evaluations, each its solved law's substitution, holding, with no step
    for tid, text, line, name in (
            ("ph-t13", _with("ph-t13", PH_PART_B, "ε = I(R + r)\nI = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A"), "I = 12 V / (2.4 Ω + 0.50 Ω)", "I"),
            ("ph-p7b", _with("ph-p7b", PB_REARR, "T½ = ln 2/λ, so λT½ = ln 2"), "λ = 0.693/8.0 h", "λ"),
            ("ph-t13", _with("ph-t13", PH_PART_D, "V² = PR\nP = (9.93 V)² / 6.0 Ω"), "P = (9.93 V)² / 6.0 Ω", "P")):
        checks, _f = _task(tid, text)
        subs = [c for c in _quoting(checks, line) if c[0] == "sub"]
        assert len(subs) == 1 and _holds(subs[0][1]) and f"solved for '{name}'" in subs[0][2] and "rule solved-law" in subs[0][2], (line, subs)
        assert not [c for c in _quoting(checks, line) if c[0] == "alg"] and all(_holds(c[1]) for c in checks if c[0] != "bool"), (line, checks)
    # the tester's ph-t13 form: no step, its arithmetic checked and holding
    checks, _f = _task("ph-t13", _with("ph-t13", PH_PART_B, "ε = I(R + r)\nI = 12 V / 2.9 Ω = 4.1 A"))
    assert not _quoting(checks, "I = 12 V / 2.9 Ω") and [c[1] for c in _quoting(checks, "12 V / 2.9 Ω = 4.1 A")] == ["ENTAILED"], checks
    # a symbol with no stated value against the value substituted before
    checks, _f = _decided("T = 2π/ω = 2π/4.0 = 1.57 s and ω = 2πf so f = 3.0/(2π) = 0.48 Hz", "physics")
    bad = [c for c in checks if not _holds(c[1])]
    assert [c[0] for c in bad] == ["sub"] and "'f = 3.0/(2π)'" in bad[0][2] and "rule solved-law: ω has no stated value" in bad[0][2], checks
    # read as before: an equation in the symbol alone, a value solving a law whose other symbols are stated
    checks, _f = _decided("2x + 3 = 11\nx = (11 − 3)/2 = 4", "mathematics_aa")
    assert [c[1] for c in _quoting(checks, "x = (11 − 3)/2") if c[0] == "alg"] == ["ENTAILED"] and not [c for c in checks if "solved-law" in c[2]]
    checks, _f = _task("ph-p7b", _with("ph-p7b", PB_PART_C, "T½ = ln 2/λ, so λT½ = ln 2\nλ = 0.097 h⁻¹"))
    assert [c[1] for c in _quoting(checks, "λ = 0.097 h⁻¹") if c[0] == "alg"] == ["COUNTEREXAMPLE"], checks
    # a value after a law with another symbol stated nowhere is no step; with every other symbol stated, it is the step it was
    assert _decided("F = ma\na = 4.0 m s⁻²", "physics") == ([], [])
    checks, _f = _decided("F = 12 N\nm = 3.0 kg\nF = ma\na = 5.0 m s⁻²", "physics")
    assert [(c[0], c[1]) for c in checks] == [("alg", "COUNTEREXAMPLE")], checks
    # mathematics names the principal root of a solved square; physics takes the physical root with no finding
    checks, findings = _decided("A = πr²\nr = √(50/π) = 3.99", "mathematics_aa")
    assert [c for c, _m in findings] == ["ST-ALG-001"] and "rule solved-law" in findings[0][1] and all(_holds(c[1]) for c in checks), (checks, findings)
    checks, findings = _decided("A = πr²\nr = √(50/π) = 3.99", "physics")
    assert findings == [] and all(_holds(c[1]) for c in checks), (checks, findings)
    # a Given statement after a law, in each form D31 names: a Given value, never a step (the first three had failed as steps)
    for given in ("Given: ε = 12 V.", "Data: ε = 12 V.", "Known: ε = 12 V.", "We know ε = 12 V.", "Given:\n- ε = 12 V"):
        checks, _f = _task("ph-t13", _with("ph-t13", PH_PART_B, "I = ε/(R + r)\n" + given + "\nI = 12 V / 2.9 Ω = 4.1 A"))
        assert not [c for c in checks if c[0] == "alg" and "ε = 12 V" in c[2].split(" [claims")[0]], (given, checks)
        assert [c[1] for c in checks if c[0] == "giv" and "'12 V'" in c[2].split(" [claims")[0]] == ["ENTAILED"], (given, checks)


def test_the_tolerance_rule_states_rule_finer_restatement_as_the_code_decides_it(d31):
    """The tolerance rule's finer restatement, executed after ph-t13's 'V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V': 9.90 and 9.94 to three
    figures hold against 9.9 V and fail the check against the arithmetic (9.93) at warning severity; 9.93 holds both; two figures give no
    such check."""
    assert ('A value restated with a rounding the prose states that is finer than the place the chain\'s final value is written to states figures that '
            'value does not carry, so it has a second check, rule finer-restatement, at severity warning: it is set against the value the expression '
            'the chain\'s last "=" evaluates gives, read as written arithmetic is (its numerals as written; a carried result or a constant ranges over '
            'its interval, below), with h the stated rounding\'s alone (never less than half a unit in the restated value\'s last written digit) and '
            'τ 0') in d31
    assert ('After "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "To 3 s.f., V = 9.90 V." and "To three significant figures, V = 9.94 V." hold against 9.9 V '
            'and fail this check (the arithmetic gives 9.93), INT-SUBJ-004, while "To 3 s.f., V = 9.93 V." holds both; a rounding no finer than the '
            'final value\'s place ("To 2 s.f., V = 9.9 V.") has no such check.') in d31
    for line, value, finer_holds in (("To 3 s.f., V = 9.90 V.", "9.90 V", False), ("To three significant figures, V = 9.94 V.", "9.94 V", False),
                                     ("To 3 s.f., V = 9.93 V.", "9.93 V", True)):
        checks, _f = _task("ph-t13", _with("ph-t13", PH_C, PH_C + "\n" + line))
        res = [c for c in _quoting(checks, value) if c[0] == "res"]
        finer = [c for c in res if "rule finer-restatement" in c[2]]
        stated = [c for c in res if "rule finer-restatement" not in c[2]]
        assert len(finer) == 1 and "failure severity warning" in finer[0][2] and _holds(finer[0][1]) == finer_holds, (line, res)
        assert len(stated) == 1 and stated[0][1] == "ENTAILED", (line, res)
        assert all(_holds(c[1]) for c in checks if c not in finer), (line, checks)
    checks, _f = _task("ph-t13", _with("ph-t13", PH_C, PH_C + "\nTo 2 s.f., V = 9.9 V."))
    assert not [c for c in checks if "rule finer-restatement" in c[2]] and all(_holds(c[1]) for c in checks), checks


def test_d32_rows_say_what_the_code_does():
    """D32's ST-UNDEC-001 row names every derivative notation the branch reads; since STEM repair 11 (rule derivative) a polynomial's
    derivative is checked against the one the power rule forms (each notation executed: one check, holding when right, failing when wrong,
    no ST code), a derivative of what is no polynomial, or set equal to a number where it is no constant, is ST-UNDEC-001 'a derivative'
    with nothing failed, a derivative's value is set against the answer's formula of it, and a primed letter with no bracket is a symbol;
    its ST-ALG-001 row the principal root of rule solved-law."""
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert ('| ST-UNDEC-001 | warning | a relation outside the encodings, for example a derivative of what is no polynomial the answer or the request '
            'defines, or set equal to a number where it is no constant (the paragraph after this table), an integral,') in d32
    assert ('A derivative is read in Leibniz notation of any order ("dN/dt", "dθ/dt", `\\frac{dN}{dt}`, "d/dx (sin x)") or as a letter with primes '
            'written applied to a bracket ("θ′(t)"), rules leibniz and prime-derivative. A polynomial\'s derivative is checked (rule derivative, D31), '
            'unless it is set equal to a number where it is no constant ("dv/dt = 6" for v(t) = 6t − 3t², an equation in the variable to solve); a '
            'derivative of anything else is ST-UNDEC-001. A derivative\'s value at a point is set against a formula the answer states for that '
            'derivative, so "v\'(1) = 6 + 6(1) = 12" after "v\'(t) = 6 − 6t" fails; a primed letter with no bracket, "v\' = 2.0 m s⁻¹", is a symbol.') in d32
    assert ('| ST-ALG-001 | warning | a step takes only the non-negative square root and states no domain, or, in mathematics, a line evaluates a law '
            'solved for a squared symbol (rule solved-law, D31: "A = πr²" then "r = √(50/π) = 3.99") and states none; the algebra, or the substitution, '
            'is checked under that condition |') in d32
    base, _bf = _task("maa-t13", R7["maa-t13"]["response_text"])

    def added(relation: str):
        text = _with("maa-t13", MA_DIST, MA_DIST + "\n    Also " + relation)
        checks, _f = _task("maa-t13", text)
        return [c for c in checks if c not in base], _new_findings("maa-t13", text)

    # what is no polynomial, and a non-constant derivative set equal to a number: named unchecked, nothing failed
    for relation in ("dN/dt = −2N", "dθ/dt = 2", "θ′(t) = 2", "d/dx (sin x) = cos x", "$\\frac{dN}{dt} = -2N$", "dv/dt = 6"):
        checks, new = added(relation)
        assert [c for c, _m in new] == ["ST-UNDEC-001"] and "a derivative" in new[0][1] and checks == [], (relation, checks, new)
    # the answer's polynomial v(t) = 6t − 3t², in every notation the row names: one power-rule check, holding when right, failing when wrong
    for relation, right in (("dv/dt = 6 − 6t", True), ("d²v/dt² = −6", True), ("d^2v/dt^2 = −6", True), ("$\\frac{d^2v}{dt^2} = -6$", True),
                            ("v'(t) = 6 − 6t", True), ("v′(t) = 6 − 6t", True), ("v″(t) = −6", True), ("v'(t) = 6 + 6t", False),
                            ("d²v/dt² = 6", False), ("v″(t) = 6", False)):
        checks, new = added(relation)
        assert new == [] and [c[0] for c in checks] == ["alg"] and "rule derivative" in checks[0][2] and _holds(checks[0][1]) is right, \
            (relation, checks, new)
    # the derivative's value against the answer's own formula of it: the value fails, the formula holds, no ST code
    text = _with("maa-t13", MA_DIST, MA_DIST + "\n    Also v'(t) = 6 − 6t\n    v'(1) = 6 + 6(1) = 12")
    checks, _f = _task("maa-t13", text)
    assert [(c[0], c[1]) for c in checks if not _holds(c[1])] == [("eq", "COUNTEREXAMPLE")] and _quoting(checks, "v'(1) = 6 + 6(1)"), checks
    # the line's own formula is the one derivative check this text adds (the recorded part (a)'s 'a = dv/dt = 6 − 6t' has its own)
    assert [c[1] for c in checks if c[0] == "alg" and "rule derivative" in c[2] and c not in base] == ["ENTAILED"], checks
    assert _new_findings("maa-t13", text) == [], checks
    for relation in ("v' = 2.0 m s⁻¹", "v′ = 2.0 m s⁻¹"):
        assert _new_findings("maa-t13", _with("maa-t13", MA_DIST, MA_DIST + "\n    Also " + relation)) == [], relation


def test_i97_the_master_prompt_and_the_mistakes_rows_say_what_the_code_does():
    inspection, prompt, dossier = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt"), _pack_text("02-dossier.md")
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    for words in ('Nor accuse the absence of an algebra step from a law to the line right after it that evaluates the law solved for one of its symbols '
                  '(rule solved-law: that line is the solved law\'s substitution, its `detail` saying "solved for"), or a value restated more finely than '
                  'the chain\'s value that fails, at severity warning, the check against the chain\'s written arithmetic while it holds against the '
                  'chain\'s value (rule finer-restatement).',
                  # STEM repair 11 (rule derivative): a polynomial's derivative is checked; any other derivative is named, as before
                  '  - a derivative of what is no polynomial the answer or the request defines, in Leibniz notation of any order or as a letter with primes '
                  'written applied to a bracket ("dN/dt = −λN"), named ST-UNDEC-001 and not checked; a polynomial\'s derivative ("d²v/dt² = −6", '
                  '"v\'(t) = 6 − 6t") is set against the one the power rule forms (rule derivative), and a derivative\'s value at a point against a formula '
                  'the answer states for that derivative (Dossier guide D31, D32);'):
        assert words in i97, words
    assert ('A line that evaluates a law stated right before it solved for one of its symbols is that formula\'s substitution, never an algebra step '
            '(rule solved-law); a value restated with a rounding finer than the chain\'s value is also set against the chain\'s written arithmetic, at '
            'severity warning (rule finer-restatement); a derivative of a polynomial the answer or the request defines is set against the one the '
            'power rule forms (rule derivative), and any other derivative is named ST-UNDEC-001 and not checked (Dossier guide D31, D32).') in prompt
    for row in ('| Looking for an algebra step from a law to the line right after it that gives one of its symbols a value ("ε = I(R + r)", then "I = 12 '
                'V / 2.9 Ω = 4.1 A") | That line evaluates the law solved for the symbol (rule solved-law): its substitution is checked against that '
                'formula, its `detail` saying "solved for", and no step is read | D31 |',
                '| Reading a derivative of what is no polynomial ("dN/dt = −λN", "d/dx (sin x) = cos x") as checked, or expecting no check of a '
                'polynomial\'s derivative ("v\'(t) = 6 − 6t", "d²v/dt² = −6") | A polynomial\'s derivative is set against the one the power rule forms '
                '(rule derivative); any other derivative is outside the encodings, ST-UNDEC-001 naming it unchecked | D31, D32 |',
                '| Reading a restatement as holding because its rounding-cue check holds when its finer-restatement check fails | A value restated more '
                'finely than the chain\'s value states figures that value does not carry: rule finer-restatement sets it against the chain\'s written '
                'arithmetic, at severity warning (INT-SUBJ-004) | D31 |'):
        assert row in dossier, row
    for row in ('| `finding_missing` for an algebra step from a law to the line right after it that gives one of its symbols a value ("ε = I(R + r)", then '
                '"I = 12 V / 2.9 Ω = 4.1 A") | That line evaluates the law solved for the symbol (rule solved-law): its stem_substitution check is the '
                'check, and no step is read | I97, Dossier guide D31 |',
                '| `finding_missing` for a check of a derivative of what is no polynomial ("dN/dt = −λN") named by an ST-UNDEC-001 | Only a polynomial\'s '
                'derivative is checked (rule derivative): for any other the ST code is what the branch decided, and nothing is checked | I97, Dossier '
                'guide D32 |',
                '| `formal_status_wrong` or `receipt_altered` for a finer-restatement check that fails as a warning while the same restatement holds '
                'against the chain\'s value | Both checks are the branch\'s: the finer one sets the restated figures against the chain\'s written '
                'arithmetic, a reading at severity warning (INT-SUBJ-004) | I97, Dossier guide D31 |'):
        assert row in inspection, row
    # "dN/dt = −λN" and "d/dx (sin x) = cos x" as the rows quote them: a derivative named, nothing failed
    text = _with("ph-p7b", PB_PART_C, PB_PART_C + "\nThe decay law is dN/dt = −λN.")
    new = _new_findings("ph-p7b", text)
    assert [c for c, _m in new] == ["ST-UNDEC-001"] and "a derivative" in new[0][1], new
    base, _bf = _task("maa-t13", R7["maa-t13"]["response_text"])
    for relation, named in (("d/dx (sin x) = cos x", True), ("v'(t) = 6 − 6t", False), ("d²v/dt² = −6", False)):
        text = _with("maa-t13", MA_DIST, MA_DIST + "\n    Also " + relation)
        checks, _f = _task("maa-t13", text)
        added = [c for c in checks if c not in base]
        new = _new_findings("maa-t13", text)
        if named:  # outside the encodings: the ST code, no check
            assert [c for c, _m in new] == ["ST-UNDEC-001"] and added == [], (relation, added, new)
        else:  # the polynomial's derivative: the power rule's check, holding, no ST code
            assert new == [] and [(c[0], c[1]) for c in added] == [("alg", "ENTAILED")] and "rule derivative" in added[0][2], (relation, added, new)
