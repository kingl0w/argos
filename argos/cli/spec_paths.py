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

One exception to the relative contract (ARG-006): a *bare* call (the ``'.'``
default) made from a subdirectory of a repo anchors at the nearest ancestor
containing ``argos/specs/`` or ``.git`` and returns absolute paths, so bare
``orchestrate`` / ``queue`` work from anywhere inside the repo. Explicit
``repo_root`` arguments and bare calls made at the repo root are unchanged.
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


def _anchor(repo_root: str | Path) -> tuple[Path, Path]:
    """Return ``(probe_root, join_base)`` for a deriver call.

    Explicit roots pass through with a relative join (the historical
    contract). A bare ``'.'`` invoked from a subdirectory of a repo anchors
    both at the nearest ancestor containing ``argos/specs/`` or ``.git``, so
    bare commands work from anywhere inside the repo (ARG-006). The ``.git``
    probe stops the ascent at a repo boundary — a bare call from an
    unscaffolded repo never escapes into a parent project's spec tree.
    """
    base = Path(repo_root)
    if base == Path("."):
        cwd = Path.cwd()
        for candidate in (cwd, *cwd.parents):
            if (candidate / _SPECS_ROOT).is_dir() or (candidate / ".git").exists():
                if candidate != cwd:
                    return candidate, candidate
                break
    return base, Path(".")


def default_state_file(repo_root: str | Path = ".") -> str:
    """Default ``STATE.md`` path (relative to ``repo_root``)."""
    probe, join = _anchor(repo_root)
    return str(join / resolve_specs_root(probe) / "STATE.md")


def default_ticket_dir(repo_root: str | Path = ".") -> str:
    """Default tickets directory (relative to ``repo_root``)."""
    probe, join = _anchor(repo_root)
    return str(join / resolve_specs_root(probe) / "tickets")


def default_spec_paths(repo_root: str | Path = ".") -> tuple[str, str]:
    """Return ``(state_file, ticket_dir)`` from a SINGLE resolved root.

    Use this whenever a command needs both defaults so the two can never
    disagree (see the module docstring's CRITICAL note).
    """
    probe, join = _anchor(repo_root)
    root = resolve_specs_root(probe)
    return str(join / root / "STATE.md"), str(join / root / "tickets")
