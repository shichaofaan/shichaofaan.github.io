from __future__ import annotations

import re

# Capture db.table or schema.table from common SQL clauses
_TABLE_RE = re.compile(
    r"(?i)\b(?:from|join|into|update|table)\s+([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*){1,2})"
)
_SELECT_FIELD_RE = re.compile(
    r"(?i)\bselect\b(.*?)\bfrom\b",
    re.DOTALL,
)
_IDENT_RE = re.compile(r"([a-zA-Z_][\w$]*(?:\.[a-zA-Z_][\w$]*){1,2})")


def extract_qualified_names(sql: str) -> list[str]:
    """Extract likely db.table / db.table.column style names from SQL text."""
    if not sql:
        return []
    names: list[str] = []
    seen: set[str] = set()

    for match in _TABLE_RE.finditer(sql):
        qn = match.group(1).lower()
        if qn not in seen:
            seen.add(qn)
            names.append(qn)

    select_blocks = _SELECT_FIELD_RE.findall(sql)
    for block in select_blocks:
        for token in block.split(","):
            token = token.strip()
            if not token or token == "*":
                continue
            # strip aliases: expr AS alias
            token = re.split(r"(?i)\s+as\s+", token)[0].strip()
            # take trailing identifier if function call
            idents = _IDENT_RE.findall(token)
            if not idents:
                continue
            qn = idents[-1].lower()
            if "." in qn and qn not in seen:
                seen.add(qn)
                names.append(qn)

    return names
