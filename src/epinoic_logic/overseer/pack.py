"""The overseer knowledge pack: loading, verifying and generating the one configuration an overseer agent has.

An overseer agent is configured ONLY by a versioned knowledge-document pack shipped as package data
(``overseer/knowledge/overseer-knowledge-docs-<version>/``): ``master_prompt.txt`` and the numbered documents (audience
``agent``, the system configuration), ``README.md`` (audience ``deployer``, never sent to a model), the generated
``verdict.schema.json`` and ``dossier.schema.json`` (audience ``machine``) and ``manifest.json``. The code alone decides
what a verdict is worth; the pack only configures what an agent writes (design ``docs/OVERSEER_DESIGN.md`` section 17).

**Trust anchor.** The digest pinned in this module (:data:`PACK_DIGESTS`), never the manifest: a manifest is
self-describing and unsigned, so an attacker who edits a document can recompute it. :func:`load_pack` checks every file
against the manifest AND the manifest's pack digest against the pinned one; a version this code does not pin is refused
unless the operator passes its exact identity in ``trusted``. A pinned ``(name, version)`` is never overridden by
``trusted``: a version, once pinned, never changes (section 17.12).

**The loader never executes, imports or evaluates anything from a pack.** It reads only regular files listed in the
manifest, with the extensions ``.txt``, ``.md`` and ``.json``, from a directory, a ``.zip`` read in place (never
extracted) or the installed package (``importlib.resources``). JSON is parsed strictly (duplicate keys and non-finite
numbers refused). Text is UTF-8 without a byte-order mark and without CR, so a checkout that rewrites line endings fails
loudly instead of changing digests silently. The first failed check raises :class:`PackError` and nothing is loaded.

Checks, in order (``PackError.reason``):

``manifest_missing``, ``manifest_invalid``, ``unsafe_path``, ``file_missing``, ``file_unlisted``, ``file_too_large``,
``file_encoding``, ``file_digest``, ``file_invalid``, ``pack_digest``, ``system_digest``, ``contract_mismatch``,
``unknown_pack``, ``digest_mismatch``, ``header_mismatch``.

**Generation** (maintainers; ``python -m epinoic_logic.overseer.export --refresh-source``): :func:`render_schemas` renders
``AgentVerdict`` and ``Dossier`` as JSON Schema (sorted keys, two-space indent, final newline, ``$id``
``urn:epinoic:overseer:verdict:1.0`` and ``urn:epinoic:overseer:dossier:1.0``); :func:`build_manifest` lists every file
but the manifest, sorted by path, with its audience, size and SHA-256, the contract versions, the system order and the
system digest, and ``pack_sha256 = sha256(canonical_json(manifest without pack_sha256))``. Generated files are never
edited by hand; the drift tests regenerate them and compare bytes.

**System text** (section 17.8, :func:`build_system_text`): for each path of ``system_order``, the separator line
(``system_separator`` with ``{path}`` replaced), a newline, the file text without its trailing newlines, and a newline;
the parts are joined with one blank line. The runner and the deployer README use this one rule, and ``system_sha256``
lets a deployer confirm a byte-identical configuration.

Deviations from ``docs/OVERSEER_DESIGN.md`` sections 17.4 and 17.6, listed as each stage requires:

* two refusal reasons are added: ``file_invalid`` (a listed ``.json`` file that is not one strict JSON object) and
  ``header_mismatch`` (the master prompt's ``PACK:``, ``VERDICT CONTRACT:`` and ``DOSSIER VERSION:`` lines differ from
  the manifest: an agent compares a dossier's pack with its ``PACK:`` line, When unsure U2). ``header_mismatch`` is
  checked last, so a changed version string is always ``unknown_pack`` (T20 d);
* a pack is flat: a listed path must be a bare file name of letters, digits, ``.``, ``_`` and ``-`` (not starting with a
  dot) with an allowed extension, otherwise ``unsafe_path``; every symlink in the pack (listed or not) is
  ``unsafe_path``; in a zip, an absolute, backslashed, drive-lettered or ``..`` entry, an entry outside the single root
  directory, a nested entry, a duplicate entry and an encrypted entry are ``unsafe_path``;
* the manifest's structure (unique paths sorted by path, the manifest not listed, the four required files present,
  audiences by the naming rule, ``system_order`` equal to the master prompt followed by the numbered documents in
  name order, one ``{path}`` in a one-line separator) is checked after path safety, so a listed ``../x`` reports
  ``unsafe_path``; a manifest that is not UTF-8, has a byte-order mark or a CR is ``manifest_invalid``;
* a path that is not a pack at all (no such path, a file that is not a zip archive) is ``manifest_missing``; a zip with
  more than 256 entries is ``file_too_large``; a corrupt zip entry (CRC or deflate error) is ``file_digest``;
* :class:`KnowledgePack` can be built only by this loader (direct construction raises ``TypeError``), keeps every file's
  bytes, and :meth:`KnowledgePack.verify` re-checks them in memory (the runner calls it).

Edits this stage made to the pack documents (each moves the pinned digest), only to remove drift its tests found:

* ``02-dossier.md`` (Dossier guide §7, the transfer field table): a row for ``created_at`` was added. The drift test of
  the table against the ``DossierTransfer`` contract found the field, which every dossier transfer carries, undescribed.
  No other drift was found in ``master_prompt.txt`` or documents ``01`` to ``09``; the 13 worked examples were consistent
  with their excerpts as written.

Edits the ``hook`` stage made to pack 1.0 for translator oversight (founder's requirement, design section 18; the pack
had not been released, so it was extended in place and its digest re-pinned, decision 33): the master prompt (step 4,
non-negotiable 4, the ``translation_fidelity`` LENS line, a WHEN IN DOUBT line); Role and trust T1, T3, T12; Dossier
guide (the lens, ``links.translations``, the outcome fields, a new §10 Translations with D21 to D23, renumbering Facts
and Common mistakes to §11 and §12); Inspection (a new §10 Translations with I70 to I81, Common mistakes now §11);
Evidence rule E9, E14; Verdict format V10; Kinds and codes (four translation kinds, OVS-TRN-007 under
``receipt_altered``, K6, the ``OVS-TRN-*`` family); Never N4, N6; When unsure U10; Examples 14 to 17 (a faithful
translation, a circular one, an invented figure, a flipped comparison) and three wrong-verdict rows. Schemas and the
manifest were regenerated with ``export --refresh-source``.

Edits the ``consolidation`` stage made to pack 1.0 (founder's requirement, design section 19; still unreleased, so extended
in place and re-pinned, decision 37): the master prompt (step 4 and a SEVERAL INSTANCES section); Role and trust (a new
§6 with T13, one of several instances, and T14, answers several agents gave to one input; Common mistakes now §7);
Dossier guide (``consolidations`` in the dossier at a glance, a new §11 Consolidations with D24 to D27, renumbering Facts
and Common mistakes to §12 and §13); Inspection (a new §11 with I82 to I89 on consolidations and repeated faults, Common
mistakes now §12); Kinds and codes K7 and the ``OVS-CONS-*`` and ``OVS-REP-*`` families; Never N13; When unsure U11;
Examples 18 and 19 (a consolidation whose repeated fault is already recorded; a fault repeated by a duplicated instance)
and two wrong-verdict rows; the deployer README's §8 Several instances. The dossier schema gained the optional
``consolidations`` section; it and the manifest were regenerated with ``export --refresh-source``.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import threading
import zipfile
import zlib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from types import MappingProxyType
from typing import Any, Collection, Iterable, Literal, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..ir.canonical import canonical_json, sha256_hex, strict_object_pairs
from .dossier import Dossier
from .verdicts import DOSSIER_VERSION, PACK_NAME_PATTERN, PACK_VERSION_PATTERN, SHA256_PATTERN, VERDICT_CONTRACT, AgentVerdict, PackIdentity

__all__ = [
    "PACK_NAME", "PACK_VERSION", "PACK_DIGESTS", "PACK_ERROR_REASONS", "PackError", "KnowledgePack", "PackManifest", "ManifestFile", "load_pack",
    "installed_pack", "installed_pack_dir", "accepted_identities", "build_system_text", "render_schemas", "build_manifest", "render_manifest",
    "manifest_pack_digest", "header_lines", "audience_of", "system_order_of", "pack_dir_name", "MANIFEST_FILE", "README_FILE", "MASTER_PROMPT_FILE",
    "VERDICT_SCHEMA_FILE", "DOSSIER_SCHEMA_FILE", "SCHEMA_FILES", "SCHEMA_IDS", "SYSTEM_SEPARATOR", "MANIFEST_VERSION", "MAX_FILE_BYTES", "MAX_PACK_BYTES",
    "MAX_PACK_FILES", "MAX_ZIP_ENTRIES", "ALLOWED_SUFFIXES", "KNOWLEDGE_DIR",
]

#: The pack this package ships and loads by default.
PACK_NAME = "overseer-knowledge-docs"
PACK_VERSION = "1.0"
#: The pack digest (manifest ``pack_sha256``) this code accepts, per ``(name, version)``. The trust anchor: a pack whose
#: digest differs is refused (``digest_mismatch``), whatever its manifest says. A new version is pinned here only after
#: ``export --refresh-source`` printed its digest; an older version stays pinned while its contracts are supported.
PACK_DIGESTS: Mapping[tuple[str, str], str] = MappingProxyType({
    (PACK_NAME, "1.0"): "668bd996ab5a67b95f35c5561d253443f9035ae8a8f77726fd834b2b00114193",
})

MANIFEST_VERSION = "1.0"
MANIFEST_FILE = "manifest.json"
README_FILE = "README.md"
MASTER_PROMPT_FILE = "master_prompt.txt"
VERDICT_SCHEMA_FILE = "verdict.schema.json"
DOSSIER_SCHEMA_FILE = "dossier.schema.json"
SCHEMA_FILES = (DOSSIER_SCHEMA_FILE, VERDICT_SCHEMA_FILE)
SCHEMA_IDS: Mapping[str, str] = MappingProxyType({
    VERDICT_SCHEMA_FILE: "urn:epinoic:overseer:verdict:" + VERDICT_CONTRACT.split("/", 1)[1],
    DOSSIER_SCHEMA_FILE: "urn:epinoic:overseer:dossier:" + DOSSIER_VERSION,
})
#: The separator line before each document of the system text; ``{path}`` is replaced by the document's path.
SYSTEM_SEPARATOR = "===== {path} ====="
KNOWLEDGE_DIR = "knowledge"
ALLOWED_SUFFIXES = (".txt", ".md", ".json")
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_PACK_BYTES = 8 * 1024 * 1024
MAX_PACK_FILES = 64
MAX_ZIP_ENTRIES = 256

PACK_ERROR_REASONS: tuple[str, ...] = (
    "manifest_missing", "manifest_invalid", "unsafe_path", "file_missing", "file_unlisted", "file_too_large", "file_encoding", "file_digest",
    "file_invalid", "pack_digest", "system_digest", "contract_mismatch", "unknown_pack", "digest_mismatch", "header_mismatch",
)
PackErrorReason = Literal[
    "manifest_missing", "manifest_invalid", "unsafe_path", "file_missing", "file_unlisted", "file_too_large", "file_encoding", "file_digest",
    "file_invalid", "pack_digest", "system_digest", "contract_mismatch", "unknown_pack", "digest_mismatch", "header_mismatch",
]

_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
_DOCUMENT_RE = re.compile(r"[0-9]{2}-[a-z0-9-]+\.md")
_BOM = b"\xef\xbb\xbf"


class PackError(ValueError):
    """A pack the loader refuses. ``reason`` is one of :data:`PACK_ERROR_REASONS`; ``path`` names the file concerned
    when there is one. The message is the loader's own text (never pack content)."""

    def __init__(self, reason: str, detail: str, *, path: Optional[str] = None) -> None:
        if reason not in PACK_ERROR_REASONS:
            raise ValueError(f"unknown pack error reason {reason!r}")
        super().__init__(f"{reason}: {detail}" + (f" [{path}]" if path else ""))
        self.reason = reason
        self.detail = detail
        self.path = path


# ============================================================================================ the manifest contract
class ManifestFile(BaseModel):
    """One file of the pack: its path, audience, size in bytes and SHA-256 over the bytes as stored."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    path: str = Field(min_length=1, max_length=256)
    audience: Literal["agent", "deployer", "machine"]
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)


class PackManifest(BaseModel):
    """``manifest.json`` (manifest version 1.0)."""
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    manifest_version: Literal["1.0"]
    pack_name: str = Field(pattern=PACK_NAME_PATTERN)
    pack_version: str = Field(pattern=PACK_VERSION_PATTERN)
    verdict_contract: str = Field(min_length=1, max_length=64)
    dossier_version: str = Field(min_length=1, max_length=16)
    system_order: tuple[str, ...] = Field(min_length=1, max_length=MAX_PACK_FILES)
    system_separator: str = Field(min_length=6, max_length=200)
    system_sha256: str = Field(pattern=SHA256_PATTERN)
    files: tuple[ManifestFile, ...] = Field(min_length=1, max_length=MAX_PACK_FILES)
    pack_sha256: str = Field(pattern=SHA256_PATTERN)


# ============================================================================================ rules shared by build and load
def pack_dir_name(name: str, version: str) -> str:
    """The directory (and zip root) name of a pack: ``<name>-<version>``."""
    return f"{name}-{version}"


def _safe_name(path: Any) -> bool:
    return (isinstance(path, str) and _NAME_RE.fullmatch(path) is not None and path not in (".", "..") and ".." not in path
            and path.endswith(ALLOWED_SUFFIXES))


def audience_of(path: str) -> Optional[str]:
    """The audience a pack file has by its name: the master prompt and the numbered documents are ``agent``, the README
    is ``deployer``, the two schemas are ``machine``; any other name has none (it is not a pack file)."""
    if path == MASTER_PROMPT_FILE or _DOCUMENT_RE.fullmatch(path):
        return "agent"
    if path == README_FILE:
        return "deployer"
    if path in SCHEMA_FILES:
        return "machine"
    return None


def system_order_of(paths: Iterable[str]) -> list[str]:
    """The system order: the master prompt, then the numbered documents in name order."""
    paths = list(paths)
    docs = sorted(p for p in paths if _DOCUMENT_RE.fullmatch(p))
    return ([MASTER_PROMPT_FILE] if MASTER_PROMPT_FILE in paths else []) + docs


def build_system_text(documents: Iterable[tuple[str, str]], separator: str = SYSTEM_SEPARATOR) -> str:
    """The system text of section 17.8 from ``(path, text)`` pairs in system order."""
    parts = [separator.replace("{path}", path) + "\n" + text.rstrip("\n") + "\n" for path, text in documents]
    return "\n".join(parts)


def header_lines(name: str, version: str, verdict_contract: str = VERDICT_CONTRACT, dossier_version: str = DOSSIER_VERSION) -> tuple[str, str, str]:
    """The three lines the master prompt opens with."""
    return (f"PACK: {name} {version}", f"VERDICT CONTRACT: {verdict_contract}", f"DOSSIER VERSION: {dossier_version}")


def manifest_pack_digest(manifest: Mapping[str, Any]) -> str:
    """``sha256(canonical_json(manifest without pack_sha256))``: sorted keys, separators ``,`` and ``:``, UTF-8 without
    ASCII escaping, so a deployer in any language can recompute it."""
    return sha256_hex(canonical_json({k: v for k, v in manifest.items() if k != "pack_sha256"}))


def _render_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def render_schemas() -> dict[str, str]:
    """``{file name: text}`` of the two schemas, generated from the protocol's contracts (``AgentVerdict``,
    ``Dossier``). Deterministic for one pydantic version; never edited by hand."""
    out = {}
    for name, model in ((VERDICT_SCHEMA_FILE, AgentVerdict), (DOSSIER_SCHEMA_FILE, Dossier)):
        schema = dict(model.model_json_schema())
        schema["$id"] = SCHEMA_IDS[name]
        out[name] = _render_json(schema)
    return out


def build_manifest(files: Mapping[str, bytes], *, name: str = PACK_NAME, version: str = PACK_VERSION, separator: str = SYSTEM_SEPARATOR) -> dict:
    """The manifest of a pack whose files (all but ``manifest.json``) are ``files`` (path to bytes as stored). Raises
    ``ValueError`` for a file that is not a pack file, a missing required file, or an agent document that is not UTF-8
    text without a byte-order mark or CR."""
    if MANIFEST_FILE in files:
        raise ValueError("the manifest does not list itself")
    for path in files:
        if not _safe_name(path) or audience_of(path) is None:
            raise ValueError(f"{path!r} is not a pack file name (master prompt, NN-name.md, README.md or a schema)")
    for required in (MASTER_PROMPT_FILE, README_FILE, *SCHEMA_FILES):
        if required not in files:
            raise ValueError(f"a pack needs {required}")
    order = system_order_of(files)
    if len(order) < 2:
        raise ValueError("a pack needs at least one numbered document")
    texts = {}
    for path, data in files.items():
        if data.startswith(_BOM) or b"\r" in data:
            raise ValueError(f"{path} has a byte-order mark or a CR")
        texts[path] = data.decode("utf-8")
    system = build_system_text(((p, texts[p]) for p in order), separator)
    manifest: dict[str, Any] = {
        "manifest_version": MANIFEST_VERSION, "pack_name": name, "pack_version": version, "verdict_contract": VERDICT_CONTRACT,
        "dossier_version": DOSSIER_VERSION, "system_order": order, "system_separator": separator, "system_sha256": sha256_hex(system),
        "files": [{"path": p, "audience": audience_of(p), "bytes": len(files[p]), "sha256": hashlib.sha256(files[p]).hexdigest()} for p in sorted(files)],
    }
    PackManifest.model_validate_json(json.dumps(dict(manifest, pack_sha256="0" * 64)))  # the builder never writes an invalid manifest
    manifest["pack_sha256"] = manifest_pack_digest(manifest)
    return manifest


def render_manifest(manifest: Mapping[str, Any]) -> str:
    """``manifest.json`` as written: sorted keys, two-space indent, final newline."""
    return _render_json(dict(manifest))


# ============================================================================================ sources
_Kind = Literal["file", "dir", "symlink", "other", "unsafe"]


class _DirSource:
    def __init__(self, root: Path, label: str) -> None:
        self.root = root
        self.label = label

    def entries(self) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            with os.scandir(self.root) as it:
                for entry in it:
                    if entry.is_symlink():
                        out[entry.name] = "symlink"
                    elif entry.is_file(follow_symlinks=False):
                        out[entry.name] = "file"
                    elif entry.is_dir(follow_symlinks=False):
                        out[entry.name] = "dir"
                    else:
                        out[entry.name] = "other"
        except OSError as exc:
            raise PackError("manifest_missing", f"the pack directory cannot be listed ({type(exc).__name__})") from None
        return out

    def read(self, name: str, limit: int) -> bytes:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        try:
            fd = os.open(self.root / name, flags)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise PackError("unsafe_path", "the file is a symlink", path=name) from None
            raise PackError("file_missing", f"the file cannot be opened ({type(exc).__name__})", path=name) from None
        with os.fdopen(fd, "rb") as fh:
            if not stat.S_ISREG(os.fstat(fh.fileno()).st_mode):
                raise PackError("file_missing", "not a regular file", path=name)
            data = fh.read(limit + 1)
        if len(data) > limit:
            raise PackError("file_too_large", f"the file is larger than {limit} bytes", path=name)
        return data

    def close(self) -> None:
        pass


class _TraversableSource:
    """An installed pack that is not on a filesystem path (a zipped installation): read through importlib.resources."""

    def __init__(self, root: Any, label: str) -> None:
        self.root = root
        self.label = label

    def entries(self) -> dict[str, str]:
        out: dict[str, str] = {}
        try:
            for child in self.root.iterdir():
                out[child.name] = "file" if child.is_file() else "dir" if child.is_dir() else "other"
        except OSError:
            raise PackError("manifest_missing", "the installed pack cannot be listed") from None
        return out

    def read(self, name: str, limit: int) -> bytes:
        try:
            with self.root.joinpath(name).open("rb") as fh:
                data = fh.read(limit + 1)
        except OSError as exc:
            raise PackError("file_missing", f"the file cannot be read ({type(exc).__name__})", path=name) from None
        if len(data) > limit:
            raise PackError("file_too_large", f"the file is larger than {limit} bytes", path=name)
        return data

    def close(self) -> None:
        pass


def _zip_name_unsafe(name: str) -> bool:
    parts = name.split("/")
    return (not name or "\\" in name or name.startswith("/") or "\x00" in name or re.match(r"[A-Za-z]:", name) is not None
            or any(p in ("..", ".") for p in parts))


class _ZipSource:
    """A zip archive read in place: its entries are screened when it is opened, and nothing is extracted."""

    def __init__(self, path: Path, label: str) -> None:
        self.label = label
        try:
            self._zf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError, ValueError):
            raise PackError("manifest_missing", "not a readable zip archive") from None
        infos = self._zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            self._zf.close()
            raise PackError("file_too_large", f"the archive holds more than {MAX_ZIP_ENTRIES} entries")
        names = [i.filename for i in infos]
        prefix = ""
        if names and all("/" in n for n in names) and len({n.split("/", 1)[0] for n in names}) == 1:
            prefix = names[0].split("/", 1)[0] + "/"
        root_ok = not prefix or _NAME_RE.fullmatch(prefix[:-1]) is not None
        self._entries: dict[str, str] = {}
        self._infos: dict[str, zipfile.ZipInfo] = {}
        for info in infos:
            name = info.filename
            mode = (info.external_attr >> 16) & 0xFFFF
            if _zip_name_unsafe(name) or not root_ok:
                key, kind = name, "unsafe"
            else:
                rel = name[len(prefix):]
                if rel == "":
                    continue  # the root directory entry
                kind = "file"
                if rel.endswith("/"):
                    rel, kind = rel[:-1], "dir"
                if "/" in rel:
                    kind = "unsafe"  # a pack is flat
                elif stat.S_ISLNK(mode):
                    kind = "symlink"
                elif info.flag_bits & 0x1:
                    kind = "unsafe"  # encrypted: cannot be read in place
                key = rel
            if key in self._entries:
                kind = "unsafe"  # a duplicate entry is ambiguous
            self._entries[key] = kind
            self._infos[key] = info
        unsafe = sorted(k for k, v in self._entries.items() if v == "unsafe")
        if unsafe:  # screened when opened: an escaping, nested, duplicate or encrypted entry refuses the whole archive
            self._zf.close()
            raise PackError("unsafe_path", "the archive holds an entry that escapes or nests inside the pack, a duplicate or an encrypted entry",
                            path=unsafe[0][:256])

    def entries(self) -> dict[str, str]:
        return dict(self._entries)

    def read(self, name: str, limit: int) -> bytes:
        info = self._infos.get(name)
        if info is None:
            raise PackError("file_missing", "no such entry", path=name)
        try:
            with self._zf.open(info) as fh:
                data = fh.read(limit + 1)
        except (zipfile.BadZipFile, zlib.error, EOFError, OSError, RuntimeError, NotImplementedError):
            raise PackError("file_digest", "the archive entry is corrupt or cannot be read in place", path=name) from None
        if len(data) > limit:
            raise PackError("file_too_large", f"the file is larger than {limit} bytes", path=name)
        return data

    def close(self) -> None:
        self._zf.close()


_Source = Union[_DirSource, _TraversableSource, _ZipSource]


def installed_pack_dir(version: str = PACK_VERSION) -> Any:
    """Where the installed pack of ``version`` lives (a ``Path`` for a normal installation, an importlib.resources
    traversable otherwise)."""
    return resources.files("epinoic_logic.overseer").joinpath(KNOWLEDGE_DIR).joinpath(pack_dir_name(PACK_NAME, version))


def _source_for(path: Any) -> _Source:
    if path is None:
        root = installed_pack_dir()
        if isinstance(root, Path):
            return _DirSource(root, "installed")
        return _TraversableSource(root, "installed")
    p = Path(path)
    if p.is_dir():
        return _DirSource(p, str(p))
    if p.is_file():
        if zipfile.is_zipfile(p):
            return _ZipSource(p, str(p))
        raise PackError("manifest_missing", "the path is neither a pack directory nor a zip archive")
    raise PackError("manifest_missing", "no pack at this path")


# ============================================================================================ the pack
_BUILDING = threading.local()  # set only while the loader constructs a pack: no copy or replace() can forge one


@dataclass(frozen=True)
class KnowledgePack:
    """A loaded, verified knowledge pack. Built only by :func:`load_pack`.

    ``identity`` is the pack the code accepted; ``documents`` are the agent-audience files in system order as
    ``(path, text)``; ``readme`` is the deployer README; ``schemas`` are ``(path, text)``; ``files`` are every file's
    bytes as stored (``manifest.json`` included), sorted by path, for the exporter."""
    identity: PackIdentity
    manifest: PackManifest
    documents: tuple[tuple[str, str], ...]
    readme: str
    schemas: tuple[tuple[str, str], ...]
    files: tuple[tuple[str, bytes], ...]
    source: str
    _system: str = field(repr=False, compare=False, default="")

    def __post_init__(self) -> None:
        if not getattr(_BUILDING, "active", False):
            raise TypeError("a KnowledgePack is built only by load_pack, which verifies it")

    def system_text(self) -> str:
        """The system configuration of an overseer agent (section 17.8)."""
        return self._system

    @property
    def system_sha256(self) -> str:
        return self.manifest.system_sha256

    @property
    def prompt_version(self) -> str:
        """``<name>/<version>+<first 16 hex of the pack digest>``: what every ``ProviderInfo`` records."""
        return f"{self.identity.name}/{self.identity.version}+{self.identity.sha256[:16]}"

    @property
    def dir_name(self) -> str:
        return pack_dir_name(self.identity.name, self.identity.version)

    @property
    def paths(self) -> tuple[str, ...]:
        return tuple(p for p, _ in self.files)

    def file_bytes(self, path: str) -> bytes:
        for p, data in self.files:
            if p == path:
                return data
        raise KeyError(path)

    def schema(self, path: str) -> dict:
        """A schema of the pack, parsed fresh (callers cannot change the pack)."""
        for p, text in self.schemas:
            if p == path:
                return json.loads(text)
        raise KeyError(path)

    def verify(self) -> None:
        """Re-check the pack in memory: every file against the manifest, the manifest digest, the system digest and the
        identity. Raises :class:`PackError`."""
        data = dict(self.files)
        try:
            manifest_obj = json.loads(data[MANIFEST_FILE].decode("utf-8"), object_pairs_hook=strict_object_pairs)
        except (KeyError, ValueError):
            raise PackError("manifest_invalid", "the pack in memory has no readable manifest") from None
        try:
            parsed = PackManifest.model_validate_json(data[MANIFEST_FILE])
        except ValidationError:
            raise PackError("manifest_invalid", "the pack in memory has an invalid manifest") from None
        if self.manifest != parsed:
            raise PackError("manifest_invalid", "the pack's manifest object is not its manifest file")
        for f in self.manifest.files:
            blob = data.get(f.path)
            if blob is None or len(blob) != f.bytes or hashlib.sha256(blob).hexdigest() != f.sha256:
                raise PackError("file_digest", "a file in memory differs from the manifest", path=f.path)
        if set(data) != {f.path for f in self.manifest.files} | {MANIFEST_FILE}:
            raise PackError("file_unlisted", "the pack in memory holds files the manifest does not list")
        if manifest_pack_digest(manifest_obj) != self.manifest.pack_sha256 or self.identity.sha256 != self.manifest.pack_sha256:
            raise PackError("pack_digest", "the pack digest in memory does not recompute")
        if (self.identity.name, self.identity.version) != (self.manifest.pack_name, self.manifest.pack_version):
            raise PackError("manifest_invalid", "the identity is not the manifest's")
        docs = tuple((p, data[p].decode("utf-8")) for p in self.manifest.system_order)
        system = build_system_text(docs, self.manifest.system_separator)
        if docs != self.documents or system != self._system or sha256_hex(system) != self.manifest.system_sha256:
            raise PackError("system_digest", "the system text in memory does not recompute")


# ============================================================================================ loading
def _decode(data: bytes, path: str, reason: str) -> str:
    if data.startswith(_BOM):
        raise PackError(reason, "the file starts with a byte-order mark", path=path)
    if b"\r" in data:
        raise PackError(reason, "the file contains a CR character (line endings must be LF)", path=path)
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise PackError(reason, "the file is not UTF-8", path=path) from None


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name}")


def _strict_json(text: str) -> Any:
    return json.loads(text, object_pairs_hook=strict_object_pairs, parse_constant=_reject_constant)


def _parse_manifest(raw: bytes) -> tuple[PackManifest, dict]:
    text = _decode(raw, MANIFEST_FILE, "manifest_invalid")
    try:
        obj = _strict_json(text)
    except (ValueError, RecursionError):
        raise PackError("manifest_invalid", "the manifest is not strict JSON (duplicate keys and non-finite numbers are refused)", path=MANIFEST_FILE) from None
    if not isinstance(obj, dict):
        raise PackError("manifest_invalid", "the manifest is not a JSON object", path=MANIFEST_FILE)
    try:
        manifest = PackManifest.model_validate_json(text)
    except ValidationError as exc:
        locs = "; ".join(f"{'/'.join(str(x) for x in e.get('loc', ())) or '$'}: {e.get('type')}" for e in exc.errors()[:6])
        raise PackError("manifest_invalid", f"the manifest does not follow manifest 1.0 ({locs})", path=MANIFEST_FILE) from None
    return manifest, obj


def _check_structure(manifest: PackManifest) -> None:
    paths = [f.path for f in manifest.files]
    if len(set(paths)) != len(paths):
        raise PackError("manifest_invalid", "the manifest lists a path twice", path=MANIFEST_FILE)
    if paths != sorted(paths):
        raise PackError("manifest_invalid", "the manifest's files are not sorted by path", path=MANIFEST_FILE)
    if MANIFEST_FILE in paths:
        raise PackError("manifest_invalid", "the manifest lists itself", path=MANIFEST_FILE)
    for f in manifest.files:
        if audience_of(f.path) is None:
            raise PackError("manifest_invalid", "a listed file is not a pack file (master prompt, NN-name.md, README.md or a schema)", path=f.path)
        if audience_of(f.path) != f.audience:
            raise PackError("manifest_invalid", f"the audience of a file is not {audience_of(f.path)!r}", path=f.path)
    for required in (MASTER_PROMPT_FILE, README_FILE, *SCHEMA_FILES):
        if required not in paths:
            raise PackError("manifest_invalid", "the manifest does not list a required file", path=required)
    order = system_order_of(paths)
    if len(order) < 2 or list(manifest.system_order) != order:
        raise PackError("manifest_invalid", "system_order is not the master prompt followed by the numbered documents in name order", path=MANIFEST_FILE)
    sep = manifest.system_separator
    if sep.count("{path}") != 1 or "\n" in sep or "\r" in sep:
        raise PackError("manifest_invalid", "system_separator must hold '{path}' once and no line break", path=MANIFEST_FILE)


def _check_identity(identity: PackIdentity, trusted: Collection[PackIdentity]) -> None:
    key = (identity.name, identity.version)
    pinned = PACK_DIGESTS.get(key)
    if pinned is not None:
        if pinned != identity.sha256:
            raise PackError("digest_mismatch", f"{identity.label} is pinned under another digest: the pack was changed after it was pinned")
        return
    same = [t for t in trusted if (t.name, t.version) == key]
    if not same:
        raise PackError("unknown_pack", f"{identity.label} is neither pinned by this code nor trusted by the operator")
    if identity not in same:
        raise PackError("digest_mismatch", f"{identity.label} is trusted under another digest")


def _load(source: _Source, trusted: Collection[PackIdentity], *, pin_check: bool = True) -> KnowledgePack:
    entries = source.entries()
    kind = entries.get(MANIFEST_FILE)
    if kind in ("symlink", "unsafe"):
        raise PackError("unsafe_path", "the manifest is a symlink or an unsafe archive entry", path=MANIFEST_FILE)
    if kind != "file":
        raise PackError("manifest_missing", "the pack has no manifest.json", path=MANIFEST_FILE)
    raw_manifest = source.read(MANIFEST_FILE, MAX_FILE_BYTES)
    manifest, manifest_obj = _parse_manifest(raw_manifest)
    # ---------------------------------------------------------------- paths
    for f in manifest.files:
        if not _safe_name(f.path):
            raise PackError("unsafe_path", "a listed path is not a bare pack file name with an allowed extension", path=f.path[:256])
    for p in manifest.system_order:
        if not _safe_name(p):
            raise PackError("unsafe_path", "a system_order entry is not a bare pack file name", path=p[:256])
    for name in sorted(entries):
        if entries[name] in ("symlink", "unsafe"):
            raise PackError("unsafe_path", "the pack holds a symlink or an entry that escapes or nests inside the pack", path=name[:256])
    _check_structure(manifest)
    listed = {f.path: f for f in manifest.files}
    for path in listed:
        if entries.get(path) != "file":
            raise PackError("file_missing", "a listed file is absent (or not a regular file)", path=path)
    for name in sorted(entries):
        if name != MANIFEST_FILE and name not in listed:
            raise PackError("file_unlisted", "the pack holds a file or directory the manifest does not list", path=name[:256])
    # ---------------------------------------------------------------- contents
    total = len(raw_manifest)
    blobs: dict[str, bytes] = {}
    for f in manifest.files:
        data = source.read(f.path, MAX_FILE_BYTES)
        total += len(data)
        if total > MAX_PACK_BYTES:
            raise PackError("file_too_large", f"the pack is larger than {MAX_PACK_BYTES} bytes", path=f.path)
        blobs[f.path] = data
    texts = {path: _decode(data, path, "file_encoding") for path, data in blobs.items()}
    for f in manifest.files:
        data = blobs[f.path]
        if len(data) != f.bytes or hashlib.sha256(data).hexdigest() != f.sha256:
            raise PackError("file_digest", "the file's SHA-256 (or size) differs from the manifest", path=f.path)
    for path, text in texts.items():
        if path.endswith(".json"):
            try:
                obj = _strict_json(text)
            except (ValueError, RecursionError):
                raise PackError("file_invalid", "the file is not strict JSON", path=path) from None
            if not isinstance(obj, dict):
                raise PackError("file_invalid", "the file is not a JSON object", path=path)
    if manifest_pack_digest(manifest_obj) != manifest.pack_sha256:
        raise PackError("pack_digest", "the recomputed pack digest differs from the manifest's pack_sha256", path=MANIFEST_FILE)
    documents = tuple((p, texts[p]) for p in manifest.system_order)
    system = build_system_text(documents, manifest.system_separator)
    if sha256_hex(system) != manifest.system_sha256:
        raise PackError("system_digest", "the recomputed system text digest differs from the manifest's system_sha256", path=MANIFEST_FILE)
    if manifest.verdict_contract != VERDICT_CONTRACT or manifest.dossier_version != DOSSIER_VERSION:
        raise PackError("contract_mismatch", f"the pack is written for {manifest.verdict_contract} and dossier {manifest.dossier_version}; this code "
                                             f"implements {VERDICT_CONTRACT} and dossier {DOSSIER_VERSION}", path=MANIFEST_FILE)
    identity = PackIdentity(name=manifest.pack_name, version=manifest.pack_version, sha256=manifest.pack_sha256)
    if pin_check:
        _check_identity(identity, trusted)
    first = tuple(texts[MASTER_PROMPT_FILE].split("\n")[:3])
    if first != header_lines(manifest.pack_name, manifest.pack_version, manifest.verdict_contract, manifest.dossier_version):
        raise PackError("header_mismatch", "the master prompt's PACK, VERDICT CONTRACT and DOSSIER VERSION lines differ from the manifest",
                        path=MASTER_PROMPT_FILE)
    files = tuple(sorted([*blobs.items(), (MANIFEST_FILE, raw_manifest)]))
    _BUILDING.active = True
    try:
        return KnowledgePack(identity=identity, manifest=manifest, documents=documents, readme=texts[README_FILE],
                             schemas=tuple((p, texts[p]) for p in SCHEMA_FILES), files=files, source=source.label, _system=system)
    finally:
        _BUILDING.active = False


def load_pack(path: Any = None, *, trusted: Collection[PackIdentity] = ()) -> KnowledgePack:
    """Load and verify a pack: the installed pack when ``path`` is None, else a pack directory or a ``.zip`` archive
    (read in place). ``trusted`` accepts further identities explicitly (never a pinned name and version under another
    digest). Raises :class:`PackError` on the first failed check; nothing is loaded."""
    trusted = tuple(trusted)
    if not all(isinstance(t, PackIdentity) for t in trusted):
        raise TypeError("trusted must hold PackIdentity values")
    source = _source_for(path)
    try:
        return _load(source, trusted)
    finally:
        source.close()


def _load_unpinned(path: Any) -> KnowledgePack:
    """Every check of :func:`load_pack` except the pin (``unknown_pack``, ``digest_mismatch``): for the maintainer's
    ``export --refresh-source``, which writes a new manifest whose digest is not pinned yet. Never used to accept a
    pack for an agent: the runner, the exporter's ``--out`` and ``--verify`` and the intake use :func:`load_pack`."""
    source = _source_for(path)
    try:
        return _load(source, (), pin_check=False)
    finally:
        source.close()


_INSTALLED: Optional[KnowledgePack] = None
_INSTALLED_LOCK = threading.Lock()


def installed_pack(*, reload: bool = False) -> KnowledgePack:
    """The installed pack, loaded and verified once (a refusal is never cached: every call retries and raises)."""
    global _INSTALLED
    with _INSTALLED_LOCK:
        if _INSTALLED is None or reload:
            _INSTALLED = load_pack(None)
        return _INSTALLED


def accepted_identities(trusted: Collection[PackIdentity] = ()) -> frozenset[PackIdentity]:
    """Every pack identity this code accepts: the pinned digests plus ``trusted`` (for an intake's ``accepted_packs``)."""
    pinned = {PackIdentity(name=n, version=v, sha256=d) for (n, v), d in PACK_DIGESTS.items()}
    extra = {t for t in trusted if (t.name, t.version) not in PACK_DIGESTS}
    return frozenset(pinned | extra)
