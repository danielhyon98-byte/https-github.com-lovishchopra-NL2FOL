# translate — from specialist claims to IR

Flow for one claim: `eligibility.decide_eligibility` (deterministic rules by claim
role and proposed kind) → `subjects.resolve_profile` applies the IB subject policy
(a class the subject does not allow is downgraded to not eligible) → the
`Translator` in `pipeline.py` builds a `TranslationRequest` (claim, supporting
claims, supplied texts, eligibility, subject profile text) → a `TranslationProvider`
proposes JSON → `parsing.parse_json_object` (strict) → `Problem.model_validate` and
the engine validator → `grounding.check_problem_grounding` marks quotation
groundings verified or not → status TRANSLATED, AMBIGUOUS_TRANSLATION,
UNSUPPORTED, INVALID_FORMALIZATION, NOT_ELIGIBLE or TRANSLATION_FAILED.

`review.py` runs an independent, advisory semantic-fidelity review. `outcome.py`
composes the Overseer-facing `ClaimVerificationOutcome` (display status derived
from the signed engine result; summary ends with the scope statement) and offers
`verify_claim` as the one-call path translate → verify → review → compose.

`providers/` holds the provider interface, a fixture provider for tests, and
Anthropic / OpenAI-compatible adapters (implemented, untested live). `prompts/`
holds versioned prompt texts; the version string is bound into each result.
