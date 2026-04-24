#!/usr/bin/env bash
set -euo pipefail

# argos-sync.sh — bidirectional sync between argos/specs/tickets/ and GitHub Issues.
#
# Usage:
#   argos-sync.sh push     # tickets/*.md -> issues (create if missing, update existing)
#   argos-sync.sh pull     # issues labeled "argos-ticket" -> tickets/*.md (skip existing)
#   argos-sync.sh status   # count local tickets vs remote issues

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

MODE="${1:-status}"
LABEL="argos-ticket"
TICKETS_DIR="argos/specs/tickets"

need_gh() {
  if ! command -v gh >/dev/null 2>&1; then
    echo "error: gh CLI not found."
    echo "  install:  https://cli.github.com/"
    echo "  then run: gh auth login"
    exit 1
  fi
  if ! gh auth status >/dev/null 2>&1; then
    echo "error: gh is installed but not authenticated."
    echo "  run: gh auth login"
    exit 1
  fi
}

# Extract ticket ID (e.g. ACME-001) from filename.
ticket_id_from_file() {
  basename "$1" .md | grep -oE '^[A-Z]+-[0-9]+' || true
}

# Extract ticket title (first H1) from ticket file.
ticket_title_from_file() {
  local f="$1" id title
  id=$(ticket_id_from_file "$f")
  title=$(grep -m1 '^# ' "$f" | sed 's/^# //')
  [ -z "$title" ] && title="$id"
  echo "$title"
}

# Find an issue whose title contains the ticket ID. Echoes issue number or empty.
find_issue_for_ticket() {
  local id="$1"
  gh issue list --label "$LABEL" --state all --limit 500 \
    --json number,title \
    --jq ".[] | select(.title | test(\"\\\\b${id}\\\\b\")) | .number" \
    2>/dev/null | head -n1
}

cmd_push() {
  [ -d "$TICKETS_DIR" ] || { echo "no $TICKETS_DIR directory"; exit 1; }
  local created=0 updated=0 skipped=0
  for f in "$TICKETS_DIR"/*.md; do
    [ -f "$f" ] || continue
    local id title num
    id=$(ticket_id_from_file "$f")
    if [ -z "$id" ]; then
      echo "  skip (no ticket ID): $f"
      skipped=$((skipped+1))
      continue
    fi
    title=$(ticket_title_from_file "$f")
    num=$(find_issue_for_ticket "$id" || true)
    if [ -n "$num" ]; then
      gh issue edit "$num" --body-file "$f" --title "$title" >/dev/null
      echo "  updated #$num  $id"
      updated=$((updated+1))
    else
      gh issue create --title "$title" --body-file "$f" --label "$LABEL" >/dev/null
      echo "  created        $id"
      created=$((created+1))
    fi
  done
  echo
  echo "push: $created created, $updated updated, $skipped skipped"
}

cmd_pull() {
  mkdir -p "$TICKETS_DIR"
  local written=0 skipped=0
  # shellcheck disable=SC2016
  mapfile -t rows < <(gh issue list --label "$LABEL" --state all --limit 500 \
    --json number,title,body \
    --jq '.[] | [.number, .title] | @tsv')
  for row in "${rows[@]}"; do
    local num title id
    num=$(echo "$row" | cut -f1)
    title=$(echo "$row" | cut -f2-)
    id=$(echo "$title" | grep -oE '[A-Z]+-[0-9]+' | head -n1)
    if [ -z "$id" ]; then
      echo "  skip #$num (no ticket ID in title): $title"
      skipped=$((skipped+1))
      continue
    fi
    # preserve existing
    existing=$(find "$TICKETS_DIR" -maxdepth 1 -type f -name "${id}*.md" | head -n1)
    if [ -n "$existing" ]; then
      echo "  skip #$num $id (local exists: $existing)"
      skipped=$((skipped+1))
      continue
    fi
    slug=$(echo "$title" | sed "s/${id}//" | tr '[:upper:]' '[:lower:]' \
           | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//' | cut -c1-40)
    [ -z "$slug" ] && slug="imported"
    out="$TICKETS_DIR/${id}-${slug}.md"
    gh issue view "$num" --json body --jq '.body' > "$out"
    echo "  wrote $out  (from #$num)"
    written=$((written+1))
  done
  echo
  echo "pull: $written written, $skipped skipped"
}

cmd_status() {
  local local_count=0 remote_count=0
  if [ -d "$TICKETS_DIR" ]; then
    local_count=$(find "$TICKETS_DIR" -maxdepth 1 -type f -name '*.md' ! -name '*.template' | wc -l | tr -d ' ')
  fi
  remote_count=$(gh issue list --label "$LABEL" --state all --limit 500 \
    --json number --jq 'length' 2>/dev/null || echo 0)
  echo "local tickets:  $local_count"
  echo "remote issues:  $remote_count  (label: $LABEL)"
}

case "$MODE" in
  push)   need_gh; cmd_push ;;
  pull)   need_gh; cmd_pull ;;
  status) need_gh; cmd_status ;;
  *)      echo "Usage: $0 {push|pull|status}"; exit 2 ;;
esac
