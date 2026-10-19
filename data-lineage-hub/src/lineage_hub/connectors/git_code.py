from __future__ import annotations

import hashlib
from pathlib import Path

from lineage_hub.config import Settings
from lineage_hub.extractors import extract_dim_ids
from lineage_hub.models import CodeSpan

SQL_GLOBS = ("**/*.sql", "**/*.hql", "**/*.ddl")


class GitCodeConnector:
    """Scan local git working trees for SQL/scripts and build code spans."""

    def __init__(self, settings: Settings, repo_paths: list[Path] | None = None) -> None:
        self.settings = settings
        self.repo_paths = repo_paths or settings.git_paths

    def fetch_code_spans(self) -> list[CodeSpan]:
        spans: list[CodeSpan] = []
        for repo_path in self.repo_paths:
            root = Path(repo_path).resolve()
            if not root.exists():
                continue
            repo_name = root.name
            files: list[Path] = []
            for pattern in SQL_GLOBS:
                files.extend(root.glob(pattern))
            for file_path in sorted(set(files)):
                if not file_path.is_file():
                    continue
                text = file_path.read_text(encoding="utf-8", errors="ignore")
                relative = str(file_path.relative_to(root))
                spans.extend(self._spans_for_file(repo_name, relative, text))
        return spans

    def _spans_for_file(self, repo: str, path: str, text: str) -> list[CodeSpan]:
        lines = text.splitlines()
        if not lines:
            return []

        dim_ids = extract_dim_ids(text)
        # Prefer a span around dim tags; otherwise whole file (capped)
        if dim_ids:
            start = 1
            for idx, line in enumerate(lines, start=1):
                if extract_dim_ids(line):
                    start = max(1, idx - 2)
                    break
            end = min(len(lines), start + 40)
        else:
            start = 1
            end = min(len(lines), 60)

        excerpt = "\n".join(lines[start - 1 : end])
        digest = hashlib.sha1(excerpt.encode("utf-8")).hexdigest()[:12]
        span_id = f"code:{repo}:{path}:{start}-{end}"
        blob_url = self._blob_url(repo, path, start)
        return [
            CodeSpan(
                id=span_id,
                repo=repo,
                path=path,
                start_line=start,
                end_line=end,
                language="sql",
                excerpt=excerpt,
                excerpt_hash=digest,
                blob_url=blob_url,
            )
        ]

    def _blob_url(self, repo: str, path: str, start: int) -> str:
        base = self.settings.git_blob_base_url.rstrip("/")
        if not base:
            return f"file://{repo}/{path}#L{start}"
        return f"{base}/{repo}/blob/main/{path}#L{start}"
