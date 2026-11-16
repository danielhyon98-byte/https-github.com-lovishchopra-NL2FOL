"""Round-10 clearance (integrated round c3), handoff pass: two ledger rules the combinator and integration fixers handed to the
integrity owner.

* Rule framing-content, announced items (combinator handoff H1; communication-fidelity minor, the same class as results-audit bug
  3): the ll-t16 synthesis carried the specialist's "To test a direction, answer these from the adverts themselves: 1. ..." and
  dropped the four questions that sentence announces, so the student was told to answer questions the answer no longer held.
  With the roles the round's hub gave the questions (interpretation, supporting) no rule named it; the delivery named it only
  because the English parser now roles such questions material. Now a carried claim that announces questions ("answer these",
  "these questions", "ask yourself", a count of questions) or items or steps ("Steps for this week:", "try these", a count of
  steps, a text ending with a colon), while the synthesis carries none of the questions or items it announces that are not roled
  ``other``, names each one left out (INT-LEDGER-019, warning, naming the announcing claim). A narrowed list is not an empty one;
  a question back with no announcing lead and a question roled ``other`` (a note) draw nothing.
* Rule orphaned-quotation (integration handoff H1): a synthesized claim that is a source's quotation and nothing else, whose every
  quoting source claim the synthesis left out, is named INT-LEDGER-017 with its own reason, read by the combinator port's reader
  (``integration.combinator_port.orphaned_quotations``): the student-facing text leaves it out (the port's composition), or the
  student reads it on its own (a text that joins every claim).

The recorded material is in ``data/c3_handoff_ledger.json`` (copied verbatim from the combinator's test data) and
``tests/integration/data/c3_orphaned_quotation.json`` (the integration fixer's, copied verbatim from the round).
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from epinoic_logic.integrity import Synthesis
from epinoic_logic.integrity import ledger as L
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport

from ..core_hostile import SHAPES, one, sweep

DATA = json.loads((Path(__file__).parent / "data" / "c3_handoff_ledger.json").read_text(encoding="utf-8"))
ORPHAN = json.loads((Path(__file__).resolve().parents[1] / "integration" / "data" / "c3_orphaned_quotation.json").read_text(encoding="utf-8"))
LL = DATA["ll-t16"]
QUESTIONS = ("p4-s02", "p4-s04", "p4-s06", "p4-s07")
LEAD = "p4-point"
RECORDED_REASON = "a question or practice prompt to the student, a note rather than a claim of the answer"
REQ, TASK = "req-c3-handoff", "task-c3-handoff"


def _report(item: dict, claims: list[dict], report_id: str = "rep-1") -> SpecialistReport:
    base = dict(request_id=REQ, task_id=TASK, report_id=report_id, agent_id=item["agent_id"], subject=item["subject"], task_type=item["task_type"])
    records = [ClaimRecord(**base, claim_id=c["claim_id"], claim_text=c["text"], claim_role=c["role"], materiality=c["materiality"],
                           certainty=c.get("certainty", "established")) for c in claims]
    response = item["response_text"]
    return SpecialistReport(report_id=report_id, request_id=REQ, task_id=TASK, agent_id=item["agent_id"], subject=item["subject"],
                            task_type=item["task_type"], original_response=response, response_sha256=hashlib.sha256(response.encode("utf-8")).hexdigest(),
                            created_at="2026-11-15T09:00:00Z", claims=records)


def _synthesis(claims: list[dict], dropped: list[dict], report_ids=("rep-1",), text=None) -> Synthesis:
    """A synthesis of the given claims (each carried word for word) with a ledger entry per claim and per drop."""
    syn = [{"claim_id": f"s{i + 1}", "text": c["text"], "source_claim_ids": list(c["source_claim_ids"]), "certainty": c.get("certainty", "established"),
            "transformation": c.get("transformation", "carried")} for i, c in enumerate(claims)]
    ledger = [{"source_claim_ids": list(c["source_claim_ids"]), "transformation": c["transformation"], "synthesized_claim_id": c["claim_id"]} for c in syn]
    ledger += [{"source_claim_ids": list(d["source_claim_ids"]), "transformation": "dropped", "reason": d["reason"]} for d in dropped]
    body = text if text is not None else " ".join(c["text"] for c in syn)
    return Synthesis.model_validate({"synthesis_id": "syn-1", "request_id": REQ, "task_id": TASK, "combinator_agent_id": "synthesis",
                                     "source_report_ids": list(report_ids), "claims": syn, "ledger": ledger, "text": body,
                                     "text_sha256": hashlib.sha256(body.encode("utf-8")).hexdigest(), "created_at": "2026-11-15T10:00:00Z"})


def _ll_ledger(*, kept=(), roles=None):
    """The hub's ledger on ll-t16 as the round's hub delivered it (the four questions roled interpretation, supporting) and the
    round's recorded synthesis, keeping the questions ``kept`` (each carried after the claim before it, as rule 6 asks)."""
    claims = copy.deepcopy(LL["claims"])
    for c in claims:
        if roles and c["claim_id"] in roles:
            c["role"], c["materiality"] = roles[c["claim_id"]]
    syn = copy.deepcopy(LL["synthesis"])
    order = [c["claim_id"] for c in claims]
    for q in kept:
        syn["dropped"] = [d for d in syn["dropped"] if q not in d["source_claim_ids"]]
        text = next(c["text"] for c in claims if c["claim_id"] == q)
        syn["claims"].append({"text": text, "source_claim_ids": [q], "certainty": "probable", "transformation": "carried"})
    syn["claims"].sort(key=lambda c: min(order.index(s) for s in c["source_claim_ids"]))
    return L.check_synthesis_ledger([_report(LL, claims)], _synthesis(syn["claims"], syn["dropped"]),
                                    extra_texts=(LL["supplied_texts"][0]["text"],),
                                    document_texts={LL["supplied_texts"][0]["document_id"]: LL["supplied_texts"][0]["text"]})


def _announced(findings) -> list:
    return [f for f in findings if f.code == "INT-LEDGER-019" and "rule framing-content" in f.message and "announces" in f.message]


# ------------------------------------------------------------------------------- rule framing-content, announced items

def test_the_recorded_ll_t16_synthesis_that_drops_every_announced_question_names_each_one():
    findings = _ll_ledger()
    for q in QUESTIONS:
        named = [f for f in findings if f.code == "INT-LEDGER-019" and q in f.claim_ids]
        assert len(named) == 1, (q, [(f.code, f.claim_ids[:3], f.message[:160]) for f in findings])
        f = named[0]
        assert f.severity == "warning" and LEAD in f.message and "rule framing-content" in f.message and RECORDED_REASON in f.message
    assert sorted(c for f in _announced(findings) for c in f.claim_ids) == sorted(QUESTIONS)
    # the numbered statements the synthesis carries ('2. ...', '3. ...') and the quotations between them are no item named
    assert not [f for f in _announced(findings) if set(f.claim_ids) & {"p4-s03", "p4-s05", "p4-q03", "p4-q04", "p4-q05"}]


def test_the_synthesis_rule_6_asks_for_names_no_announced_question():
    assert not _announced(_ll_ledger(kept=QUESTIONS))
    assert not [f for f in _ll_ledger(kept=QUESTIONS) if set(f.claim_ids) & set(QUESTIONS)]


def test_a_narrowed_list_is_not_an_empty_one():
    findings = _ll_ledger(kept=("p4-s04",))
    assert not _announced(findings), [(f.claim_ids, f.message[:160]) for f in _announced(findings)]


def test_announced_questions_roled_other_are_notes_and_draw_nothing():
    findings = _ll_ledger(roles={q: ("other", "supporting") for q in QUESTIONS})
    assert not _announced(findings)


def test_material_questions_are_left_to_the_materiality_rule():
    """As the English parser delivers them since the round-10 clearance (judgement, material): the materiality rule names each
    with the recorded reason, once; the new case adds nothing on them."""
    findings = _ll_ledger(roles={q: ("judgement", "material") for q in QUESTIONS})
    assert not _announced(findings)
    for q in QUESTIONS:
        assert [f for f in findings if f.code == "INT-LEDGER-019" and q in f.claim_ids and RECORDED_REASON in f.message]


def _small(claims, carried, dropped_reason="a note to the student, not a claim of the answer"):
    item = {"agent_id": "psychology-specialist", "subject": "Psychology", "task_type": "short_answer", "response_text": " ".join(t for _i, t, _r in claims)}
    rows = [{"claim_id": cid, "text": t, "role": role, "materiality": "supporting" if role != "point" else "material"} for cid, t, role in claims]
    syn = [{"text": t, "source_claim_ids": [cid]} for cid, t, _r in claims if cid in carried]
    dropped = [{"source_claim_ids": [cid], "reason": dropped_reason} for cid, _t, _r in claims if cid not in carried]
    return L.check_synthesis_ledger([_report(item, rows)], _synthesis(syn, dropped))


def test_a_question_back_with_no_announcing_lead_draws_nothing_new():
    claims = [("g1.1", "The Treaty of Versailles imposed reparations on Germany.", "point"),
              ("g2.1", "Would you like me to say more about the reparations?", "interpretation")]
    assert not _announced(_small(claims, {"g1.1"}))


@pytest.mark.parametrize("lead", ["Steps for this week:", "Try these before the test:", "Work through these three steps in order:",
                                  "Ask yourself these questions about your design."])
def test_announced_steps_or_questions_of_another_branch_are_named(lead):
    claims = [("g3.1", lead, "point"), ("g3.2", "1. Name your independent variable.", "analysis"), ("g3.3", "2. Name your dependent variable.", "analysis"),
              ("g3.4", "Which group is your control?", "analysis")]
    findings = _small(claims, {"g3.1"})
    named = sorted(c for f in _announced(findings) for c in f.claim_ids)
    expected = ["g3.4"] if "questions" in lead else ["g3.2", "g3.3", "g3.4"]
    assert named == expected, [(f.claim_ids, f.message[:160]) for f in findings]
    # one item carried: nothing
    assert not _announced(_small(claims, {"g3.1", "g3.2" if "questions" not in lead else "g3.4"}))
    # the lead not carried: nothing (the student is not told to answer anything)
    assert not _announced(_small(claims, {"g3.2"}))


def test_items_are_read_in_the_announcing_claims_block_only():
    claims = [("g3.1", "Try these:", "point"), ("g3.2", "1. Name your variable.", "analysis"), ("g4.1", "Which group is your control?", "analysis")]
    findings = _small(claims, {"g3.1"})
    assert sorted(c for f in _announced(findings) for c in f.claim_ids) == ["g3.2"]


def test_the_round_9_ps_t15_synthesis_draws_no_new_finding():
    """Its guiding questions are roled other under headings roled other: notes the combinator is told to leave out."""
    ps = DATA["ps-t15"]
    syn = ps["synthesis"]
    findings = L.check_synthesis_ledger([_report(ps, ps["claims"])], _synthesis(syn["claims"], syn["dropped"]))
    assert not _announced(findings), [(f.claim_ids, f.message[:160]) for f in _announced(findings)]


# ------------------------------------------------------------------------------- rule orphaned-quotation

QUEEN = '"The queen is somewhere in the dark"'


def _orphan_case(task: str, *, text_with_the_quotation: bool):
    """The recorded synthesis of ``task`` over its delivered claims (the 'Next step' note roled other, as the parsers deliver it),
    with the student-facing text the port composes (the orphan left out) or one that joins every claim."""
    item = ORPHAN[task]
    claims = copy.deepcopy(item["delivered_claims"])
    for c in claims:
        if c["text"].startswith("Next step"):
            c.update(claim_id="p2-s01", role="other", materiality="supporting")
    syn = copy.deepcopy(item["synthesis"])
    dropped = [{**d, "source_claim_ids": ["p2-s01" if x == "p2-point" else x for x in d["source_claim_ids"]]} for d in syn["dropped"]]
    texts = [c["text"] for c in syn["claims"]]
    held = L.quotations_held_verbatim(texts)
    keep = [t for i, t in enumerate(texts) if i not in held and (text_with_the_quotation or t != QUEEN)]
    rep = _report(item, claims)
    s = _synthesis(syn["claims"], dropped, text=" ".join(keep))
    poem = item["supplied_texts"][0]
    return s, L.check_synthesis_ledger([rep], s, extra_texts=(poem["text"],), document_texts={poem["document_id"]: poem["text"]})


@pytest.mark.parametrize("task", ("lit-t16", "x10"))
def test_the_orphaned_quotation_left_out_of_the_text_is_named_with_its_own_reason(task):
    s, findings = _orphan_case(task, text_with_the_quotation=False)
    [orphan] = [c.claim_id for c in s.claims if c.text == QUEEN]
    named = [f for f in findings if f.code == "INT-LEDGER-017" and orphan in f.claim_ids]
    assert len(named) == 1 and named[0].severity == "warning", [(f.code, f.claim_ids[:4], f.message[:200]) for f in findings]
    f = named[0]
    assert "rule orphaned-quotation" in f.message and "leaves it out" in f.message and "p2-s01" in f.claim_ids
    # the generic presence message no longer lists it, and nothing else is named on the text
    assert not [x for x in findings if x.code == "INT-LEDGER-017" and "do not appear" in x.message]
    assert not [x for x in findings if x.code in ("INT-LEDGER-031", "INT-LEDGER-023")]


@pytest.mark.parametrize("task", ("lit-t16", "x10"))
def test_the_orphaned_quotation_the_student_reads_on_its_own_is_named(task):
    s, findings = _orphan_case(task, text_with_the_quotation=True)
    [orphan] = [c.claim_id for c in s.claims if c.text == QUEEN]
    named = [f for f in findings if f.code == "INT-LEDGER-017" and orphan in f.claim_ids]
    assert len(named) == 1 and "rule orphaned-quotation" in named[0].message and "on its own" in named[0].message, \
        [(f.code, f.claim_ids[:4], f.message[:200]) for f in findings]


def test_controls_a_quotation_a_carried_claim_uses_or_no_claim_quotes_is_no_orphan():
    item = {"agent_id": "english-a-literature-specialist", "subject": "English A: Literature", "task_type": "short_answer", "response_text": "x"}
    q = '"one two three four"'
    # the specialist's own bare quotation: no other source claim quotes it
    claims = [{"claim_id": "p1-q01", "text": q, "role": "evidence", "materiality": "supporting"},
              {"claim_id": "p1-point", "text": "A point of the answer.", "role": "point", "materiality": "material"}]
    s = _synthesis([{"text": q, "source_claim_ids": ["p1-q01"]}, {"text": "A point of the answer.", "source_claim_ids": ["p1-point"]}], [])
    assert not [f for f in L.check_synthesis_ledger([_report(item, claims)], s) if "orphaned-quotation" in f.message]
    # a quotation a carried claim quotes
    claims2 = claims + [{"claim_id": "p1-s01", "text": f"The line {q} carries the point.", "role": "analysis", "materiality": "supporting"}]
    s2 = _synthesis([{"text": q, "source_claim_ids": ["p1-q01"]}, {"text": "A point of the answer.", "source_claim_ids": ["p1-point"]},
                     {"text": f"The line {q} carries the point.", "source_claim_ids": ["p1-s01"]}], [])
    assert not [f for f in L.check_synthesis_ledger([_report(item, claims2)], s2) if "orphaned-quotation" in f.message]


# ------------------------------------------------------------------------------- hostile input

@pytest.mark.parametrize("shape", SHAPES)
def test_the_new_ledger_readers_are_linear_on_hostile_input(shape):
    """Each standard hostile input as an announcing claim, as its items and as a quotation, through the ledger's readers."""
    item = {"agent_id": "psychology-specialist", "subject": "Psychology", "task_type": "short_answer", "response_text": "x"}

    def entries(text):
        lead = ("answer these: " + text)[:4000]
        body = text[:3990]
        claims = [{"claim_id": "g1.1", "text": lead, "role": "point", "materiality": "material"},
                  {"claim_id": "g1.2", "text": body + "?", "role": "analysis", "materiality": "supporting"},
                  {"claim_id": "g1.3", "text": "- " + body[:3990], "role": "analysis", "materiality": "supporting"},
                  {"claim_id": "g1.4", "text": '"' + body[:3990] + '"', "role": "evidence", "materiality": "supporting"}]
        rep = _report(item, claims)
        s = _synthesis([{"text": lead, "source_claim_ids": ["g1.1"]}, {"text": claims[3]["text"], "source_claim_ids": ["g1.4"]}],
                       [{"source_claim_ids": ["g1.2", "g1.3"], "reason": "practice prompts to the student"}])
        yield "announced items", lambda: L._announced_items(list(rep.claims), {"g1.1", "g1.4"})
        yield "framing-content", lambda: L.framing_content_findings(s, [rep])
        yield "orphaned quotations", lambda: L._orphaned_quotation_findings(s, [rep], "")
        yield "announcement", lambda: L._announcement(text)
        # the from-memory label read in its wording's own clause (handoff pass): one wording after the run, and a run of wordings
        yield "memory label (one clause)", lambda: L.labels_report_figures_from_memory(text[:3980] + " from memory")
        yield "memory label (wordings)", lambda: L.labels_report_figures_from_memory(("from memory would " + text)[:4000])
        yield "memory clause", lambda: L.memory_label_vetoed(text + " from memory", len(text) + 1, len(text) + 12)

    assert not sweep(entries, texts=one(shape)), shape
