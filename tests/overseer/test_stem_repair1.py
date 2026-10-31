"""STEM repair 1 on the overseer's side (``docs/OVERSEER_DESIGN.md`` section 32, decision 61).

The independent test of the STEM completion found, besides the translator's STEM faults (``tests/stem/test_stem_repair1.py``):

* rule ``excerpt-prefix-units`` (``checks.translation``): a translation that encodes a quotation's figure converted into the
  unit without its prefix (50.0 cm³ as 0.0000500, Inspection I91: not a fault) was graded the claim assumed (OVS-TRN-006)
  and an ungrounded quotation (OVS-TRN-004), because the translator's ``figures_in_excerpt`` check finds no 0.0000500 in
  the excerpt. The located excerpt now states each of its figures under the prefixes of its unit for those two checks; a
  wrong conversion keeps both, and OVS-TRN-005 still names a number the answer does not state;
* rule ``related-statements`` (the channel, read by ``check-statements``): the failure finding of a failed substitution
  names the statement whose stated value it contradicts too, and the R2 rule recomposes those claims (a channel that drops
  them is OVS-RCPT-007: the tampering case T23p in ``tests/overseer/test_stem_completion.py``);
* the pack's recognition rules for the translation faults an agent alone can name (Inspection I78 items 7 to 9, I92): the
  probe agents now take their kind from the exported pack's own rule, never from the harness.

Every recorded answer stays a read-only input: the rounds built here are copies of the repository's material.
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import ovs_harness as H  # noqa: E402
import stem_probes as SP  # noqa: E402

from epinoic_logic.ir.schema import Problem  # noqa: E402
from epinoic_logic.overseer.checks import translation as T  # noqa: E402
from epinoic_logic.overseer.pack import PACK_VERSION, installed_pack_dir  # noqa: E402
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text  # noqa: E402
from epinoic_logic.translate.grounding import check_problem_grounding  # noqa: E402

from .test_stem_completion import material_round  # noqa: E402

# ============================================================================================ rule excerpt-prefix-units
THIO = SuppliedText(document_id="doc-thio", title="Rate of reaction (method)", author="Task data",
                    text="In each run, 50.0 cm3 of 0.100 mol dm-3 sodium thiosulfate solution is placed in a conical flask and 5.0 cm3 of 2.0 mol dm-3 "
                         "hydrochloric acid is added.")
EXCERPT = "50.0 cm3 of 0.100 mol dm-3 sodium thiosulfate"
CLAIM = "The volume of thiosulfate solution is 50.0 cm³ = 5.00 × 10⁻⁵ m³."


def thio_report() -> SpecialistReport:
    text = "(a) [1]\n\n" + CLAIM
    c = ClaimRecord(claim_id="g1.1", request_id="req-ch", task_id="task-ch", report_id="rep-ch-1", agent_id="chemistry-specialist", subject="Chemistry",
                    task_type="structured_question", claim_text=CLAIM, claim_role="quantitative", proposed_claim_kind="arithmetic", materiality="material")
    return SpecialistReport(report_id="rep-ch-1", request_id="req-ch", task_id="task-ch", agent_id="chemistry-specialist", subject="Chemistry",
                            task_type="structured_question", original_response=text, response_sha256=sha256_text(text), supplied_texts=[THIO], claims=[c],
                            created_at="2026-10-12T09:00:00Z")


def thio_problem(value: str, excerpt: str = EXCERPT) -> Problem:
    """The volume quoted from the method and encoded as ``value``; the conclusion is the specialist's inference."""
    q = {"kind": "quotation", "source_refs": [{"document_id": "doc-thio", "excerpt": excerpt}], "certainty": "established"}
    return Problem.model_validate({
        "problem_id": "p-thio", "request_id": "req-ch", "claim_id": "g1.1", "query": "entailment",
        "symbols": [{"name": "vol", "sort": "Real", "meaning": "volume of thiosulfate solution", "grounding": q}],
        "premises": [{"id": "P_vol", "expr": {"op": "eq", "left": {"op": "var", "name": "vol"}, "right": {"op": "real", "value": value}},
                      "label": "the volume of thiosulfate solution", "grounding": q}],
        "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "vol"}, "right": {"op": "real", "value": "0"}}, "label": "a volume",
                       "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}})


def test_an_excerpt_states_its_figures_under_the_prefixes_of_their_unit():
    got = T._excerpt_conversions(EXCERPT)
    for v in ("0.0000500", "0.0500", "50.0", "50000"):  # m³; dm³ and litres; cm³ and millilitres; mm³ and microlitres
        assert Fraction(v) in got, v
    for v in ("0.500", "5.00", "0.000500", "0.005", "500"):  # dL and cL are no targets; the wrong conversions are no conversions
        assert Fraction(v) not in got, v
    assert {Fraction(2400), Fraction("0.0024")} <= T._excerpt_conversions("R = 2.4 kΩ")
    assert {Fraction("0.15"), Fraction(150)} <= T._excerpt_conversions("a 15 cm ruler") and Fraction("1.5") not in T._excerpt_conversions("a 15 cm ruler")
    assert Fraction("0.00025") in T._excerpt_conversions("250 cm³ of water") and Fraction("0.25") in T._excerpt_conversions("250 cm³ of water")
    assert {Fraction(3200), Fraction("0.0032")} <= T._excerpt_conversions("a 3.2 kg trolley")
    assert T._excerpt_conversions("about 50 people") == set()  # no unit: nothing is read


@pytest.mark.parametrize("value, grounded", [("50.0", True), ("0.0000500", True), ("0.0500", True), ("0.000500", False), ("0.5", False), ("0.005", False)])
def test_a_premise_encoding_the_excerpt_s_figure_converted_by_prefix_is_grounded_for_the_overseer(value, grounded):
    """The translator's own check is unchanged (it finds no 0.0000500 in the excerpt); the overseer's re-run accepts the
    premise only when every missing figure is the excerpt's figure under another prefix of its unit: no OVS-TRN-004, and a
    transcription for rule grounded-transcription (never the claim assumed). A wrong conversion keeps both."""
    rep, p = thio_report(), thio_problem(value)
    _rerun, checks = check_problem_grounding(p, [THIO])
    failed = [c for c in checks if c.verified is False]
    assert [c.method for c in failed] == ([] if value == "50.0" else ["figures_in_excerpt"])
    _again, _checks, accepted = T.overseer_grounding(p, rep)
    assert accepted == ({"P_vol"} if grounded and value != "50.0" else set())
    overstated, absent = T.grounding_faults(SimpleNamespace(problem=p, grounding_checks=checks), rep)
    assert overstated == [] and [a[0] for a in absent] == ([] if grounded else ["P_vol"])
    assert [a.grounding.verified for a in T._regrounded(p, rep).premises] == [grounded]
    assert T.is_transcription("P_vol", p, None, rep, []) is grounded


def test_the_rule_reads_a_located_excerpt_only():
    """An excerpt the supplied text does not contain states nothing, converted or not."""
    rep, p = thio_report(), thio_problem("0.0000500", excerpt="60.0 cm3 of 0.100 mol dm-3 sodium thiosulfate")
    assert T.overseer_grounding(p, rep)[2] == set() and not T.is_transcription("P_vol", p, None, rep, [])
    _rerun, checks = check_problem_grounding(p, [THIO])
    assert "P_vol" in {a[0] for a in T.grounding_faults(SimpleNamespace(problem=p, grounding_checks=checks), rep)[1]}


def test_the_conversion_probes_measure_the_rule_end_to_end():
    """The contained run's conversion probes on the recorded chemistry translation: into the unit with no prefix it is a
    clean control; under another prefix OVS-TRN-005 names the number (a warning) and neither OVS-TRN-006 nor OVS-TRN-004
    may be raised; the translator's wrong conversion (0.5 for 50.0 cm³) keeps OVS-TRN-005 and OVS-TRN-004."""
    rows = {p.probe_id: p for p in SP.CONVERSION_PROBES}
    assert rows["units-translation-base-control"].kind == "control" and rows["units-translation-base-control"].translation == ("ch-t13", "g5.1", "number:any:50.0:0.0000500")
    prefix = rows["units-translation-prefix"]
    assert prefix.expected == ("OVS-TRN-005",) and set(prefix.forbidden) == {"OVS-TRN-006", "OVS-TRN-004"}
    wrong = SP.probe("chemistry-translation")
    assert wrong.translation == ("ch-t13", "g5.1", "number:any:50.0:0.5") and wrong.expected == ("OVS-TRN-005", "OVS-TRN-004")
    assert all(p in SP.PROBES for p in SP.CONVERSION_PROBES)


# ============================================================================================ rule related-statements, read by check-statements
@pytest.fixture(scope="module")
def material(tmp_path_factory) -> Path:
    return material_round(tmp_path_factory.mktemp("r7-material-repair1") / "rounds")


def test_a_failed_substitution_s_finding_names_the_contradicted_statement_and_the_overseer_agrees(tmp_path, material):
    """The wrong formula used consistently (V = ε + Ir in part (c)) is named where part (d) substitutes the value part (c)
    should have stated: the INT-SUBJ-001 finding names s4.3, the check's statement, then s4.2, the law the substitution
    evaluates (P = V²/R: STEM repair 8 names a failed substitution's law, design section 39), then s3.2, whose stated 14.1 V
    the substitution contradicts. Rule check-statements recomposes those claims from the channel's statement and the signed
    run: no OVS-RCPT-004, -005 or -007, and no OVS-* error."""
    probe = SP.probe("formulas-consistent")
    dest = H.mini_round(material, tmp_path / "planted", probe.stems)
    SP.edit_answers(dest, probe.edits)
    aud = H.new_auditor(H.keyring_for("arena"))
    try:
        rr = H.replay_round(dest, aud, genuine_only=True)
        rec = rr.channel(probe.key)
        audit, view = aud.audit(rec.uid), aud.view(rec.uid)
    finally:
        aud.close()
    assert not [f for f in audit.report.findings if f.code in ("OVS-RCPT-004", "OVS-RCPT-005", "OVS-RCPT-007")], \
        [(f.code, f.message[:200]) for f in audit.report.findings if f.code.startswith("OVS-RCPT")]
    assert not [f for f in audit.report.findings if f.severity == "error"], [(f.code, f.message[:160]) for f in audit.report.findings if f.severity == "error"]
    [t] = [t for t in view.transfers if t.kind in ("response", "response_text") and t.receipt is not None]
    failed = [f for f in t.receipt.findings if f.code == "INT-SUBJ-001"]
    assert len(failed) == 1 and failed[0].claim_ids == ["s4.3", "s4.2", "s3.2"], [(f.claim_ids, f.message[:120]) for f in failed]
    fc = next(c for c in t.receipt.formal_checks if c.formal_result_id == failed[0].formal_result_id)
    assert fc.claim_ids == ["s4.3"] and fc.satisfied is False


# ============================================================================================ the pack's recognition rules
@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return H.export_and_load_pack(tmp_path_factory.mktemp("pack-repair1") / "pack")[0]


def test_every_probe_agent_takes_its_kind_from_the_exported_pack_s_own_rule(pack):
    """No probe agent is handed its kind: each translation probe names the words of the pack rule that recognises its
    fault, and the kind it accuses with is the first one that rule gives in the exported pack's system text."""
    with_rule = [p for p in SP.PROBES if p.agent_rule]
    # STEM repair 2: the table figures converted wrongly (units-translation-table-wrong) is accused by a probe agent too; STEM repair 12
    # (design section 43): the four conclusions a writer's-own premise restates in affine or scaled form, accused as translation_circular
    repair12 = {"equations-translation-restated-affine", "maths-translation-restated-scaled", "physics-translation-restated-linear",
                "boolean-translation-restated-affine"}
    assert {p.probe_id for p in with_rule} == {p.probe_id for p in SP.TRANSLATION_PROBES} | {"units-translation-table-wrong"} | repair12
    for p in with_rule:
        assert SP.pack_kind(pack, p.agent_rule) == p.agent_kind, (p.probe_id, p.agent_rule, SP.pack_kind(pack, p.agent_rule))


def test_pack_kind_finds_no_kind_where_the_pack_states_no_rule(pack):
    assert SP.pack_kind(None, "Another relation encoded") is None and SP.pack_kind(pack, None) is None
    assert SP.pack_kind(pack, "A rule no pack states, word for word") is None
    fake = SimpleNamespace(system_text=lambda: "- **R1 First rule.** No kind here.\n- **R2 Second rule.** kind `translation_unfaithful`.")
    assert SP.pack_kind(fake, "First rule") is None  # the kind after it belongs to the next rule
    assert SP.pack_kind(fake, "Second rule") == "translation_unfaithful"


def test_the_inspection_rules_recognise_the_agent_only_stem_translation_faults():
    inspection = (installed_pack_dir(PACK_VERSION) / "03-inspection.md").read_text(encoding="utf-8")
    i78 = inspection.split("**I78 ", 1)[1].split("\n- **I79", 1)[0]
    for n, words in ((7, "Another stated given substituted"), (8, "Another relation encoded"), (9, "Two incompatible quantities combined")):
        assert f"  {n}. **{words}.**" in i78, words
    assert i78.rstrip().endswith("No check compares meanings, so the accusation goes to human review.") and "kind `translation_unfaithful`" in i78.rsplit("9. ", 1)[1]
    dossier = (installed_pack_dir(PACK_VERSION) / "02-dossier.md").read_text(encoding="utf-8")
    d31 = dossier.split("**D31 ", 1)[1].split("\n- **D32", 1)[0]
    assert ("The finding of a failed substitution names the claims of its statement first, then, for each symbol it substitutes whose value one "
            "earlier statement alone states, that statement's claims") in d31


def test_example_33_teaches_another_stated_given_substituted():
    """Example 33: every number of the problem is stated (the supplied table and the claim), so no check names it; the premise
    D subtracts the 25 °C uptake where the claim's working subtracts the 20 °C one, and the verdict accuses it as
    translation_unfaithful, quoting the working and pointing at the premises, with no engine statement."""
    from .test_knowledge_examples import parse_examples
    _shared, examples, table = parse_examples((installed_pack_dir(PACK_VERSION) / "07-examples.md").read_text(encoding="utf-8"))
    ex = next(e for e in examples if e.number == 33)
    assert table[33] == ("faulty, decided by no check", "`translation_unfaithful`") and ex.type.startswith("faulty")
    claim = ex.value("/transfers/1/payload/claims/0/claim_text")
    data = ex.value("/transfers/0/payload/supplied_texts/0/text")
    premises = ex.value("/transfers/1/receipt/outcomes/0/translation/problem/premises")
    d = next(p for p in premises if p["id"] == "D")
    assert d["expr"]["right"]["args"][0] == {"op": "sub", "left": {"op": "var", "name": "t30"}, "right": {"op": "var", "name": "t25"}}
    assert "(80 − 40)" in claim and "25 | 58" in data
    numbers = {p["expr"]["right"]["value"] for p in premises if p["expr"]["right"].get("op") == "int"}
    assert numbers == {"40", "58", "80"} and all(n in data for n in numbers)
    [acc] = ex.verdict["accusations"]
    assert acc["kind"] == "translation_unfaithful" and ex.verdict["engine_statements"] == []
    assert {"pointer": "/transfers/1/payload/claims/0/claim_text", "quote": "(80 − 40) ÷ 40 × 100"} in acc["evidence"]
