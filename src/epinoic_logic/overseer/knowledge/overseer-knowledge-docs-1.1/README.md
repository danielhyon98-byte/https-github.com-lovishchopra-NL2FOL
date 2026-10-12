# Overseer knowledge pack: deployment guide

This directory is the whole configuration of an **overseer agent**: a reviewer that reads one dossier (the recorded
transfers between the agents of one tutoring task) and returns one verdict (a list of accusations pinned to that
dossier). This README is for whoever deploys the pack. It is **never** sent to a model.

The pack names itself in `manifest.json` (`pack_name`, `pack_version`, `pack_sha256`). The same name and version open
`master_prompt.txt` (its `PACK:` line).

## 1. What a verdict is worth

Nothing on its own. A verdict is an agent output. The infrastructure parses it strictly as data, checks its header
against the dossier it issued, validates every accusation against its journal of transfers and its signed engine
results, and never obeys it. Only an accusation that a deterministic check confirms reaches the router, and then
through that check's own finding, never through the agent's words. Correctness rests on that code and on the signed
engine results, never on the model. Engine results prove properties of the encoded problems only; neither they nor a
verdict show that any claim is true.

## 2. Files

| File | Audience | Purpose |
| --- | --- | --- |
| `master_prompt.txt` | agent | read first: the procedure, the non-negotiables, lenses and modes, the authority order |
| `01-role-and-trust.md` to `09-when-unsure.md` | agent | the numbered knowledge documents, in name order |
| `README.md` | deployer | this guide; never sent to a model |
| `verdict.schema.json` | machine | JSON Schema of the verdict contract, generated from the infrastructure's code |
| `dossier.schema.json` | machine | JSON Schema of the dossier contract, generated from the infrastructure's code |
| `manifest.json` | machine | versions, every file's size and SHA-256, the system order, the system digest, the pack digest |

The pack holds no key, no credential and no model name. No key is needed to run an overseer agent; never give one to
it.

## 3. Verify the pack

With the infrastructure's package installed:

```
python -m epinoic_logic.overseer.export --verify DIR_OR_ZIP
```

It prints one JSON line with the pack's identity, or the reason it refuses the pack with exit status 2. Without the
package, check by hand:

1. Each file listed in `manifest.json` `files` has exactly the listed `bytes` and `sha256` (SHA-256 over the bytes
   as stored). No other file is present besides `manifest.json`.
2. `pack_sha256` is the SHA-256 of the manifest without its `pack_sha256` member, written as canonical JSON: keys
   sorted, separators `,` and `:` with no spaces, UTF-8 with no ASCII escaping.
3. `pack_sha256` equals the digest the infrastructure you report to accepts for this name and version. A pack whose
   digest differs is refused by the infrastructure, whatever its manifest says.

Every file is UTF-8 with LF line endings and no byte-order mark. Never let a checkout or a transfer rewrite line
endings: the digests would no longer match.

```python
import hashlib, json, pathlib

pack = pathlib.Path("overseer-knowledge-docs-1.1")
manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
for f in manifest["files"]:
    data = (pack / f["path"]).read_bytes()
    assert len(data) == f["bytes"] and hashlib.sha256(data).hexdigest() == f["sha256"], f["path"]
body = {k: v for k, v in manifest.items() if k != "pack_sha256"}
canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["pack_sha256"]
```

## 4. Configure the model

The system configuration is built by one fixed rule from the manifest:

- For each path in `system_order` (the master prompt, then the numbered documents): the separator line, which is
  `system_separator` with `{path}` replaced by the path; a newline; the file's text without its trailing newlines;
  and a newline.
- Join these parts with one blank line between them.
- The SHA-256 of the resulting text (UTF-8) must equal `system_sha256`.

```python
parts = []
for path in manifest["system_order"]:
    text = (pack / path).read_text(encoding="utf-8").rstrip("\n")
    parts.append(manifest["system_separator"].replace("{path}", path) + "\n" + text + "\n")
system = "\n".join(parts)
assert hashlib.sha256(system.encode("utf-8")).hexdigest() == manifest["system_sha256"]
```

Never edit, shorten, summarise, translate or reorder a document, and never add instructions of your own: any change is a
new pack version (section 8). Never send this README, the schemas or the manifest to the model as instructions.

Model settings: temperature 0 where the model supports it; an output budget of at least 8,000 tokens; a JSON or
structured-output mode with `verdict.schema.json` where the model supports one. Record the settings you used with every
verdict you return.

**Input budget.** Provision the context window for the system text, the largest dossier and the output together:

- the system text of this version is 210,981 characters (about 26,600 words; roughly 53,000 tokens at four characters
  a token);
- a dossier has no fixed total size: the infrastructure cuts each string field at 20,000 characters, and the dossiers of
  the contained rounds measured so far ran from 36 KB to 301 KB (roughly 9,000 to 75,000 tokens). Measure the largest
  dossier your infrastructure issues (its canonical JSON) before choosing a model;
- the output budget above (8,000 tokens).

With the dossiers measured so far, that is about 136,000 tokens: deploy on a model whose context window is at least
160,000 tokens. Never shorten the system text or a dossier to fit a smaller window: a dossier the model cannot read whole
is not reviewed. In informed mode the documents tell the agent not to repeat the comparisons the infrastructure's checks
already make, so the work per dossier is what no check decides (Dossier guide D6).

## 5. One dossier in

The user message is one dossier exactly as the infrastructure issued it for that agent and that pack. One dossier per
call, one call per dossier. Send it either as the bare dossier JSON, or inside the data block the infrastructure's own
runner uses:

- a line `<<<DATA dossier>>>`;
- the dossier as JSON with keys sorted, two-space indentation and non-ASCII characters kept, except that the characters
  U+0085, U+2028 and U+2029 are written as the JSON escapes `\u0085`, `\u2028` and `\u2029`, so that no line of the
  block can be taken for a delimiter;
- a line `<<<END dossier>>>`.

The master prompt tells the agent this input shape. Never edit the dossier, never merge two dossiers, and never send a
dossier to an agent other than the one it names (`agent_id`, `lens`, `pack`): the infrastructure refuses the verdict.

## 6. One verdict out

Return the model's reply text **unchanged** to the infrastructure's verdict intake, with the agent id and task id the
dossier names. Never fill in, correct, reformat or retry a reply with altered instructions: an invalid verdict must be
seen as invalid, and it is recorded against the agent. A reply of exactly `{"no_dossier": true}` means the agent saw no
dossier; the intake records it as no review. Only a reply that carries the issued dossier's digest uses up the
dossier: any other reply is refused and the dossier stays open for the agent's own verdict.

**Pack identity outside the runner is self-reported.** A verdict names its pack by the header the model copied from the
dossier. For an agent run outside the package's runner, that proves only that the header was copied, not which system
text the model ran under. Record the pack you deployed in the bookkeeping you return with the reply
(`provider_info.prompt_version` as `<pack name>/<version>+<first 16 hex of the pack digest>`): the intake refuses a
verdict whose bookkeeping names another pack than the dossier's, and records every verdict submitted outside the runner
as self-reported.

`verdict.schema.json` describes the verdict for structured-output modes. The intake validates against the
infrastructure's own contract, not against this file.

## 7. Running it with the infrastructure's runner

The package's agent runner does all of the above:

```python
from epinoic_logic.overseer.pack import load_pack
from epinoic_logic.overseer.runner import OverseerAgentRunner

pack = load_pack("overseer-knowledge-docs-1.1")       # every digest checked; refused if tampered
runner = OverseerAgentRunner(pack, provider, agent_id="overseer-content-1", lens="content_fidelity")
run = runner.run(dossier, intake)                     # one provider call; the reply goes to the intake unchanged
```

`provider` is any object with a `name` and `complete(system, user, *, prompt_version)` returning the raw reply text
and its bookkeeping. The runner refuses a dossier issued for another agent, lens or pack before any call, records a
provider failure as no review, and never gives a verdict any authority.

## 8. Several instances

The infrastructure may run several overseer agents, called instances, on one batch of dossiers. Its pool decides how
many, deterministically: one by default; more when the dossiers exceed a per-instance quota, or when an answer in a
task repeats a fault, never more than a configured maximum (four unless configured otherwise). A dossier whose task has a
repeated fault goes to at least two independent instances, and their verdicts are combined by the infrastructure's rule
(checks decide, never votes). The plan is recorded in the signed review audit.

- Configure every instance from this same pack, unchanged, with its own agent id. Deploy every instance on the cheapest
  model tier: correctness rests on the infrastructure's deterministic code and its signed engine results, never on the
  model.
- Give each instance only its own dossier. Never show one instance another's verdict, and never merge or edit replies.
- The infrastructure's pool builds its instances itself:

```python
from epinoic_logic.overseer.pool import OverseerPool, PoolConfig

pool = OverseerPool(pack, provider_factory, config=PoolConfig(max_instances=4))   # provider_factory(agent_id) -> provider
review = hub.review_pool(task_keys, pool)               # one dossier per task; repeated-fault dossiers to two instances
```

When several agents answer one input, the infrastructure consolidates their answers into one signed consolidated
response; an informed dossier shows it under `consolidations`. The pack tells the agent how to review it. An instance
never produces, approves or changes a consolidation.

## 9. Versions and upgrades

- The pack version is `MAJOR.MINOR`. MINOR changes wording, examples and corrections; MAJOR changes a contract, a kind
  or the copied header.
- The verdict and dossier contract versions are named in `manifest.json`; a pack written for other contract versions
  is refused.
- A version whose digest the infrastructure has accepted never changes. Any byte change is a new version.
- Deploy a new version only after the infrastructure accepts its digest. Every verdict names the pack it was produced
  under; never pool measurements across pack versions without saying so.
