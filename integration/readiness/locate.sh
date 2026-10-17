#!/bin/sh
# Playbook step 1: locate the checkouts by marker files (read-only; prints a table, changes nothing).
# Usage: sh integration/readiness/locate.sh [search root, default /]
# A directory counts only when it is a TOP checkout: .git is a directory and it is its own top level (a linked
# worktree, an export or a copy prints SKIP).
ROOT="${1:-/}"
is_top() { d=$(cd "$1" 2>/dev/null && pwd -P) && [ -d "$d/.git" ] && [ "$(git -C "$d" rev-parse --show-toplevel 2>/dev/null)" = "$d" ]; }
find "$ROOT" -xdev -maxdepth 6 \( -name pyproject.toml -o -name package.json -o -name EPINOIC_MIRROR_NOTE.md \) \
     -not -path '*/node_modules/*' 2>/dev/null | while read -r marker; do
  dir=$(dirname "$marker")
  kind=""
  case "$(basename "$marker")" in
    pyproject.toml) grep -q 'name = "epinoic-logic"' "$marker" 2>/dev/null && kind="translator-candidate" ;;
    EPINOIC_MIRROR_NOTE.md) kind="z3-mirror" ;;
    package.json)
      if grep -q '"name": "epinoic-ai-website"' "$marker" 2>/dev/null; then kind="website"
      elif grep -q '"name": "@epinoic/specialist-runtime"' "$marker" 2>/dev/null; then kind="agents"; dir=$(dirname "$dir")
      fi ;;
  esac
  [ -n "$kind" ] || continue
  if is_top "$dir"; then top=TOP; else top=SKIP; fi
  if [ "$kind" = "z3-mirror" ]; then top=REFERENCE; fi
  remote=$(git -C "$dir" remote get-url origin 2>/dev/null || echo "-")
  head=$(git -C "$dir" rev-parse --short HEAD 2>/dev/null || echo "-")
  printf '%-22s %-9s %-10s %s %s\n' "$kind" "$top" "$head" "$dir" "$remote"
done | sort -u
