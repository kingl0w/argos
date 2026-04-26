#!/bin/sh
# state-merge-driver.sh — git custom merge driver for argos STATE.md.
#
# Invocation (from git): state-merge-driver.sh %O %A %B %P %L
#   %O = base/ancestor file (read-only)
#   %A = ours file (writable; merged content goes here)
#   %B = theirs file (read-only)
#   %P = pathname of the file being merged (informational)
#   %L = conflict-marker size (unused)
#
# Algorithm: append-only block merge per argos/specs/v1.0/schemas/state-block.md.
# Both sides may only ADD argos:entry blocks (never remove or modify pre-existing
# ones). The merged file = base prose + base blocks (verbatim) + blocks added in
# A (source order) + blocks added in B not already in A (source order).
#
# Exit codes:
#   0  — merge succeeded; %A contains merged content.
#   1  — append-only invariant violated (block removed or pre-existing body modified).
#   2  — malformed STATE.md on at least one side.
#  64  — usage error.

set -eu

if [ "$#" -lt 4 ]; then
    echo "state-merge-driver: usage: $0 %O %A %B %P [%L]" >&2
    exit 64
fi

O="$1"
A="$2"
B="$3"
P="$4"

for f in "$O" "$A" "$B"; do
    if [ ! -f "$f" ]; then
        echo "state-merge-driver: missing input file: $f" >&2
        exit 64
    fi
done

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

# -----------------------------------------------------------------------------
# AWK helpers (one program, several modes selected via -v mode=...).
# -----------------------------------------------------------------------------

# mode=ids       — print one id per line for every well-formed block in argv[1].
# mode=block     — print the full text of the block whose id matches -v want=...
# mode=validate  — exit non-zero if file is malformed; otherwise silent success.
# mode=base_emit — emit base file with each block written verbatim (used to copy
#                  base prose+blocks into the merged output).

AWK_PROG='
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }

function extract_id(line,    s, n, parts, i, kv, key, val) {
    s = line
    sub(/^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+/, "", s)
    sub(/[[:space:]]*-->[[:space:]]*$/, "", s)
    n = split(s, parts, /[[:space:]]+/)
    for (i = 1; i <= n; i++) {
        kv = parts[i]
        if (match(kv, /=/) > 0) {
            key = substr(kv, 1, RSTART - 1)
            val = substr(kv, RSTART + 1)
            if (key == "id") return val
        }
    }
    return ""
}

BEGIN {
    in_block = 0
    open_line = 0
    cur_id = ""
    cur_body = ""
}

{
    line = $0
    if (in_block == 0) {
        if (line ~ /^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+.*-->[[:space:]]*$/) {
            in_block = 1
            open_line = NR
            cur_id = extract_id(line)
            if (cur_id == "") {
                printf("%s: line %d: malformed open tag — no id attribute\n", FILENAME, NR) > "/dev/stderr"
                exit 2
            }
            cur_body = line
            next
        }
        # close tag outside a block: ignore (per schema)
        if (mode == "base_emit") print line
        next
    }

    # in_block == 1
    cur_body = cur_body "\n" line
    if (line ~ /^[[:space:]]*<!--[[:space:]]*\/argos:entry[[:space:]]*-->[[:space:]]*$/) {
        # block closed
        if (mode == "ids") {
            print cur_id
        } else if (mode == "block") {
            if (cur_id == want) print cur_body
        } else if (mode == "base_emit") {
            print cur_body
        }
        in_block = 0
        cur_id = ""
        cur_body = ""
        open_line = 0
    }
}

END {
    if (in_block == 1) {
        printf("%s: line %d: unclosed entry — open tag has no matching close before EOF\n", FILENAME, open_line) > "/dev/stderr"
        exit 2
    }
}
'

# -----------------------------------------------------------------------------
# Step 1: validate each side. awk exits 2 with a stderr line on malformation.
# -----------------------------------------------------------------------------
for side_label in O A B; do
    case "$side_label" in
        O) f="$O" ;;
        A) f="$A" ;;
        B) f="$B" ;;
    esac
    if ! awk -v mode=ids "$AWK_PROG" "$f" >/dev/null 2>"$TMPDIR/awkerr"; then
        rc=$?
        if [ -s "$TMPDIR/awkerr" ]; then
            cat "$TMPDIR/awkerr" >&2
        fi
        echo "state-merge-driver: malformed STATE.md on side $side_label ($f) for path $P" >&2
        exit $rc
    fi
done

# -----------------------------------------------------------------------------
# Step 2: extract id lists.
# -----------------------------------------------------------------------------
awk -v mode=ids "$AWK_PROG" "$O" > "$TMPDIR/ids_O" 2>/dev/null || true
awk -v mode=ids "$AWK_PROG" "$A" > "$TMPDIR/ids_A" 2>/dev/null || true
awk -v mode=ids "$AWK_PROG" "$B" > "$TMPDIR/ids_B" 2>/dev/null || true

# Stable sort copies for set-difference via comm.
sort "$TMPDIR/ids_O" > "$TMPDIR/sids_O"
sort "$TMPDIR/ids_A" > "$TMPDIR/sids_A"
sort "$TMPDIR/ids_B" > "$TMPDIR/sids_B"

# added_in_A = ids_A − ids_O
comm -23 "$TMPDIR/sids_A" "$TMPDIR/sids_O" > "$TMPDIR/added_A"
# added_in_B = ids_B − ids_O
comm -23 "$TMPDIR/sids_B" "$TMPDIR/sids_O" > "$TMPDIR/added_B"
# removed_in_A = ids_O − ids_A
comm -23 "$TMPDIR/sids_O" "$TMPDIR/sids_A" > "$TMPDIR/removed_A"
# removed_in_B = ids_O − ids_B
comm -23 "$TMPDIR/sids_O" "$TMPDIR/sids_B" > "$TMPDIR/removed_B"
# dedupe: blocks added in B that are NOT also added in A
sort "$TMPDIR/added_A" > "$TMPDIR/sa_A"
sort "$TMPDIR/added_B" > "$TMPDIR/sa_B"
comm -23 "$TMPDIR/sa_B" "$TMPDIR/sa_A" > "$TMPDIR/added_B_only"

# -----------------------------------------------------------------------------
# Step 3: append-only checks.
# -----------------------------------------------------------------------------
if [ -s "$TMPDIR/removed_A" ]; then
    bad=$(head -n1 "$TMPDIR/removed_A")
    echo "state-merge-driver: append-only violated — block $bad removed from one side ($P)" >&2
    exit 1
fi
if [ -s "$TMPDIR/removed_B" ]; then
    bad=$(head -n1 "$TMPDIR/removed_B")
    echo "state-merge-driver: append-only violated — block $bad removed from one side ($P)" >&2
    exit 1
fi

# Body-modified check: for every id in ids_O, the block text in O, A, B must match.
while IFS= read -r bid; do
    [ -n "$bid" ] || continue
    awk -v mode=block -v want="$bid" "$AWK_PROG" "$O" > "$TMPDIR/b_O" 2>/dev/null
    awk -v mode=block -v want="$bid" "$AWK_PROG" "$A" > "$TMPDIR/b_A" 2>/dev/null
    awk -v mode=block -v want="$bid" "$AWK_PROG" "$B" > "$TMPDIR/b_B" 2>/dev/null
    if ! cmp -s "$TMPDIR/b_O" "$TMPDIR/b_A" || ! cmp -s "$TMPDIR/b_O" "$TMPDIR/b_B"; then
        echo "state-merge-driver: block body modified — append-only violated (id=$bid) in $P" >&2
        exit 1
    fi
done < "$TMPDIR/sids_O"

# -----------------------------------------------------------------------------
# Step 4: emit merged file.
#   - Base file (verbatim, including base blocks) — guarantees prose preserved.
#   - Then added_in_A blocks in source order (extracted from A).
#   - Then added_in_B-only blocks in source order (extracted from B).
# -----------------------------------------------------------------------------
OUT="$TMPDIR/merged"

# Copy base verbatim. Ensure trailing newline before appending.
cat "$O" > "$OUT"
# Ensure file ends with newline.
if [ -s "$OUT" ]; then
    last_byte=$(tail -c1 "$OUT" | od -An -c | tr -d ' ')
    if [ "$last_byte" != "\n" ]; then
        printf '\n' >> "$OUT"
    fi
fi

# Helper: append blocks from a side whose ids are in <wanted_sorted>, in source
# order. Single awk pass over <side_file>; reads <wanted_sorted> first to build
# an in-memory set, then streams blocks and emits matches.
APPEND_PROG='
function trim(s) { sub(/^[[:space:]]+/, "", s); sub(/[[:space:]]+$/, "", s); return s }

function extract_id(line,    s, n, parts, i, kv, key, val) {
    s = line
    sub(/^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+/, "", s)
    sub(/[[:space:]]*-->[[:space:]]*$/, "", s)
    n = split(s, parts, /[[:space:]]+/)
    for (i = 1; i <= n; i++) {
        kv = parts[i]
        if (match(kv, /=/) > 0) {
            key = substr(kv, 1, RSTART - 1)
            val = substr(kv, RSTART + 1)
            if (key == "id") return val
        }
    }
    return ""
}

NR == FNR {
    # First file: wanted-ids list, one per line.
    if ($0 != "") wanted[$0] = 1
    next
}

{
    line = $0
    if (in_block == 0) {
        if (line ~ /^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+.*-->[[:space:]]*$/) {
            in_block = 1
            cur_id = extract_id(line)
            cur_body = line
        }
        next
    }
    cur_body = cur_body "\n" line
    if (line ~ /^[[:space:]]*<!--[[:space:]]*\/argos:entry[[:space:]]*-->[[:space:]]*$/) {
        if (cur_id in wanted) {
            print cur_body
            print ""
        }
        in_block = 0
        cur_id = ""
        cur_body = ""
    }
}
'

awk "$APPEND_PROG" "$TMPDIR/sa_A"          "$A" >> "$OUT"
awk "$APPEND_PROG" "$TMPDIR/added_B_only"  "$B" >> "$OUT"

# -----------------------------------------------------------------------------
# Step 5: write to %A atomically.
# -----------------------------------------------------------------------------
mv "$OUT" "$A"

exit 0
