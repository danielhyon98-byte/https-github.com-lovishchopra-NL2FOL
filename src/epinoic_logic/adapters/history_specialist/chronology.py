"""Chronology relations stated inside one sentence, extracted once for two consumers.

The History structural proxy (``HI-CHR-001``) and the core pack's formal chronology
check must agree on which dated events a sentence orders, so both read the relations
from :func:`chronology_relations`. A relation is a cue with a dated event on each side.
After-type cues put the event before them later (``after``, ``followed``, ``preceded by``,
``later than``, ``subsequent to``, ``postdated``, ``following``, ``in the wake of``, ``in the
aftermath of``); before-type cues earlier (``before``, ``preceded``, ``followed by``,
``earlier than``, ``sooner than``, ``prior to``, ``previous to``, ``predated``,
``antedated``, ``ahead of``, ``on the eve of``, ``in the run-up to``, ``preceding``). ``no
later than`` is a bound, ``the following year`` a date and ``followed from`` a consequence.
Every cue of a sentence is examined, not only the first.

Date tokens and their resolution:

* ``July 1932``, ``18 June 1815``, ``January 30, 1933``, ``c. 16 October 1962``: month-year,
  with the day when one is written;
* ``14 October``, ``on 26 October``, ``October 14``: a day-month token with no year;
* ``in March``, ``by late March``: a bare month with no year;
* ``the Act of 1788``, ``in 1919``: a year-only token (a four-digit year that is not part
  of a figure and carries no unit word).

Two dates are compared at the coarsest resolution they share: different years decide;
the same year decides only when both state a month and the months differ; the same
month decides only when both state a day and the days differ. An equal month with no
days, an equal year with no month, or the same day is UNDECIDED (``CORE-CHR-001``), never
a violation: a correct ordering inside one month is not an error, and an unstated day is
not evidence either way. A token with no year takes the year of the dated side when the
other side has one and that reading satisfies the stated order (any later year would too);
when neither side has a year, the year is taken from the sentence, else from the
paragraph (``context``), when exactly one year is stated there, and the relation's reason
says so; otherwise the relation is undecided because the year is not stated.

Shapes recognised:

* standard: ``<event> in <D1> ... <cue> ... <event> in <D2>``. ``D1`` is the nearest
  date before the cue inside the cue's own clause (no ``;``, ``:``, ``, and``, ``, but``
  or ``but`` between it and the cue) and ``D2`` the first date after the cue before the
  next clause break. A date that sits in a relative clause or a comma-delimited
  participial aside before the cue (``The party, which had been founded in January
  1919, was banned after ...``) is the ordered event only when the aside's verb is the
  subject's own occurrence (``met``, ``was held``, ``took place``, ``was fought``, ...;
  ``called`` is a summons, not an occurrence) or the main verb before the cue is one
  (``came``, ``happened``, ``followed``); otherwise the relation is reported as undecided
  rather than skipped.
* leading cue: ``..., and after <event> in <D1>, <event> in <D2>`` (the cue opens its
  clause, which closes at the first comma; the main clause that follows must not open
  with a relative marker). For an after-type cue the cue clause names the earlier event;
  for a before-type cue (``before``, ``prior to``) the later one.
* intransitive ``followed``/``preceded`` directly before a date (``followed in July
  1922``, ``followed, on 13 January 1923,``): the date is the cue's own subject's, and the
  other event is the one dated last before the cue in the sentence (across a coordinate
  clause or a leading ``After ...`` clause), else the one date of the previous sentence
  (several dates there: undecided).
* coordinated cues: in ``X in D0, after Y of D1 and before Z of D2`` the second cue orders
  the clause's subject (D0), never the first cue's object (D1); with no subject date the
  second relation is undecided.
* an event named without a date (``That election came after ...``, ``... before the
  treaty``): a definite noun phrase headed by an event noun is looked up in the paragraph's
  other sentences (the one date given within a few words of the noun in its clause; a date
  bounding a range such as ``up to 1923`` and a mention whose noun carries a modifier the side
  does not are not used). Both sides dated: decided, the reason naming the sentence the date
  came from. One side dated: undecided when the undated side is a demonstrative that must
  refer back, or when the dated side's date came from another sentence (stated across
  sentences); a dated and an undated, non-anaphoric event in one sentence state no checkable
  order and yield nothing.

A cue with dates on both sides that cannot be paired yields an undecided relation with the
reason, so the router sees that an order was stated but not checked. The engine's
problem compares day ordinals (``(year*12+month)*32+day``, a missing month or day
counting as 0); the month indices ``later``/``earlier`` (``year*12+month``) are kept for
the proxy's report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

__all__ = ["ChronologyRelation", "DateToken", "MONTH_YEAR_RE", "MONTHS", "chronology_findings_in", "chronology_relations", "date_in_aside", "month_index", "years_in"]

_MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTHS = {m.lower(): i for i, m in enumerate(_MONTH_NAMES.split("|"), start=1)}
#: 'July 1932', '18 June 1815', 'January 30, 1933' -> named groups ``day`` (before the month), ``month``, ``day2`` (after it), ``year``.
MONTH_YEAR_RE = re.compile(rf"\b(?:(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+)?(?P<month>{_MONTH_NAMES})\s+(?:(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?,?\s+)?(?P<year>1[0-9]{{3}}|20[0-9]{{2}})\b")
#: '14 October' / 'October 14' with no year following.
_DAY_MONTH_RE = re.compile(rf"\b(?:(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month>{_MONTH_NAMES})\b(?!,?\s*\d)|(?P<month2>{_MONTH_NAMES})\s+(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?\b(?!,?\s*\d))")
#: A month with no year after a preposition ('in March', 'by late March'); 'May' as a modal does not qualify.
_BARE_MONTH_RE = re.compile(
    rf"\b(?:in|by|on|of|until|till|during|from|to|since|that|early|late|mid)\s+(?:(?:early|late|mid)[\s-]+)?({_MONTH_NAMES})\b(?!\s*\d)"
)
#: A four-digit year standing alone: not inside a figure ('1,930', '4.1930', '1930.5') and not followed by a unit word.
_UNIT_WORDS = (r"per cent|percent|%|million|billion|thousand|trillion|seats|votes|tonnes|tons|marks|francs|dollars|pounds|shillings|men|women|people|troops|soldiers|dead|deaths|"
               r"casualties|killed|wounded|ships|aircraft|tanks|guns|acres|hectares|miles|km|kilometres|members|delegates|households|houses|workers|strikers|units|cases")
_YEAR_ONLY_RE = re.compile(rf"(?<![\d,.$£€])\b(1[0-9]{{3}}|20[0-9]{{2}})\b(?![\d,.]?\d)(?!\s*(?:{_UNIT_WORDS})\b)")
_CUE_RE = re.compile(
    r"(?<![\w-])(?P<cue>after|before|followed\s+by|preceded\s+by|followed|preceded|(?:earlier|later|sooner)\s+than|prior\s+to|previous\s+to|subsequent\s+to|"
    r"pre-?dated|predates|post-?dated|postdates|antedated|antedates|following|preceding|in\s+the\s+wake\s+of|in\s+the\s+aftermath\s+of|ahead\s+of|on\s+the\s+eve\s+of|"
    r"in\s+the\s+run-up\s+to)\b(?![-\w])(?!\s+(?:all|long)\b)", re.IGNORECASE)
#: 'named after', 'modelled after', 'look after', 'take after': not an ordering.
_NOT_A_CUE_BEFORE_RE = re.compile(r"\b(?:named|modelled|modeled|look(?:s|ed|ing)?|called|take[sn]?|took|taking|chase[sd]?|pattern(?:ed)?|styled|sought|seek(?:s|ing)?|run|ran|running|go(?:es|ing)?|went)\s+$", re.IGNORECASE)
_CLAUSE_BREAK_RE = re.compile(r";|:|,\s+(?:and|but|while|whereas|yet|so)\b|\b(?:but|while|whereas)\b", re.IGNORECASE)
_RELATIVE_CLAUSE_RE = re.compile(r"\b(?:which|who|whom|whose|that)\b", re.IGNORECASE)
_RELATIVE_START_RE = re.compile(r"^\s*(?:which|who|whom|whose|that)\b", re.IGNORECASE)
#: A comma-delimited aside that opens with a bare participle: ', founded in January 1919,' / ', fought on 18 June 1815,'.
_PARTICIPLE_OPENER_RE = re.compile(r"^\s*(?:founded|established|created|formed|born|signed|elected|appointed|published|written|dissolved|launched|begun|held|fought|passed|issued|convened|concluded|proclaimed|announced|set up)\b", re.IGNORECASE)
#: Verbs that denote the subject's own occurrence: the aside's date is then the subject's date. ``called`` (a summons, not the
#: meeting) is deliberately absent: 'The plenum, which had been called in June 1959, met after ...' is undecided, not decided.
_EVENT_VERB_RE = re.compile(
    r"\b(?:met|convened|sat|came|happened|occurred|took place|opened|began|started|ended|closed|lasted|broke out|erupted"
    r"|(?:was|were|had been|having been|being)?\s*(?:held|fought|signed|concluded|passed|issued|published|announced|proclaimed|convened|staged|delivered))\b"
    r"|^\s*(?:held|fought|signed|concluded|passed|issued|published|announced|proclaimed|convened|staged|delivered)\b",
    re.IGNORECASE,
)
#: An occurrence verb right before the cue makes the subject itself the ordered event.
_OCCURRENCE_BEFORE_CUE_RE = re.compile(r"\b(?:came|happened|occurred|took place|arrived|fell|rose|began|ended|followed|was held|were held|was fought|were fought)\s+(?:only\s+|shortly\s+|soon\s+|immediately\s+|long\s+|just\s+|well\s+|not long\s+)?$", re.IGNORECASE)
#: What may stand between a clause break and a leading cue: nothing, or a conjunction/adverb.
_LEAD_OK_RE = re.compile(r"^(?:(?:and|but|yet|so|then|only|shortly|soon|immediately|long|just|even|not long|which|and only|but only)\s*)*$", re.IGNORECASE)
_MONTH_BY_INDEX = {i: m for m, i in MONTHS.items()}


@dataclass(frozen=True)
class DateToken:
    start: int
    end: int
    text: str
    month: Optional[int]      # None for a year-only token
    year: Optional[int]       # None for a bare month or a day-month token
    day: Optional[int] = None

    def index(self, year: Optional[int] = None) -> int:
        """Month index ``year*12+month`` (a year-only token counts its month as 0)."""
        y = self.year if self.year is not None else year
        assert y is not None
        return y * 12 + (self.month or 0)

    def ordinal(self, year: Optional[int] = None) -> int:
        """Day ordinal ``(year*12+month)*32+day``; a missing month or day counts as 0."""
        return self.index(year) * 32 + (self.day or 0)


@dataclass(frozen=True)
class ChronologyRelation:
    """One ordering a sentence asserts: the event named ``later_text`` came after ``earlier_text``."""
    cue: str
    later_text: str
    earlier_text: str
    later: Optional[int]      # year*12+month when decided
    earlier: Optional[int]
    decided: bool
    reason: str = ""          # why the relation is undecided, or how an unstated year was read
    sentence: str = ""
    later_ordinal: Optional[int] = None    # day ordinal when decided (what the engine compares)
    earlier_ordinal: Optional[int] = None

    @property
    def violated(self) -> bool:
        if not self.decided:
            return False
        if self.later_ordinal is not None and self.earlier_ordinal is not None:
            return self.later_ordinal <= self.earlier_ordinal
        return self.later is not None and self.earlier is not None and self.later <= self.earlier


def month_index(month_name: str, year: str) -> int:
    return int(year) * 12 + MONTHS[month_name.lower()]


def date_in_aside(before: str, date: "re.Match[str] | DateToken") -> bool:
    """True when ``date`` sits inside a relative clause or participial aside that closes
    before the ordering cue: ``The party, which had been founded in January 1919, was
    banned after ...``. The aside opens after the last comma before the date with a
    relative marker or a bare participle, and a comma follows the date. ``The vote fell
    in November 1931, which came only after ...`` is not an aside: the marker follows
    the date and makes it the ordered event."""
    start, end = (date.start, date.end) if isinstance(date, DateToken) else (date.start(), date.end())
    pre = before[:start]
    opener = pre[max(pre.rfind(","), pre.rfind(";")) + 1:]
    return (bool(_RELATIVE_CLAUSE_RE.search(opener)) or bool(_PARTICIPLE_OPENER_RE.match(opener))) and "," in before[end:]


def _day(*groups: Optional[str]) -> Optional[int]:
    for g in groups:
        if g is not None:
            d = int(g)
            if 1 <= d <= 31:
                return d
    return None


def _tokens(text: str) -> list[DateToken]:
    """Every date token of ``text`` in order: month-year (with a day when written), day-month,
    bare month after a preposition, year-only. A candidate that starts inside a token already
    read, or ends inside one, is not a second token. The coverage test is a position mask, so
    a paragraph of hundreds of dates is read in one pass, not one pass per date."""
    out: list[DateToken] = []
    covered = bytearray(len(text) + 1)  # covered[i] == 1 when character i belongs to a token already read

    def cover(s: int, e: int) -> None:
        covered[s:e] = b"\x01" * (e - s)

    def taken(s: int, e: int) -> bool:
        # the candidate starts inside a token (a <= s < b) or ends inside one (a < e <= b, i.e. e - 1 is covered)
        return bool(covered[s]) or (e > s and bool(covered[e - 1]))

    for m in MONTH_YEAR_RE.finditer(text):
        out.append(DateToken(m.start(), m.end(), m.group(0), MONTHS[m.group("month").lower()], int(m.group("year")), _day(m.group("day"), m.group("day2"))))
        cover(m.start(), m.end())
    for m in _DAY_MONTH_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        month = (m.group("month") or m.group("month2")).lower()
        day = _day(m.group("day"), m.group("day2"))
        if day is None:
            continue
        out.append(DateToken(m.start(), m.end(), m.group(0), MONTHS[month], None, day))
        cover(m.start(), m.end())
    for m in _BARE_MONTH_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        if taken(s, e):
            continue
        out.append(DateToken(s, e, m.group(1), MONTHS[m.group(1).lower()], None))
        cover(s, e)
    for m in _YEAR_ONLY_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        out.append(DateToken(m.start(), m.end(), m.group(0), None, int(m.group(1))))
        cover(m.start(), m.end())
    out.sort(key=lambda t: t.start)
    return out


@lru_cache(maxsize=256)
def _years_in_cached(text: str, dated_only: bool) -> tuple[int, ...]:
    return tuple(sorted({t.year for t in _tokens(text) if t.year is not None and (t.month is not None or not dated_only)}))


def years_in(text: str, *, dated_only: bool = False) -> list[int]:
    """The distinct years stated in ``text`` (month-year and year-only tokens), sorted; with
    ``dated_only`` only the years of month-year tokens (the years of dated events, not of a
    publication year in parentheses). The answer is memoised per text (a bounded cache), since
    every sentence of a paragraph asks for the paragraph's years."""
    return list(_years_in_cached(text, dated_only))


def _context_year(sentence_years: list[int], context_years: list[int], dated_context_years: list[int]) -> tuple[Optional[int], str]:
    """The year to read an undated pair in, and where it came from: the sentence's only
    year; else the paragraph's only year stated with a month (its dated events); else the
    paragraph's only year of any kind. Several candidates at every level decide nothing."""
    if len(sentence_years) == 1:
        return sentence_years[0], "the sentence's only stated year"
    if not sentence_years:
        if len(dated_context_years) == 1:
            return dated_context_years[0], "the paragraph's dated events, which state one year"
        if len(context_years) == 1:
            return context_years[0], "the paragraph's only stated year"
    return None, ""


def _orient(cue: str, left: DateToken, right: DateToken) -> tuple[DateToken, DateToken]:
    """(later, earlier) for the standard shape: 'X after Y', 'X followed Y', 'X preceded by Y' put X later."""
    if cue in ("after", "followed", "preceded by"):
        return left, right
    return right, left


def _shown(token: DateToken, year: Optional[int]) -> str:
    return token.text if token.year is not None or year is None else f"{token.text} {year}"


def _order(later: DateToken, earlier: DateToken, ly: int, ey: int) -> Optional[str]:
    """None when the two dates can be compared at the resolution they share; otherwise the
    reason the comparison is undecided (same year with a month missing, same month with a
    day missing, the same day)."""
    if ly != ey:
        return None
    if later.month is None or earlier.month is None:
        bare = later if later.month is None else earlier
        return f"'{bare.text}' states only a year and both events fall in {ly}; the order within the year is not stated"
    if later.month != earlier.month:
        return None
    month = _MONTH_BY_INDEX[later.month].capitalize()
    if later.day is None or earlier.day is None:
        missing = later if later.day is None else earlier
        return f"both events fall in {month} {ly} and the day of '{missing.text}' is not stated; the order within the month is not stated"
    if later.day == earlier.day:
        return f"both events are dated {later.day} {month} {ly}; the order within the day is not stated"
    return None


def _decided(cue: str, later: DateToken, earlier: DateToken, ly: int, ey: int, reason: str, sentence: str) -> ChronologyRelation:
    return ChronologyRelation(cue, _shown(later, ly), _shown(earlier, ey), later.index(ly), earlier.index(ey), True, reason, sentence,
                              later_ordinal=later.ordinal(ly), earlier_ordinal=earlier.ordinal(ey))


def _resolve(cue: str, later: DateToken, earlier: DateToken, sentence: str, sentence_years: list[int], context_years: list[int], dated_context_years: list[int]) -> ChronologyRelation:
    if later.year is not None and earlier.year is not None:
        why = _order(later, earlier, later.year, earlier.year)
        if why is None:
            return _decided(cue, later, earlier, later.year, earlier.year, "", sentence)
        return ChronologyRelation(cue, later.text, earlier.text, None, None, False, why, sentence)
    if later.year is None and earlier.year is None:
        year, source = _context_year(sentence_years, context_years, dated_context_years)
        if year is None:
            stated = sentence_years or context_years
            how = f"; the sentence states {len(sentence_years)} different years" if len(sentence_years) > 1 else (f"; the paragraph states {len(stated)} different years" if len(stated) > 1 else "")
            return ChronologyRelation(cue, later.text, earlier.text, None, None, False, f"neither '{later.text}' nor '{earlier.text}' carries a year{how}", sentence)
        why = _order(later, earlier, year, year)
        if why is None:
            return _decided(cue, later, earlier, year, year, f"the year {year} was taken from {source} for both '{later.text}' and '{earlier.text}'", sentence)
        return ChronologyRelation(cue, later.text, earlier.text, None, None, False, f"read in {year} ({source}), {why}", sentence)
    year = later.year if later.year is not None else earlier.year
    assert year is not None
    bare = later if later.year is None else earlier
    why = _order(later, earlier, year, year)
    if why is None:
        if later.ordinal(year) > earlier.ordinal(year):
            return _decided(cue, later, earlier, year, year, f"the year {year} of the dated side was carried to '{bare.text}'; any later year satisfies the stated order too", sentence)
        return ChronologyRelation(cue, later.text, earlier.text, None, None, False,
                                  f"the year of '{bare.text}' is not stated: read in {year} the order fails, read in an adjacent year it holds", sentence)
    return ChronologyRelation(cue, later.text, earlier.text, None, None, False, f"the year of '{bare.text}' is not stated; read in {year}, {why}", sentence)


#: After-type cues put the event before them later ('X after Y', 'X followed Y', 'X was preceded by Y'); before-type cues earlier.
_AFTER_TYPE = frozenset({"after", "followed", "preceded by", "later than", "subsequent to", "postdated", "postdates", "post-dated", "following",
                         "in the wake of", "in the aftermath of"})
_BEFORE_TYPE = frozenset({"before", "preceded", "followed by", "earlier than", "sooner than", "prior to", "previous to", "predated", "predates", "pre-dated",
                          "antedated", "antedates", "ahead of", "on the eve of", "in the run-up to", "preceding"})
#: Cues that can open a clause as a preposition: 'After the riot of 1817, ...', 'Prior to the treaty of April 1922, ...'.
_LEADING_CUES = frozenset({"after", "before", "prior to", "previous to", "subsequent to", "following", "in the wake of", "in the aftermath of", "ahead of",
                           "on the eve of", "in the run-up to", "preceding"})
#: 'followed in July 1922', 'followed, on 13 January 1923,': the cue's subject is dated by the date that follows (intransitive use).
_INTRANSITIVE_HEAD_RE = re.compile(
    r"^\s*,?\s*(?:(?:soon|shortly|quickly|swiftly|rapidly|only|later|immediately|closely|in turn|then)\s+)*,?\s*(?:in|on|by|during|at|within)\s+"
    r"(?:(?:early|late|mid)[\s-]+|the\s+(?:end|start|beginning|middle|spring|summer|autumn|winter|first half|second half)\s+of\s+|(?:about|around|c\.|ca\.|circa)\s+)?$",
    re.IGNORECASE)
_BY_DATE_HEAD_RE = re.compile(r"^\s*(?:(?:early|late|mid)[\s-]+|the\s+(?:end|start|beginning|middle)\s+of\s+|(?:about|around|c\.|ca\.|circa)\s+)?$", re.IGNORECASE)
#: Between a first cue's object and a second cue: 'after X of May 1921 and before Y of 1922' coordinates both cues on the clause subject.
_COORDINATED_GAP_RE = re.compile(r"^\s*,?\s*(?:and|or|but|yet|as well as)\s+(?:(?:also|only|long|shortly|just|well|soon|immediately|not long|even)\s+)*$", re.IGNORECASE)
#: A date that bounds a range is not the date of the event beside it ('instability up to 1923', 'since 1793').
_RANGE_BEFORE_DATE_RE = re.compile(r"\b(?:up to|until|till|since|from|through|throughout|between|by)\s+(?:(?:early|late|mid)[\s-]+)?(?:the\s+)?$", re.IGNORECASE)
#: Nouns that name a datable event: only these are looked up in the paragraph when a side of a cue carries no date of its own.
_EVENT_NOUNS = frozenset("""election vote referendum plebiscite crisis crash collapse treaty war peace armistice truce putsch coup rising uprising revolt rebellion revolution
    strike occupation invasion battle siege conference congress plenum meeting summit decree act law bill plan agreement pact settlement ultimatum default murder
    assassination reform budget census purge famine flight letter broadcast speech declaration resignation dissolution devaluation moratorium holiday riot massacre
    blockade landing offensive campaign surrender abdication coronation accession founding foundation partition annexation mutiny raid bombing election""".split())
_DEMONSTRATIVES = frozenset({"that", "this", "these", "those"})
_DEFINITES = frozenset({"the", "its", "their", "his", "her"}) | _DEMONSTRATIVES
#: Words that end a noun phrase read after a cue, or that are stripped from the end of the clause before a cue.
_NP_STOP = frozenset("""was were is are be been being had has have did do does came come comes began begun begins started occurred happened took take followed
    ended broke arrived fell rose met collapsed erupted passed signed held declared announced issued resumed continued persisted emerged appeared developed grew
    spread made led caused produced brought turned and or but so because which who whom whose when while as if than in on at by of for from to with into
    only shortly soon immediately long just well not also even still already then again first finally later""".split())
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ'’-]+")
#: 'Signed on ', 'held in ': a participial opener whose date is the noun's that follows the comma.
_PARTICIPIAL_DATE_RE = re.compile(r"^\s*[A-Za-z]+(?:\s+[A-Za-z]+)?\s+(?:on|in|at|during|by)\s+(?:c\.\s+)?$", re.IGNORECASE)


def _np_words(text: str, *, trailing: bool) -> list[str]:
    """The noun phrase at the end (``trailing``) or the start of ``text``, as lower-case words with its determiner first.
    At the end of a clause, a 'that' after the clause's first word is a complementizer or a relative, not a determiner."""
    words = [w.lower().strip("'’") for w in _WORD_RE.findall(text)]
    if trailing:
        while words and (words[-1] in _NP_STOP or words[-1] == "that"):
            words.pop()
        out: list[str] = []
        for i in range(len(words) - 1, -1, -1):
            w = words[i]
            if w in _NP_STOP or (w == "that" and i > 0):
                break
            out.insert(0, w)
            if w in _DEFINITES and (w not in _DEMONSTRATIVES or i == 0):
                break
        return out[-6:]
    out = []
    for w in words:
        if w in _NP_STOP and not (w in _DEFINITES and not out):
            break
        out.append(w)
        if len(out) >= 6:
            break
    return out


def _stem(word: str) -> str:
    return word.lower().rstrip("'’").removesuffix("s") if len(word) > 3 else word.lower()


def _np_head(words: list[str]) -> Optional[str]:
    """The event noun of a noun phrase (its last event-noun word), or None."""
    for w in reversed(words):
        if _stem(w) in _EVENT_NOUNS or w in _EVENT_NOUNS:
            return _stem(w)
    return None


def _premodifiers(text: str, head: str, near: int) -> list[str]:
    """The words written directly before the occurrence of ``head`` nearest to offset ``near`` in
    ``text`` (stems, back to a determiner; a date between them ends the run): 'The agrarian crisis'
    -> ['agrarian'], 'the September 1930 election' -> []."""
    words = list(_WORD_RE.finditer(text))
    hits = [i for i, w in enumerate(words) if _stem(w.group(0)) == head]
    if not hits:
        return []
    i = min(hits, key=lambda k: abs(words[k].start() - near))
    out: list[str] = []
    j = i - 1
    while j >= 0:
        w = words[j].group(0).lower()
        gap = text[words[j].end(): words[j + 1].start()]
        if gap.strip() or w in _DEFINITES or w in _NP_STOP or w in MONTHS:
            break
        out.insert(0, _stem(w))
        j -= 1
    return out


@lru_cache(maxsize=64)
def _paragraph_sentences(context: str) -> tuple[tuple[str, str, tuple[DateToken, ...]], ...]:
    """``(sentence, whitespace-normalised sentence, date tokens)`` for every sentence of the paragraph,
    memoised per paragraph: every cue of every sentence asks for the same paragraph."""
    from .sentences import split_sentences
    return tuple((s, " ".join(s.split()), tuple(_tokens(s))) for s in split_sentences(context))


def _dated_mention(head: str, context: str, sentence: str, side_words: Optional[set] = None) -> tuple[Optional[DateToken], str]:
    """The one date the paragraph gives the event noun ``head`` outside ``sentence``: a date
    within a few words of the noun in the same clause ('the September 1930 election', 'the
    collapse of the Danatbank on 13 July 1931', 'Signed on 28 June 1919, the treaty'); a date
    that bounds a range ('up to 1923') is not the event's date, and a mention whose noun carries a
    modifier the side does not ('The agrarian crisis that began in 1928' for 'the crisis') may be
    another event and is not used. Returns the token and the sentence it stands in, or None and a
    reason (no mention, or several dates)."""
    found: dict[int, tuple[DateToken, str]] = {}
    target = " ".join(sentence.split())
    for other, normalized, tokens in _paragraph_sentences(context):
        if normalized == target or target in normalized:
            continue
        for tok in tokens:
            if tok.year is None:
                continue
            before = other[: tok.start]
            if _RANGE_BEFORE_DATE_RE.search(before):
                continue
            clause_before = re.split(r"[,;:()]", before)[-1]
            after = other[tok.end:]
            if _PARTICIPLE_OPENER_RE.match(clause_before) and _PARTICIPIAL_DATE_RE.match(clause_before):
                window_after = " ".join(re.split(r"[;:()]", after)[0].split(",")[:2])  # 'Signed on 28 June 1919, the treaty': the noun follows the comma
            else:
                window_after = re.split(r"[,;:()]", after)[0]
            words = [_stem(w) for w in _WORD_RE.findall(clause_before)][-4:] + [_stem(w) for w in _WORD_RE.findall(window_after)][:3]
            if head in words:
                if side_words is not None and not set(_premodifiers(other, head, tok.start)) <= side_words:
                    continue
                found.setdefault(tok.ordinal(), (tok, other))
    if not found:
        return None, "no other sentence of the paragraph dates it"
    if len(found) > 1:
        return None, f"the paragraph gives it {len(found)} different dates"
    tok, other = next(iter(found.values()))
    return tok, other.strip()


def _side_date(text: str, *, trailing: bool, context: Optional[str], sentence: str) -> tuple[Optional[DateToken], str, bool, str]:
    """For a side of a cue that carries no date in the sentence: ``(token, phrase, anaphoric, how)``.
    The token is the date the paragraph gives the side's event noun elsewhere (None when there is
    none); ``anaphoric`` is True for a demonstrative ('that election'), which must refer back."""
    words = _np_words(text, trailing=trailing)
    phrase = " ".join(words)
    head = _np_head(words)
    anaphoric = bool(words) and words[0] in _DEMONSTRATIVES and head is not None
    if head is None or not words or words[0] not in _DEFINITES or not context:
        return None, phrase, anaphoric, ""
    tok, where = _dated_mention(head, context, sentence, {_stem(w) for w in words})
    if tok is None:
        return None, phrase, anaphoric, where
    return tok, phrase, anaphoric, f"the date of '{phrase}' ({tok.text}) was taken from another sentence of the paragraph: '{where[:120]}'"


def _cue_name(m: "re.Match[str]") -> str:
    return " ".join(m.group("cue").lower().split())


def _is_after_type(cue: str) -> bool:
    return cue in _AFTER_TYPE


def _orient_cue(cue: str, left: DateToken, right: DateToken) -> tuple[DateToken, DateToken]:
    """(later, earlier) for the standard shape '<left> <cue> <right>'."""
    return (left, right) if _is_after_type(cue) else (right, left)


def _previous_sentence_date(sentence: str, context: Optional[str]) -> tuple[Optional[DateToken], str]:
    """The one dated item of the sentence before ``sentence`` in ``context`` (for 'Stabilisation followed in 1924.')."""
    if not context:
        return None, ""
    sentences = _paragraph_sentences(context)
    target = " ".join(sentence.split())
    for i, (_s, normalized, _tokens_of) in enumerate(sentences):
        if normalized == target:
            if i == 0:
                return None, ""
            prev = [t for t in sentences[i - 1][2] if t.year is not None]
            if len(prev) == 1:
                return prev[0], sentences[i - 1][0].strip()
            return None, f"the previous sentence states {len(prev)} dates" if prev else ""
    return None, ""


def chronology_relations(sentence: str, context: Optional[str] = None) -> list[ChronologyRelation]:
    """Every dated ordering the sentence asserts (see the module docstring). ``context``
    is the paragraph the sentence stands in; its only stated year, when the sentence
    states none, supplies the year of a day-month or bare-month pair, and its other
    sentences date an event the sentence names without a date ('That election came after
    the Danatbank collapse of July 1931'). The answer is memoised per (sentence, paragraph):
    the History proxy, the formal check and the undecided report all ask for it."""
    return list(_chronology_relations_cached(sentence, context))


@lru_cache(maxsize=1024)
def _chronology_relations_cached(sentence: str, context: Optional[str]) -> tuple[ChronologyRelation, ...]:
    return tuple(_chronology_relations(sentence, context))


def _chronology_relations(sentence: str, context: Optional[str] = None) -> list[ChronologyRelation]:
    out: list[ChronologyRelation] = []
    cues = list(_CUE_RE.finditer(sentence))
    if not cues:
        return out  # no ordering cue: nothing to read, and the paragraph's years are not needed
    sentence_years = years_in(sentence)
    context_years = years_in(context) if context else []
    dated_context_years = years_in(context, dated_only=True) if context else []
    seen: set[tuple[str, str]] = set()

    def emit(rel: ChronologyRelation) -> None:
        key = (rel.later_text, rel.earlier_text)
        if key in seen:
            return  # one ordering read by two shapes is one relation
        seen.add(key)
        out.append(rel)

    def resolve(cue: str, later: DateToken, earlier: DateToken, how: str = "") -> ChronologyRelation:
        rel = _resolve(cue, later, earlier, sentence, sentence_years, context_years, dated_context_years)
        if how:
            rel = ChronologyRelation(rel.cue, rel.later_text, rel.earlier_text, rel.later, rel.earlier, rel.decided, f"{how}; {rel.reason}" if rel.reason else how,
                                     rel.sentence, rel.later_ordinal, rel.earlier_ordinal)
        return rel

    def undecided(cue: str, later_txt: str, earlier_txt: str, reason: str) -> None:
        emit(ChronologyRelation(cue, later_txt, earlier_txt, None, None, False, reason, sentence))

    def across(cue: str, left_tok: Optional[DateToken], right_tok: Optional[DateToken], left_text: str, right_text: str) -> None:
        """A cue with a side that carries no date in the sentence: look the side's event up in the paragraph."""
        lhow = rhow = ""
        l_anaphor = r_anaphor = False
        l_phrase = r_phrase = ""
        l_cross = r_cross = False
        if left_tok is None:
            left_tok, l_phrase, l_anaphor, lhow = _side_date(left_text, trailing=True, context=context, sentence=sentence)
            l_cross = left_tok is not None
        if right_tok is None:
            right_tok, r_phrase, r_anaphor, rhow = _side_date(right_text, trailing=False, context=context, sentence=sentence)
            r_cross = right_tok is not None
        if left_tok is not None and right_tok is not None:
            later, earlier = _orient_cue(cue, left_tok, right_tok)
            emit(resolve(cue, later, earlier, "; ".join(h for h in (lhow if l_cross else "", rhow if r_cross else "") if h)))
            return
        if left_tok is None and right_tok is None:
            return  # no dated event on either side: no checkable order
        dated, dated_cross, how = (left_tok, l_cross, lhow) if left_tok is not None else (right_tok, r_cross, rhow)
        missing, missing_anaphor, missing_how = (r_phrase, r_anaphor, rhow) if left_tok is not None else (l_phrase, l_anaphor, lhow)
        if not (missing_anaphor or dated_cross):
            return  # one dated event and an undated, non-anaphoric one in the same sentence: no checkable order (see the module docstring)
        if missing_anaphor:
            reason = f"'{missing}' refers to an event dated in another sentence, which could not be identified ({missing_how or 'no other sentence of the paragraph dates it'})"
        else:
            reason = f"stated across sentences: {how}, but '{missing or 'the other event'}' carries no date in this sentence or elsewhere in the paragraph"
        dated_txt = dated.text if dated.year is not None else dated.text
        if (left_tok is not None) == _is_after_type(cue):
            undecided(cue, dated_txt, missing or "the other event", reason)
        else:
            undecided(cue, missing or "the other event", dated_txt, reason)

    for m in cues:
        cue = _cue_name(m)
        left_text, right_text = sentence[: m.start()], sentence[m.end():]
        if _NOT_A_CUE_BEFORE_RE.search(left_text):
            continue
        if cue in ("later than", "earlier than", "sooner than") and re.search(r"\b(?:no|not|nothing|none)\s+$", left_text, re.IGNORECASE):
            continue  # 'no later than' is a bound, not an order
        if cue in ("following", "preceding") and re.search(r"\b(?:the|a|an|in the|of the)\s+$", left_text, re.IGNORECASE):
            continue  # 'the following year', 'the preceding months'
        if cue == "followed" and re.match(r"\s+(?:from|suit|through|up)\b", right_text, re.IGNORECASE):
            continue  # 'followed from' is a consequence, not an order
        # intransitive 'followed in July 1922': the cue's subject is dated by the date after it; the other event is the one dated before the cue
        if cue in ("followed", "preceded", "followed by", "preceded by"):
            rt = _tokens(right_text)
            head_re = _BY_DATE_HEAD_RE if cue.endswith(" by") else _INTRANSITIVE_HEAD_RE
            if rt and head_re.match(right_text[: rt[0].start]):
                subject = rt[0]
                lt = _tokens(left_text)
                if lt:
                    other = lt[-1]
                    how = ""
                    if date_in_aside(left_text, other) and not _EVENT_VERB_RE.search(left_text[max(left_text[: other.start].rfind(","), 0): other.start]):
                        undecided(cue, subject.text if cue.startswith("followed") else other.text, other.text if cue.startswith("followed") else subject.text,
                                  f"'{cue} {right_text[: rt[0].end].strip()}' dates its own subject; the only earlier date ({other.text}) sits in an aside about the subject, not about another event")
                        continue
                else:
                    other, where = _previous_sentence_date(sentence, context)
                    if other is None:
                        if where:  # the previous sentence dates several events: which one is followed is not stated
                            later_txt, earlier_txt = (subject.text, "the previous sentence's event") if cue.startswith("followed") else ("the previous sentence's event", subject.text)
                            undecided(cue, later_txt, earlier_txt, f"'{cue}' has no object here and {where}; which event it orders its subject against is not stated")
                        continue  # no other dated event to order the subject against
                    how = f"'{cue}' with no object orders its subject after the event of the previous sentence, dated {other.text} ('{where[:120]}')"
                later, earlier = (subject, other) if cue.startswith("followed") else (other, subject)
                emit(resolve(cue, later, earlier, how))
                continue
        breaks = list(_CLAUSE_BREAK_RE.finditer(left_text))
        clause_start = breaks[-1].end() if breaks else 0
        left_clause = left_text[clause_start:]
        left_tokens = _tokens(left_clause)
        right_break = _CLAUSE_BREAK_RE.search(right_text)
        right_seg = right_text[: right_break.start()] if right_break else right_text
        right_tokens = _tokens(right_seg)
        if left_tokens:
            d1 = left_tokens[-1]
            if _CUE_RE.search(left_clause[d1.end:]):
                continue  # a nearer cue owns this date
            # 'X in D0, after Y of D1 and before Z of D2': the second cue orders the clause's subject (D0), not Y
            prior_cues = [c for c in _CUE_RE.finditer(left_clause[: d1.start])]
            if prior_cues and _COORDINATED_GAP_RE.match(left_clause[d1.end:]):
                c0 = prior_cues[-1]
                between = [t for t in left_tokens if c0.end() <= t.start < d1.start]
                if not between:
                    subject_tokens = [t for t in left_tokens if t.end <= c0.start()]
                    if not subject_tokens or _CUE_RE.search(left_clause[subject_tokens[-1].end: c0.start()]):
                        if right_tokens:
                            later_txt, earlier_txt = ("the clause's subject", right_tokens[0].text) if _is_after_type(cue) else (right_tokens[0].text, "the clause's subject")
                            undecided(cue, later_txt, earlier_txt, f"'{cue}' is coordinated with '{_cue_name(c0)}' and orders the clause's subject, which carries no date in this sentence")
                        continue
                    d1 = subject_tokens[-1]
            if date_in_aside(left_clause, d1):
                aside = left_clause[max(left_clause[: d1.start].rfind(","), left_clause[: d1.start].rfind(";")) + 1: d1.start]
                if not (_EVENT_VERB_RE.search(aside) or _OCCURRENCE_BEFORE_CUE_RE.search(left_clause)):
                    if right_tokens:
                        later_txt, earlier_txt = (d1.text, right_tokens[0].text) if _is_after_type(cue) else (right_tokens[0].text, d1.text)
                        out.append(ChronologyRelation(cue, later_txt, earlier_txt, None, None, False,
                                                      f"the only dated item before '{cue}' ({d1.text}) sits in an aside about the subject, not about the event being ordered", sentence))
                    continue
            if not right_tokens:
                across(cue, d1, None, left_clause, right_seg)
                continue
            d2 = right_tokens[0]
            if _CUE_RE.search(right_seg[: d2.start]):
                continue
            later, earlier = _orient_cue(cue, d1, d2)
            emit(resolve(cue, later, earlier))
            continue
        lead = left_clause.strip(" ,")
        if cue not in _LEADING_CUES or (lead and not _LEAD_OK_RE.match(lead)):
            # 'Britain after Waterloo' (the cue modifies a noun) or 'That election came after ...': the left side carries no date here
            if right_tokens and not _CUE_RE.search(right_seg[: right_tokens[0].start]):
                across(cue, None, right_tokens[0], left_clause, right_seg)
            elif not right_tokens:
                across(cue, None, None, left_clause, right_seg)
            continue
        all_right = _tokens(right_text)
        if not all_right:
            continue
        d1 = all_right[0]
        head = right_text[: d1.start]
        if re.search(r"[,;:]", head) or _CUE_RE.search(head):
            # 'After that election, the Act passed in March 1931': the cue clause names its event without a date
            comma = head.find(",")
            if comma > 0 and not re.search(r"[;:]", head[:comma]) and not _CUE_RE.search(head):
                main_tokens = _tokens(right_text[comma:])
                if main_tokens:
                    main_first = DateToken(main_tokens[0].start + comma, main_tokens[0].end + comma, main_tokens[0].text, main_tokens[0].month, main_tokens[0].year, main_tokens[0].day)
                    across(cue, main_first, None, "", head[:comma])
            continue
        tail = right_text[d1.end:]
        close = re.search(r"[,;:]", tail)
        if close is None or tail[close.start()] != ",":
            continue
        main = tail[close.end():]
        main_break = _CLAUSE_BREAK_RE.search(main)
        main_seg = main[: main_break.start()] if main_break else main
        if _RELATIVE_START_RE.match(main_seg):
            continue
        main_tokens = _tokens(main_seg)
        if not main_tokens or _CUE_RE.search(main_seg[: main_tokens[0].start]):
            continue
        d2 = main_tokens[0]
        later, earlier = (d2, d1) if _is_after_type(cue) else (d1, d2)
        emit(resolve(cue, later, earlier))
    return out


def chronology_findings_in(sentence: str, context: Optional[str] = None) -> Optional[tuple[int, int]]:
    """The first decided relation of ``sentence`` whose dates violate the stated order, as
    ``(later_as_stated, earlier_as_stated)`` month indices; ``None`` when every decided
    relation holds or nothing could be paired. Structural proxy for ``HI-CHR-001``."""
    for rel in chronology_relations(sentence, context):
        if rel.violated:
            return rel.later, rel.earlier  # type: ignore[return-value]
    return None
