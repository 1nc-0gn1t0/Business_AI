# Business AI 2.0 — контракты данных, планирования и инструментов

U-00, 28.10.2026. Все новые типы/API/таблицы ниже — **проект для будущих этапов**.
Ничего из этого не исполняется в текущем приложении. Контекст и совместимость:
[UNIVERSAL_ARCHITECTURE](BUSINESS_AI_2_UNIVERSAL_ARCHITECTURE.md),
порядок внедрения: [IMPLEMENTATION_PLAN](BUSINESS_AI_2_IMPLEMENTATION_PLAN.md).
Поля описаны в wire snake_case; TypeScript sketches в соседнем документе концептуальны,
будущие TS-типы генерируются из OpenAPI, не поддерживаются вручную параллельно.

**29.10.2026 / U-01:** registry/coverage/freshness и базовая sufficiency реализованы
[в ограниченном metadata service](BUSINESS_AI_2_DATA_REGISTRY_IMPLEMENTATION.md).
`local_status=available/partial/stale/missing/unknown` дополняет, а не заменяет U-00
summary/availability/freshness/completeness/acquirability. Остальные planner/jobs/tools/
assumption workflows ниже остаются проектом. Уточнения владельца — addendum ADR0013.

**29.10.2026 / U-02:** bounded POI acquisition/jobs/events/operator API реализованы
[отдельным worker](BUSINESS_AI_2_DYNAMIC_ACQUISITION.md). Точный executable contract
описан там; public Overpass только expiring operator smoke, не sustained backend.
Larger tiled imports/group activation/shared high-memory admission остаются будущей работой,
не объявлены реализованными схемами ниже. H-03 не заменён и не дублируется.

## 1. Provenance и достаточность

Единственный enum происхождения остаётся [DataOrigin](../../apps/api/app/domain/enums.py).
Epistemic — классификация пригодности, а не замена origin:

| Epistemic | Существующий origin / контракт | Условие |
| --- | --- | --- |
| observed | open_data/licensed/bank_internal, MetricWithProvenance или InputSource | Есть dataset/evidence/date/version; это наблюдение источника, не гарантия факта на местности |
| user_provided | user_input, InputSource + profile/message revision | Пользователь сообщил/исправил, отдельный review; не independent verification |
| derived | modelled, FinancialMetric/formula_id/input_paths или geo algorithm/provenance | Известен deterministic executor и все inputs/версии; сохранить assumed lineage |
| assumed | synthetic, confidence=not_applicable, limitations обязательны | Сценарная гипотеза/авторский шаблон; никакого observed_at реального наблюдения |
| unknown | nullable Indicator/Value без measurement | Причина missing/outside_coverage/not_supported; не добавлять DataOrigin.UNKNOWN и не подставлять0 |

`modelled` estimate без воспроизводимых inputs не становится observed: ограниченная
гипотеза должна пройти assumption review либо оставаться unknown. Счётчик нанесённых
OSM POI может быть observed mapping count, но не verified count действующих предприятий.
Синтетические inputs → modelled financial output с явным `contains_assumptions=true`
в v2 lineage; enum/форматы v1 не меняются. `source_attested=true` в finance v1 —
заявление источника, не доказательство независимой проверки; будущий planner доверяет
только evidence, разрешённому и проверенному сервером, а не флагу из ответа Qwen.

`DataRequirement={id,parameter_path,unit,critical_for:[capability_id],
accepted_origins[],max_age?,required_extent?,min_coverage?,allow_partial,
allow_assumption,allow_user_input,reason_code}`. Требования принадлежат reviewed
capability/config; Qwen может предложить значение, но не ослабить critical/allowed rules.

`SufficiencyAssessment={profile_revision,requirements_revision,evaluated_at,
decisions:[{requirement_id,state,evidence_refs[],action,reason_code}],
allowed_tasks[],blocked_tasks[],warnings[]}`.
States: sufficient/partial/missing/stale/not_applicable/unknown.
Actions: use_pinned/cache_revalidate/request_acquisition/ask_user/propose_assumption/
omit_optional/block. Порядок: проверенный подходящий факт → допустимая загрузка →
существенный вопрос пользователю → разрешённая гипотеза → ограничение результата.
Если факт неподходящего периода/единицы, он не «лучше» свежего пользовательского ввода.

`AssumptionProposal={id,parameter_path,value,unit,range:{min,max},method,
origin:synthetic,confidence:not_applicable,evidence_refs[],limitations[],
proposed_by:model_or_template,model_prompt_revision?,review_revision,status}`.
Method — строковый ID/version, не исполняемая формула. Для денег Decimal strings;
min≤value≤max, одинаковые units/period. Range — сценарный интервал, не доверительный.
Статусы proposed/confirmed/rejected/superseded. Подтверждение пользователем меняет
review, **не происхождение**. Изменение значения создаёт новую revision; если пользователь
заявляет собственное наблюдение, это новый user_input с цитатой, не переименование старого.

Утверждения о спросе, аренде, конкурентах/помещениях, юридической пригодности и условиях
банка не выводятся из одного отсутствующего параметра. Нельзя заменить unknown0,
NaN, пустой строкой либо «средним для Москвы» без явного сценарного источника.

## 2. Source Registry и coverage

Расширять `app/data`/`DataProvider`, `ProviderDataset` и OSM manifests, не заводить
второй набор metric origins или вторую базу геоданных. ProviderId v1 Literal остаётся
прежним; новый adapter ID публикуется через v2, когда реализация действительно существует.

| Контракт | Обязательные поля |
| --- | --- |
| SourceDefinition | id/revision/config_sha256, adapter_id/revision, publisher, data_types[], allowed_use, license_id/text_ref/license_review_at, attribution, availability, freshness_policy, endpoint_policy_ref, resource_policy_ref, approval_status/approver/review_due |
| Source availability | ready/degraded/unavailable/not_integrated/unknown; checked_at/error_code/retry_not_before. HTTP200 не означает права на использование |
| DatasetRevision | existing provider/slug/data_version/SHA, source_ref, artifact SHA, license/attribution, imported_at/fetched_at/source_timestamp, temporal_coverage, geometry/bbox/CRS, layer_types, quality_report_ref, activation state |
| TerritoryRef | canonical id/revision, country/region, raw_label, boundary artifact/source/version; per-layer dataset refs отдельно |
| CoverageQuery | territory/AOI revision, layer/metric IDs, time interval, freshness requirement, capability revision, pinned dataset refs optional |
| CoverageAssessment | query fingerprint, assessed_at, source-policy revision, candidate datasets[], missing layers/areas/periods, axes below, summary/reasons, acquisition offer optional |

Coverage axes не смешиваются:

- availability: present/missing/unknown;
- freshness: current/stale/unknown (source timestamp отдельно от download time);
- completeness: full_for_requested_scope/partial/unknown + geometry intersection,
  mapped-object quality и method; без ложной «полноты рынка»;
- acquirability: permitted/forbidden/unavailable/not_integrated/unknown;
- acquisition status и required resource estimate отдельно от локального наличия.

Public summary вычисляется сервером, причины/axes сохраняются:

| Случай | summary / что делать |
| --- | --- |
| Есть пригодный current snapshot | usable; reuse pinned version |
| Есть устаревший | stale; revalidate/refresh либо explicit stale acceptance, если capability разрешает |
| Есть часть нужных слоёв/AOI | partial; bounded analysis/загрузка missing; одновременно может быть stale |
| Нет local, проверенный разрешённый adapter может получить | acquirable; job offer с limits, не обещание успеха |
| Нет пригодного cache, approved source недоступен | source_unavailable; safe error/backoff, не silently synthetic |
| Рассмотренные approved sources не дают требуемый показатель | not_available_from_approved_sources + source IDs/date; это не доказательство отсутствия объекта в мире |
| Registry/лицензия/coverage не установлены | unknown; вопрос/operator review, не автоматический fetch |

Если source offline, но есть пригодный cache, summary остаётся usable/stale с причиной
offline_source; недоступность сети не уничтожает локальные данные. Пустой result и
HTTP404 не доказывают отсутствие предприятий. Полнота POI не равна связности graph.
Полигон города не равен bbox загруженного слоя; считать долю площади можно только с
проверенной boundary/method. Неизвестная полнота остаётся null, не 100%.

Кэш: ключ source+adapter+normalized AOI+layers+time+query/config revision; отдельные
SHA artifact и normalized dataset. Reuse только после проверки license/freshness/checksum.
TTL source-policy specific; current OSM metadata использует30дней, synthetic365, это не
универсальные сроки. Negative/error cache имеет короткий retry_not_before и reason,
не бессрочную запись «данных нет». Старые pinned datasets не удалять, пока на них есть
run/report references. Retention/stock quotas включают artifacts, events и failed staging;
последняя пригодная версия не удаляется ради новой.

SourceAdapter protocol (будущий интерфейс, не публичный model API):

```text
describe() -> SourceDefinition
assess(CoverageQuery, LocalMetadataSnapshot) -> CoverageAssessment
prepare(AcquisitionSpec, ResourcePolicy) -> BoundedFetchSpec | Denial
fetch(BoundedFetchSpec, VerifiedNetworkClient, CancelToken) -> StagedArtifactRef
validate(StagedArtifactRef) -> ValidatedArtifactRef + QualityReport
import_batches(ValidatedArtifactRef, Checkpoint, CancelToken) -> StagedDatasetRef
activate(StagedDatasetRef, ExpectedActiveVersion, FencingToken) -> DatasetRevision
```

Раздельные adapters OSM/official_statistics/licensed; второй/третий — not_integrated,
пока не проверены формат, территория, период и лицензия. `describe` не делает сеть.
Fetch/parse не принимают SQLAlchemy Session. Source approval не даёт Qwen право менять
endpoint. Непроверенный URL из поиска — SourceCandidate, не SourceDefinition.

## 3. Analysis Planner

Место: `app/analysis/planner`, рядом с dialogue service, не внутри geo/finance/Vi.
Вход: immutable ProfileV2/revision, consent revision, compact capability catalog revision,
requested goals, resource budget, registry/coverage snapshot. Qwen возвращает **proposal**,
а backend строит исполнимый план. Никакого исполнения из свободного текста.

```text
PlanProposal = {schema_version, goals[], proposed_tasks:[
  {local_id, capability_id, arguments, depends_on[], reason_code}
]}
AnalysisPlan = {
  schema_version:"analysis-plan-v2", id, revision, conversation_id, profile_revision,
  consent_revision, capability_catalog_revision, config_refs[], requirements_revision,
  budget_ref, tasks:AnalysisTask[], input_fingerprint, created_at, expires_at,
  status, missing_dependencies[], warnings[]
}
AnalysisTask = {
  id, capability_id, capability_revision, argument_schema_revision, validated_arguments,
  input_refs[], depends_on[], required:boolean, applicability,
  skip_condition_id?, reason_code, explanation_parameters,
  state, attempt, result_ref?, error?
}
```

Типы задач: clarify_profile, assess_coverage, request_acquisition, validate_dataset,
geo_candidates, geo_rank, pedestrian_catchment, finance_calculate, bank_match,
prepare_report. Car accessibility/digital finance — unavailable capability до своего PR.
Эти названия — будущий каталог; наличие строки в документации не включает инструмент.

`CapabilityDefinition={id,revision,status,input_schema_ref,output_schema_ref,
required_inputs[],applicability_rule_id,executor_id,cost_class,permissions[],
limits_ref,method_reason_codes[],policy_refs[],side_effect_class}`.
Only reviewed registrations разрешены; tool ID не равен dynamic Python import.
Статусы task: planned/blocked/awaiting_user/awaiting_data/queued/running/succeeded/
skipped/failed/cancelled/stale. Run: planning/awaiting_user/awaiting_data/queued/running/
completed/partial/failed/cancelled/stale. `succeeded` — завершилась операция, не доказан рынок.

Валидация в порядке: strict schema/caps → known capability/revision → auth/consent →
applicability → mandatory inputs/units/origins → DAG (unique IDs, no cycles,
all dependency refs exist) → budget → deterministic task expansion. Сервер добавляет
обязательные assess/validation dependencies, модель не может их удалить.
`skip_condition_id` — whitelist policy, не expression модели. Пропуск optional
допустим с reason; required unresolved означает blocked/partial, не completed.
Отмена предка отменяет или блокирует descendants, независимая готовая ветка сохраняется.

Причины — машинные codes вроде physical_location_required, online_no_location,
mapped_context_only, missing_vehicle_network, unsupported_industry_method. Безопасное
объяснение генерируется по проверенным параметрам; сырой rationale Qwen не источник фактов.

План не объявляется готовым к исполнению до review profile и существенных assumptions.
Пример A: coverage→geo_rank (+walking optional), explicit finance inputs→finance,
optional needs→bank, available results→report. B: coverage gap→acquisition offer;
car module blocked, уточнения posts/hours; C: skip geo(reason online_no_location),
digital finance blocked до adapter; D: generic clarification/partial, без fake coffee task.

Initial planning budget (кандидат для U-03 measurements): максимум2proposals/run включая
repair,6предложенных/12расширенных tasks, depth4,8tool dispatches суммарно,2attempts
на transient fetch, неизменный общий deadline. Один invalid proposal допускает один repair
с safe validation codes; второй отказ → clarification/partial, не рекурсивный агент.
Identical normalized tool call не повторяется без новой версии входа или явного retry.
Resumption обновляет refs/состояние, не сбрасывает счётчики бюджета.

Extraction сохраняет384tokens. Planner требует отдельного компактного prompt/schema:
кандидат input≤3072/output≤768 при context4096, не весь DAG/история. Это **не измеренная
способность Qwen4B**, лимиты должны быть подтверждены U-03 live корпусом до включения.
Реальный output byte cap≤64KiB и H-03 timeout/queue остаются. Ни frontend, ни модель
не увеличивают лимиты. Budget превышен → partial/awaiting_user, не silent truncation.

## 4. Acquisition jobs на16GB

Выбор: durable job/task rows в той же PostgreSQL + один operator-started CLI worker из
того же API image (в будущем optional Compose profile), без Redis/Celery/broker.
API принимает bounded intent и возвращает202; worker может быть offline, UI честно queued.
Модель остаётся в единственном API процессе/H-03 queue; CLI worker **не вызывает LLM**.
Lifespan-only FastAPI BackgroundTasks без persisted state не годится для восстановления.
Отдельный broker уместен лишь после доказанной потребности в нескольких host/workers,
распределённом egress/rate limit/приоритетах; он не решает RAM одного ноутбука сам по себе.

Job={id,source_ref,territory_revision,normalized_AOI,layers,time_range,
idempotency_key,input_fingerprint,expected_active_versions,resource_policy_ref,
state,attempt,not_before,lease_owner,lease_until,fencing_token,
checkpoint,artifact_refs[],error?,created_at,updated_at}. Owner subscriptions отдельны:
общий public dataset не даёт владельцу право видеть чужой профиль/запрос.

Состояния queued→claimed→fetching→validating→importing→indexing→verifying→activating→
succeeded; ветки retry_wait/cancel_requested/cancelled/failed/recovery_required.
Public stage не обязан раскрывать имена внутренних таблиц.

Claim: короткий SELECT FOR UPDATE SKIP LOCKED + update lease/attempt/generation,
commit до fetch. Это queue-consumer приём, не consistent analytical read.
Heartbeat короткими независимыми транзакциями; result activation проверяет fencing token
и expected active version. DB connection не удерживается во время сети/LLM ожидания.
DB import batch — короткая транзакция; staging остаётся невидимым читателям до activation.

Dedup key = source/config+territory/boundary+normalized AOI/layers/time+adapter revision.
Unique active acquisition key предотвращает два imports одного scope; один job может иметь
нескольких authorized watchers. Изменённый payload с тем же owner idempotency key →409.
Data rows имеют dataset_id + OSM type/id (nodes/ways/relations не смешивать);
повтор batches UPSERT/staging checkpoint, не дубликаты между AOI. Graph IDs/topology
проверяются на швах tiles; пока это не доказано, routing только внутри квалифицированного AOI.

Новая territory сначала raw label→candidate boundaries→user confirmation при неоднозначности;
сохранить source boundary/ref/version. Для Москвы предложить район/AOI, не скачивать всю Москву.
Check local per-layer/time coverage → approved source/terms → bounded download artifact →
SHA/format/CRS/geometry/quality → batch import → spatial/category indexes → verify counts,
FK/connectivity/dedup → atomic dataset-group activation. POI+graph версии активируются
согласованным manifest, не смесь старых graph и новых POI. Старые manifests доступны.

Существующие importers atomic/locked, но `json.loads`/read_bytes и сборка walking graph
материализуют snapshot. Они подходят только bounded small extracts; обёртка job сама
не делает их streaming. U-02 должен либо доказать peak RSS маленькой tile, либо заменить
внутренний parser на incremental path с теми же нормализацией/hash/golden outputs.

Начальные **предлагаемые**, не измеренные runtime caps; lower source-policy cap всегда важнее:

| Ресурс | Кандидат U-02 / отказ |
| --- | --- |
| Import worker |1active host-wide, queue≤2; saturated→429/job_queue_full до download |
| Heavy memory class | Пока совместный peak не измерен, import и Qwen inference не одновременно. Resource-slot reservation в БД + H-03 queue; никакой второй inference queue |
| AOI |≤10km²/tile,≤4tiles/job, старый Bounds≤0,1square_degree остаётся для v1; server metric area, не площадь из model text |
| Сеть |1fetch одновременно, connect5s/read30s/total120s/attempt;2attempts total, Retry-After/source rate cap; redirect0 |
| Bytes |≤8MiB compressed/raw response tile,≤32MiB decompressed tile; incremental counters до накопления;≤128MiB/job artifacts |
| Структура |≤25Kelements/tile,≤100K/job, parser depth/tags limits, graph nodes/edges caps до построения adjacency |
| RAM/CPU |Worker512MiB hard process/container cap,1CPU; no whole-city graph in RAM. Недостаток памяти→resource_limit, smaller AOI/review |
| Диск |Staging≤512MiB/job, global staging≤1GiB, preflight free≥2GiB + estimate; final datasets отдельная quota с учётом indexes/WAL |
| Время |Job active≤10min; pause awaiting_user/data не безграничная lease; expiry/retention отдельно |

До включения: measured memory включает Python parser+normalization+graph+Postgres
indexes/WAL+Docker VM+Qwen, не только compressed archive. Если512MiB недостаточно,
уменьшить tile/streaming; не повышать лимит без записи измерений на16GB. Не держать
полигон всего мегаполиса или все city POI в prompt/React/worker adjacency.

Resource slot reservation/lease в той же БД координирует API и CLI. H-03 остаётся
однопроцессной inference queue. Deadline/lease expiry **не доказывает остановку старого
процесса**: потерявший heartbeat job становится recovery_required, host slot не освобождается
для второго heavy worker до подтверждения остановки старого supervised process.
Fencing предотвращает late publication, но не останавливает CPU старого процесса.
Fail-closed снижает доступность, зато не создаёт скрытую параллельную нагрузку.

Cancellation проверяется между chunks/batches и до activation. Partial staging не active;
cleanup только принадлежащего job private staging, после остановки worker, без удаления
исторических snapshots/volumes. Retry с checkpoint/hash; повреждённый artifact не resume.
Revoked watcher больше не получает private events; общий импорт может продолжиться только
по действующей operator/shared policy, иначе cancel. Создание новых гостей не сбрасывает
host/source/disk quotas. Не подменять текущие H-02 storage budgets собственными счётчиками.

## 5. Ограниченный tool calling / сеть

ToolRequest={tool_id,tool_revision,argument_schema_revision,arguments,run_id,
task_id,expected_run_revision,call_id}. Модель не задаёт owner, token, timeout, budget,
permissions или произвольный URL. Контекст полномочий backend добавляет сам.
ToolResult={call_id,status:ok/partial/blocked/error,result_ref?,evidence_refs[],
warnings[],error?,usage:{calls,bytes,elapsed_ms}}; bounded summary для модели,
а не полный HTML/OSM/PG result. Каждый факт ссылается на зарегистрированный evidence ID.

Пять разных фаз:

1. **Поиск:** только local approved registry на первом запуске; будущий web-search adapter
   отдельно approved/terms-tested, возвращает candidates. Он не подключён U-00 и не
   становится обязательной платной зависимостью.
2. **Получение:** approved source ID → server-owned URL template и bounded fetch.
3. **Валидация:** формат/hash/schema/license/temporal/spatial checks; недоверенный контент
   не управляет дальнейшими шагами.
4. **Сохранение:** private staging→validated immutable evidence/dataset, atomic activation.
5. **Аналитика:** только pinned validated inputs и Python/PostGIS executor.

Network broker — единственная будущая egress-точка получения внешних данных; существующий operator Overpass endpoint
не публиковать как agent argument. Правила реализации:

- HTTPS, exact approved hosts/ports/path templates; не substring/regex-host угадывание.
  URL без credentials/fragments, запрет file/data/ftp/gopher и user-supplied proxies/headers.
- DNS resolve проверяет все A/AAAA и запрещает loopback/private/link-local/multicast/
  reserved/metadata, IPv4-mapped IPv6 и неканонические IP; отказ при смешанных ответах.
- Проверка имени сама не закрывает DNS rebinding: transport должен соединяться с проверенным
  peer IP, сохраняя TLS hostname/SNI/certificate verification, или использовать доказанный
  egress enforcement. Если это нельзя подтвердить — network acquisition disabled.
- Redirects0; новые CDN hosts — отдельный operator review, не автоматическое расширение.
  Public fetcher не наследует proxy/env secrets, cookies или локальные credentials.
- Ограничения времени/bytes/decompression/content type; HTML/XML без внешних entities,
  archives без path traversal/symlink/bombs, filenames выбирает backend.

Local Ollama endpoint — отдельная admin-configured private transport boundary,
не разрешение интернет-инструментам обращаться к Docker host, PG или metadata.
Никаких shell/SQL/file-read tools. Adapter code не запускается по URL/строке модели.
Prompt injection: source text всегда data, не system message; stripped HTML не становится
trusted instruction. Модель видит compact facts с evidence refs, не активный документ.
Tool/permission/budget/consent checks выполняются независимо от её ответа.
Logs allowlist: request/run/task/call IDs, safe codes, durations, bytes; без prompts,
profile/message payloads/DSN/ключей/полных URL с query. H-05 correlation/error format сохранён.

Основания проверены28.10: [PostgreSQL17 SKIP LOCKED](https://www.postgresql.org/docs/17/sql-select.html#SQL-FOR-UPDATE-SHARE),
[OWASP SSRF](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
Для будущего geocoding нельзя считать public Nominatim универсальным сборщиком POI:
[usage policy](https://operations.osmfoundation.org/policies/nominatim/) требует соблюдения
ограничений и запрещает systematic POI extraction/autocomplete. В U-00 его не подключаем;
boundaries сначала operator-approved cached artifacts. ODbL не заменяет условия сервера.

## 6. Будущие API, ошибки и события Ви

Под auth той же гостевой сессии, owner derive из conversation, отдельные v2 DTO:

| API sketch | Семантика |
| --- | --- |
| GET/PATCH `/api/v2/conversations/{id}/profile` | ProfileV2/revision; PATCH expected_revision, явный review/confirmation |
| POST `/api/v2/conversations/{id}/profile/confirm` | expected_revision; отдельное пользовательское действие, не model patch |
| POST `/api/v2/conversations/{id}/analyses` | goals + expected_profile_revision + Idempotency-Key;202/run ref, не arbitrary tool execution |
| GET `/api/v2/conversations/{id}/analyses/{run_id}` | plan/tasks/latest bounded results/stale reasons/run_revision |
| GET `/api/v2/conversations/{id}/analyses/{run_id}/events?after=N&limit=50` | cursor sequence, authorized polling; private status, не global чужие jobs |
| POST `/api/v2/conversations/{id}/analyses/{run_id}/decisions` | confirm assumption/AOI/retry, expected_run_revision; idempotent |
| POST `/api/v2/conversations/{id}/analyses/{run_id}/cancel` | cancel intent202, не ложный мгновенный успех остановки |

v2 confirmation проверяет обязательные поля выбранных capabilities, не заставляет
online заполнять помещение. Согласие и подтверждение исходного ввода не заполняют
unknown значения. v1 confirmation rules не меняются. Idempotency-Key ограничен форматом
и длиной, привязан к owner/operation+payload hash; повтор после disconnect читает run.

Job acquisition создаёт orchestrator по validated plan/policy, не raw public endpoint,
позволяющий обходить planner quotas. Registry read API выдаёт безопасные capabilities,
не внутренние endpoints/FS/ключи. Error envelope сохраняет detail.code/message/request_id
и X-Request-ID H-05; внутренние exception/debug данные не передаются модели/браузеру.

| HTTP / code | Правило |
| --- | --- |
|401/404 owner boundary | прежняя политика скрытия чужих IDs; никаких leaked rows |
|403 consent_required/source_not_permitted | никакого fetch/write после отказа |
|409 version_conflict/plan_stale/idempotency_conflict | перечитать; не auto last-write-wins |
|413/422 existing input caps/invalid_plan/unsupported_capability | отказ до side effects; неизвестный tool — не runtime dispatch |
|429 job_queue_full/resource_budget_exceeded | запас не списан дважды; Retry-After только если известен |
|502/503/504 dependency_error/unavailable/timeout | существующие safe коды LLM и DB сохраняются; retry только transient и в общем budget |

Асинхронный task failure — состояние результата/event, не изменение уже отправленного202.
Error={code,category,retryable,stage,request_id,missing_refs[],retry_not_before?};
categories validation/permission/data/resource/dependency/conflict/cancelled/internal.
Ни failed, ни skipped не интерпретируются как числовой0.

Event={schema_version:"analysis-event-v2",run_id,run_revision,sequence,timestamp,
task_id?,stage,state,message_code,progress?:{completed,total,unit},error_code?}.
Stages checking_local_data/finding_sources/downloading/preparing_territory/
geographic_analysis/financial_calculation/recommendations/report_preparation/
completed/partial/failed/cancelled. Domain stage и техническая task phase разделены.
Монотонный sequence уникален в run; state+event записываются одной транзакцией.
Только actual work события; total=null или progress отсутствует, если denominator неизвестен.
Нельзя превратить «3из8файлов» в80%всего анализа.

U-06 сначала fetch polling2s с backoff до5s/jitter, ETag/run_revision, без token в URL;
SSE не требуется и не вводит второй auth mechanism. Cursor replay идемпотентен; старый
cursor→event_cursor_expired и reread snapshot. Retention bounded, history paginated.
Смена profile/run revision отбрасывает поздний progress/result; reload авторизует run
через прежний guest token. Его потеря остаётся потерей доступа, не silent new guest.

Mapping Ви: checking/search/download→search (будущая подзорная труба в U-06),
planning→thinking, awaiting_user→curious/neutral, calculated→idea,
report_current→success, failed→error/support, partial→uncertain с понятным ограничением.
Current frontend pending-состояния не объявляются backend events. Новых ассетов в U-00 нет.
