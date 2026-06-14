#!/bin/sh
# pre-commit-state-write.sh — enforce "verifier-only writes STATE.md" (ARG1-032).
#
# Rejects any staged commit that modifies argos/specs/STATE.md (or the v1.0
# mirror argos/specs/v1.0/STATE.md) unless the modification consists entirely
# of new <!-- argos:entry ... author=verifier ... --> blocks. The cycle-close
# operation (which removes blocks at the operator's command) bypasses with
# ARGOS_CYCLE_CLOSE=1.
#
# This file is the local-clone enforcement point for the ARCHITECTURE.md
# §Invariants rule that the verifier is the sole writer of STATE.md.
#
# Exit codes:
#   0  — commit allowed (no STATE.md change, or all changes are verifier blocks).
#   1  — STATE.md modified outside append-block (deletion or non-block addition).
#   2  — added block has author other than verifier.
#  64  — usage / internal error.

set -eu

# --- Cycle-close bypass --------------------------------------------------------
if [ "${ARGOS_CYCLE_CLOSE:-0}" = "1" ]; then
    exit 0
fi

# --- Repo discovery ------------------------------------------------------------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
    # Not in a git repo (or git missing) — nothing for us to do.
    exit 0
fi
cd "$REPO_ROOT"

# Files this hook enforces. Keep in sync with install-merge-driver.sh's
# .gitattributes coverage so every file the merge driver protects also has
# pre-commit author enforcement.
STATE_PATHS="argos/specs/STATE.md argos/specs/v1.0/STATE.md"

# --- Validator (awk) -----------------------------------------------------------
#
# Reads a unified diff from stdin (lines beginning with -, +, @@, or file
# headers) and exits non-zero on any modification that violates the
# verifier-only-append invariant. The `file` variable identifies the path for
# the error messages — downstream consumers grep for the literal substrings
# "STATE.md modified outside append-block" and "STATE.md author must be
# verifier", so they MUST appear verbatim in the messages emitted here.

AWK_VALIDATE='
BEGIN { in_block = 0; section = "" }

# Diff metadata — skip without inspecting.
/^---[[:space:]]/         { next }
/^\+\+\+[[:space:]]/      { next }
/^---$/                   { next }
/^\+\+\+$/                { next }
/^@@/                     { next }
/^diff[[:space:]]/        { next }
/^index[[:space:]]/       { next }
/^new file mode/          { next }
/^deleted file mode/      { next }
/^old mode/               { next }
/^new mode/               { next }
/^similarity index/       { next }
/^dissimilarity index/    { next }
/^rename from/            { next }
/^rename to/              { next }
/^copy from/              { next }
/^copy to/                { next }
/^Binary files/           { next }
/^\\[[:space:]]/          { next }   # "\ No newline at end of file"

# The diff is generated with full context (-U<big>), so every unchanged line of
# the file is present as a context line (leading space). That lets us attribute
# each changed line to its ## section (ARG1-078): we track the current section
# as we walk the diff in file order, then apply section-scoped rules.
{
    marker = substr($0, 1, 1)
    rest = substr($0, 2)
}

# --- Section tracking -------------------------------------------------------
# Update the post-image section from context ( ) or added (+) level-2 headings.
# A removed (-) heading does not update it — the unchanged heading context that
# still precedes the change already set the right section.
(marker != "-" && rest ~ /^[[:space:]]*##[[:space:]]+/) {
    s = rest
    sub(/^[[:space:]]*#+[[:space:]]*/, "", s)
    sub(/[[:space:]]+$/, "", s)
    section = s
    if (marker == " ") next   # context heading — nothing to validate
    # an added heading falls through to the addition rules below
}

# Context lines (unchanged) only feed section tracking.
marker == " " { next }

# --- Exempt sections: Queue and In progress (ARG1-078) ----------------------
# These are operator-managed work lists, not the audit trail. Plain bullets and
# blank lines may be freely added OR removed; no entry-block requirement.
(section == "Queue" || section == "In progress") {
    if (marker == "-") next                        # deletions allowed
    if (rest ~ /^[[:space:]]*$/) next              # blank additions allowed
    if (rest ~ /^[[:space:]]*-[[:space:]]*/) next  # bullet additions allowed
    printf("STATE.md modified outside append-block (%s): %s\n",
           file, rest) > "/dev/stderr"
    exit 1
}

# --- Strict sections: Done this cycle + everything else ---------------------
# Any deletion is a violation: the schema is append-only outside cycle close,
# and cycle close already bypassed above.
marker == "-" {
    printf("STATE.md modified outside append-block (%s): deletion of %s\n",
           file, rest) > "/dev/stderr"
    exit 1
}

# Additions: validate the verifier-only entry-block state machine.
marker == "+" {
    line = rest

    # Blank lines (whitespace-only) are permitted anywhere — state-append
    # inserts a leading blank before each block and a trailing blank before
    # the next section heading.
    if (line ~ /^[[:space:]]*$/) next

    if (in_block == 0) {
        if (line ~ /^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+.*-->[[:space:]]*$/) {
            # Extract author=... attribute. Tags are
            # `<!-- argos:entry id=... ticket=... author=... session=... -->`,
            # whitespace-delimited per state-block.md schema.
            inner = line
            sub(/^[[:space:]]*<!--[[:space:]]*argos:entry[[:space:]]+/, "", inner)
            sub(/[[:space:]]*-->[[:space:]]*$/, "", inner)
            n = split(inner, parts, /[[:space:]]+/)
            author = ""
            for (i = 1; i <= n; i++) {
                if (substr(parts[i], 1, 7) == "author=") {
                    author = substr(parts[i], 8)
                }
            }
            if (author != "verifier") {
                printf("STATE.md author must be verifier (%s): got author=%s\n",
                       file, author) > "/dev/stderr"
                exit 2
            }
            in_block = 1
            next
        }
        # Any other added line outside a block is forbidden.
        printf("STATE.md modified outside append-block (%s): %s\n",
               file, line) > "/dev/stderr"
        exit 1
    }

    # in_block == 1: body of an in-progress block. Anything goes; close tag
    # ends the block.
    if (line ~ /^[[:space:]]*<!--[[:space:]]*\/argos:entry[[:space:]]*-->[[:space:]]*$/) {
        in_block = 0
    }
    next
}

# Any other line shape is unexpected diff output — treat as benign and skip.
{ next }

END {
    if (in_block) {
        printf("STATE.md modified outside append-block (%s): unclosed argos:entry block\n",
               file) > "/dev/stderr"
        exit 1
    }
}
'

# --- Per-file enforcement ------------------------------------------------------

OVERALL_RC=0

for STATE_REL in $STATE_PATHS; do
    # Is this file in the staged set?
    if ! git diff --cached --name-only --diff-filter=ACDMR -- "$STATE_REL" 2>/dev/null \
        | grep -F -x -q -- "$STATE_REL"; then
        continue
    fi

    # Outright deletion is a violation.
    status_line="$(git diff --cached --name-status -- "$STATE_REL" 2>/dev/null \
        | head -n1)"
    case "$status_line" in
        D*)
            echo "STATE.md modified outside append-block ($STATE_REL): file deletion not permitted" >&2
            OVERALL_RC=1
            continue
            ;;
        A*)
            # First appearance: STATE.md is newly added (present in the index,
            # absent from HEAD) — this is creation, not modification, so the
            # append-only invariant does not apply (ARG1-073). `argos init`
            # scaffolds STATE.md and commits it as the repo's first commit;
            # without this carve-out the whole scaffold is a wall of `+` prose
            # lines that the awk validator rejects. Allow creation.
            # The already-tracked path (status M) below is unchanged: a tracked
            # STATE.md still goes through full append-only awk validation.
            continue
            ;;
    esac

    # Full context (-U1000000) emits every unchanged line as a context line so
    # the awk validator can attribute each changed line to its ## section
    # (ARG1-078). --no-color avoids escape codes that would confuse the regexes.
    diff_text="$(git diff --cached --no-color -U1000000 -- "$STATE_REL" 2>/dev/null || true)"

    # Empty diff (e.g., file staged for mode change only) — nothing to validate.
    if [ -z "$diff_text" ]; then
        continue
    fi

    if printf '%s\n' "$diff_text" | awk -v file="$STATE_REL" "$AWK_VALIDATE"; then
        :
    else
        rc=$?
        if [ "$rc" -gt "$OVERALL_RC" ]; then
            OVERALL_RC=$rc
        fi
    fi
done

exit "$OVERALL_RC"
