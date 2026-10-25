"""Dossier export of the contained harness (``scripts/overseer/export_dossier.py``): one dossier per task variant and
agent, issued under the identity of an EXPORTED pack from a rebuild of the transfer record, the issue records beside
them, and the ground truth kept apart in ``gold/`` (never inside a dossier).

Abuse cases: a tampered exported pack (nothing is issued), an altered transfer record, a non-empty output directory,
and the gold labels searched for in every dossier."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import export_dossier as ED  # noqa: E402
import ovs_harness as H  # noqa: E402
import score_verdicts as SV  # noqa: E402
import tamper as T  # noqa: E402

from epinoic_logic.overseer import Dossier, PackError, PackIdentity, verify_dossier_digest  # noqa: E402
from epinoic_logic.overseer.export import export_pack  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
HAS_R5 = ROUNDS is not None and (ROUNDS / "r5" / "specialists").is_dir()
HAS_R7 = ROUNDS is not None and (ROUNDS / "r7" / "specialists").is_dir()
GOLD_KEYS = {"expected_codes", "fault_id", "faults", "injection", "agent_scorable", "visibility", "expected_reasons", "arena_injection", "gold"}
CASES = ["T1", "T3", "T8", "T16", "T22"]


#: Built once per process and shared by every harness test module that imports these fixtures (an imported fixture is
#: registered again in the importing module, so the cache, not the fixture scope, keeps them from being rebuilt).
_SHARED: dict = {}


def _shared(key: str, build):
    if key not in _SHARED:
        _SHARED[key] = build()
    return _SHARED[key]


@pytest.fixture(scope="session")
def exported_pack(tmp_path_factory):
    return _shared("pack", lambda: export_pack(tmp_path_factory.mktemp("pack"), zip_archive=True))


@pytest.fixture(scope="session")
def tamper_small(tmp_path_factory, exported_pack):
    def build():
        out = tmp_path_factory.mktemp("tamper-small")
        T.run_suite(out, cases=CASES, targets=("synthetic",), pack_dir=exported_pack.directory)
        return out
    return _shared("tamper", build)


@pytest.fixture(scope="session")
def export_small(tmp_path_factory, exported_pack, tamper_small):
    def build():
        out = tmp_path_factory.mktemp("export") / "x"
        summary = ED.run_export(out, exported_pack.directory, tamper_dir=tamper_small, modes=("blind", "informed"), lenses=["general"])
        return out, summary
    return _shared("export", build)


def _keys(x, acc):
    if isinstance(x, dict):
        for k, v in x.items():
            acc.add(k)
            _keys(v, acc)
    elif isinstance(x, list):
        for v in x:
            _keys(v, acc)
    return acc


# ============================================================================================ dossiers
def test_one_dossier_per_variant_agent_and_mode_issued_under_the_exported_pack(export_small, exported_pack):
    out, summary = export_small
    issues = [json.loads(line) for line in (out / "issues.jsonl").read_text().splitlines()]
    assert summary["dossiers"] == len(issues) == summary["variants"] * 1 * 2  # one agent (lens general), two modes
    assert summary["pack"] == exported_pack.identity.model_dump() and summary["pack_source"] == str(exported_pack.directory)
    index = json.loads((out / "index.json").read_text())
    for i in issues:
        d = json.loads((out / i["dossier"]).read_text())
        Dossier.model_validate(d)
        assert verify_dossier_digest(d) and d["dossier_sha256"] == i["issue"]["dossier_sha256"] and index[d["dossier_sha256"]] == i["dossier"]
        assert d["agent_id"] == i["issue"]["agent_id"] and d["lens"] == i["issue"]["lens"] and d["mode"] == i["issue"]["mode"]
        assert PackIdentity.model_validate(d["pack"]) == exported_pack.identity
        assert (d["mode"] == "informed") == ("auditor" in d)


def test_no_gold_label_is_inside_any_dossier(export_small):
    out, _summary = export_small
    gold = json.loads((out / "gold" / "gold.json").read_text())["variants"]
    fault_ids = {f["fault_id"] for g in gold.values() for f in g["faults"] if f.get("origin") == "tamper"}
    assert fault_ids
    for p in (out / "dossiers").rglob("*.json"):
        text = p.read_text()
        d = json.loads(text)
        assert not (_keys(d, set()) & GOLD_KEYS), p
        assert not any(fid in text for fid in fault_ids), p
        assert "@synthetic" not in text


def test_the_gold_is_kept_apart_with_faults_controls_and_injections(export_small):
    out, _summary = export_small
    gold = json.loads((out / "gold" / "gold.json").read_text())
    assert gold["format"] == ED.GOLD_FORMAT
    v = gold["variants"]
    t1 = v["tamper--T1-synthetic"]
    assert not t1["clean"] and any(f["origin"] == "tamper" and f["class"] == "payload_altered" and f["visibility"] == "live" for f in t1["faults"])
    assert v["tamper--control-synthetic"]["clean"] and v["tamper--control-synthetic"]["origin"] == "tamper_control"
    assert v["tamper--T16d-synthetic"]["injection"] and any(f["class"] == "claim_not_in_response" for f in v["tamper--T16d-synthetic"]["faults"])
    assert v["tamper--T16b-synthetic"]["faults"] == [] and not v["tamper--T16b-synthetic"]["injection"]
    meaning = v["tamper--T22-comparison-synthetic"]["faults"]
    assert meaning and meaning[0]["agent_only"] and meaning[0]["class"] == "translation_unfaithful"
    for g in v.values():
        assert g["transfers"] == len(g["message_ids"]) and g["message_ids"]


def test_a_live_tampering_shows_only_in_the_informed_dossier(export_small):
    out, _summary = export_small
    issues = [json.loads(line) for line in (out / "issues.jsonl").read_text().splitlines()]
    t1 = {i["issue"]["mode"]: json.loads((out / i["dossier"]).read_text()) for i in issues if i["variant_id"] == "tamper--T1-synthetic" and i["issue"]["lens"] == "general"}
    assert "OVS-CUST-001" in {f["code"] for f in t1["informed"]["auditor"]["findings"]}
    assert "OVS-CUST-001" not in json.dumps(t1["blind"])


def test_dossiers_carry_each_translation_with_its_claim(export_small):
    """Translator oversight: every model-proposed translation reaches the agents beside its claim and the claims it cites."""
    from epinoic_logic.overseer import resolve_pointer
    out, _summary = export_small
    issues = [json.loads(line) for line in (out / "issues.jsonl").read_text().splitlines()]
    seen = 0
    for i in issues:
        if not i["variant_id"].startswith("tamper--T22"):
            continue
        d = json.loads((out / i["dossier"]).read_text())
        links = d["links"]["translations"]
        assert links, i["variant_id"]
        for link in links:
            claim = resolve_pointer(d, link["claim_pointer"])
            translation = resolve_pointer(d, link["translation_pointer"])
            assert claim["claim_id"] == link["claim_id"] and translation["claim_id"] == link["claim_id"]
            for cp in link["cited_claim_pointers"]:
                assert resolve_pointer(d, cp)["claim_id"]
            if link["claim_id"] == "en-point":
                assert translation["problem"]["claim_id"] == "en-point" and link["cited_claim_pointers"]
                seen += 1
    assert seen


def test_every_dossier_re_issues_to_the_same_digest_from_its_transfer_record(export_small, exported_pack):
    out, _summary = export_small
    export = SV.load_export(out)
    assessed = SV.assess_export(export, {exported_pack.identity}, lambda *a: ("no_reply", None, None, None, None))
    assert assessed and {a.status for a in assessed} == {"no_reply"}


# ============================================================================================ refusals
def _tampered_pack_copy(src: Path, dest: Path) -> Path:
    d = dest / src.name
    shutil.copytree(src, d)
    p = d / "08-never.md"
    p.write_bytes(p.read_bytes().replace(b"Never", b"Always", 1))
    return d


def test_a_tampered_exported_pack_issues_nothing(exported_pack, tamper_small, tmp_path):
    bad = _tampered_pack_copy(exported_pack.directory, tmp_path / "bad")
    with pytest.raises(PackError) as ei:
        ED.run_export(tmp_path / "out", bad, tamper_dir=tamper_small)
    assert ei.value.reason == "file_digest"
    assert not (tmp_path / "out" / "dossiers").exists() and not (tmp_path / "out" / "issues.jsonl").exists()
    assert ED.main(["--pack", str(bad), "--out", str(tmp_path / "out2"), "--tamper", str(tamper_small)]) == 2


def test_an_altered_transfer_record_is_refused(exported_pack, tamper_small, tmp_path):
    copy = tmp_path / "tamper"
    shutil.copytree(tamper_small, copy, ignore=shutil.ignore_patterns("pack"))
    m = json.loads((copy / "manifest.json").read_text())
    rec = next(e["record"] for e in m["faults"] if e["record"])
    audit = json.loads((copy / rec / "audit.json").read_text())
    audit["state"] = "AUDIT_PASSED"
    (copy / rec / "audit.json").write_text(json.dumps(audit))
    with pytest.raises(H.HarnessError, match="does not verify"):
        ED.run_export(tmp_path / "out", exported_pack.directory, tamper_dir=copy)


def test_the_output_directory_must_be_new_or_empty_and_outside_the_inputs(exported_pack, tamper_small, export_small, tmp_path):
    out, _summary = export_small
    with pytest.raises(H.HarnessError, match="not empty"):
        ED.run_export(out, exported_pack.directory, tamper_dir=tamper_small)
    with pytest.raises(H.HarnessError, match="overlaps"):
        ED.run_export(tamper_small / "inside", exported_pack.directory, tamper_dir=tamper_small)


def test_unknown_modes_and_lenses_are_refused(exported_pack, tamper_small, tmp_path):
    with pytest.raises(H.HarnessError, match="modes"):
        ED.run_export(tmp_path / "a", exported_pack.directory, tamper_dir=tamper_small, modes=("loud",))
    with pytest.raises(H.HarnessError, match="lenses"):
        ED.run_export(tmp_path / "b", exported_pack.directory, tamper_dir=tamper_small, lenses=["everything"])


# ============================================================================================ a recorded round (when present)
@pytest.mark.skipif(not HAS_R5, reason="the recorded round r5 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
def test_a_recorded_task_is_exported_with_its_arena_faults_as_gold(exported_pack, tmp_path):
    rounds = tmp_path / "rounds"
    H.mini_round(ROUNDS / "r5", rounds / "r5", ["hi-t9"])
    summary = ED.run_export(tmp_path / "out", exported_pack.directory, rounds_root=rounds, rounds=["r5"], lenses=["general"])
    functional, total = summary["rounds"]["r5"]["functional"].split("/")
    assert functional == total
    gold = json.loads((tmp_path / "out" / "gold" / "gold.json").read_text())["variants"]
    assert summary["rounds"]["r5"]["channels"] == len(gold) >= 2
    genuine = gold["r5--hi-t9"]
    assert genuine["origin"] == "arena_genuine" and all(f["origin"] == "auditor" for f in genuine["faults"])
    assert {f["expected_codes"][0] for f in genuine["faults"]} <= {"OVS-DIV-001", "OVS-DIV-002"}  # true rule findings only
    muts = [g for k, g in gold.items() if g["origin"] == "arena_mutation"]
    assert len(muts) == len(gold) - 1 and all(g["arena_injection"]["functional"] for g in muts)
    assert (tmp_path / "out" / "rounds" / "r5" / "results.json").exists() and not (tmp_path / "out" / "rounds" / "r5" / "specialists").exists()


@pytest.mark.skipif(not HAS_R7, reason="the recorded round r7 is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
def test_a_round_recorded_before_the_merge_is_exported_re_keyed_so_its_stem_translations_reach_the_agents(exported_pack, tmp_path):
    """Finding (d) of the re-test of the fourth repair: no dossier built from a recorded round carried a STEM translation,
    because r7 keys its recorded fixtures by the claim ids of its time and the exporter had no re-keyed pass. A task of r7
    (ch-t13, the chemistry parser's ``s`` ids) is exported: its genuine pass and mutations carry no STEM translation (the
    gap), and its re-keyed pass (rule recorded-ids) issues dossiers that do, each link resolving to its STEM claim and a
    translation that carries a problem, its gold a genuine control's, and each dossier re-issued to the same digest from
    its transfer record."""
    from epinoic_logic.overseer import resolve_pointer
    rounds = tmp_path / "rounds"
    H.mini_round(ROUNDS / "r7", rounds / "r7", ["ch-t13"])
    summary = ED.run_export(tmp_path / "out", exported_pack.directory, rounds_root=rounds, rounds=["r7"], lenses=["translation_fidelity"])
    rk = summary["rounds"]["r7"]["rekeyed"]
    assert rk["rule"] == H.REKEY_RULE and rk["channels"] == 1 and rk["fixtures_rekeyed"] > 0 and rk["stem_translations"]["dossiers"] == 1
    assert summary["stem_translations"]["claims"] >= 1 and set(summary["stem_translations"]["by_letter"]) == {"s"}
    out = tmp_path / "out"
    issues = [json.loads(line) for line in (out / "issues.jsonl").read_text().splitlines()]
    plain = [i for i in issues if not i["variant_id"].startswith("r7-rekeyed--")]
    rekeyed = [i for i in issues if i["variant_id"].startswith("r7-rekeyed--")]
    assert plain and rekeyed
    assert all(ED.stem_translations(json.loads((out / i["dossier"]).read_text())) == [] for i in plain)  # the gap the re-test found
    stem = 0
    for i in rekeyed:
        d = json.loads((out / i["dossier"]).read_text())
        for cid in ED.stem_translations(d):
            link = next(x for x in d["links"]["translations"] if x["claim_id"] == cid)
            assert resolve_pointer(d, link["claim_pointer"])["claim_id"] == cid and resolve_pointer(d, link["translation_pointer"])["problem"]["claim_id"] == cid
            stem += 1
    assert stem >= 1
    gold = json.loads((out / "gold" / "gold.json").read_text())["variants"]
    assert {g["origin"] for v, g in gold.items() if v.startswith("r7-rekeyed--")} == {"arena_genuine_rekeyed"}
    export = SV.load_export(out)
    assessed = SV.assess_export(export, {exported_pack.identity}, lambda *a: ("no_reply", None, None, None, None))
    assert len(assessed) == len(issues)  # every dossier, the re-keyed ones included, re-issued to its digest from its record

