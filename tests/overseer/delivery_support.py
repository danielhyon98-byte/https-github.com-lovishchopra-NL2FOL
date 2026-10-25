"""Shared helpers of the delivery-policy tests (``docs/DELIVERY.md``): a fake monotonic clock, fixture translations and
fidelity reviews (no model, no network), scripted overseer providers, and one task driven through an audited hub with
a delivery session open from the first answer to the decision.

Two kinds of task are used:

* a Physics calculation (``QUESTION`` states the relation, so every premise is validated by the task record): each
  quantitative claim is translated by a fixture translation and verified by the engine, and a fixture reviewer makes the
  fidelity review. With the default fixtures the formal path completes.
* an essay-style answer (Philosophy, ``ESSAY_QUESTION``) of ``n`` material points: no point is eligible for the formal
  check, so the formal path never completes and the overseer agents decide. A point may be replaced by a quantitative
  claim the engine refutes (``REFUTED_TEXT``).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, ProviderInfo, SpecialistReport, sha256_text
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers import ProviderResponse
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

from .conftest import CFG, KEY, int_problem, make_auditor, outcome_for
from .test_protocol_validate import acc, ptr

#: The task states the relation as a given, so the task record validates the distance and the relation.
QUESTION = "A car travels 120 km in 8 hours. Use speed = d / 8. Find its average speed in km/h."
PHYSICS = dict(request_id="req-dlv", task_id="task-dlv", subject="Physics", task_type="calculation")
ESSAY_QUESTION = "Give separate reasons why careful reading matters, one sentence each."
ESSAY = dict(request_id="req-ess", task_id="task-ess", subject="Philosophy", task_type="short_answer")
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth", "eleventh", "twelfth", "thirteenth",
            "fourteenth", "fifteenth", "sixteenth", "seventeenth", "eighteenth", "nineteenth", "twentieth", "twenty-first", "twenty-second")
#: A quantitative claim whose encoding the engine refutes (x = 5 does not entail x > 9: COUNTEREXAMPLE).
REFUTED_TEXT = "The value 5 is more than 9."
CREATED = "2026-10-20T00:00:00Z"


class FakeClock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = float(start)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += float(seconds)


# ============================================================================================ the Physics task
def speed_translation(claim_id: str, *, distance: int = 120, speed: int = 15, request_id: str = PHYSICS["request_id"], ambiguous: bool = False,
                      unsupported: Optional[str] = None, broken: bool = False) -> str:
    """A fixture translation of "the speed is ``speed`` km/h": the distance and ``speed = d / 8`` as given (the task
    states both). ``broken`` gives an IR with an operator outside the allowlist (INVALID); ``unsupported`` a translator
    that declines; ``ambiguous`` a translator that flags the reading as ambiguous."""
    v = lambda n: {"op": "var", "name": n}  # noqa: E731
    r = lambda x: {"op": "real", "value": str(x)}  # noqa: E731
    conclusion = {"op": "eq", "left": v("speed"), "right": r(speed)}
    if broken:
        conclusion = {"op": "eval", "left": v("speed"), "right": r(speed)}
    problem = {"ir_version": "1.0", "problem_id": f"p-{claim_id}", "request_id": request_id, "claim_id": claim_id, "query": "entailment",
               "symbols": [{"name": "d", "sort": "Real"}, {"name": "speed", "sort": "Real"}],
               "premises": [{"id": "D", "expr": {"op": "eq", "left": v("d"), "right": r(distance)}, "label": f"distance {distance} km",
                             "grounding": {"kind": "arithmetic_fact"}},
                            {"id": "SPEED", "expr": {"op": "eq", "left": v("speed"), "right": {"op": "div", "left": v("d"), "right": r(8)}},
                             "grounding": {"kind": "arithmetic_fact"}}],
               "conclusion": {"id": "C", "expr": conclusion, "label": f"the speed is {speed} km/h"}}
    flags = [{"code": "unit_unclear", "message": "the unit of the figure may be read two ways", "alternatives": ["km/h", "m/s"]}] if ambiguous else []
    return json.dumps({"problem": None if unsupported else problem,
                       "interpretation": {"reading": "speed is distance over time", "glossary": [], "ambiguity_flags": flags},
                       "ambiguous": ambiguous, "unsupported_reason": unsupported})


def physics_report(agent: str, report_id: str, claims: Sequence[tuple[str, str]] = (("p1.1", "The speed is 15 km/h."),), *, prefix: str = "p1",
                   ids: Mapping[str, str] = PHYSICS) -> SpecialistReport:
    """A Physics answer: one supporting evidence claim (the task's figures) and the given quantitative material claims."""
    evidence = "A car travels 120 km in 8 hours."
    text = " ".join([evidence, *(t for _, t in claims)])
    recs = [ClaimRecord(**ids, report_id=report_id, agent_id=agent, claim_id=f"{prefix}.0", claim_text=evidence, claim_role="evidence", materiality="supporting")]
    recs += [ClaimRecord(**ids, report_id=report_id, agent_id=agent, claim_id=cid, claim_text=t, claim_role="quantitative", proposed_claim_kind="arithmetic",
                         supporting_claim_ids=[f"{prefix}.0"]) for cid, t in claims]
    return SpecialistReport(**ids, report_id=report_id, agent_id=agent, original_response=text, response_sha256=sha256_text(text), claims=recs, created_at=CREATED)


class Verifier:
    """The channel's claim verifier for the Physics task: per claim, a fixture translation (``translations``, default the
    faithful one), the engine, and a fixture fidelity review (``reviews``: verdict per claim, ``None`` for no reviewer).
    ``delays`` moves the fake clock by that many seconds per call (by claim id, or ``"*"`` for every claim); ``raises``
    names claims whose verification fails internally and ``none`` claims for which no outcome is produced."""

    def __init__(self, clock: Optional[FakeClock] = None, *, delays: Optional[Mapping[str, float]] = None, translations: Optional[Mapping[str, str]] = None,
                 reviews: Optional[Mapping[str, Optional[str]]] = None, reviewer: bool = True, raises: Sequence[str] = (), none: Sequence[str] = (),
                 config: SolverConfig = CFG, outcomes: Optional[Mapping[str, Callable[[Any, Any], Any]]] = None) -> None:
        self.clock = clock
        self.delays = dict(delays or {})
        self.translations = dict(translations or {})
        self.reviews = dict(reviews or {})
        self.reviewer = reviewer
        self.raises = set(raises)
        self.none = set(none)
        self.config = config
        self.outcomes = dict(outcomes or {})
        self.calls: list[tuple[str, str, float]] = []

    def __call__(self, claim, report, task=None):
        start = self.clock() if self.clock is not None else 0.0
        self.calls.append((report.report_id, claim.claim_id, start))
        delay = self.delays.get(claim.claim_id, self.delays.get("*", 0.0))
        if self.clock is not None and delay:
            self.clock.advance(delay)
        if claim.claim_id in self.raises:
            raise RuntimeError("the verifier failed")
        if claim.claim_id in self.none:
            return None
        if claim.claim_id in self.outcomes:
            return self.outcomes[claim.claim_id](claim, report)
        if claim.claim_role != "quantitative":
            return None
        translation = self.translations.get(claim.claim_id) or speed_translation(claim.claim_id, request_id=claim.request_id)
        translator = Translator(FixtureTranslationProvider({claim.claim_id: translation}), config=self.config)
        reviewer = None
        verdict = self.reviews.get(claim.claim_id, "faithful")
        if self.reviewer and verdict is not None:
            issues = [] if verdict == "faithful" else ["the encoding does not say what the claim says"]
            reviewer = SemanticReviewer(FixtureReviewProvider({claim.claim_id: {"verdict": verdict, "issues": issues}}))
        return verify_claim(claim, report, translator, reviewer=reviewer, config=self.config, signing_key=KEY, key_id="hub", task=task)


def refuted_outcome(claim, report):
    """A genuine outcome the engine refutes: x = 5 (given) does not entail x > 9 (COUNTEREXAMPLE, signed)."""
    return outcome_for(claim, report, int_problem(claim.claim_id, "x", 5, op="gt", bound=9, request_id=claim.request_id))


# ============================================================================================ the essay task
def essay_report(agent: str, report_id: str, n: int, *, prefix: str, variant: str = "attention", refuted: Sequence[int] = (),
                 ids: Mapping[str, str] = ESSAY) -> SpecialistReport:
    """An answer of ``n`` material points (claim ids ``{prefix}.1`` ...); the points at the 1-based positions in
    ``refuted`` are the quantitative claim the engine refutes instead."""
    claims = []
    for i in range(1, n + 1):
        if i in refuted:
            claims.append(dict(claim_id=f"{prefix}.{i}", claim_text=REFUTED_TEXT, claim_role="quantitative", proposed_claim_kind="arithmetic"))
        else:
            claims.append(dict(claim_id=f"{prefix}.{i}", claim_text=f"Careful reading matters for the {ORDINALS[i - 1]} reason, which concerns {variant}.",
                               claim_role="point"))
    text = " ".join(c["claim_text"] for c in claims)
    return SpecialistReport(**ids, report_id=report_id, agent_id=agent, original_response=text, response_sha256=sha256_text(text), created_at=CREATED,
                            claims=[ClaimRecord(**ids, report_id=report_id, agent_id=agent, materiality="material", **c) for c in claims])


# ============================================================================================ scripted overseer agents
class ScriptedOverseer:
    """An overseer completion provider whose reply is computed from the dossier it receives (test code reading data,
    never a model). ``clock``/``delay`` move the fake clock per call (a slow agent)."""

    name = "scripted"

    def __init__(self, reply: Callable[[dict], Any], *, clock: Optional[FakeClock] = None, delay: float = 0.0) -> None:
        self.reply = reply
        self.clock = clock
        self.delay = delay
        self.calls: list[str] = []

    def complete(self, system: str, user: str, *, prompt_version: str) -> ProviderResponse:
        lines = user.split("\n")
        assert lines[0] == "<<<DATA dossier>>>" and lines[-1] == "<<<END dossier>>>"
        d = json.loads("\n".join(lines[1:-1]))
        self.calls.append(d["agent_id"])
        if self.clock is not None and self.delay:
            self.clock.advance(self.delay)
        out = self.reply(d)
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return ProviderResponse(raw_text=text, info=ProviderInfo(provider_name=self.name, prompt_version=prompt_version, temperature=0.0))


def verdict(d: dict, accusations=(), engine_statements=(), **over) -> dict:
    """A well-formed verdict on the dossier ``d``: every transfer reviewed, the given accusations and engine statements."""
    v = {"contract": d["verdict_contract"], "pack": dict(d["pack"]), "verdict_id": f"v-{d['agent_id']}", "agent_id": d["agent_id"],
         "task_id": d["task"]["task_id"], "dossier_sha256": d["dossier_sha256"], "lens": d["lens"],
         "transfers_reviewed": [t["message_id"] for t in d["transfers"] if t["message_id"]], "accusations": list(accusations),
         "engine_statements": list(engine_statements), "notes": ""}
    v.update(over)
    return v


def silent(d: dict) -> dict:
    return verdict(d)


def response_of(d: dict, report_id: str) -> dict:
    return next(t for t in d["transfers"] if t["kind"] == "response" and t["payload"].get("report_id") == report_id)


def contest(*targets: tuple[str, str]) -> Callable[[dict], dict]:
    """A verdict that reviews every transfer and accuses each ``(report_id, claim_id)`` with a kind no check decides
    (``other``): an unresolved accusation, which leaves the claim contested (never confirmed accurate)."""
    def reply(d: dict) -> dict:
        accusations = []
        for n, (rid, cid) in enumerate(targets, 1):
            t = response_of(d, rid)
            accusations.append(acc(f"a{n}", "other", [{"pointer": ptr(d, "claim", cid) + "/claim_text"}], statement="This point is doubtful.",
                                   message_ids=[t["message_id"]], claim_ids=[cid], report_ids=[rid]))
        return verdict(d, accusations)
    return reply


def results_in(d: dict) -> dict:
    return dict(d.get("results") or {})


def state_results(*, wrong: bool) -> Callable[[dict], dict]:
    """A verdict that states the status of every signed result in the dossier: correctly, or (``wrong``) contradicting
    the stored result (an engine statement a signed result refutes)."""
    def reply(d: dict) -> dict:
        stmts = []
        for rid, r in sorted(results_in(d).items()):
            status = r["status"]
            if wrong:
                status = "COUNTEREXAMPLE" if status != "COUNTEREXAMPLE" else "ENTAILED"
            stmts.append({"result_id": rid, "asserted_status": status, "pointer": f"/results/{rid}/status"})
        return verdict(d, engine_statements=stmts)
    return reply


class Agents:
    """A provider factory for the policy's overseer pool: one :class:`ScriptedOverseer` per instance, replying with
    ``replies[agent_id]`` (or ``reply``), each moving the fake clock by ``delay`` seconds per call."""

    def __init__(self, clock: Optional[FakeClock] = None, reply: Callable[[dict], Any] = silent, *, delay: float = 0.0,
                 replies: Optional[Mapping[str, Callable[[dict], Any]]] = None) -> None:
        self.clock, self.reply, self.delay = clock, reply, delay
        self.replies = dict(replies or {})
        self.made: dict[str, ScriptedOverseer] = {}

    def __call__(self, agent_id: str) -> ScriptedOverseer:
        p = ScriptedOverseer(self.replies.get(agent_id, self.reply), clock=self.clock, delay=self.delay)
        self.made[agent_id] = p
        return p

    @property
    def calls(self) -> list[str]:
        return [c for p in self.made.values() for c in p.calls]


def assert_honest(decision) -> None:
    """The label of every decision says only what was established; the delivered payload carries the receipt's label."""
    from epinoic_logic.overseer.delivery_policy import is_fallback_label_honest
    rec = decision.receipt
    assert rec.mode == decision.mode and rec.label == decision.label and rec.delivered is decision.delivered
    assert is_fallback_label_honest(decision.mode, decision.label), decision.label
    if decision.mode != "formally_checked":
        low = decision.label.lower()
        assert "not formally checked" in low and "not verified" in low and not low.startswith("formally checked")
        assert "verified by" not in low and "is verified" not in low
    if decision.delivered:
        assert decision.answer is not None and decision.answer.mode == rec.mode and decision.answer.label == rec.label
        assert decision.message_id == rec.delivered_message_id == decision.answer.message_id
    else:
        assert decision.answer is None and rec.delivered_message_id is None and rec.delivered_payload_sha256 is None


# ============================================================================================ one task through the hub
@dataclass
class Run:
    hub: RouterHub
    plan: WorkPlan
    session: Any
    decision: Any
    mids: list[str]
    receipts: dict[str, Any] = field(default_factory=dict)
    messages: dict[str, Any] = field(default_factory=dict)

    @property
    def receipt(self):
        return self.decision.receipt

    @property
    def keyring(self):
        return self.hub.auditor.keyring

    def message_of(self, agent: str) -> str:
        return next(m for m, msg in self.messages.items() if msg is not None and msg.sender_agent_id == agent)

    def close(self) -> None:
        self.hub.close()


def run_task(policy, answers: Sequence[tuple[str, SpecialistReport]], *, verify: Optional[Callable] = None, question: str = QUESTION,
             ids: Mapping[str, str] = PHYSICS, decide: bool = True, between: Optional[Callable[[int], None]] = None,
             config: SolverConfig = CFG, plan: Optional[WorkPlan] = None, supplied: Sequence[Any] = ()) -> Run:
    """Dispatch ``question`` (with the ``supplied`` texts) to every agent of ``answers``, open the delivery session when
    the first answer arrives, install the deadline-bound verifier, receive each answer (``between(i)`` runs before
    answer ``i``) and decide. The hub's channels run under ``config`` (the configuration the auditor replays under)."""
    hub = RouterHub(signing_key=KEY, config=config, auditor=make_auditor())
    agents = list(dict.fromkeys(a for a, _ in answers))
    if plan is None:
        plan = WorkPlan(plan_id=f"plan-{ids['task_id']}", selected_agent_ids=agents, **ids)
    ch = hub.open_task(plan)
    if verify is not None:
        ch.verify_claim_fn = verify
    mids = []
    for agent, _ in answers:
        m, _req, rq = hub.dispatch(plan.task_id, agent, question, list(supplied))
        assert m is not None, rq.findings
        mids.append(m.message_id)
    session = policy.start(hub, plan.task_id)
    session.install()
    run = Run(hub=hub, plan=plan, session=session, decision=None, mids=mids)
    for i, ((agent, rep), mid) in enumerate(zip(answers, mids)):
        if between is not None:
            between(i)
        msg, rc = hub.receive(plan.task_id, mid, rep)
        run.receipts[rc.message_id] = rc
        run.messages[rc.message_id] = msg
    if decide:
        run.decision = session.decide(request_message_ids=mids, receipts=run.receipts)
    return run
