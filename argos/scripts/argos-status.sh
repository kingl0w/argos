#!/usr/bin/env bash
set -euo pipefail

# argos-status.sh — at-a-glance view of an Argos project.
# Prints STATE.md, then a ticket status table, then pending (Proposed) ADRs.

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

hr() { printf '%s\n' "------------------------------------------------------------"; }

echo "=== STATE.md ==="
if [ -f argos/specs/STATE.md ]; then
  cat argos/specs/STATE.md
else
  echo "(no argos/specs/STATE.md — run argos/scripts/argos-init.sh)"
fi

echo
hr
echo "=== Tickets ==="
if [ -d argos/specs/tickets ]; then
  printf '%-20s  %-12s  %s\n' "ID" "STATUS" "TITLE"
  printf '%-20s  %-12s  %s\n' "--" "------" "-----"
  for f in argos/specs/tickets/*.md; do
    [ -f "$f" ] || continue
    case "$f" in *.template) continue ;; esac
    id=$(basename "$f" .md | grep -oE '^[A-Z]+-[0-9]+' || echo "?")
    status=$(grep -m1 -E '^\*\*Status:\*\*' "$f" 2>/dev/null \
             | sed -E 's/^\*\*Status:\*\*[[:space:]]*//' | tr -d '\r' )
    [ -z "$status" ] && status="?"
    title=$(grep -m1 '^# ' "$f" | sed 's/^# //')
    printf '%-20s  %-12s  %s\n' "$id" "$status" "$title"
  done
else
  echo "(no argos/specs/tickets/ directory)"
fi

echo
hr
echo "=== Proposed ADRs ==="
found=0
if [ -d argos/specs/decisions ]; then
  for f in argos/specs/decisions/ADR-*.md; do
    [ -f "$f" ] || continue
    case "$f" in *.template) continue ;; esac
    status=$(grep -m1 -E '^\*\*Status:\*\*' "$f" 2>/dev/null \
             | sed -E 's/^\*\*Status:\*\*[[:space:]]*//' | tr -d '\r')
    if [ "$status" = "Proposed" ]; then
      title=$(grep -m1 '^# ' "$f" | sed 's/^# //')
      echo "  $f  —  $title"
      found=1
    fi
  done
fi
[ "$found" -eq 0 ] && echo "(none)"
