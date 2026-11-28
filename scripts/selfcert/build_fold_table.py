"""Build (or check) the self-certification reader's character fold table (rules N2 to N4 and N7 of the self-certification
design; ``src/epinoic_logic/selfcert/fold_table.json``).

The table maps single code points to the ASCII letters (or the reading token) they are read as, so the reader reads
"🆅🅴🆁🅸🅵🅸🅴🅳", "ᴠᴇʀɪꜰɪᴇᴅ", "ᵛᵉʳⁱᶠⁱᵉᵈ", "𝐕𝐞𝐫𝐢𝐟𝐢𝐞𝐝" and "Ｃｈｅｃｋｅｄ" as the words they spell. It is built ONCE from
``unicodedata`` and the explicit blocks below, committed, and reviewed; its digest is part of
``epinoic_logic.selfcert.rules_digest()``, so a Python upgrade with another Unicode version cannot silently change the
reading: ``--check`` names any drift between the committed table and the one this interpreter would build.

Usage (repository root, the venv's Python)::

    python -I scripts/selfcert/build_fold_table.py           # write the table
    python -I scripts/selfcert/build_fold_table.py --check   # exit 1 and name the drift if the committed table differs
"""
from __future__ import annotations

import argparse
import json
import re
import pathlib
import string
import sys
import unicodedata

OUT = pathlib.Path(__file__).resolve().parents[2] / "src" / "epinoic_logic" / "selfcert" / "fold_table.json"

#: Blocks whose characters are folded through NFKC / NFKD (rule N3, and N2 for the precomposed accented letters).
FOLD_BLOCKS = [
    (0x00A0, 0x024F),   # Latin-1 Supplement, Latin Extended-A and -B
    (0x0250, 0x02FF),   # IPA Extensions, Spacing Modifier Letters (by name only, below)
    (0x1D00, 0x1DBF),   # Phonetic Extensions and Supplement
    (0x1E00, 0x1EFF),   # Latin Extended Additional
    (0x2000, 0x206F),   # General Punctuation (spaces, hyphens, primes)
    (0x2070, 0x209F),   # Superscripts and Subscripts
    (0x2100, 0x214F),   # Letterlike Symbols
    (0x2150, 0x218F),   # Number Forms (roman numerals)
    (0x2460, 0x24FF),   # Enclosed Alphanumerics
    (0x2C60, 0x2C7F),   # Latin Extended-C
    (0xA720, 0xA7FF),   # Latin Extended-D
    (0xAB30, 0xAB6F),   # Latin Extended-E
    (0xFB00, 0xFB06),   # Latin ligatures
    (0xFE50, 0xFE6F),   # Small Form Variants
    (0xFF00, 0xFFEF),   # Halfwidth and Fullwidth Forms
    (0x1D400, 0x1D7FF),  # Mathematical Alphanumeric Symbols
    (0x1F100, 0x1F1FF),  # Enclosed Alphanumeric Supplement
]

#: Letter-like blocks (rule U1): a run of three or more code points of these blocks that the table does not map is unread.
LETTER_LIKE_BLOCKS = [
    (0x2460, 0x24FF), (0x1F100, 0x1F1FF), (0x1D400, 0x1D7FF), (0x2100, 0x214F), (0x1D00, 0x1DBF), (0x02B0, 0x02FF),
    (0xFF00, 0xFFEF), (0xFE50, 0xFE6F), (0xA720, 0xA7FF), (0xA4D0, 0xA4FF), (0x13A0, 0x13FF), (0xAB70, 0xABBF),
]

#: Explicit punctuation folds NFKC leaves (a ratio sign or a modifier colon used as a label colon, typographic apostrophes and
#: dashes, which the reader reads as their ASCII forms).
EXPLICIT = {
    0x2236: ":", 0xA789: ":", 0x02D0: ":", 0x02F8: ":", 0xFE13: ":", 0xFE55: ":", 0xFF1A: ":",
    0x2019: "'", 0x2018: "'", 0x02BC: "'", 0x2032: "'",
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2212: "-", 0x00AD: "",
    0x00DF: "ss", 0x00E6: "ae", 0x00C6: "AE", 0x0153: "oe", 0x0152: "OE", 0x00F8: "o", 0x00D8: "O", 0x0142: "l", 0x0141: "L",
    0x0111: "d", 0x0110: "D", 0x0131: "i", 0x0237: "j", 0x017F: "s", 0x0251: "a", 0x0261: "g", 0x0269: "i", 0x2113: "l",
}

#: Look-alike letters of other scripts (rule N4), applied only inside a token that holds a Latin letter or consists only of
#: look-alikes: Cyrillic, Greek, Armenian, Cherokee and Lisu capitals that copy Latin ones.
CONFUSABLES = {
    # Cyrillic
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q",
    "ԝ": "w", "һ": "h", "ӏ": "l", "ғ": "f", "ɡ": "g", "ⅰ": "i", "ү": "y", "в": "b", "к": "k", "м": "m", "н": "h", "т": "t", "ѵ": "v",
    "Ѵ": "V", "Ԍ": "G",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "У": "Y",
    "І": "I", "Ј": "J", "Ѕ": "S", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W", "Һ": "H", "Ү": "Y", "Ӏ": "I",
    # Greek
    "α": "a", "ο": "o", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ϲ": "c", "ϳ": "j",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T",
    "Υ": "Y", "Χ": "X", "Ϲ": "C", "Ϳ": "J", "Ϝ": "F", "γ": "y", "η": "n",
    # Armenian
    "օ": "o", "ս": "u", "հ": "h", "ո": "n", "ց": "g", "զ": "q", "Տ": "S", "Օ": "O", "Լ": "L", "Ս": "U",
    # Cherokee capitals that copy Latin ones
    "Ꭺ": "A", "Ᏼ": "B", "Ꮯ": "C", "Ꭰ": "D", "Ꭼ": "E", "Ꮐ": "G", "Ꮋ": "H", "Ꭻ": "J", "Ꮶ": "K", "Ꮮ": "L", "Ꮇ": "M",
    "Ꮲ": "P", "Ꮪ": "S", "Ꮤ": "T", "Ꮩ": "V", "Ꮃ": "W", "Ꮓ": "Z", "Ꭵ": "i", "Ꮢ": "R", "Ꭲ": "T",
    # Lisu capitals that copy Latin ones
    "ꓮ": "A", "ꓐ": "B", "ꓚ": "C", "ꓓ": "D", "ꓰ": "E", "ꓝ": "F", "ꓖ": "G", "ꓧ": "H", "ꓲ": "I", "ꓙ": "J", "ꓗ": "K",
    "ꓡ": "L", "ꓟ": "M", "ꓠ": "N", "ꓳ": "O", "ꓑ": "P", "ꓣ": "R", "ꓢ": "S", "ꓔ": "T", "ꓴ": "U", "ꓦ": "V", "ꓪ": "W",
    "ꓫ": "X", "ꓬ": "Y", "ꓜ": "Z",
}

#: Marks and symbols read as tokens (rule N7). ✓ and the rest are marks; √ is never a mark (a square root).
SYMBOLS = {
    "✓": "MARK+", "✔": "MARK+", "☑": "MARK+", "✅": "MARK+", "🗸": "MARK+", "✗": "MARK-", "✘": "MARK-", "☒": "MARK-",
    "❌": "MARK-", "❎": "MARK-", "👍": "APPROVE+", "🆗": "APPROVE+", "👌": "APPROVE+", "💯": "SCORE-FULL", "★": "STAR",
    "⭐": "STAR", "🌟": "STAR", "∎": "END-OF-PROOF",
    # colour status marks (attack round 4: "Status: 🟢" is a status shown as green, as "Status: green" and "Status: ✅" are)
    "🟢": "MARK+", "🟩": "MARK+", "🔴": "MARK-", "🟥": "MARK-",
}



def _named_marks() -> dict[str, str]:
    """Every check mark and ballot cross the Unicode character database names (rule N7 by class, not by a list of code points):
    a name holding CHECK MARK or a ballot box WITH (BOLD) CHECK is a positive mark, a BALLOT X, a ballot box WITH (SCRIPT) X or a
    CROSS MARK a negative one. ("CHECKER" boards and the like are other words.)"""
    out: dict[str, str] = {}
    # (the Symbols for Legacy Computing block holds an INVERSE CHECK MARK, U+1FBB1: attack round 5)
    for cp in list(range(0x2000, 0x2C00)) + list(range(0x1F000, 0x1FC00)):
        name = unicodedata.name(chr(cp), "")
        if not name or name.startswith("NOT "):
            continue  # (APL's NOT CHECK MARK is an operator)
        if "CHECK MARK" in name or re.search(r"BALLOT BOX WITH (BOLD )?CHECK", name):
            out[chr(cp)] = "MARK+"
        elif "BALLOT X" in name or "BALLOT SCRIPT X" in name or re.search(r"BALLOT BOX WITH (BOLD |SCRIPT )*X", name) or \
                name.endswith("CROSS MARK"):
            out[chr(cp)] = "MARK-"
    return out


SYMBOLS = {**_named_marks(), **SYMBOLS}

ASCII_OK = set(string.ascii_letters + string.digits + " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~")


def _named(ch: str) -> str | None:
    """A letter folded by its Unicode name: small capitals, modifier and subscript letters, and the 'LATIN SMALL LETTER x WITH
    ...' letters whose decomposition NFKD leaves."""
    name = unicodedata.name(ch, "")
    for prefix in ("LATIN LETTER SMALL CAPITAL ", "MODIFIER LETTER SMALL CAPITAL ", "MODIFIER LETTER SMALL ", "MODIFIER LETTER CAPITAL ",
                   "LATIN SUBSCRIPT SMALL LETTER ", "LATIN SMALL LETTER ", "LATIN CAPITAL LETTER ", "SUPERSCRIPT LATIN SMALL LETTER ",
                   "COMBINING LATIN SMALL LETTER "):
        if name.startswith(prefix):
            rest = name[len(prefix):]
            letter = rest.split(" ")[0]
            if len(letter) == 1 and letter.isalpha() and letter.isascii():
                upper = prefix.startswith("LATIN CAPITAL") or prefix == "MODIFIER LETTER CAPITAL "
                return letter.upper() if upper else letter.lower()
    return None


def _fold_one(cp: int) -> str | None:
    ch = chr(cp)
    if cp in EXPLICIT:
        return EXPLICIT[cp]
    if 0x1F150 <= cp <= 0x1F169:  # negative circled capitals
        return chr(ord("A") + cp - 0x1F150)
    if 0x1F170 <= cp <= 0x1F189:  # negative squared capitals
        return chr(ord("A") + cp - 0x1F170)
    if 0x249C <= cp <= 0x24B5:  # parenthesised small letters (NFKC would give "(a)")
        return chr(ord("a") + cp - 0x249C)
    if 0x1F1E6 <= cp <= 0x1F1FF:  # regional indicators (a lone pair is a flag: the reader's rule N6)
        return chr(ord("A") + cp - 0x1F1E6)
    if ch in SYMBOLS:
        return None
    cat = unicodedata.category(ch)
    if cat.startswith("Z") and cp != 0x20:
        return " "
    nf = unicodedata.normalize("NFKC", ch)
    nf = "".join(c for c in unicodedata.normalize("NFKD", nf) if not unicodedata.combining(c))
    if nf and nf != ch and all(c in ASCII_OK for c in nf) and len(nf) <= 4:
        if 0x0250 <= cp <= 0x02FF and not (len(nf) == 1 and nf.isalpha()):
            return None
        return nf
    named = _named(ch)
    if named is not None and cat.startswith("L"):
        return named
    return None


def build() -> dict:
    fold: dict[str, str] = {}
    for a, b in FOLD_BLOCKS:
        for cp in range(a, b + 1):
            out = _fold_one(cp)
            if out is not None and out != chr(cp):
                fold[f"{cp:04X}"] = out
    for cp, out in EXPLICIT.items():  # the explicit folds, wherever their block is
        fold[f"{cp:04X}"] = out
    for cp in range(0x0363, 0x0370):  # combining Latin small letters a e i o u c d h m r t v x (rule N2)
        fold[f"{cp:04X}"] = "aeioucdhmrtvx"[cp - 0x0363]
    for cp in range(0x1DD3, 0x1DF5):
        n = _named(chr(cp))
        if n:
            fold[f"{cp:04X}"] = n
    return {
        "rules": "selfcert-5",
        "unicode": unicodedata.unidata_version,
        "fold": dict(sorted(fold.items(), key=lambda kv: int(kv[0], 16))),
        "combining_letters": sorted([f"{cp:04X}" for cp in list(range(0x0363, 0x0370)) + list(range(0x1DD3, 0x1DF5))
                                     if f"{cp:04X}" in fold]),
        "confusables": {f"{ord(k):04X}": v for k, v in sorted(CONFUSABLES.items(), key=lambda kv: ord(kv[0]))},
        "symbols": {f"{ord(k):04X}": v for k, v in sorted(SYMBOLS.items(), key=lambda kv: ord(kv[0]))},
        "letter_like_blocks": [[f"{a:04X}", f"{b:04X}"] for a, b in LETTER_LIKE_BLOCKS],
    }


def _dump(table: dict) -> str:
    return json.dumps(table, ensure_ascii=True, indent=0, sort_keys=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="compare with the committed table; exit 1 on drift")
    args = ap.parse_args(argv)
    table = build()
    text = _dump(table)
    if args.check:
        if not OUT.exists():
            print(f"missing: {OUT}")
            return 1
        committed = json.loads(OUT.read_text(encoding="utf-8"))
        if committed == table:
            print("fold table: no drift")
            return 0
        for key in ("rules", "unicode", "fold", "combining_letters", "confusables", "symbols", "letter_like_blocks"):
            a, b = committed.get(key), table.get(key)
            if a != b:
                if isinstance(a, dict) and isinstance(b, dict):
                    diff = sorted(set(a.items()) ^ set(b.items()))[:20]
                    print(f"drift in {key}: {diff}")
                else:
                    print(f"drift in {key}: committed {a!r} != built {b!r}")
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT} ({len(table['fold'])} folds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
