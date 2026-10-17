"""Test set-up of the flash-router sub-project.

The router itself imports only the standard library. Its conformance tests validate what it answers with the
translator's router port (``epinoic_logic.integration.router_port``: pydantic and the standard library, no engine, no
Z3), exactly as the service validates it. Inside the translator repository the tests use that repository's own
``src/`` (the router port this sub-project is released against); a copy of the sub-project outside it uses the
translator package installed in its environment.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
TRANSLATOR_SRC = PROJECT.parent / "src"

sys.path.insert(0, str(PROJECT / "src"))
if (TRANSLATOR_SRC / "epinoic_logic" / "integration" / "router_port.py").is_file():
    sys.path.insert(1, str(TRANSLATOR_SRC))
