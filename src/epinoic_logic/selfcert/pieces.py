"""Segmentation for the self-certification reader (design section 3.1, rules S1 to S4), and the helpers moved here from
``adapters.self_report`` unchanged in meaning: the report's own fields (:func:`report_texts`), rule ``model-marks``
(:func:`model_mark_ranges`, :func:`blank_model_marks`) and :func:`quotation_only`.

Every transformation keeps the text's LENGTH (markup, heading, list and emphasis marks become blanks; a block tag becomes a
line break), so a piece is a span of one work string and a hit's offsets map back to the original text through the fold map.
Each character belongs to at most five pieces (the text, its paragraph, its line or table cell, a bracket, a quotation), so the
segmentation is linear.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

__all__ = ["work_string", "pieces", "sentence_spans", "report_texts", "model_mark_ranges", "blank_model_marks", "MODEL_MARKS_RULE",
           "quotation_only", "PLATFORM_NOTE_RE"]

# ---------------------------------------------------------------------------------------------------------------- markup
#: HTML tags as the student never sees them (attributes only in name=value form, so "a<b and c>d" is no tag).
_HTML_TAG_NAMES = (r"(?:details|summary|sub|sup|q|blockquote|p|div|span|br|hr|li|ul|ol|em|strong|b|i|u|small|mark|code|pre|kbd|samp|h[1-6]|table"
                   r"|thead|tbody|tfoot|tr|td|th|caption|section|aside|article|header|footer|figure|figcaption|cite|abbr|del|ins|s|font|center|a|img"
                   r"|dl|dt|dd|label|nav|main)")
_MARKUP_TAG_RE = re.compile(rf"</?(?P<name>{_HTML_TAG_NAMES})(?:\s+[\w:-]{{1,30}}\s*=\s*(?:\"[^\"<>]{{0,200}}\"|'[^'<>]{{0,200}}'|[^\s\"'<>=]{{1,200}})){{0,8}}"
                            r"(?:\s+open)?\s*/?>", re.IGNORECASE)
_BLOCK_TAG_NAMES = frozenset("details summary blockquote p div br hr li ul ol h1 h2 h3 h4 h5 h6 table thead tbody tfoot tr td th caption section aside "
                             "article header footer figure figcaption pre dl dt dd nav main".split())


def work_string(text: str) -> str:
    """``text`` (already folded) as the student sees it, with its length kept: HTML tags blanked (a block tag ends a line, <q> is a
    quotation mark), heading, quote and list marks at a line's start blanked, emphasis marks blanked. (A checklist box "[x]" is read
    as a check mark before folding: :func:`epinoic_logic.selfcert.reader.read`.)"""
    s = text
    if "<" in s:
        def sub(m: "re.Match") -> str:
            name = m.group("name").lower()
            n = len(m.group(0))
            if name == "q":
                return ("”" if m.group(0).startswith("</") else "“") + " " * (n - 1)
            return ("\n" + " " * (n - 1)) if name in _BLOCK_TAG_NAMES else " " * n
        s = _MARKUP_TAG_RE.sub(sub, s)
    out = list(s)
    n = len(out)
    # line-start marks: '#', '>', list bullets and numbers
    i = 0
    at_line_start = True
    while i < n:
        c = out[i]
        if c == "\n":
            at_line_start = True
            i += 1
            continue
        if at_line_start:
            j = i
            while j < n and out[j] in " \t":
                j += 1
            k = j
            while k < n and k - j < 6 and out[k] in "#>":
                k += 1
            if k == j and k < n and out[k] in "-*+•" and k + 1 < n and out[k + 1] in " \t":
                k += 1
            if k > j and k < n and out[k] in " \t":
                for x in range(j, k):
                    out[x] = " "
            at_line_start = False
        i += 1
    s = "".join(out)
    # emphasis marks
    s = re.sub(r"\*{1,3}|_{2,3}|`+|~~", lambda m: " " * len(m.group(0)), s)
    return s


# ---------------------------------------------------------------------------------------------------------------- pieces
_BRACKETS = {"(": ")", "[": "]", "<": ">", "{": "}"}


def _bracket_spans(s: str, a: int, b: int) -> list[tuple[int, int]]:
    """The inner spans of the brackets of ``s[a:b]`` (depth at most three; deeper is read flat). One pass."""
    out: list[tuple[int, int]] = []
    stack: list[tuple[str, int]] = []
    for i in range(a, b):
        c = s[i]
        if c in _BRACKETS:
            if c == "<" and not (i + 1 < b and (s[i + 1].isalpha() or s[i + 1] == " ")):
                continue
            if len(stack) < 3:
                stack.append((c, i))
        elif stack and (c == _BRACKETS[stack[-1][0]] or (c in ")]" and _BRACKETS[stack[-1][0]] in ")]")):
            # a round bracket closed by a square one (or the reverse) is still a bracket: "(verified]"
            _o, j = stack.pop()
            if i - j > 1:
                out.append((j + 1, i))
        elif c == "\n" and (s[i + 1:i + 2] == "\n" or "\n" in s[i + 1:i + 4].lstrip(" \t")[:1]):
            stack.clear()  # a blank line closes every bracket (a single line break inside one does not)
    return out


def pieces(s: str) -> list[tuple[int, int, str]]:
    """``(start, end, kind)`` of each piece of the work string ``s`` read on its own and inside its host: the text, each blank-line
    paragraph, each line, each table cell, each bracket. Duplicate spans are read once."""
    n = len(s)
    out: list[tuple[int, int, str]] = [(0, n, "text")]
    seen = {(0, n)}

    def add(a: int, b: int, kind: str) -> None:
        while a < b and s[a] in " \t\n":
            a += 1
        while b > a and s[b - 1] in " \t\n":
            b -= 1
        if b - a < 1 or (a, b) in seen:
            return
        seen.add((a, b))
        out.append((a, b, kind))

    # paragraphs: runs of non-blank lines
    a = 0
    par_start = None
    par_end = 0
    paragraphs: list[tuple[int, int]] = []
    for line in s.split("\n"):
        b = a + len(line)
        if line.strip():
            if par_start is None:
                par_start = a
            par_end = b
        elif par_start is not None:
            paragraphs.append((par_start, par_end))
            par_start = None
        a = b + 1
    if par_start is not None:
        paragraphs.append((par_start, par_end))
    for pa, pb in paragraphs:
        add(pa, pb, "paragraph")
    # lines and cells
    a = 0
    for line in s.split("\n"):
        b = a + len(line)
        add(a, b, "line")
        if line.count("|") >= 2 and (line.lstrip().startswith("|") or not _ABS_BARS.search(line)):
            c0 = a
            for cell in line.split("|"):
                c1 = c0 + len(cell)
                if cell.strip() and cell.strip("-: "):
                    add(c0, c1, "cell")
                c0 = c1 + 1
        a = b + 1
    # brackets, within a paragraph (a line break inside a bracket keeps it: "(verified\n)")
    for pa, pb in paragraphs:
        for x, y in _bracket_spans(s, pa, pb):
            add(x, y, "bracket")
    return out


#: An absolute-value bar pair inside a line of prose or working ("|experimental − accepted| ÷ accepted"): the bars hug their
#: content, unlike the spaced bars of a table row, which a row also starts with.
_ABS_BARS = re.compile(r"(?:^|[\s(=])\|[^|\s][^|\n]{0,80}?[^|\s]\|(?=[\s).,;:÷×=+*/]|$)")


_ABBREV = frozenset("e.g i.e etc vs cf no fig figs eq eqs mr mrs ms dr st prof approx ca p pp vol ed al q.e.d u.s u.k a.d b.c n.b p.s".split())


def _status_tail(tail: str) -> bool:
    """A lone status or check word closing a line after a quotation ("... thee.' verified"): a label after the content, a piece
    of its own."""
    from .lexicon import tags
    w = tail.rstrip(".!").lower()
    return 0 < len(w) <= 24 and w.isalpha() and bool(tags(w) & {"F:STATUS", "F:CHECK", "F:OUTCOME", "F:APPROVE"})


def sentence_spans(s: str, a: int, b: int) -> list[tuple[int, int]]:
    """The sentences of ``s[a:b]`` (rule S2): split at ".", "!", "?" followed by a blank or the end, never inside a number, after
    an abbreviation or an initial, or inside a quotation; a line break inside a piece is a blank. One pass."""
    out: list[tuple[int, int]] = []
    start = a
    i = a
    depth_q = 0
    straight_end = -1  # the closing mark of a straight-quoted span ("Tested. Approved. Trusted.") inside which no sentence ends
    text_since_start = False  # whether s[start:i] holds a non-blank character (kept as a flag: stripping a growing slice of a run
    # of line breaks was quadratic)
    while i < b:
        c = s[i]
        if not text_since_start and not c.isspace():
            text_since_start = True
        if c in "“«":
            depth_q += 1
        elif c in "”»" and depth_q:
            depth_q -= 1
        elif c == '"' and i > straight_end and (i == a or s[i - 1] in " \t\n([:—–-"):
            close = s.find('"', i + 1, min(b, i + 600))  # bounded look-ahead: linear in the input
            if close > i + 1 and "\n\n" not in s[i:close]:
                straight_end = close
        elif c in "'\u2018" and i > straight_end and (i == a or s[i - 1] in " \t\n([:—–-") and i + 1 < b and (
                s[i + 1].isalnum() or (s[i + 1] == " " and s[i + 2:i + 4] == "zz")):
            # (a quotation that opens with a mark, "'✅ Fact-checked. 100% true.'", read as its reading token: attack round 5)
            # a single-quoted span ('Tested. Trusted. Proven.'): its closing mark follows a non-blank and precedes a non-letter (an
            # apostrophe inside a word, "can't", never closes it); bounded look-ahead, one line
            end = min(b, i + 300)
            k = i + 1
            while k < end and s[k] != "\n":
                if s[k] in "'\u2019" and not s[k - 1].isspace() and (k + 1 >= b or not s[k + 1].isalnum()):
                    break
                k += 1
            if k < end and s[k] in "'\u2019" and any(x in s[i:k] for x in ".!?"):
                straight_end = k
        if ((c in "'\u2019\"" and i == straight_end) or (c in "\u201d\u00bb" and depth_q == 0)) and i > start and \
                s[i - 1] in ".!?" and i + 1 < b and s[i + 1] in " \t" and depth_q == 0:
            # a quotation that closes after its own sentence end ('... vitae.' I have checked it.): the next words open a sentence of
            # their own unless they continue this one in lower case ("The slogan 'Tested. Trusted.' uses a tricolon ...")
            m = i + 1
            while m < b and m < i + 8 and s[m] in " \t":
                m += 1
            tail = s[m:min(b, m + 40)].split("\n", 1)[0].strip()
            if m < b and (not s[m].islower() or _status_tail(tail)):
                out.append((start, i + 1))
                start = i + 1
                text_since_start = False
                i += 1
                continue
        if c == "\n" and i + 1 < b and s[i + 1] in "\n" and i > start and text_since_start:
            # a blank line ends a sentence whatever closes it (a heading, a label or a line without a stop): the next
            # paragraph is never read as the same sentence ("...\n\nNext step: compare your figures with the table.")
            out.append((start, i))
            start = i
            text_since_start = False
            depth_q = 0
            i += 1
            continue
        if c in ".!?" and depth_q == 0 and i >= straight_end:
            j = i + 1
            while j < b and s[j] in ".!?”\"'»)]}":
                j += 1
            if j >= b or s[j] in " \t\n":
                # an abbreviation before the mark is no sentence end
                k = i
                while k > start and (s[k - 1].isalnum() or s[k - 1] == "."):
                    k -= 1
                if c == "." and s[k:i].lower() in _ABBREV:
                    i = j
                    continue
                out.append((start, j))
                start = j
                text_since_start = False
                i = j
                continue
            i = j  # a run of marks is read once (a rescan from each mark was quadratic on a run of stops)
            continue
        i += 1
    if start < b and s[start:b].strip():
        out.append((start, b))
    return [(x, y) for x, y in out if s[x:y].strip()]


# ---------------------------------------------------------------------------------------------------------------- rule model-marks
#: Rule ``model-marks`` (round-10 clearance c3; the Physics knowledge base's rule S26): in a line opened by a model or markscheme
#: lead, a check-mark run that closes a marking point holding no checking, correctness or defect word and no self-certification is a
#: mark annotation, not a verification label. Moved here from ``adapters.self_report`` unchanged in meaning; the point is read with
#: the one reader.
MODEL_MARKS_RULE = "model-marks"
_MODEL_LEAD_RE = re.compile(
    r"[ \t>*_#-]{0,8}(?:(?:a|an|the)[ \t]{1,3})?(?:model(?:[ \t]{1,3}(?:answers?|responses?|paragraphs?|sentences?|lines?|working|explanations?|solutions?))?"
    r"|mark[ \t]?schemes?|marking[ \t]{1,3}points?|mark[ \t]{1,3}points?|exemplar(?:[ \t]{1,3}answers?)?)"
    r"[ \t]{0,3}(?:\([^()\n]{0,200}\)[ \t]{0,3})?[*_]{0,2}[ \t]{0,3}:", re.IGNORECASE)
_MARK_RUN_RE = re.compile(r"(?<![✓✔☑])(?:[✓✔☑]️?)++")
_MARK_POINT_CHECK_RE = re.compile(r"\b(?:check\w*|verif\w*|confirm\w*|validat\w*|audit\w*|proof|proved|proven|correct\w*|accura\w*|errors?|mistakes?"
                                  r"|passed|approved|certif\w*|qed|vetted|reviewed|tested)\b", re.IGNORECASE)
_MODEL_LINE_MAX = 4000


def model_mark_ranges(text: str) -> list[tuple[int, int]]:
    """Rule ``model-marks``: the offsets of the check-mark runs of ``text`` that are mark annotations (with the blanks before each).
    One pass over the lines; a line over 4,000 characters keeps its marks (they stay labels)."""
    if not isinstance(text, str) or not any(ch in text for ch in "✓✔☑"):
        return []
    from . import is_self_certification
    out: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        if len(line) > _MODEL_LINE_MAX or not any(ch in line for ch in "✓✔☑"):
            continue
        lead = _MODEL_LEAD_RE.match(line)
        if lead is None:
            continue
        at = lead.end()
        for m in _MARK_RUN_RE.finditer(line, at):
            point = line[at:m.start()]
            at = m.end()
            if not point.strip(" \t.;,") or _MARK_POINT_CHECK_RE.search(point) or is_self_certification(point):
                continue
            a = m.start()
            while a > 0 and line[a - 1] in " \t" and len(point) - (m.start() - a) > 0:
                a -= 1
            out.append((start + a, start + m.end()))
    return out


def blank_model_marks(text: str) -> str:
    """``text`` with the mark annotations of rule ``model-marks`` blanked character for character (length kept)."""
    ranges = model_mark_ranges(text)
    if not ranges:
        return text
    chars = list(text)
    for a, b in ranges:
        chars[a:b] = " " * (b - a)
    return "".join(chars)


# ---------------------------------------------------------------------------------------------------------------- quotations
def quotation_only(text: str) -> bool:
    """Whether ``text`` (a claim) is nothing but one quotation, its marks included: a quotation a parser drew out of a sentence as
    evidence, read in that sentence (where its attribution stands), never alone."""
    from ..adapters.markdown import find_quotation_spans
    t = (text or "").strip()
    if len(t) < 3:
        return False
    spans = find_quotation_spans(t)
    return len(spans) == 1 and spans[0][0] == 0 and t[spans[0][1]:].strip(" .,;:!?") == ""


# ---------------------------------------------------------------------------------------------------------------- report fields
#: The opening words of the notes the platform's own parsers and adapters write into a report's fields. Never trusted on their
#: own (attack round 3): a field is the platform's note only by its whole shape (:data:`_PLATFORM_NOTE_SHAPES`); a field that
#: opens with these words and has no such shape is the specialist's, and the words after the opening are read on their own too.
PLATFORM_NOTE_RE = re.compile(
    r"^(?:\d+ (?:claims|sentences) beyond the report's claim limit \(\d+\) were merged into claim \S+ and were not individually roled or checked"
    r"|no supplied text was given: quotations could not be attributed to a document$"
    r"|the answer contains meta-text \(a check label, a narrated step or a pasted receipt\); it was excluded from the argument$"
    r"|the answer contains note paragraphs \(a from-memory label, a task note or self-certification\); their sentences are roled 'other' and are not material$"
    r"|paragraph \d+: the sentence '.{0,120}' certifies the answer's own verification or imitates a receipt; it was roled 'other'"
    r"|paragraph \d+: \d+ sentence\(s\) carrying verification-status language were roled other and count as no material claim; "
    r"|paragraph\(s\) [\d, ]+ carry an unbalanced quotation mark; "
    r"|the answer holds no prose sentence \(only a pasted JSON fragment or markup\); "
    r"|the STEM front end produced no statements \("
    r"|supplied_texts were provided by the agent, not by the platform; quotations were checked against the agent's own texts$"
    r"|quotation with no supplied text to check it against: "
    r"|inline label recorded, not part of the claim: "
    r"|\d+ statement\(s\) carrying verification-status language were roled other and count as no material claim: "
    r"|the sentence attributes this view to a peer specialist; "
    r"|the statement has an unbalanced quotation mark; "
    r"|a quotation mark in this sentence cannot be paired; "
    r"|the sentence carries a verification-status label or self-certification inline \("
    r"|the sentence carries the method's own label inline \("
    r"|\d+ quotation\(s\) of the merged claims are carried as this claim's source references"
    r"|\d+ further quotation\(s\) of the merged claims could not be carried"
    r"|numeric relations of this statement are decided by the STEM pack checks "
    r"|the answer's list of sources: provenance meta-text, not a claim of the answer"
    r"|the quotation is a label relayed in a note, not evidence for the argument"
    r"|the writer's own (?:model sentence|invented example), "
    r"|claims were proposed from prose by the [\w-]+ adapter's deterministic text rules; "
    r"|a quoted span \(double marks of any kind, or single marks around two or more words\) is treated as a quotation of the supplied text; "
    r"|headings, bullet lists and meta-text blocks \(labels such as 'VERIFIED:', pasted receipts\) propose no argument claims; "
    r"|the answer's own note \([\w.@-]{1,60}\) says its sources do not confirm the figure "
    r"|paragraph \d+ is nothing but notes and verification-status language; "
    r"|\d+ line\(s\) of the answer were not joined to the line before them"
    r"|paragraph \d+ holds text the self-certification reader cannot read)", re.DOTALL)


def _field(obj, name: str):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _opening_mark(c: str) -> bool:
    """Whether ``c`` can open a quotation in any convention: the ASCII and fullwidth quotes, every initial or final quote mark
    (“ ” ‘ ’ « » ‹ › „ ‚, which open quotations in one language or another: attack round 6) and the CJK corner brackets."""
    return c in "\"'\uff02\u300c\u300e\u301d\u275d\u275b\u201e\u201a" or unicodedata.category(c) in ("Pi", "Pf")


def _bare_copy(flat: str, written: str) -> bool:
    """Whether ``flat`` stands in the response ``written`` as the response's own words at least once, not only inside quotation
    marks (a sentence the response quotes from an outside party is masked there; a field stating it bare is the specialist's own)."""
    at = written.find(flat)
    n = 0
    while at >= 0 and n < 64:
        before = written[max(0, at - 2):at].strip()
        if not before or not _opening_mark(before[-1]):
            return True
        at = written.find(flat, at + 1)
        n += 1
    return False


#: The full shapes of the notes the platform's parsers write (attack round 3, paths p12/p13): a field is the platform's own
#: note only when the WHOLE of it has one of these shapes, never because it opens with a note's words (a specialist could
#: write "quotation with no supplied text to check it against: This answer has been verified ..." itself). The named
#: groups ``q<n>`` hold words a parser copied from the response: each is read unless it stands in the response as written
#: (the response is read already); ``r<n>`` holds a reason text the platform's STEM front end wrote, read like any text.
_IDS = r"\[(?:[\w.@:/-]+(?:, [\w.@:/-]+)*)?\]"
_CID = r"[\w.@-]{1,60}"
_PLATFORM_NOTE_SHAPES = tuple(re.compile(x, re.DOTALL) for x in (
    r"\d+ (?:claims|sentences) beyond the report's claim limit \(\d+\) were merged into claim \S+ and were not individually roled or checked",
    r"no supplied text was given: quotations could not be attributed to a document",
    r"the answer contains meta-text \(a check label, a narrated step or a pasted receipt\); it was excluded from the argument",
    r"the answer contains note paragraphs \(a from-memory label, a task note or self-certification\); their sentences are roled 'other' and are not material",
    r"paragraph \d+: the sentence '(?P<q0>.{0,120})' certifies the answer's own verification or imitates a receipt; it was roled 'other' and is "
    r"not material, while the paragraph's other sentences keep their roles",
    r"paragraph \d+: \d+ sentence\(s\) carrying verification-status language were roled other and count as no material claim; the other "
    r"sentences of the paragraph keep their roles: (?P<l0>.*)",
    r"paragraph\(s\) [\d, ]+ carry an unbalanced quotation mark; the span it opens or closes was recorded as an undelimited quotation and not "
    r"checked against any text",
    r"the answer holds no prose sentence \(only a pasted JSON fragment or markup\); it was kept whole as one 'other' claim, which is not material",
    r"the STEM front end produced no statements \((?P<r0>.*)\); each paragraph was kept as one claim and its relations were not read",
    r"supplied_texts were provided by the agent, not by the platform; quotations were checked against the agent's own texts",
    r'quotation with no supplied text to check it against: "(?P<q0>.{0,200})"(?: \((?:the sentence says the text lacks these words, a mention '
    r"of a word rather than a quotation, and they occur in none of " + _IDS + r"|the sentence judges these words true or false as a statement, "
    r"or tells the reader to reply with them: a mention of words rather than a quotation, and they occur in none of " + _IDS +
    r"|the sentence names (?:no supplied text|several supplied texts \(" + _CID + r"(?:, " + _CID + r")*\)) and the words occur in none of "
    + _IDS + r")\))?",
    r"inline label recorded, not part of the claim: (?P<q0>.{0,200})",
    r"\d+ statement\(s\) carrying verification-status language were roled other and count as no material claim: (?P<l0>.*)",
    r"the sentence attributes this view to a peer specialist; it is the colleague's claim, not the (?:English|History) specialist's own, and "
    r"its certainty is capped at 'probable'",
    r"the (?:statement|sentence) has an unbalanced quotation mark; the span it opens or closes was not treated as a quotation and was not checked",
    r"a quotation mark in this sentence cannot be paired; the span '(?P<q0>.{0,120})' was not delimited, was attributed to no text and was not checked",
    r"the sentence carries a verification-status label or self-certification inline \('(?P<q0>.{0,200})'\): an agent self-report, advisory "
    r"and ignored; it is kept out of the claim's role, is no evidence of a check, and the claim's certainty is capped at 'probable' as under "
    r"any inline label",
    r"the sentence carries the method's own label inline \('(?P<q0>.{0,200})'\); the label is kept out of the claim's role and (?:is not part "
    r"of the argument|its dated items are from memory)",
    r"\d+ quotation\(s\) of the merged claims are carried as this claim's source references so the hub still checks them",
    r"\d+ further quotation\(s\) of the merged claims could not be carried and were not checked",
    r"numeric relations of this statement are decided by the STEM pack checks " + _CID + r"(?:, " + _CID + r")*",
    r"the answer's list of sources: provenance meta-text, not a claim of the answer; it counts toward no bound",
    r"the quotation is a label relayed in a note, not evidence for the argument; it supports no claim",
    r"claims were proposed from prose by the [\w-]+ adapter's deterministic text rules; roles, links and certainty are parser proposals, not "
    r"agent assertions",
    r"a quoted span \(double marks of any kind, or single marks around two or more words\) is treated as a quotation of the supplied text; "
    r"sentence punctuation inside the closing mark is not part of the recorded excerpt",
    r"headings, bullet lists and meta-text blocks \(labels such as 'VERIFIED:', pasted receipts\) propose no argument claims; quotations "
    r"inside lists are still recorded as evidence",
    r"the answer's own note \(" + _CID + r"\) says its sources do not confirm the figure '(?P<q0>.{0,60})': the figure is the specialist's "
    r"estimate, not a confirmed one",
    r"paragraph \d+ is nothing but notes and verification-status language; the whole paragraph was treated as a note and none of its "
    r"sentences counts as material",
    r"\d+ line\(s\) of the answer were not joined to the line before them: deciding the join would have read the logical line before them "
    r"again beyond the parser's reading bound \(\d+ characters per character of the answer and [\d,]+ more\), so each opens a claim of its own",
))
#: One item of a list of demoted sentences in a platform note ("sentence 2 ('...')" or "<claim id> ('...')", joined by "; ",
#: the list cut at 600 characters).
_NOTE_ITEM_RE = re.compile(r"(?:sentence \d+|" + _CID + r") \('(?P<q>.*?)'\)(?:; |$)", re.DOTALL)
_NOTE_ITEM_CUT_RE = re.compile(r"(?:sentence \d+|" + _CID + r") \('(?P<q>.*)", re.DOTALL)


def _platform_note_slots(flat: str) -> Optional[list[str]]:
    """The slots of ``flat`` when the whole of it has the shape of a platform note (:data:`_PLATFORM_NOTE_SHAPES`): the texts a
    parser copied into it (to be compared with the response) and the reasons the platform wrote (to be read); None when it has
    no such shape, so it is the specialist's own words and is read whole."""
    if not flat:
        return None
    for rx in _PLATFORM_NOTE_SHAPES:
        m = rx.fullmatch(flat)
        if m is None:
            continue
        slots = [v for k, v in m.groupdict().items() if v and k[0] in "qr"]
        lst = m.groupdict().get("l0")
        if lst:
            at = 0
            for it in _NOTE_ITEM_RE.finditer(lst):
                if it.start() != at:
                    break
                slots.append(it.group("q"))
                at = it.end()
            if at < len(lst):
                cut = _NOTE_ITEM_CUT_RE.fullmatch(lst, at)
                if cut is None:
                    return None
                slots.append(cut.group("q"))
        return slots
    return None


def report_texts(report) -> list[tuple[str, Optional[str], str]]:
    """``(where, claim id or None, text)`` for each text of a specialist report, other than its response and its claims' texts,
    that is the specialist's own: the report's assumptions and unresolved issues, and each claim's assumptions and assessment
    criteria. A field whose whole text has the shape of a note the platform's own parsers write (:data:`_PLATFORM_NOTE_SHAPES`;
    never judged by its opening words alone) is the platform's, and only the words it carries that are not the response's own
    are read; a field whose words are a copy of the response's own is not read again (the response is read as written already);
    a note "<lead>: <words of the response>" is read for its lead. Works on a report object or its mapping; anything unreadable
    yields nothing here (the callers fail closed)."""
    out: list[tuple[str, Optional[str], str]] = []
    if report is None:
        return out
    response = _field(report, "original_response")
    written = " ".join(response.split()) if isinstance(response, str) else ""

    def own(t) -> Optional[str]:
        if not isinstance(t, str) or not t.strip():
            return None
        flat = " ".join(t.split())
        slots = _platform_note_slots(flat)
        if slots is not None:
            rest = [x for x in (" ".join(s.split()).strip(" '\"“”‘’") for s in slots) if x and not (written and x in written)]
            return "\n\n".join(rest) if rest else None
        lead_words = PLATFORM_NOTE_RE.match(flat)
        if lead_words is not None:
            # a note's opening words with no note's shape: the specialist's own field written to look like a note; the words
            # after the opening are read on their own as well as in the whole (an opening such as "quotation with no supplied
            # text ...:" must never frame them as a quotation)
            tail = flat[lead_words.end():].strip(" '\"“”‘’(")
            return f"{tail}\n\n{t}" if tail else t
        if written and flat in written and _bare_copy(flat, written):
            return None
        lead, sep, rest = flat.partition(": ")
        rest = rest.strip(" \"'“”‘’")
        if sep and written and len(lead) <= 80 and len(rest) >= 12 and rest in written:
            return lead  # the lead is the specialist's own note on words of the response
        return t
    for name, where in (("assumptions", "an assumption of the report"), ("unresolved_issues", "an unresolved issue of the report")):
        for t in list(_field(report, name) or [])[:128]:
            o = own(t)
            if o is not None:
                out.append((where, None, o))
    for c in list(_field(report, "claims") or [])[:512]:
        cid = _field(c, "claim_id")
        for name, where in (("assumptions", "an assumption of claim"), ("assessment_criteria", "an assessment criterion of claim")):
            for t in list(_field(c, name) or [])[:64]:
                o = own(t)
                if o is not None:
                    out.append((where, str(cid) if cid is not None else None, o))
    return out
