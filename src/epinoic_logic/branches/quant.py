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
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
from typing import Optional

from ..adapters.history_specialist.sentences import split_clauses, split_sentences
from ..ir.schema import Problem

_SMALL_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
                "sixteen", "seventeen", "eighteen", "nineteen")
_TENS_WORDS = ("twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
_WORD_VALUES = {w: i for i, w in enumerate(_SMALL_WORDS, start=1)} | {w: 10 * (i + 2) for i, w in enumerate(_TENS_WORDS)}
_WNUM_TOKEN = "|".join(sorted((*_SMALL_WORDS, *_TENS_WORDS), key=len, reverse=True))  # longest first: 'sixty' before 'six'
#: A number in words below a thousand: 'forty-five', 'two hundred and sixty'. Scale words (thousand, million, ...) are units.
_WNUM = rf"(?:{_WNUM_TOKEN})(?:(?:[\s-]+and)?[\s-]+(?:{_WNUM_TOKEN}|hundred))*(?![a-z])"
#: Digits: thousands groups (with an optional decimal part), a plain decimal, or a decimal comma ('1,9': one or two digits after it).
#: A figure never starts inside another ('1234,567' is not '4,567'; '4.03' is not '03'): besides reading what was written, the
#: guard keeps every pattern linear on a long run of digits, since no match is attempted from each digit of the run.
_DIGITS = r"(?<!\d)(?<!\d[.,])(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?|\d+,\d{1,2})"
#: A currency sign before a figure ('$4.03', '£600 million', 'US$13 billion'): carried with the figure as its unit of account, so a
#: figure in dollars is compared only with a figure in dollars.
_CUR = r"(?:US\$|U\.S\.\s?\$|A\$|C\$|\$|£|€|¥)"
#: The longest numeral read as a figure (far below Python's 4,300-digit integer-string limit): a longer run of digits is refused per
#: statement (``CORE-QNT-001``, 'too large to check'), never converted, so one oversized figure cannot discard the report's other checks.
MAX_FIGURE_DIGITS = 1000
_NUM = rf"({_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"  # never split a thousands group or a decimal
_NUMX = rf"(?:{_DIGITS}|{_WNUM})(?!\d|,\d|\.\d)"
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


def _fig(i: int, *, dated: bool = False) -> str:
    """One figure of a pair, with named groups ``q<i>`` (qualifier), ``c<i>`` (currency sign), ``n<i>`` (number), ``u<i>`` (unit),
    ``noun<i>`` and ``d<i>`` (date)."""
    date = _DATE_BODY if dated else _DATE
    return (rf"(?:(?P<q{i}>{_QUAL})\s+)?(?P<c{i}>{_CUR})?\s?(?P<n{i}>{_NUMX})(?:\s*(?P<u{i}>{_UNIT_WORDS})(?!\w))?(?P<noun{i}>{_NOUN}){_PER}(?P<d{i}>{date})")


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
#: An average rate: 'an average of 450 miles a year', 'averaging 450 miles a year', 'at an average rate of 450 miles per year'.
_RATE_RES = (
    re.compile(rf"\b(?:an?\s+)?(?:annual\s+)?average\s+(?:annual\s+|yearly\s+)?(?:(?:rate|increase|rise|growth|gain|fall|decline|addition)\s+)?(?:of\s+)?{_ABS_AMOUNT}{_RATE_TAIL}", re.IGNORECASE),
    re.compile(rf"\baverag(?:ing|ed|es)\s+{_ABS_AMOUNT}{_RATE_TAIL}", re.IGNORECASE),
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
_SHARE_RE = re.compile(rf"\b{_NUM}\s*{_PCT_UNIT}\s+of\s+(?:the\s+)?(?:about|around|roughly)?\s*{_NUM}{_UNIT}(?:\s+[a-z]+){{0,2}}?(?:\s*,\s*(?:or|i\.e\.|that is)?|\s+(?:or|was|is|=|that is|i\.e\.)|\s*\()\s*(?:about|around|roughly|some)?\s*{_NUM}{_UNIT}", re.IGNORECASE)


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


def _derived_phrases(clause: str) -> list[_Derived]:
    """Every stated derived figure of ``clause``, in order of position."""
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
        out.append(_Derived(m.start(), m.end(), "fold_change", m.group(0).strip(), None, factor, _side(m.group(1))))
    for m in (_TIMES_RE.finditer(clause) if ("times" in low or "twice" in low or "thrice" in low) else ()):
        if m.group("twice"):
            factor = Fraction(2) if m.group("twice").lower() == "twice" else Fraction(3)
        else:
            raw = m.group("n").lower()
            factor = Fraction(100) if raw in ("a hundred",) else _number(raw)
        if factor <= 1:
            continue
        out.append(_Derived(m.start(), m.end(), "fold_change", m.group(0).strip(), None, factor, _side(m.group("q"))))
    taken = [(d.start, d.end) for d in out]
    if "averag" in low:
        for rx in _RATE_RES:
            for m in rx.finditer(clause):
                if any(a < m.end() and m.start() < b for a, b in taken) or _year_like(m.group("n"), m.group("u") or m.group("cur")):
                    continue
                amount = _frac(m.group("n"), m.group("u"))
                direction = _direction(m.group(0).split()[0]) if re.search(r"\b(?:fall|decline|drop|loss|cut|reduction)\b", m.group(0), re.IGNORECASE) else None
                out.append(_Derived(m.start(), m.end(), "rate_change", m.group(0).strip(), direction, amount, _side(m.group("q")), unit=m.group("u"),
                                    noun=(m.group("noun") or "").strip(), per=(m.group("per") or "year").lower(), cur=_cur_key(m.group("cur") or "")))
                taken.append((m.start(), m.end()))
    if _ABS_HINT_RE.search(clause):
        for rx in _ABS_CHANGE_RES:
            for m in rx.finditer(clause):
                if any(a < m.end() and m.start() < b for a, b in taken) or _year_like(m.group("n"), m.group("u") or m.group("cur")):
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
                taken.append((m.start(), m.end()))
    out.sort(key=lambda d: d.start)
    return out


def _pairs(clause: str) -> list[_Pair]:
    """Every pair of figures of ``clause`` (from/to with its list and continuations, then 'X in D1 and Y in D2'), in order."""
    pairs: list[_Pair] = []
    covered: list[tuple[int, int]] = []
    if not _FIGURE_HINT_RE.search(clause):
        return pairs

    def overlaps(s: int, e: int) -> bool:
        return any(s < b and a < e for a, b in covered)

    for m in _FROM_TO_RE.finditer(clause):
        p = _Pair(m.start(), m.end(), _fig_of(m, 1), _fig_of(m, 2))
        pos = m.end()
        while True:
            li = _LIST_ITEM_RE.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in _CONT_RE.finditer(clause):
        if overlaps(m.start(), m.end()):
            continue
        prior = [p for p in pairs if p.end <= m.start()]
        if not prior:
            continue
        p = _Pair(m.start(), m.end(), max(prior, key=lambda x: x.end).last, _fig_of(m, 3 if m.group("n3") else 4))
        pos = m.end()
        while True:
            li = _LIST_ITEM_RE.match(clause, pos)
            if not li or len(p.tail) >= _MAX_SERIES:
                break
            p.tail.append(_fig_of(li, 3))
            pos = li.end()
        p.end = pos
        pairs.append(p)
        covered.append((p.start, p.end))
    for m in _AND_DATED_RE.finditer(clause):
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


def _pair_spec(values: _Values, d: _Derived, statement: str, tolerance: Fraction, note: str = "figure stated in the report itself", basis: str = "") -> tuple[Optional[_Spec], str]:
    """The check of derived figure ``d`` against the pair ``values``, or None and why it cannot be built."""
    a, b = values.a, values.b
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
        change = {"op": "mul", "args": [_real(Fraction(100)), {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(a)}]}
        if direction == "fall":
            change = {"op": "neg", "arg": change}
        how = "the stated sign's direction" if d.direction else "the figures' own direction"
        label = f"stated {direction} of {_fmt(d.stated)} per cent against the computed change" if d.kind == "percent_change" else f"stated change of {_fmt(d.stated)} per cent ({direction}, {how}) against the computed change"
        return _Spec("percent_change", statement, before_after, premises, ("STATED_CHANGE", _within(change, d.stated, tolerance, POINT_FLOOR, d.side), label), POINT_FLOOR, d.side, note, basis, d.words), ""
    if d.kind == "fraction_change":
        change = {"op": "div", "left": {"op": "sub", "left": _v("after"), "right": _v("before")}, "right": _real(a)}
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


def _target_years(sentences: list[str], index: int, clause: str, at: int, series_years: list[int]) -> tuple[Optional[tuple[int, int]], str]:
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


def _magnitudes(text: str) -> list[_Fig]:
    """The figures of ``text`` that state an amount: digits (or a currency sign), not a year, not a per cent, not the day of a date."""
    out: list[_Fig] = []
    for m in _LONE_FIG_RE.finditer(text):
        f = _fig_of(m, 1)
        if not f.num[:1].isdigit() or _is_pct(f.unit) or _year_like(f.num, f.unit or f.cur) or _MONTH_NOUN_RE.match(f.noun):
            continue
        if re.match(r"\s*(?:s\b|-|–|st\b|nd\b|rd\b|th\b)", text[m.end("n1"):]) and _year_like(f.num, None):
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
        if re.match(r"\s*(?:s\b|-|–|st\b|nd\b|rd\b|th\b)", text[m.end("n1"):]) and _year_like(f.num, None):
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
    and a stated value ('PED = −0.67') are not worked equations."""
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
            for k in range(1, len(links)):
                # a result is a figure with no further arithmetic in its link ('3,000 loaves per month', '−4 A1'); '6 − 6t' or
                # '4000(1 + 0.036)^5' is an expression, not a stated result
                if not (_RESULT_START_RE.match(links[k]) and not _OPERATOR_BETWEEN_RE.search(links[k])):
                    continue
                first = next((f for f in range(k) if _OPERATOR_BETWEEN_RE.search(links[f])), None)
                if first is None:
                    continue
                lead = _LINK_LEAD_END_RE.match(links[first])
                p_start = bounds[first] + 1 + (lead.end() if lead else 0)
                stop = _RESULT_END_RE.search(links[k])
                p_end = bounds[k] + 1 + (stop.start() if stop else len(links[k]))
                out.append(WorkedEquation(start, end, shown_line, segment, segment[p_start:p_end].strip().rstrip(" .,;:")))
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
def _analyse(text: str, tolerance: Fraction) -> tuple[tuple[_Spec, ...], tuple[QuantUndecided, ...], tuple[tuple[str, tuple], ...]]:
    """Read every paragraph of ``text``: the pair-bound checks, the cross-sentence checks, the
    statements left undecided, and the share/total matches (built later). Memoised per text,
    since the core pack asks for the checks and for the undecided statements of one report."""
    specs: list[_Spec] = []
    undecided: list[QuantUndecided] = []
    all_clauses: list[str] = []
    for pi, para in enumerate((p for p in _PARA_RE.split(text.strip()) if p.strip()), start=1):
        sentences = split_sentences(para)
        series: list[_Series] = []
        pending: list[tuple[int, str, list[_Derived], Optional[tuple]]] = []   # (sentence index, clause, unbound derived, extras)
        per_sentence_specs: list[tuple[int, _Spec]] = []
        sentence_pairs: dict[int, list[tuple[_Pair, str, str]]] = {}   # sentence index -> (pair, clause, the pair's subject words)
        for si, sent in enumerate(sentences):
            clauses = split_clauses(sent) if (";" in sent or _LOWER_CONTINUATION_RE.search(sent)) else [sent]
            all_clauses.extend(clauses)
            try:
                part_specs, part_undecided = _part_specs(sent, para, si, pi, tolerance)
                if _RATE_TREND_RE.search(sent):
                    trend_specs, trend_undecided = _rate_trend_specs(sentences, si, pi)
                    part_specs, part_undecided = part_specs + trend_specs, part_undecided + trend_undecided
                if "year" in sent.lower() and _DUR_PHRASE_RE.search(sent):
                    dur_specs, dur_undecided = _duration_specs(sentences, si, pi, tolerance)
                    part_specs, part_undecided = part_specs + dur_specs, part_undecided + dur_undecided
            except FigureTooLarge:
                part_specs, part_undecided = [], [QuantUndecided(pi, si + 1, sent.strip(), sent.strip()[:120], _TOO_LARGE_REASON)]
            per_sentence_specs.extend((si, sp) for sp in part_specs)
            undecided.extend(part_undecided)
            # a worked equation ('$6,000 ÷ $2.00 = 3,000 loaves') is written arithmetic this reader does not decide: named, never silent
            for eq in worked_equations(sent):
                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), eq.phrase[:160], WORKED_EQUATION_REASON))
            for clause in clauses:
                try:
                    derived = _derived_phrases(clause)
                    pairs = _pairs_outside(_pairs(clause), derived)
                    prev_end = 0
                    for p in pairs:
                        s = _series_of(p, si, clause)
                        if s is not None:
                            series.append(s)
                        sentence_pairs.setdefault(si, []).append((p, clause, clause[prev_end: p.start]))
                        prev_end = p.end
                    bound: set[int] = set()
                    segments = _segments(clause, pairs)
                    for p, (seg_start, seg_end) in zip(pairs, segments):
                        mine = [d for d in derived if seg_start <= d.start < seg_end]
                        if not mine:
                            continue
                        for d in mine:
                            after = p.last if p.tail and d.start >= p.end else p.after
                            decade = _decade_before(clause, d.start)
                            if decade is not None and _outside_decade(p.before, after, int(decade.group("d"))):
                                continue  # 'so the 1850s added about 7,000 miles' after a pair of 1860 and 1870: read through the decade, not the pair
                            bound.add(id(d))
                            values, why = _values(p.before, after)
                            statement = clause.strip() if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                            if values is None:
                                if why != "year span":
                                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), d.words, why))
                                else:
                                    pending.append((si, clause, [d], None))
                                continue
                            spec, why = _pair_spec(values, d, statement, tolerance)
                            if spec is None:
                                undecided.append(QuantUndecided(pi, si + 1, sent.strip(), d.words, why))
                            else:
                                per_sentence_specs.append((si, spec))
                    # a pair governed by a direction word and no stated change ('pig iron rising from X to Y'): the direction is checked
                    prev_dir: Optional[str] = None
                    prev_end = 0
                    for p, (seg_start, seg_end) in zip(pairs, segments):
                        head = clause[prev_end: p.start]
                        inner = clause[p.start: p.after.start]   # 'before climbing to' for a continuation; 'from X to' for a from/to pair
                        prev_end = p.end
                        if any(seg_start <= d.start < seg_end for d in derived):
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
                        statement = clause.strip() if len(pairs) == 1 else clause[seg_start:seg_end].strip(" ,;")
                        per_sentence_specs.append((si, _direction_spec(values, word, statement)))
                    for cm in (_COMPARE_RE.finditer(clause) if _COMPARE_HINT_RE.search(clause) else ()):
                        spec, why = _comparison_spec(cm, clause, si, sentence_pairs, pairs, tolerance)
                        if spec is not None:
                            per_sentence_specs.append((si, spec))
                        elif why:
                            undecided.append(QuantUndecided(pi, si + 1, sent.strip(), " ".join(cm.group(0).split())[:120], why))
                    loose = [d for d in derived if id(d) not in bound]
                    low = clause.lower()
                    extras = (_MONOTONIC_RE.search(clause) if "year" in low else None,
                              _EXTREME_RE.search(clause) if _EXTREME_HINT_RE.search(low) else None,
                              _ANY_OTHER_RE.search(clause) if "any other" in low else None)
                    if loose or extras[0] or (extras[1] and not pairs) or extras[2]:
                        pending.append((si, clause, loose, extras))
                except FigureTooLarge:
                    undecided.append(QuantUndecided(pi, si + 1, sent.strip(), clause.strip()[:120], _TOO_LARGE_REASON))
        specs.extend(spec for _si, spec in per_sentence_specs)
        standalone_cache: list = []

        def standalone(_sentences=sentences, _cache=standalone_cache) -> list:
            if not _cache:
                _cache.append(_standalone_points(_sentences))
            return _cache[0]
        for si, clause, loose, extras in pending:
            try:
                sent = sentences[si].strip()
                note = "figure stated in the report itself, in another sentence of the paragraph"
                for d in loose:
                    # 'About 5.2 million people entered ... in the 1880s, an average of about 900,000 a year': a rate of the total its clause dates
                    spec, why = _total_rate_spec(clause, d, tolerance)
                    if spec is not None:
                        specs.append(spec)
                        continue
                    if why:
                        undecided.append(QuantUndecided(pi, si + 1, sent, d.words, why))
                        continue
                    target, how = _target_years(sentences, si, clause, d.start, sorted({y for s in series for y in s.points}))
                    in_equation = any(eq.start <= d.start < eq.end for eq in worked_equations(clause))
                    if target is None:
                        if d.soft and not series and _decade_before(clause, d.start) is None:
                            continue  # 'the army lost 22,000 men': a count, with no stated figures it could be a change of
                        if in_equation:
                            continue  # '(9.6 − 3.8) ÷ 9.6 × 100 = 60.4% decrease': the worked equation is named with its true reason
                        undecided.append(QuantUndecided(pi, si + 1, sent, d.words, f"{_no_pair_reason(clause, d)} and {how}"))
                        continue
                    kinds = {"pct"} if d.kind == "points_change" and d.percentage_points else None
                    s, why = _pick_series(series, list(target), clause, kinds=kinds, extra=standalone())
                    if s is None:
                        if in_equation:
                            continue
                        undecided.append(QuantUndecided(pi, si + 1, sent, d.words, f"{_no_pair_reason(clause, d)} and {why}"))
                        continue
                    (va, sa), (vb, sb) = s.points[target[0]], s.points[target[1]]
                    values = _Values(va, vb, sa + f" (stated in sentence {s.sentence + 1} of the paragraph)", sb + f" (stated in sentence {s.sentence + 1} of the paragraph)", s.kind == "pct",
                                     target[0], target[1], s.unit, "")
                    spec, why = _pair_spec(values, d, clause.strip(), tolerance, note, f"stated across sentences: {how}; figures from sentence {s.sentence + 1}: {_series_label(s, list(target))}")
                    if spec is None:
                        undecided.append(QuantUndecided(pi, si + 1, sent, d.words, why))
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
                        undecided.append(QuantUndecided(pi, si + 1, sent, any_other.group(0), reason))
                if mono:
                    rising = mono.group(1) or mono.group(2)
                    rising_dir = _direction(rising)
                    anchor_years = [int(y) for y in _YEAR_TOKEN_RE.findall(clause[: mono.start()])]
                    anchor = max(anchor_years) if anchor_years else None
                    in_range = [s for s in _merge(series) if len([y for y in s.points if anchor is None or y >= anchor]) >= 2]
                    if len(in_range) != 1:
                        why = "the paragraph states no dated series of two or more years" + (f" from {anchor}" if anchor else "") if not in_range else f"{len(in_range)} dated series of the paragraph could be meant"
                        undecided.append(QuantUndecided(pi, si + 1, sent, mono.group(0), why))
                    else:
                        s = in_range[0]
                        years = sorted(y for y in s.points if anchor is None or y >= anchor)[:_MAX_SERIES]
                        symbols = tuple((f"v{y}", f"the figure for {y} as stated") for y in years)
                        premises = tuple((f"Y{y}", {"op": "eq", "left": _v(f"v{y}"), "right": _real(s.points[y][0])}, f"{y}: {s.points[y][1]}") for y in years)
                        op = "gt" if rising_dir == "rise" else "lt"
                        steps = [{"op": op, "left": _v(f"v{b}"), "right": _v(f"v{a}")} for a, b in zip(years, years[1:])]
                        concl = steps[0] if len(steps) == 1 else {"op": "and", "args": steps}
                        label = f"stated '{mono.group(0)}' against the paragraph's dated series (sentence {s.sentence + 1}): every year's figure {'above' if rising_dir == 'rise' else 'below'} the previous one"
                        specs.append(_Spec("series_monotonic", clause.strip(), symbols, premises, ("STATED_TREND", concl, label), Fraction(0), "both", note,
                                           f"stated across sentences: figures from sentence {s.sentence + 1}: {_series_label(s, years)}"))
                if extreme and not _pairs_outside(_pairs(clause), _derived_phrases(clause)):
                    proportional = bool(extreme.group(2) and extreme.group(2).strip().lower() in ("proportional", "relative", "percentage")) or bool(_PCT_CHANGE_RE.search(clause))
                    if extreme.group(2) and extreme.group(2).strip().lower() == "absolute":
                        proportional = False
                    target, how = _target_years(sentences, si, clause, extreme.start(), sorted({y for s in series for y in s.points}))
                    s, why = (None, how) if target is None else _pick_series(series, list(target), clause)
                    if s is None:
                        undecided.append(QuantUndecided(pi, si + 1, sent, extreme.group(0), f"{_no_pair_reason(clause, None)} and {why}"))
                        continue
                    years = sorted(s.points)[:_MAX_SERIES]
                    steps_years = list(zip(years, years[1:]))
                    if target not in steps_years:
                        undecided.append(QuantUndecided(pi, si + 1, sent, extreme.group(0), f"the years {target[0]} and {target[1]} are not consecutive figures of the paragraph's series"))
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
                    label = (f"stated '{extreme.group(0)}' for {target[0]}-{target[1]} ({how}) against every other year-on-year {'proportional' if proportional else 'absolute'} change of the paragraph's series (sentence {s.sentence + 1})")
                    specs.append(_Spec("series_extreme", clause.strip(), symbols, premises, ("STATED_EXTREME", concl, label), Fraction(0), "both", note,
                                       f"stated across sentences: {how}; figures from sentence {s.sentence + 1}: {_series_label(s, years)}"))
            except FigureTooLarge:
                undecided.append(QuantUndecided(pi, si + 1, sentences[si].strip(), clause.strip()[:120], _TOO_LARGE_REASON))
    others: list[tuple[str, tuple]] = []
    for sent in all_clauses:
        sh = _SHARE_RE.search(sent)
        if sh and not any(sum(ch.isdigit() for ch in (g or "")) > MAX_FIGURE_DIGITS for g in sh.groups()):
            others.append(("share", (sent.strip(), sh.groups())))
        tot = _TOTAL_RE.search(sent)
        if tot and not any(sum(ch.isdigit() for ch in (tot.group(f"n{i}") or "")) > MAX_FIGURE_DIGITS for i in (1, 2, 3)) \
                and all(_cur_compatible(_cur_key(tot.group(f"c{i}") or ""), tot.group(f"w{i}") or "", _cur_key(tot.group("c3") or ""), tot.group("w3") or "") for i in (1, 2)):
            others.append(("total", (sent.strip(), tuple((tot.group(f"n{i}"), tot.group(f"u{i}"), tot.group(f"c{i}") or "", tot.group(f"w{i}") or "") for i in (1, 2, 3)))))
    return tuple(specs), tuple(undecided), tuple(others)


def undecided_quant_statements(text: str, tolerance: Fraction = Fraction(1, 20)) -> list[QuantUndecided]:
    """Stated derived figures and series relations no check could be built for, with the reason
    (units that cannot be compared, no figures in the sentence and none the paragraph's dated
    series supplies, an ambiguous series, a year that cannot be read)."""
    return list(_analyse(text, tolerance)[1])


def extract_quant_checks(text: str, *, request_id: str, claim_id: str, tolerance: Fraction = Fraction(1, 20)) -> list[QuantCheck]:
    """Find every stated derived figure bound to a pair of figures (in its own clause, or in
    the paragraph's dated series) and build an exact entailment problem for each, then the
    stated shares and totals. ``tolerance`` is the relative slack allowed for rounding (default
    5 per cent of the computed value; see :data:`TOLERANCE_RULE`). Memoised per call (the core
    pack reads the checks for its formal problems and for its check-limit report)."""
    return list(_extract_cached(text, request_id, claim_id, tolerance))


@lru_cache(maxsize=32)
def _extract_cached(text: str, request_id: str, claim_id: str, tolerance: Fraction) -> tuple[QuantCheck, ...]:
    return tuple(_extract(text, request_id=request_id, claim_id=claim_id, tolerance=tolerance))


def _extract(text: str, *, request_id: str, claim_id: str, tolerance: Fraction) -> list[QuantCheck]:
    specs, _undecided, others = _analyse(text, tolerance)
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
