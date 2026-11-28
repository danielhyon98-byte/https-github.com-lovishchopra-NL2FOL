"""OVS-FID-010: the meaning label's record of a delivered answer, read by the auditor (meaning-check design 2.5.6; stage 2a).

Every delivered transfer that carries an answer's text (a response, a relayed or forwarded report, a synthesis:
:data:`~epinoic_overseer.label_gate.LABELLED_KINDS`) must carry the channel's label record for exactly the text it labelled
(``ChannelEvent.label_json`` beside ``labelled_text`` and its SHA-256). The auditor reads it with the one gate every release path
reads (:func:`~epinoic_overseer.label_gate.label_gate`, with the labeller of the live channel, else the translator's default looked up
at the moment of the check) and names, at error severity:

* a missing record, a record or text that is not the journaled one, and a record it cannot read;
* a ``named`` or ``none_named`` record that does not re-validate with the labeller's own canary key and model digest;
* a ``skipped`` record whose rule-reader refusal does not reproduce on the labelled text (re-read here without any labeller).

A record whose state is ``unavailable`` is not named here: it withholds the answer by itself, and the receipt's INT-SELF-002 already
names it with its kind (an outage, never a fault of the answer). Every release path reads OVS-FID-010 on the task audit it releases on
(:func:`~epinoic_overseer.meta_notes.audit_self_reports`) and refuses as an outage (rule ``meaning-label-unavailable``). The message
names the reason and the fields that differ, never a word of the answer or of the label. A digest-only transfer is not read here
(OVS-AUDIT-005 already keeps it from passing; every release gate finds no record and withholds).
"""
from __future__ import annotations

from typing import Any

from ..label_gate import LABEL_AUDIT_CODE, LABELLED_KINDS, LabelUnavailable, label_gate
from ..view import Transfer
from . import CheckContext

__all__ = ["check_label_record"]


def _labeller(ctx: CheckContext) -> Any:
    """The live channel's labeller when it was given one (the hub's ``selfcert_labeller``), else None (the default, at use time)."""
    try:
        return getattr(ctx.live, "selfcert_labeller", None) if ctx.live is not None else None
    except Exception:  # noqa: BLE001 - the default labeller decides
        return None


def check_label_record(ctx: CheckContext, t: Transfer) -> None:
    if t.kind not in LABELLED_KINDS or not t.delivered or t.digest_only or not t.message_id:
        return
    event = t.event
    if getattr(event, "label_json", None) is None and getattr(event, "labelled_text", None) is None:
        reason = LabelUnavailable("missing")
    else:
        try:
            label_gate(event, labeller=_labeller(ctx))
            return
        except LabelUnavailable as exc:
            reason = exc
    if reason.reason == "unavailable":
        return  # an unavailable record withholds by itself; INT-SELF-002 on the receipt names it (an outage)
    what = {"relay_synthesis": "synthesis"}.get(t.kind, "answer")
    detail = reason.describe() + (f"; fields {', '.join(reason.mismatches)}" if reason.mismatches else "")
    ctx.ovs(t.seq, LABEL_AUDIT_CODE, f"{t.kind} {t.message_id}: the meaning label's record of the {what} is missing or does not reproduce "
            f"({detail}): the {what} is withheld as unlabelled (rule meaning-label-unavailable)", **t.ids())
