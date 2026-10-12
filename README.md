# Epinoic AI — Logic Translator and Z3 Verification Engine

Proprietary. See `LICENSE` and `THIRD_PARTY_NOTICES.md`. Status of every component
(planned / implemented / tested / deployed) is in `docs/STATUS.md`. Nothing in this
repository is deployed.

## What this program does, in plain language

Epinoic AI's tutor is a set of subject-specialist agents (English, Mathematics,
Physics, Economics, History and so on) that write structured answers for
International Baccalaureate students. Language models can state things confidently
that do not follow from the evidence, invent quotations, or contradict themselves.
This program makes those failures **visible and checkable** without pretending to
judge whether an interpretation is "true".

It does three separate things and never blurs them:

1. **Structural checks (deterministic code).** Is the specialist's report well
   formed, are its claim ids stable, is the original text unchanged (hash), and does
   every quotation it cites actually occur, word for word, in the text the student
   supplied? Invented quotations and invented line citations are flagged here.
2. **Translation (model-proposed, code-validated).** For claims that *can* be
   formalized, a model proposes a small typed logic problem: the atomic propositions
   the specialist relied on, where each one is grounded (a quotation, a task setting,
   an inference the specialist made, an outright assumption), the inferential links
   the specialist asserted, and the point being argued. The proposal is **data**: it
   is parsed strictly, validated against a closed schema, and never executed.
3. **Formal verification (Z3).** The engine checks whether the premises are
   consistent, and if so whether they entail the point. It reports exactly which
   premises the proof relied on and which of those are unverified inferences or
   assumptions. If the point does not follow, it shows a concrete counterexample. If
   the premises contradict each other, it names the conflicting ones.

A verified result therefore says: *given these encoded premises, under this
configuration, this conclusion does or does not follow*. It never says the premises
are factually true, that the translation captured the claim faithfully, or that a
literary or historical reading is correct. Every result carries that scope
statement. This is deliberate: the system is not a universal hallucination
detector; it is an auditable way to show what was checked, how, under which
assumptions, and what remains uncertain.

## The primary feature: every message between agents goes through the translator

The translator is a **branching infrastructure**: one hub that every specialist
(English, History, Psychology, Economics, Business Management, and any subject
added later) communicates with the primary router through, and one branch per
subject carrying an **integrity pack** of subject-specific checks. The hub integrity
(envelopes, hand-off, request fidelity, claim ledger, staleness, cross-agent
consistency, signing) is shared; the packs add what each subject's knowledge
documents demand, such as quotation integrity for literature, chronology and dated
figures for history, study attributions for psychology, elasticity arithmetic for
economics and margins for business. See `src/epinoic_logic/branches/README.md`.

Agents do not pass raw text to each other. The `channel` package
(`src/epinoic_logic/channel/`) sits on the communication path. When the router sends
a student's request to a specialist, the request is made explicit (what is asked,
word and paragraph limits, which texts may be used) and wrapped in a hashed envelope.
When the specialist answers, the response must reply to that exact request and is
checked before the router sees it: right task and agent, no replay or tampering,
quotations found in the supplied texts, numeric constraints decided by the engine as
signed results, eligible claims verified, items of the request covered, and
contradictions with claims already transmitted by other agents named. The router
receives the report together with a receipt, or a rejection and no report. The same
channel carries agent-to-agent transmissions, such as the English specialist's output
reaching the combinator, with the claim ledger checked on the way. See
`channel/README.md` and `integrity/README.md`.

Integrity properties the channel holds on every transmission and relay:

- The envelope's sender is bound to the payload's owner: a specialist cannot relay a colleague's report, or a copy of it, under its own name (INT-ENV-008).
- A report the router already holds is never overwritten: a report id re-delivered with a different payload is refused and the first delivery kept (INT-HANDOFF-015).
- A response that merely echoes the request is named as such and counts for no request item (INT-REQ-011).
- A quotation whose words occur in the supplied text but whose form differs (initial capital, a verse line break written " / ", a long elision) is a warning, never an invented quotation (INT-REQ-010).
- A quotation credited to one source but found only in another supplied text, a peer specialist's report included, is a wrong attribution and is named with both texts (CORE-SRC-005, ES-SRC-008).

## The Overseer: checks of every transfer between agents (`src/epinoic_logic/overseer/`)

Every request, report, relay, router forward and synthesis crosses the channel; the Overseer checks those transfers so
the router never acts on a miscommunicated or tampered one. It is optional and attached through the hub:
`RouterHub(auditor=TransferAuditor(...))`. Without it the hub and the channel behave exactly as before.

- **The transfer auditor** (deterministic code) journals every transfer as it is issued (a hash-chained, HMAC'd journal
  per channel), keeps every signed engine result the transfer produced, and checks that the transfer the router is about
  to act on is the one issued, that every receipt is the exact image of what was checked, that every result a receipt
  cites is a signed engine run of the problem it names inside this task (re-run on a fresh engine), that delivered
  claims, quotations and figures are what the specialist actually wrote, that forwards and peer documents are the
  delivered text, and that a synthesis accounts for the delivered reports and names every contradiction. What it finds
  is a signed audit of `OVS-*` findings with identifiers.
- **The translator is overseen too.** Every IR problem a translation provider proposed for a claim is re-checked as
  untrusted data (`OVS-TRN-*`: re-validated by the engine's validator, its status and eligibility re-derived, its
  quotation groundings re-checked against the named supplied texts, every quotation and number traced to what the
  specialist said, a conclusion found among its own premises flagged as circular, its summary regenerated from the
  signed result), and the signed audit records each translation: the claim text, the proposed IR, its validation
  outcome and the signed engine result. Overseer agents receive each translation with its claim and may accuse it,
  including of meaning faults (a dropped condition, a flipped comparison, an invented premise); those stay advisory and
  go to human review.
- **Before acting** the router calls `hub.clearance(task, message_id, receipt=...)` with the receipt it holds and acts
  only when `overseer.policy.may_act(receipt, clearance)`: an edited receipt, a forged or misattached result or an
  altered payload is never acted on, and a pending audit is never shown as passed. `hub.close_task` issues the FINAL
  audit; `policy.may_release` gates the student-facing synthesis on it.
- **Overseer agents** are model-based reviewers built only from exportable parts: the package's code and a versioned
  knowledge pack shipped as package data (`overseer/knowledge/overseer-knowledge-docs-1.0/`: `master_prompt.txt` and
  numbered documents, generated schemas, a manifest of digests). `python -m epinoic_logic.overseer.export --out DIR`
  writes the pack out with a README for whoever deploys it with any model. `hub.review(task, runners)` issues each agent
  a dossier, runs it once, and validates its verdict against the journal and the signed results. A verdict is advisory
  and decides nothing: only an accusation a deterministic check confirms reaches the router, through that check's own
  finding, and no agent ever changes a clearance. No live model provider is claimed; the tests use fake providers.
- **Several agents, one input.** When the router sends one input to several agents (duplicated instances of one
  specialist, or several specialists), `hub.consolidate(task)` returns ONE signed consolidated response: equivalent
  answers grouped deterministically (identical normalised text, or the same material claims, figures, dates and
  quotations that the engine finds mutually consistent), a representative per group, every answer with an error-level
  finding or a repeated fault excluded with its codes and signed results, and conflicts between groups disclosed instead
  of resolved by choosing. A fault that comes back in the same task (another agent, a duplicated instance, a resubmission
  after rejection, reworded or not) is a repeated fault (`OVS-REP-001`), never delivered, counted per agent.
  `hub.review_pool(tasks, OverseerPool(pack, ...))` sizes the overseer agents deterministically: one instance by default,
  more over a per-instance quota or when faults repeat (each repeated-fault dossier to two independent instances), never
  past a maximum (four by default), every instance from the same exported pack and advisory.

Results prove properties of the encoding only; an audit shows whether the recorded transfers, receipts and signed
results agree with each other and with the repository's rules, never that a claim is true. See
`src/epinoic_logic/overseer/README.md` and `docs/OVERSEER_DESIGN.md`.

## Features of the logic translator (`src/epinoic_logic/translate/`)

| Feature | What it does | Where |
| --- | --- | --- |
| Claim-record input | Works on structured claims from a specialist report (ids, role, subject, source refs, assumptions), not on raw student text. | `contracts.py` |
| Deterministic eligibility | Code, not the model, decides whether a claim may be formalized: argument structure (point + supporting claims), structural counts, exact numeric claims. Interpretive, factual and rubric judgements are routed elsewhere. | `eligibility.py` |
| IB subject policy | Per-subject profiles say which claim classes are allowed (quantitative claims in Mathematics, Sciences, Economics, Business; argument structure only in Literature, History, Arts, TOK). The profile text is injected into the prompt so the model knows what cannot be established in that subject. | `subjects.py` |
| Staged decomposition | The prompt asks the model to list grounded atomic propositions first, then the specialist's inferential links, then assemble the problem. Inspired by the NL2FOL method; no code or prompt text copied. | `prompts/translate_v1.md` |
| Grounding checks | Quotations cited as grounding are matched verbatim (then with typographic normalization) against the supplied text; `verified` is set only by this code. | `grounding.py` |
| Strict parsing | Model output is parsed with a plain JSON parser only (code fences stripped); anything else is a failed attempt. | `parsing.py` |
| Bounded retries | Validation diagnostics are fed back for at most one retry; the status then becomes INVALID_FORMALIZATION rather than looping. | `pipeline.py` |
| Ambiguity flags | The model must declare materially different readings; the result becomes AMBIGUOUS_TRANSLATION and is never shown as verified. | `pipeline.py` |
| Replaceable providers | Fixture provider for tests; Anthropic and OpenAI-compatible adapters behind one interface (untested live here). | `providers/` |
| Advisory semantic review | An independent reviewer rates translation fidelity; the verdict is labelled advisory and never changes the formal status. | `review.py` |
| Outcome for the Overseer | One record per claim: translation, signed engine result, structural findings, review, a derived display status and a plain-language summary ending with the scope statement. | `outcome.py` |

## Communication between agents (`src/epinoic_logic/integrity/`)

Miscommunication between the router, specialists, combinator and Overseer is
checked as well as hallucination inside one answer. Deterministic code checks
message envelopes (replay, tampering, mis-threaded replies), router hand-offs
(wrong task, unselected agent, off-subject, citations outside the retrieval scope),
result staleness (a verification result reused after the claim's representation
changed, or unsigned), and the combinator's claim ledger (material claims dropped
without record, claims with no source, certainty inflated above the weakest source,
evidence references lost, conflicts "resolved" without a basis). Z3 then checks
whether specialists' formalized claims contradict each other under a shared glossary,
naming the conflicting claims, and whether each synthesized claim is actually
entailed by the source claims it cites, producing a counterexample when the
combinator stated more than its sources support. See `integrity/README.md`.

## The verification engine (`src/epinoic_logic/engine/`)

Restricted IR 1.0 (Bool, Int, Real; 24 allowlisted operators; exact numerals as
text) → validator (sorts, identifiers, limits, policy; collects all diagnostics) →
compiler (one Z3 call per node, fresh context) → procedures (consistency first,
then entailment with tracked unsat cores; exact models) → result bound to a digest of
the exact problem, solver configuration and component versions, and HMAC-signed so
the Overseer can reject anything an agent fabricates. Statuses form a closed set;
only six are definitive and none means "the claim is true".

## Repository layout

- `src/epinoic_logic/ir/` — IR schema and canonical digests (`README.md` inside)
- `src/epinoic_logic/engine/` — validator, compiler, procedures, provenance, runner
- `src/epinoic_logic/translate/` — contracts, eligibility, subjects, grounding, pipeline, providers, review, outcome
- `src/epinoic_logic/branches/` — the router hub, subject branches and integrity packs (primary infrastructure)
- `src/epinoic_logic/channel/` — the translator channel every inter-agent message passes through
- `src/epinoic_logic/integrity/` — inter-agent envelope, hand-off, ledger, staleness and formal cross-checks
- `src/epinoic_logic/overseer/` — the transfer auditor, router policy, the overseer-agent verdict protocol, the knowledge pack, its loader, exporter and agent runner
- `src/epinoic_logic/adapters/` — specialist adapters (generic structured; English specialist as worked example; multi-subject fixtures)
- `src/epinoic_logic/service/` and `cli.py` — authenticated HTTP boundary and command line
- `tests/` — unit, end-to-end, service and `stress/` suites
- `docs/` — audit, plan, design, status, stress results, evidence, context pack

## Running

```
python -m venv .venv && .venv/bin/pip install -e ".[dev,service,providers]"
.venv/bin/pytest                      # unit, e2e and service tests
.venv/bin/pytest -m stress tests/stress   # load, concurrency, adversarial volume, soak
epinoic-logic verify problem.json     # one verification from the command line
```

## What it does not do

It does not decide literary, historical or rubric judgements; it does not check
units, nonlinear algebra, quantifiers or symbolic calculus (these are reported as
UNSUPPORTED); it does not run inside a Cloudflare Worker (see `docs/AUDIT.md` for
the runtime evidence); and it does not call any model provider in its tests.

## Arena: real agents, contained environment

Isolated specialist agents configured only from the knowledge documents answer router
tasks; every output crosses the hub as in production, independent overseer agents judge
fidelity and fault naming, and fixes are regression-tested before the next round. The
harness, the peer-exchange relay and the recorded rounds are described in
`docs/ARENA_RESULTS.md`; stress figures for the engine, channel and hub are in
`docs/STRESS_RESULTS.md`.

Bug testing and stress testing results (test layers, every overseer round's verdicts and findings, harness and stress numbers) are reported in `tests/README.md`.
