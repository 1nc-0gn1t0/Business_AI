"""Bounded owner-scoped inputs, command receipts and append-only result snapshots."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.db.models import FinancialActionRecord as Action
from app.db.models import FinancialResultRecord as Result
from app.db.models import FinancialWorkspaceRecord as Workspace
from app.finance.engine import canonical
from app.finance.v2.engine import missing, requirements
from app.finance.v2.registry import configuration, reject, validate
from app.finance.v2.schemas import (
    AssumptionProposal,
    FinancialCalculation,
    FinancialCommand,
    FinancialDocument,
    FinancialInput,
    FinancialSnapshot,
    FinancialView,
    InputPatch,
    ParameterUpdate,
    ReviewCommand,
)
from app.industry.schemas import UniversalProfile
from app.industry.service import IndustryProfiles
from app.leads.consents import require_consent


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            canonical(value), ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")
        ).encode()
    ).hexdigest()


def make_input(update: ParameterUpdate, revision: int, *, qwen: bool = False) -> FinancialInput:
    assumed = qwen or update.kind == "user_assumption"
    return FinancialInput.model_validate(
        dict(
            **update.model_dump(include={"base", "low", "high", "unit", "basis"}),
            source=dict(
                origin="synthetic" if assumed else "user_input",
                source_name="Qwen: исследовательская гипотеза" if qwen else "Вводная пользователя",
                data_version=f"financial-input-{revision}",
                confidence="not_applicable" if assumed else "low",
                limitations=["Не подтверждённая рыночная статистика. Требуется явный review."],
                evidence_ref=f"financial-input:{revision}:{update.parameter}",
            ),
            epistemic="assumed" if assumed else "user_provided",
            review="proposed",
            method="qwen_exploratory" if qwen else update.kind,
            revision=revision,
            created_at=datetime.now(UTC),
        )
    )


def new_document(profile: UniversalProfile) -> FinancialDocument:
    config = configuration(profile.industry)
    # Only exact semantic/unit mappings. U-04 planned students != paying students;
    # materials RUB/month != materials/order; planned orders != maximum throughput.
    mapping = {
        "auto_repair": (
            "service_bays",
            "working_days",
            "utilization",
            "average_order",
            "rent",
            "payroll",
        ),
        "online_school": ("tuition", "teachers", "marketing"),
        "generic": (),
    }
    entries = {}
    fields = {p.id: p for p in config.parameters}
    for key in mapping[profile.industry]:
        value = profile.extensions.get(profile.industry, {}).get(key)
        if not value or value.review != "confirmed" or value.epistemic != "user_provided":
            continue
        try:
            update = ParameterUpdate.model_validate(
                dict(
                    parameter=key,
                    base=value.value,
                    low=value.value,
                    high=value.value,
                    unit=value.unit,
                    basis=value.evidence,
                )
            )
            validate(fields[key], update, update.unit)
        except (HTTPException, ValidationError):
            # Keep incompatible profile facts in ProfileV2; request a suitable
            # financial input instead of blocking the owner's entire workspace.
            continue
        entry = make_input(update, 0)
        entries[key] = entry.model_copy(
            update={
                "method": "profile_v2",
                "review": "confirmed",
                "source": entry.source.model_copy(
                    update={
                        "source_name": "Подтверждённые вводные ProfileV2",
                        "data_version": f"profile-v2-{profile.revision}",
                        "evidence_ref": f"profile:{profile.id}:{profile.revision}:"
                        f"{profile.industry}.{key}",
                    }
                ),
            }
        )
    return FinancialDocument.model_validate(
        dict(
            profile_revision=profile.revision,
            profile_config_sha256=profile.config_sha256,
            model=config.id,
            adapter_sha256=digest(config.model_dump(mode="json")),
            entries=entries,
        )
    )


def compatible(doc: FinancialDocument, profile: UniversalProfile) -> bool:
    return (
        profile.confirmed_revision == profile.revision
        and doc.profile_revision == profile.revision
        and doc.model == profile.industry
        and doc.profile_config_sha256 == profile.config_sha256
        and doc.adapter_version == configuration(doc.model).version
        and doc.adapter_sha256 == digest(configuration(doc.model).model_dump(mode="json"))
    )


def patch_document(
    doc: FinancialDocument, updates: tuple[ParameterUpdate, ...]
) -> FinancialDocument:
    fields = {p.id: p for p in configuration(doc.model).parameters}
    if len({u.parameter for u in updates}) != len(updates):
        reject("duplicate_financial_parameter")
    entries = dict(doc.entries)
    for update in updates:
        if update.parameter not in fields:
            reject("financial_parameter_unsupported")
        definition = fields[update.parameter]
        validate(definition, update, update.unit)
        if definition.direction == "context" and not update.low == update.base == update.high:
            reject("financial_context_range_unsupported")
        entries[update.parameter] = make_input(update, doc.revision + 1)
    return doc.model_copy(update={"revision": doc.revision + 1, "entries": entries})


class FinancialService:
    def __init__(self, session: Session):
        self.session = session
        self.profiles = IndustryProfiles(session)

    def load(
        self, owner: UUID, token: str, *, lock: bool = False
    ) -> tuple[UniversalProfile, FinancialDocument]:
        profile = self.profiles.load(owner, token, lock=lock)
        configuration(profile.industry)
        row = self.session.get(Workspace, owner)
        return profile, FinancialDocument.model_validate(row.document) if row else new_document(
            profile
        )

    def view(self, owner: UUID, token: str) -> FinancialView:
        profile, doc = self.load(owner, token)
        current = compatible(doc, profile)
        row = self.session.scalar(
            sa.select(Result)
            .where(Result.conversation_id == owner)
            .order_by(Result.created_at.desc())
            .limit(1)
        )
        snapshot = FinancialSnapshot.model_validate(row.snapshot) if row else None
        if snapshot and (not current or snapshot.inputs != doc):
            snapshot = None
        proposal = self.session.scalar(
            sa.select(Action)
            .where(Action.conversation_id == owner, Action.kind == "propose")
            .order_by(Action.created_at.desc())
            .limit(1)
        )
        status = "idle"
        if proposal:
            status = (
                "interrupted"
                if proposal.state == "running" and proposal.deadline_at < datetime.now(UTC)
                else proposal.state
            )
        return FinancialView.model_validate(
            dict(
                configuration=configuration(doc.model),
                document=doc,
                current=current,
                missing=missing(doc),
                needs_review=tuple(
                    k
                    for k in requirements(doc)
                    if k in doc.entries and doc.entries[k].review == "proposed"
                ),
                result=snapshot,
                proposal_status=status,
                proposal_error=proposal.error_code if proposal else None,
            )
        )

    def receipt(self, owner: UUID, body: FinancialCommand, kind: str) -> Action | None:
        action = self.session.get(Action, (owner, body.request_id))
        if action and action.payload_hash != digest([kind, body.model_dump(mode="json")]):
            reject("financial_idempotency_conflict", 409)
        return action

    def guard(
        self, owner: UUID, token: str, body: FinancialCommand, *, reset: bool = False
    ) -> tuple[UniversalProfile, FinancialDocument]:
        profile, doc = self.load(owner, token, lock=True)
        if profile.revision != body.expected_profile_revision:
            reject("financial_profile_conflict", 409)
        if profile.confirmed_revision != profile.revision:
            reject("financial_profile_confirmation_required", 409)
        if doc.revision != body.expected_input_revision:
            reject("financial_input_conflict", 409)
        if not compatible(doc, profile):
            if not reset:
                reject("financial_profile_changed", 409)
            doc = new_document(profile).model_copy(update={"revision": doc.revision})
        return profile, doc

    def record(
        self,
        owner: UUID,
        body: FinancialCommand,
        kind: str,
        doc: FinancialDocument,
        *,
        running: bool = False,
    ) -> Action:
        # One global short stock lock; no lock/connection survives inference.
        self.session.execute(sa.text("SELECT pg_advisory_xact_lock(672105)"))
        global_count = self.session.scalar(sa.select(sa.func.count()).select_from(Action)) or 0
        owner_count = (
            self.session.scalar(
                sa.select(sa.func.count())
                .select_from(Action)
                .where(Action.conversation_id == owner)
            )
            or 0
        )
        if global_count >= 2000 or owner_count >= 100:
            reject("financial_storage_limit", 429)
        active = self.session.scalars(
            sa.select(Action).where(
                Action.conversation_id == owner, Action.state == "running", Action.kind == "propose"
            )
        ).all()
        for previous in active:
            if previous.deadline_at > datetime.now(UTC) and kind == "propose":
                reject("financial_proposal_in_progress", 409)
            if previous.deadline_at <= datetime.now(UTC):
                previous.state = "interrupted"
        action = Action(
            conversation_id=owner,
            request_id=body.request_id,
            payload_hash=digest([kind, body.model_dump(mode="json")]),
            kind=kind,
            state="running" if running else "completed",
            error_code=None,
            created_at=datetime.now(UTC),
            deadline_at=datetime.now(UTC) + timedelta(seconds=180),
            snapshot=doc.model_dump(mode="json"),
        )
        self.session.add(action)
        self.session.flush()
        return action

    def store(self, owner: UUID, doc: FinancialDocument) -> None:
        row = self.session.get(Workspace, owner)
        if row is None:
            self.session.add(Workspace(conversation_id=owner, document=doc.model_dump(mode="json")))
        else:
            row.document = doc.model_dump(mode="json")
        self.session.flush()

    def patch(self, owner: UUID, token: str, body: InputPatch) -> FinancialView:
        self.profiles.load(owner, token, lock=True)
        if self.receipt(owner, body, "patch"):
            return self.view(owner, token)
        _, doc = self.guard(owner, token, body, reset=body.reset_for_profile)
        updated = patch_document(doc, body.updates)
        if body.billing_model is not None:
            if doc.model != "online_school":
                reject("financial_billing_not_applicable")
            # A different billing basis invalidates ALL old payment-period confirmations.
            updated = updated.model_copy(
                update={
                    "billing_model": body.billing_model,
                    "entries": {
                        k: v.model_copy(update={"review": "proposed"})
                        for k, v in updated.entries.items()
                    }
                    if body.billing_model != doc.billing_model
                    else updated.entries,
                }
            )
        self.record(owner, body, "patch", updated)
        self.store(owner, updated)
        return self.view(owner, token)

    def review(self, owner: UUID, token: str, body: ReviewCommand) -> FinancialView:
        self.profiles.load(owner, token, lock=True)
        if self.receipt(owner, body, "review"):
            return self.view(owner, token)
        _, doc = self.guard(owner, token, body)
        keys = (*body.confirm, *body.reject)
        if not keys or len(set(keys)) != len(keys) or not set(keys) <= doc.entries.keys():
            reject("invalid_financial_review")
        entries = dict(doc.entries)
        for key in keys:
            entries[key] = entries[key].model_copy(
                update={"review": "confirmed" if key in body.confirm else "rejected"}
            )
        doc = doc.model_copy(update={"entries": entries, "revision": doc.revision + 1})
        self.record(owner, body, "review", doc)
        self.store(owner, doc)
        return self.view(owner, token)

    def begin(
        self, owner: UUID, token: str, body: FinancialCommand, kind: str
    ) -> tuple[UniversalProfile, FinancialDocument, int] | None:
        self.profiles.load(owner, token, lock=True)
        if self.receipt(owner, body, kind):
            return None
        profile, doc = self.guard(owner, token, body)
        if kind == "propose" and doc.model == "online_school" and not doc.billing_model:
            reject("financial_billing_required")
        self.record(owner, body, kind, doc, running=True)
        self.store(owner, doc)
        consent = require_consent(self.session, owner, "assistant").revision
        return profile, doc, consent

    def fence(
        self, owner: UUID, token: str, body: FinancialCommand, kind: str, consent: int
    ) -> tuple[UniversalProfile, FinancialDocument, Action]:
        profile, doc = self.guard(owner, token, body)
        action = self.receipt(owner, body, kind)
        if not action or action.state != "running" or action.deadline_at < datetime.now(UTC):
            reject("financial_operation_expired", 409)
        if require_consent(self.session, owner, "assistant").revision != consent:
            reject("consent_revision_conflict", 409)
        return profile, doc, action

    def publish_proposal(
        self,
        owner: UUID,
        token: str,
        body: FinancialCommand,
        proposal: AssumptionProposal,
        consent: int,
        generation_model: str,
    ) -> FinancialView:
        _, doc, action = self.fence(owner, token, body, "propose", consent)
        from app.finance.v2.llm import validate_proposal

        validate_proposal(proposal, doc)
        entries = dict(doc.entries)
        for suggestion in proposal.assumptions:
            update = ParameterUpdate(
                **suggestion.model_dump(exclude={"epistemic", "source"}), kind="user_assumption"
            )
            entries[suggestion.parameter] = make_input(
                update, doc.revision + 1, qwen=True
            ).model_copy(
                update={
                    "generation_model": generation_model,
                    "generation_prompt_version": "qwen-assumptions-u05-v1",
                }
            )
        doc = doc.model_copy(update={"entries": entries, "revision": doc.revision + 1})
        action.state, action.snapshot = "completed", doc.model_dump(mode="json")
        self.store(owner, doc)
        return self.view(owner, token)

    def publish_result(
        self,
        owner: UUID,
        token: str,
        body: FinancialCommand,
        result: FinancialCalculation,
        consent: int,
    ) -> FinancialView:
        profile, doc, action = self.fence(owner, token, body, "calculate", consent)
        fingerprint = digest(
            [
                profile.model_dump(mode="json"),
                doc.model_dump(mode="json"),
                result.model_dump(mode="json"),
            ]
        )
        exists = self.session.scalar(
            sa.select(Result).where(
                Result.conversation_id == owner, Result.fingerprint == fingerprint
            )
        )
        if not exists:
            self.session.execute(sa.text("SELECT pg_advisory_xact_lock(672105)"))
            total = self.session.scalar(sa.select(sa.func.count()).select_from(Result)) or 0
            own = (
                self.session.scalar(
                    sa.select(sa.func.count())
                    .select_from(Result)
                    .where(Result.conversation_id == owner)
                )
                or 0
            )
            if total >= 200 or own >= 20:
                reject("financial_result_storage_limit", 429)
            snapshot = FinancialSnapshot(
                id=uuid4(),
                created_at=datetime.now(UTC),
                fingerprint=fingerprint,
                profile=profile,
                inputs=doc,
                configuration=configuration(doc.model),
                result=result,
            )
            self.session.add(
                Result(
                    id=snapshot.id,
                    conversation_id=owner,
                    fingerprint=fingerprint,
                    created_at=snapshot.created_at,
                    snapshot=snapshot.model_dump(mode="json"),
                )
            )
        action.state = "completed"
        self.session.flush()
        return self.view(owner, token)

    def result(self, owner: UUID, token: str, result_id: UUID) -> FinancialSnapshot:
        self.profiles.load(owner, token)
        row = self.session.get(Result, result_id)
        if row is None or row.conversation_id != owner:
            reject("financial_result_not_found", 404)
        return FinancialSnapshot.model_validate(row.snapshot)
