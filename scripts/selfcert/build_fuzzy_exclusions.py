"""Build (or check) the misspelling exemptions of the self-certification reader (rule N9, ``lexicon.json`` ``fuzzy_excluded``).

The lexicon reads, for the long family and part words, every variant with ONE deletion or ONE adjacent transposition that keeps
the first letter ("corect", "psased", "signd", "reviewe"), so a misspelt self-certification reads as the word it misspells. A
variant that is itself a REAL WORD must never be read as the lexicon word ("close" is no misspelling of "closed", "pints" none
of "points"): those variants, and only those, are exempt.

What counts as a real word is the committed, cited word source ``scripts/selfcert/real_words.txt`` (each entry looked up in a
named dictionary; its header cites the dictionaries and carries their notices). The exemption list is a pure function of two
committed inputs, that word source and the rest of ``lexicon.json``:

    fuzzy_excluded = sorted(variant for variant in candidates(lexicon without exemptions) if variant in word source)

No other text is scanned (no repository corpus, no standard library, no site-packages or dist-packages): a misspelling found in
some corpus is a misspelling, never a word. ``tests/selfcert/test_c3c_fuzzy_and_labels.py`` checks that the committed list
equals this builder's output and that every entry is in the word source.

Usage (repository root, the venv's Python)::

    python -I scripts/selfcert/build_fuzzy_exclusions.py            # write the list into lexicon.json
    python -I scripts/selfcert/build_fuzzy_exclusions.py --check    # exit 1 if the committed list differs from the build
    python -I scripts/selfcert/build_fuzzy_exclusions.py --vet DICT [DICT ...]
        # REVIEW AID, never part of the build: print the candidates that are words of the given dictionary files (one word per
        # line) and are missing from the word source, for a reviewed addition to real_words.txt with its source named
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEXICON = ROOT / "src" / "epinoic_logic" / "selfcert" / "lexicon.json"
WORD_SOURCE = pathlib.Path(__file__).resolve().parent / "real_words.txt"


def _lexicon_module():
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    import epinoic_logic.selfcert.lexicon as lx
    return lx


def word_source(path: pathlib.Path = WORD_SOURCE) -> dict[str, str]:
    """The word source: case-folded word -> its cited source tag. Comment lines start with ``#``; a malformed line raises."""
    lx = _lexicon_module()
    out: dict[str, str] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or parts[1] not in ("EN", "ES") or lx.fold_word(parts[0]) != parts[0] or not parts[0].isalpha():
            raise ValueError(f"{path.name}:{n}: expected '<folded word> EN|ES', got {line!r}")
        out[parts[0]] = parts[1]
    return out


def candidates(raw: dict) -> set[str]:
    """Every rule-N9 variant of the lexicon data ``raw`` read with NO exemption."""
    lx = _lexicon_module()
    data = dict(raw)
    data["fuzzy_excluded"] = []
    return lx.fuzzy_candidates(lx.build(data))


def build(raw: dict, words: dict[str, str]) -> list[str]:
    """The exemption list: the candidates that are words of the word source, sorted."""
    return sorted(v for v in candidates(raw) if v in words)


def _dictionary(paths: list[str]) -> set[str]:
    lx = _lexicon_module()
    out: set[str] = set()
    for p in paths:
        for line in pathlib.Path(p).read_text(encoding="utf-8", errors="replace").splitlines():
            w = line.strip()
            if w and "'" not in w:
                out.add(lx.fold_word(w))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if lexicon.json's list differs from the build")
    ap.add_argument("--vet", nargs="+", metavar="DICT", help="review aid: candidates in these dictionary files missing from the source")
    args = ap.parse_args(argv)
    raw = json.loads(LEXICON.read_text(encoding="utf-8"))
    words = word_source()
    if args.vet:
        missing = sorted((candidates(raw) & _dictionary(args.vet)) - set(words))
        print("\n".join(missing) if missing else "no candidate of these dictionaries is missing from the word source")
        return 0
    built = build(raw, words)
    committed = raw.get("fuzzy_excluded", [])
    if args.check:
        if committed != built:
            extra, missing = sorted(set(committed) - set(built)), sorted(set(built) - set(committed))
            print(f"fuzzy_excluded differs from the build: not in the build {extra[:40]}, missing {missing[:40]}")
            return 1
        print(f"fuzzy_excluded: equal to the build ({len(built)} entries)")
        return 0
    raw["fuzzy_excluded"] = built
    LEXICON.write_text(json.dumps(raw, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(built)} exclusions to {LEXICON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
