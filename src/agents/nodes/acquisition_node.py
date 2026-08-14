from time import perf_counter
from typing import Dict, Any

from src.state.state import AgentState
from src.core.settings import settings
from src.tools.web import get_acquisition_provider


def _is_cache_hit(document: Any) -> bool:
    cache_status = str(document.provider_metadata.get("cache_status", "")).casefold()
    return cache_status in {"hit", "cache_hit", "read", "cached"}

def acquisition_node(state: AgentState) -> Dict[str, Any]:
    try:
        raw_data = list(state.get("raw_data", []))
        selected_sources = state.get("selected_sources", [])

        print("Acquiring data...")
        if selected_sources:
            if not state.get("approved_dataset_schema"):
                return {
                    "errors": state.get("errors", []) + [{"node": "acquisition", "error": "Schema approval is required before scraping."}],
                    "status": "failed",
                    "pipeline_status": "failed",
                }
            if settings.data_source_provider == "mock":
                raw_data.extend({
                    "source": source["url"],
                    "content": source.get("content", "Mock source content."),
                    "title": source.get("title", ""),
                    "type": source.get("type", "web"),
                    "metadata": {
                        "title": source.get("title", ""),
                        "search_query": source.get("search_query", ""),
                        "source_domain": source.get("domain", ""),
                        "source_provider": "mock",
                    },
                } for source in selected_sources)
            else:
                provider = get_acquisition_provider()
                requested_urls = [source["url"] for source in selected_sources]
                started = perf_counter()
                acquired_documents = provider.acquire_many(requested_urls)
                duration = round(perf_counter() - started, 6)
                if len(acquired_documents) != len(selected_sources):
                    raise ValueError(
                        "Acquisition provider must return exactly one document per requested URL."
                    )
                if [item.source_url for item in acquired_documents] != requested_urls:
                    raise ValueError(
                        "Acquisition provider results must preserve requested URL order."
                    )
                successful = [item for item in acquired_documents if item.success]
                failed = [item for item in acquired_documents if not item.success]
                for source, acquired in zip(
                    selected_sources, acquired_documents, strict=True
                ):
                    if not acquired.success:
                        continue
                    raw_data.append(acquired.to_pipeline_document(
                        search_query=source.get("search_query", ""),
                        candidate_title=source.get("title", ""),
                    ))
                metrics = {
                    "requested_urls": len(requested_urls),
                    "successful_urls": len(successful),
                    "failed_urls": len(failed),
                    "cache_hits": sum(_is_cache_hit(item) for item in acquired_documents),
                    "acquisition_duration_seconds": duration,
                }
                errors = state.get("errors", []) + [{
                    "node": "acquisition",
                    "source_url": item.source_url,
                    "error": item.error or "Acquisition failed without a provider error.",
                } for item in failed]
                if not successful:
                    return {
                        "acquired_documents": [
                            item.model_dump(mode="json") for item in acquired_documents
                        ],
                        "acquisition_metrics": metrics,
                        "errors": errors,
                        "status": "failed",
                        "pipeline_status": "failed",
                    }
                return {
                    "raw_data": raw_data,
                    "scraped_documents": raw_data,
                    "acquired_documents": [
                        item.model_dump(mode="json") for item in acquired_documents
                    ],
                    "acquisition_metrics": metrics,
                    "errors": errors,
                    "status": "processing",
                    "pipeline_status": "processing",
                }
        elif state.get("dataset_topic"):
            return {
                "errors": state.get("errors", []) + [{"node": "acquisition", "error": "No sources were selected for scraping."}],
                "status": "failed",
                "pipeline_status": "failed",
            }
        elif not raw_data:
            raw_data.append({
                "source": "https://example.com/mock",
                "content": "This is mock raw content from the crawler.",
                "type": "html",
            })
        
        return {
            "raw_data": raw_data,
            "scraped_documents": raw_data,
            "status": "processing",
            "pipeline_status": "processing",
        }
    except Exception as e:
        return {
            "errors": state.get("errors", []) + [{"node": "acquisition", "error": str(e)}],
            "status": "failed",
            "pipeline_status": "failed",
        }
