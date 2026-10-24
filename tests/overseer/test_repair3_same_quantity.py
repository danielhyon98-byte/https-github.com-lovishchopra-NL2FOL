"""The third repair of the translator merge (design decision 55): rules same-quantity, frequency-words, data-standing and
engine-shown, each pinned with its controls.

Finding (b) of the review of the second repair: rule figure-transcription took a ``task_setting`` or ``supplied_text``
premise with no excerpt as a transcription whenever its numbers occurred anywhere in the request, so the claim's own
count assumed beside an 80-word limit, or the claim's result beside a "show that" target, cleared a circular encoding.
The rule is withdrawn: no grounding label and no number match is evidence on its own, so a premise with no located
excerpt is never a transcription, and the request (or a document supplied with it) can only REFUTE it: a figure it
states nowhere, only as a target the answer must derive, only for another quantity than the premise names, or only as a
bound the premise states as a value (rule same-quantity; "compounded monthly" states 12, rule frequency-words).

Findings (c) and (d): the adjudicated faults of record version 4 showed only that a data conjunct needs its data premise.
Rule engine-shown grades a delivered restatement by what the engine SHOWS: OVS-TRN-006 only when the result rests on a
restating premise a deterministic check shows is not data (rule data-standing); a result that rests only on premises
presented as data that no check verifies or refutes is OVS-TRN-011, a warning that leaves an agent's
``translation_circular`` accusation unresolved (a meaning question), whatever the receipt says of the premise.

No model is called; translations come from the translator's own pipeline with the fixture provider.
"""
from __future__ import annotations

from fractions import Fraction
from typing import Optional

import pytest

from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.translate.contracts import SuppliedText
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from .conftest import CFG, DOC, EN_TEXT, KEY, english_report, make_auditor, make_plan, new_channel
from .test_protocol_validate import review
from .test_translation_agents import outcome_of, tr_acc
from .test_translation_oversight import INFER, POINT, V, point_claims, proposal, run, trn


def _count_problem(grounding: dict, value: str = "80", *, label: str = "the point", meaning: str = "the count the point states") -> dict:
    """The point's own count ``n = <value>`` assumed by a premise grounded ``grounding`` (the reviewer's probe)."""
    c = {"op": "eq", "left": V("n"), "right": {"op": "int", "value": value}}
    return {"problem_id": "p-x", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
            "symbols": [{"name": "n", "sort": "Int", "meaning": meaning}],
            "premises": [{"id": "P_assumed", "expr": c, "label": label, "grounding": grounding}],
            "conclusion": {"id": "C", "expr": c, "label": label}}


def _run_on(user_input: str, problem: dict, *, docs=(DOC,), report=None, auditor=None):
    """One request with ``user_input`` and the texts ``docs``, and the structured report whose point is translated as
    ``problem`` by the pipeline (the fixture provider) and verified by the engine inside the channel call."""
    aud = auditor or make_auditor(shadow="off")
    ch = new_channel(aud, make_plan(allowed_document_ids=[d.document_id for d in docs] + ["peer:en"]))
    translator = Translator(FixtureTranslationProvider({POINT: proposal(problem)}))

    def fn(claim, rep):
        return verify_claim(claim, rep, translator, config=CFG, signing_key=KEY, key_id="t") if claim.claim_id == POINT else None

    ch.channel.verify_claim_fn = fn
    m, _req, _rq = ch.request("router", "english-specialist", user_input, list(docs))
    _reply, rc = ch.respond(m.message_id, report or english_report(claims=point_claims(), docs=tuple(docs)))
    assert rc.status is not TransmissionStatus.REJECTED
    return aud, ch, rc


# ============================================================================================ rule same-quantity: targets
@pytest.mark.parametrize("text, targets", [
    ("Show that the distance travelled in 0 <= t <= 3 is 8 m.", ["8 m"]),
    ("Show that 36 g of water is 2.0 mol (M = 18 g mol⁻¹).", ["2.0 mol "]),         # data written beside the target is not the target
    ("Verify that x = 5. Then find y.", ["5"]),
    ("Prove that the extract names 2 measures of time", [" the extract names 2 measures of time"]),  # no copula: the whole clause
    ("Find the distance travelled in 8 s.", []),
])
def test_rule_same_quantity_reads_the_target_of_a_show_that_and_leaves_out_data_written_beside_it(text, targets):
    assert [text[a:b].strip(" ") for a, b in T.target_spans(text)] == [t.strip(" ") for t in targets]


# ============================================================================================ rule same-quantity: refutation
REQUEST_80 = "Analyse how the writer presents work in the extract. Use quotations from the extract. Write no more than 80 words."


@pytest.mark.parametrize("value, texts, statement, relations, why", [
    # F1: stated nowhere
    (81, [REQUEST_80], "the point ; the count the point states", {"eq"}, "stated nowhere in the request"),
    # F2: only as the target the answer must derive
    (8, ["Show that the distance travelled in 0 <= t <= 3 is 8 m."], "the distance is 8 m ; distance travelled in metres", {"eq"},
     "only as the target the answer must derive"),
    (2, ["Analyse the extract. Show that the extract names 2 measures of time."], "the extract names 2 measures of time", {"eq"},
     "only as the target the answer must derive"),
    # F3: only for another quantity than the premise's own statement names
    (80, [REQUEST_80], "the point ; the count the point states", {"eq"}, "only as 80 words"),
    (8, ["A particle moves for 8 seconds. Find the distance travelled."], "the distance is 8 m ; distance travelled in metres", {"eq"}, "only as 8 seconds"),
    # F4: only as a bound, while the premise states the value of its quantity and names no bound
    (80, [REQUEST_80], "the paragraph has 80 words ; the number of words of the paragraph", {"eq"}, "only as a bound ('no more than 80')"),
])
def test_rule_same_quantity_refutes_a_figure_the_request_states_nowhere_only_as_a_target_for_another_quantity_or_as_a_bound(value, texts, statement,
                                                                                                                         relations, why):
    got = T.figure_refutation(Fraction(value), texts, statement, relations)
    assert got is not None and why in got and T.SAME_QUANTITY_RULE in got, got


@pytest.mark.parametrize("value, texts, statement, relations", [
    (12, ["Write about the hours: 12 hours a day."], "the claim restated ; the hours the claim states", {"eq"}),  # the same quantity, named in words
    (12, ["Write about the hours: 12 hours a day."], "the children worked 12 hours a day", {"eq"}),           # the same quantity, with the figure
    (80, [REQUEST_80], "the word limit is 80 words", {"eq"}),                                                  # the premise names the bound
    (80, [REQUEST_80], "the paragraph has at most 80 words", {"le"}),                                          # the premise states a bound itself
    # (not refuted; since the fifth repair, decision 57, not read either: "Write no more than 80 words" only requires the
    # paragraph's count, rule statement-context, test_repair5_statement_context.py)
    (8, ["A particle moves 8 m in 2 s."], "the distance in m", {"eq"}),                                        # a one-letter unit after "in"
    (5, ["Use the 5 given values."], "", {"eq"}),                                                              # a statement naming nothing: no quantity to compare
    (1, ["Write about the mill."], "the count", {"eq"}),                                                       # 0 and 1 are structural, never refuted
])
def test_control_rule_same_quantity_does_not_refute_the_requests_statement_of_the_quantity_the_premise_names(value, texts, statement, relations):
    """The request can only refute: where it states the figure for the quantity the premise names (in its words, with the
    figure, or with a bound the premise names too), or where the premise names no quantity at all, nothing is refuted,
    and nothing is VERIFIED either (the standing is undecided: below; or, since the fifth repair, uncheckable where the
    request states the figure only as a requirement the premise does not name, rule statement-context)."""
    assert T.figure_refutation(Fraction(value), texts, statement, relations) is None


def test_rule_same_quantity_compares_units_by_their_physical_dimension():
    assert T.same_quantity_marker("m", "metres") and T.same_quantity_marker("cm3", "cm³") and T.same_quantity_marker("hours", "hour")
    assert not T.same_quantity_marker("s", "m") and not T.same_quantity_marker("words", "point") and not T.same_quantity_marker(None, "m")


# ============================================================================================ rule frequency-words
QUESTION = "A sum of 2000 euros is invested for 5 years at a nominal annual rate of 3.6%, compounded monthly. (a) Find its value, to the nearest euro."


@pytest.mark.parametrize("text, value", [("compounded monthly", 12), ("paid quarterly", 4), ("billed weekly", 52), ("reviewed annually", 1),
                                         ("interest added semi-annually", 2), ("a fortnightly wage", 26)])
def test_rule_frequency_words_reads_a_frequency_adverb_as_its_periods_a_year(text, value):
    assert Fraction(value) in T.text_numbers(text)


@pytest.mark.parametrize("statement", ["the number of compounding periods a year", "interest is compounded monthly (12 periods a year)",
                                       "12 times a year"])
def test_rule_frequency_words_12_for_monthly_is_the_requests_statement_of_the_periods_a_year(statement):
    """The second repair's reading was too strict on 12 for "monthly" (finding (d)): the request states 12 periods a year
    in the word "monthly", so a premise stating 12 for that quantity is not refuted (undecided, never verified)."""
    assert T.figure_refutation(Fraction(12), [QUESTION], statement, {"eq"}) is None


def test_control_rule_frequency_words_12_for_another_quantity_is_refuted():
    got = T.figure_refutation(Fraction(12), [QUESTION], "the number of words the answer uses", {"eq"})
    assert got is not None and "12 periods a year (a frequency word)" in got


# ============================================================================================ rule data-standing
def _restated(grounding: dict, *, symbol_grounding: Optional[dict] = None, conclusion_grounding: Optional[dict] = None, sort: str = "Bool") -> Problem:
    """A Bool (or Int) symbol ``x`` restated by premise P under ``grounding``; the symbol and the conclusion grounded as given."""
    expr = V("x") if sort == "Bool" else {"op": "eq", "left": V("x"), "right": {"op": "int", "value": "12"}}
    sym = {"name": "x", "sort": sort, "meaning": "the hours the children worked" if sort != "Bool" else "the question asks for the value"}
    if symbol_grounding is not None:
        sym["grounding"] = symbol_grounding
    concl = {"id": "C", "expr": expr, "label": "the claim"}
    if conclusion_grounding is not None:
        concl["grounding"] = conclusion_grounding
    return Problem.model_validate({"problem_id": "p", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment", "symbols": [sym],
                                   "premises": [{"id": "P", "expr": expr, "label": "the claim restated", "grounding": grounding}], "conclusion": concl})


TS = {"kind": "task_setting"}


@pytest.mark.parametrize("problem, standing, why", [
    # Boolean content no check reads against a source. The fourth repair (decision 56): declared as data throughout it is
    # still the writer's own, shown not to be data on the label alone (uncheckable); this case asserted "undecided", the
    # fault the review of the third repair found (p proves p graded OVS-TRN-011 on labels alone). Its reason is kept.
    (_restated(TS, symbol_grounding=TS, conclusion_grounding=TS), "uncheckable", "declares as data throughout"),
    (_restated(TS, symbol_grounding=INFER, conclusion_grounding=TS), "refuted", "declares x the writer's own"),
    (_restated(TS, symbol_grounding=None, conclusion_grounding=TS), "refuted", "does not ground as data"),
    (_restated(TS, symbol_grounding=TS, conclusion_grounding=INFER), "refuted", "as the writer's own (specialist_inference)"),
    (_restated(TS, symbol_grounding=TS, conclusion_grounding=None), "refuted", "nowhere (no grounding)"),
    # a figure: the symbol's own declaration, else the request's statement of the quantity (rule same-quantity)
    (_restated(TS, symbol_grounding={"kind": "assumption"}, sort="Int"), "refuted", "declares x the writer's own"),
    (_restated(TS, sort="Int"), "undecided", "a number match is no evidence"),
])
def test_rule_data_standing_reads_the_translations_own_declarations_only_toward_the_writers_own(problem, standing, why):
    """Rule data-standing reads the translation's own declarations only toward the writer's own: each Boolean case is
    shown not to be data (refuted by a declaration, or, declared as data throughout, uncheckable: decision 56, rewritten
    from "undecided" with every other assertion kept), and the figure the request states for its quantity stays undecided."""
    rs = T.restatement(problem, english_report(), ["Find the value. The children worked 12 hours a day."])
    assert rs.holds and rs.own == ("P",) and rs.grounded == () and rs.standings == (("P", standing),)
    assert why in dict(rs.why_own)["P"], rs.why_own
    assert (rs.shown, rs.undecided) == ((("P",), ()) if standing != "undecided" else ((), ("P",)))
    if standing == "uncheckable":
        assert "no deterministic check reads Boolean content" in dict(rs.why_own)["P"] and "the kind label is then the only evidence" in dict(rs.why_own)["P"]


def test_rule_same_quantity_a_located_excerpt_that_states_the_figure_only_as_a_target_is_refuted():
    """A quotation whose excerpt the grounding check locates and verifies is no transcription when the excerpt states the
    premise's figure only inside a "show that" target of its document: the target is what the answer must derive.
    Control: the same figure stated as data in the document is a transcription."""
    target = SuppliedText(document_id="doc-q", title="Question", author="Board", text="A particle starts at rest. Show that the distance travelled is 8 m.")
    data = SuppliedText(document_id="doc-q", title="Question", author="Board", text="A particle travels a distance of 8 m in 2 s.")
    c = {"op": "eq", "left": V("d"), "right": {"op": "int", "value": "8"}}
    for doc, excerpt, standing in ((target, "the distance travelled is 8 m", "refuted"), (data, "a distance of 8 m", "transcription")):
        prob = Problem.model_validate({"problem_id": "p", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
                                       "symbols": [{"name": "d", "sort": "Int", "meaning": "the distance in metres"}],
                                       "premises": [{"id": "P", "expr": c, "label": "the distance is 8 m",
                                                     "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-q", "excerpt": excerpt}]}}],
                                       "conclusion": {"id": "C", "expr": c, "label": "the distance"}})
        rep = english_report(EN_TEXT + " The distance is 8 m.", docs=(DOC, doc))
        rs = T.restatement(prob, rep, [])
        assert rs.standings == (("P", standing),), (standing, rs.why_own)
        if standing == "refuted":
            assert rs.holds and "only as the target the answer must derive" in dict(rs.why_own)["P"]
        else:
            assert not rs.holds and rs.grounded == ("P",)


# ============================================================================================ rule engine-shown
def _follows(entailed_without: set[tuple[str, ...]]):
    return lambda pids: tuple(sorted(pids)) in entailed_without


@pytest.mark.parametrize("rs, partial, entailed_without, grade", [
    # the run without every graded premise still gives ENTAILED: redundant (a coverage note for a part restated)
    (T.Restatement(holds=True, own=("A", "B"), shown=("A",), undecided=("B",)), False, {("A", "B"), ("A",)}, [("OVS-TRN-010", ["A", "B"], ["A", "B"])]),
    (T.Restatement(partial_own=("A",), shown=("A",)), True, {("A",)}, [("note:redundant", ["A"], ["A"])]),
    # the result rests on a premise shown not to be data: circular
    (T.Restatement(holds=True, own=("A", "B"), shown=("A",), undecided=("B",)), False, set(), [("OVS-TRN-006", ["A"], ["A"])]),
    # the shown premise adds nothing beside the undecided one, on which the result rests: OVS-TRN-010 and OVS-TRN-011
    (T.Restatement(holds=True, own=("A", "B"), shown=("A",), undecided=("B",)), False, {("A",)},
     [("OVS-TRN-010", ["A"], ["A"]), ("OVS-TRN-011", ["B"], ["A", "B"])]),
    (T.Restatement(partial_own=("A", "B"), shown=("A",), undecided=("B",)), True, {("A",)},
     [("note:redundant", ["A"], ["A"]), ("OVS-TRN-011", ["B"], ["A", "B"])]),
    # only undecided premises, the result resting on them: a data conjunct needs its data premise, OVS-TRN-011
    (T.Restatement(holds=True, own=("B",), undecided=("B",), undecided_disclosed=("B",)), False, set(), [("OVS-TRN-011", ["B"], ["B"])]),
    # nothing graded: no restatement, or a part restated under a non-ENTAILED result
    (T.Restatement(), False, set(), []),
    (T.Restatement(partial_own=("A",), shown=("A",)), False, set(), []),
])
def test_rule_engine_shown_grades_a_restatement_by_what_the_engine_shows(rs, partial, entailed_without, grade):
    assert T.engine_shown_grade(rs, partial, _follows(entailed_without)) == grade
    assert T.engine_shown_codes(rs, partial, _follows(entailed_without)) == sorted({d for d, _n, _r in grade if d.startswith("OVS-")})


# ============================================================================================ the reviewer's probes, end to end
@pytest.mark.parametrize("value, report_text, why", [
    ("80", None, "only as 80 words"),                        # the request states 80 only as its word limit
    ("81", None, "stated nowhere in the request"),
    ("80", EN_TEXT + " The paragraph keeps to 80 words.", "only as 80 words"),  # the report stating the count changes nothing
])
def test_the_claims_own_count_beside_the_word_limit_is_trn_006_and_the_transfer_fails(value, report_text, why):
    """Finding (b), the reviewer's probe: the point's own count assumed under a task_setting label (no excerpt). The merged
    translator delivers it (its rule reads the label as a transcription) and the engine gives ENTAILED; the request
    states 80 only as a word limit, a quantity the premise does not name (rule same-quantity), so a check SHOWS the
    premise is not data: OVS-TRN-006, AUDIT_FAILED. Under the withdrawn rule figure-transcription it was a transcription."""
    rep = english_report(report_text, claims=point_claims()) if report_text else None
    aud, ch, rc = run({POINT: proposal(_count_problem({"kind": "task_setting"}, value))}, report=rep)
    try:
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.translation.status.value == "TRANSLATED" and o.verification.status.value == "ENTAILED" and o.display_status.value == "ENTAILED"
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-006")
        assert f.severity == "error" and "P_assumed" in f.message and why in f.message and "engine-shown" in f.message, f.message
        assert trn(a, "OVS-TRN-011") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()


@pytest.mark.parametrize("request_text, why", [
    ("Show that the distance travelled in 0 <= t <= 3 is 8 m.", "only as the target the answer must derive"),
    ("A particle moves for 8 seconds. Find the distance travelled.", "only as 8 seconds"),
    ("Find the distance travelled.", "stated nowhere in the request"),
])
def test_a_show_that_target_another_quantity_or_no_figure_never_verifies_the_claims_result(request_text, why):
    """Finding (b), the reviewer's second probe: the claim's derived result (the distance is 8 m) assumed under a
    task_setting label. Neither a "show that" target nor a figure for another quantity is the request's statement of
    the premise's quantity: each is the writer's own, SHOWN not to be data (refuted)."""
    c = {"op": "eq", "left": V("s5_1_d"), "right": {"op": "int", "value": "8"}}
    p = Problem.model_validate({"problem_id": "p", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
                                "symbols": [{"name": "s5_1_d", "sort": "Int", "meaning": "distance travelled in metres"}],
                                "premises": [{"id": "t_target", "expr": c, "label": "the distance is 8 m", "grounding": {"kind": "task_setting"}}],
                                "conclusion": {"id": "C", "expr": c, "label": "distance = 8 m (the student's derived result)"}})
    rs = T.restatement(p, english_report(), [request_text])
    assert rs.holds and rs.own == ("t_target",) and rs.standings == (("t_target", "refuted"),) and why in dict(rs.why_own)["t_target"]


HOURS_INPUT = "The children worked 12 hours a day in the mill. Analyse how the writer presents work in the extract."


def _hours_problem(grounding: dict) -> dict:
    c = {"op": "eq", "left": V("hours"), "right": {"op": "int", "value": "12"}}
    return {"problem_id": "p-h", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
            "symbols": [{"name": "hours", "sort": "Int", "meaning": "the hours a day the children worked"}],
            "premises": [{"id": "P_hours", "expr": c, "label": "the children worked 12 hours a day", "grounding": grounding}],
            "conclusion": {"id": "C", "expr": c, "label": "the children worked 12 hours a day"}}


def test_a_restatement_of_task_data_for_the_same_quantity_is_trn_011_and_an_accusation_of_it_stays_unresolved():
    """Findings (c) and (d): the result rests only on a task_setting premise stating the request's own figure for the
    quantity it names. No check verifies it (no excerpt: a number match is no evidence) and none refutes it, so the
    engine shows only that a data conjunct needs its data premise: OVS-TRN-011, a warning (the transfer passes with
    findings), and an agent's translation_circular accusation is neither confirmed nor refuted (OVS-AGENT-004, human
    review). Control: the request without the figure refutes the premise (stated nowhere): OVS-TRN-006, AUDIT_FAILED,
    the accusation confirmed."""
    aud, ch, rc = _run_on(HOURS_INPUT, _hours_problem({"kind": "task_setting"}))
    try:
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-011")
        assert f.severity == "warning" and f.claim_ids == [POINT] and "P_hours" in f.message and "a data conjunct needs its data premise" in f.message
        assert "the receipt presents P_hours as given with the task" in f.message and f.related_result_ids
        assert trn(a, "OVS-TRN-006") == [] and trn(a, "OVS-TRN-010") == [] and a.transfer_states[rc.message_id] == "AUDIT_PASSED_WITH_FINDINGS"
        r = review(aud, ch.uid)
        o = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
        assert o.outcome == "unresolved" and o.code == "OVS-AGENT-004", (o.outcome, o.code)
    finally:
        aud.close()
    aud2, ch2, rc2 = _run_on("Analyse how the writer presents work in the extract.", _hours_problem({"kind": "task_setting"}))
    try:
        a2 = aud2.audit(ch2.uid)
        (f2,) = trn(a2, "OVS-TRN-006")
        assert "stated nowhere in the request" in f2.message and a2.transfer_states[rc2.message_id] == "AUDIT_FAILED"
        r2 = review(aud2, ch2.uid)
        o2 = outcome_of(r2.run([tr_acc(r2.dossier, "translation_circular")]))
        assert o2.outcome == "confirmed" and [c.code for c in o2.confirming] == ["OVS-TRN-006"]
    finally:
        aud2.close()


ROTA = SuppliedText(document_id="doc-rota", title="Rota", author="Mill office", text="Rota of 1830: the children's shift ran 12 hours a day.")


def test_a_restatement_under_a_supplied_text_the_receipt_discloses_is_trn_011_and_an_accusation_of_it_is_never_refuted():
    """The class the validator had wrong: a supplied_text premise with no excerpt naming a document supplied with the
    request, restating the whole conclusion. The receipt lists it among the result's unverified dependencies, but no
    check decides whether the document states it, so a coverage note alone would have let the validator REFUTE an
    agent's correct translation_circular accusation. It is OVS-TRN-011 too, and the accusation stays unresolved.
    Control: the same premise naming a document the request does not supply names no source a check could read
    (uncheckable, shown not to be data): OVS-TRN-006, the accusation confirmed."""
    aud, ch, rc = _run_on(HOURS_INPUT, _hours_problem({"kind": "supplied_text", "source_refs": [{"document_id": "doc-rota"}]}), docs=(DOC, ROTA))
    try:
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert "P_hours" in o.verification.unverified_dependencies and o.display_status.value == "ENTAILED"
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-011")
        assert "the receipt lists P_hours among the result's unverified dependencies" in f.message and trn(a, "OVS-TRN-006") == []
        r = review(aud, ch.uid)
        acc = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
        assert acc.outcome == "unresolved" and acc.code == "OVS-AGENT-004"
    finally:
        aud.close()
    aud2, ch2, rc2 = _run_on(HOURS_INPUT, _hours_problem({"kind": "supplied_text", "source_refs": [{"document_id": "doc-none"}]}), docs=(DOC, ROTA))
    try:
        a2 = aud2.audit(ch2.uid)
        (f2,) = trn(a2, "OVS-TRN-006")
        assert "which is not among the texts supplied with the request" in f2.message
        r2 = review(aud2, ch2.uid)
        o2 = outcome_of(r2.run([tr_acc(r2.dossier, "translation_circular")]))
        assert o2.outcome == "confirmed"
    finally:
        aud2.close()


def test_the_withdrawn_rule_is_named_for_the_record_and_verifies_nothing():
    """Rule figure-transcription is withdrawn: its name is kept for the record, and no code path reads a no-excerpt premise
    as a transcription (every standing of such a premise is one of the four that are not)."""
    assert T.FIGURE_RULE == "figure-transcription" and T.FIGURE_RULE not in T.STANDINGS
    for value in ("12", "13"):
        for request in (["Write about the hours: 12 hours a day."], []):
            rs = T.restatement(_restated(TS, sort="Int") if value == "12" else Problem.model_validate(_count_problem(TS, value)), english_report(), request)
            assert rs.standings and all(kind != T.TRANSCRIPTION for _pid, kind in rs.standings), rs.standings


# ============================================================================================ rule unaligned-polarity (the ledger)
from epinoic_logic.integrity.ledger import meaning_differences  # noqa: E402

SRC_VERB = 'The verb "assembled", with the reflexive "itself", gives the town the action, so the place she left seems to build itself out of the mist.'
SRC_NEG = "The poem never names the town, so the place she left stays nameless."


@pytest.mark.parametrize("synthesized, sources, label, said", [
    # a negation added where no cited source states one, though no statement aligns with a source statement
    ("The bruise comparison has no 'like' or 'as', so it is a metaphor.", [SRC_VERB], "paraphrased", "it adds a negation its cited sources do not state"),
    ("The bruise comparison has no 'like' or 'as', so it is a metaphor.", [SRC_VERB], "carried", "it adds a negation its cited sources do not state"),
    # a negation dropped where the cited sources state one
    ("The bruise comparison is a metaphor for hurt that is healing.", [SRC_NEG], "paraphrased", "it drops the negation its cited sources state"),
])
def test_rule_unaligned_polarity_a_negation_added_or_dropped_under_an_equivalence_label_is_a_changed_meaning(synthesized, sources, label, said):
    """The third repair restored the overseer branch's polarity reading beside the merged ledger's aligned comparison (the
    staged rewrite had pinned its loss): a claim labelled 'carried' or 'paraphrased' promises its sources' content
    unchanged, so a negation it adds or drops against them is the INT-LEDGER-026 warning even when no statement aligns."""
    assert said in meaning_differences(synthesized, sources, label)


@pytest.mark.parametrize("synthesized, sources, label", [
    ("The bruise comparison is a metaphor for hurt that is healing.", [SRC_VERB], "paraphrased"),   # neither states a negation
    ("The bruise comparison has no 'like' or 'as', so it is not a simile.", [SRC_NEG], "paraphrased"),  # both state one
    ("The bruise comparison has no 'like' or 'as', so it is a metaphor.", [SRC_VERB], "interpreted"),  # not an equivalence label
    ("The bruise comparison has no 'like' or 'as', so it is a metaphor.", [], "paraphrased"),        # nothing cited to compare
])
def test_control_rule_unaligned_polarity_reads_only_a_polarity_change_under_an_equivalence_label(synthesized, sources, label):
    assert not [d for d in meaning_differences(synthesized, sources, label) if "negation" in d]


def test_rule_unaligned_polarity_never_repeats_what_the_aligned_comparison_says():
    """A statement copied from a cited source with a negation added is the aligned comparison's finding; the unaligned
    rule adds nothing beside it (one fault, one description)."""
    said = meaning_differences("The place she left does not seem to build itself out of the mist.", [SRC_VERB], "paraphrased")
    assert sum("negation" in d for d in said) == 1, said


# ============================================================================================ evidence first in a grade's message
FIVE_INPUT = ("The mill ran for 5 years, with 12 shifts a week, 3 overseers, 7 looms and 9 rooms. "
              "Analyse how the writer presents work in the extract.")
FIVE = (("years", "5", "the years the mill ran"), ("shifts", "12", "the shifts a week"), ("overseers", "3", "the overseers"),
        ("looms", "7", "the looms"), ("rooms", "9", "the rooms"))


def _five_problem() -> dict:
    """The conclusion's five figures, each restated by its own task_setting premise with no excerpt (the shape of the
    recorded r7 task m1.1, whose five premises' reasons once pushed the signed run and the rule past the message cap)."""
    eqs = {n: {"op": "eq", "left": V(n), "right": {"op": "int", "value": v}} for n, v, _m in FIVE}
    return {"problem_id": "p-5", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment",
            "symbols": [{"name": n, "sort": "Int", "meaning": m} for n, _v, m in FIVE],
            "premises": [{"id": f"P_{n}", "expr": eqs[n], "label": f"the mill had {v} {n}", "grounding": {"kind": "task_setting"}} for n, v, _m in FIVE],
            "conclusion": {"id": "C", "expr": {"op": "and", "args": [eqs[n] for n, _v, _m in FIVE]}, "label": "the mill's figures"}}


@pytest.mark.parametrize("user_input, code, says, label, evidence", [
    # the request states each figure for the quantity its premise names: undecided, OVS-TRN-011
    (FIVE_INPUT, "OVS-TRN-011", "restate the conclusion", "why no check decides", ("a data conjunct needs its data premise", "Inspection I77, I78")),
    # control: the request states none of them: each refuted (stated nowhere), OVS-TRN-006
    ("Analyse how the writer presents work in the extract.", "OVS-TRN-006", "are the writer's own", "what a check shows of each", ("grounded-transcription",
                                                                                                                            "stated nowhere in the request")),
])
def test_a_grade_message_gives_its_signed_run_and_rule_before_the_premises_reasons_and_never_loses_them_to_the_cap(user_input, code, says, label,
                                                                                                                 evidence):
    """Found measuring the third repair on the recorded r7 task m1.1: five premises' reasons came before the auditor's
    signed run and the rule, so the finding cap (2000 characters, cut at the end) cut the evidence away. The message now
    gives its evidence first (what is restated, the signed run, the rules), then as many whole reasons as fit, saying how
    many are left out; the finding's audit note gives every premise's reason in full."""
    from epinoic_logic.integrity.contracts import MESSAGE_MAX_CHARS
    aud, ch, rc = _run_on(user_input, _five_problem())
    try:
        a = aud.audit(ch.uid)
        (f,) = trn(a, code)
        named = [f"P_{n}" for n, _v, _m in FIVE]
        assert len(f.message) <= MESSAGE_MAX_CHARS and "[truncated]" not in f.message, f.message
        assert f"premise(s) {', '.join(named)} {says}" in f.message and "COUNTEREXAMPLE" in f.message and "engine-shown" in f.message, f.message
        assert all(e in f.message for e in evidence) and f"; {label}: P_years: " in f.message and f.related_result_ids, f.message
        # whole reasons only, the rest counted: every premise is either given its reason here or counted as left out
        given = [p for p in named if f"{p}: its task_setting grounding is not verified" in f.message]
        left = len(named) - len(given)
        assert given and given == named[:len(given)] and (left == 0 or f"; and for {left} more premise(s), in the audit notes" in f.message), f.message
        (note,) = [n for n in a.coverage.notes if code in n and "P_years" in n]
        assert all(f"{p}: its task_setting grounding is not verified" in note for p in named) and f"; {label}: " in note, note
    finally:
        aud.close()


def test_fit_reasons_keeps_the_head_whole_gives_whole_reasons_and_counts_the_rest():
    head = "H" * 30
    assert T.fit_reasons(head, "why", []) == head
    assert T.fit_reasons(head, "why", ["a" * 10, "b" * 10], cap=200) == head + "; why: " + "a" * 10 + "; " + "b" * 10
    assert T.fit_reasons(head, "why", ["a" * 10, "b" * 200], cap=200) == head + "; why: " + "a" * 10 + "; and for 1 more premise(s), in the audit notes"
    assert T.fit_reasons(head, "why", ["a" * 300], cap=200) == head + "; why: in the audit notes"
    assert T._named([f"p{i}" for i in range(8)]) == "p0, p1, p2, p3, p4, p5 and 2 more" and T._named(["p0", "p1"]) == "p0, p1"
