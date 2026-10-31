"""STEM repair 6 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 37).

* the STEM probes of repair 6 (the sixth independent test's plants, each class with its clean control): a Given written in prose,
  a symbol reused in a part with a value the request states that the part names nowhere, a unit written after a compact fraction,
  and the gates NAND, NOR and XNOR;
* the STEM receipt cases T23ah (the INT-SUBJ-004 of a failed prose Given check dropped), T23ai (a failed part-given substitution
  restated as holding), T23aj (a failed NAND evaluation reported as holding) and T23ak (an ST-DIM-001 the packs do not derive added on a
  relation read with a fraction's own unit);
* the pack beside the code: D31's Given paragraph, substitutions and Boolean gates, D32's ST-PARSE-002 and ST-DIM-001 rows, I95, I97,
  I98, the master prompt and the mistakes rows, executed against the STEM front end, and Example 38 regenerated through the channel.
  The independent test found D31, I98 and the master prompt saying every Given value has its check or ST-UNDEC-003 while a Given
  written in prose had neither (an agent's true ``finding_missing`` refuted), a reuse D31 did not describe, and gates the pack did not
  mention: every statement below is what the code decides.
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
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402
from .test_stem_repair5 import _decided  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-6-test-key-0123456789abcdef"
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-p7b": "mathematics_aa", "mai-t13": "mathematics_ai", "bi-t13": "biology",
           "ch-t13": "chemistry", "cs-t13": "computer_science"}
PH_A = "(a) [2]\nFor resistors"
PH_D = "= 16.4 W, so 16 W"
BI_END = "which makes ATP. [1 spare]"
CH_END = "so I cannot give one yet."
CS_END = "Next step: trace"
MI_END = "Next step: rework (a)"
MB_K = "k = (ln 2)/8 h⁻¹  A1"


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


# ============================================================================================ the probes and the tamper cases
#: each plant of the sixth independent test (and of the shapes of its classes found closing them), with the code that must name it
REPAIR6_PROBES = {
    "givens-data-list": ("INT-SUBJ-004",), "givens-data-named": ("INT-SUBJ-004",), "givens-data-juxtaposed": ("INT-SUBJ-004",),
    "givens-given-copula": ("INT-SUBJ-004",), "givens-given-colon": ("INT-SUBJ-004",), "givens-value-of": ("INT-SUBJ-004",),
    "givens-we-know": ("INT-SUBJ-004",), "givens-known-concentration": ("INT-SUBJ-004",), "givens-list-items": ("INT-SUBJ-004",),
    "givens-prose-uncertainty": ("INT-SUBJ-004",), "givens-prose-percent": ("INT-SUBJ-004",), "receipts-prose-given-unset": ("ST-UNDEC-003",),
    "wrong-given-part-other-resistor": ("INT-SUBJ-004",), "wrong-given-part-internal": ("INT-SUBJ-004",), "wrong-given-part-current": ("INT-SUBJ-004",),
    "dimensions-fraction-unit-slip": ("INT-SUBJ-001",), "dimensions-fraction-unit-si-slip": ("INT-SUBJ-001",),
    "dimensions-fraction-rate-slip": ("INT-SUBJ-001",), "dimensions-fraction-both-wrong": ("ST-DIM-001",),
    "boolean-nand-eval": ("INT-SUBJ-001",), "boolean-nor-eval": ("INT-SUBJ-001",), "boolean-xnor-eval": ("INT-SUBJ-001",),
    "boolean-nor-identity": ("INT-SUBJ-001",), "boolean-nand-table": ("INT-SUBJ-001",), "boolean-xnor-table": ("INT-SUBJ-001",),
    "boolean-sheffer-identity": ("INT-SUBJ-001",), "receipts-gate-order": ("ST-PARSE-002",),
}
#: the correct writing of each, which must stay clean (the false ST-DIM-001 and INT-SUBJ-001 of the independent test among them)
REPAIR6_CONTROLS = ("givens-data-list-control", "givens-given-copula-control", "givens-given-colon-control", "givens-value-of-control",
                    "givens-we-know-control", "givens-known-concentration-control", "givens-list-items-control", "givens-prose-uncertainty-control",
                    "givens-clause-result-control", "givens-prose-percent-control", "wrong-given-part-current-control", "wrong-given-part-named-control",
                    "dimensions-fraction-unit-control", "dimensions-fraction-unit-si-control", "dimensions-fraction-rate-control",
                    "boolean-nand-eval-control", "boolean-nor-eval-control", "boolean-xnor-eval-control", "boolean-nor-identity-control",
                    "boolean-nand-table-control", "boolean-xnor-table-control", "boolean-sheffer-identity-control")


def test_every_plant_of_the_sixth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR6_PROBES) == len(REPAIR6_PROBES) + len(REPAIR6_CONTROLS) == 49
    assert {p.probe_id for p in SP.REPAIR6_PROBES} == set(REPAIR6_PROBES) | set(REPAIR6_CONTROLS)
    for pid, expected in REPAIR6_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR6_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    # every class of the four has its answers and its controls
    for cls in ("givens", "wrong_given", "dimensions", "boolean"):
        kinds = {p.kind for p in SP.REPAIR6_PROBES if p.fault_class == cls}
        assert kinds == {"answer", "control"}, cls
    # STEM repair 7 (design section 38) appended its 41 probes after these and STEM repair 8 (design section 39) its 62 after those:
    # repair 6's stay at the same positions
    assert SP.PROBES[303:352] == SP.REPAIR6_PROBES and SP.PROBES[352:393] == SP.REPAIR7_PROBES and SP.PROBES[393:455] == SP.REPAIR8_PROBES
    assert SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def test_the_repair_6_tamper_cases_are_registered_on_their_targets():
    """T23ah drops the INT-SUBJ-004 of a failed prose Given check (r7/ph-t13), T23ai restates a failed part-given substitution as holding
    (r7/ph-t13), T23aj reports a failed NAND evaluation as holding (r7/cs-t13), T23ak adds an ST-DIM-001 the packs do not derive on a
    relation read with a fraction's own unit (r7/ch-t13); the suite runs them in tests/overseer/test_stem_completion.py, each on its
    planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23ah", "finding_missing"), ("T23ai", "receipt_altered"), ("T23aj", "formal_status_wrong"), ("T23ak", "infrastructure")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # STEM repair 8 (design section 39) appended T23ap, T23aq and T23at to wrong_given, after T23ai; STEM repair 10 (design section 41)
    # appended T23bg to givens, T23bc to wrong_given and T23be to boolean, after these
    # STEM repair 11 (design section 42) appended T23bm and T23bl after these, and STEM repair 12 (design section 43) T23bs to boolean
    assert SP.TAMPER_CASES["givens"][-5:] == ("T23ah", "T23av", "T23ax", "T23bg", "T23bm")
    assert SP.TAMPER_CASES["wrong_given"][4:] == ("T23ai", "T23ap", "T23aq", "T23at", "T23aw", "T23bc", "T23bl")
    assert SP.TAMPER_CASES["boolean"] == ("T23b", "T23d", "T23i", "T23w", "T23aj", "T23be", "T23bs") and SP.TAMPER_CASES["dimensions"] == ("T23h", "T23ak")


@pytest.mark.timeout(1200)
def test_the_repair_6_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing and
    the dossier showing it, every control clean (the independent test's false ST-DIM-001 and INT-SUBJ-001 on correct working among
    them), no forbidden code."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR6_PROBES)
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid in REPAIR6_PROBES:
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
    for pid in REPAIR6_CONTROLS:
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ the pack beside the code
def _task(tid: str, text: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, PROFILE[tid], R7[tid]["question"], data)


def _beyond(tid: str, text: str):
    """The checks (kind, status, statement) and the finding codes ``text`` has beyond the recorded answer's."""
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


def _place(tid: str, line: str) -> str:
    text = R7[tid]["response_text"]
    anchor = {"ph-t13": PH_A, "mai-t13": MI_END, "cs-t13": CS_END, "bi-t13": BI_END, "ch-t13": CH_END}[tid]
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, line + "\n\n" + anchor) if tid in ("ph-t13", "mai-t13", "cs-t13") else text.replace(anchor, anchor + "\n\n" + line)


def _with(tid: str, old: str, new: str) -> str:
    text = R7[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _given(got: list) -> list[tuple[str, str]]:
    """The Given checks among ``got``: (status, the value the check names)."""
    return [(st, d.split(" [claims")[0].split(": ", 1)[-1]) for k, st, d in got if k == "giv"]


def _holds(kind: str, status: str) -> bool:
    return status == ("UNSATISFIABLE" if kind == "bool" else "ENTAILED") or (kind != "bool" and status == "SATISFIABLE")


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_rule_prose_given_as_the_code_decides_it(d31):
    """D31's Given paragraph, executed: every example of a data list, of the list a "Given:" line opens and of a Given clause is a Given
    value with its check (or its ST-UNDEC-003), named by its item's words; only a Given clause's first clause is given; "Data" with no
    colon heads none; an uncertainty in prose takes its unit; rule named-given in prose; an amount after a currency sign and a numeral
    with a thousands space are never read in part."""
    for words in ('or a value the prose of such a statement gives a quantity (rule prose-given): every value of a statement whose head ends with a colon '
                  'within three more words ("Data: emf 15 V, internal resistance 0.50 Ω.", "Given: the mass of seeds is 12 g.", "Given: mass of seeds: 12 g.", '
                  '"Given: 15.0 cm³ of acid.", "Known: the acid is 2.0 mol dm⁻³.", "Known values: …") and of the list a line "Given:" opens ("- mass of seeds 10 g")',
                  'in "Given that the emf is 12 V, the current is 4.1 A." only the emf is a Given: the current is the statement\'s own result',
                  '"Data" with no colon heads no Given clause ("Data analysis rewards …")',
                  'a value right after "at", "when", "whenever" or "if" is the condition another value of the item is stated under, never a Given',
                  'an uncertainty written "±0.5 °C" or "+/-0.5 °C" in prose takes the unit written after it',
                  '(rule named-given: "Data: emf 12 V, internal resistance 6.0 Ω." fails against the internal resistance 0.50 ohm, though the request states a '
                  '6.0 ohm resistor); its check\'s `detail` says "rule prose-given"',
                  'An amount after a currency sign and a numeral written with a thousands space are never read in part (below).'):
        assert words in d31, words
    for tid, line, expected in (
            ("ph-t13", "Data: emf 15 V, internal resistance 0.50 Ω.", [("COUNTEREXAMPLE", "'15 V'"), ("ENTAILED", "'0.50 Ω'")]),
            ("bi-t13", "Given: the mass of seeds is 12 g.", [("COUNTEREXAMPLE", "'12 g'")]),
            ("bi-t13", "Given: mass of seeds: 12 g.", [("COUNTEREXAMPLE", "'12 g'")]),
            ("ch-t13", "Given: 15.0 cm³ of acid.", [("COUNTEREXAMPLE", "'15.0 cm³'")]),
            ("ch-t13", "Known: the acid is 2.0 mol dm⁻³.", [("ENTAILED", "'2.0 mol dm⁻³'")]),
            ("ph-t13", "Known values: emf 12 V.", [("ENTAILED", "'12 V'")]),
            ("bi-t13", "Given:\n- mass of seeds 10 g\n- five repeats at each temperature", [("ENTAILED", "'10 g'")]),
            ("bi-t13", "We know the mass of seeds was 10 g.", [("ENTAILED", "'10 g'")]),
            ("ph-t13", "Given that the emf is 12 V, the current is 4.1 A.", [("ENTAILED", "'12 V'")]),
            ("ch-t13", "Given: thermometer uncertainty ±0.5 °C.", [("ENTAILED", "'±0.5 °C'")]),
            ("ch-t13", "Given: thermometer uncertainty +/-0.5 °C.", [("ENTAILED", "'+/-0.5 °C'")]),
            ("ph-t13", "Data: emf 12 V, internal resistance 6.0 Ω.", [("ENTAILED", "'12 V'"), ("COUNTEREXAMPLE", "'6.0 Ω'")]),
            ("mai-t13", "Data: interest rate 3.6% per year, principal €4000.", [("ENTAILED", "'3.6%'")]),
    ):
        got, f = _beyond(tid, _place(tid, line))
        assert _given(got) == expected and all("rule prose-given" in d for k, _s, d in got if k == "giv") and f == [], (line, got, f)
    got, _f = _beyond("ph-t13", _place("ph-t13", "Data: emf 12 V, internal resistance 6.0 Ω."))
    assert "rule named-given" in [d for k, st, d in got if k == "giv" and st == "COUNTEREXAMPLE"][0]
    got, f = _beyond("mai-t13", _place("mai-t13", "Data: interest rate 3.6% per year, principal 4 000 euros."))
    assert _given(got) == [("ENTAILED", "'3.6%'")] and f == ["ST-PARSE-001"], (got, f)
    for line in ("Data analysis rewards records of an emf of 15 V.", "The emf is 15 V here."):
        # no Given: no check says "rule prose-given". STEM repair 9: the request's "a battery of emf 12 V" names the emf, so the 15 V the
        # prose states for it is set against the request's emf (rule named-given) and fails, and nothing else is planned or named
        got, f = _beyond("ph-t13", _place("ph-t13", line))
        assert [(k, st) for k, st, _d in got] == [("giv", "COUNTEREXAMPLE")] and f == [], (line, got, f)
        assert "rule named-given" in got[0][2] and "rule prose-given" not in got[0][2] and "'15 V'" in got[0][2], (line, got)
    # the condition right after "at" is never a Given; the value it is stated under is checked against the supplied table's row
    got, f = _beyond("bi-t13", _place("bi-t13", "Given: the oxygen uptake at 30 °C is 85 mm³ per g per hour."))
    assert _given(got) == [("COUNTEREXAMPLE", "'85 mm³ per g per hour'")] and f == [], (got, f)
    # every Given value has its check or its ST-UNDEC-003 (D31, I98)
    got, f = _beyond("bi-t13", _place("bi-t13", "Given: the volume of water is 25.0 cm³."))
    assert got == [] and f == ["ST-UNDEC-003"]


def test_d31_states_rule_part_given_as_the_code_decides_it(d31):
    """The reuse D31 describes, executed in ph-t13 (d), which asks for the power dissipated in the 6.0 ohm resistor: the part's own value
    and a value its working names before the line are read with no check; another value the request states fails at warning severity
    in a check of its own whose detail names rule part-given."""
    for words in ('Such a symbol substituted with a value the request states with its dimension is read for the symbol in that part, with no check, when the '
                  'part\'s question states that value ("P = (9.93 V)² / 6.0 Ω" in the part that asks for the power dissipated in the 6.0 ohm resistor), states '
                  'no value of that dimension, or the part\'s working states it before the line ("For comparison, the 4.0 Ω resistor dissipates P = (9.93 V)² / '
                  '4.0 Ω")',
                  'the symbol is checked at warning severity against its stated values, the values the question states and the readings of rule part-value, in a '
                  'check of its own whose `detail` names rule part-given: "P = (9.93 V)² / 4.0 Ω" or "P = (9.93 V)² / 0.50 Ω" in that part fails, INT-SUBJ-004'):
        assert words in d31, words
    base, _f = _task("ph-t13", R7["ph-t13"]["response_text"])
    assert not [d for _k, _s, d in base if "rule part-given" in d]  # '/ 6.0 Ω' (d), and r = 0.50 Ω in (c), whose question states no resistance
    got, f = _beyond("ph-t13", _with("ph-t13", PH_D, PH_D + "\nFor comparison, the 4.0 Ω resistor dissipates P = (9.93 V)² / 4.0 Ω = 24.7 W."))
    assert all(_holds(k, st) for k, st, _d in got) and not [d for _k, _s, d in got if "rule part-given" in d] and f == ["ST-SCOPE-001"], (got, f)
    for value, result in (("4.0 Ω", "24.7 W, so 25 W"), ("0.50 Ω", "197 W, so 200 W")):
        got, f = _beyond("ph-t13", _with("ph-t13", "P = (9.93 V)² / 6.0 Ω = 16.4 W, so 16 W", f"P = (9.93 V)² / {value} = {result}"))
        part_given = [(st, d) for k, st, d in got if k == "sub" and "rule part-given" in d]
        assert [st for st, _d in part_given] == ["COUNTEREXAMPLE"] and "failure severity warning" in part_given[0][1], (value, got)
        assert all(_holds(k, st) for k, st, d in got if "rule part-given" not in d) and f == [], (value, got, f)


def test_d31_states_the_boolean_gates_as_the_code_decides_them(d31):
    for words in ('and in the gates NAND, NOR and XNOR, also written ↑ or ⊼ for NAND and ↓ or ⊽ for NOR, each the negation of AND, OR or XOR, NOT binding '
                  'tighter than every one: "With A = 0 and B = 1, A NAND B = 1" holds and "With A = 0 and B = 0, A NOR B = 0" fails, "A NOR B = NOT (A OR B)" '
                  'holds and "A NOR B = NOT A OR NOT B" fails; a gate written beside another operator, or two NAND or two NOR, with no brackets has two '
                  'readings and is named ST-PARSE-002, never read one way: "A NAND B NAND C = 1", "A NAND B AND C = 0")',):
        assert words in d31, words
    for line, ok in (("With A = 0 and B = 1, A NAND B = 1.", True), ("With A = 0 and B = 0, A NOR B = 0.", False),
                     ("So A NOR B = NOT (A OR B).", True), ("So A NOR B = NOT A OR NOT B.", False),
                     ("So A ↑ B = NOT A OR NOT B.", True), ("So A ⊼ B = NOT (A AND B).", True), ("So A ↓ B = NOT A AND NOT B.", True),
                     ("So A ⊽ B = NOT (A OR B).", True), ("So NOT A NAND B = A OR NOT B.", True)):
        got, f = _beyond("cs-t13", _place("cs-t13", line))
        assert [(k, _holds(k, st)) for k, st, _d in got] == [("bool", ok)] and f == [], (line, got, f)
    for line in ("So A NAND B NAND C = 1.", "So A NAND B AND C = 0."):
        assert _beyond("cs-t13", _place("cs-t13", line)) == ([], ["ST-PARSE-002"]), line


def test_d32_rows_say_what_the_code_does():
    """D32's ST-PARSE-002 row names the gates' order, and its ST-DIM-001 row rule fraction-unit, each executed."""
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert ('| ST-PARSE-002 | warning | an expression has too many readings (an implicit multiplication, a unit or a symbol that can be read two ways, or a '
            'NAND, NOR or XNOR written beside another operator, or two NAND or two NOR, with no brackets: "A NAND B NAND C = 1"); it is not checked |') in d32
    for words in ('A unit written right after a fraction whose slash has no space on either side ("1/40 s⁻¹", "(ln 2)/8 h⁻¹") is the divisor\'s or the whole '
                  'fraction\'s: the relation is read, and checked, with the fraction\'s own unit when that gives its two sides one dimension and the divisor\'s '
                  'does not ("k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹", "The rate is 1/40 s⁻¹ = 0.025 s⁻¹": no finding, the check\'s `detail` naming rule fraction-unit), '
                  'so ST-DIM-001 is raised only when neither reading agrees ("1/40 s⁻¹ = 0.025 m"); with a space around the slash ("1 / 0.087 h⁻¹ = 11.5 h⁻¹") '
                  'or with ÷ the unit is the divisor\'s.',):
        assert words in d32, words
    got, f = _beyond("maa-p7b", _with("maa-p7b", MB_K, "k = (ln 2)/8 h⁻¹ = 0.0866 h⁻¹  A1"))
    eq = [(st, d) for k, st, d in got if k == "eq"]
    assert [st for st, _d in eq] == ["SATISFIABLE"] and "rule fraction-unit" in eq[0][1] and f == [], (got, f)
    for line, dim in (("The rate is 1/40 s⁻¹ = 0.025 s⁻¹.", []), ("The rate is 1/40 s⁻¹ = 0.025 m.", ["ST-DIM-001"])):
        got, f = _beyond("ch-t13", _place("ch-t13", line))
        assert f == dim and ([d for k, _s, d in got if "rule fraction-unit" in d] != []) == (dim == []), (line, got, f)
    for text, dim in (("1 / 0.087 h⁻¹ = 11.5 h⁻¹", ["ST-DIM-001"]), ("1 ÷ 40 s⁻¹ = 0.025 s⁻¹", ["ST-DIM-001"])):
        checks, findings = _decided(text, "physics")
        assert [c for c, _m in findings] == dim and not [d for _k, _s, d in checks if "rule fraction-unit" in d], text


def test_i95_i97_i98_and_the_master_prompt_say_what_the_code_does():
    inspection, prompt = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt")
    i95 = _section(inspection, "**I95 ", "\n- **I96")
    assert ("The gates NAND, NOR and XNOR (↑ or ⊼, ↓ or ⊽) are read as the negations of AND, OR and XOR, in identities, evaluations and truth tables alike; "
            "a gate written beside another operator, or two NAND or two NOR, with no brackets has two readings, and ST-PARSE-002 names it unchecked "
            "(Dossier guide D31, D32): no `finding_missing` for its missing check.") in i95
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    assert ("a symbol reused in its part with a value the request states, checked at severity warning in a check of its own (rule part-given), or read with "
            "no check where the part's question or its working names that value; a Given written in prose, checked as the same Given written with \"=\" "
            "(rule prose-given); and a relation read with the unit written after a fraction as the fraction's own, with no ST-DIM-001 (rule "
            "fraction-unit).") in i97
    i98 = _section(inspection, "**I98 ", "\n- **I99")
    assert ('or a value the prose gives a quantity in a statement whose head ends with a colon, "Data: emf 15 V, internal resistance 0.50 Ω.", "Given: the mass '
            'of seeds is 12 g.", "Given: 15.0 cm³ of acid.", in the list a line "Given:" opens, or in the first clause, up to the first comma, semicolon or colon, '
            'of a statement that begins "Given", "Known" or "We know" with no such colon, "We know the mass of seeds was 10 g."; never a value right after '
            '"at", "when", "whenever" or "if", the condition it is stated under)') in i98
    assert "A Given written in prose has its check like any other (Examples, Example 38)." in i98
    for words in ("One whose `detail` names rule part-given is a check of its own, at severity warning: the symbol is reused in its part with a value the "
                  "request states that neither the part's question nor its working names (Dossier guide D31).",
                  'A Given value is a value given with "=" in a statement that begins "Given", "Data", "Known" or "We know", or one its prose gives a quantity: '
                  'every one of a data list whose head ends with a colon ("Data: emf 15 V, internal resistance 0.50 Ω.", "Given: 15.0 cm³ of acid.") and of the '
                  'list a line "Given:" opens, and those of the first clause of a statement that begins "Given", "Known" or "We know" with no colon; never one '
                  'right after "at", "when", "whenever" or "if" (Dossier guide D31).',
                  "a Given written in prose has its check too (Examples, Example 38)."):
        assert words in prompt, words


def test_the_mistakes_rows_say_what_the_code_does():
    dossier, inspection = _pack_text("02-dossier.md"), _pack_text("03-inspection.md")
    for row in ('| Reading a prose value of a Given statement ("Data: emf 15 V", "Given: the mass of seeds is 12 g.", "Given: 15.0 cm³ of acid.") as no Given | It '
                'is a Given value (rule prose-given): its check, or an ST-UNDEC-003, names it like a Given written with "=" | D31 |',
                '| Expecting a Given check for a value right after "at", "when" or "if" in a Given statement, or for a value after the first comma of a Given '
                'clause with no colon ("Given that the emf is 12 V, the current is 4.1 A.") |',
                '| Reading a substitution whose `detail` names rule part-given as an error, or as unchecked |',
                '| Expecting ST-DIM-001 on "1/40 s⁻¹ = 0.025 s⁻¹" or "(ln 2)/8 h⁻¹ = 0.0866 h⁻¹" |',
                '| Expecting a check of a NAND, NOR or XNOR written beside another operator with no brackets | It has two readings: ST-PARSE-002 names it, and '
                'nothing is checked | D31, D32 |'):
        assert row in dossier, row
    for row in ('| Leaving a Given written in prose in a data list ("Data: emf 15 V, …", "Given: 15.0 cm³ of acid.") with neither a check nor an ST-UNDEC-003, '
                'because no "=" is written | A value the prose of a Given statement gives a quantity is a Given value (rule prose-given): the receipt lacks what '
                'the branch decided: `finding_missing` | I98, Dossier guide D31 |',
                '| `finding_missing` for a value right after "at", "when" or "if" in a Given statement, or after the first comma of a Given clause with no colon',
                '| `formal_status_wrong` or `receipt_altered` for a substitution whose `detail` names rule part-given because it fails as a warning |',
                '| `finding_missing` for an ST-DIM-001 on "1/40 s⁻¹ = 0.025 s⁻¹" |',
                '| `finding_missing` for a NAND, NOR or XNOR check where the gate stands beside another operator with no brackets | It has two readings; ST-PARSE-002 '
                'names it, and nothing is checked | I95 |'):
        assert row in inspection, row


def test_example_38_is_the_receipt_the_channel_gives():
    """Example 38's request and answer through the channel: the receipt carries the two Given checks of the Data list and the arithmetic,
    detail for detail, and the INT-SUBJ-004 that names the failed Given check; its verdict accuses nothing. Had the list stated the
    request's 12 V, every check would hold and the receipt would carry no finding."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 38)
    assert table[38] == ("genuine, fault already named by the receipt", "none") and ex.type == "genuine, fault already named by the receipt."
    request = ex.value("/transfers/0/payload/user_input")
    claims = [ex.value(f"/transfers/1/payload/claims/{i}/claim_text") for i in range(2)]

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["stem-specialist"]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
        return hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")

    reply, rc = receipt("\n\n".join(claims))
    assert rc.status.value == ex.value("/transfers/1/receipt/status") == "ACCEPTED_WITH_FINDINGS"
    assert [c["claim_text"] for c in reply.payload["claims"]] == claims
    assert [(c["claim_id"], c["claim_role"]) for c in reply.payload["claims"]] == [
        (ex.value(f"/transfers/1/payload/claims/{i}/claim_id"), ex.value(f"/transfers/1/payload/claims/{i}/claim_role")) for i in range(2)]
    assert [fc.detail for fc in rc.formal_checks] == [ex.value(f"/transfers/1/receipt/formal_checks/{i}/detail") for i in range(3)]
    assert [(fc.constraint_id, list(fc.claim_ids), fc.satisfied, fc.formal_status) for fc in rc.formal_checks] == [
        (ex.value(f"/transfers/1/receipt/formal_checks/{i}/constraint_id"), ex.value(f"/transfers/1/receipt/formal_checks/{i}/claim_ids"),
         ex.value(f"/transfers/1/receipt/formal_checks/{i}/satisfied"), ex.value(f"/transfers/1/receipt/formal_checks/{i}/formal_status")) for i in range(3)]
    assert [(f.code, f.severity, list(f.claim_ids), f.message) for f in rc.findings] == [
        (ex.value("/transfers/1/receipt/findings/0/code"), ex.value("/transfers/1/receipt/findings/0/severity"),
         ex.value("/transfers/1/receipt/findings/0/claim_ids"), ex.value("/transfers/1/receipt/findings/0/message"))]
    assert rc.findings[0].formal_result_id == rc.formal_checks[0].formal_result_id
    assert list(rc.structural_findings) == [] == ex.value("/transfers/1/receipt/structural_findings")
    assert "rule prose-given" in rc.formal_checks[0].detail and "rule named-given; rule prose-given" in rc.formal_checks[1].detail
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, right = receipt("\n\n".join(claims).replace("emf 15 V", "emf 12 V").replace("I = 15 V / (2.4 Ω + 0.50 Ω) = 5.2 A", "I = 12 V / (2.4 Ω + 0.50 Ω) = 4.1 A"))
    assert right.status.value == "ACCEPTED" and all(fc.satisfied for fc in right.formal_checks) and list(right.findings) == []
    assert [fc.constraint_id for fc in right.formal_checks] == ["stem-giv-1", "stem-giv-2", "stem-eq-1"]
