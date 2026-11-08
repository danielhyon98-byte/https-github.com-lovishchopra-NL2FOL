"""The STEM front end's checks decided by the engine, for a text: ``decide``, ``holds`` and ``failing``.

Copied from the translator's tests (``tests/stem/test_stem_repair5.py``, the same three helpers and their constants) when
the overseer became a separate sub-project, so its suite runs on its own; ``test_subproject_layout.py`` keeps the copy
equal to the translator's while both live in one repository.
"""
from __future__ import annotations

from epinoic_logic.engine import SolverConfig
from epinoic_logic.engine.policies import policy_config, policy_limits
from epinoic_logic.engine.runner import verify
from epinoic_logic.ir.schema import Problem
from epinoic_logic.stem import build_document, clear_document_cache
from epinoic_logic.stem.checks import build_checks

CFG = SolverConfig(timeout_ms=8000, memory_max_mb=None)
HOLDS = {"bool": "UNSATISFIABLE"}


def decide(text: str, request, profile: str, data: tuple = ()):
    clear_document_cache()
    doc = build_document(text, request, profile, **({"data": data} if data else {}))
    plan = build_checks(doc, report_id="r", request_id="q")
    checks = [(pc.relation_kind, verify(Problem.model_validate(pc.problem), policy_config(pc.policy, CFG), limits=policy_limits(pc.policy)).status.value,
               pc.failure_severity, pc.description) for pc in plan.checks]
    return checks, [(f.code, f.severity, f.message) for f in list(doc.findings) + list(plan.findings)]


def holds(check) -> bool:
    kind, status = check[0], check[1]
    return status == HOLDS.get(kind, "ENTAILED") or (kind != "bool" and status == "SATISFIABLE")


def failing(checks) -> list:
    return [c for c in checks if not holds(c)]
