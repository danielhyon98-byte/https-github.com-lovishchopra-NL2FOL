# `selfcert_label`: the block-only meaning label (stage 1, not wired)

This package builds the meaning label of the self-certification class, as the owner approved it on 25 November (decision 1,
and the acceptance rule L2). The rule it serves is unchanged: when an answer makes a claim about its OWN checking,
verification, review, testing, quality or correctness, that claim must never help the answer be delivered, selected or
labelled.

The label reads one answer at a time, one sentence at a time, and can only withhold. The gate it is built for is
`reader OR validated label`. The rule reader (`epinoic_logic.selfcert`) stays, and either one can withhold.

## Status

- **Not yet wired.** No release path calls this package. The channel, hub, service, overseer, engine and translator are
  unchanged, and so is every delivery decision. Stage 2 wires the label into every release path, with the faithful fake for
  existing tests. Stage 2 also records labels, bumps the versions and measures against the approved bounds.
- **No provider is called.** Nothing here imports a provider SDK or opens a network connection. `ProviderLabeller` calls a
  transport that the deployment injects. In this stage every label is scripted in tests or made by the faithful fake.
- **The model** is recorded only as the SHA-256 of its configured identifier (`model_digest`), never by name.

## What it does

| Part | Module | What |
| --- | --- | --- |
| Input | `scope.py`, `inputs.py` | The answer's own sentences, numbered `s1`…`sn`, each with its place ("paragraph 3, sentence 2"). Invisible characters are removed, with an offset map (a white-space control becomes a space); delimiter runs are substituted after that removal. Code locates placeholders verbatim, and only inside quotation marks: `⟦source S1⟧`, `⟦task⟧`, and `⟦student 1⟧` in marking tasks. Certification wording becomes a placeholder only inside a relay frame; a quotation the answer asserts as its own stays visible. Input that is not a string, or an unknown writer, is `unavailable` (`label-failed`). The context block comes from the router's request only: writer, subject, task type, marking, whether a true-or-false item is asked, and at most 10 known-source titles. Chunks hold at most 8,000 characters or 120 sentences; more than 6 chunks is `oversized`. `build_input(raw_text, request, key=...)` renders byte-identical requests for the same inputs. |
| Canaries | `canaries.py`, `canaries.json` | 1 or 2 positive canaries per request, drawn from classes (language × family × form × evaluator × scope) by an HMAC of the issue id. Their positions are keyed too. The key is a deployment secret in production, a separate recording key offline, and a fixed key in tests. A negative canary appears in a keyed 10% of requests and is recorded for drift only. |
| Rendering | `render.py` | The system text is `prompt.md` (written and frozen by the prompt author; code never edits it). The user text holds JSON data blocks. Each marker carries the first 16 hex digits of the SHA-256 of the blocks. The answer's own `<<<`, `>>>`, `⟦` and `⟧` are replaced by fixed substitutes, and each marker is asserted to occur exactly once. |
| Validation | `validate.py`, `anchor.py`, `exempt.py`, `schema.json` | Validation is pure and linear. It runs in this order: size and stop reason; strict JSON (duplicate keys, depth over 6 and non-finite numbers are malformed; at most one code fence is stripped); shape (`schema.json`; `none` carries `"spans": []`, the frozen prompt's form); canaries; anchoring under the reader's visible form, with offsets mapped back; then the seven code exemptions, each recorded. An anchor word or a STATUS form in the span overrides any exemption, and a quote that occurs more than once is exempt only when every occurrence is. Only `(sentence, start, end, category)` survives. |
| Results | `record.py` | The states are `named`, `none_named`, `unavailable` (with its kind) and `skipped`. `findings(codes)` gives one finding per named sentence or one with its kind, with the receipt code its caller gives for the state; the package names no receipt code of its own. Stage 2 names INT-SELF-001 and INT-SELF-002 in the channel together with the overseer's code tables (`emitted.py`) and pack, so a code the translator names is never unknown to the overseer. A state that gives a finding refuses a missing code (`ValueError`); it never returns no finding. The record holds the input key, the label version and digest, the model digest, the raw replies, the validated offsets, the exemptions, the canary outcome, the state and the attempts. Every record carries a `seal` (the SHA-256 of the rest of it). `revalidate` recomputes a record from its raw replies, checks the seal, the writer and the configured model's digest (when given), and names every field that differs. |
| Labellers | `labellers.py` | `UnconfiguredLabeller` is the default; every call is unavailable with kind `not-configured`. Also here: `ProviderLabeller` (with an injected transport), `RecordedLabeller` (an unrecorded key, or a recording that names no model or another model, gives `not-recorded`), `CachingLabeller` (an LRU of 4,096 successes; failures are never cached), `BudgetedLabeller`, and `CircuitBreakerLabeller` (5 consecutive provider failures pause calls for 60 s, and health reports `degraded`). Each chunk gets at most one retry, with fresh canaries, inside `min(15 s, deadline − now − 2 s)`; the labeller bounds each call itself, and a reply after that bound is a `timeout`. |
| Fakes | `fakes.py` | `ReaderBackedLabeller` is the faithful fake. It names every canary and every span the rule reader hits, so the union equals the reader. `ScriptedLabeller` serves replies scripted by a test. Neither fake is for production, and neither ever measures the label. |
| Identity | `__init__.py` | `LABEL_VERSION = "selfcert-label-1"`. `label_digest()` is a SHA-256 over the version, `prompt.md`, `schema.json`, `canaries.json`, `exemptions.json`, every `.py` of the package, and `selfcert.rules_digest()`. `tests/selfcert_label/test_identity.py` pins `(LABEL_VERSION, label_digest())` together (T17): a digest change without a version bump fails. |

## What it never does

- It never releases, selects or labels an answer. It never raises a status or writes a success word.
- No label text reaches the IR, the compiler, Z3, a receipt message, a reason, feedback, a log or a payload. A quote
  survives only inside the raw reply in the record. Findings name places and families, never words.
- It never shows `none_named` to anyone as a pass. `none_named` allows nothing by itself.
- It never turns a failure of any kind into `none_named`. Not configured, provider error, timeout, budget, malformed,
  incomplete, control, oversized, truncated, label code exception and not recorded are all `unavailable`.
- It never removes a reader hit. The label is asked only about answers the reader passed.

## Results prove properties of the encoding only

A validated label is the reading of one model on one rendered request. It lowers the miss rate of the reader; it cannot
prove the miss rate zero. Every rate is measured on sets the label never saw (design 3.6), and the measurement binds the
pair (label digest, model digest).

## Tests

`tests/selfcert_label/` holds the package tests of design 3.3 (T2 to T5, T7 to T15, T17, T20, T23), and `test_attack16.py` pins the findings of label-attack round 16. Each has its expected value
fixed in the test. Run them with `python -m pytest -q tests/selfcert_label`.
