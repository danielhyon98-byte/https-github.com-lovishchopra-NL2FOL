"""Normalisation before any reading (rules N1 to N8 of the self-certification design, section 2).

:func:`fold` makes ONE pass over the code points of a text and returns the folded text, an index map from each folded
character to its original offset, and the unread runs (rule N8). Every step is a dict or frozenset lookup per code point;
``unicodedata`` is consulted one code point at a time and memoised. A token-level pass then folds look-alike letters of other
scripts inside Latin tokens (N4), digit look-alikes (N5) and letter-spaced runs (N6), each bounded per token.

* N1: invisible characters (format characters, variation selectors, fillers, controls) are dropped; a run of three or more is a
  hidden run (U2), except a ZWJ between two emoji and one variation selector after an emoji.
* N2: combining Latin small letters are read as their letters; every other combining mark is dropped (accents folded).
* N3: compatibility forms and letter-like symbols are read through the committed fold table (``fold_table.json``).
* N4: Cyrillic, Greek, Armenian, Cherokee and Lisu look-alikes are folded only inside a token that holds a Latin letter or
  consists only of look-alikes.
* N5: digit look-alikes inside a token of two or more letters, only when the result is a word of the lexicon.
* N6: a run of three or more single letters with one separator is joined when the joined word is a word of the lexicon; two
  regional indicators alone are a flag.
* N7: check marks, approval and score symbols, star runs and end-of-proof marks become reading tokens.
* N8: unread runs: letter-like (U1), hidden (U2); the script rule (U3) is the reader's.
"""
from __future__ import annotations

from typing import Optional

import functools
import json
import pathlib
import re
import unicodedata
from dataclasses import dataclass

__all__ = ["Folded", "fold", "visible_form", "TOKEN_WORDS", "fold_table", "letter_like"]

_HERE = pathlib.Path(__file__).resolve().parent

#: The reading tokens of rule N7, as the words the reader reads (none is an English or Spanish word).
TOKEN_WORDS = {
    "MARK+": "zzmarkpos", "MARK-": "zzmarkneg", "APPROVE+": "zzapprove", "SCORE-FULL": "zzscorefull", "RATING+": "zzrating",
    "END-OF-PROOF": "zzeop", "FLAG": "zzflag",
}


_TABLE: list = []


def fold_table() -> dict:
    """The committed fold table, loaded once per process (its shape is checked; a malformed table raises, so every gate fails
    closed): data, not a memo, so emptying the package's caches keeps it."""
    if not _TABLE:
        _TABLE.append(_load_table())
    return _TABLE[0]


def _load_table() -> dict:
    raw = json.loads((_HERE / "fold_table.json").read_text(encoding="utf-8"))
    for key in ("fold", "confusables", "symbols", "letter_like_blocks"):
        if key not in raw:
            raise ValueError(f"fold table lacks {key!r}")
    return {
        "fold": {int(k, 16): v for k, v in raw["fold"].items()},
        "combining": frozenset(int(k, 16) for k in raw.get("combining_letters", [])),
        "confusables": {chr(int(k, 16)): v for k, v in raw["confusables"].items()},
        "symbols": {int(k, 16): v for k, v in raw["symbols"].items()},
        "blocks": tuple((int(a, 16), int(b, 16)) for a, b in raw["letter_like_blocks"]),
    }


#: Code points dropped by N1 besides the format characters (category Cf).
_DROPPED = frozenset(
    [0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x17B4, 0x17B5, 0x180B, 0x180C, 0x180D, 0x180E, 0x180F]
    + list(range(0xFE00, 0xFE10)) + list(range(0xE0100, 0xE01F0)))
_ZWJ = 0x200D


def _emoji(cp: int) -> bool:
    return cp >= 0x1F000 or 0x2600 <= cp <= 0x27BF or 0x2B00 <= cp <= 0x2BFF or 0x2190 <= cp <= 0x21FF or 0x2300 <= cp <= 0x23FF


@functools.lru_cache(maxsize=8192)
def _category(ch: str) -> str:
    return unicodedata.category(ch)


@functools.lru_cache(maxsize=8192)
def _decomposed(ch: str) -> str:
    """NFKD of one code point with its combining marks dropped (memoised per code point)."""
    return "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))


#: (the fold table's letter-like blocks and the lowest code point of any of them, derived once per loaded table: a code point below it
#: is in none of them; data derived from the table, not a memo of any reading)
_BLOCKS_LOW: list = []


def letter_like(cp: int) -> bool:
    blocks = fold_table()["blocks"]
    if not _BLOCKS_LOW or _BLOCKS_LOW[0] is not blocks:
        _BLOCKS_LOW[:] = [blocks, min((a for a, _b in blocks), default=0x110000)]
    if cp < _BLOCKS_LOW[1]:
        return False  # (below every block: the same answer as the scan of the blocks, c3e stabilizer)
    return any(a <= cp <= b for a, b in blocks)


def _invisible(cp: int, cat: str) -> bool:
    if cp in (9, 10, 13):
        return False
    return cat == "Cf" or cp in _DROPPED or (cat == "Cc") or 0xE0000 <= cp <= 0xE007F


@dataclass(frozen=True)
class Folded:
    """The folded text, the original offset of each of its characters, and the unread runs (kind, start, end) in ORIGINAL
    offsets (letter-like and hidden; the script rule is the reader's)."""
    text: str
    origin: tuple[int, ...]
    unread: tuple[tuple[str, int, int], ...]

    def span(self, a: int, b: int) -> tuple[int, int]:
        """The original offsets of the folded span ``[a, b)``."""
        if not self.origin:
            return (0, 0)
        a = max(0, min(a, len(self.origin) - 1))
        b = max(a + 1, min(b, len(self.origin)))
        return (self.origin[a], self.origin[b - 1] + 1)


#: The Grade 1 Braille alphabet (dots 1-6; U+2800 + the dot bits): the cell of each Latin letter (attack round 7).
_BRAILLE_DOTS = {"a": (1,), "b": (1, 2), "c": (1, 4), "d": (1, 4, 5), "e": (1, 5), "f": (1, 2, 4), "g": (1, 2, 4, 5), "h": (1, 2, 5),
                 "i": (2, 4), "j": (2, 4, 5), "k": (1, 3), "l": (1, 2, 3), "m": (1, 3, 4), "n": (1, 3, 4, 5), "o": (1, 3, 5),
                 "p": (1, 2, 3, 4), "q": (1, 2, 3, 4, 5), "r": (1, 2, 3, 5), "s": (2, 3, 4), "t": (2, 3, 4, 5), "u": (1, 3, 6),
                 "v": (1, 2, 3, 6), "w": (2, 4, 5, 6), "x": (1, 3, 4, 6), "y": (1, 3, 4, 5, 6), "z": (1, 3, 5, 6)}
_BRAILLE = {0x2800 + sum(1 << (d - 1) for d in dots): letter for letter, dots in _BRAILLE_DOTS.items()}


_ASCII_RUN_RE = re.compile(r"[\x00-\x7f]+")


def _pass_one(text: str) -> tuple[list[str], list[int], list[tuple[str, int, int]]]:
    """Rules N1 to N3 and N7, one pass over the code points."""
    table = fold_table()
    fold, symbols, combining = table["fold"], table["symbols"], table["combining"]
    out: list[str] = []
    origin: list[int] = []
    unread: list[tuple[str, int, int]] = []
    hidden_start, hidden_n = -1, 0
    ll_start, ll_n = -1, 0
    n = len(text)
    i = 0
    prev_visible_cp = 0

    def emit(s: str, at: int) -> None:
        for c in s:
            out.append(c)
            origin.append(at)

    def close_hidden(end: int) -> None:
        nonlocal hidden_start, hidden_n
        if hidden_n >= 3:
            unread.append(("hidden", hidden_start, end))
        hidden_start, hidden_n = -1, 0

    def close_ll(end: int) -> None:
        nonlocal ll_start, ll_n
        if ll_n >= 3:
            unread.append(("letter-like", ll_start, end))
        ll_start, ll_n = -1, 0

    while i < n:
        ch = text[i]
        cp = ord(ch)
        if cp < 128:
            close_hidden(i)
            close_ll(i)
            # (a run of ASCII characters is emitted as written, each at its own offset, in one step: what the step per character did,
            # since closing the runs again at each later character of the run closes nothing; c3e stabilizer)
            m = _ASCII_RUN_RE.match(text, i)
            j = m.end()
            out.extend(text[i:j])
            origin.extend(range(i, j))
            prev_visible_cp = ord(text[j - 1])
            i = j
            continue
        cat = _category(ch)
        if _invisible(cp, cat):
            exempt = False
            if cp == _ZWJ and _emoji(prev_visible_cp) and i + 1 < n and _emoji(ord(text[i + 1])):
                exempt = True
            elif 0xFE00 <= cp <= 0xFE0F and _emoji(prev_visible_cp) and hidden_n == 0:
                exempt = True
            if not exempt:
                if hidden_n == 0:
                    hidden_start = i
                hidden_n += 1
            i += 1
            continue
        close_hidden(i)
        # regional indicators: a run of exactly two is a flag; three or more are letters (N6)
        if 0x1F1E6 <= cp <= 0x1F1FF:
            j = i
            while j < n and 0x1F1E6 <= ord(text[j]) <= 0x1F1FF:
                j += 1
            close_ll(i)
            if j - i == 2:
                emit(" " + TOKEN_WORDS["FLAG"] + " ", i)
            else:
                for k in range(i, j):
                    emit(fold.get(ord(text[k]), "?"), k)
            prev_visible_cp = cp
            i = j
            continue
        if 0x2800 <= cp <= 0x28FF:
            # Braille cells (attack round 7): a cell of the Grade 1 alphabet is read as its letter; any other cell is a letter-like
            # mark the reader cannot read, named unread with its run (rule unread-text)
            letter = _BRAILLE.get(cp)
            if letter is not None:
                close_ll(i)
                emit(letter, i)
            elif cp == 0x2800:
                close_ll(i)
                emit(" ", i)
            else:
                if ll_n == 0:
                    ll_start = i
                ll_n += 3  # (one unread cell is enough to name the run)
                emit(ch, i)
            prev_visible_cp = cp
            i += 1
            continue
        sym = symbols.get(cp)
        if sym is not None:
            close_ll(i)
            if sym == "STAR":
                j, stars = i, 0
                while j < n and (symbols.get(ord(text[j])) == "STAR" or 0xFE00 <= ord(text[j]) <= 0xFE0F or text[j] == " "):
                    stars += symbols.get(ord(text[j])) == "STAR"
                    j += 1
                if stars >= 3:
                    emit(" " + TOKEN_WORDS["RATING+"] + " ", i)
                i = j
                prev_visible_cp = cp
                continue
            emit(" " + TOKEN_WORDS[sym] + " ", i)
            prev_visible_cp = cp
            i += 1
            continue
        if cp in combining:
            close_ll(i)
            emit(fold[cp], i)
            i += 1
            continue
        if cat in ("Mn", "Me"):
            i += 1  # a combining mark other than a letter: dropped (N2)
            continue
        mapped = fold.get(cp)
        if mapped is not None:
            close_ll(i)
            emit(mapped, i)
            prev_visible_cp = cp
            i += 1
            continue
        if letter_like(cp):
            if ll_n == 0:
                ll_start = i
            ll_n += 1
            emit(ch, i)
            prev_visible_cp = cp
            i += 1
            continue
        close_ll(i)
        if cat.startswith("L") and not (0x0370 <= cp <= 0x03FF or 0x0400 <= cp <= 0x052F or 0x0530 <= cp <= 0x058F
                                         or 0x13A0 <= cp <= 0x13FF or 0xA4D0 <= cp <= 0xA4FF):
            dec = _decomposed(ch)
            emit(dec if dec and dec != ch and dec.isascii() else ch, i)
        elif cat.startswith("Z"):
            emit(" ", i)
        else:
            emit(ch, i)
        prev_visible_cp = cp
        i += 1
    close_hidden(n)
    close_ll(n)
    return out, origin, unread


#: An HTML character reference ("&#101;", "&#x65;", "&eacute;").
_ENTITY_RE = __import__("re").compile(r"&(?:#(\d{2,6})|#[xX]([0-9a-fA-F]{2,5})|([a-zA-Z]{2,10}));")
#: A word broken by markup or a break inside it: emphasis marks ("ver*if*ied", "ver_if_ied"), an inline tag ("ver<b>ified</b>"),
#: a hyphen character other than the ASCII one ("veri\u2010fied") or a hyphen at a line break ("veri-\nfied"). Linear.
#: (a run of up to four tags or comments counts as one break: "<b>Ver</b><i>ified</i>", "Ver<!-- -->ified", attack round 5)
_BROKEN_WORD_RE = __import__("re").compile(
    r"[^\W\d_]+(?:(?:-[ \t]*\n[ \t]*|[*_\u2010\u2011-]{1,3}|(?:</?[a-zA-Z][a-zA-Z0-9]{0,10}>|<!--[^<>]{0,40}?-->){1,4})[^\W\d_]+)+")
_BREAK_RE = __import__("re").compile(r"-[ \t]*\n[ \t]*|[*_\u2010\u2011-]{1,3}|(?:</?[a-zA-Z][a-zA-Z0-9]{0,10}>|<!--[^<>]{0,40}?-->){1,4}")


def _pass_joins(chars: list[str], origin: list[int], known) -> tuple[list[str], list[int]]:
    """Markup and breaks inside a word (attack round 3, the N-series): an HTML character reference is read as its character
    ("V&#101;rified"), and a word broken by emphasis marks, an inline tag, a non-ASCII hyphen or a hyphen at a line break is read
    joined when the joined letters are a word of the lexicon ("ver*if*ied", "ver<b>ified</b>", "veri\u2010fied", "veri-\nfied").
    A break whose joined letters are no word is kept ("well-\nknown", "x*y"). One pass each; offsets map to the original."""
    import html
    text = "".join(chars)
    if "&" in text and ";" in text:
        out_c: list[str] = []
        out_o: list[int] = []
        at = 0
        for m in _ENTITY_RE.finditer(text):
            try:
                ch = chr(int(m.group(1))) if m.group(1) else chr(int(m.group(2), 16)) if m.group(2) else html.unescape(m.group(0))
            except (ValueError, OverflowError):
                continue
            if len(ch) != 1 or not ch.isalpha():
                continue
            out_c.extend(chars[at:m.start()])
            out_o.extend(origin[at:m.start()])
            out_c.append(ch)
            out_o.append(origin[m.start()])
            at = m.end()
        if at:
            out_c.extend(chars[at:])
            out_o.extend(origin[at:])
            chars, origin = out_c, out_o
            text = "".join(chars)
    chars, origin = _pass_split_words(chars, origin, known)
    text = "".join(chars)
    if not any(c in text for c in "*_\u2010\u2011<-"):
        return chars, origin
    out_c, out_o = [], []
    at = 0
    for m in _BROKEN_WORD_RE.finditer(text):
        joined = _BREAK_RE.sub("", m.group(0))
        if len(joined) > 40 or not known(joined.lower()):
            continue
        parts = [x for x in _BREAK_RE.split(m.group(0)) if x]
        if all(known(x.lower()) for x in parts) and not _BREAK_RE.search(m.group(0)).group(0).startswith(("<", "*", "_")):
            continue  # a compound of two words ("cross-checked", "well-known"): read as written
        out_c.extend(chars[at:m.start()])
        out_o.extend(origin[at:m.start()])
        k = m.start()
        for b in _BREAK_RE.finditer(text, m.start(), m.end()):
            out_c.extend(chars[k:b.start()])
            out_o.extend(origin[k:b.start()])
            k = b.end()
        out_c.extend(chars[k:m.end()])
        out_o.extend(origin[k:m.end()])
        # the removed breaks keep the text's offsets readable: blanks after the word, so a following word is not glued to it
        pad = (m.end() - m.start()) - len(joined)
        out_c.extend(" " * pad)
        out_o.extend([origin[m.end() - 1]] * pad)
        at = m.end()
    if not at:
        return chars, origin
    out_c.extend(chars[at:])
    out_o.extend(origin[at:])
    return out_c, out_o


#: A letter run and the one blank, tab, line break or "hyphen and blank" after it (rule N6, attack round 7).
_RUN_RE = __import__("re").compile(r"[^\W\d_]{1,40}")
_SPLIT_SEPS = frozenset((" ", "\t", "\n", "- ", "-  ", "-\t"))
_FUNCTION_TAGS = frozenset(("C:prep", "C:det", "C:coordinator", "C:subordinator", "C:neg", "C:pron1", "C:pron2", "C:pron3", "C:aux",
                            "C:copula", "C:definite", "C:indefinite", "C:demonstrative", "C:anaph", "C:instr_prep", "C:by"))


def _pass_split_words(chars: list[str], origin: list[int], known) -> tuple[list[str], list[int]]:
    """A word broken by ONE blank inside it (rule N6, attack round 7): two adjacent letter runs separated by one blank (the fold
    has already read a no-break, thin or ideographic space as a blank), a tab, a line break, or a hyphen and a blank, are read
    joined when the joined letters are a word of an assessment family and at least one of the two runs is no word of the lexicon
    ("che cks", "Corre ctness", "Confirm ed", "VERI FIED", "veri\nfied", "ver- ified", "verifi cada", "Compro bado"). Two words of
    the lexicon ("in valid", "con firma" after a preposition) and a run that is a function word are read as written. One pass over
    the runs; the removed separator becomes a blank after the joined word, so offsets stay readable."""
    from .lexicon import tags as _tags
    text = "".join(chars)
    if len(text) > 400_000:
        return chars, origin
    runs = [(m.start(), m.end()) for m in _RUN_RE.finditer(text)]
    joins: list[tuple[int, int, int]] = []  # (end of the first run, start of the second, end of the second)
    k = 0
    while k + 1 < len(runs):
        a0, a1 = runs[k]
        b0, b1 = runs[k + 1]
        sep = text[a1:b0]
        if sep not in _SPLIT_SEPS or (a1 - a0) + (b1 - b0) < 5 or (a1 - a0) < 2 or (b1 - b0) < 2 or \
                (a0 > 0 and (text[a0 - 1].isalnum() or text[a0 - 1] in "'’")) or (b1 < len(text) and text[b1].isdigit()):
            k += 1
            continue
        A, B = text[a0:a1].lower(), text[b0:b1].lower()
        joined = A + B
        tj = _tags(joined)
        if not any(t.startswith("F:") for t in tj) or (known(A) and known(B)) or (_tags(A) & _FUNCTION_TAGS):
            k += 1
            continue
        joins.append((a1, b0, b1))
        k += 2
    if not joins:
        return chars, origin
    out_c: list[str] = []
    out_o: list[int] = []
    at = 0
    for a1, b0, b1 in joins:
        out_c.extend(chars[at:a1])
        out_o.extend(origin[at:a1])
        out_c.extend(chars[b0:b1])
        out_o.extend(origin[b0:b1])
        pad = b0 - a1
        out_c.extend(" " * pad)
        out_o.extend([origin[b1 - 1]] * pad)
        at = b1
    out_c.extend(chars[at:])
    out_o.extend(origin[at:])
    return out_c, out_o


def _is_letter(c: str) -> bool:
    return c.isalpha()


def _pass_tokens(chars: list[str], origin: list[int], known) -> tuple[list[str], list[int]]:
    """Rules N4 to N6 over the tokens of the folded text. ``known`` is the lexicon's word test."""
    conf = fold_table()["confusables"]
    n = len(chars)
    # N4 and N5 per token (maximal run of letters and digits)
    i = 0
    while i < n:
        if not (chars[i].isalnum()):
            i += 1
            continue
        j = i
        while j < n and (chars[j].isalnum() or (chars[j] == "'" and j + 1 < n and chars[j + 1].isalpha())):
            j += 1
        tok = chars[i:j]
        has_latin = any(c.isascii() and c.isalpha() for c in tok)
        if any(c in conf for c in tok):
            only_lookalike = all((c in conf) or not c.isalpha() for c in tok)
            if has_latin or only_lookalike:
                for k in range(i, j):
                    if chars[k] in conf:
                        chars[k] = conf[chars[k]]
                has_latin = True
        letters = sum(1 for c in tok if c.isalpha())
        # (a lower-case letter and two or more look-alike digits are a word too: "a11 g00d", attack round 7; a capital and digits,
        # "A11", "B12", is a name or a code)
        if has_latin and (letters >= 2 or (letters == 1 and j - i >= 3 and tok[0].islower())) and \
                any(c in "013457" for c in tok) and any(c.isdigit() for c in tok):
            for one in "il":
                cand = "".join({"0": "o", "3": "e", "4": "a", "5": "s", "7": "t", "1": one}.get(c, c) for c in chars[i:j])
                if cand.isalpha() and known(cand.lower()):
                    for k, c in zip(range(i, j), cand):
                        chars[k] = c
                    break
        i = j
    # N6: letter-spaced runs, each read once: the run is split greedily into the longest lexicon words (at most 20 letters
    # each); the letters of a part that is no word stay as they were
    text = "".join(chars)
    out_c: list[str] = []
    out_o: list[int] = []
    i = 0
    n = len(text)
    seps = " .-·_*/|•∙‧"

    def single(k: int) -> bool:
        # (a letter after a digit closes a number, "1920s", "4x": no letter of a spaced run)
        return text[k].isalpha() and (k == 0 or not text[k - 1].isalnum()) and (k + 1 >= n or not text[k + 1].isalnum())

    while i < n:
        c = text[i]
        if single(i):
            letters = [i]
            j = i + 1
            sep = None
            while j < n:
                k = j
                while k < n and text[k] == " " and k - j < 3:
                    k += 1
                core = ""
                if k < n and text[k] in seps and text[k] != " ":
                    core = text[k]
                    k += 1
                    while k < n and text[k] == " " and k - j < 7:
                        k += 1
                if k == j or k >= n:
                    break
                this = core or " "
                if sep is None:
                    sep = this
                if this != sep or not single(k):
                    break
                letters.append(k)
                j = k + 1
            if len(letters) >= 3:
                word = "".join(text[k] for k in letters).lower()
                pieces: list[tuple[int, int, bool]] = []
                gaps = [letters[t + 1] - letters[t] for t in range(len(letters) - 1)]
                # a run whose word gaps are wider than its letter gaps ("a l l   f i g u r e s   i n"): the wide gaps are the word
                # boundaries, and a short word between two of them ("i n", "o f") is read as written (attack round 3)
                narrow = min(gaps)
                bounds = [0] + [t + 1 for t, g in enumerate(gaps) if sep == " " and g > narrow] + [len(letters)]

                def greedy(m: int, end: int) -> None:
                    while m < end:
                        best = 0
                        for L in range(min(20, end - m), 2, -1):
                            if known(word[m:m + L]):
                                best = L
                                break
                        if best:
                            pieces.append((m, m + best, True))
                            m += best
                        else:
                            pieces.append((m, m + 1, False))
                            m += 1
                for ba, bb in zip(bounds, bounds[1:]):
                    if len(bounds) > 2 and (bb - ba <= 2 or known(word[ba:bb])):
                        pieces.append((ba, bb, True))
                    else:
                        greedy(ba, bb)
                if any(ok for _a, _b, ok in pieces):
                    last = letters[-1]
                    if len(pieces) == 1 and sep == "." and last + 1 < n and text[last + 1] == ".":
                        last += 1  # "Q.E.D.": the run's last stop is part of the letters, not a sentence end
                    elif sep == "." and pieces[-1][2] and last + 1 < n and text[last + 1] == ".":
                        # "a.m. V.E.R.I.F.I.E.D. answer": the run's last stop closes its last letter, not the sentence, when the
                        # words go on in lower case after it (attack round 3)
                        nx = last + 2
                        while nx < n and nx - last < 6 and text[nx] in " \t":
                            nx += 1
                        if nx < n and text[nx].islower():
                            last += 1
                    for n_p, (a, b, ok) in enumerate(pieces):
                        if ok:
                            for k in letters[a:b]:
                                out_c.append(text[k])
                                out_o.append(origin[k])
                            if len(pieces) > 1:
                                out_c.append(" ")
                                out_o.append(origin[letters[b - 1]])
                        else:
                            out_c.append(text[letters[a]])
                            out_o.append(origin[letters[a]])
                            if n_p + 1 < len(pieces) and pieces[n_p + 1][2] and ". " in text[letters[a]:letters[a + 1]]:
                                # "a.m. V.E.R.I.F.I.E.D.", "km/h. V.E.R.I.F.I.E.D.": the stop and blank before a word of the run
                                # close the letters before it (an abbreviation's stop, a sentence end), kept (attack round 3)
                                out_c.append(".")
                                out_o.append(origin[letters[a]])
                            out_c.append(" ")
                            out_o.append(origin[letters[a]])
                    i = last + 1
                    continue
                # no word: copy the whole run as written and move past it (each run is read once)
                last = letters[-1]
                for k in range(i, last + 1):
                    out_c.append(text[k])
                    out_o.append(origin[k])
                i = last + 1
                continue
        out_c.append(c)
        out_o.append(origin[i])
        i += 1
    return out_c, out_o


#: Other spellings of a mark (rule N7, attack round 4): an HTML character reference of a symbol ("&#10003;", "&#x2714;&#xFE0F;",
#: "&check;"), an emoji shortcode that chat and markdown front ends render as the symbol (":white_check_mark:"), a LaTeX macro that
#: KaTeX and MathJax render as one ("\checkmark", "\ding{51}"). Each is read as the symbol it renders.
_MARK_SPELLING_RE = __import__("re").compile(
    r"&#(\d{2,7});|&#[xX]([0-9a-fA-F]{2,6});|&(check|checkmark|cross|starf|bigstar|star);"
    r"|:(white_check_mark|heavy_check_mark|ballot_box_with_check|check_mark|check|heavy_check|green_circle|large_green_circle|"
    r"green_square|100|\+1|thumbsup|thumbs_up|ok_hand|star|star2|glowing_star|x|cross_mark|negative_squared_cross_mark|"
    r"red_circle|red_square):"
    r"|\\(checkmark|ding\{5[1-6]\}|cmark|xmark|tick|surd)(?![A-Za-z])")
_MARK_NAMES = {"check": "\u2713", "checkmark": "\u2713", "cross": "\u2717", "starf": "\u2605", "bigstar": "\u2605", "star": "\u2605",
               "white_check_mark": "\u2705", "heavy_check_mark": "\u2714", "ballot_box_with_check": "\u2611", "check_mark": "\u2714",
               "heavy_check": "\u2714", "green_circle": "\U0001F7E2", "large_green_circle": "\U0001F7E2",
               "green_square": "\U0001F7E9", "100": "\U0001F4AF", "+1": "\U0001F44D", "thumbsup": "\U0001F44D",
               "thumbs_up": "\U0001F44D", "ok_hand": "\U0001F44C", "star2": "\U0001F31F", "glowing_star": "\U0001F31F",
               "x": "\u274C", "cross_mark": "\u274C", "negative_squared_cross_mark": "\u274E", "red_circle": "\U0001F534",
               "red_square": "\U0001F7E5", "ding{51}": "\u2713", "ding{52}": "\u2714", "ding{53}": "\u2717",
               "ding{54}": "\u2718", "ding{55}": "\u2717", "ding{56}": "\u2718", "cmark": "\u2713", "xmark": "\u2717",
               "tick": "\u2713"}


def _mark_spellings(text: str) -> tuple[str, Optional[list[int]]]:
    """``text`` with every other spelling of a mark replaced by its symbol, and the original offset of each character (None when
    nothing was replaced). A character reference of a letter is left to :func:`_pass_joins`; one of an invisible character (a
    variation selector) is dropped. Linear: one regular-expression pass."""
    if not ("&" in text or ":" in text or "\\" in text):
        return text, None
    out: list[str] = []
    org: list[int] = []
    at = 0
    for m in _MARK_SPELLING_RE.finditer(text):
        if m.group(1) or m.group(2):
            try:
                ch = chr(int(m.group(1))) if m.group(1) else chr(int(m.group(2), 16))
            except (ValueError, OverflowError):
                continue
            cat = unicodedata.category(ch)
            if cat in ("Mn", "Cf") or 0xFE00 <= ord(ch) <= 0xFE0F:
                ch = ""
            elif not cat.startswith(("S", "P")) or ch in "&;:#<>\"'":
                continue
        elif m.group(3):
            ch = _MARK_NAMES.get(m.group(3), "")
        elif m.group(4):
            if m.group(4) == "surd":
                continue
            ch = _MARK_NAMES.get(m.group(4), "")
        else:
            if m.group(5) == "surd":
                continue
            ch = _MARK_NAMES.get(m.group(5), "")
        out.append(text[at:m.start()])
        org.extend(range(at, m.start()))
        out.append(ch)
        org.extend([m.start()] * len(ch))
        # (the rest of the spelling becomes blanks, so the offsets of what follows stay readable)
        pad = (m.end() - m.start()) - len(ch)
        out.append(" " * pad)
        org.extend([m.end() - 1] * pad)
        at = m.end()
    if not at:
        return text, None
    out.append(text[at:])
    org.extend(range(at, len(text)))
    return "".join(out), org


def fold(text: str, known=None) -> Folded:
    """The folded reading text of ``text`` (module docstring). ``known`` (a word test) defaults to the lexicon's."""
    if not isinstance(text, str) or not text:
        return Folded("", (), ())
    if known is None:
        from .lexicon import known_word as known
    src, pre = _mark_spellings(text)
    chars, origin, unread = _pass_one(src)
    chars, origin = _pass_joins(chars, origin, known)
    chars, origin = _pass_tokens(chars, origin, known)
    if pre is not None:
        origin = [pre[o] if 0 <= o < len(pre) else o for o in origin]
        unread = [(k, pre[a] if a < len(pre) else a, (pre[b - 1] + 1) if 0 < b <= len(pre) else b) for k, a, b in unread]
    return Folded("".join(chars), tuple(origin), tuple(unread) + _reordered_runs(text))


#: Bidirectional controls that make the displayed order differ from the stored one: the embeddings and overrides LRE, RLE, LRO,
#: RLO (U+202A, U+202B, U+202D, U+202E) and the isolates LRI, RLI, FSI (U+2066 to U+2068); PDF (U+202C) and PDI (U+2069) close them.
_BIDI_OPEN = frozenset((0x202A, 0x202B, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068))
_BIDI_CLOSE = frozenset((0x202C, 0x2069))
_BIDI_ANY_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")


def _reordered_runs(text: str) -> tuple[tuple[str, int, int], ...]:
    """Rule N8 (U2) for reordered text: letters or digits between a bidirectional embedding, override or isolate and its closing
    control (or the end of the line) are shown in an order the reader does not read ("\u202e.tcerroc si rewsna sihT" displays
    "This answer is correct."). Such a run is hidden text whatever it spells: never read as written, never delivered silently.
    One pass."""
    if not _BIDI_ANY_RE.search(text):
        return ()  # (the same test as a scan of every character for a control U+202A to U+202E or U+2066 to U+2069; c3e stabilizer)
    out: list[tuple[str, int, int]] = []
    start, depth, letters = -1, 0, False
    for i, c in enumerate(text):
        cp = ord(c)
        if cp in _BIDI_OPEN:
            if depth == 0:
                start, letters = i, False
            depth += 1
        elif depth and (cp in _BIDI_CLOSE or c == "\n"):
            depth = depth - 1 if cp in _BIDI_CLOSE else 0
            if depth == 0:
                if letters:
                    out.append(("hidden", start, i + 1))
                start = -1
        elif depth and c.isalnum():
            letters = True
    if depth and letters:
        out.append(("hidden", start, len(text)))
    return tuple(out)


def visible_form(text: str) -> str:
    """``text`` as the student sees it, for reading only: invisible characters removed, compatibility forms, look-alikes and
    letter-spaced runs folded (:func:`fold`), reading tokens shown as their symbols' names."""
    return fold(text).text
