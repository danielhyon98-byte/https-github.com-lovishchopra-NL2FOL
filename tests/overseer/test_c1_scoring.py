"""Regression tests for the contained round c1 judges' scoring findings (``scripts/overseer/score_verdicts.py``; each
fails on the code before the fix):

* informed mode: a fault the dossier's auditor section already names was counted against an agent the pack tells not
  to accuse it again (recall 0/21, a "missed injected fault", kappa near 0 by construction). An informed verdict that
  obeys the pack must not lower recall; recall and kappa are measured where the agent has something to find;
* false accusations: unresolved accusations of meaning or other kinds on gold-clean transfers were counted false and
  warnings were invisible; they are now unadjudicated until a judge or human decides (an adjudication file), every
  severity is counted, and a true catch outside the gold is credited;
* the combination of duplicated instances' verdicts was never measured;
* the round's verdicts were self-reported files, yet nothing said so: a deployment-faithful gate now fails unless every
  assessed verdict was attested by the package's runner.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts" / "overseer"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import export_dossier as ED  # noqa: E402
import ovs_harness as H  # noqa: E402
import run_contained as RC  # noqa: E402
import score_verdicts as SV  # noqa: E402

from .test_harness_dossier_export import _shared, export_small, exported_pack, tamper_small  # noqa: E402,F401
from .test_harness_scoring import dossiers, names_the_auditor, one_group, write_replies  # noqa: E402


def _gold(export_dir: Path) -> dict:
    return json.loads((export_dir / "gold" / "gold.json").read_text())["variants"]


def _variant_of(export_dir: Path) -> dict[str, str]:
    """dossier digest -> variant id (from the export's issue records)."""
    out = {}
    for line in (export_dir / "issues.jsonl").read_text().splitlines():
        if line.strip():
            i = json.loads(line)
            out[i["issue"]["dossier_sha256"]] = i["variant_id"]
    return out


def names_what_the_checks_find(export_dir: Path):
    """A blind agent that finds exactly what the deterministic checks found (test code reading the gold's record of the
    audit as data, a stand-in for an agent that inspects the journal itself)."""
    gold, variant = _gold(export_dir), _variant_of(export_dir)

    def reply(d: dict) -> dict:
        findings = gold[variant[d["dossier_sha256"]]].get("auditor_findings", [])
        return names_the_auditor(dict(d, auditor={"findings": [dict(f, severity=f.get("severity") or "error") for f in findings]}))
    return reply


# ============================================================================================ informed mode
def test_already_decided_needs_one_of_the_faults_codes_naming_one_of_its_identifiers():
    gold = {"auditor_findings": [{"code": "OVS-CUST-001", "message_ids": ["m1"]}, {"code": "OVS-SYN-002", "claim_ids": ["s2"]}]}
    assert SV.already_decided({"expected_codes": ["OVS-CUST-001"], "identifiers": {"message_ids": ["m1"]}}, gold, {})
    assert SV.already_decided({"expected_codes": ["OVS-CUST-001"], "identifiers": {"receipt_ids": ["r1"]}}, gold, {"r1": "m1"})
    assert not SV.already_decided({"expected_codes": ["OVS-CUST-001"], "identifiers": {"message_ids": ["m2"]}}, gold, {})
    assert not SV.already_decided({"expected_codes": ["OVS-RCPT-001"], "identifiers": {"message_ids": ["m1"]}}, gold, {})
    assert SV.already_decided({"expected_codes": ["OVS-SYN-002"], "identifiers": {"claim_ids": ["s2"]}}, gold, {})
    assert not SV.already_decided({"expected_codes": [], "identifiers": {"message_ids": ["m1"]}}, gold, {})


def test_an_informed_verdict_that_does_not_re_accuse_an_auditor_finding_does_not_lower_recall(export_small, exported_pack, tmp_path):
    out, _s = export_small
    replies = write_replies(out, tmp_path / "replies", lambda d: H.verdict_dict(d), only=lambda d: d["mode"] == "informed")
    g = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies))
    assert g["verdicts_assessed"] > 0 and g["modes"] == {"informed": g["verdicts_assessed"]}
    # every checkable fault of these informed dossiers is in their auditor section: none is counted as missed
    assert all(v["n"] == 0 for v in g["recall"]["per_class"].values()) and g["recall"]["macro_average"] is None, g["recall"]
    assert sum(v["faults"] for v in g["already_decided"]["per_class"].values()) > 0
    assert all(v["re_accused"] == 0 for v in g["already_decided"]["per_class"].values())
    assert g["injection"]["missed_injected_fault"] == 0 and g["kappa_vs_auditor"] is None


def test_recall_and_kappa_are_measured_on_blind_dossiers(export_small, exported_pack, tmp_path):
    out, _s = export_small
    replies = write_replies(out, tmp_path / "replies", names_what_the_checks_find(out), only=lambda d: d["mode"] == "blind")
    g = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies))
    assert g["modes"] == {"blind": g["verdicts_assessed"]} and g["already_decided"]["per_class"] == {}
    assert g["recall"]["per_class"] and g["recall"]["by_mode"]["blind"]["n"] > 0
    assert g["recall"]["by_mode"]["blind"]["p"] == 1.0, g["recall"]
    assert g["kappa_vs_auditor"] is not None and g["kappa_vs_auditor"]["kappa"] == 1.0


def test_the_same_empty_verdict_on_a_blind_dossier_misses_its_faults(export_small, exported_pack, tmp_path):
    """The control: blind, an empty verdict finds nothing, and recall says so."""
    out, _s = export_small
    replies = write_replies(out, tmp_path / "replies", lambda d: H.verdict_dict(d), only=lambda d: d["mode"] == "blind")
    g = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies))
    blind = g["recall"]["by_mode"]["blind"]
    assert blind["n"] > 0 and blind["k"] == 0


# ============================================================================================ false accusations
def _clean_transfer_accusation(d: dict, *, kind: str = "other", severity: str = "warning") -> dict:
    t = next(t for t in d["transfers"] if t["message_id"])
    return H.verdict_dict(d, [H.accusation("a1", kind, [{"pointer": t["at"]}], severity=severity, message_ids=[t["message_id"]])])


def test_an_unresolved_meaning_accusation_on_a_clean_transfer_is_unadjudicated_not_false(export_small, exported_pack, tmp_path):
    out, _s = export_small
    gold, variant = _gold(out), _variant_of(out)
    clean = lambda d: d["mode"] == "blind" and gold[variant[d["dossier_sha256"]]]["clean"]  # noqa: E731
    replies = write_replies(out, tmp_path / "replies", _clean_transfer_accusation, only=clean)
    result = SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies)
    g = one_group(result)
    fa = g["false_accusations"]
    assert g["verdicts_assessed"] > 0 and fa["count"] == 0 and fa["clean_transfers_falsely_accused"] == 0
    assert fa["by_category"] == {"unadjudicated_meaning_or_other": g["verdicts_assessed"]}
    assert fa["by_severity"] == {"warning": {"unadjudicated_meaning_or_other": g["verdicts_assessed"]}}  # warnings are counted
    assert len(fa["unadjudicated"]) == g["verdicts_assessed"]
    gate = g["gates"]["false_accusation_rate_at_most_2pct_of_clean_transfers"]
    assert gate["state"] == "NOT MEASURED" and gate["value"]["lower"] == 0.0 and gate["value"]["upper"] > 0.02
    # a judge decides: half false, half true
    items = [{"dossier_sha256": r["dossier_sha256"], "accusation_id": r["accusation_id"], "verdict": "false" if i % 2 == 0 else "true", "by": "judge"}
             for i, r in enumerate(fa["unadjudicated"])]
    adj = tmp_path / "adjudications.json"
    adj.write_text(json.dumps({"format": SV.ADJUDICATIONS_FORMAT, "items": items}))
    g2 = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores2", replies_dir=replies, adjudications=adj))
    fa2 = g2["false_accusations"]
    n_false = sum(1 for i in items if i["verdict"] == "false")
    assert fa2["count"] == n_false and fa2["true_catches_outside_gold"] == len(items) - n_false and fa2["unadjudicated"] == []
    assert g2["gates"]["false_accusation_rate_at_most_2pct_of_clean_transfers"]["state"] == "FAIL"
    assert g2["precision"]["k"] == len(items) - n_false


def test_an_adjudication_file_of_another_format_is_refused(tmp_path):
    p = tmp_path / "adj.json"
    p.write_text(json.dumps({"items": []}))
    with pytest.raises(H.HarnessError):
        SV.load_adjudications(p)


# ============================================================================================ combination and attestation
@pytest.fixture(scope="session")
def export_two_agents(tmp_path_factory, exported_pack, tamper_small):
    def build():
        out = tmp_path_factory.mktemp("export-two") / "x"
        ED.run_export(out, exported_pack.directory, tamper_dir=tamper_small, modes=("informed",), lenses=["general", "custody_results"])
        return out
    return _shared("export-two", build)


def test_duplicated_instances_verdicts_are_combined_and_their_outcomes_follow_the_checks(export_two_agents, exported_pack, tmp_path):
    out = export_two_agents
    replies = write_replies(out, tmp_path / "replies", names_the_auditor)
    g = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies))
    c = g["combined"]
    assert c["combined_variants"] > 0 and c["outcomes_follow_member_checks"]
    assert all(v["agents"] == 2 and v["agreement"] for v in c["variants"].values())  # both instances name the same findings
    assert any(r["outcome"] == "confirmed" and r["support"] == 2 for v in c["variants"].values() for r in v["groups"])
    assert g["gates"]["combined_outcomes_follow_member_checks"]["state"] == "PASS"


def test_runner_attested_and_self_reported_verdicts_are_reported_apart(tmp_path, export_small, exported_pack):
    out, _s = export_small
    replies = write_replies(out, tmp_path / "replies", names_the_auditor, only=lambda d: d["mode"] == "informed")
    result = RC.run_contained(tmp_path / "run", pack_path=exported_pack.directory, tamper=False, replies_dir=replies, transfers=out)
    g = next(iter(result["replies"]["scores"]["per_pack"].values()))
    assert g["attestation"] == {"runner": g["verdicts_assessed"], "self_reported": 0} and g["verdicts_assessed"] > 0
    assert g["gates"]["deployment_faithful_every_verdict_runner_attested"]["state"] == "PASS"
    files = one_group(SV.run_scoring(out, exported_pack.directory, tmp_path / "scores", replies_dir=replies))
    assert files["attestation"]["self_reported"] == files["verdicts_assessed"] > 0
    assert files["gates"]["deployment_faithful_every_verdict_runner_attested"]["state"] == "FAIL"
