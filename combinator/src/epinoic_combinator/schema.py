"""A small JSON Schema validator for the published contract's schemas (standard library only).

The translator generates its port schemas from its pydantic models; they use a closed set of keywords
(:data:`KEYWORDS`): ``type``, ``properties``, ``required``, ``additionalProperties`` (a boolean), ``items``, ``minItems``,
``maxItems``, ``minLength``, ``maxLength``, ``pattern``, ``enum``, ``const``, ``anyOf``, a local ``$ref`` into ``$defs``,
and the annotations ``title``, ``description`` and ``default``. A schema with any other keyword or form is refused when
it is loaded (:class:`SchemaUnsupported`): this validator fails closed, it never accepts a document because it did not
understand a rule.

The semantics are those of the translator's models in strict mode: no coercion (``true`` is no integer, ``1`` is no
string), lengths in code points, and a ``pattern`` anchored like the translator's regular expressions, where ``$`` is
the end of the text (never "before a final line break", as Python's ``$`` would read it). Error messages name the path
and the rule; a value is shown only when it is a short word, otherwise by its type or its length, so no agent prose is
echoed.
"""
from __future__ import annotations

import re
from typing import Any, Mapping, Optional

__all__ = ["KEYWORDS", "SchemaUnsupported", "Validator", "shown"]

KEYWORDS = frozenset({
    "type", "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "minLength", "maxLength",
    "pattern", "enum", "const", "anyOf", "$ref", "$defs", "title", "description", "default",
})
_TYPES = frozenset({"object", "array", "string", "integer", "boolean", "null"})
_REF_RE = re.compile(r"^#/\$defs/([A-Za-z0-9_.-]+)$")
_WORD_RE = re.compile(r"^[A-Za-z0-9_.:@-]{1,32}$")


class SchemaUnsupported(ValueError):
    """The schema uses a keyword or a form this validator does not implement: it is refused, never half-applied."""


def shown(value: Any) -> str:
    """How an error names a value: a short word quoted, anything else by its type or length (never the prose itself)."""
    if isinstance(value, str):
        return repr(value) if _WORD_RE.match(value) else f"free text of {len(value)} characters"
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value) if abs(value) < 10 ** 12 else "a large integer"
    return f"a value of type {_type_name(value)}"


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def _is_type(value: Any, name: str) -> bool:
    if name == "null":
        return value is None
    if name == "boolean":
        return value is True or value is False
    if name == "integer":
        return type(value) is int
    if name == "string":
        return type(value) is str
    if name == "array":
        return type(value) is list
    if name == "object":
        return type(value) is dict
    return False


def _json_equal(a: Any, b: Any) -> bool:
    if _type_name(a) != _type_name(b):
        return False
    if isinstance(a, list):
        return len(a) == len(b) and all(_json_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_json_equal(a[k], b[k]) for k in a)
    return a == b


def _compile_pattern(pattern: Any, where: str) -> "re.Pattern[str]":
    """A pattern of the form ``^...$`` with one ``$``, at its end: Python reads ``$`` before a final line break too, so the
    final ``$`` becomes ``\\Z`` (the end of the text, as the translator's models read it). Anything else is refused."""
    if not isinstance(pattern, str) or not pattern.startswith("^") or not pattern.endswith("$") or pattern.count("$") != 1 \
            or pattern.endswith("\\$"):
        raise SchemaUnsupported(f"{where}: a pattern must be anchored as ^...$ with one $ at its end")
    try:
        return re.compile(pattern[:-1] + r"\Z")
    except re.error:
        raise SchemaUnsupported(f"{where}: the pattern does not compile") from None


class Validator:
    """Validate JSON values (already parsed strictly) against one schema of the published contract."""

    def __init__(self, schema: Mapping[str, Any]):
        if not isinstance(schema, dict):
            raise SchemaUnsupported("a schema is a JSON object")
        self.schema = schema
        defs = schema.get("$defs", {})
        if not isinstance(defs, dict):
            raise SchemaUnsupported("$defs is an object of schemas")
        self.defs: dict[str, Any] = defs
        self._patterns: dict[int, "re.Pattern[str]"] = {}
        self._audit(schema, "#")

    # ----------------------------------------------------------------------------------------------- loading

    def _audit(self, node: Any, where: str) -> None:
        if not isinstance(node, dict):
            raise SchemaUnsupported(f"{where}: a schema is a JSON object")
        unknown = sorted(set(node) - KEYWORDS)
        if unknown:
            raise SchemaUnsupported(f"{where}: unsupported keyword(s) {unknown}")
        for key, value in node.items():
            at = f"{where}/{key}"
            if key in ("properties", "$defs"):
                if not isinstance(value, dict):
                    raise SchemaUnsupported(f"{at}: an object of schemas")
                if key == "$defs" and where != "#":
                    raise SchemaUnsupported(f"{at}: $defs only at the root")
                for name, sub in value.items():
                    self._audit(sub, f"{at}/{name}")
            elif key == "items":
                self._audit(value, at)
            elif key == "anyOf":
                if not isinstance(value, list) or not value:
                    raise SchemaUnsupported(f"{at}: a non-empty list of schemas")
                for i, sub in enumerate(value):
                    self._audit(sub, f"{at}/{i}")
            elif key == "$ref":
                m = _REF_RE.match(value) if isinstance(value, str) else None
                if m is None or m.group(1) not in self.defs:
                    raise SchemaUnsupported(f"{at}: only a local reference into $defs")
            elif key == "type":
                names = value if isinstance(value, list) else [value]
                if not names or not all(isinstance(n, str) and n in _TYPES for n in names):
                    raise SchemaUnsupported(f"{at}: an unsupported type")
            elif key == "additionalProperties":
                if not isinstance(value, bool):
                    raise SchemaUnsupported(f"{at}: only true or false")
            elif key == "required":
                if not isinstance(value, list) or not all(isinstance(n, str) for n in value):
                    raise SchemaUnsupported(f"{at}: a list of property names")
            elif key in ("minItems", "maxItems", "minLength", "maxLength"):
                if type(value) is not int or value < 0:
                    raise SchemaUnsupported(f"{at}: a non-negative integer")
            elif key == "pattern":
                self._patterns[id(node)] = _compile_pattern(value, at)
            elif key == "enum":
                if not isinstance(value, list) or not value:
                    raise SchemaUnsupported(f"{at}: a non-empty list")

    # ----------------------------------------------------------------------------------------------- validation

    def errors(self, value: Any, *, limit: int = 8) -> list[str]:
        """The rules ``value`` breaks (at most ``limit``), each as ``<path>: <rule>``; empty when it is valid."""
        out: list[str] = []
        self._check(self.schema, value, "$", out, limit)
        return out

    def is_valid(self, value: Any) -> bool:
        return not self.errors(value, limit=1)

    def _check(self, schema: Mapping[str, Any], value: Any, path: str, out: list[str], limit: int) -> None:
        if len(out) >= limit:
            return
        ref = schema.get("$ref")
        if ref is not None:
            self._check(self.defs[_REF_RE.match(ref).group(1)], value, path, out, limit)
        if "anyOf" in schema:
            if not any(not self._sub_errors(sub, value, path) for sub in schema["anyOf"]):
                out.append(f"{path}: {shown(value)} matches none of its allowed forms")
        if "type" in schema:
            names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
            if not any(_is_type(value, n) for n in names):
                out.append(f"{path}: expected {' or '.join(names)}, found {_type_name(value)}")
                return
        if "const" in schema and not _json_equal(value, schema["const"]):
            out.append(f"{path}: {shown(value)} is not {schema['const']!r}")
        if "enum" in schema and not any(_json_equal(value, e) for e in schema["enum"]):
            out.append(f"{path}: {shown(value)} is not one of {', '.join(str(e) for e in schema['enum'])}")
        if isinstance(value, str):
            if "minLength" in schema and len(value) < schema["minLength"]:
                out.append(f"{path}: shorter than {schema['minLength']} character(s)")
            if "maxLength" in schema and len(value) > schema["maxLength"]:
                out.append(f"{path}: longer than {schema['maxLength']} characters")
            pattern = self._patterns.get(id(schema))
            if pattern is not None and pattern.search(value) is None:
                out.append(f"{path}: {shown(value)} does not match {schema['pattern']}")
        elif isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                out.append(f"{path}: fewer than {schema['minItems']} item(s)")
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                out.append(f"{path}: more than {schema['maxItems']} items")
            items = schema.get("items")
            if items is not None:
                for i, item in enumerate(value):
                    self._check(items, item, f"{path}[{i}]", out, limit)
                    if len(out) >= limit:
                        return
        elif isinstance(value, dict):
            props: Mapping[str, Any] = schema.get("properties", {})
            for name in schema.get("required", ()):
                if name not in value:
                    out.append(f"{path}: missing key {name!r}")
            if schema.get("additionalProperties") is False:
                extra = [k for k in value if k not in props]
                if extra:
                    out.append(f"{path}: {len(extra)} key(s) the contract does not have ({', '.join(shown(k) for k in extra[:3])})")
            for name, sub in props.items():
                if name in value:
                    self._check(sub, value[name], f"{path}.{name}", out, limit)
                    if len(out) >= limit:
                        return

    def _sub_errors(self, schema: Mapping[str, Any], value: Any, path: str) -> list[str]:
        out: list[str] = []
        self._check(schema, value, path, out, 1)
        return out


def first_error(validator: Validator, value: Any) -> Optional[str]:
    errors = validator.errors(value, limit=1)
    return errors[0] if errors else None
