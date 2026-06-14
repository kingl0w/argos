# ARG1-077 — state-append leaves an orphan .lock file it never cleans up

## Intent

`argos state-append` acquires a sidecar lock at `{state_file}.lock` (ARG1-051)
and leaves the now-empty 0-byte `STATE.md.lock` behind on disk. Sessions have to
remove it by hand. state-append should clean up after itself — remove the lock
file (or otherwise stop leaving a tracked artifact) once the append completes.

## Context

Found in the jobhunter dogfood: a stray 0-byte `STATE.md.lock` is left in the
spec/ticket dir after each append. ARG1-051 §Implementation notes anticipated
this — it calls the leftover "harmless," notes the lock "self-cleans logically"
(released on FD close, but the file persists), and leaves a TODO to "add `.lock`
to `.gitignore` in a follow-up ticket; out of scope here." No such follow-up was
ever filed. This ticket is that follow-up, scoped to the operator-visible
artifact, not the locking mechanism itself.

## Acceptance criteria

- [ ] After a successful `argos state-append`, no `{state_file}.lock` file remains in the working tree (cleaned up by state-append), OR `.lock` is gitignored AND removed so it is neither tracked nor operator-visible — whichever is chosen, the dogfood symptom (a stray 0-byte lock to delete by hand) is gone.
- [ ] Concurrent-append safety from ARG1-051 is preserved (the cleanup does not reintroduce a race or break the `fcntl.flock` serialization).
- [ ] A test asserts the lock file is absent after an append completes.

## Touches

- `argos/cli/state_append.py` (lock acquire/release + cleanup) and possibly `.gitignore`

## Depends on

- ARG1-051 (state-append helper — owns the lock-file behavior this cleans up)
