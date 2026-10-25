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

One engine bound goes with every policy, linear ones included:

* :data:`MAX_COEFFICIENT_DIGITS`. Z3 checks its timeout between steps of exact arithmetic, and
  one step on numbers of tens of thousands of digits runs for seconds: a chain of 40 linear
  equations, each multiplying the previous term by a product of 25 thirty-digit literals,
  held one solver call for 5 s under a 2000 ms timeout (repair round 2, formal-robustness-1
  variant). :func:`coefficient_digits` bounds, from the IR alone, the digits of every number
  the exact linear arithmetic of a problem can reach (a Hadamard bound: the sum of the
  coefficient digits of the largest rows, one row per comparison, as many rows as the
  problem has numeric unknowns plus one), and the runner refuses a problem above the bound
  before it compiles (INVALID_FORMALIZATION, ``E307``, a limit like ``E305``).

Named engine policies a caller may request (:data:`NAMED_POLICIES`): the pack policies and
``joint``, the integrity layer's joint bounds (:data:`JOINT_LIMITS`). A caller outside this
process (``POST /v1/verify``, ``epinoic-logic verify --policy``) names one of them; it can
never send limits of its own. :func:`named_policy` returns the ``Limits`` and the solver
configuration a problem is decided under for that name, exactly as the in-process caller of
that policy decides it (the channel's branch checks for ``linear`` and ``nonlinear``, the
cross-agent joint checks for ``joint``), so the same problem gets the same decision in
process and over HTTP. The result binds the policy: its non-default limits are recorded and
their digest is part of the binding digest (``Binding.limits_digest``), the nonlinear
``rlimit`` cap is part of the configuration digest, and :func:`named_policy_of` names the
policy a result's limits record stands for. A pack still cannot choose ``joint``.

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
    "JOINT",
    "LINEAR_LIMITS",
    "NONLINEAR_LIMITS",
    "JOINT_LIMITS",
    "PACK_POLICIES",
    "NAMED_POLICIES",
    "NONLINEAR_RLIMIT",
    "NONLINEAR_MAX_DEGREE",
    "UnknownPolicyError",
    "policy_limits",
    "policy_config",
    "named_policy",
    "named_policy_of",
    "required_policy",
    "polynomial_degree",
    "max_degree",
    "MAX_COEFFICIENT_DIGITS",
    "MAX_FORCED_VALUE_DIGITS",
    "forced_value_digits",
    "coefficient_digits",
]

LINEAR = "linear"
NONLINEAR = "nonlinear"
JOINT = "joint"

#: The linear policy is the engine default itself (the same object), so nothing changes for it.
LINEAR_LIMITS: Limits = DEFAULT_LIMITS
#: The nonlinear policy opens the nonlinear-term gate and changes nothing else.
NONLINEAR_LIMITS: Limits = Limits(allow_nonlinear=True)

#: Read-only name -> Limits table. A pack can name an entry; it cannot add, replace or edit one.
PACK_POLICIES: Mapping[str, Limits] = MappingProxyType({LINEAR: LINEAR_LIMITS, NONLINEAR: NONLINEAR_LIMITS})
#: Bounds of the integrity layer's joint problems (cross-agent consistency, synthesis entailment and their re-checks): a
#: union of many claims would exceed the per-claim shape limits, so joint checks run under these larger bounds. Never a
#: pack policy. A joint result records them and binds their digest, so a receiver must name them as its required policy.
JOINT_LIMITS: Limits = Limits(max_symbols=1024, max_premises=4096, max_nodes=200_000, max_depth=40, max_nary_args=64)
#: Read-only name -> Limits table of the policies a caller outside the packs may request by name (the service, the CLI):
#: the pack policies and the joint bounds. Never raw limits; every other name is refused (:class:`UnknownPolicyError`).
NAMED_POLICIES: Mapping[str, Limits] = MappingProxyType({LINEAR: LINEAR_LIMITS, NONLINEAR: NONLINEAR_LIMITS, JOINT: JOINT_LIMITS})

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

#: Highest bound (:func:`coefficient_digits`) on the decimal digits of the numbers one problem's exact arithmetic can
#: reach. Measured on the chain of the policy docstring, at a 2000 ms timeout: about 15,200 digits (20 links) decide in
#: 0.4 s and 18,800 (24 links) in 1.2 s, 21,800 (28 links) reach the timeout, and from about 24,800 (32 links) one solver
#: call overruns it (3.3 s, growing to 5 s at 40 links). Every problem within the default limits whose literals are not
#: multiplied together stays far below the bound (128 rows of 40-digit literals are about 5,300 digits).
MAX_COEFFICIENT_DIGITS: int = 16_000

#: Highest bound (:func:`forced_value_digits`) on the decimal digits of a value the products of a nonlinear problem force.
#: Z3 checks neither its timeout nor its ``rlimit`` inside nonlinear arithmetic on such values: a chain of squarings of a
#: variable fixed to a 40-digit literal (degree 2 per assertion, within :data:`NONLINEAR_MAX_DEGREE`) decided at a 2000 ms
#: timeout in 0.09 s for 640 forced digits, 0.17 s for 960, about 0.4 s for 1,280 to 2,048, about 2 s for 2,560 and 3.1 s
#: for 5,120, and held one solver call for 37 s for 10,240 (repair round 4, formal-robustness-1 variant). The STEM shapes
#: force at most a few hundred digits (integer powers up to 12 of a literal of at most 30 digits).
MAX_FORCED_VALUE_DIGITS: int = 2_000

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


def _known(name: Any, table: Mapping[str, Limits] = PACK_POLICIES, what: str = "pack policy") -> str:
    # Exact type and exact spelling: no case folding, no stripping, no str subclasses (whose
    # __eq__ or __hash__ could pretend to be a known name).
    if type(name) is not str or name not in table:
        raise UnknownPolicyError(
            f"unknown {what} {_describe(name)}; known policies: {', '.join(sorted(table))}"
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


def named_policy(name: str, config: SolverConfig) -> tuple[Limits, SolverConfig]:
    """``(limits, config)`` to decide a problem under the named policy ``name`` exactly as the in-process caller of that
    policy decides it: a pack policy as the channel runs a branch check (:func:`policy_limits` and
    :func:`policy_config`: ``linear`` is the configuration unchanged, ``nonlinear`` caps its ``rlimit`` at
    :data:`NONLINEAR_RLIMIT` and keeps a lower one), ``joint`` as the cross-agent joint checks run (:data:`JOINT_LIMITS`,
    the configuration unchanged). Raises :class:`UnknownPolicyError` for any other name (exact type and spelling, as for
    the pack policies), so nothing is ever run under a guessed or caller-built policy."""
    known = _known(name, NAMED_POLICIES, "engine policy")
    if known == JOINT:
        return JOINT_LIMITS, config
    return policy_limits(known), policy_config(known, config)


def named_policy_of(limits: Optional[Limits]) -> Optional[str]:
    """The named policy whose limits are exactly ``limits`` (a result's ``limits`` record; ``None``, the record of the
    default limits, is ``linear``), or ``None`` when no named policy has those values (limits an in-process caller
    chose itself). Every limit value is compared, so a result names its policy without trusting any label."""
    if limits is None:
        return LINEAR
    if not isinstance(limits, Limits):
        return None
    values = {field: getattr(limits, field) for field in Limits.model_fields}
    for name in sorted(NAMED_POLICIES):
        if NAMED_POLICIES[name].model_dump() == values:
            return name
    return None


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


_COMPARISONS = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})


def _literal_digits(text: str) -> tuple[int, int, int]:
    """``(numerator digits, power-of-ten exponent, other denominator digits)`` of a literal's exact value: "1.25" is 125/10^2
    (3, 2, 0), "7/3" is (1, 0, 1), "40" is (2, 0, 0). Read from the literal's characters only."""
    body = text.strip().lstrip("+-−")
    if "/" in body:
        num, _, den = body.partition("/")
        return _numeral_digits(num), 0, _numeral_digits(den)
    whole, _, frac = body.partition(".")
    return _numeral_digits(whole + frac), len(frac), 0


def _numeral_digits(digits: str) -> int:
    return max(1, len(digits.lstrip("0")))


def _sum_digits(kids: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    """The digit triple of a sum (or difference) of linear forms: over the common denominator (the largest power of ten
    times the product of the other denominators), each numerator grows by the denominators it is scaled by, and a sum of
    ``n`` terms by at most the digits of ``n``."""
    t = max(k[1] for k in kids)
    g = sum(k[2] for k in kids)
    c = max(k[0] + (t - k[1]) + (g - k[2]) for k in kids) + len(str(len(kids)))
    return c, t, g


def _equalities(expr: Any, path: str, out: list[tuple[str, Any, str]], budget: list[int]) -> None:
    """The ``var = expr`` equalities an assertion states outright (itself, or a conjunct of a top-level conjunction), with
    their paths. Iterative over nested conjunctions; at most ``budget[0]`` are collected."""
    stack = [(expr, path)]
    while stack and budget[0] > 0:
        node, where = stack.pop()
        op = getattr(node, "op", None)
        if op == "and":
            stack.extend((arg, f"{where}.args[{i}]") for i, arg in enumerate(getattr(node, "args", None) or ()))
            continue
        if op != "eq":
            continue
        left, right = node.left, node.right
        for var, other in ((left, right), (right, left)):
            if getattr(var, "op", None) == "var":
                out.append((var.name, other, where))
                budget[0] -= 1


def forced_value_digits(problem: Problem) -> tuple[int, Optional[str]]:
    """An upper bound on the decimal digits of the values the equalities of ``problem`` force through products, with the
    path of the equality that reaches it (``(0, None)`` when no equality forces a numeric value).

    Read from the IR alone (nothing is evaluated): each premise's ``var = expr`` equalities (outright or as conjuncts) give
    ``var`` the digits of ``expr``, where a literal has its own digits (numerator and denominator), a variable the bound
    found so far (none until an equality gives it one), a product the sum of its factors' digits, a quotient the sum of
    its operands', a sum or difference the largest term's digits plus the digits of the term count, a negation its
    operand's, an ``ite`` its larger branch's. The bounds are propagated to a fixed point (at most as many rounds as there
    are equalities, a variable keeping the smallest bound any of its equalities gives it, so a cycle never grows), and the
    largest digits of any equality's expression is returned: what the solver may have to compute. A chain of squarings
    doubles the digits at each link ("x = <40 digits>, y1 = x·x, ..., y8 = y7·y7" forces 10,240 digits)."""
    from .validator import walk_postorder as _walk
    sorts = {s.name: s.sort for s in problem.symbols}
    eqs: list[tuple[str, Any, str]] = []
    budget = [4096]
    for i, a in enumerate(problem.premises):
        _equalities(a.expr, f"premises[{i}].expr", eqs, budget)
    eqs = [(v, e, w) for v, e, w in eqs if sorts.get(v) in ("Int", "Real")]
    if not eqs:
        return 0, None
    bound: dict[str, int] = {}

    def digits_of(expr: Any) -> Optional[int]:
        vals: dict[str, Optional[int]] = {}
        for node, node_path, _depth, kid_paths in _walk(expr, "e"):
            kids = [vals.pop(kp, None) for kp in kid_paths]
            op = getattr(node, "op", None)
            value: Optional[int] = None
            if op == "var":
                value = bound.get(node.name)
            elif op in ("int", "real"):
                c, t, g = _literal_digits(str(node.value))
                value = c + t + g
            elif op == "mul" and kids and all(k is not None for k in kids):
                value = sum(kids)  # type: ignore[arg-type]
            elif op == "div" and len(kids) == 2 and all(k is not None for k in kids):
                value = kids[0] + kids[1]  # type: ignore[operator]
            elif op in ("add", "sub") and kids and all(k is not None for k in kids):
                value = max(kids) + len(str(len(kids)))  # type: ignore[type-var]
            elif op in ("neg", "to_real", "idiv", "mod") and kids and kids[0] is not None:
                value = kids[0]
            elif op == "ite" and len(kids) == 3 and kids[1] is not None and kids[2] is not None:
                value = max(kids[1], kids[2])
            vals[node_path] = value
        return vals.get("e")

    best, where = 0, None
    for _round in range(len(eqs) + 1):
        changed = False
        for var, expr, path in eqs:
            d = digits_of(expr)
            if d is None:
                continue
            if d > best:
                best, where = d, path
            if var not in bound or d < bound[var]:
                bound[var] = d
                changed = True
        if not changed:
            break
    return best, where


def coefficient_digits(problem: Problem) -> tuple[int, Optional[str]]:
    """An upper bound on the decimal digits of every number the exact linear arithmetic of ``problem`` can reach, with the
    path of the comparison whose row has the most coefficient digits (``(0, None)`` when it compares no numbers).

    Each comparison of numbers is one row of the linear system. A numeric expression is read, by an iterative post-order
    walk over the IR (nothing is evaluated), as a digit triple: the digits of the largest integer numerator of its
    coefficients over a common denominator, that denominator's power of ten, and the digits of its other factors. A
    variable is (1, 0, 0), a literal its own digits; a product adds its factors' digits, a division by a constant moves
    the divisor's digits across, a sum scales each term to the common denominator; an ``ite`` term, an integer division
    and a remainder are fresh unknowns with rows of their own. The numbers the simplex can reach are quotients of minors of
    the rows, so by Hadamard's bound none has more digits than the sum, over as many of the largest rows as the problem
    has unknowns plus one, of each row's digits plus the digits of that count."""
    sorts = {s.name: s.sort for s in problem.symbols}
    rows: list[tuple[int, str]] = []
    fresh = 0
    items = [(f"premises[{i}]", a) for i, a in enumerate(problem.premises)]
    if problem.conclusion is not None:
        items.append(("conclusion", problem.conclusion))
    for base, assertion in items:
        vals: dict[str, Optional[tuple[int, int, int]]] = {}
        for node, node_path, _depth, kid_paths in walk_postorder(assertion.expr, f"{base}.expr"):
            kids = [vals.pop(kp, None) for kp in kid_paths]
            op = getattr(node, "op", None)
            value: Optional[tuple[int, int, int]] = None
            if op == "var":
                value = (1, 0, 0) if sorts.get(node.name) in ("Int", "Real") else None
            elif op in ("int", "real"):
                value = _literal_digits(str(node.value))
            elif op in ("add", "sub") and all(k is not None for k in kids) and kids:
                value = _sum_digits(kids)  # type: ignore[arg-type]
            elif op in ("neg", "to_real") and kids and kids[0] is not None:
                value = kids[0]
            elif op == "mul" and all(k is not None for k in kids) and kids:
                value = (sum(k[0] for k in kids), sum(k[1] for k in kids), sum(k[2] for k in kids))  # type: ignore[index]
            elif op == "div" and len(kids) == 2 and kids[0] is not None and kids[1] is not None:
                (c, t, g), (rc, rt, rg) = kids  # type: ignore[misc]
                value = (c + rt + rg, t, g + rc)
            elif op in ("idiv", "mod") and len(kids) == 2 and kids[0] is not None and kids[1] is not None:
                # q = l div r and m = l mod r are fresh unknowns: the row l - r*q - m = 0 holds l's and r's digits
                rows.append((_sum_digits([kids[0], (kids[1][0], 0, 0), (1, 0, 0)])[0], node_path))
                fresh += 2
                value = (1, 0, 0)
            elif op == "ite" and len(kids) == 3 and kids[1] is not None and kids[2] is not None:
                for branch in kids[1:]:  # the term v and the rows v - then = 0, v - else = 0
                    rows.append((_sum_digits([(1, 0, 0), branch])[0], node_path))  # type: ignore[list-item]
                fresh += 1
                value = (1, 0, 0)
            elif op in _COMPARISONS and len(kids) == 2 and kids[0] is not None and kids[1] is not None:
                rows.append((_sum_digits(kids)[0], node_path))  # type: ignore[arg-type]
            vals[node_path] = value
    if not rows:
        return 0, None
    unknowns = sum(1 for sort in sorts.values() if sort in ("Int", "Real")) + fresh + 1
    rows.sort(key=lambda r: -r[0])
    top = rows[:unknowns]
    return sum(d for d, _p in top) + len(top) * len(str(len(top))), rows[0][1]
