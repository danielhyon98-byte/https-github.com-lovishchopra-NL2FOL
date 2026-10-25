"""Versioned prompt texts for the model-backed providers.

Prompts are package data (``*.md``). A prompt version string is bound into every
``ProviderInfo`` so a translation can be traced to the exact instructions used.
Bump ``TRANSLATOR_VERSION`` in ``epinoic_logic.version`` when a prompt changes.
"""
from __future__ import annotations

import re
from importlib import resources

#: The prompts in use. A changed prompt is a new file and a new version; earlier files stay packaged unchanged so a
#: recorded ``prompt_version`` always names the exact instructions it was produced with. ``translate_v2``: exactness and
#: stated precision from the wording, task authority validated by code, definitions against assertions, units and
#: percentages, retries that may not change the claim. ``translate_v3`` (in use): ``translate_v2`` plus the ten rules
#: that mark the writer's own links for the argument diagnosis (a ``link: <connective>`` note on each writer's step, one
#: symbol per proposition, two symbols and an EQUIVOCATION flag for one word in two senses, scope and causal words kept,
#: excerpts for task and text facts, assumed constants as assumptions, never ``verified``). ``review_v2``: the reviewer
#: is shown the task, the supporting claims, the supplied texts and the premise-to-source mapping, and judges every
#: premise against them.
TRANSLATE_PROMPT_VERSION = "translate_v3"
REVIEW_PROMPT_VERSION = "review_v2"

#: A prompt name, matched against the whole name (``fullmatch``: a trailing newline is not part of a name).
_NAME_RE = re.compile(r"[a-z][a-z0-9_]{0,63}")


def load_prompt(name: str) -> str:
    """Return the text of the packaged prompt ``name`` (for example ``translate_v1``)."""
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise ValueError(f"invalid prompt name {name!r}")
    path = resources.files(__package__).joinpath(f"{name}.md")
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"prompt {name!r} is not packaged") from exc
