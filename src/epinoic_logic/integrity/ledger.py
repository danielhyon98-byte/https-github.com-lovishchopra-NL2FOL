"""Claim-ledger accounting for the information-preserving combinator.

Structural accounting is necessary but not sufficient (context document, section 4):
it catches dropped, orphaned, inflated and evidence-stripped claims, id collisions
between reports and between the source and synthesis namespaces, ledger entries that
point nowhere, and student-facing text that diverges from the claim ledger. Whether a
synthesized claim FOLLOWS from its sources is a formal question answered in
``cross_check.py``.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from ..translate.contracts import ClaimRecord, SpecialistReport
from .contracts import CERTAINTY_RANK, IntegrityFinding, Synthesis

PLACEHOLDERS = frozenset({"n/a", "na", "-", ".", "tbd", "see above", "none", "null", "nil", "todo", "?", "x", "...", "as above", "same"})
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_LIST_MARKER_RE = re.compile(r"(?m)^\s*\(?\d{1,2}[.)]\s")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
#: A figure for the fidelity comparison: unlike ``_NUMBER_RE`` it accepts a sentence-final period after the numeral
#: ("printed in 1818."), because list markers are removed before it runs.
_FIGURE_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?!\w)(?!\.\d)")
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december")
_MONTH_YEAR_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{3,4})\b", re.IGNORECASE)
#: Transformations that promise the source's content unchanged: a figure or date they drop is reported (INT-LEDGER-024).
_EQUIVALENCE_LABELS = frozenset({"carried", "paraphrased"})
#: Transformations that combine or widen sources: a figure or date of the sources they leave out is reported too (a
#: warning; 'narrowed' removes content by definition and is exempt).
_COMBINING_LABELS = frozenset({"merged", "generalized"})

# --- figures written in words ---------------------------------------------------------------------------------------
_ONES = {w: i for i, w in enumerate(("one", "two", "three", "four", "five", "six", "seven", "eight", "nine"), start=1)}
_TEENS = {w: i for i, w in enumerate(("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"), start=10)}
_TENS = {w: 10 * i for i, w in enumerate(("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"), start=2)}
_SCALES = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
_FRACTION_NAMES = {"half": (1, 2), "halves": (1, 2), "third": (1, 3), "thirds": (1, 3), "quarter": (1, 4), "quarters": (1, 4), "fifth": (1, 5), "fifths": (1, 5),
                   "sixth": (1, 6), "sixths": (1, 6), "eighth": (1, 8), "eighths": (1, 8), "tenth": (1, 10), "tenths": (1, 10)}


def _alt(words) -> str:
    return "|".join(sorted(words, key=len, reverse=True))


_W_SMALL = rf"(?:(?:{_alt(_TENS)})(?:[-\s](?:{_alt(_ONES)}))?|{_alt(_TEENS)}|{_alt(_ONES)})"
_W_HUNDREDS = rf"(?:(?:a|an|{_alt(_ONES)})\s+hundred(?:\s+(?:and\s+)?{_W_SMALL})?)"
_W_NUMBER = rf"(?:{_W_HUNDREDS}|{_W_SMALL})"
_W_SCALE = _alt(_SCALES)
#: A figure written in words, in the contexts where words are a quantity and not prose ("one of", "the two poems"):
#: a scale word ("a million", "two million", "half a million", "two hundred thousand"), a per-cent unit ("thirteen per
#: cent"), a fraction ("two-thirds"; "a tenth" after a qualifier or before "of"), a number with "hundred" ("two hundred
#: and sixty") or a lower-case tens or teens number ("forty-five", "twelve").
_WORD_FIGURE_RE = re.compile(
    rf"\b(?:(?P<half>half)\s+an?\s+(?P<hscale>{_W_SCALE})s?"
    rf"|(?P<snum>{_W_NUMBER}|a|an)\s+(?P<scale>{_W_SCALE})s?"
    rf"|(?P<pnum>{_W_NUMBER})(?=\s+(?:per\s?cent|percent)\b)"
    rf"|(?P<fnum>two|three|four|five|seven|nine)[-\s](?P<fname>thirds|quarters|fifths|sixths|eighths|tenths)"
    rf"|(?:about|roughly|nearly|almost|some|around|over|under|just|by|than|only|barely|approximately)\s+(?P<qart>a|an|one)\s+(?P<qname>{_alt(k for k in _FRACTION_NAMES if not k.endswith('s'))})"
    rf"|(?:a|an|one)\s+(?P<oname>{_alt(k for k in _FRACTION_NAMES if not k.endswith('s'))})(?=\s+of\b)"
    rf"|(?P<hnum>{_W_HUNDREDS})"
    rf"|(?P<lnum>(?-i:(?:{_alt(_TENS)})(?:-(?:{_alt(_ONES)}))?|{_alt(set(_TEENS) - {'ten'})}))(?!-)"
    rf")\b", re.IGNORECASE)


def _small_value(words: str) -> int:
    total = 0
    for tok in re.split(r"[\s-]+", words.casefold()):
        if tok in ("and", ""):
            continue
        if tok in ("a", "an"):
            total += 1
        elif tok == "hundred":
            total = (total or 1) * 100
        else:
            total += _ONES.get(tok) or _TEENS.get(tok) or _TENS.get(tok, 0)
    return total


def _fmt(num: int, den: int = 1) -> str:
    """Canonical text of the value ``num/den``: an integer, an exact short decimal, or a decimal to four places (a third
    is "0.3333"), always a numeral the figure readers take as one token."""
    from fractions import Fraction
    v = Fraction(num, den)
    if v.denominator == 1:
        return str(v.numerator)
    for places in range(1, 5):
        if (v * 10**places).denominator == 1:
            return f"{float(v):.{places}f}"
    return f"{float(v):.4f}"


#: Small number words (two to ten, lower case) in a quantity context the general reader leaves to prose: after a word of
#: comparison or measure ("under nine", "to ten hours", "aged twelve" is a teen and read already), never before "of".
_SMALL_WORDS = ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")
_QUANTITY_PRE = ("under", "over", "aged", "than", "to", "at", "about", "around", "nearly", "almost", "only", "exactly", "just", "roughly",
                 "approximately", "below", "above", "within", "least", "most")
_SMALL_AFTER_RE = re.compile(rf"\b(?:{_alt(_QUANTITY_PRE)})\s+(?P<anum>(?-i:{_alt(_SMALL_WORDS)}))\b(?!-)(?!\s+of\b)", re.IGNORECASE)
#: For the pairing reader only: a small number word before a plural noun ("ten hours", "nine children"), unless a
#: determiner makes it prose ("the two poems", "both"): pairing compares figures the sources state, so a count the
#: sources never state is never compared.
_SMALL_BEFORE_NOUN_RE = re.compile(rf"(?<!\bthe )(?<!\bthese )(?<!\bthose )(?<!\bits )(?<!\bhis )(?<!\bher )(?<!\btheir )(?<!\bour )"
                                   rf"\b(?P<bnum>(?-i:{_alt(_SMALL_WORDS)}))(?=\s+[a-z]{{3,}}s\b)")
_SMALL_VALUES = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _word_figures(text: str, *, pairing: bool = False) -> list[tuple[int, int, str, Optional[str], str]]:
    """``(start, end, mantissa, scale or None, surface)`` for every figure written in words in ``text``. Small number
    words (two to ten) count after a word of comparison or measure ("under nine"); with ``pairing`` also before a plural
    noun ("ten hours"), the reading the pairing comparison uses."""
    out: list[tuple[int, int, str, Optional[str], str]] = []
    taken: list[tuple[int, int]] = []
    for m in _WORD_FIGURE_RE.finditer(text):
        taken.append((m.start(), m.end()))
    extra: list[tuple[int, int, str, Optional[str], str]] = []
    for rx, group in ((_SMALL_AFTER_RE, "anum"),) + (((_SMALL_BEFORE_NOUN_RE, "bnum"),) if pairing else ()):
        for m in rx.finditer(text):
            a, b = m.start(group), m.end(group)
            if any(x < b and a < y for x, y in taken):
                continue
            taken.append((a, b))
            extra.append((a, b, str(_SMALL_VALUES[m.group(group)]), None, m.group(group)))
    for m in _WORD_FIGURE_RE.finditer(text):
        g = m.groupdict()
        if g["half"]:
            out.append((m.start(), m.end(), "0.5", g["hscale"].casefold(), m.group(0)))
        elif g["scale"]:
            out.append((m.start(), m.end(), _fmt(_small_value(g["snum"])), g["scale"].casefold(), m.group(0)))
        elif g["pnum"]:
            out.append((m.start(), m.end(), _fmt(_small_value(g["pnum"])), None, m.group(0).strip()))
        elif g["fnum"]:
            num, den = _FRACTION_NAMES[g["fname"].casefold()]
            out.append((m.start(), m.end(), _fmt(_small_value(g["fnum"]) * num, den), None, m.group(0)))
        elif g["qname"]:  # the qualifier before the fraction is matched but is not part of the figure
            num, den = _FRACTION_NAMES[g["qname"].casefold()]
            out.append((m.start("qart"), m.end(), _fmt(num, den), None, text[m.start("qart"):m.end()]))
        elif g["oname"]:
            num, den = _FRACTION_NAMES[g["oname"].casefold()]
            out.append((m.start(), m.end(), _fmt(num, den), None, m.group(0)))
        elif g["hnum"] or g["lnum"]:
            out.append((m.start(), m.end(), _fmt(_small_value(g["hnum"] or g["lnum"])), None, m.group(0)))
    return sorted(out + extra)


def _words_as_digits(text: str) -> str:
    """``text`` with its figures written in words rewritten as digits ("close to a million" -> "close to 1 million",
    "roughly a tenth" -> "roughly 0.1", "under nine" -> "under 9", "ten hours" -> "10 hours"), so the pairing and dating
    readers see them as figures."""
    figs = _word_figures(text, pairing=True)
    if not figs:
        return text
    out, cursor = [], 0
    for start, end, mantissa, scale, _surface in figs:
        out.append(text[cursor:start])
        out.append(mantissa + (f" {scale}" if scale else ""))
        cursor = end
    out.append(text[cursor:])
    return "".join(out)

# --- figure pairing (INT-LEDGER-023, the swapped-figure case) -------------------------------------------------------
#: Tokens of a clause: a numeral (thousands separators already removed), a word (apostrophes and hyphens inside), or a
#: clause-breaking punctuation mark.
_PAIR_TOKEN_RE = re.compile(r"[,;:()]|[.!?](?=\s|$)|\d+(?:\.\d+)?|[^\W\d_]+(?:['’-][^\W\d_]+)*")
#: Words a clause of nothing but a date is made of ("On 27 October", "in July 1932"): such a clause is not cut from its
#: event by a comma ("On 27 October, the day ..., a second message added a demand").
_DATE_WORDS = frozenset(("on in by of at from since until till during around about early late mid the end start beginning middle "
                         "c circa ca").split()) | frozenset(_MONTHS)
#: Conjunctions and relative pronouns that start a new clause: a figure is paired only with the words of its own clause.
#: Prepositions that attach a date to its event ("in force since 24 October", "before 1933") are deliberately not here, nor is
#: "and", which joins the items of one dated statement ("37.3 per cent and 230 seats in July 1932").
_CLAUSE_BREAK_WORDS = frozenset("but yet so when while whereas although though which who whom whose where because if unless then".split())
#: Function words and unit words, never an event word a figure is paired with. Prepositions of a range ("from", "to",
#: "between") are among them: "between about 7.8 h and 8.2 h" states no event of 7.8.
_PARTNER_STOP = frozenset(("the a an and or of to in on for with by is are was were be been being this that these those as at from between it its into their there "
                           "which who whom not had has have having some about than then when while but so per cent percent million billion trillion thousand "
                           "hundred around roughly nearly almost over under more less only also still even just such very").split())
#: How far (in tokens of the same clause) an event word or another figure may stand from a figure to count as its partner.
_WORD_WINDOW = 4
_FIGURE_WINDOW = 4
#: "<quantity> ... <preposition> [<month>] <year>": the dated statement of a quantity; up to six unpunctuated words (figures among
#: them: "37.3 per cent and 230 seats in July 1932") may stand between the quantity and the preposition.
_DATED_QUANTITY_RE = re.compile(
    r"(?<![\w.])(?P<q>\d+(?:\.\d+)?)(?!\w)(?!\.\d)(?:\s+[^\W_]+(?:[.'’-][^\W_]+)*){0,6}?\s+(?:in|by|on|of|during|at|until|from|since|for|to)\s+(?:early\s+|late\s+|mid-?\s*)?"
    r"(?:(?P<m>" + "|".join(_MONTHS) + r")\s+)?(?P<d>1\d{3}|20\d{2})(?!\w)(?!\.\d)", re.IGNORECASE)
#: "from <figure> ... to <figure>" within one sentence: an ordered pair whose reversal is a swap.
_QUALIFIER = r"(?:(?:about|some|around|roughly|nearly|almost|over|under|c\.|circa|more than|less than|fewer than)\s+)?"
_FROM_TO_RE = re.compile(r"\bfrom\s+" + _QUALIFIER + r"(?P<a>\d+(?:\.\d+)?)(?!\w)(?!\.\d)[^.;!?]{0,80}?\bto\s+" + _QUALIFIER + r"(?P<b>\d+(?:\.\d+)?)(?!\w)(?!\.\d)", re.IGNORECASE)


def light_stem(word: str) -> str:
    """A light stem for comparing words across inflections: ``-ing``, ``-ed``, ``-es`` and ``-s`` are stripped
    (never from a short word or a double ``s``), then a trailing ``e`` from a longer word, so ``quote``, ``quotes``
    and ``quoting`` compare equal, as do ``present``, ``presents`` and ``presented``. Not a linguistic stemmer: the
    same light rule is applied to both sides of every comparison."""
    w = word.casefold()
    for suffix, keep in (("ing", 4), ("ed", 3), ("es", 3), ("s", 3)):
        if w.endswith(suffix) and len(w) - len(suffix) >= keep:
            if suffix == "s" and w.endswith("ss"):
                break
            w = w[: -len(suffix)]
            break
    if w.endswith("e") and len(w) > 4:
        w = w[:-1]
    return w


def _undouble(stem: str) -> str:
    """A stem with a doubled final consonant undone ("bann" from "banned" -> "ban", "stopp" -> "stop")."""
    if len(stem) >= 4 and stem[-1] == stem[-2] and stem[-1] not in "aeiouls":
        return stem[:-1]
    return stem


def _stem_hit(stem: str, words: set[str]) -> bool:
    """Whether a light stem occurs among ``words`` (light stems) loosely: equal once a doubled final consonant is undone,
    or one a prefix of the other with five letters or more ("employ" / "employment"), so a reworded event ("the ban on
    employing" for "banned the employment") is still the same event."""
    a = _undouble(stem)
    for w in words:
        b = _undouble(w)
        if a == b or (min(len(a), len(b)) >= 5 and (a.startswith(b) or b.startswith(a))):
            return True
    return False


#: Characters of mathematical notation: a whitespace-delimited chunk holding one is part of an expression, not prose.
#: The hyphen and the en dash are not among them (ranges and compounds in prose: "1914–1918", "forty-five").
_MATH_CHARS = frozenset("=<>≤≥≈≠±×÷∫∮√∑∏∞−^*|⁰¹²³⁴⁵⁶⁷⁸⁹₀₁₂₃₄₅₆₇₈₉")
#: A chunk that is only a (signed, bracketed) number with trailing punctuation: a negative figure of prose ("−2.1 per
#: cent") is not an expression by itself.
_SIGNED_NUMBER_RE = re.compile(r"^[(\[]?[−-]?\d+(?:[.,]\d+)*[)\]%.,;:!?]*$")


def _mask_math(text: str) -> str:
    """``text`` with its mathematical expressions replaced by a clause break: every whitespace-delimited chunk holding an
    operator, a relation, an integral or a superscript or subscript digit (``0 ≤ t ≤ 3``, ``3t(2 − t)``, ``∫₀² v dt``), and
    every numeral chunk standing next to one. The numbers inside a worked solution are terms of an expression, not
    figures of events, so the pairing readers never pair them (rule ``math-notation``)."""
    parts = re.split(r"(\s+)", text)
    words = parts[0::2]
    if not any(ch in _MATH_CHARS for w in words for ch in w):
        return text
    math = [any(ch in _MATH_CHARS for ch in w) and not _SIGNED_NUMBER_RE.match(w) for w in words]
    masked = list(math)
    for i, w in enumerate(words):
        if not math[i] and any(ch.isdigit() for ch in w) and ((i > 0 and math[i - 1]) or (i + 1 < len(words) and math[i + 1])):
            masked[i] = True
    for i in range(len(words)):
        if masked[i]:
            parts[2 * i] = ";"
    return "".join(parts)


def _plain_for_pairs(text: str) -> str:
    """The text the pairing readers work on: mathematical expressions masked (:func:`_mask_math`), list markers and
    thousands separators removed, figures written in words rewritten as digits (so "roughly a tenth" pairs like "about
    13 per cent")."""
    return _words_as_digits(_THOUSANDS_RE.sub("", _LIST_MARKER_RE.sub(" ", _mask_math(text))))


def _is_numeral(tok: str) -> bool:
    """An ASCII numeral: ``str.isdigit`` is also true of superscript and subscript digits ("10²", "∫₀²"), which ``int``
    rejects, so ordinary STEM notation would raise out of the channel."""
    return bool(tok) and tok[0] in "0123456789"


def _figure_kind(tokens: list[str], i: int) -> str:
    """``year`` (a four-digit year), ``day`` (1-31 next to a month name) or ``quantity``: a swap is looked for
    between figures of one kind only, so a seat count is never 'exchanged' with the year it was won."""
    tok = tokens[i]
    if re.fullmatch(r"1\d{3}|20\d{2}", tok):
        return "year"
    if re.fullmatch(r"[0-9]{1,2}", tok) and 1 <= int(tok) <= 31:
        for j in (i - 1, i + 1):
            if 0 <= j < len(tokens) and tokens[j].casefold() in _MONTHS:
                return "day"
    return "quantity"


def _date_only(clause: list[str]) -> bool:
    return bool(clause) and any(_is_numeral(t) for t in clause) and all(_is_numeral(t) or t.casefold() in _DATE_WORDS for t in clause)


def _clauses(text: str) -> list[list[str]]:
    """The clauses of ``text`` as token lists (numerals, words); sentence ends, punctuation and clause-breaking words
    split. A clause that is nothing but a date and ends at a comma joins the clause that follows it ("On 27 October,
    the day ..., a second message added"), and one that closes its sentence after a comma joins the clause before it
    ("peaked at 6.1 million, in February 1932"): a comma alone never cuts a date from its event."""
    segments: list[tuple[list[str], str]] = []  # (tokens, the separator that ended them)
    cur: list[str] = []
    for tok in _PAIR_TOKEN_RE.findall(_plain_for_pairs(text)):
        if tok in ",;:().!?" or (not _is_numeral(tok) and tok.casefold() in _CLAUSE_BREAK_WORDS):
            segments.append((cur, tok if tok in ",;:().!?" else "word"))
            cur = []
            continue
        cur.append(tok)
    segments.append((cur, "end"))
    out: list[list[str]] = []
    carry: list[str] = []
    prev_sep = "end"
    for tokens, sep in segments:
        tokens = carry + tokens
        carry = []
        if not tokens:
            prev_sep = sep
            continue
        if _date_only(tokens) and sep == ",":
            carry = tokens  # a leading date: it belongs to the clause after the comma
        elif _date_only(tokens) and prev_sep == "," and out and sep in (".", "!", "?", "end", ";"):
            out[-1] = out[-1] + tokens  # a trailing date after a comma: it belongs to the clause before
        else:
            out.append(tokens)
        prev_sep = sep
    if carry:
        out.append(carry)
    return out


#: The two ends of a range inside one clause: "from <a> [unit] to <b>", "between <a> [unit] and <b>" (an optional
#: qualifier before each end).
_RANGE_OPENERS = {"from": "to", "between": "and"}
_RANGE_QUALIFIERS = frozenset("about some around roughly nearly almost over under c circa".split())


def _clause_ranges(clause: list[str]) -> list[tuple[str, str]]:
    """``(a, b)`` for every range of ``clause`` (:data:`_RANGE_OPENERS`): the opener, at most one qualifier, a numeral, at
    most two unit words, the connector, at most one qualifier, a numeral."""
    out: list[tuple[str, str]] = []
    for k, tok in enumerate(clause):
        conn = _RANGE_OPENERS.get(tok.casefold())
        if conn is None:
            continue
        i = k + 1
        if i < len(clause) and clause[i].casefold() in _RANGE_QUALIFIERS:
            i += 1
        if i >= len(clause) or not _is_numeral(clause[i]):
            continue
        j = next((x for x in range(i + 1, min(i + 4, len(clause))) if clause[x].casefold() == conn), None)
        if j is None or any(_is_numeral(t) for t in clause[i + 1:j]):
            continue
        m = j + 1
        if m < len(clause) and clause[m].casefold() in _RANGE_QUALIFIERS:
            m += 1
        if m < len(clause) and _is_numeral(clause[m]) and clause[m] != clause[i]:
            out.append((clause[i], clause[m]))
    return out


def _figure_partners(text: str, *, share_ranges: bool = False) -> tuple[set[tuple[str, str]], dict[str, str], dict[str, str]]:
    """``(pairs, kinds, surface)``: every ``(figure, partner)`` of ``text``, the kind of each figure, and the word each
    stemmed partner was first seen as. A partner is an event word within :data:`_WORD_WINDOW` tokens of the figure in
    the same clause (light-stemmed, prefixed ``w:``) that has no nearer figure of the same kind, or another figure within
    :data:`_FIGURE_WINDOW` tokens (prefixed ``f:``). Unit words and function words are not partners. With
    ``share_ranges`` (the sources' side, rule ``range-ends``), the two ends of a range in one clause ("the external
    resistance rises from 2.4 Ω to 4.0 Ω") share that clause's event words: the event is the range's, not its nearer end's."""
    pairs: set[tuple[str, str]] = set()
    kinds: dict[str, str] = {}
    surface: dict[str, str] = {}
    for clause in _clauses(text):
        mine = _clause_partners(clause, kinds, surface)
        if share_ranges:
            for a, b in _clause_ranges(clause):
                wa = {q for f, q in mine if f == a and q.startswith("w:")}
                wb = {q for f, q in mine if f == b and q.startswith("w:")}
                mine |= {(a, q) for q in wb} | {(b, q) for q in wa}
        pairs |= mine
    return pairs, kinds, surface


def _clause_partners(clause: list[str], kinds: dict[str, str], surface: dict[str, str]) -> set[tuple[str, str]]:
    """The ``(figure, partner)`` pairs of one clause (:func:`_figure_partners`)."""
    pairs: set[tuple[str, str]] = set()
    figs = [(i, tok, _figure_kind(clause, i)) for i, tok in enumerate(clause) if _is_numeral(tok)]
    for i, tok, kind in figs:
        kinds.setdefault(tok, kind)
        for j, other, _k in figs:
            if j != i and abs(i - j) <= _FIGURE_WINDOW:
                pairs.add((tok, "f:" + other))
    for j, word in enumerate(clause):
        if _is_numeral(word):
            continue
        low = word.casefold()
        if low in _PARTNER_STOP or len(low) < 3:
            continue
        key = "w:" + light_stem(low)
        # An event word is the partner of the NEAREST figure of each kind within the window (ties: each), so in
        # "announced on 22 October and in force from 24 October" 'force' belongs to 24, not to 22 as well.
        for kind in {k for _i, _t, k in figs}:
            near = [(abs(i - j), tok) for i, tok, k in figs if k == kind and abs(i - j) <= _WORD_WINDOW]
            if not near:
                continue
            best = min(d for d, _t in near)
            for d, tok in near:
                if d == best:
                    surface.setdefault(key, low)
                    pairs.add((tok, key))
    return pairs


def _dated_quantities(text: str) -> set[tuple[str, str, Optional[str]]]:
    """``(quantity, year, month or None)`` for every dated statement of a quantity in ``text``."""
    plain = _plain_for_pairs(text)
    return {(m.group("q"), m.group("d"), (m.group("m") or "").casefold() or None) for m in _DATED_QUANTITY_RE.finditer(plain)
            if not re.fullmatch(r"1\d{3}|20\d{2}", m.group("q"))}


def _date_label(year: str, month: Optional[str]) -> str:
    return f"{month} {year}" if month else year


def _redated_quantities(synthesized_text: str, source_texts: list[str], exchanged: set[str], src_figures: set[str]) -> list[str]:
    """Quantities the synthesis dates to another time than the sources, compared at the resolution both sides state:
    a month is held against the sources' months for that quantity when they give any, else the year against the years."""
    src = set().union(*(_dated_quantities(t) for t in source_texts)) if source_texts else set()
    out: list[str] = []
    for q, y, m in sorted(_dated_quantities(synthesized_text), key=lambda t: (t[0], t[1], t[2] or "")):
        if (q, y, m) in src or q not in src_figures or y not in src_figures or q in exchanged:
            continue
        dates_of_q = {(y2, m2) for q2, y2, m2 in src if q2 == q}
        if not dates_of_q:
            continue
        monthed = {(y2, m2) for y2, m2 in dates_of_q if m2 is not None}
        if m is not None and monthed:
            if (y, m) not in monthed:
                out.append(f"'{q}' is dated {_date_label(y, m)}, where the cited sources date it {sorted(_date_label(y2, m2) for y2, m2 in monthed)}")
        elif y not in {y2 for y2, _ in dates_of_q}:
            out.append(f"'{q}' is dated {y}, where the cited sources date it {sorted({y2 for y2, _ in dates_of_q})}")
    return out


def _from_to_pairs(text: str) -> set[tuple[str, str]]:
    return {(m.group("a"), m.group("b")) for m in _FROM_TO_RE.finditer(_plain_for_pairs(text))}


def _partner_label(p: str, surface: dict[str, str]) -> str:
    return f"'{surface.get(p, p[2:])}'" if p.startswith("w:") else f"figure '{p[2:]}'"


def _partner_figures(*partners: str) -> set[str]:
    return {p[2:] for p in partners if p.startswith("f:")}


def _event_words(pairs: set[tuple[str, str]], fig: str) -> set[str]:
    """The event words ``fig`` stands with (month names are part of a date, not an event)."""
    return {q for b, q in pairs if b == fig and q.startswith("w:") and q[2:] not in _MONTH_STEMS}


_MONTH_STEMS = frozenset(light_stem(m) for m in _MONTHS)


def _one_sided_repairings(syn_pairs: set[tuple[str, str]], src_pairs: set[tuple[str, str]], kinds: dict[str, str], src_kinds: dict[str, str],
                          src_figures: set[str], exchanged: set[str], surface: dict[str, str]) -> list[str]:
    """A figure moved onto another figure's event, the other leg left out: the synthesis states figure A with event word
    P, where the sources pair P only with figure B of the same kind (never with A), the synthesis does not state B with
    P, and A has left every event the sources pair it with ("The turning point was 1932" where the sources say "The
    turning point was 1930" and state 1932 as "the strongest counter-case"). A figure the sources state with no event
    word, or one that keeps one of its own events, is a merge, not a re-pairing (the sources' pairing gives a range's
    event words to both of its ends: rule ``range-ends`` in :func:`_figure_partners`)."""
    moved: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for a, p in sorted(syn_pairs):
        if not p.startswith("w:") or p[2:] in _MONTH_STEMS or a not in src_figures or a in exchanged or (a, p) in src_pairs:
            continue
        holders = tuple(sorted({b for b, q in src_pairs if q == p and b != a and src_kinds.get(b) == kinds.get(a)}))
        if not holders or any((b, p) in syn_pairs for b in holders):
            continue
        own = _event_words(src_pairs, a)
        # an event word the sources also pair with a competing figure ("Act", "Factory" of two Acts) is shared, not one of
        # the figure's own events: keeping a shared noun while the verb moves is still a re-pairing (rule ``shared-partner``)
        distinct = own - set().union(*(_event_words(src_pairs, b) for b in holders))
        if not own or distinct & _event_words(syn_pairs, a):
            continue
        moved.setdefault((a, holders), []).append(p)
    out: list[str] = []
    for (a, holders), words in sorted(moved.items()):
        shown = ", ".join(_partner_label(p, surface) for p in words)
        own = ", ".join(_partner_label(p, surface) for p in sorted(_event_words(src_pairs, a)))
        out.append(f"'{a}' is stated with {shown}, where the cited sources pair {shown} only with {', '.join(repr(b) for b in holders)} and state '{a}' with {own} (re-paired)")
    return out


#: Sentence ends (and semicolons) of the text the substitution rule reads one sentence at a time.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")


def _substitutions(synthesized_text: str, syn_pairs: set[tuple[str, str]], src_pairs: set[tuple[str, str]], kinds: dict[str, str],
                   src_kinds: dict[str, str], src_figures: set[str], reported: set[str], surface: dict[str, str]) -> list[str]:
    """A figure standing in another figure's place (rule ``substitution``): in a sentence of the synthesis, year A stands
    with none of the event words the sources give A alone and with event words the sources give year B alone, while B is
    left out of the synthesis ("The ban ..., which the Factory Act introduced, came in 1847", or "The Factory Act of 1847
    banned ... The Ten Hours Act of 1847 followed it", where the sources say the 1833 Act banned and the 1847 Act
    followed it). Read one sentence at a time, so a year stated twice, once with its own events and once with another
    year's, is still caught. Event words are matched loosely (:func:`_stem_hit`: "the ban on employing" is "banned the
    employment"). A figure whose own events are all shared with another is never held to this, nor one the sources
    state with no event word."""
    plain = _plain_for_pairs(synthesized_text)
    sentences = [{light_stem(w) for w in _words(x)} | {"#" + t for t in _PAIR_TOKEN_RE.findall(x) if _is_numeral(t)}
                 for x in _SENTENCE_SPLIT_RE.split(plain) if x.strip()]
    syn_figs = {a for a, _ in syn_pairs} | set(kinds)
    out: list[str] = []
    for a in sorted(syn_figs):
        if a not in src_figures or a in reported or kinds.get(a, src_kinds.get(a)) != "year":
            continue
        others = {b for b in src_figures if b != a and src_kinds.get(b) == "year" and b not in syn_figs}
        if not others:
            continue
        own = _event_words(src_pairs, a)
        distinct_a = own - set().union(*(_event_words(src_pairs, b) for b in src_figures if b != a and src_kinds.get(b) == "year"))
        if not distinct_a:
            continue
        found = None
        for words in sentences:
            if "#" + a not in words or any(_stem_hit(p[2:], words) for p in distinct_a):
                continue
            for b in sorted(others):
                distinct_b = {p for p in _event_words(src_pairs, b) - own}
                taken = sorted(p for p in distinct_b if _stem_hit(p[2:], words))
                if taken:
                    found = (b, taken)
                    break
            if found:
                break
        if found:
            b, taken = found
            shown = ", ".join(_partner_label(p, surface) for p in taken)
            out.append(f"'{a}' stands in the place of '{b}': the synthesis states {shown}, which the cited sources state only with '{b}', with '{a}' and "
                       f"without '{b}', and none of the events the sources give '{a}' ({', '.join(_partner_label(p, surface) for p in sorted(distinct_a))}) (re-paired)")
    return out


#: Words that lead a run of capitalised words without being part of the name ("The Factory Act", "In 1833").
_NAME_LEAD_STOP = frozenset(("the a an on in at by of for from to and or but nor this that these those its his her their our after before during since "
                             "when while with as both each every under over between").split())
#: Words that open a relative clause; ", which ... ," between a name and what follows is parenthetical.
_RELATIVE_WORDS = frozenset("which who whom whose where".split())
_SENTENCE_MARKS = frozenset(".!?;")


def _is_cap_word(tok: str) -> bool:
    return len(tok) >= 2 and tok[0].isupper() and not _is_numeral(tok) and tok not in ",;:().!?"


def _name_runs(sent: list[str]) -> list[tuple[int, int, tuple[str, ...], str]]:
    """``(start, end, key, surface)`` for every name of one sentence (rule ``name-partner``): a run of capitalised words,
    its leading determiner or preposition dropped ("The Ten Hours Act" -> "Ten Hours Act"); a single capitalised word
    opening the sentence is ordinary prose, not a name. ``key`` is the light-stemmed words."""
    first = next((k for k, t in enumerate(sent) if t not in ",;:()"), 0)
    out: list[tuple[int, int, tuple[str, ...], str]] = []
    i = 0
    while i < len(sent):
        if not _is_cap_word(sent[i]):
            i += 1
            continue
        j = i
        while j < len(sent) and _is_cap_word(sent[j]):
            j += 1
        s = i
        while s < j and sent[s].casefold() in _NAME_LEAD_STOP:
            s += 1
        if s < j and not (i == first and j - i == 1):
            words = sent[s:j]
            out.append((s, j, tuple(light_stem(w.casefold()) for w in words), " ".join(words)))
        i = j
    return out


@lru_cache(maxsize=8192)
def _name_partners(text: str) -> tuple[frozenset, frozenset, tuple, tuple]:
    """``(bound, governed, kinds, surface)`` of ``text`` (rule ``name-partner``). ``bound``: ``(figure, name)`` for a name
    stated with its figure ("the Ten Hours Act of 1847", "the Factory Act (1833)", "the 1833 Factory Act"). ``governed``:
    ``(quantity, name)`` for a quantity stated after a name in the same sentence, the nearest one, a parenthetical
    relative clause (", which followed it,") and a bracket skipped ("the Ten Hours Act of 1847, which followed it, set the
    age at nine": nine is the Ten Hours Act's). ``kinds``: each figure's kind; ``surface``: each name key's words."""
    toks = _PAIR_TOKEN_RE.findall(_plain_for_pairs(text))
    sentences: list[list[str]] = [[]]
    for t in toks:
        if t in _SENTENCE_MARKS:
            sentences.append([])
        else:
            sentences[-1].append(t)
    bound: set[tuple[str, tuple[str, ...]]] = set()
    governed: set[tuple[str, tuple[str, ...]]] = set()
    kinds: dict[str, str] = {}
    surface: dict[tuple[str, ...], str] = {}
    for sent in sentences:
        if not sent:
            continue
        names = _name_runs(sent)
        starts = {s: (e, key) for s, e, key, _w in names}
        for s, e, key, words in names:
            surface.setdefault(key, words)
            if e + 1 < len(sent) and sent[e].casefold() in ("of", "in", "(") and _is_numeral(sent[e + 1]):
                bound.add((sent[e + 1], key))
            if s >= 2 and _is_numeral(sent[s - 1]) and sent[s - 2].casefold() in ("the", "a", "an", "its", "their"):
                bound.add((sent[s - 1], key))
        current: Optional[tuple[str, ...]] = None
        k = 0
        while k < len(sent):
            tok = sent[k]
            if tok == "(":
                close = next((x for x in range(k + 1, len(sent)) if sent[x] == ")"), None)
                if close is not None:
                    k = close + 1
                    continue
            if tok == "," and k + 1 < len(sent) and sent[k + 1].casefold() in _RELATIVE_WORDS:
                close = next((x for x in range(k + 2, len(sent)) if sent[x] == ","), None)
                if close is not None:  # a relative clause closed by a comma is parenthetical: the name before it governs after it
                    k = close + 1
                    continue
            if k in starts:
                current = starts[k][1]
                k = starts[k][0]
                continue
            if _is_numeral(tok):
                kind = _figure_kind(sent, k)
                kinds.setdefault(tok, kind)
                if kind == "quantity" and current is not None:
                    governed.add((tok, current))
            k += 1
    return frozenset(bound), frozenset(governed), tuple(sorted(kinds.items())), tuple(sorted(surface.items()))


def _name_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Two names are the same when the words of one are among the other's ("Act" and "Factory Act")."""
    sa, sb = set(a), set(b)
    return sa <= sb or sb <= sa


def _renamed_figures(synthesized_text: str, source_texts: list[str], context_texts: tuple[str, ...] | list[str], src_figures: set[str]) -> list[str]:
    """Rule ``name-partner``: a figure stated with (or, for a quantity, under) a name the cited sources and reports never
    state with it, a name they state with another figure of the same kind, while they state the figure itself with
    another name ("The Ten Hours Act of 1833 banned ...", where the reports state the Factory Act of 1833 and the Ten
    Hours Act of 1847; "the Ten Hours Act of 1847, which followed it, set the age at nine", where the sources state
    "nine" under the Factory Act). A name no source states with any figure, and a name that is part of the figure's own
    name ("the Act of 1833"), are never re-pairings. An exchange of names that keeps every figure's verb is one."""
    syn_bound, syn_gov, syn_kinds, syn_surface = _name_partners(synthesized_text)
    if not syn_bound and not syn_gov:
        return []
    ref_bound: set = set()
    ref_gov: set = set()
    ref_kinds: dict[str, str] = {}
    surface = dict(syn_surface)
    for t in list(source_texts) + list(context_texts):
        b, g, k, sf = _name_partners(t)
        ref_bound |= b
        ref_gov |= g
        for fig, kind in k:
            ref_kinds.setdefault(fig, kind)
        for key, words in sf:
            surface.setdefault(key, words)
    kinds = dict(syn_kinds)
    src_gov = set()
    for t in source_texts:
        src_gov |= _name_partners(t)[1]
    out: list[str] = []
    for a, name in sorted(syn_bound):
        if a not in src_figures or (a, name) in ref_bound:
            continue
        own = {m for f, m in ref_bound if f == a}
        if not own or any(_name_match(name, m) for m in own):
            continue
        holders = sorted({f for f, m in ref_bound if f != a and ref_kinds.get(f) == kinds.get(a, ref_kinds.get(a)) and _name_match(name, m)})
        if holders:
            out.append(f"'{a}' is stated with the name '{surface.get(name, ' '.join(name))}', which the cited sources and reports state only with "
                       f"{', '.join(repr(h) for h in holders)}, and they state '{a}' with {', '.join(repr(surface.get(m, ' '.join(m))) for m in sorted(own))} (re-paired name)")
    for a, name in sorted(syn_gov):
        if a not in src_figures or (a, name) in src_gov:
            continue
        own = {m for f, m in src_gov if f == a}
        if not own or any(_name_match(name, m) for m in own):
            continue
        others = sorted({f for f, m in ref_bound if f != a and _name_match(name, m)})
        if others:
            out.append(f"'{a}' is stated under the name '{surface.get(name, ' '.join(name))}', which the cited sources and reports state with "
                       f"{', '.join(repr(h) for h in others)}, where the cited sources state '{a}' under {', '.join(repr(surface.get(m, ' '.join(m))) for m in sorted(own))} (re-paired name)")
    return out


# --- who is named (INT-LEDGER-029, rule ``name-substitution``) -------------------------------------------------------
#: Transformations whose claim may name only the people, places and bodies its cited sources name: they carry, restate
#: or combine the sources' content ('generalized' and 'narrowed' widen or cut it and are not held to the sources' names).
_NAME_HELD_LABELS = frozenset({"carried", "paraphrased", "merged"})
#: Capitalised words that name no actor: months, weekdays and the first-person pronoun.
_NOT_NAME_WORDS = frozenset(light_stem(w) for w in (*_MONTHS, *"monday tuesday wednesday thursday friday saturday sunday i".split()))
#: Titles and offices that a paraphrase may add to, or drop from, a name the sources state ("President Kennedy" for
#: "Kennedy"): never the part of a name that identifies who is meant.
_TITLE_WORDS = frozenset(light_stem(w) for w in ("mr mrs ms miss dr sir lady lord dame president vice king queen prince princess emperor empress tsar czar kaiser pope "
                          "saint st general gen admiral captain colonel major lieutenant marshal chancellor premier prime minister secretary senator "
                          "governor chairman chairwoman earl duke duchess baron baroness count countess viscount marquess archbishop bishop cardinal "
                          "reverend rev professor prof judge justice mayor sheikh sultan shah chief commander").split())
#: Personal pronouns a source may name an actor with ("On 27 October he chose ..."): a claim that puts a name the
#: source never states in their place has decided who acted.
_ACTOR_PRONOUNS = frozenset("he she they him her them his hers their theirs".split())


def _name_word(tok: str) -> str:
    """A name word as compared: possessive removed ("Kennedy's" -> "kennedy"), case folded, light-stemmed."""
    w = re.sub(r"['’]s?$", "", tok)
    return light_stem(w.casefold())


def _quotations_masked(text: str) -> str:
    """``text`` with its quoted spans replaced by a sentence break: a name inside a quotation is the quotation rule's
    (INT-LEDGER-025), not the synthesis's own naming."""
    from ..adapters.markdown import find_quotation_spans
    spans = find_quotation_spans(text)
    if not spans:
        return text
    out, last = [], 0
    for s, e, _inner in spans:
        out.append(text[last:s])
        out.append(" ; ")
        last = e
    out.append(text[last:])
    return "".join(out)


def _sentences_of(text: str, *, quotations: bool = False) -> list[list[str]]:
    """The sentences of ``text`` as tokens; quoted spans masked unless ``quotations``."""
    body = text if quotations else _quotations_masked(text)
    toks = _PAIR_TOKEN_RE.findall(_LIST_MARKER_RE.sub(" ", _mask_math(body)))
    sentences: list[list[str]] = [[]]
    for t in toks:
        if t in _SENTENCE_MARKS or t == ":":
            sentences.append([])
        else:
            sentences[-1].append(t)
    return [s for s in sentences if s]


def _first_word(sent: list[str]) -> int:
    return next((k for k, x in enumerate(sent) if x not in ",;:()"), 0)


def _mid_capitalised(texts: list[str]) -> set[str]:
    """Name words written capitalised away from the start of a sentence in ``texts`` (quotations included): what a
    sentence-initial word is folded against."""
    out: set[str] = set()
    for t in texts:
        for sent in _sentences_of(t, quotations=True):
            first = _first_word(sent)
            out.update(_name_word(x) for k, x in enumerate(sent) if k != first and _is_cap_word(x))
    return out


def _identifies(word: str) -> bool:
    return bool(word) and word not in _NOT_NAME_WORDS and word not in _TITLE_WORDS


def _actor_names(sent: list[str], mid_caps: set[str]) -> list[tuple[int, int, tuple[str, ...], str]]:
    """``(start, end, identifying words, surface)`` for every name of one sentence: a run of capitalised words, its
    leading determiner or preposition dropped, months, weekdays, titles and offices left out of the identifying words
    (the surface spans the identifying words). A single capitalised word opening a sentence is a name only when some
    text writes it capitalised mid-sentence (``mid_caps``): "Overall" or "Thus" opening a sentence is prose,
    "Khrushchev" is not."""
    first = _first_word(sent)
    out: list[tuple[int, int, tuple[str, ...], str]] = []
    i = 0
    while i < len(sent):
        if not _is_cap_word(sent[i]):
            i += 1
            continue
        j = i
        while j < len(sent) and _is_cap_word(sent[j]):
            j += 1
        s = i
        while s < j and sent[s].casefold() in _NAME_LEAD_STOP:
            s += 1
        if s < j and i == first and j - s == 1 and _name_word(sent[s]) not in mid_caps:
            s = j  # a single sentence-initial word no text writes capitalised elsewhere: folded, ordinary prose
        keep = [k for k in range(s, j) if _identifies(_name_word(sent[k]))]
        if keep:
            out.append((s, j, tuple(_name_word(sent[k]) for k in keep), " ".join(sent[keep[0]:keep[-1] + 1])))
        i = j
    return out


def _slot(sent: list[str], k: int, side: str) -> Optional[tuple[str, str]]:
    """The word next to an actor (``side`` "prev" before it, "next" after it), or None at a mark or a numeral."""
    if 0 <= k < len(sent) and sent[k] not in ",;:()" and not _is_numeral(sent[k]):
        return (side, _name_word(sent[k]))
    return None


def _actors(text: str, mid_caps: set[str]) -> list[tuple[tuple[str, ...], str, frozenset]]:
    """``(identifying words, surface, slots)`` for every actor of ``text``: a name, or a personal pronoun (its words
    the pronoun itself). ``slots`` are the words standing right before and right after it ("On 27 October he chose":
    ``("prev", "october")`` and ``("next", "chos")``): what the act is, as ``name-substitution`` aligns a claim with its
    source."""
    out: list[tuple[tuple[str, ...], str, frozenset]] = []
    for sent in _sentences_of(text):
        for s, e, ident, surface in _actor_names(sent, mid_caps):
            out.append((ident, surface, frozenset(x for x in (_slot(sent, s - 1, "prev"), _slot(sent, e, "next")) if x)))
        for k, x in enumerate(sent):
            if x.casefold() in _ACTOR_PRONOUNS:
                out.append(((x.casefold(),), x, frozenset(y for y in (_slot(sent, k - 1, "prev"), _slot(sent, k + 1, "next")) if y)))
    return out


def _stated_words(texts: list[str]) -> set[str]:
    """Every word ``texts`` state, folded as name words, quotations included (a name a source quotes, it states)."""
    return {_name_word(x) for t in texts for sent in _sentences_of(t, quotations=True) for x in sent if not _is_numeral(x)}


def substituted_names(synthesized_text: str, source_texts: list[str], transformation: str, *, context_texts: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Rule ``name-substitution`` (INT-LEDGER-029): a 'carried', 'paraphrased' or 'merged' claim that names an actor (a
    run of capitalised words: a person, a place, a body) none of whose identifying words its cited sources state, where
    the sources give the act to another actor:

    * aligned: a cited source puts another name, or a personal pronoun, next to the same word ("Robert Peel championed
      the Ten Hours Act" for "Lord Ashley championed the Ten Hours Act"; "On 27 October Khrushchev chose to answer" for
      "On 27 October he chose to answer", whoever "he" is: the combinator decided who acted, and the claim it cites does
      not say);
    * exchanged ('carried' and 'paraphrased' only, which promise the source's content unchanged): the claim leaves out a
      name its source states and names one the source does not ("Robert Peel promoted ..." for "Lord Ashley championed
      ..."). A merge may leave names of its sources out, so this shape is not applied to it.

    Words are compared folded (case, possessive, light stem); titles and offices ("President", "Lord"), months and
    weekdays never identify anyone; a single word opening a sentence is a name only when some text writes it capitalised
    mid-sentence; names inside the claim's quotations are left to the quotation rule, and a name a source states inside
    a quotation is stated. ``context_texts`` (the cited reports' other claims) only decide which sentence-initial words
    are names: a name only they state is still one the CITED sources do not state. A name no source states with no other
    actor for its act (a pronoun resolved where the source has none, a place named for "the city") is not reported.
    Returns one description per substituted name."""
    if transformation not in _NAME_HELD_LABELS or not source_texts:
        return []
    mid_caps = _mid_capitalised([synthesized_text, *source_texts, *context_texts])
    syn = [a for a in _actors(synthesized_text, mid_caps) if a[0][0] not in _ACTOR_PRONOUNS]
    if not syn:
        return []
    stated = _stated_words(source_texts)
    src = [a for t in source_texts for a in _actors(t, mid_caps)]
    syn_words = set().union(*(set(a[0]) for a in syn))
    dropped = sorted({surface for ident, surface, _sl in src if ident[0] not in _ACTOR_PRONOUNS and not set(ident) & syn_words
                      and not any(w in _stated_words([synthesized_text]) for w in ident)})
    out: list[str] = []
    seen: set[tuple[str, ...]] = set()
    for ident, surface, slots in syn:
        if ident in seen or all(w in stated for w in ident):
            continue
        seen.add(ident)
        instead = sorted({(s_surface, slot[1]) for s_ident, s_surface, s_slots in src for slot in slots & s_slots if not set(s_ident) & set(ident)})
        if instead:
            acts = sorted({w for _x, w in instead})
            out.append(f"it names '{surface}', which none of its cited sources states, where they give the same act (next to {', '.join(repr(w) for w in acts)}) "
                       f"to {', '.join(sorted({repr(x) for x, _w in instead}))} (a substituted actor)")
        elif dropped and transformation in _EQUIVALENCE_LABELS:
            out.append(f"it names '{surface}', which none of its cited sources states, and leaves out {', '.join(repr(x) for x in dropped)}, which its "
                       "source states (a substituted name)")
    return out


def figure_pairing_differences(synthesized_text: str, source_texts: list[str], *, context_texts: tuple[str, ...] | list[str] = ()) -> list[str]:
    """How ``synthesized_text`` pairs its figures and dates differently from ``source_texts`` while using the same
    tokens: a combinator that swaps two dates or two figures between events passes a token-set comparison, so the
    pairing is compared as well. Three shapes are read, each decided on the sources' own statements:

    * an exchange: figure A stands with event word (or figure) P and figure B with Q, where the sources state B with P
      and A with Q (A and B of the same kind: years, days of a month, or quantities);
    * a one-sided re-pairing: A stands with event word P, which the sources pair only with B, and A has left every
      event the sources state it with alone (an event word the sources also pair with B is shared and does not count:
      :func:`_one_sided_repairings`; a range the sources state gives its event words to both of its ends, rule
      ``range-ends``, so "rises from 2.4 Ω to 4.0 Ω" restated as "rises to 4.0 Ω" re-pairs nothing);
    * a substitution: year A takes the place of year B, which the synthesis leaves out, carrying B's own event words and
      none of A's (:func:`_substitutions`);
    * a dated quantity ``<q> ... in [<month>] <year>`` that the sources date to another month or year;
    * a ``from X to Y`` pair the sources state as ``from Y to X``;
    * a re-paired name (rule ``name-partner``, :func:`_renamed_figures`): a figure stated with a name, or a quantity
      under a name, that the cited sources and ``context_texts`` (the other claims of the cited reports) state only with
      another figure, while they state the figure with another name: the Acts' NAMES exchanged with every year and verb
      kept.

    Only figures that occur in the sources are compared (a figure in no source is the plain INT-LEDGER-023 case), and
    a year that carries several quantities in the sources is not held to any one of them (a merge may date several
    items at once). Returns one description per difference; empty when every pairing is the sources' own."""
    syn_pairs, kinds, surface = _figure_partners(synthesized_text)
    src_pairs: set[tuple[str, str]] = set()
    src_kinds: dict[str, str] = {}
    for t in source_texts:
        p, k, sf = _figure_partners(t, share_ranges=True)
        src_pairs |= p
        for fig, kind in k.items():
            src_kinds.setdefault(fig, kind)
        for key, word in sf.items():
            surface.setdefault(key, word)
    src_figures = {a for a, _ in src_pairs} | set(src_kinds)
    out: list[str] = []
    reported: set[frozenset[str]] = set()
    exchanged: set[str] = set()
    for a, p in sorted(syn_pairs):
        if a not in src_figures or (a, p) in src_pairs:
            continue
        for b in sorted({b for b, q in src_pairs if q == p and b != a and src_kinds.get(b) == kinds.get(a)}):
            swapped = sorted(q for bb, q in syn_pairs if bb == b and (b, q) not in src_pairs and (a, q) in src_pairs)
            if not swapped:
                continue
            key = frozenset({a, b}) | _partner_figures(p, swapped[0])  # the same exchange seen from its figure partners' side is one exchange
            if key in reported:
                continue
            reported.add(key)
            exchanged |= {a, b}
            out.append(f"'{a}' is stated with {_partner_label(p, surface)} and '{b}' with {_partner_label(swapped[0], surface)}, "
                       f"where the cited sources state '{b}' with {_partner_label(p, surface)} and '{a}' with {_partner_label(swapped[0], surface)} (exchanged)")
    one_sided = _one_sided_repairings(syn_pairs, src_pairs, kinds, src_kinds, src_figures, exchanged, surface)
    out += one_sided
    moved = exchanged | {d.split("'")[1] for d in one_sided}
    out += _substitutions(synthesized_text, syn_pairs, src_pairs, kinds, src_kinds, src_figures, moved, surface)
    out += _redated_quantities(synthesized_text, source_texts, exchanged, src_figures)
    src_from_to = set().union(*(_from_to_pairs(t) for t in source_texts)) if source_texts else set()
    for a, b in sorted(_from_to_pairs(synthesized_text)):
        if (a, b) not in src_from_to and (b, a) in src_from_to:
            out.append(f"'from {a} to {b}' reverses the cited sources' 'from {b} to {a}'")
    out += _renamed_figures(synthesized_text, source_texts, context_texts, src_figures)
    return _with_word_labels(out, [synthesized_text, *source_texts])


def _with_word_labels(descriptions: list[str], texts: list[str]) -> list[str]:
    """Show a figure written in words as the words, with the value the readers compared ("'a tenth' (0.1)")."""
    labels: dict[str, str] = {}
    for t in texts:
        for _s, _e, mantissa, _scale, surface in _word_figures(_THOUSANDS_RE.sub("", t), pairing=True):
            labels.setdefault(mantissa, " ".join(surface.split()))
    if not labels:
        return descriptions
    out = []
    for d in descriptions:
        for value, words in labels.items():
            d = d.replace(f"'{value}'", f"'{words}' ({value})")
        out.append(d)
    return out


# --- what a paraphrase says, beyond its figures (INT-LEDGER-025 / INT-LEDGER-026) ------------------------------------
_RISE_WORDS = frozenset(("rose rise rises risen rising grew grow grows growing grown growth increase increased increases increasing climbed climb climbs "
                         "climbing soared soar soaring doubled tripled trebled gained gain expanded expansion higher").split())
_FALL_WORDS = frozenset(("fell fall falls fallen falling declined decline declines declining decreased decrease decreases decreasing dropped drop drops "
                         "dropping shrank shrink shrunk slumped slump collapsed collapse halved lower contracted contraction reduced reduction").split())
_NEGATORS = frozenset("not never no nor neither none nothing nobody nowhere cannot without".split())
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")
_APPROX_RE = re.compile(r"\b(?:about|around|roughly|approximately|nearly|almost|some|close to|c\.|circa|ca\.|more than|over|under|less than|just over|just under)\s+(\d+(?:\.\d+)?)(?!\.\d)", re.IGNORECASE)
_EXACT_RE = re.compile(r"\b(exactly|precisely|fully|a full|an exact)\s+(\d+(?:\.\d+)?)(?!\.\d)", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD_RE.findall(text)]


def _negations(text: str) -> int:
    return sum(1 for w in _words(text) if w in _NEGATORS or w.endswith(("n't", "n’t")))


def meaning_differences(synthesized_text: str, source_texts: list[str], transformation: str) -> list[str]:
    """How a synthesized claim says something other than its cited sources beyond its figures, as plain descriptions:
    the direction of a change reversed (a fall where every source states a rise, or the reverse), the polarity changed
    under an equivalence label (a negation dropped or added by a 'carried' or 'paraphrased' claim), and an approximate
    figure of the sources stated as exact ("exactly 60" where a source says "roughly 60"). Lexical, not a proof: the
    findings built on it are warnings."""
    out: list[str] = []
    syn_words = set(_words(synthesized_text))
    src_words = set().union(*(set(_words(t)) for t in source_texts)) if source_texts else set()
    syn_rise, syn_fall = bool(syn_words & _RISE_WORDS), bool(syn_words & _FALL_WORDS)
    src_rise, src_fall = bool(src_words & _RISE_WORDS), bool(src_words & _FALL_WORDS)
    if syn_fall and not syn_rise and src_rise and not src_fall:
        out.append(f"it states a fall ({sorted(syn_words & _FALL_WORDS)}) where its cited sources state a rise ({sorted(src_words & _RISE_WORDS)})")
    elif syn_rise and not syn_fall and src_fall and not src_rise:
        out.append(f"it states a rise ({sorted(syn_words & _RISE_WORDS)}) where its cited sources state a fall ({sorted(src_words & _FALL_WORDS)})")
    if transformation in _EQUIVALENCE_LABELS and source_texts:
        syn_neg, src_neg = _negations(synthesized_text), sum(_negations(t) for t in source_texts)
        if (syn_neg == 0) != (src_neg == 0):
            out.append("it drops the negation its cited sources state" if syn_neg == 0 else "it adds a negation its cited sources do not state")
    approx = {m.group(1) for t in source_texts for m in _APPROX_RE.finditer(_THOUSANDS_RE.sub("", t))}
    exact = sorted({(m.group(1).casefold(), m.group(2)) for m in _EXACT_RE.finditer(_THOUSANDS_RE.sub("", synthesized_text)) if m.group(2) in approx}, key=lambda x: x[1])
    for word, fig in exact:
        out.append(f"it states '{word} {fig}' where its cited sources give {fig} as an approximate figure")
    return out


#: Comparison words that bound a figure from above (the figure is a maximum, an end or a later limit) and from below.
#: A paraphrase that turns the comparison on the same figure the other way ("under nine" -> "over nine", "before 1847"
#: -> "after 1847") states the opposite of its source (rule ``comparison-direction``).
_UPPER_BOUND = ("under", "below", "less than", "fewer than", "at most", "no more than", "up to", "younger than", "before", "earlier than", "until", "not over",
                "lower than", "smaller than", "shorter than")
_LOWER_BOUND = ("over", "above", "more than", "greater than", "at least", "no less than", "no fewer than", "older than", "after", "later than", "since",
                "higher than", "larger than", "longer than", "beyond", "exceeding")
_DIRECTION_RE = re.compile(r"\b(?P<w>" + _alt(_UPPER_BOUND + _LOWER_BOUND).replace(" ", r"\s+") + r")\s+(?:the\s+age\s+of\s+)?(?P<n>\d+(?:\.\d+)?)(?!\.\d)(?!\w)",
                           re.IGNORECASE)


def _directions(text: str) -> dict[str, set[str]]:
    """figure -> the directions (``upper`` / ``lower``) in which ``text`` bounds it with a comparison word ("under nine":
    9 -> upper). Figures written in words are read as digits; mathematical notation is masked."""
    out: dict[str, set[str]] = {}
    for m in _DIRECTION_RE.finditer(_plain_for_pairs(text)):
        w = " ".join(m.group("w").casefold().split())
        out.setdefault(m.group("n"), set()).add("upper" if w in _UPPER_BOUND else "lower")
    return out


#: Words that state a prohibition, prevention or absence: a source that holds one can be paraphrased with a negation
#: and keep its meaning ("banned employing children" -> "children could not be employed"), so an added negation is an
#: error against such a source only when it negates that very word ("banned" -> "did not ban").
_NEGATIVE_MEANING_WORDS = ("ban banned bans banning prohibit prohibited prohibits forbid forbade forbidden outlaw outlawed bar barred prevent prevented "
                           "prevents stop stopped stops end ended ends abolish abolished refuse refused refuses reject rejected rejects deny denied denies "
                           "lack lacked lacks fail failed fails exclude excluded excludes avoid avoided avoids cease ceased halt halted block blocked absent "
                           "absence lose lost loses").split()
#: How many words after a negator are read as what it negates.
_NEGATION_SCOPE = 3


def _negation_stem(word: str) -> str:
    """``light_stem`` with a doubled final consonant undone ("banned" -> "bann" -> "ban"), so a negated base form compares
    with the inflected form of its source."""
    return _undouble(light_stem(word))


_NEGATIVE_MEANING = frozenset(_negation_stem(w) for w in _NEGATIVE_MEANING_WORDS)


def _negated_source_words(synthesized_text: str, source_text: str) -> list[str]:
    """The source's own content words that a negator of ``synthesized_text`` negates (a content word within
    :data:`_NEGATION_SCOPE` words after "not", "never", "no", "didn't", ...), named rule ``negated-source-content``. Empty
    when every added negation negates something the source does not state (a different statement, not its opposite)
    or when the source states a prohibition or absence other than the negated word (a polarity-preserving rewording)."""
    src_words = _words(source_text)
    src_stems = {_negation_stem(w) for w in src_words if w not in _PARTNER_STOP and w not in _NEGATORS and len(w) >= 3}
    src_negative = {_negation_stem(w) for w in src_words} & _NEGATIVE_MEANING
    words = _words(synthesized_text)
    out: list[str] = []
    for i, w in enumerate(words):
        if not (w in _NEGATORS or w.endswith(("n't", "n’t"))):
            continue
        for v in words[i + 1:i + 1 + _NEGATION_SCOPE]:
            if v in _PARTNER_STOP or v in _NEGATORS or len(v) < 3:
                continue
            stem = _negation_stem(v)
            if stem in src_stems and not (src_negative - {stem}):
                out.append(v)
                break
    return out


def meaning_inversions(synthesized_text: str, source_texts: list[str], transformation: str) -> list[str]:
    """How a 'carried' or 'paraphrased' claim with ONE cited source states the opposite of it, as descriptions for an
    error (INT-LEDGER-027): a figure the source bounds one way ("children under nine") bounded the other way ("children
    over nine"), or a negation added where the source states none that negates the source's own content ("did not ban"
    where the source says "banned": rule ``negated-source-content``). These labels promise the source's content
    unchanged, and the figure-anchored comparison or the negated statement is not a rewording a paraphrase needs. An
    added negation over words the source does not state, or against a source that states a prohibition or absence of
    its own ("could not be employed" for "banned employing"), stays the INT-LEDGER-026 warning, as does a dropped
    negation (a paraphrase may turn "no child under nine could work" into "children under nine were banned")."""
    if transformation not in _EQUIVALENCE_LABELS or len(source_texts) != 1:
        return []
    out: list[str] = []
    syn, src = _directions(synthesized_text), _directions(source_texts[0])
    for fig in sorted(set(syn) & set(src), key=lambda x: (len(x), x)):
        if syn[fig] != src[fig] and len(syn[fig]) == 1 and len(src[fig]) == 1:
            out.append(f"it bounds '{fig}' {'from below' if 'lower' in syn[fig] else 'from above'} where its cited source bounds it "
                       f"{'from below' if 'lower' in src[fig] else 'from above'} (a comparison turned the other way)")
    if _negations(synthesized_text) > 0 and _negations(source_texts[0]) == 0:
        negated = _negated_source_words(synthesized_text, source_texts[0])
        if negated:
            out.append(f"it adds a negation its cited source does not state, negating the source's own {sorted(set(negated))}")
    return _with_word_labels(out, [synthesized_text, *source_texts])


def _quotation_corpus(reports: list[SpecialistReport], known: list[ClaimRecord], extra_texts: tuple[str, ...]) -> list[str]:
    texts: list[str] = [c.claim_text for c in known]
    seen: set[str] = set()
    for r in reports:
        for t in [r.original_response, *(x.text for x in r.supplied_texts)]:
            if t not in seen:
                seen.add(t)
                texts.append(t)
    texts += [t for t in extra_texts if t and t not in seen]
    return texts


def unlocated_quotations(text: str, corpus: list[str]) -> list[str]:
    """The quotations of ``text`` whose words occur, in any recognised form (exact, normalised, elided, a form difference,
    a long elision), in none of ``corpus``: invented or altered quotations."""
    from ..adapters.markdown import find_quotation_spans
    from ..translate.grounding import locate_long_elision, locate_quotation, locate_quotation_inexact
    out: list[str] = []
    for _s, _e, inner in find_quotation_spans(text):
        q = inner.strip().strip(".,;:!?").strip()
        if not q or not re.search(r"[^\W\d_]", q):
            continue
        if not any(locate_quotation(q, t) is not None or locate_quotation_inexact(q, t) is not None or locate_long_elision(q, t) is not None for t in corpus):
            out.append(q)
    return list(dict.fromkeys(out))


def meaningful(text: Optional[str]) -> bool:
    """A reason or basis counts only if it says something: whitespace, punctuation
    and placeholder strings ('n/a', '-', 'see above', ...) do not."""
    if not text:
        return False
    t = " ".join(text.split()).casefold()
    if not t or t in PLACEHOLDERS:
        return False
    return sum(ch.isalpha() for ch in t) >= 3


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


#: A scale word right after a figure ("6.1 million"): part of the figure, so "6.1 billion" is not "6.1 million".
_SCALE_AFTER_RE = re.compile(r"\s*(thousand|million|billion|trillion)s?\b", re.IGNORECASE)


class _Figure:
    """One figure or date of a text: ``keys`` are its equivalent spellings (the numeral; with a scale word also
    "<numeral> <scale>" and the scaled value, so "a million" meets "1 million" and "1,000,000"), ``mantissa`` and
    ``scale`` its parts, ``label`` how a finding shows it (the numeral, a month-year, or the words as written)."""
    __slots__ = ("keys", "mantissa", "scale", "label")

    def __init__(self, mantissa: str, scale: Optional[str], label: str, extra: tuple[str, ...] = ()) -> None:
        from fractions import Fraction
        keys = {mantissa, *extra}
        if scale:
            keys.add(f"{mantissa} {scale}")
            try:
                v = Fraction(mantissa) * _SCALES[scale]
                keys.add(_fmt(v.numerator, v.denominator))
            except (ValueError, ZeroDivisionError):
                pass
        self.keys = frozenset(keys)
        self.mantissa = mantissa
        self.scale = scale
        self.label = label


def _figures(text: str) -> list[_Figure]:
    """Every figure and date of ``text``: numerals (thousands separators removed) with any scale word after them,
    figures written in words (:func:`_word_figures`), and month-year dates."""
    plain = _THOUSANDS_RE.sub("", _LIST_MARKER_RE.sub(" ", text))
    out: list[_Figure] = []
    masked = plain
    for start, end, mantissa, scale, surface in _word_figures(plain):
        out.append(_Figure(mantissa, scale, " ".join(surface.split())))
        masked = masked[:start] + " " * (end - start) + masked[end:]
    for m in _FIGURE_RE.finditer(masked):
        sc = _SCALE_AFTER_RE.match(masked, m.end())
        out.append(_Figure(m.group(0), sc.group(1).casefold() if sc else None, m.group(0)))
    out += [_Figure(f"{m.group(1).casefold()} {m.group(2)}", None, f"{m.group(1).casefold()} {m.group(2)}") for m in _MONTH_YEAR_RE.finditer(plain)]
    return out


def figure_spellings(text: str) -> list[tuple[str, frozenset[str]]]:
    """``(label, spellings)`` for every figure and date of ``text`` (digits, words, scale words, month-years): two figures
    are the same when their spellings meet ("a million", "1 million" and "1,000,000")."""
    return [(f.label, f.keys) for f in _figures(text)]


def figure_tokens(text: str) -> set[str]:
    """The figures of ``text`` as tokens, the units of a figure/date fidelity comparison between a synthesized claim and
    its sources: numerals (thousands separators removed), month-year tokens, and figures written in words as their value
    ("two million" -> "2", "a tenth" -> "0.1")."""
    return {f.mantissa for f in _figures(text)}


def _figure_differences(synthesized_text: str, source_texts: list[str]) -> tuple[list[str], list[str], list[str]]:
    """``(introduced, dropped, rescaled)``: the synthesized claim's figures that occur in no source under any spelling,
    the sources' figures the claim does not state, and the claim's figures whose scale word differs from every scale the
    sources state that numeral with ("6.1 billion" where the sources say "6.1 million"; a numeral the sources state
    without a scale word is not held to one, since "from 1.9 to 6.1 million" elides the first figure's scale)."""
    syn = _figures(synthesized_text)
    src = [f for t in source_texts for f in _figures(t)]
    src_keys = set().union(*(f.keys for f in src)) if src else set()
    syn_keys = set().union(*(f.keys for f in syn)) if syn else set()
    introduced = _sorted_tokens({f.label for f in syn if not (f.keys & src_keys)})
    dropped = _sorted_tokens({f.label for f in src if not (f.keys & syn_keys)})
    rescaled: list[str] = []
    for f in syn:
        if not f.scale or not (f.keys & src_keys) or (f.keys - {f.mantissa}) & src_keys:
            continue
        scales = sorted({g.scale for g in src if g.mantissa == f.mantissa and g.scale})
        if scales and f.scale not in scales:
            shown = f.label if f.label != f.mantissa else f"{f.mantissa} {f.scale}"
            rescaled.append(f"'{shown}' where the cited sources state {f.mantissa} {' or '.join(scales)} (a changed scale word)")
    return introduced, dropped, sorted(set(rescaled))


def _sorted_tokens(tokens: set[str]) -> list[str]:
    return sorted(tokens, key=lambda s: (len(s), s))


def report_set_findings(reports: list[SpecialistReport]) -> tuple[list[IntegrityFinding], set[str]]:
    """Duplicate report ids (INT-LEDGER-013) and claim ids shared across reports
    (INT-LEDGER-014). Returns the findings and the set of colliding claim ids, which
    no ledger accounting may silently resolve."""
    f: list[IntegrityFinding] = []
    by_rid: dict[str, list[SpecialistReport]] = {}
    for r in reports:
        by_rid.setdefault(r.report_id, []).append(r)
    for rid, rs in by_rid.items():
        if len(rs) > 1:
            f.append(IntegrityFinding(code="INT-LEDGER-013", severity="error", message=f"report id {rid!r} is used by {len(rs)} reports (agents {[r.agent_id for r in rs]}); report-level provenance is ambiguous", report_ids=[rid], agent_ids=sorted({r.agent_id for r in rs}), claim_ids=[c.claim_id for r in rs for c in r.claims]))
    owners: dict[str, list[SpecialistReport]] = {}
    for r in reports:
        for c in r.claims:
            owners.setdefault(c.claim_id, []).append(r)
    colliding: set[str] = set()
    for cid, rs in owners.items():
        if len({r.report_id for r in rs}) > 1 or len(rs) > 1:
            colliding.add(cid)
            f.append(IntegrityFinding(code="INT-LEDGER-014", severity="error", message=f"claim id {cid!r} appears in reports {[r.report_id for r in rs]}; neither copy can be accounted for by id", claim_ids=[cid], report_ids=[r.report_id for r in rs], agent_ids=sorted({r.agent_id for r in rs})))
    return f, colliding


def _source_index(reports: list[SpecialistReport], colliding: set[str]) -> tuple[dict[str, ClaimRecord], dict[str, str]]:
    idx: dict[str, ClaimRecord] = {}
    report_of: dict[str, str] = {}
    for r in reports:
        for c in r.claims:
            if c.claim_id in colliding:
                continue
            idx[c.claim_id] = c
            report_of[c.claim_id] = r.report_id
    return idx, report_of


def _report_context(reports: list[SpecialistReport], known: list[ClaimRecord]) -> tuple[str, ...]:
    """The other claim texts of the reports a synthesized claim cites (what the name-partner rule reads besides the
    cited claims: a report that states "the Ten Hours Act of 1847" in a claim the synthesized claim does not cite still
    says which year that name belongs to)."""
    ids = {c.claim_id for c in known}
    out: list[str] = []
    for r in reports:
        if any(c.claim_id in ids for c in r.claims):
            out.extend(c.claim_text for c in r.claims if c.claim_id not in ids)
    return tuple(out)


def check_synthesis_ledger(reports: list[SpecialistReport], synthesis: Synthesis, *, extra_texts: tuple[str, ...] | list[str] = ()) -> list[IntegrityFinding]:
    """The ledger accounting of ``synthesis`` against ``reports``. ``extra_texts`` are further texts a synthesized
    quotation may legitimately come from (the channel passes the requests' supplied texts and user inputs)."""
    f: list[IntegrityFinding] = []
    sid = [synthesis.synthesis_id]
    report_ids = {r.report_id for r in reports}
    missing_reports = [rid for rid in synthesis.source_report_ids if rid not in report_ids]
    if missing_reports:
        f.append(IntegrityFinding(code="INT-LEDGER-000", severity="error", message=f"synthesis cites reports that were not provided: {missing_reports}", report_ids=missing_reports, agent_ids=[synthesis.combinator_agent_id], claim_ids=sid))
    for r in reports:
        if r.request_id != synthesis.request_id or r.task_id != synthesis.task_id:
            f.append(IntegrityFinding(code="INT-LEDGER-008", severity="error", message=f"report {r.report_id} belongs to another request/task ({r.request_id}/{r.task_id}) than the synthesis ({synthesis.request_id}/{synthesis.task_id})", report_ids=[r.report_id], agent_ids=[r.agent_id], claim_ids=[c.claim_id for c in r.claims]))

    set_findings, colliding = report_set_findings(reports)
    f += set_findings
    sources, report_of = _source_index(reports, colliding)
    all_source_ids = {c.claim_id for r in reports for c in r.claims}
    synthesized_ids = {s.claim_id for s in synthesis.claims}
    accounted: set[str] = set()
    listed_reports = set(synthesis.source_report_ids)

    for sc in synthesis.claims:
        if sc.claim_id in all_source_ids:
            f.append(IntegrityFinding(code="INT-LEDGER-015", severity="error", message=f"synthesized claim reuses the source claim id {sc.claim_id!r} (report {report_of.get(sc.claim_id, '?')}); a changed claim must be a NEW record linked to its source, never a rewrite under the same id", claim_ids=[sc.claim_id], report_ids=[report_of[sc.claim_id]] if sc.claim_id in report_of else [], agent_ids=[synthesis.combinator_agent_id]))
        unknown = [s for s in sc.source_claim_ids if s not in sources and s not in colliding]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"synthesized claim cites unknown source claims {unknown}", claim_ids=[sc.claim_id] + unknown, agent_ids=[synthesis.combinator_agent_id]))
        known = [sources[s] for s in sc.source_claim_ids if s in sources]
        foreign = sorted({report_of[c.claim_id] for c in known if report_of[c.claim_id] not in listed_reports})
        if foreign:
            f.append(IntegrityFinding(code="INT-LEDGER-016", severity="warning", message=f"synthesized claim cites source claims from reports {foreign} that the synthesis does not list in source_report_ids", claim_ids=[sc.claim_id] + [c.claim_id for c in known if report_of[c.claim_id] in foreign], report_ids=foreign))
        accounted.update(s for s in sc.source_claim_ids if s not in colliding)
        if sc.transformation == "new" or not sc.source_claim_ids:
            f.append(IntegrityFinding(code="INT-LEDGER-005", severity="error", message="synthesized claim has no source claim: the combinator introduced content no specialist asserted", claim_ids=[sc.claim_id], agent_ids=[synthesis.combinator_agent_id]))
            continue
        if sc.transformation == "dropped":
            f.append(IntegrityFinding(code="INT-LEDGER-009", severity="error", message="a present synthesized claim cannot have transformation 'dropped'", claim_ids=[sc.claim_id]))
        if not known:
            continue
        known_ids = [c.claim_id for c in known]
        material_sources = [c for c in known if c.materiality == "material"]
        weakest = min(CERTAINTY_RANK[c.certainty] for c in known)
        if CERTAINTY_RANK[sc.certainty] > weakest:
            f.append(IntegrityFinding(code="INT-LEDGER-003", severity="error", message=f"certainty inflated: synthesis says {sc.certainty!r} but the weakest source is rank {weakest} ({[c.certainty for c in known]})", claim_ids=[sc.claim_id] + known_ids))
        have = {(r.document_id, r.locator): r for r in sc.evidence_refs}
        lost = [c.claim_id for c in material_sources if any((r.document_id, r.locator) not in have for r in c.source_refs)]
        if lost:
            f.append(IntegrityFinding(code="INT-LEDGER-004", severity="error", message=f"evidence references of material source claims {lost} were not preserved in the '{sc.transformation}' claim", claim_ids=[sc.claim_id] + lost, document_ids=sorted({r.document_id for c in material_sources if c.claim_id in lost for r in c.source_refs})))
        altered = sorted({c.claim_id for c in known for r in c.source_refs if (r.document_id, r.locator) in have and r.excerpt and have[(r.document_id, r.locator)].excerpt and _norm(r.excerpt) != _norm(have[(r.document_id, r.locator)].excerpt)})
        if altered:
            f.append(IntegrityFinding(code="INT-LEDGER-020", severity="warning", message=f"evidence excerpt differs from the source's under the same (document, locator) for source claims {altered}", claim_ids=[sc.claim_id] + altered, document_ids=sorted({r.document_id for c in known if c.claim_id in altered for r in c.source_refs})))
        introduced, dropped_figures, rescaled = _figure_differences(sc.text, [c.claim_text for c in known])
        repaired = figure_pairing_differences(sc.text, [c.claim_text for c in known], context_texts=_report_context(reports, known))
        if introduced or rescaled or repaired:
            # One finding per synthesized claim: the figures no source states, the figures stated with another scale word,
            # and the figures every source states but with another event (a swap passes a token-set comparison, so the
            # pairing is compared too). Figures written in words count like figures in digits.
            parts: list[str] = []
            if introduced:
                parts.append(f"states figures or dates {introduced} that occur in none of its cited sources {known_ids}: a changed or introduced figure or date")
            if rescaled:
                parts.append(f"changes the scale of figures of its cited sources {known_ids}: " + "; ".join(rescaled))
            if repaired:
                parts.append(f"re-pairs figures or dates between events relative to its cited sources {known_ids}: " + "; ".join(repaired))
            f.append(IntegrityFinding(code="INT-LEDGER-023", severity="error", message=f"synthesized claim ('{sc.transformation}') " + ", and ".join(parts) + ", whatever the transformation label", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        invented = unlocated_quotations(sc.text, _quotation_corpus(reports, known, tuple(extra_texts)))
        if invented:
            f.append(IntegrityFinding(code="INT-LEDGER-025", severity="error", message=f"synthesized claim ('{sc.transformation}') quotes {[q[:80] for q in invented[:8]]}, which occur in none of the supplied texts, the cited reports or its cited source claims {known_ids}: an altered or invented quotation", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        inverted = meaning_inversions(sc.text, [c.claim_text for c in known], sc.transformation)
        if inverted:
            f.append(IntegrityFinding(code="INT-LEDGER-027", severity="error", message=f"synthesized claim ('{sc.transformation}') states the opposite of its cited source {known_ids}: "
                                      + "; ".join(inverted) + ", whatever its formal conclusion", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        substituted = substituted_names(sc.text, [c.claim_text for c in known], sc.transformation, context_texts=_report_context(reports, known))
        if substituted:
            f.append(IntegrityFinding(code="INT-LEDGER-029", severity="error", message=f"synthesized claim ('{sc.transformation}') names an actor its cited sources {known_ids} do not "
                                      "name (rule name-substitution): " + "; ".join(substituted) + ", whatever its formal conclusion: who acted is content the claim it "
                                      "cites does not state", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        neg_error = any(d.startswith("it adds a negation") for d in inverted)  # the warning's description is the error's
        changed_meaning = [d for d in meaning_differences(sc.text, [c.claim_text for c in known], sc.transformation)
                           if not (neg_error and d.startswith("it adds a negation"))]
        if changed_meaning:
            f.append(IntegrityFinding(code="INT-LEDGER-026", severity="warning", message=f"synthesized claim ('{sc.transformation}') may say something other than its cited sources {known_ids}: " + "; ".join(changed_meaning) + " (lexical comparison; not formally checked)", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        if dropped_figures and (sc.transformation in _EQUIVALENCE_LABELS or sc.transformation in _COMBINING_LABELS):
            how = "content was dropped under an equivalence label" if sc.transformation in _EQUIVALENCE_LABELS else "the dated or quantified content of those sources was left out of the combined claim"
            f.append(IntegrityFinding(code="INT-LEDGER-024", severity="warning", message=f"figures or dates {dropped_figures} of the cited sources {known_ids} do not appear in the '{sc.transformation}' synthesized claim; {how}", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        if sc.transformation == "carried":
            if len(known) != 1 or len(sc.source_claim_ids) != 1:
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message=f"claim marked 'carried' cites {len(sc.source_claim_ids)} sources; 'carried' requires exactly one source with identical text, use 'merged'", claim_ids=[sc.claim_id] + known_ids))
            elif _norm(known[0].claim_text) != _norm(sc.text):
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message="claim marked 'carried' but its text differs from the source; record it as 'paraphrased' or a new linked claim", claim_ids=[sc.claim_id, known[0].claim_id]))
        if material_sources and sc.materiality == "supporting":
            f.append(IntegrityFinding(code="INT-LEDGER-021", severity="warning", message=f"material source claims {[c.claim_id for c in material_sources]} became a 'supporting' synthesized claim: materiality downgraded", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))
        if material_sources and sc.transformation in ("merged", "generalized", "narrowed"):
            what = "content removed; formal coverage check required" if sc.transformation == "narrowed" else "formal synthesis-entailment check required"
            f.append(IntegrityFinding(code="INT-LEDGER-011", severity="info", message=f"material content produced by '{sc.transformation}' from {[c.claim_id for c in material_sources]}: {what}", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))

    for entry in synthesis.ledger:
        unknown = [s for s in entry.source_claim_ids if s not in sources and s not in colliding]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"ledger entry cites unknown source claims {unknown}", claim_ids=unknown, agent_ids=[synthesis.combinator_agent_id]))
        entry_ids = [s for s in entry.source_claim_ids if s not in colliding]
        if entry.transformation == "dropped":
            if not meaningful(entry.reason):
                f.append(IntegrityFinding(code="INT-LEDGER-006", severity="error", message=f"source claims dropped without a meaningful recorded reason (reason={entry.reason!r})", claim_ids=list(entry.source_claim_ids), agent_ids=[synthesis.combinator_agent_id]))
            else:
                material = [s for s in entry_ids if s in sources and sources[s].materiality == "material"]
                if material:
                    f.append(IntegrityFinding(code="INT-LEDGER-019", severity="warning", message=f"MATERIAL source claims {material} were dropped from the answer; recorded reason: {entry.reason!r}", claim_ids=material, agent_ids=[synthesis.combinator_agent_id]))
            accounted.update(entry_ids)
            continue
        target = next((s for s in synthesis.claims if s.claim_id == entry.synthesized_claim_id), None) if entry.synthesized_claim_id else None
        if target is None:
            f.append(IntegrityFinding(code="INT-LEDGER-012", severity="error", message=f"ledger entry '{entry.transformation}' for {list(entry.source_claim_ids)} points to synthesized claim {entry.synthesized_claim_id!r}, which does not exist in the synthesis; the sources are NOT accounted for", claim_ids=list(entry.source_claim_ids) + ([entry.synthesized_claim_id] if entry.synthesized_claim_id else []), agent_ids=[synthesis.combinator_agent_id]))
            continue
        not_cited = [s for s in entry.source_claim_ids if s not in target.source_claim_ids]
        if not_cited:
            f.append(IntegrityFinding(code="INT-LEDGER-012", severity="error", message=f"ledger entry '{entry.transformation}' says {not_cited} went into synthesized claim {target.claim_id!r}, but that claim does not cite them; the sources are NOT accounted for", claim_ids=not_cited + [target.claim_id], agent_ids=[synthesis.combinator_agent_id]))
        accounted.update(s for s in entry_ids if s in target.source_claim_ids)

    unaccounted_supporting: dict[str, list[str]] = {}
    for cid, c in sources.items():
        if cid in accounted:
            continue
        if c.materiality == "material":
            f.append(IntegrityFinding(code="INT-LEDGER-002", severity="error", message="material source claim is neither carried, transformed nor recorded as dropped", claim_ids=[cid], report_ids=[report_of[cid]], agent_ids=[c.agent_id]))
        elif c.claim_role != "other":  # a note (a from-memory label, a self-report, a task note) is not content a synthesis must account for
            unaccounted_supporting.setdefault(report_of[cid], []).append(cid)
    for rid, cids in unaccounted_supporting.items():  # one note per report: supporting claims need not be carried, the router is told which were not
        agent = next(r.agent_id for r in reports if r.report_id == rid)
        f.append(IntegrityFinding(code="INT-LEDGER-022", severity="info", message=f"{len(cids)} supporting source claim(s) of report {rid} are neither carried, transformed nor recorded as dropped: {cids[:12]}{'...' if len(cids) > 12 else ''}", claim_ids=cids, report_ids=[rid], agent_ids=[agent]))
    for r in reports:
        for c in r.claims:
            if c.claim_id in colliding:
                f.append(IntegrityFinding(code="INT-LEDGER-002" if c.materiality == "material" else "INT-LEDGER-022", severity="error" if c.materiality == "material" else "info", message=f"{c.materiality} source claim {c.claim_id!r} of report {r.report_id} cannot be accounted for: its id is shared with another report", claim_ids=[c.claim_id], report_ids=[r.report_id], agent_ids=[r.agent_id]))

    for conf in synthesis.conflicts:
        if conf.status == "resolved_with_basis" and not meaningful(conf.basis):
            f.append(IntegrityFinding(code="INT-CONFLICT-003", severity="error", message=f"conflict marked resolved without a meaningful documented basis (basis={conf.basis!r})", claim_ids=list(conf.claim_ids), agent_ids=[synthesis.combinator_agent_id]))
        unknown = [cid for cid in conf.claim_ids if cid not in all_source_ids and cid not in synthesized_ids]
        if unknown:
            f.append(IntegrityFinding(code="INT-LEDGER-001", severity="error", message=f"conflict record {conf.conflict_id} cites unknown claims {unknown}", claim_ids=unknown, agent_ids=[synthesis.combinator_agent_id]))

    f += _text_coverage(synthesis)
    return f


#: What the student-facing text may carry besides its synthesized claims (rule ``text-composition``): additive,
#: sequencing, contrast and framing connectives and markdown heading labels, which state nothing of their own. A causal
#: connective ("because", "therefore", "as a result") asserts a relation no synthesized claim states, so it is content;
#: so is a negation, a hedge or any other word.
_CONNECTIVE_PHRASES = tuple(sorted((
    "and", "also", "furthermore", "moreover", "additionally", "besides", "likewise", "similarly", "meanwhile", "then", "next",
    "first", "second", "third", "firstly", "secondly", "thirdly", "finally", "lastly", "however", "but", "yet", "whereas", "while",
    "overall", "in addition", "by contrast", "in contrast", "on the other hand", "in summary", "in conclusion", "to summarise",
    "to summarize", "to sum up", "in short", "in brief", "at the same time", "as well as", "as well", "too", "equally", "still",
    "nevertheless", "nonetheless", "alternatively", "summary", "conclusion", "overview", "introduction", "answer", "key points",
), key=len, reverse=True))
_CONNECTIVE_RE = re.compile(r"(?<!\w)(?:" + "|".join(re.escape(p).replace(r"\ ", r"\s+") for p in _CONNECTIVE_PHRASES) + r")(?!\w)")
_CONTENT_WORD_RE = re.compile(r"[^\W_]+")


def text_outside_claims(text: str, claim_texts: list[str]) -> list[str]:
    """The stretches of ``text`` (normalised: whitespace collapsed, case folded, list markers removed) that state
    something no synthesized claim states (rule ``text-composition``): every claim text is removed where it occurs as a
    whole (its final sentence mark optional), then every connective of :data:`_CONNECTIVE_PHRASES`; a stretch still
    holding a letter or digit is returned. Empty when the text is a composition of its claims and connectives."""
    body = _norm(_LIST_MARKER_RE.sub(" ", text or ""))
    forms = sorted({_norm(_LIST_MARKER_RE.sub(" ", c)).rstrip(" .!?;:") for c in claim_texts if c and c.strip()}, key=len, reverse=True)
    for form in forms:
        if not form:
            continue
        pat = (r"(?<!\w)" if form[0].isalnum() or form[0] == "_" else "") + re.escape(form) + (r"(?!\w)" if form[-1].isalnum() or form[-1] == "_" else "")
        body = re.sub(pat, "\x00", body)
    out: list[str] = []
    for part in body.split("\x00"):
        rest = _CONNECTIVE_RE.sub(" ", part)
        if _CONTENT_WORD_RE.search(rest):
            out.append(" ".join(part.split()).strip(" .,;:!?-–—*#>()[]\"'“”‘’"))
    return [x for x in out if x]


def _text_coverage(synthesis: Synthesis) -> list[IntegrityFinding]:
    """The student reads Synthesis.text, the Overseer reads the claim ledger; the two
    must agree. Each synthesized claim's text must occur in the student-facing text
    (INT-LEDGER-017), every figure or date the text states (digits, number words, scale
    words, month-years: ``figure_spellings``) must be stated by some synthesized claim
    under some spelling (INT-LEDGER-023, error: "1834" or "under ten" where every claim
    says "1833" and "under nine" miscommunicates to the student while every claim stays
    faithful), every numeric literal in the text must occur in some claim (INT-LEDGER-018,
    warning; list markers such as '1.' are ignored), the text must
    pair its figures and dates with events as the synthesized claims do (INT-LEDGER-023), and the
    text must be a composition of its synthesized claims and connectives (INT-LEDGER-028, error, rule
    ``text-composition``: a negation, an antonym, an exchanged name, a dropped qualifier or an added
    sentence in the text, with every claim faithful, miscommunicates to the student)."""
    f: list[IntegrityFinding] = []
    claim_keys = set().union(*(fig.keys for c in synthesis.claims for fig in _figures(c.text))) if synthesis.claims else set()
    stated = _sorted_tokens({fig.label for fig in _figures(synthesis.text) if not (fig.keys & claim_keys)})
    if stated:
        f.append(IntegrityFinding(code="INT-LEDGER-023", severity="error", message=f"the student-facing text states figures or dates {stated} that no synthesized claim states "
                                  "under any spelling: a changed or introduced figure or date in what the student reads", claim_ids=[synthesis.synthesis_id],
                                  agent_ids=[synthesis.combinator_agent_id]))
    body = _norm(synthesis.text)
    absent = [c.claim_id for c in synthesis.claims if _norm(c.text) not in body]
    if absent:
        f.append(IntegrityFinding(code="INT-LEDGER-017", severity="warning", message=f"synthesized claims {absent} do not appear in the student-facing text; the ledger does not describe what the student reads", claim_ids=absent, agent_ids=[synthesis.combinator_agent_id]))
    extra = text_outside_claims(synthesis.text, [c.text for c in synthesis.claims])
    if extra:
        shown = "; ".join(repr(x[:80]) for x in extra[:3]) + (f" (and {len(extra) - 3} more)" if len(extra) > 3 else "")
        f.append(IntegrityFinding(code="INT-LEDGER-028", severity="error", message=f"the student-facing text is not composed of its synthesized claims (rule text-composition): it states {shown}, "
                                  "which no synthesized claim states" + (f"; synthesized claims {absent} are absent from it, so the text says something else in their place" if absent else "")
                                  + ": the ledger does not describe what the student reads", claim_ids=[synthesis.synthesis_id] + absent, agent_ids=[synthesis.combinator_agent_id]))
        repaired = figure_pairing_differences(synthesis.text, [c.text for c in synthesis.claims])
        if repaired:
            f.append(IntegrityFinding(code="INT-LEDGER-023", severity="error", message="the student-facing text re-pairs figures or dates between events relative to the synthesized claims it presents: "
                                      + "; ".join(repaired), claim_ids=[synthesis.synthesis_id] + absent, agent_ids=[synthesis.combinator_agent_id]))
    text_wo_markers = _LIST_MARKER_RE.sub(" ", synthesis.text)
    in_claims = {m.group(0) for c in synthesis.claims for m in _NUMBER_RE.finditer(c.text)}
    stray = sorted({m.group(0) for m in _NUMBER_RE.finditer(text_wo_markers)} - in_claims, key=lambda s: (len(s), s))
    if stray:
        f.append(IntegrityFinding(code="INT-LEDGER-018", severity="warning", message=f"numeric literals {stray} appear in the student-facing text but in no synthesized claim; unledgered content", claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id]))
    return f
