"""Export the combinator agent's instructions: ``python -m epinoic_combinator.export --out <dir>``.

Writes into ``<dir>`` (created when missing; only these three files are written, nothing else is touched: each is written
through a new file renamed onto its name, so an entry already there, a symbolic link to a file elsewhere included, is
replaced and never written through):

* ``INSTRUCTIONS.md``: the agent's instructions, the text a workflow or a provider gives the combinator agent;
* ``output-format.json``: the exact output format as data (the translator's ``scripts/arena/list_claims.py`` prints it
  as ``synthesis_format`` for its combinator agents);
* ``MANIFEST.json``: this release, the pack's identity (name, version, SHA-256), the SHA-256 of every file, the digest
  of the published contract the runner validates against, and the tier.

Prints the manifest as one line of JSON. Exit status 0; 2 with one line on standard error when ``<dir>`` cannot be
written or the package's own pack or contract copy is unreadable (never a traceback). :func:`read_export` reads such a
directory back and refuses one whose files no longer match its manifest.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

from .contract import ContractUnavailable, load_contract
from .jsonio import sha256_bytes
from .pack import PACK_FILES, PackUnavailable, load_pack, pack_sha256

__all__ = ["MANIFEST_NAME", "ExportError", "export", "read_export", "main"]

MANIFEST_NAME = "MANIFEST.json"


class ExportError(RuntimeError):
    """The export cannot be written, or an exported directory does not match its manifest."""


def export(out: Path) -> dict:
    """Write the pack and its manifest into ``out``; returns the manifest."""
    pack = load_pack()
    manifest = pack.manifest(load_contract().sha256)
    out = Path(out)
    if out.exists() and not out.is_dir():
        raise ExportError(f"{out} exists and is not a directory")
    try:
        out.mkdir(parents=True, exist_ok=True)
        for name in PACK_FILES:
            _write_in(out, name, pack.files[name])
        _write_in(out, MANIFEST_NAME, (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    except OSError as exc:
        raise ExportError(f"cannot write the export into {out} ({type(exc).__name__})") from None
    return manifest


def _write_in(directory: Path, name: str, data: bytes) -> None:
    """Write ``data`` as ``directory/name`` through a new file renamed onto the name: an entry already there (a symbolic
    link to a file outside the directory included) is replaced, never written through, so nothing outside the directory
    is touched (integration gate 1)."""
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=f".{name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp, directory / name)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def read_export(directory: Path) -> tuple[dict, dict[str, bytes]]:
    """The manifest and the files of an exported pack, after checking every file against the manifest and the pack's
    digest against its files (:class:`ExportError` otherwise)."""
    directory = Path(directory)
    try:
        manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
        files = {name: (directory / name).read_bytes() for name in PACK_FILES}
    except (OSError, ValueError) as exc:
        raise ExportError(f"{directory} holds no readable exported pack ({type(exc).__name__})") from None
    if not isinstance(manifest, dict):  # valid JSON that is no object is no manifest (integration gate 1)
        raise ExportError(f"the manifest of {directory} is not a JSON object")
    if manifest.get("files") != {name: sha256_bytes(data) for name, data in files.items()}:
        raise ExportError(f"the files of {directory} are not the ones its manifest lists")
    pack = manifest.get("instruction_pack") or {}
    if not isinstance(pack, dict):
        raise ExportError(f"the instruction pack of the manifest of {directory} is not a JSON object")
    if pack.get("sha256") != pack_sha256(str(pack.get("name")), str(pack.get("version")), files):
        raise ExportError(f"the instruction pack digest of {directory} is not the digest of its files")
    return manifest, files


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m epinoic_combinator.export", description="write the combinator agent's instructions")
    ap.add_argument("--out", required=True, type=Path, help="the directory to write INSTRUCTIONS.md, output-format.json and MANIFEST.json into")
    args = ap.parse_args(argv)
    try:
        manifest = export(args.out)
    except (ExportError, PackUnavailable, ContractUnavailable) as exc:
        print(f"epinoic_combinator.export: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, sort_keys=True, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
