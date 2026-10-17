// The W0 drafter (playbook step 4; website/PATCH-PLAN.md, W0): Bruno's docs change that records the 17 October 2026
// requirement ("Z3 is required on the delivery path") and lifts gate G0, prepared as a PATCH FILE for Bruno.
//
//   node integration/website/W0/draft-w0.mjs --target <disposable export> [--patch <file>]
//
// Invariants:
// - it writes only into a disposable export (UNREVIEWED-SIMULATION-COPY.txt) and, with --patch, one patch file; it
//   never touches a website checkout or branch, never commits, never pushes: W0 is Bruno's to merge;
// - every edit is one replacement of w0.json, at an anchor (a short website phrase) whose count must be exactly 1
//   before anything is written ("anchor not found" / "anchor not unique": exit 1, nothing written); every replacement
//   text is kit-authored;
// - it changes the deferral sentences of five documents and nothing else, and it adds the positive marker
//   epinoic.integration.v1 to docs/current-state.md, so check-website.mjs --g0-export reads the draft as "lifted";
// - the patch is a unified diff with paths a/<file> and b/<file> relative to the website's root, so Bruno (or
//   `git -C <website> apply --check <patch>`) can apply or check it against origin/main.
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

function die(message) {
  console.error(message);
  process.exit(1);
}

if (!target) die("usage: draft-w0.mjs --target <disposable export> [--patch <file>]");
if (!existsSync(join(target, "UNREVIEWED-SIMULATION-COPY.txt"))) {
  die("refused: the target is not a disposable export (no UNREVIEWED-SIMULATION-COPY.txt); W0 is drafted only in an export");
}
const doc = JSON.parse(readFileSync(join(HERE, "w0.json"), "utf8"));

/** The new text of `text` after one replacement, or a refusal string. */
function applyOne(text, r) {
  if (r.mode === "line") {
    const lines = text.split("\n");
    const at = lines.flatMap((l, i) => (l.startsWith(r.anchor) ? [i] : []));
    if (at.length === 0) return { error: "anchor not found" };
    if (at.length > 1) return { error: "anchor not unique" };
    lines[at[0]] = r.replace;
    return { text: lines.join("\n") };
  }
  const n = text.split(r.anchor).length - 1;
  if (n === 0) return { error: "anchor not found" };
  if (n > 1) return { error: "anchor not unique" };
  if (r.mode === "text") return { text: text.replace(r.anchor, () => r.replace) };
  if (r.mode === "tail") {
    const start = text.indexOf(r.anchor);
    const end = text.indexOf("\n", start);
    return { text: text.slice(0, start) + r.replace + (end < 0 ? "" : text.slice(end)) };
  }
  return { error: `unknown mode ${r.mode}` };
}

/** A unified diff of one file whose line count did not change (every W0 edit replaces within a line). */
function unifiedDiff(file, before, after, context = 3) {
  const a = before.split("\n");
  const b = after.split("\n");
  if (a.length !== b.length) throw new Error(`${file}: a W0 edit changed the number of lines`);
  const changed = a.flatMap((l, i) => (l !== b[i] ? [i] : []));
  if (changed.length === 0) return "";
  const hunks = [];
  for (const i of changed) {
    const lo = Math.max(0, i - context);
    const hi = Math.min(a.length - 1, i + context);
    const last = hunks[hunks.length - 1];
    if (last && lo <= last.hi + 1) last.hi = Math.max(last.hi, hi);
    else hunks.push({ lo, hi });
  }
  const out = [`--- a/${file}`, `+++ b/${file}`];
  for (const h of hunks) {
    const len = h.hi - h.lo + 1;
    out.push(`@@ -${h.lo + 1},${len} +${h.lo + 1},${len} @@`);
    for (let i = h.lo; i <= h.hi; i += 1) {
      if (a[i] === b[i]) out.push(` ${a[i]}`);
      else out.push(`-${a[i]}`, `+${b[i]}`);
    }
  }
  return out.join("\n") + "\n";
}

const before = new Map();
const after = new Map();
for (const r of doc.replacements) {
  const path = join(target, r.file);
  if (!existsSync(path)) die(`anchor not found: ${r.file}: ${r.anchor} (the file is missing)`);
  if (!before.has(r.file)) before.set(r.file, readFileSync(path, "utf8"));
  const current = after.get(r.file) ?? before.get(r.file);
  const res = applyOne(current, r);
  if (res.error) die(`${res.error}: ${r.file}: ${r.anchor}`);
  after.set(r.file, res.text);
}
// every anchor was found exactly once: now, and only now, write
const patch = [];
for (const [file, text] of after) {
  writeFileSync(join(target, file), text);
  patch.push(unifiedDiff(file, before.get(file), text));
}
if (patchFile) writeFileSync(patchFile, patch.join(""));
console.log(`W0 drafted in the export: ${doc.replacements.length} replacement(s) in ${after.size} file(s)${patchFile ? `; patch written to ${patchFile}` : ""}`);
console.log("Check it with: node integration/readiness/check-website.mjs --g0-export <export>   (expected: lifted)");
