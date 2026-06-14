# ARG1-074 — init CLI surface disagrees with the documented "argos init your-project" mental model

## Intent

`argos init <project>` (a positional project name) is rejected — `init` takes
`--path` (default: cwd), not a positional. The README/tagline mental model
("argos init your-project") disagrees with the actual CLI surface. Reconcile
them: either accept an optional positional project name as an alias for
`--name`/`--path`, OR fix the docs/tagline to match the `--path`/cwd reality.
Pick one and make the surface and the docs agree.

## Context

Found during the jobhunter dogfood: `argos init jobhunter` errored with
`unrecognized arguments: jobhunter`, while `cd jobhunter && argos init` (relying
on the cwd default for `--path`) worked. The tagline/README present init as
taking a project name positionally, so the first thing a new operator types
fails. This is a first-run papercut on the most prominent command in the docs.

## Acceptance criteria

- [ ] The exact invocation shown in the README runs successfully against a fresh repo (no "unrecognized arguments" error).
- [ ] If a positional is added: `argos init <name>` and `argos init --path <dir>` both succeed and produce the same scaffold, and both are covered by tests.
- [ ] If the docs-only path is chosen: every README/tagline example matches the real flag surface (`--path`, cwd default), and no example shows an unsupported positional.
- [ ] The chosen direction is internally consistent — argparse usage/help text and the docs describe the same surface.

## Touches

- `argos/cli/commands/init.py` (if adding a positional alias) and/or
- README + tagline docs (if reconciling docs to the `--path`/cwd reality)

## Depends on

- (none)
