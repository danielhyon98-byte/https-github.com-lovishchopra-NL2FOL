"""The kit's repositories by role and its agents pins (integration/COMPATIBILITY.json ``repositories``,
``kit_tag_repository``, ``agents_pins``; PROTOCOL.md section 13): every role the playbook uses is present, every pin
names a repository role and full identifiers, the pinned contracts are ones the kit accepts, the retarget changed no
contract of the compatibility set, and the records of the agents measurements (integration/agents/TESTED.json) ran the
pinned commits with the files the kit holds now."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COMPAT = json.loads((ROOT / "integration" / "COMPATIBILITY.json").read_text(encoding="utf-8"))
REPOS = COMPAT["repositories"]
PINS = COMPAT["agents_pins"]
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RECORD = json.loads((ROOT / "integration" / "agents" / "TESTED.json").read_text(encoding="utf-8"))
A2_FILES = {f"integration/agents/checks-port/{p}" for p in ("package.json", "src/envelope.js", "test/envelope.test.js", "test/check-portable.mjs",
                                                            "vectors/v1-answer.json", "vectors/v2-answer.json")}


def test_the_compatibility_set_names_every_repository_by_its_role():
    assert set(REPOS) == {"translator", "translator_development", "translator_mirror", "website", "agents", "agents_harness"}
    assert REPOS["translator"] == "https://github.com/Epinoic-AI/Epinoic-Logic-Translator"
    assert REPOS["translator_development"] == "https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL"
    # the organization repository's former path stays: a remote that still uses it is named as the translator role
    assert REPOS["translator_mirror"] == "https://github.com/Bruno-ios/Epinoic-Logic-Translator"
    assert REPOS["agents"] == "https://github.com/Epinoic-AI/Epinoic-Agent-Training"
    assert REPOS["agents_harness"] == "https://github.com/danielhyon98-byte/epinoic-agent-training-api-connector"
    # the kit tag stays on the development repository (decision D20); the organization repository gets no tag
    assert COMPAT["kit_tag"] == "integration-kit-v1" and COMPAT["kit_tag_repository"] == "translator_development"
    assert COMPAT["kit_tag_repository"] in REPOS


def test_every_pin_names_a_repository_role_and_full_identifiers():
    assert set(PINS) == {"runtime", "exporter", "knowledge_bases", "routing", "harness"}
    for name, pin in PINS.items():
        assert pin["repository"] in REPOS, name
        assert HEX40.match(pin["commit"]), name
    assert {k for k, p in PINS.items() if p["repository"] == "agents_harness"} == {"harness"}
    runtime = PINS["runtime"]
    assert HEX40.match(runtime["src_tree"]) and runtime["package"] == "@epinoic/specialist-runtime" and re.match(r"^\d+\.\d+\.\d+$", runtime["version"])
    bundle = PINS["knowledge_bases"]["history_bundle"]
    assert HEX64.match(bundle["sha256"]) and isinstance(bundle["bytes"], int) and bundle["bytes"] > 0
    assert bundle["path"] == "knowledge-bases/_bundles/history.full-context.txt"
    assert PINS["exporter"]["path"] == "specialist-runtime/tools/export-bundle.mjs"
    for name in ("runtime", "knowledge_bases", "routing", "harness"):
        assert PINS[name]["branch"], name


def test_the_pinned_contracts_are_ones_the_kit_accepts():
    pairs = {p["runtime"]: p for p in COMPAT["specialist_pairs"]}
    assert PINS["runtime"]["contract"] in pairs and PINS["harness"]["contract"] in pairs
    # the runtime pin (the runtime the website is to deploy) is the v2 pair (result and log schemas v2); the harness the v1 pair
    assert pairs[PINS["runtime"]["contract"]]["result"] == "epinoic.specialist-turn-result.v2"
    assert pairs[PINS["harness"]["contract"]]["result"] == "epinoic.specialist-turn-result.v1"


def test_the_retarget_changed_no_contract_of_the_compatibility_set():
    """The pairs and the routing contract the service, the Worker and the checks port read are those the kit was built
    with: the retarget adds roles and pins, it accepts nothing new."""
    assert COMPAT["specialist_pairs"] == [
        {"result": "epinoic.specialist-turn-result.v1", "runtime": "epinoic.specialist-runtime.v0.1.0", "log": "epinoic.specialist-turn-log.v1"},
        {"result": "epinoic.specialist-turn-result.v2", "runtime": "epinoic.specialist-runtime.v0.2.0", "log": "epinoic.specialist-turn-log.v2"},
    ]
    assert COMPAT["routing_contract"] == "epinoic.specialist-routing.v0.1.0"


def test_the_records_ran_the_pinned_commits():
    # A3 and A5 (the top level) are the harness's record: written and tested for the harness pin
    assert RECORD["agents_commit"] == PINS["harness"]["commit"]
    assert RECORD["role"] == "agents_harness" and RECORD["repository"] == REPOS["agents_harness"]
    a2 = RECORD["A2"]
    assert set(a2["files"]) == A2_FILES
    for path, digest in a2["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, (
            f"{path} changed after A2 was run on the archive copies: run it again (agents/PATCH-PLAN.md, A2) and update TESTED.json A2")
    runs = {(r["role"], r["commit"]): r for r in a2["runs"]}
    for role, pin in (("agents", PINS["runtime"]), ("agents_harness", PINS["harness"])):
        run = runs[(role, pin["commit"])]
        assert run["contract"] == pin["contract"], role
        assert run["fail"] == 0 and run["pass"] == run["tests"] > 0 and run["portable"] is True, role
    # the information runs are of other commits than the pins, and never stand for a pin
    pinned = {p["commit"] for p in PINS.values()}
    assert a2["information"] and all(r["commit"] not in pinned for r in a2["information"])


DECISIONS = (ROOT / "integration" / "DECISIONS.md").read_text(encoding="utf-8")


def _record(heading: str) -> str:
    start = DECISIONS.index(heading)
    end = DECISIONS.find("\n### ", start + len(heading))
    return re.sub(r"\s+", " ", DECISIONS[start:end if end > 0 else len(DECISIONS)])


def test_the_record_names_both_agents_repositories_and_the_tags_repository():
    """The retarget's decisions of record (integration/DECISIONS.md): the tag's repository is the development
    repository, the role COMPATIBILITY.json kit_tag_repository names (the organization's repository gets no tag); the
    agents repositories are named by role, each change on a branch of the repository it names, on Daniel's go; owner
    action 3 is split by repository; and the Spanish slugs belong to their repositories, the subject map unchanged."""
    from epinoic_logic.integration.compat import COMPATIBILITY
    assert COMPATIBILITY["kit_tag_repository"] == COMPAT["kit_tag_repository"] == "translator_development"
    d20 = _record("### D20. Repositories and visibility")
    assert "**The kit tag's repository:**" in d20
    assert "`repositories.translator_development`" in d20 and "`kit_tag_repository`" in d20 and "gets no tag and no pointer" in d20
    assert "**Agents repositories, by role:** `repositories.agents` is the retrained repository" in d20
    assert "`repositories.agents_harness` is the API connector" in d20 and "`agents_pins`" in d20
    assert "accepted when its src tree is the runtime pin's" in d20 and "never a new repository" in d20
    actions = re.sub(r"\s+", " ", DECISIONS[DECISIONS.index("## Owner actions, in M2 order"):])
    assert "**3a.**" in actions and "**3b.**" in actions and "`repositories.agents`" in actions and "`repositories.agents_harness`" in actions
    assert "Daniel approves the deployable runtime pin (`agents_pins.runtime`" in actions and "`agents_pins.knowledge_bases`" in actions
    d9 = _record("### D9 / D10. Subjects, slugs and STEM on the website")
    assert "`language-b-spanish` is the retrained repository's slug" in d9 and "`spanish-b` is the harness's" in d9
    assert "subject map, which is unchanged" in d9
    assert "Daniel applies A5 in the harness (`repositories.agents_harness`)" in DECISIONS


def test_no_kit_text_says_the_runtime_is_deployed():
    """Repair 1: nothing is deployed (integration/README.md), and the website vendors no runtime on its main; the
    retrained repository's runtime is the one the website is to deploy (the deployable runtime pin), never "the deployed
    runtime". A present-tense deployment claim is made nowhere in the kit's text or code."""
    claims = re.compile(r"\b(the )?deployed (specialist )?runtime\b|\bdeploys (this|the) (specialist )?runtime\b|"
                        r"\bknowledge base it deploys\b|\bruntime (is|was) deployed\b", re.I)
    kit = ROOT / "integration"
    paths = sorted(p for p in kit.rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".mjs", ".js", ".json", ".sh")
                   and "corpus" not in p.relative_to(kit).parts)
    assert len(paths) > 50
    found = [f"{p.relative_to(ROOT)}:{n}" for p in paths for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
             if claims.search(line)]
    assert not found, found
    flat = re.sub(r"\s+", " ", (kit / "agents" / "PATCH-PLAN.md").read_text(encoding="utf-8"))
    assert "the specialist runtime the website is to deploy, at the runtime pin `8ceba43`" in flat and "Nothing is deployed by the kit" in flat
    assert "the kit deploys nothing" in re.sub(r"\s+", " ", (kit / "sim" / "README.md").read_text(encoding="utf-8"))
