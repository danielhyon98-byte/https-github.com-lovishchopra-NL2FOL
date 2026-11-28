#!/usr/bin/env python3
"""Render every meaning-label request of a round, for the recording pass (meaning-check design 3.4 and 3.5).

Usage: python list_labels.py <round> [--key KEY] [--out DIR] [--json]

The round's genuine traffic is replayed through the hub exactly as ``run_arena.py`` replays it (each group's plan, the peer
relays with the recorded relayed documents, the answers, then the combinator's synthesis of each group; and, when the round
holds ``feedback/`` and ``revisions/``, the revision pass, which delivers each recorded revision), with a labeller that RECORDS
the label request the hub asks for instead of answering it. Every request is rendered under the RECORDING key given with
``--key`` or in ``EPINOIC_ARENA_LABEL_KEY`` (never a deployment secret: a recording key makes the canaries reproducible, so the
replay with ``run_arena.py --labeller recorded`` renders the same requests and finds the recorded replies by request key). An
answer the rule reader already refuses asks for no label (its record is ``skipped``) and has no request.

For each request it writes, under ``--out`` (default ``<round>/label_requests/``):

- ``<name>.json``: the request's key (``request_key``), the label version and digest, the recording key's public fingerprint,
  the task, what was labelled (``answer``, ``synthesis`` or ``revision``), the labels/ file its reply is bound to
  (``label_file``), the system and user text files with their SHA-256 and the reply's token cap;
- ``<name>.user.txt``: the user text, exactly as rendered (the recording agent receives it with the system text, nothing else);
- ``prompt.md``: the system text (the package's frozen prompt), written once, since every request of a run carries it;

and ``index.json``, every request with its file names. ``<name>`` is the labels/ file stem (``arena_labels.label_file_name``):
``<task>``, ``<task>.synthesis``, ``<task>.rev<n>``, with ``.c<k>`` for a further chunk. A synthesis is named after the group's
last task, the task ``run_arena.py`` relays it after. A request the replay asks for twice (a relay or a forward of an answer
shares its delivery's request) is listed once.

The recording agents (deployed, cheapest tier; each in a fresh context with no tools) each read ``prompt.md`` and one
``<name>.user.txt`` and return the raw reply; ``bind_labels.py`` binds the replies to their requests by request key and writes
``<round>/labels/``. Nothing here calls a provider or opens a connection; no label is made.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arena_labels as AL  # noqa: E402
import run_arena as RA  # noqa: E402

from epinoic_logic import selfcert_label  # noqa: E402
from epinoic_logic.selfcert_label.canaries import key_fingerprint  # noqa: E402
from epinoic_logic.selfcert_label.labellers import CallingLabeller, CallFailure  # noqa: E402
from epinoic_logic.selfcert_label.record import unavailable_result  # noqa: E402

REQUESTS_DIR = "label_requests"
INDEX = "index.json"
PROMPT_FILE = "prompt.md"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


class RequestRecorder(CallingLabeller):
    """A labeller that records every request it is asked (its first attempt's rendered request of each chunk) under the context
    the replay sets (``context``: task and kind), and answers each ``unavailable`` (``not-recorded``): it makes no label."""

    def __init__(self, key: bytes):
        def caller(req, timeout):  # never reached: label_input below answers before any call
            raise CallFailure("not-recorded")
        super().__init__(caller, key=key, model_digest="")
        self.context: dict = {"task": None, "kind": "answer"}
        self.requests: dict[str, dict] = {}
        #: text -> (task, kind, rev) of the answers a pass that sets no context labels (the revision pass)
        self.by_text: dict[str, tuple] = {}

    def label_input(self, inp, *, deadline=None):
        ctx = dict(self.context)
        if ctx.get("task") is None:
            ctx = dict(zip(("task", "kind", "rev"), self.by_text.get(inp.scope.raw_text, (None, "unattributed", None))))
        for req in inp.requests:
            if req.request_key in self.requests:
                continue
            self.requests[req.request_key] = {"task": ctx.get("task"), "kind": ctx.get("kind") or "answer", "rev": ctx.get("rev"),
                                              "chunk": req.chunk, "writer": inp.scope.writer, "request": req}
        return unavailable_result(inp.input_key, "not-recorded", writer=inp.scope.writer, label_digest=selfcert_label.label_digest(),
                                  model_digest="")


def _replay(round_dir: Path, rec: RequestRecorder) -> list[str]:
    """The genuine pass of ``run_arena.run_round`` (requests, peer relays, answers, syntheses) with ``rec`` as the labeller and no
    translation (the label reads the text and the router's request only). Returns the problems met (never raised)."""
    problems: list[str] = []
    items = RA.load_items(round_dir / "specialists", include_pending=True)
    recorded_relays = RA.load_recorded_relays(round_dir, items)
    syntheses = RA.load_syntheses(round_dir / "syntheses")
    last_in_group = {RA.group_of(it): it["task_id"] for it in items}
    hub = RA.RouterHub(signing_key=RA.KEY, config=RA.CFG, selfcert_labeller=rec)
    channels: dict = {}
    delivered: dict = {}
    peer_docs: dict = {}
    for item in items:
        sp, task_id, group = item["_path"], item["task_id"], RA.group_of(item)
        try:
            if group not in channels:
                channels[group] = hub.open_task(RA.group_plan(items, group))
            ch = channels[group]
            texts = RA.supplied(item)
            pending = bool(item.get("_pending"))
            recorded_doc = recorded_relays[task_id]["payload"].get("original_response") if task_id in recorded_relays else None
            if not (pending and item.get("peer_of") and task_id not in recorded_relays):
                peer = next((it for it in items if it["task_id"] == item.get("peer_of")), None)
                rec.context = {"task": peer["task_id"] if peer else task_id, "kind": "answer"}  # a relay shares its delivery's request
                _r, ptext, _relayed = RA.relay_from_peer(ch, items, item, delivered, sp.name, recorded_doc)
                if ptext is not None:
                    peer_docs[task_id] = ptext
            if task_id in peer_docs:
                texts = [*texts, peer_docs[task_id]]
            if not pending and (not item.get("peer_of") or task_id in peer_docs):
                rec.context = {"task": task_id, "kind": "answer"}
                m, _req, rq = hub.dispatch(group, item["agent_id"], item["question"], texts)
                if m is None:
                    problems.append(f"{sp.name}: the request was {rq.status.value}: no answer to label")
                else:
                    reply, _rc = hub.receive(group, m.message_id, item["response_text"], agent_id=item["agent_id"], report_id=f"rep-{task_id}-0")
                    if reply is not None:
                        delivered[sp.stem] = reply
            if syntheses and task_id == last_in_group[group]:
                rec.context = {"task": task_id, "kind": "synthesis"}
                srec = RA.synthesis_record(ch, items, item, group, syntheses, delivered)
                if srec.get("error"):
                    problems.append(f"synthesis of group {group}: {srec['error']}")
        except Exception as exc:  # named, never allowed to end the listing
            problems.append(f"{sp.name}: {type(exc).__name__}: {exc}")
    rec.context = {"task": None, "kind": "answer"}
    rev_dir = round_dir / RA.REVISIONS_DIR
    if (round_dir / RA.FEEDBACK_DIR).is_dir() and rev_dir.is_dir():
        for p in sorted(rev_dir.glob("*.json")):
            try:
                rev = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(rev, dict) and isinstance(rev.get("response_text"), str):
                rec.by_text.setdefault(rev["response_text"], (rev.get("task_id") or p.stem, "revision", 1))
        for it in items:
            if not it.get("_pending"):
                rec.by_text.setdefault(it["response_text"], (it["task_id"], "answer", None))
        rp = RA.revision_pass(round_dir, items, recorded_relays, labeller=AL.ArenaLabeller("listing", rec, "argument"))
        if rp.get("skipped"):
            problems.append(f"revisions: {rp['skipped']}")
        problems += [f"revisions: {e.get('error')}" for e in rp.get("errors") or []]
    return problems


def label_requests(round_dir: Path, key: Any) -> dict:
    """Every label request of ``round_dir`` under the recording ``key`` (module docstring): ``{"requests": [...], "problems":
    [...], "label_version", "label_digest", "key_fingerprint"}``, each request with its name, task, kind, request key, system
    and user text. Pure over the round, the code and the key: the same round renders the same requests."""
    k = AL.recording_key(key)
    if k is None:
        raise ValueError(f"a recording key is required (--key or {AL.LABEL_KEY_ENV}); never a deployment secret")
    rec = RequestRecorder(k)
    with AL.installed(AL.ArenaLabeller("listing", rec, "argument")):
        problems = _replay(Path(round_dir), rec)
    out: list[dict] = []
    names: set[str] = set()
    for rk, r in rec.requests.items():
        req = r["request"]
        task = r["task"] or f"unattributed-{rk[:12]}"
        try:
            name = AL.label_file_name(task, r["kind"] if r["kind"] in ("synthesis", "revision") else "answer", r["rev"], req.chunk)[:-5]
        except ValueError:
            name = f"unattributed-{rk[:12]}"
        if name in names:  # two requests of one name (an answer labelled twice against different requests): keyed apart
            name = f"{name}-{rk[:12]}"
            problems.append(f"two requests are named {name.rsplit('-', 1)[0]}: the second is listed as {name} (bind it by its request key)")
        names.add(name)
        out.append({"name": name, "task_id": r["task"], "kind": r["kind"], "rev": r["rev"], "chunk": req.chunk, "writer": r["writer"],
                    "request_key": rk, "system_text": req.system_text, "user_text": req.user_text, "max_tokens": req.max_tokens,
                    "rendered": req})  # the rendered request itself (in memory only: never written)
    out.sort(key=lambda r: r["name"])
    return {"requests": out, "problems": problems, "label_version": selfcert_label.LABEL_VERSION, "label_digest": selfcert_label.label_digest(),
            "key_fingerprint": key_fingerprint(k)}


def write_requests(listing: dict, out_dir: Path, round_name: str) -> dict:
    """Write the request files and ``index.json`` (module docstring). Returns the index."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prompts: dict[str, str] = {}
    entries = []
    for r in listing["requests"]:
        sys_sha = _sha(r["system_text"])
        if sys_sha not in prompts:
            prompts[sys_sha] = PROMPT_FILE if not prompts else f"prompt-{sys_sha[:12]}.md"
            (out_dir / prompts[sys_sha]).write_text(r["system_text"], encoding="utf-8")
        user_file = f"{r['name']}.user.txt"
        (out_dir / user_file).write_text(r["user_text"], encoding="utf-8")
        entry = {"name": r["name"], "task_id": r["task_id"], "kind": r["kind"], "rev": r["rev"], "chunk": r["chunk"], "writer": r["writer"],
                 "request_key": r["request_key"], "label_file": f"{AL.LABELS_DIR}/{r['name']}.json", "label_version": listing["label_version"],
                 "label_digest": listing["label_digest"], "key_fingerprint": listing["key_fingerprint"], "system_text_file": prompts[sys_sha],
                 "system_text_sha256": sys_sha, "user_text_file": user_file, "user_text_sha256": _sha(r["user_text"]), "max_tokens": r["max_tokens"]}
        (out_dir / f"{r['name']}.json").write_text(json.dumps(entry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        entries.append(entry)
    counts: dict[str, int] = {}
    for e in entries:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    index = {"round": round_name, "label_version": listing["label_version"], "label_digest": listing["label_digest"],
             "key_fingerprint": listing["key_fingerprint"], "counts": counts, "problems": listing["problems"], "requests": entries}
    (out_dir / INDEX).write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return index


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render every meaning-label request of a round under a recording key (label_requests/).")
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("--key", default=None, help=f"the recording key (default {AL.LABEL_KEY_ENV}); never a deployment secret")
    ap.add_argument("--out", type=Path, default=None, help=f"where to write the requests (default <round>/{REQUESTS_DIR})")
    ap.add_argument("--json", action="store_true", help="print the index as JSON")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    if not (rd / "specialists").is_dir():
        print(f"{rd} has no specialists/ directory: nothing to list", file=sys.stderr)
        return 2
    try:
        listing = label_requests(rd, args.key)
    except ValueError as exc:
        print(f"list_labels.py: nothing written: {exc}", file=sys.stderr)
        return 2
    index = write_requests(listing, (args.out or rd / REQUESTS_DIR).resolve(), rd.name)
    if args.json:
        print(json.dumps(index, indent=2, ensure_ascii=False))
    else:
        print(f"{len(index['requests'])} label request(s) of {rd.name} ({', '.join(f'{k} {n}' for k, n in sorted(index['counts'].items())) or 'none'}), "
              f"label {index['label_version']}, recording key {index['key_fingerprint']}: {args.out or rd / REQUESTS_DIR}")
        for p in index["problems"]:
            print(f"problem: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
