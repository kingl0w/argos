#!/usr/bin/env bash
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-all}"
TICKET_ID="${2:-}"

fail() { echo "CHAOS: $1"; exit 1; }

probe_scope() {
  [ -n "$TICKET_ID" ] || { echo "scope probe requires ticket ID"; exit 2; }
  ticket_file=$(find argos/specs/tickets -name "${TICKET_ID}*.md" -type f | head -n1)
  [ -n "$ticket_file" ] || fail "ticket $TICKET_ID not found"

  planned=$(awk '/^### Files touched/{flag=1; next} /^### /{flag=0} flag && /^- `/ {
    gsub(/^- `/, ""); gsub(/`.*$/, ""); print
  }' "$ticket_file" | sort -u)

  [ -z "$planned" ] && { echo "scope: no Files touched section — planner may not have run"; return 0; }

  base=$(git merge-base HEAD main 2>/dev/null || git merge-base HEAD master 2>/dev/null || git rev-parse HEAD~10 2>/dev/null)
  actual=$(git diff --name-only "$base" 2>/dev/null | sort -u)

  drift=$(comm -23 <(echo "$actual") <(echo "$planned"))
  [ -n "$drift" ] && fail "scope drift — files changed outside plan: $drift"
  echo "scope: PASS"
}

probe_state() {
  [ -f argos/specs/STATE.md ] || fail "no argos/specs/STATE.md"
  state_ids=$(grep -oE '[A-Z]+-[0-9]+' argos/specs/STATE.md | sort -u)
  file_ids=$(find argos/specs/tickets -name '*.md' -type f 2>/dev/null | xargs -I {} basename {} .md 2>/dev/null | grep -oE '^[A-Z]+-[0-9]+' | sort -u)
  orphans=$(comm -23 <(echo "$state_ids") <(echo "$file_ids"))
  [ -n "$orphans" ] && fail "STATE.md references tickets that don't exist as files: $orphans"
  echo "state: PASS"
}

probe_stubs() {
  [ -n "$TICKET_ID" ] || { echo "stubs probe requires ticket ID"; exit 2; }
  base=$(git merge-base HEAD main 2>/dev/null || git rev-parse HEAD~10 2>/dev/null)
  changed=$(git diff --name-only "$base" 2>/dev/null)
  stubs_found=""
  for f in $changed; do
    [ -f "$f" ] || continue
    hits=$(grep -nE 'throw new Error\("not implemented"\)|raise NotImplementedError|todo!\(\)|panic!\("unimplemented"\)|// TODO: implement|# TODO: implement' "$f" 2>/dev/null || true)
    [ -n "$hits" ] && stubs_found="${stubs_found}${f}: ${hits}\n"
  done
  [ -n "$stubs_found" ] && fail "stubs remain: $stubs_found"
  echo "stubs: PASS"
}

probe_deps() {
  base=$(git merge-base HEAD main 2>/dev/null || git rev-parse HEAD~10 2>/dev/null)
  dep_files="package.json Cargo.toml requirements.txt pyproject.toml go.mod"
  changed_deps=""
  for df in $dep_files; do
    git diff --name-only "$base" 2>/dev/null | grep -qx "$df" && changed_deps="$changed_deps $df"
  done
  if [ -n "$changed_deps" ]; then
    recent_adrs=$(git diff --name-only "$base" 2>/dev/null | grep -c '^argos/specs/decisions/ADR-.*\.md$' || echo 0)
    [ "$recent_adrs" -eq 0 ] && fail "deps changed ($changed_deps) but no ADR — file one with /ask first"
  fi
  echo "deps: PASS"
}

case "$MODE" in
  scope)  probe_scope ;;
  state)  probe_state ;;
  stubs)  probe_stubs ;;
  deps)   probe_deps ;;
  all)    [ -n "$TICKET_ID" ] || { echo "usage: $0 all <ticket-id>"; exit 2; }
          probe_scope && probe_state && probe_stubs && probe_deps
          echo "all probes PASS" ;;
  *)      echo "Usage: $0 {scope|state|stubs|deps|all} [ticket-id]"; exit 2 ;;
esac
