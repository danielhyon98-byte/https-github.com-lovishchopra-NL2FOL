"""Data discipline of the lexicon (design 3.10): classes of words, never sentences. No entry has more than six tokens or ends with
sentence punctuation, no idiom has two open-class words besides its head, and no entry equals a development record. The per-class
counts are printed so a review sees growth."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import epinoic_logic.selfcert.lexicon as lx

DATA = Path(__file__).parent / "data"


def _entries():
    raw = json.loads((Path(lx.__file__).parent / "lexicon.json").read_text(encoding="utf-8"))
    for fam, spec in raw["families"].items():
        for key, vals in spec.items():
            if key != "base":
                for v in vals:
                    yield f"family {fam} {key}", v.split(":")[0]
    for name, vals in raw["classes"].items():
        for v in vals:
            yield f"class {name}", v


def test_the_lexicon_loads_and_reports_its_classes(capsys):
    lex = lx.lexicon()
    for name, n in sorted(lex.counts.items()):
        print(f"{name}: {n}")
    assert lex.rules == "selfcert-2" and len(lex.words) > 1000  # (pin moved with the rules version, c3e: selfcert-1 to selfcert-2)


def test_no_entry_is_a_sentence():
    for where, entry in _entries():
        toks = lx.fold_word(entry).split()
        assert len(toks) <= 6, (where, entry)
        assert not entry.rstrip().endswith(("!", "?")) and not (entry.rstrip().endswith(".") and entry not in ("o.k.", "q.e.d.", "n.b.", "p.s.")), (where, entry)


def test_no_entry_equals_a_development_record():
    texts = set()
    for name in ("dev-positive.jsonl", "dev-negative.jsonl"):
        for line in (DATA / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                texts.add(" ".join(lx.fold_word(json.loads(line)["text"]).strip(" .!?").split()))
    # a single word equal to a one-word obfuscation record ("verified") is a class member, not a sentence: the rule is about phrases
    offending = [(w, e) for w, e in _entries() if len(e.split()) > 1 and " ".join(lx.fold_word(e).strip(" .!?").split()) in texts]
    assert offending == []


def test_a_sentence_in_disguise_refuses_to_load(tmp_path, monkeypatch):
    raw = json.loads((Path(lx.__file__).parent / "lexicon.json").read_text(encoding="utf-8"))
    raw["families"]["CHECK"]["idioms"].append("every figure in the essay checked twice over")
    (tmp_path / "lexicon.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setattr(lx, "_HERE", tmp_path)
    with pytest.raises(ImportError):
        lx._load()
