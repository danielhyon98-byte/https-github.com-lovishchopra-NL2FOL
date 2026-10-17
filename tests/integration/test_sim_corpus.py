"""The synthetic simulation corpus: regenerated, never edited (build_corpus.py --check), labelled synthetic, in the
arena round format, with every fixture bound to its claim text (no FIXTURES_UNBOUND), and with at least 24 simulated
users whose turns name corpus items."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from epinoic_logic.integration.verifier import FixtureCorpus

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "integration" / "sim" / "corpus" / "synthetic" / "s1"


def test_the_corpus_is_what_the_builder_writes():
    proc = subprocess.run([sys.executable, str(ROOT / "integration" / "tools" / "build_corpus.py"), "--check"], capture_output=True, text=True, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_corpus_is_synthetic_and_in_the_arena_round_format():
    items = sorted((CORPUS / "specialists").glob("*.json"))
    assert len(items) == 6
    for p in items:
        item = json.loads(p.read_text(encoding="utf-8"))
        assert set(item) == {"task_id", "subject", "agent_id", "task_type", "question", "supplied_texts", "response_text"}
        assert item["question"].startswith("SYNTHETIC:") and item["task_id"] == p.stem
        tr = json.loads((CORPUS / "translations" / p.name).read_text(encoding="utf-8"))
        assert set(tr) == {"report_id", "claims", "claim_text_sha256"} and set(tr["claims"]) == set(tr["claim_text_sha256"])
        assert all(obj["interpretation"]["reading"].startswith("SYNTHETIC") for obj in tr["claims"].values())
    tasks = json.loads((CORPUS / "tasks.json").read_text(encoding="utf-8"))
    assert sorted(t["task_id"] for t in tasks) == sorted(p.stem for p in items)
    assert all("response_text" not in t for t in tasks)
    assert FixtureCorpus.load(CORPUS).item_for("0" * 64) is None


def test_at_least_24_simulated_users_with_sessions_of_one_to_four_turns():
    doc = json.loads((ROOT / "integration" / "sim" / "users.json").read_text(encoding="utf-8"))
    users = doc["users"]
    assert len(users) >= 24 and len({u["user"] for u in users}) == len(users)
    items = {p.stem for p in (CORPUS / "specialists").glob("*.json")}
    for u in users:
        assert 1 <= len(u["turns"]) <= 4 and u["path"] in ("website", "agents")
        for t in u["turns"]:
            assert t["item"] in items and (t.get("second") is None or t["second"] in items)
    actions = {t["action"] for u in users for t in u["turns"]}
    assert {"send", "follow_up", "retry", "cancel", "concurrent", "service_stopped", "service_slow", "clock_past_cache", "handshake_mismatch",
            "subject_unavailable", "mixed_subject", "stem", "duplicate_clean", "duplicate_conflicting", "combined"} <= actions
