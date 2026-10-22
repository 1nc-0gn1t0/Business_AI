from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

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
