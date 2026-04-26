"""Reference parser for the v1.0 verifier-output structured block.

Schema: argos/specs/v1.0/schemas/verifier-output.md.
Invocation: python3 -m argos.cli.verifier_parser <path>
            (or via the argos shim: argos verifier-parse <path>)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

VALID_SEVERITIES = {"critical", "major", "minor"}
VALID_DECISIONS = {"pass", "pass-with-minors", "fail"}

BLOCK_OPEN = "<!-- argos:verifier-output -->"
BLOCK_CLOSE = "<!-- /argos:verifier-output -->"


class SchemaError(ValueError):
    pass


def extract_block(text: str) -> str:
    start = text.find(BLOCK_OPEN)
    if start == -1:
        raise SchemaError(f"missing opening marker: {BLOCK_OPEN}")
    start += len(BLOCK_OPEN)
    end = text.find(BLOCK_CLOSE, start)
    if end == -1:
        raise SchemaError(f"missing closing marker: {BLOCK_CLOSE}")
    return text[start:end].strip("\n")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def parse_block(block_text: str) -> dict:
    """Parse the simple key/value + list grammar defined in the schema doc."""
    parsed: dict = {}
    findings: list = []
    current: dict | None = None
    in_findings = False

    for raw in block_text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue

        # top-level keys: tests_ran, findings, decision
        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if m and not line.startswith(" "):
            key, value = m.group(1), m.group(2).strip()
            if key == "tests_ran":
                if value not in {"true", "false"}:
                    raise SchemaError(f"tests_ran must be true|false, got {value!r}")
                parsed["tests_ran"] = value == "true"
                in_findings = False
            elif key == "findings":
                in_findings = True
                if value == "[]":
                    in_findings = False
                elif value:
                    raise SchemaError(
                        "findings: must be '[]' or followed by indented list items"
                    )
            elif key == "decision":
                parsed["decision"] = value
                in_findings = False
            else:
                raise SchemaError(f"unknown top-level key: {key!r}")
            current = None
            continue

        if not in_findings:
            raise SchemaError(f"unexpected line outside findings: {line!r}")

        # findings list items
        item_start = re.match(r"^  - severity:\s*(\S+)\s*$", line)
        if item_start:
            current = {"severity": item_start.group(1)}
            findings.append(current)
            continue

        sub = re.match(r"^    ([a-z_]+):\s*(.*)$", line)
        if sub and current is not None:
            sub_key, sub_value = sub.group(1), sub.group(2)
            if sub_key not in {"description", "file"}:
                raise SchemaError(f"unknown finding key: {sub_key!r}")
            current[sub_key] = _strip_quotes(sub_value)
            continue

        raise SchemaError(f"could not parse line: {line!r}")

    parsed["findings"] = findings
    return parsed


def validate(parsed: dict) -> None:
    for key in ("tests_ran", "findings", "decision"):
        if key not in parsed:
            raise SchemaError(f"missing required key: {key}")

    decision = parsed["decision"]
    if decision not in VALID_DECISIONS:
        raise SchemaError(
            f"decision must be one of {sorted(VALID_DECISIONS)}, got {decision!r}"
        )

    for idx, f in enumerate(parsed["findings"]):
        sev = f.get("severity")
        if sev not in VALID_SEVERITIES:
            raise SchemaError(
                f"finding[{idx}] severity must be one of "
                f"{sorted(VALID_SEVERITIES)}, got {sev!r}"
            )
        desc = f.get("description", "").strip()
        if not desc:
            raise SchemaError(f"finding[{idx}] missing non-empty description")

    tests_ran = parsed["tests_ran"]
    severities = {f["severity"] for f in parsed["findings"]}

    if not tests_ran and decision != "fail":
        raise SchemaError(
            "tests_ran=false requires decision=fail "
            "(verifier may not classify a missing test run as pass)"
        )
    if decision == "pass" and parsed["findings"]:
        raise SchemaError("decision=pass requires findings: []")
    if decision == "pass-with-minors":
        if not parsed["findings"]:
            raise SchemaError("decision=pass-with-minors requires ≥1 minor finding")
        if severities - {"minor"}:
            raise SchemaError(
                "decision=pass-with-minors forbids critical/major findings"
            )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: verifier_parser <path>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"unreadable: {path}: {exc}", file=sys.stderr)
        return 1

    try:
        block = extract_block(text)
        parsed = parse_block(block)
        validate(parsed)
    except SchemaError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return 2

    json.dump(parsed, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
