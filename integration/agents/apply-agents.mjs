// The kit's applier for the agents changes A3 and A5 (integration/agents/PATCH-PLAN.md; patches/agents-A3-A5.json).
//
//   node integration/agents/apply-agents.mjs --target <archive copy of the agents repository> [--check] [--patch <file>]
//
// Invariants:
// - it writes only into an archive copy (a `git archive` of the agents repository whose .kit-archive-commit names the
//   commit it was made from), never into a checkout or a branch: the changes go on a branch of the agents repository
//   only with its owner's go (decision D20), by that repository's own commit;
// - every replacement is kit-authored text at an anchor (a short phrase of the agents file) that must occur exactly once
//   before anything is written ("anchor not found" / "anchor not unique": exit 1, nothing written);
// - the copy must be of the commit the replacements were written for (agents_commit), or it refuses (exit 1);
// - --check counts the anchors and writes nothing; --patch writes a unified diff (paths a/<file>, b/<file>).
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const target = opt("--target");
const patchFile = opt("--patch");
const check = args.includes("--check");

function die(message) {
  console.error(message);
  process.exit(1);
}

if (!target) die("usage: apply-agents.mjs --target <archive copy> [--check] [--patch <file>]");
const doc = JSON.parse(readFileSync(join(HERE, "patches", "agents-A3-A5.json"), "utf8"));
const marker = join(target, ".kit-archive-commit");
if (!existsSync(marker)) die("refused: the target is not an archive copy (no .kit-archive-commit); the agents changes are applied only to a copy");
const commit = readFileSync(marker, "utf8").trim();
if (commit !== doc.agents_commit) die(`refused: the copy is of ${commit}, the replacements were written for ${doc.agents_commit}`);

const before = new Map();
const after = new Map();
for (const r of doc.replacements) {
  const path = join(target, r.file);
  if (!existsSync(path)) die(`anchor not found: ${r.file}: ${r.id} (the file is missing)`);
  if (!before.has(r.file)) before.set(r.file, readFileSync(path, "utf8"));
  const current = after.get(r.file) ?? before.get(r.file);
  const n = current.split(r.anchor).length - 1;
  if (n === 0) die(`anchor not found: ${r.file}: ${r.id}`);
  if (n > 1) die(`anchor not unique: ${r.file}: ${r.id}`);
  after.set(r.file, current.replace(r.anchor, () => r.replace));
}

/** A unified diff of one file with three lines of context (a line LCS: the agents files are a few hundred lines). */
function unifiedDiff(file, a, b, context = 3) {
  const x = a.split("\n");
  const y = b.split("\n");
  const n = x.length;
  const m = y.length;
  const lcs = Array.from({ length: n + 1 }, () => new Int32Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) for (let j = m - 1; j >= 0; j -= 1) lcs[i][j] = x[i] === y[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const ops = []; // [kind, xIndex, yIndex]: " " both, "-" x only, "+" y only
  let i = 0;
  let j = 0;
  while (i < n || j < m) {
    if (i < n && j < m && x[i] === y[j]) ops.push([" ", i++, j++]);
    else if (j < m && (i === n || lcs[i][j + 1] >= lcs[i + 1][j])) ops.push(["+", i, j++]);
    else ops.push(["-", i++, j]);
  }
  const out = [`--- a/${file}`, `+++ b/${file}`];
  let k = 0;
  while (k < ops.length) {
    if (ops[k][0] === " ") { k += 1; continue; }
    let lo = Math.max(0, k - context);
    let hi = k;
    while (hi < ops.length) {
      if (ops[hi][0] !== " ") { hi += 1; continue; }
      let run = 0;
      while (hi + run < ops.length && ops[hi + run][0] === " ") run += 1;
      if (hi + run >= ops.length || run > 2 * context) { hi = Math.min(ops.length, hi + context); break; }
      hi += run;
    }
    const part = ops.slice(lo, hi);
    const xs = part.filter((o) => o[0] !== "+").length;
    const ys = part.filter((o) => o[0] !== "-").length;
    out.push(`@@ -${part[0][1] + 1},${xs} +${part[0][2] + 1},${ys} @@`);
    for (const [kind, xi, yi] of part) out.push(kind === "+" ? `+${y[yi]}` : `${kind}${x[xi]}`);
    k = hi;
  }
  return out.join("\n") + "\n";
}

if (check) {
  console.log(`agents changes A3 and A5: ${doc.replacements.length} anchor(s) found exactly once in ${after.size} file(s) of the copy of ${commit}; nothing written`);
  process.exit(0);
}
const diff = [];
for (const [file, text] of after) {
  writeFileSync(join(target, file), text);
  diff.push(unifiedDiff(file, before.get(file), text));
}
if (patchFile) writeFileSync(patchFile, diff.join(""));
console.log(`agents changes A3 and A5 applied to the copy of ${commit}: ${doc.replacements.length} replacement(s) in ${after.size} file(s)${patchFile ? `; diff written to ${patchFile}` : ""}`);
