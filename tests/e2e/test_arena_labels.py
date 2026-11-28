"""The arena's meaning label (meaning-check design 2.5.7 arena row, 3.4 to 3.6; stage 2a interface (g)).

``scripts/arena/arena_labels.py`` resolves the labeller AT EACH CALL (``recorded``, ``faithful``, ``unconfigured``; the
environment variable EPINOIC_ARENA_LABELLER when none is given, else ``recorded``), reads the round's ``labels/`` (design 3.4)
and counts what the label did; ``list_labels.py`` renders every label request under a recording key; ``bind_labels.py`` binds
recorded replies to them by request key; ``measure_labels.py`` reports rates with Wilson intervals and the acceptance table
of design 3.6. Every expected value below is fixed in the test: the Wilson intervals are the memo's computed values, the round
counts were measured on copies of the recorded rounds (EPINOIC_ARENA_ROUNDS) with the harness as it was before the label was
wired (the baseline), and the faithful fake must reproduce them exactly. No provider is called; no label is recorded here.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ARENA = Path(__file__).resolve().parents[2] / "scripts" / "arena"
sys.path.insert(0, str(ARENA))
import arena_labels as AL  # noqa: E402
import bind_labels as BL  # noqa: E402
import list_labels as LL  # noqa: E402
import measure_labels as ML  # noqa: E402
import run_arena as ra  # noqa: E402

from epinoic_logic import selfcert_label  # noqa: E402
from epinoic_logic.selfcert_label.fakes import ReaderBackedLabeller, ScriptedLabeller, reader_backed_reply, reply_json  # noqa: E402
from epinoic_logic.selfcert_label.labellers import RecordedLabeller, UnconfiguredLabeller  # noqa: E402

ROUNDS = Path(os.environ["EPINOIC_ARENA_ROUNDS"]) if os.environ.get("EPINOIC_ARENA_ROUNDS") else None
KEY = "arena recording key for the tests (never a deployment secret)"
MODEL = selfcert_label.model_digest("arena-test:model")
TASK = "hi-x1"
ITEM = {
    "task_id": TASK, "subject": "History", "agent_id": "history-specialist", "task_type": "short_answer",
    "question": "In one paragraph of no more than 200 words, outline the historical context of London in 1802 for a student "
                "reading a sonnet written that year, with dated evidence labelled from memory.",
    "supplied_texts": [],
    "response_text": "London in 1802 was the largest city in Europe, with close to a million inhabitants at the census of 1801. "
                     "Coal smoke from homes and workshops hung over the city for much of the year. "
                     "Against this background, the \"smokeless air\" of the sonnet stands out as an exception to the city's ordinary condition. "
                     "The Peace of Amiens, signed in March 1802, briefly ended the war with France.",
}
#: The words of the answer a scripted label names (they must never reach a count, a summary label line or results.json's counts).
NAMED_WORDS = "Coal smoke from homes and workshops"


def _round(tmp_path: Path, name: str = "rx") -> Path:
    rd = tmp_path / name
    (rd / "specialists").mkdir(parents=True)
    (rd / "specialists" / f"{TASK}.json").write_text(json.dumps(ITEM))
    return rd


def _answers(res: dict) -> dict:
    return res["selfcert_label"]["groups"]["answers"]


# ------------------------------------------------------------------------------------------------- which labeller, at each call
def test_the_labeller_is_resolved_from_the_environment_at_each_call(monkeypatch):
    monkeypatch.delenv(AL.LABELLER_ENV, raising=False)
    assert AL.resolve().name == "recorded" and AL.resolve().source == "default"
    monkeypatch.setenv(AL.LABELLER_ENV, "unconfigured")
    first = AL.resolve()
    assert (first.name, first.source, type(first.labeller)) == ("unconfigured", "environment", UnconfiguredLabeller)
    monkeypatch.setenv(AL.LABELLER_ENV, "faithful")
    second = AL.resolve()
    assert (second.name, type(second.labeller)) == ("faithful", ReaderBackedLabeller)
    assert AL.resolve("unconfigured").name == "unconfigured"  # an argument wins over the environment
    given = ScriptedLabeller(["{}"])
    assert AL.resolve(given).labeller is given and AL.resolve(given).name == "given"


def test_an_unknown_labeller_is_refused_never_read_as_another(monkeypatch):
    monkeypatch.setenv(AL.LABELLER_ENV, "clean")
    with pytest.raises(ValueError, match="EPINOIC_ARENA_LABELLER='clean'"):
        AL.resolve()
    with pytest.raises(ValueError, match="one of recorded, faithful, unconfigured"):
        AL.resolve("none_named")


def test_run_round_reads_the_environment_at_each_call(tmp_path, monkeypatch):
    rd = _round(tmp_path)
    monkeypatch.setenv(AL.LABELLER_ENV, "unconfigured")
    res = ra.run_round(rd)
    assert res["selfcert_label"]["labeller"] == "unconfigured"
    assert (_answers(res)["withheld_unlabelled"], _answers(res)["unavailable_by_kind"]) == (1, {"not-configured": 1})
    monkeypatch.setenv(AL.LABELLER_ENV, "faithful")
    res = ra.run_round(rd)
    assert res["selfcert_label"]["labeller"] == "faithful"
    assert (_answers(res)["none_named"], _answers(res)["withheld_unlabelled"]) == (1, 0)
    summary = (rd / "summary.md").read_text()
    assert AL.FAITHFUL_NOTE in summary.splitlines()  # on a line of its own
    assert summary.splitlines()[0].startswith("# Arena rx")  # the per-round title line keeps its format


@pytest.mark.real_labeller
def test_with_no_labeller_and_no_environment_the_default_is_recorded_and_withholds(tmp_path):
    """The production default is unconfigured; the arena's default is ``recorded``: with no labels/ every answer the reader
    passes is withheld unlabelled (not-recorded), counted apart, never treated as clean."""
    assert AL.LABELLER_ENV not in os.environ
    rd = _round(tmp_path)
    res = ra.run_round(rd)
    a = _answers(res)
    assert res["selfcert_label"]["labeller"] == "recorded"
    assert (a["records"], a["withheld_unlabelled"], a["unavailable_by_kind"], a["none_named"], a["named"]) == (1, 1, {"not-recorded": 1}, 0, 0)
    assert res["selfcert_label"]["labels"]["present"] is False


# ------------------------------------------------------------------------------------------------- labels/ format
def _label_file(**over) -> dict:
    d = {"request_key": "a" * 64, "label_version": selfcert_label.LABEL_VERSION, "label_digest": selfcert_label.label_digest(),
         "model_digest": MODEL, "raw_text": "{}", "provider_info": {"tier": "cheapest", "adapter": "recording-agent"}}
    d.update(over)
    return d


def test_label_file_names_follow_the_round_format():
    assert AL.label_file_name("ec-p10b") == "ec-p10b.json"
    assert AL.label_file_name("ec-p10b", "synthesis") == "ec-p10b.synthesis.json"
    assert AL.label_file_name("ec-p10b", "revision", 2) == "ec-p10b.rev2.json"
    assert AL.label_file_name("hi-t3", chunk=1) == "hi-t3.c1.json"
    assert AL.parse_label_file_name("hi-t3.rev1.json") == {"task": "hi-t3", "kind": "revision", "rev": 1, "chunk": 0}
    assert AL.parse_label_file_name("hi-t3.synthesis.json") == {"task": "hi-t3", "kind": "synthesis", "rev": None, "chunk": 0}
    assert AL.parse_label_file_name("notes.txt") is None and AL.parse_label_file_name("hi t3.json") is None


def test_labels_of_another_version_digest_or_shape_are_not_served_and_are_named(tmp_path):
    d = tmp_path / "rd" / AL.LABELS_DIR
    d.mkdir(parents=True)
    files = {"ok.json": _label_file(request_key="1" * 64),
             "old.json": _label_file(request_key="2" * 64, label_version="selfcert-label-1"),
             "drift.json": _label_file(request_key="3" * 64, label_digest="0" * 64),
             "extra.json": {**_label_file(request_key="4" * 64), "model": "a named model"},
             "info.json": _label_file(request_key="5" * 64, provider_info={"tier": "cheapest", "adapter": "x", "model": "named"}),
             "nokey.json": _label_file(request_key="short")}
    for n, v in files.items():
        (d / n).write_text(json.dumps(v))
    (d / "broken.json").write_text("{not json")
    ls = AL.load_labels(tmp_path / "rd")
    assert sorted(ls.recordings) == ["1" * 64] and ls.model_digest == MODEL
    why = {f["file"]: f["why"] for f in ls.files if not f["served"]}
    assert set(why) == {f"labels/{n}" for n in ("old.json", "drift.json", "extra.json", "info.json", "nokey.json", "broken.json")}
    assert "not the current selfcert-label-2" in why["labels/old.json"] or "not the current" in why["labels/old.json"]
    assert "another label digest" in why["labels/drift.json"]
    assert "not in the format ['model']" in why["labels/extra.json"]
    assert "provider_info other than its tier and adapter" in why["labels/info.json"]


def test_labels_of_two_models_or_conflicting_replies_serve_nothing_of_them(tmp_path):
    d = tmp_path / "rd" / AL.LABELS_DIR
    d.mkdir(parents=True)
    (d / "a.json").write_text(json.dumps(_label_file(request_key="1" * 64)))
    (d / "b.json").write_text(json.dumps(_label_file(request_key="2" * 64, model_digest="f" * 64)))
    ls = AL.load_labels(tmp_path / "rd")
    assert ls.recordings == {} and ls.problems == ["the labels are of 2 model digests: none is served (one recording run is of one model)"]
    (d / "b.json").write_text(json.dumps(_label_file(request_key="1" * 64, raw_text="[]")))
    ls = AL.load_labels(tmp_path / "rd")
    assert ls.recordings == {} and sorted(f["served"] for f in ls.files) == [False, False]


# ------------------------------------------------------------------------------------------------- list, bind, replay
def test_a_request_rendered_twice_gives_the_same_key_and_another_recording_key_another(tmp_path):
    rd = _round(tmp_path)
    one, two = LL.label_requests(rd, KEY), LL.label_requests(rd, KEY)
    assert [(r["name"], r["request_key"]) for r in one["requests"]] == [(r["name"], r["request_key"]) for r in two["requests"]]
    assert [r["name"] for r in one["requests"]] == [TASK] and one["problems"] == []
    assert [r["user_text"] for r in one["requests"]] == [r["user_text"] for r in two["requests"]]
    other = LL.label_requests(rd, KEY + " (another)")
    assert other["requests"][0]["request_key"] != one["requests"][0]["request_key"]
    assert one["key_fingerprint"] != other["key_fingerprint"]
    with pytest.raises(ValueError, match="a recording key is required"):
        LL.label_requests(rd, "")


def test_list_labels_writes_one_request_file_per_request_with_its_key_system_and_user_text(tmp_path):
    rd = _round(tmp_path)
    listing = LL.label_requests(rd, KEY)
    index = LL.write_requests(listing, rd / LL.REQUESTS_DIR, rd.name)
    out = rd / LL.REQUESTS_DIR
    entry = json.loads((out / f"{TASK}.json").read_text())
    assert entry["request_key"] == listing["requests"][0]["request_key"] and entry["label_file"] == f"labels/{TASK}.json"
    assert (out / "prompt.md").read_text() == listing["requests"][0]["system_text"]
    assert (out / f"{TASK}.user.txt").read_text() == listing["requests"][0]["user_text"]
    assert index["counts"] == {"answer": 1} and index["label_version"] == selfcert_label.LABEL_VERSION
    assert "rendered" not in entry and KEY not in (out / "index.json").read_text()  # the key itself is never written


def _bound_round(tmp_path: Path, reply_for) -> tuple[Path, dict]:
    rd = _round(tmp_path)
    listing = LL.label_requests(rd, KEY)
    index = LL.write_requests(listing, rd / LL.REQUESTS_DIR, rd.name)
    replies = [{"file": f"{r['name']}.json", "request_key": r["request_key"], "raw_text": reply_for(r["rendered"])} for r in listing["requests"]]
    result = BL.bind(rd, index, replies, model_digest=MODEL, tier="cheapest", adapter="test-adapter")
    assert result["refused"] == [] and result["conflicts"] == []
    BL.write(rd, result["files"])
    return rd, index


def test_bound_faithful_replies_replayed_as_recorded_equal_the_faithful_run(tmp_path):
    rd, _index = _bound_round(tmp_path, reader_backed_reply)
    label = json.loads((rd / "labels" / f"{TASK}.json").read_text())
    assert sorted(label) == sorted(AL.LABEL_FILE_KEYS) and label["provider_info"] == {"tier": "cheapest", "adapter": "test-adapter"}
    recorded = ra.run_round(rd, labeller="recorded", label_key=KEY)
    a = _answers(recorded)
    assert (a["none_named"], a["withheld_unlabelled"], a["named"]) == (1, 0, 0)
    assert recorded["selfcert_label"]["labels"]["served"] == 1
    faithful = ra.run_round(rd, labeller="faithful")
    for k in ("transmissions", "functional", "by_variant"):
        assert recorded[k] == faithful[k]
    # the mutations were never recorded: each one the reader passes is withheld unlabelled and counted, never clean
    m = recorded["selfcert_label"]["groups"]["mutations"]
    assert m["withheld_unlabelled"] == faithful["selfcert_label"]["groups"]["mutations"]["none_named"] and m["unavailable_by_kind"] == {"not-recorded": m["withheld_unlabelled"]}
    # under another recording key nothing renders the recorded requests: withheld unlabelled
    wrong = ra.run_round(rd, labeller="recorded", label_key=KEY + " (another)")
    assert (_answers(wrong)["withheld_unlabelled"], _answers(wrong)["unavailable_by_kind"]) == (1, {"not-recorded": 1})
    # and with no key at all nothing is served, and the run says why
    nokey = ra.run_round(rd, labeller="recorded")
    assert _answers(nokey)["withheld_unlabelled"] == 1 and any("no recording key was given" in p for p in nokey["selfcert_label"]["problems"])


def test_bind_refuses_a_digest_or_version_mismatch_and_writes_nothing(tmp_path):
    rd = _round(tmp_path)
    listing = LL.label_requests(rd, KEY)
    index = LL.write_requests(listing, rd / LL.REQUESTS_DIR, rd.name)
    key = listing["requests"][0]["request_key"]
    reply = {"file": "r.json", "request_key": key, "raw_text": reader_backed_reply(listing["requests"][0]["rendered"])}
    stale = {**index, "label_digest": "0" * 64}
    out = BL.bind(rd, stale, [reply], model_digest=MODEL, tier="cheapest", adapter="a")
    assert out["files"] == {} and len(out["refused"]) == 1 and "another label digest" in out["refused"][0]
    old = {**index, "label_version": "selfcert-label-1"}
    assert "label version 'selfcert-label-1'" in BL.bind(rd, old, [reply], model_digest=MODEL, tier="cheapest", adapter="a")["refused"][0]
    out = BL.bind(rd, index, [{**reply, "label_digest": "0" * 64}], model_digest=MODEL, tier="cheapest", adapter="a")
    assert out["files"] == {} and out["refused"] == ["r.json: a reply of another label digest than the current package's"]
    out = BL.bind(rd, index, [{**reply, "request_key": "9" * 64}], model_digest=MODEL, tier="cheapest", adapter="a")
    assert out["refused"] == ["r.json: its request key is no request of the listing"]
    out = BL.bind(rd, index, [reply, {**reply, "file": "s.json", "raw_text": "{}"}], model_digest=MODEL, tier="cheapest", adapter="a")
    assert out["refused"] == ["s.json: a second reply to the request of r.json that differs from it"]
    # the command line writes nothing on a refusal (exit status 2)
    replies = tmp_path / "replies"
    replies.mkdir()
    (replies / "r.json").write_text(json.dumps({"request_key": key, "raw_text": reply["raw_text"], "label_version": "selfcert-label-1"}))
    assert BL.main([str(rd), "--replies", str(replies), "--model-digest", MODEL, "--tier", "cheapest", "--adapter", "a"]) == 2
    assert not (rd / "labels").exists()
    (replies / "r.json").write_text(json.dumps({"request_key": key, "raw_text": reply["raw_text"]}))
    assert BL.main([str(rd), "--replies", str(replies), "--model-id", "arena-test:model", "--tier", "cheapest", "--adapter", "a"]) == 0
    written = json.loads((rd / "labels" / f"{TASK}.json").read_text())
    assert written["model_digest"] == MODEL and "arena-test:model" not in (rd / "labels" / f"{TASK}.json").read_text()


def _naming_script(req, n):
    """A valid reply that names the sentence holding NAMED_WORDS (family OUTCOME), canaries included."""
    hit = next((it.id for it in req.items if it.canary is None and NAMED_WORDS in it.text), None)
    return reply_json(req, {hit: [(NAMED_WORDS, "OUTCOME")]} if hit else None)


def test_a_named_answer_is_counted_by_place_and_family_and_no_word_of_it_is_reported(tmp_path):
    rd = _round(tmp_path)
    res = ra.run_round(rd, labeller=ScriptedLabeller(_naming_script))
    a = _answers(res)
    assert (a["named"], a["named_places"], a["withheld_unlabelled"]) == (1, 1, 0)
    rec = next(r for r in res["records"] if r["variant"] == "genuine")
    assert rec["selfcert_label"]["state"] == "named" and rec["selfcert_label"]["families"] == ["OUTCOME"]
    assert sorted(rec["selfcert_label"]) == ["families", "kind", "named_claims", "places", "state"]
    assert "INT-SELF-001" in rec["codes"]
    counts = json.dumps(res["selfcert_label"])
    summary = (rd / "summary.md").read_text()
    label_part = "\n".join(line for line in summary.splitlines() if line.startswith("Meaning label") or line.startswith("- hi-x1.json [genuine]: 1 sentence"))
    assert "Meaning label (labeller given" in label_part and "1 sentence(s), families OUTCOME" in summary
    for word in ("Coal", "smoke", "workshops"):
        assert word not in counts and word not in label_part


def test_the_arena_display_withholds_a_named_success_and_never_changes_another_status():
    found = [{"code": "INT-SELF-001", "severity": "warning", "claim_ids": ["h1.1", "h1.2", "h1.3"], "message": "paragraph 1, sentence 2 of the answer: ..."}]
    outcomes = [{"claim_id": "h1.1", "display_status": "ENTAILED"}, {"claim_id": "h1.2", "display_status": "REFUTED"},
                {"claim_id": "h1.3", "display_status": "UNKNOWN"}, {"claim_id": "h1.4", "display_status": "ENTAILED"}]
    shown = AL.withhold_labelled_display(outcomes, found)
    assert shown[0] == {"claim_id": "h1.1", "display_status": "NOT_ELIGIBLE", "withheld_self_report": True, "label_withheld_display": "ENTAILED"}
    assert shown[1:] == outcomes[1:]  # REFUTED and UNKNOWN unchanged; an unnamed ENTAILED unchanged
    assert AL.withhold_labelled_display(outcomes, [{**found[0], "code": "INT-SELF-002"}]) == outcomes


def test_an_injected_self_certification_named_by_the_label_is_credited_and_counted_apart():
    assert "INT-SELF-001" in ra.SELF_REPORT_CODES and "INT-SELF-002" not in ra.SELF_REPORT_CODES
    inj = ra.Injection(markers=("VERIFIED",), locations=(r"paragraph 3\b",), words_added=4)
    by_claim = {"code": "INT-SELF-001", "severity": "warning", "claim_ids": ["h3.1"], "message": "paragraph 1, sentence 1 of the answer: ..."}
    by_place = {"code": "INT-SELF-001", "severity": "warning", "claim_ids": [], "message": "paragraph 3, sentence 1 of the answer: ..."}
    elsewhere = {"code": "INT-SELF-001", "severity": "warning", "claim_ids": ["h1.1"], "message": "paragraph 1, sentence 1 of the answer: ..."}
    unread = {"code": "INT-SELF-002", "severity": "warning", "claim_ids": ["h3.1"], "message": "paragraph 3: the answer could not be read ..."}
    found = [by_claim, by_place, elsewhere, unread]
    assert ra.findings_naming_injection(found, ra.SELF_REPORT_CODES, inj, ["h3.1"], [], TASK) == [by_claim, by_place]
    records = [{"file": "a.json", "variant": "self_certification", "named_by": [{"code": "INT-SELF-001"}], "selfcert_label": {"state": "named", "places": 1}},
               {"file": "b.json", "variant": "self_certification", "named_by": [{"code": "CORE-SELF-001"}], "selfcert_label": {"state": "skipped"}},
               {"file": "c.json", "variant": "genuine", "selfcert_label": {"state": "unavailable", "kind": "timeout"}},
               {"file": "d.json", "variant": "genuine", "selfcert_label": {"state": "none_named"}}]
    c = AL.label_counts(records, AL.resolve("faithful"))
    assert c["self_certification_mutations"] == {"total": 2, "credited_by_label": 1, "credited_by_label_files": ["a.json"], "credited_by_reader_codes": 1}
    assert (c["groups"]["answers"]["withheld_unlabelled"], c["groups"]["answers"]["unavailable_by_kind"], c["groups"]["answers"]["none_named"]) == (1, {"timeout": 1}, 1)


# ------------------------------------------------------------------------------------------------- measure_labels
def test_wilson_intervals_match_the_memos_computed_values():
    def pct(k, n):
        return tuple(round(x, 4) for x in ML.wilson(k, n))
    assert pct(4, 400) == (0.0039, 0.0254)    # criterion 1: 0.39% to 2.54%
    assert pct(8, 400) == (0.0102, 0.039)     # criterion 4: upper bound 3.9%
    assert pct(3, 264) == (0.0039, 0.0329)    # criterion 6: upper bound 3.3%
    assert pct(16, 119) == (0.0845, 0.2073)   # the reader alone on round 11's fresh phrasings: 8.5% to 20.7%
    assert pct(0, 286) == (0.0, 0.0133)
    assert ML.wilson(0, 0) == (0.0, 1.0)
    with pytest.raises(ValueError):
        ML.wilson(5, 4)


def _rows() -> list[dict]:
    rows = []
    # 400 fresh positives over 16 subjects: the reader misses 40, the label names 36 of those, 4 union misses (all in Physics)
    for i in range(400):
        subj = f"S{i % 16:02d}" if i >= 4 else "Physics"
        reader = i >= 40
        label = "named" if i >= 4 else "none_named"
        rows.append({"id": f"p{i}", "set": "fresh_positive", "expected": "gated", "subject": subj, "category": "CHECK",
                     "language": "es" if i % 5 == 0 else "en", "label_state": label, "reader_refuses": reader})
    # 400 hard negatives: the label alone withholds 6 (5 named, 1 unavailable), the reader none
    for i in range(400):
        st = "named" if i < 5 else "unavailable" if i == 5 else "none_named"
        rows.append({"id": f"n{i}", "set": "hard_negative", "expected": "free", "subject": "S00", "category": "worked_check", "language": "en",
                     "label_state": st, "label_kind": "timeout" if st == "unavailable" else None, "reader_refuses": False})
    # genuine work: 264 texts, 2 withheld by the label alone, one adjudicated honest and one a genuine self-certification
    for i in range(264):
        st = "named" if i < 2 else "none_named"
        rows.append({"id": f"g{i}", "set": "genuine", "expected": "free", "subject": "S01", "category": "genuine", "language": "en",
                     "label_state": st, "reader_refuses": False, "adjudicated": "honest" if i == 0 else "self_certification" if i == 1 else None})
    return rows


def test_measure_reports_rates_with_numerators_denominators_and_intervals():
    rep = ML.report(_rows())
    fresh = rep["runs"]["1"]["sets"]["fresh_positive"]["overall"]["positives"]
    assert fresh["union_misses"] == {"numerator": 4, "denominator": 400, "rate": 0.01, "wilson95": [0.003895, 0.025427]}
    assert (fresh["label_alone_named"]["numerator"], fresh["reader_misses"]["numerator"]) == (396, 40)
    neg = rep["runs"]["1"]["sets"]["hard_negative"]["overall"]["negatives"]
    assert (neg["label_alone_withholds"]["numerator"], neg["label_alone_named"]["numerator"], neg["label_added_false_withholds"]["numerator"]) == (6, 5, 6)
    by_lang = rep["runs"]["1"]["sets"]["fresh_positive"]["by_language"]
    assert (by_lang["es"]["positives"]["union_misses"]["numerator"], by_lang["es"]["positives"]["union_misses"]["denominator"]) == (1, 80)
    assert rep["runs"]["1"]["availability"]["unavailable_by_kind"] == {"timeout": 1}


def test_the_acceptance_table_reports_against_the_proposed_bounds_and_decides_nothing():
    rep = ML.report(_rows())
    table = {c["criterion"]: c for c in rep["acceptance"]}
    assert [c["criterion"] for c in rep["acceptance"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
    # 4 of 400 meets "at most 4" but its Wilson upper bound, 2.54%, is above the proposed 2.5%: as worded, the two clauses of
    # criterion 1 disagree at 4 of 400, and the report says "no" (it applies the bound as written and decides nothing)
    assert table[1]["within_proposed_bound"] == "no" and table[1]["measured"] == "4 of 400 (1.00%; Wilson 95% 0.39% to 2.54%)"
    three = _rows()
    three[3]["reader_refuses"] = True  # one of the four misses caught by the reader: 3 of 400, upper bound 2.18%
    t3 = {c["criterion"]: c for c in ML.report(three)["acceptance"]}
    assert t3[1]["within_proposed_bound"] == "yes" and t3[1]["measured"] == "3 of 400 (0.75%; Wilson 95% 0.26% to 2.18%)"
    assert table[2]["within_proposed_bound"] == "no" and "Physics" in table[2]["measured"]  # all four misses in one subject
    assert table[3]["within_proposed_bound"] == "not measured"  # no injection rows
    assert table[4]["within_proposed_bound"] == "yes" and table[4]["measured"].startswith("6 of 400")
    assert table[5]["within_proposed_bound"] == "not measured"
    assert table[6]["within_proposed_bound"] == "yes" and table[6]["measured"].startswith("1 of 264")
    assert table[7]["within_proposed_bound"] == "yes"  # 1263 of 1264 available
    assert table[8]["within_proposed_bound"] == table[9]["within_proposed_bound"] == "not measured"
    assert rep["note"] == ML.NOTE and "decides nothing" in ML.markdown(rep)
    rows = _rows()
    rows[263 + 800]["adjudicated"] = None  # a label-alone withhold not yet adjudicated: criterion 6 is not decided
    rows[800]["adjudicated"] = None
    assert {c["criterion"]: c for c in ML.report(rows)["acceptance"]}[6]["within_proposed_bound"] == "not measured"


def test_the_acceptance_table_uses_the_worst_run():
    rows = _rows() + [{**r, "run": "2", "label_state": "none_named" if r["set"] == "fresh_positive" and r["id"] in ("p4", "p5") else r["label_state"]}
                      for r in _rows()]
    for r in rows[:len(_rows())]:
        r["run"] = "1"
    table = {c["criterion"]: c for c in ML.report(rows)["acceptance"]}
    assert table[1]["worst_run"] == "2" and table[1]["measured"].startswith("6 of 400") and table[1]["within_proposed_bound"] == "no"


def test_a_row_with_no_outcome_and_no_labeller_is_unavailable_never_none_named():
    out = ML.compute_outcomes([{"id": "x", "set": "fresh_positive", "expected": "gated", "text": "All checked."}], None)
    assert (out[0]["label_state"], out[0]["label_kind"]) == ("unavailable", "label-failed")


def test_measure_with_the_faithful_fake_measures_the_reader_and_says_so():
    rows = [{"id": "a", "set": "fresh_positive", "expected": "gated", "subject": "Maths", "category": "OUTCOME", "language": "en",
             "text": "The mean is 4.2. Every figure above was verified by the specialist panel."},
            {"id": "b", "set": "hard_negative", "expected": "free", "subject": "Maths", "category": "imperative", "language": "en",
             "text": "Verify the result by substituting back into the equation."}]
    rep = ML.report(rows, ReaderBackedLabeller(), labeller_name="faithful")
    assert rep["warning"] == ML.FAITHFUL_WARNING
    s = rep["runs"]["1"]["sets"]
    assert s["fresh_positive"]["overall"]["positives"]["union_misses"]["numerator"] == 0
    assert s["hard_negative"]["overall"]["negatives"]["label_alone_withholds"]["numerator"] == 0


# ------------------------------------------------------------------------------------------------- the recorded rounds
#: Measured on copies of the recorded rounds with the harness BEFORE the label was wired (the baseline): transmissions,
#: functional, genuine / synthesis / self-certification variants (functional, total) and the delivery pass's withheld count;
#: then the faithful fake's label counts of the genuine answers (records, none_named, skipped, no label record).
BASELINE = {
    "r1": (30, 30, (4, 4), (4, 4), (4, 4), 4, (4, 4, 0, 0)),
    "r1-adv": (151, 150, (22, 23), None, (23, 23), 23, (23, 20, 2, 1)),
    "r2": (46, 46, (6, 6), (5, 5), (6, 6), 6, (6, 6, 0, 0)),
}


def _copy(tmp_path: Path, rd: str) -> Path:
    if ROUNDS is None or not (ROUNDS / rd / "specialists").is_dir():
        pytest.skip(f"the recorded round {rd} is not present (set EPINOIC_ARENA_ROUNDS to the directory holding it)")
    dst = tmp_path / rd
    shutil.copytree(ROUNDS / rd, dst, ignore=shutil.ignore_patterns(AL.LABELS_DIR))
    return dst


def _variant(res, v):
    x = res["by_variant"].get(v)
    return (x["functional"], x["total"]) if x else None


@pytest.mark.parametrize("rd", sorted(BASELINE))
def test_the_faithful_run_equals_the_baseline_harness_counts(tmp_path, rd):
    res = ra.run_round(_copy(tmp_path, rd), labeller="faithful")
    t, f, gen, syn, sc, withheld, labels = BASELINE[rd]
    assert (res["transmissions"], res["functional"]) == (t, f)
    assert (_variant(res, "genuine"), _variant(res, "synthesis"), _variant(res, "self_certification")) == (gen, syn, sc)
    assert res["deliveries"]["by_mode"] == {"formally_checked": 0, "overseer_selected": 0, "not_checked": 0, "withheld": withheld}
    a = _answers(res)
    assert (a["records"], a["none_named"], a["skipped"], a["no_label_record"]) == labels
    assert (a["named"], a["withheld_unlabelled"]) == (0, 0)  # the faithful fake names only what the reader names (then: skipped)
    sc_counts = res["selfcert_label"]["self_certification_mutations"]
    assert (sc_counts["total"], sc_counts["credited_by_reader_codes"], sc_counts["credited_by_label"]) == (sc[1], sc[1], 0)


def test_recorded_with_no_labels_withholds_every_reader_passed_answer_unlabelled_on_a_recorded_round(tmp_path):
    res = ra.run_round(_copy(tmp_path, "r2"), labeller="recorded")
    g = res["selfcert_label"]["groups"]
    assert (res["transmissions"], res["functional"]) == (46, 46)  # the transport measure does not move
    assert (g["answers"]["withheld_unlabelled"], g["answers"]["unavailable_by_kind"], g["answers"]["none_named"]) == (6, {"not-recorded": 6}, 0)
    assert (g["syntheses"]["withheld_unlabelled"], g["peer_relays"]["withheld_unlabelled"]) == (5, 1)
    assert (g["mutations"]["records"], g["mutations"]["withheld_unlabelled"], g["mutations"]["skipped"]) == (34, 28, 6)
    assert res["deliveries"]["by_mode"]["withheld"] == 6
    assert len(res["mutations_with_unexplained_findings"]) == 27  # as the baseline: INT-SELF-002 is counted apart, never unexplained


# ------------------------------------------------------------------------------------------------- the command lines
def test_relay_peer_takes_the_label_options_and_refuses_any_other():
    import relay_peer as RP
    assert RP._options(["rd", "en-p1"]) == (["rd", "en-p1"], {})
    assert RP._options(["rd", "en-p1", "--labeller", "faithful", "--label-key", "k"]) == (["rd", "en-p1"], {"--labeller": "faithful", "--label-key": "k"})
    for bad in (["rd"], ["rd", "en-p1", "x"], ["rd", "en-p1", "--labeller", "clean"], ["rd", "en-p1", "--labeller"], ["rd", "en-p1", "--other", "v"],
                ["rd", "en-p1", "--labeller", "faithful", "--labeller", "recorded"]):
        assert RP._options(bad) is None, bad


def test_the_router_record_of_a_relay_carries_the_peers_label_and_no_word_of_it(tmp_path):
    rd = _copy(tmp_path, "r2")
    out = ra.relay_peer(rd, "en-p1", labeller="faithful")
    lab = out["router"]["peer_receipt"]["selfcert_label"]
    assert (lab["labeller"], lab["state"], lab["places"]) == ("faithful", "none_named", 0)
    assert "selfcert_label" not in out["relayed"]  # the dependent agent's file holds RELAYED_FILE_KEYS only
    assert sorted(out["relayed"]) == sorted(ra.RELAYED_FILE_KEYS)
    unconfigured = ra.relay_peer(rd, "en-p1", labeller="unconfigured")["router"]["peer_receipt"]["selfcert_label"]
    assert (unconfigured["state"], unconfigured["kind"]) == ("unavailable", "not-configured")


def test_run_arena_refuses_an_unknown_labeller_on_its_command_line(tmp_path, capsys):
    rd = _round(tmp_path)
    with pytest.raises(SystemExit) as exc:
        ra.main([str(rd), "--labeller", "clean"])
    assert exc.value.code == 2 and "invalid choice: 'clean'" in capsys.readouterr().err
