"""Claim-ledger accounting for the information-preserving combinator.

Structural accounting is necessary but not sufficient (context document, section 4):
it catches dropped, orphaned, inflated and evidence-stripped claims, id collisions
between reports and between the source and synthesis namespaces, ledger entries that
point nowhere, and student-facing text that diverges from the claim ledger. Whether a
synthesized claim FOLLOWS from its sources is a formal question answered in
``cross_check.py``.

Figures for the synthesis-fidelity comparison (INT-LEDGER-0xx) include scientific notation
(``3.0e8``, ``6.67 × 10⁻¹¹``, ``1.2*10**6``), read exactly by the STEM number scanner
(``stem.numbers``): such a figure is one figure whose spellings are its exact decimal value
and its normalised mantissa-exponent form, so ``3.0e8``, ``3.0 × 10⁸`` and ``300000000`` are
the same figure and ``6.67 × 10⁻¹¹`` is never read as 6.67 and 10. Figures with no exponent
are read as before.
"""
from __future__ import annotations

import re
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
#: A figure in scientific notation: a mantissa, then an e-exponent or a times sign and a power of ten.
_SCI_FIGURE_RE = re.compile(r"(?<![\w.])[-−]?\d+(?:\.\d+)?(?:[eE][-+−]?\d{1,7}|\s?[×xX*·]\s?10(?:\^\{?[-−]?\d{1,7}\}?|\*\*[-−]?\d{1,7}|[⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,7}))(?!\w)(?!\.\d)")
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


def _word_figures(text: str) -> list[tuple[int, int, str, Optional[str], str]]:
    """``(start, end, mantissa, scale or None, surface)`` for every figure written in words in ``text``."""
    out: list[tuple[int, int, str, Optional[str], str]] = []
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
    return out


def _words_as_digits(text: str) -> str:
    """``text`` with its figures written in words rewritten as digits ("close to a million" -> "close to 1 million",
    "roughly a tenth" -> "roughly 0.1"), so the pairing and dating readers see them as figures."""
    figs = _word_figures(text)
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
#: Function words and unit words, never an event word a figure is paired with.
_PARTNER_STOP = frozenset(("the a an and or of to in on for with by is are was were be been being this that these those as at from it its into their there "
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


def _plain_for_pairs(text: str) -> str:
    """The text the pairing readers work on: list markers and thousands separators removed, figures written in words
    rewritten as digits (so "roughly a tenth" pairs like "about 13 per cent")."""
    return _words_as_digits(_THOUSANDS_RE.sub("", _LIST_MARKER_RE.sub(" ", text)))


def _is_numeral(tok: str) -> bool:
    return tok[0].isdigit()


def _figure_kind(tokens: list[str], i: int) -> str:
    """``year`` (a four-digit year), ``day`` (1-31 next to a month name) or ``quantity``: a swap is looked for
    between figures of one kind only, so a seat count is never 'exchanged' with the year it was won."""
    tok = tokens[i]
    if re.fullmatch(r"1\d{3}|20\d{2}", tok):
        return "year"
    if tok.isascii() and tok.isdigit() and 1 <= int(tok) <= 31:  # a superscript '¹⁹' is a digit to isdigit() but no day
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


def _figure_partners(text: str) -> tuple[set[tuple[str, str]], dict[str, str], dict[str, str]]:
    """``(pairs, kinds, surface)``: every ``(figure, partner)`` of ``text``, the kind of each figure, and the word each
    stemmed partner was first seen as. A partner is an event word within :data:`_WORD_WINDOW` tokens of the figure in
    the same clause (light-stemmed, prefixed ``w:``) that has no nearer figure of the same kind, or another figure within
    :data:`_FIGURE_WINDOW` tokens (prefixed ``f:``). Unit words and function words are not partners."""
    pairs: set[tuple[str, str]] = set()
    kinds: dict[str, str] = {}
    surface: dict[str, str] = {}
    for clause in _clauses(text):
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
    return pairs, kinds, surface


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
    word, or one that keeps one of its own events, is a merge, not a re-pairing."""
    moved: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for a, p in sorted(syn_pairs):
        if not p.startswith("w:") or p[2:] in _MONTH_STEMS or a not in src_figures or a in exchanged or (a, p) in src_pairs:
            continue
        holders = tuple(sorted({b for b, q in src_pairs if q == p and b != a and src_kinds.get(b) == kinds.get(a)}))
        if not holders or any((b, p) in syn_pairs for b in holders):
            continue
        own = _event_words(src_pairs, a)
        if not own or own & _event_words(syn_pairs, a):
            continue
        moved.setdefault((a, holders), []).append(p)
    out: list[str] = []
    for (a, holders), words in sorted(moved.items()):
        shown = ", ".join(_partner_label(p, surface) for p in words)
        own = ", ".join(_partner_label(p, surface) for p in sorted(_event_words(src_pairs, a)))
        out.append(f"'{a}' is stated with {shown}, where the cited sources pair {shown} only with {', '.join(repr(b) for b in holders)} and state '{a}' with {own} (re-paired)")
    return out


def figure_pairing_differences(synthesized_text: str, source_texts: list[str]) -> list[str]:
    """How ``synthesized_text`` pairs its figures and dates differently from ``source_texts`` while using the same
    tokens: a combinator that swaps two dates or two figures between events passes a token-set comparison, so the
    pairing is compared as well. Three shapes are read, each decided on the sources' own statements:

    * an exchange: figure A stands with event word (or figure) P and figure B with Q, where the sources state B with P
      and A with Q (A and B of the same kind: years, days of a month, or quantities);
    * a one-sided re-pairing: A stands with event word P, which the sources pair only with B, and A has left every
      event the sources state it with (:func:`_one_sided_repairings`);
    * a dated quantity ``<q> ... in [<month>] <year>`` that the sources date to another month or year;
    * a ``from X to Y`` pair the sources state as ``from Y to X``.

    Only figures that occur in the sources are compared (a figure in no source is the plain INT-LEDGER-023 case), and
    a year that carries several quantities in the sources is not held to any one of them (a merge may date several
    items at once). Returns one description per difference; empty when every pairing is the sources' own."""
    syn_pairs, kinds, surface = _figure_partners(synthesized_text)
    src_pairs: set[tuple[str, str]] = set()
    src_kinds: dict[str, str] = {}
    for t in source_texts:
        p, k, sf = _figure_partners(t)
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
    out += _one_sided_repairings(syn_pairs, src_pairs, kinds, src_kinds, src_figures, exchanged, surface)
    out += _redated_quantities(synthesized_text, source_texts, exchanged, src_figures)
    src_from_to = set().union(*(_from_to_pairs(t) for t in source_texts)) if source_texts else set()
    for a, b in sorted(_from_to_pairs(synthesized_text)):
        if (a, b) not in src_from_to and (b, a) in src_from_to:
            out.append(f"'from {a} to {b}' reverses the cited sources' 'from {b} to {a}'")
    return _with_word_labels(out, [synthesized_text, *source_texts])


def _with_word_labels(descriptions: list[str], texts: list[str]) -> list[str]:
    """Show a figure written in words as the words, with the value the readers compared ("'a tenth' (0.1)")."""
    labels: dict[str, str] = {}
    for t in texts:
        for _s, _e, mantissa, _scale, surface in _word_figures(_THOUSANDS_RE.sub("", t)):
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


def _exact_decimal(value) -> str:
    """The exact decimal text of a terminating rational (``6.67e-11`` -> ``0.0000000000667``), else its ``a/b`` form."""
    num, den = value.numerator, value.denominator
    rest, twos, fives = den, 0, 0
    while rest % 2 == 0:
        rest, twos = rest // 2, twos + 1
    while rest % 5 == 0:
        rest, fives = rest // 5, fives + 1
    if rest != 1:
        return f"{num}/{den}"
    places = max(twos, fives)
    digits = str(abs(num) * 10 ** places // den).rjust(places + 1, "0")
    sign = "-" if num < 0 else ""
    return sign + (digits if not places else digits[:-places] + "." + digits[-places:])


def _scientific_figures(text: str) -> list[tuple[int, int, Optional[str], frozenset[str], str]]:
    """``(start, end, exact decimal, spellings, surface)`` of every figure in scientific notation, read exactly by the
    STEM number scanner. A figure beyond the scanner's bounds (an exponent over 99, over 30 digits) is not read, and
    its parts are not read as figures either (the caller masks every span returned; the exact decimal is None for it)."""
    from ..stem.normalize import reading_view
    from ..stem.numbers import scan_number
    out: list[tuple[int, int, Optional[str], frozenset[str], str]] = []
    for m in _SCI_FIGURE_RE.finditer(text):
        surface = m.group(0)
        body = reading_view(surface)
        sign = -1 if body.startswith("-") else 1
        body = body.lstrip("-")
        scan = scan_number(body, 0, orig=body)
        if scan is None or scan.number is None or scan.end != len(body) or not scan.number.scientific:
            out.append((m.start(), m.end(), None, frozenset(), " ".join(surface.split())))  # unreadable: masked, not a figure
            continue
        value = sign * scan.number.value
        exact = _exact_decimal(value)
        mant = scan.number.value / (10 ** scan.number.exponent) if scan.number.exponent >= 0 else scan.number.value * (10 ** -scan.number.exponent)
        normal = f"{'-' if sign < 0 else ''}{_exact_decimal(mant)}e{scan.number.exponent}"
        out.append((m.start(), m.end(), exact, frozenset({exact, normal}), " ".join(surface.split())))
    return out


def _figures(text: str) -> list[_Figure]:
    """Every figure and date of ``text``: numerals (thousands separators removed) with any scale word after them,
    figures in scientific notation (one figure each, :func:`_scientific_figures`), figures written in words
    (:func:`_word_figures`), and month-year dates."""
    plain = _THOUSANDS_RE.sub("", _LIST_MARKER_RE.sub(" ", text))
    out: list[_Figure] = []
    masked = plain
    if "10" in plain or "e" in plain or "E" in plain:
        for start, end, exact, spellings, surface in _scientific_figures(plain):
            if exact is not None:
                out.append(_Figure(exact, None, surface, tuple(spellings)))
            masked = masked[:start] + " " * (end - start) + masked[end:]
    for start, end, mantissa, scale, surface in _word_figures(masked):
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
        repaired = figure_pairing_differences(sc.text, [c.claim_text for c in known])
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
        changed_meaning = meaning_differences(sc.text, [c.claim_text for c in known], sc.transformation)
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


def _text_coverage(synthesis: Synthesis) -> list[IntegrityFinding]:
    """The student reads Synthesis.text, the Overseer reads the claim ledger; the two
    must agree. Each synthesized claim's text must occur in the student-facing text
    (INT-LEDGER-017) and every numeric literal in the text must occur in some claim
    (INT-LEDGER-018; list markers such as '1.' are ignored)."""
    f: list[IntegrityFinding] = []
    body = _norm(synthesis.text)
    absent = [c.claim_id for c in synthesis.claims if _norm(c.text) not in body]
    if absent:
        f.append(IntegrityFinding(code="INT-LEDGER-017", severity="warning", message=f"synthesized claims {absent} do not appear in the student-facing text; the ledger does not describe what the student reads", claim_ids=absent, agent_ids=[synthesis.combinator_agent_id]))
    text_wo_markers = _LIST_MARKER_RE.sub(" ", synthesis.text)
    in_claims = {m.group(0) for c in synthesis.claims for m in _NUMBER_RE.finditer(c.text)}
    stray = sorted({m.group(0) for m in _NUMBER_RE.finditer(text_wo_markers)} - in_claims, key=lambda s: (len(s), s))
    if stray:
        f.append(IntegrityFinding(code="INT-LEDGER-018", severity="warning", message=f"numeric literals {stray} appear in the student-facing text but in no synthesized claim; unledgered content", claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id]))
    return f
