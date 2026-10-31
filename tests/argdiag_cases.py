"""Loader of the argument-diagnosis development cases (``tests/data/argdiag_dev_cases.json``).

The cases are data in the ``argdiag-corpus/1`` format: ``id``, ``family`` (formal, evidence, informal, stem, e2e),
``expected_label`` (a canonical label of ``epinoic_logic.named.DEFECT_LABELS``, or ``"none"`` for a clean control),
``acceptable_labels``, ``title``, ``subject``, ``task_type``, ``agent_id``, ``request``, ``answer``, ``supplied_texts``,
``ids`` (task, request, report and plan ids), ``plan`` (optional work-plan fields), ``modes`` (``text`` or ``report``
delivery, with or without a synthesis), ``report_claims`` (for report delivery), ``translations`` (the translator JSON a
fixture provider returns for a delivered claim, matched by exact normalised text, else by ``contains``, else by claim id),
``fidelity_review``, ``peers`` (deliveries made first, end-to-end cases), ``scope`` and ``origin``. Translation and peer
lists shared by several cases are stored once in the file; :func:`load_case` resolves them, so every case it returns is
self-contained. Nothing in a case is executed: proposals are passed to the translator as JSON text.

The holdout cases are not in this file and must never be added to it.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Optional

__all__ = ["CASES_PATH", "CASE_FORMAT", "FILE_FORMAT", "CONTROL", "case_ids", "load_case", "load_cases", "controls", "defects",
           "proposal_for", "proposal_text", "supplied_texts", "task_record", "work_plan_fields", "structured_report"]

CASES_PATH = Path(__file__).resolve().parent / "data" / "argdiag_dev_cases.json"
FILE_FORMAT = "argdiag-dev-cases/1"
CASE_FORMAT = "argdiag-corpus/1"
#: ``expected_label`` of a clean control.
CONTROL = "none"


@lru_cache(maxsize=1)
def _document() -> dict:
    doc = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if doc.get("format") != FILE_FORMAT or doc.get("case_format") != CASE_FORMAT:
        raise ValueError(f"{CASES_PATH.name} is not an {FILE_FORMAT} file")
    return doc


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    return {c["id"]: c for c in _document()["cases"]}


def case_ids(*, family: Optional[str] = None, prefix: Optional[str] = None, controls_only: Optional[bool] = None) -> list[str]:
    """The case ids in file order, optionally only of one ``family``, with an id ``prefix``, or only controls (True) or only
    defects (False)."""
    out = []
    for c in _document()["cases"]:
        if family is not None and c.get("family") != family:
            continue
        if prefix is not None and not c["id"].startswith(prefix):
            continue
        if controls_only is not None and (c.get("expected_label") == CONTROL) is not controls_only:
            continue
        out.append(c["id"])
    return out


def load_case(case_id: str) -> dict:
    """One case, self-contained (its translation and peer lists resolved) and freshly copied: a test may change it."""
    doc = _document()
    case = copy.deepcopy(_index()[case_id])
    ref = case.get("translations")
    if isinstance(ref, str):
        case["translations"] = copy.deepcopy(doc["translation_sets"][ref])
    ref = case.get("peers")
    if isinstance(ref, str):
        case["peers"] = copy.deepcopy(doc["peer_sets"][ref])
    return case


def load_cases(ids: Optional[Iterable[str]] = None) -> list[dict]:
    """Every case (or the cases ``ids`` names), in file order."""
    wanted = list(ids) if ids is not None else case_ids()
    return [load_case(i) for i in wanted]


def controls() -> list[dict]:
    return load_cases(case_ids(controls_only=True))


def defects() -> list[dict]:
    return load_cases(case_ids(controls_only=False))


def _norm(text: Optional[str]) -> str:
    return " ".join((text or "").split())


def proposal_for(case: dict, claim_text: str, claim_id: Optional[str] = None) -> Optional[dict]:
    """The recorded translator proposal for a delivered claim: exact normalised text, else a ``contains`` substring, else the
    claim id of an entry that names neither (a copy; None when no entry matches)."""
    text = _norm(claim_text)
    items = case.get("translations", [])
    for t in items:
        if t.get("claim_text") is not None and _norm(t["claim_text"]) == text:
            return copy.deepcopy(t["proposal"])
    for t in items:
        if t.get("contains") and _norm(t["contains"]) in text:
            return copy.deepcopy(t["proposal"])
    for t in items:
        if t.get("claim_text") is None and t.get("contains") is None and claim_id is not None and t.get("claim_id") == claim_id:
            return copy.deepcopy(t["proposal"])
    return None


def proposal_text(case: dict, claim: Any) -> Optional[str]:
    """The proposal for ``claim`` (a ``ClaimRecord``) as the JSON text a fixture provider returns, its problem's request and
    claim ids set to the claim's."""
    obj = proposal_for(case, claim.claim_text, claim.claim_id)
    if obj is None:
        return None
    if isinstance(obj.get("problem"), dict):
        obj["problem"]["claim_id"] = claim.claim_id
        obj["problem"]["request_id"] = claim.request_id
    return json.dumps(obj, ensure_ascii=False)


def supplied_texts(case: dict) -> list:
    """The case's supplied texts as ``SuppliedText`` records."""
    from epinoic_logic.translate.contracts import SuppliedText
    return [SuppliedText(document_id=t["document_id"], title=t.get("title"), author=t.get("author"), text=t["text"],
                         locator_scheme=t.get("locator_scheme", "none")) for t in case.get("supplied_texts", [])]


def _ids(case: dict) -> dict:
    ids = case.get("ids") or {}
    return {"plan_id": ids.get("plan_id", f"plan-{case['id']}"), "request_id": ids.get("request_id", f"req-{case['id']}"),
            "task_id": ids.get("task_id", f"task-{case['id']}"), "report_id": ids.get("report_id", f"rep-{case['id']}")}


def task_record(case: dict):
    """The case's request as the router's ``TaskRecord``."""
    from epinoic_logic.translate.contracts import TaskRecord
    ids = _ids(case)
    return TaskRecord.of(ids["task_id"], ids["request_id"], case["request"])


def work_plan_fields(case: dict, *, combinator: Optional[str] = "combinator") -> dict:
    """The ``WorkPlan`` fields of the case: its ids, subject and task type, the answering agent (and ``combinator``), the
    supplied texts as the allowed documents, then the case's own ``plan`` fields."""
    ids = _ids(case)
    fields = dict(plan_id=ids["plan_id"], request_id=ids["request_id"], task_id=ids["task_id"], subject=case["subject"], task_type=case["task_type"],
                  selected_agent_ids=[case["agent_id"]] + ([combinator] if combinator else []),
                  allowed_document_ids=sorted({t["document_id"] for t in case.get("supplied_texts", [])}))
    fields.update(case.get("plan") or {})
    return fields


def structured_report(case: dict):
    """The case's structured report (report delivery): its ``report_claims`` over the answer, which every claim text must be
    a substring of."""
    from epinoic_logic.ir.schema import SourceRef
    from epinoic_logic.translate.common import utc_now_rfc3339
    from epinoic_logic.translate.contracts import ClaimRecord, SpecialistReport, sha256_text
    ids = _ids(case)
    text = case["answer"]
    claims = []
    for c in case.get("report_claims", []):
        if c["text"] not in text:
            raise ValueError(f"report claim {c['claim_id']} is not a substring of the answer")
        claims.append(ClaimRecord(request_id=ids["request_id"], task_id=ids["task_id"], report_id=ids["report_id"], agent_id=case["agent_id"],
                                  subject=case["subject"], task_type=case["task_type"], claim_id=c["claim_id"], claim_text=c["text"],
                                  claim_role=c.get("role", "other"), proposed_claim_kind=c.get("kind", "unknown"), materiality=c.get("materiality", "material"),
                                  certainty=c.get("certainty", "established"), source_refs=[SourceRef(**r) for r in c.get("source_refs", [])],
                                  supporting_claim_ids=c.get("supporting", []), assumptions=c.get("assumptions", []),
                                  advisory_verification_status=c.get("advisory_status"), advisory_verification_eligibility=c.get("advisory_eligible")))
    return SpecialistReport(report_id=ids["report_id"], request_id=ids["request_id"], task_id=ids["task_id"], agent_id=case["agent_id"],
                            subject=case["subject"], task_type=case["task_type"], original_response=text, response_sha256=sha256_text(text),
                            supplied_texts=supplied_texts(case), claims=claims, created_at=utc_now_rfc3339())
