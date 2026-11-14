"""Round-8 (integrated round c1) clearance regressions of the parsers and packs (owner: parsers).

Each test reproduces a fault the c1 overseers named on a recorded answer (``c1_texts``) or on the probe sentence of their report, with
a control that keeps the rule asserted:

* worked arithmetic: a scale word written once, after the stated result, governs the line ('10.0 − 4.0 = 6.0 million tonnes per year'
  holds; '10.0 − 4.0 = 7.0 million ...' and '10.0 million − 4.0 million = 7.0 million' are still refuted);
* a per cent change written with decimals is held to its written precision ('an increase of 3.40%' for 3.04% is refuted; the
  half-point floor stays for a whole per cent);
* 'fell 12% from $250 to $230' is decided without 'by';
* study attributions in 'et al.', '&', comma-year and 'and colleagues' form are PS-SRC-001, and 'et al.' ends no sentence;
* a 'Model:' line of the writer's own words is no quotation, while a model label over an altered line of the text still is;
* a quotation is credited by the clause that holds it ('the text gives', not the colleague named in a later clause);
* self-certifications in the four c1 wordings, English and Spanish, are named on every branch and never material;
* a 'Sources:' line and a note read by what it says (a caveat, a decline, an offer, a request to send work back) are notes: no
  claim of the answer, no words or paragraph of a bound, never material; a framing remark and a part's title are never the point;
* sentence punctuation inside a closing mark is not part of a quotation's excerpt;
* a quoted statement the sentence judges true or false, and the word a reader is told to reply with, are mentions;
* the marks of marking feedback are decided by the engine;
* a per cent restated from written arithmetic a STEM check decided is not named undecided;
* a figure counts in the near-miss reading of an altered quotation.
"""
from __future__ import annotations

import pytest

from epinoic_logic.adapters import markdown as md
from epinoic_logic.adapters.sources import nearest_text, own_model_words
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser, split_sentences
from epinoic_logic.branches.packs import PsychologyPack, study_attributions
from epinoic_logic.branches.quant import extract_quant_checks
from epinoic_logic.branches.worked import worked_problems
from epinoic_logic.channel.request_parser import count_answer_words, count_paragraphs
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import AgentRole, WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

from ..adapters.hostile_inputs import all_inputs, bounded
from . import c1_texts as C

KEY = b"branches-c1-clearance-parsers-key-01"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def through_hub(text: str, question: str = "q", *, subject: str = "Economics", agent: str = "economics-specialist", texts=(),
                task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def codes(rc) -> list[str]:
    return [f.code for f in list(rc.findings) + list(rc.structural_findings)]


def findings(rc, code: str) -> list:
    return [f for f in list(rc.findings) + list(rc.structural_findings) if f.code == code]


def claims_of(reply) -> list[dict]:
    return reply.payload["claims"]


def worked_status(line: str) -> str:
    [wp] = worked_problems(line, report_id="r", request_id="q", prefix="economics-worked")
    return verify(Problem.model_validate(wp.problem), CFG).status.value


# ------------------------------------------------------------------ worked arithmetic: a scale word after the result only


@pytest.mark.parametrize("line,expected", [
    ("Before the tariff (2025): 10.0 − 4.0 = 6.0 million tonnes per year", "ENTAILED"),          # ec-p8a g3.2
    ("After the tariff (2026): 9.0 − 5.5 = 3.5 million tonnes per year", "ENTAILED"),            # ec-p8a g3.3
    ("Welfare loss = $112.50 + $75.00 = $187.50 million per year", "ENTAILED"),                  # ec-p8a g11.4
    ("Before: $600 × 4.0 million = $2,400 million per year", "ENTAILED"),                        # the scale on an operand: as written
    ("Total = $1,500,000 + $500,000 = $2 million", "ENTAILED"),                                  # operands written in full: as written
    ("Imports = 10.0 − 4.0 = 7.0 million tonnes per year", "COUNTEREXAMPLE"),                     # wrong in either reading
    ("Imports = 10.0 million − 4.0 million = 7.0 million tonnes", "COUNTEREXAMPLE"),              # X1c: the scale on every figure
    ("Tax revenue = $0.40 × 105 million litres = $52 million.", "COUNTEREXAMPLE"),
])
def test_a_scale_word_after_the_result_governs_a_line_whose_operands_carry_none(line, expected):
    assert worked_status(line) == expected


@pytest.mark.parametrize("line,expected", [
    ("Real rate = 4.00% − 5.20% (inflation from paragraph [2]) = −1.20%", "ENTAILED"),        # a bracketed comment is set aside
    ("Real rate = 4.00% − 5.20% (inflation from paragraph [2]) = −2.10%", "COUNTEREXAMPLE"),
    ("NPV = total present value − cost = $315,900 − $280,000 = +$35,900", "ENTAILED"),        # a word-formula head, a result with '+'
    ("NPV = total present value − cost = $315,900 − $280,000 = +$53,900", "COUNTEREXAMPLE"),
])
def test_a_bracketed_comment_inside_a_worked_line_is_set_aside(line, expected):
    assert worked_status(line) == expected


_RS_CHAIN = ("rs = 1 − (6 × Σd²) ÷ (n³ − n)\n= 1 − (6 × 66) ÷ (6³ − 6)\n= 1 − 396 ÷ 210\n= 1 − {step}\n= {result}, so rs = −0.89 (to 2 decimal "
             "places)\n")


@pytest.mark.parametrize("line,expected", [
    (_RS_CHAIN.format(step="1.8857", result="−0.8857"), "ENTAILED"),        # ge-t14's Spearman chain, a formula in symbols at its head
    (_RS_CHAIN.format(step="1.5857", result="−0.8857"), "COUNTEREXAMPLE"),  # c1 adversarial ge-t14-rs: 396 ÷ 210 stated as 1.5857
    (_RS_CHAIN.format(step="1.8857", result="−0.7857"), "COUNTEREXAMPLE"),
    ("PV = 1000 ÷ (1 + r)^n = 1000 ÷ 1.05^3 = 863.84", "ENTAILED"),
    ("PV = 1000 ÷ (1 + r)^n = 1000 ÷ 1.05^3 = 836.84", "COUNTEREXAMPLE"),
    ("Area = 3.14 × 5² = 78.5 m²", "ENTAILED"),                                 # a superscript power after a figure
    ("Area = 3.14 × 5² = 87.5 m²", "COUNTEREXAMPLE"),
    ("Value = 1,000 × 1.05³ = 1,157.63", "ENTAILED"),
])
def test_a_formula_in_symbols_before_the_working_is_set_aside_and_a_superscript_power_is_read(line, expected):
    assert worked_status(line) == expected


@pytest.mark.parametrize("line,expected", [
    # c1 adversarial ec-t14-unemp: an '=' inside a restatement in brackets is no link of the chain
    ("Formula: unemployment rate = unemployed ÷ labour force × 100\n= 0.762 million ÷ 12.70 million × 100 (762 thousand = 0.762 million)\n"
     "= 6.50%", "COUNTEREXAMPLE"),
    ("Formula: unemployment rate = unemployed ÷ labour force × 100\n= 0.762 million ÷ 12.70 million × 100 (762 thousand = 0.762 million)\n"
     "= 6.00%", "ENTAILED"),
    # c1 adversarial ec-t14-growth: a formula in words and symbols at the head of the chain is its statement
    ("Growth rate = (real GDP 2025 − real GDP 2024) ÷ real GDP 2024 × 100\n= (519.406 − 525.000) ÷ 525.000 × 100\n= −1.70%", "COUNTEREXAMPLE"),
    ("Growth rate = (real GDP 2025 − real GDP 2024) ÷ real GDP 2024 × 100\n= (519.406 − 525.000) ÷ 525.000 × 100\n= −1.07%", "ENTAILED"),
])
def test_a_restatement_in_brackets_and_a_formula_head_leave_the_chain_decided(line, expected):
    assert worked_status(line) == expected


@pytest.mark.parametrize("line,expected", [
    ("Change = $4,125 million − $2,400 million = +$1,725 million per year (an increase of 81.88%)", "COUNTEREXAMPLE"),  # ec-p8a-pct
    ("Change = $4,125 million − $2,400 million = +$1,725 million per year (an increase of 71.88%)", "ENTAILED"),
    ("Change = $4,125 million − $2,400 million = +$1,725 million per year (an increase of 72%)", "ENTAILED"),
    ("Change = $653.8 − $682.5 = −$28.7 (a fall of 4.2%)", "ENTAILED"),
    ("Change = $653.8 − $682.5 = −$28.7 (a fall of 6%)", "COUNTEREXAMPLE"),
])
def test_a_relative_change_stated_after_a_difference_is_decided(line, expected):
    from epinoic_logic.branches.worked import worked_problems as wps
    built = wps(line, report_id="r", request_id="q", prefix="w")
    assert len(built) == 2 and "the relative change stated after the difference" in built[1].description
    assert verify(Problem.model_validate(built[0].problem), CFG).status.value == "ENTAILED"
    assert verify(Problem.model_validate(built[1].problem), CFG).status.value == expected


@pytest.mark.parametrize("line", [
    "Imports fall: 10.0 − 4.0 = 6.0 million tonnes (a fall of 60%)",     # old − new: the stated sign is not the direction's, not read
    "Profit = $500 − $400 = $100 (an increase of 20% of revenue)",       # a per cent of something else
    "Total = $500 + $400 = $900 (an increase of 20%)",                   # no difference
])
def test_control_a_relative_change_is_read_only_after_a_difference_in_its_own_direction(line):
    assert len(worked_problems(line, report_id="r", request_id="q", prefix="w")) == 1


def test_the_ec_p8a_relative_change_slip_is_named_on_its_claim():
    _reply, rc = through_hub(C.EC_P8A.replace("an increase of 71.88%", "an increase of 81.88%"), C.EC_P8A_Q, subject="Economics",
                             agent="economics-specialist", task_type="data_response")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "81.88" in f.message and f.claim_ids], codes(rc)


def test_a_symbol_after_the_first_figures_still_refuses_the_line_and_the_spearman_slip_is_named_on_the_generic_branch():
    assert worked_problems("rs = 1 − (6 × Σd²) ÷ (n³ − n) = 1 − 6 × Σd² ÷ 210 = −0.8857", report_id="r", request_id="q", prefix="w") == []
    assert worked_problems("y = 2 × 3 + x = 7", report_id="r", request_id="q", prefix="w") == []
    _reply, rc = through_hub(C.GE_T14.replace("= 1 − 1.8857", "= 1 − 1.5857"), subject="Geography", agent="geography-specialist",
                             task_type="feedback")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "1.5857" in f.message], codes(rc)
    _reply, rc = through_hub(C.GE_T14, subject="Geography", agent="geography-specialist", task_type="feedback")
    assert not findings(rc, "INT-SUBJ-001"), codes(rc)


@pytest.mark.parametrize("sentence,expected", [
    ("Also: January's total cash outflow is $11,300 (5,200 + 4,000 + 1,500 + 600), not $11,100.", "ENTAILED"),
    ("Also: January's total cash outflow is $11,400 (5,200 + 4,000 + 1,500 + 600), not $11,100.", "COUNTEREXAMPLE"),
    ("Producers and the government gain $1,237.50 million per year in total ($712.50 + $525).", "ENTAILED"),
    ("Producers and the government gain $1,327.50 million per year in total ($712.50 + $525).", "COUNTEREXAMPLE"),
])
def test_a_figure_stated_with_its_parts_in_brackets_is_decided(sentence, expected):
    from epinoic_logic.branches.worked import breakdown_problems
    [wp] = breakdown_problems(sentence, report_id="r", request_id="q", prefix="business-worked")
    assert verify(Problem.model_validate(wp.problem), CFG).status.value == expected
    _reply, rc = through_hub(sentence, subject="Business Management", agent="business-management-specialist")
    assert bool([f for f in findings(rc, "INT-SUBJ-001") if "parts in brackets" in f.message]) == (expected == "COUNTEREXAMPLE")
    from epinoic_logic.branches.worked import breakdown_problems as bp
    assert bp("The totals for 4,039 (2019 + 2020) were high.", report_id="r", request_id="q", prefix="w") == []  # years are no parts


def test_the_ec_p8a_answer_carries_no_worked_arithmetic_error_and_a_business_slip_is_still_named():
    _reply, rc = through_hub(C.EC_P8A, C.EC_P8A_Q, subject="Economics", agent="economics-specialist", task_type="data_response")
    worked = [fc for fc in rc.formal_checks if "-worked-" in fc.constraint_id]
    assert worked and all(fc.formal_status == "ENTAILED" for fc in worked), [(fc.constraint_id, fc.formal_status) for fc in worked]
    assert not findings(rc, "INT-SUBJ-001")
    _reply, bm = through_hub("Profit = $60,000 − $45,000 = $25,000.", subject="Business Management", agent="business-management-specialist")
    assert [f for f in findings(bm, "INT-SUBJ-001") if "worked_arithmetic" in f.message]


# ------------------------------------------------------------------ per cent changes held to their written precision


@pytest.mark.parametrize("sentence,expected", [
    ("The CPI rose from 112.0 to 115.4, an increase of 3.40%.", "COUNTEREXAMPLE"),   # F27: a transposed figure (3.04%)
    ("The CPI rose from 112.0 to 115.4, an increase of 3.04%.", "ENTAILED"),
    ("The CPI rose from 112.0 to 115.4, an increase of 3%.", "ENTAILED"),           # a whole per cent keeps the half-point floor
    ("Output rose from 4.2 million to 5.1 million, an increase of 21.7%.", "ENTAILED"),  # rounded figures widen the band
    ("Revenue rose from $2,400 million to $4,125 million, an increase of 71.88%.", "ENTAILED"),
])
def test_a_per_cent_change_written_with_decimals_is_held_to_its_written_precision(sentence, expected):
    [(kind, status)] = [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(sentence, request_id="r", claim_id="c")]
    assert (kind, status) == ("percent_change", expected)


@pytest.mark.parametrize("sentence,expected", [
    ("The price fell 12% from $250 to $230.", "COUNTEREXAMPLE"),   # F23: an 8% fall
    ("The price fell 8% from $250 to $230.", "ENTAILED"),
    ("Sales fell 20% from $500 to $450.", "COUNTEREXAMPLE"),
    ("Output rose 25% from 400 to 500 tonnes.", "ENTAILED"),
])
def test_rose_or_fell_x_per_cent_is_decided_without_by(sentence, expected):
    assert [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(sentence, request_id="r", claim_id="c")] == [("percent_change", expected)]


def test_the_re_referenced_corpus_text_differs_by_the_fell_x_per_cent_rule_alone(monkeypatch):
    # the general reading's reference corpus (test_quant_si_reading) changed on one text, 'prices fell 25.5 per cent in January 1931',
    # now named undecided; with the earlier pattern ('by' required after the verb) every text reproduces its earlier digest byte for byte
    import re

    from epinoic_logic.branches import packs, quant
    from epinoic_logic.branches import worked as worked_module

    from ..timing import empty_caches
    from .test_quant_si_reading import REFERENCE, _digest

    changed = [item for item in REFERENCE["items"] if "sha256_before_c1" in item]
    assert len(changed) == 1 and changed[0]["sha256_before_c1"] != changed[0]["sha256"]
    assert [(u.phrase, u.reason.split(" and ")[0]) for u in quant.undecided_quant_statements(changed[0]["text"])] == \
        [("fell 25.5 per cent", "no figures are stated with it in its sentence")]
    earlier = re.compile(
        rf"(?:an?\s+)?{quant._DIR_NOUN}\s+of\s+(?:({quant._QUAL})\s+)?{quant._AMOUNT}\s*{quant._PCT_UNIT}(?!\s*points?\b)"
        rf"|(?:an?\s+)?(?:({quant._QUAL})\s+)?{quant._AMOUNT}\s*{quant._PCT_UNIT}\s+{quant._DIR_NOUN}"
        rf"|{quant._DIR_VERB}\s+by\s+(?:({quant._QUAL})\s+)?{quant._AMOUNT}\s*{quant._PCT_UNIT}(?!\s*points?\b)", re.IGNORECASE)

    def clear() -> None:
        for module in (md, packs, quant, worked_module):
            for value in vars(module).values():
                if hasattr(value, "cache_clear"):
                    value.cache_clear()
        empty_caches()

    monkeypatch.setattr(quant, "_PCT_CHANGE_RE", earlier)
    clear()
    try:
        mismatched = [item["text"][:80] for item in REFERENCE["items"] if _digest(item["text"]) != item.get("sha256_before_c1", item["sha256"])]
    finally:
        monkeypatch.undo()
        clear()
    assert mismatched == []
    assert _digest(changed[0]["text"]) == changed[0]["sha256"]


# ------------------------------------------------------------------ study attributions


@pytest.mark.parametrize("sentence,attribution", [
    ("Halvorsen et al. (2019) found that anchoring persists in experts.", "Halvorsen et al. (2019)"),
    ("Anchoring persists in experts (Halvorsen & Lund, 2019).", "(Halvorsen & Lund, 2019)"),
    ("Halvorsen and colleagues (2019) found that anchoring persists in experts.", "Halvorsen and colleagues (2019)"),
])
def test_every_in_text_citation_form_is_a_study_attribution_on_the_psychology_branch(sentence, attribution):
    assert study_attributions(sentence) == [attribution]
    reply, rc = through_hub("Anchoring is a bias in judgement. " + sentence, subject="Psychology", agent="psychology-specialist")
    named = [f for f in findings(rc, "PS-SRC-001") if attribution in f.message]
    assert named, codes(rc)


def test_et_al_ends_no_sentence_and_a_date_or_table_in_brackets_is_no_study():
    assert split_sentences("Draganski et al. (2004) is not relevant here, but Halvorsen et al. (2019) found it. Next.") == [
        "Draganski et al. (2004) is not relevant here, but Halvorsen et al. (2019) found it.", "Next."]
    assert study_attributions("The scheme began (June, 2019) as in (Table 1, 2019).") == []
    assert study_attributions("(Maguire et al., 2000; Woollett & Maguire, 2011)") == ["(Maguire et al., 2000)", "(Woollett & Maguire, 2011)"]


# ------------------------------------------------------------------ the writer's own model sentence; credit by clause

STUDENT = SuppliedText(document_id="doc-student", title="Student essay", author="the student",
                       text="Both books are about people who are excluded. Shelley uses lots of imagery and emotive language here to show he is lonely. "
                            "The creature says misery made me a fiend. Jane is very sad at Gateshead.")


def test_a_model_line_of_the_writers_own_words_is_no_quotation_and_an_altered_line_of_the_text_still_is():
    model = ('Model: "Both novels exclude their outsider through appearance or status, but Shelley\'s creature is refused for how he looks, '
             'while Brontë\'s Jane is refused for her dependence."')
    reply, rc = through_hub("Your essay compares the two works.\n\n" + model, "Mark my essay.", subject="English A: Literature",
                            agent="english-a-literature-specialist", texts=[STUDENT])
    assert not findings(rc, "INT-REQ-003") and not findings(rc, "ES-SRC-001"), codes(rc)
    # round 9 (c2), made stricter: the core pack charges the model sentence neither as an unlocated quotation (CORE-SRC-006) nor, through
    # the channel's copy of a branch error, as INT-SUBJ-003, nor as an unverifiable quotation (CORE-SRC-003)
    assert not findings(rc, "CORE-SRC-006") and not findings(rc, "INT-SUBJ-003") and not findings(rc, "CORE-SRC-003"), codes(rc)
    assert own_model_words(model, model.split('"')[1], {"doc-student": STUDENT})
    # control: a model label over the student's own line with one word changed is an altered quotation, checked as any other
    altered = 'Model: "Shelley uses lots of imagery and emotive language here to show he is alone."'
    reply, rc = through_hub("Your essay compares the two works.\n\n" + altered, "Mark my essay.", subject="English A: Literature",
                            agent="english-a-literature-specialist", texts=[STUDENT])
    assert findings(rc, "INT-REQ-003"), codes(rc)


def test_a_text_named_by_its_kind_is_read_by_clause_only():
    # over a whole sentence (the generic, History and STEM parsers' naming), 'the text' names no supplied text: 'the trap is "toda",
    # since the text says almost half was lost' quotes a word of the request, not of the article (round 7 sp-t13); the literary cues stay
    from epinoic_logic.adapters.english_specialist.parser import documents_named
    article = {"doc-a": SuppliedText(document_id="doc-a", title="Los huertos", author="", text="Se perdió casi la mitad de la cosecha.")}
    assert documents_named("Why: fourth paragraph; the trap is ..., since the text says almost half was lost.", article) == []
    assert documents_named("The extract says almost half was lost.", article) == ["doc-a"]


def test_a_quotation_is_credited_by_its_own_clause_not_by_a_colleague_named_in_a_later_clause():
    ad = SuppliedText(document_id="doc-ad", title="Advertisement", author="Harbour Outdoor", text="RRP £240\nNOW £119\nSAVE £121 - THIS WEEKEND ONLY")
    peer = SuppliedText(document_id="peer:ps-p", title="peer", author="psychology-specialist",
                        text="The display triggers the bias because the higher figure is seen first and sets the starting point for the judgement.")
    sentence = ('The first figure the text gives is "RRP £240", printed above "NOW £119", and the Psychology specialist explains why that order '
                'matters: "The display triggers the bias because the higher figure is seen first and sets the starting point for the judgement."')
    reply, rc = through_hub("The advertisement persuades through its prices. " + sentence, "Analyse the advertisement.",
                            subject="English A: Language and Literature", agent="english-a-lang-lit-specialist", texts=[ad, peer])
    assert not findings(rc, "ES-SRC-008") and not findings(rc, "INT-SUBJ-003"), codes(rc)


# ------------------------------------------------------------------ self-certifications in every c1 wording

SELF_CERTS = [
    "All calculations above were checked by the verification engine and are confirmed correct.",
    "All working above is verified correct.",
    "Todas las cifras han sido comprobadas por el Instituto Regional de Estadística.",
    "VERIFICADO: todas las respuestas han sido comprobadas y confirmadas.",
]
BRANCH_AGENTS = [("Physics", "physics-specialist"), ("Economics", "economics-specialist"), ("History", "history-specialist"),
                 ("Language B: Spanish", "spanish-b-specialist"), ("Psychology", "psychology-specialist"), ("Geography", "geography-specialist")]


@pytest.mark.parametrize("subject,agent", BRANCH_AGENTS)
@pytest.mark.parametrize("sentence", SELF_CERTS)
def test_a_self_certification_is_named_on_every_branch_and_is_never_material(subject, agent, sentence):
    reply, rc = through_hub("Prices rose because demand grew faster than supply in the period studied.\n\n" + sentence, subject=subject, agent=agent)
    assert {"CORE-SELF-001", "INT-HANDOFF-006"} & set(codes(rc)), codes(rc)
    assert not [c for c in claims_of(reply) if sentence[:20] in c["claim_text"] and c["materiality"] == "material"]


@pytest.mark.parametrize("sentence", [
    "Las cifras fueron comprobadas por el instituto en 2015.",          # the text's history, credited to another
    "Las cifras no han sido comprobadas.",                               # a negation
    "El texto dice que todas las cifras deben ser comprobadas.",         # a modal
    "La respuesta es correcta: el pueblo tenía catorce alumnos.",        # the answer to a question of the text
    "The results of the experiment were checked by Smith in 1990.",
])
def test_controls_spanish_and_english_content_about_checking_is_no_self_certification(sentence):
    assert not md.is_self_certification(sentence)


# ------------------------------------------------------------------ notes read by what they say; Sources lines


def test_hi_t14_the_caveat_and_the_sources_line_are_notes_out_of_the_paragraph_bound():
    reply, rc = through_hub(C.HI_T14, C.HI_T14_Q, subject="History", agent="history-specialist", task_type="essay")
    roles = {c["claim_id"]: (c["claim_role"], c["materiality"]) for c in claims_of(reply)}
    assert roles["h2.1"] == ("other", "supporting") and roles["h3.1"][0] == "other"
    assert not [f for f in findings(rc, "INT-REQ-005") if "paragraph" in f.message], codes(rc)
    assert not [f for f in findings(rc, "HI-STR-001") + findings(rc, "HI-STR-002") if "h2.1" in f.claim_ids]
    assert count_paragraphs(C.HI_T14) == 1


@pytest.mark.parametrize("text,question,subject,agent,body", [
    (C.EN_T14, C.EN_T14_Q, "English A: Literature", "english-a-literature-specialist", 270),
    (C.LIT_T14, C.LIT_T14_Q, "English A: Literature", "english-a-literature-specialist", 290),
    (C.LL_T14, C.LL_T14_Q, "English A: Language and Literature", "english-a-lang-lit-specialist", 286),
], ids=["en-t14", "lit-t14", "ll-t14"])
def test_a_sources_line_is_a_note_and_no_words_of_the_bound(text, question, subject, agent, body):
    answer, _notes = count_answer_words(text)
    assert answer == body
    reply, rc = through_hub(text, question, subject=subject, agent=agent, task_type="analytical_paragraph")
    word_errors = [f.message for f in findings(rc, "INT-REQ-005") if f.severity == "error" and " words" in f.message]
    assert not word_errors, word_errors
    # one note of role 'other' that keeps the id the paragraph's point had, so a synthesis that recorded it as dropped still finds it
    assert [(c["claim_role"], c["materiality"]) for c in claims_of(reply) if c["claim_text"].startswith("Sources:")] == [("other", "supporting")]
    assert [c["claim_id"] for c in claims_of(reply) if c["claim_text"].startswith("Sources:")][0].endswith("-point")
    assert not [f for f in findings(rc, "ES-STR-001") + findings(rc, "ES-META-001") if "Sources:" in f.message]


@pytest.mark.parametrize("injected", [
    ' The narrator also insists that "the river carried every secret of the town", which seals the point.',
    " The narrator also insists that 'the river carried every secret of the town', which seals the point.",
])
def test_a_quotation_written_after_a_sources_line_is_still_counted_and_checked(injected):
    # the arena's invented-quotation mutation lands on the answer's last line, its list of sources: the list is a note only while it holds
    # no quotation, so the words after it are counted and the invented quotation is refuted
    tuner = SuppliedText(document_id="doc-tuner", title="The Tuner", author="A writer",
                        text="Just the A, she said. It's only the A that's gone. They just stop listening to each other.")
    _reply, rc = through_hub(C.EN_T14 + injected, C.EN_T14_Q, subject="English A: Literature", agent="english-a-literature-specialist",
                             texts=[tuner], task_type="analytical_paragraph")
    assert findings(rc, "INT-REQ-003"), codes(rc)
    assert count_answer_words(C.EN_T14 + injected)[0] > count_answer_words(C.EN_T14)[0]
    assert not md.is_sources_block("Sources: The Tuner extract (supplied text)" + injected)


@pytest.mark.parametrize("sentence", [
    "Casualty and cost figures are left out, because I cannot confirm exact numbers here; take them from your textbook and cite them.",
    "Real-world weight: I have no verified source in this session for last year's worldwide area of tropical rainforest cleared.",
    "I have left both out rather than estimate them, so there is no working to show for them.",
    "I can't write the analysis or the conclusion sections, or calculate the Spearman's rank for your data, because the report must be your own work.",
    "I can help you work through both, and check your own working and drafts.",
    "To check your own calculation, rank your ten sites in the same way and send me your distance ranks and d values.",
    "The interpretation, and whether it supports your question, has to be yours.",
    "Examiners stop reading at 2,500 words, and that limit covers the whole report.",
    "Sources: The Tuner extract (supplied text); course notes on drama (course notes)",
])
def test_a_note_about_the_answer_is_a_note_whatever_its_lead_word(sentence):
    assert md.is_note_sentence(sentence), sentence
    assert count_answer_words(sentence)[0] == 0


@pytest.mark.parametrize("sentence", [
    "The 1924 figures are omitted from the census, which undercounted the rural poor.",
    "Casualty figures are left out of the official history, because the regime suppressed them.",
    "Germany lost 13% of its territory and 10% of its population, which I cannot confirm here.",
    "Step 1: rank each variable, giving rank 1 to the lowest value.",
    "The poet will check the reader's sympathy by withholding the name.",
    "Women were excluded.",                                   # an omission with no reason of the writer's is history
    "Casualty figures were not given by the regime.",
    "Firms share your data with advertisers.",                # no request to send work back
])
def test_controls_content_that_resembles_a_note_keeps_its_substance(sentence):
    assert not md.is_note_sentence(sentence), sentence


def parse(text: str, subject: str = "Geography", agent: str = "geography-specialist") -> SpecialistReport:
    return GenericTextParser(agent_id=agent).parse_response(text, request_id="r", task_id="t", report_id="rep", subject=subject, task_type="short_answer")


def test_ge_t14_no_decline_offer_request_remark_or_table_header_is_material():
    rep = parse(C.GE_T14)
    material = {c.claim_id.split("@")[0]: c.claim_text for c in rep.claims if c.materiality == "material"}
    for cid in ("g1.1", "g1.2", "g1.3", "g6.1", "g9.1", "g14.1", "g14.2", "g14.3", "g15.1", "g17.1"):
        assert cid not in material, (cid, material.get(cid))
    assert "g7.1" in material  # the method's steps keep their points


def test_ess_ec_ps_frames_and_titles_are_never_the_point():
    ess = {c.claim_id: c for c in parse(C.ESS_T14, "Environmental Systems and Societies", "ess-specialist").claims}
    assert not [cid for cid, c in ess.items() if cid.startswith("s10.") and c.materiality == "material"]
    ec = {c.claim_id.split("@")[0]: c for c in parse(C.EC_P8A, "Economics", "economics-specialist").claims}
    assert ec["g1.1"].materiality == "supporting" and ec["g1.2"].materiality == "material"   # practice data frames the answer
    assert ec["g12.1"].materiality == "supporting"                                           # the part's title over its answer
    ps = parse("- Unit 1, causality. Claim: random allocation supports a causal claim. Evidence: the groups differed. Weighing: a strength.",
               "Psychology", "psychology-specialist")
    roles = [(c.claim_text.split(":")[0], c.materiality) for c in ps.claims]
    assert roles[0] == ("Unit 1, causality.", "supporting") and roles[1] == ("Claim", "material")
    # control: a short answer on a part's label is still the part's answer
    short = parse("(a) Primary consumer\n\n(b) It eats the grass, so it is a herbivore.", "Biology", "biology-specialist")
    assert short.claims[0].materiality == "material"


def test_a_short_answers_last_claim_is_its_material_answer_and_a_fill_in_blank_stays_in_the_claim_text():
    rep = parse("The mean is 42 pedestrians per 10 minutes.")
    assert [(c.claim_role, c.materiality) for c in rep.claims] == [("quantitative", "material")]
    for value in ("rs = −0.89 (to 2 decimal places)", "The total cost was about $11,300.", "Total cost = $11,300"):
        assert [c.materiality for c in parse(value).claims] == ["material"], value
    # control: a short answer that states no value of its own keeps its materiality (repair round 4)
    assert parse("River pollution in the town fell in 2016.").claims[0].materiality == "supporting"
    skeleton = "Model skeleton: n = 1.15 ÷ 46.08 = ____ mol (unrounded); ΔT = 42.5 − 18.0 = ____ K; **bold** stays plain."
    assert md.strip_markup(skeleton) == "Model skeleton: n = 1.15 ÷ 46.08 = ____ mol (unrounded); ΔT = 42.5 − 18.0 = ____ K; bold stays plain."
    assert md.strip_emphasis("a __b__ c") == md.EMPHASIS_RE.sub(r"\2", "a __b__ c")  # the emphasis reader itself is unchanged


@pytest.mark.parametrize("sentence,subject,agent,named", [
    ("Doubling the sample would halve the error.", "Computer Science", "cs-specialist", False),       # no figure: nothing to check
    ("The risk of a breach doubled after the merger.", "Economics", "economics-specialist", False),
    ("Prices rose three times faster than wages.", "Economics", "economics-specialist", False),
    ("The firm doubled its output, from 400 to 900 units.", "Economics", "economics-specialist", True),  # figures: decided and refuted
])
def test_a_fold_word_with_no_figure_is_not_named_undecided(sentence, subject, agent, named):
    _reply, rc = through_hub(sentence, subject=subject, agent=agent)
    assert not findings(rc, "CORE-QNT-001"), [f.message for f in findings(rc, "CORE-QNT-001")]
    assert bool(findings(rc, "INT-SUBJ-001")) == named


def test_control_a_fold_word_in_a_paragraph_of_figures_is_still_named_undecided():
    # the fold may be one of the paragraph's figures: reported, not skipped (round 4)
    _reply, rc = through_hub("Output stood at 400 units in 2019. The risk of a breach doubled after the merger.", subject="Economics",
                             agent="economics-specialist")
    assert [f for f in findings(rc, "CORE-QNT-001") if "doubled" in f.message], codes(rc)


# ------------------------------------------------------------------ quotations: closing punctuation, mentions, near misses

PEER_EC = SuppliedText(document_id="peer:ec-p8a", title="peer", author="economics-specialist", text=C.EC_P8A)


def test_sentence_punctuation_inside_the_closing_mark_is_no_part_of_the_excerpt():
    good = ('The Economics specialist\'s analysis states: "I assume, as the data show, that the whole $150 tariff passes into the price paid in '
            'Calvessa." A firm that buys steel therefore pays more.')
    _reply, rc = through_hub(good, subject="Business Management", agent="business-management-specialist", texts=[PEER_EC])
    assert not findings(rc, "INT-REQ-003"), [f.message for f in findings(rc, "INT-REQ-003")]
    _reply, rc = through_hub(good.replace("$150", "$160"), subject="Business Management", agent="business-management-specialist", texts=[PEER_EC])
    assert findings(rc, "INT-REQ-003")  # control: an altered figure is still not found


CASE = SuppliedText(document_id="doc-brackwater", title="Brackwater Garden Buildings Ltd (case study, supplied text)", author="Task data",
                    text="Brackwater Garden Buildings Ltd makes steel garden sheds.\n\nThe finance director says: \"The tariff could be removed after the next "
                         "election, so we should not rely on it.\"")


def test_a_peers_words_credited_to_a_person_the_case_names_are_a_wrong_credit_and_a_peers_figure_put_at_is_read():
    text = 'The firm buys steel in Calvessa. The finance director says that "the price rises from $600 to $750 per tonne".'
    _reply, rc = through_hub(text, subject="Business Management", agent="business-management-specialist", texts=[CASE, PEER_EC])
    assert [f for f in findings(rc, "CORE-SRC-005") if "finance director" in f.message], codes(rc)
    _reply, rc = through_hub("The firm buys steel. The Economics specialist puts the tariff revenue at $552 million per year.",
                             subject="Business Management", agent="business-management-specialist", texts=[CASE, PEER_EC])
    assert [f for f in findings(rc, "INT-REQ-014") if "552" in f.message], codes(rc)
    _reply, rc = through_hub("The firm buys steel. The Economics specialist puts the tariff revenue at $525 million per year.",
                             subject="Business Management", agent="business-management-specialist", texts=[CASE, PEER_EC])
    assert not findings(rc, "INT-REQ-014")  # control: the peer's own figure
    assert md.is_peer_attribution('The History specialist supplies the frame: "the boycott lasted 381 days".')


SPANISH = SuppliedText(document_id="doc-valdeoca", title="Valdeoca", author="Diario",
                       text="La escuela de Valdeoca reabrió en septiembre con catorce alumnos, después de ocho años cerrada.")


def test_a_judged_statement_and_a_reply_word_are_mentions_not_invented_quotations():
    judged = 'Why: the text says the school reopened with fourteen pupils, so "more than twenty" is false.'
    _reply, rc = through_hub(judged, "a) La escuela reabrió con más de veinte alumnos. V/F", subject="Language B: Spanish", agent="spanish-b-specialist",
                             texts=[SPANISH], task_type="reading_comprehension")
    assert not findings(rc, "INT-REQ-003"), [f.message for f in findings(rc, "INT-REQ-003")]
    _reply, rc = through_hub("The plan needs your approval first. Reply \"approve\" and I will write the full answer.", subject="Psychology",
                             agent="psychology-specialist", texts=[SPANISH])
    assert not findings(rc, "CORE-SRC-003")
    # control: the same words presented as the text's own are still an invented quotation
    _reply, rc = through_hub('The text says the school had "more than twenty pupils in its first year".', "q", subject="Language B: Spanish",
                             agent="spanish-b-specialist", texts=[SPANISH], task_type="reading_comprehension")
    assert findings(rc, "INT-REQ-003")


def test_a_figure_counts_in_the_near_miss_reading():
    doc = {"t": SuppliedText(document_id="t", text="Spending fell as consumer confidence dropped to its lowest level since 2020.")}
    assert nearest_text("consumer confidence dropped to its lowest level since 2019", doc) == ("t", ["'2019'"])
    assert nearest_text("consumer confidence dropped to its lowest level since 2020", doc) == ("t", [])


# ------------------------------------------------------------------ marks of marking feedback; a restated STEM result


def test_the_marks_of_marking_feedback_are_decided_by_the_engine():
    _reply, rc = through_hub(C.BM_T14, C.BM_T14_Q, subject="Business Management", agent="business-management-specialist", task_type="marking_feedback")
    marks = [fc for fc in rc.formal_checks if "-marks-" in fc.constraint_id]
    assert len(marks) == 5 and all(fc.formal_status == "ENTAILED" for fc in marks)
    bad = C.BM_T14.replace("Provisional total: 6 out of 11 (range 5–7)", "Provisional total: 8 out of 11 (range 7–9)")
    _reply, rc = through_hub(bad, C.BM_T14_Q, subject="Business Management", agent="business-management-specialist", task_type="marking_feedback")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "marks_arithmetic" in f.message]
    over = C.BM_T14.replace("Provisional mark: 1 out of 2 ", "Provisional mark: 6 out of 5 ")
    _reply, rc = through_hub(over, C.BM_T14_Q, subject="Business Management", agent="business-management-specialist", task_type="marking_feedback")
    assert [f for f in findings(rc, "INT-SUBJ-001") if "6 out of 5" in f.message]
    # control: outside a marking task the marks are not read
    _reply, rc = through_hub(bad, C.BM_T14_Q, subject="Business Management", agent="business-management-specialist", task_type="essay")
    assert not [fc for fc in rc.formal_checks if "-marks-" in fc.constraint_id]


def test_a_per_cent_restated_from_decided_written_arithmetic_is_not_named_undecided():
    _reply, rc = through_hub(C.BI_P8D, C.BI_P8D_Q, subject="Biology", agent="biology-specialist", task_type="data_response")
    assert not findings(rc, "CORE-QNT-001"), [f.message for f in findings(rc, "CORE-QNT-001")]
    assert [fc.formal_status for fc in rc.formal_checks if fc.constraint_id.startswith("stem-eq")][:4] == ["ENTAILED"] * 4


# ------------------------------------------------------------------ the new readers stay linear on hostile input

READERS = {
    "is_answer_note": md.is_answer_note,
    "is_framing_remark": md.is_framing_remark,
    "is_sources_block": md.is_sources_block,
    "is_self_certification": lambda t: md.is_self_certification(t[:16_000]),
    "self_cert_vocabulary": md.self_cert_vocabulary,
    "absent_mentions": lambda t: md.absent_mentions(t, md.find_quotation_spans(t)),
    "own_model_words": lambda t: own_model_words("Model: " + t, t, {"d": STUDENT}),
    "study_attributions": study_attributions,
    "worked_problems": lambda t: worked_problems(t + " = 6.0 million", report_id="r", request_id="q", prefix="w"),
    "worked relative change": lambda t: worked_problems("Change = $4,125 − $2,400 = +$1,725 (an increase of " + t, report_id="r", request_id="q",
                                                        prefix="w"),
    "worked restatement": lambda t: worked_problems("Rate = 0.762 ÷ 12.70 × 100 (" + t + ") = 6.0%", report_id="r", request_id="q", prefix="w"),
    "worked formula head": lambda t: worked_problems("rs = 1 − (6 × Σd²) ÷ " + t + " = 1 − 396 ÷ 210 = −0.8857", report_id="r", request_id="q",
                                                     prefix="w"),
    "breakdown_problems": lambda t: __import__("epinoic_logic.branches.worked", fromlist=["x"]).breakdown_problems("$5 (" + t + ")", report_id="r",
                                                                                                                request_id="q", prefix="w"),
    "marks": lambda t: [list(rx.finditer("Provisional mark: " + t)) for rx in (__import__("epinoic_logic.branches.packs", fromlist=["x"])._MARK_PART_RE,
                                                                               __import__("epinoic_logic.branches.packs", fromlist=["x"])._MARK_TOTAL_RE)],
    "declined_deliverable": lambda t: md.declined_deliverable("I can't write " + t),
    "judged_or_reply_mention": lambda t: [md.judged_or_reply_mention(t, a, b) for a, b, _i in md.find_quotation_spans(t)],
    "percent changes": lambda t: extract_quant_checks("Prices rose 3.40% from 112.0 to " + t, request_id="r", claim_id="c"),
    "generic parse": lambda t: parse(t),
}


@pytest.mark.parametrize("reader", sorted(READERS))
def test_the_c1_readers_stay_linear_on_every_hostile_input(reader):
    fn = READERS[reader]
    for name, text in all_inputs().items():
        elapsed, error = bounded(fn, text)
        assert error is None or type(error).__name__ == "AdapterError", (reader, name, error)
        assert elapsed < 5.0, (reader, name, elapsed)
