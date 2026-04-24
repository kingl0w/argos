---
description: Re-plan when reality diverges from the ticket's plan mid-run
argument-hint: "[ticket-id] [reason]"
---

Re-plan when the coder hit a plan/reality mismatch, or when watchdog flagged CHAOS_BLOCKED.

Steps:
1. Read ticket file. Look for ## Plan and optionally ## Plan drift sections.
2. Read actual state of files the plan touches. Capture divergence.
3. Invoke planner subagent with original plan + drift notes + directive to produce "## Plan (revised <date>)". Do not delete the original plan — history matters.
4. If drift reveals architectural mismatch, update argos/specs/ARCHITECTURE.md and add entry to STATE.md "Known drift".
5. Show revised plan, ask whether to re-run /next.

Never silently overwrite the original plan. Never steer more than twice on one ticket — if plan keeps drifting, split the ticket.
