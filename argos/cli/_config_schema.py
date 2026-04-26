"""Machine-readable mirror of the v1.0 config schema.

Source of truth: ``argos/specs/v1.0/schemas/config.md``.

This module is the derived file referenced by AC#10 of ARG1-053: the
loader's known-key set is sourced from the schema doc via this mirror.
There is no build-time generator at this scale; editors who change the
schema doc must update ``KNOWN_KEYS`` here in the same commit. The
``SchemaDocConsistencyTests`` class in
``argos/cli/tests/test_config.py`` parses the tables in the schema doc
and asserts the key set matches ``KNOWN_KEYS``. Drift fails CI.

Keys are flat dotted strings (``section.key``); the type is the Python
type that ``Config.validate()`` checks against (``str``, ``int``,
``bool``). The mapping is intentionally small: array / inline-table /
datetime values are out of scope until a consumer needs them.
"""

from __future__ import annotations

# Project-level keys (live in argos/config.toml).
PROJECT_KEYS: dict[str, type] = {
    "project.name": str,
    "project.prefix": str,
    "orchestrator.max_parallel": int,
    "orchestrator.independence_strategy": str,
    "orchestrator.dry_plan_cache": bool,
    "verifier.auto_fix_retries": int,
    "escalation.require_attend_before_merge": bool,
}

# Per-developer keys (live in .argos/local.toml).
LOCAL_KEYS: dict[str, type] = {
    "operator.name": str,
    "operator.email": str,
    "escalation.webhook_url": str,
    "harness.claude_code_binary": str,
    "harness.session_timeout_seconds": int,
    "telemetry.opt_in": bool,
}

# Union view used by the loader for unknown-key warnings and by
# ``Config.validate()`` for type checks. A dotted key may legitimately
# appear in either file (e.g. ``escalation.*`` keys split across both),
# but no key is repeated within KNOWN_KEYS itself.
KNOWN_KEYS: dict[str, type] = {**PROJECT_KEYS, **LOCAL_KEYS}
