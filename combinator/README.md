# Epinoic AI combinator (`epinoic-combinator`)

The combinator combines the specialists' answers to **one request** into **one synthesis**: a short list of
synthesized claims, each citing the source claims it came from with one closed transformation word, the source claims
it left out with their reasons, and the contradictions it discloses instead of reconciling them.

It is a **separate agent in a sub-project of its own**: this directory has its own `pyproject.toml`, version,
instructions, runner, tests and release, needs nothing but the Python standard library at run time, and never imports
the translator, the engine or Z3. It is edited, tested and released without touching the Z3 infrastructure. It meets
the translator only through the integration protocol's combinator port `epinoic.integration.combinator-port.v1`
(the translator's `integration/PROTOCOL.md`, section 7) and the **published synthesis contract**, a copy of which
travels in this package.

| Part | Where | What it does |
|---|---|---|
| the agent's instructions | `src/epinoic_combinator/pack/` (`INSTRUCTIONS.md`, `output-format.json`) | what the agent is told, pinned by digest (`pack.py`: name `combinator-instructions`, version, SHA-256) |
| the exporter | `python -m epinoic_combinator.export --out <dir>` | writes the instructions and a manifest for a workflow or a provider |
| the runner | `src/epinoic_combinator/runner.py` | runs the agent once, on the cheapest tier, through a provider; lets out only what is in contract |
| the provider interface | `src/epinoic_combinator/providers.py` | `Provider.complete(CompletionRequest) -> str`; deterministic fakes for tests; **no live provider** |
| the published contract | `src/epinoic_combinator/contract/` (generated, never edited) and `contract.py` | the port's JSON Schemas, the synthesis vocabulary and the port rules, read by a small fail-closed validator (`schema.py`) |
| the port | `src/epinoic_combinator/port.py` | `hello() -> str`, `combine(input_json, provider) -> str`: what the service attaches |

## What the agent is told (`pack/INSTRUCTIONS.md`)

It combines the specialists' answers to this one request and nothing else; it writes `transformation` as exactly one
of `carried`, `paraphrased`, `merged`, `narrowed`, `generalized` (a category, never a description of the edit);
certainty is never stronger than the weakest source; every figure, unit, mark, date and quotation is kept exactly as
the source states it; qualifiers and attributions are kept; a note, a self-certification, a decline or a question is
never carried back as a claim; a contradiction is never merged or hidden but listed in `conflicts`; every dropped claim
is listed with its reason; it writes the exact output format and nothing else:

```
{"claims": [{"text": "...", "source_claim_ids": ["..."], "certainty": "...", "transformation": "..."}],
 "dropped": [{"source_claim_ids": ["..."], "reason": "..."}],
 "conflicts": [{"claim_ids": ["...", "..."], "description": "..."}]}
```

`output-format.json` states the same as data; its transformation words and what each records are the published
contract's word for word (tested). The end-to-end simulation of 16 October 2026 showed why this matters: its
combinator was told the field without its values and wrote free text in all 62 synthesized claims, so every synthesis
was refused.

## What the runner guarantees

`runner.run(input_json, provider)` returns exactly one of a `combinator-output.v1` document or a `combinator-refusal.v1`
document with a closed `reason` and its `KIT-CB` code; it never raises (only a `KeyboardInterrupt` goes through).

| Reason | Code | When |
|---|---|---|
| `input_not_json`, `input_invalid` | `KIT-CB-001` | the service's input is out of contract (the refusal names no request) |
| `pack_mismatch` | `KIT-CB-005` | the input pins another instruction pack than this release's |
| `provider_unavailable`, `provider_failed`, `provider_no_text` | `KIT-CB-002` | no provider, a provider on another tier, a provider that raised or gave no text |
| `output_not_json`, `output_not_object`, `output_invalid` | `KIT-CB-002` | the agent wrote anything but one JSON object in the exact format |
| `transformation_unknown` | `KIT-CB-003` | a transformation outside the five words (decided first, as the port decides it) |
| `source_claim_unknown` | `KIT-CB-004` | a citation of a claim the input does not hold |
| `output_too_large` | `KIT-CB-006` | more than 262,144 bytes from the agent, or a synthesis text over 49,152 bytes |
| `internal_error` | `KIT-CB-002` | a defect of this release (its pack or contract copy unreadable, an unexpected error) |

The agent is called once (no retry). Its output is validated against the published contract twice before it leaves:
in the agent's own, stricter format, then as the port message. **The runner checks the contract, never the
faithfulness**: an inflated certainty, a dropped qualifier, a merged contradiction, an invented figure, a wrong
attribution or a carried self-certification is in contract and leaves, and the translator's hub, the independent
checker of every synthesis, names it (the translator's `tests/integration/test_combinator_subproject.py`). Nothing the
combinator says about its own work is trusted.

## The published contract

The translator publishes it in `integration/schemas/` (generated from its models: `combinator-input.v1`,
`combinator-output.v1`, `combinator-hello.v1`, `combinator-refusal.v1`; `synthesis-vocabulary.v1.json` from its
`integrity/contracts.py`; `combinator-port.v1.json`, the port's rules) and its `integration/tools/generate.py` copies
them into `src/epinoic_combinator/contract/` byte for byte (the translator's suite fails on any drift). The runner reads
that copy with `schema.py`, a validator that refuses any schema keyword it does not implement, and applies the rules
the schemas cannot state in the port's order. Its digest is `contract_sha256` in the hello. Never edit the copy: a
contract change is made in the translator and copied here by its generator, with a new release of this package.

## How the translator's service uses it

The translator never imports this package. It attaches it through the combinator port (phase 2 of the integration:
`EPINOIC_COMBINATOR` names the module `epinoic_combinator.port`; until then the service reports the combinator
unavailable and never offers the mode `combined`). The service builds the input from the delivered reports, pins this
release's pack, validates the hello, the output or the refusal with its own port checks, turns an output into the
`synthesis/1.0` mapping (`combinator_port.synthesis_payload`) and relays it through its hub, whose ledger, conflict and
entailment checks decide it. Which model a provider calls is its owner's configuration (decision D23: none is
approved, so no live provider is in this release and no model is named here).

## Tests

```
cd combinator
python -m pytest -q                      # inside the translator repository: uses ../src for the conformance tests
```

Inside the translator repository the documented test command of the translator (`python -m pytest -q` at its root)
runs this suite too (`tests/integration/test_combinator_subproject.py` there) and requires it to pass with nothing
skipped. Installed on its own (a virtual environment with the translator installed for the conformance tests):

```
python -m pip install -e "combinator[dev]"
python -m pytest -q combinator/tests
```

The suite shows: the instructions and their format (`test_pack_and_export.py`), the contract copy and the validator
(`test_contract.py`, the translator's canonical vectors included), the runner (`test_runner.py`: every malformed output
a named refusal, every provider failure, determinism, no retry, generated provider texts never letting anything out of
contract leave), the port (`test_port.py`), the independence from the translator (`test_independence.py`: it runs with
`python -I` and only its own `src/`), and conformance with the translator's port (`test_conformance.py`: the
combinator-port vectors, copied into `tests/vectors/` by the translator's `integration/tools/vectors.py`, and generated
outputs, give the same verdict on both sides).

## Releasing a change

Edit the instructions or the runner, bump `version` in `pyproject.toml` and `__version__` in
`src/epinoic_combinator/__init__.py` (the suite checks they agree) and, for an edit of the instructions,
`PACK_VERSION` in `src/epinoic_combinator/pack.py`; run the suite. An edit of either pack file changes the pack's digest
by itself, and the service pins the digest, so a new pack is attached only when the service pins it.

## A repository of its own (split-ready)

Everything this package needs is in this directory; its tests reach the translator only through `../src` when it is
there. To give it its own repository, the owners run, from the translator repository's root:

```
git subtree split --prefix combinator -b combinator-split     # history of combinator/ only, on a new local branch
git push <new-repository-url> combinator-split:main           # an owner's action: no repository is created or pushed here
```

Then, in the translator repository, `integration/tools/generate.py` and `vectors.py` stop writing the copies (they write
them only while `combinator/` exists here); publish a contract change by copying the generated files into the new
repository's `src/epinoic_combinator/contract/` and the vectors into its `tests/vectors/`. Decision D33 of the
translator's `integration/DECISIONS.md` records who maintains it and whether it moves.
