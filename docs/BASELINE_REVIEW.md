# Baseline review: Epinoic logic translator (2026-10-12)

This review covers four things:
- it identifies the code to be established in `Bruno-ios/Epinoic-Logic-Translator`;
- it records the checks actually run on that code;
- it states the code's current behaviour and limits;
- it recommends one small next milestone.

It describes code that exists. It does not propose a redesign.

## 1. Baseline

| Item | Value |
| --- | --- |
| Baseline commit | `3147d08e0aa63d5eeaceb1072754f29e3862164d` ("Fix the r5 arena overseer findings", 2026-10-11 22:04 UTC) |
| Published at | `https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL`, branch `claude/z3-verification-engine-plan-nk3luq` |
| History | 47 commits from root `b18f06c` (2026-10-11), all made in Claude Code sessions for Daniel |
| Licence | Proprietary (`LICENSE`, Epinoic AI) |
| Package | `epinoic-logic` 0.1.0; IR 1.0, engine 0.2.0, policy 2026.10-v2, translator 0.2.0 |

**History and the NL2FOL name.** The source repository is named after NL2FOL, but this branch
does **not** share Git history with NL2FOL:
- Its root commit has no parent, and the first commit is this project's own skeleton.
- No NL2FOL code, prompts or data are included.
- NL2FOL is credited as design inspiration only, in `THIRD_PARTY_NOTICES.md`.

So only this branch should be imported. Whatever the source repository's other branches
contain is not part of the translator.

**Target repository status.** `Bruno-ios/Epinoic-Logic-Translator` has not been inspected or
written to yet. This session was not permitted to attach that repository, so its current
contents are unverified. The import steps are in section 7.

## 2. Who is editing this source

- **Claude Code automation** (in this session) was editing this branch until 2026-10-12. It is
  now paused.
- **Work after the baseline is not part of the baseline:**
  - **Partial round-6 fixes.** These were edited in the main checkout when the automation hit
    an account spend limit. They are unverified, preserved in a separate commit after this
    review, and labelled as work in progress.
  - **Two local, unpublished branches:**
    - `stem-build` (`343d8ae`): STEM support, design, corpus, maths front end;
    - `overseer-build` (`1178500` plus uncommitted hook edits): overseer agents and transfer
      audit.

    Neither has passed its own audits. Both exist only in the session's container. They need
    to be pushed somewhere durable, or they will be lost when the container is reclaimed.
- **Daniel:** no commits by Daniel appear on this branch.

## 3. Credentials and unintended artifacts

- **Credential patterns:** every revision of the branch's history was searched for AWS,
  Anthropic, OpenAI, GitHub and Slack token formats and for private-key headers. The search
  printed paths only. **No match.**
- **Key-like assignments of literal strings:** three lines matched. One is an environment
  variable *name* (`translate/providers/openai_compatible.py`). Two are test-only fixture
  tokens (`tests/service/conftest.py`, `tests/service/test_overseer_round1.py`). None is a
  credential.
- **Tracked files:** there are 240. None is a binary, wheel, archive, bytecode, virtualenv or
  `build/` output.
- **Committed generated files:** these are deliberate:
  - measured stress results in `tests/stress/results/*.json`;
  - the QA corpus in `docs/qa_corpus/`;
  - context documents supplied by Epinoic in `docs/context-pack/`. Check that these may sit in
    the target repository.

## 4. Checks run for this review (2026-10-12)

**Environment.**
- A fresh virtualenv; Python 3.13.16.
- `pip install ".[dev,service]"` from the baseline checkout. This is a normal install, not
  editable, so the tests ran against the installed copy.
- Resolved versions:
  - z3-solver 5.1.0.0;
  - pydantic 2.14.1 and pydantic_core 2.50.1;
  - fastapi 0.143.0 and starlette 1.7.0;
  - uvicorn 0.54.0;
  - httpx 0.28.1;
  - pytest 9.1.1, pytest-timeout 2.4.0, hypothesis 6.169.0.
- The paid-provider extra (`providers`, which brings in `anthropic`) was deliberately not
  installed.

| Check | Command | Outcome |
| --- | --- | --- |
| Default suite | `python -m pytest -q` | **1,303 passed, 1 skipped, 12 deselected, 0 failed** in 22.65 s. The skip is `tests/translate/test_providers_model.py:148` (`anthropic` not installed). The deselected tests are stress-marked. |
| Stress suite | `python -m pytest -q -m stress` | **12 passed** in 130.46 s |
| Valid entailment (x>y, y>z ⊨ x>z) | `epinoic-logic verify` | ENTAILED; core P1, P2; both premises listed as ungrounded (no metadata) |
| Counterexample (x>y ⊭ x>y+1) | `epinoic-logic verify` | COUNTEREXAMPLE; x = 0, y = −1 |
| Contradictory premises | `epinoic-logic verify` | INCONSISTENT_PREMISES; core P1, P2; no entailment reported |
| Malformed input (`{"op": "exec", …}`) | `epinoic-logic verify` | INVALID_FORMALIZATION (E100 ×6); nothing executed |
| Nonlinear product | `epinoic-logic verify` | UNSUPPORTED (E201); no solver call |
| Bounded solver stop (80 linear constraints, `--rlimit 50`) | `epinoic-logic verify` | TIMEOUT (E400), `reason_unknown` "canceled"; not a success |

Every result carried the scope statement and `z3_version` 5.1.0. The CLI exited with status 0
in all six cases.

**Historical reports (not re-run for this review).** These come from model-judged testing in
earlier sessions:
- `tests/README.md`, `docs/ARENA_RESULTS.md` and `docs/STRESS_RESULTS.md`;
- a breadth probe run on this baseline with eight further specialists.

Their figures are judgements by model overseers, not deterministic checks.

## 5. What the code does

- **Engine (stable, well tested).** The input is a typed JSON IR (IR 1.0):
  - sorts: Bool, Int and Real;
  - linear arithmetic, with exact string literals;
  - no quantifiers.

  It is validated against a closed allowlist and policy limits, then compiled node by node to
  the Z3 Python API (z3-solver ≥ 4.13; 5.1.0.0 tested).

  It is decided by one of three queries: consistency, satisfiability, or entailment with a
  consistency precheck. It returns a bound, optionally signed `VerificationResult`, with
  distinct non-result statuses.

  See `docs/integration-contract.md`.
- **Report level (partial).** English specialist output becomes IR only in two ways:
  - deterministic builders for narrow patterns: arithmetic changes, order of dated events,
    Economics elasticity, Business margins, and consistency across agents;
  - model-proposed translations, parsed strictly and validated. The CLI can only replay
    recorded fixtures for these. No live provider call is evidenced.

  Everything else is reported as AMBIGUOUS_TRANSLATION or NOT_ELIGIBLE, or stays undecided.
  The code does **not** translate unrestricted natural language.
- **Router hub and channel.** Every transfer between agents produces a receipt with finding
  codes. Its rules are still changing under active testing.
- **Use case.** Checking that specialist sub-agents' outputs (English, History, others) reach
  the router and combinator without miscommunication, using engine-decided checks where a claim
  is formalisable.

## 6. Limits and findings

1. **Dependencies are lower bounds only** (`z3-solver>=4.13`, `pydantic>=2.6`). There is no
   lockfile. A fresh install today resolves Z3 5.1.0.0, so results depend on install date.
   The result's `versions.z3_version` records the version used, but builds are not
   reproducible.
2. **The CLI exit code is always 0.** A failure status is visible only in the JSON.
3. **TIMEOUT versus UNKNOWN depends on Z3's `reason_unknown` text.** A Z3 upgrade could
   reclassify a stop. Neither is ever a success.
4. **Entailment may run for up to twice `timeout_ms`,** because there are two solver calls.
5. **Z3's memory limit is process-wide.** The engine scales it with the number of concurrent
   verifications. Other Z3 users in the same process should pass `memory_max_mb=None`.
6. **Groundings do not change a status.** Callers must read `ungrounded_dependencies` and
   `unverified_dependencies` and must keep the scope statement.
7. **The report-level translator is not production-ready.** Model overseers judged
   communication fidelity on fresh material at:
   - 0.366–0.79 in arena round 5;
   - 0.50 across eight further subjects in the breadth probe;
   - 0.79 for the breadth probe's results audit.

   Subjects without a dedicated branch (Computer Science, Geography, Spanish B) did worst.
8. **Known crash at the baseline.** A synthesis containing subscript digits (`₁₀`) raises
   `ValueError` out of the hub. The path is `channel/bus.py` relay →
   `integrity/ledger.check_synthesis_ledger`. It was found by the breadth probe on Computer
   Science output. This breaks the rule that the hub never raises.
9. **Documentation gaps:**
   - `CLAUDE.md` refers to `docs/DESIGN.md` and `docs/STATUS.md`, which do not exist;
   - the governing specifications are missing (`docs/context-pack/MISSING_FILES.md`);
   - there is no `AGENTS.md`.

## 7. Import steps (to run with the authorised account)

Run these on a machine signed in as `danielhyon98-byte` (`gh auth login --hostname github.com
--git-protocol https --web`). Accept the invitation first at
https://github.com/Bruno-ios/Epinoic-Logic-Translator/invitations.

```
git clone --branch claude/z3-verification-engine-plan-nk3luq \
  https://github.com/danielhyon98-byte/https-github.com-lovishchopra-NL2FOL.git epinoic-logic-translator
cd epinoic-logic-translator
git remote add epinoic https://github.com/Bruno-ios/Epinoic-Logic-Translator.git
git ls-remote epinoic                       # confirm the repository is still empty
git push epinoic <REVIEW_COMMIT>:refs/heads/main          # no --force, no --mirror
git ls-remote epinoic refs/heads/main       # must print <REVIEW_COMMIT>
```

`<REVIEW_COMMIT>` is the commit that adds this review on top of the baseline. Its parent must
be `3147d08e0aa63d5eeaceb1072754f29e3862164d`. Pushing it publishes the baseline history plus
these two documents, and nothing after them.

- Keep `origin` pointing at Daniel's repository.
- Do not push the work-in-progress commit or the local `stem-build` and `overseer-build`
  branches to `main`.

## 8. Recommended next milestone

**M1: a reproducible, executable contract.** Owner: the translator project's implementation
owner (one person), with Daniel as reviewer.

Scope: no behaviour change.
- Add an exact dependency lock for the tested set in section 4. It must cover both Python 3.11
  (the declared minimum) and 3.13.
- Add contract tests that run the six section-4 cases through `verify()` and the CLI. They
  assert status, diagnostic codes and evidence fields as documented in
  `docs/integration-contract.md`.
- Generate the contract's two example outputs with a script, not by hand.

Acceptance checks:
1. A fresh virtualenv installed only from the lock plus `pip install --no-deps .` passes the
   full default suite on Python 3.11 and on 3.13. The expected count is 1,303 passed and
   1 skipped, plus the new contract tests.
2. `pytest tests/contract -q` covers ENTAILED, COUNTEREXAMPLE, INCONSISTENT_PREMISES,
   INVALID_FORMALIZATION, UNSUPPORTED and TIMEOUT, and passes.
3. Regenerating the contract examples gives no diff apart from volatile fields.
4. No public interface changes: same IR, same result fields, same CLI exit codes.

Next candidate after M1: fix the subscript-digit crash (finding 8), with a regression test.
