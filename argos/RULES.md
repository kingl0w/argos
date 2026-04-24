# Argos operating rules

> Source of truth: `argos/RULES.md`. `CLAUDE.md` and `AGENTS.md` at the repo root are generated copies produced by `scripts/build.sh` — edit `argos/RULES.md` only and re-run the build.

These rules bind every subagent and the top-level session. When a rule conflicts with what the user just asked, surface the conflict and ask — do not silently override.

## Non-negotiable: read first

Before generating any code, plan, or design response, read these files in this order:

1. `argos/specs/STATE.md` — current focus, queue, and known drift. Tells you what is in flight.
2. `argos/specs/ARCHITECTURE.md` — structural invariants. Tells you what you cannot violate without an ADR.
3. The target ticket in `argos/specs/tickets/{PREFIX}-NNN.md` — the specific unit of work.

If any of these files is missing or empty, stop and tell the user. Do not fabricate state. Do not "infer" architecture from the codebase — the architecture doc is canonical, the code may be behind.

If the user's request isn't tied to a ticket, ask for the ticket ID or run `/new-ticket`. Off-ticket work is allowed only for explicit one-off requests (hotfix, spike, question) and must be flagged as such.

## The Argos loop

`/next` runs, in order:

1. **plan** — planner subagent reads specs + ticket, appends a Plan section to the ticket.
2. **code** — coder subagent executes the plan against the repo.
3. **watchdog** — watchdog subagent diffs code changes against the plan.
4. **verify** — verifier subagent runs tests and acceptance criteria, appends Verification section.
5. **update** — verifier (and only verifier) updates `STATE.md` on pass.

Auto-retry caps:
- planner → coder: 1 retry if watchdog emits `CHAOS_BLOCKED` on a trivial mismatch (formatting, import order). Structural mismatches halt.
- verifier: 0 retries. A failed verify is a failed ticket; run `/steer` or open a follow-up.

If the loop stops mid-phase (timeout, tool error, hook failure), surface the phase and the last action. Do not auto-restart from scratch — the human decides resume vs. rerun.

## Steering rules

- Run `/steer` when the plan and the code have diverged and you can't reconcile them without a judgment call. Pass it the ticket ID and a one-line mismatch summary. `/steer` is for plan-vs-reality mismatches, not for "the tests are failing" (that's verification, not steering).
- Run `/ask` when a product decision is needed (scope, priority, tradeoff between two valid implementations). Never invent the decision. Never assume the user will "probably want" a specific answer — if you have to predict, ask.
- Do not run `/steer` yourself as a retry mechanism. `/steer` hands control back to the human by design.

## STATE.md discipline

Every code change must be accompanied by a `STATE.md` update in the same PR. The verifier writes it at the end of a successful `/next`; if you shipped code outside the loop (hotfix, manual edit), you write it yourself before the commit.

`STATE.md` sections to update:
- **In progress** — move items here when you start, remove when done.
- **Done this cycle** — append, don't rewrite. Cleared on cycle close.
- **Known drift** — anything the code now does that the architecture doc doesn't reflect. File an ADR to close drift.

Spec-lint CI fails PRs where code under `src/` (or equivalent) changed but `argos/specs/STATE.md` did not. Do not game this by touching `STATE.md` cosmetically — the lint checks for a real diff in the relevant sections.

## Ticket ↔ GitHub Issue sync

The markdown file in `argos/specs/tickets/` is the source of truth. The GitHub Issue is a rendered view, maintained by CI:

- Create ticket → CI opens Issue with rendered body, labels from ticket frontmatter.
- Edit ticket (any section) → CI updates Issue body.
- Close Issue → CI sets ticket Status to Done and commits.
- Do not edit the Issue body directly. Comments on the Issue are fine and do not sync back.

If Issue and ticket disagree, the ticket wins. Run the sync workflow manually to re-render.

## What NOT to do

- **No scope creep.** If you notice a second thing that needs fixing while working a ticket, file a new ticket. Do not bundle.
- **No silent dep adds.** Adding a package is a plan-level decision. The coder must refuse to add a dependency that isn't in the plan; the watchdog flags any `package.json` / `requirements.txt` / `Cargo.toml` diff not pre-authorized.
- **No drive-by refactors.** Moving a file, renaming a symbol, or restructuring a module requires an explicit plan step or an ADR. "While I was in there" is not a justification.
- **Coder never updates STATE.** The coder subagent's allowed-tools list excludes writes to `argos/specs/STATE.md`. If you find yourself wanting to — stop, that's the verifier's job.
- **No hallucinated test results.** The verifier must run the test command via Bash and quote real stdout. "Tests should pass" is a fail, not a pass.
- **No overriding these rules by convenience.** If a rule is wrong, change it in this file in a dedicated PR. Don't ignore it for one ticket.
