"""Worktree merge-on-pass / preserve-on-fail finalizer (ARG1-023).

After a per-ticket session's verifier emits ``decision: pass`` or
``decision: pass-with-minors``, the orchestrator merges the worktree's
branch (``argos/{ticket-id}``) back to the base branch (default
``main``). On ``decision: fail`` the worktree and branch are left in
place for ARG1-013's auto-fix retry or operator inspection. On merge
conflict the merge is aborted, a blocking escalation file is written,
and the operator is notified.

This module is the library; :mod:`argos.cli.commands.worktree_finalize`
is the CLI shim that exposes ``argos worktree-finalize``.

Architectural pins (locked in the ticket's ``## Plan`` section, mirrored
here):

1. **Single-ticket primitive.** ``finalize`` operates on one ticket per
   call. Group-merge ordering is the caller's authority per
   ``agents/orchestrator.md`` §Decision authority. The orchestrator
   invokes us repeatedly in whatever order it chose; ARG1-023 takes no
   stance on it.
2. **Failed disposition — always preserve.** ``result=fail`` is a no-op
   merge: the worktree, the branch, and the base branch are untouched.
   ARG1-013's retry contract reuses the same worktree, so removal here
   would be premature. Preservation on first-failure-only is rejected:
   the spec's AC#4 is unconditional, and the orchestrator-agent doc's
   §Auto-fix retry behavior says "do not spawn a new worktree".
3. **Conflict handling — abort + escalate.** Three-way merge that
   produces conflicts is rolled back via ``git merge --abort``,
   restoring the base branch's working tree to its pre-merge state. A
   ``severity: blocking`` escalation is written; the merge does not
   partial-apply. Per ``agents/orchestrator.md`` §Escalation triggers
   item 6, merge-time semantic conflicts on file-disjoint sessions are
   the orchestrator's escalation surface — this is the writer.
4. **No dry-run.** The ticket's AC list does not require one and the
   spec is silent. ``--json`` covers post-execution machine inspection.
   YAGNI; if a future ticket needs preview, file an amendment.
5. **No worktree pruning on pass.** Per Non-goals: "No worktree
   deletion on pass". ``argos sync`` prunes merged-and-stale worktrees;
   this module does not. ``worktree_preserved`` is therefore True in
   every code path, kept as a JSON field so the orchestrator's dispatch
   log can record the decision explicitly.

ADR-001 stdlib-only. Imports limited to the lint-imports allowlist.
"""

from __future__ import annotations

import datetime
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from argos.cli import escalation
from argos.cli.worktree import (
    GitError,
    compute_branch_name,
)

__all__ = [
    "DEFAULT_BASE_BRANCH",
    "DEFAULT_ESCALATION_DIR",
    "VALID_RESULTS",
    "RESULTS_TRIGGERING_MERGE",
    "MERGE_STRATEGY_FF",
    "MERGE_STRATEGY_THREE_WAY",
    "FinalizeError",
    "InvalidResultError",
    "DirtyWorkingTreeError",
    "MissingBranchError",
    "FinalizeResult",
    "finalize",
    "find_main_repo_root",
]


DEFAULT_BASE_BRANCH = "main"
DEFAULT_ESCALATION_DIR = Path("argos/specs/escalations")

VALID_RESULTS = ("pass", "pass-with-minors", "fail")
RESULTS_TRIGGERING_MERGE = ("pass", "pass-with-minors")

MERGE_STRATEGY_FF = "ff"
MERGE_STRATEGY_THREE_WAY = "three-way"

_CONFLICT_BODY_PREFIX = "merge conflict"


class FinalizeError(Exception):
    """Base class for ``argos worktree-finalize`` errors."""


class InvalidResultError(FinalizeError, ValueError):
    """``--result`` was not one of pass / pass-with-minors / fail."""


class DirtyWorkingTreeError(FinalizeError):
    """Base branch's working tree is dirty; refuse to merge into it."""


class MissingBranchError(FinalizeError):
    """The ``argos/<ticket>`` branch does not exist."""


@dataclass(frozen=True)
class FinalizeResult:
    """The outcome of one ``finalize`` call.

    ``merge_strategy`` is ``"ff"`` or ``"three-way"`` when a merge
    occurred; ``None`` otherwise (fail path or conflict). ``conflicts``
    is True iff a three-way merge attempt produced unresolvable
    conflicts and was aborted. ``escalation_path`` is the absolute path
    of the written escalation file when ``conflicts`` is True; None
    otherwise.
    """

    ticket_id: str
    result: str
    branch: str
    base_branch: str
    merged: bool
    merge_strategy: Optional[str]
    conflicts: bool
    worktree_preserved: bool
    escalation_path: Optional[str]

    def to_json_payload(self) -> dict:
        """Render the AC#6 JSON shape.

        Keys are exactly the four required by AC#6 (``merged``,
        ``merge_strategy``, ``conflicts``, ``worktree_preserved``) plus
        diagnostic context (``ticket_id``, ``result``, ``branch``,
        ``base_branch``, ``escalation_path``) downstream consumers may
        ignore.
        """
        return {
            "ticket_id": self.ticket_id,
            "result": self.result,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "merged": self.merged,
            "merge_strategy": self.merge_strategy,
            "conflicts": self.conflicts,
            "worktree_preserved": self.worktree_preserved,
            "escalation_path": self.escalation_path,
        }


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------


def _git(
    *args: str,
    cwd: Path,
    check: bool = False,
) -> subprocess.CompletedProcess:
    """Run ``git <args>`` in ``cwd`` and return the completed process.

    ``check=False`` is the default so callers can branch on returncode;
    callers that want hard failure should set ``check=True`` and catch
    :class:`subprocess.CalledProcessError`.
    """
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def find_main_repo_root(start: Optional[Path] = None) -> Path:
    """Return the absolute path of the main worktree's working tree.

    Parses ``git worktree list --porcelain`` and returns the first
    ``worktree`` line — the main worktree by git's convention. Run from
    inside any registered worktree this still resolves to the canonical
    main one, which is where finalize must operate (branches are
    repository-scoped and the merge needs to switch the main worktree's
    HEAD).
    """
    cwd = Path(start).resolve() if start is not None else Path.cwd()
    res = _git(
        "worktree", "list", "--porcelain",
        cwd=cwd,
    )
    if res.returncode != 0:
        raise GitError(
            "not a git repository",
            stderr=res.stderr.strip(),
            returncode=res.returncode,
        )
    for line in res.stdout.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    raise GitError(
        "could not parse git worktree list output",
        stderr=res.stdout,
    )


def _branch_exists(repo_root: Path, branch: str) -> bool:
    res = _git(
        "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
        cwd=repo_root,
    )
    return res.returncode == 0


def _current_branch(repo_root: Path) -> Optional[str]:
    """Return the symbolic branch name at HEAD, or None if detached."""
    res = _git(
        "symbolic-ref", "--quiet", "--short", "HEAD",
        cwd=repo_root,
    )
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def _working_tree_clean(repo_root: Path) -> bool:
    """True iff there are no staged or unstaged changes to tracked files.

    Untracked files are deliberately excluded — ``git merge`` itself
    only refuses to merge when tracked files would be overwritten or
    when a merge is mid-flight. Untracked artifacts (registered
    sibling worktrees under ``.argos/worktrees/``, build outputs, the
    escalation we are about to write) are not dirtiness in the merge
    sense.
    """
    res = _git(
        "status", "--porcelain", "--untracked-files=no",
        cwd=repo_root,
    )
    if res.returncode != 0:
        raise GitError(
            "git status failed",
            stderr=res.stderr.strip(),
            returncode=res.returncode,
        )
    return res.stdout.strip() == ""


def _checkout(repo_root: Path, branch: str) -> None:
    res = _git("checkout", branch, cwd=repo_root)
    if res.returncode != 0:
        raise GitError(
            f"git checkout {branch} failed",
            stderr=res.stderr.strip(),
            returncode=res.returncode,
        )


def _try_ff_merge(repo_root: Path, branch: str) -> tuple[bool, str]:
    """Attempt ``git merge --ff-only <branch>``. Returns (ok, stderr)."""
    res = _git(
        "merge", "--ff-only", branch,
        cwd=repo_root,
    )
    return res.returncode == 0, res.stderr


def _try_three_way_merge(
    repo_root: Path, branch: str
) -> tuple[bool, str, str]:
    """Attempt ``git merge --no-ff --no-edit <branch>``.

    Returns ``(ok, stdout, stderr)``. On non-zero exit the working tree
    is left in mid-merge state; the caller is responsible for invoking
    ``git merge --abort`` to roll back.
    """
    res = _git(
        "merge", "--no-ff", "--no-edit", branch,
        cwd=repo_root,
    )
    return res.returncode == 0, res.stdout, res.stderr


def _abort_merge(repo_root: Path) -> None:
    """Best-effort ``git merge --abort``.

    If there is no merge in progress (already aborted by a hook
    failure, etc.), the call returns non-zero and we ignore it — the
    caller's intent is "leave base clean", and a no-op when no merge
    is in progress satisfies that.
    """
    _git("merge", "--abort", cwd=repo_root)


# ---------------------------------------------------------------------------
# escalation body composition
# ---------------------------------------------------------------------------


def _compose_conflict_body(
    *,
    ticket_id: str,
    branch: str,
    base_branch: str,
    git_stdout: str,
    git_stderr: str,
) -> str:
    """Render the conflict-escalation body.

    The four required H2 sections (Question / Context / Options
    considered / Why escalated) per the escalation schema are present
    so the file passes ``argos escalation-validate``. The body opens
    with the literal string ``merge conflict`` per AC#3.
    """
    git_block_parts = []
    if git_stdout.strip():
        git_block_parts.append(git_stdout.rstrip())
    if git_stderr.strip():
        git_block_parts.append(git_stderr.rstrip())
    git_block = "\n".join(git_block_parts) if git_block_parts else "(no output)"

    return (
        f"## Question\n"
        f"\n"
        f"{_CONFLICT_BODY_PREFIX} merging `{branch}` into `{base_branch}` "
        f"for ticket {ticket_id}: how should the operator resolve?\n"
        f"\n"
        f"## Context\n"
        f"\n"
        f"- ticket: `{ticket_id}`\n"
        f"- branch: `{branch}`\n"
        f"- base: `{base_branch}`\n"
        f"- merge strategy attempted: fast-forward (failed) → three-way (conflict)\n"
        f"- the merge has been aborted; the base branch's working tree is clean\n"
        f"- the worktree and branch are preserved for inspection\n"
        f"\n"
        f"### git output\n"
        f"\n"
        f"```\n"
        f"{git_block}\n"
        f"```\n"
        f"\n"
        f"## Options considered\n"
        f"\n"
        f"1. resolve conflicts by hand on the worktree branch and re-run "
        f"`argos worktree-finalize`\n"
        f"2. rebase the worktree branch onto the new base, re-run verification, "
        f"then finalize\n"
        f"3. abandon the worktree branch (`git branch -D {branch}`) and "
        f"re-dispatch the ticket\n"
        f"\n"
        f"## Why escalated\n"
        f"\n"
        f"Per `agents/orchestrator.md` §Escalation triggers item 6: "
        f"merge-time semantic conflicts on file-disjoint sessions require an "
        f"operator decision. The orchestrator does not auto-resolve; it routes.\n"
    )


# ---------------------------------------------------------------------------
# public surface
# ---------------------------------------------------------------------------


def finalize(
    *,
    ticket_id: str,
    result: str,
    repo_root: Optional[Path] = None,
    base_branch: str = DEFAULT_BASE_BRANCH,
    escalation_dir: Optional[Path] = None,
    now: Optional[datetime.datetime] = None,
) -> FinalizeResult:
    """Finalize one ticket's worktree per its verifier ``result``.

    Behavior is dispatched on ``result``:

    - ``"pass"`` / ``"pass-with-minors"`` → attempt to merge
      ``argos/<ticket_id>`` into ``base_branch`` (ff first, three-way
      fallback). On conflict, abort and write a blocking escalation.
    - ``"fail"`` → no-op; preserve worktree and branch.

    ``repo_root`` defaults to the **main** worktree of the enclosing
    git repository (resolved via :func:`find_main_repo_root`); the
    finalize must run there because branches are repository-scoped.

    ``escalation_dir`` defaults to ``<repo_root>/argos/specs/escalations``.

    Raises:
        InvalidResultError: ``result`` is not one of the three legal
            values.
        MissingBranchError: a merge was requested but the
            ``argos/<ticket>`` branch does not exist.
        DirtyWorkingTreeError: the base branch has uncommitted local
            changes; refusing to merge.
        GitError: a git plumbing call failed in a way the caller did
            not opt into handling (e.g. the base branch does not exist).
    """
    if result not in VALID_RESULTS:
        raise InvalidResultError(
            f"result must be one of {', '.join(VALID_RESULTS)} "
            f"(got {result!r})"
        )
    if not ticket_id:
        raise FinalizeError("ticket_id is required")

    branch = compute_branch_name(ticket_id)

    if repo_root is None:
        repo_root = find_main_repo_root()
    repo_root = Path(repo_root).resolve()
    if escalation_dir is None:
        escalation_dir = repo_root / DEFAULT_ESCALATION_DIR

    if result == "fail":
        # No-op: preserve worktree and branch. The branch may or may
        # not still exist (dispatch was a hard failure) — either way
        # the operator inspects state directly.
        return FinalizeResult(
            ticket_id=ticket_id,
            result=result,
            branch=branch,
            base_branch=base_branch,
            merged=False,
            merge_strategy=None,
            conflicts=False,
            worktree_preserved=True,
            escalation_path=None,
        )

    # Merge path: result is "pass" or "pass-with-minors".
    if not _branch_exists(repo_root, branch):
        raise MissingBranchError(
            f"branch {branch!r} does not exist in {repo_root}"
        )
    if not _branch_exists(repo_root, base_branch):
        raise GitError(
            f"base branch {base_branch!r} does not exist in {repo_root}",
            returncode=1,
        )

    starting_branch = _current_branch(repo_root)

    if not _working_tree_clean(repo_root):
        raise DirtyWorkingTreeError(
            f"base repo {repo_root} has a dirty working tree; "
            f"refusing to merge {branch} into {base_branch}"
        )

    if starting_branch != base_branch:
        _checkout(repo_root, base_branch)

    # 1. Fast-forward attempt — leaves working tree untouched on failure.
    ff_ok, _ff_stderr = _try_ff_merge(repo_root, branch)
    if ff_ok:
        return FinalizeResult(
            ticket_id=ticket_id,
            result=result,
            branch=branch,
            base_branch=base_branch,
            merged=True,
            merge_strategy=MERGE_STRATEGY_FF,
            conflicts=False,
            worktree_preserved=True,
            escalation_path=None,
        )

    # 2. Three-way merge attempt — may produce a merge commit (auto-
    #    commit triggers the pre-commit hook; STATE.md changes go
    #    through the ARG1-052 merge driver, which the install script
    #    has registered as `merge=argos-state` on the relevant paths).
    tw_ok, tw_stdout, tw_stderr = _try_three_way_merge(repo_root, branch)
    if tw_ok:
        return FinalizeResult(
            ticket_id=ticket_id,
            result=result,
            branch=branch,
            base_branch=base_branch,
            merged=True,
            merge_strategy=MERGE_STRATEGY_THREE_WAY,
            conflicts=False,
            worktree_preserved=True,
            escalation_path=None,
        )

    # 3. Conflict — abort to restore base, write a blocking escalation.
    _abort_merge(repo_root)

    body = _compose_conflict_body(
        ticket_id=ticket_id,
        branch=branch,
        base_branch=base_branch,
        git_stdout=tw_stdout,
        git_stderr=tw_stderr,
    )
    esc_path = escalation.write_escalation(
        ticket_id=ticket_id,
        severity="blocking",
        raised_by="orchestrator",
        body=body,
        dest_dir=escalation_dir,
        now=now,
    )

    return FinalizeResult(
        ticket_id=ticket_id,
        result=result,
        branch=branch,
        base_branch=base_branch,
        merged=False,
        merge_strategy=None,
        conflicts=True,
        worktree_preserved=True,
        escalation_path=str(esc_path),
    )
