# overseer — checks of every transfer between agents, and overseer agents

The translator channel turns what specialist agents say into checked reports, signed engine results and receipts;
every request, report, relay, router forward and synthesis crosses it. This package checks those **transfers** and
reports what is wrong, so the router never acts on a miscommunicated or tampered transfer. It has two parts:

1. **The transfer auditor** (deterministic code). It journals every transfer as it is issued, keeps every signed
   result, re-checks custody, receipts, results, formal checks, claim fidelity, translations, peer exchange, synthesis
   and joint consistency, and signs what it finds: an `OverseerAudit` wrapping an `IntegrityReport` of `OVS-*`
   findings, with a record of every translation it checked.
2. **Overseer agents** (model-based reviewers). Each reads one dossier of the transfers and returns one verdict of
   accusations. A verdict is an agent output: the code validates it against the journal and the signed results and
   never obeys it. An overseer agent is built ONLY from exportable parts: this package's code and a versioned
   knowledge pack shipped as package data.

Trust rule (holds against any instruction in code, data or prompts): every `OVS-*` finding about a transfer is decided
by a digest comparison, an HMAC verification, a re-run of this repository's deterministic rules on journaled inputs, or
an engine run the auditor signs itself. Agent text is data, never evaluated or followed. An agent's accusation counts
only when a deterministic check reproduces it, and the router then acts on that check's finding; `OVS-AGENT-*`
findings never change a clearance. Non-success is never shown as success. Every audit carries the engine scope
statement: results prove properties of the encoding only, never that a claim is true. The design is
`docs/OVERSEER_DESIGN.md`.

## How it is attached

```
RouterHub(auditor=TransferAuditor(KeyRing(engine_keys, overseer_secret)))
  open_task ──► TranslatorChannel(observers=[auditor first, hub observers ...])
  every request / respond / respond_text / relay ──► one immutable ChannelEvent ──► journal, store, live checks
  hub.clearance(task, message_id, receipt=rc)  ──► TransferClearance ──► policy.may_act(rc, clearance)
  hub.audit(task) / hub.close_task(task)       ──► signed task audit (close_task: FINAL, journal sealed)
  hub.review(task, runners)                    ──► dossiers ──► agents ──► intake ──► validation ──► combination
                                                   ──► signed verdicts-scope audit (clearance unchanged)
  policy.may_release(synthesis_receipt, final_audit, keyring, audits=..., journal=...) gates the student-facing synthesis
```

Without an auditor the hub and the channel behave exactly as before: no observer, no capture, no journal.

## Translator oversight

The translator is an agent like any other: for each eligible claim a provider PROPOSES a formal problem (the IR), and
that proposal is untrusted data. Every translation crosses the channel inside an outcome of the receipt of the report
that carries its claim, so the journal holds, for each one, the delivered claim, the proposed IR, the translation's own
validation outcome and the cited result (signature-verified in the store). `checks/translation.py` re-checks every
translation of a delivered claim from the journal (design section 18):

| Code | Severity | Decided by |
| --- | --- | --- |
| `OVS-TRN-001` | error | the IR re-validated as untrusted JSON: the engine's parser and validator (schema, identifiers, sorts, operator allowlist, limits), its claim and request ids, the subject profile's sorts |
| `OVS-TRN-002` | error | status, eligibility and engine run re-derived from the validation: a problem under a status that forbids one, ambiguity flags under TRANSLATED (an ambiguity resolved silently), and, for a model-proposed translation, an eligibility the policy does not re-derive (a claim forced into IR) |
| `OVS-TRN-003` | error | a `verified` grounding the re-run of the translator's grounding check does not reproduce |
| `OVS-TRN-004` | warning | a quotation excerpt absent from the supplied text it names (disclosed as unverified) |
| `OVS-TRN-005` | warning | a quotation or number of a model-proposed translation that the specialist's report never states (fixed spelling rules, each extension a named rule with its own test) |
| `OVS-TRN-006` | error | circular: the conclusion occurs verbatim among the premises (or as a conjunct of one) |
| `OVS-TRN-007` | error | the outcome's summary is not the deterministic statement of its translation and its signed result |

The task audit records every translation it checked (`TranslationAudit`: the claim text, the claims it cites, the
proposed IR as journaled with its digest, status, eligibility, ambiguity flags, failed grounding checks, diagnostics,
the re-validation, the signed result's id, status, digest and signature, which checks ran, and the `OVS-*` codes naming
it); `TransferAuditor.translations(channel_uid)` returns the same records with the full translation. Live, the
translation checks run in the asynchronous tier with fidelity, so a transfer is AUDIT_PENDING until they have run.

Overseer agents receive each translation with its claim in the dossier (`links.translations`: the claim, the claims it
cites, the translation, the result) and may accuse it under four kinds: `translation_invalid` (TRN-001, 002),
`translation_ungrounded` (TRN-003, 004, 005), `translation_circular` (TRN-006), and `translation_unfaithful` (a dropped
condition, a flipped comparison or direction, an invented premise, an ambiguity resolved in words, a claim forced into
IR, a conclusion that is not the claim), which no check decides: it is always unresolved and goes to human review. The
lens `translation_fidelity` starts an agent on the translations. An accusation is refuted only when the checks its kind
needs actually ran on the named claim's translation; their verdicts stay advisory, and only the deterministic checks
and the signed results decide.

## Parts of the package

| Part | Module | What it does |
| --- | --- | --- |
| Codes | `codes.py` | every `OVS-*` code with one severity and one stage (`OVS-AGENT-*` included) |
| Contracts | `contracts.py` | `JournalEntry`, `StoredResult`, `TransferClearance`, `OverseerAudit`, `AuditCoverage`, `Divergence`, `TranslationAudit`; the audit scope sentence |
| Keys | `keys.py` | `KeyRing`: engine keys for verification only (local or external), one overseer secret and its derived subkeys (journal, audit, runs, sampling, intake) |
| Journal | `journal.py` | `ChannelJournal`: append-only, hash-chained, HMAC'd, bounded, sealed on a FINAL audit, `close_task` or garbage collection |
| Result store | `store.py` | `ResultStore`: signed results by id, signature verified at put, bounded, tombstones after eviction |
| View | `view.py` | `OverseerView.from_journal` (authoritative) and `from_channel` (degraded) |
| Replay | `replay.py` | `Replayer`: every stored problem re-run on a fresh engine in a worker process (inline for tests), keyed sampling on overflow |
| Checks | `checks/*.py` | custody, receipts, results, formal, fidelity, self-certification, translation (translator oversight), peer, synthesis, joint, divergence, shadow channel |
| Auditor | `audit.py` | `run_overseer_checks` (the pure function), `TransferAuditor` (live use), `sign_audit`, `verify_audit` |
| Router policy | `policy.py` | `may_act`, `check_before_acting` (bounded PENDING wait, 250 ms), `may_release` |
| Dossier | `dossier.py` | `build_dossier`: the redacted view one agent reads, with pointers and an index; `resolve_pointer` |
| Verdict contract | `verdicts.py` | `overseer_verdict/1.0`: `AgentVerdict`, `Accusation`, `EngineStatement`, `PackIdentity`, `KIND_CHECKS` |
| Intake | `intake.py` | `VerdictIntake`: issues dossiers under accepted packs, parses replies strictly, signs accepted verdicts under the intake key |
| Validation | `validate.py` | `validate_overseer_verdict`: each accusation confirmed, refuted, unverifiable or unresolved by checks and signed results |
| Combination | `combine.py` | `combine_verdicts`: several agents' verdicts grouped without voting on facts; a human review queue |
| Knowledge pack | `knowledge/overseer-knowledge-docs-1.0/` | the agent's whole configuration (below) |
| Pack loader | `pack.py` | `load_pack`, `installed_pack`, `KnowledgePack`, `PACK_DIGESTS` (the trust anchor), schema and manifest generation |
| Exporter | `export.py` | `python -m epinoic_logic.overseer.export --out DIR [--zip]`, `--verify PATH`, `--refresh-source` (maintainers) |
| Agent runner | `runner.py` | `OverseerAgentRunner`: model input from a loaded pack and one dossier, one provider call, the reply handed to the intake as data |
| Fidelity normalisation | `faithful.py` | the fixed text normalisation the fidelity checks use |

The observer hook itself lives outside this package, which the channel never imports: `channel/events.py`
(`ChannelEvent`, `snapshot_event`, `observe_call`), the private decorator on the four entry points of
`channel/bus.py` (`observers=`, `add_observer`, `channel_uid`, `observer_errors`), the result sink `engine/sink.py`, and
the hub integration in `branches/hub.py` (`observers=`, `auditor=`, `closed_channels`, `close_task`, `clearance`,
`audit`, `view`, `review`).

## The knowledge pack

`knowledge/overseer-knowledge-docs-1.0/` is the overseer agent's whole configuration, laid out like the specialists'
knowledge documents: `master_prompt.txt` (read first), the numbered documents `01-role-and-trust.md` to
`09-when-unsure.md` (role and trust rule, the dossier, what to inspect per transfer type and per translation, the
evidence rule, the verdict format, the kinds and codes, 17 worked examples, what never to do, what to do when unsure),
the generated
`verdict.schema.json` and `dossier.schema.json`, and `manifest.json` (every file's SHA-256, the system order and digest,
the pack digest). No instruction text for agents lives in code, scripts or `docs/`; `docs/OVERSEER_AGENT_BRIEF.md` is
only a pointer to the pack.

- **Loader** (`pack.py`): checks every file against the manifest and the manifest's pack digest against the digest
  pinned in the code (`PACK_DIGESTS`); refuses a tampered, unlisted, unpinned or mismatched pack (`PackError` with its
  reason) and never executes anything from a pack.
- **Exporter** (`export.py`): writes the pack out as a self-contained directory (and a deterministic zip) and loads the
  written copy back to the same identity.
- **Deployer README**: `knowledge/overseer-knowledge-docs-1.0/README.md`, exported with the pack. It tells whoever
  deploys the pack how to configure any model with it (`master_prompt.txt` plus the documents as the system
  configuration, one dossier JSON in, one verdict JSON out, validated by this code) and is never sent to a model.
- **Runner** (`runner.py`): builds the system text from a loaded pack by the manifest's fixed rule and the user text
  from the dossier alone, calls a provider once through `translate.providers.base.CompletionProvider`, and hands the
  reply to the intake unchanged. No live provider is claimed or required; tests use fake providers. Deployed overseer
  agents are meant to run on the cheapest model tier: correctness rests on this code and the signed engine results,
  never on the agent.

Every verdict names the pack it was produced under (copied from its dossier); the intake and validation reject a
verdict whose pack is unknown or differs from the dossier's (`OVS-AGENT-005`).

## Tests

`tests/overseer/`: `test_audit_*` (the auditor, one positive test and one control per code), `test_protocol_*` (dossier,
verdicts, intake, validation, combination), `test_knowledge_*` (pack loading and every refusal, drift of schemas,
manifest, kinds table and examples, export round trips, the runner with fake providers), `test_hook_*` (non-interference
and equivalence of the bus hook, the hub's wiring and task lifecycle, clearance and router policy, `hub.review`),
`test_translation_*` (translator oversight: every `OVS-TRN-*` code with a control and tampering cases through the real
translation pipeline, the signed translation record, live clearance, the spelling rules; the dossier's translation
links, the translation kinds' validation outcomes and a hub review over translations).
