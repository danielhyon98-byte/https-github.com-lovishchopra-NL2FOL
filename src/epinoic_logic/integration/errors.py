"""Closed error codes of the integration protocol ``epinoic.integration.v1`` (``integration/PROTOCOL.md`` section 12).

Standard library only: the bootstrap prints ``KIT-HS-003 z3_unavailable`` from this table before any engine module is
imported, so nothing here may import the engine, pydantic or Z3.

Families:

* ``KIT-HS``: start-up and handshake. A service that meets one of these refuses to start (exit status 2, one line,
  no secret); a Worker that meets one refuses the turn. None of them ever falls back to an unchecked answer.
* ``KIT-REQ``: validation of a checks-port request, specialist envelopes included (the service answers HTTP 400).
* ``KIT-DL``: delivery reasons recorded in a verdict.
* ``KIT-OP``: refusals of out-of-contract overseer-port messages.
* ``KIT-CB``: refusals of out-of-contract combinator-port messages.
* ``KIT-RT``: refusals of out-of-contract flash-router-port messages, and the below-floor refusal.

The tables are append-only within a major protocol version: a code is never renamed or reused.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Mapping

__all__ = [
    "HANDSHAKE_CODES", "REQUEST_CODES", "DELIVERY_CODES", "OVERSEER_PORT_CODES", "COMBINATOR_PORT_CODES",
    "ROUTER_PORT_CODES", "CODES", "WORKER_RAW_CODES", "IntegrationError", "code_name", "code_line",
]

HANDSHAKE_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-HS-001": "protocol_unsupported",
    "KIT-HS-002": "component_versions_mismatch",
    "KIT-HS-003": "z3_unavailable",
    "KIT-HS-004": "selftest_failed",
    "KIT-HS-005": "stem_unavailable",
    "KIT-HS-006": "named_policies_unavailable",
    "KIT-HS-007": "overseer_unavailable",
    "KIT-HS-008": "signing_unconfigured",
    "KIT-HS-009": "translation_provider_unconfigured",
    "KIT-HS-010": "subject_map_mismatch",
    "KIT-HS-011": "specialist_contract_unsupported",
    "KIT-HS-012": "environment_mismatch",
    "KIT-HS-013": "limits_incompatible",
    "KIT-HS-014": "transport_unconfigured",
    "KIT-HS-015": "handshake_unreachable",
    "KIT-HS-016": "timing_infeasible",
})

REQUEST_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-REQ-001": "envelope_invalid",
    "KIT-REQ-002": "mode_unsupported",
    "KIT-REQ-003": "policy_unknown",
    "KIT-REQ-004": "ids_invalid",
    "KIT-REQ-005": "self_certification_rejected",
    "KIT-REQ-006": "too_large",
    "KIT-REQ-007": "budget_out_of_range",
    "KIT-REQ-010": "specialist_schema_unsupported",
    "KIT-REQ-011": "specialist_contract_unsupported",
    "KIT-REQ-012": "specialist_not_an_answer",
    "KIT-REQ-013": "specialist_gate_not_passed",
    "KIT-REQ-014": "answer_digest_mismatch",
    "KIT-REQ-015": "subject_unmapped",
})

DELIVERY_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-DL-001": "receipt_rejected",
    "KIT-DL-002": "receipt_error_findings",
    "KIT-DL-003": "clearance_failed",
    "KIT-DL-004": "clearance_pending",
    "KIT-DL-005": "final_audit_not_passed",
    "KIT-DL-006": "delivery_refused",
    "KIT-DL-007": "consolidation_conflicting",
    "KIT-DL-008": "no_deliverable_output",
    "KIT-DL-010": "blocking_formal_result",
    "KIT-DL-011": "checks_incomplete",
    "KIT-DL-012": "ambiguous_material_claim",
    "KIT-DL-013": "budget_spent",
    "KIT-DL-020": "revision_exhausted",
    "KIT-DL-030": "worker_binding_mismatch",
    "KIT-DL-900": "internal_error",
})

OVERSEER_PORT_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-OP-001": "message_malformed",
    "KIT-OP-002": "port_version_unsupported",
    "KIT-OP-003": "pack_unpinned",
    "KIT-OP-004": "replay_mode_unsupported",
    "KIT-OP-005": "inline_final_release_refused",
    "KIT-OP-006": "clearance_state_unknown",
    "KIT-OP-007": "clearance_inconsistent",
    "KIT-OP-008": "agent_code_in_clearance",
    "KIT-OP-009": "scope_statement_missing",
    "KIT-OP-010": "decision_unbound",
    "KIT-OP-011": "decision_inconsistent",
    "KIT-OP-012": "signature_missing",
})

COMBINATOR_PORT_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-CB-001": "input_malformed",
    "KIT-CB-002": "output_malformed",
    "KIT-CB-003": "transformation_unknown",
    "KIT-CB-004": "source_claim_unknown",
    "KIT-CB-005": "instruction_pack_mismatch",
    "KIT-CB-006": "too_large",
})

ROUTER_PORT_CODES: Mapping[str, str] = MappingProxyType({
    "KIT-RT-001": "plan_malformed",
    "KIT-RT-002": "plan_unbound",
    "KIT-RT-003": "router_identity_mismatch",
    "KIT-RT-004": "transfer_unknown",
    "KIT-RT-005": "transfer_unplanned",
    "KIT-RT-006": "transfer_duplicated",
    "KIT-RT-007": "method_invalid",
    "KIT-RT-008": "instances_over_maximum",
    "KIT-RT-009": "tier_not_cheapest",
    "KIT-RT-010": "profile_unavailable",
    "KIT-RT-011": "hidden_content",
    "KIT-RT-012": "vocabulary_unknown",
    "KIT-RT-013": "cost_invalid",
    "KIT-RT-014": "request_malformed",
    "KIT-RT-015": "hello_invalid",
    "KIT-RT-016": "router_failed",
    "KIT-RT-020": "below_floor",
})

CODES: Mapping[str, str] = MappingProxyType({
    **HANDSHAKE_CODES, **REQUEST_CODES, **DELIVERY_CODES, **OVERSEER_PORT_CODES, **COMBINATOR_PORT_CODES, **ROUTER_PORT_CODES,
})

#: The website Worker's raw codes (stored in D1 for operators; each matches ``^[a-z0-9_]{1,64}$``). The closed table that
#: maps each one to its public code is ``integration/website/src/verify/codes.js``; this tuple mirrors its keys so the
#: Python vectors and the JavaScript table are checked against one list (``tests/integration/test_vectors.py``).
WORKER_RAW_CODES: tuple[str, ...] = (
    # handshake (after admission, before routing)
    "kit_hs_not_ready", "kit_hs_unreachable", "kit_hs_mismatch",
    # subject (after routing, before the specialist call)
    "specialist_unmapped", "specialist_unavailable",
    # specialist outcomes other than "answer" (base M simulation only; runtime v0.1.0 and v0.2.0 outcome sets)
    "specialist_precondition_failed", "specialist_declined", "specialist_failed", "specialist_refusal", "specialist_refused",
    "specialist_incomplete", "specialist_oversize", "specialist_gate_failed", "specialist_gate_unverifiable",
    # the checks call
    "verifier_busy", "verifier_cancelled", "verifier_timeout", "verifier_network", "verifier_redirect", "verifier_auth",
    "verifier_rate_limited", "verifier_capacity", "verifier_rejected", "verifier_error", "verifier_malformed",
    "verifier_binding_mismatch",
    # delivery decisions
    "kit_dl_001", "kit_dl_002", "kit_dl_003", "kit_dl_004", "kit_dl_005", "kit_dl_006", "kit_dl_007", "kit_dl_008",
    "kit_dl_010", "kit_dl_011", "kit_dl_012", "kit_dl_013", "kit_dl_020", "kit_dl_030", "kit_dl_900",
    # the turn.js release gate
    "kit_gate_binding", "kit_gate_decision", "kit_gate_review", "kit_gate_checks", "kit_gate_raw_body", "kit_gate_size",
)


def code_name(code: str) -> str:
    """The name of a closed code (``KIT-HS-003`` -> ``z3_unavailable``). ``KeyError`` for any other string."""
    return CODES[code]


def code_line(code: str) -> str:
    """The one line a refusing process prints: the code and its name, nothing else (never a secret or a value)."""
    return f"{code} {CODES[code]}"


class IntegrationError(Exception):
    """A refusal named by one closed code. ``detail`` is a short, secret-free explanation for operators; it never carries
    a key, a token, student text or an answer. ``str(err)`` is the code line followed by the detail."""

    def __init__(self, code: str, detail: str = "") -> None:
        if code not in CODES:
            raise ValueError(f"unknown integration code {code!r}")
        self.code = code
        self.name = CODES[code]
        self.detail = str(detail)[:500]
        super().__init__(self.line() + (f": {self.detail}" if self.detail else ""))

    def line(self) -> str:
        return code_line(self.code)
