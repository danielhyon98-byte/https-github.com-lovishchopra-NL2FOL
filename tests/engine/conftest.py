import pytest

from epinoic_logic.ir.schema import Problem


def V(name):
    return {"op": "var", "name": name}


def I(v):
    return {"op": "int", "value": str(v)}


def R(v):
    return {"op": "real", "value": str(v)}


def cmp(op, l, r):
    return {"op": op, "left": l, "right": r}


def make_problem(query, symbols, premises, conclusion=None, **extra):
    data = {
        "problem_id": extra.pop("problem_id", "p1"),
        "request_id": extra.pop("request_id", "req1"),
        "claim_id": extra.pop("claim_id", "c1"),
        "query": query,
        "symbols": [{"name": n, "sort": s, **g} for n, s, *rest in symbols for g in [rest[0] if rest else {}]],
        "premises": [
            {"id": pid, "expr": expr, **(meta or {})} for pid, expr, *rest in premises for meta in [rest[0] if rest else {}]
        ],
    }
    if conclusion is not None:
        cid, expr, *rest = conclusion
        data["conclusion"] = {"id": cid, "expr": expr, **(rest[0] if rest else {})}
    data.update(extra)
    return data


@pytest.fixture
def transitivity():
    """x>y, y>z |= x>z over Int."""
    return make_problem(
        "entailment",
        [("x", "Int"), ("y", "Int"), ("z", "Int")],
        [("P1", cmp("gt", V("x"), V("y"))), ("P2", cmp("gt", V("y"), V("z")))],
        ("C", cmp("gt", V("x"), V("z"))),
    )


@pytest.fixture
def argument_chain():
    """q -> d (specialist inference), d -> p (specialist inference), q (quotation): q entails p."""
    return make_problem(
        "entailment",
        [("q", "Bool"), ("d", "Bool"), ("p", "Bool")],
        [
            ("E1", V("q"), {"grounding": {"kind": "quotation", "verified": True}}),
            ("L1", {"op": "implies", "left": V("q"), "right": V("d")}, {"grounding": {"kind": "specialist_inference", "certainty": "probable"}}),
            ("L2", {"op": "implies", "left": V("d"), "right": V("p")}, {"grounding": {"kind": "specialist_inference", "certainty": "probable"}}),
            ("S1", V("q"), {"id": "S1", "grounding": {"kind": "supplied_text", "verified": True}}),
        ],
        ("POINT", V("p")),
    )
