"""The flash router's rules and cost data, loaded from its versioned DATA files (``data/``): the router is edited,
re-tuned and released by changing these files, never the translator, the engine, the STEM support or the overseer.

``data/MANIFEST.json`` names the current rules file and the current cost-data file and records, for every released
file, its version, its release and its digest. A document's digest is the SHA-256 of its canonical JSON (keys sorted by
code point, no whitespace, non-ASCII raw): the rules digest and the cost-data digest are part of the router's identity
(its hellos and every plan), so a change of either is visible to the service, to the overseer pool and to every
recorded review. The sub-project's tests hold every released file to its recorded digest (a released file never
changes) and the current files to the manifest.

What the current rules file holds (``rules-2.json``): the rules in words (``rules``), the port planner's parameters
(``parameters``: split_words, max_parts, max_reviews, hard_max_instances, context_max_bytes), the pool planner's
thresholds and batch size (``pool``: escalated_reviewers, baseline_reviewers, record_weight, batch_size), the agreement
signals the port rules read (``signals``), the features each planner reads (``features``) and the method table
(``methods``). The cost data (``cost-data-2.json``) holds the port plan's planning estimates and the sizes the overseer
recorded for its knowledge pack and dossiers: estimates and sizes, never a price or a latency, and no model.

Pure: the only file this module reads is a data directory's manifest and the two files it names, once, at load, with
the builtin ``open``; nothing here uses the network, a clock, randomness or a process. A data directory other than the
package's own (:class:`DataSet` with ``data_dir``) is how a re-tuned copy is tried before it is released.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

__all__ = [
    "DATA_DIR", "DataSet", "DEFAULT", "MANIFEST", "RULES_DOCUMENT", "RULES", "PARAMETERS", "POOL", "SIGNALS", "FEATURES", "METHODS",
    "COST_MODEL", "canonical", "document_sha256", "rules_sha256", "cost_data_sha256", "RULES_SHA256", "COST_DATA_SHA256",
]


def _package_dir() -> str:
    path = __file__.replace("\\", "/")
    return path[: path.rfind("/")]


#: The package's own data directory.
DATA_DIR = _package_dir() + "/data"


def canonical(value: Any) -> str:
    """Canonical JSON (keys sorted by code point, no whitespace, non-ASCII raw): the form the service digests."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def document_sha256(document: Any) -> str:
    """The digest of a data document: SHA-256 of its canonical JSON."""
    return hashlib.sha256(canonical(document).encode("utf-8")).hexdigest()


def _no_duplicates(pairs: list) -> dict:
    out: dict = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"the data repeats the key {key!r}")
        out[key] = value
    return out


def _no_constant(name: str) -> Any:
    raise ValueError(f"the data holds {name}, which is not JSON")


def _read(data_dir: str, name: str) -> Any:
    if not isinstance(name, str) or not name.endswith(".json") or "/" in name or "\\" in name or name.startswith("."):
        raise ValueError(f"the manifest names {name!r}, which is not a data file of this directory")
    with open(data_dir.rstrip("/\\") + "/" + name, encoding="utf-8") as f:
        return json.load(f, object_pairs_hook=_no_duplicates, parse_constant=_no_constant)


def _count(doc: Mapping[str, Any], key: str, where: str, *, minimum: int = 1, optional: bool = False) -> None:
    value = doc.get(key)
    if optional and value is None:
        return
    if type(value) is not int or value < minimum:
        raise ValueError(f"{where}.{key} is an integer of at least {minimum}")


def _strings(value: Any, where: str) -> None:
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ValueError(f"{where} is a list of names")


def _check_rules(doc: Any) -> None:
    """The shape the planners read. The values themselves are the router's choice: a weakened file (fewer reviewers, a
    larger batch) loads, and the overseer's floor refuses what it plans below the floor."""
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), str) or not doc["rules"].strip():
        raise ValueError("the rules file holds its rules in words (rules)")
    params, pool, signals, features, methods = (doc.get(k) for k in ("parameters", "pool", "signals", "features", "methods"))
    if not isinstance(params, dict):
        raise ValueError("the rules file holds the port planner's parameters")
    for key in ("split_words", "max_parts", "max_reviews", "hard_max_instances", "context_max_bytes"):
        _count(params, key, "parameters")
    if not isinstance(pool, dict):
        raise ValueError("the rules file holds the pool planner's parameters")
    for key in ("escalated_reviewers", "baseline_reviewers", "record_weight"):
        _count(pool, key, "pool")
    _count(pool, "batch_size", "pool", optional=True)
    if not isinstance(signals, dict):
        raise ValueError("the rules file holds the port rules' agreement signals")
    for key in ("negative_statuses", "undecided_statuses", "stem_undecided_codes"):
        _strings(signals.get(key), f"signals.{key}")
    if not isinstance(features, dict):
        raise ValueError("the rules file holds the features each planner reads")
    for key in ("port", "port_combined", "pool", "pool_limits"):
        _strings(features.get(key), f"features.{key}")
    if not isinstance(methods, dict) or set(methods) != {"IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"}:
        raise ValueError("the rules file holds the method table of the four methods")


def _check_cost(doc: Any) -> None:
    if not isinstance(doc, dict) or not isinstance(doc.get("name"), str):
        raise ValueError("the cost-data file names itself")
    for key in ("review_tokens_base", "chars_per_token", "seconds_per_instance"):
        _count(doc, key, "cost data", minimum=0 if key != "chars_per_token" else 1)


class DataSet:
    """One data directory, loaded: its manifest, the current rules and cost-data documents and their digests.

    ``DataSet()`` is the package's own data; ``DataSet(data_dir)`` another directory with the same layout (a re-tuned
    copy being tried). ``ValueError`` (or ``OSError``) when the directory, its manifest or a file it names cannot be read
    or does not have the shape the planners read."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        self.data_dir = DATA_DIR if data_dir is None else str(data_dir)
        manifest = _read(self.data_dir, "MANIFEST.json")
        current = manifest.get("current") if isinstance(manifest, dict) else None
        if not isinstance(current, dict):
            raise ValueError("the manifest names its current rules and cost data")
        self.manifest: dict = manifest
        self.rules_file: str = current.get("rules")
        self.cost_data_file: str = current.get("cost_data")
        self.rules_document: dict = _read(self.data_dir, self.rules_file)
        self.cost_data: dict = _read(self.data_dir, self.cost_data_file)
        _check_rules(self.rules_document)
        _check_cost(self.cost_data)
        self.rules: str = self.rules_document["rules"]
        self.parameters: dict = self.rules_document["parameters"]
        self.pool: dict = self.rules_document["pool"]
        self.signals: dict = self.rules_document["signals"]
        self.features: dict = self.rules_document["features"]
        self.methods: dict = self.rules_document["methods"]
        self.rules_sha256: str = document_sha256(self.rules_document)
        self.cost_data_sha256: str = document_sha256(self.cost_data)


#: The package's own data, loaded once at import.
DEFAULT = DataSet()
MANIFEST: dict = DEFAULT.manifest
RULES_DOCUMENT: dict = DEFAULT.rules_document
RULES: str = DEFAULT.rules
PARAMETERS: dict = DEFAULT.parameters
POOL: dict = DEFAULT.pool
SIGNALS: dict = DEFAULT.signals
FEATURES: dict = DEFAULT.features
METHODS: dict = DEFAULT.methods
#: The current cost data (planning estimates and recorded sizes): the document its digest is taken of.
COST_MODEL: dict = DEFAULT.cost_data


def rules_sha256(rules: str = RULES, parameters: Mapping[str, int] = PARAMETERS, *, document: Optional[Mapping[str, Any]] = None) -> str:
    """The rules digest of ``document`` (the current rules document by default) with its words and its port parameters
    replaced by ``rules`` and ``parameters``: equal to :data:`RULES_SHA256` for the current document as it is."""
    doc = dict(RULES_DOCUMENT if document is None else document)
    doc["rules"] = rules
    doc["parameters"] = dict(parameters)
    return document_sha256(doc)


def cost_data_sha256(cost_model: Mapping[str, Any] = COST_MODEL) -> str:
    return document_sha256(dict(cost_model))


RULES_SHA256: str = DEFAULT.rules_sha256
COST_DATA_SHA256: str = DEFAULT.cost_data_sha256
