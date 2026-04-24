#!/usr/bin/env bash
# Build Argos harness-specific outputs from source/
# Targets: Claude Code, Cursor, Codex CLI, Gemini CLI
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SOURCE_AGENTS="$ROOT/source/agents"
SOURCE_COMMANDS="$ROOT/source/commands"

[ -d "$SOURCE_AGENTS" ] || { echo "missing $SOURCE_AGENTS"; exit 1; }
[ -d "$SOURCE_COMMANDS" ] || { echo "missing $SOURCE_COMMANDS"; exit 1; }

echo "=== Argos build ==="
echo "source: $SOURCE_AGENTS, $SOURCE_COMMANDS"

# ---- Claude Code ----
build_claude_code() {
  local out="$ROOT/.claude"
  echo "-> claude-code: $out"
  mkdir -p "$out/agents" "$out/commands"
  # Claude Code format matches source/ exactly: copy through
  cp "$SOURCE_AGENTS"/*.md "$out/agents/"
  cp "$SOURCE_COMMANDS"/*.md "$out/commands/"
}

# ---- Cursor ----
build_cursor() {
  local out="$ROOT/.cursor"
  echo "-> cursor: $out"
  mkdir -p "$out/rules" "$out/commands"
  # Cursor rule files are .mdc with different frontmatter; commands are similar to Claude
  # For v0.4 initial: copy agents to rules/ as-is (will tune frontmatter in Phase 3)
  for f in "$SOURCE_AGENTS"/*.md; do
    local base
    base=$(basename "$f" .md)
    cp "$f" "$out/rules/${base}.mdc"
  done
  cp "$SOURCE_COMMANDS"/*.md "$out/commands/"
}

# ---- Codex CLI ----
build_codex() {
  local out="$ROOT/.codex"
  echo "-> codex: $out"
  mkdir -p "$out/agents" "$out/prompts"
  # Codex uses .codex/prompts/ with /prompts:name invocation syntax
  cp "$SOURCE_AGENTS"/*.md "$out/agents/"
  cp "$SOURCE_COMMANDS"/*.md "$out/prompts/"
}

# ---- Gemini CLI ----
build_gemini() {
  local out="$ROOT/.gemini"
  echo "-> gemini: $out"
  mkdir -p "$out/skills"
  # Gemini uses minimal frontmatter under .gemini/skills/
  cp "$SOURCE_AGENTS"/*.md "$out/skills/"
  cp "$SOURCE_COMMANDS"/*.md "$out/skills/"
}

# ---- Root rules files ----
build_rules() {
  echo "-> root rules: CLAUDE.md, AGENTS.md"
  cp "$ROOT/argos/RULES.md" "$ROOT/CLAUDE.md"
  cp "$ROOT/argos/RULES.md" "$ROOT/AGENTS.md"
}

build_claude_code
build_cursor
build_codex
build_gemini
build_rules

echo ""
echo "build complete."
