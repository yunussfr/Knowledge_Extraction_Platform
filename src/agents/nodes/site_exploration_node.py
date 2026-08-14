"""Optionally expand useful source domains under explicit crawl bounds."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict
from urllib.parse import urlparse

from src.core.logging import get_logger
from src.core.settings import settings
from src.core.source_registry import CandidateRegistry, normalize_candidate_url
from src.schemas.models import DiscoveryOrigin, SiteExplorationConfiguration
from src.tools.web import get_acquisition_provider


logger = get_logger(__name__)


def _query_terms(state: Dict[str, Any]) -> list[str]:
    plan = state.get("research_plan", {})
    terms: list[str] = []
    for value in [*plan.get("subtopics", []), *plan.get("search_queries", [])]:
        term = str(value).strip()
        if term and term.casefold() not in {item.casefold() for item in terms}:
            terms.append(term)
    return terms


def _exploration_starts(
    state: Dict[str, Any],
    config: SiteExplorationConfiguration,
) -> list[str]:
    candidates = [
        *state.get("selected_sources", []),
        *(
            item
            for item in state.get("candidate_sources", [])
            if item.get("user_seed") or item.get("user_supplied_reference")
        ),
    ]
    starts: list[str] = []
    domains: set[str] = set()
    for candidate in candidates:
        raw_url = candidate.get("canonical_url") or candidate.get("url")
        if not raw_url:
            continue
        try:
            url = normalize_candidate_url(raw_url)
        except ValueError:
            continue
        domain = (urlparse(url).hostname or "").lower()
        if not domain or domain in domains:
            continue
        domains.add(domain)
        starts.append(url)
        if len(domains) >= config.max_seed_domains:
            break
    return starts


def site_exploration_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Explore selected/seed domains without evaluating or selecting new pages."""
    try:
        raw_config = state.get("config", {}).get("site_exploration", {})
        config = SiteExplorationConfiguration.model_validate(raw_config)
        if not config.enabled:
            return {
                "status": "site_exploration_complete",
                "pipeline_status": "site_exploration_complete",
            }

        registry = CandidateRegistry(state.get("source_registry"))
        explored_starts = {
            normalize_candidate_url(url)
            for url in state.get("explored_site_starts", [])
        }
        starts = [
            url for url in _exploration_starts(state, config)
            if url not in explored_starts
        ]
        if not starts:
            return {
                "status": "site_exploration_complete",
                "pipeline_status": "site_exploration_complete",
            }

        provider = get_acquisition_provider()
        all_results = list(state.get("site_exploration_results", []))
        result_urls = {
            normalize_candidate_url(item["url"])
            for item in all_results
            if isinstance(item, dict) and item.get("url")
        }
        new_starts: list[str] = []
        per_domain_counts: Counter[str] = Counter()
        errors = list(state.get("errors", []))
        terms = _query_terms(state)

        logger.info("Exploring %d source domains under explicit crawl limits.", len(starts))
        for start_url in starts:
            try:
                pages = provider.explore_site(
                    start_url,
                    query_terms=terms,
                    max_depth=config.max_depth,
                    max_pages=config.max_pages_per_domain,
                    same_domain_only=config.same_domain_only,
                )
            except Exception as exc:
                errors.append({
                    "node": "site_exploration",
                    "source_url": start_url,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                new_starts.append(start_url)
                continue

            for page in pages:
                canonical_page_url = normalize_candidate_url(page.url)
                if canonical_page_url in result_urls:
                    continue
                domain = (urlparse(page.url).hostname or "").lower()
                if per_domain_counts[domain] >= config.max_pages_per_domain:
                    continue
                registry.add(
                    page.url,
                    origin=DiscoveryOrigin(
                        method="site_exploration",
                        seed_url=start_url,
                        parent_url=page.parent_url,
                        depth=page.depth,
                        source_provider="crawl4ai",
                    ),
                    title=page.title,
                    source_provider="crawl4ai",
                )
                all_results.append(page.model_dump(mode="json"))
                result_urls.add(canonical_page_url)
                per_domain_counts[domain] += 1
            new_starts.append(start_url)

        completed_starts = list(dict.fromkeys([
            *state.get("explored_site_starts", []),
            *new_starts,
        ]))
        logger.info(
            "Site exploration added %d bounded page results.",
            sum(per_domain_counts.values()),
        )
        return {
            "source_registry": registry.as_serialized(),
            "candidate_sources": registry.as_pipeline_candidates(),
            "explored_site_starts": completed_starts,
            "site_exploration_results": all_results,
            "errors": errors,
            "status": "site_exploration_complete",
            "pipeline_status": "site_exploration_complete",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{
                "node": "site_exploration",
                "error": str(error),
            }],
            "status": "failed",
            "pipeline_status": "failed",
        }
