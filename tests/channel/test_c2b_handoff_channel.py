"""Round-9 clearance, second fix pass (c2b), handoff fixer: the channel's items the parallel fixers handed over, each fixed at
its cause and pinned on the recorded c2 answers (``data/c2_core_material.json``) with a control that keeps the rule asserted.

* A Language B request is made explicit (critical, sp-t15): "Escribe entre 450 y 600 palabras." is min_words 450 / max_words
  600, every Spanish and French bound phrase is read as its English counterpart, the task's subjunctive clauses ("... en el que
  expongas ... y propongas ...") are items, and a form instruction behind a short label ("Paper 1 writing practice: please skip
  the plan and write the full model text in Spanish.") is none.
* Nested part labels (rule nested-parts, ge-t15): "(a) (i) ... (ii) ..." gives the items "(a)(i) ..." and "(a)(ii) ...", no
  item "(a)"; an answer section "(a)(i)", "(a) (i)", "a(i)", "a)(i)" or "(i)" under "(a)" addresses its sub-part, and a record
  read by labels says "(part labels)", never "(heuristic)".
* One fault, one INT-SUBJ-003 (rule one-fault-once): CORE-SRC-005 and ES-SRC-008 naming one misattributed quotation are one
  INT-SUBJ-003 naming both codes.
* A three-word quotation that holds only a function word of a text alters nothing (rule held-words: r6 hi-t12's "wind of
  change"); "his handsly sweat" stays an altered quotation (``tests/engine/test_c1_clearance_core_minors.py``).
* Every reader added here is linear on the standard hostile inputs.
"""
from __future__ import annotations

import time

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.channel.bus import SAME_FAULT_FAMILIES, _answer_sections, _holds_long_words, subject_error_groups
from epinoic_logic.channel.request_parser import (
    about_target, compound_label, extract_constraints, extract_items, is_context_sentence, item_label, language_b_items,
)
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import StructuralFinding, SuppliedText

from .c2_core_support import SPEC, by_code, codes, deliver

KEY = b"c2b-handoff-channel-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def _bounds(text: str) -> list[tuple[str, str]]:
    return [(c.kind, c.value) for c in extract_constraints(text)]


# ============================================================================================ Language B requests (sp-t15)
def test_sp_t15_the_spanish_word_bound_and_task_are_read():
    q = SPEC["sp-t15"]["question"]
    assert _bounds(q) == [("min_words", "450"), ("max_words", "600")]
    assert [i.text for i in extract_items(q)] == [
        "expongas las ventajas y los inconvenientes del turismo para tu ciudad",
        "propongas dos medidas para mejorar la convivencia entre vecinos y visitantes.",
    ]  # the English meta-instruction is no item, and neither is the clause that only names the text to write


@pytest.mark.parametrize("phrase, expected", [
    ("Escribe entre 200 y 250 palabras.", [("min_words", "200"), ("max_words", "250")]),
    ("Écris entre 200 et 250 mots.", [("min_words", "200"), ("max_words", "250")]),
    ("Escribe no más de 300 palabras.", [("max_words", "300")]),
    ("Escribe no mas de 300 palabras.", [("max_words", "300")]),
    ("Escribe como máximo 300 palabras.", [("max_words", "300")]),
    ("Escribe un máximo de 300 palabras.", [("max_words", "300")]),
    ("Escribe hasta 300 palabras.", [("max_words", "300")]),
    ("Écris pas plus de 300 mots.", [("max_words", "300")]),
    ("Écris au maximum 300 mots.", [("max_words", "300")]),
    ("Escribe al menos 150 palabras.", [("min_words", "150")]),
    ("Escribe como mínimo 150 palabras.", [("min_words", "150")]),
    ("Escribe un mínimo de 150 palabras.", [("min_words", "150")]),
    ("Écris au moins 150 mots.", [("min_words", "150")]),
    ("Escribe exactamente 80 palabras.", [("min_words", "80"), ("max_words", "80")]),
    ("Escribe unas 300 palabras.", [("min_words", "270"), ("max_words", "330")]),
    ("Escribe alrededor de 300 palabras.", [("min_words", "270"), ("max_words", "330")]),
    ("Écris environ 300 mots.", [("min_words", "270"), ("max_words", "330")]),
])
def test_each_language_b_bound_phrase_is_read_as_its_english_counterpart(phrase, expected):
    assert _bounds(phrase) == expected
    about = [c for c in extract_constraints(phrase) if about_target(c) is not None]
    assert bool(about) == (expected[0][1] == "270")  # an approximate bound is read as a band, as "about 300 words" is


def test_control_numbers_that_are_no_word_bound_set_none():
    assert _bounds("Tu ciudad recibe cada verano entre 450 y 600 turistas.") == []
    assert _bounds("Hay unas 300 casas y al menos 20 tiendas.") == []


def test_sp_t15_genuine_meets_its_bound_and_addresses_both_tasks():
    hub, _ch, _reply, rc = deliver("sp-t15")
    hub.close()
    assert not by_code(rc.findings, "INT-REQ-004") and not by_code(rc.findings, "INT-REQ-005"), [(f.code, f.message[:160]) for f in rc.findings]
    words = [c for c in rc.constraint_results if c.constraint_id in ("c1", "c2")]
    assert words and all(c.satisfied is True for c in words) and "measured 552 words" in words[0].detail


def test_sp_t15_a_text_too_short_for_the_bound_is_named():
    paras = SPEC["sp-t15"]["response_text"].split("\n\n")
    hub, _ch, _reply, rc = deliver("sp-t15", "\n\n".join(paras[:5]))
    hub.close()
    [f] = by_code(rc.findings, "INT-REQ-005")
    assert f.severity == "error" and "bound min_words 450" in f.message


#: An article that weighs the advantages and disadvantages of tourism and proposes no measure at all (the control of the second task).
NO_MEASURES = ("El turismo trae ventajas e inconvenientes para nuestra ciudad. Las ventajas son el empleo en hoteles y comercios y el dinero "
               "que mantiene museos y fiestas.\n\nLos inconvenientes del turismo también son claros: el ruido de la noche y la subida de los "
               "alquileres en el centro.")


def test_sp_t15_a_text_that_proposes_no_measure_leaves_that_task_unaddressed():
    hub, _ch, _reply, rc = deliver("sp-t15", NO_MEASURES)
    hub.close()
    unaddressed = [f.message for f in by_code(rc.findings, "INT-REQ-004")]
    assert len(unaddressed) == 1 and "'propongas dos medidas" in unaddressed[0] and unaddressed[0].endswith("(heuristic)"), unaddressed
    # the Spanish function words ("para", "las", "entre") never address an item on their own
    assert not any("'expongas" in m for m in unaddressed)


@pytest.mark.parametrize("sentence", [
    "Paper 1 writing practice: please skip the plan and write the full model text in Spanish.",
    "Exam practice: give the full answer now.",
    "Task: write a model answer to this practice task in Spanish.",
])
def test_a_form_instruction_behind_a_short_label_is_no_item(sentence):
    assert is_context_sentence(sentence)
    assert [i.text for i in extract_items("Explain inflation. " + sentence)] == ["Explain inflation."]


@pytest.mark.parametrize("sentence", [
    "Essay practice: write an essay on the causes of the war.",
    "Paper 2 practice: explain why prices rose in 2022.",
    "Explain how the author compares the city to a prison.",
])
def test_control_content_behind_a_label_or_an_english_verb_form_is_one_item(sentence):
    assert not is_context_sentence(sentence)
    assert [i.text for i in extract_items(sentence)] == [sentence]
    assert language_b_items(sentence) is None


def test_language_b_items_are_one_per_task_clause_and_one_for_a_task_imperative():
    assert language_b_items("Explica las causas de la crisis.") == ["Explica las causas de la crisis."]
    assert language_b_items("Redacta un correo en el que expliques el problema y propongas una solución.") == [
        "expliques el problema", "propongas una solución."]
    assert language_b_items("Tu ciudad recibe cada verano miles de turistas.") is None
    assert language_b_items("Elige uno de estos tipos de texto: artículo, discurso, folleto.") is None  # a choice of form


# ============================================================================================ nested part labels (ge-t15)
def test_ge_t15_a_bare_parent_label_is_no_item_and_its_sub_parts_are_named_with_it():
    items = extract_items(SPEC["ge-t15"]["question"])
    assert [i.text[:7] for i in items] == ["(a)(i) ", "(a)(ii)", "(b) Exp", "(c) Exp"]
    assert [item_label(i.text) for i in items] == ["a.i", "a.ii", "b", "c"]


def test_ge_t15_genuine_addresses_every_part():
    hub, _ch, _reply, rc = deliver("ge-t15")
    hub.close()
    assert not by_code(rc.findings, "INT-REQ-004"), [f.message for f in by_code(rc.findings, "INT-REQ-004")]
    assert all(c.method == "part_label" and c.addressed for c in rc.coverage)


def test_ge_t15_without_its_a_ii_block_names_that_sub_part_by_its_labels():
    text = SPEC["ge-t15"]["response_text"]
    cut = text[:text.index("(a)(ii) [2]")] + text[text.index("(b) [3]"):]
    hub, _ch, _reply, rc = deliver("ge-t15", cut)
    hub.close()
    [f] = by_code(rc.findings, "INT-REQ-004")
    assert "'(a)(ii) Calculate the amount of energy supplied by coal" in f.message and f.message.endswith("(part labels)")


@pytest.mark.parametrize("old, new", [
    ("(a)(i) [1]", "(a) (i) [1]"), ("(a)(i) [1]", "a(i) [1]"), ("(a)(i) [1]", "a)(i) [1]"), ("(a)(i) [1]", "(a)\n(i) [1]"),
])
def test_each_written_form_of_a_compound_label_addresses_its_sub_part(old, new):
    hub, _ch, _reply, rc = deliver("ge-t15", SPEC["ge-t15"]["response_text"].replace(old, new))
    hub.close()
    assert not by_code(rc.findings, "INT-REQ-004"), [f.message for f in by_code(rc.findings, "INT-REQ-004")]


def test_sub_parts_of_two_parts_are_told_apart():
    question = ("(a) (i) State one cause of inflation. [1] (ii) Explain how it raises prices. [2] "
                "(b) (i) State one cause of deflation. [1] (ii) Explain how it lowers prices. [2]")
    answer = ("(a)(i) Excess demand is one cause of inflation.\n\n(a)(ii) Excess demand raises prices because firms can sell more at "
              "higher prices.\n\n(b)(i) Falling demand is one cause of deflation.")
    assert [item_label(i.text) for i in extract_items(question)] == ["a.i", "a.ii", "b.i", "b.ii"]
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="Economics", task_type="short_answer",
                           selected_agent_ids=["economics-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, _r, _q = hub.dispatch("t", "economics-specialist", question, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="economics-specialist", report_id="rep-x")
    hub.close()
    unaddressed = [f.message for f in by_code(rc.findings, "INT-REQ-004")]
    assert len(unaddressed) == 1 and "'(b)(ii) Explain how it lowers prices." in unaddressed[0], unaddressed


def test_compound_labels_are_read_in_every_written_form():
    assert [compound_label(t) for t in ("(a)(i) x", "(a) (i) x", "a(i) x", "a)(i) x", "**(b)(ii)** x", "(a) x", "(i) x", "a(b) x")] == [
        "a.i", "a.i", "a.i", "a.i", "b.ii", None, None, None]
    sections = _answer_sections("(a)\nfirst\n(i) one\n(ii) two\n(b)(i) three\n(ii) four\n1. five")
    assert [sorted(s) for _o, s in sections] == [["a"], ["a.i", "i"], ["a.ii", "ii"], ["b", "b.i", "i"], ["b.ii", "ii"], ["1"]]


# ============================================================================================ one fault, one INT-SUBJ-003
POEM = SuppliedText(document_id="doc-ozy", title="Ozymandias", author="Percy Bysshe Shelley",
                    text="I met a traveller from an antique land, Who said: Two vast and trunkless legs of stone Stand in the desert. Near them, on the "
                         "sand, Half sunk a shattered visage lies, whose frown, And wrinkled lip, and sneer of cold command, Tell that its sculptor well "
                         "those passions read. The lone and level sands stretch far away.")
PEER = SuppliedText(document_id="peer:hi-p1", title="History specialist report", author="history-specialist",
                    text="Parliament suspended habeas corpus in March 1817, after the Spa Fields riots.")


def _misattributed(answer: str):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="English A: Literature", task_type="analytical_paragraph",
                           selected_agent_ids=["english-specialist", "dummy-combinator"], allowed_document_ids=[POEM.document_id, PEER.document_id]))
    m, _r, _q = hub.dispatch("t", "english-specialist", "Analyse how Shelley presents power in the poem. Use quotations from the poem.", [POEM, PEER])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id="english-specialist", report_id="rep-x")
    hub.close()
    return rc


def test_one_misattributed_quotation_is_one_int_subj_003_naming_both_codes():
    rc = _misattributed('Shelley writes that "Parliament suspended habeas corpus in March" and the ruin answers the boast of the "sneer of cold command".')
    assert {"CORE-SRC-005", "ES-SRC-008"} <= {f.code for f in rc.structural_findings if f.severity == "error"}
    [f] = by_code(rc.findings, "INT-SUBJ-003")
    assert f.message.startswith("[english] CORE-SRC-005, ES-SRC-008: quotation 'Parliament suspended habeas corpus in March'")
    assert f.claim_ids == ["p1-q01", "p1-point"]


def test_control_two_misattributed_quotations_are_two_faults():
    rc = _misattributed('Shelley writes that "Parliament suspended habeas corpus in March" and adds that it happened "after the Spa Fields riots".')
    subj = by_code(rc.findings, "INT-SUBJ-003")
    quoted = sorted(f.message.split("quotation '")[1].split("'")[0] for f in subj)
    assert quoted == ["Parliament suspended habeas corpus in March", "after the Spa Fields riots"], [f.message[:120] for f in subj]


def test_the_grouping_rule_joins_only_one_family_on_one_quotation_and_shared_claims():
    core = StructuralFinding(code="CORE-SRC-005", severity="error", message="quotation 'a b c' is attributed in its sentence to X (d1) but occurs only in d2", claim_ids=["q1", "s1"])
    eng = StructuralFinding(code="ES-SRC-008", severity="error", message="paragraph 1, sentence 1 attributes the quotation 'a b c' to d1 but the words occur only in d2", claim_ids=["q1"])
    other = StructuralFinding(code="ES-SRC-008", severity="error", message="paragraph 1, sentence 2 attributes the quotation 'x y z' to d1 but the words occur only in d2", claim_ids=["q2"])
    unrelated = StructuralFinding(code="HI-SRC-001", severity="error", message="quotation 'a b c' is attributed to nobody", claim_ids=["q1"])
    assert subject_error_groups([core, eng, other, unrelated]) == [
        (("CORE-SRC-005", "ES-SRC-008"), ["q1", "s1"], core.message), (("ES-SRC-008",), ["q2"], other.message), (("HI-SRC-001",), ["q1"], unrelated.message)]
    assert SAME_FAULT_FAMILIES == (frozenset({"CORE-SRC-005", "ES-SRC-008"}),)


# ============================================================================================ rule held-words
def test_a_quotation_that_holds_only_a_function_word_of_a_text_alters_nothing():
    from tests.branches.r6_texts import HI_T12, HI_T12_Q
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="short_answer",
                           selected_agent_ids=["history-specialist", "dummy-combinator"], allowed_document_ids=[]))
    m, _r, _q = hub.dispatch("t", "history-specialist", HI_T12_Q, [])
    _reply, rc = hub.receive("t", m.message_id, HI_T12, agent_id="history-specialist", report_id="rep-x")
    hub.close()
    assert "wind of change" in HI_T12 and not by_code(rc.findings, "INT-REQ-003"), [f.message[:160] for f in by_code(rc.findings, "INT-REQ-003")]
    assert not _holds_long_words("wind of change", ["wind", "change"]) and _holds_long_words("makes his heart race and his handsly sweat", ["handsly"])


# ============================================================================================ the new readers stay linear
HOSTILE = {
    "blanks": " " * 20_000 + "x", "tabs": "\t" * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x",
    "closing marks": "]" * 20_000 + "x", "mark labels": "(A1) " * 4_000 + "x", "parentheses": "(" * 20_000 + "x", "brackets": "[" * 20_000 + "x",
    "fence openers": "```" * 7_000 + "x", "number words": " and ".join(["twenty"] * 1_800) + " x", "= links": "x = " * 5_000 + "y",
    "list markers": "- " * 10_000 + "x", "compound labels": "(a)(i) " * 3_000 + "x", "bare parents": "(a) (i) " * 2_500 + "x",
    "spanish bounds": "entre 4 y " * 2_000 + "palabras", "subjunctives": "que expongas y propongas " * 800 + "x",
    "label leads": "Paper practice: " * 1_200 + "please skip the plan", "quotations": "quotation '" * 2_000 + "x",
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_new_channel_readers_are_linear_on_hostile_inputs(name):
    text = HOSTILE[name]
    errors = [StructuralFinding(code="CORE-SRC-005" if k % 2 else "ES-SRC-008", severity="error", message=text[:1500], claim_ids=[f"q{k}"]) for k in range(200)]
    t0 = time.process_time()
    extract_constraints(text), extract_items(text), is_context_sentence(text), language_b_items(text), compound_label(text), item_label(text)
    _answer_sections(text), subject_error_groups(errors), _holds_long_words(text, ["x"])
    spent = time.process_time() - t0
    assert spent < 4.0, f"{name}: {spent:.2f} s"


# ============================================================================================ one-fault-once stays linear in the faults
def test_the_one_fault_grouping_reads_thousands_of_faults_in_one_pass():
    """The grouping first compared each family finding with every group made before it (quadratic in the faults: 20,000
    misattributed quotations took seconds). The groups that can still take a code are indexed by (family, quotation, claim,
    code they lack) now; the grouping is the same (a finding joins the earliest group of its family and quotation that
    shares a claim and lacks its code)."""
    def sf(code, quote, claims):
        return StructuralFinding(code=code, severity="error", message=f"the quotation '{quote}' is not in the text", claim_ids=claims)
    for errors in ([sf("CORE-SRC-005", f"w{k}", [f"c{k}"]) for k in range(20_000)],              # every fault its own
                   [sf("CORE-SRC-005", "w", ["c1"]) for _k in range(20_000)],                    # one quotation, one claim, one code
                   [sf(("CORE-SRC-005", "ES-SRC-008")[k % 2], "w", [f"c{k // 2}", "c0"]) for k in range(20_000)]):
        t0 = time.process_time()
        groups = subject_error_groups(errors)
        assert time.process_time() - t0 < 2.0
        assert sum(len(codes) for codes, _c, _m in groups) == len(errors)
    # the grouping itself: the earliest open group sharing a claim; a code never twice in a group; another quotation apart
    got = subject_error_groups([sf("CORE-SRC-005", "a", ["c1"]), sf("CORE-SRC-005", "a", ["c2"]), sf("ES-SRC-008", "a", ["c2", "c1"]),
                                sf("ES-SRC-008", "a", ["c2"]), sf("ES-SRC-008", "b", ["c1"]), sf("CORE-SRC-001", "a", ["c1"])])
    assert got == [(("CORE-SRC-005", "ES-SRC-008"), ["c1", "c2"], "the quotation 'a' is not in the text"),
                   (("CORE-SRC-005", "ES-SRC-008"), ["c2"], "the quotation 'a' is not in the text"),
                   (("ES-SRC-008",), ["c1"], "the quotation 'b' is not in the text"),
                   (("CORE-SRC-001",), ["c1"], "the quotation 'a' is not in the text")]
