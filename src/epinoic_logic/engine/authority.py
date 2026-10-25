"""Premise authority: which groundings establish a premise and which leave it unresolved.

A grounding kind is a claim about where a premise comes from. The claim is made by whoever wrote the problem, usually a
translation model, so it confers nothing by itself. Only an application-created record confers task or source
authority: ``grounding.verified=True``, set in this process by a deterministic check that validated the premise's whole
content against an immutable task field (the parsed request), a source span (a supplied text) or an independently
computed derivation. Figures occurring in a record validate no relation that combines them: a premise relating symbols
(``speed = d / 8``) is validated only by a record that states that relation, and otherwise stays unverified.
A payload that arrives as data cannot certify itself: :func:`epinoic_logic.engine.runner.verify` discards any
``verified=True`` it carries (``E505``), and the HTTP service refuses it.

Every premise a result relies on therefore lands in exactly one place:

* **established**: its grounding was verified positively by such a check (any kind except the writer's own steps);
* ``ungrounded_dependencies``: no grounding, one of the writer's own steps (:data:`UNGROUNDED_KINDS`), a failed check
  (``verified=False``), or a quotation no check verified;
* ``unverified_dependencies``: every other grounding no check verified, whatever authority its kind claims. A
  model-labelled ``arithmetic_fact``, ``task_setting`` or ``rubric_rule`` is listed here like an unchecked
  ``supplied_text``: the label is a proposal, never a validation, so an unsupported premise can never be hidden by
  choosing a trusted-sounding kind.

These rules decide what a result reports as resting on unresolved premises; they never change its status. Formal
entailment and permission to release an answer stay separate (:mod:`.release`).

Circularity (``E112``, and the translation layer's circularity refusal, which reads the same rule) follows the same
principle: a premise that restates the conclusion is the writer's own unless a check in this process established it
(:func:`assumed_grounding` is ``not has_authority``). Restating a task setting, a rubric rule or a text excerpt that a check
verified is a transcription; restating one that only carries the label (a ``task_setting`` with no record checked, a
``supplied_text`` with no excerpt, a ``knowledge_document``) is a circle, since nothing but the claim's own premise
supports it. A label never confers authority, here or anywhere else.
"""
from __future__ import annotations

from typing import Any, Optional

from ..ir.schema import Grounding, Problem

__all__ = [
    "UNGROUNDED_KINDS",
    "TASK_GIVEN_KINDS",
    "SOURCE_KINDS",
    "CHECKABLE_KINDS",
    "is_ungrounded",
    "is_unverified",
    "has_authority",
    "assumed_grounding",
    "ungrounded_dependencies",
    "unverified_dependencies",
    "dependency_policy",
]

#: Grounding kinds that never establish a premise: they are the writer's own steps.
UNGROUNDED_KINDS = frozenset({"assumption", "specialist_inference", "general_knowledge"})
#: Kinds that name the task as their authority (a figure, a setting or a rubric rule given with the task). The name is
#: a proposal: such a premise is established only when a check verified it, and is otherwise an unverified dependency.
TASK_GIVEN_KINDS = frozenset({"arithmetic_fact", "task_setting", "rubric_rule"})
#: Kinds that name a text as their authority; the same rule applies.
SOURCE_KINDS = frozenset({"quotation", "supplied_text", "knowledge_document", "library_source"})
#: Kinds a deterministic check can verify positively; unchecked, they count as ungrounded.
CHECKABLE_KINDS = frozenset({"quotation"})


def is_ungrounded(grounding: Optional[Grounding]) -> bool:
    """True when a grounding does not establish its premise.

    Missing grounding, the inferential kinds, a failed check (``verified is False``)
    and a checkable kind (quotation) that no check verified positively are all
    ungrounded. The engine never trusts an asserted ``verified=True`` on a payload that
    arrived as data; see :func:`epinoic_logic.engine.runner.verify` for the raw path.
    """
    if grounding is None or grounding.kind in UNGROUNDED_KINDS or grounding.verified is False:
        return True
    return grounding.kind in CHECKABLE_KINDS and grounding.verified is not True


def has_authority(grounding: Optional[Grounding]) -> bool:
    """True when an application check verified the grounding positively (task, source or derivation authority)."""
    return grounding is not None and grounding.verified is True and grounding.kind not in UNGROUNDED_KINDS


def is_unverified(grounding: Optional[Grounding]) -> bool:
    """True for a grounding that claims task or source authority that no check validated (``verified`` is ``None``).

    No kind is exempt: an unchecked ``arithmetic_fact``, ``task_setting`` or ``rubric_rule`` is unverified, exactly like
    an unchecked ``supplied_text``."""
    if grounding is None or is_ungrounded(grounding):
        return False
    return not has_authority(grounding)


def assumed_grounding(grounding: Optional[Grounding]) -> bool:
    """A premise the claim's writer (or the translator) supplies itself, for circularity: every premise that no check in
    this process established (``not has_authority``), whatever kind it claims. A premise a check verified against the task
    record or a text (a ``task_setting`` the request states, a located excerpt) is a transcription: restating it is a
    check of the claim against that source, not a circle. One that only carries a task or text label (no excerpt, an
    excerpt no check located, a ``knowledge_document``) is supported by nothing but the claim itself, so restating it is
    circular. Until policy 2026.10-v5 only the ungrounded kinds and an unverified ``arithmetic_fact`` counted, so a
    label-only ``task_setting`` that restated the conclusion cleared the check."""
    return not has_authority(grounding)


def ungrounded_dependencies(problem: Problem, relied_on: list[str]) -> list[str]:
    """Relied-on premises whose support is missing, inferential, assumed, failed a grounding
    check, or (for checkable kinds) was never positively verified."""
    by_id = {p.id: p for p in problem.premises}
    return [pid for pid in relied_on if pid in by_id and is_ungrounded(by_id[pid].grounding)]


def unverified_dependencies(problem: Problem, relied_on: list[str]) -> list[str]:
    """Relied-on premises whose grounding claims task or source authority (any kind, the task-given kinds included)
    that no deterministic check in this process validated."""
    by_id = {p.id: p for p in problem.premises}
    return [pid for pid in relied_on if pid in by_id and is_unverified(by_id[pid].grounding)]


def dependency_policy() -> dict[str, Any]:
    """The dependency rules as data, for the policy identity (:mod:`.identity`)."""
    return {
        "ungrounded_kinds": sorted(UNGROUNDED_KINDS),
        "task_given_kinds": sorted(TASK_GIVEN_KINDS),
        "source_kinds": sorted(SOURCE_KINDS),
        "checkable_kinds": sorted(CHECKABLE_KINDS),
        "authority": "verified-in-process-only",
        "unchecked_task_or_source_kind": "unverified_dependency",
        "assumed_for_circularity": "not_established",
    }
