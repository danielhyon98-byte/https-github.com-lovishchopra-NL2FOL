"""Fixtures showing the translator serving several IB subjects, not only English.

Each :class:`SubjectFixture` is a claim, the immutable report it belongs to, the
provider output a model would have proposed (or ``None`` when the provider must
never be called), and the statuses the pipeline is expected to produce. The
fixtures exercise the subject profiles in
:mod:`epinoic_logic.translate.subjects`:

===========================  ==========================  =======================
fixture                      subject                     expected display
===========================  ==========================  =======================
``maths_entailed``           Mathematics AA              ENTAILED
``maths_unsatisfiable``      Mathematics AA              UNSATISFIABLE
``physics_entailed``         Physics                     ENTAILED
``physics_counterexample``   Physics                     COUNTEREXAMPLE
``economics_entailed``       Economics                   ENTAILED
``cs_entailed``              Computer Science            ENTAILED
``history_entailed``         History                     ENTAILED (links ungrounded)
``english_interpretation``   English A: Literature       NOT_ELIGIBLE (interpretive)
``english_quantitative``     English A: Literature       NOT_ELIGIBLE (subject policy)
===========================  ==========================  =======================

All numbers are exact strings in the IR; units are not checked in v1 and are
carried as explicit assumptions. The texts are written for these fixtures; the
History source is invented and labelled as such.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..engine.statuses import VerificationStatus
from ..translate.contracts import ClaimRecord, EligibilityClass, SpecialistReport, SuppliedText, TranslationStatus, sha256_text

__all__ = ["SubjectFixture", "FIXTURES", "by_name", "fixture_responses"]

_CREATED_AT = "2026-10-11T00:00:00Z"
_IDS = dict(request_id="req-ms", task_id="task-ms")


@dataclass(frozen=True)
class SubjectFixture:
    """One subject scenario with its expected pipeline behaviour."""

    name: str
    subject: str
    description: str
    claim: ClaimRecord
    report: SpecialistReport
    provider_output: Optional[dict[str, Any]]
    expected_translation_status: TranslationStatus
    expected_display_status: VerificationStatus
    expected_eligibility_class: EligibilityClass
    expected_route: Optional[str] = None
    expected_ungrounded: tuple[str, ...] = ()
    expected_relied_on: tuple[str, ...] = ()
    expected_reason_fragment: Optional[str] = None
    assumptions: tuple[str, ...] = field(default_factory=tuple)

    @property
    def provider_called(self) -> bool:
        """True when the pipeline is expected to ask the provider for this claim."""
        return self.provider_output is not None


def _var(name: str) -> dict[str, Any]:
    return {"op": "var", "name": name}


def _int(v: object) -> dict[str, Any]:
    return {"op": "int", "value": str(v)}


def _real(v: object) -> dict[str, Any]:
    return {"op": "real", "value": str(v)}


def _cmp(op: str, left: dict, right: dict) -> dict[str, Any]:
    return {"op": op, "left": left, "right": right}


def _fact(certainty: str = "established") -> dict[str, Any]:
    return {"kind": "arithmetic_fact", "certainty": certainty}


def _report(name: str, subject: str, agent_id: str, task_type: str, claims: list[ClaimRecord], response: str,
            supplied_texts: Optional[list[SuppliedText]] = None, assumptions: tuple[str, ...] = ()) -> SpecialistReport:
    return SpecialistReport(
        **_IDS, report_id=f"rep-{name}", agent_id=agent_id, subject=subject, task_type=task_type,
        original_response=response, response_sha256=sha256_text(response), supplied_texts=supplied_texts or [],
        claims=claims, assumptions=list(assumptions), created_at=_CREATED_AT,
    )


def _claim(name: str, subject: str, agent_id: str, task_type: str, claim_id: str, text: str, **fields: Any) -> ClaimRecord:
    return ClaimRecord(**_IDS, report_id=f"rep-{name}", agent_id=agent_id, subject=subject, task_type=task_type,
                       claim_id=claim_id, claim_text=text, **fields)


def _output(problem: dict[str, Any], reading: str, glossary: list[dict[str, str]]) -> dict[str, Any]:
    return {"problem": problem, "interpretation": {"reading": reading, "glossary": glossary, "ambiguity_flags": []},
            "ambiguous": False, "unsupported_reason": None}


def _problem(problem_id: str, claim: ClaimRecord, *, query: str, symbols: list, premises: list,
             conclusion: Optional[dict] = None, notes: Optional[str] = None) -> dict[str, Any]:
    p: dict[str, Any] = {"ir_version": "1.0", "problem_id": problem_id, "request_id": claim.request_id,
                         "claim_id": claim.claim_id, "query": query, "symbols": symbols, "premises": premises}
    if conclusion is not None:
        p["conclusion"] = conclusion
    if notes:
        p["notes"] = notes
    return p


# ------------------------------------------------------------- Mathematics


def _maths_entailed() -> SubjectFixture:
    name, subject, agent, task = "maths_entailed", "Mathematics: Analysis and Approaches", "maths-specialist", "proof_sketch"
    text = "If x > 2 and y > x, then y > 2."
    claim = _claim(name, subject, agent, task, "m1", text, claim_role="other", proposed_claim_kind="formal_logic")
    report = _report(name, subject, agent, task, [claim], f"Step 3 of the proof: {text}")
    problem = _problem(
        "ms-maths-1", claim, query="entailment",
        symbols=[{"name": "x", "sort": "Int", "meaning": "x"}, {"name": "y", "sort": "Int", "meaning": "y"}],
        premises=[
            {"id": "P1", "expr": _cmp("gt", _var("x"), _int(2)), "label": "x > 2", "grounding": _fact()},
            {"id": "P2", "expr": _cmp("gt", _var("y"), _var("x")), "label": "y > x", "grounding": _fact()},
        ],
        conclusion={"id": "C", "expr": _cmp("gt", _var("y"), _int(2)), "label": "y > 2"},
    )
    return SubjectFixture(
        name=name, subject=subject, description="transitivity of > over the integers", claim=claim, report=report,
        provider_output=_output(problem, "From x > 2 and y > x it follows that y > 2 over the integers.", [{"symbol": "x", "meaning": "x"}, {"symbol": "y", "meaning": "y"}]),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=VerificationStatus.ENTAILED,
        expected_eligibility_class=EligibilityClass.PROPOSITIONAL_ARGUMENT, expected_relied_on=("P1", "P2"),
    )


def _maths_unsatisfiable() -> SubjectFixture:
    name, subject, agent, task = "maths_unsatisfiable", "Mathematics: Analysis and Approaches", "maths-specialist", "worked_solution"
    text = "There is an integer x such that 2x = 1."
    claim = _claim(name, subject, agent, task, "m2", text, claim_role="quantitative", proposed_claim_kind="arithmetic")
    report = _report(name, subject, agent, task, [claim], f"The student asserts: {text}")
    problem = _problem(
        "ms-maths-2", claim, query="satisfiability",
        symbols=[{"name": "x", "sort": "Int", "meaning": "the integer x"}],
        premises=[{"id": "EQ", "expr": _cmp("eq", {"op": "mul", "args": [_int(2), _var("x")]}, _int(1)), "label": "2x = 1", "grounding": _fact()}],
    )
    return SubjectFixture(
        name=name, subject=subject, description="no integer solves 2x = 1", claim=claim, report=report,
        provider_output=_output(problem, "Is there an integer x with 2x = 1?", [{"symbol": "x", "meaning": "the integer x"}]),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=VerificationStatus.UNSATISFIABLE,
        expected_eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, expected_relied_on=("EQ",),
    )


# ----------------------------------------------------------------- Physics


def _physics(claim_value: str, status: VerificationStatus, suffix: str) -> SubjectFixture:
    name, subject, agent, task = f"physics_{suffix}", "Physics", "physics-specialist", "worked_solution"
    text = f"With d = 120 m and t = 8 s, the speed is v = {claim_value} m/s."
    claim = _claim(name, subject, agent, task, f"ph-{suffix}", text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                   assumptions=["units are consistent (metres, seconds) and are not checked by the engine"])
    report = _report(name, subject, agent, task, [claim], f"Using v = d / t: {text}", assumptions=("SI units throughout",))
    problem = _problem(
        f"ms-phys-{suffix}", claim, query="entailment",
        symbols=[{"name": "v", "sort": "Real", "meaning": "speed"}, {"name": "d", "sort": "Real", "meaning": "distance"}, {"name": "t", "sort": "Real", "meaning": "time"}],
        premises=[
            {"id": "D", "expr": _cmp("eq", _var("d"), _real(120)), "label": "d = 120", "grounding": _fact()},
            {"id": "T", "expr": _cmp("eq", _var("t"), _real(8)), "label": "t = 8", "grounding": _fact()},
            {"id": "DEF", "expr": _cmp("eq", _var("v"), {"op": "div", "left": _var("d"), "right": _real(8)}), "label": "v = d / t with t = 8", "grounding": _fact()},
        ],
        conclusion={"id": "C", "expr": _cmp("eq", _var("v"), _real(claim_value)), "label": f"v = {claim_value}"},
        notes="units are carried as an assumption, not checked",
    )
    glossary = [{"symbol": "v", "meaning": "speed"}, {"symbol": "d", "meaning": "distance"}, {"symbol": "t", "meaning": "time"}]
    return SubjectFixture(
        name=name, subject=subject, description=f"v = d/t with exact reals; claim v = {claim_value}", claim=claim, report=report,
        provider_output=_output(problem, f"v is defined as d / t; with d = 120 and t = 8 the claim is v = {claim_value}.", glossary),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=status,
        expected_eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM,
        expected_relied_on=("D", "DEF") if status is VerificationStatus.ENTAILED else (),
        assumptions=("units are not checked in IR v1",),
    )


# --------------------------------------------------------------- Economics


def _economics_entailed() -> SubjectFixture:
    name, subject, agent, task = "economics_entailed", "Economics", "economics-specialist", "worked_solution"
    text = "When quantity demanded falls by 10% as price rises by 20%, the price elasticity of demand is 0.5."
    claim = _claim(name, subject, agent, task, "ec1", text, claim_role="quantitative", proposed_claim_kind="arithmetic",
                   assumptions=["PED is taken as the absolute value of %dQ / %dP"])
    report = _report(name, subject, agent, task, [claim], f"PED = %dQ / %dP. {text}")
    problem = _problem(
        "ms-econ-1", claim, query="entailment",
        symbols=[{"name": "dq", "sort": "Real", "meaning": "percentage change in quantity demanded (magnitude)"},
                 {"name": "dp", "sort": "Real", "meaning": "percentage change in price (magnitude)"},
                 {"name": "ped", "sort": "Real", "meaning": "price elasticity of demand (magnitude)"}],
        premises=[
            {"id": "DQ", "expr": _cmp("eq", _var("dq"), _real(10)), "label": "quantity demanded changes by 10%", "grounding": _fact()},
            {"id": "DP", "expr": _cmp("eq", _var("dp"), _real(20)), "label": "price changes by 20%", "grounding": _fact()},
            {"id": "DEF", "expr": _cmp("eq", _var("ped"), {"op": "div", "left": _var("dq"), "right": _real(20)}), "label": "PED = %dQ / %dP with %dP = 20", "grounding": _fact()},
        ],
        conclusion={"id": "C", "expr": _cmp("eq", _var("ped"), _real("1/2")), "label": "PED = 1/2"},
    )
    glossary = [{"symbol": "dq", "meaning": "%dQ"}, {"symbol": "dp", "meaning": "%dP"}, {"symbol": "ped", "meaning": "PED"}]
    return SubjectFixture(
        name=name, subject=subject, description="price elasticity 10%/20% = 1/2 exactly", claim=claim, report=report,
        provider_output=_output(problem, "PED is the ratio of the percentage changes; 10/20 is exactly 1/2.", glossary),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=VerificationStatus.ENTAILED,
        expected_eligibility_class=EligibilityClass.QUANTITATIVE_CLAIM, expected_relied_on=("DQ", "DEF"),
    )


# -------------------------------------------------------- Computer Science


def _cs_entailed() -> SubjectFixture:
    name, subject, agent, task = "cs_entailed", "Computer Science", "cs-specialist", "boolean_simplification"
    text = "(A AND B) OR (A AND NOT B) is equivalent to A."
    claim = _claim(name, subject, agent, task, "cs1", text, claim_role="other", proposed_claim_kind="formal_logic")
    report = _report(name, subject, agent, task, [claim], f"Simplification step: {text}")
    expr = {"op": "or", "args": [{"op": "and", "args": [_var("a"), _var("b")]}, {"op": "and", "args": [_var("a"), {"op": "not", "arg": _var("b")}]}]}
    problem = _problem(
        "ms-cs-1", claim, query="entailment",
        symbols=[{"name": "a", "sort": "Bool", "meaning": "A"}, {"name": "b", "sort": "Bool", "meaning": "B"}, {"name": "e", "sort": "Bool", "meaning": "the expression (A AND B) OR (A AND NOT B)"}],
        premises=[{"id": "DEF", "expr": {"op": "iff", "left": _var("e"), "right": expr}, "label": "e is (A AND B) OR (A AND NOT B)", "grounding": {"kind": "task_setting", "certainty": "established"}}],
        conclusion={"id": "C", "expr": {"op": "iff", "left": _var("e"), "right": _var("a")}, "label": "e is equivalent to A"},
    )
    glossary = [{"symbol": "a", "meaning": "A"}, {"symbol": "b", "meaning": "B"}, {"symbol": "e", "meaning": "the given expression"}]
    return SubjectFixture(
        name=name, subject=subject, description="Boolean equivalence via iff conclusion", claim=claim, report=report,
        provider_output=_output(problem, "Equivalence is encoded as a biconditional between the defined expression and A.", glossary),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=VerificationStatus.ENTAILED,
        expected_eligibility_class=EligibilityClass.PROPOSITIONAL_ARGUMENT, expected_relied_on=("DEF",),
    )


# ----------------------------------------------------------------- History


_HISTORY_SOURCE = (
    "Minutes of the town council, first sitting of March. The council voted to close the mills until the "
    "river had been dredged. Three members recorded their dissent and left before the vote was read."
)


def _history_entailed() -> SubjectFixture:
    name, subject, agent, task = "history_entailed", "History", "history-specialist", "source_analysis"
    doc = SuppliedText(document_id="hist-src-1", title="Fixture source: council minutes (invented for tests)", text=_HISTORY_SOURCE,
                       locator_scheme="none", provenance="invented fixture; not a historical document")
    evidence = _claim(name, subject, agent, task, "h-ev1", '"The council voted to close the mills"', claim_role="evidence",
                      proposed_claim_kind="factual", materiality="supporting",
                      source_refs=[{"document_id": "hist-src-1", "excerpt": "The council voted to close the mills"}])
    link = _claim(name, subject, agent, task, "h-link", "Closing the mills shows the council put the river works before trade.",
                  claim_role="link", supporting_claim_ids=["h-ev1"], certainty="probable")
    point = _claim(name, subject, agent, task, "h-point", "The source suggests the council prioritised public works over economic activity.",
                   claim_role="point", supporting_claim_ids=["h-ev1", "h-link"], certainty="probable")
    report = _report(name, subject, agent, task, [evidence, link, point],
                     f"{point.claim_text} The minutes record that {evidence.claim_text}. {link.claim_text}", supplied_texts=[doc])
    quote = {"kind": "quotation", "source_refs": [{"document_id": "hist-src-1", "excerpt": "The council voted to close the mills"}], "certainty": "established"}
    infer = {"kind": "specialist_inference", "certainty": "probable"}
    problem = _problem(
        "ms-hist-1", point, query="entailment",
        symbols=[{"name": "q", "sort": "Bool", "meaning": "the minutes record a vote to close the mills", "grounding": quote},
                 {"name": "d", "sort": "Bool", "meaning": "the council put the river works before trade", "grounding": infer},
                 {"name": "p", "sort": "Bool", "meaning": "the council prioritised public works over economic activity", "grounding": infer}],
        premises=[
            {"id": "E1", "expr": _var("q"), "label": "the council voted to close the mills", "grounding": quote},
            {"id": "L1", "expr": {"op": "implies", "left": _var("q"), "right": _var("d")}, "label": "closing the mills shows the river works came first", "grounding": infer},
            {"id": "L2", "expr": {"op": "implies", "left": _var("d"), "right": _var("p")}, "label": "putting the river works first is prioritising public works over economic activity", "grounding": infer},
        ],
        conclusion={"id": "POINT", "expr": _var("p"), "label": point.claim_text},
    )
    glossary = [{"symbol": "q", "meaning": "the quoted vote"}, {"symbol": "d", "meaning": "river works before trade"}, {"symbol": "p", "meaning": "the point"}]
    return SubjectFixture(
        name=name, subject=subject, description="argument chain with two specialist inferences", claim=point, report=report,
        provider_output=_output(problem, "The point follows from the quoted vote through two inferential steps.", glossary),
        expected_translation_status=TranslationStatus.TRANSLATED, expected_display_status=VerificationStatus.ENTAILED,
        expected_eligibility_class=EligibilityClass.PROPOSITIONAL_ARGUMENT, expected_ungrounded=("L1", "L2"),
        expected_relied_on=("E1", "L1", "L2"),
    )


# ----------------------------------------------------------------- English


def _english_interpretation() -> SubjectFixture:
    name, subject, agent, task = "english_interpretation", "English A: Literature", "english-specialist", "analytical_paragraph"
    text = "The clinical diction distances the reader from the violence."
    claim = _claim(name, subject, agent, task, "en-interp", text, claim_role="interpretation", proposed_claim_kind="interpretive",
                   advisory_verification_eligibility=True, advisory_verification_status="verified")
    report = _report(name, subject, agent, task, [claim], text)
    return SubjectFixture(
        name=name, subject=subject, description="standalone interpretation: never a solver question", claim=claim, report=report,
        provider_output=None, expected_translation_status=TranslationStatus.NOT_ELIGIBLE,
        expected_display_status=VerificationStatus.NOT_ELIGIBLE, expected_eligibility_class=EligibilityClass.NOT_ELIGIBLE_INTERPRETIVE,
        expected_route="subject_evaluator", expected_reason_fragment="is not a solver question",
    )


def _english_quantitative() -> SubjectFixture:
    name, subject, agent, task = "english_quantitative", "English A: Literature", "english-specialist", "analytical_paragraph"
    text = "The extract's 300 words contain 12 references to honor."
    claim = _claim(name, subject, agent, task, "en-quant", text, claim_role="quantitative", proposed_claim_kind="arithmetic")
    report = _report(name, subject, agent, task, [claim], text)
    return SubjectFixture(
        name=name, subject=subject, description="quantitative claim downgraded by the literature subject profile", claim=claim, report=report,
        provider_output=None, expected_translation_status=TranslationStatus.NOT_ELIGIBLE,
        expected_display_status=VerificationStatus.NOT_ELIGIBLE, expected_eligibility_class=EligibilityClass.NOT_ELIGIBLE_OTHER,
        expected_route="unresolved", expected_reason_fragment="class QUANTITATIVE_CLAIM not allowed for subject profile english_a_literature",
    )


FIXTURES: tuple[SubjectFixture, ...] = (
    _maths_entailed(),
    _maths_unsatisfiable(),
    _physics("15", VerificationStatus.ENTAILED, "entailed"),
    _physics("16", VerificationStatus.COUNTEREXAMPLE, "counterexample"),
    _economics_entailed(),
    _cs_entailed(),
    _history_entailed(),
    _english_interpretation(),
    _english_quantitative(),
)


def by_name(name: str) -> SubjectFixture:
    """Look a fixture up by its ``name``."""
    for f in FIXTURES:
        if f.name == name:
            return f
    raise KeyError(f"no multi-subject fixture named {name!r}")


def fixture_responses(fixture: SubjectFixture) -> dict[str, dict[str, Any]]:
    """``{claim_id: provider output}`` for :class:`FixtureTranslationProvider` (empty when none is expected)."""
    if fixture.provider_output is None:
        return {}
    return {fixture.claim.claim_id: fixture.provider_output}
