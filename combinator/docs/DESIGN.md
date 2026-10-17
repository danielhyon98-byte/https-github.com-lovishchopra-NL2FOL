# Combinator design

## Role and boundary

The combinator is the step of a combined answer (two or more specialists answering one request) that turns the
specialists' delivered claims into one synthesis. It is a separate agent: its own package, instructions, runner and
release, reached by the translator's service only through the combinator port. The boundary has three sides:

| Side | Owns | Trusts |
|---|---|---|
| the agent (a cheapest-tier model behind a provider) | the wording of the synthesis | nothing: it is untrusted |
| the runner (this package) | the call, and the contract gate on what the agent wrote | the published contract only |
| the translator's hub | every check of faithfulness (ledger, conflicts, entailment) | its own checks and signed engine results only |

The runner's gate answers one question: is this a message of the published contract? It never answers whether the
synthesis is faithful. That division is deliberate: if the combinator also judged faithfulness, a fault the gate let
through would look checked twice, and an agent's self-report would gain weight. The hub checks every synthesis as if
the runner did not exist.

## Input, agent format, port message

- **Input** (`combinator-input.v1`, built by the service): the request's ids; per delivered report its id, agent,
  subject, branch and claims (id, role, materiality, certainty, text and the SHA-256 of the text); the closed
  vocabulary; the instruction pack the service pins.
- **What the agent sees** (`prompt.py`): the pack's `INSTRUCTIONS.md` as its instructions; the request's ids and the
  sources' claims without digests as one JSON document. Digests and the pack reference stay with the runner.
- **What the agent writes**: `{claims, dropped?, conflicts?}`, each claim exactly `{text, source_claim_ids, certainty,
  transformation}`. This is stricter than the port message: no `evidence_refs` (the service attaches the references
  it keeps), no envelope.
- **Port message** (`combinator-output.v1`): the runner adds the request's ids, the pack's digest and `evidence_refs:
  null`, and checks the whole message against the contract again. Its text is canonical JSON, so the translator's
  `dump(check_output(text))` is byte for byte the same text.

## Refusals

A refusal is a message of the contract too (`combinator-refusal.v1`): a closed `reason`, the one `KIT-CB` code of that
reason (`combinator-port.v1.json`), the request it refuses (null only when the input could not be read, or for an
internal error before it was), the pack's digest and a detail of at most 300 characters that names positions, rules and
lengths but never the agent's prose (a long value is described as "free text of N characters"). `KIT-CB-002` covers
every case without an output in contract, including no output at all; the reason tells them apart.

## Order of the rules

The runner decides in the order the translator's `check_output` does, so both sides name the same code for the same
message: (1) not JSON or not an object; (2) a transformation outside the vocabulary, before anything else; (3) the
schema, the agent format, a conflict naming a claim twice; (4) another request; (5) another pack; (6) a citation the
input does not hold; (7) a synthesis text over 49,152 UTF-8 bytes. The runner's own size guard (262,144 bytes of agent
text, before parsing) comes first; the port never sees the agent's raw text.

## The validator

`schema.py` implements the keywords the translator's generated schemas use and refuses any other at load time, so a
rule it does not understand can never be skipped. Semantics follow the translator's strict models: no coercion,
lengths in code points, and a pattern's `$` at the end of the text only (Python's `$` also matches before a final line
break, so the final `$` is compiled as `\Z`). The conformance suite runs the translator's combinator-port vectors and
generated outputs through both validators and requires the same verdict.

## Determinism and bounds

One input, at most one provider call, one result: no retry, no fallback, no second model. The same input and agent
text give the same output text in any interpreter. Bounds: 262,144 bytes read from the agent; the port's limits on
claims (1 to 512, 4,000 characters each, 1 to 64 citations), dropped entries (512), conflicts (64) and total text
(49,152 bytes).

## Not in this release (connected in phase 2, or decided by the owners)

- **A live provider.** The interface is here; no class calls a model, reads a key or opens a connection. A live provider
  is wired by its owner with a model the owners approve (decision D23) and a per-call timeout (the provider's own).
- **The service-side attachment.** How the translator's service runs this package (its own process, as the flash
  router does, holding a provider credential, or a sidecar), and the release path of a combined answer, are the
  translator's phase 2 and decisions D19 and D33.
- **Evidence references.** The agent does not see or write them; the service attaches the references of cited material
  sources whose excerpts a synthesized claim reproduces (the rule the translator's arena harness applies), or the hub
  charges `INT-LEDGER-004` for a quoted material source.
