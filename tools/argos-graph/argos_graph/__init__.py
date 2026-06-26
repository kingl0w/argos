"""argos-graph: an optional, read-only RDF projection of an argos spec repo.

Not part of the argos core (which is stdlib-only per ADR-001). This tool has its
own dependency (rdflib), never imports the ``argos`` package, and never writes to
``argos/specs/``.
"""

__version__ = "0.1.0"
