import hashlib
import json
from datetime import UTC, datetime
from time import monotonic
from typing import NoReturn
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.bank import current_catalogue
from app.bank.matching import match
from app.data.providers import demo_enabled, policy, providers
from app.db.models import GeoDatasetRecord, ReportRecord, WalkGraphRecord
from app.domain.enums import ConfirmationState
from app.finance.engine import ALGORITHM_VERSION as FINANCE_VERSION
from app.finance.engine import calculate
from app.geo.ranking import rank_candidates
from app.geo.scoring import ALGORITHM_VERSION as GEO_VERSION
from app.geo.walk_graph import ALGORITHM_VERSION as WALK_VERSION
from app.geo.walking import catchment
from app.leads.consents import require_consent
from app.reporting.schemas import ReportRequest, ReportSnapshot, ReportView
from app.services.conversations import Conversations, VersionConflict


def fail(code: str, status: int = 409) -> NoReturn:
    raise HTTPException(status, detail={"code": code})


def serialize(snapshot: ReportSnapshot) -> bytes:
    return json.dumps(
        snapshot.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def prepare(session: Session, owner: UUID, token: str, body: ReportRequest) -> ReportView:
    started = monotonic()
    view = Conversations(session).get(owner, token, lock=True)
    require_consent(session, owner, "assistant")
    if view.version != body.expected_version:
        raise VersionConflict(view.version)
    if view.profile.confirmation_state != ConfirmationState.CONFIRMED:
        fail("report_profile_not_confirmed", 422)
    if body.geo is None and body.finance is None:
        fail("report_no_analysis", 422)
    count = (
        session.scalar(
            sa.select(sa.func.count())
            .select_from(ReportRecord)
            .where(ReportRecord.conversation_id == owner)
        )
        or 0
    )
    if count >= 20:
        fail("report_limit_reached", 429)

    def checked(actual: str, expected: str) -> None:
        if actual != expected:
            fail("report_results_changed")
        if monotonic() - started > 20:
            fail("report_generation_timeout", 503)

    geo = None
    if body.geo:
        if body.geo.request.candidates.profile != view.profile:
            fail("report_profile_mismatch")
        if not body.geo.request.candidates.data_version or body.geo.request.candidates.limit > 5:
            fail("report_geo_version_or_limit", 422)
        geo = rank_candidates(session, body.geo.dataset, body.geo.request)
        checked(geo.request_fingerprint, body.geo.fingerprint)
    if body.selected_zone and (
        geo is None or body.selected_zone not in {f.id for f in geo.candidates.features}
    ):
        fail("report_invalid_zone", 422)
    finance = None
    if body.finance:
        if body.finance.request.profile != view.profile:
            fail("report_profile_mismatch")
        zone = body.finance.request.selected_zone
        if zone and (
            geo is None
            or zone.candidate_id != body.selected_zone
            or zone.ranking_fingerprint != geo.request_fingerprint
            or zone.data_version != geo.candidates.dataset.data_version
            or zone.dataset_slug != geo.candidates.dataset.slug
        ):
            fail("report_invalid_zone", 422)
        finance = calculate(body.finance.request)
        checked(finance.request_fingerprint, body.finance.fingerprint)
    bank = None
    if body.bank:
        if body.bank.request.expected_version != view.version:
            fail("report_profile_mismatch")
        catalogue = current_catalogue()
        if body.bank.request.catalogue_fingerprint != catalogue.fingerprint:
            fail("report_results_changed")
        bank = match(view.profile, view.version, body.bank.request.needs, catalogue)
        checked(bank.request_fingerprint, body.bank.fingerprint)
    walking = None
    if body.walking:
        if geo is None or body.walking.dataset != geo.candidates.dataset.slug:
            fail("report_invalid_walking_context", 422)
        if (
            body.walking.request.data_version != geo.candidates.dataset.data_version
            or not body.walking.request.graph_version
        ):
            fail("report_invalid_walking_context", 422)
        walking = catchment(session, body.walking.dataset, body.walking.request)
        checked(walking.request_fingerprint, body.walking.fingerprint)
    data = []
    for item in body.providers:
        policy(item.request.mode)
        value = providers()[item.request.provider].read(session, item.request)
        checked(value.request_fingerprint, item.fingerprint)
        data.append(value)
    missing = tuple(
        key
        for key, value in (("geo", geo), ("finance", finance), ("bank", bank), ("walking", walking))
        if value is None
    )
    summary = [
        (
            "Результат сравнивает географические признаки и сце"
            "нарную экономику; инвестиционное решение требует д"
            "ополнительных данных."
        )
    ]
    if geo:
        summary.append(
            "Сформировано зон: "
            f"{len(geo.candidates.features)}"
            "; рейтинг относится только к доступному OSM-окруже"
            "нию."
        )
        if geo.missing_data:
            summary.append(
                f"Геоанализ: {len(geo.missing_data)} недостающих показателей; "
                "перечень - в разделе локаций и JSON."
            )
    if finance:
        if finance.missing_data:
            summary.append(
                f"Финансы: {len(finance.missing_data)} неучтённых факторов; "
                "ограничения перечислены в финансовом разделе."
            )
        summary.append(
            "Бюджет сравнивается с модельными стартовыми вложен"
            "иями, а не с проверенной ценой помещения."
        )
    summary.extend(
        (
            "Проверить помещения, аренду, реальный спрос, налоги и фактические условия банка.",
            "Данные в ВТБ не отправляются; кредитное решение не принимается.",
        )
    )
    snapshot = ReportSnapshot(
        id=uuid4(),
        created_at=datetime.now(UTC),
        profile_version=view.version,
        profile_updated_at=view.updated_at,
        profile=view.profile,
        geo=geo,
        selected_zone=body.selected_zone,
        finance=finance,
        bank=bank,
        walking=walking,
        providers=tuple(data),
        summary=tuple(dict.fromkeys(summary)),
        missing_sections=missing,
    )
    raw = serialize(snapshot)
    if len(raw) > 4 * 1024 * 1024:
        fail("report_snapshot_too_large", 413)
    from app.reporting.pdf import render

    try:
        pdf = render(snapshot)
    except ValueError:
        fail("report_render_limit", 422)
        raise AssertionError("unreachable") from None
    if len(pdf) > 3 * 1024 * 1024:
        fail("report_pdf_too_large", 413)
    if monotonic() - started > 30:
        fail("report_generation_timeout", 503)
    row = ReportRecord(
        id=snapshot.id,
        conversation_id=owner,
        profile_version=view.version,
        created_at=snapshot.created_at,
        snapshot=snapshot.model_dump(mode="json"),
        snapshot_sha256=sha(raw),
        pdf=pdf,
        pdf_sha256=sha(pdf),
    )
    session.add(row)
    session.flush()
    return describe(session, row, snapshot, view.version)


def load(
    session: Session, owner: UUID, token: str, report_id: UUID
) -> tuple[ReportRecord, ReportSnapshot, int]:
    view = Conversations(session).get(owner, token)
    row = session.scalar(
        sa.select(ReportRecord).where(
            ReportRecord.id == report_id, ReportRecord.conversation_id == owner
        )
    )
    if row is None:
        fail("report_not_found", 404)
    assert row is not None
    try:
        snapshot = ReportSnapshot.model_validate(row.snapshot)
        if sha(serialize(snapshot)) != row.snapshot_sha256 or sha(row.pdf) != row.pdf_sha256:
            fail("report_integrity_error", 503)
    except ValidationError:
        fail("report_integrity_error", 503)
        raise AssertionError("unreachable") from None
    return row, snapshot, view.version


def describe(
    session: Session, row: ReportRecord, snapshot: ReportSnapshot, current_version: int
) -> ReportView:
    reasons = []
    if current_version != snapshot.profile_version:
        reasons.append("Профиль изменился после подготовки отчёта.")
    if snapshot.geo:
        source = snapshot.geo.candidates.dataset
        if snapshot.geo.algorithm_version != GEO_VERSION:
            reasons.append("Версия географического алгоритма изменилась.")
        if (
            datetime.now(UTC) - source.osm_base
        ).days > source.stale_after_days and not source.stale:
            reasons.append("Данные OSM перешли срок пересмотра после подготовки снимка.")
        active = session.scalar(
            sa.select(GeoDatasetRecord.data_version).where(
                GeoDatasetRecord.slug == source.slug, GeoDatasetRecord.active
            )
        )
        if active != source.data_version:
            reasons.append("Активная версия OSM изменилась или недоступна.")
    if snapshot.walking and snapshot.walking.graph and snapshot.geo:
        if snapshot.walking.algorithm_version != WALK_VERSION:
            reasons.append("Версия сетевого алгоритма изменилась.")
        active_graph = session.scalar(
            sa.select(WalkGraphRecord.graph_version).where(
                WalkGraphRecord.slug == snapshot.geo.candidates.dataset.slug, WalkGraphRecord.active
            )
        )
        if active_graph != snapshot.walking.graph.graph_version:
            reasons.append("Активная версия пешеходного графа изменилась.")
    if snapshot.bank:
        try:
            catalogue = current_catalogue()
            if (
                catalogue.fingerprint != snapshot.bank.catalogue.fingerprint
                or catalogue.as_of != snapshot.bank.catalogue.as_of
            ):
                reasons.append("Банковский каталог изменился; требуется новый подбор.")
        except HTTPException:
            reasons.append("Актуальность каталога сейчас проверить невозможно.")
    if snapshot.finance and snapshot.finance.algorithm_version != FINANCE_VERSION:
        reasons.append("Версия финансовых формул изменилась.")
    for value in snapshot.providers:
        if value.dataset.provider == "synthetic" and not demo_enabled():
            reasons.append("Демонстрационные провайдерские данные отключены.")
        versions = providers()[value.dataset.provider].datasets(session)
        if not any(
            v.active
            and v.data_version == value.dataset.data_version
            and v.slug == value.dataset.slug
            for v in versions
        ):
            reasons.append("Выбранная версия провайдера больше не является текущей.")
    return ReportView(
        id=row.id,
        created_at=row.created_at,
        profile_version=row.profile_version,
        snapshot_sha256=row.snapshot_sha256,
        pdf_sha256=row.pdf_sha256,
        status="outdated" if reasons else "current",
        reasons=tuple(dict.fromkeys(reasons)),
        missing_sections=snapshot.missing_sections,
        json_bytes=len(serialize(snapshot)),
        pdf_bytes=len(row.pdf),
    )
