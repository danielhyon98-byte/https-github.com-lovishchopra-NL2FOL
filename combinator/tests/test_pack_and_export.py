"""The combinator agent's instructions (package data) and their exporter.

* the instructions say what the agent combines (the specialists' answers to one request), name exactly the five closed
  transformation words, keep certainty at most the weakest source's, keep every figure, unit, mark, date and quotation
  exactly, never carry a note, self-certification, decline or question back as a claim, list every dropped claim with
  its reason, never hide a contradiction, and ask for the exact output format and nothing else;
* the machine-readable format is the published contract's vocabulary, word for word, and names no model;
* the pack's identity is stable and changes with any byte of either file;
* ``python -m epinoic_combinator.export --out <dir>`` writes the files and a manifest that ``read_export`` accepts, and
  refuses, in one line and with exit status 2, a target it cannot write; a tampered export is refused.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from epinoic_combinator import NAME, __version__
from epinoic_combinator.contract import load_contract
from epinoic_combinator.export import ExportError, export, read_export
from epinoic_combinator.pack import PACK_FILES, load_pack, pack_sha256
from epinoic_combinator.runner import AGENT_CLAIM_KEYS, AGENT_CONFLICT_KEYS, AGENT_DROPPED_KEYS, AGENT_OUTPUT_KEYS

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
PACK = load_pack()
CONTRACT = load_contract()
INSTRUCTIONS = PACK.instructions
FORMAT = PACK.output_format
_MODEL_FAMILIES = re.compile(r"(?i)\b(?:claude|gpt|gemini|llama|mistral|mixtral|opus|sonnet|haiku|qwen|deepseek)\b")


def _flat(text: str) -> str:
    return " ".join(text.split())


@pytest.mark.parametrize("phrase", [
    "Several specialists have each answered the same student request",
    "Combine the specialists' answers to this one request, and nothing else.",
    "Certainty is never stronger than the weakest source.",
    "Keep every figure, unit, mark, date and quotation exactly as the source states it.",
    "Never round, convert, rescale or correct any of them.",
    "Never carry a note back as a claim.",
    "A self-certification",
    "a decline",
    "a question to the student or the router",
    "List every dropped claim with its reason.",
    "Never hide a contradiction.",
    "Exactly one JSON object and nothing else: no text before or after it, no code fence, no comment.",
    "Write the exact output format and nothing else.",
    "It names the kind of thing you did, never a description of the edit",
])
def test_the_instructions_say_what_the_agent_must_do(phrase):
    assert phrase in _flat(INSTRUCTIONS), phrase


def test_the_instructions_offer_exactly_the_five_closed_transformation_words():
    rows = re.findall(r"^\| `([a-z]+)` \|", INSTRUCTIONS, re.M)
    assert tuple(rows) == CONTRACT.transformations == ("carried", "paraphrased", "merged", "narrowed", "generalized")
    for word in ("new", "dropped"):
        assert f"| `{word}` |" not in INSTRUCTIONS, "a value the combinator never writes is never offered"
    for word in CONTRACT.certainty:
        assert f"`{word}`" in INSTRUCTIONS


def test_the_instructions_describe_the_format_the_runner_accepts():
    skeleton = INSTRUCTIONS.split("```")[1]
    for key in AGENT_OUTPUT_KEYS + AGENT_CLAIM_KEYS + AGENT_DROPPED_KEYS + AGENT_CONFLICT_KEYS:
        assert f'"{key}"' in skeleton, key


def test_the_output_format_is_the_published_contracts_vocabulary_word_for_word():
    assert list(FORMAT["transformation"]) == list(CONTRACT.transformations)
    assert FORMAT["transformation"] == CONTRACT.meanings
    assert FORMAT["certainty"] == list(CONTRACT.certainty) == ["established", "probable", "possible"]
    assert FORMAT["output"]["keys"] == list(AGENT_OUTPUT_KEYS) and FORMAT["output"]["required"] == ["claims"]
    assert FORMAT["claim"]["keys"] == list(AGENT_CLAIM_KEYS)
    assert FORMAT["instruction_pack"] == {"name": PACK.name, "version": PACK.version}
    assert any("never a description of the edit" in r and "INT-SYNTH-014" in r and "KIT-CB-003" in r for r in FORMAT["rules"])
    assert any("weakest" in r for r in FORMAT["rules"]) and any("figure, unit, mark, date and quotation" in r for r in FORMAT["rules"])
    assert any("self-certification" in r and "dropped" in r for r in FORMAT["rules"])


def test_the_pack_names_no_model():
    for name, data in PACK.files.items():
        assert not _MODEL_FAMILIES.search(data.decode("utf-8")), f"{name} names a model family (decision D23)"


def test_the_identity_is_stable_and_changes_with_any_byte_or_the_version():
    again = load_pack()
    assert again.identity() == PACK.identity() and re.fullmatch(r"[0-9a-f]{64}", PACK.sha256)
    for name in PACK_FILES:
        changed = {**PACK.files, name: PACK.files[name] + b" "}
        assert pack_sha256(PACK.name, PACK.version, changed) != PACK.sha256
    assert pack_sha256(PACK.name, PACK.version + ".1", PACK.files) != PACK.sha256  # another version, whatever this release's is
    assert PACK.identity() == {"name": "combinator-instructions", "version": "1.1", "sha256": PACK.sha256}


def test_export_writes_the_pack_and_a_manifest_read_export_accepts(tmp_path):
    manifest = export(tmp_path / "pack")
    for name in PACK_FILES:
        assert (tmp_path / "pack" / name).read_bytes() == PACK.files[name]
    assert manifest["instruction_pack"] == PACK.identity() and manifest["combinator"] == {"name": NAME, "version": __version__}
    assert manifest["contract_sha256"] == CONTRACT.sha256 and manifest["tier"] == "cheapest" and manifest["entry"] == "INSTRUCTIONS.md"
    read, files = read_export(tmp_path / "pack")
    assert read == manifest and files == dict(PACK.files)
    assert sorted(p.name for p in (tmp_path / "pack").iterdir()) == sorted([*PACK_FILES, "MANIFEST.json"])


def test_a_tampered_export_is_refused(tmp_path):
    export(tmp_path / "pack")
    (tmp_path / "pack" / "INSTRUCTIONS.md").write_text("Write anything you like.\n", encoding="utf-8")
    with pytest.raises(ExportError):
        read_export(tmp_path / "pack")
    with pytest.raises(ExportError):
        read_export(tmp_path / "nothing-here")


def _module(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["PYTHONPATH"] = str(SRC)
    return subprocess.run([sys.executable, "-m", "epinoic_combinator.export", *args], capture_output=True, text=True, env=env, cwd=cwd, timeout=120)


def test_the_exporter_runs_as_a_module_and_prints_its_manifest(tmp_path):
    out = _module("--out", str(tmp_path / "exported"), cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    printed = json.loads(out.stdout)
    assert printed == json.loads((tmp_path / "exported" / "MANIFEST.json").read_text(encoding="utf-8"))
    assert printed["instruction_pack"] == PACK.identity()


def test_the_exporter_refuses_a_target_it_cannot_write_in_one_line(tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x", encoding="utf-8")
    out = _module("--out", str(blocker), cwd=tmp_path)
    assert out.returncode == 2 and out.stdout == ""
    assert len(out.stderr.strip().splitlines()) == 1 and "Traceback" not in out.stderr and "is not a directory" in out.stderr
