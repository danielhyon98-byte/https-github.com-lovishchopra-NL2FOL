"""Where the translator's repository is, for the few tests and harness runs that read its files (the arena runner
``scripts/arena/run_arena.py``, the recorded rounds' tooling and the Worker's ``integration/website/src/verify/``).

Inside the translator's repository (``overseer/`` is a sub-project of it) that repository is used. A standalone copy of
the sub-project (``git subtree split --prefix overseer``) names a translator checkout with ``EPINOIC_TRANSLATOR_ROOT``;
without one, a test that needs it is skipped with that reason (never inside the repository, where it always runs).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import pytest

SUBPROJECT = Path(__file__).resolve().parents[2]


def _is_translator_checkout(path: Path) -> bool:
    return (path / "src" / "epinoic_logic" / "__init__.py").is_file() and (path / "scripts" / "arena" / "run_arena.py").is_file()


def translator_root() -> Optional[Path]:
    """``EPINOIC_TRANSLATOR_ROOT`` when set, else the repository this sub-project lives in, else None."""
    named = os.environ.get("EPINOIC_TRANSLATOR_ROOT", "").strip()
    if named:
        return Path(named).resolve()
    enclosing = SUBPROJECT.parent
    return enclosing if _is_translator_checkout(enclosing) else None


def require_translator_root() -> Path:
    """The translator checkout, or skip: only a standalone copy of the sub-project without EPINOIC_TRANSLATOR_ROOT."""
    root = translator_root()
    if root is None:
        pytest.skip("needs the translator's repository: this is a standalone copy of the overseer sub-project; set EPINOIC_TRANSLATOR_ROOT")
    return root
