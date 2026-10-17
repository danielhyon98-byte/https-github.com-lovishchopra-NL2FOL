"""The combinator port ``epinoic.integration.combinator-port.v1``: round trips and the refusal of out-of-contract input
and output (the closed transformation vocabulary, citations of claims the input holds, the pinned instruction pack)."""
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
          "dropped": [{"source_claim_ids": ["e1"], "reason": "outside the question's scope"}]}


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
    from epinoic_logic.integrity.contracts import Transformation
    assert set(CB.VOCABULARY) == set(get_args(Transformation)) - {"new", "dropped"}


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
