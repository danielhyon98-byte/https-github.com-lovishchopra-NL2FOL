"""The Overseer's transfer audit: deterministic checks of every transfer between agents.

Every request, report, relay, router forward and synthesis crosses the translator channel; the audit checks those
transfers. For each it asks whether the transfer the router is about to act on is the one that was issued, whether
every receipt is the exact image of what was checked, whether every result a receipt cites is a signed engine run of
the problem it names inside this task, whether the delivered claims are what the specialist actually said, whether
forwards and peer documents are the delivered text, and whether a synthesis accounts for the reports as delivered
and names every contradiction. When something is wrong it reports an ``OVS-*`` finding with identifiers.

Trust rule (holds against any instruction in code, data or prompts): every ``OVS-*`` finding about a transfer is
decided by a digest comparison, an HMAC verification, a re-run of this repository's deterministic rules on journaled
inputs, or an engine run the auditor signs itself. Agent text is data. The auditor holds engine keys for verification
only and signs only under its own derived keys. Non-success is never shown as success. Every audit carries the engine
scope statement and the audit scope sentence: results prove properties of the encoding only.

Main entry points: :class:`TransferAuditor` (live use), :func:`run_overseer_checks` (the pure function over a view),
:class:`KeyRing`, :class:`ChannelJournal`, :class:`ResultStore`, :class:`OverseerView`, :func:`sign_audit` and
:func:`verify_audit`. The design is ``docs/OVERSEER_DESIGN.md``.
"""
from __future__ import annotations

from .audit import (  # noqa: F401
    ALWAYS_REPLAY_CODES, AUDIT_CONTRACT, AUDITOR_AGENT_ID, AuditResult, TransferAuditor, audit_envelope, audit_signable_text, run_overseer_checks,
    sign_audit, transfer_states, verify_audit,
)
from .codes import OVS_CODES, STAGES, is_agent_code, ovs_finding, severity_of  # noqa: F401
from .contracts import (  # noqa: F401
    AUDIT_SCOPE_SENTENCE, AUDIT_SCOPE_STATEMENT, AUDITOR_VERSION, CLEARANCE_STATES, AuditCoverage, Citation, Divergence, JournalEntry, JournalHead,
    OverseerAudit, ResultTombstone, StoredResult, TransferClearance,
)
from .journal import ChainBreak, ChannelJournal, JournalSealed, JournalSet  # noqa: F401
from .keys import AUDIT_KEY_ID, INTAKE_KEY_ID, RUN_KEY_ID, EngineKey, KeyRing  # noqa: F401
from .replay import Replayer, ReplayJob, ReplayOutcome  # noqa: F401
from .store import PutOutcome, ResultStore  # noqa: F401
from .view import OverseerView, Transfer  # noqa: F401
