"""The combinator agent's instruction pack: package data, pinned by digest.

The pack is two files (``pack/`` of this package):

* ``INSTRUCTIONS.md``: what the agent is told (its role and input; the closed transformation words; certainty never
  stronger than the weakest source; every figure, unit, mark, date and quotation kept exactly; no note,
  self-certification, decline or question carried back as a claim; every dropped claim listed with its reason; no
  contradiction merged or hidden; the exact output format and nothing else);
* ``output-format.json``: the same format as data (keys, closed values with what each records, the rules), which the
  translator's arena tooling prints for its combinator agents (``scripts/arena/list_claims.py --json``).

Its identity is ``(name, version, sha256)``: the SHA-256 of the canonical JSON of ``{"name", "version", "files":
{file name: SHA-256 of its bytes}}``. The service pins that digest in every combinator input
(``instruction_pack``) and every output carries it back (``instruction_pack_sha256``; another pack is ``KIT-CB-005``).
Any edit of either file changes the digest by itself; bump :data:`PACK_VERSION` with it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from typing import Any, Mapping

from . import NAME, __version__
from .jsonio import sha256_bytes, sha256_json

__all__ = ["PACK_NAME", "PACK_VERSION", "PACK_FILES", "TIER", "PackUnavailable", "Pack", "pack_sha256", "load_pack"]

PACK_NAME = "combinator-instructions"
PACK_VERSION = "1.0"
PACK_FILES: tuple[str, ...] = ("INSTRUCTIONS.md", "output-format.json")
#: The only tier the combinator runs on.
TIER = "cheapest"


class PackUnavailable(RuntimeError):
    """The package's instruction pack is missing or unreadable: an installation defect."""


def pack_sha256(name: str, version: str, files: Mapping[str, bytes]) -> str:
    return sha256_json({"name": name, "version": version, "files": {f: sha256_bytes(files[f]) for f in sorted(files)}})


@dataclass(frozen=True)
class Pack:
    name: str
    version: str
    files: Mapping[str, bytes] = field(repr=False)
    sha256: str

    @property
    def instructions(self) -> str:
        return self.files["INSTRUCTIONS.md"].decode("utf-8")

    @property
    def output_format(self) -> dict:
        return json.loads(self.files["output-format.json"].decode("utf-8"))

    def identity(self) -> dict:
        """The pack as the port names it (``PackRef``: name, version, sha256)."""
        return {"name": self.name, "version": self.version, "sha256": self.sha256}

    def manifest(self, contract_sha256: str) -> dict[str, Any]:
        """What the exporter writes beside the files: who made them, the pack's identity and every file's digest."""
        return {"schema": "epinoic.combinator.instruction-pack.v1", "combinator": {"name": NAME, "version": __version__},
                "instruction_pack": self.identity(), "files": {f: sha256_bytes(self.files[f]) for f in sorted(self.files)},
                "entry": "INSTRUCTIONS.md", "contract_sha256": contract_sha256, "tier": TIER}


def load_pack() -> Pack:
    """The instruction pack of this release (:class:`PackUnavailable` when a file is missing or unreadable)."""
    files: dict[str, bytes] = {}
    for name in PACK_FILES:
        try:
            files[name] = resources.files("epinoic_combinator").joinpath("pack", name).read_bytes()
        except OSError as exc:
            raise PackUnavailable(f"the instruction pack file {name} is missing ({type(exc).__name__})") from None
    try:
        files["INSTRUCTIONS.md"].decode("utf-8")
        json.loads(files["output-format.json"].decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise PackUnavailable("the instruction pack is not UTF-8 text and JSON") from None
    return Pack(name=PACK_NAME, version=PACK_VERSION, files=files, sha256=pack_sha256(PACK_NAME, PACK_VERSION, files))
