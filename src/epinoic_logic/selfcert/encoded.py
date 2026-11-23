"""Encoded spellings of a check label (rule N10 of the self-certification reader, c3c).

A label's value, or a status line or bracket of its own, can spell a check status in an ENCODING instead of in letters: reversed
("Status: deifirev"), shifted (ROT13 "IREVSVRQ", any Caesar shift, Atbash), Base64 ("VkVSSUZJRUQ="), Base32, hexadecimal, binary or
decimal character codes, percent-encoding, \\u escapes, or Morse ("...- . .-. .. ..-. .. . -.."). Such a value is DECODED and the
decoding is read as the label's value: when "Status: <decoding>" reads as a self-certification, the encoded value is one (a hit
G4 STATUS on the value, the same reading the plain spelling gets on every branch and path). Nothing is executed: every decoder is
a fixed table or a standard codec over at most :data:`_MAX_VALUE` characters, so the reading is linear in the text.

Positions read (the label or status positions):

* a label line whose KEY names an assessment ("Status:", "Verdict:", "Verification =", "Z3 result:", "QA:", "Estado:"): every
  decoder;
* a line holding one value alone (a status line of its own) and a bracket closing a sentence ("... in 1919 (deifirev)."): the
  letter transforms (reversal, Caesar shifts, Atbash), Base64, Base32, percent-encoding, escapes and Morse. Binary, hexadecimal and
  decimal codes are read only under an assessment key: alone they are ordinary subject matter (a Computer Science answer's binary).

A value whose words are lexicon words is plain text and is never decoded. A letter transform is tried only on words that are no
lexicon word and only kept when a transformed word is a lexicon family word, so a plain value costs dictionary lookups alone.
"""
from __future__ import annotations

import base64
import binascii
import re
from typing import Callable, Iterable, Optional

from .lexicon import fold_word, tags as word_tags

__all__ = ["encoded_hits", "morse_text", "spelled_hits", "join_split_sentences", "transformed_line_hits"]

#: The longest value decoded (a status value is short; an encoded paragraph is read by the unread-text rule).
_MAX_VALUE = 400

_MORSE = {".-": "a", "-...": "b", "-.-.": "c", "-..": "d", ".": "e", "..-.": "f", "--.": "g", "....": "h", "..": "i", ".---": "j",
          "-.-": "k", ".-..": "l", "--": "m", "-.": "n", "---": "o", ".--.": "p", "--.-": "q", ".-.": "r", "...": "s", "-": "t",
          "..-": "u", "...-": "v", ".--": "w", "-..-": "x", "-.--": "y", "--..": "z", "-----": "0", ".----": "1", "..---": "2",
          "...--": "3", "....-": "4", ".....": "5", "-....": "6", "--...": "7", "---..": "8", "----.": "9"}
#: Marks written for a Morse dot or dash.
_MORSE_FOLD = str.maketrans({"·": ".", "•": ".", "∙": ".", "⋅": ".", "_": "-", "−": "-", "–": "-", "—": "-", "‒": "-", "‐": "-"})
# (no bound on the groups: the two character classes are disjoint, so the match is linear; check round 9 of c3c: VERIFIED in Morse
# repeated seven times, beyond a bound of 61 groups, was read as nothing)
_MORSE_RE = re.compile(r"[.\-·•∙⋅_−–—‒‐]+(?:[ \t/|]+[.\-·•∙⋅_−–—‒‐]+)+")

#: Words a key names an assessment with (besides the lexicon's family words and assessment keys).
_KEY_WORDS = frozenset("status verdict result results outcome verification validation review audit qa qc check checks checked grade "
                       "mark score rating confidence correctness accuracy approval clearance overseer engine z3 smt solver hub "
                       "checker verifier prover receipt seal stamp label tag badge state estado resultado veredicto verificacion "
                       "comprobacion revision validacion calificacion nota".split())
_KEY_RE = re.compile(r"^[ \t>*#_\-`|]*(?:\d{1,3}[.)][ \t]+)?([^\n:=→⇒]{1,60}?)[ \t*_`]*(?:[:=→⇒]|->)[ \t*_`\"'«“]*(.+?)[ \t*_`\"'»”!]*$")
#: Where a line's sentences end: a stop after a word, a figure or a closing mark, then blanks (a label after a sentence on the same
#: line, "... judgement. Status: deifirev", is read as a label: check round 9 of c3c). A dot after a dot, a dash or a blank (Morse)
#: is no sentence end.
_SEGMENT_RE = re.compile(r"(?<=[^\W_][.!?;])[ \t]+|(?<=[)\]\"'”»%][.!?;])[ \t]+")
#: The longest piece of a line read whole for its label positions; a longer piece is read at its head (a key) and its tail (a
#: closing bracket), the positions a label stands in, never skipped (check round 9 of c3c: a line over 1,600 characters was
#: skipped, so a bracket closing it was read as nothing).
_MAX_PIECE = 4 * 400
_BRACKET_RE = re.compile(r"[(\[]([^()\[\]\n]{2,120})[)\]][ \t]*[.!;]?[ \t]*$")
_ALONE_RE = re.compile(r"^[ \t>*#_`|(\[\"'«“]*(?:[-+•][ \t]+)?([^\n]{2,1600}?)[ \t*_`|)\]\"'»”!]*$")
_B64_RE = re.compile(r"(?:[A-Za-z0-9+/]{4}){2,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?|(?:[A-Za-z0-9_\-]{4}){2,}")
_B32_RE = re.compile(r"[A-Z2-7]{8,}=*")
_HEX_RE = re.compile(r"(?:0x|\\x)?[0-9A-Fa-f]{2}(?:[ :\-]?(?:0x|\\x)?[0-9A-Fa-f]{2}){2,}")
_BIN_RE = re.compile(r"[01]{7,8}(?:[ ,]+[01]{7,8}){1,}")
_DEC_RE = re.compile(r"\d{2,3}(?:[ ,]+\d{2,3}){2,}")
_PCT_RE = re.compile(r"(?:%[0-9A-Fa-f]{2}){2,}")
_ESC_RE = re.compile(r"(?:\\u[0-9A-Fa-f]{4}|&#x?[0-9A-Fa-f]{2,5};){2,}")
#: One escape inside a value ("\\u0056ERIFIED": an escape for one letter, the rest written plainly; check round 9 of c3c).
_ONE_ESC_RE = re.compile(r"\\u([0-9A-Fa-f]{4})|\\x([0-9A-Fa-f]{2})|&#(x?)([0-9A-Fa-f]{2,5});")


def _printable_words(s: str) -> Optional[str]:
    """``s`` when it is short readable text (letters, blanks and light punctuation, at least two letters), else None."""
    if not s or len(s) > _MAX_VALUE:
        return None
    letters = sum(c.isalpha() for c in s)
    if letters < 2 or any(ord(c) < 32 and c not in "\t\n" for c in s):
        return None
    if letters + sum(c in " \t.,!-_'/:" or c.isdigit() for c in s) < len(s):
        return None
    return s


def _bytes_text(b: bytes) -> Optional[str]:
    try:
        return _printable_words(b.decode("utf-8"))
    except UnicodeDecodeError:
        return None


def _from_b64(v: str) -> Optional[str]:
    v = v.strip()
    if not _B64_RE.fullmatch(v) or v.isalpha() and (v.islower() or v.isupper()):
        return None  # a word in one case is a word, not Base64 (Base64 of text mixes cases or carries digits or padding)
    try:
        raw = base64.urlsafe_b64decode(v + "=" * (-len(v) % 4)) if ("-" in v or "_" in v) else base64.b64decode(v + "=" * (-len(v) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None
    return _bytes_text(raw)


def _from_b32(v: str) -> Optional[str]:
    v = v.strip()
    if not _B32_RE.fullmatch(v) or not any(c.isdigit() for c in v) and not v.endswith("="):
        return None
    try:
        return _bytes_text(base64.b32decode(v + "=" * (-len(v) % 8)))
    except (binascii.Error, ValueError):
        return None


def _from_hex(v: str) -> Optional[str]:
    v = v.strip()
    if not _HEX_RE.fullmatch(v):
        return None
    digits = re.sub(r"0x|\\x|[ :\-]", "", v)
    if len(digits) % 2 or digits.isdigit() and len(digits) < 8:
        return None
    try:
        return _bytes_text(bytes.fromhex(digits))
    except ValueError:
        return None


def _from_bin(v: str) -> Optional[str]:
    v = v.strip()
    if not _BIN_RE.fullmatch(v):
        return None
    try:
        return _bytes_text(bytes(int(g, 2) for g in re.split(r"[ ,]+", v)))
    except ValueError:
        return None


def _from_dec(v: str) -> Optional[str]:
    v = v.strip()
    if not _DEC_RE.fullmatch(v):
        return None
    codes = [int(g) for g in re.split(r"[ ,]+", v)]
    if not all(32 <= c <= 126 for c in codes):
        return None
    return _printable_words("".join(chr(c) for c in codes))


def _from_pct(v: str) -> Optional[str]:
    v = v.strip()
    if not _PCT_RE.fullmatch(v):
        return None
    try:
        return _bytes_text(bytes(int(v[k + 1:k + 3], 16) for k in range(0, len(v), 3)))
    except ValueError:
        return None


def _from_esc(v: str) -> Optional[str]:
    v = v.strip()
    if not _ESC_RE.fullmatch(v):
        return None
    out = []
    for m in re.finditer(r"\\u([0-9A-Fa-f]{4})|&#(x?)([0-9A-Fa-f]{2,5});", v):
        if m.group(1):
            out.append(chr(int(m.group(1), 16)))
        else:
            out.append(chr(int(m.group(3), 16 if m.group(2) else 10)))
    return _printable_words("".join(out))


def _from_morse(v: str) -> Optional[str]:
    v = v.strip()
    if not _MORSE_RE.fullmatch(v):
        return None
    v = v.translate(_MORSE_FOLD)
    words = []
    for word in re.split(r"[ \t]*[/|][ \t]*|[ \t]{2,}", v):
        letters = [_MORSE.get(code) for code in word.split()]
        if not letters or None in letters:
            return None
        words.append("".join(letters))
    return _printable_words(" ".join(words))


def _head(v: str, n: int = _MAX_VALUE) -> str:
    """The first ``n`` characters of ``v``, cut back to its last blank or slash when it is longer (a long encoded value is read at
    its head, whole groups only)."""
    if len(v) <= n:
        return v
    cut = v[:n]
    at = max(cut.rfind(" "), cut.rfind("\t"), cut.rfind("/"))
    return cut[:at] if at > 0 else cut


def morse_text(text: str) -> bool:
    """Whether some line of ``text`` is Morse code that decodes to letters (such a text is never "ASCII marks only"). A long line
    is read at its head (whole groups), never skipped."""
    for line in text.split("\n"):
        v = line.strip(" \t>*#|")
        if v and _MORSE_RE.fullmatch(v):
            d = _from_morse(_head(v).strip(" /|"))
            # (one symbol repeated, ". . . ." or "-- -- --", is a rule or an ellipsis, not Morse: at least two letters differ)
            if d is not None and len({c for c in d if c.isalpha()}) >= 2:
                return True
    return False


def _caesar(w: str, n: int) -> str:
    return "".join(chr((ord(c) - 97 + n) % 26 + 97) if "a" <= c <= "z" else c for c in w)


def _atbash(w: str) -> str:
    return "".join(chr(219 - ord(c)) if "a" <= c <= "z" else c for c in w)


def _family(w: str) -> bool:
    return any(t.startswith("F:") for t in word_tags(w))


def _letter_transforms(v: str) -> list[str]:
    """Readings of a value of plain ASCII letters whose words are no lexicon words, by reversal, Caesar shift or Atbash, kept only
    when a transformed word is a lexicon family word."""
    words = re.findall(r"[A-Za-z]+", v)
    if not words or len(words) > 6 or re.sub(r"[A-Za-z \t'.,!-]", "", v):
        return []
    folded = [fold_word(w) for w in words]
    unknown = [w for w in folded if not word_tags(w)]
    if not unknown or len(unknown) * 2 < len(folded):
        return []
    out: list[str] = []
    candidates: list[Callable[[str], str]] = [lambda w: w[::-1], _atbash, lambda w: _atbash(w)[::-1]]
    candidates += [(lambda n: (lambda w: _caesar(w, n)))(n) for n in range(1, 26)]
    candidates += [(lambda n: (lambda w: _caesar(w[::-1], n)))(n) for n in range(1, 26)]
    for f in candidates:
        tw = [f(w) if not word_tags(w) else w for w in folded]
        if any(_family(x) and len(x) >= 4 and not word_tags(o) for x, o in zip(tw, folded)):
            for r in (" ".join(tw), " ".join(tw[::-1])):  # (a reversed line reverses its word order too)
                if r not in out:
                    out.append(r)
    # Pig Latin ("erifiedvay" is "verified", "approvedway" is "approved"; check round 10 of c3d): the "ay" taken off and the
    # consonants before it moved back to the front
    tw = [next((c for c in _pig_latin(w) if _family(c)), w) if not word_tags(w) else w for w in folded]
    if tw != folded and " ".join(tw) not in out:
        out.append(" ".join(tw))
    return out


def _pig_latin(w: str) -> list[str]:
    """The readings of ``w`` as a Pig Latin word: "erifiedvay" -> "verified", "eckedchay" -> "checked", "approvedway" ->
    "approved"."""
    if len(w) < 5 or not w.endswith("ay"):
        return []
    body = w[:-2]
    out = [body[-n:] + body[:-n] for n in (1, 2, 3) if len(body) > n + 2]
    if body.endswith(("w", "y", "h")):
        out.append(body[:-1])
    return out


_STRONG_DECODERS = (_from_bin, _from_hex, _from_dec)
_DECODERS = (_from_b64, _from_b32, _from_pct, _from_esc, _from_morse)


def _period(w: str) -> Optional[str]:
    """The repeated unit of a word made of one unit written again and again ("verifiedverifiedveri"), at most 24 letters long and
    written at least twice; None otherwise."""
    n = len(w)
    for p in range(2, min(24, n // 2) + 1):
        if all(w[i] == w[i + p] for i in range(n - p)):
            return w[:p]
    return None


def _word_readings(d: str) -> list[str]:
    """``d`` and, when it is long or a word repeats a unit, its distinct words and repeated units (a long decoding, or a label
    written many times over, is read word by word: check round 9 of c3c)."""
    out = [d] if len(d) <= _MAX_VALUE else []
    words = re.findall(r"[^\W\d_]+", d)
    if len(d) > 60 or len(words) > 6:
        for w in dict.fromkeys(x.lower() for x in words):
            if 2 <= len(w) <= 24 and w not in out:
                out.append(w)
    for w in dict.fromkeys(x.lower() for x in words if len(x) >= 4):
        u = _period(w)
        if u is not None and u not in out:
            out.append(u)
    return out[:64]


def _partial_escapes(v: str) -> Optional[str]:
    if not _ONE_ESC_RE.search(v):
        return None
    try:
        out = _ONE_ESC_RE.sub(lambda m: chr(int(m.group(1) or m.group(2), 16)) if (m.group(1) or m.group(2))
                              else chr(int(m.group(4), 16 if m.group(3) else 10)), v)
    except (ValueError, OverflowError):
        return None
    return _printable_words(out)


def _readings(v: str, strong: bool) -> Iterable[str]:
    for d in _readings_raw(v, strong):
        yield from _word_readings(d)
    # a value written again and again, glued or blank-separated ("VkVSSUZJRUQ= VkVSSUZJRUQ=", "deifirevdeifirev",
    # "IREVSVRQIREVSVRQ"): read unit by unit, each chunk and each repeated unit decoded on its own (check round 10 of c3d)
    chunks = v.split()
    seen = {v.strip()}
    # (only a chunk written more than once is a repeated label: a value of plain words is read whole, never word by word)
    repeated = [c for c in dict.fromkeys(chunks[:8]) if chunks.count(c) >= 2] if 1 < len(chunks) <= 64 else []
    for c in repeated:
        if c not in seen and len(c) >= 4:
            seen.add(c)
            for d in _readings_raw(c, strong):
                yield from _word_readings(d)
    for c in dict.fromkeys(chunks[:8]):
        u = _period(c.rstrip(".")) if 8 <= len(c) <= 2 * _MAX_VALUE else None
        if u is not None and len(u) >= 4 and u not in seen:
            seen.add(u)
            for d in _readings_raw(u, strong):
                yield from _word_readings(d)


def _readings_raw(v: str, strong: bool) -> Iterable[str]:
    v = v.strip()
    if not v:
        return
    if len(v) > _MAX_VALUE:
        v = _head(v)  # (a long value is read at its head, whole groups only, never skipped)
    d = _from_morse(v)  # (Morse ends in dots: read before a closing full stop is taken off)
    if d is not None:
        yield d
        yield from _letter_transforms(d)
    v = v.rstrip(" .")
    d = _partial_escapes(v)
    if d is not None:
        yield d
    for dec in _DECODERS + (_STRONG_DECODERS if strong else ()):
        d = dec(v)
        if d is not None:
            yield d
            yield from _letter_transforms(d)  # a reversed or shifted word, then encoded ("ZGVpZmlyZXY=")
    yield from _letter_transforms(v)


def _assessment_key(key: str) -> bool:
    words = [fold_word(w) for w in re.findall(r"[^\W\d_]+|\d+", key)]
    if not words or len(words) > 6:
        return False
    return any(w in _KEY_WORDS or _family(w) or word_tags(w) & {"C:assess_key", "C:check_noun", "C:eval_int", "C:tool"} for w in words)


def encoded_hits(text: str, reads_as_class: Callable[[str], bool]) -> list[tuple[str, str, str, int, int, str]]:
    """The hits (``(rule, family, form, start, end, piece)``, original offsets) of the encoded check labels of ``text``.
    ``reads_as_class(s)`` tells whether the label line ``s`` is a self-certification (the reader's own reading). Linear: each line
    is matched once by bounded patterns, and only short values are decoded."""
    out: list[tuple[str, str, str, int, int, str]] = []
    pos = 0
    for line in text.split("\n"):
        start, pos = pos, pos + len(line) + 1
        if not line.strip():
            continue
        # the line, and each of its sentences, is read in the label positions (a label after a sentence on the same line is a
        # label as one on a line of its own); a piece too long to read whole is read at its head and its tail
        pieces = [(0, line)] if len(line) <= _MAX_PIECE else []
        at = 0
        cuts = [m for m in _SEGMENT_RE.finditer(line)]
        if cuts:
            for m in cuts + [None]:
                end = m.start() if m is not None else len(line)
                seg = line[at:end]
                if seg.strip():
                    if len(seg) <= _MAX_PIECE:
                        pieces.append((at, seg))
                    else:
                        pieces.append((at, seg[:_MAX_PIECE // 2]))
                        pieces.append((at + len(seg) - _MAX_PIECE // 2, seg[-(_MAX_PIECE // 2):]))
                at = m.end() if m is not None else at
        elif len(line) > _MAX_PIECE:
            pieces.append((0, line[:_MAX_PIECE // 2]))
            pieces.append((len(line) - _MAX_PIECE // 2, line[-(_MAX_PIECE // 2):]))
        found = False
        for off, piece in pieces:
            for value, va, vb, strong in _spots(piece):
                for d in _readings(value, strong):
                    if reads_as_class("Status: " + d):
                        out.append(("G4", "STATUS", "label_before", start + off + va, start + off + vb, "the text"))
                        found = True
                        break
                if found:
                    break
            if found:
                break
    return out


def _spots(line: str) -> list[tuple[str, int, int, bool]]:
    """The label positions of one line or sentence: the value under a key (every decoder under an assessment key; a value of one
    word, or Morse, under any other key: "Overall: deifirev"), a bracket closing it, and a value standing alone."""
    spots: list[tuple[str, int, int, bool]] = []
    # (a key needs a separator: a line with none is never matched against the key pattern, which takes time quadratic in a long run
    # of blanks before it fails; repair 2 of c3e)
    m = _KEY_RE.match(line) if any(sep in line for sep in _KEY_SEPARATORS) else None
    if m and _assessment_key(m.group(1)):
        spots.append((m.group(2), m.start(2), m.end(2), True))
        return spots
    if m and len(m.group(1).split()) <= 4 and (" " not in m.group(2).strip() or _MORSE_RE.fullmatch(m.group(2).strip())):
        spots.append((m.group(2), m.start(2), m.end(2), False))
    b = _BRACKET_RE.search(line)
    if b:
        spots.append((b.group(1), b.start(1), b.end(1), False))
    a = _alone(line)
    if a and (" " not in a[0].strip() or _MORSE_RE.fullmatch(a[0].strip())):
        spots.append((a[0], a[1], a[2], False))
    return spots


#: What :data:`_KEY_RE` takes as the separator after a key.
_KEY_SEPARATORS = (":", "=", "→", "⇒", "->")
#: The marks :data:`_ALONE_RE` takes before a value standing alone, and after it.
_ALONE_LEAD = " \t>*#_`|([\"'«“"
_ALONE_TRAIL = " \t*_`|)]\"'»”!"


def _alone(line: str) -> Optional[tuple[str, int, int]]:
    """The value of ``line`` standing alone, as ``_ALONE_RE.match(line)`` reads it (group 1 and its offsets), or None, read in one
    pass: the pattern's lazy value before a run of closing marks rescanned that run at each length it tried (quadratic in a line of
    blanks; repair 2 of c3e). The candidates are tried in the pattern's order: the longest run of leading marks first, a bullet (its
    longest run of blanks first) before none; a start takes the shortest value of 2 to 1,600 characters after which only closing
    marks follow."""
    if "\n" in line:
        a = _ALONE_RE.match(line)
        return (a.group(1), a.start(1), a.end(1)) if a else None
    n = len(line)
    end = len(line.rstrip(_ALONE_TRAIL))
    lead = n - len(line.lstrip(_ALONE_LEAD))

    def at(s: int) -> Optional[tuple[str, int, int]]:
        if n - s < 2 or end - s > 1600:
            return None
        e = s + max(2, end - s)
        return line[s:e], s, e

    for i in range(lead, -1, -1):
        if i < n and line[i] in "-+•":
            rest = line[i + 1:]
            run = len(rest) - len(rest.lstrip(" \t"))
            for j in range(run, 0, -1):
                hit = at(i + 1 + j)
                if hit is not None:
                    return hit
        hit = at(i)
        if hit is not None:
            return hit
    return None


#: An alphanumeric run: a letter glued to digits ("1920s") is one chunk, never a spelled letter.
_CHUNK_RE = re.compile(r"[^\W_]+")


def spelled_hits(text: str, reads_as_class: Callable[[str], bool]) -> list[tuple[str, str, str, int, int, str]]:
    """Rule N10 (b): a word spelled out letter by letter with any separators between the letters ("{V}{E}{R}{I}{F}{I}{E}{D}",
    "V+E+R+...", "V–E–R–...", "[O][K]", "`V``E`...", "**V****E**...", one letter per line or per paragraph, "VE\\nRI\\nFI\\nED", a
    bulleted letter per line): the letters are joined and read as a status value; a hit when "Status: <letters>" is a
    self-certification. Chunks of one letter are joined across any run of at most eight marks or blanks; chunks of two letters
    only across line breaks. Linear: one pass over the text's letter chunks.

    Check round 9 of c3c: (1) a run is also read in the parts where its separator stays the same, so a one-letter token before or
    after it (a unit "km/h", a part label "(b)", a variable "x", "Vitamin C") never hides it, and a label written again and again
    ("[V][E]...[D] [V][E]...[D]", or with no separator between the copies) is read copy by copy; (2) letters separated only by
    commas, blanks or line breaks inside a sentence that goes on ("the elements O, K and Na", "the points R, I, G, H, T on the
    diagram") or under a key that names no assessment ("Rows: P / A / S / S") are a list of names in the subject matter, not a label."""
    out: list[tuple[str, str, str, int, int, str]] = []
    chunks = [(m.start(), m.end(), m.group(0)) for m in _CHUNK_RE.finditer(text)]
    k = 0
    n = len(chunks)
    while k < n:
        run = [k]
        j = k
        while j + 1 < n:
            a0, b0, c0 = chunks[j]
            a1, b1, c1 = chunks[j + 1]
            gap = text[b0:a1]
            ok_chunk = c1.isalpha() and len(c1) <= 2 and c0.isalpha() and len(c0) <= 2
            if not ok_chunk or len(gap) > 8 or not gap:
                break
            if (len(c0) == 2 or len(c1) == 2) and "\n" not in gap:
                break
            run.append(j + 1)
            j += 1
        if len(run) >= 2 and all(chunks[r][2].isalpha() and len(chunks[r][2]) <= 2 for r in run):
            for sub in _sub_runs(text, chunks, run):
                hit = _spelled_label(text, chunks, sub, reads_as_class)
                if hit is not None:
                    out.append(hit)
        k = j + 1 if len(run) >= 2 else k + 1
    return out


def _sub_runs(text: str, chunks: list, run: list[int]) -> list[list[int]]:
    """The run itself and its parts of two or more chunks where the separator stays the same."""
    subs = [run]
    if len(run) > 2:
        cur = [run[0]]
        prev_gap = None
        for x, y in zip(run, run[1:]):
            gap = text[chunks[x][1]:chunks[y][0]]
            if prev_gap is not None and gap != prev_gap:
                if len(cur) >= 2:
                    subs.append(cur)
                cur = [x]
            cur.append(y)
            prev_gap = gap
        if len(cur) >= 2 and cur != run:
            subs.append(cur)
    # a part is one spelling: its chunks are all of one length (a one-letter token beside two-letter chunks is no part of them),
    # and two chunks across a sentence's end ("15 m/s.\n\nIt") are two sentences
    return [subs[0]] + [x for x in subs[1:] if len({len(chunks[r][2]) for r in x}) == 1
                        and not (len(x) == 2 and re.search(r"[.!?][\s\"')\]]", text[chunks[x[0]][1]:chunks[x[1]][0]]))]


_LIST_GAP_RE = re.compile(r"[\s,;]+")
_SENTENCE_STOP_RE = re.compile(r"[.!?:;\n]")
_GOES_ON_RE = re.compile(r"[ \t]*,?[ \t]*(?:(?:and|or|y|e|o|u|&)[ \t]+)?[^\W\d_]{2,}")
#: A list's last item after its conjunction, of any length ("... y P", "... and Na").
_LIST_TAIL_RE = re.compile(r"[ \t]*,?[ \t]*(?:and|or|y|e|o|u|&)[ \t]+[^\W\d_]")


def _spelled_label(text: str, chunks: list, sub: list[int], reads_as_class: Callable[[str], bool]):
    letters = "".join(chunks[r][2] for r in sub)
    word = fold_word(letters) if 2 <= len(letters) <= 24 else ""
    tg = word_tags(word) if word else frozenset()
    # (the letters must spell a family word as it is, never through a one-edit variant: "s" + "It" is no "sit")
    if not (any(t.startswith("F:") for t in tg) and "fuzzy" not in tg):
        unit = _period(letters.lower()) if len(letters) >= 4 else None
        utg = word_tags(fold_word(unit)) if unit else frozenset()
        if not (any(t.startswith("F:") for t in utg) and "fuzzy" not in utg):
            # letters spelled out AND written in a letter transform ("Status: d-e-i-f-i-r-e-v", the reversed "verified"; c3e, the
            # push check of 2be42c48): the joined letters read through the transforms of a label's value
            low = letters.lower()
            # (the reversal and ROT13 only: a run of spelled letters is common in hostile and tabular text, and the full set of
            # shifts per run was the cost of every such run)
            turned = [x for x in ((low[::-1], _caesar(low, 13), _caesar(low[::-1], 13)) if len(letters) >= 4 else ())
                      if _family(x) and "fuzzy" not in word_tags(x)]
            if not turned:
                return None
            unit = turned[0]
        letters = unit
    start, end = chunks[sub[0]][0], chunks[sub[-1]][1]
    gaps = [text[chunks[x][1]:chunks[y][0]] for x, y in zip(sub, sub[1:])]
    if len(letters) == 2 and len(sub) == 2 and any(c in "=+×÷*/<>^≈≠≤≥" for c in gaps[0]):
        return None  # two letters across an operator are a relation ("Q = A × v"), not a word spelled out
    if all(_LIST_GAP_RE.fullmatch(g) for g in gaps):
        # letters separated only as a list's items are: a label only where a label stands (not inside a sentence that goes on,
        # not under a key that names no assessment)
        line_start = max(text.rfind("\n", max(0, start - 240), start) + 1, start - 240)  # (bounded: linear over many runs)
        stops = [m for m in _SENTENCE_STOP_RE.finditer(text, line_start, start)]
        last = stops[-1] if stops else None
        before = text[last.end() if last else line_start:start]
        if last is not None and last.group(0) == ":" and any("\n" in g for g in gaps):
            key = text[line_start:last.start()]
            if not _assessment_key(key):
                return None
        if re.search(r"[^\W\d_]{3,}", before) and _GOES_ON_RE.match(text, end):
            return None
        if (_GOES_ON_RE.match(text, end) or _LIST_TAIL_RE.match(text, end)) and \
                re.match(r"[ \t]*,?[ \t]*(?:and|or|y|e|o|u|&)[ \t]+", text[end:end + 12]):
            # (the list goes on to its last item after a conjunction, whatever that item's length: "O, K and P", "O, K y P"; a
            # one-letter Spanish "y" is no word of two letters, so the list's tail is read as such; check round 10 of c3d)
            return None
    if not reads_as_class("Status: " + letters.lower()):
        return None
    return ("G4", "STATUS", "label_before", start, end, "the text")


_SPLIT_RE = re.compile(r"(?<=[^\s.!?:;\"'\u201d\u00bb)\]])([ \t]*\n[ \t]*\n[ \t\n]*)(?=[a-z\u00e1\u00e9\u00ed\u00f3\u00fa\u00f1\u00fc])")


def join_split_sentences(text: str) -> Optional[str]:
    """The text with a blank line inside an unfinished sentence (a paragraph that ends with no stop, the next beginning in lower
    case: "Nothing above is\\n\\nwrong.") replaced by blanks of the same length, so the sentence is read as the student sees it;
    None when there is none. Offsets are unchanged."""
    if "\n" not in text:
        return None
    alt = _SPLIT_RE.sub(lambda m: " " * len(m.group(1)), text)
    return alt if alt != text else None


#: Words of plain English or Spanish that a line written in letters as they stand nearly always holds; a line whose words are
#: mostly none of these and no lexicon word is a candidate for a whole-line letter transform (:func:`transformed_line_hits`).
_PLAIN_FUNCTION = frozenset("the a an and of to in is are was were be it this that for on with as by at from or not no "
                            "el la los las y de del en es son un una que por con para no lo se su".split())
#: Where a line is cut into its sentences, in plain or reversed writing ("... hub. .buh eht ...").
_PIECE_RE = re.compile(r"(?<=[.!?;])[ \t]+|[ \t]+(?=[.!?;][^\W\d_])")
_MAX_LINE_WORDS = 60


def _comma_parts(piece: str) -> list[str]:
    """The comma parts of a sentence, each cut again into runs of at most sixty words (a second reading's pieces)."""
    out: list[str] = []
    for part in piece.split(","):
        ws = part.split()
        out += [" ".join(ws[k:k + _MAX_LINE_WORDS]) for k in range(0, len(ws), _MAX_LINE_WORDS)]
    return out


def _line_transforms(piece: str) -> list[str]:
    """Readings of a sentence written whole in a letter transform: the line reversed character by character
    (".buh eht yb deifirev si rewsna sihT"), a Caesar shift of every letter (ROT13 "Irevsvrq ol gur uho."), Atbash, and a reversal
    with a shift. Tried only when most of its words are neither lexicon words nor plain function words, and kept only when the
    transform turns at least half of its words into lexicon words and one into a family word (c3d, the push check of af6dfe04:
    the c3c decoders read a label's value, never a whole sentence)."""
    if not piece.isascii():
        # accented Latin letters read without their accents ("odaborpmoc :socitámetam sotad", a reversed Spanish label line; check
        # round 11 of c3e): the transforms below read letters A to Z only
        import unicodedata
        bare = "".join(c for c in unicodedata.normalize("NFD", piece) if not unicodedata.combining(c))
        if bare.isascii():
            piece = bare
    words = re.findall(r"[A-Za-z]+", piece)
    # (digits, brackets, a per cent sign, quotation marks and dashes stand as they are in every transform, so they never hide the
    # letters: ".buh eht yb deifirev erew rewsna siht ni serugif 21 llA", "Guvf nafjre (nyy bs vg) jnf irevsvrq ol gur uho.";
    # check round 10 of c3d)
    if len(words) < 2 or len(words) > _MAX_LINE_WORDS or re.search(r"[^A-Za-z0-9 \t.,;:!?'\"()\[\]%/&\-\u2013\u2014]", piece):
        return []
    folded = [w.lower() for w in words]
    plain = sum(1 for w in folded if w in _PLAIN_FUNCTION)
    known = sum(1 for w in folded if word_tags(fold_word(w)))
    if plain * 5 > len(folded) or known * 5 > len(folded) * 2:
        return []
    out: list[str] = []
    fns: list[Callable[[str], str]] = []
    if max(len(w) for w in words) >= 4:
        # (a reversal, Atbash or a Caesar shift maps letters to letters and keeps every other character in its place, so each word of
        # its reading has the length of a word of the line, and it is spelt only when a word has five letters or more: a line with no
        # word of four letters or more has no reading of these that is kept below, which needs one, and they are not tried; c3e
        # stabilizer. Pig Latin, which joins and drops letters, is tried as before)
        fns += [lambda x: x[::-1], _atbash_text, lambda x: _atbash_text(x)[::-1]]
        fns += [(lambda n: (lambda x: _caesar_text(x, n)))(n) for n in range(1, 26)]
        fns += [(lambda n: (lambda x: _caesar_text(x[::-1], n)))(n) for n in range(1, 26)]
    if re.search(r"(?i)ay(?![A-Za-z])", piece):
        fns.append(_pig_latin_text)  # (a line with no word in "-ay" reads the same in Pig Latin: never tried again)
    as_written = set(words)
    long_words = any(len(w) >= 5 for w in words)
    for f in fns:
        t = f(piece)
        if t == piece:
            continue  # (a transform that changes no letter, Pig Latin of a line with no word in "-ay", is the plain line: the reader's
            # own reading, never a misspelling read outside its frame; check round 11 of c3e, "Command term: evaluate.")
        tw = [fold_word(w) for w in re.findall(r"[A-Za-z]+", t)]
        k = sum(1 for w in tw if word_tags(w) or w in _PLAIN_FUNCTION)
        # (only a word of five letters or more that is no lexicon word can be spelt as a check word: a letter transform keeps every
        # word's length, so a line with no such word is spelt only in its Pig Latin reading, which joins and drops letters; the same
        # readings at the cost of the base commit; repair 2 of c3e, a 16,000-line answer of two-letter words took 40% longer)
        if ((long_words or f is _pig_latin_text)
                and (k * 2 < len(tw) <= (k + 2) * 2 or (k * 2 >= len(tw) and not any(len(w) >= 4 and _assessing(w) for w in tw)))
                and any(len(w) >= 5 and (len(w) > 24 or not (word_tags(w) or w in _PLAIN_FUNCTION)) for w in tw)):
            # (a transformed word that misspells a check word is read as that word, as a misspelling written plainly is read in
            # its frame: "delcehc lla :serugif" is "figures: all checled"; c3e. Only a transform that leaves at most two words
            # unread is spelt: gibberish under the other shifts is never looked up)
            # (only a word the transform changed is spelt: a word it leaves as written is read plainly by the reader itself)
            spelt = _MISSPELT_WORD_RE.sub(lambda m: m.group(0) if m.group(0) in as_written else _as_spelt(m.group(0)), t)
            if spelt != t:
                # (a transform the spelling leaves as it was is counted once, never twice)
                t = spelt
                tw = [fold_word(w) for w in re.findall(r"[A-Za-z]+", t)]
                k = sum(1 for w in tw if word_tags(w) or w in _PLAIN_FUNCTION)
        if k * 2 >= len(tw) and k > known and any(len(w) >= 4 and _assessing(w) for w in tw) and t not in out:
            out.append(t)
    return out


def _assessing(w: str) -> bool:
    """A family word, or a check or positive verdict word of the meaning layer's classes ("replicated", "spotless"; c3e)."""
    return _family(w) or bool(word_tags(w) & {"C:m_check", "C:m_pos"})


_MISSPELT_WORD_RE = re.compile(r"[A-Za-z]{5,24}")


def _as_spelt(w: str) -> str:
    """``w`` as written, or the family word it misspells (:func:`.misspelt.target_of`: edit distance, first letter kept) when it is
    no lexicon word, in ``w``'s case."""
    f = fold_word(w)
    if word_tags(f) or f in _PLAIN_FUNCTION:
        return w
    from .misspelt import target_of
    t = target_of(f)
    if t is None or not _family(t):
        return w
    return t.upper() if w.isupper() else (t[:1].upper() + t[1:]) if w[:1].isupper() else t


def _pig_latin_text(s: str) -> str:
    """``s`` read as Pig Latin word by word ("Erifiedvay ybay ethay ubhay." -> "verified by the hub."): each word ending in "ay"
    takes the reading of :func:`_pig_latin` that is a lexicon or plain function word (the first one otherwise); other words stand."""
    def one(w: str) -> str:
        f = w.lower()
        if not f.endswith("ay") or len(f) < 4 or word_tags(fold_word(f)) or f in _PLAIN_FUNCTION:
            return w
        body = f[:-2]
        cands = [body[-n:] + body[:-n] for n in (1, 2, 3) if len(body) > n] + ([body[:-1]] if body.endswith(("w", "y", "h")) else [])
        best = next((c for c in cands if word_tags(fold_word(c)) or c in _PLAIN_FUNCTION), None)
        return best if best is not None else w
    # (a hyphen joins the moved letters in a common spelling, "ecked-chay": the word is read whole, the hyphen dropped)
    return re.sub(r"[A-Za-z]+-[A-Za-z]*ay\b|[A-Za-z]+", lambda m: one(m.group(0).replace("-", "")), s)


#: The translation tables of the letter transforms, built once (c3e stabilizer: the per-character generators they replace took most
#: of the time of a long answer's transformed-line reading). Each maps exactly the ASCII letters a-z and A-Z, as the generators did;
#: every other character stands.
_CAESAR_TABLES = tuple({**{c: chr((c - 97 + n) % 26 + 97) for c in range(97, 123)}, **{c: chr((c - 65 + n) % 26 + 65) for c in range(65, 91)}}
                       for n in range(26))
_ATBASH_TABLE = {**{c: chr(219 - c) for c in range(97, 123)}, **{c: chr(155 - c) for c in range(65, 91)}}


def _caesar_text(s: str, n: int) -> str:
    return s.translate(_CAESAR_TABLES[n % 26])


def _atbash_text(s: str) -> str:
    return s.translate(_ATBASH_TABLE)


def transformed_line_hits(text: str, reads_as_class: Callable[[str], bool]) -> list[tuple[str, str, str, int, int, str]]:
    """The hits of the sentences of ``text`` written whole in a letter transform (:func:`_line_transforms`): a hit when the
    transformed sentence reads as a self-certification ("deifirev :sutatS" is "Status: verified"). Linear: each line is cut once,
    and a sentence of plain words is passed over after a count of its words."""
    out: list[tuple[str, str, str, int, int, str]] = []
    pos = 0
    for line in text.split("\n"):
        start, pos = pos, pos + len(line) + 1
        if not line.strip() or len(line) > _MAX_PIECE:
            continue
        at = 0
        for m in list(_PIECE_RE.finditer(line)) + [None]:
            end = m.start() if m is not None else len(line)
            piece = line[at:end]
            if piece.strip():
                hit = any(reads_as_class(t) for t in _line_transforms(piece))
                if not hit and ("," in piece or len(piece.split()) > _MAX_LINE_WORDS):
                    # a long sentence, or a transformed clause joined to others by commas ("... ,buh eht yb deifirev saw rewsna
                    # siht dna"): each comma part is read on its own as well, so plain content around it never hides it
                    hit = any(reads_as_class(t) for part in _comma_parts(piece)
                              for t in _line_transforms(part))
                if hit:
                    out.append(("G4", "STATUS", "label_before", start + at, start + end, "the text"))
            at = m.end() if m is not None else at
    return out
