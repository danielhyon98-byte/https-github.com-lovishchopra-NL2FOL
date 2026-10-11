"""L1 custody (and the B1 sweep): is the transfer the router is about to act on the one that was issued?

The journal copy is authoritative. Every comparison is a digest comparison against what was journaled when the
transfer was issued:

* CUST-001: the live envelope's payload rehashed against the journaled ``payload_sha256``; the canonical diff names
  the JSON paths and the claims they touch. Also an envelope whose own ``payload_sha256`` did not match its payload
  when it was issued.
* CUST-002: the live envelope's header digest (every field but the payload and the signature fields) against the
  journaled one; the changed header fields are named.
* CUST-003: a journaled message absent from the log; a logged message no event journaled; a gap in the event
  sequence (an event that was never journaled).
* CUST-004: the channel's typed copy (``ch.requests[mid]``, ``ch.transmitted_reports[rid]``) against the journaled
  delivery's payload digest (deep mutation such as ``claims.pop()``).
* CUST-006: the raw text the hub received against what was parsed (``original_response``) or refused (the withheld
  envelope's ``response_sha256``).
* CUST-005: the journal chain itself (B1 only).

A degraded view (no journal) has no reference copy: none of these is decided there, and the lost coverage is
reported (AUDIT-002) by the auditor.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ...channel.events import header_digest, model_json
from ...ir.canonical import canonical_json, sha256_hex
from ...translate.contracts import sha256_text
from ..view import REPORT_KINDS, Transfer
from . import CheckContext, claim_ids_for_paths, json_diff_paths

__all__ = ["check_custody", "check_raw_text", "sweep_log", "check_chain", "check_issue_consistency"]


def _payload_digest(payload: Any) -> Optional[str]:
    try:
        return sha256_hex(canonical_json(payload))
    except Exception:  # a non-finite number or another value JSON cannot carry: not the journaled payload
        return None


def check_issue_consistency(ctx: CheckContext, t: Transfer) -> None:
    """At issue: the envelope's own ``payload_sha256`` must be the digest of the payload it carried."""
    env = t.envelope or {}
    declared = env.get("payload_sha256")
    if declared is not None and t.event.payload_sha256 is not None and declared != t.event.payload_sha256:
        ctx.ovs(t.seq, "OVS-CUST-001", f"transfer {t.message_id}: when it was issued, the envelope's payload_sha256 did not match the payload it carried", **t.ids())


def check_custody(ctx: CheckContext, t: Transfer) -> None:
    """CUST-001/002/003/004 for one journaled transfer against the live channel (when one is attached)."""
    if ctx.view.degraded or ctx.live is None or not t.message_id:
        return
    live_msg = ctx.live.log.get(t.message_id)
    ids = t.ids()
    if live_msg is None:
        ctx.ovs(t.seq, "OVS-CUST-003", f"journaled message {t.message_id} ({t.kind}) is absent from the channel's log", **ids)
    else:
        live_hash = _payload_digest(live_msg.payload)
        if live_hash != t.event.payload_sha256:
            paths: list[str] = []
            if t.payload is not None:
                try:
                    live_payload = json.loads(canonical_json(live_msg.payload))
                except Exception:
                    live_payload = None
                paths = json_diff_paths(t.payload, live_payload) if live_payload is not None else ["$ (live payload cannot be serialised)"]
            claims = claim_ids_for_paths(t.payload, paths, None)
            what = f"at {paths}" if paths else "(the journal holds digests only, so the paths cannot be named)"
            ctx.ovs(t.seq, "OVS-CUST-001", f"the payload of {t.kind} {t.message_id} was altered after issue {what}; the journaled copy is authoritative",
                    claim_ids=claims, message_ids=ids["message_ids"], report_ids=ids["report_ids"], agent_ids=ids["agent_ids"])
        try:
            live_dump = live_msg.model_dump(mode="json", exclude_none=True)
            live_header = header_digest(live_dump)
        except Exception:
            live_dump, live_header = None, None
        if t.event.header_sha256 is not None and live_header != t.event.header_sha256:
            fields: list[str] = []
            if t.envelope is not None and live_dump is not None:
                fields = sorted(k for k in set(t.envelope) | set(live_dump) if k not in ("payload", "signature", "signature_key_id") and t.envelope.get(k) != live_dump.get(k))
            ctx.ovs(t.seq, "OVS-CUST-002", f"the envelope header of {t.kind} {t.message_id} was altered after issue" + (f" (fields {fields})" if fields else ""),
                    message_ids=ids["message_ids"], report_ids=ids["report_ids"], agent_ids=sorted(set(ids["agent_ids"]) | ({live_dump.get("sender_agent_id")} if live_dump and live_dump.get("sender_agent_id") else set())))
    _check_typed_copy(ctx, t)


def _check_typed_copy(ctx: CheckContext, t: Transfer) -> None:
    ids = t.ids()
    if t.kind == "request":
        if not t.delivered:
            return
        held = (getattr(ctx.live, "requests", None) or {}).get(t.message_id)
        if held is None:
            ctx.ovs(t.seq, "OVS-CUST-004", f"the accepted request {t.message_id} is no longer held by the channel (ch.requests)", **ids)
            return
        dig = sha256_hex(model_json(held))
        if dig != t.event.payload_sha256:
            paths = json_diff_paths(t.payload, json.loads(model_json(held))) if t.payload is not None else []
            ctx.ovs(t.seq, "OVS-CUST-004", f"the channel's typed copy of request {t.message_id} diverges from the journaled delivery" + (f" at {paths}" if paths else ""), **ids)
        return
    if t.kind not in REPORT_KINDS or not t.delivered or not t.report_id:
        return
    first = ctx.view.first_delivery(t.report_id)
    if first is None or first.seq != t.seq:
        return  # the typed copy belongs to the report id's first delivery
    held = (getattr(ctx.live, "transmitted_reports", None) or {}).get(t.report_id)
    if held is None:
        ctx.ovs(t.seq, "OVS-CUST-004", f"report {t.report_id} delivered by {t.message_id} is no longer held by the channel (transmitted_reports)", **ids)
        return
    try:
        held_json = model_json(held)
    except Exception:
        held_json = None
    if held_json is None or sha256_hex(held_json) != t.event.payload_sha256:
        live = json.loads(held_json) if held_json else None
        paths = json_diff_paths(t.payload, live) if (t.payload is not None and live is not None) else []
        claims = claim_ids_for_paths(t.payload, paths, live)
        ctx.ovs(t.seq, "OVS-CUST-004", f"the channel's typed copy of report {t.report_id} (transmitted_reports) diverges from the journaled delivery {t.message_id}"
                + (f" at {paths}" if paths else ""), claim_ids=claims, message_ids=ids["message_ids"], report_ids=ids["report_ids"], agent_ids=ids["agent_ids"])


def check_raw_text(ctx: CheckContext, t: Transfer) -> None:
    """CUST-006: the raw text the hub received is the text that was parsed or refused."""
    if t.kind != "response_text" or t.event.raw_text_sha256 is None:
        return
    ids = t.ids()
    if t.withheld is not None:
        if t.withheld.get("response_sha256") != t.event.raw_text_sha256:
            ctx.ovs(t.seq, "OVS-CUST-006", f"the withheld envelope {t.message_id} records a response digest other than the digest of the raw text the hub received", **ids)
        if t.raw_text is not None and t.withheld.get("response_chars") is not None and t.withheld.get("response_chars") != len(t.raw_text):
            ctx.ovs(t.seq, "OVS-CUST-006", f"the withheld envelope {t.message_id} records {t.withheld.get('response_chars')} characters but the raw text received has {len(t.raw_text)}", **ids)
        return
    rep = t.report
    if rep is None:
        return
    if rep.response_sha256 != t.event.raw_text_sha256 or (t.raw_text is not None and rep.original_response != t.raw_text):
        ctx.ovs(t.seq, "OVS-CUST-006", f"report {rep.report_id} parsed from the raw text of {t.message_id} carries an original_response that is not the text the hub received", **ids)


def check_chain(ctx: CheckContext) -> None:
    """CUST-005: the journal chain verifies (hashes, links, MACs, index, sequence)."""
    j = ctx.view.journal
    if j is None:
        return
    br = j.verify_chain()
    if br is not None:
        entries = j.entries()
        ev = entries[br.index - 1].event if 0 < br.index <= len(entries) else None
        mids = [ev.message_id] if ev is not None and ev.message_id else []
        ctx.ovs(ev.seq if ev is not None else 0, "OVS-CUST-005", f"the journal chain of channel {j.channel_uid} breaks at entry {br.index}: {br.reason}; every entry from there on is unverifiable", message_ids=mids)


def sweep_log(ctx: CheckContext) -> None:
    """B1 CUST-003: every logged message journaled, every journaled message logged, no unrecorded event."""
    view = ctx.view
    for a, b in view.gaps:
        ctx.ovs(a, "OVS-CUST-003", f"channel events {a}..{b} were never journaled (an observer failed or the transfer was written around the channel)")
    for t in view.raised:
        ctx.coverage.events_raised += 1
        if t.event.log_added:
            ctx.ovs(t.seq, "OVS-CUST-003", f"channel call {t.call.get('method', t.kind)} raised {t.event.raised} (event {t.seq}) after logging messages {list(t.event.log_added)} that no receipt covers",
                    message_ids=list(t.event.log_added))
        else:
            ctx.note(f"channel call {t.call.get('method', t.kind)} raised {t.event.raised} (event {t.seq}); nothing was logged or issued")
    if view.degraded or ctx.live is None:
        return
    journaled = {t.message_id for t in view.transfers if t.message_id}
    for t in view.transfers + view.raised:
        journaled.update(t.event.log_added)
    log = ctx.live.log
    live_msgs = log.messages() if hasattr(log, "messages") else tuple(getattr(log, "_by_id", {}).values())
    for m in live_msgs:
        if m.message_id not in journaled:
            ctx.ovs(0, "OVS-CUST-003", f"message {m.message_id} ({m.contract} from {m.sender_role.value} {m.sender_agent_id}) is in the channel's log but no transfer journaled it: written around the channel",
                    message_ids=[m.message_id], agent_ids=[m.sender_agent_id])
