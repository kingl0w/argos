"""Reference validator for Argos escalation files.

Schema: argos/specs/v1.0/schemas/escalation.md
        (see also ARCHITECTURE.md §Components/Escalation Channel)

This module validates a single escalation markdown file against the v1.0
schema: required frontmatter fields, allowed enum values for `severity` and
`raised_by`, ISO-8601 parsing of `created`, and presence of the four required
H2 body sections.

Provisional language pending ADR-001 (ARG1-001); port if ADR names a
different language. Stdlib only — no third-party dependencies. The companion
shell shim `argos/cli/escalation-validate` is the AC-compatibility surface
until the unified `argos` CLI dispatcher (ARG1-001) lands.

Exit codes (when invoked via `python3 -m argos.cli.escalation_validator`):
  0  valid
  1  parses but fails validation; stderr lists each failure, one per line
  2  missing/unreadable file or unparseable frontmatter; stderr names the
     path and the parse-level reason
"""

from __future__ import annotations

import argparse
import datetime
import pathlib
import re
import sys


ALLOWED_SEVERITY = {"blocking", "advisory"}
ALLOWED_RAISED_BY = {"orchestrator", "planner", "coder", "watchdog", "verifier"}
REQUIRED_FRONTMATTER_KEYS = ("ticket_id", "session_id", "severity", "raised_by", "created")
REQUIRED_BODY_SECTIONS = ("## Question", "## Context", "## Options considered", "## Why escalated")

_FRONTMATTER_LINE_RE = re.compile(r"^([a-z_]+):\s*(.+?)\s*$")
_DELIMITER_RE = re.compile(r"^---\s*$")
_HTML_COMMENT_LINE_RE = re.compile(r"^\s*<!--.*-->\s*$")


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split `text` into (frontmatter_dict, body_string).

    The frontmatter is the region between the first two `---` lines (each on
    its own line). Leading blank lines and single-line HTML comments
    (``<!-- ... -->``) before the opening delimiter are tolerated — a
    producer may emit a marker comment at the top of the file. Each
    non-empty frontmatter line must match ``^([a-z_]+):\\s*(.+?)\\s*$``.
    Raises ``ValueError`` on missing or malformed delimiters or any
    non-matching line.
    """
    lines = text.splitlines()
    # Locate the opening delimiter. Skip leading blank lines and
    # single-line HTML comments; reject anything else before the delimiter.
    open_idx: int | None = None
    for i, line in enumerate(lines):
        if line.strip() == "":
            continue
        if _HTML_COMMENT_LINE_RE.match(line):
            continue
        if _DELIMITER_RE.match(line):
            open_idx = i
            break
        raise ValueError(
            f"frontmatter must begin with a '---' delimiter on its own line "
            f"(found {line!r} at line {i + 1})"
        )
    if open_idx is None:
        raise ValueError("frontmatter missing: file has no '---' delimiter")

    # Locate the closing delimiter.
    close_idx: int | None = None
    for j in range(open_idx + 1, len(lines)):
        if _DELIMITER_RE.match(lines[j]):
            close_idx = j
            break
    if close_idx is None:
        raise ValueError("frontmatter missing closing '---' delimiter")

    fm: dict[str, str] = {}
    for k in range(open_idx + 1, close_idx):
        raw = lines[k]
        if raw.strip() == "":
            # Tolerate blank lines inside the frontmatter region — they
            # carry no key/value but are not malformed.
            continue
        m = _FRONTMATTER_LINE_RE.match(raw)
        if not m:
            raise ValueError(
                f"frontmatter line {k + 1} does not match 'key: value' "
                f"(got {raw!r})"
            )
        key, value = m.group(1), m.group(2)
        if key in fm:
            raise ValueError(f"frontmatter key {key!r} repeated")
        fm[key] = value

    body = "\n".join(lines[close_idx + 1:])
    return fm, body


def validate(path: pathlib.Path) -> list[str]:
    """Validate the escalation file at `path`.

    Returns a list of human-readable error strings; an empty list means the
    file conforms to the schema. Raises ``FileNotFoundError`` /
    ``OSError`` if the file cannot be read, and ``ValueError`` if the
    frontmatter cannot be parsed — callers (``main``) translate those into
    exit code 2.
    """
    text = path.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)

    errors: list[str] = []

    # Required frontmatter keys.
    for key in REQUIRED_FRONTMATTER_KEYS:
        if key not in fm:
            errors.append(f"{key}: required frontmatter field missing")
        elif fm[key] == "":
            errors.append(f"{key}: required frontmatter field is empty")

    # Severity enum.
    if "severity" in fm and fm["severity"] != "":
        if fm["severity"] not in ALLOWED_SEVERITY:
            allowed = ", ".join(sorted(ALLOWED_SEVERITY))
            errors.append(
                f"severity: invalid value {fm['severity']!r} "
                f"(allowed: {allowed})"
            )

    # Raised-by enum.
    if "raised_by" in fm and fm["raised_by"] != "":
        if fm["raised_by"] not in ALLOWED_RAISED_BY:
            allowed = ", ".join(sorted(ALLOWED_RAISED_BY))
            errors.append(
                f"raised_by: invalid value {fm['raised_by']!r} "
                f"(allowed: {allowed})"
            )

    # `created` ISO-8601 parse.
    if "created" in fm and fm["created"] != "":
        try:
            datetime.datetime.fromisoformat(fm["created"])
        except ValueError as exc:
            errors.append(
                f"created: not a valid ISO-8601 timestamp ({fm['created']!r}): {exc}"
            )

    # Required body sections — each heading appears at least once on its
    # own line.
    body_lines = body.splitlines()
    body_line_set = {line.rstrip() for line in body_lines}
    for section in REQUIRED_BODY_SECTIONS:
        # Match exact heading on its own line. Trailing whitespace tolerated.
        present = any(line.strip() == section for line in body_lines)
        if not present and section not in body_line_set:
            errors.append(f"{section}: required body section missing")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="escalation-validate",
        description=(
            "Validate an Argos escalation file against the v1.0 schema "
            "(argos/specs/v1.0/schemas/escalation.md). Silent on success; "
            "errors go to stderr."
        ),
    )
    parser.add_argument("path", help="Path to the escalation markdown file.")
    args = parser.parse_args(argv)

    path = pathlib.Path(args.path)

    try:
        errors = validate(path)
    except FileNotFoundError:
        print(f"{path}: file not found", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"{path}: cannot read file: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"{path}: cannot parse frontmatter: {exc}", file=sys.stderr)
        return 2

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
