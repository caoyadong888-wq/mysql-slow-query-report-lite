"""Parse MySQL slow-query log text from the FILE destination.

The metric names Query_time, Lock_time, Rows_sent, and Rows_examined are
the fields named in MySQL 8.0 Reference Manual section 7.4.5. The extra
names recognized below are the log_slow_extra names whose labels were
present in that section's rendered text. Any other Key: token on a '#'
header line is kept under unrecognized_fields and is not interpreted.

check-upstream-docs:
https://dev.mysql.com/doc/refman/8.0/en/slow-query-log.html

Header lines that start with '# Time:' or '# User@Host:' follow the FILE
layout used by the sample logs in this pack. This module does not claim
those two labels are a separate table in section 7.4.5. A line that
starts with '#' after the SQL text has begun is kept as part of the
statement, except when it starts another Time or User@Host header.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Float and int names are the ones printed as labels in manual 7.4.5.
FLOAT_FIELDS = ("Query_time", "Lock_time")
INT_FIELDS = (
    "Rows_sent",
    "Rows_examined",
    "Thread_id",
    "Errno",
    "Killed",
    "Bytes_received",
    "Bytes_sent",
    "Read_first",
    "Read_last",
    "Read_key",
    "Read_prev",
    "Read_rnd",
    "Sort_merge_passes",
    "Sort_range_count",
    "Sort_rows",
    "Sort_scan_count",
    "Created_tmp_disk_tables",
    "Created_tmp_tables",
)
TEXT_FIELDS = ("Start", "End")
KNOWN_FIELDS = set(FLOAT_FIELDS) | set(INT_FIELDS) | set(TEXT_FIELDS)

# Statement names listed as administrative in the same manual section.
ADMIN_PREFIXES = (
    "alter table",
    "analyze table",
    "check table",
    "create index",
    "drop index",
    "optimize table",
    "repair table",
)

USER_HOST_RE = re.compile(
    r"^# User@Host:\s*"
    r"(?P<user>[^\s\[]+)"
    r"(?:\[(?P<priv>[^\]]*)\])?"
    r"\s*@\s*"
    r"(?P<host>\S+)"
    r"(?:\s*\[(?P<ip>[^\]]*)\])?"
    r"(?:\s+Id:\s*(?P<header_id>\d+))?"
    r"\s*$"
)
FIELD_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)\s*:\s*(\S+)")
USE_RE = re.compile(r"^use\s+`?([A-Za-z0-9_]+)`?\s*;?\s*$", re.IGNORECASE)
SET_TS_RE = re.compile(
    r"^SET\s+timestamp\s*=\s*(\d+)\s*;?\s*$",
    re.IGNORECASE,
)


@dataclass
class SlowEntry:
    time_text: str | None = None
    user: str | None = None
    priv_user: str | None = None
    host: str | None = None
    ip: str | None = None
    header_id: str | None = None
    schema_name: str | None = None
    set_timestamp: str | None = None
    sql: str = ""
    metrics: dict[str, int | float | str] = field(default_factory=dict)
    unrecognized_fields: dict[str, str] = field(default_factory=dict)
    admin: bool = False

    def user_at_host(self) -> str | None:
        if not self.user and not self.host:
            return None
        user = self.user or "?"
        host = self.host or "?"
        return f"{user} at {host}"


@dataclass
class ParseResult:
    preamble: list[str]
    entries: list[SlowEntry]


def is_admin_statement(sql: str) -> bool:
    """True when the statement starts with a name the manual lists as admin."""
    compact = " ".join(sql.strip().split()).lower()
    return any(compact.startswith(prefix) for prefix in ADMIN_PREFIXES)


def _parse_meta_fields(line: str) -> tuple[dict[str, int | float | str], dict[str, str]]:
    body = line[1:].strip() if line.startswith("#") else line.strip()
    metrics: dict[str, int | float | str] = {}
    unknown: dict[str, str] = {}
    for key, raw in FIELD_RE.findall(body):
        if key not in KNOWN_FIELDS:
            unknown[key] = raw
            continue
        if key in FLOAT_FIELDS:
            metrics[key] = float(raw)
        elif key in INT_FIELDS:
            metrics[key] = int(raw)
        else:
            metrics[key] = raw
    return metrics, unknown


class _Builder:
    def __init__(self) -> None:
        self.entry = SlowEntry()
        self.sql_lines: list[str] = []
        self.in_sql = False

    def absorb_header(self, line: str) -> None:
        if line.startswith("# Time:"):
            self.entry.time_text = line.split(":", 1)[1].strip()
            return
        match = USER_HOST_RE.match(line)
        if match:
            self.entry.user = match.group("user")
            self.entry.priv_user = match.group("priv")
            self.entry.host = match.group("host")
            ip = match.group("ip")
            self.entry.ip = ip or None
            self.entry.header_id = match.group("header_id")
            return
        metrics, unknown = _parse_meta_fields(line)
        self.entry.metrics.update(metrics)
        self.entry.unrecognized_fields.update(unknown)

    def finish(self) -> SlowEntry | None:
        while self.sql_lines and not self.sql_lines[-1].strip():
            self.sql_lines.pop()
        sql = "\n".join(self.sql_lines).strip()
        self.entry.sql = sql
        self.entry.admin = is_admin_statement(sql) if sql else False
        has_body = bool(
            sql
            or self.entry.metrics
            or self.entry.time_text
            or self.entry.user
        )
        if not has_body:
            return None
        return self.entry


def parse_slow_log(text: str) -> ParseResult:
    """Parse one slow-log document. Accepts LF or CRLF."""
    preamble: list[str] = []
    entries: list[SlowEntry] = []
    current: _Builder | None = None

    def close() -> None:
        nonlocal current
        if current is None:
            return
        finished = current.finish()
        if finished is not None:
            entries.append(finished)
        current = None

    for raw in text.splitlines():
        line = raw.rstrip("\r")
        is_boundary = line.startswith("# Time:") or line.startswith("# User@Host:")
        if is_boundary:
            if current is not None and (
                current.in_sql
                or current.entry.time_text is not None
                or current.entry.user is not None
            ):
                # A second Time/User@Host header starts the next statement.
                if current.entry.time_text or current.entry.user or current.in_sql:
                    # Close only when this header repeats a slot we already
                    # filled, or when SQL has already started.
                    repeat = (
                        (line.startswith("# Time:") and current.entry.time_text is not None)
                        or (line.startswith("# User@Host:") and current.entry.user is not None)
                        or current.in_sql
                    )
                    if repeat:
                        close()
            if current is None:
                current = _Builder()
            current.absorb_header(line)
            continue
        if current is None:
            if line.strip():
                preamble.append(line)
            continue
        if not current.in_sql and line.startswith("#"):
            current.absorb_header(line)
            continue
        stripped = line.strip()
        if not current.in_sql and not stripped:
            continue
        if not current.in_sql:
            use_match = USE_RE.match(stripped)
            if use_match:
                current.entry.schema_name = use_match.group(1)
                continue
            ts_match = SET_TS_RE.match(stripped)
            if ts_match:
                current.entry.set_timestamp = ts_match.group(1)
                continue
        current.in_sql = True
        current.sql_lines.append(line)
    close()
    return ParseResult(preamble=preamble, entries=entries)


def parse_path(path: str) -> ParseResult:
    with open(path, encoding="utf-8") as handle:
        return parse_slow_log(handle.read())
