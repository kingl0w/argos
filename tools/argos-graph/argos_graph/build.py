"""Turn parsed entity dicts into an rdflib.Graph and serialize Turtle.

Structured edges (frontmatter, ## sections, STATE attrs) are full-confidence.
Prose-derived drain-chain hops carry ``argos:confidence "prose-derived"`` on a
reified statement, so they are distinguishable from structured edges. Every
object-property edge is reified with ``argos:sourceFile`` (and a line number
where determinable) for provenance.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from rdflib import Graph, Literal, Namespace, BNode
from rdflib.namespace import RDF, RDFS, XSD

from . import parse as _parse

A = Namespace("https://github.com/kingl0w/argos/ns#")
DATA = Namespace("https://github.com/kingl0w/argos/data#")


def _u(kind: str, key: str):
    return DATA[quote(f"{kind}/{key}", safe="-._~")]


def _rel_edge(g: Graph, s, p, o, src=None, line=None, confidence=None):
    """Assert an object-property edge and reify it with provenance."""
    g.add((s, p, o))
    stmt = BNode()
    g.add((stmt, RDF.type, RDF.Statement))
    g.add((stmt, RDF.subject, s))
    g.add((stmt, RDF.predicate, p))
    g.add((stmt, RDF.object, o))
    if src:
        g.add((stmt, A.sourceFile, Literal(src)))
    if line is not None:
        g.add((stmt, A.sourceLine, Literal(int(line), datatype=XSD.integer)))
    if confidence:
        g.add((stmt, A.confidence, Literal(confidence)))


def build_graph(parsed: dict) -> Graph:
    g = Graph()
    g.bind("argos", A)
    g.bind("argosdata", DATA)

    # registry: id -> node, for resolving prose drain-chain tokens.
    # ticket/adr take precedence over escalation (so ARG1-021 -> ticket, while
    # ARG1-057, which has no ticket file, -> its escalation node).
    registry: dict[str, object] = {}

    epics: dict[int, object] = {}

    for t in parsed["tickets"]:
        node = _u("ticket", t["ticket_id"])
        registry[t["ticket_id"]] = node
        g.add((node, RDF.type, A.Ticket))
        g.add((node, A.ticketId, Literal(t["ticket_id"])))
        g.add((node, RDFS.label, Literal(t["ticket_id"])))
        if t["priority"]:
            g.add((node, A.priority, Literal(t["priority"])))
        if t["status"]:
            g.add((node, A.status, Literal(t["status"])))
        if t["created"]:
            g.add((node, A.createdDate, Literal(t["created"])))
        if t["intent"]:
            g.add((node, A.intent, Literal(t["intent"])))

        if t["epic"] is not None:
            epic_node = epics.get(t["epic"])
            if epic_node is None:
                epic_node = _u("epic", str(t["epic"]))
                epics[t["epic"]] = epic_node
                g.add((epic_node, RDF.type, A.Epic))
                g.add((epic_node, RDFS.label, Literal(f"Epic {t['epic']}")))
                if t["epic_label"]:
                    g.add((epic_node, A.epicLabel, Literal(t["epic_label"])))
            elif t["epic_label"] and (epic_node, A.epicLabel, None) not in g:
                g.add((epic_node, A.epicLabel, Literal(t["epic_label"])))
            _rel_edge(g, node, A.partOfEpic, epic_node, t["source_file"], t["epic_line"])

        for dep in t["depends_on"]:
            _rel_edge(g, node, A.dependsOn, _u("ticket", dep), t["source_file"], t["depends_line"])
        for par in t["parallelizable_with"]:
            _rel_edge(g, node, A.parallelizableWith, _u("ticket", par), t["source_file"], t["parallel_line"])
        for f in t["touches"]:
            _rel_edge(g, node, A.touches, _sourcefile(g, f), t["source_file"], t["touches_line"])
        for adr in t["adr_refs"]:
            _rel_edge(g, node, A.governedBy, _u("adr", adr), t["source_file"])
        if t["amends"]:
            _rel_edge(g, node, A.amends, _u("ticket", t["amends"]), t["source_file"])

    for a in parsed["adrs"]:
        node = _u("adr", a["adr_id"])
        registry.setdefault(a["adr_id"], node)
        g.add((node, RDF.type, A.ADR))
        g.add((node, A.ticketId, Literal(a["adr_id"])))
        g.add((node, RDFS.label, Literal(a["adr_id"])))
        if a["status"]:
            g.add((node, A.status, Literal(a["status"])))
        if a["created"]:
            g.add((node, A.createdDate, Literal(a["created"])))
        if a["decision"]:
            g.add((node, A.decision, Literal(a["decision"])))
        if a["deciders"]:
            g.add((node, RDFS.comment, Literal(f"Deciders: {a['deciders']}")))
        # structured drainsInto: the escalation(s) the ADR names in its Context.
        for ref in a["drains_into"]:
            tgt = _resolve_escalation(parsed, ref)
            if tgt is not None:
                _rel_edge(g, node, A.drainsInto, tgt, a["source_file"])

    for e in parsed["escalations"]:
        node = _u("escalation", e["esc_id"])
        # escalation registers only if its id isn't already a ticket/adr.
        if e["ticket_id"]:
            registry.setdefault(e["ticket_id"], node)
        g.add((node, RDF.type, A.Escalation))
        g.add((node, A.ticketId, Literal(e["ticket_id"] or e["esc_id"])))
        g.add((node, RDFS.label, Literal(e["esc_id"])))
        if e["severity"]:
            g.add((node, A.severity, Literal(e["severity"])))
        if e["raised_by"]:
            g.add((node, A.raisedBy, Literal(e["raised_by"])))
        if e["created"]:
            g.add((node, A.createdDate, Literal(e["created"])))
        # the ticket named by the escalation is blockedBy it.
        if e["ticket_id"]:
            _rel_edge(g, _u("ticket", e["ticket_id"]), A.blockedBy, node, e["source_file"])

    for s in parsed["sessions"]:
        if not s["id"]:
            continue
        node = _u("session", s["id"])
        g.add((node, RDF.type, A.Session))
        g.add((node, RDFS.label, Literal(s["session"] or s["id"])))
        if s["author"]:
            agent = _u("agent", s["author"])
            if (agent, RDF.type, A.Agent) not in g:
                g.add((agent, RDF.type, A.Agent))
                g.add((agent, RDFS.label, Literal(s["author"])))
            _rel_edge(g, node, A.authoredBy, agent, s["source_file"], s["source_line"])
        if s["ticket"]:
            _rel_edge(g, _u("ticket", s["ticket"]), A.verifiedBy, node, s["source_file"], s["source_line"])
        if s["branch"]:
            branch = _u("branch", s["branch"])
            if (branch, RDF.type, A.Branch) not in g:
                g.add((branch, RDF.type, A.Branch))
                g.add((branch, RDFS.label, Literal(s["branch"])))
            _rel_edge(g, node, A.producedBranch, branch, s["source_file"], s["source_line"])
        for f in s["files"]:
            _rel_edge(g, node, A.changedFile, _sourcefile(g, f), s["source_file"], s["source_line"])
        if s["decision"] or s["counts"]:
            res = _u("result", s["id"])
            g.add((res, RDF.type, A.VerificationResult))
            if s["decision"]:
                g.add((res, A.decision, Literal(s["decision"])))
            if s["counts"]:
                c, mj, mn = s["counts"]
                g.add((res, A.criticalCount, Literal(c, datatype=XSD.integer)))
                g.add((res, A.majorCount, Literal(mj, datatype=XSD.integer)))
                g.add((res, A.minorCount, Literal(mn, datatype=XSD.integer)))
            _rel_edge(g, node, A.hasResult, res, s["source_file"], s["source_line"])

    # prose-derived drain chains (lower confidence).
    for ch in parsed["drain_chains"]:
        ids = ch["chain"]
        for src_tok, dst_tok in zip(ids, ids[1:]):
            s_node = _resolve_token(registry, src_tok)
            o_node = _resolve_token(registry, dst_tok)
            _rel_edge(g, s_node, A.drainsInto, o_node,
                      ch["source_file"], ch["source_line"], confidence="prose-derived")

    return g


def _sourcefile(g: Graph, path: str):
    node = _u("file", path)
    if (node, RDF.type, A.SourceFile) not in g:
        g.add((node, RDF.type, A.SourceFile))
        g.add((node, RDFS.label, Literal(path)))
    return node


def _resolve_token(registry: dict, tok: str):
    if tok in registry:
        return registry[tok]
    if tok.startswith("ADR"):
        return _u("adr", tok)
    return _u("ticket", tok)


def _resolve_escalation(parsed: dict, ref: str):
    """An ADR Context reference -> the escalation node whose ticket_id matches."""
    for e in parsed["escalations"]:
        if e["ticket_id"] == ref or e["esc_id"].startswith(ref):
            return _u("escalation", e["esc_id"])
    return None


def build_from_specs(specs_root: Path, repo_root: Path | None = None) -> Graph:
    parsed = _parse.scan_specs(specs_root, repo_root)
    return build_graph(parsed)


def serialize(g: Graph, out_path: Path | None = None) -> str:
    ttl = g.serialize(format="turtle")
    if out_path:
        Path(out_path).write_text(ttl, encoding="utf-8")
    return ttl
