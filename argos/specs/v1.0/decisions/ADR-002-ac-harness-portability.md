# ADR-002 — AC harness portability (stdlib-only frontmatter validation)

**Date:** 2026-04-29
**Status:** Accepted
**Deciders:** kingl0w

## Context

ADR-001 ratified Python ≥3.9 stdlib-only as the v1.0 runtime constraint, with the explicit dev-extras escape hatch for `pytest` (under `[project.optional-dependencies] dev`). ADR-001 §Decision item 2 reads, verbatim: *"Stdlib-only at runtime. Zero entries in `[project.dependencies]` … Test-only dev dependencies (`pytest`) live in `[project.optional-dependencies] dev` and are not part of the install critical path."* The mandate covers runtime; AC verification commands were not separately addressed.

That gap surfaced as escalation ARG1-057 (`argos/specs/escalations/ARG1-057-2026-04-29T19-30-00Z.md`). ARG1-010's AC#3 and ARG1-012's AC#1 used `python -c "import yaml; yaml.safe_load(...)"` to validate agent-definition and dispatch-log frontmatter. `pyyaml` is third-party, not in `pyproject.toml`. ARG1-010 AC#3 passed locally only because the AC harness reached for `/usr/bin/python3` (which had system `pyyaml` 6.0.1) rather than the project venv (which did not). ARG1-030 deliberately rejected `pyyaml` in its plan §Risks line 120 and shipped a hand-rolled stdlib subset parser; ARG1-040's `escalation_validator.py` made the same call ("No PyYAML — flat scalar key:value only."). Project evidence consistently rejected `pyyaml` in shipped code, but two ticket ACs silently re-introduced it.

The constraints that bear on this decision:

- **Distribution intent.** v1.0 is intended for distribution to other users via the (still-deferred) packaging channel from ARG1-001 / PRD §Distribution. That distribution property requires AC verification to work on any machine where `argos` works, without contributors having to bootstrap `[dev]` extras. A downstream user running `argos init` and `argos status` against a fresh checkout must be able to satisfy and verify AC text without `pip install pyyaml`.
- **The pre-existing foot-gun.** ARG1-010's AC#3 *appeared* to pass under the harness's accidental choice of system interpreter. The same AC under the project venv exits with `ModuleNotFoundError`. A solution that depends on `pyyaml` being available somewhere on the machine reproduces the foot-gun on every downstream contributor's machine. The only robust fix is to make the parser part of the tool.
- **Multi-harness portability.** PRD §Target user covers Cursor / Codex / Gemini contributors as secondary harnesses. Those harnesses may not bootstrap `[project.optional-dependencies] dev` before running AC checks. A decision that puts validation behind a dev extra silently degrades the secondary-harness experience.
- **Project pattern coherence.** Every shipped reference parser in `argos/cli/` (`state_parser.py`, `verifier_parser.py`, `escalation_validator.py`) is stdlib-only. ARG1-040's plan documents the choice explicitly. A new third-party-using parser would diverge from established practice; a new stdlib subset parser continues it.
- **Scope of this ADR.** AC tooling and frontmatter validation only. ADR-002 does NOT amend ADR-001's runtime stdlib mandate (ADR-001 stands), does NOT add or remove from the dev-extras list, and does NOT pick a published packaging channel.

## Options

### Option A — Stdlib YAML-subset parser, exposed as a new internal CLI subcommand

A new module `argos/cli/frontmatter_parser.py` parallel to the three existing reference parsers, registered as the internal subcommand `argos frontmatter-parse <file>`. AC commands invoke `python3 -m argos.cli frontmatter-parse <file>` (or the launcher equivalent) and grep / `jq` the JSON output.

**Pros:**
- Fully consistent with ADR-001 as written. No amendment needed.
- Matches every existing reference parser in the project — sets the same pattern Layer 2 tickets are already inheriting.
- AC verification becomes interpreter-independent: any python3 ≥3.9 satisfies it, no `pip install` step required, no system-package dependency. Distribution intent is preserved.
- Reusable: ARG1-010, ARG1-012, ARG1-020, ARG1-031, ARG1-041 all get one parser. Marginal cost per future AC is one shell line.
- The grammar is the contract. Frontmatter drifts to stay inside the parser, not vice versa — a discipline the project benefits from regardless.

**Cons:**
- ~30–80 lines of YAML-subset code plus tests plus dispatch wiring.
- Hand-rolled parsers accumulate edge cases. The grammar must be pinned narrowly and documented up front. (This ADR pins it; see §Decision below.)
- Two existing tickets (ARG1-010, ARG1-012) need AC retrofit. Tracked as ARG1-059.

### Option B — Permit `pyyaml` as a dev-only dependency under ADR-001's existing dev-extras mechanism

Add `pyyaml>=6` to `[project.optional-dependencies] dev`. Document `pip install -e .[dev]` as an AC prerequisite.

**Pros:**
- No new code. Drop-in.
- `pyyaml` is industry-standard with battle-tested semantics.

**Cons:**
- **Reproduces the foot-gun on every downstream machine.** A contributor who skips `pip install -e .[dev]` and happens to have system `pyyaml` will see ACs pass under their luck of interpreter; one without system `pyyaml` will see ACs fail. The same accident that surfaced ARG1-057 becomes the steady-state experience.
- Conflicts with project pattern (every shipped reference parser explicitly rejected `pyyaml`).
- Couples AC verification to a third-party package even though runtime explicitly does not. Surface area grows: every ticket reviewer must remember "ACs may use pyyaml but runtime must not."
- Multi-harness contributors (Cursor / Codex / Gemini) silently degraded.

### Option C — Broader dev-deps allowlist

Amend ADR-001 to enumerate a small explicit allowlist of dev dependencies plus criteria for adding to it. Functionally a superset of (B).

**Pros:**
- Future-proofs against the next "we need this one library for tooling" debate.

**Cons:**
- Premature. We have one motivating dep and one motivating use case.
- Erodes ADR-001's clean rule into a list that grows over time.

### Option D — Pin AC harness to a specific interpreter

Document that ACs must be run under a known interpreter (e.g., `/usr/bin/python3`) where `pyyaml` is reliably installed.

**Pros:**
- Zero code change.

**Cons:**
- Brittle. Doesn't fix the inconsistency, just hides it behind one harness configuration.
- Conflicts with the `argos init` portability ambition.
- Doesn't survive distribution to other users.

## Recommendation

**Option A.** It is the only option that preserves the distribution intent (AC verification works on any machine where `argos` works, without dev-extras setup), matches the established project pattern (every shipped reference parser is stdlib-only), and removes the pyyaml-availability foot-gun rather than reproducing it.

## Decision

**Accepted: Option A — stdlib YAML-subset parser exposed as `argos frontmatter-parse`.** The following items are the contract.

### 1. AC tooling stdlib-only mandate

AC verification tooling — every command appearing in any v1.0 ticket's `## Acceptance criteria` section — is stdlib-only on the same terms as runtime code per ADR-001 §Decision item 2. Zero non-stdlib runtime imports. The `[project.optional-dependencies] dev` extra (currently `pytest>=7`) remains available for *test-suite ergonomics* (the precedent set by ADR-001) but MUST NOT be invoked from AC text. AC text must run cleanly under a fresh `python3 ≥3.9` with no `pip install` step.

This mandate does not amend ADR-001; it extends ADR-001's runtime rule to cover the AC harness, which ADR-001 left implicit.

### 2. New internal subcommand `argos frontmatter-parse`

Registered in `argos/cli/__main__.py` alongside the existing `state-parse` / `state-append` / `verifier-parse` / `escalation-validate`. Implementation module `argos/cli/frontmatter_parser.py`, parallel in shape to `argos/cli/verifier_parser.py` and `argos/cli/state_parser.py`. Public invocation:

```
python3 -m argos.cli frontmatter-parse <path>     # emits JSON to stdout
```

Output is a JSON object representing the parsed frontmatter. Exit codes: `0` parsed and valid; `1` file not found / unreadable; `2` schema/grammar violation (with stderr line citing the offending line number).

### 3. Subset grammar (canonical)

The parser supports exactly the following YAML subset and **rejects everything else**. The grammar is the contract; if a frontmatter shape needs a feature not listed here, the frontmatter changes — not the parser.

- **Flat scalars at the top level only.** `key: value` where the value is a string, integer, boolean, or null. Type detection is YAML 1.2 core: `true`/`false` (case-sensitive) → bool; `~` or `null` → null; matching `-?[0-9]+` → int; everything else → string.
- **Block sequences of strings only.** A key followed by indented `  - item` lines. Sequence items must be flat scalars (strings); nested sequences are not supported.
- **No flow style.** Inline list literals `[a, b]` and inline maps `{a: b}` are rejected.
- **No anchors, aliases, tags.** `&anchor`, `*alias`, `!!tag`, `!custom` are all rejected.
- **No multiline scalars.** Block-scalar indicators `|` and `>` are rejected. Folded scalars are rejected.
- **No nested mappings beyond depth 1.** A top-level key may not have a mapping as its value. Block sequences (item 2) are the only structured value type.
- **Comments allowed.** `# ...` to end of line, treated as a no-op. Preserved in source but not surfaced in JSON output.
- **UTF-8 only.** Inputs not decodable as UTF-8 are rejected with a parse-level error.
- **Quoted strings.** Double-quoted strings are supported for values that contain colons or glob characters (e.g. `"**/*.{ts,py}"` in `denied_paths`). Single-quoted strings are also supported. Escape sequences inside quoted strings are limited to `\"`, `\\`, `\n`, `\t`.

### 4. Rejection contract

Any input outside the subset MUST cause the parser to exit non-zero (code 2) with a single-line stderr message of the shape:

```
frontmatter-parse: line N: <one-line reason citing the unsupported feature>
```

Examples of conforming error messages:

```
frontmatter-parse: line 7: flow-style sequence not supported
frontmatter-parse: line 12: nested mapping at depth 2 not supported
frontmatter-parse: line 3: anchor '&foo' not supported
frontmatter-parse: line 5: multiline scalar indicator '|' not supported
frontmatter-parse: line 1: input not valid UTF-8
```

Downstream consumers (AC text, the schema-doc consistency tests, future harness tooling) rely on the exit code and the `line N:` prefix; they do not parse the human-readable reason.

### 5. Grammar drift policy

If a future ticket needs a YAML feature outside this subset, the response is:

1. **Adjust the frontmatter** to fit the subset (preferred — frontmatter is project-controlled).
2. **File an ADR amending this one** if (1) is genuinely impossible. The ADR must enumerate the new feature and the parser change and re-publish §3 with the additions.

The parser does NOT silently grow features. PRs that extend the parser's capabilities without a paired ADR amendment are rejected.

## Consequences

### What this decision establishes

- Every AC verification command in every v1.0 ticket runs against a stdlib-only Python ≥3.9 with no third-party imports. `argos frontmatter-parse` is the canonical frontmatter validator for ACs.
- The subset grammar in §3 is the project's frontmatter dialect. Subagent definitions, dispatch logs, escalation files, ADR frontmatter, ticket frontmatter — all conform to it. Existing files already do (verified informally during the escalation; ARG1-060's tests will verify formally against the orchestrator and verifier agent definitions).
- ADR-001 is not amended. Its runtime stdlib-only rule and its dev-extras escape hatch (`pytest`) stand unchanged. ADR-002 extends the spirit to AC tooling rather than carving an exception.
- Two follow-up tickets are filed: ARG1-060 (implement `frontmatter-parse`) and ARG1-059 (retrofit ARG1-010 / ARG1-012 ACs to invoke it). Layer 2 fan-out (ARG1-020, ARG1-031, ARG1-041) blocks on ARG1-060.

### What this decision does NOT establish

- **Published distribution channel.** Same TODO carried forward from ADR-001. ADR-NNN-packaging-channel still required before any 1.0.0 release.
- **A general dev-deps allowlist.** ADR-001's "pytest is the named exception" rule stands. Future dev-only deps require their own ADR.
- **A schema for ticket frontmatter, ADR frontmatter, or any specific consumer's keys.** ADR-002 pins the *grammar* (what YAML features are allowed); per-document key schemas live in their respective schema docs (e.g. `argos/specs/v1.0/schemas/state-block.md`, `escalation.md`, `config.md`). `frontmatter-parse` is a parser, not a validator-of-keys.
- **Removal of `pyyaml` from any contributor's machine.** `pyyaml` may still be present system-wide or in some venvs; ADR-002 only forbids depending on it from AC text or shipped code.

### What becomes harder

- Hand-rolled parsers accumulate edge cases over time. The grammar drift policy in §5 is the mitigation, but discipline is required.
- A future "we want richer YAML in some frontmatter" wish requires ADR amendment, not a one-line `pip install`.

### What becomes easier

- AC verification is now portable to every contributor and downstream user without a setup step.
- The project's frontmatter dialect is documented in a single canonical place. Consumers of frontmatter (current and future) can be written against §3 with confidence about what they will and won't see.
- ARG1-057's foot-gun cannot recur: there is no longer an "interpreter happens to have pyyaml" path through the AC harness.
