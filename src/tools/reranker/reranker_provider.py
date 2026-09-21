"""Cross-encoder candidate reranker provider with mock and CUDA support."""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Sequence

from src.core.logging import get_logger
from src.core.settings import settings
from src.tools.reranker.models import RerankBatchResult, RerankItem

logger = get_logger(__name__)


def _sigmoid(x: float) -> float:
    """Safely map any logit to [0.0, 1.0]."""
    if x >= 15.0:
        return 1.0
    if x <= -15.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


class BaseRerankerProvider(ABC):
    """Abstract interface for candidate rerankers."""

    @abstractmethod
    def rerank(
        self,
        *,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        threshold: float,
    ) -> RerankBatchResult:
        """Rerank candidates against query and filter by minimum threshold."""
        ...


class MockRerankerProvider(BaseRerankerProvider):
    """Deterministic mock provider for tests and offline development."""

    def __init__(self, model_name: str = "mock-reranker") -> None:
        self.model_name = model_name

    def rerank(
        self,
        *,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        threshold: float,
    ) -> RerankBatchResult:
        logger.info(
            "Mock reranking %d candidates against query with threshold %.2f",
            len(candidates),
            threshold,
        )
        query_words = set(query.lower().split())
        scored: List[tuple[float, Dict[str, Any]]] = []

        for candidate in candidates:
            # Check if explicit score exists in candidate metadata
            explicit_score = candidate.get("reranker_score") or candidate.get("topic_relevance_score")
            if explicit_score is not None:
                score = float(explicit_score)
            elif settings.data_source_provider == "mock":
                # In full mock pipeline tests, candidates represent verified test fixtures
                score = 1.0
            else:
                text = f"{candidate.get('title', '')} {candidate.get('description', '')}".lower()
                matches = sum(1 for w in query_words if w in text)
                score = min(1.0, 0.4 + (0.15 * matches)) if matches > 0 else 0.35
            scored.append((score, candidate))

        # Sort descending by score
        scored.sort(key=lambda x: -x[0])

        ranked_items: List[RerankItem] = []
        accepted_items: List[RerankItem] = []
        rejected_items: List[RerankItem] = []

        cand_counter = 1
        for score, candidate in scored:
            url = candidate.get("canonical_url") or candidate["url"]
            passed = score >= threshold
            candidate_id = f"cand_{cand_counter}" if passed else None
            rejection_reason = None

            if passed:
                cand_counter += 1
            else:
                rejection_reason = (
                    f"Cross-encoder relevance ({score:.4f}) is below minimum threshold ({threshold:.4f})."
                )

            item = RerankItem(
                url=url,
                candidate_id=candidate_id,
                title=candidate.get("title", ""),
                description=candidate.get("description", ""),
                score=round(score, 4),
                passed_threshold=passed,
                rejection_reason=rejection_reason,
            )
            ranked_items.append(item)
            if passed:
                accepted_items.append(item)
            else:
                rejected_items.append(item)

        return RerankBatchResult(
            ranked_items=ranked_items,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
            threshold=threshold,
            model=self.model_name,
            provider="mock",
        )


class CrossEncoderRerankerProvider(BaseRerankerProvider):
    """Real cross-encoder provider using HuggingFace / PyTorch (e.g. BAAI/bge-reranker-v2-m3)."""

    def __init__(
        self,
        *,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str | None = None,
        max_length: int = 512,
    ) -> None:
        self.model_name = model_name
        self.max_length = max_length
        self._device = device
        self._model = None
        self._tokenizer = None
        self._use_sentence_transformers = False

    def _resolve_device(self) -> str:
        if self._device:
            target = self._device.strip().lower()
            if target == "cuda":
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            return target
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _load_model(self) -> None:
        if self._model is not None:
            return

        import torch
        device = self._resolve_device()
        logger.info(
            "Loading cross-encoder model %s on device %s...",
            self.model_name,
            device,
        )

        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(
                self.model_name,
                max_length=self.max_length,
                device=device,
                trust_remote_code=True,
            )
            self._use_sentence_transformers = True
            logger.info("Loaded CrossEncoder via sentence_transformers on %s", device)
        except (ImportError, Exception) as exc:
            logger.info(
                "sentence_transformers load bypassed (%s), loading via transformers...",
                exc,
            )
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
            )
            self._model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                trust_remote_code=True,
            )
            self._model.to(device)
            self._model.eval()
            self._use_sentence_transformers = False
            logger.info("Loaded model via transformers on %s", device)

    def _score_pairs(self, pairs: List[List[str]]) -> List[float]:
        """Compute sigmoid-normalized relevance scores in [0.0, 1.0] for (query, doc) pairs."""
        if not pairs:
            return []

        self._load_model()
        import torch

        if self._use_sentence_transformers:
            # CrossEncoder.predict returns raw logits or array
            raw_scores = self._model.predict(pairs, show_progress_bar=False)
            scores: List[float] = []
            for s in raw_scores:
                val = float(s)
                # If model already outputs sigmoid (between 0 and 1) or logits:
                # bge-reranker outputs logits (can be negative or > 1), so apply sigmoid
                scores.append(_sigmoid(val))
            return scores
        else:
            device = self._resolve_device()
            scores: List[float] = []
            batch_size = 16
            for i in range(0, len(pairs), batch_size):
                batch_pairs = pairs[i : i + batch_size]
                encoded = self._tokenizer(
                    batch_pairs,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                ).to(device)
                with torch.no_grad():
                    outputs = self._model(**encoded, return_dict=True)
                    logits = outputs.logits.view(-1).float()
                    batch_scores = torch.sigmoid(logits).cpu().tolist()
                    if isinstance(batch_scores, float):
                        batch_scores = [batch_scores]
                    scores.extend(batch_scores)
            return scores

    def rerank(
        self,
        *,
        query: str,
        candidates: Sequence[Dict[str, Any]],
        threshold: float,
    ) -> RerankBatchResult:
        if not candidates:
            return RerankBatchResult(
                ranked_items=[],
                accepted_items=[],
                rejected_items=[],
                threshold=threshold,
                model=self.model_name,
                provider="cross_encoder",
            )

        logger.info(
            "Cross-encoder reranking %d candidates against query with threshold %.4f",
            len(candidates),
            threshold,
        )

        pairs: List[List[str]] = []
        for candidate in candidates:
            title = str(candidate.get("title", "")).strip()
            desc = str(candidate.get("description", "")).strip()
            doc_text = f"{title}\n{desc}".strip() or candidate.get("canonical_url") or candidate.get("url", "")
            pairs.append([query, doc_text])

        scores = self._score_pairs(pairs)

        scored_candidates: List[tuple[float, Dict[str, Any]]] = [
            (score, candidate) for score, candidate in zip(scores, candidates)
        ]
        # Sort descending by score
        scored_candidates.sort(key=lambda x: -x[0])

        ranked_items: List[RerankItem] = []
        accepted_items: List[RerankItem] = []
        rejected_items: List[RerankItem] = []

        cand_counter = 1
        for score, candidate in scored_candidates:
            url = candidate.get("canonical_url") or candidate["url"]
            passed = score >= threshold
            candidate_id = f"cand_{cand_counter}" if passed else None
            rejection_reason = None

            if passed:
                cand_counter += 1
            else:
                rejection_reason = (
                    f"Cross-encoder relevance ({score:.4f}) is below minimum threshold ({threshold:.4f})."
                )

            item = RerankItem(
                url=url,
                candidate_id=candidate_id,
                title=candidate.get("title", ""),
                description=candidate.get("description", ""),
                score=round(score, 4),
                passed_threshold=passed,
                rejection_reason=rejection_reason,
            )
            ranked_items.append(item)
            if passed:
                accepted_items.append(item)
            else:
                rejected_items.append(item)

        logger.info(
            "Reranking completed: %d passed threshold (>= %.2f), %d filtered out.",
            len(accepted_items),
            threshold,
            len(rejected_items),
        )

        return RerankBatchResult(
            ranked_items=ranked_items,
            accepted_items=accepted_items,
            rejected_items=rejected_items,
            threshold=threshold,
            model=self.model_name,
            provider="cross_encoder",
        )


def get_reranker_provider(
    provider_name: str | None = None,
    model_name: str | None = None,
    device: str | None = None,
) -> BaseRerankerProvider:
    """Factory returning the configured reranker provider."""
    configured = (provider_name or settings.reranker_provider).strip().lower()

    if settings.data_source_provider == "mock" or configured == "mock":
        return MockRerankerProvider(model_name=model_name or "mock-reranker")

    try:
        import torch  # noqa: F401
    except ImportError:
        logger.warning("PyTorch is not installed. Falling back to MockRerankerProvider.")
        return MockRerankerProvider(model_name=model_name or "mock-reranker")

    return CrossEncoderRerankerProvider(
        model_name=model_name or settings.reranker_model,
        device=device or settings.reranker_device,
    )
