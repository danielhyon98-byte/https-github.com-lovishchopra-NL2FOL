"""Shared builders for translation-layer tests. No network, no model calls."""
from __future__ import annotations

import hashlib
from typing import Any, Optional

import pytest

from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, SuppliedText

DOC_ID = "doc-1"
TEXT = (
    "The lamp stays unlit in the hall. She does not look up; the clock ticks on.\n"
    'Outside, the yard is "a measured dose of grey" and nothing moves.'
)
IDS: dict[str, str] = dict(
    request_id="req-1",
    task_id="task-1",
    report_id="rep-1",
    agent_id="english-specialist",
    subject="English A: Literature",
    task_type="analytical_paragraph",
)


def V(name: str) -> dict[str, Any]:
    return {"op": "var", "name": name}


def I(value: object) -> dict[str, Any]:
    return {"op": "int", "value": str(value)}


def R(value: object) -> dict[str, Any]:
    return {"op": "real", "value": str(value)}


def cmp(op: str, left: dict, right: dict) -> dict[str, Any]:
    return {"op": op, "left": left, "right": right}


def make_claim(
    claim_id: str = "c-point",
    claim_text: str = "The setting conveys neglect.",
    claim_role: str = "point",
    **overrides: Any,
) -> ClaimRecord:
    data: dict[str, Any] = {**IDS, "claim_id": claim_id, "claim_text": claim_text, "claim_role": claim_role}
    data.update(overrides)
    return ClaimRecord(**data)


def make_report(
    claims: list[ClaimRecord],
    supplied_texts: Optional[list[SuppliedText]] = None,
    original_response: str = "Specialist paragraph text (immutable).",
    **overrides: Any,
) -> SpecialistReport:
    if supplied_texts is None:
        supplied_texts = [SuppliedText(document_id=DOC_ID, text=TEXT, locator_scheme="none")]
    data: dict[str, Any] = {
        **IDS,
        "original_response": original_response,
        "response_sha256": hashlib.sha256(original_response.encode("utf-8")).hexdigest(),
        "supplied_texts": supplied_texts,
        "claims": claims,
        "created_at": "2026-10-11T00:00:00Z",
    }
    data.update(overrides)
    return SpecialistReport(**data)


QUOTE = {"kind": "quotation", "source_refs": [{"document_id": DOC_ID, "excerpt": "The lamp stays unlit"}], "certainty": "established"}
INFER = {"kind": "specialist_inference", "certainty": "probable"}


def chain_problem(
    request_id: str = "req-1",
    claim_id: str = "c-point",
    *,
    excerpt: str = "The lamp stays unlit",
    document_id: str = DOC_ID,
    with_l2: bool = True,
    problem_id: str = "p-chain",
    extra_symbols: Optional[list[dict]] = None,
    extra_premises: Optional[list[dict]] = None,
) -> dict[str, Any]:
    """q (quotation) ; q -> d ; d -> p (specialist inferences) |= p."""
    quote = {"kind": "quotation", "source_refs": [{"document_id": document_id, "excerpt": excerpt}], "certainty": "established"}
    premises = [
        {"id": "E1", "expr": V("q"), "label": "the lamp stays unlit", "grounding": quote},
        {"id": "L1", "expr": {"op": "implies", "left": V("q"), "right": V("d")}, "label": "an unlit lamp presents the room as abandoned", "grounding": INFER},
    ]
    if with_l2:
        premises.append({"id": "L2", "expr": {"op": "implies", "left": V("d"), "right": V("p")}, "label": "an abandoned room conveys neglect", "grounding": INFER})
    premises += extra_premises or []
    return {
        "ir_version": "1.0",
        "problem_id": problem_id,
        "request_id": request_id,
        "claim_id": claim_id,
        "query": "entailment",
        "symbols": [
            {"name": "q", "sort": "Bool", "meaning": "the text says the lamp is unlit", "grounding": quote},
            {"name": "d", "sort": "Bool", "meaning": "the room is presented as abandoned", "grounding": INFER},
            {"name": "p", "sort": "Bool", "meaning": "the setting conveys neglect", "grounding": INFER},
            *(extra_symbols or []),
        ],
        "premises": premises,
        "conclusion": {"id": "POINT", "expr": V("p"), "label": "the setting conveys neglect"},
    }


def physics_problem(request_id: str = "req-1", claim_id: str = "c-v") -> dict[str, Any]:
    """d = 120, t = 8, v = d / 8 |= v = 15 over exact Reals."""
    fact = {"kind": "arithmetic_fact", "certainty": "established"}
    return {
        "ir_version": "1.0",
        "problem_id": "p-phys",
        "request_id": request_id,
        "claim_id": claim_id,
        "query": "entailment",
        "symbols": [{"name": "v", "sort": "Real"}, {"name": "d", "sort": "Real"}, {"name": "t", "sort": "Real"}],
        "premises": [
            {"id": "D", "expr": cmp("eq", V("d"), R(120)), "label": "distance 120", "grounding": fact},
            {"id": "T", "expr": cmp("eq", V("t"), R(8)), "label": "time 8", "grounding": fact},
            {"id": "DEF", "expr": cmp("eq", V("v"), {"op": "div", "left": V("d"), "right": R(8)}), "label": "v = d / t with t = 8", "grounding": fact},
        ],
        "conclusion": {"id": "C", "expr": cmp("eq", V("v"), R(15)), "label": "v = 15"},
    }


def provider_output(
    problem: Optional[dict],
    *,
    ambiguous: bool = False,
    flags: Optional[list[dict]] = None,
    reading: str = "The point is read as following from one quotation through two inferential steps.",
    unsupported_reason: Optional[str] = None,
    glossary: Optional[list[dict]] = None,
) -> dict[str, Any]:
    return {
        "problem": problem,
        "interpretation": {
            "reading": reading,
            "glossary": glossary if glossary is not None else [{"symbol": "q", "meaning": "the text says the lamp is unlit"}],
            "ambiguity_flags": flags or [],
        },
        "ambiguous": ambiguous,
        "unsupported_reason": unsupported_reason,
    }


@pytest.fixture
def english_claims() -> dict[str, ClaimRecord]:
    evidence = make_claim("c-ev", '"The lamp stays unlit"', "evidence", source_refs=[{"document_id": DOC_ID, "excerpt": "The lamp stays unlit"}])
    link = make_claim("c-link", "Thus the room is presented as abandoned.", "link", supporting_claim_ids=["c-ev"], certainty="probable")
    point = make_claim("c-point", "The setting conveys neglect.", "point", supporting_claim_ids=["c-ev", "c-link"], advisory_verification_eligibility=True)
    interp = make_claim("c-interp", "The diction is clinical and distancing.", "interpretation")
    quant = make_claim("c-quant", "The paragraph runs to 320 words, under the 350-word guide.", "quantitative")
    structural = make_claim("c-struct", "The paragraph develops two strands of analysis.", "structural")
    return {c.claim_id: c for c in (evidence, link, point, interp, quant, structural)}


@pytest.fixture
def english_report(english_claims: dict[str, ClaimRecord]) -> SpecialistReport:
    return make_report(list(english_claims.values()))
