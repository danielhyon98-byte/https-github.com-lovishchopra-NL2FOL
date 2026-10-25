"""Repair round 5, INV-QROLE-1 at the command line: ``check-report`` reads quotation roles in the task type the operator
states (``--task-type``, or an envelope's ``task_type``, the request's metadata beside the raw response). A
``SpecialistReport`` document's own ``task_type`` is the report's statement about itself and never widens the roles, so
without ``--task-type`` such a report is read in no task, where a correction frame is checked as a quotation."""
from __future__ import annotations

import json

import epinoic_logic.cli as cli
from epinoic_logic.adapters.markdown import feedback_task
from epinoic_logic.translate.contracts import SpecialistReport, sha256_text

BODY = 'The image → "the silent willows bend".'


def _report(task_type: str) -> SpecialistReport:
    return SpecialistReport(request_id="req", task_id="task", report_id="rep", agent_id="english-specialist", subject="English A: Literature",
                            task_type=task_type, original_response=BODY, response_sha256=sha256_text(BODY), created_at="2026-10-24T00:00:00Z",
                            claims=[], supplied_texts=[])


class _Adapter:
    """A stand-in adapter: its structural checks record whether they ran in a feedback task."""

    def __init__(self) -> None:
        self.seen: list[bool] = []

    def structural_checks(self, report):
        self.seen.append(feedback_task())
        return []

    def parse_response(self, response, **kw):
        return _report(kw["task_type"])


def _run(monkeypatch, tmp_path, capsys, document: dict, *extra: str) -> list[bool]:
    adapter = _Adapter()
    monkeypatch.setattr(cli, "_load_adapter", lambda _adapter_id: adapter)
    report, fixtures = tmp_path / "report.json", tmp_path / "fixtures.json"
    report.write_text(json.dumps(document), encoding="utf-8")
    fixtures.write_text("{}", encoding="utf-8")
    rc = cli.main(["check-report", str(report), "--fixtures", str(fixtures), *extra])
    out = capsys.readouterr().out
    assert rc == 0 and json.loads(out) == []                                   # the report holds no claims: no outcome
    return adapter.seen


def test_a_report_documents_own_task_type_never_widens_the_roles(monkeypatch, tmp_path, capsys):
    assert _run(monkeypatch, tmp_path, capsys, _report("marking_feedback").model_dump(mode="json")) == [False]


def test_control_the_operators_task_type_reads_correction_frames(monkeypatch, tmp_path, capsys):
    document = _report("analytical_paragraph").model_dump(mode="json")
    assert _run(monkeypatch, tmp_path, capsys, document, "--task-type", "marking_feedback") == [True]


def test_control_an_envelopes_task_type_is_the_requests_metadata(monkeypatch, tmp_path, capsys):
    envelope = {"response": BODY, "request_id": "req", "task_id": "task", "report_id": "rep", "subject": "English A: Literature",
                "task_type": "marking_feedback"}
    assert _run(monkeypatch, tmp_path, capsys, envelope) == [True]
