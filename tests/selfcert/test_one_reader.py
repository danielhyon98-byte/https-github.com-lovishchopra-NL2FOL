"""One self-certification reader (design section 1.4, hold remedy c3b).

Every round before c3b grew a reader of the class beside the last one (layered patterns in ``adapters/self_report.py``, markdown's
template, structural, narrated and synthesis readers, the overseer's ``answer_status_claim`` and FID-009 lexicon, the channel's
check-result vocabularies), and each push check found sentences one of them named and another freed. This test reads the source
tree with ``ast`` (never a regex over code) and fails when a module outside ``epinoic_logic/selfcert/`` defines, at module level, a
pattern or a collection of words holding more than two of the stems of the class: a reader growing back elsewhere.

The allowlist names the module-level constants that are not readers of the class, each with its reason; a new entry needs one.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TREES = [ROOT / "src" / "epinoic_logic", ROOT / "overseer" / "src", ROOT / "combinator" / "src", ROOT / "flash-router" / "src"]
STEMS = ("verif", "checked", "confirm", "validat", "audit", "approv", "certif", "correct")

#: (module path relative to the repository, constant name) -> why it is not a reader of the self-certification class.
_ROLE = ("a role reader (note, caveat, provenance or label shape of a sentence) that decides whether words are a note or a claim, "
         "never the gate; design 4.0 principle 2")
_NEG = "reads only negated or deontic checks (a disclaimer: 'not verified', 'should be checked'); it can only refuse, never free"
_FORMAL = ("the overseer's formal-path note allowlist (rule note-clauses): a refusal-only closed list whose precondition is that the "
           "one reader names no sentence (design 1.3 item 14: assurance_words, evaluation_words and note-clauses stay)")
ALLOWED: dict[tuple[str, str], str] = {
    ("src/epinoic_logic/adapters/english_specialist/parser.py", "META_LABEL_RE"): _ROLE,
    ("src/epinoic_logic/adapters/history_specialist/parser.py", "_NO_CHECK_RE"): _NEG,
    ("src/epinoic_logic/adapters/history_specialist/parser.py", "_SOURCE_CAVEAT_RE"): _NEG,
    ("src/epinoic_logic/adapters/markdown.py", "_CHECK_PARTICIPLE"): _NEG + " (part of LABEL_PHRASE_RE)",
    ("src/epinoic_logic/adapters/markdown.py", "LABEL_PHRASE_RE"): _ROLE,
    ("src/epinoic_logic/adapters/markdown.py", "_QUOTED_LABEL_RE"): _ROLE,
    ("src/epinoic_logic/adapters/markdown.py", "_PROVENANCE_EXTRA_RE"): _ROLE,
    ("src/epinoic_logic/adapters/markdown.py", "_PROV_TRAIL_RE"): _ROLE,
    ("src/epinoic_logic/adapters/markdown.py", "_ANSWER_NOTE_RES"): _ROLE,
    ("src/epinoic_logic/adapters/markdown.py", "_ASSURANCE_RE"): _ROLE + " (states_assurance: design 1.3 item 2)",
    ("src/epinoic_logic/branches/generic_parser.py", "_NEGATIVE_CAVEAT_RE"): _NEG,
    ("src/epinoic_logic/integrity/ledger.py", "_DISCLAIMER_RE"): _NEG,
    ("src/epinoic_logic/translate/assertion.py", "_MARKERS"): "the assertion moods of the translator (questions, conditions, "
                                                              "hedges); no reader of the class",
    ("overseer/src/epinoic_overseer/meta_notes.py", "_ASSURANCE_WORDS"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_FIRST_PERSON_PAST"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_ASSURANCE_STEMS"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_CHECK_VERBS"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_NEGATIVE_FORMS"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_EVALUATION_WORDS"): _FORMAL,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_NEG_STATUS"): _FORMAL + "; " + _NEG,
    ("overseer/src/epinoic_overseer/meta_notes.py", "_CHECK_PART"): _FORMAL + "; " + _NEG,
}


def _strings(node: ast.AST) -> list[str]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
    return out


def _is_pattern_or_words(value: ast.AST) -> bool:
    """A pattern (a ``re.compile(...)`` call, or a string or f-string with an alternation ``|``) or a collection of words (a set,
    frozenset, tuple or list whose strings are words or short phrases, never sentences: messages and documentation are not
    readers)."""
    if isinstance(value, ast.Call):
        f = value.func
        name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else ""
        if name == "compile":
            return True
        if name in ("frozenset", "set", "tuple") and value.args:
            return _is_pattern_or_words(value.args[0])
        return False
    if isinstance(value, (ast.Constant, ast.JoinedStr, ast.BinOp)):
        return "|" in " ".join(_strings(value))
    if isinstance(value, (ast.Set, ast.Tuple, ast.List)):
        strings = _strings(value)
        return bool(strings) and all(len(x.split()) <= 4 for x in strings)
    return False


def _readers(path: Path) -> list[tuple[str, int, list[str]]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None and _is_pattern_or_words(node.value):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [t.id for t in targets if isinstance(t, ast.Name) and t.id != "__all__"]
            text = " ".join(_strings(node.value)).lower()
            stems = [s for s in STEMS if s in text]
            if len(stems) > 2 and names:
                found.append((names[0], node.lineno, stems))
    return found


def _modules() -> list[Path]:
    out = []
    for tree in TREES:
        for p in sorted(tree.rglob("*.py")):
            if "selfcert" in p.relative_to(tree).parts[:2] and p.parent.name == "selfcert" and "epinoic_logic" in p.parts:
                continue
            out.append(p)
    return out


def test_the_scan_reads_the_source_trees():
    mods = _modules()
    assert len(mods) > 100
    assert not any(p.parent.name == "selfcert" and p.parent.parent.name == "epinoic_logic" for p in mods)


def test_every_allowed_constant_still_exists_and_has_a_reason():
    present = {(p.relative_to(ROOT).as_posix(), name) for p in _modules() for name, _l, _s in _readers(p)}
    assert all(reason for reason in ALLOWED.values())
    assert sorted(set(ALLOWED) - present) == []  # a stale entry would hide a reader growing back under the same name


def test_no_module_outside_selfcert_defines_a_reader_of_the_class():
    grown = []
    for p in _modules():
        rel = p.relative_to(ROOT).as_posix()
        for name, line, stems in _readers(p):
            if (rel, name) not in ALLOWED:
                grown.append(f"{rel}:{line} {name} {stems}")
    assert grown == [], "\n".join(grown)


@pytest.mark.parametrize("source, expected", [
    ("X = re.compile(r'verified|checked|confirmed')", ["X"]),
    ("WORDS = frozenset({'verified', 'audited', 'approved'})", ["WORDS"]),
    ("Y = 'verified or checked'", []),
    ("def f():\n    Z = re.compile('verified|checked|confirmed|audited')\n", []),
])
def test_the_scan_names_a_module_level_reader_and_nothing_else(tmp_path, source, expected):
    p = tmp_path / "m.py"
    p.write_text("import re\n" + source + "\n", encoding="utf-8")
    assert [name for name, _line, _stems in _readers(p)] == expected
