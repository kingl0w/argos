#!/bin/sh
# install-hooks.sh — register the argos pre-commit hooks into the local clone.
#
# Currently registers:
#   - argos/scripts/hooks/pre-commit-state-write.sh  (ARG1-032)
#
# Idempotent. Run by `argos init` (ARG1-002) and re-runnable manually after a
# fresh clone. The hook block in `.git/hooks/pre-commit` is delimited by
# sentinel comments so re-running this script replaces it in place rather than
# appending duplicates, and so users can safely add their own pre-commit logic
# alongside it.

set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

HOOK_REL="argos/scripts/hooks/pre-commit-state-write.sh"
HOOK_ABS="$ROOT/$HOOK_REL"

if [ ! -f "$HOOK_ABS" ]; then
    echo "install-hooks: $HOOK_REL missing" >&2
    exit 1
fi
if [ ! -x "$HOOK_ABS" ]; then
    chmod +x "$HOOK_ABS"
fi

# Resolve the hooks directory. Honor core.hooksPath (e.g. used by Husky); fall
# back to the default `.git/hooks`.
GIT_DIR="$(git rev-parse --git-dir 2>/dev/null || true)"
if [ -z "$GIT_DIR" ]; then
    echo "install-hooks: not in a git repository (run from a clone)" >&2
    exit 1
fi
HOOKS_DIR="$(git config --get core.hooksPath 2>/dev/null || true)"
if [ -z "$HOOKS_DIR" ]; then
    HOOKS_DIR="$GIT_DIR/hooks"
fi
mkdir -p "$HOOKS_DIR"

PRECOMMIT="$HOOKS_DIR/pre-commit"

SENTINEL_OPEN="# >>> argos pre-commit-state-write (ARG1-032) >>>"
SENTINEL_CLOSE="# <<< argos pre-commit-state-write (ARG1-032) <<<"

# The block re-invokes the hook with the original args ("$@") so chained
# pre-commit logic (added by the user above or below this block) keeps working.
BLOCK="$SENTINEL_OPEN
# Managed by argos/scripts/install-hooks.sh — edits inside this block will be
# overwritten on the next run. Add custom pre-commit logic outside the
# sentinel pair.
\"$HOOK_REL\" \"\$@\" || exit \$?
$SENTINEL_CLOSE"

if [ ! -f "$PRECOMMIT" ]; then
    # Fresh hook file — write a minimal shebang + the sentinel block.
    {
        printf '#!/bin/sh\n'
        printf 'set -e\n'
        printf '\n'
        printf '%s\n' "$BLOCK"
    } > "$PRECOMMIT"
    chmod +x "$PRECOMMIT"
    echo "install-hooks: wrote $PRECOMMIT"
    exit 0
fi

# Existing pre-commit. Replace any prior argos block in place; otherwise
# append.
if grep -F -q -- "$SENTINEL_OPEN" "$PRECOMMIT" \
   && grep -F -q -- "$SENTINEL_CLOSE" "$PRECOMMIT"; then
    # Use awk to strip the existing block, then append the fresh one.
    TMP="$(mktemp "${TMPDIR:-/tmp}/argos-hooks.XXXXXX")"
    awk -v opentag="$SENTINEL_OPEN" -v closetag="$SENTINEL_CLOSE" '
        BEGIN { skip = 0 }
        $0 == opentag  { skip = 1; next }
        $0 == closetag { skip = 0; next }
        skip == 0      { print }
    ' "$PRECOMMIT" > "$TMP"
    # Strip trailing blank lines from $TMP so the re-appended block is flush.
    awk 'NR==FNR { if ($0 != "") last = NR; next } FNR <= last' "$TMP" "$TMP" \
        > "$TMP.trimmed"
    mv "$TMP.trimmed" "$TMP"
    {
        cat "$TMP"
        printf '\n'
        printf '%s\n' "$BLOCK"
    } > "$PRECOMMIT.new"
    mv "$PRECOMMIT.new" "$PRECOMMIT"
    rm -f "$TMP"
    chmod +x "$PRECOMMIT"
    echo "install-hooks: refreshed argos block in $PRECOMMIT"
else
    # Append a new block; preserve existing contents verbatim.
    # Ensure file ends with newline before appending.
    if [ -s "$PRECOMMIT" ]; then
        last_byte="$(tail -c1 "$PRECOMMIT" | od -An -c | tr -d ' ')"
        if [ "$last_byte" != "\n" ]; then
            printf '\n' >> "$PRECOMMIT"
        fi
    fi
    printf '\n%s\n' "$BLOCK" >> "$PRECOMMIT"
    chmod +x "$PRECOMMIT"
    echo "install-hooks: appended argos block to $PRECOMMIT"
fi
