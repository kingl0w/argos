"""Tests for ARG1-003 ``argos status`` integrity oracle.

Two layers:

- **Unit** — drive :mod:`argos.cli.integrity` directly against
  hand-built temporary repos (fast, no subprocess, no git for the
  malformation cases).
- **CLI / acceptance** — invoke ``python3 -m argos.cli status`` as a
  subprocess so the exit-code and stderr/stdout contracts the ACs depend
  on are exercised end-to-end, including the real ``argos init`` path for
  AC#1.

ADR-001 / ADR-002: standard library only. Runnable as::

    python3 -m unittest argos.cli.tests.test_status -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli import integrity  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_STATE_VALID = """\
# Demo — State

## Current focus

Testing argos status.

## Queue

- _none_

## In progress

- [ ] _none_

## Done this cycle

<!-- argos:entry id=2026-04-26T11:00:00Z-ARG1-050 ticket=ARG1-050 author=verifier session=sess-a1 -->
- **[2026-04-26T11:00:00Z] ARG1-050 — verified**
  - Decision: pass
<!-- /argos:entry -->

## Open decisions

- _none_

## Known drift

- _none_
"""

# Same as valid but with the closing tag of the Done-this-cycle block
# deleted — the AC#2 hand-corruption.
_STATE_UNCLOSED = _STATE_VALID.replace("<!-- /argos:entry -->\n", "", 1)

_CONFIG = """\
[project]
name = "demo"
prefix = "ARG1"

[orchestrator]
max_parallel = 3
independence_strategy = "plan-declared"
dry_plan_cache = true

[verifier]
auto_fix_retries = 0

[escalation]
require_attend_before_merge = true
"""

# A schema-valid, blocking escalation with NO ## Resolution / **Drained:**
# marker — i.e. undrained (AC#4).
_ESCALATION_BLOCKING = """\
---
ticket_id: ARG1-099
session_id: sess-2026-04-26T12:00:00Z-a1b2
severity: blocking
raised_by: orchestrator
created: 2026-04-26T12:00:00Z
---

## Question

Should the demo serialize or parallelize?

## Context

Both tickets touch the same file.

## Options considered

- A: serialize.
- B: parallelize.

## Why escalated

A policy call the agent may not make.
"""


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(root: Path, *, state: str = _STATE_VALID) -> Path:
    """Build a minimal, non-git Argos repo that passes every check."""
    _write(root / "argos" / "specs" / "STATE.md", state)
    _write(root / "argos" / "config.toml", _CONFIG)
    # The block in _STATE_VALID references ARG1-050; give it a ticket file.
    _write(root / "argos" / "specs" / "tickets" / "ARG1-050.md", "# ARG1-050\n")
    return root


def _run_cli(args: list[str]) -> subprocess.CompletedProcess:
    """Invoke ``python3 -m argos.cli`` with the repo importable."""
    env = {"PYTHONPATH": str(_REPO_ROOT), "PATH": _path_env()}
    return subprocess.run(
        [sys.executable, "-m", "argos.cli", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _path_env() -> str:
    import os
    return os.environ.get("PATH", "")


# ---------------------------------------------------------------------------
# Unit tests — integrity.run_checks
# ---------------------------------------------------------------------------


class IntegrityUnitTests(unittest.TestCase):
    def test_clean_repo_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            report = integrity.run_checks(root)
            self.assertTrue(report.ok, msg=report.to_json_obj())
            for name in integrity.CHECK_NAMES:
                self.assertTrue(report.by_name()[name].passed, name)

    def test_unclosed_state_block_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td), state=_STATE_UNCLOSED)
            report = integrity.run_checks(root)
            self.assertFalse(report.ok)
            sm = report.by_name()["state_md"]
            self.assertFalse(sm.passed)
            joined = " ".join(sm.messages)
            self.assertIn("STATE.md", joined)
            self.assertIn("unclosed entry", joined)

    def test_missing_ticket_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            (root / "argos" / "specs" / "tickets" / "ARG1-050.md").unlink()
            report = integrity.run_checks(root)
            sm = report.by_name()["state_md"]
            self.assertFalse(sm.passed)
            self.assertIn("ARG1-050", " ".join(sm.messages))

    def test_ticket_found_in_v1_fallback_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _write(root / "argos" / "specs" / "STATE.md", _STATE_VALID)
            _write(root / "argos" / "config.toml", _CONFIG)
            # No argos/specs/tickets/, only the v1.0 fallback with a slug.
            _write(
                root / "argos" / "specs" / "v1.0" / "tickets"
                / "ARG1-050-state-block-schema.md",
                "# ARG1-050\n",
            )
            report = integrity.run_checks(root)
            self.assertTrue(report.by_name()["state_md"].passed)

    def test_malformed_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            # Array literal — rejected by the in-house mini-parser.
            _write(
                root / "argos" / "config.toml",
                _CONFIG + '\n[verifier]\nminor_lint_rules = ["a", "b"]\n',
            )
            report = integrity.run_checks(root)
            self.assertFalse(report.by_name()["config"].passed)

    def test_missing_project_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            (root / "argos" / "config.toml").unlink()
            report = integrity.run_checks(root)
            self.assertFalse(report.by_name()["config"].passed)

    def test_malformed_escalation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations" / "blocking.md",
                "no frontmatter here, just prose\n",
            )
            report = integrity.run_checks(root)
            esc = report.by_name()["escalations"]
            self.assertFalse(esc.passed)
            self.assertIn("blocking.md", " ".join(esc.messages))

    def test_undrained_blocking_escalation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations"
                / "ARG1-099-2026-04-26T12:00:00Z.md",
                _ESCALATION_BLOCKING,
            )
            report = integrity.run_checks(root)
            esc = report.by_name()["escalations"]
            self.assertFalse(esc.passed)
            self.assertIn("undrained escalation", " ".join(esc.messages))

    def test_drained_blocking_escalation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            drained = _ESCALATION_BLOCKING + (
                "\n## Resolution\n\n**Drained:** 2026-04-27 by operator.\n"
            )
            _write(
                root / "argos" / "specs" / "escalations"
                / "ARG1-099-2026-04-26T12:00:00Z.md",
                drained,
            )
            report = integrity.run_checks(root)
            self.assertTrue(report.by_name()["escalations"].passed)

    def test_undrained_advisory_escalation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            advisory = _ESCALATION_BLOCKING.replace(
                "severity: blocking", "severity: advisory"
            )
            _write(
                root / "argos" / "specs" / "escalations"
                / "ARG1-099-2026-04-26T12:00:00Z.md",
                advisory,
            )
            report = integrity.run_checks(root)
            self.assertTrue(report.by_name()["escalations"].passed)

    def test_readme_in_escalations_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations" / "README.md",
                "# escalations\n\nprose, intentionally no frontmatter\n",
            )
            report = integrity.run_checks(root)
            self.assertTrue(report.by_name()["escalations"].passed)

    def test_git_alignment_skipped_without_git(self) -> None:
        # _make_repo creates no .git; the Done-this-cycle block references
        # ARG1-050 which is not in any log, yet the check must not fail.
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            self.assertTrue(report_git(root))

    def test_git_alignment_fails_on_divergence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _git_repo(Path(td))
            # STATE.md says ARG1-050 is done, but no commit mentions it.
            report = integrity.run_checks(root)
            ga = report.by_name()["git_alignment"]
            self.assertFalse(ga.passed)
            self.assertIn("ARG1-050", " ".join(ga.messages))

    def test_git_alignment_passes_when_commit_mentions_ticket(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _git_repo(Path(td), commit_msg="ARG1-050: ship the thing")
            report = integrity.run_checks(root)
            self.assertTrue(report.by_name()["git_alignment"].passed)


def report_git(root: Path) -> bool:
    return integrity.run_checks(root).by_name()["git_alignment"].passed


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, check=True,
    )


def _git_repo(root: Path, *, commit_msg: str = "initial: no ticket here") -> Path:
    _make_repo(root)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "-A")
    # Bypass any inherited hooks; we only need a commit in the log.
    _git(root, "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", commit_msg)
    return root


# ---------------------------------------------------------------------------
# CLI / acceptance tests
# ---------------------------------------------------------------------------


class StatusCliTests(unittest.TestCase):
    def test_ac1_clean_init_repo_exit_zero(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            init = _run_cli(["init", "--path", td, "--name", "demo",
                             "--prefix", "ARG1"])
            self.assertEqual(init.returncode, 0, msg=init.stderr)
            res = _run_cli(["status", "--repo-root", td])
            self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_ac2_unclosed_state_block(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td), state=_STATE_UNCLOSED)
            res = _run_cli(["status", "--repo-root", str(root)])
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("STATE.md", res.stderr)
            self.assertIn("unclosed entry", res.stderr)

    def test_ac3_malformed_escalation_names_path(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations" / "blocking.md",
                "no frontmatter here\n",
            )
            res = _run_cli(["status", "--repo-root", str(root)])
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("blocking.md", res.stderr)

    def test_ac4_undrained_blocking_escalation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations"
                / "ARG1-099-2026-04-26T12:00:00Z.md",
                _ESCALATION_BLOCKING,
            )
            res = _run_cli(["status", "--repo-root", str(root)])
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("undrained escalation", res.stderr)

    def test_ac5_json_keys_and_matching_exit(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            # Failing case: undrained escalation.
            root = _make_repo(Path(td))
            _write(
                root / "argos" / "specs" / "escalations"
                / "ARG1-099-2026-04-26T12:00:00Z.md",
                _ESCALATION_BLOCKING,
            )
            res = _run_cli(["status", "--repo-root", str(root), "--json"])
            self.assertNotEqual(res.returncode, 0)
            obj = json.loads(res.stdout)
            for key in ("state_md", "config", "escalations", "git_alignment"):
                self.assertIn(key, obj)
                self.assertIn(obj[key], ("pass", "fail"))
            self.assertEqual(obj["escalations"], "fail")

    def test_ac5_json_exit_zero_all_pass(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = _make_repo(Path(td))
            res = _run_cli(["status", "--repo-root", str(root), "--json"])
            self.assertEqual(res.returncode, 0, msg=res.stderr)
            obj = json.loads(res.stdout)
            self.assertTrue(obj["ok"])
            for key in ("state_md", "config", "escalations", "git_alignment"):
                self.assertEqual(obj[key], "pass")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
