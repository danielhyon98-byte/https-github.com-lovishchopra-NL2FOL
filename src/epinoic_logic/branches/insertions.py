"""The insertions of a sentence: its subordinate and parenthetical clauses, read once and linearly for the row and column lookups of the
branch readers (geography, grounded figures, Language B).

A figure's row or column is named only by its own clause. A word inside an insertion that does not hold the figure (a clause opened by
'while', 'whereas', 'as', 'since', 'although', 'though', 'when', 'after', 'before', 'because', 'despite', 'with' and the like, their
Spanish counterparts, a relative clause, a bracket, a pair of dashes or a comma-delimited apposition) never names it, wherever the
insertion stands, and the verb of an insertion is never the sentence subject's verb (push check of 08c4a36b: 'Energy supply per person,
while coal declined, was about 11.8 GJ in 2025.' had read 'coal' as the subject and the Coal row as the figure's).

The reader is pure text handling: no model, no evaluation; each pattern is bounded and the whole sentence is walked a fixed number of times.
"""
from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from functools import lru_cache

__all__ = ["insertion_spans", "masked", "span_holding"]

#: English words that open a clause of their own (it has a verb): its span runs to the next delimiter, or to just before a second finite
#: verb when none comes first ('as gas use rose was about 9.3 GJ': the main clause resumes at 'was').
_EN_CLAUSE = (r"while|whilst|whereas|although|though|even\s+though|even\s+as|even\s+if|even\s+when|because|as|since|when|whenever|after|"
              r"before|once|unless|until|till|if|given\s+that|now\s+that|so\s+that|which|who|whom|whose|where")
#: English words that open a phrase with no verb of its own ('with natural gas expanding', 'despite oil prices', 'mostly oil and gas'):
#: its span runs to the next delimiter, or to just before the first finite verb.
_EN_PHRASE = (r"with|without|despite|in\s+spite\s+of|compared\s+(?:with|to)|relative\s+to|unlike|like|than|mostly|mainly|largely|chiefly|"
              r"primarily|principally|especially|particularly|notably|including|excluding|except|such\s+as|e\.\s*g\.|i\.\s*e\.|apart\s+from|"
              r"aside\s+from|besides|not|rather\s+than|along\s+with|together\s+with|as\s+well\s+as|in\s+particular|for\s+example|"
              r"for\s+instance|in\s+contrast|by\s+contrast|in\s+comparison|according\s+to|however|meanwhile|admittedly")
#: Spanish openers ('según la consigna', 'mientras el carbón bajaba', 'al reabrir', 'que había dejado de pasar').
_ES_OPEN = (r"seg[uú]n|mientras(?:\s+que)?|aunque|cuando|porque|ya\s+que|puesto\s+que|pues|tras|despu[eé]s\s+de|antes\s+de|desde\s+que|"
            r"a\s+pesar\s+de|pese\s+a|con|sin|como|donde|que|el\s+cual|la\s+cual|lo\s+cual|los\s+cuales|las\s+cuales|quien|quienes|"
            r"al\s+[^\W\d_]{2,20}(?:ar|er|ir)|sobre\s+todo|en\s+particular|por\s+ejemplo|es\s+decir|o\s+sea|incluido|incluida|incluidos|"
            r"incluidas|salvo|excepto|frente\s+a|a\s+diferencia\s+de|en\s+cambio|sin\s+embargo")
#: Clause openers read in mid-clause with no delimiter before them (English conjunctions only; 'as' is set aside in a comparison).
_MID_CLAUSE = r"while|whilst|whereas|although|though|even\s+though|even\s+as|because|as"

_FLAGS = re.IGNORECASE
_DELIMITED_OPEN_RE = re.compile(r"(?:^|(?<=[,;:(\[–—])|(?<=[.!?] ))[ \t]*+(?:(?:and|y|but|pero)[ \t]*+,?[ \t]*+)?(?P<w>" + _EN_CLAUSE + "|" + _EN_PHRASE + "|"
                                + _ES_OPEN + r")\b", _FLAGS)
_MID_OPEN_RE = re.compile(r"(?<=[^\W\d_][ \t])(?P<w>" + _MID_CLAUSE + r")\b", _FLAGS)
_ANY_OPEN_RE = re.compile(r"(?<![\w-])(?P<w>after|as|with|without|despite|since|before|when|whenever|while|whilst|although|though|because|"
                          r"compared\s+(?:with|to)|unlike|than|in\s+spite\s+of)\b", _FLAGS)
#: Where an insertion ends at the latest: a comma, semicolon, colon, bracket, a spaced or em dash, a sentence end or a line break.
_END_RE = re.compile(r"[,;:()\[\]\n—–]|\s-\s|[.!?](?=\s|$)")
#: English finite verbs (a closed list with the regular past): where a phrase ends, and the second verb where a clause ends.
_EN_VERBS = (r"is|are|was|were|has|have|had|does|did|do|will|would|can|could|may|might|shall|should|must|rose|rises|fell|falls|"
             r"grew|grows|showed|shows|reached|reaches|stood|stands|made|makes|came|comes|went|goes|amounted|amounts|totalled|"
             r"totaled|totals|supplied|supplies|provided|provides|used|uses|increased|increases|decreased|decreases|dropped|drops|"
             r"declined|declines|accounted|accounts|equalled|equaled|equals|climbed|climbs|eased|eases|spread|spreads|doubled|"
             r"doubles|halved|halves|expanded|expands|jumped|jumps|slipped|slips|stayed|stays|remained|remains|peaked|peaks|"
             r"surged|surges|plunged|plunges|soared|soars|shrank|shrinks|became|becomes|continued|continues|fluctuated|fluctuates|"
             r"recovered|recovers|hit|hits|averaged|averages|ran|runs|lasted|lasts|took|takes|gave|gives|got|gets|kept|keeps|"
             r"changed|changes|improved|improves|worsened|worsens")
_EN_FINITE_RE = re.compile(r"\b(?:" + _EN_VERBS + r")\b", re.IGNORECASE)
_EN_FINITE_AT_RE = re.compile(r"\s*+(?:(?:then|also|still|only|just|about|roughly|around)\s++)?(?:" + _EN_VERBS + r")\b", re.IGNORECASE)
#: The words before a mid-clause 'as' that make it a comparison or a name, never a clause ('as high as', 'such as', 'known as').
_AS_COMPARE_BEFORE_RE = re.compile(r"(?:\b(?:such|same|twice|thrice|known|so|regarded|seen|described|classed|defined|counted)|\bas\s+[^\W\d_]+(?:\s+[^\W\d_]+)?)\s*+$",
                                   _FLAGS)
_AS_COMPARE_AFTER_RE = re.compile(r"\s*+(?:well\s+as|of\b|per\b|a\s+(?:share|percentage|proportion|whole|result|fraction|rule)\b|much\b|many\b|"
                                  r"far\b|long\b|high\b|low\b|large\b|small\b|little\b|soon\b|a\b|an\b|\d)", _FLAGS)
_CLAUSE_WORDS = frozenset(w.lower() for w in re.split(r"\|", _EN_CLAUSE.replace(r"\s+", " ")))
#: A Spanish finite verb in the regular past or a closed list ('duró', 'tenía', 'fue'): where a generic comma insertion closes.
_ES_VERBS = (r"es|son|era|eran|fue|fueron|está|están|estaba|estaban|hay|había|tiene|tienen|tenía|tenían|tuvo|cuenta|contaba|"
             r"[^\W\d_]{2,20}(?:ó|ió|aba|aban|aron|ieron)")
_ES_FINITE_RE = re.compile(r"(?<![^\W\d_])(?:" + _ES_VERBS + r")(?![^\W\d_])", re.IGNORECASE)
_ES_FINITE_AT_RE = re.compile(r"\s*+(?:" + _ES_VERBS + r")(?![^\W\d_])", re.IGNORECASE)


#: The generic heads an apposition or a bracket names the referent of ('One source, natural gas, ...', 'The busiest site (site 1) ...',
#: 'The market leader, Alba, ...', 'Una fuente, el gas natural, ...'): the apposition IS the subject, so the row it names is the figure's
#: (check round 13 of c3g; the blanking is for clauses and phrases that do not hold the subject).
_REFERENT_HEAD_RE = re.compile(r"\b(?:sources?|fuels?|sites?|firms?|compan(?:y|ies)|business(?:es)?|leaders?|producers?|exporters?|"
                               r"importers?|countr(?:y|ies)|regions?|sectors?|categor(?:y|ies)|types?|items?|products?|brands?|rows?|"
                               r"cit(?:y|ies)|towns?|villages?|options?|groups?|stations?|rivers?|zones?|districts?|areas?|industr(?:y|ies)|"
                               r"carriers?|suppliers?|competitors?|rivals?|members?|nations?|states?|crops?|species|materials?|"
                               r"fuentes?|sectores|sector|empresas?|pa[ií]s(?:es)?|regi[oó]n(?:es)?|sitios?|ciudad(?:es)?|pueblos?|"
                               r"productos?|marcas?|combustibles?|grupos?|zonas?|l[ií]der(?:es)?)\b", re.IGNORECASE)
#: Words that open an insertion that is no apposition naming the referent ('mostly oil and gas', 'coal aside', 'such as coal').
_NOT_REFERENT_RE = re.compile(r"(?:\b(?:" + _EN_CLAUSE + "|" + _EN_PHRASE + "|" + _ES_OPEN + r")\b)|\b(?:aside|apart|excluded|included|"
                              r"aparte|excluido|excluida|incluido|incluida)\b|%|\d[.,]\d", re.IGNORECASE)


def _referent_apposition(text: str, a: int, inner_a: int, inner_b: int) -> bool:
    """Whether the insertion whose words run from ``inner_a`` to ``inner_b`` (it opens at ``a``) is an apposition that names the referent
    of a generic head right before it ('One source, natural gas,', 'The largest source in 2025, coal,', 'The quietest site (site 10)'):
    a short noun phrase with no verb, opener or figure of its own, after a head with no verb that ends a generic noun (source, site,
    firm, fuel, leader) or a year after one."""
    inner = text[inner_a:inner_b].strip(" \t,()[]—–-")
    if not inner or len(inner) > 60 or len(inner.split()) > 6 or _EN_FINITE_RE.search(inner) or _ES_FINITE_RE.search(inner) or \
            _NOT_REFERENT_RE.search(inner):
        return False
    lo = max(text.rfind(x, 0, a) for x in (",", ";", ":", "(", "[", "\n", ". ")) + 1
    head = text[lo:a]
    if not head.strip() or len(head) > 80 or _EN_FINITE_RE.search(head) or _ES_FINITE_RE.search(head):
        return False
    m = None
    for m in _REFERENT_HEAD_RE.finditer(head):
        pass
    if m is None:
        return False
    tail = head[m.end():].strip()
    return not tail or re.fullmatch(r"(?:in|en|de|of)\s+(?:\d{4}|the\s+\d{4}s?)", tail, re.IGNORECASE) is not None


class _Marks:
    """The sentence's delimiters and English finite verbs, found once, each lookup a bisection (so an insertion's end is found in
    O(log n), never by a scan to the next delimiter for every opener: 'while coal while coal ...' with no comma stays linear)."""

    def __init__(self, text: str):
        self.ends = [m.start() for m in _END_RE.finditer(text)]
        verbs = [m for m in _EN_FINITE_RE.finditer(text)]
        self.verb_starts = [m.start() for m in verbs]
        self.text = text

    def close(self, body: int, clause: bool) -> int:
        """The end of the insertion whose words begin at ``body``: the next delimiter, or the verb where the main clause resumes (a
        clause's second finite verb, a phrase's first)."""
        k = bisect_left(self.ends, body)
        hi = self.ends[k] if k < len(self.ends) else len(self.text)
        j = bisect_left(self.verb_starts, body) + (1 if clause else 0)
        if j < len(self.verb_starts) and self.verb_starts[j] < hi and self.text[self.verb_starts[j] - 1:self.verb_starts[j]].isspace():
            hi = self.verb_starts[j]
        return hi


@lru_cache(maxsize=512)
def insertion_spans(text: str, anywhere: bool = False) -> tuple[tuple[int, int], ...]:
    """The insertions of ``text`` as sorted, disjoint ``(start, end)`` spans (the outermost of nested ones). With ``anywhere``, an
    opener in mid-clause opens one too (the shared table reader's frame: 'Imports made up 54% after coal declined')."""
    marks = _Marks(text)  # (the whole text: no bound leaves an insertion of a long sentence unread)
    raw: list[tuple[int, int]] = []
    # brackets (an unclosed one runs to the sentence's end)
    stack: list[int] = []
    for m in re.finditer(r"[()\[\]]", text):
        if m.group(0) in "([":
            stack.append(m.start())
        elif stack:
            a = stack.pop()
            if not stack and not _referent_apposition(text, a, a + 1, m.start()):
                raw.append((a, m.end()))
    if stack:
        a = stack[0]
        e = re.compile(r"[.!?](?=\s|$)|\n").search(text, a)
        raw.append((a, e.start() if e else len(text)))
    # dashes in pairs (a last unpaired one runs to the sentence's end)
    dashes = [m for m in re.finditer(r"\s[-–—]\s|—|–(?=[^\W\d_])", text)]
    for i in range(0, len(dashes), 2):
        a = dashes[i].start()
        if i + 1 < len(dashes):
            if not _referent_apposition(text, a, dashes[i].end(), dashes[i + 1].start()):
                raw.append((a, dashes[i + 1].end()))
        else:
            e = re.compile(r"[.!?](?=\s|$)|\n").search(text, dashes[i].end())
            raw.append((a, e.start() if e else len(text)))
    # clauses and phrases opened after a delimiter or at the start
    for m in _DELIMITED_OPEN_RE.finditer(text):
        w = " ".join(m.group("w").lower().split())
        if w == "as" and _AS_COMPARE_AFTER_RE.match(text, m.end()):
            continue
        clause = w in _CLAUSE_WORDS
        a = m.start() - 1 if m.start() > 0 and text[m.start() - 1] == "," else m.start()
        b = marks.close(m.end(), clause)
        if text[a:a + 1] == "," and text[b:b + 1] == ",":
            b += 1  # (a comma pair: the insertion with both its commas)
        raw.append((a, b))
    # an English conjunction in mid-clause ('Energy supply per person as gas use rose was about 9.3 GJ')
    for m in (_ANY_OPEN_RE if anywhere else _MID_OPEN_RE).finditer(text):
        w = " ".join(m.group("w").lower().split())
        if w == "as" and (_AS_COMPARE_BEFORE_RE.search(text, max(0, m.start() - 40), m.start()) or _AS_COMPARE_AFTER_RE.match(text, m.end())):
            continue
        raw.append((m.start(), marks.close(m.end(), w in _CLAUSE_WORDS)))
    # a comma-delimited apposition between a subject and its verb ('Imported energy, mostly oil and gas, was ...', 'Energy supply per
    # person, coal aside, was ...'): the words before it have no verb and a verb follows it
    commas = [m.start() for m in re.finditer(r",", text)]
    for c1, c2 in zip(commas, commas[1:]):
        if c2 - c1 > 160 or re.search(r"[;:()\[\]\n.!?]", text[c1:c2]):
            continue
        if not (_EN_FINITE_AT_RE.match(text, c2 + 1) or _ES_FINITE_AT_RE.match(text, c2 + 1)):
            continue
        lo = max(text.rfind(",", 0, c1), text.rfind(";", 0, c1), text.rfind(":", 0, c1), text.rfind(".", 0, c1), -1) + 1
        head = text[lo:c1]
        if not head.strip() or _EN_FINITE_RE.search(head) or _ES_FINITE_RE.search(head) or re.search(r"\b(?:and|or|y|o)\s*+$", head, _FLAGS):
            continue
        if re.search(r"\b(?:and|or|y|o|&)\s*+$", text[c1 + 1:c2], _FLAGS) or re.match(r"\s*+(?:and|or|y|o|&)\b", text[c2 + 1:c2 + 8], _FLAGS):
            continue  # a list of three or more ('Coal, oil, and gas supplied ...')
        if _referent_apposition(text, c1, c1 + 1, c2):
            continue  # ('One source, natural gas, rose ...': the apposition IS the subject, its row the figure's)
        raw.append((c1, c2 + 1))
    if not raw:
        return ()
    raw.sort()
    out: list[list[int]] = []
    for a, b in raw:
        if b <= a:
            continue
        if out and a < out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return tuple((a, b) for a, b in out)


def span_holding(spans: tuple[tuple[int, int], ...], starts: list[int], at: int):
    """The span of ``spans`` (with ``starts`` their starts) that holds offset ``at``, or None."""
    k = bisect_right(starts, at) - 1
    if k >= 0 and spans[k][0] <= at < spans[k][1]:
        return spans[k]
    return None


def masked(text: str, spans: tuple[tuple[int, int], ...], keep=None) -> str:
    """``text`` with every span blanked (spaces, so every offset stays) but ``keep``."""
    if not spans:
        return text
    parts: list[str] = []
    pos = 0
    for a, b in spans:
        if keep is not None and (a, b) == keep:
            continue
        parts.append(text[pos:a])
        parts.append(" " * (b - a))
        pos = b
    parts.append(text[pos:])
    return "".join(parts)
