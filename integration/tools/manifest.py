#!/usr/bin/env python3
"""Write or check the kit's manifests (playbook step 2: ``sha256sum -c --quiet integration/MANIFEST.sha256``).

* ``integration/sim/corpus/MANIFEST.sha256``: every file of the simulation corpus;
* ``integration/MANIFEST.sha256``: every file under ``integration/`` and ``src/epinoic_logic/integration/`` (the corpus
  manifest included), except the manifest itself and Python caches.

Lines are ``<sha256>  <path relative to the repository root>`` in path order, so ``sha256sum -c`` checks them from the
repository root. Generated last (integration/README.md, T9); ``tests/integration/test_manifest.py`` fails when either is stale.

Usage: ``python integration/tools/manifest.py [--check]``.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT_MANIFEST = ROOT / "integration" / "MANIFEST.sha256"
CORPUS = ROOT / "integration" / "sim" / "corpus"
CORPUS_MANIFEST = CORPUS / "MANIFEST.sha256"
TREES = (ROOT / "integration", ROOT / "src" / "epinoic_logic" / "integration")


def _files(base: Path, exclude: set[Path]) -> list[Path]:
    return sorted(p for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p not in exclude)


def _text(paths: list[Path]) -> str:
    return "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n" for p in paths)


def corpus_text() -> str:
    return _text(_files(CORPUS, {CORPUS_MANIFEST}))


def kit_text(corpus_manifest: str) -> str:
    paths: list[Path] = []
    for tree in TREES:
        paths += _files(tree, {KIT_MANIFEST})
    lines = []
    for p in sorted(set(paths)):
        data = corpus_manifest.encode("utf-8") if p == CORPUS_MANIFEST else p.read_bytes()
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n")
    if CORPUS_MANIFEST not in paths:
        lines.append(f"{hashlib.sha256(corpus_manifest.encode('utf-8')).hexdigest()}  {CORPUS_MANIFEST.relative_to(ROOT).as_posix()}\n")
        lines.sort(key=lambda line: line.split("  ", 1)[1])
    return "".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="write or check the kit manifests")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)
    corpus = corpus_text()
    kit = kit_text(corpus)
    stale = [p for p, t in ((CORPUS_MANIFEST, corpus), (KIT_MANIFEST, kit)) if not p.exists() or p.read_text(encoding="utf-8") != t]
    if args.check:
        for p in stale:
            print(f"stale: {p.relative_to(ROOT)}")
        return 1 if stale else 0
    CORPUS_MANIFEST.write_text(corpus, encoding="utf-8")
    KIT_MANIFEST.write_text(kit, encoding="utf-8")
    print(f"manifest: {kit.count(chr(10))} kit file(s), {corpus.count(chr(10))} corpus file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
