from typing import Any, Dict

from src.core.source_registry import CandidateRegistry
from src.core.settings import settings
from src.core.logging import get_logger
from src.schemas.models import DiscoveryOrigin
from src.tools.web import get_discovery_provider


logger = get_logger(__name__)


def _matches_preferred_domain(domain: str, preferred_domains: list[str]) -> bool:
    host = domain.lower().rstrip(".")
    return any(
        host == preferred.lower().rstrip(".")
        or host.endswith("." + preferred.lower().rstrip("."))
        for preferred in preferred_domains
    )


def source_search_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        logger.info("Searching candidate sources.")
        config = state.get("config", {})
        research = config.get("research", {})
        source_controls = config.get("sources", {})
        if not isinstance(source_controls, dict):
            source_controls = {}
        queries = state.get("research_plan", {}).get("search_queries", [])
        registry = CandidateRegistry(state.get("source_registry"))
        preferred_domains = source_controls.get(
            "preferred_domains",
            research.get("preferred_domains", []),
        )
        reference_urls = source_controls.get("seed_urls", research.get("reference_urls", []))
        for reference in reference_urls:
            url = reference.get("url") if isinstance(reference, dict) else reference
            if url:
                registry.add(
                    url,
                    origin=DiscoveryOrigin(
                        method="seed",
                        seed_url=url,
                        source_provider="user",
                    ),
                    title=reference.get("title", "") if isinstance(reference, dict) else "",
                    description=(
                        reference.get("description", "") if isinstance(reference, dict) else ""
                    ),
                    source_provider="user",
                )
        if settings.data_source_provider == "mock":
            legacy_mock_sources = config.get("mock_sources")
            if legacy_mock_sources is None and isinstance(config.get("sources"), list):
                legacy_mock_sources = config.get("sources", [])
            for source in legacy_mock_sources or []:
                if not source.get("enabled", True) or not source.get("url"):
                    continue
                query = str(source.get("search_query", "")).strip()
                method = "search" if query else "mock"
                registry.add(
                    source["url"],
                    origin=DiscoveryOrigin(
                        method=method,
                        query=query or None,
                        source_provider="mock",
                    ),
                    title=source.get("title", ""),
                    description=source.get("description", ""),
                    source_provider="mock",
                    candidate_metadata={
                        key: value
                        for key, value in source.items()
                        if key not in {
                            "url", "title", "description", "domain", "search_query",
                            "source_provider", "provider_metadata", "enabled",
                        }
                    },
                )
        else:
            provider = get_discovery_provider()
            for query in queries:
                discovered = provider.search(
                    query,
                    limit=research.get("max_sources", settings.default_max_sources),
                )
                for result in discovered:
                    registry.add(
                        result.url,
                        origin=DiscoveryOrigin(
                            method="search",
                            query=query,
                            source_provider=result.source_provider,
                        ),
                        title=result.title,
                        description=result.description,
                        source_provider=result.source_provider,
                        preferred_domain_match=bool(
                            preferred_domains
                            and _matches_preferred_domain(result.domain, preferred_domains)
                        ),
                        provider_metadata=result.provider_metadata,
                    )
        candidates = registry.as_pipeline_candidates()
        if preferred_domains:
            for candidate in candidates:
                if _matches_preferred_domain(candidate["domain"], preferred_domains):
                    registry.mark_preferred_domain(candidate["canonical_url"])
            candidates = registry.as_pipeline_candidates()
        logger.info("Discovered %d canonical candidate sources.", len(registry))
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": candidates,
            "status": "sources_discovered",
            "pipeline_status": "sources_discovered",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "source_search", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
