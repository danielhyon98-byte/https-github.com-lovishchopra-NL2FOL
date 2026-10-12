"""Safety of the STEM front end: nothing evaluates agent text, imports stay on an allowlist, and
adversarial input is rejected within bounds, without raising and without excessive time
(docs/STEM_DESIGN.md, sections 4.9 and 11)."""
from __future__ import annotations

import ast
import time
from pathlib import Path

import pytest

from epinoic_logic.stem import build_document, clear_document_cache

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "epinoic_logic" / "stem"
STEM_MODULES = {p.stem for p in PACKAGE.glob("*.py")}

#: built-in names that evaluate, compile, import or reflect: never used by the front end
FORBIDDEN_NAMES = frozenset({"eval", "exec", "compile", "__import__", "globals", "locals", "vars", "open", "input", "breakpoint", "setattr", "delattr",
                             "memoryview", "help"})
#: attributes that evaluate strings or reach the interpreter (``ast.literal_eval``, ``sympy.sympify``, ``pickle.loads``, ``os.system``, ...)
FORBIDDEN_ATTRS = frozenset({"eval", "exec", "sympify", "parse_expr", "literal_eval", "loads", "load", "system", "popen", "import_module", "__import__",
                             "__subclasses__", "__globals__", "__builtins__", "__code__", "__getattribute__", "run_path", "run_module"})
#: standard-library modules the front end may import (data structures, exact arithmetic, text scanning, hashing for cache keys)
STDLIB_ALLOWED = frozenset({"__future__", "re", "fractions", "dataclasses", "functools", "typing", "hashlib", "unicodedata", "math", "enum", "types"})
#: the one module outside the package it may import: the shared sentence splitter (design section 4.3), used as it is
SHARED_ALLOWED = frozenset({"adapters.history_specialist.sentences"})


def violations(source: str, filename: str = "<src>") -> list[str]:
    """Every use of a forbidden name, attribute, reflective call or import in ``source``."""
    out: list[str] = []
    tree = ast.parse(source, filename=filename)
    for node in ast.walk(tree):
        where = f"{filename}:{getattr(node, 'lineno', 0)}"
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            out.append(f"{where} name {node.id}")
        elif isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS:
            out.append(f"{where} attribute .{node.attr}")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("getattr", "hasattr"):
            if len(node.args) < 2 or not (isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str)):
                out.append(f"{where} {node.func.id} with a computed attribute name")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] not in STDLIB_ALLOWED:
                    out.append(f"{where} import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and mod.split(".")[0] not in STDLIB_ALLOWED:
                out.append(f"{where} from {mod} import")
            elif node.level == 1 and mod.split(".")[0] not in STEM_MODULES:
                out.append(f"{where} from .{mod} import (not a stem module)")
            elif node.level == 2 and mod not in SHARED_ALLOWED:
                out.append(f"{where} from ..{mod} import")
            elif node.level > 2:
                out.append(f"{where} relative import beyond the package")
    return out


def test_package_is_scanned():
    assert {"lexer", "parser", "numbers", "units", "spans", "segment", "scope", "relations", "chem", "boolean", "document", "normalize", "nodes",
            "limits", "__init__"} <= STEM_MODULES


@pytest.mark.parametrize("path", sorted(PACKAGE.glob("*.py")), ids=lambda p: p.name)
def test_no_evaluation_and_import_allowlist(path):
    assert violations(path.read_text(encoding="utf-8"), path.name) == []


@pytest.mark.parametrize("bad", [
    "eval('1+1')", "exec('x = 1')", "compile('1', 'f', 'eval')", "__import__('os')", "import os", "import pickle", "from sympy import sympify",
    "import ast\nast.literal_eval('1')", "from subprocess import run", "x = getattr(obj, name)", "setattr(obj, 'a', 1)", "import importlib",
    "from ...engine import runner", "from ..engine import runner", "open('f')", "import marshal", "import numpy",
])
def test_the_scan_catches_violations(bad):
    assert violations(bad) != []


def test_the_scan_accepts_what_the_package_does():
    ok = "from __future__ import annotations\nimport re\nfrom fractions import Fraction\nfrom .lexer import lex\n" \
         "from ..adapters.history_specialist.sentences import sentence_boundaries\nx = getattr(node, 'start', 0)\nre.compile('a')\n"
    assert violations(ok) == []


# ---------------------------------------------------------------- adversarial input

def _adversarial(n: int) -> list[tuple[str, str, str]]:
    """(name, profile, text) of about ``n`` characters each."""
    k = max(1, n // 10)
    return [
        ("nested_parens_500", "mathematics_aa", "x = " + "(" * 500 + "1" + ")" * 500 + " and y = 2. " * k),
        ("nested_unclosed", "physics", "(" * n),
        ("nested_latex_500", "mathematics_aa", "$" + "\\frac{" * 500 + "1" + "}{2}" * 500 + "$ = 1"),
        ("unclosed_dollars", "physics", "$x = 1 " * k),
        ("dollar_storm", "physics", "$" * n),
        ("sci_chain", "physics", "x = " + "1e" * (n // 2)),
        ("digits_30", "physics", " ".join(["x = " + "9" * 30] * (n // 36))),
        ("digits_10000", "physics", "x = " + "7" * 10_000 + " m s⁻¹"),
        ("tower", "mathematics_aa", "y = 10^10^10^10 = " + "10^" * (n // 3) + "10"),
        ("huge_exponent", "physics", "E = 1.5 × 10^99999999 J and m = 1e999999 kg. " * (k // 4 or 1)),
        ("malformed_latex", "mathematics_aa", ("$$\\begin{align} x &= \\frac{{{ \\left( \\sqrt[ \\text{ \\unknown{ $$ " * (k // 6 or 1))),
        ("confusables", "physics", ("а = 3 ν = 2 х = 5 Ꮪ = 1 ０ = １ x‍ = 2 ‮x = 3 " * (k // 4 or 1))),
        ("deep_unary", "physics", "x = " + "-" * (n // 2) + "1"),
        ("relation_storm", "physics", "= " * (n // 2)),
        ("comparison_storm", "mathematics_aa", "a == b " * (n // 7)),
        ("long_word_line", "physics", "x" * n + " = 1"),
        ("many_lines", "physics", "v = 5.0 m s⁻¹\n" * (n // 14)),
        ("chem_storm", "chemistry", " + ".join(["2H₂O(l)"] * (n // 20)) + " → " + " + ".join(["Fe2+(aq)"] * (n // 20))),
        ("fences", "computer_science", "```\n" * (n // 4)),
        ("table_storm", "computer_science", "| A | B | A AND B |\n|---|---|---|\n" + "| 0 | 1 | 0 |\n" * (n // 14)),
        ("bars", "mathematics_aa", "| " * (n // 2) + "x = 1"),
        ("subscripts", "physics", "x" + "_{" * (n // 2) + " = 1"),
        ("roots_deltas_primes", "physics", "√" * (n // 3) + "2 = " + "Δ" * (n // 3) + "x''''''''''"),
        ("superscripts", "physics", "x" + "⁻¹²³⁴⁵⁶⁷⁸⁹" * (n // 10) + " = 1"),
        ("controls", "physics", ("\x00\x01\x1b[31m x = 1 � \U0001f600 = 2 " * (k // 3 or 1))),
        ("implicit_letters", "physics", "E = " + "abcdefghij" * (n // 10)),
        ("verbal", "physics", " ".join(["3 plus 4 times 5 divided by 2 equals 7"] * (n // 40))),
        ("units_storm", "physics", "x = 1 " + "kg m s⁻² mol⁻¹ K⁻¹ " * (n // 20)),
    ]


SMALL = _adversarial(20_000)


@pytest.mark.parametrize("name, profile, text", SMALL, ids=[c[0] for c in SMALL])
def test_adversarial_input_is_bounded_and_never_raises(name, profile, text):
    clear_document_cache()
    t = time.perf_counter()
    d = build_document(text, "Calculate x. " * 3, profile)
    elapsed = time.perf_counter() - t
    assert elapsed < 3.0, f"{name}: {elapsed:.2f}s"
    assert not [f for f in d.findings if f.code == "ST-INTERNAL-001"], name
    assert all(f.severity in ("info", "warning") for f in d.findings)
    assert len(d.checks) <= d.limits.max_checks_per_report and len(d.statements) <= d.limits.max_statements
    for st in d.statements:
        assert 0 <= st.start <= st.end <= len(text)


def test_huge_powers_are_never_computed():
    t = time.perf_counter()
    d = build_document("y = 10^10^10\nz = 2^(10^12)\nw = 9^99999999", None, "mathematics_aa")
    assert time.perf_counter() - t < 1.0
    assert not d.checks
    assert all(r.outcome in ("undecided", "binding", "context", "formula") for r in d.relations)


def test_ten_thousand_digit_numeral_is_rejected_within_bounds():
    d = build_document("x = " + "7" * 10_000, None, "physics")
    assert any(f.code == "ST-LIM-001" for f in d.findings) and not d.checks


@pytest.mark.stress
@pytest.mark.parametrize("name, profile, text", _adversarial(380_000), ids=[c[0] for c in _adversarial(10)])
def test_adversarial_input_at_the_response_bound(name, profile, text):
    text = text[:400_000]
    clear_document_cache()
    t = time.perf_counter()
    d = build_document(text, None, profile)
    elapsed = time.perf_counter() - t
    assert elapsed < 8.0, f"{name}: {elapsed:.2f}s"
    assert not [f for f in d.findings if f.code == "ST-INTERNAL-001"], name
