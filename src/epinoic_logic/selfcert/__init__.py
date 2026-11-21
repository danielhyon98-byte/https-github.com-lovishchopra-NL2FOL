"""The one self-certification reader every gate consults (round-10 hold remedy c3b; rules ``selfcert-1``).

An answer's claim, in its OWN scope, about checking, verification, review, testing, audit, QA, an engine or system result, proof,
approval, marking or scoring, or its own correctness, quality or confidence, whoever is credited, in any position, quoted or
relayed or not, and in any script or spelling, is a self-certification: never evidence, never a reason to deliver, select or
label an answer, and a non-success status is never shown as success (repository ``CLAUDE.md``).

The reading is by MEANING, not by a phrase list: the text is normalised (:mod:`.normalise`, rules N1 to N9), segmented into
pieces, sentences, clauses, labels and quotations (:mod:`.pieces`), and every assessment trigger is read for its theme and scope,
its evaluator, its polarity and its mood or frame (:mod:`.reader`) against closed classes of words (:mod:`.lexicon`,
``lexicon.json``). An encoded check label (reversed, shifted, Base64, hexadecimal, binary, Morse) and a word spelled out letter by
letter with any separators are decoded and read as a status value (:mod:`.encoded`, rule N10), and a sentence split by a blank
line is read as one as well. Text the reader cannot read (a run of letter-like symbols the fold table does not map, hidden characters, a
script with no vocabulary) is never delivered silently: :meth:`Reading.refuses` names it (receipt code CORE-SELF-002).

What is NOT a self-certification and is never gated: a negated, questioned or uncertain assessment; an instruction ("verify by
substituting back"); a worked check that shows its computation ("Check: 3 × 5 = 15", material for the engine); a named outside
source's check reported as evidence; a third party's check that is the subject matter; a quotation inside an analysed source
whose content does not refer to this answer; agreement of a value with a named subject-matter reference.

Public functions (exported through ``epinoic_logic.api.adapters``): :func:`read`, :func:`is_self_certification`,
:func:`claims_a_check`, :func:`wholly_self_certification`, :func:`text_spots`, :func:`report_spots`, :func:`payload_spots`,
:func:`unread_text_runs`, :func:`reading_form`, :func:`visible_form`, :func:`context_for`, :data:`SELFCERT_RULES`,
:func:`rules_digest`. :func:`read` is a pure function of ``(text, ctx)``, cached for texts up to 16 KiB, and never raises.
"""
from __future__ import annotations

import functools
import hashlib
import pathlib
import re
from typing import Any, Optional

from .encoded import morse_text
from .reader import Context, Hit, Reading, Unread, read_text

__all__ = ["Context", "Hit", "Unread", "Reading", "Spot", "SELFCERT_RULES", "rules_digest", "read", "is_self_certification",
           "claims_a_check", "wholly_self_certification", "text_spots", "report_spots", "payload_spots", "unread_text_runs",
           "reading_form", "visible_form", "context_for", "UNREAD_RULE", "GATE_RULE"]

#: The version of the self-certification rules (bound into the policy identity by ``engine.identity.policy_manifest``).
SELFCERT_RULES = "selfcert-1"
#: The rule names the delivery refusals carry.
GATE_RULE = "self-certification-gate"
UNREAD_RULE = "unread-text"

_HERE = pathlib.Path(__file__).resolve().parent
_CACHE_MAX = 16 * 1024

#: ``(paragraph number, piece text, Hit or Unread)``.
Spot = tuple


def rules_digest() -> str:
    """SHA-256 over :data:`SELFCERT_RULES`, ``lexicon.json`` and ``fold_table.json`` as stored."""
    h = hashlib.sha256()
    h.update(SELFCERT_RULES.encode())
    for name in ("lexicon.json", "fold_table.json"):
        h.update(b"\0" + name.encode() + b"\0")
        h.update((_HERE / name).read_bytes())
    return h.hexdigest()


def _read(text: str, ctx: Context) -> Reading:
    try:
        hits, unread = read_text(text, ctx)
        return Reading(tuple(Hit(*h) for h in hits), tuple(Unread(*u) for u in unread))
    except Exception:  # noqa: BLE001 - fail closed: a reader failure refuses
        return Reading((Hit("reader-failed", "CHECK", "whole", 0, len(text), "the text"),), ())


@functools.lru_cache(maxsize=4096)
def _read_cached(text: str, ctx: Context) -> Reading:
    return _read(text, ctx)


#: Text of ASCII blanks and ASCII punctuation alone (". . . .", "---"): no word, no symbol token, no hidden run; read as nothing.
#: (A star or a check mark is not ASCII punctuation, so "***" folds to a rating below and is read.)
_ASCII_MARKS_ONLY_RE = re.compile(r"[\s.,;:!?()\[\]{}'\"`_\-/\\|<>=+#@$%^&~]*")


#: A line drawn with marks alone: at least three non-blank characters, at most a tenth of them letters or digits.


def _art_runs(text: str) -> tuple[Unread, ...]:
    """Blocks of three or more consecutive lines drawn with marks ("#   #  #####", "*      *****", a figlet banner of _ \\ / | < >):
    letters drawn with symbols, text the reader cannot read (rule unread-text, attack round 6: an ASCII-art "VERIFIED" was read as
    nothing and delivered). A run of rule lines (one mark repeated, "-----", "=====") is a separator, not a drawing. Linear."""
    if text.count("\n") < 2:
        return ()
    out: list[Unread] = []
    run_start, run_n, run_rules, pos = -1, 0, 0, 0
    lines = text.split("\n")
    # (every line is read: the scan is one pass over the text, linear in its length. Attack round 7: a cap of the first 4,000 lines
    # read a banner after them as nothing; a bounded reader never reads what lies beyond its bound as nothing)

    def close(end: int) -> None:
        if run_n >= 3 and run_rules < run_n:
            out.append(Unread("art", run_start, end, "the text"))

    for line in lines:
        st = line.strip().strip("`")
        body = st.replace(" ", "").replace("\t", "")
        drawn = len(body) >= 3 and sum(c.isalnum() for c in body) * 10 <= len(body) and not (
            st.startswith("|") and st.endswith("|") and set(body) <= set("|-:+"))  # (a table's separator row is no drawing)
        if drawn:
            if run_n == 0:
                run_start = pos
            run_n += 1
            run_rules += 1 if (len(set(body)) == 1 and " " not in st) else 0
        else:
            close(pos)
            run_n, run_rules = 0, 0
        pos += len(line) + 1
    close(min(pos, len(text)))
    return tuple(out)


def read(text: str, ctx: Context = Context()) -> Reading:
    """The reading of ``text`` in ``ctx`` (module docstring). Never raises: any exception is a hit ``reader-failed`` (fail
    closed); a non-string or blank text reads as nothing. Lines drawn with marks (an ASCII-art banner) are named unread."""
    if not isinstance(text, str) or not text.strip():
        return Reading((), ())
    try:
        art = _art_runs(text)
    except Exception:  # noqa: BLE001 - fail closed
        art = (Unread("art", 0, len(text), "the text"),)
    if art:
        base = _read_plain(text, ctx)
        return Reading(base.hits, base.unread + art)
    return _read_plain(text, ctx)


def _read_plain(text: str, ctx: Context) -> Reading:
    if _ASCII_MARKS_ONLY_RE.fullmatch(text) and not morse_text(text):
        return Reading((), ())  # blanks and ASCII punctuation only: no word, symbol or hidden run to read (Morse is read, rule N10)
    if not isinstance(ctx, Context):
        ctx = Context()
    if len(text) <= _CACHE_MAX:
        return _read_cached(text, ctx)
    # a longer text is read uncached, except the last few read (the thin names of the gates read the same answer several times,
    # between readings of its claims; the reading is a pure function of the text and the context). The entries are a functools
    # cache, so emptying the package's caches empties them too (a hand-kept entry outlived that and served a timing sample)
    return _read_last_long(text, ctx)


@functools.lru_cache(maxsize=8)
def _read_last_long(text: str, ctx: Context) -> Reading:
    return _read(text, ctx)


def is_self_certification(text: str, ctx: Context = Context()) -> bool:
    """Whether ``text`` holds a self-certification (any hit), failing closed on a sentence in a script the reader has no vocabulary
    for (an unread run of kind "script": what it says cannot be read, so it is never taken for content). Hidden and letter-like runs
    are named by :func:`unread_text_runs` and refused by :meth:`Reading.refuses`; :attr:`Reading.hits` never holds an unread run."""
    r = read(text, ctx)
    return r.self_certifies() or any(u.kind == "script" for u in r.unread)


_PARA_SPLIT_RE = re.compile(r"\n\s*\n")


def certifies_where_written(piece: str, written: Optional[str], ctx: Context = Context()) -> bool:
    """Whether ``piece`` (a claim or a sentence a parser drew out of the answer ``written``) is a self-certification READ WHERE IT
    STANDS: it is one alone (:func:`is_self_certification`) and the paragraph of ``written`` that holds it is one too. A heading
    joined to the line under it ("Verification" over "Substitute x = 2: y = 4 − 8 = −4"), or a quotation cut from the source the
    sentence before names ("It claims: '... published here ...'"), is read in its paragraph (attack round 6). A piece not found in
    ``written`` (or no ``written``) is read alone. Fails closed."""
    try:
        if not is_self_certification(piece, ctx):
            return False
        if not isinstance(written, str) or not written.strip():
            return True
        head = " ".join(piece.split())[:40]
        if not head:
            return True
        for para in _PARA_SPLIT_RE.split(written)[:4096]:
            if head in " ".join(para.split()):
                return read(para, ctx).refuses()
        return True
    except Exception:  # noqa: BLE001 - fail closed
        return True


def claims_a_check(text: str, ctx: Context = Context()) -> bool:
    """Whether the claim ``text`` claims a check, a review, an engine or system result, a proof, an approval, a score or its own
    correctness (any hit, a label on content included): a claim whose outcome display is never a success status."""
    return read(text, ctx).self_certifies()


_RELATION_RE = re.compile(r"[=<>≤≥≠≈]")
_CLAUSE_SPLIT_RE = re.compile(r"(?<=[.!?;])\s+")


def wholly_self_certification(text: str, ctx: Context = Context()) -> bool:
    """Eligibility rule 0: every sentence and every ';'-clause of the claim holds a hit and no clause holds a relation sign outside
    a hit's span. Such a claim is NOT_ELIGIBLE_OTHER ("self-report") and never reaches the solver; a claim that also states content
    keeps its content's check (its outcome never shows a success status: :func:`claims_a_check`)."""
    if not isinstance(text, str) or not text.strip():
        return False
    r = read(text, ctx)
    if not r.hits:
        return False
    # a stated word count ("The paragraph has 320 words.") is a measurable claim: the gate names it (decision D7) and its display
    # never shows success (claims_a_check), but the count itself stays a question the engine can decide
    if all(h.family == "COMPLY" for h in r.hits) and any(ch.isdigit() for ch in text):
        return False
    if _RELATION_RE.search(text):
        # (a relation sign is covered when a hit's span holds it; the spans sorted once and searched, never every span per sign)
        from bisect import bisect_right
        covered = sorted((h.start, h.end) for h in r.hits)
        starts = [a for a, _b in covered]
        reach: list[int] = []
        best = -1
        for _a, b in covered:
            best = max(best, b)
            reach.append(best)
        for m in _RELATION_RE.finditer(text):
            k = bisect_right(starts, m.start()) - 1
            if k < 0 or reach[k] <= m.start():
                return False
    pieces = [p for p in _CLAUSE_SPLIT_RE.split(text.strip()) if p.strip(" .;!?")]
    for p in pieces:
        if not read(p, ctx).self_certifies():
            return False
        if _content_beside_label(p, ctx):
            return False
    return True


_SCORE_VALUE_WORDS = frozenset("band bands level levels mark marks grade grades top distinction score scores markband nota banda nivel "
                               "sobresaliente matricula".split())


def _score_value(rest: str) -> bool:
    """Whether a label's value is a score said in words ("Graded: top of the band.", "Marked: level 7 territory"): no clause of its
    own and a score word; the label and its value are one verdict, not content (check round 9 of c3c)."""
    from .reader import _has_clause, _merge, _tokens
    toks = _merge(_tokens(rest, 0, len(rest)))
    return any(t.w in _SCORE_VALUE_WORDS for t in toks) and not _has_clause(toks) and not any(c in rest for c in "=<>")


def _content_beside_label(piece: str, ctx: Context) -> bool:
    """Whether a piece is content with a label on it ("The treaty was signed in 1919 (verified).", "Verified: The constitution was
    adopted in 1919."): the content stays a claim to check."""
    r = read(piece, ctx)
    if all(h.form in ("label_after", "label_inside", "label_before") for h in r.hits):
        k = piece.find(":")
        if k > 0:
            rest = piece[k + 1:].strip()
            if len(rest.split()) >= 3 and not read(rest, ctx).self_certifies() and not _score_value(rest):
                return True
    if "(" in piece:
        outside = re.sub(r"\([^()]*\)", " ", piece)
        if len(outside.split()) >= 3 and not read(outside, ctx).self_certifies() and _states_something(outside):
            return True
    return False


_FINITE_HINT_RE = re.compile(r"\b(?:is|are|was|were|has|have|had|be|been|equals?|gives?|shows?|means?|es|son|fue|fueron)\b|\w(?:ed|es)\b",
                             re.IGNORECASE)


def _states_something(text: str) -> bool:
    """Whether the content beside a label states something the engine can check: a relation, or a clause with a verb. A bare
    labelled value ("Answer (verified): 15 km/h.") states no proposition of its own: the label is the whole claim."""
    if _RELATION_RE.search(text):
        return True
    body = text.split(":", 1)[1] if ":" in text else text
    words = [w for w in body.split() if any(c.isalpha() for c in w)]
    return len(words) >= 3 or bool(_FINITE_HINT_RE.search(body))


_PARAGRAPH_RE = re.compile(r"\n[ \t]*\n")


#: The half-width of the window a spot's sentence is looked for in (characters on each side of the hit).
_SPOT_WINDOW = 600


def text_spots(text: str, ctx: Context = Context()) -> list:
    """``(paragraph number, piece text, Hit | Unread)`` for each hit and unread run of the answer ``text``, smallest piece first.
    The piece is sliced from the original text by the hit's offsets (a sentence or a line around it)."""
    if not isinstance(text, str) or not text.strip():
        return []
    r = read(text, ctx)
    paras: list[tuple[int, int]] = []
    pos = 0
    for part in _PARAGRAPH_RE.split(text):
        k = text.find(part, pos)
        if part.strip():
            paras.append((k, k + len(part)))
        pos = k + len(part)
    out: list = []
    from bisect import bisect_right
    starts = [a for a, _b in paras]
    for item in list(r.hits) + list(r.unread):
        k = bisect_right(starts, item.start) - 1
        n = k + 1 if k >= 0 and paras[k][0] <= item.start < paras[k][1] else 1
        a, b = item.start, item.end
        # the sentence or line around the hit, looked for within a bounded window on each side (a text with no stop and no line
        # break must not make each hit slice the whole text: that was quadratic in time and memory up to the response limit)
        w0 = max(0, a - _SPOT_WINDOW)
        w1 = min(len(text), b + _SPOT_WINDOW)
        lo = max(text.rfind("\n", w0, a), max(text.rfind(". ", w0, a), text.rfind("? ", w0, a), text.rfind("! ", w0, a)) + 1)
        lo = w0 if lo < w0 else lo
        hi_c = [x for x in (text.find("\n", b, w1), text.find(". ", b, w1)) if x >= 0]
        hi = min(hi_c) + 1 if hi_c else w1
        piece = " ".join(text[lo:min(hi, max(b, lo) + 2 * _SPOT_WINDOW)].split())
        out.append((n, piece, item))
    out.sort(key=lambda x: (x[0], len(x[1])))
    return out


def unread_text_runs(text: str) -> tuple[Unread, ...]:
    """The runs of ``text`` the reader cannot read (rule unread-text, CORE-SELF-002): letter-like symbols the fold table does not
    map, hidden characters, a sentence in a script with no vocabulary."""
    return read(text).unread


def reading_form(text: str) -> str:
    """``text`` as the reader reads it: folded (:func:`visible_form`), markup and emphasis marks blanked, lower case."""
    from .normalise import fold
    from .pieces import work_string
    if not isinstance(text, str):
        return ""
    return " ".join(work_string(fold(text).text).split())


def visible_form(text: str) -> str:
    """``text`` as the student sees it, for reading only (rules N1 to N7)."""
    from .normalise import visible_form as _v
    return _v(text) if isinstance(text, str) else ""


def _field(obj, name: str):
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def report_spots(report, ctx: Context = Context()) -> list:
    """``(where, claim id or None, Hit | Unread)`` for every hit and unread run of a specialist report: the response, every
    claim's text, and every one of the specialist's own fields (assumptions, unresolved issues, assessment criteria). A field
    that cannot be read is named with a ``reader-failed`` hit (fail closed)."""
    from .pieces import report_texts, quotation_only
    out: list = []
    if report is None:
        return out
    response = _field(report, "original_response")
    if isinstance(response, str):
        r = read(response, ctx)
        for item in list(r.hits) + list(r.unread):
            out.append(("the response", None, item))
    for c in list(_field(report, "claims") or [])[:512]:
        t = _field(c, "claim_text")
        if not isinstance(t, str):
            t = _field(c, "text")  # (ClaimRecord and journaled payloads carry claim_text; older mappings carry text)
        if isinstance(t, str) and t.strip() and not quotation_only(t):
            r = read(t, ctx)
            cid = _field(c, "claim_id")
            for item in r.hits:
                out.append(("claim", str(cid) if cid is not None else None, item))
    try:
        fields = report_texts(report)
    except Exception:  # noqa: BLE001
        return out + [("a field of the report", None, Hit("reader-failed", "CHECK", "whole", 0, 0, "a field"))]
    for where, cid, text in fields:
        if len(text) > 4000 * 64:
            out.append((where, cid, Hit("reader-failed", "CHECK", "whole", 0, len(text), "a field too long to read")))
            continue
        r = read(text, ctx)
        for item in list(r.hits) + list(r.unread):
            out.append((where, cid, item))
    return out


_TEXT_KEYS = ("original_response", "synthesis", "synthesis_text", "answer", "text", "student_facing_text")
_LIST_OF_TEXT_KEYS = ("assumptions", "unresolved_issues")
_CLAIM_TEXT_KEYS = ("claim_text", "text")
_CLAIM_LIST_KEYS = ("assumptions", "assessment_criteria")
_RECORD_LIST_KEYS = ("ledger", "conflicts", "notes")


def _shape_faults(payload: dict) -> list[str]:
    """The places of a payload whose shape the reader cannot read (attack round 6: a response written as a list, claims as a
    mapping, an assumption as a bare string were read as nothing): a text that is not a string, a list of texts that is not a list
    of strings, claims that are not a list of claims. Each is named "(unreadable)" and refused as a whole (fail closed)."""
    out: list[str] = []
    for key in _TEXT_KEYS:
        v = payload.get(key)
        if v is not None and not isinstance(v, str):
            out.append(f"the {key.replace('_', ' ')} (unreadable)")
    for key in _LIST_OF_TEXT_KEYS:
        v = payload.get(key)
        if v is not None and not (isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v)):
            out.append(f"the {key.replace('_', ' ')} (unreadable)")
    for key in ("claims", "synthesized_claims", "claims_synthesized") + _RECORD_LIST_KEYS:
        v = payload.get(key)
        if v is None:
            continue
        if not isinstance(v, (list, tuple)):
            out.append(f"the {key.replace('_', ' ')} (unreadable)")
            continue
        for c in v[:512]:
            if isinstance(c, str):
                continue
            if not isinstance(c, dict):
                out.append(f"an item of the {key.replace('_', ' ')} (unreadable)")
                continue
            for k2, v2 in c.items():
                if k2 in _CLAIM_TEXT_KEYS and v2 is not None and not isinstance(v2, str):
                    out.append(f"a {k2.replace('_', ' ')} of the {key} (unreadable)")
                elif k2 in _CLAIM_LIST_KEYS and v2 is not None and not (
                        isinstance(v2, (list, tuple)) and all(isinstance(x, str) for x in v2)):
                    out.append(f"the {k2.replace('_', ' ')} of an item of the {key} (unreadable)")
    return list(dict.fromkeys(out))


def payload_spots(payload: Any, ctx: Context = Context()) -> list[str]:
    """The places (never the words) of a specialist report's payload or a synthesis mapping that hold a self-certification or an
    unread run: "the response", "claim <id>", "an assumption of claim <id>", "the synthesis", ... Unreadable: named."""
    if payload is None:
        return []
    if not isinstance(payload, dict):
        try:
            payload = dict(payload)
        except Exception:  # noqa: BLE001
            return ["the payload (unreadable)"]
    places: list[str] = _shape_faults(payload)
    try:
        if "original_response" in payload or "claims" in payload and "synthesis" not in payload:
            for where, cid, _item in report_spots(payload, ctx):
                places.append(where if cid is None else f"{where} {cid}")
        for key in ("synthesis", "synthesis_text", "answer", "text", "student_facing_text"):
            v = payload.get(key)
            if isinstance(v, str) and read(v, ctx).refuses():
                places.append(f"the {key.replace('_', ' ')}")
        for c in list(payload.get("synthesized_claims") or payload.get("claims_synthesized") or [])[:512]:
            t = (_field(c, "claim_text") if isinstance(_field(c, "claim_text"), str) else _field(c, "text")) if not isinstance(c, str) else c
            if isinstance(t, str) and read(t, ctx).refuses():
                cid = _field(c, "claim_id") if not isinstance(c, str) else None
                places.append(f"synthesized claim {cid}" if cid else "a synthesized claim")
    except Exception:  # noqa: BLE001 - fail closed
        places.append("the payload (unreadable)")
    return list(dict.fromkeys(places))


def context_for(request_or_plan: Any = None, *, writer: str = "specialist") -> Context:
    """The reading context built from the ROUTER's record (a journaled request, a plan, or a mapping with ``task_type``): marking
    only when the router's task type is a marking or feedback task (``markdown.corrections_apply``), the supplied texts' titles
    and authors as known sources, the supplied peer reports as peer documents. Missing or unreadable: the strict default."""
    if writer not in ("specialist", "combinator"):
        writer = "specialist"
    marking = False
    truth_item = False
    sources: list[str] = []
    peers: list[str] = []
    try:
        if request_or_plan is not None:
            for name in ("request_text", "text", "prompt", "question", "task"):
                v = _field(request_or_plan, name)
                if isinstance(v, str) and _TRUTH_ITEM_RE.search(v[:20000]):
                    truth_item = True
            task_type = _field(request_or_plan, "task_type")
            if task_type is None:
                inner = _field(request_or_plan, "request") or _field(request_or_plan, "plan")
                task_type = _field(inner, "task_type") if inner is not None else None
            if isinstance(task_type, str):
                from ..adapters.markdown import corrections_apply
                marking = bool(corrections_apply(task_type))
            for st in list(_field(request_or_plan, "supplied_texts") or [])[:64]:
                for name in ("title", "author", "name"):
                    v = _field(st, name)
                    if isinstance(v, str) and v.strip():
                        sources.append(v.strip())
            for pd in list(_field(request_or_plan, "peer_reports") or _field(request_or_plan, "peer_documents") or [])[:64]:
                for name in ("title", "name", "agent_id", "agent"):
                    v = _field(pd, name) if not isinstance(pd, str) else (pd if name == "name" else None)
                    if isinstance(v, str) and v.strip():
                        peers.append(v.strip())
    except Exception:  # noqa: BLE001 - unreadable: the strict default
        return Context(writer=writer)
    return Context(writer=writer, marking=marking, known_sources=tuple(sources), peer_documents=tuple(peers), truth_item=truth_item)


#: A request that asks a true-or-false item ("True or false: ...", "Is the statement correct or incorrect?", "verdadero o falso").
_TRUTH_ITEM_RE = __import__("re").compile(r"\btrue\s+or\s+false\b|\bcorrect\s+or\s+(?:in)?correct\b|\bright\s+or\s+wrong\b|"
                                          r"\bverdadero\s+o\s+falso\b|\bcorrect[ao]?\s+o\s+incorrect[ao]?\b", __import__("re").IGNORECASE)


def context_from_dict(d: Optional[dict]) -> Context:
    """The development sets' ``context`` field as a :class:`Context` (``{"task_type": ...}`` read through :func:`context_for`,
    ``{"writer": "combinator"}``)."""
    if not d:
        return Context()
    writer = d.get("writer", "specialist")
    if "task_type" in d or "request_text" in d:
        c = context_for({k: d[k] for k in ("task_type", "request_text") if k in d}, writer=writer)
        return c
    return Context(writer=writer)
