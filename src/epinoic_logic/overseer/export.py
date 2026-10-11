"""Exporter of the overseer knowledge pack: writes it out for deployment, verifies an exported pack, and (for
maintainers) regenerates the pack's generated files in a source checkout.

::

    python -m epinoic_logic.overseer.export --out DIR [--zip] [--force]
    python -m epinoic_logic.overseer.export --verify PATH
    python -m epinoic_logic.overseer.export --refresh-source [--source PACK_DIR]     (maintainers, source checkout only)

* ``--out DIR`` loads the installed pack (every check of :mod:`~epinoic_logic.overseer.pack`), copies every file byte
  for byte into ``DIR/overseer-knowledge-docs-<version>/``, loads the written copy again and checks that its identity and
  bytes are identical. It refuses a non-empty ``DIR`` unless ``--force`` is given, and writes nothing outside ``DIR``:
  files are created exclusively in a temporary directory inside ``DIR`` that is then renamed. With ``--force`` an earlier
  export of the same pack inside ``DIR`` is replaced (only when it is a directory of regular files); other content of
  ``DIR`` is left alone.
* ``--zip`` also writes ``DIR/overseer-knowledge-docs-<version>.zip`` deterministically (entries sorted under the pack
  directory, stored without compression, timestamps fixed at 1980-01-01, Unix mode 0644, no extra attributes), loads it
  back in place and prints its SHA-256.
* ``--verify PATH`` loads a pack directory or zip and prints its identity, or the refusal reason with exit status 2.
* ``--refresh-source`` regenerates ``verdict.schema.json`` and ``dossier.schema.json`` from the contracts and
  ``manifest.json`` from the files, runs every loader check except the pin, and prints the new pack digest, which the
  maintainer pins in ``pack.PACK_DIGESTS``. Without ``--source`` it works on the package's own pack and refuses to run
  outside a source checkout (an installed copy is never rewritten); ``--source`` names another pack directory of a
  working copy (never one inside ``site-packages``).

Every mode prints one JSON summary line (pack name, version, digest, files, output paths). Exit status 0 on success,
2 on a refusal. Nothing in a pack is ever executed, imported or evaluated.

Deviations from ``docs/OVERSEER_DESIGN.md`` section 17.7, listed as each stage requires:

* the zip stores entries uncompressed, so its bytes do not depend on the zlib build;
* ``--source PACK_DIR`` is added to ``--refresh-source`` (a maintainer preparing a new version, and the tests, which
  refresh a scratch copy and never the source tree); a refresh summary says whether the new digest is already pinned;
* refusals of the exporter itself have their own reasons (:data:`EXPORT_REASONS`) beside the loader's
  (:data:`~epinoic_logic.overseer.pack.PACK_ERROR_REASONS`).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

from .pack import (
    KNOWLEDGE_DIR, MANIFEST_FILE, PACK_DIGESTS, PACK_NAME, PACK_VERSION, KnowledgePack, PackError, _load_unpinned, build_manifest, installed_pack,
    load_pack, pack_dir_name, render_manifest, render_schemas,
)
from .verdicts import PackIdentity

__all__ = [
    "ExportError", "ExportResult", "RefreshResult", "EXPORT_REASONS", "ZIP_DATE_TIME", "export_pack", "write_zip", "verify_export", "refresh_source",
    "source_checkout_root", "main",
]

#: Every zip entry carries this timestamp, so an archive's bytes depend only on the pack.
ZIP_DATE_TIME = (1980, 1, 1, 0, 0, 0)
ZIP_FILE_MODE = 0o644
EXPORT_REASONS: tuple[str, ...] = ("target_not_empty", "target_unsafe", "roundtrip_mismatch", "not_source_checkout", "source_invalid", "io_error")
_DIR_NAME_RE = re.compile(r"(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)-(?P<version>[0-9]+\.[0-9]+)")
_INSTALLED_PARTS = ("site-packages", "dist-packages")


class ExportError(ValueError):
    """A refusal of the exporter itself (the loader's refusals are :class:`~epinoic_logic.overseer.pack.PackError`)."""

    def __init__(self, reason: str, detail: str, *, path: Optional[str] = None) -> None:
        if reason not in EXPORT_REASONS:
            raise ValueError(f"unknown export error reason {reason!r}")
        super().__init__(f"{reason}: {detail}" + (f" [{path}]" if path else ""))
        self.reason = reason
        self.detail = detail
        self.path = path


@dataclass(frozen=True)
class ExportResult:
    identity: PackIdentity
    directory: Path
    files: tuple[str, ...]
    zip_path: Optional[Path] = None
    zip_sha256: Optional[str] = None


@dataclass(frozen=True)
class RefreshResult:
    identity: PackIdentity
    directory: Path
    files: tuple[str, ...]
    changed: tuple[str, ...]
    pinned: bool


# ============================================================================================ writing
def _write_new(path: Path, data: bytes) -> None:
    """Create ``path`` exclusively (never through a symlink, never over an existing file) and write ``data``."""
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags, ZIP_FILE_MODE)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _write_replace(path: Path, data: bytes) -> bool:
    """Replace ``path`` atomically with ``data`` (a temporary file in the same directory, then a rename). Refuses a
    symlink or a non-file target. Returns whether the bytes changed."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ExportError("source_invalid", "the file to regenerate is a symlink or not a regular file", path=path.name)
    if path.exists() and path.read_bytes() == data:
        return False
    tmp = path.with_name(f".{path.name}.tmp-{uuid.uuid4().hex}")
    _write_new(tmp, data)
    os.replace(tmp, path)
    return True


def _remove_export(target: Path) -> None:
    """Remove an earlier export (``--force``): only a real directory holding only regular files."""
    if target.is_symlink() or not target.is_dir():
        raise ExportError("target_unsafe", "the pack path inside the output directory exists and is not a directory", path=target.name)
    entries = list(os.scandir(target))
    for e in entries:
        if e.is_symlink() or not e.is_file(follow_symlinks=False):
            raise ExportError("target_unsafe", "an earlier export holds something other than regular files; it is not removed", path=f"{target.name}/{e.name}")
    for e in entries:
        os.unlink(e.path)
    target.rmdir()


def write_zip(pack: KnowledgePack, zip_path: Path) -> str:
    """Write the pack as a deterministic zip archive at ``zip_path`` (which must not exist); returns its SHA-256."""
    zip_path = Path(zip_path)
    tmp = zip_path.with_name(f".{zip_path.name}.tmp-{uuid.uuid4().hex}")
    try:
        with zipfile.ZipFile(tmp, "x", compression=zipfile.ZIP_STORED, allowZip64=False) as zf:
            for path, data in sorted(pack.files):
                info = zipfile.ZipInfo(f"{pack.dir_name}/{path}", date_time=ZIP_DATE_TIME)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | ZIP_FILE_MODE) << 16
                zf.writestr(info, data)
        if zip_path.exists() or zip_path.is_symlink():
            raise ExportError("target_unsafe", "the zip path exists", path=zip_path.name)
        os.replace(tmp, zip_path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return hashlib.sha256(zip_path.read_bytes()).hexdigest()


# ============================================================================================ modes
def export_pack(out: Any, *, zip_archive: bool = False, force: bool = False, pack: Optional[KnowledgePack] = None) -> ExportResult:
    """Export ``pack`` (default: the installed pack) into ``out`` and load the written copy back (section 17.7)."""
    pack = pack if pack is not None else installed_pack()
    pack.verify()
    out = Path(out)
    if out.is_symlink() and not out.is_dir():
        raise ExportError("target_unsafe", "the output path is a dangling symlink")
    if out.exists() and not out.is_dir():
        raise ExportError("target_unsafe", "the output path exists and is not a directory")
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()) and not force:
        raise ExportError("target_not_empty", "the output directory is not empty; pass --force to replace an earlier export in it")
    target = out / pack.dir_name
    zip_path = out / f"{pack.dir_name}.zip" if zip_archive else None
    if target.exists() or target.is_symlink():
        _remove_export(target)
    if zip_path is not None and (zip_path.exists() or zip_path.is_symlink()):
        if zip_path.is_symlink() or not zip_path.is_file():
            raise ExportError("target_unsafe", "the zip path inside the output directory is not a regular file", path=zip_path.name)
        zip_path.unlink()
    tmp = out / f".{pack.dir_name}.tmp-{uuid.uuid4().hex}"
    tmp.mkdir()
    try:
        for path, data in pack.files:
            _write_new(tmp / path, data)
        tmp.rename(target)
    finally:
        if tmp.exists():
            for e in os.scandir(tmp):
                os.unlink(e.path)
            tmp.rmdir()
    loaded = load_pack(target, trusted=[pack.identity])
    if loaded.identity != pack.identity or loaded.files != pack.files:
        raise ExportError("roundtrip_mismatch", "the written pack does not load back to the same identity and bytes", path=pack.dir_name)
    zip_sha = None
    if zip_path is not None:
        zip_sha = write_zip(pack, zip_path)
        zloaded = load_pack(zip_path, trusted=[pack.identity])
        if zloaded.identity != pack.identity or zloaded.files != pack.files:
            raise ExportError("roundtrip_mismatch", "the written zip does not load back to the same identity and bytes", path=zip_path.name)
    return ExportResult(identity=pack.identity, directory=target, files=pack.paths, zip_path=zip_path, zip_sha256=zip_sha)


def verify_export(path: Any, *, trusted: Sequence[PackIdentity] = ()) -> KnowledgePack:
    """Load an exported pack (directory or zip) with every check; raises :class:`PackError`."""
    return load_pack(path, trusted=trusted)


def source_checkout_root() -> Optional[Path]:
    """The repository root when this package runs from a source checkout (``<root>/src/epinoic_logic`` beside
    ``<root>/pyproject.toml``, not under ``site-packages``); ``None`` for an installed copy."""
    pkg = Path(__file__).resolve().parent.parent
    src = pkg.parent
    if src.name == "src" and (src.parent / "pyproject.toml").is_file() and not any(p in _INSTALLED_PARTS for p in pkg.parts):
        return src.parent
    return None


def refresh_source(pack_dir: Any = None, *, version: str = PACK_VERSION) -> RefreshResult:
    """Regenerate the schemas and the manifest of a pack directory in a source checkout (section 17.4)."""
    if pack_dir is None:
        root = source_checkout_root()
        if root is None:
            raise ExportError("not_source_checkout", "--refresh-source rewrites the pack of a source checkout; this is an installed copy")
        pack_dir = root / "src" / "epinoic_logic" / "overseer" / KNOWLEDGE_DIR / pack_dir_name(PACK_NAME, version)
    pack_dir = Path(pack_dir)
    if any(p in _INSTALLED_PARTS for p in pack_dir.resolve().parts):
        raise ExportError("not_source_checkout", "the pack directory is inside an installed package; it is never rewritten")
    if pack_dir.is_symlink() or not pack_dir.is_dir():
        raise ExportError("source_invalid", "the pack directory does not exist or is a symlink")
    m = _DIR_NAME_RE.fullmatch(pack_dir.name)
    if m is None:
        raise ExportError("source_invalid", "a pack directory is named <name>-<MAJOR.MINOR>", path=pack_dir.name)
    name, ver = m.group("name"), m.group("version")
    changed = [fname for fname, text in sorted(render_schemas().items()) if _write_replace(pack_dir / fname, text.encode("utf-8"))]
    files: dict[str, bytes] = {}
    for e in sorted(os.scandir(pack_dir), key=lambda e: e.name):
        if e.name == MANIFEST_FILE:
            continue
        if e.is_symlink() or not e.is_file(follow_symlinks=False):
            raise ExportError("source_invalid", "the pack directory holds a symlink or a directory", path=e.name)
        files[e.name] = Path(e.path).read_bytes()
    try:
        manifest = build_manifest(files, name=name, version=ver)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ExportError("source_invalid", f"the pack's files cannot be listed in a manifest: {exc}") from None
    if _write_replace(pack_dir / MANIFEST_FILE, render_manifest(manifest).encode("utf-8")):
        changed.append(MANIFEST_FILE)
    pack = _load_unpinned(pack_dir)  # every check but the pin: a refreshed pack must load once its digest is pinned
    pinned = PACK_DIGESTS.get((pack.identity.name, pack.identity.version)) == pack.identity.sha256
    return RefreshResult(identity=pack.identity, directory=pack_dir, files=pack.paths, changed=tuple(changed), pinned=pinned)


# ============================================================================================ command line
def _summary(mode: str, identity: PackIdentity, files: Sequence[str], paths: dict) -> dict:
    return {"mode": mode, "ok": True, "pack_name": identity.name, "pack_version": identity.version, "pack_sha256": identity.sha256,
            "files": list(files), "paths": paths}


def _refusal(mode: str, exc: Exception) -> dict:
    return {"mode": mode, "ok": False, "reason": getattr(exc, "reason", "io_error"), "path": getattr(exc, "path", None),
            "detail": getattr(exc, "detail", type(exc).__name__)}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, sort_keys=True, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m epinoic_logic.overseer.export",
                                     description="Export, verify or (maintainers) refresh the overseer knowledge pack.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--out", metavar="DIR", help="write the installed pack into DIR/<name>-<version>/")
    mode.add_argument("--verify", metavar="PATH", help="load a pack directory or zip and print its identity")
    mode.add_argument("--refresh-source", action="store_true", help="regenerate schemas and manifest in a source checkout")
    parser.add_argument("--zip", action="store_true", help="with --out: also write DIR/<name>-<version>.zip")
    parser.add_argument("--force", action="store_true", help="with --out: write into a non-empty DIR, replacing an earlier export")
    parser.add_argument("--source", metavar="PACK_DIR", help="with --refresh-source: the pack directory to refresh")
    args = parser.parse_args(argv)
    if (args.zip or args.force) and args.out is None:
        parser.error("--zip and --force go with --out")
    if args.source is not None and not args.refresh_source:
        parser.error("--source goes with --refresh-source")
    if args.out is not None:
        try:
            res = export_pack(args.out, zip_archive=args.zip, force=args.force)
        except (PackError, ExportError, OSError) as exc:
            _emit(_refusal("export", exc))
            return 2
        paths: dict[str, Any] = {"directory": str(res.directory)}
        if res.zip_path is not None:
            paths.update(zip=str(res.zip_path), zip_sha256=res.zip_sha256)
        _emit(_summary("export", res.identity, res.files, paths))
        return 0
    if args.verify is not None:
        try:
            pack = verify_export(args.verify)
        except (PackError, OSError) as exc:
            _emit(_refusal("verify", exc))
            return 2
        out = _summary("verify", pack.identity, pack.paths, {"source": str(args.verify)})
        out["system_sha256"] = pack.system_sha256
        _emit(out)
        return 0
    try:
        ref = refresh_source(args.source)
    except (PackError, ExportError, OSError) as exc:
        _emit(_refusal("refresh-source", exc))
        return 2
    out = _summary("refresh-source", ref.identity, ref.files, {"directory": str(ref.directory)})
    out.update(changed=list(ref.changed), pinned=ref.pinned)
    _emit(out)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
