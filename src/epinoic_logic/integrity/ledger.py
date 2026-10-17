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
    return _words_as_digits(_THOUSANDS_RE.sub("", text))


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
    if tok.isdecimal() and 1 <= int(tok) <= 31:  # a superscript '¹⁹' is a digit to isdigit() but neither decimal nor a day
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


def _align_tokens(text: str) -> list[tuple[str, str]]:
    """``(key, surface)`` per token of ``text``: words light-stemmed and case-folded, numerals as written (thousands
    separators removed), decades as "1840s", and the canonical phrases (:data:`_CANON_PHRASES`) as one token."""
    plain = _DECADE_RE.sub(lambda m: m.group(1) + "s", _THOUSANDS_RE.sub("", _PARENTHETICAL_RE.sub(" ", fold_exponent_marks(text))))
    for rx, canon, _shown in _CANON_PHRASES:
        plain = rx.sub(canon, plain)
    out: list[tuple[str, str]] = []
    for m in _ALIGN_TOKEN_RE.finditer(plain):
        w = m.group(0)
        low = w.casefold()
        out.append((low if low[:1].isdecimal() or low in _CANON_SHOWN else _akey(low), _CANON_SHOWN.get(low, w)))
    return out


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


def aligned_changes(synthesized_text: str, source_text: str) -> tuple[list[str], list[str]]:
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
    figures, meaning = _aligned_ops(syn, src, src_numerals)
    src_sentences = [t for t in (_align_tokens(x) for x in _ALIGN_SENTENCE_RE.split(source_text)) if len(t) >= 4]
    syn_sentences = [t for t in (_align_tokens(x) for x in _ALIGN_SENTENCE_RE.split(synthesized_text)) if len(t) >= 4]
    if src_sentences and syn_sentences:
        for st in src_sentences:
            content = {k for k, w in st if w.isalpha() and k not in _ALIGN_STOP and w.casefold() not in _ALIGN_STOP}
            for yt in syn_sentences:
                shared = content & {k for k, _w in yt}
                if not content or len(shared) * 2 < len(content):
                    continue
                f2, m2 = _aligned_ops(yt, st, src_numerals, anchored=True)
                figures += f2
                meaning += m2
    return list(dict.fromkeys(figures)), list(dict.fromkeys(meaning))


#: Sentence ends for the anchored alignment: a full stop, question or exclamation mark, a semicolon, a line break.
_ALIGN_SENTENCE_RE = re.compile(r"(?<=[.!?;])\s+|\n+")


def _aligned_ops(syn: list[tuple[str, str]], src: list[tuple[str, str]], src_numerals: set[str], *, anchored: bool = False) -> tuple[list[str], list[str]]:
    """The changes :func:`aligned_changes` reads between two token lists. With ``anchored`` (two sentences), the start and
    the end of the source sentence count as one copied word each."""
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
                elif ka in src_numerals:  # a figure the source states elsewhere, put in place of the one it states here
                    figures.append(f"'{here}' where its cited sources state '{there}': '{sa}' is a figure they state elsewhere, put in place of '{sb}'")
                continue
            if sa.casefold() in _MONTH_KEYS and sb.casefold() in _MONTH_KEYS and sa.casefold() != sb.casefold():
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
    """:func:`aligned_changes` against every cited source text, and :func:`day_month_differences` against all of them,
    deduplicated."""
    figures: list[str] = []
    meaning: list[str] = []
    for t in source_texts:
        f, m = aligned_changes(synthesized_text, t)
        figures += f
        meaning += m
    figures += day_month_differences(synthesized_text, source_texts)
    return list(dict.fromkeys(figures)), list(dict.fromkeys(meaning))


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
    approx = {m.group(1) for t in source_texts for m in _APPROX_RE.finditer(_words_as_digits(_THOUSANDS_RE.sub("", t)))}
    syn_plain = _THOUSANDS_RE.sub("", synthesized_text)
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
    plain = _THOUSANDS_RE.sub("", text)
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
    from ..adapters.markdown import find_quotation_spans
    out: list[str] = []
    for _s, _e, inner in find_quotation_spans(text):
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
    from ..adapters.markdown import find_quotation_spans
    from ..translate.grounding import locate_quotation, locate_quotation_inexact
    out: list[str] = []
    for _s, _e, inner in find_quotation_spans(text):
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
        tok = m.group(0)
        if tok.endswith("s"):  # a decade ("1840s", "1840's"): one date, never scaled
            tok = tok.replace("'", "").replace("’", "")
            out.append(_Figure(tok, None, tok))
            continue
        sc = _SCALE_AFTER_RE.match(masked, m.end())
        out.append(_Figure(tok, sc.group(1).casefold() if sc else None, tok))
    out += [_Figure(f"{m.group(1).casefold()} {m.group(2)}", None, f"{m.group(1).casefold()} {m.group(2)}") for m in _MONTH_YEAR_RE.finditer(plain)]
    return out


def figure_spellings(text: str, *, with_scale: bool = False) -> list[tuple[str, frozenset[str]]]:
    """``(label, spellings)`` for every figure and date of ``text`` (digits, words, scale words, month-years): two figures
    are the same when their spellings meet ("a million", "1 million" and "1,000,000"). With ``with_scale`` a numeral's
    label carries its scale word ("2.5 million"), as a finding should name it."""
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
    plain = _THOUSANDS_RE.sub("", text)
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
    # A source in another language states its figures in its own words ("doce vecinos"): a faithful "twelve" is no
    # introduced figure.
    foreign = set().union(*(foreign_number_values(t) for t in source_texts)) if source_texts else set()
    introduced = _sorted_tokens({f.label for f in syn if not (f.keys & (src_keys | foreign))})
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
    from ..adapters.markdown import find_quotation_spans
    from ..adapters.sources import quotation_credit
    if not docs:
        return []

    def holds(q: str, doc) -> bool:
        return _holds_quotation(q, doc.text)

    out: list[str] = []
    for start, _end, inner in find_quotation_spans(text):
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


def _self_report_sentences(text: str, labels: Optional[list[str]] = None) -> list[str]:
    """The sentences of ``text`` that state a verification status of the answer itself ("VERIFIED: all claims checked and
    confirmed.", "checked by the formal verifier: every line holds"), read with the closed self-certification vocabulary
    of the specialists' reports (:func:`~epinoic_logic.adapters.markdown.is_self_certification`), or that carry a
    verification label on their content ("Verified: ...", "... (verified).", "..., as formally verified.";
    :func:`~epinoic_logic.adapters.markdown.verification_label`), which are also appended to ``labels``. One linear split."""
    from ..adapters.markdown import is_self_certification, verification_label
    out: list[str] = []
    for sentence in _SELF_REPORT_SENTENCE_RE.split(text or ""):
        s = sentence.strip()
        if not s:
            continue
        if is_self_certification(s[:_SELF_REPORT_SENTENCE_CHARS]):
            out.append(s[:200])
        elif verification_label(s[:_SELF_REPORT_SENTENCE_CHARS]) is not None:
            out.append(s[:200])
            if labels is not None:
                labels.append(s[:200])
    return list(dict.fromkeys(out))


def _self_report_findings(synthesis: Synthesis) -> list[IntegrityFinding]:
    """INT-LEDGER-029: a synthesized claim, or a sentence of the student-facing text, that states a verification status of
    the answer: a self-report of the combinator (or one it carried from a specialist's note), advisory only. No check in
    this process stands behind it, so it is never material content and never evidence that anything was checked (a
    specialist's report with the same sentence is named CORE-SELF-001). A verification label on the content of a claim
    ("Verified: ...", "... (verified).", "..., as formally verified.") is named the same way: the label is the
    self-report, and the content stays accounted for like any other claim's. Each sentence is named once."""
    f: list[IntegrityFinding] = []
    named: set[str] = set()
    for sc in synthesis.claims:
        labels: list[str] = []
        found = _self_report_sentences(sc.text, labels)
        if found:
            named.update(found)
            what = (f"synthesized claim ('{sc.transformation}', {sc.materiality}) carries a verification-status label on its content: {found[:3]}: the "
                    "label is a self-report, advisory only; no check in this process stands behind it, so it is no evidence that the claim was "
                    "checked (its content is still accounted for like any other claim's)") if set(found) <= set(labels) else (
                    f"synthesized claim ('{sc.transformation}', {sc.materiality}) states a verification status of the answer: {found[:3]}: a self-report, "
                    "advisory only; no check in this process stands behind it, so it is no material content and no evidence of a check")
            f.append(IntegrityFinding(code="INT-LEDGER-029", severity="warning", message=what,
                                      claim_ids=[sc.claim_id] + list(sc.source_claim_ids)[:16], agent_ids=[synthesis.combinator_agent_id]))
    rest = [s for s in _self_report_sentences(synthesis.text) if s not in named and not any(s in n or n in s for n in named)]
    if rest:
        f.append(IntegrityFinding(code="INT-LEDGER-029", severity="warning", message=(
            f"the synthesis text states a verification status of the answer: {rest[:3]}: a self-report, advisory only; no check in this "
            "process stands behind it"), claim_ids=[synthesis.synthesis_id], agent_ids=[synthesis.combinator_agent_id]))
    return f


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
    # across two synthesized claims loses no figure the other one carries).
    carried_by_source: dict[str, set[str]] = {}
    for sc in synthesis.claims:
        keys = set().union(*(f.keys for f in _figures(sc.text))) if sc.text else set()
        for cid in sc.source_claim_ids:
            carried_by_source.setdefault(cid, set()).update(keys)
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
        altered = sorted({c.claim_id for c in known for r in c.source_refs if (r.document_id, r.locator) in have and r.excerpt and have[(r.document_id, r.locator)].excerpt and _norm(r.excerpt) != _norm(have[(r.document_id, r.locator)].excerpt)})
        if altered:
            f.append(IntegrityFinding(code="INT-LEDGER-020", severity="warning", message=f"evidence excerpt differs from the source's under the same (document, locator) for source claims {altered}", claim_ids=[sc.claim_id] + altered, document_ids=sorted({r.document_id for c in known if c.claim_id in altered for r in c.source_refs})))
        introduced, _dropped_here, rescaled = _figure_differences(sc.text, [c.claim_text for c in known])
        dropped_figures = _sorted_tokens({f.label for c in known for f in _figures(c.claim_text) if not (f.keys & carried_by_source.get(c.claim_id, set()))
                                          and f.label not in incidental_figures(c.claim_text)})
        repaired = figure_pairing_differences(sc.text, [c.claim_text for c in known])
        word_counts, _meaning = aligned_differences(sc.text, [c.claim_text for c in known])
        if introduced or rescaled or repaired or word_counts:
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
