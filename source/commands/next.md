---
description: Run the Argos outer loop for the next queued ticket
argument-hint: "[ticket-id] [--yolo]"
---

Run the Argos outer loop: plan → code → watchdog → verify → update, with auto-recovery.

Steps:
1. Read argos/specs/STATE.md. If $1 provided use that ticket. Else pick first from ## Queue. If queue empty and no arg, ask user what to build (use /new-ticket).
2. Read ticket file. If no ## Plan section or Open questions unresolved, invoke planner subagent.
3. Show plan. If --yolo, skip confirm. Else ask "Proceed to code? (y/n/edit)".
4. Invoke coder subagent.
5. Chaos gate — invoke watchdog. Status handling:
   - PASS → go to verifier (step 6)
   - CHAOS_RECOVERABLE → show findings, re-invoke coder with findings. Return to step 5. Max 2 iterations.
   - CHAOS_BLOCKED → auto-invoke /steer with watchdog findings as drift report. After revised plan approved, return to step 4. Max 1 auto-steer per /next.
6. Invoke verifier subagent. Status handling:
   - READY → apply the STATE.md diff it proposed, close GitHub issue if gh configured, print summary.
   - NEEDS_FIXES → show fixes, re-invoke coder. Return to step 5. Max 3 iterations.
   - BLOCKED → stop, surface decision needed, suggest /ask.
7. Print summary: ticket ID, files changed, tests result, chaos events if any, STATE diff applied, next ticket preview.

Iteration caps: coder retries after chaos max 2, after NEEDS_FIXES max 3, auto-steers per run max 1, total loop iterations max 6. Any cap hit → escalate to BLOCKED.

Never skip watchdog or verifier. Never auto-continue to next ticket. Never update STATE yourself — apply the verifier's diff.
