"""L6 peer exchange: are forwards and peer documents the delivered text?

* PEER-001: a delivered forward's payload digest differs from the journaled delivery of that ``report_id``, or the
  forwarded report was never delivered before it (or only in REJECTED transfers). A forward the channel itself
  REJECTED (INT-HANDOFF-013) is the channel doing its job and gives no finding here.
* PEER-002: a ``peer:<task>`` document in a later delivered request is not byte-identical to the ``original_response``
  of a report forwarded earlier to that same recipient, or no forward to that recipient preceded it.
* PEER-003 (info): the peer document is linked to its forward by text equality only (``TaskRequest`` carries no link
  field), stated so a reader knows the link is not an identifier.
"""
from __future__ import annotations

from ..view import Transfer
from . import CheckContext

__all__ = ["check_forward", "check_peer_documents"]


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
        elif not link.identical:
            ctx.ovs(t.seq, "OVS-PEER-002", f"peer document {link.document_id!r} in request {t.message_id} is not byte-identical to the original_response of the report forwarded to {agents} (forward {link.forward_message_id})",
                    message_ids=mids, agent_ids=agents, document_ids=[link.document_id], report_ids=[link.report_id] if link.report_id else [])
        else:
            ctx.ovs(t.seq, "OVS-PEER-003", f"peer document {link.document_id!r} in request {t.message_id} is linked to forward {link.forward_message_id} of report {link.report_id} by text equality only",
                    message_ids=mids, agent_ids=agents, document_ids=[link.document_id], report_ids=[link.report_id] if link.report_id else [])
