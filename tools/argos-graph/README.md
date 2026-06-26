# argos-graph

`argos-graph` is an **optional, read-only projection** of an argos repo's specs
into an RDF knowledge graph. It is **NOT part of the argos core** (which is
stdlib-only per ADR-001); it lives here for discoverability but has its own
dependency (`rdflib`) and its own `pyproject.toml`, never imports the `argos`
package, and never touches argos's runtime or `argos/specs/`. The markdown specs
remain the source of truth; this graph is a **derived, rebuild-on-demand view**
for querying and analysis.

## What it reads

Three distinct source formats, parsed verbatim (READ-ONLY):

| Source | Format | Becomes |
|--------|--------|---------|
| `argos/specs/**/tickets/{ID}.md` | markdown headers (`**Epic:**`, `## Depends on`, `## Touches`, `## Parallelizable with`, `## Amendment`) | `argos:Ticket` + `argos:Epic` |
| `argos/specs/**/decisions/ADR-NNN-*.md` | markdown (`**Status:**`, `**Deciders:**`) | `argos:ADR` |
| `argos/specs/escalations/*.md` | YAML frontmatter (`ticket_id`, `severity`, `raised_by`, `created`) | `argos:Escalation` |
| `argos/specs/**/STATE.md` | `<!-- argos:entry id=.. ticket=.. author=.. -->` blocks | `argos:Session` + `argos:VerificationResult` |

The vocabulary is hand-authored in [`ontology/argos.ttl`](ontology/argos.ttl)
(classes, object/datatype properties, `rdfs:domain`/`range`/`label`).

## Structured vs. prose-derived edges

Edges from **structured** sources — frontmatter, `## sections`, STATE attributes —
are full-confidence. Some relationships only exist in **narrative prose** (e.g.
"drained via ARG1-057 → ADR-002 → ARG1-059"). Those are recovered best-effort by
regex and tagged on a reified statement with `argos:confidence "prose-derived"`,
so a consumer can always tell a structured edge from a scraped one. Every
object-property edge is reified with `argos:sourceFile` (and a line number where
determinable) for provenance.

## Install

```sh
cd tools/argos-graph
python3 -m venv .venv && .venv/bin/pip install -e .
```

## Usage

```sh
argos-graph build [--specs PATH] [--out graph.ttl]   # parse → Turtle (stdout or file)
argos-graph query <name> [--json]                    # run a named query (table, or viz-ready JSON)
argos-graph sparql <file.sparql>                     # run an arbitrary query
argos-graph queries                                  # list named queries
```

`--specs` defaults to `argos/specs/` resolved relative to the repo root.
`--json` emits `{columns, rows, nodes, edges}` — a node-link structure ready for
a v1.1 visualizer.

## Example queries

**Flagship — reconstruct a drain-chain** (`queries/drain-chain.sparql`):

```sh
$ argos-graph query drain-chain
ticket           escalation                                adr          resolution
---------------  ----------------------------------------  -----------  ---------------
ticket/ARG1-010  escalation/ARG1-057-2026-04-29T19-30-00Z  adr/ADR-002  ticket/ARG1-059
```

A ticket's foot-gun (`ARG1-010` shipped `import yaml`) → the escalation that
surfaced it (`ARG1-057`) → the ADR that resolved it (`ADR-002`) → the ticket that
retrofitted it (`ARG1-059`) — recovered entirely from prose.

**Per-agent verification outcomes** (`queries/agent-pass-rate.sparql`):

```sh
$ argos-graph query agent-pass-rate
author              decision          count
------------------  ----------------  -----
agent/coder         pass              4
agent/verifier      pass              23
agent/verifier      pass-with-minors  2
```

**Tickets blocked by an escalation** (`queries/blocked-tickets.sparql`):

```sh
$ argos-graph query blocked-tickets
ticket           escalation                                severity
---------------  ----------------------------------------  --------
ticket/ARG1-021  escalation/ARG1-021-2026-05-02T15-49-14Z  advisory
ticket/ARG1-057  escalation/ARG1-057-2026-04-29T19-30-00Z  blocking
```

Other named queries: `dependency-dag` (the ticket DAG), `epic-rollup` (tickets
per epic by status).

## Privacy

ADR `**Deciders:**` lines often contain email addresses. The parser **redacts**
any email to `[decider]` before it reaches the graph — real addresses are never
emitted.

## Tests

```sh
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests run against a **synthetic** fixture spec tree under `tests/fixtures/` (one
ticket per edge type incl. a drain chain), not argos's real specs (which would be
brittle).
