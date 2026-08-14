"""Crawl4AI page acquisition normalized into provider-neutral contracts."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from datetime import datetime, timezone
from hashlib import sha256
import inspect
import os
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlparse

from src.core.settings import settings
from src.core.source_registry import normalize_candidate_url
from src.tools.web.models import AcquiredDocument, DiscoveredPage, SourcePreview
from src.tools.web.preview_builder import build_source_preview


ResultLoader = Callable[[str], Any | Awaitable[Any]]
ExplorationLoader = Callable[..., Any | Awaitable[Any]]


class Crawl4AIAcquisitionProvider:
    """Synchronous pipeline adapter around Crawl4AI's asynchronous API."""

    SUPPORTED_CACHE_MODES = {
        "enabled",
        "disabled",
        "read_only",
        "write_only",
        "bypass",
    }

    def __init__(
        self,
        *,
        result_loader: ResultLoader | None = None,
        exploration_loader: ExplorationLoader | None = None,
        base_directory: str | Path | None = None,
        headless: bool | None = None,
        page_timeout_ms: int | None = None,
        cache_mode: str | None = None,
        pruning_threshold: float | None = None,
        preview_max_words: int | None = None,
        batch_concurrency: int | None = None,
        batch_delay_seconds: float | None = None,
    ) -> None:
        self._result_loader = result_loader
        self._exploration_loader = exploration_loader
        self.base_directory = Path(
            base_directory or settings.crawl4ai_base_directory
        ).expanduser().resolve()
        self.headless = settings.crawl4ai_headless if headless is None else headless
        self.page_timeout_ms = (
            settings.crawl4ai_page_timeout_ms
            if page_timeout_ms is None
            else page_timeout_ms
        )
        self.cache_mode = (cache_mode or settings.crawl4ai_cache_mode).strip().lower()
        self.pruning_threshold = (
            settings.crawl4ai_pruning_threshold
            if pruning_threshold is None
            else pruning_threshold
        )
        self.preview_max_words = (
            settings.crawl4ai_preview_max_words
            if preview_max_words is None
            else preview_max_words
        )
        self.batch_concurrency = (
            settings.crawl4ai_batch_concurrency
            if batch_concurrency is None
            else batch_concurrency
        )
        self.batch_delay_seconds = (
            settings.crawl4ai_batch_delay_seconds
            if batch_delay_seconds is None
            else batch_delay_seconds
        )
        self._preview_cache: dict[tuple[str, str], SourcePreview] = {}

        if self.cache_mode not in self.SUPPORTED_CACHE_MODES:
            supported = ", ".join(sorted(self.SUPPORTED_CACHE_MODES))
            raise ValueError(
                f"Unsupported Crawl4AI cache mode {self.cache_mode!r}; use one of: {supported}."
            )
        if self.page_timeout_ms <= 0:
            raise ValueError("Crawl4AI page timeout must be greater than zero.")
        if not 0.0 <= self.pruning_threshold <= 1.0:
            raise ValueError("Crawl4AI pruning threshold must be between 0 and 1.")
        if self.preview_max_words <= 0:
            raise ValueError("Crawl4AI preview max words must be greater than zero.")
        if self.batch_concurrency < 1:
            raise ValueError("Crawl4AI batch concurrency must be at least 1.")
        if self.batch_delay_seconds < 0:
            raise ValueError("Crawl4AI batch delay cannot be negative.")

    def preview(self, url: str, *, query: str | None = None) -> SourcePreview:
        cache_key = (url, (query or "").strip())
        cached = self._preview_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(deep=True)

        document = self._acquire_document(url, query=query)
        preview = build_source_preview(document, max_words=self.preview_max_words)
        self._preview_cache[cache_key] = preview
        return preview.model_copy(deep=True)

    def acquire(self, url: str) -> AcquiredDocument:
        """Acquire one page and return only the stable internal document model."""
        return self._acquire_document(url)

    def _acquire_document(self, url: str, *, query: str | None = None) -> AcquiredDocument:
        try:
            result = self._run_async(self._load_result(url, query=query))
            return self._normalize_result(url, result)
        except Exception as exc:  # Provider/browser failures are data, not leaked SDK errors.
            return self._failure_document(url, exc)

    def acquire_many(self, urls: list[str]) -> list[AcquiredDocument]:
        """Acquire an ordered batch with bounded concurrency and isolated failures."""
        if not urls:
            return []
        try:
            outcomes = self._run_async(self._load_many_results(urls))
        except Exception as exc:
            return [self._failure_document(url, exc) for url in urls]

        documents: list[AcquiredDocument] = []
        for url, outcome in zip(urls, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                documents.append(self._failure_document(url, outcome))
            else:
                documents.append(self._normalize_result(url, outcome))
        return documents

    async def _load_many_results(self, urls: list[str]) -> list[Any | BaseException]:
        if self._result_loader is not None:
            return await self._load_many_with_fixture_loader(urls)
        return await self._load_many_with_crawl4ai(urls)

    async def _load_many_with_fixture_loader(
        self, urls: list[str]
    ) -> list[Any | BaseException]:
        semaphore = asyncio.Semaphore(self.batch_concurrency)
        throttle_lock = asyncio.Lock()
        next_start = 0.0

        async def load(url: str) -> Any:
            nonlocal next_start
            async with semaphore:
                async with throttle_lock:
                    loop = asyncio.get_running_loop()
                    while True:
                        now = loop.time()
                        wait_seconds = next_start - now
                        if wait_seconds <= 0:
                            break
                        # Some Windows event-loop/timer combinations can wake a
                        # short sleep early. Recheck the monotonic deadline so
                        # the configured minimum start spacing remains true.
                        await asyncio.sleep(wait_seconds)
                    next_start = loop.time() + self.batch_delay_seconds
                result = self._result_loader(url)
                return await result if inspect.isawaitable(result) else result

        return list(await asyncio.gather(
            *(load(url) for url in urls),
            return_exceptions=True,
        ))

    async def _load_many_with_crawl4ai(
        self, urls: list[str]
    ) -> list[Any | BaseException]:
        self.base_directory.mkdir(parents=True, exist_ok=True)
        os.environ["CRAWL4_AI_BASE_DIRECTORY"] = str(self.base_directory)

        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher, RateLimiter

        browser_config = BrowserConfig(headless=self.headless, verbose=False)
        run_config = CrawlerRunConfig(
            cache_mode=getattr(CacheMode, self.cache_mode.upper()),
            page_timeout=self.page_timeout_ms,
            wait_until="domcontentloaded",
            stream=False,
            semaphore_count=self.batch_concurrency,
            mean_delay=self.batch_delay_seconds,
            max_range=0.0,
            verbose=False,
            log_console=False,
        )
        dispatcher = MemoryAdaptiveDispatcher(
            max_session_permit=self.batch_concurrency,
            rate_limiter=RateLimiter(
                base_delay=(self.batch_delay_seconds, self.batch_delay_seconds),
                max_delay=max(1.0, self.batch_delay_seconds),
                max_retries=0,
            ),
        )
        crawler_urls = [self._crawler_url(url) for url in urls]
        async with AsyncWebCrawler(
            config=browser_config,
            base_directory=str(self.base_directory),
        ) as crawler:
            raw_results = list(await crawler.arun_many(
                urls=crawler_urls,
                config=run_config,
                dispatcher=dispatcher,
            ))
        return self._restore_batch_order(urls, crawler_urls, raw_results)

    @classmethod
    def _restore_batch_order(
        cls,
        source_urls: list[str],
        crawler_urls: list[str],
        results: list[Any],
    ) -> list[Any | BaseException]:
        """Map provider completion order back to deterministic request order."""
        remaining = list(results)
        ordered: list[Any | BaseException | None] = [None] * len(source_urls)
        for target_index, (source_url, crawler_url) in enumerate(
            zip(source_urls, crawler_urls, strict=True)
        ):
            match_index = next((
                index
                for index, result in enumerate(remaining)
                if cls._text(getattr(result, "url", None)) in {source_url, crawler_url}
            ), None)
            if match_index is not None:
                ordered[target_index] = remaining.pop(match_index)
        for target_index, item in enumerate(ordered):
            if item is None and remaining:
                ordered[target_index] = remaining.pop(0)
            elif item is None:
                ordered[target_index] = RuntimeError(
                    "Crawl4AI batch omitted a result for requested URL: "
                    f"{source_urls[target_index]}"
                )
        return [item for item in ordered if item is not None]

    def explore_site(
        self,
        start_url: str,
        *,
        query_terms: list[str],
        max_depth: int,
        max_pages: int,
        same_domain_only: bool = True,
    ) -> list[DiscoveredPage]:
        if max_depth < 1:
            raise ValueError("Site exploration max_depth must be at least 1.")
        if max_pages < 1:
            raise ValueError("Site exploration max_pages must be at least 1.")
        start_url = normalize_candidate_url(start_url)
        results = self._run_async(self._load_exploration_results(
            start_url,
            query_terms=query_terms,
            max_depth=max_depth,
            max_pages=max_pages,
            same_domain_only=same_domain_only,
        ))
        return self._normalize_exploration_results(
            start_url,
            results,
            max_depth=max_depth,
            max_pages=max_pages,
            same_domain_only=same_domain_only,
        )

    async def _load_result(self, url: str, *, query: str | None = None) -> Any:
        if self._result_loader is not None:
            result = self._result_loader(url)
            return await result if inspect.isawaitable(result) else result

        # Crawl4AI creates its database during import. Set its supported base
        # directory first so the dependency never writes to an implicit home path.
        self.base_directory.mkdir(parents=True, exist_ok=True)
        os.environ["CRAWL4_AI_BASE_DIRECTORY"] = str(self.base_directory)

        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

        browser_config = BrowserConfig(
            headless=self.headless,
            verbose=False,
        )
        content_filter = PruningContentFilter(
            user_query=query,
            threshold=self.pruning_threshold,
            threshold_type="fixed",
            min_word_threshold=5,
        )
        run_config = CrawlerRunConfig(
            cache_mode=getattr(CacheMode, self.cache_mode.upper()),
            page_timeout=self.page_timeout_ms,
            markdown_generator=DefaultMarkdownGenerator(content_filter=content_filter),
            wait_until="domcontentloaded",
            verbose=False,
            log_console=False,
        )

        async with AsyncWebCrawler(
            config=browser_config,
            base_directory=str(self.base_directory),
        ) as crawler:
            return await crawler.arun(url=self._crawler_url(url), config=run_config)

    async def _load_exploration_results(
        self,
        start_url: str,
        *,
        query_terms: list[str],
        max_depth: int,
        max_pages: int,
        same_domain_only: bool,
    ) -> Any:
        if self._exploration_loader is not None:
            results = self._exploration_loader(
                start_url,
                query_terms=query_terms,
                max_depth=max_depth,
                max_pages=max_pages,
                same_domain_only=same_domain_only,
            )
            return await results if inspect.isawaitable(results) else results

        self.base_directory.mkdir(parents=True, exist_ok=True)
        os.environ["CRAWL4_AI_BASE_DIRECTORY"] = str(self.base_directory)

        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.deep_crawling import BestFirstCrawlingStrategy
        from crawl4ai.deep_crawling.filters import ContentTypeFilter, DomainFilter, FilterChain
        from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer

        allowed_domain = urlparse(start_url).netloc.lower()
        filters = [ContentTypeFilter(allowed_types=["text/html", "application/xhtml+xml"])]
        if same_domain_only:
            # Crawl4AI's DomainFilter compares the full URL authority, including
            # non-default ports, rather than urllib's hostname-only value.
            filters.insert(0, DomainFilter(allowed_domains=[allowed_domain]))
        normalized_terms = list(dict.fromkeys(
            term.strip().casefold() for term in query_terms if term.strip()
        ))
        scorer = (
            KeywordRelevanceScorer(keywords=normalized_terms, weight=1.0)
            if normalized_terms
            else None
        )
        strategy = BestFirstCrawlingStrategy(
            max_depth=max_depth,
            max_pages=max_pages,
            include_external=not same_domain_only,
            filter_chain=FilterChain(filters),
            url_scorer=scorer,
        )
        run_config = CrawlerRunConfig(
            cache_mode=getattr(CacheMode, self.cache_mode.upper()),
            page_timeout=self.page_timeout_ms,
            deep_crawl_strategy=strategy,
            stream=False,
            wait_until="domcontentloaded",
            preserve_https_for_internal_links=True,
            verbose=False,
            log_console=False,
        )
        browser_config = BrowserConfig(headless=self.headless, verbose=False)

        async with AsyncWebCrawler(
            config=browser_config,
            base_directory=str(self.base_directory),
        ) as crawler:
            return await crawler.arun(url=start_url, config=run_config)

    @staticmethod
    def _run_async(awaitable: Awaitable[Any]) -> Any:
        """Run async Crawl4AI from both ordinary and already-async callers."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(awaitable)

        outcome: list[Any] = []
        failure: list[BaseException] = []

        def runner() -> None:
            try:
                outcome.append(asyncio.run(awaitable))
            except BaseException as exc:  # Re-raised on the calling thread below.
                failure.append(exc)

        thread = Thread(target=runner, name="crawl4ai-acquire", daemon=True)
        thread.start()
        thread.join()
        if failure:
            raise failure[0]
        return outcome[0]

    @classmethod
    def _normalize_result(cls, source_url: str, result: Any) -> AcquiredDocument:
        success = bool(getattr(result, "success", False))
        markdown = getattr(result, "markdown", None)
        raw_markdown = cls._markdown_value(markdown, "raw_markdown")
        fit_markdown = cls._markdown_value(markdown, "fit_markdown") or None
        html = cls._text(getattr(result, "html", None)) or None
        metadata = cls._mapping(getattr(result, "metadata", None))
        links = cls._mapping(getattr(result, "links", None))

        redirected_url = cls._http_url(getattr(result, "redirected_url", None))
        result_url = cls._http_url(getattr(result, "url", None))
        metadata_canonical = cls._http_url(
            metadata.get("canonical_url")
            or metadata.get("canonical")
            or metadata.get("og:url")
        )
        canonical_url = metadata_canonical or redirected_url or result_url
        title = cls._text(metadata.get("title") or metadata.get("og:title"))
        error_message = cls._text(getattr(result, "error_message", None)) or None

        provider_metadata = cls._json_mapping(metadata)
        provider_metadata.update({
            "status_code": cls._json_value(getattr(result, "status_code", None)),
            "redirected_url": redirected_url,
            "cache_status": cls._json_value(getattr(result, "cache_status", None)),
        })
        provider_metadata = {
            key: value for key, value in provider_metadata.items() if value is not None
        }

        if not success and error_message is None:
            error_message = "Crawl4AI returned an unsuccessful result without an error message."

        return AcquiredDocument(
            source_url=source_url,
            canonical_url=canonical_url,
            title=title,
            domain=urlparse(canonical_url or source_url).netloc.lower(),
            raw_markdown=raw_markdown,
            fit_markdown=fit_markdown,
            html=html,
            internal_links=cls._link_urls(links.get("internal")),
            external_links=cls._link_urls(links.get("external")),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            source_provider="crawl4ai",
            content_hash=sha256(raw_markdown.encode("utf-8")).hexdigest(),
            success=success,
            error=error_message,
            provider_metadata=provider_metadata,
        )

    @classmethod
    def _failure_document(cls, source_url: str, exc: Exception) -> AcquiredDocument:
        return AcquiredDocument(
            source_url=source_url,
            canonical_url=cls._http_url(source_url),
            domain=urlparse(source_url).netloc.lower(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            source_provider="crawl4ai",
            content_hash=sha256(b"").hexdigest(),
            success=False,
            error=f"{type(exc).__name__}: {exc}",
            provider_metadata={"failure_type": type(exc).__name__},
        )

    @classmethod
    def _markdown_value(cls, markdown: Any, attribute: str) -> str:
        if markdown is None:
            return ""
        value = getattr(markdown, attribute, None)
        if value is None and attribute == "raw_markdown" and isinstance(markdown, str):
            value = markdown
        return cls._text(value)

    @classmethod
    def _link_urls(cls, entries: Any) -> list[str]:
        if not isinstance(entries, list):
            return []
        urls: list[str] = []
        for entry in entries:
            value = entry.get("href") if isinstance(entry, Mapping) else entry
            url = cls._text(value).strip()
            if url and url not in urls:
                urls.append(url)
        return urls

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _text(value: Any) -> str:
        return value if isinstance(value, str) else ""

    @staticmethod
    def _http_url(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        parsed = urlparse(value)
        return value if parsed.scheme in {"http", "https"} and parsed.netloc else None

    @staticmethod
    def _crawler_url(url: str) -> str:
        """Work around Crawl4AI 0.9.2's Windows file-URI path handling."""
        if os.name == "nt" and url.startswith("file:///"):
            return "file://" + url[8:]
        return url

    @classmethod
    def _normalize_exploration_results(
        cls,
        start_url: str,
        results: Any,
        *,
        max_depth: int,
        max_pages: int,
        same_domain_only: bool,
    ) -> list[DiscoveredPage]:
        start_canonical = normalize_candidate_url(start_url)
        start_host = urlparse(start_canonical).hostname or ""
        normalized: list[DiscoveredPage] = []
        seen = {start_canonical}

        if results is None:
            return []
        if isinstance(results, (str, bytes)):
            result_items = []
        else:
            try:
                result_items = list(results)
            except TypeError:
                result_items = [results]

        for result in result_items:
            if len(normalized) >= max_pages:
                break
            if not bool(getattr(result, "success", False)):
                continue
            raw_url = getattr(result, "url", None)
            if not isinstance(raw_url, str):
                continue
            try:
                canonical_url = normalize_candidate_url(raw_url)
            except ValueError:
                continue
            metadata = cls._mapping(getattr(result, "metadata", None))
            try:
                depth = int(metadata.get("depth", 0))
            except (TypeError, ValueError):
                continue
            if depth < 1 or depth > max_depth:
                continue
            if canonical_url in seen or not cls._is_explorable_page_url(canonical_url):
                continue
            if same_domain_only and (urlparse(canonical_url).hostname or "") != start_host:
                continue

            parent_url = metadata.get("parent_url")
            try:
                normalized_parent = (
                    normalize_candidate_url(parent_url)
                    if isinstance(parent_url, str)
                    else None
                )
            except ValueError:
                normalized_parent = None
            result_metadata = cls._mapping(getattr(result, "metadata", None))
            title = cls._text(result_metadata.get("title") or result_metadata.get("og:title"))
            normalized.append(DiscoveredPage(
                url=canonical_url,
                title=title,
                depth=depth,
                parent_url=normalized_parent,
            ))
            seen.add(canonical_url)
        return normalized

    @staticmethod
    def _is_explorable_page_url(url: str) -> bool:
        path = urlparse(url).path.casefold()
        blocked_extensions = {
            ".7z", ".avi", ".bmp", ".css", ".csv", ".doc", ".docx", ".exe",
            ".gif", ".gz", ".ico", ".jpeg", ".jpg", ".js", ".json", ".mkv",
            ".mov", ".mp3", ".mp4", ".pdf", ".png", ".ppt", ".pptx", ".rar",
            ".rss", ".svg", ".tar", ".tgz", ".tif", ".tiff", ".txt", ".wav",
            ".webm", ".webp", ".xml", ".xls", ".xlsx", ".zip",
        }
        return not any(path.endswith(extension) for extension in blocked_extensions)

    @classmethod
    def _json_mapping(cls, value: Mapping[str, Any]) -> dict[str, Any]:
        return {str(key): cls._json_value(item) for key, item in value.items()}

    @classmethod
    def _json_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Mapping):
            return cls._json_mapping(value)
        if isinstance(value, (list, tuple)):
            return [cls._json_value(item) for item in value]
        return str(value)
