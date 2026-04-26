#!/bin/sh
# test_merge_driver.sh — POSIX-shell test harness for ARG1-052 merge driver.
# Exits 0 iff every test passes. Each test runs in its own mktemp -d sandbox.
#
# Usage: sh argos/scripts/tests/test_merge_driver.sh
#   ARGOS_TEST_VERBOSE=1 → echo every command.
set -eu

if [ "${ARGOS_TEST_VERBOSE:-0}" = "1" ]; then
    set -x
fi

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DRIVER="$REPO_ROOT/argos/scripts/state-merge-driver.sh"
INSTALLER="$REPO_ROOT/argos/scripts/install-merge-driver.sh"

if [ ! -f "$DRIVER" ] || [ ! -f "$INSTALLER" ]; then
    echo "test: driver or installer missing under $REPO_ROOT/argos/scripts/" >&2
    exit 1
fi

chmod +x "$DRIVER" "$INSTALLER"

COUNTER_DIR="$(mktemp -d)"
trap 'rm -rf "$COUNTER_DIR"' EXIT INT TERM
: > "$COUNTER_DIR/pass"
: > "$COUNTER_DIR/fail"
: > "$COUNTER_DIR/warn"

pass() { echo "x" >> "$COUNTER_DIR/pass"; echo "PASS: $1"; }
fail() { echo "x" >> "$COUNTER_DIR/fail"; echo "FAIL: $1"; }
warn() { echo "x" >> "$COUNTER_DIR/warn"; echo "WARN: $1"; }

# Build a minimal STATE.md fixture under $1 (path), with optional extra blocks
# from stdin. Each line on stdin is ID:TICKET:AUTHOR:SESSION:BODY_LINE.
make_state_file() {
    out="$1"
    cat > "$out" <<'HDR'
# STATE — fixture

## Done this cycle

HDR
    while IFS=: read -r bid btk bau bse bbody; do
        [ -n "$bid" ] || continue
        printf '<!-- argos:entry id=%s ticket=%s author=%s session=%s -->\n' \
            "$bid" "$btk" "$bau" "$bse" >> "$out"
        printf -- '- %s\n' "$bbody" >> "$out"
        printf -- '<!-- /argos:entry -->\n\n' >> "$out"
    done
}

# Set up a sandbox repo with the merge driver registered.
setup_repo() {
    sandbox="$1"
    mkdir -p "$sandbox"
    (
        cd "$sandbox"
        git init -q
        git config user.email "test@example.com"
        git config user.name  "test"
        # Symlink driver into a stable path inside the sandbox.
        mkdir -p argos/scripts
        cp "$DRIVER" argos/scripts/state-merge-driver.sh
        chmod +x argos/scripts/state-merge-driver.sh
        # Register driver locally.
        git config merge.argos-state.name "Argos test"
        git config merge.argos-state.driver "argos/scripts/state-merge-driver.sh %O %A %B %P %L"
        git config merge.argos-state.recursive "binary"
        # .gitattributes registers our STATE.md test file.
        echo "STATE.md merge=argos-state" > .gitattributes
        git add .gitattributes argos
        git commit -q -m "init driver"
    )
}

# -----------------------------------------------------------------------------
# Test 1 (AC#1): installer registers the driver.
# -----------------------------------------------------------------------------
test_installer_registers() {
    sandbox="$1"
    rm -rf "$sandbox"
    mkdir -p "$sandbox"
    (
        cd "$sandbox"
        git init -q
        git config user.email "test@example.com"
        git config user.name  "test"
        # Mirror the argos layout for the installer.
        mkdir -p argos/scripts
        cp "$DRIVER" argos/scripts/state-merge-driver.sh
        cp "$INSTALLER" argos/scripts/install-merge-driver.sh
        chmod +x argos/scripts/*.sh
        sh argos/scripts/install-merge-driver.sh > install.out 2>&1
        val=$(git config --get merge.argos-state.driver || true)
        if echo "$val" | grep -q state-merge-driver.sh; then
            pass "AC#1 installer registers driver (driver=$val)"
        else
            fail "AC#1 installer registers driver — got: '$val'"
        fi
    )
}

# -----------------------------------------------------------------------------
# Test 2 (AC#2): .gitattributes contains the AC literal line.
# -----------------------------------------------------------------------------
test_gitattributes_line() {
    sandbox="$1"
    (
        cd "$sandbox"
        if grep -F -q -- 'argos/specs/STATE.md merge=argos-state' .gitattributes; then
            pass "AC#2 .gitattributes contains literal line"
        else
            fail "AC#2 .gitattributes missing literal line"
        fi
        if grep -F -q -- 'argos/specs/v1.0/STATE.md merge=argos-state' .gitattributes; then
            pass "AC#2 .gitattributes contains v1.0 path line"
        else
            fail "AC#2 .gitattributes missing v1.0 line"
        fi
    )
}

# -----------------------------------------------------------------------------
# Test 3 (AC#3): two-branch parallel block merge — both blocks present, no markers.
# -----------------------------------------------------------------------------
test_two_branch_concat() {
    sandbox="$1"
    rm -rf "$sandbox"
    setup_repo "$sandbox"
    (
        cd "$sandbox"
        # Base STATE.md (no blocks).
        make_state_file STATE.md </dev/null
        git add STATE.md
        git commit -q -m "base"

        BASE_COUNT=$(grep -c '<!-- argos:entry' STATE.md || true)

        git checkout -q -b branchA
        echo '<!-- argos:entry id=2026-04-26T10:00:00Z-ARG-A1 ticket=ARG-A1 author=verifier session=sa -->' >> STATE.md
        echo '- A1 entry' >> STATE.md
        echo '<!-- /argos:entry -->' >> STATE.md
        git add STATE.md
        git commit -q -m "A: add A1"

        git checkout -q main 2>/dev/null || git checkout -q master 2>/dev/null || git checkout -q -
        # Find the original branch.
        git checkout -q HEAD~0  # no-op; we need the base branch by name
    )
    # Switch to the base branch and create branchB. Use detached fallback.
    (
        cd "$sandbox"
        BASE_BRANCH=$(git rev-parse --abbrev-ref HEAD)
        # If we're on branchA still, get back to base via the SHA of the base commit.
        BASE_SHA=$(git log --format=%H --grep "^base$" | head -n1)
        git checkout -q "$BASE_SHA" -B branchB
        echo '<!-- argos:entry id=2026-04-26T11:00:00Z-ARG-B1 ticket=ARG-B1 author=verifier session=sb -->' >> STATE.md
        echo '- B1 entry' >> STATE.md
        echo '<!-- /argos:entry -->' >> STATE.md
        git add STATE.md
        git commit -q -m "B: add B1"

        # Merge branchA into branchB.
        if git merge --no-edit branchA > merge.out 2>&1; then
            :
        else
            fail "AC#3 merge exited non-zero: $(cat merge.out)"
            return 0
        fi

        ENTRY_COUNT=$(grep -c '<!-- argos:entry' STATE.md || echo 0)
        if [ "$ENTRY_COUNT" = "2" ]; then
            pass "AC#3 merged STATE.md contains 2 entries (was 0 in base)"
        else
            fail "AC#3 expected 2 entries, got $ENTRY_COUNT"
        fi

        if grep -q '^<<<<<<<' STATE.md; then
            fail "AC#3 conflict markers found in merged file"
        else
            pass "AC#3 no conflict markers in merged file"
        fi

        # Persist sandbox path for AC#6 to reuse.
        echo "$sandbox/STATE.md" > /tmp/argos_test_merged_path.$$
    )
}

# -----------------------------------------------------------------------------
# Test 4 (AC#4): same-id collision keeps exactly one.
# -----------------------------------------------------------------------------
test_same_id_collision() {
    sandbox="$1"
    rm -rf "$sandbox"
    setup_repo "$sandbox"
    (
        cd "$sandbox"
        make_state_file STATE.md </dev/null
        git add STATE.md
        git commit -q -m "base"

        BASE_SHA=$(git rev-parse HEAD)

        git checkout -q -b branchA
        cat >> STATE.md <<'EOF'
<!-- argos:entry id=2026-04-26T12:00:00Z-ARG-DUP ticket=ARG-DUP author=verifier session=sa -->
- A side body
<!-- /argos:entry -->
EOF
        git add STATE.md && git commit -q -m "A: add DUP"

        git checkout -q "$BASE_SHA" -B branchB
        cat >> STATE.md <<'EOF'
<!-- argos:entry id=2026-04-26T12:00:00Z-ARG-DUP ticket=ARG-DUP author=verifier session=sa -->
- A side body
<!-- /argos:entry -->
EOF
        git add STATE.md && git commit -q -m "B: add DUP (identical)"

        if git merge --no-edit branchA > merge.out 2>&1; then
            :
        else
            fail "AC#4 merge exited non-zero: $(cat merge.out)"
            return 0
        fi

        DUP_COUNT=$(grep -c 'id=2026-04-26T12:00:00Z-ARG-DUP' STATE.md || echo 0)
        if [ "$DUP_COUNT" = "1" ]; then
            pass "AC#4 same-id collision deduped to 1 entry"
        else
            fail "AC#4 expected 1 entry with that id, got $DUP_COUNT"
        fi
    )
}

# -----------------------------------------------------------------------------
# Test 5 (AC#5): body-modified violation fails with named id in stderr.
# -----------------------------------------------------------------------------
test_body_modified_fails() {
    sandbox="$1"
    rm -rf "$sandbox"
    setup_repo "$sandbox"
    (
        cd "$sandbox"
        cat > STATE.md <<'EOF'
# STATE — fixture

## Done this cycle

<!-- argos:entry id=2026-04-26T13:00:00Z-ARG-MOD ticket=ARG-MOD author=verifier session=so -->
- original body
<!-- /argos:entry -->

EOF
        git add STATE.md && git commit -q -m "base with one block"

        BASE_SHA=$(git rev-parse HEAD)

        git checkout -q -b branchA
        # Modify the existing block's body.
        sed -i 's/- original body/- modified body/' STATE.md
        git add STATE.md && git commit -q -m "A: mutate body"

        git checkout -q "$BASE_SHA" -B branchB
        # Append a new, well-formed block on the other side so a 3-way merge happens.
        cat >> STATE.md <<'EOF'
<!-- argos:entry id=2026-04-26T13:30:00Z-ARG-NEW ticket=ARG-NEW author=verifier session=sn -->
- new entry
<!-- /argos:entry -->
EOF
        git add STATE.md && git commit -q -m "B: append new"

        # Merge should fail.
        if git merge --no-edit branchA > merge.out 2>&1; then
            fail "AC#5 merge unexpectedly succeeded"
            return 0
        fi

        # Driver stderr is captured by git merge's output. Look at it + git status.
        if grep -q 'block body modified — append-only violated' merge.out; then
            pass "AC#5 stderr contains required violation message"
        else
            fail "AC#5 stderr missing 'block body modified — append-only violated'; got: $(cat merge.out)"
        fi
        if grep -q 'id=2026-04-26T13:00:00Z-ARG-MOD' merge.out; then
            pass "AC#5 stderr names the offending id"
        else
            fail "AC#5 stderr missing offending id; got: $(cat merge.out)"
        fi
        if git status --porcelain | grep -q 'STATE.md'; then
            pass "AC#5 git status shows STATE.md conflicted/modified"
        else
            fail "AC#5 git status does not show STATE.md as conflicted"
        fi
    )
}

# -----------------------------------------------------------------------------
# Test 6 (AC#6): merged file parses cleanly with state-parse.
# -----------------------------------------------------------------------------
test_state_parse_roundtrip() {
    if [ ! -f /tmp/argos_test_merged_path.$$ ]; then
        warn "AC#6 skipped — no merged fixture from AC#3"
        return 0
    fi
    merged_path=$(cat /tmp/argos_test_merged_path.$$)
    rm -f /tmp/argos_test_merged_path.$$
    if [ ! -f "$merged_path" ]; then
        warn "AC#6 skipped — merged fixture missing at $merged_path"
        return 0
    fi
    if ! ( cd "$REPO_ROOT" && python3 -c 'import argos.cli' >/dev/null 2>&1 ); then
        warn "AC#6 skipped — python3 -m argos.cli unavailable in host env"
        return 0
    fi
    parse_err="$COUNTER_DIR/parse.err"
    if ( cd "$REPO_ROOT" && python3 -m argos.cli state-parse "$merged_path" ) >/dev/null 2>"$parse_err"; then
        pass "AC#6 state-parse exits 0 on merged fixture"
    else
        fail "AC#6 state-parse failed: $(cat "$parse_err" 2>/dev/null || true)"
    fi
}

# -----------------------------------------------------------------------------
# Test 7 (AC#7): perf — 500+500 unique blocks merge under 1 second.
# -----------------------------------------------------------------------------
test_perf_1000_blocks() {
    sandbox="$1"
    rm -rf "$sandbox"
    setup_repo "$sandbox"
    (
        cd "$sandbox"
        make_state_file STATE.md </dev/null
        git add STATE.md && git commit -q -m "base"

        BASE_SHA=$(git rev-parse HEAD)

        git checkout -q -b branchA
        i=0
        while [ "$i" -lt 500 ]; do
            printf '<!-- argos:entry id=A-%05d ticket=ARG-PA author=verifier session=spA -->\n- A entry %d\n<!-- /argos:entry -->\n' "$i" "$i" >> STATE.md
            i=$((i + 1))
        done
        git add STATE.md && git commit -q -m "A: 500 blocks"

        git checkout -q "$BASE_SHA" -B branchB
        i=0
        while [ "$i" -lt 500 ]; do
            printf '<!-- argos:entry id=B-%05d ticket=ARG-PB author=verifier session=spB -->\n- B entry %d\n<!-- /argos:entry -->\n' "$i" "$i" >> STATE.md
            i=$((i + 1))
        done
        git add STATE.md && git commit -q -m "B: 500 blocks"

        # Time the merge.
        START=$(date +%s%N)
        if ! git merge --no-edit branchA > merge.out 2>&1; then
            fail "AC#7 merge failed: $(cat merge.out)"
            return 0
        fi
        END=$(date +%s%N)
        ELAPSED_NS=$((END - START))
        ELAPSED_MS=$((ELAPSED_NS / 1000000))

        TOTAL=$(grep -c '<!-- argos:entry' STATE.md || echo 0)
        if [ "$TOTAL" != "1000" ]; then
            fail "AC#7 expected 1000 blocks, got $TOTAL"
            return 0
        fi
        if [ "$ELAPSED_MS" -lt 1000 ]; then
            pass "AC#7 1000-block merge in ${ELAPSED_MS}ms (< 1000ms)"
        else
            fail "AC#7 1000-block merge took ${ELAPSED_MS}ms (>= 1000ms)"
        fi
    )
}

# -----------------------------------------------------------------------------
# Run all tests.
# -----------------------------------------------------------------------------
ROOT_TMP="$(mktemp -d)"
# Append cleanup of ROOT_TMP without overwriting COUNTER_DIR's trap.
trap 'rm -rf "$COUNTER_DIR" "$ROOT_TMP"' EXIT INT TERM

# AC#1 + AC#2 share one sandbox (installer creates .gitattributes there).
SANDBOX1="$ROOT_TMP/s1"
test_installer_registers "$SANDBOX1"
test_gitattributes_line  "$SANDBOX1"

test_two_branch_concat   "$ROOT_TMP/s3"
test_same_id_collision   "$ROOT_TMP/s4"
test_body_modified_fails "$ROOT_TMP/s5"
test_state_parse_roundtrip
test_perf_1000_blocks    "$ROOT_TMP/s7"

PASSES=$(wc -l < "$COUNTER_DIR/pass" | tr -d ' ')
FAILS=$(wc -l < "$COUNTER_DIR/fail" | tr -d ' ')
WARNS=$(wc -l < "$COUNTER_DIR/warn" | tr -d ' ')

echo
echo "Summary: $PASSES pass, $FAILS fail, $WARNS warn"
[ "$FAILS" = "0" ]
