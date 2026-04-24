#!/usr/bin/env bash
# argos-migrate-v0.5.sh — one-shot v0.4 -> v0.5 layout migration.
# Moves .specs/ -> argos/specs/, ARGOS-RULES.md -> argos/RULES.md,
# scripts/argos-*.sh -> argos/scripts/, and regenerates harness outputs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# Idempotency: if argos/specs/ already exists, we've already migrated.
if [ -d argos/specs ]; then
  echo "argos: already on v0.5 layout (argos/specs/ exists). Nothing to do."
  exit 0
fi

# Refuse if there's no v0.4 layout to migrate from.
if [ ! -d .specs ]; then
  echo "argos: no .specs/ directory found — nothing to migrate."
  echo "       are you sure this is a v0.4 Argos project?"
  exit 1
fi

echo "=== Argos v0.4 -> v0.5 migration ==="
echo "root: $ROOT"
echo

mkdir -p argos

# .specs/ -> argos/specs/
if [ -d .specs ]; then
  echo "  moving .specs/            -> argos/specs/"
  if command -v git >/dev/null 2>&1 && [ -d .git ]; then
    git mv .specs argos/specs 2>/dev/null || mv .specs argos/specs
  else
    mv .specs argos/specs
  fi
fi

# ARGOS-RULES.md -> argos/RULES.md
if [ -f ARGOS-RULES.md ]; then
  echo "  moving ARGOS-RULES.md     -> argos/RULES.md"
  if command -v git >/dev/null 2>&1 && [ -d .git ]; then
    git mv ARGOS-RULES.md argos/RULES.md 2>/dev/null || mv ARGOS-RULES.md argos/RULES.md
  else
    mv ARGOS-RULES.md argos/RULES.md
  fi
fi

# scripts/argos-*.sh -> argos/scripts/
mkdir -p argos/scripts
for s in argos-init.sh argos-status.sh argos-sync.sh argos-chaos-probe.sh; do
  if [ -f "scripts/$s" ]; then
    echo "  moving scripts/$s -> argos/scripts/$s"
    if command -v git >/dev/null 2>&1 && [ -d .git ]; then
      git mv "scripts/$s" "argos/scripts/$s" 2>/dev/null || mv "scripts/$s" "argos/scripts/$s"
    else
      mv "scripts/$s" "argos/scripts/$s"
    fi
  fi
done

# Sentinel: .specs/.argos-initialized -> argos/.initialized
# (If the specs move landed the old sentinel at argos/specs/.argos-initialized,
# lift it up a directory and rename.)
if [ -f argos/specs/.argos-initialized ]; then
  echo "  moving .argos-initialized -> argos/.initialized"
  mv argos/specs/.argos-initialized argos/.initialized
fi

# Regenerate harness outputs (CLAUDE.md, AGENTS.md, .claude/, .cursor/, .codex/, .gemini/)
# from the updated source/ so everything points at the new paths.
if [ -f scripts/build.sh ]; then
  echo
  echo "  rebuilding harness outputs (scripts/build.sh)"
  bash scripts/build.sh
fi

cat <<EOF

Migration complete. Changes:
  .specs/            -> argos/specs/
  ARGOS-RULES.md     -> argos/RULES.md
  scripts/argos-*.sh -> argos/scripts/
  .argos-initialized -> argos/.initialized

Harness outputs (CLAUDE.md, AGENTS.md, .claude/, .cursor/, .codex/, .gemini/)
were regenerated from source/.

Next:
  1. git status      — review the changes
  2. git add -A
  3. git commit -m "Migrate to Argos v0.5 layout"
EOF
