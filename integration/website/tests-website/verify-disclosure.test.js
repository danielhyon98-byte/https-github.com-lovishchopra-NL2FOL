// Kit W4, the disclosure (copied into the website's tests/ by integration/website/apply.mjs): under the verified
// backend the chat page says that answers pass automatic checks before they are shown, each anchor rewritten exactly
// once, failing closed (503) when an anchor is missing or "no live AI" would survive.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { chatPageResponse } from "../src/disclosure.js";

const PAGE = readFileSync(new URL("../public/dev/chat/index.html", import.meta.url), "utf8");
const assets = (html) => ({ fetch: async () => new Response(html, { status: 200, headers: { "Content-Type": "text/html" } }) });
const get = (env, html = PAGE) => chatPageResponse(new Request("http://127.0.0.1:8787/dev/chat/"), { ...env, ASSETS: assets(html) });

test("the verified backend's page says that answers pass automatic checks, and no longer says no live AI", async () => {
  const r = await get({ CHAT_BACKEND: "verified", ROUTER_MODE: "mock" });
  assert.equal(r.status, 200);
  const html = await r.text();
  assert.match(html, /answers pass automatic checks, including formal checks of their logic encoding, before they are shown/);
  assert.doesNotMatch(html, /no live AI/i);
  assert.doesNotMatch(html, /\bverified\b|\bproven\b|Reviewed/);
});

test("with live routing too, both disclosures are rewritten", async () => {
  const html = await (await get({ CHAT_BACKEND: "verified", ROUTER_MODE: "live" })).text();
  assert.match(html, /Live routing; simulated specialist; answers pass automatic checks/);
  assert.match(html, /data-routing="live"/);
});

test("a missing anchor fails closed", async () => {
  const r = await get({ CHAT_BACKEND: "verified", ROUTER_MODE: "mock" }, PAGE.replace("Replies come from a mock backend", "Replies come from somewhere"));
  assert.equal(r.status, 503);
});

test("the mock backend's page is unchanged", async () => {
  const r = await get({ CHAT_BACKEND: "mock", ROUTER_MODE: "mock" });
  assert.equal(await r.text(), PAGE);
});
