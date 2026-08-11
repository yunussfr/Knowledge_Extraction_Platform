from typing import Dict, Any
from urllib.parse import urlparse
from src.state.state import AgentState
from src.core.settings import settings
from src.tools.firecrawl_tool import FirecrawlTool

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
                for source in selected_sources:
                    scraped = FirecrawlTool().scrape(source["url"])
                    scraped["metadata"] = {
                        **scraped.get("metadata", {}),
                        "source_domain": source.get("domain") or urlparse(scraped["source"]).netloc,
                        "source_provider": "firecrawl",
                        "search_query": source.get("search_query", ""),
                        "candidate_title": source.get("title", ""),
                    }
                    scraped["title"] = scraped.get("title") or source.get("title", "")
                    raw_data.append(scraped)
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
