"""Test set-up of the flash-router sub-project (its own test package, ``flash_router_tests``, so the translator's
documented test command can collect it beside the translator's and the overseer's suites).

The router itself imports only the standard library. Its conformance tests validate what it answers with the
translator's router port (``epinoic_logic.integration.router_port`` and ``router_pool``: pydantic and the standard
library, no engine, no Z3, no overseer), exactly as the service and the overseer pool validate it. Inside the
translator repository the tests use that repository's own ``src/`` (the router port this sub-project is released
against); a copy of the sub-project outside it (``git subtree split --prefix flash-router``) uses the translator package
installed in its environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
TRANSLATOR_SRC = PROJECT.parent / "src"

sys.path.insert(0, str(PROJECT / "src"))
if (TRANSLATOR_SRC / "epinoic_logic" / "integration" / "router_port.py").is_file():
    sys.path.insert(1, str(TRANSLATOR_SRC))


# The meaning label (stage 2a of the meaning check, interface (a)). The flash router reads no answer text (it plans review methods
# from the pool's risk features only), and this suite runs the router and the translator's router port alone: it opens no channel,
# makes no receipt, no delivery record and no label, so there is nothing for the faithful fake to answer and nothing for the T24
# invariant to read here. The sub-project's own rule (test_subproject.py: the tests reach the translator through its router port
# contract only) also keeps the translator's public label API out of this suite. The marker every suite of the repository knows is
# registered, so a test marked ``real_labeller`` reads the same here. The method tests of T19 (IN_DEPTH, DUPLICATE, SPLIT and N_FOLD
# each leave a label-blocked candidate undeliverable) run where the router is attached to the overseer's pool and its delivery
# policy decides: overseer/tests/overseer_tests/test_c3k_label_gate.py.
def pytest_configure(config):
    config.addinivalue_line("markers", "real_labeller: run with the translator's production default labeller (UnconfiguredLabeller)")
