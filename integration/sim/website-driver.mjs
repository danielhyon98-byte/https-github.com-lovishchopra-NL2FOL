// The simulation's website driver (PROTOCOL.md section 14.5, step 2): replays every simulated user of users.json through the
// website path of a DISPOSABLE export of the website (in-process handleRequest / handleChat, the export's own
// tests/helpers/d1.js on node:sqlite, a fake clock, fetch limited to loopback, synthetic principals).
//
// Invariants:
// - it runs only on a directory that carries UNREVIEWED-SIMULATION-COPY.txt (an export, never a checkout or a branch);
// - every fetch that is not to a loopback host is refused before it is sent (no provider, no network);
// - it needs the verified backend in the export (patch set M applied: src/verify/with-verification.js and the W3
//   handler wiring); without it, it exits 3 and names what is missing, and run_sim.py reports the website-path gates
//   NOT RUN with that reason, never PASS.
//
// Usage: node website-driver.mjs --website <export> --service <http://127.0.0.1:port> --token-file <file>
//        --users <users.json> --corpus <round copy> --out <dir>
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const missing = [];
if (!args.website || !existsSync(join(args.website, "UNREVIEWED-SIMULATION-COPY.txt"))) missing.push("a disposable website export (UNREVIEWED-SIMULATION-COPY.txt)");
for (const f of ["src/verify/with-verification.js", "src/verify/release-gate.js", "tests/helpers/d1.js"]) {
  if (!args.website || !existsSync(join(args.website, f))) missing.push(f);
}
if (missing.length > 0) {
  console.error(`not runnable: the export has no verified backend (patch set M not applied): missing ${missing.join(", ")}`);
  process.exit(3);
}

// Loopback only: replace fetch before anything of the export is imported.
const realFetch = globalThis.fetch;
globalThis.fetch = async (input, init) => {
  const url = new URL(typeof input === "string" ? input : input.url);
  if (!["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) throw new Error(`the simulation refuses non-loopback host ${url.hostname}`);
  return realFetch(input, init);
};

// The replay loop over users.json is connected in phase 2 with the patched export's handler options
// (options.verified.inner = the simulation's specialist orchestrator over the agents copy's offline runtime). Until a
// patched export exists this driver stops at the prerequisite check above; it never fabricates a turn.
mkdirSync(args.out, { recursive: true });
writeFileSync(join(args.out, "website-driver.json"), JSON.stringify({ status: "not connected", reason: "the replay loop is connected in phase 2" }, null, 1));
console.error("not runnable: the replay loop over users.json is connected in phase 2 (see integration/sim/README.md)");
process.exit(3);
