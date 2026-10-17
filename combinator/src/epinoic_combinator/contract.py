"""The published contract the combinator validates every message against, and the port rules its schemas cannot state.

The translator publishes the combinator port's contract (``integration/schemas/`` of the translator repository): the
JSON Schemas of the four messages (``combinator-input.v1``, ``combinator-output.v1``, ``combinator-hello.v1``,
``combinator-refusal.v1``), the synthesis contract's closed vocabularies (``synthesis-vocabulary.v1.json``, built from
the translator's ``integrity/contracts.py``: the transformations a synthesized claim may carry, the certainty order) and
the port's rules (``combinator-port.v1.json``: the refusal reasons and their codes, the size limits). The translator's
generator copies them into this package (``contract/``, byte for byte); never edit the copy, regenerate it.

:class:`Contract` loads that copy and checks a message the way the translator's port does
(``epinoic_logic.integration.combinator_port``), in the same order, with the same ``KIT-CB`` code: the schema first, then
the rules a schema cannot state (an output's transformation outside the closed vocabulary before anything else, the
request it answers, the instruction pack, the claims it cites, its size; a conflict naming a claim twice; a refusal's
code being its reason's). The sub-project's conformance tests run the translator's own vectors and generated documents
through both and require the same outcome. A check returns a :class:`Problem` or ``None``; it never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources
from typing import Any, Mapping, Optional

from .jsonio import JsonError, loads_strict, sha256_json, sha256_text
from .schema import SchemaUnsupported, Validator, shown

__all__ = ["CONTRACT_FILES", "ContractUnavailable", "Problem", "Contract", "load_contract"]

#: The files of the published contract, in the order the translator lists them (``combinator_port.CONTRACT_FILES``).
CONTRACT_FILES: tuple[str, ...] = (
    "combinator-input.v1.schema.json", "combinator-output.v1.schema.json", "combinator-hello.v1.schema.json",
    "combinator-refusal.v1.schema.json", "synthesis-vocabulary.v1.json", "combinator-port.v1.json",
)


class ContractUnavailable(RuntimeError):
    """The package's copy of the published contract is missing or unreadable: an installation defect."""


@dataclass(frozen=True)
class Problem:
    """Why a message is out of contract: its ``KIT-CB`` code, a closed reason and a detail that never echoes prose."""
    code: str
    reason: str
    detail: str


def _read(name: str) -> Any:
    try:
        data = resources.files("epinoic_combinator").joinpath("contract", name).read_bytes()
        return loads_strict(data)
    except (OSError, JsonError) as exc:
        raise ContractUnavailable(f"the published contract file {name} is missing or unreadable ({type(exc).__name__})") from None


class Contract:
    """The published contract (one immutable copy per process; :func:`load_contract`)."""

    def __init__(self, documents: Optional[Mapping[str, Any]] = None):
        docs = dict(documents) if documents is not None else {name: _read(name) for name in CONTRACT_FILES}
        if sorted(docs) != sorted(CONTRACT_FILES):
            raise ContractUnavailable("the published contract does not hold exactly its files")
        self.documents: dict[str, Any] = {name: docs[name] for name in CONTRACT_FILES}
        try:
            self.input = Validator(self.documents["combinator-input.v1.schema.json"])
            self.output = Validator(self.documents["combinator-output.v1.schema.json"])
            self.hello = Validator(self.documents["combinator-hello.v1.schema.json"])
            self.refusal = Validator(self.documents["combinator-refusal.v1.schema.json"])
        except SchemaUnsupported as exc:
            raise ContractUnavailable(f"the published contract uses a rule this release does not implement: {exc}") from None
        vocab = self.documents["synthesis-vocabulary.v1.json"]
        rules = self.documents["combinator-port.v1.json"]
        try:
            self.transformations: tuple[str, ...] = tuple(vocab["synthesized_claim_transformations"])
            self.meanings: dict[str, str] = {v: vocab["transformations"][v] for v in self.transformations}
            self.certainty: tuple[str, ...] = tuple(vocab["certainty"])
            self.certainty_rank: dict[str, int] = dict(vocab["certainty_rank"])
            self.refusal_reasons: dict[str, str] = dict(rules["refusal_reasons"])
            self.unread_input_reasons: frozenset[str] = frozenset(rules["unread_input_reasons"])
            self.ids_optional_reasons: frozenset[str] = frozenset(rules["ids_optional_reasons"])
            self.max_output_text_bytes: int = int(rules["max_output_text_bytes"])
            self.max_refusal_detail_chars: int = int(rules["max_refusal_detail_chars"])
            self.port_version: str = str(rules["port_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractUnavailable(f"the published contract's vocabulary or port rules are incomplete ({type(exc).__name__})") from None
        self.sha256 = sha256_json(self.documents)

    # ----------------------------------------------------------------------------------------------- helpers

    @staticmethod
    def _parsed(raw: Any) -> tuple[Any, Optional[str]]:
        if isinstance(raw, (str, bytes, bytearray)):
            try:
                return loads_strict(raw), None
            except JsonError as exc:
                return None, str(exc)
        return raw, None

    @staticmethod
    def _detail(text: str, limit: int = 300) -> str:
        text = " ".join(text.split()) or "out of contract"
        return text if len(text) <= limit else text[: limit - 3] + "..."

    # ----------------------------------------------------------------------------------------------- the four messages

    def check_input(self, raw: Any) -> tuple[Optional[dict], Optional[Problem]]:
        """A combinator input as the translator's ``check_input`` reads it (``KIT-CB-001``)."""
        data, err = self._parsed(raw)
        if err is not None:
            return None, Problem("KIT-CB-001", "input_not_json", self._detail(f"the input is not protocol JSON: {err}"))
        if not isinstance(data, dict):
            return None, Problem("KIT-CB-001", "input_invalid", "a combinator-port message is a JSON object")
        errors = self.input.errors(data, limit=1)
        if errors:
            return None, Problem("KIT-CB-001", "input_invalid", self._detail(f"the input does not validate: {errors[0]}"))
        if tuple(data["vocabulary"]) != self.transformations:
            return None, Problem("KIT-CB-001", "input_invalid", "the input's vocabulary is not the closed transformation vocabulary")
        ids = [c["claim_id"] for s in data["sources"] for c in s["claims"]]
        if len(set(ids)) != len(ids):
            return None, Problem("KIT-CB-001", "input_invalid", "two source claims share a claim id")
        for s in data["sources"]:
            for c in s["claims"]:
                if sha256_text(c["text"]) != c["claim_text_sha256"]:
                    return None, Problem("KIT-CB-001", "input_invalid", "a source claim's digest is not the digest of its text")
        return data, None

    def transformation_problem(self, data: Mapping[str, Any]) -> Optional[Problem]:
        """``KIT-CB-003``, decided before the rest of the output, as the translator's ``check_output`` decides it."""
        claims = data.get("claims")
        if isinstance(claims, list):
            for i, c in enumerate(claims):
                if isinstance(c, dict) and "transformation" in c and c["transformation"] not in self.transformations:
                    return Problem("KIT-CB-003", "transformation_unknown",
                                   self._detail(f"claims[{i}].transformation: {shown(c['transformation'])} is not one of "
                                                f"{', '.join(self.transformations)} (a category, never a description of the edit)"))
        return None

    def check_output(self, raw: Any, inp: Mapping[str, Any]) -> Optional[Problem]:
        """A combinator output for ``inp`` (a checked input) as the translator's ``check_output`` reads it."""
        data, err = self._parsed(raw)
        if err is not None:
            return Problem("KIT-CB-002", "output_not_json", self._detail(f"the output is not protocol JSON: {err}"))
        if not isinstance(data, dict):
            return Problem("KIT-CB-002", "output_not_object", "a combinator-port message is a JSON object")
        problem = self.transformation_problem(data)
        if problem is not None:
            return problem
        errors = self.output.errors(data, limit=1)
        if errors:
            return Problem("KIT-CB-002", "output_invalid", self._detail(f"the output does not validate: {errors[0]}"))
        for i, k in enumerate(data.get("conflicts", [])):
            if len(set(k["claim_ids"])) != len(k["claim_ids"]):
                return Problem("KIT-CB-002", "output_invalid", f"conflicts[{i}]: names a source claim twice (two distinct claims at least)")
        if data["ids"] != inp["ids"]:
            return Problem("KIT-CB-002", "output_invalid", "the output answers another request")
        if data["instruction_pack_sha256"] != inp["instruction_pack"]["sha256"]:
            return Problem("KIT-CB-005", "pack_mismatch", "the output was written under another instruction pack")
        known = {c["claim_id"] for s in inp["sources"] for c in s["claims"]}
        for where, ids in self._citations(data):
            unknown = [n for n, cid in enumerate(ids) if cid not in known]
            if unknown:
                return Problem("KIT-CB-004", "source_claim_unknown",
                               f"{where}[{unknown[0]}]: no source claim of the input has this id ({len(unknown)} unknown id(s) there)")
        size = sum(len(c["text"].encode("utf-8")) for c in data["claims"])
        if size > self.max_output_text_bytes:
            return Problem("KIT-CB-006", "output_too_large", f"the synthesis text is {size} UTF-8 bytes, more than {self.max_output_text_bytes}")
        return None

    @staticmethod
    def _citations(data: Mapping[str, Any]):
        for i, c in enumerate(data["claims"]):
            yield f"claims[{i}].source_claim_ids", c["source_claim_ids"]
        for i, d in enumerate(data.get("dropped", [])):
            yield f"dropped[{i}].source_claim_ids", d["source_claim_ids"]
        for i, k in enumerate(data.get("conflicts", [])):
            yield f"conflicts[{i}].claim_ids", k["claim_ids"]

    def check_hello(self, raw: Any) -> Optional[Problem]:
        data, err = self._parsed(raw)
        if err is not None or not isinstance(data, dict):
            return Problem("KIT-CB-002", "output_invalid", "the hello is not a protocol JSON object")
        errors = self.hello.errors(data, limit=1)
        if errors:
            return Problem("KIT-CB-002", "output_invalid", self._detail(f"the hello does not validate: {errors[0]}"))
        if tuple(data["vocabulary"]) != self.transformations:
            return Problem("KIT-CB-002", "output_invalid", "the hello's vocabulary is not the closed transformation vocabulary")
        return None

    def check_refusal(self, raw: Any, inp: Optional[Mapping[str, Any]] = None) -> Optional[Problem]:
        data, err = self._parsed(raw)
        if err is not None or not isinstance(data, dict):
            return Problem("KIT-CB-002", "output_invalid", "the refusal is not a protocol JSON object")
        errors = self.refusal.errors(data, limit=1)
        if errors:
            return Problem("KIT-CB-002", "output_invalid", self._detail(f"the refusal does not validate: {errors[0]}"))
        if self.refusal_reasons.get(data["reason"]) != data["code"]:
            return Problem("KIT-CB-002", "output_invalid", "the refusal's code is not the code of its reason")
        if data["reason"] not in self.ids_optional_reasons and (data.get("ids") is None) != (data["reason"] in self.unread_input_reasons):
            return Problem("KIT-CB-002", "output_invalid", "a refusal names the request it refuses unless the input could not be read")
        if inp is not None and data.get("ids") is not None and data["ids"] != inp["ids"]:
            return Problem("KIT-CB-002", "output_invalid", "the refusal answers another request")
        return None


_CONTRACT: Optional[Contract] = None


def load_contract() -> Contract:
    """The package's copy of the published contract, loaded once (:class:`ContractUnavailable` when it is unreadable)."""
    global _CONTRACT
    if _CONTRACT is None:
        _CONTRACT = Contract()
    return _CONTRACT
