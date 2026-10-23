#!/bin/sh
# Playbook step 1: locate the checkouts by marker files (read-only; prints a table, changes nothing).
# Usage: sh integration/readiness/locate.sh [search root, default /]
# A directory counts only when it is a TOP checkout: .git is a directory and it is its own top level (a linked
# worktree, an export or a copy prints SKIP). Agents checkouts are found by either marker: the specialist runtime's
# package.json (its parent directory) or the knowledge bases' knowledge-bases/_build/check_kb_set.py (the directory
# three levels up), which the retrained repository holds on every branch. A runtime vendored into another repository
# (a specialist-runtime/ under a directory named vendor) is kind agents-vendored, REFERENCE only: never an agents
# checkout (step 9a compares it with the pins).
ROOT="${1:-/}"
is_top() { d=$(cd "$1" 2>/dev/null && pwd -P) && [ -d "$d/.git" ] && [ "$(git -C "$d" rev-parse --show-toplevel 2>/dev/null)" = "$d" ]; }
find "$ROOT" -xdev -maxdepth 7 \( -name pyproject.toml -o -name package.json -o -name EPINOIC_MIRROR_NOTE.md -o -name check_kb_set.py \) \
     -not -path '*/node_modules/*' 2>/dev/null | while read -r marker; do
  dir=$(dirname "$marker")
  kind=""
  case "$(basename "$marker")" in
    pyproject.toml) grep -q 'name = "epinoic-logic"' "$marker" 2>/dev/null && kind="translator-candidate" ;;
    EPINOIC_MIRROR_NOTE.md) kind="z3-mirror" ;;
    check_kb_set.py)
      if [ "$(basename "$dir")" = "_build" ] && [ "$(basename "$(dirname "$dir")")" = "knowledge-bases" ]; then
        kind="agents"; dir=$(dirname "$(dirname "$dir")")
      fi ;;
    package.json)
      if grep -q '"name": "epinoic-ai-website"' "$marker" 2>/dev/null; then kind="website"
      elif grep -q '"name": "@epinoic/specialist-runtime"' "$marker" 2>/dev/null; then
        dir=$(dirname "$dir")
        if [ "$(basename "$dir")" = "vendor" ]; then kind="agents-vendored"; else kind="agents"; fi
      fi ;;
  esac
  [ -n "$kind" ] || continue
  if is_top "$dir"; then top=TOP; else top=SKIP; fi
  if [ "$kind" = "z3-mirror" ] || [ "$kind" = "agents-vendored" ]; then top=REFERENCE; fi
  remote=$(git -C "$dir" remote get-url origin 2>/dev/null || echo "-")
  head=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "-")
  printf '%-22s %-9s %-10s %s %s\n' "$kind" "$top" "$head" "$dir" "$remote"
done | sort -u
