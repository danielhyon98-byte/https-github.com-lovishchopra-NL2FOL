"""Misspelt check vocabulary read in its frame (rule N9 (b) of the self-certification reader, c3d).

Rule N9 reads, from a list built once, the variants of the long family words with one deletion or one adjacent transposition
("psased", "signd"), and exempts the variants that are real words ("singed", "passe", "prefect"). That list missed two kinds of
misspelling (the push check of af6dfe04):

* a misspelling by any other edit, or by two ("Veryfied", "Verifyed", "Validaded", "chequed"), which no list of one-edit
  variants holds;
* a real word one edit from a check word, exempt wherever it stood, so "Singed off by the hub." and "This answer passe every
  check." were read as the real words they spell.

Here a misspelling is read by EDIT DISTANCE, not by a list, and only INSIDE A CHECK FRAME: a word that is no lexicon word (or is
one of the exempt real words) and lies within a small Damerau-Levenshtein distance of a family word of the lexicon is a
candidate, and the candidate is read as that word only when the sentence, read with the candidate written as that word, is a
self-certification while the sentence as written is not. Outside such a frame a real word keeps its own meaning ("The cloth was
singed by the fire.", "The prefect read the decree.") and an unknown word stays unknown.

Bounds: a candidate keeps the first letter of its word; it is one edit from it, or two in a word of nine letters or more, or two
that vanish once both are spelled by sound ("chequed" for "checked"). The frame is read in the candidate's sentence: its agent
is an evaluator, its subject the answer or an item of it, its place a label's value, or its object a check (``_in_check_frame``).
The family words are indexed once by their deletions (two at most), so a word is looked up in time linear in its length; a
sentence is read again only when it holds a candidate in a frame, once per candidate.
"""
from __future__ import annotations

import functools
import re
from typing import Callable, Optional

from .lexicon import fold_word, fuzzy_targets, fuzzy_targets_es, lexicon, tags as word_tags

__all__ = ["candidates", "frame_hits"]

#: A word of letters (a hyphen or apostrophe inside it), in any Latin script.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")
_MIN_LEN = 5
_MAX_LEN = 24


def _targets() -> frozenset[str]:
    lex = lexicon()
    out = set(fuzzy_targets(lex)) | set(fuzzy_targets_es(lex))
    # the family words of five letters too ("check" in "chequed" is "checked"; "proved"): the frame decides, not the length
    for w, tg in lex.words.items():
        if w.isalpha() and len(w) >= 5 and any(t.startswith("F:") for t in tg) and "prod" not in tg:
            out.add(w)
    return frozenset(out)


def _deletes(w: str, d: int) -> set[str]:
    out = {w}
    frontier = {w}
    for _ in range(d):
        nxt = set()
        for x in frontier:
            for i in range(1, len(x)):  # (the first letter is kept)
                nxt.add(x[:i] + x[i + 1:])
        out |= nxt
        frontier = nxt
    return out


_INDEX: list = []


def _index() -> dict[str, tuple[str, ...]]:
    """Each deletion (up to two, never of the first letter) of each target word -> the target words it comes from."""
    if not _INDEX:
        idx: dict[str, set[str]] = {}
        for t in _targets():
            for x in _deletes(t, 2):
                idx.setdefault(x, set()).add(t)
        _INDEX.append({k: tuple(sorted(v)) for k, v in idx.items()})
    return _INDEX[0]


def _distance(a: str, b: str, bound: int) -> int:
    """Damerau-Levenshtein (optimal string alignment) distance of ``a`` and ``b``, or ``bound + 1`` once it exceeds ``bound``."""
    if abs(len(a) - len(b)) > bound:
        return bound + 1
    prev2: Optional[list[int]] = None
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if prev2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > bound:
            return bound + 1
        prev2, prev = prev, cur
    return prev[-1]


@functools.lru_cache(maxsize=65536)
def target_of(word: str) -> Optional[str]:
    """The family word ``word`` (folded, lower case) may misspell, or None: ``word`` is no lexicon word (or is a real word exempt
    from rule N9), keeps the target's first letter and lies within the bounds of the module docstring. The nearest target wins;
    ties go to the first in order."""
    if not (_MIN_LEN <= len(word) <= _MAX_LEN) or not word.isalpha():
        return None
    if word in lexicon().words or word_tags(word):
        return None  # (a lexicon word, or a variant rule N9 already reads; an exempt real word has no tags and is a candidate)
    idx = _index()
    found: dict[str, int] = {}
    for x in _deletes(word, 2):
        for t in idx.get(x, ()):
            if t[0] == word[0] and t != word and t not in found:
                d = _distance(word, t, 2)
                # one edit; or two in a long word; or two that vanish once spelled by sound ("chequed" for "checked")
                if d <= 1 or (d == 2 and (len(word) >= 9 or _sound(word) == _sound(t))):
                    found[t] = d
    best = sorted((d, t) for t, d in found.items())
    if not best:
        # a spelling by sound three edits away ("Revued" for "reviewed"; check round 10 of c3d): the word and the target sound
        # alike and keep the first letter
        t = _sound_index().get(_sound(word))
        if t is not None and t[0] == word[0] and t != word and _distance(word, t, 3) <= 3:
            return t
    return best[0][1] if best else None


_SOUND_INDEX: list = []


def _sound_index() -> dict[str, str]:
    """Each target word's sound spelling -> the target (the first in order when two sound alike)."""
    if not _SOUND_INDEX:
        idx: dict[str, str] = {}
        for t in sorted(_targets()):
            idx.setdefault(_sound(t), t)
        _SOUND_INDEX.append(idx)
    return _SOUND_INDEX[0]


_SOUND = (("iew", "u"), ("ew", "u"), ("ph", "f"), ("ck", "k"), ("qu", "k"), ("c", "k"), ("y", "i"), ("z", "s"))


def _sound(w: str) -> str:
    """``w`` spelled by sound, coarsely: "iew" and "ew" as "u", "ph" as "f", "ck", "qu" and "c" as "k", "y" as "i", "z" as "s", a doubled letter once."""
    for a, b in _SOUND:
        w = w.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", w)


def candidates(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, target)`` for each word of ``text`` that may misspell a family word (:func:`target_of`)."""
    out = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        if "-" in raw or "'" in raw or "’" in raw:
            continue
        t = target_of(fold_word(raw))
        if t is not None:
            out.append((m.start(), m.end(), t))
    return out


def _spelled_as(raw: str, target: str) -> str:
    if raw.isupper() and len(raw) > 1:
        return target.upper()
    if raw[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


#: The most characters of a candidate's sentence read on each side of it.
_WINDOW = 160
#: Where a sentence ends (the frame of a candidate is read inside its sentence).
_SENT_END_RE = re.compile(r"[.!?;\n]")
#: Particles between a check verb and its agent ("signed off by", "checked over by").
_PARTICLES = frozenset("off over through out up down".split())
_BY = frozenset(("by", "por", "from"))
_EVALUATOR_TAGS = ("C:eval_int", "C:tool", "C:eval_asr", "C:m_eval", "C:assessor_extra", "C:eval_int_agentive")
_OWN_TAGS = ("C:anchor", "C:anchor_idioms", "C:poss1", "C:pron1")
_LINK_TAGS = ("C:aux", "C:copula", "C:neg", "C:det", "C:dist", "C:anaph", "C:demonstrative", "C:part", "C:genre", "C:genre_strong",
              "C:perfect_aux", "C:present_aux", "C:past_aux", "C:weak")


def _word_toks(sentence: str) -> list[tuple[int, int, str, frozenset]]:
    return [(m.start(), m.end(), fold_word(m.group(0)), word_tags(fold_word(m.group(0)))) for m in _WORD_RE.finditer(sentence)]


_DEICTIC = ("this", "these", "esta", "este", "esto", "estos", "estas")
_DIST = ("every", "all", "each", "todas", "todos", "cada")


def _own_object(after: list) -> bool:
    for i, t in enumerate(after[:5]):
        if t[3] & {"C:anchor", "C:anchor_idioms"}:
            return True
        if t[2] in _DEICTIC + _DIST and any(x[3] & {"C:genre", "C:genre_strong", "C:part"} for x in after[i + 1:i + 4]):
            return True
    return False


def _in_check_frame(sentence: str, a: int) -> bool:
    """Whether the word at ``a`` of ``sentence`` stands in a check or assessment frame about the answer: (1) its agent is an
    evaluator ("... by the hub", "... off by the system", "por el revisor"); (2) its subject is the answer, an item of it or the
    writer, with nothing but auxiliaries, negators, determiners and part nouns between ("This answer is ...", "This answer passe
    ...", "All of the figures above were ...", "I have ..."); (3) it is a label's value under an assessment key ("Status: passe");
    or (4) its object is a check ("... passe every check"); or (5) it opens a fragment coordinated with a check participle
    ("Revued and approved.")."""
    toks = _word_toks(sentence)
    k = next((i for i, t in enumerate(toks) if t[0] == a), None)
    if k is None:
        return False
    after = toks[k + 1:k + 6]
    j = 0
    while j < len(after) and after[j][2] in _PARTICLES:
        j += 1
    if j < len(after) and after[j][2] in _BY:
        rest = [t for t in after[j + 1:] if not t[3] & {"C:det", "C:definite", "C:indefinite", "C:poss1"}]
        if rest and rest[0][3] & set(_EVALUATOR_TAGS):
            return True
    obj = [t for t in after if not t[3] & {"C:det", "C:dist", "C:definite", "C:indefinite"}]
    if obj and obj[0][3] & {"C:check_noun"}:
        return True
    before = toks[:k]
    # (5) a fragment that opens with the word, coordinated with a check participle ("Revued and approved.", "Chequed and signed
    # off."; check round 10 of c3d): the two participles label the same thing, the answer the fragment stands in
    if k == 0 and len(after) >= 2 and after[0][2] in ("and", "y", "&") and any(x.startswith("F:") for x in after[1][3]) and \
            (after[1][2].endswith(("ed", "ado", "ada", "ido", "ida")) or after[1][3] & {"v:part"}):
        return True
    before = toks[:k]
    head = sentence[:a].rstrip()
    if head.endswith(":") and len(before) <= 4 and any(t[3] & {"C:assess_key", "C:check_noun"} or
                                                       any(x.startswith("F:") for x in t[3]) for t in before):
        return True
    for i in range(len(before) - 1, -1, -1):
        t = before[i]
        if t[3] & {"C:pron1", "C:poss1"}:
            # the writer as the subject: a frame only with the answer or an item of it as the object ("I have veryfied every figure
            # above"), never with the subject matter ("I have treated the 15-mark part as the extended part")
            return _own_object(after)
        if t[3] & {"C:anchor", "C:anchor_idioms"} or (t[2] in _DEICTIC + _DIST and i + 1 < len(before) and
                                                      before[i + 1][3] & {"C:genre", "C:genre_strong", "C:part"}):
            return True
        if not t[3] & set(_LINK_TAGS) and not t[2] in ("been", "being", "fully", "now", "also", "all", "every", "of", "here", "de"):
            return False
        if k - i > 6:
            return False
    # (a sentence that opens with the word, "Veryfied.", or "Singed off by ..." handled above, is no frame by itself)
    return False


def frame_hits(text: str, reads: Callable[[str], list]) -> list[tuple[str, str, str, int, int, str]]:
    """The hits of the misspelt check words of ``text`` read in their frame (module docstring). ``reads(s)`` is the reader's own
    list of hits for ``s``. Each candidate in a check frame (:func:`_in_check_frame`) is read in a window of its sentence (at most
    :data:`_WINDOW` characters each side); overlapping windows are read as one, with every candidate in them written as its
    target, and each such candidate is a hit when that reading holds one (family of the reading's first hit, form "misspelt"). A
    window whose words as written already read as a self-certification adds nothing new but a second name for the same claim.
    Linear: each character is in at most one window read."""
    cands = candidates(text)
    if not cands:
        return []
    framed: list[tuple[int, int, int, int, str]] = []
    for a, b, target in cands:
        sa = max((m.end() for m in _SENT_END_RE.finditer(text, max(0, a - _WINDOW), a)), default=max(0, a - _WINDOW))
        m_end = _SENT_END_RE.search(text, b, min(len(text), b + _WINDOW))
        sb = m_end.end() if m_end else min(len(text), b + _WINDOW)
        if _in_check_frame(text[sa:sb], a - sa):
            framed.append((sa, sb, a, b, target))
    out: list[tuple[str, str, str, int, int, str]] = []
    k = 0
    while k < len(framed):
        sa, sb = framed[k][0], framed[k][1]
        group = [framed[k]]
        k += 1
        while k < len(framed) and framed[k][0] < sb:
            sb = max(sb, framed[k][1])
            group.append(framed[k])
            k += 1
        parts, at = [], sa
        for _sa, _sb, a, b, target in group:
            parts.append(text[at:a])
            parts.append(_spelled_as(text[a:b], target))
            at = b
        parts.append(text[at:sb])
        got = reads("".join(parts))
        if got:
            out += [("N9", got[0][1], "misspelt", a, b, "the text") for _sa, _sb, a, b, _t in group]
    return out
