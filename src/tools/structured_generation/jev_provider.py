"""TypeSafe Jev decisions for evidence-backed source evaluation."""

from __future__ import annotations

import json
import math
from typing import Any
from urllib.request import Request, urlopen

from src.core.settings import settings
from src.observability.events import model_exchange
from src.schemas.models import SourceProfile
from src.tools.web.models import SourcePreview


class JevDecisionProvider:
    provider_name = "jev"

    def __init__(self, *, api_key: str | None = None, model: str | None = None,
                 api_url: str | None = None, timeout: int | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.jev_api_key
        self.model = model or settings.jev_model
        self.api_url = api_url or settings.jev_api_url
        self.timeout = timeout or settings.source_evaluator_timeout
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def _request(self, *, state: dict[str, Any], questions: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("JEV_API_KEY is required when SOURCE_EVALUATOR_PROVIDER=jev.")
        payload = {"model": self.model, "state": state, "questions": questions}
        request = Request(
            self.api_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with model_exchange(model=self.model, provider="jev", request=payload) as observed:
            with urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            if (not isinstance(body, dict) or not isinstance(body.get("answers"), dict)
                    or not isinstance(body.get("model"), str)
                    or not isinstance(body.get("usage"), dict)):
                raise ValueError("Jev response did not match the structured answer envelope.")
            observed["output"] = body
            self.calls += 1
            usage = body["usage"]
            self.input_tokens += int(usage.get("input_tokens", 0))
            self.output_tokens += int(usage.get("output_tokens", 0))
            return body["answers"]

    @staticmethod
    def _number(answer: dict[str, Any], *, key: str, low: float, high: float) -> float:
        value = answer.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"Jev {key} answer must be numeric.")
        number = float(value)
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError(f"Jev {key} answer is outside [{low}, {high}].")
        return number

    def verify_profile(self, *, preview: SourcePreview, profile: SourceProfile) -> dict[str, float]:
        state = {
            "source_url": preview.url,
            "title": preview.title,
            "headings": preview.headings[:20],
            "publication_date": preview.publication_date,
            "updated_date": preview.updated_date,
            "preview_text": preview.relevant_text,
            "proposed_profile": profile.model_dump(mode="json"),
        }
        questions = {
            "source_type_supported": {"type": "noul", "instructions":
                "Does the supplied preview support the proposed source_type? Treat missing evidence as no."},
            "content_supported": {"type": "noul", "instructions":
                "Does the supplied preview support every proposed content characteristic, authority signal and content depth? Treat unsupported claims as no."},
            "scores_supported": {"type": "noul", "instructions":
                "Are the proposed authority, density, depth, recency and extractability scores plausible from the supplied preview and metadata alone? Treat unsupported certainty as no."},
        }
        answers = self._request(state=state, questions=questions)
        checks: dict[str, float] = {}
        for name in questions:
            answer = answers.get(name)
            if not isinstance(answer, dict) or answer.get("type") != "noul":
                raise ValueError(f"Jev omitted the {name} profile check.")
            checks[name] = self._number(answer, key="noul", low=0.0, high=1.0)
        return checks

    def score_relevance(self, *, preview: SourcePreview, topic: str, purpose: str) -> tuple[float, float]:
        answers = self._request(
            state={"source_url": preview.url, "title": preview.title,
                   "preview_text": preview.relevant_text, "dataset_topic": topic,
                   "dataset_purpose": purpose},
            questions={"topic_purpose_relevance": {"type": "score",
                "instructions": "Rate how directly the supplied source evidence supports the dataset topic and purpose. Do not infer unseen page content or score source policy here.",
                "criteria": [
                    "Unrelated or no usable evidence", "Weakly related",
                    "Partly related", "Clearly relevant", "Direct, substantial support",
                ]}},
        )
        answer = answers.get("topic_purpose_relevance")
        if (not isinstance(answer, dict) or answer.get("type") != "score"
                or not isinstance(answer.get("legend"), dict)
                or not isinstance(answer.get("probabilities"), dict)):
            raise ValueError("Jev omitted the topic/purpose score.")
        score = self._number(answer, key="score", low=0.0, high=4.0) / 4.0
        confidence = self._number(answer, key="confidence", low=0.0, high=1.0)
        return round(score, 6), confidence

    def metrics(self) -> dict[str, int | str]:
        return {"provider": self.provider_name, "model": self.model,
                "jev_calls": self.calls, "jev_input_tokens": self.input_tokens,
                "jev_output_tokens": self.output_tokens}
