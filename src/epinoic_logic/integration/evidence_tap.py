"""The evidence tap (``integration/PROTOCOL.md`` section 2.8): the ``integration-sim`` profile only, on a loopback bind.

It writes each checks call's full evidence (receipts, outcomes, signed results, the FINAL audit, the delivery decision,
the routing admission and the verdict) to ``EPINOIC_SIM_EVIDENCE_DIR/<request_id>.json``, so the simulation can compare
the exact website-path call with the reference harnesses. Every other profile refuses to start when the directory is
configured (``KIT-HS-012``, checked by the preflight and again here). No response ever carries the evidence.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

from .errors import IntegrationError
from .settings import LOOPBACK_HOSTS

__all__ = ["EvidenceTap"]

_NAME_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class EvidenceTap:
    def __init__(self, directory: str, *, profile: str, host: str) -> None:
        if profile != "integration-sim" or host not in LOOPBACK_HOSTS:
            raise IntegrationError("KIT-HS-012", "the evidence tap runs only in the integration-sim profile on a loopback bind")
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, request_id: str, evidence: Mapping[str, Any]) -> Path:
        if not _NAME_RE.match(request_id) or request_id in (".", ".."):
            raise ValueError("the evidence file is named by a protocol request id")
        path = self.directory / f"{request_id}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")
        os.replace(tmp, path)
        return path
