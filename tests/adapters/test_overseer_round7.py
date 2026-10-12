"""Regression tests for the round-7 overseer findings assigned to the generic parser, the shared pre-segmentation helpers
(adapters/markdown.py), the English parser and its structural checks (results-audit, communication-fidelity,
adversarial-live and translation-fidelity reports):

* claim ids of the generic branch are qualified by the agent (``g4.2@economics-specialist``) and the STEM branches'
  ids carry the branch's letter (``s1.2`` Physics, ``m1.2`` Mathematics, over the same claims), so two specialists of
  one peer group (Economics with Business, Physics with Mathematics) never hold the same id: no INT-REQ-016 at
  delivery, and the recorded p7a and p7b group syntheses carry no INT-LEDGER-014, no INT-LEDGER-002 and no
  collision-driven INT-LEDGER-023;
* worked answers are segmented line by line: part labels ("(a) [2]", "(i) [2 marks]", "Part (a) — find — 3 marks") and
  mark annotations ("[1]", "[1 spare]", "M1", "(A1)") are no claims, each line of working and each result is a claim of
  its own, an equation chain continued on lines opening with "=" is one claim, and a sentence ends at '."' and '.”';
* the answer of each part is material: a line led by "Answer:", "Result:", "Results:" or "Total:", a line credited with
  an accuracy mark, else the last line of the part's working (with its parallel rows), else the part's opening claim; a
  bare value ("(-1, 3)") opening a part always; so the recorded syntheses that drop requested answers get INT-LEDGER-002;
* notes ("Note:", "Note on ...:", "Next step:", "Confidence:", and "Limit:" on the generic branch), questions and headings
  ("Measure: ...", "2024 (no tax)", "Diagram 1: ...") are roled ``other``; a "Note:" sentence is a note on the History
  and English branches too and stays out of the channel's word count, so hi-t13 and ess-t13 are within their bounds;
* support links follow the specialist's stated direction: a consequence ("Consumers therefore pay ...") or a judgement
  rests on the claims before it and supports nothing, a caveat ("However, ...") is no support, an "Assumption:" line is
  never a derived point, two labelled answers opening a paragraph are coordinate, and no support cycle forms;
* lit-t13's marking feedback: the task heading, the restated task, the provisional marks line and the confidence label
  are notes, inline list numbers ("Fix it: 1. Choose ...") open their item instead of being cut off, and the judgement and
  the fixes are material;
* ES-SRC-008 binds each quotation to the phrase that governs it in its own clause: the poem's lines after "... the
  History specialist's "...":" in lit-p7c are not credited to the colleague, while lit-p7cb's "The History specialist calls
  the street "two streets"" still is.

The texts are the genuine round-7 answers (and the round-7 adversarial variants named above) with the recorded syntheses
(tests/adapters/data/r7_specialists.json). The recorded syntheses cite the claim ids the parser delivered when they were
written; the data file keeps the text of each cited claim instead, and :func:`cite` resolves it to the ids delivered now."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.english_specialist.parser import parse_response as parse_english, split_sentences as english_sentences
from epinoic_logic.adapters.english_specialist.structural import structural_checks
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub, default_registry
from epinoic_logic.branches.generic_parser import GenericTextParser, agent_claim_tag, split_sentences
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.channel.request_parser import count_answer_words
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import AgentRole, LedgerEntry, Synthesis, SynthesizedClaim, WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

DATA = json.loads((Path(__file__).parent / "data" / "r7_specialists.json").read_text(encoding="utf-8"))
ITEMS, SYNTHESES = DATA["items"], DATA["syntheses"]
KEY = b"round7-english-fixer-key-0123456789ab"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
GENERIC = ("ec-p7a", "bm-p7a", "ph-p7b", "maa-p7b", "ph-t13", "ge-t13", "maa-t13", "bi-t13", "ess-t13", "cs-t13", "sp-t13", "bm-t13", "ch-t13", "ec-t13")
#: A claim that is nothing but a part label with its mark allocation.
LABEL_ONLY = re.compile(r"^\s*(?:part\s+)?(?:\(\s*(?:[a-h]|[ivx]{1,4}|\d{1,2})\s*\)|(?:[a-h]|[ivx]{1,4})\)|\d{1,2}[.)])\s*(?:[—–-]\s*\w+\s*[—–-]\s*)?"
                        r"(?:\[\s*\d+(?:\s*(?:marks?|spare))?\s*\]|\d+\s*marks?)?\s*$", re.IGNORECASE)


def docs(item: dict) -> list[SuppliedText]:
    return [SuppliedText(**d) for d in item.get("supplied_texts", [])]


def parse(tid: str, extra: tuple[SuppliedText, ...] = ()) -> SpecialistReport:
    it = ITEMS[tid]
    branch, _ = default_registry().for_subject(it["subject"])
    return branch.parser().parse_response(it["response_text"], request_id=f"req-{tid}", task_id=tid, report_id=f"rep-{tid}-0", subject=it["subject"],
                                          task_type=it["task_type"], supplied_texts=[*docs(it), *extra], agent_id=it["agent_id"])


def claim(report: SpecialistReport, start: str):
    found = [c for c in report.claims if " ".join(c.claim_text.split()).startswith(start)]
    assert found, (report.report_id, start, [c.claim_text[:60] for c in report.claims])
    return found[0]


_FURNITURE = re.compile(r"\s*\[\s*\d+(?:\s*(?:marks?|spare))?\s*\]|\s*\((?:[MARN]\d|AG)\)|\s{2,}(?:[MARN]\d|AG)\b|^\s*(?:\(?[a-h]\)|\(?[ivx]{1,4}\)|\d{1,2}[.)])(?:\s*[a-h]\))?\s+",
                        re.MULTILINE)


def norm(text: str) -> str:
    """``text`` without part labels and mark annotations, whitespace collapsed: what a recorded claim and the claims the
    current parser cuts from it have in common."""
    return " ".join(_FURNITURE.sub("", text).split())


def cite(claims: list[dict], texts: list[str]) -> list[str]:
    """The ids delivered now for the claims a recorded synthesis cited: every claim whose text lies inside a cited claim's
    text (the new segmentation splits worked blocks) or holds it."""
    out: list[str] = []
    for t in texts:
        nt = norm(t)
        for c in claims:
            nc = norm(c["claim_text"])
            if c["claim_id"] not in out and (nc in nt or nt in nc):
                out.append(c["claim_id"])
    return out


def codes(receipt) -> set[str]:
    return {f.code for f in receipt.findings} | {f.code for f in receipt.structural_findings}


def exchange(first: str, second: str, group: str):
    """A peer exchange as the arena runs it: ``first`` delivered and relayed to ``second``'s agent, ``second`` delivered
    with the relayed report supplied as peer:<first>. Returns (channel, replies by task, receipts by task)."""
    a, b = ITEMS[first], ITEMS[second]
    allowed = sorted({d["document_id"] for it in (a, b) for d in it.get("supplied_texts", [])} | {f"peer:{first}"})
    plan = WorkPlan(plan_id=f"plan-{group}", request_id=f"req-{group}", task_id=group, subject=b["subject"], task_type=b["task_type"],
                    selected_agent_ids=[a["agent_id"], b["agent_id"], "dummy-combinator"], allowed_document_ids=allowed,
                    agent_subjects={a["agent_id"]: a["subject"]} if a["subject"] != b["subject"] else {},
                    agent_task_types={a["agent_id"]: a["task_type"]} if a["task_type"] != b["task_type"] else {})
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(plan)
    m1, _, _ = hub.dispatch(group, a["agent_id"], a["question"], docs(a))
    r1, rc1 = hub.receive(group, m1.message_id, a["response_text"], agent_id=a["agent_id"], report_id=f"rep-{first}-0")
    fwd, _ = ch.relay("router", AgentRole.ROUTER, b["agent_id"], AgentRole.SPECIALIST, SpecialistReport.model_validate(r1.payload), in_reply_to=r1.message_id)
    peer = SuppliedText(document_id=f"peer:{first}", title="peer report relayed through the hub", author=a["agent_id"], text=fwd.payload["original_response"])
    m2, _, _ = hub.dispatch(group, b["agent_id"], b["question"], [*docs(b), peer])
    r2, rc2 = hub.receive(group, m2.message_id, b["response_text"], agent_id=b["agent_id"], report_id=f"rep-{second}-0")
    return ch, {first: r1, second: r2}, {first: rc1, second: rc2}


def single(tid: str):
    it = ITEMS[tid]
    plan = WorkPlan(plan_id=f"plan-{tid}", request_id=f"req-{tid}", task_id=tid, subject=it["subject"], task_type=it["task_type"],
                    selected_agent_ids=[it["agent_id"], "dummy-combinator"], allowed_document_ids=[d["document_id"] for d in it.get("supplied_texts", [])])
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(plan)
    m, _, _ = hub.dispatch(tid, it["agent_id"], it["question"], docs(it))
    reply, receipt = hub.receive(tid, m.message_id, it["response_text"], agent_id=it["agent_id"], report_id=f"rep-{tid}-0")
    return ch, reply, receipt


def recorded_synthesis(ch, replies: dict, order: tuple[str, ...]) -> Synthesis:
    """The recorded synthesis of ``order``'s reports, built as the harness builds a group synthesis (one claim list per
    member, prefixed by task id), each cited claim resolved to the id delivered now."""
    claims, ledger = [], []
    for tid in order:
        syn, delivered = SYNTHESES[tid], replies[tid].payload["claims"]
        prefix = f"{tid}-" if len(order) > 1 else ""
        for i, c in enumerate(syn["claims"]):
            claims.append(SynthesizedClaim(claim_id=f"{prefix}s{i}", text=c["text"], certainty=c["certainty"], source_claim_ids=cite(delivered, c["source_texts"]),
                                           transformation=c["transformation"]))
        for d in syn["dropped"]:
            ids = cite(delivered, d["source_texts"])
            if ids:
                ledger.append(LedgerEntry(source_claim_ids=ids, transformation="dropped", reason=d["reason"]))
    body = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn-r7", request_id=ch.plan.request_id, task_id=ch.plan.task_id, combinator_agent_id="dummy-combinator",
                     source_report_ids=[replies[t].payload["report_id"] for t in order], claims=claims, ledger=ledger, text=body, text_sha256=sha256_text(body),
                     created_at="2026-10-11T15:00:00Z")


def deliver_synthesis(ch, replies: dict, order: tuple[str, ...]):
    _relayed, receipt = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, recorded_synthesis(ch, replies, order))
    return receipt


# ------------------------------------------------------------ results-audit / communication-fidelity / adversarial-live: claim ids


def generic_parse(tid: str) -> SpecialistReport:
    """``tid``'s answer read by the generic parser (the parser every subject had in round 7)."""
    it = ITEMS[tid]
    return GenericTextParser(it["agent_id"]).parse_response(it["response_text"], request_id=f"req-{tid}", task_id=tid, report_id=f"rep-{tid}-0",
                                                            subject=it["subject"], task_type=it["task_type"], supplied_texts=docs(it), agent_id=it["agent_id"])


def assert_same_claims(report: SpecialistReport, reference: SpecialistReport) -> None:
    """``report`` holds ``reference``'s claims, claim by claim and in order, under its own ids: the same texts, roles,
    proposed kinds, materiality and quotations (source references), and supports that name the same claims."""
    assert len(report.claims) == len(reference.claims), (report.report_id, len(report.claims), len(reference.claims))
    to_new = {r.claim_id: c.claim_id for c, r in zip(report.claims, reference.claims)}
    for c, r in zip(report.claims, reference.claims):
        assert (c.claim_text, c.claim_role, c.proposed_claim_kind, c.materiality) == (r.claim_text, r.claim_role, r.proposed_claim_kind, r.materiality), (c.claim_id, r.claim_id)
        assert [(x.document_id, x.excerpt) for x in c.source_refs] == [(x.document_id, x.excerpt) for x in r.source_refs], c.claim_id
        assert c.supporting_claim_ids == [to_new[x] for x in r.supporting_claim_ids], (c.claim_id, c.supporting_claim_ids, r.supporting_claim_ids)


def test_claim_ids_are_qualified_by_the_agent_or_lettered_by_the_stem_branch_and_two_reports_share_none():
    """Generic-branch ids are qualified by the agent; Physics and Mathematics answers go through the STEM branches, whose
    ids carry the branch's letter (``s1.2`` sciences, ``m1.2`` mathematics), so the two reports of each peer group still
    share no id, and the STEM reports hold exactly the claims the generic parser delivered for the same answers."""
    reports = {t: parse(t) for t in ("ec-p7a", "bm-p7a", "ph-p7b", "maa-p7b")}
    for tid in ("ec-p7a", "bm-p7a"):
        tag = agent_claim_tag(ITEMS[tid]["agent_id"])
        assert tag == ITEMS[tid]["agent_id"]
        assert all(re.fullmatch(rf"g\d+\.\d+@{re.escape(tag)}", c.claim_id) for c in reports[tid].claims), [c.claim_id for c in reports[tid].claims]
    for tid, letter in (("ph-p7b", "s"), ("maa-p7b", "m")):
        assert all(re.fullmatch(rf"{letter}\d+\.\d+", c.claim_id) for c in reports[tid].claims), [c.claim_id for c in reports[tid].claims]
        assert_same_claims(reports[tid], generic_parse(tid))
    for tid, rep in reports.items():
        assert [c.claim_id for c in parse(tid).claims] == [c.claim_id for c in rep.claims]  # stable: the ledger can cite them
    for x, y in (("ec-p7a", "bm-p7a"), ("ph-p7b", "maa-p7b")):
        assert not {c.claim_id for c in reports[x].claims} & {c.claim_id for c in reports[y].claims}
    # an agent id that is not a plain token still yields a distinct, bounded tag
    odd = agent_claim_tag("physics specialist (HL) — mock " * 3)
    assert len(odd) <= 49 and odd != agent_claim_tag("physics specialist (SL) — mock " * 3)


@pytest.mark.parametrize("first,second,group", [("ec-p7a", "bm-p7a", "p7a"), ("ph-p7b", "maa-p7b", "p7b")])
def test_peer_exchange_raises_no_id_collision_and_the_recorded_group_synthesis_is_accounted_for(first, second, group):
    ch, replies, receipts = exchange(first, second, group)
    for tid, rc in receipts.items():
        assert replies[tid] is not None and "INT-REQ-016" not in codes(rc), (tid, sorted(codes(rc)))
    assert not {c["claim_id"] for c in replies[first].payload["claims"]} & {c["claim_id"] for c in replies[second].payload["claims"]}
    rr = deliver_synthesis(ch, replies, (first, second))
    found = codes(rr)
    assert "INT-LEDGER-014" not in found and "INT-LEDGER-002" not in found, sorted(found)
    # no figure is reported missing from the cited sources because a colliding source was set aside
    assert not [f for f in rr.findings if f.code == "INT-LEDGER-023" and "occur in none of its cited sources" in f.message]
    assert not [f for f in rr.findings if "shared with another report" in f.message]


def test_bm_p7a_quotation_of_the_economics_specialist_is_not_merged_with_its_own_working():
    ch, replies, receipts = exchange("ec-p7a", "bm-p7a", "p7a")
    bm = SpecialistReport.model_validate(replies["bm-p7a"].payload)
    quoted = claim(bm, 'Volume: the Economics specialist gives "Percentage change in quantity demanded')
    assert quoted.claim_text.endswith('−12.50%".') and "13.125" not in quoted.claim_text
    assert claim(bm, "Fizzbrook's volume = 15 million litres").claim_role == "quantitative"
    # its own results are no longer read as the colleague's misreported figures
    assert not [f for f in receipts["bm-p7a"].findings if f.code == "INT-REQ-014"]
    two = claim(bm, 'The Economics specialist calculates "PED = −12.50 ÷ 18.75 = −0.67"')
    assert two.claim_text.endswith('is less than 1."') and claim(bm, "On that elasticity, passing the whole tax on")


# ------------------------------------------------------------ communication-fidelity / adversarial-live: segmentation of worked answers


@pytest.mark.parametrize("tid", GENERIC)
def test_part_labels_and_mark_annotations_are_never_claims(tid):
    rep = parse(tid)
    for c in rep.claims:
        assert not LABEL_ONLY.fullmatch(c.claim_text), (tid, c.claim_text)
        assert not re.search(r"\[\s*\d+(?:\s*(?:marks?|spare))?\s*\]\s*$|\s{2,}[MA]\d$|\((?:M|A)\d\)", c.claim_text), (tid, c.claim_text)
    assert not CorePack._support_cycles(rep)
    ids = {c.claim_id for c in rep.claims}
    assert all(s in ids for c in rep.claims for s in c.supporting_claim_ids)


def test_ph_p7b_results_are_the_material_claims_and_the_headings_are_gone():
    rep = parse("ph-p7b")
    rows = [c for c in rep.claims if re.match(r"t = \d+ h: ", c.claim_text)]
    assert len(rows) == 7 and all(c.materiality == "material" for c in rows)
    for start in ("T½ = 8.0 h", "λ = 0.693/8.0 h = 0.087 h⁻¹", "32 h is 4 half-lives, so C = 1600"):
        assert claim(rep, start).materiality == "material", start
    formula = claim(rep, "Corrected count rate = measured count rate − background.")
    assert formula.materiality == "supporting" and formula.claim_id in rows[-1].supporting_claim_ids
    assert claim(rep, "Assumption: the background of 20 counts").claim_text.endswith("of the measured value.")  # the rows are claims of their own
    assert not any(c.claim_text.startswith("(") and "]" in c.claim_text[:8] for c in rep.claims)


def test_each_line_of_working_is_a_claim_and_an_equation_chain_is_one():
    ec = parse("ec-p7a")
    result = claim(ec, "Result: PED = −0.67.")
    assert result.claim_text == "Result: PED = −0.67." and result.materiality == "material" and result.claim_role == "point"
    lines = [claim(ec, s) for s in ("Percentage change in quantity demanded = (105 − 120)", "Percentage change in price = (1.90 − 1.60)", "PED = −12.50 ÷ 18.75 = −0.67")]
    assert all(c.claim_role == "quantitative" and c.materiality == "supporting" and c.claim_id in result.supporting_claim_ids for c in lines)
    maa = parse("maa-t13")
    distance = claim(maa, "Distance travelled = 8 m")
    assert distance.claim_text == "Distance travelled = 8 m" and distance.materiality == "material"
    assert claim(maa, "distance = 4 − (−4) = 8").claim_id in distance.supporting_claim_ids
    ge = parse("ge-t13")
    chain = claim(ge, "1990: (31 − 11) ÷ 10")
    assert chain.claim_text == "1990: (31 − 11) ÷ 10\n= 20 ÷ 10\n= 2.0%" and chain.claim_role == "quantitative"  # working, never a note
    assert claim(ge, "2020: (16 − 7) ÷ 10").claim_role == "quantitative"


def test_a_sentence_ends_after_a_closing_quotation_mark():
    assert split_sentences('It states: "Demand is price inelastic, because its absolute value, 0.67, is less than 1." On that elasticity, prices rise.') == [
        'It states: "Demand is price inelastic, because its absolute value, 0.67, is less than 1."', "On that elasticity, prices rise."]
    maa = parse("maa-p7b")
    note_on = claim(maa, "Note on the Physics specialist’s uncertainty:")
    assert note_on.claim_text.endswith("values).”") and note_on.claim_role == "other"
    assert claim(maa, "Checking only t = 0 and t = 8").claim_role != "other"


# ------------------------------------------------------------ results-audit: answers to request parts are material


def test_answers_to_request_parts_are_material():
    sp = parse("sp-t13")
    for start in ("F: «sin pesticidas químicos»", "F: «se perdió casi la mitad de la cosecha»", "supera", "Lucía Ferrer, una maestra jubilada.",
                  "En 2020 reunió a doce vecinos"):
        c = claim(sp, start)
        assert c.materiality == "material" and c.claim_role == "point", start
    why = claim(sp, "Why: third paragraph;")
    assert why.materiality == "supporting" and why.claim_id in claim(sp, "F: «sin pesticidas químicos»").supporting_claim_ids
    assert claim(parse("bi-t13"), "Percentage change = (final − initial)").materiality == "material"
    assert claim(parse("ge-t13"), "Answer: the rate of natural increase was 2.0%").materiality == "material"
    assert claim(parse("ess-t13"), "Percentage decrease = (9.6 − 3.8)").materiality == "material"
    maa = parse("maa-t13")
    assert claim(maa, "a = 0 m s⁻²").materiality == "material" and claim(maa, "t = 0 or t = 2").materiality == "material"
    cs = parse("cs-t13")
    bare = claim(cs, "(-1, 3)")
    assert bare.materiality == "material" and bare.claim_role == "point" and claim(cs, "The loop ends when low (2)").claim_id in bare.supporting_claim_ids
    assert claim(parse("bm-t13"), "As a percentage of current output: 1,200 ÷ 4,200").materiality == "material"  # part (a) has a material claim
    maa_p = parse("maa-p7b")
    for start in ("k = (ln 2)/8 h⁻¹", "The half-life is 8 h", "Gradient = −(ln 2)/8 h⁻¹"):  # lines credited with an accuracy mark
        assert claim(maa_p, start).materiality == "material", start
    assert claim(maa_p, "Hence, using the k from (a).").claim_role != "judgement"  # the question's command term, not a conclusion


@pytest.mark.parametrize("tid,dropped", [("bi-t13", ["Percentage change = (final − initial)"]), ("ge-t13", ["Answer: the rate of natural increase"]),
                                         ("sp-t13", ["F: «sin pesticidas químicos»", "F: «se perdió casi la mitad", "supera"])])
def test_a_recorded_synthesis_that_drops_a_requested_answer_is_named(tid, dropped):
    ch, reply, receipt = single(tid)
    rr = deliver_synthesis(ch, {tid: reply}, (tid,))
    named = {cid for f in rr.findings if f.code == "INT-LEDGER-002" for cid in f.claim_ids}
    report = SpecialistReport.model_validate(reply.payload)
    for start in dropped:
        assert claim(report, start).claim_id in named, (tid, start, sorted(named))


# ------------------------------------------------------------ notes, questions and headings


def test_note_leads_are_notes_on_every_branch_and_outside_the_word_count():
    for sentence in ("Note: I am answering from memory.", "Note on the Physics specialist’s uncertainty: it writes “T½ = 8.0 h”.",
                     "Next step: trace find_position(scores, 12) yourself; it should return (0, 3) after three passes.", "Confidence: lowered.", "N.B. the figures are rounded."):
        assert md.is_note_sentence(sentence) and md.split_note_clauses(sentence)[0] == "", sentence
    for sentence in ("Note that the poem never names the city.", 'The speaker says "Note: the gate is shut" twice.'):
        assert not md.is_note_sentence(sentence), sentence
    for tid in ("hi-t13", "hi-p7c"):
        note = claim(parse(tid), "Note:")
        assert note.claim_role == "other" and note.materiality == "supporting", tid
    assert count_answer_words(ITEMS["hi-t13"]["response_text"]) == (303, 57)
    assert count_answer_words(ITEMS["ess-t13"]["response_text"])[0] <= 350
    for tid in ("hi-t13", "ess-t13"):
        _ch, _reply, receipt = single(tid)
        assert "INT-REQ-005" not in codes(receipt), tid
        assert not [f for f in receipt.structural_findings if f.code == "HI-STR-001" and any(c.startswith("h2.") for c in f.claim_ids)]
    # the History parser reads the note through the shared helper: a "Note:" paragraph is a note paragraph, not body paragraph 2
    rep = HistorySpecialistAdapter().parse_response(ITEMS["hi-t13"]["response_text"], request_id="r", task_id="t", report_id="rep", subject="History",
                                                    task_type="essay", supplied_texts=[])
    assert [c.claim_role for c in rep.claims if c.claim_id.startswith("h2.")] == ["other"]


def test_generic_notes_questions_and_headings_are_other():
    ess = parse("ess-t13")
    assert claim(ess, "Note: the textbook library and MyLib were unavailable").claim_role == "other"
    for tid, start in (("cs-t13", "Next step: trace find_position"), ("sp-t13", "Next step: redo item 3")):
        assert claim(parse(tid), start).claim_role == "other"
    maa = parse("maa-p7b")
    assert claim(maa, "Limit: no textbook library").claim_role == "other"
    assert claim(maa, "The answer rests on course-standard results").claim_role == "other"  # a "Limit:" paragraph is a note as a whole
    ch = parse("ch-t13")
    question = claim(ch, "What are the concentrations of each reactant in the mixture")
    assert question.claim_role == "other" and question.materiality == "supporting"  # "should" inside a question is no judgement
    assert claim(ch, "Ask yourself:").claim_role == "other"
    ec = parse("ec-p7a")
    assert claim(ec, "Measure: price elasticity of demand (PED)").claim_role == "other"
    assert claim(ec, "Diagram 1: The market for sugar-sweetened drinks").claim_role == "other"
    assert claim(parse("ec-t13"), "Table 1 quotes the rate as krona per US$").claim_role != "other"  # the sentence after a heading keeps its role
    bm = parse("bm-p7a")
    assert claim(bm, "2024 (no tax)").claim_role == "other" and claim(bm, "Price received per litre = $1.60.").claim_role == "quantitative"
    assert claim(bm, "Working for (b):").claim_role == "other"


@pytest.mark.parametrize("tid", ["ps-t13-all-notes", "ch-t13-all-notes"])
def test_an_answer_made_only_of_notes_carries_no_answer(tid):
    rep = parse(tid)
    assert all(c.claim_role == "other" and c.materiality == "supporting" for c in rep.claims)
    _ch, reply, receipt = single(tid)
    assert reply is not None and "INT-REQ-012" in codes(receipt)


def test_dropping_a_note_in_a_synthesis_raises_no_ledger_warning():
    ch, reply, _receipt = single("hi-t13")
    assert "INT-LEDGER-019" not in codes(deliver_synthesis(ch, {"hi-t13": reply}, ("hi-t13",)))
    ch, replies, receipts = exchange("hi-p7c", "lit-p7c", "p7c")
    assert "INT-LEDGER-019" not in codes(deliver_synthesis(ch, replies, ("hi-p7c", "lit-p7c")))


# ------------------------------------------------------------ translation-fidelity: support links follow the stated direction


def test_support_links_follow_the_direction_the_specialist_states():
    ec = parse("ec-p7a")
    point, consequence = claim(ec, "Consumers bear most of the tax because"), claim(ec, "Consumers therefore pay $0.30")
    assert consequence.claim_id not in point.supporting_claim_ids and point.claim_id in consequence.supporting_claim_ids
    ess = parse("ess-t13")
    strategy, however = claim(ess, "Upgrading the sewage treatment works"), claim(ess, "However, arable farmland drains")
    assert however.claim_id not in strategy.supporting_claim_ids
    overall = claim(ess, "Overall, it is a worthwhile first step")
    assert overall.claim_id not in strategy.supporting_claim_ids and strategy.claim_id in overall.supporting_claim_ids
    cs = parse("cs-t13")
    binary, linear = claim(cs, "Binary search: at most 10 passes."), claim(cs, "Linear search: at most 1,000 comparisons.")
    assert binary.materiality == linear.materiality == "material"
    assert linear.claim_id not in binary.supporting_claim_ids and binary.claim_id not in linear.supporting_claim_ids
    rep = GenericTextParser("mathematics-ai-specialist").parse_response(
        'Assumption: "complete years" is read as the value at the end of each whole year. The value first passes 6000 in month 136, during the twelfth year.',
        request_id="r", task_id="t", report_id="rep", subject="Mathematics: Applications and Interpretation", task_type="short_answer")
    assumption = claim(rep, "Assumption:")
    assert assumption.claim_role != "point" and assumption.supporting_claim_ids == [] and assumption.materiality == "supporting"


# ------------------------------------------------------------ results-audit (minor): lit-t13 marking feedback


def test_lit_t13_feedback_labels_are_notes_and_the_fixes_are_whole_material_claims():
    rep = parse("lit-t13")
    for start in ("Task — Paper 1, SL — How does the writer present", "What the task wants:", "Provisional marks: A 3/5", "Confidence: lowered."):
        c = claim(rep, start)
        assert c.claim_role == "other" and c.materiality == "supporting", start
    assert claim(rep, "What earned credit:").claim_role == "point"
    fixes = [claim(rep, s) for s in ("Biggest gap: each quotation is followed", "Fix it: 1. Choose one key word", "2. Add the evidence", "3. Quote and name accurately")]
    assert all(c.materiality == "material" for c in fixes), [(c.claim_id, c.claim_role) for c in fixes]
    assert not [c for c in rep.claims if re.fullmatch(r"(?:Fix it: )?\d\.", c.claim_text.strip())]
    assert english_sentences("Fix it: 1. Choose one key word. 2. Add the evidence.") == ["Fix it: 1. Choose one key word.", "2. Add the evidence."]
    assert english_sentences("The total was 12. The next line follows.") == ["The total was 12.", "The next line follows."]
    ch, reply, _receipt = single("lit-t13")
    assert "INT-LEDGER-019" not in codes(deliver_synthesis(ch, {"lit-t13": reply}, ("lit-t13",)))


# ------------------------------------------------------------ adversarial-live: ES-SRC-008 per quotation


def peer_doc(tid: str) -> SuppliedText:
    return SuppliedText(document_id=f"peer:{tid}", title="peer report relayed through the hub", author=ITEMS[tid]["agent_id"], text=ITEMS[tid]["response_text"])


def test_es_src_008_credits_each_quotation_by_the_phrase_that_governs_it():
    genuine = parse_english(ITEMS["lit-p7c"]["response_text"], request_id="r", task_id="p7c", report_id="rep", task_type="analytical_paragraph",
                            supplied_texts=[*docs(ITEMS["lit-p7c"]), peer_doc("hi-p7c")])
    assert not [f for f in structural_checks(genuine) if f.code == "ES-SRC-008"]
    control = parse_english(ITEMS["lit-p7ce"]["response_text"], request_id="r", task_id="p7c", report_id="rep", task_type="analytical_paragraph",
                            supplied_texts=[*docs(ITEMS["lit-p7ce"]), peer_doc("hi-p7ce")])
    assert not [f for f in structural_checks(control) if f.code == "ES-SRC-008"]
    wrong = parse_english(ITEMS["lit-p7cb"]["response_text"], request_id="r", task_id="p7c", report_id="rep", task_type="analytical_paragraph",
                          supplied_texts=[*docs(ITEMS["lit-p7cb"]), peer_doc("hi-p7cb")])
    [f] = [f for f in structural_checks(wrong) if f.code == "ES-SRC-008"]
    assert f.severity == "error" and "'two streets'" in f.message and "peer:hi-p7cb" in f.message
    # through the hub the genuine exchange carries no misattribution for the poem's lines
    _ch, _replies, receipts = exchange("hi-p7c", "lit-p7c", "p7c")
    assert not [x for x in receipts["lit-p7c"].findings if x.code == "INT-SUBJ-003" and ("By Wednesday" in x.message or "By autumn" in x.message)]
