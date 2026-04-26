#!/bin/sh
# install-merge-driver.sh — register the argos-state custom merge driver.
# Idempotent. Run by `argos init`; also re-runnable manually after `git clone`.
set -eu

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

DRIVER_REL="argos/scripts/state-merge-driver.sh"
DRIVER_ABS="$ROOT/$DRIVER_REL"

if [ ! -f "$DRIVER_ABS" ]; then
    echo "install-merge-driver: $DRIVER_REL missing" >&2
    exit 1
fi

if [ ! -x "$DRIVER_ABS" ]; then
    chmod +x "$DRIVER_ABS"
fi

git config merge.argos-state.name "Argos STATE.md append-mostly merge"
git config merge.argos-state.driver "$DRIVER_REL %O %A %B %P %L"
git config merge.argos-state.recursive "binary"

ATTR_FILE="$ROOT/.gitattributes"
touch "$ATTR_FILE"

# Ensure file ends with newline before appending.
if [ -s "$ATTR_FILE" ]; then
    last_byte=$(tail -c1 "$ATTR_FILE" | od -An -c | tr -d ' ')
    if [ "$last_byte" != "\n" ]; then
        printf '\n' >> "$ATTR_FILE"
    fi
fi

for line in \
    "argos/specs/v1.0/STATE.md merge=argos-state" \
    "argos/specs/STATE.md merge=argos-state"
do
    if ! grep -F -x -q -- "$line" "$ATTR_FILE"; then
        printf '%s\n' "$line" >> "$ATTR_FILE"
    fi
done

echo "argos: registered merge.argos-state driver and updated .gitattributes."
