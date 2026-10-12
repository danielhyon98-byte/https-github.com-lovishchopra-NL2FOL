"""L6 peer exchange: are forwards and peer documents the delivered text?

* PEER-001: a delivered forward's payload digest differs from the journaled delivery of that ``report_id``, or the
  forwarded report was never delivered before it (or only in REJECTED transfers). A forward the channel itself
  REJECTED (INT-HANDOFF-013) is the channel doing its job and gives no finding here.
* PEER-002: a ``peer:<task>`` document in a later delivered request is not byte-identical to the ``original_response``
  of a report forwarded earlier to that same recipient, or no forward to that recipient preceded it, or its
  attribution is not the report its text is (its ``author`` is not that report's agent, or its ``peer:<id>`` names
  another forwarded report): two forwarded reports supplied with their attributions swapped.
* PEER-003 (info): the peer document is linked to its forward by text equality only (``TaskRequest`` carries no link
  field), stated so a reader knows the link is not an identifier.
* PEER-001 also for a ``relay_report`` (a report relayed by a party other than the router: a specialist's hand-off of
  its own report): it must reproduce a delivery that agent actually made, a ``response`` or ``response_text`` of the
  same report id with the same payload digest, sent by the same agent. A relay that reproduces none is a fabricated or
  unattributable report (router-side code writing a report in a specialist's name and role), however the channel
  recorded it.
"""
from __future__ import annotations

from ..view import Transfer
from . import CheckContext

__all__ = ["check_forward", "check_peer_documents", "check_relayed_report"]


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
    for d in ctx.view.transfers:
        if d.seq >= t.seq:
            break
        if (d.kind in ("response", "response_text") and d.delivered and d.report_id == rid and d.sender_agent_id == sender
                and d.event.payload_sha256 == t.event.payload_sha256):
            return
    ids = t.ids()
    role = (t.envelope or {}).get("sender_role")
    ctx.ovs(t.seq, "OVS-PEER-001", f"{t.kind} {t.message_id} relays report {rid} as {role} {sender!r}, but {sender!r} never delivered that report with that content "
            "(no earlier response of the same report id and payload digest from that agent): a fabricated or unattributable report", **ids)
