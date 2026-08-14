"""Provider-neutral web discovery and acquisition boundary."""

from src.tools.web.acquisition_provider import WebAcquisitionProvider
from src.tools.web.crawl4ai_provider import Crawl4AIAcquisitionProvider
from src.tools.web.discovery_provider import SourceDiscoveryProvider
from src.tools.web.firecrawl_provider import FirecrawlDiscoveryProvider
from src.tools.web.models import AcquiredDocument, DiscoveredPage, DiscoveredSource, SourcePreview


def get_discovery_provider() -> SourceDiscoveryProvider:
    return FirecrawlDiscoveryProvider()


def get_acquisition_provider() -> WebAcquisitionProvider:
    return Crawl4AIAcquisitionProvider()


__all__ = [
    "AcquiredDocument",
    "DiscoveredPage",
    "DiscoveredSource",
    "SourcePreview",
    "SourceDiscoveryProvider",
    "WebAcquisitionProvider",
    "get_discovery_provider",
    "get_acquisition_provider",
]
