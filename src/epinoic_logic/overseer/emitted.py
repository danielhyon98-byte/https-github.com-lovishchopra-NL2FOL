"""Everything the translator and the channel can emit, as the overseer knows it.

The overseer reads transfers whose receipts, outcomes and signed results carry the translator's own vocabulary. This
module is the overseer's table of that vocabulary, kept identical to the translator's code by drift tests
(``tests/overseer/test_integration_codes.py``), so a code the merged translator emits is never unknown to the audit, the
dossiers, the knowledge pack or the pool:

* :data:`RECEIPT_CODES`: every receipt finding code (``findings`` and ``structural_findings``) with every severity the
  translator raises it at: the channel and integrity codes (``INT-*``), the subject packs' codes (``CORE-*``, ``ES-*``,
  ``HI-*``, ``GEN-*``, ``PS-*``, ``EC-*``, ``BM-*``, ``PACK-INTERNAL-001``, ``BR-INTERNAL-001``) and the STEM branches'
  ``ST-*`` codes (the STEM package's own ``stem.relations.ST_SEVERITY``), each with the defect labels it can carry
  (``named.DEFECT_OF_CODE``) and the codes the translator names but does not raise on this tree (:data:`NAMED_ONLY`);
* :data:`NAMED_DIAGNOSTIC_CODES` and :data:`DEFECT_LABELS`: the argument diagnosis (rules ``argdiag-2``): every named
  code with its defect label, its maximum severity, its layers and its caps (``named.NAMED_CODES``), and the 28 labels;
* :data:`ENGINE_STATUSES`, :data:`TRANSLATION_STATUSES` and :data:`RECEIPT_STATUSES`: every status, classed;
* :data:`ENGINE_DIAGNOSTICS`: every engine diagnostic code (``E100`` to ``E900``, ``W110``, ``W111``), classed;
* :data:`RELEASE_RULES` and :data:`OUTCOME_RELEASE_REASONS`: every reason the engine's release check
  (``engine.release.release_check``, rules 1 to 9) and the outcome's release assessment (``release-v1``) give for a refusal,
  with :func:`release_rule_of` to name the rule of a reason;
* :data:`NAMED_REJECTIONS`: the refusals with a name: the channel's blocking codes (a transfer REJECTED and not
  delivered), the end-to-end fixes' INT-SYNTH-014 beside INT-REQ-009, and the service's named refusals (an engine policy
  that is not exactly one of :data:`NAMED_POLICIES`, E100, among them).

**Risk signals.** :func:`risk_of` classes a code, a status or a diagnostic as a risk signal (:data:`RISK_CLASSES`) and
:func:`risk_signals` reads every signal a journaled task carries, in two strengths: a signal (what blocks release or names a
fault: a diagnostic at effective warning or error, an error finding, a withheld verdict, a rejection, a diagnosis that did
not finish) and a record (an info diagnostic of the three named families: a load-bearing writer's assumption, an unchecked
source, a STEM method record). Both only ever escalate oversight (``pool.plan_pool``): a dossier with a signal goes to two
independent instances, one with records only counts an extra review unit toward the quota; neither ever makes a plan
smaller. Nothing here lowers a severity, lifts a cap or reads a capped diagnostic as anything but what it blocks (its
effective severity).

Nothing here decides a transfer: the audit decides with the checks it already runs (custody, receipts, results,
formal, fidelity, translation, ...), which read these tables. Like every result, a diagnosis or a code proves a property
of the encoding and of this code only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional

__all__ = [
    "EmittedCode", "RECEIPT_CODES", "NAMED_ONLY", "NAMED_DIAGNOSTIC_CODES", "NamedCode", "DEFECT_LABELS", "STEM_DEFECTS", "ENGINE_STATUSES",
    "TRANSLATION_STATUSES", "RECEIPT_STATUSES", "ENGINE_DIAGNOSTICS", "NO_VERDICT_CODES", "ADVISORY_CODES", "RELEASE_RULES", "ReleaseRule",
    "OUTCOME_RELEASE_REASONS", "NAMED_POLICIES", "NAMED_REJECTIONS", "BLOCKING_PREFIXES", "ARGUMENT_RULES", "ARGUMENT_RULE_STATES",
    "RISK_CLASSES", "WRITER_ASSUMPTION_CODES", "UNCHECKED_SOURCE_CODES", "STEM_METHOD_CODES", "release_rule_of", "outcome_reason_of",
    "risk_of", "diagnostic_risk", "risk_signals", "risk_reading", "known_code",
]

_SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class EmittedCode:
    """One receipt finding code: every severity it is raised at, its family and the defect labels it can carry."""
    code: str
    severities: frozenset
    family: str
    defects: tuple = ()

    @property
    def fixed(self) -> Optional[str]:
        """The one severity of a code raised at a single severity, else None."""
        return next(iter(self.severities)) if len(self.severities) == 1 else None


# ============================================================================================ receipt codes
#: (code, severities "a|b") of the channel and integrity layer: ``checks.receipts.FIXED_SEVERITY`` and
#: ``VARIABLE_SEVERITY`` (INT-REQ-004 a warning for a required item, else info; INT-REQ-005 an error for a word bound,
#: a warning for a paragraph bound; INT-REQ-007 and INT-CONFLICT-005 a warning on an assumed reading; INT-ARG-001 the
#: severity of the named diagnostic it carries).
_INT_ROWS: tuple[tuple[str, str], ...] = (
    ("INT-ARG-001", "error|warning"), ("INT-CONFLICT-001", "error"), ("INT-CONFLICT-002", "error"),
    ("INT-CONFLICT-003", "error"), ("INT-CONFLICT-004", "warning"), ("INT-CONFLICT-005", "error|warning"),
    ("INT-CONFLICT-006", "info"), ("INT-ENV-001", "warning"), ("INT-ENV-002", "error"), ("INT-ENV-003", "error"),
    ("INT-ENV-004", "error"), ("INT-ENV-005", "warning"), ("INT-ENV-006", "error"), ("INT-ENV-007", "error"),
    ("INT-ENV-008", "error"), ("INT-ENV-009", "error"), ("INT-ENV-010", "error"), ("INT-ENV-011", "error"),
    ("INT-GLOSSARY-001", "error"), ("INT-GLOSSARY-002", "info"), ("INT-GLOSSARY-003", "error"),
    ("INT-GLOSSARY-004", "error"), ("INT-GLOSSARY-005", "warning"), ("INT-GLOSSARY-006", "error"),
    ("INT-GLOSSARY-007", "error"), ("INT-HANDOFF-001", "error"), ("INT-HANDOFF-002", "error"),
    ("INT-HANDOFF-003", "error"), ("INT-HANDOFF-004", "error"), ("INT-HANDOFF-005", "warning"),
    ("INT-HANDOFF-006", "info"), ("INT-HANDOFF-007", "error"), ("INT-HANDOFF-008", "error"),
    ("INT-HANDOFF-009", "warning"), ("INT-HANDOFF-010", "warning"), ("INT-HANDOFF-011", "error"),
    ("INT-HANDOFF-012", "error"), ("INT-HANDOFF-013", "error"), ("INT-HANDOFF-014", "warning"),
    ("INT-HANDOFF-015", "error"), ("INT-HANDOFF-016", "warning"), ("INT-HANDOFF-017", "warning"),
    ("INT-INTERNAL-001", "error"), ("INT-LEDGER-000", "error"), ("INT-LEDGER-001", "error"), ("INT-LEDGER-002", "error"),
    ("INT-LEDGER-003", "error"), ("INT-LEDGER-004", "error"), ("INT-LEDGER-005", "error"), ("INT-LEDGER-006", "error"),
    ("INT-LEDGER-008", "error"), ("INT-LEDGER-009", "error"), ("INT-LEDGER-010", "warning"), ("INT-LEDGER-011", "info"),
    ("INT-LEDGER-012", "error"), ("INT-LEDGER-013", "error"), ("INT-LEDGER-014", "error"), ("INT-LEDGER-015", "error"),
    ("INT-LEDGER-016", "warning"), ("INT-LEDGER-017", "warning"), ("INT-LEDGER-018", "warning"),
    ("INT-LEDGER-019", "warning"), ("INT-LEDGER-020", "warning"), ("INT-LEDGER-021", "warning"),
    ("INT-LEDGER-022", "info"), ("INT-LEDGER-023", "error"), ("INT-LEDGER-024", "warning"), ("INT-LEDGER-025", "error"),
    ("INT-LEDGER-026", "warning"), ("INT-LEDGER-027", "warning"), ("INT-LEDGER-028", "warning"),
    ("INT-LEDGER-029", "warning"), ("INT-LEDGER-030", "error"), ("INT-LEDGER-031", "error"), ("INT-LEDGER-032", "error"),
    ("INT-REQ-000", "error"), ("INT-REQ-001", "error"), ("INT-REQ-002", "error"), ("INT-REQ-003", "error"),
    ("INT-REQ-004", "warning|info"), ("INT-REQ-005", "error|warning"), ("INT-REQ-006", "warning"),
    ("INT-REQ-007", "error|warning"), ("INT-REQ-008", "warning"), ("INT-REQ-009", "error"), ("INT-REQ-010", "warning"),
    ("INT-REQ-011", "error"), ("INT-REQ-012", "error"), ("INT-REQ-013", "warning"), ("INT-REQ-014", "warning"),
    ("INT-REQ-015", "error"), ("INT-REQ-016", "warning"), ("INT-STALE-001", "error"), ("INT-STALE-002", "error"),
    ("INT-STALE-003", "error"), ("INT-STALE-004", "error"), ("INT-STALE-005", "error"), ("INT-STALE-006", "error"),
    ("INT-STALE-007", "error"), ("INT-STALE-008", "error"), ("INT-STALE-009", "error"), ("INT-STALE-010", "error"),
    ("INT-STALE-011", "error"), ("INT-SUBJ-001", "error"), ("INT-SUBJ-002", "warning"), ("INT-SUBJ-003", "error"),
    ("INT-SUBJ-004", "warning"), ("INT-SYNTH-001", "error"), ("INT-SYNTH-002", "info"), ("INT-SYNTH-003", "warning"),
    ("INT-SYNTH-004", "warning"), ("INT-SYNTH-005", "warning"), ("INT-SYNTH-006", "error"), ("INT-SYNTH-007", "warning"),
    ("INT-SYNTH-008", "warning"), ("INT-SYNTH-009", "warning"), ("INT-SYNTH-010", "error"), ("INT-SYNTH-011", "info"),
    ("INT-SYNTH-012", "warning"), ("INT-SYNTH-013", "warning"), ("INT-SYNTH-014", "error"), ("INT-XENC-001", "warning"),
)
#: (code, severities) of the subject packs and the branch hub (``branches/``, ``adapters/``): the core pack, the English,
#: History, generic, Psychology, Economics and Business packs, and the hub's internal-failure codes.
_BRANCH_ROWS: tuple[tuple[str, str], ...] = (
    ("BM-STR-001", "info"), ("BR-INTERNAL-001", "warning"), ("CORE-CHR-001", "warning"), ("CORE-INTERNAL-001", "error"),
    ("CORE-QNT-001", "warning"), ("CORE-SELF-001", "warning"), ("CORE-SRC-001", "error"), ("CORE-SRC-002", "info"),
    ("CORE-SRC-003", "warning|info"), ("CORE-SRC-004", "warning"), ("CORE-SRC-005", "error|warning"), ("CORE-SRC-006", "error"),
    ("CORE-STR-001", "error"), ("EC-STR-001", "info"), ("EC-STR-002", "info"), ("ES-INTERNAL-001", "warning"),
    ("ES-META-001", "warning"), ("ES-SRC-001", "error"), ("ES-SRC-002", "error|warning"), ("ES-SRC-003", "warning"),
    ("ES-SRC-004", "warning"), ("ES-SRC-005", "warning"), ("ES-SRC-006", "warning"), ("ES-SRC-007", "info"),
    ("ES-SRC-008", "error|warning"), ("ES-STR-001", "warning"), ("ES-STR-002", "info"), ("ES-STY-001", "info"),
    ("ES-STY-002", "info"), ("ES-STY-003", "warning"), ("GEN-DUP-001", "info"), ("GEN-SRC-001", "error"),
    ("GEN-SRC-002", "warning"), ("GEN-SRC-003", "warning"), ("GEN-SRC-004", "info"), ("GEN-SRC-005", "warning"),
    ("GEN-STR-001", "error"), ("GEN-STR-002", "error"), ("HI-CHR-001", "warning"), ("HI-SRC-001", "error|warning"),
    ("HI-SRC-002", "warning"), ("HI-SRC-003", "warning"), ("HI-SRC-004", "info"), ("HI-STR-001", "warning"),
    ("HI-STR-002", "info"), ("HI-STR-003", "info"), ("HI-STR-004", "info"), ("PACK-INTERNAL-001", "error"),
    ("PS-SRC-001", "warning"), ("PS-STR-001", "info"),
)
#: (code, severity) of the STEM branches (``stem.relations.ST_SEVERITY``, the STEM package's own table): the front end's
#: findings, and ST-UNIT-003, ST-STEP-001 and ST-ROUND-001, the codes of engine-decided checks (a unit companion, a stated
#: operation, a rounding), whose failure reaches the receipt as INT-SUBJ-001 or INT-SUBJ-004 carrying their defect.
_ST_ROWS: tuple[tuple[str, str], ...] = (
    ("ST-ALG-001", "warning"), ("ST-CHEM-001", "warning"), ("ST-CODE-001", "info"), ("ST-DIM-001", "warning"),
    ("ST-DIM-002", "warning"), ("ST-GIVEN-002", "warning"), ("ST-GIVEN-003", "warning"), ("ST-GIVEN-004", "warning"),
    ("ST-INTERNAL-001", "warning"), ("ST-LIM-001", "warning"), ("ST-LIM-002", "warning"), ("ST-PARSE-001", "warning"),
    ("ST-PARSE-002", "warning"), ("ST-RANGE-001", "warning"), ("ST-REF-001", "warning"), ("ST-REF-002", "warning"),
    ("ST-ROUND-001", "warning"), ("ST-SCOPE-001", "info"), ("ST-SCOPE-002", "warning"), ("ST-STEP-001", "warning"),
    ("ST-STEP-002", "info"), ("ST-STEP-003", "warning"), ("ST-UNDEC-001", "warning"), ("ST-UNDEC-002", "warning"),
    ("ST-UNDEC-003", "warning"), ("ST-UNDEF-001", "warning"), ("ST-UNIT-001", "warning"), ("ST-UNIT-002", "info"),
    ("ST-UNIT-003", "warning"), ("ST-WORK-001", "warning"),
)
#: Codes the translator names that no code of this tree raises, with why: they are known (an agent or a check that meets
#: one is not met by an unknown code) and never expected on a receipt of this build.
NAMED_ONLY: Mapping[str, str] = MappingProxyType({
    "CORE-SRC-007": "labelled by named.DEFECT_OF_CODE (a figure a supplied table states for another year or no year); the table reader that "
                    "raised it on the argument-diagnostics line was not ported onto this tree",
    "INT-HIST-001": "read by the response gate (channel/gate.py) as a finding carried from an earlier receipt; the relay history that raised it "
                    "was not ported onto this tree",
    "INT-REQ-017": "a receipt-only named code (named.NAMED_CODES, warning: a system check result handed to the reader as subject content); "
                   "the relay check that raised it (end-to-end B3) was not ported onto this tree",
})

#: The canonical defect labels of the argument diagnosis, in the contract's order (``named.DEFECT_LABELS``).
DEFECT_LABELS: tuple[str, ...] = (
    "leap_in_logic", "affirming_the_consequent", "denying_the_antecedent", "hasty_generalisation", "false_dilemma",
    "circular_reasoning", "equivocation", "causal_leap", "bare_assertion", "contradiction", "vacuous_argument",
    "lack_of_evidence", "unchecked_source", "source_mismatch", "altered_quotation", "invented_figure",
    "cherry_picked_data", "uncheckable_authority", "stem_wrong_formula", "stem_unit_error", "stem_dimension_error",
    "stem_arithmetic_slip", "stem_invalid_step", "stem_rounding_changes_conclusion", "stem_extrapolation",
    "stem_missing_working", "stem_contradictory_givens", "stem_symbol_conflict",
)
#: The STEM method labels (a STEM method error).
STEM_DEFECTS: frozenset = frozenset(label for label in DEFECT_LABELS if label.startswith("stem_"))

#: Existing receipt codes and the defect labels ``named.DEFECT_OF_CODE`` (and ``DEFECT_OF_CHECK_KIND`` for INT-SUBJ-001
#: and INT-SUBJ-004, besides the label a STEM check carries itself) can give them.
_LABELS: Mapping[str, tuple[str, ...]] = {
    "INT-REQ-007": ("contradiction",), "INT-CONFLICT-001": ("contradiction",), "INT-CONFLICT-005": ("contradiction",),
    "INT-REQ-003": ("altered_quotation", "source_mismatch"), "ES-SRC-001": ("altered_quotation", "source_mismatch"),
    "CORE-SRC-001": ("altered_quotation", "source_mismatch"), "GEN-SRC-001": ("altered_quotation", "source_mismatch"),
    "CORE-SRC-005": ("source_mismatch",), "ES-SRC-008": ("source_mismatch",), "INT-LEDGER-025": ("source_mismatch",),
    "INT-REQ-015": ("source_mismatch",), "CORE-SRC-007": ("invented_figure", "source_mismatch"), "CORE-SRC-003": ("unchecked_source",),
    "CORE-SELF-001": ("unchecked_source",), "CORE-SRC-002": ("lack_of_evidence",), "HI-SRC-004": ("lack_of_evidence",),
    "PS-SRC-001": ("uncheckable_authority",), "HI-SRC-003": ("uncheckable_authority",), "ST-DIM-001": ("stem_dimension_error",),
    "ST-DIM-002": ("stem_dimension_error",), "ST-SCOPE-001": ("stem_symbol_conflict",),
    "INT-SUBJ-001": tuple(sorted(STEM_DEFECTS)), "INT-SUBJ-004": tuple(sorted(STEM_DEFECTS)),
}


def _family(code: str) -> str:
    return code.rsplit("-", 1)[0]


def _receipt_table() -> dict[str, EmittedCode]:
    out: dict[str, EmittedCode] = {}
    for code, sevs in (*_INT_ROWS, *_BRANCH_ROWS, *_ST_ROWS):
        parts = frozenset(sevs.split("|"))
        assert parts <= set(_SEVERITIES) and code not in out, code
        out[code] = EmittedCode(code=code, severities=parts, family=_family(code), defects=_LABELS.get(code, ()))
    return out


#: Every receipt finding code the translator and the channel raise, with every severity they raise it at.
RECEIPT_CODES: Mapping[str, EmittedCode] = MappingProxyType(_receipt_table())


# ============================================================================================ named diagnostics
@dataclass(frozen=True)
class NamedCode:
    """One named-diagnostic code (``named.NAMED_CODES``): its label, its maximum severity, the layers it is made in, and its
    caps (``ambiguous``: capped at info on an AMBIGUOUS_TRANSLATION; ``scope``: when a warning is shown as one)."""
    code: str
    defect: str
    max_severity: str
    layers: tuple
    ambiguous_cap: bool
    scope: str


def _named(code: str, defect: str, sev: str, layers: str, ambiguous: bool = True, scope: str = "always") -> NamedCode:
    return NamedCode(code=code, defect=defect, max_severity=sev, layers=tuple(layers.split("|")), ambiguous_cap=ambiguous, scope=scope)


#: Every named-diagnostic code (rules ``argdiag-2``): the engine layer (signed with the result), the claim and report
#: layers, and the STEM layer. The receipt-only channel codes INT-ARG-001, INT-REQ-017 and INT-XENC-001 are receipt codes.
NAMED_DIAGNOSTIC_CODES: Mapping[str, NamedCode] = MappingProxyType({n.code: n for n in (
    _named("ARG-AC-001", "affirming_the_consequent", "warning", "engine"),
    _named("ARG-BARE-001", "bare_assertion", "warning", "report"),
    _named("ARG-CIRC-001", "circular_reasoning", "warning", "engine|claim"),
    _named("ARG-CIRC-002", "circular_reasoning", "warning", "engine"),
    _named("ARG-CIRC-003", "circular_reasoning", "warning", "engine|report"),
    _named("ARG-CL-001", "causal_leap", "warning", "engine"),
    _named("ARG-CONTRA-001", "contradiction", "error", "engine"),
    _named("ARG-DA-001", "denying_the_antecedent", "warning", "engine"),
    _named("ARG-EQ-001", "equivocation", "warning", "claim", ambiguous=False),
    _named("ARG-EQ-002", "equivocation", "warning", "engine", ambiguous=False),
    _named("ARG-EQ-003", "equivocation", "warning", "engine", ambiguous=False),
    _named("ARG-FACT-001", "lack_of_evidence", "info", "engine"),
    _named("ARG-FD-001", "false_dilemma", "warning", "engine"),
    _named("ARG-HG-001", "hasty_generalisation", "warning", "engine"),
    _named("ARG-INV-001", "leap_in_logic", "warning", "engine"),
    _named("ARG-LINK-001", "leap_in_logic", "info", "engine"),
    _named("ARG-LINK-002", "unchecked_source", "info", "engine"),
    _named("ARG-NS-001", "leap_in_logic", "warning", "engine"),
    _named("ARG-NS-002", "leap_in_logic", "warning", "engine"),
    _named("ARG-NS-003", "leap_in_logic", "warning", "claim"),
    _named("ARG-PART-001", "leap_in_logic", "info", "engine"),
    _named("ARG-REFUTE-001", "contradiction", "warning", "engine"),
    _named("ARG-VAC-001", "vacuous_argument", "warning", "engine"),
    _named("EVD-AUTH-001", "uncheckable_authority", "warning", "claim"),
    _named("EVD-CHERRY-001", "cherry_picked_data", "warning", "claim"),
    _named("EVD-FIG-001", "invented_figure", "warning", "claim", scope="source_bound_or_data"),
    _named("EVD-LACK-001", "lack_of_evidence", "warning", "claim", scope="source_bound"),
    _named("EVD-LACK-002", "lack_of_evidence", "info", "report"),
    _named("EVD-SRC-001", "unchecked_source", "warning", "claim", scope="source_bound"),
    _named("EVD-SRC-002", "unchecked_source", "info", "report"),
    _named("EVD-SRC-003", "source_mismatch", "warning", "claim"),
    _named("EVD-SRC-004", "unchecked_source", "info", "claim"),
    _named("EVD-SRC-005", "unchecked_source", "warning", "claim"),
    _named("EVD-SRC-006", "source_mismatch", "warning", "report"),
    _named("ST-GIVEN-002", "stem_contradictory_givens", "warning", "stem", ambiguous=False),
    _named("ST-GIVEN-003", "stem_contradictory_givens", "warning", "stem", ambiguous=False),
    _named("ST-GIVEN-004", "stem_contradictory_givens", "warning", "stem", ambiguous=False),
    _named("ST-RANGE-001", "stem_extrapolation", "warning", "stem", ambiguous=False),
    _named("ST-REF-001", "stem_wrong_formula", "warning", "stem", ambiguous=False),
    _named("ST-REF-002", "stem_wrong_formula", "warning", "stem", ambiguous=False),
    _named("ST-ROUND-001", "stem_rounding_changes_conclusion", "warning", "stem", ambiguous=False),
    _named("ST-SCOPE-002", "stem_symbol_conflict", "warning", "stem", ambiguous=False),
    _named("ST-STEP-001", "stem_invalid_step", "warning", "stem", ambiguous=False),
    _named("ST-STEP-002", "stem_invalid_step", "info", "stem", ambiguous=False),
    _named("ST-STEP-003", "stem_invalid_step", "warning", "stem", ambiguous=False),
    _named("ST-UNIT-003", "stem_unit_error", "warning", "stem", ambiguous=False),
    _named("ST-WORK-001", "stem_missing_working", "warning", "stem", ambiguous=False),
)})
#: The argument rules of this build, and the states a result's ``argument_rules`` can be in (``named.rules_state``).
ARGUMENT_RULES = "argdiag-2"
ARGUMENT_RULE_STATES: tuple[str, ...] = ("complete", "incomplete", "other", "not_computed")

#: A load-bearing writer's assumption: the proof needs a link or a fact of the writer's own that no check established.
WRITER_ASSUMPTION_CODES: frozenset = frozenset({"ARG-LINK-001", "ARG-LINK-002", "ARG-FACT-001"})
#: An unchecked source: a premise or a claim leans on an authority no check in this process verified.
UNCHECKED_SOURCE_CODES: frozenset = frozenset(
    {c for c, n in NAMED_DIAGNOSTIC_CODES.items() if n.defect in ("unchecked_source", "uncheckable_authority")}
    | {c for c, e in RECEIPT_CODES.items() if set(e.defects) & {"unchecked_source", "uncheckable_authority"}})
#: A STEM method error: every code whose label is a STEM method label (a wrong formula, a unit or dimension error, an
#: invalid step, a rounding that changes a conclusion, an extrapolation, missing working, contradictory givens, a symbol
#: conflict), and the failed STEM checks (INT-SUBJ-001, INT-SUBJ-004) when they carry such a label.
STEM_METHOD_CODES: frozenset = frozenset(
    {c for c, n in NAMED_DIAGNOSTIC_CODES.items() if n.defect in STEM_DEFECTS} | {"ST-DIM-001", "ST-DIM-002", "ST-SCOPE-001"})


# ============================================================================================ statuses and engine codes
#: Every engine status (``engine.statuses.VerificationStatus``) and its class.
ENGINE_STATUSES: Mapping[str, str] = MappingProxyType({
    "ENTAILED": "definitive", "COUNTEREXAMPLE": "definitive", "INCONSISTENT_PREMISES": "definitive", "CONSISTENT": "definitive",
    "SATISFIABLE": "definitive", "UNSATISFIABLE": "definitive", "UNKNOWN": "solver_non_result", "TIMEOUT": "solver_non_result",
    "UNSUPPORTED": "policy_non_result", "INVALID_FORMALIZATION": "policy_non_result", "AMBIGUOUS_TRANSLATION": "translation_non_result",
    "NOT_ELIGIBLE": "translation_non_result", "INTERNAL_ERROR": "failure",
})
#: Every translation status (``translate.contracts.TranslationStatus``); only TRANSLATED carries an accepted encoding.
TRANSLATION_STATUSES: tuple[str, ...] = ("TRANSLATED", "AMBIGUOUS_TRANSLATION", "NOT_ELIGIBLE", "UNSUPPORTED", "INVALID_FORMALIZATION",
                                         "TRANSLATION_FAILED")
#: Every receipt status (``channel.contracts.TransmissionStatus``); a REJECTED transfer is not delivered.
RECEIPT_STATUSES: tuple[str, ...] = ("ACCEPTED", "ACCEPTED_WITH_FINDINGS", "REJECTED")
#: Every engine diagnostic code (``engine.errors.DiagnosticCode``) and its class: ``invalid`` (INVALID_FORMALIZATION),
#: ``no_verdict`` (on a definitive status: no verdict on the claim, release rule 5), ``advisory`` (the status stands),
#: ``unsupported`` and ``limits`` (UNSUPPORTED or INVALID_FORMALIZATION before any solver call), ``solver`` (TIMEOUT or
#: UNKNOWN), ``service`` (a refusal of the HTTP boundary or of a binding) and ``internal`` (INTERNAL_ERROR).
ENGINE_DIAGNOSTICS: Mapping[str, str] = MappingProxyType({
    "E100": "invalid", "E101": "invalid", "E102": "invalid", "E103": "invalid", "E104": "invalid", "E105": "invalid", "E106": "invalid",
    "E107": "invalid", "E108": "no_verdict", "E109": "invalid", "E110": "no_verdict", "E111": "no_verdict", "E112": "no_verdict",
    "W110": "advisory", "W111": "advisory", "E200": "unsupported", "E201": "unsupported", "E202": "unsupported", "E203": "unsupported",
    "E204": "unsupported", "E205": "unsupported", "E206": "unsupported", "E300": "limits", "E301": "limits", "E302": "limits", "E303": "limits",
    "E304": "limits", "E305": "limits", "E306": "limits", "E400": "solver", "E401": "solver", "E402": "solver", "E403": "solver",
    "E500": "service", "E501": "service", "E502": "service", "E503": "service", "E504": "service", "E505": "service", "E900": "internal",
})
NO_VERDICT_CODES: frozenset = frozenset(c for c, k in ENGINE_DIAGNOSTICS.items() if k == "no_verdict")
ADVISORY_CODES: frozenset = frozenset(c for c, k in ENGINE_DIAGNOSTICS.items() if k == "advisory")


# ============================================================================================ release refusals
@dataclass(frozen=True)
class ReleaseRule:
    """One rule of the engine's release check (``engine.release``) and the leads of the reasons it gives."""
    number: int
    name: str
    leads: tuple


#: The nine rules of ``engine.release.release_check``; rules 8 and 9 are the argument diagnosis (a named defect at
#: effective warning or error, a capped one included; a result not diagnosed by ``argdiag-2``).
RELEASE_RULES: tuple[ReleaseRule, ...] = (
    ReleaseRule(1, "authentic", ("unauthenticated:",)),
    ReleaseRule(2, "bound", ("binding inconsistent:", "not bound to this problem:", "not bound to this claim:")),
    ReleaseRule(3, "current", ("stale:",)),
    ReleaseRule(4, "positive verdict", ("no positive verdict:",)),
    ReleaseRule(5, "verdict on the claim", ("no verdict on the claim:",)),
    ReleaseRule(6, "with its evidence", ("no dependency evidence:",)),
    ReleaseRule(7, "established premises only", ("unresolved dependencies (ungrounded):", "unresolved dependencies (authority not validated by any check):")),
    ReleaseRule(8, "no named defect", ("named defect:", "capped diagnostic, shown at info and still blocking release (it names no defect):")),
    ReleaseRule(9, "diagnosed by these rules", ("argument diagnosis not computed:", "argument diagnosis incomplete (", "argument diagnosis by other rules (")),
)
#: The leads of every unresolved item of the outcome's release assessment (``translate.outcome.assess_release``,
#: ``release-v1``), with the class of each; ``named_defect`` and ``diagnosis`` are the argument diagnosis.
OUTCOME_RELEASE_REASONS: Mapping[str, str] = MappingProxyType({
    "translation ": "translation", "formal check: display status": "formal", "ungrounded dependencies": "evidence",
    "unverified dependencies": "evidence", "the engine's release check was not run": "engine", "engine release check:": "engine",
    "failed grounding checks:": "evidence", "task authority unvalidated": "evidence", "references not all located:": "evidence",
    "a retry changed the claim:": "translation", "a retry added premises no source asserts:": "translation", "structural errors:": "structural",
    "named defect on this claim:": "named_defect", "capped diagnostic, shown at info and still blocking release (it names no defect):": "named_defect",
    "argument diagnosis incomplete": "diagnosis", "no semantic-fidelity review": "review", "the fidelity review": "review",
    "the fidelity reviewer saw supplied text(s) only in part:": "review",
})


def release_rule_of(reason: str) -> Optional[int]:
    """The number of the release rule a reason of ``engine.release.release_check`` states, or None for a reason no rule
    gives (never read as a pass)."""
    if not isinstance(reason, str):
        return None
    for rule in RELEASE_RULES:
        if reason.startswith(rule.leads):
            return rule.number
    return None


def outcome_reason_of(reason: str) -> Optional[str]:
    """The class of an unresolved item of an outcome's release assessment, or None."""
    if not isinstance(reason, str):
        return None
    for lead in sorted(OUTCOME_RELEASE_REASONS, key=len, reverse=True):
        if reason.startswith(lead):
            return OUTCOME_RELEASE_REASONS[lead]
    return None


# ============================================================================================ named rejections and policies
#: The named engine policies a caller may ask for (``engine.policies.NAMED_POLICIES``); any other name is refused.
NAMED_POLICIES: tuple[str, ...] = ("joint", "linear", "nonlinear")
#: The channel's blocking prefixes (``channel.bus._BLOCKING_PREFIXES``): an error finding of one of them REJECTS the
#: transfer, which is then not delivered.
BLOCKING_PREFIXES: tuple[str, ...] = ("INT-HANDOFF", "INT-ENV", "INT-REQ-000", "INT-REQ-001", "INT-REQ-002", "INT-REQ-009", "INT-LEDGER-000",
                                      "INT-LEDGER-008")
#: The refusals with a name, and what each refuses.
NAMED_REJECTIONS: Mapping[str, str] = MappingProxyType({
    "INT-REQ-009": "a payload that does not validate against its contract: the transfer is REJECTED and not delivered",
    "INT-SYNTH-014": "a synthesis carrying a value outside the synthesis contract's closed vocabularies (end-to-end fix, bug 7): named beside "
                     "INT-REQ-009, the synthesis REJECTED, never delivered with the ledger rules those values select skipped",
    "E100": "over HTTP and on the command line, an engine policy that is not exactly one of the named policies (end-to-end fix, bug 8): refused "
            "before anything runs (HTTP 400, CLI exit 2), as is a payload outside the request schema",
    "E306": "a request body over the service's size limit",
    "E502": "a request with no valid service token",
    "E503": "a request over the service's rate limit",
    "E504": "a request over the service's concurrency limit",
    "E505": "a payload that certifies itself (verified: true): the field is discarded and the service refuses a self-certifying release check",
})


# ============================================================================================ risk
#: The risk classes a signal can have; any one escalates oversight (``pool.plan_pool``), none lowers it.
RISK_CLASSES: tuple[str, ...] = ("named_defect", "writer_assumption", "unchecked_source", "stem_method", "encoding_conflict", "contradiction",
                                 "withheld_verdict", "rejection", "diagnosis_incomplete", "integrity_error")
_RANK = {"info": 0, "warning": 1, "error": 2}


def known_code(code: str) -> bool:
    """Whether ``code`` is in the overseer's tables (a receipt code, a named-diagnostic code, a code named only, an engine
    diagnostic or a status)."""
    return (code in RECEIPT_CODES or code in NAMED_DIAGNOSTIC_CODES or code in NAMED_ONLY or code in ENGINE_DIAGNOSTICS
            or code in ENGINE_STATUSES or code in TRANSLATION_STATUSES)


def diagnostic_risk(code: str, defect: Optional[str], effective_severity: str) -> Optional[str]:
    """The risk class of one named diagnostic, read at its EFFECTIVE severity (the higher of its severity and the one a cap
    lowered it from), so a capped diagnostic is never read as less than what it blocks."""
    if code in WRITER_ASSUMPTION_CODES:
        return "writer_assumption"
    if code in UNCHECKED_SOURCE_CODES or defect in ("unchecked_source", "uncheckable_authority"):
        return "unchecked_source"
    if code in STEM_METHOD_CODES or defect in STEM_DEFECTS:
        return "stem_method"
    if _RANK.get(effective_severity, 0) >= _RANK["warning"]:
        return "named_defect"
    return None


def risk_of(code: str, severity: str = "warning", defect: Optional[str] = None) -> Optional[str]:
    """The risk class of a receipt finding (``code`` at ``severity``, carrying ``defect``), or None when it is no risk
    signal. Error-level integrity findings, rejections, contradictions, encoding conflicts, the argument-diagnosis finding
    and every code of the three named families (a writer's assumption, an unchecked source, a STEM method error) are."""
    if code == "INT-ARG-001":
        return diagnostic_risk(code, defect, severity) or "named_defect"
    if code == "INT-XENC-001":
        return "encoding_conflict"
    if code in ("INT-REQ-007", "INT-CONFLICT-001", "INT-CONFLICT-005"):
        return "contradiction"
    if code in NAMED_REJECTIONS or (code.startswith(BLOCKING_PREFIXES) and severity == "error"):
        return "rejection"
    if code in UNCHECKED_SOURCE_CODES or defect in ("unchecked_source", "uncheckable_authority"):
        return "unchecked_source"
    if code in STEM_METHOD_CODES or (defect in STEM_DEFECTS and code in ("INT-SUBJ-001", "INT-SUBJ-004")):
        return "stem_method"
    if severity == "error":
        return "integrity_error"
    return None


def _items(x: Any) -> list:
    return list(x or ())


def _strength(cls: str, severity: str) -> str:
    """``signal`` for what blocks release or names a fault, ``record`` for an info record of a named family."""
    return "signal" if _RANK.get(severity, 0) >= _RANK["warning"] or cls not in ("writer_assumption", "unchecked_source", "stem_method") else "record"


def _receipt_signals(rc: Any) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    if getattr(getattr(rc, "status", None), "value", getattr(rc, "status", None)) == "REJECTED":
        out.add(("rejection", "signal"))
    for f in _items(getattr(rc, "findings", None)) + _items(getattr(rc, "structural_findings", None)):
        sev = str(getattr(f, "severity", "warning"))
        r = risk_of(str(getattr(f, "code", "")), sev, getattr(f, "defect", None))
        if r:
            out.add((r, _strength(r, sev)))
    named = _items(getattr(rc, "named_diagnostics", None))
    for o in _items(getattr(rc, "outcomes", None)):
        named += _items(getattr(o, "named_diagnostics", None))
        if _items(getattr(o, "diagnosis_incomplete", None)):
            out.add(("diagnosis_incomplete", "signal"))
        v = getattr(o, "verification", None)
        if v is not None:
            if {getattr(d, "code", None) for d in _items(getattr(v, "diagnostics", None))} & NO_VERDICT_CODES:
                out.add(("withheld_verdict", "signal"))
            rules = getattr(v, "argument_rules", None)
            if rules is not None and rules != ARGUMENT_RULES:
                out.add(("diagnosis_incomplete", "signal"))
    if getattr(rc, "diagnosis_incomplete", None) or getattr(rc, "named_overflow", 0):
        out.add(("diagnosis_incomplete", "signal"))
    for d in named:
        sev = str(getattr(d, "severity", "info"))
        capped = getattr(d, "capped_from", None)
        eff = capped if capped is not None and _RANK.get(capped, 0) > _RANK.get(sev, 0) else sev
        r = diagnostic_risk(str(getattr(d, "code", "")), getattr(d, "defect", None), eff)
        if r:
            out.add((r, _strength(r, eff)))
    return out


def risk_reading(view: Any) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(signals, records)``: every risk class the journaled transfers of ``view`` (an ``OverseerView``) carry as a signal
    (what blocks release or names a fault, read at the EFFECTIVE severity) and every class they carry only as an info record
    of a named family, each sorted. Read from the receipts, outcomes and signed results as journaled (findings and their
    labels, named diagnostics, withheld verdicts, an argument diagnosis that is incomplete or not this build's, a rejection);
    a transfer with no receipt carries none. Deterministic; never raises: a receipt that cannot be read is a signal."""
    found: set[tuple[str, str]] = set()
    for t in _items(getattr(view, "transfers", None)):
        try:
            rc = getattr(t, "receipt", None)
            if rc is not None:
                found |= _receipt_signals(rc)
        except Exception:  # noqa: BLE001 - a receipt that cannot be read is a signal in itself, never a pass
            found.add(("integrity_error", "signal"))
    signals = {c for c, s in found if s == "signal"}
    records = {c for c, s in found if s == "record"} - signals
    return tuple(sorted(signals)), tuple(sorted(records))


def risk_signals(view: Any) -> tuple[str, ...]:
    """The risk classes ``view`` carries as signals (:func:`risk_reading`)."""
    return risk_reading(view)[0]


_CODE_RE = re.compile(r"^[A-Z]{2,7}-[A-Z]{2,10}-\d{3}$")


def codes_in(items: Iterable[Any]) -> list[str]:
    """The codes of ``items`` (findings or named diagnostics) in first-seen order (a helper for the tests and the docs)."""
    return list(dict.fromkeys(str(getattr(x, "code", "")) for x in items if _CODE_RE.match(str(getattr(x, "code", "")))))
