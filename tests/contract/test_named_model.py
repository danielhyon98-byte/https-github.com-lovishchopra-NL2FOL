"""The shared model of the argument diagnosis (``epinoic_logic.named``, rules argdiag-1): the canonical labels, the code
table, the records and the helpers. These pin the contract every fixer builds on; no detection logic is tested here."""
from __future__ import annotations

import json
import re
from typing import get_args

import pytest
from pydantic import ValidationError

from epinoic_logic import named as N
from epinoic_logic.integrity.contracts import IntegrityFinding
from epinoic_logic.translate.contracts import StructuralFinding

#: The 28 canonical labels, exactly as the corpus scores them (written out here, not imported).
CANONICAL = (
    "leap_in_logic", "affirming_the_consequent", "denying_the_antecedent", "hasty_generalisation", "false_dilemma",
    "circular_reasoning", "equivocation", "causal_leap", "bare_assertion", "contradiction", "vacuous_argument",
    "lack_of_evidence", "unchecked_source", "source_mismatch", "altered_quotation", "invented_figure",
    "cherry_picked_data", "uncheckable_authority", "stem_wrong_formula", "stem_unit_error", "stem_dimension_error",
    "stem_arithmetic_slip", "stem_invalid_step", "stem_rounding_changes_conclusion", "stem_extrapolation",
    "stem_missing_working", "stem_contradictory_givens", "stem_symbol_conflict",
)

#: The whole table: code -> (label, maximum severity, default layer, owner). Channel codes carry no label.
TABLE = {
    "ARG-LINK-001": ("leap_in_logic", "info", "engine", "b"),
    "ARG-FACT-001": ("lack_of_evidence", "info", "engine", "b"),
    # repair round 2: a rule the writer states from subject knowledge (marked as stated) is no missing link
    "ARG-LINK-002": ("unchecked_source", "info", "engine", "b"),
    "ARG-NS-001": ("leap_in_logic", "warning", "engine", "b"),
    "ARG-NS-002": ("leap_in_logic", "warning", "engine", "b"),
    "ARG-PART-001": ("leap_in_logic", "info", "engine", "b"),
    "ARG-INV-001": ("leap_in_logic", "warning", "engine", "b"),
    # repair round 3 (V3-LEAP-INFO-ONLY): an unbridged leap between two named things, read in the answer (claim layer)
    "ARG-NS-003": ("leap_in_logic", "warning", "claim", "b"),
    "ARG-REFUTE-001": ("contradiction", "warning", "engine", "b"),
    "ARG-AC-001": ("affirming_the_consequent", "warning", "engine", "b"),
    "ARG-DA-001": ("denying_the_antecedent", "warning", "engine", "b"),
    "ARG-FD-001": ("false_dilemma", "warning", "engine", "b"),
    "ARG-HG-001": ("hasty_generalisation", "warning", "engine", "b"),
    "ARG-CL-001": ("causal_leap", "warning", "engine", "b"),
    "ARG-CIRC-001": ("circular_reasoning", "warning", "engine", "b"),
    "ARG-CIRC-002": ("circular_reasoning", "warning", "engine", "b"),
    "ARG-CIRC-003": ("circular_reasoning", "warning", "engine", "b"),
    "ARG-EQ-002": ("equivocation", "warning", "engine", "b"),
    "ARG-EQ-003": ("equivocation", "warning", "engine", "b"),
    "ARG-VAC-001": ("vacuous_argument", "warning", "engine", "b"),
    "ARG-CONTRA-001": ("contradiction", "error", "engine", "b"),
    "ARG-EQ-001": ("equivocation", "warning", "claim", "b"),
    "ARG-BARE-001": ("bare_assertion", "warning", "report", "b"),
    "EVD-SRC-001": ("unchecked_source", "warning", "claim", "a"),
    "EVD-SRC-003": ("source_mismatch", "warning", "claim", "a"),
    "EVD-SRC-004": ("unchecked_source", "info", "claim", "a"),
    "EVD-SRC-005": ("unchecked_source", "warning", "claim", "a"),
    "EVD-LACK-001": ("lack_of_evidence", "warning", "claim", "a"),
    "EVD-FIG-001": ("invented_figure", "warning", "claim", "a"),
    "EVD-AUTH-001": ("uncheckable_authority", "warning", "claim", "a"),
    "EVD-CHERRY-001": ("cherry_picked_data", "warning", "claim", "a"),
    "EVD-SRC-002": ("unchecked_source", "info", "report", "a"),
    "EVD-LACK-002": ("lack_of_evidence", "info", "report", "a"),
    "EVD-SRC-006": ("source_mismatch", "warning", "report", "a"),   # repair round 2 (NAME-E04A)
    "ST-REF-001": ("stem_wrong_formula", "warning", "stem", "c"),
    "ST-REF-002": ("stem_wrong_formula", "warning", "stem", "c"),
    "ST-UNIT-003": ("stem_unit_error", "warning", "stem", "c"),
    "ST-STEP-001": ("stem_invalid_step", "warning", "stem", "c"),
    "ST-STEP-002": ("stem_invalid_step", "info", "stem", "c"),
    # repair round 3 (V3-H2-STEM-MISSES): a rewrite inside a chain whose two sides differ at a sample point of the unknown
    "ST-STEP-003": ("stem_invalid_step", "warning", "stem", "c"),
    "ST-ROUND-001": ("stem_rounding_changes_conclusion", "warning", "stem", "c"),
    "ST-RANGE-001": ("stem_extrapolation", "warning", "stem", "c"),
    "ST-WORK-001": ("stem_missing_working", "warning", "stem", "c"),
    "ST-GIVEN-002": ("stem_contradictory_givens", "warning", "stem", "c"),
    "ST-GIVEN-003": ("stem_contradictory_givens", "warning", "stem", "c"),
    "ST-GIVEN-004": ("stem_contradictory_givens", "warning", "stem", "c"),
    "ST-SCOPE-002": ("stem_symbol_conflict", "warning", "stem", "c"),
    "INT-ARG-001": (None, "error", "channel", "contract"),
    "INT-REQ-017": (None, "warning", "channel", "d"),
    "INT-XENC-001": (None, "warning", "channel", "d"),
}


def diag(code="ARG-AC-001", **kw):
    kw.setdefault("derivation", "ir_structure")
    kw.setdefault("message", "the writer's link is the converse of the stated rule")
    return N.named_diagnostic(code, **kw)


# --------------------------------------------------------------------------------------------- the vocabulary


def test_the_28_labels_are_the_canonical_list_in_the_literal_and_the_tuple():
    assert N.DEFECT_LABELS == CANONICAL and len(set(CANONICAL)) == 28
    assert get_args(N.DefectLabel) == CANONICAL


def test_the_code_table_is_complete_and_every_row_has_a_canonical_label_a_layer_and_an_owner():
    assert set(N.NAMED_CODES) == set(TABLE)
    for code, (label, sev, layer, owner) in TABLE.items():
        spec = N.NAMED_CODES[code]
        assert re.fullmatch(r"[A-Z]{2,5}-[A-Z]{2,8}-[0-9]{3}", code) and spec.code == code
        assert (spec.defect, spec.max_severity, spec.layer, spec.owner) == (label, sev, layer, owner), code
        assert spec.defect is None if spec.finding_only else spec.defect in CANONICAL
        assert spec.layer in spec.layers and set(spec.layers) <= set(N.LAYERS)
        assert spec.meaning and len(spec.meaning) <= 300
    assert {c for c, s in N.NAMED_CODES.items() if s.finding_only} == {"INT-ARG-001", "INT-REQ-017", "INT-XENC-001"}
    assert N.NAMED_CODES["ARG-CIRC-001"].layers == ("engine", "claim")
    assert N.NAMED_CODES["ARG-CONTRA-001"].stated_by == "INT-REQ-007"
    assert len({s.precedence for s in N.NAMED_CODES.values()}) == len(N.NAMED_CODES)
    with pytest.raises(TypeError):
        N.NAMED_CODES["ARG-NEW-001"] = N.NAMED_CODES["ARG-AC-001"]  # type: ignore[index]


def test_the_cap_scopes_of_the_table():
    exempt = {c for c, s in N.NAMED_CODES.items() if c.startswith(("ARG-", "EVD-")) and not s.capped_on_ambiguous}
    assert exempt == {"ARG-EQ-001", "ARG-EQ-002", "ARG-EQ-003"}
    assert not any(s.capped_on_ambiguous for c, s in N.NAMED_CODES.items() if c.startswith(("ST-", "INT-")))
    scopes = {c: s.warning_scope for c, s in N.NAMED_CODES.items() if s.warning_scope != "always"}
    assert scopes == {"EVD-SRC-001": "source_bound", "EVD-LACK-001": "source_bound", "EVD-FIG-001": "source_bound_or_data"}
    assert {c for c, s in N.NAMED_CODES.items() if s.generic} == {"ARG-NS-001", "ARG-NS-002", "ARG-INV-001", "ARG-NS-003"}


# --------------------------------------------------------------------------------------------- the records


def test_named_diagnostic_takes_label_and_layer_from_the_table_and_lowers_a_severity_but_never_raises_it():
    d = diag()
    assert (d.defect, d.layer, d.severity, d.rule_version) == ("affirming_the_consequent", "engine", "warning", "argdiag-2")
    assert diag(severity="info").severity == "info"                                   # lowered on request
    assert diag("ARG-LINK-001", severity="warning").severity == "info"                # never raised above the table
    assert diag("ARG-CONTRA-001").severity == "error" and diag("ARG-CONTRA-001", severity="warning").severity == "warning"
    assert diag("ARG-CIRC-001", layer="claim").layer == "claim"
    with pytest.raises(ValidationError):
        diag("ARG-AC-001", layer="claim")                                             # not a layer the table allows
    with pytest.raises(ValueError):
        N.named_diagnostic("ARG-XX-001", derivation="ir_structure", message="x")      # outside the table
    with pytest.raises(ValueError):
        N.named_diagnostic("INT-ARG-001", derivation="ir_structure", message="x")     # a receipt finding only
    with pytest.raises(ValueError):
        diag(severity="fatal")


def test_a_directly_built_record_obeys_the_table():
    base = dict(derivation="ir_structure", message="m", layer="engine")
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-LINK-001", defect="leap_in_logic", severity="warning", **base)        # above the maximum
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="leap_in_logic", severity="warning", **base)          # another code's label
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-ZZ-001", defect="leap_in_logic", severity="info", **base)             # the new vocabulary is closed
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="INT-XENC-001", defect="contradiction", severity="warning", **{**base, "layer": "channel"})
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="arg-ac-001", defect="affirming_the_consequent", severity="info", **base)
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="not_a_label", severity="info", **base)
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="affirming_the_consequent", severity="info", capped_from="warning", **base)  # no reason
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="affirming_the_consequent", severity="warning", capped_from="info",
                          cap_reason="ambiguous_translation", **base)                                     # a cap only lowers
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="affirming_the_consequent", severity="info", capped_from="error",
                          cap_reason="ambiguous_translation", **base)                                     # never above the maximum
    # an existing finding code given a label (a finding turned into a diagnostic) is accepted at its own severity
    d = N.NamedDiagnostic(code="INT-REQ-003", defect="altered_quotation", severity="error", layer="channel", derivation="source_text", message="m")
    assert d.severity == "error"


def test_bounds_of_a_record():
    with pytest.raises(ValidationError):
        N.NamedDiagnostic(code="ARG-AC-001", defect="affirming_the_consequent", severity="info", layer="engine", derivation="ir_structure", message="x" * 601)
    assert len(diag(message="x" * 5000).message) <= N.MAX_MESSAGE_CHARS   # named_diagnostic cuts, never raises on length
    span = N.EvidenceSpan(source_kind="claim", source_id="c", text="t")
    with pytest.raises(ValidationError):
        diag(evidence=[span] * (N.MAX_EVIDENCE + 1))
    with pytest.raises(ValidationError):
        diag(derived_problem_digests=["a" * 64] * (N.MAX_DERIVED_DIGESTS + 1))
    with pytest.raises(ValidationError):
        diag(derived_problem_digests=["not-a-digest"])
    with pytest.raises(ValidationError):
        diag(derivation="a_guess")
    with pytest.raises(ValidationError):
        N.EvidenceSpan(source_kind="claim", source_id="c", start=9, end=3, text="t")


def test_missing_link_expr_is_ir_data_validated_never_anything_else():
    good = {"op": "implies", "left": {"op": "var", "name": "wall"}, "right": {"op": "var", "name": "plant"}}
    link = N.MissingLink(premise_ids=["l_so"], antecedent="a", consequent="b", text="if a then b", expr=good)
    assert link.expr == good
    for bad in ({"op": "exec", "code": "print(1)"}, {"op": "var", "name": "Not An Ident"}, "implies(a, b)", ["implies"],
                {"op": "implies", "left": {"op": "var", "name": "a"}}):
        with pytest.raises(ValidationError):
            N.MissingLink(antecedent="a", consequent="b", text="t", expr=bad)
    deep: dict = {"op": "var", "name": "a"}
    for _ in range(200):
        deep = {"op": "not", "arg": deep}
    with pytest.raises(ValidationError):
        N.MissingLink(antecedent="a", consequent="b", text="t", expr=deep)
    wide = {"op": "and", "args": [{"op": "var", "name": "a"}] * 3000}
    with pytest.raises(ValidationError):
        N.MissingLink(antecedent="a", consequent="b", text="t", expr=wide)


def test_dumps_leave_out_empty_optional_fields_and_round_trip():
    bare = diag()
    assert set(bare.model_dump()) == {"code", "defect", "severity", "layer", "derivation", "rule_version", "message"}
    assert set(json.loads(bare.model_dump_json())) == set(bare.model_dump(mode="json"))
    full = diag(claim_ids=["s1.1"], assertion_ids=["l_so", "l_plant_wall"], related_result_ids=["r" * 32],
                missing_link=N.MissingLink(premise_ids=["l_so"], antecedent="the cell has a wall", consequent="it is a plant cell",
                                           text="if the cell has a wall then it is a plant cell",
                                           expr={"op": "implies", "left": {"op": "var", "name": "wall"}, "right": {"op": "var", "name": "plant"}}),
                evidence=[N.EvidenceSpan(source_kind="claim", source_id="s1.1", start=0, end=4, text="The ")],
                derived_problem_digests=["0" * 64])
    capped = N.cap([full], "info", "ambiguous_translation")[0]
    for d in (bare, full, capped):
        text = d.model_dump_json()
        again = N.NamedDiagnostic.model_validate_json(text)
        assert again == d and again.model_dump_json() == text
    assert "start" not in N.EvidenceSpan(source_kind="task", source_id="t", text="x").model_dump()
    assert set(N.MissingLink(antecedent="a", consequent="b", text="t").model_dump()) == {"antecedent", "consequent", "text"}


# --------------------------------------------------------------------------------------------- the helpers


def test_cap_records_capped_from_and_leaves_lower_severities_untouched():
    warning, info = diag(), diag("ARG-LINK-001")
    capped, kept = N.cap([warning, info], "info", "ambiguous_translation")
    assert (capped.severity, capped.capped_from, capped.cap_reason) == ("info", "warning", "ambiguous_translation")
    assert "on the translator's assumed reading" in capped.message and len(capped.message) <= N.MAX_MESSAGE_CHARS
    assert kept is info
    assert N.effective_severity(capped) == "warning" and N.is_blocking(capped) and not N.is_blocking(info)
    twice = N.cap([capped], "info", "not_source_bound")[0]
    assert twice is capped                                    # already at the level: unchanged, its first reason kept
    with pytest.raises(ValueError):
        N.cap([warning], "info", "because")
    with pytest.raises(ValueError):
        N.cap([warning], "fatal", "ambiguous_translation")


def test_apply_cap_rule_covers_exactly_the_codes_of_its_rule():
    codes = ["ARG-AC-001", "ARG-EQ-001", "ARG-EQ-002", "ARG-EQ-003", "EVD-AUTH-001", "EVD-SRC-001", "EVD-FIG-001", "ST-REF-001"]
    made = [N.named_diagnostic(c, layer=N.NAMED_CODES[c].layer, derivation="source_text", message="m") for c in codes]
    amb = {d.code: d.severity for d in N.apply_cap_rule(made, "ambiguous_translation")}
    assert amb == {"ARG-AC-001": "info", "ARG-EQ-001": "warning", "ARG-EQ-002": "warning", "ARG-EQ-003": "warning",
                   "EVD-AUTH-001": "info", "EVD-SRC-001": "info", "EVD-FIG-001": "info", "ST-REF-001": "warning"}
    loose = {d.code: d.severity for d in N.apply_cap_rule(made, "not_source_bound")}
    assert loose["EVD-SRC-001"] == "info" and loose["EVD-FIG-001"] == "info" and loose["EVD-AUTH-001"] == "warning" and loose["ARG-AC-001"] == "warning"
    bound = {d.code: d.severity for d in N.apply_cap_rule(made, "not_source_bound", source_bound=True)}
    assert bound["EVD-SRC-001"] == "warning" and bound["EVD-FIG-001"] == "warning"
    data = {d.code: d.severity for d in N.apply_cap_rule(made, "not_source_bound", data_texts=True)}
    assert data["EVD-SRC-001"] == "info" and data["EVD-FIG-001"] == "warning"
    assert all(d.capped_from == "warning" and d.cap_reason == "not_source_bound" for d in N.apply_cap_rule(made, "not_source_bound") if d.severity == "info")


def test_merge_is_deterministic_and_keeps_the_highest_effective_severity():
    a = diag(claim_ids=["c1"], assertion_ids=["l"])
    a_info = diag(claim_ids=["c1"], assertion_ids=["l"], severity="info", message="the same rule, lower")
    a_capped = N.cap([a], "info", "ambiguous_translation")[0]
    other = diag("ARG-LINK-001", claim_ids=["c1"], assertion_ids=["l"])
    assert N.merge([a_info], [a]) == [a] and N.merge([a], [a_info]) == [a]
    assert N.merge([a_info, a_capped]) == [a_capped]           # the capped one is a warning in effect
    assert N.merge([a, other, a_info]) == [a, other]
    assert N.ordered(N.merge([other], [a])) == N.ordered(N.merge([a], [other]))


def test_ordered_sorts_by_claim_then_precedence_then_assertions():
    d1 = diag("ARG-LINK-001", claim_ids=["c2"], assertion_ids=["a"])
    d2 = diag("ARG-AC-001", claim_ids=["c2"], assertion_ids=["b"])
    d3 = diag("ARG-AC-001", claim_ids=["c2"], assertion_ids=["a"])
    d4 = diag("ARG-LINK-001", claim_ids=["c1"], assertion_ids=["z"])
    assert N.ordered([d1, d2, d3, d4]) == [d4, d3, d2, d1]


def test_suppress_dominated_lets_a_specific_warning_drop_the_generic_one_and_keeps_info():
    ns = diag("ARG-NS-001", claim_ids=["c"], assertion_ids=["C"])
    hg = diag("ARG-HG-001", claim_ids=["c"], assertion_ids=["C", "l"])
    link = diag("ARG-LINK-001", claim_ids=["c"], assertion_ids=["C"])
    elsewhere = diag("ARG-NS-001", claim_ids=["c2"], assertion_ids=["C"])
    assert N.suppress_dominated([ns, hg, link, elsewhere]) == [hg, link, elsewhere]
    hg_info = diag("ARG-HG-001", claim_ids=["c"], assertion_ids=["C", "l"], severity="info")
    assert N.suppress_dominated([ns, hg_info]) == [ns, hg_info]     # an info record dominates nothing
    other_assertions = diag("ARG-HG-001", claim_ids=["c"], assertion_ids=["l"])
    assert N.suppress_dominated([ns, other_assertions]) == [ns, other_assertions]


def test_bounded_counts_the_overflow():
    many = [diag("ARG-LINK-001", claim_ids=["c"], assertion_ids=[f"p{i:02d}"]) for i in range(40)]
    kept, over = N.bounded(many)
    assert len(kept) == N.MAX_PER_CLAIM and over == 40 - N.MAX_PER_CLAIM


def test_from_finding_names_a_labelled_finding_and_nothing_else():
    f = IntegrityFinding(code="INT-REQ-003", severity="error", message="quotation 'x' was not found (an altered quotation)", claim_ids=["c1"],
                         defect="altered_quotation", formal_result_id="r" * 32)
    d = N.from_finding(f)
    assert (d.code, d.defect, d.severity, d.layer, d.claim_ids, d.related_result_ids) == ("INT-REQ-003", "altered_quotation", "error", "channel", ["c1"], ["r" * 32])
    s = StructuralFinding(code="ST-DIM-001", severity="warning", message="dimensions differ", claim_ids=["s1.2"], defect="stem_dimension_error")
    assert N.from_finding(s).layer == "stem" and N.from_finding(s).derivation == "stem_reference"
    assert N.from_finding(StructuralFinding(code="ES-SRC-001", severity="error", message="m")) is None          # no label: nothing named
    arg = IntegrityFinding(code="INT-ARG-001", severity="warning", message="m", defect="leap_in_logic")
    assert N.from_finding(arg) is None                                                                      # the receipt's own finding of a diagnostic


def test_rules_state_reads_absent_as_not_computed_never_as_none_found():
    assert N.rules_state("argdiag-2") == ("complete", None)
    assert N.rules_state(None) == ("not_computed", None)
    assert N.rules_state(N.incomplete_rules("Budget exhausted!")) == ("incomplete", "budget_exhausted")
    assert N.rules_state("argdiag-0") == ("other", "argdiag-0")
    assert N.incomplete_rules("") == "argdiag-2/incomplete:unknown"


def test_the_code_table_is_bound_as_data():
    manifest = N.named_codes_manifest()
    assert json.loads(json.dumps(manifest)) == manifest and manifest["rules"] == "argdiag-2" and manifest["labels"] == list(CANONICAL)
    assert re.fullmatch(r"[0-9a-f]{64}", N.named_codes_digest()) and N.named_codes_digest() == N.named_codes_digest()


def test_defect_of_check_kind_and_its_rows():
    assert N.defect_of_check_kind("stem_conversion") == "stem_unit_error"
    assert N.defect_of_check_kind("stem_algebra") == "stem_invalid_step"
    assert N.defect_of_check_kind("stem_given") == "stem_contradictory_givens"
    for kind in ("stem_comparison", "stem_target", "stem_balance"):
        assert N.defect_of_check_kind(kind) is None
    for kind in ("stem_arithmetic", "stem_substitution", "stem_result", "arithmetic", "percentage", "pair_direction"):
        assert N.defect_of_check_kind(kind) == "stem_arithmetic_slip"
    assert N.defect_of_check_kind("chronology") is None and N.defect_of_check_kind(None) is None


@pytest.mark.parametrize("code, message, label", [
    ("INT-REQ-007", "claim c rests on premises that contradict each other", "contradiction"),
    ("INT-CONFLICT-001", "the claims contradict each other", "contradiction"),
    ("INT-CONFLICT-005", "a self-refutation under an assumed reading", "contradiction"),
    ("INT-REQ-003", "the supplied text holds all of its words but 'x' (an altered quotation)", "altered_quotation"),
    ("INT-REQ-003", "quotation cited by claim c names document 'd', which is not among the supplied texts", "source_mismatch"),
    ("ES-SRC-001", "not in the supplied text: invented, altered, or quoted from memory", "altered_quotation"),
    ("CORE-SRC-001", "cited excerpt not found", "source_mismatch"),
    ("GEN-SRC-001", "cited excerpt not found", "source_mismatch"),
    ("CORE-SRC-005", "credited to one text, found only in another", "source_mismatch"),
    ("ES-SRC-008", "credited to one text, found only in another", "source_mismatch"),
    ("INT-LEDGER-025", "the synthesis quotes words no source holds", "source_mismatch"),
    ("INT-REQ-015", "a colleague's words presented as the source's", "source_mismatch"),
    ("CORE-SRC-003", "quotations no supplied text holds", "unchecked_source"),
    ("CORE-SELF-001", "self-certification", "unchecked_source"),
    ("CORE-SRC-002", "figures with no source", "lack_of_evidence"),
    ("HI-SRC-004", "figures with no source", "lack_of_evidence"),
    ("PS-SRC-001", "a study attributed with no grounding", "uncheckable_authority"),
    ("HI-SRC-003", "a historian attributed with no grounding", "uncheckable_authority"),
    ("ST-DIM-001", "the two sides have different dimensions", "stem_dimension_error"),
    ("ST-DIM-002", "the terms have different dimensions", "stem_dimension_error"),
    ("ST-SCOPE-001", "a symbol rebound to a different value", "stem_symbol_conflict"),
    ("INT-SUBJ-001", "the report's own stem_conversion statement in claim s1 does not hold", "stem_unit_error"),
    ("INT-SUBJ-004", "the report's own stem_algebra statement does not hold under a reading", "stem_invalid_step"),
    ("INT-SUBJ-001", "the report's own stem_given statement does not hold", "stem_contradictory_givens"),
    ("INT-SUBJ-001", "the report's own stem_arithmetic statement in claim s1.2 does not hold", "stem_arithmetic_slip"),
    ("INT-SUBJ-001", "the report's own pair_direction statement does not hold", "stem_arithmetic_slip"),
])
def test_every_defect_of_code_row_labels_its_code(code, message, label):
    assert N.defect_of(code, message) == label


@pytest.mark.parametrize("code, message", [
    ("INT-CONFLICT-004", "a translation fault"),            # stays unlabelled
    ("INT-SUBJ-001", "the report's own stem_comparison statement does not hold"),
    ("INT-SUBJ-001", "the report's own chronology statement does not hold"),
    ("INT-REQ-004", "request item i1 appears unaddressed"),  # coverage names no defect
    ("ES-STR-001", "two strands"),
    ("INT-SUBJ-003", "[english] ES-SRC-001: altered"),
])
def test_an_unmapped_code_names_no_defect(code, message):
    assert N.defect_of(code, message) is None


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.casefold()))


def test_no_template_reads_as_success_and_verified_only_says_what_a_check_did():
    fixed = [N.SECTION_HEADING, *N.diagnosis_section([]), *N.diagnosis_section([], engine_state="not_computed"),
             *N.diagnosis_section([], incomplete=["engine: budget"]), *(s.meaning for s in N.NAMED_CODES.values())]
    capped = N.cap([diag(message="m")], "info", "not_source_bound")
    fixed += N.diagnosis_section(capped, engine_state="not_computed", incomplete=["diag_argument.rule: KeyError"])
    for text in fixed:
        assert not (_words(text) & set(N.SUCCESS_WORDS)), text
        rest = text.casefold().replace("a check verified", "").replace("no check verified", "")
        assert "verified" not in rest, text
