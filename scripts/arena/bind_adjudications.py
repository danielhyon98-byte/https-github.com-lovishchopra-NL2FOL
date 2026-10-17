#!/usr/bin/env python3
"""Bind an adjudicator's judgments of translation fidelity to the round's recorded translations.

Usage: python bind_adjudications.py <round> <judgments.json> [--adjudicator NAME] [--force]

<judgments.json> is a list of judgments as the adjudicator wrote them while judging the round's translations/*.json:
{"file": "hi-t13.json" (or "task_id" / "task": the task id), "claim_id": "h1.4", "verdict": "faithful" | "unfaithful"
('F' / 'U' accepted), "cause": optional}. Each is written to <round>/adjudications/translation_fidelity.json with the digest
of the recorded fixture it judged (``translation_sha256``, run_arena.fixture_sha256) and, when the translations file records
it, the digest of the claim text that fixture was produced for (``claim_text_sha256``). run_arena.py then applies a judgment
only to that translation and that text: the judgments are frozen with the translations they judged, and a change to a
fixture or to the claim it is served for leaves the judgment unapplied (listed, never counted) until it is judged again.

Run it when the judgments are made, against the fixtures that were judged. A judgment of a claim with no recorded fixture
is written without digests and run_arena.py lists it as not applicable. The round directory is never otherwise changed,
and an existing adjudications file is replaced only with --force.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_arena import ADJUDICATIONS_FILE, VERDICT_SPELLINGS, fixture_sha256  # noqa: E402


def _file_stem(j: dict, task_files: dict[str, list[str]]) -> str | None:
    """The specialist file a judgment names: its ``file``, else the one file whose task id it gives (None when none or several)."""
    if j.get("file"):
        return j["file"][:-5] if j["file"].endswith(".json") else j["file"]
    files = task_files.get(j.get("task_id") or j.get("task")) or []
    return files[0] if len(files) == 1 else None


def bind(round_dir: Path, judgments: list[dict], adjudicator: str | None = None) -> dict:
    """The adjudications file's content for ``judgments`` on ``round_dir`` (nothing is written)."""
    translations = {p.stem: json.loads(p.read_text()) for p in sorted((round_dir / "translations").glob("*.json"))}
    task_files: dict[str, list[str]] = {}
    for p in sorted((round_dir / "specialists").glob("*.json")):
        task_files.setdefault(json.loads(p.read_text()).get("task_id"), []).append(p.stem)
    out: list[dict] = []
    unbound: list[str] = []
    for j in judgments:
        name = j.get("file") or j.get("task_id") or j.get("task")
        stem = _file_stem(j, task_files)
        entry = {"file": f"{stem}.json" if stem else None, **({} if stem else {"task_id": name}), "claim_id": j.get("claim_id"),
                 "verdict": VERDICT_SPELLINGS.get(str(j.get("verdict", "")).strip().lower(), j.get("verdict"))}
        if j.get("cause"):
            entry["cause"] = j["cause"]
        tr = translations.get(stem or "") or {}
        fixture = (tr.get("claims") or {}).get(j.get("claim_id"))
        if fixture is not None:
            entry["translation_sha256"] = fixture_sha256(fixture)
            digest = (tr.get("claim_text_sha256") or {}).get(j.get("claim_id"))
            if digest:
                entry["claim_text_sha256"] = digest
        else:
            unbound.append(f"{name} {j.get('claim_id')}")
        out.append({k: v for k, v in entry.items() if v is not None})
    return {"adjudicator": adjudicator, "judgments": out, "bound_to_a_recorded_fixture": len(out) - len(unbound), "without_a_recorded_fixture": unbound}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Bind judgments of translation fidelity to a round's recorded translations.")
    ap.add_argument("round_dir", type=Path)
    ap.add_argument("judgments", type=Path)
    ap.add_argument("--adjudicator", default=None, help="who judged (kept in the file)")
    ap.add_argument("--force", action="store_true", help="replace an existing adjudications file")
    args = ap.parse_args(argv)
    target = args.round_dir / ADJUDICATIONS_FILE
    if target.exists() and not args.force:
        print(f"{target} exists; pass --force to replace it")
        return 2
    data = json.loads(args.judgments.read_text())
    content = bind(args.round_dir, data.get("judgments", []) if isinstance(data, dict) else data, args.adjudicator)
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(content, indent=2, ensure_ascii=False))
    print(f"{len(content['judgments'])} judgments written to {target}: {content['bound_to_a_recorded_fixture']} bound to the recorded fixture they judged, "
          f"{len(content['without_a_recorded_fixture'])} without a recorded fixture")
    return 0


if __name__ == "__main__":
    sys.exit(main())
