from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from lineage_hub.config import Settings
from lineage_hub.models import YuqueDoc


class YuqueConnector:
    """Fetch documents from Yuque Open API, or from local fixtures."""

    def __init__(self, settings: Settings, fixture_dir: Path | None = None) -> None:
        self.settings = settings
        self.fixture_dir = fixture_dir

    def fetch_docs(self) -> list[YuqueDoc]:
        if self.fixture_dir:
            return self._from_fixture(self.fixture_dir)
        return self._from_api()

    def _from_fixture(self, fixture_dir: Path) -> list[YuqueDoc]:
        path = fixture_dir / "docs.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [self._to_doc(item) for item in payload]

    def _from_api(self) -> list[YuqueDoc]:
        if not self.settings.yuque_token:
            raise RuntimeError("YUQUE_TOKEN is required unless using --fixture")
        if not self.settings.yuque_book_namespace:
            raise RuntimeError("YUQUE_BOOK_NAMESPACE is required unless using --fixture")

        headers = {"X-Auth-Token": self.settings.yuque_token, "User-Agent": "lineage-hub"}
        base = self.settings.yuque_api_url.rstrip("/")
        book = self.settings.yuque_book_namespace
        docs: list[YuqueDoc] = []

        with httpx.Client(base_url=base, headers=headers, timeout=60.0) as client:
            listing = client.get(f"/repos/{book}/docs")
            listing.raise_for_status()
            items = listing.json().get("data") or []
            for item in items:
                slug = item.get("slug") or str(item.get("id"))
                detail = client.get(f"/repos/{book}/docs/{slug}", params={"raw": 1})
                detail.raise_for_status()
                body_data = detail.json().get("data") or {}
                docs.append(
                    self._to_doc(
                        {
                            "id": f"yuque:{book}:{slug}",
                            "book": book,
                            "slug": slug,
                            "title": body_data.get("title") or item.get("title") or slug,
                            "url": f"https://www.yuque.com/{book}/{slug}",
                            "updated_at": body_data.get("updated_at") or item.get("updated_at") or "",
                            "body": body_data.get("body") or body_data.get("body_html") or "",
                            "excerpt": (body_data.get("description") or "")[:500],
                        }
                    )
                )
        return docs

    def _to_doc(self, item: dict[str, Any]) -> YuqueDoc:
        book = str(item.get("book", "unknown"))
        slug = str(item.get("slug", "unknown"))
        doc_id = str(item.get("id") or f"yuque:{book}:{slug}")
        body = str(item.get("body", ""))
        excerpt = str(item.get("excerpt") or body[:500])
        return YuqueDoc(
            id=doc_id,
            book=book,
            slug=slug,
            title=str(item.get("title", slug)),
            url=str(item.get("url") or f"https://www.yuque.com/{book}/{slug}"),
            updated_at=str(item.get("updated_at", "")),
            excerpt=excerpt,
            body=body,
        )
