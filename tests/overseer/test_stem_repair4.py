"""STEM repair 4 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 35).

* the STEM probes of repair 4 (the fourth independent test's plants, each class with its clean control), and repair 3's control
  ``arithmetic-within-uncertainty-control`` rewritten to an uncertainty its stated rule gives (its old ``± 11`` contradicts that
  rule and is now the answer probe ``arithmetic-uncertainty-rule``);
* the STEM receipt cases T23w (a failed Boolean evaluation restated as an identity holding), T23x (a stated-uncertainty
  INT-SUBJ-004 dropped), T23y (a failed '±' Given-uncertainty check reported as holding) and T23z (an operand-precision τ
  restated as 1/100);
* the pack beside the code: D31's new readings, D32's ST-PARSE-001 row, I95, I98, the master prompt and the mistakes rows executed
  against the STEM front end, Example 36 regenerated through the channel, and an agent that follows I98 literally accusing nothing
  on the planted Givens the independent test's pack agent was refuted on (the pack and the code now agree).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
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
KEY = b"stem-repair-4-test-key-0123456789abcdef"
PROFILE = {"ph-t13": "physics", "ph-p7b": "physics", "maa-p7b": "mathematics_aa", "mai-t13": "mathematics_ai", "ess-t13": "ess", "ch-t13": "chemistry",
           "cs-t13": "computer_science"}


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


# ============================================================================================ the probes and the tamper cases
#: each plant of the fourth independent test (and of the classes found closing them), with the code that must name it
REPAIR4_PROBES = {
    "boolean-evaluation": ("INT-SUBJ-001",), "boolean-evaluation-and": ("INT-SUBJ-001",), "boolean-evaluation-setup": ("INT-SUBJ-001",),
    "physics-changed-value": ("INT-SUBJ-001",), "physics-changed-value-earlier-part": ("INT-SUBJ-001",), "rounding-changed-value": ("INT-SUBJ-001",),
    "givens-uncertainty-percent": ("INT-SUBJ-004",), "givens-uncertainty-percent-start": ("INT-SUBJ-004",), "givens-uncertainty-ascii": ("INT-SUBJ-004",),
    "givens-relative-uncertainty": ("INT-SUBJ-004",), "givens-central-uncertainty": ("INT-SUBJ-004",), "givens-after-formula": ("INT-SUBJ-004",),
    "givens-unread-span": ("ST-PARSE-001",), "rounding-unit-word": ("INT-SUBJ-001",), "rounding-unit-word-inline": ("INT-SUBJ-001",),
    "rounding-no-unit-word": ("INT-SUBJ-001",), "rounding-subunit": ("INT-SUBJ-001",), "units-row-value": ("INT-SUBJ-004",), "units-row-statement": ("INT-SUBJ-004",),
    "units-row-reaches": ("INT-SUBJ-004",), "wrong-given-row": ("INT-SUBJ-004",), "wrong-given-row-prose": ("INT-SUBJ-004",),
    "wrong-given-row-number": ("INT-SUBJ-004",), "precision-exact-carry": ("INT-SUBJ-001",), "precision-exact-carry-equal": ("INT-SUBJ-001",),
    "precision-stated-uncertainty": ("INT-SUBJ-004",), "arithmetic-uncertainty-rule": ("INT-SUBJ-004",), "arithmetic-exact-operands": ("INT-SUBJ-001",),
    "maths-geometric-slip": ("INT-SUBJ-001",), "maths-geometric-slip-1pct": ("INT-SUBJ-001",),
}
#: the correct writing of each, which must stay clean (the first nine were INT-SUBJ-001 false errors before the repair)
REPAIR4_CONTROLS = ("boolean-evaluation-control", "boolean-evaluation-and-control", "boolean-evaluation-not-control", "boolean-evaluation-xor-control",
                    "boolean-evaluation-or-control", "boolean-evaluation-setup-control", "physics-changed-value-control",
                    "physics-changed-value-rounded-control", "rounding-changed-value-control", "givens-uncertainty-percent-control",
                    "givens-uncertainty-percent-start-control", "givens-uncertainty-ascii-control", "givens-relative-uncertainty-control",
                    "givens-after-formula-control", "rounding-unit-word-control", "rounding-unit-word-inline-control", "rounding-subunit-control",
                    "units-row-value-control",
                    "units-row-value-si-control", "units-row-reaches-control", "wrong-given-row-control", "wrong-given-row-number-control",
                    "precision-exact-carry-control", "precision-stated-uncertainty-control", "maths-geometric-slip-control")


def test_every_plant_of_the_fourth_independent_test_is_a_probe_with_its_control():
    assert len(SP.REPAIR4_PROBES) == len(REPAIR4_PROBES) + len(REPAIR4_CONTROLS) == 55
    assert {p.probe_id for p in SP.REPAIR4_PROBES} == set(REPAIR4_PROBES) | set(REPAIR4_CONTROLS)
    for pid, expected in REPAIR4_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR4_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    assert SP.probe("givens-unread-span").forbidden == ("INT-SUBJ-004", "INT-SUBJ-001")  # the condition, never again failed as a Given
    # STEM repair 5 (design section 36) appended its 81 probes after these, STEM repair 6 (design section 37) its 49 after those, STEM
    # repair 7 (design section 38) its 41 after those and STEM repair 8 (design section 39) its 62 after those: repair 4's stay at the
    # same positions
    assert SP.PROBES[167:222] == SP.REPAIR4_PROBES and SP.PROBES[222:303] == SP.REPAIR5_PROBES and SP.PROBES[303:352] == SP.REPAIR6_PROBES
    assert SP.PROBES[352:393] == SP.REPAIR7_PROBES and SP.PROBES[393:455] == SP.REPAIR8_PROBES and SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677
    # repair 3's control keeps its id and its purpose with an uncertainty its stated rule gives; its old text is an answer probe now
    ctl, old = SP.probe("arithmetic-within-uncertainty-control"), SP.probe("arithmetic-uncertainty-rule")
    assert ctl.kind == "control" and ctl.edits == ((SP.PB, "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11.7"),)
    assert old.kind == "answer" and old.edits == ((SP.PB, "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11"),) and old.expected == ("INT-SUBJ-004",)


def test_the_repair_4_tamper_cases_are_registered_on_their_targets():
    """T23w rewrites a failed Boolean evaluation as an identity that holds (r7/cs-t13), T23x drops a stated-uncertainty INT-SUBJ-004
    (r7/p7b), T23y reports a failed '±3%' Given-uncertainty check as holding (r7/p7b), T23z restates an operand-precision τ as 1/100
    (r7/p7b); the suite runs them in tests/overseer/test_stem_completion.py, each on its planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23w", "receipt_altered"), ("T23x", "finding_missing"), ("T23y", "formal_status_wrong"), ("T23z", "receipt_altered")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    assert "T23w" in SP.TAMPER_CASES["boolean"] and "T23x" in SP.TAMPER_CASES["precision"]
    assert "T23y" in SP.TAMPER_CASES["givens"] and "T23z" in SP.TAMPER_CASES["arithmetic"]


@pytest.mark.timeout(1200)
def test_the_repair_4_probes_name_every_plant_and_keep_every_control_clean(tmp_path):
    """The probes on copies of the recorded answers the repository keeps: every plant named by its code with the overseer agreeing
    and the dossier showing it, every control clean, no forbidden code."""
    rnd = material_round(tmp_path / "rounds")
    doc = SP.run_probes(tmp_path / "probes", rnd.parent, probes=SP.REPAIR4_PROBES + (SP.probe("arithmetic-within-uncertainty-control"),))
    rows = {r["probe_id"]: r for r in doc["probes"]}
    for pid in REPAIR4_PROBES:
        r = rows[pid]
        assert r["outcome"] == "named" and r["overseer_agrees"] and r["dossier"]["finding"] and r["forbidden_raised"] == [], (pid, r)
    for pid in REPAIR4_CONTROLS + ("arithmetic-within-uncertainty-control",):
        assert rows[pid]["outcome"] == "clean", (pid, rows[pid].get("new_receipt_findings"), rows[pid].get("new_ovs_findings"))
    assert doc["gate"]["failing"] == []


# ============================================================================================ an agent that follows I98 literally
def _items(x) -> list:
    """A dossier list, or an example excerpt's nested form of one (a dict keyed by the index)."""
    if isinstance(x, dict):
        return [x[k] for k in sorted(x, key=int)]
    return list(x or [])


def _given_claims(t: dict) -> list[tuple[int, dict]]:
    return [(j, c) for j, c in enumerate(_items((t.get("payload") or {}).get("claims")))
            if isinstance(c, dict) and str(c.get("claim_text") or "").lstrip().startswith("Given")]


def _given_values(claim_text: str) -> list[str]:
    """The values a Given claim states, as I98 reads them: each part between commas, its value the text after its last '=' (a
    Given stated under a condition quotes its value, never the condition)."""
    body = claim_text.split(":", 1)[1] if ":" in claim_text else claim_text
    out = []
    for part in body.rstrip().rstrip(".").split(","):
        if "=" in part:
            out.append(part.rsplit("=", 1)[1].strip())
    return out


def _i98_missing(d: dict) -> list[tuple[dict, int, dict, str]]:
    """I98, read as a cheapest-tier agent would: each Given value of a report that answers a request has its own check (a
    ``formal_checks`` entry naming its claim whose ``detail`` begins "stem_given" and quotes the value) or is listed by an
    ST-UNDEC-003 naming its claim (an ST-PARSE-001 naming it when the branch cannot read its span whole). The (transfer, claim
    index, claim, value) of each Given value with neither."""
    out = []
    for t in _items(d["transfers"]):
        rc = t.get("receipt") or {}
        for j, c in _given_claims(t):
            cid = c["claim_id"]
            details = [str(fc.get("detail") or "") for fc in _items(rc.get("formal_checks")) if cid in _items(fc.get("claim_ids"))]
            st = [f for f in _items(rc.get("structural_findings")) if cid in _items(f.get("claim_ids"))]
            if any(f.get("code") == "ST-PARSE-001" for f in st):
                continue
            for value in _given_values(c["claim_text"]):
                checked = any(dt.startswith("stem_given") and f"'{value}'" in dt for dt in details)
                named = any(f.get("code") == "ST-UNDEC-003" and value in str(f.get("message") or "") for f in st)
                if not (checked or named):
                    out.append((t, j, c, value))
    return out


def _i98_agent(d: dict) -> dict:
    """The I98 agent's verdict: ``finding_missing`` for each Given claim with neither its check nor its ST code, with the pointers I98
    and Evidence rule E8 prescribe (the claim's text quoted, the receipt's ``structural_findings`` with no quote)."""
    accusations = []
    for t, j, c, _value in _i98_missing(d):
        ev = [{"pointer": f"{t['at']}/payload/claims/{j}/claim_text", "quote": c["claim_text"]}, {"pointer": f"{t['at']}/receipt/structural_findings"}]
        accusations.append(H.accusation(f"a{len(accusations) + 1}", "finding_missing", ev, message_ids=[t["message_id"]], claim_ids=[c["claim_id"]],
                                        report_ids=[t["payload"].get("report_id")],
                                        statement="A Given value of this report has neither its stem_given check nor an ST-UNDEC-003 (I98)."))
    return H.verdict_dict(d, accusations)


@pytest.mark.timeout(1200)
@pytest.mark.parametrize("pid", ["givens-uncertainty-percent", "givens-uncertainty-percent-start", "givens-after-formula", "givens-unread-span",
                                 "givens-relative-uncertainty"])
def test_an_agent_that_follows_i98_finds_every_planted_given_checked_or_named(tmp_path, pid):
    """The independent test's pack agent accused finding_missing on 'Given: count rate uncertainty = ±3%' as I98 told it to, and the
    deterministic check refuted it: the receipt was the branch's, and the branch read no '±3%'. Now every such Given has its
    stem_given check (or, for a span the branch cannot read whole, its ST-PARSE-001), so an agent following I98 accuses nothing."""
    rnd = material_round(tmp_path / "rounds")
    p = SP.probe(pid)
    dest = H.mini_round(rnd, tmp_path / "work", p.stems)
    SP.edit_answers(dest, p.edits)
    pack = H.export_and_load_pack(tmp_path / "pack")[0]
    seen: list[dict] = []

    def agent(d):
        v = _i98_agent(d)
        seen.append(v)
        return v
    ob = SP._observe(dest, p.key, p.marker, pack=pack, agent=agent)
    assert seen and all(v["accusations"] == [] for v in seen), seen
    assert ob.marker_claims, pid
    planted = {cid for _rid, cid in ob.marker_claims}
    codes = {f["code"] for r in ob.receipts for f in r["findings"] if set(f.get("claim_ids") or []) & planted}
    assert set(p.expected) & codes, (pid, codes)


def test_the_i98_agent_accuses_a_given_with_neither_its_check_nor_its_st_code():
    """The agent's own control, on Example 34's excerpt (a Given value the receipt leaves with neither): it accuses finding_missing."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, _table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 34)
    missing = _i98_missing(ex.nested)
    assert [(c["claim_id"], value) for _t, _j, c, value in missing] == [(ex.verdict["accusations"][0]["claim_ids"][0], "5.0 s")]
    assert [a["kind"] for a in ex.verdict["accusations"]] == ["finding_missing"]


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


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_the_boolean_evaluation_as_the_code_decides_it(d31):
    for words in ('a Boolean expression evaluated under the values the answer gives its inputs ("With A = 1 and B = 0, NOT A OR B = 0" is decided at A = 1 and B = 0',
                  '"Let A = 1 and B = 0. Then NOT A OR B = 0"', "an input given no value must hold for each of its values",
                  'or a Boolean evaluation (its `detail` says "the Boolean evaluation" and names the values it is evaluated under), checked over its negation '
                  'under those values'):
        assert words in d31, words
    for line, status in (("With A = 1 and B = 0, NOT A OR B = 0.", "UNSATISFIABLE"), ("With A = 1 and B = 0, NOT A OR B = 1.", "SATISFIABLE"),
                         ("Let A = 1 and B = 0. Then NOT A OR B = 0.", "UNSATISFIABLE"), ("With A = 1, A OR B = 1.", "UNSATISFIABLE"),
                         ("With A = 0, A OR B = 1.", "SATISFIABLE")):
        checks, findings = _decided(line, "computer_science")
        assert [(k, st) for k, st, _d in checks] == [("bool", status)] and findings == [], (line, checks)
        assert "the Boolean evaluation" in checks[0][2] and "evaluated under the values the statement gives its inputs" in checks[0][2]


def test_d31_states_the_restatement_row_given_and_change_readings_as_the_code_reads_them(d31):
    for words in ('a word naming the value\'s unit may stand after the number, or none, and the rounding may name the unit, a place with the unit after it '
                  'or a part of the unit: after "= 4773.74", "so 4774 euros to the nearest euro" holds, and "so 4775 euros to the nearest euro", "so 4775 to '
                  'the nearest euro" and "so 4780 to the nearest ten euros" fail; after "= 4773.7401", "so 4773.74 euros to the nearest cent" holds and "so '
                  '4773.75 euros to the nearest cent" fails',
                  '"Dissolved oxygen at site C = 3.8 mg dm⁻³", "At site C, dissolved oxygen is 3.8 mg dm⁻³"',
                  '("Given: count rate uncertainty = ±3%" against "+/-2%")', '("1620 counts min⁻¹ ± 2%")',
                  '("Given: ε = 12 ± 0.1 V" after "ε = I(R + r)") is a Given, never the formula evaluated at it',
                  '"Given: count rate at t = 0 h = 1620 ± 2% counts min⁻¹", a unit after a per cent sign): nothing of the span is read',
                  '"mayfly nymphs" for "Mayfly nymphs per kick sample"', '"The value at site C = 3.8 mg dm⁻³" names no column and is not read (rule row-value)',
                  'a substitution stated after the change, in its statement or in its part may take 2.7 A', "one in an earlier part never does",
                  "which value an uncertainty rule's percentage is of"):
        assert words in d31, words
    # each restatement D31 names, executed: the ones it says hold hold, the ones it says fail fail
    for chain, tail, status in (("4773.74", "so 4774 euros to the nearest euro", "ENTAILED"), ("4773.74", "so 4775 euros to the nearest euro", "COUNTEREXAMPLE"),
                                ("4773.74", "so 4775 to the nearest euro", "COUNTEREXAMPLE"), ("4773.74", "so 4780 to the nearest ten euros", "COUNTEREXAMPLE"),
                                ("4773.7401", "so 4773.74 euros to the nearest cent", "ENTAILED"),
                                ("4773.7401", "so 4773.75 euros to the nearest cent", "COUNTEREXAMPLE")):
        got, _f = _beyond("mai-t13", _with("mai-t13", "Next step: rework (a)", f"Check: 4000 × 1.036⁵ = {chain}, {tail}.\n\nNext step: rework (a)"))
        # STEM repair 9: beside the restatement's own check, the place its digits are written to is set against the place its rounding
        # names (rule rounded-digits), which every one of these holds: their slips are in the value, never in its place
        assert [(k, st) for k, st, _d in got] == [("eq", "ENTAILED"), ("res", status), ("eq", "ENTAILED")], (tail, got)
        assert "(rule rounded-digits)" in got[2][2] and "(rule rounded-digits)" not in got[1][2], (tail, got)
    w = "Water temperature was between 17 °C and 18 °C at every site, so it does not explain the difference."
    for line, status in (("At site C, dissolved oxygen is 3.8 mg dm⁻³.", "ENTAILED"), ("At site C, dissolved oxygen is 3.8 g dm⁻³.", "COUNTEREXAMPLE")):
        got, _f = _beyond("ess-t13", _with("ess-t13", w, line))
        assert [(k, st) for k, st, _d in got] == [("giv", status)] and "rule row-value" in got[0][2]
    assert _beyond("ess-t13", _with("ess-t13", w, "The value at site C = 3.8 mg dm⁻³.")) == ([], [])
    end = "Both effects make the count rate smaller than the activity."
    got, _f = _beyond("ph-p7b", _with("ph-p7b", end, end + "\n\nGiven: count rate uncertainty = ±3%."))
    assert [(k, st) for k, st, _d in got] == [("giv", "COUNTEREXAMPLE")] and "(rule given-uncertainty)" in got[0][2]
    got, f = _beyond("ph-p7b", _with("ph-p7b", end, end + "\n\nGiven: count rate at t = 0 h = 1620 ± 2% counts min⁻¹."))
    assert got == [] and "ST-PARSE-001" in f
    ph_end = "from 9.9 V to 10.7 V."
    got, _f = _beyond("ph-t13", _with("ph-t13", ph_end, ph_end + "\n\nGiven: ε = 12 ± 0.1 V."))
    assert [(k, st) for k, st, _d in got] == [("giv", "ENTAILED")]
    got, _f = _beyond("ph-t13", _with("ph-t13", ph_end, ph_end + "\nV = 12 V − 2.7 A × 0.50 Ω = 10.65 V"))
    assert ("sub", "ENTAILED") in [(k, st) for k, st, _d in got] and all(st == "ENTAILED" for _k, st, _d in got)
    assert any("(rule changed-value)" in d for k, _st, d in got if k == "sub")
    got, _f = _beyond("ph-t13", _with("ph-t13", "V = 12 V − (4.14 A × 0.50 Ω) = 9.9 V", "V = 12 V − (2.7 A × 0.50 Ω) = 10.65 V"))
    assert ("sub", "COUNTEREXAMPLE") in [(k, st) for k, st, _d in got]  # an earlier part never takes it


def test_d31_s_tolerance_rule_states_operand_precision_stated_uncertainty_and_exact_carry(d31):
    for words in ('rule operand-precision): "4000 × 1.036³ = 4467.74" fails, 0.45% being beyond the 0.29% the rounding of 1.036 allows',
                  '"586 − 20 = 564 ± 12" fails, whole numbers being exact (τ = 0)', "A stated value that is a whole number ending in zero, written without a "
                  "point, keeps 1/100", '("each corrected value has an absolute uncertainty of 2% of the measured value")',
                  '("1151 − 20 = 1131 ± 23": 2% of 1151 is 23.02)', "(rule stated-uncertainty); otherwise u is not checked",
                  '("T = ln 2 ÷ ((ln 2)/8) = 8": every operand and the stated value exact) is carried exactly, with no interval (rule exact-carry)',
                  '"8 ln 2 ÷ ln(1568/816) ≈ 9.5 h" fails (8.49)'):
        assert words in d31, words
    checks, _f = _decided("u = 4000 × 1.036³ = 4467.74", "mathematics_ai")
    assert [(k, st) for k, st, _d in checks] == [("eq", "COUNTEREXAMPLE")] and "(rule operand-precision)" in checks[0][2]
    assert "τ = 1449/500000" in checks[0][2]  # 0.2898%: the 0.29% D31 states
    checks, _f = _decided("t = 12 h: 586 − 20 = 564 ± 12 counts min⁻¹", "physics", request="Q")
    assert [(k, st) for k, st, _d in checks] == [("eq", "COUNTEREXAMPLE")] and "τ = 0: twice the largest relative change" in checks[0][2]
    got, _f = _beyond("ph-p7b", _with("ph-p7b", "t = 4 h: 1151 − 20 = 1131 ± 23", "t = 4 h: 1151 − 20 = 1131 ± 33"))
    assert [(k, st) for k, st, _d in got if k == "giv"] == [("giv", "COUNTEREXAMPLE")]
    got, _f = _beyond("maa-p7b", _with("maa-p7b", "≈ 8.5 h", "≈ 9.5 h"))
    assert [st for k, st, d in got if "8 ln 2 ÷ ln(1568/816)" in d] == ["UNSATISFIABLE"]


def test_d32_i95_i98_the_master_prompt_and_the_mistakes_rows_say_what_the_code_does():
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert 'its relations are not checked, and a Given in such a span is not read in part |' in d32
    inspection, prompt, dossier = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt"), _pack_text("02-dossier.md")
    i95 = _section(inspection, "**I95 ", "\n- **I96")
    i98 = _section(inspection, "**I98 ", "\n## ")
    assert ('is checked as evaluated under them: its `detail` says "the Boolean evaluation" and names the values, and UNSATISFIABLE with `satisfied` true '
            'means it holds under them (Examples, Example 36)') in i95
    assert "never accuse the evaluation because the expression is no identity: the signed result decides it" in i95
    assert ('A Given uncertainty written with "±", "+/-" or "%" ("Given: count rate uncertainty = ±3%") is a Given value like any other: its check '
            'sets it against the uncertainties the request and its supplied texts state, and its ST-UNDEC-003 names it when they state none of its '
            'kind') in i98
    assert 'or a Given in a maths span the branch cannot read whole, is ST-PARSE-001 instead' in i98
    assert 'an ST-PARSE-001 when its maths span is not read whole' in prompt and 'an uncertainty written "±3%" is a Given value too' in prompt
    assert 'A Boolean check whose `detail` says "the Boolean evaluation" is the expression evaluated under the values its statement gives, never an identity' in prompt
    assert '| Reading a Boolean check whose `detail` says "the Boolean evaluation" as an identity over every input |' in dossier
    assert '| Reading a substitution that takes the value a stated change ends at as unchecked or wrong |' in dossier
    assert '| `formal_status_wrong` or `receipt_altered` for a Boolean check whose `detail` says "the Boolean evaluation", because the expression is no identity |' in inspection
    assert '| `finding_missing` for the uncertainty written with a Given value ("Given: ε = 12 ± 0.1 V") that no check of its own names' in inspection
    # what I98 says of the uncertainty written with a Given value, executed: checked with an uncertainty of its kind stated, else not read
    ch_end = "so I cannot give one yet."
    got, _f = _beyond("ch-t13", _with("ch-t13", ch_end, ch_end + "\n\nGiven: T = 20.0 ± 0.2 °C."))
    assert [(k, st) for k, st, _d in got] == [("giv", "ENTAILED"), ("giv", "COUNTEREXAMPLE")]
    got, f = _beyond("ph-t13", _with("ph-t13", "from 9.9 V to 10.7 V.", "from 9.9 V to 10.7 V.\n\nGiven: ε = 12 ± 0.1 V."))
    assert [(k, st) for k, st, _d in got] == [("giv", "ENTAILED")] and f == []  # no uncertainty in volts stated: the ± 0.1 V is not read
    # and a Given that is an uncertainty, with none of its kind stated (ph-t13 states no uncertainty), is named ST-UNDEC-003, never left silent
    got, f = _beyond("ph-t13", _with("ph-t13", "from 9.9 V to 10.7 V.", "from 9.9 V to 10.7 V.\n\nGiven: uncertainty in each voltmeter reading = ±3%."))
    assert got == [] and f == ["ST-UNDEC-003"]


def test_example_36_is_the_receipt_the_channel_gives():
    """Example 36's request and answer through the channel: the receipt carries the one Boolean evaluation the example shows, detail
    for detail, and no finding; its verdict accuses nothing. Had the answer stated NOT A OR B = 1, the check would fail, named by
    its INT-SUBJ-001."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 36)
    assert table[36] == ("genuine", "none") and ex.type == "genuine."
    request = ex.value("/transfers/0/payload/user_input")
    answer = ex.value("/transfers/1/payload/claims/0/claim_text")

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Computer Science", task_type="short_answer",
                               selected_agent_ids=["stem-specialist"]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
        return hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")

    reply, rc = receipt(answer)
    assert rc.status.value == ex.value("/transfers/1/receipt/status") == "ACCEPTED"
    assert [fc.detail for fc in rc.formal_checks] == [ex.value("/transfers/1/receipt/formal_checks/0/detail")]
    assert [(fc.constraint_id, list(fc.claim_ids), fc.satisfied, fc.formal_status) for fc in rc.formal_checks] == [
        (ex.value("/transfers/1/receipt/formal_checks/0/constraint_id"), ex.value("/transfers/1/receipt/formal_checks/0/claim_ids"), True, "UNSATISFIABLE")]
    assert list(rc.findings) == [] and list(rc.structural_findings) == [] == ex.value("/transfers/1/receipt/structural_findings")
    claim = reply.payload["claims"][0]
    assert (claim["claim_id"], claim["claim_text"], claim["claim_role"]) == ("c1.1", answer, ex.value("/transfers/1/payload/claims/0/claim_role"))
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, wrong = receipt(answer.replace("NOT A OR B = 0", "NOT A OR B = 1"))
    assert [(fc.satisfied, fc.formal_status) for fc in wrong.formal_checks] == [(False, "SATISFIABLE")]
    assert [(f.code, f.severity) for f in wrong.findings] == [("INT-SUBJ-001", "error")]
