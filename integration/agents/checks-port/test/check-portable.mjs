// The checks port uses only portable globals (globalThis.crypto.subtle, TextEncoder): no Node.js import in src/.
import { readdirSync, readFileSync } from "node:fs";

const bad = [];
for (const f of readdirSync(new URL("../src/", import.meta.url))) {
  const text = readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
  if (/\bfrom\s+["']node:|\brequire\(|\bprocess\.|\bBuffer\b/.test(text)) bad.push(f);
}
if (bad.length > 0) {
  console.error(`not portable: ${bad.join(", ")}`);
  process.exit(1);
}
console.log("portable");
