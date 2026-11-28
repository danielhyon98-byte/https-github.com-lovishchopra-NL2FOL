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
    # (rewritten, stage 2a: selfcert-label-1 was committed in stage 1, so the package's next change needs a new version)
    assert L.LABEL_VERSION == "selfcert-label-2"
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
#: History: selfcert-label-1 was committed in stage 1 (its pair is kept here as a recorded entry and never re-pinned).
#: selfcert-label-2 (stage 2a, the KIT step: the package wired, with the rule reader's selfcert-5 and policy 2026.11-v9 in its
#: digest) is not yet committed: its pin tracks the package as built until this round's commit; after that commit any move of
#: the digest needs a new LABEL_VERSION and a new pin here, never a new digest under selfcert-label-2.
PINNED = {
    "selfcert-label-1": "42ade34271d6aac7ffe021610696d819383c4b57c70458fe58d63c2beb13c680",
    "selfcert-label-2": "b8832db4a926eb2bd1083eb0d61f388801070b39985b69cf425dce48c469c142",
}


def _check_pin(version: str, digest: str) -> None:
    """The T17 rule: the version must be pinned and its digest must be the pinned one."""
    assert version in PINNED, "a new label version needs its digest pinned here"
    assert digest == PINNED[version], "the label digest moved without a version bump"


def test_t17_the_version_and_the_digest_are_pinned_together():
    # (re-pinned by the KIT step of stage 2a: R2 bumped LABEL_VERSION to selfcert-label-2 because selfcert-label-1 was committed
    # in stage 1 and the package changed; the selfcert-label-1 pair stays below as the recorded history entry)
    assert L.LABEL_VERSION == "selfcert-label-2"
    assert PINNED["selfcert-label-2"] == "b8832db4a926eb2bd1083eb0d61f388801070b39985b69cf425dce48c469c142"
    _check_pin(L.LABEL_VERSION, L.label_digest())


def test_t17_the_committed_history_entry_is_kept_and_never_reused():
    """selfcert-label-1 was committed in stage 1 with this digest. Its pair stays pinned as history; the current package's digest
    under that old version fails the pin (a version is never reused for another digest)."""
    assert PINNED["selfcert-label-1"] == "42ade34271d6aac7ffe021610696d819383c4b57c70458fe58d63c2beb13c680"
    assert PINNED["selfcert-label-1"] != PINNED["selfcert-label-2"]
    assert list(PINNED) == ["selfcert-label-1", "selfcert-label-2"]  # versions only grow; the current one is the last
    assert list(PINNED)[-1] == L.LABEL_VERSION
    with pytest.raises(AssertionError, match="moved without a version bump"):
        _check_pin("selfcert-label-1", L.label_digest())


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
        _check_pin("selfcert-label-3", L.label_digest(copy))  # (selfcert-label-2 is pinned since stage 2a; the next is unpinned)


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


#: Every module outside the package that names it, pinned by name (stage 2a). Rewritten from the stage-1 rule "no module uses
#: the package" (true until stage 2a wired it) to this stricter rule: the users are exactly the public API, the release paths of
#: meaning-check design 2.5.1 and 2.5.7 (with the integration's settings, handshake and display of the label), the policy
#: identity (engine/identity.py, since policy 2026.11-v9), the arena's label tools and the test fixtures; a module outside this
#: set that starts naming the label package fails here, and so does a release path that stops. Each release path must also
#: still call the labeller or the label gate (RELEASE_PATH_CALLS below).
LABEL_USERS = {
    # the public API (API 1.5): the only way the sub-projects reach the label
    "src/epinoic_logic/api/__init__.py", "src/epinoic_logic/api/label.py",
    # the policy identity (design 2.5.9, KIT step of stage 2a): policy_manifest()'s selfcert_meaning_label entry
    "src/epinoic_logic/engine/identity.py",
    # 2.5.1 hub and channel: the label runs at respond and relay; the hub carries its labeller
    "src/epinoic_logic/branches/hub.py", "src/epinoic_logic/channel/bus.py",
    # 2.5.1 service step 4 and 2.5.7 service turn: submit, guard, decide (KIT-DL-006 / KIT-DL-014), settings, handshake
    "src/epinoic_logic/integration/turn.py", "src/epinoic_logic/integration/delivery.py",
    "src/epinoic_logic/integration/label.py", "src/epinoic_logic/integration/settings.py",
    "src/epinoic_logic/integration/preflight.py", "src/epinoic_logic/integration/handshake.py",
    "src/epinoic_logic/integration/capabilities.py", "src/epinoic_logic/integration/protocol.py",
    "src/epinoic_logic/integration/errors.py", "src/epinoic_logic/integration/runtime.py",
    "src/epinoic_logic/integration/verifier.py", "src/epinoic_logic/integration/overseer_port.py",
    # 2.5.7 overseer paths (through epinoic_logic.api only): label gate, fallback, formal, not-checked, router decision,
    # combined answer, port, and the auditor's OVS-FID-010
    "overseer/src/epinoic_overseer/label_gate.py", "overseer/src/epinoic_overseer/delivery_policy.py",
    "overseer/src/epinoic_overseer/consolidate.py", "overseer/src/epinoic_overseer/policy.py",
    "overseer/src/epinoic_overseer/port.py", "overseer/src/epinoic_overseer/checks/label.py",
    # the auditor's shadow replay, which labels with the live channel's labeller (the hub's ``selfcert_labeller``)
    "overseer/src/epinoic_overseer/checks/shadow.py",
    # 2.5.7 arena replay and the label tools of design 3.4 and 3.5
    "scripts/arena/run_arena.py", "scripts/arena/relay_peer.py", "scripts/arena/stress_arena.py",
    "scripts/arena/arena_labels.py", "scripts/arena/list_labels.py", "scripts/arena/bind_labels.py",
    "scripts/arena/measure_labels.py", "scripts/arena/conftest.py",
}


#: The test fixtures that install the faithful fake through ``set_default_labeller`` (interface (a)): the translator's own
#: conftest files (R2) and the combinator's and flash router's (R6, through ``epinoic_logic.api`` only). No other conftest of
#: these trees names the package. The overseer's conftest (``overseer/tests/overseer_tests/conftest.py``) is pinned by the
#: overseer's own suite (``test_c3k_label_gate.py::test_the_overseers_test_fixture_that_names_the_label_package_is_pinned``):
#: the isolation rule of ``tests/channel/test_without_the_overseer.py`` forbids a translator test to build a path to the
#: overseer's tests.
LABEL_FIXTURES = {
    "tests/conftest.py", "tests/selfcert_label/conftest.py", "combinator/tests/conftest.py",
}

#: Each release path (design 2.5.1 and 2.5.7) and what it must call: a function or method of that name, or a call that hands the
#: labeller on by that keyword. Every name listed must occur in the module (a release path that stops calling fails here).
RELEASE_PATH_CALLS = {
    # the hub hands its labeller to every channel it opens; the channel labels at respond and relay (submit, then result), with
    # the default labeller looked up at use time when none is given
    "src/epinoic_logic/branches/hub.py": {"selfcert_labeller"},
    "src/epinoic_logic/channel/bus.py": {"default_labeller", "submit", "result"},
    # the service's step 4 submits the answer; its guard reads the result (KIT-DL-006 / KIT-DL-014)
    "src/epinoic_logic/integration/turn.py": {"default_labeller", "submit"},
    # the overseer's one gate re-validates the journaled record with the labeller's own key and model digest
    "overseer/src/epinoic_overseer/label_gate.py": {"label_gate", "default_labeller", "revalidate_record"},
    # fallback, not-checked and formal paths; the router's documented decision; the combined answer (label_refusal calls label_gate)
    "overseer/src/epinoic_overseer/delivery_policy.py": {"label_refusal", "labeller_of"},
    "overseer/src/epinoic_overseer/consolidate.py": {"label_refusal", "labeller_of"},
    "overseer/src/epinoic_overseer/policy.py": {"label_refusal"},
    # the auditor's OVS-FID-010 and its shadow replay (with the live channel's labeller)
    "overseer/src/epinoic_overseer/checks/label.py": {"label_gate"},
    "overseer/src/epinoic_overseer/checks/shadow.py": {"selfcert_labeller"},
    # the arena replay and the peer relay hand the chosen labeller to the hub
    "scripts/arena/run_arena.py": {"selfcert_labeller"},
    "scripts/arena/relay_peer.py": {"labeller"},
    "scripts/arena/stress_arena.py": {"selfcert_labeller"},
}

#: The release paths that only map the label's refusal to their own outcome: each names the unavailable refusal.
RELEASE_PATH_MAPPINGS = {
    "overseer/src/epinoic_overseer/port.py",          # REFUSAL_RULES: unavailable -> selfcert_label_unavailable
    "src/epinoic_logic/integration/delivery.py",      # decide: selfcert_label_unavailable -> KIT-DL-014
}


def _python_users(trees) -> set[str]:
    users = set()
    for tree in trees:
        if not tree.exists():
            continue
        for p in tree.rglob("*.py"):
            if PKG in p.parents:
                continue
            if "selfcert_label" in p.read_text(encoding="utf-8", errors="replace"):
                users.add(p.relative_to(ROOT).as_posix())
    return users


def _calls(rel: str) -> set[str]:
    """The function and method names a module calls, and the keywords its calls pass."""
    out = set()
    for node in ast.walk(ast.parse((ROOT / rel).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute):
                out.add(f.attr)
            elif isinstance(f, ast.Name):
                out.add(f.id)
            out |= {k.arg for k in node.keywords if k.arg}
    return out


def test_the_label_package_is_used_by_exactly_the_release_paths_pinned_here():
    trees = [ROOT / "src" / "epinoic_logic", ROOT / "overseer" / "src", ROOT / "flash-router" / "src", ROOT / "combinator" / "src",
             ROOT / "scripts"]
    users = _python_users(trees)
    assert users == LABEL_USERS
    # design 2.5.1 (4): never the translator, the flash router or the combinator sub-project; of the engine, only the policy
    # identity, which reads the label's version and digest and nothing else (no label output reaches the IR, the compiler or Z3)
    assert not any(u.startswith(("src/epinoic_logic/translate/", "flash-router/", "combinator/", "src/epinoic_logic/ir/"))
                   for u in users)
    assert {u for u in users if u.startswith("src/epinoic_logic/engine/")} == {"src/epinoic_logic/engine/identity.py"}
    imported = set()
    for node in ast.walk(ast.parse((ROOT / "src/epinoic_logic/engine/identity.py").read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and "selfcert_label" in node.module:
            imported |= {a.name for a in node.names}
    assert imported == {"LABEL_VERSION", "label_digest"}


def test_the_test_fixtures_that_name_the_label_package_are_pinned():
    # Repair after the stage-2a verification: this test also walked the overseer's test tree, a path the translator's isolation
    # rule (tests/channel/test_without_the_overseer.py) forbids. The overseer's half of the pin moved, unchanged in strength, to
    # the overseer's own suite (test_c3k_label_gate.py), which also pins that its conftest installs the fake through the switch.
    conftests = set()
    for tree in (ROOT / "tests", ROOT / "combinator" / "tests", ROOT / "flash-router" / "tests"):
        for p in tree.rglob("conftest.py"):
            if "selfcert_label" in p.read_text(encoding="utf-8", errors="replace"):
                conftests.add(p.relative_to(ROOT).as_posix())
    assert conftests == LABEL_FIXTURES
    # the session fixtures install the faithful fake through the one switch (the label package's own conftest only scripts labels)
    for rel in LABEL_FIXTURES - {"tests/selfcert_label/conftest.py"}:
        assert "set_default_labeller" in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_each_release_path_calls_the_labeller_or_the_label_gate():
    assert set(RELEASE_PATH_CALLS) | RELEASE_PATH_MAPPINGS <= LABEL_USERS
    for rel, names in RELEASE_PATH_CALLS.items():
        missing = names - _calls(rel)
        assert not missing, (rel, sorted(missing))
    # label_refusal, which the overseer's release paths call, goes through label_gate itself
    tree = ast.parse((ROOT / "overseer/src/epinoic_overseer/label_gate.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "label_refusal")
    assert any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == "label_gate" for c in ast.walk(fn))
    for rel in RELEASE_PATH_MAPPINGS:
        assert "selfcert_label_unavailable" in (ROOT / rel).read_text(encoding="utf-8"), rel


def test_the_overseer_reaches_the_label_only_through_the_public_api():
    for rel in sorted(u for u in LABEL_USERS if u.startswith("overseer/")):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "epinoic_logic.selfcert_label" not in text, rel
        assert "from epinoic_logic import selfcert_label" not in text, rel


def test_the_readme_says_what_the_package_does_and_does_not_do():
    # Rewritten in stage 2a: the stage-1 README said "Not yet wired.", which the wiring made false, and this test pinned the
    # false sentence. It now pins the stage-2a statement, and also that the README no longer says the package is unwired.
    text = " ".join((PKG / "README.md").read_text(encoding="utf-8").split())
    assert "not wired" not in text.lower() and "not yet wired" not in text.lower()
    assert "stage 1: NOT wired" not in (PKG / "__init__.py").read_text(encoding="utf-8")
    # (KIT step of stage 2a: the status sentence the owner's run fixed, kept beside every earlier phrase)
    for phrase in ("Wired with the unconfigured default: every answer the reader passes is withheld until labels are configured; "
                   "no label is recorded or measured yet.", "Wired into every release path (stage 2a).", "The production default stays `UnconfiguredLabeller`",
                   "No label is recorded and nothing is measured in this stage", "No provider is called.", "never releases, selects or labels an answer",
                   "never shows `none_named` to anyone as a pass", "never turns a failure of any kind into `none_named`",
                   "No label text reaches the IR"):
        assert phrase in text, phrase
