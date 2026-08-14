"""Page-level web acquisition provider protocol."""

from typing import Protocol, runtime_checkable

from src.tools.web.models import AcquiredDocument, DiscoveredPage, SourcePreview


@runtime_checkable
class WebAcquisitionProvider(Protocol):
    def preview(self, url: str, *, query: str | None = None) -> SourcePreview:
        ...

    def acquire(self, url: str) -> AcquiredDocument:
        ...

    def acquire_many(self, urls: list[str]) -> list[AcquiredDocument]:
        ...

    def explore_site(
        self,
        start_url: str,
        *,
        query_terms: list[str],
        max_depth: int,
        max_pages: int,
        same_domain_only: bool = True,
    ) -> list[DiscoveredPage]:
        ...
