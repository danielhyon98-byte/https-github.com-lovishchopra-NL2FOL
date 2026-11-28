"""The meaning label in the checks service (meaning-check design 2.5.1 item 1, 2.5.6 to 2.5.9; stage 2a, owner R5).

The block-only meaning label (:mod:`epinoic_logic.selfcert_label`) reads each answer the rule reader passes and can only
withhold. This module is the service's side of it:

* **The setting** ``EPINOIC_SELFCERT_LABEL`` (:func:`parse_setting`): ``unconfigured`` (the default: no labeller is given, so
  every release path asks ``selfcert_label.labellers.default_labeller()`` at use time, whose production default withholds
  every answer the reader passes as ``not-configured``), ``recorded:<directory>`` (recorded labels served by request key, for
  ``development`` and ``sim``), ``faithful`` (the reader-backed fake, for ``development`` and ``sim`` only) and
  ``provider:<model identifier>`` (a provider reached only through a transport the deployment injects; the identifier is
  hashed at once and never kept; live calls are off, so no transport is injected anywhere in this repository).
* **The labeller** :func:`live_labeller` builds from the setting; :func:`check_label` is the preflight's part (``KIT-HS-017``
  no labeller on a hosted environment or a setting that cannot be read, ``KIT-HS-018`` a fake or recorded labeller on a
  hosted environment or a provider in the simulation, ``KIT-HS-019`` a model digest with no acceptance record).
* **The handshake member** :func:`label_caps`: the label version, the label digest, the model digest (never a name), the
  labeller's kind and its state ``ok``, ``degraded`` or ``off`` from ``Labeller.health()``, read at each request.
* **The receipt's label** :func:`receipt_label`: the refusal a deliverable's receipt calls for (INT-SELF-002:
  ``selfcert_label_unavailable``, KIT-DL-014; INT-SELF-001: ``not_deliverable``, KIT-DL-006) and the unavailable kinds.
* **The daily outage counts** :class:`LabelOutageCounter`: INT-SELF-002 answers by kind, per UTC day, in the metadata log
  (counts only, never text: decision D15), with an alarm above :data:`ALARM_RATE` of the day's answers.
* **Recorded labels** :func:`load_recordings`: a round's ``labels/`` directory (design 3.4), keyed by request key. An
  unrecorded key is ``unavailable`` (``not-recorded``): withheld and counted, never treated as clean.

Nothing here calls a provider, opens a connection, or lets a label's text reach a verdict, a log, the IR or the engine.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from .errors import IntegrationError

__all__ = [
    "SETTING_ENV", "KEY_ENV", "RECORDING_KEY", "LABELLER_KINDS", "LABEL_STATES", "LABEL_ACCEPTANCE", "ALARM_RATE",
    "UNAVAILABLE_REFUSAL", "NAMED_REFUSAL", "LabelSetting", "LabelSetup", "parse_setting", "live_labeller", "check_label",
    "labeller_kind", "label_caps", "receipt_label", "named_claim_ids", "load_recordings", "provider_labeller",
    "LabelOutageCounter", "HOSTED_ENVS",
]

log = logging.getLogger("epinoic_logic.integration")

#: The setting's environment variable (``integration/PROTOCOL.md`` section 3).
SETTING_ENV = "EPINOIC_SELFCERT_LABEL"
#: The canary key of a provider labeller (a deployment secret, hex, at least 32 bytes) and, when set, of recorded labels.
KEY_ENV = "EPINOIC_SELFCERT_LABEL_KEY"
#: The offline recording key (design 3.4): recorded labels of ``development`` and ``sim`` are rendered with it unless
#: ``EPINOIC_SELFCERT_LABEL_KEY`` names another, so recordings reproduce and the deployment secret never leaves the
#: deployment. It is not a secret: it keys canaries of recordings only, never a hosted label.
RECORDING_KEY = b"epinoic selfcert-label offline recording key (not a secret; recordings only)"
#: The labeller kinds the handshake reports.
LABELLER_KINDS: tuple[str, ...] = ("unconfigured", "recorded", "faithful", "provider", "other")
#: The label states the handshake reports (``Labeller.health()``).
LABEL_STATES: tuple[str, ...] = ("ok", "degraded", "off")
#: Environments that are hosted: they serve labels from an accepted provider only.
HOSTED_ENVS = frozenset({"staging", "production"})
#: Acceptance records (decision L2): the pairs (label version, label digest, model digest) whose measurement on the blind
#: sets met the approved bounds. A hosted preflight serves labels only for a pair listed here. EMPTY: no label has been
#: measured yet (stage 2b records and measures them), so every hosted preflight refuses (``KIT-HS-019``).
LABEL_ACCEPTANCE: tuple[Mapping[str, str], ...] = ()
#: The daily alarm (design 2.5.8): more than this share of the day's answers withheld for an unavailable label.
ALARM_RATE = 0.02
#: The overseer refusal of an unavailable label (KIT-DL-014) and of a named one (KIT-DL-006), interface (b).
UNAVAILABLE_REFUSAL = "selfcert_label_unavailable"
NAMED_REFUSAL = "not_deliverable"
#: The receipt codes of the label (raised by the channel, ``channel.bus.SELFCERT_LABEL_CODES``).
_NAMED_CODE, _UNAVAILABLE_CODE = "INT-SELF-001", "INT-SELF-002"
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class LabelSetting:
    """The parsed setting: ``kind`` is ``unconfigured``, ``recorded``, ``faithful`` or ``provider``; ``directory`` the
    recorded labels; ``model_digest`` the SHA-256 of a provider's model identifier (the identifier itself is never kept)."""
    kind: str
    directory: Optional[str] = None
    model_digest: Optional[str] = None


@dataclass(frozen=True)
class LabelSetup:
    """The labeller the service uses (``None``: the default, looked up at each use) and the setting it came from."""
    setting: LabelSetting
    labeller: Any = field(default=None, repr=False)


def parse_setting(value: Optional[str]) -> LabelSetting:
    """``EPINOIC_SELFCERT_LABEL`` read (module docstring); a value that is none of the four forms is ``KIT-HS-017``."""
    v = (value or "").strip()
    if v in ("", "unconfigured"):
        return LabelSetting("unconfigured")
    if v == "faithful":
        return LabelSetting("faithful")
    if v.startswith("recorded:") and v[len("recorded:"):].strip():
        return LabelSetting("recorded", directory=v[len("recorded:"):].strip())
    if v.startswith("provider:") and v[len("provider:"):].strip():
        from ..selfcert_label.labellers import model_digest
        return LabelSetting("provider", model_digest=model_digest(v[len("provider:"):].strip()))
    raise IntegrationError("KIT-HS-017", f"{SETTING_ENV} is not unconfigured, recorded:<directory>, faithful or provider:<model>")


def _key(hex_value: Optional[str], *, required: bool) -> Optional[bytes]:
    if not hex_value:
        if required:
            raise IntegrationError("KIT-HS-017", f"{KEY_ENV} is not set (a provider label needs its canary key)")
        return None
    try:
        key = bytes.fromhex(hex_value)
    except ValueError:
        raise IntegrationError("KIT-HS-017", f"{KEY_ENV} is not hex text") from None
    if len(key) < 32:
        raise IntegrationError("KIT-HS-017", f"{KEY_ENV} is shorter than 32 bytes")
    return key


def load_recordings(directory: str | Path) -> tuple[dict[str, dict], Optional[str]]:
    """``(recordings by request key, the one model digest they name)`` from a ``labels/`` directory (design 3.4), or from
    a directory of rounds each holding one (``<round>/labels/``). Each file is a JSON object ``{request_key, label_version,
    label_digest, model_digest, raw_text, stop_reason?, provider_info?}``, or a list of them. A directory with no recording is
    valid (every key is then unrecorded: withheld as ``not-recorded``). Raises ``ValueError`` on a file that is not such a
    record, on two recordings of one key that differ, and on recordings of more than one model."""
    d = Path(directory)
    if not d.is_dir():
        raise ValueError("the recorded labels directory does not exist")
    dirs = [d / "labels"] if (d / "labels").is_dir() else ([p / "labels" for p in sorted(d.iterdir()) if (p / "labels").is_dir()] or [d])
    out: dict[str, dict] = {}
    models: set[str] = set()
    for ld in dirs:
        for path in sorted(ld.glob("*.json")):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise ValueError(f"recorded label {path.name} is not readable JSON") from None
            for rec in (doc if isinstance(doc, list) else [doc]):
                if not (isinstance(rec, dict) and isinstance(rec.get("request_key"), str) and _HEX64.match(rec["request_key"])
                        and isinstance(rec.get("raw_text"), str) and isinstance(rec.get("model_digest"), str)
                        and _HEX64.match(rec["model_digest"]) and isinstance(rec.get("label_version"), str)):
                    raise ValueError(f"recorded label {path.name} is not a label recording")
                entry = {k: rec[k] for k in ("raw_text", "model_digest", "label_version", "label_digest", "stop_reason") if k in rec}
                held = out.get(rec["request_key"])
                if held is not None and held != entry:
                    raise ValueError(f"two recordings of one request key differ ({path.name})")
                out[rec["request_key"]] = entry
                models.add(rec["model_digest"])
    if len(models) > 1:
        raise ValueError("the recorded labels name more than one model")
    return out, (next(iter(models)) if models else None)


def live_labeller(setting: LabelSetting, *, key_hex: Optional[str] = None, transport: Optional[Callable[..., Any]] = None,
                  clock: Optional[Callable[[], float]] = None) -> Any:
    """The labeller of ``setting``: ``None`` for ``unconfigured`` (every release path then asks the default at use time);
    a :class:`~epinoic_logic.selfcert_label.RecordedLabeller` over the directory's recordings (one share scope per
    directory content, so the service's step 4 and the hub share one call); the faithful fake; or a provider labeller over
    the injected ``transport`` behind the circuit breaker (no transport: ``KIT-HS-017``; this repository injects none)."""
    from ..selfcert_label import labellers as L
    if setting.kind == "unconfigured":
        return None
    if setting.kind == "faithful":
        from ..selfcert_label.fakes import ReaderBackedLabeller
        return ReaderBackedLabeller(clock=clock)
    if setting.kind == "recorded":
        try:
            recordings, model = load_recordings(setting.directory or "")
        except ValueError as exc:
            raise IntegrationError("KIT-HS-017", f"the recorded labels cannot be served: {exc}") from None
        scope = hashlib.sha256(json.dumps(recordings, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
        return L.RecordedLabeller(recordings, key=_key(key_hex, required=False) or RECORDING_KEY, model_digest=model or "",
                                  clock=clock, share_scope=f"recorded:{scope}")
    if setting.kind == "provider":
        if transport is None:
            raise IntegrationError("KIT-HS-017", "no label transport is injected (live label calls are off)")
        return provider_labeller(transport, model_digest=setting.model_digest or "", key_hex=key_hex, clock=clock)
    raise IntegrationError("KIT-HS-017", f"{SETTING_ENV} names no labeller")  # pragma: no cover - parse_setting refuses it


def provider_labeller(transport: Callable[..., Any], *, model_digest: str, key_hex: Optional[str],
                      clock: Optional[Callable[[], float]] = None) -> Any:
    """A provider labeller over an INJECTED transport, behind the circuit breaker (the deployment's own call; never made in
    this repository, whose live calls are off). The labeller is bound to ``model_digest`` (the SHA-256 the setting computed
    from the configured identifier; the identifier itself was never kept)."""
    from ..selfcert_label import labellers as L
    if not (isinstance(model_digest, str) and _HEX64.match(model_digest)):
        raise IntegrationError("KIT-HS-017", "a provider label names no model")
    inner = L.ProviderLabeller(transport, key=_key(key_hex, required=True), model_id="", clock=clock)
    inner.model_digest = model_digest  # the configured model's digest, never the empty placeholder's
    return L.CircuitBreakerLabeller(inner, clock=clock)


def labeller_kind(labeller: Any) -> str:
    """The kind of a labeller (:data:`LABELLER_KINDS`), read through its wrappers."""
    from ..selfcert_label import labellers as L
    from ..selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller
    seen = 0
    while seen < 8 and isinstance(labeller, (L.CachingLabeller, L.BudgetedLabeller, L.CircuitBreakerLabeller)):
        labeller, seen = labeller.inner, seen + 1
    if isinstance(labeller, L.UnconfiguredLabeller):
        return "unconfigured"
    if isinstance(labeller, L.RecordedLabeller):
        return "recorded"
    if isinstance(labeller, ReaderBackedLabeller):
        return "faithful"
    if isinstance(labeller, ScriptedLabeller):
        return "other"
    if isinstance(labeller, L.ProviderLabeller):
        return "provider"
    return "other"


def check_label(setting: LabelSetting, labeller: Any, *, profile: str, service_env: str,
                acceptance: Optional[Iterable[Mapping[str, str]]] = None) -> None:
    """The preflight's part (``KIT-HS-017/018/019``; module docstring). A hosted environment (staging, production) serves
    labels only from a provider labeller whose pair (label digest, model digest) has an acceptance record; development
    and the simulation run with the unconfigured default, recorded labels or the faithful fake, never a provider."""
    kind = labeller_kind(labeller) if labeller is not None else setting.kind
    if service_env in HOSTED_ENVS:
        if labeller is None or kind == "unconfigured":
            raise IntegrationError("KIT-HS-017", "a hosted environment needs a meaning labeller (EPINOIC_SELFCERT_LABEL is unconfigured)")
        if kind != "provider":
            raise IntegrationError("KIT-HS-018", f"a hosted environment serves no {kind} labeller (fakes and recordings serve development and sim only)")
        from ..selfcert_label import label_digest
        records = tuple(acceptance) if acceptance is not None else LABEL_ACCEPTANCE
        from ..selfcert_label import LABEL_VERSION
        digest, model = label_digest(), getattr(labeller, "model_digest", None)
        if not any(isinstance(r, Mapping) and r.get("label_version") == LABEL_VERSION and r.get("label_digest") == digest
                   and r.get("model_digest") == model for r in records):
            raise IntegrationError("KIT-HS-019", "no acceptance record exists for this label and model digest (decision L2)")
        return
    if profile == "integration-sim" and kind == "provider":
        raise IntegrationError("KIT-HS-018", "the sim profile labels with recorded labels or the unconfigured default only")


def label_caps(labeller: Any) -> dict:
    """The handshake member ``ports.selfcert_label``: the label version and digest, the model digest (or ``None``), the
    labeller's kind and its state from ``Labeller.health()``, read NOW (``labeller`` ``None``: the default at this call)."""
    from ..selfcert_label import LABEL_VERSION, label_digest
    from ..selfcert_label import labellers as L
    lab = labeller if labeller is not None else L.default_labeller()
    try:
        state = lab.health()
    except Exception:  # noqa: BLE001 - a labeller whose health cannot be read is reported off, never ok
        state = "off"
    if state not in LABEL_STATES:
        state = "off"
    model = getattr(lab, "model_digest", None)
    return {"version": LABEL_VERSION, "label_digest": label_digest(), "required": True, "labeller": labeller_kind(lab),
            "model_digest": model if isinstance(model, str) and _HEX64.match(model) else None, "state": state}


_KIND_RE = re.compile(r"\((" + "|".join(re.escape(k) for k in ("not-configured", "provider-error", "timeout", "budget", "malformed",
                                                                 "incomplete", "control", "oversized", "truncated", "label-failed",
                                                                 "not-recorded")) + r");")


def receipt_label(receipt: Any) -> tuple[Optional[str], tuple[str, ...]]:
    """``(refusal, unavailable kinds)`` of one receipt's label findings: ``selfcert_label_unavailable`` for INT-SELF-002,
    ``not_deliverable`` for INT-SELF-001 (and nothing for a receipt that carries neither, or one that was REJECTED). A kind
    is read from the finding's message (``(<kind>;``) against the closed list of kinds; one that cannot be read is
    ``unknown``. No word of the message reaches anything else."""
    status = getattr(getattr(receipt, "status", None), "value", getattr(receipt, "status", None))
    if receipt is None or status == "REJECTED":
        return None, ()
    named = unavailable = False
    kinds: list[str] = []
    for f in getattr(receipt, "findings", None) or ():
        code = getattr(f, "code", None)
        if code == _UNAVAILABLE_CODE:
            unavailable = True
            m = _KIND_RE.search(str(getattr(f, "message", "") or ""))
            kinds.append(m.group(1) if m else "unknown")
        elif code == _NAMED_CODE:
            named = True
    if unavailable:
        return UNAVAILABLE_REFUSAL, tuple(kinds)
    if named:
        return NAMED_REFUSAL, ()
    return None, ()


def named_claim_ids(receipt: Any) -> frozenset[str]:
    """The claim ids the label names on ``receipt`` (the INT-SELF-001 findings' ``claim_ids``)."""
    out: set[str] = set()
    for f in getattr(receipt, "findings", None) or ():
        if getattr(f, "code", None) == _NAMED_CODE:
            out.update(str(c) for c in (getattr(f, "claim_ids", None) or ()))
    return frozenset(out)


class LabelOutageCounter:
    """Daily counts of answers withheld for an unavailable label, by kind (design 2.5.8; counts only, never text, decision
    D15). :meth:`record` is called once per checked answer; the day's line is logged when the UTC day turns, and the alarm
    once a day as soon as the day's unavailable answers exceed :data:`ALARM_RATE` of its answers."""

    def __init__(self, *, today: Optional[Callable[[], str]] = None, logger: Optional[logging.Logger] = None, rate: float = ALARM_RATE) -> None:
        self._today = today or (lambda: _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d"))
        self._log = logger or log
        self.rate = float(rate)
        self._lock = threading.Lock()
        self.day: Optional[str] = None
        self.answers = 0
        self.unavailable = 0
        self.kinds: dict[str, int] = {}
        self.alarmed = False

    def _line(self) -> str:
        kinds = ",".join(f"{k}:{n}" for k, n in sorted(self.kinds.items())) or "none"
        return f"selfcert_label_daily day={self.day} answers={self.answers} unavailable={self.unavailable} kinds={kinds}"

    def record(self, kinds: Iterable[str]) -> None:
        """One checked answer: ``kinds`` its unavailable kinds (empty for an answer the label read or did not need)."""
        ks = [k if _KIND_RE.search(f"({k};") else "unknown" for k in kinds]
        with self._lock:
            today = self._today()
            if self.day is not None and today != self.day:
                self._log.info(self._line())
                self.answers, self.unavailable, self.kinds, self.alarmed = 0, 0, {}, False
            self.day = today
            self.answers += 1
            if ks:
                self.unavailable += 1
                for k in ks[:1]:
                    self.kinds[k] = self.kinds.get(k, 0) + 1
            if not self.alarmed and self.unavailable > self.rate * self.answers:
                self.alarmed = True
                self._log.warning("selfcert_label_alarm day=%s answers=%d unavailable=%d threshold=%.2f", self.day, self.answers,
                                  self.unavailable, self.rate)

    def snapshot(self) -> dict:
        """The day's counts (numbers and kinds only)."""
        with self._lock:
            return {"day": self.day, "answers": self.answers, "unavailable": self.unavailable, "kinds": dict(self.kinds),
                    "alarm": self.alarmed}
