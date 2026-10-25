"""Restricted typed intermediate representation (IR), version 1.0.

Design rules (from the Epinoic AI architecture and kickoff documents):
- Closed operator allowlist. Anything not listed here is UNSUPPORTED, never compiled.
- Three sorts only: Bool, Int, Real. No implicit coercion; ``to_real`` is explicit.
- Numeric constants are STRINGS so that exact integers and rationals survive JSON
  without floating-point conversion ("1/3", "-7", "0.25").
- No quantifiers, arrays, strings, bit-vectors or uninterpreted functions in v1.
- Every symbol and premise may carry ``Grounding`` metadata: where the claim came
  from and how certain the specialist was. The engine never interprets grounding
  semantically; it only reports which grounded/ungrounded premises a result relied on.
- The IR is DATA. It is never executed. The compiler (separate module) maps allowed
  nodes to Z3 API calls one by one.
"""
from __future__ import annotations

import re
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Sort = Literal["Bool", "Int", "Real"]
QueryKind = Literal["entailment", "consistency", "satisfiability"]
GroundingKind = Literal[
    "quotation",            # verbatim span of a supplied text
    "supplied_text",        # paraphrase or structural fact about a supplied text
    "task_setting",         # word counts, prompt constraints, task parameters
    "rubric_rule",          # an assessment-criterion rule supplied with the task
    "arithmetic_fact",      # a figure the task (or a supplied text) states, or one computed from such figures
    "specialist_inference", # an inferential step asserted by the specialist agent
    "assumption",           # an explicit assumption with no textual support
    "knowledge_document",   # a fact held in the specialist's own knowledge documents (source boundary (a))
    "library_source",       # a fact retrieved from the approved library, cited by title and locator (source boundary (b))
    "general_knowledge",    # subject knowledge stated from memory at a labelled certainty (a date or figure from memory included); never a quotation
]
Certainty = Literal["established", "probable", "possible"]

#: The documented patterns of identifiers, assertion ids and numeric literals. They are always applied with
#: ``fullmatch``: with ``match`` a trailing ``$`` also matches before a final newline, so ``"x\n"`` would be a symbol
#: distinct from ``"x"`` and ``"P\n"`` an assertion id that impersonates ``"P"``. The whole text must match.
IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
ASSERTION_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
INT_RE = re.compile(r"^-?(0|[1-9][0-9]*)$")
RATIONAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)/([1-9][0-9]*)$")
DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)\.[0-9]+$")


class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Var(_Node):
    op: Literal["var"]
    name: str

    @field_validator("name")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not IDENT_RE.fullmatch(v):
            raise ValueError(f"invalid identifier {v!r}: must match {IDENT_RE.pattern}")
        return v


class BoolConst(_Node):
    op: Literal["bool"]
    value: bool


class IntConst(_Node):
    op: Literal["int"]
    value: str  # exact decimal integer as text

    @field_validator("value")
    @classmethod
    def _int(cls, v: str) -> str:
        if not INT_RE.fullmatch(v):
            raise ValueError(f"invalid integer literal {v!r}")
        return v


class RealConst(_Node):
    op: Literal["real"]
    value: str  # exact rational: "3", "-7/2", "0.25"

    @field_validator("value")
    @classmethod
    def _real(cls, v: str) -> str:
        if not (INT_RE.fullmatch(v) or RATIONAL_RE.fullmatch(v) or DECIMAL_RE.fullmatch(v)):
            raise ValueError(f"invalid real literal {v!r}: use integer, fraction a/b or decimal text")
        return v


class Not(_Node):
    op: Literal["not"]
    arg: "Expr"


class And(_Node):
    op: Literal["and"]
    args: list["Expr"] = Field(min_length=2)


class Or(_Node):
    op: Literal["or"]
    args: list["Expr"] = Field(min_length=2)


class Implies(_Node):
    op: Literal["implies"]
    left: "Expr"
    right: "Expr"


class Iff(_Node):
    op: Literal["iff"]
    left: "Expr"
    right: "Expr"


class Ite(_Node):
    op: Literal["ite"]
    cond: "Expr"
    then: "Expr"
    otherwise: "Expr"


class Add(_Node):
    op: Literal["add"]
    args: list["Expr"] = Field(min_length=2)


class Mul(_Node):
    op: Literal["mul"]
    args: list["Expr"] = Field(min_length=2)


class Sub(_Node):
    op: Literal["sub"]
    left: "Expr"
    right: "Expr"


class Neg(_Node):
    op: Literal["neg"]
    arg: "Expr"


class Div(_Node):
    """Real division. Policy v1 requires the divisor to be a non-zero constant."""
    op: Literal["div"]
    left: "Expr"
    right: "Expr"


class IntDiv(_Node):
    """Integer division with Z3 semantics. Policy v1 requires a non-zero integer constant divisor."""
    op: Literal["idiv"]
    left: "Expr"
    right: "Expr"


class Mod(_Node):
    """Integer modulus with Z3 semantics (non-negative result for positive divisor).
    Policy v1 requires a non-zero integer constant divisor."""
    op: Literal["mod"]
    left: "Expr"
    right: "Expr"


class ToReal(_Node):
    op: Literal["to_real"]
    arg: "Expr"


class Compare(_Node):
    """Arithmetic comparison. Both sides must have the same numeric sort (Int or Real).
    Boolean equivalence is expressed with ``iff``, not ``eq``."""
    op: Literal["eq", "ne", "lt", "le", "gt", "ge"]
    left: "Expr"
    right: "Expr"


Expr = Annotated[
    Union[
        Var, BoolConst, IntConst, RealConst, Not, And, Or, Implies, Iff, Ite,
        Add, Sub, Mul, Neg, Div, IntDiv, Mod, ToReal, Compare,
    ],
    Field(discriminator="op"),
]

ALLOWED_OPS: frozenset[str] = frozenset({
    "var", "bool", "int", "real", "not", "and", "or", "implies", "iff", "ite",
    "add", "sub", "mul", "neg", "div", "idiv", "mod", "to_real",
    "eq", "ne", "lt", "le", "gt", "ge",
})

for _m in (Not, And, Or, Implies, Iff, Ite, Add, Mul, Sub, Neg, Div, IntDiv, Mod, ToReal, Compare):
    _m.model_rebuild()


class SourceRef(BaseModel):
    """Stable reference into a supplied document. ``locator`` is scheme-specific
    (e.g. "para:3", "line:12-14", "page:7"). Never invented by the engine."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    document_id: str = Field(min_length=1, max_length=200)
    locator: Optional[str] = Field(default=None, max_length=200)
    excerpt: Optional[str] = Field(default=None, max_length=2000)


class Grounding(BaseModel):
    """Where a symbol or premise comes from and how certain it is.

    ``verified`` is set ONLY by deterministic grounding checks (e.g. verbatim
    quotation match against the supplied text). ``None`` means not checked.
    The engine reports grounding; it never judges it.
    """
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: GroundingKind
    source_refs: list[SourceRef] = Field(default_factory=list, max_length=16)
    certainty: Certainty = "established"
    verified: Optional[bool] = None
    note: Optional[str] = Field(default=None, max_length=1000)


class Symbol(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    sort: Sort
    meaning: Optional[str] = Field(default=None, max_length=1000, description="natural-language gloss; not compiled")
    grounding: Optional[Grounding] = None

    @field_validator("name")
    @classmethod
    def _ident(cls, v: str) -> str:
        if not IDENT_RE.fullmatch(v):
            raise ValueError(f"invalid symbol name {v!r}")
        return v


class Assertion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    expr: Expr
    label: Optional[str] = Field(default=None, max_length=1000, description="natural-language statement; not compiled")
    grounding: Optional[Grounding] = None
    materiality: Literal["material", "supporting"] = "material"

    @field_validator("id")
    @classmethod
    def _aid(cls, v: str) -> str:
        if not ASSERTION_ID_RE.fullmatch(v):
            raise ValueError(f"invalid assertion id {v!r}")
        return v


class Limits(BaseModel):
    """Resource and shape limits enforced by the validator BEFORE compilation."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_symbols: int = 64
    max_premises: int = 128
    max_nodes: int = 2000
    max_depth: int = 40
    max_nary_args: int = 32
    max_const_digits: int = 40
    allow_nonlinear: bool = False      # products of two non-constant terms
    allow_real_division: bool = True   # with constant non-zero divisor only
    allow_int_division: bool = True    # with constant non-zero divisor only


DEFAULT_LIMITS = Limits()


class Problem(BaseModel):
    """A complete verification problem. This is the exact representation a result
    is bound to; any change produces a different digest and invalidates prior results."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    ir_version: Literal["1.0"] = "1.0"
    problem_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    claim_id: str = Field(min_length=1, max_length=128)
    query: QueryKind
    symbols: list[Symbol] = Field(default_factory=list)
    premises: list[Assertion] = Field(default_factory=list)
    conclusion: Optional[Assertion] = None
    notes: Optional[str] = Field(default=None, max_length=4000, description="translator interpretation notes; not compiled")

    @model_validator(mode="after")
    def _shape(self) -> "Problem":
        if self.query == "entailment" and self.conclusion is None:
            raise ValueError("entailment query requires a conclusion")
        if self.query != "entailment" and self.conclusion is not None:
            raise ValueError(f"{self.query} query must not carry a conclusion")
        names = [s.name for s in self.symbols]
        if len(names) != len(set(names)):
            raise ValueError("duplicate symbol names")
        ids = [p.id for p in self.premises] + ([self.conclusion.id] if self.conclusion else [])
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate assertion ids")
        return self
