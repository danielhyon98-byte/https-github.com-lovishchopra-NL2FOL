"""STEM repair 3 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 34).

* the STEM probes of repair 3 (the third independent test's plants, each class with its clean control) and the probe module's
  rule that a planted finding is matched to the untampered copy's by the texts of the claims it names before their ids;
* the STEM receipt cases T23t (an INT-SUBJ-004 of a value-at Given dropped), T23u (a failed central-value check restated as
  the uncertainty band, holding) and T23v (a failed processed-data check reported as holding);
* the pack beside the code: D31's new readings, D32's ST-UNDEC-001, ST-UNDEC-003, ST-DIM and ST-UNDEF-001 rows, I97, I98 and
  the master prompt executed against the STEM front end, and Example 35 regenerated through the channel.
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
from epinoic_logic.ir.schema import Problem  # noqa: E402
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402
from epinoic_logic.stem.datatables import parse_data_tables  # noqa: E402
from epinoic_logic.translate.contracts import SuppliedText  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-3-test-key-0123456789abcdef"


def _pack_text(name: str) -> str:
    return (installed_pack_dir(PACK_VERSION) / name).read_text(encoding="utf-8")


# ============================================================================================ the probes and the tamper cases
#: each plant of the third independent test, with the code that must name it
REPAIR3_PROBES = {
    "givens-at-condition": ("INT-SUBJ-004",), "givens-at-condition-symbol": ("INT-SUBJ-004",), "givens-at-condition-trials": ("INT-SUBJ-004",),
    "givens-values-at": ("INT-SUBJ-004",), "givens-supplied-prose": ("INT-SUBJ-004",), "givens-supplied-volume": ("INT-SUBJ-004",),
    "givens-uncertainty": ("INT-SUBJ-004",), "givens-central": ("INT-SUBJ-004",), "arithmetic-within-uncertainty": ("INT-SUBJ-001",),
    "wrong-given-measured": ("INT-SUBJ-004",), "units-table-restated": ("INT-SUBJ-004",), "units-task-restated": ("INT-SUBJ-004",),
    "formulas-percentage-final": ("INT-SUBJ-004",), "formulas-half-lives": ("INT-SUBJ-004",), "physics-half-lives-count": ("INT-SUBJ-004",),
    "rounding-stated-value-sf": ("INT-SUBJ-001",), "receipts-sum": ("INT-SUBJ-001",), "receipts-sum-symbolic": ("ST-UNDEC-001",),
}
#: the correct writing of each class, which must stay clean (the first nine were findings before the repair)
REPAIR3_CONTROLS = ("givens-at-condition-control", "givens-at-condition-symbol-control", "givens-at-condition-trials-control", "givens-values-at-control",
                    "givens-supplied-prose-control", "givens-supplied-volume-control", "givens-uncertainty-control", "units-table-restated-control",
                    "physics-percent-control", "givens-central-control", "arithmetic-within-uncertainty-control", "wrong-given-measured-control",
                    "units-task-restated-control", "formulas-percentage-final-control", "formulas-half-lives-control", "physics-half-lives-count-control",
                    "rounding-stated-value-sf-control", "receipts-sum-control")


def test_every_plant_of_the_third_independent_test_is_a_probe_with_its_control():
    """The plants are probes of the module the contained run gates (stem_fault_classes_named), each with the code that must name
    it; a value under a condition must never again be failed as a conversion; each class's correct writing is a control."""
    assert len(SP.REPAIR3_PROBES) == len(REPAIR3_PROBES) + len(REPAIR3_CONTROLS) == 36
    assert {p.probe_id for p in SP.REPAIR3_PROBES} == set(REPAIR3_PROBES) | set(REPAIR3_CONTROLS)
    for pid, expected in REPAIR3_PROBES.items():
        p = SP.probe(pid)
        assert p.expected == expected and p.kind == "answer" and p.context == "receipt" and p.fault_class in SP.TAMPER_CASES, pid
    for pid in REPAIR3_CONTROLS:
        p = SP.probe(pid)
        assert p.kind == "control" and p.expected == () and p.fault_class in SP.TAMPER_CASES, pid
    for pid in ("givens-at-condition", "givens-at-condition-symbol", "givens-at-condition-trials", "givens-values-at"):
        assert SP.probe(pid).forbidden == ("INT-SUBJ-001", "ST-DIM-001"), pid  # the false conversion, never again
    # STEM repair 4 (design section 35) appended its 55 probes after these, STEM repair 5 (design section 36) its 81 after those, STEM
    # repair 6 (design section 37) its 49 after those, STEM repair 7 (design section 38) its 41 after those and STEM repair 8 (design
    # section 39) its 62 after those: repair 3's stay at the same positions
    assert SP.REPAIR3_PROBES == SP.PROBES[131:167] and SP.PROBES[167:222] == SP.REPAIR4_PROBES and SP.PROBES[222:303] == SP.REPAIR5_PROBES
    assert SP.PROBES[303:352] == SP.REPAIR6_PROBES and SP.PROBES[352:393] == SP.REPAIR7_PROBES and SP.PROBES[393:455] == SP.REPAIR8_PROBES
    assert SP.PROBES[455:512] == SP.REPAIR9_PROBES and SP.PROBES[512:606] == SP.REPAIR10_PROBES and SP.PROBES[606:641] == SP.REPAIR11_PROBES and SP.PROBES[641:] == SP.REPAIR12_PROBES
    assert len(SP.PROBES) == 677


def _f(code: str, claim: str, text: str, severity: str = "warning") -> dict:
    return {"code": code, "severity": severity, "claim_ids": [claim], "claim_texts": (text,), "message": code}


def test_a_planted_finding_is_matched_by_the_texts_of_its_claims_before_their_ids():
    """A line added before a claim shifts its id: the tester's control 'x-giv-bi-table-ctl' read the untampered CORE-QNT-001 of the
    shifted claim as new. Matched by the claims' texts first, then by ids, each untampered finding once."""
    base = [_f("CORE-QNT-001", "s3.1", "The uptake rises from 18 mm³ per g per hour.")]
    shifted = [_f("CORE-QNT-001", "s3.2", "The uptake rises from 18 mm³ per g per hour.")]
    assert SP._new(shifted, base) == []
    planted = shifted + [_f("INT-SUBJ-004", "s3.1", "Given: oxygen uptake at 30 °C = 85 mm³ per g per hour.")]
    assert SP._new(planted, base) == [planted[1]]
    twice = shifted + [_f("CORE-QNT-001", "s3.3", "The uptake rises from 18 mm³ per g per hour.")]
    assert SP._new(twice, base) == [twice[1]]  # each untampered finding matches once
    old = [{"code": "CORE-QNT-001", "severity": "warning", "claim_ids": ["s3.1"], "message": "m"}]  # a record with no claim texts: by ids
    assert SP._new(old, old) == [] and SP._new([dict(old[0], claim_ids=["s3.2"])], old) == [dict(old[0], claim_ids=["s3.2"])]


def test_the_repair_3_tamper_cases_are_registered_on_their_targets():
    """T23t drops a value-at Given's INT-SUBJ-004 (r7/p7b, r7/ch-t13), T23u restates a failed central-value check as the band
    holding (r7/p7b), T23v reports a failed processed-data check as holding (r7/p7b); the suite runs them in
    tests/overseer/test_stem_completion.py, each on its planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23t", "finding_missing"), ("T23u", "receipt_altered"), ("T23v", "formal_status_wrong")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    assert "T23t" in SP.TAMPER_CASES["givens"] and "T23u" in SP.TAMPER_CASES["arithmetic"] and "T23v" in SP.TAMPER_CASES["wrong_given"]


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


def _task(tid: str, text: str, profile: str):
    data = tuple(t["text"] for t in R7[tid].get("supplied_texts") or [])
    return _decided(text, profile, R7[tid]["question"], data)


def _edited(tid: str, old: str, new: str) -> str:
    text = R7[tid]["response_text"]
    assert text.count(old) == 1, old
    return text.replace(old, new)


def _beyond(tid: str, text: str, profile: str):
    """The checks ``text`` has beyond the recorded answer's, compared by kind and status (the check of an edited statement takes
    the place of the recorded one's), as (kind, status, description); and the finding codes it has beyond the recorded answer's."""
    checks, findings = _task(tid, text, profile)
    base, base_f = _task(tid, R7[tid]["response_text"], profile)
    left = Counter((k, st) for k, st, _d in base)
    out = []
    for c in checks:
        if left[(c[0], c[1])]:
            left[(c[0], c[1])] -= 1
        else:
            out.append(c)
    return out, sorted((Counter(c for c, _m in findings) - Counter(c for c, _m in base_f)).elements())


def _kinds(checks) -> list[tuple[str, str]]:
    return [(k, st) for k, st, _d in checks]


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


@pytest.fixture(scope="module")
def d31() -> str:
    return _section(_pack_text("02-dossier.md"), "**D31 ", "\n- **D32")


def test_d31_states_the_new_readings_as_the_code_reads_them(d31):
    """Each new statement of D31's opening list, executed against the STEM front end."""
    for words in ('a sum Σ over written whole-number bounds of at most 24 terms, expanded: "Σ_{k=1}^{10} k = 55"',
                  '"R = 2.4 Ω (the external resistance), or 2 Ω to one significant figure"',
                  '("the background of 20 counts s⁻¹" against the supplied "20 counts per minute")',
                  '"oxygen uptake at 30 °C = 80 mm³ per g per hour" is the uptake at the table\'s row 30 °C, never a conversion of 30 °C',
                  '("C = 1620 counts min⁻¹ × (1/2)⁴" after "1620 − 20 = 1600", in a part asking for the corrected rate)',
                  '"(9.6 − 3.8) ÷ 3.8 × 100 = 152.6% decrease" divides by the final value and fails',
                  '("32 h is 4 half-lives": 4 × T½ against 32 h, and the power of ½ written after it against 4)'):
        assert words in d31, words
    for n, status in ((10, "ENTAILED"), (24, "ENTAILED")):
        assert _kinds(_decided(f"Σ_{{k=1}}^{{{n}}} k = {n * (n + 1) // 2}", "mathematics_aa")[0]) == [("eq", status)]
    assert _kinds(_decided("Σ_{k=1}^{10} k = 56", "mathematics_aa")[0]) == [("eq", "COUNTEREXAMPLE")]
    checks, findings = _decided("Σ_{k=1}^{25} k = 325", "mathematics_aa")
    assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-001"] and "a sum (Σ)" in findings[0][1]
    for value, status in (("2", "ENTAILED"), ("3", "COUNTEREXAMPLE")):
        line = f"R = 2.4 Ω (the external resistance), or {value} Ω to one significant figure"
        # STEM repair 9: the restatement's own check is as before, and beside it the place its digits are written to is set against
        # the place the rounding names (rule rounded-digits): 2 and 3 are written to the units, as one significant figure of 2.4 is
        checks = _decided(line, "physics")[0]
        assert _kinds(checks) == [("res", status), ("eq", "ENTAILED")], line
        assert "(rule rounded-digits)" in checks[1][2] and "(rule rounded-digits)" not in checks[0][2], line
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "the background of 20 counts min⁻¹ is constant", "the background of 20 counts s⁻¹ is constant"), "physics")
    assert _kinds(got) == [("giv", "COUNTEREXAMPLE")] and "(rule restated-unit)" in got[0][2] and codes == []
    assert _beyond("ph-p7b", _edited("ph-p7b", "the background of 20 counts min⁻¹ is constant", "the background of 20 counts per minute is constant"),
                   "physics") == ([], [])
    checks, findings = _task("bi-t13", "Given: oxygen uptake at 30 °C = 80 mm³ per g per hour.", "biology")
    assert _kinds(checks) == [("giv", "ENTAILED")] and findings == [] and "(rule table-data, rule value-at)" in checks[0][2]
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹", "C = 1620 counts min⁻¹ × (1/2)⁴ = 101 counts min⁻¹"),
                         "physics")
    assert _kinds(got) == [("giv", "COUNTEREXAMPLE")] and "(rule processed-data)" in got[0][2] and codes == []
    got, codes = _beyond("ess-t13", _edited("ess-t13", "(9.6 − 3.8) ÷ 9.6 × 100\n= 60.4% decrease", "(9.6 − 3.8) ÷ 3.8 × 100\n= 152.6% decrease"), "ess")
    assert _kinds(got) == [("eq", "COUNTEREXAMPLE")] and "(rule percentage-change)" in got[0][2] and codes == []
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "32 h is 4 half-lives", "32 h is 5 half-lives"), "physics")
    assert _kinds(got) == [("eq", "COUNTEREXAMPLE")] * 2 and all("(rule half-lives)" in d for _k, _s, d in got) and codes == []
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "C = 1600 counts min⁻¹ × (1/2)⁴ = 100 counts min⁻¹", "C = 1600 counts min⁻¹ × (1/2)³ = 200 counts min⁻¹"),
                         "physics")
    assert _kinds(got) == [("eq", "COUNTEREXAMPLE")] and "(rule half-lives)" in got[0][2] and codes == []


@pytest.mark.parametrize("tid, line, profile, status, rule, extra", [
    ("ch-t13", "Given: volume of thiosulfate = 40.0 cm³.", "chemistry", "COUNTEREXAMPLE", "rule supplied-values", ()),
    ("ch-t13", "Given: volume of thiosulfate = 50.0 cm³.", "chemistry", "ENTAILED", "rule supplied-values", ()),
    ("bi-t13", "Given: oxygen uptake at 30 °C = 85 mm³ per g per hour.", "biology", "COUNTEREXAMPLE", "rule value-at", ()),
    ("ph-p7b", "Given: the count rate at t = 8 h = 820 counts min⁻¹.", "physics", "ENTAILED", "rule value-at", ()),
    ("ph-p7b", "Given: at t = 8 h, C = 830 counts min⁻¹.", "physics", "COUNTEREXAMPLE", "rule value-at", ()),
    ("ch-t13", "Given: time at 30.0 °C = 34.0 s.", "chemistry", "ENTAILED", "rule value-at", ()),
    ("ch-t13", "Given: time at 30.0 °C = 36.1 s.", "chemistry", "COUNTEREXAMPLE", "rule value-at", ()),
    ("ph-p7b", "Given: background count rate = 30 counts min⁻¹.", "physics", "COUNTEREXAMPLE", "rule given-digits", ()),
    ("ch-t13", "Given: thermometer uncertainty = 0.5 °C.", "chemistry", "ENTAILED", "rule given-uncertainty", ()),
    ("ch-t13", "Given: Δθ = ±0.5 °C.", "chemistry", "ENTAILED", "rule given-uncertainty", ()),
    ("ph-p7b", "Given: percentage uncertainty in each count rate = 3%.", "physics", "COUNTEREXAMPLE", "rule given-uncertainty", ()),
    # STEM repair 4: the uncertainty written with the Given value is set against the supplied text's +/-0.5 °C too (rule given-uncertainty)
    ("ch-t13", "Given: T = 20.0 ± 0.5 °C.", "chemistry", "ENTAILED", "rule central-value", (("ENTAILED", "rule given-uncertainty"),)),
    ("ch-t13", "Given: T = 20.0 ± 0.2 °C.", "chemistry", "ENTAILED", "rule central-value", (("COUNTEREXAMPLE", "rule given-uncertainty"),)),
])
def test_d31_s_given_paragraph_is_what_the_given_checks_read(d31, tid, line, profile, status, rule, extra):
    """D31's Given paragraph names each of these readings, and the code reads each Given so: one stem_given check, a warning
    failure, the rule in its detail (STEM repair 4: and, for a Given written with its uncertainty, a second check of the uncertainty
    against the uncertainties the request and its supplied texts state of its kind)."""
    for words in ('("Given: volume of thiosulfate = 40.0 cm³" against "50.0 cm3 of … sodium thiosulfate solution"',
                  '"Given: the count rate at t = 8 h = 820 counts min⁻¹", "Given: at t = 8 h, C = 820 counts min⁻¹"', '("time" beside three timed trials)',
                  "The condition itself is no Given and binds nothing", '(30 and 20 differ; the `detail` says "rule given-digits")',
                  '"Given: thermometer uncertainty = 0.5 °C") or written as one ("Given: Δθ = ±0.5 °C") is no value of its quantity',
                  '("Uncertainties: thermometer +/-0.5 °C", "+/-2%"; the `detail` says "rule given-uncertainty")',
                  'A Given written with its uncertainty ("Given: T = 20.0 ± 0.5 °C") is set against the request at its central value (rule central-value)'):
        assert words in d31, words
    checks, findings = _task(tid, line, profile)
    assert _kinds(checks) == [("giv", status)] + [("giv", st) for st, _r in extra] and findings == [], (checks, findings)
    assert rule in checks[0][2] and "failure severity warning" in checks[0][2], checks[0][2]
    for (st, r), c in zip(extra, checks[1:]):
        assert r in c[2] and "failure severity warning" in c[2], c[2]


def test_d31_s_given_none_and_table_paragraphs_are_what_the_code_names(d31):
    for words in ('"C0 = 1600 counts min⁻¹" beside the supplied background', "a Given stated under a condition with no supplied table to read the row of",
                  "a Given uncertainty where the request and its supplied texts state no uncertainty of its kind",
                  '("from 18 cm³ per g per hour at 10 °C" for the table\'s 18 mm3 per g per hour)',
                  'A header unit written with ASCII exponents ("mm3", "mg dm-3") is read as written with superscripts',
                  'a line that processes the raw cell again into the processed value ("C₀ = 1620 − 20 = 1600 counts min⁻¹")',
                  '("20/1620 × 100 = 1.2% of the first reading") are not read',
                  '"the current falls from 4.1 A to 2.7 A" checks 4.1 A only', "the direction of a percentage change, the number of half-lives the prose states"):
        assert words in d31, words
    for tid, line, profile, data in (("ph-p7b", "Given: C0 = 1600 counts min⁻¹.", "physics", True),
                                     ("bi-t13", "Given: oxygen uptake at 30 °C = 80 mm³ per g per hour.", "biology", False),
                                     ("ph-t13", "Given: thermometer uncertainty = 0.5 °C.", "physics", True)):
        checks, findings = _task(tid, line, profile) if data else _decided(line, profile, R7[tid]["question"])
        assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-003"], (line, checks, findings)
    got, codes = _beyond("bi-t13", _edited("bi-t13", "from 18 mm³ per g per hour at 10 °C", "from 18 cm³ per g per hour at 10 °C"), "biology")
    assert [st for _k, st, _d in got] == ["COUNTEREXAMPLE"] and codes == []
    assert _beyond("bi-t13", _edited("bi-t13", "from 18 mm³ per g per hour at 10 °C", "from 0.018 cm³ per g per hour at 10 °C"), "biology") == ([], [])
    [table] = parse_data_tables((R7["bi-t13"]["supplied_texts"][0]["text"],))
    col = table.columns[1]
    assert col.unit_ascii and col.unit is not None and col.unit.dim is not None and "mm³" in col.unit.text
    for line in ("C₀ = 1620 − 20 = 1600 counts min⁻¹.", "The background is 20/1620 × 100 = 1.2% of the first reading."):
        got, codes = _beyond("ph-p7b", _edited("ph-p7b", "32 h is 4 half-lives, so", line + " 32 h is 4 half-lives, so"), "physics")
        assert _kinds(got) == [("eq", "ENTAILED")] and codes == [], (line, got)
    assert _beyond("ph-t13", _edited("ph-t13", "from 4.1 A to 2.7 A", "from 4.1 A to 2.6 A"), "physics") == ([], [])  # the silence D31 states
    got, codes = _beyond("ph-t13", _edited("ph-t13", "from 4.1 A to 2.7 A", "from 3.1 A to 2.7 A"), "physics")
    assert [st for _k, st, _d in got] == ["COUNTEREXAMPLE"] and codes == []


def test_d31_s_tolerance_rule_checks_a_value_with_its_uncertainty_at_its_central_value(d31):
    assert ('A stated value written with its uncertainty, S ± u ("586 − 20 = 566 ± 12"), is checked at its central value S under this rule: u never '
            'widens h, so a slip within the uncertainty fails ("586 − 20 = 556 ± 12"), and this rule does not check u itself. The `detail` says so ("rule '
            'central-value").') in d31
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "586 − 20 = 566 ± 12", "586 − 20 = 556 ± 12"), "physics")
    assert _kinds(got) == [("eq", "COUNTEREXAMPLE")] and "(rule central-value)" in got[0][2] and codes == []
    # STEM repair 4: u is set against the rule the answer states for it ('an absolute uncertainty of 2% of the measured value': 2% of
    # 586 is 11.72), never by rule central-value: the central value's check is the same with any u
    got, codes = _beyond("ph-p7b", _edited("ph-p7b", "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11"), "physics")
    assert _kinds(got) == [("giv", "COUNTEREXAMPLE")] and "(rule stated-uncertainty)" in got[0][2] and codes == []
    assert ('this rule does not check u itself' in d31 and '(rule stated-uncertainty)' in d31)
    assert _beyond("ph-p7b", _edited("ph-p7b", "586 − 20 = 566 ± 12", "586 − 20 = 566 ± 11.7"), "physics") == ([], [])


def test_d32_says_which_st_codes_call_a_relation_wrong_and_what_st_undec_001_names():
    d32 = _section(_pack_text("02-dossier.md"), "**D32 ", "\n## ")
    assert ("Three say more: ST-DIM-001, ST-DIM-002 and ST-UNDEF-001 say that a relation is wrong as written (its two sides have different "
            "dimensions, a sum adds unlike quantities, an expression is undefined)") in d32
    for words in ("a sum Σ over a symbolic bound or of more than 24 terms (a sum over written whole-number bounds is expanded and checked as arithmetic: D31)",
                  "a product ∏", "an ellipsis written in LaTeX (`4787.58\\ldots`, `1 + 2 + \\cdots + 10`)", "a symbolic power",
                  "(for a Given uncertainty, no uncertainty of its kind)", 'A value stated under a condition ("uptake at 30 °C = 80 mm³") relates no two sides and gets none',
                  "the relation is wrong as written; no check is built", "a sum or a difference of terms with different dimensions: wrong as written"):
        assert words in d32, words
    for text, reason in (("Σ_{k=1}^{n} k = n(n + 1)/2", "a sum (Σ)"), ("∏_{k=1}^{4} k = 24", "a product (∏)"), ("$A = 4787.58\\ldots$", "an ellipsis"),
                         ("$1 + 2 + \\cdots + 10 = 55$", "an ellipsis"), ("2^x = 8", "a symbolic power")):
        checks, findings = _decided(text, "mathematics_aa")
        assert checks == [] and [c for c, _m in findings] == ["ST-UNDEC-001"] and reason in findings[0][1], (text, findings)
    for text, code in (("0.693 × 8.0 h = 5.5 h⁻¹", "ST-DIM-001"), ("2.0 m + 3.0 s = 5.0 m", "ST-DIM-002"), ("5/0 = 3", "ST-UNDEF-001"), ("ln(0) = 1", "ST-UNDEF-001")):
        assert code in [c for c, _m in _decided(text, "physics" if "ST-DIM" in code else "mathematics_aa")[1]], text
    assert _decided("uptake at 30 °C = 80 mm³", "biology") == ([], [])  # a value under a condition: no conversion, no ST-DIM-001


def test_i97_i98_and_the_master_prompt_say_what_an_st_code_and_a_conditioned_given_are():
    inspection, prompt = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt")
    i97 = _section(inspection, "**I97 ", "\n- **I98")
    i98 = _section(inspection, "**I98 ", "\n## ")
    assert "ST-DIM-001, ST-DIM-002 and ST-UNDEF-001 say the relation is wrong as written" in i97
    assert "never that the claim is wrong" not in inspection and "never that the claim is wrong" not in prompt
    assert ('A Given stated under a condition ("Given: oxygen uptake at 30 °C = 80 mm³ per g per hour") quotes its value, never the condition: its check is '
            "the stem_given entry set against the supplied table's row (\"the Given value against the request: '80 mm³ per g per hour'\"), and the "
            "condition is no Given of its own (Examples, Example 35)") in i98
    assert "ST-DIM-001, ST-DIM-002 and ST-UNDEF-001 say a relation is wrong as written, decided without the engine" in prompt
    assert "is no Given: the check quotes the value" in prompt and "Example 34 and Example 35" in prompt
    kinds = _pack_text("06-kinds-and-codes.md")
    assert "never that the claim is wrong" not in kinds


def test_example_35_is_the_receipt_the_channel_gives():
    """Example 35's request, table and answer through the channel: the receipt carries the one Given check the example shows,
    detail for detail, and no structural finding (the condition is no Given); its verdict accuses nothing. Had the Given taken the
    25 °C row's 58, the check would fail at warning severity, named by its INT-SUBJ-004."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 35)
    assert table[35] == ("genuine", "none") and ex.type == "genuine."
    request = ex.value("/transfers/0/payload/user_input")
    doc_id = ex.value("/transfers/0/payload/supplied_texts/0/document_id")
    data = ex.value("/transfers/0/payload/supplied_texts/0/text")
    answer = ex.value("/transfers/1/payload/claims/0/claim_text")

    def receipt(text: str):
        hub = RouterHub(signing_key=KEY, config=CFG)
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Biology", task_type="short_answer", selected_agent_ids=["stem-specialist"],
                               allowed_document_ids=[doc_id]))
        m, _, _ = hub.dispatch("t", "stem-specialist", request, [SuppliedText(document_id=doc_id, title="Oxygen uptake", author="Task data", text=data)])
        reply, rc = hub.receive("t", m.message_id, text, agent_id="stem-specialist", report_id="rep-t-0")
        return reply, rc

    reply, rc = receipt(answer)
    assert rc.status.value == ex.value("/transfers/1/receipt/status") == "ACCEPTED"
    assert [fc.detail for fc in rc.formal_checks] == [ex.value("/transfers/1/receipt/formal_checks/0/detail")]
    assert [(fc.constraint_id, list(fc.claim_ids), fc.satisfied, fc.formal_status) for fc in rc.formal_checks] == [
        (ex.value("/transfers/1/receipt/formal_checks/0/constraint_id"), ex.value("/transfers/1/receipt/formal_checks/0/claim_ids"), True, "ENTAILED")]
    assert list(rc.findings) == [] and list(rc.structural_findings) == [] == ex.value("/transfers/1/receipt/structural_findings")
    claim = reply.payload["claims"][0]
    assert (claim["claim_id"], claim["claim_text"], claim["claim_role"]) == ("s1.1", answer, ex.value("/transfers/1/payload/claims/0/claim_role"))
    assert "the Given value stated under its condition against Mean oxygen uptake at the supplied table's row 30 (80)" in rc.formal_checks[0].detail
    assert ex.verdict["accusations"] == [] and ex.verdict["engine_statements"] == []
    _r, wrong = receipt(answer.replace("= 80 mm³", "= 58 mm³"))
    assert [(fc.satisfied, fc.formal_status) for fc in wrong.formal_checks] == [(False, "COUNTEREXAMPLE")]
    assert [(f.code, f.severity) for f in wrong.findings] == [("INT-SUBJ-004", "warning")] and "failure severity warning" in wrong.formal_checks[0].detail
