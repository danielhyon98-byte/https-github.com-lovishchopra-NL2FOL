"""L5 claim fidelity: are the delivered claims what the specialist actually said?

The checks run on the delivered payload against its own ``original_response`` (the specialist's text as received),
after the fixed fidelity normalisation of :func:`~epinoic_logic.overseer.checks.normalise` (NFKC; typographic quotes,
apostrophes and dashes folded; markdown emphasis and code markers, heading hashes and list bullets removed; whitespace
collapsed; no case folding, no similarity threshold). Named rules extending it, each with its own test:

* ``enclosing-quotes``: a claim that is a quotation is compared without one pair of quotation marks enclosing the
  whole claim (a parser closes an unbalanced quotation: ``"... a social code."`` from ``"... a social code. The``);
* ``folded-tail``: the tail claim an adapter folded the claims beyond its limit into (its ``unresolved_issues`` say
  so) passes when its text, without the truncation mark, is a prefix of a span of the normalised response, or each of
  its sentences occurs in it;
* ``trailing-punctuation``: for FID-004, a quotation is also located without the punctuation that closes it inside
  the marks (``"from the barbarous work of death."`` quotes "from the barbarous work of death," of the source: the full
  stop belongs to the quoting sentence);
* ``contract-cut``: a claim the adapter cut at the contract limit (``MAX_CLAIM_TEXT_CHARS``, marked with ``...``) is
  compared without the mark, as a prefix of a span of the response.

* FID-001: a delivered ``claim_text`` does not occur in the normalised response.
* FID-002: a quotation span inside a claim, or a ``source_refs[].excerpt``, does not occur in the response.
* FID-003: a figure or date of a claim (``ledger.figure_spellings``) occurs in the response under no spelling.
* FID-004: a quotation that occurs in no supplied text has no receipt finding naming that claim (INT-REQ-003,
  INT-REQ-010, INT-REQ-013, INT-SUBJ-003 for a source rule, or a branch ``-SRC-`` rule), nor any other claim of the
  report that carries the same quotation (a sentence claim and its evidence claim quote the same words; the receipt
  names one of them).
* FID-005: a self-report delivered as content: the claim carries ``advisory_verification_status`` or
  ``advisory_verification_eligibility``, or the branch's own detector (``adapters.markdown.is_self_certification``)
  flags it, and it is delivered with a role other than ``other``, with materiality ``material``, or counts towards
  coverage.
* FID-006 (warning): parse loss: a quoted span or figure of the response that no claim carries and no INT-REQ-013
  fold accounts for (markdown heading lines and list numbering are structure and are not scanned).
* FID-007 (warning): quotations checked only against texts the specialist supplied itself (the request carried none).
* FID-008: a supplied text in the report, under a document id the request supplied, differs from the request's text.
* FID-009 (warning): only the auditor's independent structural detector (``selfcert``) flags a self-certification
  delivered as content.
"""
from __future__ import annotations

import re
from typing import Optional

from ...adapters.markdown import MAX_CLAIM_TEXT_CHARS, find_quotation_spans, is_self_certification
from ...channel.bus import _FOLDED_TAIL_RE, _located
from ...integrity.ledger import figure_spellings
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText
from ..view import REPORT_KINDS, Transfer
from . import CheckContext, normalise
from .selfcert import flags_self_certification

__all__ = ["check_fidelity", "claim_occurs", "strip_enclosing_quotes", "strip_trailing_punctuation", "located_anywhere", "FIDELITY_RULES"]

FIDELITY_RULES = ("enclosing-quotes", "folded-tail", "trailing-punctuation", "contract-cut")
_QUOTE_CHARS = "\"'‘’“”«»"
_TRUNC_MARKS = ("...", "…")
_SOURCE_CODES = ("INT-REQ-003", "INT-REQ-010", "INT-REQ-013")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_HEADING_LINE_RE = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+.*$")


def strip_enclosing_quotes(text: str) -> str:
    """Named rule ``enclosing-quotes``: one pair of quotation marks enclosing the whole claim is not compared."""
    t = text.strip()
    if len(t) >= 2 and t[0] in _QUOTE_CHARS and t[-1] in _QUOTE_CHARS:
        return t[1:-1].strip()
    if len(t) >= 3 and t[0] in _QUOTE_CHARS and t[-2] in _QUOTE_CHARS and t[-1] in ".,;:!?":
        return t[1:-2].strip()
    return t


def _folded_tail_ids(report: SpecialistReport) -> set[str]:
    out = set()
    for issue in report.unresolved_issues:
        m = _FOLDED_TAIL_RE.search(issue)
        if m:
            out.add(m.group("tail"))
    return out


def claim_occurs(claim_text: str, norm_response: str, *, tail: bool = False) -> bool:
    n = normalise(claim_text)
    if n and n in norm_response:
        return True
    s = normalise(strip_enclosing_quotes(claim_text))
    if s and s in norm_response:
        return True
    stripped = claim_text.rstrip()
    if len(stripped) >= MAX_CLAIM_TEXT_CHARS - 3 and stripped.endswith("..."):  # named rule contract-cut
        cut = normalise(stripped[:-3])
        if cut and cut in norm_response:
            return True
    if tail:
        t = n
        for mark in _TRUNC_MARKS:
            if t.endswith(mark):
                t = t[: -len(mark)].rstrip()
        if t and t in norm_response:
            return True
        parts = [p.strip() for p in _SENT_SPLIT.split(t) if p.strip()]
        return bool(parts) and all(p in norm_response for p in parts)
    return False


def _supplied_for(ctx: CheckContext, t: Transfer, rep: SpecialistReport) -> tuple[list[SuppliedText], bool, bool]:
    """(texts the channel checked quotations against, request carried texts, report texts came from the specialist)."""
    req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
    req_texts = list(req.supplied_texts) if req is not None else []
    if t.kind == "response_text":
        override = t.call.get("supplied_texts")
        if override is not None:
            return list(rep.supplied_texts), bool(req_texts), False
        return req_texts or list(rep.supplied_texts), bool(req_texts), False
    if t.kind == "relay_report":
        return list(rep.supplied_texts), True, False
    return req_texts or list(rep.supplied_texts), bool(req_texts), True


def _named_claims(t: Transfer) -> set[str]:
    """Claims a source finding of the receipt names (INT-REQ-003/010/013, INT-SUBJ-003 for a source rule, a branch
    ``-SRC-`` rule)."""
    rc = t.receipt
    out: set[str] = set()
    if rc is None:
        return out
    for f in rc.findings:
        if f.code in _SOURCE_CODES or (f.code == "INT-SUBJ-003" and "-SRC-" in f.message):
            out.update(f.claim_ids)
    for sf in rc.structural_findings:
        if "-SRC-" in sf.code:
            out.update(sf.claim_ids)
    return out


def _accounted(rep: SpecialistReport, quote: str, named: set[str]) -> bool:
    """A quotation is accounted for when a source finding names a claim of the report that carries the same quotation
    (as a quoted span or an excerpt; one containing the other, after normalisation)."""
    q = normalise(quote)
    for c in rep.claims:
        if c.claim_id not in named:
            continue
        for other in _quotations(c):
            o = normalise(other)
            if o and (q in o or o in q):
                return True
    return False


_TRAILING_PUNCT = ".,;:!?\u2026 "


def strip_trailing_punctuation(q: str) -> str:
    """Named rule ``trailing-punctuation``: the punctuation closing a quotation inside its marks is the quoting
    sentence's."""
    return q.rstrip(_TRAILING_PUNCT)


def located_anywhere(q: str, supplied: list[SuppliedText]) -> bool:
    """The channel's own locator (exact, normalised, elided, form difference, long elision), with and without the
    closing punctuation."""
    cands = [q] + ([strip_trailing_punctuation(q)] if strip_trailing_punctuation(q) and strip_trailing_punctuation(q) != q else [])
    return any(_located(x, s.text, s.document_id) for x in cands for s in supplied)


def _quotations(c: ClaimRecord) -> list[str]:
    out = [inner.strip() for _s, _e, inner in find_quotation_spans(c.claim_text) if inner.strip()]
    out += [(r.excerpt or "").strip() for r in c.source_refs if (r.excerpt or "").strip()]
    return list(dict.fromkeys(out))


def check_fidelity(ctx: CheckContext, t: Transfer) -> None:
    if t.kind not in REPORT_KINDS or not t.delivered or t.digest_only:
        return
    rep = t.report
    if rep is None:
        return
    ids = t.ids()
    norm_resp = normalise(rep.original_response)
    tails = _folded_tail_ids(rep)
    known_figs: set[str] = set()
    for _label, keys in figure_spellings(rep.original_response):
        known_figs |= keys
    claim_figures = {c.claim_id: figure_spellings(c.claim_text) for c in rep.claims}
    covering = {cid for cov in (t.receipt.coverage if t.receipt else []) for cid in cov.addressed_by_claim_ids}
    supplied, req_had_texts, self_supplied = _supplied_for(ctx, t, rep)
    named = _named_claims(t)
    ctx.coverage.claims_checked += len(rep.claims)
    claim_texts_norm: list[str] = []
    for c in rep.claims:
        cid = [c.claim_id]
        claim_texts_norm.append(normalise(c.claim_text))
        # FID-001
        if not claim_occurs(c.claim_text, norm_resp, tail=c.claim_id in tails):
            ctx.ovs(t.seq, "OVS-FID-001", f"claim {c.claim_id} of report {rep.report_id} does not occur in the specialist's original_response: {c.claim_text[:160]!r}",
                    claim_ids=cid, **ids)
        # FID-002
        absent = [q for q in _quotations(c) if normalise(q) not in norm_resp and normalise(strip_enclosing_quotes(q)) not in norm_resp]
        if absent and c.claim_id not in tails:
            ctx.ovs(t.seq, "OVS-FID-002", f"claim {c.claim_id} carries quotations or excerpts the original_response does not contain: {[q[:80] for q in absent[:4]]}",
                    claim_ids=cid, document_ids=[r.document_id for r in c.source_refs], **ids)
        # FID-003
        lost = [label for label, keys in claim_figures[c.claim_id] if not (keys & known_figs)]
        if lost and c.claim_id not in tails:
            ctx.ovs(t.seq, "OVS-FID-003", f"claim {c.claim_id} states figures or dates the original_response states under no spelling: {lost[:6]}", claim_ids=cid, **ids)
        # FID-004
        if supplied:
            unlocated = [q for q in _quotations(c) if not located_anywhere(q, supplied)]
            unlocated = [q for q in unlocated if c.claim_id not in named and not _accounted(rep, q, named)]
            if unlocated:
                ctx.ovs(t.seq, "OVS-FID-004", f"claim {c.claim_id} quotes {[q[:80] for q in unlocated[:4]]}, which occur in no supplied text, and no receipt finding names the claim",
                        claim_ids=cid, document_ids=[s.document_id for s in supplied], **ids)
        # FID-005 / FID-009
        as_content = c.claim_role != "other" or c.materiality == "material" or c.claim_id in covering
        if as_content:
            self_report = c.advisory_verification_status is not None or c.advisory_verification_eligibility is not None or is_self_certification(c.claim_text)
            if self_report:
                ctx.ovs(t.seq, "OVS-FID-005", f"claim {c.claim_id} is a self-report or self-certification delivered as content (role {c.claim_role}, materiality {c.materiality}"
                        + (", counted towards coverage" if c.claim_id in covering else "") + ")", claim_ids=cid, **ids)
            elif flags_self_certification(c.claim_text):
                ctx.ovs(t.seq, "OVS-FID-009", f"claim {c.claim_id} reads as a self-certification of the answer's own items (auditor's structural detector) but is delivered as content "
                        f"(role {c.claim_role}, materiality {c.materiality})", claim_ids=cid, **ids)
    # FID-006: parse loss
    folded = any(f.code == "INT-REQ-013" for f in (t.receipt.findings if t.receipt else []))
    if not folded:
        carried = " \u0000 ".join(claim_texts_norm + [normalise(r.excerpt or "") for c in rep.claims for r in c.source_refs])
        lost_quotes = [inner.strip() for _s, _e, inner in find_quotation_spans(rep.original_response)
                       if inner.strip() and normalise(inner) not in carried and normalise(strip_enclosing_quotes(inner)) not in carried]
        claim_figs: set[str] = set()
        for spellings in claim_figures.values():
            for _l, keys in spellings:
                claim_figs |= keys
        content = normalise(_HEADING_LINE_RE.sub("", rep.original_response))  # headings and list numbering are structure, not content
        lost_figs = [label for label, keys in figure_spellings(content) if not (keys & claim_figs)]
        if lost_quotes or lost_figs:
            ctx.ovs(t.seq, "OVS-FID-006", f"report {rep.report_id}: response content no claim carries (parse loss): quotations {[q[:60] for q in lost_quotes[:6]]}, figures {lost_figs[:8]}", **ids)
    # FID-007 / FID-008
    if not req_had_texts and self_supplied and rep.supplied_texts and any(c.source_refs or find_quotation_spans(c.claim_text) for c in rep.claims):
        ctx.ovs(t.seq, "OVS-FID-007", f"report {rep.report_id}: the request supplied no text, so its quotations were checked only against texts the specialist supplied itself "
                f"({sorted(s.document_id for s in rep.supplied_texts)})", document_ids=[s.document_id for s in rep.supplied_texts], **ids)
    req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
    if req is not None:
        req_docs = {s.document_id: s.text for s in req.supplied_texts}
        changed = sorted(s.document_id for s in rep.supplied_texts if s.document_id in req_docs and s.text != req_docs[s.document_id])
        if changed:
            ctx.ovs(t.seq, "OVS-FID-008", f"report {rep.report_id} carries supplied texts {changed} that differ from the texts the request supplied under those ids",
                    document_ids=changed, **ids)
