"""Data structures for cross-encoder candidate reranking."""

from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class RerankItem(BaseModel):
    """Result of reranking one candidate."""

    url: str
    candidate_id: Optional[str] = None
    title: str = ""
    description: str = ""
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    passed_threshold: bool = False
    rejection_reason: Optional[str] = None


class RerankBatchResult(BaseModel):
    """Aggregate result from reranking candidates."""

    ranked_items: List[RerankItem] = Field(default_factory=list)
    accepted_items: List[RerankItem] = Field(default_factory=list)
    rejected_items: List[RerankItem] = Field(default_factory=list)
    threshold: float = 0.60
    model: str = "BAAI/bge-reranker-v2-m3"
    provider: str = "cross_encoder"
