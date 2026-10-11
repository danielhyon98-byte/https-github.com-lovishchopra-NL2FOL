"""Chronology relations stated inside one sentence, extracted once for two consumers.

The History structural proxy (``HI-CHR-001``) and the core pack's formal chronology
check must agree on which dated events a sentence orders, so both read the relations
from :func:`chronology_relations`. A relation is a cue (``after``, ``before``,
``followed``, ``followed by``, ``preceded``, ``preceded by``) with a dated event on
each side. Every cue of a sentence is examined, not only the first.

Shapes recognised (dates are month-year, ``18 June 1815`` or ``January 30, 1933``):

* standard: ``<event> in <D1> ... <cue> ... <event> in <D2>``. ``D1`` is the nearest
  date before the cue inside the cue's own clause (no ``;``, ``:``, ``, and``, ``, but``
  or ``but`` between it and the cue) and ``D2`` the first date after the cue before the
  next clause break. A date that sits in a relative clause or a comma-delimited
  participial aside before the cue (``The party, which had been founded in January
  1919, was banned after ...``) is the ordered event only when the aside's verb is the
  subject's own occurrence (``met``, ``was held``, ``took place``, ``was fought``, ...)
  or the main verb before the cue is one (``came``, ``happened``, ``followed``);
  otherwise the relation is reported as undecided rather than skipped.
* leading cue: ``..., and after <event> in <D1>, <event> in <D2>`` (the cue opens its
  clause, which closes at the first comma; the main clause that follows must not open
  with a relative marker). For ``after`` the cue clause names the earlier event; for
  ``before`` the later one.
* a bare month on one side (``after ... in January 1817, Parliament suspended habeas
  corpus in March``) takes the year of the dated side; the relation is decided only
  when that reading satisfies the stated order (any later year would too), otherwise
  it is undecided because the year is not stated.

A cue with no date on one side states no checkable order and yields nothing; a cue
with dates on both sides that cannot be paired yields an undecided relation with the
reason, so the router sees that an order was stated but not checked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

__all__ = ["ChronologyRelation", "DateToken", "MONTH_YEAR_RE", "MONTHS", "chronology_findings_in", "chronology_relations", "date_in_aside", "month_index"]

_MONTH_NAMES = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTHS = {m.lower(): i for i, m in enumerate(_MONTH_NAMES.split("|"), start=1)}
#: 'July 1932', '18 June 1815', 'January 30, 1933' -> (month, year)
MONTH_YEAR_RE = re.compile(rf"\b(?:\d{{1,2}}\s+)?({_MONTH_NAMES})\s+(?:\d{{1,2}},?\s+)?(1[0-9]{{3}}|20[0-9]{{2}})\b")
#: A month with no year after a preposition ('in March', 'by late March'); 'May' as a modal does not qualify.
_BARE_MONTH_RE = re.compile(
    rf"\b(?:in|by|on|of|until|till|during|from|to|since|that|early|late|mid)\s+(?:(?:early|late|mid)[\s-]+)?({_MONTH_NAMES})\b(?!\s*\d)"
)
_CUE_RE = re.compile(r"(?<![\w-])(?P<cue>after|before|followed by|preceded by|followed|preceded)\b(?![-\w])(?!\s+(?:all|long)\b)", re.IGNORECASE)
#: 'named after', 'modelled after', 'look after', 'take after': not an ordering.
_NOT_A_CUE_BEFORE_RE = re.compile(r"\b(?:named|modelled|modeled|look(?:s|ed|ing)?|called|take[sn]?|took|taking|chase[sd]?|pattern(?:ed)?|styled|sought|seek(?:s|ing)?|run|ran|running|go(?:es|ing)?|went)\s+$", re.IGNORECASE)
_CLAUSE_BREAK_RE = re.compile(r";|:|,\s+(?:and|but|while|whereas|yet|so)\b|\b(?:but|while|whereas)\b", re.IGNORECASE)
_RELATIVE_CLAUSE_RE = re.compile(r"\b(?:which|who|whom|whose|that)\b", re.IGNORECASE)
_RELATIVE_START_RE = re.compile(r"^\s*(?:which|who|whom|whose|that)\b", re.IGNORECASE)
#: A comma-delimited aside that opens with a bare participle: ', founded in January 1919,' / ', fought on 18 June 1815,'.
_PARTICIPLE_OPENER_RE = re.compile(r"^\s*(?:founded|established|created|formed|born|signed|elected|appointed|published|written|dissolved|launched|begun|held|fought|passed|issued|convened|concluded|proclaimed|announced|set up)\b", re.IGNORECASE)
#: Verbs that denote the subject's own occurrence: the aside's date is then the subject's date.
_EVENT_VERB_RE = re.compile(
    r"\b(?:met|convened|sat|came|happened|occurred|took place|opened|began|started|ended|closed|lasted|broke out|erupted"
    r"|(?:was|were|had been|having been|being)?\s*(?:held|fought|signed|concluded|passed|issued|published|announced|proclaimed|convened|called|staged|delivered))\b"
    r"|^\s*(?:held|fought|signed|concluded|passed|issued|published|announced|proclaimed|convened|staged|delivered)\b",
    re.IGNORECASE,
)
#: An occurrence verb right before the cue makes the subject itself the ordered event.
_OCCURRENCE_BEFORE_CUE_RE = re.compile(r"\b(?:came|happened|occurred|took place|arrived|fell|rose|began|ended|followed|was held|were held|was fought|were fought)\s+(?:only\s+|shortly\s+|soon\s+|immediately\s+|long\s+|just\s+|well\s+|not long\s+)?$", re.IGNORECASE)
#: What may stand between a clause break and a leading cue: nothing, or a conjunction/adverb.
_LEAD_OK_RE = re.compile(r"^(?:(?:and|but|yet|so|then|only|shortly|soon|immediately|long|just|even|not long|which|and only|but only)\s*)*$", re.IGNORECASE)


@dataclass(frozen=True)
class DateToken:
    start: int
    end: int
    text: str
    month: int
    year: Optional[int]       # None for a bare month

    def index(self, year: Optional[int] = None) -> int:
        y = self.year if self.year is not None else year
        assert y is not None
        return y * 12 + self.month


@dataclass(frozen=True)
class ChronologyRelation:
    """One ordering a sentence asserts: the event named ``later_text`` came after ``earlier_text``."""
    cue: str
    later_text: str
    earlier_text: str
    later: Optional[int]      # year*12+month when decided
    earlier: Optional[int]
    decided: bool
    reason: str = ""          # why the relation is undecided, or how a bare month was read
    sentence: str = ""

    @property
    def violated(self) -> bool:
        return self.decided and self.later is not None and self.earlier is not None and self.later <= self.earlier


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


def _tokens(text: str) -> list[DateToken]:
    out: list[DateToken] = []
    for m in MONTH_YEAR_RE.finditer(text):
        out.append(DateToken(m.start(), m.end(), m.group(0), MONTHS[m.group(1).lower()], int(m.group(2))))
    covered = [(t.start, t.end) for t in out]
    for m in _BARE_MONTH_RE.finditer(text):
        s, e = m.start(1), m.end(1)
        if any(a <= s < b for a, b in covered):
            continue
        out.append(DateToken(s, e, m.group(1), MONTHS[m.group(1).lower()], None))
    out.sort(key=lambda t: t.start)
    return out


def _orient(cue: str, left: DateToken, right: DateToken) -> tuple[DateToken, DateToken]:
    """(later, earlier) for the standard shape: 'X after Y', 'X followed Y', 'X preceded by Y' put X later."""
    if cue in ("after", "followed", "preceded by"):
        return left, right
    return right, left


def _resolve(cue: str, later: DateToken, earlier: DateToken, sentence: str) -> ChronologyRelation:
    if later.year is not None and earlier.year is not None:
        return ChronologyRelation(cue, later.text, earlier.text, later.index(), earlier.index(), True, "", sentence)
    if later.year is None and earlier.year is None:
        return ChronologyRelation(cue, later.text, earlier.text, None, None, False, f"neither '{later.text}' nor '{earlier.text}' carries a year", sentence)
    year = later.year if later.year is not None else earlier.year
    a, b = later.index(year), earlier.index(year)
    bare = later if later.year is None else earlier
    if a > b:
        return ChronologyRelation(cue, f"{later.text}{'' if later.year is not None else f' {year}'}", f"{earlier.text}{'' if earlier.year is not None else f' {year}'}", a, b, True,
                                  f"the year {year} of the dated side was carried to '{bare.text}'; any later year satisfies the stated order too", sentence)
    return ChronologyRelation(cue, later.text, earlier.text, None, None, False,
                              f"the year of '{bare.text}' is not stated: read in {year} the order fails, read in an adjacent year it holds", sentence)


def chronology_relations(sentence: str) -> list[ChronologyRelation]:
    """Every dated ordering the sentence asserts (see the module docstring)."""
    out: list[ChronologyRelation] = []
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
            out.append(_resolve(cue, later, earlier, sentence))
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
        out.append(_resolve(cue, later, earlier, sentence))
    return out


def chronology_findings_in(sentence: str) -> Optional[tuple[int, int]]:
    """The first decided relation of ``sentence`` whose dates violate the stated order, as
    ``(later_as_stated, earlier_as_stated)`` month indices; ``None`` when every decided
    relation holds or nothing could be paired. Structural proxy for ``HI-CHR-001``."""
    for rel in chronology_relations(sentence):
        if rel.violated:
            return rel.later, rel.earlier  # type: ignore[return-value]
    return None
