# translate — from specialist claims to IR

Flow for one claim: `eligibility.decide_eligibility` (deterministic rules by claim
role and proposed kind) → `subjects.resolve_profile` applies the IB subject policy
(a class the subject does not allow is downgraded to not eligible) → the
`Translator` in `pipeline.py` builds a `TranslationRequest` (claim, supporting
claims, supplied texts, eligibility, subject profile text) → a `TranslationProvider`
proposes JSON → `parsing.parse_json_object` (strict) → `Problem.model_validate` and
the engine validator → `grounding.check_problem_grounding` marks quotation
groundings verified or not → stated figures: a premise that only defines an atom by a
comparison of a figure no other premise mentions (`b <-> (n = 17)` with `n` free) asserts
nothing, so when the conclusion fails only on such a figure (the engine's `E110`: the
COUNTEREXAMPLE turns ENTAILED once the defined atoms are asserted) the output is
INVALID_FORMALIZATION with that diagnostic, fed back once, ambiguous or not; otherwise the
unasserted definitions are recorded as a note, and an ambiguity flag that says the figure "is
encoded" (a literal equality) is named as not matching the IR → circularity: an encoding whose
premises restate its conclusion from the writer's own assertions (the engine's `E112`) is
INVALID_FORMALIZATION, fed back once → stated precision: a figure written to n places states its
value to half a unit of its last place (`widen_rounded_literals` reads each decimal literal as that
interval, "-0.67" as [-0.675, -0.665)), so an encoding that is INCONSISTENT_PREMISES or a
COUNTEREXAMPLE as written and ENTAILED or CONSISTENT once its rounded figures are so read is
INVALID_FORMALIZATION ("stated precision: ..."), fed back once; a wrong rounded figure stays wrong → a
conclusion label that states a figure its expression does not check (no literal of the conclusion, to
its stated precision or as a percentage, and no gloss of its symbols states it) is recorded as a note
(`label_beyond_expression`) and shown beside the label in the outcome summary; the verdict is unchanged →
status TRANSLATED, AMBIGUOUS_TRANSLATION, UNSUPPORTED, INVALID_FORMALIZATION, NOT_ELIGIBLE or
TRANSLATION_FAILED. `outcome.display_status_for` displays a definitive result carrying `E108`
(vacuous), `E110` (unasserted figure), `E111` (unencoded reason) or `E112` (circular) as
INVALID_FORMALIZATION, never as a verdict; an AMBIGUOUS_TRANSLATION's result is described as the
translator's chosen encoding of one reading, run for inspection.

Eligibility counts figures on `eligibility.figure_text`: mark annotations ("[2]", "[2 marks]"), part
labels ("(a)", "(iii)", "Part (b)") and named items ("Paper 1") are not figures, so a heading is not
a quantitative claim. Evidence is a QUANTITATIVE_CLAIM only with two related figures or a
comparative; a single date or figure is not (its only encoding would restate it).

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
quote marks folded, every dash variant read as one dash with the spaces on both sides of it dropped, in the text and
the excerpt alike, so `like - just as I -` typed for the poem's `like—just as I—` is the same quotation, and verse line
breaks written as slashes; an elision within the window; then the form-difference tier: an initial capital, a line-break
mark, the text's own double speech mark at a line or stanza start or end left out of a quotation that runs across the
break, with ` / `, ` // ` or no break mark (every stanza of 'The Man He Killed' opens with one: "omits the text's own
speech mark at a line or stanza start or end"), diacritics folded with NFKD and combining marks dropped, a long
elision). An elision mark written in the academic form, in brackets or
parentheses (`[...]`, `[…]`, `[ . . . ]`, `(...)`), is read as the same ellipsis in every tier (`unbracket_elisions`), so
a correct elided quotation is never reported as invented. A located excerpt verifies a premise only when it states the premise's figures (the figures of its
literals; 0, ±1, 10, 100, 1000 and fractions aside): a premise `it1 = 3` grounded in "scores = [12, 19, 23" is not verified
(`GroundingCheck.method` `figures_in_excerpt`). A form difference never verifies a
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
codes `OVS-TRN-001` to `OVS-TRN-009`): the IR re-validated with the engine's validator, the status and eligibility
re-derived, the quotation groundings re-run against the supplied texts, every quotation and number traced to the
specialist's report, a conclusion found among its own premises flagged as circular, the outcome summary regenerated from
the signed result, and two receipt-level warnings (a definitive display resting on unsuccessful sibling claims; one fact
a premise in one translation and unsupported in another). No check depends on who proposed the IR: a problem this
pipeline produced always records its provider, and one that records none is reported unless the operator declared its
translator hand-built. The signed task audit records each translation (claim text, proposed IR, validation outcome, signed
result). Nothing in this package changed for it: the checks only read what the pipeline already records.
