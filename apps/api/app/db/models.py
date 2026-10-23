from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.spatial import Geometry
from app.domain.enums import (
    Confidence,
    ConfirmationState,
    ConversationState,
    DataOrigin,
    Funding,
    MessageRole,
)


def enum_values(enum: type[Enum]) -> list[str]:
    return [str(member.value) for member in enum]


class Base(DeclarativeBase):
    pass


class GeoDatasetRecord(Base):
    __tablename__ = "geo_datasets"
    __table_args__ = (
        sa.UniqueConstraint("slug", "data_version"),
        sa.Index("ix_geo_active_slug", "slug", unique=True, postgresql_where=sa.text("active")),
        sa.CheckConstraint("data_version ~ '^[0-9a-f]{64}$'", name="ck_geo_version"),
        sa.CheckConstraint("osm_base <= fetched_at", name="ck_geo_dates"),
        sa.CheckConstraint("poi_count >= 0 AND district_count >= 0", name="ck_geo_counts"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(sa.Text)
    city: Mapped[str] = mapped_column(sa.Text)
    bbox: Mapped[dict[str, float]] = mapped_column(JSONB)
    source_url: Mapped[str] = mapped_column(sa.Text)
    query: Mapped[str] = mapped_column(sa.Text)
    data_version: Mapped[str] = mapped_column(sa.String(64))
    osm_base: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(server_default=sa.false())
    poi_count: Mapped[int] = mapped_column(server_default="0")
    district_count: Mapped[int] = mapped_column(server_default="0")
    diagnostics: Mapped[dict[str, int]] = mapped_column(JSONB)


class GeoPOIRecord(Base):
    __tablename__ = "geo_pois"
    __table_args__ = (
        sa.CheckConstraint("osm_type IN ('node', 'way', 'relation')", name="ck_poi_osm_type"),
        sa.CheckConstraint("osm_id > 0 AND osm_version > 0", name="ck_poi_identity"),
        sa.CheckConstraint("cardinality(categories) > 0", name="ck_poi_categories"),
        sa.Index("ix_geo_poi_geom", "geom", postgresql_using="gist"),
        sa.Index("ix_geo_poi_geography", sa.text("(geom::geography)"), postgresql_using="gist"),
        sa.Index("ix_geo_poi_categories", "categories", postgresql_using="gin"),
    )

    dataset_id: Mapped[UUID] = mapped_column(sa.ForeignKey("geo_datasets.id"), primary_key=True)
    osm_type: Mapped[str] = mapped_column(sa.Text, primary_key=True)
    osm_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    osm_version: Mapped[int]
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    name: Mapped[str | None] = mapped_column(sa.Text)
    categories: Mapped[list[str]] = mapped_column(ARRAY(sa.Text))
    tags: Mapped[dict[str, str]] = mapped_column(JSONB)
    representation: Mapped[str] = mapped_column(sa.Text)
    geom: Mapped[str] = mapped_column(Geometry())


class GeoDistrictRecord(Base):
    __tablename__ = "geo_districts"
    __table_args__ = (
        sa.CheckConstraint("osm_id > 0 AND osm_version > 0", name="ck_district_identity"),
        sa.CheckConstraint("ST_IsValid(geom) AND NOT ST_IsEmpty(geom)", name="ck_district_geom"),
        sa.Index("ix_geo_district_geom", "geom", postgresql_using="gist"),
    )

    dataset_id: Mapped[UUID] = mapped_column(sa.ForeignKey("geo_datasets.id"), primary_key=True)
    osm_id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True)
    osm_version: Mapped[int]
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    name: Mapped[str | None] = mapped_column(sa.Text)
    admin_level: Mapped[int]
    geom: Mapped[str] = mapped_column(Geometry("MULTIPOLYGON"))


class ConversationRecord(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        sa.CheckConstraint("version >= 0", name="ck_conversation_version"),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_conversation_token_hash"),
        sa.CheckConstraint(
            "extraction_mode IN ('rules', 'stub', 'ollama')", name="ck_conversation_mode"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(sa.String(64))
    state: Mapped[ConversationState] = mapped_column(
        sa.Enum(ConversationState, name="conversation_state", values_callable=enum_values)
    )
    version: Mapped[int] = mapped_column(server_default="0")
    extraction_mode: Mapped[Literal["rules", "stub", "ollama"]] = mapped_column(
        sa.Text, server_default="rules"
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class MessageRecord(Base):
    __tablename__ = "messages"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "version", "role"),
        sa.CheckConstraint("version >= 0", name="ck_message_version"),
        sa.CheckConstraint("length(btrim(content)) BETWEEN 1 AND 4000", name="ck_message_content"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("conversations.id", ondelete="CASCADE")
    )
    version: Mapped[int]
    role: Mapped[MessageRole] = mapped_column(
        sa.Enum(MessageRole, name="message_role", values_callable=enum_values)
    )
    content: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class ProfileRevisionRecord(Base):
    __tablename__ = "profile_revisions"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "version"),
        sa.CheckConstraint("version >= 0", name="ck_revision_version"),
        sa.CheckConstraint(
            "jsonb_typeof(profile_snapshot) = 'object'", name="ck_revision_snapshot"
        ),
        sa.CheckConstraint(
            "source IN ('created', 'message', 'patch', 'confirmation', 'legacy_import')",
            name="ck_revision_source",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("conversations.id", ondelete="CASCADE")
    )
    version: Mapped[int]
    source: Mapped[str] = mapped_column(sa.Text)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class BusinessProfileRecord(Base):
    __tablename__ = "business_profiles"
    __table_args__ = (
        sa.CheckConstraint("budget >= 0 AND budget <> 'NaN'::numeric", name="ck_profile_budget"),
        sa.CheckConstraint("city IS NULL OR length(btrim(city)) > 0", name="ck_profile_city"),
        sa.CheckConstraint(
            "category IS NULL OR length(btrim(category)) > 0", name="ck_profile_category"
        ),
        sa.CheckConstraint("jsonb_typeof(preferences) = 'object'", name="ck_profile_preferences"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("conversations.id", ondelete="CASCADE", name="fk_profile_conversation"),
        unique=True,
    )
    city: Mapped[str | None] = mapped_column(sa.Text)
    category: Mapped[str | None] = mapped_column(sa.Text)
    budget: Mapped[Decimal | None] = mapped_column(sa.Numeric(18, 2))
    funding: Mapped[Funding | None] = mapped_column(
        sa.Enum(Funding, name="funding", values_callable=enum_values, validate_strings=True)
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB)
    confirmation_state: Mapped[ConfirmationState] = mapped_column(
        sa.Enum(ConfirmationState, name="confirmation_state", values_callable=enum_values),
        server_default="draft",
    )


class ConsentRecord(Base):
    __tablename__ = "consents"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "purpose", "revision"),
        sa.CheckConstraint("revision > 0", name="ck_consent_revision"),
        sa.CheckConstraint(
            "purpose IN ('assistant', 'marketing', 'demo_lead')", name="ck_consent_purpose"
        ),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_consent_document"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(sa.ForeignKey("conversations.id"), index=True)
    purpose: Mapped[str] = mapped_column(sa.Text)
    revision: Mapped[int]
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)


class LeadDraftRecord(Base):
    __tablename__ = "lead_drafts"
    __table_args__ = (
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_draft_document"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(sa.ForeignKey("conversations.id"), index=True)
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)


class LeadSubmissionRecord(Base):
    __tablename__ = "lead_submissions"
    __table_args__ = (
        sa.UniqueConstraint("conversation_id", "idempotency_key"),
        sa.CheckConstraint("jsonb_typeof(document) = 'object'", name="ck_submission_document"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(sa.ForeignKey("conversations.id"), index=True)
    draft_id: Mapped[UUID] = mapped_column(sa.ForeignKey("lead_drafts.id"), unique=True)
    idempotency_key: Mapped[UUID]
    request_fingerprint: Mapped[str] = mapped_column(sa.String(64))
    document: Mapped[dict[str, Any]] = mapped_column(JSONB)


class AuditEventRecord(Base):
    __tablename__ = "audit_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(sa.ForeignKey("conversations.id"), index=True)
    action: Mapped[str] = mapped_column(sa.Text)
    object_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class AnalysisRunRecord(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (
        sa.CheckConstraint("jsonb_typeof(profile_snapshot) = 'object'", name="ck_run_snapshot"),
        sa.CheckConstraint(
            "jsonb_typeof(dataset_versions) = 'object' AND dataset_versions <> '{}'::jsonb",
            name="ck_run_datasets",
        ),
        sa.CheckConstraint("length(btrim(algorithm_version)) > 0", name="ck_run_algorithm"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    profile_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    dataset_versions: Mapped[dict[str, str]] = mapped_column(JSONB)
    algorithm_version: Mapped[str] = mapped_column(sa.Text)
    tool_trace_id: Mapped[UUID]
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))


class LocationMetricRecord(Base):
    __tablename__ = "location_metrics"
    __table_args__ = (
        sa.CheckConstraint("length(btrim(metric)) > 0", name="ck_metric_name"),
        sa.CheckConstraint("length(btrim(unit)) > 0", name="ck_metric_unit"),
        sa.CheckConstraint("length(btrim(source_name)) > 0", name="ck_metric_source"),
        sa.CheckConstraint("length(btrim(data_version)) > 0", name="ck_metric_version"),
        sa.CheckConstraint(
            "value > '-Infinity'::double precision AND value < 'Infinity'::double precision",
            name="ck_metric_finite",
        ),
        sa.CheckConstraint(
            "observed_at IS NULL OR observed_at <= generated_at", name="ck_metric_dates"
        ),
        sa.CheckConstraint("jsonb_typeof(limitations) = 'array'", name="ck_metric_limitations"),
        sa.CheckConstraint(
            "origin <> 'synthetic' OR "
            "(confidence = 'not_applicable' AND jsonb_array_length(limitations) > 0)",
            name="ck_metric_synthetic",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    analysis_run_id: Mapped[UUID] = mapped_column(
        sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[UUID]
    metric: Mapped[str] = mapped_column(sa.Text)
    value: Mapped[float] = mapped_column(sa.Double)
    unit: Mapped[str] = mapped_column(sa.Text)
    origin: Mapped[DataOrigin] = mapped_column(
        sa.Enum(DataOrigin, name="data_origin", values_callable=enum_values, validate_strings=True)
    )
    source_name: Mapped[str] = mapped_column(sa.Text)
    observed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    data_version: Mapped[str] = mapped_column(sa.Text)
    confidence: Mapped[Confidence] = mapped_column(
        sa.Enum(Confidence, name="confidence", values_callable=enum_values, validate_strings=True)
    )
    limitations: Mapped[list[str]] = mapped_column(JSONB)
