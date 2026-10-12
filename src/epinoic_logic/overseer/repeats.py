"""Repeated faults: a deterministic signature for every error-level fault of an agent's answer, and the detection of a
fault that comes back in the same task.

When several agents answer the same input (duplicated instances of one specialist, or several specialists), or one
agent resubmits after a rejection, the same fault can come back. A repeated fault is never delivered or consolidated
(:mod:`~epinoic_logic.overseer.consolidate`), it is counted per agent, and it makes the overseer pool send the task's
dossier to at least two independent overseer-agent instances (:mod:`~epinoic_logic.overseer.pool`). Design
``docs/OVERSEER_DESIGN.md`` section 19.

**What is a fault here.** Every error-level finding about an ANSWER (a ``response`` or ``response_text`` transfer: an
agent's reply to a router request), delivered or REJECTED:

* every error-level finding on its receipt (the channel's own ``INT-*`` checks); a branch rule escalated as
  INT-SUBJ-003 is signed under its branch code too (``INT-SUBJ-003/HI-SRC-001``);
* every error-level ``OVS-FID-*`` and ``OVS-TRN-*`` finding of the task audit that names its message: what the agent
  said, as the auditor re-checked it. Custody, receipt and result findings concern the infrastructure, not what the agent
  said: they exclude the answer from a consolidation, but they are no fault of the agent's to repeat.

**The signature** (rule :data:`SIGNATURE_RULE`) is ``sha256(canonical_json([rule, code, anchor_kind, anchor,
figures]))``, where the anchor is the normalised offending claim or quoted phrase:

* ``quotation``: a source fault (:data:`QUOTATION_CODES`, or a branch ``-SRC-`` rule) of claims that carry quotations:
  the claims' quoted phrases and source excerpts, each in content form, sorted and unique. A rewording of the claim
  around the same invented quotation keeps the signature;
* ``claim``: a finding that names claims of the answer's own report: those claims' texts in content form, sorted and
  unique;
* ``finding``: otherwise (a finding that names no claim of the answer: identity, envelope, parse, constraint faults):
  the finding's message in content form, with every identifier of the answer (message, receipt, report, request,
  claim, agent and result ids, and any long hexadecimal id) replaced by its type, so the same fault from another agent
  or another submission signs alike.

``figures`` are the figures and dates of the anchor's source text (``ledger.figure_spellings``; a figure with a scale
word keeps it, "6.1 million"), sorted and unique. **Content form** (:func:`content_form`): invisible format characters
removed (category Cf, such as zero-width spaces and soft hyphens, and every other default-ignorable code point, assigned
or not), confusable Cyrillic, Greek and Latin letters folded to the basic Latin letters they look like (before the
normalisation, whose NFKC would turn some into other letters, and after it), the fidelity normalisation
(``checks.normalise``: NFKC, quotes and dashes folded, markdown removed, whitespace collapsed), then case folded, thousands separators
removed, the text read as words and numbers (a decimal point or separator inside a number kept), and the articles "a",
"an" and "the" dropped. A rewording that changes only case, punctuation, markdown, whitespace, invisible characters,
look-alike letters or articles leaves the signature unchanged; one that changes a word, a figure or a quotation changes
it.

**Repeats.** :func:`detect_repeats` walks the answers of one task in order (the views given, each in journal sequence
order). An answer contributes each signature once. Rule ``quotation-anchor`` (review round 2): a quoted phrase that an
error-level source fault named earlier in the task, carried again by a later answer (in a claim, an excerpt or only the
prose) that a weaker check flags (a warning-level ``-SRC-`` rule, OVS-FID-006 parse loss), is a repeat of that fault
whatever code catches it now. The first answer with a signature is its original; every later answer
with the same signature, from any agent (another agent, a duplicated instance, or the same agent resubmitting after a
rejection), is a repeat: one ``OVS-REP-001`` finding (error) naming both answers, and one count against the repeating
agent. The code is recorded in the :class:`RepeatReport` and in the consolidated response, never in a task audit: it
never changes a clearance, and the answer it names already carries the error-level fault its signature came from.

Everything here reads the journal (an :class:`~epinoic_logic.overseer.view.OverseerView`) and a signed task audit; agent
text is normalised, hashed and compared, never interpreted or followed.
"""
from __future__ import annotations

import re
from typing import Any, Literal, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from ..adapters.markdown import find_quotation_spans
from ..integrity.contracts import IntegrityFinding
from ..integrity.ledger import figure_spellings
from ..ir.canonical import canonical_json, sha256_hex
from .checks import is_default_ignorable, normalise
from .codes import is_agent_code, ovs_finding
from .contracts import OverseerAudit
from .view import RESPONSE_KINDS, OverseerView, Transfer

__all__ = [
    "SIGNATURE_RULE", "REPEAT_CODE", "ANSWER_KINDS", "AUDIT_FAULT_PREFIXES", "QUOTATION_CODES", "AnchorKind", "FaultOccurrence", "RepeatRecord",
    "RepeatReport", "content_form", "figures_of", "quotations_of", "fault_signature", "fault_occurrences", "detect_repeats",
]

#: The signature rule's name and version; it is part of every signature, so a changed rule never matches an old one.
SIGNATURE_RULE = "fault-signature/1"
REPEAT_CODE = "OVS-REP-001"
#: The transfers that are agents' answers to router requests.
ANSWER_KINDS = RESPONSE_KINDS
#: Task-audit findings about what an agent said (claim fidelity, translations), signed as the agent's faults.
AUDIT_FAULT_PREFIXES = ("OVS-FID-", "OVS-TRN-")
#: Source faults: their anchor is the quoted phrase, not the wording around it.
QUOTATION_CODES = frozenset({"INT-REQ-003", "INT-REQ-010", "INT-LEDGER-025", "OVS-FID-002", "OVS-FID-004", "OVS-TRN-004"})
#: The longest anchor kept in a record (the signature is computed over the whole anchor).
MAX_ANCHOR_CHARS = 2000

AnchorKind = Literal["quotation", "claim", "finding"]

_ARTICLES = frozenset({"a", "an", "the"})
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*|[^\W\d_]+")
_THOUSANDS_RE = re.compile(r"(?<=\d),(?=\d{3}(?!\d))")
_BRANCH_RULE_RE = re.compile(r"^\[[^\]]*\]\s*([A-Z]+-[A-Z]+-\d{3})\b")
_HEX_ID_RE = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{16,}(?![0-9A-Za-z])|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# ============================================================================================ normalisation
#: Confusable letters (Cyrillic, Greek and Latin forms that look like basic Latin ones), mapped to the Latin letter for
#: the content form only (a skeleton in the spirit of UTS #39, restricted to lower-case letters after case folding). It
#: is applied BEFORE the NFKC normalisation (which would turn the lunate sigma "ϲ" into "σ") and again after it.
_CONFUSABLES = str.maketrans({
    "а": "a", "в": "b", "е": "e", "ё": "e", "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "с": "c", "т": "t", "у": "y", "х": "x",
    "і": "i", "ї": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ɡ": "g", "һ": "h", "ӏ": "l", "ү": "y", "ԍ": "g", "ɩ": "i",
    "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ν": "v", "ο": "o", "ρ": "p", "τ": "t", "υ": "u", "χ": "x", "ϳ": "j",
    # the sigma forms (lunate, final, medial; NFKC turns the lunate sigma into the final one) are read as the letter they
    # are, s: "ϲecret" is "secret" with its s in another script
    "ϲ": "s", "ς": "s", "σ": "s",
    "ı": "i", "ɑ": "a", "ʀ": "r", "ɪ": "i", "ʏ": "y", "ɴ": "n", "ʙ": "b", "ʜ": "h", "ʟ": "l", "ᴀ": "a", "ᴄ": "c", "ᴅ": "d", "ᴇ": "e",
    "ᴋ": "k", "ᴍ": "m", "ᴏ": "o", "ᴘ": "p", "ᴛ": "t", "ᴜ": "u", "ᴠ": "v", "ᴡ": "w", "ᴢ": "z",
})


def _visible(text: str) -> str:
    """``text`` without invisible format characters (category Cf: zero-width spaces and joiners, soft hyphens, bidi
    controls) and every other default-ignorable code point, assigned or not (U+2065, U+FFF0-FFF8, U+E0000-E0FFF)."""
    import unicodedata
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf" and not is_default_ignorable(ch))


def content_form(text: Any) -> str:
    """The content form of ``text`` (module docstring): invisible characters removed, confusable letters folded to Latin
    (before and after the normalisation), normalised, case folded, words and numbers only, no articles."""
    pre = _visible(text if isinstance(text, str) else "").casefold().translate(_CONFUSABLES)
    t = _visible(normalise(pre)).casefold().translate(_CONFUSABLES)
    t = _THOUSANDS_RE.sub("", t)
    return " ".join(tok for tok in _TOKEN_RE.findall(t) if tok not in _ARTICLES)


def figures_of(text: Any) -> tuple[str, ...]:
    """The figures and dates of ``text``, sorted and unique: a numeral as written (thousands separators removed), a
    figure with a scale word as ``"<numeral> <scale>"``, a month-year as ``"<month> <year>"``."""
    out: set[str] = set()
    for label, keys in figure_spellings(text if isinstance(text, str) else ""):
        scaled = sorted(k for k in keys if " " in k and k[:1].isdigit())
        out.add(scaled[0] if scaled else label.casefold())
    return tuple(sorted(out, key=lambda s: (len(s), s)))


def quotations_of(claim: Any) -> tuple[str, ...]:
    """The quoted phrases of a claim (quotation spans of its text and its source excerpts), each in content form,
    sorted and unique."""
    texts = [inner for _s, _e, inner in find_quotation_spans(getattr(claim, "claim_text", "") or "")]
    texts += [getattr(r, "excerpt", None) or "" for r in (getattr(claim, "source_refs", None) or [])]
    forms = {content_form(q) for q in texts}
    forms.discard("")
    return tuple(sorted(forms))


def fault_signature(code: str, anchor_kind: str, anchor: str, figures: Sequence[str]) -> str:
    return sha256_hex(canonical_json([SIGNATURE_RULE, code, anchor_kind, anchor, list(figures)]))


# ============================================================================================ contracts
_FROZEN = ConfigDict(extra="forbid", frozen=True)


class FaultOccurrence(BaseModel):
    """One error-level fault of one answer, with its signature."""
    model_config = _FROZEN
    signature: str
    code: str
    anchor_kind: AnchorKind
    anchor: str = Field(max_length=MAX_ANCHOR_CHARS)
    figures: list[str] = Field(default_factory=list)
    channel_uid: str
    seq: int
    message_id: str
    receipt_id: Optional[str] = None
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    claim_ids: list[str] = Field(default_factory=list)
    source: Literal["receipt", "audit"]
    result_ids: list[str] = Field(default_factory=list)


class RepeatRecord(BaseModel):
    """A fault whose signature already occurred earlier in the task: the repeating answer and the original."""
    model_config = _FROZEN
    signature: str
    code: str
    anchor_kind: AnchorKind
    anchor: str = Field(max_length=MAX_ANCHOR_CHARS)
    figures: list[str] = Field(default_factory=list)
    message_id: str
    agent_id: Optional[str] = None
    report_id: Optional[str] = None
    channel_uid: str
    seq: int
    first_message_id: str
    first_agent_id: Optional[str] = None
    first_report_id: Optional[str] = None
    first_channel_uid: str
    first_seq: int
    occurrence: int = Field(ge=2, description="2 for the first repeat of a signature, 3 for the second, ...")
    same_agent: bool
    result_ids: list[str] = Field(default_factory=list)


class RepeatReport(BaseModel):
    """Every fault of every answer of one task, the repeats among them, and the count of repeats per agent. Deterministic:
    no timestamp, no random id."""
    model_config = ConfigDict(extra="forbid")
    task_id: str
    channel_uids: list[str] = Field(default_factory=list)
    rule: str = SIGNATURE_RULE
    answers: int = 0
    occurrences: list[FaultOccurrence] = Field(default_factory=list)
    repeats: list[RepeatRecord] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict, description="agent id -> repeated faults of that agent")
    findings: list[IntegrityFinding] = Field(default_factory=list)

    def repeated_message_ids(self) -> list[str]:
        return list(dict.fromkeys(r.message_id for r in self.repeats))

    def for_message(self, message_id: str) -> list[RepeatRecord]:
        return [r for r in self.repeats if r.message_id == message_id]

    def channel_has_repeats(self, channel_uid: str) -> bool:
        return any(r.channel_uid == channel_uid for r in self.repeats)


# ============================================================================================ signatures
def _branch_code(f: IntegrityFinding) -> str:
    if f.code == "INT-SUBJ-003":
        m = _BRANCH_RULE_RE.match(f.message or "")
        if m:
            return f"INT-SUBJ-003/{m.group(1)}"
    return f.code


def _answer_identifiers(t: Transfer, report: Any) -> list[tuple[str, str]]:
    """``(identifier, type)`` of everything that names this answer rather than its content, longest first."""
    pairs: dict[str, str] = {}

    def add(value: Any, kind: str) -> None:
        if isinstance(value, str) and len(value) >= 2:
            pairs.setdefault(value, kind)

    add(t.message_id, "message")
    add(t.receipt_id, "receipt")
    add(t.in_reply_to, "message")
    add(t.report_id, "report")
    add(t.sender_agent_id, "agent")
    add(t.recipient_agent_id, "agent")
    payload = t.payload or {}
    for k, kind in (("report_id", "report"), ("agent_id", "agent"), ("request_id", "request"), ("task_id", "task")):
        add(payload.get(k), kind)
    if report is not None:
        for c in report.claims:
            add(c.claim_id, "claim")
    if t.receipt is not None:
        for f in t.receipt.findings:
            add(f.formal_result_id, "result")
            for r in f.related_result_ids:
                add(r, "result")
        for o in t.receipt.outcomes:
            if o.verification is not None:
                add(o.verification.result_id, "result")
        for r in t.receipt.formal_result_ids:
            add(r, "result")
    return sorted(pairs.items(), key=lambda kv: (-len(kv[0]), kv[0]))


def _strip_identifiers(message: str, idents: list[tuple[str, str]]) -> str:
    out = message or ""
    for ident, kind in idents:
        out = re.sub(r"(?<![\w-])" + re.escape(ident) + r"(?![\w-])", f" {kind} ", out)
    return _HEX_ID_RE.sub(" id ", out)


def _finding_result_ids(f: IntegrityFinding, t: Transfer) -> list[str]:
    ids = [f.formal_result_id] if f.formal_result_id else []
    ids += list(f.related_result_ids)
    if t.receipt is not None and f.claim_ids:
        named = set(f.claim_ids)
        ids += [o.verification.result_id for o in t.receipt.outcomes if o.claim_id in named and o.verification is not None]
    return list(dict.fromkeys(i for i in ids if i))


def _occurrence(view: OverseerView, t: Transfer, f: IntegrityFinding, source: str, idents: list[tuple[str, str]]) -> FaultOccurrence:
    code = _branch_code(f)
    report = t.report
    claims = [c for c in (report.claims if report is not None else []) if c.claim_id in set(f.claim_ids)]
    kind: AnchorKind
    anchor = ""
    figures: tuple[str, ...] = ()
    if claims and (f.code in QUOTATION_CODES or "-SRC-" in code):
        quotes = sorted({q for c in claims for q in quotations_of(c)})
        if quotes:
            kind, anchor = "quotation", " | ".join(quotes)
            figures = figures_of(" ".join(quotes))
    if not anchor and claims:
        kind = "claim"
        anchor = " | ".join(sorted({content_form(c.claim_text) for c in claims}))
        figures = figures_of(" ".join(c.claim_text for c in claims))
    if not anchor:
        kind = "finding"
        stripped = _strip_identifiers(f.message, idents)
        anchor = content_form(stripped)
        figures = figures_of(stripped)
    sig = fault_signature(code, kind, anchor, figures)
    agent = t.sender_agent_id or (t.payload or {}).get("agent_id")
    return FaultOccurrence(signature=sig, code=code, anchor_kind=kind, anchor=anchor[:MAX_ANCHOR_CHARS], figures=list(figures), channel_uid=view.channel_uid,
                           seq=t.seq, message_id=t.message_id or "", receipt_id=t.receipt_id, agent_id=agent if isinstance(agent, str) else None,
                           report_id=t.report_id, claim_ids=[c.claim_id for c in claims] or list(f.claim_ids), source=source,  # type: ignore[arg-type]
                           result_ids=_finding_result_ids(f, t))


def fault_occurrences(view: OverseerView, t: Transfer, audit: Optional[OverseerAudit] = None) -> list[FaultOccurrence]:
    """The error-level faults of one answer, each signature once (receipt findings first, then the audit's)."""
    if t.kind not in ANSWER_KINDS or not t.message_id:
        return []
    idents = _answer_identifiers(t, t.report)
    found: list[FaultOccurrence] = []
    seen: set[str] = set()
    receipt_findings = list(t.receipt.findings) if t.receipt is not None else []
    audit_findings = []
    if audit is not None:
        audit_findings = [f for f in audit.report.findings if f.severity == "error" and not is_agent_code(f.code)
                          and f.code.startswith(AUDIT_FAULT_PREFIXES) and t.message_id in f.message_ids]
    for source, findings in (("receipt", [f for f in receipt_findings if f.severity == "error"]), ("audit", audit_findings)):
        for f in findings:
            o = _occurrence(view, t, f, source, idents)
            if o.signature not in seen:
                seen.add(o.signature)
                found.append(o)
    return found


#: Audit findings that signal a quotation of an answer could not be placed (any severity): a weaker check catching a
#: quoted phrase that an error-level source fault named earlier in the task (rule ``quotation-anchor``).
_WEAK_SOURCE_AUDIT_CODES = frozenset({"OVS-FID-002", "OVS-FID-004", "OVS-FID-006", "OVS-FID-007", "OVS-TRN-004"})


def _source_signal(t: Transfer, audit: Optional[OverseerAudit]) -> bool:
    """Whether a check flagged a quotation of this answer as unplaced, at any severity: a receipt source finding (the
    INT quotation codes, a branch ``-SRC-`` rule or its INT-SUBJ-003), a ``-SRC-`` structural finding, or an audit
    finding of :data:`_WEAK_SOURCE_AUDIT_CODES` naming its message."""
    rc = t.receipt
    if rc is not None:
        if any(f.code in QUOTATION_CODES or "-SRC-" in _branch_code(f) for f in rc.findings):
            return True
        if any("-SRC-" in sf.code for sf in rc.structural_findings):
            return True
    if audit is not None and t.message_id:
        return any(f.code in _WEAK_SOURCE_AUDIT_CODES and t.message_id in f.message_ids for f in audit.report.findings)
    return False


def _answer_phrases(t: Transfer) -> set[str]:
    """Every quoted phrase of an answer in content form: its claims' quotations and source excerpts, and every quotation
    span of its ``original_response`` (a phrase kept only in the prose is the answer's too)."""
    report = t.report
    out: set[str] = set()
    if report is None:
        return out
    for c in report.claims:
        out.update(quotations_of(c))
    out.update(content_form(inner) for _s, _e, inner in find_quotation_spans(report.original_response or ""))
    out.discard("")
    return out


# ============================================================================================ repeats
def detect_repeats(views: Sequence[OverseerView], audits: Optional[Mapping[str, OverseerAudit]] = None, *, keyring: Any = None) -> RepeatReport:
    """The repeat report of one task. ``views`` are the task's channels in the order they were used (a reopened task's
    earlier channel first), each built from its journal; ``audits`` maps a channel uid to the signed task audit whose
    ``OVS-FID-*`` and ``OVS-TRN-*`` findings count as faults. With ``keyring`` every audit must verify under the audit key
    (``ValueError`` otherwise): an unverified audit's findings never count."""
    from .audit import verify_audit
    vs = list(views)
    if not vs:
        raise ValueError("no view: repeats are detected over the answers of one task")
    if any(v.degraded for v in vs):
        raise ValueError("repeats are detected only from journaled views; a degraded view has no reference copy")
    tasks = {v.task_id for v in vs}
    if len(tasks) != 1:
        raise ValueError("repeats are detected within one task: the views belong to different tasks")
    uids = [v.channel_uid for v in vs]
    if len(set(uids)) != len(uids):
        raise ValueError("a channel is given twice")
    audits = dict(audits or {})
    for uid, a in audits.items():
        if not isinstance(a, OverseerAudit) or a.channel_uid != uid or a.scope != "task":
            raise ValueError(f"the audit given for channel {uid} is not that channel's task audit")
        if keyring is not None and not verify_audit(a, keyring):
            raise ValueError(f"the task audit of channel {uid} does not verify under the audit key: its findings never count")
    first: dict[str, FaultOccurrence] = {}
    seen_count: dict[str, int] = {}
    occurrences: list[FaultOccurrence] = []
    repeats: list[RepeatRecord] = []
    findings: list[IntegrityFinding] = []
    counts: dict[str, int] = {}
    answers = 0
    quote_faults: dict[str, FaultOccurrence] = {}  # quoted phrase -> the first error-level quotation fault naming it
    for v in vs:
        audit = audits.get(v.channel_uid)
        for t in v.transfers:
            if t.kind not in ANSWER_KINDS or not t.message_id:
                continue
            answers += 1
            occs = fault_occurrences(v, t, audit)
            # rule quotation-anchor: an answer whose quotation a weaker check flags (a warning-level source rule, a parse-loss
            # warning) and which carries a quoted phrase an error-level source fault named earlier in the task repeats that
            # fault, whatever code catches it now (design 19.1: a fault that comes back, reworded or not)
            if quote_faults and _source_signal(t, audit):
                own = {o.signature for o in occs}
                for ph in sorted(_answer_phrases(t)):
                    f0 = quote_faults.get(ph)
                    if f0 is None or f0.message_id == t.message_id or f0.signature in own:
                        continue
                    own.add(f0.signature)
                    agent = t.sender_agent_id or (t.payload or {}).get("agent_id")
                    occs.append(FaultOccurrence(signature=f0.signature, code=f0.code, anchor_kind="quotation", anchor=f0.anchor, figures=list(f0.figures),
                                                channel_uid=v.channel_uid, seq=t.seq, message_id=t.message_id, receipt_id=t.receipt_id,
                                                agent_id=agent if isinstance(agent, str) else None, report_id=t.report_id, claim_ids=[], source="receipt"))
            for o in occs:
                if o.anchor_kind == "quotation" and o.signature not in first:
                    for ph in o.anchor.split(" | "):
                        quote_faults.setdefault(ph, o)
            for o in occs:
                occurrences.append(o)
                f0 = first.get(o.signature)
                if f0 is None:
                    first[o.signature] = o
                    seen_count[o.signature] = 1
                    continue
                seen_count[o.signature] += 1
                rec = RepeatRecord(signature=o.signature, code=o.code, anchor_kind=o.anchor_kind, anchor=o.anchor, figures=list(o.figures), message_id=o.message_id,
                                   agent_id=o.agent_id, report_id=o.report_id, channel_uid=o.channel_uid, seq=o.seq, first_message_id=f0.message_id,
                                   first_agent_id=f0.agent_id, first_report_id=f0.report_id, first_channel_uid=f0.channel_uid, first_seq=f0.seq,
                                   occurrence=seen_count[o.signature], same_agent=o.agent_id == f0.agent_id, result_ids=list(o.result_ids))
                repeats.append(rec)
                who = o.agent_id or "unknown"
                counts[who] = counts.get(who, 0) + 1
                shown = o.anchor if len(o.anchor) <= 120 else o.anchor[:117] + "..."
                how = "the same agent resubmitted it" if rec.same_agent else f"first given by agent {f0.agent_id}"
                findings.append(ovs_finding(
                    REPEAT_CODE,
                    f"repeated fault {o.code} ({o.anchor_kind} {shown!r}; figures {list(o.figures)}): answer {o.message_id} of agent {o.agent_id} repeats the "
                    f"fault of answer {f0.message_id} ({how}; occurrence {rec.occurrence} in task {v.task_id}); it is never delivered or consolidated",
                    message_ids=[o.message_id, f0.message_id], agent_ids=[o.agent_id, f0.agent_id], report_ids=[o.report_id, f0.report_id],
                    claim_ids=o.claim_ids, related_result_ids=o.result_ids))
    return RepeatReport(task_id=next(iter(tasks)), channel_uids=uids, answers=answers, occurrences=occurrences, repeats=repeats,
                        counts=dict(sorted(counts.items())), findings=findings)
