"""Named pack policies: the only way an integrity pack chooses the engine's ``Limits``.

A pack's formal check names a policy, ``"linear"`` or ``"nonlinear"``, and the engine maps
the name to a fixed ``Limits`` value here. A pack never supplies raw ``Limits``, so the one
thing a policy can relax is the nonlinear-term gate. No policy can raise ``max_symbols``,
``max_premises``, ``max_nodes``, ``max_depth``, ``max_nary_args`` or ``max_const_digits``,
and none can change the division rules (constant non-zero divisors only).

* ``linear`` is :data:`~epinoic_logic.ir.schema.DEFAULT_LIMITS` itself, so a linear check
  runs exactly as every existing caller does and its result is byte-identical (no
  ``limits`` record; see :mod:`.results`).
* ``nonlinear`` is ``Limits(allow_nonlinear=True)`` and nothing else. The runner records
  it on the signed result, so a reader can see which gate a result was decided under.

Two engine bounds go with the nonlinear policy:

* :data:`NONLINEAR_RLIMIT`. :func:`policy_config` caps the solver's ``rlimit`` at this
  value, so a nonlinear check that runs out of resource stops at the same point on every
  run. That cutoff is a TIMEOUT, never a success. The value is calibrated in the engine
  README: every STEM encoding shape is decided within a tenth of it.
* :data:`NONLINEAR_MAX_DEGREE`. Z3 cannot be interrupted inside some high-degree
  polynomial operations. With the default 2000 ms timeout and ``allow_nonlinear``, a
  degree-1024 polynomial held the solver for about 20 s, and neither ``rlimit`` nor the
  timeout stopped it sooner. So the runner refuses any assertion whose polynomial degree
  exceeds this bound (UNSUPPORTED, ``E201``) before it compiles. Under the linear policy
  every degree is at most 1, so the bound never applies there.

Everything here inspects the IR as data. Nothing is evaluated or executed.
"""
from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping, Optional

from ..ir.schema import DEFAULT_LIMITS, Limits, Problem
from .errors import DiagnosticCode
from .results import SolverConfig
from .validator import validate_problem, walk_postorder

__all__ = [
    "LINEAR",
    "NONLINEAR",
    "LINEAR_LIMITS",
    "NONLINEAR_LIMITS",
    "PACK_POLICIES",
    "NONLINEAR_RLIMIT",
    "NONLINEAR_MAX_DEGREE",
    "UnknownPolicyError",
    "policy_limits",
    "policy_config",
    "required_policy",
    "polynomial_degree",
    "max_degree",
]

LINEAR = "linear"
NONLINEAR = "nonlinear"

#: The linear policy is the engine default itself (the same object), so nothing changes for it.
LINEAR_LIMITS: Limits = DEFAULT_LIMITS
#: The nonlinear policy opens the nonlinear-term gate and changes nothing else.
NONLINEAR_LIMITS: Limits = Limits(allow_nonlinear=True)

#: Read-only name -> Limits table. A pack can name an entry; it cannot add, replace or edit one.
PACK_POLICIES: Mapping[str, Limits] = MappingProxyType({LINEAR: LINEAR_LIMITS, NONLINEAR: NONLINEAR_LIMITS})

#: Deterministic Z3 resource limit for nonlinear checks (per solver call). Calibrated in
#: ``engine/README.md``: the costliest STEM shape still decides at a tenth of this value,
#: while a hard cubic system over the integers is cut off in a few hundred milliseconds.
NONLINEAR_RLIMIT: int = 2_000_000

#: Highest polynomial degree of one assertion the engine will hand to Z3 when nonlinear terms
#: are allowed. STEM needs degree 13 at most (integer powers up to 12, plus one auxiliary
#: factor); 24 leaves room for a product of two such terms. Measured: degree 32 decides in
#: under 1 s, while from degree 384 the solver overran a 2000 ms timeout (2.3 s), growing to
#: about 20 s at degree 1024.
NONLINEAR_MAX_DEGREE: int = 24

_MAX_NAME_CHARS = 64


class UnknownPolicyError(ValueError):
    """A policy name that is not exactly one of :data:`PACK_POLICIES`. Such a check is never run
    under some other policy; the caller reports it as undecided."""


def _describe(name: Any) -> str:
    """Bounded description of a refused name. Only a real ``str`` is shown, and only its first
    64 characters. Any other object is named by its type, so its own ``__repr__`` is never called."""
    if type(name) is str:
        shown = repr(name[:_MAX_NAME_CHARS])
        return shown + (f" (+{len(name) - _MAX_NAME_CHARS} characters)" if len(name) > _MAX_NAME_CHARS else "")
    return f"an object of type {type(name).__name__}"


def _known(name: Any) -> str:
    # Exact type and exact spelling: no case folding, no stripping, no str subclasses (whose
    # __eq__ or __hash__ could pretend to be a known name).
    if type(name) is not str or name not in PACK_POLICIES:
        raise UnknownPolicyError(
            f"unknown pack policy {_describe(name)}; known policies: {', '.join(sorted(PACK_POLICIES))}"
        )
    return name


def policy_limits(name: str) -> Limits:
    """The fixed ``Limits`` for a named policy. Raises :class:`UnknownPolicyError` for any other name."""
    return PACK_POLICIES[_known(name)]


def policy_config(name: str, config: SolverConfig) -> SolverConfig:
    """The solver configuration to run a check of policy ``name`` under.

    ``linear`` returns ``config`` itself, unchanged, so linear results bind to exactly the
    caller's configuration. ``nonlinear`` returns a copy whose ``rlimit`` is at most
    :data:`NONLINEAR_RLIMIT`. A caller's lower ``rlimit`` is kept, because a policy only ever
    tightens a bound. Raises :class:`UnknownPolicyError` for an unknown name.
    """
    if _known(name) == LINEAR:
        return config
    rlimit = NONLINEAR_RLIMIT if config.rlimit is None else min(int(config.rlimit), NONLINEAR_RLIMIT)
    if config.rlimit == rlimit:
        return config
    return config.model_copy(update={"rlimit": rlimit})


def required_policy(problem: Problem) -> str:
    """``"nonlinear"`` exactly when the linear policy refuses the problem for a nonlinear term
    (``E201``), else ``"linear"``. A pack can use this to pick the least permissive policy.
    It decides nothing about the problem's other diagnostics."""
    outcome = validate_problem(problem, LINEAR_LIMITS)
    if any(d.code == DiagnosticCode.NONLINEAR_TERM.value for d in outcome.diagnostics):
        return NONLINEAR
    return LINEAR


def polynomial_degree(expr: Any, path: str = "expr") -> int:
    """Total polynomial degree of one IR expression, by an iterative post-order walk.

    A numeric or Boolean variable has degree 1 and a literal has degree 0. ``mul`` adds the
    degrees of its factors. ``div``, ``idiv`` and ``mod`` add the degree of the divisor too
    (it is 0 for the literal divisors the validator admits). Every other node takes the
    largest degree among its children, so the condition of an ``ite`` counts as well. This
    is an upper bound on the degree Z3 sees after expanding products, never an underestimate.
    """
    degrees: dict[str, int] = {}
    for node, node_path, _depth, kid_paths in walk_postorder(expr, path):
        kids = [degrees.pop(kid_path) for kid_path in kid_paths]
        op = getattr(node, "op", None)
        if op == "var":
            degree = 1
        elif op in ("mul", "div", "idiv", "mod"):
            degree = sum(kids)
        else:
            degree = max(kids, default=0)
        degrees[node_path] = degree
    return degrees.get(path, 0)


def max_degree(problem: Problem) -> tuple[int, Optional[str]]:
    """The highest polynomial degree among the problem's assertions, with the path of the first
    assertion that reaches it (``None`` when the problem has no assertions)."""
    best, where = 0, None
    items = [(f"premises[{i}]", a) for i, a in enumerate(problem.premises)]
    if problem.conclusion is not None:
        items.append(("conclusion", problem.conclusion))
    for base, assertion in items:
        degree = polynomial_degree(assertion.expr, f"{base}.expr")
        if where is None or degree > best:
            best, where = degree, f"{base}.expr"
    return best, where
