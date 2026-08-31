"""create persistent pipeline storage tables"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_persistent_storage"
down_revision = None
branch_labels = None
depends_on = None

JSON_PAYLOAD = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table("datasets", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("name", sa.String(255), nullable=False), sa.Column("topic", sa.Text(), nullable=False), sa.Column("purpose", sa.Text(), nullable=False), sa.Column("schema_json", JSON_PAYLOAD, nullable=False), sa.Column("schema_version", sa.Integer()), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("name"))
    op.create_index("ix_datasets_name", "datasets", ["name"], unique=False)
    op.create_table("research_runs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False), sa.Column("run_key", sa.String(255), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("request_json", JSON_PAYLOAD, nullable=False), sa.Column("metrics_json", JSON_PAYLOAD, nullable=False), sa.UniqueConstraint("run_key"))
    op.create_index("ix_research_runs_dataset_id", "research_runs", ["dataset_id"], unique=False)
    op.create_index("ix_research_runs_run_key", "research_runs", ["run_key"], unique=False)
    op.create_table("sources", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("canonical_url", sa.Text(), nullable=False), sa.Column("domain", sa.String(255), nullable=False), sa.Column("title", sa.Text(), nullable=False), sa.Column("source_type", sa.String(128), nullable=False), sa.Column("content_hash", sa.String(128), nullable=False), sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("canonical_url"))
    op.create_index("ix_sources_canonical_url", "sources", ["canonical_url"], unique=False)
    op.create_table("documents", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False), sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id"), nullable=False), sa.Column("raw_markdown", sa.Text(), nullable=False), sa.Column("processed_markdown", sa.Text(), nullable=False), sa.Column("raw_html", sa.Text()), sa.Column("language", sa.String(32), nullable=False), sa.Column("word_count", sa.Integer(), nullable=False), sa.Column("content_hash", sa.String(128), nullable=False), sa.Column("retrieved_at", sa.String(64), nullable=False))
    op.create_index("ix_documents_source_id", "documents", ["source_id"], unique=False)
    op.create_index("ix_documents_run_id", "documents", ["run_id"], unique=False)
    op.create_table("document_chunks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False), sa.Column("chunk_index", sa.Integer(), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("token_count", sa.Integer(), nullable=False), sa.Column("heading", sa.Text(), nullable=False), sa.Column("content_hash", sa.String(128), nullable=False), sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"))
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)
    op.create_table("dataset_records", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("dataset_id", sa.Integer(), sa.ForeignKey("datasets.id"), nullable=False), sa.Column("run_id", sa.Integer(), sa.ForeignKey("research_runs.id"), nullable=False), sa.Column("local_record_id", sa.String(255), nullable=False), sa.Column("identity_key", sa.String(255), nullable=False), sa.Column("data_json", JSON_PAYLOAD, nullable=False), sa.Column("completeness_score", sa.Float(), nullable=False), sa.Column("quality_score", sa.Float(), nullable=False), sa.Column("status", sa.String(64), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_dataset_records_dataset_id", "dataset_records", ["dataset_id"], unique=False)
    op.create_index("ix_dataset_records_run_id", "dataset_records", ["run_id"], unique=False)
    op.create_index("ix_dataset_records_local_record_id", "dataset_records", ["local_record_id"], unique=False)
    op.create_index("ix_dataset_records_identity_key", "dataset_records", ["identity_key"], unique=False)
    op.create_table("field_evidence", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("record_id", sa.Integer(), sa.ForeignKey("dataset_records.id"), nullable=False), sa.Column("field_name", sa.String(255), nullable=False), sa.Column("source_id", sa.Integer(), sa.ForeignKey("sources.id"), nullable=False), sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id")), sa.Column("chunk_id", sa.String(255), nullable=False), sa.Column("evidence_text", sa.Text(), nullable=False), sa.Column("confidence", sa.Float()))
    op.create_index("ix_field_evidence_record_id", "field_evidence", ["record_id"], unique=False)
    op.create_index("ix_field_evidence_source_id", "field_evidence", ["source_id"], unique=False)
    op.create_index("ix_field_evidence_document_id", "field_evidence", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_table("field_evidence")
    op.drop_table("dataset_records")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("sources")
    op.drop_table("research_runs")
    op.drop_table("datasets")
