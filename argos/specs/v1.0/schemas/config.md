---
name: argos-v1.0-config-schema
description: Canonical schema for Argos v1.0 config split (`argos/config.toml` + `.argos/local.toml`)
status: draft
version: 1.0
---

# Config schema (v1.0)

**Created:** 2026-04-26
**Owner:** loader at `argos/cli/config.py` (sole reader); operators write the
TOML files directly.

This document is the canonical contract for the two TOML files that make up
Argos's runtime configuration. It lifts the inline split from
`ARCHITECTURE.md` §Contracts/Config split into a versioned schema document
so future changes go through the v1.0 → v1.x → v2.0 schema-evolution
process rather than ad-hoc edits to ARCHITECTURE.md.

The loader at `argos/cli/config.py` reads both files (project-level first,
then per-developer local overrides) and presents a single dotted-key view
via `Config.get("section.key")`. Unknown keys produce a stderr warning but
do not fail the load. Type validation lives behind `Config.validate()`,
exposed via `argos config validate`.

The machine-readable mirror of the tables below lives at
`argos/cli/_config_schema.py` as `KNOWN_KEYS`. The `SchemaDocConsistencyTests`
class in `argos/cli/tests/test_config.py` parses the tables in this file and
asserts the key set matches `_config_schema.KNOWN_KEYS`. Drift fails CI.

## File 1 — `argos/config.toml` (project-level, committed)

These keys define behaviour that applies to every developer working in the
repository. They are committed alongside the source. The shipped default
template is `argos/config.toml.template`; `argos init` (ARG1-002) copies it
to `argos/config.toml`. Until ARG1-002 lands, the loader falls back to the
template directly.

| Key                                      | Type | Default                  | Required | Notes |
|------------------------------------------|------|--------------------------|----------|-------|
| `project.name`                           | str  | `"argos"`                | yes      | Display name; appears in CLI banners. |
| `project.prefix`                         | str  | `"ARG1"`                 | yes      | Ticket-ID prefix (matches `[A-Z][A-Z0-9]*` per state-block schema). |
| `orchestrator.max_parallel`              | int  | `3`                      | yes      | Max concurrent sessions the orchestrator will spawn. |
| `orchestrator.independence_strategy`     | str  | `"plan-declared"`        | yes      | How parallelizable-with declarations are interpreted (currently only `plan-declared`). |
| `orchestrator.dry_plan_cache`            | bool | `true`                   | no       | If true, planner output is cached on disk between dry runs. |
| `verifier.auto_fix_retries`              | int  | `0`                      | yes      | Number of automatic retry passes the verifier may attempt before failing. |
| `escalation.require_attend_before_merge` | bool | `true`                   | yes      | If true, open escalations block merges; operator must drain via `argos attend`. |

## File 2 — `.argos/local.toml` (per-developer, gitignored)

These keys carry per-developer state — operator identity, secrets,
machine-specific paths — that must not be checked into the repository.
The `.argos/` directory is in `.gitignore`. The shipped sample is
`.argos/local.toml.template`; `argos init` (ARG1-002) copies it to
`.argos/local.toml` for new clones.

| Key                                  | Type | Default                          | Required | Notes |
|--------------------------------------|------|----------------------------------|----------|-------|
| `operator.name`                      | str  | `""`                             | no       | Display name used in escalation `raised_by` annotations. |
| `operator.email`                     | str  | `""`                             | no       | Optional contact for escalation routing. |
| `escalation.webhook_url`             | str  | `""`                             | no       | Optional webhook fired by `argos attend` on new blocking escalations. |
| `harness.claude_code_binary`         | str  | `"claude"`                       | no       | Path to the Claude Code binary the orchestrator invokes. |
| `harness.session_timeout_seconds`    | int  | `3600`                           | no       | Per-session wall-clock timeout. |
| `telemetry.opt_in`                   | bool | `false`                          | no       | If true, anonymized usage counts are emitted (no telemetry endpoint exists yet). |

## Override semantics

When the same dotted key appears in both files, the value from
`.argos/local.toml` wins. The loader emits no warning on legitimate
override (it is the documented mechanism). Unknown keys (in either file)
emit a single stderr line of the form:

```
unknown config key: <dotted.key> (in <file>)
```

The loader returns successfully even when unknown keys are present. Type
validation runs only against keys present in `KNOWN_KEYS`; an unknown key
cannot trigger a `TypeMismatchError`.

## Documented gaps

- `verifier.minor_lint_rules` — the architecture lists this as an array
  of strings (e.g. `["unused-imports", "import-order"]`). Array support
  in the in-house TOML mini-parser is deferred to **ARG1-013**; the
  template ships the line commented out so the architectural intent is
  preserved. Setting an array value today raises `ConfigParseError` from
  the in-house parser and is silently consumed by `tomllib` on 3.11+ but
  rejected by the loader as an unknown-key warning (the schema has no
  array type).

## TOML surface supported by the in-house mini-parser

ADR-001 forbids third-party deps and pins the floor to Python 3.9 (no
`tomllib` until 3.11). The in-house parser supports exactly:

- Section headers `[section]` and `[section.subsection]` (one nesting
  level).
- Flat `key = value` pairs where value is a quoted string (`"..."`),
  integer (`-?\d+`), or boolean (`true` / `false`).
- Comments (`#` to end of line) and blank lines.

It rejects, with `ConfigParseError(file, line, reason)`:

- Array literals (`[...]`).
- Inline tables (`{...}`).
- Multi-line strings (`"""..."""`).
- Datetimes.
- Dotted keys outside section headers.

On Python 3.11+ the loader uses `tomllib` directly; both parsers must
yield the same `{section: {key: typed_value}}` shape for the supported
surface. The `ParserTests` class in
`argos/cli/tests/test_config.py` round-trips fixtures through both
parsers (skipping `tomllib` cases on 3.9/3.10 via
`unittest.skipIf(sys.version_info < (3, 11), ...)`).

## Schema evolution

Changes to this schema are not ad-hoc edits. They go through:

1. An ADR proposing the change, written under `argos/specs/decisions/`.
2. A bump to the `version:` frontmatter field of this file (semver-style:
   additive change → minor; breaking change → major).
3. Coordinated update to `argos/cli/_config_schema.py` and the two
   templates (`argos/config.toml.template`, `.argos/local.toml.template`).

The `SchemaDocConsistencyTests` unit test enforces that the table
content here and the `KNOWN_KEYS` dict in `_config_schema.py` agree on
the key set. Editors who change one must change the other.
