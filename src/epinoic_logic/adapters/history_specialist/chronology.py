"""Chronology relations stated inside one sentence, extracted once for two consumers.

The History structural proxy (``HI-CHR-001``) and the core pack's formal chronology
check must agree on which dated events a sentence orders, so both read the relations
from :func:`chronology_relations`. A relation is a cue (``after``, ``before``,
``followed``, ``followed by``, ``preceded``, ``preceded by``) with a dated event on
each side. Every cue of a sentence is examined, not only the first.

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
  with a relative marker). For ``after`` the cue clause names the earlier event; for
  ``before`` the later one.

A cue with no date on one side states no checkable order and yields nothing; a cue
with dates on both sides that cannot be paired yields an undecided relation with the
reason, so the router sees that an order was stated but not checked. The engine's
problem compares day ordinals (``(year*12+month)*32+day``, a missing month or day
counting as 0); the month indices ``later``/``earlier`` (``year*12+month``) are kept for
the proxy's report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
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
_CUE_RE = re.compile(r"(?<![\w-])(?P<cue>after|before|followed by|preceded by|followed|preceded)\b(?![-\w])(?!\s+(?:all|long)\b)", re.IGNORECASE)
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
    bare month after a preposition, year-only."""
    out: list[DateToken] = []
    for m in MONTH_YEAR_RE.finditer(text):
        out.append(DateToken(m.start(), m.end(), m.group(0), MONTHS[m.group("month").lower()], int(m.group("year")), _day(m.group("day"), m.group("day2"))))
    covered = [(t.start, t.end) for t in out]

    def taken(s: int, e: int) -> bool:
        return any(a <= s < b or a < e <= b for a, b in covered)

    for m in _DAY_MONTH_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        month = (m.group("month") or m.group("month2")).lower()
        day = _day(m.group("day"), m.group("day2"))
        if day is None:
            continue
        out.append(DateToken(m.start(), m.end(), m.group(0), MONTHS[month], None, day))
        covered.append((m.start(), m.end()))
    for m in _BARE_MONTH_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        if taken(s, e):
            continue
        out.append(DateToken(s, e, m.group(1), MONTHS[m.group(1).lower()], None))
        covered.append((s, e))
    for m in _YEAR_ONLY_RE.finditer(text):
        if taken(m.start(), m.end()):
            continue
        out.append(DateToken(m.start(), m.end(), m.group(0), None, int(m.group(1))))
        covered.append((m.start(), m.end()))
    out.sort(key=lambda t: t.start)
    return out


def years_in(text: str, *, dated_only: bool = False) -> list[int]:
    """The distinct years stated in ``text`` (month-year and year-only tokens), sorted; with
    ``dated_only`` only the years of month-year tokens (the years of dated events, not of a
    publication year in parentheses)."""
    return sorted({t.year for t in _tokens(text) if t.year is not None and (t.month is not None or not dated_only)})


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


def chronology_relations(sentence: str, context: Optional[str] = None) -> list[ChronologyRelation]:
    """Every dated ordering the sentence asserts (see the module docstring). ``context``
    is the paragraph the sentence stands in; its only stated year, when the sentence
    states none, supplies the year of a day-month or bare-month pair."""
    out: list[ChronologyRelation] = []
    sentence_years = years_in(sentence)
    context_years = years_in(context) if context else []
    dated_context_years = years_in(context, dated_only=True) if context else []
    for m in _CUE_RE.finditer(sentence):
        cue = m.group("cue").lower()
        left_text, right_text = sentence[: m.start()], sentence[m.end():]
        if _NOT_A_CUE_BEFORE_RE.search(left_text):
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
            if date_in_aside(left_clause, d1):
                aside = left_clause[max(left_clause[: d1.start].rfind(","), left_clause[: d1.start].rfind(";")) + 1: d1.start]
                if not (_EVENT_VERB_RE.search(aside) or _OCCURRENCE_BEFORE_CUE_RE.search(left_clause)):
                    if right_tokens:
                        later_txt, earlier_txt = (d1.text, right_tokens[0].text) if cue in ("after", "followed", "preceded by") else (right_tokens[0].text, d1.text)
                        out.append(ChronologyRelation(cue, later_txt, earlier_txt, None, None, False,
                                                      f"the only dated item before '{cue}' ({d1.text}) sits in an aside about the subject, not about the event being ordered", sentence))
                    continue
            if not right_tokens:
                continue
            d2 = right_tokens[0]
            if _CUE_RE.search(right_seg[: d2.start]):
                continue
            later, earlier = _orient(cue, d1, d2)
            out.append(_resolve(cue, later, earlier, sentence, sentence_years, context_years, dated_context_years))
            continue
        if cue not in ("after", "before"):
            continue
        lead = left_clause.strip(" ,")
        if lead and not _LEAD_OK_RE.match(lead):
            continue  # 'Britain after Waterloo': the cue modifies a noun; there is no dated left event
        all_right = _tokens(right_text)
        if not all_right:
            continue
        d1 = all_right[0]
        head = right_text[: d1.start]
        if re.search(r"[,;:]", head) or _CUE_RE.search(head):
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
        later, earlier = (d2, d1) if cue == "after" else (d1, d2)
        out.append(_resolve(cue, later, earlier, sentence, sentence_years, context_years, dated_context_years))
    return out


def chronology_findings_in(sentence: str, context: Optional[str] = None) -> Optional[tuple[int, int]]:
    """The first decided relation of ``sentence`` whose dates violate the stated order, as
    ``(later_as_stated, earlier_as_stated)`` month indices; ``None`` when every decided
    relation holds or nothing could be paired. Structural proxy for ``HI-CHR-001``."""
    for rel in chronology_relations(sentence, context):
        if rel.violated:
            return rel.later, rel.earlier  # type: ignore[return-value]
    return None
