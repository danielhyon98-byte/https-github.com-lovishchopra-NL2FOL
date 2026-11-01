"""Integration gate 2, handoff fixer: the generic parser's input stalls found by the class sweep (critical rule: input that
stalls the service is a security finding, fixed at its cause, never deferred as optimisation work). The generic parser reads
the Economics, Business Management, Psychology and generic-branch answers, and the STEM parser shares its role assignment.

* ``_logical_lines`` asked every join rule of the whole logical line read so far, and copied it to add each physical line: n²
  steps on an answer of joined lines ('ab cd' on each of 8,000 lines: 35 s; 4,000 of them took 20 s to receive and 9 s to audit
  on an Economics hub). The logical line is kept as lines are added (``_LogicalLine``): each rule gives the answer its pattern
  gave on the whole text, and the two readings that may still need the whole text (the trailing annotations when the last line
  could hold nothing else, the working test of a text with a relation sign, whose quotation masking pairs the marks of the whole
  text) are paid from a budget of 8 characters per character of the answer and 20,000 more; a join it cannot pay is refused and
  named in the report's unresolved issues.
* ``_part_answers`` read the lines of every unit of the answer again for each part (``_first_working_run``) and every support list
  for each part's answer: n² steps on an answer of thousands of parts ('1. x' on each of 3,200 lines: 8 s of a 9.6 s receive).
* ``_backward_conclusions`` gave every conclusion of a paragraph a list of all the claims before it, and the report listed the
  support ids of every unit before keeping 512: n² entries ('Therefore x. ' * 8,000: 5.8 s and 1.5 GB; the 400,000-character
  limit ran out of memory). The conclusions share their paragraph's list (``_Earlier``), and the ids are read for the kept claims.
* ``_part_answers`` gave every closing answer of a part, and every answer of a part's opening line, a list read from the whole
  part ('(a) ' + 'Search: x. ' * k + 'More text. ' * k: 9.2 s at 88 KB; thousands of results, accuracy-marked lines or parallel
  rows likewise, n² steps and entries): they read lists built once per part, as views (``_View``).

Each is held to the reading it replaces (kept below as the specification) on random answers, and timed on the worst-case input
with a wide margin and a growth ratio.
"""
from __future__ import annotations

import itertools
import random
import time

import pytest

from epinoic_logic.adapters.markdown import mask_quotations
from epinoic_logic.branches import RouterHub
from epinoic_logic.branches import generic_parser as g
from epinoic_logic.branches.generic_parser import GenericTextParser
from epinoic_logic.integrity import WorkPlan

from ..growth import growth
from ..timing import empty_caches

LINEAR = 8.0  # a 4x input: about 4 for a linear reader, about 16 for a quadratic one
KEY = b"integration-gate-2-handoff-generic-key-0123456789"


def _parse(text: str):
    return GenericTextParser("economics-specialist").parse_response(text, request_id="q", task_id="t", report_id="r", subject="Economics", task_type="essay")


def _cpu(fn, *args) -> float:
    empty_caches()
    c0 = time.process_time()
    fn(*args)
    return time.process_time() - c0


# --------------------------------------------------------------------------- the logical lines


def _whole_text_logical_lines(paragraph: str):
    """``_logical_lines`` as it was before the fix (the specification): every rule asked of the whole joined logical line."""
    out = []
    for line in paragraph.split("\n"):
        if not line.strip():
            continue
        accuracy = g._accuracy_marked(line)
        line = g._strip_annotations(line) if not g._ANNOTATION_ONLY_LINEAR_RE.fullmatch(line) else line
        if g._TABLE_SEPARATOR_RE.match(line) and "-" in line:
            if out and g._TABLE_ROW_RE.match(out[-1][0]):
                out[-1][1] = True
            continue
        if out and not g._PART_LEAD_RE.match(line) and not g._BULLET_RE.match(line) and not g._TABLE_ROW_RE.match(line):
            prev = out[-1][0]
            prev_masked, line_masked = mask_quotations(prev), mask_quotations(line)
            joins = bool(g._CONTINUATION_RE.match(line))
            if not joins and g._CONNECTIVE_END_RE.search(g._strip_annotations(prev)) and not g._TABLE_ROW_RE.match(prev):
                joins = True
            if (not joins and g._SOFT_WRAP_NEXT_RE.match(line) and not g._TERMINAL_PUNCT_RE.search(prev.rstrip(":;"))
                    and not prev.rstrip().endswith((":", ";")) and not g._is_working(prev_masked) and not g._is_working(line_masked)):
                joins = True
            if joins:
                out[-1][0] = prev.rstrip() + "\n" + line.rstrip()
                out[-1][2] = out[-1][2] or accuracy
                continue
        out.append([line.rstrip(), False, accuracy])
    return [(line, header, accuracy) for line, header, accuracy in out]


PIECES = [" ", "  ", "\t", "ab", "cd", "so", "and", "therefore", ",", ":", ";", ".", ".)", "!", "?", ")", "]", '"', "“", "”", "'", "’", "=", "<", ">",
          "!=", "5", "3", "×", "+", "-", "/", "(", "$", "|", "| a |", "|---|", "x", "also", "x = 5", '"x = 5"', "5 *", "[1]", "[2 marks]", "(3 marks)",
          "M1", "  A1", "(A1)", "AG", "ms", "as", "make", "(a)", "1.", "- ", "{", "}", '{"a": 1}', "[1", "mark", "spare", "1", "e", "R", "N2"]


@pytest.mark.parametrize("seed", [61, 62])
def test_the_kept_logical_lines_are_those_of_the_whole_text_reading(seed):
    rng = random.Random(seed)
    for _ in range(30000):
        paragraph = "\n".join("".join(rng.choice(PIECES) for _ in range(rng.randint(0, 6))) for _ in range(rng.randint(1, 8)))
        assert g._logical_lines(paragraph) == _whole_text_logical_lines(paragraph), repr(paragraph)


@pytest.mark.parametrize("make", [
    lambda k: "ab cd\n" * k,                                   # soft-wrapped lines (before: 35 s at 8,000 lines)
    lambda k: "ab,\n" * k,                                     # lines ending on a comma
    lambda k: "x = 1\n" + "= 1\n" * k,                         # an equation continued line after line
    lambda k: "x,\n" + "[1]\n" * k,                            # a comma, then lines of annotations the strip removes
    lambda k: "x\n" + "ms\n" * k,                              # lines of letters an annotation may hold
    lambda k: "x,\n" + "  M1\n" * k,                           # bare markscheme codes
    lambda k: 'a "x = 5" b\n' + 'ab "c" "d" e\n' * k,          # a quoted equation, then soft-wrapped lines of quotations
])
def test_a_paragraph_of_joined_lines_is_read_in_linear_time(make):
    state = g._State()
    c0 = time.process_time()
    g._logical_lines(make(30_000), state)
    assert time.process_time() - c0 < 6.0
    ratio, small, large = growth(g._logical_lines, make(2000), make(8000))
    assert ratio < LINEAR, (ratio, small, large)


def test_only_a_join_whose_reading_the_budget_cannot_pay_is_refused_and_it_is_named():
    # an answer built to make every join read all that came before: a quoted equation, then thousands of soft-wrapped lines
    text = 'The text says "x = 5" here\n' + "ab cd\n" * 6000
    state = g._State()
    g._logical_lines(text, state)
    assert state.joins_refused == 1
    report = _parse(text)
    assert any("not joined to the line before them" in issue and "reading bound" in issue for issue in report.unresolved_issues)
    # control: an ordinary answer, and the same shape at an ordinary length, refuse nothing and name nothing
    for ordinary in ('The text says "x = 5" here\n' + "ab cd\n" * 20, "The price rose because demand rose.\nTherefore the market cleared."):
        state = g._State()
        g._logical_lines(ordinary, state)
        assert state.joins_refused == 0
        assert not any("not joined to the line before them" in issue for issue in _parse(ordinary).unresolved_issues)


# --------------------------------------------------------------------------- the role assignment


def _old_first_working_run(flat, live):
    """``GenericTextParser._first_working_run`` as it was before the fix (the specification)."""
    by_para: dict[int, list[int]] = {}
    for i in live:
        by_para.setdefault(flat[i].para, []).append(i)
    lines_of: dict[int, list[int]] = {}
    for i, u in enumerate(flat):
        lines_of.setdefault(u.line, []).append(i)
    structured = {p for p in by_para if len({flat[i].line for i in range(len(flat)) if flat[i].para == p}) > 1}
    run: list[int] = []
    started = False
    for para in sorted(by_para):
        working = [i for i in by_para[para] if flat[i].working and flat[i].lead not in ("diagram", "heading")
                   and (para in structured or len(lines_of[flat[i].line]) == 1)]
        if working:
            started = True
            run.extend(working)
        elif started:
            break
    return run


def test_the_first_run_of_working_is_that_of_the_reading_of_every_unit():
    rng = random.Random(63)
    for _ in range(3000):
        n = rng.randint(1, 30)
        flat = [g._Unit(text="x", para=rng.randint(0, 3), line=rng.randint(0, 8), part=1, working=rng.random() < 0.5,
                        lead=rng.choice(["", "", "diagram", "heading", "result"])) for _ in range(n)]
        flat.sort(key=lambda u: (u.para, u.line))
        live = sorted(rng.sample(range(n), rng.randint(0, n)))
        layout = GenericTextParser._line_layout(flat)
        assert GenericTextParser._first_working_run(flat, live, layout) == _old_first_working_run(flat, live)
        assert GenericTextParser._first_working_run(flat, live) == _old_first_working_run(flat, live)


def test_the_support_index_leaves_the_lists_the_scans_of_every_list_left():
    """``_SupportIndex`` against the operations ``_part_answers`` made on the dict directly (the specification), key order included."""
    rng = random.Random(64)
    for _ in range(4000):
        n = rng.randint(1, 12)
        start = {p: rng.sample(range(n), rng.randint(0, n)) for p in rng.sample(range(n), rng.randint(0, n))}
        direct = {p: list(ss) for p, ss in start.items()}
        indexed = {p: list(ss) for p, ss in start.items()}
        links = g._SupportIndex(indexed)
        for _ in range(rng.randint(1, 10)):
            op, i = rng.choice(["withdraw", "set", "pop", "pop_if"]), rng.randrange(n)
            if op == "withdraw":
                for p, ss in direct.items():
                    if i in ss:
                        direct[p] = [s for s in ss if s != i]
                links.withdraw(i)
            elif op == "set":
                ss = rng.sample(range(n), rng.randint(0, n))
                direct[i] = list(ss)
                links.set(i, list(ss))
            elif op == "pop":
                direct.pop(i, None)
                links.pop(i)
            elif i in direct:  # 'if roles[i] == "point" and i in supports: supports.pop(i)'
                direct.pop(i)
                links.pop(i)
        links.settle()
        assert list(indexed.items()) == list(direct.items())


def _old_part_answers(flat, roles, material, supports, answer, consequence, caveat):
    """``GenericTextParser._part_answers`` as it was before the fix (the specification): every closing answer and every answer
    of the opening line read the part again, and every withdrawal read every support list."""
    parts: dict[int, list[int]] = {}
    for i, u in enumerate(flat):
        if u.part:
            parts.setdefault(u.part, []).append(i)
    leads = [u.lead for u in flat]
    for _part, members in parts.items():
        live = [i for i in members if roles[i] != "other"]
        if not live:
            continue
        closing: list[int] = []
        results = [i for i in live if leads[i] == "result" or flat[i].accuracy]
        if results:
            closing = results
        else:
            run = _old_first_working_run(flat, live)
            if run:
                last = run[-1]
                closing = [*reversed(g._parallel_rows(flat, last, run)), last]
        opening = [i for i in live if flat[i].opening and leads[i] not in ("diagram", "assumption")]
        opening_answers: list[int] = []
        if opening and not closing:
            first_line = flat[opening[0]].line
            on_line = [i for i in opening if flat[i].line == first_line]
            justified = any(leads[i] == "why" for i in live)
            if not flat[on_line[0]].text.rstrip().endswith(":"):
                if justified:
                    opening_answers = on_line
                elif len(on_line) > 1 and all(leads[i] == "label" for i in on_line[:2]):
                    opening_answers = list(itertools.takewhile(lambda i: leads[i] == "label", on_line))
                else:
                    opening_answers = on_line[:1]
        elif opening and flat[opening[0]].value:
            opening_answers = [opening[0]]
        for i in closing + opening_answers:
            answer[i] = True
            material[i] = True
        for i in closing:
            earlier = [j for j in live if j < i and not answer[j] and leads[j] != "diagram" and roles[j] != "other"
                       and (flat[j].para == flat[i].para or flat[j].working or roles[j] == "evidence")]
            for p, ss in supports.items():
                if i in ss:
                    supports[p] = [s for s in ss if s != i]
            if roles[i] == "point" and i in supports:
                supports.pop(i)
            if earlier:
                roles[i] = "point"
                supports[i] = earlier
        for i in opening_answers:
            if i in closing:
                continue
            para = flat[i].para
            alone = not any(j > i and flat[j].para == para for j in live)
            pool = [j for j in live if j > i and (alone or flat[j].para == para)]
            later = [j for j in pool if not answer[j] and roles[j] != "judgement" and (alone or roles[j] != "point") and not consequence[j]
                     and not caveat[j] and leads[j] not in ("assumption", "diagram")]
            for p, ss in supports.items():
                if i in ss:
                    supports[p] = [s for s in ss if s != i]
            roles[i] = "point" if later or roles[i] in ("point", "analysis") else roles[i]
            supports[i] = later
            for j in later:
                if roles[j] == "point":
                    roles[j], material[j] = ("quantitative" if g._NUM_RE.search(flat[j].text) else "analysis"), False
                    supports.pop(j, None)


def test_the_part_answers_are_those_of_the_reading_of_every_part_and_list():
    rng = random.Random(65)
    leads = ["", "", "", "result", "label", "why", "diagram", "assumption", "heading"]
    role_names = ["analysis", "quantitative", "evidence", "judgement", "point", "other"]
    texts = ["x = 5", "It rose.", "Search: halves.", "(-1, 3)", "Find x:", "Answer: 4", "5 + 3 = 8"]
    for _ in range(4000):
        n = rng.randint(1, 24)
        flat, line, para, part = [], 0, 0, 0
        for _k in range(n):
            if rng.random() < 0.3:
                line += 1
                if rng.random() < 0.4:
                    para += 1
                if rng.random() < 0.3:
                    part += 1
            flat.append(g._Unit(text=rng.choice(texts), para=para, line=line, part=part, lead=rng.choice(leads), working=rng.random() < 0.4,
                                value=rng.random() < 0.15, opening=rng.random() < 0.4, accuracy=rng.random() < 0.1))
        roles = [rng.choice(role_names) for _ in range(n)]
        material = [rng.random() < 0.5 for _ in range(n)]
        supports = {p: sorted(rng.sample(range(n), rng.randint(0, min(n, 5)))) for p in rng.sample(range(n), rng.randint(0, n))}
        answer = [False] * n
        consequence = [rng.random() < 0.15 for _ in range(n)]
        caveat = [rng.random() < 0.1 for _ in range(n)]
        old = (list(roles), list(material), {p: list(ss) for p, ss in supports.items()}, list(answer))
        _old_part_answers(flat, old[0], old[1], old[2], old[3], consequence, caveat)
        new = (list(roles), list(material), {p: list(ss) for p, ss in supports.items()}, list(answer))
        GenericTextParser._part_answers(flat, new[0], new[1], new[2], new[3], consequence, caveat)
        assert new[0] == old[0] and new[1] == old[1] and new[3] == old[3]
        assert [(p, list(ss)) for p, ss in new[2].items()] == [(p, list(ss)) for p, ss in old[2].items()]


def test_a_view_reads_its_slices_as_the_list_they_stand_for():
    rng = random.Random(66)
    for _ in range(3000):
        a = sorted(rng.sample(range(60), rng.randint(0, 20)))
        b = sorted(rng.sample(range(60), rng.randint(0, 20)))
        sa, ea = sorted((rng.randint(0, len(a)), rng.randint(0, len(a))))
        sb, eb = sorted((rng.randint(0, len(b)), rng.randint(0, len(b))))
        view, expected = g._View((a, sa, ea), (b, sb, eb)), sorted(set(a[sa:ea]) | set(b[sb:eb]))
        assert list(view) == expected and len(view) == len(expected) and bool(view) == bool(expected) and view == expected
        if expected:
            assert view[0] == expected[0] and view[-1] == expected[-1] and expected[len(expected) // 2] in view


def test_a_conclusion_rests_on_the_claims_before_it_as_a_list_would():
    items = [3, 5, 8, 13]
    earlier = g._Earlier(items, 3)
    items.append(21)  # the paragraph's list grows past it
    assert list(earlier) == [3, 5, 8] and len(earlier) == 3 and earlier[0] == 3 and earlier[-1] == 8 and earlier[1:] == [5, 8]
    assert 8 in earlier and 13 not in earlier and earlier == [3, 5, 8] and sorted(set(earlier)) == [3, 5, 8]
    with pytest.raises(IndexError):
        earlier[3]


@pytest.mark.parametrize("make", [
    lambda k: "Therefore x. " * k,                             # before: 5.8 s and 1.5 GB at 8,000; out of memory at the size limit
    lambda k: "Overall x. " * k,                               # judgements
    lambda k: "1. x\n" * k,                                    # thousands of parts (before: 8 s of a 9.6 s receive at 3,200)
    lambda k: "(a) x = 1\n" * k,                               # parts with a line of working each
    lambda k: "(a) x\n" + "y\nAnswer: z\n" * k,                # a part of many answers
    lambda k: "(a) Find x.\n" + "It rises.\nAnswer: x = 1\n" * k,  # closing answers each resting on the part before them
    lambda k: "(a) Find x.\n" + "x = 1  A1\n" * k,             # accuracy-marked lines
    lambda k: "(a) Find x.\n" + "x = 1\n" * k,                 # a run of working of parallel rows
    lambda k: "(a) " + "Search: x. " * k + "\n" + "More text. " * k,  # a line of labelled answers, then claims (before: 9.2 s at 88 KB)
    lambda k: "(a) " + "Lucia x. " * k + "\nWhy: because.",     # a justified opening line
])
def test_an_answer_of_thousands_of_conclusions_or_parts_is_parsed_in_linear_time(make):
    text = make(400_000)[:400_000]
    assert _cpu(_parse, text) < 20.0
    ratio, small, large = growth(_parse, make(1000), make(4000), clear=empty_caches)
    assert ratio < LINEAR, (ratio, small, large)


def test_the_kept_claims_keep_their_supports():
    """Controls for the supports the report lists: a point rests on the plain claims after it, a closing judgement on the
    claims before it, and a claim beyond the claim limit is folded and supports nothing that is kept."""
    report = _parse("Prices rose in 2022. Demand rose. Supply fell. Therefore prices rose.")
    by_text = {c.claim_text: c for c in report.claims}
    ids = [c.claim_id for c in report.claims]
    assert by_text["Prices rose in 2022."].supporting_claim_ids == [ids[1], ids[2]]
    assert by_text["Therefore prices rose."].supporting_claim_ids == ids[:3]
    big = _parse("Therefore x. " * 600)
    assert len(big.claims) == 512 and big.claims[-1].claim_id == "g.tail"
    kept = {c.claim_id for c in big.claims}
    assert all(set(c.supporting_claim_ids) <= kept for c in big.claims)
    assert big.claims[510].supporting_claim_ids == [c.claim_id for c in big.claims[:510]]


# --------------------------------------------------------------------------- through the hub


@pytest.mark.parametrize("text", ["ab cd\n" * 8000, "1. x\n" * 3200, "Therefore x. " * 8000])
def test_an_economics_answer_of_these_shapes_crosses_the_hub_in_seconds(text):
    hub = RouterHub(signing_key=KEY)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject="Economics", task_type="short_answer", selected_agent_ids=["economics-specialist"]))
    m, _req, _rq = hub.dispatch("t", "economics-specialist", "Answer the question.")
    empty_caches()
    c0 = time.process_time()
    _reply, rc = hub.receive("t", m.message_id, text, agent_id="economics-specialist", report_id="r1")
    assert time.process_time() - c0 < 20.0  # before: 30 s (soft-wrapped lines, 48 KB), 9.6 s (3,200 parts), minutes (8,000 conclusions)
    assert rc.status.value.startswith("ACCEPTED")


# --------------------------------------------------------------------------- the sweep of the generic parser's entry points

SHAPES = {
    "soft-wrapped lines": "ab cd\n" * 3333, "comma lines": "ab,\n" * 5000, "connective lines": "it rose so\n" * 1818,
    "continued equation": "x = 1\n" + "= 1\n" * 4999, "annotation lines after a comma": "x,\n" + "[1]\n" * 5000,
    "letters an annotation holds": "x\n" + "ms\n" * 6666, "quoted equation then wraps": 'a "x = 5" b\n' + "ab cd\n" * 3330,
    "numbered lines": "1. x\n" * 4000, "conclusions": "Therefore x. " * 1538, "judgements": "Overall x. " * 1818,
    "parts with working": "(a) x = 1\n" * 2000, "mark then blanks": "(A1)" + " " * 19_990 + "x", "run of marks": "x = 5" + " (A1)" * 4000 + " z",
    "blanks": " " * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x", "list markers": "\n1. " * 5000 + "x",
}


def test_sweep_generic_parser_with_the_line_shapes():
    entries = {"parse_response": _parse, "split_sentences": g.split_sentences, "logical lines": g._logical_lines}
    slow, crashed = [], []
    for shape, text in SHAPES.items():
        for name, fn in entries.items():
            empty_caches()
            c0 = time.process_time()
            try:
                fn(text)
            except g.AdapterError:
                pass  # an empty answer is refused, which is an answer
            except Exception as exc:  # noqa: BLE001 - any other exception is a crash the sweep reports
                crashed.append((name, shape, type(exc).__name__))
            spent = time.process_time() - c0
            if spent > 4.0:
                slow.append((name, shape, round(spent, 2)))
    assert not slow, slow
    assert not crashed, crashed
