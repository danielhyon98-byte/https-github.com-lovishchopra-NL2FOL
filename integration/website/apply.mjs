// The kit's anchor applier for the website (playbook step 10; website/PATCH-PLAN.md).
//
//   node integration/website/apply.mjs --base M --target <export> [--verify] [--work-branch] [--steps W1,...]
//
// Invariants:
// - it applies only kit-authored material: the modules of website/src/verify/ and the kit's tests are copied as they
//   are, the vectors are copied into tests/fixtures/kit/, and each edit of an existing website file is one block of
//   website/blocks/<base>/ inserted at its anchor; nobody writes gate code by hand;
// - before writing anything it counts every block's anchor in the target and refuses (exit 1, nothing written) when a
//   count differs from ANCHORS.md: "anchor not found: <file>: <anchor>" or "anchor not unique: <file>: <anchor>";
// - it runs only on a disposable export (UNREVIEWED-SIMULATION-COPY.txt) unless --work-branch says the target is the
//   local website work branch a lifted G0 and the user's request allow;
// - with --verify it compares every file it touched with patches/<base>/RESULT.sha256 and prints "exact" (exit status
//   0) or "drift" with the drifted files (exit status 3: the files written are not the tested patch set, so playbook
//   step 10 stops; a refusal, with nothing written, is exit status 1).
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const KIT_WEBSITE = dirname(fileURLToPath(import.meta.url));
const KIT_ROOT = join(KIT_WEBSITE, "..", "..");
const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : undefined;
};
const base = opt("--base") ?? "M";
const target = opt("--target");
const verify = args.includes("--verify");
const writeResult = args.includes("--write-result");
const workBranch = args.includes("--work-branch");
// --steps W1 (or W1,W3,...): apply only these W-steps' blocks (the rollback rehearsal's "W1 alone"); copies always go.
const steps = opt("--steps")?.split(",").map((s) => s.trim()).filter(Boolean) ?? null;

function die(message) {
  console.error(message);
  process.exit(1);
}

if (!target) die("usage: apply.mjs --base M --target <export> [--verify]");
if (!existsSync(join(target, "UNREVIEWED-SIMULATION-COPY.txt")) && !workBranch) {
  die("refused: the target is not a disposable export (no UNREVIEWED-SIMULATION-COPY.txt); pass --work-branch only for the local work branch");
}
const blocksDir = join(KIT_WEBSITE, "blocks", base);
if (!existsSync(blocksDir)) die(`website base ${base} has no tested patch material in this kit`);

// ----------------------------------------------------------------------------------------- inputs

function anchorTable() {
  const rows = readFileSync(join(KIT_WEBSITE, "ANCHORS.md"), "utf8").split("\n").filter((l) => l.startsWith("| `") && !l.startsWith("| `File"));
  const table = new Map();
  for (const line of rows) {
    const cells = line.split(" | ").map((c) => c.replace(/^\|\s*/, "").replace(/\s*\|$/, "").trim());
    const file = cells[0].replaceAll("`", "");
    const anchor = cells[1].replace(/^`|`$/g, "").replaceAll("\\|", "|");
    table.set(`${file}\u0000${anchor}`, Number(cells[2]));
  }
  return table;
}

function readBlocks() {
  return readdirSync(blocksDir).filter((f) => f.endsWith(".block")).sort().map((name) => {
    const text = readFileSync(join(blocksDir, name), "utf8");
    const split = text.indexOf("\n---\n");
    const head = Object.fromEntries(text.slice(0, split).split("\n").map((l) => [l.slice(0, l.indexOf(":")), l.slice(l.indexOf(":") + 2)]));
    const body = text.slice(split + 5).replace(/\n$/, "");
    return { name, step: head["kit-block"], file: head.file, anchor: head.anchor, mode: head.mode, body };
  });
}

const count = (text, needle) => text.split(needle).length - 1;
const sha256 = (path) => createHash("sha256").update(readFileSync(path)).digest("hex");

function listFiles(dir) {
  const out = [];
  for (const name of readdirSync(dir).sort()) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...listFiles(p));
    else out.push(p);
  }
  return out;
}

// ----------------------------------------------------------------------------------------- the copies

function copies() {
  const out = [];
  for (const f of readdirSync(join(KIT_WEBSITE, "src", "verify")).filter((n) => n.endsWith(".js"))) {
    out.push([join(KIT_WEBSITE, "src", "verify", f), join("src", "verify", f)]);
  }
  for (const dir of ["tests", "tests-website"]) {
    const d = join(KIT_WEBSITE, dir);
    if (!existsSync(d)) continue;
    for (const f of readdirSync(d).filter((n) => n.endsWith(".js"))) out.push([join(d, f), join("tests", f)]);
  }
  for (const folder of ["canonical", "handshake", "decision-table", "verdict-binding", "chat-contract", "codes", "specialist-port"]) {
    const src = join(KIT_ROOT, "integration", "vectors", folder);
    for (const p of listFiles(src)) out.push([p, join("tests", "fixtures", "kit", folder, relative(src, p))]);
  }
  return out;
}

// ----------------------------------------------------------------------------------------- apply

const table = anchorTable();
const blocks = readBlocks().filter((b) => steps === null || steps.includes(b.step));
const problems = [];
for (const b of blocks) {
  const key = `${b.file}\u0000${b.anchor}`;
  if (!table.has(key)) {
    problems.push(`block ${b.name}: its anchor is not in ANCHORS.md: ${b.file}: ${b.anchor}`);
    continue;
  }
  const path = join(target, b.file);
  const found = existsSync(path) ? count(readFileSync(path, "utf8"), b.anchor) : 0;
  const expected = table.get(key);
  if (found === 0) problems.push(`anchor not found: ${b.file}: ${b.anchor}`);
  else if (found !== expected) problems.push(`anchor not unique: ${b.file}: ${b.anchor} (${found}, expected ${expected})`);
}
const plannedCopies = copies();
for (const [src, rel] of plannedCopies) {
  const dest = join(target, rel);
  if (existsSync(dest) && readFileSync(dest, "utf8") !== readFileSync(src, "utf8")) problems.push(`refused: ${rel} already exists with other content`);
}
if (problems.length > 0) die(problems.join("\n"));

if ((verify || writeResult) && steps !== null) die("--verify and --write-result concern the whole patch set; they cannot be combined with --steps");
const touched = new Set();
for (const [src, rel] of plannedCopies) {
  const dest = join(target, rel);
  mkdirSync(dirname(dest), { recursive: true });
  copyFileSync(src, dest);
  touched.add(rel);
}
for (const b of blocks) {
  const path = join(target, b.file);
  const lines = readFileSync(path, "utf8").split("\n");
  const out = [];
  for (const line of lines) {
    if (!line.includes(b.anchor)) {
      out.push(line);
      continue;
    }
    const indent = line.match(/^\s*/)[0];
    const body = b.body.replaceAll("{{indent}}", indent);
    if (b.mode === "replace") out.push(line.replace(b.anchor, body));
    else if (b.mode === "replace-line") out.push(body);
    else if (b.mode === "before-line") out.push(body, line);
    else if (b.mode === "after-line") out.push(line, body);
    else die(`block ${b.name}: unknown mode ${b.mode}`);
  }
  writeFileSync(path, out.join("\n"));
  touched.add(b.file);
}

const files = [...touched].sort();
console.log(`applied ${blocks.length} block(s) and ${plannedCopies.length} file(s) for base ${base}:`);
for (const f of files) console.log(`  ${f}`);

const resultPath = join(KIT_WEBSITE, "patches", base, "RESULT.sha256");
const digests = files.map((f) => `${sha256(join(target, f))}  ${f}`).join("\n") + "\n";
if (writeResult) {
  mkdirSync(dirname(resultPath), { recursive: true });
  writeFileSync(resultPath, digests);
  console.log(`wrote ${relative(KIT_ROOT, resultPath)}`);
}
if ((verify || writeResult) && steps !== null) die("--verify and --write-result concern the whole patch set; they cannot be combined with --steps");
if (verify) {
  const expected = new Map(readFileSync(resultPath, "utf8").trim().split("\n").map((l) => [l.slice(66), l.slice(0, 64)]));
  const drift = files.filter((f) => expected.get(f) !== sha256(join(target, f)));
  const missing = [...expected.keys()].filter((f) => !touched.has(f));
  if (drift.length === 0 && missing.length === 0) console.log("exact");
  else {
    console.log("drift");
    for (const f of [...drift, ...missing]) console.log(`  ${f}`);
    process.exitCode = 3; // not the tested patch set: a caller that reads only the exit status stops too
  }
}
