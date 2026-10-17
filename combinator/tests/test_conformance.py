"""Conformance with the translator's combinator port (``epinoic_logic.integration.combinator_port``), the side the
published contract is generated from. Inside the translator repository these tests always run (the ``kit`` fixture).

1. the contract copy is the published contract (the same documents, the same digest);
2. every port vector gets the port's verdict from the combinator's own checks (input, output, hello, refusal);
3. the hello passes the port, contract digest included;
4. everything the runner lets out passes the port: an output round-trips exactly (``dump(check_output(...))`` is the
   runner's text), a refusal is in contract and names the request it refuses;
5. on generated outputs both sides give the same verdict, so the runner's last gate is the port's own rule;
6. the vocabulary and the limits it restates are the port's and the hub's;
7. a message passed already parsed is held to the protocol's JSON rules first, on both sides, so both give one code.
"""
from __future__ import annotations

import copy
import json

import pytest
from hypothesis import given, settings, strategies as st

from combinator_helpers import MALFORMED, input_doc, faithful_agent_output, load_vectors, text
from epinoic_combinator import port
from epinoic_combinator import runner as R
from epinoic_combinator.contract import load_contract
from epinoic_combinator.jsonio import canonical_json
from epinoic_combinator.providers import FaithfulFakeProvider, ScriptedProvider

CONTRACT = load_contract()
VECTORS = load_vectors("combinator-port")


def _kit_code(fn):
    from epinoic_logic.integration.errors import IntegrationError
    try:
        fn()
    except IntegrationError as exc:
        return exc.code
    return None


def test_1_the_copy_is_the_published_contract(kit):
    assert CONTRACT.documents == kit.contract_documents()
    assert CONTRACT.sha256 == kit.contract_digest() and list(CONTRACT.documents) == list(kit.CONTRACT_FILES)


def test_2_the_vectors_are_present():
    kinds = {v["kind"] for v in VECTORS}
    assert len(VECTORS) >= 40 and kinds == {"input", "output", "hello", "refusal"}


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_2_every_port_vector_gets_the_ports_verdict_from_the_combinators_own_checks(vector):
    kind, msg = vector["kind"], vector["message"]
    if kind == "input":
        problem = CONTRACT.check_input(msg)[1]
    elif kind == "output":
        inp, p = CONTRACT.check_input(vector["input"])
        assert p is None
        problem = CONTRACT.check_output(msg, inp)
    elif kind == "hello":
        problem = CONTRACT.check_hello(msg)
    else:
        inp, p = CONTRACT.check_input(vector["input"])
        assert p is None
        problem = CONTRACT.check_refusal(msg, inp)
    got = {"ok": problem is None, "code": None if problem is None else problem.code}
    assert got == vector["expect"], (vector["name"], problem)


def test_3_the_hello_passes_the_port(kit):
    hello = kit.check_hello(port.hello(), contract_sha256=kit.contract_digest())
    assert hello.instruction_pack.sha256 == json.loads(port.hello())["instruction_pack"]["sha256"]


def _cases():
    yield "faithful", FaithfulFakeProvider()
    yield "no provider", None
    for name, agent_text, _code, _reason in MALFORMED:
        yield name, ScriptedProvider(agent_text)
    yield "provider fails", ScriptedProvider(RuntimeError("x"))


def test_4_everything_the_runner_lets_out_passes_the_port(kit):
    from epinoic_logic.integration.protocol import dump
    inp = kit.check_input(input_doc())
    for name, provider in _cases():
        result = R.run(input_doc(), provider)
        if result.ok:
            checked = kit.check_output(result.text, inp)
            assert canonical_json(dump(checked)) == result.text, name
        else:
            refusal = kit.check_refusal(result.text, inp)
            assert refusal.ids is not None and refusal.ids == inp.ids and refusal.code == kit.REFUSAL_REASONS[refusal.reason], name
    for doc in ("{not json", input_doc(port_version="2.0")):
        refusal = kit.check_refusal(R.run(doc, FaithfulFakeProvider()).text)
        assert refusal.ids is None and refusal.code == "KIT-CB-001"


_EDITS = st.lists(st.tuples(st.sampled_from(["top", "claim", "dropped"]),
                            st.sampled_from(["text", "source_claim_ids", "certainty", "transformation", "evidence_refs", "reason", "claims", "dropped",
                                             "conflicts", "ids", "instruction_pack_sha256", "schema", "note"]),
                            st.one_of(st.none(), st.booleans(), st.integers(-3, 3), st.text(max_size=10),
                                      st.sampled_from(["carried", "joined", "certain", "established", "h1.1", "x9", "z" * 4001]),
                                      st.lists(st.sampled_from(["h1.1", "e1.1", "x9", "h1.1"]), max_size=3),
                                      st.just([{"claim_ids": ["h1.1", "e1.1"], "description": "x"}]))), max_size=3)


@settings(max_examples=300, deadline=None)
@given(_EDITS)
def test_5_on_generated_outputs_both_sides_give_the_same_verdict(kit, edits):
    inp_doc = input_doc()
    inp = kit.check_input(inp_doc)
    ok = json.loads(R.run(inp_doc, FaithfulFakeProvider()).text)
    msg = copy.deepcopy(ok)
    for where, key, value in edits:
        node = msg
        if where in ("claim", "dropped"):
            items = msg.get("claims" if where == "claim" else "dropped")
            node = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else msg
        node[key] = copy.deepcopy(value)
    mine = CONTRACT.check_output(msg, CONTRACT.check_input(inp_doc)[0])
    assert (None if mine is None else mine.code) == _kit_code(lambda: kit.check_output(msg, inp)), (edits, mine)


def test_6_the_vocabulary_and_the_limits_are_the_ports_and_the_hubs(kit):
    from epinoic_logic.integrity.contracts import CERTAINTY_RANK, SYNTHESIZED_CLAIM_TRANSFORMATIONS, TRANSFORMATION_MEANINGS
    assert CONTRACT.transformations == kit.VOCABULARY == SYNTHESIZED_CLAIM_TRANSFORMATIONS
    assert CONTRACT.meanings == {v: TRANSFORMATION_MEANINGS[v] for v in SYNTHESIZED_CLAIM_TRANSFORMATIONS}
    assert CONTRACT.certainty_rank == CERTAINTY_RANK and set(CONTRACT.certainty) == set(kit.CERTAINTIES)
    assert CONTRACT.refusal_reasons == dict(kit.REFUSAL_REASONS) and CONTRACT.max_output_text_bytes == kit.MAX_OUTPUT_TEXT_BYTES
    assert CONTRACT.max_refusal_detail_chars == kit.MAX_REFUSAL_DETAIL_CHARS and CONTRACT.port_version == kit.PORT_VERSION


def test_6_the_hub_accepts_the_payload_of_every_output_the_runner_lets_out(kit):
    """The projection of an output (``combinator_port.synthesis_payload``) validates against the hub's synthesis contract."""
    from epinoic_logic.integrity.contracts import Synthesis
    inp = kit.check_input(input_doc())
    agent = faithful_agent_output()
    agent["conflicts"] = [{"claim_ids": ["h1.1", "e1.1"], "description": "the dates disagree"}]
    for provider in (FaithfulFakeProvider(), ScriptedProvider(text(agent))):
        result = R.run(input_doc(), provider)
        out = kit.check_output(result.text, inp)
        payload = kit.synthesis_payload(out, inp, synthesis_id="syn-1", combinator_agent_id="synthesis", created_at="2026-10-17T00:00:00Z")
        syn = Synthesis.model_validate(payload)
        assert [c.claim_id for c in syn.claims] == [f"s{i}" for i in range(len(out.claims))]
        assert {e.transformation for e in syn.ledger} <= {"dropped"} and all(k.status == "unresolved" for k in syn.conflicts)


def test_7_a_message_passed_already_parsed_gets_the_ports_code_from_both_sides(kit):
    """Both sides hold a message passed already parsed to the protocol's JSON rules before any other rule (verification
    round 2, V2-L2): a lone surrogate, a float or a non-string key is "not protocol JSON", so even an output that also
    carries an unknown transformation gets the same code on both sides."""
    from combinator_helpers import input_doc as fresh
    inp_k, inp_c = kit.check_input(input_doc()), CONTRACT.check_input(input_doc())[0]
    for change in (lambda d: d["sources"][0]["claims"][0].update(text="\ud800"), lambda d: d.update(port_version=1.0),
                   lambda d: d["sources"][0]["claims"][0].update({1: "x"})):
        doc = fresh()
        change(doc)
        assert CONTRACT.check_input(doc)[1].code == _kit_code(lambda: kit.check_input(doc)) == "KIT-CB-001"
    out = json.loads(R.run(input_doc(), FaithfulFakeProvider()).text)
    for change in (lambda o: o["claims"][0].update(text="\ud800"), lambda o: o["claims"][0].update(certainty=1.5)):
        msg = copy.deepcopy(out)
        change(msg)
        msg["claims"][-1]["transformation"] = "joined"
        assert CONTRACT.check_output(msg, inp_c).code == _kit_code(lambda: kit.check_output(msg, inp_k)) == "KIT-CB-002"
