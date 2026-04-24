# ARG-005 — Scan-report generator for retrofit onto existing codebases

**Status:** Queued
**Created:** 2026-04-24
**Priority:** P2

## Intent
Reduce friction of retrofitting Argos onto existing projects by generating a code inventory that helps the user write PRD.md and ARCHITECTURE.md faster. Not an LLM-driven draft — a deterministic bash-level inventory of languages, dependencies, directory structure, and deployment config.

## Context
Dogfood session on kingl0w/jobhunter showed retrofit requires manually inventorying the codebase before filling in specs. An argos-scan.sh script could produce argos/specs/_scan-report.md with structured findings (detected stack from package.json/requirements.txt/pyproject.toml, top-level dirs with one-line descriptions, docker-compose services, Dockerfile presence, CI workflow presence). User references it while writing specs, then deletes the report when done.

## Non-goals
- LLM-driven spec drafting during init (keep init offline and deterministic)
- Writing specs for the user (scan report is reference material, not output)
- Auto-committing the report
- Running any network calls

## Acceptance criteria (draft)
- [ ] argos/scripts/argos-init.sh prompts "Is this a retrofit onto an existing codebase? [y/N]"
- [ ] If yes, runs argos/scripts/argos-scan.sh
- [ ] Scan detects: languages (from manifest files), top-level dirs, docker-compose services, Dockerfile presence, CI workflow presence
- [ ] Output written to argos/specs/_scan-report.md with explicit "one-time artifact, delete after use" header
- [ ] Works without internet access
- [ ] Does not invoke any LLM
- [ ] Underscore prefix on filename signals transience (_scan-report.md, not scan-report.md)
