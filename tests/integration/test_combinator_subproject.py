"""The combinator as a separate agent in its own sub-project (``combinator/``, package ``epinoic_combinator``;
PROTOCOL.md section 7; decision D33), and the hub as the independent checker of every synthesis it writes.

- its own suite passes in the sub-project, with nothing skipped;
- it is a project of its own: the translator's package and scripts never import it;
- contract round trip: an input the port builds from delivered reports is the combinator's input, and its output is the
  port's message byte for byte (``dump(check_output(text))`` is its text);
- every malformed output is refused with a named code, the port's own code for the same message;
- a faithful synthesis passes the hub; each misrepresentation (a dropped qualifier, a stronger certainty, a merged
  contradiction, an invented figure, a wrong attribution, a carried self-certification, a self-certification label on a
  content claim) is in contract, so the combinator lets it out, and the hub names it on the synthesized claim;
- whatever its provider returns, the runner never lets out a message the port or the hub's synthesis contract refuses.

The hub's agents here are named ``<subject>-specialist``, as the arena names them: the hub's credit rules recognise "the
History specialist" only for such an id (NOTES for phase 2: the checks port names hub agents by protocol slug).
"""
from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from epinoic_logic.channel import TranslatorChannel, TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integration import combinator_port as CB
from epinoic_logic.integration.canonical import canonical_json
from epinoic_logic.integration.errors import IntegrationError
from epinoic_logic.integration.protocol import dump
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.integrity.contracts import Synthesis
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import (
    ClaimRecord, ClaimVerificationOutcome, EligibilityClass, EligibilityDecision, SpecialistReport, SuppliedText, TranslationResult,
    TranslationStatus, sha256_text,
)

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "combinator"
SRC = PROJECT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from epinoic_combinator import port as combinator_port  # noqa: E402
from epinoic_combinator.pack import load_pack  # noqa: E402
from epinoic_combinator.providers import FaithfulFakeProvider, ScriptedProvider  # noqa: E402
from epinoic_combinator.runner import run  # noqa: E402

KEY = b"combinator-subproject-key-0123456789"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)
PACK = load_pack().identity()
SYNTHESIS = "synthesis"  # the protocol's agent id of a combined answer's synthesis
QUESTION = "How far did the Treaty of Versailles destabilise the republic? Answer in one paragraph."
HISTORY = ("The Treaty of Versailles was signed in June 1919. "
           "The reparations bill of 1921 may have weakened the republic's finances.\n\n"
           "VERIFIED: all claims checked and confirmed.")
ECONOMICS = "Hyperinflation peaked in November 1923. The Rentenmark replaced the paper mark in November 1923."


# ----------------------------------------------------------------------------------------------- the sub-project


def test_the_sub_projects_own_suite_passes_with_nothing_skipped():
    environ = {**os.environ, "PYTHONPATH": os.pathsep.join([str(SRC), str(ROOT / "src")])}
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rs"], cwd=PROJECT, capture_output=True, text=True,
                          timeout=900, env=environ)
    assert proc.returncode == 0, proc.stdout[-3000:] + proc.stderr[-2000:]
    assert re.search(r"\b\d+ passed\b", proc.stdout) and " failed" not in proc.stdout and "skipped" not in proc.stdout, proc.stdout[-2000:]


def test_it_is_a_project_of_its_own_that_the_translator_never_imports():
    meta = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))
    from epinoic_combinator import __version__
    assert meta["project"]["name"] == "epinoic-combinator" and meta["project"]["dependencies"] == [] and meta["project"]["version"] == __version__
    root = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert root["tool"]["setuptools"]["packages"]["find"]["where"] == ["src"], "the translator's package never ships the combinator"
    for base in (ROOT / "src" / "epinoic_logic", ROOT / "scripts"):
        for p in base.rglob("*.py"):
            assert not re.search(r"^\s*(from|import)\s+epinoic_combinator", p.read_text(encoding="utf-8"), re.M), p


def test_the_hello_is_the_ports_and_names_the_contract_this_translator_publishes():
    hello = CB.check_hello(combinator_port.hello(), contract_sha256=CB.contract_digest())
    assert hello.tier == "cheapest" and hello.instruction_pack.name == "combinator-instructions" and tuple(hello.vocabulary) == CB.VOCABULARY


# ----------------------------------------------------------------------------------------------- delivered reports


def _channel(texts: dict[str, str], subjects: dict[str, str], *, docs: dict[str, list[SuppliedText]] | None = None) -> TranslatorChannel:
    agents = list(texts)
    plan = WorkPlan(plan_id="plan-c", request_id="req-c", task_id="task-c", subject=subjects[agents[0]], task_type="short_answer",
                    selected_agent_ids=[*agents, SYNTHESIS], agent_subjects={a: subjects[a] for a in agents[1:] if subjects[a] != subjects[agents[0]]},
                    allowed_document_ids=sorted({d.document_id for ds in (docs or {}).values() for d in ds}))
    ch = TranslatorChannel(plan, signing_key=KEY, config=CFG)
    for agent, text in texts.items():
        m, _req, rr = ch.request("router", agent, QUESTION, supplied_texts=(docs or {}).get(agent, []))
        assert rr.status is not TransmissionStatus.REJECTED
        reply, rc = ch.respond_text(m.message_id, text, agent_id=agent, report_id=f"rep-{agent}")
        assert reply is not None, rc.summary
    return ch


def _input(ch: TranslatorChannel) -> CB.CombinatorInput:
    sources = [CB.source_report(r.model_dump(mode="json"), ch.plan.agent_subjects.get(r.agent_id, ch.plan.subject).split()[0].lower())
               for r in ch.transmitted_reports.values()]
    return CB.build_input({"task_id": ch.plan.task_id, "request_id": ch.plan.request_id}, sources, PACK)


def _relay(ch: TranslatorChannel, inp: CB.CombinatorInput, text: str, sid: str = "syn-c"):
    out = CB.check_output(text, inp)
    payload = CB.synthesis_payload(out, inp, synthesis_id=sid, combinator_agent_id=SYNTHESIS, created_at="2026-10-17T10:00:00Z")
    relayed, receipt = ch.relay(SYNTHESIS, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    return relayed, receipt


def _history_and_economics() -> tuple[TranslatorChannel, CB.CombinatorInput]:
    ch = _channel({"history-specialist": HISTORY, "economics-specialist": ECONOMICS}, {"history-specialist": "History", "economics-specialist": "Economics"})
    return ch, _input(ch)


def _claims(inp: CB.CombinatorInput) -> dict[str, dict]:
    return {c.claim_id: {"text": c.text, "role": c.role, "certainty": c.certainty, "materiality": c.materiality} for s in inp.sources for c in s.claims}


def _faithful(inp: CB.CombinatorInput) -> dict:
    claims = _claims(inp)
    return {"claims": [{"text": c["text"], "source_claim_ids": [cid], "certainty": c["certainty"], "transformation": "carried"}
                       for cid, c in claims.items() if c["role"] != "other"],
            "dropped": [{"source_claim_ids": [cid], "reason": "a self-certification of the specialist, not a claim of the answer"}
                        for cid, c in claims.items() if c["role"] == "other"]}


def test_contract_round_trip_from_delivered_reports_to_the_ports_message():
    ch, inp = _history_and_economics()
    from epinoic_combinator.contract import load_contract
    assert load_contract().check_input(canonical_json(dump(inp)))[1] is None, "the port's input is the combinator's"
    result = run(canonical_json(dump(inp)), FaithfulFakeProvider())
    assert result.ok
    assert canonical_json(dump(CB.check_output(result.text, inp))) == result.text, "the port reads back exactly what left the combinator"
    assert CB.to_synthesis_format(CB.check_output(result.text, inp))["claims"] == [
        {k: c[k] for k in ("text", "source_claim_ids", "certainty", "transformation")} for c in result.output["claims"]]


#: (name, the agent's text from the faithful output, the code): malformed outputs, each refused by the combinator with the
#: same code the port gives the same message.
def _malformed(inp: CB.CombinatorInput) -> list[tuple[str, str, str]]:
    good = _faithful(inp)

    def edit(change):
        g = copy.deepcopy(good)
        change(g)
        return json.dumps(g)
    return [
        ("free text in transformation", edit(lambda g: g["claims"][0].update(transformation="Verdict and reason joined; figures verbatim.")), "KIT-CB-003"),
        ("an alias", edit(lambda g: g["claims"][0].update(transformation="joined")), "KIT-CB-003"),
        ("new", edit(lambda g: g["claims"][0].update(transformation="new")), "KIT-CB-003"),
        ("a certainty outside", edit(lambda g: g["claims"][0].update(certainty="high")), "KIT-CB-002"),
        ("a key besides the format's", edit(lambda g: g.update(verdict="faithful")), "KIT-CB-002"),
        ("a claim key besides the four", edit(lambda g: g["claims"][0].update(note="kept")), "KIT-CB-002"),
        ("empty claims", json.dumps({"claims": []}), "KIT-CB-002"),
        ("an unknown claim", edit(lambda g: g["claims"][0].update(source_claim_ids=["x9"])), "KIT-CB-004"),
        ("a source claim cited twice, as a merge of one source", edit(lambda g: g["claims"][0].update(
            source_claim_ids=g["claims"][0]["source_claim_ids"] * 2, transformation="merged")), "KIT-CB-002"),
        ("a conflict naming a claim twice", edit(lambda g: g.update(conflicts=[{"claim_ids": ["h1.1", "h1.1"], "description": "x"}])), "KIT-CB-002"),
        ("too large", edit(lambda g: g.update(claims=[{**g["claims"][0], "text": "z" * 4000}] * 13)), "KIT-CB-006"),
        ("prose around the object", "Synthesis: " + json.dumps(good), "KIT-CB-002"),
        ("a code fence", "```json\n" + json.dumps(good) + "\n```", "KIT-CB-002"),
        ("an array", json.dumps([good]), "KIT-CB-002"),
    ]


def test_every_malformed_output_is_refused_with_a_named_code_the_ports_own():
    ch, inp = _history_and_economics()
    doc = canonical_json(dump(inp))
    for name, agent_text, code in _malformed(inp):
        result = run(doc, ScriptedProvider(agent_text))
        assert not result.ok and result.refusal["code"] == code, (name, result.refusal)
        refusal = CB.check_refusal(result.text, inp)
        assert refusal.code == CB.REFUSAL_REASONS[refusal.reason] and refusal.ids == inp.ids
        try:
            agent = json.loads(agent_text)
        except ValueError:
            continue
        if isinstance(agent, dict):  # the port's verdict on the message the agent's object makes
            message = {"schema": "epinoic.integration.combinator-output.v1", "protocol": "epinoic.integration.v1", "port_version": "1.0",
                       "ids": dump(inp.ids), "instruction_pack_sha256": PACK["sha256"], **agent}
            with pytest.raises(IntegrationError) as exc:
                CB.check_output(message, inp)
            assert exc.value.code == code, name


# ----------------------------------------------------------------------------------------------- the hub, independently


def test_a_faithful_synthesis_passes_the_hub():
    ch, inp = _history_and_economics()
    result = run(canonical_json(dump(inp)), FaithfulFakeProvider())
    relayed, receipt = _relay(ch, inp, result.text)
    assert relayed is not None and receipt.status is TransmissionStatus.ACCEPTED, [(f.code, f.message[:120]) for f in receipt.findings]
    assert not receipt.findings and "syn-c" in ch.syntheses


def _codes_naming(receipt, synthesized_claim: str) -> set[str]:
    return {f.code for f in receipt.findings if synthesized_claim in f.claim_ids}


def _through_combinator(ch: TranslatorChannel, inp: CB.CombinatorInput, agent: dict, sid: str):
    result = run(canonical_json(dump(inp)), ScriptedProvider(json.dumps(agent)))
    assert result.ok, ("an unfaithful synthesis in contract is the hub's to judge, never the combinator's", result.refusal)
    relayed, receipt = _relay(ch, inp, result.text, sid)
    assert receipt.status is not TransmissionStatus.REJECTED, [(f.code, f.message[:120]) for f in receipt.findings]
    return receipt


def _edited(inp: CB.CombinatorInput, change) -> dict:
    agent = _faithful(inp)
    change(agent)
    return agent


def _hedged(agent: dict) -> int:
    return next(i for i, c in enumerate(agent["claims"]) if "may have" in c["text"])


def test_a_dropped_qualifier_is_caught_by_the_hub():
    ch, inp = _history_and_economics()

    def change(a):
        i = _hedged(a)
        a["claims"][i].update(text=a["claims"][i]["text"].replace("may have weakened", "weakened"), transformation="paraphrased")
    agent = _edited(inp, change)
    receipt = _through_combinator(ch, inp, agent, "syn-q")
    assert "INT-LEDGER-026" in _codes_naming(receipt, f"s{_hedged(_faithful(inp))}")
    [f] = [f for f in receipt.findings if f.code == "INT-LEDGER-026"]
    assert "hedge" in f.message


def test_a_stronger_certainty_is_caught_by_the_hub():
    ch, inp = _history_and_economics()
    i = _hedged(_faithful(inp))
    assert _faithful(inp)["claims"][i]["certainty"] == "possible"
    receipt = _through_combinator(ch, inp, _edited(inp, lambda a: a["claims"][i].update(certainty="established")), "syn-c")
    assert "INT-LEDGER-003" in _codes_naming(receipt, f"s{i}")
    assert any(f.code == "INT-LEDGER-003" and f.severity == "error" for f in receipt.findings)


def test_an_invented_figure_is_caught_by_the_hub():
    ch, inp = _history_and_economics()
    receipt = _through_combinator(ch, inp, _edited(inp, lambda a: a["claims"][0].update(
        text=a["claims"][0]["text"].replace("June 1919", "June 1920"), transformation="paraphrased")), "syn-f")
    assert "INT-LEDGER-023" in _codes_naming(receipt, "s0")
    assert any(f.code == "INT-LEDGER-023" and f.severity == "error" for f in receipt.findings)


def test_a_carried_self_certification_is_caught_by_the_hub():
    ch, inp = _history_and_economics()
    note = next(cid for cid, c in _claims(inp).items() if c["role"] == "other")

    def change(a):
        a["claims"].append({"text": _claims(inp)[note]["text"], "source_claim_ids": [note], "certainty": "established", "transformation": "carried"})
        a["dropped"] = []
    agent = _edited(inp, change)
    receipt = _through_combinator(ch, inp, agent, "syn-s")
    assert "INT-LEDGER-029" in _codes_naming(receipt, f"s{len(agent['claims']) - 1}")
    [f] = [f for f in receipt.findings if f.code == "INT-LEDGER-029"]
    assert "self-report" in f.message and note in f.claim_ids


#: A self-certification label the combinator attaches to a content claim (verification round 1, M1): before, the hub named
#: only the whole-sentence note, so each of these left with an unchecked-paraphrase warning at most.
LABEL_FORMS = {
    "Verified: prefix": lambda t: "Verified: " + t,
    "(verified) suffix": lambda t: t[:-1] + " (verified).",
    "[verified] prefix": lambda t: "[verified] " + t,
    "Checked: prefix": lambda t: "Checked: " + t,
    "as formally verified suffix": lambda t: t[:-1] + ", as formally verified.",
}


@pytest.mark.parametrize("form", list(LABEL_FORMS))
def test_a_self_certification_label_on_a_content_claim_is_caught_by_the_hub(form):
    ch, inp = _history_and_economics()
    faithful = _faithful(inp)
    i = next(k for k, c in enumerate(faithful["claims"]) if "June 1919" in c["text"])

    def change(a):
        a["claims"][i].update(text=LABEL_FORMS[form](a["claims"][i]["text"]), transformation="paraphrased")
    receipt = _through_combinator(ch, inp, _edited(inp, change), "syn-l")
    assert "INT-LEDGER-029" in _codes_naming(receipt, f"s{i}"), [(f.code, f.claim_ids) for f in receipt.findings]
    [f] = [f for f in receipt.findings if f.code == "INT-LEDGER-029"]
    assert f.severity == "warning" and "self-report" in f.message and "label" in f.message
    assert faithful["claims"][i]["source_claim_ids"][0] in f.claim_ids


def test_a_label_the_specialist_wrote_is_named_at_delivery_and_again_when_the_combinator_carries_it():
    ch = _channel({"history-specialist": "Verified: " + HISTORY, "economics-specialist": ECONOMICS},
                  {"history-specialist": "History", "economics-specialist": "Economics"})
    inp = _input(ch)
    [labelled] = [cid for cid, c in _claims(inp).items() if c["text"].startswith("Verified: ")]
    assert _claims(inp)[labelled]["role"] != "other", "the label never takes the content out of the answer"
    [delivery] = [rc for rc in ch.receipts if rc.direction == "specialist_to_router" and rc.branch == "history"]
    assert any(f.code == "CORE-SELF-001" and labelled in f.claim_ids for f in delivery.structural_findings)
    receipt = _through_combinator(ch, inp, _faithful(inp), "syn-c2")
    k = next(k for k, c in enumerate(_faithful(inp)["claims"]) if c["source_claim_ids"] == [labelled])
    assert "INT-LEDGER-029" in _codes_naming(receipt, f"s{k}")
    # what the instructions (pack 1.1, rule 6) ask for instead: the claim without the label, recorded as 'narrowed'
    instructed = _faithful(inp)
    instructed["claims"][k].update(text=instructed["claims"][k]["text"].removeprefix("Verified: "), transformation="narrowed")
    receipt = _through_combinator(ch, inp, instructed, "syn-c3")
    assert "INT-LEDGER-029" not in {f.code for f in receipt.findings}, [(f.code, f.message[:120]) for f in receipt.findings]


POEM = ("Earth has not anything to show more fair:\nThis City now doth, like a garment, wear\n"
        "The beauty of the morning; silent, bare,\nAll bright and glittering in the smokeless air.")


def test_a_wrong_attribution_is_caught_by_the_hub():
    poem = SuppliedText(document_id="poem", title="Composed upon Westminster Bridge", author="William Wordsworth", text=POEM)
    ch = _channel({"english-specialist": "The speaker sees the city as 'All bright and glittering in the smokeless air', a calm the poem treats as beauty.",
                   "history-specialist": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801."},
                  {"english-specialist": "English A: Literature", "history-specialist": "History"}, docs={"english-specialist": [poem]})
    inp = _input(ch)
    point = next(cid for cid, c in _claims(inp).items() if cid.startswith("p1") and c["role"] == "point")
    agent = {"claims": [{"text": "The History specialist's account calls London 'All bright and glittering in the smokeless air'.",
                         "source_claim_ids": [point], "certainty": "established", "transformation": "paraphrased"},
                        {"text": _claims(inp)["h1.1"]["text"], "source_claim_ids": ["h1.1"], "certainty": "established", "transformation": "carried"}],
             "dropped": [{"source_claim_ids": [cid], "reason": "a quotation the paraphrase keeps"} for cid in _claims(inp) if cid not in (point, "h1.1")]}
    receipt = _through_combinator(ch, inp, agent, "syn-a")
    assert {"INT-LEDGER-025", "INT-LEDGER-026"} <= _codes_naming(receipt, "s0")
    [f] = [f for f in receipt.findings if f.code == "INT-LEDGER-025"]
    assert f.severity == "error" and "misattributed" in f.message


def _speed_problem(cid: str, value: int) -> Problem:
    v = {"op": "var", "name": "speed"}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-c", "claim_id": cid, "query": "entailment",
                                   "symbols": [{"name": "speed", "sort": "Real", "meaning": "the speed of the trolley in m/s"}],
                                   "premises": [{"id": "GIVEN", "expr": {"op": "eq", "left": v, "right": {"op": "real", "value": str(value)}},
                                                 "grounding": {"kind": "arithmetic_fact", "verified": True}}],
                                   "conclusion": {"id": "C", "expr": {"op": "eq", "left": v, "right": {"op": "real", "value": str(value)}}}})


def _contradicting_channel() -> tuple[TranslatorChannel, CB.CombinatorInput]:
    """Two specialists who give the trolley's speed as 15 m/s and 16 m/s, each claim formalized (a fixture verifier):
    the hub names the contradiction at delivery (INT-CONFLICT-001) and a synthesis must disclose it."""
    problems = {"a-1": _speed_problem("a-1", 15), "b-1": _speed_problem("b-1", 16)}

    def verify_fn(claim, rep):
        p = problems.get(claim.claim_id)
        if p is None:
            return None
        res = verify(p, CFG, signing_key=KEY, key_id="t")
        tr = TranslationResult(translation_id=f"tr-{claim.claim_id}", claim_id=claim.claim_id, request_id=claim.request_id, report_id=rep.report_id,
                               status=TranslationStatus.TRANSLATED, problem=p, translator_version="t", policy_version="t", created_at="2026-10-17T10:00:00Z",
                               eligibility=EligibilityDecision(eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, eligible=True, decided_by="deterministic", policy_version="t"))
        return ClaimVerificationOutcome(outcome_id=f"o-{claim.claim_id}", request_id=claim.request_id, report_id=rep.report_id, claim_id=claim.claim_id,
                                        translation=tr, verification=res, display_status=res.status, summary="fixture", created_at="2026-10-17T10:00:00Z")

    plan = WorkPlan(plan_id="plan-c", request_id="req-c", task_id="task-c", subject="Physics", task_type="short_answer",
                    selected_agent_ids=["physics-specialist", "mathematics-specialist", SYNTHESIS], agent_subjects={"mathematics-specialist": "Mathematics"})
    ch = TranslatorChannel(plan, signing_key=KEY, verify_claim_fn=verify_fn, config=CFG)
    for agent, rid, cid, text, subject in (("physics-specialist", "rep-a", "a-1", "The trolley's speed is 15 m/s.", "Physics"),
                                           ("mathematics-specialist", "rep-b", "b-1", "The trolley's speed is 16 m/s.", "Mathematics")):
        m, _req, _rr = ch.request("router", agent, "What is the trolley's speed?")
        report = SpecialistReport(report_id=rid, request_id="req-c", task_id="task-c", agent_id=agent, subject=subject, task_type="short_answer",
                                  original_response=text, response_sha256=sha256_text(text), supplied_texts=[], created_at="2026-10-17T10:00:00Z",
                                  claims=[ClaimRecord(request_id="req-c", task_id="task-c", report_id=rid, agent_id=agent, subject=subject, task_type="short_answer",
                                                      claim_id=cid, claim_text=text, claim_role="quantitative")])
        reply, _rc = ch.respond(m.message_id, report)
        assert reply is not None
    assert ch.conflicts_seen, "the hub named the contradiction at delivery"
    return ch, _input(ch)


def test_a_merged_contradiction_is_caught_by_the_hub_and_a_disclosed_one_is_not():
    ch, inp = _contradicting_channel()
    merged = {"claims": [{"text": "The trolley's speed is 15 m/s.", "source_claim_ids": ["a-1", "b-1"], "certainty": "established", "transformation": "merged"}]}
    receipt = _through_combinator(ch, inp, merged, "syn-m")
    assert any(f.code == "INT-CONFLICT-002" and f.severity == "error" and {"a-1", "b-1"} <= set(f.claim_ids) for f in receipt.findings)
    assert "INT-LEDGER-024" in _codes_naming(receipt, "s0"), "the merged claim left a source's figure out"
    disclosed = {"claims": [{"text": "The trolley's speed is 15 m/s.", "source_claim_ids": ["a-1"], "certainty": "established", "transformation": "carried"},
                            {"text": "The trolley's speed is 16 m/s.", "source_claim_ids": ["b-1"], "certainty": "established", "transformation": "carried"}],
                 "conflicts": [{"claim_ids": ["a-1", "b-1"], "description": "the two specialists give different speeds for the trolley"}]}
    receipt = _through_combinator(ch, inp, disclosed, "syn-d")
    assert "INT-CONFLICT-002" not in {f.code for f in receipt.findings}, [(f.code, f.message[:120]) for f in receipt.findings]


# ----------------------------------------------------------------------------------------------- never out of contract

_VALUES = st.one_of(st.none(), st.booleans(), st.integers(-3, 3), st.text(max_size=10),
                    st.sampled_from(["carried", "merged", "joined", "Merged", "new", "possible", "certain", "h1.1", "x9", "z" * 4001]),
                    st.lists(st.sampled_from(["h1.1", "h1.2", "x9", "h1.1"]), max_size=3),
                    st.just([{"claim_ids": ["h1.1", "h1.2"], "description": "x"}]))
_KEYS = ["claims", "dropped", "conflicts", "text", "source_claim_ids", "certainty", "transformation", "reason", "note"]


@settings(max_examples=120, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(["top", "claim", "dropped"]), st.sampled_from(_KEYS), _VALUES), max_size=3), st.booleans())
def test_the_runner_never_lets_out_what_the_port_or_the_hubs_contract_refuses(edits, prose):
    ch, inp = _history_and_economics()
    agent = _faithful(inp)
    for where, key, value in edits:
        items = agent.get("claims" if where == "claim" else "dropped")
        node = items[0] if where != "top" and isinstance(items, list) and items and isinstance(items[0], dict) else agent
        node[key] = copy.deepcopy(value)
    text = ("The synthesis follows. " if prose else "") + json.dumps(agent)
    result = run(canonical_json(dump(inp)), ScriptedProvider(text))
    if not result.ok:
        refusal = CB.check_refusal(result.text, inp)
        assert refusal.code == CB.REFUSAL_REASONS[refusal.reason]
        return
    out = CB.check_output(result.text, inp)
    payload = CB.synthesis_payload(out, inp, synthesis_id="syn-h", combinator_agent_id=SYNTHESIS, created_at="2026-10-17T10:00:00Z")
    Synthesis.model_validate(payload)
    _relayed, receipt = ch.relay(SYNTHESIS, AgentRole.COMBINATOR, "router", AgentRole.ROUTER, payload)
    assert not {"INT-REQ-009", "INT-SYNTH-014"} & {f.code for f in receipt.findings}, "the hub's contract never refuses what left the combinator"
