"""The committed fold table is the one ``scripts/selfcert/build_fold_table.py`` builds on this interpreter (no silent drift with a
Unicode upgrade), and its digest is part of the rules digest bound into the policy identity."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from epinoic_logic.selfcert import rules_digest
from epinoic_logic.selfcert.normalise import fold, fold_table

ROOT = Path(__file__).resolve().parents[2]


def test_the_build_script_reports_no_drift():
    out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "selfcert" / "build_fold_table.py"), "--check"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_obfuscated_alphabets_fold_to_their_letters():
    for text, folded in (("\U0001F185\U0001F174\U0001F181\U0001F178\U0001F175\U0001F178\U0001F174\U0001F173", "VERIFIED"),
                         ("ᴠᴇʀɪꜰɪᴇᴅ", "verified"), ("Ｃｈｅｃｋｅｄ", "Checked"),
                         ("Ⓥⓔⓡⓘⓕⓘⓔⓓ", "Verified"), ("Ver​ified", "Verified"),
                         ("Аll", "All"), ("V E R I F I E D", "VERIFIED"), ("C-H-E-C-K-E-D", "CHECKED")):
        assert fold(text).text.replace(" ", "").startswith(folded.replace(" ", "")), (text, fold(text).text)


def test_a_genuine_word_of_another_script_is_left_as_written():
    assert fold("Жить").text == "Жить"
    assert fold("θ = π/2").text == "θ = π/2"


def test_the_rules_digest_changes_with_the_table(tmp_path, monkeypatch):
    import epinoic_logic.selfcert as sc
    before = rules_digest()
    copy = tmp_path / "selfcert"
    copy.mkdir()
    for name in ("lexicon.json", "fold_table.json"):
        (copy / name).write_bytes((Path(sc.__file__).parent / name).read_bytes())
    table = json.loads((copy / "fold_table.json").read_text(encoding="utf-8"))
    table["fold"]["0041"] = "B"
    (copy / "fold_table.json").write_text(json.dumps(table), encoding="utf-8")
    monkeypatch.setattr(sc, "_HERE", copy)
    assert rules_digest() != before
    assert fold_table()["fold"]  # the loaded table is unchanged by the copy
