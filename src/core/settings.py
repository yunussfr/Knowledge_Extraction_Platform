"""Centralized environment settings for providers and pipeline behavior."""

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _integer(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _boolean(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    data_source_provider: str = os.getenv("DATA_SOURCE_PROVIDER", "mock")
    firecrawl_api_key: str | None = os.getenv("FIRECRAWL_API_KEY")
    firecrawl_api_url: str = os.getenv("FIRECRAWL_API_URL", "https://api.firecrawl.dev")
    firecrawl_search_limit: int = _integer("FIRECRAWL_SEARCH_LIMIT", 10)
    request_timeout: int = _integer("FIRECRAWL_REQUEST_TIMEOUT", 60)
    firecrawl_max_retries: int = _integer("FIRECRAWL_MAX_RETRIES", 2)
    crawl4ai_headless: bool = _boolean("CRAWL4AI_HEADLESS", True)
    crawl4ai_page_timeout_ms: int = _integer("CRAWL4AI_PAGE_TIMEOUT_MS", 60000)
    crawl4ai_cache_mode: str = os.getenv("CRAWL4AI_CACHE_MODE", "enabled").strip().lower()
    crawl4ai_pruning_threshold: float = _float("CRAWL4AI_PRUNING_THRESHOLD", 0.45)
    crawl4ai_preview_max_words: int = _integer("CRAWL4AI_PREVIEW_MAX_WORDS", 400)
    crawl4ai_batch_concurrency: int = _integer("CRAWL4AI_BATCH_CONCURRENCY", 4)
    crawl4ai_batch_delay_seconds: float = _float(
        "CRAWL4AI_BATCH_DELAY_SECONDS", 0.25
    )
    content_min_words: int = _integer("CONTENT_MIN_WORDS", 30)
    crawl4ai_base_directory: str = os.getenv(
        "CRAWL4_AI_BASE_DIRECTORY",
        str(PROJECT_ROOT / ".runtime"),
    )
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_temperature: float = _float("GROQ_TEMPERATURE", 0.0)
    groq_request_timeout: int = _integer("GROQ_REQUEST_TIMEOUT", 60)
    groq_max_retries: int = _integer("GROQ_MAX_RETRIES", 2)
    groq_structured_output_mode: str = os.getenv(
        "GROQ_STRUCTURED_OUTPUT_MODE", "auto"
    ).strip().lower()
    run_integration_tests: bool = _boolean("RUN_INTEGRATION_TESTS", False)
    default_max_search_queries: int = _integer("DEFAULT_MAX_SEARCH_QUERIES", 10)
    default_max_sources: int = _integer("DEFAULT_MAX_SOURCES", 20)
    require_schema_approval: bool = _boolean("REQUIRE_SCHEMA_APPROVAL", True)
    minimum_confidence: float = _float("MINIMUM_CONFIDENCE", 0.70)
    minimum_evidence_quality: float = _float("MINIMUM_EVIDENCE_QUALITY", 0.70)
    allow_partially_supported: bool = _boolean("ALLOW_PARTIALLY_SUPPORTED", False)
    low_confidence_action: str = os.getenv("LOW_CONFIDENCE_ACTION", "reject")
    max_extraction_retries: int = _integer("MAX_EXTRACTION_RETRIES", 3)
    validate_structured_output: bool = _boolean("VALIDATE_STRUCTURED_OUTPUT", True)
    chunking_enabled: bool = _boolean("CHUNKING_ENABLED", True)
    chunk_target_tokens: int = _integer("CHUNK_TARGET_TOKENS", 6000)
    chunk_overlap_tokens: int = _integer("CHUNK_OVERLAP_TOKENS", 300)
    output_directory: str = os.getenv("OUTPUT_DIRECTORY", "./knowledge/datasets")
    default_output_format: str = os.getenv("DEFAULT_OUTPUT_FORMAT", "json")
    save_raw_content: bool = _boolean("SAVE_RAW_CONTENT", False)
    save_clean_content: bool = _boolean("SAVE_CLEAN_CONTENT", False)


settings = Settings()
