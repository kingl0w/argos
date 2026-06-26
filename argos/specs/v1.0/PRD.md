---
name: argos-v1.0-prd
description: Product requirements for argos v1.0 — semi-autonomous spec-driven guardrail layer over Claude Code subagents
status: draft
version: 1.0
---

# Argos v1.0 — Product Requirements

**Created:** 2026-04-26
**Status:** Draft
**Owner:** kingl0w

## One-line pitch

Argos v1.0 turns the v0.5 spec-driven scaffold into a semi-autonomous loop: it parallelizes independent tickets, splits work across scoped agents, and pings the operator only on genuine ambiguity — keeping Claude Code on rails without gating every step.

## Problem

v0.5 ships a four-agent loop (planner → coder → watchdog → verifier) that catches drift and keeps specs as the source of truth, but every ticket runs sequentially and every phase boundary is a human checkpoint. A solo developer running an Epic of five independent tickets spends the wall-clock cost of five sequential `/next` invocations and the attention cost of ~20 confirm-and-continue beats. The current workaround is "just stay at the keyboard," which defeats the point of an agent loop. What changed: Claude Code subagents are now reliable enough that the bottleneck is orchestration, not generation.

## Target user

- **Primary:** Solo developers running Argos against their own repos via Claude Code, working in Epics of 1–10 tickets.
- **Secondary:** Solo developers on adjacent harnesses (Cursor, Codex, Gemini) who can tolerate experimental multi-harness support.
- **Non-user:** Teams needing shared dashboards, role-based routing, or hosted multi-tenant operation. v1.0 leaves room for them architecturally but does not serve them.

## Goals

1. **After v1.0, an operator can dispatch an Epic of ≥3 independent tickets and walk away for ≥15 minutes**, returning to either a clean STATE.md update per ticket or a precise ambiguity prompt — not a wall of confirm-to-continue beats.
2. **After v1.0, ≥95% of coder scope-drift violations are caught by watchdog before STATE.md is updated**, holding the v0.5 guardrail invariant under autonomous operation.
3. **After v1.0, ≥80% of operator pings are genuine ambiguity** (decisions the orchestrator cannot make from specs + ticket alone), not false alarms or routine progress reports.
4. **After v1.0, an Epic with ≥3 independent tickets completes in ≤½ the wall-clock time of v0.5 sequential execution.**
5. **After v1.0, `argos status` exits clean (zero) after every autonomous run that the verifier accepted** — spec integrity is observable from a single command.

## Non-goals

- **Differentiation against hosted competitors** (Bart, etc.). v1.0 wins on the "specs-as-source-of-truth, runs in your harness" axis or it doesn't ship — feature parity for parity's sake is out.
- **Team features:** shared dashboards, role-based routing, multi-operator locking, presence. Architecture leaves room (append-mostly STATE.md, project-vs-local config split) but v1.0 ships none of it.
- **Hosted SaaS layer.** No argos.cloud, no managed runtime, no telemetry pipeline beyond what the operator opts into locally.
- **Multi-harness feature parity.** Claude Code is the primary harness. Cursor / Codex / Gemini support is experimental and may lag by a minor version.

## Success metrics

- **Leading indicator:** ratio of autonomous-completed tickets to operator-touched tickets per Epic, measured weekly on the maintainer's own usage. Target: ≥0.7 by end of v1.0.x series.
- **Lagging indicator:** total operator interaction time per Epic (clock time spent reading prompts, typing decisions). Target: ≤15 min/Epic at the median.
- **Guardrail:** scope-drift catch rate must not regress below v0.5's measured baseline. If autonomous runs leak more drift than supervised v0.5 runs, v1.0 is a regression regardless of speed gains.

## Constraints

- **Technical — specs are source of truth.** Everything under `argos/specs/` (STATE.md, ARCHITECTURE.md, tickets, ADRs) remains canonical. The orchestrator's decisions must be reconstructable from these files; no orchestrator-only state that lives outside the repo.
- **Technical — four-agent foundation.** The planner / coder / watchdog / verifier roles from v0.5 are preserved. The orchestrator sits *above* them, dispatching and reconciling. It does not replace any of the four, and it does not collapse their separation of concerns (e.g., orchestrator never updates STATE.md — that stays the verifier's exclusive write).
- **Technical — markdown-first.** Orchestrator decisions (which tickets are independent, which were dispatched in parallel, which escalated and why) are written as inspectable files (e.g., per-Epic dispatch logs, per-ticket escalation notes). No opaque runtime state, no required database, no required daemon.
- **Technical — Claude Code is primary.** Multi-harness support stays experimental in v1.0. Argos must not require a harness feature only Claude Code provides for its critical path; where it does, the dependency is documented and the fallback is "run sequentially under the supported harness."
- **Resource:** single maintainer, no funded runway. Scope must fit what one person can ship and dogfood.
- **External:** Claude Code's subagent API surface. Argos cannot ship features that depend on unreleased harness primitives.

## Distribution

- **CLI installer.** Argos v1.0 is installed and operated via a `argos` binary, not by cloning the repo into a project.
- **Commands (v1.0 public surface):**
  - `argos init` — scaffold `argos/specs/`, install hooks, register slash commands in the harness config.
  - `argos sync` — reconcile ticket files ↔ GitHub Issues; reconcile STATE.md against `git log` if drifted.
  - `argos status` — exit 0 iff specs are internally consistent and STATE.md matches git reality; nonzero with a one-screen diagnosis otherwise.
- **Versioning:** semver. v1.0.0 is the first stable release; breaking changes to spec file shapes or the four-agent contract require a major bump.
- **Packaging channel:** TODO — npm vs. homebrew vs. cargo vs. standalone binary. Decision blocks the installer ticket; file an ADR before scaffolding the release pipeline.

## Open questions

- [ ] **Epic boundary.** What declares an Epic? A label on tickets? A frontmatter field? A queue grouping in STATE.md? The success metrics ("≤15 min/Epic", "≥3 independent tickets") need a concrete unit. TODO: decide before drafting the orchestrator ticket.
- [ ] **Independence detection.** How does the orchestrator decide two tickets are safe to run in parallel? File-overlap heuristic from the planner output? Explicit `depends_on:` frontmatter? Mixed? TODO.
- [ ] **Parallelism mechanism.** Multiple concurrent Claude Code sessions? A single session with parallel subagent dispatches? Out-of-process workers coordinated via the file system? Each has different harness-coupling implications. TODO.
- [ ] **Escalation channel.** When the orchestrator decides "this is genuine ambiguity," where does the ping land? Stdout in the running session? A file the operator polls? An OS notification? TODO — affects walk-away time metric.
- [ ] **Operator interaction measurement.** "≤15 min" is the goal; we need a definition of what counts. Active typing? Wall-clock between first prompt and last confirm? TODO before we can self-measure.
- [ ] **Project-vs-local config split.** The team-deferral decision rests on this split existing. v1.0 must define the split (which keys live in repo-checked config vs. operator-local overrides) even though no team feature consumes it yet. TODO.
- [ ] **Failure-mode budget.** v0.5 has 1 retry between planner and coder, 0 for verifier. Does autonomous v1.0 keep these caps, or does walk-away operation justify higher retry budgets with stricter guards? TODO.

## Out-of-band context

- **v0.5 lineage.** v1.0 is an evolution of the v0.5 scaffold currently self-hosted in this repo (`argos/specs/`). v0.5 tickets ARG-001…005 should close before or during v1.0 development; their fixes are prerequisite quality-of-life for autonomous operation (notably ARG-001 — `argos status` exit codes — which v1.0 success criterion #5 depends on).
- **Why "Argos."** The hundred-eyed watcher. The product premise is that an agent loop without independent observers drifts; v1.0 keeps the watchers and adds an orchestrator that knows when to wake the human.
- **Bart and similar.** Hosted competitors exist and are explicitly out of scope for differentiation (see non-goals). The reason to know they exist: they validate the demand and shape user expectations around what "autonomous coding agent" means. v1.0 should not be surprised when users compare.
- **Dogfooding constraint.** v1.0 is built using v0.5 against this repo. Any v1.0 feature must be expressible as a sequence of v0.5-style tickets — if a v1.0 capability cannot be planned, coded, watchdogged, and verified within the v0.5 loop, that is itself a signal the design is wrong.
