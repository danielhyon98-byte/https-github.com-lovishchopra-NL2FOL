// Agents readiness (playbook steps 8 and 9a). Read-only, on COPIES (git archive) of the agents repositories and on
// disposable website exports: it never "fixes" a blocker.
//
//   node check-agents.mjs <agents copy>
//       one copy (unchanged): the runtime contract is one integration/COMPATIBILITY.json accepts, the routing contract
//       is the pinned one, and `claims: null` is still the runtime's provenance. PASS or BLOCKER rows.
//   node check-agents.mjs [--runtime <copy>] [--routing <copy>] [--harness <copy>] [--vendored <export> [--kit-tree <tree>]]
//       by role (COMPATIBILITY.json `agents_pins`; the flags combine):
//       --runtime   a copy of the retrained repository (`repositories.agents`) at the runtime pin: its archive commit and
//                   contract are the pin's, `claims: null`, and every entry of its RUNTIME_MANIFEST names the pinned
//                   knowledge-base commit and bundle digest (all BLOCKER);
//       --routing   a copy at the routing pin: its archive commit and routing contract (BLOCKER); whether it accepts the
//                   runtime pin's contract (REPORTED: the website path is History only and unrouted, D9/D10);
//       --harness   a copy of the harness (`repositories.agents_harness`), runtime and routing in one tree: the one-copy
//                   rows and whether its routing accepts its own runtime (BLOCKER); its archive commit against the
//                   harness pin (REPORTED: the harness branch moves; the A3/A5 applier refuses another commit);
//       --vendored  a disposable website export: the vendored runtime's source repository, src tree, contract and
//                   knowledge base against the pins (BLOCKER); the vendored kit's source (REPORTED) and, with
//                   --kit-tree <tree> (`git -C <kit> rev-parse HEAD:integration`), its integration tree (BLOCKER).
//       Status column PASS, BLOCKER or REPORTED (recorded, never a stop). The last line is "agents contracts: accepted"
//       when no row is a BLOCKER. Exit status 1 iff a row is a BLOCKER (2: a usage error).
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { ownerRepo, printable } from "./roles.mjs";

const compat = JSON.parse(readFileSync(fileURLToPath(new URL("../COMPATIBILITY.json", import.meta.url)), "utf8"));

/** The three rows of one copy: [name, ok, detail]. */
function oneCopyRows(copy) {
  const read = (p) => (existsSync(`${copy}/${p}`) ? readFileSync(`${copy}/${p}`, "utf8") : null);
  const rows = [];
  const constants = read("specialist-runtime/src/constants.js");
  const runtime = constants?.match(/RUNTIME_CONTRACT_VERSION\s*=\s*"([^"]+)"/)?.[1] ?? null;
  const accepted = compat.specialist_pairs.map((p) => p.runtime);
  rows.push(["runtime contract", runtime !== null && accepted.includes(runtime), `${runtime} (accepted: ${accepted.join(", ")})`]);
  const routingSrc = read("specialist-routing/src/version.js") ?? "";
  const routing = routingSrc.match(/ROUTING_CONTRACT_VERSION\s*=\s*"([^"]+)"/)?.[1] ?? null;
  rows.push(["routing contract", routing === compat.routing_contract, `${routing} (pinned: ${compat.routing_contract})`]);
  const sources = ["specialist-runtime/src/provenance.js", "specialist-runtime/src/redact.js"].map(read).filter(Boolean).join("\n");
  rows.push(["claims: null", /claims:\s*null/.test(sources), "provenance.claims stays null (claims are extracted by the translator's parsers)"]);
  return rows;
}

if (!(process.argv[2] ?? "").startsWith("--")) {
  const rows = oneCopyRows(process.argv[2]);
  let bad = 0;
  for (const [name, ok, detail] of rows) {
    if (!ok) bad += 1;
    console.log(`${ok ? "PASS   " : "BLOCKER"}  ${name}: ${detail}`);
  }
  console.log(bad === 0 ? "agents contracts: accepted" : `agents contracts: ${bad} blocker(s)`);
  process.exit(bad === 0 ? 0 : 1);
}

// ------------------------------------------------------------------------------------------------- by role

const PASS = "PASS";
const BLOCKER = "BLOCKER";
const REPORTED = "REPORTED";
const FLAGS = ["--runtime", "--routing", "--harness", "--vendored", "--kit-tree"];
const argv = process.argv.slice(2);
const opts = {};
for (let i = 0; i < argv.length; i += 2) {
  const [flag, value] = [argv[i], argv[i + 1]];
  if (!FLAGS.includes(flag) || value === undefined || value.startsWith("--") || Object.hasOwn(opts, flag)) {
    console.error(`usage: check-agents.mjs <copy> | [--runtime <copy>] [--routing <copy>] [--harness <copy>] [--vendored <export> [--kit-tree <tree>]] (at ${flag})`);
    process.exit(2);
  }
  opts[flag] = value;
}
if (opts["--kit-tree"] !== undefined && opts["--vendored"] === undefined) {
  console.error("usage: --kit-tree compares a vendored kit, so it needs --vendored <export>");
  process.exit(2);
}

const PINS = compat.agents_pins;
const PAIRS = compat.specialist_pairs.map((p) => p.runtime);
const rows = [];
const add = (status, name, detail) => rows.push([status, name, detail]);
const readIn = (dir, p) => (existsSync(join(dir, p)) ? readFileSync(join(dir, p), "utf8") : null);
const archiveCommit = (dir) => readIn(dir, ".kit-archive-commit")?.trim() || null;
const runtimeContract = (dir) => readIn(dir, "specialist-runtime/src/constants.js")?.match(/RUNTIME_CONTRACT_VERSION\s*=\s*"([^"]+)"/)?.[1] ?? null;
const claimsNull = (dir) => /claims:\s*null/.test(["specialist-runtime/src/provenance.js", "specialist-runtime/src/redact.js"].map((p) => readIn(dir, p)).filter(Boolean).join("\n"));
const short = (commit) => (typeof commit === "string" ? commit.slice(0, 7) : String(commit));
const json = (dir, p) => {
  const text = readIn(dir, p);
  if (text === null) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { unreadable: true };
  }
};

/** The copy's own routing contract module (specialist-routing/src/version.js): its contract and accepted runtimes. */
async function routingModule(dir) {
  const path = join(dir, "specialist-routing", "src", "version.js");
  if (!existsSync(path)) return { error: "no specialist-routing/src/version.js" };
  try {
    const m = await import(pathToFileURL(path).href);
    return { contract: m.ROUTING_CONTRACT_VERSION ?? null, accepts: Array.isArray(m.ACCEPTED_RUNTIME_CONTRACT_VERSIONS) ? [...m.ACCEPTED_RUNTIME_CONTRACT_VERSIONS] : null };
  } catch (e) {
    return { error: `version.js does not load: ${e.message}` };
  }
}

function archiveRow(name, dir, pin, statusIfDifferent, whyIfDifferent) {
  const commit = archiveCommit(dir);
  const same = commit === pin.commit;
  add(same ? PASS : statusIfDifferent, name, `${commit ?? "no .kit-archive-commit (not an archive copy)"} (pinned: ${pin.commit}, ${pin.branch})${same ? "" : `: ${whyIfDifferent}`}`);
}

if (opts["--runtime"] !== undefined) {
  const dir = opts["--runtime"];
  const pin = PINS.runtime;
  archiveRow("runtime archive commit", dir, pin, BLOCKER, "not the runtime pin");
  const contract = runtimeContract(dir);
  add(contract === pin.contract && PAIRS.includes(pin.contract) ? PASS : BLOCKER, "runtime contract",
    `${contract} (pinned: ${pin.contract}; accepted: ${PAIRS.join(", ")})`);
  add(claimsNull(dir) ? PASS : BLOCKER, "runtime claims: null", "provenance.claims stays null (claims are extracted by the translator's parsers)");
  // Every entry of the runtime's own manifest must name the pinned knowledge base: the commit, and for each slug the
  // kit pins a bundle of (`<slug>_bundle`), its path and digest. An entry without a pinned bundle is a blocker.
  const kb = PINS.knowledge_bases;
  const bundles = Object.fromEntries(Object.entries(kb).filter(([k]) => k.endsWith("_bundle")).map(([k, v]) => [k.slice(0, -"_bundle".length), v]));
  const index = join(dir, "specialist-runtime", "src", "index.js");
  let manifest = null;
  let failure = null;
  if (!existsSync(index)) failure = "no specialist-runtime/src/index.js";
  else {
    try {
      manifest = (await import(pathToFileURL(index).href)).RUNTIME_MANIFEST ?? null;
      if (!manifest || !Array.isArray(manifest.entries) || manifest.entries.length === 0) failure = "RUNTIME_MANIFEST has no entries";
    } catch (e) {
      failure = `the runtime does not load: ${e.message}`;
    }
  }
  if (failure !== null) add(BLOCKER, "runtime knowledge base", failure);
  else {
    const wrong = [];
    for (const e of manifest.entries) {
      const b = Object.hasOwn(bundles, e.slug) ? bundles[e.slug] : null;
      if (e?.source?.commit !== kb.commit) wrong.push(`${e.slug}: knowledge-base commit ${e?.source?.commit ?? null}`);
      if (b === null) wrong.push(`${e.slug}: no bundle pinned in the kit`);
      else if (e.bundleSha256 !== b.sha256 || e?.source?.bundlePath !== b.path) wrong.push(`${e.slug}: bundle ${e?.source?.bundlePath ?? null} ${e.bundleSha256 ?? null}`);
    }
    add(wrong.length === 0 ? PASS : BLOCKER, "runtime knowledge base",
      wrong.length === 0
        ? `${manifest.entries.map((e) => e.slug).join(", ")} at ${short(kb.commit)} (${kb.branch}), bundles as pinned (${Object.entries(bundles).map(([s, b]) => `${s} ${b.sha256.slice(0, 12)}`).join(", ")})`
        : `${wrong.join("; ")} (pinned: ${kb.commit}${Object.entries(bundles).map(([s, b]) => `, ${s} ${b.path} ${b.sha256}`).join("")})`);
  }
}

if (opts["--routing"] !== undefined) {
  const dir = opts["--routing"];
  const pin = PINS.routing;
  archiveRow("routing archive commit", dir, pin, BLOCKER, "not the routing pin");
  const r = await routingModule(dir);
  add(r.contract === compat.routing_contract ? PASS : BLOCKER, "routing contract", `${r.error ?? r.contract} (pinned: ${compat.routing_contract})`);
  const accepts = r.accepts ?? [];
  add(accepts.includes(PINS.runtime.contract) ? PASS : REPORTED, "routing accepts runtime",
    `${r.error ?? `accepts ${accepts.join(", ") || "nothing"}`}${accepts.includes(PINS.runtime.contract) ? `, the runtime pin's ${PINS.runtime.contract}`
      : `; not the runtime pin's ${PINS.runtime.contract}: History only and unrouted on the website (D9/D10); routing over this runtime needs the routing owner's change`}`);
}

if (opts["--harness"] !== undefined) {
  const dir = opts["--harness"];
  archiveRow("harness archive commit", dir, PINS.harness, REPORTED, "the harness branch moved past its pin; the applier refuses this copy, A3/A5 need a re-anchor");
  for (const [name, ok, detail] of oneCopyRows(dir)) add(ok ? PASS : BLOCKER, `harness ${name}`, detail);
  const own = runtimeContract(dir);
  const r = await routingModule(dir);
  const ok = own !== null && (r.accepts ?? []).includes(own);
  add(ok ? PASS : BLOCKER, "harness routing accepts runtime", `${r.error ?? `accepts ${(r.accepts ?? []).join(", ") || "nothing"}`}; the harness runtime is ${own}`);
}

if (opts["--vendored"] !== undefined) {
  const dir = opts["--vendored"];
  const base = existsSync(join(dir, "src", "chat", "pilot.js")) ? "P" : "M";
  const rt = json(dir, "vendor/specialist-runtime/SOURCE.json");
  if (rt === null) add(REPORTED, "vendored runtime", `no vendored runtime (base ${base})`);
  else {
    const pin = PINS.runtime;
    const kb = PINS.knowledge_bases;
    const repo = rt?.source?.repo ?? null;
    add(repo !== null && ownerRepo(repo) === ownerRepo(compat.repositories.agents) ? PASS : BLOCKER, "vendored runtime source",
      `${printable(repo)} ${rt?.source?.branch ?? "-"} ${rt?.source?.commit ?? "-"} (repositories.agents: ${compat.repositories.agents}; a GitHub name or URL)`);
    add(rt?.source?.srcTree === pin.src_tree ? PASS : BLOCKER, "vendored runtime src tree",
      `${rt?.source?.srcTree ?? null} (pinned: ${pin.src_tree}, the runtime pin ${short(pin.commit)})`);
    add(rt?.package?.contractVersion === pin.contract ? PASS : BLOCKER, "vendored runtime contract",
      `${rt?.package?.contractVersion ?? null}, package ${rt?.package?.version ?? null} (pinned: ${pin.contract}, package ${pin.version})`);
    const k = rt?.knowledgeBase ?? {};
    add(k.commit === kb.commit && k.sha256 === kb.history_bundle.sha256 ? PASS : BLOCKER, "vendored knowledge base",
      `${k.commit ?? null} ${k.sha256 ?? null} (pinned: ${kb.commit} ${kb.history_bundle.sha256})`);
  }
  const kit = json(dir, "vendor/logic-translator-kit/SOURCE.json");
  if (kit === null) add(REPORTED, "vendored kit", "no vendored kit");
  else {
    const s = kit?.source ?? {};
    add(REPORTED, "vendored kit source", `${s.repo ?? null} ${s.branch ?? "-"} ${s.commit ?? null}, integration tree ${s.integrationTree ?? null}`);
    if (opts["--kit-tree"] !== undefined) {
      add(s.integrationTree === opts["--kit-tree"] ? PASS : BLOCKER, "vendored kit tree",
        `${s.integrationTree ?? null} (this kit's integration tree: ${opts["--kit-tree"]})`);
    }
  }
}

if (rows.length === 0) {
  console.error("usage: name at least one of --runtime, --routing, --harness, --vendored");
  process.exit(2);
}
let blockers = 0;
for (const [status, name, detail] of rows) {
  if (status === BLOCKER) blockers += 1;
  console.log(`${status.padEnd(8)}  ${name}: ${detail}`);
}
console.log(blockers === 0 ? "agents contracts: accepted" : `agents contracts: ${blockers} blocker(s)`);
process.exit(blockers === 0 ? 0 : 1);
