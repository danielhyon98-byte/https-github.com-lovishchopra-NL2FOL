"""The quotation roles (``adapters.markdown.quotation_role`` / ``cited_quotation_spans``): the call sites that check or
attribute quotations read ``cited_quotation_spans``, which keeps only the spans whose role is ``quotation``. While the roles
were a stub every span was a quotation; with the roles filled in (B5, B6), only closed frames give a span another role, and
the role of every recorded span is pinned. Pinned on the recorded specialist answers and the development cases."""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from epinoic_logic.adapters import markdown
from epinoic_logic.adapters.markdown import QUOTATION_ROLES, cited_quotation_spans, find_quotation_spans, quotation_role, quotation_task

from ..argdiag_cases import load_cases

TESTS = Path(__file__).resolve().parent.parent
SRC = Path(markdown.__file__).resolve().parent.parent


def _texts() -> list[tuple[str, object]]:
    """Every recorded text with the task type of the item it belongs to (repair round 4: the roles are read in the task)."""
    out: list[tuple[str, object]] = []
    for name in ("r4_specialists.json", "r5_specialists.json", "r6_specialists.json", "r7_specialists.json"):
        data = json.loads((TESTS / "adapters" / "data" / name).read_text(encoding="utf-8"))
        items = data.get("items", data) if isinstance(data, dict) else data
        for item in (items.values() if isinstance(items, dict) else items):
            if isinstance(item, dict):
                task = item.get("task_type")
                out += [(item[k], task) for k in ("response_text", "question") if isinstance(item.get(k), str)]
                out += [(t["text"], task) for t in item.get("supplied_texts", []) if isinstance(t, dict) and isinstance(t.get("text"), str)]
    for case in load_cases():
        task = case["task_type"]
        out += [(case["answer"], task), (case["request"], task), *((t["text"], task) for t in case.get("supplied_texts", []))]
        out += [(c["text"], task) for c in case.get("report_claims", [])]
    return out


def test_the_roles_are_closed():
    assert QUOTATION_ROLES == ("quotation", "correction", "suggestion", "mention")


#: Every recorded span whose role is not ``quotation``, with its count: the corrected forms after an arrow in the Spanish
#: feedback (each recorded three times: the case's answer and two report claims) and the quoted function words of the English
#: answers ('no "like" or "as"', 'the conjunction "But"'). Every other recorded span is a quotation and is checked. Repair
#: round 4 (ADV4-03) added one entry: 'Also avoid "dropped", because ...' in the Psychology answers (three records) advises
#: against a word and attributes it to no text, the frame the round's absence mentions name ('avoids "very"'). Repair round 5
#: (ADV5-08) added one entry, 'the text never says "ayudar"' in a Spanish reading answer (one record), read as a mention for
#: its reporting verb under a negation; close round 3 (INV-QR-1) rewrote it stricter: that reading also took 'not only says
#: "..."' out of the checks, so it was reverted to the committed base's reading, and the span is a quotation again (checked;
#: the core pack's own absent-word reading still keeps it out of CORE-SRC-003). Every other role is unchanged and still
#: pinned exactly.
PINNED_OTHER_ROLES = {
    ("correction", "*Al principio, estaba un poco nervioso*"): 3, ("correction", "*El verano pasado trabajé*"): 3,
    ("correction", "*Fue muy agotador*"): 3, ("correction", "*También*"): 3, ("correction", "*la gente es muy agradecida*"): 3,
    ("correction", "*os recomiendo que participéis*"): 3, ("correction", "*para ayudar*"): 3,
    ("correction", "*te recomiendo que participes*"): 3, ("correction", "*una mujer muy simpática*"): 3,
    ("mention", "But"): 1, ("mention", "as"): 10, ("mention", "like"): 7, ("mention", "dropped"): 3,
}


def test_only_closed_frames_take_a_recorded_span_out_of_the_cited_quotations():
    """Rewritten when the roles were filled in (argdiag-1, B5 and B6), to a stricter rule than the stub's "every span is a
    quotation": ``cited_quotation_spans`` is exactly the spans whose role is ``quotation``, and the role of every recorded span
    is pinned, so a frame that takes one more span out of the checks (or puts one back) fails here. Rewritten again in
    repair round 4 (INV-Q1) to a stricter rule: each recorded text is read in its own item's task type, the pinned roles are
    unchanged, and read in an analysis task no recorded span is a correction or a suggestion."""
    from collections import Counter
    texts = _texts()
    assert len(texts) > 300
    spans = 0
    others: Counter = Counter()
    for text, task in texts:
        found = find_quotation_spans(text)
        with quotation_task(task if isinstance(task, str) else None):
            roles = [quotation_role(text, s, e) for s, e, _inner in found]
            assert cited_quotation_spans(text) == [sp for sp, role in zip(found, roles) if role == "quotation"]
        assert all(role in QUOTATION_ROLES for role in roles)
        others.update((role, inner) for (_s, _e, inner), role in zip(found, roles) if role != "quotation")
        spans += len(found)
        with quotation_task("analytical_paragraph"):
            assert not {quotation_role(text, s, e) for s, e, _inner in found} & {"correction", "suggestion"}
    assert spans > 200                                     # the fixtures really hold quotations
    assert dict(others) == PINNED_OTHER_ROLES


@pytest.mark.parametrize("module, functions", [
    ("channel/bus.py", {"_uncredited_quotations", "_foreign_credits", "_fold_findings", "_request_echo"}),
    ("integrity/ledger.py", {"unlocated_quotations", "quotation_form_differences", "misattributed_quotations"}),
    ("adapters/sources.py", {"_credit_to_unsupplied", "_mention_governs"}),
    ("branches/packs.py", {"_quotation_ref_disagreements", "_unverifiable_quotations", "_misattributed_quotations"}),
    ("adapters/history_specialist/parser.py", {"quotations_in"}),
    ("branches/generic_parser.py", {"quotations_in"}),
    ("adapters/stem_specialist/parser.py", {"_quotations"}),
    ("adapters/english_specialist/parser.py", {"_iter_cited_quotes"}),
])
def test_the_quotation_checks_and_attributions_read_cited_spans(module, functions):
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in functions:
            names = {n.id if isinstance(n, ast.Name) else n.attr for n in ast.walk(node) if isinstance(n, (ast.Name, ast.Attribute))}
            found[node.name] = ("cited_quotation_spans" in names, "find_quotation_spans" in names)
    assert set(found) == functions
    for name, (cited, plain) in found.items():
        assert cited and not plain, name


def test_masking_and_position_tests_keep_every_quoted_span():
    # a span of another role must stay masked: masking reads find_quotation_spans
    tree = ast.parse((SRC / "adapters" / "markdown.py").read_text(encoding="utf-8"))
    mask = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "mask_quotations")
    assert "find_quotation_spans" in {n.id for n in ast.walk(mask) if isinstance(n, ast.Name)}
