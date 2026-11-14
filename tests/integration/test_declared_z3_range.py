"""The z3-solver range the package declares agrees with the range the integration bootstrap accepts (round-9 clearance c2b, the core
fixer's handoff 3: ``pyproject.toml`` declared ``z3-solver>=4.13`` while the bootstrap accepts only ``[5.1.0, 5.2)``, so a fresh install
resolved 5.3.3 and every service entry refused with KIT-HS-003). Read as data: the declared specifier from ``pyproject.toml`` (TOML, with
the standard library's reader), the accepted range from the kit's compatibility record."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

from epinoic_logic.integration.compat import COMPATIBILITY

ROOT = Path(__file__).resolve().parents[2]


def _declared() -> list[str]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    deps = list(project["dependencies"]) + [d for extra in project.get("optional-dependencies", {}).values() for d in extra]
    return [d for d in deps if re.match(r"^\s*z3-solver\b", d)]


def test_the_declared_z3_range_is_the_one_the_bootstrap_accepts():
    accepted = COMPATIBILITY["components"]["z3_solver"]
    [spec] = _declared()  # declared once, in the dependencies, never also in an extra with another range
    bounds = sorted(x.strip() for x in spec.split("z3-solver", 1)[1].split(","))
    assert bounds == sorted([f">={accepted['min']}", f"<{accepted['below']}"]), (spec, accepted)


def test_the_kit_constraints_pin_a_version_inside_the_declared_range():
    pinned = re.search(r"^z3-solver==(\S+)$", (ROOT / "integration" / "constraints.txt").read_text(encoding="utf-8"), re.MULTILINE).group(1)
    accepted = COMPATIBILITY["components"]["z3_solver"]
    as_tuple = lambda v: tuple(int(x) for x in v.split(".")[:3])  # noqa: E731
    assert as_tuple(accepted["min"]) <= as_tuple(pinned) < as_tuple(accepted["below"] + ".0"), pinned
