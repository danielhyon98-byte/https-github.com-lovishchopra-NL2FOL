"""Repair round 4, rerun-security-2 variant: agent authorship is read from the words of an author or a provenance, not
from a fixed suffix. A supplied text whose author is "Economics Specialist (AI)", "economics_specialist" or "Maths
specialist, round 2", or whose provenance says "forwarded by the maths agent" or "copied from the History specialist's
answer", is another agent's output: it confers no authority, so the premise it alone supports stays ungrounded and the
result is not releasable. The grounding checks, the channel's source readers and the core pack use the same test. The
controls: a primary text by a person, an office or a bank, supplied by the student or the teacher, still grounds."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import is_peer_text
from epinoic_logic.branches.packs import _is_peer_text
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.grounding import AGENT_WORDS, is_peer_document, names_an_agent
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

KEY = b"k" * 32
TEXT = "Economics note: the price index rose to 5000 by November 1923."

AGENT_LABELS = [
    dict(author="Economics Specialist (AI)", provenance=None),
    dict(author="economics_specialist", provenance=None),
    dict(author="Maths specialist, round 2", provenance=None),
    dict(author="the History specialist's report", provenance=None),
    dict(author="Reichsbank", provenance="forwarded by the maths agent"),
    dict(author="Reichsbank", provenance="copied from the History specialist's answer"),
    dict(author=None, provenance="output of another specialist"),
    dict(author="combinator", provenance=None),
]
PRIMARY_LABELS = [
    dict(author="Reichsbank", provenance="supplied by student"),
    dict(author="A. Historian", provenance="supplied by student"),
    dict(author="Office for National Statistics", provenance="downloaded by the teacher"),
    dict(author="Health Protection Agency", provenance="task record issued by router"),
    dict(author=None, provenance=None),
]


@pytest.mark.parametrize("fields", AGENT_LABELS)
def test_an_agent_named_in_any_words_of_the_author_or_provenance_makes_a_peer_document(fields):
    doc = SuppliedText(document_id="doc-1", text=TEXT, **fields)
    assert is_peer_document(doc) and is_peer_text(doc) and _is_peer_text(doc)


@pytest.mark.parametrize("fields", PRIMARY_LABELS)
def test_control_a_primary_text_is_no_peer_document(fields):
    doc = SuppliedText(document_id="doc-1", text=TEXT, **fields)
    assert not is_peer_document(doc) and not is_peer_text(doc) and not _is_peer_text(doc)


def test_the_agent_words_are_a_closed_table_without_the_router():
    assert AGENT_WORDS == frozenset({"specialist", "specialists", "agent", "agents", "combinator"})
    assert names_an_agent("Economics-Specialist") and not names_an_agent("router") and not names_an_agent("Agency")


def _verify(author, provenance):
    sup = [SuppliedText(document_id="doc-1", author=author, text=TEXT, provenance=provenance)]
    text = "The price index rose to 5000, so it exceeded 1000."
    ids = dict(request_id="r", task_id="t", report_id="rep")
    claim = ClaimRecord(**ids, agent_id="generic-structured", subject="History", task_type="essay", claim_id="k1", claim_text=text,
                        claim_role="quantitative", proposed_claim_kind="arithmetic",
                        source_refs=[{"document_id": "doc-1", "excerpt": "the price index rose to 5000"}])
    rep = SpecialistReport(**ids, agent_id="generic-structured", subject="History", task_type="essay", original_response=text,
                           response_sha256=sha256_text(text), claims=[claim], supplied_texts=sup, created_at="2026-10-11T00:00:00Z")
    v = {"op": "var", "name": "p"}
    prob = {"problem_id": "k1-p", "request_id": "r", "claim_id": "k1", "query": "entailment",
            "symbols": [{"name": "p", "sort": "Int", "meaning": "the price index in November 1923"}],
            "premises": [{"id": "P1", "expr": {"op": "eq", "left": v, "right": {"op": "int", "value": "5000"}}, "label": "the price index rose to 5000",
                          "grounding": {"kind": "quotation", "source_refs": [{"document_id": "doc-1", "excerpt": "the price index rose to 5000"}]}}],
            "conclusion": {"id": "C", "expr": {"op": "gt", "left": v, "right": {"op": "int", "value": "1000"}}, "label": "it exceeded 1000"}}
    fx = {"k1": {"problem": prob, "interpretation": {"reading": "p = 5000 entails p > 1000", "glossary": [{"symbol": "p", "meaning": "the price index"}],
                                                    "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}}
    return verify_claim(claim, rep, Translator(FixtureTranslationProvider(fx)),
                        SemanticReviewer(FixtureReviewProvider({"k1": {"verdict": "faithful", "issues": []}})),
                        config=SolverConfig(), signing_key=KEY, key_id="kid")


@pytest.mark.parametrize("fields", AGENT_LABELS[:3] + AGENT_LABELS[4:6])
def test_a_relayed_report_under_any_agent_label_grounds_nothing_and_is_not_released(fields):
    o = _verify(fields["author"], fields["provenance"])
    assert o.verification.ungrounded_dependencies == ["P1"]
    assert o.release is not None and not o.release.permitted


def test_control_a_primary_source_still_grounds_the_premise_and_is_released():
    o = _verify("Reichsbank", "supplied by student")
    assert o.verification.ungrounded_dependencies == [] and o.verification.unverified_dependencies == []
    assert o.release is not None and o.release.permitted
