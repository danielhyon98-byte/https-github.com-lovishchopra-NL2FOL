"""Stage 0 of the integration service: Z3 must be present, checked before any engine module is imported.

Standard library only (with the generated ``compat`` data and the ``errors`` table, both standard library only). The
check looks for the ``z3`` module, reads the installed ``z3-solver`` version against the range pinned in
``integration/COMPATIBILITY.json``, and imports ``z3`` inside a ``try``. Any failure prints the single line
``KIT-HS-003 z3_unavailable`` on standard error and exits with status 2: no traceback, no fallback, and no engine module
imported. Z3 and the STEM front end are required parts of the integration ("z3 is not optional").
"""
from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import re
import sys
from typing import Optional, TextIO

from .compat import COMPATIBILITY
from .errors import code_line

__all__ = ["version_tuple", "z3_problem", "require_z3"]


def version_tuple(text: str) -> tuple[int, ...]:
    """The leading numeric components of a version string (``"5.1.0.0"`` -> ``(5, 1, 0, 0)``)."""
    parts: list[int] = []
    for piece in str(text).split("."):
        m = re.match(r"^([0-9]+)", piece)
        if not m:
            break
        parts.append(int(m.group(1)))
    return tuple(parts)


def z3_problem() -> Optional[str]:
    """``None`` when Z3 is importable and its version is in the accepted range, else a short secret-free reason."""
    accepted = COMPATIBILITY["components"]["z3_solver"]
    try:
        spec = importlib.util.find_spec("z3")
    except (ImportError, ValueError):  # ValueError: a module hidden as None in sys.modules has no spec
        return "the z3 module cannot be found"
    if spec is None:
        return "the z3 module cannot be found"
    try:
        installed = importlib.metadata.version("z3-solver")
    except importlib.metadata.PackageNotFoundError:
        return "the z3-solver distribution is not installed"
    have = version_tuple(installed)
    if not have or not version_tuple(accepted["min"]) <= have < version_tuple(accepted["below"]):
        return f"z3-solver {installed} is outside the accepted range [{accepted['min']}, {accepted['below']})"
    try:
        importlib.import_module("z3")
    except Exception:  # noqa: BLE001 - any failure to import is the same refusal
        return "the z3 module cannot be imported"
    return None


def require_z3(stream: Optional[TextIO] = None) -> None:
    """Exit with status 2 after printing ``KIT-HS-003 z3_unavailable`` unless Z3 is usable."""
    if z3_problem() is not None:
        out = stream if stream is not None else sys.stderr
        out.write(code_line("KIT-HS-003") + "\n")
        out.flush()
        raise SystemExit(2)
