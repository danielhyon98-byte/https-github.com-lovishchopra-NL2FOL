"""What counts as citing the supplied texts, for the request constraint ``must_cite_supplied_text`` (INT-REQ-005).

Before the round-8 clearance (c1, breadth findings F13/F14) the constraint was satisfied only by a quotation: a claim had
to carry a source reference, which the parsers create from quotation marks alone. An answer that cites as it was asked to
cite was charged INT-REQ-005 (error, "no claim carries a source reference"): "Cite the text by paragraph and the data by
table" answered with "(paragraph 1)" and "(Table 1)", "Quote figures from the table" answered with the table's figures,
"Quote my code exactly" answered with the student's code in backticks.

The evidence read here, each resolved against the supplied texts (never counted on the answer's word alone):

* a **locator** ("paragraph 2", "(para. 3)", "Table 1", "Figure 2", "line 12", "lines 3-5", "stanza 2", "Source A",
  "Extract B", "Document 2", "section 3"): a paragraph, line or stanza number the supplied texts have (a "Paragraph 2"
  heading, or at least that many paragraphs, lines or stanzas), or a table, figure, source or extract the supplied texts
  name ("Table 1 shows ...") or hold (the one table of a text answers "Table 1");
* **figures from a supplied table**: at least two distinct figures of the answer (not one-digit whole numbers) that are
  cells of a table in a supplied text (rows with "|" or tab separators);
* **quoted code**: a code span in backticks whose content (white space folded) occurs in a supplied text.

A request that asks for quotations ("quote", "quotations") is satisfied by quotations, table figures and quoted code, not
by bare locators; one that asks for citations ("cite", "refer to the text", "textual evidence") by any of them. Every
reader is linear in its input (no nested or adjacent unbounded runs) and bounded in the evidence it collects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Sequence

from ..translate.contracts import SuppliedText

__all__ = ["CitationEvidence", "citation_evidence", "locators_in", "table_cells", "code_spans"]

#: A locator of a supplied text: its kind and its label (a number, or one capital letter for a source or an extract).
_LOCATOR_RE = re.compile(
    r"(?<![\w])(?P<kind>paragraphs?|paras?\.?|tables?|figures?|figs?\.|lines?|ll?\.|stanzas?|sections?|sources?|extracts?|documents?"
    r"|passages?|texts?|appendix|appendices)[ \t]{0,3}\(?(?P<label>[0-9]{1,3}|[A-H])(?![\w])", re.IGNORECASE)
#: The kinds a locator names, by their singular stem.
_KIND = {"paragraph": "paragraph", "para": "paragraph", "table": "table", "figure": "figure", "fig": "figure", "line": "line", "l": "line",
         "ll": "line", "stanza": "stanza", "section": "section", "source": "source", "extract": "extract", "document": "document",
         "passage": "passage", "text": "text", "appendix": "appendix", "appendice": "appendix"}
#: A figure of the answer or of a table cell (thousands separators allowed, a decimal part, a sign).
_FIGURE_RE = re.compile(r"(?<![\w.,])[-+−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\w])|(?<![\w.,])[-+−]?\d+(?:\.\d+)?(?![\w])")
#: An inline code span: one backtick, at most 500 characters on one line, one backtick.
_CODE_SPAN_RE = re.compile(r"`([^`\n]{1,500})`")
#: At most this many locators, figures or code spans are read from one answer (the evidence needs only one or two).
MAX_EVIDENCE_READ = 256


@dataclass(frozen=True)
class CitationEvidence:
    """What made an answer cite the supplied texts: the kind of evidence and the spans that show it."""
    kind: str                      # "locator" | "table_figures" | "code"
    shown: tuple[str, ...]
    document_ids: tuple[str, ...]

    def describe(self) -> str:
        what = {"locator": "cites the supplied texts by locator", "table_figures": "states figures from a supplied table",
                "code": "quotes the supplied code"}[self.kind]
        return f"{what}: {', '.join(repr(s) for s in self.shown[:4])} (in {', '.join(self.document_ids[:3])})"


def _norm_figure(text: str) -> str:
    return text.replace(",", "").replace("−", "-").lstrip("+")


def _blank_runs(text: str) -> tuple[int, int]:
    """``(paragraphs, lines)`` of a supplied text: blocks of non-blank lines separated by blank lines, and non-blank lines."""
    paragraphs = lines = 0
    blank = True
    for line in text.split("\n"):
        if line.strip():
            lines += 1
            if blank:
                paragraphs += 1
            blank = False
        else:
            blank = True
    return paragraphs, lines


def locators_in(text: str) -> list[tuple[str, str, str]]:
    """``(kind, label, span)`` for every locator of ``text`` (at most :data:`MAX_EVIDENCE_READ`)."""
    out: list[tuple[str, str, str]] = []
    for m in _LOCATOR_RE.finditer(text):
        word = m.group("kind").lower().rstrip(".")
        stem = word[:-1] if word.endswith("s") and word[:-1] in _KIND else word
        kind = _KIND.get(stem) or _KIND.get(word)
        if kind is None:
            continue
        label = m.group("label")
        if kind in ("paragraph", "line", "stanza", "table", "figure", "section", "appendix") and not label.isdigit() and kind not in ("appendix",):
            continue  # "paragraph A" is no locator; a table or figure is numbered
        if kind in ("text", "document", "passage", "source", "extract") and m.group("kind")[0].islower() and not label.isdigit():
            continue  # "the text A ..." is prose; a named source is written with a capital ("Source A", "Text B")
        out.append((kind, label, m.group(0)))
        if len(out) >= MAX_EVIDENCE_READ:
            break
    return out


def table_cells(text: str) -> set[str]:
    """The figures that are cells of a table in ``text``: rows holding at least two "|" separators or a tab."""
    cells: set[str] = set()
    for line in text.split("\n"):
        if line.count("|") >= 2:
            parts = line.split("|")
        elif "\t" in line:
            parts = line.split("\t")
        else:
            continue
        for part in parts:
            p = part.strip().rstrip("%").strip()
            m = _FIGURE_RE.fullmatch(p)
            if m is not None:
                cells.add(_norm_figure(p))
    return cells


def code_spans(text: str) -> list[str]:
    """The inline code spans of ``text`` (backticks), white space folded (at most :data:`MAX_EVIDENCE_READ`)."""
    out: list[str] = []
    for m in _CODE_SPAN_RE.finditer(text):
        body = " ".join(m.group(1).split())
        if sum(1 for ch in body if not ch.isspace()) >= 3:
            out.append(body)
            if len(out) >= MAX_EVIDENCE_READ:
                break
    return out


@dataclass(frozen=True)
class _TextFacts:
    """What one supplied text holds for resolving a locator, read once (linear in the text)."""
    document_id: str
    named: frozenset[tuple[str, str]]   # (kind, label) the text or its title names ("Table 1 shows ...", a "Paragraph 2" heading)
    paragraphs: int
    lines: int
    has_table: bool


def _facts(t: SuppliedText) -> _TextFacts:
    body = t.text or ""
    named: set[tuple[str, str]] = set()
    for source in (body, t.title or ""):
        for m in _LOCATOR_RE.finditer(source):
            word = m.group("kind").lower().rstrip(".")
            stem = word[:-1] if word.endswith("s") and word[:-1] in _KIND else word
            kind = _KIND.get(stem) or _KIND.get(word)
            if kind is not None:
                named.add((kind, m.group("label").upper()))
    paragraphs, lines = _blank_runs(body)
    return _TextFacts(t.document_id, frozenset(named), paragraphs, lines, bool(table_cells(body)))


def _resolved(kind: str, label: str, facts: Sequence[_TextFacts]) -> Optional[str]:
    """The id of a supplied text the locator resolves against, or None."""
    for f in facts:
        if (kind, label.upper()) in f.named:
            return f.document_id
        if label.isdigit():
            n = int(label)
            if kind in ("paragraph", "stanza") and 1 <= n <= f.paragraphs:
                return f.document_id
            if kind == "line" and 1 <= n <= f.lines:
                return f.document_id
            if kind == "table" and n == 1 and f.has_table:
                return f.document_id
    return None


def citation_evidence(answer: str, texts: Sequence[SuppliedText], *, quotation_asked: bool) -> Optional[CitationEvidence]:
    """The evidence that ``answer`` cites the supplied ``texts`` other than a quotation a claim carries, or None. With
    ``quotation_asked`` (the request asked to quote) a bare locator is no quotation and does not count."""
    if not texts or not answer:
        return None
    if not quotation_asked:
        found: list[tuple[str, str]] = []
        facts = [_facts(t) for t in texts]
        for kind, label, span in locators_in(answer):
            doc = _resolved(kind, label, facts)
            if doc is not None:
                found.append((span.strip(), doc))
        if found:
            return CitationEvidence("locator", tuple(dict.fromkeys(s for s, _d in found)), tuple(dict.fromkeys(d for _s, d in found)))
    for t in texts:
        cells = table_cells(t.text or "")
        if not cells:
            continue
        stated: list[str] = []
        for i, m in enumerate(_FIGURE_RE.finditer(answer)):
            if i >= MAX_EVIDENCE_READ * 4:
                break
            fig = _norm_figure(m.group(0))
            if len(fig.lstrip("-").replace(".", "")) < 2:
                continue  # a one-digit whole number is no evidence of a table
            if fig in cells and fig not in stated:
                stated.append(fig)
        if len(stated) >= 2:
            return CitationEvidence("table_figures", tuple(stated), (t.document_id,))
    spans = code_spans(answer)
    if spans:
        folded = [(t.document_id, " ".join((t.text or "").split())) for t in texts]
        for span in spans:
            for doc_id, body in folded:
                if span in body:
                    return CitationEvidence("code", (span,), (doc_id,))
    return None
