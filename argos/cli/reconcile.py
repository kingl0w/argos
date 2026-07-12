"""Shared reconciliation logic for ``argos sync`` (ARG1-004).

``argos sync`` performs three independent reconciliations between the
canonical spec tree and the world around it:

1. **ticket files ↔ GitHub Issues** (:func:`reconcile_issues`) — re-render the
   bodies of *existing* Issues from their ticket markdown. This is the v0.5
   ``argos-sync.sh push`` behaviour (script since retired) exposed for local
   invocation. Issue
   *creation* stays CI's job (a ticket-file Non-goal), so a ticket with no
   matching Issue is skipped, never created. This is the only phase that can
   touch the network; it is skipped wholesale when ``gh`` is unavailable or
   the operator passes ``--no-issues``.
2. **STATE.md ↔ git** (:func:`reconcile_state_git`) — every ticket recorded
   under ``## Done this cycle`` must trace to a commit on the first-parent
   history of the main branch. A done-but-unmerged ticket is reported as a
   ``MISMATCH`` and the operator decides; sync never auto-corrects STATE.md
   (a Non-goal).
3. **worktree pruning** (:func:`reconcile_worktrees`) — worktrees under
   ``.argos/worktrees/`` whose branch has been merged into main *and* deleted
   from ``origin`` are stale build artifacts; sync removes them.

Each function returns a :class:`PhaseResult`. The command layer
(:mod:`argos.cli.commands.sync`) renders them and decides the exit code.

ADR-001 / ADR-002: Python ≥3.9, standard library only. The only outside
process is ``git`` (and ``gh`` for the issues phase), invoked via
:mod:`subprocess` — no third-party imports.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from argos.cli.queue import TICKET_ID_RE
from argos.cli.state_parser import parse as parse_state

__all__ = [
    "STATUS_OK",
    "STATUS_WOULD_FIX",
    "STATUS_FIXED",
    "STATUS_MISMATCH",
    "PhaseResult",
    "ReconcileError",
    "IssueBackend",
    "GhIssueBackend",
    "DEFAULT_MAIN_REF",
    "DONE_SECTION",
    "WORKTREES_SUBDIR",
    "reconcile_state_git",
    "reconcile_worktrees",
    "reconcile_issues",
]


# Phase status vocabulary. ``argos sync --dry-run`` renders OK / WOULD-FIX /
# MISMATCH (AC#1); a real run renders FIXED in place of WOULD-FIX for the
# phases it actually applied.
STATUS_OK = "OK"
STATUS_WOULD_FIX = "WOULD-FIX"
STATUS_FIXED = "FIXED"
STATUS_MISMATCH = "MISMATCH"

DEFAULT_MAIN_REF = "main"
DONE_SECTION = "Done this cycle"
WORKTREES_SUBDIR = (".argos", "worktrees")

_DONE_HEADING_RE = re.compile(rf"^## {re.escape(DONE_SECTION)}\s*$")
_NEXT_HEADING_RE = re.compile(r"^## ")
_BRANCH_PREFIX = "argos/"


class ReconcileError(Exception):
    """An operational failure (git plumbing, malformed input) in a phase."""


@dataclass
class PhaseResult:
    """The outcome of one reconciliation phase.

    ``status`` is one of the module-level ``STATUS_*`` constants.
    ``summary`` is a one-line human description for the status table.
    ``details`` carries per-item lines (offending ticket ids, pruned paths)
    that the command layer may surface to stderr (for ``MISMATCH``) or in
    verbose output. ``is_mismatch`` lets the command decide the exit code
    without string-matching ``status``.
    """

    name: str
    status: str
    summary: str
    details: list = field(default_factory=list)

    @property
    def is_mismatch(self) -> bool:
        return self.status == STATUS_MISMATCH


# ---------------------------------------------------------------------------
# git plumbing
# ---------------------------------------------------------------------------


def _git(args: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )


def _git_check(args: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess:
    res = _git(args, cwd=cwd)
    if res.returncode != 0:
        raise ReconcileError(
            f"git {' '.join(args)} failed (rc={res.returncode}): "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    return res


def _ref_exists(repo_root: Path, ref: str) -> bool:
    res = _git(["rev-parse", "--verify", "--quiet", ref], cwd=repo_root)
    return res.returncode == 0


# ---------------------------------------------------------------------------
# phase 2: STATE.md ↔ git
# ---------------------------------------------------------------------------


def _done_section_ticket_ids(text: str) -> list:
    """Ticket ids of ``argos:entry`` blocks inside ``## Done this cycle``.

    Returned in source order with duplicates removed (a ticket can legitimately
    appear once; a correction block referencing a prior id would repeat it).
    Bounded to the exact ``## Done this cycle`` heading so inline historical
    archives such as ``## Done this cycle (ARG1-001)`` are not picked up
    (mirrors cycle_close / clean_queue heading discipline).
    """
    lines = text.splitlines()
    heading_idx = -1
    for idx, line in enumerate(lines):
        if _DONE_HEADING_RE.match(line):
            heading_idx = idx
            break
    if heading_idx == -1:
        return []
    next_idx = len(lines)
    for idx in range(heading_idx + 1, len(lines)):
        if _NEXT_HEADING_RE.match(lines[idx]):
            next_idx = idx
            break

    ordered: list = []
    seen: set = set()
    for block in parse_state(text):
        if heading_idx < (block.start_line - 1) < next_idx:
            if block.ticket not in seen:
                seen.add(block.ticket)
                ordered.append(block.ticket)
    return ordered


def _first_parent_subjects(repo_root: Path, main_ref: str) -> list:
    """``(sha, subject)`` pairs along ``git log --first-parent <main_ref>``."""
    res = _git(
        ["log", "--first-parent", main_ref, "--format=%H%x1f%s"],
        cwd=repo_root,
    )
    if res.returncode != 0:
        raise ReconcileError(
            f"could not read 'git log --first-parent {main_ref}': "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    pairs: list = []
    for line in res.stdout.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x1f")
        pairs.append((sha, subject))
    return pairs


def reconcile_state_git(
    *,
    state_file: Path,
    repo_root: Path,
    main_ref: str = DEFAULT_MAIN_REF,
) -> PhaseResult:
    """Check that every ``## Done this cycle`` ticket traces to ``main``.

    A ticket is "traced" iff its id appears as a whole word in the subject of
    some commit on ``git log --first-parent <main_ref>`` — covering both
    ``merge: ARG1-NNN ...`` merge commits and fast-forwarded ticket commits.
    A done-this-cycle ticket with no such commit is a ``MISMATCH``; sync
    reports it and refuses to auto-correct STATE.md (ticket Non-goal). This
    function never mutates anything.
    """
    state_path = Path(state_file)
    if not state_path.exists():
        raise ReconcileError(f"state file not found: {state_path}")

    ticket_ids = _done_section_ticket_ids(state_path.read_text(encoding="utf-8"))
    if not ticket_ids:
        return PhaseResult(
            name="state-git",
            status=STATUS_OK,
            summary="no '## Done this cycle' entries to reconcile",
        )

    subjects = _first_parent_subjects(repo_root, main_ref)

    missing: list = []
    for tid in ticket_ids:
        token = re.compile(rf"\b{re.escape(tid)}\b")
        if not any(token.search(subject) for _, subject in subjects):
            missing.append(tid)

    if missing:
        details = [
            f"{tid} listed in '## Done this cycle' but no merge commit found "
            f"in 'git log --first-parent {main_ref}'"
            for tid in missing
        ]
        return PhaseResult(
            name="state-git",
            status=STATUS_MISMATCH,
            summary=(
                f"{len(missing)} done-this-cycle ticket(s) absent from "
                f"'git log --first-parent {main_ref}': {', '.join(missing)}"
            ),
            details=details,
        )

    return PhaseResult(
        name="state-git",
        status=STATUS_OK,
        summary=(
            f"{len(ticket_ids)} done-this-cycle ticket(s) trace to "
            f"'git log --first-parent {main_ref}'"
        ),
    )


# ---------------------------------------------------------------------------
# phase 3: worktree pruning
# ---------------------------------------------------------------------------


@dataclass
class _Worktree:
    path: Path
    branch: Optional[str]  # short branch name, or None if detached


def _parse_worktree_list(stdout: str) -> list:
    """Parse ``git worktree list --porcelain`` into :class:`_Worktree` records."""
    entries: list = []
    cur_path: Optional[Path] = None
    cur_branch: Optional[str] = None
    cur_detached = False

    def flush() -> None:
        nonlocal cur_path, cur_branch, cur_detached
        if cur_path is not None:
            entries.append(
                _Worktree(path=cur_path, branch=None if cur_detached else cur_branch)
            )
        cur_path, cur_branch, cur_detached = None, None, False

    for line in stdout.splitlines():
        if line.startswith("worktree "):
            flush()
            cur_path = Path(line[len("worktree "):]).resolve()
        elif line.startswith("branch "):
            ref = line[len("branch "):].strip()
            if ref.startswith("refs/heads/"):
                cur_branch = ref[len("refs/heads/"):]
            else:
                cur_branch = ref
        elif line.strip() == "detached":
            cur_detached = True
    flush()
    return entries


def _has_origin_remote(repo_root: Path) -> bool:
    res = _git(["remote"], cwd=repo_root)
    if res.returncode != 0:
        return False
    return "origin" in res.stdout.split()


def _is_merged(repo_root: Path, branch: str, main_ref: str) -> bool:
    """True iff ``branch`` tip is an ancestor of ``main_ref`` (fully merged)."""
    res = _git(
        ["merge-base", "--is-ancestor", f"refs/heads/{branch}", main_ref],
        cwd=repo_root,
    )
    return res.returncode == 0


def _branch_deleted_on_origin(repo_root: Path, branch: str, has_origin: bool) -> bool:
    """True iff the branch is gone from ``origin``.

    When no ``origin`` remote is configured the signal degrades to "trivially
    deleted" — a local-only repo has no upstream to retain the branch, so a
    merged worktree there is just as stale. Uses the existing remote-tracking
    ref; no implicit fetch is performed, keeping the phase offline-safe (the
    operator runs ``git fetch --prune`` when reconciling cross-machine state).
    """
    if not has_origin:
        return True
    return not _ref_exists(repo_root, f"refs/remotes/origin/{branch}")


def _prune_worktree(repo_root: Path, wt: _Worktree) -> None:
    """Remove a worktree directory and its merged branch.

    ``git worktree remove --force`` deregisters and deletes the directory even
    if it holds untracked artifacts; ``git branch -D`` drops the now-merged
    branch; ``git worktree prune`` clears any leftover administrative metadata.
    """
    res = _git(["worktree", "remove", "--force", str(wt.path)], cwd=repo_root)
    if res.returncode != 0:
        raise ReconcileError(
            f"could not remove worktree {wt.path}: "
            f"{res.stderr.strip() or res.stdout.strip()}"
        )
    if wt.branch:
        # Best-effort: the branch may already be gone, which is fine.
        _git(["branch", "-D", wt.branch], cwd=repo_root)
    _git(["worktree", "prune"], cwd=repo_root)


def reconcile_worktrees(
    *,
    repo_root: Path,
    main_ref: str = DEFAULT_MAIN_REF,
    dry_run: bool = False,
) -> PhaseResult:
    """Prune merged-and-deleted worktrees under ``.argos/worktrees/``.

    A worktree is prunable iff its branch is fully merged into ``main_ref``
    *and* deleted from ``origin`` (see :func:`_branch_deleted_on_origin`).
    The main worktree and any worktree outside ``.argos/worktrees/`` are never
    touched. ``dry_run`` reports the candidates without removing them.
    """
    repo_root = Path(repo_root).resolve()
    res = _git_check(["worktree", "list", "--porcelain"], cwd=repo_root)
    worktrees = _parse_worktree_list(res.stdout)

    worktrees_root = repo_root.joinpath(*WORKTREES_SUBDIR).resolve()
    has_origin = _has_origin_remote(repo_root)

    prunable: list = []
    for wt in worktrees:
        # Only consider worktrees strictly under .argos/worktrees/.
        try:
            wt.path.relative_to(worktrees_root)
        except ValueError:
            continue
        if wt.path == worktrees_root:
            continue
        if not wt.branch or not wt.branch.startswith(_BRANCH_PREFIX):
            continue
        if not _is_merged(repo_root, wt.branch, main_ref):
            continue
        if not _branch_deleted_on_origin(repo_root, wt.branch, has_origin):
            continue
        prunable.append(wt)

    if not prunable:
        return PhaseResult(
            name="worktrees",
            status=STATUS_OK,
            summary="no stale worktrees under .argos/worktrees/ to prune",
        )

    rel_paths = [str(wt.path.relative_to(repo_root)) for wt in prunable]

    if dry_run:
        return PhaseResult(
            name="worktrees",
            status=STATUS_WOULD_FIX,
            summary=f"{len(prunable)} stale worktree(s) to prune",
            details=rel_paths,
        )

    for wt in prunable:
        _prune_worktree(repo_root, wt)

    return PhaseResult(
        name="worktrees",
        status=STATUS_FIXED,
        summary=f"pruned {len(prunable)} stale worktree(s)",
        details=rel_paths,
    )


# ---------------------------------------------------------------------------
# phase 1: ticket files ↔ GitHub Issues
# ---------------------------------------------------------------------------


_TEMPLATE_SUFFIX = ".template"
_H1_RE = re.compile(r"^#\s+(?P<title>.*\S)\s*$")


class IssueBackend:
    """Interface for the GitHub Issue side of the issues reconciliation.

    The default :class:`GhIssueBackend` shells to ``gh``. Tests inject a fake
    so the phase is exercised without network access or a real GitHub repo.
    """

    def available(self) -> bool:  # pragma: no cover - interface
        raise NotImplementedError

    def find_issue(self, ticket_id: str) -> Optional[int]:  # pragma: no cover
        raise NotImplementedError

    def update_issue(self, number: int, title: str, body_file: Path) -> None:  # pragma: no cover
        raise NotImplementedError


class GhIssueBackend(IssueBackend):
    """``gh``-shelling implementation of :class:`IssueBackend`.

    Mirrors the retired v0.5 ``argos-sync.sh``: existing Issues are located by a
    word-boundary match on the ticket id in the Issue title (label
    ``argos-ticket``) and their body/title re-rendered from the ticket file.
    """

    LABEL = "argos-ticket"

    def __init__(self, *, repo_root: Path) -> None:
        self._repo_root = Path(repo_root)

    def _gh(self, args: Sequence[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["gh", *args],
            cwd=str(self._repo_root),
            capture_output=True,
            text=True,
            check=False,
        )

    def available(self) -> bool:
        if shutil.which("gh") is None:
            return False
        return self._gh(["auth", "status"]).returncode == 0

    def find_issue(self, ticket_id: str) -> Optional[int]:
        res = self._gh(
            [
                "issue", "list",
                "--label", self.LABEL,
                "--state", "all",
                "--limit", "500",
                "--search", ticket_id,
                "--json", "number,title",
            ]
        )
        if res.returncode != 0:
            raise ReconcileError(
                f"gh issue list failed for {ticket_id}: {res.stderr.strip()}"
            )
        token = re.compile(rf"\b{re.escape(ticket_id)}\b")
        try:
            rows = json.loads(res.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise ReconcileError(f"gh returned non-JSON output: {exc}") from exc
        for row in rows:
            if token.search(row.get("title", "")):
                return int(row["number"])
        return None

    def update_issue(self, number: int, title: str, body_file: Path) -> None:
        res = self._gh(
            [
                "issue", "edit", str(number),
                "--title", title,
                "--body-file", str(body_file),
            ]
        )
        if res.returncode != 0:
            raise ReconcileError(
                f"gh issue edit #{number} failed: {res.stderr.strip()}"
            )


def _ticket_files(tickets_dir: Path) -> list:
    if not tickets_dir.is_dir():
        return []
    return sorted(
        p
        for p in tickets_dir.glob("*.md")
        if not p.name.endswith(_TEMPLATE_SUFFIX)
    )


def _ticket_id_of(path: Path) -> Optional[str]:
    stem = path.name[: -len(".md")] if path.name.endswith(".md") else path.name
    head = stem.split("-")
    # Filenames look like ARG1-004-argos-sync; reassemble the id prefix.
    if len(head) >= 2:
        candidate = f"{head[0]}-{head[1]}"
        if TICKET_ID_RE.match(candidate):
            return candidate
    return None


def _ticket_title_of(path: Path, ticket_id: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _H1_RE.match(line)
        if m:
            return m.group("title")
    return ticket_id


def reconcile_issues(
    *,
    tickets_dir: Path,
    repo_root: Path,
    dry_run: bool = False,
    backend: Optional[IssueBackend] = None,
    skip: bool = False,
) -> PhaseResult:
    """Re-render existing GitHub Issue bodies from ticket markdown.

    Update-only: a ticket whose Issue does not yet exist is left alone (Issue
    creation is CI's job — a ticket Non-goal). The phase is reported ``OK``
    with a "skipped" note and performs **zero** ``gh`` invocations when
    ``skip`` is set (the ``--no-issues`` flag) or the backend is unavailable —
    this is what keeps ``argos sync --no-issues`` fully offline.
    """
    if skip:
        return PhaseResult(
            name="issues",
            status=STATUS_OK,
            summary="skipped (--no-issues)",
        )

    if backend is None:
        backend = GhIssueBackend(repo_root=Path(repo_root))

    if not backend.available():
        return PhaseResult(
            name="issues",
            status=STATUS_OK,
            summary="skipped (gh unavailable or not authenticated)",
        )

    tickets = _ticket_files(Path(tickets_dir))
    targets: list = []  # (ticket_id, title, path, issue_number)
    for path in tickets:
        tid = _ticket_id_of(path)
        if tid is None:
            continue
        number = backend.find_issue(tid)
        if number is None:
            continue  # Non-goal: do not create missing Issues.
        targets.append((tid, _ticket_title_of(path, tid), path, number))

    if not targets:
        return PhaseResult(
            name="issues",
            status=STATUS_OK,
            summary="no existing Issues to re-render",
        )

    ids = [t[0] for t in targets]
    if dry_run:
        return PhaseResult(
            name="issues",
            status=STATUS_WOULD_FIX,
            summary=f"{len(targets)} existing Issue(s) to re-render",
            details=ids,
        )

    for tid, title, path, number in targets:
        backend.update_issue(number, title, path)

    return PhaseResult(
        name="issues",
        status=STATUS_FIXED,
        summary=f"re-rendered {len(targets)} existing Issue(s)",
        details=ids,
    )
