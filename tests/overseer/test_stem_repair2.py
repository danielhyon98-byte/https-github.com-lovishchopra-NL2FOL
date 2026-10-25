"""STEM repair 2 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 33).

* rule ``table-units`` (``checks.translation``, TRN-004 and TRN-005, STEM answers only): a supplied table's figure the answer
  states, converted into its column's unit with no prefix or into the coherent SI unit (9.6 mg dm⁻³ as 0.0096 kg m⁻³), and a
  figure the answer writes with a compound unit, are the answer's own numbers (Inspection I91). The independent test's
  control (ess-t13 g1.1 encoded in kg m⁻³) got OVS-TRN-004 and OVS-TRN-005; a wrong conversion (0.096) is still named;
* the STEM probes of repair 2 and the probe module's rule that a code a probe forbids overrides its outcome;
* the pack beside the code: D31's Given, table and silence statements executed against the STEM front end, D32's
  ST-UNDEC-003, I97 and I98, the master prompt, and Example 34 regenerated through the channel.
"""
from __future__ import annotations

import json
import sys
from fractions import Fraction
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
from epinoic_logic.overseer.checks.translation import (  # noqa: E402
    TABLE_UNITS_RULE, _table_conversions, stem_subject, unprefixed_factors, untraced_content)
from epinoic_logic.overseer.pack import installed_pack_dir  # noqa: E402

R7 = json.loads((Path(__file__).resolve().parents[1] / "channel" / "data" / "r7_material.json").read_text(encoding="utf-8"))["specialists"]
ESS_TABLE = R7["ess-t13"]["supplied_texts"][0]["text"]
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"stem-repair-2-test-key-0123456789abcdef"


def _pack_text(name: str) -> str:
    return (installed_pack_dir("1.3") / name).read_text(encoding="utf-8")


# ============================================================================================ rule table-units
@pytest.mark.parametrize("unit, factors", [("mg dm⁻³", {Fraction(1, 1000)}), ("mg dm-3", {Fraction(1, 1000)}), ("mol dm⁻³", {Fraction(1000)}),
                                           ("cm³", {Fraction(1, 10 ** 6)}), ("km", {Fraction(1000)}), ("g", {Fraction(1, 1000)}),
                                           ("mm3 per g per hour", {Fraction(1, 10 ** 9), Fraction(1, 10 ** 6)}), ("counts min⁻¹", set()), ("m", set())])
def test_the_factors_into_the_unit_with_no_prefix_and_the_coherent_si_unit(unit, factors):
    """9.6 mg dm⁻³ is 9.6 g m⁻³ (the unit with no prefix: factor 1, nothing to add) and 0.0096 kg m⁻³ (coherent SI); a unit with
    no prefix and no gram converts to nothing."""
    assert TABLE_UNITS_RULE == "table-units"
    assert unprefixed_factors(unit) == frozenset(factors)


def test_a_supplied_table_s_figures_the_answer_states_are_known_in_si():
    stated = {Fraction("9.6"), Fraction("3.8")}
    assert _table_conversions(ESS_TABLE, stated=stated) == {Fraction("0.0096"), Fraction("0.0038")}
    assert _table_conversions(ESS_TABLE, excerpt="A | 0.5 upstream | 1.2 | 9.6 | 34") == {Fraction("0.0012"), Fraction("0.0096")}
    assert _table_conversions(ESS_TABLE, stated={Fraction("5.0")}) == set()  # a figure no cell holds converts nothing


def _problem(values: dict[str, str]) -> tuple[Problem, dict]:
    symbols = [{"name": n, "sort": "Real", "meaning": f"the value {n}"} for n in values]
    premises = [{"id": f"P_{n}", "expr": {"op": "eq", "left": {"op": "var", "name": n}, "right": {"op": "real", "value": v}}, "label": f"{n} as stated",
                 "grounding": {"kind": "specialist_inference"}} for n, v in values.items()]
    obj = {"ir_version": "1.0", "problem_id": "ess-pct", "request_id": "q", "claim_id": "s1.1", "query": "consistency", "symbols": symbols, "premises": premises}
    return Problem.model_validate(obj), obj


@pytest.mark.parametrize("values, untraced", [({"a_do_a": "0.0096", "a_do_c": "0.0038"}, []), ({"a_do_a": "0.096", "a_do_c": "0.038"}, ["P_a_do_a", "P_a_do_c"])])
def test_a_correct_table_conversion_is_the_answer_s_number_and_a_wrong_one_is_named(values, untraced):
    """End to end through ``untraced_content`` (TRN-005's input): the answer states 9.6 and 3.8 mg dm⁻³ from the table, so 0.0096 and
    0.0038 (kg m⁻³) are its own numbers on a STEM answer; 0.096 and 0.038 are no reading of them. On another answer the rule is not
    read (exact_scale off: the generic tracing applies)."""
    answer = "(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease"
    problem, obj = _problem(values)
    got = untraced_content(problem, obj, [answer], [R7["ess-t13"]["question"]], [ESS_TABLE], exact_scale=True)
    assert [t for t, _d in got] == untraced
    if not untraced:
        assert [t for t, _d in untraced_content(problem, obj, [answer], [R7["ess-t13"]["question"]], [ESS_TABLE], exact_scale=False)] == ["P_a_do_a", "P_a_do_c"]


@pytest.mark.parametrize("subject, stem", [("Environmental Systems and Societies", True), ("Physics", True), ("Mathematics: Applications and Interpretation", True),
                                           ("Computer Science", True), ("History", False), ("English A: Literature", False)])
def test_table_units_applies_to_stem_answers_only(subject, stem):
    assert stem_subject(subject) is stem


# ============================================================================================ the probes and the tamper cases
REPAIR2_PROBES = {
    "arithmetic-mod-slip": ("INT-SUBJ-001",), "arithmetic-quotient-remainder": ("INT-SUBJ-001",), "arithmetic-verbal-slip": ("INT-SUBJ-001",),
    "maths-congruence": ("INT-SUBJ-001",), "receipts-fragment": ("ST-PARSE-001",), "receipts-unread-sign": ("ST-PARSE-001",), "boolean-question": ("INT-SUBJ-001",),
    "givens-percent": ("INT-SUBJ-004",), "givens-currency": ("INT-SUBJ-004",), "givens-years": ("INT-SUBJ-004",), "givens-per-cent": ("INT-SUBJ-004",),
    "givens-bare": ("ST-UNDEC-003",), "givens-bare-conversion": ("ST-UNDEC-003",), "givens-prose": ("INT-SUBJ-004",), "givens-table": ("INT-SUBJ-004",),
    "receipts-given-unchecked": ("ST-UNDEC-003",), "wrong-given-table-row": ("INT-SUBJ-004",), "wrong-given-table-line": ("INT-SUBJ-004",),
    "wrong-given-table-row-p7b": ("INT-SUBJ-004",), "relay-derived-rate": ("INT-SUBJ-004",), "relay-derived-initial": ("INT-SUBJ-004",),
    "physics-unit-sum": ("INT-SUBJ-001",), "physics-prose-sum": ("INT-SUBJ-001",), "units-bracketed-conversion": ("INT-SUBJ-001",),
    "equations-premise-cue": ("INT-SUBJ-001",), "units-translation-table-wrong": ("OVS-TRN-005",),
}
REPAIR2_CONTROLS = ("arithmetic-mod-control", "arithmetic-div-control", "arithmetic-floor-division-control", "arithmetic-percent-mod-control",
                    "arithmetic-quotient-remainder-control", "arithmetic-verbal-control", "maths-mod-control", "maths-congruence-control", "boolean-question-control",
                    "givens-percent-control", "givens-currency-control", "givens-years-control", "givens-per-cent-control", "givens-bare-control",
                    "givens-prose-control", "givens-table-control", "wrong-given-table-line-control", "physics-unit-sum-control", "physics-prose-sum-control",
                    "units-bracketed-conversion-control", "equations-premise-cue-control", "units-translation-table-base-control")


def test_every_independent_test_plant_is_a_probe_with_its_control():
    """The independent test's plants are probes of the module the contained run gates (stem_fault_classes_named), each with the
    code that must name it, and each class's correct writing is a control that must stay clean."""
    for pid, expected in REPAIR2_PROBES.items():
        assert SP.probe(pid).expected == expected and SP.probe(pid).kind in ("answer", "translation"), pid
    for pid in REPAIR2_CONTROLS:
        assert SP.probe(pid).kind == "control", pid
    for pid in ("receipts-fragment", "receipts-unread-sign"):
        assert SP.probe(pid).forbidden == ("INT-SUBJ-001",)  # named unchecked, never the false check '5 = 2'
    for pid in ("givens-bare", "givens-bare-conversion"):
        assert SP.probe(pid).forbidden == ("INT-SUBJ-004", "INT-SUBJ-001")  # a bare number is never failed
    # STEM repair 3 (design section 34) registered 36 more probes: 167 (131 before); STEM repair 4 (design section 35) 55 more: 222;
    # STEM repair 5 (design section 36) 81 more: 303; STEM repair 6 (design section 37) 49 more: 352; STEM repair 7 (design section 38) 41
    # more: 393; STEM repair 8 (design section 39) 62 more: 455; STEM repair 9 (design section 40) 57 more: 512; STEM repair 10 (design
    # section 41) 94 more: 606; STEM repair 11 (design section 42) 35 more: 641; STEM repair 12 (design section 43) 36 more: 677, every id
    # still unique
    assert len(SP.PROBES) == 677 and len({p.probe_id for p in SP.PROBES}) == 677


def _observed(codes: list[tuple[str, str]], claim: str = "m13.1") -> "SP.Observed":
    return SP.Observed(receipts=[{"kind": "response_text", "message_id": "m1", "report_id": "rep-mai-t13-0", "status": "ACCEPTED_WITH_FINDINGS",
                                  "findings": [{"code": c, "severity": s, "claim_ids": [claim], "message": c} for c, s in codes], "failed_checks": []}],
                       marker_claims=[("rep-mai-t13-0", claim)], dossier={"transfers": [], "links": {}})


def test_a_code_a_probe_forbids_overrides_its_outcome():
    """A bare Given named unchecked AND failed would be named by its expected code, yet wrong: the forbidden code decides."""
    p = SP.probe("givens-bare")
    base = _observed([])
    base.receipts[0]["findings"] = []
    assert SP.evaluate(p, _observed([("ST-UNDEC-003", "warning")]), base)["outcome"] == "named"
    got = SP.evaluate(p, _observed([("ST-UNDEC-003", "warning"), ("INT-SUBJ-004", "warning")]), base)
    assert got["outcome"] == "forbidden_code" and got["forbidden_raised"] == ["INT-SUBJ-004"] and not SP.probe_ok(got)


def test_the_repair_2_tamper_cases_are_registered_on_their_targets():
    """T23q drops an ST-UNDEC-003 (r7/ph-t13), T23r a table-operands INT-SUBJ-004 (r7/p7b), T23s rewrites a restated-binding check's
    detail (r7/p7b); the suite runs them in tests/overseer/test_stem_completion.py, each on its planted copy."""
    by_name = {c.name: c for c in T.CASES}
    for case, cls in (("T23q", "finding_missing"), ("T23r", "finding_missing"), ("T23s", "receipt_altered")):
        assert by_name[case].fault_class == cls and by_name[case].targets == T.STEM_TARGETS, case
    # STEM repair 3 (design section 34) appended T23t to the Given class and T23v to the wrong-given class, and STEM repair 4 (design
    # section 35) T23y to the Given class, and STEM repair 5 (design section 36) T23aa to the wrong-given class, and STEM repair 6
    # (design section 37) T23ah to the Given class and T23ai to the wrong-given class: each class still opens with exactly its earlier
    # cases, in order, and holds nothing else
    # STEM repair 10 (design section 41) appended T23bg to the Given class and T23bc to the wrong-given class, after these
    # STEM repair 11 (design section 42) appended T23bm to the givens class and T23bl to the wrong-given class
    assert SP.TAMPER_CASES["givens"] == ("T23c", "T23q", "T23t", "T23y", "T23ah", "T23av", "T23ax", "T23bg", "T23bm")
    # STEM repair 8 (design section 39) appended T23ap, T23aq and T23at to the class, after these
    assert SP.TAMPER_CASES["wrong_given"] == ("T23f", "T23r", "T23v", "T23aa", "T23ai", "T23ap", "T23aq", "T23at", "T23aw", "T23bc", "T23bl")
    assert "T23s" in SP.TAMPER_CASES["relay"]


# ============================================================================================ the pack beside the code
def _decided(text: str, profile: str, request: str = None, data: tuple = ()):
    from epinoic_logic.engine.policies import policy_config, policy_limits
    from epinoic_logic.engine.runner import verify
    from epinoic_logic.stem import build_document, clear_document_cache
    from epinoic_logic.stem.checks import build_checks
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value)
              for pc in plan.checks]
    return checks, [f.code for f in list(doc.findings) + list(plan.findings)]


def test_d31_states_what_the_given_and_table_checks_read_as_the_code_reads_it():
    """Each statement of D31's Given, table and silence paragraphs, executed against the STEM front end."""
    d31 = _pack_text("02-dossier.md").split("**D31 ", 1)[1].split("\n- **D32", 1)[0]
    for words in ('"Given", "Data", "Known" or "We know"', "the request's value of the same symbol", "the request's quantities of the same dimension",
                  "the request's percentages", "the request's numbers written with the same word", "the request's number it equals",
                  "is named by ST-UNDEC-003 (D32), one finding per statement", "A bare number is never failed", "zero, a condition the request states in words",
                  "a data-booklet constant written at the booklet's value", "is ST-PARSE-001, never read in part", "sets no Given against anything",
                  "An amount written after a currency sign", "is neither checked nor named",
                  "when the line takes as many different cells of that column as there are rows named", "**Silence is not a check.**",
                  "a failed Given check is INT-SUBJ-004", "Is 38 = 67? No.", "(so C(8) = 800)", "17 ≡ 2 (mod 5)", "3 times 4 = 12"):
        assert words in d31, words
    mi, ph, ess = R7["mai-t13"]["question"], R7["ph-t13"]["question"], R7["ess-t13"]["question"]
    ess_data = (ESS_TABLE,)
    cases = [
        ("Given: P = 5000 euros.", "mathematics_ai", mi, (), [("giv", "COUNTEREXAMPLE")], []),
        ("Given: t = 6 years.", "mathematics_ai", mi, (), [("giv", "COUNTEREXAMPLE")], []),
        ("Given: r = 3.9%.", "mathematics_ai", mi, (), [("giv", "COUNTEREXAMPLE")], []),
        ("Given: P = 4000.", "mathematics_ai", mi, (), [("giv", "ENTAILED")], []),
        ("Given: r = 0.036, n = 12.", "mathematics_ai", mi, (), [], ["ST-UNDEC-003"]),
        ("Given: t = 5.0 s.", "physics", ph, (), [], ["ST-UNDEC-003"]),
        ("Given: u = 0", "physics", ph, (), [], []), ("Given: g = 9.81 m s⁻²", "physics", ph, (), [], []),
        ("Given: P = €4000", "mathematics_ai", mi, (), [], []), ("Given: P = 4 000 euros", "mathematics_ai", mi, (), [], ["ST-PARSE-001"]),
        ("Given: P = 5000.", "mathematics_ai", None, (), [], []),
        ("Given: dissolved oxygen at C = 3.5 mg dm⁻³.", "ess", ess, ess_data, [("giv", "COUNTEREXAMPLE")], []),
        ("(a) Percentage decrease = (9.6 − 6.1) ÷ 9.6 × 100 = 36.5% decrease", "ess", ess, ess_data, [("eq", "ENTAILED"), ("giv", "ENTAILED"), ("giv", "COUNTEREXAMPLE")], []),
        ("The battery's emf is 9.0 V.", "physics", ph, (), [("giv", "COUNTEREXAMPLE")], []),
        ("Is 38 = 67? No.", "computer_science", None, (), [("cmp", "ENTAILED")], []), ("Is 38 = 67?", "computer_science", None, (), [], []),
        ("“t = 8 h: 820 − 20 = 800 ± 16 counts min⁻¹” (so C(8) = 800)", "mathematics_aa", "Q", (), [("eq", "ENTAILED"), ("res", "ENTAILED")], []),
        ("17 ≡ 2 (mod 5)", "mathematics_aa", None, (), [("eq", "ENTAILED")], []), ("So 3 times 4 = 12.", "mathematics_aa", None, (), [("eq", "ENTAILED")], []),
        ("The remainder when 17 is divided by 5 = 2.", "mathematics_aa", None, (), [], ["ST-PARSE-001"]),
        ("From c = n/V, n = cV = 0.10 × 0.0500 = 0.0050.", "chemistry", "Q", (), [("alg", "ENTAILED"), ("eq", "ENTAILED")], []),
        ("The fall is greatest at C (2.0 km = 2000 m).", "ess", "Q", (), [("cnv", "ENTAILED")], []),
    ]
    for text, profile, request, data, checks, codes in cases:
        assert _decided(text, profile, request, data) == (checks, codes), text
    d32 = _pack_text("02-dossier.md").split("**D32 ", 1)[1].split("\n## ", 1)[0]
    assert "| ST-UNDEC-003 | warning | a Given value could not be set against the request (D31)" in d32
    assert "an ST-UNDEC-003 dropped from a Given included" in d32


def test_i97_i98_and_the_master_prompt_teach_that_silence_is_not_a_check():
    inspection, prompt = _pack_text("03-inspection.md"), _pack_text("master_prompt.txt")
    i97 = inspection.split("**I97 ", 1)[1].split("\n- **I98", 1)[0]
    i98 = inspection.split("**I98 ", 1)[1].split("\n## ", 1)[0]
    assert "a STEM claim for its silence alone" in i97 and "Never read the silence as checked either" in i97
    for words in ("a Given value (Dossier guide D31", "whose `detail` begins \"stem_given\"", "or is listed by an ST-UNDEC-003 naming its claim",
                  "unless its value is zero or it is a data-booklet constant", "Neither: kind `finding_missing`", "(Evidence rule E8)"):
        assert words in i98, words
    assert "A STEM claim with no check and no ST code was not checked" in prompt and "Example 34" in prompt
    kinds = _pack_text("06-kinds-and-codes.md")
    assert "a Given value of a STEM answer with neither its check nor an ST-UNDEC-003 naming its claim (Inspection I98)" in kinds


def test_example_34_is_the_receipt_the_channel_gives_with_its_st_undec_003_dropped():
    """Example 34's request and answer through the channel: the receipt carries the two Given checks the example shows, detail for
    detail, and an ST-UNDEC-003 naming s1.1 for t = 5.0 s; the example's receipt is that receipt with the finding dropped (the
    tampering T23q makes), and its verdict accuses finding_missing showing the absence as E8 asks."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples(_pack_text("07-examples.md"))
    ex = next(e for e in examples if e.number == 34)
    assert table[34] == ("faulty", "`finding_missing`")
    request = ex.value("/transfers/0/payload/user_input")
    answer = ex.value("/transfers/1/payload/claims/0/claim_text")
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Physics", task_type="short_answer", selected_agent_ids=["stem-specialist"],
                           allowed_document_ids=[]))
    m, _, _ = hub.dispatch("t", "stem-specialist", request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="stem-specialist", report_id="rep-t-0")
    assert [fc.detail for fc in rc.formal_checks] == [ex.value(f"/transfers/1/receipt/formal_checks/{i}/detail") for i in (0, 1)]
    assert [(sf.code, list(sf.claim_ids)) for sf in rc.structural_findings] == [("ST-UNDEC-003", ["s1.1"])]
    assert "t = 5.0 s" in rc.structural_findings[0].message
    assert ex.value("/transfers/1/receipt/structural_findings") == []
    [acc] = ex.verdict["accusations"]
    assert acc["kind"] == "finding_missing" and acc["claim_ids"] == ["s1.1"] and ex.verdict["engine_statements"] == []
    assert acc["evidence"] == [{"pointer": "/transfers/1/payload/claims/0/claim_text", "quote": "t = 5.0 s"}, {"pointer": "/transfers/1/receipt/structural_findings"}]
