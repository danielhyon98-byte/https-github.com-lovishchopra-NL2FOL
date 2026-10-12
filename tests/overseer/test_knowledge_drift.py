"""Drift tests: the knowledge pack and the code must say the same thing.

Each check is a function over a pack directory that returns a list of problems. It runs on the source pack (no
problem allowed) and, for the acceptance criterion "each drift test fails on a one-byte change", on a scratch copy with
one byte changed (a problem must be reported). The checks cover the generated files (schemas, manifest, the pinned
digest), the master prompt's header lines, the kinds table against ``KIND_CHECKS``, the rule-code cross-references,
and the facts about the system the documents state (status rule, scope sentence, statuses, lenses, field names, codes).
A drift failure is fixed by changing the contract or the documents deliberately and regenerating, never by editing a
generated file."""
from __future__ import annotations

import fnmatch
import json
import re
import tomllib
import typing
import unicodedata
from pathlib import Path
from typing import Callable

import pytest

import epinoic_logic
import epinoic_logic.channel.bus as bus
from epinoic_logic.channel import contracts as channel_contracts
from epinoic_logic.engine.results import VerificationResult
from epinoic_logic.engine.statuses import DEFINITIVE, VerificationStatus
from epinoic_logic.integrity import contracts as integrity_contracts
from epinoic_logic.ir import schema as ir_schema
from epinoic_logic.ir.schema import SourceRef
from epinoic_logic.overseer import consolidate as consolidate_mod
from epinoic_logic.overseer import dossier as dossier_mod
from epinoic_logic.overseer.codes import OVS_CODES
from epinoic_logic.overseer.pack import (
    MANIFEST_FILE, PACK_DIGESTS, build_manifest, header_lines, installed_pack, render_manifest, render_schemas,
)
from epinoic_logic.overseer.runner import DOSSIER_LABEL, render_dossier_block
from epinoic_logic.overseer.verdicts import (
    DOSSIER_VERSION, KIND_CHECKS, KIND_CODE_QUALIFIERS, LENSES, MAX_TEXT_CHARS, MODES, NO_DOSSIER_MARKER, STATUS_SPELLINGS, VERDICT_CONTRACT,
    VERDICT_ID_PATTERN, Accusation, AgentVerdict, EngineStatement, EvidenceItem, PackIdentity,
)
from epinoic_logic.translate import contracts as translate_contracts

from .test_knowledge_pack import SRC_PACK_DIR, copy_pack, pack_files

AGENT_DOCS = ("01-role-and-trust.md", "02-dossier.md", "03-inspection.md", "04-evidence.md", "05-verdict-format.md", "06-kinds-and-codes.md",
              "07-examples.md", "08-never.md", "09-when-unsure.md")
DISPLAY_NAMES = {"01-role-and-trust.md": "Role and trust", "02-dossier.md": "Dossier guide", "03-inspection.md": "Inspection",
                 "04-evidence.md": "Evidence rule", "05-verdict-format.md": "Verdict format", "06-kinds-and-codes.md": "Kinds and codes",
                 "07-examples.md": "Examples", "08-never.md": "Never", "09-when-unsure.md": "When unsure"}
RULE_PREFIX_DOC = {"T": "01-role-and-trust.md", "D": "02-dossier.md", "I": "03-inspection.md", "E": "04-evidence.md", "V": "05-verdict-format.md",
                   "K": "06-kinds-and-codes.md", "X": "07-examples.md", "N": "08-never.md", "U": "09-when-unsure.md"}
REPO = Path(epinoic_logic.__file__).resolve().parent.parent.parent


def read(d: Path, name: str) -> str:
    return (d / name).read_text(encoding="utf-8")


def manifest_of(d: Path) -> dict:
    return json.loads(read(d, MANIFEST_FILE))


def body_lines(text: str) -> list[str]:
    """The lines of a document without its footer line."""
    lines = text.rstrip("\n").split("\n")
    return lines[:-1] if lines and lines[-1].startswith("Pack version ") else lines


# ============================================================================================ the checks
def problems_schemas(d: Path) -> list[str]:
    return [f"{name} differs from the schema generated from the contract" for name, text in render_schemas().items()
            if (d / name).read_bytes() != text.encode("utf-8")]


def problems_manifest(d: Path) -> list[str]:
    m = manifest_of(d)
    rebuilt = build_manifest(pack_files(d), name=m.get("pack_name"), version=m.get("pack_version"))
    out = []
    if (d / MANIFEST_FILE).read_bytes() != render_manifest(rebuilt).encode("utf-8"):
        out.append("manifest.json differs from the manifest rebuilt from the files")
    if (m.get("verdict_contract"), m.get("dossier_version")) != (VERDICT_CONTRACT, DOSSIER_VERSION):
        out.append("the manifest's contract versions differ from VERDICT_CONTRACT and DOSSIER_VERSION")
    return out


def problems_pinned(d: Path) -> list[str]:
    m = manifest_of(d)
    pinned = PACK_DIGESTS.get((m["pack_name"], m["pack_version"]))
    return [] if pinned == m["pack_sha256"] else [f"PACK_DIGESTS pins {pinned} but the pack digest is {m['pack_sha256']}"]


def problems_header(d: Path) -> list[str]:
    m = manifest_of(d)
    first = tuple(read(d, "master_prompt.txt").split("\n")[:3])
    out = []
    if first != header_lines(m["pack_name"], m["pack_version"], m["verdict_contract"], m["dossier_version"]):
        out.append(f"master prompt header lines {first} differ from the manifest")
    if first != header_lines(m["pack_name"], m["pack_version"], VERDICT_CONTRACT, DOSSIER_VERSION):
        out.append("master prompt header lines differ from the code's contract constants")
    return out


def kinds_table(d: Path) -> list[tuple[str, tuple[str, ...], dict]]:
    """``(kind, codes, {code: qualifier})`` rows of Kinds and codes §3, in order."""
    text = read(d, "06-kinds-and-codes.md")
    section = text.split("## 3. The accusation kinds", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.split("\n"):
        m = re.match(r"^\| `([a-z_]+)` \| .* \| ([^|]+) \|$", line)
        if not m:
            continue
        col = m.group(2).strip()
        codes = tuple(re.findall(r"OVS-[A-Z]+-\d{3}", col))
        quals = {c: q for c, q in re.findall(r"(OVS-[A-Z]+-\d{3}) \((INT-[A-Z]+-\d{3})\)", col)}
        if not codes and not col.startswith("none"):
            codes = ("<unparsed>",)
        rows.append((m.group(1), codes, quals))
    return rows


def problems_kinds(d: Path) -> list[str]:
    rows = kinds_table(d)
    out = []
    if [(k, c) for k, c, _ in rows] != list(KIND_CHECKS.items()):
        out.append("the Kinds and codes table differs from KIND_CHECKS (kinds and codes, in order)")
    quals = {(k, c): (q,) for k, _cs, qs in rows for c, q in qs.items()}
    if quals != dict(KIND_CODE_QUALIFIERS):
        out.append("the qualified codes of the table differ from KIND_CODE_QUALIFIERS")
    return out


_DEF_RE = re.compile(r"^\s*- \*\*([TDIEVKNUX])(\d{1,2}) ")
_CITE_RE = re.compile(r"(?<![A-Za-z0-9_+-])([TDIEVKNUX])(\d{1,2})(?![0-9])")
_NAMED_CITE_RE = re.compile(r"(Role and trust|Dossier guide|Inspection|Evidence rule|Verdict format|Kinds and codes|Never|When unsure),? ([TDIEVKNUX]\d{1,2})\b")
_SECTION_RE = re.compile(r"(?:(Role and trust|Dossier guide|Inspection|Evidence rule|Verdict format|Kinds and codes|Examples|Never|When unsure),? )?§(\d+)")


def problems_rule_codes(d: Path) -> list[str]:
    out = []
    defined: dict[str, list[str]] = {}
    texts = {name: read(d, name) for name in (*AGENT_DOCS, "master_prompt.txt")}
    for name in AGENT_DOCS:
        for line in texts[name].split("\n"):
            m = _DEF_RE.match(line)
            if m:
                defined.setdefault(m.group(1) + m.group(2), []).append(name)
    for code, docs in sorted(defined.items()):
        if len(docs) != 1:
            out.append(f"{code} is defined {len(docs)} times")
        elif docs[0] != RULE_PREFIX_DOC[code[0]]:
            out.append(f"{code} is defined in {docs[0]}, not in {RULE_PREFIX_DOC[code[0]]}")
    titles = {v: k for k, v in DISPLAY_NAMES.items()}
    for name, text in texts.items():
        body = "\n".join(body_lines(text))
        for m in _CITE_RE.finditer(body):
            if m.group(1) + m.group(2) not in defined:
                out.append(f"{name} cites {m.group(1) + m.group(2)}, which no document defines")
        for doc_name, code in _NAMED_CITE_RE.findall(body):
            if RULE_PREFIX_DOC[code[0]] != titles[doc_name]:
                out.append(f"{name} cites '{doc_name} {code}', but {code} belongs to {RULE_PREFIX_DOC[code[0]]}")
        for doc_name, num in _SECTION_RE.findall(body):
            target = titles[doc_name] if doc_name else name
            if not re.search(rf"^## {num}\. ", texts[target], re.M):
                out.append(f"{name} cites §{num} of {target}, which has no such section")
        for num in re.findall(r"Example (\d+)\b", body):
            if not re.search(rf"^## \d+\. Example {num}: ", texts["07-examples.md"], re.M):
                out.append(f"{name} cites Example {num}, which does not exist")
    return out


def problems_titles_and_footers(d: Path) -> list[str]:
    m = manifest_of(d)
    out = []
    prompt = read(d, "master_prompt.txt")
    listed = re.findall(r"^\d+\. (.+) \((\d{2}-[a-z-]+\.md)\): ", prompt, re.M)
    if [(t, f) for t, f in listed] != [(DISPLAY_NAMES[f], f) for f in m["system_order"][1:]]:
        out.append("the master prompt's list of documents differs from the system order and the display names")
    for name in m["system_order"][1:]:
        text = read(d, name)
        if not text.startswith(f"# {DISPLAY_NAMES[name]}\n"):
            out.append(f"{name} does not open with its display name")
        if not text.startswith(f"# {DISPLAY_NAMES[name]}\n\n## 1. Scope\n"):
            out.append(f"{name} does not open with its Scope section")
        last = text.rstrip("\n").split("\n")[-1]
        if not re.fullmatch(rf"Pack version {re.escape(m['pack_version'])} · {re.escape(m['pack_name'])} · .+", last):
            out.append(f"{name}'s footer does not name pack {m['pack_name']} {m['pack_version']}")
        if "Common mistakes" not in text and name != "07-examples.md":
            out.append(f"{name} has no Common mistakes table")
    return out


def _backticked(text: str) -> list[str]:
    return re.findall(r"`([^`\n]+)`", text)


def problems_facts(d: Path) -> list[str]:
    """What the documents state about the system, against the code that implements it."""
    out = []
    prompt, dossier_doc, insp, verdict_doc, kinds, unsure = (read(d, n) for n in (
        "master_prompt.txt", "02-dossier.md", "03-inspection.md", "05-verdict-format.md", "06-kinds-and-codes.md", "09-when-unsure.md"))
    # the channel's status rule (Inspection I2): the blocking prefixes, in the channel's order
    i2 = re.search(r"code that starts with one of: (.+)\.\n", insp)
    if i2 is None or tuple(_backticked(i2.group(1))) != tuple(bus._BLOCKING_PREFIXES):
        out.append("Inspection I2's blocking prefixes differ from the channel's _BLOCKING_PREFIXES")
    # the scope sentence every non-request receipt ends with
    for name, text in (("02-dossier.md", dossier_doc), ("03-inspection.md", insp)):
        if f'"{bus._SCOPE_TAIL}"' not in text:
            out.append(f"{name} does not quote the channel's scope sentence exactly")
    # definitive statuses (Dossier guide D16) and the spelling list (Verdict format V19)
    d16 = re.search(r"Only six statuses are definitive: (.+?)\. None of them.*?Every other status \((.+?)\) is a non-result", dossier_doc, re.S)
    if d16 is None or set(re.findall(r"[A-Z_]{4,}", d16.group(1))) != {s.value for s in DEFINITIVE}:
        out.append("Dossier guide D16's definitive statuses differ from engine.statuses.DEFINITIVE")
    elif set(re.findall(r"[A-Z_]{4,}", d16.group(2))) != {s.value for s in VerificationStatus} - {s.value for s in DEFINITIVE}:
        out.append("Dossier guide D16's non-results differ from the other engine statuses")
    v19 = re.search(r"\*\*V19 Status spelling\.\*\* (.+)\n", verdict_doc)
    if v19 is None or tuple(_backticked(v19.group(1).split("exactly as in `results`:", 1)[-1])) != STATUS_SPELLINGS:
        out.append("Verdict format V19's status spellings differ from STATUS_SPELLINGS")
    # lenses and modes
    if tuple(re.findall(r"^LENS ([a-z_]+):", prompt, re.M)) != LENSES:
        out.append("the master prompt's LENS lines differ from LENSES")
    if tuple(re.findall(r"^MODE ([a-z]+):", prompt, re.M)) != MODES:
        out.append("the master prompt's MODE lines differ from MODES")
    d4 = dossier_doc.split("**D4 Where to start.**", 1)[1].split("- **D5", 1)[0]
    if tuple(re.findall(r"^  - `([a-z_]+)`:", d4, re.M)) != LENSES:
        out.append("Dossier guide D4's lenses differ from LENSES")
    # the data block the runner sends
    for line in (f"<<<DATA {DOSSIER_LABEL}>>>", f"<<<END {DOSSIER_LABEL}>>>"):
        if line not in prompt or line not in render_dossier_block({"x": 1}).split("\n"):
            out.append(f"the delimiter {line} differs between the master prompt and the runner")
    # limits the code enforces
    if f"longer than {dossier_mod.TRUNCATE_AT:,} characters" not in dossier_doc:
        out.append("Dossier guide D11's truncation length differs from TRUNCATE_AT")
    if f"At most {MAX_TEXT_CHARS:,} characters" not in verdict_doc or f"at most {MAX_TEXT_CHARS} characters" not in verdict_doc:
        out.append("Verdict format's statement and notes bound differs from MAX_TEXT_CHARS")
    vid_max = re.search(r"\{1,(\d+)\}", VERDICT_ID_PATTERN).group(1)
    if f"at most {vid_max} characters" not in verdict_doc:
        out.append("Verdict format V4's verdict id bound differs from the verdict contract")
    # the verdict skeleton names exactly the contract's fields
    skeleton = verdict_doc.split("## 3. The skeleton", 1)[1].split("```", 2)[1]
    fields = set(re.findall(r'"([a-z_0-9]+)":', skeleton))
    expected = set(AgentVerdict.model_fields) | set(Accusation.model_fields) | set(EvidenceItem.model_fields) | set(EngineStatement.model_fields)
    expected |= set(PackIdentity.model_fields)
    if fields != expected:
        out.append(f"the verdict skeleton's fields differ from the contract: {sorted(fields ^ expected)}")
    # the copied header (Dossier guide D2) is what the intake checks
    d2 = dossier_doc.split("**D2 Copy the header.**", 1)[1].split("- **D3", 1)[0]
    header_fields = [c for c in re.findall(r"^\| [^|]+ \| `([a-z_0-9]+)` \|$", d2, re.M)]
    if sorted(header_fields) != sorted(["contract", "pack", "agent_id", "task_id", "dossier_sha256", "lens"]):
        out.append("Dossier guide D2's copied header differs from the six fields the intake checks")
    # the dossier's shape (Dossier guide §3, §7, D7, D9)
    glance = dossier_doc.split("## 3. The dossier at a glance", 1)[1].split("```", 2)[1]
    if set(re.findall(r'^  "([a-z_0-9]+)":', glance, re.M)) != set(dossier_mod.Dossier.model_fields):
        out.append("the dossier at a glance differs from the Dossier contract's top-level fields")
    table = dossier_doc.split("Each entry of `transfers` has these fields:", 1)[1].split("**The payloads you will meet.**", 1)[0]
    if {t for row in re.findall(r"^\| (`[^|]+`) \|", table, re.M) for t in _backticked(row)} != set(dossier_mod.DossierTransfer.model_fields):
        out.append("the transfer field table differs from DossierTransfer")
    kinds_row = re.search(r"^\| `kind` \| (.+) \|$", table, re.M)
    if kinds_row is None or tuple(_backticked(kinds_row.group(1))) != typing.get_args(dossier_mod.TransferKind):
        out.append("the transfer kinds differ from the dossier's TransferKind")
    d7 = dossier_doc.split("**D7 Results.**", 1)[1].split("- **D8", 1)[0]
    d7_fields = set(_backticked(d7.split("maps each `result_id` to:", 1)[1].split("A result id cited", 1)[0])) - set(dossier_mod.DossierBinding.model_fields)
    if d7_fields != set(dossier_mod.DossierResult.model_fields):
        out.append(f"Dossier guide D7 differs from DossierResult: {sorted(d7_fields ^ set(dossier_mod.DossierResult.model_fields))}")
    d9 = dossier_doc.split("**D9 Index.**", 1)[1].split("- **D10", 1)[0]
    d9_types = re.search(r"`type` \((.+?)\)", d9)
    if d9_types is None or tuple(_backticked(d9_types.group(1))) != typing.get_args(dossier_mod.IndexType):
        out.append("Dossier guide D9's index types differ from IndexType")
    receipt = dossier_doc.split("| `receipt` |", 1)[1].split("\n", 1)[0]
    if tuple(_backticked(receipt)) != dossier_mod.RECEIPT_FIELDS:
        out.append("the receipt fields of the transfer table differ from RECEIPT_FIELDS")
    # the "no dossier" object (When unsure U1)
    u1 = re.search(r"```json\n(.+?)\n\s*```", unsure, re.S)
    if u1 is None or json.loads(u1.group(1)) != dict(NO_DOSSIER_MARKER):
        out.append("When unsure U1's object differs from NO_DOSSIER_MARKER")
    # the codes that record an agent's accusations (Kinds and codes §7)
    agent_rows = re.findall(r"^\| (OVS-AGENT-\d{3}) \|", kinds, re.M)
    if agent_rows != sorted(c for c in OVS_CODES if c.startswith("OVS-AGENT-")):
        out.append("Kinds and codes §7 differs from the OVS-AGENT codes")
    return out


def _source_text() -> str:
    pkg = Path(epinoic_logic.__file__).resolve().parent
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(pkg.rglob("*.py")))


def problems_codes(d: Path, source: str) -> list[str]:
    """Every OVS code the pack names exists; every INT and branch code it names is raised somewhere in the package."""
    out = []
    families = {c.rsplit("-", 1)[0] for c in OVS_CODES}
    for name in (*AGENT_DOCS, "master_prompt.txt"):
        text = read(d, name)
        for code in sorted(set(re.findall(r"OVS-[A-Z]+-\d{3}", text))):
            if code not in OVS_CODES:
                out.append(f"{name} names {code}, which is not an OVS code")
        for fam in sorted(set(re.findall(r"(OVS-[A-Z]+)-\*", text))):
            if fam not in families:
                out.append(f"{name} names the family {fam}-*, which does not exist")
        for code in sorted(set(re.findall(r"\b(?:INT|CORE|HI|ES|GEN)-[A-Z]+-\d{3}\b", text))):
            if f'"{code}"' not in source and f"'{code}'" not in source:
                out.append(f"{name} names {code}, which no module of the package raises")
        for fam in sorted(set(re.findall(r"\b(INT-[A-Z]+)-\*", text))):
            if f'"{fam}-' not in source:
                out.append(f"{name} names the family {fam}-*, which the package does not use")
    return out


def _known_names() -> set[str]:
    models = [dossier_mod.Dossier, dossier_mod.DossierTransfer, dossier_mod.DossierReceipt, dossier_mod.DossierResult, dossier_mod.DossierBinding,
              dossier_mod.DossierParty, dossier_mod.DossierPoolEntry, dossier_mod.DossierLinks, dossier_mod.ForwardLink, dossier_mod.PeerDocumentLink,
              dossier_mod.SynthesisCitation, dossier_mod.IndexEntry, dossier_mod.DossierAuditor, dossier_mod.DossierLimits, dossier_mod.TruncatedField,
              dossier_mod.DossierTask, AgentVerdict, Accusation, EvidenceItem, EngineStatement, PackIdentity,
              channel_contracts.TaskRequest, channel_contracts.RequestItem, channel_contracts.Constraint, channel_contracts.TransmissionReceipt,
              channel_contracts.CoverageRecord, channel_contracts.ConstraintResult, integrity_contracts.WorkPlan, integrity_contracts.Synthesis,
              integrity_contracts.SynthesizedClaim, integrity_contracts.LedgerEntry, integrity_contracts.ConflictRecord,
              integrity_contracts.IntegrityFinding, translate_contracts.SpecialistReport, translate_contracts.ClaimRecord,
              translate_contracts.SuppliedText, translate_contracts.TranslationResult, translate_contracts.ClaimVerificationOutcome, SourceRef,
              VerificationResult,
              # translator oversight: the translation and its formal problem, which the documents teach the agent to read
              dossier_mod.TranslationLink, translate_contracts.EligibilityDecision, translate_contracts.Interpretation,
              translate_contracts.AmbiguityFlag, translate_contracts.AtomGloss, translate_contracts.GroundingCheck, translate_contracts.ProviderInfo,
              ir_schema.Problem, ir_schema.Symbol, ir_schema.Assertion, ir_schema.Grounding,
              # consolidation (design section 19): the consolidations an informed dossier shows
              dossier_mod.DossierConsolidation, dossier_mod.ConsolidationGroup, dossier_mod.ConsolidationMember, dossier_mod.ConsolidationCheck,
              dossier_mod.ConsolidationExcluded, dossier_mod.ConsolidationConflict, dossier_mod.ConsolidationRepeat, dossier_mod.ConsolidationAdvisory]
    names: set[str] = set()
    for m in models:
        names |= set(m.model_fields)
    values = set(KIND_CHECKS) | set(LENSES) | set(MODES) | set(typing.get_args(dossier_mod.TransferKind)) | set(typing.get_args(dossier_mod.IndexType))
    values |= {r.value for r in integrity_contracts.AgentRole}
    # the IR's expression nodes (their fields and operators), grounding kinds and query kinds (Dossier guide D22)
    for node in vars(ir_schema).values():
        if isinstance(node, type) and "op" in getattr(node, "model_fields", {}):
            values |= set(typing.get_args(node.model_fields["op"].annotation))
            names |= set(node.model_fields)
    values |= set(typing.get_args(ir_schema.GroundingKind)) | set(typing.get_args(ir_schema.QueryKind))
    values |= set(typing.get_args(consolidate_mod.GroupBasis)) | set(typing.get_args(consolidate_mod.Relation))
    for model, field in ((integrity_contracts.SynthesizedClaim, "transformation"), (integrity_contracts.SynthesizedClaim, "certainty"),
                         (integrity_contracts.SynthesizedClaim, "materiality"), (translate_contracts.ClaimRecord, "claim_role"),
                         (channel_contracts.TransmissionReceipt, "direction")):
        ann = model.model_fields[field].annotation
        for arg in typing.get_args(ann) or ():
            values |= {a for a in (typing.get_args(arg) or (arg,)) if isinstance(a, str)}
            if isinstance(arg, type) and hasattr(arg, "__members__"):
                values |= {m.value for m in arg}
        if isinstance(ann, type) and hasattr(ann, "__members__"):
            values |= {m.value for m in ann}
    # the payload names a document refers to by contract (``synthesis.conflicts``) and JSON literals
    return names | values | {"error", "warning", "info", "true", "false", "null", "synthesis", "request", "report", "_"}


def problems_field_names(d: Path) -> list[str]:
    """Every backticked snake_case name the documents use is a field or a value of a contract (no invented field)."""
    known = _known_names()
    out = []
    for name in AGENT_DOCS:
        for tok in sorted(set(_backticked(read(d, name)))):
            for part in tok.split("."):
                if re.fullmatch(r"[a-z]\d+", part):
                    continue  # an example identifier value (a1, a2, ...), not a field name
                if re.fullmatch(r"[a-z_][a-z0-9_]*", part) and part not in known:
                    out.append(f"{name} names `{tok}`, which is no field or value of the contracts")
    return out


_FORBIDDEN_NAMES = re.compile(r"(?i)\b(claude|anthropic|openai|chatgpt|gpt-?\d|gemini|llama|mistral|haiku|sonnet|opus|deepseek|qwen|session_[0-9a-z]{6,})\b")
_SECRET_SHAPES = re.compile(r"(sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----|AKIA[0-9A-Z]{16}|xox[baprs]-[A-Za-z0-9-]{10,})")


def _invisible(text: str) -> list[str]:
    """Control, format, line/paragraph separator, non-plain space, private-use and surrogate characters (a line feed
    excepted): characters a reader cannot see, or that some readers take for a line break."""
    return sorted({f"U+{ord(c):04X}" for c in text if c != "\n" and (unicodedata.category(c) in ("Cc", "Cf", "Zl", "Zp", "Co", "Cs")
                                                                     or (unicodedata.category(c) == "Zs" and c != " "))})


def problems_hygiene(d: Path) -> list[str]:
    out = []
    for e in sorted(d.iterdir()):
        data = e.read_bytes()
        text = data.decode("utf-8")
        if data.startswith(b"\xef\xbb\xbf") or b"\r" in data or not data.endswith(b"\n") or data.endswith(b"\n\n"):
            out.append(f"{e.name}: not UTF-8 text with LF line endings ending in exactly one newline")
        if _invisible(text):
            out.append(f"{e.name} holds invisible or line-breaking characters {_invisible(text)}")
        if _FORBIDDEN_NAMES.search(text):
            out.append(f"{e.name} names a model, a vendor or a session: {_FORBIDDEN_NAMES.search(text).group(0)!r}")
        if _SECRET_SHAPES.search(text):
            out.append(f"{e.name} holds something shaped like a credential")
    return out


CHECKS: dict[str, Callable[[Path], list[str]]] = {
    "schemas": problems_schemas, "manifest": problems_manifest, "pinned": problems_pinned, "header": problems_header, "kinds": problems_kinds,
    "rule_codes": problems_rule_codes, "titles_and_footers": problems_titles_and_footers, "facts": problems_facts,
    "codes": lambda d: problems_codes(d, _source_text()), "field_names": problems_field_names, "hygiene": problems_hygiene,
}


# ============================================================================================ the source pack has no drift
@pytest.mark.parametrize("check", sorted(CHECKS))
def test_the_source_pack_has_no_drift(check):
    assert CHECKS[check](SRC_PACK_DIR) == []


def test_pack_digests_pin_the_installed_pack():
    pack = installed_pack()
    assert PACK_DIGESTS[(pack.identity.name, pack.identity.version)] == pack.identity.sha256 == manifest_of(SRC_PACK_DIR)["pack_sha256"]
    assert pack.manifest.verdict_contract == VERDICT_CONTRACT and pack.manifest.dossier_version == DOSSIER_VERSION


def test_the_kinds_table_parses_every_kind():
    rows = kinds_table(SRC_PACK_DIR)
    assert len(rows) == len(KIND_CHECKS) == 23 and rows[-1] == ("other", (), {})
    assert ("translation_unfaithful", (), {}) in rows and ("translation_circular", ("OVS-TRN-006",), {}) in rows
    assert ("figure_changed", ("OVS-FID-003", "OVS-SYN-002"), {"OVS-SYN-002": "INT-LEDGER-023"}) in rows


def test_every_rule_code_is_defined_once():
    text = {n: read(SRC_PACK_DIR, n) for n in AGENT_DOCS}
    defs = [m.group(1) + m.group(2) for n in AGENT_DOCS for line in text[n].split("\n") if (m := _DEF_RE.match(line))]
    assert len(defs) == len(set(defs)) and {c[0] for c in defs} == set(RULE_PREFIX_DOC)
    nums = {p: sorted(int(c[1:]) for c in defs if c[0] == p) for p in RULE_PREFIX_DOC}
    # the ranges design section 17.3 declares; every family but Inspection is numbered without gaps. The consolidation
    # stage (design section 19) added T13-T14, D24-D27, K7, N13, U11 and the consolidation checks I82-I89.
    for prefix, last in {"T": 14, "D": 27, "E": 15, "V": 20, "K": 7, "X": 3, "N": 13, "U": 11}.items():
        assert nums[prefix] == list(range(1, last + 1)), prefix
    assert nums["I"][0] == 1 and nums["I"][-1] == 89
    assert [n for n in nums["I"] if 70 <= n < 82] == list(range(70, 82))  # the translation checks, I70 to I81
    assert [n for n in nums["I"] if n >= 82] == list(range(82, 90))  # the consolidation and repeated-fault checks, I82 to I89


def test_package_data_ships_every_pack_file():
    conf = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = conf["tool"]["setuptools"]["package-data"]["epinoic_logic"]
    for pattern in ("overseer/knowledge/*/*.txt", "overseer/knowledge/*/*.md", "overseer/knowledge/*/*.json"):
        assert pattern in patterns
    for e in SRC_PACK_DIR.iterdir():
        rel = f"overseer/knowledge/{SRC_PACK_DIR.name}/{e.name}"
        assert any(fnmatch.fnmatch(rel, p) for p in patterns), rel


def test_line_endings_are_pinned_for_checkouts():
    attrs = Path(SRC_PACK_DIR).parent / ".gitattributes"
    assert attrs.read_text() == "* -text\n"


# ============================================================================================ each check fails on a one-byte change
def _swap(d: Path, name: str, old: str, new: str) -> None:
    data = (d / name).read_bytes()
    assert old.encode() in data, (name, old)
    assert len(old.encode()) == len(new.encode())  # one byte changed, size kept
    (d / name).write_bytes(data.replace(old.encode(), new.encode(), 1))


#: The size of the manifest's first file, read from the source manifest (the pack's documents change; the one-byte
#: change of the manifest is to that number's last bit, so the length is kept).
_FIRST_BYTES = manifest_of(SRC_PACK_DIR)["files"][0]["bytes"]

ONE_BYTE = {
    "schemas": ("verdict.schema.json", '"title": "Accusation Id"', '"title": "Accusation Ie"'),
    "manifest": (MANIFEST_FILE, f'"bytes": {_FIRST_BYTES}', f'"bytes": {_FIRST_BYTES ^ 1}'),
    "kinds": ("06-kinds-and-codes.md", "OVS-CUST-004, OVS-CUST-006 |", "OVS-CUST-004, OVS-CUST-007 |"),
    "header": ("master_prompt.txt", "DOSSIER VERSION: 1.0", "DOSSIER VERSION: 1.1"),
    "rule_codes": ("03-inspection.md", "(I3)", "(I0)"),
    "titles_and_footers": ("08-never.md", "Pack version 1.0 · overseer-knowledge-docs", "Pack version 1.1 · overseer-knowledge-docs"),
    "facts": ("03-inspection.md", "`INT-LEDGER-008`", "`INT-LEDGER-009`"),
    "codes": ("06-kinds-and-codes.md", "INT-GLOSSARY-001", "INT-GLOSSARY-901"),
    "field_names": ("02-dossier.md", "`cited_result_ids`", "`cited_result_idz`"),
    "hygiene": ("01-role-and-trust.md", "You decide nothing.", "You decide nothing\r"),
}


@pytest.mark.parametrize("check", sorted(ONE_BYTE))
def test_each_check_fails_on_a_one_byte_change(tmp_path, check):
    d = copy_pack(tmp_path)
    assert CHECKS[check](d) == []
    _swap(d, *ONE_BYTE[check])
    assert CHECKS[check](d) != []


def test_the_pinned_digest_check_fails_when_any_byte_moves_the_digest(tmp_path):
    from .test_knowledge_pack import remanifest
    d = copy_pack(tmp_path)
    _swap(d, "09-when-unsure.md", "Never resolve doubt", "Never resolve doubT")
    remanifest(d)
    assert problems_pinned(d) != [] and problems_manifest(d) == []


@pytest.mark.parametrize("variant", ["kind_reordered", "qualifier_dropped", "code_added"])
def test_the_kinds_check_sees_reordering_and_qualifiers(tmp_path, variant):
    d = copy_pack(tmp_path)
    text = read(d, "06-kinds-and-codes.md")
    if variant == "kind_reordered":
        a = next(l for l in text.split("\n") if l.startswith("| `replay_differs` |"))
        b = next(l for l in text.split("\n") if l.startswith("| `formal_status_wrong` |"))
        text = text.replace(a, "\0").replace(b, a).replace("\0", b)
    elif variant == "qualifier_dropped":
        text = text.replace("OVS-SYN-002 (INT-LEDGER-023)", "OVS-SYN-002")
    else:
        text = text.replace("| OVS-PEER-001 |", "| OVS-PEER-001, OVS-PEER-003 |")
    (d / "06-kinds-and-codes.md").write_text(text, encoding="utf-8")
    assert problems_kinds(d) != []


def test_a_duplicate_rule_definition_and_a_misattributed_citation_are_seen(tmp_path):
    d = copy_pack(tmp_path)
    text = read(d, "08-never.md").replace("- **N12 Never output anything but the verdict.**", "- **N11 Never output anything but the verdict.**")
    (d / "08-never.md").write_text(text, encoding="utf-8")
    assert any("defined 2 times" in p for p in problems_rule_codes(d))
    d2 = copy_pack(tmp_path / "b")
    (d2 / "04-evidence.md").write_text(read(d2, "04-evidence.md").replace("(Dossier guide D11)", "(Dossier guide I11)"), encoding="utf-8")
    assert any("belongs to" in p for p in problems_rule_codes(d2))


@pytest.mark.parametrize("char", ["\u2028", "\u2029", "\u0085", "\u200b", "\u00a0", "\t", "\ue000"])
def test_an_invisible_character_in_the_pack_is_seen(tmp_path, char):
    d = copy_pack(tmp_path)
    (d / "README.md").write_text(read(d, "README.md").replace("JSON escapes", "JSON" + char + "escapes", 1), encoding="utf-8")
    assert any("invisible" in p for p in problems_hygiene(d))


def test_a_model_name_or_a_credential_in_the_pack_is_seen(tmp_path):
    d = copy_pack(tmp_path)
    (d / "README.md").write_text(read(d, "README.md") + "Tested with Sonnet.\n", encoding="utf-8")
    assert problems_hygiene(d) != []
    d2 = copy_pack(tmp_path / "b")
    (d2 / "README.md").write_text(read(d2, "README.md") + "key: sk-" + "a" * 24 + "\n", encoding="utf-8")
    assert problems_hygiene(d2) != []
