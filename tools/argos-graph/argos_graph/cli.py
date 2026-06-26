"""argos-graph CLI:  build | query <name> | sparql <file> | queries

READ-ONLY against the spec tree. Default --specs resolves argos/specs/ relative
to the repo root (three levels up from this file).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, build, query


def _default_specs() -> Path:
    return Path(__file__).resolve().parents[3] / "argos" / "specs"


def _load_graph(specs: Path, graph_file: Path | None):
    if graph_file:
        from rdflib import Graph
        g = Graph()
        g.parse(graph_file, format="turtle")
        return g
    specs = specs.resolve()
    return build.build_from_specs(specs, repo_root=specs.parent.parent)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    p = argparse.ArgumentParser(prog="argos-graph", description=__doc__)
    p.add_argument("--version", action="version", version=f"argos-graph {__version__}")
    sub = p.add_subparsers(dest="cmd")

    pb = sub.add_parser("build", help="parse specs and emit Turtle")
    pb.add_argument("--specs", type=Path, default=_default_specs())
    pb.add_argument("--out", type=Path, help="write .ttl here (default: stdout)")

    pq = sub.add_parser("query", help="run a named query")
    pq.add_argument("name")
    pq.add_argument("--specs", type=Path, default=_default_specs())
    pq.add_argument("--graph", type=Path, help="load a prebuilt .ttl instead of re-parsing specs")
    pq.add_argument("--json", action="store_true", help="emit viz-ready {nodes, edges} JSON")

    ps = sub.add_parser("sparql", help="run an arbitrary .sparql file")
    ps.add_argument("file", type=Path)
    ps.add_argument("--specs", type=Path, default=_default_specs())
    ps.add_argument("--graph", type=Path, help="load a prebuilt .ttl instead of re-parsing specs")
    ps.add_argument("--json", action="store_true")

    sub.add_parser("queries", help="list named queries")

    args = p.parse_args(argv)

    if args.cmd == "build":
        g = _load_graph(args.specs, None)
        ttl = build.serialize(g, args.out)
        if args.out:
            print(f"wrote {len(g)} triples to {args.out}", file=sys.stderr)
        else:
            sys.stdout.write(ttl)
        return 0

    if args.cmd == "queries":
        for name in query.named_queries():
            print(name)
        return 0

    if args.cmd == "query":
        try:
            sparql = query.load_named(args.name)
        except KeyError:
            print(f"argos-graph: unknown query: {args.name}", file=sys.stderr)
            print("available: " + ", ".join(query.named_queries()), file=sys.stderr)
            return 2
        g = _load_graph(args.specs, args.graph)
        result = query.run(g, sparql)
        return _emit(g, result, args.json)

    if args.cmd == "sparql":
        if not args.file.exists():
            print(f"argos-graph: no such file: {args.file}", file=sys.stderr)
            return 1
        g = _load_graph(args.specs, args.graph)
        result = query.run(g, args.file.read_text(encoding="utf-8"))
        return _emit(g, result, args.json)

    p.print_help()
    return 0


def _emit(g, result, as_json: bool) -> int:
    # ASK / CONSTRUCT / DESCRIBE have no result.vars to iterate; guard by type.
    if result.type == "ASK":
        print(result.askAnswer)
        return 0
    if result.type in ("CONSTRUCT", "DESCRIBE"):
        sys.stdout.write(result.serialize(format="turtle"))
        return 0
    if as_json:
        print(json.dumps(query.to_node_link(g, result), indent=2))
    else:
        print(query.to_table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
