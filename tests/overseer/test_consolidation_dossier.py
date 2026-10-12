"""Consolidations in the dossier (design section 19): an overseer agent reviews consolidated groups and repeated faults
through the ``consolidations`` section of an INFORMED dossier, and only there.

Covered: the section's shape (pointers that resolve to the transfers they name, no agent text copied in); blind mode
carries none; a dossier of a channel never consolidated is byte-identical to the dossier issued before the section
existed (same digest); the intake refuses a tampered consolidated response or one of another channel; the contract
refuses a consolidation in blind mode or under a wrong pointer; and an agent's accusation about a consolidation is advisory
(unresolved, human review) and changes no clearance and no consolidation."""
from __future__ import annotations

import json
import socket

import pytest
from pydantic import ValidationError

from epinoic_logic.overseer import (
    Dossier, IntakeRefused, OverseerAgentRunner, VerdictIntake, build_dossier, installed_pack, load_pack, resolve_pointer, sign_consolidated,
    verify_consolidated, verify_dossier_digest,
)
from epinoic_logic.overseer.export import export_pack

from .test_consolidation_consolidate import Dup
from .test_consolidation_repeats import bad_answer
from .test_hook_hub import audited_hub
from .test_hook_review import Scripted, verdict
from .test_protocol_validate import acc


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    exported = export_pack(tmp_path_factory.mktemp("export"), zip_archive=True)
    return load_pack(exported.directory)


@pytest.fixture
def hub():
    h = audited_hub()
    yield h
    h.close()


def faulty_task(hub) -> tuple[Dup, object]:
    d = Dup(hub)
    text, claims = bad_answer()
    d.answer("english-1", text=text, claims=claims, name="first")
    d.answer("english-2", text=text, claims=claims, name="again")
    d.answer("english-3", name="clean")
    return d, d.consolidate()


def issue(hub, d: Dup, *, mode: str = "informed", consolidations=(), agent: str = "overseer-general-1") -> dict:
    a = hub.auditor
    intake = VerdictIntake(a.keyring, accepted_packs={installed_pack().identity})
    audit = a.audit(d.ch.channel_uid) if mode == "informed" else None
    return intake.issue(a.view(d.ch.channel_uid), agent_id=agent, lens="general", mode=mode, pack=installed_pack().identity, audit=audit,
                        consolidations=consolidations)


# ============================================================================================ the section
def test_an_informed_dossier_shows_the_consolidation_with_pointers_to_the_transfers_it_names(hub):
    d, r = faulty_task(hub)
    dossier = issue(hub, d, consolidations=[r])
    assert verify_dossier_digest(dossier) and Dossier.model_validate(dossier)
    (c,) = dossier["consolidations"]
    assert c["at"] == "/consolidations/0" and resolve_pointer(dossier, c["at"]) == c
    assert c["consolidation_id"] == r.consolidation_id and c["status"] == r.status == "CONSOLIDATED_WITH_FINDINGS" and c["signature_present"] is True
    assert c["deliverable_message_id"] == d.mids["clean"] and c["user_input_sha256"] == r.user_input_sha256
    member = c["groups"][0]["members"][0]
    assert member["message_id"] == d.mids["clean"] and resolve_pointer(dossier, member["transfer_pointer"] + "/message_id") == d.mids["clean"]
    ex = {e["message_id"]: e for e in c["excluded"]}
    assert ex[d.mids["again"]]["repeated"] is True and "OVS-REP-001" in ex[d.mids["again"]]["codes"] and "INT-REQ-003" in ex[d.mids["first"]]["codes"]
    (rep,) = c["repeats"]
    assert rep["code"] == "INT-REQ-003" and rep["message_id"] == d.mids["again"] and rep["first_message_id"] == d.mids["first"]
    assert resolve_pointer(dossier, rep["first_transfer_pointer"] + "/message_id") == d.mids["first"] and rep["same_agent"] is False
    # no agent text is copied into the section: no claim text, no quotation, no anchor
    assert "river carried" not in json.dumps(c)


def test_blind_mode_shows_no_consolidation_and_an_unconsolidated_dossier_keeps_its_digest(hub):
    d, r = faulty_task(hub)
    blind = issue(hub, d, mode="blind", consolidations=[r])
    assert "consolidations" not in blind and Dossier.model_validate(blind)
    a = hub.auditor
    audit = a.audit(d.ch.channel_uid)
    view = a.view(d.ch.channel_uid)
    plain = build_dossier(view, mode="informed", lens="general", agent_id="x-1", pack=installed_pack().identity, audit=audit)
    empty = build_dossier(view, mode="informed", lens="general", agent_id="x-1", pack=installed_pack().identity, audit=audit, consolidations=())
    assert "consolidations" not in plain and plain == empty and plain["dossier_sha256"] == empty["dossier_sha256"]
    shown = build_dossier(view, mode="informed", lens="general", agent_id="x-1", pack=installed_pack().identity, audit=audit, consolidations=[r])
    assert shown["dossier_sha256"] != plain["dossier_sha256"] and shown["transfers"] == plain["transfers"]


def test_the_intake_refuses_a_tampered_consolidation_or_one_of_another_channel(hub):
    d, r = faulty_task(hub)
    kr = hub.auditor.keyring
    for bad in (r.model_copy(update={"deliverable_message_id": d.mids["again"]}), r.model_copy(update={"signature": None}), "a response"):
        with pytest.raises(IntakeRefused) as exc:
            issue(hub, d, consolidations=[bad])
        assert exc.value.reason == "consolidation"
    e = Dup(hub, task_id="task-other")
    e.answer("english-1", name="x")
    with pytest.raises(IntakeRefused) as exc:
        issue(hub, e, consolidations=[r])
    assert exc.value.reason == "consolidation"
    # signed by the infrastructure, but for another channel: build_dossier refuses it too
    moved = sign_consolidated(r.model_copy(update={"channel_uid": e.ch.channel_uid}), kr)
    assert verify_consolidated(moved, kr)
    a = hub.auditor
    with pytest.raises(ValueError, match="another channel"):
        build_dossier(a.view(d.ch.channel_uid), mode="informed", lens="general", agent_id="x-1", pack=installed_pack().identity,
                      audit=a.audit(d.ch.channel_uid), consolidations=[moved])


def test_the_dossier_contract_refuses_a_consolidation_in_blind_mode_or_under_a_wrong_pointer(hub):
    d, r = faulty_task(hub)
    dossier = issue(hub, d, consolidations=[r])
    wrong = json.loads(json.dumps(dossier))
    wrong["consolidations"][0]["at"] = "/consolidations/1"
    with pytest.raises(ValidationError):
        Dossier.model_validate(wrong)
    blind = json.loads(json.dumps(dossier))
    blind["mode"] = "blind"
    blind.pop("auditor")
    with pytest.raises(ValidationError):
        Dossier.model_validate(blind)
    extra = json.loads(json.dumps(dossier))
    extra["consolidations"][0]["verified"] = True
    with pytest.raises(ValidationError):
        Dossier.model_validate(extra)


# ============================================================================================ agents review a consolidation
def test_an_agents_concern_about_a_consolidation_is_advisory_and_changes_nothing(hub, pack):
    d, r = faulty_task(hub)

    def concern(dd: dict) -> dict:
        c = dd["consolidations"][0]
        g = c["groups"][0]
        return verdict(dd, [acc("a1", "other", [{"pointer": c["at"] + "/groups/0/canonical_message_id", "quote": g["canonical_message_id"]},
                                                 {"pointer": g["members"][0]["transfer_pointer"] + "/payload/original_response"}],
                               severity="warning", statement="The representative may not say what the excluded answers meant.",
                               message_ids=[g["canonical_message_id"]])])

    before = {m: hub.clearance(d.key, m).state for m in d.mids.values()}
    runner = OverseerAgentRunner(pack, Scripted(concern), agent_id="overseer-general-1", lens="general")
    rv = hub.review(d.key, [runner])
    (assessment,) = rv.assessments
    (a1,) = assessment.accusations
    assert a1.outcome == "unresolved" and a1.code == "OVS-AGENT-004"
    assert rv.combined.review_queue and {m: hub.clearance(d.key, m).state for m in d.mids.values()} == before
    assert hub.consolidations(d.key) == [r] and any(r.consolidation_id in n for n in rv.audit.coverage.notes)
