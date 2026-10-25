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
  compared without the mark, as a prefix of a span of the response; its figures (FID-003) and quotations (FID-002,
  FID-004) are read without the mark and without the partial token left at the cut;
* ``joined-list-markers`` (in the normalisation): list markers an adapter's line join left inside a claim are removed
  on both sides alike, and list numbering is never read as a stated figure (FID-003);
* ``context-free`` (review round 2): FID-001 first compares the claim and the response in the plain form (invisible
  characters, NFKC, quotes, dashes, emphasis and whitespace only; no list-marker stripping), so a claim that occurs
  verbatim is never failed because the normalisation strips a list marker in context on one side only (bold numbering
  ``**2.**``, items without full stops, a bullet after a closing quotation mark, inline numbering ``1. X. 2. Y.``);
* ``carried-list-number`` (review round 2): a list number at the start or the end of a claim that the response uses as a
  list marker is structure, not a figure the claim states (FID-003); so is one after a colon inside the claim (the merged
  translator's English adapter joins "were:" and the item lines below it into one claim, "were: 1. Reparations ... 2."),
  again only when the response uses that number as a list marker;
* ``invisible`` (in the normalisation, review round 2): format and default-ignorable characters (a U+FEFF where two chunks
  were joined) are removed on both sides;
* ``mark-annotation`` (the translator merge): the generic and STEM parsers remove a mark annotation from the claim that
  ends with it ("[1]", "[1 spare]", "[2 marks]", "(3 marks)", "(M1)", "(A1)", "M1" after two spaces; ``original_response``
  keeps them), so FID-001 also compares a claim with the response read without the annotations that end a sentence or a
  line (the parsers' own patterns, ``branches.generic_parser``), and FID-006 never reads a mark annotation as a figure
  the parse lost. Since the STEM completion (decision 60) the response is read line by line with the parsers' own rule as
  well (``stem.layout.annotation_ranges``, the generic parser's patterns restated, which a test keeps identical): it also
  removes an annotation that closes a sentence inside a line, before the next sentence ("... an increase of 100% [1] Mean
  uptake = ..."), and a sentence that is nothing but annotations; the claim is compared with the response read either way;
* ``same-form-figures`` (the translator merge, FID-006): the figures the claims carry are read in the same comparison
  form as the response's content (normalised: a U+2212 minus, a superscript power), as well as as written, so a figure a
  claim carries is never reported as lost for its spelling alone;
* ``no-quotation-to-verify`` (the translator merge, FID-004): the merged core pack's own rule (round 7) for quoted words
  that are no quotation to verify, applied as the pack applies it: words the request itself holds (located in the
  journaled request by the channel's locator: a guiding question's "returning home", a true/false statement's "toda"), and
  a word the sentence says the text lacks ('has no "like" or "as"', 'never says "ayudar"': a mention, read by the pack's
  ``_absent_mentions``).

* FID-001: a delivered ``claim_text`` does not occur in the normalised response (rule ``raw-occurrence``: a claim that
  occurs in the raw response as written, or whose comparison forms are all empty, always occurs).
* FID-002: a quotation span inside a claim, or a ``source_refs[].excerpt``, does not occur in the response.
* FID-003: a figure or date of a claim (``ledger.figure_spellings``) occurs in the response under no spelling.
* FID-004: a quotation that occurs in no supplied text has no receipt finding naming that claim (INT-REQ-003,
  INT-REQ-010, INT-REQ-013, INT-SUBJ-003 for a source rule, or a branch ``-SRC-`` rule), nor any other claim of the
  report that carries the same quotation (a sentence claim and its evidence claim quote the same words; the receipt
  names one of them); quoted words that are no quotation to verify (rule ``no-quotation-to-verify``) are not read.
* FID-005: a self-report delivered as content: the branch's own detector (``adapters.markdown.is_self_certification``)
  flags its TEXT read with its quotations masked (``mask_quotations``, as the adapters read it: a quoted claim of
  accuracy belongs to the supplied text, rule ``quoted-certification``), or (raw-text path) the adapter set ``advisory_verification_status`` or
  ``advisory_verification_eligibility`` yet roled it as content, and it is delivered with a role other than ``other``,
  with materiality ``material``, or counts towards coverage. On a structured report the advisory fields alone are the
  contract's ignored self-report (INT-HANDOFF-006): FID-009, a warning (review round 2).
* FID-006 (warning): parse loss: a quoted span, figure or sentence of the response that no claim carries and no
  INT-REQ-013 fold accounts for (markdown heading lines and list numbering are structure and are not scanned; a
  sentence counts when it has five words or more, does not end with a colon, and neither occurs in the claims nor
  contains one).
* CUST-006 (re-parse, with L5): a ``response_text`` is re-parsed by the auditor with the branch adapter its registry
  gives the agent's subject, on the journaled raw text and the journaled call; a delivered report whose claims (ids,
  texts, roles, materiality) are not the re-parse's is not what the hub received: an adapter that drops, adds or
  rewrites a claim (a judgement sentence with no quotation and no figure) is named, whatever the shadow's sampling.
  Rule ``request-text``: a parser that declares ``accepts_request_text`` (the STEM branches' parser, whose claims and
  planned check ids depend on the request) is given the journaled request's ``user_input``, as the channel gives it, so
  a STEM answer is re-parsed exactly as it was parsed (whatever id scheme the parser uses: ``g``, ``h``, ``s``, ``m``,
  ``c``, agent-qualified ids).
* FID-007 (warning): quotations checked only against texts the specialist supplied itself (the request carried none).
* FID-008: a supplied text in the report, under a document id the request supplied, differs from the request's text.
* FID-009 (warning): only the auditor's independent structural detector (``selfcert``) flags a self-certification
  delivered as content.
"""
from __future__ import annotations

import re
from typing import Optional

from ...adapters.markdown import MAX_CLAIM_TEXT_CHARS, find_quotation_spans, is_self_certification, mask_quotations
from ...adapters.sources import check_excerpt
from ...branches.generic_parser import _MARK_ALLOC, _MARK_CODE
from ...branches.packs import _absent_mentions, _quote_key
from ...channel.bus import _CHECK_OUTCOME_RE, _CHECK_SUBJECT_RE, _FOLDED_TAIL_RE, _located
from ...integrity.ledger import figure_spellings
from ...stem.layout import annotation_ranges
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText
from ..view import REPORT_KINDS, RESPONSE_KINDS, Transfer
from . import CheckContext, normalise, plain_form, strip_list_markers
from .selfcert import flags_self_certification

__all__ = ["check_fidelity", "check_reparse", "claim_occurs", "strip_enclosing_quotes", "strip_trailing_punctuation", "located_anywhere", "FIDELITY_RULES",
           "uncut_text", "response_list_numbers", "strip_mark_annotations", "no_quotation_to_verify"]

FIDELITY_RULES = ("enclosing-quotes", "folded-tail", "trailing-punctuation", "contract-cut", "joined-list-markers", "context-free", "carried-list-number",
                  "invisible", "mark-annotation", "same-form-figures", "no-quotation-to-verify")
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


def _is_cut(text: str) -> bool:
    stripped = (text or "").rstrip()
    return len(stripped) >= MAX_CLAIM_TEXT_CHARS - 3 and stripped.endswith("...")


def uncut_text(text: str) -> str:
    """Rule ``contract-cut``: a claim cut at the contract limit, without the mark and the partial token left at the cut
    (the claim's figures and quotations are read from this)."""
    if not _is_cut(text):
        return text
    body = text.rstrip()[:-3]
    return body.rsplit(None, 1)[0] if len(body.split()) > 1 else ""


#: A list number the response sets out as a list marker: at the start of a line, or left after sentence or colon
#: punctuation by an inline list ("Answers: 1. X. 2. Y."), optionally in bold or in brackets.
_RESPONSE_LIST_NUMBER_RE = re.compile(r"(?:(?m:^)[ \t]*|(?<=[.:;!?])[ \t]+)(?:\*\*|__)?\(?(\d{1,3})[.)](?:\*\*|__)?(?=\s|$)")
#: A list number at the start or the end of a claim (an adapter's line join or item cut carried it into the claim).
_LEAD_NUMBER_RE = re.compile(r"^\s*(?:\*\*|__)?\(?(\d{1,3})[.)](?:\*\*|__)?(?=\s|$)")
#: A list number an adapter's line join left after a colon inside a claim ("were: 1. Reparations ...").
_AFTER_COLON_NUMBER_RE = re.compile(r"(?<=:)[ \t]+(?:\*\*|__)?\(?(\d{1,3})[.)](?:\*\*|__)?(?=\s|$)")
_TRAIL_NUMBER_RE = re.compile(r"(?:(?<=\s)|^)(?:\*\*|__)?\(?(\d{1,3})[.)](?:\*\*|__)?\s*$")


def response_list_numbers(response: str) -> set[str]:
    """The numbers ``response`` uses as list markers (named rule ``carried-list-number``)."""
    return {m.group(1) for m in _RESPONSE_LIST_NUMBER_RE.finditer(response or "")}


#: Rule ``mark-annotation``: a run of mark annotations (the generic and STEM parsers' own patterns: a mark allocation, a
#: mark code in brackets or after two spaces) that ends a sentence or a line.
_MARK_ANNOTATION_RE = re.compile(rf"(?:[ \t]*{_MARK_ALLOC}|(?:[ \t]{{2,}}|\t)\(?{_MARK_CODE}\)?|[ \t]*\({_MARK_CODE}\))+(?=[.;,]?[ \t]*$|\.[ \t])", re.MULTILINE)


def _parser_unmarked(text: str) -> str:
    """``text`` without the mark annotations the parsers' own line rule finds (``stem.layout.annotation_ranges``: those
    closing the line, those closing one of its sentences, sentences of annotations alone), line by line."""
    out: list[str] = []
    for line in (text or "").split("\n"):
        ranges = annotation_ranges(line)
        if not ranges:
            out.append(line)
            continue
        pieces, pos = [], 0
        for a, b in ranges:
            pieces.append(line[pos:a])
            pos = max(pos, b)
        pieces.append(line[pos:])
        out.append("".join(pieces))
    return "\n".join(out)


def strip_mark_annotations(text: str) -> str:
    """``text`` without the mark annotations that end a sentence or a line (rule ``mark-annotation``): what the generic and
    STEM parsers leave out of a claim ("only 9 [1]." is delivered as "only 9."; "100% [1] Mean uptake = ..." as "100% Mean
    uptake = ..."), read with the parsers' line rule and then with this module's pattern."""
    return _MARK_ANNOTATION_RE.sub("", _parser_unmarked(text or ""))


def no_quotation_to_verify(quotations: list[str], request_text: Optional[str], mention_keys: set[str]) -> list[str]:
    """Rule ``no-quotation-to-verify``: the quotations among ``quotations`` that the merged core pack does not treat as
    quotations to verify: located in the request (the channel's locator, with and without the closing punctuation), or a
    mention whose sentence says the text lacks it (``mention_keys``, by the pack's quotation key)."""
    out: list[str] = []
    req = {"the request": SuppliedText(document_id="the request", title=None, author="router", text=request_text)} if request_text and request_text.strip() else None
    for q in quotations:
        if _quote_key(q) in mention_keys:
            out.append(q)
            continue
        if req is not None and any(check_excerpt(x, "the request", req).located for x in dict.fromkeys([q, strip_trailing_punctuation(q)]) if x):
            out.append(q)
    return out


def _strip_carried_numbers(text: str, list_numbers: set[str]) -> str:
    """Rule ``carried-list-number``: a list number at the start or the end of a claim that the response uses as a list
    marker is list structure carried into the claim, never a figure the claim states."""
    t = text
    m = _LEAD_NUMBER_RE.match(t)
    if m and m.group(1) in list_numbers:
        t = t[m.end():]
    t = _AFTER_COLON_NUMBER_RE.sub(lambda x: " " if x.group(1) in list_numbers else x.group(0), t)
    m = _TRAIL_NUMBER_RE.search(t)
    if m and m.group(1) in list_numbers:
        t = t[:m.start()]
    return t


def _claim_figures(text: str, list_numbers: set[str] = frozenset()):
    return figure_spellings(strip_list_markers(_strip_carried_numbers(uncut_text(text), set(list_numbers))))


def claim_occurs(claim_text: str, norm_response: str, *, tail: bool = False, plain_response: Optional[str] = None,
                 raw_response: Optional[str] = None) -> bool:
    """Whether a claim occurs in its response. Rule ``raw-occurrence`` first: a claim whose text occurs in the raw
    response as written always occurs, whatever its comparison forms are (a markdown thematic break "***" delivered as the
    claim "*", or a paragraph of zero-width characters, has EMPTY comparison forms, and an empty form never decides that
    a claim is absent). Then rule ``context-free``: a claim that occurs verbatim (in the plain comparison form,
    :func:`~epinoic_logic.overseer.checks.plain_form`, with no list-marker stripping) always occurs; the fidelity
    normalisation's list-marker and heading rules only ACCEPT further matches, never reject a verbatim one."""
    raw = claim_text.strip()
    if raw_response is not None and raw and raw in raw_response:
        return True
    if not plain_form(claim_text) and not normalise(claim_text):
        # every comparison form is empty: the claim is structure (only markup or invisible characters), never content the
        # response lacks; an empty form never decides absence
        return True
    if plain_response is not None:
        p = plain_form(claim_text)
        if p and p in plain_response:
            return True
        q = plain_form(strip_enclosing_quotes(claim_text))
        if q and q in plain_response:
            return True
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


def _request_text(ctx: CheckContext, t: Transfer) -> Optional[str]:
    """The journaled request's ``user_input`` the channel gave the branch packs for this report (None without a request)."""
    req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
    return req.user_input if req is not None else None


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
    out = [inner.strip() for _s, _e, inner in find_quotation_spans(uncut_text(c.claim_text)) if inner.strip()]
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
    plain_resp = plain_form(rep.original_response)
    # rule mark-annotation: the response as the generic and STEM parsers read a claim from it (mark annotations removed)
    unmarked = strip_mark_annotations(rep.original_response)
    unmarked_forms = (normalise(unmarked), plain_form(unmarked)) if unmarked != rep.original_response else None
    tails = _folded_tail_ids(rep)
    known_figs: set[str] = set()
    for _label, keys in figure_spellings(rep.original_response):
        known_figs |= keys
    list_numbers = response_list_numbers(rep.original_response)
    claim_figures = {c.claim_id: _claim_figures(c.claim_text, list_numbers) for c in rep.claims}
    covering = {cid for cov in (t.receipt.coverage if t.receipt else []) for cid in cov.addressed_by_claim_ids}
    supplied, req_had_texts, self_supplied = _supplied_for(ctx, t, rep)
    named = _named_claims(t)
    request_text = _request_text(ctx, t)
    mention_keys = {_quote_key(q) for q in _absent_mentions(rep.original_response, find_quotation_spans(rep.original_response))}
    ctx.coverage.claims_checked += len(rep.claims)
    claim_texts_norm: list[str] = []
    for c in rep.claims:
        cid = [c.claim_id]
        claim_texts_norm.append(normalise(c.claim_text))
        # FID-001
        if not claim_occurs(c.claim_text, norm_resp, tail=c.claim_id in tails, plain_response=plain_resp, raw_response=rep.original_response) and not (
                unmarked_forms is not None and claim_occurs(strip_mark_annotations(c.claim_text), unmarked_forms[0], tail=c.claim_id in tails,
                                                            plain_response=unmarked_forms[1], raw_response=unmarked)):
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
            if unlocated:  # rule no-quotation-to-verify: the merged core pack's own reading of quoted words
                exempt = no_quotation_to_verify(unlocated, request_text, mention_keys)
                unlocated = [q for q in unlocated if q not in exempt]
            if unlocated:
                ctx.ovs(t.seq, "OVS-FID-004", f"claim {c.claim_id} quotes {[q[:80] for q in unlocated[:4]]}, which occur in no supplied text, and no receipt finding names the claim",
                        claim_ids=cid, document_ids=[s.document_id for s in supplied], **ids)
        # FID-005 / FID-009
        as_content = c.claim_role != "other" or c.materiality == "material" or c.claim_id in covering
        if as_content:
            advisory = c.advisory_verification_status is not None or c.advisory_verification_eligibility is not None
            # read with quotations masked, as the adapters decide notes and self-reports: a sentence QUOTING a supplied
            # text's own claim of accuracy (a brochure's "every figure has been verified", a narrator's) is analysis of that
            # text, not the specialist certifying its answer, and a claim that is only such a quotation is evidence
            text_self = is_self_certification(mask_quotations(c.claim_text))
            # the advisory fields are the contract's "agent self-report; ignored, recorded for audit" (INT-HANDOFF-006): on a
            # structured report they are the specialist's own record, so the field alone is a warning; the TEXT being a
            # self-certification delivered as content, or an adapter that set the field yet roled the claim as content (raw
            # text), is FID-005
            if text_self or (advisory and t.kind == "response_text"):
                ctx.ovs(t.seq, "OVS-FID-005", f"claim {c.claim_id} is a self-report or self-certification delivered as content (role {c.claim_role}, materiality {c.materiality}"
                        + (", counted towards coverage" if c.claim_id in covering else "") + ")", claim_ids=cid, **ids)
            elif advisory:
                ctx.ovs(t.seq, "OVS-FID-009", f"claim {c.claim_id} of a structured report carries the contract's advisory self-report fields (ignored, recorded by "
                        f"INT-HANDOFF-006) while delivered as content (role {c.claim_role}, materiality {c.materiality}); its text is not a self-certification",
                        claim_ids=cid, **ids)
            elif flags_self_certification(c.claim_text):
                ctx.ovs(t.seq, "OVS-FID-009", f"claim {c.claim_id} reads as a self-certification of the answer's own items (auditor's structural detector) but is delivered as content "
                        f"(role {c.claim_role}, materiality {c.materiality})", claim_ids=cid, **ids)
    # FID-009 (relayed check results): a dependent agent (a peer report or a specialist-authored text was supplied) that
    # states, as a claim of its own, a check result credited to the system or to a report ("A formal check failed the
    # report's restated 0.1 pH result", "the Mathematics report's own checks flag its written lines as not holding"). A
    # relayed check result is a self-report (advisory), never evidence: the channel names it with INT-REQ-014 (every
    # claim read, notes included, quotations masked); a receipt with no INT-REQ-014 naming such a claim is FID-009.
    _relayed_check_results(ctx, t, rep, supplied, ids)
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
        for text_norm in claim_texts_norm:  # rule same-form-figures: the claims' figures in the content's comparison form too
            for _l, keys in figure_spellings(text_norm):
                claim_figs |= keys
        # headings and list numbering are structure, not content; so are mark annotations (rule mark-annotation)
        content = normalise(_HEADING_LINE_RE.sub("", strip_mark_annotations(rep.original_response)))
        lost_figs = [label for label, keys in figure_spellings(content) if not (keys & claim_figs)]
        lost_sentences = _uncarried_sentences(content, claim_texts_norm, carried)
        if lost_quotes or lost_figs or lost_sentences:
            ctx.ovs(t.seq, "OVS-FID-006", f"report {rep.report_id}: response content no claim carries (parse loss): quotations {[q[:60] for q in lost_quotes[:6]]}, "
                    f"figures {lost_figs[:8]}, sentences {[x[:80] for x in lost_sentences[:4]]}", **ids)
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


def _dependent_texts(supplied: list[SuppliedText]) -> bool:
    """Whether the texts the channel checked against hold a relayed peer report (``peer:<task>``) or a text a specialist
    wrote (its author ends in "-specialist" or " specialist"): the channel's condition for reading relayed check results."""
    return any(s.document_id.startswith("peer:") or (s.author or "").strip().lower().endswith(("-specialist", " specialist")) for s in supplied)


def _relayed_check_results(ctx: CheckContext, t: Transfer, rep: SpecialistReport, supplied: list[SuppliedText], ids: dict) -> None:
    """OVS-FID-009 for a delivered claim of a dependent agent that states a check result credited to the system or to a
    report (the channel's ``_CHECK_SUBJECT_RE`` and ``_CHECK_OUTCOME_RE``, quotations masked) while the receipt carries
    no INT-REQ-014 naming the claim: the Overseer's own reading of the channel's rule, so a channel that fails to name
    the self-report is caught. Advisory: a relayed check result is a self-report, never evidence. Read on the response
    paths only, where the channel runs the rule (a relay hands on a report already delivered and named)."""
    if t.kind not in RESPONSE_KINDS or not _dependent_texts(supplied):
        return
    named = {cid for f in (t.receipt.findings if t.receipt else []) if f.code == "INT-REQ-014" for cid in f.claim_ids}
    for c in rep.claims:
        if c.claim_id in named:
            continue
        text = c.claim_text
        for start, end, _inner in reversed(find_quotation_spans(text)):  # masked as the channel masks them (spaces)
            text = text[:start] + " " * (end - start) + text[end:]
        noun = _CHECK_SUBJECT_RE.search(text)
        if noun is None or _CHECK_OUTCOME_RE.search(text) is None:
            continue
        ctx.ovs(t.seq, "OVS-FID-009", f"claim {c.claim_id} (role {c.claim_role}) states a check result credited to the system or to a report ({noun.group(0)!r}) "
                "and no INT-REQ-014 on the receipt names it: a relayed check result is a self-report (advisory), never evidence",
                claim_ids=[c.claim_id], **ids)


def _uncarried_sentences(content: str, claim_texts_norm: list[str], carried: str) -> list[str]:
    """Sentences of the normalised response (five words or more, not a lead-in ending with a colon) that occur in no claim
    and contain none."""
    claims = [c for c in (normalise(strip_enclosing_quotes(x)) for x in claim_texts_norm) if len(c) >= 12] + [c for c in claim_texts_norm if len(c) >= 12]
    out: list[str] = []
    for sent in _SENT_SPLIT.split(content):
        sent = sent.strip()
        if len(sent.split()) < 5 or sent.endswith(":"):
            continue
        core = sent.rstrip(".!?;:").strip()
        if sent in carried or core in carried or any(c in sent or c.rstrip(".!?;:") in sent for c in claims):
            continue
        out.append(sent)
    return out


def _reparse_args(ctx: CheckContext, t: Transfer, rep: SpecialistReport) -> Optional[dict]:
    plan = ctx.view.plan_at(t.seq)
    call = t.call or {}
    agent = call.get("agent_id") or rep.agent_id
    if plan is None or not agent:
        return None
    req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
    texts = call.get("supplied_texts")
    if texts is not None:
        supplied = [SuppliedText.model_validate(x) for x in texts]
    else:
        supplied = list(req.supplied_texts) if req is not None else []
    return dict(request_id=plan.request_id, task_id=plan.task_id, report_id=call.get("report_id") or rep.report_id,
                subject=plan.agent_subjects.get(agent, plan.subject), task_type=plan.agent_task_types.get(agent, plan.task_type), supplied_texts=supplied,
                course_level=plan.course_level or "unknown", agent_version=call.get("agent_version"), agent_id=agent)


def _claim_key(c: ClaimRecord) -> tuple:
    """The whole claim as the comparison key (every field: text, role, materiality, certainty, source references,
    supporting and parent ids, the proposed kind and the advisory fields): a parse stage that changes any of them (a
    hedged "may have" delivered as ``established``) delivers a report the raw text does not yield."""
    from ...ir.canonical import canonical_json
    return (c.claim_id, canonical_json(c.model_dump(mode="json")))


def _changed_fields(a: ClaimRecord, b: ClaimRecord) -> list[str]:
    da, db = a.model_dump(mode="json"), b.model_dump(mode="json")
    return sorted(k for k in set(da) | set(db) if da.get(k) != db.get(k))


def check_reparse(ctx: CheckContext, t: Transfer) -> None:
    """CUST-006: a delivered ``response_text`` is re-parsed from its journaled raw text by the branch adapter the auditor's
    registry gives the agent's subject; its claims must be the delivered report's."""
    if t.kind != "response_text" or not t.delivered or t.digest_only or t.raw_text is None:
        return
    rep = t.report
    if rep is None:
        return
    args = _reparse_args(ctx, t, rep)
    if args is None:
        return
    registry = ctx.registry
    if registry is None:
        from ...branches import default_registry
        registry = default_registry()
    branch = registry.for_subject(args["subject"])[0]
    try:
        parser = branch.parser()
        # rule ``request-text`` (STEM readiness): a parser that declares ``accepts_request_text`` (the STEM branches' parser,
        # which reads the answer and the request as one document) is given the journaled request's text, exactly as the
        # channel gives it; any other parser is called as before
        req = ctx.view.by_seq[t.request_seq].request if t.request_seq is not None and t.request_seq in ctx.view.by_seq else None
        extra = {"request_text": req.user_input} if (req is not None and getattr(parser, "accepts_request_text", False) is True) else {}
        again = parser.parse_response(t.raw_text, **args, **extra)
    except Exception as exc:
        ctx.ovs(t.seq, "OVS-CUST-006", f"the raw text of {t.kind} {t.message_id} does not parse with branch {branch.key} when the auditor re-parses it "
                f"({type(exc).__name__}), yet a parsed report was delivered", **t.ids())
        return
    mine = [_claim_key(c) for c in rep.claims]
    theirs = [_claim_key(c) for c in again.claims]
    if mine == theirs:
        return
    gone = [k[0] for k in theirs if k not in mine]
    added = [k[0] for k in mine if k not in theirs]
    by_id = {c.claim_id: c for c in again.claims}
    fields = sorted({f for c in rep.claims if c.claim_id in by_id and c.claim_id in added for f in _changed_fields(c, by_id[c.claim_id])})
    ctx.ovs(t.seq, "OVS-CUST-006", f"the report delivered by {t.kind} {t.message_id} is not what branch {branch.key} parses from its raw text: claims "
            f"{gone[:8]} of the re-parse are missing or differ, claims {added[:8]} of the delivered report are not in it" + ("" if gone or added else " (order differs)")
            + (f" (fields {fields[:10]} differ)" if fields else ""),
            claim_ids=list(dict.fromkeys(gone + added)), **t.ids())
