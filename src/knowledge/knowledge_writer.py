"""Write dataset records into deterministic entity/fact knowledge objects."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.knowledge.entity_resolution import entity_identity
from src.storage.models.knowledge import DatasetRecordEntity, Entity, Fact, FactEvidence, Relation
from src.storage.models.entities import Document, Source


def _hash_value(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def write_knowledge_records(
    session: Session,
    records: list[dict[str, Any]],
    schema: dict[str, Any],
    source_by_url: dict[str, Source],
    document_by_url: dict[str, Document],
    dataset_record_by_local_id: dict[str, Any],
) -> dict[str, int]:
    entities_created = facts_created = relations_created = evidence_created = conflicts = links_created = 0
    entity_by_identity: dict[tuple[str, str], Entity] = {}
    for raw in records:
        entity_type, canonical_name, normalized_name = entity_identity(raw, schema)
        cache_key = (entity_type, normalized_name)
        entity = entity_by_identity.get(cache_key) or session.scalar(select(Entity).where(Entity.entity_type == entity_type, Entity.normalized_name == normalized_name))
        if entity is None:
            entity = Entity(entity_type=entity_type, canonical_name=canonical_name, normalized_name=normalized_name, attributes_json={})
            session.add(entity)
            session.flush()
            entities_created += 1
        entity_by_identity[cache_key] = entity
        local_id = str(raw.get("local_record_id") or hashlib.sha256(json.dumps(raw.get("data", {}), sort_keys=True, default=str).encode()).hexdigest())
        dataset_record = dataset_record_by_local_id.get(local_id)
        if dataset_record is not None:
            link = session.get(DatasetRecordEntity, {"dataset_record_id": dataset_record.id, "entity_id": entity.id})
            if link is None:
                session.add(DatasetRecordEntity(dataset_record_id=dataset_record.id, entity_id=entity.id))
                links_created += 1
        metadata = dict(raw.get("_metadata", {}))
        field_evidence = metadata.get("field_evidence", {})
        for predicate, value in dict(raw.get("data", {})).items():
            if value in (None, "", [], {}):
                continue
            value_hash = _hash_value(value)
            same = session.scalar(select(Fact).where(Fact.entity_id == entity.id, Fact.predicate == str(predicate), Fact.value_hash == value_hash))
            if same is None:
                existing_values = session.scalars(select(Fact).where(Fact.entity_id == entity.id, Fact.predicate == str(predicate))).all()
                status = "conflict" if existing_values else "asserted"
                if status == "conflict":
                    conflicts += 1
                fact = Fact(entity_id=entity.id, predicate=str(predicate), value_json=value, value_hash=value_hash, confidence=raw.get("confidence"), status=status)
                session.add(fact)
                session.flush()
                facts_created += 1
            else:
                fact = same
            for ref in field_evidence.get(predicate, []) if isinstance(field_evidence.get(predicate, []), list) else []:
                source = source_by_url.get(str(ref.get("source_url", "")))
                if source is None or not ref.get("evidence_text"):
                    continue
                document = document_by_url.get(str(ref.get("source_url", "")))
                duplicate = session.scalar(select(FactEvidence).where(FactEvidence.fact_id == fact.id, FactEvidence.chunk_id == str(ref.get("chunk_id", "")), FactEvidence.evidence_text == str(ref["evidence_text"])))
                if duplicate is None:
                    session.add(FactEvidence(fact_id=fact.id, source_id=source.id, document_id=document.id if document else None, chunk_id=str(ref.get("chunk_id", "")), evidence_text=str(ref["evidence_text"])))
                    evidence_created += 1
        for relation in metadata.get("evidence_backed_relations", []) if isinstance(metadata.get("evidence_backed_relations", []), list) else []:
            # Relations without explicit evidence are deliberately ignored.
            target_name = str(relation.get("object", relation.get("target_entity", ""))).strip()
            relation_type = str(relation.get("predicate", relation.get("relation_type", ""))).strip()
            if not target_name or not relation_type or not relation.get("evidence"):
                continue
            target_normalized = target_name.casefold()
            target = session.scalar(select(Entity).where(Entity.entity_type == entity_type, Entity.normalized_name == target_normalized))
            if target is None:
                target = Entity(entity_type=entity_type, canonical_name=target_name, normalized_name=target_normalized, attributes_json={})
                session.add(target)
                session.flush()
                entities_created += 1
            existing_relation = session.scalar(select(Relation).where(Relation.source_entity_id == entity.id, Relation.relation_type == relation_type, Relation.target_entity_id == target.id))
            if existing_relation is None:
                session.add(Relation(source_entity_id=entity.id, relation_type=relation_type, target_entity_id=target.id, attributes_json={"evidence": relation["evidence"]}, confidence=relation.get("confidence")))
                relations_created += 1
    return {"entities_created": entities_created, "facts_created": facts_created, "relations_created": relations_created, "knowledge_evidence_created": evidence_created, "identity_conflicts": conflicts, "record_entity_links_created": links_created}
