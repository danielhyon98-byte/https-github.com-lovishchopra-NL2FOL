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
| `manifest.json` | machine | versions, every file's size and SHA-256, the system order, the modules, the digest of the system text of every composition, the pack digest |

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

pack = pathlib.Path("overseer-knowledge-docs-1.4")
manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
for f in manifest["files"]:
    data = (pack / f["path"]).read_bytes()
    assert len(data) == f["bytes"] and hashlib.sha256(data).hexdigest() == f["sha256"], f["path"]
body = {k: v for k, v in manifest.items() if k != "pack_sha256"}
canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["pack_sha256"]
```

## 4. Configure the model

The system configuration is built by one fixed rule from the manifest and the dossier it reviews. Parts of the agent
documents concern one kind of dossier content: each lies between a line `<!-- module: NAME -->` and a line
`<!-- end module: NAME -->`, and `system_modules` lists the modules (`stem`, `translations`). An agent is sent the
core and the modules its dossier needs, so a dossier with neither STEM answers nor translations costs the smallest
configuration:

- Choose the modules the dossier needs. `stem` when it carries a STEM answer: a claim in a transfer's `payload.claims`
  whose `claim_id` is `s`, `m` or `c` followed by digits, a point and digits (`s1.2`), or `s.tail`, `m.tail` or
  `c.tail`; or, in a transfer's `receipt`, a `formal_checks` entry whose `constraint_id` begins `stem-` or a `findings`
  or `structural_findings` entry whose `code` begins `ST-`. `translations` when it carries a translation:
  `links.translations` is not empty, or a receipt's `outcomes` entry has a `translation`.
- For each path in `system_order` (the master prompt, then the numbered documents): the separator line, which is
  `system_separator` with `{path}` replaced by the path; a newline; the file's text with every marker line removed and
  the lines between a pair of markers removed too unless the dossier needs that module, without its trailing newlines;
  and a newline.
- Join these parts with one blank line between them.
- The SHA-256 of the resulting text (UTF-8) must equal the composition's digest in `system_compositions`, under the key
  `core` followed by `+` and each chosen module in the order of `system_modules` (`core`, `core+stem`,
  `core+translations`, `core+stem+translations`). With every module chosen it is `system_sha256` too.

```python
import re

def modules_for(dossier):
    need = set()
    if (dossier.get("links") or {}).get("translations"):
        need.add("translations")
    for t in dossier.get("transfers") or []:
        receipt, payload = t.get("receipt") or {}, t.get("payload") or {}
        if any(o.get("translation") is not None for o in receipt.get("outcomes") or []):
            need.add("translations")
        if any(str(c.get("constraint_id", "")).startswith("stem-") for c in receipt.get("formal_checks") or []) \
                or any(str(f.get("code", "")).startswith("ST-") for k in ("findings", "structural_findings") for f in receipt.get(k) or []) \
                or any(re.fullmatch(r"[smc](?:\d+\.\d+|\.tail)", str(c.get("claim_id", ""))) for c in payload.get("claims") or []):
            need.add("stem")
    return [m for m in manifest.get("system_modules", []) if m in need]

def as_sent(text, modules):
    out, current = [], None
    for line in text.split("\n"):
        opening, closing = re.fullmatch(r"<!-- module: ([a-z]+) -->", line), re.fullmatch(r"<!-- end module: ([a-z]+) -->", line)
        if opening:
            current = opening.group(1)
        elif closing:
            current = None
        elif current is None or current in modules:
            out.append(line)
    return "\n".join(out)

modules = modules_for(dossier)
parts = []
for path in manifest["system_order"]:
    text = as_sent((pack / path).read_text(encoding="utf-8"), modules).rstrip("\n")
    parts.append(manifest["system_separator"].replace("{path}", path) + "\n" + text + "\n")
system = "\n".join(parts)
key = "+".join(["core"] + modules)
assert hashlib.sha256(system.encode("utf-8")).hexdigest() == manifest["system_compositions"][key]
```

Never edit, shorten, summarise, translate or reorder a document, never choose the modules by another rule, and never
add instructions of your own: any change is a new pack version (section 8). The master prompt tells the agent that the
parts it does not receive concern content its dossier does not hold. Never send this README, the schemas or the
manifest to the model as instructions.

Model settings: temperature 0 where the model supports it; an output budget of at least 8,000 tokens; a JSON or
structured-output mode with `verdict.schema.json` where the model supports one. Record the settings you used with every
verdict you return.

**Input budget.** Provision the context window for the system text the dossier's content needs, the dossier and the
output together:

- the system text depends on the dossier (the rule above): the core alone, for a dossier with neither STEM answers nor
  translations, is 215,053 characters (about 29,200 words; roughly 53,800 tokens at four characters a token); the core
  with the STEM module 427,175 characters (roughly 106,800 tokens); with the translations module 311,024 characters
  (roughly 77,800 tokens); with both, the whole text, 523,146 characters (about 73,300 words; roughly 130,800 tokens);
- a dossier has no fixed total size: the infrastructure cuts each string field at 20,000 characters, and the dossiers
  measured so far (the exporter's, for the recorded rounds r2 to r5 and r7, r7's re-keyed pass included) ran from 17 KB
  to 1,297 KB (roughly 4,300 to 324,300 tokens). The largest are tasks of the re-keyed pass, which carry the recorded
  translations with their signed results and joint consistency runs; every other dossier was at most 356 KB (roughly
  89,100 tokens), r7's p7b with its STEM answer. Measure the largest dossier your infrastructure issues (its canonical
  JSON) before choosing a model;
- the output budget above (8,000 tokens).

The dossier figures below were measured with pack 1.3 as it was released. Pack 1.4 is larger: the core by 27,329
characters (the argument diagnosis and the table of every code the translator and the channel emit, about 6,800 tokens)
and the STEM module by 3,074 more (the argument diagnosis's ST codes, about 770 tokens), so every need is about 6,800
tokens more, and one that includes the STEM module about 7,600 more. The dossiers themselves now carry a receipt's and a
signed result's argument diagnosis when they hold one, which is not measured here: measure the largest dossier your
infrastructure issues.
Of the 1,435 dossiers measured, 190 need the core alone (at most about 94,600 tokens with the output), 315 the STEM
module (at most about 196,300), 890 the translations module (at most about 403,200) and 40 both (at most about 336,100).
To review every one under pack 1.3, a model needed a context window of at least 404,000 tokens (the largest need, the
re-keyed p7a's with the translations module, lay about 750 tokens inside it); under pack 1.4 provision at least 411,000. On a window of 160,000 tokens, 95 of them would
not fit (19 tasks, one dossier per lens: r7's p7b and its eight fault variants, with the STEM module, and ten tasks of
the re-keyed pass, bi-t13, cs-t13, ess-t13, maa-t13, mai-t13, p7b and ph-t13 with both modules and bm-t13, ge-t13 and
p7a with the translations module); fifteen of them, the re-keyed cs-t13, mai-t13 and p7a, would not fit with no system
text at all. With the whole text for every dossier, 755 would not fit that window. On a window of 128,000 tokens 480
would not fit (60 of them by less than 2,000 tokens, and 35 that fit do so by less than 2,000), and on one of 200,000
tokens 25 (the re-keyed cs-t13, ess-t13, mai-t13, p7a and p7b). Five dossiers measured (r2's p1, one per lens) fit the
160,000-token window by about 1,000 tokens and none lies within 2,000 tokens of the 200,000-token window, but a dossier
differs by a few bytes from one export to the next. Never shorten the system text or a dossier to fit a smaller window:
a dossier the model cannot read whole is not reviewed. In informed mode the documents tell the
agent not to repeat the comparisons the infrastructure's checks already make, so the work per dossier is what no check
decides (Dossier guide D6).

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

pack = load_pack("overseer-knowledge-docs-1.4")       # every digest checked; refused if tampered
runner = OverseerAgentRunner(pack, provider, agent_id="overseer-content-1", lens="content_fidelity")
run = runner.run(dossier, intake)                     # one provider call; the reply goes to the intake unchanged
```

`provider` is any object with a `name` and `complete(system, user, *, prompt_version)` returning the raw reply text
and its bookkeeping. The runner refuses a dossier issued for another agent, lens or pack before any call, records a
provider failure as no review, and never gives a verdict any authority. It sends each dossier the composition its
content needs (section 4) and records that composition's modules and digest with the run.

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
