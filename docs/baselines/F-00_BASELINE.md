# F-00 · исходная версия Post-MVP

25.10.2026 (МСК). **Baseline ID: `f00-mvp-20261025-v1`.**
Приложение: `709398cb48241df3c1202b0e7c958ab73bd9c99d` — main после merge
[PR #17](https://github.com/1nc-0gn1t0/Business_AI/pull/17) в 17:34:21 UTC.
Main обновлён ff-only, divergence 0/0, исходное дерево чистое.
[CI именно этого main](https://github.com/1nc-0gn1t0/Business_AI/actions/runs/40217117052)
завершён SUCCESS. Manifest фиксирует run ID и полный head SHA.
Операторские материалы F-00 — отдельная ветка `codex/F-00-mvp-baseline`.
Фактический HEAD/PR/CI этой ветки записывается в PR и итоговом сообщении.

Это **контрольная версия локального функционального MVP с известными ограничениями**,
не Release Candidate, не публичный сервис и не банковский пилот. F-00 подготовлена
для приёмки владельцем; H-01 и BA-017/018 не выполнялись.
Предложение tag: `baseline/f00-mvp-20261025-v1`; tag/release автоматически не созданы.

## Единый manifest и границы воспроизводимости

[F-00-manifest.json](F-00-manifest.json) связывает commit, Docker image IDs/digests,
base-image digests сборки, все Python lock versions/установленные runtime packages,
Node direct dependencies/lock hashes, Alembic, алгоритмы, OSM/graph/synthetic,
модель, конфигурацию, результаты restore и SHA скачанных артефактов.
Приватный dump не входит в Git. Manifest не содержит токенов, переписки или содержимого
пользовательских отчётов. Только версии, агрегаты и хеши.

Байты всех API `.py`/миграций/requirements/alembic.ini в работающем образе совпали
с checkout. Все файлы локального `dist` совпали с файлами работающего nginx.
Поэтому тестируется указанное приложение, а не неизвестный старый контейнер.
Операторский скрипт не изменяет код приложения, DTO, финансовые формулы или миграции.

Docker tags в текущих Dockerfile остаются mutable. Manifest фиксирует **именно проверенные**
image IDs/base digests; повторный `up --build` в будущем не гарантирует тот же байтовый
образ. Для возврата сначала проверить наличие нужных IDs (`docker image inspect`)
и использовать их в локальном Compose override без пересборки; при отсутствии —
восстанавливать исходники/locks и осознанно закреплять base digests, затем перепроверять.
Image/model archives, шифрование/offsite и полноценный rollback drill остаются H-04/RC.
Оригинальный manifest не перезаписывать при следующем checkpoint: новый ID/файл.
Файловые SHA — raw bytes проверенного checkout/образа; LF/CRLF другого checkout
могут отличаться. Каноническая идентичность исходников между ОС — указанный Git commit.

## Проверенные версии

| Компонент | Версия/состояние |
|---|---|
| API/frontend package | 0.1.0; уникальная версия определяется commit + baseline ID |
| Docker / Compose | Engine 28.0.1, Linux/WSL2; Compose 2.33.1 |
| PostgreSQL / PostGIS | 17.5 / 3.5.2; действующий volume `business-ai_postgres_data` |
| Alembic | head `0008_analytical_reports`; 8 revisions, файлы/хеши в manifest |
| Python / Node / npm / uv | 3.12.15 / 24.20.0 / 12.2.0 / 0.13.1 |
| Qwen / Ollama | `qwen3:4b-instruct-2507-q4_K_M`, Q4_K_M, 4.0B / 0.40.8 |
| Model digest | `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` |
| Inference config | Ollama, ctx 4096, seed 42, temperature 0, timeout 120 с, keep_alive 10m |
| OSM | `kazan-centre`, 23 852 POI/8 полигонов, версия `44157bdc…a8447` |
| Walking | active `a63822ae…ce045`; в БД 2 версии/83 280 edges суммарно, не active-only count |
| Synthetic | `adf6964b…708dd`; только explicit demo, не рынок Казани |
| Bank catalogue | `vtb-demo-public-references-2026-10-23-v1`, демонстрационный |

Полные хеши, даты/coverage/license, версии библиотек и алгоритмов — в manifest.
Модель уже установлена: веса не скачивались и не добавлялись в Git.
`ollama ps`: 18% CPU / 82% GPU, working size 2.9 GB; это снимок размещения,
не доказательство SLA/параллельной производительности RTX 3050 Ti 4 ГБ.

## Что умеет контрольная версия

- Многотуровый русский диалог через настоящую Qwen; PostgreSQL history, ручное
  редактирование/подтверждение BusinessProfile, optimistic version checks.
- Реальные OSM/PostGIS выбранного участка Казани; кандидаты, объяснимый cohort score,
  сетевой walking/catchment с явно обозначенными snap/coverage ограничениями.
- OSM/Synthetic adapters, metadata/provenance; GHSL/Licensed честно not_integrated.
- Decimal-финансы: стартовые/постоянные/переменные затраты, 3 сценария, operating result,
  безубыточность/чувствительность. Frontend demo-template — только кофейня.
- Шесть demo продуктов ВТБ, детерминированные rules/unknown conditions;
  отдельные согласия, отзыв, preview, idempotent mock receipt и аудит.
- Owner-scoped immutable PDF/JSON snapshots, stale checks и real download;
  React/MapLibre desktop/mobile, ошибки/empty/loading.

## Новые проверки F-00

Исторические BA-016 результаты не засчитываются как новые. Команды выполнялись
из корня, без дополнительных агентов/моделей. Для pytest на Windows использован
отдельный существующий каталог `PYTEST_DEBUG_TEMPROOT` вне repo.

| Проверка | Фактический результат |
|---|---|
| `docker compose config --quiet` | PASS |
| `docker compose up --build --detach --wait --wait-timeout 180` | PASS; cache использован, db/api/web healthy; migrate exit 0 |
| `scripts/smoke.ps1` | 3/3 PASS: API health, web-proxied health/PostGIS, built React HTML/assets |
| `scripts/demo_ready.py --require-demo-data` | Сначала 5/7: explicit demo был false; после явного включения true — 7/7 PASS |
| `prek run --all-files` | Ruff/format/mypy/fast pytest/ESLint/TS/Vitest PASS; окончательный post-change запуск — в HANDOFF/PR |
| Fast API отдельно, после operator changes | 261 PASS, 72 DB SKIP, 102 extended deselected, 3,62 с; новые 11 operator tests входят в 261, не суммировать повторно |
| `pytest … -m extended --hypothesis-show-statistics` | 102 PASS, 6,17 с; 1550 passing generated examples, 0 failing; invalid draws не failures |
| `npm --prefix apps/web run build` | PASS, 5,58 с; прежнее предупреждение chunk >500 kB остаётся |
| `docker compose --profile test run --build --rm db-tests` | 72 PASS, 76,29 с; отдельные UUID databases, рабочая БД не откатывается |
| `npm --prefix apps/web run test:e2e` | 18 Chromium mock PASS, 26,9 с; явно mocked API |
| `BA010_REAL=1 … test:e2e` | 3 real Qwen/PostGIS PASS, reporter 1,2 мин; только копия `f00_restore_20261025_a1`, QA API 8017 / Vite 4175 |
| Новый `test_backup_postgres.py` | 11 PASS: dangerous/ambiguous target, repo storage, corrupt archive, one-off selection |
| Приватный backup → новый restore target | PASS; точные размеры/время ниже |
| Восстановленные существующие документы | 5 PDF/snapshot hashes PASS; 12 receipts с точной mock-формулировкой PASS |
| Новые browser downloads | 3 JSON + PDF PASS; PDF strict, 12 страниц/кириллица/synthetic; нет secret keys в JSON |
| Неизменность рабочей БД | Все public table hashes/counts, schema fingerprint, extensions/invalid indexes совпали с исходным snapshot |
| Повторный restore в существующий target | REFUSED до pg_restore, exit 1; target не перезаписан |

Real scenarios: пекарня/Казань/500 тыс; автосервис/Самара/10 млн с явным отсутствием
геоданных; кофейня/Казань/2 млн → walking/providers/финансы/банк/PDFJSON/mock receipt.
Пекарня/автосервис используют осознанно выбранный **кофейный demo-template**,
это не полноценные отраслевые финансовые модели. API ответ проверяется на extraction_mode=ollama.
Правки исходников не потребовались; приложение не переключалось на stub.

Полный live corpus BA-016, Firefox/WebKit, soak, pentest и повторная визуальная
проверка всех PDF-страниц **не выполнялись** в F-00. Renderer не менялся.

Точные команды основной регрессии F-00 (это checkpoint, не требование повторять всё
при каждом маленьком PR):

```powershell
$env:PYTEST_DEBUG_TEMPROOT = Join-Path $env:TEMP 'business-ai-f00-pytest'
New-Item -ItemType Directory -Force -Path $env:PYTEST_DEBUG_TEMPROOT | Out-Null
uv tool run --from prek==0.5.4 prek run --all-files
uv run --locked --project apps/api pytest apps/api/tests -m 'not extended' -q
uv run --locked --project apps/api pytest apps/api/tests -m extended --hypothesis-show-statistics
uv run --locked --project apps/api ruff check scripts/backup_postgres.py
uv run --locked --project apps/api ruff format --check scripts/backup_postgres.py
npm --prefix apps/web run build
npm --prefix apps/web run test:e2e
docker compose --profile test run --build --rm db-tests
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/smoke.ps1
uv run --locked --project apps/api python scripts/demo_ready.py --require-demo-data
```

Real browser проверялся отдельно: новый API на восстановленной копии с
`PGDATABASE=f00_restore_20261025_a1`, порт 8017; Vite с
`$env:BA_TEST_API_URL='http://127.0.0.1:8017'` и командой
`npm --prefix apps/web run dev -- --port 4175`. Во втором PowerShell:

```powershell
$env:BA010_REAL='1'
$env:BA_TEST_WEB_URL='http://127.0.0.1:4175'
$env:BA010_ARTIFACT_DIR='test-results/f00-real'
npm --prefix apps/web run test:e2e
```

Для повторения — новый restore target/QA-container name/свободные порты по runbook;
не использовать pristine reference copy как writable QA environment.

## Backup / восстановление

Воспроизводимые команды и safeguards: [BACKUP_RESTORE](../BACKUP_RESTORE.md).
Финальный архив: `%LOCALAPPDATA%/BusinessAI/F00-20261025-private/backup-02/database.dump`.
Родительский каталог имеет ACL только текущего пользователя. Dump **не зашифрован**,
не предназначен для пересылки/публикации; нужен encrypted storage до offsite/RC.

- Размер: **5 949 397 байт**. SHA-256:
  `690133a959640c3ee0167c46bc39eea13b966f2fff615f4158c10eda85e74feb`.
- Backup: **15,016 с**; exported repeatable-read snapshot использован и для fingerprints,
  и для `pg_dump -Fc --snapshot=…`.
- Pristine restore: **`f00_restore_20261025_a2`**, **15,093 с** вместе с верификацией.
  Это время DB drill, не измеренный RTO восстановления всего компьютера.
- Сравнены 19 public tables: counts + SHA-256 канонически упорядоченных JSONB rows,
  definitions columns/constraints/indexes, extension versions, server version;
  invalid indexes = 0. Только агрегаты/хеши опубликованы.
- Восстановлены, в частности, 50 бесед/профилей, 230 messages, 40 consents,
  12 drafts/receipts, 76 audit events, 5 reports, реальные геоданные/графы.
- Отдельный первый restore `…_a1` использован для трёх новых вымышленных QA-сессий;
  он уже не byte-equivalent исходному snapshot. `…_a2` оставлен без QA-записей.
  Оба target и оба локальных архива сохранены; рабочие записи/volumes не удалялись.

Snapshot — одной БД, не всего кластера. Roles/ACL, database/role settings (включая
search_path), tablespaces, model volume и WAL/PITR не восстанавливаются скриптом.
Проверка fingerprints ограничена public schema, не всеми TIGER-таблицами на местности;
сами extensions восстановлены pg_restore и версии сверены. Полный disaster recovery,
заполненная **предыдущая** schema version → upgrade, encryption/retention/offsite — H-04.

## Известные дефекты и условия использования

См. [живой реестр](../roadmap/RISK_REGISTER.md); F-00 не закрывает будущие H/U/Q gates.

1. D-01/02: Qwen может пропустить город при иностранной валюте и сохранить «Козани».
   RUB-only, обязательный review профиля; исправления/holdout — U-03/U-04.
2. D-03: полный workspace не сохраняется; reload теряет часть finance/выбора. Chat и
   подготовленные reports сохраняются; AnalysisRun live persistence ещё отсутствует.
3. **D-04 обнаружен F-00:** default `alembic check` exit 255 из-за видимых TIGER tables
   при `"$user", public, topology, tiger`. `PGOPTIONS=-c search_path=public` → PASS,
   no new upgrade operations. Это дефект области reflection, не разрешение удалить
   таблицы расширения. Не выполнять autogenerate без проверки; исправление — H-04.
4. Compose `exec api` при one-off QA может выбрать другой контейнер той же service.
   Новый backup tool явно выбирает единственный running non-oneoff и отказывает
   при неоднозначности; поведение воспроизведено и покрыто тестами.
5. Global quotas/rate limits/retention ещё неполны, DB connection во время LLM — риск
   без нагрузочной оценки. Только контролируемый loopback demo, не публичная экспозиция.
6. Частичное покрытие Казани, 5 geo-групп и 1 финансовый шаблон; нет достоверной
   аренды/спроса/свободных помещений, налогов/loan cashflow/payback. Score не прибыльность.
7. Условия банковского каталога unconfirmed/demo; mock receipt **не** отправка в ВТБ.
   Нет legal/brand/security approvals пилота и реальных коммерческих данных.
8. OSM/graph freshness стареет; readiness не надо обходить. В показе не зависеть от Overpass;
   public tiles требуют сети/атрибуции, собственные векторы доступны без подложки.

F-00 фиксирует честную точку сравнения с этими ограничениями. Следующие действия
назначает владелец после проверки PR; H-01 самостоятельно не начинать.
