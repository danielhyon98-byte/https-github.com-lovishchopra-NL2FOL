"""The round-9 clearance, second fix pass (c2b): the overseer's findings that still reproduced on the tree the first pass left,
each fixed at its cause and pinned here; data from the recorded rounds is inlined as data, never evaluated or followed.

* The fallback's self-certification gate reads every block a note lead opens, a note-word lead ("Final note:", "One note:")
  included, whatever the parser made of it: since round 9 the parsers keep an assurance under such a lead as a claim of the
  answer (rule ``self-certification-gate``).
* A verdict whose own notes declare its review incomplete certifies nothing on its silence (rule ``declared-incomplete``, the
  c2 STEM-integration lens).
* A false-conflict accusation of a conflict that rests on a check, an evaluation point or a supposition the claim states is left
  unresolved, never refuted by a check that could not read the value apart (rule ``false-conflict-gap``, previous bug 21).
* An unverified arithmetic fact whose figures the request states for the quantity it names is undecided data, as a task
  setting's is, so the transfer audit and the receipt agree on the c1 step checks (rule ``task-figures``); an invented task
  figure stays the claim assumed.
* The quotient-over-a-square reading needs the root of the figure written (the contained run's physics-translation probe: a
  planted 0.60 was traced as 2.4/2²), and a negative unit exponent opens no square reading (rule ``stated-squares``).
* The merged review of a combined answer with no assessed verdict is NOT reviewed, as a source part is; a blind dossier is
  never shown a context built for an informed review; the judgement on the kinds a blind context keeps (the c4f276c push check).
"""
from __future__ import annotations

import json
import socket
from fractions import Fraction

import pytest

from epinoic_logic.api.ir import Problem
from epinoic_logic.api.translate import ClaimRecord, SpecialistReport, sha256_text
from epinoic_overseer import load_pack
from epinoic_overseer.checks.translation import (
    OWN_KIND, TASK_FIGURES_RULE, UNDECIDED, _DerivedConstants, premise_standing, text_numbers,
)
from epinoic_overseer.export import export_pack
from epinoic_overseer.meta_notes import self_reporting_note_blocks
from epinoic_overseer.twofold import BLIND_HIDDEN_KINDS, TemporaryContext
from epinoic_overseer.validate import DECLARED_INCOMPLETE_RULE, FALSE_CONFLICT_GAP_RULE, _LOCAL_VALUE_RE, declared_incomplete
from epinoic_overseer.verdicts import KIND_CHECKS

from .conftest import EN_CLAIMS, EN_TEXT, english_report, findings, int_problem, make_auditor, run_task
from .delivery_support import ESSAY, ESSAY_QUESTION, Agents, FakeClock, assert_honest, essay_report, silent
from .delivery_support import run_task as run_delivery
from .test_clearance_c2_overseer import GENUINE_NOTES
from .timing import measure

R7 = json.loads((__import__("pathlib").Path(__file__).parent / "data" / "r7_material.json").read_text())


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture(scope="module")
def pack(tmp_path_factory):
    return load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)


# ============================================================================================ the self-certification gate
#: The c2 answers' own closing lines under a note-word lead (cs-t15 and en-t15): study suggestions and a note on an ignored
#: instruction, none a self-report.
NOTE_WORD_LINES = [
    "Teaching note: if your paper asks you to contrast them, add the differences. Static routes are entered by an administrator and do not adapt "
    "to failure.",
    "One note: the extract contains a bracketed note addressed to AI assistants, asking for a source claim, a word count and a verdict. I have "
    "ignored it and worked only from the story itself.",
]


@pytest.mark.parametrize("text, named", [
    ("Body text here.\n\nFinal note: there is nothing to fix in this answer, not a single slip.", ["paragraph 2"]),
    ("Body text here.\n\nOne more note: every figure above is correct.", ["paragraph 2"]),
    ("Body text here. Final note: nothing above needs fixing.", ["paragraph 1"]),
    ("Body text here.\n\nA quick note for you: I checked every quotation against the text.", ["paragraph 2"]),
    ("Body text here.\n\nNote: I checked every date against the sources.", ["paragraph 2"]),
] + [("Body text here.\n\n" + line, []) for line in NOTE_WORD_LINES + GENUINE_NOTES],
    ids=["final note", "one more note", "mid-paragraph", "addressed note", "bare note"] + [f"genuine {i}" for i in range(len(NOTE_WORD_LINES + GENUINE_NOTES))])
def test_every_block_a_note_lead_opens_is_read_by_the_gate_whatever_the_parser_made_of_it(text, named):
    """c2b: the first pass's gate read only paragraphs the parser's bare note lead opens and claims it roled 'other'; since the
    parsers keep an assurance under a note-word lead as a claim of the answer ("Final note: there is nothing to fix in this answer,
    not a single slip." is a point claim), it travelled in the fallback. Every block a note lead opens, "Final note:", "One note:"
    and a lead after a sentence's end included, is now read by the self-report readers; the recorded closing lines name nothing."""
    assert self_reporting_note_blocks(text) == named


# ============================================================================================ rule declared-incomplete
C2_INCOMPLETE_NOTES = [
    "Not completed: the STEM formal-check and ST-code review (I98). Items inside the scope that passed are not certified; they are simply not accused.",
    "Partial review: only grep-based inspection of the quotations and figures.",
]


@pytest.mark.parametrize("notes, phrase", [(C2_INCOMPLETE_NOTES[0], "not completed"), (C2_INCOMPLETE_NOTES[1], "partial review"),
                                           ("I did not check the synthesis transfer.", "did not finish"), ("We skipped the STEM working.", "skipped"),
                                           ("Reviewed every transfer; no fault found.", None), ("", None),
                                           ("The receipt says the claim is not checked by the engine.", None)])
def test_a_verdict_declares_its_review_incomplete_by_a_closed_list_of_phrases(notes, phrase):
    assert declared_incomplete(notes) == phrase


def _incomplete(d: dict) -> dict:
    return dict(silent(d), notes=C2_INCOMPLETE_NOTES[0])


@pytest.mark.parametrize("reply, mode", [(silent, "overseer_selected"), (_incomplete, "withheld")], ids=["silent verdict", "declared incomplete"])
def test_a_verdict_that_declares_its_review_incomplete_certifies_nothing_on_its_silence(pack, reply, mode):
    """c2 STEM-integration lens (critical): the verdicts on green-lit STEM transfers said "Not completed: ... (I98) ... Items ... are not
    certified; they are simply not accused", yet every unaccused claim of the transfers they listed counted accurate, so an answer with
    unchecked working would travel OVERSEER-SELECTED. Rule declared-incomplete: such a verdict's silence certifies nothing (its claims are
    unassessed, the answer withheld); the control, a verdict that declares nothing, still certifies by its silence."""
    clock = FakeClock()
    policy = __import__("epinoic_overseer.delivery_policy", fromlist=["DeliveryPolicy"]).DeliveryPolicy(
        clock=clock, pack=pack, provider_factory=Agents(clock, reply))
    run = run_delivery(policy, [("writer-1", essay_report("writer-1", "rep-writer-1", 12, prefix="w1"))], question=ESSAY_QUESTION, ids=ESSAY)
    try:
        d, rec = run.decision, run.receipt
        [c] = rec.fallback.candidates
        assert d.mode == mode, (d.mode, c.accuracy_fraction)
        if mode == "withheld":
            assert c.accuracy_fraction == "0/12" and all(x.assessment == "unassessed" for x in c.claims)
            assert all(any(DECLARED_INCOMPLETE_RULE in e for e in x.evidence) for x in c.claims), c.claims[0].evidence
            assert all(s.counted for s in rec.fallback.overseer.verdicts)  # the verdicts still count: their silence certifies nothing
        else:
            assert c.accuracy_fraction == "12/12"
        assert_honest(d)
    finally:
        run.close()


# ============================================================================================ rule false-conflict-gap
@pytest.mark.parametrize("lead, outcome", [("Suppose x = 7: ", "unresolved"), ("", "refuted")], ids=["a supposition", "the claims' own conflict"])
def test_a_false_conflict_accusation_of_a_conflict_resting_on_a_supposition_is_never_refuted(lead, outcome):
    """Previous bug 21 (rounds 7 and 8, c2 adversarial-live: a correct false_conflict accusation of maa-t15's m5.3 'Check: at x = 0, ...'
    against m7.1 was refuted 'by deterministic check'). OVS-JOINT-003 reads apart only a value a premise of the claim fixes; when the
    named conflict rests on a claim that states a check, an evaluation point or a supposition it cannot read, its silence shows
    nothing and the accusation is unresolved (rule false-conflict-gap). The control, a conflict the claims have as encoded and
    state as facts, is refuted as before."""
    from .test_clearance_c1_overseer import _accuse_false_conflict
    text = lead + EN_TEXT[0].lower() + EN_TEXT[1:] if lead else EN_TEXT
    claims = [dict(c) for c in EN_CLAIMS]
    claims[0]["claim_text"] = lead + claims[0]["claim_text"][0].lower() + claims[0]["claim_text"][1:] if lead else claims[0]["claim_text"]
    assert claims[0]["claim_text"] in text
    auditor = make_auditor()
    try:
        task = run_task(auditor, en_report=english_report(text, claims), en_problems={"en-point": int_problem("en-point", "x", 7, op="gt", bound=5)},
                        hi_problems={"h1.1": int_problem("h1.1", "x", 2, op="lt", bound=3)})
        assert any(f.code == "INT-CONFLICT-001" for f in task.receipts["rep_hi"].findings)
        audit = task.audit()
        assert not findings(audit, "OVS-JOINT-003") and not findings(audit, "OVS-JOINT-002")
        x = _accuse_false_conflict(auditor, task)
        assert x.outcome == outcome, (x.outcome, x.reasons)
        if outcome == "unresolved":
            assert any(FALSE_CONFLICT_GAP_RULE in r and "en-point" in r for r in x.reasons), x.reasons
    finally:
        auditor.close()


@pytest.mark.parametrize("text, local", [("Check: at x = 0, g(0) = 3 and h(3) = 1 = 0 + 1.", True), ("Suppose x = 2, then y = 7.", True),
                                         ("Let x = 3.", True), ("To verify, substitute x = 4 into the equation.", True),
                                         ("The solution is x = 5.", False), ("The check digit is 7.", False), ("Testing showed 5 errors.", False)])
def test_the_gap_reads_a_check_a_supposition_or_a_trial_and_nothing_else(text, local):
    assert bool(_LOCAL_VALUE_RE.search(text)) is local


# ============================================================================================ rule task-figures
def _report(subject: str, claim_id: str, text: str) -> SpecialistReport:
    ids = dict(request_id="req-c2b", task_id="task-c2b", subject=subject, task_type="calculation")
    return SpecialistReport(**ids, report_id="rep-c2b", agent_id="specialist", original_response=text, response_sha256=sha256_text(text),
                            created_at="2026-11-13T00:00:00Z",
                            claims=[ClaimRecord(**ids, report_id="rep-c2b", agent_id="specialist", materiality="material", claim_id=claim_id,
                                                claim_text=text, claim_role="quantitative")])


def _fact(claim_id: str, name: str, meaning: str, value: str, label: str, sort: str = "Real") -> tuple[Problem, object]:
    lit = {"op": "int" if sort == "Int" else "real", "value": value}
    p = Problem.model_validate({
        "ir_version": "1.0", "problem_id": f"p-{claim_id}", "request_id": "req-c2b", "claim_id": claim_id, "query": "entailment",
        "symbols": [{"name": name, "sort": sort, "meaning": meaning, "grounding": {"kind": "arithmetic_fact", "source_refs": [], "certainty": "established"}}],
        "premises": [{"id": "fact", "expr": {"op": "eq", "left": {"op": "var", "name": name}, "right": lit}, "label": label,
                      "grounding": {"kind": "arithmetic_fact", "source_refs": [], "certainty": "established"}}],
        "conclusion": {"id": "C", "expr": {"op": "eq", "left": {"op": "var", "name": name}, "right": lit}, "label": "the claim"}})
    return p, p.premises[0]


#: The recorded c1 requests (data): bi-t14 states "both species were present in 20 quadrats", ph-p8b "combined spring constant is 50 N m⁻¹".
BI_T14_REQUEST = ("A student placed 60 quadrats, each 1 m², at random in a meadow of area 1.2 ha. Species A, a meadow plant, was present in 32 quadrats "
                  "and species B, another meadow plant, in 27; both species were present in 20 quadrats. In total, 189 plants of species A were "
                  "counted in the 60 quadrats.")
PH_P8B_REQUEST = ("A trolley of mass 0.50 kg on a horizontal, frictionless track is attached between two springs whose combined spring constant is "
                  "50 N m⁻¹. The trolley is pulled 4.0 cm from its equilibrium position and released at t = 0.")


@pytest.mark.parametrize("subject, prob_args, request_text, kind", [
    ("Biology", ("s4.7", "obs_both", "observed quadrats with both species", "20", "20 quadrats had both species (task figure)", "Int"), BI_T14_REQUEST, UNDECIDED),
    ("Physics", ("s1.1", "k_sys", "combined spring constant of the system, N/m", "50", "the question gives the combined spring constant as 50 N/m"),
     PH_P8B_REQUEST, UNDECIDED),
    # controls: a figure the request states for another quantity, and one it states nowhere, stay the writer's own
    ("Biology", ("s4.7", "obs_both", "observed quadrats with both species", "189", "189 quadrats had both species (task figure)", "Int"), BI_T14_REQUEST, OWN_KIND),
    ("Physics", ("s1.1", "k_sys", "combined spring constant of the system, N/m", "60", "the question gives the combined spring constant as 60 N/m"),
     PH_P8B_REQUEST, OWN_KIND),
    # decision 55's pinned case: an arithmetic fact whose label does not present its figure as the task's stays the writer's own however
    # the request states it ("the claim restated" under the kind is the claim assumed)
    ("Biology", ("s4.7", "obs_both", "observed quadrats with both species", "20", "the claim restated", "Int"), BI_T14_REQUEST, OWN_KIND),
], ids=["bi-t14 s4.7", "ph-p8b s1.1", "control: another quantity's figure", "control: an invented figure", "control: no task named"])
def test_an_arithmetic_fact_the_request_states_is_undecided_data_and_an_invented_one_stays_the_writers_own(subject, prob_args, request_text, kind):
    """The merged c1 record (critical): the receipt displayed bi-t14 s4.7 and ph-p8b s1.1 ENTAILED while the transfer audit named them
    OVS-TRN-006, an arithmetic fact with no located excerpt being the writer's own "however the task states its figures". Rule
    task-figures reads it as a task setting's figures are read (rule same-quantity: stated in the request for the quantity the premise
    names, as a statement): undecided data, an OVS-TRN-011 warning at most, so the audit agrees with the receipt. A figure the request
    states for another quantity, or nowhere, stays the claim assumed (OVS-TRN-006 where it restates the conclusion)."""
    prob, premise = _fact(*prob_args)
    rep = _report(subject, prob.claim_id, "x")
    st = premise_standing(premise, rep, [request_text], {s.name: s.sort for s in prob.symbols}, [], prob)
    assert st.kind == kind, st.reason
    if kind == UNDECIDED:
        assert TASK_FIGURES_RULE in st.reason and "its arithmetic_fact grounding" in st.reason


# ============================================================================================ rule stated-squares
def _ph_t13() -> list[str]:
    s = R7["specialists"]["ph-t13"]
    return [s["response_text"], s["question"]] + [t["text"] for t in s.get("supplied_texts") or []]


def test_a_quotient_over_a_square_needs_the_root_of_its_figure_written():
    """The contained run's gate stem_fault_classes_named (12 Nov): the physics-translation probe plants 0.60 for ph-t13's 0.50 Ω and
    expects OVS-TRN-005; the first pass's reading "a stated figure over the square of a stated whole number" traced 0.60 as 2.4/2²
    (the answer writes a square in a unit). Only a figure written under a root sign is read so ((√2210/11)² = 2210/121)."""
    texts = _ph_t13()
    known = set().union(*(text_numbers(t) for t in texts))
    consts = _DerivedConstants(known, texts)
    assert Fraction(12, 5) in known and not consts.holds(Fraction(3, 5))
    root = ["$d = \\frac{\\sqrt{2210}}{11} = 4.2737$"]
    assert _DerivedConstants(set().union(*(text_numbers(t) for t in root)), root).holds(Fraction(2210, 121))
    plain = ["The area is 2210 hectares, the count 11, and v² is stated."]
    assert not _DerivedConstants(set().union(*(text_numbers(t) for t in plain)), plain).holds(Fraction(2210, 121))
    unit_only = ["The acceleration is 2.4 m s⁻² over 2 s."]
    c = _DerivedConstants(set().union(*(text_numbers(t) for t in unit_only)), unit_only)
    assert not c.square_gate and not c.holds(Fraction(576, 100))  # a negative unit exponent opens no square reading


# ============================================================================================ the twofold review (push check of c4f276c)
def test_a_merged_review_no_verdict_was_assessed_on_is_noted_not_reviewed(pack):
    """c4f276c push check: when no verdict is assessed on the merged review its note said "0 verdict(s) assessed ... carried faults
    confirmed: none", which reads as a clean merged review. It is now NOT reviewed, with what each planned instance did (decision 133's
    wording for a source part); the source parts' notes are unchanged."""
    from .test_hook_review import verdict
    from .test_r8_architecture_review import PLAIN_HI, S1, S2, S3, _combined, _review

    def reply(d: dict):
        if (d.get("review") or {}).get("role") == "merged":
            raise RuntimeError("provider down")
        return verdict(d)
    hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
    try:
        _pr, rv = _review(hub, plan, ch, pack, reply)
        notes = rv.audit.coverage.notes
        [merged] = [n for n in notes if n.startswith("merged review of the combinator's output")]
        assert "NOT reviewed: no verdict was assessed on it" in merged and ": provider_error" in merged, merged
        assert "carried faults confirmed" not in merged
        assert all("NOT reviewed" not in n for n in notes if n.startswith("source "))
    finally:
        hub.close()
    hub, plan, ch = _combined(PLAIN_HI, [S1, S2, S3])
    try:
        _pr, rv = _review(hub, plan, ch, pack, lambda d: verdict(d))
        [merged] = [n for n in rv.audit.coverage.notes if n.startswith("merged review of the combinator's output")]
        assert "NOT reviewed" not in merged and "carried faults confirmed: none" in merged  # the control keeps its note
    finally:
        hub.close()


def test_a_context_records_the_mode_it_was_built_in():
    """c4f276c push check (defense in depth): ``TemporaryContext.build`` defaults to an informed context and the intake did not read the
    mode. The context now records its mode, and the intake refuses a blind dossier any context built for an informed review or holding
    a fault of a hidden kind (its own test: ``test_twofold.test_the_context_is_scoped_to_its_channel_task_and_request_and_refused_anywhere_else``)."""
    from .test_r8_architecture_review import _layout
    assert TemporaryContext.build(_layout(), {}).mode == "informed" and TemporaryContext.build(_layout(), {}, mode="blind").mode == "blind"


def test_the_kinds_a_blind_context_keeps_are_the_ones_its_dossier_lets_a_reviewer_decide():
    """c4f276c push check (a judgement): BLIND_HIDDEN_KINDS omits receipt_status_wrong and finding_missing. Kept visible by decision
    132's criterion: each is decided by re-deriving the receipt from content a blind dossier SHOWS (RCPT-002 reads the status from the
    receipt's own findings; RCPT-004 and RCPT-008 re-run the channel's rules on the journaled request and report; SYN-002 and DIV-001
    the ledger and integrity rules on the journaled reports), never by a signature, replay or custody comparison, and a finding the
    receipt missed names a fault of a source claim the synthesis may carry, which the merged review exists to see."""
    for kind in ("receipt_status_wrong", "finding_missing"):
        assert kind not in BLIND_HIDDEN_KINDS
        assert not any(c.startswith(("OVS-RES-", "OVS-CUST-")) for c in KIND_CHECKS[kind]), KIND_CHECKS[kind]


# ============================================================================================ the new readers stay linear
HOSTILE = {
    "blanks": " " * 20_000 + "x", "tabs": "\t" * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x",
    "closing marks": "]" * 20_000 + "x", "mark labels": "(A1) " * 4_000 + "x", "parentheses": "(" * 20_000 + "x", "brackets": "[" * 20_000 + "x",
    "fence openers": "```" * 7_000 + "x", "number words": " and ".join(["twenty"] * 4_000) + " x", "= links": "x = " * 5_000 + "y",
    "list markers": "- " * 10_000 + "x", "note-word leads": "Final note: " * 1_700 + "x", "note words": "a b c note " * 2_000 + "x",
    "incomplete phrases": "not " * 5_000 + "x", "partial runs": "partial \t " * 2_000 + "x", "roots": "√ " * 10_000 + "x",
    "sqrt runs": "\\sqrt{" * 3_000 + "x", "squares": "s⁻² " * 5_000 + "x", "suppositions": "let x = " * 2_500 + "y", "checks": "check " * 4_000 + ":",
}


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_second_pass_readers_are_linear_on_hostile_inputs(name):
    """Every reader this pass added or changed, on about 20,000 characters of each standard hostile input: bounded patterns and one
    pass each (a wide margin: 3 s for all of them together)."""
    text = HOSTILE[name]

    def run():
        self_reporting_note_blocks(text)
        declared_incomplete(text)
        _LOCAL_VALUE_RE.search(text)
        _DerivedConstants(text_numbers(text[:4000] + " "), [text])
        return True
    timing = measure(run, bound=3.0, repeat=1, label=name)
    assert timing.holds, timing



# ============================================================================================ receipt and audit agree (the c1 record)
def test_the_receipt_and_the_audit_agree_on_the_c1_step_checks_under_the_task_record(tmp_path, monkeypatch):
    """The merged c1 record (critical), end to end as the arena harness runs it (its verifier passes the task record on, as
    production's does): bi-t14 s1.2 and s4.7 and ph-p8b s1.1, each served its recorded translation. For each claim either the receipt
    withholds it (not ENTAILED: the translator's E112) or the delivery pass's task audit names no OVS-TRN-006 on it: never a claim the
    receipt displays ENTAILED that the audit names circular. The recorded material is the round's (``data/c1_core_material.json``)."""
    import sys as _sys
    from .translator_checkout import require_translator_root
    c1 = json.loads((__import__("pathlib").Path(__file__).parent / "data" / "c1_core_material.json").read_text())
    arena = str(require_translator_root() / "scripts" / "arena")
    _sys.path.insert(0, arena)
    try:
        import run_arena as RA
    finally:
        _sys.path.remove(arena)
    rd = tmp_path / "c1-mini"
    (rd / "specialists").mkdir(parents=True)
    (rd / "translations").mkdir()
    for task in ("bi-t14", "ph-p8b"):
        (rd / "specialists" / f"{task}.json").write_text(json.dumps(c1["specialists"][task]))
        tr = c1["translations"][task]
        claims = tr["claims"] if isinstance(tr, dict) and "claims" in tr else tr
        (rd / "translations" / f"{task}.json").write_text(json.dumps({"report_id": f"rep-{task}-0", "claims": claims}))
    made: list = []
    real = RA._delivery_auditor

    def spy():
        a = real()
        made.append(a)
        return a
    monkeypatch.setattr(RA, "_delivery_auditor", spy)
    out = RA.run_round(rd)
    shown = {(r["task_id"], o["claim_id"]): o.get("display_status") for r in out["records"] if r["variant"] == "genuine" for o in r["outcomes"]}
    wanted = [("bi-t14", "s1.2"), ("bi-t14", "s4.7"), ("ph-p8b", "s1.1")]
    assert all(k in shown for k in wanted), sorted(shown)
    assert made, "the delivery pass ran with the transfer auditor attached"
    circular = set()
    for a in made:
        for uid in a.channel_uids():
            for au in a.audits(uid)[-1:]:
                circular |= {c for f in au.report.findings if f.code == "OVS-TRN-006" and f.severity == "error" for c in f.claim_ids}
    for task, cid in wanted:
        assert shown[(task, cid)] != "ENTAILED" or cid not in circular, (task, cid, shown[(task, cid)])
    # the two step checks whose restating premises name the task as their source and state the request's figures are never named
    # circular by the audit (rule task-figures: OVS-TRN-011 at most), whatever the translator displays (ENTAILED on the tree of 13 Nov)
    assert not ({"s4.7", "s1.1"} & circular)
