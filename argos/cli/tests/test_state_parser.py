"""Tests for ``argos.cli.state_parser`` and the ``state-parse`` CLI shim.

Fixture paths are resolved relative to ``__file__`` so the tests run regardless
of the directory pytest is invoked from.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Make ``argos.cli...`` importable when pytest is invoked from anywhere.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from argos.cli.state_parser import (  # noqa: E402  (sys.path tweak above)
    Block,
    DuplicateIdError,
    MalformedOpenTagError,
    MissingAttributeError,
    UnclosedEntryError,
    parse,
    parse_file,
)

# argos/cli/tests/test_state_parser.py
#   parents[0] = argos/cli/tests
#   parents[1] = argos/cli
#   parents[2] = argos
#   parents[3] = repo root
_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "specs"
    / "v1.0"
    / "schemas"
    / "examples"
)


def _fixture(name: str) -> Path:
    p = _FIXTURES / name
    assert p.exists(), f"fixture missing: {p}"
    return p


# ---------------------------------------------------------------------------
# parse() / parse_file() — direct API
# ---------------------------------------------------------------------------


def test_parse_valid_returns_blocks_with_required_attrs():
    blocks = parse_file(_fixture("state-valid.md"))
    assert len(blocks) >= 1
    for b in blocks:
        assert isinstance(b, Block)
        assert b.id, "id must be populated"
        assert b.ticket, "ticket must be populated"
        assert b.author, "author must be populated"
        assert b.session, "session must be populated"


def test_parse_valid_dict_round_trips_to_json():
    blocks = parse_file(_fixture("state-valid.md"))
    payload = [b.to_dict() for b in blocks]
    s = json.dumps(payload)
    parsed = json.loads(s)
    assert parsed[0]["id"] == blocks[0].id
    assert parsed[0]["ticket"] == blocks[0].ticket
    assert parsed[0]["author"] == blocks[0].author
    assert parsed[0]["session"] == blocks[0].session


def test_unclosed_block_raises_unclosed_entry():
    with pytest.raises(UnclosedEntryError) as excinfo:
        parse_file(_fixture("state-unclosed-block.md"))
    assert "unclosed entry" in str(excinfo.value)
    assert "line " in str(excinfo.value)


def test_duplicate_id_raises_with_offending_id():
    with pytest.raises(DuplicateIdError) as excinfo:
        parse_file(_fixture("state-duplicate-id.md"))
    msg = str(excinfo.value)
    assert "duplicate id" in msg
    # Offending id must appear verbatim in the error message.
    assert "2026-04-26T16:00:00Z-ARG-044" in msg


def test_missing_attr_names_attribute_and_line():
    with pytest.raises(MissingAttributeError) as excinfo:
        parse_file(_fixture("state-missing-attr.md"))
    msg = str(excinfo.value)
    assert "session" in msg, "missing attribute name must appear in message"
    assert "line " in msg, "message must carry a `line N:` prefix"


def test_malformed_open_tag_raises():
    text = "<!-- argos:entry totally bogus -->\nbody\n<!-- /argos:entry -->\n"
    with pytest.raises(MalformedOpenTagError):
        parse(text)


def test_blocks_unordered_within_section_all_returned():
    """Acceptance criterion 7 — three blocks intermixed with prose return as a 3-element list."""
    text = (
        "## Done this cycle\n"
        "\n"
        "Some intro prose.\n"
        "\n"
        "<!-- argos:entry id=2026-04-26T10:00:00Z-ARG-100 ticket=ARG-100 author=verifier session=s1 -->\n"
        "- block one body\n"
        "<!-- /argos:entry -->\n"
        "\n"
        "Some prose between blocks.\n"
        "\n"
        "<!-- argos:entry id=2026-04-26T10:00:01Z-ARG-101 ticket=ARG-101 author=coder session=s2 -->\n"
        "- block two body\n"
        "<!-- /argos:entry -->\n"
        "\n"
        "More prose.\n"
        "\n"
        "<!-- argos:entry id=2026-04-26T10:00:02Z-ARG-102 ticket=ARG-102 author=planner session=s3 -->\n"
        "- block three body\n"
        "<!-- /argos:entry -->\n"
    )
    blocks = parse(text)
    assert len(blocks) == 3
    ids = [b.id for b in blocks]
    assert ids == [
        "2026-04-26T10:00:00Z-ARG-100",
        "2026-04-26T10:00:01Z-ARG-101",
        "2026-04-26T10:00:02Z-ARG-102",
    ]
    tickets = [b.ticket for b in blocks]
    assert tickets == ["ARG-100", "ARG-101", "ARG-102"]
    authors = [b.author for b in blocks]
    assert authors == ["verifier", "coder", "planner"]


def test_empty_text_returns_empty_list():
    assert parse("") == []


def test_stray_close_tag_outside_block_is_ignored():
    text = "<!-- /argos:entry -->\nsome prose\n"
    assert parse(text) == []


# ---------------------------------------------------------------------------
# CLI shim — subprocess invocations of `python3 -m argos.cli state-parse <path>`
# ---------------------------------------------------------------------------


def _run_cli(fixture_name: str) -> subprocess.CompletedProcess:
    fixture = _fixture(fixture_name)
    return subprocess.run(
        [sys.executable, "-m", "argos.cli", "state-parse", str(fixture)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        check=False,
    )


def test_cli_valid_exits_zero_and_emits_json():
    proc = _run_cli("state-valid.md")
    assert proc.returncode == 0, f"stderr was: {proc.stderr!r}"
    payload = json.loads(proc.stdout)
    assert isinstance(payload, list)
    assert len(payload) >= 1
    for entry in payload:
        for key in ("id", "ticket", "author", "session"):
            assert key in entry, f"missing key {key!r} in CLI JSON output"
            assert entry[key], f"empty value for key {key!r}"


def test_cli_unclosed_exits_nonzero_with_substring():
    proc = _run_cli("state-unclosed-block.md")
    assert proc.returncode != 0
    assert "unclosed entry" in proc.stderr


def test_cli_duplicate_exits_nonzero_with_id():
    proc = _run_cli("state-duplicate-id.md")
    assert proc.returncode != 0
    assert "duplicate id" in proc.stderr
    assert "2026-04-26T16:00:00Z-ARG-044" in proc.stderr


def test_cli_missing_attr_exits_nonzero_naming_attr():
    proc = _run_cli("state-missing-attr.md")
    assert proc.returncode != 0
    assert "session" in proc.stderr
    assert "line " in proc.stderr
