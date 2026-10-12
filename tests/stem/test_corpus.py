"""Stage ``corpus-eval`` (docs/STEM_DESIGN.md, section 16): every item of the labelled STEM corpus
(``tests/stem/data/stem_corpus.json``) through ``RouterHub``.

Acceptance criteria, each asserted below:

* **No error of any kind on correct work, and verbatim delivery.** A correct answer or a
  rounding-only control receives no error-severity finding, no INT-SUBJ-004, no failed formal
  check and no fault-naming warning (ST-DIM-001/-002, ST-UNDEF-001, ST-ALG-001) unless its gold
  names that warning; the delivered report's ``original_response`` is the answer, byte for
  byte, and every claim text is a substring of it.
* **Recall.** Each injected fault is named by one of its expected codes on a claim that covers
  the faulty step; for an engine code (INT-SUBJ-001/-004) the finding's signed result belongs to a
  check of an expected kind (``stem-<kind>-N``).
* **Precision.** In a mutant, every error-level finding (and every INT-SUBJ-004) names a claim
  that covers the faulty step or a step that carries the fault forward (gold ``affected_steps``);
  none lands on correct work alone.
* **Out of scope is named.** Each relation the gold lists as undecided is named on a covering
  claim with one of its codes and its reason.
* **Undecided rate.** Of the relations the front end recognises in correct answers (planned
  checks and undecided relations), fewer than 10 % are undecided, overall and per subject.
* **The 13 silent passes** observed before STEM support are each caught or named.
* **Bounded.** Nothing raises; each item's ``receive`` stays under the design's 2.5 s bound
  (section 13: a 128-check answer below 2.5 s).

Run as a script to print the measured summary (``docs/STEM_RESULTS.md``)::

    python tests/stem/test_corpus.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

import pytest

from epinoic_logic.adapters.stem_specialist.parser import stem_profile_key
from epinoic_logic.branches import RouterHub
from epinoic_logic.channel import TransmissionStatus
from epinoic_logic.engine import SolverConfig
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.stem import build_document
from epinoic_logic.translate.contracts import SuppliedText

DATA = Path(__file__).resolve().parent / "data"
CORPUS = json.loads((DATA / "stem_corpus.json").read_text(encoding="utf-8"))
ITEMS = CORPUS["items"]
BY_ID = {it["id"]: it for it in ITEMS}
KEY = b"stem-corpus-eval-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=4000, memory_max_mb=None)
#: section 13: a 128-check answer through the hub below 2.5 s; every corpus item is far smaller
TIME_BOUND_S = 2.5
#: warnings that name a fault in the work; on correct work they are false findings unless the gold expects them
FAULT_WARNINGS = frozenset({"INT-SUBJ-004", "ST-DIM-001", "ST-DIM-002", "ST-UNDEF-001", "ST-ALG-001"})
ENGINE_CODES = frozenset({"INT-SUBJ-001", "INT-SUBJ-004"})
BRANCH_MODES = {"sciences": "sciences", "mathematics": "mathematics", "computer_science": "computer_science"}
AGENT = "stem-specialist"


def send(item: dict):
    """One item through the hub: (hub, receipt, delivered report or None, seconds in receive)."""
    hub = RouterHub(signing_key=KEY, config=CFG)
    hub.open_task(WorkPlan(plan_id="p", request_id="q", task_id="t", subject=item["subject"], task_type=item.get("task_type") or "short_answer",
                           selected_agent_ids=[AGENT]))
    m, _req, rq = hub.dispatch("t", AGENT, item["question"], [SuppliedText(**s) for s in item.get("supplied_texts", [])])
    assert m is not None and rq.status is TransmissionStatus.ACCEPTED, [f.code for f in rq.findings]
    t0 = time.perf_counter()
    _reply, rc = hub.receive("t", m.message_id, item["response_text"], agent_id=AGENT, report_id="r1")
    elapsed = time.perf_counter() - t0
    return hub, rc, hub.channels["t"].transmitted_reports.get("r1"), elapsed


def claim_spans(report, text: str) -> dict[str, tuple[int, int]]:
    """Each claim's offsets in the answer (claims are offset substrings, in document order)."""
    out, cursor = {}, 0
    for c in report.claims:
        k = text.find(c.claim_text, cursor)
        if k < 0:
            k = text.find(c.claim_text)
        if k >= 0:
            out[c.claim_id] = (k, k + len(c.claim_text))
            cursor = k
    return out


def covering(spans: dict[str, tuple[int, int]], text: str, step: str) -> set[str]:
    a = text.find(step)
    if a < 0:
        return set()
    b = a + len(step)
    return {cid for cid, (x, y) in spans.items() if x < b and a < y}


def _relations(item: dict, branch: str):
    if branch not in BRANCH_MODES:
        return []
    doc = build_document(item["response_text"], item["question"], stem_profile_key(item["subject"], BRANCH_MODES[branch]))
    return [r for r in doc.relations if r.outcome in ("check", "undecided")]


@lru_cache(maxsize=None)
def evaluate(item_id: str) -> dict:
    """Send one item and judge its receipt against the gold. Returns the measurements and every problem found."""
    item = BY_ID[item_id]
    text = item["response_text"]
    gold = item["gold"]
    problems: list[str] = []
    try:
        hub, rc, report, elapsed = send(item)
    except Exception as exc:  # nothing may raise out of the hub
        return {"problems": [f"raised {type(exc).__name__}: {exc}"], "elapsed": 0.0, "relations": 0, "undecided": 0, "branch": None, "named": []}
    if rc.status is TransmissionStatus.REJECTED or report is None:
        problems.append(f"not delivered: {rc.status.value} {[f.code for f in rc.findings]}")
        return {"problems": problems, "elapsed": elapsed, "relations": 0, "undecided": 0, "branch": rc.branch, "named": []}
    if report.original_response != text:
        problems.append("original_response is not the answer verbatim")
    for c in report.claims:
        if c.claim_text not in text:
            problems.append(f"claim {c.claim_id} is not a substring of the answer")
    if elapsed > TIME_BOUND_S:
        problems.append(f"receive took {elapsed:.2f} s (bound {TIME_BOUND_S} s)")
    spans = claim_spans(report, text)
    findings = list(rc.findings) + list(rc.structural_findings)
    by_result = {fc.formal_result_id: fc for fc in rc.formal_checks if fc.formal_result_id}

    def kind_of(f) -> str:
        fc = by_result.get(getattr(f, "formal_result_id", None))
        return fc.constraint_id.split("-")[1] if fc is not None and fc.constraint_id.startswith("stem-") else ""

    expected_undecided = {c for u in gold.get("undecided", []) for c in u["expected_codes"]}
    for u in gold.get("undecided", []):
        cover = covering(spans, text, u["step"])
        hit = [f for f in findings if f.code in u["expected_codes"] and set(f.claim_ids) & cover and u["reason"].lower() in f.message.lower()]
        if not hit:
            problems.append(f"undecided relation not named with its reason {u['reason']!r}: {u['step'][:80]!r}")
    named = []
    if item["role"] in ("correct", "control"):
        for f in findings:
            if f.severity == "error":
                problems.append(f"error on correct work: {f.code} {f.claim_ids} {f.message[:200]}")
            elif f.code in FAULT_WARNINGS and f.code not in expected_undecided:
                problems.append(f"fault warning on correct work: {f.code} {f.claim_ids} {f.message[:200]}")
        for fc in rc.formal_checks:
            if fc.satisfied is False:
                problems.append(f"failed check on correct work: {fc.constraint_id} {fc.detail[:200]}")
    else:
        fault_cover: set[str] = set()
        for fault in gold["faults"]:
            cover = covering(spans, text, fault["step"])
            fault_cover |= cover
            hits = []
            for f in findings:
                if f.code not in fault["expected_codes"] or not (set(f.claim_ids) & cover):
                    continue
                if f.code in ENGINE_CODES and fault.get("check_kinds") and kind_of(f) not in fault["check_kinds"]:
                    continue
                hits.append(f)
            if not hits:
                present = sorted({f.code for f in findings if f.severity != "info"})
                problems.append(f"fault {fault['class']} not named by {fault['expected_codes']} (kinds {fault.get('check_kinds')}) on {sorted(cover)} "
                                f"for {fault['step'][:80]!r}; present: {present}")
            named.extend((fault["class"], f.code, kind_of(f)) for f in hits)
        allowed = set(fault_cover)
        for step in gold.get("affected_steps", []):
            allowed |= covering(spans, text, step)
        for f in rc.findings:
            if (f.severity == "error" or f.code == "INT-SUBJ-004") and not (set(f.claim_ids) & allowed):
                problems.append(f"false finding in a mutant: {f.code} {f.claim_ids} {f.message[:200]}")
    rels = _relations(item, rc.branch or "")
    undecided_checks = {fc.constraint_id for fc in rc.formal_checks if fc.satisfied is None}
    undecided = sum(1 for r in rels if r.outcome == "undecided" or r.check_id in undecided_checks)
    return {"problems": problems, "elapsed": elapsed, "relations": len(rels), "undecided": undecided, "branch": rc.branch, "named": named}


def _ids(role: str) -> list[str]:
    return [it["id"] for it in ITEMS if it["role"] == role]


# --------------------------------------------------------------------------------------------- the corpus
def test_the_corpus_meets_the_size_and_coverage_of_section_16():
    roles = Counter(it["role"] for it in ITEMS)
    assert roles["correct"] >= 120 and roles["mutant"] >= 240 and roles["control"] >= 1, roles
    profiles = {stem_profile_key(it["subject"], "sciences") for it in ITEMS if it["role"] == "correct"}
    for need in ("physics", "chemistry", "biology", "ess", "sports_science", "design_technology", "mathematics_aa", "mathematics_ai", "computer_science"):
        assert need in profiles, need
    classes = Counter(f["class"] for it in ITEMS for f in it["gold"]["faults"])
    for cls in CORPUS["catalogue"]:
        assert classes[cls] >= 3, (cls, classes[cls])
    notations = Counter(n for it in ITEMS if it["role"] == "correct" for n in it["notation"])
    for need in ("latex_inline", "latex_display", "unicode", "ascii"):
        assert notations[need] >= 10, (need, notations[need])
    assert sum(1 for it in ITEMS if it["gold"].get("undecided")) >= 5


def test_every_step_label_is_a_unique_substring_and_every_fault_label_carries_a_proof():
    for it in ITEMS:
        text = it["response_text"]
        g = it["gold"]
        for f in g["faults"]:
            assert text.count(f["step"]) == 1, (it["id"], f["step"])
            assert f["expected_codes"] and f["severity"] in ("error", "warning")
            if it["source"] == "built":
                assert f["proof"].get("fails") is True or f["proof"].get("holds") is False, (it["id"], f["proof"])
                assert f["class"] in CORPUS["catalogue"]
        for s in g["correct_steps"] + g.get("affected_steps", []):
            assert s in text, (it["id"], s)
        assert (it["role"] == "mutant") == bool(g["faults"]), it["id"]


def test_the_fixture_items_are_copied_verbatim():
    for it in ITEMS:
        if not it["source"].startswith("tests/fixtures/"):
            continue
        src = json.loads((DATA.parents[2] / it["source"]).read_text(encoding="utf-8"))
        assert (src["response_text"], src["question"], src["subject"]) == (it["response_text"], it["question"], it["subject"])
        assert [f["step"] for f in src["gold"]["faults"]] == [f["step"] for f in it["gold"]["faults"]]
        assert src["gold"]["correct_steps"] == it["gold"]["correct_steps"]


def test_the_committed_corpus_is_what_the_builder_writes(tmp_path, monkeypatch):
    sys.path.insert(0, str(DATA))
    try:
        import build_stem_corpus as builder
        monkeypatch.setattr(builder, "OUT", tmp_path / "corpus.json")
        builder.main()
        assert json.loads((tmp_path / "corpus.json").read_text(encoding="utf-8")) == CORPUS
    finally:
        sys.path.remove(str(DATA))


@pytest.mark.parametrize("item_id", _ids("correct") + _ids("control"))
def test_correct_work_gets_no_error_and_is_delivered_verbatim(item_id):
    res = evaluate(item_id)
    assert not res["problems"], res["problems"]


@pytest.mark.parametrize("item_id", _ids("mutant"))
def test_each_injected_fault_is_named_on_its_claim_and_nothing_else_is_flagged(item_id):
    res = evaluate(item_id)
    assert not res["problems"], res["problems"]


def test_the_undecided_rate_on_correct_answers_is_under_ten_per_cent():
    """Over every correct answer the rate is under 10 %. Per subject it is under 10 % over the answers written as they come
    (``undecided_by_subject_typical``): the handful of answers written to exercise notation outside the encodings (their
    gold lists the undecided relations they must name: calculus, limits, complex numbers, asymptotic notation, fractional
    powers) are left out of that per-subject figure, and both figures are reported (docs/STEM_RESULTS.md)."""
    s = summary()
    rows = s["undecided_by_subject"]
    total_rel = sum(r["relations"] for r in rows.values())
    total_und = sum(r["undecided"] for r in rows.values())
    assert total_rel >= 400 and total_und / total_rel < 0.10, (total_und, total_rel)
    for subject, r in s["undecided_by_subject_typical"].items():
        assert r["relations"] == 0 or r["undecided"] / r["relations"] < 0.10, (subject, r)


SILENT_PASSES = ("P1-observed", "P3-latex-display-err", "P5-sci-notation-err", "P7-momentum-err", "P8-unit-conversion-err", "P10-percent-efficiency-err",
                 "C1-moles-err", "C2-concentration-yield-err", "M2-series-err", "M3-calculus-err", "M4-ai-percent-err", "B1-magnification-err", "CS1-binary-err")


def test_all_thirteen_silent_passes_observed_before_stem_support_are_caught_or_named():
    for pid in SILENT_PASSES:
        item = BY_ID[f"probe-{pid}"]
        assert item["role"] == "mutant"
        res = evaluate(item["id"])
        assert not res["problems"], (pid, res["problems"])
        assert res["named"], pid


# ------------------------------------------------------------------------------------------- the summary
@lru_cache(maxsize=None)
def summary() -> dict:
    by_subject: dict[str, dict[str, int]] = defaultdict(lambda: {"items": 0, "relations": 0, "undecided": 0})
    typical: dict[str, dict[str, int]] = defaultdict(lambda: {"items": 0, "relations": 0, "undecided": 0})
    recall = Counter()
    recall_total = Counter()
    problems = {}
    times = []
    for it in ITEMS:
        res = evaluate(it["id"])
        times.append(res["elapsed"])
        if res["problems"]:
            problems[it["id"]] = res["problems"]
        if it["role"] == "correct":
            for table in (by_subject, typical) if not it["gold"].get("undecided") else (by_subject,):
                row = table[it["subject"]]
                row["items"] += 1
                row["relations"] += res["relations"]
                row["undecided"] += res["undecided"]
        for f in it["gold"]["faults"]:
            recall_total[f["class"]] += 1
            if not any(p.startswith(f"fault {f['class']} not named") for p in res["problems"]):
                recall[f["class"]] += 1
    times.sort()
    return {"undecided_by_subject": dict(by_subject), "undecided_by_subject_typical": dict(typical), "recall": dict(recall), "recall_total": dict(recall_total), "problems": problems,
            "p50_s": times[len(times) // 2], "p95_s": times[int(len(times) * 0.95)], "max_s": times[-1], "items": len(ITEMS),
            "roles": dict(Counter(it["role"] for it in ITEMS))}


if __name__ == "__main__":
    s = summary()
    print(json.dumps({k: v for k, v in s.items() if k != "problems"}, indent=1))
    print(f"items with problems: {len(s['problems'])}")
    for k, v in list(s["problems"].items())[:400]:
        print(k)
        for p in v:
            print("   ", p)
