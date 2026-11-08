"""The overseer sub-project's test helpers (``overseer/tests/overseer_tests``), for the translator's tests that attach the
overseer to a hub (its test auditor, keys and scripted overseer agents).

The overseer is a separate sub-project (``overseer/``, package ``epinoic_overseer``); its tests are the package
``overseer_tests`` under ``overseer/tests``. Importing this module puts that directory on the import path, so
``from overseer_tests.conftest import make_auditor`` names the same module pytest loads for the overseer's own suite.
"""
from __future__ import annotations

import sys
from pathlib import Path

OVERSEER_TESTS = Path(__file__).resolve().parents[1] / "overseer" / "tests"
if str(OVERSEER_TESTS) not in sys.path:
    sys.path.insert(0, str(OVERSEER_TESTS))
