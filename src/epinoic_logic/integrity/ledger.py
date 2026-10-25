"""Claim-ledger accounting for the information-preserving combinator.

Structural accounting is necessary but not sufficient (context document, section 4):
it catches dropped, orphaned, inflated and evidence-stripped claims, id collisions
between reports and between the source and synthesis namespaces, ledger entries that
point nowhere, and student-facing text that diverges from the claim ledger. Whether a
synthesized claim FOLLOWS from its sources is a formal question answered in
``cross_check.py``.

Figures for the synthesis-fidelity comparison (INT-LEDGER-0xx) include scientific notation
(``3.0e8``, ``6.67 × 10⁻¹¹``, ``1.2*10**6``), read exactly by the STEM number scanner
(``stem.numbers``), so ``6.67 × 10⁻¹¹`` is never read as 6.67 and 10. Figures are compared as
typed quantities (docs/STEM_DESIGN.md, section 11.5): a numeral's exact value and its
significant figures are one spelling (``3.0e-2``, ``0.030`` and ``30e-3`` are the same figure:
the value 3/100 to two significant figures; ``0.03`` is the same value to one, a precision
change; ``0.031`` is another value), and the unit written after it is a separate attribute
(``2.0 g`` and ``2.0 kg`` state the same numeral of two different quantities, a unit change;
``2.0 g`` and ``0.0020 kg`` state one quantity in commensurable units, a conversion). The
trailing zeros of an integer written without a point are ambiguous, so ``300`` meets ``3e2``,
``3.0e2`` and ``3.00e2``. A value change, a precision change, a unit change and a change of
form only are distinct outcomes (:func:`figure_changes`).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import Optional, Sequence

from ..translate.contracts import ClaimRecord, SpecialistReport
from .contracts import CERTAINTY_RANK, IntegrityFinding, Synthesis

PLACEHOLDERS = frozenset({"n/a", "na", "-", ".", "tbd", "see above", "none", "null", "nil", "todo", "?", "x", "...", "as above", "same"})
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")
_LIST_MARKER_RE = re.compile(r"(?m)^\s*\(?\d{1,2}[.)]\s")
_COMMA_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}\b)")
#: A figure grouped in thousands with a space as the SI and the IB write it ("12 500", "1 250.75", with a thin space, a
#: no-break space, a narrow no-break space or LaTeX "\\,"): a first group of one to three digits that no digit, point or
#: comma precedes, then groups of exactly three digits (repair round 3, rerun-combinator-faults-8: "12 500" was read as
#: the two figures 12 and 500, so a synthesis writing a source's 12500 in SI grouping was charged INT-LEDGER-023).
_SPACE_THOUSANDS_RE = re.compile(r"(?<![\d.,])(\d{1,3})((?:(?: |\u2009|\u00a0|\u202f|\\,)\d{3})+)(?!\d)")
_GROUP_SPACE_RE = re.compile(r" |\u2009|\u00a0|\u202f|\\,")
#: The decimal digits grouped in threes after the point, as the SI and the IB write them ("0.000 42", "1.138 429…",
#: "0.047 79"): a first group of exactly three digits after the point, then groups of three, the last of one to three
#: digits, each after a space of the thousands groups (repair round 4, rerun-combinator-faults-8 variant: "0.000 42" was
#: read as the two figures 0.000 and 42, so a synthesis writing a source's 0.00042 in SI grouping was charged
#: INT-LEDGER-023).
_SPACE_DECIMALS_RE = re.compile(r"(?<![\d,])(\d+\.\d{3})((?:(?: |\u2009|\u00a0|\u202f|\\,)\d{3})*(?: |\u2009|\u00a0|\u202f|\\,)\d{1,3})(?!\d)(?![.,]\d)")
#: Thousands grouped with an apostrophe ("12'500", "1'250'000"): groups of exactly three digits.
_APOSTROPHE_THOUSANDS_RE = re.compile(r"(?<![\d.,'’])(\d{1,3})((?:['’]\d{3})+)(?![\d'’])")


def _ungrouped(text: str) -> str:
    """``text`` with its thousands separators removed: commas ("12,500"), the space groups of
    :data:`_SPACE_THOUSANDS_RE` ("12 500"), the apostrophe groups of :data:`_APOSTROPHE_THOUSANDS_RE` ("12'500") and the
    decimal groups of :data:`_SPACE_DECIMALS_RE` ("0.000 42"), so one figure is read as one figure however it is grouped."""
    text = _COMMA_THOUSANDS_RE.sub("", text)
    if "'" in text or "’" in text:
        text = _APOSTROPHE_THOUSANDS_RE.sub(lambda m: m.group(1) + re.sub("['’]", "", m.group(2)), text)
    if not any(ch in text for ch in (" ", "\u2009", "\u00a0", "\u202f", "\\")):
        return text
    text = _SPACE_THOUSANDS_RE.sub(lambda m: m.group(1) + _GROUP_SPACE_RE.sub("", m.group(2)), text)
    return _SPACE_DECIMALS_RE.sub(lambda m: m.group(1) + _GROUP_SPACE_RE.sub("", m.group(2)), text)
#: Minus glyphs other than the ASCII hyphen-minus, right before a digit: the minus sign U+2212, the hyphen, non-breaking
#: hyphen, figure dash and en dash (U+2010 to U+2013), the small and full-width hyphen-minus (:func:`_figures` gives a figure
#: after one its signed spelling as well).
_MINUS_GLYPH_RE = re.compile("[‐‑‒–−﹣－](?=[0-9])")
#: The glyphs that are minus signs and nothing else (U+2212 MINUS SIGN, U+FE63 SMALL HYPHEN-MINUS, U+FF0D FULLWIDTH
#: HYPHEN-MINUS): written as a sign (not after a letter or digit) they sign the figure exactly as the ASCII hyphen-minus
#: does, so "−0.5" restated as "0.5" is a change (repair round 2, combinator-faults-8 variant). The hyphens and dashes
#: (U+2010 to U+2013) are also range and punctuation marks: one signs the figure only in a sign's place, after a space,
#: a bracket or a relation sign with no figure before it ("the change was –12 K"; "2010 –2020" and "3 –5" are ranges or
#: differences), and otherwise the figure keeps both readings.
_MINUS_SIGNS = frozenset("−﹣－")
#: A unit symbol's exponent written with a caret: a letter or µ, then "^", an optional sign or bracket and one or two digits.
_CARET_UNIT_EXPONENT_RE = re.compile(r"([A-Za-zµμΩ])\^[({]?[-−]?\d{1,2}[)}]?(?!\d|\.\d)")
#: The count of a precision note: "2 s.f.", "3 sf", "2 d.p.", "1 dp", "3 significant figures", "2 decimal places" (the
#: count, in digits, right before the note's words).
_PRECISION_NOTE_RE = re.compile(r"(?<![\w.,])\d{1,2}(?=[ \t]*(?:s\.[ \t]?f\.?|sf|sig\.?[ \t]*figs?\.?|significant[ \t]+fig(?:ure)?s?|d\.[ \t]?p\.?|dp|decimal[ \t]+places?)(?![^\W\d_]))", re.IGNORECASE)
#: Accounting parentheses: an amount alone between brackets, written as money (a currency sign, or thousands separators:
#: "(1,250.75)", "($450)", "(£1.2 million)"). A bare small figure in brackets ("(2) per cent") is no accounting amount.
_ACCOUNTING_AMOUNT_RE = re.compile(r"\([ \t]?(?:[$£€¥][ \t]?(?P<a>\d[\d,]*(?:\.\d+)?)|(?P<b>\d{1,3}(?:,\d{3})+(?:\.\d+)?))"
                                   r"(?:[ \t]+(?:thousand|million|billion|trillion|bn))?[ \t]?\)", re.IGNORECASE)
#: A decrease stated in words right before or after a figure ("fell 12.50%", "a fall of 12.50%", "decreased by 3", "a 12.50%
#: drop"): the figure carries its negative spelling too, so "fell 12.50%" restates "−12.50%" for either minus glyph, while
#: "12.50%" alone or "rose 12.50%" for "−12.50%" is a change.
_DECREASE_BEFORE_RE = re.compile(
    r"\b(?:fell|fall|falls|fallen|falling|decreased|decrease|decreases|decreasing|declined|decline|declines|declining|dropped|drop|drops|dropping"
    r"|lowered|lower|down|loss|deficit|reduction|reduced|cut|negative|minus|shrank|shrunk|contracted|contraction)"
    r"\s+(?:(?:by|of|a|an|some|about|around|nearly|almost|roughly|approximately)\s+){0,2}[$£€¥]?$", re.IGNORECASE)
#: (security round 1) The white space around the per-cent unit read possessively: the unit and the word cannot begin with white
#: space, so the run's longest reading is the only one the rest can follow, and the same figures are read as decreases; the run
#: after a figure was split between two quantifiers before failing, once per figure (quadratic in the run)
#: (tests/integrity/test_security_round1_decrease.py).
_DECREASE_AFTER_RE = re.compile(r"\s*+(?:%|per\s*cent|percent)?+\s*+(?:fall|decrease|drop|decline|reduction|loss|cut|contraction)\b", re.IGNORECASE)
_DASH_SIGNS = frozenset("‐‑‒–")
#: A decade written in digits ("the 1840s", "the 1840's"): a date of its own, never the year it starts with, so a synthesis
#: that moves an event or a verdict to "the 1850s" states a date its sources do not (INT-LEDGER-023).
_DECADE_RE = re.compile(r"(?<![\w.])(1\d{2}0|20\d0)['’]?s(?!\w)")
#: A figure for the fidelity comparison: unlike ``_NUMBER_RE`` it accepts a sentence-final period after the numeral
#: ("printed in 1818."), because list markers are removed before it runs. A decade ("1840s") is one figure.
_FIGURE_RE = re.compile(r"(?<![\w.])(?:(?:1\d{2}0|20\d0)['’]?s(?!\w)|-?\d+(?:\.\d+)?(?!\w)(?!\.\d))")
#: A quantity written with a thousands separator that would read as a year once the separator is removed ("1,500 by 1840"):
#: the pairing readers see it as "1500.0", a quantity, so it is dated and paired like one (shown again as "1,500").
_YEARLIKE_QUANTITY_RE = re.compile(r"(?<![\w.,])(?:(1),(\d{3})|(2),(0\d{2}))(?![\d,]|\.\d)")
_YEARLIKE_SHOWN_RE = re.compile(r"(?<![\w.])(1\d{3}|20\d{2})\.0(?![\w.])")
#: A figure in scientific notation: a mantissa, then an e-exponent or a times sign and a power of ten.
#: The exponent may be written "10^-3", "10^{-3}" or "10^(−3)" (repair round 4, rerun-combinator-faults-8 variant: the
#: bracketed form of "10⁻³" was read as an introduced figure).
_SCI_FIGURE_RE = re.compile(r"(?<![\w.])[-−]?\d+(?:\.\d+)?(?:[eE][-+−]?\d{1,7}|\s?[×xX*·]\s?10(?:\^\{[-−]?\d{1,7}\}|\^\([-−]?\d{1,7}\)|\^[-−]?\d{1,7}|\*\*[-−]?\d{1,7}|[⁻]?[⁰¹²³⁴⁵⁶⁷⁸⁹]{1,7}))(?!\w)(?!\.\d)")
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
#: clause-breaking punctuation mark. The full stop of an initial or of "c." / "ca." ("Chester A. Arthur", "c. 1963") does
#: not end a clause, so a date is never cut from the event that follows the abbreviation.
_PAIR_TOKEN_RE = re.compile(r"\n|[,;:()]|(?<!\b[A-Z])(?<!\bc)(?<!\bca)[.](?=\s|$)|[!?](?=\s|$)|(?:1\d{2}0|20\d0)s(?!\w)|\d+(?:\.\d+)?~\d+(?:\.\d+)?|\d+(?:\.\d+)?"
                            r"|[^\W\d_]+(?:['’-][^\W\d_]+)*|[=≈→]|->|[×÷*/+^·⋅−<>≤≥±]|(?<=\s)-(?=\s)")
#: Clause breaks of the pairing reader: punctuation, a line break (a line of working is a statement of its own) and an
#: arrow (each member of a chain "1,000 → 500 → ... → 0" stands alone).
_PAIR_BREAKS = frozenset({",", ";", ":", "(", ")", ".", "!", "?", "\n", "→", "->"})
#: Arithmetic operators: a figure standing next to one is an operand of a calculation, not a quantity stated with the
#: words around it.
_PAIR_OPS = frozenset({"×", "÷", "*", "/", "+", "^", "·", "⋅", "−", "-", "<", ">", "≤", "≥"})
_PAIR_EQ = frozenset({"=", "≈"})
#: A line of working that continues the equation of the line before ("Break-even quantity = fixed costs ÷ contribution\n=
#: $6,000 ÷ $2.00 = 3,000 loaves").
_CONTINUED_LINE_RE = re.compile(r"\n[ \t]*(?=[=≈×÷*/+−])")
#: A bracket that holds nothing but an arithmetic expression ("(1 − 0.1675)", "(105 − 120)").
_ARITHMETIC_BRACKET_RE = re.compile(r"\(([\d\s.,×÷*/+\-−^·⋅%]+)\)")
#: A currency sign or code glued to a figure ("US$0.1190", "$1.60", "£2.5 million"): not part of the figure.
_CURRENCY_RE = re.compile(r"(?:\b(?:US|A|C|NZ|HK|S))?[$£€¥](?=\s?\d)")
#: Inline maths markup a worked answer may carry: delimiters and the commands for its operators.
_MATH_MARKUP = ((re.compile(r"\\times\b"), " × "), (re.compile(r"\\div\b"), " ÷ "), (re.compile(r"\\c?dot\b"), " · "), (re.compile(r"\\(?:l|c)?dots\b|\\ldots"), " "),
                (re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}"), r" \1 / \2 "), (re.compile(r"\\(?:left|right)\b"), " "), (re.compile(r"[{}]|\$(?!\s?\d)"), " "))
#: A data interval stated with its unit ("between 25 °C and 30 °C", "between 25 and 30 °C"): one figure of kind
#: 'interval' for the pairing reader ("25~30"), so a synthesis that moves the steepest rise to another interval re-pairs it.
_INTERVAL_UNIT = r"(?:°\s?[CF]|%|per\s+cent|km|cm|mm|m|kg|mg|g|ml|l|s|h|min|K|V|A|W|J|N|kPa|Pa|Hz|mol)\b"
_INTERVAL_RE = re.compile(r"\bbetween\s+(\d+(?:\.\d+)?)\s*(?:" + _INTERVAL_UNIT + r")?\s+and\s+(\d+(?:\.\d+)?)\s*(" + _INTERVAL_UNIT + ")")
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
                           "hundred around roughly nearly almost over under more less only also still even just such very between among within via each "
                           "both either").split())
#: Verbs of reasoning about a figure ("0.087 matches k", "4,200 loaves gives a margin"), not events it stands with: a
#: synthesis that says "matches" where the source says "agrees" moves no figure (compared on light stems).
_REASONING_STEMS = frozenset("match agre equal giv mean show impli imply becom correspond fit confirm satisfi satisfy yield check"
                             .split())
#: How far (in tokens of the same clause) an event word or another figure may stand from a figure to count as its partner.
_WORD_WINDOW = 4
_FIGURE_WINDOW = 4
#: "<quantity> ... <preposition> [<month>] <year>": the dated statement of a quantity; up to six unpunctuated words (figures among
#: them: "37.3 per cent and 230 seats in July 1932") may stand between the quantity and the preposition.
_DATED_QUANTITY_RE = re.compile(
    r"(?<![\w.])(?P<q>\d+(?:\.\d+)?)(?!\w)(?!\.\d)(?:[ \t]+[^\W_]+(?:[.'’-][^\W_]+)*){0,6}?[ \t]+(?:in|by|on|of|during|at|until|from|since|for|to)[ \t]+(?:early[ \t]+|late[ \t]+|mid-?[ \t]*)?"
    r"(?:(?P<m>" + "|".join(_MONTHS) + r")[ \t]+)?(?P<d>1\d{3}|20\d{2})(?!\w)(?!\.\d)", re.IGNORECASE)
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


#: Superscript and subscript digits and signs ("min⁻¹", "10³", "CO₂", "(1/2)⁴"): the exponent or index of a unit or a
#: power, never a figure of their own. ``str.isdigit()`` is true for them while ``int()`` refuses them, so the figure
#: readers fold them away before reading (a figure is read in decimal digits only, :func:`_is_numeral`).
_EXPONENT_MARKS_RE = re.compile("[\u00b2\u00b3\u00b9\u2070-\u209f]+")
#: Enclosed numbers ("①", "❶"): list markers, never figures.
_ENCLOSED_NUMBER_RE = re.compile("[\u2460-\u24ff\u2776-\u2793]")


def fold_exponent_marks(text: str) -> str:
    """``text`` with superscript and subscript digits and signs removed (an exponent or index: "min⁻¹" -> "min", "10³"
    -> "10") and enclosed numbers read as list markers (a space): what every figure reader of this module works on."""
    if not text or text.isascii():
        return text
    return _ENCLOSED_NUMBER_RE.sub(" ", _EXPONENT_MARKS_RE.sub("", text))


def _plain_for_pairs(text: str) -> str:
    """The text the pairing readers work on: superscript and subscript marks folded away (:func:`fold_exponent_marks`),
    list markers and thousands separators removed (a separated quantity that would then read as a year, "1,500",
    becomes "1500.0"), decades written "1840s", figures written in words rewritten as digits (so "roughly a tenth" pairs
    like "about 13 per cent")."""
    text = fold_exponent_marks(text)
    for rx, rep in _MATH_MARKUP:
        text = rx.sub(rep, text)
    text = _CURRENCY_RE.sub("", _CONTINUED_LINE_RE.sub(" ", text.replace("\r\n", "\n")))
    # Brackets that group operands ("= 15 million litres × (1 − 0.1675) = 12.49 million") are no clause break, so the
    # result stays with the quantity the line names; a bracket of prose stays one.
    for _ in range(3):
        text = _ARITHMETIC_BRACKET_RE.sub(lambda m: f" {m.group(1)} ", text)
    text = _INTERVAL_RE.sub(lambda m: f"{m.group(1)}~{m.group(2)} {m.group(3)}", text)
    text = _YEARLIKE_QUANTITY_RE.sub(lambda m: f"{m.group(1) or m.group(3)}{m.group(2) or m.group(4)}.0", _LIST_MARKER_RE.sub(" ", text))
    text = _DECADE_RE.sub(lambda m: m.group(1) + "s", text)
    return _words_as_digits(_ungrouped(text))


def _shown_figures(description: str) -> str:
    """A pairing description with the reader's "1500.0" shown as the "1,500" the texts write, and an interval "25~30"
    as "between 25 and 30"."""
    description = re.sub(r"'(\d+(?:\.\d+)?)~(\d+(?:\.\d+)?)'", r"'between \1 and \2'", description)
    return _YEARLIKE_SHOWN_RE.sub(lambda m: f"{m.group(1)[0]},{m.group(1)[1:]}", description)


def _is_numeral(tok: str) -> bool:
    """A numeral token: it starts with a decimal digit (``str.isdecimal``, never ``isdigit``, which is also true for a
    superscript '¹' that ``int()`` refuses)."""
    return tok[:1].isdecimal()


def _figure_kind(tokens: list[str], i: int) -> str:
    """``year`` (a four-digit year), ``day`` (1-31 next to a month name) or ``quantity``: a swap is looked for
    between figures of one kind only, so a seat count is never 'exchanged' with the year it was won."""
    tok = tokens[i]
    if "~" in tok:
        return "interval"
    if re.fullmatch(r"1\d{3}|20\d{2}", tok):
        return "year"
    if re.fullmatch(r"1\d{2}0s|20\d0s", tok):
        return "decade"
    # a superscript '¹⁹' is a digit to isdigit() but neither decimal nor a day; a day has at most two digits, so a figure of
    # thousands of digits is never converted (int() refuses more than 4,300 digits, which once ended the whole ledger check)
    if tok.isdecimal() and len(tok) <= 2 and 1 <= int(tok) <= 31:
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
        if tok in _PAIR_BREAKS or (not _is_numeral(tok) and tok.casefold() in _CLAUSE_BREAK_WORDS):
            sep = tok if tok in ",;:().!?" else ("." if tok == "\n" else ("→" if tok in ("→", "->") else "word"))
            for k, piece in enumerate(_equation_clauses(cur)):
                segments.append((piece, sep if k == 0 else "eq"))
            cur = []
            continue
        if _is_numeral(tok) and cur and cur[-1].casefold() == "per":
            continue  # "per 1,000", "per 100 ml": the unit of a rate, not a figure of the statement
        cur.append(tok)
    for piece in _equation_clauses(cur):
        segments.append((piece, "end"))
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


def _equation_clauses(tokens: list[str]) -> list[list[str]]:
    """The pairing clauses of one clause's tokens once its calculations are read: a figure standing next to an operator
    is an operand and pairs with nothing ("4,200 − 3,000" states neither figure with the words around it), and in an
    equation chain ("Break-even quantity = fixed costs ÷ contribution = 6,000 ÷ 2.00 = 3,000 loaves per month") each
    result (a figure that opens a segment after "=" and is no operand) is stated with the words that name it (the
    left-hand side, its figures included: "Value in 2022 = 1 ÷ 8.40 = 0.1190") and the words that follow it ("loaves per
    month"), never with the operands between. A sign before a figure ("= −0.67") is no operator. Operator tokens and "="
    never reach a clause."""
    if "±" in tokens:  # "1600 ± 32 counts": the uncertainty is no quantity of its own; the figure before it stands
        tokens = [t for i, t in enumerate(tokens) if t != "±" and not (i > 0 and tokens[i - 1] == "±" and _is_numeral(t))]
    if not any(t in _PAIR_OPS or t in _PAIR_EQ for t in tokens):
        return [tokens]
    ops: set[int] = set()
    for i, t in enumerate(tokens):
        if t in _PAIR_OPS:
            prev = tokens[i - 1] if i > 0 else None
            if t in ("−", "-", "+") and (prev is None or prev in _PAIR_OPS or prev in _PAIR_EQ):
                continue  # a sign, not an operator
            ops.add(i)

    def operand(i: int) -> bool:
        return _is_numeral(tokens[i]) and ((i - 1) in ops or (i + 1) in ops)

    def kept(idxs: list[int]) -> list[str]:
        return [tokens[i] for i in idxs if i not in ops and tokens[i] not in _PAIR_OPS and not operand(i)]
    segs: list[list[int]] = [[]]
    for i, t in enumerate(tokens):
        if t in _PAIR_EQ:
            segs.append([])
        else:
            segs[-1].append(i)
    if len(segs) == 1:
        return [kept(segs[0])]
    out: list[list[str]] = []
    name = kept(segs[0])
    for seg in segs[1:]:
        body = [i for i in seg if not (tokens[i] in ("−", "-", "+") and i not in ops)]  # a leading sign
        if body and _is_numeral(tokens[body[0]]) and not operand(body[0]):
            j = 1
            while j < len(body) and not _is_numeral(tokens[body[j]]) and body[j] not in ops and tokens[body[j]] not in _PAIR_OPS:
                j += 1
            if j < len(body) and (body[j] in ops or tokens[body[j]] in _PAIR_OPS):
                continue  # "= 15 million litres × (1 − 0.1675)": the figure opens an expression, it is no result
            out.append(name + [tokens[body[0]]] + [tokens[i] for i in body[1:j]])
            name = kept(body[j:])
        # an expression segment ("fixed costs ÷ contribution", "6,000 ÷ 2.00"): the chain's name stands
    if not out and any(_is_numeral(t) for t in name):
        out.append(name)
    return out


def _figure_partners(text: str) -> tuple[set[tuple[str, str]], dict[str, str], dict[str, str]]:
    """``(pairs, kinds, surface)``: every ``(figure, partner)`` of ``text``, the kind of each figure, and the word each
    stemmed partner was first seen as. A partner is an event word within :data:`_WORD_WINDOW` tokens of the figure in
    the same clause (light-stemmed, prefixed ``w:``) that has no nearer figure of the same kind, or another figure within
    :data:`_FIGURE_WINDOW` tokens (prefixed ``f:``). Unit words and function words are not partners."""
    pairs: set[tuple[str, str]] = set()
    kinds: dict[str, str] = {}
    surface: dict[str, str] = {}
    clauses = _clauses(text)
    for ci, clause in enumerate(clauses):
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
            if low in _PARTNER_STOP or len(low) < 3 or light_stem(low) in _REASONING_STEMS:
                continue
            key = "w:" + _partner_stem(low)
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
        # "rises from 2.4 to 4.0": both ends of a from-to change stand with the words of the change, so "rises to 4.0"
        # states the end the source states and re-pairs nothing; and both stand with the series the change is of, the
        # words before "from" back to the previous figure ("the crude death rate in Country X fell from 11 to 7"), so
        # a synthesis that gives the death rate the birth rate's figures exchanges them.
        lows = [t.casefold() for t in clause]
        for a_i in [k + 1 for k, w in enumerate(lows[:-1]) if w == "from" and _is_numeral(clause[k + 1])]:
            b_i = next((k + 1 for k in range(a_i + 1, min(len(clause) - 1, a_i + 6)) if lows[k] == "to" and _is_numeral(clause[k + 1])), None)
            if b_i is None:
                continue
            a, b = clause[a_i], clause[b_i]
            series: set[str] = set()
            back = [(clause[k], lows[k]) for k in range(a_i - 2, max(-1, a_i - 10), -1)]
            if len(back) == a_i - 1 and not any(_is_numeral(t) for t, _w in back) and len([w for _t, w in back if w not in _PARTNER_STOP]) <= 1 and ci > 0:
                # "the crude birth rate, which fell from 31 to 16": the series is named in the clause before
                prev = clauses[ci - 1]
                back += [(prev[k], prev[k].casefold()) for k in range(len(prev) - 1, max(-1, len(prev) - 7), -1)]
            for tok, w in back:
                if _is_numeral(tok):
                    break
                if w in _PARTNER_STOP or len(w) < 3 or light_stem(w) in _REASONING_STEMS:
                    continue
                key = "w:" + _partner_stem(w)
                surface.setdefault(key, w)
                series.add(key)
            words_a = {q for x, q in pairs if x == a and q.startswith("w:")} | series
            words_b = {q for x, q in pairs if x == b and q.startswith("w:")} | series
            pairs |= {(b, q) for q in words_a} | {(a, q) for q in words_b}
    return pairs, kinds, surface


def _partner_stem(word: str) -> str:
    """The key of a partner word: :func:`light_stem`, and a final -e of a longer stem dropped too, so "rise" and "rises",
    "dedicate" and "dedicates" meet."""
    k = light_stem(word)
    return k[:-1] if k.endswith("e") and len(k) > 3 else k


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


_MONTH_STEMS = frozenset(light_stem(m) for m in _MONTHS) | frozenset(_partner_stem(m) for m in _MONTHS)


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
        if kinds.get(a, src_kinds.get(a)) == "quantity":
            # A quantity of a worked answer is restated with other words ("cut volume by 16.75%" for "sales would fall by
            # 16.75%"): a one-sided move is read for dates and data intervals, an exchange of two quantities for both.
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
            if key in reported or a in exchanged or b in exchanged:  # two series exchanged whole are named once per figure
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
    return [_shown_figures(d) for d in _with_word_labels(out, [synthesized_text, *source_texts])]


def _with_word_labels(descriptions: list[str], texts: list[str]) -> list[str]:
    """Show a figure written in words as the words, with the value the readers compared ("'a tenth' (0.1)")."""
    labels: dict[str, str] = {}
    for t in texts:
        for _s, _e, mantissa, _scale, surface in _word_figures(_ungrouped(t)):
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
#: Figures written in words as the approximation readers see them: "roughly fifteen" -> "roughly 15", so an approximate
#: figure in words made exact ("exactly fifteen", "exactly 15") is read like one in digits.
_EXACT_SHOWN_RE = re.compile(r"\b(exactly|precisely|fully|a full|an exact)\s+(\S+(?:\s+(?:thousand|million|billion|trillion))?)", re.IGNORECASE)


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD_RE.findall(text)]


# --- aligned comparison: one statement copied with one word changed ---------------------------------------------------
#: Tokens of the aligned comparison: a decade, a numeral (thousands separators removed), a word (an apostrophe inside it).
_ALIGN_TOKEN_RE = re.compile(r"(?:1\d{2}0|20\d0)s(?!\w)|\d+(?:\.\d+)?|[^\W\d_]+(?:['’][^\W\d_]+)*")
#: Phrases read as one token before aligning, so a three-word reversal ("fell short of" -> "exceeded") is one substitution,
#: and a quantity qualifier ("at least", "no more than") is one word: "only one" -> "at least one" is one exchange.
_CANON_PHRASES = (
    (re.compile(r"\b(?:fell|fall|falls|falling|fallen)\s+(?:far\s+|well\s+|just\s+)?short\s+of\b", re.IGNORECASE), "fellshortof", "fell short of"),
    (re.compile(r"\bno\s+more\s+than\b", re.IGNORECASE), "nomorethan", "no more than"),
    (re.compile(r"\bno\s+fewer\s+than\b", re.IGNORECASE), "nofewerthan", "no fewer than"),
    (re.compile(r"\bno\s+less\s+than\b", re.IGNORECASE), "nolessthan", "no less than"),
    (re.compile(r"\bat\s+least\b", re.IGNORECASE), "atleast", "at least"),
    (re.compile(r"\bat\s+most\b", re.IGNORECASE), "atmost", "at most"),
    # "X rather than Y", "X instead of Y", "X as opposed to Y" deny Y as "X, not Y" does: one polarity
    (re.compile(r"\brather\s+than\b", re.IGNORECASE), "ratherthan", "rather than"),
    (re.compile(r"\binstead\s+of\b", re.IGNORECASE), "insteadof", "instead of"),
    (re.compile(r"\bas\s+opposed\s+to\b", re.IGNORECASE), "asopposedto", "as opposed to"),
)
#: Canonical phrases that deny what follows them, like "not".
_NEGATING_PHRASES = frozenset({"ratherthan", "insteadof", "asopposedto"})
_CANON_SHOWN = {canon: shown for _re, canon, shown in _CANON_PHRASES}
#: A parenthetical aside ("(from memory; check your notes)"): left out of the alignment, so a label the synthesis dropped
#: never hides the one word it changed beside it.
_PARENTHETICAL_RE = re.compile(r"\([^()]{0,300}\)")

#: Nouns that number the steps, trials and parts of a piece of work: one label is written "Trial 1", "the first trial",
#: "the 1st trial" or "trial one" (closed reference data; repair round 5, rerun-combinator-faults-7 variant: a correct
#: synthesis writing "Trial 1" for its source's "the first trial" was charged INT-LEDGER-023 for the figure 1).
STEP_LABEL_NOUNS = frozenset((
    "trial run test attempt experiment sample replicate repeat repetition loop iteration pass step stage phase round cycle wave "
    "batch generation lap game match heat day week year quarter term session visit case scenario option version method group "
    "site plot zone level"
).split())
_ORDINAL_WORDS = {w: i for i, w in enumerate((
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth "
    "sixteenth seventeenth eighteenth nineteenth twentieth").split(), start=1)}
_LABEL_NUMBER_WORDS = {w: i for i, w in enumerate((
    "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen "
    "nineteen twenty").split(), start=1)}
_STEP_NOUN_ALT = "|".join(sorted(STEP_LABEL_NOUNS, key=len, reverse=True))
#: A step label in its three notations: an ordinal before the noun ("the first trial", "the 2nd loop"), or the noun before
#: its number in digits ("Trial 1", "Loop 2:") or in words ("year one").
_STEP_LABEL_RE = re.compile(
    r"\b(?:(?P<ord>" + "|".join(sorted(_ORDINAL_WORDS, key=len, reverse=True)) + r")|(?P<ordn>[1-9]\d?)(?:st|nd|rd|th))[ \t]+(?P<n1>"
    + _STEP_NOUN_ALT + r")\b"
    r"|\b(?P<n2>" + _STEP_NOUN_ALT + r")[ \t]+(?:(?P<num>[1-9]\d?)|(?P<word>" + "|".join(sorted(_LABEL_NUMBER_WORDS, key=len, reverse=True))
    + r"))(?![\w'’])(?![.,]\d)", re.IGNORECASE)


def _step_label_matches(text: str):
    """``(match, noun, number)`` for every step label of ``text`` (:data:`_STEP_LABEL_RE`)."""
    if not text or len(text) > 400_000:
        return
    for m in _STEP_LABEL_RE.finditer(text):
        if m.group("n1"):
            n = _ORDINAL_WORDS[m.group("ord").casefold()] if m.group("ord") else int(m.group("ordn"))
            yield m, m.group("n1").casefold(), n
        else:
            n = int(m.group("num")) if m.group("num") else _LABEL_NUMBER_WORDS[m.group("word").casefold()]
            yield m, m.group("n2").casefold(), n


def step_labels(text: str) -> set[tuple[str, int]]:
    """The step labels ``text`` states, ``(noun, number)``, whatever their notation: "Trial 1", "the first trial", "the
    1st trial" and "trial one" are each ``("trial", 1)``."""
    return {(noun, n) for _m, noun, n in _step_label_matches(text)}


def _canonical_step_labels(text: str) -> str:
    """``text`` with every step label written as its noun and its number in digits ("the first trial" -> "the trial 1",
    "year one" -> "year 1"), so one label in two notations reads as the same words."""
    if not text or not _STEP_LABEL_RE.search(text):
        return text
    return _STEP_LABEL_RE.sub(lambda m: next(f"{noun} {n}" for mm, noun, n in _step_label_matches(m.group(0))), text)


def _masked_step_labels(text: str, labels: set[tuple[str, int]]) -> str:
    """``text`` with the number of every step label written in digits blanked when ``labels`` holds that label: the
    number of "Trial 1" restates the label "the first trial" of a source, never a figure of the statement."""
    if not labels or not text:
        return text
    out = text
    for m, noun, n in _step_label_matches(text):
        if (noun, n) not in labels:
            continue
        key = "num" if m.group("num") else "ordn" if m.group("ordn") else None
        if key is None:
            continue
        a, b = m.span(key)
        out = out[:a] + " " * (b - a) + out[b:]
    return out


def _akey(word: str) -> str:
    """The aligned comparison's key of a word: :func:`light_stem` applied twice, so the singular and plural of a noun
    ending in -ing compare equal ("shilling", "shillings"), after a final -ies or -ied is read as -y ("territories",
    "territory"; "carried", "carry")."""
    w = word.casefold()
    if len(w) > 4 and w.endswith(("ies", "ied")):
        w = w[:-3] + "y"
    return light_stem(light_stem(w))


def _bases(key: str) -> set[str]:
    """The bases a key may be an inflection of: itself, and without a final -e, -es, -s, -ed or -ing (two letters kept)."""
    out = {key}
    for suffix in ("ing", "es", "ed", "e", "s"):
        if key.endswith(suffix) and len(key) - len(suffix) >= 2:
            out.add(key[: -len(suffix)])
    return out


def _variants(a: str, b: str) -> bool:
    """Two keys that are forms of one word the light stemmer leaves apart: they differ only in their last letter, or
    share a base once an inflection is set aside ("goes" -> "goe" and "going" meet at "go")."""
    from os.path import commonprefix
    n = len(commonprefix([a, b]))
    return (n >= 4 and n >= min(len(a), len(b)) - 1) or bool(_bases(a) & _bases(b))


def _stems(words: str) -> frozenset[str]:
    return frozenset(_akey(w) for w in words.split())


#: Opposed word classes (light stems): a statement copied with one of these words exchanged for its opposite says the
#: opposite. Each entry: (class A, class B, what the exchange reverses).
#: The two sides of a degree verdict. A phrase is read as a unit (:func:`_degree_side`): one that carries a limiting word
#: is limited whatever else it says ("significant but limited", "real but partial"), so "to a large extent" or "to a
#: decisive extent" in place of "to a significant but limited extent" reverses the verdict.
_DEGREE_HIGH = _stems("large great considerable significant substantial major high vast huge full strong profound dramatic wide decisive crucial pivotal "
                      "overwhelming dominant central fundamental enormous immense tremendous primary principal complete total")
_DEGREE_LOW = _stems("limited small lesser little minor slight modest partial low weak marginal negligible narrow secondary peripheral minimal moderate "
                     "qualified incomplete")
_OPPOSED: tuple[tuple[frozenset[str], frozenset[str], str], ...] = (
    (_stems(" ".join(sorted(_RISE_WORDS))), _stems(" ".join(sorted(_FALL_WORDS))), "the direction of a change"),
    (_DEGREE_HIGH, _DEGREE_LOW, "a degree verdict"),
    (_stems("more greater larger higher bigger most greatest largest highest biggest faster fastest stronger strongest better best"),
     _stems("less fewer smaller lower least fewest smallest lowest slower slowest weaker weakest worse worst"), "a comparative or superlative"),
    (_stems("before earlier prior preceded precedes preceding"), _stems("after later following followed follows subsequent"), "an order in time"),
    (_stems("exceeded exceeds exceed surpassed surpasses surpass outstripped outstrips overtook beat topped above"), frozenset({"fellshortof"}) | _stems("below missed"),
     "a comparison with a target"),
    (_stems("long longer longest lengthy"), _stems("short shorter shortest brief"), "a length"),
    (_stems("include included includes including inclusion welcome welcomed welcomes welcoming admit admits admitted admitting admission embrace embraced "
            "embracing invite invited inviting"),
     _stems("exclude excluded excludes excluding exclusion bar barred barring ban banned banning expel expelled expelling forbid forbade forbidden "
            "prohibit prohibited prohibiting restrict restricted restricting"), "inclusion or exclusion"),
    (_stems("accept accepted accepting acceptance agree agreed agreeing agreement consent consented comply complied complying compliance"),
     _stems("refuse refused refusing refusal reject rejected rejecting rejection resist resisted resisting resistance"), "acceptance or refusal"),
    (_stems("succeed succeeded succeeds success successful win won wins victory"), _stems("fail failed fails failure unsuccessful lose lost loses defeat"),
     "success or failure"),
    (_stems("only just merely solely exactly precisely") | {"atmost", "nomorethan"}, _stems("upwards") | {"atleast", "nofewerthan", "nolessthan"},
     "a quantity qualifier"),
    (_stems("all every each universal"), _stems("some few several"), "the scope of a quantity"),
    (_stems("positive optimistic favourable favorable"), _stems("negative pessimistic unfavourable unfavorable"), "an evaluation"),
    (_stems("legal lawful legally lawfully constitutional constitutionally peaceful peacefully nonviolent parliamentary electoral"),
     _stems("violent violently illegal unlawful unconstitutional forceful forcibly coercive coercion terror intimidation"), "lawful or violent means"),
    (_stems("true verdadero verdadera vrai vraie correct right"), _stems("false falso falsa faux incorrect wrong"), "a true/false verdict"),
)
#: Verbs of comparison whose passive reverses the comparison ("working-age people outnumber dependants" -> "are outnumbered
#: by dependants"): the active form, and the passive with its agent.
_COMPARISON_VERB_RE = r"(outnumber|exceed|outweigh|outperform|surpass|overtake|overtook|dominate|outpace|outstrip)"
_PASSIVE_COMPARISON_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+(?:\w+\s+)?" + _COMPARISON_VERB_RE + r"(?:e?d|en)?\s+by\b", re.IGNORECASE)
_ACTIVE_COMPARISON_RE = re.compile(r"(?<!\bbe )(?<!\bis )(?<!\bare )(?<!\bwas )(?<!\bwere )(?<!\bbeen )\b" + _COMPARISON_VERB_RE + r"(?:s|es|ed|d|ing)?\b(?!\s+by\b)", re.IGNORECASE)


def _comparison_voices(text: str) -> set[tuple[str, str]]:
    """``(verb, 'active' | 'passive')`` for every verb of comparison in ``text``."""
    def key(v: str) -> str:
        v = v.casefold()
        return "overtake" if v == "overtook" else v
    out = {(key(m.group(1)), "passive") for m in _PASSIVE_COMPARISON_RE.finditer(text)}
    out |= {(key(m.group(1)), "active") for m in _ACTIVE_COMPARISON_RE.finditer(text)}
    return out


def reversed_voices(synthesized_text: str, source_texts: list[str]) -> list[str]:
    """A comparison the synthesis turns round by its voice: "working-age people are outnumbered by dependants" where every
    cited source states the active "working-age people outnumber dependants" (or the reverse)."""
    syn = _comparison_voices(synthesized_text)
    if not syn:
        return []
    src = set().union(*(_comparison_voices(t) for t in source_texts)) if source_texts else set()
    out = []
    for verb, voice in sorted(syn):
        other = "active" if voice == "passive" else "passive"
        if (verb, other) in src and (verb, voice) not in src:
            out.append(f"it reverses the direction of a comparison: it states '{verb}' in the {voice} where its cited sources state it in the {other} (who {verb}s whom is turned round)")
    return out
_POLARITY_WORDS = frozenset().union(*(a | b for a, b, _what in _OPPOSED))
#: Prefixes that negate the word they stand before ("limited" -> "unlimited", "complete" -> "incomplete").
_NEGATING_PREFIXES = ("un", "non", "in", "im", "il", "ir", "dis")
#: Words a negating prefix does not negate (an intensifier, a different word).
_PREFIX_EXCEPTIONS = frozenset({"valuable", "flammable", "ravel", "loose", "press", "port", "form", "tend", "vent", "vest", "pose", "cover", "play", "tract", "close",
                                "volve", "clude", "crease", "dicat", "stance", "ternal", "sist", "sight", "side", "spire"})
#: Small counts written in words: "a shilling" against "two shillings" is a changed figure.
_CARDINAL_WORDS = {"a": 1, "an": 1, **_ONES, **_TEENS, **_TENS, "dozen": 12, "single": 1, "both": 2, "twice": 2, "thrice": 3}
_MONTH_KEYS = frozenset(_MONTHS)
#: Function and filler words that are never a "changed content word".
_ALIGN_STOP = _PARTNER_STOP | frozenset(("his her him he she they them we our you your i me my one ones such would could should shall will may might must can did does do "
                                         "what how why where also yet thus therefore however whose than then there here made make makes very much many most "
                                         "whereas whilst although though because since unless until whether wherever whenever where's within through "
                                         "throughout across among amongst between beyond toward towards upon onto into itself himself herself themselves "
                                         "rather instead indeed hence thereby whereby moreover furthermore additionally nevertheless nonetheless "
                                         "consequently overall finally firstly secondly thirdly meanwhile similarly likewise conversely "
                                         "accordingly besides").split())


def _align_plain(text: str) -> str:
    """``text`` as the aligned comparison reads it: parentheticals left out, thousands separators removed, decades as
    "1840s" and the canonical phrases (:data:`_CANON_PHRASES`) as one word."""
    plain = _DECADE_RE.sub(lambda m: m.group(1) + "s", _ungrouped(_PARENTHETICAL_RE.sub(" ", fold_exponent_marks(text))))
    for rx, canon, _shown in _CANON_PHRASES:
        plain = rx.sub(canon, plain)
    return plain


def _align_token(m: "re.Match[str]") -> tuple[str, str]:
    w = m.group(0)
    low = w.casefold()
    return (low if low[:1].isdecimal() or low in _CANON_SHOWN else _akey(low), _CANON_SHOWN.get(low, w))


def _align_tokens(text: str) -> list[tuple[str, str]]:
    """``(key, surface)`` per token of ``text``: words light-stemmed and case-folded, numerals as written (thousands
    separators removed), decades as "1840s", and the canonical phrases (:data:`_CANON_PHRASES`) as one token."""
    return [_align_token(m) for m in _ALIGN_TOKEN_RE.finditer(_align_plain(text))]


def _cardinal(key: str, surface: str) -> Optional[float]:
    low = surface.casefold()
    if low in _CARDINAL_WORDS:
        return float(_CARDINAL_WORDS[low])
    if key[:1].isdecimal() and not key.endswith("s"):
        try:
            return float(key)
        except ValueError:
            return None
    return None


def _is_soft_negator(surface: str) -> bool:
    return surface.casefold().replace(" ", "") in _NEGATING_PHRASES


def _is_negator(surface: str) -> bool:
    low = surface.casefold().replace(" ", "")
    return low in _NEGATORS or low in _NEGATING_PHRASES or low.endswith(("n't", "n’t"))


def _context(tokens: list[tuple[str, str]], i1: int, i2: int, width: int = 2) -> str:
    return " ".join(s for _k, s in tokens[max(0, i1 - width):i2 + width])


def _degree_side(keys: list[str]) -> Optional[str]:
    """The side of a degree verdict a phrase takes, read as a unit: "low" when it carries a limiting word, whatever else it
    says ("significant but limited", "real but partial"), "high" when it carries only raising words ("large",
    "decisive"), None when it states no degree."""
    if any(k in _DEGREE_LOW for k in keys):
        return "low"
    if any(k in _DEGREE_HIGH for k in keys):
        return "high"
    return None


def _negating_prefix(a: str, b: str) -> bool:
    """``a`` is ``b`` with a negating prefix (or the reverse): "unlimited" against "limited", "incomplete" against "complete"."""
    for x, y in ((a, b), (b, a)):
        for p in _NEGATING_PREFIXES:
            if x == p + y and len(y) >= 4 and y not in _PREFIX_EXCEPTIONS:
                return True
    return False


def _class_side(key: str) -> Optional[tuple[int, int]]:
    """``(class index, side)`` of a polarity word (:data:`_OPPOSED`), or None."""
    for i, (a, b, _what) in enumerate(_OPPOSED):
        if key in a:
            return i, 0
        if key in b:
            return i, 1
    return None


def _reversal(syn_keys: list[str], src_keys: list[str]) -> Optional[str]:
    """What a replaced span of up to three words reverses against the span it replaces: a degree verdict read as a phrase
    (:func:`_degree_side`), a word of one side of an opposed class where the source has only the other side ("preceded
    Ghana" for "followed", "welcoming all" for "excluding some"), or a word negated by its prefix. None otherwise."""
    ds, dr = _degree_side(syn_keys), _degree_side(src_keys)
    if ds is not None and dr is not None and ds != dr:
        return "a degree verdict"
    sy, sr = set(syn_keys), set(src_keys)
    for a, b, what in _OPPOSED:
        if a is _DEGREE_HIGH:
            continue
        ya, yb, ra, rb = bool(sy & a), bool(sy & b), bool(sr & a), bool(sr & b)
        if (ya and not yb and rb and not ra) or (yb and not ya and ra and not rb):
            return what
    if any(_negating_prefix(x, y) for x in sy for y in sr):
        return "a word by a negating prefix"
    return None


def _joined_keys(texts: Sequence[str]) -> tuple[str, ...]:
    """The alignment keys of every text in ``texts``, one after another with a separator no token equals between them, so
    a run never crosses from one text into the next."""
    out: list[str] = []
    for t in texts:
        out.extend(k for k, _s in _align_tokens(t))
        out.append("\x00")
    return tuple(out)


def aligned_changes(synthesized_text: str, source_text: str, *, context_keys: Optional[tuple[str, ...]] = None) -> tuple[list[str], list[str]]:
    """``(figure_changes, meaning_changes)``: where ``synthesized_text`` copies a statement of ``source_text`` word for word
    around one changed place (difflib alignment of the light-stemmed tokens; the change must stand between copied words
    on both sides, at least three copied words in all; a replaced content word two on each side, four in all):

    * a small count written in words changed ("about a shilling a day" -> "about two shillings a day", "two contingents"
      -> "three contingents", "ten years" -> "twenty years"), a month changed ("11 December" -> "11 October"), or a figure
      in digits replaced by another figure the source states elsewhere ("wrote the sonnet in 1883" -> "in 1886", the year
      the source gives the dedication): a changed figure or date (INT-LEDGER-023);
    * a word or a phrase of up to three words exchanged for its opposite (:data:`_OPPOSED`: rising/falling; a degree
      verdict read as a phrase, so "to a large extent" or "to a decisive extent" reverses "to a significant but limited
      extent"; more/less, most/least; before/after, "preceded Ghana" for "followed"; exceeded/fell short of; long/short;
      including/excluding, "welcoming all" for "excluding some"; accepting/refusing; a quantity qualifier, "at least one"
      for "only one"; the scope of a quantity, all/some), a word negated by its prefix ("unlimited" for "limited"), a
      negation added or dropped ("were the most decisive" -> "were not the most decisive"), or a content word replaced in
      an otherwise copied statement ("the large majority from disease" -> "from battle", "in unprecedented numbers" -> "in
      declining numbers"; two synonyms of one class, "large" and "great", are not a replacement): a changed meaning
      (INT-LEDGER-026, lexical).

    A rewording that changes more than three words at a place is a paraphrase and is not read here.

    Each sentence of the source is also aligned on its own against each sentence of the synthesis that shares most of its
    content words, with the source sentence's start and end as anchors: a change to the first or last word of a sentence
    the synthesis copies into a merged claim ("Legal means did most of the consolidating" -> "Violent means did most of the
    consolidating") is read like one between copied words (a replaced content word then needs three copied words on its
    other side)."""
    syn, src = _align_tokens(synthesized_text), _align_tokens(source_text)
    if not syn or not src:
        return [], []
    src_numerals = {k for k, _s in src if k[:1].isdecimal()}
    # where a copied statement is looked for: this source, or every cited source (``context_keys``, :func:`aligned_differences`)
    src_all = context_keys if context_keys is not None else tuple(k for k, _s in src)
    figures, meaning = _aligned_ops(syn, src, src_numerals, src_all=src_all, syn_starts=_sentence_starts(synthesized_text, syn))
    src_sentences = [t for t in (_align_tokens(x) for x in _ALIGN_SENTENCE_RE.split(source_text)) if len(t) >= 4]
    syn_sentences = [t for t in (_align_tokens(x) for x in _ALIGN_SENTENCE_RE.split(synthesized_text)) if len(t) >= 4]
    if src_sentences and syn_sentences:
        syn_keys = tuple(k for k, _s in syn)
        src_keys = tuple(k for k, _s in src)
        # A synthesized sentence the source states word for word is a copy of that source sentence: it is never the place
        # another source sentence was changed ("from July to September by 20.9" is not "from January to July by 1.55").
        candidates = [yt for yt in syn_sentences if not _holds_run(src_keys, tuple(k for k, _w in yt))]
        for st in src_sentences:
            if _holds_run(syn_keys, tuple(k for k, _w in st)):
                continue  # copied word for word: nothing of this sentence changed
            content = {k for k, w in st if w.isalpha() and k not in _ALIGN_STOP and w.casefold() not in _ALIGN_STOP}
            if not content:
                continue
            # only the best-matching synthesized sentence(s) are its rewrite, never every parallel sentence sharing half its words
            scored = [(len(content & {k for k, _w in yt}), yt) for yt in candidates]
            scored = [(n, yt) for n, yt in scored if n * 2 >= len(content)]
            best = max((n for n, _yt in scored), default=0)
            for n, yt in scored:
                if n != best:
                    continue
                f2, m2 = _aligned_ops(yt, st, src_numerals, anchored=True, src_all=src_all)
                figures += f2
                meaning += m2
    return list(dict.fromkeys(figures)), list(dict.fromkeys(meaning))


def _holds_run(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    """Whether the token sequence ``needle`` occurs contiguously in ``haystack`` (a word-for-word copy). Linear in practice:
    each candidate start is the needle's first token."""
    n = len(needle)
    if n == 0 or n > len(haystack):
        return False
    first = needle[0]
    for i in range(len(haystack) - n + 1):
        if haystack[i] == first and haystack[i:i + n] == needle:
            return True
    return False


#: Sentence ends for the anchored alignment: a full stop, question or exclamation mark, a semicolon, a line break.
_ALIGN_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


def _start_of(starts: tuple[int, ...], i: int) -> int:
    """The first token of the sentence that holds token ``i`` (``starts`` from :func:`_sentence_starts`)."""
    return max((s for s in starts if s <= i), default=0)


def _copied_with_context(syn: list[tuple[str, str]], i1: int, i2: int, lb: int, la: int, src_all: tuple[str, ...], start: int = 0) -> bool:
    """Whether the source states the synthesis's words at ``i1:i2`` with the copied words around them, word for word: the
    whole copied run before them in their own sentence (``start`` is the sentence's first token; never fewer than the four
    copied words before, when the run is that long) and up to two after. The synthesis then copies that statement of the
    source, wherever the alignment paired it. A source that states two parallel steps ("On the first loop, i is 0, so
    total = 3. On the second loop, i is 1, so total = 8.") pairs a synthesized step with either one; "so total 8" is still
    the source's own statement, never a 3 changed to 8 (repair round 4, rerun-combinator-faults-7 variant). The words that
    tell parallel statements apart (a year, a place, a trial) may stand anywhere before the figure in its sentence: "In
    2019 the price of bread rose by 1.4 per cent" is no copy of a source that states "in 2020 the price of bread rose by
    1.4 per cent" and gives 2019 3.2 per cent (repair round 5, rerun-combinator-faults-7: a window of four words excused
    that swap). A figure that no source statement carries with those words ("wrote the sonnet in 1886" for a source that
    dates the dedication 1886) is still a swap."""
    if not src_all:
        return False
    left = min(i1 - min(lb, 4), max(i1 - lb, start))
    run = tuple(k for k, _s in syn[max(0, left):i2 + min(la, 2)])
    return _holds_run(src_all, run)


def _sentence_starts(text: str, tokens: list[tuple[str, str]]) -> tuple[int, ...]:
    """The index in ``tokens`` (:func:`_align_tokens` of ``text``) of the first token of each sentence of ``text``
    (:data:`_ALIGN_SENTENCE_RE`), or ``(0,)`` when the sentences' own tokens do not add up to ``tokens`` (a parenthesis
    or a canonical phrase across a sentence end)."""
    starts: list[int] = []
    n = 0
    for piece in _ALIGN_SENTENCE_RE.split(text):
        starts.append(n)
        n += len(_align_tokens(piece))
    return tuple(starts) if n == len(tokens) else (0,)


def _aligned_ops(syn: list[tuple[str, str]], src: list[tuple[str, str]], src_numerals: set[str], *, anchored: bool = False,
                 src_all: tuple[str, ...] = (), syn_starts: tuple[int, ...] = (0,)) -> tuple[list[str], list[str]]:
    """The changes :func:`aligned_changes` reads between two token lists. With ``anchored`` (two sentences), the start and
    the end of the source sentence count as one copied word each. ``src_all`` is the whole source's token keys: a figure or
    month the synthesis states with the words the source states it with is a copy (:func:`_copied_with_context`);
    ``syn_starts`` are the first tokens of the synthesis's sentences."""
    from difflib import SequenceMatcher
    ops = SequenceMatcher(None, [k for k, _s in syn], [k for k, _s in src], autojunk=False).get_opcodes()
    figures: list[str] = []
    meaning: list[str] = []
    for n, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "equal":
            continue
        lb = (ops[n - 1][2] - ops[n - 1][1]) if n > 0 and ops[n - 1][0] == "equal" else 0
        la = (ops[n + 1][2] - ops[n + 1][1]) if n + 1 < len(ops) and ops[n + 1][0] == "equal" else 0
        start_anchor = anchored and j1 == 0 and lb == 0
        end_anchor = anchored and j2 == len(src) and la == 0
        if start_anchor and end_anchor:
            continue  # the whole sentence differs: nothing is copied
        if start_anchor:
            lb = 1
        if end_anchor:
            la = 1
        if lb < 1 or la < 1 or lb + la < 3:
            continue
        here, there = _context(syn, i1, i2), _context(src, j1, j2)
        syn_words, src_words = syn[i1:i2], src[j1:j2]
        # "rather than", "instead of" deny what follows them like "not" does: they cancel a "not" on the other side ("X,
        # not Y" -> "X rather than Y" keeps the polarity), but adding one ("lowest at C rather than at B") adds a contrast,
        # not a negation of the source's statement.
        hard_syn, hard_src = any(_is_negator(s) and not _is_soft_negator(s) for _k, s in syn_words), any(_is_negator(s) and not _is_soft_negator(s) for _k, s in src_words)
        soft_syn, soft_src = any(_is_soft_negator(s) for _k, s in syn_words), any(_is_soft_negator(s) for _k, s in src_words)
        syn_neg = hard_syn and not (hard_src or soft_src)
        src_neg = hard_src and not (hard_syn or soft_syn)
        if syn_neg != src_neg and len(syn_words) <= 3 and len(src_words) <= 3:
            meaning.append(f"it adds a negation its cited sources do not state ('{here}' where they state '{there}')" if syn_neg
                           else f"it drops the negation its cited sources state ('{here}' where they state '{there}')")
            continue
        if tag != "replace" or i2 - i1 > 3 or j2 - j1 > 3:
            continue
        if i2 - i1 == 1 and j2 - j1 == 1:
            (ka, sa), (kb, sb) = syn[i1], src[j1]
            va, vb = _cardinal(ka, sa), _cardinal(kb, sb)
            if va is not None and vb is not None and va != vb:
                if not (ka[:1].isdecimal() and kb[:1].isdecimal()):
                    nxt_syn = syn[i2][1] if i2 < len(syn) else ""
                    nxt_src = src[j2][1] if j2 < len(src) else ""
                    figures.append(f"'{(sa + ' ' + nxt_syn).strip()}' ({_fmt_value(va)}) where its cited sources state '{(sb + ' ' + nxt_src).strip()}' ({_fmt_value(vb)}): a count written in words changed")
                elif ka in src_numerals and not _copied_with_context(syn, i1, i2, lb, la, src_all, _start_of(syn_starts, i1)):
                    # a figure the source states elsewhere, put in place of the one it states here
                    figures.append(f"'{here}' where its cited sources state '{there}': '{sa}' is a figure they state elsewhere, put in place of '{sb}'")
                continue
            if sa.casefold() in _MONTH_KEYS and sb.casefold() in _MONTH_KEYS and sa.casefold() != sb.casefold():
                if not _copied_with_context(syn, i1, i2, lb, la, src_all, _start_of(syn_starts, i1)):
                    figures.append(f"'{here}' where its cited sources state '{there}': a month changed")
                continue
        what = _reversal([k for k, _s in syn_words], [k for k, _s in src_words])
        if what == "a comparative or superlative" and _change_words(src[max(0, j1 - 5):j1]) != _change_words(syn[max(0, i1 - 5):i1]):
            what = None  # "the fall in dissolved oxygen is greatest at C" and "dissolved oxygen is lowest at C" agree: one compares a change, the other a level
        if what is not None:
            meaning.append(f"it reverses {what} ('{here}' where its cited sources state '{there}')")
            continue
        if i2 - i1 != 1 or j2 - j1 != 1:
            continue
        (ka, sa), (kb, sb) = syn[i1], src[j1]
        content = all(w.isalpha() and len(w) >= 4 and k not in _ALIGN_STOP and w.casefold() not in _ALIGN_STOP for k, w in ((ka, sa), (kb, sb)))
        sides = (_class_side(ka), _class_side(kb))
        enough = (lb >= 2 and la >= 2) if not (start_anchor or end_anchor) else (la >= 3 if start_anchor else lb >= 3)
        if content and ka != kb and not _variants(ka, kb) and enough and not (sides[0] is not None and sides[1] is not None):
            meaning.append(f"it replaces '{sb}' with '{sa}' in an otherwise copied statement ('{here}' where its cited sources state '{there}')")
    return figures, meaning


_CHANGE_KEYS = frozenset(_akey(w) for w in (_RISE_WORDS | _FALL_WORDS))


def _change_words(tokens: list[tuple[str, str]]) -> bool:
    """True when ``tokens`` name a change ("the fall in", "the rise of"), not a level."""
    return any(k in _CHANGE_KEYS for k, _s in tokens)


def _fmt_value(v: float) -> str:
    return str(int(v)) if v == int(v) else str(v)


def aligned_differences(synthesized_text: str, source_texts: list[str]) -> tuple[list[str], list[str]]:
    """:func:`aligned_changes` against every cited source text, :func:`day_month_differences` and :func:`context_swaps`
    against all of them, deduplicated (a swap the alignment already names is not named twice). A pure reading of the texts:
    the ledger reads it twice for one synthesized claim (its count and date changes, and :func:`meaning_differences`), so
    one answer is kept per pair of texts (close round 3, DV2-06); callers receive copies."""
    figures, meaning = _aligned_differences(synthesized_text, tuple(source_texts))
    return list(figures), list(meaning)


@lru_cache(maxsize=64)
def _aligned_differences(synthesized_text: str, source_texts: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    figures: list[str] = []
    meaning: list[str] = []
    joined = _joined_keys(source_texts) if len(source_texts) > 1 else None
    for t in source_texts:
        f, m = aligned_changes(synthesized_text, t, context_keys=joined)
        figures += f
        meaning += m
    figures += day_month_differences(synthesized_text, list(source_texts))
    for swap, tail in context_swaps(synthesized_text, source_texts):
        if not any(tail in d for d in figures):
            figures.append(swap)
    return tuple(dict.fromkeys(figures)), tuple(dict.fromkeys(meaning))


#: An operator, a relation sign or a function right after a figure: the figure starts a calculation ("8 ln 2 ÷ ln(...) ≈ 8.5"),
#: it is not the figure the statement states.
_EXPRESSION_AFTER_RE = re.compile(r"[ \t]*(?:[×÷/*+\-−^·√=≈<>≤≥(]|(?:ln|log|lg|sin|cos|tan|exp|sqrt|mod)\b)")
#: A swap read from a figure's copied context: at least four copied tokens before the figure, two of them content words,
#: read back at most twenty-four tokens within the figure's own sentence.
_SWAP_MIN_RUN = 4
_SWAP_REACH = 24
_SWAP_SCALES = {"thousand": 10 ** 3, "million": 10 ** 6, "billion": 10 ** 9, "trillion": 10 ** 12}


def _scaled_number(keys: Sequence[str], shown: Sequence[str], i: int) -> Optional[float]:
    """The value of the numeral token ``i`` with a scale word right after it ("1.4 million")."""
    v = _cardinal(keys[i], shown[i])
    if v is None:
        return None
    nxt = shown[i + 1].casefold() if i + 1 < len(shown) else ""
    return v * _SWAP_SCALES.get(nxt, 1)


def _yearlike(key: str) -> bool:
    return re.fullmatch(r"1\d{3}|20\d{2}", key) is not None


class _RunPlaces:
    """The places in the sources of one run of tokens, and, read on demand, the places of each run one token longer, by that
    token (close round 3, DV2-06). ``places`` are anchors in ascending order: for a run read backwards from a figure, the end
    (exclusive) of each place (the run is ``keys[e - length:e]``); for a run read forwards, the position of the figure the run
    follows (the run is ``keys[p + 1:p + 1 + length]``). A place enters at most :data:`_SWAP_REACH` runs of one direction, so
    every run of a pair of texts together costs a bounded multiple of the sources' length, whatever is repeated in them."""

    __slots__ = ("places", "length", "_next", "_followers", "_values")

    def __init__(self, places: list[int], length: int) -> None:
        self.places = places
        self.length = length
        self._next: Optional[dict[str, "_RunPlaces"]] = None
        self._followers: Optional[tuple[bool, bool, bool, frozenset, str]] = None
        self._values: Optional[frozenset] = None

    def extended(self, token: str, keys: Sequence[str], backward: bool) -> Optional["_RunPlaces"]:
        """The places of this run with ``token`` one place before it (``backward``) or after it, or None."""
        if self._next is None:
            grouped: dict[str, list[int]] = {}
            n, length = len(keys), self.length
            for p in self.places:
                q = p - length - 1 if backward else p + length + 1
                if 0 <= q < n:
                    grouped.setdefault(keys[q], []).append(p)
            self._next = {k: _RunPlaces(v, length + 1) for k, v in grouped.items()}
        return self._next.get(token)

    def followers(self, keys: Sequence[str], shown: Sequence[str], in_expression: Sequence[bool]) -> tuple[bool, bool, bool, frozenset, str]:
        """What follows every place of a backward run, read once: ``(each is a figure that starts no calculation and has a
        value, each is year-like, none is year-like, their values, the first one as written)``."""
        if self._followers is None:
            ok, years, no_years, values = True, True, True, set()
            for e in self.places:
                if e >= len(keys) or not keys[e][:1].isdecimal() or in_expression[e]:
                    ok = False
                    break
                other = _scaled_number(keys, shown, e)
                if other is None:
                    ok = False
                    break
                y = _yearlike(keys[e])
                years, no_years = years and y, no_years and not y
                values.add(other)
            first = shown[self.places[0]] if ok and self.places else ""
            self._followers = (ok and bool(self.places), years, no_years, frozenset(values), first)
        return self._followers

    def figure_values(self, keys: Sequence[str], shown: Sequence[str]) -> frozenset:
        """The values of the figures a forward run follows, read once."""
        if self._values is None:
            self._values = frozenset(v for v in (_scaled_number(keys, shown, p) for p in self.places) if v is not None)
        return self._values


def _states_own_figure(plain: str, matches: Sequence["re.Match[str]"], tkeys: Sequence[str], tshown: Sequence[str], i: int, value: float,
                       keys: Sequence[str], shown: Sequence[str], after: dict[tuple[str, ...], _RunPlaces]) -> bool:
    """Whether the synthesis's words after its figure ``i``, to the end of the figure's clause (a comma, a semicolon, a colon
    or the sentence's end; at most :data:`_SWAP_REACH` tokens), are what a source states right after the same figure: at
    least :data:`_SWAP_MIN_RUN` tokens, two of them content words and one of them a figure or a date of that statement
    ("37.3 per cent and 230 seats in July 1932"). Such a figure keeps its own words; the words before it may come from the
    statement of a figure the summary skipped (close round 1, arena r1 hi-t1 synthesis). ``after`` holds the places of every
    source figure followed by :data:`_SWAP_MIN_RUN` tokens, by those five keys (close round 3: each source place is read
    once for all the synthesis's figures, :class:`_RunPlaces`)."""
    j = i + 1
    while j < len(tkeys) and j - i <= _SWAP_REACH:
        if any(ch in ",;:" for ch in plain[matches[j - 1].end():matches[j].start()]):
            break
        j += 1
    run = list(tkeys[i + 1:j])
    words = list(tshown[i + 1:j])
    content = sum(1 for kk, ww in zip(run, words) if ww.isalpha() and kk not in _ALIGN_STOP and ww.casefold() not in _ALIGN_STOP)
    if len(run) < _SWAP_MIN_RUN or content < 2 or not any(kk[:1].isdecimal() for kk in run):
        return False
    node = after.get((tkeys[i], *run[:_SWAP_MIN_RUN]))
    while node is not None and node.length < len(run):
        node = node.extended(run[node.length], keys, backward=False)
    return node is not None and value in node.figure_values(keys, shown)


def _longest_run(window: tuple[str, ...], keys: Sequence[str], at_run: dict[tuple[str, ...], _RunPlaces]) -> Optional[_RunPlaces]:
    """The places of the longest suffix of ``window`` (the tokens before a figure in its own sentence, at most
    :data:`_SWAP_REACH`) that the sources hold, as the token-by-token extension of :func:`context_swaps` finds it: from the
    places of its last :data:`_SWAP_MIN_RUN` tokens (``at_run``), extended one token at a time while some place still holds
    it. None when the sources hold no such run of :data:`_SWAP_MIN_RUN` tokens."""
    reach = len(window)
    if reach < _SWAP_MIN_RUN:
        return None
    node = at_run.get(window[reach - _SWAP_MIN_RUN:])
    while node is not None and node.length < reach:
        longer = node.extended(window[reach - node.length - 1], keys, backward=True)
        if longer is None:
            break
        node = longer
    return node


def context_swaps(synthesized_text: str, source_texts: Sequence[str]) -> list[tuple[str, str]]:
    """Figures the synthesis states right after words its sources state, word for word, with another figure: the longest
    run of tokens before the figure in its own sentence that the sources hold (at least :data:`_SWAP_MIN_RUN` tokens, two
    of them content words; step labels read in one notation, :func:`_canonical_step_labels`) is followed in every place
    the sources state it by a figure of the same kind with another value, while the sources state the synthesized figure
    elsewhere. "In 2019 the price of bread rose by 1.4 per cent" for a source that states "In 2019 the price of bread rose
    by 3.2 per cent, while in 2020 the price of bread rose by 1.4 per cent" splices one statement's figure into the other's
    words: the alignment pairs it with the 2020 statement and reads no change (repair round 5, rerun-combinator-faults-7).
    A run the sources state with the synthesized figure somewhere, a run followed there by anything but a figure, and a
    figure in no source (the plain introduced figure) are not read. Nor is a figure whose words after it, to the end of its
    clause, are a source's own statement of that same figure (:func:`_states_own_figure`: "from 2.6 per cent ... in May 1928
    to 37.3 per cent and 230 seats in July 1932" for a source that lists 18.3 per cent in September 1930 between them): the
    summary skips an intermediate figure and keeps each figure with its own words (close round 1). Returns ``(description,
    its swap clause)`` pairs.

    Linear in the two texts (close round 3, DV2-06; the old answer on every input): the places of every run of
    :data:`_SWAP_MIN_RUN` source tokens and of every source figure with the tokens after it are indexed once and extended
    one token at a time on demand (:class:`_RunPlaces`, which also reads once what follows every place of a run), a figure
    whose preceding tokens hold fewer than two content words is not read (no run inside them could hold two), and one
    reading is kept per sequence of preceding tokens."""
    texts = [t for t in source_texts if t]
    if not synthesized_text or not texts or len(synthesized_text) > 400_000:
        return []
    keys: list[str] = []
    shown: list[str] = []
    in_expression: list[bool] = []  # the token is a figure an operator or a function follows: the start of a calculation
    for t in texts:
        plain = _align_plain(_canonical_step_labels(t))
        for m in _ALIGN_TOKEN_RE.finditer(plain):
            k, w = _align_token(m)
            keys.append(k)
            shown.append(w)
            in_expression.append(bool(_EXPRESSION_AFTER_RE.match(plain, m.end())))
        keys.append("\x00")
        shown.append("")
        in_expression.append(False)
    numerals = {k for k in keys if k[:1].isdecimal()}
    if not numerals:
        return []
    # the end (exclusive) of every place of every run of _SWAP_MIN_RUN source tokens, and every place of a source figure by
    # its key and the _SWAP_MIN_RUN keys after it: each read once (close round 3, DV2-06)
    run_places: dict[tuple[str, ...], list[int]] = {}
    figure_places: dict[tuple[str, ...], list[int]] = {}
    for p in range(len(keys)):
        if p >= _SWAP_MIN_RUN - 1:
            run_places.setdefault(tuple(keys[p - _SWAP_MIN_RUN + 1:p + 1]), []).append(p + 1)
        if keys[p][:1].isdecimal() and p + _SWAP_MIN_RUN < len(keys):
            figure_places.setdefault(tuple(keys[p:p + _SWAP_MIN_RUN + 1]), []).append(p)
    at_run = {k: _RunPlaces(v, _SWAP_MIN_RUN) for k, v in run_places.items()}
    after = {k: _RunPlaces(v, _SWAP_MIN_RUN) for k, v in figure_places.items()}
    runs: dict[tuple[str, ...], Optional[_RunPlaces]] = {}  # one reading per sequence of preceding tokens
    out: list[tuple[str, str]] = []
    for sentence in _ALIGN_SENTENCE_RE.split(_canonical_step_labels(synthesized_text)):
        plain = _align_plain(sentence)
        matches = list(_ALIGN_TOKEN_RE.finditer(plain))
        toks = [_align_token(m) for m in matches]
        tkeys = [k for k, _w in toks]
        tshown = [w for _k, w in toks]
        for i, (k, w) in enumerate(toks):
            if not k[:1].isdecimal() or k not in numerals or i < _SWAP_MIN_RUN or _EXPRESSION_AFTER_RE.match(plain, matches[i].end()):
                continue
            value = _scaled_number(tkeys, tshown, i)
            if value is None:
                continue
            reach = min(i, _SWAP_REACH)
            # the run is a suffix of the tokens before the figure: with fewer than two content words among them it has fewer
            if sum(1 for kk, ww in toks[i - reach:i] if ww.isalpha() and kk not in _ALIGN_STOP and ww.casefold() not in _ALIGN_STOP) < 2:
                continue
            # the ends (exclusive) of every place the sources state the longest run of the tokens before the figure
            window = tuple(tkeys[i - reach:i])
            if window not in runs:
                runs[window] = _longest_run(window, keys, at_run)
            node = runs[window]
            if node is None:
                continue
            length = node.length
            run = toks[i - length:i]
            content = sum(1 for kk, ww in run if ww.isalpha() and kk not in _ALIGN_STOP and ww.casefold() not in _ALIGN_STOP)
            if length < _SWAP_MIN_RUN or content < 2:
                continue
            # every place the sources state the run is followed by a figure of the same kind (year-like or not) with another value
            ok, years, no_years, values, first = node.followers(keys, shown, in_expression)
            if not ok or not (years if _yearlike(k) else no_years) or value in values:
                continue
            if _states_own_figure(plain, matches, tkeys, tshown, i, value, keys, shown, after):
                continue  # the words after it are a source's own statement of this figure: an intermediate figure skipped, no swap
            context = " ".join(ww for _kk, ww in run)
            tail = f"'{w}' is a figure they state elsewhere, put in place of '{first}'"
            out.append((f"'{context} {w}' where its cited sources state '{context} {first}': {tail}", tail))
    return out


_MONTH_ALT = "|".join(m.capitalize() for m in _MONTHS)
#: A day-month date, "6 March", "6th of March" or "March 6" (a capitalised month name; "March 1957" is a month-year).
_DAY_MONTH_RE = re.compile(rf"\b(?:(?P<d1>[0-3]?\d)(?:st|nd|rd|th)?\s+(?:of\s+)?(?P<m1>{_MONTH_ALT})\b|(?P<m2>{_MONTH_ALT})\s+(?P<d2>[0-3]?\d)(?:st|nd|rd|th)?(?![\d.]?\d))")


def _day_months(text: str) -> list[tuple[int, str, str]]:
    """``(day, month, as written)`` for every day-month date of ``text``."""
    out: list[tuple[int, str, str]] = []
    for m in _DAY_MONTH_RE.finditer(text):
        day = int(m.group("d1") or m.group("d2"))
        if 1 <= day <= 31:
            out.append((day, (m.group("m1") or m.group("m2")).casefold(), " ".join(m.group(0).split())))
    return out


def day_month_differences(synthesized_text: str, source_texts: list[str]) -> list[str]:
    """Day-month dates compared at month resolution: a date of the synthesis ("6 May") that no cited source states, while
    a cited source states that day with another month ("6 March") or that month with another day the sources also give
    as a figure, is a changed date, wherever it stands in the sentence (the aligned comparison needs copied words after
    the change, and a date often closes its sentence). A day no source states at all is the plain introduced figure."""
    syn = _day_months(synthesized_text)
    if not syn:
        return []
    src = [d for t in source_texts for d in _day_months(t)]
    if not src:
        return []
    stated = {(d, m) for d, m, _w in src}
    src_days = {d for d, _m, _w in src}
    out: list[str] = []
    for d, m, written in syn:
        if (d, m) in stated:
            continue
        same_day = sorted({w for d2, m2, w in src if d2 == d and m2 != m})
        same_month = sorted({w for d2, m2, w in src if m2 == m and d2 != d}) if d in src_days else []
        if same_day:
            out.append(f"'{written}' where its cited sources state {same_day}: a month changed (no cited source states '{written}')")
        elif same_month:
            out.append(f"'{written}' where its cited sources state {same_month}: a day changed (no cited source states '{written}')")
    return list(dict.fromkeys(out))


def meaning_differences(synthesized_text: str, source_texts: list[str], transformation: str) -> list[str]:
    """How a synthesized claim says something other than its cited sources beyond its figures, as plain descriptions:
    the direction of a change reversed (a fall where every source states a rise, or the reverse), a statement copied
    from a cited source with one word exchanged for its opposite (a degree verdict, a comparative or superlative, an
    order in time, a comparison with a target, a direction), with a negation added or dropped, or with a content word
    replaced (:func:`aligned_changes`; under every transformation label), and an approximate figure of the sources
    stated as exact ("exactly 60" where a source says "roughly 60"). Lexical, not a proof: the findings built on it are
    warnings. ``transformation`` is kept for callers; every label is read the same way."""
    out: list[str] = []
    syn_words = set(_words(synthesized_text))
    src_words = set().union(*(set(_words(t)) for t in source_texts)) if source_texts else set()
    syn_rise, syn_fall = bool(syn_words & _RISE_WORDS), bool(syn_words & _FALL_WORDS)
    src_rise, src_fall = bool(src_words & _RISE_WORDS), bool(src_words & _FALL_WORDS)
    if syn_fall and not syn_rise and src_rise and not src_fall:
        out.append(f"it states a fall ({sorted(syn_words & _FALL_WORDS)}) where its cited sources state a rise ({sorted(src_words & _RISE_WORDS)})")
    elif syn_rise and not syn_fall and src_fall and not src_rise:
        out.append(f"it states a rise ({sorted(syn_words & _RISE_WORDS)}) where its cited sources state a fall ({sorted(src_words & _FALL_WORDS)})")
    _figs, aligned = aligned_differences(synthesized_text, source_texts)
    if out and any(a.startswith("it reverses the direction") for a in aligned):
        aligned = [a for a in aligned if not a.startswith("it reverses the direction")]
    out += aligned
    out += reversed_comparisons(synthesized_text, source_texts)
    out += reversed_voices(synthesized_text, source_texts)
    out += dropped_hedges(synthesized_text, source_texts)
    # Figures in words are read as digits first, so "roughly fifteen" is an approximate 15 and "exactly fifteen" an exact one.
    approx = {m.group(1) for t in source_texts for m in _APPROX_RE.finditer(_words_as_digits(_ungrouped(t)))}
    syn_plain = _ungrouped(synthesized_text)
    exact: dict[str, str] = {}
    for m in _EXACT_RE.finditer(_words_as_digits(syn_plain)):
        if m.group(2) in approx:
            exact.setdefault(m.group(2), m.group(1).casefold())
    for fig, word in sorted(exact.items()):
        written = next((w.group(0) for w in _EXACT_SHOWN_RE.finditer(syn_plain) if _words_as_digits(w.group(2)).split()[0].rstrip(".,;:") == fig), f"{word} {fig}")
        src_shown = next((w for t in source_texts for w in _approx_phrases(t) if w[1] == fig), None)
        where = f"'{src_shown[0]}'" if src_shown else f"{fig} as an approximate figure"
        out.append(f"it states '{written.strip(' .,;:')}' where its cited sources give {where}" + ("" if not src_shown else " (an approximate figure)"))
    return out


#: A hedge: the writer's own qualification of how far a statement is established ("suggested", "may", "probably", "the data
#: do not show", "rather than one the data show", "inferred ... rather than measured").
_HEDGE_RE = re.compile(
    r"\b(?:suggest(?:s|ed|ing)?|(?:may|might|could)\s+(?:have|be)\b|possibly|probably|perhaps|likely|unlikely|appears?\s+to|seems?\s+to|apparently|arguably|"
    r"tentative(?:ly)?|uncertain|unclear|unconfirmed|provisional(?:ly)?|inferred|presumably|plausibl[ey]|"
    r"(?:do|does|did)\s+not\s+(?:show|measure|prove|confirm)|not\s+(?:measured|shown|proven|proved|confirmed)|cannot\s+(?:be\s+)?(?:measured|confirmed|shown|proven)|"
    r"rather\s+than\s+(?:one|what|something)\s+(?:that\s+)?the\s+(?:data|evidence|table|figures?)\s+(?:show|shows|prove|proves|measure|measures))\b", re.IGNORECASE)


def dropped_hedges(synthesized_text: str, source_texts: list[str]) -> list[str]:
    """A hedge of a cited source dropped: the synthesis carries no hedge at all, while a cited source that hedges its
    statement ("this reason is a suggested process rather than one the data show") has most of its content words (half
    or more, three at least, hedges aside) restated in the synthesis: the qualification is gone and the router reads
    the statement as established."""
    if _HEDGE_RE.search(synthesized_text):
        return []
    syn_keys = _content_keys(synthesized_text)
    out = []
    for t in source_texts:
        for sentence in _ALIGN_SENTENCE_RE.split(t):
            hedges = [m.group(0) for m in _HEDGE_RE.finditer(sentence)]
            if not hedges:
                continue
            keys = _content_keys(_HEDGE_RE.sub(" ", sentence))
            if len(keys) >= 3 and len(keys & syn_keys) >= 3 and len(keys & syn_keys) * 2 >= len(keys):
                out.append(f"it drops the hedge its cited sources state ({', '.join(repr(h) for h in dict.fromkeys(hedges))} in '{' '.join(sentence.split())[:160]}'), so the statement reads as established")
    return list(dict.fromkeys(out))


def _approx_phrases(text: str) -> list[tuple[str, str]]:
    """``(phrase as written, value)`` for every approximate figure of ``text`` ("roughly fifteen", 15)."""
    plain = _ungrouped(text)
    out: list[tuple[str, str]] = []
    for m in re.finditer(r"\b(?:about|around|roughly|approximately|nearly|almost|some|close to|c\.|circa|ca\.|more than|over|under|less than|just over|just under)\s+(\S+(?:[\s-](?:hundred|thousand|million|billion|five|four|three|two|one|six|seven|eight|nine))?)", plain, re.IGNORECASE):
        value = _APPROX_RE.match(_words_as_digits(m.group(0)))
        if value is not None:
            out.append((m.group(0).strip(" .,;:"), value.group(1)))
    return out


#: "more X than Y", "less X than Y": the two sides of a comparison, read up to the end of the clause.
_COMPARISON_RE = re.compile(r"\b(?P<cmp>more|less|rather)\s+(?P<x>[^,;:.!?()]{3,80}?)\s+than\s+(?P<y>[^,;:.!?()]{3,80}?)(?=\s*(?:[,;:.!?()]|$|\b(?:but|so|while|whereas|because|when|which)\b))", re.IGNORECASE)
_RATHER_THAN_RE = re.compile(r"(?P<x>(?:[^\W\d_]+(?:['’-][^\W\d_]+)*\s+){1,6}?)rather\s+than\s+(?P<y>[^,;:.!?()]{3,80}?)(?=\s*(?:[,;:.!?()]|$|\b(?:but|so|while|whereas|because|when|which)\b))", re.IGNORECASE)


def _content_keys(text: str) -> set[str]:
    return {_akey(w) for w in _words(text) if len(w) >= 3 and w not in _ALIGN_STOP and _akey(w) not in _ALIGN_STOP}


def _comparisons(text: str) -> list[tuple[str, set[str], set[str], str]]:
    """``(kind, X, Y, phrase)`` for every "more X than Y" / "X rather than Y" of ``text`` (content stems of each side)."""
    out: list[tuple[str, set[str], set[str], str]] = []
    for m in _COMPARISON_RE.finditer(text):
        if m.group("cmp").casefold() == "rather":
            continue
        x, y = _content_keys(m.group("x")), _content_keys(m.group("y"))
        if x and y:
            out.append((m.group("cmp").casefold(), x, y, " ".join(m.group(0).split())))
    for m in _RATHER_THAN_RE.finditer(text):
        x, y = _content_keys(m.group("x")), _content_keys(m.group("y"))
        if x and y:
            out.append(("rather", x, y, " ".join(m.group(0).split())))
    return out


def reversed_comparisons(synthesized_text: str, source_texts: list[str]) -> list[str]:
    """A comparison whose two sides the synthesis exchanges: "more for its occurrence than for the timing of recovery"
    where a cited source states "more for the timing of recovery than for its occurrence" (each side of the synthesis
    shares more content words with the OTHER side of the source's comparison than with its own)."""
    src = [c for t in source_texts for c in _comparisons(t)]
    if not src:
        return []
    out: list[str] = []
    for kind, x, y, phrase in _comparisons(synthesized_text):
        for kind2, x2, y2, phrase2 in src:
            if kind != kind2 or (x == x2 and y == y2):
                continue
            if len(x & y2) > len(x & x2) and len(y & x2) > len(y & y2):
                out.append(f"it reverses the two sides of a comparison ('{phrase}' where its cited sources state '{phrase2}')")
                break
    return list(dict.fromkeys(out))


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


#: Quotation marks of every style (straight, curly, guillemets, primes): a quotation that differs from its source only in
#: its marks (the inner marks of a nested quotation dropped, double marks for single) is the same quotation.
_QUOTE_MARKS_RE = re.compile("[\"'“”‘’«»‹›„‚′″`]")


def _unmarked(text: str) -> str:
    return " ".join(_QUOTE_MARKS_RE.sub(" ", text).split())


def _holds_quotation(q: str, t: str) -> bool:
    """``t`` holds the quoted words ``q`` in a recognised form: exact, normalised, elided, a form difference, a long
    elision, or the same words once quotation marks are set aside on both sides ("say cheers" for "say 'cheers'")."""
    from ..translate.grounding import locate_long_elision, locate_quotation, locate_quotation_inexact
    if locate_quotation(q, t) is not None or locate_quotation_inexact(q, t) is not None or locate_long_elision(q, t) is not None:
        return True
    if not (_QUOTE_MARKS_RE.search(q) or _QUOTE_MARKS_RE.search(t)):
        return False
    uq = _unmarked(q)
    return bool(uq) and locate_quotation(uq, _unmarked(t)) is not None


def unlocated_quotations(text: str, corpus: list[str]) -> list[str]:
    """The quotations of ``text`` whose words occur, in any recognised form (exact, normalised, elided, a form difference,
    a long elision, the same words with their inner quotation marks dropped or changed), in none of ``corpus``: invented
    or altered quotations."""
    from ..adapters.markdown import cited_quotation_spans
    out: list[str] = []
    for _s, _e, inner in cited_quotation_spans(text):
        q = inner.strip().strip(".,;:!?").strip()
        if not q or not re.search(r"[^\W\d_]", q):
            continue
        if not any(_holds_quotation(q, t) for t in corpus):
            out.append(q)
    return list(dict.fromkeys(out))


def quotation_form_differences(text: str, corpus: list[str]) -> list[str]:
    """The quotations of ``text`` whose words occur in ``corpus`` only with other diacritics ("vivian solas" for "vivían
    solas"): a misspelt quotation, located, so no invented one (INT-LEDGER-028, a warning). A difference of quotation
    marks, capitals or line breaks is the quotation's form and is not reported."""
    from ..adapters.markdown import cited_quotation_spans
    from ..translate.grounding import locate_quotation, locate_quotation_inexact
    out: list[str] = []
    for _s, _e, inner in cited_quotation_spans(text):
        q = inner.strip().strip(".,;:!?").strip()
        if not q or not re.search(r"[^\W\d_]", q) or any(locate_quotation(q, t) is not None for t in corpus):
            continue
        for t in corpus:
            found = locate_quotation_inexact(q, t)
            if found is not None and "diacritic" in found[1]:
                out.append(f"'{q[:80]}' ({found[1]})")
                break
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
#: Most canonical spellings one figure gets (one per admissible count of significant figures).
_MAX_CANONICAL = 48
#: Longest numeral, in written digits, whose exact value the ledger builds; a longer one keeps its written spelling only.
_MAX_VALUE_DIGITS = 60
#: A unit spelled out after a figure ("2.0 grams", "3 kilojoules", "20 metres per second"); symbols ("g", "kJ", "m s⁻²")
#: are read with the SI reading's unit pattern. Per cent is no unit here: a per-cent figure keeps its own spellings.
_UNIT_WORD = (r"(?:kilo|mega|giga|tera|milli|micro|nano|pico|centi|deci)?(?:metre|meter|gramme|gram|second|ampere|amp|kelvin|mole|newton|joule|watt|"
              r"pascal|hertz|coulomb|volt|ohm|farad|tesla|litre|liter|minute|hour|day|radian|becquerel|electronvolt)s?")
_UNIT_WORDS_RE = re.compile(rf"{_UNIT_WORD}(?:\s+(?:squared|cubed))?(?:\s+per\s+{_UNIT_WORD}(?:\s+(?:squared|cubed))?)?", re.IGNORECASE)
#: What may close a unit read after a figure without being part of it.
_UNIT_TRAILING = ".,;:!?)]\"'’”"
_ASCII_DIGIT_RE = re.compile(r"[0-9]")


@dataclass(frozen=True)
class FigureUnit:
    """The unit written right after a figure, as the STEM unit table reads it: its dimension, its exact SI factor (None
    when the table has none, as for the angle degree) and, for an offset scale (°C, °F), its offset (SI value =
    factor·(x + offset))."""
    text: str
    dim: object
    factor: Optional[Fraction]
    offset: Optional[Fraction] = None

    def same(self, other: "FigureUnit") -> bool:
        """The same unit, however it is spelled ("J" and "N m", "h" and "hours")."""
        return (self.dim == other.dim and self.factor == other.factor and self.offset == other.offset
                and (self.factor is not None or _norm(self.text) == _norm(other.text)))

    def si(self, value: Fraction) -> Optional[Fraction]:
        if self.factor is None:
            return None
        return self.factor * (value + self.offset) if self.offset is not None else self.factor * value


@lru_cache(maxsize=1024)
def _read_unit(candidate: str) -> Optional[FigureUnit]:
    """``candidate`` as one unit expression the STEM table reads unambiguously (one dimension, one factor), written as
    symbols the SI reading accepts after a figure or as unit words; None otherwise."""
    from ..stem.si_reading import si_unit_pattern
    from ..stem.units import parse_unit
    if not candidate or "%" in candidate or _ASCII_DIGIT_RE.search(candidate) or len(candidate) > 48:
        return None
    if not (re.fullmatch(si_unit_pattern(), candidate) or _UNIT_WORDS_RE.fullmatch(candidate)):
        return None
    expr = parse_unit(candidate)
    if expr is None or not expr.known:
        return None
    readings = expr.readings
    if len({r.dim for r in readings}) != 1 or len({r.factor for r in readings}) != 1 or len({r.affine for r in readings}) != 1 or readings[0].dim is None:
        return None
    r = readings[0]
    return FigureUnit(text=candidate, dim=r.dim, factor=r.factor, offset=(r.affine[1] if r.affine is not None else None))


def _unit_after(text: str, pos: int) -> Optional[FigureUnit]:
    """The unit written right after the figure that ends at ``pos`` (no space or one space between them; at most four
    words of the same line, the longest that reads as one unit), or None."""
    j = pos
    if j < len(text) and text[j] in " \u00a0\u2009\u202f":
        j += 1
    if j >= len(text) or not (text[j].isalpha() or text[j] in "µμΩ°Å"):
        return None
    stop = text.find("\n", j)
    chunk = text[j:(min(stop, j + 64) if stop >= 0 else j + 64)]
    words = chunk.split()[:4]
    for n in range(len(words), 0, -1):
        unit = _read_unit(" ".join(words[:n]).rstrip(_UNIT_TRAILING))
        if unit is not None:
            return unit
    return None


def _decimal_digits(value: Fraction) -> Optional[tuple[str, int]]:
    """``(digits, exponent)`` with ``|value| = int(digits) · 10^exponent`` and no trailing zero in ``digits``, for a
    non-zero terminating decimal; None otherwise (a third, zero)."""
    if value == 0:
        return None
    num, den = abs(value.numerator), value.denominator
    rest, twos, fives = den, 0, 0
    while rest % 2 == 0:
        rest, twos = rest // 2, twos + 1
    while rest % 5 == 0:
        rest, fives = rest // 5, fives + 1
    if rest != 1:
        return None
    places = max(twos, fives)
    digits = str(num * 10 ** places // den)
    stripped = digits.rstrip("0")
    return stripped, len(digits) - len(stripped) - places


def canonical_spellings(value: Fraction, lo: int, hi: int) -> frozenset[str]:
    """The precision-aware spellings of an exact value: ``d.ddd e<exponent>`` with exactly n significant digits, one per
    admissible count n in ``[lo, hi]`` (a count too small to write the value exactly is skipped: a value is never rounded
    into a spelling). ``3/100`` to two figures is ``3.0e-2``; ``300`` written without a point (one to three figures) is
    ``3e2``, ``3.0e2`` and ``3.00e2``."""
    dd = _decimal_digits(value)
    if dd is None:
        return frozenset()
    digits, exp = dd
    m = len(digits)
    sign = "-" if value < 0 else ""
    lead = exp + m - 1  # the power of ten of the leading digit
    out = set()
    for n in range(max(lo, m), min(hi, m + _MAX_CANONICAL) + 1):
        mant = digits + "0" * (n - m)
        out.add(f"{sign}{mant[0]}{'.' + mant[1:] if n > 1 else ''}e{lead}")
    return frozenset(out)


def _token_reading(tok: str) -> tuple[Optional[Fraction], Optional[tuple[int, int]], Optional[Fraction]]:
    """``(value, significant-figure range, half a unit in the last written place)`` of a plain numeral ("0.030" ->
    (3/100, (2, 2), 1/2000); "1500" -> (1500, (2, 4), 1/2): the trailing zeros of an integer written without a point may
    or may not be significant, but a conversion is held to its last written digit)."""
    body = tok.lstrip("-")
    if not body or len(body) > _MAX_VALUE_DIGITS:
        return None, None, None
    try:
        value = Fraction(tok)
    except (ValueError, ZeroDivisionError):
        return None, None, None
    if "." in body:
        ip, fp = body.split(".", 1)
        n = len((ip + fp).lstrip("0")) or 1
        return value, (n, n), Fraction(1, 2) / 10 ** len(fp)
    sig = body.lstrip("0")
    if not sig:
        return value, (1, 1), Fraction(1, 2)
    core = sig.rstrip("0")
    # half a unit in the last written digit: a conversion is held to the figure as written ("300 K" for 25 °C is not one)
    return value, (len(core), len(sig)), Fraction(1, 2)


def _value_key(spelling: str) -> str:
    """A normalised scientific spelling without its mantissa's trailing zeros ("1.50e999" -> "1.5e999"): the value a
    figure read by its digits alone states, whatever its precision."""
    mant, _, exp = spelling.partition("e")
    if "." in mant:
        mant = mant.rstrip("0").rstrip(".")
    return f"{mant}e{exp}"


def _normalised_scientific(surface: str) -> Optional[str]:
    """The precision-aware spelling of a figure in scientific notation read from its digits alone (no value is built):
    for a figure beyond the number scanner's bounds ("1e999", "1.0 × 10^999" -> "1.0e999"), compared by what is
    written."""
    m = re.match(r"^\s*([-−]?)(\d+)(?:\.(\d+))?", surface)
    e = re.search(r"(?:[eE]|10\^\{?|10\*\*|10)([-+−⁻]?)([0-9⁰¹²³⁴⁵⁶⁷⁸⁹]{1,7})\}?\s*$", surface)
    if m is None or e is None:
        return None
    sup = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789")
    exp = int(e.group(2).translate(sup)) * (-1 if e.group(1) in ("-", "−", "⁻") else 1)
    ip, fp = m.group(2), m.group(3) or ""
    digits = (ip + fp)
    lead_zeros = len(digits) - len(digits.lstrip("0"))
    sig = digits.lstrip("0")
    if not sig:
        return None
    lead = exp + len(ip) - 1 - lead_zeros  # the power of ten of the first significant digit
    sign = "-" if m.group(1) else ""
    return f"{sign}{sig[0]}{'.' + sig[1:] if len(sig) > 1 else ''}e{lead}"


class _Figure:
    """One figure or date of a text: ``keys`` are its equivalent spellings (the numeral; with a scale word also
    "<numeral> <scale>" and the scaled value, so "a million" meets "1 million" and "1,000,000"; for a numeral, its
    precision-aware spellings, :func:`canonical_spellings`, so "3.0e-2" meets "0.030" and not "0.03"), ``mantissa`` and
    ``scale`` its parts, ``label`` how a finding shows it (the numeral, a month-year, or the words as written).
    ``value`` is its exact value (scale applied; None for a date or a figure read by its digits alone), ``sig`` the range
    of its significant figures, ``half`` half a unit in its last written place (in its own unit), ``unit`` the unit
    written after it (:class:`FigureUnit`) and ``unread`` marks a figure beyond the number scanner's bounds, compared by
    its normalised written form only."""
    __slots__ = ("keys", "mantissa", "scale", "label", "value", "sig", "half", "unit", "unread", "vkey")

    def __init__(self, mantissa: str, scale: Optional[str], label: str, extra: tuple[str, ...] = (), *, value: Optional[Fraction] = None,
                 sig: Optional[tuple[int, int]] = None, half: Optional[Fraction] = None, unit: Optional[FigureUnit] = None,
                 unread: bool = False, mantissa_key: bool = True) -> None:
        keys = {mantissa, *extra} if mantissa_key else set(extra)
        if scale:
            keys.add(f"{mantissa} {scale}")
            try:
                v = Fraction(mantissa) * _SCALES[scale]
                keys.add(_fmt(v.numerator, v.denominator))
            except (ValueError, ZeroDivisionError):
                pass
        if value is not None and sig is not None:
            keys |= canonical_spellings(value, sig[0], sig[1])
        self.keys = frozenset(keys)
        self.mantissa = mantissa
        self.scale = scale
        self.label = label
        self.value = value
        self.sig = sig
        self.half = half
        self.unit = unit
        self.unread = unread
        self.vkey = _value_key(mantissa) if unread else None


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
    STEM number scanner; its spellings are its precision-aware spellings (:func:`canonical_spellings`: "3.0e8" is
    ``3.0e8``, never the less precise ``3e8``). A figure beyond the scanner's bounds (an exponent over 99, over 30
    digits) is not read as a value, and its parts are not read as figures either (the caller masks every span returned;
    the exact decimal is None for it and its spellings are its normalised written form, :func:`_normalised_scientific`)."""
    return [(start, end, exact, spellings, surface) for start, end, exact, spellings, surface, _number in _scientific_readings(text)]


def _scientific_readings(text: str) -> list[tuple[int, int, Optional[str], frozenset[str], str, object]]:
    from ..stem.normalize import reading_view
    from ..stem.numbers import scan_number
    out: list[tuple[int, int, Optional[str], frozenset[str], str, object]] = []
    for m in _SCI_FIGURE_RE.finditer(text):
        surface = m.group(0)
        body = reading_view(surface)
        sign = -1 if body.startswith("-") else 1
        body = body.lstrip("-")
        scan = scan_number(body, 0, orig=body)
        shown = " ".join(surface.split())
        if scan is None or scan.number is None or scan.end != len(body) or not scan.number.scientific:
            normal = _normalised_scientific(surface)
            out.append((m.start(), m.end(), None, frozenset({normal} if normal else ()), shown, None))  # masked; compared by its digits
            continue
        value = sign * scan.number.value
        n = scan.number.sig_figs
        out.append((m.start(), m.end(), _exact_decimal(value), canonical_spellings(value, n, n), shown, (value, (n, n), scan.number.half_width)))
    return out


def _figures(text: str) -> list[_Figure]:
    """Every figure and date of ``text``: numerals (thousands separators removed) with any scale word after them,
    figures in scientific notation (one figure each, :func:`_scientific_figures`), figures written in words
    (:func:`_word_figures`), and month-year dates. Each numeral carries its exact value, its significant figures and
    the unit written after it (:class:`_Figure`). A figure written after a minus sign (U+2212 and the other glyphs of
    :data:`_MINUS_SIGNS`, as a sign: not after a letter or digit) is signed exactly as after the ASCII hyphen-minus, so
    "−352.19" and "-352.19" are one figure and "352.19" for either is a change; a figure after a hyphen or dash
    (U+2010 to U+2013, also range and punctuation marks) keeps its unsigned reading and also carries its signed spelling."""
    plain = _ungrouped(_LIST_MARKER_RE.sub(" ", text))
    out: list[_Figure] = []
    masked = plain
    accounting = {_COMMA_THOUSANDS_RE.sub("", m.group("a") or m.group("b")) for m in _ACCOUNTING_AMOUNT_RE.finditer(text)} if "(" in text else set()
    if any(ch in plain for ch in "sdSD"):
        # a precision note ("4.9 N (2 s.f.)", "to 3 d.p.", "correct to 2 significant figures") states how a figure is
        # written, never a figure of the statement (repair round 5, rerun-combinator-faults-8 variant)
        masked = _PRECISION_NOTE_RE.sub(lambda m: " " * len(m.group(0)), masked)
    if "^" in plain:
        # a unit's exponent written with a caret ("dm^-3", "m s^-1", "cm^3") is part of the unit, as "dm⁻³" is: no figure
        # (repair round 4, rerun-combinator-faults-8 variant: "mol dm^-3" gave a figure -3 that "mol dm⁻³" does not)
        masked = _CARET_UNIT_EXPONENT_RE.sub(lambda m: m.group(1) + " " * (len(m.group(0)) - len(m.group(1))), masked)
    if "10" in plain or "e" in plain or "E" in plain:
        for start, end, exact, spellings, surface, reading in _scientific_readings(plain):
            unit = _unit_after(plain, end)
            if exact is not None and reading is not None:
                value, sig, half = reading
                out.append(_Figure(exact, None, surface, tuple(spellings), value=value, sig=sig, half=half, unit=unit, mantissa_key=False))
            elif spellings:
                spelling = next(iter(spellings))
                n = len(spelling.partition("e")[0].lstrip("-").replace(".", ""))
                out.append(_Figure(spelling, None, surface, tuple(spellings), sig=(n, n), unit=unit, unread=True))
            masked = masked[:start] + " " * (end - start) + masked[end:]
    for start, end, mantissa, scale, surface in _word_figures(masked):
        value, sig, _half = _token_reading(mantissa)
        if value is not None and sig is not None:
            value = value * _SCALES[scale] if scale else value
            if value.denominator == 1 and value != 0:  # words state no precision: any count up to the integer's own digits
                sig = (sig[0], max(sig[1], len(str(abs(value.numerator)))))
        # words state no last written place, so a conversion of a figure in words must be exact (half None)
        out.append(_Figure(mantissa, scale, " ".join(surface.split()), value=value, sig=sig, unit=_unit_after(plain, end)))
        masked = masked[:start] + " " * (end - start) + masked[end:]
    for m in _FIGURE_RE.finditer(masked):
        tok = m.group(0)
        if tok.endswith("s"):  # a decade ("1840s", "1840's"): one date, never scaled
            tok = tok.replace("'", "").replace("’", "")
            out.append(_Figure(tok, None, tok))
            continue
        sc = _SCALE_AFTER_RE.match(masked, m.end())
        scale = sc.group(1).casefold() if sc else None
        at = m.start()
        sign_glyph = (not tok.startswith("-") and at > 0 and (at < 2 or not masked[at - 2].isalnum())
                      and (masked[at - 1] in _MINUS_SIGNS
                           or (masked[at - 1] in _DASH_SIGNS and not masked[max(0, at - 24):at - 1].rstrip()[-1:].isdigit()
                               and masked[max(0, at - 24):at - 1].rstrip()[-1:] not in (")", "]"))))
        if not sign_glyph and not tok.startswith("-") and at > 1 and masked[at - 1] == " " and masked[at - 2] in _MINUS_SIGNS:
            # a minus sign set apart from its figure in a sign's place ("x = − 3", "(− 0.5)"): after a relation sign, an
            # opening bracket or the start, never after a figure or a letter ("5 − 3" is a difference); repair round 4
            before = masked[max(0, at - 26):at - 2].rstrip()
            sign_glyph = before[-1:] in ("", "=", "(", "[", "<", ">", "≈", "≤", "≥", ":", ",")
        if sign_glyph:  # "−0.5": a minus sign, read as "-0.5"
            tok = f"-{tok}"
        value, sig, half = _token_reading(tok)
        if value is not None and scale:
            value, half = value * _SCALES[scale], (half * _SCALES[scale] if half is not None else None)
        signed: tuple[str, ...] = ()
        if not tok.startswith("-") and at > 0 and _MINUS_GLYPH_RE.match(masked, at - 1):
            signed = (f"-{tok}",) + ((f"-{tok} {scale}",) if scale else ())
        elif not tok.startswith("-") and tok in accounting and "(" in masked[max(0, at - 4):at]:
            # accounting parentheses around an amount alone ("(1,250.75)", "($450)") write it negative: the figure keeps
            # its unsigned reading and carries its signed spelling (repair round 5, rerun-combinator-faults-8 variant)
            signed = (f"-{tok}",) + ((f"-{tok} {scale}",) if scale else ())
        elif not tok.startswith("-") and (_DECREASE_BEFORE_RE.search(masked[max(0, at - 48):at]) or _DECREASE_AFTER_RE.match(masked, m.end())):
            # the sign stated in words: "fell 12.50%", "a fall of 12.50%", "a 12.50% drop" restate "−12.50%" (whatever the glyph)
            signed = (f"-{tok}",) + ((f"-{tok} {scale}",) if scale else ())
        out.append(_Figure(tok, scale, tok, signed, value=value, sig=sig, half=half, unit=_unit_after(plain, sc.end() if sc else m.end())))
    out += [_Figure(f"{m.group(1).casefold()} {m.group(2)}", None, f"{m.group(1).casefold()} {m.group(2)}") for m in _MONTH_YEAR_RE.finditer(plain)]
    return out


def figure_spellings(text: str, *, with_scale: bool = False) -> list[tuple[str, frozenset[str]]]:
    """``(label, spellings)`` for every figure and date of ``text`` (digits, words, scale words, month-years): two figures
    are the same when their spellings meet ("a million", "1 million" and "1,000,000"; "3.0e-2" and "0.030"). With
    ``with_scale`` a numeral's label carries its scale word ("2.5 million"), as a finding should name it."""
    return [((f"{f.label} {f.scale}" if with_scale and f.scale and f.label == f.mantissa else f.label), f.keys) for f in _figures(text)]


#: Words of a crediting clause that never pair a date with an event: the colleague's name and the crediting verbs.
_CREDIT_FILLER = frozenset(light_stem(w) for w in ("history english economics psychology business specialist specialists colleague report account "
                                                   "dates dated gives gave puts placed places records recorded notes noted states stated says said "
                                                   "writes wrote reports reported according words figure figures date year years statistic").split())


def _event_stem(word: str) -> str:
    """An event word's key for date pairing: a possessive dropped, :func:`light_stem`, and a noun in -ion read as its verb
    ("dedication" and "dedicated" meet at "dedicat", "the statue's" and "the statue" at "statu")."""
    w = word.casefold()
    if w.endswith(("'s", "’s")):
        w = w[:-2]
    w = light_stem(w.rstrip("'’"))
    return w[:-3] if w.endswith("ion") and len(w) > 7 else w


def _clause_event_words(clause: list[str], surface: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for w in clause:
        low = w.casefold()
        if _is_numeral(w) or low in _PARTNER_STOP or len(low) < 3:
            continue
        key = _event_stem(low)
        if key in _MONTH_STEMS or key in _CREDIT_FILLER or light_stem(low) in _CREDIT_FILLER:
            continue
        surface.setdefault(key, low)
        out.add(key)
    return out


def _year_partners(text: str, surface: dict[str, str]) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """``(years_of_word, words_of_year)``: per event word (:func:`_event_stem`), the years and decades stated in the same
    clause of ``text`` (:func:`_clauses`), and per year the event words of its clauses."""
    years_of: dict[str, set[str]] = {}
    words_of: dict[str, set[str]] = {}
    for clause in _clauses(text):
        years = {tok for i, tok in enumerate(clause) if _is_numeral(tok) and _figure_kind(clause, i) in ("year", "decade")}
        if not years:
            continue
        words = _clause_event_words(clause, surface)
        for w in words:
            years_of.setdefault(w, set()).update(years)
        for y in years:
            words_of.setdefault(y, set()).update(words)
    return years_of, words_of


def credited_date_repairings(stated: str, peer_text: str) -> list[str]:
    """Dates a clause credited to a colleague pairs with an event the colleague dates otherwise: a year (or decade) the
    clause states with event words that the peer report states, in its clauses, only with other years, while the peer
    states this year with another event ("The History specialist dates the sonnet to 1886" where the peer writes "wrote
    the sonnet in 1883" and "dedicated on 28 October 1886"). Every event word of the clause that the peer dates must
    disagree: one that the peer dates with this year too ("the statue's dedication to 1886") clears it. A year the peer
    never states is the plain INT-REQ-014 case; event words the peer dates nowhere decide nothing."""
    surface: dict[str, str] = {}
    years_of, words_of = _year_partners(peer_text, surface)
    if not years_of:
        return []
    out: list[str] = []
    for clause in _clauses(stated):
        words = _clause_event_words(clause, surface)
        dated = {w: years_of[w] for w in words if w in years_of}
        if not dated:
            continue
        for i, tok in enumerate(clause):
            if not _is_numeral(tok) or _figure_kind(clause, i) not in ("year", "decade") or tok not in words_of:
                continue
            if any(tok in ys for ys in dated.values()):
                continue
            others = sorted(set().union(*dated.values()))
            shown = [surface.get(w, w) for w in sorted(dated)]
            own = [surface.get(w, w) for w in sorted(words_of[tok])][:6]
            out.append(f"'{tok}' is stated with {shown}, which the peer report dates only {others}; the peer states '{tok}' with {own} (a date re-paired to another event)")
    return list(dict.fromkeys(out))


#: Figures a source states that are no content of its own: a formula constant ("× 100", "÷ 10", "/ 1000"), a reference to
#: a part of a text or a task ("paragraph 1", "part 2", "line 14", "Table 1", "Paper 2", "question 3", "stanza 4") and a
#: mark annotation ("[1]", "[2 marks]", "[1 spare]"). A synthesis that leaves them out drops no figure (INT-LEDGER-024).
_INCIDENTAL_FIGURE_RE = re.compile(
    r"(?:[×÷*/x]\s*(?P<k>10{1,3})(?![\d.,]))"
    r"|(?:\b(?:paragraphs?|paras?|parts?|lines?|stanzas?|sections?|tables?|figures?|figs?\.?|diagrams?|questions?|papers?|items?|pages?|pp?\.|steps?|criteri(?:on|a)|units?|topics?)\s+(?P<r>\d{1,3})(?![\d.,]\d))"
    r"|(?:\[\s*(?P<m>\d{1,2})\s*(?:marks?|spare)?\s*\])", re.IGNORECASE)


def incidental_figures(text: str) -> set[str]:
    """The labels of the figures of ``text`` that are formula constants, references to a part of a text or task, or mark
    annotations (:data:`_INCIDENTAL_FIGURE_RE`), unless the same numeral also stands in ``text`` as content elsewhere."""
    plain = _ungrouped(text)
    out: set[str] = set()
    spans: list[tuple[int, int]] = []
    for m in _INCIDENTAL_FIGURE_RE.finditer(plain):
        g = m.group("k") or m.group("r") or m.group("m")
        if g:
            out.add(g)
            key = "k" if m.group("k") else "r" if m.group("r") else "m"
            spans.append(m.span(key))
    if not out:
        return out
    for m in _FIGURE_RE.finditer(plain):  # the numeral stated as content somewhere else keeps its place
        if m.group(0) in out and not any(a <= m.start() < b for a, b in spans):
            out.discard(m.group(0))
    return out


#: Number words of the languages the subject specialists answer in besides English (Spanish, French, German, Italian,
#: Portuguese), whole words only; words that are also English words with another meaning ("cent", "sept") are left out.
_FOREIGN_NUMBER_WORDS: dict[str, int] = {
    "uno": 1, "una": 1,
    **dict(zip("dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis diecisiete dieciocho diecinueve veinte".split(), range(2, 21))),
    **{"treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100, "mil": 1000},
    **dict(zip("un une deux trois quatre cinq six huit neuf dix onze douze treize quatorze quinze seize".split(), (1, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 15, 16))),
    **{"vingt": 20, "trente": 30, "quarante": 40, "cinquante": 50, "soixante": 60, "mille": 1000},
    **dict(zip("eins zwei drei vier fünf sechs sieben acht neun zehn elf zwölf zwanzig dreißig hundert tausend".split(), (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 30, 100, 1000))),
    **dict(zip("due quattro sei sette otto nove dieci undici dodici tredici quindici venti trenta cento".split(), (2, 4, 6, 7, 8, 9, 10, 11, 12, 13, 15, 20, 30, 100))),
    **dict(zip("dois duas quatro cinco seis sete oito nove dez onze doze vinte trinta cem".split(), (2, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 20, 30, 100))),
}
_FOREIGN_NUMBER_RE = re.compile(r"(?<![\w-])(" + "|".join(sorted(map(re.escape, _FOREIGN_NUMBER_WORDS), key=len, reverse=True)) + r")(?![\w-])", re.IGNORECASE)


def foreign_number_values(text: str) -> set[str]:
    """The values of the number words of ``text`` written in Spanish, French, German, Italian or Portuguese ("doce" ->
    "12"), as figure keys: a synthesis that gives a source's "doce vecinos" as "twelve neighbours" states no new figure."""
    return {str(_FOREIGN_NUMBER_WORDS[m.group(1).casefold()]) for m in _FOREIGN_NUMBER_RE.finditer(text)} if text else set()


def figure_tokens(text: str) -> set[str]:
    """The figures of ``text`` as tokens, the units of a figure/date fidelity comparison between a synthesized claim and
    its sources: numerals (thousands separators removed), month-year tokens, and figures written in words as their value
    ("two million" -> "2", "a tenth" -> "0.1"). A figure in scientific notation beyond the number scanner's bounds has
    no exact value and is no token (the ledger still compares it by its normalised written form)."""
    return {f.mantissa for f in _figures(text) if not f.unread}


def _sig_text(f: _Figure) -> str:
    if f.sig is None:
        return "an unstated number of significant figures"
    lo, hi = f.sig
    return f"{lo} significant figure{'' if lo == 1 else 's'}" if lo == hi else f"{lo} to {hi} significant figures"


def _sig_overlap(a: _Figure, b: _Figure) -> bool:
    """The two figures may state the same number of significant figures (a figure with no stated precision may)."""
    if a.sig is None or b.sig is None:
        return True
    return max(a.sig[0], b.sig[0]) <= min(a.sig[1], b.sig[1])


def _units_agree(a: Optional[FigureUnit], b: Optional[FigureUnit]) -> bool:
    """No unit change: the same unit, or a unit stated on one side only (an omitted unit is no different unit)."""
    return a is None or b is None or a.same(b)


def _converts(g: _Figure, f: _Figure) -> bool:
    """``g`` states ``f``'s quantity in another, commensurable unit (same dimension, exact SI factors): the two agree in
    SI to within half a unit in ``g``'s last written place ("0.0020 kg" for "2.0 g", "90 min" for "1.5 h"). Units of
    different dimensions are never converted."""
    if g.unit is None or f.unit is None or g.value is None or f.value is None or g.unit.same(f.unit) or g.unit.dim != f.unit.dim:
        return False
    a, b = g.unit.si(g.value), f.unit.si(f.value)
    if a is None or b is None:
        return False
    tolerance = abs((g.half or Fraction(0)) * g.unit.factor) if g.unit.factor is not None else Fraction(0)
    return abs(a - b) <= tolerance


def _same_value(g: _Figure, f: _Figure) -> bool:
    if g.value is not None and f.value is not None:
        return g.value == f.value and _units_agree(g.unit, f.unit)
    return g.vkey is not None and g.vkey == f.vkey and _units_agree(g.unit, f.unit)


def _tolerance(g: _Figure) -> Fraction:
    """Half a unit in ``g``'s last written place, in SI (0 for a figure with no stated last place)."""
    return abs((g.half or Fraction(0)) * g.unit.factor) if g.unit is not None and g.unit.factor is not None else Fraction(0)


class _FigureIndex:
    """Figures indexed by spelling, by value and, per dimension, by SI quantity in order, so that comparing two texts
    costs about the sum of their figure counts, never their product."""

    def __init__(self, figs: list[_Figure]) -> None:
        from bisect import bisect_left, bisect_right
        self._lo, self._hi = bisect_left, bisect_right
        self.figs = figs
        self.by_key: dict[str, list[_Figure]] = {}
        self.by_value: dict[object, list[_Figure]] = {}
        quantities: dict[object, list[tuple[Fraction, int]]] = {}
        self.max_tolerance: dict[object, Fraction] = {}
        for i, f in enumerate(figs):
            for k in f.keys:
                self.by_key.setdefault(k, []).append(f)
            if f.value is not None:
                self.by_value.setdefault(("v", f.value), []).append(f)
            elif f.vkey:
                self.by_value.setdefault(("k", f.vkey), []).append(f)
            si = f.unit.si(f.value) if f.unit is not None and f.value is not None else None
            if si is not None:
                quantities.setdefault(f.unit.dim, []).append((si, i))
                self.max_tolerance[f.unit.dim] = max(self.max_tolerance.get(f.unit.dim, Fraction(0)), _tolerance(f))
        self.quantities = {d: sorted(v) for d, v in quantities.items()}
        self.si_values = {d: [q for q, _i in v] for d, v in self.quantities.items()}
        # one answer per set of spellings, and per figure as written (close round 3, DV2-06: a text of one repeated figure
        # made every figure read every other figure that shares its spelling, the product of the two counts)
        self._spelled: dict[frozenset, list[_Figure]] = {}
        self._carried: dict[tuple, bool] = {}

    def spelled(self, g: _Figure) -> list[_Figure]:
        """The indexed figures sharing a spelling with ``g`` (one list per set of spellings; callers do not change it)."""
        found = self._spelled.get(g.keys)
        if found is None:
            out: dict[int, _Figure] = {}
            for k in g.keys:
                for f in self.by_key.get(k, ()):
                    out.setdefault(id(f), f)
            found = list(out.values())
            self._spelled[g.keys] = found
        return found

    def same_value(self, g: _Figure) -> list[_Figure]:
        """The indexed figures stating ``g``'s value with a unit that agrees (the same, or stated on one side only)."""
        key = ("v", g.value) if g.value is not None else (("k", g.vkey) if g.vkey else None)
        if key is None:
            return []
        return [f for f in self.by_value.get(key, ()) if _units_agree(g.unit, f.unit)]

    def _window(self, dim, centre: Fraction, width: Fraction) -> list[_Figure]:
        sis = self.si_values.get(dim)
        if not sis:
            return []
        lo, hi = self._lo(sis, centre - width), self._hi(sis, centre + width)
        return [self.figs[i] for _q, i in self.quantities[dim][lo:hi]]

    def converted_by(self, g: _Figure) -> list[_Figure]:
        """The indexed figures whose quantity ``g`` states in another commensurable unit (:func:`_converts`)."""
        if g.unit is None or g.value is None:
            return []
        si = g.unit.si(g.value)
        if si is None:
            return []
        return [f for f in self._window(g.unit.dim, si, _tolerance(g)) if _converts(g, f)]

    def converting(self, f: _Figure) -> list[_Figure]:
        """The indexed figures that state ``f``'s quantity in another commensurable unit (each to its own tolerance)."""
        if f.unit is None or f.value is None:
            return []
        si = f.unit.si(f.value)
        if si is None:
            return []
        return [g for g in self._window(f.unit.dim, si, self.max_tolerance.get(f.unit.dim, Fraction(0))) if _converts(g, f)]

    def carries(self, f: _Figure) -> bool:
        """Some indexed (synthesized) figure carries source figure ``f`` (:func:`_carries`). The answer depends only on what
        ``f`` states (its spellings, value, unit and precision), so it is read once per figure as written."""
        sig = _figure_signature(f)
        known = self._carried.get(sig)
        if known is None:
            known = any(k in self.by_key for k in f.keys) or bool(self.same_value(f)) or bool(self.converting(f))
            self._carried[sig] = known
        return known


def _figure_signature(g: _Figure) -> tuple:
    """Everything a figure comparison of the ledger reads of ``g``: two figures with the same signature are compared alike."""
    return (g.keys, g.mantissa, g.scale, g.label, g.value, g.sig, g.half, g.unit, g.unread, g.vkey)


def _carries(g: _Figure, f: _Figure) -> bool:
    """Synthesized figure ``g`` carries source figure ``f`` (so ``f`` is not dropped): the same spelling, the same value
    with other significant figures (a precision change, reported as one), or the same quantity in a commensurable unit."""
    return bool(g.keys & f.keys) or _same_value(g, f) or _converts(g, f)


def _shown(f: _Figure) -> str:
    return f"{f.label} {f.unit.text}" if f.unit is not None else f.label


@dataclass
class FigureChanges:
    """How a synthesized claim's figures differ from its cited sources', as distinct outcomes: ``introduced`` (a value
    that occurs in no source under any spelling, precision or commensurable unit: a changed or new figure), ``dropped``
    (a source figure no synthesized figure carries), ``rescaled`` (a changed scale word), ``reprecised`` (a source's
    value with other significant figures: "0.03" for "3.0e-2"), ``reunited`` (a source's numeral with another unit that
    is not its value converted: "2.0 kg" for "2.0 g"). A change of form only ("0.030 J" for "3.0e-2 J", "0.0020 kg"
    for "2.0 g") is none of these."""
    introduced: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    rescaled: list[str] = field(default_factory=list)
    reprecised: list[str] = field(default_factory=list)
    reunited: list[str] = field(default_factory=list)


def figure_changes(synthesized_text: str, source_texts: list[str]) -> FigureChanges:
    """The typed comparison of a synthesized claim's figures with its sources' (:class:`FigureChanges`). Figures are
    compared by their precision-aware spellings first; a figure whose spelling meets a source figure's is the same
    numeral, and a unit change when every source figure it meets states a unit and none is its unit (a unit on one side
    only is no change). A figure whose spelling meets none is a precision change when a source states its exact value
    (in the same unit or with no unit), a faithful conversion when a source states its quantity in a commensurable unit
    (a precision change if the significant figures cannot agree), and otherwise an introduced figure. A figure that only
    a source in another language states in its own words ("doce" for "twelve") is no introduced figure."""
    # a step label states no figure where the other side states the same label in any notation ("Trial 1" for "the first
    # trial"; repair round 5, rerun-combinator-faults-7 variant)
    src_labels = set().union(*(step_labels(t) for t in source_texts)) if source_texts else set()
    syn_labels = step_labels(synthesized_text)
    syn = _figures(_masked_step_labels(synthesized_text, src_labels))
    src = [f for t in source_texts for f in _figures(_masked_step_labels(t, syn_labels))]
    src_keys = set().union(*(f.keys for f in src)) if src else set()
    foreign = set().union(*(foreign_number_values(t) for t in source_texts)) if source_texts else set()
    sources, synthesized = _FigureIndex(src), _FigureIndex(syn)
    out = FigureChanges()
    introduced: set[str] = set()
    reprecised: set[str] = set()
    reunited: set[str] = set()
    read: set[tuple] = set()  # every outcome below depends only on what the figure states: one reading per figure as written
    for g in syn:
        sig = _figure_signature(g)
        if sig in read:
            continue
        read.add(sig)
        hits = sources.spelled(g)
        if hits:
            if g.unit is not None and all(f.unit is not None and not f.unit.same(g.unit) for f in hits) and not sources.converted_by(g):
                f = hits[0]
                kind = "another kind of quantity" if f.unit.dim != g.unit.dim else "the same numeral in another unit, so another quantity"
                reunited.add(f"'{_shown(g)}' where the cited sources state {_shown(f)} ({kind})")
            continue
        if g.keys & foreign:
            continue
        if _bits_in_cells(g.label, source_texts):
            continue  # a row of bits a source's table states cell by cell ("010" for "| 0 | 1 | 0 |")
        same = sources.same_value(g)
        if same:
            f = same[0]
            reprecised.add(f"'{_shown(g)}' where the cited sources state {_shown(f)} ({_sig_text(f)} there, {_sig_text(g)} here)")
            continue
        converted = sources.converted_by(g)
        if converted:
            # significant figures carry over a change of factor ("2.0 g" is "0.0020 kg") but not over an offset scale
            # ("25 °C" is "298 K" or "298.15 K"), where the tolerance alone decides
            if not any(_sig_overlap(g, f) or g.unit.offset is not None or f.unit.offset is not None for f in converted):
                f = converted[0]
                reprecised.add(f"'{_shown(g)}' converts {_shown(f)} to other significant figures ({_sig_text(f)} there, {_sig_text(g)} here)")
            continue
        introduced.add(g.label)
    out.introduced = _sorted_tokens(introduced)
    out.dropped = _sorted_tokens({f.label for f in src if not synthesized.carries(f)})
    out.reprecised = sorted(reprecised)
    out.reunited = sorted(reunited)
    rescaled: list[str] = []
    scales_of: dict[str, set[str]] = {}  # the scale words the sources write after each mantissa, read once (close round 3, DV2-06)
    for g in src:
        if g.scale:
            scales_of.setdefault(g.mantissa, set()).add(g.scale)
    for f in syn:
        if not f.scale or not (f.keys & src_keys) or (f.keys - {f.mantissa}) & src_keys:
            continue
        scales = sorted(scales_of.get(f.mantissa, ()))
        if scales and f.scale not in scales:
            shown = f.label if f.label != f.mantissa else f"{f.mantissa} {f.scale}"
            rescaled.append(f"'{shown}' where the cited sources state {f.mantissa} {' or '.join(scales)} (a changed scale word)")
    out.rescaled = sorted(set(rescaled))
    return out


#: A row of bits written as one numeral ("010", "1101"): two to sixteen digits, each 0 or 1.
_BITS_RE = re.compile(r"-?[01]{2,16}")


def _bits_in_cells(written: str, source_texts: Sequence[str]) -> bool:
    """Whether ``written`` is a row of bits (:data:`_BITS_RE`) that a source states cell by cell, in order, on one line:
    its digits as single-digit cells of a table, between bars or tabs ("| 0 | 1 | 0 |"; repair round 4,
    rerun-combinator-faults-7 variant: a correct truth table synthesized as rows "000 → ..." was charged INT-LEDGER-023 for
    rows its source table writes in separate columns). The bits are compared as written, so "011" is no restatement of a
    row "1 1 0", and a list in prose ("1, 1, 0") is no row of a table."""
    if not _BITS_RE.fullmatch(written or ""):
        return False
    bits = written.lstrip("-")
    sep = r"[ ]*[|\t][ ]*"
    pattern = re.compile(r"(?<![\w.])" + sep.join(bits) + r"(?![\w.])")
    return any(pattern.search(t) for t in source_texts if t and len(t) <= 400_000)


def _figure_differences(synthesized_text: str, source_texts: list[str]) -> tuple[list[str], list[str], list[str]]:
    """``(introduced, dropped, rescaled)`` of :func:`figure_changes`: the synthesized claim's figures whose value occurs
    in no source under any spelling, precision or commensurable unit, the sources' figures the claim does not carry,
    and the claim's figures whose scale word differs from every scale the sources state that numeral with ("6.1
    billion" where the sources say "6.1 million"; a numeral the sources state without a scale word is not held to one,
    since "from 1.9 to 6.1 million" elides the first figure's scale)."""
    changes = figure_changes(synthesized_text, source_texts)
    return changes.introduced, changes.dropped, changes.rescaled


def _sorted_tokens(tokens: set[str]) -> list[str]:
    return sorted(tokens, key=lambda s: (len(s), s))


# --- who a synthesized claim credits (INT-LEDGER-025 misattribution, INT-LEDGER-026 view credit) -----------------------
#: The author of a request text in scope: the router wrote the request, so its words quoted as the poem's are misattributed.
REQUEST_AUTHOR = "router"


def _credit_documents(reports: list[SpecialistReport], request_texts: tuple[str, ...] | list[str] = ()) -> dict[str, "SuppliedText"]:
    """The texts a synthesized quotation may be credited to: every supplied text of the reports in scope (first text per
    document id), per report its response as a document whose author is the reporting agent ("the English specialist"
    names it), so a specialist's prose quoted as a supplied text's words is told apart from that text, and every request
    text that is not already one of those (the router's own words: a request's wording quoted as the poem's or its
    author's is misattributed too, ``request:<n>``)."""
    from ..translate.contracts import SuppliedText
    docs: dict[str, SuppliedText] = {}
    for r in reports:
        for t in r.supplied_texts:
            docs.setdefault(t.document_id, t)
    for r in reports:
        if r.original_response.strip():
            docs.setdefault(f"report:{r.report_id}", SuppliedText(document_id=f"report:{r.report_id}", title=None, author=r.agent_id, text=r.original_response))
    known = {d.text for d in docs.values()}
    for i, t in enumerate(dict.fromkeys(x for x in request_texts if x and x.strip() and x not in known), start=1):
        docs.setdefault(f"request:{i}", SuppliedText(document_id=f"request:{i}", title=None, author=REQUEST_AUTHOR, text=t))
    return docs


def _doc_label(doc_id: str, doc) -> str:
    if doc_id.startswith("report:"):
        return f"the {doc.author} report {doc_id[len('report:'):]}"
    if doc_id.startswith("request:"):
        return f"the router's request ({doc_id})"
    who = ", ".join(x for x in (doc.author, doc.title) if x)
    return f"{doc_id} ({who})" if who else doc_id


def misattributed_quotations(text: str, docs: dict, *, skip: set[str] = frozenset()) -> list[str]:
    """Descriptions of the quotations of ``text`` that its sentence credits (:func:`~epinoic_logic.adapters.sources.quotation_credit`:
    a possessive or a crediting verb after a named author, title, specialist or "the poem") to a text that does not hold
    them while another text of ``docs`` does: a specialist's prose presented as the poem's words, the poem's words
    presented as a colleague's. Quotations in ``skip`` (already reported as found nowhere) are not read."""
    from ..adapters.markdown import cited_quotation_spans
    from ..adapters.sources import quotation_credit
    if not docs:
        return []

    def holds(q: str, doc) -> bool:
        return _holds_quotation(q, doc.text)

    out: list[str] = []
    for start, _end, inner in cited_quotation_spans(text):
        q = inner.strip().strip(".,;:!?").strip()
        if not q or q in skip or not re.search(r"[^\W\d_]", q):
            continue
        credit = quotation_credit(text, start, docs)
        if credit is None or credit.document_id is None or credit.document_id not in docs:
            continue
        if holds(q, docs[credit.document_id]):
            continue
        located = [d for d, doc in docs.items() if d != credit.document_id and holds(q, doc)]
        # A request's words count as a holder only for a quotation of three words or more that is no title of a text in
        # scope (a request names the poem it asks about; quoting the title is no misattribution).
        if located and all(d.startswith("request:") for d in located) and (len(q.split()) < 3 or _is_title(q, docs)):
            continue
        if not located:
            continue
        out.append(f"'{q[:80]}' is credited to {credit.phrase!r} ({_doc_label(credit.document_id, docs[credit.document_id])}) but occurs only in "
                   + ", ".join(_doc_label(d, docs[d]) for d in located[:4]))
    return list(dict.fromkeys(out))


def _is_title(q: str, docs: dict) -> bool:
    low = " ".join(q.split()).casefold()
    return any(doc.title and low in " ".join(doc.title.split()).casefold() for doc in docs.values())


def _view_credit(text: str, known: list[ClaimRecord], agents: list[str]) -> list[str]:
    """A synthesized claim that credits a view to a specialist (named with a possessive or as the subject of a crediting
    verb: "The English specialist dates the war ...") while none of its cited source claims holds that specialist's view:
    a source claim holds its own agent's view and the views it credits to a colleague itself, except a 'perspective'
    claim, which holds only the view of the specialist it names ("The English specialist's paragraph identifies ..." in
    the History report)."""
    from ..adapters.sources import credited_agents
    if len(agents) < 1:
        return []
    credited = credited_agents(text, agents)
    if not credited:
        return []
    holders: set[str] = set()
    for c in known:
        named = credited_agents(c.claim_text, agents)
        if c.claim_role == "perspective":
            holders |= set(named) if named else {c.agent_id}
        else:  # its own agent's view, and any colleague's view it reports itself ("bearing out the English specialist's claim")
            holders |= {c.agent_id, *named}
    if set(credited) & holders:
        return []
    return [f"it credits the view to {credited} but its cited source claims {[c.claim_id for c in known]} state the view of {sorted(holders)} (a view credited to another agent)"]


#: A from-memory label or qualification in a text.
_MEMORY_LABEL_RE = re.compile(r"\bfrom memory\b|\bmemory\b|\b(?:check|verify)\b[^.;]{0,40}\bnotes?\b|\bunverified\b|\bnot (?:been )?(?:verified|checked)\b|\bto be (?:checked|verified)\b", re.IGNORECASE)
_MEMORY_PAREN_RE = re.compile(r"\(([^()]*\bmemory\b[^()]*)\)", re.IGNORECASE)


def _dropped_memory_labels(text: str, known: list[ClaimRecord], report_labelled: set[str]) -> Optional[tuple[list[str], list[str], list[str]]]:
    """``(items, source ids, labels)`` when ``text`` states dated or quantified items of cited source claims labelled
    from memory (the label in the claim's text or assumptions, or a note of its report that labels every date and figure)
    and carries no from-memory label of its own; None otherwise."""
    if _MEMORY_LABEL_RE.search(text):
        return None
    syn_keys = set().union(*(f.keys for f in _figures(text))) if text else set()
    items: set[str] = set()
    ids: list[str] = []
    labels: list[str] = []
    for c in known:
        if c.claim_role == "other":
            continue
        own = _MEMORY_LABEL_RE.search(c.claim_text) or any(_MEMORY_LABEL_RE.search(a) for a in c.assumptions)
        if not own and c.claim_id not in report_labelled:
            continue
        carried = {f.label for f in _figures(c.claim_text) if f.keys & syn_keys}
        if not carried:
            continue
        items |= carried
        ids.append(c.claim_id)
        m = _MEMORY_PAREN_RE.search(c.claim_text)
        labels.append(f"'{m.group(1).strip()}'" if m else ("'from memory'" if own else "a note of its report labels its dates and figures from memory"))
    if not ids:
        return None
    return _sorted_tokens(items), ids, list(dict.fromkeys(labels))


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


#: Sentence ends for the self-report reading of a synthesis: a sentence stop followed by space, or a line break.
_SELF_REPORT_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
#: The longest sentence the self-report reading reads (a sentence beyond it is read on its first characters only).
_SELF_REPORT_SENTENCE_CHARS = 4000


#: What runs the checks, as the subject of a check-status statement: the verification infrastructure (Z3, the engine,
#: solver, verifier, checker, the hub, channel, router, translator, Overseer) or the checks of a report, an answer or a
#: specialist ("the Mathematics report's own checks", "its own checks", "the formal checks"). Checks of anything else
#: ("border checks", "the safety checks") are subject matter, not the process.
_CHECK_SUBJECT = (r"(?:\bz3\b|\b(?:the\s+)?(?:(?:verification|logic|formal|z3|translation|integrity)\s+)?(?:engine|solver|verifier|checker)\b"
                  r"|\bthe\s+(?:hub|channel|translator|overseer|router)\b(?:\s*['’]s\s+(?:own\s+)?checks?\b)?"
                  r"|\b(?:its|their|my|our)\s+own\s+(?:formal\s+|automated\s+)?checks?\b"
                  r"|\bthe\s+[\w-]+(?:\s+(?:report|specialist|answer|working|paragraph))?\s*['’]s?\s+(?:own\s+)?(?:formal\s+|automated\s+)?checks?\b"
                  r"|\bthe\s+(?:formal|automated|verification|integrity)\s+checks?\b)")
#: A check status stated in a synthesis, in either polarity (repair round 1, re-run review cf-3 variant): the checks of the
#: process or of a report as the subject of a verb that reports a check's outcome on the answer's items ("the Mathematics
#: report's own checks flag its written lines ... as not holding", "the engine found that the second line does not hold",
#: "the hub's checks show every figure holds"). A combinator cannot vouch for a check result; only the receipts carry
#: them, so the statement is a self-report like a self-certification.
_CHECK_STATUS_RE = re.compile(
    rf"{_CHECK_SUBJECT}\s+(?:(?:have|has|had)\s+)?(?:flag(?:s|ged)?|mark(?:s|ed)?)\b[^\n]{{0,240}}?\bas\s+(?:not\s+holding|false|wrong|incorrect|"
    r"failing|failed|holding|true|correct|valid)\b"
    rf"|{_CHECK_SUBJECT}\s+(?:(?:have|has|had)\s+)?(?:show(?:s|ed|n)?|finds?|found|report(?:s|ed)?|confirm(?:s|ed)?|reject(?:s|ed)?|refute(?:s|d)?)\b"
    r"[^\n]{0,240}?\b(?:do(?:es)?\s+not\s+hold|does\s+hold|holds|is\s+false|are\s+false|is\s+wrong|are\s+wrong|fails|failed)\b",
    re.IGNORECASE)


def _self_report_sentences(text: str) -> list[str]:
    """The sentences of ``text`` that state a verification status of the answer itself ("VERIFIED: all claims checked and
    confirmed.", "checked by the formal verifier: every line holds", "All checks passed."), read with the closed
    self-certification vocabulary of the specialists' reports
    (:func:`~epinoic_logic.adapters.markdown.is_self_certification`), and those that state a check's result in either
    polarity (:data:`_CHECK_STATUS_RE`: "the Mathematics report's own checks flag its written lines ... as not holding").
    One linear split."""
    from ..adapters.markdown import is_self_certification, is_word_count_line
    out: list[str] = []
    for sentence in _SELF_REPORT_SENTENCE_RE.split(text or ""):
        s = sentence.strip()
        if s and is_word_count_line(s):
            continue  # a word count is a length the channel measures, no verification status (repair round 5, ADV5-12)
        if s and (is_self_certification(s[:_SELF_REPORT_SENTENCE_CHARS]) or _CHECK_STATUS_RE.search(s[:_SELF_REPORT_SENTENCE_CHARS])):
            out.append(s[:200])
    return list(dict.fromkeys(out))


def _self_report_findings(synthesis: Synthesis) -> list[IntegrityFinding]:
    """INT-LEDGER-029: a synthesized claim, or a sentence of the student-facing text, that states a verification status of
    the answer: a self-report of the combinator (or one it carried from a specialist's note), advisory only. No check in
    this process stands behind it, so it is never material content and never evidence that anything was checked (a
    specialist's report with the same sentence is named CORE-SELF-001). Each sentence is named once."""
    f: list[IntegrityFinding] = []
    named: set[str] = set()
    for sc in synthesis.claims:
        found = _self_report_sentences(sc.text)
        if found:
            named.update(found)
            f.append(IntegrityFinding(code="INT-LEDGER-029", severity="warning", message=(
                f"synthesized claim ('{sc.transformation}', {sc.materiality}) states a verification status of the answer: {found[:3]}: a self-report, "
                "advisory only; no check in this process stands behind it, so it is no material content and no evidence of a check"),
                claim_ids=[sc.claim_id] + list(sc.source_claim_ids)[:16], agent_ids=[synthesis.combinator_agent_id]))
    rest = [s for s in _self_report_sentences(synthesis.text) if s not in named and not any(s in n or n in s for n in named)]
    if rest:
        f.append(IntegrityFinding(code="INT-LEDGER-029", severity="warning", message=(
            f"the synthesis text states a verification status of the answer: {rest[:3]}: a self-report, advisory only; no check in this "
            "process stands behind it"), claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id]))
    return f


def _reference_findings(sc, known: list[ClaimRecord], reports: list[SpecialistReport], combinator: str) -> list[IntegrityFinding]:
    """The evidence references of a synthesized claim checked against the documents they name:

    * INT-LEDGER-025 (error): an excerpt that the named supplied text does not hold in any recognised form
      (:func:`_holds_quotation`): an invented excerpt, or a misattributed one when another supplied text holds it;
    * INT-LEDGER-030 (warning): a reference to a document that no report supplies and no source claim cites, so nothing
      in scope can check it.

    A document known only from the source claims' references (no text supplied) is not read further: its excerpt is
    compared with the sources' by INT-LEDGER-020."""
    texts: dict[str, object] = {}
    for r in reports:
        for t in r.supplied_texts:
            texts.setdefault(t.document_id, t)
    cited = {ref.document_id for r in reports for c in r.claims for ref in c.source_refs}
    carried = {(ref.document_id, _norm(ref.excerpt)) for c in known for ref in c.source_refs if ref.excerpt}
    out: list[IntegrityFinding] = []
    unknown: list[str] = []
    for ref in sc.evidence_refs:
        doc = texts.get(ref.document_id)
        if doc is None:
            if ref.document_id not in cited:
                unknown.append(ref.document_id)
            continue
        excerpt = (ref.excerpt or "").strip().strip(".,;:!?").strip()
        if not excerpt or not re.search(r"[^\W_]", excerpt) or _holds_quotation(excerpt, doc.text):  # type: ignore[attr-defined]
            continue
        elsewhere = sorted(d for d, t in texts.items() if d != ref.document_id and _holds_quotation(excerpt, t.text))  # type: ignore[attr-defined]
        how = (f"misattributed: the words are in {elsewhere[:4]}, not in {ref.document_id}" if elsewhere
               else "an invented or altered excerpt: no supplied text holds it")
        source_note = " (as a cited source claim's reference also states it)" if (ref.document_id, _norm(ref.excerpt or "")) in carried else ""
        out.append(IntegrityFinding(code="INT-LEDGER-025", severity="error", message=(
            f"synthesized claim ('{sc.transformation}') credits to {ref.document_id} the excerpt {excerpt[:120]!r}, which that document does not "
            f"hold{source_note}: {how}"), claim_ids=[sc.claim_id] + [c.claim_id for c in known][:16], agent_ids=[combinator],
            document_ids=sorted({ref.document_id, *elsewhere[:4]})))
    if unknown:
        docs = sorted(set(unknown))
        out.append(IntegrityFinding(code="INT-LEDGER-030", severity="warning", message=(
            f"synthesized claim ('{sc.transformation}') references document(s) {docs[:8]} that no report supplies and no source claim cites: "
            "nothing in scope can check them, so the references are the combinator's own"), claim_ids=[sc.claim_id], agent_ids=[combinator],
            document_ids=docs[:16]))
    return out


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
    # Figures a source's content keeps in the synthesis: those of every synthesized claim that cites it (a source split
    # across two synthesized claims loses no figure the other one carries). A source figure is carried by a synthesized
    # figure that spells it, states its value to other significant figures (a precision change, reported as one) or
    # states its quantity in a commensurable unit (:func:`_carries`).
    carried_by_source: dict[str, list[_Figure]] = {}
    labels_by_source: dict[str, set[tuple[str, int]]] = {}  # the step labels the claims citing a source state (any notation)
    for sc in synthesis.claims:
        figs = _figures(sc.text) if sc.text else []
        labels = step_labels(sc.text) if sc.text else set()
        for cid in sc.source_claim_ids:
            carried_by_source.setdefault(cid, []).extend(figs)
            labels_by_source.setdefault(cid, set()).update(labels)
    carried_index = {cid: _FigureIndex(figs) for cid, figs in carried_by_source.items()}
    no_figures = _FigureIndex([])
    credit_docs = _credit_documents(reports, tuple(extra_texts))
    agents = sorted({r.agent_id for r in reports})
    memory_reports = {r.report_id for r in reports if any(c.claim_role == "other" and _MEMORY_LABEL_RE.search(c.claim_text) for c in r.claims)}

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
        # A source excerpt is preserved when it is among the synthesized claim's excerpts under the same (document, locator):
        # one table cited twice with no locator ("2022: 6.4%", "2023: 3.9%") holds two excerpts under one key, and comparing
        # the source's excerpt with only one of them read a faithful copy as an altered one.
        excerpts_at: dict[tuple[str, Optional[str]], set[str]] = {}
        for r in sc.evidence_refs:
            if r.excerpt and _norm(r.excerpt):
                excerpts_at.setdefault((r.document_id, r.locator), set()).add(_norm(r.excerpt))
        altered = sorted({c.claim_id for c in known for r in c.source_refs
                          if r.excerpt and excerpts_at.get((r.document_id, r.locator)) and _norm(r.excerpt) not in excerpts_at[(r.document_id, r.locator)]})
        f += _reference_findings(sc, known, reports, synthesis.combinator_agent_id)
        if altered:
            f.append(IntegrityFinding(code="INT-LEDGER-020", severity="warning", message=f"evidence excerpt differs from the source's under the same (document, locator) for source claims {altered}", claim_ids=[sc.claim_id] + altered, document_ids=sorted({r.document_id for c in known if c.claim_id in altered for r in c.source_refs})))
        changes = figure_changes(sc.text, [c.claim_text for c in known])
        introduced, rescaled = changes.introduced, changes.rescaled
        dropped_figures = _sorted_tokens({f.label for c in known for f in _figures(_masked_step_labels(c.claim_text, labels_by_source.get(c.claim_id, set())))
                                          if not carried_index.get(c.claim_id, no_figures).carries(f) and f.label not in incidental_figures(c.claim_text)})
        repaired = figure_pairing_differences(sc.text, [c.claim_text for c in known])
        word_counts, _meaning = aligned_differences(sc.text, [c.claim_text for c in known])
        if introduced or rescaled or repaired or word_counts or changes.reprecised or changes.reunited:
            # One finding per synthesized claim: the figures no source states, the figures stated with another scale word,
            # another precision or another unit, and the figures every source states but with another event (a swap
            # passes a token-set comparison, so the pairing is compared too). Figures written in words count like figures
            # in digits. A change of form only (another notation, a commensurable unit) is none of these.
            parts: list[str] = []
            if introduced:
                parts.append(f"states figures or dates {introduced} that occur in none of its cited sources {known_ids}: a changed or introduced figure or date")
            if rescaled:
                parts.append(f"changes the scale of figures of its cited sources {known_ids}: " + "; ".join(rescaled))
            if changes.reprecised:
                parts.append(f"changes the precision (significant figures) of figures of its cited sources {known_ids}: " + "; ".join(changes.reprecised))
            if changes.reunited:
                parts.append(f"changes the unit of figures of its cited sources {known_ids}: " + "; ".join(changes.reunited))
            if repaired:
                parts.append(f"re-pairs figures or dates between events relative to its cited sources {known_ids}: " + "; ".join(repaired))
            if word_counts:
                parts.append(f"changes a count or a date of a statement it copies from its cited sources {known_ids}: " + "; ".join(word_counts))
            f.append(IntegrityFinding(code="INT-LEDGER-023", severity="error", message=f"synthesized claim ('{sc.transformation}') " + ", and ".join(parts) + ", whatever the transformation label", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        corpus = _quotation_corpus(reports, known, tuple(extra_texts))
        invented = unlocated_quotations(sc.text, corpus)
        misspelt = quotation_form_differences(sc.text, corpus)
        if misspelt:
            f.append(IntegrityFinding(code="INT-LEDGER-028", severity="warning", message=f"synthesized claim ('{sc.transformation}') quotes {misspelt[:8]}: the words occur in a text in scope, but with other diacritics, so the quotation is not reproduced exactly", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        if invented:
            f.append(IntegrityFinding(code="INT-LEDGER-025", severity="error", message=f"synthesized claim ('{sc.transformation}') quotes {[q[:80] for q in invented[:8]]}, which occur in none of the supplied texts, the cited reports or its cited source claims {known_ids}: an altered or invented quotation", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        miscredited = misattributed_quotations(sc.text, credit_docs, skip=set(invented))
        if miscredited:
            f.append(IntegrityFinding(code="INT-LEDGER-025", severity="error", message=f"synthesized claim ('{sc.transformation}') credits quotations to a source that does not hold them: " + "; ".join(miscredited[:8]) + " (misattributed: the words are genuine, the credit is not)",
                                      claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id], document_ids=sorted({d for d in credit_docs if any(d in m for m in miscredited)})))
        changed_meaning = meaning_differences(sc.text, [c.claim_text for c in known], sc.transformation)
        changed_meaning += _view_credit(sc.text, known, agents)
        if changed_meaning:
            f.append(IntegrityFinding(code="INT-LEDGER-026", severity="warning", message=f"synthesized claim ('{sc.transformation}') may say something other than its cited sources {known_ids}: " + "; ".join(changed_meaning) + " (lexical comparison; not formally checked)", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        if dropped_figures and (sc.transformation in _EQUIVALENCE_LABELS or sc.transformation in _COMBINING_LABELS):
            how = "content was dropped under an equivalence label" if sc.transformation in _EQUIVALENCE_LABELS else "the dated or quantified content of those sources was left out of the combined claim"
            f.append(IntegrityFinding(code="INT-LEDGER-024", severity="warning", message=f"figures or dates {dropped_figures} of the cited sources {known_ids} do not appear in the '{sc.transformation}' synthesized claim or in any other synthesized claim citing those sources; {how}", claim_ids=[sc.claim_id] + known_ids, agent_ids=[synthesis.combinator_agent_id]))
        unlabelled = _dropped_memory_labels(sc.text, known, {c.claim_id for c in known if report_of.get(c.claim_id) in memory_reports})
        if unlabelled:
            items, labelled_ids, labels = unlabelled
            f.append(IntegrityFinding(code="INT-LEDGER-027", severity="warning", message=f"synthesized claim ('{sc.transformation}') states dated or quantified items {items} of source claims {labelled_ids} that the specialist labelled from memory ({labels}), without the label: the qualification was dropped, so the router reads those items as unqualified",
                                      claim_ids=[sc.claim_id] + labelled_ids, agent_ids=[synthesis.combinator_agent_id]))
        if sc.transformation == "carried":
            if len(known) != 1 or len(sc.source_claim_ids) != 1:
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message=f"claim marked 'carried' cites {len(sc.source_claim_ids)} sources; 'carried' requires exactly one source with identical text, use 'merged'", claim_ids=[sc.claim_id] + known_ids))
            elif _norm(_QUOTE_MARKS_RE.sub('"', known[0].claim_text)) != _norm(_QUOTE_MARKS_RE.sub('"', sc.text)):  # the style of its quotation marks is no change
                f.append(IntegrityFinding(code="INT-LEDGER-010", severity="warning", message="claim marked 'carried' but its text differs from the source; record it as 'paraphrased' or a new linked claim", claim_ids=[sc.claim_id, known[0].claim_id]))
        if material_sources and sc.materiality == "supporting":
            f.append(IntegrityFinding(code="INT-LEDGER-021", severity="warning", message=f"material source claims {[c.claim_id for c in material_sources]} became a 'supporting' synthesized claim: materiality downgraded", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))
        if material_sources and sc.transformation in ("merged", "generalized", "narrowed"):
            what = "content removed; formal coverage check required" if sc.transformation == "narrowed" else "formal synthesis-entailment check required"
            f.append(IntegrityFinding(code="INT-LEDGER-011", severity="info", message=f"material content produced by '{sc.transformation}' from {[c.claim_id for c in material_sources]}: {what}", claim_ids=[sc.claim_id] + [c.claim_id for c in material_sources]))

    f += _self_report_findings(synthesis)
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
