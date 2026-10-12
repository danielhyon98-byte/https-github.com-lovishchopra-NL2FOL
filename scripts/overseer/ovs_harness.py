"""Shared parts of the contained Overseer harness (``scripts/overseer``): test keys, output-directory guards, arena
replays through a hub that carries the auditor, the transfer records (journaled channel events plus the signed task
audit) that let a later process rebuild exactly the state a dossier was issued from, and the overseer-agent helpers
(an exported pack, runners built only from it, scripted probe providers).

Nothing here is part of the package: the harness drives the package's public code (``RouterHub(auditor=...)``,
``TransferAuditor``, ``VerdictIntake``, ``validate_overseer_verdict``, ``load_pack``, ``export_pack``,
``OverseerAgentRunner``) and never configures an overseer agent itself. It holds no instruction text for agents: an
agent's whole configuration is the knowledge pack, exported by the package's exporter and loaded by its loader.

Rules every script of the harness follows (design section 13.1):

* keys are test constants (below); there is no network and no model call;
* a recorded round is a read-only input: it is copied into the output directory first (:func:`copy_round`) and the
  arena runs on the copy; :func:`check_output_dir` refuses an output directory inside a recorded round (or a round
  inside the output directory);
* every output goes under the directory given on the command line.

Transfer records. A dossier is built only from a channel's journal, and the journal holds every event exactly as it was
issued. :func:`write_record` writes one channel's events as JSON lines (``ChannelEvent.to_dict``) beside its signed task
audit; :func:`event_from_record` reads an event back field for field, and :func:`rebuild` feeds the events of one
channel, in order, to a fresh :class:`~epinoic_logic.overseer.audit.TransferAuditor` (through ``on_event``, with no live
channel), so the rebuilt journal, store and view are those the exporter issued its dossiers from and a re-issued blind
dossier has the same digest. What a rebuild cannot have is the live channel: custody of live objects (a payload edited
in the log after its receipt, a receipt the router edited) is decided by the recorded signed task audit, never
re-decided; an informed dossier shows that audit's findings, so it is re-issued from the same recorded audit.

Deviation from ``docs/OVERSEER_DESIGN.md`` section 14 (stage ``harness``): this helper module is a file the stage's list
does not name; it holds what several of the listed scripts share, so that no script imports another script's command
line.
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional

from epinoic_logic.channel.events import CapturedResult, ChannelEvent, PoolEntry
from epinoic_logic.ir.canonical import canonical_json
from epinoic_logic.overseer import EngineKey, KeyRing, OverseerAudit, TransferAuditor, verify_audit

REPO_ROOT = Path(__file__).resolve().parents[2]
ARENA_SCRIPT = REPO_ROOT / "scripts" / "arena" / "run_arena.py"

#: The overseer secret of every harness keyring (a test constant; it differs from every engine key, as KeyRing checks).
HARNESS_SECRET = b"overseer-harness-secret-0123456789abcdef-0123"
#: The engine key of the harness's synthetic tasks (a test constant).
SYNTHETIC_ENGINE_KEY = b"overseer-harness-engine-key-0123456789abcdef"
#: A second engine key, declared EXTERNAL in the synthetic keyring (T11: an insider holding an external engine's key).
EXTERNAL_ENGINE_KEY = b"overseer-harness-external-engine-key-0123456"
#: A key no keyring declares (T4b: a result signed with a wrong key).
WRONG_ENGINE_KEY = b"overseer-harness-wrong-engine-key-0123456789"
#: Engine key ids the hub, the channel and the arena sign under (all one key, as in the arena).
ENGINE_KEY_IDS = ("hub", "channel", "default", "integrity", "t")
#: The recorded rounds the harness knows, in order (each is used only when present).
ROUND_NAMES = ("r1", "r1-adv", "r2", "r3", "r4", "r5", "r6")
#: The rounds the contained run and the dossier export use by default (the stage's acceptance names r2 to r5).
DEFAULT_ROUNDS = ("r2", "r3", "r4", "r5", "r7")
#: One overseer agent per lens: the agent ids the dossier export issues dossiers to (design section 10).
LENS_AGENTS: tuple[tuple[str, str], ...] = (
    ("overseer-custody-1", "custody_results"), ("overseer-content-1", "content_fidelity"), ("overseer-translation-1", "translation_fidelity"),
    ("overseer-peer-1", "peer_synthesis"), ("overseer-general-1", "general"),
)
#: The format of a transfer record directory (events.jsonl, audit.json, record.json).
RECORD_FORMAT = "overseer-transfer-record/1.0"


# ============================================================================================ arena module and keys
def _load_arena():
    """``scripts/arena/run_arena.py`` as a module (imported once, by path: ``scripts/arena`` is not a package)."""
    mod = sys.modules.get("run_arena")
    if mod is not None and getattr(mod, "__file__", None) and Path(mod.__file__).resolve() == ARENA_SCRIPT:
        return mod
    spec = importlib.util.spec_from_file_location("run_arena", ARENA_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run_arena"] = mod
    spec.loader.exec_module(mod)
    return mod


def arena():
    return _load_arena()


def keyring_for(profile: str) -> KeyRing:
    """The harness keyring of a profile: ``arena`` (the arena's engine key under every engine key id) or ``synthetic``
    (the synthetic engine key, plus ``remote`` declared external). A profile is named in records; a key never is."""
    if profile == "arena":
        key = arena().KEY
        return KeyRing({k: EngineKey(key) for k in ENGINE_KEY_IDS}, HARNESS_SECRET)
    if profile == "synthetic":
        keys: dict[str, EngineKey] = {k: EngineKey(SYNTHETIC_ENGINE_KEY) for k in ENGINE_KEY_IDS}
        keys["remote"] = EngineKey(EXTERNAL_ENGINE_KEY, scope="external")
        return KeyRing(keys, HARNESS_SECRET)
    raise ValueError(f"unknown keyring profile {profile!r}")


def new_auditor(keyring: KeyRing, **over: Any) -> TransferAuditor:
    """The contained harness's auditor: inline replay (no worker process to manage), every result replayed, and the
    shadow channel on every task (design section 6.4: contained testing runs it always)."""
    opts: dict[str, Any] = dict(replay_mode="inline", eager=True, shadow="always")
    opts.update(over)
    return TransferAuditor(keyring, **opts)


# ============================================================================================ output directories
class HarnessError(RuntimeError):
    """A refusal of the harness itself (an output directory inside a recorded round, a missing input, ...)."""


def _inside(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def check_output_dir(out: Path, *, inputs: Iterable[Path] = (), must_be_empty: bool = False) -> Path:
    """Create ``out`` (refusing one inside any input directory, an input inside it, or one inside the repository's
    source tree) and return it resolved."""
    out = Path(out)
    for src in inputs:
        src = Path(src)
        if _inside(out, src) or _inside(src, out):
            raise HarnessError(f"the output directory {out} overlaps the read-only input {src}; choose a directory outside the recorded rounds")
    if _inside(out, REPO_ROOT / "src") or _inside(out, REPO_ROOT / "tests") or _inside(out, REPO_ROOT / "scripts") or _inside(out, REPO_ROOT / "docs"):
        raise HarnessError(f"the output directory {out} is inside the repository's sources; choose a directory outside them")
    if must_be_empty and out.exists() and any(out.iterdir()):
        raise HarnessError(f"the output directory {out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    return out.resolve()


def safe_name(text: str) -> str:
    """A file-name-safe form of an identifier (``group::kind`` keys, ``r5/p4`` targets)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-") or "x"


def copy_round(src: Path, dest_root: Path, *, name: Optional[str] = None) -> Path:
    """Copy a recorded round into ``dest_root/<name>`` (never writing into ``src``) and return the copy."""
    src = Path(src)
    if not (src / "specialists").is_dir():
        raise HarnessError(f"{src} is not a round directory (no specialists/)")
    dst = Path(dest_root) / (name or src.name)
    if _inside(dst, src) or _inside(src, dst):
        raise HarnessError(f"refusing to copy {src} into an overlapping directory {dst}")
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "results.json", "summary.md"))
    return dst


def mini_round(src: Path, dest: Path, stems: Iterable[str]) -> Path:
    """A round directory at ``dest`` holding only the specialist files ``stems`` of ``src`` (with their translations,
    syntheses and relayed records): a recorded task replayed on its own."""
    src, dest = Path(src), Path(dest)
    if _inside(dest, src) or _inside(src, dest):
        raise HarnessError(f"refusing to build a round copy at {dest} overlapping {src}")
    if dest.exists():
        shutil.rmtree(dest)
    stems = list(stems)
    for sub in ("specialists", "translations", "syntheses"):
        (dest / sub).mkdir(parents=True, exist_ok=True)
        for stem in stems:
            p = src / sub / f"{stem}.json"
            if p.exists():
                shutil.copy2(p, dest / sub / p.name)
    if not any((dest / "specialists").iterdir()):
        raise HarnessError(f"none of {stems} is a specialist file of {src}")
    rel = src / "relayed"
    if rel.is_dir():
        (dest / "relayed").mkdir(exist_ok=True)
        for stem in stems:
            p = rel / f"{stem}.json"
            if p.exists():
                shutil.copy2(p, dest / "relayed" / p.name)
    return dest


def round_dirs(root: Path, names: Iterable[str]) -> list[tuple[str, Path]]:
    """The recorded rounds ``names`` found under ``root`` (each only when present), in the given order."""
    out = []
    for n in names:
        p = Path(root) / n
        if (p / "specialists").is_dir():
            out.append((n, p))
    return out


def write_json(path: Path, obj: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@contextlib.contextmanager
def patched(*patches: tuple[Any, str, Any]) -> Iterator[None]:
    """Set ``obj.name = value`` for each ``(obj, name, value)`` and restore every attribute afterwards (the harness's
    own monkeypatching: a channel patched to misbehave, a check disabled by a mutant)."""
    saved: list[tuple[Any, str, Any, bool]] = []
    try:
        for obj, name, value in patches:
            if isinstance(obj, type):  # keep the raw class attribute (a staticmethod stays a staticmethod)
                had = name in vars(obj)
                old = vars(obj).get(name)
            else:
                had = hasattr(obj, name)
                old = getattr(obj, name, None)
            saved.append((obj, name, old, had))
            setattr(obj, name, value)
        yield
    finally:
        for obj, name, old, had in reversed(saved):
            if had:
                setattr(obj, name, old)
            else:
                try:
                    delattr(obj, name)
                except AttributeError:
                    pass


# ============================================================================================ arena replays
@dataclass
class ChannelRecord:
    """One channel the arena opened: its hub key (``group`` or ``group::variant``), its uid and the channel."""
    key: str
    uid: str
    task_id: str
    variant: str
    channel: Any


@dataclass
class RoundReplay:
    """A round copy replayed through hubs that carry ``auditor``."""
    round_name: str
    round_dir: Path
    results: dict
    auditor: TransferAuditor
    hubs: list = field(default_factory=list)
    channels: list[ChannelRecord] = field(default_factory=list)

    def channel(self, key: str) -> ChannelRecord:
        return next(c for c in self.channels if c.key == key)

    def hub_for(self, key: str) -> Any:
        rec = self.channel(key)
        return next(h for h in self.hubs if any(ch is rec.channel for ch in h.channels.values()) or rec.uid in h.closed_channels)


@contextlib.contextmanager
def audited_arena(auditor: TransferAuditor, *, genuine_only: bool = False, verify_hook: Optional[Callable[..., Any]] = None) -> Iterator[list]:
    """``run_arena`` with ``RouterHub`` replaced by a hub that carries ``auditor`` (restored afterwards). With
    ``genuine_only`` the arena's fault mutations are switched off (only the genuine pass runs). ``verify_hook`` replaces
    the arena's ``verify_claim``: it is called as ``verify_hook(real, claim, report, translator, **kw)`` inside the
    channel call (so every engine run it makes is captured) and returns the outcome the channel receives."""
    ra = arena()
    from epinoic_logic.branches import hub as hubmod
    hubs: list = []

    class AuditedHub(hubmod.RouterHub):
        def __init__(self, **kw):
            super().__init__(auditor=auditor, **kw)
            hubs.append(self)

    saved = {"RouterHub": ra.RouterHub, "MUTATIONS": ra.MUTATIONS, "verify_claim": ra.verify_claim}
    ra.RouterHub = AuditedHub
    if genuine_only:
        ra.MUTATIONS = ()
    if verify_hook is not None:
        real = saved["verify_claim"]

        def verify_claim(claim, report, translator, **kw):
            return verify_hook(real, claim, report, translator, **kw)
        ra.verify_claim = verify_claim
    try:
        yield hubs
    finally:
        for k, v in saved.items():
            setattr(ra, k, v)


def channel_records(hubs: Iterable[Any]) -> list[ChannelRecord]:
    """Every channel the hubs opened, keyed by the hub key the router used (``group`` or ``group::variant``); a channel
    only in ``closed_channels`` keeps its uid as its key."""
    out: list[ChannelRecord] = []
    seen: set[str] = set()
    for hub in hubs:
        for key, ch in list(hub.channels.items()):
            if ch.channel_uid in seen:
                continue
            seen.add(ch.channel_uid)
            variant = key.split("::", 1)[1] if "::" in key else "genuine"
            out.append(ChannelRecord(key=key, uid=ch.channel_uid, task_id=ch.plan.task_id, variant=variant, channel=ch))
        for uid, ch in list(hub.closed_channels.items()):
            if uid in seen:
                continue
            seen.add(uid)
            out.append(ChannelRecord(key=uid, uid=uid, task_id=ch.plan.task_id, variant="closed", channel=ch))
    return out


def replay_round(round_copy: Path, auditor: TransferAuditor, *, genuine_only: bool = False, verify_hook: Optional[Callable[..., Any]] = None) -> RoundReplay:
    """Run the arena on ``round_copy`` (a COPY: ``run_round`` writes results.json and summary.md into it) with the
    auditor attached to every channel, and return the channels it opened (only those the auditor journaled)."""
    ra = arena()
    with audited_arena(auditor, genuine_only=genuine_only, verify_hook=verify_hook) as hubs:
        results = ra.run_round(Path(round_copy))
    journaled = set(auditor.channel_uids())
    return RoundReplay(round_name=Path(round_copy).name, round_dir=Path(round_copy), results=results, auditor=auditor, hubs=hubs,
                       channels=[c for c in channel_records(hubs) if c.uid in journaled])


# ============================================================================================ transfer records
def event_record(event: ChannelEvent) -> dict:
    """One journaled event as plain JSON (exactly ``ChannelEvent.to_dict``)."""
    return event.to_dict()


def event_from_record(d: dict) -> ChannelEvent:
    """The event of :func:`event_record`, field for field (lists back to tuples). Data only: nothing is evaluated."""
    def pools(xs):
        return tuple(PoolEntry(claim_id=p["claim_id"], problem_digest=p["problem_digest"], ambiguous=bool(p["ambiguous"]), agent_id=p.get("agent_id"),
                               report_id=p.get("report_id")) for p in xs)
    captured = tuple(CapturedResult(result_id=c["result_id"], key_id=c.get("key_id"), result_json=c["result_json"], result_sha256=c["result_sha256"],
                                    problem_json=c.get("problem_json"), problem_digest=c.get("problem_digest")) for c in d["captured"])
    return ChannelEvent(
        channel_uid=d["channel_uid"], seq=int(d["seq"]), kind=d["kind"], task_id=d["task_id"], request_id=d["request_id"], plan_sha256=d["plan_sha256"],
        plan_json=d.get("plan_json"), channel_json=d.get("channel_json"), message_id=d.get("message_id"), receipt_id=d.get("receipt_id"),
        status=d.get("status"), delivered=bool(d["delivered"]), returned_message=bool(d["returned_message"]), envelope_json=d.get("envelope_json"),
        envelope_digest=d.get("envelope_digest"), header_sha256=d.get("header_sha256"), payload_sha256=d.get("payload_sha256"),
        receipt_json=d.get("receipt_json"), receipt_sha256=d.get("receipt_sha256"), typed_kind=d.get("typed_kind"), typed_id=d.get("typed_id"),
        typed_copy_sha256=d.get("typed_copy_sha256"), raw_text=d.get("raw_text"), raw_text_sha256=d.get("raw_text_sha256"), call_json=d["call_json"],
        captured=captured, captured_overflow=int(d.get("captured_overflow", 0)), pool_before=pools(d["pool_before"]), pool=pools(d["pool"]),
        conflicts_added=tuple((tuple(c), r) for c, r in d["conflicts_added"]), forwards_added=tuple(tuple(f) for f in d["forwards_added"]),
        superseded_added=tuple(tuple(s) for s in d["superseded_added"]), transmitted_added=tuple(d["transmitted_added"]),
        recipients_added=tuple(tuple(r) for r in d["recipients_added"]), requests_added=tuple(d["requests_added"]), log_added=tuple(d["log_added"]),
        raised=d.get("raised"), created_at=d["created_at"], monotonic_ns=int(d["monotonic_ns"]), digest_only=bool(d.get("digest_only", False)))


def channel_events(auditor: TransferAuditor, uid: str) -> list[ChannelEvent]:
    return auditor.journal(uid).events()


def write_events(path: Path, events: Iterable[ChannelEvent]) -> Path:
    """The events as JSON lines (canonical JSON, one event per line)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(canonical_json(event_record(ev)) + "\n")
    return path


def read_events(path: Path) -> list[ChannelEvent]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(event_from_record(json.loads(line)))
    return out


def rebuild(events: Iterable[ChannelEvent], keyring: KeyRing, *, registry: Any = None) -> tuple[TransferAuditor, str]:
    """A fresh auditor fed ``events`` (one channel, in order, no live channel): its journal, store and view are those
    of the auditor that journaled them. Returns ``(auditor, channel_uid)``; the caller closes the auditor."""
    events = list(events)
    if not events:
        raise HarnessError("no events to rebuild a channel from")
    uids = {e.channel_uid for e in events}
    if len(uids) != 1:
        raise HarnessError(f"the events belong to {len(uids)} channels; a rebuild takes one")
    aud = new_auditor(keyring)
    for ev in events:
        aud.on_event(ev, channel=None, registry=registry)
    return aud, events[0].channel_uid


def write_record(directory: Path, *, auditor: TransferAuditor, uid: str, audit: OverseerAudit, profile: str, meta: Optional[dict] = None) -> Path:
    """One channel's transfer record: ``events.jsonl`` (the journal's events as issued), ``audit.json`` (the signed task
    audit, verified under the ``profile`` keyring when read back) and ``record.json`` (identifiers and ``meta``)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    events = channel_events(auditor, uid)
    write_events(directory / "events.jsonl", events)
    (directory / "audit.json").write_text(canonical_json(audit.model_dump(mode="json", exclude_none=True)) + "\n", encoding="utf-8")
    rec = {"format": RECORD_FORMAT, "channel_uid": uid, "task_id": audit.task_id, "request_id": audit.request_id, "keyring_profile": profile,
           "events": len(events), "audit_id": audit.audit_id, "audit_state": audit.state, "message_ids": list(audit.message_ids)}
    rec.update(meta or {})
    write_json(directory / "record.json", rec)
    return directory


@dataclass
class LoadedRecord:
    directory: Path
    record: dict
    events: list[ChannelEvent]
    audit: OverseerAudit
    keyring: KeyRing


def load_record(directory: Path) -> LoadedRecord:
    """Read a transfer record and verify its signed audit under the record's keyring profile (refused otherwise)."""
    directory = Path(directory)
    rec = read_json(directory / "record.json")
    if rec.get("format") != RECORD_FORMAT:
        raise HarnessError(f"{directory} is not a transfer record of format {RECORD_FORMAT}")
    keyring = keyring_for(rec["keyring_profile"])
    audit = OverseerAudit.model_validate(read_json(directory / "audit.json"))
    if not verify_audit(audit, keyring):
        raise HarnessError(f"the audit of {directory} does not verify under the {rec['keyring_profile']} keyring: the record was altered")
    events = read_events(directory / "events.jsonl")
    if not events or {e.channel_uid for e in events} != {rec["channel_uid"]} or audit.channel_uid != rec["channel_uid"]:
        raise HarnessError(f"the events of {directory} do not belong to the recorded channel")
    return LoadedRecord(directory=directory, record=rec, events=events, audit=audit, keyring=keyring)


# ============================================================================================ overseer agents (only from an exported pack)
def export_and_load_pack(out_dir: Path) -> tuple[Any, Any]:
    """Export the INSTALLED pack with the package's exporter into ``out_dir`` (a directory and a zip) and load the
    exported directory back with the loader (every file against the manifest, the pack digest against ``PACK_DIGESTS``).
    Returns ``(pack, export_result)``. A refusal raises (``ExportError``, ``PackError``): no agent can be built."""
    from epinoic_logic.overseer import load_pack
    from epinoic_logic.overseer.export import export_pack
    res = export_pack(Path(out_dir), zip_archive=True)
    pack = load_pack(res.directory)
    zpack = load_pack(res.zip_path)
    if zpack.identity != pack.identity:
        raise HarnessError("the exported zip and directory load to different identities")
    return pack, res


def load_exported_pack(path: Path, *, trusted: Iterable[Any] = ()) -> Any:
    """Load an exported pack (directory or zip) with every check of the loader; ``PackError`` when refused."""
    from epinoic_logic.overseer import load_pack
    return load_pack(Path(path), trusted=tuple(trusted))


def build_runner(pack: Any, provider: Any, *, agent_id: str, lens: str) -> Any:
    """One overseer agent: the package's runner, configured from a LOADED pack (``KnowledgePack``) and a provider. The
    harness passes no prompt text of its own: the runner's input is the pack's system text and the dossier."""
    from epinoic_logic.overseer import KnowledgePack, OverseerAgentRunner
    if not isinstance(pack, KnowledgePack):
        raise TypeError("an overseer agent is built only from a KnowledgePack loaded from an exported pack")
    return OverseerAgentRunner(pack, provider, agent_id=agent_id, lens=lens)


def dossier_of_user_text(user: str) -> dict:
    """The dossier inside the runner's user text (the data block, or bare JSON). Data only."""
    lines = user.split("\n")
    if lines and lines[0].startswith("<<<DATA") and lines[-1].startswith("<<<END"):
        return json.loads("\n".join(lines[1:-1]))
    return json.loads(user)


class ScriptedProvider:
    """A completion provider whose reply is computed from the dossier it receives: harness code reading the dossier as
    JSON data (a probe, never a model). ``reply(dossier)`` returns a verdict dict, raw text, or an exception to raise.
    Every call is recorded. No network."""

    name = "harness-probe"

    def __init__(self, reply: Callable[[dict], Any], *, name: Optional[str] = None) -> None:
        self.reply = reply
        if name:
            self.name = name
        self.calls: list[tuple[str, str, str]] = []

    def complete(self, system: str, user: str, *, prompt_version: str):
        import time as _time
        from epinoic_logic.translate.contracts import ProviderInfo
        from epinoic_logic.translate.providers import ProviderResponse
        t0 = _time.perf_counter()
        self.calls.append((system, user, prompt_version))
        out = self.reply(dossier_of_user_text(user))
        if isinstance(out, BaseException):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return ProviderResponse(raw_text=text, info=ProviderInfo(provider_name=self.name, prompt_version=prompt_version, temperature=0.0,
                                                                 latency_ms=(_time.perf_counter() - t0) * 1000.0))


def verdict_dict(d: dict, accusations: Iterable[dict] = (), engine_statements: Iterable[dict] = (), *, notes: str = "", **over: Any) -> dict:
    """A verdict whose header is COPIED from the dossier ``d`` (as the pack's Verdict format requires)."""
    v = {"contract": d["verdict_contract"], "pack": dict(d["pack"]), "verdict_id": f"v-{d['agent_id']}"[:128], "agent_id": d["agent_id"],
         "task_id": d["task"]["task_id"], "dossier_sha256": d["dossier_sha256"], "lens": d["lens"],
         "transfers_reviewed": [t["message_id"] for t in d["transfers"] if t["message_id"]], "accusations": list(accusations),
         "engine_statements": list(engine_statements), "notes": notes}
    v.update(over)
    return v


def accusation(aid: str, kind: str, evidence: list, *, severity: str = "error", statement: str = "Harness probe accusation.", **ids: Any) -> dict:
    out = {"accusation_id": aid, "kind": kind, "claimed_severity": severity, "evidence": evidence, "statement": statement}
    for name in ("message_ids", "receipt_ids", "claim_ids", "report_ids", "result_ids", "document_ids"):
        out[name] = list(ids.get(name, []))
    return out


def index_pointer(d: dict, kind: str, ident: str, *, report_id: Optional[str] = None) -> Optional[str]:
    """The dossier index's pointer for an identifier (a claim also by its report), or None."""
    for e in d.get("index", []):
        if e["type"] == kind and e["id"] == ident and (report_id is None or e.get("report_id") in (None, report_id)):
            return e["pointer"]
    return None


def transfer_of(d: dict, message_id: str) -> Optional[dict]:
    return next((t for t in d["transfers"] if t["message_id"] == message_id), None)


def finding_ids(f: Any) -> dict[str, set[str]]:
    """The identifiers an ``IntegrityFinding`` (or its JSON) names, by kind."""
    get = (lambda k: f.get(k)) if isinstance(f, dict) else (lambda k: getattr(f, k, None))
    results = set(get("related_result_ids") or [])
    if get("formal_result_id"):
        results.add(get("formal_result_id"))
    return {"message_ids": set(get("message_ids") or []), "claim_ids": set(get("claim_ids") or []), "report_ids": set(get("report_ids") or []),
            "document_ids": set(get("document_ids") or []), "result_ids": results}


def names_any(f: Any, ids: dict[str, Iterable[str]]) -> bool:
    """True when the finding names at least one of ``ids`` (by kind; receipt ids are not on findings)."""
    have = finding_ids(f)
    return any(set(ids.get(k) or ()) & have.get(k, set()) for k in ("message_ids", "claim_ids", "report_ids", "document_ids", "result_ids"))
