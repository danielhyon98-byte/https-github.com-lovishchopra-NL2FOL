"""Deliver a development case of ``tests/data/argdiag_dev_cases.json`` to the hub as raw text, as the router does, and read
the receipt: the helper of the STEM argument-diagnosis tests (ST-REF-001 to ST-SCOPE-002, the B2 classes).

Nothing here is a test. The cases are data (``tests/argdiag_cases.py``); the answer can be replaced by a variant of it, so a
test can set a wrong twin beside a correct answer.
"""
from __future__ import annotations

from typing import Optional

from epinoic_logic.branches import RouterHub
from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.integrity import WorkPlan
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document
from epinoic_logic.stem.checks import build_checks

from .. import argdiag_cases as C

KEY = b"argdiag-stem-test-key-0123456789abcdef"
CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)


def deliver(case_or_id, *, answer: Optional[str] = None, request: Optional[str] = None):
    """The receipt of the case's answer (or ``answer``) delivered as text for the case's request (or ``request``)."""
    case = C.load_case(case_or_id) if isinstance(case_or_id, str) else case_or_id
    hub = RouterHub(signing_key=KEY, config=CFG)
    plan = WorkPlan(**C.work_plan_fields(case))
    hub.open_task(plan)
    msg, _req, _rq = hub.dispatch(plan.task_id, case["agent_id"], request if request is not None else case["request"], C.supplied_texts(case))
    _reply, rc = hub.receive(plan.task_id, msg.message_id, answer if answer is not None else case["answer"], agent_id=case["agent_id"],
                             report_id=case["ids"]["report_id"])
    return rc


def structural(rc, code: str) -> list:
    return [f for f in rc.structural_findings if f.code == code]


def findings(rc, code: str) -> list:
    return [f for f in rc.findings if f.code == code]


def failed_checks(rc) -> list:
    return [c for c in rc.formal_checks if c.satisfied is False]


def flagged(rc) -> list:
    """Every warning or error the receipt carries (integrity and structural findings, failed checks), as ``(code, severity)``."""
    out = [(f.code, f.severity) for f in rc.findings if f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.structural_findings if f.severity in ("warning", "error")]
    out += [(c.constraint_id, "failed") for c in failed_checks(rc)]
    return out


def stem_flags(rc) -> list:
    """The warnings and errors of the STEM front end and checks: ST-* structural findings, INT-SUBJ-001/004 and failed STEM
    checks (a control's other findings, such as a request item the coverage heuristic misses, are not the STEM checker's)."""
    out = [(f.code, f.severity) for f in rc.structural_findings if f.code.startswith("ST-") and f.severity in ("warning", "error")]
    out += [(f.code, f.severity) for f in rc.findings if f.code in ("INT-SUBJ-001", "INT-SUBJ-004")]
    out += [(c.constraint_id, "failed") for c in failed_checks(rc) if c.constraint_id.startswith("stem-")]
    return out


def decide(pc) -> Optional[bool]:
    """A planned STEM check run by the engine: True when it gives the status expected of sound work (and no vacuity
    diagnostic), False when it gives another verdict, None when it gives none."""
    res = verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy), diagnose=False)
    status = res.status.value
    if status == pc.expected_if_sound and not any(d.code == "E108" for d in res.diagnostics):
        return True
    if status in ("ENTAILED", "COUNTEREXAMPLE", "CONSISTENT", "SATISFIABLE", "UNSATISFIABLE") or (status == "INCONSISTENT_PREMISES" and pc.inconsistent_is_failure):
        return False
    return None


def plan(text: str, request: Optional[str] = None, profile: str = "physics"):
    """The STEM document and check plan of ``text`` (as the STEM pack builds them for a report)."""
    doc = build_document(text, request, profile)
    return doc, build_checks(doc, report_id="r", request_id="q")


def decided(text: str, request: Optional[str] = None, profile: str = "physics") -> dict:
    """``check id -> (planned check, decide(check))`` for every check of ``text``."""
    _doc, p = plan(text, request, profile)
    return {pc.check_id: (pc, decide(pc)) for pc in p.checks}
