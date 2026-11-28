"""The arena's meaning label (meaning-check design 2.5.7, arena row; 3.4 to 3.6; stage 2a, interface (g)).

Every hub the arena builds labels each answer, synthesis and revision with the labeller this module resolves, and the arena
reports what the label did beside its other measures, never inside them.

**Which labeller.** ``resolve(labeller, round_dir)`` is called AT EACH CALL of ``run_arena.run_round`` and of every
``run_arena`` function other modules call (``relay_peer``, ``revision_feedback``, ``delivery_pass``, ``revision_pass``,
``_feedback_replay``, ``synthesis_record``): ``labeller`` is one of :data:`LABELLERS` (or a ``selfcert_label`` Labeller, or
an :class:`ArenaLabeller` already resolved); when none is given the environment variable :data:`LABELLER_ENV` is read at that
call, else :data:`DEFAULT_LABELLER`. An unknown name is refused (``ValueError``), never read as some other labeller.

* ``recorded`` serves the round's ``labels/`` directory by request key (:func:`load_labels`; the format is below) with the
  recording key of :data:`LABEL_KEY_ENV` (or the one given). An unrecorded key is ``unavailable`` (``not-recorded``): the
  answer is withheld and counted apart as "withheld unlabelled", never treated as clean. A ``labels/`` file that does not
  hold to the format, or whose label version or label digest is not the current package's, is not served and is named.
* ``faithful`` is the faithful fake (``selfcert_label.fakes.ReaderBackedLabeller``): it answers exactly as the rule reader
  reads, so every delivery decision is the reader's. The summary says, on its own line, that such a run is a wiring-parity run
  and NOT a label measurement (:data:`FAITHFUL_NOTE`).
* ``unconfigured`` is the production default (``selfcert_label.labellers.production_default_labeller``): every answer the
  reader passes is withheld as ``not-configured``.

**The labels/ format** (design 3.4). One JSON object per label request: ``labels/<task>.json`` (an answer),
``labels/<task>.synthesis.json`` (the combined answer of the task's group, written to the group's last task) and
``labels/<task>.rev<n>.json`` (revision ``n`` of an answer); an answer that renders more than one request (more than one chunk;
no recorded answer does) adds ``.c<k>`` for chunk ``k`` >= 1. Each holds exactly :data:`LABEL_FILE_KEYS`: ``request_key`` (the
rendered request's key, which binds the label version, the prompt, the schema, the answer's text and the recording key's
fingerprint), ``label_version`` and ``label_digest`` (the package's at recording), ``model_digest`` (the SHA-256 of the
configured model's identifier; never the identifier), ``raw_text`` (the reply exactly as returned) and ``provider_info`` with
:data:`PROVIDER_INFO_KEYS` only (``tier``, ``adapter``). ``list_labels.py`` renders the requests and ``bind_labels.py`` writes
these files from the raw replies.

**What a record carries** (:func:`label_member`): the label's state (``named``, ``none_named``, ``unavailable``, ``skipped``),
the unavailable kind, the number of places named and their families, and the claims named; never a word of the answer and
never the label's quote. ``none_named`` is never shown as a pass: it allows nothing by itself.

**The display rule** (interface (d), T18 for the arena): :func:`withhold_labelled_display` shows a claim named by INT-SELF-001
whose display would be a success (ENTAILED, CONSISTENT, SATISFIABLE) as NOT_ELIGIBLE with ``withheld_self_report`` True; a
non-success status is never changed or raised.

Nothing here calls a provider or opens a connection; no label output reaches the IR, the compiler or the engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from epinoic_logic import selfcert_label
from epinoic_logic.selfcert_label import labellers as _labellers
from epinoic_logic.selfcert_label.canaries import key_fingerprint

#: The environment variable read at each call when no labeller is given (one of :data:`LABELLERS`).
LABELLER_ENV = "EPINOIC_ARENA_LABELLER"
#: The environment variable that holds the RECORDING key of ``recorded`` and of list_labels.py (never a deployment secret).
LABEL_KEY_ENV = "EPINOIC_ARENA_LABEL_KEY"
LABELLERS = ("recorded", "faithful", "unconfigured")
DEFAULT_LABELLER = "recorded"
LABELS_DIR = "labels"
LABEL_FILE_KEYS = ("request_key", "label_version", "label_digest", "model_digest", "raw_text", "provider_info")
PROVIDER_INFO_KEYS = ("tier", "adapter")
#: The receipt codes the channel raises for the label (``channel.bus.SELFCERT_LABEL_CODES``).
LABEL_NAMED_CODE, LABEL_UNAVAILABLE_CODE = "INT-SELF-001", "INT-SELF-002"
LABEL_CODES = (LABEL_NAMED_CODE, LABEL_UNAVAILABLE_CODE)
#: The summary's line for a run with the faithful fake.
FAITHFUL_NOTE = ("Meaning label: labeller faithful (the faithful fake answers exactly as the rule reader reads). This is a wiring-parity "
                 "run, not a label measurement: it shows that wiring the label changed no delivery decision, and says nothing about how "
                 "well a deployed label reads.")
#: The display statuses that read as a success (``translate.outcome._SUCCESS_DISPLAY``).
SUCCESS_DISPLAY = frozenset({"ENTAILED", "CONSISTENT", "SATISFIABLE"})
#: The record groups the counts are kept by (a record's ``variant``: genuine answers, peer relays, syntheses, mutations).
COUNT_GROUPS = ("answers", "peer_relays", "syntheses", "mutations")

_HEX64 = re.compile(r"[0-9a-f]{64}")
_NAME_RE = re.compile(r"^(?P<task>[A-Za-z0-9][A-Za-z0-9_-]*)(?:\.(?P<kind>synthesis|rev(?P<rev>[1-9][0-9]{0,2})))?(?:\.c(?P<chunk>[1-9][0-9]{0,2}))?$")
#: The key a recorded labeller is built with when no recording key is given: it serves nothing (every label not-recorded).
_NO_KEY = b"arena: no recording key was given (nothing is served)"


def label_file_name(task: str, kind: str = "answer", rev: Optional[int] = None, chunk: int = 0) -> str:
    """``labels/`` file name of one request (module docstring): ``<task>.json``, ``<task>.synthesis.json``,
    ``<task>.rev<n>.json``, with ``.c<k>`` for chunk ``k`` >= 1."""
    stem = task + (".synthesis" if kind == "synthesis" else f".rev{int(rev)}" if kind == "revision" else "")
    if chunk:
        stem += f".c{int(chunk)}"
    if not _NAME_RE.match(stem):
        raise ValueError(f"no labels/ file name for task {task!r}")
    return stem + ".json"


def parse_label_file_name(name: str) -> Optional[dict]:
    """``{task, kind, rev, chunk}`` of a ``labels/`` file name, or None for a name outside the format."""
    if not name.endswith(".json"):
        return None
    m = _NAME_RE.match(name[:-5])
    if m is None:
        return None
    kind = "synthesis" if m["kind"] == "synthesis" else "revision" if m["rev"] else "answer"
    return {"task": m["task"], "kind": kind, "rev": int(m["rev"]) if m["rev"] else None, "chunk": int(m["chunk"] or 0)}


def label_file_problem(value: Any, *, version: str, digest: str) -> Optional[str]:
    """Why ``value`` is no ``labels/`` file of the current package (None when it is one)."""
    if not isinstance(value, dict):
        return "is not one JSON object"
    keys = set(value)
    if keys != set(LABEL_FILE_KEYS):
        missing, extra = sorted(set(LABEL_FILE_KEYS) - keys), sorted(keys - set(LABEL_FILE_KEYS))
        return "does not hold exactly the label file's fields" + (f" (missing {missing})" if missing else "") + (f" (not in the format {extra})" if extra else "")
    if not (isinstance(value["request_key"], str) and _HEX64.fullmatch(value["request_key"])):
        return "has no request key (64 hexadecimal digits)"
    if not (isinstance(value["model_digest"], str) and _HEX64.fullmatch(value["model_digest"])):
        return "has no model digest (the SHA-256 of the model's identifier, 64 hexadecimal digits)"
    if not isinstance(value["raw_text"], str):
        return "has no raw reply text"
    info = value["provider_info"]
    if not (isinstance(info, dict) and set(info) == set(PROVIDER_INFO_KEYS) and all(isinstance(info[k], str) and info[k] for k in PROVIDER_INFO_KEYS)):
        return "has provider_info other than its tier and adapter"
    if value["label_version"] != version:
        return f"is of label version {str(value['label_version'])[:40]!r}, not the current {version}"
    if value["label_digest"] != digest:
        return "is of another label digest than the current package's (prompt, schema, canaries, code or reader changed)"
    return None


@dataclass
class LabelSet:
    """The ``labels/`` directory of a round as read (:func:`load_labels`)."""
    present: bool = False
    files: list = field(default_factory=list)
    recordings: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)
    model_digest: Optional[str] = None
    label_version: str = ""
    label_digest: str = ""

    def summary(self) -> dict:
        return {"present": self.present, "files": len(self.files), "served": sum(1 for f in self.files if f["served"]),
                "refused": [f"{f['file']}: {f['why']}" for f in self.files if not f["served"]], "problems": list(self.problems),
                "model_digest": self.model_digest, "label_version": self.label_version, "label_digest": self.label_digest}


def load_labels(round_dir: Optional[Path]) -> LabelSet:
    """Read ``<round>/labels/*.json`` (module docstring). A file that does not hold to the format, is of another label version or
    digest, or repeats another file's request key with other content is not served and is named; labels of more than one model
    digest are none of them served (one recording run is of one model)."""
    return load_labels_dir(Path(round_dir) / LABELS_DIR if round_dir is not None else None)


def load_labels_dir(d: Optional[Path]) -> LabelSet:
    """:func:`load_labels` of a directory of label files given by its own path (a ``labels/`` directory)."""
    out = LabelSet(label_version=selfcert_label.LABEL_VERSION)
    if d is None or not Path(d).is_dir():
        return out
    d = Path(d)
    out.present = True
    out.label_digest = digest = selfcert_label.label_digest()
    by_key: dict[str, dict] = {}
    for p in sorted(d.glob("*.json")):
        entry: dict = {"file": f"{LABELS_DIR}/{p.name}", "served": False, "why": None, **(parse_label_file_name(p.name) or {})}
        out.files.append(entry)
        if "task" not in entry:
            entry["why"] = "its name is outside the labels/ format (<task>.json, <task>.synthesis.json, <task>.rev<n>.json)"
            continue
        try:
            value = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            entry["why"] = f"is not JSON ({type(exc).__name__})"
            continue
        why = label_file_problem(value, version=out.label_version, digest=digest)
        if why is not None:
            entry["why"] = why
            continue
        entry.update(request_key=value["request_key"], model_digest=value["model_digest"])
        held = by_key.get(value["request_key"])
        if held is not None and (held["value"]["raw_text"] != value["raw_text"] or held["value"]["model_digest"] != value["model_digest"]):
            entry["why"] = f"repeats the request key of {held['entry']['file']} with another reply"
            held["entry"]["served"], held["entry"]["why"] = False, f"its request key is repeated by {entry['file']} with another reply"
            held["conflict"] = True
            continue
        if held is None:
            by_key[value["request_key"]] = {"entry": entry, "value": value, "conflict": False}
        entry["served"] = True
    good = {k: v for k, v in by_key.items() if not v["conflict"]}
    models = sorted({v["value"]["model_digest"] for v in good.values()})
    if len(models) > 1:
        out.problems.append(f"the labels are of {len(models)} model digests: none is served (one recording run is of one model)")
        for v in good.values():
            v["entry"]["served"], v["entry"]["why"] = False, "the labels/ directory holds labels of more than one model digest"
        return out
    out.model_digest = models[0] if models else None
    for k, v in good.items():
        if v["entry"]["served"]:
            out.recordings[k] = {"raw_text": v["value"]["raw_text"], "model_digest": v["value"]["model_digest"],
                                 "label_version": v["value"]["label_version"]}
    return out


def recording_key(key: Any = None) -> Optional[bytes]:
    """The recording key: the one given, else :data:`LABEL_KEY_ENV` read now; None when there is none."""
    if key is None:
        key = os.environ.get(LABEL_KEY_ENV)
    if isinstance(key, str):
        key = key.encode("utf-8")
    if isinstance(key, (bytes, bytearray)) and key:
        return bytes(key)
    return None


@dataclass
class ArenaLabeller:
    """A resolved arena labeller: its name (:data:`LABELLERS`, or ``given``), where the name came from, the Labeller every hub of
    the run is given and, for ``recorded``, what the round's ``labels/`` directory served."""
    name: str
    labeller: Any
    source: str
    labels: Optional[LabelSet] = None
    key_fingerprint: Optional[str] = None
    problems: list = field(default_factory=list)

    def describe(self) -> dict:
        out = {"labeller": self.name, "source": self.source, "label_version": selfcert_label.LABEL_VERSION,
               "model_digest": getattr(self.labeller, "model_digest", "") or None, "problems": list(self.problems),
               "label_measurement": self.name == "recorded"}
        if self.name == "faithful":
            out["note"] = FAITHFUL_NOTE
        if self.labels is not None:
            out["labels"] = self.labels.summary()
            out["recording_key_fingerprint"] = self.key_fingerprint
        return out


def resolve(labeller: Any = None, round_dir: Optional[Path] = None, *, key: Any = None) -> ArenaLabeller:
    """The labeller of one call (module docstring). ``labeller`` None reads :data:`LABELLER_ENV` NOW (else
    :data:`DEFAULT_LABELLER`); ``round_dir`` is the round whose ``labels/`` a ``recorded`` labeller serves; ``key`` the recording
    key (else :data:`LABEL_KEY_ENV`, read now)."""
    if isinstance(labeller, ArenaLabeller):
        return labeller
    if isinstance(labeller, _labellers.Labeller):
        return ArenaLabeller("given", labeller, "argument")
    if labeller is None:
        env = (os.environ.get(LABELLER_ENV) or "").strip()
        name, source = (env, "environment") if env else (DEFAULT_LABELLER, "default")
    else:
        name, source = labeller, "argument"
    if not isinstance(name, str) or name.strip() not in LABELLERS:
        where = f"{LABELLER_ENV}={name!r}" if source == "environment" else repr(name)
        raise ValueError(f"no arena labeller {where}: one of {', '.join(LABELLERS)}")
    name = name.strip()
    if name == "faithful":
        from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller
        return ArenaLabeller(name, ReaderBackedLabeller(), source)
    if name == "unconfigured":
        return ArenaLabeller(name, _labellers.production_default_labeller(), source)
    labels = load_labels(round_dir)
    lab, problems = recorded_labeller(labels, key)
    k = recording_key(key)
    return ArenaLabeller(name, lab, source, labels=labels, key_fingerprint=key_fingerprint(k) if k else None, problems=problems)


def recorded_labeller(labels: LabelSet, key: Any = None) -> tuple[Any, list]:
    """The recorded labeller over ``labels`` with the recording ``key`` (else :data:`LABEL_KEY_ENV`, read now), and the problems:
    with no key nothing is served (every label ``not-recorded``), never a label rendered under some other key."""
    k = recording_key(key)
    problems = list(labels.problems)
    recordings = labels.recordings
    if k is None:
        if recordings:
            problems.append(f"no recording key was given ({LABEL_KEY_ENV} or --label-key): no recorded label is served")
        recordings = {}
    return _labellers.RecordedLabeller(recordings, key=k or _NO_KEY, model_digest=labels.model_digest or ""), problems


class installed:
    """``with installed(arena_labeller): ...``: the arena's labeller is also the default labeller for the block (put back after),
    so a release path of the run that is given no labeller (the overseer's delivery policy) reads the same labeller as the
    hubs, which are given it explicitly."""

    def __init__(self, arena_labeller: ArenaLabeller):
        self._ctx = _labellers.using_default_labeller(arena_labeller.labeller)

    def __enter__(self):
        return self._ctx.__enter__()

    def __exit__(self, *exc):
        return self._ctx.__exit__(*exc)


# ------------------------------------------------------------------------------------------------- what a record carries
def label_member(channel: Any, message_id: Optional[str], findings: Optional[list] = None) -> dict:
    """The label of one transmission, read from the channel's journal of label records (``TranslatorChannel.label_records``):
    ``state``, ``kind``, ``places`` (how many sentences were named), ``families`` and ``named_claims`` (from the INT-SELF-001
    findings of the receipt). Never a word of the answer or of the label. A transmission that made no label record (a refused
    request, a rejected reply) has state None."""
    entry = (getattr(channel, "label_records", None) or {}).get(message_id) if message_id else None
    record = None
    if entry is not None and isinstance(entry[0], str):
        try:
            record = json.loads(entry[0])
        except ValueError:
            record = None
    named = [f for f in (findings or []) if isinstance(f, dict) and f.get("code") == LABEL_NAMED_CODE]
    out: dict = {"state": None, "kind": None, "places": 0, "families": [], "named_claims": []}
    if isinstance(record, dict):
        spans = record.get("spans") if isinstance(record.get("spans"), list) else []
        out.update(state=record.get("state") if isinstance(record.get("state"), str) else None,
                   kind=record.get("kind") if isinstance(record.get("kind"), str) else None,
                   places=len({s.get("place") for s in spans if isinstance(s, dict)}),
                   families=sorted({s.get("category") for s in spans if isinstance(s, dict) and isinstance(s.get("category"), str)}))
        if out["state"] == "skipped":
            out["reason"] = record.get("reason") if isinstance(record.get("reason"), str) else None
    elif entry is not None:
        # a label record that could not be made (label code failed): the channel raised INT-SELF-002 label-failed
        out.update(state="unavailable", kind="label-failed")
    out["named_claims"] = sorted({c for f in named for c in (f.get("claim_ids") or [])})
    if out["state"] is None and any(isinstance(f, dict) and f.get("code") == LABEL_UNAVAILABLE_CODE for f in (findings or [])):
        out.update(state="unavailable", kind=out["kind"] or "label-failed")
    return out


def withhold_labelled_display(outcomes: list[dict], findings: list[dict]) -> list[dict]:
    """The arena's display rule (module docstring): each outcome record of a claim INT-SELF-001 names whose display is a success
    is shown NOT_ELIGIBLE with ``withheld_self_report`` True (its engine status kept apart, as recorded); every other outcome is
    returned as it is. A non-success status is never changed or raised."""
    named = {c for f in findings if isinstance(f, dict) and f.get("code") == LABEL_NAMED_CODE for c in (f.get("claim_ids") or [])}
    if not named:
        return outcomes
    out = []
    for o in outcomes:
        if o.get("claim_id") in named and o.get("display_status") in SUCCESS_DISPLAY:
            o = {**o, "display_status": "NOT_ELIGIBLE", "withheld_self_report": True, "label_withheld_display": o["display_status"]}
        out.append(o)
    return out


def _group(record: dict) -> str:
    v = record.get("variant")
    return {"genuine": "answers", "peer_relay": "peer_relays", "synthesis": "syntheses"}.get(v, "mutations")


def label_counts(records: list[dict], arena_labeller: ArenaLabeller) -> dict:
    """The label counts of a run (results.json ``selfcert_label``), by record group (:data:`COUNT_GROUPS`): records with a label
    record, named (with the sentences named), valid labels that named nothing (``none_named``: it allows nothing by itself and
    is never a pass), skipped (the rule reader already refuses), and unavailable by kind, every unavailable answer counted
    apart as "withheld unlabelled"; records with no label record (a refused request, a rejected reply) are counted too. The
    self-certification mutations credited by INT-SELF-001 (the label named the injected claim) are counted apart from those
    the rule reader's codes credit."""
    groups: dict[str, dict] = {}
    for g in COUNT_GROUPS:
        groups[g] = {"records": 0, "labelled": 0, "named": 0, "named_places": 0, "none_named": 0, "skipped": 0, "unavailable": 0,
                     "unavailable_by_kind": {}, "withheld_unlabelled": 0, "no_label_record": 0, "named_records": []}
    credited_label, credited_reader, self_cert = [], 0, 0
    for r in records:
        if "variant" not in r:
            continue
        g = groups[_group(r)]
        g["records"] += 1
        lab = r.get("selfcert_label")
        state = lab.get("state") if isinstance(lab, dict) else None
        if state is None:
            g["no_label_record"] += 1
        else:
            g["labelled"] += 1
            if state == "named":
                g["named"] += 1
                g["named_places"] += int(lab.get("places") or 0)
                g["named_records"].append({"file": r.get("file"), "variant": r.get("variant"), "places": int(lab.get("places") or 0),
                                           "families": list(lab.get("families") or []), "named_claims": list(lab.get("named_claims") or [])})
            elif state in ("none_named", "skipped"):
                g[state] += 1
            else:
                g["unavailable"] += 1
                g["withheld_unlabelled"] += 1
                kind = lab.get("kind") or "label-failed"
                g["unavailable_by_kind"][kind] = g["unavailable_by_kind"].get(kind, 0) + 1
        if r.get("variant") == "self_certification":
            self_cert += 1
            if any(f.get("code") == LABEL_NAMED_CODE for f in r.get("named_by") or []):
                credited_label.append(r.get("file"))
            elif r.get("named_by"):
                credited_reader += 1
    out = {**arena_labeller.describe(), "groups": groups,
           "self_certification_mutations": {"total": self_cert, "credited_by_label": len(credited_label), "credited_by_label_files": credited_label,
                                            "credited_by_reader_codes": credited_reader}}
    return out


def _kinds(d: dict) -> str:
    return ", ".join(f"{k} {n}" for k, n in sorted(d.items())) or "none"


def label_lines(counts: dict) -> list[str]:
    """The summary's label lines: one line of counts (with the labeller), the faithful note on a line of its own, and the
    problems of the labels/ directory. Counts only: never a word of an answer or of a label."""
    a = counts["groups"]["answers"]
    s = counts["groups"]["syntheses"]
    m = counts["groups"]["mutations"]
    sc = counts["self_certification_mutations"]
    line = (f"Meaning label (labeller {counts['labeller']}, label {counts['label_version']}): answers named by the label {a['named']} of {a['records']} "
            f"({a['named_places']} sentences), withheld unlabelled {a['withheld_unlabelled']} (unavailable by kind: {_kinds(a['unavailable_by_kind'])}), "
            f"skipped (the rule reader refuses) {a['skipped']}, a valid label naming nothing {a['none_named']} (allows nothing by itself), "
            f"no label record {a['no_label_record']}; syntheses named {s['named']}, withheld unlabelled {s['withheld_unlabelled']} of {s['records']}; "
            f"mutations named {m['named']}, withheld unlabelled {m['withheld_unlabelled']} of {m['records']}; injected self-certifications "
            f"credited by INT-SELF-001 {sc['credited_by_label']} of {sc['total']} (by the rule reader's codes {sc['credited_by_reader_codes']}).")
    out = [line]
    if counts.get("note"):
        out.append(counts["note"])
    labels = counts.get("labels")
    if labels is not None:
        out.append(f"Recorded labels: labels/ {'present' if labels['present'] else 'absent'}, {labels['served']} of {labels['files']} file(s) served"
                   + (f"; not served: {'; '.join(labels['refused'][:10])}" if labels["refused"] else ""))
    for p in counts.get("problems") or []:
        out.append(f"Recorded labels: {p}")
    return out


def named_files(counts: dict) -> list[str]:
    """``<file> [<variant>]`` of every record the label named (for the summary's list; places and families only)."""
    out = []
    for g in COUNT_GROUPS:
        for n in counts["groups"][g]["named_records"]:
            out.append(f"{n['file']} [{n['variant']}]: {n['places']} sentence(s), families {', '.join(n['families']) or 'none'}, claims "
                       f"{', '.join(n['named_claims']) or 'none'}")
    return out


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()
