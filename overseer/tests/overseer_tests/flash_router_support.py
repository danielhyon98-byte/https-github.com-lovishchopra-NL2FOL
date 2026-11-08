"""Where the flash router is, for the overseer tests that attach it to the pool through the router port.

The overseer never imports the flash router (``flash-router/``, package ``epinoic_flash_router``): its pool attaches the
router by module name, and the router runs in its own process, which imports what this process's import path holds
(``epinoic_logic.integration.router_child``). Inside the translator's repository the router is the sub-project beside
this one (installed, or on the documented test command's path); a standalone copy of the overseer finds it through
``EPINOIC_TRANSLATOR_ROOT`` or an installed ``epinoic-flash-router``, and without either a test that needs it is skipped
with that reason (never inside the repository, where it always runs).

:func:`attach` is the router as a deployment attaches it (its own process). :func:`attach_in_process` wires the router's
in-process API (``epinoic_flash_router.port.pool_hello`` and ``pool_plan``) for the sweeps that plan hundreds of batches:
the same code and the same data, without a process per plan.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import Optional

import pytest

from epinoic_logic.integration.router_pool import PoolRouterAttachment, attach_pool_router, attach_pool_router_in_process

from .translator_checkout import translator_root

MODULE = "epinoic_flash_router.port"
#: A generous bound for one plan in the tests (the deployment's is ``router_port.PLAN_TIMEOUT_S``): a loaded machine
#: never turns a test's router into a failed one.
TEST_TIMEOUT_S = 60.0


def flash_router_src() -> Optional[Path]:
    """The ``src/`` directory that holds ``epinoic_flash_router``, or None."""
    spec = importlib.util.find_spec("epinoic_flash_router")
    if spec is not None and spec.origin:
        return Path(spec.origin).resolve().parents[1]
    root = translator_root()
    if root is not None and (root / "flash-router" / "src" / "epinoic_flash_router" / "__init__.py").is_file():
        return root / "flash-router" / "src"
    return None


def require_flash_router() -> str:
    """The router's module name, importable on this process's path (so in the router's own process too)."""
    src = flash_router_src()
    if src is None:
        pytest.skip("needs the flash router: the translator's repository (flash-router/) or the epinoic-flash-router package; "
                    "this is a standalone copy of the overseer sub-project")
    if importlib.util.find_spec("epinoic_flash_router") is None:
        sys.path.insert(0, str(src))
    return MODULE


def attach(module: Optional[str] = None) -> PoolRouterAttachment:
    """The flash router attached as a deployment attaches it: by module name, through the router port, in its own
    process; refused or failed, the attachment says why (the test asserts it is attached)."""
    name = module or require_flash_router()
    return attach_pool_router(name, timeout_s=TEST_TIMEOUT_S, plan_timeout_s=TEST_TIMEOUT_S)


def attach_in_process() -> PoolRouterAttachment:
    """The router's in-process API attached through the router port's validation (tests and tools only)."""
    require_flash_router()
    port = importlib.import_module(MODULE)
    return attach_pool_router_in_process(port.pool_hello, port.pool_plan, plan_timeout_s=TEST_TIMEOUT_S)
