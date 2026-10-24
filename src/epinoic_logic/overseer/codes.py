"""Every ``OVS-*`` finding code, with exactly one severity, the stage that decides it and what it means.

The table is the single source: a finding is built only through :func:`ovs_finding`, which takes the
severity from here, so no check can raise a code under another severity. ``OVS-AGENT-*`` codes concern
overseer agents and never change a transfer's clearance (design decision 16).

``OVS-CONS-*`` and ``OVS-REP-*`` (stage ``consolidation``, design section 19) are raised by the consolidation of several
agents' answers to one input and by repeated-fault detection. They are recorded in the signed consolidated response
and the repeat report, outside the task audit, so they never change a transfer's clearance either: an answer with a
repeated fault already carries the error-level fault the signature was taken from.
"""
from __future__ import annotations

from typing import Literal, Optional

from ..integrity.contracts import IntegrityFinding

Severity = Literal["error", "warning", "info"]

#: code -> (severity, stage, meaning)
OVS_CODES: dict[str, tuple[Severity, str, str]] = {
    "OVS-CUST-001": ("error", "custody", "envelope payload altered after issue (rehash or canonical diff against the journal; names the JSON paths; the journal copy is authoritative)"),
    "OVS-CUST-002": ("error", "custody", "envelope header altered after issue (envelope digest differs; names the fields), or a transfer issued under a work plan, solver configuration, engine key id or branch other than the channel's first journaled ones (rule pinned-setup)"),
    "OVS-CUST-003": ("error", "custody", "transfer not journaled (written around the channel), or a journaled message missing from the log"),
    "OVS-CUST-004": ("error", "custody", "a typed copy (transmitted_reports, ch.requests) diverges from the journaled delivery"),
    "OVS-CUST-005": ("error", "custody", "journal chain broken (hash, link, sequence or HMAC); everything after the break is unverifiable and the task audit fails"),
    "OVS-CUST-006": ("error", "custody", "the raw text the hub received is not the text that was parsed or refused, or the delivered report is not what the branch adapter parses from it (re-parsed by the auditor)"),
    "OVS-RCPT-001": ("error", "receipts", "receipt differs from the journaled receipt (the channel's copy or the copy the router presents; names the fields)"),
    "OVS-RCPT-002": ("error", "receipts", "receipt status is not the image of its contents under the channel's status rule"),
    "OVS-RCPT-003": ("error", "receipts", "delivery contradicts status (a REJECTED transfer delivered, pooled, forwarded or recorded, or an accepted one not recorded)"),
    "OVS-RCPT-004": ("error", "receipts", "a finding re-derived on journaled inputs is absent from the receipt or carries a lower severity (names the code): implied by the receipt's own structured results, its coverage rule, its identity, relay, role and plan rules, a captured INCONSISTENT joint run (live), an error or warning the shadow replay raises more often, or an ST code the STEM packs re-derive from the journaled report (R2, rule stem-structural); also coverage records that are not the coverage rule's image, and a request whose word or paragraph bounds are weaker than its own user input states"),
    "OVS-RCPT-005": ("warning", "receipts", "a receipt finding the re-derivation does not reproduce (the shadow replay's, or an ST code the STEM packs do not re-derive: rule stem-structural)"),
    "OVS-RCPT-006": ("error", "receipts", "the receipt names identifiers that resolve nowhere"),
    "OVS-RCPT-007": ("error", "receipts", "the summary states something the structured fields do not support, a non-request receipt lacks the scope sentence, or a branch check's claims, detail or failure finding are not the channel's statement of the check and its signed run (R2, rule check-statements)"),
    "OVS-RCPT-008": ("error", "receipts", "the shadow channel, fed the journaled inputs, issues another status, coverage, constraint results or outcome display statuses for this transfer, and no undecided engine run under the channel's configuration explains it"),
    "OVS-RES-001": ("error", "results", "a cited result under a local key id was never produced by the engine while capture was active"),
    "OVS-RES-002": ("warning", "results", "a cited result is not retained (evicted, before attachment, degraded mode); unverifiable, not an accusation"),
    "OVS-RES-003": ("error", "results", "result unsigned, signature invalid, or signed under an undeclared key id"),
    "OVS-RES-004": ("error", "results", "result bound to another problem or ids, or its binding is internally inconsistent, or a local engine run under a solver configuration other than the channel's journaled one or component versions other than the running engine's"),
    "OVS-RES-005": ("error", "results", "result out of task or reused (another channel, task or request, a later event, or an earlier event re-cited as fresh)"),
    "OVS-RES-006": ("error", "results", "one result id with two contents, or a receipt copy not byte-identical to the stored result"),
    "OVS-RES-007": ("error", "results", "replay on a fresh engine (under the channel's journaled solver configuration) gives another definitive status, or another problem or config digest; or a word or paragraph bound whose signed status integer arithmetic contradicts, or leaves undecided while the bound fails (R2)"),
    "OVS-RES-008": ("warning", "results", "replay inconclusive for a result whose own status was undecided (timeout or unknown), or a shadow difference an undecided run explains; a definitive status the replay cannot reproduce is OVS-AUDIT-005"),
    "OVS-RES-009": ("error", "results", "display status not derivable from the translation and the signed result"),
    "OVS-RES-010": ("error", "results", "outcome translation not bound to the delivered claim (claim text digest or ids)"),
    "OVS-FORM-001": ("error", "formal", "formal_status differs from the cited result's status"),
    "OVS-FORM-002": ("error", "formal", "satisfied is not the image of the status"),
    "OVS-FORM-003": ("error", "formal", "the checked problem is not the one re-derived from the payload (recount or pack digest)"),
    "OVS-FORM-004": ("error", "formal", "a re-derived formal check is absent from the receipt"),
    "OVS-FORM-005": ("error", "formal", "an identity check (a step from the trivially true premise, which holds only when it holds for every value of its variable, the variable its statement names) was decided on a problem that gives that variable a value or a formula, and its signed status is the success the check expects: the identity was decided at that value only (rule identity-statement)"),
    "OVS-FID-001": ("error", "fidelity", "a delivered claim text does not occur in original_response"),
    "OVS-FID-002": ("error", "fidelity", "a quotation or excerpt in a delivered claim is absent from original_response"),
    "OVS-FID-003": ("error", "fidelity", "a figure or date in a delivered claim is absent from original_response under every spelling"),
    "OVS-FID-004": ("error", "fidelity", "a quotation located in no supplied text, with no receipt finding naming the claim"),
    "OVS-FID-005": ("error", "fidelity", "a self-report or self-certification delivered as content: its text (the branch detector), or an advisory self-report field an adapter set on a claim it roled as content (raw text)"),
    "OVS-FID-006": ("warning", "fidelity", "response content that no claim carries (parse loss)"),
    "OVS-FID-007": ("warning", "fidelity", "quotations self-grounded (checked only against texts the specialist supplied)"),
    "OVS-FID-008": ("error", "fidelity", "a supplied text under a requested document id altered in the report"),
    "OVS-FID-009": ("warning", "fidelity", "the auditor's independent structural detector flags a self-certification delivered as content, or a structured report's content claim carries the contract's advisory self-report fields (ignored; recorded by INT-HANDOFF-006)"),
    "OVS-TRN-001": ("error", "translation", "a translation's IR fails re-validation as untrusted data (schema, claim or request ids, the engine validator's allowlist, sorts and limits, or the subject profile's sorts)"),
    "OVS-TRN-002": ("error", "translation", "a translation's status, eligibility or engine run is not the image of its validation (a problem under a status that forbids one, ambiguity flags under TRANSLATED, a claim the eligibility policy rules out forced into IR, an engine result without a translated problem)"),
    "OVS-TRN-003": ("error", "translation", "a translation's grounding states more than the deterministic grounding check gives (a verified flag or a verified grounding check the re-run on the delivered supplied texts does not reproduce)"),
    "OVS-TRN-004": ("warning", "translation", "a quotation grounding's excerpt in a translation does not occur in the supplied text it names (disclosed as unverified; the result relies on it only as an ungrounded dependency)"),
    "OVS-TRN-005": ("warning", "translation", "a quotation or number in a translation (whoever proposed it) that the specialist's report never states"),
    "OVS-TRN-006": ("error", "translation", "circular translation: the conclusion, or part of it, is restated by premises that are the writer's own for the overseer (rule circularity-agreement: never looser than the translator's E112; rule semantic-restatement: as written or in another form, by Boolean structure, by the order of numbers or by the arithmetic of the conjunct's own symbols (rule arithmetic-restatement), never by the arithmetic of numbers alone; rule grounded-transcription: a premise is a transcription only when the deterministic grounding check verified its located excerpt, which states its figures and not only as a target the answer must derive, never on a grounding kind label or a number match alone; rule receipt-disclosure: a premise restating only part of the conclusion counts when the receipt presents it as given with the task), at least one of them SHOWN not to be data by a deterministic check (rule data-standing: the writer's own by its grounding, refuted by its source under rule same-quantity (a figure stated nowhere, only as a show-that target, only for another quantity, or only as a bound read as a value) or by the translation's own declarations, naming no source the overseer holds, or presented as data on a kind label alone: a task_setting or supplied_text with no located excerpt whose content no check reads in its source, such as Boolean content, a relation, a structural figure or a figure stated there only bare), and the auditor's own signed engine run on the problem without those premises (keeping the premises whose whole content rule same-quantity reads as their source's data) does not give ENTAILED, or could not decide (rules restatement-necessity and engine-shown), so the engine result rests on the claim assumed"),
    "OVS-TRN-007": ("error", "translation", "an outcome's summary is not the deterministic statement of its translation and its signed result"),
    "OVS-TRN-008": ("warning", "translation", "a definitive display (ENTAILED, CONSISTENT) rests on premises that assert supporting claims whose own outcomes in the same receipt are not successful"),
    "OVS-TRN-009": ("warning", "translation", "one receipt's translations encode the same fact inconsistently: one asserts it as a premise, another leaves it an unsupported conjunct of its own claim's check"),
    "OVS-TRN-010": ("warning", "translation", "redundant restatement: the overseer's circularity rules hold for a delivered translation whose conclusion is restated as a whole (rules circularity-agreement, semantic-restatement and grounded-transcription), but the auditor's own signed engine run on the problem without the restating premise(s) still gives ENTAILED (rule restatement-necessity), from the other premises or from premises presented as data that no check verifies or refutes (then also OVS-TRN-011): the result does not rest on the claim assumed; the restating premise adds nothing"),
    "OVS-TRN-011": ("warning", "translation", "restatement under an undecided data grounding: the result of a delivered translation rests on premises that restate its conclusion, or part of it, as data the request or a supplied text holds (a task_setting, or a supplied_text naming a document supplied with the request, with no located excerpt) whose whole content rule same-quantity reads there but that no deterministic check verifies as a transcription or refutes (rule data-standing: values of quantities, each figure stated in the source for the quantity the premise names, as the premise states it, in a table in the row the premise names; never Boolean content or anything else a label alone presents as data; the receipt may list it among the result's unverified dependencies or present it as given with the task), and no premise shown not to be data carries it: the auditor's own signed engine run without them does not give ENTAILED, which shows only that a data conjunct needs its data premise (rule engine-shown); whether the source states it, for the same quantity, is a meaning question for overseer agents, and a translation_circular accusation of it is unresolved"),
    "OVS-PEER-001": ("error", "peer", "forward not byte-identical to the delivery, a forward of an undelivered or REJECTED report, or a relayed report that reproduces no delivery its sender made of it"),
    "OVS-PEER-002": ("error", "peer", "peer document (a peer: id, or any supplied text presenting a forwarded report by its author, id, near-copy text or text containing most of the answer's own words, those no earlier source carries, first supplied after the answer existed) differs from the forwarded original_response (or does not carry it as one verbatim span), no forward to that recipient preceded it, or its attribution (author, report id) is not the forwarded report's; or one document id carries two texts in a task"),
    "OVS-PEER-003": ("info", "peer", "peer document linked to its forward by text equality only"),
    "OVS-SYN-001": ("error", "synthesis", "synthesis cites a report not delivered before it"),
    "OVS-SYN-002": ("error", "synthesis", "a ledger fault found against the journaled reports is absent from the synthesis receipt (names the INT code)"),
    "OVS-SYN-003": ("error", "synthesis", "a conflict non-disclosure (against all contradictions) is absent from the synthesis receipt"),
    "OVS-JOINT-001": ("error", "joint", "unnamed contradiction (claim-minimal; cites the auditor's signed run)"),
    "OVS-JOINT-002": ("warning", "joint", "independent joint check undecided, not buildable, or over the joint limits"),
    "OVS-JOINT-003": ("error", "joint", "a named conflict not reproduced by the engine (false conflict; a named set is re-run on its pooled part), or named on a claim that had no formalization in the pool"),
    "OVS-JOINT-004": ("error", "joint", "the live pool differs from the journaled snapshot or from the outcomes' problems"),
    "OVS-DIV-001": ("error", "divergence", "an error-level integrity rule fires in the Overseer's report but on no receipt (names the INT code, classification and owner)"),
    "OVS-DIV-002": ("warning", "divergence", "a warning- or info-level rule divergence"),
    "OVS-AUDIT-001": ("error", "audit", "an audit check failed internally (named); no PASSED state"),
    "OVS-AUDIT-002": ("warning", "audit", "audit coverage lost (eviction, capture inactive, digest-only journal, queue overflow, degraded view)"),
    "OVS-AUDIT-003": ("info", "audit", "live replay sampled (k of n replayed); live, it names each transfer citing a sampled-out result, so that transfer is never AUDIT_PASSED before the batch replay"),
    "OVS-AUDIT-004": ("error", "audit", "no verification key configured for a declared key id in use"),
    "OVS-AUDIT-005": ("error", "audit", "a check a transfer needs cannot run on content the auditor no longer holds or never had (a digest-only journal entry past the bound, a cited result evicted with no journaled copy or no completed replay, a definitive result with no replayable problem), or a definitive signed status its replay cannot reproduce (undecided, budget exceeded, versions changed); the transfer cannot pass"),
    "OVS-CONS-001": ("warning", "consolidation", "an answer excluded from a consolidated response: its receipt or the task audit carries an error-level finding, its transfer did not pass the audit, it was not delivered, or it repeats a fault (names the codes and the signed results)"),
    "OVS-CONS-002": ("warning", "consolidation", "answers to one input conflict: two or more groups, or a contradiction between a group and an excluded answer; disclosed, none chosen"),
    "OVS-CONS-003": ("info", "consolidation", "answers with the same material claims under the lexical rule kept apart: the engine did not confirm them mutually consistent (advisory; never merged)"),
    "OVS-CONS-004": ("error", "consolidation", "a consolidated response that does not verify under the consolidation key, or that a recomputation from the journal does not reproduce"),
    "OVS-REP-001": ("error", "repeats", "a repeated fault: an error-level fault whose signature (code, normalised offending claim or quoted phrase, figures) already occurred earlier in the same task; the answer is never delivered or consolidated"),
    "OVS-AGENT-001": ("error", "verdicts", "an overseer agent's statement is refuted by a verified signed result or a deterministic check"),
    "OVS-AGENT-002": ("warning", "verdicts", "an accusation's identifiers or evidence pointers do not resolve"),
    "OVS-AGENT-003": ("info", "verdicts", "accusation confirmed; the router acts on the confirming OVS-* finding"),
    "OVS-AGENT-004": ("warning", "verdicts", "accusation neither confirmed nor refuted (human review)"),
    "OVS-AGENT-005": ("error", "verdicts", "verdict invalid (unparseable, schema, role, contract, signature, digest or dossier binding); discarded"),
}

#: The stage names an audit's ``checks_run`` uses, in run order.
STAGES = ("custody", "receipts", "results", "formal", "fidelity", "translation", "peer", "synthesis", "joint", "divergence", "shadow", "replay", "verdicts")
#: Stages outside the task audit: the consolidation of several agents' answers to one input (``consolidate.py``) and
#: repeated-fault detection (``repeats.py``). Their codes appear in a consolidated response and in a repeat report,
#: never in a task audit's ``checks_run``, so they never change a transfer's clearance.
CONSOLIDATION_STAGES = ("consolidation", "repeats")


def severity_of(code: str) -> Severity:
    return OVS_CODES[code][0]


def is_agent_code(code: str) -> bool:
    return code.startswith("OVS-AGENT-")


def ovs_finding(code: str, message: str, *, claim_ids=(), message_ids=(), report_ids=(), agent_ids=(), document_ids=(),
                formal_result_id: Optional[str] = None, related_result_ids=()) -> IntegrityFinding:
    """An ``OVS-*`` finding with the table's severity. Identifier lists are deduplicated in first-seen order;
    every finding is deterministic (decided by a digest, an HMAC, a re-run of repository rules or an
    auditor-signed engine run, never by agent text)."""
    if code not in OVS_CODES:
        raise KeyError(f"unknown Overseer code {code!r}")

    def ids(xs) -> list[str]:
        return list(dict.fromkeys(str(x) for x in xs if x is not None and str(x) != ""))

    related = [r for r in ids(related_result_ids) if r != formal_result_id]
    return IntegrityFinding(code=code, severity=OVS_CODES[code][0], message=message, claim_ids=ids(claim_ids), message_ids=ids(message_ids),
                            report_ids=ids(report_ids), agent_ids=ids(agent_ids), document_ids=ids(document_ids),
                            formal_result_id=formal_result_id, related_result_ids=related, deterministic=True)
