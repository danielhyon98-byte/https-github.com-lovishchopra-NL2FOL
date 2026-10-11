"""Fixtures built from Example 1 of the English specialist's knowledge documents.

Two kinds of material live here:

* the exact Example 1 texts (re-exported from :mod:`example1_texts`), a corrupted
  variant of body paragraph 1 with an invented quotation, and helpers that run the
  adapter over them to produce a :class:`SpecialistReport`;
* provider outputs for :class:`~epinoic_logic.translate.providers.FixtureTranslationProvider`
  that encode the body-1 point in the restricted IR in deliberately different ways:

  ``FAITHFUL_CHAIN``          quotations -> inferential links -> point; ENTAILED with the
                              links reported as ungrounded dependencies.
  ``HALLUCINATED_QUOTATION``  the same chain with one excerpt that is not in the extract;
                              still ENTAILED, but the grounding check fails and the
                              evidence premise joins the ungrounded dependencies.
  ``CONTRADICTION``           two 'established' supplied-text premises, X and not X;
                              INCONSISTENT_PREMISES naming both.
  ``NON_SEQUITUR``            evidence with no link to the point; COUNTEREXAMPLE.
  ``STRUCTURAL_ARITH``        word count and strand count as Int constraints; ENTAILED.

Every fixture is data that travels through exactly the same untrusted path as a
model's output: strict JSON parsing, schema validation, engine validation,
grounding checks, the engine. Nothing here is evaluated.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from ...engine.statuses import VerificationStatus
from ...translate.contracts import ClaimRecord, SpecialistReport, SuppliedText
from . import parser
from .example1_texts import (  # noqa: F401  (re-exported fixture texts)
    EXAMPLE1_BODY_1,
    EXAMPLE1_BODY_2,
    EXAMPLE1_BODY_3,
    EXAMPLE1_CONCLUSION,
    EXAMPLE1_ESSAY,
    EXAMPLE1_PROMPT,
    EXAMPLE1_SOURCE_EXTRACT,
    EXAMPLE1_THESIS,
    EXAMPLE1_TITLE,
)

__all__ = [
    "REQUEST_ID", "TASK_ID", "REPORT_ID", "DOCUMENT_ID", "TASK_TYPE", "POINT_CLAIM_ID", "STRUCTURAL_CLAIM_ID",
    "EXAMPLE1_TITLE", "EXAMPLE1_PROMPT", "EXAMPLE1_SOURCE_EXTRACT", "EXAMPLE1_THESIS", "EXAMPLE1_BODY_1",
    "EXAMPLE1_BODY_2", "EXAMPLE1_BODY_3", "EXAMPLE1_CONCLUSION", "EXAMPLE1_ESSAY",
    "EXAMPLE1_BODY_1_HALLUCINATED", "HALLUCINATED_EXCERPT", "JOINED_QUOTATION",
    "QUOTE_THESIS", "QUOTE_OPENLY", "QUOTE_INNOCENT", "BODY_1_WORDS",
    "example1_supplied_text", "example1_report", "point_claim", "with_structural_claim",
    "faithful_chain", "hallucinated_quotation", "contradiction", "non_sequitur", "structural_arith",
    "FAITHFUL_CHAIN", "HALLUCINATED_QUOTATION", "CONTRADICTION", "NON_SEQUITUR", "STRUCTURAL_ARITH",
    "FIXTURE_BUILDERS", "EXPECTED_STATUS", "fixture_responses",
]

REQUEST_ID = "req-ex1"
TASK_ID = "task-ex1"
REPORT_ID = "rep-ex1"
DOCUMENT_ID = "ex1-extract"
TASK_TYPE = "analytical_paragraph"
POINT_CLAIM_ID = "p1-point"
STRUCTURAL_CLAIM_ID = "p1-structural"

#: Quotations of the extract used by the fixtures (all occur verbatim in EXAMPLE1_SOURCE_EXTRACT).
QUOTE_THESIS = "thesis of homicide in legitimate defense of honor"
QUOTE_OPENLY = "We killed him openly"
QUOTE_INNOCENT = "but we're innocent"
#: Body 1 quotes this as one span although the extract has a speech tag between the halves (S12).
JOINED_QUOTATION = "We killed him openly, but we're innocent."
#: Not in the extract.
HALLUCINATED_EXCERPT = "We killed him in secret"
EXAMPLE1_BODY_1_HALLUCINATED = EXAMPLE1_BODY_1.replace(f'"{JOINED_QUOTATION}"', f'"{HALLUCINATED_EXCERPT}, and we are guilty."')
assert EXAMPLE1_BODY_1_HALLUCINATED != EXAMPLE1_BODY_1
BODY_1_WORDS = len(EXAMPLE1_BODY_1.split())

STRUCTURAL_CLAIM_TEXT = "The paragraph develops two strands of analysis within 400 words."


# ----------------------------------------------------------------- reports


def example1_supplied_text(document_id: str = DOCUMENT_ID) -> SuppliedText:
    """The Example 1 extract as a supplied text without a locator scheme."""
    return SuppliedText(
        document_id=document_id, title=EXAMPLE1_TITLE, author="Gabriel García Márquez",
        text=EXAMPLE1_SOURCE_EXTRACT, locator_scheme="none", provenance="supplied with the task (fixture)",
    )


def example1_report(
    text: str = EXAMPLE1_BODY_1,
    *,
    request_id: str = REQUEST_ID,
    task_id: str = TASK_ID,
    report_id: str = REPORT_ID,
    supplied_texts: Optional[list[SuppliedText]] = None,
    task_type: str = TASK_TYPE,
) -> SpecialistReport:
    """Run the English specialist parser over ``text`` with the extract supplied."""
    return parser.parse_response(
        text, request_id=request_id, task_id=task_id, report_id=report_id, subject=parser.DEFAULT_SUBJECT,
        task_type=task_type, supplied_texts=supplied_texts if supplied_texts is not None else [example1_supplied_text()],
        course_level="HL", agent_version="1.0",
    )


def point_claim(report: SpecialistReport, claim_id: str = POINT_CLAIM_ID) -> ClaimRecord:
    """The point claim of body 1 in a parsed report."""
    for claim in report.claims:
        if claim.claim_id == claim_id:
            return claim
    raise KeyError(f"claim {claim_id!r} not in report")


def with_structural_claim(report: SpecialistReport, claim_id: str = STRUCTURAL_CLAIM_ID) -> tuple[SpecialistReport, ClaimRecord]:
    """Return a copy of ``report`` with a ``structural`` role claim appended, and that claim.

    The structural claim is the kind of self-report a specialist might make about
    its own paragraph; it is eligible as an ARITHMETIC_CONSTRAINT.
    """
    base = report.claims[0]
    claim = ClaimRecord(
        request_id=base.request_id, task_id=base.task_id, report_id=base.report_id, agent_id=base.agent_id,
        agent_version=base.agent_version, subject=base.subject, course_level=base.course_level, task_type=base.task_type,
        claim_id=claim_id, claim_text=STRUCTURAL_CLAIM_TEXT, claim_role="structural", proposed_claim_kind="arithmetic",
        materiality="supporting", certainty="established",
    )
    updated = report.model_copy(update={"claims": [*report.claims, claim]})
    return SpecialistReport.model_validate(updated.model_dump(mode="json")), claim


# ------------------------------------------------------------ IR builders


def _var(name: str) -> dict[str, Any]:
    return {"op": "var", "name": name}


def _int(value: int) -> dict[str, Any]:
    return {"op": "int", "value": str(value)}


def _quote(document_id: str, *excerpts: str, certainty: str = "established") -> dict[str, Any]:
    return {
        "kind": "quotation",
        "source_refs": [{"document_id": document_id, "excerpt": e} for e in excerpts],
        "certainty": certainty,
    }


def _infer(certainty: str = "probable", note: Optional[str] = None) -> dict[str, Any]:
    g: dict[str, Any] = {"kind": "specialist_inference", "certainty": certainty}
    if note:
        g["note"] = note
    return g


def _problem(problem_id: str, request_id: str, claim_id: str, *, query: str, symbols: list, premises: list,
             conclusion: Optional[dict] = None, notes: Optional[str] = None) -> dict[str, Any]:
    p: dict[str, Any] = {
        "ir_version": "1.0", "problem_id": problem_id, "request_id": request_id, "claim_id": claim_id,
        "query": query, "symbols": symbols, "premises": premises,
    }
    if conclusion is not None:
        p["conclusion"] = conclusion
    if notes:
        p["notes"] = notes
    return p


def _output(problem: Optional[dict], reading: str, glossary: list[dict], *, ambiguous: bool = False,
            unsupported_reason: Optional[str] = None) -> dict[str, Any]:
    return {
        "problem": problem,
        "interpretation": {"reading": reading, "glossary": glossary, "ambiguity_flags": []},
        "ambiguous": ambiguous,
        "unsupported_reason": unsupported_reason,
    }


_POINT_LABEL = (
    "the administration of justice is presented as morally compromised: the rhetoric of honor "
    "turns homicide into socially sanctioned duty"
)
_SYMBOLS_CHAIN = [
    {"name": "q1", "sort": "Bool", "meaning": "the extract calls the killing a thesis of homicide in legitimate defense of honor"},
    {"name": "q2", "sort": "Bool", "meaning": "the twins admit the killing and in the same breath call themselves innocent"},
    {"name": "d1", "sort": "Bool", "meaning": "the legal diction sanitizes the brutality of the crime"},
    {"name": "d2", "sort": "Bool", "meaning": "the paradox severs physical responsibility from moral guilt"},
    {"name": "p", "sort": "Bool", "meaning": _POINT_LABEL},
]
_GLOSSARY_CHAIN = [{"symbol": s["name"], "meaning": s["meaning"]} for s in _SYMBOLS_CHAIN]


def _evidence_premises(document_id: str, second_excerpts: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {"id": "E1", "expr": _var("q1"), "label": f'the lawyer\'s "{QUOTE_THESIS}"', "grounding": _quote(document_id, QUOTE_THESIS)},
        {"id": "E2", "expr": _var("q2"), "label": "the twins' declaration of open killing and innocence", "grounding": _quote(document_id, *second_excerpts)},
    ]


def _link_premises() -> list[dict[str, Any]]:
    return [
        {"id": "L1", "expr": {"op": "implies", "left": _var("q1"), "right": _var("d1")}, "label": "legal diction that calls homicide legitimate sanitizes the brutality", "grounding": _infer()},
        {"id": "L2", "expr": {"op": "implies", "left": _var("q2"), "right": _var("d2")}, "label": "admitting the killing while claiming innocence severs responsibility from guilt", "grounding": _infer()},
        {"id": "L3", "expr": {"op": "implies", "left": {"op": "and", "args": [_var("d1"), _var("d2")]}, "right": _var("p")}, "label": "sanitized brutality and severed guilt together present justice as morally compromised", "grounding": _infer()},
    ]


def _point_conclusion() -> dict[str, Any]:
    return {"id": "POINT", "expr": _var("p"), "label": _POINT_LABEL}


def faithful_chain(request_id: str = REQUEST_ID, claim_id: str = POINT_CLAIM_ID, document_id: str = DOCUMENT_ID) -> dict[str, Any]:
    """Quotations -> inferences -> point. Expected: ENTAILED, ungrounded L1, L2, L3."""
    problem = _problem(
        "ex1-faithful", request_id, claim_id, query="entailment", symbols=_SYMBOLS_CHAIN,
        premises=_evidence_premises(document_id, (QUOTE_OPENLY, QUOTE_INNOCENT)) + _link_premises(),
        conclusion=_point_conclusion(),
        notes="Each inferential step is the specialist's reading and is recorded as a specialist_inference, not as a fact of the text.",
    )
    return _output(problem, "The point is read as following from two quotations through three inferential steps.", _GLOSSARY_CHAIN)


def hallucinated_quotation(request_id: str = REQUEST_ID, claim_id: str = POINT_CLAIM_ID, document_id: str = DOCUMENT_ID) -> dict[str, Any]:
    """As ``faithful_chain`` but E2 cites words that are not in the extract. Expected: ENTAILED with E2 ungrounded."""
    problem = _problem(
        "ex1-hallucinated", request_id, claim_id, query="entailment", symbols=_SYMBOLS_CHAIN,
        premises=_evidence_premises(document_id, (HALLUCINATED_EXCERPT,)) + _link_premises(),
        conclusion=_point_conclusion(),
    )
    return _output(problem, "The point is read as following from two quotations through three inferential steps.", _GLOSSARY_CHAIN)


def contradiction(request_id: str = REQUEST_ID, claim_id: str = POINT_CLAIM_ID, document_id: str = DOCUMENT_ID) -> dict[str, Any]:
    """Two established supplied-text premises, s and not s. Expected: INCONSISTENT_PREMISES with core S1, S2."""
    symbols = _SYMBOLS_CHAIN + [{"name": "s", "sort": "Bool", "meaning": "the priest recalled the surrender as an act of great dignity"}]
    supplied = {"kind": "supplied_text", "source_refs": [{"document_id": document_id}], "certainty": "established"}
    premises = _evidence_premises(document_id, (QUOTE_OPENLY, QUOTE_INNOCENT)) + _link_premises() + [
        {"id": "S1", "expr": _var("s"), "label": "the priest recalled the surrender as an act of great dignity", "grounding": supplied},
        {"id": "S2", "expr": {"op": "not", "arg": _var("s")}, "label": "the priest recalled the surrender as shameful", "grounding": supplied},
    ]
    problem = _problem("ex1-contradiction", request_id, claim_id, query="entailment", symbols=symbols, premises=premises, conclusion=_point_conclusion())
    return _output(problem, "The report asserts both that the priest saw dignity in the surrender and that he saw shame.", _GLOSSARY_CHAIN + [{"symbol": "s", "meaning": symbols[-1]["meaning"]}])


def non_sequitur(request_id: str = REQUEST_ID, claim_id: str = POINT_CLAIM_ID, document_id: str = DOCUMENT_ID) -> dict[str, Any]:
    """Evidence only, no link to the point. Expected: COUNTEREXAMPLE."""
    problem = _problem(
        "ex1-nonsequitur", request_id, claim_id, query="entailment", symbols=_SYMBOLS_CHAIN,
        premises=_evidence_premises(document_id, (QUOTE_OPENLY, QUOTE_INNOCENT)),
        conclusion=_point_conclusion(),
    )
    return _output(problem, "The point is asserted after the quotations with no inferential step connecting them.", _GLOSSARY_CHAIN)


def structural_arith(
    request_id: str = REQUEST_ID,
    claim_id: str = STRUCTURAL_CLAIM_ID,
    *,
    words: Optional[int] = None,
    strands: int = 2,
    max_words: int = 400,
    min_strands: int = 2,
) -> dict[str, Any]:
    """Word and strand counts as Int facts; conclusion words <= max and strands >= min (task_setting)."""
    n = BODY_1_WORDS if words is None else words
    problem = _problem(
        "ex1-structural", request_id, claim_id, query="entailment",
        symbols=[
            {"name": "words", "sort": "Int", "meaning": "whitespace-token word count of the paragraph"},
            {"name": "strands", "sort": "Int", "meaning": "number of analytical strands the paragraph develops"},
        ],
        premises=[
            {"id": "WORDS", "expr": {"op": "eq", "left": _var("words"), "right": _int(n)}, "label": f"the paragraph has {n} words", "grounding": {"kind": "arithmetic_fact", "certainty": "established"}},
            {"id": "STRANDS", "expr": {"op": "eq", "left": _var("strands"), "right": _int(strands)}, "label": f"the paragraph develops {strands} strands", "grounding": _infer("probable", "strand count is the specialist's structural reading")},
        ],
        conclusion={
            "id": "LIMITS",
            "expr": {"op": "and", "args": [
                {"op": "le", "left": _var("words"), "right": _int(max_words)},
                {"op": "ge", "left": _var("strands"), "right": _int(min_strands)},
            ]},
            "label": f"at most {max_words} words and at least {min_strands} strands",
            "grounding": {"kind": "task_setting", "certainty": "established"},
        },
    )
    glossary = [{"symbol": "words", "meaning": "word count"}, {"symbol": "strands", "meaning": "strand count"}]
    return _output(problem, "The structural claim is read as: given the counted words and strands, the task limits are met.", glossary)


FAITHFUL_CHAIN: dict[str, Any] = faithful_chain()
HALLUCINATED_QUOTATION: dict[str, Any] = hallucinated_quotation()
CONTRADICTION: dict[str, Any] = contradiction()
NON_SEQUITUR: dict[str, Any] = non_sequitur()
STRUCTURAL_ARITH: dict[str, Any] = structural_arith()

FIXTURE_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "FAITHFUL_CHAIN": faithful_chain,
    "HALLUCINATED_QUOTATION": hallucinated_quotation,
    "CONTRADICTION": contradiction,
    "NON_SEQUITUR": non_sequitur,
    "STRUCTURAL_ARITH": structural_arith,
}

EXPECTED_STATUS: dict[str, VerificationStatus] = {
    "FAITHFUL_CHAIN": VerificationStatus.ENTAILED,
    "HALLUCINATED_QUOTATION": VerificationStatus.ENTAILED,
    "CONTRADICTION": VerificationStatus.INCONSISTENT_PREMISES,
    "NON_SEQUITUR": VerificationStatus.COUNTEREXAMPLE,
    "STRUCTURAL_ARITH": VerificationStatus.ENTAILED,
}


def fixture_responses(name: str, claim: ClaimRecord, document_id: str = DOCUMENT_ID) -> dict[str, dict[str, Any]]:
    """``{claim_id: provider output}`` for :class:`FixtureTranslationProvider`, re-keyed to ``claim``."""
    builder = FIXTURE_BUILDERS[name]
    if name == "STRUCTURAL_ARITH":
        return {claim.claim_id: builder(claim.request_id, claim.claim_id)}
    return {claim.claim_id: builder(claim.request_id, claim.claim_id, document_id)}
