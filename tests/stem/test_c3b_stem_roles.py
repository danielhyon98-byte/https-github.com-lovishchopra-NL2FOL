"""Round-10 leftover R10-STEM-H1-ROLES (major): STEM claim roles. A part's section title ('(a) Confusion matrix (rows show the actual
class, columns the predicted class)', '(b) Round robin, time slice 2 ms') was the part's material point; a label line of working
closing on a colon ('(f) For the current cans, $r = 3.2$ cm:', 'Sign of f′(x) = 3(x − 3)(x + 1):') was a quantitative claim; the
results a part asks for in paragraphs of their own ('Accuracy = ... = 0.950', 'Precision = ... = 0.880') were supports of the last
one, not material; and the 'Option 1' of 'Option 1 is market development.' was read as an unencoded figure '1'.

Now a section title and a colon label line are headings (role other, no claim to verify), and an option's number is a label. (Each
requested result of a part being material is not done here: ``_part_answers`` is pinned by the gate-2 equivalence test and a
paragraph's last line of working may be a check line; it needs the request's requested quantities read.)"""
from __future__ import annotations

from tests.channel.c3_core_support import _deliver

CS_P10A = ("(a) Confusion matrix (rows show the actual class, columns the predicted class)\n\n"
           "| | Predicted aluminium | Predicted not aluminium | Total |\n|---|---|---|---|\n"
           "| Actually aluminium | 132 (TP) | 12 (FN) | 144 |\n| Actually not aluminium | 18 (FP) | 438 (TN) | 456 |\n| Total | 150 | 450 | 600 |\n\n"
           "(b) Accuracy = (TP + TN) ÷ total\n= (132 + 438) ÷ 600\n= 570 ÷ 600\n= 19/20 = 0.950 (3 s.f.)\n\n"
           "Precision = TP ÷ (TP + FP)\n= 132 ÷ (132 + 18)\n= 132 ÷ 150\n= 22/25 = 0.880 (3 s.f.)\n\n"
           "Recall = TP ÷ (TP + FN)\n= 132 ÷ (132 + 12)\n= 132 ÷ 144\n= 11/12 = 0.917 (3 s.f.)\n\n"
           "(c) Round robin, time slice 2 ms\n\nIn the queue column, each entry is name(time still needed).\n\n"
           "| Slice | Process | Start (ms) | End (ms) |\n|---|---|---|---|\n| 1 | P1 | 0 | 2 |\n| 2 | P2 | 2 | 4 |\n\n"
           "Average turnaround time = (14 + 11 + 18 + 8) ÷ 4 = 51 ÷ 4 = 12.75 ms.")
CS_Q = ("(a) Construct the confusion matrix. [2] (b) Calculate the accuracy, the precision and the recall. [3] "
        "(c) Trace round robin with a 2 ms slice and give the average turnaround time. [3]")
MAA = ("(a) f′(x) = 3x² − 6x − 9  M1A1\n= 3(x − 3)(x + 1)\nf′(x) = 0 when x = 3 or x = −1  M1\nStationary points: (−1, 32) and (3, 0)  A1\n"
       "Sign of f′(x) = 3(x − 3)(x + 1):\nfor x < −1, both brackets are negative, so f′(x) > 0;\nfor −1 < x < 3, f′(x) < 0;\nfor x > 3, f′(x) > 0.\n\n"
       "(b) For the current cans, r = 3.2 cm:\n\nA = 2π(3.2)² + 660/3.2 = 270.59 cm² (M1)\n\nSaving per can = 270.59 − 264.36 = 6.23 cm² (A1)")
MAA_Q = "(a) Find the stationary points of f(x) = x³ − 3x² − 9x + 27 and classify them. [6] (b) Find the saving per can. [3]"


def _claims(subject: str, agent: str, question: str, text: str) -> dict[str, dict]:
    item = {"task_id": "probe-h1", "subject": subject, "agent_id": agent, "task_type": "short_answer", "question": question,
            "supplied_texts": [], "response_text": text}
    hub, _ch, reply, _rc = _deliver(item, None, None)
    hub.close()
    return {c["claim_text"]: c for c in reply.payload["claims"]}


def _find(claims: dict[str, dict], start: str) -> dict:
    found = [c for t, c in claims.items() if t.startswith(start)]
    assert len(found) == 1, (start, list(claims))
    return found[0]


def test_section_titles_are_headings_and_the_parts_result_is_material():
    claims = _claims("Computer Science", "computer-science-specialist", CS_Q, CS_P10A)
    for title in ("Confusion matrix", "Round robin, time slice 2 ms"):
        assert _find(claims, title)["claim_role"] == "other", _find(claims, title)
    assert _find(claims, "Recall = TP")["materiality"] == "material", _find(claims, "Recall = TP")


def test_a_label_line_closing_on_a_colon_is_a_heading_over_its_working():
    claims = _claims("Mathematics: Analysis and Approaches", "mathematics-aa-specialist", MAA_Q, MAA)
    for label in ("Sign of f′(x)", "For the current cans"):
        assert _find(claims, label)["claim_role"] == "other", _find(claims, label)
    assert _find(claims, "Saving per can")["materiality"] == "material"


def test_an_options_number_is_a_label_never_an_unencoded_figure():
    from epinoic_logic.api.ir import Problem
    from epinoic_logic.translate.contracts import ClaimRecord
    from epinoic_logic.translate.pipeline import unencoded_claim_figures
    p = Problem.model_validate({"problem_id": "p", "request_id": "r", "claim_id": "g6.1", "query": "entailment",
                                "symbols": [{"name": "x", "sort": "Int"}],
                                "premises": [{"id": "P", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "4"}}}],
                                "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "3"}}}})
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a", subject="Business Management", task_type="essay")
    for text, expected in (("Option 1 is market development, with 4 new stores.", []), ("Option (2) adds 4 stores.", []),
                           ("Market development adds 4 stores and 7 staff.", ["'7'"])):
        assert unencoded_claim_figures(p, ClaimRecord(**ids, claim_id="g6.1", claim_text=text)) == expected, text


def test_a_request_statement_id_in_a_check_message_is_named_as_the_requests():
    """Round-10 leftover R10-STEM-H5-REQUEST-IDS (c3 maa-t16 stem_substitution): '[claims m2.1, s1.2]' showed the request's statement
    id s1.2 as a claim id of the report (whose claims are m*.*). A statement id the answer's document does not hold is the request's:
    '[claims m2.1; the request (s1.2)]'; an id the document holds keeps its claim id, and a list of request ids alone is the request's."""
    from types import SimpleNamespace

    from epinoic_logic.branches.stem_pack import _ClaimMap
    from epinoic_logic.translate.contracts import ClaimRecord
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="mathematics-aa-specialist", subject="Mathematics: Analysis and Approaches",
               task_type="short_answer")
    text = "f(−6) = (−3)³ − 3(−3)² − 9(−3) + 27"
    report = SimpleNamespace(claims=[ClaimRecord(**ids, claim_id="m2.1", claim_text=text)], original_response=text)
    held = {"s2.1": SimpleNamespace(start=0, end=len(text))}
    doc = SimpleNamespace(statement=lambda sid: held.get(sid), text=text)
    cm = _ClaimMap(report, doc)
    assert cm.relabel("the written arithmetic: 'x' [claims s2.1, s1.2] [rule]") == "the written arithmetic: 'x' [claims m2.1; the request (s1.2)] [rule]"
    assert cm.relabel("[claims s2.1]") == "[claims m2.1]"
    assert cm.relabel("[claims s1.2, s1.3]") == "[the request (s1.2, s1.3)]"


G_REQUEST = ("The planet has a mass of 6.4 × 10²³ kg and a radius of 3400 km. G = 6.67 × 10⁻¹¹ N m² kg⁻². Calculate the gravitational field "
             "strength at the surface.")
G_WORK = "g = GM/r² = 6.67 × 10⁻¹¹ × 6.4 × 10²³ ÷ (3.4 × 10⁶)² = 3.7 N kg⁻¹"


def test_a_restated_constant_that_differs_from_the_requests_value_is_named_at_warning():
    """Round-9 leftover R9-STEM-NAMED-UNDECIDED (G-plain): 'G = 6.67 × 40⁻¹¹ N m² kg⁻²' beside the request's G = 6.67 × 10⁻¹¹ was named
    only at info (ST-SCOPE-001). Its value, read exactly in the unit as written, differs from the request's: a symbol conflict,
    ST-SCOPE-002 at warning. The request's own value restated, as a value or as an expression of the same value, draws none (controls)."""
    from epinoic_logic.stem.document import build_document

    def codes(first_line: str) -> dict[str, str]:
        doc = build_document(first_line + "\n" + G_WORK, G_REQUEST, "physics")
        return {f.code: f.severity for f in doc.findings}
    assert codes("G = 6.67 × 40⁻¹¹ N m² kg⁻²").get("ST-SCOPE-002") == "warning"
    assert "ST-SCOPE-002" not in codes("G = 6.67 × 10⁻¹¹ N m² kg⁻²")
    assert "ST-SCOPE-002" not in codes("G = 667 × 10⁻¹³ N m² kg⁻²")
    # control: a bare variable the request evaluates at ('at x = 1') that the answer solves for ('x = −1/3') is no restated constant
    doc = build_document("f′(x) = 6x + 2\nAt x = 1, f′(1) = 8.\n6x + 2 = 0, so x = -(1/3).",
                         "Find f′(x) for f(x) = 3x² + 2x − 5 and hence find the gradient of the curve at x = 1 and the x-coordinate of the "
                         "stationary point.", "mathematics")
    assert "ST-SCOPE-002" not in {f.code for f in doc.findings}, [f.message for f in doc.findings]


def test_controls_an_equation_or_a_value_on_a_parts_lead_line_is_never_a_title():
    """Controls of the section-title rule: a chemical equation or a value on a part's lead line, over a table or not, is the part's
    content, never a heading (a title is a noun phrase with no relation, operation, arrow or sub- or superscript digit, over a table
    it heads, and never opens with a figure)."""
    text = ("(a) 2C₁₂H₂₆(l) + 37O₂(g) → 24CO₂(g) + 26H₂O(l)  [1]\n\n| Atom | Left | Right |\n|---|---|---|\n| C | 24 | 24 |\n\n"
            "(b) 0.0896 mol\n\n| n | V |\n|---|---|\n| 0.0896 | 1.0 |")
    claims = _claims("Chemistry", "chemistry-specialist", "(a) Write the balanced equation. [1] (b) Give the amount. [1]", text)
    assert _find(claims, "2C₁₂H₂₆(l)")["claim_role"] != "other", _find(claims, "2C₁₂H₂₆(l)")
    assert _find(claims, "0.0896 mol")["claim_role"] != "other", _find(claims, "0.0896 mol")


def test_controls_a_colon_line_citing_its_method_or_stating_a_relation_is_no_label():
    """Controls of the colon-label rule (``generic_parser.stem_colon_label``): a line that cites the law or step it applies ('Using
    a = (v − u)/t:', 'Substitute into C(t) = C0 e^(−kt) at t = 0 and t = 8:') or states a relation ('Acceleration is the derivative of
    velocity:') keeps its claim; the round-7 STEM reading equals the generic one on such lines (tests/stem/test_merge_round7.py)."""
    from epinoic_logic.branches.generic_parser import stem_colon_label
    assert stem_colon_label("Sign of f′(x) = 3(x − 3)(x + 1):") is True
    assert stem_colon_label("For the current cans, r = 3.2 cm:") is True
    for line in ("Using a = (v − u)/t:", "Substitute into C(t) = C0 e^(−kt) at t = 0 and t = 8:", "Acceleration is the derivative of velocity:",
                 "Sign of f′(x) = 3(x − 3)(x + 1)", "For " + "the cans " * 10 + ":"):
        assert stem_colon_label(line) is False, line
