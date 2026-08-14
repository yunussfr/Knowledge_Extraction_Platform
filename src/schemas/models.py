"""Pydantic models shared by the dataset-generation pipeline."""

from enum import Enum
from statistics import fmean
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalized_unique_strings(values: List[str] | None) -> List[str] | None:
    if values is None:
        return None
    normalized: List[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = raw_value.strip()
        if not value:
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized


class SourceImportance(BaseModel):
    """Request-specific weights; none of these values is a hard restriction."""

    authority: Literal["low", "medium", "high"] = "medium"
    technical_depth: Literal["low", "medium", "high"] = "medium"
    information_density: Literal["low", "medium", "high"] = "medium"
    recency: Literal["low", "medium", "high"] = "medium"
    extractability: Literal["low", "medium", "high"] = "medium"


class SourcePolicy(BaseModel):
    """Typed user policy with absence-preserving hard-rule semantics."""

    preferred_source_types: List[str] = Field(default_factory=list)
    allowed_source_types: Optional[List[str]] = None
    blocked_source_types: Optional[List[str]] = None
    desired_content: List[str] = Field(default_factory=list)
    avoided_content: List[str] = Field(default_factory=list)
    minimum_content_depth: Optional[Literal["shallow", "medium", "deep"]] = None
    importance: SourceImportance = Field(default_factory=SourceImportance)

    @field_validator(
        "preferred_source_types", "allowed_source_types", "blocked_source_types",
        "desired_content", "avoided_content", mode="before",
    )
    @classmethod
    def normalize_policy_lists(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("Source policy list fields must be lists when supplied.")
        return _normalized_unique_strings(value)

    @model_validator(mode="after")
    def reject_conflicting_source_type_rules(self):
        allowed = {item.casefold() for item in self.allowed_source_types or []}
        blocked = {item.casefold() for item in self.blocked_source_types or []}
        conflict = allowed & blocked
        if conflict:
            raise ValueError(
                "Source types cannot be both allowed and blocked: "
                + ", ".join(sorted(conflict))
            )
        return self

    @property
    def has_source_type_allowlist(self) -> bool:
        return bool(self.allowed_source_types)

    @property
    def has_source_type_blocklist(self) -> bool:
        return bool(self.blocked_source_types)


class SourceConfiguration(BaseModel):
    """Seed, soft domain preferences, explicit hard domain rules, and policy."""

    seed_urls: List[str] = Field(default_factory=list)
    preferred_domains: List[str] = Field(default_factory=list)
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)

    @field_validator("seed_urls", mode="before")
    @classmethod
    def normalize_seed_urls(cls, value: Any) -> List[str]:
        from urllib.parse import urlparse

        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("seed_urls must be a list when supplied.")
        normalized = _normalized_unique_strings(value) or []
        for url in normalized:
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Seed URL must be an absolute HTTP(S) URL: {url}")
        return normalized

    @field_validator("preferred_domains", "allowed_domains", "blocked_domains", mode="before")
    @classmethod
    def normalize_domains(cls, value: Any) -> Any:
        if value is None:
            return None
        if not isinstance(value, list):
            raise ValueError("Domain control fields must be lists when supplied.")
        normalized = _normalized_unique_strings(value)
        result = []
        for domain in normalized or []:
            domain = domain.lower().rstrip(".")
            if "://" in domain or "/" in domain:
                raise ValueError(f"Domain controls require hostnames, not URLs: {domain}")
            result.append(domain)
        return result

    @model_validator(mode="after")
    def reject_conflicting_domain_rules(self):
        allowed = set(self.allowed_domains or [])
        blocked = set(self.blocked_domains or [])
        conflict = allowed & blocked
        if conflict:
            raise ValueError(
                "Domains cannot be both allowed and blocked: "
                + ", ".join(sorted(conflict))
            )
        return self


class DatasetRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    profile: Literal["structured", "rag", "graphrag"] = "structured"


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    max_queries: int = Field(default=10, ge=1)
    max_sources: int = Field(default=20, ge=1)
    constraints: str = ""
    queries: List[str] = Field(default_factory=list)
    auto_generate_queries: bool = True


class SiteExplorationConfiguration(BaseModel):
    enabled: bool = False
    max_seed_domains: int = Field(default=5, ge=1)
    max_depth: int = Field(default=2, ge=1)
    max_pages_per_domain: int = Field(default=25, ge=1)
    same_domain_only: bool = True


class RequestConfiguration(BaseModel):
    """Deterministically validated user request while preserving later-phase sections."""

    model_config = ConfigDict(extra="allow")

    dataset: DatasetRequest
    research: ResearchRequest = Field(default_factory=ResearchRequest)
    sources: SourceConfiguration = Field(default_factory=SourceConfiguration)
    site_exploration: SiteExplorationConfiguration = Field(
        default_factory=SiteExplorationConfiguration
    )
    schema_config: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("schema", "schema_config"),
        serialization_alias="schema",
    )
    extraction: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)
    output: Dict[str, Any] = Field(default_factory=dict)


class MetadataSchema(BaseModel):
    schema_version: str = Field(default="1.0", description="JSON schema version")
    source_url: str = Field(..., description="URL from which the data was collected")
    source_type: str = Field(..., description="web, pdf, api, or manual")
    retrieved_at: str = Field(..., description="Collection time in ISO 8601 format")
    processed_at: str = Field(..., description="Processing completion time in ISO 8601 format")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Evidence-support score")
    validation_method: str = Field(..., description="Validation strategy")
    reviewed_by: Optional[str] = Field(default=None, description="Human reviewer identifier")
    domain_specific: Optional[Dict[str, Any]] = Field(default=None, description="Domain-specific metadata")


class KnowledgeRecord(BaseModel):
    id: str
    domain: str
    title: str
    content: str
    relations: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    metadata: MetadataSchema
    validation_status: str


class ResearchPlannerInput(BaseModel):
    """Serializable request context available at the planner boundary."""

    dataset_topic: str
    dataset_purpose: str
    source_policy: SourcePolicy
    seed_urls: List[str] = Field(default_factory=list)
    preferred_domains: List[str] = Field(default_factory=list)
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    max_queries: int = Field(ge=1, default=10)
    constraints: str = ""


class SourceEvaluatorInput(BaseModel):
    """Serializable request and evidence available to source evaluation."""

    dataset_topic: str
    dataset_purpose: str
    source_policy: SourcePolicy
    preferred_domains: List[str] = Field(default_factory=list)
    allowed_domains: Optional[List[str]] = None
    blocked_domains: Optional[List[str]] = None
    research_plan: Dict[str, Any] = Field(default_factory=dict)
    research_constraints: str = ""
    candidate_sources: List[Dict[str, Any]] = Field(default_factory=list)
    source_previews: List[Dict[str, Any]] = Field(default_factory=list)


class ResearchQueryFamily(BaseModel):
    name: str = Field(min_length=1)
    purpose: str = ""
    queries: List[str] = Field(default_factory=list)

    @field_validator("queries", mode="before")
    @classmethod
    def normalize_queries(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Query family queries must be a list.")
        return _normalized_unique_strings(value) or []


class Entity(BaseModel):
    name: str
    type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    source_entity: str
    target_entity: str
    relation_type: str
    attributes: Dict[str, Any] = Field(default_factory=dict)


class EnrichedData(BaseModel):
    entities: List[Entity] = Field(default_factory=list)
    relations: List[Relation] = Field(default_factory=list)
    raw_content: str = ""
    cleaned_content: str = ""


class ResearchPlan(BaseModel):
    research_topic: str = Field(validation_alias=AliasChoices("research_topic", "researchTopic"))
    subtopics: List[str] = Field(default_factory=list, validation_alias=AliasChoices("subtopics", "subTopics"))
    search_queries: List[str] = Field(default_factory=list, validation_alias=AliasChoices("search_queries", "searchQueries"))
    preferred_source_types: List[str] = Field(default_factory=list, validation_alias=AliasChoices("preferred_source_types", "preferredSourceTypes"))
    excluded_source_types: List[str] = Field(default_factory=list, validation_alias=AliasChoices("excluded_source_types", "excludedSourceTypes"))
    query_families: List[ResearchQueryFamily] = Field(
        default_factory=list,
        validation_alias=AliasChoices("query_families", "queryFamilies"),
    )

    @field_validator("search_queries", mode="before")
    @classmethod
    def normalize_search_queries(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("search_queries must be a list.")
        return _normalized_unique_strings(value) or []

    @model_validator(mode="after")
    def ensure_query_families_are_non_duplicate(self):
        family_names: set[str] = set()
        family_queries: set[str] = set()
        for family in self.query_families:
            family_name = family.name.casefold()
            if family_name in family_names:
                raise ValueError(f"Duplicate research query family: {family.name}")
            family_names.add(family_name)
            for query in family.queries:
                normalized_query = query.casefold()
                if normalized_query in family_queries:
                    raise ValueError(f"Query appears in more than one family: {query}")
                family_queries.add(normalized_query)
        return self


class CandidateSource(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    domain: str = ""
    search_query: str = Field(default="", validation_alias=AliasChoices("search_query", "searchQuery"))


class DiscoveryOrigin(BaseModel):
    """One independently preserved path by which a candidate was discovered."""

    method: Literal["search", "seed", "mock", "site_exploration"]
    query: Optional[str] = None
    seed_url: Optional[str] = None
    parent_url: Optional[str] = None
    depth: Optional[int] = Field(default=None, ge=0)
    source_provider: Optional[str] = None

    @model_validator(mode="after")
    def validate_method_context(self):
        if self.method == "search" and not (self.query or "").strip():
            raise ValueError("Search discovery origins require a query.")
        if self.method == "seed" and not (self.seed_url or "").strip():
            raise ValueError("Seed discovery origins require seed_url.")
        if self.method == "site_exploration" and not (self.seed_url or "").strip():
            raise ValueError("Site-exploration origins require seed_url.")
        return self


class SourceCandidate(BaseModel):
    """Canonical candidate with discovery history and reusable work state."""

    canonical_url: str
    original_urls: List[str] = Field(min_length=1)
    domain: str
    title: str = ""
    description: str = ""
    discovery_origins: List[DiscoveryOrigin] = Field(min_length=1)
    user_seed: bool = False
    preview_status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    evaluation_status: Literal["pending", "in_progress", "completed", "failed", "skipped"] = "pending"
    selection_state: Literal["pending", "selected", "rejected"] = "pending"
    selected: bool = False
    rejection_reasons: List[str] = Field(default_factory=list)
    source_providers: List[str] = Field(default_factory=list)
    preferred_domain_match: bool = False
    provider_metadata: Dict[str, Any] = Field(default_factory=dict)
    candidate_metadata: Dict[str, Any] = Field(default_factory=dict)
    source_profile: Optional[Dict[str, Any]] = None
    policy_evaluation: Optional[Dict[str, Any]] = None

    @field_validator("canonical_url")
    @classmethod
    def validate_canonical_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Candidate canonical_url must be an absolute HTTP(S) URL.")
        return value

    @field_validator("original_urls")
    @classmethod
    def validate_original_urls(cls, values: List[str]) -> List[str]:
        from urllib.parse import urlsplit

        unique: List[str] = []
        for value in values:
            parsed = urlsplit(value)
            if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Candidate original URLs must be absolute HTTP(S) URLs.")
            if value not in unique:
                unique.append(value)
        return unique

    @field_validator("rejection_reasons", "source_providers", mode="before")
    @classmethod
    def normalize_candidate_lists(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Candidate history fields must be lists.")
        return _normalized_unique_strings(value) or []

    @model_validator(mode="after")
    def synchronize_selection_state(self):
        self.selected = self.selection_state == "selected"
        return self

    def to_pipeline_candidate(self) -> Dict[str, Any]:
        """Serializable compatibility view for nodes not yet migrated off `url`."""
        result = dict(self.candidate_metadata)
        result.update(self.model_dump(mode="json"))
        search_queries = [
            origin.query
            for origin in self.discovery_origins
            if origin.query and origin.method in {"search", "mock"}
        ]
        result.update({
            "url": self.canonical_url,
            "search_query": search_queries[0] if search_queries else (
                "user reference" if self.user_seed else ""
            ),
            "user_supplied_reference": self.user_seed,
            "source_provider": self.source_providers[0] if self.source_providers else "",
        })
        return result


class SourceEvaluation(BaseModel):
    url: str
    selected: bool = Field(default=True, validation_alias=AliasChoices("selected", "isSelected"))
    reason: str
    priority: int = Field(ge=1, default=1)


class SourceProfile(BaseModel):
    """Request-independent characterization grounded in supplied preview evidence."""

    source_type: str = Field(default="unknown", min_length=1)
    content_characteristics: List[str] = Field(default_factory=list)
    content_depth: Literal["unknown", "shallow", "medium", "deep"] = "unknown"
    authority_signals: List[str] = Field(default_factory=list)
    authority_score: float = Field(default=0.5, ge=0.0, le=1.0)
    information_density_score: float = Field(default=0.5, ge=0.0, le=1.0)
    technical_depth_score: float = Field(default=0.5, ge=0.0, le=1.0)
    recency_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    extractability_score: float = Field(default=0.5, ge=0.0, le=1.0)

    @field_validator("source_type")
    @classmethod
    def normalize_source_type(cls, value: str) -> str:
        normalized = value.strip().casefold().replace(" ", "_").replace("-", "_")
        return normalized or "unknown"

    @field_validator("content_characteristics", "authority_signals", mode="before")
    @classmethod
    def normalize_profile_lists(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("Source profile labels must be lists.")
        normalized = _normalized_unique_strings(value) or []
        labels: List[str] = []
        seen: set[str] = set()
        for item in normalized:
            label = item.casefold().replace(" ", "_").replace("-", "_")
            if label and label not in seen:
                seen.add(label)
                labels.append(label)
        return labels


class EvaluatedSource(BaseModel):
    """Reusable profile plus request-specific policy evaluation."""

    url: str
    source_profile: SourceProfile
    topic_relevance_score: float = Field(ge=0.0, le=1.0)
    policy_alignment_score: float = Field(default=0.0, ge=0.0, le=1.0)
    final_score: float = Field(default=0.0, ge=0.0, le=1.0)
    hard_policy_rejected: bool = False
    decision: Literal["select", "reject"] = "reject"
    reasons: List[str] = Field(default_factory=list)
    preview_success: bool = True
    duplicate_of: Optional[str] = None

    @field_validator("reasons", mode="before")
    @classmethod
    def normalize_reasons(cls, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            raise ValueError("Evaluation reasons must be a list or string.")
        return _normalized_unique_strings(value) or []


class SelectedSource(BaseModel):
    url: str
    rank: int = Field(ge=1)
    selection_score: float = Field(ge=0.0, le=1.0)
    final_score: float = Field(ge=0.0, le=1.0)
    domain: str
    source_type: str
    selection_reasons: List[str] = Field(default_factory=list)


class SourceEvaluationResult(BaseModel):
    evaluated_sources: List[EvaluatedSource] = Field(
        default_factory=list,
        validation_alias=AliasChoices("evaluated_sources", "evaluatedSources", "sources"),
    )
    selected_sources: List[SourceEvaluation] = Field(default_factory=list, validation_alias=AliasChoices("selected_sources", "selectedSources"))
    rejected_sources: List[SourceEvaluation] = Field(default_factory=list, validation_alias=AliasChoices("rejected_sources", "rejectedSources"))


class DatasetSchemaField(BaseModel):
    """One user-reviewable field in the dynamic dataset schema."""

    field_name: str = Field(
        validation_alias=AliasChoices("field_name", "fieldName", "name"),
        serialization_alias="field_name",
        min_length=1,
    )
    type: str
    required: bool = True
    nullable: bool = False
    is_array: bool = False
    description: str = Field(min_length=1)
    extraction_instruction: str = Field(min_length=1)

    @field_validator("type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        normalized = value.strip().lower()
        supported = {"string", "integer", "number", "boolean", "array", "object"}
        array_types = {"string", "integer", "number", "boolean", "object"}
        if normalized in supported:
            return normalized
        if normalized.startswith("array[") and normalized.endswith("]"):
            item_type = normalized[6:-1]
            if item_type in array_types:
                return normalized
        raise ValueError(f"Unsupported schema type: {value}")

    @model_validator(mode="after")
    def synchronize_array_flag(self):
        if self.type == "array" or self.type.startswith("array["):
            self.is_array = True
        return self


class DraftDatasetSchema(BaseModel):
    name: str = Field(validation_alias=AliasChoices("name", "dataset_name", "datasetName", "schema_name", "schemaName"))
    description: str = Field(validation_alias=AliasChoices("description", "schema_description", "schemaDescription"))
    fields: List[DatasetSchemaField] = Field(min_length=1)
    identity_fields: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("identity_fields", "identityFields"),
    )

    @model_validator(mode="after")
    def keep_normal_provenance_outside_domain_fields(self):
        reserved = {
            "source_url",
            "source_urls",
            "source_title",
            "source_domain",
            "source_provider",
            "search_query",
            "retrieved_at",
            "processed_at",
            "schema_version",
            "confidence_score",
            "contributing_chunk_ids",
            "provenance",
        }
        invalid = sorted({
            field.field_name.strip().casefold()
            for field in self.fields
            if field.field_name.strip().casefold() in reserved
        })
        if invalid:
            raise ValueError(
                "Normal provenance belongs in record metadata, not the domain schema: "
                + ", ".join(invalid)
            )
        field_by_name = {field.field_name: field for field in self.fields}
        normalized_identity_fields: List[str] = []
        seen_identity_fields: set[str] = set()
        for raw_name in self.identity_fields:
            name = raw_name.strip()
            if not name or name in seen_identity_fields:
                continue
            field = field_by_name.get(name)
            if field is None:
                raise ValueError(f"Identity field is not present in schema fields: {name}")
            if field.type == "boolean" or field.type == "object" or field.type.startswith("array"):
                raise ValueError(
                    f"Identity field must be a scalar string, integer, or number: {name}"
                )
            seen_identity_fields.add(name)
            normalized_identity_fields.append(name)
        self.identity_fields = normalized_identity_fields
        return self


class SchemaEvidencePreview(BaseModel):
    """Bounded selected-source evidence exposed to dataset schema design."""

    url: str
    title: str = ""
    domain: str = ""
    headings: List[str] = Field(default_factory=list)
    relevant_text: str
    approximate_word_count: Optional[int] = Field(default=None, ge=0)
    preview_word_count: int = Field(default=0, ge=0)
    language: Optional[str] = None
    publication_date: Optional[str] = None
    updated_date: Optional[str] = None
    structure_hints: List[str] = Field(default_factory=list)
    fetch_success: Literal[True] = True
    source_rank: int = Field(ge=1)
    selection_score: float = Field(default=0.0, ge=0.0, le=1.0)


class DatasetSchemaDesignerInput(BaseModel):
    """Complete request and selected evidence available at schema design time."""

    dataset_topic: str = Field(min_length=1)
    dataset_purpose: str = Field(min_length=1)
    research_plan: ResearchPlan
    source_policy: SourcePolicy
    selected_source_previews: List[SchemaEvidencePreview] = Field(min_length=1)
    user_schema_constraints: str | Dict[str, Any] | List[Any] = ""
    configured_fields: List[DatasetSchemaField] = Field(default_factory=list)


class ApprovedDatasetSchema(DraftDatasetSchema):
    schema_version: int = Field(ge=1, default=1)
    approved_at: str
    approved_by: str = "user"


class DocumentChunk(BaseModel):
    """A token-budgeted, source-traceable portion of one cleaned document."""

    chunk_id: str = Field(min_length=1)
    source_url: str = ""
    source_title: str = ""
    chunk_index: int = Field(ge=0)
    total_chunks: int = Field(ge=1)
    heading: str = ""
    content: str = Field(min_length=1)
    token_count: int = Field(ge=1)
    overlap_token_count: int = Field(ge=0, default=0)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)


class ProcessedDocument(BaseModel):
    """Silver content linked to immutable Bronze source evidence."""

    source_url: str
    title: str = ""
    raw_content: str = ""
    processed_content: str = ""
    content_hash: str
    processed_content_hash: str
    word_count: int = Field(ge=0)
    content_status: Literal["usable", "thin", "empty"]
    removed_boilerplate_lines: int = Field(default=0, ge=0)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_pipeline_document(self) -> Dict[str, Any]:
        return {
            "source": self.source_url,
            "title": self.title,
            "raw_content": self.raw_content,
            "cleaned_content": self.processed_content,
            "content_status": self.content_status,
            "metadata": {
                **self.source_metadata,
                "content_hash": self.content_hash,
                "processed_content_hash": self.processed_content_hash,
                "word_count": self.word_count,
                "removed_boilerplate_lines": self.removed_boilerplate_lines,
            },
        }


class DeterministicExtractionRule(BaseModel):
    """An explicit, provider-neutral instruction for zero-LLM extraction."""

    model_config = ConfigDict(populate_by_name=True)

    rule_id: str = Field(
        min_length=1,
        validation_alias=AliasChoices("rule_id", "id"),
        serialization_alias="rule_id",
    )
    method: Literal["css", "xpath", "regex"]
    url_pattern: str = ".*"
    schema_config: Dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("schema", "schema_config"),
        serialization_alias="schema",
    )
    patterns: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_method_configuration(self):
        import re

        try:
            re.compile(self.url_pattern)
        except re.error as error:
            raise ValueError(f"Invalid deterministic rule url_pattern: {error}") from error
        if self.method in {"css", "xpath"}:
            if not self.schema_config.get("baseSelector"):
                raise ValueError(f"{self.method} rules require schema.baseSelector.")
            if not isinstance(self.schema_config.get("fields"), list):
                raise ValueError(f"{self.method} rules require schema.fields.")
        elif not self.patterns:
            raise ValueError("regex rules require at least one field pattern.")
        return self


class ExtractionRoute(BaseModel):
    """Observable source-level decision made before semantic extraction."""

    source_url: str
    chunk_ids: List[str] = Field(default_factory=list)
    method: Literal["css", "xpath", "regex", "table", "semantic"]
    reason: str
    rule_id: Optional[str] = None
    fallback_from: Optional[Literal["css", "xpath", "regex", "table"]] = None
    result_count: int = Field(default=0, ge=0)
    model_call_required: bool


class ExtractionResult(BaseModel):
    source_url: str = Field(default="", validation_alias=AliasChoices("source_url", "sourceUrl"))
    data: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: Dict[str, float] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("field_confidence", "fieldConfidence", "field_confidences", "fieldConfidences"),
    )
    source_chunk_id: str = Field(default="", validation_alias=AliasChoices("source_chunk_id", "sourceChunkId"))
    chunk_index: int = Field(default=0, ge=0, validation_alias=AliasChoices("chunk_index", "chunkIndex"))
    total_chunks: int = Field(default=1, ge=1, validation_alias=AliasChoices("total_chunks", "totalChunks"))
    extraction_method: Literal["css", "xpath", "regex", "table", "semantic"] = Field(
        default="semantic",
        validation_alias=AliasChoices("extraction_method", "extractionMethod"),
    )

    @model_validator(mode="before")
    @classmethod
    def derive_missing_overall_confidence(cls, value: Any) -> Any:
        """Derive missing confidence from populated fields' model-provided evidence."""
        if not isinstance(value, dict) or "confidence" in value:
            return value
        data = value.get("data")
        if not isinstance(data, dict):
            return value
        field_confidence = (
            value.get("field_confidence")
            or value.get("fieldConfidence")
            or value.get("field_confidences")
            or value.get("fieldConfidences")
        )
        if not isinstance(field_confidence, dict) or not field_confidence:
            return value
        try:
            scores = [
                float(score)
                for field_name, score in field_confidence.items()
                if field_name in data and data[field_name] not in (None, "", [], {})
            ]
        except (TypeError, ValueError):
            return value
        if scores and all(0.0 <= score <= 1.0 for score in scores):
            normalized = dict(value)
            normalized["confidence"] = fmean(scores)
            return normalized
        return value


class EvidenceRef(BaseModel):
    """A serializable pointer to source text supporting one extracted field."""

    source_url: str
    chunk_id: str
    evidence_text: str = Field(min_length=1)


class ExtractedRecord(ExtractionResult):
    """One record inside a zero/one/many extraction batch."""

    local_record_id: str = ""
    segment_id: str = ""
    chunk_id: str = ""
    field_evidence: Dict[str, List[EvidenceRef]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def synchronize_chunk_identifiers(self):
        if not self.chunk_id:
            self.chunk_id = self.source_chunk_id
        if not self.source_chunk_id:
            self.source_chunk_id = self.chunk_id
        return self


class EvidenceSupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    CONTRADICTED = "CONTRADICTED"


class FieldEvidenceValidation(BaseModel):
    """Deterministic support result for one populated dynamic-schema field."""

    field_name: str
    status: EvidenceSupportStatus
    evidence: List[EvidenceRef] = Field(default_factory=list)
    reasons: List[str] = Field(default_factory=list)
    semantic_review_required: bool = False


class VerifiedRecord(BaseModel):
    """An extraction candidate after deterministic evidence validation."""

    record: ExtractedRecord
    status: EvidenceSupportStatus
    field_validations: Dict[str, FieldEvidenceValidation] = Field(default_factory=dict)
    schema_valid: bool
    source_exists: bool
    chunk_exists: bool
    required_field_completeness: float = Field(ge=0.0, le=1.0)
    evidence_support_rate: float = Field(ge=0.0, le=1.0)
    provenance_completeness: float = Field(ge=0.0, le=1.0)
    duplicate_status: Literal["unique", "duplicate", "not_evaluated"] = "not_evaluated"
    validation_errors: List[str] = Field(default_factory=list)


class RecordQualityAssessment(BaseModel):
    """Measurable Phase-18 quality gate decision; extractor confidence is excluded."""

    local_record_id: str
    source_url: str
    support_status: EvidenceSupportStatus
    components: Dict[str, float]
    final_quality_score: float = Field(ge=0.0, le=1.0)
    accepted: bool
    reasons: List[str] = Field(default_factory=list)


class RecordContributor(BaseModel):
    """Globally scoped provenance for one candidate contributing to a resolution."""

    source_url: str
    local_record_id: str
    chunk_id: str = ""
    extraction_method: Literal["css", "xpath", "regex", "table", "semantic"]


class StructuredOutputRecord(BaseModel):
    """Topic-specific record with explicit evidence, provenance, quality, and schema."""

    data: Dict[str, Any]
    evidence: Dict[str, List[EvidenceRef]] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)
    schema_metadata: Dict[str, Any] = Field(
        default_factory=dict, serialization_alias="schema"
    )
    legacy_metadata: Dict[str, Any] = Field(
        default_factory=dict, serialization_alias="_metadata"
    )


class RAGOutputRecord(BaseModel):
    """Retrieval-oriented text plus the minimum evidence/provenance payload."""

    text: str = Field(min_length=1)
    title: str = ""
    source_url: str = ""
    source_urls: List[str] = Field(default_factory=list)
    section_path: str = ""
    chunk_id: str = ""
    language: str = ""
    content_hash: str = ""
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: Dict[str, List[EvidenceRef]] = Field(default_factory=dict)
    record_data: Dict[str, Any] = Field(default_factory=dict)
    schema_name: str = ""
    schema_version: str = ""


class GraphRAGEntity(BaseModel):
    name: str
    entity_type: str = "record_identity"
    field_name: str
    evidence: List[EvidenceRef] = Field(min_length=1)


class GraphRAGClaim(BaseModel):
    claim_id: str
    predicate: str
    value: Any
    evidence: List[EvidenceRef] = Field(min_length=1)


class EvidenceBackedRelation(BaseModel):
    subject: str
    predicate: str
    object: str
    evidence: List[EvidenceRef] = Field(min_length=1)


class GraphRAGOutputRecord(BaseModel):
    """Evidence-only preparation payload; co-occurrence relations are excluded."""

    record_key: str
    entities: List[GraphRAGEntity] = Field(default_factory=list)
    claims: List[GraphRAGClaim] = Field(default_factory=list)
    relations: List[EvidenceBackedRelation] = Field(default_factory=list)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)
    schema_name: str = ""
    schema_version: str = ""


class ExtractionBatch(BaseModel):
    """Canonical semantic/deterministic extraction envelope; records are never capped."""

    model_config = ConfigDict(extra="ignore")

    source_url: str = ""
    segment_id: str = ""
    chunk_id: str = ""
    records: List[ExtractedRecord] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def isolate_invalid_records_and_adapt_legacy_single_result(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        if "records" not in normalized and "data" in normalized:
            normalized["records"] = [{
                key: normalized[key]
                for key in (
                    "data", "confidence", "field_confidence", "fieldConfidence",
                    "field_confidences", "fieldConfidences", "field_evidence",
                    "extraction_method", "extractionMethod",
                )
                if key in normalized
            }]
        raw_records = normalized.get("records", [])
        if not isinstance(raw_records, list):
            raise ValueError("ExtractionBatch.records must be a list.")
        warnings = list(normalized.get("warnings") or [])
        valid_records: List[ExtractedRecord] = []
        for index, raw_record in enumerate(raw_records):
            try:
                valid_records.append(ExtractedRecord.model_validate(raw_record))
            except Exception as error:
                warnings.append(f"Record {index} was rejected at the extraction boundary: {error}")
        normalized["records"] = valid_records
        normalized["warnings"] = warnings
        return normalized

    @model_validator(mode="after")
    def complete_record_identifiers(self):
        seen: set[str] = set()
        for index, record in enumerate(self.records, start=1):
            record.source_url = record.source_url or self.source_url
            record.segment_id = record.segment_id or self.segment_id
            record.chunk_id = record.chunk_id or self.chunk_id
            record.source_chunk_id = record.source_chunk_id or record.chunk_id
            record.local_record_id = record.local_record_id or (
                f"{record.chunk_id or self.chunk_id or 'segment'}:record:{index:04d}"
            )
            if record.local_record_id in seen:
                raise ValueError(
                    f"ExtractionBatch local_record_id must be unique: {record.local_record_id}"
                )
            seen.add(record.local_record_id)
        return self


class MergedRecord(BaseModel):
    """A conservative merge of extraction results that identify the same record."""

    data: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: Dict[str, float] = Field(default_factory=dict)
    source_url: str = ""
    source_urls: List[str] = Field(default_factory=list)
    source_title: str = ""
    source_titles: Dict[str, str] = Field(default_factory=dict)
    source_content_hashes: Dict[str, str] = Field(default_factory=dict)
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    contributing_chunk_ids: List[str] = Field(default_factory=list)
    contributing_record_ids: List[str] = Field(default_factory=list)
    contributors: List[RecordContributor] = Field(default_factory=list)
    field_evidence: Dict[str, List[EvidenceRef]] = Field(default_factory=dict)
    evidence_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_support_statuses: List[EvidenceSupportStatus] = Field(default_factory=list)
    quality_assessments: List[RecordQualityAssessment] = Field(default_factory=list)
    resolution_method: Literal[
        "explicit_identity", "normalized_identity", "composite_identity", "local_record"
    ] = "local_record"
    resolution_key: str = ""
    extraction_methods: List[Literal["css", "xpath", "regex", "table", "semantic"]] = Field(
        default_factory=list
    )
    merge_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
