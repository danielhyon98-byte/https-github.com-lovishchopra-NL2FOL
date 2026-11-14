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
  ``nearly a doubling``, ``over a threefold rise``); multiples (``six times its earlier
  length``, ``twice its 1928 level``) are fold changes;
* absolute changes (``an increase of about 6,500 miles``, ``added roughly 4,500 miles``,
  ``rose by 2.9 million tonnes``) are the pair's difference, and average rates (``an average
  of 450 miles a year``) the difference over the years between the pair's dates;
* a from/to pair governed by a direction word and no stated change (``pig iron rising from
  about 3.3 million tonnes to about 6.2 million``) is checked for that direction;
* an exchange rate (``from 25 to the pound in 1919 to 240 to the pound``) is the price of one pound in the
  quoted currency, so a fall of the quoted currency is a RISE of the figure (integration gate 3): a sentence
  that names the quoted currency (``The franc fell``, ``the value of the mark collapsed``, ``Against the
  pound, the franc fell``) is checked with the direction inverted; one that names the base currency (``The
  dollar rose``) as written; one that names neither (``The exchange rate fell``, ``It fell``) as written when
  that holds, and otherwise is reported undecided (:data:`XRATE_OPEN_REASON`), never an error. A derived
  change on such a pair holds when it holds of the figures as written or of the quoted currency's value
  (one pound over the figure: ``a fall of about 90 per cent``, ``halved``), unless it is said of the base
  currency (``a rise in the dollar's price of about 1,670-fold``); exchange rates of two currencies, or an
  exchange rate against another rate, are not compared;
* a comparison with a stated benchmark (``fell short of the First Plan's original target of
  about 10 million tonnes of pig iron``, ``exceeded ... by half``) compares the figure before
  it in its clause, or the figure of the previous sentence its anaphoric subject (``These
  totals``) and the benchmark's noun (``of pig iron``) pick out, with the benchmark;
* a currency sign before a figure (``$4.03``, ``£600 million``, ``US$13 billion``) is the figure's
  unit of account (``$4.03`` and ``4.03 dollars`` are one unit); ``devalued``/``depreciated``/
  ``reduced``/``cut``/``lowered`` are falls and ``revalued``/``appreciated``/``raised`` rises;
* parts of a stated total (``..., of which A received X and B Y``, ``1882 alone brought N``) may
  not exceed it; a share of the total (``about a quarter of the decade's total``) is the figure
  before it over the total before that; a difference (``about $2 billion more than France``) is
  read against the figures the paragraph states for the two parties; a stated length (``for ten
  years, from 1882 to 1892``) against its span; a rate verb (``From 1961 the flow slowed to fifteen
  by 1968``) compares the span's count per year with the one-year count of the year before;
* a numeral of more than :data:`MAX_FIGURE_DIGITS` digits is never converted: its statement is
  reported undecided and the report's other checks still run;
* a stated length of years in any wording (``lasted five years, from June 1924 to January 1926``,
  ``which lasted about five years from 1924 to 1926``) against its span, in elapsed days when the dates
  carry months or days, or against the one span an adjacent sentence states (stated across sentences);
  a signed change (``changed by −6 per 1,000``, ``a change of −6``; an ASCII or Unicode minus); a share
  written ``356 of the 535 seats, about three-quarters``;
* a worked equation (``$6,000 ÷ $2.00 = 3,000 loaves``, :func:`worked_equations`) is written arithmetic
  this reader does not decide: it is returned undecided with that reason, never skipped (the Economics, Business Management and
  generic packs decide the ones ``branches.worked`` reads, and the core pack then does not name them);
* a figure in scientific notation (``from 500 tonnes to 2.5e3 tonnes``, ``to 2.5 × 10³ tonnes``, ``from 5 to 1e9``) is read whole
  as a figure of a pair, a list, a continuation, a dated figure, a difference or an absolute change (the STEM number reader gives
  its exact value), and no reader takes the mantissa alone or starts a figure at the exponent (``1e100``, ``2.5e−3``, ``× 10⁴``
  are read by none).

Relations stated across sentences: a derived figure whose clause states no pair (``The
annual average grew by roughly 60 per cent that year``, ``The 1840s ... added roughly 4,500
miles``: a decade is read as its first and last year), ``rose in each year (that
followed)``, ``the greatest (proportional) rise of the period`` and ``more than any other
decade of the period`` are read against the
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
computed value (rounding to the nearest whole per cent is never a finding). A per cent change
written with decimals states its own precision, so the half-point floor does not apply to it: it
passes within 5 per cent of the computed value, or within half a unit in its last written digit
plus 1 per cent of the computed value plus what rounding the pair's figures at their own written
precision can move the change by (:data:`PRECISION_RULE`), so 'from 112.0 to 115.4, an increase of
3.40%' (the change is 3.04%) is a COUNTEREXAMPLE while 3.04% holds. ``more
than``/``over`` before a stated change makes the check one-sided (a lower bound only),
``under``/``less than`` an upper bound only. ``nearly``/``almost``/``just under``/``not
quite`` approach the stated figure from below: the computed value may exceed it by no more
than rounding (:data:`APPROACH_ROUNDING`, 1 per cent of it, or the half-point floor of a
per-cent figure) and must be at least :data:`APPROACH_BAND` (85 per cent) of it; ``just
over``/``a little over`` are the mirror case. The rule is repeated in every check's
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
  finding's paragraph and sentence numbers are the STEM claim's ``s<paragraph>.<n>``;
* the relations read are those of pairs and their derived figures (per cent, point, fraction
  and fold changes), the paragraph's dated series (across sentences, 'rose in each year', 'the
  greatest rise'), shares and totals, and a pair's direction word with its figures in SI units
  (``rises from 4.0 Ω to 2.4 Ω`` is a COUNTEREXAMPLE, ``decreases from 5.0 kΩ to 500 Ω`` holds), except
  a verb of motion over lengths (``the ball falls from 0 m to 20 m``: a position, not a change). The
  general reading's other prose readers (absolute changes and average rates, multiples such as 'six
  times', parts of a total, differences between parties, stated lengths of years, rate trends,
  comparisons with a benchmark, 'more than any other decade', worked equations) read their figures
  with the general reading's scale words ('m' is million there), so they do not run in the SI reading;
  an approach qualifier ('nearly', 'just over') is read with the symmetric band.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass, field, replace
from fractions import Fraction
from functools import lru_cache
from typing import NamedTuple, Optional

from ..adapters.history_specialist.sentences import split_clauses, split_sentences
from ..ir.schema import Problem
from ..stem.si_reading import (
    SI_READING, SI_SCALE_UNIT, SI_SCALES, QuantReading, si_digits_pattern, si_number, si_quant_view, si_statements, si_unit, si_unit_pattern,
)

#: The general reading: the development branch's extractor, byte for byte (see the module docstring).
GENERAL = QuantReading(name="general")

_SMALL_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen")
_TENS_WORDS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_WORD_VALUES = {w: i for i, w in enumerate(_SMALL_WORDS, start=1)} | {w: 10 * (i + 2) for i, w in enumerate(_TENS_WORDS)}
_WNUM_TOKEN = "|".join(sorted((*_SMALL_WORDS, *_TENS_WORDS), key=len, reverse=True))  # longest first: 'sixty' before 'six'
#: The most number words a figure in words takes: a number below a hundred, 'hundred', and a number below a hundred ('nine hundred and
#: ninety-nine', 'nineteen hundred and twenty-nine', 'ninety-nine hundred and ninety-nine'; a scale word after it is its unit).
MAX_NUMBER_WORDS = 5
#: A number in words below a thousand: 'forty-five', 'two hundred and sixty'. Scale words (thousand, million, ...) are units. At most
#: :data:`MAX_NUMBER_WORDS` words: the unbounded repetition let every pattern that reads a figure try every length of a long run of
#: number words from each of its words ('one hundred and ' * k, 'twenty-three ' * k), n² to n³ steps, while 'and' between words is
#: also the 'and' of a total ('twenty and thirty, making fifty'); a sentence holding a longer run is reported undecided by the readers
#: (:data:`_LONG_NUMBER_RUN_RE`), never read as a figure of its first words (integration gate 1, parser-safety-2 and -7).
_WNUM = rf"(?:{_WNUM_TOKEN})(?:(?:[\s-]+and)?[\s-]+(?:{_WNUM_TOKEN}|hundred)){{0,{MAX_NUMBER_WORDS - 1}}}(?![a-z])"
#: A run of more number words than a figure in words takes (:data:`MAX_NUMBER_WORDS`), joined as the words of one figure are: such a
#: sentence states no number in those words, and the readers report it undecided instead of reading its first words.
#: Each start reads at most that many words, so the search is linear.
_LONG_NUMBER_RUN_RE = re.compile(rf"(?:{_WNUM_TOKEN})(?:(?:[\s-]+and)?[\s-]+(?:{_WNUM_TOKEN}|hundred)){{{MAX_NUMBER_WORDS}}}(?![a-z])", re.IGNORECASE)
LONG_NUMBER_RUN_REASON = (f"it holds a run of more than {MAX_NUMBER_WORDS} number words, which states no number in words, so its figures "
                           f"were not read")
#: A power of ten written after a mantissa ('2.5e3', '2.5 × 10³', '3.0 x 10^8', '1.2*10**6') or a superscript power ('10³'): a figure
#: is never read as the mantissa alone (2.5 for 2,500), and never starts at the exponent.
_SCI_TAIL = r"(?:[eE][-+−]?\d|\s?[×xX*·]\s?10(?:\^|\*\*|[⁻⁰¹²³⁴⁵⁶⁷⁸⁹])|[⁻⁰¹²³⁴⁵⁶⁷⁸⁹])"
_NOT_EXPONENT = r"(?<!\d[eE])(?<!\d[eE][-+−])(?<!\^)(?<!\^[-−{(])(?<!\^\{[-−])(?<!\*\*)(?<!\*\*[-−])"
#: Digits: thousands groups (with an optional decimal part), a plain decimal, or a decimal comma ('1,9': one or two digits after it).
#: A figure never starts inside another ('1234,567' is not '4,567'; '4.03' is not '03'): besides reading what was written, the
#: guard keeps every pattern linear on a long run of digits, since no match is attempted from each digit of the run. A figure with a
#: power of ten after it (:data:`_SCI_TAIL`) is not these digits: only the pair figures read it whole (:data:`_FIG_NUMX`).
_DIGITS = rf"(?<!\d)(?<!\d[.,]){_NOT_EXPONENT}(?:\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?|\d+(?:\.\d+)?|\d+,\d{{1,2}})(?!{_SCI_TAIL})"
#: A currency sign before a figure ('$4.03', '£600 million', 'US$13 billion'): carried with the figure as its unit of account, so a
#: figure in dollars is compared only with a figure in dollars.
_CUR = r"(?:US\$|U\.S\.\s?\$|A\$|C\$|\$|£|€|¥)"
#: The longest numeral read as a figure (far below Python's 4,300-digit integer-string limit): a longer run of digits is refused per
#: statement (``CORE-QNT-001``, 'too large to check'), never converted, so one oversized figure cannot discard the report's other checks.
MAX_FIGURE_DIGITS = 1000
_NUM = rf"({_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"  # never split a thousands group or a decimal
_NUMX = rf"(?:{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
#: A figure of a pair, a list, a continuation, a dated figure or a difference: digits, words, or scientific notation read whole
#: ('from 500 tonnes to 2.5e3 tonnes', 'to 2.5 × 10³ tonnes', 'from 5 to 1e9'; the STEM number reader gives its exact value).
_FIG_NUMX = rf"(?:(?<!\d)(?<!\d[.,]){_NOT_EXPONENT}(?:{si_digits_pattern()})|{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
_AMOUNT = rf"([-+−]?(?:{_DIGITS})|{_WNUM})(?!\d|,\d|\.\d)"  # a derived figure may carry a sign (ASCII or Unicode minus)
_PCT_UNIT = r"(?:per cent|percent(?!age)|%)"  # 'percentage points' is a difference, not a per-cent unit
_RATE_UNIT = r"per (?:thousand|1,?000|10,?000|100,?000|million|head|capita)"
_SCALE_UNIT = r"quadrillion|trillion|billion|million|thousand|trn|tn|bn|m|k"
_UNIT = rf"(?:\s*({_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes)\b)?"
#: Every unit a figure of a pair may carry ('to the dollar' is an exchange rate).
_UNIT_WORDS = rf"(?:{_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes|to (?:the|one|a) (?:US |U\.S\. |American )?(?:dollar|pound)s?)"
_QUAL = (r"(?:a little over|a little more than|a little under|slightly over|slightly more than|slightly under|slightly less than|not quite|"
         r"just over|just under|just above|just below|more than|less than|at least|at most|up to|close to|an estimated|approximately|about|around|roughly|nearly|almost|"
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
              rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:{_MONTH}\s+)?(?:\d{{1,2}},?\s+)?(?:1[0-9]{{3}}|20[0-9]{{2}})(?:(?<=0)s\b|\s*[-–/]\s*\d{{2,4}})?(?![\d])")
_DATE = rf"(?:{_DATE_BODY})?"


def _fig(i: int, *, dated: bool = False, numx: str = _FIG_NUMX, unit_words: str = _UNIT_WORDS) -> str:
    """One figure of a pair, with named groups ``q<i>`` (qualifier), ``c<i>`` (currency sign), ``n<i>`` (number), ``u<i>`` (unit),
    ``noun<i>`` and ``d<i>`` (date). ``numx`` and ``unit_words`` default to the general reading's; the SI reading passes its own."""
    date = _DATE_BODY if dated else _DATE
    # the general reading reads a minus sign written right before the figure ('and −4.6 billion dalers in 2025'; round 9, c2), never one
    # glued to a word or a figure ('1929-1932'); the SI reading's number already holds its sign
    sign = r"(?:(?<![\w.,])[−-](?=\d))?" if numx == _FIG_NUMX else ""
    return (rf"(?:(?P<q{i}>{_QUAL})\s+)?(?P<c{i}>{_CUR})?\s?{sign}(?P<n{i}>{numx})(?:\s*(?P<u{i}>{unit_words})(?!\w))?(?P<noun{i}>{_NOUN}){_PER}(?P<d{i}>{date})")


_FROM_TO_RE = re.compile(rf"\b(?:from|of)\s+{_fig(1)}\s+(?:to|and)\s+{_fig(2)}", re.IGNORECASE)
#: '... X in D1 and [reached] Y in D2': both dates are required, so a list of undated figures is never a pair.
_TO_VERB = (r"(?:reached|rose to|risen to|climbed to|grew to|increased to|jumped to|soared to|fell to|fallen to|dropped to|declined to|decreased to|"
            r"sank to|shrank to|stood at|was|were|had|bought|cost|numbered|totalled|totaled|to)")
#: The join of two dated figures, ', and' or ' and': read as one comma-led or one blank-led run (``_AND_JOIN``), never as two
#: adjacent blank runs around an optional comma (``\s*,?\s+and``), which a long run of blanks after a dated figure split in
#: every way before failing, n² steps (integration gate 2); the joins matched are the same.
_AND_JOIN = r"(?:\s*+,\s++|\s++)and\s+"
_AND_DATED_RE = re.compile(rf"(?<![\w.,]){_fig(1, dated=True)}{_AND_JOIN}(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{_fig(2, dated=True)}", re.IGNORECASE)
#: The next item of a list after a pair's second figure: ', 4.5 million in 1931 and 5.6 million in 1932'. Read after every pair; the
#: blanks before the comma or the 'and' are one possessive run (integration gate 2, critical): the leading ``\s*`` and the ``\s+`` of
#: ' and ' split a long run of blanks after a pair in every way before failing ('... to 4.5 million in 1931' + blanks + 'xx'), n² steps
#: (19.7 s per History receive at 40,000 characters). A comma or 'and' follows the whole run or nothing does, so the items are the same.
_LIST_JOIN = r"(?:\s*+,\s*(?:and\s+)?|\s++and\s+)"
_LIST_ITEM_RE = re.compile(rf"{_LIST_JOIN}(?:then\s+)?(?:to\s+)?{_fig(3, dated=True)}", re.IGNORECASE)
#: A chained continuation: '..., before climbing to 5.6 million in 1932', ', and on to 4.5 million in 1931'.
_CONT_RE = re.compile(
    rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
    rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+)?(?:further\s+|again\s+|back\s+)?to\s+{_fig(3)}"
    rf"|(?:\bbefore|\bthen|\band then|\band later|\blater)\s+(?:reaching|reached|hitting|hit|peaking at|peaked at)\s+{_fig(4)}", re.IGNORECASE)
_YEAR_SPAN_RE = re.compile(r"\b(?:from|between)\s+(1[0-9]{3}|20[0-9]{2})\s+(?:to|and)\s+(1[0-9]{3}|20[0-9]{2})\b")
_FALL_WORDS = frozenset({"fall", "decrease", "decline", "drop", "reduction", "cut", "loss", "contraction", "fell", "dropped", "declined", "decreased", "shrank", "contracted", "slumped", "collapsed", "halved", "halving",
                         "devalued", "devaluing", "devaluation", "depreciated", "depreciating", "depreciation", "reduced", "reducing", "lowered", "lowering", "cutting",
                         "lost", "losing", "loses", "shed", "shedding", "sheds", "falling", "fallen", "dropping", "declining", "decreasing", "shrinking", "shrunk", "sank", "sinking", "contracting"})
_DIR_NOUN = r"(increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction|devaluation|depreciation|revaluation|appreciation)"
_DIR_VERB = (r"(rose|grew|increased|expanded|climbed|fell|dropped|declined|decreased|shrank|contracted|slumped|collapsed|devalued|depreciated|revalued|appreciated|"
             r"reduced|cut|lowered|raised)")
_PCT_CHANGE_RE = re.compile(
    rf"(?:an?\s+)?{_DIR_NOUN}\s+of\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)"
    rf"|(?:an?\s+)?(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}\s+{_DIR_NOUN}"
    # 'rose by 5%', and 'fell 12% from $250 to $230' with no 'by' (c1 breadth F23: the change was neither decided nor named undecided)
    rf"|{_DIR_VERB}\s+(?:by\s+)?(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)",
    re.IGNORECASE)
#: 'a change of 20 per cent', 'changed by −6 per cent': the direction is the figures' own (a sign is read as stated).
_CHANGE_OF_RE = re.compile(rf"(?:(?:an?\s+)?(?:net\s+|overall\s+|total\s+)?change\s+of|\bchanged\s+by)\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)", re.IGNORECASE)
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
    rf"(?:\b(more than|over|nearly|almost|not quite|about|around|roughly|approximately|close to|at least|less than|under|up to|just over|just under|"
    rf"a little over|a little more than|slightly over|slightly more than|slightly under|slightly less than)\s+(?:an?\s+)?)?"
    rf"\b(doubl(?:ed|ing)|trebl(?:ed|ing)|tripl(?:ed|ing)|quadrupl(?:ed|ing)|halv(?:ed|ing)"
    rf"|({_DIGITS})-fold|({'|'.join(_FOLD_WORDS)})-?fold)\b", re.IGNORECASE)
_FOLD_STEMS = {"doubl": Fraction(2), "trebl": Fraction(3), "tripl": Fraction(3), "quadrupl": Fraction(4), "halv": Fraction(1, 2)}
#: An opening quotation mark right after a fold word: the word qualifies quoted words ('The doubled "we know"'), no quantity.
_QUOTE_AFTER_RE = re.compile(r"\s{0,3}[\"“‘'«]")
#: A multiple: 'six times its earlier length', 'four times as large', 'twice its 1928 level' (a fold change by another wording).
_TIMES_RE = re.compile(
    rf"\b(?:(?P<q>{_QUAL})\s+)?(?:(?P<n>(?<![\d.,])\d+(?:\.\d+)?|{_WNUM}|a hundred)\s+times|(?P<twice>twice|thrice))\s+"
    r"(?=as\b|its\b|their\b|his\b|her\b|the\b|that\b|what\b|over\b|larger\b|greater\b|bigger\b|higher\b|longer\b|more\b)", re.IGNORECASE)
#: The amount of an absolute change: a figure with an optional scale or count unit and a noun ('roughly 4,500 miles', '2.9 million
#: tonnes'), never a per-cent, point, fraction, fold or multiple (those are the relative readings above).
_ABS_AMOUNT = (rf"(?:(?P<q>{_QUAL})\s+)?(?P<cur>{_CUR})?\s?(?P<n>{_FIG_NUMX})"
               r"(?!\s*(?:per\s*cent|percent|%|percentage|points?\b|times\b|-?fold\b)|[\s-]+(?:half|halves|thirds?|quarters?|fifths?|tenths?)\b)"
               rf"(?:\s*(?P<u>{_SCALE_UNIT}|seats|votes)\b)?(?P<noun>{_NOUN})")
_RATE_TAIL = r"\s+(?:a|an|per|each|every)\s+(?P<per>year|annum|decade|month)\b|\s+(?P<annually>annually|yearly)\b"
_ABS_DIR_NOUN = r"(?P<dir>increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction|addition)"
#: 'an increase of about 6,500 miles', 'added roughly 4,500 miles', 'rose by 2.9 million tonnes', 'lost 3,000 men': an absolute change.
_ABS_CHANGE_RES = (
    re.compile(rf"(?:\ban?\s+)?(?:net\s+|total\s+|overall\s+|further\s+)?\b{_ABS_DIR_NOUN}\s+of\s+{_ABS_AMOUNT}(?:{_RATE_TAIL})?", re.IGNORECASE),
    re.compile(rf"\b(?P<dir>added|adding|adds|gained|gaining|gains|lost|losing|loses|shed|shedding|sheds)\s+(?:a\s+further\s+|another\s+|some\s+)?{_ABS_AMOUNT}(?:{_RATE_TAIL})?", re.IGNORECASE),
    re.compile(rf"\b(?P<dir>rose|grew|increased|expanded|climbed|fell|dropped|declined|decreased|shrank|contracted|slumped|collapsed|risen|grown|fallen|reduced|cut|lowered|raised)"
               rf"\s+by\s+{_ABS_AMOUNT}(?:{_RATE_TAIL})?", re.IGNORECASE),
    # 'changed by −6 per 1,000', 'a change of -$34.50 million': a sign states the direction (minus a fall, plus a rise); an unsigned amount
    # takes the direction of its figures
    re.compile(rf"\b(?P<dir>(?:an?\s+)?(?:net\s+|overall\s+|total\s+)?change\s+of|changed\s+by)\s+(?:(?P<q>{_QUAL})\s+)?(?P<sign>[-+−])?\s?(?P<cur>{_CUR})?\s?"
               rf"(?P<n>{_FIG_NUMX})"
               r"(?!\s*(?:per\s*cent|percent|%|percentage|points?\b|times\b|-?fold\b)|[\s-]+(?:half|halves|thirds?|quarters?|fifths?|tenths?)\b)"
               rf"(?:\s*(?P<u>{_SCALE_UNIT}|seats|votes)\b)?(?P<noun>{_NOUN})(?:{_RATE_TAIL})?", re.IGNORECASE),
)
#: An average rate: 'an average of 450 miles a year', 'averaging 450 miles a year', 'at an average rate of 450 miles per year'. The rate tail is
#: one group (integration gate 2): written bare, its second alternative ``\s+(annually|yearly)\b`` was an alternative of the whole pattern, so
#: ' annually' alone matched with no amount (a clause holding 'averag' and 'annually' made the arithmetic check fail internally, a TypeError,
#: and the search read a run of blanks again from each of its blanks, n² steps); an amount with 'annually' ('an average of 450 miles
#: annually') is now read as the rate it states.
_RATE_RES = (
    re.compile(rf"\b(?:an?\s+)?(?:annual\s+)?average\s+(?:annual\s+|yearly\s+)?(?:(?:rate|increase|rise|growth|gain|fall|decline|addition)\s+)?(?:of\s+)?{_ABS_AMOUNT}(?:{_RATE_TAIL})", re.IGNORECASE),
    re.compile(rf"\baverag(?:ing|ed|es)\s+{_ABS_AMOUNT}(?:{_RATE_TAIL})", re.IGNORECASE),
)
#: A comparison of a figure with a stated benchmark: 'fell short of the First Plan's original target of about 10 million tonnes of pig
#: iron (by about 10 per cent)', 'exceeded the target of 5 million tonnes by half'.
_COMPARE_RE = re.compile(
    rf"\b(?P<verb>(?:(?:fell|falling|fall|fallen|came|coming|remained|remaining|stayed|was|were|stood|lay)\s+)?(?:well\s+|far\s+|still\s+|just\s+|some\s+way\s+)?short\s+of"
    r"|exceeded|exceeding|exceeds|exceed|surpassed|surpassing|surpasses|outstripped|outstripping|outstrips|overtook|overtaking|overtakes|topped|topping|outpaced)\s+"
    rf"(?P<words>(?:[^\d;.!?]{{0,90}}?))(?:(?P<tq>{_QUAL})\s+)?(?P<tc>{_CUR})?\s?(?P<tn>{_NUMX})(?:\s*(?P<tu>{_UNIT_WORDS})(?!\w))?(?P<tnoun>{_NOUN})"
    r"(?P<tof>\s+of\s+[a-z][a-z'’-]*(?:\s+(?!by\b)[a-z][a-z'’-]*){0,3})?"
    rf"(?:\s+by\s+(?:(?P<bq>{_QUAL})\s+)?(?:(?P<bfrac>{_FRAC})|(?P<bn>{_NUMX})\s*(?P<bu>{_PCT_UNIT}|{_SCALE_UNIT}|seats|votes)?(?P<bnoun>{_NOUN})))?",
    re.IGNORECASE)
_BENCHMARK_RE = re.compile(r"\b(?:target|goal|quota|plan|forecast|projection|estimate|level|record|peak|figure|total|mark|ceiling|limit)s?\b", re.IGNORECASE)
#: The subject of a comparison that refers back to the figures of the previous sentence: 'These totals', 'The figures', 'They'.
_ANAPHOR_SUBJECT_RE = re.compile(r"^\s*(?:(?:and|but|yet|so)\s+)?(?:(?:these|those|the|such|this|that|both|all\s+(?:these|three|of\s+these))\s+(?:\w+\s+)?"
                                 r"(?:totals?|figures?|levels?|outputs?|numbers?|tonnages?|results?|increases?|gains?|amounts?|quantities|series)|they|it)\b", re.IGNORECASE)
#: A superlative over the periods of a dated series: 'more than any other decade of the period', 'fewer than in any other year'.
_ANY_OTHER_RE = re.compile(r"\b(?P<cmp>more|greater|larger|bigger|faster|higher|fewer|less|smaller|slower|lower)\s+(?:[a-z]+\s+){0,2}?than\s+(?:in\s+|during\s+)?any\s+other\s+(?P<unit>decade|year)\b", re.IGNORECASE)
_DECADE_TOKEN_RE = re.compile(r"\b(?:the\s+)?(?P<d>1[0-9]{2}0|20[0-9]0)s\b")
#: A direction word governing a pair with no stated change: 'pig iron rising from X to Y', 'output fell from X to Y'.
_PAIR_DIR_RE = re.compile(r"\b(rose|rising|risen|rises|grew|growing|grown|grows|increased|increasing|increases|climbed|climbing|climbs|expanded|expanding|jumped|jumping|soared|soaring|"
                          r"went\s+up|revalued|revaluing|appreciated|appreciating|raised|raising|"
                          r"fell|falling|fallen|falls|declined|declining|declines|dropped|dropping|drops|decreased|decreasing|decreases|shrank|shrinking|shrunk|slumped|"
                          r"slumping|collapsed|sank|sinking|contracted|contracting|went\s+down|devalued|devaluing|depreciated|depreciating|reduced|reducing|lowered|lowering|"
                          r"cut|cutting)\b", re.IGNORECASE)
#: A direction word directly before a pair's 'from', with at most two adverbs between: 'pig iron rising from', 'rose sharply from'.
_PAIR_DIR_BEFORE_RE = re.compile(_PAIR_DIR_RE.pattern + r"(?:\s+(?:[a-z]+ly|again|further|back|still|then|in\s+turn))?(?:\s+(?:[a-z]+ly|again|further|back))?\s+$", re.IGNORECASE)
_RISE_DIR_WORDS = frozenset("rose rising risen rises grew growing grown grows increased increasing increases climbed climbing climbs expanded expanding jumped jumping soared soaring "
                            "revalued revaluing appreciated appreciating raised raising".split()) | {"went up"}
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
def _share_pattern(num: str, unit: str) -> str:
    r"""'20 per cent of 300 million, or 60 million': a share of a total and the part it states. Every blank run is read once (integration
    gate 2): the runs after 'of', 'the' and an approximation word, and before and after the separator (a comma, 'or', 'is', '=', a
    parenthesis), were adjacent ``\s*``/``\s+`` runs around optional words, which a long run of blanks after 'of' or after the total
    split in every way before failing, n² to n³ steps (0.72 s at 2,000 blanks, hours at 400,000). Each run is followed by a word, a mark
    or a figure, never by a blank, so the possessive runs give the same matches; a separator word needs a blank before it, as before."""
    return (rf"\b{num}\s*{_PCT_UNIT}\s+of\s++(?:the\s++)?(?:(?:about|around|roughly)\s*+)?{num}{unit}(?:\s+[a-z]+){{0,2}}?"
            rf"\s*+(?:,\s*+(?:(?:or|i\.e\.|that is)\s*+)?|(?<=\s)(?:or|was|is|=|that is|i\.e\.)\s*+|\(\s*+)(?:(?:about|around|roughly|some)\s*+)?{num}{unit}")


_SHARE_RE = re.compile(_share_pattern(_NUM, _UNIT), re.IGNORECASE)


def _tfig(i: int) -> str:
    """A figure of a stated total: an optional currency sign, the number, a unit and one noun ('3.2 billion dollars', '$2.7 billion')."""
    return (rf"(?P<c{i}>{_CUR})?\s?(?P<n{i}>{_NUMX})(?:\s*(?P<u{i}>{_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes)\b)?"
            rf"(?:\s+(?P<w{i}>(?!(?:and|plus|to|in|of|a|an|the|gave|giving|making|made|for|with|or|by|on|at)\b)[a-z]+))?")


#: The first letters of a stated total's keywords: checked before the keyword alternation at each position of the gap after the second
#: figure, so a position no keyword starts at costs one test, not one per keyword (the matches are unchanged).
_TOTAL_KEYWORD_START = r"(?=[atimg])"
_TOTAL_RE = re.compile(rf"{_tfig(1)}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?(?:(?:about|around|roughly|some|nearly)\s+)?{_tfig(2)}[^.;]{{0,60}}?"
                       rf"{_TOTAL_KEYWORD_START}(?:a total of|totalling|totaling|together|in total|making|giving|totals?)\s+(?:(?:about|around|roughly|some|nearly)\s+)?{_tfig(3)}", re.IGNORECASE)
#: Every keyword of a stated total holds one of these words: a sentence holding none of them states no total, and the total patterns
#: are not searched in it (:func:`_search_total`; the result is the same).
_TOTAL_HINT_RE = re.compile(r"total|together|making|giving", re.IGNORECASE)


def _search_total(pattern: "re.Pattern[str]", text: str) -> "Optional[re.Match[str]]":
    """``pattern.search(text)`` for a total pattern, skipped when ``text`` holds no keyword of a total (:data:`_TOTAL_HINT_RE`)."""
    return pattern.search(text) if _TOTAL_HINT_RE.search(text) else None
#: A full stop followed by a lower-case word inside one parser sentence: the arithmetic reading splits there too.
_LOWER_CONTINUATION_RE = re.compile(r"[.?!][\"”’')\]»]*\s+[a-z]")
#: Where one part of a clause ends and the next begins between two pairs.
#: Read from a comma or from the first blank of a run (``(?<!\s)``, possessive runs; integration gate 2): ``\s+and`` was tried again from
#: every blank of a long run between two pairs, k² steps. :func:`_segments` reads it on the text between the pairs, as the scan between
#: their offsets read it.
_SEG_SEP_RE = re.compile(r",\s*+(?:and|while|whereas|but|yet)\b|;|(?<!\s)\s++and\s+", re.IGNORECASE)
_EDGE_SEP_RE = re.compile(r",\s*(?:and|while|whereas|but|yet)\b|;", re.IGNORECASE)
_MONTH_INDEX = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), start=1)}
_SCALE = {"thousand": 10**3, "k": 10**3, "million": 10**6, "m": 10**6, "billion": 10**9, "bn": 10**9, "trillion": 10**12, "tn": 10**12, "trn": 10**12, "quadrillion": 10**15}
_LOWER_ONLY = frozenset({"more than", "over", "at least"})
_UPPER_ONLY = frozenset({"less than", "under", "at most", "up to"})
#: 'nearly', 'almost', 'just under', 'not quite' (and their kin) approach the stated figure from below: it is an upper bound the
#: computed value may not exceed beyond rounding, and the computed value lies within a band under it.
_APPROACH_BELOW = frozenset({"nearly", "almost", "just under", "just below", "not quite", "a little under", "slightly under", "slightly less than"})
#: 'just over', 'a little over', 'slightly more than' are the mirror case: a lower bound with a band above it.
_APPROACH_ABOVE = frozenset({"just over", "just above", "a little over", "a little more than", "slightly over", "slightly more than"})
#: The band of an approach qualifier: 'nearly X' holds for a computed value from 85 per cent of X up to X; 'just over X' from X up to X / 0.85.
APPROACH_BAND = Fraction(85, 100)
#: Rounding allowed past the bound an approach qualifier sets: 1 per cent of the stated figure (or the half-point floor of a per-cent figure).
APPROACH_ROUNDING = Fraction(1, 100)
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
        re.compile(rf"(?<![\w.,]){fig(1, True)}{_AND_JOIN}(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{fig(2, True)}", re.IGNORECASE),
        re.compile(rf"{_LIST_JOIN}(?:then\s+)?(?:to\s+)?{fig(3, True)}", re.IGNORECASE),
        re.compile(
            rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
            rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+)?(?:further\s+|again\s+|back\s+)?to\s+{fig(3)}"
            rf"|(?:\bbefore|\bthen|\band then|\band later|\blater)\s+(?:reaching|reached|hitting|hit|peaking at|peaked at)\s+{fig(4)}", re.IGNORECASE),
        re.compile(_share_pattern(num, unit), re.IGNORECASE),
        re.compile(rf"{num}{unit}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{num}{unit}[^.;]{{0,60}}?{_TOTAL_KEYWORD_START}(?:a total of|totalling|together|in total|making|giving|totals?)\s+(?:about|around|roughly)?\s*{num}{unit}", re.IGNORECASE),
    )


#: SI reading pieces: scientific notation and a sign on a figure; spelled-out scale words only; unit symbols of the STEM table.
#: A figure in scientific notation starts only where no digit precedes (``(?<!\d)``): from a digit inside a run the mantissa ends
#: where the run's own mantissa ends, so the matches are those of the unguarded alternation, read in linear time (from every digit
#: of a long run, '0b111...1', the mantissa read the rest of the run before failing, n² steps; integration gate 1,
#: parser-safety-8).
_SI_DIGITS = rf"(?<!\d)(?:{si_digits_pattern()})|{_DIGITS}"
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
    kind: str                 # percent_change | points_change | fraction_change | fold_change | abs_change | rate_change | comparison | pair_direction
                              # | series_monotonic | series_extreme | share | total
    sentence: str
    problem: Problem
    expected_if_consistent: str = "ENTAILED"
    rule: str = ""            # the tolerance rule applied, for the receipt
    basis: str = ""           # for a relation stated across sentences: where its year and figures were read
    phrase: str = ""          # the derived phrase or relation read ('added roughly 4,500 miles'), so a finding can name the claim that states it
    failure_severity: str = "error"  # 'warning' for a check that rests on a reading the report did not state (INT-SUBJ-004 when it fails)


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


#: A figure written in scientific notation (an e-form, a times sign before a power of ten, a superscript exponent).
_SCI_NUM_RE = re.compile(r"\d[eE][-+]?\d|\d\s?[×xX*·]\s?10|\d\^|\d\*\*|\d[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]")


class FigureTooLarge(ValueError):
    """A figure of more than :data:`MAX_FIGURE_DIGITS` digits: the statement that holds it is reported undecided."""


_TOO_LARGE_REASON = f"a figure in it has more than {MAX_FIGURE_DIGITS:,} digits and is too large to check"
#: The most derived figures, and the most pairs of figures, a clause is read for (integration gate 2): every derived figure of a clause reads
#: the clause again (its decade, its years, its stated figures, its working), and every pair looks through the clause's derived figures, so a
#: clause of thousands ('a rise of 20 per cent a rise of 20 per cent ...') cost n² steps (8.7 s at 10,000 characters). A real sentence
#: states a few (the most in the recorded rounds is 2 and 3); a clause over the bound is reported undecided as a whole, never read in part.
_MAX_CLAUSE_FIGURES = 32
_TOO_MANY_REASON = (f"it states more than {_MAX_CLAUSE_FIGURES} derived figures or pairs of figures, more than a sentence is read for, so its "
                    f"arithmetic was not read")


def _number(num: str) -> Fraction:
    """Exact value of a figure written in digits (thousands separators, decimals, a decimal comma, a sign) or in words.
    Raises :class:`FigureTooLarge` for a numeral of more than :data:`MAX_FIGURE_DIGITS` digits."""
    if sum(ch.isdigit() for ch in num) > MAX_FIGURE_DIGITS:
        raise FigureTooLarge(f"figure of {sum(ch.isdigit() for ch in num)} digits")
    s = num.strip().replace("−", "-").lstrip("+")
    if _SCI_NUM_RE.search(s):
        v = si_number(s)  # scientific notation read whole ('2.5e3', '2.5 × 10³'), exactly, by the STEM number reader
        if v is None:
            raise FigureTooLarge(f"figure {s[:40]!r} outside the number reader's bounds")
        return v
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
    q = " ".join((qualifier or "").lower().split())
    if q in _APPROACH_BELOW:
        return "below"
    if q in _APPROACH_ABOVE:
        return "above"
    return "lower" if q in _LOWER_ONLY else "upper" if q in _UPPER_ONLY else "both"


_SIDE_TEXT = {
    "lower": " (one-sided: the stated figure is a lower bound)",
    "upper": " (one-sided: the stated figure is an upper bound)",
    "below": (" (approached from below, 'nearly'/'almost'/'just under': the computed value may not exceed the stated figure by more than 1 per cent "
              "of it, or the half-point floor of a per-cent figure, and must be at least 85 per cent of it)"),
    "above": (" (approached from above, 'just over'/'a little over': the computed value may not fall below the stated figure by more than 1 per cent "
              "of it, or the half-point floor of a per-cent figure, and must be at most the stated figure divided by 0.85)"),
}


def _rule_text(tolerance: Fraction, floor: Fraction, side: str) -> str:
    return TOLERANCE_RULE.format(tol=f"{float(tolerance) * 100:g}",
                                 floor=f", or within {float(floor):g} percentage points of it" if floor else "",
                                 side=_SIDE_TEXT.get(side, ""))


def _within(expr: dict, stated: Fraction, tolerance: Fraction, floor: Fraction = Fraction(0), side: str = "both") -> dict:
    """``expr`` within the tolerance band around itself that contains ``stated``:
    |computed - stated| <= tolerance * computed, or <= floor. Linear in ``expr``. An approach
    qualifier sets its own band: 'nearly X' (``below``) holds for a computed value from
    ``APPROACH_BAND`` * X up to X plus rounding (``APPROACH_ROUNDING`` of X, or the floor); 'just
    over X' (``above``) from X less rounding up to X / ``APPROACH_BAND``."""
    if side == "below":
        lo = stated * APPROACH_BAND
        hi = max(stated * (1 + APPROACH_ROUNDING), stated + floor)
    elif side == "above":
        lo = min(stated * (1 - APPROACH_ROUNDING), stated - floor)
        hi = stated / APPROACH_BAND
    else:
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

#: The band of a per cent change written with decimals ('an increase of 3.40%'): the figure states its own precision, so instead of
#: the half-point floor it passes within h + tau * |C| + k * |C + 100| of the computed change C (or within the relative tolerance):
#: h is half a unit in its last written digit, tau = 1/100 (the STEM rule for '='), and k * |C + 100| bounds what rounding the
#: pair's figures at their written precision can move the change by (k = (r_a + r_b) / (1 - r_a) for the figures' relative half-units
#: r_a, r_b; |C + 100| is 100 times the later figure over the earlier, so the band is computed by the engine, not in Python).
PRECISION_RULE = ("the per cent is written with decimals, so it states its own precision: it must lie within {tol}% of the value computed from "
                  "the report's own figures, or within half a unit in its last written digit plus 1% of the computed value plus what rounding the "
                  "pair's figures at their written precision can move the change by (no half-point floor)")
PRECISION_TAU = Fraction(1, 100)
_WRITTEN_FIGURE_RE = re.compile(r"\d[\d,]*+(?:\.(\d++))?")


def _written_places(text: str, value: Optional[Fraction] = None) -> Optional[int]:
    """The decimal places of the written figure of ``text`` (of value ``value`` when given): None when no figure in digits is found."""
    for m in _WRITTEN_FIGURE_RE.finditer(text):
        try:
            v = Fraction(m.group(0).replace(",", ""))
        except (ValueError, ZeroDivisionError):
            continue
        if value is None or v == abs(value):
            return len(m.group(1) or "")
    return None


def _relative_half_unit(shown: str) -> Optional[Fraction]:
    """Half a unit in the last written digit of the figure ``shown`` opens with ('112.0', '$4.03 billion in 2020'), relative to the
    figure's written value; None when the figure is not written in digits or is zero."""
    m = _WRITTEN_FIGURE_RE.search(shown)
    if m is None:
        return None
    try:
        v = Fraction(m.group(0).replace(",", ""))
    except (ValueError, ZeroDivisionError):
        return None
    if v == 0:
        return None
    return Fraction(1, 2) / Fraction(10) ** len(m.group(1) or "") / v


def _precision_band(change: dict, stated: Fraction, tolerance: Fraction, places: int, values: "_Values") -> Optional[dict]:
    """:data:`PRECISION_RULE` for ``change`` (a per cent change expression) against ``stated``, or None when the pair's figures carry
    no written precision (the default band then applies)."""
    ra, rb = _relative_half_unit(values.shown_a), _relative_half_unit(values.shown_b)
    if ra is None or rb is None or ra >= 1:
        return None
    h = Fraction(1, 2) / Fraction(10) ** places
    k = (ra + rb) / (1 - ra)
    ratio = {"op": "add", "args": [change, _real(Fraction(100))]}
    slack = {"op": "add", "args": [_real(h), {"op": "mul", "args": [_real(PRECISION_TAU), _abs(change)]}, {"op": "mul", "args": [_real(k), _abs(ratio)]}]}
    diff = {"op": "sub", "left": change, "right": _real(stated)}
    relative = {"op": "le", "left": _abs(diff), "right": {"op": "mul", "args": [_real(tolerance), _abs(change)]}}
    return {"op": "or", "args": [relative, {"op": "le", "left": _abs(diff), "right": slack}]}


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
    cur: str = ""             # a currency sign written before the figure ('$', '£', 'US$')

    @property
    def year(self) -> Optional[int]:
        """The year that dates the figure; None for a decade ('in the 1870s' dates a decade's total, not a year's figure)."""
        m = re.search(r"(1[0-9]{3}|20[0-9]{2})(s\b)?", self.date)
        return int(m.group(1)) if m and not m.group(2) else None

    @property
    def annual(self) -> bool:
        """Dated by a year alone (not a month, a day, a range or a part of the year): a point of an annual series."""
        d = self.date
        return (self.year is not None and not re.search(_MONTH, d, re.IGNORECASE) and not re.search(r"(1[0-9]{3}|20[0-9]{2})\s*[-–/]\s*\d", d)
                and not re.search(r"\b(?:early|late|mid|end|start|beginning|middle)\b", d, re.IGNORECASE) and not re.search(r"\d{1,2}(?:st|nd|rd|th)?\s+(?:1[0-9]{3}|20[0-9]{2})", d))


def _fig_of(m: "re.Match[str]", i: int) -> _Fig:
    cur = _cur_key(m.group(f"c{i}") or "")
    num = m.group(f"n{i}")
    if num and num[:1].isdigit() and _signed_before(m.string, m.start(f"c{i}") if m.group(f"c{i}") else m.start(f"n{i}")):
        num = "-" + num  # a figure written with a minus sign ('0.2 billion in 2024 and −4.6 billion in 2025'): its value is negative (round 9, c2)
    return _Fig(num, m.group(f"u{i}"), (m.group(f"noun{i}") or "").strip(), (m.group(f"d{i}") or "").strip(), m.start(f"n{i}"), m.end(), cur)


def _signed_before(text: str, at: int) -> bool:
    """A minus sign written right before the figure at ``at`` ('−4.6', '(−4.6', ' -4.6'), itself after a blank, a bracket or the start: the
    figure is negative. A hyphen glued to a word or a figure ('1929-1932', 'post-1945') is no sign."""
    if at <= 0 or text[at - 1] not in "−-":
        return False
    return at - 1 == 0 or text[at - 2] in " \t\n(["


#: Currency signs and the noun that names the same currency ('$4.03' and '4.03 dollars' are one unit of account).
_CUR_NOUNS = {"$": ("dollar",), "£": ("pound", "sterling"), "€": ("euro",), "¥": ("yen", "yuan"), "A$": ("dollar",), "C$": ("dollar",)}


def _cur_key(sign: str) -> str:
    """'US$', 'U.S. $' and '$' are one currency sign."""
    sign = sign.replace(" ", "").replace("U.S.", "US")
    return "$" if sign in ("US$", "$") else sign


def _cur_of_noun(noun: str) -> str:
    """The currency a figure's noun names ('dollars' -> '$'), or ''."""
    last = noun.lower().split()[-1].rstrip("s") if noun.split() else ""
    for sign, names in _CUR_NOUNS.items():
        if last in names:
            return sign
    return ""


def _cur_compatible(cur_a: str, noun_a: str, cur_b: str, noun_b: str) -> bool:
    """Two figures are in the same unit of account: the same currency sign, a sign and the noun naming that currency ('$13 billion'
    and '13 billion dollars'), or no currency on either side. A sign on one figure and a noun naming something else on the other
    ('$4 billion' and '4 billion marks') are not comparable; a sign beside a bare figure carries over ('from $4 billion to 6 billion')."""
    a = cur_a or _cur_of_noun(noun_a)
    b = cur_b or _cur_of_noun(noun_b)
    if a and b:
        return a == b
    if a and not b:
        return not noun_b
    if b and not a:
        return not noun_a
    return True


@dataclass
class _Pair:
    start: int
    end: int
    before: _Fig
    after: _Fig
    tail: list = field(default_factory=list)   # list figures after the second figure, in order
    via: str = ""      # the written arithmetic the figure after 'to' opens, whose stated result is ``after`` ('$2.00 − $0.60')
    arith: str = ""    # the written arithmetic the figure after 'to' opens when it states no result: the pair is not read

    @property
    def last(self) -> _Fig:
        return self.tail[-1] if self.tail else self.after


@dataclass(frozen=True)
class _Derived:
    start: int
    end: int
    kind: str                 # percent_change | points_change | fraction_change | fold_change | change | abs_change | rate_change
    words: str
    direction: Optional[str]
    stated: Fraction
    side: str
    percentage_points: bool = False
    unit: Optional[str] = None   # abs_change / rate_change: the amount's unit word (a scale or count unit), if any
    noun: str = ""               # abs_change / rate_change: the amount's noun ('miles', 'tonnes')
    per: str = ""                # rate_change: the period of the rate ('year', 'decade', 'month')
    soft: bool = False           # a verb of gain or loss ('lost 3,000 men', 'added 1.2 million'): a count unless figures are stated to read it against
    cur: str = ""                # abs_change / rate_change: the amount's currency sign ('an increase of about $1.4 billion')


_FRACTION_HINT_RE = re.compile(r"half|third|quarter|fifth|tenth")
_FOLD_HINT_RE = re.compile(r"fold|doubl|trebl|tripl|quadrupl|halv")
#: A figure of a pair is digits or a number word; a clause with neither holds no pair.
_FIGURE_HINT_RE = re.compile(rf"\d|\b(?:{_WNUM_TOKEN})\b", re.IGNORECASE)
#: A clause with none of these states no derived figure (a cheap test before the five patterns run).
_DERIVED_HINT_RE = re.compile(r"per\s*cent|percent|%|points?\b|half|third|quarter|fifth|tenth|fold|doubl|trebl|tripl|quadrupl|halv|times|twice|thrice|average|averag|"
                              r"\b(?:increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction|addition)\s+of\b|\badd(?:ed|ing|s)\b|\bgain(?:ed|ing|s)\b|"
                              r"\blos(?:t|ing|es)\b|\bshed|\bby\s+(?:about\s+|roughly\s+|some\s+|nearly\s+|almost\s+|around\s+|over\s+|more\s+than\s+)?(?:US)?[$£€¥]?\d|"
                              r"\bchange\s+of\b|\bchanged\s+by\b", re.IGNORECASE)
_ABS_HINT_RE = re.compile(r"\b(?:increase|rise|fall|decrease|decline|drop|growth|reduction|cut|gain|loss|expansion|contraction|addition|change)\s+of\b|\badd(?:ed|ing|s)\b|\bgain(?:ed|ing|s)\b|\blos(?:t|ing|es)\b|\bshed|\bby\s", re.IGNORECASE)


def _derived_phrases(clause: str, si: bool = False) -> list[_Derived]:
    """Every stated derived figure of ``clause``, in order of position. In the SI reading a fold may be repeated ('halved
    twice' is a factor of 1/4, 'doubled three times' 8); the kinds the SI reading reads are per cent, point, fraction and fold
    changes (multiples, absolute changes and average rates read their amounts with the general reading's scale words, where 'm'
    is a million), and an approach qualifier ('nearly', 'just over') is read with the symmetric band there."""
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
        direction = "fall" if value < 0 else "rise" if m.group(2).strip().startswith("+") else None  # an explicit sign states the direction
        out.append(_Derived(m.start(), m.end(), "change", m.group(0).strip(), direction, abs(value), _side(m.group(1))))
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
        if _QUOTE_AFTER_RE.match(clause, m.end()):
            continue  # a fold word that qualifies a quotation ('The doubled "we know"' repeats a phrase; round 9, c1 stem-integration 33)
        end, words = m.end(), m.group(0).strip()
        if si:
            rep = _REPEAT_RE.match(clause, m.end())
            if rep:
                times = 2 if rep.group(1) else (_REPEAT_WORDS.get(rep.group(2).lower()) or int(rep.group(2)))
                if 1 <= times <= _MAX_REPEAT:
                    factor, end, words = factor ** times, rep.end(), clause[m.start():rep.end()].strip()
        out.append(_Derived(m.start(), end, "fold_change", words, None, factor, _side(m.group(1))))
    if si:  # the SI reading: no multiples, absolute changes or average rates; an approach qualifier is read with the symmetric band
        out = [d if d.side not in ("below", "above") else _Derived(d.start, d.end, d.kind, d.words, d.direction, d.stated, "both", d.percentage_points)
               for d in out]
        out.sort(key=lambda d: d.start)
        return out
    for m in (_TIMES_RE.finditer(clause) if ("times" in low or "twice" in low or "thrice" in low) else ()):
        if m.group("twice"):
            factor = Fraction(2) if m.group("twice").lower() == "twice" else Fraction(3)
        else:
            raw = m.group("n").lower()
            factor = Fraction(100) if raw in ("a hundred",) else _number(raw)
        if factor <= 1:
            continue
        out.append(_Derived(m.start(), m.end(), "fold_change", m.group(0).strip(), None, factor, _side(m.group("q"))))
    # the characters of the phrases read so far, marked once: a match is skipped when it shares a character with one of them (integration
    # gate 2: each match was tested against every phrase read before it, n² steps on a clause of thousands of rates)
    taken = bytearray(len(clause))
    for d in out:
        taken[d.start: d.end] = b"\x01" * (d.end - d.start)
    if "averag" in low:
        for rx in _RATE_RES:
            for m in rx.finditer(clause):
                if taken.find(1, m.start(), m.end()) >= 0 or _year_like(m.group("n"), m.group("u") or m.group("cur")):
                    continue
                amount = _frac(m.group("n"), m.group("u"))
                direction = _direction(m.group(0).split()[0]) if re.search(r"\b(?:fall|decline|drop|loss|cut|reduction)\b", m.group(0), re.IGNORECASE) else None
                out.append(_Derived(m.start(), m.end(), "rate_change", m.group(0).strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                    noun=(m.group("noun") or "").strip(), per=(m.group("per") or "year").lower(), cur=_cur_key(m.group("cur") or "")))
                taken[m.start(): m.end()] = b"\x01" * (m.end() - m.start())
    if _ABS_HINT_RE.search(clause):
        for rx in _ABS_CHANGE_RES:
            for m in rx.finditer(clause):
                if taken.find(1, m.start(), m.end()) >= 0 or _year_like(m.group("n"), m.group("u") or m.group("cur")):
                    continue
                amount = _frac(m.group("n"), m.group("u"))
                if amount <= 0:
                    continue
                word = m.group("dir").lower()
                direction: Optional[str] = "fall" if word in _FALL_WORDS else "rise"
                if "change" in word:
                    sign = m.groupdict().get("sign") or ""
                    direction = "fall" if sign in ("-", "−") else "rise" if sign == "+" else None
                if m.group("per") or m.group("annually"):
                    out.append(_Derived(m.start(), m.end(), "rate_change", m.group(0).strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                        noun=(m.group("noun") or "").strip(), per=(m.group("per") or "year").lower(), cur=_cur_key(m.group("cur") or "")))
                else:
                    soft = word in ("added", "adding", "adds", "gained", "gaining", "gains", "lost", "losing", "loses", "shed", "shedding", "sheds")
                    out.append(_Derived(m.start(), m.end(), "abs_change", m.group(0).strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                        noun=(m.group("noun") or "").strip(), soft=soft, cur=_cur_key(m.group("cur") or "")))
                taken[m.start(): m.end()] = b"\x01" * (m.end() - m.start())
    out.sort(key=lambda d: d.start)
    return out


#: An operand of written arithmetic after a pair's later figure: a figure (a currency sign, a sign, brackets and up to two unit
#: words around it allowed: '$0.60', '(0.60)', '0.60 litres').
_ARITH_OPERAND = r"\(?[ \t]?(?:US)?[$£€¥]?[ \t]?[-−]?\d[\d,.]*(?:[ \t]?%)?\)?(?:[ \t][A-Za-zΩµμ°]{1,12}\.?){0,2}"
#: Written arithmetic opened by the figure after 'to' ('from $1.60 to $2.00 − $0.60 = $1.40'): up to two unit words after the figure,
#: then an operator (the operators of :data:`_OPERATOR_BETWEEN_RE`: a hyphen or a dash only with a blank on each side) and an operand,
#: repeated. Anchored at the end of the pair, so each stretch of arithmetic is read once.
_ARITH_CHAIN_RE = re.compile(rf"(?:[ \t][A-Za-zΩµμ°]{{1,12}}\.?){{0,2}}(?:[ \t]?(?:[+×÷*/^·]|[ \t][-–][ \t]|−)[ \t]?{_ARITH_OPERAND})+")
_ARITH_EQ_RE = re.compile(r"[ \t]*[=≈][ \t]*")
#: The reason a pair whose later figure opens written arithmetic with no stated result is not read (``CORE-QNT-001``).
ARITH_ENDPOINT_REASON = ("the figure after 'to' opens written arithmetic that states no result, so the figure the change ends at is not stated "
                         "and the pair was not read")


@lru_cache(maxsize=1)
def _si_lone_fig() -> "re.Pattern[str]":
    """The SI reading's figure pattern for one figure (the general reading's is :data:`_LONE_FIG_RE`)."""
    return re.compile(_fig(1, numx=_SI_NUMX, unit_words=_SI_UNIT_WORDS), re.IGNORECASE)


def _arith_endpoint(clause: str, p: _Pair, pat: _Patterns) -> _Pair:
    """``p`` read with written arithmetic after its later figure: 'falls from $1.60 to $2.00 − $0.60 = $1.40' ends at the arithmetic's
    stated result, $1.40, not at $2.00, the arithmetic's first operand (integration gate 1: the price producers keep in ec-e1 was read as
    a fall from $1.60 to $2.00 and refuted). The pair's later figure is then the stated result (``via`` records the arithmetic: a check
    resting on it is read through the arithmetic, a reading the report did not state as a figure after 'to', so its failure is a warning);
    arithmetic with no stated result leaves the pair unread (``arith``, reported undecided). ``p`` itself when no arithmetic follows."""
    chain = _ARITH_CHAIN_RE.match(clause, p.end)
    if chain is None:
        return p
    expr = " ".join((p.after.cur + clause[p.after.start:chain.end()]).split()).rstrip(" .,;:")
    eq = _ARITH_EQ_RE.match(clause, chain.end())
    lone = _LONE_FIG_RE if pat is _GENERAL_PATTERNS else _si_lone_fig()
    res = lone.match(clause, eq.end()) if eq is not None and eq.group(0).strip() else None
    if res is None or _ARITH_CHAIN_RE.match(clause, res.end()) is not None:
        return replace(p, arith=expr)
    return _Pair(p.start, res.end(), p.before, _fig_of(res, 1), [], via=expr)


#: The label of the case a figure of a from-to pair belongs to, written between the figure and the 'to' or 'and' of the pair ('from 5.4 m³ s⁻¹ in
#: Storm 1 to 16.2 m³ s⁻¹ in Storm 2', 'from 40 at site A to 120 at site B', 'from 5.4 (Storm 1) to 16.2 (Storm 2)'): a preposition and a
#: word that is no month, with a number of one or two digits or a capital letter after it, or the same in brackets. The pair reader reads the
#: clause with such a label blanked, at the same length so that every offset holds: the label names the figure's case, never a date or a unit
#: (round 9 second pass, c2 ess-p9c s8.2 and ge-p9c g3.2: the stated change was named undecided as if its sentence stated no figures). Read only
#: right after a word character or a sign of a unit, every run possessive or bounded: linear in the clause.
_PAIR_LABEL_RE = re.compile(
    r"(?<=[\w%³²¹⁰⁻])(?:\s++(?:in|for|at|on)\s++(?:the\s++)?|\s*+\(\s*+)"
    r"(?!(?:January|February|March|April|May|June|July|August|September|October|November|December)\b)[A-Za-z][a-z]{1,15}\s++(?:\d{1,2}|[A-Z])\b(?:\s*+\))?"
    r"(?=\s++(?:to|and|until)\s)")


def _blank_pair_labels(clause: str) -> str:
    """``clause`` with each case label between a figure of a pair and its 'to' or 'and' blanked (:data:`_PAIR_LABEL_RE`), at the same length."""
    if "to " not in clause and "and " not in clause:
        return clause
    return _PAIR_LABEL_RE.sub(lambda m: " " * (m.end() - m.start()), clause)


def _pairs(clause: str, pat: _Patterns = _GENERAL_PATTERNS) -> list[_Pair]:
    """Every pair of figures of ``clause`` (from/to with its list and continuations, then 'X in D1 and Y in D2'), in order.
    ``pat`` holds the reading's figure patterns (the general reading's by default). A later figure that opens written arithmetic
    ends the pair at the arithmetic's stated result (:func:`_arith_endpoint`). A case label after a figure ('in Storm 1', '(site A)') is
    read as no part of the pair (:func:`_blank_pair_labels`; offsets unchanged).

    Linear in the pairs: a continuation's earlier pair (the first of the pairs ending latest before it) and whether a match
    overlaps a pair already read are looked up by bisection, never by reading every pair again (integration gate 1: thousands of
    continuations in one sentence read the list of pairs once for each, 4.3 s for 160,000 characters). The pairs are those the
    scan of every pair gives."""
    pairs: list[_Pair] = []
    if not _FIGURE_HINT_RE.search(clause):
        return pairs
    clause = _blank_pair_labels(clause)
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
        if not p.tail:
            p = _arith_endpoint(clause, p, pat)
        pairs.append(p)
    # the from/to pairs in order of their starts (finditer), with the largest end so far: a match (s, e) overlaps one of them when
    # one that starts before e ends after s
    covered = _Covered(pairs)
    ends = sorted((p.end, i) for i, p in enumerate(pairs))  # every pair's end with its index: the continuation's earlier pair
    latest = -1  # the largest end of the continuations read so far (each starts after the one before it)
    for m in pat.cont.finditer(clause):
        if covered.overlaps(m.start(), m.end()) or latest > m.start():
            continue
        k = bisect_right(ends, (m.start(), len(pairs))) - 1
        if k < 0:
            continue  # no pair ends before the continuation
        first = bisect_left(ends, (ends[k][0], -1))  # the first pair, in the list's order, of that largest end (``max`` keeps it)
        p = _Pair(m.start(), m.end(), pairs[ends[first][1]].last, _fig_of(m, 3 if m.group("n3") else 4))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        if not p.tail:
            p = _arith_endpoint(clause, p, pat)
        pairs.append(p)
        insort(ends, (p.end, len(pairs) - 1))
        latest = max(latest, p.end)
    covered = _Covered(sorted(pairs, key=lambda x: x.start))  # from/to pairs and continuations: their starts interleave
    latest = -1  # the largest end of the dated pairs read so far
    for m in pat.and_dated.finditer(clause):
        if covered.overlaps(m.start(), m.end()) or latest > m.start():
            continue
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        pairs.append(p)
        latest = max(latest, p.end)
    pairs.sort(key=lambda p: p.start)
    return pairs


class _Covered:
    """The spans of pairs read, in order of their starts, with the largest end among each prefix: whether a span (s, e)
    overlaps one of them (some pair with start < e and end > s) is one bisection."""

    def __init__(self, ordered: list[_Pair]) -> None:
        self.starts = [p.start for p in ordered]
        self.reach: list[int] = []
        best = -1
        for p in ordered:
            best = max(best, p.end)
            self.reach.append(best)

    def overlaps(self, s: int, e: int) -> bool:
        k = bisect_left(self.starts, e) - 1  # the pairs that start before e
        return k >= 0 and self.reach[k] > s


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
    if k1 == "rate" and k2 == "rate" and _xrate_unit_conflict(u1, u2):
        return u1, u2, False  # 'from 4.2 to the dollar to 20 to the pound': exchange rates of two currencies, or a rate per head
    return u1, u2, True


@dataclass(frozen=True)
class _Values:
    a: Fraction
    b: Fraction
    shown_a: str
    shown_b: str
    pct: bool                 # both figures are per-cent shares
    year_a: Optional[int] = None
    year_b: Optional[int] = None
    unit: Optional[str] = None   # the pair's unit after shared-unit elision (the later figure's)
    noun: str = ""               # the pair's noun, when a figure carries one ('miles')
    cur: str = ""                # the pair's currency ('$' for '$4.03' or '4.03 dollars'), when a figure carries one


def _shown(fig: _Fig, unit: Optional[str]) -> str:
    return " ".join(x for x in (f"{fig.cur}{fig.num}", unit or fig.noun, fig.date) if x)


def _values(before: _Fig, after: _Fig) -> tuple[Optional[_Values], str]:
    """The two figures of a pair as exact values, or None and the reason they cannot be compared."""
    u1, u2, ok = _comparable(before.unit, after.unit, before.noun if not before.cur or after.cur else "", after.noun if not after.cur or before.cur else "")
    if not ok or not _cur_compatible(before.cur, before.noun, after.cur, after.noun):
        return None, f"the units of '{_shown(before, before.unit)}' and '{_shown(after, after.unit)}' cannot be compared, so the pair was not read"
    if _year_like(before.num, u1 or before.cur) and _year_like(after.num, u2 or after.cur):
        return None, "year span"
    a, b = _frac(before.num, u1), _frac(after.num, u2)
    return _Values(a, b, _shown(before, u1), _shown(after, u2), _is_pct(u1) and _is_pct(u2), before.year, after.year, u2 or u1, after.noun or before.noun,
                   before.cur or after.cur or _cur_of_noun(after.noun or before.noun)), ""


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
    if not _cur_compatible(before.cur, before.noun, after.cur, after.noun):  # a currency sign is a unit of account, as in the general reading
        return None, cannot
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
    elif k1 == "rate" and k2 == "rate" and _xrate_unit_conflict(u1, u2):
        return None, cannot  # exchange rates of two currencies, or an exchange rate against a rate per head
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
    phrase: str = ""          # the derived phrase or relation the check reads ('added roughly 4,500 miles'), for naming its claim
    rule: str = ""            # the rule the check applies, when it is not the kind's default (a duration with a qualifier or day dates)
    severity: str = "error"   # the severity of a failure: 'warning' when the check rests on a reading the report did not state


def _amount_comparable(values: _Values, d: _Derived) -> str:
    """Why the amount of an absolute change or a rate cannot be read against the pair's figures, or '' when it can: units of
    different kinds (a scaled amount against unscaled figures, a count against per-cent figures), or two different nouns
    ('an increase of 4,500 miles' against figures in tonnes)."""
    k_amount, k_pair = _unit_kind(d.unit), _unit_kind(values.unit)
    if values.pct:
        return f"'{d.words}' states an amount, but its figures are per-cent shares (a change in points or per cent was expected)"
    if k_amount != k_pair and {k_amount, k_pair} != {"count", None}:  # '34 seats' against bare figures is a count of the same thing
        return f"the unit of '{d.words}' and of its figures ({values.shown_a}, {values.shown_b}) cannot be compared"
    if (d.cur or values.cur) and not _cur_compatible(d.cur, d.noun, values.cur, values.noun if not values.cur else ""):
        return f"the currency of '{d.words}' and of its figures ({values.shown_a}, {values.shown_b}) differ"
    if d.cur and values.cur:
        return ""  # '$1.4 billion' against '$1.5 billion ... $4.9 billion': one unit of account
    if d.noun and values.noun and not _same_noun(d.noun, values.noun):
        return f"'{d.words}' counts {d.noun.split()[-1]} while its figures count {values.noun.split()[-1]}"
    return ""


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
                     f"stated {d.direction} of {_fmt(d.stated)} {'percentage ' if d.percentage_points else ''}points against the computed difference"), POINT_FLOOR, d.side, note, basis, d.words), ""
    if d.kind in ("abs_change", "rate_change"):
        why = _amount_comparable(values, d)
        if why:
            return None, why
        diff = {"op": "sub", "left": _v("after"), "right": _v("before")}
        direction = d.direction or ("rise" if b >= a else "fall")
        if direction == "fall":
            diff = {"op": "sub", "left": _v("before"), "right": _v("after")}
        unit_words = " ".join(x for x in (d.unit or "", d.noun) if x)
        if d.kind == "abs_change":
            return _Spec("abs_change", statement, before_after, premises, ("STATED_DIFFERENCE", _within(diff, d.stated, tolerance, Fraction(0), d.side),
                         f"stated {direction} of {_fmt(d.stated)}{(' ' + unit_words) if unit_words else ''} against the computed difference"), Fraction(0), d.side, note, basis, d.words), ""
        if values.year_a is None or values.year_b is None or values.year_b <= values.year_a:
            return None, "the figures of its pair are not dated by two different years, so no average rate per year can be computed"
        periods = Fraction(values.year_b - values.year_a) / {"year": 1, "annum": 1, "decade": 10, "month": Fraction(1, 12)}.get(d.per, 1)
        rate = {"op": "div", "left": diff, "right": _real(periods)}
        return _Spec("rate_change", statement, before_after, premises, ("STATED_RATE", _within(rate, d.stated, tolerance, Fraction(0), d.side),
                     f"stated average of {_fmt(d.stated)}{(' ' + unit_words) if unit_words else ''} a {d.per} against the computed difference over {values.year_b - values.year_a} years"),
                     Fraction(0), d.side, note, basis, d.words), ""
    if a == 0:
        return None, "the earlier figure is zero, so no relative change can be computed"
    if not si and (a < 0 or b < 0):
        return None, "a figure of its pair is negative, and a relative change of a negative figure is not read in this reading"
    if d.kind in ("percent_change", "change"):
        direction = d.direction or ("rise" if b >= a else "fall")
        change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(base)}]}
        if direction == "fall":
            change = {"op": "neg", "arg": change}
        how = "the stated sign's direction" if d.direction else "the figures' own direction"
        label = f"stated {direction} of {_fmt(d.stated)} per cent against the computed change" if d.kind == "percent_change" else f"stated change of {_fmt(d.stated)} per cent ({direction}, {how}) against the computed change"
        places = _written_places(d.words, d.stated) if d.side == "both" else None
        band = _precision_band(change, d.stated, tolerance, places, values) if places else None
        if band is not None:
            # a per cent written with decimals states its own precision: no half-point floor (PRECISION_RULE)
            return _Spec("percent_change", statement, before_after, premises, ("STATED_CHANGE", band, label + " at its written precision"), Fraction(0), d.side, note, basis,
                         d.words, rule=PRECISION_RULE.format(tol=f"{float(tolerance) * 100:g}")), ""
        return _Spec("percent_change", statement, before_after, premises, ("STATED_CHANGE", _within(change, d.stated, tolerance, POINT_FLOOR, d.side), label), POINT_FLOOR, d.side, note, basis, d.words), ""
    if d.kind == "fraction_change":
        change = {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(base)}
        if d.direction == "fall":
            change = {"op": "neg", "arg": change}
        return _Spec("fraction_change", statement, before_after, premises, ("STATED_FRACTION", _within(change, d.stated, tolerance, Fraction(0), d.side),
                     f"stated {d.direction} of '{d.words}' (= {d.stated}) against the computed change"), Fraction(0), d.side, note, basis, d.words), ""
    ratio = {"op": "div", "left": _v("after"), "right": _real(a)}
    return _Spec("fold_change", statement, before_after, premises, ("STATED_FOLD", _within(ratio, d.stated, tolerance, Fraction(0), d.side),
                 f"stated '{d.words}' (factor {_fmt(d.stated)}) against the computed ratio"), Fraction(0), d.side, note, basis, d.words), ""


#: A clause turn between a stated change and a later pair, followed by the pair's own subject and its own direction verb right before its
#: 'from' ("... the market grew by 25.0%, so its market share fell from 15.0% to 13.2%"): read only on the text between the change and
#: the pair (bounded by a clause), from the turn's end.
_CHANGE_TURN_RE = re.compile(r"(?:,\s*+(?:so|and|but|while|whereas|yet|hence|thus|therefore|which\s++meant|meaning)\b|;)", re.IGNORECASE)
#: The subject of the pair's own clause: one to six words that are no pronoun of the change's own subject ('it', 'this', 'they').
_TURN_SUBJECT_RE = re.compile(r"^\s*+(?:(?:as\s++a\s++result|in\s++turn|consequently|then)\s*+,?\s++)?(?P<subj>(?!(?:it|this|that|they|these|those|which)\b)"
                              r"[\w'’$£€%.-]++(?:\s++[\w'’$£€%.-]++){0,5}?)\s++$", re.IGNORECASE)


def _foreign_change(clause: str, d: "_Derived", p: "_Pair") -> bool:
    """True when the change ``d`` stated before the pair ``p`` is the change of another quantity (round 9, c2 bm-t15): a clause turn
    (', so', ', but', ';', ...) lies between them and the pair's clause has its own subject and its own direction verb right before its
    'from' ("Pellow Cycles' sales revenue rose by 10.0%, but the market grew by 25.0%, so its market share fell from 15.0% to 13.2%": the
    25.0% is the market's growth, the pair the market share's fall). A change written right before its pair ("roughly tripled from 1.9
    million ..."), after it (", a rise of 63 per cent"), or whose pair's clause has no subject of its own or a pronoun of the change's
    ("..., and it fell from 100 to 70") stays bound. Read on the text between the two, at most 400 characters."""
    if d.end > p.start:
        return False
    gap = clause[d.end:p.start]
    if len(gap) > 400:
        return False
    turns = list(_CHANGE_TURN_RE.finditer(gap))
    if not turns:
        return False
    tail = gap[turns[-1].end():]
    verb = _PAIR_DIR_BEFORE_RE.search(tail)
    if verb is None:
        return False
    return _TURN_SUBJECT_RE.match(tail[:verb.start()] + " ") is not None


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
            seps = list(_SEG_SEP_RE.finditer(clause[p.end: nxt.start]))
            end = p.end + seps[-1].start() if seps else nxt.start
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
    u1, u2, ok = _comparable(pair.before.unit, pair.after.unit, pair.before.noun if not pair.before.cur or pair.after.cur else "",
                             pair.after.noun if not pair.after.cur or pair.before.cur else "")
    if not ok or not _cur_compatible(pair.before.cur, pair.before.noun, pair.after.cur, pair.after.noun):
        return None
    if _year_like(pair.before.num, u1 or pair.before.cur) and _year_like(pair.after.num, u2 or pair.after.cur):
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


def _merge_related(candidates: list[_Series]) -> list[_Series]:
    """Series of one kind that agree on every shared year and are stated with a common content word ('Route mileage was about 1,500 by
    1840 and about 6,000 by 1850' and 'Route mileage reached about 13,000 in 1860 and about 15,500 in 1870') are one series."""
    merged: list[_Series] = []
    for s in candidates:
        for m in merged:
            if (m.kind == s.kind and all(m.points[y][0] == s.points[y][0] for y in m.points.keys() & s.points.keys())
                    and _content_words(m.text) & _content_words(s.text)):
                m.points = {**s.points, **m.points}
                m.text = m.text + " " + s.text
                break
        else:
            merged.append(_Series(s.kind, s.unit, dict(s.points), s.sentence, s.text))
    return merged


def _pick_series(series: list[_Series], years: list[int], clause: str, *, kinds: Optional[set] = None, extra: Optional[list] = None) -> tuple[Optional[_Series], str]:
    """The one series of the paragraph that states every year in ``years``; several are told apart by shared words with ``clause``.
    When no single series states them all, series of the same measure stated in different sentences (a common content word, no
    disagreement on a shared year) are read as one."""
    candidates = [s for s in series if all(y in s.points for y in years) and (kinds is None or s.kind in kinds)]
    candidates = _merge(candidates)
    if not candidates:
        pool = [s for s in [*series, *(extra or [])] if kinds is None or s.kind in kinds]
        candidates = [s for s in _merge_related(pool) if all(y in s.points for y in years)]
    if not candidates:
        return None, "the paragraph states no dated series with figures for " + " and ".join(str(y) for y in years)
    if len(candidates) > 1:
        words = _content_words(clause)
        scored = [s for s in candidates if words & _content_words(s.text)]
        if len(scored) == 1:
            return scored[0], ""
        return None, f"{len(candidates)} dated series of the paragraph state figures for " + " and ".join(str(y) for y in years) + "; which one the statement relies on is not stated"
    return candidates[0], ""


def _earlier_year(sentences: list[str], index: int, clause: str, phrase_start: int,
                  nearest: Optional[list[Optional[list[int]]]] = None) -> tuple[Optional[int], str]:
    """The year an anaphor ('that year') refers to, and why when there is none: the one year stated
    before it in its own clause, else the one year stated in the nearest earlier sentence of the
    paragraph that states any. Two or more candidate years at the nearest level are ambiguous.
    ``nearest`` (:func:`_nearest_years`) is the paragraph's reading of that sentence for every sentence, read once per paragraph
    (integration gate 2: the walk back from every anaphor read every earlier sentence again, n² steps on a paragraph of anaphors with no
    year); without it the sentences are walked back as before."""
    years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(clause[:phrase_start])})
    if len(years) == 1:
        return years[0], ""
    if years:
        return None, f"'that year' could refer to {len(years)} years stated before it in its sentence"
    if nearest is not None:
        found = nearest[index - 1] if index > 0 else None
        candidates = [found] if found else []
    else:
        candidates = (y for y in (sorted({int(t) for t in _YEAR_TOKEN_RE.findall(sentences[j])}) for j in range(index - 1, -1, -1)) if y)
    for years in candidates:
        if len(years) == 1:
            return years[0], ""
        return None, f"'that year' could refer to {len(years)} years ({', '.join(map(str, years[:6]))}) stated in the sentence before it"
    return None, "'that year' refers to no year stated earlier in the paragraph"


def _nearest_years(sentences: list[str]) -> list[Optional[list[int]]]:
    """For every sentence of a paragraph, the years (sorted, distinct) of the nearest sentence at or before it that states any, or None."""
    out: list[Optional[list[int]]] = []
    last: Optional[list[int]] = None
    for sent in sentences:
        years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(sent)})
        if years:
            last = years
        out.append(last)
    return out


def _decade_before(clause: str, at: int) -> Optional["re.Match[str]"]:
    """The decade token ('the 1840s') that governs a phrase at ``at``: the last one before it in its clause, when every year the
    clause states between the decade and the phrase falls inside that decade ('The 1840s, which included the Railway Mania of 1845
    to 1847, added ...') and no 'from'/'between' span stands between them; otherwise None."""
    decades = list(_DECADE_TOKEN_RE.finditer(clause, 0, at))
    if not decades:
        return None
    d = decades[-1]
    d0 = int(d.group("d"))
    between = clause[d.end(): at]
    if _YEAR_SPAN_RE.search(between):
        return None
    if any(not (d0 <= int(y) < d0 + 10) for y in _YEAR_TOKEN_RE.findall(between)):
        return None
    return d


def _outside_decade(before: _Fig, after: _Fig, d0: int) -> bool:
    """True when a pair's dated figures cannot be about the decade starting ``d0`` (a year before it or after its end)."""
    return before.year is not None and after.year is not None and (before.year < d0 or after.year > d0 + 10)


def _target_years(sentences: list[str], index: int, clause: str, at: int, series_years: list[int],
                  nearest: Optional[list[Optional[list[int]]]] = None) -> tuple[Optional[tuple[int, int]], str]:
    """(earlier year, later year) a derived figure with no pair of its own speaks of: a decade that is the clause's subject ('The
    1840s ... added roughly 4,500 miles': 1840 to 1850), a span in the clause ('from 1929 to 1930'), an anaphor ('that year') or the
    one year the clause states, read against the series' previous dated figure."""
    decade = _decade_before(clause, at)
    if decade is not None:
        d0 = int(decade.group("d"))
        return (d0, d0 + 10), f"'{decade.group(0).strip()}' read as {d0} to {d0 + 10}"
    span = _YEAR_SPAN_RE.search(clause)
    if span:
        return (int(span.group(1)), int(span.group(2))), f"the years {span.group(1)} and {span.group(2)} stated in the sentence"
    anaphor = _THAT_YEAR_RE.search(clause)
    if anaphor:
        year, why = _earlier_year(sentences, index, clause, anaphor.start(), nearest)
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


_COMPARE_HINT_RE = re.compile(r"short\s+of|exceed|surpass|outstrip|overt(?:ook|ak)|topp?(?:ed|ing)|outpaced", re.IGNORECASE)
#: A figure standing alone before a comparison verb ('Output reached 6.2 million tonnes in 1932, short of ...').
_LONE_FIG_RE = re.compile(rf"{_fig(1)}", re.IGNORECASE)


def _elliptical(gap: str) -> bool:
    """True when the words before a pair are a bare noun phrase continuing a list ('..., steel from', ' and coal from'): the
    previous pair's direction word governs it too."""
    tail = re.split(r"[;:]", gap)[-1]
    m = re.search(r"(?:,|\band\b)\s*((?:[a-z][a-z'’-]*\s+){0,3})$", tail, re.IGNORECASE)
    if m is None:
        return False
    words = m.group(1).split()
    return 0 < len(words) <= 3 and not any(w.lower().endswith(("ed", "ing")) for w in words)


#: Direction words that are also verbs of motion: over lengths in the SI reading they may describe a position ('the ball falls from 0 m
#: to 20 m' below its start), so a pair of lengths they govern is not read as a change of a quantity.
_MOTION_WORDS = frozenset("rose rising risen rises fell falling fallen falls dropped dropping drops climbed climbing climbs sank sinking jumped jumping "
                          "soared soaring raised raising lowered lowering".split()) | {"went up", "went down"}


def _si_length_pair(pair: "_Pair", profile: str) -> bool:
    """SI reading: a figure of the pair carries a unit of length."""
    for fig in (pair.before, pair.last):
        if fig.unit:
            su = si_unit(fig.unit, profile)
            if su is not None and su.dimension == "length":
                return True
    return False


def _direction_spec(values: _Values, word: str, statement: str, *, quoted: str = "", base: str = "") -> _Spec:
    """The check that the pair moves the way its direction word says. With ``quoted`` (the currency the sentence says moved, when
    the figures are an exchange rate of ``base``: :func:`_xrate_reading`), the figures are the price of one ``base`` in that
    currency, so a fall of the currency is a rise of the figure and a rise of it a fall (integration gate 3)."""
    rising = word.lower() in _RISE_DIR_WORDS
    figure_rises = rising != bool(quoted)
    premises = (("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(values.a)}, f"before = {values.shown_a}"),
                ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(values.b)}, f"after = {values.shown_b}"))
    concl = {"op": "gt" if figure_rises else "lt", "left": _v("after"), "right": _v("before")}
    label = f"stated '{word}' from {values.shown_a} to {values.shown_b}: the later figure {'above' if figure_rises else 'below'} the earlier"
    if quoted:
        label += (f" (the figures are the price of one {base} in the {quoted}, so a {'rise' if rising else 'fall'} of the {quoted} is a "
                  f"{'fall' if rising else 'rise'} of the figure)")
    return _Spec("pair_direction", statement, (("before", "the earlier figure as stated"), ("after", "the later figure as stated")), premises,
                 ("STATED_DIRECTION", concl, label), Fraction(0), "both", phrase=word)


# ------------------------------------------------------------------ exchange rates (integration gate 3)

#: An exchange rate written as a count of one currency to one unit of another ('25 to the pound', '4.2 to the US dollar'): the figure is
#: the price of the BASE currency (the unit's: the pound, the dollar) in the QUOTED one (the franc, the mark), so the quoted currency falls
#: when the figure rises. Read as a whole unit string (a pair figure's unit, :data:`_UNIT_WORDS`).
_XRATE_UNIT_RE = re.compile(r"to\s+(?:the|one|a)\s+(?:US\s+|U\.S\.\s+|American\s+)?(?P<base>dollar|pound)s?", re.IGNORECASE)
#: Currency nouns a subject may name, and the currency each names ('sterling' is the pound, 'Reichsmark' a mark). 'crown', 'real' and
#: 'won' are left out: as subjects they are more often the monarchy, an adjective or a verb.
_CURRENCY_NAMES = {"dollar": "dollar", "pound": "pound", "sterling": "pound", "franc": "franc", "mark": "mark", "reichsmark": "mark",
                   "rentenmark": "mark", "deutschmark": "mark", "deutsche mark": "mark", "rouble": "rouble", "ruble": "rouble", "lira": "lira",
                   "lire": "lira", "peso": "peso", "yen": "yen", "yuan": "yuan", "renminbi": "yuan", "rupee": "rupee", "krona": "krona",
                   "krone": "krona", "kronor": "krona", "kroner": "krona", "zloty": "zloty", "drachma": "drachma", "escudo": "escudo",
                   "peseta": "peseta", "guilder": "guilder", "florin": "guilder", "schilling": "schilling", "forint": "forint", "koruna": "koruna",
                   "rand": "rand", "dinar": "dinar", "baht": "baht", "euro": "euro", "pengo": "pengo", "pengő": "pengo"}
_CURRENCY_WORD = (r"(?:deutsche\s+marks?|dollars?|pounds?|sterling|francs?|marks?|reichsmarks?|rentenmarks?|deutschmarks?|roubles?|rubles?|lira|lire|pesos?|yen"
                  r"|yuan|renminbi|rupees?|krona|krone|kronor|kroner|zlotys?|drachmas?|escudos?|pesetas?|guilders?|florins?|schillings?|forints?"
                  r"|korunas?|rand|dinars?|baht|euros?|peng(?:o|ő)s?)")
_CURRENCY_RE = re.compile(rf"\b{_CURRENCY_WORD}\b", re.IGNORECASE)
#: A currency named as what another is measured against or in ('against the pound', 'in marks', 'per dollar', 'relative to the US dollar'):
#: never the subject whose direction the sentence states. Every run is possessive and every repetition bounded, so a long blank run is
#: read once.
_XRATE_COUNTER_RE = re.compile(rf"\b(?:(?:against|versus|vs\.?|relative\s++to|compared\s++(?:with|to)|in\s++terms\s++of|per|to)\s++(?:(?:the|one|a)\s++)?"
                               rf"|(?:in|into|for)\s++)(?:(?!(?:the|an?|one)\s)[A-Za-z][\w.'’-]{{0,20}}\s++)?{_CURRENCY_WORD}\b(?!['’]s\b)", re.IGNORECASE)
#: What a pair's head holds besides its subject: punctuation, connectors, adverbs and the direction word (', and later', 'before falling').
_XRATE_FILLER_RE = re.compile(rf"[\W\d_]++|\b(?:and|but|while|whereas|before|then|later|again|further|back|still|in\s++turn|also|so|as|[a-z]+ly)\b"
                              rf"|{_PAIR_DIR_RE.pattern}", re.IGNORECASE)
#: Why a direction stated of an exchange rate without the currency it is said of is not checked (``CORE-QNT-001``).
XRATE_OPEN_REASON = ("its figures are an exchange rate (a count of one currency to one unit of another) and the sentence does not name the currency its "
                     "direction is said of: a fall of the quoted currency is a rise of the figure, so the stated direction holds under one reading "
                     "and fails under the other, and it was not checked")
#: The basis of a derived figure stated of an exchange rate whose subject is not the base currency (``_xrate_either``).
_XRATE_EITHER_BASIS = ("the figures are an exchange rate (a count of the quoted currency to one {base}): the stated change is read of the figures "
                       "as written and of the quoted currency's value (one {base} over the figure), and it holds when either reading holds")


def _xrate_base(before: _Fig, after: _Fig) -> str:
    """The base currency ('dollar', 'pound') when both figures of a pair are an exchange rate of it (a unit on one figure only carries to the
    other, as :func:`_comparable` reads it), else ''."""
    u1, u2 = before.unit or after.unit, after.unit or before.unit
    m1 = _XRATE_UNIT_RE.fullmatch(" ".join((u1 or "").split()))
    m2 = _XRATE_UNIT_RE.fullmatch(" ".join((u2 or "").split()))
    if m1 is None or m2 is None or m1.group("base").lower() != m2.group("base").lower():
        return ""
    return m1.group("base").lower()


def _xrate_unit_conflict(u1: Optional[str], u2: Optional[str]) -> bool:
    """Two rate units of which one is an exchange rate and the other is not the same one ('to the dollar' against 'to the pound' or 'per
    head'): the figures count different things and are never compared."""
    m1 = _XRATE_UNIT_RE.fullmatch(" ".join((u1 or "").split()))
    m2 = _XRATE_UNIT_RE.fullmatch(" ".join((u2 or "").split()))
    if m1 is None and m2 is None:
        return False
    return m1 is None or m2 is None or m1.group("base").lower() != m2.group("base").lower()


def _xrate_reading(heads: list[str], k: int, base: str) -> tuple[str, str]:
    """How the direction word of pair ``k`` reads its exchange-rate figures (``heads``: the text before each pair of the clause, from the
    end of the pair before it): ``('written', base)`` when the sentence says the base currency moved ('The dollar rose'), ``('inverse',
    currency)`` when it says another currency moved ('The franc fell', 'the value of the mark collapsed'), else ``('open', '')`` ('The
    exchange rate fell', 'It fell', 'Prices rose'). The currency is the last one named before the pair that is not named as what it is
    measured against ('Against the pound, the franc fell' is the franc); a head that holds nothing but connectors, adverbs and a direction
    word continues the head before it ('..., and later fell from')."""
    for head in reversed(heads[:k + 1]):
        name = _named_currency(head)
        if name:
            return ("written", base) if name == base else ("inverse", name)
        if _XRATE_FILLER_RE.sub("", head).strip():
            return "open", ""
    return "open", ""


def _named_currency(text: str) -> str:
    """The currency ``text`` last names that is not named as what another is measured against or in (:data:`_XRATE_COUNTER_RE`), by its
    name in :data:`_CURRENCY_NAMES` ('Reichsmark' is 'mark', 'sterling' is 'pound'), or ''."""
    found = None
    for found in _CURRENCY_RE.finditer(_XRATE_COUNTER_RE.sub(" ", text)):
        pass
    if found is None:
        return ""
    word = " ".join(found.group(0).lower().split())
    return _CURRENCY_NAMES.get(word) or _CURRENCY_NAMES.get(word[:-1] if word.endswith("s") else word, "")


def _renamed(expr, names: dict[str, str]):
    """A copy of the IR expression ``expr`` with its variables renamed by ``names`` (data only: dicts and lists are rebuilt)."""
    if isinstance(expr, dict):
        if expr.get("op") == "var" and expr.get("name") in names:
            return {**expr, "name": names[expr["name"]]}
        return {key: _renamed(value, names) for key, value in expr.items()}
    if isinstance(expr, list):
        return [_renamed(value, names) for value in expr]
    return expr


def _xrate_either(spec: _Spec, values: _Values, d: "_Derived", statement: str, tolerance: Fraction, base: str, *, si: bool = False) -> _Spec:
    """The check of derived figure ``d`` on an exchange-rate pair whose subject is not the base currency: it holds when the stated change
    holds of the figures as written ('a rise of 860 per cent' in the rate) or of the quoted currency's value, one ``base`` over the
    figure ('The franc fell ..., a fall of 90 per cent', 'halved'), since such a sentence may state either. ``spec`` (the reading as
    written) when the reciprocal reading cannot be built (a zero figure)."""
    if values.a == 0 or values.b == 0:
        return spec
    inverse = replace(values, a=1 / values.a, b=1 / values.b, shown_a=f"1/({values.shown_a})", shown_b=f"1/({values.shown_b})", pct=False)
    value_spec, _why = _pair_spec(inverse, d, statement, tolerance, si=si)
    if value_spec is None:
        return spec
    names = {"before": "value_before", "after": "value_after"}
    premises = spec.premises + tuple((f"VALUE_{pid}", _renamed(expr, names), f"value_{label} (the quoted currency's value, in {base}s)")
                                     for pid, expr, label in value_spec.premises)
    symbols = spec.symbols + (("value_before", f"the quoted currency's value at the earlier figure, in {base}s (one {base} over the figure)"),
                              ("value_after", f"the quoted currency's value at the later figure, in {base}s (one {base} over the figure)"))
    conclusion = (spec.conclusion[0], {"op": "or", "args": [spec.conclusion[1], _renamed(value_spec.conclusion[1], names)]},
                  f"{spec.conclusion[2]}; or, of the quoted currency's value, {value_spec.conclusion[2]}")
    basis = _XRATE_EITHER_BASIS.format(base=base)
    return replace(spec, symbols=symbols, premises=premises, conclusion=conclusion, basis=(spec.basis + "; " + basis) if spec.basis else basis)


def _through_arithmetic(spec: _Spec, p: _Pair, values: "_Values") -> _Spec:
    """``spec`` for a pair whose later figure is the stated result of written arithmetic after 'to' (:func:`_arith_endpoint`): its
    basis names the arithmetic, and a failure is a warning (INT-SUBJ-004), since the figure the change ends at is read through the
    arithmetic, not stated as the figure after 'to'. ``spec`` itself for any other pair."""
    if not p.via:
        return spec
    basis = f"the figure after 'to' is the stated result of the written arithmetic '{p.via} = {values.shown_b}'"
    return replace(spec, severity="warning", basis=(spec.basis + "; " + basis) if spec.basis else basis)


def _subject_words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", text.lower())} - {"the", "and", "from", "rising", "rose", "falling", "fell", "official", "figures", "show", "between"}


def _comparison_spec(cm: "re.Match[str]", clause: str, si: int, sentence_pairs: dict, pairs: list, tolerance: Fraction) -> tuple[Optional[_Spec], str]:
    """The check of a comparison with a stated benchmark ('fell short of the target of about 10 million tonnes of pig iron', 'exceeded
    ... by half'): the compared figure is the last figure before the verb in its clause, or, for a subject that refers back ('These
    totals'), the figure of the previous sentence whose subject the benchmark names ('of pig iron'). Returns ``(spec, '')``, ``(None,
    reason)`` when the comparison cannot be decided, or ``(None, '')`` when the clause compares no stated figure at all."""
    verb = " ".join(cm.group("verb").lower().split())
    short = "short of" in verb
    target_unit, target_noun = cm.group("tu"), (cm.group("tnoun") or "").strip()
    if _year_like(cm.group("tn"), target_unit):
        return None, ""
    target = _frac(cm.group("tn"), target_unit)
    target_shown = " ".join(x for x in (cm.group("tn"), target_unit or "", target_noun, (cm.group("tof") or "").strip()) if x)
    head = clause[: cm.start()]
    subject: Optional[tuple[_Fig, Optional[str], str]] = None   # (figure, unit after elision, where it was read)
    local = [p for p in pairs if p.end <= cm.start()]
    if local:
        p = local[-1]
        u1, u2, _ok = _comparable(p.before.unit, p.last.unit, p.before.noun, p.last.noun)
        subject = (p.last, u2, "the later figure of the pair before it in its clause")
    else:
        lone = [m for m in _LONE_FIG_RE.finditer(head) if m.group("n1")[:1].isdigit() and not _year_like(m.group("n1"), m.group("u1"))]
        if lone:
            f = _fig_of(lone[-1], 1)
            subject = (f, f.unit, "the figure before it in its clause")
    if subject is None and _ANAPHOR_SUBJECT_RE.match(head) and not _FIGURE_HINT_RE.search(head):
        candidates = sentence_pairs.get(si - 1, [])
        if not candidates:
            return None, "its subject refers back to figures, but the sentence before it states no pair of figures"
        wanted = _subject_words((cm.group("tof") or "") + " " + target_noun) - {"tonne", "ton", "million", "thousand", "billion", "mile", "unit"}
        matching = [c for c in candidates if wanted and wanted & _subject_words(c[2])]
        chosen = matching[0] if len(matching) == 1 else (candidates[0] if len(candidates) == 1 else None)
        if chosen is None:
            return None, f"its subject refers back to {len(candidates)} figures of the sentence before it, and the benchmark names none of them alone"
        p = chosen[0]
        _u1, u2, _ok = _comparable(p.before.unit, p.last.unit, p.before.noun, p.last.noun)
        subject = (p.last, u2, "the later figure of the pair in the sentence before it" + (f" whose subject matches '{(cm.group('tof') or target_noun).strip()}'" if matching else ""))
    if subject is None:
        if _BENCHMARK_RE.search(cm.group("words") or ""):
            return None, f"the figure compared with {target_shown} is not stated in its sentence or the sentence before it"
        return None, ""
    fig, unit, where = subject
    _ua, _ub, ok = _comparable(unit, target_unit, fig.noun, target_noun)
    if not ok:
        return None, f"the units of '{_shown(fig, unit)}' and '{target_shown}' cannot be compared"
    value = _frac(fig.num, unit)
    premises = (("VALUE", {"op": "eq", "left": _v("value"), "right": _real(value)}, f"value = {_shown(fig, unit)} ({where})"),
                ("TARGET", {"op": "eq", "left": _v("target"), "right": _real(target)}, f"benchmark = {target_shown}"))
    order = {"op": "lt" if short else "gt", "left": _v("value"), "right": _v("target")}
    parts = [order]
    margin = ""
    floor = Fraction(0)
    side = "both"
    if target != 0 and (cm.group("bfrac") or cm.group("bn")):
        gap = {"op": "sub", "left": _v("target"), "right": _v("value")} if short else {"op": "sub", "left": _v("value"), "right": _v("target")}
        side = _side(cm.group("bq"))
        if cm.group("bfrac"):
            key = re.sub(r"^(?:a|one)\s+", "", cm.group("bfrac").lower()).replace("-", " ")
            stated = _FRACTION_WORDS[key]
            parts.append(_within({"op": "div", "left": gap, "right": _real(target)}, stated, tolerance, Fraction(0), side))
            margin = f" by '{cm.group('bfrac')}' (= {stated} of the benchmark)"
        elif cm.group("bu") and _is_pct(cm.group("bu")):
            stated = _number(cm.group("bn"))
            floor = POINT_FLOOR
            parts.append(_within({"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": gap, "right": _real(target)}]}, stated, tolerance, POINT_FLOOR, side))
            margin = f" by {_fmt(stated)} per cent of the benchmark"
        else:
            stated = _frac(cm.group("bn"), cm.group("bu"))
            parts.append(_within(gap, stated, tolerance, Fraction(0), side))
            margin = f" by {cm.group('bn')}{(' ' + cm.group('bu')) if cm.group('bu') else ''}"
    concl = parts[0] if len(parts) == 1 else {"op": "and", "args": parts}
    label = f"stated '{verb}' {target_shown}{margin}: {_shown(fig, unit)} {'below' if short else 'above'} the benchmark"
    return _Spec("comparison", clause.strip(), (("value", "the compared figure as stated"), ("target", "the benchmark as stated")), premises,
                 ("STATED_COMPARISON", concl, label), floor, side, phrase=" ".join(cm.group(0).split())[:200]), ""


#: One figure dated by a year alone, standing outside any pair ('took the network to about 13,000 miles by 1870').
_DATED_FIG_RE = re.compile(_fig(1, dated=True), re.IGNORECASE)


def _standalone_points(sentences: list[str]) -> list[_Series]:
    """Every figure of the paragraph dated by a year alone and standing outside a pair, as one-point series (read only by the
    comparison with every other decade, which needs the figure at each decade's end)."""
    out: list[_Series] = []
    for si, sent in enumerate(sentences):
        if not _FIGURE_HINT_RE.search(sent):
            continue
        covered = [(p.start, p.end) for p in _pairs(sent)]
        for m in _DATED_FIG_RE.finditer(sent):
            if any(a <= m.start() < b for a, b in covered):
                continue
            f = _fig_of(m, 1)
            if not f.annual or _year_like(f.num, f.unit):
                continue
            out.append(_Series(_unit_kind(f.unit), f.unit, {f.year: (_frac(f.num, f.unit), _shown(f, f.unit))}, si, sent))
    return out


def _any_other_spec(m: "re.Match[str]", clause: str, para: str, series: list, standalone: Optional[list] = None) -> tuple[Optional[_Spec], list[str]]:
    """'The 1840s ... added roughly 4,500 miles, more than any other decade of the period': the decade's change in the paragraph's
    dated series against every other decade whose figures the series states at both ends. Decided (a check) when the stated
    decades refute it, or when every decade of the period ('between 1830 and 1870') is stated; otherwise undecided, with the
    decades whose figures are missing. A year ('more than in any other year') is read the same way over consecutive years."""
    unit = m.group("unit").lower()
    larger = m.group("cmp").lower() in ("more", "greater", "larger", "bigger", "faster", "higher")
    if unit != "decade":
        return None, ["a comparison with every other year is read only for decades; the years it compares are not paired with figures"]
    dec = _decade_before(clause, m.start())
    if dec is None:
        return None, ["the decade it speaks of is not named before it in its clause"]
    d0 = int(dec.group("d"))
    s, why = _pick_series(series, [d0, d0 + 10], clause, extra=standalone)
    if s is None:
        return None, [f"the paragraph's dated series does not state figures at both ends of the {d0}s: {why}"]
    # the other decades' ends may stand in other pairs or alone ('The 1850s took the network to about 11,000 miles by 1860'):
    # every annual figure of the same kind that does not contradict the series is read with it
    s = _Series(s.kind, s.unit, dict(s.points), s.sentence, s.text)
    for extra in [x for x in series if x.kind == s.kind] + [x for x in (standalone or []) if x.kind == s.kind]:
        if all(s.points[y][0] == extra.points[y][0] for y in s.points.keys() & extra.points.keys()):
            for y, v in extra.points.items():
                s.points.setdefault(y, v)
    span = _YEAR_SPAN_RE.search(para)
    period = list(range((int(span.group(1)) // 10) * 10, int(span.group(2)), 10)) if span else []
    others = sorted(e for e in s.points if e % 10 == 0 and e != d0 and (e + 10) in s.points and (not period or e in period))
    missing = [e for e in period if e != d0 and e not in others]
    shown_missing = ", ".join(f"the {e}s" for e in missing)
    if not others:
        return None, [f"no other decade of the period has figures at both its ends in the paragraph's dated series" + (f" ({shown_missing} are not stated decade by decade)" if missing else "")]
    change = {e: s.points[e + 10][0] - s.points[e][0] for e in (d0, *others)}
    refuted = [e for e in others if (change[e] >= change[d0] if larger else change[e] <= change[d0])]
    reasons: list[str] = []
    if not refuted and missing:
        return None, [f"the {d0}s exceed every decade the paragraph states ({', '.join(f'the {e}s' for e in others)}), but {shown_missing} are not stated decade by decade"]
    years = sorted({y for e in (d0, *others) for y in (e, e + 10)})
    symbols = tuple((f"v{y}", f"the figure for {y} as stated") for y in years)
    premises = tuple((f"Y{y}", {"op": "eq", "left": _v(f"v{y}"), "right": _real(s.points[y][0])}, f"{y}: {s.points[y][1]}") for y in years)

    def delta(e: int) -> dict:
        return {"op": "sub", "left": _v(f"v{e + 10}"), "right": _v(f"v{e}")}
    cmp = [{"op": "gt" if larger else "lt", "left": delta(d0), "right": delta(e)} for e in others]
    concl = cmp[0] if len(cmp) == 1 else {"op": "and", "args": cmp}
    label = f"stated '{m.group(0)}' for the {d0}s against every other decade the paragraph's dated series states ({', '.join(f'the {e}s' for e in others)}, sentence {s.sentence + 1})"
    return _Spec("series_extreme", clause.strip(), symbols, premises, ("STATED_EXTREME", concl, label), Fraction(0), "both",
                 "figure stated in the report itself, in another sentence of the paragraph",
                 f"stated across sentences: '{dec.group(0).strip()}' read as {d0} to {d0 + 10}; figures from sentence {s.sentence + 1}: {_series_label(s, years)}", m.group(0)), reasons


# ------------------------------------------------------------------ parts of a stated total, shares of it, differences, durations

#: '..., of which the United Kingdom received about $3.2 billion and France about $2.7 billion': the parts of the total before it.
_OF_WHICH_RE = re.compile(r",\s*(?:(?:most|some|part|much|all)\s+)?of\s+(?:which|whom|these)\b", re.IGNORECASE)
#: '1882 alone brought nearly 790,000', 'the United Kingdom alone received $3.2 billion': one part of the total stated before it.
#: The party's name is read up to twelve capitalised words (integration gate 2: an unbounded name was read again from each of its words, n²
#: steps on a run of capitalised words, 4 s at 24,000 characters); a longer name is read as its last twelve words.
_ALONE_RE = re.compile(r"\b(?P<who>(?:1[0-9]{3}|20[0-9]{2})|[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*){0,11})\s+alone\s+(?:had\s+|has\s+)?"
                       r"(?P<verb>brought|saw|accounted\s+for|added|contributed|admitted|received|took|produced|absorbed|got|gained|sent|supplied|provided|delivered|lost|"
                       r"took\s+in|let\s+in)\s+")
#: '<part>, about a quarter of the decade's total', 'about 60 per cent of the total': the share of a total stated in the sentence.
#: Read from a comma or from the first blank of a run (``(?<!\s)``, possessive runs; integration gate 2): a search from every blank of a long
#: run read the rest of the run each time (72 s for a clause with 16,000 blanks).
_SHARE_OF_TOTAL_RE = re.compile(
    rf"(?:,\s*+|(?<!\s)\s++)(?:(?P<q>{_QUAL})\s++)?(?:(?P<frac>{_FRAC})|(?P<pn>\d+(?:\.\d+)?)\s*{_PCT_UNIT})\s+of\s+(?:the|this|that|its|their)\s+"
    r"(?:(?P<period>decade|year|period|programme|plan|war|era|century|month)(?:'s|’s)\s+)?(?P<noun>total|sum|whole|aggregate|arrivals|figure|amount|number)\b",
    re.IGNORECASE)
#: 'about $2 billion more than France': a difference between two figures the paragraph states for two named parties.
_DIFF_RE = re.compile(rf"{_fig(1)}\s+(?P<cmp>more|less|fewer|higher|lower|larger|smaller|greater)\s+than\s+(?P<other>(?:the\s+)?[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*)*)")
#: A stated length of years: 'for ten years', 'lasted five years', 'had run for more than twelve years', 'which lasted about five years'.
_DUR_VERBS = (r"lasted|lasting|lasts|last|ran|run|running|runs|continued|continuing|continues|endured|enduring|endures|spanned|spanning|spans|persisted|"
              r"persisting|went\s+on|going\s+on")
_DUR_PHRASE_RE = re.compile(rf"\b(?:(?P<verb>{_DUR_VERBS})\s+(?:for\s+)?|for\s+)(?:(?P<q>{_QUAL})\s+)?(?P<n>\d{{1,3}}(?:\.\d+)?|{_WNUM})\s+(?:full\s+|whole\s+|long\s+)?years?\b"
                            r"(?![-'’]|\s+(?:old|of\s+age|each|apiece|at\s+a\s+time|later|earlier|ago|per|running|in\s+a\s+row)\b)", re.IGNORECASE)
_MONTHS_TEXT = "January|February|March|April|May|June|July|August|September|October|November|December"
_MONTH_NUMBER = {m.lower(): i for i, m in enumerate(_MONTHS_TEXT.split("|"), start=1)}
#: A date of a span: a year, a month and year, or a day, month and year ('7 October 1949', 'October 7, 1949').
_SPAN_DATE = (rf"(?:(?:\d{{1,2}}(?:st|nd|rd|th)?\s+)?(?:{_MONTHS_TEXT})\s+(?:\d{{1,2}}(?:st|nd|rd|th)?,?\s+)?)?(?:1[0-9]{{3}}|20[0-9]{{2}})(?![\d,.]?\d)"
              r"(?!\s*(?:per\s*cent|percent|%|million|billion|thousand|seats|votes)\b)")
_ONE_DATE_RE = re.compile(rf"^(?:(?:(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+)?(?P<month>{_MONTHS_TEXT})\s+(?:(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?,?\s+)?)?(?P<year>1[0-9]{{3}}|20[0-9]{{2}})$",
                          re.IGNORECASE)
_SPAN_DATE_RE = re.compile(rf"(?<![\d,.$£€]){_SPAN_DATE}", re.IGNORECASE)
_SPAN_LEAD = r"(?:(?:the\s+)?(?:early|late|mid)[\s-]+|(?:about|around|c\.|ca\.|circa)\s+)?"
#: A span: 'from 1882 to 1892', 'from June 1924 to January 1926', 'between the founding of the GDR on 7 October 1949 and 1961', 'after the
#: GDR's founding on 7 October 1949, until 13 August 1961'. Words before a date end with 'on', 'in' or 'of' and hold no figure.
_DUR_SPAN_RE = re.compile(
    rf"\b(?P<open>from|between|since|after)\s+(?:[^\d;:!?]{{0,80}}?\b(?:on|in|of)\s+)?{_SPAN_LEAD}(?P<d1>{_SPAN_DATE})"
    rf"(?:\s*,)?\s+(?:and|to|until|till|through|up\s+to)\s+(?:[^\d;:!?]{{0,60}}?\b(?:on|in|of)\s+)?{_SPAN_LEAD}(?P<d2>{_SPAN_DATE})", re.IGNORECASE)
#: Days in a year, for an elapsed time stated between day or month dates (the mean Gregorian year).
_DAYS_PER_YEAR = Fraction(3652425, 10000)
#: Half a year: a length stated in whole years and read against day or month dates passes when it rounds the elapsed time.
YEAR_FLOOR = Fraction(1, 2)
_STRICT_LOWER = frozenset({"more than", "over"})
_STRICT_UPPER = frozenset({"less than", "under"})
#: 'Of the $13 billion, the United Kingdom received about $3.2 billion and France about $2.7 billion': a total that opens its clause
#: ('Of the', 'Out of'), its parts after the comma.
_OF_THE_LEAD_RE = re.compile(r"^\s*(?:(?:and|but|so|yet|thus)\s+)?(?:of|out\s+of)\s+(?:(?:the|this|that|its|their)\s+)?(?:(?:total|sum)\s+of\s+)?"
                             r"(?P<lead>[^,;:]{1,80}?)\s*,\s*", re.IGNORECASE)
#: Where the parts after a leading total end: a comparison or a change states no part ('more than in 1881', 'up from', 'against').
_PARTS_STOP_RE = re.compile(r"\b(?:than|against|compared|from|since)\b", re.IGNORECASE)
#: A stated total with its figure ('a total of about 9 billion dollars', 'totalling $5.9 billion', 'in total 790,000', 'a combined $5.9
#: billion'). When no check reads it, it is undecided if its parts are meant but not stated as figures in its clause.
_TOTAL_PHRASE_RE = re.compile(rf"\b(?:a\s+(?:combined\s+)?total\s+of|totall?ing|in\s+total|a\s+combined)\s+(?:(?:about|around|roughly|some|nearly|almost|"
                              rf"over|more\s+than|just\s+over|just\s+under)\s+)?{_CUR}?\s?\d", re.IGNORECASE)
#: The subject of a total that refers to its parts without stating them ('The two received a total of ...', 'Together they had ...').
_PARTS_ANAPHOR_RE = re.compile(r"\b(?:the\s+(?:two|three|four|five|six|pair)|both|these|those|they|between\s+them|together)\b", re.IGNORECASE)
_PART_HINT_RE = re.compile(r"of\s+(?:which|whom|these)\b|\balone\b|\btotal\b|\btotall?ing\b|\bcombined\b|\bsum\b|\bwhole\b|\baggregate\b|\barrivals\b|"
                           r"\d\s?(?:%|per\s?cent|percent)\s+of\s|"
                           r"more\s+than|less\s+than|fewer\s+than|higher\s+than|lower\s+than|larger\s+than|smaller\s+than|greater\s+than|"
                           r"(?:^|;)\s*(?:(?:and|but|so|yet|thus)\s+)?(?:of|out\s+of)\s|\d\s+(?:out\s+)?of\s", re.IGNORECASE)
_MONTH_NOUN_RE = re.compile(r"^(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE)


#: What makes a figure part of a decade, a span or a date ('1930s', '1914-18', '21st'), read at the figure's end (integration gate 2: the
#: rest of the text was copied for every figure, n² steps on a text of many figures); a month name after a count, likewise.
_FIG_SUFFIX_RE = re.compile(r"\s*(?:s\b|-|–|st\b|nd\b|rd\b|th\b)")
_MONTH_AFTER_RE = re.compile(r"\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\b")


def _magnitudes(text: str) -> list[_Fig]:
    """The figures of ``text`` that state an amount: digits (or a currency sign), not a year, not a per cent, not the day of a date."""
    out: list[_Fig] = []
    for m in _LONE_FIG_RE.finditer(text):
        f = _fig_of(m, 1)
        if not f.num[:1].isdigit() or _is_pct(f.unit) or _year_like(f.num, f.unit or f.cur) or _MONTH_NOUN_RE.match(f.noun):
            continue
        if _FIG_SUFFIX_RE.match(text, m.end("n1")) and _year_like(f.num, None):
            continue
        out.append(f)
    return out


def _amounts(clause: str, end: int) -> list[_Fig]:
    """The figures of ``clause[:end]`` that can be a total or a part: :func:`_magnitudes`, less the amount of a derived phrase ('an average
    of about 900,000 a year', 'an increase of 6,500 miles') and a figure stated as a rate ('500,000 a year'), which are no stock of the thing
    counted."""
    spans = [(d.start, d.end) for d in _derived_phrases(clause)]
    return [f for f in _magnitudes(clause[:end]) if not any(a <= f.start < b for a, b in spans) and not _RATE_PHRASE_RE.search(clause[f.start: f.end])]


#: A word after a figure that is a verb, not the noun of the thing counted ('about 790,000 came in 1882', '230 were won'): the noun the
#: amounts are compared on ends before it, so 'Out of about 5.2 million arrivals, about 790,000 came in 1882' compares arrivals with arrivals.
_VERB_WORD_RE = re.compile(r"^(?:[a-z]{2,}(?<!e)ed|came|went|left|got|won|lost|took|gave|made|saw|brought|sent|fell|rose|grew|became|were|was|had|"
                           r"are|is|has|have|did|ran)$")


def _noun_head(noun: str) -> str:
    """The words of a figure's noun before the first verb word ('people came' -> 'people', 'came' -> '')."""
    words: list[str] = []
    for w in noun.lower().split():
        if _VERB_WORD_RE.match(w):
            break
        words.append(w)
    return " ".join(words)


def _amount_pair(whole: _Fig, part: _Fig) -> Optional[str]:
    """Why ``part`` cannot be read against ``whole`` as amounts of one thing, or None when it can."""
    if not _cur_compatible(whole.cur, whole.noun, part.cur, part.noun):
        return f"the currency of '{_shown(part, part.unit)}' and of '{_shown(whole, whole.unit)}' differ"
    kinds = {_unit_kind(whole.unit), _unit_kind(part.unit)} - {None, "scale"}
    if kinds - {"count"}:
        return f"the units of '{_shown(part, part.unit)}' and '{_shown(whole, whole.unit)}' cannot be compared"
    nw, np_ = (_noun_head(whole.noun) if not _cur_of_noun(whole.noun) else ""), (_noun_head(part.noun) if not _cur_of_noun(part.noun) else "")
    if nw and np_ and not _same_noun(nw, np_):
        return f"'{_shown(part, part.unit)}' counts {np_.split()[-1]} while '{_shown(whole, whole.unit)}' counts {nw.split()[-1]}"
    return None


def _entity_figures(name: str, para: str, exclude: tuple[int, int]) -> list[_Fig]:
    """The figures the paragraph states right after the name ``name`` ('France about $2.7 billion', 'the United Kingdom received about
    $3.2 billion'), a verb of receiving and a qualifier at most between them, outside the span ``exclude``."""
    out: list[_Fig] = []
    for m in re.finditer(r"\b" + re.escape(name) + r"\b", para):
        g = _ENTITY_GAP_RE.match(para, m.end())
        f = _LONE_FIG_RE.match(para, g.end() if g else m.end())
        if f is None or exclude[0] <= f.start() < exclude[1]:
            continue
        fig = _fig_of(f, 1)
        if fig.num[:1].isdigit() and not _year_like(fig.num, fig.unit or fig.cur):
            out.append(fig)
    return out


#: What may stand between a party's name and its figure: 'received', 'had', 'was given', 'got'.
_ENTITY_GAP_RE = re.compile(r"(?:\s+(?:had\s+|has\s+|was\s+|were\s+)?(?:received|got|took|obtained|gained|given|granted|allotted|had|spent|lost|with|at))?\s+")


def _stated_figures(text: str) -> list[_Fig]:
    """Every figure ``text`` states, per cents included: digits (or a currency sign), not a year, not the day of a date."""
    out: list[_Fig] = []
    for m in _LONE_FIG_RE.finditer(text):
        f = _fig_of(m, 1)
        if not f.num[:1].isdigit() or _year_like(f.num, f.unit or f.cur) or _MONTH_NOUN_RE.match(f.noun):
            continue
        if _FIG_SUFFIX_RE.match(text, m.end("n1")) and _year_like(f.num, None):
            continue
        out.append(f)
    return out


def _no_pair_reason(clause: str, d: Optional[_Derived]) -> str:
    """Why a derived figure or relation has no figures of its own to be read against: its sentence states no figures at all, or states
    figures that are not a pair it binds to (a total, a lone figure, a per cent), which the reason names."""
    span = (d.start, d.end) if d is not None else (-1, -1)
    figs = [f for f in _stated_figures(clause) if not (span[0] <= f.start < span[1])]
    if not figs:
        return "no figures are stated with it in its sentence"
    working = worked_equations(clause)
    if working:  # 'Result: the krona appreciated by 20.00%' under lines of working: its figures are in the working, not in a pair of words
        return (f"its sentence states its figures only as written arithmetic ('{working[0].phrase[:100]}'), which this reader does not decide, "
                f"and no pair of figures in words it can be read against")
    shown = [_shown(f, f.unit).replace(" %", "%") for f in figs[:3]]
    return f"its sentence states no pair of figures it can be read against (only {', '.join(shown)})"


#: An arithmetic operator between two figures of written working ('+', '−', '×', '÷', '/', '*', '^', '·', or a spaced hyphen or dash), up to
#: two unit words between the first figure and the operator ('105 million litres ×', '2.4 Ω +'); a figure with a letter attached ('6t') is a term
#: of algebra, not a figure, and the end of a range label ('aged 15–64 × 100') is no operand.
_OPERATOR_BETWEEN_RE = re.compile(r"(?<![\d.,])(?<!\d[–-])\d[\d,.]*[ \t]?%?(?:[ \t][A-Za-zΩµμ°³²⁻¹]{1,12}\.?){0,2}[ \t]?\){0,3}[ \t]?(?:[+×÷*/^·]|[ \t][-–][ \t]|−)[ \t]?\({0,3}[ \t]?(?:US)?[$£€¥]?[ \t]?[-−]?[ \t]?\({0,3}(?:US)?[$£€¥]?\d[\d,.]*(?![\d,.A-Za-zα-ω])")
#: A restatement in brackets inside a line of working: an '=' and a word of three letters, and no arithmetic operator ('(762 thousand =
#: 0.762 million)', '(1 tonne = 1,000 kg)'). Bounded: at most 120 characters inside the brackets, each lookahead too.
_EQ_COMMENT_RE = re.compile(r"\((?=[^()\n]{0,120}?=)(?=[^()\n]{0,120}?[A-Za-z]{3})[^()\n+×÷*/−–^\-]{1,120}\)")
#: The result of a link of a worked equation: a figure (a sign or a currency sign before it allowed; a plus sign too, '= +$53,900').
_RESULT_START_RE = re.compile(r"^[ \t]?\$?[ \t]?[-+\u2212]?[ \t]?(?:US)?[$£€¥]?[ \t]?[-+\u2212]?\d")
#: A line that continues the equation of the line before it ('= 20 ÷ 10').
_CONTINUATION_LINE_RE = re.compile(r"^\s*(?:\$\s*)?[=≈]")
#: The reason a worked equation is reported undecided (``CORE-QNT-001``): written arithmetic in '=' form has no reader on this branch.
WORKED_EQUATION_REASON = "it is written arithmetic in '=' form (a worked equation), which this branch's prose arithmetic reader does not decide"


@dataclass(frozen=True)
class WorkedEquation:
    """One worked equation of a text: ``line`` is its whole line (with its '=' continuation lines), from ``start`` to ``end`` of the text;
    ``statement`` the statement of the line that holds it (a line is cut at semicolons and full stops); ``phrase`` the arithmetic it states,
    from the first link that computes to the stated result ('$6,000 ÷ $2.00 = 3,000 loaves per month')."""
    start: int
    end: int
    line: str
    statement: str
    phrase: str


#: Where a line of working holds several statements: a semicolon, or a full stop before a capital or a figure ('Table 1. 4,200 × 12 = ...').
_WORKING_SEGMENT_RE = re.compile(r";\s*|(?<=[.!?])\s+(?=[A-Z0-9(])")
#: Where the stated result of a link ends: a comma or full stop before a space, or an opening bracket ('$192.00 million per year (no tax, ...'),
#: or the closing bracket of working written in brackets inside a sentence ('a threefold increase (16.2 ÷ 5.4 = 3.0).': round 9, c2).
_RESULT_END_RE = re.compile(r",\s|\.\s|\s\(|;|[”\"’]|\)")
#: The opening bracket of working written in brackets inside a sentence, before the working's first figure: the phrase starts after it.
_OPEN_WORKING_RE = re.compile(r"\((?=[^()]*$)")
#: Where the words before the arithmetic of a link end ('Check: $31.50 million + ...', 'Answer: 2,000').
_LINK_LEAD_END_RE = re.compile(r".*(?::\s|\.\s)")


def worked_equations(text: str) -> list[WorkedEquation]:
    """Every worked equation of ``text``: a statement of a line (with the lines after it that open with '=' or '≈'; a line's statements are
    cut at semicolons and full stops) whose '=' links put an arithmetic operator between two figures before a link whose value is a figure
    with no further arithmetic ('$6,000 ÷ $2.00 = 3,000 loaves', '(12 − 8) − 0 = 4', '= 31 ÷ 69 × 100 = 44.9'). A formula with no figures
    on both sides of an operator ('Dependency ratio = (aged 0–14 + aged 65 and over) ÷ aged 15–64'), an expression of algebra ('a = 6 − 6t')
    and a stated value ('PED = −0.67') are not worked equations. A restatement in brackets that holds an '=' and words and no operator
    ('(762 thousand = 0.762 million)', :data:`_EQ_COMMENT_RE`) cuts no link: it is set aside before the links are cut, and the
    statement keeps it as written."""
    out: list[WorkedEquation] = []
    if "=" not in text and "≈" not in text:
        return out
    lines: list[tuple[int, int]] = []
    pos = 0
    for raw in text.split("\n"):
        start, end = pos, pos + len(raw)
        pos = end + 1
        if lines and _CONTINUATION_LINE_RE.match(raw):
            lines[-1] = (lines[-1][0], end)
        else:
            lines.append((start, end))
    for start, end in lines:
        line = text[start:end]
        if "=" not in line and "≈" not in line:
            continue
        shown_line = " ".join(line.split())
        cuts = [0] + [m.end() for m in _WORKING_SEGMENT_RE.finditer(line)] + [len(line)]
        for a, b in zip(cuts, cuts[1:]):
            statement = " ".join(line[a:b].split())  # one space between words: every pattern below reads at most one blank in a row
            segment = statement
            if "(" in segment and "=" in segment:
                # a restatement in brackets inside the working ('0.762 million ÷ 12.70 million × 100 (762 thousand = 0.762 million) = 6.50%'):
                # its '=' is no link of the chain, so it is set aside before the links are cut; the statement keeps it, as written (c1
                # adversarial ec-t14-unemp)
                segment = " ".join(_EQ_COMMENT_RE.sub(" ", segment).split())
            bounds = [-1] + [m.start() for m in re.finditer(r"[=≈]", segment)] + [len(segment)]
            links = [segment[x + 1: y] for x, y in zip(bounds, bounds[1:])]
            if len(links) < 2:
                continue
            # the first link with an operator between two figures, kept as the links are read: each link is searched once, so a chain
            # of n '=' links costs n searches (the earliest such link before link k was searched for again at every k, n² searches;
            # integration gate 1, parser-safety-12)
            first: Optional[int] = None
            for k in range(1, len(links)):
                if first is None and _OPERATOR_BETWEEN_RE.search(links[k - 1]):
                    first = k - 1
                # a result is a figure with no further arithmetic in its link ('3,000 loaves per month', '−4 A1'); '6 − 6t' or
                # '4000(1 + 0.036)^5' is an expression, not a stated result
                if not (_RESULT_START_RE.match(links[k]) and not _OPERATOR_BETWEEN_RE.search(links[k])):
                    continue
                if first is None:
                    continue
                lead = _LINK_LEAD_END_RE.match(links[first])
                p_start = bounds[first] + 1 + (lead.end() if lead else 0)
                # working written in brackets inside a sentence ('This is a threefold increase (16.2 ÷ 5.4 = 3.0).'): the phrase starts after
                # the bracket that opens it, before its first figure, so the words before it are no label of the line (round 9, c2 ge-p9c)
                opened = _OPEN_WORKING_RE.search(segment, p_start, bounds[first + 1])
                if opened is not None and _OPERATOR_BETWEEN_RE.search(segment, opened.end(), bounds[first + 1]):
                    p_start = opened.end()
                stop = _RESULT_END_RE.search(links[k])
                p_end = bounds[k] + 1 + (stop.start() if stop else len(links[k]))
                out.append(WorkedEquation(start, end, shown_line, statement, segment[p_start:p_end].strip().rstrip(" .,;:")))
                break
    return out


_RATE_PHRASE_RE = re.compile(r"\b(?:a|an|per|each|every)\s+(?:year|annum|month|week|day|head|capita)\b|\bannually\b", re.IGNORECASE)


def _total_rate_spec(clause: str, d: _Derived, tolerance: Fraction) -> tuple[Optional[_Spec], str]:
    """'About 5.2 million people entered the United States in the 1880s, an average of about 900,000 a year': a yearly rate stated after the
    one total its clause dates by a decade (ten years) or a span ('from 1881 to 1890': nine or ten years, either count accepted) is that
    total over those years (a decade dates the decade's total, never an annual point). ``(None, '')`` when the clause states no such
    total; ``(None, reason)`` when the rate and the total cannot be compared."""
    if d.kind != "rate_change" or d.per not in ("year", "annum"):
        return None, ""
    head = clause[: d.start]
    if len(_magnitudes(head)) != 1:
        return None, ""
    figs = _amounts(clause, d.start)
    if len(figs) != 1:
        return None, ""  # the one figure before it is itself a rate ('500,000 a year in the 1880s') or a derived amount, not a total
    total = figs[0]
    decades = list(_DECADE_TOKEN_RE.finditer(head))
    span = _YEAR_SPAN_RE.search(head)
    years = {int(y) for y in _YEAR_TOKEN_RE.findall(head)}
    if len(decades) == 1 and span is None and all(int(decades[0].group("d")) <= y < int(decades[0].group("d")) + 10 for y in years):
        counts, over = (10,), f"'{decades[0].group(0).strip()}' (ten years)"
    elif span is not None and not decades and int(span.group(2)) > int(span.group(1)):
        y1, y2 = int(span.group(1)), int(span.group(2))
        counts, over = (y2 - y1, y2 - y1 + 1), f"{y1} to {y2} ({y2 - y1} or {y2 - y1 + 1} years, counted either way)"
    else:
        return None, ""
    shown = _shown(total, total.unit)
    if (d.cur or total.cur or _cur_of_noun(total.noun) or _cur_of_noun(d.noun)) and not _cur_compatible(total.cur, total.noun, d.cur, d.noun):
        return None, f"the currency of '{d.words}' and of the total it averages ({shown}) differ"
    if {_unit_kind(d.unit), _unit_kind(total.unit)} - {None, "scale", "count"}:
        return None, f"the unit of '{d.words}' and of the total it averages ({shown}) cannot be compared"
    if d.noun and total.noun and not ({w.rstrip("s") for w in d.noun.lower().split()} & {w.rstrip("s") for w in total.noun.lower().split()}):
        return None, f"'{d.words}' counts {d.noun.split()[-1]} while the total it averages ({shown}) counts {total.noun}"
    premises = (("TOTAL", {"op": "eq", "left": _v("total"), "right": _real(_frac(total.num, total.unit))}, f"total = {shown}"),)
    rates = [_within({"op": "div", "left": _v("total"), "right": _real(Fraction(n))}, d.stated, tolerance, Fraction(0), d.side) for n in counts]
    concl = rates[0] if len(rates) == 1 else {"op": "or", "args": rates}
    label = f"stated average of {_fmt(d.stated)} a year against the total {shown} over {over}"
    return _Spec("rate_change", clause.strip(), (("total", "the total as stated"),), premises, ("STATED_RATE", concl, label), Fraction(0), d.side,
                 "figure stated in the report itself", f"a yearly average of the total its clause dates by {over}", d.words), ""


#: The party whose share a phrase states: '..., so the United Kingdom alone received about two-thirds of the total'.
#: The party's name is read up to twelve capitalised words, as in :data:`_ALONE_RE` (integration gate 2).
_SHARE_PARTY_RE = re.compile(r"(?P<who>(?:the\s+)?[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*){0,11})\s+(?:alone\s+|itself\s+)?(?:had\s+|has\s+)?"
                             r"(?:received|got|took|obtained|absorbed|accounted\s+for|was\s+given|was\s+granted|was\s+allotted|gained|brought|sent|admitted)\s*$")


def _party_share(clause: str, head: str, para: str, phrase_span: tuple[int, int]) -> tuple[str, Optional[_Fig], Optional[_Fig], str]:
    """For a share stated with no figure right before it: ``(party, part, total, reason)``. The part is the one figure the paragraph states
    for the party named before the share ('the United Kingdom alone received about two-thirds of the total': 'the United Kingdom received
    about $3.2 billion'); the total is the figure the clause's parts are stated 'of which', else the one other figure of the clause. The
    reason says which of them could not be read."""
    pm = _SHARE_PARTY_RE.search(head)
    if pm is None:
        return "", None, None, "the part it is a share of is not stated as a figure right before it, and no party with a stated figure is named before it"
    who = re.sub(r"^the\s+", "", pm.group("who"))
    at = para.find(clause)
    exclude = (at + phrase_span[0], at + phrase_span[1]) if at >= 0 else (0, 0)
    found = {(_frac(f.num, f.unit), f.cur): f for f in _entity_figures(who, para, exclude)}
    if len(found) != 1:
        return who, None, None, (f"the paragraph states {'no figure' if not found else f'{len(found)} different figures'} for {who}, so the share stated for it "
                                 f"could not be read against a part")
    part = next(iter(found.values()))
    of_which = _OF_WHICH_RE.search(clause)
    wholes = _amounts(clause, of_which.start()) if of_which is not None else [f for f in _amounts(clause, len(head)) if (f.num, f.cur, f.unit) != (part.num, part.cur, part.unit)]
    if of_which is None and len(wholes) != 1:
        return who, part, None, f"the total the share of {who} is stated against is not stated as one figure in its sentence"
    if not wholes:
        return who, part, None, "the total it is a share of is not stated as a figure before its parts"
    return who, part, wholes[-1], ""


def _sum_expr(names: list[str]) -> dict:
    return _v(names[0]) if len(names) == 1 else {"op": "add", "args": [_v(n) for n in names]}


#: '356 of the 535 seats, about three-quarters', '3.2 million of the 5.2 million arrivals (about 60 per cent)': a part, the whole it is
#: stated 'of', and the share stated right after them.
_N_OF_M_SHARE_RE = re.compile(
    rf"(?<![\w.,])(?P<cp>{_CUR})?\s?(?P<np>{_NUMX})(?:\s*(?P<up>{_SCALE_UNIT})\b)?\s+(?:out\s+)?of\s+(?:(?:the|its|their|all(?:\s+the)?)\s+)?"
    rf"(?:(?:about|around|roughly|some|nearly)\s+)?(?P<cw>{_CUR})?\s?(?P<nw>{_NUMX})(?:\s*(?P<uw>{_SCALE_UNIT})\b)?(?P<noun>{_NOUN})"
    rf"\s*(?:,|\()\s*(?:or\s+|that\s+is\s+|i\.e\.\s+)?(?:(?P<q>{_QUAL})\s+)?(?:(?P<frac>{_FRAC})|(?P<pn>\d+(?:\.\d+)?)\s*{_PCT_UNIT})(?![\w-])",
    re.IGNORECASE)
#: A part stated as a share of a whole whose figure the clause states after 'of' (round-8 clearance c1, critical finding: a wrong per
#: cent in prose crossed silently): '$40m, which is 25% of total sales of $200m', 'Labour costs of $30,000 are 30% of total costs of
#: $120,000', 'Exports came to $40m, or 20 per cent of the $200m total' is read by _N_OF_M_SHARE_RE's kin below. Neither figure is a per
#: cent. Every run is bounded, so a search is linear in the clause.
_IS_SHARE_OF_RE = re.compile(
    rf"(?<![\w.,])(?P<cp>{_CUR})?\s?(?P<np>{_NUMX})(?:\s*(?P<up>{_SCALE_UNIT})\b)?(?![ \t]{{0,3}}(?:per[ \t]?cent|percent|%))"
    rf"(?:[ \t]{{1,3}}[a-z][a-z'’-]*){{0,3}}?[ \t]{{0,3}},?[ \t]{{1,3}}(?:(?:which|that)[ \t]{{1,3}})?"
    rf"(?:is|was|are|were|represents?|represented|makes?[ \t]up|made[ \t]up|accounts?[ \t]for|accounted[ \t]for|equals?|equalled|equaled|comes?[ \t]to|came[ \t]to)[ \t]{{1,3}}"
    rf"(?:(?P<q>{_QUAL})[ \t]{{1,3}})?(?P<pn>\d+(?:\.\d+)?)[ \t]{{0,3}}{_PCT_UNIT}[ \t]{{1,3}}of[ \t]{{1,3}}(?:(?:the|its|their|all(?:[ \t]the)?)[ \t]{{1,3}})?"
    rf"(?:[a-z][a-z'’-]*[ \t]{{1,3}}){{0,4}}?(?:of[ \t]{{1,3}})?(?P<cw>{_CUR})?\s?(?P<nw>{_NUMX})(?:\s*(?P<uw>{_SCALE_UNIT})\b)?"
    rf"(?![ \t]{{0,3}}(?:per[ \t]?cent|percent|%))(?P<noun>{_NOUN})",
    re.IGNORECASE)
#: The share stated in brackets a few words after a part ('Of the 60 households surveyed, 27 owned a car (45%)'): the part's own
#: sentence states it, the whole opens the clause.
_PAREN_SHARE_AFTER_RE = re.compile(
    rf"(?:[ \t]{{1,3}}[a-z][a-z'’-]*){{1,6}}?[ \t]{{0,3}}\([ \t]{{0,3}}(?:(?P<q>{_QUAL})[ \t]{{1,3}})?(?P<pn>\d+(?:\.\d+)?)[ \t]{{0,3}}{_PCT_UNIT}[ \t]{{0,3}}\)",
    re.IGNORECASE)
#: A share stated right after a part, with no 'of the total' ('..., the list was guaranteed 356, about three-quarters').
_BARE_SHARE_TAIL_RE = re.compile(
    rf"\s*(?:,|\()\s*(?:or\s+)?(?:(?P<q>{_QUAL})\s+)?(?:(?P<frac>{_FRAC})|(?P<pn>\d+(?:\.\d+)?)\s*{_PCT_UNIT})(?![\w-])"
    r"(?=\s*(?:[,;.)]|$|\s+of\s+(?:them|these|those|it|the\s+(?:total|whole|seats|votes))\b|\s+(?:and|but|while)\b))", re.IGNORECASE)


def _share_fig(m: "re.Match[str]", side: str) -> _Fig:
    """The part (``side`` 'p') or the whole ('w') of an 'N of the M' share, as a figure (the noun is the whole's)."""
    unit = m.group(f"u{side}")
    noun = (m.group("noun") or "").strip() if side == "w" else ""
    return _Fig(m.group(f"n{side}"), unit, noun, "", m.start(f"n{side}"), m.end(f"n{side}"), _cur_key(m.group(f"c{side}") or ""))


def _share_spec(clause: str, whole: _Fig, part: _Fig, frac: Optional[str], pn: Optional[str], qualifier: Optional[str], tolerance: Fraction, phrase: str,
                basis: str = "") -> tuple[Optional[_Spec], str]:
    """The check of a stated share (a word fraction or a per cent) of ``whole`` held by ``part``: part / whole within the tolerance
    rule of the stated share, or ``(None, reason)`` when the two figures cannot be compared."""
    why = _amount_pair(whole, part)
    if why:
        return None, why
    wv, pv = _frac(whole.num, whole.unit), _frac(part.num, part.unit)
    if wv == 0:
        return None, ""
    side = _side(qualifier)
    premises = (("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(wv)}, f"total = {_shown(whole, whole.unit)}"),
                ("PART", {"op": "eq", "left": _v("part"), "right": _real(pv)}, f"part = {_shown(part, part.unit)}"))
    ratio = {"op": "div", "left": _v("part"), "right": _real(wv)}
    if frac:
        key = re.sub(r"^(?:a|one)\s+", "", frac.lower()).replace("-", " ")
        stated = _FRACTION_WORDS[key]
        concl = _within(ratio, stated, tolerance, Fraction(0), side)
        floor = Fraction(0)
        label = f"stated share '{frac}' (= {stated}) of the total against part / total"
    else:
        stated = _number(pn or "0")
        concl = _within({"op": "mul", "args": [_real(Fraction(100)), ratio]}, stated, tolerance, POINT_FLOOR, side)
        floor = POINT_FLOOR
        label = f"stated share of {_fmt(stated)} per cent of the total against 100 * part / total"
    return _Spec("share", clause.strip(), (("whole", "the total as stated"), ("part", "the part as stated")), premises,
                 ("STATED_SHARE", concl, label), floor, side, "figure stated in the report itself", basis, phrase), ""


#: The most part markers ('of which', '<party> alone', a share of the total, 'N of the M', a difference between named parties) a clause is
#: read for (integration gate 2): each reads the clause before it again (its amounts and derived phrases, the paragraph's figures for a
#: party), so a clause of thousands of them cost n² steps (256 s for a clause of 'of which' at 32,000 characters). A real clause states a
#: few; a clause over the bound is reported undecided with this reason (``CORE-QNT-001``), never read in part.
_MAX_CLAUSE_PART_MARKERS = 16
_TOO_MANY_PARTS_REASON = (f"it states more than {_MAX_CLAUSE_PART_MARKERS} parts, shares or differences of a total, more than a clause is read "
                          f"for, so none of them was read")


def _part_markers_over_bound(clause: str) -> bool:
    """True when ``clause`` holds more than :data:`_MAX_CLAUSE_PART_MARKERS` part markers (counted up to the bound)."""
    count = 0
    for pattern in (_OF_WHICH_RE, _ALONE_RE, _SHARE_OF_TOTAL_RE, _N_OF_M_SHARE_RE, _IS_SHARE_OF_RE, _DIFF_RE):
        for _m in pattern.finditer(clause):
            count += 1
            if count > _MAX_CLAUSE_PART_MARKERS:
                return True
    return False


# ------------------------------------------------------------------ prose arithmetic of round 9 (c2): products, rates, shares, point gaps
#
# Each reader below reads one closed shape of a sentence stated in words and decides it as an exact entailment problem under the
# tolerance rule (round 9, c2: wrong arithmetic in these shapes crossed the hub with no finding, or named only as 'not checked'):
#
# * a count times an amount each, stated as a total: 'Four criteria of 6 marks each give a total of 26 marks' (4 × 6 against 26);
# * a rate over periods, stated as a total: 'Thirteen years at £90,000 a year comes to £1.71 million' (13 × £90,000), 'At £4 a month a
#   year costs £52' (12 × £4);
# * a gap in percentage points between the two per cents its clause states: '... 228 of 1,200 (19%) and 54 of 1,800 (3%), a difference
#   of 18 percentage points' (19 − 3);
# * a share stated after the part and the whole it is of: '$18,000 of the $300,000 increase in market sales, which is 8.0% of the
#   growth', '$40m of a market of $200m, a share of 25%', '$40m in a market worth $200m, so its market share is 25%', 'market share is
#   25% ($40m of $200m)';
# * a multiple compared across the two counts its clause states: 'Site A recorded 40 pedestrians and site B recorded 120, so site B had twice
#   as many as site A' (the larger over the smaller; a failure is a warning, since which figure is which is the reader's);
# * a per cent change followed by its working in brackets: 'grew by 38.0% (1,050 ÷ 820)', 'rose by 5.29% (131.4 ÷ 124.8 − 1)', 'an
#   increase of 82.0% ((567.0 − 311.6) ÷ 311.6 × 100)': the bracket read as the growth factor, the fractional change or the per cent
#   itself, the check failing only when no reading holds.
#
# Every pattern is anchored at a figure or a fixed word and every run in it is bounded or possessive; each reader runs only on a
# sentence that holds its fixed words, so the readers are linear in the text.

_C2_FIG = rf"(?:{_DIGITS})"
_C2_COUNT = rf"(?:{_DIGITS}|{_WNUM})"
_C2_SCALE = rf"(?:\s*+(?:{_SCALE_UNIT})\b)?"
_C2_TOTAL_VERB = (r"(?:gives?|gave|make|makes|made|comes?\s++to|came\s++to|totals?|totall?ed|adds?\s++up\s++to|added\s++up\s++to|amounts?\s++to"
                  r"|amounted\s++to|is|are|was|were|equals?|costs?)")
#: 'Four criteria of 6 marks each give a total of 26 marks'.
_EACH_TOTAL_RE = re.compile(
    rf"(?<![\w.,$£€¥])(?P<n>{_C2_COUNT})\s++(?:[a-z][a-z'’-]*+\s++){{1,3}}?(?:of|at|worth|carrying)\s++(?P<mc>{_CUR})?\s?(?P<m>{_C2_FIG})(?P<mu>{_C2_SCALE})"
    rf"\s++(?P<unit>[a-z][a-z'’-]*+)\s++each\b[^.;:]{{0,40}}?\b{_C2_TOTAL_VERB}\s++(?:a\s++total\s++of\s++)?(?:(?P<q>{_QUAL})\s++)?"
    rf"(?P<tc>{_CUR})?\s?(?P<t>{_C2_FIG})(?P<tu>{_C2_SCALE})(?![\d.,]?\d)",
    re.IGNORECASE)
#: 'Thirteen years at £90,000 a year comes to £1.71 million'.
_PERIODS_AT_RATE_RE = re.compile(
    rf"(?<![\w.,$£€¥])(?P<n>{_C2_COUNT})\s++(?P<per>years?|months?|weeks?|days?|quarters?|hours?)\s++at\s++(?:(?P<q1>{_QUAL})\s++)?(?P<xc>{_CUR})?\s?"
    rf"(?P<x>{_C2_FIG})(?P<xu>{_C2_SCALE})\s++(?:a|an|per|each|every)\s++(?P<per2>year|month|week|day|quarter|hour)\b\s*+,?\s*+{_C2_TOTAL_VERB}\s++"
    rf"(?:a\s++total\s++of\s++)?(?:(?P<q>{_QUAL})\s++)?(?P<zc>{_CUR})?\s?(?P<z>{_C2_FIG})(?P<zu>{_C2_SCALE})(?![\d.,]?\d)",
    re.IGNORECASE)
#: 'At £4 a month a year costs £52', 'at $20 a week, a year comes to $1,040'.
_AT_RATE_PERIOD_RE = re.compile(
    rf"\bat\s++(?:(?P<q1>{_QUAL})\s++)?(?P<xc>{_CUR})?\s?(?P<x>{_C2_FIG})(?P<xu>{_C2_SCALE})\s++(?:a|an|per|each|every)\s++(?P<per1>day|week|month|quarter|year)\b"
    rf"(?:\s*+,\s*+|\s++)(?:a|one|each|every|the|per)\s++(?P<per2>week|month|quarter|year)\s++(?:of\s++(?:it|them|membership|payments?)\s++)?{_C2_TOTAL_VERB}\s++"
    rf"(?:(?P<q>{_QUAL})\s++)?(?P<zc>{_CUR})?\s?(?P<z>{_C2_FIG})(?P<zu>{_C2_SCALE})(?![\d.,]?\d)",
    re.IGNORECASE)
#: Whole periods of a longer period: only the exact ones ('a month' to 'a year' is twelve; 'a week' to 'a month' is no whole count).
_PERIODS_IN = {("day", "week"): 7, ("week", "year"): 52, ("month", "year"): 12, ("quarter", "year"): 4, ("day", "year"): 365, ("month", "quarter"): 3}
#: 'a difference of 18 percentage points', 'a gap of about 16 percentage points'.
_PP_GAP_RE = re.compile(rf"\b(?:an?\s++)?(?:difference|gap|margin|spread)\s++of\s++(?:(?P<q>{_QUAL})\s++)?(?P<d>\d{{1,3}}(?:\.\d{{1,4}})?)\s++percentage[ -]points?\b",
                        re.IGNORECASE)
_PCT_FIG_RE = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{1,4})?)\s*+(?:%|per\s?cent\b|percent\b)(?!\s*+points?\b)", re.IGNORECASE)
_SHARE_PART = rf"(?<![\w.,])(?P<cp>{_CUR})?\s?(?P<np>{_C2_FIG})(?:\s*+(?P<up>{_SCALE_UNIT})\b)?"
_SHARE_WHOLE = rf"(?P<cw>{_CUR})?\s?(?P<nw>{_C2_FIG})(?:\s*+(?P<uw>{_SCALE_UNIT})\b)?"
_SHARE_PN = rf"(?:(?P<q>{_QUAL})\s++)?(?P<pn>\d{{1,3}}(?:\.\d{{1,4}})?)\s*+{_PCT_UNIT}"
_SHARE_IS = r"(?:is|was|are|were|represents?|represented|makes?\s++up|made\s++up|accounts?\s++for|accounted\s++for|equals?|comes?\s++to|came\s++to)"
#: Shares stated after their part and their whole (module comment above). Each opens at the part's figure.
_C2_SHARE_RES = (
    # '$18,000 of the $300,000 increase in market sales, which is 8.0% of the growth'
    re.compile(rf"{_SHARE_PART}\s++of\s++(?:the|its|their|a|an|all)\s++{_SHARE_WHOLE}(?P<noun>(?:\s++[a-z][a-z'’-]*+){{0,6}}?)\s*+,\s*+(?:which|that|this)\s++"
               rf"{_SHARE_IS}\s++{_SHARE_PN}", re.IGNORECASE),
    # '$40m of a market of $200m, a share of 25%'
    re.compile(rf"{_SHARE_PART}\s++of\s++(?:the|its|their|a|an)\s++(?:[a-z][a-z'’-]*+\s++){{0,2}}?(?:of|worth)\s++{_SHARE_WHOLE}(?P<noun>)\s*+,\s*+"
               rf"(?:giving\s++(?:it\s++)?|for\s++|or\s++)?an?\s++(?:market\s++)?share\s++of\s++{_SHARE_PN}", re.IGNORECASE),
    # '$40m of the $200m market, a share of 25%' (round 9 second pass, c1 stem-integration#33: the whole right after its determiner, the share
    # after a comma, as the first shape's 'which is')
    re.compile(rf"{_SHARE_PART}\s++of\s++(?:the|its|their|a|an|all)\s++{_SHARE_WHOLE}(?P<noun>(?:\s++[a-z][a-z'’-]*+){{0,6}}?)\s*+,\s*+"
               rf"(?:giving\s++(?:it\s++)?|for\s++|or\s++)?an?\s++(?:market\s++)?share\s++of\s++{_SHARE_PN}", re.IGNORECASE),
    # '$40m in a market worth $200m, so its market share is 25%'
    re.compile(rf"{_SHARE_PART}\s++(?:[a-z][a-z'’-]*+\s++){{0,3}}?in\s++an?\s++(?:[a-z][a-z'’-]*+\s++){{0,2}}?market\s++(?:worth|of)\s++{_SHARE_WHOLE}(?P<noun>)\s*+,?\s*+"
               rf"(?:so|giving|which\s++gives|and)\s++(?:it\s++|its\s++|the\s++firm['’]s\s++)?(?:a\s++)?(?:market\s++)?share\s++(?:is|was|of)\s++{_SHARE_PN}", re.IGNORECASE),
)
#: 'market share is 25% ($40m of $200m)': the share first, the part and the whole in brackets after it.
_SHARE_BRACKETED_RE = re.compile(
    rf"\bshare\s++(?:is|was|of)\s++{_SHARE_PN}\s*+\(\s*+(?P<cp>{_CUR})?\s?(?P<np>{_C2_FIG})(?:\s*+(?P<up>{_SCALE_UNIT})\b)?\s++of\s++(?:the\s++|a\s++)?"
    rf"{_SHARE_WHOLE}(?P<noun>)\s*+\)", re.IGNORECASE)
#: A multiple stated as a comparison of two counts its clause states before it ('Site A recorded 40 pedestrians and site B recorded 120, so
#: site B had twice as many as site A'): 'N times as many/much/large as', 'twice as many as'.
_TIMES_AS_RE = re.compile(rf"\b(?:(?P<q>{_QUAL})\s++)?(?:(?P<n>(?<![\d.,])\d+(?:\.\d+)?|{_WNUM})\s++times|(?P<twice>twice|thrice))\s++as\s++(?:many|much|large|big|high|great|long)\b"
                          r"(?:\s++[a-z]+){0,2}?\s++as\b", re.IGNORECASE)
_COUNT_FIG_RE = re.compile(r"(?<![\w.,$£€¥])(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.,]?\d|\s*+(?:%|per\s?cent))")
#: A per cent change followed right after by its working in brackets ('grew by 38.0% (1,050 ÷ 820)'): the bracket holds figures and
#: operators only (an operator at least), at most 120 characters, one level of inner brackets.
_PCT_THEN_WORKING_RE = re.compile(
    rf"(?P<lead>(?:\b(?:rose|grew|increased|climbed|fell|dropped|declined|decreased|shrank|went\s++up|went\s++down)\s++by"
    rf"|\b(?:an?\s++)?(?:increase|rise|growth|fall|decrease|decline|drop|reduction)\s++of)\s++(?:(?P<q>{_QUAL})\s++)?)"
    rf"(?P<pct>\d{{1,4}}(?:\.\d{{1,4}})?)\s*+{_PCT_UNIT}\s*+\((?P<work>(?:[^()\n]|\([^()\n]{{0,60}}\)){{1,120}}?)\)",
    re.IGNORECASE)
_WORKING_ONLY_RE = re.compile(r"^[\s\d.,()+\-−–×÷*/x$£€¥%]+$")
_FALL_LEAD_RE = re.compile(r"fell|dropped|declined|decreased|shrank|down|fall|decrease|decline|drop|reduction", re.IGNORECASE)


def _c2_count(num: str) -> Optional[Fraction]:
    """A count in digits or words ('Four', '13'), or None when it is not a whole positive count."""
    try:
        v = _number(num)
    except (ValueError, ZeroDivisionError, FigureTooLarge):
        return None
    return v if v > 0 and v.denominator == 1 else None


def _c2_amount(cur: Optional[str], num: str, unit: Optional[str]) -> tuple[Fraction, str]:
    """The value of an amount ('£90,000', '$1.71 million') and how it is shown."""
    u = (unit or "").strip()
    return _frac(num, u or None), " ".join(x for x in (f"{(cur or '').strip()}{num}", u) if x)


def _c2_product_spec(clause: str, phrase: str, factors: list[tuple[str, Fraction, str]], stated: Fraction, shown_total: str, qualifier: Optional[str],
                     tolerance: Fraction, kind: str, label: str) -> _Spec:
    """``factors`` multiplied against the stated total within the tolerance rule (the first factors as constants, the last as a variable,
    so the product is linear)."""
    *consts, (name, value, meaning) = factors
    symbols = ((name, meaning),)
    premises = ((name.upper(), {"op": "eq", "left": _v(name), "right": _real(value)}, f"{meaning} = {_fmt(value)}"),)
    product = {"op": "mul", "args": [*(_real(v) for _n, v, _m in consts), _v(name)]}
    label = f"{label}: {' × '.join(f'{_fmt(v)} ({m})' for _n, v, m in factors)}"
    side = _side(qualifier)
    return _Spec(kind, clause.strip(), symbols, premises, ("STATED_TOTAL", _within(product, stated, tolerance, Fraction(0), side),
                 f"{label} ({shown_total}) against the product of its stated figures"), Fraction(0), side, "figure stated in the report itself", "", phrase)


def _c2_bracket_change_spec(clause: str, m: "re.Match[str]", tolerance: Fraction) -> tuple[Optional[_Spec], str]:
    """The per cent change ``m`` states against its working in brackets, read as the growth factor (a ÷ b), the fractional change or the
    per cent itself: the check fails only when the stated per cent lies outside its band under every reading. ``(None, why)`` when the
    working cannot be read (a figure the expression reader refuses, a quotient by an expression)."""
    work = m.group("work")
    if not _WORKING_ONLY_RE.match(work) or not re.search(r"\d\s*+[×÷*/+\-−–x]\s*+\(?\s*+\d", work):
        return None, ""
    from . import worked as _w  # the expression reader of the worked equations (imported here: worked imports this module)
    try:
        tree = _w._Parser(_w._tokens(work)).parse()
        expr, closed = _w._Encoder("", False).enc(tree, work)
    except Exception:  # noqa: BLE001 - never an exception on agent text: the bracket is not read
        return None, "its working in brackets is outside the written-arithmetic reading"
    if not closed:
        return None, "its working in brackets divides by an expression, which this reader does not decide"
    stated = _number(m.group("pct"))
    fall = bool(_FALL_LEAD_RE.search(m.group("lead")))
    side = _side(m.group("q"))
    as_written = expr
    as_fraction = {"op": "mul", "args": [_real(Fraction(100)), expr]}
    factor = {"op": "sub", "left": {"op": "mul", "args": [_real(Fraction(100)), _v("c")]}, "right": _real(Fraction(100))}
    if fall:
        factor = {"op": "neg", "arg": factor}
    places = _written_places(m.group("pct"), stated)
    tol = tolerance
    c = _v("c")
    readings = (c, {"op": "mul", "args": [_real(Fraction(100)), c]}, factor)
    del as_written, as_fraction
    bands = [_within(e, stated, tol, POINT_FLOOR if not places else Fraction(0), side) for e in readings]
    concl = {"op": "or", "args": bands}
    phrase = " ".join(m.group(0).split())
    label = (f"stated {'fall' if fall else 'change'} of {_fmt(stated)} per cent against its working in brackets ({' '.join(work.split())}), read as the "
             f"per cent itself, as the fractional change or as the growth factor (the check fails only when no reading holds)")
    return _Spec("percent_change", clause.strip(), (("c", "the value of the working in brackets, as written"),),
                 (("C_DEF", {"op": "eq", "left": c, "right": expr}, f"c = {' '.join(work.split())}"),), ("STATED_CHANGE", concl, label), POINT_FLOOR, side,
                 "figure stated in the report itself", "the working in brackets after the stated per cent", phrase), ""


def _c2_prose_specs(sent: str, si: int, pi: int, tolerance: Fraction) -> tuple[list[_Spec], list[QuantUndecided], list[str]]:
    """The checks of the round-9 (c2) prose shapes (module comment above) in ``sent``: ``(specs, undecided, phrases read)``; a phrase
    read is never also named undecided by the derived-figure reader (the caller drops such an entry)."""
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    read: list[str] = []
    if len(sent) > 4000 or not _FIGURE_HINT_RE.search(sent):
        return specs, undecided, read
    clauses = split_clauses(sent) if ";" in sent else [sent]
    for clause in clauses:
        cl = clause.lower()
        if " each" in cl:
            for m in _EACH_TOTAL_RE.finditer(clause):
                n = _c2_count(m.group("n"))
                if n is None:
                    continue
                each, each_shown = _c2_amount(m.group("mc"), m.group("m"), m.group("mu"))
                total, total_shown = _c2_amount(m.group("tc"), m.group("t"), m.group("tu"))
                phrase = " ".join(m.group(0).split())
                specs.append(_c2_product_spec(clause, phrase, [("count", n, f"the count ('{m.group('n')}')"), ("each", each, f"the amount each ({each_shown} {m.group('unit')})")],
                                              total, total_shown, m.group("q"), tolerance, "product_total", "stated total of a count of equal amounts"))
                read.append(phrase)
        if "at " in cl:
            for m in _PERIODS_AT_RATE_RE.finditer(clause):
                per, per2 = m.group("per").lower().rstrip("s"), m.group("per2").lower()
                n = _c2_count(m.group("n"))
                if n is None or per != per2:
                    continue
                rate, rate_shown = _c2_amount(m.group("xc"), m.group("x"), m.group("xu"))
                total, total_shown = _c2_amount(m.group("zc"), m.group("z"), m.group("zu"))
                if (m.group("xc") or "") and (m.group("zc") or "") and _cur_key(m.group("xc")) != _cur_key(m.group("zc")):
                    continue
                phrase = " ".join(m.group(0).split())
                specs.append(_c2_product_spec(clause, phrase, [("periods", n, f"the number of {per}s ('{m.group('n')}')"), ("rate", rate, f"the amount a {per} ({rate_shown})")],
                                              total, total_shown, m.group("q") or m.group("q1"), tolerance, "rate_total", f"stated total over {m.group('n')} {per}s"))
                read.append(phrase)
            for m in _AT_RATE_PERIOD_RE.finditer(clause):
                k = _PERIODS_IN.get((m.group("per1").lower(), m.group("per2").lower()))
                if k is None:
                    continue
                if (m.group("xc") or "") and (m.group("zc") or "") and _cur_key(m.group("xc")) != _cur_key(m.group("zc")):
                    continue
                rate, rate_shown = _c2_amount(m.group("xc"), m.group("x"), m.group("xu"))
                total, total_shown = _c2_amount(m.group("zc"), m.group("z"), m.group("zu"))
                phrase = " ".join(m.group(0).split())
                specs.append(_c2_product_spec(clause, phrase, [("periods", Fraction(k), f"the {m.group('per1')}s in a {m.group('per2')}"), ("rate", rate, f"the amount a {m.group('per1')} ({rate_shown})")],
                                              total, total_shown, m.group("q") or m.group("q1"), tolerance, "rate_total", f"stated amount a {m.group('per2')}"))
                read.append(phrase)
        if "percentage point" in cl or "percentage-point" in cl:
            for m in _PP_GAP_RE.finditer(clause):
                head = clause[: m.start()]
                pcts = _PCT_FIG_RE.findall(head)
                if len(pcts) != 2 or _pairs(clause):
                    continue
                a, b = _number(pcts[0]), _number(pcts[1])
                stated = _number(m.group("d"))
                side = _side(m.group("q"))
                premises = (("FIRST", {"op": "eq", "left": _v("first"), "right": _real(a)}, f"first share = {pcts[0]}%"),
                            ("SECOND", {"op": "eq", "left": _v("second"), "right": _real(b)}, f"second share = {pcts[1]}%"))
                gap = {"op": "sub", "left": _v("first"), "right": _v("second")} if a >= b else {"op": "sub", "left": _v("second"), "right": _v("first")}
                phrase = " ".join(m.group(0).split())
                specs.append(_Spec("points_change", clause.strip(), (("first", "the first per cent as stated"), ("second", "the second per cent as stated")), premises,
                                   ("STATED_POINTS", _within(gap, stated, tolerance, POINT_FLOOR, side),
                                    f"stated gap of {_fmt(stated)} percentage points against the difference of the two per cents its clause states ({pcts[0]}% and {pcts[1]}%)"),
                                   POINT_FLOOR, side, "figure stated in the report itself", "", phrase))
                read.append(phrase)
        if "%" in cl or "per cent" in cl or "percent" in cl:
            for rx in _C2_SHARE_RES + (_SHARE_BRACKETED_RE,):
                for m in rx.finditer(clause):
                    part, whole = _share_fig(m, "p"), _share_fig(m, "w")
                    if _year_like(part.num, part.unit or part.cur) or _year_like(whole.num, whole.unit or whole.cur):
                        continue
                    phrase = " ".join(m.group(0).split()).strip(" ,(")
                    spec, why = _share_spec(clause, whole, part, None, m.group("pn"), m.group("q"), tolerance, phrase, "the share stated of the part and the whole before it")
                    if spec is not None:
                        specs.append(spec)
                        read.append(phrase)
                    elif why:
                        undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                        read.append(phrase)
        if " as " in cl and ("times" in cl or "twice" in cl or "thrice" in cl):
            for m in _TIMES_AS_RE.finditer(clause):
                head = clause[: m.start()]
                figs = [f for f in _COUNT_FIG_RE.finditer(head) if not _YEAR_LIKE_RE.match(f.group(0))]
                if len(figs) != 2 or _pairs(clause):
                    continue
                a, b = _number(figs[0].group(0)), _number(figs[1].group(0))
                if a <= 0 or b <= 0 or a == b:
                    continue
                stated = Fraction(2) if (m.group("twice") or "").lower() == "twice" else Fraction(3) if m.group("twice") else _number(m.group("n"))
                big, small = (a, b) if a > b else (b, a)
                phrase = " ".join(m.group(0).split())
                premises = (("LARGER", {"op": "eq", "left": _v("larger"), "right": _real(big)}, f"the larger figure = {_fmt(big)}"),)
                ratio = {"op": "div", "left": _v("larger"), "right": _real(small)}
                specs.append(_Spec("fold_change", clause.strip(), (("larger", "the larger of the two figures its clause states"),), premises,
                                   ("STATED_FOLD", _within(ratio, stated, tolerance, Fraction(0), _side(m.group("q"))),
                                    f"stated '{phrase}' (factor {_fmt(stated)}) against the ratio of the larger to the smaller figure its clause states "
                                    f"({_fmt(big)} and {_fmt(small)})"), Fraction(0), _side(m.group("q")), "figure stated in the report itself",
                                   "the two figures its clause states before the comparison", phrase, severity="warning"))
                read.append(phrase)
                read.append(" ".join(m.group(0).split()[:2]))
        if "%" in cl or "per cent" in cl or "percent" in cl:
            for m in (_PCT_THEN_WORKING_RE.finditer(clause) if "(" in clause else ()):
                spec, why = _c2_bracket_change_spec(clause, m, tolerance)
                phrase = " ".join(m.group(0).split())
                if spec is not None:
                    specs.append(spec)
                    read.append(phrase)
                    read.append(" ".join((m.group("lead") + m.group("pct")).split()))
                elif why:
                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
    return specs, undecided, read


def _part_specs(sent: str, para: str, si: int, pi: int, tolerance: Fraction) -> tuple[list[_Spec], list[QuantUndecided]]:
    """Parts of a total stated before them ('..., of which A received X and B Y', 'Y alone brought N', 'Of the $13 billion, A received
    X and B Y'), a share of the total ('about a quarter of the decade's total'), a difference between two named parties' figures ('about
    $2 billion more than France') and a stated length against its span ('for ten years, from 1882 to 1892'). Each is decided against the
    sentence's own figures (a difference against the paragraph's), or returned undecided with the reason, as is a stated total no check
    reads whose parts are meant but not stated ('The two received a total of about 9 billion dollars')."""
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    if not _PART_HINT_RE.search(sent):
        return specs, undecided
    rule_note = "figure stated in the report itself"
    clauses = split_clauses(sent) if ";" in sent else [sent]
    for clause in clauses:
        if _part_markers_over_bound(clause):
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), " ".join(clause.split())[:120], _TOO_MANY_PARTS_REASON))
            continue
        # parts after 'of which': their sum may not exceed the total before it
        for m in _OF_WHICH_RE.finditer(clause):
            wholes = _amounts(clause, m.start())
            rest = re.split(r"[;:]", clause[m.end():])[0]
            share_cut = _SHARE_OF_TOTAL_RE.search(rest)
            parts = _magnitudes(rest[: share_cut.start()] if share_cut else rest)
            if not wholes or not parts:
                continue
            whole = wholes[-1]
            why = next((w for w in (_amount_pair(whole, p) for p in parts) if w), None)
            phrase = " ".join(clause[m.start():].split())[:160].strip(" ,")
            if why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                continue
            specs.append(_parts_spec(clause, whole, parts, tolerance, phrase, f"the parts stated after '{m.group(0).strip(' ,')}'"))
        lead_parts = False
        lead = _OF_THE_LEAD_RE.match(clause)
        if lead is not None and not _OF_WHICH_RE.search(clause):
            # 'Of the $13 billion, the United Kingdom received about $3.2 billion and France about $2.7 billion': the one figure of the
            # lead is the total, the figures after the comma (up to a comparison or a change) its parts
            wholes = _amounts(lead.group("lead"), len(lead.group("lead")))
            rest = re.split(r"[;:]", clause[lead.end():])[0]
            stop = _PARTS_STOP_RE.search(rest)
            rest = rest[: stop.start()] if stop else rest
            share_cut = _SHARE_OF_TOTAL_RE.search(rest)
            parts = _amounts(rest, share_cut.start() if share_cut else len(rest))
            if len(wholes) == 1 and parts:
                lead_parts = True
                whole = wholes[0]
                phrase = " ".join(clause[: lead.end() + len(rest)].split())[:160].strip(" ,")
                why = next((w for w in (_amount_pair(whole, p) for p in parts) if w), None)
                if why:
                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                else:
                    specs.append(_parts_spec(clause, whole, parts, tolerance, phrase, f"the parts stated after the total that opens the clause ('{lead.group(0).strip(' ,')}')"))
                # 'Of the 60 households surveyed, 27 owned a car (45%)': a share in brackets a few words after a part, before the next one
                # (round-8 clearance c1: a wrong per cent there crossed silently)
                for k, part in enumerate(parts if not why else ()):
                    stop_at = parts[k + 1].start if k + 1 < len(parts) else len(rest)
                    paren = _PAREN_SHARE_AFTER_RE.match(rest[:stop_at], part.end)
                    if paren is None or _BARE_SHARE_TAIL_RE.match(rest, part.end) is not None:
                        continue
                    share_phrase = " ".join(rest[part.start: paren.end()].split()).strip(" ,")
                    spec, why_share = _share_spec(clause, whole, part, None, paren.group("pn"), paren.group("q"), tolerance, share_phrase,
                                                  f"the share in brackets after the part, of the total that opens the clause ('{lead.group(0).strip(' ,')}')")
                    if spec is not None:
                        specs.append(spec)
                    elif why_share:
                        undecided.append(QuantUndecided(pi, si + 1, sent.strip(), share_phrase, why_share))
                # 'Of the 535 seats, the list was guaranteed 356, about three-quarters': a share stated right after the last part
                tail = _BARE_SHARE_TAIL_RE.match(rest, parts[-1].end)
                if tail is not None and not why:
                    share_phrase = " ".join((rest[parts[-1].start: tail.end()]).split()).strip(" ,")
                    spec, why_share = _share_spec(clause, whole, parts[-1], tail.group("frac"), tail.group("pn"), tail.group("q"), tolerance, share_phrase,
                                                  f"the share of the total that opens the clause ('{lead.group(0).strip(' ,')}')")
                    if spec is not None:
                        specs.append(spec)
                    elif why_share:
                        undecided.append(QuantUndecided(pi, si + 1, sent.strip(), share_phrase, why_share))
        # a stated total no check reads ('The two received a total of about 9 billion dollars'; 'Britain received about $3.2 billion, a
        # total of about $9 billion'): its parts are meant but not all stated as figures, so it is named, never passed silently; a plain
        # quantity ('The famine killed a total of about one million people') states no arithmetic and is not read
        tp = _TOTAL_PHRASE_RE.search(clause)
        if tp is not None and not lead_parts and not _OF_WHICH_RE.search(clause) and not _search_total(_TOTAL_RE, clause):
            before = _amounts(clause, tp.start())
            anaphor = _PARTS_ANAPHOR_RE.search(clause[: tp.start()])
            phrase = " ".join(clause[tp.start():].split())[:120].strip(" ,.")
            if before:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase,
                                                f"its sentence states {len(before)} figure(s) before the total ({', '.join(_shown(f, f.unit) for f in before[:3])}), "
                                                f"not the two or more parts it totals"))
            elif anaphor:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase,
                                                f"the parts it totals ('{anaphor.group(0)}') are not stated as figures in its sentence"))
        # 'Y alone brought N': one part of the total stated before it
        for m in _ALONE_RE.finditer(clause):
            fm = _LONE_FIG_RE.match(clause, m.end())
            if fm is None:
                continue
            part = _fig_of(fm, 1)
            if not part.num[:1].isdigit() or _is_pct(part.unit) or _year_like(part.num, part.unit or part.cur):
                continue
            wholes = _amounts(clause, m.start())
            if not wholes:
                continue
            whole = wholes[-1]
            who = m.group("who")
            if _YEAR_LIKE_RE.match(who):
                span = clause[whole.end: m.start()]
                dec = _DECADE_TOKEN_RE.search(span) or _DECADE_TOKEN_RE.search(clause[: whole.start][-40:])
                yr = _YEAR_SPAN_RE.search(span)
                if dec is not None and not (int(dec.group("d")) <= int(who) < int(dec.group("d")) + 10):
                    continue  # the year lies outside the decade the total covers: not a part of it
                if yr is not None and not (int(yr.group(1)) <= int(who) <= int(yr.group(2))):
                    continue
            phrase = " ".join(clause[m.start(): fm.end()].split())[:160]
            why = _amount_pair(whole, part)
            if why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                continue
            specs.append(_parts_spec(clause, whole, [part], tolerance, phrase, f"'{who} alone' states a part of the total"))
        # '<part>, about a quarter of the decade's total': the share of the total stated before the part
        for m in _SHARE_OF_TOTAL_RE.finditer(clause):
            head = clause[: m.start()]
            figs = _amounts(clause, m.start())
            phrase = " ".join(m.group(0).split()).strip(" ,")
            part = figs[-1] if figs and not head[figs[-1].end:].strip(" ,") else None
            whole = figs[-2] if part is not None and len(figs) >= 2 else None
            basis = ""
            if part is None:
                # 'of which the United Kingdom received about $3.2 billion ..., so the United Kingdom alone received about two-thirds of the
                # total': the part is the one figure the paragraph states for the party, the total the figure its parts are 'of which'
                party, part, whole, why = _party_share(clause, head, para, (m.start(), m.end()))
                if part is None or whole is None:
                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                    continue
                basis = f"the part is the figure the paragraph states for {party}"
            elif whole is None:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, "the total it is a share of is not stated as a figure before it in its sentence"))
                continue
            spec, why = _share_spec(clause, whole, part, m.group("frac"), m.group("pn"), m.group("q"), tolerance, phrase, basis)
            if spec is not None:
                specs.append(spec)
            elif why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
        # '356 of the 535 seats, about three-quarters' / '..., about 75 per cent': a share of the whole named right before it
        for m in (_N_OF_M_SHARE_RE.finditer(clause) if " of " in clause else ()):
            part, whole = _share_fig(m, "p"), _share_fig(m, "w")
            if _year_like(part.num, part.unit or part.cur) or _year_like(whole.num, whole.unit or whole.cur):
                continue
            phrase = " ".join(m.group(0).split()).strip(" ,(")
            spec, why = _share_spec(clause, whole, part, m.group("frac"), m.group("pn"), m.group("q"), tolerance, phrase, "the part and the whole stated as 'N of the M'")
            if spec is not None:
                specs.append(spec)
            elif why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
        # '$40m, which is 25% of total sales of $200m': a part stated as a share of the whole named after 'of' (round-8 clearance c1)
        for m in (_IS_SHARE_OF_RE.finditer(clause) if " of " in clause else ()):
            part, whole = _share_fig(m, "p"), _share_fig(m, "w")
            if _year_like(part.num, part.unit or part.cur) or _year_like(whole.num, whole.unit or whole.cur):
                continue
            phrase = " ".join(m.group(0).split()).strip(" ,(")
            spec, why = _share_spec(clause, whole, part, None, m.group("pn"), m.group("q"), tolerance, phrase,
                                    "the part stated as a share of the whole named after 'of'")
            if spec is not None:
                specs.append(spec)
            elif why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
        # 'about $2 billion more than France': the difference between two named parties' figures in the paragraph
        for m in _DIFF_RE.finditer(clause):
            diff = _fig_of(m, 1)
            if not diff.num[:1].isdigit() or _year_like(diff.num, diff.unit or diff.cur):
                continue
            other = re.sub(r"^the\s+", "", m.group("other")).rstrip(".")
            subj = [x for x in re.finditer(r"(?<![\w'’])(?:[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*)*)", clause[: m.start()])
                    if x.group(0).split()[0] not in ("The", "So", "Thus", "And", "But", "In", "By", "Of")]
            phrase = " ".join(m.group(0).split())[:160]
            at = para.find(clause)
            exclude = (at + m.start(), at + m.end()) if at >= 0 else (0, 0)
            if not subj:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, f"the party compared with {other} is not named before the difference"))
                continue
            subject = subj[-1].group(0).rstrip(".")
            a_figs = {(_frac(f.num, f.unit), f.cur): f for f in _entity_figures(subject, para, exclude)}
            b_figs = {(_frac(f.num, f.unit), f.cur): f for f in _entity_figures(other, para, exclude)}
            if len(a_figs) != 1 or len(b_figs) != 1:
                missing = subject if len(a_figs) != 1 else other
                n = len(a_figs) if missing == subject else len(b_figs)
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase,
                                                f"the paragraph states {'no figure' if n == 0 else f'{n} different figures'} for {missing}, so the stated difference could not be read against them"))
                continue
            fa, fb = next(iter(a_figs.values())), next(iter(b_figs.values()))
            why = _amount_pair(fa, fb) or _amount_pair(fa, diff)
            if why:
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, why))
                continue
            larger = m.group("cmp").lower() in ("more", "higher", "larger", "greater")
            va, vb, vd = _frac(fa.num, fa.unit), _frac(fb.num, fb.unit), _frac(diff.num, diff.unit)
            gap = {"op": "sub", "left": _v("a"), "right": _v("b")} if larger else {"op": "sub", "left": _v("b"), "right": _v("a")}
            side = _side(m.group("q1"))
            premises = (("A", {"op": "eq", "left": _v("a"), "right": _real(va)}, f"{subject} = {_shown(fa, fa.unit)}"),
                        ("B", {"op": "eq", "left": _v("b"), "right": _real(vb)}, f"{other} = {_shown(fb, fb.unit)}"))
            specs.append(_Spec("difference", clause.strip(), (("a", f"the figure stated for {subject}"), ("b", f"the figure stated for {other}")), premises,
                               ("STATED_DIFFERENCE", _within(gap, vd, tolerance, Fraction(0), side), f"stated difference '{phrase}' against {subject} minus {other}"
                                if larger else f"stated difference '{phrase}' against {other} minus {subject}"),
                               Fraction(0), side, "figure stated in the report itself, in the paragraph", f"figures read for {subject} and {other} in the paragraph", phrase))
    return specs, undecided


#: 'From 1961 the flow slowed to roughly fifteen states by 1968': a rate verb between a one-year count and a multi-year count.
_RATE_TREND_RE = re.compile(rf"\b(?P<verb>slowed|slowing|slackened|slackening|eased|easing|dwindled|dwindling|quickened|quickening|accelerated|accelerating|sped\s+up|"
                            rf"picked\s+up)\s+(?:down\s+)?to\s+{_fig(1)}?\s*(?:by|in|until|through)\s+(?P<y2>1[0-9]{{3}}|20[0-9]{{2}})\b", re.IGNORECASE)
_RATE_FROM_RE = re.compile(r"\b(?:from|after|since)\s+(?P<y1>1[0-9]{3}|20[0-9]{2})\b", re.IGNORECASE)
_SLOWER = frozenset({"slowed", "slowing", "slackened", "slackening", "eased", "easing", "dwindled", "dwindling"})


def _rate_trend_specs(sentences: list[str], si: int, pi: int) -> tuple[list[_Spec], list[QuantUndecided]]:
    """'From 1961 the flow slowed to roughly fifteen states by 1968' after 'in 1960, when seventeen African states became independent':
    the multi-year count over its years (1961 to 1968, both counted) per year against the one-year count of the year before. A rate
    verb whose counts cannot be read is returned undecided."""
    sent = sentences[si]
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    for m in _RATE_TREND_RE.finditer(sent):
        phrase = " ".join(m.group(0).split())
        y2 = int(m.group("y2"))
        frm = [x for x in _RATE_FROM_RE.finditer(sent[: m.start()])]
        if m.group("n1") is None or not frm:
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, "the count and the years the rate is stated over are not both stated in its sentence"))
            continue
        y1 = int(frm[-1].group("y1"))
        fig = _fig_of(m, 1)
        if y2 < y1 or _is_pct(fig.unit):
            continue
        prior: Optional[tuple[_Fig, int, int]] = None   # (count, its year, sentence index)
        for j in range(si, -1, -1):
            text = sentences[j] if j < si else sent[: frm[-1].start()]
            for clause in re.split(r"[;:]", text):
                years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(clause)})
                if years != [y1 - 1]:
                    continue
                counts = [f for f in (_fig_of(x, 1) for x in _LONE_FIG_RE.finditer(clause))
                          if not _year_like(f.num, f.unit or f.cur) and not _MONTH_NOUN_RE.match(f.noun) and not _is_pct(f.unit)
                          and not _MONTH_AFTER_RE.match(clause, f.start + len(f.num))]
                if len(counts) == 1:
                    prior = (counts[0], y1 - 1, j)
                    break
            if prior is not None:
                break
        if prior is None:
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, f"no one-year count for {y1 - 1}, the year before the rate's span, is stated in the paragraph"))
            continue
        before, year, j = prior
        shared = {w.rstrip("s") for w in before.noun.lower().split()} & {w.rstrip("s") for w in fig.noun.lower().split()}
        if not _cur_compatible(before.cur, "", fig.cur, "") or (before.noun and fig.noun and not shared):
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, f"'{_shown(fig, fig.unit)}' and '{_shown(before, before.unit)}' do not count the same thing"))
            continue
        years = y2 - y1 + 1
        slower = m.group("verb").lower().split()[0] in _SLOWER
        premises = (("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(_frac(before.num, before.unit))}, f"{year}: {_shown(before, before.unit)} (sentence {j + 1})"),
                    ("SPAN", {"op": "eq", "left": _v("span"), "right": _real(_frac(fig.num, fig.unit))}, f"{y1} to {y2}: {_shown(fig, fig.unit)}"))
        rate = {"op": "div", "left": _v("span"), "right": _real(Fraction(years))}
        concl = {"op": "lt" if slower else "gt", "left": rate, "right": _v("before")}
        label = f"stated '{m.group('verb')}': {_shown(fig, fig.unit)} over {years} years ({y1} to {y2}) a year {'below' if slower else 'above'} {_shown(before, before.unit)} in {year}"
        specs.append(_Spec("rate_trend", sent.strip(), (("before", f"the count for {year} as stated"), ("span", f"the count for {y1} to {y2} as stated")), premises,
                           ("STATED_RATE_TREND", concl, label), Fraction(0), "both", "figure stated in the report itself",
                           f"the one-year count for {year} read from sentence {j + 1}; the span counted from {y1} to {y2} inclusive", phrase))
    return specs, undecided


@dataclass(frozen=True)
class _SpanDate:
    text: str
    year: int
    month: Optional[int]
    day: Optional[int]

    @property
    def days(self) -> tuple[int, int]:
        """The first and last day the date can denote, as proleptic Gregorian ordinals (a year: 1 January to 31 December)."""
        import calendar
        from datetime import date
        if self.month is None:
            return date(self.year, 1, 1).toordinal(), date(self.year, 12, 31).toordinal()
        if self.day is None:
            return date(self.year, self.month, 1).toordinal(), date(self.year, self.month, calendar.monthrange(self.year, self.month)[1]).toordinal()
        d = date(self.year, self.month, self.day).toordinal()
        return d, d


def _span_date(text: str) -> Optional[_SpanDate]:
    m = _ONE_DATE_RE.match(" ".join(text.split()))
    if m is None:
        return None
    month = _MONTH_NUMBER[m.group("month").lower()] if m.group("month") else None
    day = m.group("day") or m.group("day2")
    out = _SpanDate(" ".join(text.split()), int(m.group("year")), month, int(day) if day else None)
    try:
        out.days  # noqa: B018 - a day the month does not have ('31 February') is no date
    except ValueError:
        return None
    return out


def _span_of(sentence: str, phrase: "re.Match[str]", spans: list, starts: list[int], ends: list[int]) -> Optional["re.Match[str]"]:
    """The span a stated length is read against in its own sentence (``spans``: the sentence's spans in order, read once): the first span
    after the phrase, within 40 characters and with no clause break between ('for ten years, from 1882 to 1892', 'which lasted five years
    from 1924 to 1926', 'for more than twelve years after the GDR's founding on 7 October 1949, until 13 August 1961'), else the last span
    before it in its clause, within 200 characters ('From 1924 to 1926 the secession lasted five years'). Each lookup is a bisection, so a
    sentence of thousands of stated lengths costs no quadratic scan."""
    import bisect
    k = bisect.bisect_left(starts, phrase.end())
    if k < len(spans):
        sp = spans[k]
        if sp.start() - phrase.end() <= 40 and not _EDGE_SEP_RE.search(sentence, phrase.end(), sp.start()):
            return sp
    k = bisect.bisect_right(ends, phrase.start()) - 1
    if k >= 0:
        sp = spans[k]
        if phrase.start() - sp.end() <= 200 and not _EDGE_SEP_RE.search(sentence, sp.end(), phrase.start()):
            return sp
    return None


def _band(stated: Fraction, qualifier: Optional[str], tolerance: Fraction) -> tuple[Optional[Fraction], bool, Optional[Fraction], bool, str]:
    """``(low, low strict, high, high strict, how)``: the elapsed years a stated length allows. A one-sided qualifier is exact ('more than
    twelve years' needs more than twelve); 'nearly'/'almost' approach it from below and 'just over' from above (the approach band); 'about',
    'roughly' and no qualifier allow the tolerance rule or half a year (a length rounded to whole years)."""
    q = " ".join((qualifier or "").lower().split())
    if q in _LOWER_ONLY:
        return stated, q in _STRICT_LOWER, None, False, f"more than {_fmt(stated)} years" if q in _STRICT_LOWER else f"at least {_fmt(stated)} years"
    if q in _UPPER_ONLY:
        return None, False, stated, q in _STRICT_UPPER, f"less than {_fmt(stated)} years" if q in _STRICT_UPPER else f"at most {_fmt(stated)} years"
    if q in _APPROACH_BELOW:
        return stated * APPROACH_BAND, False, stated * (1 + APPROACH_ROUNDING), False, f"approaching {_fmt(stated)} years from below (from 85 per cent of it up to it)"
    if q in _APPROACH_ABOVE:
        return stated * (1 - APPROACH_ROUNDING), False, stated / APPROACH_BAND, False, f"just over {_fmt(stated)} years (up to it divided by 0.85)"
    lo, hi = min(stated / (1 + tolerance), stated - YEAR_FLOOR), max(stated / (1 - tolerance), stated + YEAR_FLOOR)
    return lo, False, hi, False, f"{_fmt(stated)} years within {float(tolerance) * 100:g}% of the elapsed time or half a year of it"


def _band_expr(expr: dict, band: tuple) -> dict:
    lo, lo_strict, hi, hi_strict, _how = band
    parts = []
    if lo is not None:
        parts.append({"op": "gt" if lo_strict else "ge", "left": expr, "right": _real(lo)})
    if hi is not None:
        parts.append({"op": "lt" if hi_strict else "le", "left": expr, "right": _real(hi)})
    return parts[0] if len(parts) == 1 else {"op": "and", "args": parts}


def _inside(value_lo: Fraction, value_hi: Fraction, band: tuple) -> Optional[bool]:
    """True when every elapsed time from ``value_lo`` to ``value_hi`` satisfies the band, False when none does, None when some do."""
    lo, lo_strict, hi, hi_strict, _how = band

    def ok(x: Fraction) -> bool:
        return (lo is None or (x > lo if lo_strict else x >= lo)) and (hi is None or (x < hi if hi_strict else x <= hi))
    if ok(value_lo) and ok(value_hi):
        return True
    below = lo is not None and (value_hi <= lo if lo_strict else value_hi < lo)
    above = hi is not None and (value_lo >= hi if hi_strict else value_lo > hi)
    return False if below or above else None


_DURATION_RULE = ("a stated length of years against its span: in whole years, the difference of the years or the difference plus one (both end years "
                  "counted); with day or month dates, the elapsed days / 365.2425; 'more than', 'over', 'at least', 'less than', 'under' are exact bounds, "
                  "'nearly'/'almost' approach the length from below (85 per cent of it up to it), and 'about', 'roughly' or no qualifier allow 5% of the "
                  "elapsed time or half a year; a span whose dates are too coarse to decide the length is reported undecided")


def _duration_specs(sentences: list[str], si: int, pi: int, tolerance: Fraction) -> tuple[list[_Spec], list[QuantUndecided]]:
    """A stated length of years against its span: 'for ten years, from 1882 to 1892', 'lasted five years, from June 1924 to January 1926',
    'which lasted about five years from 1924 to 1926', 'continued for more than twelve years after the GDR's founding on 7 October 1949, until
    13 August 1961'. A sentence that states no span of its own is read against the one span an adjacent sentence of the paragraph states, when
    that span shares a year with the sentence's own dates (hi-p7c: 'ended a drain that had run for more than twelve years' with 'Between the
    founding of the German Democratic Republic on 7 October 1949 and 1961' next; the bare end year is read as the day the duration's own
    sentence dates in it, 13 August 1961), and the check says it was stated across sentences. A stated length whose dates cannot be paired
    into a span, or whose span is too coarse to decide it, is returned undecided."""
    sent = sentences[si]
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    spans_here = list(_DUR_SPAN_RE.finditer(sent))
    span_starts, span_ends = [sp.start() for sp in spans_here], [sp.end() for sp in spans_here]
    own_cache: list = []
    adjacent_cache: list = []
    for m in _DUR_PHRASE_RE.finditer(sent):
        raw = m.group("n")
        try:
            stated = _number(raw)
        except FigureTooLarge:
            continue
        if stated <= 0:
            continue
        phrase = " ".join(m.group(0).split())
        qualifier = m.group("q")
        basis = ""
        span = _span_of(sent, m, spans_here, span_starts, span_ends)
        if span is not None:
            d1, d2 = _span_date(span.group("d1")), _span_date(span.group("d2"))
        else:
            if not own_cache:
                own_cache.append([d for d in (_span_date(x.group(0)) for x in _SPAN_DATE_RE.finditer(sent)) if d is not None])
            own = own_cache[0]
            if not adjacent_cache:
                adjacent: list = []
                for j in (si - 1, si + 1):
                    if not 0 <= j < len(sentences):
                        continue
                    spans = list(_DUR_SPAN_RE.finditer(sentences[j]))
                    if len(spans) != 1:
                        continue
                    a, b = _span_date(spans[0].group("d1")), _span_date(spans[0].group("d2"))
                    if a is not None and b is not None:
                        adjacent.append((j, spans[0], a, b))
                adjacent_cache.append(adjacent)
            found = [(j, sp, a, b) for j, sp, a, b in adjacent_cache[0] if own and ({a.year, b.year} & {d.year for d in own})]
            if len(found) != 1:
                if len({d.text for d in own}) >= 2:
                    elsewhere = spans_here
                    how = (f"the span its sentence states ('{' '.join(elsewhere[0].group(0).split())[:80]}') stands in another clause, so it was not read as the "
                           f"span of the stated length" if elsewhere else
                           f"its sentence states {', '.join(dict.fromkeys(d.text for d in own))} but no 'from ... to ...' or 'between ... and ...' span")
                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, f"a stated length of years whose dates cannot be paired into a span: {how}"
                                                    + ("" if not found else f", and {len(found)} adjacent sentences state spans that could be meant")))
                continue
            j, sp, d1, d2 = found[0]
            refined = []
            for which, d in (("first", d1), ("last", d2)):
                if d.month is None:
                    finer = [x for x in own if x.year == d.year and x.month is not None]
                    if len({x.text for x in finer}) == 1:
                        refined.append(f"its {which} year {d.year} read as {finer[0].text}, the date the duration's own sentence gives in that year")
                        d = finer[0]
                if which == "first":
                    d1 = d
                else:
                    d2 = d
            basis = (f"stated across sentences: the span is the one sentence {j + 1} of the paragraph states ('{' '.join(sp.group(0).split())[:120]}')"
                     + (f"; {'; '.join(refined)}" if refined else ""))
        if d1 is None or d2 is None:
            continue
        shown = f"{d1.text} to {d2.text}"
        if d1.month is None and d2.month is None:
            if d2.year < d1.year:
                continue
            premises = (("START", {"op": "eq", "left": _v("start"), "right": _real(Fraction(d1.year))}, f"start = {d1.year}"),
                        ("END", {"op": "eq", "left": _v("end"), "right": _real(Fraction(d2.year))}, f"end = {d2.year}"))
            symbols = (("start", "the first year as stated"), ("end", "the last year as stated"))
            diff = {"op": "sub", "left": _v("end"), "right": _v("start")}
            if not qualifier:
                concl = {"op": "and", "args": [{"op": "le", "left": diff, "right": _real(stated)}, {"op": "ge", "left": {"op": "add", "args": [diff, _real(Fraction(1))]}, "right": _real(stated)}]}
                specs.append(_Spec("duration", sent.strip(), symbols, premises,
                                   ("STATED_DURATION", concl, f"stated length '{raw} years' against the span {d1.year} to {d2.year} (counted either exclusively or inclusively)"),
                                   Fraction(0), "both", "figure stated in the report itself", basis, phrase))
                continue
            band = _band(stated, qualifier, tolerance)
            concl = {"op": "or", "args": [_band_expr(diff, band), _band_expr({"op": "add", "args": [diff, _real(Fraction(1))]}, band)]}
            specs.append(_Spec("duration", sent.strip(), symbols, premises,
                               ("STATED_DURATION", concl, f"stated length '{phrase}' ({band[4]}) against the span {d1.year} to {d2.year} (counted either exclusively or inclusively)"),
                               Fraction(0), "both", "figure stated in the report itself", basis, phrase, _DURATION_RULE))
            continue
        (s_lo, s_hi), (e_lo, e_hi) = d1.days, d2.days
        if e_hi <= s_lo:
            continue  # a span that runs backwards states no length (its order is the chronology check's)
        band = _band(stated, qualifier, tolerance)
        lo_years, hi_years = Fraction(e_lo - s_hi) / _DAYS_PER_YEAR, Fraction(e_hi - s_lo) / _DAYS_PER_YEAR
        verdict = _inside(lo_years, hi_years, band)
        if verdict is None:
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase,
                                            f"the stated length ({band[4]}) cannot be decided at the resolution of its dates: {shown} is between "
                                            f"{float(lo_years):.1f} and {float(hi_years):.1f} years" + (f" ({basis})" if basis else "")))
            continue
        premises = (("START_FROM", {"op": "ge", "left": _v("start"), "right": _real(Fraction(s_lo))}, f"start on or after the first day of {d1.text}"),
                    ("START_TO", {"op": "le", "left": _v("start"), "right": _real(Fraction(s_hi))}, f"start on or before the last day of {d1.text}"),
                    ("END_FROM", {"op": "ge", "left": _v("end"), "right": _real(Fraction(e_lo))}, f"end on or after the first day of {d2.text}"),
                    ("END_TO", {"op": "le", "left": _v("end"), "right": _real(Fraction(e_hi))}, f"end on or before the last day of {d2.text}"))
        symbols = (("start", f"the first day of the span ({d1.text}) as a day ordinal"), ("end", f"the last day of the span ({d2.text}) as a day ordinal"))
        elapsed = {"op": "div", "left": {"op": "sub", "left": _v("end"), "right": _v("start")}, "right": _real(_DAYS_PER_YEAR)}
        specs.append(_Spec("duration", sent.strip(), symbols, premises,
                           ("STATED_DURATION", _band_expr(elapsed, band), f"stated length '{phrase}' ({band[4]}) against the elapsed time from {shown} (days / 365.2425)"),
                           Fraction(0), "both", "figure stated in the report itself", basis, phrase, _DURATION_RULE))
    return specs, undecided


# ------------------------------------------------------------------ calendar lengths between dated events (round 9 second pass)
#
# A length of time stated in days, weeks, months or years, alone or compounded ('two years and seventeen days', 'about seven months', '381
# days', 'more than a year'), read against the two dates it spans (round 9 second pass: c2 adversarial-live bug 20 and the leftovers' History
# chronology finding; a wrong length crossed every branch with no finding). The shapes read, each in one sentence of a paragraph:
#
# * a length after the later of two dates of its sentence: '... opened at Kaesong on 10 July 1951, and the armistice was signed at Panmunjom on
#   27 July 1953, two years and seventeen days later';
# * a length up to an end date, its start the date before it in the sentence's clause, or the date the paragraph gives the beginning of the event
#   the sentence names: 'The boycott began on 5 December 1955 and lasted for 381 days, until 20 December 1956'; '... sustained the boycott for
#   381 days, until 20 December 1956' after '... a boycott, which began on 5 December 1955';
# * a length set after a span: '... ran from January 1968 to the invasion of 20–21 August 1968, about seven months', 'Between January 1968 and
#   August 1968, seven months passed';
# * a length between the two dated events an order cue sets apart: 'The Action Programme of April 1968 came two months before the June manifesto of
#   1968'.
#
# A length after an event noun that the reader cannot pair with two dates ('A war of three years and one month ...') is named undecided
# (CORE-QNT-001), never skipped. Every pattern is anchored at a fixed word or a date, and every run in it is bounded or possessive.

_CAL_UNIT = r"(?:years?|months?|weeks?|days?)"
_CAL_COUNT = rf"(?:an?|one|{_WNUM}|\d{{1,4}})"
_CAL_PART = rf"{_CAL_COUNT}\s++(?:full\s++|whole\s++|calendar\s++)?{_CAL_UNIT}\b"
#: A stated length with its qualifier: groups ``q`` (the qualifier) and ``len`` (the length, up to three parts).
_CAL_LENGTH = rf"(?:(?P<q>{_QUAL})\s++)?(?P<len>{_CAL_PART}(?:(?:\s*+,\s*+(?:and\s++)?|\s++and\s++){_CAL_PART}){{0,2}})"
_CAL_PART_RE = re.compile(rf"({_CAL_COUNT})\s++(?:full\s++|whole\s++|calendar\s++)?({_CAL_UNIT})\b", re.IGNORECASE)
#: One date as text (a day range, a day, a month, a year): '20–21 August 1968', '5 January 1968', 'January 30, 1933', 'January 1968', '1968'.
_CAL_DATE_TEXT = (rf"(?:(?:\d{{1,2}}\s*+[–-]\s*+)?(?:\d{{1,2}}(?:st|nd|rd|th)?\s++)?(?:{_MONTHS_TEXT})(?:\s++\d{{1,2}}(?:st|nd|rd|th)?,?)?\s++)?"
                  r"(?:1[0-9]{3}|20[0-9]{2})(?![\d,.]?\d)")
#: A date of a sentence (groups: ``d0`` the first day of a day range, ``d`` / ``dm`` the day, ``mon``, ``fill`` the noun between a month and
#: 'of' in 'the June manifesto of 1968', ``y``; ``yo`` a year alone).
_CAL_DATE_RE = re.compile(
    rf"(?<![\w,.$£€])(?:(?P<d0>\d{{1,2}})\s*+[–-]\s*+)?(?:(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s++)?(?P<mon>{_MONTHS_TEXT})"
    rf"(?:\s++(?P<dm>\d{{1,2}})(?:st|nd|rd|th)?,?|(?P<fill>(?:\s++[a-z][a-z'’-]{{0,20}}){{1,2}}?\s++of))?\s++(?P<y>1[0-9]{{3}}|20[0-9]{{2}})(?![\d,.]?\d)"
    r"|(?<![\w,.$£€])(?P<yo>1[0-9]{3}|20[0-9]{2})(?![\d,.]?\d)(?!\s*+(?:per\s*+cent|percent|%|million|billion|thousand|seats|votes)\b)")
_CAL_HINT_RE = re.compile(r"\b(?:years?|months?|weeks?|days?)\b", re.IGNORECASE)
#: '..., two years and seventeen days later'.
_CAL_LATER_RE = re.compile(rf"(?:,\s*+|\s++)(?:only\s++|exactly\s++)?{_CAL_LENGTH}\s++(?:later|afterwards|after\s++that)\b", re.IGNORECASE)
#: '... for 381 days, until 20 December 1956', '... lasted seven months, until ...'.
_CAL_UNTIL_RE = re.compile(rf"\b(?P<verb>for|lasted|lasting|lasts|ran|running|continued|continuing|endured|enduring)\s++(?:for\s++)?{_CAL_LENGTH}\s*+,?\s*+"
                           r"(?:until|till|up\s++to)\s++", re.IGNORECASE)
#: A span and the length after it: '... from January 1968 to the invasion of 20–21 August 1968, about seven months', 'Between January 1968 and
#: August 1968, seven months passed'.
_CAL_SPAN_LENGTH_RE = re.compile(
    rf"\b(?:from|between)\s++(?:[^\d;:!?]{{0,80}}?\b(?:on|in|of)\s++)?(?P<a>{_CAL_DATE_TEXT})(?:\s*+,)?\s++(?:and|to|until|till|through|up\s++to)\s++"
    rf"(?:[^\d;:!?]{{0,60}}?\b(?:on|in|of)\s++)?(?P<b>{_CAL_DATE_TEXT})\s*+,\s*+(?:a\s++(?:period|span|gap|total)\s++of\s++|or\s++|some\s++)?{_CAL_LENGTH}"
    r"(?=\s*+(?:[.;,)]|$|passed|elapsed|went\s++by|had\s++passed|in\s++all|in\s++total))", re.IGNORECASE)
#: A length between two dated events an order cue sets apart: '... came two months before ...', '... three years after ...'.
_CAL_CUE_RE = re.compile(rf"(?<![\w-]){_CAL_LENGTH}\s++(?P<cue>before|after|earlier\s++than|later\s++than|prior\s++to)\b", re.IGNORECASE)
#: A length after an event noun with no dates of its own: 'A war of three years and one month', 'a boycott of 381 days'.
_CAL_NOUN_RE = re.compile(rf"\b(?:an?|the|this|that|its)\s++(?:[a-z]+\s++)?(?P<noun>war|conflict|occupation|boycott|strike|siege|campaign|reign|blockade|struggle"
                          rf"|presidency|premiership|dictatorship|regime|truce|ceasefire|crisis|revolution|uprising|lockout)\s++of\s++{_CAL_LENGTH}", re.IGNORECASE)
_CAL_BEGIN_VERBS = r"(?:began|begun|started|opened|broke\s++out|was\s++launched|were\s++launched|got\s++under\s++way|commenced)"
#: Where a length's clause ends: a semicolon, a colon, or ', and' / ', but' before another clause.
_CAL_CLAUSE_END_RE = re.compile(r";|:|,\s*+(?:and|but|while|whereas|yet)\b", re.IGNORECASE)
_CAL_RULE = ("a stated length of time against the dates it spans, counted on the calendar from the start (a month or a year moves the date on, a "
             "day it the number of days): a length with days in it holds to the day, give or take one (the end day counted or not), one in weeks to "
             "three days, one in whole months to the elapsed time rounded or cut to whole months (from half a month short of it to a month beyond "
             "it), one in whole years to half a year either way; 'about', 'around', 'roughly' and 'some' allow one unit of the smallest unit "
             "stated or 5% of the length; 'more than', 'over', 'at least', 'less than', 'under', 'at most' are bounds; 'nearly'/'almost' "
             "approach the length from below (85 per cent of it up to it) and 'just over' from above; a date stated only as a month or a year is "
             "every day it can be, and a length its dates are too coarse to decide is named undecided")


@dataclass(frozen=True)
class _CalDate:
    """A date of a sentence as the days it can denote: ``lo`` and ``hi`` are proleptic Gregorian ordinals (a year: 1 January to 31
    December; a month: its first to its last day; a day range '20–21 August': its two days)."""
    text: str
    start: int
    end: int
    lo: int
    hi: int
    res: str = "day"          # 'day' (a day or a day range), 'month' or 'year': what the date states
    index: int = 0            # year * 12 + month (a 'year' date: year * 12), for the month and year rules


def _cal_dates(text: str) -> list[_CalDate]:
    """The dates of ``text`` in order (:data:`_CAL_DATE_RE`); a day the month does not have is no date. 'the June manifesto of 1968' is
    June 1968; a month and a noun before 'of' with no 'the' before them ('May the people of 1968') date only the year."""
    import calendar
    from datetime import date
    out: list[_CalDate] = []
    for m in _CAL_DATE_RE.finditer(text):
        try:
            if m.group("yo") or (m.group("fill") and text[max(0, m.start() - 4): m.start()].lower() != "the "):
                y = int(m.group("yo") or m.group("y"))
                s, e = (m.start(), m.end()) if m.group("yo") else (m.start("y"), m.end("y"))
                out.append(_CalDate(text[s:e], s, e, date(y, 1, 1).toordinal(), date(y, 12, 31).toordinal(), "year", y * 12))
                continue
            y, mon = int(m.group("y")), _MONTH_NUMBER[m.group("mon").lower()]
            last = calendar.monthrange(y, mon)[1]
            day = m.group("d") or m.group("dm")
            if day is None:
                lo, hi = date(y, mon, 1).toordinal(), date(y, mon, last).toordinal()
            else:
                d = int(day)
                first = int(m.group("d0")) if m.group("d0") else d
                if not 1 <= first <= d <= last:
                    continue
                lo, hi = date(y, mon, first).toordinal(), date(y, mon, d).toordinal()
            out.append(_CalDate(" ".join(m.group(0).split()), m.start(), m.end(), lo, hi, "month" if day is None else "day", y * 12 + mon))
        except (ValueError, KeyError):
            continue
    return out


def _cal_parts(length: str) -> Optional[tuple[int, int, int, int]]:
    """``(years, months, weeks, days)`` of a stated length ('two years and seventeen days' -> (2, 0, 0, 17)), or None when a count is not a
    whole number of at most four digits or a unit is stated twice."""
    parts = {"year": 0, "month": 0, "week": 0, "day": 0}
    seen: set[str] = set()
    for m in _CAL_PART_RE.finditer(length):
        word, unit = m.group(1).lower(), m.group(2).lower().rstrip("s")
        try:
            n = Fraction(1) if word in ("a", "an", "one") else _number(word)
        except (ValueError, ZeroDivisionError, FigureTooLarge, KeyError):
            return None
        if unit in seen or n.denominator != 1 or not 0 < n <= 9999:
            return None
        seen.add(unit)
        parts[unit] = int(n)
    return (parts["year"], parts["month"], parts["week"], parts["day"]) if seen else None


def _cal_add(ordinal: int, years: int, months: int, days: int) -> Optional[int]:
    """The day ``ordinal`` moved on by ``years`` and ``months`` on the calendar (the day of the month kept, or the month's last day when it is
    shorter: 31 January and a month is 28 or 29 February) and then by ``days``; None outside the calendar."""
    import calendar
    from datetime import date
    try:
        d = date.fromordinal(ordinal)
        total = d.year * 12 + (d.month - 1) + years * 12 + months
        y, m = divmod(total, 12)
        day = min(d.day, calendar.monthrange(y, m + 1)[1])
        return date(y, m + 1, day).toordinal() + days
    except (ValueError, OverflowError):
        return None


def _cal_band(start: int, parts: tuple[int, int, int, int], qualifier: Optional[str]) -> Optional[tuple[Optional[Fraction], bool, Optional[Fraction], bool]]:
    """``(low, low strict, high, high strict)`` in days of the elapsed time a stated length allows from the day ``start`` (:data:`_CAL_RULE`)."""
    years, months, weeks, days = parts
    end = _cal_add(start, years, months, weeks * 7 + days)
    if end is None:
        return None
    length = Fraction(end - start)
    if length <= 0:
        return None
    if days:
        slack, unit = Fraction(1), Fraction(1)
    elif weeks:
        slack, unit = Fraction(3), Fraction(7)
    elif months:
        slack, unit = Fraction(0), Fraction(30)
    else:
        slack, unit = Fraction(183), Fraction(365)
    q = " ".join((qualifier or "").lower().split())
    if q in _LOWER_ONLY:
        return length, q in _STRICT_LOWER, None, False
    if q in _UPPER_ONLY:
        return None, False, length, q in _STRICT_UPPER
    if q in _APPROACH_BELOW:
        return length * APPROACH_BAND, False, length, False
    if q in _APPROACH_ABOVE:
        return length, False, length / APPROACH_BAND, False
    if q in ("about", "around", "roughly", "approximately", "approx.", "some", "c.", "ca.", "circa", "close to", "an estimated", "near"):
        width = max(unit, length / 20)
        return length - width, False, length + width, False
    if months and not (days or weeks):
        return length - 15, False, length + 30, True  # rounded or cut to whole months
    return length - slack, False, length + slack, False


def _cal_spec(sent: str, phrase: str, qualifier: Optional[str], length: str, d1: _CalDate, d2: _CalDate, basis: str, pi: int, si: int
              ) -> tuple[Optional[_Spec], Optional[QuantUndecided]]:
    """The check of the stated ``length`` from ``d1`` to ``d2``, or the reason it is undecided (a length the reader cannot read, dates too
    coarse to decide it), or ``(None, None)`` when the span runs backwards (its order is the chronology check's)."""
    parts = _cal_parts(length)
    if parts is None:
        return None, QuantUndecided(pi, si + 1, sent.strip(), phrase, "a stated length of time whose parts could not be read as whole numbers of days, weeks, months and years")
    if d2.hi <= d1.lo:
        return None, None
    years, months, weeks, days = parts
    # a length in whole years between two dates stated as months or years is read on the year index ('three years after the war began in
    # June 1950' for July 1953: a length of years is rounded or cut to whole years); one with months between two month dates on the month index
    unit = "year" if {d1.res, d2.res} <= {"month", "year"} and not (months or weeks or days) else \
        "month" if d1.res == d2.res == "month" and not (weeks or days) else None
    if unit is not None:
        return _cal_index_spec(sent, phrase, qualifier, d1, d2, years * 12 + months if unit == "month" else years, unit, basis, pi, si)
    lows, highs = [], []
    for s in {d1.lo, d1.hi}:
        band = _cal_band(s, parts, qualifier)
        if band is None:
            return None, QuantUndecided(pi, si + 1, sent.strip(), phrase, "a stated length of time outside the calendar the reader reads")
        lows.append(band[:2])
        highs.append(band[2:])
    lo = min((x for x in lows if x[0] is not None), default=(None, False), key=lambda x: x[0])
    hi = max((x for x in highs if x[0] is not None), default=(None, False), key=lambda x: x[0])
    band = (lo[0], lo[1], hi[0], hi[1], "")
    shown = f"{d1.text} to {d2.text}"
    verdict = _inside(Fraction(max(0, d2.lo - d1.hi)), Fraction(d2.hi - d1.lo), band)
    if verdict is None:
        return None, QuantUndecided(pi, si + 1, sent.strip(), phrase, f"the stated length ('{phrase}') cannot be decided at the resolution of its dates: {shown} is between "
                                                                      f"{max(0, d2.lo - d1.hi)} and {d2.hi - d1.lo} days" + (f" ({basis})" if basis else ""))
    premises = (("START_FROM", {"op": "ge", "left": _v("start"), "right": _real(Fraction(d1.lo))}, f"start on or after the first day of {d1.text}"),
                ("START_TO", {"op": "le", "left": _v("start"), "right": _real(Fraction(d1.hi))}, f"start on or before the last day of {d1.text}"),
                ("END_FROM", {"op": "ge", "left": _v("end"), "right": _real(Fraction(d2.lo))}, f"end on or after the first day of {d2.text}"),
                ("END_TO", {"op": "le", "left": _v("end"), "right": _real(Fraction(d2.hi))}, f"end on or before the last day of {d2.text}"))
    symbols = (("start", f"the first day of the span ({d1.text}) as a day ordinal"), ("end", f"the last day of the span ({d2.text}) as a day ordinal"))
    elapsed = {"op": "sub", "left": _v("end"), "right": _v("start")}
    bounds = []
    if band[0] is not None:
        bounds.append(f"{'more than' if band[1] else 'at least'} {_fmt(band[0])} days")
    if band[2] is not None:
        bounds.append(f"{'less than' if band[3] else 'at most'} {_fmt(band[2])} days")
    label = f"stated length '{phrase}' against the elapsed days from {shown} (on the calendar: {' and '.join(bounds)})"
    return _Spec("duration", sent.strip(), symbols, premises, ("STATED_DURATION", _band_expr(elapsed, band), label), Fraction(0), "both",
                 "figure stated in the report itself", basis, phrase, _CAL_RULE), None


def _cal_index_verdict(diff: int, stated: int, qualifier: Optional[str]) -> tuple[Optional[bool], dict]:
    """The month or year rule (:func:`_cal_index_spec`): the verdict on the elapsed whole units ``diff`` (the later date's index less the
    earlier's) against the ``stated`` units, and the conclusion over ``diff`` that encodes it. Each date covers its whole month (or year), so the
    elapsed time lies between ``diff - 1`` and ``diff + 1`` units: without a qualifier the stated length is the difference, or the difference
    plus one when both end units are counted; 'about' allows one unit more either way; a bound ('more than', 'less than') holds only when every
    elapsed time the dates allow meets it, fails when none does, and is undecided otherwise; 'nearly' is the length or one unit short of it, and
    'just over' the length or one unit more."""
    q = " ".join((qualifier or "").lower().split())
    d = {"op": "sub", "left": _v("later"), "right": _v("earlier")}

    def cmp(op: str, k: int) -> dict:
        return {"op": op, "left": d, "right": _real(Fraction(k))}
    if q in _LOWER_ONLY:
        verdict = True if diff - 1 >= stated else False if diff + 1 <= stated else None
        return verdict, cmp("ge", stated + 1)
    if q in _UPPER_ONLY:
        verdict = True if diff + 1 <= stated else False if diff - 1 >= stated else None
        return verdict, cmp("le", stated - 1)
    if q in _APPROACH_BELOW:
        verdict = True if stated - 1 <= diff <= stated else False if diff > stated or diff < stated * APPROACH_BAND - 1 else None
        return verdict, {"op": "and", "args": [cmp("ge", stated - 1), cmp("le", stated)]}
    if q in _APPROACH_ABOVE:
        verdict = True if stated <= diff <= stated + 1 else False if diff < stated - 1 or diff > stated / APPROACH_BAND + 1 else None
        return verdict, {"op": "and", "args": [cmp("ge", stated), cmp("le", stated + 1)]}
    if q in ("about", "around", "roughly", "approximately", "approx.", "some", "c.", "ca.", "circa", "close to", "an estimated", "near"):
        return stated - 2 <= diff <= stated + 1, {"op": "and", "args": [cmp("ge", stated - 2), cmp("le", stated + 1)]}
    return diff in (stated, stated - 1), {"op": "or", "args": [cmp("eq", stated), cmp("eq", stated - 1)]}


def _cal_index_spec(sent: str, phrase: str, qualifier: Optional[str], d1: _CalDate, d2: _CalDate, stated: int, unit: str, basis: str, pi: int, si: int
                    ) -> tuple[Optional[_Spec], Optional[QuantUndecided]]:
    """A length in whole months (or years) between two dates stated only as months (or years): read on the month (year) index, as a stated
    length of years is read between two years ('from January 1968 to August 1968, seven months')."""
    step = 12 if unit == "year" else 1
    a, b = d1.index // step, d2.index // step
    verdict, concl = _cal_index_verdict(b - a, stated, qualifier)
    if verdict is None:
        return None, QuantUndecided(pi, si + 1, sent.strip(), phrase, f"the stated length ('{phrase}') cannot be decided at the resolution of its dates: "
                                                                      f"{d1.text} to {d2.text} is {b - a} {unit}s apart as written, so the elapsed time lies between "
                                                                      f"{b - a - 1} and {b - a + 1} {unit}s" + (f" ({basis})" if basis else ""))
    premises = (("EARLIER", {"op": "eq", "left": _v("earlier"), "right": _real(Fraction(a))}, f"the {unit} of {d1.text} as a {unit} index"),
                ("LATER", {"op": "eq", "left": _v("later"), "right": _real(Fraction(b))}, f"the {unit} of {d2.text} as a {unit} index"))
    symbols = (("earlier", f"the {unit} of {d1.text}"), ("later", f"the {unit} of {d2.text}"))
    label = f"stated length '{phrase}' against the {unit}s from {d1.text} to {d2.text} (the difference, or the difference plus one when both ends are counted)"
    return _Spec("duration", sent.strip(), symbols, premises, ("STATED_DURATION", concl, label), Fraction(0), "both", "figure stated in the report itself",
                 basis, phrase, _CAL_RULE), None


def _cal_clause(sent: str, at: int, end: int) -> tuple[int, int]:
    """The clause of ``sent`` around ``at``..``end``: from after the last clause break before ``at`` to the first after ``end``."""
    before = [m.end() for m in _CAL_CLAUSE_END_RE.finditer(sent, 0, at)]
    after = _CAL_CLAUSE_END_RE.search(sent, end)
    return (before[-1] if before else 0), (after.start() if after else len(sent))


def _cal_event_start(sentences: list[str], si: int, noun: str) -> tuple[Optional[_CalDate], str]:
    """The date an earlier sentence of the paragraph gives the beginning of the event ``noun`` names ('a boycott, which began on 5 December
    1955'; 'The boycott began on 5 December 1955'): exactly one such date, else None and the reason."""
    pattern = re.compile(rf"\b{re.escape(noun)}s?\b[^.;]{{0,40}}?\b{_CAL_BEGIN_VERBS}\s++(?:on|in)\s++(?P<date>{_CAL_DATE_TEXT})", re.IGNORECASE)
    found: dict[tuple[int, int], tuple[_CalDate, str]] = {}
    for j in range(max(0, si - 12), si):
        for m in pattern.finditer(sentences[j][:20_000]):  # (each earlier sentence read to a bound: a look-up is linear in the paragraph)
            dates = _cal_dates(m.group("date"))
            if dates:
                found[(dates[0].lo, dates[0].hi)] = (dates[0], sentences[j].strip())
    if len(found) == 1:
        d, where = next(iter(found.values()))
        return d, f"its start is the date the paragraph gives the beginning of the {noun} ('{where[:120]}')"
    return None, (f"the paragraph gives the beginning of the {noun} {len(found)} different dates" if found
                  else f"neither its sentence nor an earlier sentence of the paragraph dates the beginning of the {noun}")


def _calendar_length_specs(sentences: list[str], si: int, pi: int) -> tuple[list[_Spec], list[QuantUndecided], list[str]]:
    """The checks of the stated calendar lengths of sentence ``si`` (the module comment above): ``(specs, undecided, phrases read)``."""
    sent = sentences[si]
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    read: list[str] = []
    if len(sent) > 4000 or not _CAL_HINT_RE.search(sent):
        return specs, undecided, read
    dates = _cal_dates(sent)
    taken: list[tuple[int, int]] = []
    starts: dict[str, tuple[Optional[_CalDate], str]] = {}

    def add(m: "re.Match[str]", d1: Optional[_CalDate], d2: Optional[_CalDate], basis: str = "", why: str = "") -> None:
        phrase = " ".join(m.group(0).strip(" ,").split())
        taken.append((m.start("len"), m.end("len")))
        read.append(phrase)
        if d1 is None or d2 is None:
            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), phrase, f"a stated length of time whose dates cannot be paired: {why}"))
            return
        spec, und = _cal_spec(sent, phrase, m.group("q"), m.group("len"), d1, d2, basis, pi, si)
        if spec is not None:
            specs.append(spec)
        if und is not None:
            undecided.append(und)

    for m in _CAL_SPAN_LENGTH_RE.finditer(sent):
        a, b = _cal_dates(m.group("a")), _cal_dates(m.group("b"))
        add(m, a[0] if a else None, b[0] if b else None, why="its span's dates could not be read")
    for m in _CAL_LATER_RE.finditer(sent):
        if any(s <= m.start("len") < e for s, e in taken):
            continue
        before = [d for d in dates if d.end <= m.start()]
        if len(before) >= 2:
            add(m, before[-2], before[-1])
        # (with fewer than two dates before it the length dates an undated event by its offset, 'founded in 2019 and profitable two years
        # later', or relates no dated events at all, 'paid a month later': no relation between stated dates, so nothing to check or name)
    for m in _CAL_UNTIL_RE.finditer(sent):
        if any(s <= m.start("len") < e for s, e in taken):
            continue
        parts = _cal_parts(m.group("len"))
        if parts is not None and parts[1:] == (0, 0, 0) and _DUR_PHRASE_RE.match(sent, m.start()):
            continue  # 'lasted for twelve years, until ...': a length of years the duration reader above reads (with the span next to it)
        after = [d for d in dates if d.start >= m.end() and d.start - m.end() <= 60]
        if not after:
            continue
        c0, _c1 = _cal_clause(sent, m.start(), m.end())
        before = [d for d in dates if c0 <= d.start and d.end <= m.start()]
        if before:
            add(m, before[-1], after[0])
            continue
        head = re.search(r"\b(?:the|this|that|its|their)\s++(?:[a-z]+\s++)?([a-z]{3,20})\s*+$", sent[max(0, m.start() - 80): m.start()], re.IGNORECASE)
        if head is None:
            continue  # a length up to an end date with no start the text states: it dates the start by its offset, nothing to check
        noun = head.group(1).lower()
        if noun not in starts:
            starts[noun] = _cal_event_start(sentences, si, noun)  # one look-up per event noun of the sentence
        start, how = starts[noun]
        if start is not None:
            add(m, start, after[0], basis=how)
        elif how.startswith("the paragraph gives"):
            add(m, None, None, why=how)  # the paragraph dates the event's beginning more than once: which is meant is not stated
    for m in _CAL_CUE_RE.finditer(sent):
        if any(s <= m.start("len") < e for s, e in taken):
            continue
        c0, c1 = _cal_clause(sent, m.start(), m.end())
        left = [d for d in dates if c0 <= d.start and d.end <= m.start()]
        right = [d for d in dates if m.end() <= d.start and d.end <= c1]
        if not left or not right:
            continue  # an interval against an event the sentence does not date: the chronology check names the order
        cue = m.group("cue").lower()
        earlier, later = (left[-1], right[0]) if cue in ("before", "earlier than", "prior to") else (right[0], left[-1])
        add(m, earlier, later)
    for m in _CAL_NOUN_RE.finditer(sent):
        if any(s <= m.start("len") < e for s, e in taken):
            continue
        c0, c1 = _cal_clause(sent, m.start(), m.end())
        own = [d for d in dates if c0 <= d.start and d.end <= c1]
        noun = m.group("noun").lower()
        if len(own) == 2:
            add(m, own[0], own[1])  # 'The war of three years and one month, from 25 June 1950 to 27 July 1953, ...': the two dates of its clause
            continue
        start, _how = _cal_event_start(sentences, si, noun) if not own else (None, "")
        if own or start is not None:
            # a length of an event the text dates: named undecided with what is missing ('A war of three years and one month ...' after 'the
            # war had begun on 25 June 1950'); one of an event the text never dates relates no dated events, so nothing is named
            add(m, None, None, why=(f"the paragraph dates the beginning of the {noun} ({start.text}) but neither this sentence nor the paragraph "
                                    f"states its end" if start is not None else f"its clause states {len(own)} date(s) of the {noun}, not the two its length spans"))
    return specs, undecided, read


def _paragraph_sentences(text: str, reading: QuantReading):
    """``(paragraph number, paragraph, sentences, sentence numbers or None)`` of ``text``: the general reading splits
    blank-line paragraphs with the shared splitter (numbers 1, 2, ...); the SI reading takes the STEM statements of the SI
    quant view (maths masked), numbered as the STEM claim ids, and the paragraph is the view from its first statement to its
    last."""
    if not reading.si:
        for pi, para in enumerate((p for p in _PARA_RE.split(text.strip()) if p.strip()), start=1):
            yield pi, para, split_sentences(para), None
        return
    view = si_quant_view(text, reading.profile)
    grouped: dict[int, tuple[list[str], list[int], list[tuple[int, int]]]] = {}
    for pi, number, start, end in si_statements(text, reading.profile):
        texts, numbers, bounds = grouped.setdefault(pi, ([], [], []))
        texts.append(view[start:end])
        numbers.append(number)
        bounds.append((start, end))
    for pi in sorted(grouped):
        texts, numbers, bounds = grouped[pi]
        yield pi, view[bounds[0][0]:bounds[-1][1]], texts, numbers


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


def _parts_spec(clause: str, whole: _Fig, parts: list[_Fig], tolerance: Fraction, phrase: str, how: str) -> _Spec:
    """The parts of a stated total may not exceed it (beyond the tolerance, since each figure may be rounded)."""
    wv = _frac(whole.num, whole.unit)
    names = [f"part{i + 1}" for i in range(len(parts))]
    premises = (("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(wv)}, f"total = {_shown(whole, whole.unit)}"),
                *((f"PART{i + 1}", {"op": "eq", "left": _v(n), "right": _real(_frac(p.num, p.unit))}, f"part = {_shown(p, p.unit)}") for i, (n, p) in enumerate(zip(names, parts))))
    concl = {"op": "le", "left": _sum_expr(names), "right": {"op": "mul", "args": [_real(1 + tolerance), _v("whole")]}}
    label = f"{how}: {' + '.join(_shown(p, p.unit) for p in parts)} does not exceed the total {_shown(whole, whole.unit)}"
    return _Spec("parts", clause.strip(), (("whole", "the total as stated"), *((n, "a part as stated") for n in names)), premises,
                 ("STATED_PARTS", concl, label), Fraction(0), "both", "figure stated in the report itself", "", phrase)


def _without_long_number_runs(pi: int, para: str, sentences: list[str], numbers: Optional[list[int]],
                              undecided: list[QuantUndecided]) -> tuple[str, list[str]]:
    """``(para, sentences)`` with every sentence that holds a run of more number words than a figure in words takes
    (:data:`_LONG_NUMBER_RUN_RE`, 'one hundred and one hundred and ...') blanked, and each such sentence reported undecided
    (``CORE-QNT-001``): no reader of the sentence or of its paragraph reads a figure in it, so no part of the run is read as a
    figure of its first words. Unchanged (the same objects) when no sentence holds such a run."""
    runs = [_LONG_NUMBER_RUN_RE.search(s) for s in sentences]
    if not any(runs):
        return para, sentences
    out = list(sentences)
    for si, (sent, run) in enumerate(zip(sentences, runs)):
        if run is None:
            continue
        undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), " ".join(run.group(0).split())[:100] + " ...", LONG_NUMBER_RUN_REASON))
        out[si] = ""
        at = para.find(sent)
        if at >= 0:
            para = para[:at] + " " * len(sent) + para[at + len(sent):]
    return para, out


@lru_cache(maxsize=128)
def _analyse(text: str, tolerance: Fraction, reading: QuantReading = GENERAL) -> tuple[tuple[_Spec, ...], tuple[QuantUndecided, ...], tuple[tuple[str, tuple], ...]]:
    """Read every paragraph of ``text``: the pair-bound checks, the cross-sentence checks, the
    statements left undecided, and the share/total matches (built later). Memoised per text
    and reading, since the core pack asks for the checks and for the undecided statements of
    one report. ``reading`` selects the general or the SI reading (module docstring): the SI
    reading reads the relations of pairs, series, shares and totals in SI units, and none of
    the general reading's other prose readers."""
    si_mode = reading.si
    pat = _patterns(reading)
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    read_phrases: dict[tuple[int, str], list[str]] = {}   # (paragraph, sentence) -> phrases a round-9 prose reader read (never also undecided)
    own_undecided: set[int] = set()                       # the round-9 prose readers' own undecided entries (kept)
    all_clauses: list[str] = []
    clause_where: list[tuple[int, int, str]] = []   # (paragraph, sentence number, sentence) of every clause, for SI undecided shares
    for pi, para, sentences, numbers in _paragraph_sentences(text, reading):
        series: list[_Series] = []
        pending: list[tuple[int, str, list[_Derived], Optional[tuple]]] = []   # (sentence index, clause, unbound derived, extras)
        per_sentence_specs: list[tuple[int, _Spec]] = []
        sentence_pairs: dict[int, list[tuple[_Pair, str, str]]] = {}   # sentence index -> (pair, clause, the pair's subject words)
        para, sentences = _without_long_number_runs(pi, para, list(sentences), numbers, undecided)
        for si, sent in enumerate(sentences):
            if not sent:
                continue  # a sentence holding a run of number words too long for a figure: reported undecided, not read
            clauses = split_clauses(sent) if (";" in sent or _LOWER_CONTINUATION_RE.search(sent)) else [sent]
            all_clauses.extend(clauses)
            if si_mode:
                clause_where.extend((pi, _num(numbers, si), sent.strip()) for _c in clauses)
            try:
                part_specs, part_undecided = _part_specs(sent, para, si, pi, tolerance) if not si_mode else ([], [])
                if not si_mode:
                    c2_specs, c2_undecided, c2_read = _c2_prose_specs(sent, si, pi, tolerance)
                    part_specs, part_undecided = part_specs + c2_specs, part_undecided + c2_undecided
                    own_undecided.update(id(u) for u in c2_undecided)
                    if c2_read:
                        read_phrases.setdefault((pi, sent.strip()), []).extend(c2_read)
                if not si_mode and _RATE_TREND_RE.search(sent):
                    trend_specs, trend_undecided = _rate_trend_specs(sentences, si, pi)
                    part_specs, part_undecided = part_specs + trend_specs, part_undecided + trend_undecided
                if not si_mode and "year" in sent.lower() and _DUR_PHRASE_RE.search(sent):
                    dur_specs, dur_undecided = _duration_specs(sentences, si, pi, tolerance)
                    part_specs, part_undecided = part_specs + dur_specs, part_undecided + dur_undecided
                if not si_mode and _CAL_HINT_RE.search(sent):
                    # a calendar length between dated events (round 9 second pass): decided, or named undecided with its own reason
                    cal_specs, cal_undecided, cal_read = _calendar_length_specs(sentences, si, pi)
                    part_specs, part_undecided = part_specs + cal_specs, part_undecided + cal_undecided
                    own_undecided.update(id(u) for u in cal_undecided)
                    if cal_read:
                        read_phrases.setdefault((pi, sent.strip()), []).extend(cal_read)
            except FigureTooLarge:
                part_specs, part_undecided = [], [QuantUndecided(pi, _num(numbers, si), sent.strip(), sent.strip()[:120], _TOO_LARGE_REASON)]
            per_sentence_specs.extend((si, sp) for sp in part_specs)
            undecided.extend(part_undecided)
            # a worked equation ('$6,000 ÷ $2.00 = 3,000 loaves') is written arithmetic this reader does not decide: named, never silent
            for eq in (worked_equations(sent) if not si_mode else ()):  # the SI reading: the STEM pack decides the maths
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), eq.phrase[:160], WORKED_EQUATION_REASON))
            for clause in clauses:
                try:
                    derived = _derived_phrases(clause, si_mode)
                    all_pairs = _pairs(clause, pat)
                    if len(derived) > _MAX_CLAUSE_FIGURES or len(all_pairs) > _MAX_CLAUSE_FIGURES:
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), clause.strip()[:120], _TOO_MANY_REASON))
                        continue
                    pairs = _pairs_outside(all_pairs, derived)
                    for p in pairs:  # a later figure opening written arithmetic with no stated result: the change's end is not stated
                        if p.arith:
                            undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), p.arith[:120], ARITH_ENDPOINT_REASON))
                    pairs = [p for p in pairs if not p.arith]
                    prev_end = 0
                    heads: list[str] = []   # the text before each pair, from the end of the pair before it (its subject, for an exchange rate)
                    for p in pairs:
                        s = _si_series_of(p, si, clause, reading.profile) if si_mode else _series_of(p, si, clause)
                        if s is not None:
                            series.append(s)
                        heads.append(clause[prev_end: p.start])
                        sentence_pairs.setdefault(si, []).append((p, clause, heads[-1]))
                        prev_end = p.end
                    bound: set[int] = set()
                    segments = _segments(clause, pairs)
                    for k, (p, (seg_start, seg_end)) in enumerate(zip(pairs, segments)):
                        # a change stated of another quantity in an earlier clause of the segment is not this pair's (round 9, c2 bm-t15)
                        mine = [d for d in derived if seg_start <= d.start < seg_end and not _foreign_change(clause, d, p)]
                        if not mine:
                            continue
                        for d in mine:
                            after = p.last if p.tail and d.start >= p.end else p.after
                            decade = _decade_before(clause, d.start)
                            if decade is not None and _outside_decade(p.before, after, int(decade.group("d"))):
                                continue  # 'so the 1850s added about 7,000 miles' after a pair of 1860 and 1870: read through the decade, not the pair
                            bound.add(id(d))
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
                                base = _xrate_base(p.before, after)
                                if base:
                                    # an exchange rate: a change said of the base currency ('a rise in the dollar's price of 1,670-fold') is the
                                    # figures' own; one said of another currency, or of no currency in a sentence whose subject is not the base
                                    # ('The franc fell ..., a fall of 90 per cent'), is the change of the rate or of the currency's value
                                    named = _named_currency(clause[p.end:d.end] if d.start >= p.end else clause[d.start:d.end])
                                    if (named != base) if named else (_xrate_reading(heads, k, base)[0] != "written"):
                                        spec = _xrate_either(spec, values, d, statement, tolerance, base, si=si_mode)
                                per_sentence_specs.append((si, _through_arithmetic(spec, p, values)))
                    # a pair governed by a direction word and no stated change ('pig iron rising from X to Y'): the direction is checked
                    prev_dir: Optional[str] = None
                    prev_end = 0
                    for k, (p, (seg_start, seg_end)) in enumerate(zip(pairs, segments)):  # the SI reading reads the figures in SI units ('from 4.0 Ω to 2.4 Ω')
                        head = clause[prev_end: p.start]
                        inner = clause[p.start: p.after.start]   # 'before climbing to' for a continuation; 'from X to' for a from/to pair
                        prev_end = p.end
                        if any(seg_start <= d.start < seg_end and not _foreign_change(clause, d, p) for d in derived):
                            prev_dir = None
                            continue  # a stated change already decides the pair's direction (a change of another quantity does not)
                        # the direction word must govern the pair: right before its 'from' (adverbs aside), or inside a continuation
                        own = _PAIR_DIR_BEFORE_RE.search(head) if inner[:4].lower() == "from" else _PAIR_DIR_RE.search(inner)
                        word = own.group(1).lower() if own else (prev_dir if _elliptical(clause[max(0, p.start - 40): p.start]) else None)
                        prev_dir = word
                        if not word:
                            continue
                        if not re.search(r"\bto\b", clause[p.before.start: p.after.start], re.IGNORECASE):
                            continue  # 'from 2.6 per cent and twelve seats': two figures of one date, not a change from one to the other
                        if si_mode and word in _MOTION_WORDS and _si_length_pair(p, reading.profile):
                            continue  # 'the ball falls from 0 m to 20 m': a verb of motion over positions, not a change of a quantity
                        values, why = _si_values(p.before, p.last, reading.profile) if si_mode else _values(p.before, p.last)
                        if values is None:
                            continue  # a year span, or units that cannot be compared (a misread pair): no direction is stated between them
                        statement = clause.strip() if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                        # an exchange rate ('from 25 to the pound to 240 to the pound'): the figure is the base currency's price, so a fall of
                        # the currency the sentence names is a rise of the figure; with no currency named, a direction that holds only of the
                        # quoted currency is named undecided, never an error (integration gate 3)
                        base, quoted = _xrate_base(p.before, p.last), ""
                        if base:
                            how, name = _xrate_reading(heads, k, base)
                            if how == "inverse":
                                quoted = name
                            elif how == "open" and values.a != values.b and (values.b > values.a) != (word in _RISE_DIR_WORDS):
                                undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), statement[:160], XRATE_OPEN_REASON))
                                continue
                        per_sentence_specs.append((si, _through_arithmetic(_direction_spec(values, word, statement, quoted=quoted, base=base), p, values)))
                    for cm in (_COMPARE_RE.finditer(clause) if not si_mode and _COMPARE_HINT_RE.search(clause) else ()):
                        spec, why = _comparison_spec(cm, clause, si, sentence_pairs, pairs, tolerance)
                        if spec is not None:
                            per_sentence_specs.append((si, spec))
                        elif why:
                            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), " ".join(cm.group(0).split())[:120], why))
                    loose = [d for d in derived if id(d) not in bound]
                    low = clause.lower()
                    extras = (_MONOTONIC_RE.search(clause) if "year" in low else None,
                              _EXTREME_RE.search(clause) if _EXTREME_HINT_RE.search(low) else None,
                              _ANY_OTHER_RE.search(clause) if "any other" in low and not si_mode else None)
                    if loose or extras[0] or (extras[1] and not pairs) or extras[2]:
                        pending.append((si, clause, loose, extras))
                except FigureTooLarge:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent.strip(), clause.strip()[:120], _TOO_LARGE_REASON))
        specs.extend(spec for _si, spec in per_sentence_specs)
        standalone_cache: list = []

        def standalone(_sentences=sentences, _cache=standalone_cache) -> list:
            if not _cache:
                _cache.append(_standalone_points(_sentences))
            return _cache[0]
        series_years = sorted({y for s in series for y in s.points})  # the series are complete here: read once per paragraph
        nearest = _nearest_years(sentences) if pending else None
        for si, clause, loose, extras in pending:
            try:
                sent = sentences[si].strip()
                note = "figure stated in the report itself, in another sentence of the paragraph"
                for d in loose:
                    # 'About 5.2 million people entered ... in the 1880s, an average of about 900,000 a year': a rate of the total its clause dates
                    spec, why = _total_rate_spec(clause, d, tolerance) if not si_mode else (None, "")
                    if spec is not None:
                        specs.append(spec)
                        continue
                    if why:
                        undecided.append(QuantUndecided(pi, si + 1, sent, d.words, why))
                        continue
                    target, how = _target_years(sentences, si, clause, d.start, series_years, nearest)
                    in_equation = not si_mode and any(eq.start <= d.start < eq.end for eq in worked_equations(clause))
                    if target is None:
                        if d.soft and not series and _decade_before(clause, d.start) is None:
                            continue  # 'the army lost 22,000 men': a count, with no stated figures it could be a change of
                        if in_equation:
                            continue  # '(9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease': the worked equation is named with its true reason
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words,
                                                        f"{_no_pair_reason(clause, d) if not si_mode else 'no figures are stated with it in its sentence'} and {how}"))
                        continue
                    kinds = {"pct"} if d.kind == "points_change" and d.percentage_points else None
                    s, why = _pick_series(series, list(target), clause, kinds=kinds, extra=standalone() if not si_mode else None)
                    if s is None:
                        if in_equation:
                            continue
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words,
                                                        f"{_no_pair_reason(clause, d) if not si_mode else 'no figures are stated with it in its sentence'} and {why}"))
                        continue
                    if si_mode and (s.kind or "").startswith("si-affine") and d.kind in _RELATIVE_KINDS:
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, "a relative change is not defined on an offset temperature scale (°C, °F), so the figures were not read"))
                        continue
                    (va, sa), (vb, sb) = s.points[target[0]], s.points[target[1]]
                    values = _Values(va, vb, sa + f" (stated in sentence {_num(numbers, s.sentence)} of the paragraph)", sb + f" (stated in sentence {_num(numbers, s.sentence)} of the paragraph)",
                                     s.kind == "pct", target[0], target[1], s.unit, "")
                    spec, why = _pair_spec(values, d, clause.strip(), tolerance, note,
                                           f"stated across sentences: {how}; figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, list(target))}", si=si_mode)
                    if spec is None:
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words, why))
                    else:
                        specs.append(spec)
                if not extras:
                    continue
                mono, extreme, any_other = extras
                if any_other:
                    spec, why = _any_other_spec(any_other, clause, para, series, standalone())
                    if spec is not None:
                        specs.append(spec)
                    for reason in why:
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, any_other.group(0), reason))
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
                    target, how = _target_years(sentences, si, clause, extreme.start(), series_years, nearest)
                    s, why = (None, how) if target is None else _pick_series(series, list(target), clause)
                    if s is None:
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, extreme.group(0),
                                                        f"{_no_pair_reason(clause, None) if not si_mode else 'no figures are stated with it in its sentence'} and {why}"))
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
            except FigureTooLarge:
                undecided.append(QuantUndecided(pi, _num(numbers, si), sentences[si].strip(), clause.strip()[:120], _TOO_LARGE_REASON))
    others: list[tuple[str, tuple]] = []
    if si_mode:
        for k, sent in enumerate(all_clauses):
            for kind, m in (("share", pat.share.search(sent)), ("total", _search_total(pat.total, sent))):
                if not m:
                    continue
                try:
                    values, why = _si_others(kind, m.groups(), reading.profile)
                except FigureTooLarge:
                    values, why = None, _TOO_LARGE_REASON
                if values is None:
                    p_no, s_no, s_text = clause_where[k]
                    undecided.append(QuantUndecided(p_no, s_no, s_text, m.group(0).strip()[:120], why))
                else:
                    others.append((kind, (sent.strip(), m.groups(), values)))
        return tuple(specs), tuple(undecided), tuple(others)
    if read_phrases:
        # a phrase a round-9 prose reader read (decided, or named undecided with its own reason) is not named again by the derived-figure
        # reader ('a total of 26 marks' with no pair; 'grew by 38.0%' with its working in brackets)
        def _covered(u: QuantUndecided) -> bool:
            phrases = read_phrases.get((u.paragraph, (u.sentence_text or "").strip()))
            if not phrases or not u.phrase or id(u) in own_undecided:
                return False
            ph = " ".join(u.phrase.split())
            words = ph.split()
            head = " ".join(words[:-1]) if len(words) >= 3 else ph  # the phrase without its trailing unit word ('a total of 26 [marks]')
            return any(ph in r or r in ph or head in r for r in phrases)
        undecided = [u for u in undecided if not _covered(u)]
    for sent in all_clauses:
        sh = _SHARE_RE.search(sent)
        if sh and not any(sum(ch.isdigit() for ch in (g or "")) > MAX_FIGURE_DIGITS for g in sh.groups()):
            others.append(("share", (sent.strip(), sh.groups())))
        tot = _search_total(_TOTAL_RE, sent)
        if tot and not any(sum(ch.isdigit() for ch in (tot.group(f"n{i}") or "")) > MAX_FIGURE_DIGITS for i in (1, 2, 3)) \
                and all(_cur_compatible(_cur_key(tot.group(f"c{i}") or ""), tot.group(f"w{i}") or "", _cur_key(tot.group("c3") or ""), tot.group("w3") or "") for i in (1, 2)):
            others.append(("total", (sent.strip(), tuple((tot.group(f"n{i}"), tot.group(f"u{i}"), tot.group(f"c{i}") or "", tot.group(f"w{i}") or "") for i in (1, 2, 3)))))
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
    5 per cent of the computed value; see :data:`TOLERANCE_RULE`). Memoised per call (the core
    pack reads the checks for its formal problems and for its check-limit report). ``reading``: see the module docstring (the
    general reading by default)."""
    return list(_extract_cached(text, request_id, claim_id, tolerance, reading))


@lru_cache(maxsize=32)
def _extract_cached(text: str, request_id: str, claim_id: str, tolerance: Fraction, reading: QuantReading = GENERAL) -> tuple[QuantCheck, ...]:
    return tuple(_extract(text, request_id=request_id, claim_id=claim_id, tolerance=tolerance, reading=reading))


def _extract(text: str, *, request_id: str, claim_id: str, tolerance: Fraction, reading: QuantReading = GENERAL) -> list[QuantCheck]:
    specs, _undecided, others = _analyse(text, tolerance, reading)
    checks: list[QuantCheck] = []
    n = 0
    prefix = {"percent_change": "pct", "points_change": "points", "fraction_change": "frac", "fold_change": "fold", "series_monotonic": "trend", "series_extreme": "extreme",
              "abs_change": "abs", "rate_change": "rate", "comparison": "cmp", "pair_direction": "dir", "parts": "parts", "share": "share", "difference": "diff",
              "duration": "dur", "rate_trend": "trend", "product_total": "prod", "rate_total": "rtot"}
    for spec in specs:
        n += 1
        if spec.rule:
            rule = spec.rule
        elif spec.kind in ("series_monotonic", "series_extreme", "pair_direction", "rate_trend"):
            rule = "exact comparison of the figures as stated (no tolerance)"
        elif spec.kind == "parts":
            rule = (f"the stated parts may not exceed the stated total by more than {float(tolerance) * 100:g}% of it (each figure may be rounded)")
        elif spec.kind == "duration":
            rule = "exact: the stated number of years equals the span's difference, or the difference plus one when both end years are counted"
        elif spec.kind == "comparison":
            rule = "exact comparison of the figure with the stated benchmark" + ("; the stated margin: " + _rule_text(tolerance, spec.floor, spec.side) if len(spec.conclusion[1].get("args", [])) > 1 and spec.conclusion[1].get("op") == "and" else "")
        else:
            rule = _rule_text(tolerance, spec.floor, spec.side)
        checks.append(QuantCheck(f"quant-{n}", spec.kind, spec.sentence, _problem(f"quant-{prefix[spec.kind]}-{n}", claim_id, request_id, list(spec.symbols), list(spec.premises), spec.conclusion, spec.note),
                                 rule=rule, basis=spec.basis, phrase=spec.phrase, failure_severity=spec.severity))
    if reading.si:  # shares and totals read in SI units, with the sign-aware band
        for kind, (sent, g, values) in others:
            n += 1
            if kind == "share":
                pct, whole, part = values
                computed = {"op": "div", "left": {"op": "mul", "args": [_real(pct), _v("whole")]}, "right": _real(Fraction(100))}  # constant * variable: linear
                checks.append(QuantCheck(f"quant-{n}", "share", sent, _problem(f"quant-share-{n}", claim_id, request_id,
                    [("pct", "stated percentage"), ("whole", "stated whole")],
                    [("PCT", {"op": "eq", "left": _v("pct"), "right": _real(pct)}, "percentage"), ("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(whole)}, "whole")],
                    ("STATED_PART", _within_si(computed, part, tolerance), f"stated part {g[3]} {g[4] or ''}".strip())),
                    rule=_rule_text(tolerance, Fraction(0), "both")))
            else:
                x, y, z = values
                s = {"op": "add", "args": [_v("x"), _v("y")]}
                checks.append(QuantCheck(f"quant-{n}", "total", sent, _problem(f"quant-total-{n}", claim_id, request_id,
                    [("x", "first addend"), ("y", "second addend")],
                    [("X", {"op": "eq", "left": _v("x"), "right": _real(x)}, "x"), ("Y", {"op": "eq", "left": _v("y"), "right": _real(y)}, "y")],
                    ("STATED_TOTAL", _within_si(s, z, tolerance), f"stated total {g[4]} {g[5] or ''}".strip())),
                    rule=_rule_text(tolerance, Fraction(0), "both")))
        return checks
    for kind, (sent, g) in others:
        n += 1
        if kind == "share":
            pct, whole, part = _number(g[0]), _frac(g[1], g[2]), _frac(g[3], g[4])
            computed = {"op": "div", "left": {"op": "mul", "args": [_real(pct), _v("whole")]}, "right": _real(Fraction(100))}  # constant * variable: linear
            checks.append(QuantCheck(f"quant-{n}", "share", sent, _problem(f"quant-share-{n}", claim_id, request_id,
                [("pct", "stated percentage"), ("whole", "stated whole")],
                [("PCT", {"op": "eq", "left": _v("pct"), "right": _real(pct)}, "percentage"), ("WHOLE", {"op": "eq", "left": _v("whole"), "right": _real(whole)}, "whole")],
                ("STATED_PART", _within(computed, part, tolerance), f"stated part {g[3]} {g[4] or ''}".strip())),
                rule=_rule_text(tolerance, Fraction(0), "both")))
        else:
            (n1, u1, c1, w1), (n2, u2, c2, w2), (n3, u3, c3, w3) = g
            x, y, z = _frac(n1, u1), _frac(n2, u2), _frac(n3, u3)
            s = {"op": "add", "args": [_v("x"), _v("y")]}
            shown = " ".join(t for t in (f"{c3}{n3}", u3 or "", w3) if t)
            checks.append(QuantCheck(f"quant-{n}", "total", sent, _problem(f"quant-total-{n}", claim_id, request_id,
                [("x", "first addend"), ("y", "second addend")],
                [("X", {"op": "eq", "left": _v("x"), "right": _real(x)}, f"x = {' '.join(t for t in (f'{c1}{n1}', u1 or '', w1) if t)}"),
                 ("Y", {"op": "eq", "left": _v("y"), "right": _real(y)}, f"y = {' '.join(t for t in (f'{c2}{n2}', u2 or '', w2) if t)}")],
                ("STATED_TOTAL", _within(s, z, tolerance), f"stated total {shown}")),
                rule=_rule_text(tolerance, Fraction(0), "both"), phrase=shown))
    return checks
