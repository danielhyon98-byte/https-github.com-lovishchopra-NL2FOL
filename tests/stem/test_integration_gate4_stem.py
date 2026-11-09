"""Integration gate 4 (before arena round 8): the STEM finding of the independent lenses (parser-safety), reproduced through the audited
hub and fixed at its cause, with clean controls (correct working that holds, wrong working that fails or is named), and the further
shapes of its class that the sweep found. docs/STEM_DESIGN.md, section 38.

* rule sign-forms in every category (major): round 3 read only the mathematical symbols of Unicode category Sm, so an equals sign of
  another category ('🟰' HEAVY EQUALS SIGN, an emoji models emit; '꞊' MODIFIER LETTER SHORT EQUALS SIGN) and the characters drawn as one
  ('゠', '⹀', '˭', '═', '⚌', '〓') were read as nothing and named nothing: a wrong step written with one crossed the audited hub ACCEPTED
  with no check and no finding, and the audit passed (fail-open). The heavy and short equals signs and the double hyphens are '=' in the
  reading view (the step is checked); every other one is named (ST-PARSE-001), as are the relation signs of other categories by their
  name ('⯹', '⌸', '\u0347') and the further look-alikes ('᐀', '꓿', '⸗', '☰', '˂', '˃');
* rule sign-forms by place (the sweep): any other sign outside the grammar between two numerals ('3 • 4', '20 ╱ 4.0', '3 ✱ 4', '3 ˖ 4')
  ended the run, so the numeral after it began a fragment that was checked, an error on correct work ('x = 3 • 4 = 12' read as '4 = 12',
  INT-SUBJ-001), and the symbol before it was bound to a part of the expression ('x = 3'). It is kept in its run, the relation named
  undecided. 10,853 of the 11,205 non-ASCII symbols, punctuation marks, marks and format characters did so before the fix;
* invisible characters (the sweep): the emoji presentation selector after a dingbat sign ('✖\ufe0f', '➕\ufe0f', '🟰\ufe0f') and every other Unicode
  default-ignorable code point (a left-to-right mark, a soft hyphen, INVISIBLE TIMES) ended the run and let the next run start right after
  it, so 'x = 3 ✖\ufe0f 4 = 12' was read as '4 = 12' (an error on correct work); they are blanks in the reading view;
* a relation sign right after a sign outside the grammar ('x = 3 + 4 ⨯ = 8') was dropped with nothing named; the run goes on through it.

The last sections sweep the class over every character of the categories concerned and bound the CPU time of the new readings on hostile
input of about 20,000 characters.
"""
from __future__ import annotations

import time
import unicodedata

import pytest

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks
from epinoic_logic.stem.document import _relation_sign, clear_document_cache
from epinoic_logic.stem.lexer import RELATION_LOOKALIKES, is_sign_error, lex, sign_outside_grammar
from epinoic_logic.stem.limits import profile_for
from epinoic_logic.stem.normalize import SIGN_FORMS, reading_view
from epinoic_logic.stem.spans import find_spans

from ..overseer_attach import overseer

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
KEY = b"integration-gate-4-stem-key-0123456789"
SECRET = b"integration-gate-4-stem-secret-0123456789"
SUBJECTS = {"physics": "Physics", "mathematics_aa": "Mathematics: Analysis and Approaches", "chemistry": "Chemistry"}
PHYS, AA = "physics", "mathematics_aa"
TROLLEY = "A trolley accelerates uniformly from rest to 20 m s⁻¹ in 4.0 s. Calculate its acceleration."
FIND_X = "Find x = 3 + 4."
WRONG_STEP = "The trolley starts from rest. a = (20 - 0)/4.0 {} 6.0 m s⁻²."
RIGHT_STEP = "The trolley starts from rest. a = (20 - 0)/4.0 {} 5.0 m s⁻²."

#: the characters the lens found read as nothing: the four now '=' in the reading view, then the four now named
EQUALS_FORMS = ["\U0001f7f0", "\ua78a", "\u30a0", "\u2e40"]
NAMED_LOOKALIKES = ["\u02ed", "\u2550", "\u268c", "\u3013"]
#: the rest of the class: the other look-alikes of a relation sign, and relation signs of other categories by their name
FURTHER_LOOKALIKES = ["\u1400", "\ua4ff", "\u2e17", "\u2630", "\u02c2", "\u02c3"]
NAMED_BY_CATEGORY = ["\u2bf9", "\u2338", "\u0347", "\u236f", "\u2343"]
#: signs outside the grammar that cut correct working into a fragment that failed (the sweep): their reading by place, or by name
PLACE_SIGNS = ["\u2022", "\u2731", "\u204e", "\u066d", "\u271a", "\u2719", "\u2571", "\u27cb", "\u2e4a", "\ufe68", "\uff3c", "\U0001f67c",
               "\u2f03", "\u02d6"]


def receive(profile: str, answer: str, request: str = "Answer the question."):
    agent = "stem-specialist"
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer", selected_agent_ids=[agent]))
    m, _, _ = hub.dispatch("t", agent, request, [])
    _reply, rc = hub.receive("t", m.message_id, answer, agent_id=agent, report_id="rep-t-0")
    return rc


def audited(profile: str, answer: str, request: str):
    """The receipt and the transfer audit's state on a hub with the overseer's auditor attached, as the lens reproduced the finding."""
    ov = overseer()  # the overseer's public package API: skips the test where it is not installed
    keyring = ov.KeyRing({k: ov.EngineKey(KEY) for k in ("hub", "channel", "default", "integrity")}, SECRET)
    hub = RouterHub(signing_key=KEY, key_id="hub", config=CFG, auditor=ov.TransferAuditor(keyring, replay_mode="inline", eager=True, shadow="always"))
    try:
        hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=SUBJECTS[profile], task_type="short_answer",
                               selected_agent_ids=["stem-specialist"]))
        m, _req, _rq = hub.dispatch("t", "stem-specialist", request)
        _reply, rc = hub.receive("t", m.message_id, answer, agent_id="stem-specialist", report_id="r1")
        audit = hub.audit("t")
    finally:
        hub.close()
    return rc, getattr(audit.state, "value", audit.state), audit


def failed(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is False}


def held(rc) -> set[str]:
    return {c.constraint_id for c in rc.formal_checks if c.satisfied is True}


def codes(rc) -> list[str]:
    return [f.code for f in rc.findings]


def structural(rc) -> list[str]:
    return [f.code for f in rc.structural_findings]


def message(rc, code: str) -> str:
    return " ".join(f.message for f in rc.findings if f.code == code)


def errors(rc) -> list[str]:
    return [f.code for f in list(rc.findings) + list(rc.structural_findings) if f.severity == "error"]


# ============================================================================================ major: rule sign-forms in every category
@pytest.mark.parametrize("sign", EQUALS_FORMS)
def test_a_wrong_step_written_with_an_equals_sign_of_another_category_is_checked(sign):
    rc, state, audit = audited(PHYS, WRONG_STEP.format(sign), TROLLEY)
    # before: ('ACCEPTED', no findings, no structural findings, no formal checks, AUDIT_PASSED)
    assert "stem-eq-1" in failed(rc) and "c = 5, r = 6" in message(rc, "INT-SUBJ-001"), (sign, rc.formal_checks, codes(rc))
    assert state == "AUDIT_PASSED", (sign, state, [(f.code, f.message[:160]) for f in audit.report.findings])
    ok = receive(PHYS, RIGHT_STEP.format(sign), TROLLEY)
    assert "stem-eq-1" in held(ok) and not failed(ok) and not errors(ok), (sign, ok.formal_checks, codes(ok))


@pytest.mark.parametrize("sign", EQUALS_FORMS)
def test_mathematics_written_with_an_equals_sign_of_another_category_is_checked(sign):
    bad = receive(AA, f"x = 3 + 4 {sign} 8", FIND_X)
    # before (U+A78A): only the heuristic INT-REQ-004
    assert "stem-eq-1" in failed(bad) and "c = 7, r = 8" in message(bad, "INT-SUBJ-001"), (sign, bad.formal_checks, codes(bad))
    ok = receive(AA, f"x = 3 + 4 {sign} 7", FIND_X)
    assert "stem-eq-1" in held(ok) and not failed(ok) and not errors(ok), (sign, ok.formal_checks, codes(ok))


@pytest.mark.parametrize("sign", NAMED_LOOKALIKES)
def test_a_wrong_step_written_with_a_look_alike_of_equals_is_named(sign):
    rc, state, audit = audited(PHYS, WRONG_STEP.format(sign), TROLLEY)
    # before: ('ACCEPTED', no findings, no structural findings, no formal checks, AUDIT_PASSED)
    assert "ST-PARSE-001" in structural(rc) and not held(rc) and rc.status.value != "ACCEPTED", (sign, rc.status, structural(rc), rc.formal_checks)
    assert state == "AUDIT_PASSED", (sign, state, [(f.code, f.message[:160]) for f in audit.report.findings])
    for answer, request in ((RIGHT_STEP.format(sign), TROLLEY), (f"x = 3 + 4 {sign} 7", FIND_X)):
        ok = receive(PHYS if request is TROLLEY else AA, answer, request)
        assert "ST-PARSE-001" in structural(ok) and not failed(ok) and not errors(ok), (answer, ok.formal_checks, codes(ok))
    bad = receive(AA, f"x = 3 + 4 {sign} 8", FIND_X)
    assert "ST-PARSE-001" in structural(bad) and not held(bad), (sign, structural(bad), bad.formal_checks)


@pytest.mark.parametrize("sign", FURTHER_LOOKALIKES + NAMED_BY_CATEGORY)
def test_the_rest_of_the_class_is_named(sign):
    for answer, request in ((WRONG_STEP.format(sign), TROLLEY), (f"x = 3 + 4 {sign} 8", FIND_X), (f"x {sign} 6", "Find x.")):
        rc = receive(PHYS if request is TROLLEY else AA, answer, request)
        assert "ST-PARSE-001" in structural(rc) and not held(rc) and not errors(rc), (answer, structural(rc), rc.formal_checks, codes(rc))


def test_the_new_equals_forms_map_one_for_one():
    text = "".join(EQUALS_FORMS)
    assert all(SIGN_FORMS[ch] == "=" for ch in EQUALS_FORMS)
    assert reading_view(text) == "=" * len(EQUALS_FORMS)
    assert reading_view("a = 20/4.0 \U0001f7f0 5.0") == "a = 20/4.0 = 5.0"


def test_signs_of_other_categories_by_their_name():
    for ch in ("⯹", "⌸", "⍯", "\u0347", "\u034c", "⍃", "⍄", "꞊", "\U0001f7f0"):
        assert sign_outside_grammar(ch) == "relation", (hex(ord(ch)), unicodedata.name(ch))
    for ch in ("˖", "˗", "⹊", "﹨", "＼", "\U0001f67c"):
        assert sign_outside_grammar(ch) == "operator", (hex(ord(ch)), unicodedata.name(ch))
    # brackets, invisible tags and symbols whose name only mentions a sign are no signs ('LEFT ARC LESS-THAN BRACKET', 'TAG EQUALS SIGN',
    # 'GINGER ROOT', 'CIRCLED ZERO WITH SLASH', 'BLACK DIAMOND MINUS WHITE X'); round 3's decisions stand
    for ch in ("⦓", "\U000e003d", "\U0001fada", "\U0001f10d", "❖", "∈", "⊆", "∵", "="):
        assert sign_outside_grammar(ch) == "", (hex(ord(ch)), unicodedata.name(ch, "?"))
    assert sign_outside_grammar("⨯") == "operator" and sign_outside_grammar("≪") == "relation"


def test_the_look_alikes_stay_unknown_characters_and_the_unread_relation_rule_reads_them():
    for ch in RELATION_LOOKALIKES:
        assert sign_outside_grammar(ch) == "" and _relation_sign(ch), (hex(ord(ch)), unicodedata.name(ch))
    # a frame line, a menu sign or a trigram around working absorbs nothing: the working is read as before
    for text in ("══════\nx = 5 + 2 = 7", "x = 5 + 2 = 7 ══════", "Click ☰ to open the menu. x = 5 + 2 = 7"):
        doc = build_document(text, "Find x.", AA)
        assert "x" in doc.bindings and not [f for f in doc.findings if f.code == "ST-PARSE-001"], (text, dict(doc.bindings), doc.findings)
        assert [r.check_id for r in doc.checks] == ["stem-eq-1"], (text, doc.checks)


def test_every_relation_sign_of_another_category_is_read_or_named():
    """The class by name: every non-ASCII symbol, dash, punctuation mark or combining mark outside Sm whose Unicode name holds the word
    EQUAL, EQUALS, LESS-THAN or GREATER-THAN is a relation sign of the grammar in the reading view or a relation sign the unread-relation
    rule names."""
    missed = []
    for cp in range(0x80, 0x110000):
        ch = chr(cp)
        category = unicodedata.category(ch)
        if category == "Sm" or category not in ("Sk", "So", "Pd", "Po", "Mn", "Me"):
            continue
        words = set(unicodedata.name(ch, "").split())
        if words.isdisjoint({"EQUAL", "EQUALS", "LESS-THAN", "GREATER-THAN"}):
            continue
        if reading_view(ch) not in ("=", "<", ">") and not _relation_sign(ch):
            missed.append(f"U+{cp:04X}")
    assert not missed, missed


# ============================================================================================ rule sign-forms by place
@pytest.mark.parametrize("sign", PLACE_SIGNS)
def test_correct_working_with_a_sign_outside_the_grammar_between_numerals_is_no_error(sign):
    # before: 'x = 3 C 4 = 12' read as '4 = 12' (INT-SUBJ-001, c = 4, r = 12) and x bound to 3; '20 C 4.0 = 5.0' read as '4.0 = 5.0'
    rc = receive(AA, f"x = 3 {sign} 4 = 12", "Find x.")
    assert not failed(rc) and not errors(rc) and "ST-PARSE-001" in structural(rc), (sign, rc.formal_checks, codes(rc), structural(rc))
    rc = receive(PHYS, f"The trolley starts from rest. a = (20 - 0) {sign} 4.0 = 5.0 m s⁻².", TROLLEY)
    assert not failed(rc) and not errors(rc) and "ST-PARSE-001" in structural(rc), (sign, rc.formal_checks, codes(rc), structural(rc))
    doc = build_document(f"x = 3 {sign} 4 = 12", "Find x.", AA)
    assert "x" not in doc.bindings, (sign, dict(doc.bindings))


@pytest.mark.parametrize("sign", ["\U0001f34e", "•", "✱", "٫"])
def test_a_wrong_step_with_an_unknown_sign_between_numerals_is_named(sign):
    # before: 'a = (20 - 0)/4.0 🍎 6.0' read as the binding a = 5 with nothing named
    rc, state, audit = audited(PHYS, WRONG_STEP.format(sign), TROLLEY)
    assert "ST-PARSE-001" in structural(rc) and not held(rc), (sign, structural(rc), rc.formal_checks)
    assert state == "AUDIT_PASSED", (sign, state, [(f.code, f.message[:160]) for f in audit.report.findings])


def test_the_place_rule_leaves_the_rest_as_it_was():
    # the signs round 3 left as unknown characters (sets, arrows, ∵) are read as before; a sign between a unit or a symbol and the next
    # value (an inline list) is read as before; the signs of the grammar are read as before
    for text, symbols in (("x = 2 ∈ (1, 3)", {"x"}), ("x = 2 ↦ 4", {"x"}), ("x = 2 ∵ 3 > 1", {"x"}), ("m = 2 kg • v = 3 m s⁻¹", {"m", "v"}),
                          ("x = 5 • y = 6", {"x", "y"})):
        doc = build_document(text, "Find x.", AA)
        assert symbols <= set(doc.bindings) and not [f for f in doc.findings if f.code == "ST-PARSE-001"], (text, dict(doc.bindings), doc.findings)
    for answer in ("x = 3 × 4 = 12", "x = 3 · 4 = 12", "x = 3 ✖ 4 = 12"):
        rc = receive(AA, answer, "Find x.")
        assert "stem-eq-1" in held(rc) and not failed(rc), (answer, rc.formal_checks)
    toks = lex("x = 3 • 4 = 12").tokens
    assert [t.text for t in toks if is_sign_error(t)] == ["•"], toks
    assert not any(is_sign_error(t) for t in lex("Data: 5 m • 3 s").tokens)


def test_a_number_glued_after_a_sign_between_numerals_is_no_prose_value():
    # the bullet of '5\u20223' had been an unknown character, after which a glued number is no value the prose states; read as a sign
    # between numerals it must stay so ('3' would have become a stated value), and so after a sign of the grammar's own rule ('3\u2a2f4')
    for text, values in (("The values are 5\u20223 and 7.", ["5", "7"]), ("3\u2a2f4 is 12.", ["3", "12"])):
        doc = build_document(text, "Find a.", PHYS)
        assert [text[p.start:p.end] for p in doc.prose_values] == values, (text, doc.prose_values)


# ============================================================================================ invisible characters
@pytest.mark.parametrize("answer, held_id", [("x = 3 ✖\ufe0f 4 = 12", "stem-eq-1"), ("x = 3 ➕\ufe0f 4 = 7", "stem-eq-1"),
                                             ("x = 3 + 4\u2062 = 7", "stem-eq-1"), ("x = 3 +\u200e 4 = 7", "stem-eq-1")])
def test_correct_working_with_an_invisible_character_holds(answer, held_id):
    # before: 'x = 3 ✖\ufe0f 4 = 12' and 'x = 3 ➕\ufe0f 4 = 7' read as '4 = 12' and '4 = 7' (INT-SUBJ-001 on correct work)
    rc = receive(AA, answer, "Find x.")
    assert held_id in held(rc) and not failed(rc) and not errors(rc), (answer, rc.formal_checks, codes(rc))


def test_a_wrong_step_with_the_emoji_selector_is_checked():
    rc = receive(AA, "x = 3 + 4 \U0001f7f0\ufe0f 8", FIND_X)
    assert "stem-eq-1" in failed(rc) and "c = 7, r = 8" in message(rc, "INT-SUBJ-001"), (rc.formal_checks, codes(rc))


@pytest.mark.parametrize("mark", ["\u200e", "\u200f", "\u2066", "\u202a", "\u00ad", "\u2062", "\u2064", "\ufe0f", "\U000e0041", "\u061c"])
def test_an_invisible_mark_between_numerals_reads_as_a_blank(mark):
    # before: 'x = 3\u200e4 = 12' (with a left-to-right mark the reader cannot see) read as '4 = 12', an error; with a blank the relation is
    # named unread.
    # Rewritten to a stricter rule by the round-8 clearance's handoff fixer (rule bidi-text): an answer holding a bidirectional isolate
    # or embedding (U+2066, U+202A) is now refused by the channel before it is parsed (INT-REQ-009, REJECTED, nothing checked or
    # delivered); what the STEM pack reads in it (no failed check, the relation named ST-PARSE-001) is kept, asserted on the pack.
    for answer in (f"x = 3{mark}4 = 12", f"x = 3 {mark} 4 = 12"):
        rc = receive(AA, answer, "Find x.")
        if mark in ("\u2066", "\u202a"):
            assert rc.status.value == "REJECTED" and codes(rc).count("INT-REQ-009") == 1 and f"U+{ord(mark):04X}" in message(rc, "INT-REQ-009") \
                and not rc.formal_checks and not rc.structural_findings, (answer, codes(rc))
            clear_document_cache()
            plan = build_checks(build_document(answer, "Find x.", "mathematics_aa"), report_id="r", request_id="q")
            st = [f.code for f in (*build_document(answer, "Find x.", "mathematics_aa").findings, *plan.findings)]
            assert not plan.checks and "ST-PARSE-001" in st, (answer, plan.checks, st)
            continue
        assert not failed(rc) and not errors(rc) and "ST-PARSE-001" in structural(rc), (answer, rc.formal_checks, codes(rc))
    view = reading_view(f"a{mark}b")
    assert view == "a b" and len(view) == 3


# ============================================================================================ a relation sign right after a sign outside the grammar
@pytest.mark.parametrize("answer", ["x = 3 + 4 ⨯ = 8", "x = 3 + 4 ⨯ = 7", "⨯ = 5", "x = 3 + 4 ≒ = 8"])
def test_a_relation_after_a_sign_outside_the_grammar_is_named(answer):
    # before: the relation after the sign was dropped with nothing named ('x = 3 + 4 ⨯ = 8': only the heuristic INT-REQ-004)
    rc = receive(AA, answer, "Find x.")
    assert "ST-PARSE-001" in structural(rc) and not failed(rc) and not errors(rc), (answer, structural(rc), rc.formal_checks, codes(rc))


# ============================================================================================ the class, character by character
#: the categories of the place rule and the names it leaves alone (lexer._PLACE_SIGN_CATEGORIES, lexer._PLACE_EXCEPT_WORDS)
_PLACE_CATEGORIES = ("Sm", "So", "Sk", "Po", "Mn", "Me")
_PLACE_EXCEPT = ("ELEMENT", "SUBSET", "SUPERSET", "CONTAINS", "SUBGROUP", "ARROW", "BECAUSE")


def test_no_sign_between_two_numerals_is_read_as_nothing():
    """Every non-ASCII symbol, punctuation mark and combining mark of the place rule's categories, written between two numerals, is read as
    a token of the grammar or a sign outside it (or as a blank, when invisible): none is an unknown character that ends the run. Before
    the fix, 10,853 of the 11,205 non-ASCII symbols, punctuation marks, marks and format characters cut correct working between two
    numerals into a checked fragment."""
    unread = []
    for cp in range(0x80, 0x110000):
        ch = chr(cp)
        if unicodedata.category(ch) not in _PLACE_CATEGORIES or any(w in unicodedata.name(ch, "") for w in _PLACE_EXCEPT):
            continue
        text = reading_view(f"3 {ch} 4")
        if text[2] == " ":
            continue  # invisible: a blank
        toks = lex(text).tokens
        at = [t for t in toks if t.start <= 2 < t.end]
        if at and at[0].kind == "OTHER":
            unread.append(f"U+{cp:04X}")
    assert not unread, (len(unread), unread[:40])


@pytest.mark.parametrize("sign", ["•", "\U0001f34e", "═", "✱", "˖", "٫", "\u0307"])
def test_no_fragment_after_a_sign_between_numerals_is_planned(sign):
    for text, request, profile in ((f"x = 3 {sign} 4 = 12", "Find x.", AA), (f"a = 20 {sign} 4.0 = 5.0 m s⁻²", "Find a.", PHYS)):
        doc = build_document(text, request, profile)
        cut = text.index(sign) + 1
        assert not [r for r in doc.relations if r.outcome == "check" and r.left is not None and r.left.start >= cut], (text, doc.checks)


# ============================================================================================ the transfer audit of the new readings
@pytest.mark.parametrize("profile, request_, answer", [
    (AA, FIND_X, "x = 3 + 4 ꞊ 8"),
    (AA, "Find x.", "x = 3 ✖\ufe0f 4 = 12"),
    (AA, "Find x.", "x = 3 • 4 = 12"),
    (AA, "Find x.", "x = 3 + 4 ⨯ = 8"),
    (AA, "Find x.", "x = 3\u200e4 = 12"),
])
def test_the_transfer_audit_rederives_the_new_readings(profile, request_, answer):
    _rc, state, audit = audited(profile, answer, request_)
    assert state == "AUDIT_PASSED", (answer, state, [(f.code, f.message[:160]) for f in audit.report.findings])


# ============================================================================================ the new readings on hostile input
N = 20_000
HOSTILE = {
    "heavy equals signs": "\U0001f7f0 " * (N // 2) + "x", "short equals signs": "꞊" * N + "x", "frame line": "═" * N + "x",
    "look-alike relations": "x ═ 1 " * (N // 6) + "!", "bullets between numerals": "3 • " * (N // 4) + "x",
    "glued signs between numerals": "3•" * (N // 2) + "x", "invisible times": "3\u2062" * (N // 2) + "x",
    "emoji selectors": "✖\ufe0f" * (N // 2) + "x", "direction marks": "\u200e" * N + "x", "tags": "\U000e0041" * N + "x",
    "signs before relations": "x = 3 + 4 ⨯ = " * (N // 14) + "!", "decimal separators": "3 ٫ " * (N // 4) + "x",
    "named operators": "3 ˖ " * (N // 4) + "x", "mixed look-alikes": "4.0 ⚌ 6.0 〓 " * (N // 12) + "!",
}
#: per call, CPU seconds: a direct entry point (measured under 0.3 s on every shape) and a whole document with its checks
#: (measured under 0.6 s); a quadratic scan of 20,000 characters takes seconds, a regular-expression blow-up far longer
DIRECT_BOUND = 2.0
DOCUMENT_BOUND = 8.0


@pytest.mark.parametrize("shape", sorted(HOSTILE))
def test_the_new_readings_stay_linear_on_hostile_input(shape):
    text = HOSTILE[shape]
    clear_document_cache()
    for name, call, bound in (("reading_view", lambda: reading_view(text), DIRECT_BOUND), ("lex", lambda: lex(reading_view(text)), DIRECT_BOUND),
                              ("find_spans", lambda: find_spans(text, profile=profile_for(AA)), DIRECT_BOUND),
                              ("build_document", lambda: build_checks(build_document(text, "Find x.", AA)), DOCUMENT_BOUND)):
        c0 = time.process_time()
        call()
        spent = time.process_time() - c0
        assert spent < bound, (shape, name, round(spent, 2))
    assert len(reading_view(text)) == len(text)
