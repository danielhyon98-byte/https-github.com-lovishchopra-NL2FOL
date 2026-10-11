"""Keys and the channel journal: derivation, construction checks, hash chain and MACs, contiguous sequences, bounds,
sealing, and the custody findings a broken journal gives (CUST-003, CUST-005)."""
from __future__ import annotations

import dataclasses
import pickle

import pytest

from epinoic_logic.channel import TranslatorChannel
from epinoic_logic.channel.events import observe_call, ObservationState
from epinoic_logic.overseer import ChannelJournal, EngineKey, JournalSealed, JournalSet, KeyRing
from epinoic_logic.overseer.contracts import JournalEntry
from epinoic_logic.overseer.journal import entry_hash_of, genesis_hash

from .conftest import DOC, EN_INPUT, KEY, SECRET, codes_of, english_report, findings, make_auditor, make_keyring, make_plan, new_channel, run_task


# ------------------------------------------------------------------------------------------- keys
def test_subkeys_are_derived_deterministically_and_are_distinct():
    a, b = make_keyring(), make_keyring()
    labels = ("journal", "audit", "runs", "sampling", "intake")
    assert [a.subkey(x) for x in labels] == [b.subkey(x) for x in labels]
    assert len({a.subkey(x) for x in labels}) == 5
    assert a.mac("journal", "x") == b.mac("journal", "x") != a.mac("audit", "x")
    other = KeyRing({"hub": EngineKey(KEY)}, SECRET[::-1])
    assert other.subkey("audit") != a.subkey("audit")


def test_overseer_secret_must_be_long_and_differ_from_every_engine_key():
    with pytest.raises(ValueError, match="at least 32"):
        KeyRing({"hub": EngineKey(KEY)}, b"short")
    with pytest.raises(ValueError, match="differ from every engine key"):
        KeyRing({"hub": EngineKey(KEY), "x": EngineKey(SECRET)}, SECRET)
    with pytest.raises(ValueError, match="reserved"):
        KeyRing({"overseer-run": EngineKey(KEY)}, SECRET)


def test_keys_never_leak_through_repr_or_pickling():
    kr = make_keyring()
    assert KEY.decode() not in repr(kr) and SECRET.decode() not in repr(kr)
    assert KEY.decode() not in repr(EngineKey(KEY))
    with pytest.raises(TypeError):
        pickle.dumps(kr)


def test_key_status_and_declared_ids():
    kr = KeyRing({"hub": EngineKey(KEY), "ext": EngineKey(KEY, scope="external"), "nokey": EngineKey(None)}, SECRET)
    assert kr.key_status("hub") == "local" and kr.key_status("ext") == "external"
    assert kr.key_status("overseer-run") == "auditor" and kr.key_status("who") == "unknown"
    assert kr.is_declared("nokey") and not kr.has_secret("nokey") and kr.verification_key("nokey") is None


def test_sampling_fraction_is_reproducible_and_keyed():
    a, b = make_keyring(), make_keyring()
    fr = [a.sample_fraction(f"r{i}") for i in range(200)]
    assert fr == [b.sample_fraction(f"r{i}") for i in range(200)]
    assert all(0.0 <= x < 1.0 for x in fr)
    assert 0.15 < sum(1 for x in fr if x < 0.25) / 200 < 0.35
    other = KeyRing({"hub": EngineKey(KEY)}, SECRET[::-1])
    assert [other.sample_fraction(f"r{i}") for i in range(20)] != fr[:20]


# ------------------------------------------------------------------------------------------- journal
def _events(n_requests: int = 3):
    """Real channel events of ``n_requests`` requests, captured with a list observer."""
    ch = TranslatorChannel(make_plan(), signing_key=KEY, key_id="hub")
    st = ObservationState()
    got = []
    for i in range(n_requests):
        observe_call(ch, "request", ("router", "english-specialist", EN_INPUT + f" Version {i}.", [DOC]), {}, [got.append], state=st)
    return st.channel_uid, got


def test_chain_verifies_and_every_entry_is_maced():
    uid, events = _events(3)
    kr = make_keyring()
    j = ChannelJournal(uid, "task-ovs", kr)
    for ev in events:
        j.append(ev)
    j.append_record("clearance", {"x": 1})
    assert j.verify_chain() is None
    entries = j.entries()
    assert entries[0].prev_hash == genesis_hash(uid)
    assert all(e.entry_hash == entry_hash_of(e.body()) and kr.mac_ok("journal", e.entry_hash, e.mac) for e in entries)
    assert j.head() == (4, entries[-1].entry_hash)


def test_edited_entry_breaks_the_chain_at_its_index():
    uid, events = _events(3)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    for ev in events:
        j.append(ev)
    forged_event = dataclasses.replace(events[1], status="REJECTED")
    j._entries[1] = dataclasses.replace(j._entries[1], event=forged_event)
    br = j.verify_chain()
    assert br is not None and br.index == 2 and "hash" in br.reason
    # recomputing the hash without the journal key leaves the MAC wrong
    body = dataclasses.replace(j._entries[1], event=forged_event).body()
    j._entries[1] = dataclasses.replace(j._entries[1], event=forged_event, entry_hash=entry_hash_of(body))
    br = j.verify_chain()
    assert br is not None and br.index == 2 and "MAC" in br.reason


def test_a_journal_under_another_key_does_not_verify():
    uid, events = _events(2)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    for ev in events:
        j.append(ev)
    other = ChannelJournal(uid, "task-ovs", KeyRing({"hub": EngineKey(KEY)}, SECRET[::-1]))
    other._entries = list(j.entries())
    other._head = j.head()
    assert other.verify_chain() is not None


def test_sequence_must_be_contiguous_and_gaps_are_recorded():
    uid, events = _events(4)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    j.append(events[0])
    j.append(events[2])  # event 2 was never journaled
    assert j.gaps() == [(2, 2)]
    assert j.verify_chain() is None  # the gap is recorded, so the chain itself verifies
    with pytest.raises(ValueError):
        j.append(events[1])  # backwards: replayed or reordered
    with pytest.raises(ValueError):
        j.append(events[2])  # repeated
    other_uid, other_events = _events(1)
    with pytest.raises(ValueError):
        j.append(other_events[0])  # another channel's event


def test_removed_gap_record_is_a_chain_break():
    uid, events = _events(3)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    j.append(events[0])
    j.append(events[2])
    del j._entries[1]  # hide the gap record
    assert j.verify_chain() is not None


def test_digest_only_past_the_entry_bound():
    uid, events = _events(4)
    j = ChannelJournal(uid, "task-ovs", make_keyring(), max_entries=2)
    for ev in events:
        j.append(ev)
    entries = j.entries()
    assert [e.event.digest_only for e in entries] == [False, False, True, True]
    assert entries[2].event.envelope_json is None and entries[2].event.payload_sha256 == events[2].payload_sha256
    assert j.digest_only_entries == 2 and len(j.coverage_notes) == 1
    assert j.verify_chain() is None


def test_digest_only_past_the_byte_bound():
    uid, events = _events(2)
    j = ChannelJournal(uid, "task-ovs", make_keyring(), max_bytes=10)
    j.append(events[0])
    assert j.entries()[0].event.digest_only


def test_sealed_journal_accepts_nothing():
    uid, events = _events(2)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    j.append(events[0])
    j.seal("final task audit")
    with pytest.raises(JournalSealed):
        j.append(events[1])
    with pytest.raises(JournalSealed):
        j.append_record("clearance", {})
    assert j.verify_chain() is None and j.entries()[-1].kind == "seal"


def test_late_attachment_starts_the_journal_without_a_gap():
    uid, events = _events(3)
    j = ChannelJournal(uid, "task-ovs", make_keyring())
    j.start_at(3)
    j.append(events[2])
    assert j.gaps() == [] and j.verify_chain() is None


def test_journal_set_evicts_sealed_journals_lru_and_keeps_heads():
    kr = make_keyring()
    js = JournalSet(kr, global_max_bytes=1)
    uid1, ev1 = _events(1)
    uid2, ev2 = _events(1)
    j1 = js.create(uid1, "t1")
    j1.append(ev1[0])
    j1.seal("done")
    head = j1.head()
    j2 = js.create(uid2, "t2")
    j2.append(ev2[0])
    assert j1.evicted and j1.entries() == () and j1.head() == head
    assert not j2.evicted  # unsealed journals are never evicted


# ------------------------------------------------------------------------------------------- through the auditor
def test_t12_an_edited_journal_entry_fails_the_task_audit(auditor):
    task = run_task(auditor)
    j = auditor.journal(task.uid)
    idx = next(i for i, e in enumerate(j._entries) if e.event is not None and e.event.kind == "response")
    j._entries[idx] = dataclasses.replace(j._entries[idx], event=dataclasses.replace(j._entries[idx].event, status="REJECTED"))
    audit = task.audit()
    f = findings(audit, "OVS-CUST-005")
    assert f and f[0].severity == "error" and f"entry {idx + 1}" in f[0].message
    assert audit.state == "AUDIT_FAILED"


def test_t13_a_message_written_around_the_channel_is_cust_003(auditor):
    task = run_task(auditor, synthesis=False)
    forged = task.ch.channel.log.get(task.mids["rep_en"]).model_copy(update={"message_id": "forged-message-1"})
    task.ch.channel.log.accept(forged)  # injected straight into the log: no event, no receipt
    audit = task.audit()
    f = [x for x in findings(audit, "OVS-CUST-003") if "forged-message-1" in x.message_ids]
    assert f and f[0].severity == "error" and audit.state == "AUDIT_FAILED"


def test_an_unjournaled_event_gap_is_cust_003():
    auditor = make_auditor()
    try:
        ch = new_channel(auditor)
        ch.request("router", "english-specialist", EN_INPUT, [DOC])
        observer = ch.observers[0]

        def broken(event):
            raise RuntimeError("observer failure")
        ch.observers[:] = [broken]  # the observer raises: the event is built but never journaled
        msg, _req, rc = ch.request("router", "english-specialist", EN_INPUT + " Again.", [DOC])
        assert msg is not None and rc.status.value == "ACCEPTED"  # the failure never reaches the caller
        assert ch.state.observer_errors and ch.state.observer_errors[0][2] == "RuntimeError"
        ch.observers[:] = [observer]
        ch.request("router", "english-specialist", EN_INPUT + " Third.", [DOC])
        audit = auditor.audit(ch.uid)
        f = findings(audit, "OVS-CUST-003")
        assert any("events 2..2 were never journaled" in x.message for x in f)
        assert any(rc.message_id in x.message_ids for x in f)  # the logged message no event journaled
        assert audit.state == "AUDIT_FAILED"
    finally:
        auditor.close()


def test_final_audit_seals_the_journal_and_later_events_are_refused():
    auditor = make_auditor()
    try:
        ch = new_channel(auditor)
        ch.request("router", "english-specialist", EN_INPUT, [DOC])
        audit = auditor.audit(ch.uid, final=True)
        assert audit.final and auditor.journal(ch.uid).sealed
        ch.request("router", "english-specialist", EN_INPUT + " More.", [DOC])  # never raises into the channel
        later = auditor.audit(ch.uid)
        assert any(f.code == "OVS-CUST-003" and "could not be journaled" in f.message for f in later.report.findings)
    finally:
        auditor.close()
