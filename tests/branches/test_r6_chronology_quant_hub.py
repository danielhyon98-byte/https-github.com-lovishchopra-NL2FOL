"""Round-6 overseer regressions for the chronology extractor, the arithmetic extractor, the core pack and the hub.

Chronology: a containment cue reads its outer period from the clause's span ('From 1961 ... by 1968'; a bare 'by 1968' is an upper
bound) and checks every item of its list; 'among them' reads its list before the cue; every dated object of an ordering cue is
checked; a year opening an intransitive 'followed' dates its own subject; an event is dated in another sentence by a participial
aside or a governing date. Arithmetic: figures with a currency sign, 'devalued', parts of a total, shares of the total, totals with
nouns, differences, durations and rate trends are decided; an oversized figure is refused per statement. Core pack: a support cycle in
any delivered report is CORE-STR-001; formal checks are capped per transmission. Hub: nothing raises."""
from __future__ import annotations

import json
import time

import pytest

from epinoic_logic.adapters.history_specialist.chronology import chronology_relations
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.base import SubjectBranch
from epinoic_logic.branches.packs import MAX_FORMAL_CHECKS, CorePack
from epinoic_logic.branches.quant import MAX_FIGURE_DIGITS, extract_quant_checks, undecided_quant_statements
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig, verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

from ..timing import measure
from .r6_texts import HI_P5, HI_P5_Q, HI_T11, HI_T11_Q, HI_T12, HI_T12_INCLUDING, HI_T12_Q

KEY = b"branches-r6-regression-key-012345"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)


def through_hub(text: str, question: str, *, subject: str = "History", agent: str = "history-specialist", task_type: str = "short_answer"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent, "dummy-combinator"]))
    m, _, _ = hub.dispatch("t", agent, question)
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def statuses(text: str) -> list[tuple[str, str]]:
    return [(c.kind, verify(c.problem, CFG).status.value) for c in extract_quant_checks(text, request_id="r", claim_id="c")]


def rels(sentence: str, context: str | None = None):
    return chronology_relations(sentence, context or sentence)


def subj_errors(receipt) -> list:
    return [f for f in receipt.findings if f.code == "INT-SUBJ-001"]


# ------------------------------------------------------------------ containment: the outer period's span and every item of the list


def test_genuine_hi_t12_carries_no_false_chronology_error_and_every_inner_date_is_checked():
    reply, rc = through_hub(HI_T12, HI_T12_Q)
    assert reply is not None and not subj_errors(rc)
    codes = {f.code for f in rc.structural_findings}
    assert "HI-CHR-001" not in codes and "CORE-CHR-001" not in codes
    within = [fc for fc in rc.formal_checks if "containment" in (fc.detail or "")]
    # one engine problem per list, every item in it: 1961, 1963 and 1966 within 1961 to 1968
    [including] = [fc for fc in within if "'including'" in fc.detail]
    assert all(f"{y} within 1961 to 1968" in including.detail for y in (1961, 1963, 1966))
    assert all(fc.formal_status == "ENTAILED" for fc in rc.formal_checks)
    # 'Nigeria on 1 October and the Belgian Congo on 30 June among them' after 'in 1960': both checked inside 1960
    [among] = [fc for fc in within if "'among them'" in fc.detail]
    assert "1 October within 1960" in among.detail and "30 June within 1960" in among.detail


@pytest.mark.parametrize("old,new,named", [
    ("Kenya in 1963", "Kenya in 1973", "1973 within 1961 to 1968"),          # middle item
    ("Botswana in 1966", "Botswana in 1971", "1971 within 1961 to 1968"),    # last item
    ("Tanganyika in 1961", "Tanganyika in 1959", "1959 within 1961 to 1968"),  # first item
])
def test_a_wrong_item_anywhere_in_the_list_is_named(old, new, named):
    _reply, rc = through_hub(HI_T12.replace(old, new), HI_T12_Q)
    errors = subj_errors(rc)
    assert errors and all(named in f.message for f in errors) and len(errors) == 1


def test_a_bare_by_bound_is_an_upper_bound_not_the_year():
    ok = rels("By 1968 roughly fifteen more states had followed, including Kenya in 1963 and Botswana in 1966.")
    within = [r for r in ok if r.kind == "within"]
    assert len(within) == 2 and all(r.decided and not r.violated and "the period up to 1968" in r.statement for r in within)
    bad = [r for r in rels("By 1968 roughly fifteen more states had followed, including Kenya in 1963 and Botswana in 1969.") if r.kind == "within"]
    assert [r.later_text for r in bad if r.violated] == ["1969"]


def test_among_them_reads_its_list_before_the_cue():
    sentence = HI_T12.split(". ")[3] + "."
    assert sentence.startswith("The pace changed in 1960")
    wrong = sentence.replace("Nigeria on 1 October", "Nigeria on 1 October 1961")
    got = [r for r in rels(wrong, HI_T12.replace(sentence, wrong)) if r.kind == "within"]
    assert [r.later_text for r in got if r.violated] == ["1 October 1961"]
    _reply, rc = through_hub(HI_T12.replace(sentence, wrong), HI_T12_Q)
    assert any("1 October 1961 within 1960" in f.message for f in subj_errors(rc))
    listed = [r for r in rels("From 1961 to 1968 roughly fifteen states followed, Tanganyika in 1961 and Botswana in 1970 among them.") if r.kind == "within"]
    assert [(r.later_text, r.violated) for r in listed] == [("1961", False), ("1970", True)]


def test_which_included_checks_every_listed_date_and_stops_at_the_main_clause():
    got = [r for r in rels("The years from 1961 to 1968, which included Tanganyika's independence in 1961 and Botswana's in 1970, saw a slower flow.") if r.kind == "within"]
    assert [(r.later_text, r.violated) for r in got] == [("1961", False), ("1970", True)]
    mania = [r for r in rels("The 1840s, which included the Railway Mania of 1845 to 1847, ended in 1850 with a slump.") if r.kind == "within"]
    assert [(r.later_text, r.violated) for r in mania] == [("1845 to 1847", False)]


# ------------------------------------------------------------------ an ordering cue with a list of dated objects


@pytest.mark.parametrize("sentence,false_pair", [
    ("Kenya became independent in 1963, after Tanganyika in 1961 and Botswana in 1966.", ("1963", "1966")),
    ("Tanganyika became independent in 1961, before Kenya in 1963 and Ghana in 1957.", ("1957", "1961")),
])
def test_every_dated_object_of_a_cue_is_ordered_against_the_subject(sentence, false_pair):
    got = rels(sentence)
    assert len(got) == 2 and all(r.decided for r in got)
    assert [(r.later_text, r.earlier_text) for r in got if r.violated] == [false_pair]


def test_a_coordinated_clause_or_cue_is_not_read_as_an_object():
    got = rels("Unemployment rose in 1930, after the crash in 1929 and peaked in 1932.")
    assert [(r.later_text, r.earlier_text) for r in got] == [("1930", "1929")]
    got = rels("The decree of October 14, 1962 followed the flight of October 12, 1962.")
    assert [(r.later_text, r.earlier_text, r.violated) for r in got] == [("October 14, 1962", "October 12, 1962", False)]


# ------------------------------------------------------------------ intransitive 'followed' with the clause's own year


def test_in_1958_guinea_followed_dates_its_own_subject_and_follows_the_previous_sentence():
    sentence = "In 1958 Guinea followed on 2 October, having voted No in de Gaulle's referendum of 28 September and faced the immediate withdrawal of French aid and personnel."
    [rel] = [r for r in chronology_relations(sentence, HI_T12) if r.cue == "followed"]
    assert rel.decided and not rel.violated and (rel.later_text, rel.earlier_text) == ("2 October 1958", "6 March 1957")
    wrong = HI_T12.replace("In 1958 Guinea followed", "In 1956 Guinea followed")
    [bad] = [r for r in chronology_relations(sentence.replace("1958", "1956"), wrong) if r.cue == "followed"]
    assert bad.decided and bad.violated
    _reply, rc = through_hub(wrong, HI_T12_Q)
    assert any("2 October 1956 later than 6 March 1957" in f.message for f in subj_errors(rc))
    assert not any("is not stated" in f.message and "2 October" in f.message for f in rc.structural_findings if f.code == "CORE-CHR-001")
    # with no dated event before it, the relation is undecided rather than read against its own year
    [alone] = [r for r in chronology_relations("In 1958 Guinea followed on 2 October.", "In 1958 Guinea followed on 2 October.")]
    assert not alone.decided and "2 October 1958" in alone.later_text


def test_a_coordinate_clause_year_still_dates_the_followed_event():
    [rel] = rels("The Ruhr was occupied in January 1923 and passive resistance followed in February 1923.")
    assert rel.decided and (rel.later_text, rel.earlier_text) == ("February 1923", "January 1923")


# ------------------------------------------------------------------ an event dated elsewhere in the paragraph


def test_an_event_dated_by_a_participial_aside_or_a_governing_date_is_looked_up():
    wrong = HI_T11.replace("and it came before most Marshall deliveries had arrived", "and it came before the Economic Cooperation Act was signed")
    _reply, rc = through_hub(wrong, HI_T11_Q, task_type="essay")
    assert any("3 April 1948 later than 20 June 1948" in f.message for f in subj_errors(rc))
    right = HI_T11.replace("and it came before most Marshall deliveries had arrived", "and it came after the Economic Cooperation Act was signed")
    _reply, ok = through_hub(right, HI_T11_Q, task_type="essay")
    assert not subj_errors(ok)
    para = "The Act, signed on 3 April 1948, launched the programme. The reform came in June 1948, before the Act."
    [rel] = chronology_relations("The reform came in June 1948, before the Act.", para)
    assert rel.decided and rel.violated
    late = HI_P5 + " The statue was dedicated in 1880, after the Chinese Exclusion Act."
    [rel] = chronology_relations("The statue was dedicated in 1880, after the Chinese Exclusion Act.", late)
    assert rel.decided and rel.violated and rel.earlier_text == "6 May 1882"


def test_a_named_event_no_sentence_dates_is_reported_undecided_not_silent():
    [rel] = rels("The reform came in June 1948, before the Marshall Act.")
    assert not rel.decided and "the Marshall Act" in rel.reason
    assert rels("Prices rose in March 1930; the budget fell after the vote of July 1930.") == []


# ------------------------------------------------------------------ arithmetic: currency signs and 'devalued'


def test_genuine_hi_t11_arithmetic_is_checked():
    got = statuses(HI_T11)
    assert ("pair_direction", "ENTAILED") in got and ("parts", "ENTAILED") in got
    assert not undecided_quant_statements(HI_T11)
    _reply, rc = through_hub(HI_T11, HI_T11_Q, task_type="essay")
    assert rc.formal_checks and all(fc.formal_status == "ENTAILED" for fc in rc.formal_checks) and not subj_errors(rc)


@pytest.mark.parametrize("old,new,kind", [
    ("devalued from $4.03 to $2.80", "devalued from $2.80 to $4.03", "pair_direction"),                       # R1
    ("devalued from $4.03 to $2.80", "devalued from $4.03 to $2.80, a fall of about 50 per cent,", "percent_change"),  # R2 (true 30.5)
    ("sterling was devalued from $4.03 to $2.80", "sterling rose from $4.03 to $2.80", "pair_direction"),
    ("of which the United Kingdom received about $3.2 billion", "of which the United Kingdom received about $23.2 billion", "parts"),  # R4
    ("of which the United Kingdom received about $3.2 billion", "of which the United Kingdom received about $13.2 billion", "parts"),
])
def test_false_dollar_relations_in_hi_t11_are_counterexamples(old, new, kind):
    text = HI_T11.replace(old, new)
    assert text != HI_T11
    assert (kind, "COUNTEREXAMPLE") in statuses(text)
    _reply, rc = through_hub(text, HI_T11_Q, task_type="essay")
    assert subj_errors(rc)


@pytest.mark.parametrize("sentence,expected", [
    ("American aid commitments rose from about $1.2 billion in 1947 to about $4.9 billion in 1949, roughly a fourfold rise.", ("fold_change", "ENTAILED")),
    ("American aid commitments rose from about $1.2 billion in 1947 to about $4.9 billion in 1949, a sixfold rise.", ("fold_change", "COUNTEREXAMPLE")),
    ("Aid rose from about $1.5 billion in 1947 to about $4.9 billion in 1949, an increase of about $1.4 billion.", ("abs_change", "COUNTEREXAMPLE")),
    ("Cumulative aid rose from about $5 billion in 1949 to about $13 billion in 1952, an average of about $6 billion a year.", ("rate_change", "COUNTEREXAMPLE")),
    ("British reserves fell from about £600 million in 1948 to about £300 million in 1949, a fall of 80 per cent.", ("percent_change", "COUNTEREXAMPLE")),
    ("Aid rose from $4 billion in 1948 to $6 billion in 1949, a rise of about 90 per cent.", ("percent_change", "COUNTEREXAMPLE")),
    ("Sterling was devalued from 4.03 dollars to 2.80 dollars in 1949.", ("pair_direction", "ENTAILED")),
    ("Sterling was devalued from 2.80 dollars to 4.03 dollars in 1949.", ("pair_direction", "COUNTEREXAMPLE")),
])
def test_a_change_in_dollars_is_decided_like_one_in_billion_dollars(sentence, expected):
    assert statuses(sentence) == [expected]
    assert not undecided_quant_statements(sentence)


def test_figures_in_different_currencies_are_not_compared():
    assert statuses("Aid rose from $4 billion in 1948 to 6 billion marks in 1949, a rise of 50 per cent.") == []
    [u] = undecided_quant_statements("Aid rose from $4 billion in 1948 to 6 billion marks in 1949, a rise of 50 per cent.")
    assert "cannot be compared" in u.reason


# ------------------------------------------------------------------ parts, shares, totals, differences, durations, rate trends


@pytest.mark.parametrize("old,new,kind,expected", [
    ("1882 alone brought nearly 790,000", "1882 alone brought nearly 7.9 million", "parts", "COUNTEREXAMPLE"),
    ("1882 alone brought nearly 790,000", "1882 alone brought nearly 7,900,000", "parts", "COUNTEREXAMPLE"),
    ("1882 alone brought nearly 790,000,", "1882 alone brought nearly 790,000, about a quarter of the decade's total,", "share", "COUNTEREXAMPLE"),
    ("1882 alone brought nearly 790,000,", "1882 alone brought nearly 790,000, about 15 per cent of the decade's total,", "share", "ENTAILED"),
    ("suspended Chinese labour immigration for ten years.", "suspended Chinese labour immigration for ten years, from 1882 to 1902.", "duration", "COUNTEREXAMPLE"),
    ("suspended Chinese labour immigration for ten years.", "suspended Chinese labour immigration for ten years, from 1882 to 1892.", "duration", "ENTAILED"),
])
def test_hi_p5_parts_shares_and_durations(old, new, kind, expected):
    text = HI_P5.replace(old, new)
    assert text != HI_P5
    assert (kind, expected) in statuses(text)
    assert ("parts", "ENTAILED") in statuses(HI_P5)


@pytest.mark.parametrize("sentence,kind,expected", [
    ("The Programme had transferred about 13 billion dollars by mid-1952, of which the United Kingdom received about 3.2 billion dollars, about two-thirds of the total.", "share", "COUNTEREXAMPLE"),
    ("The Programme had transferred about 13 billion dollars by mid-1952, of which the United Kingdom received about 3.2 billion dollars, about 60 per cent of the total.", "share", "COUNTEREXAMPLE"),
    ("The Programme had transferred about 13 billion dollars by mid-1952, of which the United Kingdom received about 3.2 billion dollars, about a quarter of the total.", "share", "ENTAILED"),
    ("Of the aid, the United Kingdom received about 3.2 billion dollars and France about 2.7 billion dollars, a total of about 9 billion dollars.", "total", "COUNTEREXAMPLE"),
    ("Of the aid, the United Kingdom received about $3.2 billion and France about $2.7 billion, a total of about $5.9 billion.", "total", "ENTAILED"),
])
def test_shares_of_the_total_and_totals_with_nouns(sentence, kind, expected):
    assert (kind, expected) in statuses(sentence)


def test_a_difference_between_named_parties_is_read_against_their_figures():
    eca = HI_T11.split(". ")[2]
    assert eca.startswith("The Economic Cooperation Act")
    wrong = eca + ", so the United Kingdom received about $2 billion more than France."
    right = eca + ", so the United Kingdom received about $0.5 billion more than France."
    assert ("difference", "COUNTEREXAMPLE") in statuses(wrong) and ("difference", "ENTAILED") in statuses(right)
    [u] = undecided_quant_statements("Germany had 3 million more than France.")
    assert "Germany" in u.reason


def test_a_share_of_the_total_is_read_against_the_partys_stated_figure():
    # Rewritten to a stricter rule: the share used to be reported undecided only. The paragraph states
    # the party's figure (about $3.2 billion of about $13 billion), so the share is now decided: a wrong
    # share is a counterexample, a right one is entailed, and a party with no stated figure stays undecided.
    eca = HI_T11.split(". ")[2]
    wrong = eca + ", so the United Kingdom alone received about two-thirds of the total."
    right = eca + ", so the United Kingdom alone received about a quarter of the total."
    unknown = eca + ", so Belgium alone received about two-thirds of the total."
    assert ("share", "COUNTEREXAMPLE") in statuses(wrong)
    assert not [u for u in undecided_quant_statements(wrong) if "two-thirds" in u.phrase]
    assert ("share", "ENTAILED") in statuses(right)
    [u] = [u for u in undecided_quant_statements(unknown) if "two-thirds" in u.phrase]
    assert "no figure for Belgium" in u.reason
    assert not [s for s in statuses(unknown) if s[0] == "share"]


def test_hi_t12_rate_trend_is_decided():
    assert ("rate_trend", "ENTAILED") in statuses(HI_T12)
    quick = HI_T12.replace("the flow slowed", "the flow quickened")
    assert ("rate_trend", "COUNTEREXAMPLE") in statuses(quick)
    _reply, rc = through_hub(quick, HI_T12_Q)
    assert any("rate_trend" in f.message for f in subj_errors(rc))


@pytest.mark.parametrize("sentence,expected", [
    ("Immigration rose from about 2.8 million in the 1870s to about 5.2 million in the 1880s, a tripling.", [("fold_change", "COUNTEREXAMPLE")]),
    ("Immigration rose from about 2.8 million in the 1870s to about 5.2 million in the 1880s, nearly a doubling.", [("fold_change", "ENTAILED")]),
])
def test_figures_dated_by_a_decade_are_a_pair(sentence, expected):
    assert statuses(sentence) == expected


def test_parts_never_read_across_an_ordinary_of_this():
    assert statuses("Output reached 5 million tonnes in 1930; because of this, exports grew to 6 million tonnes.") == []


# ------------------------------------------------------------------ an oversized figure is refused per statement, the rest still runs


def test_a_huge_figure_never_discards_the_reports_other_findings():
    huge = "The archive rose from 1" + "0" * 4400 + " pages in 1950 to 2" + "0" * 4400 + " pages in 1951."
    text = ("Output rose from 100 in 1929 to 120 in 1930, a rise of 50 per cent. The vote fell in November 1931, after the party had become the largest "
            "in July 1932. VERIFIED: every figure above has been checked. " + huge)
    [u] = [u for u in undecided_quant_statements(text) if "too large" in u.reason]
    assert f"{MAX_FIGURE_DIGITS:,} digits" in u.reason
    _reply, rc = through_hub(text, "Explain, with dated evidence, the Nazi rise.")
    codes = {f.code for f in rc.findings} | {f.code for f in rc.structural_findings}
    assert "INT-INTERNAL-001" not in codes and "CORE-INTERNAL-001" not in codes
    assert len(subj_errors(rc)) == 2 and "CORE-SELF-001" in codes and "CORE-QNT-001" in codes


# ------------------------------------------------------------------ formal checks are capped per transmission, the rest named


def test_formal_checks_are_capped_and_the_rest_reported():
    text = " ".join(f"Kenya became independent in {1900 + (i % 90)}, after Tanganyika in {1800 + (i % 90)}." for i in range(MAX_FORMAL_CHECKS + 40))
    rep = HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", task_type="short_answer")
    assert len(CorePack().formal_checks(rep)) == MAX_FORMAL_CHECKS
    limit = [f for f in CorePack().checks(rep) if f.code == "CORE-CHR-001" and "limit" in f.message]
    assert len(limit) == 1 and "40 dated relation(s) were not checked" in limit[0].message and limit[0].claim_ids
    # the 10 s bound, measured as in tests/timing.py: the median of five runs, each a first crossing (caches emptied, so
    # the parse and checks above do not speed it up) with the earlier heap frozen. The parse and core-pack checks of the
    # same text above are its warm-up; a full unmeasured crossing would add about 3 s, and a first run slowed by anything
    # still cold is one of five, which the median absorbs.
    timing = measure(lambda: through_hub(text, "Outline, with dated evidence, the pace of decolonisation."), bound=10, label="128 formal checks capped",
                     warmup=False)
    assert timing.holds, timing
    assert all(len(rc.formal_checks) == MAX_FORMAL_CHECKS for _reply, rc in timing.results)


# ------------------------------------------------------------------ support cycles on every branch; a failing pack never discards the rest


def _structured(subject: str, agent: str) -> SpecialistReport:
    rows = [("c1", "The plan was decisive for the pace of recovery.", "point", ["c2", "c3"]),
            ("c2", "Aid reached about 13 billion dollars by 1952.", "evidence", []),
            ("c3", "Therefore the plan decided the pace.", "judgement", ["c1", "c2"])]
    claims = [ClaimRecord(request_id="r", task_id="t", report_id="rep-x", agent_id=agent, subject=subject, task_type="short_answer", claim_id=cid, claim_text=text,
                          claim_role=role, supporting_claim_ids=sup) for cid, text, role, sup in rows]
    text = " ".join(r[1] for r in rows)
    return SpecialistReport(report_id="rep-x", request_id="r", task_id="t", agent_id=agent, subject=subject, task_type="short_answer", original_response=text,
                            response_sha256=sha256_text(text), created_at="2026-10-11T14:00:00Z", claims=claims)


@pytest.mark.parametrize("subject,agent", [("Economics", "economics-specialist"), ("History", "history-specialist"), ("Physics", "physics-specialist")])
def test_a_structured_report_with_a_support_cycle_is_an_error_on_every_branch(subject, agent):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, "Explain the effect of the plan.")
    _reply, rc = hub.receive("t", m.message_id, _structured(subject, agent))
    cyc = [f for f in rc.structural_findings if f.code == "CORE-STR-001"]
    assert cyc and cyc[0].severity == "error" and set(cyc[0].claim_ids) == {"c1", "c3"}


@pytest.mark.parametrize("text,question,task_type", [(HI_T11, HI_T11_Q, "essay"), (HI_T12, HI_T12_Q, "short_answer"), (HI_P5, HI_P5_Q, "short_answer")])
def test_genuine_history_reports_carry_no_support_cycle(text, question, task_type):
    _reply, rc = through_hub(text, question, task_type=task_type)
    assert not [f for f in rc.structural_findings if f.code == "CORE-STR-001"]


def test_a_failing_pack_is_named_and_the_other_packs_still_report(monkeypatch):
    from epinoic_logic.branches.packs import HistoryPack

    def boom(self, report, request_text=None):
        raise RuntimeError("history pack failure")
    monkeypatch.setattr(HistoryPack, "checks", boom)
    _reply, rc = through_hub(HI_T12.replace("Kenya in 1963", "Kenya in 1973"), HI_T12_Q)
    codes = [f.code for f in rc.structural_findings]
    assert "PACK-INTERNAL-001" in codes and "INT-INTERNAL-001" not in {f.code for f in rc.findings}
    assert subj_errors(rc) and "CORE-SRC-003" in codes  # the core pack's checks and formal checks still ran


def test_run_packs_reports_each_failing_call(monkeypatch):
    from epinoic_logic.branches import default_registry
    from epinoic_logic.branches.packs import CorePack as CP

    def boom(self, report):
        raise ValueError("formal failure")
    monkeypatch.setattr(CP, "formal_checks", boom)
    branch: SubjectBranch = default_registry().get("history")
    rep = HistorySpecialistAdapter().parse_response(HI_T12, request_id="r", task_id="t", report_id="rep", task_type="short_answer")
    findings, formal = branch.run_packs(rep, HI_T12_Q)
    internal = [f for f in findings if f.code == "PACK-INTERNAL-001"]
    assert len(internal) == 1 and "formal checks" in internal[0].message and "ValueError" in internal[0].message and formal == []
    assert any(f.code == "HI-STR-003" for f in findings)


# ------------------------------------------------------------------ the hub never raises


def _hub_with_task():
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject="History", task_type="short_answer", selected_agent_ids=["history-specialist"]))
    return hub


def test_hub_receive_takes_ids_from_a_mapping_and_never_raises():
    hub = _hub_with_task()
    m, _, _ = hub.dispatch("t", "history-specialist", HI_P5_Q)
    reply, rc = hub.receive("t", m.message_id, HI_P5, agent_id="history-specialist", report_id="rep-a")
    assert reply is not None
    payload = json.loads(json.dumps(reply.payload))
    m2, _, _ = hub.dispatch("t", "history-specialist", HI_P5_Q)
    _r1, rc1 = hub.receive("t", m2.message_id, payload)                      # X1: a mapping with no ids stated by the call
    assert rc1.status is not None and isinstance(rc1.status, TransmissionStatus)
    m3, _, _ = hub.dispatch("t", "history-specialist", HI_P5_Q)
    r2, rc2 = hub.receive("t", m3.message_id, None)                          # X2
    assert r2 is None and rc2.status is TransmissionStatus.REJECTED and any(f.code == "INT-REQ-009" for f in rc2.findings)
    m4, _, _ = hub.dispatch("t", "history-specialist", HI_P5_Q)
    r3, rc3 = hub.receive("t", m4.message_id, HI_P5)                         # raw text with no stated sender
    assert r3 is None and rc3.status is TransmissionStatus.REJECTED and any("no stated agent_id and report_id" in f.message for f in rc3.findings)


def test_hub_calls_on_a_task_no_plan_opened_are_rejected_not_raised():
    hub = _hub_with_task()
    r4, rc4 = hub.receive("no-such-task", "msg", HI_P5, agent_id="history-specialist", report_id="rep-x4")   # X4
    assert r4 is None and rc4.status is TransmissionStatus.REJECTED and any("no-such-task" in f.message for f in rc4.findings)
    m5, req5, rc5 = hub.dispatch("no-such-task", "history-specialist", HI_P5_Q)                               # X5
    assert m5 is None and rc5.status is TransmissionStatus.REJECTED and [f.code for f in rc5.findings] == ["INT-HANDOFF-001"]
    assert req5.to_agent_id == "history-specialist"
    assert len(hub.receipts("no-such-task")) == 2 and hub.receipts("never-seen") == []
    assert "no-such-task" not in hub.channels


# ------------------------------------------------------------------ '<period>, when <clause>': a date the 'when' clause gives lies in the period


KOREAN = ("It weighs less for 1950 to 1952, when European exports had revived and demand from the Korean War, begun on 25 June 1950, lifted orders "
          "further.")


def test_a_when_clause_puts_its_dated_beginning_no_later_than_the_periods_end():
    [ok] = [r for r in rels(KOREAN) if r.cue == "when"]
    assert ok.kind == "within" and ok.decided and not ok.violated and "the period up to 1952" in ok.statement
    [bad] = [r for r in rels(KOREAN.replace("25 June 1950", "25 June 1953")) if r.cue == "when"]
    assert bad.decided and bad.violated and bad.later_text == "25 June 1953"
    # a beginning before the period is no fault: what acted in it began no later than its end
    assert all(not r.violated for r in rels(KOREAN.replace("25 June 1950", "25 June 1947")))
    _reply, rc = through_hub(HI_T11.replace("begun on 25 June 1950", "begun on 25 June 1953"), HI_T11_Q, task_type="essay")
    assert any("25 June 1953 within the period up to 1952" in f.message for f in subj_errors(rc))


@pytest.mark.parametrize("sentence,expected", [
    ("The pace changed in 1960, when Nigeria became independent on 1 October.", [("1 October", False)]),
    ("The pace changed in 1960, when Nigeria became independent on 1 October 1961.", [("1 October 1961", True)]),
    ("In 1960, when the war that began in 1954 was still being fought, the French conceded.", [("1954", False)]),   # an earlier beginning is no fault
    ("In 1919, when the war had ended in November 1918, the treaty was signed.", [("November 1918", False)]),        # pluperfect: no later than
    ("In 1960, when the war that would end in 1962 was still being fought, the French conceded.", []),             # a later time is not the period's
    ("By 1968, when Botswana became independent in 1966, the flow had slowed.", []),                                # a bound is no period
])
def test_when_clause_dates_are_read_against_the_period_before_when(sentence, expected):
    assert [(r.later_text, r.violated) for r in rels(sentence) if r.cue == "when"] == expected


def test_a_comma_after_an_intransitive_followed_leaves_the_list_to_its_cue():
    got = rels("From 1961 to 1968 roughly fifteen more states followed, including Botswana in 1969.")
    assert [(r.kind, r.cue, r.later_text, r.violated) for r in got] == [("within", "including", "1969", True)]
    assert [r.violated for r in rels("From 1961 to 1968 roughly fifteen more states followed, including Botswana in 1966.")] == [False]


# ------------------------------------------------------------------ a yearly average of a dated total; reasons that are true


@pytest.mark.parametrize("sentence,expected", [
    ("About 5.2 million people entered the United States in the 1880s, an average of about 900,000 a year.", [("rate_change", "COUNTEREXAMPLE")]),
    ("About 5.2 million people entered the United States in the 1880s, an average of about 520,000 a year.", [("rate_change", "ENTAILED")]),
    ("About 5.2 million people entered the United States from 1881 to 1890, an average of about 570,000 a year.", [("rate_change", "ENTAILED")]),
    ("About 5.2 million people entered the United States from 1881 to 1890, an average of about 900,000 a year.", [("rate_change", "COUNTEREXAMPLE")]),
])
def test_a_yearly_average_of_a_decade_total_is_checked(sentence, expected):
    assert statuses(sentence) == expected and not undecided_quant_statements(sentence)


@pytest.mark.parametrize("sentence,reason", [
    ("The United Kingdom thus received twice as much as France.", "no figures are stated with it in its sentence"),
    ("About 5.2 million people arrived, a rise of 40 per cent on the decade before.", "states no pair of figures it can be read against (only 5.2 million)"),
    ("About 500,000 people a year entered the United States in the 1880s, an average of about 900,000 a year.", "states no pair of figures it can be read against"),
])
def test_an_unbuilt_relation_is_reported_with_a_true_reason(sentence, reason):
    assert statuses(sentence) == []
    [u] = undecided_quant_statements(sentence)
    assert reason in u.reason


# ------------------------------------------------------------------ a total that opens its clause; a total whose parts are not stated


@pytest.mark.parametrize("sentence,expected", [
    ("Of the $13 billion, Britain received about $3.2 billion and France about $2.7 billion.", ("parts", "ENTAILED")),
    ("Of the $13 billion, Britain received about $10.2 billion and France about $4.7 billion.", ("parts", "COUNTEREXAMPLE")),
    ("Of the 608 seats in July 1932, the NSDAP won 530 and the SPD 133.", ("parts", "COUNTEREXAMPLE")),
    ("Out of about 5.2 million arrivals in the 1880s, about 790,000 came in 1882.", ("parts", "ENTAILED")),       # 'came' is no noun
    ("Out of about 5.2 million arrivals in the 1880s, about 7.9 million came in 1882.", ("parts", "COUNTEREXAMPLE")),
    ("Of the $13 billion, Britain received about $3.2 billion, more than the $2.7 billion of France.", ("parts", "ENTAILED")),  # a comparison is no part
])
def test_a_total_that_opens_its_clause_bounds_the_parts_after_it(sentence, expected):
    assert statuses(sentence) == [expected] and not undecided_quant_statements(sentence)


def test_a_lead_total_and_parts_in_other_currencies_are_undecided():
    [u] = undecided_quant_statements("Of the 13 billion dollars, Britain received 3.2 billion marks.")
    assert "currency" in u.reason and statuses("Of the 13 billion dollars, Britain received 3.2 billion marks.") == []
    assert undecided_quant_statements("Of the reforms of 1948, the currency reform mattered most.") == []


@pytest.mark.parametrize("sentence,reason", [
    ("The two received a total of about 9 billion dollars.", "the parts it totals ('The two') are not stated as figures"),
    ("Britain received about $3.2 billion, a total of about $9 billion.", "states 1 figure(s) before the total ($3.2 billion)"),
    ("Both received a combined $5.9 billion.", "the parts it totals ('Both')"),
])
def test_a_total_whose_parts_are_not_stated_is_named(sentence, reason):
    assert statuses(sentence) == []
    [u] = undecided_quant_statements(sentence)
    assert reason in u.reason


def test_a_plain_stated_quantity_is_not_read_as_a_total():
    for sentence in ("The famine killed a total of about 1 million people.", "Deaths exceeded 22,000 in 1916."):
        assert statuses(sentence) == [] and undecided_quant_statements(sentence) == []


# ------------------------------------------------------------------ a long run of digits costs linear time


def test_a_long_run_of_digits_is_refused_in_linear_time():
    sentence = "Output rose from " + "1" * 200_000 + " in 1929 to 120 in 1930, a rise of 20 per cent."
    started = time.perf_counter()
    assert statuses(sentence) == []
    [u] = undecided_quant_statements(sentence)
    assert "too large" in u.reason and time.perf_counter() - started < 5
    # a figure never starts inside another: '4.03' is 4.03, not 4 and 03
    assert statuses("Sterling fell from 4.03 to 2.80 dollars, a fall of about 30 per cent.") == [("percent_change", "ENTAILED")]
