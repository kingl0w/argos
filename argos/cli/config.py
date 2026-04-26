"""Loader for the v1.0 config split.

Schema: argos/specs/v1.0/schemas/config.md
        (see also ARCHITECTURE.md §Contracts/Config split)

Reads two TOML files — ``argos/config.toml`` (project-level, committed)
and ``.argos/local.toml`` (per-developer, gitignored) — and presents a
single dotted-key view via :class:`Config`. Local keys override project
keys on collision.

ADR-001 pins Argos to **Python ≥3.9, stdlib-only** (no ``tomli``). This
loader uses :mod:`tomllib` when available (3.11+) and an in-house regex
mini-parser on 3.9/3.10. Both produce the same
``{section: {key: typed_value}}`` shape for the supported surface
(strings, ints, bools, two-level section headers).

Public surface:

- :func:`load` — assemble a :class:`Config` from project + local files.
- :class:`Config` — get / validate dotted keys.
- :func:`ensure_gitignore_entry` — idempotent ``.argos/`` append helper
  (called by ``argos init`` when ARG1-002 lands).

Exception classes:

- :class:`ConfigError` (base)
- :class:`ConfigParseError` — raised by the mini-parser on unsupported
  TOML (arrays, inline tables, multi-line strings, datetimes).
- :class:`KeyNotFoundError` — raised by ``Config.get`` on misses.
- :class:`TypeMismatchError` — recorded by ``Config.validate`` (not
  raised; returned as a string in the error list).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

from argos.cli._config_schema import KNOWN_KEYS

__all__ = [
    "Config",
    "ConfigError",
    "ConfigParseError",
    "KeyNotFoundError",
    "TypeMismatchError",
    "load",
    "ensure_gitignore_entry",
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Base class for config loader errors."""


class ConfigParseError(ConfigError):
    """The in-house TOML mini-parser rejected an input.

    Carries the source filename, the 1-indexed line number, and a
    human-readable reason. ``str(exc)`` is suitable for stderr output.
    """

    def __init__(self, file: str, line: int, reason: str) -> None:
        self.file = file
        self.line = line
        self.reason = reason
        super().__init__(f"{file}:{line}: {reason}")


class KeyNotFoundError(ConfigError):
    """``Config.get(dotted_key)`` was called with a key not present."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"key not found: {key}")


class TypeMismatchError(ConfigError):
    """A KNOWN_KEYS entry has a value of the wrong type.

    Not raised by the loader at load time — surfaced via
    ``Config.validate()`` as a string. Kept as a class so callers may
    still raise it if they wish.
    """

    def __init__(self, key: str, expected: type, got: type) -> None:
        self.key = key
        self.expected = expected
        self.got = got
        super().__init__(
            f"type mismatch for {key}: expected {expected.__name__}, "
            f"got {got.__name__}"
        )


# ---------------------------------------------------------------------------
# In-house TOML mini-parser (3.9/3.10 fallback for ADR-001 stdlib-only)
# ---------------------------------------------------------------------------

# Section header: [name] or [name.subname]. One nesting level only.
_SECTION_RE = re.compile(r"^\[\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*\]\s*(?:#.*)?$")
# key = value with optional trailing comment.
_KV_RE = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(.+?)\s*$")
# A quoted string value (no escapes beyond \" — narrow surface).
_STRING_RE = re.compile(r'^"((?:[^"\\]|\\.)*)"$')
# An integer (optional leading minus, no underscores).
_INT_RE = re.compile(r"^-?\d+$")


def _strip_inline_comment(value: str) -> str:
    """Strip a trailing ``# ...`` comment from a value, respecting quoted strings.

    Walks character-by-character so a ``#`` inside a quoted string is not
    treated as a comment marker.
    """
    out: list[str] = []
    in_string = False
    escape = False
    for ch in value:
        if escape:
            out.append(ch)
            escape = False
            continue
        if ch == "\\" and in_string:
            out.append(ch)
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            out.append(ch)
            continue
        if ch == "#" and not in_string:
            break
        out.append(ch)
    return "".join(out).rstrip()


def _parse_value(raw: str, file: str, line_no: int) -> Any:
    """Parse a single TOML scalar value. Rejects unsupported constructs."""
    raw = raw.strip()
    if not raw:
        raise ConfigParseError(file, line_no, "empty value")
    # Reject arrays, inline tables, multi-line strings up front.
    if raw.startswith("["):
        raise ConfigParseError(
            file, line_no, "array values are not supported by the in-house parser"
        )
    if raw.startswith("{"):
        raise ConfigParseError(
            file, line_no, "inline tables are not supported by the in-house parser"
        )
    if raw.startswith('"""') or raw.startswith("'''"):
        raise ConfigParseError(
            file, line_no, "multi-line strings are not supported by the in-house parser"
        )
    # Bool.
    if raw == "true":
        return True
    if raw == "false":
        return False
    # Int.
    if _INT_RE.match(raw):
        return int(raw)
    # Quoted string.
    m = _STRING_RE.match(raw)
    if m:
        # Minimal escape handling — \" and \\.
        return m.group(1).replace('\\"', '"').replace("\\\\", "\\")
    # Reject single-quoted (literal) strings — narrow surface keeps the
    # parser simple; nothing in the schema needs them.
    if raw.startswith("'"):
        raise ConfigParseError(
            file, line_no, "literal (single-quoted) strings are not supported"
        )
    # Anything else (bare words, datetimes, floats) is rejected.
    raise ConfigParseError(
        file, line_no, f"unrecognized value {raw!r}"
    )


def _parse_toml_inhouse(text: str, source: str) -> dict[str, dict[str, Any]]:
    """Parse a narrow TOML subset. Returns ``{section: {key: value}}``.

    Supports section headers (one nesting level), flat ``key = value``
    pairs (string / int / bool), comments, blank lines. Rejects
    everything else with :class:`ConfigParseError`.
    """
    result: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None
    current_name: str | None = None

    for idx, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip()
        # Strip leading whitespace for matching, but keep the original
        # line number in error messages.
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        m_section = _SECTION_RE.match(stripped)
        if m_section:
            name = m_section.group(1)
            # Build nested dict for "a.b" headers.
            if "." in name:
                top, sub = name.split(".", 1)
                top_dict = result.setdefault(top, {})
                if not isinstance(top_dict, dict):
                    raise ConfigParseError(
                        source, idx, f"section {top!r} already has a non-table value"
                    )
                current = top_dict.setdefault(sub, {})
                current_name = name
            else:
                current = result.setdefault(name, {})
                current_name = name
            continue
        m_kv = _KV_RE.match(stripped)
        if m_kv:
            key = m_kv.group(1)
            value_part = _strip_inline_comment(m_kv.group(2))
            value = _parse_value(value_part, source, idx)
            if current is None:
                # Bare top-level key (not under any [section]). The
                # schema does not use these; reject for clarity.
                raise ConfigParseError(
                    source, idx,
                    f"key {key!r} appears outside any [section]"
                )
            if "." in key:
                # Dotted keys outside section headers are not supported.
                raise ConfigParseError(
                    source, idx,
                    "dotted keys outside section headers are not supported"
                )
            current[key] = value
            continue
        raise ConfigParseError(source, idx, f"unparseable line: {raw_line!r}")

    return result


def _parse_toml(text: str, source: str) -> dict[str, dict[str, Any]]:
    """Parse a TOML string.

    Uses :mod:`tomllib` on Python 3.11+, the in-house mini-parser
    otherwise. Both produce the same ``{section: {key: value}}`` shape
    for the supported surface (see ``argos/specs/v1.0/schemas/config.md``).
    """
    if sys.version_info >= (3, 11):
        import tomllib  # stdlib on 3.11+
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            # Surface a uniform ConfigParseError; tomllib's exception
            # message includes a line number we don't try to extract.
            raise ConfigParseError(source, 0, f"TOML decode error: {exc}") from exc
        # tomllib happily accepts arrays/inline-tables/datetimes; we do
        # NOT reject them here at the loader level (the in-house parser
        # rejects to keep the contract tight on 3.9/3.10, but on 3.11+
        # it would be surprising to fail on valid TOML). Unknown keys
        # warn downstream regardless.
        return data
    return _parse_toml_inhouse(text, source)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _find_repo_root(start: Path) -> Path | None:
    """Walk up from ``start`` looking for a directory that contains either
    ``argos/config.toml`` or ``argos/config.toml.template`` (the marker
    that says "this is an Argos repo root"). Returns the first such
    directory or ``None``.
    """
    cur = start.resolve()
    while True:
        if (cur / "argos" / "config.toml").is_file():
            return cur
        if (cur / "argos" / "config.toml.template").is_file():
            return cur
        if cur.parent == cur:
            return None
        cur = cur.parent


def _resolve_project_path(explicit: Path | None) -> Path | None:
    """Pick the project-level TOML file to read.

    Order: explicit override → ``argos/config.toml`` under repo root →
    ``argos/config.toml.template`` under repo root → ``None``.
    """
    if explicit is not None:
        return explicit
    root = _find_repo_root(Path.cwd())
    if root is None:
        return None
    concrete = root / "argos" / "config.toml"
    if concrete.is_file():
        return concrete
    template = root / "argos" / "config.toml.template"
    if template.is_file():
        return template
    return None


def _resolve_local_path(explicit: Path | None) -> Path | None:
    """Pick the per-developer TOML file to read.

    Order: explicit override → ``.argos/local.toml`` under repo root →
    ``.argos/local.toml.template`` under repo root → ``None``.
    """
    if explicit is not None:
        return explicit
    root = _find_repo_root(Path.cwd())
    if root is None:
        return None
    concrete = root / ".argos" / "local.toml"
    if concrete.is_file():
        return concrete
    template = root / ".argos" / "local.toml.template"
    if template.is_file():
        return template
    return None


# ---------------------------------------------------------------------------
# Config object
# ---------------------------------------------------------------------------


def _flatten(parsed: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Flatten ``{section: {key: value}}`` to ``{section.key: value}``.

    For two-level headers (``[a.b]``) the result emits ``a.b.key``.
    """
    out: dict[str, Any] = {}
    for section, body in parsed.items():
        if not isinstance(body, dict):
            # Top-level scalar — schema does not use these, but be
            # defensive and emit it under its bare name so unknown-key
            # warnings can flag it.
            out[section] = body
            continue
        for key, value in body.items():
            if isinstance(value, dict):
                # Nested table from tomllib (e.g. [a.b]).
                for sub_key, sub_value in value.items():
                    out[f"{section}.{key}.{sub_key}"] = sub_value
            else:
                out[f"{section}.{key}"] = value
    return out


class Config:
    """Loaded view of the project + local TOML files.

    ``Config`` is a thin wrapper around a flat ``{dotted_key: value}``
    dict. Local keys override project keys on collision. Use
    :meth:`get` to fetch a value (raises :class:`KeyNotFoundError` on
    miss) and :meth:`validate` to type-check known keys.
    """

    def __init__(
        self,
        project: dict[str, Any] | None = None,
        local: dict[str, Any] | None = None,
    ) -> None:
        self._project: dict[str, Any] = dict(project or {})
        self._local: dict[str, Any] = dict(local or {})
        self._merged: dict[str, Any] = {**self._project, **self._local}

    def get(self, dotted_key: str) -> Any:
        if dotted_key not in self._merged:
            raise KeyNotFoundError(dotted_key)
        return self._merged[dotted_key]

    def has(self, dotted_key: str) -> bool:
        return dotted_key in self._merged

    def keys(self) -> list[str]:
        return list(self._merged.keys())

    def validate(self) -> list[str]:
        """Return a list of human-readable validation errors (empty = clean).

        Type-checks every key present in :data:`KNOWN_KEYS`. Booleans
        are NOT treated as integers (Python's ``isinstance(True, int)``
        quirk is filtered out). Unknown keys are skipped — they are
        warned about at load time but cannot fail validation.
        """
        errors: list[str] = []
        for key, expected in KNOWN_KEYS.items():
            if key not in self._merged:
                continue
            value = self._merged[key]
            actual = type(value)
            # Filter the bool-is-int quirk both ways.
            if expected is int and isinstance(value, bool):
                errors.append(
                    str(TypeMismatchError(key, expected, bool))
                )
                continue
            if expected is bool and not isinstance(value, bool):
                errors.append(
                    str(TypeMismatchError(key, expected, actual))
                )
                continue
            if expected is str and not isinstance(value, str):
                errors.append(
                    str(TypeMismatchError(key, expected, actual))
                )
                continue
            if expected is int and not isinstance(value, int):
                errors.append(
                    str(TypeMismatchError(key, expected, actual))
                )
                continue
        return errors


# ---------------------------------------------------------------------------
# Public load() entry point
# ---------------------------------------------------------------------------


def _read_and_flatten(
    path: Path | None,
    label: str,
    warn_stream,
) -> dict[str, Any]:
    """Read ``path``, parse it, flatten to dotted keys, warn on unknowns.

    Returns ``{}`` if ``path`` is ``None``.
    """
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8")
    parsed = _parse_toml(text, str(path))
    flat = _flatten(parsed)
    for key in flat:
        if key not in KNOWN_KEYS:
            warn_stream.write(
                f"unknown config key: {key} (in {path})\n"
            )
    return flat


def load(
    project_path: Path | None = None,
    local_path: Path | None = None,
    warn_stream=None,
) -> Config:
    """Load the project + local config pair.

    If either ``project_path`` or ``local_path`` is omitted, the loader
    walks up from CWD looking for an Argos repo root and uses the
    concrete TOML file if present, falling back to the template.
    Missing-on-disk files are silently treated as empty (the loader
    does not require either file to exist).

    Unknown keys produce a stderr warning prefixed
    ``unknown config key:`` but do not fail the load (per AC#9).
    """
    if warn_stream is None:
        warn_stream = sys.stderr
    project_resolved = _resolve_project_path(project_path)
    local_resolved = _resolve_local_path(local_path)

    project_flat = _read_and_flatten(project_resolved, "project", warn_stream)
    local_flat = _read_and_flatten(local_resolved, "local", warn_stream)

    return Config(project=project_flat, local=local_flat)


# ---------------------------------------------------------------------------
# .gitignore helper
# ---------------------------------------------------------------------------


def ensure_gitignore_entry(repo_root: Path, line: str = ".argos/") -> None:
    """Append ``line`` to ``<repo_root>/.gitignore`` if not already present.

    Idempotent: if the file already contains a matching whole-line
    entry (``grep -Fxq``), this is a no-op. If the file does not
    exist, it is created with a single line. A trailing newline is
    always written so the file ends cleanly.

    This helper exists so ``argos init`` (ARG1-002) can call it; it is
    also exercised directly by ``GitignoreHelperTests`` in
    ``argos/cli/tests/test_config.py``.
    """
    gitignore = repo_root / ".gitignore"
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8").splitlines()
        if any(existing_line.strip() == line for existing_line in existing):
            return
        # Append, preserving any existing trailing newline state.
        suffix = "" if gitignore.read_text(encoding="utf-8").endswith("\n") else "\n"
        with gitignore.open("a", encoding="utf-8") as fh:
            fh.write(f"{suffix}{line}\n")
        return
    gitignore.write_text(f"{line}\n", encoding="utf-8")
