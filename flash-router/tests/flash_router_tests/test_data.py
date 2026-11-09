"""The flash router's versioned data files (``src/epinoic_flash_router/data/``): its rules (the features it reads, the
thresholds, the method table, the batch sizes) and its cost data, each with a digest.

- the manifest records every data file's digest (SHA-256 of the document's canonical JSON), and the files match it;
- a released file never changes: 0.1.0's rules and cost model are kept, pinned to the digests 0.1.0 reported in its
  identity, 0.2.0's to theirs, 0.3.0's (the flash decision maker, architecture step 3) to theirs, and 0.4.0's (the system
  text sizes of the overseer's pack 2.1, and the port's N_FOLD fit-checked) to theirs;
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
    "rules-4.json": "59b955429d7695de7081eca646f2e637069736f5d731b8e44e0846e01841d3ba",      # 0.4.0, the port's N_FOLD fit-checked
    "cost-data-4.json": "bc66e9e945a831456517f06c25955d7ddfdbdd476d0f13229a81600115a69600",  # 0.4.0, sizes of pack 2.1
}
#: The system text the overseer's pack 2.1 sends for each composition, in characters (its deployer README, section 4,
#: "Input budget"; the pack's loader builds exactly these): the sizes the current cost data must price every call with.
PACK_2_1_SYSTEM_TEXT_CHARS = {"core": 249054, "core+stem": 461507, "core+translations": 345025, "core+stem+translations": 557478}


def _canonical_sha(path: Path) -> str:
    doc = json.loads(path.read_text(encoding="utf-8"))
    return hashlib.sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def test_every_data_file_matches_its_manifest_and_every_released_file_its_pin():
    files = {p.name for p in DATA.glob("*.json")} - {"MANIFEST.json"}
    assert files == set(MANIFEST["files"]), "every data file is in the manifest, and only those"
    for name, entry in MANIFEST["files"].items():
        assert _canonical_sha(DATA / name) == entry["sha256"], name
        assert RELEASED.get(name) == entry["sha256"], f"{name}: a released file never changes; a new one is pinned here when it is released"
    # 0.4.0 (rules-3 and cost-data-3 before, from 0.3.0; rules-2 and cost-data-2 before them)
    assert MANIFEST["current"] == {"rules": "rules-4.json", "cost_data": "cost-data-4.json"}


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
    it was measured with, the budgets and the dossier estimate, and names no model.

    0.4.0 made rules-4 and cost-data-4 the current files: these assertions are kept on 0.3.0's files, which never change
    (as 0.3.0 kept rules-2's on rules-2.json), and the current files are held to the same and more by the next test."""
    doc = json.loads((DATA / "rules-3.json").read_text(encoding="utf-8"))
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
    cost = json.loads((DATA / "cost-data-3.json").read_text(encoding="utf-8"))
    assert set(cost["system_text_chars"]) == {"core", "core+stem", "core+translations", "core+stem+translations"}
    assert cost["system_text_chars"]["core"] < cost["system_text_chars"]["core+translations"] < cost["system_text_chars"]["core+stem"] \
        < cost["system_text_chars"]["core+stem+translations"]
    assert cost["recorded"]["system_text_pack"] == "overseer-knowledge-docs 2.0"
    assert (cost["chars_per_token"], cost["output_tokens"], cost["instance_budget_tokens"], cost["seconds_per_call"]) == (4, 8000, 200000, 30)
    assert "model" not in json.dumps(cost["recorded"]).lower()


def test_the_current_cost_data_prices_every_call_with_the_system_text_of_the_pack_the_overseer_sends():
    """0.4.0 (architecture lenses after arena round 8): cost data 3 recorded pack 2.0's system text while the overseer sent
    pack 2.1, 13,360 characters larger in every composition, so a dossier between the two fit limits was recorded as
    fitting (a need of 198,174 tokens of a budget of 200,000) when one instance could not read it whole (201,514 tokens:
    over_budget). The current cost data records pack 2.1's sizes exactly and names that pack; everything else it prices
    with is cost data 3's. The current rules (rules/4) are rules/3 with the port's N_FOLD fit-checked: the same sections
    and parameters, D1 to D7 and P8, D4 naming the pack the sizes are of, port rule 5 and D7 on the merged review's fit and
    where it is disclosed."""
    cost, before = rules.COST_MODEL, json.loads((DATA / "cost-data-3.json").read_text(encoding="utf-8"))
    assert MANIFEST["files"][MANIFEST["current"]["cost_data"]]["release"] == __version__ == "0.4.0"
    assert cost["name"] == "epinoic-flash-router/cost-data-4" and cost["recorded"]["system_text_pack"] == "overseer-knowledge-docs 2.1"
    assert cost["system_text_chars"] == PACK_2_1_SYSTEM_TEXT_CHARS
    assert all(cost["system_text_chars"][k] - before["system_text_chars"][k] == 13360 for k in PACK_2_1_SYSTEM_TEXT_CHARS)
    assert {k: v for k, v in cost.items() if k not in ("name", "system_text_chars", "recorded")} == \
        {k: v for k, v in before.items() if k not in ("name", "system_text_chars", "recorded")}
    assert "model" not in json.dumps(cost["recorded"]).lower()
    doc, previous = rules.RULES_DOCUMENT, json.loads((DATA / "rules-3.json").read_text(encoding="utf-8"))
    assert doc["name"] == "epinoic-flash-router rules/4" and doc["rules"].startswith("epinoic-flash-router rules/4\n") and doc["version"] == 4
    for rule in ("D1.", "D2.", "D3.", "D4.", "D5.", "D6.", "D7.", "1.", "5.", "7.", "P1.", "P8."):
        assert f"\n{rule} " in doc["rules"], rule
    assert "system_text_pack" in doc["rules"] and "Its merged review is decided by D4 and D5" in doc["rules"] \
        and "none for over_budget or split_to_fit" in doc["rules"]
    for key in ("decision", "features", "format", "parameters", "pool", "signals"):
        assert doc[key] == previous[key], key
    assert {k: v for k, v in doc["methods"].items() if k != "N_FOLD"} == {k: v for k, v in previous["methods"].items() if k != "N_FOLD"}


def test_the_finding_s_dossier_between_the_two_fit_limits_is_disclosed_over_budget(tmp_path):
    """The finding's case, through the released pool planner: one plain dossier of 525,000 characters in three transfers.
    Under cost data 3 (pack 2.0's sizes) one instance needed 198,174 tokens of 200,000 (fits, in_depth_cheapest); under the
    current cost data (pack 2.1's, which the pool sends) it needs 201,514: the decision says it does not fit and discloses
    over_budget, never shortening it, and the floor's one review is still planned."""
    def item_plan(router: port.FlashRouter) -> dict:
        request = {"schema": "epinoic.integration.pool-routing-request.v1", "protocol": "epinoic.integration.v1", "port_version": "1.2",
                   "items": [{"item_id": "d1", "repeated_faults": 0, "risk_signals": [], "risk_records": [], "advised": False,
                              "features": {"transfers": 3, "chars": 525000, "stem": False, "translations": 0}}],
                   "limits": {"max_instances": 8, "per_instance_quota": 8, "profiles": ["standard"]}}
        return json.loads(router.pool_plan(json.dumps(request)))["assignments"][0]
    now = item_plan(port.FlashRouter())
    assert (now["method"], now["instances"]) == ("IN_DEPTH", [1])
    d = now["decision"]
    assert (d["need_tokens"], d["budget_tokens"], d["fits"], d["reasons"]) == (201514, 200000, False, ["over_budget"])
    assert not any(c["keeps_accuracy"] for c in d["candidates"])
    released_0_3_0 = tmp_path / "data-0.3.0"  # the released 0.3.0 files, kept at their digests, made current in a copy
    shutil.copytree(DATA, released_0_3_0)
    manifest = json.loads((released_0_3_0 / "MANIFEST.json").read_text(encoding="utf-8"))
    manifest["current"] = {"rules": "rules-3.json", "cost_data": "cost-data-3.json"}
    (released_0_3_0 / "MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    old = item_plan(port.FlashRouter(str(released_0_3_0)))
    assert (old["method"], old["decision"]["need_tokens"], old["decision"]["fits"], old["decision"]["reasons"]) == \
        ("IN_DEPTH", 198174, True, ["in_depth_cheapest"])


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
