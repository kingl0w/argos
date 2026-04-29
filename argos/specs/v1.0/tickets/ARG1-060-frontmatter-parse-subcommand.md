# ARG1-060 — `argos frontmatter-parse` subcommand (stdlib YAML-subset parser)

**Status:** Queued
**Created:** 2026-04-29
**Priority:** P0
**Epic:** 1 (CLI scaffold) — extends ARG1-001's internal-subcommand surface

## Intent

Implement the `argos frontmatter-parse` internal subcommand mandated by ADR-002. Stdlib-only YAML-subset parser at `argos/cli/frontmatter_parser.py`, registered in `argos/cli/__main__.py` alongside `state-parse` / `state-append` / `verifier-parse` / `escalation-validate`. Parses the YAML subset pinned in ADR-002 §3 (block sequences of strings, flat scalars, comments, double/single-quoted scalars, no flow style, no anchors/aliases/tags, no multiline scalars, no nested mappings beyond depth 1, UTF-8 only) and emits JSON to stdout. Rejects everything outside the subset with the rejection contract from ADR-002 §4.

## Context

ARG1-057 surfaced a foot-gun: ARG1-010 AC#3 used `python -c "import yaml; yaml.safe_load(...)"` and passed only because the AC harness picked up a system `pyyaml`. The project venv has no `pyyaml`; downstream contributors and other harnesses (Cursor / Codex / Gemini) reproduce the same failure. ADR-002 ratified Option A — stdlib-only AC tooling, with frontmatter validation routed through this new subcommand. This ticket implements the subcommand. ARG1-059 retrofits existing ACs to invoke it.

## Non-goals

- No retrofit of ARG1-010 / ARG1-012 / other ticket ACs (ARG1-059).
- No per-document key schema validation (the parser is a parser, not a validator-of-keys; key schemas live in `argos/specs/v1.0/schemas/`).
- No support for YAML features outside the ADR-002 §3 subset. Adding any feature requires an ADR amendment per ADR-002 §5.
- No new dependencies. Stdlib only per ADR-001 §Decision item 2 and ADR-002 §1.
- No `argos frontmatter-validate` variant (parse + JSON output is sufficient; AC text greps the JSON).

## Acceptance criteria

- [ ] `test -f argos/cli/frontmatter_parser.py` exits 0; module is stdlib-only (`grep -E '^import |^from ' argos/cli/frontmatter_parser.py` shows only stdlib modules — `re`, `sys`, `json`, `pathlib`, `argparse`, `dataclasses`, `typing`, `enum` permitted; anything else fails AC).
- [ ] `python3 -m argos.cli frontmatter-parse argos/specs/v1.0/agents/orchestrator.md` exits 0; stdout is valid JSON; the JSON object contains keys `name`, `description`, `allowed_tools`, `denied_paths`; `allowed_tools` is a JSON array; `denied_paths` is a JSON array.
- [ ] `python3 -m argos.cli frontmatter-parse argos/specs/v1.0/agents/verifier.md` exits 0; stdout JSON contains keys `name`, `description`, `tools`.
- [ ] Happy path with quoted scalar: a fixture frontmatter containing `denied_paths:\n  - "**/*.{ts,py}"` parses; the array element is the string `**/*.{ts,py}` (verbatim, including braces).
- [ ] Happy path with comments: a fixture with `# leading comment` lines, blank lines, and `key: value  # trailing comment` lines parses; the JSON output omits the comments and contains the key with value `value`.
- [ ] Rejection — flow-style sequence: `python3 -m argos.cli frontmatter-parse <fixture-with-`tools: [Read, Bash]`>` exits 2; stderr matches `^frontmatter-parse: line [0-9]+: flow-style sequence not supported$`.
- [ ] Rejection — flow-style mapping: a fixture with `key: {a: b}` exits 2; stderr line cites `flow-style mapping not supported`.
- [ ] Rejection — multiline scalar (block scalar `|`): a fixture with `description: |\n  line1\n  line2` exits 2; stderr cites `multiline scalar indicator '|' not supported`.
- [ ] Rejection — nested mapping depth >1: a fixture with `nested:\n  key:\n    deeper: x` exits 2; stderr cites `nested mapping at depth 2 not supported`.
- [ ] Rejection — anchor: a fixture with `&anchor` syntax exits 2; stderr cites `anchor` and the offending line number.
- [ ] Rejection — alias: a fixture with `*alias` syntax exits 2; stderr cites `alias`.
- [ ] Rejection — tag: a fixture with `!!str` or `!custom` syntax exits 2; stderr cites `tag`.
- [ ] Rejection — non-UTF-8: a fixture with bytes `\xff\xfe` at the start exits 2; stderr cites `input not valid UTF-8`.
- [ ] File-not-found: `python3 -m argos.cli frontmatter-parse /nonexistent/path` exits 1; stderr names the path.
- [ ] Subcommand registration: `python3 -m argos.cli --help` lists `frontmatter-parse` under internal subcommands; `python3 -m argos.cli frontmatter-parse --help` exits 0 with usage on stdout.
- [ ] Test suite: `python3 -m unittest argos.cli.tests.test_frontmatter_parser -v` passes; ≥ one test per AC above.
- [ ] Integration regression: existing `python3 -m unittest argos.cli.tests.test_version argos.cli.tests.test_verifier_parser argos.cli.tests.test_escalation_validator argos.cli.tests.test_state_append argos.cli.tests.test_config -v` continues to pass with no changes.

## Depends on

- ADR-002 (ac-harness-portability) — pins the subset grammar this ticket implements
- ARG1-001 (CLI scaffold) — provides the `argos/cli/__main__.py` dispatch surface this ticket extends

## Touches

- `argos/cli/frontmatter_parser.py` (new)
- `argos/cli/commands/frontmatter_parse.py` (new — optional thin shim if the planner prefers the commands/ layout used by `state_parse` and `state_append`; otherwise wire directly through `__main__.py` like `verifier_parser`/`escalation_validator`)
- `argos/cli/__main__.py` (modify — add `frontmatter-parse` to `INTERNAL_SUBCOMMANDS`, dispatch branch, help text)
- `argos/cli/tests/test_frontmatter_parser.py` (new)
- `argos/cli/tests/fixtures/frontmatter/` (new — fixture files for each rejection AC; one file per case, named for the case)

## Parallelizable with

_none for the duration of Layer 2 fan-out — Layer 2 tickets ARG1-020 / ARG1-031 / ARG1-041 block on this ticket landing. ARG1-059 is sequenced after this ticket._

## Out of scope

- Modifying ARG1-010 / ARG1-012 ACs (ARG1-059 owns that).
- Modifying any shipped agent definition file or any frontmatter the parser will consume. If existing frontmatter does not parse cleanly (it should, but the AC verifier should confirm against orchestrator.md and verifier.md specifically), the fix is to adjust the frontmatter to fit the parser per ADR-002 §5 — file a separate ticket for the adjustment, do not extend the parser.
- A `frontmatter-validate <path> --require K1,K2[,...]` mode. Out of scope; AC text greps the parser's JSON output for required keys via stdlib `json.tool` or shell. If a future ticket needs the require-keys ergonomic, file it as a follow-up.
- ADR amendment. ADR-002 §3 is the contract; this ticket implements it as written.
