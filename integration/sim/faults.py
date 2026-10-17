"""The fault cases of the simulation (PROTOCOL.md section 14.5, step 4): the arena's OWN mutations and the 15 STEM mutations, applied
to the corpus answers by the arena's own functions, to be sent through the website path.

The arena's classification of each mutation (caught, the codes that name it, or a known miss) comes from the reference
run on the same copy (``reference.py``). A case is a mutated answer text for one corpus item; ``run_sim.py`` sends it
through the website path when that path exists and records whether it was refused there and with which codes. Nothing
here changes a mutation or a classification.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

__all__ = ["fault_cases"]


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


if __name__ == "__main__":
    print(json.dumps([{k: v for k, v in c.items() if k != "text"} for c in fault_cases(Path(sys.argv[1]), Path(sys.argv[2]))], indent=1))
