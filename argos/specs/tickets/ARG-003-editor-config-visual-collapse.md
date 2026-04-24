# ARG-003 — Ship editor config for visual collapse of harness-required directories

**Status:** Queued
**Created:** 2026-04-24
**Priority:** P2

## Intent
Reduce visual noise from harness-required root-level directories (.claude/, .cursor/, .codex/, .gemini/, .github/) in VS Code and JetBrains file explorers. These paths can't move (tools hardcode them), but editors can be told to collapse or sort them to the bottom.

## Context
v0.5 consolidated movable files under argos/, but five harness-required directories plus CLAUDE.md and AGENTS.md remain at root by necessity. Users retrofitting onto existing projects find this visually cluttered, especially for public repos where the file tree is part of the project's first impression.

## Non-goals
- Moving the harness directories (impossible — tools hardcode paths)
- Hiding files from git (they need to be committed)
- Any runtime behavior change

## Acceptance criteria (draft)
- [ ] .vscode/settings.json committed to the template with file-explorer hints (folder sort order, file nesting patterns) for Argos-managed roots
- [ ] .idea/ config for JetBrains users (or documented workaround)
- [ ] README section explaining the editor config and how to opt out
- [ ] Config works when committed to repo (shared settings) without forcing user-specific preferences
