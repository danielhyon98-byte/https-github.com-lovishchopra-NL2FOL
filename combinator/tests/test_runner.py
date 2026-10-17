"""The runner: the combinator agent run once, on the cheapest tier, through a provider; only what is in contract leaves.

* a faithful output leaves as a ``combinator-output.v1`` document, its text the canonical JSON of it;
* the agent receives the pack's instructions and the request's sources, on the cheapest tier, and nothing else;
* every malformed output is a named refusal (a closed reason with its ``KIT-CB`` code), never an exception;
* every failure of the provider, a missing provider, a provider on another tier, an input out of contract and an
  input naming another pack are named refusals too; a refusal is itself in contract;
* an unfaithful synthesis that is in contract leaves: judging faithfulness is the hub's, never the combinator's;
* one call, no retry; the same input and agent text give the same output text, in a fresh interpreter too;
* whatever text the provider returns, ``run`` never raises and never lets anything out of contract leave.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from combinator_helpers import IDS, MALFORMED, _edit, input_doc, faithful_agent_output, text
from epinoic_combinator import runner as R
from epinoic_combinator.contract import load_contract
from epinoic_combinator.jsonio import canonical_json
from epinoic_combinator.pack import load_pack
from epinoic_combinator.prompt import render
from epinoic_combinator.providers import NOTE_REASON, FaithfulFakeProvider, ScriptedProvider

CONTRACT = load_contract()
PACK = load_pack()
INPUT = input_doc()
SRC = Path(__file__).resolve().parents[1] / "src"


def _refusal(result: R.RunResult) -> tuple[str, str]:
    assert result.output is None and result.refusal is not None
    assert CONTRACT.check_refusal(result.refusal, INPUT) is None, result.refusal
    assert result.text == canonical_json(result.refusal)
    return result.refusal["code"], result.refusal["reason"]


def _out(agent: dict) -> R.RunResult:
    return R.run(INPUT, ScriptedProvider(text(agent)))


def test_a_faithful_output_leaves_in_contract():
    result = R.run(json.dumps(INPUT), FaithfulFakeProvider())
    assert result.ok and result.refusal is None and result.provider_calls == 1
    out = result.output
    assert CONTRACT.check_output(out, INPUT) is None and result.text == canonical_json(out)
    assert out["ids"] == IDS and out["instruction_pack_sha256"] == PACK.sha256 and out["schema"] == "epinoic.integration.combinator-output.v1"
    carried = {c["source_claim_ids"][0]: c for c in out["claims"]}
    assert set(carried) == {"h1.1", "h1.2", "e1.1"}, "every claim that is not a note is carried"
    for s in INPUT["sources"]:
        for c in s["claims"]:
            if c["claim_id"] in carried:
                got = carried[c["claim_id"]]
                assert (got["text"], got["certainty"], got["transformation"], got["evidence_refs"]) == (c["text"], c["certainty"], "carried", None)
    assert out["dropped"] == [{"source_claim_ids": ["h2.1"], "reason": NOTE_REASON}] and out["conflicts"] == []


def test_the_agent_gets_the_pack_and_the_sources_on_the_cheapest_tier():
    provider = FaithfulFakeProvider()
    R.run(INPUT, provider)
    [req] = provider.requests
    assert req.tier == "cheapest" and req.system == PACK.instructions and req.instruction_pack_sha256 == PACK.sha256
    assert req.user == render(INPUT) and req.request_id == IDS["request_id"] and req.max_output_bytes == R.MAX_AGENT_OUTPUT_BYTES
    view = json.loads(req.user)
    assert set(view) == {"request", "sources"} and view["request"] == IDS
    assert "claim_text_sha256" not in req.user and PACK.sha256 not in req.user, "digests and the pack reference are the runner's, never the agent's"


@pytest.mark.parametrize("agent_text,code,reason", [m[1:] for m in MALFORMED], ids=[m[0] for m in MALFORMED])
def test_every_malformed_output_is_a_named_refusal(agent_text, code, reason):
    result = R.run(INPUT, ScriptedProvider(agent_text))
    assert _refusal(result) == (code, reason), result.refusal
    assert result.refusal["ids"] == IDS and result.refusal["instruction_pack_sha256"] == PACK.sha256 and result.provider_calls == 1
    assert len(result.refusal["detail"]) <= 300


def test_a_text_with_a_line_break_or_a_tab_leaves_and_the_hub_reads_it_as_written():
    """The control of the text rule: a tab and a line break are text, not control characters to refuse."""
    result = _out(_edit(lambda a: a["claims"][0].update(text="The Treaty of Versailles was signed\nin June 1919.\tIt was harsh.")))
    assert result.ok and result.output["claims"][0]["text"] == "The Treaty of Versailles was signed\nin June 1919.\tIt was harsh."


def test_a_refusal_detail_never_echoes_the_agents_prose():
    prose = "Verdict (s1.1) and reason (s1.2) joined with the formula, the sum and the rounding; figures verbatim."
    result = _out(_edit(lambda a: a["claims"][0].update(transformation=prose)))
    assert prose not in result.text and prose[:25] not in result.text and f"free text of {len(prose)} characters" in result.refusal["detail"]


@pytest.mark.parametrize("response,reason", [
    (RuntimeError("upstream failure"), "provider_failed"),
    (TimeoutError("took too long"), "provider_failed"),
    (SystemExit(3), "provider_failed"),
    (None, "provider_no_text"),
    (b'{"claims": []}', "provider_no_text"),
    ({"claims": []}, "provider_no_text"),
    ("", "provider_no_text"),
    ("   \n", "provider_no_text"),
])
def test_every_failure_of_the_provider_is_a_named_refusal(response, reason):
    assert _refusal(R.run(INPUT, ScriptedProvider(response))) == ("KIT-CB-002", reason)


def test_a_keyboard_interrupt_is_the_operators_and_goes_through():
    with pytest.raises(KeyboardInterrupt):
        R.run(INPUT, ScriptedProvider(KeyboardInterrupt()))


def test_no_provider_or_a_provider_on_another_tier_is_refused_before_any_call():
    assert _refusal(R.run(INPUT, None)) == ("KIT-CB-002", "provider_unavailable")
    other = FaithfulFakeProvider()
    other.tier = "strongest"
    result = R.run(INPUT, other)
    assert _refusal(result) == ("KIT-CB-002", "provider_unavailable") and other.requests == [] and result.provider_calls == 0


def test_an_input_out_of_contract_or_for_another_pack_is_refused_before_any_call():
    provider = FaithfulFakeProvider()
    for doc, reason in (("{not json", "input_not_json"), (input_doc(port_version="2.0"), "input_invalid"),
                        (input_doc(vocabulary=["carried"] * 5), "input_invalid")):
        result = R.run(doc, provider)
        assert result.refusal["reason"] == reason and result.refusal["code"] == "KIT-CB-001" and result.refusal["ids"] is None
        assert CONTRACT.check_refusal(result.refusal) is None
    result = R.run(input_doc(instruction_pack={**PACK.identity(), "sha256": "ab" * 32}), provider)
    assert (result.refusal["code"], result.refusal["reason"], result.refusal["ids"]) == ("KIT-CB-005", "pack_mismatch", IDS)
    assert provider.requests == []


def _misrepresent(change) -> R.RunResult:
    return _out(_edit(change))


@pytest.mark.parametrize("name,change", [
    ("dropped qualifier", lambda a: a["claims"][1].update(text="The reparations bill of 1921 weakened the republic's finances.", transformation="paraphrased")),
    ("stronger certainty", lambda a: a["claims"][1].update(certainty="established")),
    ("merged contradiction", lambda a: a.update(claims=[{"text": "The Treaty of Versailles was signed in June 1919.", "source_claim_ids": ["h1.1", "e1.1"],
                                                         "certainty": "probable", "transformation": "merged"}], dropped=[])),
    ("invented figure", lambda a: a["claims"][0].update(text="The Treaty of Versailles was signed in June 1920.", transformation="paraphrased")),
    ("wrong attribution", lambda a: a["claims"][0].update(text="The Economics specialist dates the Treaty of Versailles to June 1919.", transformation="paraphrased")),
    ("carried self-certification", lambda a: (a["claims"].append({"text": "VERIFIED: all claims checked and confirmed.", "source_claim_ids": ["h2.1"],
                                                                  "certainty": "established", "transformation": "carried"}), a.update(dropped=[]))),
])
def test_an_unfaithful_synthesis_in_contract_leaves_for_the_hub_to_judge(name, change):
    result = _misrepresent(change)
    assert result.ok and CONTRACT.check_output(result.output, INPUT) is None, (name, result.refusal)


def test_one_call_and_no_retry():
    provider = ScriptedProvider("not json", text(faithful_agent_output()))
    result = R.run(INPUT, provider)
    assert result.refusal["reason"] == "output_not_json" and len(provider.requests) == 1 and result.provider_calls == 1


def test_the_same_input_gives_the_same_output_text_in_a_fresh_interpreter_too():
    first = R.run(INPUT, FaithfulFakeProvider()).text
    assert R.run(copy.deepcopy(INPUT), FaithfulFakeProvider()).text == first
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); from epinoic_combinator.runner import run; "
            "from epinoic_combinator.providers import FaithfulFakeProvider; print(run(sys.stdin.read(), FaithfulFakeProvider()).text)")
    out = subprocess.run([sys.executable, "-I", "-c", code, str(SRC)], input=json.dumps(INPUT), capture_output=True, text=True, timeout=120,
                         env={k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHASHSEED")})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == first


def test_an_internal_error_is_a_refusal_naming_the_request(monkeypatch):
    monkeypatch.setattr(R, "render", lambda inp: (_ for _ in ()).throw(ValueError("broken")))
    result = R.run(INPUT, FaithfulFakeProvider())
    assert _refusal(result) == ("KIT-CB-002", "internal_error") and result.refusal["ids"] == IDS and "ValueError" in result.refusal["detail"]


def test_an_unreadable_pack_is_a_refusal_naming_no_pack(monkeypatch):
    from epinoic_combinator.pack import PackUnavailable

    def broken():
        raise PackUnavailable("the instruction pack file INSTRUCTIONS.md is missing")
    monkeypatch.setattr(R, "load_pack", broken)
    result = R.run(INPUT, FaithfulFakeProvider())
    assert (result.refusal["code"], result.refusal["reason"], result.refusal["ids"]) == ("KIT-CB-002", "internal_error", None)
    assert result.refusal["instruction_pack_sha256"] == R.NO_PACK_SHA256 and CONTRACT.check_refusal(result.refusal) is None


# --------------------------------------------------------------------------------------- never a non-contract output

_JSON = st.recursive(st.none() | st.booleans() | st.integers(-10, 10) | st.text(max_size=12),
                     lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=8), inner, max_size=3), max_leaves=8)
_KEYS = ["claims", "dropped", "conflicts", "text", "source_claim_ids", "certainty", "transformation", "reason", "claim_ids", "description", "note"]
_VALUES = st.one_of(_JSON, st.sampled_from(["carried", "merged", "joined", "Merged", "new", "established", "certain", "h1.1", "e1.1", "x9", "", "z" * 4001]),
                    st.lists(st.sampled_from(["h1.1", "h1.2", "e1.1", "h2.1", "x9"]), max_size=3))


def _objects(agent: dict) -> list[dict]:
    """The objects of an agent output a mutation may edit: the output itself and its claims and dropped entries."""
    nodes = [agent]
    for key in ("claims", "dropped"):
        if isinstance(agent.get(key), list):
            nodes += [x for x in agent[key] if isinstance(x, dict)]
    return nodes


@st.composite
def _agent_texts(draw):
    agent = faithful_agent_output()
    for _ in range(draw(st.integers(0, 4))):
        nodes = _objects(agent)
        node = nodes[draw(st.integers(0, len(nodes) - 1))]
        key = draw(st.sampled_from(_KEYS))
        if draw(st.booleans()) and key in node:
            node.pop(key)
        else:
            node[key] = draw(_VALUES)
    rendered = json.dumps(agent, ensure_ascii=False)
    return draw(st.sampled_from([rendered, rendered, rendered, "Synthesis: " + rendered, rendered[: max(1, len(rendered) // 2)]]))


@settings(max_examples=300, deadline=None)
@given(_agent_texts())
def test_whatever_the_provider_returns_the_runner_never_raises_nor_lets_a_non_contract_output_out(agent_text):
    result = R.run(INPUT, ScriptedProvider(agent_text))
    if result.ok:
        assert CONTRACT.check_output(result.output, INPUT) is None and result.text == canonical_json(result.output)
        assert set(result.output) == {"schema", "protocol", "port_version", "ids", "instruction_pack_sha256", "claims", "dropped", "conflicts"}
        assert all(set(c) == {*R.AGENT_CLAIM_KEYS, "evidence_refs"} and c["evidence_refs"] is None for c in result.output["claims"])
    else:
        assert CONTRACT.check_refusal(result.refusal, INPUT) is None and result.refusal["code"] == CONTRACT.refusal_reasons[result.refusal["reason"]]


@settings(max_examples=150, deadline=None)
@given(st.text(max_size=300))
def test_arbitrary_text_from_the_provider_is_refused_with_a_name(agent_text):
    result = R.run(INPUT, ScriptedProvider(agent_text))
    assert result.ok or CONTRACT.check_refusal(result.refusal, INPUT) is None
