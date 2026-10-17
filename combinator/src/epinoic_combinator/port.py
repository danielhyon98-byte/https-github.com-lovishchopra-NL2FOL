"""What the translator's service attaches through the combinator port (``epinoic.integration.combinator-port.v1``).

* ``hello() -> str``: one ``combinator-hello.v1`` document (JSON text): this release (name, version), the instruction
  pack it runs (name, version, digest), the digest of the published contract it validates against, ``tier:
  "cheapest"`` and the closed transformation vocabulary. Raises only when the package itself is broken (its pack or
  its contract copy unreadable), so a broken installation is never attached.
* ``combine(input_json, provider=None) -> str``: one ``combinator-output.v1`` document, or one
  ``combinator-refusal.v1`` document with its ``KIT-CB`` code (:func:`epinoic_combinator.runner.run`). Never raises.
  Without a provider it refuses (``provider_unavailable``): this release holds no live provider, and which model a
  provider calls is its owner's configuration, never this package's.

The service validates both as untrusted data with its own port (``combinator_port.check_hello``, ``check_output``,
``check_refusal``) and relays an output through its hub, which checks the synthesis on its own.
"""
from __future__ import annotations

from typing import Any, Optional

from . import NAME, __version__
from .contract import load_contract
from .jsonio import canonical_json
from .pack import TIER, load_pack
from .providers import Provider
from .runner import run

__all__ = ["hello", "hello_document", "combine"]


def hello_document() -> dict:
    contract = load_contract()
    return {"schema": "epinoic.integration.combinator-hello.v1", "protocol": "epinoic.integration.v1", "port_version": contract.port_version,
            "combinator": {"name": NAME, "version": __version__}, "instruction_pack": load_pack().identity(),
            "contract_sha256": contract.sha256, "tier": TIER, "vocabulary": list(contract.transformations)}


def hello() -> str:
    return canonical_json(hello_document())


def combine(input_json: Any, provider: Optional[Provider] = None) -> str:
    return run(input_json, provider).text
