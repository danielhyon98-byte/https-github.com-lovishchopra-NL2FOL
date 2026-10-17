"""The published contract's copy and the validator that reads it (no translator needed).

* the copy loads, every schema uses only keywords the validator implements, and its digest is the digest of the files;
* the validator fails closed: a schema with a keyword or a form it does not implement is refused when it is loaded;
* the semantics are the port's: no coercion, lengths in code points, a pattern's ``$`` at the end of the text only;
* an error never echoes prose; the canonical JSON is the translator's byte for byte (its canonical vectors);
* the port rules a schema cannot state are applied in the port's order.
"""
from __future__ import annotations

import copy

import pytest

from combinator_helpers import IDS, input_doc, load_vectors
from epinoic_combinator.contract import CONTRACT_FILES, Contract, ContractUnavailable, load_contract
from epinoic_combinator.jsonio import JsonError, canonical_json, loads_strict, sha256_json, sha256_text
from epinoic_combinator.pack import load_pack
from epinoic_combinator.schema import SchemaUnsupported, Validator, shown

CONTRACT = load_contract()
PACK = load_pack()


def test_the_copy_loads_and_its_digest_is_the_digest_of_its_files():
    c = Contract()
    assert list(c.documents) == list(CONTRACT_FILES) and c.sha256 == sha256_json(c.documents) == CONTRACT.sha256
    assert c.transformations == ("carried", "paraphrased", "merged", "narrowed", "generalized")
    assert c.certainty == ("established", "probable", "possible") and c.certainty_rank == {"possible": 1, "probable": 2, "established": 3}
    assert c.refusal_reasons["transformation_unknown"] == "KIT-CB-003" and c.max_output_text_bytes == 49152


def test_a_copy_without_one_of_its_files_is_refused():
    docs = dict(CONTRACT.documents)
    docs.pop("combinator-port.v1.json")
    with pytest.raises(ContractUnavailable):
        Contract(docs)


@pytest.mark.parametrize("schema", [
    {"type": "object", "oneOf": [{"type": "string"}]},
    {"type": "object", "additionalProperties": {"type": "string"}},
    {"$ref": "https://example.invalid/schema"},
    {"type": "string", "pattern": "[a-z]+"},
    {"type": "string", "pattern": "^a$|^b$"},
    {"type": "number"},
    {"type": "array", "items": [{"type": "string"}]},
    {"type": "object", "properties": {"a": {"type": "string", "format": "email"}}},
])
def test_a_schema_with_a_rule_the_validator_does_not_implement_is_refused(schema):
    with pytest.raises(SchemaUnsupported):
        Validator(schema)


def test_no_coercion_and_lengths_in_code_points():
    v = Validator({"type": "object", "additionalProperties": False, "required": ["n", "s"],
                   "properties": {"n": {"type": "integer"}, "s": {"type": "string", "maxLength": 3}, "b": {"type": "boolean"}}})
    assert v.is_valid({"n": 1, "s": "été"})
    assert not v.is_valid({"n": True, "s": "a"}), "a boolean is no integer"
    assert not v.is_valid({"n": "1", "s": "a"}), "a string is no integer"
    assert not v.is_valid({"n": 1, "s": "abcd"})
    assert not v.is_valid({"n": 1, "s": "a", "b": 0}), "an integer is no boolean"
    assert not v.is_valid({"n": 1, "s": "a", "x": None}), "a key the schema does not have"


def test_a_pattern_ends_at_the_end_of_the_text():
    v = Validator({"type": "string", "pattern": "^[A-Za-z0-9._:-]{1,128}$"})
    assert v.is_valid("h1.1") and not v.is_valid("h1.1\n") and not v.is_valid("") and not v.is_valid("h 1")


def test_errors_never_echo_prose():
    prose = "The combinator joined the verdict with its reason and kept the figures verbatim."
    assert shown(prose) == f"free text of {len(prose)} characters" and shown("joined") == "'joined'"
    errors = CONTRACT.output.errors({"claims": prose})
    assert errors and all(prose not in e and prose[:20] not in e for e in errors)


def test_canonical_json_is_the_translators_on_its_vectors():
    vectors = load_vectors("canonical")
    assert len(vectors) >= 9
    for v in vectors:
        if v["name"] == "texts":
            assert all(sha256_text(t["text"]) == t["sha256"] for t in v["texts"])
        elif v["name"] == "refused":
            for doc in v["documents"]:
                with pytest.raises(JsonError):
                    loads_strict(doc)
        else:
            assert canonical_json(v["value"]) == v["canonical"] and sha256_json(v["value"]) == v["sha256"], v["name"]


def test_an_input_in_contract_and_each_input_rule():
    inp, problem = CONTRACT.check_input(input_doc())
    assert problem is None and inp["ids"] == IDS
    bad = input_doc()
    bad["sources"][1]["claims"][0]["claim_id"] = "h1.1"
    assert CONTRACT.check_input(bad)[1].reason == "input_invalid"
    bad = input_doc(vocabulary=list(reversed(CONTRACT.transformations)))
    assert CONTRACT.check_input(bad)[1].code == "KIT-CB-001"
    bad = input_doc()
    bad["sources"][0]["claims"][0]["text"] += " (edited)"
    assert "digest" in CONTRACT.check_input(bad)[1].detail
    assert CONTRACT.check_input('{"a": 1, "a": 2}')[1].reason == "input_not_json"
    assert CONTRACT.check_input("[1]")[1].reason == "input_invalid"


def _message(**changes):
    inp, _ = CONTRACT.check_input(input_doc())
    msg = {"schema": "epinoic.integration.combinator-output.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0", "ids": dict(IDS),
           "instruction_pack_sha256": PACK.sha256,
           "claims": [{"text": "The Treaty of Versailles was signed in June 1919.", "source_claim_ids": ["h1.1"], "certainty": "established",
                       "transformation": "carried", "evidence_refs": None}],
           "dropped": [], "conflicts": []}
    msg.update(changes)
    return msg, inp


def test_the_output_rules_come_in_the_ports_order():
    msg, inp = _message()
    assert CONTRACT.check_output(msg, inp) is None
    # a transformation outside the vocabulary is named before anything else, an extra key included
    m = copy.deepcopy(msg)
    m["claims"][0]["transformation"] = "joined"
    m["note"] = "x"
    assert CONTRACT.check_output(m, inp).code == "KIT-CB-003"
    # another request before another pack, another pack before an unknown citation
    m, _ = _message(ids={**IDS, "request_id": "a_other"}, instruction_pack_sha256="0" * 64)
    assert CONTRACT.check_output(m, inp).detail == "the output answers another request"
    m, _ = _message(instruction_pack_sha256="0" * 64)
    m["claims"][0]["source_claim_ids"] = ["x9"]
    assert CONTRACT.check_output(m, inp).code == "KIT-CB-005"
    m, _ = _message(conflicts=[{"claim_ids": ["h1.1", "h1.1"], "description": "x"}])
    assert CONTRACT.check_output(m, inp).code == "KIT-CB-002"
    m, _ = _message(conflicts=[{"claim_ids": ["h1.1", "x9"], "description": "x"}])
    assert CONTRACT.check_output(m, inp).code == "KIT-CB-004"
    m, _ = _message()
    m["claims"] = [{**m["claims"][0], "text": "z" * 4000} for _ in range(13)]
    assert CONTRACT.check_output(m, inp).code == "KIT-CB-006"
