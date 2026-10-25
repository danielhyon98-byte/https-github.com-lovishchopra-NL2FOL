"""Round-7 overseer regressions for the arithmetic extractor, the core pack and the Economics and Business packs.

Durations: a stated length of years is decided with an 'about' qualifier (the tolerance rule), with or without 'for', against day or
month dates (elapsed days), in a relative clause, and against a span the adjacent sentence states (hi-p7c's 'had run for more than twelve
years' with 7 October 1949 to 13 August 1961: a COUNTEREXAMPLE stated across sentences); dates that cannot be paired, or are too coarse, are
CORE-QNT-001. Signed changes ('changed by −6 per 1,000', 'a change of −6') and shares written 'N of the M ..., about <fraction or per cent>'
are decided. Worked equations ('$6,000 ÷ $2.00 = 3,000 loaves') are never silent: an elasticity worked as a division ('PED = −12.50 ÷ 18.75 =
−0.67') or a margin worked as '(A ÷ B) × 100 = m%' is decided by its subject pack, every other one is CORE-QNT-001 with its true reason. An
elasticity is read as PED, YED, XED or PES and with a Unicode minus. An undecided reason names the figures its sentence does state.
CORE-SRC-003 does not call a quotation of the request, or a word the sentence says the text lacks, an unverifiable quotation. A containment
list ending in bare years joined by 'and' names only the year outside the period."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.packs import BusinessPack, CorePack, EconomicsPack
from epinoic_logic.branches.quant import WORKED_EQUATION_REASON, extract_quant_checks, undecided_quant_statements, worked_equations
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text

from .r7_texts import BM_T13, BM_T13_Q, EC_P7A, EC_P7A_Q, GE_T13, GE_T13_Q, HI_P7C, HI_P7C_Q, HI_T13

KEY = b"branches-r7-regression-key-0123456"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def statuses(text: str) -> list[tuple[str, str]]:
    return [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(text, request_id="r", claim_id="c")]


def through_hub(text: str, question: str, *, subject: str = "History", agent: str = "history-specialist", texts=()):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent, "dummy-combinator"],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def errors(rc, code: str = "INT-SUBJ-001") -> list:
    return [f for f in rc.findings if f.code == code]


def report(subject: str, agent: str, text: str, *, texts=(), claims=None) -> SpecialistReport:
    claims = claims or [dict(claim_id="c1", claim_text=text, claim_role="point", materiality="material")]
    return SpecialistReport(report_id="rep-u", request_id="r", task_id="t", agent_id=agent, subject=subject, task_type="short_answer", original_response=text,
                            response_sha256=sha256_text(text), supplied_texts=list(texts),
                            claims=[ClaimRecord(request_id="r", task_id="t", report_id="rep-u", agent_id=agent, subject=subject, task_type="short_answer", **c) for c in claims],
                            created_at="2026-10-12T00:00:00Z")


# ------------------------------------------------------------------ durations (probe B [24]-[26], B2)


@pytest.mark.parametrize("sentence,expected", [
    ("The drain ran for twelve years, from 1949 to 1961.", "ENTAILED"),
    ("The drain ran for about twelve years, from 1949 to 1961.", "ENTAILED"),                          # [26]
    ("The drain ran for five years, from 1949 to 1961.", "COUNTEREXAMPLE"),
    ("The drain lasted for about five years, from 1949 to 1961.", "COUNTEREXAMPLE"),                   # 'about' with the tolerance rule
    ("The drain lasted for more than twenty years, from 1949 to 1961.", "COUNTEREXAMPLE"),
    ("The drain ran for more than twelve years, from 7 October 1949 to 13 August 1961.", "COUNTEREXAMPLE"),  # [25]: 11 years 10 months
    ("The drain lasted for twelve years, from 7 October 1949 to 13 August 1961.", "ENTAILED"),          # rounds to twelve
    ("The Aventine secession lasted for about five years, from 1924 to 1926.", "COUNTEREXAMPLE"),
    ("The Aventine secession lasted for more than five years, from 1924 to 1926.", "COUNTEREXAMPLE"),
    ("The Aventine secession lasted for five years, from June 1924 to January 1926.", "COUNTEREXAMPLE"),  # month dates: elapsed days
    ("The Aventine secession lasted five years, from 1924 to 1926.", "COUNTEREXAMPLE"),                # no 'for'
    ("The Aventine secession, which lasted five years from 1924 to 1926, failed.", "COUNTEREXAMPLE"),  # a relative clause, no comma
    ("The Aventine secession lasted two years, from 1924 to 1926.", "ENTAILED"),
    ("Departures continued for more than twelve years after the GDR's founding on 7 October 1949, until 13 August 1961.", "COUNTEREXAMPLE"),
    ("suspended Chinese labour immigration for ten years, from 1882 to 1892.", "ENTAILED"),
    ("suspended Chinese labour immigration for ten years, from 1882 to 1902.", "COUNTEREXAMPLE"),
])
def test_a_stated_length_of_years_is_decided_in_every_wording(sentence, expected):
    assert ("duration", expected) in statuses(sentence), statuses(sentence)
    assert not undecided_quant_statements(sentence)


def test_the_genuine_hi_p7c_duration_is_read_against_the_span_of_the_next_sentence():
    # 'ended a drain that had run for more than twelve years' with 'Between the founding of the German Democratic Republic on 7 October 1949
    # and 1961' next: the bare end year is the day the duration's own sentence dates in it (13 August 1961), 11 years 10 months
    [dur] = [c for c in extract_quant_checks(HI_P7C, request_id="r", claim_id="c") if c.kind == "duration"]
    assert verify(dur.problem, CFG).status.value == "COUNTEREXAMPLE"
    assert "stated across sentences" in dur.basis and "13 August 1961" in dur.basis and "7 October 1949" in dur.problem.conclusion.label
    reply, rc = through_hub(HI_P7C, HI_P7C_Q)
    assert reply is not None
    [err] = [f for f in errors(rc) if "duration" in f.message]
    assert err.claim_ids == ["h1.1"] and "more than twelve years" in err.message and "stated across sentences" in err.message
    # 'about twelve years' is within the tolerance rule of 11 years 10 months
    fixed = HI_P7C.replace("had run for more than twelve years", "had run for about twelve years")
    assert ("duration", "ENTAILED") in statuses(fixed)


@pytest.mark.parametrize("sentence,reason", [
    ("The drain ran for more than twelve years, from 7 October 1949 to 1961.", "cannot be decided at the resolution of its dates"),
    ("From 1928 to 1932 output fell, and the famine lasted for two years.", "stands in another clause"),
    ("The famine lasted for two years, between the harvests of 1932 and the census, 1928 and 1937 being the years compared.", "cannot be paired into a span"),
])
def test_a_duration_whose_dates_cannot_be_paired_is_undecided_not_silent(sentence, reason):
    assert not [k for k, _s in statuses(sentence) if k == "duration"]
    found = [u for u in undecided_quant_statements(sentence) if reason in u.reason]
    assert found and "years" in found[0].phrase


def test_a_length_with_one_date_or_none_states_no_arithmetic():
    for sentence in ("He ruled for ten years until his death in 1953.", "The war lasted for six years.", "On 6 May 1882 the Act suspended immigration for ten years."):
        assert statuses(sentence) == [] and not undecided_quant_statements(sentence)


# ------------------------------------------------------------------ signed changes and 'N of the M' shares (neg_probe)


@pytest.mark.parametrize("sentence,expected", [
    ("The crude death rate changed by −6 per 1,000, from 11 in 1990 to 7 in 2020.", "COUNTEREXAMPLE"),   # Unicode minus; true −4
    ("The crude death rate changed by -6 per 1,000, from 11 in 1990 to 7 in 2020.", "COUNTEREXAMPLE"),
    ("The crude death rate changed by −4 per 1,000, from 11 in 1990 to 7 in 2020.", "ENTAILED"),
    ("The crude death rate fell from 11 in 1990 to 7 in 2020, a change of −6 per 1,000.", "COUNTEREXAMPLE"),
    ("The crude death rate fell from 11 in 1990 to 7 in 2020, a change of −4 per 1,000.", "ENTAILED"),
    ("The crude death rate fell from 11 in 1990 to 7 in 2020, a change of +4 per 1,000.", "COUNTEREXAMPLE"),  # a plus sign is a rise
    ("The crude death rate fell from 11 in 1990 to 7 in 2020, a fall of 6 per 1,000.", "COUNTEREXAMPLE"),
])
def test_a_signed_change_is_decided_with_either_minus(sentence, expected):
    assert ("abs_change", expected) in statuses(sentence), statuses(sentence)


def test_a_signed_per_cent_change_states_its_direction():
    assert ("percent_change", "COUNTEREXAMPLE") in statuses("Output fell from 11 in 1990 to 7 in 2020, a change of +36 per cent.")
    assert ("percent_change", "ENTAILED") in statuses("Output changed by −36 per cent, from 11 in 1990 to 7 in 2020.")


@pytest.mark.parametrize("sentence,expected", [
    ("The list with the most votes was guaranteed 356 of the 535 seats, about three-quarters.", "COUNTEREXAMPLE"),
    ("The list with the most votes was guaranteed 356 of the 535 seats, about 75 per cent.", "COUNTEREXAMPLE"),
    ("The list with the most votes was guaranteed 356 of the 535 seats, about two-thirds.", "ENTAILED"),
    ("The list won 356 of the 535 seats (about 67 per cent).", "ENTAILED"),
    ("Of the 535 seats, the list with the most votes was guaranteed 356, about three-quarters.", "COUNTEREXAMPLE"),
    ("Of the 535 seats, the list with the most votes was guaranteed 356, about two-thirds.", "ENTAILED"),
])
def test_a_share_written_n_of_the_m_is_decided(sentence, expected):
    assert ("share", expected) in statuses(sentence), statuses(sentence)


def test_the_share_probe_inside_hi_t13_is_named_on_the_receipt():
    text = HI_T13.replace("The electoral route came first.", "The electoral route came first. The list with the most votes was guaranteed 356 of the 535 seats, about three-quarters.")
    reply, rc = through_hub(text, "Write one body paragraph.")
    assert any("356 of the 535 seats" in f.message for f in errors(rc))


# ------------------------------------------------------------------ worked equations: decided by a subject pack, else named undecided


@pytest.mark.parametrize("line,phrase", [
    ("Break-even quantity = fixed costs ÷ contribution per loaf\n= $6,000 ÷ $2.00 = 2,000 loaves per month", "$6,000 ÷ $2.00 = 2,000 loaves per month"),
    ("Dependency ratio = (aged 0–14 + aged 65 and over) ÷ aged 15–64 × 100\n= (22 + 9) ÷ 69 × 100\n= 31 ÷ 69 × 100\n= 54.9", "(22 + 9) ÷ 69 × 100 = 31 ÷ 69 × 100 = 54.9"),
    ("∫₀² v dt = [3t² − t³]₀² = (12 − 8) − 0 = 5", "(12 − 8) − 0 = 5"),
    ("distance = 4 − (−4) = 0", "4 − (−4) = 0"),
    ("With monthly compounding the rate per period is $0.036/12 = 0.03$, and there are 60 periods.", "With monthly compounding the rate per period is $0.036/12 = 0.03$"),
    ("(a) Percentage decrease = (9.6 − 3.8) ÷ 9.6 × 100\n= 39.6% decrease [1]", "(9.6 − 3.8) ÷ 9.6 × 100 = 39.6% decrease [1]"),
    ("R + r = 2.4 Ω + 0.50 Ω = 3.9 Ω", "2.4 Ω + 0.50 Ω = 3.9 Ω"),
])
def test_a_worked_equation_is_named_undecided_with_its_true_reason(line, phrase):
    assert [e.phrase for e in worked_equations(line)] == [phrase]
    [u] = [u for u in undecided_quant_statements(line) if u.reason == WORKED_EQUATION_REASON]
    assert u.phrase == phrase
    assert not [u for u in undecided_quant_statements(line) if "states no pair of figures" in u.reason]  # the false reason of r7 is gone


@pytest.mark.parametrize("text", [
    "PED = −0.67",                                              # a stated value
    "Rate of natural increase (%) = (crude birth rate − crude death rate) ÷ 10",  # a formula
    "a = dv/dt = 6 − 6t M1",                                    # algebra
    "Your line $A = 4000(1 + 0.036)^5$ compounds once a year.",  # a formula with a substitution, no stated result
])
def test_formulas_values_and_algebra_are_not_worked_equations(text):
    assert worked_equations(text) == []


def test_bm_t13_break_even_is_never_silent_and_its_margins_are_decided():
    # Rewritten to a stricter rule (B25): the wrong worked break-even line was named undecided (CORE-QNT-001, a warning); the
    # STEM chain checker now decides it, so it is an engine counterexample (INT-SUBJ-001, an error) on the claim holding it.
    wrong = BM_T13.replace("= $6,000 ÷ $2.00 = 3,000 loaves per month", "= $6,000 ÷ $2.00 = 4,000 loaves per month")
    reply, rc = through_hub(wrong, BM_T13_Q, subject="Business Management", agent="business-specialist")
    assert reply is not None
    failed = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("core-stem") and fc.satisfied is False]
    assert len(failed) == 1 and failed[0].formal_status == "COUNTEREXAMPLE" and failed[0].claim_ids
    assert any(f.code == "INT-SUBJ-001" and f.severity == "error" and "6,000 ÷ 2.00 = 4,000" in f.message and f.claim_ids == failed[0].claim_ids
               for f in rc.findings)
    assert not [f for f in rc.structural_findings if f.code == "CORE-QNT-001" and "$6,000 ÷ $2.00 = 4,000" in f.message]
    margins = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("business-margin")]
    assert [fc.formal_status for fc in margins] == ["ENTAILED", "ENTAILED"]
    # a margin the Business pack decides is not also named undecided
    assert not [f for f in rc.structural_findings if f.code == "CORE-QNT-001" and "$100,800 ÷ $201,600" in f.message]
    wrong_margin = BM_T13.replace("= ($100,800 ÷ $201,600) × 100 = 50.00%", "= ($100,800 ÷ $201,600) × 100 = 60.00%")
    _reply, rc2 = through_hub(wrong_margin, BM_T13_Q, subject="Business Management", agent="business-specialist")
    assert any("margin" in f.message and "60.00%" in f.message for f in errors(rc2))


def test_ge_t13_dependency_ratio_is_decided_by_the_stem_checker():
    # Rewritten to a stricter rule and renamed (was test_ge_t13_dependency_ratio_is_named_undecided, B25): the wrong worked ratio
    # was named undecided (CORE-QNT-001, a warning); the STEM chain checker now decides it (INT-SUBJ-001, an error), and the
    # correct lines of the same answer (rates per 1,000 divided by 10 as per cent) hold.
    wrong = GE_T13.replace("= 31 ÷ 69 × 100\n= 44.9", "= 31 ÷ 69 × 100\n= 54.9")
    reply, rc = through_hub(wrong, GE_T13_Q, subject="Geography", agent="geography-specialist")
    errs = [f for f in rc.findings if f.code == "INT-SUBJ-001" and f.severity == "error"]
    assert len(errs) == 1 and "31 ÷ 69 × 100 = 54.9" in errs[0].message
    assert not any(f.code == "CORE-QNT-001" and "31 ÷ 69 × 100 = 54.9" in f.message for f in rc.structural_findings)
    _reply, ok = through_hub(GE_T13, GE_T13_Q, subject="Geography", agent="geography-specialist")
    assert not errors(ok) and [fc for fc in ok.formal_checks if fc.constraint_id.startswith("core-stem")]
    assert all(fc.satisfied is True for fc in ok.formal_checks if fc.constraint_id.startswith("core-stem"))


# ------------------------------------------------------------------ elasticity: PED/YED/XED/PES, Unicode minus, worked divisions


def test_ec_p7a_elasticities_are_entailed_and_each_wrong_variant_is_a_counterexample():
    reply, rc = through_hub(EC_P7A, EC_P7A_Q, subject="Economics", agent="economics-specialist")
    ped = [fc for fc in rc.formal_checks if fc.constraint_id.startswith("economics-elasticity")]
    assert len(ped) == 2 and all(fc.formal_status == "ENTAILED" for fc in ped)
    assert not errors(rc)
    assert not [f for f in rc.structural_findings if f.code == "CORE-QNT-001" and "−12.50 ÷ 18.75" in f.message]  # decided by the pack
    for old, new in (("PED = −12.50 ÷ 18.75 = −0.67", "PED = −12.50 ÷ 18.75 = −0.97"),
                     ("PED = −12.50 ÷ 18.75 = −0.67", "PED = −12.50 ÷ 18.75 = 0.67"),          # the sign of a worked division is checked
                     ("a PED of −0.67 means", "a PED of −1.67 means"),
                     ("a PED of −0.67 means", "a price elasticity of demand of −1.67 means")):
        _reply, bad = through_hub(EC_P7A.replace(old, new), EC_P7A_Q, subject="Economics", agent="economics-specialist")
        assert any(f.code == "INT-SUBJ-001" and "elasticity" in f.message for f in bad.findings), new


@pytest.mark.parametrize("sentence,ok", [
    ("Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 0.5.", True),
    ("Quantity demanded fell by 10 per cent when price rose by 20 per cent, so the price elasticity of demand is 2.", False),
    ("Price rose by 20 per cent and quantity demanded fell by 10 per cent, so PED is −0.5.", True),
    ("Income rose by 4% and quantity demanded rose by 8%, so the YED is 2.", True),
    ("Income rose by 4% and quantity demanded rose by 8%, so the YED is 0.5.", False),
    ("PES = 12 ÷ 4 = 3", True),
    ("PES = 12 ÷ 4 = 2", False),
])
def test_elasticity_abbreviations_and_orders(sentence, ok):
    rep = report("Economics", "economics-specialist", sentence)
    checks = EconomicsPack().formal_checks(rep)
    assert checks and all(fc.claim_ids == ("c1",) for fc in checks)
    assert all((verify(fc.problem, CFG).status.value == "ENTAILED") is ok for fc in checks)


def test_a_margin_in_prose_still_decided_and_names_its_claim():
    good = report("Business Management", "business-specialist", "With a profit of 50,000 on revenue of 250,000 the profit margin is 20 per cent.")
    [fc] = BusinessPack().formal_checks(good)
    assert verify(fc.problem, CFG).status.value == "ENTAILED" and fc.claim_ids == ("c1",)


# ------------------------------------------------------------------ undecided reasons name the figures their sentence states


def test_the_ec_p7a_undecided_reason_names_the_figures_it_states():
    [u] = [u for u in undecided_quant_statements(EC_P7A) if u.phrase == "fell by $34.50 million per year"]
    assert "no figures are stated" not in u.reason and "only 17.97%" in u.reason


# ------------------------------------------------------------------ CORE-SRC-003: the request's own words and words the text lacks


def test_a_quotation_of_the_request_or_a_word_the_text_lacks_is_no_unverifiable_quotation():
    # lit-t13, sp-t13 and mai-t13: the parsers record every quotation credited to no text, whatever its length; the core pack reads them
    from epinoic_logic.adapters.sources import uncredited_assumption
    doc = SuppliedText(document_id="doc-ferry", title="Extract", author="A Writer", text="She stood at the rail. The harbour came up grey; her arm still ached where it had been bruised.")
    question = "My teacher set this extract with the guiding question 'How does the writer present Mrs Okafor's feelings about returning home?'"
    text = ('Your paragraph answers the question of how she feels about "returning home". The bruise comparison has no "like" or "as", so it is a metaphor. '
            'The text never says "ayudar" either. One critic calls her "a woman between two shores".')
    quotes = ("returning home", "like", "as", "ayudar", "a woman between two shores")
    rep = report("History", "history-specialist", text, texts=[doc],
                 claims=[dict(claim_id="c1", claim_text=text, claim_role="point", materiality="material", assumptions=[uncredited_assumption(q) for q in quotes])])
    [f] = [x for x in CorePack().checks(rep, question) if x.code == "CORE-SRC-003"]
    assert "a woman between two shores" in f.message and f.message.startswith("1 quotation(s)")
    assert all(f"'{w}'" not in f.message for w in quotes[:4])
    # without the request, the guiding question's words are unlocated
    [g] = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert "'returning home'" in g.message and "'like'" not in g.message


# ------------------------------------------------------------------ containment lists: bare years joined by 'and'


@pytest.mark.parametrize("sentence,outside", [
    ("Emigration ran from 1949 to 1961, including peaks in 1953 and 1963.", ["1963"]),
    ("Emigration ran from 1949 to 1961, including peaks in 1953, 1956 and 1963.", ["1963"]),
    ("Emigration ran from 1949 to 1961, including a peak in 1953 and a peak in 1963.", ["1963"]),
])
def test_a_containment_finding_names_only_the_year_outside_the_period(sentence, outside):
    named = [r.later_text for r in chronology_relations(sentence) if r.kind == "within" and r.violated]
    assert named == outside
    text = HI_P7C.replace("In 1952 the GDR sealed", sentence + " In 1952 the GDR sealed")
    from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
    rep = HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="x", task_type="short_answer")
    [chr_finding] = [f for f in structural_checks(rep) if f.code == "HI-CHR-001"]
    assert "1963 does not fall within 1949 to 1961" in chr_finding.message and "1953" not in chr_finding.message.split(":")[-1]
    assert [r.later_text for r in chronology_relations("Production was compared between 1953 and 1963, including 1960.") if r.kind == "within"] == ["1960"]


def test_a_short_quotation_the_parser_recorded_is_reported_with_no_text_supplied():
    # hi-t13-italian: 'Me ne frego' (11 characters) is recorded by the parser as credited to no text; with no supplied text it is still named
    from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
    text = HI_T13.replace("The electoral route came first.", 'The electoral route came first. The squads had sung "Me ne frego" in the streets since 1921.')
    rep = HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="x", task_type="short_answer")
    [f] = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert "'Me ne frego'" in f.message and "no text was supplied" in f.message and f.claim_ids


@pytest.mark.parametrize("text", [
    "= 1" + " " * 20000 + "+ x = 2",                                        # a long blank run between a figure and an operator
    "= 1 + " + "1" * 100000 + "x = 2",                                      # a long run of digits after an operator
    "1 + 2 = 3; " * 3000,                                                    # thousands of statements on one line
    "It lasted for five years " * 2000 + "from 1924 to 1926.",               # thousands of stated lengths in one sentence
    "from 1924 to 1926, it lasted five years " * 2000 + ".",                 # and as many spans
    "It lasted for five years, from 1 May 1924" + " " * 20000 + "x",
])
def test_the_new_readers_stay_linear_on_adversarial_text(text):
    import time
    t0 = time.perf_counter()
    worked_equations(text)
    undecided_quant_statements(text)
    extract_quant_checks(text, request_id="r", claim_id="c")
    assert time.perf_counter() - t0 < 5.0


def test_a_word_quoted_from_a_quotation_already_given_is_not_counted_again():
    # r1-adv hi-t2: 'the verb "killed"' and 'the adverb "openly"' after '"We killed him openly," Pedro Vicario says' (no text supplied)
    from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
    text = ('The twins\' declaration makes this separation explicit. "We killed him openly," Pedro Vicario says, "but we\'re innocent." The paradox '
            'turns on the verb "killed", which carries the admission, and the key word is the adverb "openly", dated by the trial of 1951.')
    rep = HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="x", task_type="short_answer")
    [f] = [x for x in CorePack().checks(rep) if x.code == "CORE-SRC-003"]
    assert f.message.startswith("2 quotation(s)") and "'killed'" not in f.message and "'openly'" not in f.message
