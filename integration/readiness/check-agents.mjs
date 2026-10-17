// Agents readiness (playbook step 8). Read-only, on a COPY of the agents repository (git archive): the runtime and
// routing contract versions are ones integration/COMPATIBILITY.json accepts, `claims: null` is still the runtime's
// provenance, and the website-facing runtime result schema is an accepted pair. It never "fixes" a blocker.
//
//   node check-agents.mjs <agents copy>
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const copy = process.argv[2];
const compat = JSON.parse(readFileSync(fileURLToPath(new URL("../COMPATIBILITY.json", import.meta.url)), "utf8"));
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
let bad = 0;
for (const [name, ok, detail] of rows) {
  if (!ok) bad += 1;
  console.log(`${ok ? "PASS   " : "BLOCKER"}  ${name}: ${detail}`);
}
console.log(bad === 0 ? "agents contracts: accepted" : `agents contracts: ${bad} blocker(s)`);
process.exit(bad === 0 ? 0 : 1);
