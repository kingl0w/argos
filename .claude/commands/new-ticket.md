---
description: Scaffold a new ticket and add it to the queue
argument-hint: "<description>"
---

Scaffold a ticket from a description.

Steps:
1. Read STATE.md to find prefix and highest ticket number. Compute next ID.
2. Create argos/specs/tickets/<PREFIX>-NNN-<kebab-slug>.md with sections: title header, **Status:** Queued, **Created:** <date>, **Priority:** (ask user P0/P1/P2), Intent, Context, Non-goals, Acceptance criteria (draft, rough — planner will refine).
3. Append to ## Queue in STATE.md in priority order.
4. If gh CLI configured, offer to mirror to GitHub Issue (gh issue create --title ... --body-file ...).
5. Ask user whether to run /next on this ticket now.

Never plan the ticket here — planner subagent does that inside /next. Don't over-specify acceptance criteria.
