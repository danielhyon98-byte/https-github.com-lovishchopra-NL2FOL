#!/bin/sh
# PROPOSED ONLY. The bootstrap, the preflight and the self-test run before the socket is bound; any missing required
# part prints one KIT-HS line and exits 2. Keys and tokens come from the environment (names only), never from a file.
set -eu
exec python -m epinoic_logic.integration serve --host 0.0.0.0 --port "${PORT:-8080}"
