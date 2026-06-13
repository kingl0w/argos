"""Merge-aware independence detection (ARG1-066, superseding ARG1-021).

Implements the v1.0 independence criterion specified by:

- ``argos/specs/v1.0/ARCHITECTURE.md`` §Components/Parallel Session Manager
  / Independence detection (merge-dryrun analysis)
- ``argos/specs/v1.0/agents/orchestrator.md`` §Parallel dispatch behavior
- ``argos/specs/v1.0/tickets/ARG1-066-merge-aware-independence.md`` §Goal
- ``argos/specs/v1.0/decisions/ESC-ARG1-021-independence-criterion.md`` (the
  ratified decision: dynamic dry-run merge, not static ``.gitattributes``
  inspection and not a carve-out allowlist).

**Criterion.** Two tickets A and B are independent iff:

1. Neither lists the other in ``depends_on:`` ticket frontmatter. This is the
   cheap first-pass check and short-circuits before any merge.
2. The dry-run ``git merge --no-commit --no-ff`` of one ticket branch onto the
   other — in *both* directions, in a clean throwaway staging worktree —
   completes without conflicts. The branch for ticket ``ARG1-NNN`` is
   ``argos/ARG1-NNN`` (:func:`compute_branch_name`).

The dry-run subsumes both shared-file patterns the strict criterion got wrong:
``argos/cli/__main__.py`` (default ``text`` driver, clean via the keep-both
registration pattern) and ``argos/specs/v1.0/STATE.md`` (the ARG1-052 custom
merge driver). It exercises the *actual* configured merge — the staging worktree
inherits ``.gitattributes`` and shares the repo's ``merge.*.driver`` config — so
no static heuristic or allowlist is needed.

**Lifecycle / degraded-but-correct fallback.** The merge path requires both
branches to exist with commits. When a pair's branches do not exist, or no git
repository is reachable, the criterion degrades to ARG1-021's strict file-set
disjointness over the declared ``files_touched:`` sets — conservative-correct
per ARCHITECTURE.md §Invariants line 274. The merge path is therefore *opt-in*
at the API layer: :func:`is_independent` / :func:`partition` are pure-static
unless handed a ``staging`` (or ``repo_root``). ARG1-022's
``dispatch.partition(loaded)`` call (no extra argument, plan time, no branches)
keeps its static behavior unchanged; the ``argos independence`` CLI auto-enables
the merge path against whatever branches actually exist.

**What this module still does NOT model.**

- No directory-prefix overlap heuristics or import-graph analysis. Content-level
  conflicts on file-disjoint diffs are caught downstream (verifier / merge
  time), per orchestrator.md §Parallel dispatch.
- No dynamic re-evaluation mid-batch.

Standard library only — :mod:`re`, :mod:`json`, :mod:`pathlib`,
:mod:`dataclasses`, :mod:`typing`, plus :mod:`subprocess` / :mod:`tempfile` /
:mod:`atexit` / :mod:`signal` / :mod:`shutil` / :mod:`os` for the git dry-run
plumbing (ADR-001 / ADR-002; subprocess-to-git is the contract).
"""

from __future__ import annotations

import atexit
import os
import re
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

__all__ = [
    "IndependenceError",
    "TicketParseError",
    "TicketNotFoundError",
    "MissingFilesTouchedError",
    "GitError",
    "Ticket",
    "PairResult",
    "MergeStagingArea",
    "compute_branch_name",
    "branch_commit",
    "find_repo_root",
    "load_ticket",
    "find_ticket_path",
    "is_independent",
    "partition",
    "DEFAULT_TICKET_DIR",
    "BRANCH_PREFIX",
]


DEFAULT_TICKET_DIR = "argos/specs/v1.0/tickets"

# Canonical ticket-branch prefix, mirroring ``argos.cli.worktree.BRANCH_PREFIX``
# (kept local so the two modules stay decoupled, same discipline as
# ``_TICKET_ID_RE`` below).
BRANCH_PREFIX = "argos"


# Frontmatter delimiter — three dashes on their own line per ADR-002 §1.
_FRONTMATTER_DELIM_RE = re.compile(r"^---\s*$")

# A top-level frontmatter key: alphanumeric/underscore/dash, ``:``, then
# either end-of-line (block-sequence value) or whitespace + value.
_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:(?:\s+(?P<inline>.+))?\s*$")

# A block-sequence item: any indentation, then ``- item``.
_FM_BLOCK_ITEM_RE = re.compile(r"^\s+-\s+(?P<item>.+?)\s*$")

# A flow-style sequence: ``[a, b, c]``. Items are comma-separated with
# optional whitespace; quotes around items are tolerated and stripped.
_FLOW_SEQ_RE = re.compile(r"^\[(?P<body>.*)\]\s*$")

# A ``## Plan`` heading — H2 whose text is exactly ``Plan``.
_PLAN_HEADING_RE = re.compile(r"^##\s+Plan\s*$")
# Any H2 heading; used to bound the Plan section.
_NEXT_H2_RE = re.compile(r"^##\s")

# In-Plan ``files_touched:`` opener. Permits leading indentation so the
# field can appear inside a sub-bullet, but the canonical form is at
# column zero.
_FILES_TOUCHED_OPENER_RE = re.compile(r"^(?P<indent>\s*)files_touched\s*:\s*(?P<inline>.*)$")

# Block-sequence item under ``files_touched:`` — must be indented strictly
# deeper than the opener line. Captures the indent length so we can
# detect when the sequence ends.
_PLAN_BLOCK_ITEM_RE = re.compile(r"^(?P<indent>\s+)-\s+(?P<item>.+?)\s*$")

# Ticket id shape — uppercase letters, optional digits, dash, digits.
# Mirrors ``argos.cli.queue.TICKET_ID_RE`` (kept local so the modules do
# not couple).
_TICKET_ID_RE = re.compile(r"^[A-Z]+\d*-\d+$")


class IndependenceError(Exception):
    """Base class for independence-detection errors."""


class TicketParseError(IndependenceError):
    """A ticket file could not be parsed as a ticket.

    Carries ``ticket_id`` so callers can name the offending ticket in
    operator-facing diagnostics.
    """

    def __init__(self, ticket_id: str, reason: str) -> None:
        self.ticket_id = ticket_id
        self.reason = reason
        super().__init__(f"{ticket_id}: {reason}")


class TicketNotFoundError(IndependenceError):
    """No ticket file matches the requested ticket id."""

    def __init__(self, ticket_id: str, ticket_dir: Path) -> None:
        self.ticket_id = ticket_id
        self.ticket_dir = ticket_dir
        super().__init__(
            f"ticket not found: {ticket_id} (looked in {ticket_dir})"
        )


class GitError(IndependenceError):
    """A git subprocess returned non-zero where success was required.

    Raised only by the merge-dryrun plumbing (staging-worktree setup /
    teardown). Pair-level merge *conflicts* are an expected outcome, not an
    error, and are reported as ``dependent`` — this is for the
    infrastructure-failed case (cannot create the staging worktree, cannot
    resolve a ref that was supposed to exist, etc.).
    """

    def __init__(self, message: str, *, stderr: str = "", returncode: int = 1) -> None:
        super().__init__(message)
        self.stderr = stderr
        self.returncode = returncode


class MissingFilesTouchedError(TicketParseError):
    """A ticket's Plan section is present but lacks ``files_touched:``.

    The error message contains the literal substring
    ``missing files_touched`` so AC text can grep for it without coupling
    to the exact phrasing.
    """

    def __init__(self, ticket_id: str) -> None:
        super().__init__(
            ticket_id, "missing files_touched in ## Plan section"
        )


@dataclass(frozen=True)
class Ticket:
    """A ticket as far as the independence detector is concerned.

    Only the three fields the criterion consumes are loaded:
    ``ticket_id``, ``depends_on``, and ``files_touched``. Other ticket
    content (Intent, ACs, Plan body) is not modeled.
    """

    ticket_id: str
    path: Path
    depends_on: tuple[str, ...]
    files_touched: tuple[str, ...]


@dataclass(frozen=True)
class PairResult:
    """The result of comparing two tickets for independence.

    Returned by :func:`is_independent` so callers can render both the
    boolean answer and the human-readable reason without re-running the
    check. ``reason`` is empty when ``independent`` is ``True``.
    """

    a: str
    b: str
    independent: bool
    reason: str = ""
    shared_files: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Ticket file location + parsing
# ---------------------------------------------------------------------------


def find_ticket_path(ticket_id: str, ticket_dir: str | Path = DEFAULT_TICKET_DIR) -> Path:
    """Return the on-disk path for ``ticket_id`` under ``ticket_dir``.

    Tickets are named ``{ticket_id}-{slug}.md`` (precedent: every ticket
    under ``argos/specs/v1.0/tickets/``); a bare ``{ticket_id}.md`` is
    also accepted for synthetic test fixtures.
    """
    tdir = Path(ticket_dir)
    candidates = sorted(tdir.glob(f"{ticket_id}*.md"))
    candidates = [
        p for p in candidates
        if p.stem == ticket_id or p.stem.startswith(f"{ticket_id}-")
    ]
    if not candidates:
        raise TicketNotFoundError(ticket_id, tdir)
    if len(candidates) > 1:
        raise TicketParseError(
            ticket_id,
            "multiple ticket files match: "
            + ", ".join(p.name for p in candidates),
        )
    return candidates[0]


def _parse_flow_sequence(body: str) -> list[str]:
    """Parse a flow-style sequence body — the contents between ``[`` and ``]``.

    Items are comma-separated. Surrounding whitespace and matched single
    or double quotes around each item are stripped. Empty body returns
    an empty list.
    """
    body = body.strip()
    if not body:
        return []
    items: list[str] = []
    for raw in body.split(","):
        item = raw.strip()
        if (
            len(item) >= 2
            and item[0] == item[-1]
            and item[0] in ("'", '"')
        ):
            item = item[1:-1]
        if item:
            items.append(item)
    return items


def _parse_frontmatter_depends_on(text: str) -> list[str]:
    """Return the ``depends_on`` ticket ids from a ticket file's frontmatter.

    Returns an empty list when the field is absent or the file has no
    frontmatter. Tolerates both block-sequence form (canonical for
    ADR-002) and flow-style form ``[A, B]`` (the literal example used in
    ARG1-021 AC#3). Other YAML constructs are not interpreted.
    """
    lines = text.splitlines()
    if not lines or not _FRONTMATTER_DELIM_RE.match(lines[0]):
        return []

    # Find the closing delimiter.
    end = -1
    for idx in range(1, len(lines)):
        if _FRONTMATTER_DELIM_RE.match(lines[idx]):
            end = idx
            break
    if end == -1:
        return []

    idx = 1
    while idx < end:
        line = lines[idx]
        if not line.strip() or line.lstrip().startswith("#"):
            idx += 1
            continue
        m = _FM_KEY_RE.match(line)
        if not m or m.group(1) != "depends_on":
            idx += 1
            continue
        inline = m.group("inline")
        if inline is not None:
            inline = inline.strip()
            if not inline:
                return []
            flow = _FLOW_SEQ_RE.match(inline)
            if flow:
                return _parse_flow_sequence(flow.group("body"))
            # Inline scalar — single ticket id (rare; tolerated).
            return [inline]
        # Block sequence: collect indented ``- item`` lines until a non
        # block-item line.
        items: list[str] = []
        cursor = idx + 1
        while cursor < end:
            sub = lines[cursor]
            if not sub.strip():
                cursor += 1
                continue
            mi = _FM_BLOCK_ITEM_RE.match(sub)
            if not mi:
                break
            items.append(mi.group("item").strip())
            cursor += 1
        return items

    return []


def _extract_plan_section(text: str) -> str | None:
    """Return the body of the ``## Plan`` section, or ``None`` if absent.

    The Plan section runs from the line after ``## Plan`` up to (but not
    including) the next ``## `` heading or end-of-file.
    """
    lines = text.splitlines()
    start = -1
    for idx, line in enumerate(lines):
        if _PLAN_HEADING_RE.match(line):
            start = idx + 1
            break
    if start == -1:
        return None
    end = len(lines)
    for idx in range(start, len(lines)):
        if _NEXT_H2_RE.match(lines[idx]):
            end = idx
            break
    return "\n".join(lines[start:end])


def _parse_plan_files_touched(plan_body: str) -> list[str] | None:
    """Return the ``files_touched:`` list from a Plan section body.

    Returns ``None`` if the field is absent. An empty list is a valid
    return value (a ticket may declare no files touched, e.g. a spec-only
    ticket).
    """
    lines = plan_body.splitlines()
    for idx, line in enumerate(lines):
        m = _FILES_TOUCHED_OPENER_RE.match(line)
        if not m:
            continue
        opener_indent = len(m.group("indent"))
        inline = m.group("inline").strip()
        if inline:
            flow = _FLOW_SEQ_RE.match(inline)
            if flow:
                return _parse_flow_sequence(flow.group("body"))
            # Single inline scalar — accept as one entry.
            return [inline]
        # Block sequence — collect indented ``- item`` lines until a
        # less-or-equal-indented non-blank line appears.
        items: list[str] = []
        for sub in lines[idx + 1 :]:
            if not sub.strip():
                continue
            mi = _PLAN_BLOCK_ITEM_RE.match(sub)
            if not mi:
                break
            indent = len(mi.group("indent"))
            if indent <= opener_indent:
                break
            items.append(mi.group("item").strip())
        return items
    return None


def load_ticket(
    ticket_id: str,
    ticket_dir: str | Path = DEFAULT_TICKET_DIR,
) -> Ticket:
    """Load a ticket file and extract its independence-relevant fields.

    Raises:
        TicketNotFoundError: no ticket file matches ``ticket_id``.
        MissingFilesTouchedError: ticket exists but its Plan section
            lacks ``files_touched:`` (or the Plan section is absent).
        TicketParseError: structural problem reading the ticket.
    """
    if not _TICKET_ID_RE.match(ticket_id):
        raise TicketParseError(ticket_id, "not a ticket-shaped id")
    path = find_ticket_path(ticket_id, ticket_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise TicketParseError(ticket_id, f"read error: {exc}") from exc

    depends_on = _parse_frontmatter_depends_on(text)
    plan_body = _extract_plan_section(text)
    if plan_body is None:
        raise MissingFilesTouchedError(ticket_id)
    files = _parse_plan_files_touched(plan_body)
    if files is None:
        raise MissingFilesTouchedError(ticket_id)

    return Ticket(
        ticket_id=ticket_id,
        path=path,
        depends_on=tuple(depends_on),
        files_touched=tuple(files),
    )


# ---------------------------------------------------------------------------
# Git dry-run merge plumbing (the merge-aware mechanism)
# ---------------------------------------------------------------------------


def compute_branch_name(ticket_id: str) -> str:
    """Return the canonical branch name for ``ticket_id`` (``argos/<id>``).

    Mirrors :func:`argos.cli.worktree.compute_branch_name`; kept local so the
    independence module does not couple to the worktree module.
    """
    return f"{BRANCH_PREFIX}/{ticket_id}"


def find_repo_root(start: str | Path | None = None) -> Optional[Path]:
    """Return the enclosing git repo root, or ``None`` if not in a repo.

    Unlike :func:`argos.cli.worktree.find_repo_root` this never raises — a
    missing repo is a normal "merge path unavailable, fall back to static"
    signal, not an error.
    """
    cwd = Path(start).resolve() if start is not None else Path.cwd()
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    return Path(res.stdout.strip()).resolve()


def branch_commit(repo_root: Path, ref: str) -> Optional[str]:
    """Return the full commit sha that ``ref`` resolves to, or ``None``.

    ``None`` means the ref does not exist (the common "branch not created yet"
    case) — the caller degrades to the static criterion for that pair.
    """
    res = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return None
    sha = res.stdout.strip()
    return sha or None


# Process-wide registry of live staging-worktree paths, so the atexit / signal
# backstops can clean up every one even if a context manager never runs (crash,
# SIGTERM). Keyed by path string → repo_root string.
_ACTIVE_STAGES: "dict[str, str]" = {}
_SIGNALS_INSTALLED = False
_PREV_HANDLERS: dict = {}


def _force_remove_worktree(repo_root: str, path: str) -> None:
    """Best-effort ``git worktree remove --force`` + prune + rmtree."""
    subprocess.run(
        ["git", "worktree", "remove", "--force", path],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    subprocess.run(
        ["git", "worktree", "prune"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    shutil.rmtree(path, ignore_errors=True)


def _cleanup_all_stages() -> None:
    for path, repo_root in list(_ACTIVE_STAGES.items()):
        _force_remove_worktree(repo_root, path)
        _ACTIVE_STAGES.pop(path, None)


def _signal_cleanup(signum, frame) -> None:  # pragma: no cover - signal path
    _cleanup_all_stages()
    prev = _PREV_HANDLERS.get(signum)
    if callable(prev):
        prev(signum, frame)
    else:
        # Restore the default and re-raise so the process terminates as the
        # signal intended (we are a backstop, not a swallower).
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)


def _install_backstops() -> None:
    """Idempotently register atexit + SIGINT/SIGTERM cleanup. Best-effort."""
    global _SIGNALS_INSTALLED
    if _SIGNALS_INSTALLED:
        return
    atexit.register(_cleanup_all_stages)
    for signum in (signal.SIGINT, signal.SIGTERM):
        try:
            _PREV_HANDLERS[signum] = signal.getsignal(signum)
            signal.signal(signum, _signal_cleanup)
        except (ValueError, OSError):
            # Not on the main thread, or platform without this signal — the
            # context manager + atexit still cover the common paths.
            _PREV_HANDLERS.pop(signum, None)
    _SIGNALS_INSTALLED = True


class MergeStagingArea:
    """A reusable throwaway worktree for dry-run merges.

    Created lazily on the first :meth:`try_merge` via
    ``git worktree add --detach`` into a :func:`tempfile.mkdtemp` path *outside*
    the repo tree, so it can never show up in the parent worktree's
    ``git status`` (AC#8). Reused across every pair in a detection run, reset
    between checks — so a 45-pair batch pays the worktree-creation cost once
    (AC#3), not 45 times.

    Cleanup is guaranteed on three paths: the context-manager :meth:`__exit__`,
    the process ``atexit`` hook, and ``SIGINT``/``SIGTERM`` handlers
    (:func:`_install_backstops`). After :meth:`close` the parent repo has no
    leaked worktrees.
    """

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root).resolve()
        self._path: Optional[Path] = None
        self._base_sha: Optional[str] = None

    # -- lifecycle ----------------------------------------------------------

    def __enter__(self) -> "MergeStagingArea":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _base(self) -> str:
        """A commit the worktree can detach onto. HEAD, or any branch tip."""
        res = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        raise GitError(
            "cannot resolve a base commit for the staging worktree",
            stderr=res.stderr.strip(),
            returncode=res.returncode,
        )

    def _ensure(self) -> Path:
        if self._path is not None:
            return self._path
        _install_backstops()
        self._base_sha = self._base()
        path = Path(tempfile.mkdtemp(prefix="argos-indep-staging-"))
        res = subprocess.run(
            ["git", "worktree", "add", "--detach", str(path), self._base_sha],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            raise GitError(
                "git worktree add (staging) failed",
                stderr=res.stderr.strip(),
                returncode=res.returncode,
            )
        self._path = path
        _ACTIVE_STAGES[str(path)] = str(self.repo_root)
        return path

    def close(self) -> None:
        if self._path is None:
            return
        path = self._path
        self._path = None
        _force_remove_worktree(str(self.repo_root), str(path))
        _ACTIVE_STAGES.pop(str(path), None)

    # -- the dry-run --------------------------------------------------------

    def _wt(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args],
            cwd=str(self._path),
            capture_output=True,
            text=True,
            check=False,
        )

    def _reset_to(self, sha: str) -> None:
        # Abort any merge left in progress, then hard-detach onto ``sha``.
        self._wt("merge", "--abort")
        res = self._wt("checkout", "-f", "--detach", sha)
        if res.returncode != 0:
            raise GitError(
                f"staging checkout of {sha} failed",
                stderr=res.stderr.strip(),
                returncode=res.returncode,
            )

    def try_merge(self, target_sha: str, incoming_sha: str) -> tuple[bool, tuple[str, ...]]:
        """Dry-run ``git merge --no-commit --no-ff incoming`` onto ``target``.

        Returns ``(clean, conflicted_paths)``. ``clean`` is True iff the merge
        auto-resolved with no unmerged paths. The merge is always aborted before
        returning, leaving the worktree reset — so a later pair starts clean.

        ``--no-commit`` means no commit is ever created, so commit-time hooks
        (the ARG1-032 ``pre-commit-state-write.sh``) never fire (AC#5). The
        configured merge driver *does* run (it is invoked during the merge, not
        at commit), so STATE.md exercises the ARG1-052 driver (AC#4).
        """
        self._ensure()
        self._reset_to(target_sha)
        res = self._wt("merge", "--no-commit", "--no-ff", incoming_sha)
        # Unmerged paths are the authoritative conflict signal; rc corroborates.
        unmerged = self._wt("diff", "--name-only", "--diff-filter=U")
        conflicted = tuple(
            p for p in unmerged.stdout.splitlines() if p.strip()
        )
        clean = res.returncode == 0 and not conflicted
        self._wt("merge", "--abort")
        return clean, conflicted


# ---------------------------------------------------------------------------
# Independence criterion
# ---------------------------------------------------------------------------


def _static_pair(a: Ticket, b: Ticket) -> PairResult:
    """ARG1-021 strict file-set disjointness — the degraded-but-correct path.

    Used when the merge path is unavailable for this pair (branches absent, or
    no git repo). Conservative-correct: never false-permissive.
    """
    shared = sorted(set(a.files_touched) & set(b.files_touched))
    if shared:
        return PairResult(
            a.ticket_id,
            b.ticket_id,
            independent=False,
            reason="shared file: " + ", ".join(shared),
            shared_files=tuple(shared),
        )
    return PairResult(a.ticket_id, b.ticket_id, independent=True)


def is_independent(
    a: Ticket,
    b: Ticket,
    *,
    staging: Optional[MergeStagingArea] = None,
    repo_root: str | Path | None = None,
) -> PairResult:
    """Decide whether two tickets are independent for parallel dispatch.

    Order (ARCHITECTURE.md §Independence detection / orchestrator.md §Parallel
    dispatch):

    1. ``depends_on`` (and the same-ticket guard) — checked first, by set
       membership, short-circuiting to ``dependent`` before any branch work
       (AC#7). The reason is deterministic when both conditions would fail.
    2. Merge dry-run — when a ``staging`` area (or ``repo_root``) is supplied
       and *both* ticket branches (``argos/<id>``) resolve to a commit, run
       ``git merge --no-commit --no-ff`` in both directions; independent iff
       both are conflict-free.
    3. Static fallback — when no merge area is supplied, or a branch is missing,
       fall back to strict ``files_touched:`` disjointness.

    With neither ``staging`` nor ``repo_root`` this is a pure-static comparison
    with no git interaction (so ARG1-022's plan-time ``partition(loaded)`` and
    the library unit tests behave exactly as under ARG1-021).
    """
    if a.ticket_id == b.ticket_id:
        return PairResult(
            a.ticket_id, b.ticket_id, independent=False, reason="same ticket"
        )
    if b.ticket_id in a.depends_on or a.ticket_id in b.depends_on:
        return PairResult(
            a.ticket_id, b.ticket_id, independent=False, reason="depends_on"
        )

    # No merge area requested → pure static.
    if staging is None and repo_root is None:
        return _static_pair(a, b)

    # Resolve a staging area, creating an ephemeral one for a bare repo_root.
    owns_staging = False
    if staging is None:
        # repo_root is not None here (the both-None case returned above).
        staging = MergeStagingArea(repo_root)
        owns_staging = True
    try:
        rr = staging.repo_root
        sha_a = branch_commit(rr, compute_branch_name(a.ticket_id))
        sha_b = branch_commit(rr, compute_branch_name(b.ticket_id))
        if sha_a is None or sha_b is None:
            # At least one branch not created yet → degraded-but-correct.
            return _static_pair(a, b)
        clean_ab, conf_ab = staging.try_merge(sha_a, sha_b)
        clean_ba, conf_ba = staging.try_merge(sha_b, sha_a)
        if clean_ab and clean_ba:
            return PairResult(a.ticket_id, b.ticket_id, independent=True)
        conflicts = sorted(set(conf_ab) | set(conf_ba))
        reason = "merge conflict"
        if conflicts:
            reason += ": " + ", ".join(conflicts)
        return PairResult(
            a.ticket_id,
            b.ticket_id,
            independent=False,
            reason=reason,
            shared_files=tuple(conflicts),
        )
    finally:
        if owns_staging:
            staging.close()


def partition(
    tickets: Iterable[Ticket],
    *,
    staging: Optional[MergeStagingArea] = None,
    repo_root: str | Path | None = None,
) -> list[list[str]]:
    """Greedy partition of tickets into independence groups.

    Each returned group is a list of ticket ids whose pairwise
    :func:`is_independent` checks all return ``independent=True``. First-fit
    greedy: each ticket joins the earliest group that accepts it, opening a new
    group only when none does.

    ``staging`` / ``repo_root`` are threaded into every pairwise check so a
    single staging worktree is reused across the whole partition (AC#3). With
    neither argument the partition is pure-static — ARG1-022's
    ``partition(loaded)`` call site is unchanged and keeps its plan-time
    behavior.

    Determinism: input order is preserved; same input + same branch state yields
    the same partition. Optimality (minimum number of groups) is not guaranteed.
    """
    tickets = list(tickets)
    groups: list[list[Ticket]] = []
    for t in tickets:
        placed = False
        for grp in groups:
            if all(
                is_independent(t, other, staging=staging, repo_root=repo_root).independent
                for other in grp
            ):
                grp.append(t)
                placed = True
                break
        if not placed:
            groups.append([t])
    return [[t.ticket_id for t in grp] for grp in groups]
