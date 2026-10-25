"""Repair round 3, rerun-security-2 variant: the peer test reads a document id the way a router could write it. A supplied
text whose id is "PEER:abc", " peer:x" or "peer​:x" (a zero-width space) is a relayed agent's report as "peer:abc"
is, so it confers no authority: the premise it alone supports stays ungrounded and the result is not releasable. The
control: a primary source with an ordinary id still grounds the premise."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.sources import is_peer_text
from epinoic_logic.branches.packs import _is_peer_text
from epinoic_logic.engine.results import SolverConfig
from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText, sha256_text
from epinoic_logic.translate.grounding import is_peer_document, is_peer_id, normalized_document_id
from epinoic_logic.translate.outcome import verify_claim
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureReviewProvider, FixtureTranslationProvider
from epinoic_logic.translate.review import SemanticReviewer

KEY = b"k" * 32
TEXT = "Economics note: the price index rose to 5000 by November 1923."
FORMS = ["peer:abc", "PEER:abc", " peer:x", "Peer-x", "peer​:x", "﻿peer_x", "REPORT:r2", "ｐｅｅｒ:x"]


@pytest.mark.parametrize("doc_id", FORMS)
def test_every_spelling_of_a_peer_id_is_a_peer_id(doc_id):
    doc = SuppliedText(document_id=doc_id, author="Reichsbank", text=TEXT, provenance="supplied by student")
    assert is_peer_id(doc_id) and is_peer_document(doc) and is_peer_text(doc) and _is_peer_text(doc)


@pytest.mark.parametrize("doc_id", ["doc-src", "peerless-review", "source-peer:x", "pee:r"])
def test_an_ordinary_id_is_no_peer_id(doc_id):
    assert not is_peer_id(doc_id)
    assert normalized_document_id(" A​B ") == "ab"


def _verify(doc_id: str):
    sup = [SuppliedText(document_id=doc_id, author="Reichsbank", text=TEXT, provenance="supplied by student")]
    text = "The price index rose to 5000, so it exceeded 1000."
    ids = dict(request_id="r", task_id="t", report_id="rep")
    claim = ClaimRecord(**ids, agent_id="generic-structured", subject="History", task_type="essay", claim_id="k1", claim_text=text,
                        claim_role="quantitative", proposed_claim_kind="arithmetic",
                        source_refs=[{"document_id": doc_id, "excerpt": "the price index rose to 5000"}])
    rep = SpecialistReport(**ids, agent_id="generic-structured", subject="History", task_type="essay", original_response=text,
                           response_sha256=sha256_text(text), claims=[claim], supplied_texts=sup, created_at="2026-10-11T00:00:00Z")
    v = {"op": "var", "name": "p"}
    prob = {"problem_id": "k1-p", "request_id": "r", "claim_id": "k1", "query": "entailment",
            "symbols": [{"name": "p", "sort": "Int", "meaning": "the price index in November 1923"}],
            "premises": [{"id": "P1", "expr": {"op": "eq", "left": v, "right": {"op": "int", "value": "5000"}}, "label": "the price index rose to 5000",
                          "grounding": {"kind": "quotation", "source_refs": [{"document_id": doc_id, "excerpt": "the price index rose to 5000"}]}}],
            "conclusion": {"id": "C", "expr": {"op": "gt", "left": v, "right": {"op": "int", "value": "1000"}}, "label": "it exceeded 1000"}}
    fx = {"k1": {"problem": prob, "interpretation": {"reading": "p = 5000 entails p > 1000", "glossary": [{"symbol": "p", "meaning": "the price index"}],
                                                    "ambiguity_flags": []}, "ambiguous": False, "unsupported_reason": None}}
    return verify_claim(claim, rep, Translator(FixtureTranslationProvider(fx)),
                        SemanticReviewer(FixtureReviewProvider({"k1": {"verdict": "faithful", "issues": []}})),
                        config=SolverConfig(), signing_key=KEY, key_id="kid")


@pytest.mark.parametrize("doc_id", ["PEER:abc", " peer:x", "peer​:x"])
def test_a_peer_report_under_any_spelling_grounds_nothing(doc_id):
    o = _verify(doc_id)
    assert o.verification.ungrounded_dependencies == ["P1"]
    assert o.release is not None and not o.release.permitted


def test_a_primary_source_still_grounds_the_premise():
    o = _verify("doc-src")
    assert o.verification.ungrounded_dependencies == [] and o.verification.unverified_dependencies == []
