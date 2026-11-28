# `selfcert_label`: the block-only meaning label (stage 2a: wired, no label recorded)

This package builds the meaning label of the self-certification class, as the owner approved it on 25 November (decision 1,
and the acceptance rule L2). The rule it serves is unchanged: when an answer makes a claim about its OWN checking,
verification, review, testing, quality or correctness, that claim must never help the answer be delivered, selected or
labelled.

The label reads one answer at a time, one sentence at a time, and can only withhold. The gate it is built for is
`reader OR validated label`. The rule reader (`epinoic_logic.selfcert`) stays, and either one can withhold.

## Status

- **Wired with the unconfigured default: every answer the reader passes is withheld until labels are configured; no label is
  recorded or measured yet.** Wired into every release path (stage 2a). The hub and channel label at `respond` and
  `relay`, the service submits at step 4 and decides KIT-DL-006 or KIT-DL-014, and every overseer release path calls `label_gate` (meaning-check design
  2.5.1 and 2.5.7); the arena replays with `--labeller`. The engine, the translator, the flash router and the combinator
  sub-project never call it. The production default stays `UnconfiguredLabeller`, so a deployment with no labeller withholds
  every answer the reader passes. The test suites install the faithful fake, which names exactly what the rule reader names,
  so every existing delivery decision is unchanged under it. No label is recorded and nothing is measured in this stage:
  stage 2b records labels with deployed agents and measures them against the approved bounds.
- **No provider is called.** Nothing here imports a provider SDK or opens a network connection. `ProviderLabeller` calls a
  transport that the deployment injects. In this stage every label is scripted in tests or made by the faithful fake.
- **The model** is recorded only as the SHA-256 of its configured identifier (`model_digest`), never by name.
- **The record's seal is a content hash, not a signature.** `seal` is the SHA-256 of the rest of the record. It shows a change
  made by anyone who does not recompute it, and re-validation recomputes everything it can from the stored raw replies. It
  does not stop a deliberate forger who re-seals an edited record: integrity against deliberate forgery comes from the channel
  journal, which holds the record in `ChannelEvent.label_json` beside the SHA-256 of the text it labelled (owner R4).

## Stage 2a: what the release paths use

- **The default labeller** (interface (a)). A release path that is given no labeller calls `default_labeller()` at use time,
  never a name bound at import. `set_default_labeller(labeller)` is the one switch: it returns what it replaced, and `None`
  (or `restore_default_labeller()`) restores the production default, `UnconfiguredLabeller`. With that default every answer
  the reader passes is withheld as `unavailable` (`not-configured`). `using_default_labeller(labeller)` installs one for a
  block. The test suite installs the faithful fake through this switch in `tests/conftest.py`; production code never calls it.
- **Submission** (interface (e)). `labeller.submit(raw_text, request, *, writer, deadline)` returns a `LabelHandle`, and
  `labeller.result(handle)` collects it. A calling labeller joins a module-level in-flight table. The table is keyed on the
  rendered request (bound to the input key), the model digest, the canary key's fingerprint and the labeller's share scope. So
  the service's step-4 submit and the hub's later submit of the same answer make one call, even through two
  `default_labeller()` instances. Successes are kept in a module-level LRU of 4,096 entries; failures never are. A shared
  flight or a cached success costs no budget. Provider labellers share by model; the faithful fake shares by its key. A
  scripted fake shares with itself only, and so does a recorded labeller unless it is given a `share_scope`. A provider
  labeller starts the call at submission on a worker thread, so the wait overlaps the translation; every other labeller
  computes when the result is first collected. A handle whose result is never collected costs nothing more. Each call keeps
  its one retry, with fresh canaries, inside `min(15 s, deadline - now - 2 s)`.
- **Re-validation** (interface (c)). `labeller.revalidate_record(record, raw_text, request)` re-validates a stored record with
  the labeller's own canary key and model digest. The model digest is always bound, so a record of another model is a
  mismatch. `UnconfiguredLabeller`, and a labeller with no model digest, never re-validate anything: a record is never read
  as clean for want of a labeller.
- **Bounded work at the oversized cap.** The own scope stops being built once it is oversized whatever follows: more than
  45,600 characters of segment text, or more than 720 segments (6 chunks of 7,600 characters or 120 sentences). A 2 MB
  answer is refused as `oversized`, with no call, well within T23's bound. The cap changes no reading.
- **T24** (`t24.py`). `check_t24(receipt)` returns the invariant's violations for a transmission receipt, a delivery
  receipt, a delivered answer or a channel event:
  - no label-derived text carries a success word;
  - no label field reaches a Problem;
  - no status is raised;
  - a delivered payload equals the specialist's bytes.

  `tests/conftest.py` applies it to everything the suite produces, through one session-level hook. A test that builds a
  violation on purpose carries the marker `t24_expected_violation` and asserts the detection itself.

## What it does

| Part | Module | What |
| --- | --- | --- |
| Input | `scope.py`, `inputs.py` | The answer's own sentences, numbered `s1`…`sn`, each with its place ("paragraph 3, sentence 2"). Invisible characters are removed, with an offset map (a white-space control becomes a space); delimiter runs are substituted after that removal. Code locates placeholders verbatim, and only inside quotation marks: `⟦source S1⟧`, `⟦task⟧`, and `⟦student 1⟧` in marking tasks. Certification wording becomes a placeholder only inside a relay frame; a quotation the answer asserts as its own stays visible. Input that is not a string, or an unknown writer, is `unavailable` (`label-failed`). The context block comes from the router's request only: writer, subject, task type, marking, whether a true-or-false item is asked, and at most 10 known-source titles. Chunks hold at most 8,000 characters or 120 sentences; more than 6 chunks is `oversized`. `build_input(raw_text, request, key=...)` renders byte-identical requests for the same inputs. |
| Canaries | `canaries.py`, `canaries.json` | 1 or 2 positive canaries per request, drawn from classes (language × family × form × evaluator × scope) by an HMAC of the issue id. Their positions are keyed too. The key is a deployment secret in production, a separate recording key offline, and a fixed key in tests. A negative canary appears in a keyed 10% of requests and is recorded for drift only. |
| Rendering | `render.py` | The system text is `prompt.md` (written and frozen by the prompt author; code never edits it). The user text holds JSON data blocks. Each marker carries the first 16 hex digits of the SHA-256 of the blocks. The answer's own `<<<`, `>>>`, `⟦` and `⟧` are replaced by fixed substitutes, and each marker is asserted to occur exactly once. |
| Validation | `validate.py`, `anchor.py`, `exempt.py`, `schema.json` | Validation is pure and linear. It runs in this order: size and stop reason; strict JSON (duplicate keys, depth over 6 and non-finite numbers are malformed; at most one code fence is stripped); shape (`schema.json`; `none` carries `"spans": []`, the frozen prompt's form); canaries; anchoring under the reader's visible form, with offsets mapped back; then the seven code exemptions, each recorded. An anchor word or a STATUS form in the span overrides any exemption, and a quote that occurs more than once is exempt only when every occurrence is. Only `(sentence, start, end, category)` survives. |
| Results | `record.py` | The states are `named`, `none_named`, `unavailable` (with its kind) and `skipped`. `findings(codes)` gives one finding per named sentence or one with its kind, with the receipt code its caller gives for the state; the package names no receipt code of its own. Stage 2 names INT-SELF-001 and INT-SELF-002 in the channel together with the overseer's code tables (`emitted.py`) and pack, so a code the translator names is never unknown to the overseer. A state that gives a finding refuses a missing code (`ValueError`); it never returns no finding. The record holds the input key, the label version and digest, the model digest, the raw replies, the validated offsets, the exemptions, the canary outcome, the state and the attempts. Every record carries a `seal` (the SHA-256 of the rest of it). `revalidate` recomputes a record from its raw replies, checks the seal, the writer and the configured model's digest (when given), and names every field that differs. |
| Labellers | `labellers.py` | `UnconfiguredLabeller` is the default; every call is unavailable with kind `not-configured`. Also here: `ProviderLabeller` (with an injected transport), `RecordedLabeller` (an unrecorded key, or a recording that names no model or another model, gives `not-recorded`), `CachingLabeller` (an LRU of 4,096 successes; failures are never cached), `BudgetedLabeller`, and `CircuitBreakerLabeller` (5 consecutive provider failures pause calls for 60 s, and health reports `degraded`). `default_labeller()`, `set_default_labeller()` and the shared submission (in-flight table and cache of successes) are described above. Each chunk gets at most one retry, with fresh canaries, inside `min(15 s, deadline − now − 2 s)`; the labeller bounds each call itself, and a reply after that bound is a `timeout`. |
| Fakes | `fakes.py` | `ReaderBackedLabeller` is the faithful fake. It names every canary and every span the rule reader hits, so the union equals the reader. `ScriptedLabeller` serves replies scripted by a test. Neither fake is for production, and neither ever measures the label. |
| Identity | `__init__.py` | `LABEL_VERSION = "selfcert-label-2"` (selfcert-label-1 was committed in stage 1, so the package's stage-2 change took a new version). `label_digest()` is a SHA-256 over the version, `prompt.md`, `schema.json`, `canaries.json`, `exemptions.json`, every `.py` of the package, and `selfcert.rules_digest()`. `tests/selfcert_label/test_identity.py` pins `(LABEL_VERSION, label_digest())` together (T17): a digest change without a version bump fails. |

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

`tests/selfcert_label/` holds the package tests of design 3.3 (T2 to T5, T7 to T15, T17, T20, T23, T24), and `test_attack16.py` pins the findings of label-attack round 16. Stage 2a added `test_default_labeller.py`, `test_submission.py`, `test_revalidate_record.py`, `test_oversized_cap.py` and `test_t24.py`. Each has its expected value
fixed in the test. Run them with `python -m pytest -q tests/selfcert_label`.
