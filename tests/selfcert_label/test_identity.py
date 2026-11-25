"""The label's identity (meaning-check design 2.5.9) and the stage-1 boundaries: ``LABEL_VERSION`` and ``label_digest()``
(the digest moves with any covered byte, and the pair is pinned together, T17), no provider SDK, no socket, no model name, and
no release path that calls the package yet."""
from __future__ import annotations

import ast
import pathlib
import re
import shutil

import pytest

import epinoic_logic.selfcert_label as L
from epinoic_logic.selfcert_label import build_input

PKG = pathlib.Path(L.__file__).resolve().parent
ROOT = PKG.parents[2]


def test_the_version_and_the_covered_files():
    assert L.LABEL_VERSION == "selfcert-label-1"
    covered = L.covered_files()
    assert covered[:4] == ("prompt.md", "schema.json", "canaries.json", "exemptions.json")
    expected_code = sorted(p.relative_to(PKG).as_posix() for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)
    assert list(covered[4:]) == expected_code
    assert {"__init__.py", "anchor.py", "canaries.py", "exempt.py", "fakes.py", "inputs.py", "labellers.py", "record.py",
            "render.py", "scope.py", "validate.py"} <= set(expected_code)
    assert re.fullmatch(r"[0-9a-f]{64}", L.label_digest())
    assert L.label_digest() == L.label_digest()


#: T17 (memo 2.5.9 and 3.3): the label version and its digest, pinned together. A change of any covered byte (prompt.md,
#: schema.json, the canary and exemption data, any module of the package, or the rule reader's digest) moves the digest; it
#: must come with a new LABEL_VERSION and a new pin here, never with a new digest under the old version.
#: (selfcert-label-1 is not yet committed or released: its pin tracks the package as built until its first commit.)
PINNED = {"selfcert-label-1": "42ade34271d6aac7ffe021610696d819383c4b57c70458fe58d63c2beb13c680"}


def _check_pin(version: str, digest: str) -> None:
    """The T17 rule: the version must be pinned and its digest must be the pinned one."""
    assert version in PINNED, "a new label version needs its digest pinned here"
    assert digest == PINNED[version], "the label digest moved without a version bump"


def test_t17_the_version_and_the_digest_are_pinned_together():
    assert L.LABEL_VERSION == "selfcert-label-1"
    assert PINNED["selfcert-label-1"] == "42ade34271d6aac7ffe021610696d819383c4b57c70458fe58d63c2beb13c680"
    _check_pin(L.LABEL_VERSION, L.label_digest())


@pytest.fixture
def copy(tmp_path):
    dst = tmp_path / "selfcert_label"
    shutil.copytree(PKG, dst, ignore=shutil.ignore_patterns("__pycache__"))
    if not (dst / "prompt.md").exists():
        (dst / "prompt.md").write_text("placeholder prompt for the digest test\n", encoding="utf-8")
    return dst


def test_t17_a_digest_change_without_a_version_change_fails(copy):
    """T17 (negative): the pinned copy passes the pin check; one changed byte of any covered file under the same version
    fails it, and so does a new version that has no pin."""
    _check_pin(L.LABEL_VERSION, L.label_digest(copy))  # an unchanged copy carries the pinned digest
    for name in ("prompt.md", "schema.json", "canaries.json", "exemptions.json", "validate.py"):
        p = copy / name
        data = p.read_bytes()
        p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        with pytest.raises(AssertionError, match="moved without a version bump"):
            _check_pin(L.LABEL_VERSION, L.label_digest(copy))
        p.write_bytes(data)
    _check_pin(L.LABEL_VERSION, L.label_digest(copy))
    with pytest.raises(AssertionError, match="needs its digest pinned"):
        _check_pin("selfcert-label-2", L.label_digest(copy))


def test_the_digest_moves_when_any_covered_byte_changes(copy):
    base = L.label_digest(copy)
    seen = {base}
    for name in L.covered_files(copy):
        p = copy / name
        data = p.read_bytes()
        p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))
        moved = L.label_digest(copy)
        assert moved not in seen, name
        seen.add(moved)
        p.write_bytes(data)
        assert L.label_digest(copy) == base, name
    (copy / "new_module.py").write_text("X = 1\n", encoding="utf-8")
    assert L.label_digest(copy) not in seen  # a new module of the package is covered too
    (copy / "new_module.py").unlink()
    (copy / "prompt.md").unlink()
    assert L.label_digest(copy) not in seen  # an absent prompt is hashed as absent


def test_the_build_ships_every_data_file_of_the_package():
    """An installed copy carries the files label_digest covers: every non-code file of the package matches a package-data
    glob of pyproject.toml, so a wheel's digest equals the checkout's."""
    import fnmatch
    import tomllib
    globs = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["tool"]["setuptools"]["package-data"]["epinoic_logic"]
    data = sorted(p.relative_to(PKG.parent).as_posix() for p in PKG.rglob("*")
                  if p.is_file() and p.suffix not in (".py", ".pyc") and "__pycache__" not in p.parts)
    assert set(L.DATA_FILES) <= {pathlib.PurePosixPath(d).name for d in data}
    unshipped = [d for d in data if not any(fnmatch.fnmatchcase(d, g) for g in globs)]
    assert unshipped == []


def test_the_digest_covers_the_rule_readers_digest(copy, monkeypatch):
    from epinoic_logic import selfcert
    base = L.label_digest(copy)
    monkeypatch.setattr(selfcert, "rules_digest", lambda: "0" * 64)
    assert L.label_digest(copy) != base


def test_one_byte_of_the_prompt_moves_the_request_key_and_the_digest(copy, key):
    """T15 (second half): a changed prompt is a different recording key and a different label digest."""
    text = "The speed is 15 km/h."
    before = build_input(text, {"subject": "physics"}, key=key, prompt_path=copy / "prompt.md").requests[0].request_key
    d0 = L.label_digest(copy)
    p = copy / "prompt.md"
    data = p.read_bytes()
    p.write_bytes(data[:-1] + bytes([data[-1] ^ 1]) if data[-1:] != b"\n" else data + b" ")
    after = build_input(text, {"subject": "physics"}, key=key, prompt_path=p).requests[0].request_key
    assert after != before and L.label_digest(copy) != d0


def test_the_default_prompt_is_the_packaged_prompt_md(key):
    from epinoic_logic.selfcert_label import render
    assert render.PROMPT_PATH == PKG / "prompt.md"
    if not render.PROMPT_PATH.exists():
        pytest.skip("prompt.md is written by the prompt author")
    req = build_input("The speed is 15 km/h.", {"subject": "physics"}, key=key).requests[0]
    assert req.system_text == render.PROMPT_PATH.read_bytes().decode("utf-8")


_FORBIDDEN_IMPORTS = ("socket", "ssl", "http", "urllib", "requests", "httpx", "aiohttp", "anthropic", "openai", "google",
                      "boto3", "botocore", "websocket", "websockets", "asyncio", "subprocess", "multiprocessing")


def _imports(path: pathlib.Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.add(node.module.split(".")[0])
    return out


def test_no_module_imports_a_provider_sdk_or_a_network_library():
    for p in PKG.rglob("*.py"):
        found = _imports(p) & set(_FORBIDDEN_IMPORTS)
        assert found == set(), (p.name, found)
    # and the rest of the package's imports are the standard library and the translator itself
    allowed = {"__future__", "bisect", "collections", "dataclasses", "functools", "hashlib", "hmac", "json", "math", "pathlib", "re",
               "threading", "time", "typing", "unicodedata"}
    for p in PKG.rglob("*.py"):
        assert _imports(p) <= allowed, (p.name, _imports(p) - allowed)


def test_the_package_names_no_model_and_no_scratch_path():
    text = "\n".join(p.read_text(encoding="utf-8") for p in PKG.rglob("*") if p.suffix in (".py", ".json", ".md") and p.name != "prompt.md")
    assert not re.search(r"\b(?:claude|gpt-?\d|gemini|llama|mistral|haiku|sonnet|opus)\b", text, re.IGNORECASE)
    assert "/tmp/" not in text and "/root/" not in text and "session_" not in text


def test_no_release_path_calls_the_label_package_in_stage_1():
    trees = [ROOT / "src" / "epinoic_logic", ROOT / "overseer" / "src", ROOT / "flash-router" / "src", ROOT / "combinator" / "src",
             ROOT / "scripts"]
    users = []
    for tree in trees:
        if not tree.exists():
            continue
        for p in tree.rglob("*.py"):
            if PKG in p.parents:
                continue
            if "selfcert_label" in p.read_text(encoding="utf-8", errors="replace"):
                users.append(p.relative_to(ROOT).as_posix())
    assert users == []


def test_the_readme_says_what_the_package_does_and_does_not_do():
    text = " ".join((PKG / "README.md").read_text(encoding="utf-8").split())
    for phrase in ("Not yet wired.", "No provider is called.", "never releases, selects or labels an answer",
                   "never shows `none_named` to anyone as a pass", "never turns a failure of any kind into `none_named`",
                   "No label text reaches the IR"):
        assert phrase in text, phrase
