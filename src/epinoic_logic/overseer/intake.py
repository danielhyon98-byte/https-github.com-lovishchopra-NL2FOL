"""The verdict intake: dossiers out, verdicts in, under the intake key. The agent never builds its own envelope.

**Issue.** ``VerdictIntake(keyring, accepted_packs=...)`` is configured with the knowledge packs it accepts.
:meth:`VerdictIntake.issue` refuses a pack outside them, builds the dossier for one agent under one pack
(:func:`~epinoic_logic.overseer.dossier.build_dossier`) and records the issue ``(agent_id, task_id, dossier_sha256,
pack, lens, mode)``. A later issue for the same agent and task replaces the earlier one.

**Submit.** :meth:`VerdictIntake.submit` takes the agent's reply text exactly as the model returned it and:

1. requires an open issue for ``(agent_id, task_id)`` (``not_issued``) that has not been answered (``duplicate``: an
   issue takes one BOUND submission, whatever its outcome, so a rejected verdict is never silently retried). A reply is
   bound only when it carries the issued dossier's digest; any other reply (junk text, a non-text value, an array, the
   "no dossier" object, a well-formed object naming another digest) is refused under its own reason (``unparseable``,
   ``no_dossier``, ``dossier_mismatch``) and does NOT use up the issue (review rounds 2 and 3: each dossier the intake
   issues carries a keyed ``issue_binding``, so no other agent can derive its digest, and no outcome of an unbound
   submission, ``not_issued`` or ``duplicate`` carries the issue id or the digest, so a party that can call ``submit``
   can neither learn the digest nor pre-empt the issued agent's verdict under that agent's id);
2. parses the text strictly as ONE JSON object (``parse_json_object(strict=True)``: the bare object, or exactly one code
   fence opening and closing the whole reply; prose around a fence, a second fence, duplicate keys, NaN/Infinity,
   trailing prose and non-objects refused): ``unparseable``. The "no dossier" object of When unsure U1 is
   ``no_dossier``, recorded apart so scoring counts it as no review rather than as a malformed verdict;
3. checks the contract (``contract``) and validates against :class:`~epinoic_logic.overseer.verdicts.AgentVerdict`
   (``schema``);
4. checks the copied header against the issue record: ``agent_mismatch``, ``task_mismatch``, ``dossier_mismatch``,
   ``lens_mismatch``, then the pack: outside ``accepted_packs`` is ``pack_unknown``, accepted but not the pack the
   dossier was issued under is ``pack_mismatch`` (dossier-binding faults under the existing meaning of AGENT-005);
5. wraps the verdict in an ``overseer_verdict/1.0`` envelope from the Overseer role (sender: the agent; recipient:
   ``overseer-auditor``), signs it with ``sign_message`` under the intake subkey (key id ``overseer-intake``) and
   accepts it into a ``MessageLog`` per task and request that requires that signature; any ``INT-ENV`` finding is
   ``envelope``.

Every rejection is ``OVS-AGENT-005`` and the verdict is discarded. ``submit`` never raises on agent output, and a bound
reply always leaves an outcome (round-7 finding: a verdict holding a lone UTF-16 surrogate, what a provider SDK hands
over after decoding a truncated ``\\ud83d`` escape, raised ``UnicodeEncodeError`` after the issue was marked answered, so
the verdict was lost and a clean resubmission refused as ``duplicate``). A reply that is not valid Unicode text is
``unparseable``; whatever else fails at a stage is refused under that stage's reason (``unparseable``, ``schema``,
``envelope``) with the error type only, so the one bound submission of an issue is always recorded. A finding message
never contains agent text: only the reason, field locations (list positions and the contract's field names; any other
key is shown as ``<unknown field #n sha256:...>``) and error types. The verdict is data: it is parsed, never evaluated
or followed, and an accepted verdict has no authority; only :func:`~epinoic_logic.overseer.validate.validate_overseer_verdict` assesses
it, and only a confirming deterministic check reaches the router. ``provider_info`` is bookkeeping recorded beside the
verdict, never evidence; but a ``provider_info.prompt_version`` in the runner's form (``<pack>/<version>+<digest
prefix>``) naming another pack than the issue's contradicts the verdict's copied header and is ``pack_mismatch``
(review round 3). Each accepted verdict records how its pack identity is known (``pack_attestation``: ``runner`` for
the package's ``OverseerAgentRunner``, else ``self_reported``: an exported deployment's verdict names the pack only by
the header the model copied, design 17.10).

Deviations from ``docs/OVERSEER_DESIGN.md`` section 9.4, listed as each stage requires:

* ``issue`` takes ``audit=`` (passed to ``build_dossier`` for informed mode) and refuses an unknown pack, an audit that
  does not verify under the audit key, an invalid agent id, lens or mode with :class:`IntakeRefused` (no dossier is
  built or recorded);
* one submission per issue (``duplicate``) and the explicit ``not_issued`` reason are additions; the header checks
  report their own reasons (``agent_mismatch`` ...) where the design names them all "dossier binding";
* the text is bounded at 1 MB (the runner's bound), not the translator's 2 MB;
* the message logs are kept per task AND request (a reopened task id may carry another request id), not per task.
"""
from __future__ import annotations

import hashlib

import json
import re
import threading
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Collection, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..integrity.contracts import AgentMessage, AgentRole, IntegrityFinding, payload_hash, sign_message, verify_message
from ..integrity.envelope import MessageLog
from ..ir.canonical import canonical_json, sha256_hex
from ..translate.parsing import ProviderOutputError, parse_json_object
from .audit import AUDITOR_AGENT_ID, verify_audit
from .codes import ovs_finding
from .contracts import OverseerAudit
from .dossier import build_dossier, dossier_json
from .keys import INTAKE_KEY_ID, KeyRing
from .verdicts import HEADER_ID_PATTERN, LENSES, MODES, VERDICT_CONTRACT, AgentVerdict, PackIdentity, is_no_dossier
from .view import OverseerView

__all__ = [
    "VerdictIntake", "IssueRecord", "IntakeOutcome", "AcceptedVerdict", "IntakeRefused", "IntakeReason", "INTAKE_REASONS", "MAX_VERDICT_BYTES", "MAX_OUTCOMES",
]

MAX_VERDICT_BYTES = 1_048_576
#: Bound of the intake's outcome record (oldest dropped first); accepted verdicts and issues are kept.
MAX_OUTCOMES = 65_536
IntakeReason = Literal[
    "not_issued", "duplicate", "unparseable", "no_dossier", "contract", "schema", "agent_mismatch", "task_mismatch", "dossier_mismatch",
    "lens_mismatch", "pack_unknown", "pack_mismatch", "envelope",
]
INTAKE_REASONS: tuple[str, ...] = (
    "not_issued", "duplicate", "unparseable", "no_dossier", "contract", "schema", "agent_mismatch", "task_mismatch", "dossier_mismatch",
    "lens_mismatch", "pack_unknown", "pack_mismatch", "envelope",
)
_AGENT_ID_RE = re.compile(HEADER_ID_PATTERN.replace("$", r"\Z"))
#: A lone UTF-16 surrogate code point: not valid Unicode text, so no verdict, digest or signature can be made of a reply holding one.
_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class IntakeRefused(ValueError):
    """An issue the intake refuses (no dossier is built): ``reason`` is ``pack_unknown``, ``audit``, ``agent_id``,
    ``lens``, ``mode`` or ``consolidation`` (a consolidated response that does not verify under the consolidation key or
    belongs to another channel; consolidation stage, design section 19)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class IssueRecord(BaseModel):
    """One dossier issued to one agent for one task under one pack."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    issue_id: str
    agent_id: str
    task_id: str
    request_id: str
    channel_uid: str
    dossier_sha256: str
    pack: PackIdentity
    lens: str
    mode: str
    task_audit_id: Optional[str] = None
    issued_at: str


class IntakeOutcome(BaseModel):
    """What the intake did with one submission. ``finding`` is the AGENT-005 of a rejected verdict; an accepted one
    carries the id of the signed envelope. ``detail`` is the intake's own text, never agent text."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    accepted: bool
    agent_id: str
    task_id: str
    reason: Optional[IntakeReason] = None
    detail: str = Field(default="", max_length=2000)
    issue_id: Optional[str] = None
    message_id: Optional[str] = None
    verdict_id: Optional[str] = None
    pack: Optional[PackIdentity] = None
    dossier_sha256: Optional[str] = None
    finding: Optional[IntegrityFinding] = None
    raw_text_sha256: Optional[str] = None
    raw_chars: int = 0
    provider_info: Optional[dict[str, Any]] = None
    received_at: str


#: How the pack identity of an accepted verdict is known: ``runner`` when the package's own ``OverseerAgentRunner`` built
#: the model input from a pack it loaded and verified against the pinned digests and handed the reply over; else
#: ``self_reported`` (an exported deployment: the verdict's pack is the copy of the dossier header the model returned,
#: which proves only that the header was copied, not which system text the model ran under; design 17.10).
PackAttestation = Literal["runner", "self_reported"]
#: ``provider_info.prompt_version`` as the runner records it: ``<pack name>/<version>+<first hex of the pack digest>``.
_PROMPT_VERSION_RE = re.compile(r"\A(?P<name>[A-Za-z0-9._-]{1,64})/(?P<version>[0-9A-Za-z.]{1,16})\+(?P<digest>[0-9a-f]{8,64})\Z")


@dataclass(frozen=True)
class AcceptedVerdict:
    """A verdict the intake accepted: the signed envelope, the parsed verdict and the issue it answers."""
    message: AgentMessage
    verdict: AgentVerdict
    issue: IssueRecord
    provider_info: Optional[dict]
    raw_text_sha256: str
    received_at: str
    pack_attestation: str = "self_reported"


def _provider_info(info: Any) -> Optional[dict]:
    if info is None:
        return None
    try:
        data = info.model_dump(mode="json") if hasattr(info, "model_dump") else dict(info)
        return json.loads(canonical_json(data))
    except Exception:
        return {"unrecorded": type(info).__name__}


def _named_pack(info: Optional[dict]) -> Optional[tuple[str, str, str]]:
    """``(name, version, digest prefix)`` that ``provider_info.prompt_version`` names, or None when it names no pack in
    the runner's form (a provider's own prompt version is not read as a pack)."""
    pv = info.get("prompt_version") if isinstance(info, dict) else None
    if not isinstance(pv, str):
        return None
    m = _PROMPT_VERSION_RE.match(pv)
    return (m.group("name"), m.group("version"), m.group("digest")) if m else None


def _known_fields() -> frozenset[str]:
    from .verdicts import Accusation, AgentVerdict, EngineStatement, EvidenceItem, PackIdentity
    return frozenset(n for m in (AgentVerdict, Accusation, EvidenceItem, EngineStatement, PackIdentity) for n in m.model_fields)


def _schema_detail(exc: ValidationError) -> str:
    """Field locations and error types only: never the input values (agent text). A location part is shown only when it
    is a list position or the name of a field of the verdict contract; any other key (an extra field the agent chose, which
    is agent text) is shown as ``<unknown field #n sha256:...>`` with a short digest, never its words."""
    known = _known_fields()
    unknown: dict[str, int] = {}
    parts = []

    def part(x: Any) -> str:
        if isinstance(x, int) and not isinstance(x, bool):
            return str(x)
        if isinstance(x, str) and x in known:
            return x
        key = str(x)
        n = unknown.setdefault(key, len(unknown) + 1)
        return f"<unknown field #{n} sha256:{hashlib.sha256(key.encode('utf-8', errors='replace')).hexdigest()[:8]}>"
    for e in exc.errors()[:8]:
        loc = "/".join(part(x) for x in e.get("loc", ()))
        etype = e.get("type", "invalid")
        parts.append(f"{loc or '$'}: {etype if isinstance(etype, str) and etype.replace('_', '').isalnum() else 'invalid'}")
    more = len(exc.errors()) - len(parts)
    return "; ".join(parts) + (f"; and {more} more" if more > 0 else "")


class VerdictIntake:
    """Issues dossiers and takes verdicts in, for any number of agents and tasks. Thread-safe."""

    def __init__(self, keyring: KeyRing, *, accepted_packs: Collection[PackIdentity], max_text_bytes: int = MAX_VERDICT_BYTES) -> None:
        packs = frozenset(accepted_packs)
        if not packs:
            raise ValueError("an intake must accept at least one knowledge pack")
        if not all(isinstance(p, PackIdentity) for p in packs):
            raise TypeError("accepted_packs must hold PackIdentity values")
        self._keyring = keyring
        self._packs = packs
        self.max_text_bytes = int(max_text_bytes)
        self._lock = threading.RLock()
        self._issues: dict[tuple[str, str], IssueRecord] = {}
        self._issue_by_id: dict[str, IssueRecord] = {}
        self._dossiers: dict[str, str] = {}
        self._answered: set[str] = set()
        self._logs: dict[tuple[str, str], MessageLog] = {}
        self._verdicts: dict[str, AcceptedVerdict] = {}
        self._outcomes: deque[IntakeOutcome] = deque(maxlen=MAX_OUTCOMES)

    def __repr__(self) -> str:
        return f"VerdictIntake(packs={sorted(p.label for p in self._packs)}, issues={len(self._issue_by_id)}, verdicts={len(self._verdicts)})"

    # ------------------------------------------------------------------ configuration
    @property
    def keyring(self) -> KeyRing:
        return self._keyring

    @property
    def accepted_packs(self) -> frozenset[PackIdentity]:
        return self._packs

    def _intake_key(self) -> bytes:
        return self._keyring.subkey("intake")

    # ------------------------------------------------------------------ issue
    def issue(self, view: OverseerView, *, agent_id: str, lens: str, mode: str, pack: PackIdentity, audit: Optional[OverseerAudit] = None,
              consolidations: Sequence[Any] = ()) -> dict:
        """Build and record the dossier of ``view`` for ``agent_id`` under ``pack``; returns the dossier (a copy).
        ``consolidations`` (signed consolidated responses of the channel) are shown in informed mode only; each must
        verify under the consolidation key and belong to the view's channel, or nothing is issued."""
        if not isinstance(agent_id, str) or not _AGENT_ID_RE.match(agent_id) or agent_id == AUDITOR_AGENT_ID:
            raise IntakeRefused("agent_id", "the agent id is empty, too long, contains a control character or is reserved for the auditor")
        if lens not in LENSES:
            raise IntakeRefused("lens", f"unknown lens {lens!r}")
        if mode not in MODES:
            raise IntakeRefused("mode", f"unknown mode {mode!r}")
        if not isinstance(pack, PackIdentity) or pack not in self._packs:
            raise IntakeRefused("pack_unknown", "the pack is not one this intake accepts; no dossier is issued under it")
        if audit is not None and (not verify_audit(audit, self._keyring) or audit.scope not in ("task", "transfer")):
            raise IntakeRefused("audit", "the audit does not verify under the audit key (or is not a task or transfer audit); its findings are not shown")
        shown = list(consolidations or ())
        if shown:
            from .consolidate import verify_consolidated
            for c in shown:
                if not verify_consolidated(c, self._keyring) or c.channel_uid != view.channel_uid:
                    raise IntakeRefused("consolidation", "a consolidated response does not verify under the consolidation key or belongs to another channel; it is not shown")
        plain = build_dossier(view, mode=mode, lens=lens, agent_id=agent_id, pack=pack, audit=audit, consolidations=shown if mode == "informed" else ())
        # the binding is keyed: only this intake can compute it, so no agent can derive another agent's dossier digest from
        # its own dossier (they differ only in the header); deterministic, so a re-issue gives the same dossier
        binding = self._keyring.mac("intake", "issue-binding|" + canonical_json([agent_id, lens, mode, pack.model_dump(mode="json"), plain["dossier_sha256"]]))[:32]
        dossier = build_dossier(view, mode=mode, lens=lens, agent_id=agent_id, pack=pack, audit=audit, consolidations=shown if mode == "informed" else (),
                                issue_binding=binding)
        record = IssueRecord(issue_id=uuid.uuid4().hex, agent_id=agent_id, task_id=dossier["task"]["task_id"], request_id=dossier["task"]["request_id"],
                             channel_uid=view.channel_uid, dossier_sha256=dossier["dossier_sha256"], pack=pack, lens=lens, mode=mode,
                             task_audit_id=audit.audit_id if audit is not None else None, issued_at=_now())
        with self._lock:
            self._issues[(agent_id, record.task_id)] = record
            self._issue_by_id[record.issue_id] = record
            self._dossiers[record.issue_id] = dossier_json(dossier)
        return json.loads(self._dossiers[record.issue_id])

    def issue_record(self, agent_id: str, task_id: str) -> Optional[IssueRecord]:
        with self._lock:
            return self._issues.get((agent_id, task_id))

    def issue_by_id(self, issue_id: str) -> Optional[IssueRecord]:
        with self._lock:
            return self._issue_by_id.get(issue_id)

    def dossier_for(self, issue: IssueRecord) -> dict:
        """The dossier exactly as issued (a fresh copy: callers cannot change the record)."""
        with self._lock:
            text = self._dossiers[issue.issue_id]
        return json.loads(text)

    def dossier(self, agent_id: str, task_id: str) -> dict:
        rec = self.issue_record(agent_id, task_id)
        if rec is None:
            raise KeyError(f"no dossier was issued to {agent_id!r} for task {task_id!r}")
        return self.dossier_for(rec)

    # ------------------------------------------------------------------ submit
    def _reject(self, *, agent_id: str, task_id: str, reason: str, detail: str, issue: Optional[IssueRecord], raw_sha: Optional[str], raw_chars: int,
                provider_info: Optional[dict], verdict: Optional[AgentVerdict] = None, message_id: Optional[str] = None) -> IntakeOutcome:
        f = ovs_finding("OVS-AGENT-005", f"the verdict of agent {agent_id!r} for task {task_id!r} is invalid ({reason}): {detail}; it is discarded",
                        agent_ids=[agent_id], message_ids=[message_id] if message_id else [])
        out = IntakeOutcome(accepted=False, agent_id=agent_id, task_id=task_id, reason=reason, detail=detail[:2000], issue_id=issue.issue_id if issue else None,
                            message_id=message_id, verdict_id=verdict.verdict_id if verdict is not None else None,
                            pack=verdict.pack if verdict is not None else None, dossier_sha256=issue.dossier_sha256 if issue else None, finding=f,
                            raw_text_sha256=raw_sha, raw_chars=raw_chars, provider_info=provider_info, received_at=_now())
        self._outcomes.append(out)
        return out

    def submit(self, agent_id: str, task_id: str, text: Any, *, provider_info: Any = None, attestation: str = "self_reported") -> IntakeOutcome:
        """Take one reply text for the dossier issued to ``agent_id`` for ``task_id``. Never raises on agent output.
        ``attestation``: ``runner`` only from the package's ``OverseerAgentRunner`` (recorded beside the verdict, never
        evidence); anything else is recorded as ``self_reported``."""
        info = _provider_info(provider_info)
        attested = "runner" if attestation == "runner" else "self_reported"
        is_text = isinstance(text, str)
        raw_sha = sha256_hex(text) if is_text else None
        raw_chars = len(text) if is_text else 0
        with self._lock:
            issue = self._issues.get((agent_id, task_id))
            common = dict(agent_id=str(agent_id)[:128], task_id=str(task_id)[:128], issue=issue, raw_sha=raw_sha, raw_chars=raw_chars, provider_info=info)
            # an outcome of a submission that is not bound to the issue never carries the issue's id or dossier digest:
            # the digest is the proof of holding the dossier, so it is never handed to a caller who did not show it
            unbound = dict(common, issue=None)
            if issue is None:
                return self._reject(reason="not_issued", detail="no dossier was issued to this agent for this task", **unbound)
            if issue.issue_id in self._answered:
                return self._reject(reason="duplicate", detail="this dossier was already answered; an issue takes one submission", **unbound)
            if not self._bound(text, issue):
                # a reply that does not carry this issue's dossier digest proves nothing about who sent it, whatever it is (junk,
                # None, an array, the "no dossier" object, a well-formed verdict naming another digest): it is refused and does
                # NOT use up the issue, so whoever can call submit cannot pre-empt the issued agent's genuine verdict
                reason, detail = self._unbound_reason(text)
                return self._reject(reason=reason, detail=detail + "; it does not carry the digest of the dossier issued to this agent, so the issue stays open",
                                    **unbound)
            self._answered.add(issue.issue_id)
            stage = ["unparseable"]
            try:
                return self._take_bound(issue, text, info, attested, raw_sha, raw_chars, common, stage)
            except Exception as exc:
                # never raises on agent output, and never loses the issue's one bound submission: whatever failed is recorded
                # as a refusal under the stage it failed in (the error type only, never agent text)
                return self._reject(reason=stage[0], detail=f"the reply could not be taken in ({type(exc).__name__}); it is discarded", **common)

    def _take_bound(self, issue: IssueRecord, text: Any, info: Optional[dict], attested: str, raw_sha: Optional[str], raw_chars: int, common: dict,
                    stage: list) -> IntakeOutcome:
        """The stages of a bound reply (the lock held, the issue marked answered). ``stage[0]`` names the stage reached."""
        if not isinstance(text, str):
            return self._reject(reason="unparseable", detail="the reply is not text", **common)
        if _SURROGATE_RE.search(text):
            return self._reject(reason="unparseable", detail="the reply is not valid Unicode text (it holds a lone UTF-16 surrogate code point)", **common)
        try:
            obj = parse_json_object(text, max_bytes=self.max_text_bytes, strict=True)
        except ProviderOutputError:
            return self._reject(reason="unparseable", detail="the reply is not exactly one strict JSON object (fences tolerated, nothing else)", **common)
        stage[0] = "schema"
        if is_no_dossier(obj):
            return self._reject(reason="no_dossier", detail="the agent reported that it received no dossier (no review)", **common)
        if obj.get("contract") != VERDICT_CONTRACT:
            return self._reject(reason="contract", detail=f"the verdict does not name the contract {VERDICT_CONTRACT}", **common)
        try:
            verdict = AgentVerdict.model_validate(obj)
        except ValidationError as exc:
            return self._reject(reason="schema", detail="the verdict does not validate against overseer_verdict/1.0: " + _schema_detail(exc), **common)
        stage[0] = "envelope"
        for field, reason in (("agent_id", "agent_mismatch"), ("task_id", "task_mismatch"), ("dossier_sha256", "dossier_mismatch"), ("lens", "lens_mismatch")):
            if getattr(verdict, field) != getattr(issue, field):
                return self._reject(reason=reason, detail=f"the verdict's {field} is not the one in the dossier issued to this agent", verdict=verdict, **common)
        if verdict.pack not in self._packs:
            return self._reject(reason="pack_unknown", detail="the verdict names a knowledge pack this intake does not accept", verdict=verdict, **common)
        if verdict.pack != issue.pack:
            return self._reject(reason="pack_mismatch", detail=f"the verdict names another pack than the one the dossier was issued under ({issue.pack.label})",
                                verdict=verdict, **common)
        named = _named_pack(info)
        if named is not None and not (named[0] == issue.pack.name and named[1] == issue.pack.version and issue.pack.sha256.startswith(named[2])):
            # the deployment's own record of the pack it ran under contradicts the pack the verdict copied from the header
            return self._reject(reason="pack_mismatch", detail=f"provider_info.prompt_version names another pack than the one the dossier was issued under "
                                f"({issue.pack.label}): the verdict was produced under an altered or other pack", verdict=verdict, **common)
        try:
            payload = json.loads(canonical_json(verdict.model_dump(mode="json")))
            msg = AgentMessage(message_id=uuid.uuid4().hex, request_id=issue.request_id or "unknown", task_id=issue.task_id or "unknown",
                               sender_agent_id=issue.agent_id, sender_role=AgentRole.OVERSEER, recipient_role=AgentRole.OVERSEER,
                               recipient_agent_id=AUDITOR_AGENT_ID, contract=VERDICT_CONTRACT, payload=payload, payload_sha256=payload_hash(payload),
                               created_at=_now())
            msg = sign_message(msg, self._intake_key(), INTAKE_KEY_ID)
        except Exception as exc:
            return self._reject(reason="envelope", detail=f"the verdict could not be wrapped in an envelope ({type(exc).__name__})", verdict=verdict, **common)
        log_key = (issue.task_id, issue.request_id or "unknown")
        log = self._logs.get(log_key)
        if log is None:
            log = self._logs[log_key] = MessageLog(signing_key=self._intake_key(), request_id=log_key[1])
        try:
            env = log.accept(msg)
        except Exception as exc:
            return self._reject(reason="envelope", detail=f"the envelope could not be checked ({type(exc).__name__})", verdict=verdict,
                                message_id=msg.message_id, **common)
        if env:
            return self._reject(reason="envelope", detail="the envelope was refused: " + ", ".join(sorted({f.code for f in env})), verdict=verdict,
                                message_id=msg.message_id, **common)
        self._verdicts[msg.message_id] = AcceptedVerdict(message=msg, verdict=verdict, issue=issue, provider_info=info, raw_text_sha256=raw_sha or "",
                                                         received_at=_now(), pack_attestation=attested)
        out = IntakeOutcome(accepted=True, agent_id=issue.agent_id, task_id=issue.task_id, issue_id=issue.issue_id, message_id=msg.message_id,
                            verdict_id=verdict.verdict_id, pack=verdict.pack, dossier_sha256=issue.dossier_sha256, raw_text_sha256=raw_sha,
                            raw_chars=raw_chars, provider_info=info, received_at=_now())
        self._outcomes.append(out)
        return out

    @staticmethod
    def _bound(text: Any, issue: IssueRecord) -> bool:
        """Whether a reply is bound to the issue: it is text that carries the issued dossier's digest, which only the holder
        of the dossier can know (the dossier carries the intake's keyed ``issue_binding``, and no refusal ever returns the
        digest). Nothing else binds (review round 3): not a reply the strict parse refuses, not the "no dossier" object."""
        return isinstance(text, str) and bool(issue.dossier_sha256) and issue.dossier_sha256 in text

    def _unbound_reason(self, text: Any) -> tuple[str, str]:
        """The reason recorded for a reply that is not bound to its issue (the issue stays open)."""
        if not isinstance(text, str):
            return "unparseable", "the reply is not text"
        if _SURROGATE_RE.search(text):
            return "unparseable", "the reply is not valid Unicode text (it holds a lone UTF-16 surrogate code point)"
        try:
            obj = parse_json_object(text, max_bytes=self.max_text_bytes, strict=True)
        except Exception:  # ProviderOutputError, or anything else the parser raises on agent text: never raised from submit
            return "unparseable", "the reply is not exactly one strict JSON object"
        if is_no_dossier(obj):
            return "no_dossier", "the agent reported that it received no dossier (no review)"
        return "dossier_mismatch", "the reply is a JSON object that names no issued dossier digest"

    # ------------------------------------------------------------------ reading
    def accepted(self, message_id: str) -> Optional[AcceptedVerdict]:
        with self._lock:
            return self._verdicts.get(message_id)

    def accepted_verdicts(self, task_id: Optional[str] = None) -> list[AcceptedVerdict]:
        with self._lock:
            return [v for v in self._verdicts.values() if task_id is None or v.issue.task_id == task_id]

    def outcomes(self, task_id: Optional[str] = None) -> list[IntakeOutcome]:
        with self._lock:
            return [o for o in self._outcomes if task_id is None or o.task_id == task_id]

    def check_message(self, message: Any) -> tuple[bool, str]:
        """Re-check a verdict envelope (validation does this for every verdict, whatever path it arrived by):
        ``(ok, reason)``. It must be an ``overseer_verdict/1.0`` envelope from the Overseer role to the auditor, its
        payload digest must hold, it must be signed under the intake key with key id ``overseer-intake``, and it must be
        the very envelope this intake accepted."""
        if not isinstance(message, AgentMessage):
            return False, "not an envelope"
        if message.contract != VERDICT_CONTRACT:
            return False, "contract"
        if message.sender_role != AgentRole.OVERSEER or message.recipient_role != AgentRole.OVERSEER or message.recipient_agent_id != AUDITOR_AGENT_ID:
            return False, "role"
        try:
            if payload_hash(message.payload) != message.payload_sha256:
                return False, "digest"
        except Exception:
            return False, "digest"
        if message.signature_key_id != INTAKE_KEY_ID or not verify_message(message, self._intake_key()):
            return False, "signature"
        acc = self.accepted(message.message_id)
        if acc is None:
            return False, "not_accepted"
        if acc.message.signature != message.signature or acc.message.payload_sha256 != message.payload_sha256:
            return False, "not_accepted"
        return True, "ok"
