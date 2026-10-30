"""The one tokenizer every lexical rule of the argument diagnosis uses (rules ``argdiag-2``).

Labels, meanings, claims, requests and supplied texts are read only as strings, and only through these functions:

* :func:`tokens` / :func:`token_spans`: lower-case words and numbers, found by one linear scan over the characters (no
  regular expression at all). A word is a run of letters (combining marks included) that may hold an apostrophe between
  letters ("don't", "palmer's"); a number is a run of decimal digits that may hold a "." or "," between digits ("2.5",
  "1,800"). Every other character, a hyphen included, separates tokens ("non-random" is "non", "random");
* :func:`stem`: a light, closed stemmer. A possessive is dropped; a negating prefix (``un``, ``in``, ``im``, ``il``,
  ``ir``, ``non``, ``dis``) is dropped before an ``-able``, ``-ible``, ``-ful`` or ``-ent`` stem whose root has 4 or more
  letters (never before ``-ment``); then ``-ied`` becomes ``y``, or the first of ``-able``, ``-ible``, ``-ing``, ``-ed``,
  ``-es``, ``-ly``, ``-s`` that leaves enough of the word is stripped, and a final ``i`` left by the strip becomes ``y``.
  So "relied", "relies", "reliable" and "unreliable" share the stem "rely" (the last one negated: :func:`negated`).
  Guards keep short words whole: a strip must leave 4 letters (5 for ``-ly``, so "family" is not "fami"), and ``-s`` is
  not stripped after ``s``, ``u`` or ``i`` ("class", "status", "analysis");
* :func:`root`: a coarser, closed root for readings that compare two texts word by word: irregular forms, the light
  stem and closed derivational suffixes ("driven" and "drives", "stability" and "stable" share one);
* :func:`content_stems`: the stems of a text's tokens without its function words, its frame words and phrases (the
  words a paraphrase may add without adding content: "is", "true", "the fact that") and its negation words, in order
  of first appearance and without repeats;
* :func:`has_cue` / :func:`find_cues`: a token-sequence match of a closed cue table on word boundaries, linear in the
  input for a fixed table (each table is indexed by its first token; ``*`` in a cue matches any one token);
* :func:`negated`: whether a token sequence is negated: an odd number of negation markers (``not``, ``no``,
  ``never``, ``cannot``, ``nor``, a contraction ending in ``n't``, a standalone ``non`` and a word whose negating
  prefix :func:`stem` drops). Two markers cancel ("not unreliable").

The tables of this module are data and a unit test pins each of them. The cue tables of the rules stay with their owners
(the engine's argument cues, the evidence rules, the STEM reference data, the channel's cues); this module only matches
them. Nothing here evaluates or executes text. Inputs are bounded by the schemas that carry them (labels and meanings at
most 1,000 characters, claims at most 4,000, supplied texts at most 400,000), and every function is linear in its input.

This module imports neither z3 nor the engine package, so receipts, translation records and the overseer can read text
the same way where Z3 is absent.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Iterable, Mapping, Sequence, Union

__all__ = [
    "FUNCTION_WORDS", "FRAME_WORDS", "FRAME_PHRASES", "NEGATION_WORDS", "NEGATING_PREFIXES", "NEGATABLE_SUFFIXES",
    "NOT_NEGATED", "STRIPPED_SUFFIXES", "IRREGULAR_FORMS", "DERIVATIONAL_SUFFIXES", "WILDCARD",
    "CueTable", "cue_table", "token_spans", "tokens", "stem", "root", "content_stems", "find_cues", "has_cue",
    "negation_markers", "negation_words", "negated",
]

#: Closed-class words (articles, determiners, quantifiers, pronouns, prepositions, conjunctions, connectives, auxiliaries
#: and modals) that carry no content of their own. They stay tokens (a cue table can still match them); only
#: :func:`content_stems` leaves them out.
FUNCTION_WORDS: frozenset[str] = frozenset("""
a an the this that these those such
some any each every all both either neither one two three much many more most less least few several
it its itself they them their theirs themselves he him his himself she her hers herself we us our ours ourselves
you your yours yourself yourselves i me my mine myself who whom whose which what when where how why whether
of to in on at by for from with into onto over under about after before during while within via per through
throughout across along among between against toward towards upon off out up down near than
and or but if then so also only just very too even yet because since therefore thus hence although though whereas
however
is are was were be been being am
do does did done doing has have had having
can could may might must shall should will would
there here
""".split())

#: Single frame words: what a paraphrase may add to a statement without adding content ("it is true that ...").
FRAME_WORDS: frozenset[str] = frozenset({"be", "is", "are", "was", "cannot", "upon", "shown", "true", "indeed", "really", "clearly"})
#: Frame phrases, matched as token sequences before single words are read.
FRAME_PHRASES: tuple[tuple[str, ...], ...] = (("can", "not"), ("the", "fact", "that"), ("in", "fact"))

#: Words that negate on their own. A contraction ending in "n't" and a standalone "non" negate too (:func:`negation_markers`).
NEGATION_WORDS: frozenset[str] = frozenset({"not", "no", "never", "cannot", "nor"})
#: Prefixes that negate a word whose remainder ends in one of :data:`NEGATABLE_SUFFIXES` (longest first).
NEGATING_PREFIXES: tuple[str, ...] = ("non", "dis", "un", "in", "im", "il", "ir")
#: The suffixes after which a negating prefix negates: "unreliable", "impossible", "unfaithful", "inconsistent".
NEGATABLE_SUFFIXES: tuple[str, ...] = ("able", "ible", "ful", "ent")
#: Words of the negating shape that are not negations ("intelligent" is not "not telligent").
NOT_NEGATED: frozenset[str] = frozenset({"intelligent", "insistent", "indulgent", "ingredient", "incandescent", "insurgent"})
#: The suffixes :func:`stem` strips, in the order tried (after the ``-ied`` rule); the first that applies is stripped.
STRIPPED_SUFFIXES: tuple[str, ...] = ("able", "ible", "ing", "ed", "es", "ly", "s")
#: Irregular verb forms and a few derived forms, read as their base form by :func:`root`.
IRREGULAR_FORMS: dict[str, str] = {
    "driven": "drive", "drove": "drive", "written": "write", "wrote": "write", "taken": "take", "took": "take", "given": "give",
    "gave": "give", "shown": "show", "known": "know", "knew": "know", "risen": "rise", "rose": "rise", "fallen": "fall", "fell": "fall",
    "chosen": "choose", "chose": "choose", "broken": "break", "broke": "break", "spoken": "speak", "spoke": "speak", "begun": "begin",
    "began": "begin", "seen": "see", "saw": "see", "made": "make", "led": "lead", "held": "hold", "kept": "keep", "lost": "lose",
    "won": "win", "brought": "bring", "thought": "think", "caught": "catch", "taught": "teach", "bought": "buy", "sought": "seek",
    "felt": "feel", "left": "leave", "meant": "mean", "built": "build", "sent": "send", "spent": "spend", "grew": "grow", "grown": "grow",
    "threw": "throw", "thrown": "throw", "drew": "draw", "drawn": "draw", "came": "come", "went": "go", "gone": "go", "got": "get",
    "gotten": "get", "ran": "run", "stood": "stand", "understood": "understand", "became": "become", "fought": "fight", "struck": "strike",
    "hid": "hide", "hidden": "hide", "forgot": "forget", "forgotten": "forget", "fed": "feed", "fled": "flee", "flew": "fly", "flown": "fly",
    "froze": "freeze", "frozen": "freeze", "paid": "pay", "said": "say", "sold": "sell", "told": "tell", "wore": "wear", "worn": "wear",
    "tore": "tear", "torn": "tear", "woke": "wake", "woken": "wake", "overthrew": "overthrow", "overthrown": "overthrow",
    "undertook": "undertake", "undertaken": "undertake", "succeeded": "success", "succeed": "success", "succeeds": "success",
    "failed": "fail", "failure": "fail", "fails": "fail", "achievement": "achieve", "achievements": "achieve",
}
#: Derivational suffixes :func:`root` reads off a stem, in this order and repeatedly, while at least four letters remain
#: (each with its replacement): "stability" is "stable", "politically" and "politics" are "polit", "successful" is
#: "success".
DERIVATIONAL_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("ibility", "ible"), ("ability", "able"), ("ically", "ic"), ("ality", "al"), ("ivity", "ive"), ("iness", "y"), ("ness", ""),
    ("ment", ""), ("ity", ""), ("fully", "ful"), ("ful", ""), ("ally", "al"), ("ical", "ic"), ("ous", ""), ("ive", ""), ("ion", ""),
    ("al", ""), ("ic", ""), ("ly", ""),
)
#: A cue token that matches any one token.
WILDCARD = "*"

_APOSTROPHES = frozenset("'’")
_NUMBER_JOINERS = frozenset(".,")
#: Letters a strip must leave (``-ly`` needs one more, so "family" and "supply" stay whole).
_MIN_STEM = 4
_MIN_STEM_LY = 5
#: The root a negating prefix needs before its suffix ("un" + "reli" + "able").
_MIN_NEGATED_ROOT = 4


def _is_letter(ch: str) -> bool:
    return ch.isalpha() or unicodedata.category(ch).startswith("M")


#: Texts up to this length have their tokens kept in a bounded cache: labels, meanings and claims are read by several rules
#: (repair round 2, ADV2-03: the same short texts were tokenized tens of thousands of times in one corpus run).
_CACHED_TEXT_MAX = 8192


def token_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    """``(start, end, token)`` for every word and number of ``text`` in order (module docstring); ``token`` is lower-case
    (case-folded, with a typographic apostrophe written as ``'``). Character offsets refer to ``text`` itself. One pass,
    linear in ``len(text)``; a text of at most :data:`_CACHED_TEXT_MAX` characters is read once (a bounded cache)."""
    if not isinstance(text, str) or not text:
        return ()
    if len(text) <= _CACHED_TEXT_MAX:
        return _cached_token_spans(text)
    return _token_spans(text)


@lru_cache(maxsize=16384)
def _cached_token_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    return _token_spans(text)


def _token_spans(text: str) -> tuple[tuple[int, int, str], ...]:
    out: list[tuple[int, int, str]] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _is_letter(ch):
            j = i + 1
            while j < n:
                c = text[j]
                if _is_letter(c):
                    j += 1
                elif c in _APOSTROPHES and j + 1 < n and _is_letter(text[j + 1]):
                    j += 2
                else:
                    break
            out.append((i, j, text[i:j].casefold().replace("’", "'")))
            i = j
        elif ch.isdecimal():
            j = i + 1
            while j < n:
                c = text[j]
                if c.isdecimal():
                    j += 1
                elif c in _NUMBER_JOINERS and j + 1 < n and text[j + 1].isdecimal():
                    j += 2
                else:
                    break
            out.append((i, j, text[i:j]))
            i = j
        else:
            i += 1
    return tuple(out)


def tokens(text: str) -> tuple[str, ...]:
    """The lower-case words and numbers of ``text`` in order (:func:`token_spans` without the offsets)."""
    return tuple(t for _s, _e, t in token_spans(text))


def _as_tokens(seq: Union[str, Sequence[str], Iterable[str]]) -> tuple[str, ...]:
    if isinstance(seq, str):
        return tokens(seq)
    return tuple(str(t).casefold() for t in seq)


def _without_possessive(word: str) -> str:
    if word.endswith("'s"):
        return word[:-2]
    if word.endswith("'"):
        return word[:-1]
    return word


def _negating_prefix(word: str) -> str:
    """The negating prefix of ``word`` ("" when it has none): the prefix is followed by a remainder ending in a
    negatable suffix (never ``-ment``) whose root has at least 4 letters."""
    if word in NOT_NEGATED:
        return ""
    for prefix in NEGATING_PREFIXES:
        if not word.startswith(prefix):
            continue
        rest = word[len(prefix):]
        if rest.endswith("ment"):
            return ""
        for suffix in NEGATABLE_SUFFIXES:
            if rest.endswith(suffix) and len(rest) - len(suffix) >= _MIN_NEGATED_ROOT:
                return prefix
        return ""
    return ""


def _strip_suffix(word: str) -> str:
    if len(word) >= 6 and word.endswith("ied"):
        return word[:-3] + "y"
    for suffix in STRIPPED_SUFFIXES:
        if not word.endswith(suffix):
            continue
        keep = len(word) - len(suffix)
        if keep < (_MIN_STEM_LY if suffix == "ly" else _MIN_STEM):
            continue
        if suffix == "s" and word[-2] in "sui":
            continue
        root = word[:keep]
        return root[:-1] + "y" if root.endswith("i") else root
    return word


def stem(word: str) -> str:
    """The light stem of one word (module docstring). Numbers and words with an inner apostrophe that is not a possessive
    ("don't") are returned lower-cased and otherwise unchanged. A pure function of the word over the closed tables, so it
    is cached (repair round 5, ADV5-13: the argument and grounding readings stem the same words many times)."""
    return _stem(str(word))


@lru_cache(maxsize=65536)
def _stem(word: str) -> str:
    w = _without_possessive(word.casefold().replace("’", "'"))
    if not w or not w.isalpha():
        return w
    prefix = _negating_prefix(w)
    if prefix:
        w = w[len(prefix):]
    return _strip_suffix(w)


_PLURAL_KEEP = ("ss", "us", "is")


def root(word: str) -> str:
    """The concept root of one word, for readings that compare two texts word by word (the paraphrase reading of
    ARG-CIRC-003, the rule reading of a grounding check): its base form (:data:`IRREGULAR_FORMS`), its light stem
    (:func:`stem`), a plural "s" a short stem kept dropped, the closed derivational suffixes (:data:`DERIVATIONAL_SUFFIXES`)
    read off repeatedly while four letters remain, and a final "e" or "y" dropped from a root of five letters or more.
    "drives", "driven" and "drove"; "stability" and "stable"; "political", "politics" and "politically"; "successful"
    and "succeeded" each share one root. A number is returned as it is. Linear in the word, and cached like :func:`stem`."""
    return _root(str(word))


@lru_cache(maxsize=65536)
def _root(word: str) -> str:
    w = _without_possessive(word.casefold().replace("’", "'"))
    w = IRREGULAR_FORMS.get(w, w)
    s = stem(w) if w.isalpha() else w
    if not s.isalpha():
        return s
    if len(s) >= 4 and s.endswith("s") and not s.endswith(_PLURAL_KEEP):
        s = s[:-1]
    changed = True
    while changed:
        changed = False
        for suffix, replacement in DERIVATIONAL_SUFFIXES:
            if s.endswith(suffix) and len(s) - len(suffix) + len(replacement) >= 4:
                s = s[: len(s) - len(suffix)] + replacement
                changed = True
                break
    if len(s) >= 5 and s[-1] in "ey":
        s = s[:-1]
    return s


def _is_negation_token(token: str) -> bool:
    return token in NEGATION_WORDS or token.endswith("n't") or token == "non"


def content_stems(text: Union[str, Sequence[str]]) -> tuple[str, ...]:
    """The stems of the content words of ``text`` (a string or its tokens), in order of first appearance, without
    repeats: function words, frame words, frame phrases and negation words are left out (module docstring)."""
    toks = _as_tokens(text)
    out: dict[str, None] = {}
    i, n = 0, len(toks)
    while i < n:
        skip = next((len(p) for p in FRAME_PHRASES if toks[i:i + len(p)] == p), 0)
        if skip:
            i += skip
            continue
        t = toks[i]
        i += 1
        bare = _without_possessive(t)
        if t in FUNCTION_WORDS or bare in FUNCTION_WORDS or t in FRAME_WORDS or _is_negation_token(t):
            continue
        s = stem(t)
        if s:
            out.setdefault(s, None)
    return tuple(out)


@dataclass(frozen=True)
class CueTable:
    """A closed cue table, indexed by first token (:func:`cue_table`). ``phrases`` keeps the table's order."""
    phrases: tuple[tuple[str, ...], ...]
    by_first: Mapping[str, tuple[tuple[str, ...], ...]]
    wild_first: tuple[tuple[str, ...], ...]


def cue_table(phrases: Iterable[Union[str, Sequence[str]]]) -> CueTable:
    """Build a :class:`CueTable` from phrases (``"led to"``) or token sequences (``("led", "to")``). Each phrase is read
    with :func:`tokens`, except that ``*`` stays a wildcard token; empty phrases are ignored."""
    seqs: list[tuple[str, ...]] = []
    for p in phrases:
        parts: list[str] = []
        for part in (p.split() if isinstance(p, str) else [str(x) for x in p]):
            if part == WILDCARD:
                parts.append(WILDCARD)
            else:
                parts.extend(tokens(part))
        seq = tuple(parts)
        if seq and seq not in seqs:
            seqs.append(seq)
    by_first: dict[str, list[tuple[str, ...]]] = {}
    wild: list[tuple[str, ...]] = []
    for seq in seqs:
        (wild if seq[0] == WILDCARD else by_first.setdefault(seq[0], [])).append(seq)
    return CueTable(phrases=tuple(seqs), by_first=MappingProxyType({k: tuple(v) for k, v in by_first.items()}), wild_first=tuple(wild))


def _table(table: Union[CueTable, Iterable[Union[str, Sequence[str]]]]) -> CueTable:
    return table if isinstance(table, CueTable) else cue_table(table)


def _matches_at(toks: tuple[str, ...], i: int, seq: tuple[str, ...]) -> bool:
    if i + len(seq) > len(toks):
        return False
    return all(c == WILDCARD or c == toks[i + k] for k, c in enumerate(seq))


def find_cues(text_or_tokens: Union[str, Sequence[str]], table: Union[CueTable, Iterable[Union[str, Sequence[str]]]]) -> tuple[tuple[int, tuple[str, ...]], ...]:
    """Every ``(token index, cue)`` where a cue of ``table`` matches, in order of position (then table order)."""
    toks = _as_tokens(text_or_tokens)
    t = _table(table)
    out: list[tuple[int, tuple[str, ...]]] = []
    for i, tok in enumerate(toks):
        for seq in t.by_first.get(tok, ()) + t.wild_first:
            if _matches_at(toks, i, seq):
                out.append((i, seq))
    return tuple(out)


def has_cue(text_or_tokens: Union[str, Sequence[str]], table: Union[CueTable, Iterable[Union[str, Sequence[str]]]]) -> bool:
    """Whether any cue of ``table`` matches ``text_or_tokens`` on word boundaries (module docstring)."""
    toks = _as_tokens(text_or_tokens)
    t = _table(table)
    for i, tok in enumerate(toks):
        for seq in t.by_first.get(tok, ()) + t.wild_first:
            if _matches_at(toks, i, seq):
                return True
    return False


def negation_markers(text_or_tokens: Union[str, Sequence[str]]) -> int:
    """How many negation markers ``text_or_tokens`` holds (module docstring)."""
    count = 0
    for t in _as_tokens(text_or_tokens):
        if _is_negation_token(t):
            count += 1
            continue
        w = _without_possessive(t)
        if w.isalpha() and _negating_prefix(w):
            count += 1
    return count


def negation_words(text_or_tokens: Union[str, Sequence[str]]) -> int:
    """How many explicit negation words ``text_or_tokens`` holds ("not", "no", "never", "neither", "n't", "non"): a negating
    prefix on a word ("independent", "unbiased") is no negation word. The words that negate a clause, as opposed to a word
    that names the opposite of another (repair round 5, DA-2: "an independent-groups experiment" was read as negating the
    list of groups the sentence then states)."""
    return sum(1 for t in _as_tokens(text_or_tokens) if _is_negation_token(t))


def negated(text_or_tokens: Union[str, Sequence[str]]) -> bool:
    """True when ``text_or_tokens`` holds an odd number of negation markers: "the source is unreliable" and "the source
    is not reliable" are negated, "the source is not unreliable" is not."""
    return negation_markers(text_or_tokens) % 2 == 1
