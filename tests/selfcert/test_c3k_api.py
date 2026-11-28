"""The public API 1.5 (c3k, stage 2a of the meaning check), each expected value fixed here: the area ``label`` exports what an
integrator needs to configure the self-certification meaning label and what the overseer's label gate and the sub-projects' test
fixtures need, the TEST-ONLY names are marked in ``docs/PUBLIC_API.md``, nothing in it releases or labels an answer on its own,
and ``labelled_text`` hands on exactly the text a channel event's label read, or None."""
from __future__ import annotations

import hashlib
import importlib
import types
from pathlib import Path

import pytest

import epinoic_logic.api as api
from epinoic_logic import selfcert_label

ROOT = Path(__file__).resolve().parents[2]

LABEL_NAMES = {"LABEL_VERSION", "label_digest", "model_digest", "Labeller", "UnconfiguredLabeller", "RecordedLabeller",
               "ProviderLabeller", "default_labeller", "set_default_labeller", "restore_default_labeller", "revalidate",
               "Revalidation", "LabelResult", "STATES", "KINDS", "labelled_text", "ReaderBackedLabeller", "ScriptedLabeller",
               "check_t24"}


def test_the_api_is_1_5_with_the_label_area():
    assert api.API_VERSION == "1.5"
    assert api.AREAS[-1] == "label" and "label" in api.exports_table()
    assert set(api.exports_table()["label"]) == LABEL_NAMES


def test_every_label_name_resolves_to_the_label_package():
    label = importlib.import_module("epinoic_logic.api.label")
    for name in LABEL_NAMES - {"labelled_text"}:
        mod, attr = label.EXPORTS[name]
        assert getattr(label, name) is getattr(importlib.import_module(mod), attr), name
        assert mod.startswith("epinoic_logic.selfcert_label"), name
    assert label.LABEL_VERSION == selfcert_label.LABEL_VERSION
    assert label.TEST_ONLY == {"ReaderBackedLabeller", "ScriptedLabeller", "check_t24"}


def test_the_default_labeller_is_read_at_call_time_through_the_api():
    from epinoic_logic.api.label import ScriptedLabeller, default_labeller, set_default_labeller
    before = default_labeller()
    mine = ScriptedLabeller([])
    previous = set_default_labeller(mine)
    try:
        assert default_labeller() is mine  # the same function, reading the switch each time it is called
    finally:
        set_default_labeller(previous)
    assert type(default_labeller()) is type(before)


def test_nothing_in_the_label_area_builds_or_runs_a_label_call():
    label = importlib.import_module("epinoic_logic.api.label")
    # (the input builder, the reply validator and the calling machinery stay inside the package: an attached component never labels
    # an answer itself)
    assert not {"build_input", "validate_reply", "CallingLabeller", "CachingLabeller", "BudgetedLabeller",
                "CircuitBreakerLabeller", "LabelHandle", "Reply"} & set(label.EXPORTS)


def test_the_generated_document_matches_and_marks_the_test_only_names():
    doc = (ROOT / "docs" / "PUBLIC_API.md").read_text(encoding="utf-8")
    assert doc == api.markdown()
    for name in ("ReaderBackedLabeller", "ScriptedLabeller", "check_t24"):
        assert f"| `{name}` (TEST-ONLY) |" in doc, name
    assert "| `UnconfiguredLabeller` |" in doc and "(TEST-ONLY)" not in doc.split("| `UnconfiguredLabeller`", 1)[1].split("\n", 1)[0]
    assert "they are not moved into the reader in this release" in doc  # the frames stay where stage 1 built them


def _event(text, digest="auto"):
    d = hashlib.sha256(text.encode("utf-8")).hexdigest() if (digest == "auto" and isinstance(text, str)) else digest
    return types.SimpleNamespace(labelled_text=text, labelled_text_sha256=None if digest is None else d)


@pytest.mark.parametrize("event,expected", [
    (_event("The treaty was signed in 1919."), "The treaty was signed in 1919."),
    # rewritten stricter in the check round of stage 2a (interface (c)): a text with no SHA-256 beside it is not bound to the record
    # and is never handed on as the labelled text (before: it was handed on unchecked, and the label gate skipped its check)
    (_event("Texto sin digest", digest=None), None),
    (_event("The treaty was signed in 1919.", digest="0" * 64), None),  # a text that is not the labelled one
    (_event(None), None), (_event(b"bytes"), None), (types.SimpleNamespace(), None), (None, None), (object(), None),
])
def test_labelled_text_hands_on_exactly_the_labelled_text_or_none(event, expected):
    from epinoic_logic.api.label import labelled_text
    assert labelled_text(event) == expected
