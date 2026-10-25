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
  this reader does not decide: it is returned undecided with that reason, never skipped.

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
computed value (rounding to the nearest whole per cent is never a finding). ``more
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
  greatest rise'), shares and totals. The general reading's other prose readers (absolute changes
  and average rates, multiples such as 'six times', parts of a total, differences between
  parties, stated lengths of years, rate trends, comparisons with a benchmark, a pair's direction
  word, 'more than any other decade', worked equations) read their figures with the general
  reading's scale words ('m' is million there), so they do not run in the SI reading; an
  approach qualifier ('nearly', 'just over') is read with the symmetric band.
"""
from __future__ import annotations

import bisect
import itertools
import re
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
#: A number in words below a thousand: 'forty-five', 'two hundred and sixty'. Scale words (thousand, million, ...) are units.
#: One atomic group of at most four words, 'and' only after 'hundred': a run of number words ('twenty-three twenty-three …',
#: 'one hundred and one hundred and …') is read in one bounded way, so the patterns built on it never backtrack through it.
_WNUM = rf"(?>(?:{_WNUM_TOKEN})(?:[\s-]+hundred(?:\s+and)?)?(?:[\s-]+(?:{_WNUM_TOKEN})){{0,2}})(?![a-z])"
#: Digits: thousands groups (with an optional decimal part), a plain decimal, or a decimal comma ('1,9': one or two digits after it).
#: A figure never starts inside another ('1234,567' is not '4,567'; '4.03' is not '03'): besides reading what was written, the
#: guard keeps every pattern linear on a long run of digits, since no match is attempted from each digit of the run.
#: (security round 1, SEC-1) A space-grouped figure never starts at a group of three digits that follows two groups of three digits of
#: its run: a figure from there reads the same groups to the same end, with the same text after it, as a figure from the group before
#: (or the one before that), which every scan of the run has already tried. Without the guard every group of a long run ('000 000
#: 000 …') was a new start that read the run again to its end (quadratic); with it each run is read from at most three of its
#: places. The run's head and the two groups after it still start a figure, so a scan that starts right after a head another reader
#: took ('= 138 349 800') reads every figure as before (tests/branches/test_security_round1_digits.py).
_DIGITS = (r"(?<!\d)(?<!\d[.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?!(?<=[ \u00a0\u2009\u202f]\d{3}[ \u00a0\u2009\u202f]\d{3}[ \u00a0\u2009\u202f])\d{3})\d{1,3}(?:[ \u00a0\u2009\u202f]\d{3})+"
           r"(?![\d,]|\.\d|[ \u00a0\u2009\u202f]\d)(?:\.\d+)?|\d+(?:\.\d+)?|\d+,\d{1,2})")
#: (repair round 4, rerun-parser-safety-13) thousands grouped by a space ('45 000', '1 800 000', SI style) are one figure, so a pair
#: written with one grouped and one plain figure ('from 30000 to 45 000') compares the two whole values
#: A currency sign before a figure ('$4.03', '£600 million', 'US$13 billion'): carried with the figure as its unit of account, so a
#: figure in dollars is compared only with a figure in dollars.
_CUR = r"(?:US\$|U\.S\.\s?\$|A\$|C\$|\$|£|€|¥)"
#: The longest numeral read as a figure (far below Python's 4,300-digit integer-string limit): a longer run of digits is refused per
#: statement (``CORE-QNT-001``, 'too large to check'), never converted, so one oversized figure cannot discard the report's other checks.
MAX_FIGURE_DIGITS = 1000
#: A figure in scientific notation is no figure of the general reading ('2.5e3', '2.5 × 10³' are not 2.5): the mantissa is
#: never read alone, so a pair holding one is not read (the SI reading reads it exactly)
_NOT_SCI = r"(?![eE][-+]?\d|\s?[×xX*·]\s?10(?:\^|\*\*|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]))"
_NUM = rf"({_DIGITS}|{_WNUM})(?!\d|,\d|\.\d){_NOT_SCI}"  # never split a thousands group or a decimal
_NUMX = rf"(?:{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d){_NOT_SCI}"
_AMOUNT = rf"([-+−]?(?:{_DIGITS})|{_WNUM})(?!\d|,\d|\.\d){_NOT_SCI}"  # a derived figure may carry a sign (ASCII or Unicode minus)
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


def _fig(i: int, *, dated: bool = False, numx: str = _NUMX, unit_words: str = _UNIT_WORDS) -> str:
    """One figure of a pair, with named groups ``q<i>`` (qualifier), ``c<i>`` (currency sign), ``n<i>`` (number), ``u<i>`` (unit),
    ``noun<i>`` and ``d<i>`` (date). ``numx`` and ``unit_words`` default to the general reading's; the SI reading passes its own."""
    date = _DATE_BODY if dated else _DATE
    return (rf"(?:(?P<q{i}>{_QUAL})\s+)?(?P<c{i}>{_CUR})?\s?(?P<n{i}>{numx})(?:\s*(?P<u{i}>{unit_words})(?!\w))?(?P<noun{i}>{_NOUN}){_PER}(?P<d{i}>{date})")


_FROM_TO_RE = re.compile(rf"\b(?:from|of)\s+{_fig(1)}\s+(?:to|and)\s+{_fig(2)}", re.IGNORECASE)
#: '... X in D1 and [reached] Y in D2': both dates are required, so a list of undated figures is never a pair.
_TO_VERB = (r"(?:reached|rose to|risen to|climbed to|grew to|increased to|jumped to|soared to|fell to|fallen to|dropped to|declined to|decreased to|"
            r"sank to|shrank to|stood at|was|were|had|bought|cost|numbered|totalled|totaled|to)")
#: (security round 1) The links between the figures of a list, their white space read possessively. ', and' after a figure was
#: '\s*,?\s+and' and the lead of the next item '\s*(?:,\s*(?:and\s+)?|\s+and\s+)': a run of white space after a figure with no
#: comma or 'and' after it was split between two quantifiers in every way before failing (quadratic: a pair, 16,000 spaces and
#: a word held the prose reading for 2.8 s). A run is now read once: a run with at most one comma that white space follows, then
#: 'and', is what '\s*,?\s+' read, and the lead of an item is the run and a comma, or the run (one space or more) and 'and'. The
#: run's longest reading is the only one a comma or 'and' can follow, so every list is read as before
#: (tests/branches/test_security_round1_lists.py).
_AND_LINK = r"(?:\s*+,)?+\s++and\s+"
_ITEM_LEAD = r"(?:\s*+,\s*(?:and\s+)?|\s++and\s+)"
_AND_DATED_RE = re.compile(rf"(?<![\w.,]){_fig(1, dated=True)}{_AND_LINK}(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{_fig(2, dated=True)}", re.IGNORECASE)
#: The next item of a list after a pair's second figure: ', 4.5 million in 1931 and 5.6 million in 1932'.
_LIST_ITEM_RE = re.compile(rf"{_ITEM_LEAD}(?:then\s+)?(?:to\s+)?{_fig(3, dated=True)}", re.IGNORECASE)
#: A chained continuation: '..., before climbing to 5.6 million in 1932', ', and on to 4.5 million in 1931'.
#: A manner adverb may stand between the verb and "to" ("then rose sharply to 11.4%": repair round 4, ADV4-12; unread, the
#: continuation after it was chained from the figure before it, "5.9% ... before falling to 8.1%", a false failure).
_CONT_ADVERB = r"(?:(?:sharply|steeply|rapidly|quickly|slowly|slightly|gradually|dramatically|significantly|considerably|markedly|modestly|briefly|steadily|suddenly|substantially)\s+)?"
_CONT_RE = re.compile(
    rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
    rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+{_CONT_ADVERB})?(?:further\s+|again\s+|back\s+)?to\s+{_fig(3)}"
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
    rf"|{_DIR_VERB}\s+by\s+(?:({_QUAL})\s+)?{_AMOUNT}\s*{_PCT_UNIT}(?!\s*points?\b)",
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
#: A multiple: 'six times its earlier length', 'four times as large', 'twice its 1928 level' (a fold change by another wording).
_TIMES_RE = re.compile(
    rf"\b(?:(?P<q>{_QUAL})\s+)?(?:(?P<n>(?<![\d.,])\d+(?:\.\d+)?|{_WNUM}|a hundred)\s+times|(?P<twice>twice|thrice))\s+"
    r"(?=as\b|its\b|their\b|his\b|her\b|the\b|that\b|what\b|over\b|larger\b|greater\b|bigger\b|higher\b|longer\b|more\b)", re.IGNORECASE)
#: The amount of an absolute change: a figure with an optional scale or count unit and a noun ('roughly 4,500 miles', '2.9 million
#: tonnes'), never a per-cent, point, fraction, fold or multiple (those are the relative readings above).
_ABS_AMOUNT = (rf"(?:(?P<q>{_QUAL})\s+)?(?P<cur>{_CUR})?\s?(?P<n>{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
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
               rf"(?P<n>{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
               r"(?!\s*(?:per\s*cent|percent|%|percentage|points?\b|times\b|-?fold\b)|[\s-]+(?:half|halves|thirds?|quarters?|fifths?|tenths?)\b)"
               rf"(?:\s*(?P<u>{_SCALE_UNIT}|seats|votes)\b)?(?P<noun>{_NOUN})(?:{_RATE_TAIL})?", re.IGNORECASE),
)
#: (security round 1) The rate tail as the average-rate patterns below read it: unbracketed, so its second alternative is a pattern of
#: its own (white space then 'annually' or 'yearly', anywhere in the clause). That alternative was tried from every space of a run and
#: read the run again to its end each time (quadratic: 1.4 s on 'averaging' and 8,000 spaces, against 0.3 s for 4,000). It now starts
#: only where its run of white space starts. Every match ends on a letter, never inside a run, so the scan reaches a space inside a
#: run only after trying the run's start, where the same alternative reads the same run to the same 'annually' or fails the same way:
#: the matches are the ones they were (tests/branches/test_security_round1_rates.py).
_RATE_SCAN_TAIL = r"\s+(?:a|an|per|each|every)\s+(?P<per>year|annum|decade|month)\b|(?<!\s)\s+(?P<annually>annually|yearly)\b"
#: An average rate: 'an average of 450 miles a year', 'averaging 450 miles a year', 'at an average rate of 450 miles per year'.
_RATE_RES = (
    re.compile(rf"\b(?:an?\s+)?(?:annual\s+)?average\s+(?:annual\s+|yearly\s+)?(?:(?:rate|increase|rise|growth|gain|fall|decline|addition)\s+)?(?:of\s+)?{_ABS_AMOUNT}{_RATE_SCAN_TAIL}", re.IGNORECASE),
    re.compile(rf"\baverag(?:ing|ed|es)\s+{_ABS_AMOUNT}{_RATE_SCAN_TAIL}", re.IGNORECASE),
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
#: A period named by an anaphor ('over the twenty years', 'in that decade', 'over the period', 'during this time'): the
#: paragraph's dated span, checked against the number of years when it names one (repair round 1, re-run review A-FA-QNT).
#: A year that opens a trend: 'from 1990', 'since 2015', 'after 2001', 'starting in 2010'.
_ANCHOR_YEAR_RE = re.compile(r"\b(?:from|since|after|starting\s+in|beginning\s+in)\s+(1[0-9]{3}|20[0-9]{2})\b", re.IGNORECASE)
_PERIOD_ANAPHOR_RE = re.compile(
    r"\b(?:over|during|in|across|throughout|within)\s+(?:the|that|this|those|these)\s+(?:(?P<n>\d{1,3}|ten|twenty|thirty|forty|fifty|five|"
    r"two|three|four|six|seven|eight|nine|eleven|twelve|fifteen)\s+)?(?P<unit>years|decade|period|time|span)\b", re.IGNORECASE)
_YEAR_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
                     "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def _number_of_years(n: Optional[str], unit: str) -> Optional[int]:
    """The length a period anaphor names: its number of years ('the twenty years'), ten for a decade, else None."""
    if unit.lower() == "decade":
        return 10
    if not n:
        return None
    return int(n) if n.isdigit() else _YEAR_COUNT_WORDS.get(n.lower())
_YEAR_TOKEN_RE = re.compile(r"(?<![\d,.])\b(1[0-9]{3}|20[0-9]{2})\b(?![\d,.]?\d)")
_YEAR_LIKE_RE = re.compile(r"^(?:1[0-9]{3}|20[0-9]{2})$")
_PCT_WORDS = frozenset({"per cent", "percent", "%"})
#: The links of a stated share ('5 per cent of the 200 seats, or 10'): after 'of' and between the whole and the part. Every run
#: of white space in them is read once (possessive): the words a run may stand before ('the', 'about', 'or', 'that is', a
#: noun) and a figure never start with white space, so a run read in part leaves the same match or none. With greedy runs,
#: 'of the' and ', ' before a long run of spaces split it between two and three quantifiers (quadratic and cubic in the run;
#: security round 2, SEC-V5).
_SHARE_OF = r"\s+of\s++(?:the\s++)?(?:about|around|roughly)?\s*+"
_SHARE_LINK = (r"(?:\s++[a-z]++){0,2}?(?:\s*+,\s*+(?:or|i\.e\.|that is)?|\s++(?:or|was|is|=|that is|i\.e\.)|\s*+\()"
               r"\s*+(?:about|around|roughly|some)?\s*+")
_SHARE_RE = re.compile(rf"\b{_NUM}\s*{_PCT_UNIT}{_SHARE_OF}{_NUM}{_UNIT}{_SHARE_LINK}{_NUM}{_UNIT}", re.IGNORECASE)


#: The white space between the word of a total and its figure in the readings built by :func:`_build_patterns` ('a total of
#: about 9'), each run read once (possessive): a figure and 'about' never start with white space, so a run read in part
#: leaves the same match or none. Read greedily, a long run there was split between the two quantifiers around the optional
#: qualifier (quadratic in the run: one try took 15 s on 4,800 characters of the SI reading; security round 2).
_TOTAL_LINK = r"\s++(?:about|around|roughly)?\s*+"


def _tfig(i: int) -> str:
    """A figure of a stated total: an optional currency sign, the number, a unit and one noun ('3.2 billion dollars', '$2.7 billion')."""
    return (rf"(?P<c{i}>{_CUR})?\s?(?P<n{i}>{_NUMX})(?:\s*(?P<u{i}>{_SCALE_UNIT}|{_RATE_UNIT}|per cent|percent(?!age)|%|seats|votes)\b)?"
            rf"(?:\s+(?P<w{i}>(?!(?:and|plus|to|in|of|a|an|the|gave|giving|making|made|for|with|or|by|on|at)\b)[a-z]+))?")


_TOTAL_RE = re.compile(rf"{_tfig(1)}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?(?:(?:about|around|roughly|some|nearly)\s+)?{_tfig(2)}[^.;]{{0,60}}?"
                       rf"(?:a total of|totalling|totaling|together|in total|making|giving|totals?)\s+(?:(?:about|around|roughly|some|nearly)\s+)?{_tfig(3)}", re.IGNORECASE)
#: A full stop followed by a lower-case word inside one parser sentence: the arithmetic reading splits there too.
_LOWER_CONTINUATION_RE = re.compile(r"[.?!][\"”’')\]»]*\s+[a-z]")
#: Where one part of a clause ends and the next begins between two pairs.
_SEG_SEP_RE = re.compile(r",\s*(?:and|while|whereas|but|yet)\b|;|\s+and\s+", re.IGNORECASE)
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
#: 'close to', 'near' approach the stated figure from either side: the computed value lies within the approach band on either side
#: of it ('close to doubling' for a ratio of 1.85; repair round 2, I2). Read with the 5 per cent band, the hedge was a false error.
_APPROACH_NEAR = frozenset({"close to", "near"})
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
    figure: "re.Pattern[str]"    # one figure (number ``n9``, unit ``u9``, currency ``c9``): what stands between two links


_GENERAL_PATTERNS = _Patterns(_FROM_TO_RE, _AND_DATED_RE, _LIST_ITEM_RE, _CONT_RE, _SHARE_RE, _TOTAL_RE,
                              re.compile(rf"(?<![\w.,]){_fig(9)}", re.IGNORECASE))


def _build_patterns(numx: str, num: str, unit_words: str, unit: str) -> _Patterns:
    """The six figure patterns from a reading's number, unit-word and unit pieces, composed exactly as the module-level
    (general) patterns are."""
    def fig(i: int, dated: bool = False) -> str:
        return _fig(i, dated=dated, numx=numx, unit_words=unit_words)
    return _Patterns(
        re.compile(rf"\b(?:from|of)\s+{fig(1)}\s+(?:to|and)\s+{fig(2)}", re.IGNORECASE),
        re.compile(rf"(?<![\w.,]){fig(1, True)}{_AND_LINK}(?:(?:had\s+|then\s+)?{_TO_VERB}\s+)?{fig(2, True)}", re.IGNORECASE),
        re.compile(rf"{_ITEM_LEAD}(?:then\s+)?(?:to\s+)?{fig(3, True)}", re.IGNORECASE),
        re.compile(
            rf"(?:\bbefore|\bthen|\band on|\band then|\band later|\blater)\s+(?:(?:climbing|rising|falling|dropping|increasing|decreasing|declining|growing|jumping|soaring|sinking|slumping|recovering|"
            rf"returning|climbed|rose|fell|dropped|increased|decreased|declined|grew|jumped|soared|sank|slumped|recovered|returned)\s+{_CONT_ADVERB})?(?:further\s+|again\s+|back\s+)?to\s+{fig(3)}"
            rf"|(?:\bbefore|\bthen|\band then|\band later|\blater)\s+(?:reaching|reached|hitting|hit|peaking at|peaked at)\s+{fig(4)}", re.IGNORECASE),
        re.compile(rf"\b{num}\s*{_PCT_UNIT}{_SHARE_OF}{num}{unit}{_SHARE_LINK}{num}{unit}", re.IGNORECASE),
        re.compile(rf"{num}{unit}\s+(?:and|plus)\s+(?:[a-z][a-z ]{{0,40}}?\s)?{num}{unit}[^.;]{{0,60}}?(?:a total of|totalling|together|in total|making|giving|totals?)"
                   rf"{_TOTAL_LINK}{num}{unit}", re.IGNORECASE),
        re.compile(rf"(?<![\w.,]){fig(9)}", re.IGNORECASE),
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
#: A fold word that names a quantity ('doubling time', 'halving period'): no fold is stated.
_FOLD_NAME_RE = re.compile(r"[ \t]+(?:times?|periods?)\b(?![ \t]+(?:as|more|over|the|its|their|his|her|that|this|than)\b)", re.IGNORECASE)
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


class FigureTooLarge(ValueError):
    """A figure of more than :data:`MAX_FIGURE_DIGITS` digits: the statement that holds it is reported undecided."""


_TOO_LARGE_REASON = f"a figure in it has more than {MAX_FIGURE_DIGITS:,} digits and is too large to check"


def _number(num: str) -> Fraction:
    """Exact value of a figure written in digits (thousands separators, decimals, a decimal comma, a sign) or in words.
    Raises :class:`FigureTooLarge` for a numeral of more than :data:`MAX_FIGURE_DIGITS` digits."""
    if sum(ch.isdigit() for ch in num) > MAX_FIGURE_DIGITS:
        raise FigureTooLarge(f"figure of {sum(ch.isdigit() for ch in num)} digits")
    s = num.strip().replace("−", "-").lstrip("+")
    if re.fullmatch(r"-?\d{1,3}(?:[ \u00a0\u2009\u202f]\d{3})+(?:\.\d+)?", s):
        s = re.sub(r"[ \u00a0\u2009\u202f]", "", s)  # '45 000': thousands grouped by a space
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
    if q in _APPROACH_NEAR:
        return "near"
    return "lower" if q in _LOWER_ONLY else "upper" if q in _UPPER_ONLY else "both"


_SIDE_TEXT = {
    "lower": " (one-sided: the stated figure is a lower bound)",
    "upper": " (one-sided: the stated figure is an upper bound)",
    "below": (" (approached from below, 'nearly'/'almost'/'just under': the computed value may not exceed the stated figure by more than 1 per cent "
              "of it, or the half-point floor of a per-cent figure, and must be at least 85 per cent of it)"),
    "above": (" (approached from above, 'just over'/'a little over': the computed value may not fall below the stated figure by more than 1 per cent "
              "of it, or the half-point floor of a per-cent figure, and must be at most the stated figure divided by 0.85)"),
    "near": (" (approached from either side, 'close to'/'near': the computed value must be at least 85 per cent of the stated figure and at most "
             "the stated figure divided by 0.85)"),
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
    elif side == "near":
        lo = min(stated * APPROACH_BAND, stated - floor)
        hi = max(stated / APPROACH_BAND, stated + floor)
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


#: A qualifier of a falling fold bounds the size of the fall, so its side on the ratio is the mirror image ('more than
#: halved': the ratio is at most a half; 'nearly halved': the ratio approaches a half from above). Repair round 2.
_MIRRORED_SIDE = {"lower": "upper", "upper": "lower", "below": "above", "above": "below", "near": "near", "both": "both"}
#: Nouns after a fold that make it a fall ('a threefold reduction', 'a fivefold drop').
_FALL_FOLD_NOUNS = frozenset({"fall", "decrease", "decline", "drop", "reduction", "cut", "loss", "contraction", "shrinkage", "falls", "decreases",
                              "declines", "drops", "reductions", "cuts"})
_WORD_BEFORE_RE = re.compile(r"([A-Za-z]+)\s+(?:by\s+)?(?:(?:more than|over|nearly|almost|about|around|roughly|some|at least|less than|up to)\s+)?(?:an?\s+)?$",
                             re.IGNORECASE)
_WORD_AFTER_RE = re.compile(r"\s+(?:in\s+)?([A-Za-z]+)")


def _fold_falls(clause: str, start: int, end: int) -> bool:
    """Whether the fold word at ``start``-``end`` states a fall: a falling verb before it ('fell threefold', 'decreased by
    fivefold', 'dropped nearly tenfold') or a falling noun after it ('a threefold reduction'). Bounded windows."""
    before = _WORD_BEFORE_RE.search(clause[max(0, start - 48):start])
    if before is not None and before.group(1).lower() in _FALL_WORDS:
        return True
    after = _WORD_AFTER_RE.match(clause, end, min(len(clause), end + 24))
    return after is not None and after.group(1).lower() in _FALL_FOLD_NOUNS


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
    return _Fig(m.group(f"n{i}"), m.group(f"u{i}"), (m.group(f"noun{i}") or "").strip(), (m.group(f"d{i}") or "").strip(), m.start(f"n{i}"), m.end(), cur)


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
    negated: bool = False        # the clause negates the derived figure ('it has not doubled', 'this was not a rise of 12 per cent')


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
        if _FOLD_NAME_RE.match(clause, m.end()):
            continue  # 'Doubling time = 70 ÷ growth rate': the name of a quantity, no fold the clause states (repair round 2)
        end, words = m.end(), m.group(0).strip()
        rep = _REPEAT_RE.match(clause, m.end())
        if rep:  # 'halved twice' is a factor of 1/4 in every reading: 'halved' alone would be checked against the wrong factor
            times = 2 if rep.group(1) else (_REPEAT_WORDS.get(rep.group(2).lower()) or int(rep.group(2)))
            if 1 <= times <= _MAX_REPEAT:
                factor, end, words = factor ** times, rep.end(), clause[m.start():rep.end()].strip()
        if factor > 1 and _fold_falls(clause, m.start(2), m.end(2)):
            factor = 1 / factor  # 'fell threefold', 'a fivefold reduction': the later figure is the earlier divided by the fold
        side = _side(m.group(1))
        if factor < 1:
            side = _MIRRORED_SIDE[side]  # 'more than halved': the fall exceeds a halving, so the ratio is at most a half
        out.append(_Derived(m.start(), end, "fold_change", words, None, factor, side))
    if si:  # the SI reading: no multiples, absolute changes or average rates; an approach qualifier is read with the symmetric band
        out = [d if d.side not in ("below", "above", "near") else replace(d, side="both") for d in out]
        out.sort(key=lambda d: d.start)
        return _with_negation(clause, out)
    for m in (_TIMES_RE.finditer(clause) if ("times" in low or "twice" in low or "thrice" in low) else ()):
        if m.group("twice"):
            factor = Fraction(2) if m.group("twice").lower() == "twice" else Fraction(3)
        else:
            raw = m.group("n").lower()
            factor = Fraction(100) if raw in ("a hundred",) else _number(raw)
        if factor <= 1:
            continue
        out.append(_Derived(m.start(), m.end(), "fold_change", m.group(0).strip(), None, factor, _side(m.group("q"))))
    taken: Optional[_GrowingSpans] = None  # the spans of the phrases read so far (security round 2: a scan of every span per match)
    if "averag" in low:
        taken = _GrowingSpans(len(clause), ((d.start, d.end) for d in out))
        for rx in _RATE_RES:
            for m in rx.finditer(clause):
                if taken.meets(m.start(), m.end()) or _year_like(m.group("n"), m.group("u") or m.group("cur")):
                    continue
                amount = _frac(m.group("n"), m.group("u"))
                direction = _direction(m.group(0).split()[0]) if re.search(r"\b(?:fall|decline|drop|loss|cut|reduction)\b", m.group(0), re.IGNORECASE) else None
                out.append(_Derived(m.start(), m.end(), "rate_change", m.group(0).strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                    noun=(m.group("noun") or "").strip(), per=(m.group("per") or "year").lower(), cur=_cur_key(m.group("cur") or "")))
                taken.add(m.start(), m.end())
    if _ABS_HINT_RE.search(clause):
        if taken is None:
            taken = _GrowingSpans(len(clause), ((d.start, d.end) for d in out))
        for rx in _ABS_CHANGE_RES:
            for m in rx.finditer(clause):
                if taken.meets(m.start(), m.end()) or _year_like(m.group("n"), m.group("u") or m.group("cur")):
                    continue
                amount = _frac(m.group("n"), m.group("u"))
                end = m.end()
                rest = clause[end:end + 160]
                if _CALC_CONTINUES_RE.match(rest):
                    # 'an increase of $9.00 − $8.00 = $1.00': the figure is the first operand of the written calculation, and the
                    # change stated is its result (repair round 2: the operand was read as the change, a false counterexample)
                    res = _CALC_RESULT_RE.match(rest)
                    if res is None:
                        continue
                    amount = _frac(res.group("n"), m.group("u"))
                    end += res.end()
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
                    out.append(_Derived(m.start(), end, "abs_change", clause[m.start():end].strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                        noun=(m.group("noun") or "").strip(), soft=soft, cur=_cur_key(m.group("cur") or "")))
                taken.add(m.start(), end)
    out.sort(key=lambda d: d.start)
    return _with_negation(clause, out)


#: A written calculation going on after a stated amount ('an increase of $9.00 − $8.00 = $1.00'), and its result.
_CALC_CONTINUES_RE = re.compile(r"\s*[−\-+×*÷/]\s*[$£€]?\s*\d")
_CALC_RESULT_RE = re.compile(r"[^=≈;\n]{1,120}?[=≈]\s*[$£€]?\s*(?P<n>\d[\d,]*(?:\.\d+)?)")

#: Words that negate the derived figure after them in its clause ('it has not doubled', 'this was never a rise of 12 per cent',
#: 'prices didn't rise by 10 per cent', 'there was no fall of 5 per cent'); 'not only', 'not just', 'not merely', 'not simply'
#: affirm it ('not only doubled but ...'). At most four words may stand between the marker and the figure (repair round 2, I2).
_NEGATION_BEFORE_RE = re.compile(
    r"\b(?:not|never|no|nor|neither|cannot|[a-z]+n't|[a-z]+n’t)\b(?!\s+(?:only|just|merely|simply|least)\b)((?:\s+[A-Za-z’'-]+){0,4})\s*$",
    re.IGNORECASE)
#: A clause break between the negation and the figure ends its reach ('it did not fall, and then it doubled').
_NEGATION_BREAK_RE = re.compile(r"[,;:]|\b(?:and|but|then|while|whereas|so|because|which|that)\b", re.IGNORECASE)


def _with_negation(clause: str, out: list[_Derived]) -> list[_Derived]:
    """``out`` with each derived figure that its clause negates marked ``negated`` (:data:`_NEGATION_BEFORE_RE`)."""
    marked: list[_Derived] = []
    for d in out:
        m = _NEGATION_BEFORE_RE.search(clause[max(0, d.start - 60):d.start])
        if m is not None and not _NEGATION_BREAK_RE.search(m.group(1) or ""):
            d = replace(d, negated=True)
        marked.append(d)
    return marked


#: an arithmetic operator and a figure right after the second figure of a pair: the pair ends in an expression
#: ('from $1.60 to $2.00 − $0.60 = $1.40'); a hyphen glued between figures ('1923-24') is a range, not a minus
_EXPR_AFTER_RE = re.compile(r"(?:\s+[−\-+×÷/*]\s+|\s*[×÷*+]\s*)(?:US\$|[$£€])?\s?\d")
#: the value such an expression is said to equal: up to five operator-and-figure steps, then '=' and the figure
_EXPR_VALUE_RE = re.compile(r"(?:\s*[−\-+×÷/*]\s*(?:US\$|[$£€])?\s?[\d][\d,]{0,14}(?:\.\d{1,12})?){1,5}\s*=\s*(?P<c>US\$|[$£€])?\s?(?P<n>\d[\d,]{0,14}(?:\.\d{1,12})?)")


def _pairs(clause: str, pat: _Patterns = _GENERAL_PATTERNS) -> list[_Pair]:
    """Every pair of figures of ``clause`` (from/to with its list and continuations, then 'X in D1 and Y in D2'), in order.
    ``pat`` holds the reading's figure patterns (the general reading's by default)."""
    pairs: list[_Pair] = []
    covered: list[tuple[int, int]] = []
    if not _FIGURE_HINT_RE.search(clause):
        return pairs

    spans: Optional[_GrowingSpans] = None   # ``covered`` and the pairs' ends, each one structure (security round 2: scanned per match)
    ends: Optional[_GrowingSpans] = None
    first_with_end: dict[int, _Pair] = {}

    def index_pairs() -> None:
        nonlocal spans, ends
        if spans is None:
            spans, ends = _GrowingSpans(len(clause), covered), _GrowingSpans(len(clause))
            for q in pairs:
                ends.add(q.end, q.end)
                first_with_end.setdefault(q.end, q)

    def overlaps(s: int, e: int) -> bool:
        index_pairs()
        return spans.meets(s, e)

    def append(q: _Pair) -> None:
        pairs.append(q)
        covered.append((q.start, q.end))
        if spans is not None:
            spans.add(q.start, q.end)
            ends.add(q.end, q.end)
            first_with_end.setdefault(q.end, q)

    for m in pat.from_to.finditer(clause):
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        if _EXPR_AFTER_RE.match(clause, m.end()):
            # 'falls from $1.60 to $2.00 − $0.60 = $1.40': the end of the pair is an expression, so its figure is the value the
            # expression is said to equal; an expression with no stated value ends no pair (never read as its first term)
            res = _EXPR_VALUE_RE.match(clause, m.end())
            if res is None:
                covered.append((m.start(), m.end()))
                continue
            after = p.after
            p = _Pair(m.start(), res.end(), p.before, _Fig(res.group("n"), after.unit, after.noun, after.date, res.start("n"), res.end(),
                                                          _cur_key(res.group("c") or "") or after.cur))
            pairs.append(p)
            covered.append((p.start, p.end))
            continue
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        if not p.tail and not p.after.date and p.before.annual:
            pos = _undated_list(clause, p, pos)
        p.end = pos
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in pat.cont.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        last_end = ends.furthest(m.start())   # the pair that ends last at or before the continuation (the first such in order)
        if last_end < 0:
            continue
        base = first_with_end[last_end]
        if _unread_figure_between(clause, base.end, m.start(), pat, _fig_of(m, 3 if m.group("n3") else 4)):
            # a figure the reader did not read stands between the pair and the continuation: the continuation starts from it,
            # not from the pair's last figure, so no pair is read (undecided, never a wrong pair; repair round 4, ADV4-12)
            continue
        p = _Pair(m.start(), m.end(), base.last, _fig_of(m, 3 if m.group("n3") else 4))
        pos = m.end()
        while True:
            li = pat.list_item.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        append(p)
    for m in pat.and_dated.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        append(p)
    pairs.sort(key=lambda p: p.start)
    return pairs


#: A figure in digits (a continuation is never chained across one the reader left unread), and a year, which states no level.
_DIGIT_RUN_RE = re.compile(r"\d")
_YEAR_RUN_RE = re.compile(r"1\d{3}|20\d{2}|21\d{2}")


def _unread_figure_between(clause: str, start: int, end: int, pat: "_Patterns", cont: _Fig) -> bool:
    """Whether ``clause[start:end]`` holds a figure the pairs leave unread that the continuation ``cont`` could start from:
    a figure written in digits with the continuation figure's own unit and currency (an unread level of the same
    quantity: "peaking at 11.4% in 2020, before falling to 8.1%"), which is no year and stands inside no derived figure the
    clause states. A stated change of the link before (``a rise of 63 per cent``, read by the derived reader) and a figure
    of another unit ("with 230 seats" before "falling to 33.1 per cent") move no level of the chain, so "from 1.9 million in
    1929 to 3.1 million in 1930, a rise of 63 per cent, before climbing to 5.6 million in 1932" chains 3.1 to 5.6."""
    index = _clause_index(clause)   # the clause's digits, figures and derived figures read once (security round 2)
    digits = index.digit_positions
    i = bisect.bisect_left(digits, start)
    if i == len(digits) or digits[i] >= end or start >= end:
        return False
    kind = (_level_unit(cont.unit), cont.cur)
    scan = index.scan(pat.figure, start)
    k, tail = scan.upto(end)
    state = index._get(("unread-kinds", pat.figure, start), lambda: [0, {}])   # [matches read, the first index of each kind]
    while state[0] < k:
        key = _unread_kind(index, scan.full[state[0]])
        if key is not None:
            state[1].setdefault(key, state[0])
        state[0] += 1
    if state[1].get(kind, k) < k:
        return True
    return any(_unread_kind(index, f) == kind for f in tail)


def _unread_kind(index: "_ClauseIndex", f: "re.Match[str]") -> Optional[tuple]:
    """The level and currency of a figure :func:`_unread_figure_between` may start a continuation from, or None for a figure it
    passes over (no digits, a year, or the amount of a derived figure)."""
    num = f.group("n9") or ""
    if not _DIGIT_RUN_RE.search(num) or _YEAR_RUN_RE.fullmatch(num):
        return None
    if index.derived_stab(False).covers(f.start("n9")):
        return None
    return (_level_unit(f.group("u9")), _cur_key(f.group("c9") or ""))


def _level_unit(unit: Optional[str]) -> str:
    """A figure's unit for telling whether it is a level of a continuation's quantity: "%", "per cent" and "percent" are
    one unit; no unit is ''."""
    u = " ".join((unit or "").lower().split())
    return "%" if u in ("%", "per cent", "percent") else u


#: The next item of a list whose items carry no date of their own (', 655', ' and 720 mm in 2023').
_UNDATED_ITEM_RE = re.compile(rf"{_ITEM_LEAD}{_fig(3)}", re.IGNORECASE)  # the lead read once (security round 1, _ITEM_LEAD)


def _undated_list(clause: str, p: _Pair, pos: int) -> int:
    """'from 610 mm in 2019 to 640, 655, 690 and 720 mm in 2023': a from/to pair whose second figure opens a list of undated
    figures that ends in a dated one. When the list holds exactly one figure per year from the first figure's year to the last
    one's, the figures are the consecutive years' values and become the pair's dated list (repair round 2,
    FA-ALLDATA-GEO-SERIES); otherwise nothing is read (the pair keeps its second figure, as before). Returns where the pair ends."""
    items: list[_Fig] = []
    end = pos
    cur = pos
    while len(items) < _MAX_SERIES:
        li = _UNDATED_ITEM_RE.match(clause, cur)
        if not li:
            break
        f = _fig_of(li, 3)
        items.append(f)
        cur = li.end()
        if f.date:
            break
    if not items or not items[-1].annual or any(f.date for f in items[:-1]):
        return end
    y1, y2 = p.before.year, items[-1].year
    values = [p.after, *items]
    if y1 is None or y2 is None or y2 - y1 + 1 != 1 + len(values):
        return end
    dated = [replace(f, date=f"in {y1 + 1 + k}") if not f.date else f for k, f in enumerate(values)]
    p.after = dated[0]
    p.tail = dated[1:]
    return cur


def _pairs_outside(pairs: list[_Pair], derived: list[_Derived]) -> list[_Pair]:
    """Pairs whose first figure is not the amount of a derived phrase ('a rise of 20 per cent in 1930 and 30 per cent in 1931' is no pair)."""
    stab = _Stab((d.start, d.end) for d in derived)  # one bisection per pair (security round 2)
    return [p for p in pairs if not stab.covers(p.before.start)]


def _same_noun(a: str, b: str) -> bool:
    wa, wb = a.lower().split(), b.lower().split()
    return bool(wa and wb) and wa[-1].rstrip("s") == wb[-1].rstrip("s")


def _same_noun_phrase(a: str, b: str) -> bool:
    """Whether two figures name the same noun phrase, word for word (plurals aside): "tonnes" and "tonnes", never "rupees"
    and "lakh rupees", where an unknown word stands before the noun."""
    wa, wb = a.lower().split(), b.lower().split()
    return bool(wa) and len(wa) == len(wb) and all(x.rstrip("s") == y.rstrip("s") for x, y in zip(wa, wb))


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
            if noun1 and noun2 and _same_noun_phrase(noun1, noun2):
                # 'from 2.5 million tonnes to 1 800 000 tonnes': the scale word multiplies its own figure, and the second figure,
                # of the same noun with no scale word, is a whole value (repair round 4, rerun-parser-safety-13)
                return u1, None, True
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
        if k1 == "scale" and not (before.noun and after.noun and _same_noun_phrase(before.noun, after.noun)):
            return None, cannot
        if k1 != "scale":
            u2, k2 = u1, k1  # the first unit carries over; a scale word multiplies only its own figure (as in :func:`_comparable`)
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
    phrase: str = ""          # the derived phrase or relation the check reads ('added roughly 4,500 miles'), for naming its claim
    rule: str = ""            # the rule the check applies, when it is not the kind's default (a duration with a qualifier or day dates)


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
    """The check of derived figure ``d`` against the pair ``values``, or None and why it cannot be built
    (:func:`_plain_pair_spec`). A negated derived figure ('it has not doubled') is checked as negated: the computed value
    must lie outside the band the figure would set (repair round 2, I2: read as stated, the negation was a false error)."""
    spec, why = _plain_pair_spec(values, d, statement, tolerance, note, basis, si=si)
    if spec is None or not d.negated:
        return spec, why
    return _negated_spec(spec, tolerance), why


def _negated_spec(spec: _Spec, tolerance: Fraction) -> _Spec:
    name, expr, label = spec.conclusion
    return replace(spec, conclusion=(name, {"op": "not", "arg": expr}, f"negated: {label} (the statement says it does not hold)"),
                   rule="negated statement: the computed value must lie outside the band of the stated figure; the band: " + _rule_text(tolerance, spec.floor, spec.side))


def _plain_pair_spec(values: _Values, d: _Derived, statement: str, tolerance: Fraction, note: str = "figure stated in the report itself", basis: str = "",
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
    if d.kind in ("percent_change", "change"):
        direction = d.direction or ("rise" if b >= a else "fall")
        change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(base)}]}
        if direction == "fall":
            change = {"op": "neg", "arg": change}
        how = "the stated sign's direction" if d.direction else "the figures' own direction"
        label = f"stated {direction} of {_fmt(d.stated)} per cent against the computed change" if d.kind == "percent_change" else f"stated change of {_fmt(d.stated)} per cent ({direction}, {how}) against the computed change"
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


@lru_cache(maxsize=1024)
def _content_words_of(text: str) -> frozenset:
    """:func:`_content_words`, read once per text."""
    return frozenset(_content_words(text))


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


def _pick_series(series: list[_Series], years: list[int], clause: str, *, kinds: Optional[set] = None, extra: Optional[list] = None,
                 cache: Optional[dict] = None) -> tuple[Optional[_Series], str]:
    """The one series of the paragraph that states every year in ``years``; several are told apart by shared words with ``clause``.
    When no single series states them all, series of the same measure stated in different sentences (a common content word, no
    disagreement on a shared year) are read as one."""
    candidates = [s for s in series if all(y in s.points for y in years) and (kinds is None or s.kind in kinds)]
    candidates = _merge(candidates)
    if not candidates:
        key = ("merged-related", frozenset(kinds) if kinds is not None else None, extra is not None)
        merged = cache.get(key) if cache is not None else None
        if merged is None:   # the paragraph's pool, merged once for every question (security round 2); the result is only read
            merged = _merge_related([s for s in [*series, *(extra or [])] if kinds is None or s.kind in kinds])
            if cache is not None:
                cache[key] = merged
        candidates = [s for s in merged if all(y in s.points for y in years)]
    if not candidates:
        return None, "the paragraph states no dated series with figures for " + " and ".join(str(y) for y in years)
    if len(candidates) > 1:
        words = _clause_index(clause).content_words
        scored = [s for s in candidates if words & _content_words_of(s.text)]
        if len(scored) == 1:
            return scored[0], ""
        return None, f"{len(candidates)} dated series of the paragraph state figures for " + " and ".join(str(y) for y in years) + "; which one the statement relies on is not stated"
    return candidates[0], ""


def _earlier_year(sentences: list[str], index: int, clause: str, phrase_start: int, memo: Optional[dict] = None) -> tuple[Optional[int], str]:
    """The year an anaphor ('that year') refers to, and why when there is none: the one year stated
    before it in its own clause, else the one year stated in the nearest earlier sentence of the
    paragraph that states any. Two or more candidate years at the nearest level are ambiguous. ``memo`` (one per paragraph)
    keeps the answer of the sentences before each sentence (security round 2: it was read again for every derived figure)."""
    if 0 <= phrase_start <= len(clause):
        count, only = _cut_years(_clause_index(clause), phrase_start)
        if count == 1:
            return only, ""
        if count:
            return None, f"'that year' could refer to {count} years stated before it in its sentence"
    else:
        years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(clause[:phrase_start])})
        if len(years) == 1:
            return years[0], ""
        if years:
            return None, f"'that year' could refer to {len(years)} years stated before it in its sentence"
    return _year_before(sentences, index, memo if memo is not None else {})


def _year_before(sentences: list[str], index: int, memo: dict) -> tuple[Optional[int], str]:
    """The answer of :func:`_earlier_year` from the sentences before ``sentences[index]``: the nearest one that states a year."""
    key = ("year-before", index)
    if key in memo:
        return memo[key]
    todo = []
    j = index
    while j > 0 and ("year-before", j) not in memo:
        todo.append(j)
        j -= 1
    answer = memo.get(("year-before", j), (None, "'that year' refers to no year stated earlier in the paragraph"))
    for j in reversed(todo):
        years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(sentences[j - 1])})
        if len(years) == 1:
            answer = (years[0], "")
        elif years:
            answer = (None, f"'that year' could refer to {len(years)} years ({', '.join(map(str, years[:6]))}) stated in the sentence before it")
        memo[("year-before", j)] = answer
    return memo.get(key, answer)


def _decade_before(clause: str, at: int) -> Optional["re.Match[str]"]:
    """The decade token ('the 1840s') that governs a phrase at ``at``: the last one before it in its clause, when every year the
    clause states between the decade and the phrase falls inside that decade ('The 1840s, which included the Railway Mania of 1845
    to 1847, added ...') and no 'from'/'between' span stands between them; otherwise None."""
    if not 0 <= at <= len(clause):
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
    # the clause's decades, spans and years read once, the text up to ``at`` read again only near ``at`` (security round 2)
    index = _clause_index(clause)
    _count, d, _first = _decade_cut(index, at)
    if d is None:
        return None
    d0 = int(d.group("d"))
    if _first_span_cut(index, d.end(), at) is not None:
        return None
    if _years_outside(index, d.end(), at, d0):
        return None
    return d


def _outside_decade(before: _Fig, after: _Fig, d0: int) -> bool:
    """True when a pair's dated figures cannot be about the decade starting ``d0`` (a year before it or after its end)."""
    return before.year is not None and after.year is not None and (before.year < d0 or after.year > d0 + 10)


def _target_years(sentences: list[str], index: int, clause: str, at: int, series_years: list[int],
                  memo: Optional[dict] = None) -> tuple[Optional[tuple[int, int]], str]:
    """(earlier year, later year) a derived figure with no pair of its own speaks of: a decade that is the clause's subject ('The
    1840s ... added roughly 4,500 miles': 1840 to 1850), a span in the clause ('from 1929 to 1930'), an anaphor ('that year') or the
    one year the clause states, read against the series' previous dated figure."""
    decade = _decade_before(clause, at)
    if decade is not None:
        d0 = int(decade.group("d"))
        return (d0, d0 + 10), f"'{decade.group(0).strip()}' read as {d0} to {d0 + 10}"
    ci = _clause_index(clause)
    span = ci.year_span
    if span:
        return (int(span.group(1)), int(span.group(2))), f"the years {span.group(1)} and {span.group(2)} stated in the sentence"
    # the figure's own part of the clause and what comes before it: a later clause's years ('..., with a sharp dip in 2020') say
    # nothing of the period the figure speaks of (repair round 2: a 50% growth over the whole period was read from 2012 to 2020).
    # Read as the text 'clause[:at] + " " + own' would be read, from what the clause keeps (security round 2: the text was built
    # and read again for every derived figure).
    if 0 <= at <= len(clause):
        a, z = ci.own_bounds(at, at)
        lead_years = _LeadYears(ci, at, a, z)
        period = _lead_period(ci, at, a, z) if len(series_years) >= 2 and not lead_years.count else None
    else:
        lead = clause[:max(at, 0)] + " " + clause
        lead_years = _LeadYears.of_text(lead)
        period = _PERIOD_ANAPHOR_RE.search(lead) if len(series_years) >= 2 and not lead_years.count else None
    if period:
        first, last = min(series_years), max(series_years)
        length = _number_of_years(period.group("n"), period.group("unit"))
        if length is not None and length != last - first:
            return None, f"'{period.group(0)}' names {length} years, but the paragraph's dated figures run from {first} to {last}"
        return (first, last), f"'{period.group(0)}' read as the paragraph's dated span, {first} to {last}"
    anaphor = ci.that_year
    if anaphor:
        key = ("earlier-year", index, clause, anaphor.start())
        if memo is not None and key in memo:
            year, why = memo[key]
        else:
            year, why = _earlier_year(sentences, index, clause, anaphor.start(), memo)
            if memo is not None:
                memo[key] = (year, why)
        if year is None:
            return None, why
        how = f"'{anaphor.group(0)}' read as {year}, the one year stated before it"
    else:
        if lead_years.count != 1:
            return None, ("the sentence states no year and no anaphor such as 'that year'" if not lead_years.count else f"the sentence states {lead_years.count} years and no span between them")
        year, how = lead_years.only, f"the year {lead_years.only} stated in the sentence"
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


#: The scale words of the general reading by the factor each multiplies its own figure by.
_SCI_SCALE_WORDS = {"thousand": 10 ** 3, "k": 10 ** 3, "million": 10 ** 6, "m": 10 ** 6, "mn": 10 ** 6, "billion": 10 ** 9, "bn": 10 ** 9,
                    "trillion": 10 ** 12, "tn": 10 ** 12, "trn": 10 ** 12, "quadrillion": 10 ** 15}
#: a figure of a pair written in scientific notation, as the SI patterns read one (the general patterns never read it)
_SCI_FIGURE_RE = re.compile(rf"\s*(?:{si_digits_pattern()})\s*")
_SCI_HINT_RE = re.compile(r"\d[eE][-+]?\d|×\s?10|[xX*·]\s?10(?:\^|\*\*|[⁰¹²³⁴⁵⁶⁷⁸⁹⁻])")


_SPACE_GROUPED_RE = re.compile(r"-?\d{1,3}(?:[ \u00a0\u2009\u202f]\d{3})+(?:\.\d+)?")


def _sci_pair_number(num: str) -> Optional[Fraction]:
    """A figure of a pair beside scientific notation: as the STEM number reader reads it, and a figure grouped in thousands
    by a space ("45 000") as the same digits ungrouped (repair round 4, rerun-parser-safety-13: '3.0 × 10⁴ tonnes to 45 000
    tonnes' left the pair unread)."""
    v = si_number(num)
    if v is None and _SPACE_GROUPED_RE.fullmatch(num.strip()):
        v = si_number(re.sub(r"[ \u00a0\u2009\u202f]", "", num.strip()))
    return v


def _sci_direction_pairs(clause: str, pairs: list[_Pair]) -> list[tuple[_Pair, str, Optional[_Values], str]]:
    """The from/to pairs of ``clause`` whose figures the general reading leaves unread because one of them is written in
    scientific notation ('Debt rose from 3.2e4 to 7.5e3'), with the direction word that governs each, the two figures as exact
    values (the STEM number reader, :func:`si_number`), or None and the reason. Bounded: one pass of the SI patterns over a
    clause that holds scientific notation at all."""
    if not _SCI_HINT_RE.search(clause):
        return []
    out: list[tuple[_Pair, str, Optional[_Values], str]] = []
    taken = _Stab((g.start, g.end) for g in pairs)  # one bisection per pair (security round 2)
    for m in _si_patterns().from_to.finditer(clause):
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        if not (_SCI_FIGURE_RE.fullmatch(p.before.num) or _SCI_FIGURE_RE.fullmatch(p.after.num)):
            continue
        if taken.meets(p.start, p.end):
            continue
        own = _PAIR_DIR_BEFORE_RE.search(clause[max(0, p.start - 80):p.start])
        if own is None:
            continue
        word = own.group(1).lower()
        a, b = _sci_pair_number(p.before.num), _sci_pair_number(p.after.num)
        if a is None or b is None:
            out.append((p, word, None, "a figure of the pair is written in scientific notation outside the reader's bounds, so the direction is not checked"))
            continue
        # a scale word multiplies its own figure only ('2.5 million' is 2 500 000), so a figure in scientific notation is
        # compared with the other figure's whole value, never with its mantissa (repair round 4, rerun-parser-safety-13: '2.5
        # million to 1.8 × 10⁶' compared 2.5 with 1 800 000)
        sa, sb = _SCI_SCALE_WORDS.get((p.before.unit or "").lower()), _SCI_SCALE_WORDS.get((p.after.unit or "").lower())
        if sa is not None or sb is not None:
            a, b = a * (sa or 1), b * (sb or 1)
            ua = None if sa is not None else p.before.unit
            ub = None if sb is not None else p.after.unit
            if ua and ub and ua != ub:
                out.append((p, word, None, f"the units of '{p.before.num} {p.before.unit}' and '{p.after.num} {p.after.unit}' cannot be compared"))
                continue
            out.append((p, word, _Values(a, b, " ".join(x for x in (p.before.num, p.before.unit) if x), " ".join(x for x in (p.after.num, p.after.unit) if x),
                                        False, unit=ua or ub), ""))
            continue
        if (p.before.unit or "") != (p.after.unit or "") and p.before.unit and p.after.unit:
            out.append((p, word, None, f"the units of '{p.before.num} {p.before.unit}' and '{p.after.num} {p.after.unit}' cannot be compared"))
            continue
        unit = p.after.unit or p.before.unit
        out.append((p, word, _Values(a, b, " ".join(x for x in (p.before.num, unit) if x), " ".join(x for x in (p.after.num, unit) if x), False,
                                    unit=unit), ""))
    return out


def _direction_spec(values: _Values, word: str, statement: str) -> _Spec:
    rising = word.lower() in _RISE_DIR_WORDS
    premises = (("BEFORE", {"op": "eq", "left": _v("before"), "right": _real(values.a)}, f"before = {values.shown_a}"),
                ("AFTER", {"op": "eq", "left": _v("after"), "right": _real(values.b)}, f"after = {values.shown_b}"))
    concl = {"op": "gt" if rising else "lt", "left": _v("after"), "right": _v("before")}
    label = f"stated '{word}' from {values.shown_a} to {values.shown_b}: the later figure {'above' if rising else 'below'} the earlier"
    return _Spec("pair_direction", statement, (("before", "the earlier figure as stated"), ("after", "the later figure as stated")), premises,
                 ("STATED_DIRECTION", concl, label), Fraction(0), "both", phrase=word)


def _subject_words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", text.lower())} - {"the", "and", "from", "rising", "rose", "falling", "fell", "official", "figures", "show", "between"}


def _comparison_spec(cm: "re.Match[str]", clause: str, si: int, sentence_pairs: dict, pairs: list, tolerance: Fraction,
                     before: Optional["_LastBefore"] = None) -> tuple[Optional[_Spec], str]:
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
    # the clause up to the comparison read from what the clause keeps (security round 2: it was copied and read for every comparison)
    subject: Optional[tuple[_Fig, Optional[str], str]] = None   # (figure, unit after elision, where it was read)
    p = (before or _LastBefore(pairs)).last(cm.start())
    if p is not None:
        u1, u2, _ok = _comparable(p.before.unit, p.last.unit, p.before.noun, p.last.noun)
        subject = (p.last, u2, "the later figure of the pair before it in its clause")
    else:
        lone = _figure_run(clause, cm.start(), "lone")
        if lone:
            f = lone[-1]
            subject = (f, f.unit, "the figure before it in its clause")
    if subject is None and _ANAPHOR_SUBJECT_RE.match(clause, 0, cm.start()) and not _FIGURE_HINT_RE.search(clause, 0, cm.start()):
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


#: A figure labelled by its year ('2019: 610', '2020 - 640'), and a figure a clause dates by a year before it ('in 2000 the
#: population was 30 million'): points of the paragraph's dated series read as standalone figures (repair round 1, re-run
#: review A-FA-QNT).
_LABELLED_FIG_RE = re.compile(rf"(?<![\w.,])(?P<y>1[0-9]{{3}}|20[0-9]{{2}})\s*[:–-]\s*{_fig(1)}", re.IGNORECASE)
_YEAR_LEAD_FIG_RE = re.compile(rf"\b(?:in|by|during)\s+(?P<y>1[0-9]{{3}}|20[0-9]{{2}})\b,?\s+(?:[a-z'’]+\s+){{0,5}}?"
                               rf"(?:was|were|stood\s+at|reached|totalled|totaled|numbered|had|came\s+to)\s+{_fig(1)}", re.IGNORECASE)


def _standalone_points(sentences: list[str]) -> list[_Series]:
    """Every figure of the paragraph dated by a year alone and standing outside a pair, as one-point series (read by the
    comparison with every other decade, which needs the figure at each decade's end, and, merged by a common measure, as the
    paragraph's dated series when it states no pair): a figure dated after it ('about 13,000 miles by 1870'), labelled by
    its year ('2019: 610') or dated by a year that opens its clause ('in 2000 the population was 30 million')."""
    out: list[_Series] = []
    for si, sent in enumerate(sentences):
        if not _FIGURE_HINT_RE.search(sent):
            continue
        covered = _Stab((p.start, p.end) for p in _pairs(sent))  # one bisection per figure (security round 2)
        for m in _DATED_FIG_RE.finditer(sent):
            if covered.covers(m.start()):
                continue
            f = _fig_of(m, 1)
            if not f.annual or _year_like(f.num, f.unit):
                continue
            out.append(_Series(_unit_kind(f.unit), f.unit, {f.year: (_frac(f.num, f.unit), _shown(f, f.unit))}, si, sent))
        for rx in (_LABELLED_FIG_RE, _YEAR_LEAD_FIG_RE):
            for m in rx.finditer(sent):
                if covered.covers(m.start()):
                    continue
                f = _fig_of(m, 1)
                f = _Fig(f.num, f.unit, f.noun, f"in {m.group('y')}", f.start, f.end, f.cur)
                if _year_like(f.num, f.unit) or not f.annual:
                    continue
                out.append(_Series(_unit_kind(f.unit), f.unit, {f.year: (_frac(f.num, f.unit), _shown(f, f.unit))}, si, sent))
    return out


def _standalone_series(points: list[_Series]) -> list[_Series]:
    """Standalone points of one kind that agree on every shared year, as series of two or more years."""
    merged: list[_Series] = []
    for s in points:
        for m in merged:
            if m.kind == s.kind and all(m.points[y][0] == s.points[y][0] for y in m.points.keys() & s.points.keys()):
                m.points = {**s.points, **m.points}
                m.text = m.text if s.text in m.text else m.text + " " + s.text
                break
        else:
            merged.append(_Series(s.kind, s.unit, dict(s.points), s.sentence, s.text))
    return [s for s in merged if len(s.points) >= 2]


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
_ALONE_RE = re.compile(r"\b(?P<who>(?:1[0-9]{3}|20[0-9]{2})|[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*)*)\s+alone\s+(?:had\s+|has\s+)?"
                       r"(?P<verb>brought|saw|accounted\s+for|added|contributed|admitted|received|took|produced|absorbed|got|gained|sent|supplied|provided|delivered|lost|"
                       r"took\s+in|let\s+in)\s+")
#: '<part>, about a quarter of the decade's total', 'about 60 per cent of the total': the share of a total stated in the sentence.
_SHARE_OF_TOTAL_RE = re.compile(
    rf"(?:,\s*|\s+)(?:(?P<q>{_QUAL})\s+)?(?:(?P<frac>{_FRAC})|(?P<pn>\d+(?:\.\d+)?)\s*{_PCT_UNIT})\s+of\s+(?:the|this|that|its|their)\s+"
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
                           r"more\s+than|less\s+than|fewer\s+than|higher\s+than|lower\s+than|larger\s+than|smaller\s+than|greater\s+than|"
                           r"(?:^|;)\s*(?:(?:and|but|so|yet|thus)\s+)?(?:of|out\s+of)\s|\d\s+(?:out\s+)?of\s", re.IGNORECASE)
_MONTH_NOUN_RE = re.compile(r"^(?:january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE)


# ---- security round 2 (SEC-V2): one clause read once ----------------------------------------------------------------------
# The prose reading asks one clause the same questions once for each derived figure, comparison or figure it states (the
# figures it states, its worked equations, its decades and years up to the phrase, the subclause around the phrase), and
# answered each of them by reading the clause, or the clause up to the phrase, again: quadratic in the phrases of one clause
# (2,000 derived figures in one sentence held the reading for minutes). The helpers below read a clause once, keep what they
# read, and answer each question from it, with the answers the readers gave.

_ORDINAL_AFTER_RE = re.compile(r"\s*(?:s\b|-|–|st\b|nd\b|rd\b|th\b)")
_TOKEN_RE = re.compile(r"\S+")
_SEPARATOR_RE = re.compile(r"[,;:]")
_NUMBER_WORDS = frozenset((*_SMALL_WORDS, *_TENS_WORDS, "hundred", "and", ""))
_SCI_TOKEN_CHARS = frozenset("×xX*·^{}-–−+eE⁰¹²³⁴⁵⁶⁷⁸⁹⁻")
_TOKEN_EDGE = ".,;:!?()[]\"'“”‘’"


def _numberish(token: str) -> bool:
    """Whether a run of characters between white space may be part of one figure's number: it holds a digit or a superscript,
    is made of the signs of scientific notation alone ('×', '·', '^'), or is number words, 'hundred' or 'and', alone or joined by
    hyphens ('twenty-five', '-'). A generous test: only its 'no' is relied on (no number reads across a run it rejects)."""
    if any(c.isdigit() for c in token) or all(c in _SCI_TOKEN_CHARS for c in token):
        return True
    word = token.strip(_TOKEN_EDGE).lower()
    return bool(word) and all(part in _NUMBER_WORDS for part in word.split("-"))


class _Stab:
    """Which of a fixed set of spans ``[start, end)`` cover a position or meet a range, each answer one bisection: the spans
    sorted by start with the running furthest end (a scan of every span for every position was quadratic in one clause)."""

    __slots__ = ("_starts", "_reach")

    def __init__(self, spans) -> None:
        spans = sorted(spans)
        self._starts = [a for a, _b in spans]
        reach: list[int] = []
        far = -1
        for _a, b in spans:
            far = b if b > far else far
            reach.append(far)
        self._reach = reach

    def covers(self, x: int) -> bool:
        """``any(a <= x < b for a, b in spans)``."""
        i = bisect.bisect_right(self._starts, x)
        return i > 0 and self._reach[i - 1] > x

    def meets(self, s: int, e: int) -> bool:
        """``any(a < e and s < b for a, b in spans)``."""
        i = bisect.bisect_left(self._starts, e)
        return i > 0 and self._reach[i - 1] > s


class _GrowingSpans:
    """A growing set of spans ``[a, b)`` within a text of ``n`` characters, asked whether any meets ``[s, e)`` (``a < e`` and
    ``s < b``): a Fenwick tree over the starts holding the furthest end, a logarithm per addition and per question."""

    __slots__ = ("_n", "_tree")

    def __init__(self, n: int, spans=()) -> None:
        self._n = n + 1
        self._tree = [-1] * (self._n + 1)
        for a, b in spans:
            self.add(a, b)

    def add(self, a: int, b: int) -> None:
        i = min(max(a, 0), self._n - 1) + 1
        tree = self._tree
        while i <= self._n:
            if tree[i] < b:
                tree[i] = b
            i += i & -i

    def meets(self, s: int, e: int) -> bool:
        return self._reach(e) > s

    def furthest(self, x: int) -> int:
        """The furthest end of the spans that start at ``x`` or before (-1 when none does)."""
        return self._reach(x + 1)

    def _reach(self, e: int) -> int:
        i = min(max(e, 0), self._n)
        far = -1
        tree = self._tree
        while i > 0:
            if tree[i] > far:
                far = tree[i]
            i -= i & -i
        return far


class _LastBefore:
    """For a fixed list of pairs: the last pair of the list that ends at a place or before it, one bisection per place (the
    comparison reader listed every such pair for every comparison)."""

    __slots__ = ("_ends", "_last", "_pairs")

    def __init__(self, pairs: list) -> None:
        order = sorted(range(len(pairs)), key=lambda i: pairs[i].end)
        self._pairs = pairs
        self._ends = [pairs[i].end for i in order]
        last: list[int] = []
        best = -1
        for i in order:
            best = i if i > best else best
            last.append(best)
        self._last = last

    def last(self, x: int):
        """``[p for p in pairs if p.end <= x][-1]``, or None."""
        i = bisect.bisect_right(self._ends, x)
        return self._pairs[self._last[i - 1]] if i else None


class _PrefixScan:
    """``list(pattern.finditer(text, pos, end))`` for many ends, without reading the text from ``pos`` to each end: the scan to
    the text's end, read on demand, holds the same matches as the scan to ``end`` up to a little before ``end``, and only the rest
    is scanned again. ``pattern`` is a figure pattern (:func:`_fig`): an attempt reads at most ten runs of characters between
    white space before its number, the number, and thirty after it, and a number reads across white space only over runs that
    may hold one (:func:`_numberish`). An attempt that starts more than 64 such runs before ``end``, and ten runs before every
    run that may hold a number it reaches, reads nothing near ``end``, so it gives the same answer in both scans; the scan to
    ``end`` is the same up to there."""

    __slots__ = ("_pattern", "_text", "_pos", "_it", "full", "_starts", "_tstarts", "_numberish")

    WINDOW = 64
    BEFORE = 10

    def __init__(self, pattern: "re.Pattern[str]", text: str, pos: int, index: "_ClauseIndex") -> None:
        self._pattern, self._text, self._pos = pattern, text, pos
        self._it = pattern.finditer(text, pos)
        self.full: list = []        # the matches of the scan to the text's end read so far, in order
        self._starts: list[int] = []
        self._tstarts = index.token_starts
        self._numberish = index.token_numberish

    def _read(self, upto: int) -> None:
        """Read the scan to the text's end until a match starts at ``upto`` or later (or the scan ends)."""
        while self._it is not None and (not self._starts or self._starts[-1] < upto):
            m = next(self._it, None)
            if m is None:
                self._it = None
                break
            self.full.append(m)
            self._starts.append(m.start())

    def upto(self, end: int) -> tuple[int, list]:
        """``(k, tail)``: ``list(pattern.finditer(text, pos, end))`` is ``full[:k] + tail`` (``0 <= end <= len(text)``)."""
        j = bisect.bisect_left(self._tstarts, end) - 1
        k = j - self.WINDOW
        if k > 0 and self._tstarts[k] > self._pos:
            numberish = self._numberish
            while k > 0 and numberish[k]:
                k -= 1
            k -= self.BEFORE
            if k > 0 and self._tstarts[k] > self._pos:
                r0 = self._tstarts[k]
                self._read(r0)
                i = bisect.bisect_left(self._starts, r0)
                r = r0
                if i and self.full[i - 1].end() > r0:
                    r = self.full[i - 1].end()
                if r <= end:
                    return i, list(self._pattern.finditer(self._text, r, end))
        return 0, list(self._pattern.finditer(self._text, self._pos, end))


class _ClauseIndex:
    """What the prose reading keeps of one clause (or sentence) between its questions, each part read on first use."""

    def __init__(self, text: str) -> None:
        self.text = text
        self._cache: dict = {}

    def _get(self, key, build):
        v = self._cache.get(key, self)
        if v is self:
            v = self._cache[key] = build()
        return v

    # -- runs of characters between white space
    def _tokens(self):
        starts, flags = [], []
        for m in _TOKEN_RE.finditer(self.text):
            starts.append(m.start())
            flags.append(_numberish(m.group()))
        return starts, flags

    @property
    def token_starts(self) -> list[int]:
        return self._get("tokens", self._tokens)[0]

    @property
    def token_numberish(self) -> list[bool]:
        return self._get("tokens", self._tokens)[1]

    @property
    def stripped(self) -> str:
        return self._get("strip", self.text.strip)

    @property
    def separators(self) -> list[int]:
        """Where a comma, semicolon or colon stands (the edges of :func:`_own_subclause`)."""
        return self._get("seps", lambda: [m.start() for m in _SEPARATOR_RE.finditer(self.text)])

    def own_bounds(self, start: int, end: int) -> tuple[int, int]:
        """The bounds of :func:`_own_subclause` ``(clause, start, end)``."""
        seps = self.separators
        i = bisect.bisect_left(seps, max(start, 0))
        a = seps[i - 1] + 1 if i else 0
        j = bisect.bisect_left(seps, end)
        return a, (seps[j] if j < len(seps) else len(self.text))

    def own_has_year(self, start: int, end: int) -> bool:
        """``_YEAR_TOKEN_RE.search(_own_subclause(clause, start, end)) is not None``."""
        a, z = self.own_bounds(start, end)
        return self._get(("own-year", a, z), lambda: _YEAR_TOKEN_RE.search(self.text[a:z]) is not None)

    def own_lead_years(self, a: int, z: int) -> tuple[int, ...]:
        """The years of ``' ' + clause[a:z]`` (the subclause as it stands after the joining space of :func:`_target_years`)."""
        return self._get(("own-lead-years", a, z), lambda: tuple(int(y) for y in _YEAR_TOKEN_RE.findall(" " + self.text[a:z])))

    def own_lead_period(self, a: int, z: int):
        """``_PERIOD_ANAPHOR_RE.search(' ' + clause[a:z])``."""
        return self._get(("own-lead-period", a, z), lambda: _PERIOD_ANAPHOR_RE.search(" " + self.text[a:z]))

    # -- whole-clause readings
    @property
    def stated_figures(self) -> tuple:
        return self._get("stated", lambda: tuple(_stated_figures(self.text)))

    @property
    def stated_starts(self) -> list[int]:
        return self._get("stated-starts", lambda: [f.start for f in self.stated_figures])

    @property
    def worked(self) -> tuple:
        return self._get("worked", lambda: _worked_equations_of(self.text))

    @property
    def worked_stab(self) -> _Stab:
        return self._get("worked-stab", lambda: _Stab((eq.start, eq.end) for eq in self.worked))

    def derived(self, si: bool) -> tuple:
        return self._get(("derived", si), lambda: tuple(_derived_phrases(self.text, si)))

    def derived_stab(self, si: bool) -> _Stab:
        return self._get(("derived-stab", si), lambda: _Stab((d.start, d.end) for d in self.derived(si)))

    @property
    def year_span(self):
        return self._get("year-span", lambda: _YEAR_SPAN_RE.search(self.text))

    @property
    def that_year(self):
        return self._get("that-year", lambda: _THAT_YEAR_RE.search(self.text))

    @property
    def period(self):
        return self._get("period", lambda: _PERIOD_ANAPHOR_RE.search(self.text))

    @property
    def content_words(self) -> frozenset:
        return self._get("content-words", lambda: frozenset(_content_words(self.text)))

    # -- year tokens, decades and year spans of the whole clause, in order
    def _years(self):
        ms = list(_YEAR_TOKEN_RE.finditer(self.text))
        return [m.start() for m in ms], [m.end() for m in ms], [int(m.group(1)) for m in ms]

    @property
    def years(self):
        return self._get("years", self._years)

    @property
    def year_first_index(self) -> dict:
        """For each year the clause states, the index of its first token."""
        def build():
            out: dict = {}
            for i, y in enumerate(self.years[2]):
                out.setdefault(y, i)
            return out
        return self._get("year-first", build)

    @property
    def year_distinct_prefix(self) -> list[int]:
        """``[len(set(years[:k])) for k in range(len(years) + 1)]``."""
        def build():
            seen: set = set()
            out = [0]
            for y in self.years[2]:
                seen.add(y)
                out.append(len(seen))
            return out
        return self._get("year-distinct", build)

    @property
    def year_minmax(self):
        """A sparse table of the minimum and maximum year over any run of the clause's year tokens."""
        def build():
            ys = self.years[2]
            lo, hi = [list(ys)], [list(ys)]
            step = 1
            while 2 * step <= len(ys):
                plo, phi = lo[-1], hi[-1]
                lo.append([min(plo[i], plo[i + step]) for i in range(len(ys) - 2 * step + 1)])
                hi.append([max(phi[i], phi[i + step]) for i in range(len(ys) - 2 * step + 1)])
                step *= 2
            return lo, hi
        return self._get("year-minmax", build)

    def years_minmax(self, i: int, j: int) -> tuple[int, int]:
        """The least and greatest year of the year tokens ``i`` to ``j - 1`` (``i < j``)."""
        lo, hi = self.year_minmax
        level = (j - i).bit_length() - 1
        step = 1 << level
        return min(lo[level][i], lo[level][j - step]), max(hi[level][i], hi[level][j - step])

    @property
    def decades(self) -> list:
        return self._get("decades", lambda: list(_DECADE_TOKEN_RE.finditer(self.text)))

    @property
    def decade_ends(self) -> list[int]:
        return self._get("decade-ends", lambda: [m.end() for m in self.decades])

    @property
    def spans(self) -> list:
        return self._get("spans", lambda: list(_YEAR_SPAN_RE.finditer(self.text)))

    @property
    def span_starts(self) -> list[int]:
        return self._get("span-starts", lambda: [m.start() for m in self.spans])

    def scan(self, pattern: "re.Pattern[str]", pos: int = 0) -> _PrefixScan:
        return self._get(("scan", pattern, pos), lambda: _PrefixScan(pattern, self.text, pos, self))

    @property
    def digit_positions(self) -> list[int]:
        return self._get("digits", lambda: [m.start() for m in _DIGIT_RUN_RE.finditer(self.text)])


#: The prose reading asks only about the clause it is reading, so the indexes of the last few clauses are enough; each holds
#: about 22 bytes per character of its clause, and a longer list would keep that much of the earlier analyses' texts.
@lru_cache(maxsize=32)
def _clause_index(text: str) -> _ClauseIndex:
    return _ClauseIndex(text)


# -- the readings of a clause up to a position, from the whole clause's ------------------------------------------------------
# A token of a pattern found in the whole clause is found the same way in the clause cut at ``at`` when the attempt that found
# it read nothing at or after ``at - 1``; only the last few characters or runs before ``at`` are read again, in the cut text.

def _last_token_before(index: _ClauseIndex, at: int) -> int:
    """The index of the last run of characters between white space that starts before ``at`` (-1 when none does)."""
    return bisect.bisect_left(index.token_starts, at) - 1


def _years_cut(index: _ClauseIndex, lo: int, at: int, joined: bool) -> tuple[int, list[int]]:
    """The year tokens of ``clause[lo:at]`` (``joined``: of ``clause[lo:at] + ' '``), as ``(k, near)``: the clause's own year
    tokens ``i0`` to ``k - 1`` (``i0`` the first that starts at ``lo`` or after), and ``near``, the years of the cut text's
    tokens that start in its last six characters. A year token reads its four digits, one character before them and two
    after them, so the clause's own tokens that start six or more characters before ``at`` are the cut text's. ``lo`` is a
    place no year token can start at or straddle (the start of the clause, or the end of a decade token)."""
    starts, ends, years = index.years
    k = bisect.bisect_right(starts, at - 6)
    i0 = bisect.bisect_left(starts, lo)
    if k < i0:
        k = i0
    from_ = max(lo, at - 5, ends[k - 1] if k > i0 else lo)
    if from_ >= at:
        return k, []
    w = max(0, from_ - 1)
    view = index.text[w:at] + (" " if joined else "")
    near = [int(m.group(1)) for m in _YEAR_TOKEN_RE.finditer(view, from_ - w) if m.start() + w < at]
    return k, near


def _decade_cut(index: _ClauseIndex, at: int):
    """The last match of ``_DECADE_TOKEN_RE`` in ``clause[:at]``, and how many there are: the clause's own decades that end
    before ``at``, and a decade that ends at ``at`` itself, which only the cut text can read when a word character follows it
    in the clause."""
    text = index.text
    ends = index.decade_ends
    n = bisect.bisect_left(ends, at)
    last = index.decades[n - 1] if n else None
    if at >= 5 and text[at - 1] == "s" and text[at - 5:at - 1].isdigit():
        k = at - 5
        q = k
        while q > 0 and text[q - 1].isspace():
            q -= 1
        start = q - 3 if q < k and q >= 3 and text[q - 3:q] == "the" else k
        lo = max(last.end() if last is not None else 0, start - 1 if start > 0 else 0)
        tail = [m for m in _DECADE_TOKEN_RE.finditer(text, lo, at) if m.end() == at]
        if tail:
            return n + 1, tail[-1], (index.decades[0] if n else tail[-1])
    return n, last, (index.decades[0] if n else None)


def _first_span_cut(index: _ClauseIndex, lo: int, at: int):
    """``_YEAR_SPAN_RE.search(clause[lo:at])`` (``lo``: the start of the clause or the end of a decade token, where no span
    starts or ends): the clause's own first span from ``lo`` when the attempt that found it started at least six runs of
    characters before ``at`` (a span reads five runs and one character more), else a scan of the cut text from there."""
    spans, starts = index.spans, index.span_starts
    i = bisect.bisect_left(starts, lo)
    j = _last_token_before(index, at)
    safe = index.token_starts[j - 5] if j - 5 >= 0 else 0
    if i < len(spans) and spans[i].start() < safe:
        return spans[i]
    return _YEAR_SPAN_RE.search(index.text, max(lo, safe), at)


def _years_outside(index: _ClauseIndex, lo: int, at: int, d0: int) -> bool:
    """``any(not (d0 <= int(y) < d0 + 10) for y in _YEAR_TOKEN_RE.findall(clause[lo:at]))``."""
    starts = index.years[0]
    i0 = bisect.bisect_left(starts, lo)
    k, near = _years_cut(index, lo, at, False)
    if k > i0:
        y_lo, y_hi = index.years_minmax(i0, k)
        if y_lo < d0 or y_hi >= d0 + 10:
            return True
    return any(not (d0 <= y < d0 + 10) for y in near)


def _cut_years(index: _ClauseIndex, at: int) -> tuple[int, Optional[int]]:
    """How many distinct years ``clause[:at]`` states, and the one when it states one."""
    k, near = _years_cut(index, 0, at, False)
    years, first = index.years[2], index.year_first_index
    extra = {y for y in near if not first.get(y, k) < k}
    count = index.year_distinct_prefix[k] + len(extra)
    only = (years[0] if k else next(iter(extra))) if count == 1 else None
    return count, only


class _LeadYears:
    """The distinct years of ``clause[:at] + ' ' + clause[a:z]`` (:func:`_target_years`): how many, and the one when there is one."""

    __slots__ = ("count", "only")

    def __init__(self, index: _ClauseIndex, at: int, a: int, z: int) -> None:
        k, near = _years_cut(index, 0, at, True)
        years = index.years[2]
        first = index.year_first_index
        own = index._get(("own-lead-set", a, z), lambda: frozenset(index.own_lead_years(a, z)))
        own_firsts = index._get(("own-lead-firsts", a, z), lambda: sorted(first[y] for y in own if y in first))
        count = index.year_distinct_prefix[k] + len(own) - bisect.bisect_left(own_firsts, k)
        extra = {y for y in near if not (first.get(y, k) < k or y in own)}
        count += len(extra)
        self.count = count
        self.only: Optional[int] = None
        if count == 1:
            self.only = years[0] if k else (next(iter(own)) if own else next(iter(extra)))

    @classmethod
    def of_text(cls, text: str) -> "_LeadYears":
        """The distinct years of ``text``, read directly."""
        out = cls.__new__(cls)
        years = sorted({int(y) for y in _YEAR_TOKEN_RE.findall(text)})
        out.count = len(years)
        out.only = years[0] if len(years) == 1 else None
        return out


def _lead_period(index: _ClauseIndex, at: int, a: int, z: int):
    """``_PERIOD_ANAPHOR_RE.search(clause[:at] + ' ' + clause[a:z])`` as far as :func:`_target_years` reads it (its words and
    groups). A match reads at most four runs of characters and one character more, so the clause's own first match is the
    joined text's when it starts at least four runs before ``at``; a match that starts nearer ``at`` is read in the last five
    runs before it, the joining space and the subclause's first five runs; else it is the subclause's own first match after the
    space."""
    text = index.text
    j = _last_token_before(index, at)
    safe = index.token_starts[j - 4] if j - 4 >= 0 else 0
    first = index.period
    if first is not None and first.start() < safe:
        return first
    own_starts = index._get(("own-tokens", a, z), lambda: [m.end() for m in _TOKEN_RE.finditer(text, a, z)])
    head_end = own_starts[4] if len(own_starts) > 4 else z
    lo = max(0, safe - 1)
    view = text[lo:at] + " " + text[a:head_end]
    for m in _PERIOD_ANAPHOR_RE.finditer(view, safe - lo):
        if m.start() + lo < at:
            return m
        break
    return index.own_lead_period(a, z)


# -- the figures of a clause up to a place --------------------------------------------------------------------------------------

class _FigureRun:
    """The figures :func:`_magnitudes` or :func:`_amounts` list for a clause up to a place, as a sequence (its length, its items
    and its ends are read without listing it again: the first ``n`` of ``stable`` are the clause's own, then ``tail``)."""

    __slots__ = ("_stable", "_n", "_tail")

    def __init__(self, stable: list, n: int, tail: list) -> None:
        self._stable, self._n, self._tail = stable, n, tail

    def __len__(self) -> int:
        return self._n + len(self._tail)

    def __bool__(self) -> bool:
        return self._n > 0 or bool(self._tail)

    def __getitem__(self, i):
        size = self._n + len(self._tail)
        if isinstance(i, slice):
            return [self[j] for j in range(*i.indices(size))]
        if i < 0:
            i += size
        if not 0 <= i < size:
            raise IndexError(i)
        return self._stable[i] if i < self._n else self._tail[i - self._n]

    def __iter__(self):
        yield from itertools.islice(self._stable, self._n)
        yield from self._tail


def _figure_ok(kind: str, index: _ClauseIndex, m: "re.Match[str]", f: "_Fig", end: Optional[int]) -> bool:
    """Whether a figure of :data:`_LONE_FIG_RE` is one :func:`_magnitudes` keeps (``kind`` 'magnitude'), one :func:`_amounts` keeps
    ('amount'), or the figure a comparison is read from ('lone'); ``end`` is where the text was cut (None: the whole clause)."""
    if kind == "lone":
        return m.group("n1")[:1].isdigit() and not _year_like(m.group("n1"), m.group("u1"))
    if not f.num[:1].isdigit() or _is_pct(f.unit) or _year_like(f.num, f.unit or f.cur) or _MONTH_NOUN_RE.match(f.noun):
        return False
    after = _ORDINAL_AFTER_RE.match(index.text, m.end("n1")) if end is None else _ORDINAL_AFTER_RE.match(index.text, m.end("n1"), end)
    if after and _year_like(f.num, None):
        return False
    if kind == "amount":
        return not index.derived_stab(False).covers(f.start) and not _RATE_PHRASE_RE.search(index.text, f.start, f.end)
    return True


def _figure_run(clause: str, end: int, kind: str) -> _FigureRun:
    """The figures of ``clause[:end]`` that :func:`_figure_ok` keeps for ``kind``, in order (``_magnitudes(clause[:end])`` for
    'magnitude', ``_amounts(clause, end)`` for 'amount', the comparison's figures for 'lone')."""
    cut = len(clause) if end >= len(clause) else (end if end >= 0 else max(0, len(clause) + end))
    index = _clause_index(clause)
    scan = index.scan(_LONE_FIG_RE, 0)
    k, tail = scan.upto(cut)
    state = index._get(("passing", kind), lambda: [0, [], []])   # [matches read, their indices, their figures] of the whole clause
    full = scan.full
    while state[0] < k:
        m = full[state[0]]
        f = _fig_of(m, 1)
        if _figure_ok(kind, index, m, f, None):
            state[1].append(state[0])
            state[2].append(f)
        state[0] += 1
    n = bisect.bisect_left(state[1], k)
    return _FigureRun(state[2], n, [f for m in tail for f in (_fig_of(m, 1),) if _figure_ok(kind, index, m, f, cut)])


def _magnitudes(text: str) -> list[_Fig]:
    """The figures of ``text`` that state an amount: digits (or a currency sign), not a year, not a per cent, not the day of a date."""
    out: list[_Fig] = []
    for m in _LONE_FIG_RE.finditer(text):
        f = _fig_of(m, 1)
        if not f.num[:1].isdigit() or _is_pct(f.unit) or _year_like(f.num, f.unit or f.cur) or _MONTH_NOUN_RE.match(f.noun):
            continue
        if _ORDINAL_AFTER_RE.match(text, m.end("n1")) and _year_like(f.num, None):
            continue
        out.append(f)
    return out


def _amounts(clause: str, end: int) -> list[_Fig]:
    """The figures of ``clause[:end]`` that can be a total or a part: :func:`_magnitudes`, less the amount of a derived phrase ('an average
    of about 900,000 a year', 'an increase of 6,500 miles') and a figure stated as a rate ('500,000 a year'), which are no stock of the thing
    counted. The figures of the clause up to ``end`` read once for every ``end`` (:func:`_figure_run`, security round 2)."""
    return _figure_run(clause, end, "amount")


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
        if _ORDINAL_AFTER_RE.match(text, m.end("n1")) and _year_like(f.num, None):
            continue
        out.append(f)
    return out


def _own_subclause(clause: str, start: int, end: int) -> str:
    """The part of ``clause`` around ``[start, end)`` up to the nearest comma, semicolon or colon on each side."""
    if 0 <= end <= len(clause):
        a, z = _clause_index(clause).own_bounds(start, end)  # the clause's separators read once (security round 2)
        return clause[a:z]
    a = max(clause.rfind(c, 0, max(start, 0)) for c in ",;:") + 1
    ends = [k for k in (clause.find(c, end) for c in ",;:") if k >= 0]
    return clause[a:min(ends) if ends else len(clause)]


def _no_pair_reason(clause: str, d: Optional[_Derived]) -> str:
    """Why a derived figure or relation has no figures of its own to be read against: its sentence states no figures at all, or states
    figures that are not a pair it binds to (a total, a lone figure, a per cent), which the reason names."""
    index = _clause_index(clause)  # the clause's figures and worked equations read once (security round 2)
    stated, starts = index.stated_figures, index.stated_starts
    lo, hi = (bisect.bisect_left(starts, d.start), bisect.bisect_left(starts, d.end)) if d is not None else (0, 0)
    figs = [*stated[:lo][:3], *stated[hi:hi + 3]][:3]   # the first three figures outside the phrase (they are in order)
    if not figs:
        return "no figures are stated with it in its sentence"
    working = index.worked
    if working:  # 'Result: the krona appreciated by 20.00%' under lines of working: its figures are in the working, not in a pair of words
        return (f"its sentence states its figures only as written arithmetic ('{working[0].phrase[:100]}'), which this reader does not decide, "
                f"and no pair of figures in words it can be read against")
    shown = [_shown(f, f.unit).replace(" %", "%") for f in figs[:3]]
    return f"its sentence states no pair of figures it can be read against (only {', '.join(shown)})"


#: An arithmetic operator between two figures of written working ('+', '−', '×', '÷', '/', '*', '^', '·', or a spaced hyphen or dash), up to
#: two unit words between the first figure and the operator ('105 million litres ×', '2.4 Ω +'); a figure with a letter attached ('6t') is a term
#: of algebra, not a figure, and the end of a range label ('aged 15–64 × 100') is no operand.
_OPERATOR_BETWEEN_RE = re.compile(r"(?<![\d.,])(?<!\d[–-])\d[\d,.]*[ \t]?%?(?:[ \t][A-Za-zΩµμ°³²⁻¹]{1,12}\.?){0,2}[ \t]?\){0,3}[ \t]?(?:[+×÷*/^·]|[ \t][-–][ \t]|−)[ \t]?\({0,3}[ \t]?(?:US)?[$£€¥]?[ \t]?[-−]?[ \t]?\({0,3}(?:US)?[$£€¥]?\d[\d,.]*(?![\d,.A-Za-zα-ω])")
#: The result of a link of a worked equation: a figure (a sign or a currency sign before it allowed).
_RESULT_START_RE = re.compile(r"^[ \t]?\$?[ \t]?[-\u2212]?[ \t]?(?:US)?[$£€¥]?[ \t]?[-\u2212]?\d")
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
    #: the further links of the same chain after the stated result ('= 95.0' after '(4.3 + 0.3) ÷ 5.0 × 100 = 92.0'): each is a figure or
    #: arithmetic, so a checker of the equation must read them too (repair round 2, I1); empty when the chain ends at the result
    tail: str = ""

    @property
    def chain(self) -> str:
        """The equation's arithmetic with the further links of its chain ('(4.3 + 0.3) ÷ 5.0 × 100 = 92.0 = 95.0')."""
        return f"{self.phrase} {self.tail}" if self.tail else self.phrase


#: Where a line of working holds several statements: a semicolon, or a full stop before a capital or a figure ('Table 1. 4,200 × 12 = ...').
_WORKING_SEGMENT_RE = re.compile(r";\s*|(?<=[.!?])\s+(?=[A-Z0-9(])")
#: Where the stated result of a link ends: a comma or full stop before a space, or an opening bracket ('$192.00 million per year (no tax, ...').
_RESULT_END_RE = re.compile(r",\s|\.\s|\s\(|;|[”\"’]")
#: Where the words before the arithmetic of a link end ('Check: $31.50 million + ...', 'Answer: 2,000').
_LINK_LEAD_END_RE = re.compile(r".*(?::\s|\.\s)")


def worked_equations(text: str) -> list[WorkedEquation]:
    """Every worked equation of ``text``: a statement of a line (with the lines after it that open with '=' or '≈'; a line's statements are
    cut at semicolons and full stops) whose '=' links put an arithmetic operator between two figures before a link whose value is a figure
    with no further arithmetic ('$6,000 ÷ $2.00 = 3,000 loaves', '(12 − 8) − 0 = 4', '= 31 ÷ 69 × 100 = 44.9'). A formula with no figures
    on both sides of an operator ('Dependency ratio = (aged 0–14 + aged 65 and over) ÷ aged 15–64'), an expression of algebra ('a = 6 − 6t')
    and a stated value ('PED = −0.67') are not worked equations. Read once per text and kept (:func:`_worked_equations_of`)."""
    return list(_worked_equations_of(text))


@lru_cache(maxsize=32)
def _worked_equations_of(text: str) -> tuple[WorkedEquation, ...]:
    """The worked equations of ``text`` (:func:`worked_equations`), read once: the prose reading asked for a clause's equations once
    for each of its derived figures (security round 2)."""
    return tuple(_read_worked_equations(text))


def _read_worked_equations(text: str) -> list[WorkedEquation]:
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
            segment = " ".join(line[a:b].split())  # one space between words: every pattern below reads at most one blank in a row
            bounds = [-1] + [m.start() for m in re.finditer(r"[=≈]", segment)] + [len(segment)]
            links = [segment[x + 1: y] for x, y in zip(bounds, bounds[1:])]
            if len(links) < 2:
                continue
            first = None  # the first link that puts an operator between two figures, found in one pass (linear in the links)
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
                stop = _RESULT_END_RE.search(links[k])
                p_end = bounds[k] + 1 + (stop.start() if stop else len(links[k]))
                t_end = p_end
                for j in (range(k + 1, len(links)) if stop is None else ()):
                    # the chain goes on after its first result ('= 92.0 = 95.0', '= 92.0 ≈ 95', '= 92.0 = 0.95 × 100'): every further
                    # link that is a figure or arithmetic is part of the equation a checker must read
                    if not (_RESULT_START_RE.match(links[j]) or _OPERATOR_BETWEEN_RE.search(links[j]) or links[j].lstrip()[:1] in "(−-"):
                        break
                    stop_j = _RESULT_END_RE.search(links[j])
                    t_end = bounds[j] + 1 + (stop_j.start() if stop_j else len(links[j]))
                    if stop_j is not None:
                        break
                tail = segment[p_end:t_end].strip().rstrip(" .,;:") if t_end > p_end else ""
                out.append(WorkedEquation(start, end, shown_line, segment, segment[p_start:p_end].strip().rstrip(" .,;:"), tail))
                break
    return out


_RATE_PHRASE_RE = re.compile(r"\b(?:a|an|per|each|every)\s+(?:year|annum|month|week|day|head|capita)\b|\bannually\b", re.IGNORECASE)


#: The stated result at the end of a worked equation's chain ('= 12.5%', '= −11.1 per cent').
_WORKED_RESULT_RE = re.compile(r"[=≈]\s*([-−]?\s*\d[\d,]*(?:\.\d+)?)\s*(%|per\s*cent|percent)?\s*[.,;:)]?\s*$", re.IGNORECASE)


def _restated_result_spec(previous: str, d: _Derived, statement: str, tolerance: Fraction, note: str) -> Optional[_Spec]:
    """The check of a per-cent change that restates the result of the one worked equation of the sentence before it, or None.
    The equation must end in a per-cent result; the stated change is checked against its magnitude within the tolerance
    rule, and a negative result is no rise (a positive one may be a rise, or a fall computed as a positive share of the
    earlier figure, so its direction is the stated one). Nothing is computed here: the equation's own arithmetic is the chain
    checker's (B25) or named by CORE-QNT-001."""
    if d.kind not in ("percent_change", "change") or d.negated or not previous:
        return None
    eqs = _worked_equations_of(previous)
    if len(eqs) != 1:
        return None
    m = _WORKED_RESULT_RE.search(eqs[0].chain)
    if m is None or not m.group(2):
        return None
    try:
        result = Fraction(m.group(1).replace("−", "-").replace(" ", "").replace(",", ""))
    except (ValueError, ZeroDivisionError):
        return None
    if result < 0 and d.direction == "rise":
        return None  # a negative result restated as a rise: left undecided, named by CORE-QNT-001
    premises = (("RESULT", {"op": "eq", "left": _v("result"), "right": _real(abs(result))}, f"the worked equation's result = {abs(result)} per cent"),)
    label = f"stated {d.direction or 'change'} of {_fmt(d.stated)} per cent against the result of the worked equation of the sentence before it"
    return _Spec("percent_change", statement, (("result", "the per-cent result of the worked equation as stated"),), premises,
                 ("STATED_CHANGE", _within(_v("result"), d.stated, tolerance, POINT_FLOOR, d.side), label), POINT_FLOOR, d.side, note,
                 f"stated across sentences: the result of the worked equation '{eqs[0].chain[:120]}'", d.words)


def _total_rate_spec(clause: str, d: _Derived, tolerance: Fraction) -> tuple[Optional[_Spec], str]:
    """'About 5.2 million people entered the United States in the 1880s, an average of about 900,000 a year': a yearly rate stated after the
    one total its clause dates by a decade (ten years) or a span ('from 1881 to 1890': nine or ten years, either count accepted) is that
    total over those years (a decade dates the decade's total, never an annual point). ``(None, '')`` when the clause states no such
    total; ``(None, reason)`` when the rate and the total cannot be compared."""
    if d.kind != "rate_change" or d.per not in ("year", "annum"):
        return None, ""
    # the clause up to the rate, read from what the clause keeps (security round 2: it was read again for every rate)
    if len(_figure_run(clause, d.start, "magnitude")) != 1:
        return None, ""
    figs = _amounts(clause, d.start)
    if len(figs) != 1:
        return None, ""  # the one figure before it is itself a rate ('500,000 a year in the 1880s') or a derived amount, not a total
    total = figs[0]
    index = _clause_index(clause)
    n_decades, _last, first_decade = _decade_cut(index, d.start)
    span = _first_span_cut(index, 0, d.start)
    if n_decades == 1 and span is None and not _years_outside(index, 0, d.start, int(first_decade.group("d"))):
        counts, over = (10,), f"'{first_decade.group(0).strip()}' (ten years)"
    elif span is not None and not n_decades and int(span.group(2)) > int(span.group(1)):
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
    spec = _Spec("rate_change", clause.strip(), (("total", "the total as stated"),), premises, ("STATED_RATE", concl, label), Fraction(0), d.side,
                 "figure stated in the report itself", f"a yearly average of the total its clause dates by {over}", d.words)
    return (_negated_spec(spec, tolerance) if d.negated else spec), ""


#: The party whose share a phrase states: '..., so the United Kingdom alone received about two-thirds of the total'.
_SHARE_PARTY_RE = re.compile(r"(?P<who>(?:the\s+)?[A-Z][\w'’.-]*(?:\s+(?:of\s+)?[A-Z][\w'’.-]*)*)\s+(?:alone\s+|itself\s+)?(?:had\s+|has\s+)?"
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
        if tp is not None and not lead_parts and not _OF_WHICH_RE.search(clause) and not _TOTAL_RE.search(clause):
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
                          and not re.match(r"\s*(?:January|February|March|April|May|June|July|August|September|October|November|December)\b", clause[f.start + len(f.num):])]
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
    all_clauses: list[str] = []
    clause_where: list[tuple[int, int, str]] = []   # (paragraph, sentence number, sentence) of every clause, for SI undecided shares
    for pi, para, sentences, numbers in _paragraph_sentences(text, reading):
        stripped: dict[int, str] = {}

        def stripped_sentence(i: int, _sentences=sentences, _stripped=stripped) -> str:
            s = _stripped.get(i)
            if s is None:
                s = _stripped[i] = _sentences[i].strip()
            return s
        memo: dict = {}   # the paragraph's readings kept between its derived figures (security round 2)
        series: list[_Series] = []
        pending: list[tuple[int, str, list[_Derived], Optional[tuple]]] = []   # (sentence index, clause, unbound derived, extras)
        per_sentence_specs: list[tuple[int, _Spec]] = []
        sentence_pairs: dict[int, list[tuple[_Pair, str, str]]] = {}   # sentence index -> (pair, clause, the pair's subject words)
        for si, sent in enumerate(sentences):
            clauses = split_clauses(sent) if (";" in sent or _LOWER_CONTINUATION_RE.search(sent)) else [sent]
            all_clauses.extend(clauses)
            sent_s = stripped_sentence(si)
            if si_mode:
                clause_where.extend((pi, _num(numbers, si), sent_s) for _c in clauses)
            try:
                part_specs, part_undecided = _part_specs(sent, para, si, pi, tolerance) if not si_mode else ([], [])
                if not si_mode and _RATE_TREND_RE.search(sent):
                    trend_specs, trend_undecided = _rate_trend_specs(sentences, si, pi)
                    part_specs, part_undecided = part_specs + trend_specs, part_undecided + trend_undecided
                if not si_mode and "year" in sent.lower() and _DUR_PHRASE_RE.search(sent):
                    dur_specs, dur_undecided = _duration_specs(sentences, si, pi, tolerance)
                    part_specs, part_undecided = part_specs + dur_specs, part_undecided + dur_undecided
            except FigureTooLarge:
                part_specs, part_undecided = [], [QuantUndecided(pi, _num(numbers, si), sent_s, sent_s[:120], _TOO_LARGE_REASON)]
            per_sentence_specs.extend((si, sp) for sp in part_specs)
            undecided.extend(part_undecided)
            # a worked equation ('$6,000 ÷ $2.00 = 3,000 loaves') is written arithmetic this reader does not decide: named, never silent
            for eq in (worked_equations(sent) if not si_mode else ()):  # the SI reading: the STEM pack decides the maths
                undecided.append(QuantUndecided(pi, si + 1, sent_s, eq.chain[:160], WORKED_EQUATION_REASON))
            for clause in clauses:
                try:
                    derived = _derived_phrases(clause, si_mode)
                    dstarts = [d.start for d in derived]   # derived figures are in order: a segment's are one run of them (security round 2)
                    cstrip = _clause_index(clause).stripped
                    pairs = _pairs_outside(_pairs(clause, pat), derived)
                    prev_end = 0
                    for p in pairs:
                        s = _si_series_of(p, si, clause, reading.profile) if si_mode else _series_of(p, si, clause)
                        if s is not None:
                            series.append(s)
                        sentence_pairs.setdefault(si, []).append((p, clause, clause[prev_end: p.start]))
                        prev_end = p.end
                    bound: set[int] = set()
                    segments = _segments(clause, pairs)
                    for p, (seg_start, seg_end) in zip(pairs, segments):
                        mine = derived[bisect.bisect_left(dstarts, seg_start):bisect.bisect_left(dstarts, seg_end)]
                        if not mine:
                            continue
                        statement = cstrip if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                        for d in mine:
                            after = p.last if p.tail and d.start >= p.end else p.after
                            decade = _decade_before(clause, d.start)
                            if decade is not None and _outside_decade(p.before, after, int(decade.group("d"))):
                                continue  # 'so the 1850s added about 7,000 miles' after a pair of 1860 and 1870: read through the decade, not the pair
                            bound.add(id(d))
                            values, why = _si_values(p.before, after, reading.profile, d.kind) if si_mode else _values(p.before, after)
                            if values is None:
                                if why != "year span":
                                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent_s, d.words, why))
                                else:
                                    pending.append((si, clause, [d], None))
                                continue
                            spec, why = _pair_spec(values, d, statement, tolerance, si=si_mode)
                            if spec is None:
                                undecided.append(QuantUndecided(pi, _num(numbers, si), sent_s, d.words, why))
                            else:
                                per_sentence_specs.append((si, spec))
                    # a pair governed by a direction word and no stated change ('pig iron rising from X to Y'): the direction is checked
                    prev_dir: Optional[str] = None
                    prev_end = 0
                    for p, (seg_start, seg_end) in (zip(pairs, segments) if not si_mode else ()):  # the SI reading reads no direction word
                        head = clause[prev_end: p.start]
                        inner = clause[p.start: p.after.start]   # 'before climbing to' for a continuation; 'from X to' for a from/to pair
                        prev_end = p.end
                        if bisect.bisect_left(dstarts, seg_start) < bisect.bisect_left(dstarts, seg_end):
                            prev_dir = None
                            continue  # a stated change already decides the pair's direction
                        # the direction word must govern the pair: right before its 'from' (adverbs aside), or inside a continuation
                        own = _PAIR_DIR_BEFORE_RE.search(head) if inner[:4].lower() == "from" else _PAIR_DIR_RE.search(inner)
                        word = own.group(1).lower() if own else (prev_dir if _elliptical(clause[max(0, p.start - 40): p.start]) else None)
                        prev_dir = word
                        if not word:
                            continue
                        if not re.search(r"\bto\b", clause[p.before.start: p.after.start], re.IGNORECASE):
                            continue  # 'from 2.6 per cent and twelve seats': two figures of one date, not a change from one to the other
                        values, why = _values(p.before, p.last)
                        if values is None:
                            continue  # a year span, or units that cannot be compared (a misread pair): no direction is stated between them
                        statement = cstrip if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                        per_sentence_specs.append((si, _direction_spec(values, word, statement)))
                    # a pair written in scientific notation ('rose from 3.2e4 to 7.5e3'), which the general patterns never read: its
                    # figures read exactly (the STEM number reader), its direction word as above; a pair that cannot be read is named
                    for p, word, values, why in (_sci_direction_pairs(clause, pairs) if not si_mode else ()):
                        if values is None:
                            undecided.append(QuantUndecided(pi, _num(numbers, si), sent_s, clause[p.start:p.end].strip()[:120], why))
                            continue
                        per_sentence_specs.append((si, _direction_spec(values, word, cstrip)))
                    before: Optional[_LastBefore] = None
                    for cm in (_COMPARE_RE.finditer(clause) if not si_mode and _COMPARE_HINT_RE.search(clause) else ()):
                        before = before or _LastBefore(pairs)
                        spec, why = _comparison_spec(cm, clause, si, sentence_pairs, pairs, tolerance, before)
                        if spec is not None:
                            per_sentence_specs.append((si, spec))
                        elif why:
                            undecided.append(QuantUndecided(pi, si + 1, sent_s, " ".join(cm.group(0).split())[:120], why))
                    loose = [d for d in derived if id(d) not in bound]
                    low = clause.lower()
                    extras = (_MONOTONIC_RE.search(clause) if "year" in low else None,
                              _EXTREME_RE.search(clause) if _EXTREME_HINT_RE.search(low) else None,
                              _ANY_OTHER_RE.search(clause) if "any other" in low and not si_mode else None)
                    if loose or extras[0] or (extras[1] and not pairs) or extras[2]:
                        pending.append((si, clause, loose, extras))
                except FigureTooLarge:
                    undecided.append(QuantUndecided(pi, _num(numbers, si), sent_s, clause.strip()[:120], _TOO_LARGE_REASON))
        specs.extend(spec for _si, spec in per_sentence_specs)
        standalone_cache: list = []

        def standalone(_sentences=sentences, _cache=standalone_cache) -> list:
            if not _cache:
                _cache.append(_standalone_points(_sentences))
            return _cache[0]
        def paragraph_years(_series=series, _memo=memo, _standalone=standalone) -> list[int]:
            """The years of the paragraph's dated series (else of its standalone points), read once."""
            if "series-years" not in _memo:
                years = sorted({y for s in _series for y in s.points})
                if not years and not si_mode:
                    years = sorted({y for s in _standalone_series(_standalone()) for y in s.points})
                _memo["series-years"] = years
            return _memo["series-years"]

        def pick(target: tuple, clause: str, kinds: Optional[set], extra: bool, _series=series, _memo=memo, _standalone=standalone):
            """``_pick_series`` for the paragraph, kept per question."""
            key = ("pick", target, clause, frozenset(kinds) if kinds is not None else None, extra)
            if key not in _memo:
                _memo[key] = _pick_series(_series, list(target), clause, kinds=kinds, extra=_standalone() if extra else None, cache=_memo)
            return _memo[key]
        for si, clause, loose, extras in pending:
            try:
                sent = stripped_sentence(si)
                cstrip = _clause_index(clause).stripped
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
                    series_years = paragraph_years()
                    target, how = _target_years(sentences, si, clause, d.start, series_years, memo)
                    in_equation = not si_mode and _clause_index(clause).worked_stab.covers(d.start)
                    if target is None and not si_mode and not _clause_index(clause).own_has_year(d.start, d.end):
                        # the derived figure's own part of the clause (to the commas around it) names no year: a later clause of
                        # the sentence may name others ('That is a fall of 157 mm, about 19% of the 1990 total'; repair round 2)
                        prev = sentence_pairs.get(si - 1, [])
                        if len(prev) == 1:
                            # 'Revenue rose from £80,000 to £90,000. That is a rise of 12.5%.': a derived figure with no figures and no
                            # year of its own reads the one pair of the sentence right before it (repair round 1, re-run review A-FA-QNT)
                            pp = prev[0][0]
                            values, why_prev = _values(pp.before, pp.last)
                            if values is not None:
                                spec, why = _pair_spec(values, d, cstrip, tolerance, note,
                                                       f"stated across sentences: the one pair of the sentence before it ('{_shown(pp.before, pp.before.unit)}' to "
                                                       f"'{_shown(pp.last, pp.last.unit)}')")
                                if spec is not None:
                                    specs.append(spec)
                                    continue
                        if not prev or len(prev) != 1:
                            # 'The percentage change is (54 − 48) ÷ 48 × 100 = 12.5%. The price therefore rose by 12.5%.': a derived
                            # figure that restates the result of the worked equation of the sentence before it is checked against that
                            # result (the equation itself is the chain checker's); repair round 2, FA-ARITH-ECON-CROSS-SENTENCE
                            spec = _restated_result_spec(sentences[si - 1] if si > 0 else "", d, cstrip, tolerance, note)
                            if spec is not None:
                                specs.append(spec)
                                continue
                    if target is None:
                        if d.soft and not series and _decade_before(clause, d.start) is None:
                            continue  # 'the army lost 22,000 men': a count, with no stated figures it could be a change of
                        if in_equation:
                            continue  # '(9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease': the worked equation is named with its true reason
                        undecided.append(QuantUndecided(pi, _num(numbers, si), sent, d.words,
                                                        f"{_no_pair_reason(clause, d) if not si_mode else 'no figures are stated with it in its sentence'} and {how}"))
                        continue
                    kinds = {"pct"} if d.kind == "points_change" and d.percentage_points else None
                    s, why = pick(tuple(target), clause, kinds, not si_mode)
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
                    spec, why = _pair_spec(values, d, cstrip, tolerance, note,
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
                    # only a year that opens the trend ('from 1990', 'since 2015', 'after 2001') anchors it; the years of the
                    # series the clause itself states are its points (re-run review A-FA-QNT: 'were 610 in 2019 and 720 in 2023,
                    # and they rose every year' read its own 2023 as the anchor)
                    anchor_years = [int(m.group(1)) for m in _ANCHOR_YEAR_RE.finditer(clause[: mono.start()])]
                    anchor = max(anchor_years) if anchor_years else None
                    if "merged-series" not in memo:
                        memo["merged-series"] = _merge(series)
                    pool = memo["merged-series"] or ([] if si_mode else _standalone_series(standalone()))
                    in_range = [s for s in pool if len([y for y in s.points if anchor is None or y >= anchor]) >= 2]
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
                        specs.append(_Spec("series_monotonic", cstrip, symbols, premises, ("STATED_TREND", concl, label), Fraction(0), "both", note,
                                           f"stated across sentences: figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, years)}"))
                if extreme and not _pairs_outside(_pairs(clause, pat), _derived_phrases(clause, si_mode)):
                    proportional = bool(extreme.group(2) and extreme.group(2).strip().lower() in ("proportional", "relative", "percentage")) or bool(_PCT_CHANGE_RE.search(clause))
                    if extreme.group(2) and extreme.group(2).strip().lower() == "absolute":
                        proportional = False
                    target, how = _target_years(sentences, si, clause, extreme.start(), sorted({y for s in series for y in s.points}), memo)
                    s, why = (None, how) if target is None else pick(tuple(target), clause, None, False)
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
                    specs.append(_Spec("series_extreme", cstrip, symbols, premises, ("STATED_EXTREME", concl, label), Fraction(0), "both", note,
                                       f"stated across sentences: {how}; figures from sentence {_num(numbers, s.sentence)}: {_series_label(s, years)}"))
            except FigureTooLarge:
                undecided.append(QuantUndecided(pi, _num(numbers, si), stripped_sentence(si), clause.strip()[:120], _TOO_LARGE_REASON))
    others: list[tuple[str, tuple]] = []
    if si_mode:
        for k, sent in enumerate(all_clauses):
            for kind, m in (("share", pat.share.search(sent)), ("total", pat.total.search(sent))):
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
    for sent in all_clauses:
        sh = _SHARE_RE.search(sent)
        if sh and not any(sum(ch.isdigit() for ch in (g or "")) > MAX_FIGURE_DIGITS for g in sh.groups()):
            others.append(("share", (sent.strip(), sh.groups())))
        tot = _TOTAL_RE.search(sent)
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
              "duration": "dur", "rate_trend": "trend"}
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
                                 rule=rule, basis=spec.basis, phrase=spec.phrase))
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
