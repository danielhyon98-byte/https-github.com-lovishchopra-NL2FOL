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

The completion entry point `providers.base.CompletionProvider` (`complete(system, user, *,
prompt_version) -> ProviderResponse`) is the public form of the `_complete` the vendor adapters
already use: the caller supplies both texts and the provider adds nothing, while retries,
timeouts, `ProviderInfo` (which records `prompt_version`) and `ProviderError` are reused
unchanged. Both vendor adapters implement it; `propose` and `review` are unchanged. The overseer
agent runner (`epinoic_logic.overseer.runner`) calls it with a knowledge pack's system text and one
dossier, and its reply is untrusted data parsed only by the verdict intake.
`FixtureCompletionProvider` serves canned replies keyed by dossier digest or in order, raises a
canned `ProviderError` and records every call; no live provider is claimed.

`grounding.py` locates a quotation in tiers (verbatim; typographic normalisation, with
quote marks folded and verse line breaks written as slashes; an elision within the window;
then the form-difference tier: an initial capital, a line-break mark, diacritics folded
with NFKD and combining marks dropped, a long elision). An elision mark written in the academic form, in brackets or
parentheses (`[...]`, `[…]`, `[ . . . ]`, `(...)`), is read as the same ellipsis in every tier (`unbracket_elisions`), so
a correct elided quotation is never reported as invented. A form difference never verifies a
grounding but is reported as one ("differs in form", the channel's INT-REQ-010), never as an
invented quotation; accents encoded differently (precomposed against combining) are the same
letters and a normalised match. Each supplied text's normalised forms and offset maps are
built once and cached per `(document_id, sha256 of the text)` in a bounded LRU
(`TextForms`, `text_forms`), and every locating answer is memoised per excerpt and text, so
a parse and its checks never locate one excerpt in one document twice; the caches are
thread-safe and `clear_grounding_caches()` empties them. Hashing agent text never raises: `contracts.sha256_text`
(like `ir.canonical.sha256_hex` and the grounding cache's `text_sha256`) encodes a lone UTF-16 surrogate with
`surrogatepass`, so valid text hashes exactly as before and the channel can refuse such text (INT-REQ-009) instead of
raising.

**Overseen like every other agent.** Every translation this package proposes reaches the router inside a receipt
outcome, and the Overseer re-checks it from its journal as untrusted data (`epinoic_logic.overseer.checks.translation`,
codes `OVS-TRN-001` to `OVS-TRN-007`): the IR re-validated with the engine's validator, the status and eligibility
re-derived, the quotation groundings re-run against the supplied texts, every quotation and number traced to the
specialist's report, a conclusion found among its own premises flagged as circular, the outcome summary regenerated from
the signed result. The signed task audit records each translation (claim text, proposed IR, validation outcome, signed
result). Nothing in this package changed for it: the checks only read what the pipeline already records.
