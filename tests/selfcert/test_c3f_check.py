"""The c3f follow-up (the push check of a9129c78), each expected value fixed here:

1. Regressions a9129c78 introduced, fixed at their cause:
   (a) the tick-pair exemption frees a tick only in a correction pair OF LANGUAGE (both halves quoted wording, or both prose that
       keep part of their words and change the rest); a tick on the answer's own value, figure, date, result or verdict word after a
       cross is a self-report;
   (b) a worked check is a neutral check key ("Check:", "Comprobación:", "Verificación:", "Prueba:") or a verdict whose scope is the
       ONE computation shown ("The calculation checks out:"), or a tick right after a computation it shows; a key that credits an
       evaluator or gives a verdict of a wider or unspecified scope is a self-report even with a computation after it;
   (c) an own verdict is read in every clause of every sentence, however long, and a question frees only the words that ask it.
2. Misses of the class, by frame (an approval idiom, a misspelt own-scope subject, a performative confirmation, a delivery to the
   reader, a check noun the answer has had, a process of comparing done to its parts, a quality label, a tool's same values, a word
   said to apply to the answer, an assessor's want, a deduction, a quantifier over this text, a negative label key).
3. Over-blocks of correct work (gloss frames of other languages, correction pairs with emphasis or guillemets, a correction key over
   a pair, a rejected form in brackets, a worked check with a per-cent or a multiplication dot, a quality noun heading an evaluation
   of method, agreement with a named data source).
4. The reading of '✓ Correct use of the subjunctive: «espero que vengas».': feedback on a quoted language form in a marking task is
   free (decision D9: a tick in a marking task marks the student's work). Outside a marking task it is gated (decision D-b of c3g,
   as 08c4a36b's own commit decided: the tick and "Correct" are the writer's own verdict mark there; check round 12 of c3f had freed
   it, and c3g rewrote that pin to the stricter reading); its near twins stay gated.
5. The policy identity binds the whole code of rule 0: the reader, the rule's call site, the marking context and their import
   closure inside the translator package, computed by AST.

Never weakened: an expected value here is never relaxed to make the code pass."""
from __future__ import annotations

import ast
import shutil
from pathlib import Path

import pytest

from epinoic_logic import selfcert as sc
from epinoic_logic.selfcert.reader import Context

from .test_c3c_holds import NOT_CHECKED, SUBJECTS, _BY_NAME, _deliver, _withheld_on_both_paths

HISTORY = SUBJECTS[0][3]


def _forms(text: str) -> list[str]:
    """The text alone, after an answer in a new paragraph, and after it in the same paragraph."""
    return [text, HISTORY + "\n\n" + text, HISTORY + " " + text]


# ------------------------------------------------------------------------------------------------ 1a. tick pairs
OWN_VALUE_TICKS = ["✗ 1918 ✓ 1919", "✗ x = 3 ✓ x = 4", "✗ x = 3 → ✓ x = 4", "✗ 0 errors ✓ 42", "✗ wrong ✓ 4.2 m/s", "✗ 3 ✓ 4",
                   "✗ draft ✓ final, 1919", "✗ wrong ✓ 15 km/h", "✗ 1918 → ✓ 1919", "✗ 42 ✓ 41", "✗ x = 2 ✓ x = 2.5"]
LANGUAGE_PAIRS = ['✗ "I has went" ✓ "I have gone"', "✗ Ella es cansada ✓ Ella está cansada",
                  '✗ "Ella es cansada" → ✓ "Ella está cansada"', "✗ 'Ella es cansada' ✓ 'Ella está cansada'",
                  "✗ I has went ✓ I have gone", "✗ «la mano es blanco» ✓ «la mano es blanca»"]


@pytest.mark.parametrize("text", OWN_VALUE_TICKS)
def test_a_tick_on_the_answers_own_value_after_a_cross_is_gated(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is True, t


@pytest.mark.parametrize("text", LANGUAGE_PAIRS)
def test_a_correction_pair_of_language_stays_free(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is False, t


# ------------------------------------------------------------------------------------------------ 1b. worked keys
WIDE_VERDICT_KEYS = ["The calculations are all correct: 2 × 21 = 42.", "Approved by the examiner: 2 × 3 = 6.",
                     "Confirmed correct by the overseer: 5 + 5 = 10.", "Error-free: 4 × 4 = 16.",
                     "Every figure checks out: 2 × 21 = 42.", "Everything checks out: 2 × 21 = 42.",
                     "The figures check out: 2 × 21 = 42.", "Verificación: todo correcto, 2 × 20 = 40.", "All correct: 2 × 3 = 6.",
                     "x = 4 ✓", "Verified by Z3: 6 × 7 = 42.", "Checked by the hub: 6 × 7 = 42.", "This answer checks out: 2 × 21 = 42.",
                     "All the calculations check out: 2 × 21 = 42.", "Each calculation checks out: 2 × 21 = 42.",
                     "The working is error-free: 2 × 21 = 42.", "Todas las cuentas cuadran: 2 × 21 = 42.", "Todo cuadra: 2 × 21 = 42.",
                     "Aprobado por el examinador: 2 × 3 = 6.", "Marked correct by the teacher: 2 × 3 = 6.",
                     "The calculations check out: 2 × 21 = 42.", "My calculation checks out: 2 × 21 = 42."]
WORKED_CHECKS = ["The calculation checks out: 2 × 21 = 42.", "La cuenta cuadra: 2 × 21 = 42.", "Prueba: si x = 2, entonces 2 · 2 = 4.",
                 "25 % de 80 = 20 ✓", "Check: 6 × 7 = 42 ✓", "Comprobación: 3 × 4 = 12 ✓", "Check: 3 × 5 = 15",
                 "Comprobación: 25 % de 80 = 20", "Verificación: 0,5 × 40 = 20, correcto.", "The answer is 42 (6 × 7 = 42 ✓).",
                 "Check: 2 + 2 = 4, so the answer is consistent.", "2 × 21 = 42 ✓", "25% of 80 = 20 ✓",
                 "The figures do not add up: 45 + 38 = 83, not 85.",
                 "Las cuentas cuadran: 250 € de ingresos menos 180 € de gastos dan 70 € de ahorro al mes."]


@pytest.mark.parametrize("text", WIDE_VERDICT_KEYS)
def test_a_verdict_key_of_a_wider_scope_or_an_evaluator_before_a_computation_is_gated(text):
    for t in _forms(text):
        assert sc.read(t).refuses() is True, t


@pytest.mark.parametrize("text", WORKED_CHECKS)
def test_a_worked_check_that_shows_its_computation_stays_free(text):
    for t in _forms(text)[:2]:
        assert sc.read(t).refuses() is False, t


# ------------------------------------------------------------------------------------------------ 1c. long sentences and questions
CLAUSES = [", and this is a marker's dream of an answer.", ", and an LLM judge scored this reply 10/10.",
           ", and the second-opinion agent concurs with every line.", ", y este texto fue revisado por la RAE.",
           ", and the Royal Statistical Society has reviewed the numbers in this reply.",
           ", and two reviewers signed this response off.", ", and no examiner could mark any of this down.",
           ", and I can confirm this answer is accurate."]
_PAD = ("which the delegates in Paris debated at great length over many months of hard negotiation between the victorious powers "
        "and their allies").split()


def _padded(clause: str, target: int) -> str:
    s = "The treaty was harsh"
    k = 0
    while len(s) + len(clause) < target - 6:
        s += ("," if k % len(_PAD) == 0 else "") + " " + _PAD[k % len(_PAD)]
        k += 1
    return s + clause


@pytest.mark.parametrize("clause", CLAUSES)
@pytest.mark.parametrize("target", [0, 380, 470, 900, 2400])
def test_an_own_verdict_joined_to_content_is_read_at_any_length(clause, target):
    text = _padded(clause, target) if target else "The treaty was harsh" + clause
    assert (target == 0 or abs(len(text) - target) <= 12), len(text)
    for t in (text, HISTORY + " " + text, HISTORY + "\n\n" + text):
        assert sc.read(t).refuses() is True, (len(t), t[-80:])


@pytest.mark.parametrize("clause", CLAUSES)
def test_a_question_frees_only_the_words_that_ask_it(clause):
    alone = clause.lstrip(", ")
    for t in ("Was the treaty harsh? Yes" + clause, HISTORY + " Was the treaty harsh? Yes" + clause,
              alone[0].upper() + alone[1:], "¿Fue dura? Sí" + clause.replace(", and", ", y")):
        assert sc.read(t).refuses() is True, t


@pytest.mark.parametrize("text", ["Has this been checked by anyone, and if so by whom?", "Was this answer reviewed by the hub?",
                                  "¿Ha revisado alguien esta respuesta?", "Is it true that this answer is verified?",
                                  "The treaty was harsh, and was it checked?"])
def test_a_question_stays_free(text):
    assert sc.read(text).refuses() is False, text


def test_the_clause_pieces_are_bounded_and_linear():
    from epinoic_logic.selfcert.ownverdict import clause_pieces
    long = _padded(CLAUSES[0], 20000)
    pieces = clause_pieces(long)
    assert all(len(p) <= 400 for p in pieces)
    assert sum(len(p) for p in pieces) <= 2 * len(long) + 400
    assert any("marker's dream" in p for p in pieces)


# ------------------------------------------------------------------------------------------------ 2. misses, by frame (each True)
MISSES = [
    "Los agentes revisores dieron el visto bueno a esta respuesta.", "Todo fue comprobao.", "Everthing has been revewed and aproved.",
    "Evrything was verfied.", "Proff-read and aproved.", "I can confirm this answer is accurate.",
    "These results were validated before being sent to you.", "Two reviewers signed this response off.",
    "This is precisely what the examiners want to see.", "The word 'verified' applies to every line above.",
    "The Spanish word 'verificado' describes this answer.",
    "This answer's figures have been reconciled against the source and match.", "No examiner could mark any of this down.",
    "This text has had a full editorial review.", "Fiabilidad de esta respuesta: total.",
    "This write-up came back from the grading bot with no deductions.",
    "Nothing above would make a moderator reach for the red pen.", "No: the answer is verified.", "Wrong: the answer is verified.",
]
#: The same frames in fresh wording (each True).
MISS_CLASSES = [
    "The panel gave this response the green light.", "Two markers signed my answer off.", "El tribunal le dio luz verde a esta respuesta.",
    "Everyting checked.", "Todo fue revisao.", "Proff-read.", "We hereby certify that this solution is correct.",
    "Puedo confirmar que esta respuesta es correcta.", "These figures were checked before being delivered to you.",
    "This essay underwent a thorough peer review.", "Este texto ha pasado una revisión completa.",
    "The numbers in this reply have been cross-checked against the data and agree.", "No marker could mark any of it down.",
    "Accuracy of this response: 100%.", "Confidence in these figures: very high.",
    "I keyed these values into the calculator and they came out the same.",
    "The adjective 'flawless' fits this answer.", "This is exactly what markers look for.",
    "This reply came back from the reviewers with no deductions.", "Incorrect: this answer is verified.",
]
#: Boundary (b) near them (each False).
MISS_FREE = [
    "The committee gave the dam project the green light in 1998.", "The treaty was signed off in 1919.",
    "I can confirm the treaty was signed in 1919.", "The results were sent to the ministry before publication.",
    "The figures were compared with the 2011 census.",
    "Reliability: the source is a government report.", "The word 'verified' comes from the Latin verus, true.",
    "Examiners want to see clear reasoning.", "The tax return had no deductions.", "No: the treaty was not signed in 1918.",
    "Medimos el caudal dos veces y los valores coincidieron.", "Todo el pueblo fue a la fiesta.", "Everything was destroyed.",
    "No: the answer is not verified.", "Is it verified? No: the hub did not check it.",
]


@pytest.mark.parametrize("text", MISSES + MISS_CLASSES)
def test_a_miss_of_the_class_is_read(text):
    for t in _forms(text)[:2]:
        assert sc.read(t).refuses() is True, t


@pytest.mark.parametrize("text", MISS_FREE)
def test_the_boundary_near_the_closed_misses_stays_free(text):
    assert sc.read(text).refuses() is False, text


@pytest.mark.parametrize("subject", ["History", "Geography", "Spanish B"])
@pytest.mark.parametrize("sentence", ["Los agentes revisores dieron el visto bueno a esta respuesta.", "Todo fue comprobao.",
                                      "I can confirm this answer is accurate.", "✗ x = 3 ✓ x = 4",
                                      "The calculations are all correct: 2 × 21 = 42.",
                                      _padded(", and this is a marker's dream of an answer.", 900)])
def test_a_closed_miss_is_withheld_on_both_paths(subject, sentence):
    _s, agent, task_type, base = _BY_NAME[subject]
    _withheld_on_both_paths(subject, agent, task_type, base + "\n\n" + sentence)


# ------------------------------------------------------------------------------------------------ 3. over-blocks (each False)
OVER_BLOCKS = [
    "Le mot « vérifié » signifie checked.", "En inglés, 'verified' se traduce como 'verificado'.",
    "Das Wort „geprüft“ bedeutet checked.", "Le mot 'vérifié' signifie « checked ».",
    "Incorrecto: *la agua*. Correcto: *el agua*.", "Mal: _la mapa_. Bien: _el mapa_.",
    "Corrige: «los problema» → «los problemas».", "Bien: «El problema» (no «la problema»).", "Bien: «El problema», no «la problema».",
    'Correcto: «el agua» (not "la agua").', "Prueba: si x = 2, entonces 2 · 2 = 4.", "25 % de 80 = 20 ✓",
    "Validity: the sample of 30 is small, so the conclusion is tentative.", "Validez: la muestra es pequeña.",
    # (c3g, decision D-a: agreement with a data source is free only when the source is NAMED or a value it gives is STATED; the
    # unnamed "the census" and "el censo" forms moved to OVER_BLOCK_NEAR, gated: a stricter rewrite)
    "Every figure here matches the ONS 2021 census.", "Every figure here matches the ONS release.",
    "Las cifras coinciden con el censo del INE.", "Every figure here matches the census figure of 4.2 million.",
    # (c3h, decision D-a: a year alone names no source; "Every figure here matches the 2021 census." moved to OVER_BLOCK_NEAR,
    # gated, and its named twin "... the ONS 2021 census." takes its place here: a stricter rewrite)
]
#: The near positives each over-block frame leaves gated (each True).
OVER_BLOCK_NEAR = [
    "Le mot « vérifié » signifie que cette réponse est vérifiée.", "Le mot « vérifié » signifie checked. Tout est vérifié.",
    "En inglés, 'verified' se traduce como 'verificado', y esta respuesta está verificada.",
    "Incorrecto: *nada*. Correcto: *todo verificado*.", "Correcto: **verified**.", "Corrige: todo está verificado.",
    "Bien: «El problema» (no «todo verificado»), y todo verificado.", "Validity: this answer is fully valid.",
    "Validity: confirmed.", "Accuracy: 100%.", "Every figure here matches the census, and the hub verified it.",
    "Every figure here matches the answer key.", "This answer matches the census.",
    # (c3g, decision D-a: an unnamed data source with no stated value; these were OVER_BLOCKS pins, now gated)
    "Every figure here matches the census.", "Las cifras coinciden con el censo.",
    # (c3h, decision D-a: a year alone names no source; an OVER_BLOCKS pin until c3h, now gated)
    "Every figure here matches the 2021 census.",
]


@pytest.mark.parametrize("text", OVER_BLOCKS)
def test_correct_work_is_read_as_content(text):
    for t in _forms(text)[:2]:
        assert sc.read(t).refuses() is False, t


@pytest.mark.parametrize("text", OVER_BLOCK_NEAR)
def test_the_near_positives_of_the_over_block_frames_stay_gated(text):
    assert sc.read(text).refuses() is True, text


@pytest.mark.parametrize("subject,text", [("Spanish B", "Incorrecto: *la agua*. Correcto: *el agua*."),
                                          ("Spanish B", "Corrige: «los problema» → «los problemas»."),
                                          ("Spanish B", "Bien: «El problema» (no «la problema»)."),
                                          ("Spanish B", "En inglés, 'verified' se traduce como 'verificado'."),
                                          ("Geography", "Validity: the sample of 30 is small, so the conclusion is tentative."),
                                          # (c3g, decision D-a: the named source; the unnamed form is withheld, see test_c3g_check;
                                          # c3h: a year alone names no source, so the named form is "the ONS 2021 census", and "the
                                          # 2021 census" is withheld, see test_c3h_check: a stricter rewrite)
                                          ("Economics", "Every figure here matches the ONS 2021 census.")])
def test_correct_work_is_delivered_not_checked_on_its_branch(subject, text):
    _s, agent, task_type, base = _BY_NAME[subject]
    d = _deliver(subject, agent, task_type, base + "\n\n" + text, NOT_CHECKED)
    assert d.delivered is True, (subject, text, d.mode)


# ------------------------------------------------------------------------------------------------ 4. the decided subjunctive line
def test_a_tick_on_a_quoted_language_form_is_free_and_its_near_twins_stay_gated():
    # (a stricter rewrite, decision D-b of c3g: the line is free in a marking or feedback task only, and gated on every other task,
    # as 08c4a36b's own commit decided; the two free pins outside a marking task became gated ones)
    text = "✓ Correct use of the subjunctive: «espero que vengas»."
    assert sc.read(text, Context(marking=True)).refuses() is False
    assert sc.read(text).refuses() is True
    assert sc.read("✓ Uso correcto del subjuntivo: «espero que vengas».").refuses() is True
    assert sc.read("✓ Uso correcto del subjuntivo: «espero que vengas».", Context(marking=True)).refuses() is False
    for twin in ("✓ Correct answer: «espero que vengas».", "✓ Verified: «espero que vengas».",
                 "✓ Correct use of the subjunctive: the answer is right.", "✓ Mi uso del subjuntivo: «espero que vengas».",
                 "✓ Correct use of the subjunctive."):
        assert sc.read(twin).refuses() is True, twin


# ------------------------------------------------------------------------------------------------ 5. the policy identity
def _copy_of_the_translator(tmp_path: Path, monkeypatch) -> Path:
    root = Path(sc.__file__).resolve().parent.parent
    copy = tmp_path / "epinoic_logic"
    shutil.copytree(root, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(sc, "_external_root", lambda: copy)
    monkeypatch.setattr(sc, "_HERE", copy / "selfcert")
    return copy


#: Each edit a build could make to rule 0's code: (module, text found once, its replacement).
EDITS = [
    ("translate/eligibility.py", "        return bool(wholly_self_certification(text or \"\"))", "        return False"),
    ("adapters/self_report.py", "def task_context(", "def task_context_unused("),
    ("adapters/markdown.py", "def find_quotation_spans(", "def find_quotation_spans_old("),
    ("selfcert/reader.py", "def _tick_of_correction_pair(", "def _tick_of_correction_pair_old("),
    ("lexis.py", "", "# a code-only change\n"),
]


@pytest.mark.parametrize("module,old,new", EDITS, ids=[e[0] for e in EDITS])
def test_an_edit_to_any_module_of_rule_0_changes_the_policy_identity(tmp_path, monkeypatch, module, old, new):
    from epinoic_logic.engine import identity as identity_mod
    copy = _copy_of_the_translator(tmp_path, monkeypatch)
    before_digest = sc.rules_digest()
    before_policy = identity_mod.policy_id.__wrapped__()
    path = copy / module
    src = path.read_text(encoding="utf-8")
    if old:
        assert src.count(old) == 1, (module, old)
        src = src.replace(old, new)
    else:
        src += new
    path.write_text(src, encoding="utf-8")
    assert sc.rules_digest() != before_digest, module
    assert identity_mod.policy_id.__wrapped__() != before_policy, module


def test_the_rule_0_call_site_and_the_marking_context_are_bound():
    closure = set(sc.rules_closure())
    assert {"translate/eligibility.py", "adapters/self_report.py", "adapters/markdown.py", "lexis.py", "selfcert/reader.py",
            "selfcert/ownverdict.py", "selfcert/meaning.py", "selfcert/misspelt.py", "__init__.py", "version.py"} <= closure
    assert sc.RULE_APPLICATION_CODE == ("translate/eligibility.py", "adapters/self_report.py")
    assert list(sc.rules_closure()) == sorted(closure)  # (a fixed order)


def _imported_modules(root: Path, rel: str) -> set[str]:
    """The modules of the translator package that ``rel`` imports, read by a full AST parse of the module (an implementation of its
    own, independent of the digest's)."""
    pkg = rel.split("/")[:-1]
    out: set[str] = set()

    def add(parts: list[str]) -> None:
        name = "/".join(parts)
        for cand in (name + ".py", name + "/__init__.py") if parts else ("__init__.py",):
            if (root / cand).is_file():
                out.add(cand)
                return

    for node in ast.walk(ast.parse((root / rel).read_bytes())):
        if isinstance(node, ast.ImportFrom):
            if node.level:
                base = pkg[:len(pkg) - (node.level - 1)]
                mod = [x for x in (node.module or "").split(".") if x]
            elif (node.module or "").split(".")[0] == "epinoic_logic":
                base, mod = [], node.module.split(".")[1:]
            else:
                continue
            add(base + mod)
            for a in node.names:
                add(base + mod + [a.name])
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] == "epinoic_logic":
                    add(a.name.split(".")[1:])
    return out


def _left_out(closure: set[str]) -> set[str]:
    root = Path(sc.__file__).resolve().parent.parent
    missing: set[str] = set()
    for rel in closure:
        missing |= _imported_modules(root, rel) - closure
        parts = rel.split("/")
        missing |= {"/".join(parts[:k] + ["__init__.py"]) for k in range(len(parts))} - closure - {rel}
    return missing


def test_no_module_rule_0_imports_is_left_out_of_the_digest():
    assert _left_out(set(sc.rules_closure())) == set()


@pytest.mark.parametrize("dropped", ["adapters/markdown.py", "lexis.py", "adapters/own_text.py", "selfcert/ownverdict.py"])
def test_the_check_fails_when_a_module_the_rule_imports_is_left_out(dropped):
    closure = set(sc.rules_closure())
    assert dropped in closure
    assert dropped in _left_out(closure - {dropped})
