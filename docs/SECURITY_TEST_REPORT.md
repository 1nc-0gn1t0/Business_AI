# Business AI · безопасность и ранний triage

## H-03 · 26.10.2026 · transaction lifecycle и queue

Основание: H-02 PR#20 merged, main559a193503f12ca4156526c3ab86474a5fde8e2a,
чистое дерево; ветка `codex/H-03-inference-isolation`. **H01-P1-02 исправлен**:
контролируемый before1idle/1pool → after0/0, PASS после фактического XPASS.
`PERFORMANCE.md` содержит точные pg_stat_activity/pool/live measurements и методику;
не только API-коды. Нет новых P0 в выполненных сценариях.

Изолированные tests подтверждают: snapshot без ORM/открытой Session; новая write
транзакция; CAS при city/budget edits и двух сообщениях; revoke403/regrant409;
rollback после successful flush/SQL error, отсутствие новых history/messages при
отказе; owner isolation и H-02 storage quotas. Один active + один waiting, overflow/
wait timeout429 без вымышленного Retry-After; async socket deadline/cancellation,
HTTP disconnect active/queued, promotion/cancel race и повтор после ошибки/timeout.
Пять параллельных metadata reads работают с pool_size1 при blocked inference.

Регрессия: быстрые **310 PASS/95 DB SKIP** (БД выполнена отдельно), extended **102 PASS**
с1550 successful property examples, **95 PostgreSQL/PostGIS PASS, без XFAIL**;
frontend **43 PASS**, Chromium mock **24 PASS**, настоящий Qwen/browser **3 PASS/57.4s**.
Отдельный live pool probe —538 samples/27.609s, peak checked-out0 и idle transaction0.
Прежние два urllib transport mocks адаптированы к async streaming transport с теми же
assertions бюджетной безопасности; исходный полный DB run93PASS/2FAIL сохранён как
промежуточный результат, окончательный полный95PASS. Не ослаблялись tests ради CI.

Новых таблиц/миграций/public DTO/доменных алгоритмов нет. httpx2 ранее был в dev/lock,
перенесён в runtime для cancellable HTTP; версии пакетов прежние. Секреты/guest keys/
приватные snapshots не включены в evidence, ошибка БД503 не отражает SQL/sentinel.
Рабочая БД не использовалась для write tests, backup F-00 не менялся, volumes сохранены.

Ограничения: single-worker, произвольный sync thread держит lease до завершения,
direct Ollama не регулируется; отмена после commit не стирает законные записи.
Queue/connection tests не заменяют public security/pilot/8ч soak/Q-04. H-04/H-05/H-06
и старые D-01…04 остаются. Состояние PR/CI точного HEAD — HANDOFF/финальный отчёт.

## H-02 · 26.10.2026 · input/resource hardening

PR #19 merged, база `c3c8c73d92c1f63664b440faee62d69c9c5fce2e`, исходное дерево
чистое, ветка `codex/H-02-api-resource-limits`. Инвентаризация **18 write API до
изменения кода**, конфигурация, rationale, concurrency/deployment assumptions и
таблица отказов — [API_LIMITS](API_LIMITS.md). Продуктовые алгоритмы/миграции/
формат отчётов не менялись; новых зависимостей/сервисов нет.

| Finding | Статус после H-02 | Доказательство |
|---|---|---|
| H01-P1-01 | Закрыт в локальном single-worker scope | Profile/PATCH200/20; body chunks/envelope, admission и persistent stock caps; boundary/parallel/refusal-no-write tests PASS |
| H01-P2-01 | Закрыт для стандартного request-validation422 | Отсутствуют input/ctx, редактируются arbitrary keys; sentinel assertions PASS, не переносится на H-05 |
| H01-P1-02 | Подтверждён, открыт для H-03 | Controlled PostgreSQL inference probe остаётся strict XFAIL, не PASS |
| Новый P0 | Не выявлен на выполненных проверках | Не полный pentest/DoS; публичный deployment по-прежнему запрещён |

Новые проверки: Content-Length/отсутствующий/заниженный length/chunks, exact/+1 bytes,
Unicode200/201 и message4000/4001, JSON depth/nodes/collections/nonfinite/types,
версии INTEGER, fail-closed config, общий window между endpoints, concurrent active
slots, timeout release, safe422 с sentinel в имени/значении extra field. DB probes:
parallel new guests и reports с одним оставшимся global slot; профиль/messages/confirm
используют общую квоту; spy гарантирует отсутствие Qwen/renderer/mock sender при
preflight отказе; snapshot/count/version не изменены после отказов; consent revoke
доступен при полном stock/window; повтор receipt не пишет audit; owner401/404 сохранены.

Фактические прогоны: **299 PASS/83 SKIP** быстрых (DB skips выполнены отдельно),
**102 PASS** extended, включая **1550** successful Hypothesis examples с прежними seed;
**82 PASS/1 XFAIL** PostgreSQL/PostGIS, **41 PASS** frontend, **22 PASS** Chromium mock
E2E и 4 targeted повторных PASS после проверки клавиатуры/390px. Не складывать повторы
в уникальное покрытие. Полные commands — API_LIMITS и действующий CI/prek.
Первые prek: 3 environment errors из чужого `%TEMP%/pytest-of-inc`; повтор с отдельным
PYTEST_DEBUG_TEMPROOT проверяет те же assertions, без отключения тестов.

Окончательный локальный prek: **7/7 hooks PASS**, Ruff/format/mypy и ESLint/TypeScript/
build PASS, doc links/OpenAPI inventory/git diff --check PASS. Generated TypeScript
types не изменились по смыслу, formatting-only output не включён. Общая policy
расположена в трёх небольших модулях config/http/storage; размер PR оправдан одной
атомарной защитой 18 write API, тесты и operator documentation вынесены отдельно.

Compose db/api/web healthy, HTTP/API/web/PostGIS smoke PASS, migration head
`0008_analytical_reports`. Настоящая Qwen `qwen3:4b-instruct-2507-q4_K_M`, model ID
`0edcdef34593`: отдельная новая H-02 UUID-БД, oversized413 → version0 unchanged →
запрос кофейни/Казань/2млн → mode=ollama, city/category/budget корректны, version1,
history3, **22.04s** (один live smoke, не повтор BA-016 evaluation/latency benchmark).
Ollama была остановлена; запущен существующий контейнер, веса не скачивались.
Backup F-00 SHA256 `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`
неизменен. Рабочие write API для тестов не вызывались, volumes не удалялись.

Оставшиеся риски: exhaustion общей квоты доступным локальным клиентом, сеть/slow
connections до ASGI, hard compute cancellation/CPU/диск PostgreSQL, прямой Ollama
и несколько workers не защищены этой политикой; stock bytes — logical report payload.
H-03 нужен для DB connection/очереди модели, H-04 backup/restore, H-05 broader diagnostics,
H-06 supply chain. Удаление/retention/accounts не реализованы. Никакого production/pilot
approval. Exact HEAD CI/PR и окончательный prek — в PR и финальном сообщении.

Ниже сохранён исторический H-01 результат; его исходные XFAIL/counts не переписаны.

## H-01 · 25.10.2026 · результат ограниченной проверки

Основание: PR #18 merged, main `6d2cee01473cb88ad4ce0f0632436fda4a32e9c0`,
ветка `codex/H-01-early-triage`. Main синхронизирован ff-only, исходное дерево чистое.
Проверялись действующие API/services/DTO/транзакции, ADR-0001/0002/0008/0011,
релевантные разделы PROJECT_PLAN, BA-016 evidence и F-00. Остальные ADR не изменились.
Это bounded triage, не pentest, не нагрузочное тестирование и не выполнение H-02…06.

**Результат: P0 = 0 выявлено; подтверждены 2 группы P1 и 1 P2.**
Две P1 конкретизируют уже известные R-01/02/03, а не объявляют два новых exploit.
Старые D-01…04 и прочие риски не включены повторно в этот счёт. Нулевой P0 относится
только к перечисленным сценариям и не доказывает отсутствие всех уязвимостей.
Немедленного P0-fix не требуется; H-02 можно начать после разрешения владельца,
сохраняя loopback/demo scope. Публичный доступ/пилот пока недопустимы.

### Методика, результаты и воспроизведение

Только синтетические вводные, отдельные UUID-БД из integration/support.py.
Для существующих защит повторно использованы тесты BA-016, без переписывания/ослабления.
Новые проверки: 2 tests rollback после **успешного SQL flush**, 3 строгих XFAIL-пробы.
XFAIL содержит конкретный тип исключения: ошибка setup/SQL/потоков остаётся FAIL.
Исправление причины должно дать XPASS(strict), после чего удалить только метку xfail,
сохранив проверку инварианта. **XFAIL — открытая проблема, не PASS.**

| Набор | Свежий результат H-01 |
|---|---|
| Offline health/LLM/leads/reporting/backup + H-01 | 67 PASS, 2 XFAIL, 5,31 с |
| PostgreSQL conversations/leads/reports + H-01 | 25 PASS, 1 XFAIL, 40,95 с |
| Новые тесты внутри этих наборов | 2 PASS (rollback), 3 XFAIL (известные ограничения); не суммировать повторно |
| Качество PR | Новый prek: все 7 hooks PASS (Ruff/format/mypy/pytest/ESLint/TS/Vitest); CI точного HEAD — в PR |

Из корня на Windows, с установленными locked dependencies:

```powershell
$env:PYTEST_DEBUG_TEMPROOT = Join-Path $env:TEMP 'business-ai-h01-pytest'
New-Item -ItemType Directory -Force -Path $env:PYTEST_DEBUG_TEMPROOT | Out-Null
uv run --locked --project apps/api pytest apps/api/tests/test_h01_triage.py apps/api/tests/test_health.py apps/api/tests/test_llm.py apps/api/tests/test_leads.py apps/api/tests/test_reporting.py apps/api/tests/test_backup_postgres.py -q
$taskDbTests = @(
  'tests/integration/test_conversations.py', 'tests/integration/test_leads.py',
  'tests/integration/test_reports.py', 'tests/integration/test_h01_triage.py'
)
docker compose --profile test run --build --rm db-tests /app/.venv/bin/python -m pytest @taskDbTests -q -p no:cacheprovider
```

Docker Engine первоначально не был запущен (pipe not found); запущен установленный
Docker Desktop, без системных изменений. Тестовый профиль поднял существующую db и
штатный migrate. Новых инфраструктурных сервисов/volumes не добавлялось.
Ollama/GPU/live corpus не запускались: transport failures проверялись mock-транспортом,
ожидание inference — явно обозначенным controlled stub, не настоящей Qwen.

### Покрытие обязательных направлений

| Направление / гипотеза | Статус и фактическое доказательство |
|---|---|
| Чужие conversation/profile/history/messages, ID substitution | Уже покрыт существующими тестами, повторно PASS: отсутствие header 401, чужой header/UUID 404; серверный hash + constant-time comparison, не browser-only guard |
| Чужие drafts/receipts/audit, PDF/JSON | Уже покрыт, повторно PASS: owner predicate + UUID, чужая conversation/report комбинация недоступна; токен только в header |
| Чужой AnalysisRun | HTTP CRUD отсутствует в подключённых router/OpenAPI; DTO/ORM есть. Гипотеза текущего IDOR не подтверждена; обязательные ownership tests при U-10, сейчас не выдавать N/A за PASS авторизации будущего API |
| Нет assistant/demo_lead, marketing decline, отзыв/смена текста | Уже покрыт, повторно PASS: 403/409; marketing не блокирует базовые функции; отзыв во время controlled inference предотвращает запись |
| Stale draft/profile/CAS, concurrent profile/draft edits | Уже покрыт, повторно PASS: shared conversation FOR UPDATE/populate_existing, expected versions, 409; draft с изменённым профилем не отправляется |
| Повторный submit, одинаковый key одновременно, другой key | Уже покрыт, повторно PASS: одинаковая квитанция, одна submission и один audit event; конфликтующий ключ/состав — 409 |
| Receipt + submitted + audit после исключения | Новая проверка PASS: injected SQLAlchemyError **после flush**, 503, 0 persisted submissions, draft остаётся confirmed, audit неизменен |
| Profile/version/history/messages после исключения | Новая проверка PASS: SQL уже выполнен, затем исключение; профиль и история полностью совпадают с исходными, 503 |
| Неполные/невалидные профили | Уже покрыт, повторно PASS: draft сохраняется намеренно, automatic confirmation отсутствует; неполный/невалидный confirm блокируется; изменение снимает подтверждение |
| Устаревший отчёт, source changes, historical/demo disabled | Уже покрыт, повторно PASS: обычный download блокируется; historical не обходит owner/demo policy; PDF/JSON одного snapshot |
| Реальная передача в ВТБ | Текущий sender — локальный MockLeadAdapter без транспорта/URL; receipt Literal sent_to_bank=false. Соответствующие тесты PASS; банковский endpoint не вызывался |
| PostgreSQL/Ollama errors, traceback/server secrets | Повторно PASS: safe 503 / 502 / 504, code/trace ID; SQL synthetic sentinel отсутствует в response/caplog. Не доказательство безопасности любых непредвиденных исключений |
| Request-validation 422 | Подтверждён H01-P2-01: отражается только ввод самого отправителя; не server secret и не чужой токен |
| DOM/log sinks | Ключевые OSM popups используют textContent/setDOMContent, React text; опасный HTML sink не найден. App logs статические/code/trace ID, header/body logging не найден. Полный XSS/infra-log audit не проводился |
| Report/backup paths | Report UUID → DB bytes, не пользовательский filesystem path; filename генерируется из UUID. Backup — operator CLI вне HTTP, repo-storage/target/checksum tests повторно PASS; нет web-доступа к архивам |
| Размеры/накопление/повторные запросы | H01-P1-01; bounded DTO probe и код, без DoS/load. Не считать отсутствие caps подтверждённым падением сервиса |
| Занятая Qwen/транзакция | H01-P1-02: pg_stat_activity тестовой БД показывает idle-in-transaction при blocked stub; иной GET проходит. Реальное GPU queue saturation/p95 не измерены |

### H01-P1-01 · Неравномерные лимиты и отсутствие бюджета гостевых ресурсов

- **Severity / статус:** P1, подтверждён как design gap; R-01/R-03, не доказанный DoS.
- **Файлы / причина:** api/schemas.py NonEmptyText/BusinessPreferences без max;
  services/conversations.py create/update без session/message quota;
  reporting/limits.py ограничивает только POST reports. Общего API budget нет.
- **Reproducer:** `test_h01_full_profile_bounds_oversized_city` — 4096 символов в
  BusinessProfile.city принимаются. Код create допускает новые guest sessions без
  quota/TTL; lead workspace возвращает все drafts/receipts без pagination.
- **Факт / ожидание:** PATCH ограничен, но полный DTO/public stateless requests — нет;
  нужна согласованная серверная политика размеров, количества/хранения и 413/422/429.
  Это не означает, что private PATCH позволяет сохранить city 4096: он ограничен 200.
- **Последствия:** неконтролируемое накопление/CPU/память при расширении доступа;
  реальное истощение не воспроизводилось и не заявляется.
- **Предложение / задача:** H-02 — инвентаризация каждого write/stateless API, caps,
  guest/message/report budgets; без молчаливого удаления consent/audit/history.
- **Регрессия:** границы/oversized/chunked body, concurrent quota, отсутствие записи
  при отказе, защита от сброса квоты новым запросом; текущий XFAIL должен стать PASS.

### H01-P1-02 · DB-транзакция удерживается во время inference

- **Severity / статус:** P1, подтверждён; R-02. Pool starvation/реальный overload не доказаны.
- **Файлы / причина:** db/session.py Session.begin охватывает весь request;
  services/conversations.py читает профиль/историю, затем синхронно вызывает extract.
  Row lock берётся позже; отсутствие row lock не означает отсутствие транзакции.
- **Reproducer:** `test_h01_no_idle_transaction_during_inference`: Event блокирует
  controlled stub; другая connection в **той же UUID-БД** читает pg_stat_activity.
- **Факт / ожидание:** минимум одна idle-in-transaction connection сохраняется до
  завершения extract; ожидается отсутствие DB connection/transaction во время inference.
  Обычный owner GET и последующая запись прошли, потери данных не обнаружены.
- **Последствия:** риск connection pool exhaustion/долгих snapshots при очереди модели;
  semaphore/bounded queue в API отсутствуют по коду, масштаб влияния требует измерения.
- **Предложение / задача:** H-03 — read snapshot → закрытие DB → inference → новая
  транзакция с повторными owner/consent/CAS checks, bounded queue. Сейчас не реализуется.
- **Регрессия:** текущий XFAIL, edit/revoke/inference races, queue overflow и pool
  occupancy. Q-04 — нагрузочные пределы, не часть H-01.

### H01-P2-01 · Default 422 отражает пользовательский input

- **Severity / статус:** P2, подтверждён; не межсессионная утечка и не раскрытие server secret.
- **Файлы / причина:** main.py не переопределяет RequestValidationError;
  api/conversations.py обрабатывает отдельный Pydantic ValidationError без input,
  но framework request errors идут по другому пути.
- **Reproducer:** `test_h01_validation_error_omits_input`: лишнее JSON-поле со строго
  синтетическим marker, фиктивный header, unbound Session; БД не вызывается.
- **Факт / ожидание:** 422 содержит marker в detail/input; caplog и response не содержат
  traceback, marker не найден в логах. Желательна единая минимальная redacted ошибка,
  особенно для клиентов, сохраняющих response body в диагностике.
- **Последствия:** возможное повторное распространение случайно присланных чувствительных
  данных самим клиентом; реальных секретов в probe нет, чужая информация не получена.
- **Предложение / задача:** согласовать redaction в H-02/H-05 с сохранением 422 и
  совместимости error contract. Ни handler, ни публичный API сейчас не менялись.
- **Регрессия:** marker отсутствует в invalid JSON/type/extra/size errors и logs;
  исходный статус/loc/code сохраняются; строгий XFAIL удалить только после исправления.

### Ресурсная инвентаризация и границы вывода

| Уже есть | Ещё нет / дальнейшая проверка |
|---|---|
| Message 1…4000 chars; PATCH text ≤200, arrays ≤20 | Session/message lifetime quotas/TTL/общая request-body policy |
| Pagination GET messages/history/audit ≤100 | Quotas на creation; pagination/bounds lead workspace |
| Money finite, ≤18 digits/2 decimals; confirm требует positive budget | Согласованный max для общего NonEmptyText/full-profile arrays |
| Reports body 128 KiB, snapshot 4 MiB, PDF 3 MiB, 40 pages, 20 reports/conversation | Global storage quotas; report deadlines 20/30 с — checkpoints, не preemption; измерение lock/CPU — H-02/Q-04 |
| Ollama reply ≤64 KiB, predict384, ctx4096, configured timeout/retry2 | API-level bounded inference queue; настоящая busy-GPU проверка — H-03/Q-04 |
| DB connect5s / statement timeout5s | Эти лимиты не ограничивают время HTTP inference/PDF CPU; H-03/H-05 |

Не проводились: live Qwen evaluation, реальный load/DoS/soak, отключение рабочей БД,
dependency/secret-history scans, cross-browser, legal/pilot certification.
Архивный SEC-14 ниже подтверждает отдельные проверенные поля, а не наличие глобальных
resource budgets: H-01 уточняет эту границу. XFAIL сохраняются открытыми до исправления.
H-04: D-04/migration/полный DR; H-05: diagnostics/redaction; H-06: supply chain.
F-00 файлы не менялись; SHA приватного backup-02 остался
`690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
Рабочие запросы записи не выполнялись; тесты использовали только UUID fixtures.

BA-017/018 перенесены владельцем в отдельный research track, не отменены/не выполнены.
Перед UX/U потребуется отдельное решение по их зависимостям. Их плановый P0 —
бизнес-приоритет исходного backlog, не технический security blocker H-01.

## BA-016 · архивная проверка (ниже не новый запуск H-01)

25.10.2026. Проверялось только локальное приложение/изолированные фикстуры.
Никаких нагрузочных/атакующих запросов к ВТБ, Overpass или другим сторонним API.

| ID | Проверка | Результат / доказательство |
|---|---|---|
| SEC-01 | чужие conversation/draft/report UUID + отсутствующий/чужой header | PASS: conversations/leads/reports integration, 401/404 |
| SEC-02 | stale expected_version, правка во время inference, параллельные drafts | PASS: реальная PostgreSQL блокировка/409, потерянных обновлений нет |
| SEC-03 | нет отдельного demo_lead consent, отзыв/смена текста после draft | PASS: leads integration; sender не вызывается |
| SEC-04 | отказ от marketing, сохранение базового профиля/аналитики | PASS: leads integration + LeadFlow/Vitest; отдельные purpose |
| SEC-05 | duplicate submit, idempotency, audit | PASS: одна локальная квитанция, `sent_to_bank=false` |
| SEC-06 | подмена payload, profile_version, продукта/условий | PASS: leads и reports integration |
| SEC-07 | stale report/source/demo disabled/historical | PASS: reports integration; historical не обходит policy |
| SEC-08 | corrupt provider/hash/version/license/origin | PASS: providers/import tests; нет synthetic fallback |
| SEC-09 | invalid LLM JSON, tools, SQL fields, timeout/outage | PASS: test_llm; 502/503/504 и rollback state/history |
| SEC-10 | live prompt injection/выдуманные geo/финансы/кредит | PASS на 5 сценариях × 2 полных прогона; не универсальная гарантия |
| SEC-11 | отрицательная/противоречащая цитате сумма | исправлено: clarification вместо ложного +budget; unit и 2 Postgres regressions PASS |
| SEC-12 | SQLAlchemy failure: риск SQL/secret в стандартном stack logging | business API теперь возвращает 503 `database_unavailable`, безопасный log; caplog/response assertions PASS |
| SEC-13 | guest token в download URL/PDF/JSON/браузерном логе | PASS для проверенных путей: protected headers, report fixtures, download E2E; traces/HAR выключены |
| SEC-14 | ресурсные границы, NaN/Infinity/длинные строки/нулевой чек | PASS: contracts/finance/reports/LLM tests; 4000 chars в UI и API |
| SEC-15 | устаревшие/unconfirmed/retired банковские продукты | PASS: bank tests; unknown не равен matched, credit_decision=not_assessed |

Бизнес-ошибка не выдаётся за успешную операцию. Повреждённый/обрезанный ответ Qwen
не записывает частичное состояние. Противоречащая денежная цитата теперь становится
запросом уточнения в нормальном ходе; корректные независимые поля допустимо сохранить.

Отчёты содержат только вымышленные входные данные и открытые OSM-агрегаты.
Live runner исключает идентификаторы бесед, токены и полную техническую историю.
Браузерные failure screenshots относятся к искусственным сессиям; не включены в Git.

Ограничения: это regression/security testing, не независимый pentest и не юридическая
сертификация. Нет глобальных rate limits/anti-abuse, пользовательских аккаунтов,
retention/delete workflow, многопользовательской эксплуатационной проверки. Гостевой
token остаётся bearer-secret в sessionStorage и может быть похищен при будущем XSS;
React экранирует текст, но это не заменяет отдельный аудит. Не публиковать локальные
сервисы в интернет без BA-017/018 и согласования владельца.
