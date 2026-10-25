"""The dossier: built from the journal, issued to one agent under one pack, with the header the agent copies, a pointer
``at`` per transfer and an ``index`` of every identifier; strict JSON Pointers; the digest; truncation; redaction (no key,
no signature, no auditor finding in blind mode)."""
from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from epinoic_logic.overseer import OverseerView, ResultStore
from epinoic_logic.overseer.dossier import (
    TRUNCATE_AT, TRUNCATION_MARKER, Dossier, PointerError, build_dossier, dossier_digest, dossier_identifiers, pointer_join, resolve_pointer,
    truncated_pointers, verify_dossier_digest, visible_text,
)
from epinoic_logic.overseer.verdicts import PackIdentity

from .conftest import EN_INPUT, HI_TEXT, KEY, SECRET, DOC, english_report, make_keyring, new_channel, run_task

PACK = PackIdentity(name="overseer-knowledge-docs", version="1.0", sha256="ab" * 32)
PACK_11 = PackIdentity(name="overseer-knowledge-docs", version="1.1", sha256="cd" * 32)


@pytest.fixture
def task(auditor):
    t = run_task(auditor)
    t.audit_obj = t.audit()
    return t


def _dossier(auditor, task, **kw):
    opts = dict(mode="blind", lens="general", agent_id="overseer-general-1", pack=PACK)
    opts.update(kw)
    return build_dossier(auditor.view(task.uid), **opts)


def _keys(x, out=None):
    out = set() if out is None else out
    if isinstance(x, dict):
        for k, v in x.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(x, list):
        for v in x:
            _keys(v, out)
    return out


# ------------------------------------------------------------------------------------------- shape and header
def test_dossier_validates_and_its_digest_holds(auditor, task):
    d = _dossier(auditor, task)
    Dossier.model_validate(d)
    assert verify_dossier_digest(d) and d["dossier_sha256"] == dossier_digest(d)
    assert d["dossier_version"] == "1.0" and d["verdict_contract"] == "overseer_verdict/1.0"
    assert d["agent_id"] == "overseer-general-1" and d["pack"] == PACK.model_dump() and d["mode"] == "blind" and d["lens"] == "general"
    assert d["task"]["task_id"] == "task-ovs" and d["task"]["request_id"] == "req-ovs" and d["task"]["plan"]["selected_agent_ids"]
    assert json.loads(json.dumps(d)) == d  # plain JSON values only


def test_transfers_in_sequence_order_each_with_its_own_pointer(auditor, task):
    d = _dossier(auditor, task)
    kinds = [t["kind"] for t in d["transfers"]]
    assert kinds == ["request", "response", "relay_forward", "request", "response_text", "relay_synthesis"]
    seqs = [t["seq"] for t in d["transfers"]]
    assert seqs == sorted(seqs) and all(resolve_pointer(d, t["at"]) == t for t in d["transfers"])
    assert [t["at"] for t in d["transfers"]] == [f"/transfers/{i}" for i in range(len(kinds))]
    assert [t["message_id"] for t in d["transfers"]] == [task.mids[k] for k in ("req_en", "rep_en", "fwd", "req_hi", "rep_hi", "syn")]
    rep = d["transfers"][1]
    assert rep["direction"] == "specialist_to_router" and rep["sender"] == {"agent_id": "english-specialist", "role": "specialist"}
    assert rep["contract"].startswith("specialist_report/") and rep["in_reply_to"] == task.mids["req_en"]
    assert rep["payload"]["report_id"] == "rep-en-1" and rep["payload_sha256"] and rep["receipt"]["status"] == "ACCEPTED"
    assert set(rep["receipt"]) == {"status", "findings", "coverage", "constraint_results", "outcomes", "structural_findings", "formal_checks",
                                   "formal_result_ids", "summary"}
    assert d["transfers"][4]["raw_text"] == HI_TEXT and "raw_text" not in d["transfers"][1]
    assert rep["pool_after"] and {"claim_id", "problem_digest", "ambiguous", "agent_id", "report_id"} == set(rep["pool_after"][0])


def test_results_carry_signature_presence_never_the_signature(auditor, task):
    d = _dossier(auditor, task)
    cited = {r for t in d["transfers"] for r in t["cited_result_ids"]}
    assert d["results"] and set(d["results"]) <= cited
    for rid, r in d["results"].items():
        assert r["signature_present"] is True and r["signature_key_id"] and set(r["binding"]) == {"problem_digest", "config_digest", "versions_digest", "binding_digest"}
        assert r["status"] == auditor.store.get(rid).status and "problem" in r
    assert "signature" not in _keys(d)  # receipts' copies of results are redacted too
    outcome = d["transfers"][1]["receipt"]["outcomes"][0]["verification"]
    assert outcome["signature_present"] is True and outcome["signature_key_id"]


def test_no_key_or_secret_ever_appears(auditor, task):
    text = json.dumps(_dossier(auditor, task, mode="informed", audit=task.audit_obj), ensure_ascii=False)
    ring = make_keyring()
    for secret in [KEY, SECRET] + [ring.subkey(label) for label in ("journal", "audit", "runs", "sampling", "intake")]:
        assert secret.hex() not in text and secret.decode("latin-1") not in text


def test_blind_mode_has_no_auditor_section_and_informed_mode_shows_the_audit_findings(auditor, task):
    blind = _dossier(auditor, task)
    assert "auditor" not in blind
    informed = _dossier(auditor, task, mode="informed", audit=task.audit_obj)
    assert [f["code"] for f in informed["auditor"]["findings"]] == [f.code for f in task.audit_obj.report.findings]
    for k in ("transfers", "results", "links", "index", "task"):
        assert informed[k] == blind[k]
    with pytest.raises(ValueError):
        _dossier(auditor, task, mode="informed")


def test_two_agents_get_different_digests_over_identical_content(auditor, task):
    a = _dossier(auditor, task, agent_id="overseer-content-1", lens="content_fidelity")
    b = _dossier(auditor, task, agent_id="overseer-peer-1", lens="peer_synthesis")
    c = _dossier(auditor, task, agent_id="overseer-content-1", lens="content_fidelity", pack=PACK_11)
    assert len({a["dossier_sha256"], b["dossier_sha256"], c["dossier_sha256"]}) == 3
    for k in ("transfers", "results", "links", "index", "task"):
        assert a[k] == b[k] == c[k]
    assert a == _dossier(auditor, task, agent_id="overseer-content-1", lens="content_fidelity")  # deterministic


def test_the_dossier_reads_the_journal_not_the_live_objects(auditor, task):
    before = _dossier(auditor, task)
    task.ch.channel.log.get(task.mids["rep_en"]).payload["claims"][0]["claim_text"] = "rewritten after issue"
    task.ch.channel.transmitted_reports["rep-en-1"].claims.pop()
    after = _dossier(auditor, task)
    assert after["transfers"] == before["transfers"] and after["dossier_sha256"] == before["dossier_sha256"]


# ------------------------------------------------------------------------------------------- links and index
def test_links_say_where_to_look(auditor, task):
    d = _dossier(auditor, task)
    assert d["links"]["forwards"] == [{"forward_message_id": task.mids["fwd"], "report_id": "rep-en-1", "delivering_message_id": task.mids["rep_en"]}]
    assert d["links"]["peer_documents"] == [{"request_message_id": task.mids["req_hi"], "document_id": "peer:en", "earlier_forward_message_ids": [task.mids["fwd"]]}]
    cites = {(c["report_id"], c["delivering_message_id"]) for c in d["links"]["synthesis_citations"]}
    assert cites == {("rep-en-1", task.mids["rep_en"]), ("rep-hi-1", task.mids["rep_hi"])}
    assert all(c["synthesis_message_id"] == task.mids["syn"] for c in d["links"]["synthesis_citations"])


def test_every_index_pointer_resolves_to_its_identifier(auditor, task):
    d = _dossier(auditor, task)
    types = {e["type"] for e in d["index"]}
    assert {"message", "receipt", "report", "claim", "synthesized_claim", "result", "document"} <= types
    for e in d["index"]:
        node = resolve_pointer(d, e["pointer"])
        if e["type"] == "message":
            assert node["message_id"] == e["id"]
        elif e["type"] == "receipt":
            assert resolve_pointer(d, e["pointer"].rsplit("/", 1)[0])["receipt_id"] == e["id"]
        elif e["type"] in ("claim", "synthesized_claim"):
            assert node["claim_id"] == e["id"] and e["report_id"]
        elif e["type"] == "report":
            assert node["report_id"] == e["id"]
        elif e["type"] == "result":
            assert e["pointer"] == pointer_join("results", e["id"])
        elif e["type"] == "document":
            assert node["document_id"] == e["id"]
    claims = [e for e in d["index"] if e["type"] == "claim" and e["id"] == "en-point"]
    assert {e["pointer"] for e in claims} == {"/transfers/1/payload/claims/0", "/transfers/2/payload/claims/0"}  # delivery and forward


def test_a_conflict_record_is_indexed(auditor):
    task = run_task(auditor, conflicts=({"conflict_id": "cf-1", "claim_ids": ["en-point", "h1.1"], "description": "they disagree", "status": "unresolved"},))
    d = build_dossier(auditor.view(task.uid), mode="blind", lens="general", agent_id="overseer-peer-1", pack=PACK)
    e = [x for x in d["index"] if x["type"] == "conflict"]
    assert e and e[0]["id"] == "cf-1" and resolve_pointer(d, e[0]["pointer"])["conflict_id"] == "cf-1"


def test_a_cited_result_the_store_does_not_retain_is_absent_from_results_but_indexed_at_its_citation(auditor, task):
    view = OverseerView.from_journal(auditor.journal(task.uid), ResultStore(make_keyring()))  # an empty store
    d = build_dossier(view, mode="blind", lens="general", agent_id="overseer-general-1", pack=PACK)
    assert d["results"] == {}
    cited = [e for e in d["index"] if e["type"] == "result"]
    assert cited and all("/cited_result_ids/" in e["pointer"] and resolve_pointer(d, e["pointer"]) == e["id"] for e in cited)
    assert len({e["id"] for e in cited}) == len(cited)


def test_identifiers_are_every_short_string_value(auditor, task):
    d = _dossier(auditor, task)
    ids = dossier_identifiers(d)
    assert {task.mids["rep_en"], task.receipts["rep_en"].receipt_id, "en-point", "rep-en-1", "doc-mill", "peer:en", "syn-1"} <= ids
    assert set(d["results"]) <= ids and "overseer-general-1" not in ids  # the header is not a source of identifiers


# ------------------------------------------------------------------------------------------- withheld responses
def test_a_withheld_response_shows_only_its_digest(auditor):
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "history-specialist", "Explain the Factory Act of 1833.", [])
    msg, rc = ch.respond_text(m.message_id, HI_TEXT, agent_id="english-specialist", report_id="rep-x")
    assert msg is None
    d = build_dossier(auditor.view(ch.uid), mode="blind", lens="general", agent_id="overseer-general-1", pack=PACK)
    t = d["transfers"][1]
    assert set(t["payload"]) == {"withheld"} and set(t["payload"]["withheld"]) == {"response_sha256", "response_chars"}
    assert t["receipt"]["status"] == "REJECTED" and t["raw_text"] == HI_TEXT
    assert not [e for e in d["index"] if e["type"] == "report"]


# ------------------------------------------------------------------------------------------- truncation
def test_long_fields_are_cut_listed_and_quotable_only_in_their_visible_part(auditor):
    long_text = "The writer presents work as endless. " + "The mill turned and turned. " * 900
    assert len(long_text) > TRUNCATE_AT
    ch = new_channel(auditor)
    m, _r, _q = ch.request("router", "english-specialist", EN_INPUT, [DOC])
    claims = [dict(claim_id="en-point", claim_text="The writer presents work as endless", claim_role="point", materiality="material")]
    ch.respond(m.message_id, english_report(text=long_text, claims=claims))
    d = build_dossier(auditor.view(ch.uid), mode="blind", lens="general", agent_id="overseer-general-1", pack=PACK)
    ptr = "/transfers/1/payload/original_response"
    cut = truncated_pointers(d)
    assert ptr in cut and cut[ptr]["chars"] == len(long_text)
    import hashlib
    assert cut[ptr]["sha256"] == hashlib.sha256(long_text.encode()).hexdigest()
    value = resolve_pointer(d, ptr)
    assert value.endswith(TRUNCATION_MARKER) and len(value) == TRUNCATE_AT + len(TRUNCATION_MARKER)
    visible = visible_text(d, ptr, value)
    assert visible == long_text[:TRUNCATE_AT] and TRUNCATION_MARKER not in visible
    assert verify_dossier_digest(d)


def test_visible_text_of_non_strings_is_their_canonical_json():
    d = {"limits": {"truncated_fields": []}}
    assert visible_text(d, "/x", ["c1", "c2"]) == '["c1","c2"]' and visible_text(d, "/x", True) == "true"


# ------------------------------------------------------------------------------------------- pointers
@pytest.mark.parametrize("pointer,expected", [
    ("", {"a/b": {"m~n": [10, 20]}, "": 1}),
    ("/a~1b/m~0n/1", 20),
    ("/a~1b/m~0n/0", 10),
    ("/", 1),
])
def test_rfc6901_resolution(pointer, expected):
    doc = {"a/b": {"m~n": [10, 20]}, "": 1}
    assert resolve_pointer(doc, pointer) == expected


@pytest.mark.parametrize("pointer", ["/a~1b/m~0n/2", "/a~1b/m~0n/-", "/a~1b/m~0n/01", "/a~1b/m~0n/x", "/a~1b/m~0n/0/x", "/missing", "a~1b",
                                     "/a~2b", "/a~", "/a~1b/m~0n/١"])
def test_unresolvable_pointers(pointer):
    doc = {"a/b": {"m~n": [10, 20]}, "": 1}
    with pytest.raises(PointerError):
        resolve_pointer(doc, pointer)


def test_pointer_join_escapes():
    assert pointer_join("results", "a/b~c", "status") == "/results/a~1b~0c/status"
    assert resolve_pointer({"results": {"a/b~c": {"status": "ENTAILED"}}}, pointer_join("results", "a/b~c", "status")) == "ENTAILED"


# ------------------------------------------------------------------------------------------- digest and contract
def test_any_change_breaks_the_digest(auditor, task):
    d = _dossier(auditor, task)
    for mutate in (lambda x: x["transfers"][1]["payload"]["claims"][0].update(claim_text="changed"),
                   lambda x: x.update(agent_id="overseer-general-2"),
                   lambda x: x["pack"].update(version="1.1"),
                   lambda x: x.update(lens="custody_results"),
                   lambda x: x.update(dossier_sha256="0" * 64)):
        e = copy.deepcopy(d)
        mutate(e)
        assert not verify_dossier_digest(e)
    assert not verify_dossier_digest({"dossier_sha256": 5}) and not verify_dossier_digest([])


@pytest.mark.parametrize("mutate", [
    lambda d: d.update(extra=1),
    lambda d: d["transfers"][0].update(extra=1),
    lambda d: d["transfers"][1]["receipt"].update(extra=1),
    lambda d: d["transfers"][0].update(at="/transfers/3"),
    lambda d: d.update(auditor={"findings": []}),
    lambda d: d.update(mode="informed"),
    lambda d: d.update(verdict_contract="overseer_verdict/1.1"),
    lambda d: d.update(dossier_version="2.0"),
    lambda d: d["pack"].update(sha256="xyz"),
    lambda d: d["index"][0].update(type="secret"),
    lambda d: d["transfers"][0].update(seq="1"),
])
def test_the_dossier_contract_is_strict(auditor, task, mutate):
    d = copy.deepcopy(_dossier(auditor, task))
    mutate(d)
    with pytest.raises(ValidationError):
        Dossier.model_validate(d)


def test_refusals(auditor, task):
    view = auditor.view(task.uid)
    with pytest.raises(ValueError):
        build_dossier(view, mode="sighted", lens="general", agent_id="a", pack=PACK)
    with pytest.raises(ValueError):
        build_dossier(view, mode="blind", lens="everything", agent_id="a", pack=PACK)
    with pytest.raises(TypeError):
        build_dossier(view, mode="blind", lens="general", agent_id="a", pack=PACK.model_dump())
    other = run_task(auditor, synthesis=False)
    with pytest.raises(ValueError):
        build_dossier(view, mode="informed", lens="general", agent_id="a", pack=PACK, audit=other.audit())
    degraded = OverseerView.from_channel(task.ch.channel, auditor.store)
    with pytest.raises(ValueError):
        build_dossier(degraded, mode="blind", lens="general", agent_id="a", pack=PACK)


def test_schema_is_generable_and_strict():
    schema = Dossier.model_json_schema()
    assert schema["additionalProperties"] is False and schema["properties"]["verdict_contract"]["const"] == "overseer_verdict/1.0"
    for name in ("DossierTransfer", "DossierReceipt", "DossierResult", "IndexEntry", "DossierLinks", "DossierLimits", "PackIdentity"):
        assert schema["$defs"][name]["additionalProperties"] is False
