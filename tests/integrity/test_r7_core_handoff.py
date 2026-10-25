"""Integrity regressions from the round-7 arena fixers' hand-off (owner: core).

* A figure that ends a sentence before another sentence ("Sales were 300. Costs rose.") made the unit reader raise
  IndexError, so every INT-LEDGER finding of a correct synthesis was lost behind INT-INTERNAL-001; the same unit run read
  across the full stop gave a false changed unit ("0.025 kg. L").
* A verbatim copy was charged a figure swap across two parallel sentences (``aligned_changes(t, t)`` was not empty).
* The minus sign U+2212 and the ASCII hyphen-minus were two signs in the figure comparison.
* A power written with its exponent ("10³", "10^6") was no figure at all, so 10³ changed to 10⁶ passed.
* A synthesized claim's evidence references were never checked against the documents they name.
* Two correct lines that compute one resistance from rounded intermediates (24.0 ohm to 3 s.f. both) were charged as a
  contradiction (INT-CONFLICT-001), and a synthesis merging them with INT-CONFLICT-002.
"""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity.cross_check import at_stated_precision, check_cross_report_consistency
from epinoic_logic.integrity.ledger import (
    _figure_differences, _unit_figures, aligned_changes, check_synthesis_ledger, evidence_ref_problems, unit_differences,
)
from epinoic_logic.ir.schema import Problem, SourceRef
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def _report(rid: str, agent: str, claims: list[tuple[str, str]], *, supplied: list[SuppliedText] = (), refs: dict[str, list[SourceRef]] = None) -> SpecialistReport:
    text = " ".join(t for _c, t in claims)
    base = dict(request_id="req-x", task_id="t-x", report_id=rid, agent_id=agent, subject="Business Management", task_type="short_answer")
    refs = refs or {}
    return SpecialistReport(**base, original_response=text, response_sha256=sha256_text(text), created_at="2026-10-11T10:00:00Z", supplied_texts=list(supplied),
                            claims=[ClaimRecord(**base, claim_id=c, claim_text=t, claim_role="point", materiality="material", source_refs=refs.get(c, [])) for c, t in claims])


def _synthesis(sources: list[str], claims: list[tuple[str, str, list[str], str]], *, refs: dict[str, list[SourceRef]] = None) -> Synthesis:
    refs = refs or {}
    sc = [SynthesizedClaim(claim_id=c, text=t, certainty="established", source_claim_ids=s, transformation=tr, evidence_refs=refs.get(c, [])) for c, t, s, tr in claims]
    text = " ".join(c.text for c in sc)
    return Synthesis(synthesis_id="syn-x", request_id="req-x", task_id="t-x", combinator_agent_id="comb", source_report_ids=sources, claims=sc, ledger=[],
                     text=text, text_sha256=sha256_text(text), created_at="2026-10-11T11:00:00Z")


# ------------------------------------------------------------------ blocker: a unit run never starts at or crosses a sentence stop


@pytest.mark.parametrize("text", ["Sales were 300. Costs rose.", "The ratio is 1.60. Next it falls.", "It was 300 ... later", "It was 300.\nCosts rose."])
def test_a_figure_ending_a_sentence_never_raises_and_reads_no_unit(text):
    figures = _unit_figures(text)
    assert figures and all(unit is None for _v, unit, _s, _e, _n in figures)
    assert unit_differences(text, []) == []


def test_a_unit_run_is_cut_at_the_sentence_stop():
    assert unit_differences("The mass is 0.025 kg. L is the length.", ["The mass is 0.025 kg.", "L is the length."]) == []
    assert _unit_figures("The mass is 0.025 kg. L is the length.")[0][2] == "0.025 kg"
    # control: a changed unit is still named
    assert unit_differences("The mass is 0.025 g. L is the length.", ["The mass is 0.025 kg."])


def test_a_correct_synthesis_whose_figure_ends_a_sentence_gets_its_ledger():
    report = _report("rep-1", "business-management-specialist", [("g1", "The current ratio is 2.40 / 1.50 = 1.60. Acid-test ratio is 0.90.")])
    synthesis = _synthesis(["rep-1"], [("s0", "The current ratio is 2.40 / 1.50 = 1.60. Acid-test ratio is 0.90.", ["g1"], "carried")])
    findings = check_synthesis_ledger([report], synthesis)
    assert "INT-INTERNAL-001" not in codes(findings) and "INT-LEDGER-023" not in codes(findings)
    # control: a changed figure is still named, so the ledger really ran
    wrong = _synthesis(["rep-1"], [("s0", "The current ratio is 2.40 / 1.50 = 1.70. Acid-test ratio is 0.90.", ["g1"], "paraphrased")])
    assert "INT-LEDGER-023" in codes(check_synthesis_ledger([report], wrong))


# ------------------------------------------------------------------ a verbatim copy is no figure swap


PARALLEL = "From January to July the price multiplied by 1.55 per month; from July to September by 20.9 per month."


def test_aligned_changes_of_a_text_with_itself_is_empty():
    assert aligned_changes(PARALLEL, PARALLEL) == ([], [])


@pytest.mark.parametrize("text", [
    PARALLEL,
    "In 1990 output rose by 4 per cent; in 1991 output rose by 7 per cent; in 1992 it fell by 2 per cent.",
    "The ratio was 1.6 in March. The ratio was 1.2 in June. The ratio was 0.9 in September.",
    "Legal means did most of the consolidating. Violent means did the rest of the consolidating.",
])
def test_aligned_changes_is_empty_for_every_verbatim_copy(text):
    assert aligned_changes(text, text) == ([], [])
    assert aligned_changes(f"{text} It is copied.", text) == ([], [])


def test_a_real_swap_between_parallel_sentences_is_still_named():
    swapped = "From January to July the price multiplied by 20.9 per month; from July to September by 20.9 per month."
    figures, _meaning = aligned_changes(swapped, PARALLEL)
    assert any("20.9" in d and "1.55" in d for d in figures)


# ------------------------------------------------------------------ one minus sign, whatever its glyph


@pytest.mark.parametrize("syn,src", [
    ("The payment is PMT = −352.19 euros.", "The payment is PMT = -352.19 euros."),
    ("The payment is PMT = -352.19 euros.", "The payment is PMT = −352.19 euros."),
    ("PMT = −352.1907… euros and z = −1.28155", r"PMT = $-352.1907\ldots$ euros and z = $-1.28155\ldots$"),
    ("The change is ‒4.5 per cent.", "The change is -4.5 per cent."),
])
def test_a_minus_written_with_another_glyph_is_the_same_figure(syn, src):
    assert _figure_differences(syn, [src]) == ([], [], [])


def test_a_dropped_sign_and_a_range_dash_are_read_as_before():
    assert _figure_differences("the gap is −5 °C", ["the gap is 5 °C"])[0] == ["-5"]
    assert _figure_differences("from 1990–2000 it rose", ["from 1990-2000 it rose"]) == ([], [], [])


@pytest.mark.parametrize("minus", ["−", "-"])
def test_a_signed_source_figure_restated_as_its_magnitude_is_the_same_figure(minus):
    """Reading U+2212 as a sign must not turn the magnitude a synthesis restates with a direction word ("falls by 12.50%"
    for "= −12.50%") into an introduced figure (a recorded round-7 group synthesis did, once the glyph was read)."""
    src = f"Percentage change in quantity demanded = (105 − 120) ÷ 120 × 100 = {minus}12.50%"
    assert _figure_differences("Quantity demanded falls by 12.50%.", [src])[0] == []
    assert _figure_differences("A PED of 0.67 in absolute value.", [f"PED = {minus}12.50 ÷ 18.75 = {minus}0.67"])[0] == []
    # a sign the synthesis adds, or reverses, is still a changed figure
    assert _figure_differences(f"Quantity demanded changes by {minus}12.50%.", ["Quantity demanded falls by 12.50%."])[0] == ["-12.50"]


# ------------------------------------------------------------------ a power is one figure


def test_a_changed_power_of_ten_is_a_changed_figure():
    introduced, dropped, _r = _figure_differences("The volume is 10⁶ m³.", ["The volume is 10³ m³."])
    assert introduced == ["10⁶"] and dropped == ["10³"]
    report = _report("rep-1", "physics-specialist", [("g1", "The volume is 10³ m³.")])
    assert "INT-LEDGER-023" in codes(check_synthesis_ledger([report], _synthesis(["rep-1"], [("s0", "The volume is 10⁶ m³.", ["g1"], "paraphrased")])))


@pytest.mark.parametrize("syn", ["The volume is 10³ m³.", "The volume is 10^3 m³.", "The volume is 10^{3} m³.", "The volume is 1000 m³."])
def test_one_power_in_any_spelling_is_one_figure(syn):
    assert _figure_differences(syn, ["The volume is 10³ m³."]) == ([], [], [])


def test_a_changed_unit_exponent_is_a_changed_unit():
    assert unit_differences("The rate is 3 min⁻².", ["The rate is 3 min⁻¹."])


# ------------------------------------------------------------------ evidence references are checked against the documents they name


LUMA = SuppliedText(document_id="doc-luma", title="Luma case study", text="Luma Ltd does not have much cash to spare. Its sales rose by 4 per cent.")


def _evidence_case(refs: list[SourceRef]):
    report = _report("rep-1", "business-management-specialist", [("g1", "Luma does not have much cash to spare.")], supplied=[LUMA])
    synthesis = _synthesis(["rep-1"], [("s0", "Luma does not have much cash to spare.", ["g1"], "paraphrased")], refs={"s0": refs})
    return report, synthesis


def test_an_invented_excerpt_credited_to_a_supplied_text_is_int_ledger_025():
    report, synthesis = _evidence_case([SourceRef(document_id="doc-luma", locator="para 9", excerpt="profits will double next year")])
    findings = check_synthesis_ledger([report], synthesis, allowed_document_ids=["doc-luma"])
    hit = [f for f in findings if f.code == "INT-LEDGER-025"]
    assert hit and "profits will double next year" in hit[0].message and "invented" in hit[0].message and hit[0].severity == "error"


def test_a_reference_to_a_document_outside_the_task_is_int_ledger_025():
    report, synthesis = _evidence_case([SourceRef(document_id="doc-nowhere", excerpt="does not have much cash to spare")])
    findings = check_synthesis_ledger([report], synthesis, allowed_document_ids=["doc-luma"])
    assert any(f.code == "INT-LEDGER-025" and "doc-nowhere" in f.message for f in findings)


def test_an_excerpt_credited_to_the_wrong_document_is_named_misattributed():
    peer = SuppliedText(document_id="peer:maa-e1a", author="mathematics-specialist", text="The model is not a good fit for 1923.")
    report = _report("rep-1", "history-specialist", [("h1", "The model fails for 1923.")], supplied=[LUMA, peer])
    synthesis = _synthesis(["rep-1"], [("s0", "The model fails for 1923.", ["h1"], "paraphrased")],
                           refs={"s0": [SourceRef(document_id="doc-luma", excerpt="the model is not a good fit for 1923")]})
    problems = evidence_ref_problems(synthesis, [report], allowed_document_ids=["doc-luma", "peer:maa-e1a"])
    assert problems and "misattributed" in problems[0][1] and "peer:maa-e1a" in problems[0][1]


def test_genuine_and_copied_references_pass():
    report, synthesis = _evidence_case([SourceRef(document_id="doc-luma", excerpt="does not have much cash to spare")])
    assert "INT-LEDGER-025" not in codes(check_synthesis_ledger([report], synthesis, allowed_document_ids=["doc-luma"]))
    # a reference copied unchanged from its cited source claim is that source's (checked on the report's own delivery)
    ref = SourceRef(document_id="doc-other", locator="p. 3", excerpt="words of a text not supplied here")
    report = _report("rep-1", "business-management-specialist", [("g1", "Luma does not have much cash to spare.")], supplied=[LUMA], refs={"g1": [ref]})
    synthesis = _synthesis(["rep-1"], [("s0", "Luma does not have much cash to spare.", ["g1"], "paraphrased")], refs={"s0": [ref]})
    assert evidence_ref_problems(synthesis, [report], allowed_document_ids=["doc-luma"]) == []
    # a document of the plan's scope whose text was not supplied: known, its excerpt cannot be checked
    report, synthesis = _evidence_case([SourceRef(document_id="doc-library", excerpt="anything at all")])
    assert evidence_ref_problems(synthesis, [report], allowed_document_ids=["doc-luma", "doc-library"]) == []


# ------------------------------------------------------------------ figures stated to their precision are pooled as intervals


def _resistance(cid: str, premise: dict, conclusion_lo: str, conclusion_hi: str, label: str) -> Problem:
    return Problem.model_validate({
        "ir_version": "1.0", "problem_id": f"ph-e1-{cid}", "request_id": "req-ph-e1", "claim_id": cid, "query": "entailment",
        "symbols": [{"name": "mains_volts", "sort": "Real", "meaning": "mains voltage in volts (task: 230 V)"},
                    {"name": "heater_res", "sort": "Real", "meaning": "resistance of the heating element in ohms"}],
        "premises": [{"id": "pv", "expr": {"op": "eq", "left": {"op": "var", "name": "mains_volts"}, "right": {"op": "real", "value": "230"}},
                      "grounding": {"kind": "arithmetic_fact", "source_refs": [], "certainty": "established"}},
                     {"id": "link", "expr": premise, "grounding": {"kind": "specialist_inference", "source_refs": [], "certainty": "established"}}],
        "conclusion": {"id": "claim_r", "label": label, "expr": {"op": "and", "args": [
            {"op": "ge", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": conclusion_lo}},
            {"op": "lt", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": conclusion_hi}}]}},
    })


#: R = V/I = 230 V / 9.57 A = 24.0 ohm (the current 9.57 A is itself 2200/230 to 3 s.f.)
S21 = _resistance("s2.1", {"op": "eq", "left": {"op": "mul", "args": [{"op": "real", "value": "9.57"}, {"op": "var", "name": "heater_res"}]}, "right": {"op": "var", "name": "mains_volts"}},
                  "23.95", "24.05", "R = 230 V / 9.57 A = 24.0 ohm to 3 s.f.")
#: Check: R = V^2/P = (230 V)^2 / 2200 W = 24.0 ohm
S22 = _resistance("s2.2", {"op": "eq", "left": {"op": "mul", "args": [{"op": "real", "value": "2200"}, {"op": "var", "name": "heater_res"}]},
                           "right": {"op": "mul", "args": [{"op": "var", "name": "mains_volts"}, {"op": "real", "value": "230"}]}},
                  "23.95", "24.05", "R = (230 V)^2 / 2200 W = 24.0 ohm to 3 s.f.")


def test_two_correct_resistance_lines_at_three_significant_figures_are_no_contradiction():
    _res, findings = check_cross_report_consistency([S21, S22], request_id="req-ph-e1", config=CFG)
    assert "INT-CONFLICT-001" not in codes(findings)


def test_figures_that_differ_at_their_stated_precision_still_contradict():
    other = _resistance("s9.1", {"op": "eq", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "26.1"}}, "26.05", "26.15", "R = 26.1 ohm")
    _res, findings = check_cross_report_consistency([S21, other], request_id="req-ph-e1", config=CFG)
    assert any(f.code == "INT-CONFLICT-001" and set(f.claim_ids) == {"s2.1", "s9.1"} for f in findings)
    near = [_resistance(c, {"op": "eq", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": v}}, "0", "100", f"R = {v} ohm")
            for c, v in (("a1", "24.03"), ("b1", "24.05"))]
    _res, findings = check_cross_report_consistency(near, request_id="req-ph-e1", config=CFG)
    assert any(f.code == "INT-CONFLICT-001" for f in findings)


def test_integer_contradictions_are_read_exactly():
    a = _resistance("a1", {"op": "eq", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "24"}}, "0", "100", "R = 24")
    b = _resistance("b1", {"op": "eq", "left": {"op": "var", "name": "heater_res"}, "right": {"op": "real", "value": "25"}}, "0", "100", "R = 25")
    assert at_stated_precision([a.model_copy(update={"conclusion": None, "query": "consistency"})]) is None
    _res, findings = check_cross_report_consistency([a, b], request_id="req-ph-e1", config=CFG)
    assert any(f.code == "INT-CONFLICT-001" for f in findings)


def test_the_stated_precision_reading_is_data_and_keeps_divisors_constant():
    div = _resistance("d1", {"op": "eq", "left": {"op": "div", "left": {"op": "var", "name": "mains_volts"}, "right": {"op": "real", "value": "9.57"}},
                             "right": {"op": "var", "name": "heater_res"}}, "23.95", "24.05", "R = V / 9.57")
    relaxed = at_stated_precision([div])
    assert relaxed is not None
    dumped = relaxed[0].model_dump(mode="json")
    assert dumped["premises"][1]["expr"]["left"]["right"] == {"op": "real", "value": "9.57"}  # the divisor stays a constant
    assert any(s["name"].startswith("rnd0_") for s in dumped["symbols"])  # the conclusion's bounds read at their precision


# ------------------------------------------------------------------ security-1: an envelope signature of any text


@pytest.mark.parametrize("forged", ["é" * 64, "\ud83d" * 64, "Z" * 64, "0" * 63, ""])
def test_an_envelope_signature_of_any_text_is_invalid_and_never_raises(forged):
    """``hmac.compare_digest`` raised TypeError on a non-ASCII forged signature in ``verify_message`` (and so in
    ``MessageLog.accept``); a signature that is not 64 lowercase hex characters is now simply invalid (INT-ENV-006)."""
    from epinoic_logic.integrity import AgentMessage, AgentRole, MessageLog
    from epinoic_logic.integrity.contracts import payload_hash, sign_message, verify_message
    key = b"r7-core-envelope-key-0123456789abcd"
    payload = {"report_id": "rep-1", "claims": 3}
    m = AgentMessage(message_id="m1", request_id="req-1", task_id="task-1", sender_agent_id="physics-specialist", sender_role=AgentRole.SPECIALIST,
                     recipient_role=AgentRole.COMBINATOR, contract="specialist_report/1.0", payload=payload, payload_sha256=payload_hash(payload),
                     created_at="2026-10-11T10:00:00Z")
    signed = sign_message(m, key, "k")
    assert verify_message(signed, key)
    bad = signed.model_copy(update={"signature": forged})
    assert verify_message(bad, key) is False
    assert [f.code for f in MessageLog(signing_key=key, request_id="req-1").accept(bad)] == ["INT-ENV-006"]
