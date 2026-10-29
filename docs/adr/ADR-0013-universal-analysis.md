# ADR-0013: универсальный анализ с проверяемыми возможностями и совместимостью v1

Дата:28.10.2026. Статус: **Proposed — на review владельца в PR U-00**.
Владелец утвердил семиэтапную инициативу; принятие её технических контрактов — отдельное
решение при review этого PR. Никакой runtime функционал этим ADR не включается.

## Контекст

MVP имеет проверенные диалог/OSM/Decimal/consent/report механизмы, но не durable planner.
Есть DataProvider/provenance и ownerless неиспользуемая live сервисами AnalysisRun table.
Фиксированный frontend guard требует карту; кофе-шаблон не универсален.
Целевая машина16GB/RTX3050Ti4GB не подходит для whole-city graph в памяти и нескольких
одновременных LLM/import операций без измерений. Старый roadmap содержит конфликтующие
U-ID; [crosswalk](../architecture/BUSINESS_AI_2_IMPLEMENTATION_PLAN.md) сохраняет их историю.

## Решение для будущего внедрения

1. Оставить modular monolith/одну PostgreSQL/PostGIS/локальную Qwen. Qwen предлагает
   compact PlanProposal, backend валидирует capabilities/permissions/units/DAG/budget.
   Python/PostGIS исполняют только reviewed methods. Unknown остаётся unknown.
2. Universal ProfileV2 и owner-scoped AnalysisPlan/Run APIs отдельно от strict v1.
   Reuse DataOrigin, MetricWithProvenance, InputSource/FinancialMetric/Indicator;
   epistemic/review/lineage — дополнительные измерения, не конкурентный enum origin.
3. Расширять существующий DataProvider/dataset metadata. City identity, граница,
   покрытие слоя и нанесённые объекты — разные понятия. Source license и network
   permission проверяются отдельно; никакого автоматического synthetic fallback.
4. Durable jobs/leases/checkpoints/events в PostgreSQL, bounded operator CLI worker
   из того же image, без Redis/Celery. Fetch/LLM вне DB transaction; short claim и
   fenced activation. Lease timeout не освобождает heavy slot без подтверждения
   остановки старого worker. H-03 single-process queue остаётся единственной LLM queue.
5. Tool gateway принимает approved source/tool IDs, не shell/SQL/file paths/user URLs.
   Network egress fail-closed, redirects0, проверенный peer/DNS и budgets.
6. Новые sector configs выбирают Python adapters; v1 finance formulas/rounding и
   immutable report bytes/hash не меняются. No-map и partial — нормальные outcomes.
7. Ви получает owner-scoped реальный stage/event cursor; никаких фиктивных процентов.
   Profile changes/consent revocation повторно проверяются перед result publication.

Контракты/границы/предварительные caps:
[Architecture](../architecture/BUSINESS_AI_2_UNIVERSAL_ARCHITECTURE.md),
[Data & Tools](../architecture/BUSINESS_AI_2_DATA_AND_TOOLS.md).

## Рассмотренные альтернативы

- Один giant prompt и произвольные HTTP/tools: не проверяет поддержку методов,
  ресурсы и достоверность, SSRF/injection риски. Не выбран.
- Расширить v1 DTO/переписать старые report snapshots: extra-forbid и hashes делают
  это несовместимым. Не выбран; только versioned additive evolution.
- Новая provenance/data база: дублирует готовые origins/providers/datasets. Не выбрана.
- Только BackgroundTasks/React flags: нет restart recovery/atomic dedup/owner isolation.
  Не выбрано для длительных импортов; существующий короткий UI flow пока не меняется.
- Redis/Celery/microservices/whole-city in-memory routing: не оправданы доказанной
  нагрузкой/оборудованием; отдельный broker рассмотреть только по измеренным требованиям.
- Все неизвестные отрасли → nearest coffee: создаёт неподходящий анализ; сохраняем
  raw label, clarification и limited generic capabilities.

## Последствия и проверка

Потребуются последующие additive migrations, profiles/config revisions, worker supervision,
source-policy review, Qwen live evaluation и real small-AOI resource measurements.
Предложенные512MiB worker/tiles/LLM budgets не измерены и не SLA. Нет обещания all cities/
all industries, юридической пригодности, банковского одобрения или достоверности гипотез.
Rollout expand/read-switch, old v1 readers/exports работают; app rollback отключает v2,
не запускает destructive DB downgrade. При несовместимой схеме — backup/restore H-04/FU.

U-00 проверяет согласованность со static code/links/4design walkthrough и mandatory
docs-only QG-PR. Реальные новые интеграции тестируются в U-01…06, не объявлены PASS здесь.
Owner approval/merge U-00 не означает разрешения начать следующий этап.

## Уточнение владельца при U-01 — 29.10.2026

Актуальный статус: **Accepted**. PR31 объединён; владелец подтвердил принятие ADR
и разрешил только BA2/U-01. Исходные дата/Proposed-строка выше сохранены как история U-00.

1. No automatic synthetic fallback запрещает незаметную подмену фактов, а не сценарное
   моделирование. Существенные гипотезы требуют review U-05; подтверждение не меняет
   synthetic origin на observed. U-01 сохраняет такую типизацию, не генерирует гипотезы.
2. Неизвестная отрасль получает будущий generic профиль/уточнения/ограниченный анализ,
   а не отказ или nearest coffee. Реестр категорий U-01 не зависит от отрасли;
   весь отраслевой движок остаётся U-04.
3. 512MiB и другие U-00 бюджеты — кандидаты для измерений, не blanket limits.
   Per-operation resource policies/peak RAM/диск/CPU/время измеряются в U-02.
   U-01 ограничивает только объём metadata/HTTP и не доказывает импорт всей Москвы.

Фактическая реализация и границы: [U-01](../architecture/BUSINESS_AI_2_DATA_REGISTRY_IMPLEMENTATION.md).

## Уточнение реализации U-02 — 29.10.2026

[U-02](../architecture/BUSINESS_AI_2_DYNAMIC_ACQUISITION.md) реализует один small-POI
profile, а не универсальный city importer. PostgreSQL jobs/events, отдельный процесс,
process+session DB mutex, lease/fence/expected version и atomic existing importer сохранены.
Checkpoint — проверенный normalized artifact в БД; внутри маленького atomic import
повторяется целая AOI. Streaming больших выгрузок/tiling/group activation не заявлены.

Публичный Overpass допускается только как operator one-off smoke после terms review,
с expiry; default network закрыт. Он не становится постоянным backend приложения.
Измерено ~87,3MiB RSS на одной реальной маленькой AOI. Для этого класса выбраны4MiB/
10000elements/256MiB RSS check и768MiB cgroup cap/0.5CPU, не универсальные512MiB.
H-03 не изменён: worker не использует LLM/API pool. Совместный live inference stress
не измерен; shared admission для будущих high-memory jobs остаётся незавершённым,
а не объявляется работающим. Увеличение budget требует новых измерений.

Lease expiry восстанавливается только при доказанно освобождённом process lock той же
installation; другая installation получает recovery_required. Обычный API restart
не является доказательством смерти worker. Нового broker/Redis/Celery нет.
