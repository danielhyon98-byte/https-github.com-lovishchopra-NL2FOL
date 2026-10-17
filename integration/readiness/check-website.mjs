// Website readiness (playbook steps 4 and 9). Read-only: it reads origin/main with `git show` (it never fetches,
// checks out, branches or commits) and reads a disposable export's files.
//
//   node check-website.mjs --g0 <website checkout>      gate G0 on origin/main: lifted | in force | inconsistent
//   node check-website.mjs --g0-export <export>         the same rule on an export's files: a W0 draft
//                                                       (website/W0/draft-w0.mjs) is checked here, never on origin/main
//   node check-website.mjs --base <website checkout>    the website base on origin/main: M (no src/chat/pilot.js) or P
//   node check-website.mjs --anchors <export>           the anchor counts of integration/website/ANCHORS.md
//
// G0 is decided ONLY by --g0 on origin/main; --g0-export says what a draft would give once Bruno merges it.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const [mode, target] = process.argv.slice(2);
const fromExport = mode === "--g0-export";
const show = (path) => {
  if (fromExport) {
    const p = `${target}/${path}`;
    return existsSync(p) ? readFileSync(p, "utf8") : null;
  }
  try {
    return execFileSync("git", ["-C", target, "show", `origin/main:${path}`], { encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return null;
  }
};
const count = (text, needle) => (text === null ? null : text.split(needle).length - 1);

if (mode === "--g0" || mode === "--g0-export") {
  const current = show("docs/current-state.md");
  const architecture = show("docs/architecture.md");
  const brief = show("docs/handoff/05-integration-planning-brief.md");
  const notice = show("docs/handoff/04-logic-translator.md");
  const deferrals = [
    count(current, "Z3 remains deferred"),
    count(architecture, "Z3 logic translator is **deferred**"),
    count(brief, "Website Z3 integration stays deferred"),
    notice === null ? null : count(notice.split("\n").slice(0, 3).join("\n"), "Deferred by Bruno"),
  ];
  const positive = count(current, "epinoic.integration.v1");
  let state = "inconsistent";
  if (deferrals.every((n) => n === 0) && positive !== null && positive >= 1) state = "lifted";
  else if (deferrals.every((n) => n !== null && n >= 1)) state = "in force";
  console.log(JSON.stringify({ deferrals, positive }));
  console.log(fromExport ? `G0 on the export (a draft, not the published main): ${state}` : `G0 on origin/main: ${state}`);
  process.exit(0);
}

if (mode === "--base") {
  console.log(show("src/chat/pilot.js") === null ? "M" : "P");
  process.exit(0);
}

if (mode === "--anchors") {
  const anchorsFile = fileURLToPath(new URL("../website/ANCHORS.md", import.meta.url));
  const rows = readFileSync(anchorsFile, "utf8").split("\n").filter((l) => l.startsWith("| `") && !l.startsWith("| `File"));
  let bad = 0;
  for (const line of rows) {
    const cells = line.split(" | ").map((c) => c.replace(/^\|\s*/, "").trim());
    const file = cells[0].replaceAll("`", "");
    const anchor = cells[1].replace(/^`|`$/g, "").replaceAll("\\|", "|");
    const expected = Number(cells[2]);
    const path = `${target}/${file}`;
    const found = existsSync(path) ? readFileSync(path, "utf8").split(anchor).length - 1 : 0;
    const ok = found === expected;
    if (!ok) bad += 1;
    console.log(`${ok ? "ok  " : "BAD "} ${file}: ${found}/${expected}  ${anchor.slice(0, 80)}`);
  }
  console.log(bad === 0 ? "anchors: every count as expected" : `anchors: ${bad} count(s) differ`);
  process.exit(bad === 0 ? 0 : 1);
}

console.error("usage: check-website.mjs --g0 <checkout> | --g0-export <export> | --base <checkout> | --anchors <export>");
process.exit(2);
