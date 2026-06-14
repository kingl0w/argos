"""Tests for the ARG1-001 CLI scaffold acceptance criteria.

Each test invokes ``argos/cli/argos`` as a subprocess via absolute path and
asserts the exit code, stdout, and stderr contracts named in the ticket ACs.
Runnable as::

    python3 -m unittest argos.cli.tests.test_version -v

(no third-party dependencies required).
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

# Make ``argos.cli...`` importable when the tests are invoked from anywhere.
# argos/cli/tests/test_version.py
#   parents[0] = argos/cli/tests
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_ARGOS_BIN = Path(__file__).resolve().parents[1] / "argos"


def _run(*args: str) -> subprocess.CompletedProcess:
    """Invoke the in-repo argos launcher with the given args."""
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class CLIVersionAndHelpTests(unittest.TestCase):
    """ACs #1, #2 — version and help."""

    def test_version_exits_zero_and_matches_regex(self) -> None:
        result = _run("--version")
        self.assertEqual(
            result.returncode, 0,
            f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}",
        )
        # AC#2: stdout matches ^argos N.N.N(-suffix)?$ (ignoring trailing newline).
        regex = re.compile(r"^argos [0-9]+\.[0-9]+\.[0-9]+(-[a-z0-9.]+)?$")
        self.assertRegex(result.stdout.rstrip("\n"), regex)

    def test_help_exits_zero_and_lists_public_subcommands(self) -> None:
        result = _run("--help")
        self.assertEqual(
            result.returncode, 0,
            f"expected exit 0, got {result.returncode}; stderr={result.stderr!r}",
        )
        # AC#3: stdout contains init / sync / status / attend.
        for sub in ("init", "sync", "status", "attend"):
            self.assertIn(
                sub, result.stdout,
                f"expected --help output to contain {sub!r}; got: {result.stdout!r}",
            )


class CLIErrorPathTests(unittest.TestCase):
    """ACs #4, #5 — no-args usage and unknown-subcommand errors."""

    def test_no_args_exits_nonzero_with_usage(self) -> None:
        result = _run()
        self.assertNotEqual(
            result.returncode, 0,
            "expected non-zero exit when invoked with no args",
        )
        # AC#4: stderr contains 'usage:'.
        self.assertIn(
            "usage:", result.stderr,
            f"expected stderr to contain 'usage:'; got: {result.stderr!r}",
        )

    def test_unknown_subcommand_exits_nonzero(self) -> None:
        result = _run("definitely-not-a-real-subcommand")
        self.assertNotEqual(
            result.returncode, 0,
            "expected non-zero exit for unknown subcommand",
        )
        # AC#5: stderr contains 'unknown'.
        self.assertIn(
            "unknown", result.stderr,
            f"expected stderr to contain 'unknown'; got: {result.stderr!r}",
        )


class CLIStubSubcommandTests(unittest.TestCase):
    """Sanity guard: registered public stubs exit non-zero until implemented."""

    def test_attend_stub_exits_nonzero(self) -> None:
        # ``status`` was implemented in ARG1-003 and is exercised by
        # test_status.py; ``attend`` (ARG1-005) remains a stub.
        result = _run("attend")
        self.assertNotEqual(
            result.returncode, 0,
            "expected non-zero exit from unimplemented 'attend' stub",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
