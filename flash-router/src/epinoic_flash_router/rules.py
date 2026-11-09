"""The flash router's rules and cost data, loaded from its versioned DATA files (``data/``): the router is edited,
re-tuned and released by changing these files, never the translator, the engine, the STEM support or the overseer.

``data/MANIFEST.json`` names the current rules file and the current cost-data file and records, for every released
file, its version, its release and its digest. A document's digest is the SHA-256 of its canonical JSON (keys sorted by
code point, no whitespace, non-ASCII raw): the rules digest and the cost-data digest are part of the router's identity
(its hellos and every plan), so a change of either is visible to the service, to the overseer pool and to every
recorded review. The sub-project's tests hold every released file to its recorded digest (a released file never
changes) and the current files to the manifest.

What the current rules file holds (``rules-4.json``, 0.4.0; ``rules-3.json`` of 0.3.0 has the same sections): the rules
in words (``rules``: the flash decision maker's rules D1 to D7, the port rules 1 to 7 and the pool rules P1 to P8), the
port planner's parameters (``parameters``:
max_parts, max_reviews, hard_max_instances, context_max_bytes), the pool planner's thresholds and batch size (``pool``:
escalated_reviewers, baseline_reviewers, record_weight, batch_size, and for a combined answer source_reviewers and
merged_reviewers), the flash decision maker's own section (``decision``: its two methods and the order its choice
follows), the agreement signals the port rules read (``signals``), the features each planner reads (``features``) and the
method table (``methods``). The cost data (``cost-data-4.json``) holds the decision maker's planning estimates (the
instance budget, the output budget, the seconds a call, the dossier estimate) and the sizes of the system text of every
composition of the knowledge pack the overseer sends (pack 2.1, which ``recorded.system_text_pack`` names) and of its
dossiers: estimates and sizes, never a price or a latency, and no model.

A rules/2 document (``rules-2.json``, 0.2.0) has no ``decision`` section and a ``split_words`` parameter: the planners
plan it by its own rules (an output longer than split_words words is divided), with 0.2.0's cost model
(``cost-data-2.json``), so a data directory holding the released 0.2.0 files plans exactly as 0.2.0 did.

Pure: the only file this module reads is a data directory's manifest and the two files it names, once, at load, with
the builtin ``open``; nothing here uses the network, a clock, randomness or a process. A data directory other than the
package's own (:class:`DataSet` with ``data_dir``) is how a re-tuned copy is tried before it is released.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Optional

__all__ = [
    "DATA_DIR", "DataSet", "DEFAULT", "MANIFEST", "RULES_DOCUMENT", "RULES", "PARAMETERS", "POOL", "SIGNALS", "FEATURES", "METHODS", "DECISION", "COMPOSITIONS",
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
    larger batch) loads, and the overseer's floor refuses what it plans below the floor. A rules/3 document carries the
    flash decision maker's ``decision`` section and the combined answer's pool parameters; a rules/2 document its
    ``split_words`` instead."""
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), str) or not doc["rules"].strip():
        raise ValueError("the rules file holds its rules in words (rules)")
    params, pool, signals, features, methods = (doc.get(k) for k in ("parameters", "pool", "signals", "features", "methods"))
    decision = doc.get("decision")
    if not isinstance(params, dict):
        raise ValueError("the rules file holds the port planner's parameters")
    for key in ("max_parts", "max_reviews", "hard_max_instances", "context_max_bytes") + (() if decision is not None else ("split_words",)):
        _count(params, key, "parameters")
    if not isinstance(pool, dict):
        raise ValueError("the rules file holds the pool planner's parameters")
    for key in ("escalated_reviewers", "baseline_reviewers", "record_weight") + (("source_reviewers", "merged_reviewers") if decision is not None else ()):
        _count(pool, key, "pool")
    _count(pool, "batch_size", "pool", optional=True)
    if decision is not None:
        if not isinstance(decision, dict) or decision.get("approaches") != {"in_depth": ["IN_DEPTH"], "duplication": ["SPLIT", "DUPLICATE", "N_FOLD"]}:
            raise ValueError("the decision section names the flash decision maker's two methods (approaches)")
        if decision.get("order") != ["tokens", "seconds", "calls", "method"]:
            raise ValueError("the decision section states the order its choice follows")
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


#: The compositions of the overseer's knowledge pack whose system text sizes the decision maker prices.
COMPOSITIONS = ("core", "core+stem", "core+translations", "core+stem+translations")


def _check_cost(doc: Any, *, decision: bool) -> None:
    if not isinstance(doc, dict) or not isinstance(doc.get("name"), str):
        raise ValueError("the cost-data file names itself")
    if not decision:
        for key in ("review_tokens_base", "chars_per_token", "seconds_per_instance"):
            _count(doc, key, "cost data", minimum=0 if key != "chars_per_token" else 1)
        return
    for key, minimum in (("chars_per_token", 1), ("output_tokens", 0), ("instance_budget_tokens", 1), ("seconds_per_call", 0)):
        _count(doc, key, "cost data", minimum=minimum)
    sizes = doc.get("system_text_chars")
    if not isinstance(sizes, dict) or set(sizes) != set(COMPOSITIONS):
        raise ValueError("the cost data records the system text size of every composition (system_text_chars)")
    for key in COMPOSITIONS:
        _count(sizes, key, "cost data.system_text_chars", minimum=0)
    dossier = doc.get("dossier")
    if not isinstance(dossier, dict):
        raise ValueError("the cost data holds the dossier estimate (dossier)")
    for key in ("base_chars", "chars_per_answer_char", "chars_per_translation"):
        _count(dossier, key, "cost data.dossier", minimum=0)


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
        _check_cost(self.cost_data, decision=self.rules_document.get("decision") is not None)
        self.rules: str = self.rules_document["rules"]
        self.parameters: dict = self.rules_document["parameters"]
        self.pool: dict = self.rules_document["pool"]
        self.signals: dict = self.rules_document["signals"]
        self.features: dict = self.rules_document["features"]
        self.methods: dict = self.rules_document["methods"]
        #: the flash decision maker's section (rules/3 and later), or None for a rules/2 document (its own rule 4 plans it)
        self.decision: Optional[dict] = self.rules_document.get("decision")
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
DECISION: Optional[dict] = DEFAULT.decision
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
