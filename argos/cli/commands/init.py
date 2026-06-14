"""``argos init`` — scaffold a repository into an Argos project (ARG1-002).

Invocation forms (ARG1-074 reconciles the CLI with the documented
``argos init <project>`` form):

- ``argos init`` — project name detected (git origin basename, else dir name),
  scaffolds the current directory.
- ``argos init myproject`` — optional positional sets the project name; still
  scaffolds the current directory.
- ``argos init --path /x`` / ``argos init myproject --path /x`` — scaffolds
  ``/x``. The positional is a pure alias for ``--name`` (``--name`` wins if both
  are given); it never changes the target directory.

Scaffolds, relative to the target repo root (CWD unless ``--path`` is
given):

- ``argos/specs/{STATE,PRD,ARCHITECTURE}.md`` — rendered from the
  placeholder templates shipped with the package
  (``argos/cli/templates/``, copied verbatim from the ARG1-050 / ARG1-053
  canonical templates).
- ``argos/specs/tickets/`` — created (with a ``.gitkeep`` when empty);
  **never overwritten**, even under ``--force``.
- ``argos/config.toml`` — copied from the project-config template.
- ``.argos/local.toml`` — copied from the local-config template.
- ``.gitignore`` — ensures a ``.argos/`` ignore entry (idempotent, via
  :func:`argos.cli.config.ensure_gitignore_entry`).
- the STATE.md custom git merge driver — copies the ARG1-052 driver into
  the target repo, registers ``merge.argos-state.*`` git config, and adds
  the STATE.md ``merge=argos-state`` lines to ``.gitattributes``.
- ``.git/hooks/pre-commit`` — best-effort install of the ARG1-032
  verifier-only-STATE pre-commit hook (non-fatal on failure).

**Idempotent.** A sentinel at ``.argos/.initialized`` marks a finished
init. Re-running without ``--force`` prints what it found and exits 0
without touching any file. ``--force`` re-scaffolds (overwriting the
generated spec/config files, refreshing the driver and hooks) but never
touches existing tickets.

Standard library only (ADR-001); runs under Python >= 3.9.
"""

from __future__ import annotations

import argparse
import datetime
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from argos.cli.config import ensure_gitignore_entry

# Package layout: this file is argos/cli/commands/init.py.
#   parents[0] = argos/cli/commands
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root of the installed package (source of scaffold data)
_THIS = Path(__file__).resolve()
_CLI_DIR = _THIS.parents[1]
_PKG_ROOT = _THIS.parents[3]
_TEMPLATES = _CLI_DIR / "templates"
_MERGE_DRIVER_SRC = _PKG_ROOT / "argos" / "scripts" / "state-merge-driver.sh"
_HOOK_SRC = _PKG_ROOT / "argos" / "scripts" / "hooks" / "pre-commit-state-write.sh"

# Sentinel lives under the gitignored .argos/ dir — never committed.
_SENTINEL_REL = Path(".argos") / ".initialized"

# Templates carrying {{PROJECT}} / {{PREFIX}} / {{DESC}} / {{DATE}}
# placeholders, rendered into the repo's spec tree.
_PLACEHOLDER_TEMPLATES = {
    "STATE.md.template": Path("argos") / "specs" / "STATE.md",
    "PRD.md.template": Path("argos") / "specs" / "PRD.md",
    "ARCHITECTURE.md.template": Path("argos") / "specs" / "ARCHITECTURE.md",
    # The target repo's own language/dependency/test conventions, injected
    # into every dispatched session's prompt. Scaffolded as an operator-facing
    # stub that must be filled in per repo.
    "conventions.md.template": Path("argos") / "conventions.md",
}

# Config templates copied verbatim (static defaults, no placeholders).
_COPY_TEMPLATES = {
    "config.toml.template": Path("argos") / "config.toml",
    "local.toml.template": Path(".argos") / "local.toml",
}

# Files whose presence/absence is reported on an already-initialized re-run.
_REPORT_PATHS = (
    "argos/config.toml",
    "argos/specs/STATE.md",
    "argos/specs/PRD.md",
    "argos/specs/ARCHITECTURE.md",
    ".argos/local.toml",
)

# .gitattributes lines registering the STATE.md merge driver. The flat path
# is the one that fires for a freshly-scaffolded repo (its STATE.md lives at
# argos/specs/STATE.md); the v1.0 path mirrors ARG1-052 for self-hosting.
_GITATTRIBUTES_LINES = (
    "argos/specs/STATE.md merge=argos-state",
    "argos/specs/v1.0/STATE.md merge=argos-state",
)

_HOOK_SENTINEL_OPEN = "# >>> argos pre-commit-state-write (ARG1-032) >>>"
_HOOK_SENTINEL_CLOSE = "# <<< argos pre-commit-state-write (ARG1-032) <<<"


# ---------------------------------------------------------------------------
# Project identity detection
# ---------------------------------------------------------------------------


def _detect_project_name(repo_root: Path) -> str:
    """Best-effort project name: git ``origin`` basename, else dir name.

    Per the ticket Non-goals, detection goes no further than the git
    remote, falling back to the current directory name on any failure.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        )
        url = proc.stdout.strip()
        if url:
            name = url.rstrip("/").split("/")[-1]
            if name.endswith(".git"):
                name = name[:-4]
            if name:
                return name
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return repo_root.resolve().name or "project"


def _derive_prefix(name: str) -> str:
    """Derive a 2-4 letter uppercase ticket prefix from a project name."""
    letters = re.sub(r"[^A-Za-z]", "", name).upper()
    if len(letters) >= 2:
        return letters[:4]
    return "PRJ"


def _render(text: str, *, project: str, prefix: str, desc: str, date: str) -> str:
    return (
        text.replace("{{PROJECT}}", project)
        .replace("{{PREFIX}}", prefix)
        .replace("{{DESC}}", desc)
        .replace("{{DATE}}", date)
    )


def _today() -> str:
    return datetime.date.today().isoformat()


# ---------------------------------------------------------------------------
# Git / merge-driver / hooks
# ---------------------------------------------------------------------------


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )


def _ensure_git_repo(repo_root: Path) -> bool:
    """Ensure ``repo_root`` is a git repo. Returns True if git is usable."""
    if (repo_root / ".git").exists():
        return True
    try:
        subprocess.run(
            ["git", "init", "-q", str(repo_root)],
            capture_output=True,
            text=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        sys.stderr.write(
            "argos init: warning: could not initialize a git repository "
            "(git unavailable?); skipping merge-driver registration\n"
        )
        return False


def _register_merge_driver(repo_root: Path) -> None:
    """Copy the STATE.md merge driver into the repo and register it."""
    driver_rel = Path("argos") / "scripts" / "state-merge-driver.sh"
    if _MERGE_DRIVER_SRC.is_file():
        dst = repo_root / driver_rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_MERGE_DRIVER_SRC, dst)
        os.chmod(dst, 0o755)
    driver_value = f"{driver_rel.as_posix()} %O %A %B %P %L"
    try:
        _git(repo_root, "config", "merge.argos-state.name",
             "Argos STATE.md append-mostly merge")
        _git(repo_root, "config", "merge.argos-state.driver", driver_value)
        _git(repo_root, "config", "merge.argos-state.recursive", "binary")
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        sys.stderr.write(
            "argos init: warning: could not register the merge driver "
            "(git unavailable?)\n"
        )
    _ensure_gitattributes(repo_root)


def _ensure_gitattributes(repo_root: Path) -> None:
    """Idempotently add the STATE.md ``merge=argos-state`` lines."""
    attr = repo_root / ".gitattributes"
    text = attr.read_text(encoding="utf-8") if attr.exists() else ""
    existing = set(text.splitlines())
    to_add = [line for line in _GITATTRIBUTES_LINES if line not in existing]
    if not to_add:
        return
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(line + "\n" for line in to_add)
    attr.write_text(text, encoding="utf-8")


def _install_hooks(repo_root: Path) -> None:
    """Best-effort install of the ARG1-032 pre-commit hook. Never raises."""
    try:
        if not _HOOK_SRC.is_file():
            return
        hook_rel = Path("argos") / "scripts" / "hooks" / "pre-commit-state-write.sh"
        hook_dst = repo_root / hook_rel
        hook_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(_HOOK_SRC, hook_dst)
        os.chmod(hook_dst, 0o755)

        git_dir = repo_root / ".git"
        # Only the standard layout (.git directory) is handled here; a
        # worktree's .git file points elsewhere and is left untouched.
        if not git_dir.is_dir():
            return
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        precommit = hooks_dir / "pre-commit"
        block = (
            f"{_HOOK_SENTINEL_OPEN}\n"
            f'"{hook_rel.as_posix()}" "$@" || exit $?\n'
            f"{_HOOK_SENTINEL_CLOSE}\n"
        )
        if not precommit.exists():
            precommit.write_text(f"#!/bin/sh\nset -e\n\n{block}", encoding="utf-8")
            os.chmod(precommit, 0o755)
            return
        current = precommit.read_text(encoding="utf-8")
        if _HOOK_SENTINEL_OPEN in current:
            return  # already installed; leave user content alone
        if current and not current.endswith("\n"):
            current += "\n"
        precommit.write_text(f"{current}\n{block}", encoding="utf-8")
        os.chmod(precommit, 0o755)
    except OSError:
        sys.stderr.write(
            "argos init: warning: pre-commit hook install failed "
            "(non-fatal)\n"
        )


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------


def _scaffold(repo_root: Path, args: argparse.Namespace) -> tuple[str, str]:
    project = args.name or _detect_project_name(repo_root)
    prefix = args.prefix or _derive_prefix(project)
    desc = args.desc if args.desc is not None else "(no description provided)"
    date = _today()

    specs = repo_root / "argos" / "specs"
    tickets = specs / "tickets"
    tickets.mkdir(parents=True, exist_ok=True)
    (repo_root / ".argos").mkdir(parents=True, exist_ok=True)

    # Keep an empty tickets/ tracked; never write into a non-empty one.
    if not any(tickets.iterdir()):
        (tickets / ".gitkeep").write_text("", encoding="utf-8")

    for tpl_name, out_rel in _PLACEHOLDER_TEMPLATES.items():
        src = _TEMPLATES / tpl_name
        out = repo_root / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        rendered = _render(
            src.read_text(encoding="utf-8"),
            project=project,
            prefix=prefix,
            desc=desc,
            date=date,
        )
        out.write_text(rendered, encoding="utf-8")

    for tpl_name, out_rel in _COPY_TEMPLATES.items():
        src = _TEMPLATES / tpl_name
        out = repo_root / out_rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    ensure_gitignore_entry(repo_root, ".argos/")

    if _ensure_git_repo(repo_root):
        _register_merge_driver(repo_root)
        _install_hooks(repo_root)

    sentinel = repo_root / _SENTINEL_REL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text(
        f"project: {project}\nprefix: {prefix}\ndate: {date}\n",
        encoding="utf-8",
    )
    return project, prefix


def _report_already_initialized(repo_root: Path) -> None:
    print(f"argos: already initialized at {repo_root}")
    for rel in _REPORT_PATHS:
        mark = "found" if (repo_root / rel).exists() else "missing"
        print(f"  {mark}: {rel}")
    print(
        "Re-run 'argos init --force' to overwrite scaffolded files "
        "(tickets are never touched)."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="argos init",
        description="Scaffold the current repository into an Argos project.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-scaffold, overwriting generated files (never touches tickets)",
    )
    parser.add_argument(
        "project",
        nargs="?",
        default=None,
        help=(
            "project name (positional alias for --name; the documented "
            "'argos init <project>' form). Scaffolding still targets the "
            "current directory unless --path is given. --name takes precedence "
            "if both are supplied."
        ),
    )
    parser.add_argument("--name", default=None, help="project name (default: positional, else detected)")
    parser.add_argument(
        "--prefix", default=None, help="ticket prefix (default: derived from name)"
    )
    parser.add_argument(
        "--desc", default=None, help="one-line project description"
    )
    parser.add_argument(
        "--path", default=None, help="target repo root (default: current directory)"
    )
    args = parser.parse_args(argv)

    # The positional is an alias for --name; --name wins if both are given.
    # Target directory is independent (cwd unless --path), so
    # `argos init myproject` names the project but still scaffolds cwd.
    args.name = args.name or args.project

    repo_root = Path(args.path).resolve() if args.path else Path.cwd()
    sentinel = repo_root / _SENTINEL_REL

    if sentinel.exists() and not args.force:
        _report_already_initialized(repo_root)
        return 0

    project, prefix = _scaffold(repo_root, args)

    verb = "re-initialized" if args.force else "initialized"
    print(f"Argos {verb} '{project}' (prefix {prefix}) at {repo_root}")
    print("  argos/specs/{STATE,PRD,ARCHITECTURE}.md, argos/config.toml, "
          ".argos/local.toml")
    print("  registered the STATE.md merge driver and updated .gitignore")
    print("Next: edit argos/specs/PRD.md and ARCHITECTURE.md, then "
          "'/new-ticket' to draft your first ticket.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
