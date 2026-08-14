"""Firecrawl adapter for global source discovery."""

from __future__ import annotations

from urllib.parse import urlparse

from src.tools.firecrawl_tool import FirecrawlTool
from src.tools.web.models import DiscoveredSource


class FirecrawlDiscoveryProvider:
    def __init__(self, tool: FirecrawlTool | None = None) -> None:
        self._tool = tool or FirecrawlTool()

    def search(self, query: str, *, limit: int) -> list[DiscoveredSource]:
        return [
            DiscoveredSource(
                url=item["url"],
                title=item.get("title", ""),
                description=item.get("description", ""),
                domain=urlparse(item["url"]).netloc,
                source_provider="firecrawl",
            )
            for item in self._tool.search(query, limit)
        ]
