"""Premise roles: how a translation marks each premise of its problem (the marking record of the argument diagnosis).

``premise_roles(problem, checks)`` is written into ``TranslationResult.premise_roles`` at translation time. It records,
for every premise, what kind of step it is, what authority it has, and how the translation marked it, so a reader (the
claim rules, the overseer) can tell a writer's own link from a stated rule or a checked fact without trusting a label:

* ``role`` is read from the expression alone: an implication is a ``link``; a biconditional is a ``definition`` when an
  atom stands on one side (``b <-> (n = 17)``) and a ``link`` otherwise; a disjunction is ``either_or``; a numeric
  relation that combines symbols (``relations.numeric_shape`` is ``relation``: ``speed = d / 8``, ``x != 5``) is a
  ``figure_relation``; everything else (atoms, negations, assignments of stated figures, conjunctions) is a ``fact``;
* ``authority`` is read from the grounding's ``verified`` flag and kind, never from its label: ``established`` only when a
  check in this process verified it (``engine.authority.has_authority``), ``refuted`` when a check failed, ``writer_own``
  for no grounding and the writer's own kinds (assumption, specialist inference, general knowledge), ``unverified`` for a
  task or source kind no check verified;
* ``marked`` says how a link-shaped premise (link, either_or, definition, figure_relation) was marked: ``source_link``
  when a check verified it against a source; ``translator_link`` for ``specialist_inference`` with a ``link:`` note (the
  writer's step, marked as the writer's); ``translator_rule`` for ``general_knowledge`` (a rule stated from subject
  knowledge); ``label_conflict`` when its kind claims a text or task authority while no check verified the relation;
  ``unmarked_link`` for any other kind no check verified. Every fact-shaped premise is ``fact``;
* ``connective`` is the connective of a ``link: <connective>`` note ("so", "because", "which shows").

Nothing is evaluated: the record is computed from the validated IR and the grounding records only.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from ..engine.authority import SOURCE_KINDS, TASK_GIVEN_KINDS, UNGROUNDED_KINDS, has_authority
from ..ir.schema import Assertion, Grounding, Problem
from .contracts import GroundingCheck, PremiseRole
from .relations import numeric_shape

__all__ = ["LINK_ROLES", "premise_roles", "premise_role", "role_of", "authority_of", "link_connective", "roles_by_id"]

#: The link-shaped roles: the steps a proof can need that only a source or the writer can supply.
LINK_ROLES = frozenset({"link", "either_or", "definition", "figure_relation"})
#: Kinds that claim a text's or the task's authority.
_CLAIMED_AUTHORITY = frozenset(SOURCE_KINDS | TASK_GIVEN_KINDS)
_LINK_NOTE = "link:"


def role_of(expr) -> str:
    """The role of a premise expression (module docstring), read from the expression only."""
    op = getattr(expr, "op", None)
    if op == "or":
        return "either_or"
    if op == "implies":
        return "link"
    if op == "iff":
        return "definition" if getattr(expr.left, "op", None) == "var" or getattr(expr.right, "op", None) == "var" else "link"
    if numeric_shape(expr) == "relation":
        return "figure_relation"
    return "fact"


def authority_of(grounding: Optional[Grounding], refuted: bool = False) -> str:
    """``established``, ``refuted``, ``writer_own`` or ``unverified`` (module docstring)."""
    if refuted or (grounding is not None and grounding.verified is False):
        return "refuted"
    if has_authority(grounding):
        return "established"
    if grounding is None or grounding.kind in UNGROUNDED_KINDS:
        return "writer_own"
    return "unverified"


def link_connective(grounding: Optional[Grounding]) -> Optional[str]:
    """The connective of a ``link: <connective>`` note (cut to 80 characters), or None."""
    note = (grounding.note or "").strip() if grounding is not None else ""
    if not note.casefold().startswith(_LINK_NOTE):
        return None
    connective = " ".join(note[len(_LINK_NOTE):].split())
    return connective[:80] or None


def premise_role(premise: Assertion, refuted: bool = False) -> PremiseRole:
    """The :class:`~.contracts.PremiseRole` of one premise."""
    g = premise.grounding
    role = role_of(premise.expr)
    authority = authority_of(g, refuted)
    connective = link_connective(g)
    if role not in LINK_ROLES:
        marked = "fact"
    elif authority == "established":
        marked = "source_link"
    elif g is not None and g.kind == "specialist_inference" and connective is not None:
        marked = "translator_link"
    elif g is not None and g.kind == "general_knowledge":
        marked = "translator_rule"
    elif g is not None and g.kind in _CLAIMED_AUTHORITY:
        marked = "label_conflict"
    else:
        marked = "unmarked_link"
    return PremiseRole(assertion_id=premise.id, role=role, authority=authority, marked=marked,  # type: ignore[arg-type]
                       kind=g.kind if g is not None else None, connective=connective)


def premise_roles(problem: Optional[Problem], checks: Iterable[GroundingCheck] = ()) -> list[PremiseRole]:
    """The role of every premise of ``problem``, in premise order ([] for no problem). A premise a grounding check in
    ``checks`` refuted counts as refuted even when its grounding was not updated."""
    if problem is None:
        return []
    refuted = {c.target_id for c in checks if c.verified is False}
    return [premise_role(p, p.id in refuted) for p in problem.premises]


def roles_by_id(roles: Sequence[PremiseRole]) -> dict[str, PremiseRole]:
    """``{assertion_id: role}``."""
    return {r.assertion_id: r for r in roles}
