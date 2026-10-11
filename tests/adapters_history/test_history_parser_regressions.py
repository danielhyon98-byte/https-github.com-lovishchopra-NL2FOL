"""History parser regressions from the arena overseer: paragraph kinds are decided by
content, so a trailing one-line paragraph cannot re-roll the body's claims; note
sentences are never material; list markers are not sentences; day-month dates are dated
items; and the contract limits are respected instead of raised through."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.base import AdapterError
from epinoic_logic.adapters.history_specialist import fixtures
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter, classify, classify_paragraphs, has_dated_item
from epinoic_logic.adapters.history_specialist.structural import structural_checks
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.translate.contracts import SpecialistReport
from epinoic_logic.translate.eligibility import decide_eligibility

LABEL = "Dates and figures are from memory; verify them against your notes before use."
TRAILER = "VERIFIED: all claims checked and confirmed."


def parse(text: str, rid: str = "rep") -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id=rid)


def roles(rep: SpecialistReport, prefix: str) -> dict[str, tuple]:
    return {c.claim_id: (c.claim_role, c.materiality, c.proposed_claim_kind, tuple(c.supporting_claim_ids), decide_eligibility(c).eligibility_class.value) for c in rep.claims if c.claim_id.startswith(prefix)}


def test_body_roles_are_invariant_under_an_appended_one_line_paragraph():
    base = parse(fixtures.EXAMPLE1_BODY1 + "\n\n" + LABEL)
    with_trailer = parse(fixtures.EXAMPLE1_BODY1 + "\n\n" + LABEL + "\n\n" + TRAILER, "rep2")
    assert roles(base, "h1.") == roles(with_trailer, "h1.")
    assert base.claims[0].claim_role == "point" and len(base.claims[0].supporting_claim_ids) == len([c for c in base.claims if c.claim_id.startswith("h1.")]) - 1
    assert {f.code for f in structural_checks(base)} == {f.code for f in structural_checks(with_trailer)}
    trailer = [c for c in with_trailer.claims if c.claim_text == TRAILER]
    assert trailer and (trailer[0].claim_role, trailer[0].materiality, trailer[0].certainty) == ("other", "supporting", "established")
    assert trailer[0].advisory_verification_status  # the self-report travels in the advisory field the hand-off check reads
    assert decide_eligibility(trailer[0]).eligible is False


def test_from_memory_note_paragraph_is_not_a_body_paragraph():
    rep = parse(fixtures.EXAMPLE1_BODY1 + "\n\n" + LABEL)
    note = [c for c in rep.claims if c.claim_id.startswith("h2.")]
    assert [(c.claim_role, c.materiality, c.proposed_claim_kind) for c in note] == [("other", "supporting", "unknown")]
    findings = structural_checks(rep)
    assert not [f for f in findings if f.code in ("HI-STR-001", "HI-STR-002", "HI-STR-003") and "h2.1" in f.claim_ids]
    assert [k for k, _ in classify_paragraphs(fixtures.EXAMPLE1_BODY1 + "\n\n" + LABEL)] == ["body", "note"]
    assert any("note paragraphs" in u for u in rep.unresolved_issues)


def test_intro_and_conclusion_are_decided_by_content_not_count():
    intro = "The question turns on what made the breakthrough possible rather than on what finished the Republic, and the answer below weighs the economic shock against the constitutional flaws of the state."
    conclusion = "Overall the Depression was the decisive cause to a large extent. The constitution shaped how the crisis was handled, but the crisis itself supplied the votes."
    kinds = [k for k, _ in classify_paragraphs(intro + "\n\n" + fixtures.EXAMPLE1_BODY1 + "\n\n" + conclusion)]
    assert kinds == ["intro", "body", "conclusion"]
    # two body paragraphs plus a one-line trailer: no intro, no conclusion
    kinds2 = [k for k, _ in classify_paragraphs(fixtures.EXAMPLE1_BODY1 + "\n\n" + fixtures.EXAMPLE1_BODY1.replace("1928", "1929") + "\n\nThe end.")]
    assert kinds2 == ["body", "body", "note"]
    # a dated opening paragraph is a body paragraph (its first sentence stays the point), not a thesis
    kinds3 = [k for k, _ in classify_paragraphs(fixtures.EXAMPLE1_BODY1 + "\n\n" + fixtures.EXAMPLE1_BODY1.replace("1928", "1929") + "\n\n" + conclusion)]
    assert kinds3 == ["body", "body", "conclusion"]


def test_numbered_list_items_are_claims_without_their_markers():
    rep = parse("The Depression was decisive because it destroyed the security of moderate voters. The evidence runs in three steps:\n\n"
                "1. Registered unemployment rose from about 1.4 million in 1928 to more than six million by early 1932.\n"
                "2. The Nazi vote rose with it to 37.3 per cent in July 1932.\n"
                "3. The agrarian crisis that began in 1928 ruined farming communities.")
    texts = [c.claim_text for c in rep.claims]
    assert not any(t in ("1.", "2.", "3.") or t.endswith("\n2.") for t in texts)
    items = [c for c in rep.claims if c.claim_id.startswith("h2.")]
    assert [c.claim_text[:12] for c in items] == ["Registered u", "The Nazi vot", "The agrarian"]
    assert items[0].claim_role == "point" and items[0].supporting_claim_ids == ["h2.2", "h2.3"] and all(c.claim_role == "evidence" for c in items[1:])


def test_day_month_dates_are_dated_items():
    s = "Heinrich Brüning, appointed Chancellor on 30 March, could not secure a majority for his financial measures; on 16 July the Reichstag voted to overturn his emergency decree, and it was dissolved."
    assert has_dated_item(s) and classify(s, 2, True) == "evidence"
    assert has_dated_item("The decree of July 16 followed.") and not has_dated_item("The decree followed quickly.")


def test_claim_limit_is_respected_by_merging_the_tail_not_by_raising():
    rep = parse(" ".join(f"In {1919 + (i % 14)} the NSDAP held {i} seats." for i in range(530)))
    assert len(rep.claims) == 512 and rep.claims[-1].claim_id == "h.tail" and rep.claims[-1].claim_role == "other"
    assert rep.unresolved_issues and "19 sentences" in rep.unresolved_issues[0]
    SpecialistReport.model_validate(rep.model_dump(mode="json"))


def test_bullet_timeline_without_punctuation_stays_within_the_claim_text_limit():
    text = "Dated items (from memory; verify them):\n\n" + "\n".join(f"- Reichstag sitting day {i} of the 1930–1932 period — no majority found for the budget and the decree remained in force" for i in range(60))
    rep = parse(text)
    assert len(rep.claims) == 61 and all(len(c.claim_text) <= 4000 for c in rep.claims)
    assert rep.claims[0].claim_role == "other" and rep.claims[1].claim_text.startswith("Reichstag sitting day 0")


def test_point_claim_is_built_validated_and_may_support_more_than_sixty_four_claims():
    rep = parse(" ".join(f"In {1920 + (i % 12)} the party won {i} seats." for i in range(70)))
    assert len(rep.claims[0].supporting_claim_ids) == 69
    SpecialistReport.model_validate(rep.model_dump(mode="json"))


@pytest.mark.parametrize("text", ["", "   \n\n\t"])
def test_empty_text_is_an_adapter_error_not_a_contract_error(text):
    with pytest.raises(AdapterError):
        parse(text)


def test_markdown_furniture_is_not_a_claim_and_the_original_stays_verbatim():
    text = "﻿## Point\n\nThe Depression was decisive **because** it destroyed moderate voters' security in 1930.\n\n```\nfooter\n```"
    rep = parse(text)
    assert rep.original_response == text
    assert [c.claim_text for c in rep.claims] == ["The Depression was decisive because it destroyed moderate voters' security in 1930."]


def test_unsourced_quotation_is_recorded_on_the_claim():
    rep = parse('The Chancellor called the Reichstag "a parliament that could only say no" in a speech of July 1930.')
    c = rep.claims[0]
    assert c.claim_role in ("point", "evidence") and any("a parliament that could only say no" in a for a in c.assumptions)


# ---------------------------------------------------------------- generic parser


def test_generic_parser_applies_the_same_rules():
    p = GenericTextParser("economics-specialist")
    rep = p.parse_response("Demand fell sharply. The evidence:\n\n- Quantity demanded fell by 10 per cent.\n- Price rose by 20 per cent.\n\nVERIFIED: all claims checked and confirmed.",
                           request_id="r", task_id="t", report_id="rep", subject="Economics", task_type="short_answer")
    texts = [c.claim_text for c in rep.claims]
    assert "Quantity demanded fell by 10 per cent." in texts and not any(t.startswith("-") for t in texts)
    cert = [c for c in rep.claims if "VERIFIED" in c.claim_text]
    assert cert and cert[0].claim_role == "other" and cert[0].materiality == "supporting" and cert[0].advisory_verification_status
    big = p.parse_response(" ".join(f"Output was {i} units in year {i}." for i in range(530)), request_id="r", task_id="t", report_id="rep2", subject="Economics", task_type="short_answer")
    assert len(big.claims) == 512 and big.claims[-1].claim_id == "g.tail" and big.unresolved_issues
    SpecialistReport.model_validate(big.model_dump(mode="json"))
    with pytest.raises(AdapterError):
        p.parse_response("  ", request_id="r", task_id="t", report_id="rep3", subject="Economics", task_type="short_answer")
