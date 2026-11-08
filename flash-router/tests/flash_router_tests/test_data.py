"""The flash router's versioned data files (``src/epinoic_flash_router/data/``): its rules (the features it reads, the
thresholds, the method table, the batch sizes) and its cost data, each with a digest.

- the manifest records every data file's digest (SHA-256 of the document's canonical JSON), and the files match it;
- a released file never changes: 0.1.0's rules and cost model are kept, pinned to the digests 0.1.0 reported in its
  identity, 0.2.0's to theirs, and 0.3.0's (the flash decision maker, architecture step 3) to theirs;
- the identity (hellos and every plan) reports the current files' digests and this release's version, which is the
  project's version and the release the manifest names for the current files;
- the loader refuses data the planners cannot read (a repeated key, a non-JSON constant, a missing parameter);
- the router reads no file but its data directory's manifest and the two files it names, at load, and a plan reads no
  file at all.
"""
from __future__ import annotations

import builtins
import hashlib
import json
import shutil
import tomllib
from pathlib import Path

import pytest

from epinoic_flash_router import __version__, port, rules

PROJECT = Path(__file__).resolve().parents[2]
DATA = Path(rules.DATA_DIR)
MANIFEST = json.loads((DATA / "MANIFEST.json").read_text(encoding="utf-8"))
#: The digests released files carry; a released file never changes (a re-tune is a new file and a new release).
RELEASED = {
    "rules-1.json": "177786eebe7d76009881cb4fa00cd2e0f9a9512926e0012117692ea09f0ef7f7",      # 0.1.0, as its identity reported it
    "cost-data-1.json": "228fe3e768b97c4807866cc973b7c24697283767a335c1db6a097a7ac3870e7e",  # 0.1.0, as its identity reported it
    "rules-2.json": "befadfa1abf55e7ba96c8cad654b8073de0f29afbb8a1676e092cd42593ee8c4",      # 0.2.0
    "cost-data-2.json": "a251369b4192d4b623281d1cd5ba77b9b0eaaab0b399187f07d257bd7de86860",  # 0.2.0
    "rules-3.json": "6750626527a7e1ddd7d82facefb86222a7881462b7fca9df3fdfd7e2cdd23896",      # 0.3.0, the flash decision maker
    "cost-data-3.json": "8b5747bc69997e9b030b7d70883cff38c46dcd3e86a4bef28a0dd5a791fe2d4e",  # 0.3.0, sizes of pack 2.0
}


def _canonical_sha(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def test_every_data_file_matches_its_manifest_and_every_released_file_its_pin():
    files = {p.name for p in DATA.glob("*.json")} - {"MANIFEST.json"}
    assert files == set(MANIFEST["files"]), "every data file is in the manifest, and only those"
    for name, entry in MANIFEST["files"].items():
        assert _canonical_sha(DATA / name) == entry["sha256"], name
        assert RELEASED.get(name) == entry["sha256"], f"{name}: a released file never changes; a new one is pinned here when it is released"
    assert MANIFEST["current"] == {"rules": "rules-3.json", "cost_data": "cost-data-3.json"}  # 0.3.0 (rules-2 and cost-data-2 before)


def test_the_identity_reports_the_current_files_and_this_release():
    current = MANIFEST["current"]
    assert rules.RULES_SHA256 == MANIFEST["files"][current["rules"]]["sha256"] == rules.rules_sha256()
    assert rules.COST_DATA_SHA256 == MANIFEST["files"][current["cost_data"]]["sha256"] == rules.cost_data_sha256()
    assert port.IDENTITY == {"name": "epinoic-flash-router", "version": __version__, "rules_sha256": rules.RULES_SHA256,
                             "cost_data_sha256": rules.COST_DATA_SHA256}
    project = tomllib.loads((PROJECT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["version"] == __version__ == MANIFEST["files"][current["rules"]]["release"] == MANIFEST["files"][current["cost_data"]]["release"]


def test_the_0_1_0_files_reproduce_the_0_1_0_identity_digests():
    """0.1.0 kept its rules and cost model as Python constants; they are kept as data, byte for byte their digest."""
    r1 = json.loads((DATA / "rules-1.json").read_text(encoding="utf-8"))
    assert set(r1) == {"rules", "parameters"} and r1["rules"].startswith("epinoic-flash-router rules/1\n")
    assert rules.rules_sha256(r1["rules"], r1["parameters"], document=r1) == RELEASED["rules-1.json"]
    assert rules.cost_data_sha256(json.loads((DATA / "cost-data-1.json").read_text(encoding="utf-8"))) == RELEASED["cost-data-1.json"]


def test_the_rules_file_holds_the_features_thresholds_method_table_and_batch_sizes():
    # 0.3.0 made rules-3 the current file: the assertions on rules-2 are kept on rules-2.json, which never changes, and the
    # current file is held to the same table and to the flash decision maker's section below
    doc = json.loads((DATA / "rules-2.json").read_text(encoding="utf-8"))
    assert doc["name"] == "epinoic-flash-router rules/2" and doc["rules"].startswith("epinoic-flash-router rules/2\n")
    assert set(doc["methods"]) == {"IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"}
    assert all({"meaning", "complete_reviews", "port", "pool"} <= set(m) for m in doc["methods"].values())
    assert doc["pool"] == {"escalated_reviewers": 2, "baseline_reviewers": 1, "record_weight": 2, "batch_size": None}
    assert doc["parameters"] == {"split_words": 900, "max_parts": 16, "max_reviews": 4, "hard_max_instances": 64, "context_max_bytes": 65536}
    assert set(doc["features"]) == {"port", "port_combined", "pool", "pool_limits"}
    assert set(doc["signals"]) == {"negative_statuses", "undecided_statuses", "stem_undecided_codes"}
    cost = rules.COST_MODEL
    assert "not measurements" in cost["basis"] and "recorded" in cost and "model" not in json.dumps(cost["recorded"]).lower().replace("no model was called", "")


def test_the_current_rules_file_holds_the_flash_decision_maker():
    """0.3.0 (architecture step 3): the current rules hold the flash decision maker (rules D1 to D7: in-depth examination or
    duplication, the cheapest that keeps accuracy, from the cost data), the N_FOLD reviewers of a combined answer (P8) and
    no split_words (the fit replaces the word threshold); the cost data holds every composition's system text of the pack
    it was measured with, the budgets and the dossier estimate, and names no model."""
    doc = rules.RULES_DOCUMENT
    assert doc["name"] == "epinoic-flash-router rules/3" and doc["rules"].startswith("epinoic-flash-router rules/3\n")
    for rule in ("D1.", "D2.", "D3.", "D4.", "D5.", "D6.", "D7.", "P8."):
        assert f"\n{rule} " in doc["rules"], rule
    assert set(doc["methods"]) == {"IN_DEPTH", "SPLIT", "DUPLICATE", "N_FOLD"}
    assert all({"meaning", "complete_reviews", "port", "pool"} <= set(m) for m in doc["methods"].values())
    assert doc["pool"] == {"escalated_reviewers": 2, "baseline_reviewers": 1, "record_weight": 2, "batch_size": None, "source_reviewers": 1,
                           "merged_reviewers": 1}
    assert doc["parameters"] == {"max_parts": 16, "max_reviews": 4, "hard_max_instances": 64, "context_max_bytes": 65536}
    d = doc["decision"]
    assert d["approaches"] == {"in_depth": ["IN_DEPTH"], "duplication": ["SPLIT", "DUPLICATE", "N_FOLD"]}
    assert d["order"] == ["tokens", "seconds", "calls", "method"] and d["pool_methods"] == ["IN_DEPTH", "DUPLICATE", "N_FOLD"]
    assert {"sources", "merged", "features"} <= set(doc["features"]["pool"]) and {"supplied_texts", "claims"} <= set(doc["features"]["port"])
    cost = rules.COST_MODEL
    assert set(cost["system_text_chars"]) == {"core", "core+stem", "core+translations", "core+stem+translations"}
    assert cost["system_text_chars"]["core"] < cost["system_text_chars"]["core+translations"] < cost["system_text_chars"]["core+stem"] \
        < cost["system_text_chars"]["core+stem+translations"]
    assert cost["recorded"]["system_text_pack"] == "overseer-knowledge-docs 2.0"
    assert (cost["chars_per_token"], cost["output_tokens"], cost["instance_budget_tokens"], cost["seconds_per_call"]) == (4, 8000, 200000, 30)
    assert "model" not in json.dumps(cost["recorded"]).lower()


@pytest.mark.parametrize("damage,match", [
    (lambda text: text.replace('"record_weight": 2', '"record_weight": 2, "record_weight": 2'), "repeats the key"),
    (lambda text: text.replace('"record_weight": 2', '"record_weight": NaN'), "not JSON"),
    (lambda text: json.dumps({**json.loads(text), "pool": {k: v for k, v in json.loads(text)["pool"].items() if k != "record_weight"}}),
     "record_weight"),
    (lambda text: text.replace('"escalated_reviewers": 2', '"escalated_reviewers": true'), "escalated_reviewers"),
])
def test_the_loader_refuses_data_the_planners_cannot_read(tmp_path, damage, match):
    dest = tmp_path / "data"
    shutil.copytree(DATA, dest)
    path = dest / MANIFEST["current"]["rules"]
    text = path.read_text(encoding="utf-8")
    damaged = damage(text)
    assert damaged != text, "the damage applies"
    path.write_text(damaged, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        rules.DataSet(str(dest))


def test_the_router_reads_only_its_data_directory_and_a_plan_reads_no_file(tmp_path, monkeypatch):
    real_open = builtins.open
    opened: list[str] = []

    def recording(file, *args, **kwargs):
        opened.append(str(file))
        return real_open(file, *args, **kwargs)
    monkeypatch.setattr(builtins, "open", recording)
    data = rules.DataSet()
    assert sorted(Path(p).name for p in opened) == sorted(["MANIFEST.json", data.rules_file, data.cost_data_file])
    assert all(Path(p).resolve().parent == DATA.resolve() for p in opened)

    def refuse(*args, **kwargs):
        raise AssertionError("a plan opened a file")
    monkeypatch.setattr(builtins, "open", refuse)
    request = json.loads((PROJECT / "tests" / "vectors" / "router-port" / "single-at-floor.json").read_text(encoding="utf-8"))["request"]
    port.plan(json.dumps(request))
    port.pool_plan(json.dumps({"schema": "epinoic.integration.pool-routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.1",
                               "items": [{"item_id": "d1", "repeated_faults": 0, "risk_signals": [], "risk_records": [], "advised": False}],
                               "limits": {"max_instances": 4, "per_instance_quota": 8, "profiles": ["standard"]}}))
    port.hello()
    port.pool_hello()
