// SHA-256 digests of protocol epinoic.integration.v1 with crypto.subtle (integration/PROTOCOL.md section 1).
//
// Invariants:
// - lowercase hex; a text digest is over the exact UTF-8 bytes of the text, an object digest over its canonical JSON;
// - a text with a lone surrogate has no UTF-8 form and is refused (CanonicalError), never replaced with U+FFFD;
// - only globalThis.crypto.subtle and TextEncoder are used (no new dependency).

import { CanonicalError, canonicalJson, hasLoneSurrogate } from "./canonical-json.js";

const ENCODER = new TextEncoder();

function hex(buffer) {
  return Array.from(new Uint8Array(buffer), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** SHA-256 of the UTF-8 bytes of `text`. */
export async function sha256Text(text) {
  if (typeof text !== "string") throw new CanonicalError("a text digest needs a string");
  if (hasLoneSurrogate(text)) throw new CanonicalError("a text with a lone surrogate has no UTF-8 form");
  return hex(await globalThis.crypto.subtle.digest("SHA-256", ENCODER.encode(text)));
}

/** SHA-256 of the canonical JSON of `value`. */
export async function sha256Json(value) {
  return sha256Text(canonicalJson(value));
}

/** The UTF-8 byte length of `text` (the protocol's size limits count bytes, not code units). */
export function utf8Bytes(text) {
  return ENCODER.encode(text).byteLength;
}
