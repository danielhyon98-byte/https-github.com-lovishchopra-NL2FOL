"""No file of the repository holds a raw bidirectional control (round-9 clearance c2b, queued q215a; the harness owner's handoff 3).

The bidirectional embedding, override and isolate controls (U+202A to U+202E, U+2066 to U+2069) written raw in a source file reorder what a
reviewer reads against what the interpreter runs (Trojan Source). A test input writes each as its escape ("\\u202e") and a generated vector as
its JSON escape (``integration/tools/vectors.py``), so the values stay the same and every file reads as it runs. This guard runs in the default
suite over every text file of the repository's own trees (the harness owner's test covers the harness owner's files and is run by path).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: The trees the repository owns (a worktree, a cache, a virtual environment or a dependency is none of them).
TREES = ("src", "tests", "scripts", "docs", "integration", "overseer", "flash-router", "combinator")
SUFFIXES = frozenset({".py", ".md", ".json", ".txt", ".toml", ".cfg", ".ini", ".yml", ".yaml", ".js", ".mjs", ".ts", ".html", ".sh"})
SKIP_PARTS = frozenset({"__pycache__", ".hypothesis", ".git", ".worktrees", "node_modules", ".venv", "venv", ".pytest_cache", "build", "dist"})
_BIDI_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")


def _files() -> list[Path]:
    out: list[Path] = [p for p in ROOT.glob("*") if p.is_file() and p.suffix in SUFFIXES]
    for tree in TREES:
        base = ROOT / tree
        if base.is_dir():
            out += [p for p in base.rglob("*") if p.is_file() and p.suffix in SUFFIXES and not (set(p.relative_to(ROOT).parts) & SKIP_PARTS)]
    return sorted(out)


def test_no_file_of_the_repository_holds_a_raw_bidirectional_control():
    found = {}
    for p in _files():
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        lines = [i for i, line in enumerate(text.split("\n"), 1) if _BIDI_RE.search(line)]
        if lines:
            found[p.relative_to(ROOT).as_posix()] = lines[:10]
    assert not found, found


def test_the_guard_reads_a_raw_control_and_never_its_escape():
    assert _BIDI_RE.search("abc\u202edef") and _BIDI_RE.search("x\u2066y") and not _BIDI_RE.search(r"abc\u202edef")
