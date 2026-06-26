"""Named SPARQL queries + raw-query runner + result rendering.

Named queries live as ``queries/*.sparql`` next to the package; the file stem is
the query name. ``--json`` output is a viz-ready node-link structure (nodes +
edges derived from the URIRef bindings of each result row) alongside the raw rows.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from rdflib import Graph, URIRef, Literal
from rdflib.namespace import RDF, RDFS

_QUERIES_DIR = Path(__file__).resolve().parent.parent / "queries"


def queries_dir() -> Path:
    return _QUERIES_DIR


def named_queries() -> list[str]:
    return sorted(p.stem for p in _QUERIES_DIR.glob("*.sparql"))


def load_named(name: str) -> str:
    path = _QUERIES_DIR / f"{name}.sparql"
    if not path.exists():
        raise KeyError(name)
    return path.read_text(encoding="utf-8")


def run(graph: Graph, sparql: str):
    return graph.query(sparql)


def run_named(graph: Graph, name: str):
    return run(graph, load_named(name))


# --- rendering -------------------------------------------------------------

def _short(term) -> str:
    s = str(term)
    if "/data#" in s:
        return unquote(s.split("/data#", 1)[1])
    if "/ns#" in s:
        return "argos:" + s.split("/ns#", 1)[1]
    return s


def _term_str(term) -> str:
    if term is None:
        return ""
    if isinstance(term, URIRef):
        return _short(term)
    return str(term)


def _node_meta(graph: Graph, uri: URIRef) -> dict:
    label = graph.value(uri, RDFS.label)
    rtype = graph.value(uri, RDF.type)
    return {
        "id": _short(uri),
        "label": str(label) if label else _short(uri),
        "type": _short(rtype) if rtype else None,
    }


def to_rows(result) -> tuple[list[str], list[dict]]:
    cols = [str(v) for v in result.vars]
    rows = [{str(v): _term_str(row[v]) for v in result.vars} for row in result]
    return cols, rows


def to_table(result) -> str:
    cols, rows = to_rows(result)
    if not rows:
        return "(no results)"
    widths = {c: max(len(c), *(len(r[c]) for r in rows)) for c in cols}
    line = lambda cells: "  ".join(c.ljust(widths[col]) for col, c in zip(cols, cells))
    out = [line(cols), line(["-" * widths[c] for c in cols])]
    out += [line([r[c] for c in cols]) for r in rows]
    return "\n".join(out)


def to_node_link(graph: Graph, result) -> dict:
    cols = [str(v) for v in result.vars]
    nodes: dict[str, dict] = {}
    edges: list[dict] = []
    rows: list[dict] = []
    for row in result:
        r = {}
        uri_cells = []
        for v in result.vars:
            val = row[v]
            r[str(v)] = _term_str(val)
            if isinstance(val, URIRef):
                nid = _short(val)
                nodes.setdefault(nid, _node_meta(graph, val))
                uri_cells.append(nid)
        rows.append(r)
        for a, b in zip(uri_cells, uri_cells[1:]):
            edges.append({"source": a, "target": b})
    return {"columns": cols, "rows": rows,
            "nodes": list(nodes.values()), "edges": edges}
