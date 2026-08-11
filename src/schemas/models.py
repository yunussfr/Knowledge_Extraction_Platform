"""Pydantic models shared by the dataset-generation pipeline."""

from statistics import fmean
from typing import Any, Dict, List, Literal, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


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


class CandidateSource(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    domain: str = ""
    search_query: str = Field(default="", validation_alias=AliasChoices("search_query", "searchQuery"))


class SourceEvaluation(BaseModel):
    url: str
    selected: bool = Field(default=True, validation_alias=AliasChoices("selected", "isSelected"))
    reason: str
    priority: int = Field(ge=1, default=1)


class SourceEvaluationResult(BaseModel):
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


class MergedRecord(BaseModel):
    """A conservative merge of extraction results that identify the same record."""

    data: Dict[str, Any]
    confidence: float = Field(ge=0.0, le=1.0)
    field_confidence: Dict[str, float] = Field(default_factory=dict)
    source_url: str = ""
    source_title: str = ""
    source_metadata: Dict[str, Any] = Field(default_factory=dict)
    contributing_chunk_ids: List[str] = Field(default_factory=list)
    merge_conflicts: List[Dict[str, Any]] = Field(default_factory=list)
