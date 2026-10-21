"""Group similar SQL text for this pack's report.

The fingerprint is a local grouping key. It is not the MySQL
performance_schema digest, and it is not mysqldumpslow output.
Number literals and single-quoted strings become '?'. A parenthesized
list that is only '?' items collapses to '(?)'. Whitespace collapses,
and the result is lowercased.

check-upstream-docs: MySQL's own digest rules are described with the
server you run. This function does not follow those rules.
https://dev.mysql.com/doc/refman/8.0/en/performance-schema-statement-digests.html
"""

from __future__ import annotations

import re


_IN_LIST = re.compile(r"\(\s*\?(?:\s*,\s*\?)*\s*\)")
_NUMBER = re.compile(r"\b\d+(?:\.\d+)?\b")


def _strip_comments_and_quotes(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if ch == "'":
            out.append("?")
            i += 1
            while i < n:
                if sql[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if sql[i] == "'" and i + 1 < n and sql[i + 1] == "'":
                    i += 2
                    continue
                if sql[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            if end < 0:
                break
            out.append(" ")
            i = end + 2
            continue
        if sql.startswith("--", i) or (ch == "#" and (i == 0 or sql[i - 1] in "\n")):
            end = sql.find("\n", i)
            if end < 0:
                break
            out.append(" ")
            i = end
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def fingerprint(sql: str) -> str:
    """Return this pack's grouping key for one statement."""
    text = _strip_comments_and_quotes(sql)
    text = _NUMBER.sub("?", text)
    text = _IN_LIST.sub("(?)", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.rstrip(";").strip()
    return text.lower()
