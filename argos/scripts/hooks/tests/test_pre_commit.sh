#!/bin/sh
# test_pre_commit.sh — POSIX-shell AC harness for ARG1-032 pre-commit hook.
# Exits 0 iff every test passes. Each test runs in its own mktemp -d sandbox.
#
# Mirrors the style of argos/scripts/tests/test_merge_driver.sh.
#
# Usage:
#   sh argos/scripts/hooks/tests/test_pre_commit.sh
#   ARGOS_TEST_VERBOSE=1 → echo every command.

set -eu

if [ "${ARGOS_TEST_VERBOSE:-0}" = "1" ]; then
    set -x
fi

REPO_ROOT="$(cd "$(dirname "$0")/../../../.." && pwd)"
HOOK="$REPO_ROOT/argos/scripts/hooks/pre-commit-state-write.sh"
INSTALLER="$REPO_ROOT/argos/scripts/install-hooks.sh"

if [ ! -f "$HOOK" ] || [ ! -f "$INSTALLER" ]; then
    echo "test: hook or installer missing under $REPO_ROOT/argos/scripts/" >&2
    exit 1
fi

chmod +x "$HOOK" "$INSTALLER"

COUNTER_DIR="$(mktemp -d)"
ROOT_TMP="$(mktemp -d)"
trap 'rm -rf "$COUNTER_DIR" "$ROOT_TMP"' EXIT INT TERM
: > "$COUNTER_DIR/pass"
: > "$COUNTER_DIR/fail"
: > "$COUNTER_DIR/warn"

pass() { echo "x" >> "$COUNTER_DIR/pass"; echo "PASS: $1"; }
fail() { echo "x" >> "$COUNTER_DIR/fail"; echo "FAIL: $1"; }
warn() { echo "x" >> "$COUNTER_DIR/warn"; echo "WARN: $1"; }

# -----------------------------------------------------------------------------
# Sandbox builder. Lays out a minimal repo mirroring the argos directory shape
# the hook expects (script lives at argos/scripts/hooks/...). STATE.md is seeded
# with one verifier block so prose modifications and block deletions are
# distinguishable.
# -----------------------------------------------------------------------------
make_state_seed() {
    out="$1"
    cat > "$out" <<'EOF'
# Argos — State

**Last updated:** 2026-04-26
**Updated by:** _verifier (automated)_

## Done this cycle

<!-- argos:entry id=2026-04-26T00:00:00Z-ARG1-SEED ticket=ARG1-SEED author=verifier session=seed -->
- Seed entry for AC harness.
<!-- /argos:entry -->

## Known drift

- _none_
EOF
}

setup_repo() {
    sandbox="$1"
    install_hook="${2:-yes}"
    rm -rf "$sandbox"
    mkdir -p "$sandbox"
    (
        cd "$sandbox"
        git init -q
        git config user.email "test@example.com"
        git config user.name  "test"
        git config commit.gpgsign false
        # Mirror the argos layout the hook expects.
        mkdir -p argos/scripts/hooks argos/specs
        cp "$HOOK" argos/scripts/hooks/pre-commit-state-write.sh
        cp "$INSTALLER" argos/scripts/install-hooks.sh
        chmod +x argos/scripts/hooks/pre-commit-state-write.sh argos/scripts/install-hooks.sh
        make_state_seed argos/specs/STATE.md
        git add argos
        git commit -q -m "seed"
        if [ "$install_hook" = "yes" ]; then
            sh argos/scripts/install-hooks.sh > install.out 2>&1
        fi
    )
}

# Like setup_repo, but seeds the repo committing ONLY argos/scripts (the hook +
# installer) and NOT STATE.md, so the file's first commit exercises the
# untracked->tracked "first appearance" path (ARG1-073). The hook is installed.
setup_repo_without_state() {
    sandbox="$1"
    rm -rf "$sandbox"
    mkdir -p "$sandbox"
    (
        cd "$sandbox"
        git init -q
        git config user.email "test@example.com"
        git config user.name  "test"
        git config commit.gpgsign false
        mkdir -p argos/scripts/hooks argos/specs
        cp "$HOOK" argos/scripts/hooks/pre-commit-state-write.sh
        cp "$INSTALLER" argos/scripts/install-hooks.sh
        chmod +x argos/scripts/hooks/pre-commit-state-write.sh argos/scripts/install-hooks.sh
        git add argos/scripts
        git commit -q -m "seed (no STATE.md)"
        sh argos/scripts/install-hooks.sh > install.out 2>&1
    )
}

# -----------------------------------------------------------------------------
# AC#1: install-hooks.sh registers the hook into .git/hooks/pre-commit.
# -----------------------------------------------------------------------------
test_installer_registers() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        if [ ! -f .git/hooks/pre-commit ]; then
            fail "AC#1 .git/hooks/pre-commit not created"
            return 0
        fi
        if [ ! -x .git/hooks/pre-commit ]; then
            fail "AC#1 .git/hooks/pre-commit not executable"
            return 0
        fi
        if grep -F -q -- 'argos/scripts/hooks/pre-commit-state-write.sh' .git/hooks/pre-commit; then
            pass "AC#1 .git/hooks/pre-commit invokes pre-commit-state-write.sh"
        else
            fail "AC#1 invocation line missing — got: $(cat .git/hooks/pre-commit)"
        fi

        # Idempotency: re-running the installer doesn't duplicate the block.
        sh argos/scripts/install-hooks.sh > install2.out 2>&1
        count=$(grep -c -F -- 'argos/scripts/hooks/pre-commit-state-write.sh' .git/hooks/pre-commit || echo 0)
        if [ "$count" = "1" ]; then
            pass "AC#1 installer idempotent (1 invocation line after re-run)"
        else
            fail "AC#1 installer not idempotent — found $count invocation lines"
        fi
    )
}

# -----------------------------------------------------------------------------
# AC#2: a commit that adds only verifier-authored blocks passes.
# -----------------------------------------------------------------------------
test_verifier_block_passes() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        # Append a new verifier block to ## Done this cycle (raw text — no
        # state-append dependency in this AC).
        python3 - argos/specs/STATE.md <<'PY'
import sys
p = sys.argv[1]
with open(p, "r", encoding="utf-8") as f:
    text = f.read()
new_block = (
    "\n<!-- argos:entry id=2026-04-26T01:00:00Z-ARG1-AC2 ticket=ARG1-AC2 "
    "author=verifier session=ac2 -->\n"
    "- AC#2 entry\n"
    "<!-- /argos:entry -->\n"
)
# Insert before ## Known drift heading.
marker = "## Known drift"
i = text.index(marker)
out = text[:i] + new_block + "\n" + text[i:]
with open(p, "w", encoding="utf-8") as f:
    f.write(out)
PY
        git add argos/specs/STATE.md
        if git commit -q -m "verifier append" 2> commit.err; then
            pass "AC#2 verifier-only block append commit succeeds"
        else
            fail "AC#2 commit failed unexpectedly: $(cat commit.err)"
        fi
    )
}

# -----------------------------------------------------------------------------
# AC#3: a commit that modifies STATE.md outside any block fails with the
# required stderr substring.
# -----------------------------------------------------------------------------
test_outside_block_fails() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        # Touch the prose: change "Last updated:".
        sed -i 's/2026-04-26/2026-05-01/' argos/specs/STATE.md
        git add argos/specs/STATE.md
        if git commit -m "tamper prose" > commit.out 2>&1; then
            fail "AC#3 commit unexpectedly succeeded"
            return 0
        fi
        if grep -F -q -- 'STATE.md modified outside append-block' commit.out; then
            pass "AC#3 stderr contains 'STATE.md modified outside append-block'"
        else
            fail "AC#3 stderr missing required substring; got: $(cat commit.out)"
        fi
    )
}

# -----------------------------------------------------------------------------
# AC#4: a commit that adds a block with author=coder fails with the required
# stderr substring.
# -----------------------------------------------------------------------------
test_coder_author_fails() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        python3 - argos/specs/STATE.md <<'PY'
import sys
p = sys.argv[1]
with open(p, "r", encoding="utf-8") as f:
    text = f.read()
new_block = (
    "\n<!-- argos:entry id=2026-04-26T02:00:00Z-ARG1-AC4 ticket=ARG1-AC4 "
    "author=coder session=ac4 -->\n"
    "- AC#4 entry (coder authored — should be rejected)\n"
    "<!-- /argos:entry -->\n"
)
marker = "## Known drift"
i = text.index(marker)
out = text[:i] + new_block + "\n" + text[i:]
with open(p, "w", encoding="utf-8") as f:
    f.write(out)
PY
        git add argos/specs/STATE.md
        if git commit -m "coder author" > commit.out 2>&1; then
            fail "AC#4 commit unexpectedly succeeded"
            return 0
        fi
        if grep -F -q -- 'STATE.md author must be verifier' commit.out; then
            pass "AC#4 stderr contains 'STATE.md author must be verifier'"
        else
            fail "AC#4 stderr missing required substring; got: $(cat commit.out)"
        fi
    )
}

# -----------------------------------------------------------------------------
# AC#5: ARGOS_CYCLE_CLOSE=1 bypasses the hook even when STATE.md has block
# deletions.
# -----------------------------------------------------------------------------
test_cycle_close_bypass() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        # Delete the seed block entirely (simulating cycle close).
        python3 - argos/specs/STATE.md <<'PY'
import re, sys
p = sys.argv[1]
with open(p, "r", encoding="utf-8") as f:
    text = f.read()
text = re.sub(
    r"<!-- argos:entry [^>]+ -->\n.*?\n<!-- /argos:entry -->\n",
    "",
    text,
    flags=re.DOTALL,
)
with open(p, "w", encoding="utf-8") as f:
    f.write(text)
PY
        git add argos/specs/STATE.md
        # First, sanity-check that without the bypass it fails.
        if git commit -m "delete (no bypass)" > commit_no_bypass.out 2>&1; then
            fail "AC#5 baseline: commit succeeded without bypass (block removal should fail)"
            return 0
        fi
        # Now retry with ARGOS_CYCLE_CLOSE=1.
        if ARGOS_CYCLE_CLOSE=1 git commit -m "cycle close" > commit.out 2>&1; then
            pass "AC#5 ARGOS_CYCLE_CLOSE=1 bypass: block deletion accepted"
        else
            fail "AC#5 ARGOS_CYCLE_CLOSE=1 bypass failed: $(cat commit.out)"
        fi
    )
}

# -----------------------------------------------------------------------------
# AC#6: a commit that does not touch STATE.md exits 0 (no false positives).
# -----------------------------------------------------------------------------
test_unrelated_commit_passes() {
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        echo "hello" > unrelated.txt
        git add unrelated.txt
        if git commit -q -m "unrelated" 2> commit.err; then
            pass "AC#6 unrelated commit (no STATE.md change) succeeds"
        else
            fail "AC#6 unrelated commit failed unexpectedly: $(cat commit.err)"
        fi
    )
}

# -----------------------------------------------------------------------------
# Interop: `python3 -m argos.cli state-append` succeeds under the hook.
# Skipped (warn) if argos.cli isn't importable in the host env.
# -----------------------------------------------------------------------------
test_state_append_interop() {
    if ! ( cd "$REPO_ROOT" && python3 -c 'import argos.cli' >/dev/null 2>&1 ); then
        warn "interop skipped — python3 -m argos.cli unavailable in host env"
        return 0
    fi
    sandbox="$1"
    setup_repo "$sandbox" yes
    (
        cd "$sandbox"
        echo "- interop body" > body.md
        if ! ( PYTHONPATH="$REPO_ROOT" python3 -m argos.cli state-append \
                  --section "Done this cycle" \
                  --ticket ARG1-AC7 \
                  --author verifier \
                  --session ac7 \
                  --suffix done \
                  --body-file body.md \
                  --state-file argos/specs/STATE.md \
              ) > append.out 2>&1; then
            fail "interop state-append failed: $(cat append.out)"
            return 0
        fi
        git add argos/specs/STATE.md
        if git commit -q -m "verifier writeback" 2> commit.err; then
            pass "interop state-append + commit succeeds under hook"
        else
            fail "interop commit failed: $(cat commit.err)"
        fi
    )
}

# -----------------------------------------------------------------------------
# ARG1-073: the first appearance of STATE.md (untracked -> tracked) is creation,
# not modification, and must commit cleanly without the ARGOS_CYCLE_CLOSE bypass.
# The scaffolded STATE.md is a wall of prose that would fail append-only if it
# were treated as a modification, so a clean commit proves the carve-out fires.
# -----------------------------------------------------------------------------
test_untracked_state_commits_clean() {
    sandbox="$1"
    setup_repo_without_state "$sandbox"
    (
        cd "$sandbox"
        # STATE.md has never been tracked; scaffold it fresh (prose + a seed
        # block, like `argos init` does) and commit it.
        make_state_seed argos/specs/STATE.md
        git add argos/specs/STATE.md
        if git commit -q -m "scaffold STATE.md" 2> commit.err; then
            pass "ARG1-073 untracked STATE.md first commit succeeds without ARGOS_CYCLE_CLOSE"
        else
            fail "ARG1-073 untracked STATE.md first commit rejected: $(cat commit.err)"
        fi
    )
}

# -----------------------------------------------------------------------------
# Run all tests.
# -----------------------------------------------------------------------------
test_installer_registers   "$ROOT_TMP/s1"
test_verifier_block_passes "$ROOT_TMP/s2"
test_outside_block_fails   "$ROOT_TMP/s3"
test_coder_author_fails    "$ROOT_TMP/s4"
test_cycle_close_bypass    "$ROOT_TMP/s5"
test_unrelated_commit_passes "$ROOT_TMP/s6"
test_state_append_interop  "$ROOT_TMP/s7"
test_untracked_state_commits_clean "$ROOT_TMP/s8"

PASSES=$(wc -l < "$COUNTER_DIR/pass" | tr -d ' ')
FAILS=$(wc -l < "$COUNTER_DIR/fail" | tr -d ' ')
WARNS=$(wc -l < "$COUNTER_DIR/warn" | tr -d ' ')

echo
echo "Summary: $PASSES pass, $FAILS fail, $WARNS warn"
[ "$FAILS" = "0" ]
