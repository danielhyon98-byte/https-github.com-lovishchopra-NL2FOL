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

Bounds: a candidate keeps the first letter of its word (or writes it as the letter that sounds the same: Spanish b and v,
"berificado"; c3g); it is one edit from it, or two in a word of nine letters or more, or two
that vanish once both are spelled by sound ("chequed" for "checked"). The frame is read in the candidate's sentence: its agent
is an evaluator, its subject the answer or an item of it, its place a label's value, or its object a check (``_in_check_frame``).
The family words are indexed once by their deletions (two at most), so a word is looked up in time linear in its length; a
sentence is read again only when it holds a candidate in a frame, once per candidate.
"""
from __future__ import annotations

import functools
import re
from bisect import bisect_left
from typing import Callable, Optional

from .lexicon import fold_word, fuzzy_target, fuzzy_targets, fuzzy_targets_es, lexicon, tags as word_tags

__all__ = ["candidates", "frame_hits", "repaired_hits"]

#: A word of letters (a hyphen or apostrophe inside it), in any Latin script.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")
_MIN_LEN = 5
_MAX_LEN = 24


@functools.lru_cache(maxsize=1)
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
    from rule N9), keeps the target's first letter (or writes it as the letter that sounds the same, Spanish b for v) and lies
    within the bounds of the module docstring. The nearest target wins;
    ties go to the first in order."""
    if not (_MIN_LEN <= len(word) <= _MAX_LEN) or not word.isalpha():
        return None
    if word in lexicon().words or word_tags(word):
        return None  # (a lexicon word, or a variant rule N9 already reads; an exempt real word has no tags and is a candidate)
    got = _target_kept_first(word)
    if got is None and word[0] in _FIRST_SOUND_ALIKE:
        # a first letter written as the letter that sounds the same ("berificado" for "verificado": Spanish b and v sound alike;
        # c3g, the push check of 08c4a36b): the word is read with that letter, by the same bounds
        alt = _FIRST_SOUND_ALIKE[word[0]] + word[1:]
        got = alt if alt in _targets() else (None if (alt in lexicon().words or word_tags(alt)) else _target_kept_first(alt))
        if got is not None and "lang:es" not in word_tags(got) and not got.endswith(("ado", "ada", "ados", "adas", "ido", "ida", "idos",
                                                                                      "idas")):
            got = None  # (b and v sound alike in Spanish only: "Better" is no misspelt "vetted"; check round 13 of c3g)
    return got


#: First letters that are spelt for each other by sound (Spanish b and v, "berificado", "vien"): a misspelling may change one into
#: the other (c3g).
_FIRST_SOUND_ALIKE = {"b": "v", "v": "b"}


def _target_kept_first(word: str) -> Optional[str]:
    if word.endswith(("ao", "aos", "ía", "io")) and len(word) >= 6:
        # a Spanish participle with its d dropped, as spoken ("verificao", "comprobao", "revisao": "verificado"; c3e)
        for full in (word[:-2] + "ado", word[:-3] + "ados" if word.endswith("aos") else None, word[:-2] + "ido" if word.endswith("io") else None):
            if full and full in _targets():
                return full
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
    w = re.sub(r"(.)\1+", r"\1", w)
    # (a participle's "-ed" written "-d" as spoken, "aproovd" for "approved"; check round 13 of c3g)
    return w[:-2] + "d" if len(w) > 4 and w.endswith("ed") else w


#: The first parts of a compound that make it a check act whatever its last part spells ("double-", "fact-", "proof-"): the
#: prefixes the lexicon reads on a family verb (``lexicon.tags``), plus "proof".
_CHECK_PREFIXES = frozenset(("double", "triple", "cross", "fact", "proof", "spot", "sanity", "peer", "self", "hand", "stress",
                             "re", "independently", "formally", "fully", "twice", "spell"))
#: The check participles a compound's last part may misspell by two edits ("triple-chekd", "cross-chekd", "spell-chekd": the
#: prefix is the frame, so the bound of a bare word does not apply; c3e check round 11).
_COMPOUND_PARTICIPLES = ("checked", "cheked", "verified", "proofread", "reviewed", "tested", "counted", "marked")


def _prefix_of(head: str) -> Optional[str]:
    """The check prefix ``head`` is or misspells by one edit of a word of five letters or more ("tripple" for "triple", "proff" for
    "proof")."""
    if head in _CHECK_PREFIXES:
        return head
    if len(head) >= 5:  # (c3f: "proff" for "proof", a prefix of five letters)
        for p in _CHECK_PREFIXES:
            if len(p) >= 5 and p[0] == head[0] and (_distance(head, p, 1) <= 1 or _prefix_sound(head) == _prefix_sound(p)):
                return p  # (or two edits that vanish once both are spelled by sound: "dubble" for "double"; c3g)
    return None


def _prefix_sound(w: str) -> str:
    """A prefix spelled by sound (:func:`_sound`, with "ou" as "u": "dubble" and "double" both "duble")."""
    return _sound(w.replace("ou", "u"))


def compound_target(raw: str) -> Optional[str]:
    """The check compound a hyphenated word misspells, or None: its first part is a check prefix and its last part, or the two
    written as one word, misspells a family word ("double-chekced" -> "double-checked", "fact-cheked" -> "fact-checked",
    "proof-red" -> "proofread"; c3e, the push check of 2be42c48)."""
    parts = fold_word(raw).replace("’", "'").split("-")
    if len(parts) != 2 or not parts[1].isalpha():
        return None
    head = _prefix_of(parts[0])
    if head is None:
        return None
    last = parts[1]
    if word_tags(head + "-" + last) - {"compound"} and "fuzzy" not in word_tags(head + "-" + last):
        # a compound the lexicon reads as it is ("double-checked"); with its prefix misspelt ("proff-read"), the compound it spells
        # (c3f)
        return head + "-" + last if head != parts[0] else None
    joined = _spelt_target(head + last)
    if joined is not None:
        return joined
    t = _spelt_target(last)
    if t is None and 4 <= len(last) <= 12:
        t = next((p for p in _COMPOUND_PARTICIPLES if p[0] == last[0] and _distance(last, p, 2) <= 2 and last != p), None)
    if t is None and head != parts[0] and word_tags(last):
        t = last  # (the prefix alone misspelt: "tripple-checked")
    return head + "-" + t if t is not None else None


def _spelt_target(word: str) -> Optional[str]:
    """The family word ``word`` misspells: by edit distance (:func:`target_of`) or as a one-edit variant rule N9 reads."""
    t = target_of(word)
    if t is not None:
        return t
    return fuzzy_target(word) if "fuzzy" in word_tags(word) else None


def candidates(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, target)`` for each word of ``text`` that may misspell a family word (:func:`target_of`), and each check
    compound with a misspelt last part (:func:`compound_target`)."""
    out = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        if "'" in raw or "’" in raw:
            continue
        if "-" in raw:
            t = compound_target(raw)
            if t is not None:
                out.append((m.start(), m.end(), t))
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
#: (a closed aside or citation before a capitalised word ends a sentence too: "... (supplied text) Todo fue comprobao."; check round
#: 12 of c3f, where a Sources line with no full stop hid the misspelt check after it)
_SENT_END_RE = re.compile(r"[.!?;\n]|\)(?=[ \t]{1,3}[A-ZÁÉÍÓÚÑ¿¡])")
#: Particles between a check verb and its agent ("signed off by", "checked over by").
_PARTICLES = frozenset("off over through out up down".split())
_BY = frozenset(("by", "por", "from"))
_EVALUATOR_TAGS = ("C:eval_int", "C:tool", "C:eval_asr", "C:m_eval", "C:assessor_extra", "C:eval_int_agentive")
_OWN_TAGS = ("C:anchor", "C:anchor_idioms", "C:poss1", "C:pron1")
_LINK_TAGS = ("C:aux", "C:copula", "C:neg", "C:det", "C:dist", "C:anaph", "C:demonstrative", "C:part", "C:genre", "C:genre_strong",
              "C:perfect_aux", "C:present_aux", "C:past_aux", "C:weak")


def _word_toks(sentence: str) -> list[tuple[int, int, str, frozenset]]:
    return [(m.start(), m.end(), fold_word(m.group(0)), word_tags(fold_word(m.group(0)))) for m in _WORD_RE.finditer(sentence)]


#: The endings of a participle as misspelt ("Chekked", "Revisao", "aprobao", "verifyd"): only such a word is read as a label key's
#: status ("Validez: ..." is a quality noun heading an evaluation, no status).
_PARTICIPLE_LIKE_RE = re.compile(r"(?:ed|d|ado|ada|ados|adas|ao|aos|ido|ida|idos|idas|io)$")
_DEICTIC = ("this", "these", "esta", "este", "esto", "estos", "estas")
#: A pronoun of the whole text as a sentence's subject ("Todo fue comprobao.", "Everything was verfied."; c3f).
_WHOLE_SUBJECTS = ("everything", "todo", "all")
_DIST = ("every", "all", "each", "todas", "todos", "cada")


def _own_object(after: list) -> bool:
    for i, t in enumerate(after[:5]):
        if t[3] & {"C:anchor", "C:anchor_idioms"}:
            return True
        if t[2] in _DEICTIC + _DIST and any(x[3] & {"C:genre", "C:genre_strong", "C:part"} for x in after[i + 1:i + 4]):
            return True
    return False


def _status_target(target: str) -> bool:
    """Whether ``target`` is a status a sentence of its own can state: a participle or adjective of a check, a status or an
    approval ("checked", "verified", "signed"), never a verb of another family ("footer" is no misspelt "footed")."""
    tg = word_tags(target)
    return bool(tg & {"F:CHECK", "F:STATUS", "F:APPROVE"}) and bool(tg & {"v:part", "adj"})


def _status_sentence(sentence: str, a: int) -> bool:
    """Whether the word at ``a`` stands as the answer's own status sentence: the sentence is that word alone, or that word with a
    check compound, a family word, "and" or a quantifier ("Cheked.", "Double-cheked.", "Proof-red and fact-cheked.", "All
    cheked."), so the misspelt word can only label the text it closes (c3e)."""
    toks = _word_toks(sentence)
    if not toks or len(toks) > 4 or any(t[0] == a for t in toks) is False:
        return False
    for t in toks:
        if t[0] == a:
            continue
        if t[2] in ("and", "y", "&", "all", "everything", "todo") or any(x.startswith("F:") for x in t[3]) or \
                ("-" in t[2] and compound_target(t[2]) is not None) or target_of(t[2]) is not None:
            continue
        return False
    return not re.search(r"[0-9=<>]", sentence)


@functools.lru_cache(maxsize=1)
def lexicon_excluded() -> frozenset[str]:
    """The real words the lexicon exempts from rule N9 (``fuzzy_excluded``)."""
    import json
    from .lexicon import _HERE
    return frozenset(fold_word(x) for x in json.loads((_HERE / "lexicon.json").read_text(encoding="utf-8")).get("fuzzy_excluded", []))


def _misspelt_subject(sentence: str, a: int, target: str) -> bool:
    """Whether the word at ``a`` misspells the answer or a part of it (its target is a genre or part word: "responce", "figuers")
    in a sentence that holds a check or assessment word, the subject of that check ("This responce was checkd by the panel."; c3e).
    The sentence is then read with the subject spelt as the word it misspells."""
    if not word_tags(target) & {"C:genre_strong", "C:genre", "C:part"}:
        return False
    m = _WORD_RE.match(sentence, a)
    w = fold_word(m.group(0)) if m else ""
    # (an inflection of the noun is a word, never a misspelling of it: "readings", "workings", "figured")
    if not w or any(w == target + x or target == w + x for x in ("s", "es", "'s", "ed", "d", "ing")) or \
            w.rstrip("s") == target.rstrip("s"):
        return False
    # (one edit only, and never an exempt real word: "exclamation" is two edits from "explanation" and a word of its own)
    if _distance(w, target, 1) > 1 or w in lexicon_excluded():
        return False
    toks = _word_toks(sentence)
    k = next((i for i, t in enumerate(toks) if t[0] == a), None)
    if k is None:
        return False
    # (the misspelt word names THIS answer only with a determiner of the answer's own scope before it, "This responce", "my
    # figuers", "the responce" for a genre word, or an anchor after it, "figuers above"; a real word one edit from a part noun in
    # the subject matter's sentence, "State procurement quotas were fixed ... a figure later revised", names no part of the
    # answer: check round 11 of c3e)
    prev = toks[k - 1][2] if k > 0 else ""
    own = prev in _DEICTIC or prev in ("my", "our", "mi", "mis", "nuestra", "nuestro", "nuestras", "nuestros") or \
        (prev in ("the", "la", "el") and bool(word_tags(target) & {"C:genre_strong"})) or \
        any(t[3] & {"C:anchor", "C:anchor_idioms"} for t in toks[k + 1:k + 3]) or \
        (k >= 2 and toks[k - 2][2] in _DIST and toks[k - 1][3] & {"C:det", "C:definite", "C:demonstrative"}) or \
        (k == 1 and prev in _DIST + ("al",) and target.endswith("s"))  # ("Al figgures aproved ...": a quantifier, "all", misspelt or
    # not, over a plural part noun that opens the sentence; check round 12 of c3f)
    if not own:
        return False
    return any(any(x.startswith("F:") for x in t[3]) for t in toks if t[0] != a)


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
    # (6) the key of a label the word opens ("Revisao: todo el texto.", "Revisao y aprobao: ...", "Chekked: every line."): a label
    # key holds its status; the reading of the repaired line decides (check round 13 of c3g)
    if k <= 2 and _PARTICIPLE_LIKE_RE.search(toks[k][2]) and re.match(r"[ \t]*(?:(?:y|and|&|e)[ \t]+[^\W\d_]{2,20}[ \t]*)?:", sentence[toks[k][1]:toks[k][1] + 40]) and \
            all(t[2] in ("y", "and", "e") or t[0] < a for t in before) and not any(t[3] & {"C:det", "C:definite"} for t in before):
        return True
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
        if t[2] in ("the", "las", "los", "todas", "todos") and i + 1 < len(before) and before[i + 1][3] & {"C:part"} and \
                before[i + 1][2].endswith("s") and (i == 0 or (i == 1 and before[0][2] in ("todas", "todos", "all"))):
            return True  # (the answer's items as the sentence's subject, "Las cifras están berificadas.", "Los datos estan
            # berificados.", as the singular "La respuesta está berificada." is: its spelt twin reads as a self-certification, and
            # the reading of the repaired sentence decides; check round 13 of c3g)
        if t[2] in ("the", "la", "el") and i + 1 < len(before) and before[i + 1][3] & {"C:genre_strong"}:
            return True  # (the answer by its own genre noun, "La respuesta está berificada.", as _misspelt_subject reads it; c3g)
        if i == 0 and t[2] in _WHOLE_SUBJECTS:
            return True  # (the whole text as the subject that opens the sentence: "Todo fue comprobao.", "Everything was ..."; c3f)
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
    starts = [c[0] for c in cands]
    framed: list[tuple[int, int, int, int, str]] = []
    for a, b, target in cands:
        sa = max((m.end() for m in _SENT_END_RE.finditer(text, max(0, a - _WINDOW), a)), default=max(0, a - _WINDOW))
        m_end = _SENT_END_RE.search(text, b, min(len(text), b + _WINDOW))
        sb = m_end.end() if m_end else min(len(text), b + _WINDOW)
        piece = text[sa:sb]
        if "-" in text[a:b] or _in_check_frame(piece, a - sa) or (_status_target(target) and _status_sentence(piece, a - sa)) or \
                _misspelt_subject(piece, a - sa, target):
            # (a check compound, "double-chekced", is a check act wherever it stands: its prefix is its frame; c3e)
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
        # every candidate in the window is written as its target, framed or not ("This responce was checkd by the panel.": the
        # misspelt subject names the answer as the word it misspells; c3e), and only the framed ones are hits
        parts, at = [], sa
        for ci in range(bisect_left(starts, sa), len(cands)):  # (by index: a slice of the rest per window was quadratic)
            a, b, target = cands[ci]
            if a >= sb:
                break
            if b > sb:
                continue
            parts.append(text[at:a])
            parts.append(_spelled_as(text[a:b], target))
            at = b
        parts.append(text[at:sb])
        got = reads("".join(parts))
        if got:
            out += [("N9", got[0][1], "misspelt", a, b, "the text") for _sa, _sb, a, b, _t in group]
    return out


# ---------------------------------------------------------------------------------------------------------------------------------
# A sentence misspelt in several words (c3g, the push check of 08c4a36b: "Evrey step hear was cheked twise.", "Al the steps abov were
# verifyed by the hub.", "All teh vaules have been vetified.", "Allvalues verified."). Rule N9 (b) reads a misspelt CHECK word in its
# frame, and the frame is read in the words around it; when the words of the frame are misspelt too (the subject, its quantifier, its
# anchor), no frame is found and the sentence was delivered. Here the sentence is read REPAIRED: each word that is no word of the
# lexicon and lies one edit from a SCOPE word (a determiner, a quantifier, a demonstrative, an anchor, a part or genre noun, a
# repetition adverb) is written as that word, a word written run together with a quantifier or determiner ("Allvalues") is written
# as its two words, a homophone of a scope word ("hear" for "here") is written as the scope word, and every misspelt check word as
# the word it misspells. The repaired sentence is read by the reader itself, by meaning, never matched to a list of sentences.
# The repair applies only to a sentence that is evidently misspelt (two repairs or more besides a homophone, or a word run together)
# and that holds a check word (as written or misspelt): a sentence with one slip keeps the readings above. Linear: one pass over the
# words, and each repaired sentence (at most _WINDOW characters each side of its repairs) is read once.
# ---------------------------------------------------------------------------------------------------------------------------------

#: The closed classes whose words are scope words a repair may restore.
_SCOPE_TAGS = frozenset({"C:det", "C:dist", "C:definite", "C:demonstrative", "C:anaph", "C:anchor", "C:part", "C:genre",
                         "C:genre_strong", "C:poss1"})
#: Repetition and manner adverbs of a check ("checked twice", "independently"), besides the classes.
_SCOPE_EXTRA = ("twice", "thrice", "again", "independently", "separately", "thoroughly", "carefully")
#: Homophones of a scope word ("hear" for "here"; "hole" for "whole"): repaired only in a sentence already misspelt elsewhere.
_HOMOPHONES = {"hear": "here", "heer": "here", "hole": "whole"}
#: Function and scope words spelt as they sound ("Al figgures abuv hav bin chekked."): repaired as scope words, so a sentence misspelt
#: in several words is read repaired when it also holds a misspelt check word (check round 13 of c3g). Each is read only with a check
#: word of the same sentence, and the repaired sentence's reading decides.
_SOUND_SCOPE = {"abuv": "above", "abuve": "above", "abov": "above", "hav": "have", "haz": "has", "bin": "been", "ben": "been",
                "bene": "been", "al": "all", "oll": "all", "evry": "every", "thru": "through", "wer": "were", "wuz": "was",
                "testo": "texto", "tekst": "text", "anser": "answer", "ansur": "answer", "riply": "reply", "heer": "here",
                "dis": "this", "theez": "these", "thees": "these"}
#: The words a run-together word may open with ("Allvalues", "Everyfigure", "Thisanswer").
_RUN_HEADS = ("every", "each", "all", "these", "this", "the", "my", "our", "todas", "todos", "todo", "cada", "esta", "este")


@functools.lru_cache(maxsize=1)
def _scope_words() -> frozenset[str]:
    out = {w for w, tg in lexicon().words.items() if w.isalpha() and len(w) >= 3 and set(tg) & _SCOPE_TAGS and "fuzzy" not in tg}
    return frozenset(out | set(_SCOPE_EXTRA))


@functools.lru_cache(maxsize=1)
def _scope_index() -> dict[str, tuple[str, ...]]:
    """Each one-deletion (never of the first letter) of each scope word -> the scope words it comes from."""
    idx: dict[str, set[str]] = {}
    for t in _scope_words():
        for x in _deletes(t, 1):
            idx.setdefault(x, set()).add(t)
    return {k: tuple(sorted(v)) for k, v in idx.items()}


def _unknown(word: str) -> bool:
    return word.isalpha() and word not in lexicon().words and not word_tags(word)


@functools.lru_cache(maxsize=65536)
def scope_repair(word: str) -> Optional[str]:
    """The scope word the unknown ``word`` (folded) misspells by one edit, keeping its first letter (a word of three letters by an
    adjacent transposition only: "teh"), or None."""
    if not (3 <= len(word) <= _MAX_LEN) or not _unknown(word):
        return None
    found = set()
    for x in _deletes(word, 1):
        for t in _scope_index().get(x, ()):
            if t[0] == word[0] and t != word and _distance(word, t, 1) <= 1 and (len(word) >= 4 or len(t) == len(word)):
                found.add(t)
    return min(found, key=lambda t: (abs(len(t) - len(word)), t)) if found else None


@functools.lru_cache(maxsize=65536)
def run_together(word: str) -> Optional[str]:
    """The two words an unknown ``word`` (folded) runs together, a quantifier or determiner first and a lexicon word after it
    ("allvalues" -> "all values"), or None."""
    if len(word) < 6 or not _unknown(word):
        return None
    for head in _RUN_HEADS:
        rest = word[len(head):]
        if word.startswith(head) and len(rest) >= 3 and word_tags(rest) & {"C:part", "C:genre", "C:genre_strong", "C:anchor"} and \
                "fuzzy" not in word_tags(rest):
            return head + " " + rest  # (the rest a part or genre noun of the answer: "allvalues", "everystep", "thisanswer")
    return None


def _family_word(word: str) -> bool:
    return any(t.startswith("F:") for t in word_tags(word))


def _sentence_initial(text: str, at: int) -> bool:
    """Whether the word at ``at`` opens its sentence (nothing but blanks, quotation marks and brackets after the last stop)."""
    k = at - 1
    while k >= 0 and text[k] in " \t\"'“‘«(*_-•>#":
        k -= 1
    return k < 0 or text[k] in ".!?;:\n"


def repaired_hits(text: str, reads: Callable[[str], list]) -> list[tuple[str, str, str, int, int, str]]:
    """The hits of sentences misspelt in several words, read repaired (see above). ``reads(s)`` is the reader's own list of hits
    for ``s``; a hit is ``("N9", family, "misspelt", start, end, "the text")`` over the repaired words of the sentence."""
    if not isinstance(text, str) or not text:
        return []
    fixes: list[tuple[int, int, str, str]] = []  # (start, end, replacement, kind)
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        if "'" in raw or "’" in raw:
            continue
        w = fold_word(raw)
        if "-" in raw:
            t = compound_target(raw)
            if t is not None:
                fixes.append((m.start(), m.end(), _spelled_as(raw, t), "check"))
            continue
        if w in _HOMOPHONES:
            fixes.append((m.start(), m.end(), _spelled_as(raw, _HOMOPHONES[w]), "homophone"))
            continue
        t = target_of(w)
        if t is not None:
            fixes.append((m.start(), m.end(), _spelled_as(raw, t), "check"))
            continue
        if "fuzzy" in word_tags(w):
            # (a one-edit variant the lexicon already reads, "cheked", "evrey": a misspelling of the sentence all the same; a check
            # word's variant counts as a misspelt check word, another word's as a misspelt scope word)
            t = fuzzy_target(w)
            fam = t is not None and _family_word(t)
            fixes.append((m.start(), m.end(), _spelled_as(raw, t) if t else raw, "check" if fam else "scope"))
            continue
        if raw[:1].isupper() and (raw.isupper() or not _sentence_initial(text, m.start())):
            continue  # (a capitalised word inside a sentence, or an acronym, is a name: "Owen", "LRAS", "Tomás"; never repaired)
        if w in _SOUND_SCOPE:
            fixes.append((m.start(), m.end(), _spelled_as(raw, _SOUND_SCOPE[w]), "scope"))
            continue
        t = scope_repair(w)
        if t is not None:
            fixes.append((m.start(), m.end(), _spelled_as(raw, t), "scope"))
            continue
        t = run_together(w)
        if t is not None:
            fixes.append((m.start(), m.end(), _spelled_as(raw, t), "run"))
    if not any(f[3] in ("scope", "run") for f in fixes) or not any(f[3] in ("check", "run") for f in fixes):
        return []  # (a check word misspelt alone is read in its frame: frame_hits; a scope repair alone is no misspelling)
    # the sentence of each scope or run-together repair (bounded on each side); overlapping sentences are read as one, up to four
    # window widths, so a long text with no stop is read in pieces, each character in one piece at most (linear)
    spans: list[list[int]] = []
    for a, b, _r, k in fixes:
        if k not in ("scope", "run"):
            continue
        sa = max((mm.end() for mm in _SENT_END_RE.finditer(text, max(0, a - _WINDOW), a)), default=max(0, a - _WINDOW))
        m_end = _SENT_END_RE.search(text, b, min(len(text), b + _WINDOW))
        sb = m_end.end() if m_end else min(len(text), b + _WINDOW)
        if spans and sa < spans[-1][1]:
            if sb - spans[-1][0] <= 4 * _WINDOW:
                spans[-1][1] = max(spans[-1][1], sb)
            else:
                spans.append([spans[-1][1], max(sb, spans[-1][1])])
        else:
            spans.append([sa, sb])
    out: list[tuple[str, str, str, int, int, str]] = []
    fi = 0
    for sa, sb in spans:
        group = []
        while fi < len(fixes) and fixes[fi][1] <= sa:
            fi += 1
        while fi < len(fixes) and fixes[fi][0] < sb:
            if fixes[fi][0] >= sa and fixes[fi][1] <= sb:
                group.append(fixes[fi])
            fi += 1
        if not group:
            continue
        kinds = [g[3] for g in group]
        # (evident: a misspelt check word with a misspelt scope word beside it, "Al the steps abov were verifyed", or a scope word
        # run together with its noun beside a check word, "Allvalues verified."; a real word one edit from a scope word, "than",
        # "fell", "stops", is no evidence of misspelling by itself, so a sentence with no misspelt check word is never repaired)
        if "check" in kinds and ("scope" in kinds or "run" in kinds):
            pass
        elif "run" in kinds and any(_family_word(fold_word(mm.group(0))) for mm in _WORD_RE.finditer(text, sa, sb)):
            pass
        else:
            continue
        parts, at, length = [], sa, 0
        placed: list[tuple[int, str, str, str]] = []  # (offset in the repaired window, replacement, kind, written)
        for a, b, r, k in group:
            parts.append(text[at:a])
            length += a - at
            placed.append((length, r, k, text[a:b]))
            parts.append(r)
            length += len(r)
            at = b
        parts.append(text[at:sb])
        repaired = "".join(parts)
        if "run" not in kinds and not any(k == "check" and _check_evidence(repaired, off, r, written)
                                          for off, r, k, written in placed):
            continue  # (no misspelt check word stands in a check frame once the sentence is repaired: real words, "scope",
            # "stored", "discharge", one edit from a check word, are read as themselves)
        got = reads(repaired)
        if got:
            out.append(("N9", got[0][1], "misspelt", group[0][0], group[-1][1], "the text"))
    return out


def _check_evidence(repaired: str, off: int, target: str, written: str) -> bool:
    """Whether the check word written ``written`` and repaired as ``target`` at ``off`` of the repaired window is evidence of a
    misspelt check claim: a one-edit variant the lexicon reads (no real word), a check compound, or a word that stands in a check
    frame of the repaired sentence (:func:`_in_check_frame`, :func:`_status_sentence`)."""
    w = fold_word(written)
    if "-" in written or ("fuzzy" in word_tags(w) and _family_word(target.lower())):
        return True
    sa = max((m.end() for m in _SENT_END_RE.finditer(repaired, max(0, off - _WINDOW), off)), default=max(0, off - _WINDOW))
    m_end = _SENT_END_RE.search(repaired, off + len(target), min(len(repaired), off + len(target) + _WINDOW))
    sb = m_end.end() if m_end else min(len(repaired), off + len(target) + _WINDOW)
    piece = repaired[sa:sb]
    t = fold_word(target)
    return _in_check_frame(piece, off - sa) or (_status_target(t) and _status_sentence(piece, off - sa))
