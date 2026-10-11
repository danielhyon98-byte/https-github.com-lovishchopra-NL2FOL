"""Consolidation pass on the adapters and parsers.

Attribution: the English, History and generic parsers apply one rule
(``sources.attribute_excerpt``): the text that holds the words wins; a quotation held by no
text is credited to the one text its sentence names, whether or not that text holds the
words; otherwise it is credited to no text, carries no source reference and records the
assumption that the core pack reports as CORE-SRC-003, on the English branch too. The
English branch's one addition: a sentence that names no text quotes the one literary text
under analysis. Named-but-wrong credits stay ES-SRC-008 / CORE-SRC-005.

Diacritics through the hub: 'Bayardo San Román' quoted from a text printing 'Bayardo San
Roman' (arena round 1, adversarial file en-t2-diacritic-ellipsis, claim p4-q02) is
INT-REQ-010 and an ES-SRC-006 warning, not INT-REQ-003 + ES-SRC-001.

Long elision on the generic structured adapter: every located form-difference status of the
shared excerpt check (a long elision, diacritics, an initial capital) is the inexact warning
code, never the not-found error."""
from __future__ import annotations

import json

import pytest

from epinoic_logic.adapters import GenericStructuredAdapter
from epinoic_logic.adapters.english_specialist.example1_texts import EXAMPLE1_SOURCE_EXTRACT
from epinoic_logic.adapters.english_specialist.parser import parse_response as english_parse
from epinoic_logic.adapters.english_specialist.structural import structural_checks as english_checks
from epinoic_logic.adapters.history_specialist.parser import HistorySpecialistAdapter
from epinoic_logic.adapters.sources import UNCREDITED_QUOTATION, attribute_excerpt, check_excerpt, uncredited_assumption, uncredited_excerpt
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.branches.packs import CorePack
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.translate.contracts import SpecialistReport, SuppliedText

KEY = b"consolidation-attribution-key-0123456789"
CFG = SolverConfig(timeout_ms=3000, memory_max_mb=None)

TOWN = SuppliedText(document_id="doc-town", title="The Town", author="Thomas Fielding",
                    text="The river carries the charter of the town, and every face I meet bears marks of weakness, marks of woe.")
FIELD = SuppliedText(document_id="doc-field", title="The Field", author="Mary Holt",
                     text="The plough turns the field in silence while the larks rise over the hedges at dawn.")
PEER = SuppliedText(document_id="peer:hi-p9", title="history-specialist report relayed through the hub", author="history-specialist",
                    text="The charter of 1600 gave the Company its monopoly. Parliament renewed it in 1793.")
CDF = SuppliedText(document_id="doc-cdf", title="Chronicle of a Death Foretold (extract)", author="Gabriel García Márquez", text=EXAMPLE1_SOURCE_EXTRACT)


def english(text: str, texts) -> SpecialistReport:
    return english_parse(text, request_id="r", task_id="t", report_id="rep", subject="English A: Literature", task_type="analytical_paragraph", supplied_texts=list(texts))


def history(text: str, texts) -> SpecialistReport:
    return HistorySpecialistAdapter().parse_response(text, request_id="r", task_id="t", report_id="rep", supplied_texts=list(texts))


def generic(text: str, texts) -> SpecialistReport:
    return GenericTextParser("psychology-specialist").parse_response(text, request_id="r", task_id="t", report_id="rep", subject="Psychology", task_type="short_answer", supplied_texts=list(texts))


def through_hub(text: str, texts, *, subject: str = "English A: Literature", agent: str = "english-specialist", task_type: str = "analytical_paragraph",
                question: str = "Write one analytical paragraph on the extract. Quote from the extract."):
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="r", task_id="t", subject=subject, task_type=task_type, selected_agent_ids=[agent],
                           allowed_document_ids=[t.document_id for t in texts]))
    m, _, _ = hub.dispatch("t", agent, question, list(texts))
    return hub.receive("t", m.message_id, text, agent_id=agent, report_id="rep-x")


def attribution(report: SpecialistReport, excerpt: str) -> tuple[list[str], list[str]]:
    """(documents credited, attribution assumptions) for the claim(s) quoting ``excerpt``."""
    docs: list[str] = []
    notes: list[str] = []
    for c in report.claims:
        if excerpt not in c.claim_text:
            continue
        docs += [r.document_id for r in c.source_refs if r.excerpt and excerpt in r.excerpt]
        notes += [a for a in c.assumptions if excerpt in a or a.startswith(("the sentence attributes this quotation", "excerpt found in none"))]
    return sorted(set(docs)), sorted(set(notes))


# ------------------------------------------------------------------ one attribution rule for the three parsers


SENTENCES = {
    # located only in doc-town though the sentence names Holt (doc-field): the located text wins, the discrepancy is recorded
    "located": ('Holt writes that "marks of weakness, marks of woe" mark every face.', "marks of weakness, marks of woe",
                ["doc-town"], ["the sentence attributes this quotation to doc-field but the words were located only in doc-town"]),
    # held by no text, the sentence names Fielding (doc-town): credited to the named text whether or not it holds the words
    "named": ('Fielding writes that "the chimney sweeper cries at noon" in the poem.', "the chimney sweeper cries at noon",
              ["doc-town"], ["excerpt found in none of the supplied texts [doc-town, doc-field]; attributed to doc-town because the sentence names it"]),
    # held by no text, the sentence names neither: credited to no text, the shared assumption recorded
    "unnamed": ('One critic writes that "the city sleeps beneath its laws" at night.', "the city sleeps beneath its laws",
                [], [uncredited_assumption("the city sleeps beneath its laws", "the sentence names no supplied text and the words occur in none of [doc-town, doc-field]")]),
}


@pytest.mark.parametrize("case", sorted(SENTENCES))
@pytest.mark.parametrize("parse", [english, history, generic], ids=["english", "history", "generic"])
def test_the_three_parsers_attribute_by_one_rule(case, parse):
    sentence, excerpt, docs, notes = SENTENCES[case]
    report = parse("The two poems answer each other. " + sentence + " The answer stands.", [TOWN, FIELD])
    assert attribution(report, excerpt) == (docs, notes)
    assert attribute_excerpt(excerpt, {"located": ["doc-field"], "named": ["doc-town"], "unnamed": []}[case], {"doc-town": TOWN, "doc-field": FIELD}) == (
        docs[0] if docs else None, notes)


def test_the_generic_parser_locates_in_every_recognised_form_before_crediting():
    # the generic parser used to locate with the exact and normalised tiers only and then fell back to the FIRST text;
    # a quotation the second text holds in another form (here, diacritics) is now credited to that text, and the hub's
    # form-difference warning follows instead of a 'not found' against the first text
    cdf_second = [TOWN, CDF]
    report = generic('The victim was, the villagers agreed, "Bayardo San Román" and nobody else.', cdf_second)
    [claim] = [c for c in report.claims if "Román" in c.claim_text]
    assert [(r.document_id, r.excerpt) for r in claim.source_refs] == [("doc-cdf", "Bayardo San Román")] and claim.assumptions == []
    reply, rc = through_hub('The victim was, the villagers agreed, "Bayardo San Román" and nobody else.', cdf_second, subject="Psychology",
                            agent="psychology-specialist", task_type="short_answer", question="Who was the victim?")
    assert reply is not None
    assert [f.code for f in rc.findings if claim.claim_id in f.claim_ids] == ["INT-REQ-010"]
    assert not [sf for sf in rc.structural_findings if sf.code == "CORE-SRC-001"]


def test_the_uncredited_assumption_round_trips():
    a = uncredited_assumption('a "nested" quotation', "why")
    assert a.startswith(UNCREDITED_QUOTATION) and uncredited_excerpt(a) == 'a "nested" quotation'
    assert uncredited_excerpt(uncredited_assumption("plain")) == "plain" and uncredited_excerpt("excerpt found in none of the supplied texts [d]") is None


def test_english_branch_an_unnamed_unlocated_quotation_is_core_src_003_when_no_text_is_the_one_under_analysis():
    # two literary texts and a sentence naming neither: no reference, no INT-REQ-003, CORE-SRC-003 on the receipt
    text = ('The two poems answer each other through their images of order. One critic writes that "the city sleeps beneath its laws", '
            'and the "marks of weakness, marks of woe" answer that sleep. Thus the poems meet.')
    report = english(text, [TOWN, FIELD])
    claim = next(c for c in report.claims if c.claim_text == '"the city sleeps beneath its laws"')
    assert claim.source_refs == [] and uncredited_excerpt(claim.assumptions[0]) == "the city sleeps beneath its laws"
    assert not [f for f in english_checks(report) if f.code == "ES-SRC-001"]
    reply, rc = through_hub(text, [TOWN, FIELD])
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    assert not [f for f in rc.findings if f.code == "INT-REQ-003"]
    [core] = [sf for sf in rc.structural_findings if sf.code == "CORE-SRC-003"]
    assert core.severity == "warning" and claim.claim_id in core.claim_ids and "the city sleeps beneath its laws" in core.message
    delivered = next(c for c in reply.payload["claims"] if c["claim_id"] == claim.claim_id)
    assert delivered["source_refs"] == []  # no invented reference to either text leaves the hub


def test_english_branch_a_short_uncredited_quotation_with_only_a_peer_supplied_still_reaches_core_src_003():
    # only the colleague's report is supplied: it is never the text under analysis, so a quotation it does not hold, in a
    # sentence naming no text, is credited to none; CORE-SRC-003 reads the parser's record, so even a quotation shorter
    # than the core pack's own span threshold is reported
    text = 'The charter is presented as a cage. The poem\'s "dark arch" closes the street. Thus the city is a prison.'
    report = english(text, [PEER])
    claim = next(c for c in report.claims if c.claim_text == '"dark arch"')
    assert claim.source_refs == [] and claim.assumptions == [uncredited_assumption("dark arch", "the sentence names no supplied text and the words occur in none of [peer:hi-p9]")]
    [core] = [f for f in CorePack().checks(report) if f.code == "CORE-SRC-003"]
    assert "'dark arch'" in core.message and claim.claim_id in core.claim_ids
    # the same answer with the poem supplied credits the poem under analysis and the hub refutes the quotation
    reply, rc = through_hub(text, [PEER, TOWN])
    poem_claim = next(c for c in reply.payload["claims"] if c["claim_text"] == '"dark arch"')
    assert [r["document_id"] for r in poem_claim["source_refs"]] == ["doc-town"]
    assert any(f.code == "INT-REQ-003" and poem_claim["claim_id"] in f.claim_ids for f in rc.findings)
    assert not [sf for sf in rc.structural_findings if sf.code == "CORE-SRC-003"]


def test_named_but_wrong_credits_keep_their_codes():
    # the sentence credits the colleague with the poem's words: ES-SRC-008 (error, a peer is involved) and CORE-SRC-005
    text = 'The History specialist observes that "marks of weakness, marks of woe" are recorded in the charter. Thus the poem indicts the town.'
    report = english(text, [TOWN, PEER])
    assert any(f.code == "ES-SRC-008" and f.severity == "error" for f in english_checks(report))
    assert any(f.code == "CORE-SRC-005" and f.severity == "error" for f in CorePack().checks(report))
    q = next(c for c in report.claims if c.claim_role == "evidence")
    assert [r.document_id for r in q.source_refs] == ["doc-town"]


# ------------------------------------------------------------------ diacritics through the hub (r1-adv en-t2-diacritic-ellipsis, claim p4-q02)


EN_T2_QUESTION = ("Write one analytical paragraph on how the extract constructs the reader's view of guilt and innocence. Quote from the extract. "
                  "Keep to about 350 words.")
EN_T2_DIACRITIC = (
    "García Márquez constructs the reader's view of guilt and innocence by separating the two judgements, so that the court and the town grant "
    "the twins innocence while the extract keeps their guilt physically and morally visible.\n\n"
    "The twins' declaration makes this separation explicit. \"We killed him openly,\" Pedro Vicario says, \"but we're innocent.\" The paradox turns "
    "on the verb \"killed\", which carries the admission, and on the conjunction \"but\", which sets a denial against it, so that confession and "
    "innocence stand side by side in one sentence. The key word is the adverb \"openly\", which conventionally means publicly and without "
    "concealment, and which carries connotations of candour and moral transparency. Here it lends the confession a virtue, so that candour appears "
    "to cancel culpability. García Márquez thus encourages the reader to test the claim rather than accept it, and the priest's reply, \"Perhaps "
    "before God\", defers the judgement to God rather than settling it.\n\n"
    "The physical detail works against that declared innocence. The twins place the knives, \"with clean blades,\" on the priest's desk, yet they "
    "arrive with \"faces smeared with sweat ... still living blood\", so the traces of the act stay on their bodies while the weapons look clean. "
    "This contrast locates guilt in the men rather than in the instruments. The narration then passes judgement: both twins were exhausted \"from "
    "the barbarous work of death.\" Conventionally, \"barbarous\" denotes savage cruelty, a condemnation that sits uneasily with the priest's view "
    "of the surrender as \"an act of great dignity\". García Márquez thus positions the reader to hold the appearance the twins present against the "
    "act their bodies record, so that visible guilt persists beneath the declared innocence.\n\n"
    "Together, these strands show that the verdicts of innocence from court and town rest on honour, whereas the extract's physical and narrative "
    "detail keeps the killing's guilt in view. The narrator's closing observation that \"we all could have been to blame\" spreads culpability "
    "across the community, so guilt is redistributed rather than cancelled. The only one who had lost everything was \"Bayardo San Román\", whose "
    "name the town shortens to \"poor Bayardo\". The reader is left to weigh a declared innocence against a guilt the text refuses to erase."
)


def test_a_quotation_differing_only_in_diacritics_is_int_req_010_and_a_pack_warning_through_the_hub():
    report = english(EN_T2_DIACRITIC, [CDF])
    q = next(c for c in report.claims if c.claim_id == "p4-q02")
    assert q.claim_text == '"Bayardo San Román"' and [(r.document_id, r.excerpt) for r in q.source_refs] == [("doc-cdf", "Bayardo San Román")]
    assert q.assumptions == []  # located (in another form), so no 'found in none' assumption
    assert check_excerpt("Bayardo San Román", "doc-cdf", {"doc-cdf": CDF}).status == "found_inexact"
    reply, rc = through_hub(EN_T2_DIACRITIC, [CDF], question=EN_T2_QUESTION)
    assert reply is not None and rc.status is not TransmissionStatus.REJECTED
    on_q = [f for f in rc.findings if "p4-q02" in f.claim_ids]
    assert [f.code for f in on_q] == ["INT-REQ-010"] and on_q[0].severity == "warning"
    assert "differs in diacritics ('Román' where the document has 'Roman')" in on_q[0].message and "ES-SRC-006" in on_q[0].message
    pack = [sf for sf in rc.structural_findings if "p4-q02" in sf.claim_ids]
    assert [(sf.code, sf.severity) for sf in pack] == [("ES-SRC-006", "warning")] and "differs in diacritics" in pack[0].message
    assert not [f for f in rc.findings if f.code in ("INT-REQ-003", "INT-SUBJ-003")]
    assert not rc.errors  # the genuine answer carries no error-level finding any more (it carried INT-REQ-003 for p4-q02)
    # the core pack does not call the excerpt 'not found' either (it said so before, kept off the receipt only by the channel)
    assert not [f for f in CorePack().checks(report) if f.code == "CORE-SRC-001"]
    invented = english(EN_T2_DIACRITIC.replace("Bayardo San Román", "Bayardo the bridegroom"), [CDF])
    assert [f.claim_ids for f in CorePack().checks(invented) if f.code == "CORE-SRC-001"] == [["p4-q02"]]


# ------------------------------------------------------------------ long elision and other form differences on the generic structured adapter


def structured(excerpt: str) -> SpecialistReport:
    doc = {"original_response": f'The extract says "{excerpt}".',
           "claims": [{"claim_id": "e1", "claim_text": f'"{excerpt}"', "claim_role": "evidence", "source_refs": [{"document_id": "doc-cdf", "excerpt": excerpt}]}]}
    return GenericStructuredAdapter().parse_response(json.dumps(doc), request_id="r", task_id="t", report_id="rep", subject="Psychology",
                                                     task_type="short_answer", supplied_texts=[CDF])


@pytest.mark.parametrize("excerpt,status,phrase", [
    ("The lawyer stood by the thesis of homicide ... as he was remembered over the years", "found_long_elision", "long elision, not an invented quotation"),
    ("Bayardo San Román", "found_inexact", "differs in diacritics"),
    ("for the immense majority of people there was only one victim", "found_inexact", "initial capital"),
])
def test_generic_structured_source_findings_report_every_form_difference_as_the_inexact_warning(excerpt, status, phrase):
    assert check_excerpt(excerpt, "doc-cdf", {"doc-cdf": CDF}).status == status
    findings = GenericStructuredAdapter().structural_checks(structured(excerpt))
    src = [f for f in findings if f.code.startswith("GEN-SRC")]
    assert [(f.code, f.severity) for f in src] == [("GEN-SRC-003", "warning")] and phrase in src[0].message and src[0].claim_ids == ["e1"]
    # an invented quotation is still the not-found error
    invented = GenericStructuredAdapter().structural_checks(structured("the river carried every secret of the town"))
    assert [(f.code, f.severity) for f in invented if f.code.startswith("GEN-SRC")] == [("GEN-SRC-001", "error")]
