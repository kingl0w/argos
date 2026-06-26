"""Read argos spec markdown/frontmatter (READ-ONLY) into plain entity dicts.

Three source formats, three readers (plus STATE entry blocks and a best-effort
prose drain-chain scraper):

  * tickets       -> markdown headers (**Epic:** N, ## Depends on, ## Touches, ...)
  * ADRs          -> markdown (**Status:**, **Deciders:**)
  * escalations   -> YAML frontmatter (---ticket_id/severity/raised_by/created---)
  * STATE entries -> <!-- argos:entry id=.. ticket=.. author=.. session=.. --> blocks

Every reader returns a dict (or list of dicts) of primitive values plus a
``source_file`` (repo-relative) and, where determinable, line numbers for
provenance. build.py turns these into RDF; this module never imports rdflib and
never writes anything.
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Prefix-agnostic ticket id (ARG1-030, SYN-057, …); excludes ADR-NNN.
_TICKET_PAT = r"(?!ADR-)[A-Z]{2,}\d*-\d+"
_ID_RE = re.compile(rf"\b({_TICKET_PAT})\b")
_ADR_RE = re.compile(r"\b(ADR-\d+)\b")


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _field(text: str, label: str):
    """Return (value, line_no) for a ``**Label:** value`` markdown header field."""
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(rf"\*\*{re.escape(label)}:\*\*\s*(.+?)\s*$", line)
        if m:
            return m.group(1).strip(), i
    return None, None


def _section(text: str, heading: str):
    """Return (body_lines, start_line) for a ``## heading`` block, or ([], None)."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(rf"##\s+{re.escape(heading)}\s*$", line):
            start = i
            break
    if start is None:
        return [], None
    body = []
    for line in lines[start + 1:]:
        if line.startswith("## "):
            break
        body.append(line)
    return body, start + 1  # +1 -> 1-based line of the heading


def _ids_in(lines) -> list[str]:
    """Ticket ids mentioned in a list of lines; 'none' / 'root of' -> []."""
    blob = "\n".join(lines)
    if re.search(r"\bnone\b", blob, re.I) and not _ID_RE.search(blob):
        return []
    seen, out = set(), []
    for m in _ID_RE.finditer(blob):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


# ---------------------------------------------------------------------------
# tickets
# ---------------------------------------------------------------------------

def parse_ticket(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    src = _rel(path, root)

    # ticketId: prefer the H1, fall back to the filename stem.
    m = re.search(rf"^#\s+({_TICKET_PAT})\b", text, re.M)
    ticket_id = m.group(1) if m else path.stem.split("-")[0] + "-" + path.stem.split("-")[1]

    priority, _ = _field(text, "Priority")
    status, _ = _field(text, "Status")
    created, _ = _field(text, "Created")

    epic_raw, epic_line = _field(text, "Epic")
    epic_num = epic_label = None
    if epic_raw:
        em = re.match(r"(\d+)\s*(?:\(([^)]*)\))?", epic_raw)
        if em:
            epic_num = int(em.group(1))
            epic_label = (em.group(2) or "").strip() or None

    dep_lines, dep_line = _section(text, "Depends on")
    par_lines, par_line = _section(text, "Parallelizable with")
    touch_lines, touch_line = _section(text, "Touches")

    depends_on = [d for d in _ids_in(dep_lines) if d != ticket_id]
    parallel = [p for p in _ids_in(par_lines) if p != ticket_id]
    touches = _touched_files(touch_lines)

    # ADR refs anywhere -> governedBy.
    adr_refs = sorted({m.group(1) for m in _ADR_RE.finditer(text)})

    # ## Amendment (ARGNNN) -> amends the named ticket.
    amends = None
    am = re.search(rf"##\s+Amendment\s*\(({_TICKET_PAT})\)", text)
    if am:
        amends = am.group(1)

    # intent: first non-empty paragraph of ## Intent.
    intent_lines, _ = _section(text, "Intent")
    intent = _first_paragraph(intent_lines)

    return {
        "ticket_id": ticket_id,
        "priority": priority,
        "status": status,
        "created": created,
        "epic": epic_num,
        "epic_label": epic_label,
        "epic_line": epic_line,
        "depends_on": depends_on,
        "depends_line": dep_line,
        "parallelizable_with": parallel,
        "parallel_line": par_line,
        "touches": touches,
        "touches_line": touch_line,
        "adr_refs": adr_refs,
        "amends": amends,
        "intent": intent,
        "source_file": src,
    }


def _touched_files(lines) -> list[str]:
    """Extract backtick-quoted path tokens from a ## Touches bullet list."""
    out = []
    for line in lines:
        for tok in re.findall(r"`([^`]+)`", line):
            tok = tok.strip()
            if "/" in tok or re.search(r"\.\w+$", tok):
                out.append(tok)
    # de-dup, preserve order
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


def _first_paragraph(lines) -> str | None:
    para = []
    for line in lines:
        if line.strip() == "":
            if para:
                break
            continue
        para.append(line.strip())
    return " ".join(para) if para else None


# ---------------------------------------------------------------------------
# ADRs
# ---------------------------------------------------------------------------

def parse_adr(path: Path, root: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    src = _rel(path, root)

    m = re.search(r"^#\s+(ADR-\d+)\b", text, re.M)
    adr_id = m.group(1) if m else "-".join(path.stem.split("-")[:2])

    status, _ = _field(text, "Status")
    created, _ = _field(text, "Date")

    # Deciders: REDACT any email before it ever reaches the graph.
    deciders_raw, _ = _field(text, "Deciders")
    deciders = _EMAIL_RE.sub("[decider]", deciders_raw) if deciders_raw else None

    # decision: the ratified line in ## Decision (best effort: first bold line).
    dec_lines, _ = _section(text, "Decision")
    decision = None
    for line in dec_lines:
        bm = re.match(r"\*\*(.+?)\*\*", line.strip())
        if bm:
            decision = bm.group(1).strip()
            break

    # drainsInto: the escalation/ticket ids named in ## Context.
    ctx_lines, _ = _section(text, "Context")
    drains_into = _ids_in(ctx_lines)

    return {
        "adr_id": adr_id,
        "status": status,
        "created": created,
        "deciders": deciders,
        "decision": decision,
        "drains_into": drains_into,
        "source_file": src,
    }


# ---------------------------------------------------------------------------
# escalations (YAML frontmatter)
# ---------------------------------------------------------------------------

def parse_escalation(path: Path, root: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    src = _rel(path, root)
    fm = _frontmatter(text)
    if not fm or "ticket_id" not in fm:
        return None  # README.md and other non-escalation files
    return {
        "esc_id": path.stem,            # filename stem, e.g. ARG1-057-2026-04-29T19-30-00Z
        "ticket_id": fm.get("ticket_id"),
        "session_id": fm.get("session_id"),
        "severity": fm.get("severity"),
        "raised_by": fm.get("raised_by"),
        "created": fm.get("created"),
        "source_file": src,
    }


def _frontmatter(text: str) -> dict:
    """Parse a leading ``---`` YAML frontmatter block: flat ``key: value`` scalars.

    Deliberately a tiny subset (no nesting, no flow style) — the same dialect the
    argos core's own stdlib parsers accept (ADR-002).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        m = re.match(r"([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return out


# ---------------------------------------------------------------------------
# STATE.md entry blocks
# ---------------------------------------------------------------------------

_ENTRY_RE = re.compile(
    r"<!--\s*argos:entry\s+(?P<attrs>[^>]*?)-->\s*(?P<body>.*?)<!--\s*/argos:entry\s*-->",
    re.S,
)
_ATTR_RE = re.compile(r"(\w+)=(\S+)")


def parse_state(path: Path, root: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    src = _rel(path, root)
    out = []
    for m in _ENTRY_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        body = m.group("body")
        line_no = text[: m.start()].count("\n") + 1

        decm = re.search(r"\bdecision:\s*(pass-with-minors|pass|fail)\b", body, re.I)
        if not decm:  # also "- Decision: pass" with a capital D handled by re.I above
            decm = re.search(r"\bDecision:\s*(pass-with-minors|pass|fail)\b", body)
        decision = decm.group(1).lower() if decm else None

        findm = re.search(r"(\d+)\s+critical,\s*(\d+)\s+major,\s*(\d+)\s+minor", body)
        counts = None
        if findm:
            counts = tuple(int(x) for x in findm.groups())

        bm = re.search(r"branch[es]*\s+`?([\w./-]+)`?", body)
        branch = bm.group(1) if bm else None

        out.append({
            "id": attrs.get("id"),
            "ticket": attrs.get("ticket"),
            "author": attrs.get("author"),
            "session": attrs.get("session"),
            "decision": decision,
            "counts": counts,
            "branch": branch,
            "files": _changed_files(body),
            "source_file": src,
            "source_line": line_no,
        })
    return out


def _changed_files(body: str) -> list[str]:
    """Backtick-quoted path tokens from Files-changed/added/edited lines."""
    out = []
    for line in body.splitlines():
        if re.search(r"^\s*-?\s*(Files changed|Files added|Files edited|Files|New|Edited)\b", line):
            for tok in re.findall(r"`([^`]+)`", line):
                tok = tok.strip()
                if "/" in tok:
                    out.append(tok)
    seen, uniq = set(), []
    for t in out:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    return uniq


# ---------------------------------------------------------------------------
# drain chains (best-effort, prose-derived)
# ---------------------------------------------------------------------------

# Matches "<originating id> ... drained via A -> B -> C ..." capturing the
# originating id and the arrow-joined token run that follows "drained via".
_CHAIN_ID = r"[A-Z]{2,}\d*-\d+"
_DRAIN_RE = re.compile(
    rf"({_CHAIN_ID})[^.\n]*?drained via\s+(?P<chain>(?:{_CHAIN_ID})"
    rf"(?:[^.\n]*?(?:→|->)[^.\n]*?(?:{_CHAIN_ID}))+)",
    re.I,
)
_CHAIN_TOKEN_RE = re.compile(_CHAIN_ID)


def parse_drain_chains(text: str, source_file: str) -> list[dict]:
    """Find 'X ... drained via A -> B -> C' prose and return ordered id chains.

    Lower-confidence than structured edges; build.py tags every hop
    ``argos:confidence "prose-derived"``.
    """
    chains = []
    for m in _DRAIN_RE.finditer(text):
        origin = m.group(1).upper()
        tokens = [t.upper() for t in _CHAIN_TOKEN_RE.findall(m.group("chain"))]
        ids = [origin] + tokens
        # collapse consecutive dupes
        seq = [ids[0]]
        for t in ids[1:]:
            if t != seq[-1]:
                seq.append(t)
        if len(seq) >= 3:
            line_no = text[: m.start()].count("\n") + 1
            chains.append({"chain": seq, "source_file": source_file, "source_line": line_no})
    return chains


# ---------------------------------------------------------------------------
# aggregate scan of a specs tree
# ---------------------------------------------------------------------------

def scan_specs(specs_root: Path, repo_root: Path | None = None) -> dict:
    """Walk a specs/ tree READ-ONLY and return all parsed entities."""
    specs_root = Path(specs_root)
    repo_root = Path(repo_root) if repo_root else specs_root.parent

    tickets, adrs, escalations, sessions, drains = [], [], [], [], []

    for p in sorted(specs_root.rglob("*.md")):
        rel = _rel(p, repo_root)
        name = p.name
        if "/tickets/" in "/" + rel.replace("\\", "/") + "/" and re.match(r"[A-Z]{2,}\d*-\d+", name):
            tickets.append(parse_ticket(p, repo_root))
            drains += parse_drain_chains(p.read_text(encoding="utf-8"), rel)
        elif "/decisions/" in "/" + rel.replace("\\", "/") + "/" and name.startswith("ADR-"):
            adrs.append(parse_adr(p, repo_root))
            drains += parse_drain_chains(p.read_text(encoding="utf-8"), rel)
        elif "/escalations/" in "/" + rel.replace("\\", "/") + "/":
            esc = parse_escalation(p, repo_root)
            if esc:
                escalations.append(esc)
        elif name == "STATE.md":
            entries = parse_state(p, repo_root)
            sessions += entries
            drains += parse_drain_chains(p.read_text(encoding="utf-8"), rel)

    return {
        "tickets": tickets,
        "adrs": adrs,
        "escalations": escalations,
        "sessions": sessions,
        "drain_chains": drains,
    }
