"""Epinoic AI logic translator and Z3 verification engine.

A definitive result proves a property of the ENCODED problem under its ENCODED
premises. It never establishes that the premises are factually true or that a
natural-language claim was translated faithfully. See
``epinoic_logic.engine.statuses.SCOPE_STATEMENT``.
"""
from .version import ENGINE_VERSION, IR_VERSION, POLICY_VERSION, TRANSLATOR_VERSION

__all__ = ["ENGINE_VERSION", "IR_VERSION", "POLICY_VERSION", "TRANSLATOR_VERSION"]
