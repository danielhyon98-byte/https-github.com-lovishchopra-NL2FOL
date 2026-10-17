"""The fault cases of the simulation (PROTOCOL.md section 14.5, step 4): the arena's OWN mutations and the 15 STEM mutations, applied
to the corpus answers by the arena's own functions, to be sent through the website path.

The arena's classification of each mutation (caught, the codes that name it, or a known miss) comes from the reference
run on the same copy (``reference.py``). A case is a mutated answer text for one corpus item; ``run_sim.py`` sends it
through the website path when that path exists and records whether it was refused there and with which codes. Nothing
here changes a mutation or a classification.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path
from typing import Iterable, Mapping

__all__ = ["fault_cases", "write_fault_round"]


def fault_cases(translator: Path, round_copy: Path) -> list[dict]:
    """``[{case, item, kind, text}]`` for every mutation the arena applies to every item of the copy."""
    sys.path.insert(0, str(translator / "scripts" / "arena"))
    import run_arena as ra
    cases = []
    for item in ra.load_items(round_copy / "specialists"):
        stem = item["_path"].stem
        texts = ra.supplied(item)
        for kind in ra.MUTATIONS:
            text, _expected = ra.mutate(item["response_text"], kind, texts)
            cases.append({"case": f"{stem}:{kind}", "item": stem, "kind": kind, "text": text})
        if ra.is_stem_subject(item["subject"]):
            for kind in ra.STEM_MUTATIONS:
                text, _expected = ra.stem_variant(item["response_text"], item["question"], kind)
                cases.append({"case": f"{stem}:{kind}", "item": stem, "kind": kind, "text": text})
    return cases


def write_fault_round(cases: Iterable[Mapping], round_copies: Mapping[str, Path], service_copy: Path) -> dict:
    """Index each case's mutated answer to its item's own fixtures in rounds that only the SERVICE loads (never the
    reference copy): one round per case, ``<service_copy>/sim-fault-<item>~<kind>/``, holding
    ``specialists/<item>.json`` (the item, under its own name, with the mutated ``response_text``) and
    ``translations/<item>.json`` (the item's fixtures, unchanged). The service then serves a mutated answer as the
    arena's mutation pass does: by claim id, bound to the claim text each fixture was produced for (a re-stated claim is
    refused as stale), and under the item's own arena request id (``req-<item>``: the item keeps its name). A case whose
    text another item's different fixtures already index is left out (the fixture corpus refuses two fixture sets for
    one answer text) and named in ``skipped``. Returns ``{written, skipped}``."""
    seen: dict[str, str] = {}
    docs: dict[str, str] = {}
    written, skipped = [], []
    for c in cases:
        src = round_copies[c["round"]]
        item_path = src / "specialists" / f"{c['item']}.json"
        tr_path = src / "translations" / f"{c['item']}.json"
        item = json.loads(item_path.read_text(encoding="utf-8"))
        doc = tr_path.read_text(encoding="utf-8") if tr_path.exists() else None
        for text, key in ((item["response_text"], f"{c['round']}/{c['item']}"), (c["text"], c["case"])):
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if digest in seen and docs.get(seen[digest]) != doc:
                break
            seen.setdefault(digest, key)
            docs.setdefault(key, doc)
        else:
            target = service_copy / f"sim-fault-{c['item']}~{c['kind']}"
            (target / "specialists").mkdir(parents=True, exist_ok=True)
            (target / "specialists" / f"{c['item']}.json").write_text(json.dumps({**item, "response_text": c["text"]}, ensure_ascii=False, indent=2) + "\n",
                                                                         encoding="utf-8")
            if doc is not None:
                (target / "translations").mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tr_path, target / "translations" / f"{c['item']}.json")
            written.append(c["case"])
            continue
        skipped.append({"case": c["case"], "reason": "another item's different fixtures already index this answer text"})
    return {"written": written, "skipped": skipped}


if __name__ == "__main__":
    print(json.dumps([{k: v for k, v in c.items() if k != "text"} for c in fault_cases(Path(sys.argv[1]), Path(sys.argv[2]))], indent=1))
