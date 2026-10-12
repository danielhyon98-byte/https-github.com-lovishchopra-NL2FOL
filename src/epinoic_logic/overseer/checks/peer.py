"""L6 peer exchange: are forwards and peer documents the delivered text?

* PEER-001: a delivered forward's payload digest differs from the journaled delivery of that ``report_id``, or the
  forwarded report was never delivered before it (or only in REJECTED transfers). A forward the channel itself
  REJECTED (INT-HANDOFF-013) is the channel doing its job and gives no finding here.
* PEER-002: a ``peer:<task>`` document in a later delivered request is not byte-identical to the ``original_response``
  of a report forwarded earlier to that same recipient, or no forward to that recipient preceded it, or its
  attribution is not the report its text is (its ``author`` is not that report's agent, or its ``peer:<id>`` names
  another forwarded report): two forwarded reports supplied with their attributions swapped.
* PEER-002 also for a supplied text under any other document id that presents a forwarded report (its author is the
  report's agent, its id names the report or the agent, or its text is a near copy of the report's answer) and is not
  byte-identical to it, or presents a delivered report never forwarded to that recipient; and for one document id
  supplied with two different texts in one task's requests (``check_document_ids``: a document id carries one text).
* PEER-003 (info): the peer document is linked to its forward by text equality only (``TaskRequest`` carries no link
  field), stated so a reader knows the link is not an identifier.
* PEER-001 also for a ``relay_report`` (a report relayed by a party other than the router: a specialist's hand-off of
  its own report): it must reproduce a delivery that agent actually made, a ``response`` or ``response_text`` of the
  same report id with the same content under the channel's own equality (the payload without ``created_at``, as
  ``_content_dump`` compares a re-delivery), sent by the same agent. A relay that reproduces none is a fabricated or
  unattributable report (router-side code writing a report in a specialist's name and role), however the channel
  recorded it.
"""
from __future__ import annotations

from ..view import Transfer
from . import CheckContext


def _content(payload) -> "dict | None":
    """A journaled report payload without its delivery timestamp (the channel's ``_content_dump``)."""
    return {k: v for k, v in payload.items() if k != "created_at"} if isinstance(payload, dict) else None

__all__ = ["check_forward", "check_peer_documents", "check_relayed_report", "check_document_ids"]


def check_forward(ctx: CheckContext, t: Transfer) -> None:
    if t.kind != "relay_forward" or not t.delivered:
        return
    rid = t.report_id
    ids = t.ids()
    first = ctx.view.first_delivery(rid or "", before_seq=t.seq)
    if first is None:
        ctx.ovs(t.seq, "OVS-PEER-001", f"forward {t.message_id} carries report {rid}, which was never delivered on this channel before it (or only in REJECTED transfers)", **ids)
        return
    if first.event.payload_sha256 != t.event.payload_sha256:
        ctx.ovs(t.seq, "OVS-PEER-001", f"forward {t.message_id} of report {rid} is not byte-identical to its delivery {first.message_id}",
                message_ids=[t.message_id, first.message_id], report_ids=[rid], agent_ids=ids["agent_ids"])


def check_peer_documents(ctx: CheckContext, t: Transfer) -> None:
    if t.kind != "request" or not t.delivered or not t.peer_links:
        return
    for link in t.peer_links:
        mids = [t.message_id] + ([link.forward_message_id] if link.forward_message_id else [])
        agents = [a for a in (t.request.to_agent_id if t.request else None,) if a]
        if link.forward_seq is None:
            ctx.ovs(t.seq, "OVS-PEER-002", f"request {t.message_id} supplies peer document {link.document_id!r} to {agents}, but no forward to that recipient preceded it",
                    message_ids=mids, agent_ids=agents, document_ids=[link.document_id])
        elif link.misattributed is not None:
            ctx.ovs(t.seq, "OVS-PEER-002", f"peer document {link.document_id!r} in request {t.message_id} is attributed to another report than the one its text is: "
                    f"{link.misattributed} (forward {link.forward_message_id})", message_ids=mids, agent_ids=agents, document_ids=[link.document_id],
                    report_ids=[link.report_id] if link.report_id else [])
        elif not link.identical:
            ctx.ovs(t.seq, "OVS-PEER-002", f"peer document {link.document_id!r} in request {t.message_id} is not byte-identical to the original_response of the report forwarded to {agents} (forward {link.forward_message_id})",
                    message_ids=mids, agent_ids=agents, document_ids=[link.document_id], report_ids=[link.report_id] if link.report_id else [])
        else:
            ctx.ovs(t.seq, "OVS-PEER-003", f"peer document {link.document_id!r} in request {t.message_id} is linked to forward {link.forward_message_id} of report {link.report_id} by text equality only",
                    message_ids=mids, agent_ids=agents, document_ids=[link.document_id], report_ids=[link.report_id] if link.report_id else [])


def check_relayed_report(ctx: CheckContext, t: Transfer) -> None:
    """PEER-001 for a delivered ``relay_report`` that reproduces no delivery its sender made of that report."""
    if t.kind != "relay_report" or not t.delivered or t.digest_only:
        return
    rid = t.report_id
    sender = t.sender_agent_id
    mine = _content(t.payload)
    for d in ctx.view.transfers:
        if d.seq >= t.seq:
            break
        if not (d.kind in ("response", "response_text") and d.delivered and d.report_id == rid and d.sender_agent_id == sender):
            continue
        # the channel's own equality of a report (``_content_dump``): the delivery timestamp ``created_at`` excluded, so a
        # hand-off of the delivered report re-serialised with a new timestamp is the same report
        if d.event.payload_sha256 == t.event.payload_sha256 or (mine is not None and _content(d.payload) == mine):
            return
    ids = t.ids()
    role = (t.envelope or {}).get("sender_role")
    ctx.ovs(t.seq, "OVS-PEER-001", f"{t.kind} {t.message_id} relays report {rid} as {role} {sender!r}, but {sender!r} never delivered that report with that content "
            "(no earlier response of the same report id and payload digest from that agent): a fabricated or unattributable report", **ids)


def check_document_ids(ctx: CheckContext, t: Transfer) -> None:
    """PEER-002: a document id this delivered request supplies with a text other than the one an earlier delivered request
    of the task supplied under the same id (one document id carries one text across the task's requests)."""
    if t.kind != "request" or not t.delivered or t.request is None:
        return
    earlier: dict[str, Transfer] = {}
    for r in ctx.view.requests_before(t.seq):
        for d in r.request.supplied_texts:
            earlier.setdefault(d.document_id, r)
    linked = {link.document_id for link in t.peer_links}  # a document presenting a forward is held to that forward's text instead
    for doc in t.request.supplied_texts:
        prev = earlier.get(doc.document_id)
        if prev is None or doc.document_id in linked:
            continue
        old = next(d for d in prev.request.supplied_texts if d.document_id == doc.document_id)
        if old.text != doc.text:
            ctx.ovs(t.seq, "OVS-PEER-002", f"document {doc.document_id!r} in request {t.message_id} carries another text than the same document id in request "
                    f"{prev.message_id}: one document id carries one text in a task", message_ids=[t.message_id, prev.message_id],
                    agent_ids=[a for a in (t.request.to_agent_id, prev.request.to_agent_id) if a], document_ids=[doc.document_id])
