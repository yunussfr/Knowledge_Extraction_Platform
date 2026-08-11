"""Centralized environment settings for providers and pipeline behavior."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


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
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    groq_temperature: float = _float("GROQ_TEMPERATURE", 0.0)
    groq_request_timeout: int = _integer("GROQ_REQUEST_TIMEOUT", 60)
    groq_max_retries: int = _integer("GROQ_MAX_RETRIES", 2)
    run_integration_tests: bool = _boolean("RUN_INTEGRATION_TESTS", False)
    default_max_search_queries: int = _integer("DEFAULT_MAX_SEARCH_QUERIES", 10)
    default_max_sources: int = _integer("DEFAULT_MAX_SOURCES", 20)
    require_schema_approval: bool = _boolean("REQUIRE_SCHEMA_APPROVAL", True)
    minimum_confidence: float = _float("MINIMUM_CONFIDENCE", 0.70)
    low_confidence_action: str = os.getenv("LOW_CONFIDENCE_ACTION", "reject")
    max_extraction_retries: int = _integer("MAX_EXTRACTION_RETRIES", 3)
    validate_structured_output: bool = _boolean("VALIDATE_STRUCTURED_OUTPUT", True)
    output_directory: str = os.getenv("OUTPUT_DIRECTORY", "./knowledge/datasets")
    default_output_format: str = os.getenv("DEFAULT_OUTPUT_FORMAT", "json")
    save_raw_content: bool = _boolean("SAVE_RAW_CONTENT", False)
    save_clean_content: bool = _boolean("SAVE_CLEAN_CONTENT", False)


settings = Settings()
