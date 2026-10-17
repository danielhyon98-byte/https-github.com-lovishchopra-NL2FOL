# PROPOSED: a container for the checks service

**PROPOSED ONLY. Not built, not pushed, not deployed.** Building, pushing or deploying an image needs the owners'
go-ahead (decision D7: hosting, the operator, per-environment deployments and tokens, capacity). No secret is in any
file here: keys and tokens come from the host's secret store as environment variables at run time (names only:
`EPINOIC_SERVICE_TOKEN`, `EPINOIC_SIGNING_KEY`, `EPINOIC_VERDICT_KEY`, `EPINOIC_OVERSEER_SECRET`, and the provider's
own key variable).

- `Dockerfile`: a slim Python image, the translator package with its `service` and `providers` extras, a non-root
  user, the `integration` profile.
- `entrypoint.sh`: `python -m epinoic_logic.integration serve`, which runs the standard-library bootstrap first (Z3
  missing prints `KIT-HS-003 z3_unavailable` and exits 2), then the preflight and the self-test before binding.

The image fails closed: any missing required part stops it with its `KIT-HS` line before a socket is bound.

The flash router (`flash-router/`, a sub-project of its own) is not in the image and is never required: decision D28
says whether hosted environments attach it. If they do, the image also installs it (`pip install ./flash-router`, standard
library only) and the environment sets `EPINOIC_FLASH_ROUTER=epinoic_flash_router.port`; the service then runs it in a
process of its own, with no `EPINOIC_` variable in its environment. That process runs as the service's user: the image's
non-root user, the `exec` entrypoint (no other process holds the secrets) and keys only in the environment are what let
the service's non-dumpable mark keep its keys out of the router's reach; the hosted profile refuses to attach a router
when the service runs as root or holds `CAP_SYS_PTRACE` (`KIT-RT-016`, PROTOCOL.md section 7a).
