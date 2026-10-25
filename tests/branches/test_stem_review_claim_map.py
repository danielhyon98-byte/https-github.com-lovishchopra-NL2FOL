"""STEM review S4: claim ids never outrank source spans (docs/STEM_DESIGN.md, section 9.1). The STEM pack attaches its
checks and findings to the report's claims by their source spans and texts; a familiar-looking id ('s1.1') whose text is
another statement's is no evidence: the statement is mapped by text and the disagreement is named (ST-CLAIM-001,
warning), so a failed check is never attributed to the correct claim and a passing check to the false one. Controls: ids
that agree with their texts (the parser's own, or any other spelling) map exactly as before, with no finding."""
from __future__ import annotations

from epinoic_logic.adapters.stem_specialist import StemTextParser, statement_claim_text
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.stem_pack import StemPack
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text

KEY = b"stem-review-claim-map-key-0123456789"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
TEXT = "2 + 2 = 5.\n3 + 3 = 6."


def structured(text: str, pairs: list[tuple[str, str]], subject: str = "Physics", rid: str = "r") -> SpecialistReport:
    common = dict(request_id="q", task_id="t", report_id=rid, agent_id="spec", subject=subject, task_type="short_answer")
    return SpecialistReport(**common, original_response=text, response_sha256=sha256_text(text), created_at="2026-10-12T00:00:00Z",
                            claims=[ClaimRecord(**common, claim_id=cid, claim_text=t, claim_role="quantitative") for cid, t in pairs])


def receive(report_or_text, subject: str = "Physics"):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=subject, task_type="short_answer", selected_agent_ids=["spec"]))
    m, _req, _rq = hub.dispatch("t", "spec", "Check the arithmetic.")
    reply, rc = hub.receive("t", m.message_id, report_or_text, agent_id="spec", report_id="r")
    assert reply is not None
    return rc


def checks(rc) -> dict[str, tuple[bool, list[str]]]:
    return {c.constraint_id: (c.satisfied, list(c.claim_ids)) for c in rc.formal_checks}


def test_swapped_familiar_ids_never_carry_the_check_of_the_other_statement():
    rc = receive(structured(TEXT, [("s1.2", "2 + 2 = 5."), ("s1.1", "3 + 3 = 6.")]))
    # the failed check is on the claim whose text is the false sum, the passing one on the true sum
    assert checks(rc) == {"stem-eq-1": (False, ["s1.2"]), "stem-eq-2": (True, ["s1.1"])}
    errors = [f for f in rc.findings if f.code == "INT-SUBJ-001"]
    assert len(errors) == 1 and errors[0].claim_ids == ["s1.2"] and "in claim s1.2" in errors[0].message and "[claims s1.2]" in errors[0].message
    assert "s1.1" not in errors[0].message
    named = [sf for sf in rc.structural_findings if sf.code == "ST-CLAIM-001"]
    assert len(named) == 1 and named[0].severity == "warning" and set(named[0].claim_ids) == {"s1.1", "s1.2"}
    assert "claim id 's1.1' is spelled like statement s1.1 ('2 + 2 = 5.'), but its text is '3 + 3 = 6.'" in named[0].message


def test_other_spellings_map_the_same_content_the_same_way_with_no_finding():
    rc = receive(structured(TEXT, [("first", "2 + 2 = 5."), ("second", "3 + 3 = 6.")]))
    assert checks(rc) == {"stem-eq-1": (False, ["first"]), "stem-eq-2": (True, ["second"])}
    assert not [sf for sf in rc.structural_findings if sf.code == "ST-CLAIM-001"]


def test_ids_that_agree_with_their_texts_keep_their_mapping():
    rc = receive(structured(TEXT, [("s1.1", "2 + 2 = 5."), ("s1.2", "3 + 3 = 6.")]))
    assert checks(rc) == {"stem-eq-1": (False, ["s1.1"]), "stem-eq-2": (True, ["s1.2"])}
    assert not [sf for sf in rc.structural_findings if sf.code == "ST-CLAIM-001"]
    raw = receive(TEXT)  # the STEM parser's own claims
    assert checks(raw) == {"stem-eq-1": (False, ["s1.1"]), "stem-eq-2": (True, ["s1.2"])}
    assert not [sf for sf in raw.structural_findings if sf.code == "ST-CLAIM-001"]


def test_a_familiar_id_whose_text_is_nowhere_in_the_answer_gets_no_check():
    rc = receive(structured(TEXT, [("s1.1", "The answer is correct."), ("x-2", "2 + 2 = 5."), ("x-3", "3 + 3 = 6.")]))
    assert checks(rc) == {"stem-eq-1": (False, ["x-2"]), "stem-eq-2": (True, ["x-3"])}
    named = [sf for sf in rc.structural_findings if sf.code == "ST-CLAIM-001"]
    assert named and "claim id 's1.1'" in named[0].message and "attached to x-2" in named[0].message


def test_branch_letters_are_checked_against_the_text_too():
    pack = StemPack("mathematics")
    rep = structured(TEXT, [("m1.2", "2 + 2 = 5."), ("m1.1", "3 + 3 = 6.")], subject="Mathematics: Analysis and Approaches")
    formal = {fc.check_id: fc.claim_ids for fc in pack.formal_checks_for(rep, None)}
    assert formal == {"stem-eq-1": ("m1.2",), "stem-eq-2": ("m1.1",)}
    assert [f.code for f in pack.checks(rep, None) if f.code == "ST-CLAIM-001"] == ["ST-CLAIM-001"]


def test_a_parser_claim_whose_text_leaves_markup_out_keeps_its_id():
    text = "The *sum* is 2 + 2 = 5.\nThen 3 + 3 = 6."
    rep = StemTextParser().parse_response(text, request_id="q", task_id="t", report_id="r", subject="Physics", task_type="short_answer")
    first = rep.claims[0]
    assert first.claim_text == "The sum is 2 + 2 = 5." and first.claim_text not in text  # not an offset substring
    doc = build_document(text, None, "physics")
    st = doc.statements[0]
    assert statement_claim_text(text, doc, st.start, st.end) == first.claim_text
    formal = {fc.check_id: fc.claim_ids for fc in StemPack("sciences").formal_checks_for(rep, None)}
    assert formal == {"stem-eq-1": (first.claim_id,), "stem-eq-2": (rep.claims[1].claim_id,)}
    assert not [f for f in StemPack("sciences").checks(rep, None) if f.code == "ST-CLAIM-001"]
    # the same id with another text is not trusted: the statement goes to the claim that holds its text
    swapped = structured(text, [("s1.1", "Then 3 + 3 = 6."), ("other", "The sum is 2 + 2 = 5.")])
    formal = {fc.check_id: fc.claim_ids for fc in StemPack("sciences").formal_checks_for(swapped, None)}
    assert formal == {"stem-eq-1": ("other",), "stem-eq-2": ("s1.1",)}


def test_a_repeated_line_maps_to_its_own_occurrence():
    text = "x = 2 + 2 = 5\ny = 1\nx = 2 + 2 = 5"
    rep = structured(text, [("a", "x = 2 + 2 = 5"), ("b", "y = 1"), ("c", "x = 2 + 2 = 5")])
    formal = [fc for fc in StemPack("sciences").formal_checks_for(rep, None) if fc.kind == "stem_arithmetic"]
    assert sorted(fc.claim_ids for fc in formal) == [("a",), ("c",)]
