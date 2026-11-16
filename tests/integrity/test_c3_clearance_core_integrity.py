"""Integrity behaviour found wanting by the round-10 clearance overseers (integrated round c3), fixed by the core fixer:

* critical (rule local-glosses): translator symbols that only share a name were pooled as one quantity: a gloss that refers to its
  own claim's statement (ch-p10c 'x0', 'value of the left-hand side of a stated equation'), two functions told apart only by their
  case ('f(-3) from the cubic' against 'F(-3)'), other arithmetic ("f'(-1) = 3 + 6 - 9" against '3 - 6 - 9'), a figure of
  another sign; a sort clash between two translations withheld the whole joint check with an error (ec-t16);
* major and minor (rule same-gloss): paraphrased glosses of one quantity were read as two (abbreviations 'ctrl' and 'inter', word
  order and a unit after a comma, a descriptive 'non-' compound read as a negation);
* major: a note about figures the specialist declines ('any number I gave would be unverified') labelled every figure of its
  report as given from memory (INT-LEDGER-027 x27 on the bm-t16 synthesis), label numbers ('Option 1') included;
* major: a synthesized claim crediting one specialist's calculation to another specialist ('The Geography specialist calculated
  that ...', citing the Chemistry report) drew no finding;
* major: a figure written as a Spanish count ('hace dos semanas' carried as 'hace tres semanas') drew no figure finding;
* minor: INT-LEDGER-026 charged a claim carried word for word with a credit its source makes ('The narrator notes that ...'), and
  read 'Diagram 1', the answer's own diagram, as the supplied document.

The recorded material is in ``tests/channel/data/c3_core_material.json`` (copied verbatim from the round)."""
from __future__ import annotations

import pytest

from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import Synthesis, SynthesizedClaim
from epinoic_logic.integrity import ledger as L
from epinoic_logic.integrity.cross_check import (check_cross_report_consistency, claim_local_gloss, gloss_difference, gloss_reading,
                                                 rename_sort_clashes_apart, split_by_gloss)
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText, sha256_text

from ..channel.c3_core_support import C3, deliver_exchange
from ..core_hostile import SHAPES, one, sweep

CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)


def codes(findings) -> list[str]:
    return [f.code for f in findings]


def recorded(task: str, cid: str) -> Problem:
    tr = C3["c3"]["translations"][task]
    key = cid if cid in tr else next(k for k in tr if k.split("@")[0] == cid)
    data = dict(tr[key]["problem"])
    data["claim_id"] = key
    return Problem.model_validate(data)


# ------------------------------------------------------------------------------------------ critical: rule local-glosses

@pytest.mark.parametrize("a,b,why", [
    ("f(-3) from the cubic", "F(-3)", "functions ['f'] against ['F']"),               # maa-t16 m2.1 / m5.5
    ("f(3) from the cubic", "F(3) for F(x) = x^4/4 - x^3 - (9/2)x^2 + 27x", "functions"),  # maa-t16 m3.4 / m5.4 (a true warning)
    ("f'(-1) = 3 + 6 - 9", "3 - 6 - 9", "arithmetic ['3+6-9'] against ['3-6-9']"),    # maa-t16 m3.5 / m6.3
    ("f'(1)", "f(1)", "functions"),
    ("x = -5", "x = 5", "figures ['-5'] against ['5']"),
])
def test_another_function_other_arithmetic_or_another_sign_names_another_quantity(a, b, why):
    found = gloss_difference(a, b)
    assert found is not None and why in found, found
    assert gloss_difference(b, a) is not None


def test_a_gloss_that_refers_to_its_own_claims_statement_is_that_claims_quantity():
    assert claim_local_gloss("value of the left-hand side of a stated equation") and claim_local_gloss("the value in this step")
    assert not claim_local_gloss("the x the claim states") and not claim_local_gloss("the left-hand side of the ideal gas equation")
    probs = [recorded("ch-p10c", c) for c in ("s3.1", "s4.2", "s4.6", "s6.2")]
    apart, splits = split_by_gloss(probs)
    assert "x0" in splits and len({tuple(ids) for _n, ids, _g in splits["x0"]}) == 4  # every claim keeps its own x0


@pytest.mark.parametrize("task,claims", [("ch-p10c", ("s3.1", "s4.2", "s4.6", "s6.2")), ("maa-t16", ("m2.1", "m5.5", "m3.5", "m6.3", "m3.4", "m5.4"))])
def test_the_recorded_pools_charge_no_contradiction_on_a_shared_name(task, claims):
    res, f = check_cross_report_consistency([recorded(task, c) for c in claims], request_id=f"req-{task}", config=CFG)
    assert res is not None and "INT-CONFLICT-001" not in codes(f) and all(x.severity == "warning" for x in f), [(x.code, x.claim_ids) for x in f]
    # what the pool would charge is named as unattributable, a translation fault
    assert "INT-CONFLICT-004" in codes(f)


def _real(cid: str, name: str, meaning: str, value: str) -> Problem:
    v = {"op": "var", "name": name}
    return Problem.model_validate({"problem_id": f"p-{cid}", "request_id": "req-x", "claim_id": cid, "query": "consistency",
                                   "symbols": [{"name": name, "sort": "Real", "meaning": meaning}],
                                   "premises": [{"id": "pr", "expr": {"op": "eq", "left": v, "right": {"op": "real", "value": value}}}]})


@pytest.mark.parametrize("g1,g2", [("molar mass of CO2, g/mol", "molar mass of CO2, g/mol"), ("f(-3) from the cubic", "f(-3)"),
                                   ("control roots: interphase cells out of 500", "ctrl roots: inter cells out of 500 counted")])
def test_a_real_contradiction_over_one_quantity_is_still_charged(g1, g2):
    _res, f = check_cross_report_consistency([_real("a1", "q", g1, "44.01"), _real("b2", "q", g2, "45")], request_id="req-x", config=CFG)
    assert [(x.code, x.severity, sorted(x.claim_ids)) for x in f if x.code.startswith("INT-CONFLICT")] == [("INT-CONFLICT-001", "error", ["a1", "b2"])]


def test_ec_t16_a_sort_clash_is_read_apart_with_a_warning():
    probs = [recorded("ec-t16", "g11.7"), recorded("ec-t16", "g11.9")]
    renamed, warned = rename_sort_clashes_apart(probs)
    assert sorted(f.message.split("'")[1] for f in warned) == ["boats19", "boats25"] and all(f.code == "INT-GLOSSARY-005" and f.severity == "warning" for f in warned)
    assert {s.name for s in renamed[1].symbols} >= {"boats19_int", "boats25_int"} and {s.name for s in renamed[0].symbols} >= {"boats19", "boats25"}
    res, f = check_cross_report_consistency(probs, request_id="req-ec-t16", config=CFG)
    assert res is not None and res.status.value == "CONSISTENT" and "INT-GLOSSARY-001" not in codes(f)


# ------------------------------------------------------------------------------------------ rule same-gloss: paraphrases

@pytest.mark.parametrize("a,b", [
    ("control roots: interphase cells out of 500 (task figure)", "ctrl roots: inter cells out of 500 counted (task figure)"),  # bi-t16 ctrl_inter
    ("extract roots: interphase cells out of 500 (task figure)", "ext roots: inter cells out of 500 counted (task figure)"),   # bi-t16 ext_inter
    ("FCFS completion time of P4, ms", "P4 completion time under FCFS, ms"),                                                   # cs-t16 fc4
    ("false positives (non-aluminium flagged), count", "false positives, count"),                                               # cs-p10a fp
    ("P1 turnaround time, ms", "P1 turnaround time, ms (round robin)"),
])
def test_paraphrased_glosses_of_one_quantity_are_one_gloss(a, b):
    assert gloss_difference(a, b) is None and gloss_difference(b, a) is None


@pytest.mark.parametrize("a,b,why", [
    ("non-renewable resources", "renewable resources", "negates"),
    ("non-aluminium items flagged", "aluminium items flagged", "negates"),
    ("the price does not rise", "the price rises", "negates"),
    ("P1 turnaround time, ms (FCFS)", "P1 turnaround time, ms (round robin)", "content"),
    ("marks allocated to part (a)", "marks allocated to part (c)", "part labels"),
])
def test_glosses_of_different_quantities_still_stay_apart(a, b, why):
    found = gloss_difference(a, b)
    assert found is not None and why in found, found


def test_a_non_compound_is_still_read_as_a_negation_by_the_reading():
    r = gloss_reading("false positives (non-aluminium flagged), count")
    assert r.negated and not r.plain_negated and "aluminium" in r.non_of


# ------------------------------------------------------------------------------------------ major: the from-memory label

def _report(text: str, *, agent: str = "business-management-specialist", subject: str = "Business Management", claims=None) -> SpecialistReport:
    ids = dict(request_id="req", task_id="t", report_id=f"rep-{agent}", agent_id=agent, subject=subject, task_type="structured_question")
    claims = claims or [dict(claim_id="g1.1", claim_text=text, claim_role="point", materiality="material")]
    return SpecialistReport.model_validate(dict(ids, original_response=text, response_sha256=sha256_text(text), created_at="2026-11-15T09:00:00Z",
                                                claims=[dict(ids, **c) for c in claims]))


def _synthesis(claims: list[SynthesizedClaim], reports) -> Synthesis:
    text = " ".join(c.text for c in claims)
    return Synthesis(synthesis_id="syn", request_id="req", task_id="t", combinator_agent_id="dummy-combinator", source_report_ids=[r.report_id for r in reports],
                     claims=claims, ledger=[], text=text, text_sha256=sha256_text(text), created_at="2026-11-15T09:00:00Z")


def test_x12_a_note_about_declined_figures_labels_no_case_figure_from_memory():
    """Exchange x12 (a gross profit margin worked from the supplied case beside a one-line LEGO decline): the decline's note 'so any
    number I gave would be unverified' is no from-memory label of the case figures carried word for word."""
    item = C3["exchanges"]["specialists"]["x12"]
    hub, _ch, reply, _rc = deliver_exchange("x12")
    hub.close()
    rep = SpecialistReport.model_validate(reply.payload)
    by_text = {c.claim_text: c.claim_id for c in rep.claims}
    gross = next(cid for t, cid in by_text.items() if t.startswith("Gross profit = "))
    margin = next(cid for t, cid in by_text.items() if t.startswith("Gross profit margin"))
    claims = [SynthesizedClaim(claim_id=f"s{i}", text=t, certainty="established", source_claim_ids=[by_text_id], transformation="carried")
              for i, (t, by_text_id) in enumerate([(next(t for t in by_text if t.startswith("Gross profit = ")), gross),
                                                    (next(t for t in by_text if t.startswith("Gross profit margin")), margin)])]
    f = L.check_synthesis_ledger([rep], _synthesis(claims, [rep]))
    assert "INT-LEDGER-027" not in codes(f), [x.message[:200] for x in f if x.code == "INT-LEDGER-027"]
    assert "unverified" in item["response_text"]
    # control: a note that labels the report's figures from memory still applies
    noted = _report("Option 1 costs $2,400,000. Figures quoted from memory.", claims=[
        dict(claim_id="g1.1", claim_text="Option 1 costs $2,400,000.", claim_role="point", materiality="material"),
        dict(claim_id="g1.2", claim_text="Figures quoted from memory.", claim_role="other", materiality="supporting")])
    f = L.check_synthesis_ledger([noted], _synthesis([SynthesizedClaim(claim_id="s0", text="Option 1 costs $2,400,000.", certainty="established",
                                                                       source_claim_ids=["g1.1"], transformation="carried")], [noted]))
    hit = [x for x in f if x.code == "INT-LEDGER-027"]
    assert hit and "['2400000']" in hit[0].message  # the label number of 'Option 1' is no quantified item


@pytest.mark.parametrize("note,labels", [
    ("None of these figures is in the case, and I have no source for them in this session, so any number I gave would be unverified.", False),
    ("I have no approved source for their death tolls, so I have left those figures out rather than give them from memory.", False),
    ("Dates and figures here are from memory; check them against your notes.", True),
    ("(from memory, to be checked)", True),
])
def test_which_notes_label_the_reports_figures_from_memory(note, labels):
    assert L.labels_report_figures_from_memory(note) is labels


# ------------------------------------------------------------------------------------------ major: a credit to the wrong specialist

def test_p10c_exchange_a_calculation_credited_to_the_wrong_specialist_is_named():
    """The communication-fidelity lens's p10c exchange synthesis: 'The Geography specialist calculated that one bus releases 0.2444 t
    of CO2 per day.' cites the Chemistry report's s4.7; the faithful credit 'The Chemistry specialist calculated ...' is unchanged."""
    hub, _ch, reply_ch, _rc = deliver_exchange("ch-p10c")
    hub.close()
    hub, _ch, reply_ge, _rc = deliver_exchange("ge-p10c")
    hub.close()
    ch = SpecialistReport.model_validate(reply_ch.payload)
    ge = SpecialistReport.model_validate(reply_ge.payload)
    ids = {c.claim_id.split("@")[0]: c.claim_id for c in ch.claims}
    doc = C3["exchanges"]["syntheses"]["ge-p10c"]
    wrong = next(c for c in doc["claims"] if c["text"].startswith("The Geography specialist calculated"))
    right = next(c for c in doc["claims"] if c["text"].startswith("The Chemistry specialist calculated"))
    claims = [SynthesizedClaim(claim_id="s3", text=wrong["text"], certainty="established", source_claim_ids=[ids[s.split("@")[0]] for s in wrong["source_claim_ids"]],
                               transformation="paraphrased"),
              SynthesizedClaim(claim_id="s1", text=right["text"], certainty="established", source_claim_ids=[ids[s.split("@")[0]] for s in right["source_claim_ids"]],
                               transformation="merged")]
    f = L.check_synthesis_ledger([ch, ge], _synthesis(claims, [ch, ge]))
    credit = [x for x in f if x.code == "INT-LEDGER-026" and "a view credited to another agent" in x.message]
    assert [x.claim_ids[0] for x in credit] == ["s3"] and "geography-specialist" in credit[0].message and "chemistry-specialist" in credit[0].message


# ------------------------------------------------------------------------------------------ major: Spanish counts are figures

def _sp_report(text: str) -> SpecialistReport:
    return _report(text, agent="language-b-spanish-specialist", subject="Language B: Spanish")


@pytest.mark.parametrize("transformation", ["carried", "paraphrased"])
@pytest.mark.parametrize("source,changed", [
    ("Volviste hace dos semanas y ya echas de menos el pueblo.", "Volviste hace tres semanas y ya echas de menos el pueblo."),
    ("Tengo dos hermanos y una hermana.", "Tengo cuatro hermanos y una hermana."),
])
def test_a_spanish_count_changed_by_the_combinator_is_int_ledger_023_whatever_the_label(transformation, source, changed):
    rep = _sp_report(source)
    s = _synthesis([SynthesizedClaim(claim_id="s0", text=changed, certainty="established", source_claim_ids=["g1.1"], transformation=transformation)], [rep])
    assert "INT-LEDGER-023" in codes(L.check_synthesis_ledger([rep], s))
    faithful = _synthesis([SynthesizedClaim(claim_id="s0", text=source, certainty="established", source_claim_ids=["g1.1"], transformation=transformation)], [rep])
    assert "INT-LEDGER-023" not in codes(L.check_synthesis_ledger([rep], faithful))


@pytest.mark.parametrize("synthesized", ["The student came back two weeks ago.", "Mis dos hermanos viven aqui.", "Volviste hace dos semanas."])
def test_control_a_faithful_count_or_a_count_after_a_determiner_draws_no_figure_finding(synthesized):
    rep = _sp_report("Volviste hace dos semanas. Mis dos hermanos viven aqui.")
    s = _synthesis([SynthesizedClaim(claim_id="s0", text=synthesized, certainty="established", source_claim_ids=["g1.1"], transformation="paraphrased")], [rep])
    assert "INT-LEDGER-023" not in codes(L.check_synthesis_ledger([rep], s))


# ------------------------------------------------------------------------------------------ minor: a verbatim carry credits nothing new

def test_x13_and_en_t16_a_claim_carried_word_for_word_is_charged_no_credit():
    hub, _ch, reply, _rc = deliver_exchange("x13")
    hub.close()
    rep = SpecialistReport.model_validate(reply.payload)
    src = next(c for c in rep.claims if c.claim_text.startswith("The narrator notes that"))
    s = _synthesis([SynthesizedClaim(claim_id="s0", text=src.claim_text, certainty="established", source_claim_ids=[src.claim_id], transformation="carried")], [rep])
    assert "INT-LEDGER-026" not in codes(L.check_synthesis_ledger([rep], s))
    # control: the same credit added by the synthesis to a claim that does not make it is still named
    plain = next(c for c in rep.claims if c.claim_text.startswith("The auctioneer's speech"))
    s = _synthesis([SynthesizedClaim(claim_id="s0", text="The narrator states that the auctioneer's speech turns the sale into a performance.",
                                     certainty="established", source_claim_ids=[plain.claim_id], transformation="paraphrased")], [rep])
    assert "INT-LEDGER-026" in codes(L.check_synthesis_ledger([rep], s))


def test_a_numbered_diagram_no_supplied_document_carries_is_the_answers_own():
    """ec-t16 s20 ('As Diagram 1 shows, ...'): Diagram 1 is the answer's own diagram, never the supplied text doc-pelland."""
    item = C3["c3"]["specialists"]["ec-t16"]
    assert "Diagram 1" not in item["supplied_texts"][0]["text"]
    text = "As Diagram 1 shows, each boat fishes until price equals its marginal private cost, so the catch exceeds the social optimum."
    rep = _report("Each boat fishes until price equals its marginal private cost, so the catch exceeds the social optimum.", agent="economics-specialist",
                  subject="Economics")
    docs = [SuppliedText(**{k: v for k, v in t.items() if k in ("document_id", "title", "author", "text")}) for t in item["supplied_texts"]]
    rep = rep.model_copy(update={"supplied_texts": docs})
    s = _synthesis([SynthesizedClaim(claim_id="s20", text=text, certainty="established", source_claim_ids=["g1.1"], transformation="paraphrased")], [rep])
    assert not [x for x in L.check_synthesis_ledger([rep], s) if x.code == "INT-LEDGER-026" and "Diagram 1" in x.message]


# ------------------------------------------------------------------------------------------ the readers of this pass are linear

def _entries(text: str):
    yield "gloss_difference", lambda: gloss_difference(text, "f(-3) = 3 + 6 - 9 from the cubic, ms")
    yield "gloss_reading", lambda: gloss_reading(text)
    yield "claim_local_gloss", lambda: claim_local_gloss(text)
    yield "labels_report_figures_from_memory", lambda: L.labels_report_figures_from_memory(text)
    yield "carried_verbatim", lambda: L.carried_verbatim(text, [])
    yield "_work_credits", lambda: L._work_credits(text, ["chemistry-specialist", "geography-specialist"])
    yield "_without_label_numbers", lambda: L._without_label_numbers(text)
    yield "_count_figures", lambda: L._read_count_figures(text)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_c3_integrity_readers(shape):
    """The readers this pass added or extended, fed the standard hostile inputs (``tests/core_hostile.py``)."""
    assert not sweep(_entries, texts=one(shape))
