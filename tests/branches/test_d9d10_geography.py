"""D9/D10 (decision D35): the Geography branch's own checks, through the hub. Each kind is decided by the engine on the answer as written:
the correct statement is ENTAILED, the faulty one fails with the severity its kind sets (INT-SUBJ-001, or INT-SUBJ-004 for a convention or
an uncredited table figure); approximation words widen the band, comparative bounds make it one-sided, area units convert exactly, scale
words and currency are carried, questions are skipped, a rate read but not built is named undecided (CORE-QNT-001) and never also decided.
The faulty variants of the recorded answers (design section 11) are named."""
from __future__ import annotations

import pytest

from epinoic_logic.branches.geography import GeographyPack
from epinoic_logic.engine import verify

from . import d9d10_texts as T
from .d9d10_hub import CFG, GEO, checks, failed, recorded, report, through_hub


def geo(text: str, question: str = "Answer the question.", docs=()):
    return through_hub(text, question, *GEO, "structured_question", docs)


def kinds(text: str, docs=()) -> list[tuple[str, str]]:
    """(kind, engine status) of every Geography check the pack builds for ``text`` (worked equations aside)."""
    rep = report(*GEO, text, docs=docs)
    return [(fc.kind, verify(fc.problem, CFG).status.value) for fc in GeographyPack().formal_checks_for(rep, "") if fc.kind != "worked_arithmetic"]


# ------------------------------------------------------------------ each kind: correct and faulty


@pytest.mark.parametrize("sentence,kind,status", [
    ("With 2.4 million people on 1,200 km², the density is 2,000 people per km².", "geo_density", "ENTAILED"),
    ("With 2.4 million people on 1,200 km², the density is 3,000 people per km².", "geo_density", "COUNTEREXAMPLE"),
    ("The town has a population of 48,000 and an area of 12 km², a density of 4,000 people per square kilometre.", "geo_density", "ENTAILED"),
    ("The town has a population of 48,000 and an area of 1,200 ha, a density of 4,000 people per km².", "geo_density", "ENTAILED"),      # ha -> km²
    ("The town has a population of 48,000 and an area of 1,200 ha, a density of 40 people per km².", "geo_density", "COUNTEREXAMPLE"),
    ("The estate houses 2,000 people on 400,000 m², a density of 5,000 people per km².", "geo_density", "ENTAILED"),                   # m² -> km²
    ("With 2.4 million people on 1,200 km², the density is about 2,050 people per km².", "geo_density", "ENTAILED"),                     # about: 5 %
    ("With 2.4 million people on 1,200 km², the density is more than 1,500 people per km².", "geo_density", "ENTAILED"),                # a lower bound
    ("With 2.4 million people on 1,200 km², the density is more than 2,500 people per km².", "geo_density", "COUNTEREXAMPLE"),
    ("Births: 4,800 in a population of 200,000, a crude birth rate of 24 per 1,000.", "geo_rate_per_thousand", "ENTAILED"),
    ("There were 4,800 births in a population of 200,000, a crude birth rate of 42 per 1,000.", "geo_rate_per_thousand", "COUNTEREXAMPLE"),
    ("With 90 infant deaths among 6,000 live births, the infant mortality rate is 15 per 1,000.", "geo_rate_per_thousand", "ENTAILED"),
    ("The crude birth rate is 24 per 1,000 and the crude death rate 9 per 1,000, so the natural increase rate is 1.5%.", "geo_natural_increase", "ENTAILED"),
    ("With a birth rate of 24 per 1,000 and a death rate of 9 per 1,000, natural increase is 2.5%.", "geo_natural_increase", "COUNTEREXAMPLE"),
    ("The birth rate is 24 per 1,000 and the death rate 9 per 1,000, a natural increase of 15 per 1,000.", "geo_natural_increase", "ENTAILED"),
    ("At a growth rate of 2% a year, the population will double in about 35 years.", "geo_doubling_time", "ENTAILED"),
    ("Growing at 2% a year, the population doubles in about 36 years.", "geo_doubling_time", "ENTAILED"),
    ("Growing at 2% a year, the population doubles in about 50 years.", "geo_doubling_time", "COUNTEREXAMPLE"),
    ("The country's GDP of $1.2 trillion and its 60 million people give a GDP per capita of $20,000.", "geo_per_capita", "ENTAILED"),
    ("A GDP of $1.2 trillion and 60 million people give a GDP per capita of $2,000.", "geo_per_capita", "COUNTEREXAMPLE"),
    ("The population grew from 10,000 in 2010 to 12,000 in 2020, an average annual growth rate of 2%.", "geo_growth_rate", "ENTAILED"),         # simple
    ("The population grew from 10,000 in 2010 to 12,190 in 2020, an average annual growth rate of 2%.", "geo_growth_rate", "ENTAILED"),         # compound
    ("The population grew from 10,000 in 2010 to 15,000 in 2020, an average annual growth rate of 2%.", "geo_growth_rate", "COUNTEREXAMPLE"),
    ("The mean of the three counts (210, 218 and 214) is 214.", "geo_mean", "ENTAILED"),
    ("The mean of the three counts (210, 218 and 214) is 218.", "geo_mean", "COUNTEREXAMPLE"),
    ("We counted an average of 12, 15 and 18 people, 15.", "geo_mean", "ENTAILED"),
    ("We sampled ten sites at 100 m intervals from 0 m to 900 m.", "geo_sampling", "ENTAILED"),
    ("We sampled twelve sites at 100 m intervals from 0 m to 900 m.", "geo_sampling", "COUNTEREXAMPLE"),
    ("A 1 km transect sampled every 100 m gives 11 sites.", "geo_sampling", "ENTAILED"),
    ("rs = −0.89 exceeds the critical value of 0.648, so the correlation is significant at the 0.05 level.", "geo_significance", "ENTAILED"),
    ("rs = 0.42 is below the critical value of 0.648, so the correlation is significant at the 0.05 level.", "geo_significance", "COUNTEREXAMPLE"),
    ("rs = 0.42 is below the critical value of 0.648, so the correlation is not significant.", "geo_significance", "ENTAILED"),
])
def test_each_geography_kind_is_decided(sentence, kind, status):
    assert (kind, status) in kinds(sentence), kinds(sentence)


def test_questions_and_imperatives_are_not_read():
    assert kinds("With 2.4 million people on 1,200 km², is the density 3,000 people per km²?") == []
    assert kinds("Why did you choose ten sites at 100 m intervals from 0 m to 900 m?") == []


@pytest.mark.parametrize("sentence,code", [
    ("With 2.4 million people on 1,200 km², the density is 3,000 people per km².", "INT-SUBJ-001"),
    ("There were 4,800 births in a population of 200,000, a crude birth rate of 42 per 1,000.", "INT-SUBJ-001"),
    ("With a birth rate of 24 per 1,000 and a death rate of 9 per 1,000, natural increase is 2.5%.", "INT-SUBJ-001"),
    ("Growing at 2% a year, the population doubles in about 50 years.", "INT-SUBJ-001"),
    ("A GDP of $1.2 trillion and 60 million people give a GDP per capita of $2,000.", "INT-SUBJ-001"),
    ("The mean of the three counts (210, 218 and 214) is 218.", "INT-SUBJ-001"),
    ("We sampled twelve sites at 100 m intervals from 0 m to 900 m.", "INT-SUBJ-004"),
])
def test_faulty_geography_statements_are_named_through_the_hub(sentence, code):
    rc = geo(sentence)
    assert rc.branch == "geography"
    assert failed(rc, code) and all(f.claim_ids for f in failed(rc, code)), [(f.code, f.message[:120]) for f in rc.findings]
    ok = geo(sentence.replace("3,000", "2,000").replace("42 per", "24 per").replace("2.5%", "1.5%").replace("50 years", "35 years")
             .replace("$2,000", "$20,000").replace("is 218", "is 214").replace("twelve sites", "ten sites"))
    assert not failed(ok, "INT-SUBJ-001") and not failed(ok, "INT-SUBJ-004"), [(f.code, f.message[:120]) for f in ok.findings]


def test_a_rate_outside_the_doubling_band_is_named_undecided_once():
    rc = geo("Growing at 14% a year, the population doubles in about 5 years.")
    und = [f for f in rc.structural_findings if f.code == "CORE-QNT-001"]
    assert len(und) == 1 and "outside the rule's band" in und[0].message and und[0].claim_ids
    assert not [fc for fc in rc.formal_checks if "doubling" in fc.constraint_id]


def test_a_mean_whose_count_differs_from_its_list_is_named_undecided():
    rc = geo("The mean of the four counts (210, 218 and 214) is 214.")
    assert any(f.code == "CORE-QNT-001" and "lists 3" in f.message for f in rc.structural_findings)
    assert not [fc for fc in rc.formal_checks if "-mean-" in fc.constraint_id]


def test_a_decided_statement_is_never_also_named_undecided():
    for s in ("With 2.4 million people on 1,200 km², the density is 2,000 people per km².",
              "The crude birth rate is 24 per 1,000 and the crude death rate 9 per 1,000, so the natural increase rate is 1.5%.",
              "At a growth rate of 2% a year, the population will double in about 35 years.",
              "The country's GDP of $1.2 trillion and its 60 million people give a GDP per capita of $20,000."):
        rc = geo(s)
        assert checks(rc, "geography-") and all(st == "ENTAILED" for _c, st in checks(rc, "geography-")), checks(rc)
        assert not [f for f in rc.structural_findings if f.code == "CORE-QNT-001"], [f.message for f in rc.structural_findings]


# ------------------------------------------------------------------ the recorded answers' faulty variants (design section 11)


def test_ge_t15_wrong_written_arithmetic_is_a_geography_worked_failure():
    rc = recorded("c2/ge-t15", T.GE_T15.replace("= 0.46 × 820 = 377.2 PJ", "= 0.46 × 820 = 372.2 PJ"))
    bad = [f for f in failed(rc) if "geography-worked" in f.message or "worked_arithmetic" in f.message]
    assert bad and any("g2.2@geography-specialist" in f.claim_ids for f in bad)
    assert not [c for c, _s in checks(rc) if c.startswith("generic-worked")]


def test_ge_p9c_wrong_percentage_is_a_geography_worked_failure():
    rc = recorded("c2/ge-p9c", T.GE_P9C.replace("= 10.8 ÷ 5.4 × 100\n= 200%", "= 10.8 ÷ 5.4 × 100\n= 300%"))
    assert any("worked_arithmetic" in f.message for f in failed(rc))


def test_ge_t15_misread_year_table_figure_is_still_the_core_figure_check():
    rc = recorded("c2/ge-t15", T.GE_T15.replace("Coal supply in 2005: 46% × 820 PJ", "Coal supply in 2005: 64% × 820 PJ"))
    assert any(c.startswith("core-figure") and s == "COUNTEREXAMPLE" for c, s in checks(rc))


@pytest.mark.parametrize("sentence,code,status", [
    ("According to the table, Site 4 had a mean pedestrian count of 79 per 10 minutes.", "INT-SUBJ-001", "COUNTEREXAMPLE"),
    ("Site 4 had 79 pedestrians per 10 minutes.", "INT-SUBJ-004", "COUNTEREXAMPLE"),
    ("According to the table, Site 4 had a mean pedestrian count of 97 per 10 minutes.", None, "ENTAILED"),
    ("Your table shows an EQS of 15 at site 5.", None, "ENTAILED"),
    ("Your table shows an EQS of 18 at site 5.", "INT-SUBJ-001", "COUNTEREXAMPLE"),
])
def test_ge_t14_figures_read_from_the_supplied_attribute_table(sentence, code, status):
    rc = recorded("c1/ge-t14", T.GE_T14 + "\n\n" + sentence)
    figs = checks(rc, "geography-supplied-figure")
    assert figs and figs[-1][1] == status, checks(rc)
    if code:
        assert any("source_mismatch" in (f.message + str(getattr(f, "defect", ""))) or f.code == code for f in failed(rc, code)), [f.code for f in rc.findings]
        assert failed(rc, code)
    else:
        assert not failed(rc, "INT-SUBJ-001") and not failed(rc, "INT-SUBJ-004")


def test_ge_t14_table_count():
    bad = recorded("c1/ge-t14", T.GE_T14 + "\n\nThe table shows twelve sites.")
    assert ("geography-table-count-1", "COUNTEREXAMPLE") in checks(bad) and failed(bad, "INT-SUBJ-004")
    ok = recorded("c1/ge-t14", T.GE_T14 + "\n\nThe table shows ten sites.")
    assert ("geography-table-count-1", "ENTAILED") in checks(ok) and not failed(ok, "INT-SUBJ-004")
    # the recorded questions and imperatives ('Why did you choose ten sites ...?', 'rank your ten sites') are not claims
    assert not checks(recorded("c1/ge-t14"), "geography-table-count")


def test_ge_t16_case_inconsistency_is_a_warning():
    text = T.GE_T16.replace("Development cannot explain everything, however.",
                            "Development cannot explain everything, however. The 158 deaths in Christchurch came later.")
    rc = recorded("c3/ge-t16", text)
    assert any(c.startswith("geography-case-consistency") and s == "COUNTEREXAMPLE" for c, s in checks(rc)), checks(rc)
    assert failed(rc, "INT-SUBJ-004")
    # the recorded answer: both 'more than 130' statements are overlapping bounds, so no pair is built
    assert not checks(recorded("c3/ge-t16"), "geography-case-consistency")


def test_ge_t16_padded_answer_is_named_by_the_channel_unchanged():
    padded = T.GE_T16 + "\n\n" + " ".join(["Shaking intensity depends on depth and distance from the epicentre."] * 45)
    rc = recorded("c3/ge-t16", padded)
    assert "INT-REQ-005" in [f.code for f in rc.findings]


def test_a_figure_credited_to_an_unsupplied_figure_is_core_src_002_info():
    rc = geo("Figure 2 shows 64% of households in the flood zone.")
    info = [f for f in rc.structural_findings if f.code == "CORE-SRC-002" and "not supplied" in f.message]
    assert info and info[0].severity == "info" and info[0].claim_ids


def test_unknown_supporting_claims_are_gen_str_001_on_the_geography_branch():
    rep = report(*GEO, "Point.", claims=[dict(claim_id="c1", claim_text="Point.", claim_role="point", materiality="material", supporting_claim_ids=["zz"])])
    assert [f.code for f in GeographyPack().checks(rep, "")] == ["GEN-STR-001"]
