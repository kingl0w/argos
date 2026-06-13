---
name: argos-v1.0-architecture
description: Architecture for argos v1.0 — orchestrator above the four-agent loop, parallel sessions via worktrees, severity-tiered verification
status: draft
version: 1.0
---

# Argos v1.0 — Architecture

**Created:** 2026-04-26
**Last material change:** 2026-04-26

This document describes the structure of Argos v1.0: the orchestrator that sits above the v0.5 four-agent loop, the parallel-session machinery that runs N tickets concurrently via git worktrees, the append-mostly STATE.md format that survives concurrent writes, the project/local config split, the escalation channel, and the severity-tiered verifier.

It is canonical. If the code contradicts this document, the code is drifting — file an ADR and update this file.

## System shape

```
                     ┌──────────────────┐
                     │    operator      │
                     │  (CLI + attend)  │
                     └────────┬─────────┘
                              │ argos init / sync / status / attend
                              ▼
                     ┌──────────────────┐
                     │   orchestrator   │  ← v1.0 addition
                     │  (above loop)    │
                     └────────┬─────────┘
                              │ dispatches N independent tickets
              ┌───────────────┼────────────────┐
              ▼               ▼                ▼
       ┌───────────┐   ┌───────────┐    ┌───────────┐
       │ session 1 │   │ session 2 │ …  │ session N │   ← Claude Code session
       │ worktree  │   │ worktree  │    │ worktree  │   ← per-ticket worktree
       └─────┬─────┘   └─────┬─────┘    └─────┬─────┘
             │               │                │
             ▼               ▼                ▼
       planner→coder→watchdog→verifier  (v0.5 loop, unchanged)
             │               │                │
             └───────────────┼────────────────┘
                             ▼
                    ┌──────────────────┐
                    │ argos/specs/     │  ← canonical state
                    │  STATE.md        │  ← append-mostly, verifier-only
                    │  tickets/        │  ← orchestrator + verifier write
                    │  escalations/    │  ← orchestrator writes, operator drains
                    └──────────────────┘
```

The orchestrator is a new top-level component. It does not replace any of the four agents; it spawns and routes them. The four-agent loop runs unmodified inside each session.

## Components

### Orchestrator

**What it is.** A new agent (running in the top-level Claude Code session, or as a thin Python/Bash driver — TODO: pick one before the orchestrator ticket) that owns Epic-level dispatch. It reads the queue from STATE.md, decides which tickets are independent, spawns sessions, monitors results, and surfaces escalations.

**What it owns.**
- Reading the queue and selecting the next batch of tickets to dispatch.
- Independence analysis (file-scope analysis — see §Parallel Session Manager).
- Spawning per-ticket sessions in dedicated worktrees.
- Routing escalations from sessions into `argos/specs/escalations/`.
- Updating ticket files (`argos/specs/tickets/*.md`) with dispatch metadata: which session ID ran the ticket, which worktree, start/end timestamps, parallel batch ID.
- Writing per-Epic dispatch logs to `argos/specs/dispatch/`.

**What it explicitly does not own.**
- **Cannot write to `argos/specs/PRD.md`.** Product surface is human-only.
- **Cannot write to `argos/specs/ARCHITECTURE.md`.** Architecture changes require a human-written ADR.
- **Cannot write to `argos/specs/STATE.md`.** STATE.md remains the verifier's exclusive write surface, even under autonomous operation. The orchestrator reads STATE.md to pick work; it does not edit it.
- **Cannot mutate code.** All code changes happen inside spawned sessions, attributed to the coder agent inside that session.
- **Cannot run tests or declare verification outcomes.** The verifier inside each session owns verification; the orchestrator only relays the verifier's pass/fail signal.

**Allowed-tools set (Claude Code subagent config).**
```yaml
allowed_tools:
  - Read                        # all spec files, all ticket files
  - Edit                        # tickets/*.md only — enforced by hook
  - Write                       # dispatch/*.md, escalations/*.md only — enforced by hook
  - Bash                        # git worktree, claude-code session spawn, argos CLI
  - Grep
  - Glob
denied_paths:
  - argos/specs/PRD.md
  - argos/specs/ARCHITECTURE.md
  - argos/specs/STATE.md
  - "**/*.{ts,tsx,js,py,rs,go,sh}"   # no source code edits
```

**Authority boundary.** The orchestrator is a *dispatcher and reconciler*. If it is tempted to make a code-shaped or spec-shaped decision, that decision is by definition an escalation. Escalations go to the operator via `argos attend`; the orchestrator does not adjudicate.

### Parallel Session Manager

**What it is.** A subcomponent of the orchestrator (not a separate agent) responsible for the mechanics of running N Claude Code sessions concurrently against N independent tickets.

**Worktree strategy.**
- One git worktree per dispatched ticket. Path: `.argos/worktrees/{ticket-id}-{short-sha}/`.
- Worktrees branch from the same base commit (typically `main` or the operator's current HEAD at dispatch time). Branch name: `argos/{ticket-id}`.
- Each session runs `claude-code` with its working directory pinned to the worktree path. The session sees only that worktree; it cannot reach sibling worktrees because they live outside its CWD subtree.
- On verifier pass: orchestrator merges the worktree branch back to base via fast-forward if possible, or three-way merge if base has moved. Merge conflicts halt the merge and escalate (the verifier already passed — conflicts are an integration-level concern, not a per-ticket failure).
- On verifier fail: worktree is preserved (not deleted) for operator inspection. Branch is left in place. STATE.md gets a fail entry (written by the verifier in that session, see §STATE.md Concurrency).
- Cleanup: `argos sync` prunes worktrees whose branches have been merged and deleted.

**Independence detection (merge-dryrun analysis).**
- The criterion is a **dynamic dry-run merge** (ARG1-066, ratified in ESC-ARG1-021-independence-criterion; supersedes ARG1-021's strict file-set disjointness). Two tickets are checked by actually exercising the configured merge, not by predicting conflict from static metadata.
- Two tickets are **independent** iff: (1) neither lists the other in `depends_on:` frontmatter — the cheap first-pass exclusion; AND (2) `git merge --no-commit --no-ff` of one ticket branch (`argos/{ticket-id}`) onto the other, attempted in **both directions** in a throwaway staging worktree, completes with no conflicts. `depends_on:` is checked first and short-circuits before any merge.
- Two tickets are **dependent** if `depends_on:` declares a relationship, or if either merge direction conflicts. Dependent tickets are serialized in dispatch order.
- The dry-run exercises the *actual* merge configuration: the staging worktree inherits `.gitattributes` and shares the repo's `merge.*.driver` config, so STATE.md merges run the ARG1-052 custom driver and registration-style files (e.g. `argos/cli/__main__.py`) are judged by whether `ort` actually resolves them — no allowlist, no line-range heuristic. `--no-commit` means commit-time hooks (ARG1-032) never fire. Staging worktrees are created lazily, reused across a batch, and cleaned up on every exit path including crash (atexit + signal).
- **Degraded-but-correct fallback.** When a pair's branches do not exist yet (the plan-time case, before sessions have produced commits) or no git repo is reachable, the criterion degrades to strict `files_touched:` disjointness — the ARG1-021 behavior, conservative-correct per §Invariants.
- Heuristic floor: the orchestrator never dispatches more than `max_parallel` sessions concurrently (default 3, configurable in `argos/config.toml`). This caps blast radius even when independence analysis says more would be safe.
- Out of scope (caught downstream at the second-merging ticket's verifier or at merge time, not at dispatch): content-level conflicts on file-disjoint diffs — shared imports, type/behavioral contracts, invalidated invariants.

**Inputs.** Selected ticket batch from the orchestrator's queue read.

**Outputs.** Per-session result objects (pass/fail, files changed, escalations raised), written to `argos/specs/dispatch/{epic-id}/{ticket-id}.md`.

### Escalation Channel

**What it is.** The mechanism by which a session (or the orchestrator itself) signals "operator, decide this." The only paths into the operator's attention.

**v1.0 minimum surface.**
1. **CLI prompt** via `argos attend` — operator-driven drain of the escalation queue. Reads `argos/specs/escalations/*.md`, presents each as a prompt, captures the operator's decision into the ticket's Decisions section, and removes the escalation file.
2. **Optional webhook** — if `escalation.webhook_url` is set in `.argos/local.toml`, every new escalation file POSTs a JSON summary `{ticket_id, severity, summary, file_path}` to that URL. Fire-and-forget; no retry, no delivery guarantee.

**Out of scope for v1.0.** Discord bot, email, OS notifications, in-IDE popups, notification routing rules, on-call rotation. The webhook is the extension seam — anything fancier wires up to the webhook downstream of Argos.

**Escalation file schema.** Markdown with frontmatter:
```markdown
---
ticket_id: ARG-042
session_id: sess-2026-04-26T14:33:01Z-a1b2
severity: blocking            # blocking | advisory
raised_by: orchestrator       # orchestrator | planner | coder | watchdog | verifier
created: 2026-04-26T14:33:01Z
---

## Question
[One-paragraph statement of what the operator must decide.]

## Context
[What the agent already knows. File paths, line numbers, prior decisions consulted.]

## Options considered
- A: [option] — [tradeoff]
- B: [option] — [tradeoff]

## Why escalated
[Why this is genuine ambiguity, not a default the agent should have taken.]
```

**Authority.** Only `blocking` escalations halt the affected session. `advisory` escalations are noted but the session proceeds with the agent's best guess; the operator reviews after the fact via `argos attend`.

### Severity-Tiered Verifier

**What it is.** The v0.5 verifier extended with three severity levels for verification findings. Replaces the v0.5 binary pass/fail.

**Severity tiers.**
- **Critical.** Test suite fails, acceptance criterion explicitly listed in the ticket is not met, security or data-integrity invariant violated, build/typecheck broken.
- **Major.** Acceptance criterion partially met, lint/format broken, new TODO/FIXME introduced inside changed code, test coverage on changed lines decreased meaningfully (TODO: define threshold).
- **Minor.** Cosmetic — comment formatting, import ordering, unused-import warnings inside changed files only.

**Behavior per tier.**
- **Critical or Major:** verifier writes a fail entry to STATE.md, surfaces the finding to the orchestrator, which triggers **auto-fix retry (cap: 1)**. The orchestrator re-dispatches the ticket through planner → coder → watchdog → verifier within the same worktree. If the retry's verifier still reports critical or major, the ticket is marked failed and an escalation is written. No second retry.
- **Minor:** verifier writes a `verified-with-minors` entry to STATE.md listing the minor findings, allows the merge, and continues. Operator sees minors during the next `argos attend` or `argos status` review. No retry, no escalation.

**Verifier prompt changes (delta from v0.5).**
- v0.5 verifier asks: "Did the change meet the acceptance criteria? Output PASS or FAIL."
- v1.0 verifier asks: "For each finding, classify as critical / major / minor using the criteria below. Output a structured block: `findings: [{severity, description, file:line}], decision: pass|pass-with-minors|fail`."
- v1.0 verifier MUST quote real test stdout for any critical-tier finding (carries forward the v0.5 "no hallucinated test results" rule).
- v1.0 verifier MUST refuse to classify a missing test run as `pass`. Absence of evidence is critical.
- TODO: exact rubric for Major vs Minor on lint findings. Linters are noisy; we don't want every stray warning to trigger a retry.

**Authority boundary unchanged.** The verifier is still the only writer to STATE.md. Auto-fix retries do not let the coder write STATE.md; the second verifier pass writes the final entry.

### STATE.md (concurrent-writer redesign)

See §Contracts and §Invariants for the format. The component note: STATE.md is structurally the same file v0.5 used, but its body sections are now **append-mostly timestamped blocks** rather than free-form prose. This is the load-bearing change that lets N concurrent verifiers write without coordination.

### Config (project + local split)

See §Contracts. Two files: `argos/config.toml` (committed) and `.argos/local.toml` (gitignored). The orchestrator and all subagents read both; local overrides project on key collision.

## Contracts

### STATE.md format (append-mostly, concurrent-writer-safe)

STATE.md retains its v0.5 sections (Current focus, Queue, In progress, Done this cycle, Open decisions, Known drift). The v1.0 change is in the body of the **In progress**, **Done this cycle**, and **Known drift** sections: each entry is a self-contained timestamped block, never edited after write. Removal happens only at cycle close (a separate, single-writer operation).

**Block schema (canonical).**
```markdown
<!-- argos:entry id=2026-04-26T14:33:01Z-ARG-042 ticket=ARG-042 author=verifier session=sess-a1b2 -->
- **[2026-04-26T14:33:01Z] ARG-042 — verified** (session sess-a1b2, worktree `.argos/worktrees/ARG-042-3f9c/`)
  - Files changed: `src/foo.ts`, `src/foo.test.ts`
  - Findings: 0 critical, 0 major, 1 minor (`src/foo.ts:42` unused import in changed region)
  - Decision: pass-with-minors
<!-- /argos:entry -->
```

**Rules.**
- Each block is wrapped in `<!-- argos:entry ... -->` … `<!-- /argos:entry -->` HTML comments. The `id` attribute is `{ISO-timestamp}-{ticket-id}` and is globally unique (UTC timestamp + ticket ID collide only on the same-second double-write of the same ticket, which the orchestrator prevents structurally).
- Entries are **append-only** within a section. Never edit an existing entry. Corrections are new entries that reference the prior `id`.
- Section order inside STATE.md is fixed. Concurrent verifiers append to **In progress** when starting a ticket and to **Done this cycle** when finishing; they never reorder.
- **Merge conflict resolution.** Because every entry is a self-contained block and entries are only appended, the only possible git conflict is two verifiers appending to the same section at the same git-tree position. Resolution is concatenation in either order — both blocks are kept, neither is dropped. A trivial merge driver shipped with `argos init` (custom git merge driver registered for STATE.md) does this automatically. Manual fallback: `cat ours theirs` of the conflict region, dedupe by `id`.
- **Cycle close** (single-writer operation): the operator runs `argos sync --close-cycle`, which moves all `Done this cycle` blocks into a dated archive file under `argos/specs/cycles/{YYYY-MM-DD}.md` and clears the section. This is the only operation that *removes* blocks from STATE.md.

### Config split

**`argos/config.toml`** (committed to the repo, project-level, every contributor sees the same values).
```toml
[project]
name = "argos"
prefix = "ARG"

[orchestrator]
max_parallel = 3              # max concurrent sessions
independence_strategy = "file-overlap"   # file-overlap | depends-on | both
dry_plan_cache = true

[verifier]
auto_fix_retries = 1          # cap; applies to critical+major
minor_lint_rules = ["unused-imports", "import-order"]

[escalation]
require_attend_before_merge = true   # if true, blocking escalations must be drained before any merge
```

**`.argos/local.toml`** (gitignored, per-developer / per-machine).
```toml
[operator]
name = "ian"
email = "ianfrushon@gmail.com"

[escalation]
webhook_url = "https://hooks.example.com/argos"   # optional; empty/missing = no webhook

[harness]
claude_code_binary = "/usr/local/bin/claude"      # override if non-default
session_timeout_seconds = 1800

[telemetry]
opt_in = false
```

**Resolution.** Local overrides project on key collision. Unknown keys in either file warn but don't fail (forward-compatibility with future minor versions).

**`.gitignore`** must include `.argos/` (added by `argos init`). The `.argos/` directory also holds worktrees (`.argos/worktrees/`) and orchestrator scratch state — none of it should ever be committed.

### Orchestrator → Session

- **Spawn:** orchestrator invokes `argos run-session --ticket ARG-042 --worktree .argos/worktrees/ARG-042-3f9c/ --epic EPIC-007`. This launches a Claude Code session with the planner subagent loaded as the entry agent.
- **Result reporting:** session writes a result file at `.argos/dispatch/{epic-id}/{ticket-id}.json` on exit (pass/fail, findings, files changed). Orchestrator polls for completion via file existence + a sentinel `done` field.
- TODO: streaming progress vs. polled completion. Polling is simpler but adds latency to escalation surfacing.

### Session → STATE.md

- The verifier inside the session is the only writer.
- Verifier appends one block per phase transition (start, finish) into the appropriate section.
- Writes use `argos state-append --section "Done this cycle" --block <path>` rather than direct file edits, so the merge driver and block-id generator are enforced in one place.

### Escalation → Operator

- Session or orchestrator writes a file under `argos/specs/escalations/{ticket-id}-{timestamp}.md`.
- If a webhook is configured, the same writer POSTs the JSON summary.
- `argos attend` reads the directory in chronological order, presents each, captures the decision, and deletes the file on operator confirmation.

## Invariants

Things that must be true across all tickets. Violating one of these requires an ADR.

- **Specs are source of truth.** Every orchestrator decision must be reconstructable from files under `argos/specs/`. No orchestrator-only state outside the repo (worktree mechanics live under `.argos/`, but the *decisions* about what to dispatch are in `argos/specs/dispatch/`).
- **Verifier is the sole writer of STATE.md.** Even auto-fix retries do not let the coder or planner write STATE.md. The orchestrator does not write STATE.md. This is enforced by the agent allowed-tools config and by a pre-commit hook that rejects STATE.md changes from non-verifier authors (TODO: how is "verifier author" stamped on the change — git trailer? commit metadata?).
- **STATE.md is append-mostly.** No edits to existing blocks. Removal only at cycle close, only by the operator, only via `argos sync --close-cycle`.
- **Orchestrator cannot mutate code or product/architecture specs.** Allowed-tools and denied-paths enforce this.
- **One worktree per active ticket.** No two sessions share a worktree. No session writes outside its own worktree.
- **Independence analysis runs before every parallel dispatch.** The orchestrator never parallelizes on assumption; if independence analysis fails or is unavailable, the orchestrator falls back to serial dispatch (degraded but correct).
- **No hallucinated test results.** The verifier's critical-tier findings must quote real test stdout. Carried forward from v0.5 RULES.md.
- **No silent dependency adds.** Carried forward from v0.5 RULES.md. The watchdog inside each session enforces this per-ticket.
- **Auto-fix retry cap is 1.** Hard cap, not configurable beyond enabled/disabled. A second failure escalates.
- **`argos status` is the integrity oracle.** If `argos status` exits zero, the operator can trust that STATE.md, tickets, and git are mutually consistent. If it exits nonzero, the diagnosis on stdout names the specific drift.

## Technology choices

- **Language (CLI / orchestrator driver):** TODO. Candidates: Python (cross-platform, easy subprocess, ships with most dev machines), Rust (single binary, fast, harder to hack on), Go (single binary, easy concurrency, less common among target users), Bash (current v0.5 idiom, but doesn't scale to orchestrator complexity). Decision blocks the orchestrator and CLI implementation tickets — file an ADR before either is scaffolded.
- **Subagent harness:** Claude Code (primary). Subagent definitions remain markdown-with-frontmatter under `.claude/agents/` per Claude Code conventions.
- **Concurrency primitive:** OS-level processes (one Claude Code session per process). No shared in-process state. Coordination is via the file system under `argos/specs/` and `.argos/`.
- **Worktree management:** `git worktree` (native git). No external workspace tooling.
- **Config format:** TOML for both `argos/config.toml` and `.argos/local.toml`. Markdown remains the format for everything inside `argos/specs/`.
- **Webhook transport:** plain HTTPS POST with JSON body. No auth in v1.0 (TODO: signed payloads if anyone asks).
- **CI:** existing GitHub Actions (spec-lint, ticket↔issue sync). v1.0 adds an `argos status` job that must pass on every PR.

## What this architecture deliberately does not support

- **Shared multi-operator state.** Two operators dispatching against the same repo at the same time will produce STATE.md merge artifacts that are *resolvable* (concatenation) but not *coordinated* (one operator may not see the other's in-flight tickets). v1.0 ships for solo operators; team coordination is a v1.x or v2 problem.
- **Cross-repo orchestration.** The orchestrator runs against one repo. No multi-repo Epics, no cross-repo dispatch.
- **Hosted runtime.** No daemon, no server, no scheduled background jobs. The orchestrator runs only when the operator (or the operator's session) is running it.
- **Notification routing.** v1.0 has CLI + optional webhook. No rules engine, no per-ticket routing, no severity-based channel selection beyond the webhook payload's `severity` field.
- **Rollback of merged work.** If the orchestrator merges a verified ticket and a *later* ticket reveals the merge was wrong, recovery is manual (`git revert` by the operator). The orchestrator does not auto-revert.
- **Real-time streaming UI.** No web dashboard, no TUI live view. Inspection is via `argos status`, `argos attend`, and reading files under `argos/specs/`.

## Known drift

This section should be near-empty at any given moment. Entries here are bugs in the documentation, tickets to file, or ADRs to write.

- _none — v1.0 has not been implemented yet; nothing can drift from a doc that pre-dates the code._
