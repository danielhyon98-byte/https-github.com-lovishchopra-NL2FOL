// Canonical JSON of protocol epinoic.integration.v1 (integration/PROTOCOL.md section 1).
//
// Invariants:
// - byte-identical to the translator's canonical_json on every value both accept (golden vectors in
//   integration/vectors/canonical/, run by tests/verify-vectors.test.js);
// - keys are sorted by Unicode code point (not by UTF-16 code unit), separators "," and ":" with no whitespace,
//   non-ASCII written raw, integers only and within Number.MAX_SAFE_INTEGER;
// - no float, NaN, Infinity, lone surrogate, duplicate key or nesting deeper than MAX_DEPTH is ever accepted: each is a
//   CanonicalError naming the rule, never the content.

export const MAX_DEPTH = 64;

export class CanonicalError extends Error {
  constructor(rule) {
    super(rule);
    this.name = "CanonicalError";
  }
}

const SURROGATE = /[\uD800-\uDFFF]/;

/** True when `text` holds an unpaired UTF-16 surrogate (it then has no UTF-8 form). */
export function hasLoneSurrogate(text) {
  if (!SURROGATE.test(text)) return false;
  for (let i = 0; i < text.length; i += 1) {
    const c = text.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff) {
      const d = i + 1 < text.length ? text.charCodeAt(i + 1) : 0;
      if (d >= 0xdc00 && d <= 0xdfff) {
        i += 1;
        continue;
      }
      return true;
    }
    if (c >= 0xdc00 && c <= 0xdfff) return true;
  }
  return false;
}

/** Compare two strings by Unicode code point (what the translator's sort does). */
export function compareCodePoints(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i += 1) {
    let x = a.charCodeAt(i);
    let y = b.charCodeAt(i);
    if (x === y) continue;
    // Move surrogates above U+E000..U+FFFF so UTF-16 order becomes code point order.
    if (x >= 0xd800) x = x >= 0xe000 ? x - 0x800 : x + 0x2000;
    if (y >= 0xd800) y = y >= 0xe000 ? y - 0x800 : y + 0x2000;
    return x - y;
  }
  return a.length - b.length;
}

/** Throws CanonicalError unless `value` is a protocol JSON value. */
export function checkValue(value) {
  const stack = [[value, 0]];
  while (stack.length > 0) {
    const [node, depth] = stack.pop();
    if (depth > MAX_DEPTH) throw new CanonicalError(`the value nests deeper than ${MAX_DEPTH} levels`);
    if (node === null || node === true || node === false) continue;
    const t = typeof node;
    if (t === "number") {
      if (!Number.isInteger(node)) throw new CanonicalError("a float is not allowed (integers only)");
      if (!Number.isSafeInteger(node)) throw new CanonicalError("an integer is outside the safe range (|n| <= 2^53 - 1)");
      continue;
    }
    if (t === "string") {
      if (hasLoneSurrogate(node)) throw new CanonicalError("a string holds a lone surrogate");
      continue;
    }
    if (Array.isArray(node)) {
      for (const child of node) stack.push([child, depth + 1]);
      continue;
    }
    if (t === "object" && Object.getPrototypeOf(node) === Object.prototype || (t === "object" && Object.getPrototypeOf(node) === null)) {
      for (const [key, child] of Object.entries(node)) {
        if (hasLoneSurrogate(key)) throw new CanonicalError("an object key holds a lone surrogate");
        stack.push([child, depth + 1]);
      }
      continue;
    }
    throw new CanonicalError(`a value of type ${t} is not JSON`);
  }
}

function write(node, out) {
  if (node === null || node === true || node === false || typeof node === "number" || typeof node === "string") {
    out.push(JSON.stringify(node));
    return;
  }
  if (Array.isArray(node)) {
    out.push("[");
    node.forEach((child, i) => {
      if (i > 0) out.push(",");
      write(child, out);
    });
    out.push("]");
    return;
  }
  const keys = Object.keys(node).sort(compareCodePoints);
  out.push("{");
  keys.forEach((key, i) => {
    if (i > 0) out.push(",");
    out.push(JSON.stringify(key), ":");
    write(node[key], out);
  });
  out.push("}");
}

/** The canonical text of `value`. Throws CanonicalError for a non-protocol value. */
export function canonicalJson(value) {
  checkValue(value);
  const out = [];
  write(value, out);
  return out.join("");
}

/** Parse one protocol document: no duplicate key, no float, no non-finite constant, no lone surrogate. */
export function parseStrict(text) {
  if (typeof text !== "string") throw new CanonicalError("the document must be text");
  scan(text);
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new CanonicalError("the document is not valid JSON");
  }
  checkValue(value);
  return value;
}

// One forward pass over the text (O(n)): refuses a number with a fraction or an exponent and an object that repeats a
// key. Text it cannot read is left to JSON.parse, which refuses it right after.
function scan(text) {
  const stack = [];
  let expectKey = false;
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '"') {
      let j = i + 1;
      while (j < text.length && text[j] !== '"') j += text[j] === "\\" ? 2 : 1;
      if (expectKey && stack.length > 0) {
        let key;
        try {
          key = JSON.parse(text.slice(i, j + 1));
        } catch {
          throw new CanonicalError("the document is not valid JSON");
        }
        const top = stack[stack.length - 1];
        if (top.has(key)) throw new CanonicalError("a JSON object repeats a key");
        top.add(key);
        expectKey = false;
      }
      i = j + 1;
      continue;
    }
    if (ch === "-" || (ch >= "0" && ch <= "9")) {
      let j = i;
      while (j < text.length && "+-0123456789.eE".includes(text[j])) j += 1;
      if (/[.eE]/.test(text.slice(i, j))) throw new CanonicalError("a JSON number with a fraction or an exponent is not allowed (integers only)");
      i = j;
      continue;
    }
    if (ch === "{") {
      stack.push(new Set());
      expectKey = true;
    } else if (ch === "[") {
      stack.push(null);
      expectKey = false;
    } else if (ch === "}" || ch === "]") {
      stack.pop();
      expectKey = false;
    } else if (ch === ",") {
      expectKey = stack.length > 0 && stack[stack.length - 1] !== null;
    } else if (ch === ":") {
      expectKey = false;
    }
    i += 1;
  }
}
