"""Build (or check) the reviewed exclusion list of the self-certification reader's one-edit variants (rule N9 of the
self-certification design, ``lexicon.json`` ``fuzzy_excluded``).

The lexicon generates, for the long closed-lexicon words, every variant with ONE deletion or ONE adjacent transposition that keeps
the first letter ("corect", "quotaton", "evry"), so a misspelt self-certification is still read. A variant that is itself a real
word must never be read as the lexicon word ("close" is no misspelling of "closed", "pints" none of "points"): every variant that
occurs as a word in the repository's own real text (recorded round answers and fixtures, branch data, the documentation) and in
any extra corpus directory named on the command line (the knowledge-base snapshot the arena uses) is EXCLUDED and listed, sorted,
in ``lexicon.json`` for review. The Python standard library's own sources (English documentation strings and comments, fixed per
Python version) are scanned too, as a large real-text corpus of ordinary English words ("noting" is no misspelling of "nothing").

Usage (repository root, the venv's Python)::

    python -I scripts/selfcert/build_fuzzy_exclusions.py [--corpus DIR ...]          # write the list
    python -I scripts/selfcert/build_fuzzy_exclusions.py --check [--corpus DIR ...]  # exit 1 if the committed list misses one
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEXICON = ROOT / "src" / "epinoic_logic" / "selfcert" / "lexicon.json"
#: The repository's own real text. The self-certification tests and the expectation tables are NOT corpus: they hold the
#: obfuscated self-certifications themselves.
DEFAULT_CORPUS = ["tests/fixtures", "tests/branches/data", "docs", "README.md", "REVIEW_FIXES_README.md", "src/epinoic_logic/branches",
                  "overseer/docs", "combinator", "flash-router/docs", "integration/corpus"]
_SKIP_PARTS = ("selfcert", "self_report_expectations", "__pycache__", "/.git/", "site-packages", "/test/", "/tests/")
_WORD_RE = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def corpus_words(paths: list[pathlib.Path]) -> set[str]:
    sys.path.insert(0, str(ROOT / "src"))
    from epinoic_logic.selfcert.lexicon import fold_word
    words: set[str] = set()
    for base in paths:
        files = [base] if base.is_file() else sorted(base.rglob("*")) if base.exists() else []
        for f in files:
            if not f.is_file() or any(p in str(f) for p in _SKIP_PARTS):
                continue
            if f.suffix.lower() not in (".md", ".json", ".txt", ".jsonl", ".py", ".csv", ".yaml", ".yml", ""):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for w in _WORD_RE.findall(text):
                words.add(fold_word(w))
    return words


def variants_in(words: set[str]) -> list[str]:
    sys.path.insert(0, str(ROOT / "src"))
    import epinoic_logic.selfcert.lexicon as lx
    raw = json.loads(LEXICON.read_text(encoding="utf-8"))
    saved = raw.get("fuzzy_excluded", [])
    raw["fuzzy_excluded"] = []
    lx.lexicon.cache_clear()
    lx.tags.cache_clear()
    orig = lx._HERE
    tmp = pathlib.Path(sys.argv[0]).resolve().parent / ".fuzzy_tmp"
    tmp.mkdir(exist_ok=True)
    (tmp / "lexicon.json").write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    try:
        lx._HERE = tmp
        lex = lx._load()
    finally:
        lx._HERE = orig
        (tmp / "lexicon.json").unlink()
        tmp.rmdir()
        raw["fuzzy_excluded"] = saved
    return sorted(v for v in lex.fuzzy if v in words)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--corpus", action="append", default=[], help="an extra corpus directory (the knowledge-base snapshot)")
    ap.add_argument("--no-stdlib", action="store_true", help="do not scan the Python standard library's sources")
    args = ap.parse_args(argv)
    paths = [ROOT / p for p in DEFAULT_CORPUS] + [pathlib.Path(p) for p in args.corpus]
    if not args.no_stdlib:
        import sysconfig
        paths.append(pathlib.Path(sysconfig.get_paths()["stdlib"]))
    found = variants_in(corpus_words(paths))
    raw = json.loads(LEXICON.read_text(encoding="utf-8"))
    committed = set(raw.get("fuzzy_excluded", []))
    if args.check:
        missing = sorted(set(found) - committed)
        if missing:
            print(f"fuzzy exclusions missing from lexicon.json: {missing[:40]}")
            return 1
        print(f"fuzzy exclusions: none missing ({len(committed)} committed)")
        return 0
    raw["fuzzy_excluded"] = sorted(committed | set(found))
    LEXICON.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(raw['fuzzy_excluded'])} exclusions to {LEXICON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
