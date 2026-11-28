"""Interface (c) of stage 2a: ``Labeller.revalidate_record(record, raw_text, request)`` re-validates a stored record with the
labeller's OWN canary key and model digest, and always binds the model digest (the auditor's path): a record of another model,
another key or another text is a mismatch, and the unconfigured default never re-validates anything, so no record is ever read as
clean for want of a labeller. The record's seal is a content hash: a record re-sealed after an edit still fails on what the
re-validation recomputes, and integrity against deliberate forgery is the channel journal's (README)."""
from __future__ import annotations

import copy

import pytest

from epinoic_logic.selfcert_label import CachingLabeller, ProviderLabeller, UnconfiguredLabeller, model_digest
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, id_of, reply_json
from epinoic_logic.selfcert_label.record import seal_of

REQ = {"subject": "chemistry", "task_type": "short_answer"}
CLEAN = "The molar mass of water is 18 g/mol.\n\nIt boils at 100 degrees Celsius at sea level."
NAMED = "The molar mass of water is 18 g/mol.\n\nThis passed the hub's checks."


def _resealed(record: dict, **changes) -> dict:
    rec = copy.deepcopy(record)
    rec.update(changes)
    rec["seal"] = seal_of(rec)
    return rec


def test_a_record_revalidates_with_the_labeller_that_made_it_and_its_twin():
    lab = ReaderBackedLabeller()
    for text, state in ((CLEAN, "none_named"), (NAMED, "named")):
        res = lab.label(text, REQ)
        assert res.state == state
        rv = lab.revalidate_record(res.record, text, REQ)
        assert (rv.ok, rv.mismatches) == (True, ())
        assert ReaderBackedLabeller().revalidate_record(res.record, text, REQ).ok  # same key, same model digest
        assert CachingLabeller(lab).revalidate_record(res.record, text, REQ).ok


def test_the_model_digest_is_always_bound():
    lab = ReaderBackedLabeller()
    scripted = ScriptedLabeller(lambda req, n: reply_json(req))
    other = scripted.label(CLEAN, REQ)
    rv = lab.revalidate_record(other.record, CLEAN, REQ)  # a record of another model
    assert not rv.ok and "model_digest" in rv.mismatches
    # the faithful fake's own record, re-sealed under another model's digest: the seal is a content hash, so it matches, and
    # the bound model digest is what names the edit
    forged = _resealed(lab.label(CLEAN, REQ).record, model_digest=model_digest("another-model"))
    rv = lab.revalidate_record(forged, CLEAN, REQ)
    assert (rv.ok, rv.mismatches) == (False, ("model_digest",))


def test_another_key_another_text_or_another_request_is_a_mismatch():
    lab = ReaderBackedLabeller()
    res = lab.label(NAMED, REQ)
    assert not ReaderBackedLabeller(key=b"another canary key").revalidate_record(res.record, NAMED, REQ).ok
    rv = lab.revalidate_record(res.record, NAMED + " ", REQ)
    assert not rv.ok and "input_key" in rv.mismatches
    rv = lab.revalidate_record(res.record, NAMED, {"subject": "physics", "task_type": "short_answer"})
    assert not rv.ok and "input_key" in rv.mismatches


def test_an_edited_record_does_not_revalidate_even_when_resealed():
    lab = ReaderBackedLabeller()
    res = lab.label(NAMED, REQ)
    for change, field in (({"state": "none_named"}, "state"), ({"spans": []}, "spans"), ({"attempts": []}, "state")):
        rv = lab.revalidate_record(_resealed(res.record, **change), NAMED, REQ)
        assert not rv.ok and field in rv.mismatches, (change, rv.mismatches)
    tampered = copy.deepcopy(res.record)
    tampered["state"] = "none_named"  # not re-sealed: the seal names it too
    rv = lab.revalidate_record(tampered, NAMED, REQ)
    assert not rv.ok and rv.mismatches[:1] == ("seal",)


def test_the_unconfigured_default_never_revalidates_anything():
    un = UnconfiguredLabeller()
    own = un.label(CLEAN, REQ)
    assert own.record["model_digest"] == ""
    for rec, text in ((own.record, CLEAN), (ReaderBackedLabeller().label(CLEAN, REQ).record, CLEAN), ({}, CLEAN), (None, "")):
        rv = un.revalidate_record(rec, text, REQ)
        assert (rv.ok, rv.mismatches, rv.result) == (False, ("not-configured",), None)


def test_a_calling_labeller_with_no_model_digest_revalidates_nothing():
    lab = ScriptedLabeller(lambda req, n: reply_json(req))
    res = lab.label(CLEAN, REQ)
    assert lab.revalidate_record(res.record, CLEAN, REQ).ok
    lab.model_digest = ""
    rv = lab.revalidate_record(res.record, CLEAN, REQ)
    assert (rv.ok, rv.mismatches) == (False, ("model_digest",))


def test_a_provider_labellers_record_revalidates_under_its_configured_model():
    def transport(system, user, *, max_tokens, timeout_s):
        raise AssertionError("re-validation never calls the provider")
    lab = ProviderLabeller(transport, key=b"deployment canary key", model_id="configured-model")
    scripted = ScriptedLabeller(lambda req, n: reply_json(req, {id_of(req, 1): [("passed the hub's checks", "OUTCOME")]}),
                                key=b"deployment canary key")
    res = scripted.label(NAMED, REQ)
    rec = _resealed(res.record, model_digest=model_digest("configured-model"))
    rv = lab.revalidate_record(rec, NAMED, REQ)
    assert (rv.ok, rv.mismatches) == (True, ()) and rv.result.state == "named"
    assert not ProviderLabeller(transport, key=b"deployment canary key", model_id="m2").revalidate_record(rec, NAMED, REQ).ok


def test_a_skipped_record_revalidates_only_while_the_reader_still_refuses():
    lab = ReaderBackedLabeller()
    skipped = lab.skipped(NAMED, REQ)
    assert skipped.state == "skipped"
    assert lab.revalidate_record(skipped.record, NAMED, REQ).ok
    # the same record against a text the reader passes: its refusal does not reproduce at release
    other = _resealed(skipped.record, input_key=lab.prepare(CLEAN, REQ).input_key)
    rv = lab.revalidate_record(other, CLEAN, REQ)
    assert not rv.ok and "state" in rv.mismatches


@pytest.mark.parametrize("record", [None, "text", 3, [], {"record": "selfcert-label-record/1"}])
def test_a_record_that_cannot_be_read_does_not_revalidate(record):
    rv = ReaderBackedLabeller().revalidate_record(record, CLEAN, REQ)
    assert rv.ok is False and rv.mismatches
