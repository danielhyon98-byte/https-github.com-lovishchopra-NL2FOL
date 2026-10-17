# Rollback

This file prints commands for owners to run on their own go-ahead; the kit runs nothing. A rollback never releases an
unchecked answer: every path below fails closed.

## Website (Bruno)

1. Set staging `CHAT_BACKEND` back to its previous value through a reviewed pull request. Merging deploys staging
   (Cloudflare's connected build), so this is Bruno's action.
2. Revert the writer (W3) if needed. **Keep the reader (W1) for good once any row with `checks` exists**: removing it
   would make those replays fail with 500.
3. The usage migration (W5) stays: migrations are forward-only and additive; its columns or reservation kind become
   unused.
4. Bruno removes `TRANSLATOR_SERVICE_TOKEN` with `wrangler secret delete`, on his own go-ahead. Removing it deploys.
5. The kit never applied W0, so there is nothing of it to roll back. If Bruno merged W0 and later restores the
   deferral, that is his own docs change.

## Service (Daniel)

Redeploy the previous image tag. If its versions fall outside the Worker's compatibility set, the Worker fails closed:
`service_unavailable` after admission (the handshake, `kit_hs_mismatch`) or `chat_unavailable` before admission (the
configuration), never an unchecked answer.

## Agents (Daniel)

Nothing to roll back in the runtime or the router. Revert the docs, port and test changes (A1 to A5) if needed.

## Flash router (its sub-project's owner)

Detach it: set `EPINOIC_FLASH_ROUTER=none`, or remove the variable (the service attaches the router only when the
variable names it; the default is `none`, decision D28), and restart the service. The floor plan then runs for every
review; no decision changes, because a plan never changes a clearance, a delivery or a verdict's decision. To roll back
a release of the router itself, reinstall the previous version of `flash-router/` (its identity in the handshake and in
every verdict's review names the version that planned it); the translator and the kit need no change.

## The kit itself (Daniel)

A published tag is never moved or deleted. A bad kit is withdrawn by updating `INTEGRATION_KIT.md` to name the
previous or the next tag, and by listing the bad tag in `DECISIONS.md`. Scratch exports and worktrees disappear with
`<scratch>`; afterwards run `git worktree prune` in the translator checkout. The engine and its existing routes never
changed, because the default profile is `engine`.

## Rollback rehearsal (PROTOCOL.md section 14.7)

Playbook step 11a runs it on three disposable exports of the website's `origin/main` (the whole patch set, W1 alone,
and the unpatched base): `node integration/rollback/rehearse.mjs --full <export> --reader <W1-only export> --base
<unpatched export> --work <dir>`. `website/patches/M/TESTED.json` records the last run. It shows:

1. with W1 alone (the reader) applied to a database that holds rows written by W3, replay and history still work;
2. removing W3 (the writer) leaves every stored row valid;
3. a service rolled back to an incompatible version gives `service_unavailable` after admission, or
   `chat_unavailable` before admission, and never an unchecked answer;
4. on base P, removing patch set P leaves the pilot's own behaviour unchanged.

What the kit rehearses without a website export: `tests/integration/test_rollback.py` shows on the service side that
a service whose versions fall outside the compatibility set is refused by the Worker's handshake rules
(`kit_hs_mismatch` for every refusing code), that the floor runs when the router is detached, and that the `engine`
profile serves exactly the routes it served before; `tests/integration/test_flash_router_subproject.py` shows that
removing `EPINOIC_FLASH_ROUTER` detaches the router even when its sub-project is installed.
