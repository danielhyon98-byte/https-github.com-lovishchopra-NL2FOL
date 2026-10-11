"""Statement segmentation (docs/STEM_DESIGN.md, section 4.3)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from epinoic_logic.stem.limits import PROFILES, StemLimits
from epinoic_logic.stem.normalize import reading_view
from epinoic_logic.stem.segment import TAIL_ID, segment_statements
from epinoic_logic.stem.spans import find_spans

ROOT = Path(__file__).resolve().parents[2]


def seg(text: str, profile: str = "physics", names=frozenset(), limits: StemLimits = StemLimits()):
    rv = reading_view(text)
    ss = find_spans(text, rv, profile=PROFILES[profile], names=frozenset(names), limits=limits)
    return segment_statements(text, ss, names=frozenset(names), reading=rv, limits=limits), ss


def rows(text: str, profile: str = "physics", **kw) -> list[tuple[str, str, str]]:
    sg, _ = seg(text, profile, **kw)
    return [(st.id, st.kind, text[st.start:st.end]) for st in sg.statements]


def test_sentences_never_split_inside_math():
    text = "The ball falls. Its speed is v = 9.8 × 2.0 = 19.6 m s⁻¹. Then it stops."
    assert rows(text) == [("s1.1", "sentence", "The ball falls."), ("s1.2", "sentence", "Its speed is v = 9.8 × 2.0 = 19.6 m s⁻¹."),
                          ("s1.3", "sentence", "Then it stops.")]
    assert [r[2] for r in rows("Use g = 9.81 m s⁻². The time is 2.0 s.")] == ["Use g = 9.81 m s⁻².", "The time is 2.0 s."]
    assert [r[2] for r in rows("Dr. Smith measured x = 2.5 m. It was fine.")] == ["Dr. Smith measured x = 2.5 m.", "It was fine."]
    assert [r[2] for r in rows("x = 2. y = 3.")] == ["x = 2.", "y = 3."]
    text = r"So the energy is $\frac{1}{2} M v^2 = 3.5$ J. Next we find the speed."
    assert [r[2] for r in rows(text)] == [r"So the energy is $\frac{1}{2} M v^2 = 3.5$ J.", "Next we find the speed."]   # a unit after the span
    text = r"So the energy is $E = 3.5$ kJ mol⁻¹. Next we find the speed."
    assert len(rows(text)) == 2
    text = r"The value $x = 2$ was given by Q. Smith in an early paper."
    assert len(rows(text)) == 1          # 'Q' is no unit and not after the span: the shared splitter's initial rule stands


def test_symbol_boundary_rule():
    text = "The speed is v. Then it stops."
    assert [r[2] for r in rows(text, names={"v"})] == ["The speed is v.", "Then it stops."]


def test_claim_texts_are_offset_substrings():
    text = "  Given: m = 2.0 kg, v = 3.0 m s⁻¹.\n\n(a) v = u + at\n= 0 + 9.8 × 2.0\n- item x = 1\n"
    sg, _ = seg(text)
    for st in sg.statements:
        piece = text[st.start:st.end]
        assert piece == piece.strip() and piece


def test_derivation_lines_and_continuations():
    text = "v = u + at\n= 0 + 9.8 × 2.0\n= 19.6 m s⁻¹"
    sg, _ = seg(text)
    assert [(st.kind, st.continuation) for st in sg.statements] == [("derivation", False), ("derivation", True), ("derivation", True)]
    assert [st.id for st in sg.statements] == ["s1.1", "s1.2", "s1.3"]
    assert all(st.spans for st in sg.statements)


def test_display_rows_code_tables_and_paragraphs():
    assert [r[1:] for r in rows("$$\nx = 1 \\\\\n= 2 - 1\n$$\nSo done.")] == [("display_row", "x = 1"), ("display_row", "= 2 - 1"), ("sentence", "So done.")]
    sg, _ = seg("$$\nx = 1 \\\\\n= 2 - 1\n$$")
    assert [st.continuation for st in sg.statements] == [False, True]
    assert [r[1:] for r in rows("```\ncode here\n```\nText after.", "computer_science")] == [("code", "```\ncode here\n```"), ("sentence", "Text after.")]
    assert [r[1] for r in rows("| a | b |\n|---|---|\n| 1 | 2 |")] == ["table"]
    assert [r[0] for r in rows("Para one.\n\nPara two.")] == ["s1.1", "s2.1"]
    assert [r[1] for r in rows("[1, 2, 3]", "mathematics_aa")] == ["data_line"]


def test_parts_headings_and_list_items():
    sg, _ = seg("(a) v = 3 m s⁻¹\n(b) The ball stops.")
    assert [(st.part, st.kind) for st in sg.statements] == [("(a)", "derivation"), ("(b)", "sentence")]
    sg, _ = seg("## Part (a)\nx = 2\n## Part (b)\ny = 3")
    assert [(st.id, st.part) for st in sg.statements] == [("s1.1", "Part (a)"), ("s2.1", "Part (b)")]
    sg, _ = seg("**Part (a)**\nx = 2\n\n**Part (b)**\nThe ball stops.")
    assert [st.part for st in sg.statements] == ["Part (a)", "Part (b)"]
    sg, _ = seg("Intro x = 1.\n### Question 2\nx = 2\nMore text here.")
    assert [(st.id, st.part) for st in sg.statements] == [("s1.1", ""), ("s2.1", "Question 2"), ("s2.2", "Question 2")]
    sg, _ = seg("- First, x = 2.\n- Second, y = 3.")
    assert [(st.kind, st.list_item) for st in sg.statements] == [("list_item", True), ("list_item", True)]


def test_line_ending_in_math_then_capital_is_two_statements():
    assert [r[2] for r in rows("Hence x = 2\nThe next part begins.")] == ["Hence x = 2", "The next part begins."]
    assert [r[2] for r in rows("So x = 2 and\ny = 3 here.")] == ["So x = 2 and\ny = 3 here."]   # a sentence wrapped over two lines


def test_statement_bound_merges_the_tail():
    text = " ".join(f"Point {i} holds." for i in range(30))
    sg, _ = seg(text, limits=StemLimits(max_statements=10))
    assert len(sg.statements) == 10 and sg.statements[-1].id == TAIL_ID and sg.overflow == 21
    assert text[sg.statements[-1].start:sg.statements[-1].end].startswith("Point 9 holds.")


def test_ids_are_deterministic():
    text = "(a) v = 3\nSo the ball moves. It stops.\n\n$$x = 1$$\n- y = 2"
    a, _ = seg(text)
    b, _ = seg(text)
    assert a.statements == b.statements


def test_segmentation_is_linear():
    text = ("The ball falls 5.0 m. Its speed is v = 9.8 × 2.0 = 19.6 m s⁻¹.\n" * 3000)
    t = time.perf_counter()
    sg, _ = seg(text)
    assert time.perf_counter() - t < 3.0
    assert sg.overflow > 0 and len(sg.statements) == 512


@pytest.mark.skipif(not (ROOT / "docs/qa_corpus/history/example_1.json").exists(), reason="History corpus not present")
def test_shared_splitter_is_untouched_by_the_stem_package():
    """The STEM front end reuses the History sentence splitter as it is: importing and running the
    STEM package must leave its boundaries on a History answer byte-identical."""
    script = (
        "import json, sys\n"
        "from epinoic_logic.adapters.history_specialist.sentences import sentence_boundaries\n"
        "text = json.load(open(sys.argv[1], encoding='utf-8'))['model_answer']\n"
        "if sys.argv[2] == 'stem':\n"
        "    from epinoic_logic.stem import build_document\n"
        "    build_document('v = 5.0 m s⁻¹. Then it stops.', None, 'physics')\n"
        "print(json.dumps(sentence_boundaries(text)))\n"
    )
    path = str(ROOT / "docs/qa_corpus/history/example_1.json")
    env_path = str(ROOT / "src")
    outs = []
    for mode in ("plain", "stem"):
        res = subprocess.run([sys.executable, "-c", script, path, mode], capture_output=True, text=True, timeout=60,
                             env={"PYTHONPATH": env_path, "PATH": "/usr/bin:/bin"})
        assert res.returncode == 0, res.stderr
        outs.append(res.stdout)
    assert outs[0] == outs[1] and json.loads(outs[0])
