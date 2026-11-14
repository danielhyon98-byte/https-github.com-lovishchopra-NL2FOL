"""The round-9 clearance, second fix pass (c2b): the items the parallel fixers handed over across owners, fixed at their cause
and pinned here (the translator's side of each item is pinned in the translator's own suite).

* Rule ``response-limit`` (queued q211b, critical; defence in depth): the channel refuses a response text over the contract's
  limit before any reader runs on it, and the auditor's answer-level readers refuse such a text unread too: the re-parse of a
  delivered response (OVS-CUST-006, by its length and the limit), the note and lead readers of ``meta_notes`` and the parser
  readings of ``non_material``. A text over the limit is refused, never cut.
* The class sweep of that input stall: every public text entry point of ``meta_notes``, ``non_material`` and
  ``checks.fidelity`` stays linear on the standard hostile inputs (one test per module).
"""
from __future__ import annotations

import dataclasses
import socket

import pytest

import epinoic_logic.api.adapters as api_adapters
from epinoic_logic.api.branches import default_registry
from epinoic_logic.api.translate import SpecialistReport, SuppliedText
from epinoic_overseer import meta_notes as M
from epinoic_overseer import non_material as N
from epinoic_overseer.checks import CheckContext
from epinoic_overseer.checks import fidelity as F

from .conftest import DOC, HI_TEXT, run_task
from .timing import measure


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def refuse(*args, **kwargs):  # pragma: no cover - only hit if a test leaks a connection
        raise AssertionError("network access attempted in a unit test")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# ============================================================================================ rule response-limit
#: The worst case the finding names: an answer far over the contract's response limit (the English segmenter reads about 13
#: microseconds a character, so a reader that ran on this text would spend about half a minute on each call).
OVER = ("The poem turns on its image. Note: check the quotation. (A1) [2] = - " * 40_000)[:2_000_000]
ENGLISH = "English A: Language and Literature"
KW = dict(request_id="req-x", task_id="task-x", report_id="rep-x", subject=ENGLISH, task_type="analytical_paragraph", supplied_texts=[DOC],
          course_level="SL", agent_version=None, agent_id="english-specialist")


class _CountingParser:
    """A branch parser that records every text it is asked to parse and delegates to the real one."""

    def __init__(self, real) -> None:
        self.real = real
        self.seen: list[int] = []
        self.accepts_request_text = getattr(real, "accepts_request_text", False)

    def parse_response(self, text, **kw):
        self.seen.append(len(text))
        return self.real.parse_response(text, **kw)


def test_the_limit_is_the_contracts():
    """The bound is read from the contract (``SpecialistReport.original_response``), as the channel reads it: never a copy."""
    [limit] = [m.max_length for m in SpecialistReport.model_fields["original_response"].metadata if getattr(m, "max_length", None) is not None]
    assert M.RESPONSE_MAX_CHARS == limit == 400_000
    assert not M.over_response_limit("x" * limit) and M.over_response_limit("x" * (limit + 1)) and not M.over_response_limit(None)
    M.require_response_limit("x" * limit)
    with pytest.raises(M.OversizeAnswer, match=r"has 400001 characters, over the contract's limit of 400000; it was not read \(rule response-limit\)"):
        M.require_response_limit("x" * (limit + 1))


def test_an_answer_over_the_contract_limit_is_refused_unread_by_every_answer_reader(monkeypatch):
    """Each answer-level reader on a text five times the limit: the fail-closed value (no note freed, the answer named as a whole,
    or OversizeAnswer for the caller to refuse it), the segmenter and the parser never run, and all of them together well under a
    second (they ran for about half a minute EACH before the rule)."""
    segmented: list[int] = []
    real_segment = api_adapters.segment

    def watched(text, *a, **kw):
        segmented.append(len(text))
        return real_segment(text, *a, **kw)
    monkeypatch.setattr(api_adapters, "segment", watched)
    parser = _CountingParser(default_registry().for_subject(ENGLISH)[0].parser())

    def run():
        out = {"notes": M.note_paragraphs(OVER), "self-reporting": M.self_reporting_note_blocks(OVER),
               "lead blocks": [b.detail for b in M.unread_lead_blocks(OVER)], "blocks": [b.detail for b in N.unread_non_material_blocks(OVER, [])]}
        for name, call in (("english units", lambda: N.english_units(OVER)), ("parser units", lambda: N.parser_units(OVER, parser, **KW)),
                           ("parser claims", lambda: N.parser_claims(OVER, parser, **KW))):
            with pytest.raises(M.OversizeAnswer) as exc:
                call()
            out[name] = str(exc.value)
        return out
    timing = measure(run, bound=1.0, repeat=3, label="over the response limit")
    assert timing.holds, timing
    out = timing.results[0]
    assert out["notes"] == frozenset()
    assert out["self-reporting"] == ["the answer as a whole (its text is over the contract's limit of 400000 characters: rule response-limit)"]
    assert out["lead blocks"] == out["blocks"] == ["the answer is over the contract's limit of 400000 characters, unread (rule response-limit)"]
    for name in ("english units", "parser units", "parser claims"):
        assert "has 2000000 characters, over the contract's limit of 400000" in out[name] and "poem" not in out[name]
    assert segmented == [] and parser.seen == []


def test_an_answer_within_the_limit_is_read_as_before(monkeypatch):
    """Control: an answer within the limit takes the existing path (the segmenter and the parser run on it, once per reader)."""
    text = "The poem turns on its image.\n\nNote: the figures are unverified."
    parser = _CountingParser(default_registry().for_subject(ENGLISH)[0].parser())
    assert [u.text for u in N.english_units(text)][:1] == ["The poem turns on its image."]
    assert N.parser_claims(text, parser, **KW) and N.parser_units(text, parser, **KW)
    assert parser.seen == [len(text), len(text)]
    assert M.note_paragraphs(text) == frozenset({2})


class _Registry:
    """The auditor's registry for one branch, with a parser that records what it is given."""

    def __init__(self, parser) -> None:
        self.parser_obj = parser

    def for_subject(self, subject):
        real = default_registry().for_subject(subject)[0]
        parser = self.parser_obj
        return (dataclasses.replace(real, parser_factory=lambda: parser), None) if dataclasses.is_dataclass(real) else (real, None)


def _history_transfer(auditor):
    task = run_task(auditor, synthesis=False)
    view = auditor.view(task.uid)
    [t] = [x for x in view.transfers if x.kind == "response_text" and x.delivered]
    return view, t


def test_the_re_parse_of_a_delivered_response_over_the_limit_is_named_unread(auditor):
    """A delivered response_text whose journaled raw text is over the contract's limit (the channel refuses such a text, so only a
    journal that does not hold what the channel received can show one) is named OVS-CUST-006 by its length and the limit, and the
    branch parser never runs on it; the same transfer with its own raw text is re-parsed as before and names nothing."""
    view, t = _history_transfer(auditor)
    assert t.raw_text == HI_TEXT
    parser = _CountingParser(default_registry().for_subject("History")[0].parser())
    ctx = CheckContext(view=view, keyring=auditor.keyring, store=auditor.store, registry=_Registry(parser))
    F.check_reparse(ctx, t)  # control: the journaled text, re-parsed once, gives the delivered report
    assert parser.seen == [len(HI_TEXT)] and not [f for _s, f in ctx.findings if f.code == "OVS-CUST-006"]
    forged = dataclasses.replace(t, raw_text=OVER)
    ctx2 = CheckContext(view=view, keyring=auditor.keyring, store=auditor.store, registry=_Registry(parser))
    timing = measure(lambda: F.check_reparse(ctx2, forged), bound=1.0, repeat=1, label="re-parse over the limit")
    assert timing.holds, timing
    cust = [f for _s, f in ctx2.findings if f.code == "OVS-CUST-006"]
    assert cust and all(f.severity == "error" and f.message_ids == [t.message_id] for f in cust)
    assert "has 2000000 characters, over the contract's limit of 400000" in cust[0].message and "rule response-limit" in cust[0].message
    assert "poem" not in cust[0].message and parser.seen == [len(HI_TEXT)]


# ============================================================================================ the class sweep, one test per module
#: The standard hostile inputs: runs of about 20,000 characters, each followed by a character that defeats the match.
HOSTILE = {
    "blanks": " " * 20_000 + "x", "tabs": "\t" * 20_000 + "x", "line breaks": "\n" * 20_000 + "x", "stops": "." * 20_000 + "x",
    "closing marks": "]" * 20_000 + "x", "mark labels": "(A1) " * 4_000 + "x", "parentheses": "(" * 20_000 + "x", "brackets": "[" * 20_000 + "x",
    "fence openers": "```" * 7_000 + "x", "number words": " and ".join(["twenty"] * 1_800) + " x", "= links": "x = " * 5_000 + "y",
    "list markers": "- " * 10_000 + "x", "note leads": "Note: " * 3_400 + "x", "quotation marks": "\"" * 20_000 + "x",
    "model leads": "Model: \"" * 2_500 + "x", "blank lines": "a\n\n" * 6_700 + "x",
}


def _meta_notes_entry_points(text: str) -> None:
    M.assurance_words(text), M.hides_text(text), M.reader_text(text), M.skeleton(text), M.evaluation_words(text)
    M.note_reading(text), M.note_form(text), M.read_meta_paragraph(text), M.note_paragraphs(text), M.self_report_reading(text)
    M.self_reporting_note_blocks(text), M.lead_region_end(text), M.lead_starts(text), M.claim_alphabet_breach(text), M.glued_note_lead(text)
    M.answer_paragraphs(text), M.normalised_answer(text), M.unread_lead_blocks(text, ["Mill", "extract"]), M.source_list_grounding(text)
    M.read_source_list(text, ["mill"]), M.is_note_paragraph(text)


def _non_material_entry_points(text: str) -> None:
    parser = default_registry().for_subject(ENGLISH)[0].parser()
    units = N.english_units(text)
    N.parser_units(text, parser, **KW), N.parser_claims(text, parser, **KW), N.claim_key(text), N.layout_marks_only(text)
    N.task_wordings(text), N.read_layout(text, text[:2000]), N.covered_spans(M.normalised_answer(text), units)
    N.unread_non_material_blocks(text, units, grounding=["mill"], task_wording=text[:2000])


def _fidelity_entry_points(text: str) -> None:
    F.strip_enclosing_quotes(text), F.uncut_text(text), F.response_list_numbers(text), F.strip_mark_annotations(text)
    F.strip_edge_emphasis(text), F.figure_text(text), F.own_model_quotations(text), F.unmarked_cut_text(text[:4000], text)
    F.claim_occurs(text[:300], text, plain_response=text, raw_response=text), F.strip_trailing_punctuation(text)
    F.no_quotation_to_verify([text[:1000]], text, set()), F.located_anywhere(text[:1000], [SuppliedText(document_id="d", text=text)])
    for i in range(0, len(text), max(1, len(text) // 64)):  # a bracket read at every place of the text, as the check reads it
        F.referring_bracket(text, i)


def _fidelity_checks(auditor, text: str) -> None:
    """``check_fidelity`` and ``check_reparse`` on a delivered response whose raw text and report are the hostile text's own."""
    view, t = _history_transfer(auditor)
    parser = default_registry().for_subject("History")[0].parser()
    try:
        rep = parser.parse_response(text, request_id=t.report.request_id, task_id=t.report.task_id, report_id=t.report.report_id, subject="History",
                                    task_type="short_answer", supplied_texts=[], course_level="unknown", agent_version=None, agent_id="history-specialist")
    except Exception:  # noqa: BLE001 - a text the parser refuses is never delivered; the raw-text checks still run below
        rep = t.report
    forged = dataclasses.replace(t, raw_text=text, typed=rep)
    ctx = CheckContext(view=view, keyring=auditor.keyring, store=auditor.store)
    F.check_fidelity(ctx, forged)
    F.check_reparse(ctx, forged)


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_meta_notes_readers_are_linear_on_hostile_inputs(name):
    timing = measure(lambda: _meta_notes_entry_points(HOSTILE[name]), bound=8.0, repeat=1, label=f"meta_notes {name}")
    assert timing.holds, timing


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_non_material_readers_are_linear_on_hostile_inputs(name):
    timing = measure(lambda: _non_material_entry_points(HOSTILE[name]), bound=8.0, repeat=1, label=f"non_material {name}")
    assert timing.holds, timing


@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_fidelity_readers_are_linear_on_hostile_inputs(name, auditor):
    def run():
        _fidelity_entry_points(HOSTILE[name])
        _fidelity_checks(auditor, HOSTILE[name])
    timing = measure(run, bound=8.0, repeat=1, label=f"fidelity {name}")
    assert timing.holds, timing


# ============================================================================================ rule one-fault-once in R2
POEM = SuppliedText(document_id="doc-ozy", title="Ozymandias", author="Percy Bysshe Shelley",
                    text="I met a traveller from an antique land, Who said: Two vast and trunkless legs of stone Stand in the desert. Near them, on the "
                         "sand, Half sunk a shattered visage lies, whose frown, And wrinkled lip, and sneer of cold command, Tell that its sculptor well "
                         "those passions read. The lone and level sands stretch far away.")
PEER = SuppliedText(document_id="peer:hi-p1", title="History specialist report", author="history-specialist",
                    text="Parliament suspended habeas corpus in March 1817, after the Spa Fields riots.")
MISATTRIBUTED = 'Shelley writes that "Parliament suspended habeas corpus in March" and the ruin answers the boast of the "sneer of cold command".'


def _misattributed_transfer(auditor):
    from .conftest import make_plan, new_channel
    ch = new_channel(auditor, make_plan(allowed_document_ids=["doc-ozy", "peer:hi-p1"]))
    m, _req, _rq = ch.request("router", "english-specialist", "Analyse how Shelley presents power in the poem. Use quotations from the poem.", [POEM, PEER])
    _msg, rc = ch.respond_text(m.message_id, MISATTRIBUTED, agent_id="english-specialist", report_id="rep-mis")
    return ch, rc


def test_one_misattributed_quotation_is_one_int_subj_003_and_the_recount_agrees(auditor):
    """CORE-SRC-005 and ES-SRC-008 name one misattributed quotation: the receipt carries ONE INT-SUBJ-003 naming both codes, and
    R2's recount, which groups by the channel's own rule (``subject_error_groups``, called, not copied), names nothing."""
    ch, rc = _misattributed_transfer(auditor)
    subj = [f for f in rc.findings if f.code == "INT-SUBJ-003"]
    assert len(subj) == 1 and subj[0].message.startswith("[english] CORE-SRC-005, ES-SRC-008: ")
    rcpt = [f for f in auditor.audit(ch.uid).report.findings if f.code == "OVS-RCPT-004" and rc.message_id in f.message_ids]
    assert not rcpt, [f.message[:200] for f in rcpt]


def test_a_receipt_that_reports_the_fault_once_per_code_is_rcpt_004(auditor, monkeypatch):
    """Control: a channel that copies each code of the fault into an INT-SUBJ-003 of its own (the old form) carries no
    INT-SUBJ-003 for the fault as one: R2 names it, with both codes; never "a superset of the claims"."""
    from epinoic_logic.api.channel import TranslatorChannel
    real = TranslatorChannel._branch_checks

    def per_code(self, report, req, findings, *a, **kw):
        out = real(self, report, req, findings, *a, **kw)
        grouped = [f for f in findings if f.code == "INT-SUBJ-003" and ", " in f.message.split(":")[0]]
        for f in grouped:
            findings.remove(f)
        for sf in out[0]:
            if sf.severity == "error" and sf.code in ("CORE-SRC-005", "ES-SRC-008"):
                findings.append(f.model_copy(update={"message": f"[english] {sf.code}: {sf.message}", "claim_ids": list(sf.claim_ids)}))
        return out
    monkeypatch.setattr(TranslatorChannel, "_branch_checks", per_code)
    ch, rc = _misattributed_transfer(auditor)
    monkeypatch.undo()
    assert len([f for f in rc.findings if f.code == "INT-SUBJ-003"]) == 2
    rcpt = [f for f in auditor.audit(ch.uid).report.findings if f.code == "OVS-RCPT-004" and rc.message_id in f.message_ids]
    assert any("CORE-SRC-005, ES-SRC-008 (one fault)" in f.message for f in rcpt), [f.message[:200] for f in rcpt]


# ============================================================================================ the floor reads the previous lines (F17)
def _maa_t15():
    """The recorded maa-t15 answer parsed by its branch (through the public API) and its recorded m2.4 and m7.2 encodings
    (the translator's recorded material, read from its checkout as data)."""
    import json as _json
    from epinoic_logic.api.translate import TaskRecord
    from .translator_checkout import require_translator_root
    root = require_translator_root()
    spec = _json.loads((root / "tests" / "channel" / "data" / "c2_core_material.json").read_text())["specialists"]["maa-t15"]
    recorded = _json.loads((root / "tests" / "channel" / "data" / "c2b_core_material.json").read_text())["c2"]["translations"]["maa-t15"]
    parser = default_registry().for_subject(spec["subject"])[0].parser()
    extra = {"request_text": spec["question"]} if getattr(parser, "accepts_request_text", False) else {}
    report = parser.parse_response(spec["response_text"], request_id="req-maa", task_id="maa-t15", report_id="rep-maa-0", subject=spec["subject"],
                                   task_type=spec.get("task_type") or "short_answer", supplied_texts=[], course_level="unknown", agent_version=None,
                                   agent_id=spec["agent_id"], **extra)
    task = TaskRecord.of("maa-t15", "req-maa", spec["question"])
    return report, recorded, task


@pytest.mark.parametrize("cid", ["m2.4", "m7.2"])
def test_the_floor_reads_a_step_from_its_previous_line_as_the_pipeline_does(cid):
    """F17's remaining instances (c2 stem-integration, critical): maa-t15 m2.4 ("4k < 36" from m2.3's "36 − 4k > 0") and m7.2
    ("2x + 2 = x − 3" from m7.1) are faithful step checks. The translator's pipeline now passes the claim's previous lines to its
    step 4c (rule previous-line-step) and the auditor's floor re-runs the rule with the same lines, so the floor names nothing on
    them (no OVS-TRN-006) and the receipt's ENTAILED and the audit agree. Control: the same encodings in a report that holds no
    earlier line are named by the floor (the premise restates the conclusion, ``full``)."""
    from epinoic_logic.api.ir import Problem
    from epinoic_overseer.checks.translation import restatement, translator_semantic_floor
    report, recorded, task = _maa_t15()
    problem = Problem.model_validate({**recorded[cid]["problem"], "claim_id": cid, "request_id": "req-maa"})
    claim = next(c for c in report.claims if c.claim_id == cid)
    kind, floor = translator_semantic_floor(problem, report, task=task, claim_text=claim.claim_text)
    assert (kind, floor) == (None, ()), (cid, kind, floor)
    assert restatement(problem, report, [task.text], task=task, claim_text=claim.claim_text).translator_floor == ()
    alone = report.model_copy(update={"claims": [claim.model_copy(update={"supporting_claim_ids": []})]})
    kind2, floor2 = translator_semantic_floor(problem, alone, task=task, claim_text=claim.claim_text)
    assert kind2 == "full" and floor2, (cid, kind2, floor2)


# ============================================================================================ rule coverage-gap in the fallback
def _gap_outcome(claim, report):
    """A genuine outcome whose COUNTEREXAMPLE carries the engine's W111: x = 5 (given) and the conclusion y > 3 over a symbol no
    premise mentions (the counterexample may show a gap of the translation, not that the claim is false)."""
    from epinoic_logic.api.ir import Problem
    from .conftest import outcome_for
    p = Problem.model_validate({"problem_id": f"gap-{claim.claim_id}", "request_id": claim.request_id, "claim_id": claim.claim_id, "query": "entailment",
                                "symbols": [{"name": "x", "sort": "Int"}, {"name": "y", "sort": "Int"}],
                                "premises": [{"id": "G", "expr": {"op": "eq", "left": {"op": "var", "name": "x"}, "right": {"op": "int", "value": "5"}},
                                              "grounding": {"kind": "arithmetic_fact"}}],
                                "conclusion": {"id": "C", "expr": {"op": "gt", "left": {"op": "var", "name": "y"}, "right": {"op": "int", "value": "3"}}}})
    return outcome_for(claim, report, p)


def test_a_counterexample_with_a_coverage_warning_is_unassessed_never_a_refutation(tmp_path_factory):
    """Rule coverage-gap, read (the overseer's handoff 3, c2 results-audit bug 9): the claim whose signed COUNTEREXAMPLE carries W111
    is unassessed with the warning as its evidence, never ``refuted_by_signed_result``, and its candidate is not "refuted"; the same
    claim refuted by a counterexample with no coverage warning stays a refutation (control)."""
    from epinoic_overseer import load_pack
    from epinoic_overseer.delivery_policy import DeliveryPolicy
    from epinoic_overseer.export import export_pack
    from .delivery_support import ESSAY, ESSAY_QUESTION, Agents, FakeClock, Verifier, essay_report, refuted_outcome, silent
    from .delivery_support import run_task as run_delivery_task
    pack = load_pack(export_pack(tmp_path_factory.mktemp("export"), zip_archive=True).zip_path)
    for outcome, refuted in ((_gap_outcome, False), (refuted_outcome, True)):
        clock = FakeClock()
        policy = DeliveryPolicy(clock=clock, pack=pack, provider_factory=Agents(clock, silent))
        answers = [("writer-1", essay_report("writer-1", "rep-writer-1", 12, prefix="w1", refuted=[7]))]
        run = run_delivery_task(policy, answers, verify=Verifier(clock, outcomes={"w1.7": outcome}), question=ESSAY_QUESTION, ids=ESSAY)
        try:
            [c] = run.receipt.fallback.candidates
            [w17] = [x for x in c.claims if x.claim_id == "w1.7"]
            [o] = [o for o in run.receipts[c.message_id].outcomes if o.claim_id == "w1.7"]
            assert o.display_status.value == "COUNTEREXAMPLE" and o.verification.signature
            if refuted:
                assert w17.assessment == "inaccurate" and w17.refuted_by_signed_result and c.refuted
            else:
                assert {d.code for d in o.verification.diagnostics} >= {"W111"}
                assert w17.assessment == "unassessed" and not w17.refuted_by_signed_result and not c.refuted, (w17, c.refuted)
                assert any("does not refute it" in e and "W111" in e and "rule coverage-gap" in e for e in w17.evidence), w17.evidence
        finally:
            run.close()


def test_the_recount_reads_thousands_of_faults_in_one_pass():
    """R2's recount compared every re-derived error with every finding of the receipt (quadratic in the faults); the receipt's
    error-level structural findings and INT-SUBJ-003 messages are indexed by their claims once now, with the same verdict:
    nothing missing is nothing named, and one dropped INT-SUBJ-003 among 6,000 is named (control)."""
    import time
    from types import SimpleNamespace as NS

    from epinoic_logic.api.translate import StructuralFinding
    from epinoic_overseer.checks.formal import _structural_implied
    n = 6_000
    structural = [StructuralFinding(code="CORE-SRC-005", severity="error", message=f"the quotation 'w{k}' is not in the text", claim_ids=[f"c{k}"])
                  for k in range(n)]
    subj = [NS(code="INT-SUBJ-003", severity="error", claim_ids=[f"c{k}"], message=f"[english] CORE-SRC-005: the quotation 'w{k}' is not in the text")
            for k in range(n)]
    t = NS(kind="specialist_report", message_id="m-1")
    t0 = time.process_time()
    assert _structural_implied(NS(receipt_id="r-1", findings=subj, structural_findings=structural), t, "english", structural, {}) == []
    assert time.process_time() - t0 < 3.0
    dropped = _structural_implied(NS(receipt_id="r-1", findings=subj[1:], structural_findings=structural[:-1]), t, "english", structural, {})
    assert sorted((f.code, tuple(f.claim_ids)) for f in dropped) == [("OVS-RCPT-004", ("c0",)), ("OVS-RCPT-004", (f"c{n - 1}",))]
    assert any("implies INT-SUBJ-003 (error) for the structural finding CORE-SRC-005" in f.message for f in dropped)


# ============================================================================================ the sweep of this pass's other readers
@pytest.mark.parametrize("name", sorted(HOSTILE))
def test_the_recount_and_the_floor_are_linear_on_hostile_inputs(name):
    """The class sweep of the two auditor readers this pass changed beside the response limit: R2's recount (``checks.formal``,
    rule one-fault-once: the channel's grouping reads a quotation out of each message, the recount a lead at each message's
    start) on 200 faults whose messages are the hostile text (cut to the contract's 2,000 characters for a structural finding), and the translator floor (``checks.translation``, rule
    previous-line-step) on maa-t15's m7.2 with three previous lines and the claim's text replaced by the hostile text."""
    from types import SimpleNamespace as NS

    from epinoic_logic.api.ir import Problem
    from epinoic_logic.api.translate import StructuralFinding
    from epinoic_overseer.checks.formal import _structural_implied
    from epinoic_overseer.checks.translation import translator_semantic_floor
    text = HOSTILE[name]
    quoted = (f"the quotation '{text[:180]}' is not in the text " + text)[:2000]  # a structural finding's message, at the contract's bound
    structural = [StructuralFinding(code=("CORE-SRC-005", "ES-SRC-008")[k % 2], severity="error", message=quoted, claim_ids=[f"c{k // 2}"]) for k in range(200)]
    subj = [NS(code="INT-SUBJ-003", severity="error", claim_ids=[f"c{k}"], message=text) for k in range(100)]
    report, recorded, task = _maa_t15()
    problem = Problem.model_validate({**recorded["m7.2"]["problem"], "claim_id": "m7.2", "request_id": "req-maa"})
    at = next(i for i, c in enumerate(report.claims) if c.claim_id == "m7.2")
    hostile = report.model_copy(update={"claims": [c.model_copy(update={"claim_text": text}) if at - 3 <= i < at else c for i, c in enumerate(report.claims)]})

    def run():
        _structural_implied(NS(receipt_id="r", findings=subj, structural_findings=structural), NS(kind="specialist_report", message_id="m"), "english", structural, {})
        translator_semantic_floor(problem, hostile, task=task, claim_text=text)
    timing = measure(run, bound=8.0, repeat=1, label=f"recount and floor {name}")
    assert timing.holds, timing
