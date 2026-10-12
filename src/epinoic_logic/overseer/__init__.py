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
:func:`verify_audit`. The design is ``docs/OVERSEER_DESIGN.md``; the package's parts are listed in ``README.md`` beside
this file.

Overseer agents are built only from exportable parts: this package's code and a versioned knowledge pack shipped as
package data (``knowledge/overseer-knowledge-docs-<version>/``). The names exported below are:

* the verdict protocol: :func:`build_dossier`, :class:`VerdictIntake`, :func:`validate_overseer_verdict`,
  :func:`combine_verdicts` and their contracts (:class:`AgentVerdict`, :class:`PackIdentity`, :data:`KIND_CHECKS`, ...);
* the knowledge pack: :func:`load_pack`, :func:`installed_pack`, :class:`KnowledgePack`, :data:`PACK_DIGESTS`,
  :class:`PackError`, the agent runner :class:`OverseerAgentRunner` and :class:`AgentRun`; the exporter
  (``python -m epinoic_logic.overseer.export``) is reached as :func:`export_pack` and :func:`verify_export`, imported on
  first use so that running the exporter as a module never finds it imported already;
* translator oversight: every translation of a delivered claim is re-checked as untrusted data (``OVS-TRN-*``,
  :mod:`~epinoic_logic.overseer.checks.translation`) and recorded in the signed audit (:class:`TranslationAudit`;
  :class:`TranslationRecord`, :func:`translation_records`, ``TransferAuditor.translations``);
* the observer hook and live operation: the router policy (:func:`may_act`, :func:`may_release`,
  :func:`check_before_acting`, :data:`MAX_PENDING_WAIT_MS`). The hook itself lives in the channel
  (``TranslatorChannel(observers=...)``) and the hub (``RouterHub(observers=..., auditor=...)``), which never import
  this package unless an auditor is attached;
* consolidation and self-duplication (design section 19): ``consolidate.consolidate`` (not re-exported here, so the
  name ``consolidate`` stays the submodule) and the signed
  :class:`ConsolidatedResponse` (``consolidated_response/1.0``) when several agents answer one input, with
  :func:`delivery_decision` / :func:`may_deliver` for the router and :func:`check_consolidation` (OVS-CONS-004);
  repeated-fault signatures and detection (:func:`detect_repeats`, :class:`RepeatReport`, OVS-REP-001); and the overseer
  pool (:class:`OverseerPool`, :func:`plan_pool`, :class:`PoolPlan`) that decides how many overseer-agent instances,
  all from one loaded pack, review a batch. The hub's entry points are ``RouterHub.consolidate``, ``repeats`` and
  ``review_pool``.

A verdict is advisory and decides nothing: only a deterministic check's ``OVS-*`` finding reaches the router, and
``OVS-AGENT-*`` findings never change a clearance.
"""
from __future__ import annotations

from .audit import (  # noqa: F401
    ALWAYS_REPLAY_CODES, AUDIT_CONTRACT, AUDITOR_AGENT_ID, AuditResult, TransferAuditor, audit_envelope, audit_signable_text, run_overseer_checks,
    sign_audit, transfer_states, verify_audit,
)
from .codes import OVS_CODES, STAGES, is_agent_code, ovs_finding, severity_of  # noqa: F401
from .contracts import (  # noqa: F401
    AUDIT_SCOPE_SENTENCE, AUDIT_SCOPE_STATEMENT, AUDITOR_VERSION, CLEARANCE_STATES, AuditCoverage, Citation, Divergence, JournalEntry, JournalHead,
    OverseerAudit, ResultTombstone, StoredResult, TransferClearance, TranslationAudit,
)
from .journal import ChainBreak, ChannelJournal, JournalSealed, JournalSet  # noqa: F401
from .keys import AUDIT_KEY_ID, INTAKE_KEY_ID, RUN_KEY_ID, EngineKey, KeyRing  # noqa: F401
from .replay import Replayer, ReplayJob, ReplayOutcome  # noqa: F401
from .store import PutOutcome, ResultStore  # noqa: F401
from .view import OverseerView, Transfer  # noqa: F401
from .checks.translation import TRANSLATION_CHECKS, TranslationRecord, translation_records  # noqa: F401

# ---------------------------------------------------------------------------------------- verdict protocol
from .verdicts import (  # noqa: F401,E402
    ACCUSATION_KINDS, DOSSIER_VERSION, KIND_CHECKS, LENSES, MODES, NO_DOSSIER_MARKER, VERDICT_CONTRACT, Accusation, AccusationKind, AgentVerdict,
    EngineStatement, EvidenceItem, PackIdentity, is_no_dossier,
)
from .dossier import Dossier, build_dossier, dossier_digest, resolve_pointer, verify_dossier_digest  # noqa: F401,E402
from .intake import INTAKE_REASONS, AcceptedVerdict, IntakeOutcome, IntakeRefused, IssueRecord, VerdictIntake  # noqa: F401,E402
from .validate import (  # noqa: F401,E402
    OUTCOME_CODES, AccusationAssessment, EngineStatementAssessment, FindingRef, VerdictAssessment, build_verdicts_audit, validate_overseer_verdict,
)
from .combine import AccusationGroup, CombinedAssessment, combine_verdicts, combined_audit, combined_digest  # noqa: F401,E402

# ---------------------------------------------------------------------------------------- knowledge pack and agent runner
from .pack import (  # noqa: F401,E402
    PACK_DIGESTS, PACK_ERROR_REASONS, PACK_NAME, PACK_VERSION, KnowledgePack, PackError, accepted_identities, installed_pack, load_pack,
)
from .runner import RUN_STATUSES, AgentRun, OverseerAgentRunner, render_dossier_block  # noqa: F401,E402

# ---------------------------------------------------------------------------------------- hook: router policy
from .policy import (  # noqa: F401,E402
    ACTABLE_STATES, MAX_PENDING_WAIT_MS, PolicyDecision, act_decision, bounded_wait_ms, check_before_acting, may_act, may_release, receipt_digest,
    release_decision,
)

# ---------------------------------------------------------------------------------------- consolidation, repeated faults, the overseer pool
from .repeats import SIGNATURE_RULE, FaultOccurrence, RepeatRecord, RepeatReport, content_form, detect_repeats, fault_occurrences, figures_of  # noqa: F401,E402
from .consolidate import (  # noqa: F401,E402
    CONSOLIDATED_CONTRACT, CONSOLIDATION_STATUSES, DELIVERABLE_STATUSES, AdvisoryNote, ConsolidatedGroup, ConsolidatedMember, ConsolidatedResponse,
    ConsolidationDecision, EngineCheck, ExcludedOutput, GroupConflict, check_consolidation, consolidation_envelope, delivery_decision, may_deliver,
    sign_consolidated, verify_consolidated,
)
from .pool import DEFAULT_MAX_INSTANCES, MODEL_TIER, OverseerPool, PoolConfig, PoolItem, PoolPlan, plan_pool  # noqa: F401,E402
from .keys import CONSOLIDATION_KEY_ID  # noqa: F401,E402

_EXPORTER_NAMES = frozenset({"export_pack", "verify_export", "ExportError", "ExportResult"})


def __getattr__(name: str):
    """The exporter's names, imported on first use (``python -m epinoic_logic.overseer.export`` must not find the module
    imported by the package before it runs)."""
    if name in _EXPORTER_NAMES:
        from . import export
        return getattr(export, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
