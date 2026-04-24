#!/usr/bin/env bash
set -euo pipefail

# argos-init.sh — one-shot template initializer for Argos.
# Replaces {{PROJECT}}, {{PREFIX}}, {{DESC}}, {{DATE}} placeholders in every
# argos/specs/**/*.template file, writes the result to the same path without the
# .template suffix, renames EXAMPLE-001.md → <PREFIX>-001.md, drops a
# .initialized sentinel so it won't re-run.

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

SENTINEL="argos/.initialized"

if [ -f "$SENTINEL" ]; then
  echo "argos: already initialized ($(cat "$SENTINEL" 2>/dev/null | head -n1))"
  echo "       delete $SENTINEL to re-run, or edit argos/specs/ files directly."
  exit 0
fi

templates=$(find argos/specs -type f -name '*.template' 2>/dev/null)
if [ -z "$templates" ]; then
  echo "argos: no .template files found under argos/specs/ — nothing to do."
  exit 1
fi

echo "=== Argos init ==="
read -rp "Project name (e.g. \"Acme API\"): " PROJECT
[ -n "$PROJECT" ] || { echo "project name required"; exit 1; }

while :; do
  read -rp "Ticket prefix (2-4 uppercase letters, e.g. ACME): " PREFIX
  if [[ "$PREFIX" =~ ^[A-Z]{2,4}$ ]]; then
    break
  fi
  echo "  must be 2-4 uppercase letters, got: '$PREFIX'"
done

read -rp "One-line description: " DESC
[ -n "$DESC" ] || DESC="(no description provided)"

DATE="$(date +%Y-%m-%d)"

echo
echo "  Project: $PROJECT"
echo "  Prefix:  $PREFIX"
echo "  Desc:    $DESC"
echo "  Date:    $DATE"
echo
read -rp "Proceed? [y/N] " confirm
case "$confirm" in
  y|Y|yes|YES) ;;
  *) echo "aborted."; exit 1 ;;
esac

# Escape replacement strings for sed (handle &, /, \)
esc() { printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'; }
P_ESC=$(esc "$PROJECT")
X_ESC=$(esc "$PREFIX")
D_ESC=$(esc "$DESC")
T_ESC=$(esc "$DATE")

echo
echo "Rendering templates..."
while IFS= read -r tpl; do
  out="${tpl%.template}"
  sed \
    -e "s/{{PROJECT}}/$P_ESC/g" \
    -e "s/{{PREFIX}}/$X_ESC/g" \
    -e "s/{{DESC}}/$D_ESC/g" \
    -e "s/{{DATE}}/$T_ESC/g" \
    "$tpl" > "$out"
  rm "$tpl"
  echo "  rendered: $out"
done <<< "$templates"

# Rename the example ticket
example_src="argos/specs/tickets/EXAMPLE-001.md"
example_dst="argos/specs/tickets/${PREFIX}-001.md"
if [ -f "$example_src" ]; then
  mv "$example_src" "$example_dst"
  echo "  renamed:  $example_src -> $example_dst"
fi

# Sentinel
{
  echo "project: $PROJECT"
  echo "prefix:  $PREFIX"
  echo "date:    $DATE"
} > "$SENTINEL"

cat <<EOF

Argos initialized.

Next steps:
  1. Edit argos/specs/PRD.md — fill in problem, goals, non-goals.
  2. Edit argos/specs/ARCHITECTURE.md — describe system shape and invariants.
  3. Review (or delete) the example ticket at $example_dst.
  4. In Claude Code: /new-ticket to draft your first real ticket, then /next to run the loop.

See ARGOS.md for methodology and CLAUDE.md for operating rules.
EOF
