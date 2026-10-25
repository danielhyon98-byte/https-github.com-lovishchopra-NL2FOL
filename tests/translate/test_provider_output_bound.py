"""Provider output over the parsing bound (``parsing.MAX_PROVIDER_TEXT_BYTES``, 64 KiB) is refused before it is parsed, and
the translation is TRANSLATION_FAILED with no retry: the provider failed to give a usable output, and a retry would ask for
the same thing again (security fix SEC-3, the pipeline half). Output within the bound is parsed as before."""
from __future__ import annotations

import json

from epinoic_logic.translate.contracts import TranslationStatus as T
from epinoic_logic.translate.parsing import MAX_PROVIDER_TEXT_BYTES
from epinoic_logic.translate.pipeline import Translator
from epinoic_logic.translate.providers.fixture import FixtureTranslationProvider

from ..contract.helpers import CFG, make_report, output, speed_problem


def _translate(raw: str):
    claim, report = make_report("The speed is 15 km/h.")
    provider = FixtureTranslationProvider({claim.claim_id: raw})   # it keeps every request it is asked in ``calls``
    return Translator(provider, config=CFG).translate(claim, report), provider


def test_output_over_the_bound_fails_the_translation_with_no_retry():
    raw = json.dumps(output(speed_problem())) + " " * (MAX_PROVIDER_TEXT_BYTES + 1)
    result, provider = _translate(raw)
    assert result.status is T.TRANSLATION_FAILED and result.problem is None
    assert len(provider.calls) == 1 and result.provider.attempts == 1
    assert any("provider output too large" in d for d in result.diagnostics)


def test_control_output_within_the_bound_is_parsed_as_before():
    raw = json.dumps(output(speed_problem()))
    assert len(raw.encode("utf-8")) <= MAX_PROVIDER_TEXT_BYTES
    result, provider = _translate(raw)
    assert result.status is T.TRANSLATED and len(provider.calls) == 1


def test_control_malformed_output_within_the_bound_is_still_retried():
    result, provider = _translate("this is not JSON")
    assert result.status is T.INVALID_FORMALIZATION and len(provider.calls) == 2
