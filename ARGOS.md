# Argos — methodology

This document explains *why* the scaffold is shaped the way it is. If you're tempted to collapse the loop, skip an ADR, or let the coder touch `STATE.md`, read the relevant section first.

## Why three (four) subagents instead of one

A single "do the ticket" agent is simpler to invoke but worse at every sub-task:

- It has a bloated tool allowlist, so it reaches for the wrong tool under pressure (grep when it should plan, write when it should read).
- Its context mixes spec prose, source code, and test output, and the one that got into context most recently dominates its decisions. Plans drift mid-execution.
- There is no checkpoint where someone with no stake in the code-written-so-far looks at the diff.

Splitting the work forces an explicit interface between phases:

- **planner** reads specs, writes a plan. It does not see diffs. It cannot be seduced by "while I'm in here…".
- **coder** reads the plan and the code. It does not see `.specs/` except the one ticket; it does not write `STATE.md`. Its job is "make the plan true."
- **watchdog** reads the plan and the diff — nothing else. It is cheap, narrow, and adversarial. It exists because a coder will happily ship a diff that doesn't match the plan if nobody checks.
- **verifier** runs tests and acceptance criteria in a fresh subagent context, so "tests pass" is not a claim the coder gets to make about itself.

The handoff cost is real (more tokens, slower). The correctness win is larger than the cost, in practice, because the watchdog catches roughly the class of errors that would otherwise silently ship.

## Why STATE.md is load-bearing

`STATE.md` is the one file every agent reads first and the verifier writes last. It is not documentation — it's the project's short-term memory. Without it:

- The planner re-plans the same ticket differently every run, because it has no notion of "we already decided X."
- The human has no place to write "I'm pausing ticket Q-012 until the auth refactor lands" that the agents will actually see.
- A failed ticket produces no residue — next run, the loop starts from scratch and often picks the same wrong approach.

`STATE.md` is deliberately short. If it grows past a screen, that's a signal to move standing facts into `ARCHITECTURE.md` or an ADR. The Known drift section is the most important — it's where reality gets to contradict the plan out loud.

## Why ADRs instead of TODOs

TODOs rot. They accumulate in code where nobody planning the next ticket will see them; they get grep-audited once a quarter and deleted out of shame. Architecture Decision Records invert the relationship:

- A decision gets a number, a date, and a fixed file. It does not move.
- Options considered are written down, so next year's revisit doesn't relitigate the rejected ones from scratch.
- The Consequences section forces you to say what will go wrong, which is the part a TODO never captures.

In Argos, the planner is instructed to cite relevant ADRs in its Plan section ("per ADR-004, we write to Postgres, not SQLite"). If a ticket requires a decision that isn't in an ADR yet, the planner halts and the human runs `/ask`.

## Why /steer is manual, not automatic

The temptation is to let the loop retry intelligently — "planner, watchdog rejected your plan, try again." In practice this produces two failure modes:

1. The planner learns to write plans that survive the watchdog but don't match reality. You get clean loops and broken code.
2. The human loses visibility into *why* the loop is stuck, because the retry masks the disagreement.

`/steer` is manual because the mismatch between plan and reality is usually information the human needs to know, not friction to automate away. The cost of one human interruption per stuck ticket is much lower than the cost of a successfully-looping system that ships the wrong thing.

The one exception: a `CHAOS_BLOCKED` from the watchdog on a *formatting* or *trivial* mismatch (line endings, import ordering) can auto-retry once. Anything structural halts.

## Why GitHub Issues over Linear for solo work

Linear is better for teams: keyboard-first, typed fields, a real state machine. For a solo operator running Argos, it has two problems:

- It's a second source of truth. The ticket in `.specs/tickets/` and the Linear issue drift; resolving drift becomes its own chore.
- The agents can't see it without an MCP connector, and the connector adds latency + auth surface for no benefit when the ticket is already on disk.

GitHub Issues are strictly a *view* of the on-disk ticket in Argos. A CI job renders the markdown ticket into an issue body; closing the issue closes the ticket (via a commit hook that flips Status to Done). If you grow into a team, swap the view layer — the tickets stay put.

This is the rare "pick the worse tool because it composes better" call. Teams of >3 should reconsider.

## Predicted weak spots for v0.1

These are the failure modes to watch for in the first month of real use. Each has a countermeasure but no fix yet.

- **Planner under-specs tests.** The planner will write "add tests for X" without naming the cases, and the coder will write the thinnest test that passes. Countermeasure: the ticket template's Acceptance criteria section must list test cases, not just behaviors. The planner should refine these, not invent them.
- **Coder over-refactors fresh repos.** On a new or near-empty codebase, the coder will rewrite structure it has no mandate to change (moving files, renaming modules, introducing abstractions). Countermeasure: watchdog's allowed-diff rules should include "no file renames unless plan explicitly calls for them." Also, seed the repo with at least one ticket's worth of real code before running the full loop.
- **Verifier claims tests pass without running them.** The verifier's prompt tells it to run the test command and paste the output. Nothing currently forces it to actually do so — it can hallucinate "all 14 tests passed" from pattern matching. Countermeasure: the verifier subagent should be restricted to tools {Bash, Read, Edit} with an explicit instruction that the Verification section must quote real stdout, and CI should re-run the same command on PR open. Treat any verifier pass that CI contradicts as a P0 bug in Argos itself.

## What to measure

If you're running Argos seriously, track these monthly. They are the metrics that tell you whether the scaffold is earning its complexity.

- **Tickets passing verifier on first try.** Target: >60%. Below that, the planner is underspecifying or the acceptance criteria are too loose.
- **ADR filings per month.** Target: 2–6. Zero means you're either making decisions implicitly or not making any. Double digits means you're using ADRs as a scratch pad — tighten the threshold.
- **/steer frequency.** Target: <1 per ticket on average. Higher means the planner isn't reading `STATE.md` carefully (or `STATE.md` is stale). Consistently zero means the watchdog is asleep — spot-check some diffs by hand.

A secondary metric: **time from `/new-ticket` to merged PR**. If it's going up over time, either tickets are getting bigger (fine, intentional) or the loop is accreting friction (investigate). Plot both and you'll know.
