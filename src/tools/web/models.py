"""Internal web contracts; provider SDK objects never cross this boundary."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


class DiscoveredSource(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    domain: str = ""
    source_provider: str
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Discovered source URLs must be absolute HTTP(S) URLs.")
        return value


class SourcePreview(BaseModel):
    url: str
    title: str = ""
    domain: str = ""
    headings: list[str] = Field(default_factory=list)
    relevant_text: str = ""
    approximate_word_count: int | None = None
    preview_word_count: int = 0
    internal_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    language: str | None = None
    publication_date: str | None = None
    updated_date: str | None = None
    structure_hints: list[str] = Field(default_factory=list)
    fetch_success: bool
    error: str | None = None


class DiscoveredPage(BaseModel):
    url: str
    title: str = ""
    depth: int = Field(ge=0)
    parent_url: str | None = None


class AcquiredDocument(BaseModel):
    source_url: str
    canonical_url: str | None = None
    title: str = ""
    domain: str = ""
    raw_markdown: str = ""
    fit_markdown: str | None = None
    html: str | None = None
    internal_links: list[str] = Field(default_factory=list)
    external_links: list[str] = Field(default_factory=list)
    retrieved_at: str
    source_provider: str
    content_hash: str
    success: bool
    error: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    def to_pipeline_document(
        self,
        *,
        search_query: str = "",
        candidate_title: str = "",
    ) -> dict[str, Any]:
        """Compatibility projection while downstream content contracts migrate."""
        return {
            "source": self.canonical_url or self.source_url,
            "title": self.title or candidate_title,
            "content": self.fit_markdown or self.raw_markdown,
            "type": "web",
            "metadata": {
                **self.provider_metadata,
                "source_domain": self.domain,
                "source_provider": self.source_provider,
                "search_query": search_query,
                "candidate_title": candidate_title,
                "retrieved_at": self.retrieved_at,
                "content_hash": self.content_hash,
                "canonical_url": self.canonical_url,
                "acquisition_success": self.success,
                "acquisition_error": self.error,
                "internal_links": self.internal_links,
                "external_links": self.external_links,
            },
        }
