"""Tests for argos.cli.config (loader) and argos.cli.commands.config (CLI).

Stdlib ``unittest`` only — no pytest. Run from repo root:

    python3 -m unittest argos.cli.tests.test_config -v

Covers ARG1-053 ACs #1, #4, #5, #6, #8, #9, #10. ACs #2 / #3 (template
key presence) and #7 (.gitignore content) are verified by external
shell commands in the ticket's Verification block; this file covers
their loader-side behaviour and the gitignore-helper invariants.
"""

from __future__ import annotations

import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

# argos/cli/tests/test_config.py
#   parents[0] = argos/cli/tests
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli import config as config_mod  # noqa: E402
from argos.cli._config_schema import KNOWN_KEYS  # noqa: E402
from argos.cli.config import (  # noqa: E402
    Config,
    ConfigParseError,
    KeyNotFoundError,
    _flatten,
    _parse_toml,
    _parse_toml_inhouse,
    ensure_gitignore_entry,
    load,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


_PROJECT_TEMPLATE = _REPO_ROOT / "argos" / "config.toml.template"
_LOCAL_TEMPLATE = _REPO_ROOT / ".argos" / "local.toml.template"
_SCHEMA_DOC = _REPO_ROOT / "argos" / "specs" / "v1.0" / "schemas" / "config.md"


SAMPLE_TOML = textwrap.dedent(
    """\
    # comment line
    [project]
    # project.name
    name = "argos"
    prefix = "ARG1"

    [orchestrator]
    max_parallel = 3
    independence_strategy = "plan-declared"
    dry_plan_cache = true

    [verifier]
    auto_fix_retries = 0  # inline comment

    [escalation]
    require_attend_before_merge = false
    """
)


def _make_temp_repo(
    tmpdir: Path,
    project_text: str | None = None,
    local_text: str | None = None,
) -> Path:
    """Materialize a fake repo root with ``argos/`` and ``.argos/`` layout.

    Always creates ``argos/`` and ``.argos/`` directories. If the
    ``*_text`` arg is provided, writes the corresponding concrete file
    (``argos/config.toml`` / ``.argos/local.toml``); otherwise writes
    only the template so the loader's template-fallback path is
    exercised.
    """
    (tmpdir / "argos").mkdir(parents=True, exist_ok=True)
    (tmpdir / ".argos").mkdir(parents=True, exist_ok=True)
    # Always copy templates so _find_repo_root identifies tmpdir as a
    # repo root via the template-marker rule.
    shutil.copy(_PROJECT_TEMPLATE, tmpdir / "argos" / "config.toml.template")
    shutil.copy(_LOCAL_TEMPLATE, tmpdir / ".argos" / "local.toml.template")
    if project_text is not None:
        (tmpdir / "argos" / "config.toml").write_text(project_text, encoding="utf-8")
    if local_text is not None:
        (tmpdir / ".argos" / "local.toml").write_text(local_text, encoding="utf-8")
    return tmpdir


# ---------------------------------------------------------------------------
# ParserTests — round-trip the in-house parser against tomllib
# ---------------------------------------------------------------------------


class ParserTests(unittest.TestCase):
    def test_inhouse_parser_yields_expected_shape(self) -> None:
        parsed = _parse_toml_inhouse(SAMPLE_TOML, "<sample>")
        self.assertEqual(parsed["project"]["name"], "argos")
        self.assertEqual(parsed["project"]["prefix"], "ARG1")
        self.assertEqual(parsed["orchestrator"]["max_parallel"], 3)
        self.assertEqual(
            parsed["orchestrator"]["independence_strategy"], "plan-declared"
        )
        self.assertIs(parsed["orchestrator"]["dry_plan_cache"], True)
        self.assertEqual(parsed["verifier"]["auto_fix_retries"], 0)
        self.assertIs(parsed["escalation"]["require_attend_before_merge"], False)

    @unittest.skipIf(
        sys.version_info < (3, 11),
        "tomllib is stdlib only on Python 3.11+",
    )
    def test_tomllib_and_inhouse_agree_on_supported_surface(self) -> None:
        import tomllib  # noqa: PLC0415  (skipped on <3.11)

        oracle = tomllib.loads(SAMPLE_TOML)
        inhouse = _parse_toml_inhouse(SAMPLE_TOML, "<sample>")
        self.assertEqual(inhouse, oracle)

    def test_inhouse_rejects_array(self) -> None:
        bad = "[verifier]\nminor_lint_rules = [\"a\", \"b\"]\n"
        with self.assertRaises(ConfigParseError) as ctx:
            _parse_toml_inhouse(bad, "<bad>")
        self.assertIn("array", str(ctx.exception))

    def test_inhouse_rejects_inline_table(self) -> None:
        bad = "[harness]\nbinary = { path = \"/x\" }\n"
        with self.assertRaises(ConfigParseError) as ctx:
            _parse_toml_inhouse(bad, "<bad>")
        self.assertIn("inline table", str(ctx.exception))

    def test_inhouse_rejects_multiline_string(self) -> None:
        bad = "[project]\nname = \"\"\"argos\"\"\"\n"
        with self.assertRaises(ConfigParseError) as ctx:
            _parse_toml_inhouse(bad, "<bad>")
        self.assertIn("multi-line", str(ctx.exception))

    def test_inhouse_rejects_key_outside_section(self) -> None:
        bad = "name = \"argos\"\n"
        with self.assertRaises(ConfigParseError) as ctx:
            _parse_toml_inhouse(bad, "<bad>")
        self.assertIn("outside any [section]", str(ctx.exception))

    def test_inhouse_carries_file_and_line_in_error(self) -> None:
        bad = "[a]\nname = \"ok\"\nbroken = [1, 2]\n"
        with self.assertRaises(ConfigParseError) as ctx:
            _parse_toml_inhouse(bad, "<source>")
        exc = ctx.exception
        self.assertEqual(exc.file, "<source>")
        self.assertEqual(exc.line, 3)

    def test_template_files_parse(self) -> None:
        """AC#1 — both shipped templates parse as valid TOML through _parse_toml."""
        proj = _parse_toml(
            _PROJECT_TEMPLATE.read_text(encoding="utf-8"), str(_PROJECT_TEMPLATE)
        )
        loc = _parse_toml(
            _LOCAL_TEMPLATE.read_text(encoding="utf-8"), str(_LOCAL_TEMPLATE)
        )
        self.assertEqual(proj["project"]["name"], "argos")
        self.assertEqual(proj["orchestrator"]["max_parallel"], 3)
        self.assertEqual(loc["operator"]["name"], "")
        self.assertEqual(loc["harness"]["claude_code_binary"], "claude")


# ---------------------------------------------------------------------------
# LoaderOverrideTests
# ---------------------------------------------------------------------------


class LoaderOverrideTests(unittest.TestCase):
    def test_local_overrides_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                local_text="[orchestrator]\nmax_parallel = 5\n",
            )
            cfg = load(
                project_path=root / "argos" / "config.toml.template",
                local_path=root / ".argos" / "local.toml",
                warn_stream=io.StringIO(),
            )
            self.assertEqual(cfg.get("orchestrator.max_parallel"), 5)

    def test_missing_local_falls_back_to_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))  # no concrete files
            cfg = load(
                project_path=root / "argos" / "config.toml.template",
                local_path=None,  # explicit override left to discovery (will hit template)
                warn_stream=io.StringIO(),
            )
            # Project default for max_parallel is 3.
            self.assertEqual(cfg.get("orchestrator.max_parallel"), 3)

    def test_missing_project_falls_back_to_template_via_discovery(self) -> None:
        # The CWD-walk discovery picks up the template when the concrete
        # file is absent. Verified via _resolve_project_path indirectly.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                cfg = load(warn_stream=io.StringIO())
            finally:
                os.chdir(old_cwd)
            self.assertEqual(cfg.get("orchestrator.max_parallel"), 3)
            self.assertEqual(cfg.get("project.name"), "argos")

    def test_get_unknown_key_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            cfg = load(
                project_path=root / "argos" / "config.toml.template",
                local_path=root / ".argos" / "local.toml.template",
                warn_stream=io.StringIO(),
            )
            with self.assertRaises(KeyNotFoundError) as ctx:
                cfg.get("nonexistent.key")
            self.assertEqual(ctx.exception.key, "nonexistent.key")


# ---------------------------------------------------------------------------
# UnknownKeyWarningTests
# ---------------------------------------------------------------------------


class UnknownKeyWarningTests(unittest.TestCase):
    def test_unknown_key_in_project_warns_but_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                project_text=(
                    "[orchestrator]\n"
                    "max_parallel = 3\n"
                    "future_key = \"x\"\n"
                ),
            )
            warn = io.StringIO()
            cfg = load(
                project_path=root / "argos" / "config.toml",
                local_path=root / ".argos" / "local.toml.template",
                warn_stream=warn,
            )
            text = warn.getvalue()
            self.assertIn("unknown config key", text)
            self.assertIn("orchestrator.future_key", text)
            # Loader still returns a usable Config.
            self.assertEqual(cfg.get("orchestrator.max_parallel"), 3)

    def test_unknown_key_in_local_warns_but_loads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                local_text=(
                    "[telemetry]\n"
                    "opt_in = true\n"
                    "future_flag = false\n"
                ),
            )
            warn = io.StringIO()
            cfg = load(
                project_path=root / "argos" / "config.toml.template",
                local_path=root / ".argos" / "local.toml",
                warn_stream=warn,
            )
            text = warn.getvalue()
            self.assertIn("unknown config key", text)
            self.assertIn("telemetry.future_flag", text)
            self.assertIs(cfg.get("telemetry.opt_in"), True)


# ---------------------------------------------------------------------------
# ValidateTests
# ---------------------------------------------------------------------------


class ValidateTests(unittest.TestCase):
    def test_clean_config_validates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            cfg = load(
                project_path=root / "argos" / "config.toml.template",
                local_path=root / ".argos" / "local.toml.template",
                warn_stream=io.StringIO(),
            )
            self.assertEqual(cfg.validate(), [])

    def test_non_int_max_parallel_emits_type_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                project_text=(
                    "[project]\nname = \"argos\"\nprefix = \"ARG1\"\n"
                    "[orchestrator]\n"
                    "max_parallel = \"three\"\n"
                    "independence_strategy = \"plan-declared\"\n"
                ),
            )
            cfg = load(
                project_path=root / "argos" / "config.toml",
                local_path=root / ".argos" / "local.toml.template",
                warn_stream=io.StringIO(),
            )
            errors = cfg.validate()
            self.assertTrue(errors, "expected at least one error")
            joined = "\n".join(errors)
            self.assertIn("orchestrator.max_parallel", joined)
            self.assertIn("type mismatch", joined)
            self.assertIn("expected int", joined)

    def test_bool_value_for_int_key_is_a_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                project_text=(
                    "[project]\nname = \"argos\"\nprefix = \"ARG1\"\n"
                    "[orchestrator]\n"
                    "max_parallel = true\n"
                    "independence_strategy = \"plan-declared\"\n"
                ),
            )
            cfg = load(
                project_path=root / "argos" / "config.toml",
                local_path=root / ".argos" / "local.toml.template",
                warn_stream=io.StringIO(),
            )
            errors = cfg.validate()
            self.assertTrue(any("orchestrator.max_parallel" in e for e in errors))


# ---------------------------------------------------------------------------
# GitignoreHelperTests
# ---------------------------------------------------------------------------


class GitignoreHelperTests(unittest.TestCase):
    def test_appends_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("# stuff\nnode_modules/\n", encoding="utf-8")
            ensure_gitignore_entry(root)
            text = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".argos/", text)
            # Whole-line match — not just a substring of another path.
            lines = text.splitlines()
            self.assertIn(".argos/", lines)

    def test_noop_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            initial = "# stuff\n.argos/\nnode_modules/\n"
            (root / ".gitignore").write_text(initial, encoding="utf-8")
            ensure_gitignore_entry(root)
            self.assertEqual(
                (root / ".gitignore").read_text(encoding="utf-8"),
                initial,
            )

    def test_idempotent_across_two_calls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("# stuff\n", encoding="utf-8")
            ensure_gitignore_entry(root)
            after_first = (root / ".gitignore").read_text(encoding="utf-8")
            ensure_gitignore_entry(root)
            after_second = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(after_first, after_second)
            # Exactly one occurrence.
            self.assertEqual(after_second.count(".argos/\n"), 1)

    def test_creates_file_when_absent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ensure_gitignore_entry(root)
            text = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertEqual(text, ".argos/\n")


# ---------------------------------------------------------------------------
# CLISubcommandTests — subprocess against `python3 -m argos.cli config ...`
# ---------------------------------------------------------------------------


class CLISubcommandTests(unittest.TestCase):
    def _run(
        self,
        tmp_root: Path,
        args: list[str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "argos.cli", "config", *args],
            capture_output=True,
            text=True,
            cwd=str(tmp_root),
            env={**os.environ, "PYTHONPATH": str(_REPO_ROOT)},
            check=False,
        )

    def test_get_default_max_parallel(self) -> None:
        # AC#4 — `argos config get orchestrator.max_parallel` prints `3`.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            proc = self._run(root, ["get", "orchestrator.max_parallel"])
            self.assertEqual(
                proc.returncode, 0,
                f"stderr={proc.stderr!r} stdout={proc.stdout!r}",
            )
            self.assertEqual(proc.stdout, "3\n")

    def test_local_override_visible_in_get(self) -> None:
        # AC#5 — local override of orchestrator.max_parallel = 5.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                local_text="[orchestrator]\nmax_parallel = 5\n",
            )
            proc = self._run(root, ["get", "orchestrator.max_parallel"])
            self.assertEqual(proc.returncode, 0, f"stderr={proc.stderr!r}")
            self.assertEqual(proc.stdout, "5\n")

    def test_get_missing_key_exits_nonzero(self) -> None:
        # AC#6 — `argos config get nonexistent.key` exits non-zero, stderr
        # contains `key not found`.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            proc = self._run(root, ["get", "nonexistent.key"])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("key not found", proc.stderr)

    def test_validate_clean_exits_zero(self) -> None:
        # AC#8 — clean config validates.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(Path(tmp))
            proc = self._run(root, ["validate"])
            self.assertEqual(
                proc.returncode, 0,
                f"stderr={proc.stderr!r} stdout={proc.stdout!r}",
            )

    def test_validate_bad_type_exits_nonzero(self) -> None:
        # AC#8 — non-int orchestrator.max_parallel produces a typed error.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                project_text=(
                    "[project]\nname = \"argos\"\nprefix = \"ARG1\"\n"
                    "[orchestrator]\n"
                    "max_parallel = \"three\"\n"
                    "independence_strategy = \"plan-declared\"\n"
                ),
            )
            proc = self._run(root, ["validate"])
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("orchestrator.max_parallel", proc.stderr)
            self.assertIn("type mismatch", proc.stderr)

    def test_unknown_key_does_not_break_get(self) -> None:
        # AC#9 — unknown key emits stderr warning but command exits 0.
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_temp_repo(
                Path(tmp),
                project_text=(
                    "[project]\nname = \"argos\"\nprefix = \"ARG1\"\n"
                    "[orchestrator]\n"
                    "max_parallel = 3\n"
                    "independence_strategy = \"plan-declared\"\n"
                    "future_key = \"x\"\n"
                ),
            )
            proc = self._run(root, ["get", "orchestrator.max_parallel"])
            self.assertEqual(
                proc.returncode, 0,
                f"stderr={proc.stderr!r} stdout={proc.stdout!r}",
            )
            self.assertEqual(proc.stdout, "3\n")
            self.assertIn("unknown config key", proc.stderr)


# ---------------------------------------------------------------------------
# SchemaDocConsistencyTests — schema doc tables match KNOWN_KEYS
# ---------------------------------------------------------------------------


_TABLE_KEY_RE = __import__("re").compile(r"^\|\s*`([a-z][a-z0-9_.]*)`\s*\|")


class SchemaDocConsistencyTests(unittest.TestCase):
    def _parse_doc_keys(self) -> set[str]:
        text = _SCHEMA_DOC.read_text(encoding="utf-8")
        keys: set[str] = set()
        for line in text.splitlines():
            m = _TABLE_KEY_RE.match(line)
            if m:
                keys.add(m.group(1))
        return keys

    def test_doc_key_set_matches_known_keys(self) -> None:
        doc_keys = self._parse_doc_keys()
        code_keys = set(KNOWN_KEYS.keys())
        # Symmetric difference makes drift visible in the failure message.
        missing_in_doc = code_keys - doc_keys
        missing_in_code = doc_keys - code_keys
        self.assertEqual(
            missing_in_doc, set(),
            f"keys in KNOWN_KEYS but absent from schema doc: {missing_in_doc}",
        )
        self.assertEqual(
            missing_in_code, set(),
            f"keys in schema doc but absent from KNOWN_KEYS: {missing_in_code}",
        )

    def test_doc_includes_both_files(self) -> None:
        text = _SCHEMA_DOC.read_text(encoding="utf-8")
        self.assertIn("argos/config.toml", text)
        self.assertIn(".argos/local.toml", text)


if __name__ == "__main__":
    unittest.main()
