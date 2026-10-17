// The simulation's agents driver (PROTOCOL.md section 14.5): without the website, the agents router (synthetic catalogue) ->
// router-port.js -> the offline runtime -> the specialist port -> the checks service, for STEM, duplicate, combined
// and clarify turns.
//
// Invariants: it runs on a COPY of the agents repository (git archive), never a checkout; fetch is limited to loopback;
// the runtime is the copy's createOfflineTestRuntime with its synthetic bundle; the router never fans out (a mixed
// request is a clarification). Without the checks service (the service refused to start) or a copy it exits 3 and
// names what is missing.
//
// Usage: node agents-driver.mjs --agents <copy> --service <http://127.0.0.1:port> --token-file <file> --users <users.json>
//        --corpus <round copy> --out <dir>
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => (a.startsWith("--") ? [...acc, [a.slice(2), all[i + 1]]] : acc), []));
const missing = [];
for (const f of ["specialist-runtime/src/index.js", "specialist-runtime/fixtures/synthetic/harness.js", "specialist-routing/package.json"]) {
  if (!args.agents || !existsSync(join(args.agents, f))) missing.push(f);
}
if (!args.service) missing.push("a running checks service (--service)");
if (missing.length > 0) {
  console.error(`not runnable: missing ${missing.join(", ")}`);
  process.exit(3);
}
mkdirSync(args.out, { recursive: true });
writeFileSync(join(args.out, "agents-driver.json"), JSON.stringify({ status: "not connected", reason: "the agents turns are connected in phase 2" }, null, 1));
console.error("not runnable: the agents turns are connected in phase 2 (see integration/sim/README.md)");
process.exit(3);
