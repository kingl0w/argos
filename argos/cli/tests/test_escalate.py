"""Tests for argos.cli.escalation and the ``argos escalate`` CLI (ARG1-041).

Stdlib ``unittest`` only — no pytest. Run from the repo root::

    python3 -m unittest argos.cli.tests.test_escalate -v
"""

from __future__ import annotations

import io
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli import escalation  # noqa: E402
from argos.cli import escalation_validator  # noqa: E402
from argos.cli.tests.fixtures.test_webhook_server import (  # noqa: E402
    WebhookTestServer,
    find_unused_port,
)

_ARGOS_BIN = _REPO_ROOT / "argos" / "cli" / "argos"


def _run_cli(
    *args: str,
    cwd: Path | None = None,
    env: dict | None = None,
    timeout: float = 10.0,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_ARGOS_BIN), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
        env=env,
        timeout=timeout,
    )


def _setup_repo_root(tmp: Path, *, webhook_url: str | None) -> Path:
    """Build a minimal Argos repo skeleton inside ``tmp``.

    Returns the resolved repo root. The ``escalation.webhook_url`` value is
    written into ``.argos/local.toml`` if ``webhook_url`` is non-None.
    """
    (tmp / "argos" / "specs").mkdir(parents=True, exist_ok=True)
    (tmp / "argos" / "config.toml.template").write_text(
        '[project]\nname = "argos-test"\n', encoding="utf-8"
    )
    if webhook_url is not None:
        (tmp / ".argos").mkdir(parents=True, exist_ok=True)
        (tmp / ".argos" / "local.toml").write_text(
            f'[escalation]\nwebhook_url = "{webhook_url}"\n',
            encoding="utf-8",
        )
    (tmp / "argos" / "specs" / "escalations").mkdir(parents=True, exist_ok=True)
    return tmp


class WriterTests(unittest.TestCase):
    """Direct exercises of :func:`argos.cli.escalation.write_escalation`."""

    def test_writes_valid_escalation_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            path = escalation.write_escalation(
                ticket_id="ARG1-099",
                severity="blocking",
                raised_by="orchestrator",
                body="The agent hit ambiguity X.",
                dest_dir=tmp,
            )
            self.assertTrue(path.name.startswith("ARG1-099-"))
            self.assertTrue(path.name.endswith(".md"))
            errors = escalation_validator.validate(path)
            self.assertEqual(errors, [], f"unexpected validator errors: {errors}")

    def test_passes_through_full_body(self) -> None:
        body = textwrap.dedent(
            """\
            ## Question

            Q?

            ## Context

            C.

            ## Options considered

            - A
            - B

            ## Why escalated

            W.
            """
        )
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            path = escalation.write_escalation(
                ticket_id="ARG1-099",
                severity="advisory",
                raised_by="planner",
                body=body,
                dest_dir=tmp,
            )
            text = path.read_text(encoding="utf-8")
            self.assertIn("- A", text)
            self.assertIn("- B", text)
            for heading in escalation_validator.REQUIRED_BODY_SECTIONS:
                self.assertEqual(
                    sum(1 for line in text.splitlines() if line.strip() == heading),
                    1,
                    f"heading {heading!r} duplicated in pass-through body",
                )

    def test_invalid_severity_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            with self.assertRaises(escalation.InvalidSeverityError):
                escalation.write_escalation(
                    ticket_id="ARG1-099",
                    severity="urgent",
                    raised_by="orchestrator",
                    body="x",
                    dest_dir=Path(tmp_str),
                )

    def test_invalid_raised_by_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            with self.assertRaises(escalation.InvalidRaisedByError):
                escalation.write_escalation(
                    ticket_id="ARG1-099",
                    severity="blocking",
                    raised_by="human",
                    body="x",
                    dest_dir=Path(tmp_str),
                )

    def test_concurrent_same_second_writes_produce_distinct_files(self) -> None:
        """AC#7: two writes in the same wall-clock second produce two files."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            fixed_now = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)
            paths: list[Path] = []
            errors: list[BaseException] = []

            def worker() -> None:
                try:
                    p = escalation.write_escalation(
                        ticket_id="ARG1-099",
                        severity="blocking",
                        raised_by="coder",
                        body="concurrent",
                        dest_dir=tmp,
                        now=fixed_now,
                    )
                    paths.append(p)
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [], f"unexpected exceptions: {errors}")
            self.assertEqual(len(paths), 2)
            self.assertNotEqual(paths[0], paths[1])
            for p in paths:
                self.assertTrue(p.exists())
                self.assertEqual(escalation_validator.validate(p), [])

    def test_filename_uses_dash_separated_timestamp(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            now = datetime(2026, 4, 26, 14, 33, 1, tzinfo=timezone.utc)
            path = escalation.write_escalation(
                ticket_id="ARG1-099",
                severity="blocking",
                raised_by="orchestrator",
                body="x",
                dest_dir=tmp,
                now=now,
            )
            self.assertEqual(path.name, "ARG1-099-2026-04-26T14-33-01Z.md")
            text = path.read_text(encoding="utf-8")
            self.assertIn("created: 2026-04-26T14:33:01Z", text)


class WebhookUnitTests(unittest.TestCase):
    """Direct exercises of :func:`argos.cli.escalation.post_webhook`."""

    def test_post_success_records_request(self) -> None:
        server = WebhookTestServer(response_status=200)
        try:
            log = io.StringIO()
            ok = escalation.post_webhook(
                server.url,
                ticket_id="ARG1-099",
                severity="blocking",
                summary="hello",
                file_path="/tmp/x.md",
                log_stream=log,
            )
        finally:
            server.stop()
        self.assertTrue(ok)
        self.assertEqual(log.getvalue(), "")
        reqs = server.requests
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["method"], "POST")
        self.assertEqual(
            reqs[0]["payload"],
            {
                "ticket_id": "ARG1-099",
                "severity": "blocking",
                "summary": "hello",
                "file_path": "/tmp/x.md",
            },
        )

    def test_post_500_logs_status(self) -> None:
        server = WebhookTestServer(response_status=500)
        try:
            log = io.StringIO()
            ok = escalation.post_webhook(
                server.url,
                ticket_id="ARG1-099",
                severity="blocking",
                summary="hello",
                file_path="/tmp/x.md",
                log_stream=log,
            )
        finally:
            server.stop()
        self.assertFalse(ok)
        self.assertIn("webhook delivery failed: 500", log.getvalue())

    def test_post_unreachable_logs_failure_within_timeout(self) -> None:
        port = find_unused_port()
        log = io.StringIO()
        ok = escalation.post_webhook(
            f"http://127.0.0.1:{port}/hook",
            ticket_id="ARG1-099",
            severity="blocking",
            summary="hello",
            file_path="/tmp/x.md",
            log_stream=log,
            timeout=2.0,
        )
        self.assertFalse(ok)
        self.assertIn("webhook delivery failed", log.getvalue())


class CliTests(unittest.TestCase):
    """End-to-end CLI exercises (subprocess against the in-repo launcher)."""

    def test_ac1_basic_invocation_writes_valid_file(self) -> None:
        """AC#1: file matching ARG1-099-*.md is created and validates."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = _setup_repo_root(Path(tmp_str), webhook_url=None)
            result = _run_cli(
                "escalate",
                "--ticket", "ARG1-099",
                "--severity", "blocking",
                "--raised-by", "orchestrator",
                "--body", "test",
                cwd=tmp,
            )
            self.assertEqual(
                result.returncode, 0,
                f"stdout={result.stdout!r} stderr={result.stderr!r}",
            )
            files = sorted((tmp / "argos" / "specs" / "escalations").glob("ARG1-099-*.md"))
            self.assertEqual(len(files), 1, f"expected 1 file, got: {files}")
            self.assertEqual(escalation_validator.validate(files[0]), [])

    def test_ac2_no_webhook_url_means_no_network_call(self) -> None:
        """AC#2: with webhook_url empty, no HTTP request goes out.

        We assert this by running a server, leaving its URL OUT of the
        config (config has empty webhook_url), and confirming the server
        records zero requests after the CLI run.
        """
        server = WebhookTestServer(response_status=200)
        try:
            with tempfile.TemporaryDirectory() as tmp_str:
                tmp = _setup_repo_root(Path(tmp_str), webhook_url="")
                result = _run_cli(
                    "escalate",
                    "--ticket", "ARG1-099",
                    "--severity", "blocking",
                    "--raised-by", "orchestrator",
                    "--body", "test",
                    cwd=tmp,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"stderr={result.stderr!r}",
                )
                files = list((tmp / "argos" / "specs" / "escalations").glob("ARG1-099-*.md"))
                self.assertEqual(len(files), 1)
            self.assertEqual(server.requests, [])
        finally:
            server.stop()

    def test_ac3_webhook_receives_one_post_with_required_keys(self) -> None:
        """AC#3: configured webhook URL → exactly one POST with the four keys."""
        server = WebhookTestServer(response_status=200)
        try:
            with tempfile.TemporaryDirectory() as tmp_str:
                tmp = _setup_repo_root(Path(tmp_str), webhook_url=server.url)
                result = _run_cli(
                    "escalate",
                    "--ticket", "ARG1-099",
                    "--severity", "blocking",
                    "--raised-by", "orchestrator",
                    "--body", "the question",
                    cwd=tmp,
                )
                self.assertEqual(
                    result.returncode, 0,
                    f"stderr={result.stderr!r}",
                )
            reqs = server.requests
        finally:
            server.stop()
        self.assertEqual(len(reqs), 1)
        payload = reqs[0]["payload"]
        self.assertIsNotNone(payload)
        self.assertEqual(set(payload.keys()), {"ticket_id", "severity", "summary", "file_path"})
        self.assertEqual(payload["ticket_id"], "ARG1-099")
        self.assertEqual(payload["severity"], "blocking")
        self.assertEqual(payload["summary"], "the question")
        self.assertTrue(payload["file_path"].endswith(".md"))

    def test_ac4_webhook_500_exits_zero_with_stderr_log(self) -> None:
        """AC#4: 500 → exit 0, stderr contains ``webhook delivery failed: 500``."""
        server = WebhookTestServer(response_status=500)
        try:
            with tempfile.TemporaryDirectory() as tmp_str:
                tmp = _setup_repo_root(Path(tmp_str), webhook_url=server.url)
                result = _run_cli(
                    "escalate",
                    "--ticket", "ARG1-099",
                    "--severity", "blocking",
                    "--raised-by", "orchestrator",
                    "--body", "boom",
                    cwd=tmp,
                )
        finally:
            server.stop()
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("webhook delivery failed: 500", result.stderr)

    def test_ac5_unreachable_webhook_exits_zero_within_5s(self) -> None:
        """AC#5: closed-port URL → exit 0 within 5 seconds, stderr logged."""
        port = find_unused_port()
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = _setup_repo_root(
                Path(tmp_str),
                webhook_url=f"http://127.0.0.1:{port}/hook",
            )
            import time
            start = time.monotonic()
            result = _run_cli(
                "escalate",
                "--ticket", "ARG1-099",
                "--severity", "blocking",
                "--raised-by", "orchestrator",
                "--body", "no listener",
                cwd=tmp,
                timeout=8.0,
            )
            elapsed = time.monotonic() - start
        self.assertEqual(result.returncode, 0, f"stderr={result.stderr!r}")
        self.assertIn("webhook delivery failed", result.stderr)
        self.assertLess(elapsed, 5.0, f"escalate took {elapsed:.2f}s; should be <5s")

    def test_ac6_invalid_severity_rejected(self) -> None:
        """AC#6: ``--severity invalid`` → non-zero, stderr names the rule."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = _setup_repo_root(Path(tmp_str), webhook_url=None)
            result = _run_cli(
                "escalate",
                "--ticket", "ARG1-099",
                "--severity", "invalid",
                "--body", "x",
                cwd=tmp,
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("severity must be blocking or advisory", result.stderr)

    def test_ac7_concurrent_calls_produce_distinct_files(self) -> None:
        """AC#7: two concurrent invocations produce two distinct files."""
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = _setup_repo_root(Path(tmp_str), webhook_url=None)
            results: list[subprocess.CompletedProcess] = []
            errors: list[BaseException] = []

            def worker() -> None:
                try:
                    res = _run_cli(
                        "escalate",
                        "--ticket", "ARG1-099",
                        "--severity", "blocking",
                        "--raised-by", "orchestrator",
                        "--body", "concurrent",
                        cwd=tmp,
                    )
                    results.append(res)
                except BaseException as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])
            self.assertEqual(len(results), 2)
            for res in results:
                self.assertEqual(
                    res.returncode, 0,
                    f"stderr={res.stderr!r}",
                )
            files = sorted((tmp / "argos" / "specs" / "escalations").glob("ARG1-099-*.md"))
            self.assertEqual(len(files), 2, f"expected 2 distinct files, got {files}")
            for path in files:
                self.assertEqual(escalation_validator.validate(path), [])

    def test_dispatcher_lists_escalate_in_help(self) -> None:
        result = _run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("escalate", result.stdout)


class FilenameRegexTests(unittest.TestCase):
    """The filename must match the schema's documented convention."""

    def test_filename_matches_schema_pattern(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_str:
            tmp = Path(tmp_str)
            path = escalation.write_escalation(
                ticket_id="ARG1-099",
                severity="blocking",
                raised_by="orchestrator",
                body="x",
                dest_dir=tmp,
            )
        # ARG1-099-YYYY-MM-DDTHH-MM-SSZ[.suffix].md
        self.assertRegex(
            path.name,
            r"^ARG1-099-\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}Z(-[0-9a-f]{4})?\.md$",
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
