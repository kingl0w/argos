# ARG1-075 — orchestrate default spec paths assume argos's own v1.0/ tree

## Intent

`argos orchestrate` defaults `--state-file` to `argos/specs/v1.0/STATE.md` and
`--ticket-dir` to `argos/specs/v1.0/tickets`. But `argos init` scaffolds a
foreign repo to `argos/specs/STATE.md` and `argos/specs/tickets/` (no `v1.0/`
segment). So on every non-argos repo, a bare `orchestrate` reads nonexistent
paths and finds no queue — the operator must pass both overrides by hand. The
defaults leak argos's own internal layout. Make argos's own repo and a
scaffolded repo both work with bare `orchestrate`.

## Context

Found in the jobhunter dogfood: `orchestrate` only worked when invoked with
explicit `--state-file argos/specs/STATE.md --ticket-dir argos/specs/tickets`.
argos versions its own specs under `v1.0/`; scaffolded foreign repos do not.
The default-resolution logic was written from inside argos's own tree and never
reconciled with what `init` actually lays down elsewhere.

## Acceptance criteria

- [ ] On a freshly `init`-ed (non-argos) repo, `argos orchestrate --dry-run` with NO path flags reads the scaffolded queue correctly (finds `argos/specs/STATE.md` and `argos/specs/tickets/`).
- [ ] In argos's own repo, `argos orchestrate --dry-run` with NO path flags still resolves to the `v1.0/` tree it uses today (no regression).
- [ ] A test covers both layouts resolving correctly under bare `orchestrate` (scaffolded layout and argos's own layout).
- [ ] The fix approach is recorded (derive defaults from where `init` scaffolds, OR read the paths from `argos/config.toml`, OR have `init` scaffold to the `v1.0/` path) and applied consistently across the CLI.

## Touches

- `argos/cli/commands/orchestrate.py` (default path resolution)
- possibly `argos/cli/commands/init.py` (scaffold layout) and/or `argos/config.toml` + its loader (if defaults are read from config)

## Depends on

- (none)
