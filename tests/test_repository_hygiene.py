"""The repository tracks no leaked temporary output (the round-10 hold remedy c3c, push check of the c3 clearance commit).

That commit picked up five scratch directories at the repository root (``tmp`` plus eight random characters, each a byte copy of
the exported overseer knowledge pack ``overseer-knowledge-docs-2.2`` and its zip). They were written by an untracked probe that
called ``tempfile.mkdtemp(dir=".")`` and the pack exporter while its working directory was the repository. The guards below hold
the class, not those five names:

* no tracked top-level entry is named like a Python ``tempfile`` directory or file (``tmp`` followed by 6 to 12 characters of
  ``[a-z0-9_]``), and ``.gitignore`` ignores such directories at the root while ignoring no tracked path;
* a copy of the overseer pack is tracked only where its source lives (``overseer/src/epinoic_overseer/knowledge/``, directories
  without a zip): the exporter writes ``DIR/overseer-knowledge-docs-<version>/`` and its zip into the ``--out DIR`` the caller
  names, which is export output and never tracked, so no tracked ``.zip`` holds the pack, whatever the zip is called;
* no tracked Python file creates a temporary file or directory in the working directory or under a relative path
  (``dir="."``, ``dir=os.getcwd()``, ``dir=Path.cwd()``, ``dir="out"``), or points ``tempfile.tempdir`` or ``TMPDIR``/``TEMP``/``TMP``
  at one: temporary output belongs under the system temporary directory (the ``tempfile`` default) or a directory the caller
  passes in (an atomic write into its own destination).

The checks read the index (``git ls-files``), which is what a commit records; they are skipped only outside a git checkout.
"""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
#: Python's tempfile names: ``tmp`` and a random suffix (8 characters of ``[a-z0-9_]`` today; 6 to 12 allowed).
TEMPFILE_NAME = re.compile(r"tmp[a-z0-9_]{6,12}")
PACK_NAME = re.compile(r"overseer-knowledge-docs-\d+(?:\.\d+)+")
#: Where the overseer pack's source lives; the only tracked place for a copy of it (directories only, never a zip).
PACK_SOURCE = "overseer/src/epinoic_overseer/knowledge/"
TEMP_CALLS = frozenset({"mkdtemp", "mkstemp", "mktemp", "TemporaryDirectory", "NamedTemporaryFile", "SpooledTemporaryFile", "TemporaryFile"})
TEMP_ENV = frozenset({"TMPDIR", "TEMP", "TMP"})


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, check=True, timeout=120).stdout


@pytest.fixture(scope="module")
def tracked() -> list[str]:
    if shutil.which("git") is None or not (ROOT / ".git").exists():
        pytest.skip("not a git checkout: the tracked paths cannot be read")
    return [p for p in _git("ls-files", "-z").split("\0") if p]


# ============================================================================================ tempfile-named root entries
def is_tempfile_name(name: str) -> bool:
    return TEMPFILE_NAME.fullmatch(name) is not None


def test_the_tempfile_name_predicate_reads_python_tempfile_names_and_no_repository_name():
    for name in ("tmp4cuakejq", "tmp_tdbh6dg", "tmpb7ndk4bd", "tmps9eqtyvj", "tmpt3bv1x3c", "tmpab12_x", "tmp0123456789ab"):
        assert is_tempfile_name(name) is True, name
    for name in ("tmp", "tmp12", "tmp0123456789abc", "tmpAbcdefgh", "tmp-abcdefgh", "temp_abcdefgh", "src", "tests", "templates",
                 "tmp4cuakejq.zip", ".tmp4cuakejq", "overseer", "pyproject.toml"):
        assert is_tempfile_name(name) is False, name


def test_no_tracked_top_level_entry_is_named_like_a_tempfile_directory(tracked):
    top = sorted({p.split("/", 1)[0] for p in tracked})
    assert [name for name in top if is_tempfile_name(name)] == []


def test_the_gitignore_ignores_tempfile_directories_at_the_root_and_no_tracked_path(tracked):
    for probe in ("tmp4cuakejq/overseer-knowledge-docs-2.2.zip", "tmp_tdbh6dg/x/manifest.json", "tmpab12cd34/a.txt"):
        out = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", probe], capture_output=True, timeout=60)
        assert out.returncode == 0, probe
    for kept in ("tests/test_repository_hygiene.py", "src/tmp4cuakejq/a.py", "templates/a.txt"):
        out = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", kept], capture_output=True, timeout=60)
        assert out.returncode == 1, kept
    assert _git("ls-files", "-c", "-i", "--exclude-standard") == ""


# ============================================================================================ copies of the overseer pack
def _zip_holds_the_pack(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return any(PACK_NAME.search(n) or n.rsplit("/", 1)[-1] == "master_prompt.txt" for n in z.namelist())
    except (zipfile.BadZipFile, OSError):
        return PACK_NAME.search(path.name) is not None


def test_no_tracked_zip_holds_the_overseer_pack(tracked):
    zips = [p for p in tracked if p.lower().endswith(".zip")]
    assert [p for p in zips if PACK_NAME.search(p) or _zip_holds_the_pack(ROOT / p)] == []


def test_a_tracked_copy_of_the_overseer_pack_lies_only_in_its_source_tree(tracked):
    copies = [p for p in tracked if any(PACK_NAME.fullmatch(part) for part in p.split("/")[:-1])]
    assert copies, "the pack's source tree is tracked"
    assert [p for p in copies if not p.startswith(PACK_SOURCE)] == []


def test_the_pack_guards_read_a_stray_export_as_one():
    stray = ["tmp4cuakejq/overseer-knowledge-docs-2.2/manifest.json", "tmp4cuakejq/overseer-knowledge-docs-2.2.zip"]
    assert [p for p in stray if any(PACK_NAME.fullmatch(part) for part in p.split("/")[:-1]) and not p.startswith(PACK_SOURCE)] == stray[:1]
    assert [p for p in stray if PACK_NAME.search(p) and p.endswith(".zip")] == stray[1:]
    assert PACK_NAME.fullmatch("overseer-knowledge-docs-2.2") and not PACK_NAME.fullmatch("overseer-knowledge-docs")


# ============================================================================================ temporary output under the repository
def _callee(node: ast.AST) -> str:
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _relative(node: ast.AST) -> bool:
    """True when ``node`` names the working directory or a relative path: a relative string constant, ``os.curdir``,
    ``os.getcwd()``, ``Path.cwd()``, or ``Path``/``str``/``os.path.join``/``os.path.abspath`` of one of these."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        value = node.value.decode() if isinstance(node.value, bytes) else node.value
        return not (value.startswith("/") or re.match(r"[A-Za-z]:[\\/]", value) or value.startswith("\\\\"))
    if isinstance(node, ast.Attribute) and node.attr == "curdir":
        return True
    if isinstance(node, ast.Call):
        name = _callee(node.func)
        if name in ("getcwd", "getcwdb", "cwd"):
            return True
        if name in ("Path", "PurePath", "str", "fspath", "join", "abspath", "realpath", "resolve") and node.args:
            return _relative(node.args[0])
        if name in ("resolve", "absolute") and isinstance(node.func, ast.Attribute):
            return _relative(node.func.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _relative(node.left)
    if isinstance(node, ast.JoinedStr) and node.values:
        return _relative(node.values[0]) if isinstance(node.values[0], ast.Constant) else False
    return False


def temp_output_in_the_working_directory(source: str) -> list[str]:
    """Every place in ``source`` that creates temporary output in the working directory or under a relative path."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _callee(node.func) in TEMP_CALLS:
            for kw in node.keywords:
                if kw.arg == "dir" and _relative(kw.value):
                    found.append(f"{node.lineno}: {_callee(node.func)}(dir=...)")
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr == "tempdir" and _relative(node.value):
                    found.append(f"{node.lineno}: tempfile.tempdir")
                if isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) and t.slice.value in TEMP_ENV and _relative(node.value):
                    found.append(f"{node.lineno}: environ[{t.slice.value}]")
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value in TEMP_ENV and _relative(v):
                    found.append(f"{node.lineno}: {{{k.value!r}: ...}}")
        if isinstance(node, ast.Call) and _callee(node.func) in ("dict", "setenv", "setdefault", "putenv"):
            for kw in node.keywords:
                if kw.arg in TEMP_ENV and _relative(kw.value):
                    found.append(f"{node.lineno}: {kw.arg}=...")
            if len(node.args) >= 2 and isinstance(node.args[0], ast.Constant) and node.args[0].value in TEMP_ENV and _relative(node.args[1]):
                found.append(f"{node.lineno}: {_callee(node.func)}({node.args[0].value!r}, ...)")
    return found


def test_the_scanner_reads_temporary_output_in_the_working_directory():
    leaks = {
        'import tempfile\nd = tempfile.mkdtemp(dir=".")': ["2: mkdtemp(dir=...)"],
        'import tempfile, os\nwith tempfile.TemporaryDirectory(dir=os.getcwd()) as d: pass': ["2: TemporaryDirectory(dir=...)"],
        'import tempfile\nfrom pathlib import Path\nf = tempfile.NamedTemporaryFile(dir=Path.cwd())': ["3: NamedTemporaryFile(dir=...)"],
        'import tempfile\nfrom pathlib import Path\nfd, p = tempfile.mkstemp(dir=Path("out") / "x")': ["3: mkstemp(dir=...)"],
        'import tempfile, os\nd = tempfile.mkdtemp(dir=os.curdir)': ["2: mkdtemp(dir=...)"],
        'import tempfile\ntempfile.tempdir = "."': ["2: tempfile.tempdir"],
        'import os\nos.environ["TMPDIR"] = "scratch"': ['2: environ[TMPDIR]'],
        'import subprocess\nsubprocess.run(["x"], env={"TMPDIR": "."})': ["2: {'TMPDIR': ...}"],
        'def t(monkeypatch):\n    monkeypatch.setenv("TMPDIR", ".")': ["2: setenv('TMPDIR', ...)"],
        'env = dict(TMP=".")': ["1: TMP=..."],
    }
    for source, expected in leaks.items():
        assert temp_output_in_the_working_directory(source) == expected, source
    clean = (
        'import tempfile\nd = tempfile.mkdtemp()',
        'import tempfile\nwith tempfile.TemporaryDirectory(prefix="arena-pack-") as d: pass',
        'import tempfile\nd = tempfile.mkdtemp(prefix="probe-", dir="/tmp")',
        'import tempfile\ndef w(directory, name):\n    return tempfile.mkstemp(dir=directory, prefix=f".{name}.")',
        'def t(tmp_path):\n    import tempfile\n    return tempfile.mkdtemp(dir=tmp_path)',
        'import tempfile\nd = tempfile.mkdtemp(dir=tempfile.gettempdir())',
        'import os\nenv = {"PATH": os.environ.get("PATH", "")}',
        'x = {"dir": "."}',
    )
    for source in clean:
        assert temp_output_in_the_working_directory(source) == [], source


def test_no_tracked_python_file_writes_temporary_output_into_the_working_directory(tracked):
    found: dict[str, list[str]] = {}
    for rel in tracked:
        if not rel.endswith(".py"):
            continue
        path = ROOT / rel
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            hits = temp_output_in_the_working_directory(source)
        except SyntaxError:
            continue
        if hits:
            found[rel] = hits
    assert found == {}
