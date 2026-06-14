"""Shared spec-tree path resolution (ARG1-075).

argos versions its own specs under ``argos/specs/v1.0/`` while ``argos init``
scaffolds a foreign repo to a flat ``argos/specs/`` (no ``v1.0/`` segment).
Queue-touching commands must read the right tree in *both* layouts without the
operator passing ``--state-file`` / ``--ticket-dir`` by hand; hardcoding the
``argos/specs/v1.0/...`` defaults leaked argos's own internal layout onto every
scaffolded repo (the queue came up empty there).

INTERIM probe: we decide the root by checking whether
``<repo_root>/argos/specs/v1.0/STATE.md`` exists. The eventual model is an
explicit ``project.specs_root`` config key (see ARG1-075) read via
``argos.cli.config``; until that lands, this filesystem probe keeps both argos's
own repo and a freshly ``init``-ed repo working with bare commands.

CRITICAL: ``STATE.md`` and ``tickets/`` MUST derive from the *same* resolved
root in a single call — never probe them independently, or a v1.0 STATE.md
could be paired with a flat ``tickets/`` dir. Use :func:`default_spec_paths`
whenever a command needs both.

Paths are returned *relative* to ``repo_root`` (e.g. ``argos/specs/v1.0/STATE.md``),
matching the literal defaults these helpers replace; callers join them against
their own resolved repo root exactly as before. ADR-001: standard library only.
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "resolve_specs_root",
    "default_state_file",
    "default_ticket_dir",
    "default_spec_paths",
]

# Relative spec-tree roots, in probe order.
_SPECS_ROOT = Path("argos") / "specs"
_V1_SPECS_ROOT = _SPECS_ROOT / "v1.0"


def resolve_specs_root(repo_root: str | Path = ".") -> Path:
    """Return the specs root (relative to ``repo_root``) for this repo.

    ``argos/specs/v1.0`` when a v1.0 ``STATE.md`` is present (argos's own
    versioned tree); otherwise ``argos/specs`` (a flat, ``init``-scaffolded
    repo).
    """
    if (Path(repo_root) / _V1_SPECS_ROOT / "STATE.md").exists():
        return _V1_SPECS_ROOT
    return _SPECS_ROOT


def default_state_file(repo_root: str | Path = ".") -> str:
    """Default ``STATE.md`` path (relative to ``repo_root``)."""
    return str(resolve_specs_root(repo_root) / "STATE.md")


def default_ticket_dir(repo_root: str | Path = ".") -> str:
    """Default tickets directory (relative to ``repo_root``)."""
    return str(resolve_specs_root(repo_root) / "tickets")


def default_spec_paths(repo_root: str | Path = ".") -> tuple[str, str]:
    """Return ``(state_file, ticket_dir)`` from a SINGLE resolved root.

    Use this whenever a command needs both defaults so the two can never
    disagree (see the module docstring's CRITICAL note).
    """
    root = resolve_specs_root(repo_root)
    return str(root / "STATE.md"), str(root / "tickets")
