"""Firecrawl search and scrape integration without pipeline decisions."""

from time import sleep
from typing import Any, Callable, Dict, List, TypeVar
from urllib.parse import urlparse

from src.core.settings import settings
from src.core.retry import is_retryable_provider_error


Result = TypeVar("Result")


def _as_dict(value: Any) -> Dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(by_alias=True)
    if isinstance(value, dict):
        return value
    return vars(value)


class FirecrawlTool:
    def _client(self) -> Any:
        if not settings.firecrawl_api_key:
            raise RuntimeError("FIRECRAWL_API_KEY is required when DATA_SOURCE_PROVIDER is firecrawl")
        from firecrawl import Firecrawl
        return Firecrawl(api_key=settings.firecrawl_api_key, api_url=settings.firecrawl_api_url)

    def _request(self, operation: Callable[[], Result]) -> Result:
        last_error: Exception | None = None
        for attempt in range(settings.firecrawl_max_retries + 1):
            try:
                return operation()
            except Exception as error:
                last_error = error
                if attempt < settings.firecrawl_max_retries and is_retryable_provider_error(error):
                    sleep(2 ** attempt)
                    continue
                break
        raise RuntimeError(f"Firecrawl request failed: {last_error}") from last_error

    def search(self, query: str, limit: int | None = None) -> List[Dict[str, str]]:
        result = self._request(lambda: self._client().search(query, limit=limit or settings.firecrawl_search_limit))
        payload = _as_dict(result)
        web_results = payload.get("web", payload.get("data", []))
        return [
            {
                "url": item.get("url", ""),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
            }
            for item in web_results
            if item.get("url")
        ]

    def scrape(self, url: str) -> Dict[str, Any]:
        payload = _as_dict(self._request(lambda: self._client().scrape(url, formats=["markdown"])))
        metadata = payload.get("metadata", {})
        source_url = metadata.get("sourceURL") or metadata.get("url") or url
        return {
            "source": source_url,
            "title": metadata.get("title", ""),
            "content": payload.get("markdown", ""),
            "type": "web",
            "metadata": {
                **metadata,
                "source_domain": urlparse(source_url).netloc,
                "source_provider": "firecrawl",
            },
        }
