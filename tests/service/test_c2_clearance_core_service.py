"""Round-9 clearance (integrated round c2), the class sweep of the over-long response (queued q211b, critical: unbounded work
on oversize input, the contract's limit held only after a reader had run on the whole text) at the command-line boundary
and the channel's structured payloads:

* ``check-report`` handed an envelope whose ``response`` is over the contract's 400,000-character limit parsed it whole with
  the branch adapter first; it is now refused before the adapter runs, naming the length and the limit;
* a report or fixtures file was read whole however large; a file over the command line's limit is now refused before it is
  read, and a problem file is read up to the validator's own limit and one byte more, so the engine refuses it (E306) as
  before without the command reading the rest;
* a structured report whose claims list is over the contract's limit (512) was read claim by claim for provenance before
  validation refused it (100,000 claims: 1.5 s and as many findings); the list is now refused by validation unread.
"""
from __future__ import annotations

import json
import time

import pytest

from epinoic_logic import cli
from epinoic_logic.channel.bus import _raw_claim_provenance


def _envelope(response: str) -> dict:
    return {"request_id": "r", "task_id": "t", "report_id": "rep", "subject": "History", "task_type": "short_answer", "response": response}


def test_check_report_refuses_an_over_long_response_before_the_adapter_parses_it(tmp_path, capsys, monkeypatch):
    seen: list[int] = []

    class Recording:
        def parse_response(self, text, **kw):
            seen.append(len(text))
            raise ValueError("stub")
    monkeypatch.setattr(cli, "_load_adapter", lambda adapter_id: Recording())
    report = tmp_path / "report.json"
    fixtures = tmp_path / "fixtures.json"
    fixtures.write_text("{}")
    report.write_text(json.dumps(_envelope("The war ended in 1953. " * 20_000)))  # 460,000 characters
    code = cli.main(["check-report", str(report), "--fixtures", str(fixtures), "--adapter", "history-specialist"])
    err = capsys.readouterr().err
    assert code != 0 and seen == [] and "over the contract's limit of 400000" in err and "460000 characters" in err, err
    # control: a response within the limit reaches the adapter
    report.write_text(json.dumps(_envelope("The war ended in 1953.")))
    cli.main(["check-report", str(report), "--fixtures", str(fixtures), "--adapter", "history-specialist"])
    capsys.readouterr()
    assert seen == [len("The war ended in 1953.")]


def test_a_file_over_the_command_line_limit_is_refused_unread(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(cli, "MAX_INPUT_FILE_BYTES", 1_000)
    report = tmp_path / "report.json"
    report.write_text(json.dumps(_envelope("x" * 5_000)))
    fixtures = tmp_path / "fixtures.json"
    fixtures.write_text("{}")
    code = cli.main(["check-report", str(report), "--fixtures", str(fixtures), "--adapter", "history-specialist"])
    err = capsys.readouterr().err
    assert code != 0 and "over the command line's limit of 1000 bytes" in err, err


def test_a_problem_file_over_the_validator_limit_is_still_refused_by_the_engine(tmp_path, capsys):
    problem = tmp_path / "problem.json"
    problem.write_text('{"notes": "' + "x" * 1_200_000 + '"}')
    code = cli.main(["verify", str(problem)])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and any(d["code"] == "E306" for d in out["diagnostics"]), out["diagnostics"]


@pytest.mark.parametrize("n", [513, 100_000])
def test_a_claims_list_over_the_contract_limit_is_not_read_claim_by_claim(n):
    ids = dict(request_id="r", task_id="t", report_id="rep", agent_id="a")
    data = dict(ids, claims=[dict(ids, claim_id=f"h{i}", report_id="other") for i in range(n)])
    t0 = time.process_time()
    assert _raw_claim_provenance(data) == []
    assert time.process_time() - t0 < 0.5
    # control: within the limit every claim carrying another report's provenance is still named
    assert len(_raw_claim_provenance(dict(ids, claims=data["claims"][:3]))) == 3
