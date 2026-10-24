"""The fourth repair of the translator merge (design decision 56): rule data-standing reads a restating premise with no
located excerpt as UNDECIDED only when a deterministic check READS its whole content in its held source (rule
same-quantity's positive reading, :func:`figure_reading`, with rule table-cells for a table's data). Content that only a
kind label presents as data is UNCHECKABLE, shown not to be data, so a result resting on it is OVS-TRN-006:

* Boolean content, whatever the translation declares of its symbols and its conclusion (no check reads a Boolean
  statement against a source);
* anything but the values of quantities (:func:`value_atoms`: a relation between quantities, arithmetic, a negation);
* a structural figure (0 or 1, never read as data);
* a figure the source states only bare, for a premise whose statement names no quantity, otherwise than the premise
  states it (a value for a bound), or in a table row the premise's statement does not name: a number match only.

Finding (b) of the review of the third repair: p proves p with every grounding ``task_setting``, or ``supplied_text``
naming a supplied document with no excerpt, was graded OVS-TRN-011 (a warning), the transfer cleared and the router was
shown ENTAILED; no grounding label and no number match is evidence on its own. Each test fails on the third repair's code
(the standing was ``undecided``, the grade OVS-TRN-011) and each control pins what stays: a premise whose figures the
request states for the quantity it names is still undecided (OVS-TRN-011), never a transcription.

No model is called; translations come from the translator's own pipeline with the fixture provider.
"""
from __future__ import annotations

import json
from fractions import Fraction
from typing import Optional

import pytest

from epinoic_logic.ir.schema import Problem
from epinoic_logic.overseer.checks import translation as T
from epinoic_logic.translate.contracts import SuppliedText

from .conftest import DOC, english_report, make_auditor
from .test_protocol_validate import review
from .test_repair3_same_quantity import _run_on
from .test_translation_agents import outcome_of, tr_acc
from .test_translation_oversight import INFER, POINT, V, genuine_problem, proposal, run, trn

TS = {"kind": "task_setting"}
#: The supplied extract of the synthetic task (doc-mill), named with no excerpt.
ST = {"kind": "supplied_text", "source_refs": [{"document_id": "doc-mill"}]}


def _g(g: dict) -> dict:
    return json.loads(json.dumps(g))


def _declared_throughout(p: dict, g: dict, *, keep_quotations: bool = False) -> dict:
    """The reviewer's probe: the specialist's reasoning replaced by the claim itself under the label ``g``, every symbol and
    the conclusion grounded the same way (the translation declares the claim as data throughout). With
    ``keep_quotations`` only the link is replaced (the two quotations stay)."""
    for s in p["symbols"]:
        if not keep_quotations or s["name"] == "endless":
            s["grounding"] = _g(g)
    kept = [x for x in p["premises"] if x["id"] != "P_link"] if keep_quotations else []
    p["premises"] = kept + [{"id": "P_assumed", "expr": V("endless"), "label": "given", "grounding": _g(g)}]
    p["conclusion"]["grounding"] = _g(g)
    return p


# ============================================================================================ the reviewer's probe, end to end
@pytest.mark.parametrize("label, g, keep", [
    ("p proves p, every grounding task_setting", TS, False),
    ("the link replaced, endless and the conclusion task_setting", TS, True),
    ("p proves p, every grounding supplied_text naming doc-mill with no excerpt", ST, False),
])
def test_p_proves_p_on_a_kind_label_alone_is_trn_006_and_the_transfer_fails(label, g, keep):
    """The review's probe. The merged translator delivers the encoding (its rule reads the label as a transcription) and
    the engine gives ENTAILED, displayed ENTAILED. No check reads Boolean content against the request or the extract, so
    the label is the only evidence the premise is data: it is shown not to be data (uncheckable), the result rests on it,
    and the grade is OVS-TRN-006 (an error), the transfer AUDIT_FAILED, an agent's translation_circular accusation
    CONFIRMED. The third repair graded it OVS-TRN-011, the transfer AUDIT_PASSED_WITH_FINDINGS and the accusation
    unresolved."""
    aud = make_auditor(shadow="off")
    try:
        aud, ch, rc = run({POINT: proposal(_declared_throughout(genuine_problem(), g, keep_quotations=keep))}, auditor=aud)
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.translation.status.value == "TRANSLATED" and o.verification.status.value == "ENTAILED" and not o.verification.diagnostics
        assert o.display_status.value == "ENTAILED"  # what the router is shown: the translator's rule delivered it
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-006")
        assert f.severity == "error" and f.claim_ids == [POINT] and "P_assumed" in f.message and f.related_result_ids, f.message
        assert "engine-shown" in f.message and "Boolean content" in f.message and "data-standing" in f.message
        assert trn(a, "OVS-TRN-011") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"
        r = review(aud, ch.uid)
        acc = outcome_of(r.run([tr_acc(r.dossier, "translation_circular")]))
        assert acc.outcome == "confirmed" and [c.code for c in acc.confirming] == ["OVS-TRN-006"]
    finally:
        aud.close()


def test_control_the_writers_own_label_is_withheld_by_the_translator_itself():
    """Control (the review's probe, its last variant): the same circle under specialist_inference is withheld by the
    merged translator's own gate (E112, INVALID_FORMALIZATION, no problem), so no OVS-TRN-006 or -011 is raised for a
    circle the receipt already shows as no verdict (rule circularity-agreement)."""
    p = genuine_problem()
    p["premises"] = [{"id": "a_point", "expr": V("endless"), "grounding": INFER}]
    aud, ch, rc = run({POINT: proposal(p)})
    try:
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.translation.status.value == "INVALID_FORMALIZATION" and any("E112" in d for d in o.translation.diagnostics)
        a = aud.audit(ch.uid)
        assert trn(a, "OVS-TRN-006") == [] and trn(a, "OVS-TRN-011") == []
    finally:
        aud.close()


# ============================================================================================ rule data-standing (decision 56)
HOURS_REQUEST = "Write about the mill. The children worked 12 hours a day, 1 shift."
TABLE_DOC = SuppliedText(document_id="doc-table", title="Table 1", author="Task data", text=(
    "Table 1\nYear | Price paid by consumers ($ per litre) | Quantity sold (million litres per year) | Tax per litre ($)\n"
    "2024 | 1.60 | 120 | 0.00\n2025 | 1.90 | 105 | 0.40"))


def _premise_problem(expr: dict, symbols: dict[str, str], *, g: Optional[dict] = None, label: Optional[str] = None,
                     meanings: Optional[dict[str, str]] = None, ground_symbols: bool = True) -> Problem:
    """A restating premise P (``expr``, grounded ``g``: a task setting by default) that is also the conclusion, its symbols
    and the conclusion grounded as P is (the translation declares it data throughout)."""
    g = g or TS
    syms = []
    for name, sort in symbols.items():
        s = {"name": name, "sort": sort}
        if (meanings or {}).get(name):
            s["meaning"] = meanings[name]
        if ground_symbols:
            s["grounding"] = _g(g)
        syms.append(s)
    prem = {"id": "P", "expr": expr, "grounding": _g(g)}
    if label is not None:
        prem["label"] = label
    return Problem.model_validate({"problem_id": "p-ds", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment", "symbols": syms,
                                   "premises": [prem], "conclusion": {"id": "C", "expr": expr, "label": label or "the claim", "grounding": _g(g)}})


def _eq(name: str, value: str, op: str = "eq", lit: str = "int") -> dict:
    return {"op": op, "left": V(name), "right": {"op": lit, "value": value}}


HOURS = {"hours": "Int"}
HOURS_MEANING = {"hours": "the hours a day the children worked"}


@pytest.mark.parametrize("case, problem, request_texts, docs, why", [
    # Boolean content, which the translation declares as data throughout: no check reads it against a source
    ("bool, task_setting", _premise_problem(V("ok"), {"ok": "Bool"}, meanings={"ok": "the children worked long hours"}), [HOURS_REQUEST], (),
     "no deterministic check reads Boolean content"),
    ("bool, supplied_text naming a supplied document", _premise_problem(V("ok"), {"ok": "Bool"}, g=ST, meanings={"ok": "the writer presents work as endless"}),
     [HOURS_REQUEST], (DOC,), "no deterministic check reads Boolean content"),
    ("bool beside a figure the request states", _premise_problem({"op": "and", "args": [_eq("hours", "12"), V("ok")]}, {"hours": "Int", "ok": "Bool"},
                                                                 meanings={"hours": "the hours a day the children worked", "ok": "the work was hard"}),
     [HOURS_REQUEST], (), "no deterministic check reads Boolean content"),
    # no figure but 0 or 1 (structural, never read), or one beside a figure the request states for its quantity
    ("structural only", _premise_problem(_eq("shifts", "1"), {"shifts": "Int"}, meanings={"shifts": "the shifts a day"}), [HOURS_REQUEST], (),
     "no figure other than 0 or 1"),
    ("structural beside data", _premise_problem({"op": "and", "args": [_eq("hours", "12"), _eq("shifts", "1")]}, {"hours": "Int", "shifts": "Int"},
                                                meanings={"hours": "the hours a day the children worked", "shifts": "the shifts a day"}),
     [HOURS_REQUEST], (), "structural figure(s) 1"),
    # not the values of quantities: a relation, arithmetic, a negation, a comparison negated
    ("a relation between quantities", _premise_problem({"op": "eq", "left": {"op": "add", "args": [V("hours"), V("rest")]}, "right": {"op": "int", "value": "12"}},
                                                       {"hours": "Int", "rest": "Int"}, meanings={"hours": "the hours a day the children worked"}),
     [HOURS_REQUEST], (), "not the values of quantities"),
    ("a negated value", _premise_problem({"op": "not", "arg": _eq("hours", "12")}, HOURS, meanings=HOURS_MEANING), [HOURS_REQUEST], (),
     "not the values of quantities"),
    ("a value negated by ne", _premise_problem(_eq("hours", "12", op="ne"), HOURS, meanings=HOURS_MEANING), [HOURS_REQUEST], (), "not the values of quantities"),
    # a figure the request states only bare, for a premise whose statement names no quantity, or not as the premise states it
    ("only bare", _premise_problem(_eq("hours", "12"), HOURS, meanings=HOURS_MEANING), ["Question 12. Write about the mill."], (), "only bare"),
    ("statement names no quantity", _premise_problem(_eq("hours", "12"), HOURS), [HOURS_REQUEST], (), "names no quantity"),
    ("a bound for a value", _premise_problem(_eq("hours", "12", op="gt"), HOURS, meanings={"hours": "the hours a day the children worked, more than 12"}),
     [HOURS_REQUEST], (), "otherwise than the premise states it"),
    ("a table row the statement does not name", _premise_problem(_eq("q", "105"), {"q": "Int"}, g={"kind": "supplied_text", "source_refs": [{"document_id": "doc-table"}]},
                                                                 meanings={"q": "quantity sold (million litres)"}), [], (TABLE_DOC,),
     "table row its statement does not name"),
    # the fifth repair (decision 57, rule statement-context): the input of this file's control "a bound for a bound", which
    # pinned it undecided (OVS-TRN-011). The request REQUIRES the paragraph's count, it never states it: the review's
    # requirement case in its bound form, shown not to be data
    ("a bound the request only requires (the control's input)", _premise_problem(_eq("n", "80", op="le"), {"n": "Int"},
                                                                               label="the paragraph has no more than 80 words",
                                                                               meanings={"n": "the number of words of the paragraph"}),
     ["Write no more than 80 words."], (), "as a requirement on the answer"),
])
def test_rule_data_standing_content_only_a_label_presents_as_data_is_uncheckable(case, problem, request_texts, docs, why):
    """Decision 56: presented as data the request (or a supplied document it names) holds, a premise with no located
    excerpt is undecided only when a check reads its whole content there; here none does, so the kind label is the only
    evidence: uncheckable (shown not to be data), never undecided. Each case was undecided on the third repair's code."""
    rs = T.restatement(problem, english_report(docs=(DOC,) + tuple(d for d in docs if d.document_id != "doc-mill")), request_texts, request_documents=docs)
    assert rs.holds and rs.own == ("P",) and rs.grounded == (), (case, rs)
    assert rs.standings == (("P", "uncheckable"),) and rs.shown == ("P",) and rs.undecided == (), (case, rs.why_own)
    reason = dict(rs.why_own)["P"]
    assert why in reason and "the kind label is then the only evidence" in reason, (case, reason)
    # rule engine-shown: the result rests on it, so the grade is OVS-TRN-006 (the third repair: OVS-TRN-011)
    obj = json.loads(problem.model_dump_json(exclude_none=True))
    from epinoic_logic.engine import SolverConfig, verify
    follows = lambda pids: verify(json.dumps(T.without_premises(obj, pids)), SolverConfig()).status.value == "ENTAILED"  # noqa: E731
    assert T.engine_shown_codes(rs, False, follows) == ["OVS-TRN-006"], case


@pytest.mark.parametrize("case, problem, request_texts, docs", [
    ("a value for its quantity", _premise_problem(_eq("hours", "12"), HOURS, meanings=HOURS_MEANING), [HOURS_REQUEST], ()),
    ("the comparison the other way round", _premise_problem({"op": "eq", "left": {"op": "int", "value": "12"}, "right": V("hours")}, HOURS, meanings=HOURS_MEANING),
     [HOURS_REQUEST], ()),
    # a bound the request STATES (the fifth repair: the request that only requires a bound, "Write no more than 80 words.",
    # is now shown not to be data, asserted in the test above on this case's earlier input)
    ("a bound for a bound", _premise_problem(_eq("n", "80", op="le"), {"n": "Int"}, label="the extract has no more than 80 words",
                                             meanings={"n": "the number of words of the extract"}), ["The extract has no more than 80 words."], ()),
    ("a percentage", _premise_problem(_eq("rate", "3.6", lit="real"), {"rate": "Real"}, meanings={"rate": "the nominal annual rate is 3.6 per cent"}),
     ["A sum is invested at a nominal annual rate of 3.6%, compounded monthly."], ()),
    ("a frequency word", _premise_problem(_eq("comp", "12"), {"comp": "Int"}, meanings={"comp": "interest is compounded monthly (12 periods a year)"}),
     ["A sum is invested at 3.6%, compounded monthly."], ()),
    ("a table cell in its column and row", _premise_problem(_eq("q25", "105"), {"q25": "Int"}, g={"kind": "supplied_text", "source_refs": [{"document_id": "doc-table"}]},
                                                            label="2025 quantity sold is 105 million litres",
                                                            meanings={"q25": "quantity sold, 2025 (million litres, Table 1)"}), [], (TABLE_DOC,)),
])
def test_control_a_premise_whose_figures_the_source_states_for_its_quantity_stays_undecided(case, problem, request_texts, docs):
    """Control: a premise that states only values of quantities, each figure stated by its held source for the quantity
    its statement names, as it states it (and in a table in its column and row), is still undecided: data presented as
    given, never a transcription (no located excerpt: a number match is no evidence), and a result resting on it alone is
    OVS-TRN-011 (a data conjunct needs its data premise)."""
    rs = T.restatement(problem, english_report(docs=(DOC,) + tuple(docs)), request_texts, request_documents=docs)
    assert rs.holds and rs.own == ("P",) and rs.standings == (("P", "undecided"),) and rs.undecided == ("P",) and rs.shown == (), (case, rs.why_own)
    reason = dict(rs.why_own)["P"]
    assert "a number match is no evidence" in reason and "a quantity the premise's own statement names" in reason, (case, reason)
    obj = json.loads(problem.model_dump_json(exclude_none=True))
    from epinoic_logic.engine import SolverConfig, verify
    follows = lambda pids: verify(json.dumps(T.without_premises(obj, pids)), SolverConfig()).status.value == "ENTAILED"  # noqa: E731
    assert T.engine_shown_codes(rs, False, follows) == ["OVS-TRN-011"], case


def test_value_atoms_reads_only_the_values_of_quantities():
    sorts = {"x": "Int", "y": "Real", "b": "Bool"}
    assert T.value_atoms(_eq("x", "5"), sorts) == [("x", "eq", Fraction(5))]
    assert T.value_atoms({"op": "lt", "left": {"op": "int", "value": "3"}, "right": V("x")}, sorts) == [("x", "gt", Fraction(3))]
    assert T.value_atoms({"op": "and", "args": [_eq("x", "5"), {"op": "ge", "left": V("y"), "right": {"op": "neg", "arg": {"op": "real", "value": "2.5"}}},
                                                {"op": "bool", "value": True}]}, sorts) == [("x", "eq", Fraction(5)), ("y", "ge", Fraction(-5, 2))]
    for expr in (V("b"), {"op": "not", "arg": _eq("x", "5")}, _eq("x", "5", op="ne"), {"op": "eq", "left": V("x"), "right": V("y")},
                 {"op": "eq", "left": {"op": "add", "args": [V("x"), {"op": "int", "value": "0"}]}, "right": {"op": "int", "value": "5"}},
                 {"op": "or", "args": [_eq("x", "5"), _eq("x", "6")]}, {"op": "bool", "value": False}, _eq("b", "1")):
        assert T.value_atoms(expr, sorts) is None, expr


# ============================================================================================ rule table-cells
def test_rule_table_cells_reads_a_figure_for_its_column_and_row():
    """Rule table-cells: a figure in a data cell names its column's quantity (the header's unit and words) and the row
    its first cell names, and reads no marker beyond its cell. Read for the right column in the right row; unread in
    another row; refuted for a quantity no column states it for (the third repair read every table cell bare: never
    refuted, never read)."""
    occ = {(sorted(o.values)[0], o.column): o for o in T._occurrences(TABLE_DOC.text) if o.column}
    q = occ[(Fraction(105), "Quantity sold (million litres per year)")]
    assert q.row == "2025" and "litres" in q.quantity and q.marker is None and not q.bare
    p = occ[(Fraction(19, 10), "Price paid by consumers ($ per litre)")]
    assert p.row == "2025" and "dollar" in p.quantity
    tax = occ[(Fraction(2, 5), "Tax per litre ($)")]
    assert tax.marker is None  # the next line ("Assume ...") is no unit of a cell's figure
    texts = [TABLE_DOC.text]
    read = T.figure_reading(Fraction(105), texts, "2025 quantity sold is 105 million litres ; quantity sold, 2025", {"eq"}, where="the table")
    assert read.kind == T.FIGURE_READ and "table column 'Quantity sold (million litres per year)' (row 2025)" in read.reason
    other_row = T.figure_reading(Fraction(105), texts, "2024 quantity sold is 105 million litres ; quantity sold, 2024", {"eq"}, where="the table")
    assert other_row.kind == T.FIGURE_UNREAD and "table row its statement does not name" in other_row.reason
    other_column = T.figure_reading(Fraction(105), texts, "the 2025 price paid is 105 dollars ; price paid by consumers, 2025", {"eq"}, where="the table")
    assert other_column.kind == T.FIGURE_REFUTED and "Quantity sold (million litres per year)" in other_column.reason
    assert T.figure_refutation(Fraction(105), texts, "the 2025 price paid is 105 dollars ; price paid by consumers, 2025", {"eq"}) is not None
    # a Markdown table with its rule line, and a row opened and closed by pipes
    md = "| Temperature / °C | Mean oxygen uptake / mm3 per g per hour |\n|---|---|\n| 10 | 18 |\n| 35 | 92 |"
    o18 = next(o for o in T._occurrences(md) if Fraction(18) in o.values)
    assert o18.row == "10" and "mm3" in o18.quantity
    assert T.figure_reading(Fraction(18), [md], "oxygen uptake at 10 C is 18 mm3 per g per hour", {"eq"}).kind == T.FIGURE_READ
    # text that is no table keeps its own reading: the marker after a figure
    (h,) = [o for o in T._occurrences("The children worked 12 hours a day.") if Fraction(12) in o.values]
    assert h.marker == "hours" and h.column is None and h.row is None


def test_figure_reading_never_reads_a_structural_figure_and_refutes_as_before():
    """0 and 1 are structural: never refuted (as for the number trace) and, decision 56, never read as data. The
    refutations are those of the third repair, in its order (figure_refutation is their view)."""
    for v in (Fraction(0), Fraction(1)):
        r = T.figure_reading(v, ["1 shift, 0 breaks"], "the shifts a day", {"eq"})
        assert r.kind == T.FIGURE_UNREAD and "structural" in r.reason and T.figure_refutation(v, ["x"], "y", {"eq"}) is None
    assert T.figure_reading(Fraction(81), ["Write no more than 80 words."], "the count the point states", {"eq"}).kind == T.FIGURE_REFUTED
    shown = T.figure_reading(Fraction(8), ["Show that the distance is 8 m."], "the distance in metres", {"eq"})
    assert shown.kind == T.FIGURE_REFUTED and "only as the target the answer must derive" in shown.reason
    bound = T.figure_reading(Fraction(80), ["Write no more than 80 words."], "the paragraph has 80 words", {"eq"})
    assert bound.kind == T.FIGURE_REFUTED and "only as a bound" in bound.reason


# ============================================================================================ the mai-t13 shape, end to end
MAI_INPUT = "A sum of 2000 euros is invested for 5 years at a nominal annual rate of 3.6%, compounded monthly. (a) Find its value at the end, to the nearest euro."


def _question_problem(with_bool: bool = True) -> dict:
    years = _eq("years", "5")
    symbols = [{"name": "years", "sort": "Int", "meaning": "the years the sum is invested", "grounding": _g(TS)}]
    premises = [{"id": "t_years", "expr": years, "label": "the sum is invested for 5 years", "grounding": _g(TS)}]
    concl = years
    if with_bool:
        symbols.append({"name": "wants_value", "sort": "Bool", "meaning": "the question asks for the value to the nearest euro", "grounding": _g(TS)})
        premises.append({"id": "t_wants", "expr": V("wants_value"), "label": "the question asks for the value to the nearest euro", "grounding": _g(TS)})
        concl = {"op": "and", "args": [years, V("wants_value")]}
    return {"problem_id": "p-q", "request_id": "req-ovs", "claim_id": POINT, "query": "entailment", "symbols": symbols, "premises": premises,
            "conclusion": {"id": "C", "expr": concl, "label": "the question wants the value after 5 years, to the nearest euro", "grounding": _g(TS)}}


def test_the_question_restated_with_a_bool_task_setting_conjunct_is_trn_006_naming_that_premise_only():
    """The shape of r7 mai-t13 m1.1 and m7.1 (and of pack Example 27): every conjunct restated by a task setting, one a
    figure the request states for the years (undecided), one a Boolean statement of what the question asks (only the
    label presents it as data: uncheckable). The run without the shown premise, keeping the undecided one, is not
    ENTAILED: OVS-TRN-006 naming t_wants alone and saying t_years was kept; AUDIT_FAILED. Control: without the Boolean
    conjunct the result rests on t_years alone, undecided: OVS-TRN-011 and AUDIT_PASSED_WITH_FINDINGS (unchanged)."""
    aud, ch, rc = _run_on(MAI_INPUT, _question_problem())
    try:
        o = next(x for x in rc.outcomes if x.claim_id == POINT)
        assert o.translation.status.value == "TRANSLATED" and o.display_status.value == "ENTAILED"
        a = aud.audit(ch.uid)
        (f,) = trn(a, "OVS-TRN-006")
        assert "t_wants" in f.message and "the premise(s) t_years" in f.message and "were kept in that run" in f.message, f.message
        assert trn(a, "OVS-TRN-011") == [] and a.transfer_states[rc.message_id] == "AUDIT_FAILED"
    finally:
        aud.close()
    aud2, ch2, rc2 = _run_on(MAI_INPUT, _question_problem(with_bool=False))
    try:
        a2 = aud2.audit(ch2.uid)
        (f2,) = trn(a2, "OVS-TRN-011")
        assert "t_years" in f2.message and trn(a2, "OVS-TRN-006") == [] and a2.transfer_states[rc2.message_id] == "AUDIT_PASSED_WITH_FINDINGS"
    finally:
        aud2.close()
