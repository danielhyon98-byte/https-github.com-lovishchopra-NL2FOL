"""Deterministic extraction of a report's own quantitative statements and formal
self-consistency checks on them. No model is involved: regular expressions find
figures the specialist stated, and the engine decides whether the derived figures
the specialist also stated actually follow (percentage changes, percentage-point
differences, word fractions, fold changes, shares, totals). A specialist that writes
"rose from 1.4 million to 6 million, a threefold increase" is caught by arithmetic,
not by opinion.

Pairs of figures read inside one clause (``from 381 in September 1929 to about 41 in July
1932``; dated figures may carry a day, a month, ``early``/``late``, a year, a year range
such as ``1923-24``, or a circa before the year: ``by about 1700``, ``in c. 1700``):

* ``from X to Y`` (every one in the clause, not only the first), with a list after it
  (``to 3.1 million in 1930, 4.5 million in 1931 and 5.6 million in 1932``) and a chained
  continuation (``..., a rise of 63 per cent, before climbing to 5.6 million in 1932, a
  rise of 30 per cent``: the second change is read from 3.1 to 5.6 million);
* ``X in D1 and Y in D2`` with both dates stated (``stood at 1.9 million in 1929 and
  reached 5.6 million in 1932``, ``bought 4.2 marks in July 1914 and about 4.2 trillion
  marks in November 1923``);
* each derived figure binds to the pair of its own part of the clause: the parts are cut
  at ``, and`` / ``and`` / ``, while`` / ``, but`` between two pairs, so ``Output rose from
  100 in 1929 to 120 in 1930, a rise of 20 per cent, and exports rose from 50 in 1929 to 60
  in 1930, a rise of 50 per cent`` is two checks and the second fails;
* an optional noun phrase of up to three digit-free words after a figure's unit and
  before its date or ``to`` (``200 students in 1920``, ``800 million gold marks in
  1924``, ``6 per cent of members in September 1923``), and a rate phrase after it
  (``500,000 tons a year in 1700``, ``per annum``, ``each year``);
* shared-unit elision: when only the second figure carries a unit and the first carries
  neither a unit nor a noun (``from 15 to 45 million``, ``from 3.2 to 24.9 per cent``) the
  unit applies to both figures; a first figure with its own noun is read as written
  (``from about 4.2 marks in 1914 to about 4.2 trillion marks``: 4.2 marks, not 4.2
  trillion); a per-cent, rate or count unit on the first figure alone applies to the second
  too (``from 37.3 per cent to 33.1``);
* units: scales (thousand, million, billion, trillion, quadrillion and their
  abbreviations), per cent, rates (``per thousand``, ``per 100,000``, ``per head``,
  ``to the dollar``), seats and votes. A pair whose units are of different kinds, or whose
  first figure carries a scale and whose second figure carries no recognised unit (``from 4
  billion to 4 lakh``), is NOT read as a bare number: no check is built and the derived
  figure is reported undecided;
* figures written in words (``from two hundred to two hundred and sixty students, an
  increase of forty-five per cent``) are read for numbers below a thousand, with a scale
  word as the unit (``six million``); a decimal comma (``1,9 million``: one or two digits
  after the comma) is a decimal point;
* derived figures: ``a fall of 50 per cent``, ``a rise of -10 per cent`` (a signed
  change reverses the stated direction), ``a change of 20 per cent`` (the direction is the
  figures' own; a sign is read as above), ``fell by a third``, ``a rise of 25 percentage
  points``, ``doubled``/``doubling``, ``halved``, ``threefold``, ``2.5-fold``,
  ``1,000-fold``, ``hundredfold``, ``thousandfold``, ``millionfold``, ``trillionfold``;
  a qualifier may stand before a fold with an article between (``more than a tripling``,
  ``nearly a doubling``, ``over a threefold rise``).

Relations stated across sentences: a derived figure whose clause states no pair (``The
annual average grew by roughly 60 per cent that year``), ``rose in each year (that
followed)`` and ``the greatest (proportional) rise of the period`` are read against the
paragraph's dated series (the year-dated figures of its pairs and lists, one series per
kind of unit; a month-dated peak is not an annual figure). The year comes from the clause
(``from 1929 to 1930``, ``in 1930``) or, for ``that year``/``the same year``, from the
nearest earlier year the paragraph states; the change is read from the series' previous
year. The check's label names the sentence the figures came from. When the series is
missing, ambiguous (two series state the needed years) or the year cannot be read, the
statement is returned by :func:`undecided_quant_statements` with the reason, and the core
pack reports it as ``CORE-QNT-001``: no stated arithmetic is skipped silently.

Sentences are split with the shared abbreviation-aware splitter
(``adapters/history_specialist/sentences.py``), so ``c.``, ``approx.``, ``p.`` and
initials never end a statement and ``from c. 200 million tonnes in 1928 to c. 100
million in 1932`` is one statement.

Tolerance rule (:data:`TOLERANCE_RULE`): the stated derived figure must lie within
``tolerance`` (default 5 per cent) of the value computed from the report's own figures.
The band is symmetric around the COMPUTED value, not around the stated one, so a
specialist who understates a change does not earn a wider band than one who overstates
it. Per-cent and percentage-point figures also pass when within 0.5 points of the
computed value (rounding to the nearest whole per cent is never a finding). ``more
than``/``over`` before a stated change makes the check one-sided (a lower bound only),
``under``/``less than`` an upper bound only. The rule is repeated in every check's
``rule`` field so the receipt says how the figure was judged.

Readings (``reading``, keyword-only on :func:`extract_quant_checks` and
:func:`undecided_quant_statements`; part of the cache key). :data:`GENERAL`, the default, is
the reading described above, byte for byte; every non-STEM branch uses it.
:data:`~epinoic_logic.stem.si_reading.SI_READING` (the STEM branches, through
``CorePack(reading=SI_READING)``) reads the same relations with these differences
(docs/STEM_DESIGN.md, section 12):

* only spelled-out scale words scale a figure; ``m``, ``k``, ``K``, ``M``, ``A`` and ``g`` are
  units, so ``from 500 mm to 2 m, a fourfold increase`` and ``300 K`` read as written;
* a unit symbol after a figure is read through the STEM unit table into an exact SI value:
  ``from 500 g to 1.0 kg`` is a doubling and ``from 2 kg to 500 g`` a fall of 75 per cent;
  figures of different dimensions, and a relative change on an offset temperature scale (°C,
  °F), are not paired and the derived figure is reported undecided with the reason;
* figures may be written in scientific notation (``1.5e-6 C``, ``6.67 × 10⁻¹¹``) and carry a
  sign (``-4.0 m/s``; U+2212 is read as a minus); a relative change is taken against the
  magnitude of the earlier figure, so a rise from -4.0 to -2.0 is a rise of 50 per cent;
* repeated folds are read: ``halved twice`` is a factor of 1/4, ``doubled three times`` 8;
* the band is sign-aware, ``|C - S| <= tolerance * |C| + floor``, encoded with ``ite`` (a
  stated figure of 0 is decided by the same inequality);
* the text read is the SI quant view: relation-bearing maths (LaTeX, math runs, verbal
  arithmetic, chemistry, code) is masked, so this extractor reads only prose relations and the
  STEM pack only the maths; sentences are the STEM segmenter's statements, so a CORE-QNT-001
  finding's paragraph and sentence numbers are the STEM claim's ``s<paragraph>.<n>``.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import NamedTuple, Optional

from ..adapters.history_specialist.sentences import split_clauses, split_sentences
from ..ir.schema import Problem
from ..stem.si_reading import (
    SI_READING, SI_SCALE_UNIT, SI_SCALES, QuantReading, si_digits_pattern, si_number, si_quant_view, si_statements, si_unit, si_unit_pattern,
)

#: The general reading: today's extractor, byte for byte (see the module docstring).
GENERAL = QuantReading(name="general")

_SMALL_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen")
_TENS_WORDS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_WORD_VALUES = {w: i for i, w in enumerate(_SMALL_WORDS, start=1)} | {w: 10 * (i + 2) for i, w in enumerate(_TENS_WORDS)}
_WNUM_TOKEN = "|".join(sorted((*_SMALL_WORDS, *_TENS_WORDS), key=len, reverse=True))  # longest first: 'sixty' before 'six'
#: A number in words below a thousand: 'forty-five', 'two hundred and sixty'. Scale words (thousand, million, ...) are units.
_WNUM = rf"(?:{_WNUM_TOKEN})(?:(?:[\s-]+and)?[\s-]+(?:{_WNUM_TOKEN}|hundred))*(?![a-z])"
#: Digits: thousands groups (with an optional decimal part), a plain decimal, or a decimal comma ('1,9': one or two digits after it).
_DIGITS = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\d+,\d{1,2}"
_NUM = rf"({_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"  # never split a thousands group or a decimal
_NUMX = rf"(?:{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
_AMOUNT = rf"([-+]?(?:{_DIGITS})|{_WNUM})(?!\d|,\d|\.\d)"  # a derived figure may carry a sign
_PCT_UNIT = r"(?:per cent|percent(?!age)|%)"  # 'percentage points' is a difference, not a per-cent unit
_RATE_UNIT = r"per (?:thousand|1,?000|10,?000|100,?000|million|head|capita)"
_SCALE_UNIT = r"quadrillion|trillion|billion|million|thousand|trn|tn|bn|m|k"
_UNIT = rf"(?:\s*({_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes)\b)?"
#: Every unit a figure of a pair may carry ('to the dollar' is an exchange rate).
_UNIT_WORDS = rf"(?:{_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes|to (?:the|one|a) (?:US |U\.S\. |American )?(?:dollar|pound)s?)"
_QUAL = (r"(?:just over|just under|more than|less than|at least|at most|up to|close to|an estimated|approximately|about|around|roughly|nearly|almost|"
         r"near|just|some|over|under|c\.|ca\.|circa|approx\.)")
_MONTH = r"(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?"
#: Words a noun phrase after a figure may not start with: the connectors and prepositions that end it.
_CONNECT = (r"(?:to|and|in|by|of|on|at|during|for|from|a|an|the|or|than|that|which|when|while|as|per|with|between|against|over|under|about|around|"
            r"roughly|nearly|almost|some|more|less|each|every|before|after|then|but|whereas|so|while|peaking|reaching|rising|falling)")
#: An optional digit-free noun phrase (up to three words) after a figure's unit: 'students', 'gold marks', 'of members'.
_NOUN = rf"(?:\s+(?:(?:of|among)\s+(?:the\s+|all\s+|its\s+|their\s+)?)?(?!{_CONNECT}\b)[a-z][a-z'’-]*(?:\s+(?!{_CONNECT}\b)[a-z][a-z'’-]*){{0,2}})?"
#: An optional rate phrase after the unit or noun: 'a year', 'per annum', 'each year', 'a head'.
_PER = r"(?:\s+(?:a|an|per|each|every)\s+(?:year|annum|head|month|week|day|capita|person|household)\b|\s+annually\b)?"
#: A date after a figure: 'in 1928', 'by early 1932', 'in September 1929', 'on 18 June 1815', 'in January 30, 1933', 'in 1923-24', 'by about 1700', 'in c. 1700'.
_DATE_BODY = (rf"\s+(?:(?:in|by|of|on|at|during|for)\s+(?:(?:about|around|approximately|roughly|c\.|ca\.|circa)\s+)?|(?:about|around|circa|c\.|ca\.)\s+)"
              rf"(?:the\s+)?(?:(?:early|late|mid|the end of|the start of|the beginning of|the middle of)[\s-]*)?"
              rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:{_MONTH}\s+)?(?:\d{{1,2}},?\s+)?(?:1[0-9]{{3}}|20[0-9]{{2}})(?:\s*[-–/]\s*\d{{2,4}})?(?![\d])")
_DATE = rf"(?:{_DATE_BODY})?"


def _fig(i: int, *, dated: bool = False, numx: str = _NUMX, unit_words: str = _UNIT_WORDS) -> str:
    """One figure of a pair, with named groups ``q<i>`` (qualifier), ``n<i>`` (number), ``u<i>`` (unit), ``noun<i>`` and ``d<i>`` (date).
    ``numx`` and ``unit_words`` default to the general reading's; the SI reading passes its own."""
    date = _DATE_BODY if dated else _DATE
    return (rf"(?:(?P<q{i}>{_QUAL})\s+)?(?P<n{i}>{numx})(?:\s*(?P<u{i}>{unit_words})(?!\w))?(?P<noun{i}>{_NOUN}){_PER}(?P<d{i}>{date})")


_FROM_TO_RE = re.compile(rf"\b(?:from|of)\s+{_fig(1)}\s+(?:to|and)\s+{_fig(2)}", re.IGNORECASE)
#: '... X in D1 and [reached] Y in D2': both dates are required, so a list of undated figures is never a pair.
_TO_VERB = (r"(?:reached|rose to|risen to|climbed to|grew to|increased to|jumped to|soared to|fell to|fallen to|dropped to|declined to|decreased to|"
            r"sank to|shrank to|stood at|was|were|had|bought|cost|numbered|totalled|totaled|to)")
_AND_DATED_RE = re.compile(rf"(?<![\w.,]){_fig(1, dated=True)}\s*,?\s+and\s+(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{_fig(2, dated=True)}", re.IGNORECASE)
#: The next item of a list after a pair's second figure: ', 4.5 million in 1931 and 5.6 million in 1932'.
_LIST_ITEM_RE = re.compile(rf"\s*(?:,\s*(?:and\s+)?|\s+and\s+)(?:then\s+)?(?:to\s+)?{_fig(3, dated=True)}", re.IGNORECASE)
#: A chained continuation: '..., before climbing to 5.6 million in 1932', ', and on to 4.5 million in 1931'.
_CONT_RE = re.compile(
    rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
    rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+)?(?:further\s+|again\s+|back\s+)?to\s+{_fig(3)}"
    rf"|(?:\bbefore|\bthen|\band then|\band later|\blater)\s+(?:reaching|reached|hitting|hit|peaking at|peaked at)\s+{_fig(4)}", re.IGNORECASE)
_YEAR_SPAN_RE = re.compile(r"\b(?:from|between)\s+(1[0-9]{3}|20[0-9]{2})\s+(?:to|and)\s+(1[0-9]{3}|20[0-9]{2})\b")
_FALL_WORDS = frozenset({"fall", "decrease", "decline", "drop", "reduction", "cut", "loss", "contraction", "fell", "dropped", "declined", "decreased", "shrank", "contracted", "slumped", "collapsed", "halved", "halving"})
_DIR_NOUN = r"(increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction)"
_DIR_VERB = r"(rose|grew|increased|expanded|climbed|fell|dropped|declined|decreased|shrank|contracted|slumped|collapsed)"
_PCT_CHANGE_RE = re.compile(
    rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)"
    rf"|(?:an?\s+)?(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}\s+{_DIR_NOUN}"
    rf"|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)",
    re.IGNORECASE)
#: 'a change of 20 per cent': the direction is the figures' own (a sign is read as stated).
_CHANGE_OF_RE = re.compile(rf"(?:an?\s+)?(?:net\s+|overall\s+|total\s+)?change\s+of\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)", re.IGNORECASE)
# 'a fall of 4.2 percentage points' / 'rose by 3 points' between two per-cent figures: an absolute difference.
_POINTS_CHANGE_RE = re.compile(
    rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*(percentage\s+)?points?\b"
    rf"|(?:an?\s+)?(?:({_QUAL})\s+)?{_AMOUNT}\s*(percentage\s+)?points?\s+{_DIR_NOUN}"
    rf"|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*(percentage\s+)?points?\b",
    re.IGNORECASE)
_FRAC = r"((?:a|one)\s+(?:half|third|quarter|fifth|tenth)|two[- ]thirds|three[- ]quarters|two[- ]fifths|three[- ]fifths|four[- ]fifths|half)"
_FRACTION_CHANGE_RE = re.compile(rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?{_FRAC}\b|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?{_FRAC}\b", re.IGNORECASE)
_FRACTION_WORDS = {"half": Fraction(1, 2), "third": Fraction(1, 3), "quarter": Fraction(1, 4), "fifth": Fraction(1, 5), "tenth": Fraction(1, 10),
                   "two thirds": Fraction(2, 3), "three quarters": Fraction(3, 4), "two fifths": Fraction(2, 5), "three fifths": Fraction(3, 5), "four fifths": Fraction(4, 5)}
_FOLD_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
               "hundred": 100, "thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
#: A fold word, with an optional qualifier before it and an article between them ('more than a tripling', 'nearly a doubling').
_FOLD_RE = re.compile(
    rf"(?:\b(more than|over|nearly|almost|about|around|roughly|approximately|close to|at least|less than|under|up to|just over|just under)\s+(?:an?\s+)?)?"
    rf"\b(doubl(?:ed|ing)|trebl(?:ed|ing)|tripl(?:ed|ing)|quadrupl(?:ed|ing)|halv(?:ed|ing)"
    rf"|({_DIGITS})-fold|({'|'.join(_FOLD_WORDS)})-?fold)\b", re.IGNORECASE)
_FOLD_STEMS = {"doubl": Fraction(2), "trebl": Fraction(3), "tripl": Fraction(3), "quadrupl": Fraction(4), "halv": Fraction(1, 2)}
#: A statement over a dated series: 'rose in each year that followed', 'fell every year', 'rose year on year'.
_MONOTONIC_RE = re.compile(
    r"\b(rose|grew|increased|climbed|fell|declined|dropped|decreased|shrank)\s+(?:again\s+|steadily\s+|further\s+)?"
    r"(?:(?:in|during)\s+)?(?:each|every)\s+(?:single\s+|subsequent\s+|following\s+|successive\s+)?year\b|\b(rose|grew|increased|climbed|fell|declined|dropped|decreased|shrank)\s+year[- ]on[- ]year\b",
    re.IGNORECASE)
#: 'the greatest proportional rise of the period', 'the steepest fall'.
_EXTREME_RE = re.compile(
    r"\b(greatest|largest|biggest|steepest|sharpest|fastest|highest|smallest|slowest|lowest|least)\s+(proportional\s+|relative\s+|percentage\s+|absolute\s+)?"
    r"(rise|increase|growth|jump|gain|fall|drop|decline|decrease|contraction)\b", re.IGNORECASE)
_EXTREME_HINT_RE = re.compile(r"greatest|largest|biggest|steepest|sharpest|fastest|highest|smallest|slowest|lowest|least")
#: An anaphor for a year stated in an earlier sentence.
_THAT_YEAR_RE = re.compile(r"\b(?:that|the same|this|the following|the next)\s+year\b", re.IGNORECASE)
_YEAR_TOKEN_RE = re.compile(r"(?<![\d,.])\b(1[0-9]{3}|20[0-9]{2})\b(?![\d,.]?\d)")
_YEAR_LIKE_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
_PCT_WORDS = frozenset({"per cent", "percent", "%"})
_SHARE_RE = re.compile(rf"\b{_NUM}\s*{_PCT_UNIT}\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{_NUM}{_UNIT}(?:\s+[a-z]+){{0,2}}?(?:\s*,\s*(?:or|i\.e\.|that is)?|\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()\s*(?:about|around|roughly|some)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
_TOTAL_RE = re.compile(rf"{_NUM}{_UNIT}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{_NUM}{_UNIT}[^.;]{{0,60}}?(?:a total of|totalling|together|in total|making|giving|totals?)\s+(?:about|around|roughly)?\s*{_NUM}{_UNIT}", re.IGNORECASE)
#: A full stop followed by a lower-case word inside one parser sentence: the arithmetic reading splits there too.
_LOWER_CONTINUATION_RE = re.compile(r"[.?!][\"”’')\]»]*\s+[a-z]")
#: Where one part of a clause ends and the next begins between two pairs.
_SEG_SEP_RE = re.compile(r",\s*(?:and|while|whereas|but|yet)\b|;|\s+and\s+", re.IGNORECASE)
_EDGE_SEP_RE = re.compile(r",\s*(?:and|while|whereas|but|yet)\b|;", re.IGNORECASE)
_MONTH_INDEX = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_SCALE = {"thousand": 10**3, "k": 10**3, "million": 10**6, "m": 10**6, "billion": 10**9, "bn": 10**9, "trillion": 10**12, "tn": 10**12, "trn": 10**12, "quadrillion": 10**15}
_LOWER_ONLY = frozenset({"more than", "over", "at least", "just over"})
_UPPER_ONLY = frozenset({"less than", "under", "at most", "up to", "just under"})
_PARA_RE = re.compile(r"\n\s*\n")
#: The longest series a cross-sentence check reads (the engine's symbol and n-ary limits stay far away).
_MAX_SERIES = 24
#: Half a percentage point: a per-cent figure rounded to the nearest whole number always passes.
POINT_FLOOR = Fraction(1, 2)
TOLERANCE_RULE = ("tolerance: the stated figure must lie within {tol}% of the value computed from the report's own figures; the band is symmetric "
                  "around the computed value (understating a change earns no wider band){floor}{side}")


class _Patterns(NamedTuple):
    """The figure patterns of one reading (the general reading's are the module-level patterns themselves)."""
    from_to: "re.Pattern[str]"
    and_dated: "re.Pattern[str]"
    list_item: "re.Pattern[str]"
    cont: "re.Pattern[str]"
    share: "re.Pattern[str]"
    total: "re.Pattern[str]"


_GENERAL_PATTERNS = _Patterns(_FROM_TO_RE, _AND_DATED_RE, _LIST_ITEM_RE, _CONT_RE, _SHARE_RE, _TOTAL_RE)


def _build_patterns(numx: str, num: str, unit_words: str, unit: str) -> _Patterns:
    """The six figure patterns from a reading's number, unit-word and unit pieces, composed exactly as the module-level
    (general) patterns are."""
    def fig(i: int, dated: bool = False) -> str:
        return _fig(i, dated=dated, numx=numx, unit_words=unit_words)
    return _Patterns(
        re.compile(rf"\b(?:from|of)\s+{fig(1)}\s+(?:to|and)\s+{fig(2)}", re.IGNORECASE),
        re.compile(rf"(?<![\w.,]){fig(1, True)}\s*,?\s+and\s+(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{fig(2, True)}", re.IGNORECASE),
        re.compile(rf"\s*(?:,\s*(?:and\s+)?|\s+and\s+)(?:then\s+)?(?:to\s+)?{fig(3, True)}", re.IGNORECASE),
        re.compile(
            rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
            rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+)?(?:further\s+|again\s+|back\s+)?to\s+{fig(3)}"
            rf"|(?:\bbefore|\bthen|\band then|\band later|\blater)\s+(?:reaching|reached|hitting|hit|peaking at|peaked at)\s+{fig(4)}", re.IGNORECASE),
        re.compile(rf"\b{num}\s*{_PCT_UNIT}\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{num}{unit}(?:\s+[a-z]+){{0,2}}?(?:\s*,\s*(?:or|i\.e\.|that is)?|\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()\s*(?:about|around|roughly|some)?\s*{num}{unit}", re.IGNORECASE),
        re.compile(rf"{num}{unit}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{num}{unit}[^.;]{{0,60}}?(?:a total of|totalling|together|in total|making|giving|totals?)\s+(?:about|around|roughly)?\s*{num}{unit}", re.IGNORECASE),
    )


#: SI reading pieces: scientific notation and a sign on a figure; spelled-out scale words only; unit symbols of the STEM table.
_SI_DIGITS = rf"{si_digits_pattern()}|{_DIGITS}"
_SI_UNIT_RX = f"(?-i:{si_unit_pattern()})"
_SI_NUMX = rf"(?:(?:-(?=\.?\d))?(?:{_SI_DIGITS})|{_WNUM})(?!\d|,\d|\.\d)"
_SI_NUM = rf"((?:-(?=\.?\d))?(?:{_SI_DIGITS})|{_WNUM})(?!\d|,\d|\.\d)"
_SI_UNIT_WORDS = (rf"(?:{SI_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes|to (?:the|one|a) (?:US |U\.S\. |American )?(?:dollar|pound)s?"
                  rf"|{_SI_UNIT_RX})")
_SI_UNIT = rf"(?:\s*({SI_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes|{_SI_UNIT_RX})(?!\w))?"
#: 'halved twice', 'doubled three times': a fold repeated (SI reading only); at most 30 repetitions are read.
_REPEAT_RE = re.compile(r"\s+(?:(twice)|(three|four|five|six|seven|eight|nine|ten|\d{1,2})\s+times)\b", re.IGNORECASE)
_REPEAT_WORDS = {"three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
_MAX_REPEAT = 30


@lru_cache(maxsize=2)
def _si_patterns() -> _Patterns:
    return _build_patterns(_SI_NUMX, _SI_NUM, _SI_UNIT_WORDS, _SI_UNIT)


def _patterns(reading: QuantReading) -> _Patterns:
    return _si_patterns() if reading.si else _GENERAL_PATTERNS


@dataclass(frozen=True)
class QuantCheck:
    check_id: str
    kind: str                 # percent_change | points_change | fraction_change | fold_change | series_monotonic | series_extreme | share | total
    sentence: str
    problem: Problem
    expected_if_consistent: str = "ENTAILED"
    rule: str = ""            # the tolerance rule applied, for the receipt
    basis: str = ""           # for a relation stated across sentences: where its year and figures were read


@dataclass(frozen=True)
class QuantUndecided:
    """A stated derived figure or series relation that no check could be built for, and why.
    The core pack reports it as ``CORE-QNT-001`` so it never crosses the hub silently."""
    paragraph: int            # 1-based, over the blank-line paragraphs of the text
    sentence: int             # 1-based within the paragraph, by the shared sentence splitter
    sentence_text: str
    phrase: str
    reason: str


def _words_value(words: str) -> Fraction:
    """Value of a number written in words below a thousand ('two hundred and sixty' -> 260)."""
    total = 0
    for tok in re.split(r"[\s-]+", words.lower()):
        if tok == "and" or not tok:
            continue
        if tok == "hundred":
            total = (total or 1) * 100
        else:
            total += _WORD_VALUES[tok]
    return Fraction(total)


def _number(num: str) -> Fraction:
    """Exact value of a figure written in digits (thousands separators, decimals, a decimal comma, a sign) or in words."""
    s = num.strip().lstrip("+")
    if re.fullmatch(r"-?\d+,\d{1,2}", s):
        return Fraction(s.replace(",", "."))  # '1,9': a decimal comma, never a thousands group
    if re.fullmatch(r"-?[\d,.]+", s):
        return Fraction(s.replace(",", ""))
    return _words_value(s)


def _frac(num: str, unit: Optional[str]) -> Fraction:
    f = _number(num)
    if unit:
        u = unit.lower()
        if u in _SCALE:
            f *= _SCALE[u]
    return f


def _real(f: Fraction) -> dict:
    return {"op": "real", "value": f"{f.numerator}/{f.denominator}" if f.denominator != 1 else str(f.numerator)}


def _v(n):
    return {"op": "var", "name": n}


def _year_like(num: str, unit: Optional[str]) -> bool:
    """A unitless integer in 1000-2099 with no separator reads as a year, not a quantity."""
    return not unit and bool(_YEAR_LIKE_RE.match(num))


def _is_pct(unit: Optional[str]) -> bool:
    return bool(unit) and unit.lower().replace("percent", "per cent") in _PCT_WORDS


def _unit_kind(unit: Optional[str]) -> Optional[str]:
    """'scale', 'pct', 'rate' or 'count' for a recognised unit word, None for a bare figure."""
    if not unit:
        return None
    u = unit.lower()
    if u in _SCALE:
        return "scale"
    if _is_pct(u):
        return "pct"
    if u.startswith("per ") or u.startswith("to "):
        return "rate"
    return "count"


def _side(qualifier: Optional[str]) -> str:
    q = (qualifier or "").lower()
    return "lower" if q in _LOWER_ONLY else "upper" if q in _UPPER_ONLY else "both"


def _rule_text(tolerance: Fraction, floor: Fraction, side: str) -> str:
    return TOLERANCE_RULE.format(tol=f"{float(tolerance) * 100:g}",
                                 floor=f", or within {float(floor):g} percentage points of it" if floor else "",
                                 side=" (one-sided: the stated figure is a lower bound)" if side == "lower" else " (one-sided: the stated figure is an upper bound)" if side == "upper" else "")


def _within(expr: dict, stated: Fraction, tolerance: Fraction, floor: Fraction = Fraction(0), side: str = "both") -> dict:
    """``expr`` within the tolerance band around itself that contains ``stated``:
    |computed - stated| <= tolerance * computed, or <= floor. Linear in ``expr``."""
    lo = min(stated / (1 + tolerance), stated - floor)
    hi = max(stated / (1 - tolerance), stated + floor)
    ge = {"op": "ge", "left": expr, "right": _real(lo)}
    le = {"op": "le", "left": expr, "right": _real(hi)}
    if side == "lower":
        return ge
    if side == "upper":
        return le
    return {"op": "and", "args": [ge, le]}


_within_general = _within


def _abs(expr: dict) -> dict:
    return {"op": "ite", "cond": {"op": "ge", "left": expr, "right": _real(Fraction(0))}, "then": expr, "otherwise": {"op": "neg", "arg": expr}}


def _within_si(expr: dict, stated: Fraction, tolerance: Fraction, floor: Fraction = Fraction(0), side: str = "both") -> dict:
    """The SI reading's band, sign-aware: ``|computed - stated| <= tolerance * |computed| + floor``, with ``|.|`` encoded
    by ``ite``. Linear in ``expr``. A stated figure of 0 is decided by the same inequality. One-sided: the stated figure
    is a lower bound (``computed - stated >= -(slack)``) or an upper bound (``computed - stated <= slack``)."""
    diff = {"op": "sub", "left": expr, "right": _real(stated)}
    slack: dict = {"op": "mul", "args": [_real(tolerance), _abs(expr)]}
    if floor:
        slack = {"op": "add", "args": [_real(floor), slack]}
    if side == "lower":
        return {"op": "ge", "left": diff, "right": {"op": "neg", "arg": slack}}
    if side == "upper":
        return {"op": "le", "left": diff, "right": slack}
    return {"op": "le", "left": _abs(diff), "right": slack}


def _problem(pid: str, claim_id: str, request_id: str, symbols: list[tuple[str, str]], premises: list[tuple[str, dict, str]], conclusion: tuple[str, dict, str], note: str = "figure stated in the report itself") -> Problem:
    return Problem.model_validate({
        "problem_id": pid, "request_id": request_id, "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": n, "sort": "Real", "meaning": m[:1000]} for n, m in symbols],
        "premises": [{"id": i, "expr": e, "label": l[:1000], "grounding": {"kind": "supplied_text", "verified": True, "note": note[:1000]}} for i, e, l in premises],
        "conclusion": {"id": conclusion[0], "expr": conclusion[1], "label": conclusion[2][:1000], "grounding": {"kind": "supplied_text", "verified": True}},
    })


def _fmt(f: Fraction) -> str:
    """A stated figure as written: a terminating decimal in decimal form ('37.5'), otherwise the exact fraction."""
    d = f.denominator
    while d % 2 == 0:
        d //= 2
    while d % 5 == 0:
        d //= 5
    if d == 1:
        text = f"{f.numerator / f.denominator:.10f}".rstrip("0").rstrip(".") if f.denominator != 1 else str(f.numerator)
        return text
    return str(f)


def _direction(word: str) -> str:
    return "fall" if word.lower() in _FALL_WORDS else "rise"


def _signed(direction: str, amount: str) -> tuple[str, Fraction]:
    """A stated change with a sign reverses its direction: 'a rise of -10 per cent' is a fall of 10."""
    value = _number(amount)
    if value < 0:
        return ("rise" if direction == "fall" else "fall"), -value
    return direction, value


# ------------------------------------------------------------------ figures, pairs and derived phrases of one clause


@dataclass(frozen=True)
class _Fig:
    num: str
    unit: Optional[str]
    noun: str
    date: str
    start: int
    end: int

    @property
    def year(self) -> Optional[int]:
        m = re.search(r"(1[0-9]{3}|20[0-9]{2})", self.date)
        return int(m.group(1)) if m else None

    @property
    def annual(self) -> bool:
        """Dated by a year alone (not a month, a day, a range or a part of the year): a point of an annual series."""
        d = self.date
        return (self.year is not None and not re.search(_MONTH, d, re.IGNORECASE) and not re.search(r"(1[0-9]{3}|20[0-9]{2})\s*[-–/]\s*\d", d)
                and not re.search(r"\b(?:early|late|mid|end|start|beginning|middle)\b", d, re.IGNORECASE) and not re.search(r"\d{1,2}(?:st|nd|rd|th)?\s+(?:1[0-9]{3}|20[0-9]{2})", d))


def _fig_of(m: "re.Match[str]", i: int) -> _Fig:
    return _Fig(m.group(f"n{i}"), m.group(f"u{i}"), (m.group(f"noun{i}") or "").strip(), (m.group(f"d{i}") or "").strip(), m.start(f"n{i}"), m.end())


@dataclass
class _Pair:
    start: int
    end: int
    before: _Fig
    after: _Fig
    tail: list = field(default_factory=list)   # list figures after the second figure, in order

    @property
    def last(self) -> _Fig:
        return self.tail[-1] if self.tail else self.after


@dataclass(frozen=True)
class _Derived:
    start: int
    end: int
    kind: str                 # percent_change | points_change | fraction_change | fold_change | change
    words: str
    direction: Optional[str]
    stated: Fraction
    side: str
    percentage_points: bool = False


_FRACTION_HINT_RE = re.compile(r"half|third|quarter|fifth|tenth")
_FOLD_HINT_RE = re.compile(r"fold|doubl|trebl|tripl|quadrupl|halv")
#: A figure of a pair is digits or a number word; a clause with neither holds no pair.
_FIGURE_HINT_RE = re.compile(rf"\d|\b(?:{_WNUM_TOKEN})\b", re.IGNORECASE)
#: A clause with none of these states no derived figure (a cheap test before the five patterns run).
_DERIVED_HINT_RE = re.compile(r"per\s*cent|percent|%|points?\b|half|third|quarter|fifth|tenth|fold|doubl|trebl|tripl|quadrupl|halv", re.IGNORECASE)


def _derived_phrases(clause: str, si: bool = False) -> list[_Derived]:
    """Every stated derived figure of ``clause``, in order of position. In the SI reading a fold
    may be repeated ('halved twice' is a factor of 1/4, 'doubled three times' 8)."""
    out: list[_Derived] = []
    if not _DERIVED_HINT_RE.search(clause):
        return out
    low = clause.lower()
    pct = "%" in clause or "per cent" in low or "percent" in low or "per\u00a0cent" in low
    for m in (_PCT_CHANGE_RE.finditer(clause) if pct else ()):
        if m.group(1):
            d, v = _signed(_direction(m.group(1)), m.group(3))
            out.append(_Derived(m.start(), m.end(), "percent_change", m.group(0).strip(), d, v, _side(m.group(2))))
        elif m.group(6):
            d, v = _signed(_direction(m.group(6)), m.group(5))
            out.append(_Derived(m.start(), m.end(), "percent_change", m.group(0).strip(), d, v, _side(m.group(4))))
        else:
            d, v = _signed(_direction(m.group(7)), m.group(9))
            out.append(_Derived(m.start(), m.end(), "percent_change", m.group(0).strip(), d, v, _side(m.group(8))))
    for m in (_CHANGE_OF_RE.finditer(clause) if pct and "change" in low else ()):
        value = _number(m.group(2))
        out.append(_Derived(m.start(), m.end(), "change", m.group(0).strip(), "fall" if value < 0 else None, abs(value), _side(m.group(1))))
    for m in (_POINTS_CHANGE_RE.finditer(clause) if "point" in low else ()):
        if m.group(1):
            (d, v), q, pp = _signed(_direction(m.group(1)), m.group(3)), m.group(2), bool(m.group(4))
        elif m.group(8):
            (d, v), q, pp = _signed(_direction(m.group(8)), m.group(6)), m.group(5), bool(m.group(7))
        else:
            (d, v), q, pp = _signed(_direction(m.group(9)), m.group(11)), m.group(10), bool(m.group(12))
        out.append(_Derived(m.start(), m.end(), "points_change", m.group(0).strip(), d, v, _side(q), pp))
    for m in (_FRACTION_CHANGE_RE.finditer(clause) if _FRACTION_HINT_RE.search(low) else ()):
        word, qual, frac = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(4), m.group(5), m.group(6))
        key = re.sub(r"^(?:a|one)\s+", "", frac.lower()).replace("-", " ")
        out.append(_Derived(m.start(), m.end(), "fraction_change", frac, _direction(word), _FRACTION_WORDS[key], _side(qual)))
    for m in (_FOLD_RE.finditer(clause) if _FOLD_HINT_RE.search(low) else ()):
        word = m.group(2).lower()
        factor = next((f for stem, f in _FOLD_STEMS.items() if word.startswith(stem)), None)
        if factor is None:
            factor = Fraction(m.group(3).replace(",", "")) if m.group(3) else Fraction(_FOLD_WORDS[m.group(4).lower()])
        if factor <= 0:
            continue
        end, words = m.end(), m.group(0).strip()
        if si:
            rep = _REPEAT_RE.match(clause, m.end())
            if rep:
                times = 2 if rep.group(1) else (_REPEAT_WORDS.get(rep.group(2).lower()) or int(rep.group(2)))
                if 1 <= times <= _MAX_REPEAT:
                    factor, end, words = factor ** times, rep.end(), clause[m.start():rep.end()].strip()
        out.append(_Derived(m.start(), end, "fold_change", words, None, factor, _side(m.group(1))))
    out.sort(key=lambda d: d.start)
    return out


def _pairs(clause: str, pat: _Patterns = _GENERAL_PATTERNS) -> list[_Pair]:
    """Every pair of figures of ``clause`` (from/to with its list and continuations, then 'X in D1 and Y in D2'), in order.
    ``pat`` holds the reading's figure patterns (the general reading's by default)."""
    pairs: list[_Pair] = []
    covered: list[tuple[int, int]] = []
    if not _FIGURE_HINT_RE.search(clause):
        return pairs

    def overlaps(s: int, e: int) -> bool:
        return any(s < b and a < e for a, b in covered)

    for m in pat.from_to.finditer(clause):
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in pat.cont.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        prior = [p for p in pairs if p.end <= m.start()]
        if not prior:
            continue
        p = _Pair(m.start(), m.end(), max(prior, key=lambda x: x.end).last, _fig_of(m, 3 if m.group("n3") else 4))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in pat.and_dated.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        pairs.append(p)
        covered.append((p.start, p.end))
    pairs.sort(key=lambda p: p.start)
    return pairs


def _pairs_outside(pairs: list[_Pair], derived: list[_Derived]) -> list[_Pair]:
    """Pairs whose first figure is not the amount of a derived phrase ('a rise of 20 per cent in 1930 and 30 per cent in 1931' is no pair)."""
    return [p for p in pairs if not any(d.start <= p.before.start < d.end for d in derived)]


def _same_noun(a: str, b: str) -> bool:
    wa, wb = a.lower().split(), b.lower().split()
    return bool(wa and wb) and wa[-1].rstrip("s") == wb[-1].rstrip("s")


def _comparable(u1: Optional[str], u2: Optional[str], noun1: str = "", noun2: str = "") -> tuple[Optional[str], Optional[str], bool]:
    """Apply shared-unit elision and decide whether the pair can be compared at all.
    Returns ``(unit1, unit2, comparable)``. Elision applies only when the first figure carries
    neither a unit nor a noun: a first figure with its own noun ('4.2 marks ... 4.2 trillion
    marks') is read as written. Units of different kinds, or a scale on the first figure with
    no recognised unit on the second (an unknown unit word), are not comparable."""
    if not u1 and u2:
        if noun1:
            if _unit_kind(u2) == "scale":
                return None, u2, True  # 'from 4.2 marks to 4.2 trillion marks': the first figure is 4.2 marks
            return None, u2, False     # 'from 37 seats ... to 45 per cent': the first figure's noun is its own unit
        return u2, u2, True  # 'from 15 to 45 million', 'from 3.2 to 24.9 per cent'
    k1, k2 = _unit_kind(u1), _unit_kind(u2)
    if u1 and not u2:
        if k1 == "scale":
            return u1, u2, False  # 'from 4 billion to 4 lakh': the second figure's unit word is unknown
        return u1, u1, True  # 'from 37.3 per cent to 33.1': the first unit carries over
    if k1 and k2 and k1 != k2:
        return u1, u2, False
    return u1, u2, True


@dataclass(frozen=True)
class _Values:
    a: Fraction
    b: Fraction
    shown_a: str
    shown_b: str
    pct: bool                 # both figures are per-cent shares


def _shown(fig: _Fig, unit: Optional[str]) -> str:
    return " ".join(x for x in (fig.num, unit or fig.noun, fig.date) if x)


def _values(before: _Fig, after: _Fig) -> tuple[Optional[_Values], str]:
    """The two figures of a pair as exact values, or None and the reason they cannot be compared."""
    u1, u2, ok = _comparable(before.unit, after.unit, before.noun, after.noun)
    if not ok:
        return None, f"the units of '{_shown(before, before.unit)}' and '{_shown(after, after.unit)}' cannot be compared, so the pair was not read"
    if _year_like(before.num, u1) and _year_like(after.num, u2):
        return None, "year span"
    a, b = _frac(before.num, u1), _frac(after.num, u2)
    return _Values(a, b, _shown(before, u1), _shown(after, u2), _is_pct(u1) and _is_pct(u2)), ""


# ------------------------------------------------------------------ the SI reading of a pair (STEM branches)

_DIGIT_RE = re.compile(r"\d")


def _si_kind(unit: Optional[str], profile: str) -> Optional[str]:
    """``scale``, ``pct``, ``rate``, ``count``, ``si`` (a unit of the STEM table), ``si-affine`` (°C, °F) or ``unknown``
    for a unit read in the SI reading; None for a bare figure."""
    if not unit:
        return None
    u = unit.lower()
    if u in SI_SCALES:
        return "scale"
    if _is_pct(u):
        return "pct"
    if u.startswith("per ") or u.startswith("to "):
        return "rate"
    if u in ("seats", "votes"):
        return "count"
    su = si_unit(unit, profile)
    if su is None:
        return "unknown"
    return "si-affine" if su.affine else "si"


def _si_number(num: str) -> Optional[Fraction]:
    """A figure of the SI reading: digits (a sign, scientific notation) through the STEM number reader, words as in general."""
    if _DIGIT_RE.search(num):
        v = si_number(num)
        if v is None and re.fullmatch(r"-?\d+,\d{1,2}", num.strip()):
            v = _number(num)  # a decimal comma ('1,9 million'), read as the general reading reads it
        return v
    return _number(num)


def _si_value(num: str, unit: Optional[str], profile: str) -> Optional[Fraction]:
    """Exact value of a figure in the SI reading: a scale word multiplies, a unit of the table converts to SI (None when
    the unit has no exact factor), anything else is read as written."""
    v = _si_number(num)
    if v is None:
        return None
    kind = _si_kind(unit, profile)
    if kind == "scale":
        return v * SI_SCALES[unit.lower()]
    if kind in ("si", "si-affine"):
        su = si_unit(unit, profile)
        if su is None or su.factor is None or su.affine:
            return None
        return v * su.factor
    return v


def _si_shown(fig: _Fig, unit: Optional[str], value: Optional[Fraction], profile: str) -> str:
    shown = _shown(fig, unit)
    if value is not None and _si_kind(unit, profile) == "si":
        written = _si_number(fig.num)
        if written is not None and written != value:
            shown += f" (= {_fmt(value)} in SI units)"
    return shown


_RELATIVE_KINDS = frozenset({"percent_change", "change", "fraction_change", "fold_change"})


def _si_values(before: _Fig, after: _Fig, profile: str, kind: str = "") -> tuple[Optional[_Values], str]:
    """The SI reading of :func:`_values`: units of the STEM table convert exactly to SI and pair only when their dimensions
    agree; a relative change (``kind``) on an offset temperature scale is not defined."""
    u1, u2 = before.unit, after.unit
    k1, k2 = _si_kind(u1, profile), _si_kind(u2, profile)
    cannot = f"the units of '{_shown(before, u1)}' and '{_shown(after, u2)}' cannot be compared, so the pair was not read"
    if not u1 and u2:
        if before.noun and k2 != "scale":
            return None, cannot
        u1, k1 = (None, None) if before.noun else (u2, k2)
    elif u1 and not u2:
        if k1 == "scale":
            return None, cannot
        u2, k2 = u1, k1
    if "unknown" in (k1, k2):
        return None, cannot
    si1, si2 = bool(k1 and k1.startswith("si")), bool(k2 and k2.startswith("si"))
    if si1 and si2:
        a_u, b_u = si_unit(u1, profile), si_unit(u2, profile)
        if a_u is None or b_u is None:
            return None, cannot
        if a_u.dim != b_u.dim:
            return None, (f"'{_shown(before, u1)}' is a {a_u.dimension} and '{_shown(after, u2)}' a {b_u.dimension}: figures of different dimensions "
                          "cannot be compared, so the pair was not read")
    elif k1 and k2 and k1 != k2:
        return None, cannot
    if _year_like(before.num, u1) and _year_like(after.num, u2):
        return None, "year span"
    affine = "si-affine" in (k1, k2)
    if affine and kind in _RELATIVE_KINDS:
        return None, (f"a relative change between '{_shown(before, u1)}' and '{_shown(after, u2)}' is not defined on an offset temperature scale "
                      "(°C, °F), so the pair was not read")
    if si1 and si2 and (u1 or "").strip() == (u2 or "").strip():
        a, b = _si_number(before.num), _si_number(after.num)  # the same unit: compared as written, the factor cancels
        if a is not None and k1 == "scale":
            a, b = a * SI_SCALES[u1.lower()], (b * SI_SCALES[u1.lower()] if b is not None else None)
    elif affine:
        return None, f"'{_shown(before, u1)}' and '{_shown(after, u2)}' are on offset temperature scales in different units, so the pair was not read"
    else:
        a, b = _si_value(before.num, u1, profile), _si_value(after.num, u2, profile)
    if a is None or b is None:
        return None, f"'{_shown(before, u1)}' or '{_shown(after, u2)}' has no exact value in SI units, so the pair was not read"
    shown_a = _si_shown(before, u1, a, profile) if not (si1 and (u1 or "").strip() == (u2 or "").strip()) else _shown(before, u1)
    shown_b = _si_shown(after, u2, b, profile) if not (si2 and (u1 or "").strip() == (u2 or "").strip()) else _shown(after, u2)
    return _Values(a, b, shown_a, shown_b, _is_pct(u1) and _is_pct(u2)), ""


def _si_series_of(pair: "_Pair", sentence_index: int, text: str, profile: str) -> Optional["_Series"]:
    """The SI reading of :func:`_series_of`: the figures as written when they all carry the same unit (a scale word
    applied), else in SI units; the series kind names the unit's dimension, so series of different dimensions never
    merge, and an offset temperature scale is marked (``si-affine``) so no relative change is read from it."""
    probe, _why = _si_values(pair.before, pair.after, profile)
    if probe is None:
        return None
    unit = pair.after.unit or pair.before.unit
    kind = _si_kind(unit, profile)
    if kind in ("si", "si-affine"):
        su = si_unit(unit, profile)
        if su is None:
            return None
        kind = f"{kind}:{su.dim}"
    figs = (pair.before, pair.after, *pair.tail)
    same = len({(f.unit or unit or "").strip() for f in figs}) == 1
    points: dict[int, tuple[Fraction, str]] = {}
    for f in figs:
        if not f.annual:
            continue
        u = f.unit or unit
        if same:
            value = _si_number(f.num)
            if value is not None and _si_kind(u, profile) == "scale":
                value *= SI_SCALES[u.lower()]
        else:
            value = _si_value(f.num, u, profile)
        if value is None:
            return None
        if f.year in points and points[f.year][0] != value:
            return None  # one pair states two values for one year: not a series
        points[f.year] = (value, _shown(f, u))
    if len(points) < 2:
        return None
    return _Series(kind, unit, points, sentence_index, text)


@dataclass(frozen=True)
class _Spec:
    """A check to build: kind, the statement it reads, the problem's parts."""
    kind: str
    sentence: str
    symbols: tuple
    premises: tuple
    conclusion: tuple
    floor: Fraction
    side: str
    note: str = "figure stated in the report itself"
    basis: str = ""


def _pair_spec(values: _Values, d: _Derived, statement: str, tolerance: Fraction, note: str = "figure stated in the report itself", basis: str = "",
               *, si: bool = False) -> tuple[Optional[_Spec], str]:
    """The check of derived figure ``d`` against the pair ``values``, or None and why it cannot be built. In the SI
    reading the band is sign-aware (:func:`_within_si`) and a relative change is taken against the earlier figure's
    magnitude (a rise from -4 to -2 is a rise of 50 per cent)."""
    a, b = values.a, values.b
    _within = _within_si if si else _within_general
    base = abs(a) if si else a
    premises = (("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(a)}, f"before = {values.shown_a}"),
                ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(b)}, f"after = {values.shown_b}"))
    before_after = (("before", "the earlier figure as stated"), ("after", "the later figure as stated"))
    if d.kind == "points_change":
        if d.percentage_points and not values.pct:
            return None, "a change in percentage points between figures that are not both per-cent shares"
        diff = {"op": "sub", "left": _v("after"), "right": _v("before")}
        if d.direction == "fall":
            diff = {"op": "neg", "arg": diff}
        symbols = (("before", "the earlier share as stated (per cent)"), ("after", "the later share as stated (per cent)")) if values.pct else before_after
        return _Spec("points_change", statement, symbols, premises, ("STATED_POINTS", _within(diff, d.stated, tolerance, POINT_FLOOR, d.side),
                     f"stated {d.direction} of {_fmt(d.stated)} {'percentage ' if d.percentage_points else ''}points against the computed difference"), POINT_FLOOR, d.side, note, basis), ""
    if a == 0:
        return None, "the earlier figure is zero, so no relative change can be computed"
    if d.kind in ("percent_change", "change"):
        direction = d.direction or ("rise" if b >= a else "fall")
        change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(base)}]}
        if direction == "fall":
            change = {"op": "neg", "arg": change}
        label = f"stated {direction} of {_fmt(d.stated)} per cent against the computed change" if d.kind == "percent_change" else f"stated change of {_fmt(d.stated)} per cent ({direction}, the figures' own direction) against the computed change"
        return _Spec("percent_change", statement, before_after, premises, ("STATED_CHANGE", _within(change, d.stated, tolerance, POINT_FLOOR, d.side), label), POINT_FLOOR, d.side, note, basis), ""
    if d.kind == "fraction_change":
        change = {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(base)}
        if d.direction == "fall":
            change = {"op": "neg", "arg": change}
        return _Spec("fraction_change", statement, before_after, premises, ("STATED_FRACTION", _within(change, d.stated, tolerance, Fraction(0), d.side),
                     f"stated {d.direction} of '{d.words}' (= {d.stated}) against the computed change"), Fraction(0), d.side, note, basis), ""
    ratio = {"op": "div", "left": _v("after"), "right": _real(a)}
    return _Spec("fold_change", statement, before_after, premises, ("STATED_FOLD", _within(ratio, d.stated, tolerance, Fraction(0), d.side),
                 f"stated '{d.words}' (factor {_fmt(d.stated)}) against the computed ratio"), Fraction(0), d.side, note, basis), ""


def _segments(clause: str, pairs: list[_Pair]) -> list[tuple[int, int]]:
    """``(start, end)`` of the part of ``clause`` each pair owns: parts are cut at the last
    separator between two pairs (else where the next pair starts); text before the first pair
    after a separator, and after the last pair beyond a separator, belongs to no pair."""
    bounds: list[tuple[int, int]] = []
    for i, p in enumerate(pairs):
        if i == 0:
            seps = list(_EDGE_SEP_RE.finditer(clause, 0, p.start))
            start = seps[-1].end() if seps else 0
        else:
            start = bounds[-1][1]
        if i + 1 < len(pairs):
            nxt = pairs[i + 1]
            seps = list(_SEG_SEP_RE.finditer(clause, p.end, nxt.start))
            end = seps[-1].start() if seps else nxt.start
        else:
            sep = _EDGE_SEP_RE.search(clause, p.end)
            end = sep.start() if sep else len(clause)
        bounds.append((start, max(end, p.end)))
    return bounds


# ------------------------------------------------------------------ the paragraph's dated series (relations across sentences)


@dataclass
class _Series:
    kind: Optional[str]
    unit: Optional[str]
    points: dict              # year -> (value, shown)
    sentence: int             # 0-based index of the sentence that states it
    text: str


def _series_of(pair: _Pair, sentence_index: int, text: str) -> Optional[_Series]:
    """The year-dated figures of a pair and its list as one series (a month-dated figure is not an annual point)."""
    u1, u2, ok = _comparable(pair.before.unit, pair.after.unit, pair.before.noun, pair.after.noun)
    if not ok or (_year_like(pair.before.num, u1) and _year_like(pair.after.num, u2)):
        return None
    points: dict[int, tuple[Fraction, str]] = {}
    for f in (pair.before, pair.after, *pair.tail):
        if not f.annual:
            continue
        unit = u1 if f is pair.before else (f.unit or u2)
        value = _frac(f.num, unit)
        if f.year in points and points[f.year][0] != value:
            return None  # one pair states two values for one year: not a series
        points[f.year] = (value, _shown(f, unit))
    if len(points) < 2:
        return None
    return _Series(_unit_kind(u2 or u1), u2 or u1, points, sentence_index, text)


def _merge(candidates: list[_Series]) -> list[_Series]:
    """Series that agree on every shared year are one series."""
    merged: list[_Series] = []
    for s in candidates:
        for m in merged:
            if m.kind == s.kind and all(m.points[y][0] == s.points[y][0] for y in m.points.keys() & s.points.keys()):
                m.points = {**s.points, **m.points}
                break
        else:
            merged.append(_Series(s.kind, s.unit, dict(s.points), s.sentence, s.text))
    return merged


def _content_words(text: str) -> set[str]:
    stop = {"the", "a", "an", "of", "in", "on", "by", "to", "and", "or", "that", "this", "year", "years", "was", "were", "is", "rose", "grew", "fell", "from", "with",
            "about", "roughly", "per", "cent", "rise", "fall", "increase", "decrease", "period", "greatest", "largest", "each", "every", "then", "which", "its", "their"}
    return {w.rstrip("s") for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in stop}


def _pick_series(series: list[_Series], years: list[int], clause: str, *, kinds: Optional[set] = None) -> tuple[Optional[_Series], str]:
    """The one series of the paragraph that states every year in ``years``; several are told apart by shared words with ``clause``."""
    candidates = [s for s in series if all(y in s.points for y in years) and (kinds is None or s.kind in kinds)]
    candidates = _merge(candidates)
    if not candidates:
        return None, "the paragraph states no dated series with figures for " + " and ".join(str(y) for y in years)
    if len(candidates) > 1:
        words = _content_words(clause)
        scored = [s for s in candidates if words & _content_words(s.text)]
        if len(scored) == 1:
            return scored[0], ""
        return None, f"{len(candidates)} dated series of the paragraph state figures for " + " and ".join(str(y) for y in years) + "; which one the statement relies on is not stated"
    return candidates[0], ""


def _earlier_year(sentences: list[str], index: int, clause: str, phrase_start: int) -> tuple[Optional[int], str]:
    """The year an anaphor ('that year') refers to, and why when there is none: the one year stated
    before it in its own clause, else the one year stated in the nearest earlier sentence of the
    paragraph that states any. Two or more candidate years at the nearest level are ambiguous."""
    years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(clause[:phrase_start])})
    if len(years) == 1:
        return years[0], ""
    if years:
        return None, f"'that year' could refer to {len(years)} years stated before it in its sentence"
    for j in range(index - 1, -1, -1):
        years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(sentences[j])})
        if len(years) == 1:
            return years[0], ""
        if years:
            return None, f"'that year' could refer to {len(years)} years ({', '.join(map(str, years[:6]))}) stated in the sentence before it"
    return None, "'that year' refers to no year stated earlier in the paragraph"


def _target_years(sentences: list[str], index: int, clause: str, at: int, series_years: list[int]) -> tuple[Optional[tuple[int, int]], str]:
    """(earlier year, later year) a derived figure with no pair of its own speaks of."""
    span = _YEAR_SPAN_RE.search(clause)
    if span:
        return (int(span.group(1)), int(span.group(2))), f"the years {span.group(1)} and {span.group(2)} stated in the sentence"
    anaphor = _THAT_YEAR_RE.search(clause)
    if anaphor:
        year, why = _earlier_year(sentences, index, clause, anaphor.start())
        if year is None:
            return None, why
        how = f"'{anaphor.group(0)}' read as {year}, the one year stated before it"
    else:
        stated = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(clause)})
        if len(stated) != 1:
            return None, ("the sentence states no year and no anaphor such as 'that year'" if not stated else f"the sentence states {len(stated)} years and no span between them")
        year, how = stated[0], f"the year {stated[0]} stated in the sentence"
    earlier = [y for y in series_years if y < year]
    if not earlier:
        return None, f"the paragraph's dated figures state no year before {year}"
    return (max(earlier), year), how + f", against the previous dated figure ({max(earlier)})"


def _series_label(s: _Series, years: list[int]) -> str:
    return "; ".join(f"{y}: {s.points[y][1]}" for y in years)


def _paragraph_sentences(text: str, reading: QuantReading):
    """``(paragraph number, sentences, sentence numbers or None)`` of ``text``: the general reading splits blank-line
    paragraphs with the shared splitter (numbers 1, 2, ...); the SI reading takes the STEM statements of the SI quant view
    (maths masked), numbered as the STEM claim ids."""
    if not reading.si:
        for pi, para in enumerate((p for p in _PARA_RE.split(text.strip()) if p.strip()), start=1):
            yield pi, split_sentences(para), None
        return
    view = si_quant_view(text, reading.profile)
    grouped: dict[int, tuple[list[str], list[int]]] = {}
    for pi, number, start, end in si_statements(text, reading.profile):
        texts, numbers = grouped.setdefault(pi, ([], []))
        texts.append(view[start:end])
        numbers.append(number)
    for pi in sorted(grouped):
        yield pi, grouped[pi][0], grouped[pi][1]


def _num(numbers: Optional[list[int]], index: int) -> int:
    """The number a finding gives sentence ``index`` (0-based) of its paragraph: ``index + 1``, or the STEM statement number."""
    return index + 1 if numbers is None else numbers[index]


def _si_others(kind: str, groups: tuple, profile: str) -> tuple[Optional[tuple[Fraction, ...]], str]:
    """Values of a share (percentage, whole, part) or a total (two addends and the total) in the SI reading, or None and
    why: the figures carrying units must share one dimension."""
    pairs = [(groups[0], None), (groups[1], groups[2]), (groups[3], groups[4])] if kind == "share" else [(groups[0], groups[1]), (groups[2], groups[3]), (groups[4], groups[5])]
    measured = pairs[1:] if kind == "share" else pairs
    dims = set()
    for num, unit in measured:
        k = _si_kind(unit, profile)
        if k == "unknown":
            return None, f"the unit '{unit}' could not be read"
        if k in ("si", "si-affine"):
            su = si_unit(unit, profile)
            if su is None or su.affine:
                return None, f"the unit '{unit}' is not read for a {kind}"
            dims.add(str(su.dim))
        elif k is not None:
            dims.add(k)
    if len(dims) > 1:
        return None, f"the figures of the {kind} carry units of different kinds or dimensions, so it was not checked"
    values = []
    for num, unit in pairs:
        v = _si_number(num) if unit is None else _si_value(num, unit, profile)
        if v is None:
            return None, f"the figure '{(num + ' ' + (unit or '')).strip()}' could not be read exactly"
        values.append(v)
    return tuple(values), ""


@lru_cache(maxsize=128)
def _analyse(text: str, tolerance: Fraction, reading: QuantReading = GENERAL) -> tuple[tuple[_Spec, ...], tuple[QuantUndecided, ...], tuple[tuple[str, tuple], ...]]:
    """Read every paragraph of ``text``: the pair-bound checks, the cross-sentence checks, the
    statements left undecided, and the share/total matches (built later). Memoised per text
    and reading, since the core pack asks for the checks and for the undecided statements of
    one report. ``reading`` selects the general or the SI reading (module docstring)."""
    si_mode = reading.si
    pat = _patterns(reading)
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    all_clauses: list[str] = []
    clause_where: list[tuple[int, int, str]] = []   # (paragraph, sentence number, sentence) of every clause, for SI undecided shares
    for pi, sentences, numbers in _paragraph_sentences(text, reading):
        series: list[_Series] = []
        pending: list[tuple[int, str, list[_Derived], Optional[tuple]]] = []   # (sentence index, clause, unbound derived, extras)
        per_sentence_specs: list[tuple[int, _Spec]] = []
        for si, sent in enumerate(sentences):
            clauses = split_clauses(sent) if (";" in sent or _LOWER_CONTINUATION_RE.search(sent)) else [sent]
            all_clauses.extend(clauses)
            if si_mode:
                clause_where.extend((pi, _num(numbers, si), sent.strip()) for _c in clauses)
            for clause in clauses:
                derived = _derived_phrases(clause, si_mode)
                pairs = _pairs_outside(_pairs(clause, pat), derived)
                for p in pairs:
                    s = _si_series_of(p, si, clause, reading.profile) if si_mode else _series_of(p, si, clause)
                    if s is not None:
                        series.append(s)
                bound: set[int] = set()
                segments = _segments(clause, pairs)
                for p, (seg_start, seg_end) in zip(pairs, segments):
                    mine = [d for d in derived if seg_start <= d.start < seg_end]
                    if not mine:
                        continue
                    for d in mine:
                        bound.add(id(d))
                        after = p.last if p.tail and d.start >= p.end else p.after
                        values, why = _si_values(p.before, after, reading.profile, d.kind) if si_mode else _values(p.before, after)
                        statement = clause.strip() if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                        if values is None:
                            if why != "year span":
                                undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), d.words, why))
                            else:
                                pending.append((si, clause, [d], None))
                            continue
                        spec, why = _pair_spec(values, d, statement, tolerance, si=si_mode)
                        if spec is None:
                            undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), d.words, why))
                        else:
                            per_sentence_specs.append((si, spec))
                loose = [d for d in derived if id(d) not in bound]
                low = clause.lower()
                extras = (_MONOTONIC_RE.search(clause) if "year" in low else None,
                          _EXTREME_RE.search(clause) if _EXTREME_HINT_RE.search(low) else None)
                if loose or extras[0] or (extras[1] and not pairs):
                    pending.append((si, clause, loose, extras))
        specs.extend(spec for _si, spec in per_sentence_specs)
        for si, clause, loose, extras in pending:
            sent = sentences[si].strip()
            note = "figure stated in the report itself, in another sentence of the paragraph"
            for d in loose:
                target, how = _target_years(sentences, si, clause, d.start, sorted({y for s in series for y in s.points}))
                if target is None:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, f"no figures are stated with it in its sentence and {how}"))
                    continue
                kinds = {"pct"} if d.kind == "points_change" and d.percentage_points else None
                s, why = _pick_series(series, list(target), clause, kinds=kinds)
                if s is None:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, f"no figures are stated with it in its sentence and {why}"))
                    continue
                if si_mode and (s.kind or "").startswith("si-affine") and d.kind in _RELATIVE_KINDS:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, "a relative change is not defined on an offset temperature scale (°C, °F), so the figures were not read"))
                    continue
                (va, sa), (vb, sb) = s.points[target[0]], s.points[target[1]]
                values = _Values(va, vb, sa + f" (stated in sentence {_num(numbers, s.sentence)} of the paragraph)", sb + f" (stated in sentence {_num(numbers, s.sentence)} of the paragraph)", s.kind == "pct")
                spec, why = _pair_spec(values, d, clause.strip(), tolerance, note, f"stated across sentences: {how}; figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, list(target))}", si=si_mode)
                if spec is None:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, why))
                else:
                    specs.append(spec)
            if not extras:
                continue
            mono, extreme = extras
            if mono:
                rising = mono.group(1) or mono.group(2)
                rising_dir = _direction(rising)
                anchor_years = [int(y) for y in _YEAR_TOKEN_RE.findall(clause[: mono.start()])]
                anchor = max(anchor_years) if anchor_years else None
                in_range = [s for s in _merge(series) if len([y for y in s.points if anchor is None or y >= anchor]) >= 2]
                if len(in_range) != 1:
                    why = "the paragraph states no dated series of two or more years" + (f" from {anchor}" if anchor else "") if not in_range else f"{len(in_range)} dated series of the paragraph could be meant"
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, mono.group(0), why))
                else:
                    s = in_range[0]
                    years = sorted(y for y in s.points if anchor is None or y >= anchor)[:_MAX_SERIES]
                    symbols = tuple((f"v{y}", f"the figure for {y} as stated") for y in years)
                    premises = tuple((f"Y{y}", {"op": "eq", "left": _v(f"v{y}"), "right": _real(s.points[y][0])}, f"{y}: {s.points[y][1]}") for y in years)
                    op = "gt" if rising_dir == "rise" else "lt"
                    steps = [{"op": op, "left": _v(f"v{b}"), "right": _v(f"v{a}")} for a, b in zip(years, years[1:])]
                    concl = steps[0] if len(steps) == 1 else {"op": "and", "args": steps}
                    label = f"stated '{mono.group(0)}' against the paragraph's dated series (sentence {_num(numbers, s.sentence)}): every year's figure {'above' if rising_dir == 'rise' else 'below'} the previous one"
                    specs.append(_Spec("series_monotonic", clause.strip(), symbols, premises, ("STATED_TREND", concl, label), Fraction(0), "both", note,
                                       f"stated across sentences: figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, years)}"))
            if extreme and not _pairs_outside(_pairs(clause, pat), _derived_phrases(clause, si_mode)):
                proportional = bool(extreme.group(2) and extreme.group(2).strip().lower() in ("proportional", "relative", "percentage")) or bool(_PCT_CHANGE_RE.search(clause))
                if extreme.group(2) and extreme.group(2).strip().lower() == "absolute":
                    proportional = False
                target, how = _target_years(sentences, si, clause, extreme.start(), sorted({y for s in series for y in s.points}))
                s, why = (None, how) if target is None else _pick_series(series, list(target), clause)
                if s is None:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, extreme.group(0), f"no figures are stated with it in its sentence and {why}"))
                    continue
                years = sorted(s.points)[:_MAX_SERIES]
                steps_years = list(zip(years, years[1:]))
                if target not in steps_years:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent, extreme.group(0), f"the years {target[0]} and {target[1]} are not consecutive figures of the paragraph's series"))
                    continue
                if len(steps_years) < 2:
                    continue  # one step only: nothing to compare it with
                largest = extreme.group(1).lower() in ("greatest", "largest", "biggest", "steepest", "sharpest", "fastest", "highest")
                falling = extreme.group(3).lower() in ("fall", "drop", "decline", "decrease", "contraction")
                symbols = tuple((f"v{y}", f"the figure for {y} as stated") for y in years)
                premises = tuple((f"Y{y}", {"op": "eq", "left": _v(f"v{y}"), "right": _real(s.points[y][0])}, f"{y}: {s.points[y][1]}") for y in years)

                def measure(a: int, b: int) -> dict:
                    if proportional:
                        if s.points[a][0] == 0:
                            return {"op": "sub", "left": _v(f"v{b}"), "right": _v(f"v{a}")}
                        return {"op": "div", "left": _v(f"v{b}"), "right": _real(s.points[a][0])}
                    return {"op": "sub", "left": _v(f"v{b}"), "right": _v(f"v{a}")}
                # a larger rise has the larger ratio/difference; a larger fall the smaller one
                op = ("ge" if not falling else "le") if largest else ("le" if not falling else "ge")
                cmp = [{"op": op, "left": measure(*target), "right": measure(a, b)} for a, b in steps_years if (a, b) != target]
                concl = cmp[0] if len(cmp) == 1 else {"op": "and", "args": cmp}
                label = (f"stated '{extreme.group(0)}' for {target[0]}-{target[1]} ({how}) against every other year-on-year {'proportional' if proportional else 'absolute'} change of the paragraph's series (sentence {_num(numbers, s.sentence)})")
                specs.append(_Spec("series_extreme", clause.strip(), symbols, premises, ("STATED_EXTREME", concl, label), Fraction(0), "both", note,
                                   f"stated across sentences: {how}; figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, years)}"))
    others: list[tuple[str, tuple]] = []
    for k, sent in enumerate(all_clauses):
        for kind, m in (("share", pat.share.search(sent)), ("total", pat.total.search(sent))):
            if not m:
                continue
            if not si_mode:
                others.append((kind, (sent.strip(), m.groups())))
                continue
            values, why = _si_others(kind, m.groups(), reading.profile)
            if values is None:
                p_no, s_no, s_text = clause_where[k]
                undecided.append(QuantUndecided(p_no, s_no, s_text, m.group(0).strip()[:120], why))
            else:
                others.append((kind, (sent.strip(), m.groups(), values)))
    return tuple(specs), tuple(undecided), tuple(others)


def undecided_quant_statements(text: str, tolerance: Fraction = Fraction(1, 20), *, reading: QuantReading = GENERAL) -> list[QuantUndecided]:
    """Stated derived figures and series relations no check could be built for, with the reason
    (units that cannot be compared, no figures in the sentence and none the paragraph's dated
    series supplies, an ambiguous series, a year that cannot be read). ``reading``: see the
    module docstring (the general reading by default)."""
    return list(_analyse(text, tolerance, reading)[1])


def extract_quant_checks(text: str, *, request_id: str, claim_id: str, tolerance: Fraction = Fraction(1, 20), reading: QuantReading = GENERAL) -> list[QuantCheck]:
    """Find every stated derived figure bound to a pair of figures (in its own clause, or in
    the paragraph's dated series) and build an exact entailment problem for each, then the
    stated shares and totals. ``tolerance`` is the relative slack allowed for rounding (default
    5 per cent of the computed value; see :data:`TOLERANCE_RULE`). ``reading``: see the module
    docstring (the general reading by default)."""
    specs, _undecided, others = _analyse(text, tolerance, reading)
    band = _within_si if reading.si else _within
    checks: list[QuantCheck] = []
    n = 0
    prefix = {"percent_change": "pct", "points_change": "points", "fraction_change": "frac", "fold_change": "fold", "series_monotonic": "trend", "series_extreme": "extreme"}
    for spec in specs:
        n += 1
        rule = _rule_text(tolerance, spec.floor, spec.side) if spec.kind not in ("series_monotonic", "series_extreme") else "exact comparison of the figures as stated (no tolerance)"
        checks.append(QuantCheck(f"quant-{n}", spec.kind, spec.sentence, _problem(f"quant-{prefix[spec.kind]}-{n}", claim_id, request_id, list(spec.symbols), list(spec.premises), spec.conclusion, spec.note),
                                 rule=rule, basis=spec.basis))
    for kind, other in others:
        sent, g = other[0], other[1]
        n += 1
        if kind == "share":
            pct, whole, part = other[2] if reading.si else (_number(g[0]), _frac(g[1], g[2]), _frac(g[3], g[4]))
            computed = {"op": "div", "left": {"op": "mul", "args": [_real(pct), _v("whole")]}, "right": _real(Fraction(100))}  # constant * variable: linear
            checks.append(QuantCheck(f"quant-{n}", "share", sent, _problem(f"quant-share-{n}", claim_id, request_id,
                [("pct", "stated percentage"), ("whole", "stated whole")],
                [("PCT", {"op": "eq", "left": _v("pct"), "right": _real(pct)}, "percentage"), ("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(whole)}, "whole")],
                ("STATED_PART", band(computed, part, tolerance), f"stated part {g[3]} {g[4] or ''}".strip())),
                rule=_rule_text(tolerance, Fraction(0), "both")))
        else:
            x, y, z = other[2] if reading.si else (_frac(g[0], g[1]), _frac(g[2], g[3]), _frac(g[4], g[5]))
            s = {"op": "add", "args": [_v("x"), _v("y")]}
            checks.append(QuantCheck(f"quant-{n}", "total", sent, _problem(f"quant-total-{n}", claim_id, request_id,
                [("x", "first addend"), ("y", "second addend")],
                [("X", {"op": "eq", "left": _v("x"), "right": _real(x)}, "x"), ("Y", {"op": "eq", "left": _v("y"), "right": _real(y)}, "y")],
                ("STATED_TOTAL", band(s, z, tolerance), f"stated total {g[4]} {g[5] or ''}".strip())),
                rule=_rule_text(tolerance, Fraction(0), "both")))
    return checks
