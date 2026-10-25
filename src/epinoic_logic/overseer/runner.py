"""The overseer agent runner: one dossier in, one provider call, the reply handed to the verdict intake as data.

An overseer agent is built only from exportable parts: this code and a loaded knowledge pack
(:class:`~epinoic_logic.overseer.pack.KnowledgePack`). The runner adds no instruction text of its own: the system text is
the pack's (built by the fixed rule of design section 17.8, checked against the manifest's ``system_sha256``; since STEM
repair 11 the composition of the core and the modules the dossier's content needs, :meth:`KnowledgePack.system_text_for`,
whose digest the manifest's ``system_compositions`` records), and the user text is the dossier alone inside one data block.
Its only text of its own is that block's delimiter pair, which the master prompt describes.

:meth:`OverseerAgentRunner.run` takes these steps (section 17.9):

1. **Check the input.** The dossier must validate against :class:`~epinoic_logic.overseer.dossier.Dossier`, its digest
   must recompute, its ``agent_id``, ``lens`` and ``pack`` must be the runner's, and the intake must hold the issue of
   exactly this dossier for this agent under this pack. Otherwise the run is ``refused_input`` and the provider is never
   called (T21); nothing reaches the intake.
2. **Build the input**: the pack's system text for the dossier (the core and the modules its content needs), and
   :func:`render_dossier_block` of the dossier.
3. **Call the provider once** through the completion entry point
   (:class:`~epinoic_logic.translate.providers.base.CompletionProvider`) with ``prompt_version =
   "<pack name>/<version>+<first 16 hex of the pack digest>"``, so every ``ProviderInfo`` names the pack. A provider
   failure is ``provider_error``: no verdict, recorded as no review, never shown as one. The runner never retries.
4. **Hand the reply to the intake unchanged**: ``intake.submit(agent_id, task_id, raw_text, provider_info=...)``. The
   runner never parses, edits, completes or repairs the reply, and never evaluates or executes anything in it; the
   intake parses it strictly as data. The run is ``submitted`` when the intake accepted the envelope and ``invalid``
   (with the AGENT-005 finding) when it did not.

**Authority.** None. A runner holds no key and cannot sign anything. :class:`AgentRun` records what happened (statuses
``refused_input``, ``provider_error``, ``invalid``, ``submitted``) and has no field that confirms, passes or clears
anything: an assessment comes only from :func:`~epinoic_logic.overseer.validate.validate_overseer_verdict`, and only a
confirming deterministic check reaches the router.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 17.9, listed as each stage requires:

* the user text escapes U+0085, U+2028 and U+2029 inside the dossier JSON (as ``\\u0085``, ``\\u2028``, ``\\u2029``),
  so no line of the block, under any line-break convention, can be taken for a delimiter; for every other dossier it
  is byte-identical to ``translate.providers.rendering.data_block("dossier", dossier)``. The deployer README states the
  same rule;
* step 1 also requires the intake's issue record for the agent and task to name this dossier digest, pack and lens
  (``not_issued``, ``issue_mismatch``), so a well-formed dossier the intake did not issue never costs a provider call;
* ``AgentRun`` records the refusal or failure ``reason``, the system and user text digests and timestamps; the intake
  outcome is kept as the intake's reason, the accepted message id and the AGENT-005 finding (not as the intake's own
  outcome object);
* the raw text kept on the run is bounded at 1,048,576 characters (a longer reply is kept as its prefix, flagged, with
  the digest of the whole); the intake receives it whole and applies its own bound;
* a provider that raises something other than ``ProviderError``, or returns something other than a
  ``ProviderResponse`` with text, is ``provider_error`` too (reasons ``provider_exception`` and ``bad_response``).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..integrity.contracts import IntegrityFinding
from ..ir.canonical import sha256_hex
from ..translate.common import truncate
from ..translate.providers.base import ProviderError, ProviderResponse
from ..translate.providers.rendering import BLOCK_CLOSE, BLOCK_OPEN
from .audit import AUDITOR_AGENT_ID
from .dossier import Dossier, verify_dossier_digest
from .pack import KnowledgePack, PackError
from .verdicts import HEADER_ID_PATTERN, LENSES, PackIdentity

__all__ = [
    "OverseerAgentRunner", "AgentRun", "RunStatus", "RUN_STATUSES", "REFUSAL_REASONS", "PROVIDER_FAILURE_REASONS", "render_dossier_block",
    "DOSSIER_LABEL", "MAX_RAW_TEXT_CHARS",
]

RunStatus = Literal["refused_input", "provider_error", "invalid", "submitted"]
RUN_STATUSES: tuple[str, ...] = ("refused_input", "provider_error", "invalid", "submitted")
REFUSAL_REASONS: tuple[str, ...] = (
    "dossier_type", "dossier_schema", "dossier_digest", "agent_mismatch", "lens_mismatch", "pack_mismatch", "not_issued", "issue_mismatch",
)
PROVIDER_FAILURE_REASONS: tuple[str, ...] = ("provider_error", "provider_exception", "bad_response")
#: The data-block label of the dossier in the user text.
DOSSIER_LABEL = "dossier"
#: Bound of the raw reply kept on an :class:`AgentRun`.
MAX_RAW_TEXT_CHARS = 1_048_576
_AGENT_ID_RE = re.compile(HEADER_ID_PATTERN.replace("$", r"\Z"))
#: Characters JSON leaves unescaped that some readers treat as line breaks.
_LINE_BREAKS = {"\u0085": "\\u0085", "\u2028": "\\u2028", "\u2029": "\\u2029"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def render_dossier_block(dossier: Mapping[str, Any]) -> str:
    """The user text: ``<<<DATA dossier>>>``, the dossier as sorted, two-space indented JSON (non-ASCII kept; U+0085,
    U+2028 and U+2029 written as JSON escapes), ``<<<END dossier>>>``. Every string of the dossier stays on a line that
    also holds JSON, so no dossier text can stand alone as a delimiter."""
    body = json.dumps(dossier, indent=2, ensure_ascii=False, sort_keys=True)
    for ch, esc in _LINE_BREAKS.items():
        body = body.replace(ch, esc)
    return "\n".join([BLOCK_OPEN.format(label=DOSSIER_LABEL), body, BLOCK_CLOSE.format(label=DOSSIER_LABEL)])


class AgentRun(BaseModel):
    """What one run of one overseer agent did. Bookkeeping only: no field confirms, passes or clears anything."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    agent_id: str
    lens: str
    pack: PackIdentity
    status: RunStatus
    reason: Optional[str] = Field(default=None, description="refused_input, provider_error: why; invalid: the intake's AGENT-005 reason")
    detail: str = Field(default="", max_length=2000, description="the runner's own text, never agent text")
    task_id: Optional[str] = None
    dossier_sha256: Optional[str] = None
    prompt_version: str
    system_sha256: str = Field(description="the digest of the system text sent (the composition for the dossier), or of the whole text when "
                                           "nothing was sent")
    #: STEM repair 11: the pack modules the system text sent holds (the dossier's content decides them)
    system_modules: tuple[str, ...] = ()
    user_sha256: Optional[str] = None
    provider_name: Optional[str] = None
    provider_info: Optional[dict[str, Any]] = None
    raw_text_sha256: Optional[str] = None
    raw_chars: int = 0
    raw_text: Optional[str] = Field(default=None, description="the reply as received (bounded); data, never evaluated")
    raw_text_truncated: bool = False
    message_id: Optional[str] = Field(default=None, description="the id of the envelope the intake signed, when it accepted the reply")
    finding: Optional[IntegrityFinding] = Field(default=None, description="the intake's OVS-AGENT-005, when it rejected the reply")
    started_at: str
    finished_at: str


class OverseerAgentRunner:
    """Runs one overseer agent: a loaded pack, a completion provider, an agent id and a lens. Holds no key."""

    def __init__(self, pack: KnowledgePack, provider: Any, *, agent_id: str, lens: str) -> None:
        if not isinstance(pack, KnowledgePack):
            raise TypeError("an overseer agent is configured only from a KnowledgePack loaded by load_pack")
        pack.verify()
        if not callable(getattr(provider, "complete", None)):
            raise TypeError("the provider must implement complete(system, user, *, prompt_version)")
        if not isinstance(agent_id, str) or not _AGENT_ID_RE.match(agent_id) or agent_id == AUDITOR_AGENT_ID:
            raise ValueError("the agent id is empty, too long, contains a control character or is reserved for the auditor")
        if lens not in LENSES:
            raise ValueError(f"unknown lens {lens!r}")
        self._pack = pack
        self._provider = provider
        self._agent_id = agent_id
        self._lens = lens
        self._system = pack.system_text()
        if sha256_hex(self._system) != pack.system_sha256:
            raise PackError("system_digest", "the pack's system text does not match its manifest")

    def __repr__(self) -> str:
        return f"OverseerAgentRunner(agent_id={self._agent_id!r}, lens={self._lens!r}, pack={self._pack.identity.label!r})"

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def lens(self) -> str:
        return self._lens

    @property
    def pack(self) -> KnowledgePack:
        return self._pack

    @property
    def identity(self) -> PackIdentity:
        return self._pack.identity

    @property
    def prompt_version(self) -> str:
        return self._pack.prompt_version

    def build_input(self, dossier: Mapping[str, Any]) -> tuple[str, str]:
        """``(system, user)`` exactly as :meth:`run` sends them (no input check): the pack's composition for the dossier's content."""
        return self._pack.system_text_for(dossier), render_dossier_block(dossier)

    def _system_for(self, dossier: Mapping[str, Any]) -> tuple[str, tuple[str, ...], str]:
        """``(system text, modules, digest)`` for ``dossier``; the digest must be the manifest's for that composition."""
        modules = self._pack.modules_for(dossier)
        system = self._pack.system_text(modules)
        digest = sha256_hex(system)
        if digest != self._pack.composition_sha256(modules):
            raise PackError("system_digest", "the pack's composition for the dossier does not match its manifest")
        return system, modules, digest

    # ------------------------------------------------------------------ run
    def _run(self, status: str, started: str, **kw: Any) -> AgentRun:
        kw.setdefault("system_sha256", self._pack.system_sha256)
        return AgentRun(agent_id=self._agent_id, lens=self._lens, pack=self._pack.identity, status=status, prompt_version=self.prompt_version,
                        provider_name=getattr(self._provider, "name", None) if isinstance(
                            getattr(self._provider, "name", None), str) else None, started_at=started, finished_at=_now(), **kw)

    def _check(self, dossier: Any, intake: Any) -> tuple[Optional[dict], str, str]:
        """``(dossier copy, reason, detail)``; the copy is None when the input is refused."""
        try:
            d = json.loads(json.dumps(dossier, ensure_ascii=False, allow_nan=False))
        except (TypeError, ValueError, RecursionError):
            return None, "dossier_type", "the dossier is not a JSON object"
        if not isinstance(d, dict):
            return None, "dossier_type", "the dossier is not a JSON object"
        try:
            Dossier.model_validate(d)
        except ValidationError as exc:
            return None, "dossier_schema", f"the dossier does not validate against dossier 1.0 ({len(exc.errors())} errors)"
        if not verify_dossier_digest(d):
            return None, "dossier_digest", "the dossier's digest does not recompute"
        if d["agent_id"] != self._agent_id:
            return None, "agent_mismatch", "the dossier was issued for another agent"
        if d["lens"] != self._lens:
            return None, "lens_mismatch", "the dossier was issued for another lens"
        if PackIdentity.model_validate(d["pack"]) != self._pack.identity:
            return None, "pack_mismatch", "the dossier was issued under another pack than the runner's"
        issue = intake.issue_record(self._agent_id, d["task"]["task_id"])
        if issue is None:
            return None, "not_issued", "the intake issued no dossier to this agent for this task"
        if issue.dossier_sha256 != d["dossier_sha256"] or issue.pack != self._pack.identity or issue.lens != self._lens:
            return None, "issue_mismatch", "the dossier is not the one the intake issued to this agent"
        return d, "", ""

    def run(self, dossier: Mapping[str, Any], intake: Any) -> AgentRun:
        """Review one dossier: check it, call the provider once, hand the reply to the intake unchanged."""
        if not callable(getattr(intake, "issue_record", None)) or not callable(getattr(intake, "submit", None)):
            raise TypeError("intake must be a VerdictIntake")
        started = _now()
        d, reason, detail = self._check(dossier, intake)
        if d is None:
            ident: dict[str, Any] = {}
            if isinstance(dossier, Mapping):
                task = dossier.get("task")
                tid = task.get("task_id") if isinstance(task, Mapping) else None
                dsha = dossier.get("dossier_sha256")
                ident = {"task_id": tid[:128] if isinstance(tid, str) else None, "dossier_sha256": dsha if isinstance(dsha, str) and len(dsha) == 64 else None}
            return self._run("refused_input", started, reason=reason, detail=detail, **ident)
        task_id, dsha = d["task"]["task_id"], d["dossier_sha256"]
        system, modules, system_digest = self._system_for(d)
        user = render_dossier_block(d)
        common = dict(task_id=task_id, dossier_sha256=dsha, user_sha256=sha256_hex(user), system_sha256=system_digest, system_modules=modules)
        try:
            resp = self._provider.complete(system, user, prompt_version=self.prompt_version)
        except ProviderError as exc:
            transient = " (transient)" if getattr(exc, "transient", False) else ""
            return self._run("provider_error", started, reason="provider_error", detail=f"ProviderError{transient}: {truncate(str(exc), 300)}", **common)
        except Exception as exc:  # a provider must never crash a review; recorded as no review
            return self._run("provider_error", started, reason="provider_exception", detail=f"the provider raised {type(exc).__name__}", **common)
        if not isinstance(resp, ProviderResponse) or not isinstance(resp.raw_text, str):
            return self._run("provider_error", started, reason="bad_response", detail="the provider returned no ProviderResponse with text", **common)
        raw = resp.raw_text
        info = resp.info.model_dump(mode="json")
        kept = raw if len(raw) <= MAX_RAW_TEXT_CHARS else raw[:MAX_RAW_TEXT_CHARS]
        outcome = intake.submit(self._agent_id, task_id, raw, provider_info=resp.info, attestation="runner")
        reply = dict(provider_info=info, raw_text_sha256=sha256_hex(raw), raw_chars=len(raw), raw_text=kept, raw_text_truncated=len(raw) > MAX_RAW_TEXT_CHARS)
        if outcome.accepted:
            return self._run("submitted", started, message_id=outcome.message_id, **reply, **common)
        return self._run("invalid", started, reason=outcome.reason, detail=f"the intake rejected the reply ({outcome.reason})", finding=outcome.finding,
                         **reply, **common)
