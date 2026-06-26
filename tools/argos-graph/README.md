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

## What this demonstrates

`argos-graph` is a read-only RDF projection of an argos spec tree. The markdown
specs stay the source of truth; this tool parses them into a knowledge graph
(`rdflib` + SPARQL) that answers questions the markdown cannot answer by eye.
Three commands make the case.

### 1. Causal provenance reconstructed across artifact types

```
argos-graph query drain-chain
```

```
ticket           escalation                                adr          resolution
ticket/ARG1-010  escalation/ARG1-057-2026-04-29T19-30-00Z  adr/ADR-002  ticket/ARG1-059
```

ARG1-010 used `import yaml`, violating the stdlib-only decision ADR-001. That
violation was escalated (ARG1-057, blocking), the escalation drained into a new
decision (ADR-002), and that decision was implemented by ARG1-059. The full
chain spans four artifact types in three different file formats, and part of it
is encoded only in prose. The parser extracts structured edges authoritatively
and treats prose-derived edges as a secondary pass, marking them
`argos:confidence "prose-derived"` with `sourceFile` and `sourceLine`. Declared
edges and extracted edges stay distinguishable, which is the honest way to build
a graph from semi-structured text.

### 2. Reconciling two sources that disagree

```
argos-graph query effective-status
```

Ticket files carry a `**Status:**` field that, in this repo, still reads
`Queued` for work that has long since shipped. The real done-ness signal lives
elsewhere, in the verification record attached to each session. This query
reaches past the stale field and reports the disagreement: tickets whose file
says `Queued` (or omits status entirely) while a verification result records a
`pass`. The blank-status rows are the sharpest, the markdown says nothing and
the graph still knows the work is done. A graph earns its keep when it can
reconcile sources that contradict each other.

### 3. The vocabulary

```
sed -n '1,40p' ontology/argos.ttl
```

`ontology/argos.ttl` is hand-authored and is the canonical vocabulary; the build
tool emits instance data in its namespace and never edits it. Classes and
properties are format-neutral so one vocabulary describes a ticket (markdown
headers), an ADR (markdown), an escalation (YAML frontmatter), and a STATE.md
session (HTML-comment-delimited block). Properties carry `rdfs:domain`,
`rdfs:range`, and labels; `parallelizableWith` is an `owl:SymmetricProperty`
whose inverse is materialized at build time so queries read correctly without a
reasoner.

### It is an open graph, not a fixed report

The five named queries are conveniences. The graph answers arbitrary SPARQL:

```
echo 'PREFIX argos: <https://github.com/kingl0w/argos/ns#>
SELECT ?t ?adr WHERE { ?t argos:governedBy ?adr } ORDER BY ?t' > /tmp/gov.sparql
argos-graph sparql /tmp/gov.sparql
```

This one surfaces which ADRs govern which tickets, and the answer shows the
ratification boundary as data: tickets created before ADR-002 answer only to
ADR-001, tickets after answer to both.

### Boundaries

This tool is optional and isolated. It has its own `pyproject.toml` with
`rdflib`, never imports the `argos` package, and never writes to
`argos/specs/`. The argos core stays standard-library-only (ADR-001); this
projection lives at arm's length and serves humans and analysis, never argos's
runtime.
