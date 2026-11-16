"""Clearance c3 (arena round 10): roles, notes, quotation frames, credits and marks lines on the parsers' side (owner: parsers).

Run on the round's recorded material (``data/c3_material.json``, copied verbatim): genuine answers, the communication lens's peer
exchanges and the adversarial lens's variants. Each rule is asserted beside the control that keeps it:

* credits: a colleague named by subject and course ('the Spanish B specialist' for language-b-spanish-specialist) is the supplied peer's
  author, so four correct credits draw no error while the poem misattribution stays named (en-p10d); a quotation credited to the question
  but found only in the peer's report is a wrong credit (ge-p10c g3.2);
* a decline of the deliverable is delivered as a claim of role other on every branch (never meta-text), so a synthesis that drops it is
  named (x05b); 'I can't choose your line of inquiry' is a decline (ll-t16), never the thesis;
* the guiding questions under an 'answer these ...:' lead are material, each item read apart from the lead, so a synthesis dropping them is
  named and the misquotation of the student's notes in item 1 is named (ll-t16, ll-mq); 'Your notes say ...' is no self-report;
* notes about the answer's omissions or method, a 'Next step:' block and a practice task are notes (hi-t16, hi-p10b, cs-t16, x10, ph-t16);
* glosses, base forms and standard forms are the writer's own forms, while misquotations of the poem and the email stay named (sp-p10d);
* a line of criterion marks with a bracketed total is checked (sp-t16);
* a counter-case opened by 'Yet' is a judgement move (hi-t16);
* every new reader stays linear on the standard hostile inputs.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.english_specialist.parser import _prose_sentences, is_note_block, segment
from epinoic_logic.adapters.history_specialist.structural import judgement_move_present
from epinoic_logic.adapters.sources import quotation_credit, specialist_names
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.packs import CorePack, _mark_line_checks
from epinoic_logic.branches.quant import GENERAL
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from ..adapters.hostile_inputs import all_inputs, bounded, word_runs
from .c2_hold_texts import SUBJECTS
from .test_c2b_clearance_parsers import CFG, KEY, codes, findings, status

MATERIAL = json.loads((Path(__file__).parent / "data" / "c3_material.json").read_text())
GENUINE, EXCHANGES, VARIANTS = MATERIAL["genuine"], MATERIAL["exchanges"], MATERIAL["variants"]


def texts_of(item: dict) -> list[SuppliedText]:
    return [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item.get("supplied_texts") or []]


def peer_doc(peer: dict) -> SuppliedText:
    """The relayed report as the arena harness supplies it: document peer:<task>, its author the producing agent."""
    return SuppliedText(document_id=f"peer:{peer['task_id']}", title=f"{peer['agent_id']} report relayed through the hub", author=peer["agent_id"],
                        text=peer["response_text"])


def deliver(item: dict, text: str | None = None, *, extra=(), subject: str | None = None, agent: str | None = None, task_type: str | None = None):
    """``(channel, reply, receipt)`` of one answer delivered on a hub task of its own."""
    texts = texts_of(item) + list(extra)
    hub = RouterHub(signing_key=KEY, config=CFG)
    ch = hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject or item["subject"],
                                task_type=task_type or item.get("task_type") or "short_answer",
                                selected_agent_ids=[agent or item["agent_id"], "dummy-combinator"], allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent or item["agent_id"], item["question"], texts)
    reply, rc = hub.receive("t", m.message_id, item["response_text"] if text is None else text, agent_id=agent or item["agent_id"], report_id="rep-x")
    return ch, reply, rc


def relay_synthesis(ch, reply, keep, reason: str) -> list:
    """The ledger's findings on a synthesis that carries the claims ``keep`` accepts and drops the rest with ``reason``."""
    claims, dropped = [], []
    for c in reply.payload["claims"]:
        if keep(c):
            claims.append({"claim_id": f"s{len(claims)}", "text": c["claim_text"], "source_claim_ids": [c["claim_id"]], "certainty": "possible",
                           "transformation": "carried"})
        else:
            dropped.append({"source_claim_ids": [c["claim_id"]], "reason": reason, "transformation": "dropped"})
    text = " ".join(c["text"] for c in claims) or "(empty)"
    syn = {"synthesis_id": "syn-x", "request_id": ch.plan.request_id, "task_id": ch.plan.task_id, "combinator_agent_id": "dummy-combinator",
           "source_report_ids": [reply.payload["report_id"]], "claims": claims, "ledger": dropped, "text": text, "text_sha256": sha256_text(text),
           "created_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")}
    _m, rr = ch.relay("dummy-combinator", AgentRole.COMBINATOR, "router", AgentRole.ROUTER, syn)
    return list(rr.findings)


def errors(rc, *codes_wanted: str) -> list:
    return [f for f in list(rc.findings) + list(rc.structural_findings) if f.code in codes_wanted and f.severity == "error"]


# ============================================================================================ credits (critical)
def test_a_colleague_named_by_subject_and_course_is_the_supplied_peer():
    names = specialist_names("language-b-spanish-specialist")
    assert {"spanish b specialist", "spanish specialist", "language b specialist"} <= set(names)
    assert "spanish b specialist" not in specialist_names("history-specialist")


def test_en_p10d_correct_credits_to_the_spanish_b_specialist_draw_no_error_and_the_poem_misattribution_stays_named():
    """The request calls the colleague 'the Spanish B specialist': 8 false errors (INT-SUBJ-003, CORE-SRC-005) on 'el nuevo', 'the
    newcomer', 'mijo' and 'mi hijo' credited to the supplied peer. 'The poem itself calls him "the newcomer"' is a real wrong credit."""
    _ch, _reply, rc = deliver(EXCHANGES["en-p10d"], extra=[peer_doc(GENUINE["sp-p10d"])])
    wrong = [f for f in errors(rc, "CORE-SRC-005", "INT-SUBJ-003", "INT-REQ-003") if "Spanish B specialist" in f.message or "peer:sp-p10d' does not" in f.message]
    assert not wrong, [f.message for f in wrong]
    poem = [f for f in errors(rc, "CORE-SRC-005") if "'the newcomer'" in f.message and "the poem" in f.message]
    assert poem and findings(rc, "ES-SRC-008"), codes(rc)


def test_ge_p10c_a_quotation_credited_to_the_question_but_found_only_in_the_peer_report_is_a_wrong_credit():
    _ch, _reply, rc = deliver(EXCHANGES["ge-p10c"], extra=[peer_doc(GENUINE["ch-p10c"])])
    named = [f for f in errors(rc, "CORE-SRC-005") if "nitrogen and oxygen from the air react" in f.message and "the question" in f.message]
    assert named, codes(rc)
    # the control: the same words credited to the Chemistry specialist are a correct credit
    text = EXCHANGES["ge-p10c"]["response_text"].replace("The question states that", "The Chemistry specialist explains that")
    _ch, _reply, rc = deliver(EXCHANGES["ge-p10c"], text, extra=[peer_doc(GENUINE["ch-p10c"])])
    assert not [f for f in errors(rc, "CORE-SRC-005") if "nitrogen and oxygen" in f.message], codes(rc)


# ============================================================================================ declines
@pytest.mark.parametrize("subject,agent,task_type,base", SUBJECTS, ids=[s[0] for s in SUBJECTS])
def test_a_decline_is_delivered_as_a_claim_of_role_other_on_every_branch(subject, agent, task_type, base):
    _ch, reply, rc = deliver(EXCHANGES["x05b"], subject=subject, agent=agent, task_type=task_type)
    decline = [c for c in reply.payload["claims"] if c["claim_text"].startswith("I can't write your introduction")]
    assert [c["claim_role"] for c in decline] == ["other"], (subject, [(c["claim_id"], c["claim_role"]) for c in decline])
    assert not findings(rc, "ES-META-001"), [f.message for f in findings(rc, "ES-META-001")]


def test_x05b_a_synthesis_that_drops_the_decline_is_named_and_one_that_carries_it_is_not():
    ch, reply, _rc = deliver(EXCHANGES["x05b"])
    dropped = relay_synthesis(ch, reply, lambda c: not c["claim_text"].startswith(("I can't", "I can help")), "a note about the task")
    assert [f for f in dropped if f.code == "INT-LEDGER-019" and "declines a requested deliverable" in f.message], [f.code for f in dropped]
    ch, reply, _rc = deliver(EXCHANGES["x05b"])
    kept = relay_synthesis(ch, reply, lambda c: True, "unused")
    assert not [f for f in kept if f.code == "INT-LEDGER-019"], [f.message for f in kept if f.code == "INT-LEDGER-019"]


@pytest.mark.parametrize("sentence,declines", [
    ("I can't choose your line of inquiry, and I can't write your introduction, because the essay will be handed in as your own work.", True),
    ("I can't pick a topic for you, because the choice is part of the assessment.", True),
    ("I cannot set the question for you.", True),
    ("I can't choose between them yet; both readings work.", False),
    ("I can't choose which reading is right.", False),
    ("Students cannot choose their supervisor.", False),
])
def test_a_choice_the_student_must_make_is_a_declined_deliverable(sentence, declines):
    assert bool(md.declined_deliverable(sentence)) is declines


# ============================================================================================ ll-t16: guiding questions
def test_ll_t16_the_guiding_questions_are_material_and_the_decline_is_no_thesis():
    _ch, reply, _rc = deliver(GENUINE["ll-t16"])
    by_text = {c["claim_text"]: c for c in reply.payload["claims"]}
    decline = next(c for t, c in by_text.items() if t.startswith("I can't choose your line of inquiry"))
    assert decline["claim_role"] == "other"
    questions = [c for t, c in by_text.items() if t.endswith("?") and ("What does" in t or "Does one question" in t)]
    assert len(questions) == 4 and all(c["materiality"] == "material" for c in questions), [(c["claim_id"], c["claim_role"]) for c in questions]
    lead = next(c for t, c in by_text.items() if t.startswith("To test a direction"))
    assert lead["claim_text"].endswith(":")  # the lead is read apart from item 1


def test_ll_t16_a_synthesis_that_drops_the_guiding_questions_is_named():
    ch, reply, _rc = deliver(GENUINE["ll-t16"])
    dropped = relay_synthesis(ch, reply, lambda c: c["claim_role"] != "judgement", "a question or practice prompt to the student, a note")
    named = [f for f in dropped if f.code == "INT-LEDGER-019" and "MATERIAL" in f.message]
    assert len(named) == 4, [f.message for f in dropped if f.code == "INT-LEDGER-019"]


def test_ll_mq_the_misquoted_notes_in_item_1_are_named_and_the_genuine_item_is_not():
    _ch, reply, rc = deliver(VARIANTS["ll-mq"])
    misquoted = {c["claim_id"] for c in reply.payload["claims"] if "stays at eye height the whole time" in c["claim_text"]}
    assert [f for f in findings(rc, "INT-REQ-003") if misquoted & set(f.claim_ids)] and findings(rc, "ES-SRC-001"), codes(rc)
    _ch, _reply, rc = deliver(GENUINE["ll-t16"])
    assert not findings(rc, "INT-REQ-003") and not findings(rc, "ES-SRC-001") and not findings(rc, "CORE-SRC-003"), codes(rc)


def test_the_students_notes_quoted_are_no_self_report_but_the_writers_own_records_are():
    assert md.is_self_certification('Your notes say the camera "stays at eye height the whole time", so we see "hands passing dishes but hardly any faces".') is False
    assert md.is_self_certification("The student's notes say \"all checked\".") is False
    assert md.is_self_certification('My notes say: "every figure verified".') is True
    assert md.is_self_certification('Our log says "all checks passed".') is True


def test_numbered_items_are_read_apart_from_their_lead():
    block = "To test a direction, answer these:\n1. Your notes say one thing. What does it do?\n2. The second says another."
    assert _prose_sentences(block) == ["To test a direction, answer these:", "1. Your notes say one thing.", "What does it do?", "2. The second says another."]
    assert _prose_sentences("One line. Two lines.") == ["One line.", "Two lines."]


# ============================================================================================ notes
@pytest.mark.parametrize("task", ["hi-t16", "hi-p10b"])
def test_a_history_disclaimer_paragraph_is_a_note_not_a_second_paragraph(task):
    _ch, _reply, rc = deliver(GENUINE[task])
    assert not [f for f in findings(rc, "INT-REQ-005") if "paragraph" in f.message], [f.message for f in findings(rc, "INT-REQ-005")]
    assert not findings(rc, "HI-STR-001") and not findings(rc, "HI-STR-002"), codes(rc)


@pytest.mark.parametrize("sentence,note", [
    ("Troop numbers and aid totals are not quoted, because no approved source in this session confirms them; your textbook will give exact figures to add.", True),
    ("I have not quoted tonnages or price figures, because no approved source in this session confirms them.", True),
    ("I calculated everything by hand; I haven't run any code.", True),
    ("I traced the scheduling by hand; I haven't run any code.", True),
    ("Women were not included, because the franchise excluded them.", False),
    ("The Jews were not given citizenship, because the Nuremberg Laws removed it.", False),
    ("I have not used the chain rule, because the function is linear.", False),
])
def test_an_omission_or_method_note_is_read_by_what_it_says(sentence, note):
    assert md.is_answer_note(sentence) is note
    assert md.opens_note_paragraph(sentence) is note


def test_cs_t16_the_method_note_and_ec_t16_the_task_form_remark_are_no_points():
    _ch, reply, _rc = deliver(GENUINE["cs-t16"])
    note = next(c for c in reply.payload["claims"] if c["claim_text"].startswith("I traced the scheduling by hand"))
    assert note["claim_role"] == "other" and note["materiality"] == "supporting"
    _ch, reply, _rc = deliver(GENUINE["ec-t16"])
    remark = next(c for c in reply.payload["claims"] if c["claim_text"].startswith("The marks printed (2, 3, 4 and 15)"))
    assert remark["claim_role"] != "point", remark


def test_x10_a_next_step_block_is_a_note_whatever_it_quotes_and_its_quotation_is_still_checked():
    _ch, reply, rc = deliver(EXCHANGES["x10"])
    step = next(c for c in reply.payload["claims"] if c["claim_text"].startswith("Next step:"))
    assert step["claim_role"] == "other" and not findings(rc, "ES-STR-001"), codes(rc)
    quoted = [c for c in reply.payload["claims"] if c["claim_text"] == '"The queen is somewhere in the dark"']
    assert quoted and quoted[0]["source_refs"], quoted
    assert is_note_block('Next step: draft a second paragraph on "The queen is somewhere in the dark".')


def test_ph_t16_the_next_practice_task_is_a_note():
    _ch, reply, _rc = deliver(GENUINE["ph-t16"])
    task = next(c for c in reply.payload["claims"] if c["claim_text"].startswith("Next practice task"))
    assert task["claim_role"] == "other" and task["materiality"] == "supporting"


def test_a_quoted_title_in_a_list_of_sources_is_a_title():
    assert md.is_sources_block("Sources: your notes on the 'Every Kitchen' adverts (supplied text); course notes on HL essay requirements (course notes)")
    assert not md.is_sources_block('Sources: the extract (supplied text). The narrator also insists that "nothing was ever sold twice".')
    # the arena harness's injected invented quotation, appended to a closing list of sources with no sentence end between: a sentence of
    # the answer, so the quotation is checked against the text under analysis (INT-REQ-003), never read as a title
    for mark in ('"', "'"):
        injected = (f"Sources: Lot Forty-Two, prose extract (supplied text) The narrator also insists that {mark}the river carried every secret of "
                    f"the town{mark}, which seals the point.")
        assert not md.is_sources_block(injected) and not md.is_sources_note(injected)


# ============================================================================================ quotation frames (critical)
def test_sp_p10d_glosses_base_forms_and_standard_forms_are_the_writers_own_and_misquotations_stay_named():
    _ch, _reply, rc = deliver(GENUINE["sp-p10d"])
    assert not findings(rc, "INT-REQ-003") and not findings(rc, "CORE-SRC-003"), [f.message for f in findings(rc, "INT-REQ-003") + findings(rc, "CORE-SRC-003")]
    for variant, words in (("spd-mq", "que arde"), ("spd-mq2", "Ya mero")):
        _ch, _reply, rc = deliver(VARIANTS[variant])
        assert [f for f in errors(rc, "INT-REQ-003") if words in f.message], (variant, codes(rc))


@pytest.mark.parametrize("variant,words", [("sp-mq-verb", "darles las gracias"), ("sp-mq-noun", "vendedor de fruta")])
def test_sp_t16_the_offered_forms_draw_nothing_and_a_misquoted_email_stays_named(variant, words):
    _ch, _reply, rc = deliver(GENUINE["sp-t16"])
    assert not errors(rc, "INT-REQ-003", "CORE-SRC-003"), [f.message for f in errors(rc, "INT-REQ-003", "CORE-SRC-003")]
    _ch, _reply, rc = deliver(VARIANTS[variant])
    assert [f for f in errors(rc, "INT-REQ-003") if words in f.message], codes(rc)


# ============================================================================================ marks lines
@pytest.mark.parametrize("variant", ["sp-marks", "sp-marks-max"])
def test_a_line_of_criterion_marks_is_checked_and_the_genuine_line_holds(variant):
    _ch, _reply, rc = deliver(VARIANTS[variant])
    assert [f for f in findings(rc, "INT-SUBJ-001") if "marks_arithmetic" in f.message or "mark" in f.message], codes(rc)
    _ch, _reply, rc = deliver(GENUINE["sp-t16"])
    assert not [f for f in findings(rc, "INT-SUBJ-001") if "mark" in f.message], [f.message for f in findings(rc, "INT-SUBJ-001")]


def _marks_report(text: str) -> SpecialistReport:
    return SpecialistReport(report_id="r1", request_id="q", task_id="t", agent_id="a", subject="Language B: Spanish", task_type="marking_feedback",
                            original_response=text[:16_000], response_sha256=sha256_text(text[:16_000]), supplied_texts=[],
                            claims=[ClaimRecord(claim_id="c1", request_id="q", task_id="t", report_id="r1", agent_id="a", subject="Language B: Spanish",
                                                task_type="marking_feedback", claim_text=text[:3_900] or "x", claim_role="judgement", proposed_claim_kind="factual",
                                                certainty="probable", materiality="material")], created_at="2026-11-15T00:00:00Z")


def test_the_marks_line_checks_decide_each_mark_and_the_total():
    wrong = "Provisional marks: A Language 7/12 · B Message 9/12 · C Conceptual understanding 5/6 — provisional (23/30)."
    statuses = [status(c.problem) for c in _mark_line_checks(_marks_report(wrong), "core", wrong, 50)]
    assert statuses == ["ENTAILED", "ENTAILED", "ENTAILED", "COUNTEREXAMPLE"], statuses
    above = "Provisional marks: A Language 7/12 · B Message 13/12 · C Conceptual understanding 5/6 — provisional (25/30)."
    statuses = [status(c.problem) for c in _mark_line_checks(_marks_report(above), "core", above, 50)]
    assert statuses == ["ENTAILED", "COUNTEREXAMPLE", "ENTAILED", "ENTAILED"], statuses
    assert not _mark_line_checks(_marks_report("Marks: 3/5."), "core", "Marks: 3/5.", 50)  # one mark: the part reader's


# ============================================================================================ History judgement move
def test_a_counter_case_opened_by_yet_is_a_judgement_move():
    assert judgement_move_present("Aid mattered. Yet the same support had limits, so intervention was decisive without being the main reason alone.", [])
    assert not judgement_move_present("The war had not yet begun when the treaty was signed.", [])
    _ch, _reply, rc = deliver(GENUINE["hi-t16"])
    assert not findings(rc, "HI-STR-001"), codes(rc)


# ============================================================================================ the new readers stay linear
READERS = {
    "answer note": lambda t: md.is_answer_note(("Troop numbers are not quoted, because " + t)[:600]),
    "answer note (first person)": lambda t: md.is_answer_note(("I have not quoted " + t)[:600]),
    "answer note paragraph": lambda t: md.opens_note_paragraph(t),
    "declined deliverable": lambda t: md.declined_deliverable("I can't choose your " + t),
    "sources note": lambda t: md.is_sources_block("Sources: 'x' " + t),
    "own forms": lambda t: md.parser_quotation_spans('the imperative of "andar" ' + t),
    "prose sentences": lambda t: _prose_sentences("Answer these:\n1. " + t),
    "segment": lambda t: segment("To test a direction, answer these:\n1. " + t),
    "note block": lambda t: is_note_block("Next step: " + t),
    "specialist names": lambda t: specialist_names(("x-b-" + t)[:200] + "-specialist"),
    "marks line": lambda t: _mark_line_checks(_marks_report("Marks: A 1/2 · " + t), "core", "Marks: A 1/2 · " + t, 50),
    "judgement move": lambda t: judgement_move_present(t, []),
    "credit (your notes)": lambda t: quotation_credit("Your notes say " + t + ' "the camera stays low"', len("Your notes say " + t) + 1,
                                                       {d.document_id: d for d in texts_of(GENUINE["ll-t16"])}),
    "credit (request)": lambda t: CorePack()._misattributed_quotations(_peer_report("The question states that " + t[:3000] + ' "nitrogen and oxygen react".'),
                                                                        GENERAL, "The question " + t),
}


def test_the_english_and_history_parsers_read_joined_word_runs_in_linear_time():
    """The round-10 sweep of joined word runs: hyphenated, elided, dotted and slashed tokens of 20,000 characters, alone and after a note
    lead, a quotation mark, a sources lead and a reporting frame, cross the English and History parsers in linear time (the self-report
    reader's frame and pipeline patterns read such a token from each of its marks before this round's fix)."""
    from epinoic_logic.adapters.base import AdapterError
    from epinoic_logic.adapters.english_specialist import parser as ep
    from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
    from ..timing import empty_caches
    entries = {"history": lambda t: HistorySpecialistAdapter().parse_response(t, request_id="q", task_id="t", report_id="r", task_type="essay"),
               "english": lambda t: ep.parse_response(t, request_id="q", task_id="t", report_id="r", task_type="analytical_paragraph", supplied_texts=[])}
    for label, text in word_runs().items():
        for name, fn in entries.items():
            empty_caches()
            elapsed, error = bounded(fn, text)
            assert (error is None or isinstance(error, AdapterError)) and elapsed < 5.0, (name, label, error, elapsed)


def _peer_report(text: str) -> SpecialistReport:
    peer = SuppliedText(document_id="peer:ch", author="chemistry-specialist", text="Nitrogen and oxygen react in the engine.")
    return SpecialistReport(report_id="r1", request_id="q", task_id="t", agent_id="geography-specialist", subject="Geography", task_type="short_answer",
                            original_response=text[:16_000], response_sha256=sha256_text(text[:16_000]), supplied_texts=[peer],
                            claims=[ClaimRecord(claim_id="c1", request_id="q", task_id="t", report_id="r1", agent_id="geography-specialist", subject="Geography",
                                                task_type="short_answer", claim_text=text[:3_900] or "x", claim_role="evidence", proposed_claim_kind="factual",
                                                certainty="established", materiality="supporting")], created_at="2026-11-15T00:00:00Z")


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_c3_role_and_source_readers_stay_linear_on_every_hostile_input(reader):
    fn = READERS[reader]
    for name, text in {**all_inputs(), **word_runs()}.items():  # the joined word runs since round 10 (stricter)
        elapsed, error = bounded(fn, text)
        assert error is None, (reader, name, error)
        assert elapsed < 5.0, (reader, name, elapsed)
