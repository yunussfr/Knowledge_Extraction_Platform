"""Canonical source-candidate registry with conservative URL normalization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit

from src.schemas.models import DiscoveryOrigin, SourceCandidate


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


def normalize_candidate_url(url: str) -> str:
    """Normalize only URL differences that safely identify the same resource."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Candidate URL must be a non-empty string.")
    value = url.strip()
    if any(ord(character) < 32 for character in value):
        raise ValueError("Candidate URL cannot contain control characters.")

    parsed = urlsplit(value)
    address_without_fragment = value.split("#", 1)[0]
    has_explicit_empty_query = "?" in address_without_fragment and parsed.query == ""
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"Candidate URL must be absolute HTTP(S): {url}")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Candidate URLs cannot contain embedded user credentials.")

    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"Candidate URL has an invalid port: {url}") from exc

    hostname = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        rendered_host = f"{rendered_host}:{port}"

    normalized = SplitResult(
        scheme=scheme,
        netloc=rendered_host,
        path=parsed.path or "/",
        query=parsed.query,
        fragment="",
    )
    canonical = urlunsplit(normalized)
    return canonical + "?" if has_explicit_empty_query else canonical


class CandidateRegistry:
    """Ordered canonical registry; values remain JSON-serializable Pydantic models."""

    def __init__(self, serialized: Mapping[str, Any] | None = None) -> None:
        self._candidates: dict[str, SourceCandidate] = {}
        for key, value in (serialized or {}).items():
            candidate = SourceCandidate.model_validate(value)
            canonical = normalize_candidate_url(candidate.canonical_url)
            if canonical != key or candidate.canonical_url != canonical:
                raise ValueError("Source registry keys must match normalized canonical URLs.")
            self._candidates[canonical] = candidate

    def add(
        self,
        url: str,
        *,
        origin: DiscoveryOrigin,
        title: str = "",
        description: str = "",
        source_provider: str = "",
        preferred_domain_match: bool = False,
        provider_metadata: Mapping[str, Any] | None = None,
        candidate_metadata: Mapping[str, Any] | None = None,
    ) -> SourceCandidate:
        canonical_url = normalize_candidate_url(url)
        original_url = url.strip()
        candidate = self._candidates.get(canonical_url)
        if candidate is None:
            parsed = urlsplit(canonical_url)
            candidate = SourceCandidate(
                canonical_url=canonical_url,
                original_urls=[original_url],
                domain=(parsed.hostname or "").lower(),
                title=title,
                description=description,
                discovery_origins=[origin],
                user_seed=origin.method == "seed",
                source_providers=[source_provider] if source_provider else [],
                preferred_domain_match=preferred_domain_match,
                provider_metadata=_json_safe(provider_metadata or {}),
                candidate_metadata=_json_safe(candidate_metadata or {}),
            )
            self._candidates[canonical_url] = candidate
            return candidate

        if original_url not in candidate.original_urls:
            candidate.original_urls.append(original_url)
        if not any(existing == origin for existing in candidate.discovery_origins):
            candidate.discovery_origins.append(origin)
        if not candidate.title and title:
            candidate.title = title
        if not candidate.description and description:
            candidate.description = description
        if source_provider and source_provider.casefold() not in {
            item.casefold() for item in candidate.source_providers
        }:
            candidate.source_providers.append(source_provider)
        candidate.user_seed = candidate.user_seed or origin.method == "seed"
        candidate.preferred_domain_match = (
            candidate.preferred_domain_match or preferred_domain_match
        )
        for key, value in (provider_metadata or {}).items():
            candidate.provider_metadata.setdefault(str(key), _json_safe(value))
        for key, value in (candidate_metadata or {}).items():
            candidate.candidate_metadata.setdefault(str(key), _json_safe(value))
        return candidate

    def set_preview_status(self, url: str, status: str) -> None:
        candidate = self._require(url)
        updated = SourceCandidate.model_validate({
            **candidate.model_dump(),
            "preview_status": status,
        })
        self._candidates[candidate.canonical_url] = updated

    def mark_preferred_domain(self, url: str) -> None:
        self._require(url).preferred_domain_match = True

    def record_evaluation(
        self,
        *,
        selected_sources: list[Mapping[str, Any]],
        rejected_sources: list[Mapping[str, Any]],
    ) -> None:
        for rejected in rejected_sources:
            candidate = self._find(rejected.get("url"))
            if candidate is None:
                continue
            candidate.evaluation_status = "completed"
            candidate.selection_state = "rejected"
            candidate.selected = False
            reason = str(rejected.get("reason", "")).strip()
            if reason and reason.casefold() not in {
                item.casefold() for item in candidate.rejection_reasons
            }:
                candidate.rejection_reasons.append(reason)

        for selected in selected_sources:
            candidate = self._find(selected.get("url"))
            if candidate is None:
                continue
            candidate.evaluation_status = "completed"
            candidate.selection_state = "selected"
            candidate.selected = True

    def record_policy_evaluations(self, evaluations: list[Mapping[str, Any]]) -> None:
        for raw_evaluation in evaluations:
            candidate = self._find(raw_evaluation.get("url"))
            if candidate is None:
                continue
            evaluation = _json_safe(raw_evaluation)
            candidate.source_profile = evaluation.get("source_profile")
            candidate.policy_evaluation = {
                key: value
                for key, value in evaluation.items()
                if key != "source_profile"
            }
            candidate.evaluation_status = "completed"
            decision = evaluation.get("decision")
            candidate.selection_state = "selected" if decision == "select" else "rejected"
            candidate.selected = decision == "select"
            if decision == "reject":
                for reason in evaluation.get("reasons", []):
                    if reason.casefold() not in {
                        item.casefold() for item in candidate.rejection_reasons
                    }:
                        candidate.rejection_reasons.append(reason)

    def as_serialized(self) -> dict[str, dict[str, Any]]:
        return {
            url: candidate.model_dump(mode="json")
            for url, candidate in self._candidates.items()
        }

    def as_pipeline_candidates(self) -> list[dict[str, Any]]:
        return [candidate.to_pipeline_candidate() for candidate in self._candidates.values()]

    def pending_preview_urls(self) -> list[str]:
        """Return each canonical URL at most once and never repeat completed work."""
        return [
            candidate.canonical_url
            for candidate in self._candidates.values()
            if candidate.preview_status == "pending"
        ]

    def __len__(self) -> int:
        return len(self._candidates)

    def _find(self, url: Any) -> SourceCandidate | None:
        if not isinstance(url, str):
            return None
        try:
            return self._candidates.get(normalize_candidate_url(url))
        except ValueError:
            return None

    def _require(self, url: str) -> SourceCandidate:
        candidate = self._find(url)
        if candidate is None:
            raise KeyError(f"Candidate is not registered: {url}")
        return candidate
