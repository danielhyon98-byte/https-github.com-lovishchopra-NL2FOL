"""The combinator port ``epinoic.integration.combinator-port.v1``: round trips and the refusal of out-of-contract input
and output (the closed transformation vocabulary, citations of claims the input holds, the pinned instruction pack), the
disclosed conflicts, the hello and the named refusal of a combinator, the ``synthesis/1.0`` payload the service relays,
and the published contract (its documents, generated files and digest)."""
from __future__ import annotations

import copy

import pytest

from epinoic_logic.integration import combinator_port as CB
from epinoic_logic.integration.canonical import sha256_text
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import PROTOCOL, dump

PACK = {"name": "combinator-instructions", "version": "1.0", "sha256": "9a" * 32}
IDS = {"task_id": "t_" + "0" * 31 + "1", "request_id": "a_" + "0" * 31 + "1"}


def claim(cid, text, materiality="material"):
    return {"claim_id": cid, "role": "point", "materiality": materiality, "certainty": "established", "claim_text_sha256": sha256_text(text), "text": text}


def source(rid, agent, *claims):
    return {"report_id": rid, "agent_id": agent, "subject": "History", "branch": "history", "claims": list(claims)}


INPUT = {"schema": "epinoic.integration.combinator-input.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": IDS,
         "sources": [source("rep-h", "history", claim("h1", "The treaty was signed in 1919.")),
                     source("rep-e", "english-a-literature", claim("e1", "The poem's speaker mourns the war."))],
         "vocabulary": list(CB.VOCABULARY), "instruction_pack": PACK}
OUTPUT = {"schema": "epinoic.integration.combinator-output.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": IDS,
          "instruction_pack_sha256": PACK["sha256"],
          "claims": [{"text": "The treaty was signed in 1919.", "source_claim_ids": ["h1"], "certainty": "established", "transformation": "carried", "evidence_refs": None}],
          "dropped": [{"source_claim_ids": ["e1"], "reason": "outside the question's scope"}], "conflicts": []}


def _code(fn) -> str:
    with pytest.raises(IntegrationError) as exc:
        fn()
    return exc.value.code


def test_round_trips_and_the_arena_synthesis_format():
    inp = CB.check_input(INPUT)
    assert dump(inp) == INPUT
    out = CB.check_output(OUTPUT, inp)
    assert dump(out) == OUTPUT
    assert CB.to_synthesis_format(out) == {"claims": [{"text": "The treaty was signed in 1919.", "source_claim_ids": ["h1"], "certainty": "established", "transformation": "carried"}],
                                           "dropped": [{"source_claim_ids": ["e1"], "reason": "outside the question's scope"}]}


def test_the_vocabulary_is_the_integrity_layers_minus_new_and_dropped():
    from typing import get_args
    from epinoic_logic.integrity.contracts import SYNTHESIZED_CLAIM_TRANSFORMATIONS, Transformation
    assert set(CB.VOCABULARY) == set(get_args(Transformation)) - {"new", "dropped"}
    assert CB.VOCABULARY == SYNTHESIZED_CLAIM_TRANSFORMATIONS, "the port restates the end-to-end fixes' closed values, in their order"


@pytest.mark.parametrize("edit", [
    lambda i: i.update(vocabulary=["carried", "new", "merged", "narrowed", "generalized"]),
    lambda i: i["sources"].pop(),
    lambda i: i["sources"][0]["claims"][0].update(claim_text_sha256="0" * 64),
    lambda i: i["sources"][1]["claims"][0].update(claim_id="h1"),
    lambda i: i.update(extra=1),
])
def test_inputs_out_of_contract_are_kit_cb_001(edit):
    i = copy.deepcopy(INPUT)
    edit(i)
    assert _code(lambda: CB.check_input(i)) == "KIT-CB-001"


@pytest.mark.parametrize("edit,code", [
    (lambda o: o["claims"][0].update(transformation="new"), "KIT-CB-003"),
    (lambda o: o["claims"][0].update(transformation="joined"), "KIT-CB-003"),
    (lambda o: o["claims"][0].update(transformation="Merged"), "KIT-CB-003"),
    (lambda o: o["claims"][0].update(source_claim_ids=["x9"]), "KIT-CB-004"),
    (lambda o: o["claims"][0].update(source_claim_ids=["h1", "h1"], transformation="merged"), "KIT-CB-002"),  # one source cited twice (L2)
    (lambda o: o["claims"][0].update(source_claim_ids=["x9", "x9"]), "KIT-CB-002"),  # decided before the citations
    (lambda o: o["dropped"][0].update(source_claim_ids=["x9"]), "KIT-CB-004"),
    (lambda o: o.update(instruction_pack_sha256="0" * 64), "KIT-CB-005"),
    (lambda o: o["claims"].extend([{**o["claims"][0], "text": "z" * 4000} for _ in range(13)]), "KIT-CB-006"),
    (lambda o: o.update(ids={**IDS, "request_id": "a_other"}), "KIT-CB-002"),
    (lambda o: o["claims"][0].update(certainty="certain"), "KIT-CB-002"),
    (lambda o: o.update(claims=[]), "KIT-CB-002"),
    (lambda o: o.update(verdict="faithful"), "KIT-CB-002"),
])
def test_outputs_out_of_contract_are_refused_with_their_codes(edit, code):
    o = copy.deepcopy(OUTPUT)
    edit(o)
    assert _code(lambda: CB.check_output(o, CB.check_input(INPUT))) == code


# ----------------------------------------------------------------------------------------------- conflicts


def test_a_disclosed_conflict_round_trips_and_cites_claims_the_input_holds():
    inp = CB.check_input(INPUT)
    o = copy.deepcopy(OUTPUT)
    o["conflicts"] = [{"claim_ids": ["h1", "e1"], "description": "the two readings disagree"}]
    o["dropped"] = []
    assert dump(CB.check_output(o, inp)) == o
    assert CB.to_synthesis_format(CB.check_output(o, inp))["conflicts"] == o["conflicts"]
    for conflicts, code in (([{"claim_ids": ["h1", "x9"], "description": "x"}], "KIT-CB-004"), ([{"claim_ids": ["h1", "h1"], "description": "x"}], "KIT-CB-002"),
                            ([{"claim_ids": ["h1"], "description": "x"}], "KIT-CB-002"),
                            ([{"claim_ids": ["h1", "e1"], "description": "x", "status": "resolved_with_basis"}], "KIT-CB-002")):
        bad = {**o, "conflicts": conflicts}
        assert _code(lambda: CB.check_output(bad, inp)) == code


# ----------------------------------------------------------------------------------------------- hello and refusal

HELLO = {"schema": "epinoic.integration.combinator-hello.v1", "protocol": PROTOCOL, "port_version": "1.0",
         "combinator": {"name": "test-combinator", "version": "0.1.0"}, "instruction_pack": PACK, "contract_sha256": "c0" * 32,
         "tier": "cheapest", "vocabulary": list(CB.VOCABULARY)}


def test_a_hello_in_contract_and_the_hellos_refused():
    assert dump(CB.check_hello(HELLO)) == HELLO
    for edit in (dict(tier="strongest"), dict(vocabulary=list(reversed(CB.VOCABULARY))), dict(combinator={"name": "gpt-combinator", "version": "1"}),
                 dict(instruction_pack={**PACK, "name": "llama-pack"}), dict(model="x"), dict(port_version="2.0")):
        assert _code(lambda: CB.check_hello({**HELLO, **edit})) == "KIT-CB-002", edit
    assert _code(lambda: CB.check_hello(HELLO, contract_sha256="c1" * 32)) == "KIT-CB-002", "another version of the contract"
    assert CB.check_hello(HELLO, contract_sha256="c0" * 32).contract_sha256 == "c0" * 32


REFUSAL = {"schema": "epinoic.integration.combinator-refusal.v1", "protocol": PROTOCOL, "port_version": "1.0", "ids": IDS,
           "instruction_pack_sha256": PACK["sha256"], "code": "KIT-CB-003", "reason": "transformation_unknown", "detail": "claims[0].transformation: 'joined'"}


def test_a_refusal_names_its_reason_with_its_code_and_the_request_it_refuses():
    inp = CB.check_input(INPUT)
    assert dump(CB.check_refusal(REFUSAL, inp)) == REFUSAL
    assert set(CB.REFUSAL_REASONS.values()) == {f"KIT-CB-00{n}" for n in range(1, 7)}
    for reason, code in CB.REFUSAL_REASONS.items():
        ids = None if reason in ("input_not_json", "input_invalid") else IDS
        assert CB.check_refusal({**REFUSAL, "reason": reason, "code": code, "ids": ids}).reason == reason
    assert CB.check_refusal({**REFUSAL, "reason": "internal_error", "code": "KIT-CB-002", "ids": None}).ids is None
    for edit in (dict(code="KIT-CB-002"), dict(ids=None), dict(reason="input_invalid", code="KIT-CB-001"), dict(reason="provider_timeout"),
                 dict(detail=""), dict(detail="x" * 301), dict(ids={**IDS, "request_id": "a_other"})):
        assert _code(lambda: CB.check_refusal({**REFUSAL, **edit}, inp)) == "KIT-CB-002", edit


# ----------------------------------------------------------------------------------------------- the payload the hub receives


def test_the_synthesis_payload_validates_against_the_hubs_contract():
    from epinoic_logic.integrity.contracts import Synthesis
    inp = CB.check_input(INPUT)
    o = copy.deepcopy(OUTPUT)
    o["claims"].append({"text": "The poem's speaker mourns the war.", "source_claim_ids": ["e1"], "certainty": "established", "transformation": "carried",
                        "evidence_refs": [{"document_id": "poem", "locator": None, "excerpt": None}]})
    o["dropped"] = []
    o["conflicts"] = [{"claim_ids": ["h1", "e1"], "description": "x"}]
    out = CB.check_output(o, inp)
    payload = CB.synthesis_payload(out, inp, synthesis_id="syn-1", combinator_agent_id="synthesis", created_at="2026-10-17T00:00:00Z",
                                   evidence_refs={0: [{"document_id": "doc-h", "locator": "para:1", "excerpt": "1919"}]})
    syn = Synthesis.model_validate(payload)
    assert [c.claim_id for c in syn.claims] == ["s0", "s1"] and syn.source_report_ids == ["rep-h", "rep-e"]
    assert syn.claims[0].evidence_refs[0].document_id == "doc-h" and syn.claims[1].evidence_refs[0].document_id == "poem"
    assert syn.conflicts[0].status == "unresolved" and syn.text == "The treaty was signed in 1919. The poem's speaker mourns the war."
    assert (syn.request_id, syn.task_id) == (IDS["request_id"], IDS["task_id"])


def test_synthesized_claim_ids_never_reuse_a_source_claim_id():
    i = copy.deepcopy(INPUT)
    i["sources"][0]["claims"][0].update(claim_id="s0")
    inp = CB.check_input(i)
    o = copy.deepcopy(OUTPUT)
    o["claims"][0]["source_claim_ids"] = ["s0"]
    payload = CB.synthesis_payload(CB.check_output(o, inp), inp, synthesis_id="syn-1", combinator_agent_id="synthesis", created_at="2026-10-17T00:00:00Z")
    assert [c["claim_id"] for c in payload["claims"]] == ["ss0"]


def test_an_input_is_built_from_the_delivered_reports_payloads():
    payload = {"report_id": "rep-h", "agent_id": "history", "subject": "History",
               "claims": [{"claim_id": "h1", "claim_role": "point", "materiality": "material", "certainty": "established", "claim_text": "The treaty was signed in 1919."}]}
    other = {"report_id": "rep-e", "agent_id": "english-a-literature", "subject": "History",
             "claims": [{"claim_id": "e1", "claim_role": "point", "materiality": "material", "certainty": "established", "claim_text": "The poem's speaker mourns the war."}]}
    inp = CB.build_input(IDS, [CB.source_report(payload, "history"), CB.source_report(other, "history")], PACK)
    assert dump(inp) == INPUT
    assert _code(lambda: CB.build_input(IDS, [CB.source_report(payload, "history")], PACK)) == "KIT-CB-001", "a combined answer has two sources at least"


# ----------------------------------------------------------------------------------------------- the published contract


def test_the_published_contract_is_the_generated_files_and_its_digest_is_stable():
    import json
    from pathlib import Path
    from epinoic_logic.integration.canonical import sha256_json
    root = Path(__file__).resolve().parents[2]
    docs = CB.contract_documents()
    assert list(docs) == list(CB.CONTRACT_FILES)
    for name, doc in docs.items():
        assert json.loads((root / "integration" / "schemas" / name).read_text(encoding="utf-8")) == doc, name
    assert CB.contract_digest() == sha256_json(docs) == CB.contract_digest(docs)
    vocab = docs["synthesis-vocabulary.v1.json"]
    assert vocab["synthesized_claim_transformations"] == list(CB.VOCABULARY) and vocab["certainty"] == ["established", "probable", "possible"]
    rules = docs["combinator-port.v1.json"]
    assert rules["refusal_reasons"] == dict(CB.REFUSAL_REASONS) and rules["max_output_text_bytes"] == CB.MAX_OUTPUT_TEXT_BYTES
