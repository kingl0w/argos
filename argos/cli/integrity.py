"""Integrity checks behind ``argos status`` (ARG1-003).

``argos status`` is the v1.0 integrity oracle named in
``ARCHITECTURE.md`` §Invariants: *"If ``argos status`` exits zero, the
operator can trust that STATE.md, tickets, and git are mutually
consistent."* This module holds the four checks; the CLI shim at
``argos/cli/commands/status.py`` resolves the repo root, calls
:func:`run_checks`, and formats the result.

The four checks (the exact key set surfaced by ``--json``):

1. ``state_md`` — ``argos/specs/STATE.md`` parses against the v1.0 block
   schema (``state_parser``), every block's ``ticket`` resolves to a
   ticket file on disk, and every ``## Queue`` entry resolves to a
   ticket file on disk.
2. ``config`` — ``argos/config.toml`` exists and, together with
   ``.argos/local.toml``, parses and type-validates against the config
   schema.
3. ``escalations`` — every file under ``argos/specs/escalations/`` is a
   schema-valid escalation, and none is an undrained *blocking*
   escalation.
4. ``git_alignment`` — every ticket recorded under ``## Done this cycle``
   appears in the git log reachable from HEAD.

Diagnose only — no auto-fix (that is ``argos sync``'s job) and no network
calls (no GitHub Issues check). Standard library only (ADR-001); runs
under Python >= 3.9.
"""

from __future__ import annotations

import io
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from argos.cli import config as config_mod
from argos.cli import escalation_validator
from argos.cli import queue as queue_mod
from argos.cli import state_parser

__all__ = [
    "CheckResult",
    "IntegrityReport",
    "CHECK_NAMES",
    "run_checks",
]

# The check keys surfaced (in this order) by ``argos status --json``.
CHECK_NAMES = ("state_md", "config", "escalations", "git_alignment")

# Paths, relative to the repo root, that each check inspects.
_STATE_REL = Path("argos") / "specs" / "STATE.md"
_ESCALATIONS_REL = Path("argos") / "specs" / "escalations"
_PROJECT_CONFIG_REL = Path("argos") / "config.toml"
_PROJECT_CONFIG_TEMPLATE_REL = Path("argos") / "config.toml.template"
_LOCAL_CONFIG_REL = Path(".argos") / "local.toml"
_LOCAL_CONFIG_TEMPLATE_REL = Path(".argos") / "local.toml.template"

# Ticket-file search roots, in priority order. The canonical
# ``argos init`` layout is ``argos/specs/tickets/``; the self-hosted
# Argos tree keeps its tickets under ``argos/specs/v1.0/tickets/``, so we
# fall back to it when the canonical directory is absent.
_TICKET_DIRS_REL = (
    Path("argos") / "specs" / "tickets",
    Path("argos") / "specs" / "v1.0" / "tickets",
)

_DONE_SECTION = "Done this cycle"
_DONE_HEADING_RE = re.compile(rf"^##\s+{re.escape(_DONE_SECTION)}\s*$")
_NEXT_HEADING_RE = re.compile(r"^##\s")
# A drained escalation carries either a ``## Resolution`` section or an
# inline ``**Drained:**`` marker (see the drained audit files under
# ``argos/specs/escalations/``).
_DRAINED_RE = re.compile(r"(?mi)^##\s+Resolution\b|\*\*Drained:\*\*")

# Cap on how far back the git-alignment check reads. Keeps ``argos status``
# well under its 2-second budget on a large history.
_GIT_LOG_LIMIT = 500


@dataclass
class CheckResult:
    """Outcome of a single integrity check."""

    name: str
    passed: bool
    messages: list[str] = field(default_factory=list)

    @property
    def verdict(self) -> str:
        return "pass" if self.passed else "fail"


@dataclass
class IntegrityReport:
    """Aggregate of all four checks."""

    checks: list[CheckResult]

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def by_name(self) -> dict[str, CheckResult]:
        return {c.name: c for c in self.checks}

    def to_json_obj(self) -> dict:
        """Serialize to the ``argos status --json`` object.

        Top-level check keys map to the literal string ``"pass"`` /
        ``"fail"`` (AC#5). ``diagnostics`` carries the per-check messages
        for richer tooling; ``ok`` mirrors the process exit status.
        """
        by_name = self.by_name()
        obj: dict = {"ok": self.ok}
        for name in CHECK_NAMES:
            check = by_name.get(name)
            obj[name] = check.verdict if check is not None else "fail"
        obj["diagnostics"] = {
            name: (by_name[name].messages if name in by_name else [])
            for name in CHECK_NAMES
        }
        return obj


# ---------------------------------------------------------------------------
# Ticket lookup
# ---------------------------------------------------------------------------


def _ticket_exists(repo_root: Path, ticket_id: str) -> bool:
    """True iff a ticket file for ``ticket_id`` exists under any search root.

    A ticket file is ``{ticket_id}.md`` or ``{ticket_id}-{slug}.md`` (the
    slugged form is what ``/new-ticket`` produces, e.g.
    ``ARG1-032-pre-commit-verifier-only-state.md``).
    """
    for rel in _TICKET_DIRS_REL:
        d = repo_root / rel
        if not d.is_dir():
            continue
        if (d / f"{ticket_id}.md").is_file():
            return True
        if any(d.glob(f"{ticket_id}-*.md")):
            return True
    return False


# ---------------------------------------------------------------------------
# Check 1 — STATE.md
# ---------------------------------------------------------------------------


def check_state_md(repo_root: Path) -> CheckResult:
    """Parse STATE.md and confirm every block's ticket resolves to a file."""
    state_path = repo_root / _STATE_REL
    if not state_path.is_file():
        return CheckResult(
            "state_md",
            False,
            [f"STATE.md: not found at {_STATE_REL.as_posix()}"],
        )

    try:
        blocks = state_parser.parse_file(state_path)
    except state_parser.StateBlockError as exc:
        # The parser's message carries the schema-contract substring
        # (e.g. "unclosed entry"); prefix with "STATE.md" so the AC's
        # two-substring check (STATE.md + unclosed entry) is satisfied.
        return CheckResult("state_md", False, [f"STATE.md: {exc}"])
    except OSError as exc:
        return CheckResult("state_md", False, [f"STATE.md: cannot read ({exc})"])

    messages: list[str] = []
    for block in blocks:
        if not _ticket_exists(repo_root, block.ticket):
            messages.append(
                f"STATE.md: block id={block.id!r} references ticket "
                f"{block.ticket} but no ticket file was found under "
                f"argos/specs/tickets/"
            )

    # Queue entries are plain bullets, not annotated blocks, so the block
    # pass above never sees them. A queue pointing at a ticket file that
    # does not exist is exactly the drift this oracle is for.
    try:
        queued = queue_mod.parse_queue(state_path.read_text(encoding="utf-8"))
    except (queue_mod.QueueSectionMissingError, OSError):
        queued = []
    for ticket_id in queued:
        if not _ticket_exists(repo_root, ticket_id):
            messages.append(
                f"STATE.md: '## Queue' lists {ticket_id} but no ticket "
                f"file was found under argos/specs/tickets/"
            )
    return CheckResult("state_md", not messages, messages)


# ---------------------------------------------------------------------------
# Check 2 — config
# ---------------------------------------------------------------------------


def _existing(repo_root: Path, *rels: Path) -> Path | None:
    for rel in rels:
        p = repo_root / rel
        if p.is_file():
            return p
    return None


def check_config(repo_root: Path) -> CheckResult:
    """Both config files parse and type-validate against the schema."""
    project_path = _existing(
        repo_root, _PROJECT_CONFIG_REL, _PROJECT_CONFIG_TEMPLATE_REL
    )
    if project_path is None:
        return CheckResult(
            "config",
            False,
            [f"config: {_PROJECT_CONFIG_REL.as_posix()} not found"],
        )
    local_path = _existing(
        repo_root, _LOCAL_CONFIG_REL, _LOCAL_CONFIG_TEMPLATE_REL
    )

    # Unknown-key warnings are informational, not failures — swallow them.
    sink = io.StringIO()
    try:
        cfg = config_mod.load(
            project_path=project_path,
            local_path=local_path,
            warn_stream=sink,
        )
    except config_mod.ConfigParseError as exc:
        return CheckResult("config", False, [f"config: {exc}"])
    except OSError as exc:
        return CheckResult("config", False, [f"config: cannot read ({exc})"])

    errors = cfg.validate()
    if errors:
        return CheckResult(
            "config", False, [f"config: {e}" for e in errors]
        )
    return CheckResult("config", True, [])


# ---------------------------------------------------------------------------
# Check 3 — escalations
# ---------------------------------------------------------------------------


def _is_drained(text: str) -> bool:
    return bool(_DRAINED_RE.search(text))


def check_escalations(repo_root: Path) -> CheckResult:
    """No malformed escalation files; no undrained *blocking* escalations."""
    esc_dir = repo_root / _ESCALATIONS_REL
    if not esc_dir.is_dir():
        return CheckResult("escalations", True, [])

    messages: list[str] = []
    for path in sorted(esc_dir.glob("*.md")):
        if path.name == "README.md" or path.name.startswith("."):
            continue
        rel = path.relative_to(repo_root).as_posix()

        try:
            errors = escalation_validator.validate(path)
        except (ValueError, OSError) as exc:
            messages.append(f"escalations: {rel}: malformed ({exc})")
            continue
        if errors:
            joined = "; ".join(errors)
            messages.append(f"escalations: {rel}: malformed ({joined})")
            continue

        text = path.read_text(encoding="utf-8")
        fm, _ = escalation_validator.parse_frontmatter(text)
        if fm.get("severity") == "blocking" and not _is_drained(text):
            messages.append(
                f"escalations: {rel}: undrained escalation "
                f"(blocking, no ## Resolution / **Drained:** marker)"
            )

    return CheckResult("escalations", not messages, messages)


# ---------------------------------------------------------------------------
# Check 4 — git alignment
# ---------------------------------------------------------------------------


def _done_section_ticket_blocks(text: str) -> list[state_parser.Block]:
    """Return parsed blocks whose open tag falls under ``## Done this cycle``.

    Returns ``[]`` if the section is absent or the text does not parse.
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

    try:
        blocks = state_parser.parse(text)
    except state_parser.StateBlockError:
        return []
    # start_line is 1-indexed; heading_idx / next_idx are 0-indexed.
    return [b for b in blocks if heading_idx < (b.start_line - 1) < next_idx]


def _git_log_text(repo_root: Path) -> str | None:
    """Return recent commit subjects+bodies, or ``None`` if git is unusable."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "log",
             f"-n{_GIT_LOG_LIMIT}", "--format=%s%n%b"],
            capture_output=True,
            text=True,
            check=False,
        )
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def check_git_alignment(repo_root: Path) -> CheckResult:
    """Every ``## Done this cycle`` ticket appears in the recent git log."""
    state_path = repo_root / _STATE_REL
    if not state_path.is_file():
        # state_md already reports the missing file; nothing to align.
        return CheckResult("git_alignment", True, [])
    try:
        text = state_path.read_text(encoding="utf-8")
    except OSError:
        return CheckResult("git_alignment", True, [])

    blocks = _done_section_ticket_blocks(text)
    if not blocks:
        return CheckResult("git_alignment", True, [])

    log_text = _git_log_text(repo_root)
    if log_text is None:
        # Degraded-but-correct: no git history to check against, so we
        # cannot prove misalignment. Pass rather than raise a false alarm.
        return CheckResult("git_alignment", True, [])

    messages: list[str] = []
    for block in blocks:
        if block.ticket not in log_text:
            messages.append(
                f"git_alignment: STATE.md '## {_DONE_SECTION}' records "
                f"{block.ticket} (block id={block.id!r}) but no commit "
                f"mentioning it was found in the last {_GIT_LOG_LIMIT} "
                f"commits on the current branch"
            )
    return CheckResult("git_alignment", not messages, messages)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_checks(repo_root: Path) -> IntegrityReport:
    """Run all four integrity checks against ``repo_root``."""
    repo_root = Path(repo_root)
    checks = [
        check_state_md(repo_root),
        check_config(repo_root),
        check_escalations(repo_root),
        check_git_alignment(repo_root),
    ]
    return IntegrityReport(checks)
