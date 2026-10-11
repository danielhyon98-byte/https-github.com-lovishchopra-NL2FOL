"""Default branch registry: which subjects route to which branch, with which packs."""
from __future__ import annotations

from .base import BranchRegistry, SubjectBranch
from .packs import BusinessPack, CorePack, EconomicsPack, EnglishPack, GenericPack, HistoryPack, PsychologyPack


class _EnglishParserWrapper:
    """Adapts the agent-written English adapter (module-level parse_response) to the branch
    parser protocol. The hub-stated ``agent_id`` is passed through unchanged: the report
    names who actually answered, so the channel's identity checks (INT-REQ-001,
    INT-HANDOFF-002) can compare it with the request and the plan."""
    agent_id = "english-specialist"

    def parse_response(self, text, *, request_id, task_id, report_id, subject, task_type, supplied_texts=(), course_level="unknown", agent_version=None, agent_id=None):
        from ..adapters.english_specialist.parser import parse_response
        return parse_response(text, request_id=request_id, task_id=task_id, report_id=report_id, subject=subject, task_type=task_type,
                              supplied_texts=list(supplied_texts), course_level=course_level, agent_version=agent_version,
                              agent_id=agent_id or self.agent_id)


def _english_parser():
    try:
        import epinoic_logic.adapters.english_specialist.parser  # noqa: F401
        return _EnglishParserWrapper()
    except Exception:
        from .generic_parser import GenericTextParser
        return GenericTextParser(agent_id="english-specialist")


def _history_parser():
    from ..adapters.history_specialist.parser import HistorySpecialistAdapter
    return HistorySpecialistAdapter()


def _generic_parser(agent_id: str):
    def make():
        from .generic_parser import GenericTextParser
        return GenericTextParser(agent_id=agent_id)
    return make


CORE = CorePack()

BRANCHES = [
    SubjectBranch(key="english", display_name="Studies in Language and Literature", profile_keys=("english_a_literature", "english_a_language_literature", "literature_performance", "language_a_other", "english"),
                  parser_factory=_english_parser, packs=(CORE, EnglishPack()), notes="Device-Interpretation-Effect inside Point-strand-Link; quotation integrity is the central check."),
    SubjectBranch(key="history", display_name="History and argued humanities", profile_keys=("history", "global_politics"),
                  parser_factory=_history_parser, packs=(CORE, HistoryPack()), notes="Claim-Evidence-Analysis-Judgement-Link; dates and figures checked for exact consistency and chronology."),
    SubjectBranch(key="psychology", display_name="Psychology", profile_keys=("psychology",),
                  parser_factory=_generic_parser("psychology-specialist"), packs=(CORE, PsychologyPack()), notes="Claim-Study-Link-Evaluation; study attributions need grounding."),
    SubjectBranch(key="economics", display_name="Economics", profile_keys=("economics",),
                  parser_factory=_generic_parser("economics-specialist"), packs=(CORE, EconomicsPack()), notes="Define-Model-Mechanism-Apply-Evaluate; elasticity and percentage arithmetic decided by the engine."),
    SubjectBranch(key="business_management", display_name="Business Management", profile_keys=("business_management",),
                  parser_factory=_generic_parser("business-specialist"), packs=(CORE, BusinessPack()), notes="Define-Apply-Analyse-Evaluate; ratios and margins decided by the engine."),
    SubjectBranch(key="generic", display_name="Generic (any other subject)", profile_keys=("unknown",),
                  parser_factory=_generic_parser("specialist"), packs=(CORE, GenericPack()), notes="Shared hub integrity plus numeric self-consistency; subject pack to be added."),
]


def default_registry() -> BranchRegistry:
    return BranchRegistry(BRANCHES, default_key="generic")
