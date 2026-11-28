#!/usr/bin/env python3
"""Bind recorded meaning-label replies to the requests they answer, and write the round's ``labels/`` (meaning-check design 3.4).

Usage: python bind_labels.py <round> --replies <dir> (--model-digest HEX | --model-id ID) --tier TIER --adapter ADAPTER
                             [--requests <dir>] [--force]

``list_labels.py`` renders every label request of a round under a recording key and writes ``<round>/label_requests/``
(``index.json``: each request's name, request key, label version and label digest). The recording agents (deployed, cheapest
tier) each return one raw reply. This tool binds each reply to its request BY REQUEST KEY, as ``bind_translations.py`` binds a
translation to the claim text it was produced for, and writes ``<round>/labels/<name>.json`` in the round format
(``arena_labels.LABEL_FILE_KEYS``: ``request_key``, ``label_version``, ``label_digest``, ``model_digest``, ``raw_text`` and
``provider_info`` with ``tier`` and ``adapter`` only), which ``run_arena.py --labeller recorded`` serves.

A reply is a JSON object ``{"request_key": ..., "raw_text": ...}`` (the reply exactly as returned; optionally with the
``label_version`` and ``label_digest`` of the request it answered) in ``<replies>/*.json``, or the raw reply text in
``<replies>/<name>.txt`` named after its request (``<name>`` as list_labels.py names it). The model is recorded only as the
SHA-256 of its configured identifier (``--model-id`` is hashed at once and never written; ``--model-digest`` gives the digest).

Refused, with exit status 2 and NOTHING written:

- a listing (``index.json``) or a reply of another label version or label digest than the current package's: the prompt, the
  schema, the canaries, the package's code or the reader changed since the requests were rendered, so a reply to them is no
  label of the current package (render the requests again and record again);
- a reply whose request key the listing does not hold, a reply file that cannot be read, and two replies to one request that
  differ;
- a labels/ file already written with another reply or model for the same request, unless ``--force`` replaces it.

Nothing here calls a provider or opens a connection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))
import arena_labels as AL  # noqa: E402
from list_labels import INDEX, REQUESTS_DIR  # noqa: E402

from epinoic_logic import selfcert_label  # noqa: E402

_HEX64 = re.compile(r"[0-9a-f]{64}")


class BindingError(Exception):
    """A listing that cannot be read: nothing is written."""


def read_index(requests_dir: Path) -> dict:
    p = requests_dir / INDEX
    try:
        index = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BindingError(f"{p} is not a list_labels.py index ({type(exc).__name__})") from None
    if not isinstance(index, dict) or not isinstance(index.get("requests"), list):
        raise BindingError(f"{p} is not a list_labels.py index (an object with a requests list)")
    return index


def read_replies(replies_dir: Path, index: dict) -> tuple[list[dict], list[str]]:
    """Every reply of ``replies_dir`` as ``{"file", "request_key", "raw_text", "label_version"?, "label_digest"?}``, and the
    files that cannot be read as replies (each named)."""
    by_name = {r.get("name"): r.get("request_key") for r in index["requests"] if isinstance(r, dict)}
    replies, refused = [], []
    for p in sorted(replies_dir.iterdir()) if replies_dir.is_dir() else []:
        if p.suffix == ".json":
            try:
                v = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                refused.append(f"{p.name}: not JSON ({type(exc).__name__})")
                continue
            if not (isinstance(v, dict) and isinstance(v.get("request_key"), str) and isinstance(v.get("raw_text"), str)):
                refused.append(f"{p.name}: not a reply (an object with request_key and raw_text)")
                continue
            replies.append({"file": p.name, **{k: v[k] for k in ("request_key", "raw_text", "label_version", "label_digest") if k in v}})
        elif p.suffix == ".txt":
            key = by_name.get(p.stem)
            if key is None:
                refused.append(f"{p.name}: no request of the listing is named {p.stem}")
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, ValueError) as exc:
                refused.append(f"{p.name}: cannot be read ({type(exc).__name__})")
                continue
            replies.append({"file": p.name, "request_key": key, "raw_text": text})
    return replies, refused


def bind(round_dir: Path, index: dict, replies: list[dict], *, model_digest: str, tier: str, adapter: str, force: bool = False) -> dict:
    """What binding ``replies`` to the requests of ``index`` does (module docstring): the labels/ files to write (``files``: name
    -> content), and every refusal and conflict. Nothing is written."""
    version, digest = selfcert_label.LABEL_VERSION, selfcert_label.label_digest()
    out: dict = {"files": {}, "refused": [], "conflicts": [], "kept": [], "unanswered": []}
    if index.get("label_version") != version or index.get("label_digest") != digest:
        what = (f"label version {str(index.get('label_version'))[:40]!r}" if index.get("label_version") != version else
                "another label digest")
        out["refused"].append(f"the requests were rendered for {what}, not the current package's ({version}, its label digest): "
                              "render them again with list_labels.py and record again")
        return out
    requests = {r["request_key"]: r for r in index["requests"] if isinstance(r, dict) and isinstance(r.get("request_key"), str)}
    for r in requests.values():
        if r.get("label_version") != version or r.get("label_digest") != digest:
            out["refused"].append(f"request {r.get('name')}: rendered for another label version or digest than the current package's")
    seen: dict[str, dict] = {}
    for rep in replies:
        if "label_version" in rep and rep["label_version"] != version:
            out["refused"].append(f"{rep['file']}: a reply of label version {str(rep['label_version'])[:40]!r}, not the current {version}")
            continue
        if "label_digest" in rep and rep["label_digest"] != digest:
            out["refused"].append(f"{rep['file']}: a reply of another label digest than the current package's")
            continue
        req = requests.get(rep["request_key"])
        if req is None:
            out["refused"].append(f"{rep['file']}: its request key is no request of the listing")
            continue
        held = seen.get(rep["request_key"])
        if held is not None:
            if held["raw_text"] != rep["raw_text"]:
                out["refused"].append(f"{rep['file']}: a second reply to the request of {held['file']} that differs from it")
            continue
        seen[rep["request_key"]] = rep
        content = {"request_key": rep["request_key"], "label_version": version, "label_digest": digest, "model_digest": model_digest,
                   "raw_text": rep["raw_text"], "provider_info": {"tier": tier, "adapter": adapter}}
        name = req.get("name") or f"unattributed-{rep['request_key'][:12]}"
        path = round_dir / AL.LABELS_DIR / f"{name}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = None
            if existing == content:
                out["kept"].append(name)
                continue
            out["conflicts"].append(f"{AL.LABELS_DIR}/{name}.json already holds another reply or model for this request")
            if not force:
                continue
        out["files"][name] = content
    out["unanswered"] = sorted(r.get("name") for k, r in requests.items() if k not in seen)
    return out


def write(round_dir: Path, files: dict[str, dict]) -> None:
    d = round_dir / AL.LABELS_DIR
    d.mkdir(exist_ok=True)
    for name, content in files.items():
        (d / f"{name}.json").write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Bind recorded meaning-label replies to their requests by request key and write <round>/labels/.")
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("--replies", type=Path, required=True, help="the directory of raw replies (<name>.txt, or JSON objects with request_key and raw_text)")
    ap.add_argument("--requests", type=Path, default=None, help=f"the list_labels.py output (default <round>/{REQUESTS_DIR})")
    model = ap.add_mutually_exclusive_group(required=True)
    model.add_argument("--model-digest", help="the SHA-256 of the configured model's identifier (64 hexadecimal digits)")
    model.add_argument("--model-id", help="the configured model's identifier: hashed at once, never written")
    ap.add_argument("--tier", required=True, help="the model tier the replies were recorded on")
    ap.add_argument("--adapter", required=True, help="the adapter the recording ran through")
    ap.add_argument("--force", action="store_true", help="replace a labels/ file that holds another reply or model for the same request")
    args = ap.parse_args(argv)
    rd = args.round_dir.resolve()
    digest = args.model_digest if args.model_digest is not None else selfcert_label.model_digest(args.model_id)
    if not (isinstance(digest, str) and _HEX64.fullmatch(digest)):
        print("nothing written: --model-digest is not 64 hexadecimal digits")
        return 2
    if not args.tier.strip() or not args.adapter.strip():
        print("nothing written: --tier and --adapter are required")
        return 2
    try:
        index = read_index((args.requests or rd / REQUESTS_DIR).resolve())
    except BindingError as exc:
        print(f"nothing written: {exc}")
        return 2
    replies, unreadable = read_replies(args.replies.resolve(), index)
    result = bind(rd, index, replies, model_digest=digest, tier=args.tier.strip(), adapter=args.adapter.strip(), force=args.force)
    refused = unreadable + [r for r in result["refused"] if r]
    for line in refused:
        print(f"refused: {line}")
    for line in result["conflicts"]:
        print(f"conflict: {line}")
    if refused:
        print(f"nothing written: {len(refused)} reply file(s) or request(s) refused")
        return 2
    if result["conflicts"] and not args.force:
        print(f"nothing written: {len(result['conflicts'])} labels/ file(s) hold another reply (pass --force to replace them)")
        return 2
    write(rd, result["files"])
    print(f"{len(result['files'])} label(s) written to {rd / AL.LABELS_DIR}, {len(result['kept'])} already bound; requests with no reply: "
          f"{len(result['unanswered'])}" + (f" ({', '.join(result['unanswered'][:20])})" if result["unanswered"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
