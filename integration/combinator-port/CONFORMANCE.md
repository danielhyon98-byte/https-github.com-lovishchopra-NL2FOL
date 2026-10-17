# Combinator conformance (`epinoic.integration.combinator-port.v1`)

The combinator is a **separate agent** in its own sub-project, [`combinator/`](../../combinator/) (package
`epinoic_combinator`, its own `pyproject.toml`, version, instructions, tests and release), edited and released without
touching the Z3 infrastructure. The translator never imports it; the service reaches it only through the combinator
port (PROTOCOL.md section 7) and validates everything it returns as untrusted data. The hub checks every synthesis on
its own: a combinator that passes this conformance has shown that its messages are in contract, never that its
syntheses are faithful.

## What the sub-project exposes

- `epinoic_combinator.port.hello() -> str`: one `combinator-hello.v1` document: `port_version` `1.0`, its release
  (`name`, `version`), the instruction pack it runs (`name`, `version`, `sha256`), the digest of the published contract
  it validates against (`contract_sha256`), `tier: "cheapest"` and the closed vocabulary. No name naming a model.
- `epinoic_combinator.port.combine(input_json, provider=None) -> str`: one `combinator-output.v1` document for the
  `combinator-input.v1` it is given, or one `combinator-refusal.v1` document. Never raises. Without a provider it refuses
  (`provider_unavailable`).
- `python -m epinoic_combinator.export --out <dir>`: its instructions (`INSTRUCTIONS.md`, `output-format.json`) and a
  manifest of their digests, for a workflow or a provider.

At run time it needs nothing but the standard library. It carries the published contract (the four schemas, the
synthesis vocabulary, the port rules) in `src/epinoic_combinator/contract/`, copied there by the kit's
`integration/tools/generate.py`, and the combinator-port and canonical vectors in `tests/vectors/`, copied there by
`integration/tools/vectors.py` (both drift-tested here).

## What its own tests must show (`cd combinator && python -m pytest -q`)

1. **Hello in contract**: `combinator_port.check_hello(hello(), contract_sha256=combinator_port.contract_digest())`
   passes; the pack's identity is stable and changes with any byte of the instructions.
2. **Round trip**: an output's text is its canonical JSON and `dump(check_output(text, input))` is that text; the
   input the port builds is accepted as it is.
3. **The instructions**: they say what it combines (the specialists' answers to one request); name exactly the five
   transformation words; certainty never stronger than the weakest source; every figure, unit, mark, date and quotation
   kept exactly; no note, self-certification, decline or question carried back as a claim; every dropped claim listed
   with its reason; no contradiction merged or hidden (`conflicts`); the exact output format and nothing else.
4. **Named refusals**: every malformed output (prose or a code fence around it, not an object, a key outside the format,
   a value outside a closed set, a text, a dropped reason or a conflict description that is blank or holds a control
   character, a source claim cited twice by one synthesized claim, an unknown citation, too large) and
   every failure of the provider is a refusal with its
   reason and its `KIT-CB` code, the same code the port gives the same message; nothing raises.
5. **Never out of contract**: whatever the provider returns, nothing leaves that `check_output` or `check_refusal`
   refuses (generated provider texts), and on the combinator-port vectors and on generated outputs its own checks give
   the port's verdict.
6. **Independent**: it runs with nothing but its own `src/` on the path (`python -I`) and imports neither the translator,
   the engine, Z3 nor pydantic; one call, no retry; the same input gives the same output in a fresh interpreter.

The first release (`combinator/tests/`) shows all six. The kit runs that suite and shows the other side
(`tests/integration/test_combinator_subproject.py`): a faithful synthesis passes the hub, and each misrepresentation the
combinator lets out because it is in contract (a dropped qualifier, a stronger certainty, a merged contradiction of
formalized claims, an invented figure, a wrong attribution, a carried self-certification, a self-certification label
on a content claim, a self-certification of the synthesis itself, a note carried back as a claim, a figure restated in
another unit or era, a bound or a frequency dropped, a credit to every specialist for one specialist's claim) is named by
the hub on the synthesized claim; a disclosed conflict the hub found no contradiction for is `INT-CONFLICT-006` (info). A
contradiction between claims in prose is not formalized, so the hub names it only through the figures a synthesis
changes or drops (INT-LEDGER-023, INT-LEDGER-024), never as INT-CONFLICT-002. Both sides hold a message passed already
parsed to the same JSON rules as text (a lone surrogate, a float or a non-string key is not protocol JSON, decided
first).

## What the service guarantees whatever the combinator does (phase 2 connects it)

- **Only through the port**: no import of the sub-project; every message checked as untrusted data; an output out of
  contract or a refusal is no synthesis, and the combined answer is not released.
- **The pinned pack**: the service pins one instruction pack by digest in every input; an output under another pack is
  `KIT-CB-005`.
- **The hub decides**: every checked output is relayed through the hub as a `synthesis/1.0` mapping and decided by its
  ledger, conflict and entailment checks; the release decision (`release_decision`) reads that receipt, never the
  combinator's own word.
- **Not offered before it is connected**: until `EPINOIC_COMBINATOR` attaches it (decision D33), the capabilities omit
  `combined` and the checks port refuses it (`KIT-REQ-002`).
