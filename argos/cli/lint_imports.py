"""Stdlib-only import-allowlist linter (``argos lint-imports``).

Walks ``.py`` files under a given root, verifies that every ``import`` /
``from`` statement references either a stdlib module from the ADR-001
§Decision item 1 allowlist, the ``__future__`` pseudo-module (per
ARG1-062), or an internal ``argos`` submodule. Exits 0 if all imports
pass; exits 1 with one stderr line per violation otherwise.

The canonical violation format — the contract downstream tooling may
grep — is::

    lint-imports: <relpath>:<line>: forbidden import <name>

Missing-path errors emit::

    lint-imports: <path>: not found

See ``argos/specs/decisions/ADR-001-cli-language.md`` §Decision for the
runtime stdlib-only mandate, and ``argos/specs/v1.0/decisions/ADR-002-ac-harness-portability.md``
§1 for the AC-tooling extension.

Standard library only — no external runtime dependencies.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

__all__ = [
    "STDLIB_ALLOWLIST",
    "lint_file",
    "lint_tree",
    "main",
]


# ADR-001 §Decision item 1 — stdlib-only allowlist + the ``__future__``
# pseudo-module + the internal ``argos`` package. The literal is the
# source of truth: any expansion requires both an ADR-001 amendment and
# a literal update. That coupling is intentional.
#
# Members fall into three groups:
#   - ADR-001 §Pros (Option A) enumerated subset — the floor.
#   - Additional stdlib modules already in use across argos/ at v1.0.
#   - The pseudo-module __future__ and the internal package argos.
STDLIB_ALLOWLIST: frozenset = frozenset({
    # ADR-001 §Pros enumerated subset.
    "argparse",
    "re",
    "dataclasses",
    "pathlib",
    "json",
    "datetime",
    # Additional stdlib top-level packages used by shipped argos modules.
    "ast",
    "fcntl",
    "hashlib",
    "http",
    "io",
    "os",
    "random",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "tempfile",
    "textwrap",
    "threading",
    "time",
    "tomllib",
    "typing",
    "unittest",
    "urllib",
    # Pseudo-module — ADR-001 §Decision item 1 (PEP 563 stringified
    # annotations) requires `from __future__ import annotations`.
    "__future__",
    # Internal package.
    "argos",
})


def _top_level(name: str) -> str:
    return name.split(".")[0]


def _format_relpath(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when ``root`` is a directory.

    For a file root the linter only ever inspects the single file, so
    ``relpath`` is simply the file's name. For a directory root, paths
    are emitted relative to that directory so output stays grep-friendly
    regardless of how deep the user pointed.
    """
    if root.is_dir():
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
    return path.name


def lint_file(path: Path, root: Path) -> list:
    """Return a list of ``(relpath, lineno, name)`` violations for ``path``.

    A relative ``ImportFrom`` (``from . import foo``) is treated as
    internal — its top-level package is the current package, which is
    always inside ``argos`` for this codebase.

    Files that fail to parse as Python return an empty list; the linter
    is concerned with import allowlisting only, not with syntactic
    well-formedness of the broader tree.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError:
        return []

    rel = _format_relpath(path, root)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = _top_level(alias.name)
                if top not in STDLIB_ALLOWLIST:
                    violations.append((rel, node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            mod = node.module or ""
            top = _top_level(mod)
            if top not in STDLIB_ALLOWLIST:
                violations.append((rel, node.lineno, mod or "<empty>"))
    return violations


def _under_fixtures(path: Path, root: Path) -> bool:
    """True iff ``path`` sits below a ``fixtures`` directory under ``root``.

    Test fixtures are deliberately synthetic — some carry forbidden imports
    on purpose (the AC#4 fixture imports ``requests``). The recursive walk
    skips any subtree whose path component (below ``root``) is named
    ``fixtures``. The skip does not apply when ``root`` itself names the
    fixtures subtree: pointing the linter explicitly at a fixtures
    directory means "I want this linted."
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False
    return any(part == "fixtures" for part in rel.parent.parts)


def lint_tree(root: Path) -> list:
    """Walk ``root`` recursively and aggregate per-file violations.

    The walk visits every ``.py`` file under ``root`` in sorted order so
    the violation stream is deterministic. ``root`` may itself be a
    file, in which case only that file is linted. Test-fixture subtrees
    (any descendant of a directory named ``fixtures``) are skipped per
    :func:`_under_fixtures`.
    """
    if root.is_file():
        return lint_file(root, root)
    out = []
    for path in sorted(root.rglob("*.py")):
        if _under_fixtures(path, root):
            continue
        out.extend(lint_file(path, root))
    return out


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="argos lint-imports",
        description=(
            "Verify every `import` / `from` statement under <root> references "
            "either a stdlib module from the ADR-001 allowlist, `__future__`, "
            "or an internal `argos` submodule."
        ),
    )
    parser.add_argument(
        "root",
        help="directory or `.py` file to lint",
    )
    return parser


def main(argv: list) -> int:
    parser = _build_argparser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 2

    root = Path(args.root)
    if not root.exists():
        sys.stderr.write(f"lint-imports: {args.root}: not found\n")
        return 1

    violations = lint_tree(root)
    if violations:
        for relpath, line, name in violations:
            sys.stderr.write(
                f"lint-imports: {relpath}:{line}: forbidden import {name}\n"
            )
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
