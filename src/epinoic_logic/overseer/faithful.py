"""Faithful re-parsing of journaled JSON into the repository's models.

Everything the channel issues is serialised with ``model_dump(mode="json", exclude_none=True)``, and every digest and
signature in the repository is computed over that form. ``exclude_none`` drops a field whose value is ``None``; a field
that is ``Optional`` with a NON-None default (``SolverConfig.memory_max_mb`` defaults to 512, ``course_level`` to
"unknown") therefore comes back with its default when the JSON is parsed again, and the re-dumped object no longer
matches the digest or the signature it was issued with. That would turn every such result into a false RES-003 and
every such report into a false custody fault.

:func:`faithful` restores the dropped values: in a dump made with ``exclude_none``, a field that is absent was ``None``
(``exclude_unset`` is never used on these paths), so every absent ``Optional`` field that is required (``ConstraintResult.
satisfied``) or has a non-None default is set to ``None`` explicitly before validation, recursively through nested models,
lists and dicts. Without it a receipt with an undecided check (``satisfied=None``) would not even parse again. Parsing is still the
contract's own strict validation; nothing in the data is evaluated.
"""
from __future__ import annotations

import types
import typing
from functools import lru_cache
from typing import Any, TypeVar

from pydantic import BaseModel
from pydantic_core import PydanticUndefined

__all__ = ["faithful", "fill_dropped_nones"]

M = TypeVar("M", bound=BaseModel)


def _allows_none(ann: Any) -> bool:
    origin = typing.get_origin(ann)
    return ann is type(None) or (origin in (typing.Union, types.UnionType) and type(None) in typing.get_args(ann))


def _model_types(ann: Any) -> list[type]:
    """The model classes an annotation can hold (through Optional, unions, lists and dicts)."""
    origin = typing.get_origin(ann)
    if origin is not None:
        out: list[type] = []
        for a in typing.get_args(ann):
            out += _model_types(a)
        return out
    return [ann] if isinstance(ann, type) and issubclass(ann, BaseModel) else []


@lru_cache(maxsize=None)
def _needs(cls: type) -> bool:
    """True when ``cls`` or a model nested in it has a field whose dropped ``None`` must be restored."""
    _needs_stack.add(cls)
    try:
        for f in cls.model_fields.values():
            if _allows_none(f.annotation) and (f.is_required() or f.default is not None):
                return True
            for m in _model_types(f.annotation):
                if m not in _needs_stack and _needs(m):
                    return True
        return False
    finally:
        _needs_stack.discard(cls)


_needs_stack: set = set()


@lru_cache(maxsize=None)
def _plan(cls: type) -> tuple[tuple[str, Any, bool], ...]:
    """(key, annotation, restore-None-when-absent) for every field of ``cls`` that matters: a field to restore, or one
    holding a model that needs restoring somewhere below it (other subtrees, such as the IR, are left untouched)."""
    out = []
    for name, f in cls.model_fields.items():
        key = f.alias or name
        restore = _allows_none(f.annotation) and (f.is_required() or f.default is not None)
        if restore or any(_needs(m) for m in _model_types(f.annotation)):
            out.append((key, f.annotation, restore))
    return tuple(out)


def _fill_value(ann: Any, value: Any) -> Any:
    origin = typing.get_origin(ann)
    if origin in (typing.Union, types.UnionType):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        models = [a for a in args if isinstance(a, type) and issubclass(a, BaseModel)]
        if len(args) == 1:
            return _fill_value(args[0], value)
        if len(models) == 1 and isinstance(value, dict):
            return fill_dropped_nones(models[0], value)
        return value  # an ambiguous union (the IR's expression nodes): left as it is
    if origin in (list, tuple, set, frozenset) and isinstance(value, list):
        args = typing.get_args(ann)
        if not args:
            return value
        inner = args[0]
        return [_fill_value(inner, v) for v in value]
    if origin is dict and isinstance(value, dict):
        args = typing.get_args(ann)
        return {k: _fill_value(args[1], v) for k, v in value.items()} if len(args) == 2 else value
    if isinstance(ann, type) and issubclass(ann, BaseModel) and isinstance(value, dict):
        return fill_dropped_nones(ann, value)
    return value


def fill_dropped_nones(cls: type[BaseModel], data: Any) -> Any:
    if not isinstance(data, dict) or not _needs(cls):
        return data
    out = dict(data)
    for key, ann, restore in _plan(cls):
        if key not in out:
            if restore:
                out[key] = None
            continue
        out[key] = _fill_value(ann, out[key])
    return out


def faithful(cls: type[M], data: Any) -> M:
    """``cls.model_validate`` of a dict made with ``exclude_none=True``, with the dropped ``None`` values restored."""
    return cls.model_validate(fill_dropped_nones(cls, data))
