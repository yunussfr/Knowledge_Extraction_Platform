from typing import Any, Dict
from urllib.parse import urlparse

from src.core.settings import settings
from src.core.logging import get_logger
from src.tools.firecrawl_tool import FirecrawlTool


logger = get_logger(__name__)


def source_search_node(state: Dict[str, Any]) -> Dict[str, Any]:
    try:
        logger.info("Searching candidate sources.")
        config = state.get("config", {})
        queries = state.get("research_plan", {}).get("search_queries", [])
        found = []
        reference_urls = config.get("research", {}).get("reference_urls", [])
        for reference in reference_urls:
            url = reference.get("url") if isinstance(reference, dict) else reference
            if url:
                found.append({
                    "url": url,
                    "title": reference.get("title", "") if isinstance(reference, dict) else "",
                    "description": reference.get("description", "") if isinstance(reference, dict) else "",
                    "search_query": "user reference",
                    "user_supplied_reference": True,
                })
        if settings.data_source_provider == "mock":
            found.extend(source for source in config.get("sources", []) if source.get("enabled", True))
        else:
            tool = FirecrawlTool()
            for query in queries:
                for source in tool.search(query, config.get("research", {}).get("max_sources", settings.default_max_sources)):
                    source["search_query"] = query
                    found.append(source)
        preferred_domains = config.get("research", {}).get("preferred_domains", [])
        unique = {}
        for source in found:
            url = source.get("url", "")
            if url:
                source["domain"] = source.get("domain") or urlparse(url).netloc
                if preferred_domains and not source.get("user_supplied_reference"):
                    if not any(source["domain"].endswith(domain) for domain in preferred_domains):
                        continue
                unique[url] = source
        logger.info("Discovered %d unique candidate sources.", len(unique))
        return {
            "candidate_sources": list(unique.values()),
            "status": "sources_discovered",
            "pipeline_status": "sources_discovered",
        }
    except Exception as error:
        return {
            "errors": state.get("errors", []) + [{"node": "source_search", "error": str(error)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
