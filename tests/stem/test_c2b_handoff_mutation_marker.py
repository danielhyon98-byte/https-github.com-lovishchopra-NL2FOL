"""Round-9 clearance, second fix pass (c2b), handoff fixer: a STEM mutation on a list-item line (the STEM owner's handoff 3a; c2
stem-integration, c1 stem-integration#26; minor).

``stem_mutations._link_marker`` started the marker at the line start when no '=' precedes the operand, so the breadth answer cs-2's
'- 181 − 128 = 53' gave the marker '- 181 − 128 = 83': the delivered claim carries no list marker, so ``run_arena.injected_claim_ids``
found no claim and the INT-SUBJ-001 that names c1.2 was counted a miss. A list marker opening the line (the STEM front end's shape,
``stem.spans``) is now left out as a part label is; on the recorded rounds only cs-2's two STEM markers change (measured).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import run_arena as ra  # noqa: E402
import stem_mutations as sm  # noqa: E402

from ..core_hostile import SHAPES, one, sweep  # noqa: E402

CS2 = json.loads((Path(__file__).parents[1] / "fixtures" / "stem" / "round8" / "c1_answers.json").read_text(encoding="utf-8"))["answers"]["cs-2"]


def test_a_list_item_site_is_marked_without_its_list_marker():
    slip = sm.mutate_stem(CS2["response_text"], CS2["question"], "stem_arithmetic_slip")
    sub = sm.mutate_stem(CS2["response_text"], CS2["question"], "stem_substitution")
    assert slip.marker == "181 − 128 = 83" and "\n- 181 − 128 = 83\n" in slip.text  # the text keeps its list; the marker is the claim's
    assert sub.marker == "481 − 128" and "\n- 481 − 128 = 53\n" in sub.text
    # the claim the hub delivers carries no list marker: the old marker found none
    claims = [{"claim_id": "c1.1", "claim_text": "Subtract each place value that fits:"}, {"claim_id": "c1.2", "claim_text": "181 − 128 = 83"},
              {"claim_id": "c1.3", "claim_text": "53 − 32 = 21"}]
    assert ra.injected_claim_ids(claims, (slip.marker,)) == ["c1.2"]
    assert ra.injected_claim_ids(claims, ("- 181 − 128 = 83",)) == []
    # numbered and bulleted shapes alike, and a part label before the list marker
    for line, marker in (("* 181 − 128 = 53", "181 − 128 = 83"), ("• 181 − 128 = 53", "181 − 128 = 83"), ("3) 181 − 128 = 53", "181 − 128 = 83"),
                         ("(a) - 181 − 128 = 53", "181 − 128 = 83")):
        inj = sm.mutate_stem("Subtract each place value that fits:\n" + line + "\n", CS2["question"], "stem_arithmetic_slip")
        assert inj is not None and inj.marker == marker, (line, inj and inj.marker)
    # control: a sign that is the operand's own is never taken for a list marker
    neg = sm.mutate_stem("Work:\n-5 + 12 = 7\n", "Calculate -5 + 12.", "stem_arithmetic_slip")
    assert neg is not None and neg.marker == "-5 + 12 = 4", neg and neg.marker


def test_a_contained_round_credits_the_list_item_site_and_a_finding_naming_nothing_is_a_miss(tmp_path):
    (tmp_path / "specialists").mkdir()
    it = {"task_id": "cs-2", "subject": CS2["subject"], "agent_id": "computer-science-specialist", "task_type": "short_answer",
          "question": CS2["question"], "supplied_texts": [], "response_text": CS2["response_text"]}
    (tmp_path / "specialists" / "cs-2.json").write_text(json.dumps(it, ensure_ascii=False), encoding="utf-8")
    out = ra.run_round(tmp_path, without_overseer=True)
    assert not out["failures"], out["failures"]
    recs = {r["variant"]: r for r in out["records"]}
    for kind, quoted in (("stem_arithmetic_slip", "'181 − 128 = 83'"), ("stem_substitution", "'481 − 128 = 53'")):
        r = recs[kind]
        assert r["functional"] and r["injected_claim_ids"] == ["c1.2"], (kind, r.get("injected_claim_ids"))
        assert [f["code"] for f in r["named_by"]] == ["INT-SUBJ-001"] and r["named_by"][0]["claim_ids"] == ["c1.2"]
        assert quoted in r["named_by"][0]["message"]
    # control: a finding that names neither the claim nor the mutated words is not counted
    inj = ra.injection(CS2["response_text"], "stem_arithmetic_slip", question=CS2["question"])
    other = {"code": "INT-SUBJ-001", "severity": "error", "claim_ids": ["c1.3"], "message": "the written arithmetic '53 − 32 = 21' ..."}
    assert not ra.names_injection(other, inj, ["c1.2"])
    assert ra.names_injection({**other, "claim_ids": [], "message": "the written arithmetic '181 − 128 = 83' does not hold"}, inj, [])


def _marker_entries(text: str):
    """The mutation builder (and so ``_link_marker``) on the hostile text: alone, after list markers, and before a site."""
    q = "Calculate 181 − 128."
    for kind in sm.STEM_MUTATIONS:
        yield f"mutate_stem {kind}", lambda kind=kind: sm.mutate_stem(text + "\n- 181 − 128 = 53", q, kind)
        yield f"mutate_stem {kind} (list markers)", lambda kind=kind: sm.mutate_stem("- " * 4_000 + text[:4_000] + " 181 − 128 = 53", q, kind)


@pytest.mark.parametrize("shape", SHAPES)
def test_sweep_the_mutation_marker(shape):
    """Round-9 c2b class sweep (``scripts/arena/stem_mutations``, whose marker now leaves a list marker out)."""
    assert not sweep(_marker_entries, texts=one(shape))
