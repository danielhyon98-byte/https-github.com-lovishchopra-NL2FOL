"""Test set-up of the combinator sub-project.

The combinator imports only the standard library and its own package. Most of its tests need nothing else. Its
conformance tests (``test_conformance.py``) compare it with the translator's own combinator port
(``epinoic_logic.integration.combinator_port``, which the hub's contract is published from): inside the translator
repository they use that repository's ``src/`` and must run; a copy of the sub-project outside it runs them against the
translator package installed in its environment, and skips them (saying so) when none is installed.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
TRANSLATOR_SRC = PROJECT.parent / "src"
#: True when this sub-project sits in the translator repository (its port module beside it).
INSIDE_TRANSLATOR = (TRANSLATOR_SRC / "epinoic_logic" / "integration" / "combinator_port.py").is_file()

sys.path.insert(0, str(PROJECT / "src"))
if INSIDE_TRANSLATOR:
    sys.path.insert(1, str(TRANSLATOR_SRC))


def _translator_importable() -> bool:
    try:
        import epinoic_logic.integration.combinator_port  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="session")
def kit():
    """The translator's combinator port. Inside the translator repository its absence is a failure, never a skip."""
    if not _translator_importable():
        if INSIDE_TRANSLATOR:
            pytest.fail("inside the translator repository the conformance tests must run, but its src/ is not importable")
        pytest.skip("the translator package (epinoic_logic) is not installed: the conformance tests against its combinator port need it")
    from epinoic_logic.integration import combinator_port
    return combinator_port
