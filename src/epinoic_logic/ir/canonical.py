"""Canonical serialization and digests.

The canonical form is JSON with sorted keys, no whitespace, UTF-8, and all
numeric literals already represented as strings by the schema. Two problems with
the same canonical form are the same problem; any difference changes the digest.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel


def canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json", exclude_none=True)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def problem_digest(problem: BaseModel) -> str:
    """Digest over the exact problem. Labels and notes ARE included: they are part of
    what a reviewer saw, so a changed gloss is a changed representation."""
    return sha256_hex(canonical_json(problem))
