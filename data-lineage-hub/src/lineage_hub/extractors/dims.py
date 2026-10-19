from __future__ import annotations

import re

DIM_PATTERN = re.compile(r"\bdim:([a-z][a-z0-9_]*)\b", re.IGNORECASE)


def extract_dim_ids(*texts: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in DIM_PATTERN.finditer(text):
            dim_id = match.group(1).lower()
            if dim_id not in seen:
                seen.add(dim_id)
                found.append(dim_id)
    return found
