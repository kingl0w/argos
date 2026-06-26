"""Tests for the parser + graph builder against a SYNTHETIC fixture spec tree.

Deliberately does NOT test against argos's real specs (brittle). The fixture tree
under tests/fixtures/specs/ hand-rolls one ticket per edge type plus a drain chain.
"""

from __future__ import annotations

from pathlib import Path

from rdflib.namespace import RDF

from argos_graph import parse, build, query
from argos_graph.build import A, DATA, _u

SPECS = Path(__file__).parent / "fixtures" / "specs"


# --- parser ---------------------------------------------------------------

def _scan():
    return parse.scan_specs(SPECS, repo_root=SPECS.parent)


def test_ticket_headers_and_sections():
    t = {x["ticket_id"]: x for x in _scan()["tickets"]}
    syn10 = t["SYN-010"]
    assert syn10["status"] == "Done"
    assert syn10["priority"] == "P0"
    assert syn10["epic"] == 7
    assert syn10["epic_label"] == "Widget platform"
    assert syn10["depends_on"] == []           # "none" -> no edge
    assert "syn/widget/core.py" in syn10["touches"]
    assert "SYN-020" in syn10["parallelizable_with"]
    assert "ADR-009" in syn10["adr_refs"]
    assert syn10["intent"].startswith("Build the widget core")
    assert "Second paragraph" not in (syn10["intent"] or "")


def test_depends_and_amendment():
    t = {x["ticket_id"]: x for x in _scan()["tickets"]}
    syn20 = t["SYN-020"]
    assert syn20["depends_on"] == ["SYN-010"]
    assert syn20["amends"] == "SYN-099"


def test_adr_redacts_emails_and_drains():
    adr = _scan()["adrs"][0]
    assert adr["adr_id"] == "ADR-009"
    assert adr["status"] == "Accepted"
    assert adr["deciders"] is not None
    assert "@" not in adr["deciders"]          # emails redacted
    assert "[decider]" in adr["deciders"]
    assert "SYN-057" in adr["drains_into"]
    assert adr["decision"].startswith("Accepted: Option A")


def test_escalation_frontmatter():
    esc = _scan()["escalations"][0]
    assert esc["ticket_id"] == "SYN-057"
    assert esc["severity"] == "blocking"
    assert esc["raised_by"] == "coder"
    assert esc["created"].startswith("2026-01-04")


def test_state_entries():
    s = {x["ticket"]: x for x in _scan()["sessions"]}
    assert s["SYN-010"]["decision"] == "pass-with-minors"
    assert s["SYN-010"]["counts"] == (0, 1, 2)
    assert s["SYN-010"]["author"] == "verifier"
    assert s["SYN-010"]["branch"] == "ticket/SYN-010"
    assert "syn/widget/core.py" in s["SYN-010"]["files"]


def test_drain_chain_parsed():
    chains = _scan()["drain_chains"]
    assert any(c["chain"] == ["SYN-010", "SYN-057", "ADR-009", "SYN-020"] for c in chains)


# --- graph ----------------------------------------------------------------

def _graph():
    return build.build_graph(_scan())


def test_structured_edges_present():
    g = _graph()
    assert (_u("ticket", "SYN-020"), A.dependsOn, _u("ticket", "SYN-010")) in g
    assert (_u("ticket", "SYN-010"), A.partOfEpic, _u("epic", "7")) in g
    assert (_u("ticket", "SYN-010"), A.governedBy, _u("adr", "ADR-009")) in g
    assert (_u("ticket", "SYN-020"), A.amends, _u("ticket", "SYN-099")) in g
    assert (_u("epic", "7"), A.epicLabel, None) in [(s, p, None) for s, p, o in g
                                                    if p == A.epicLabel and s == _u("epic", "7")]


def test_blocked_by_edge():
    g = _graph()
    esc = _u("escalation", "SYN-057-2026-01-04T00-00-00Z")
    assert (_u("ticket", "SYN-057"), A.blockedBy, esc) in g


def test_no_emails_in_graph():
    ttl = _graph().serialize(format="turtle")
    assert "@example" not in ttl


def test_prose_drain_edges_carry_confidence():
    g = _graph()
    # a reified statement for a drain hop must carry prose-derived confidence
    from rdflib import Literal
    confident = list(g.subjects(A.confidence, Literal("prose-derived")))
    assert confident, "expected at least one prose-derived reified statement"
    # and the asserted drain edge SYN-010 -> escalation exists
    assert (_u("ticket", "SYN-010"), A.drainsInto,
            _u("escalation", "SYN-057-2026-01-04T00-00-00Z")) in g


def test_verification_result_counts():
    g = _graph()
    res = _u("result", "2026-01-06T00:00:00Z-SYN-010")
    from rdflib import Literal
    from rdflib.namespace import XSD
    assert (res, A.majorCount, Literal(1, datatype=XSD.integer)) in g
    assert (res, A.minorCount, Literal(2, datatype=XSD.integer)) in g


# --- queries --------------------------------------------------------------

def test_drain_chain_query():
    g = _graph()
    rows = list(query.run_named(g, "drain-chain"))
    chains = {(query._short(r[0]), query._short(r[1]),
               query._short(r[2]), query._short(r[3])) for r in rows}
    assert ("ticket/SYN-010", "escalation/SYN-057-2026-01-04T00-00-00Z",
            "adr/ADR-009", "ticket/SYN-020") in chains


def test_dependency_dag_query():
    g = _graph()
    rows = list(query.run_named(g, "dependency-dag"))
    pairs = {(query._short(r[0]), query._short(r[1])) for r in rows}
    assert ("ticket/SYN-020", "ticket/SYN-010") in pairs


def test_parallelizable_with_is_symmetric():
    g = _graph()
    pairs = list(g.subject_objects(A.parallelizableWith))
    assert pairs, "expected at least one parallelizableWith edge"
    for a, b in pairs:
        assert (b, A.parallelizableWith, a) in g, f"missing inverse for {a} <-> {b}"


def test_ask_query_returns_bool_without_raising():
    g = _graph()
    result = query.run(g, """
        PREFIX argos: <https://github.com/kingl0w/argos/ns#>
        ASK { ?t a argos:Ticket }
    """)
    assert result.type == "ASK"
    assert isinstance(result.askAnswer, bool)
    assert result.askAnswer is True


def test_agent_pass_rate_query():
    g = _graph()
    rows = list(query.run_named(g, "agent-pass-rate"))
    triples = {(query._short(r[0]), str(r[1]), int(r[2])) for r in rows}
    assert ("agent/verifier", "pass-with-minors", 1) in triples
    assert ("agent/coder", "pass", 1) in triples
