# Business AI — Sab0tage

**Существующая установка перед обновлением H-06-FU:** не запускайте новый DB-образ
поверх старого volume. Нужен зашифрованный dump/restore в новый проект/кластер;
entrypoint намеренно откажет старому PGDATA. [Порядок обновления](docs/CONTAINER_UPGRADE.md),
[результаты и открытые риски](docs/qa/H-06-FU_CONTAINER_REPORT.md).

H-06: [supply-chain audit / открытые release-блокеры](docs/qa/H-06_SUPPLY_CHAIN_REPORT.md),
[проверки](docs/SUPPLY_CHAIN.md), [third-party notices](THIRD_PARTY_NOTICES.md).
Python/npm audits и scoped CI не означают принятие старого DB/native image baseline:
оставшиеся CRITICAL/HIGH требуют отдельного follow-up и решения владельца.

H-05: [безопасная диагностика и runbook](docs/DIAGNOSTICS.md),
[fault-injection и проверки](docs/qa/H-05_DIAGNOSTICS_REPORT.md).
`/livez` — процесс; `/readyz` — PostgreSQL/PostGIS/схема; `/healthz` сохранён.
Ошибки содержат `X-Request-ID` для поиска безопасного события в логах. Подробный
bundle по умолчанию закрыт; модель presence не подменяет настоящий inference.

**AI-ассистент для запуска малого бизнеса и персонального подбора банковских сервисов ВТБ.** Пользователь описывает бизнес-идею, система уточняет вводные, сравнивает геолокации, показывает финансовые сценарии и предлагает релевантные услуги банка. Заявка передаётся только по отдельному согласию.

**Текущее состояние:** единый React-интерфейс → FastAPI → PostgreSQL/PostGIS: чат с локальной Qwen, подтверждаемый профиль, карта OSM, сравнение зон, финансовые сценарии, rule-based подбор продуктов ВТБ и отдельные согласия с локальной mock-заявкой. Действующие банковские условия не подтверждены. Данные в ВТБ не отправляются.

## Главные документы

- **[Краткий постоянный контекст для агента](docs/PROJECT_CONTEXT.md)** — этот файл + HANDOFF можно загружать в следующую модель без расхода токенов на полную спецификацию.
- **[Полный план продукта и архитектуры](docs/PROJECT_PLAN.md)** — согласованный замысел, требования, этапы до промышленного продукта, риски, технические контракты и backlog.
- **[Актуальная передача работы](docs/HANDOFF.md)** — что сделано, где остановились, первая следующая задача.
- **[API limits и квоты H-02](docs/API_LIMITS.md)** — все write endpoints, body/DTO caps, PostgreSQL stock quotas, 413/422/429 и `BA_API_LIMITS_JSON`. Локальный Compose рассчитан на **один** API worker. Временные ограничения находятся в памяти процесса; storage quotas сохраняются в БД, новая гостевая сессия их не сбрасывает. При исчерпании лимита данные не удаляются. Не увеличивайте число workers/replicas без отдельной политики admission.
- **H-03:** очередь Qwen — один активный вызов и одно место ожидания (10s); PostgreSQL connection освобождается до очереди/inference, перед записью заново проверяются версии и согласия. Конфигурация/ошибки — в API_LIMITS, реальные pool measurements — в [PERFORMANCE](docs/PERFORMANCE.md). Многопроцессная очередь не заявлена.
- **[Утверждённый Post-MVP roadmap](docs/roadmap/POST_MVP_ROADMAP.md)** — фактический аудит, BA-017/018 до 1 ноября, универсальность, UX/UI, качество и путь к локальному RC; статус исполнения — в HANDOFF.
- **[Baseline F-00](docs/baselines/F-00_BASELINE.md)** — проверенная исходная версия, точные pins, регрессия, ограничения; [backup/restore](docs/BACKUP_RESTORE.md) без перезаписи рабочей БД.
- **[Миграции и rollback H-04](docs/MIGRATIONS.md)** — populated upgrade, TIGER-safe Alembic check, запрет рабочего downgrade; [измерения восстановления](docs/evals/H-04-migration-restore.json).
- **[Encrypted backup H-04-FU](docs/BACKUP_RESTORE.md#h-04-fu-первичная-настройка-оператором)** — age, private key custody,12h scheduler/age monitor; [реальное recovery53.157s](docs/qa/H-04-FU_RECOVERY_REPORT.md). Постоянное расписание и реальный ключ включает владелец; RPO выключенного ноутбука не гарантирован.
- **[Протокол AI-разработчиков](docs/AGENT_WORKFLOW.md)** — как начинать, завершать и передавать сеанс между Codex/Claude/людьми.
- **[Пользовательский интерфейс BA-010](docs/USER_INTERFACE.md)** — сценарий в браузере, API, карта, безопасность гостевого доступа, реальные и mock-проверки, скриншоты.
- **[Каталог и подбор ВТБ BA-011](docs/BANK_CATALOGUE.md)** — источники, статус проверки, обновление, правила, защищённый API и ограничения.
- **[Согласия и mock-заявка BA-012](docs/CONSENT_LEADS.md)** — отдельные цели, отзыв, состав заявки, версии, API и локальная квитанция.
- **[Пешеходная доступность BA-013](docs/WALKING_CATCHMENT.md)** — OSM-граф, сетевые расстояния/GeoJSON, сравнение рейтингов, измерения и ограничения.

## DESIGN-03 · познакомьтесь с Ви

Новая демонстрационная главная в банковской эстетике: три круглых элемента справа,
нижний — Ви. Нажмите его, затем «Начать с Ви»: откроется прежний рабочий маршрут.
Возврат на главную по названию Business AI сохраняет текущий проект в открытой вкладке.
Ви показывает состояние настоящих запросов, ошибки и готовность отчёта; расчёты не подменены.
Банковская навигационная композиция декоративная, авторизации и реальных банковских форм нет.
[Компоненты, ассеты и ограничения прав](docs/design/DESIGN-03_VI_MASCOT.md) ·
[реальные desktop/mobile screenshots](docs/qa/design-03/).

## DESIGN-02 · от идеи к результату

[Концепция, переходы и проверки](docs/design/DESIGN-02_MINIMALIST_FLOW.md) ·
[реальные desktop/mobile screenshots](docs/qa/design-02/).
Один вопрос → короткий AI-диалог → подтверждение → карта/выбор зоны →
финансовые сценарии → добровольный банковский подбор → PDF/JSON.
Без постоянной боковой навигации; подробности доступны на нужном шаге.
Белый фон, синие акценты, локальный Golos Text; адаптация1440/768/390.
MapLibre загружается при переходе к локациям. Все результаты через прежние API;
синтетика и демонстрационные банковские операции явно обозначены.
При reload восстанавливаются профиль/история, анализ нужно повторить.
Для совместимого работающего backend8000: `npm --prefix apps/web ci`,
`npm --prefix apps/web run dev -- --port 5174 --strictPort`.
Это хакатонный приоритет, не принятие открытой security release baseline.
Не обновляйте рабочий DB-volume этим запуском; предупреждение H-06-FU сохраняет силу.

## Важно

- LLM **не придумывает** данные о локации, аренде, спросе или кредитном рейтинге; она вызывает проверяемые сервисы.
- Недоступные коммерческие данные в MVP можно заменить **только явно помеченными синтетическими**.
- Оценка потребностей клиента не равна банковскому кредитному скорингу.
- До доступа к ВТБ реальные заявки и банковские интеграции не заявляются как работающие.

## Пользовательский сценарий BA-010

Опишите кофейню в Казани. Перед первой отправкой отдельно согласитесь на использование
ассистента. Ответьте на короткие уточнения, подтвердите параметры и нажмите «Найти локации».
Карта показывает реальные OSM-объекты и модельные зоны; сравнение — серверный
рейтинг с объяснениями. Выберите зону, откройте финансовую модель, явно загрузите
демо-допущения и выполните расчёт. Изменение аренды/продаж пересчитывается API.
Демо-допущения не являются реальными ценами/спросом; оценка OSM не прогнозирует прибыль.
История беседы сохраняется после reload в той же вкладке; финансовый черновик — только в памяти.

На шаге «Что поможет вашему бизнесу?» укажите добровольные потребности и выполните подбор после
подтверждения профиля. Шесть карточек охватывают РКО, регистрацию, торговый/онлайн-эквайринг,
дебетовую бизнес-карту и информацию о финансировании. Начальный каталог — **демонстрационный**:
23.10.2026 доступны индексированные официальные страницы, но прямая TLS-проверка не удалась.
Нет выдуманных тарифов или обещаний открытия/кредита. Неизвестные ответы требуют уточнения,
просроченные записи блокируются; действующие рекомендации отделены от демо-совпадений.
Каталог обновляется локальным JSON без переписывания матчера; подробности — BANK_CATALOGUE.md.

Под каталогом — заключительный шаг BA-012: выбор продуктов, исправление/исключение полей,
отдельное согласие на подготовку демо-заявки, сохранение и подтверждение состава.
Маркетинговое согласие можно отклонить. Финальное отдельное действие создаёт квитанцию:
**«Демонстрационная заявка создана. Данные в ВТБ не отправлены»**.
После изменения профиля/согласия черновик нужно обновить и подтвердить заново.
Согласия, их отзыв и квитанции сохраняются в PostgreSQL. Тексты демонстрационные,
не документы ВТБ; перед пилотом нужна правовая проверка.

## Запуск на Windows / PowerShell

BA-013: в разделе «Пешком по дорожной сети» выберите точку/зону/координаты, задайте
бюджет и рассчитайте достижимые линии/POI. Граф загружается отдельно по инструкции
WALKING_CATCHMENT.md. Без него прежние карта/скоринг/финансы работают, а маршруты
не подставляются. Можно явно найти новую группу зон внутри дорожного покрытия.
Сетевой рейтинг — отдельный opt-in режим; соединители к сети модельные.

Нужны Git и Docker Desktop с Linux containers и WSL2 backend (включите WSL2 в настройках Docker Desktop). Для запуска контейнеров локальные Python и Node.js не требуются. Команды выполняются из корня репозитория.

```powershell
git clone https://github.com/1nc-0gn1t0/Business_AI.git
cd Business_AI
docker version
docker compose up --build
```

Если репозиторий уже клонирован, начните с перехода в его папку. В `docker version` должна отображаться секция Server. При ошибке соединения запустите Docker Desktop и дождитесь готовности движка.

Первый запуск скачивает образы и зависимости. Compose ждёт готовности БД и API. После запуска:

- Приложение: http://localhost:5173 — чат, карта, сравнение зон и финансовая модель.
- API readiness: http://localhost:8000/healthz — `200` с версией PostGIS либо `503`, если БД/расширение недоступны.
- OpenAPI: http://localhost:8000/docs.

Frontend обращается к `/healthz` на своём origin, nginx проксирует запрос к API. PostgreSQL доступен только внутри сети Compose; HTTP-порты привязаны к loopback компьютера.

`.env` необязателен: для локального запуска предусмотрены демонстрационные значения. Для других портов/локальных реквизитов скопируйте `.env.example` в `.env` и измените его. Это окружение разработки, не production-конфигурация. Не используйте демонстрационный пароль вне локальной машины. Переменные `POSTGRES_*` инициализируют БД только при первом создании volume: изменение пароля в `.env` не изменяет уже созданного пользователя PostgreSQL.

```powershell
# В другом окне PowerShell, после запуска
docker compose ps
powershell -NoProfile -File scripts/smoke.ps1

# Фоновый запуск с ожиданием готовности
docker compose up --build --detach --wait --wait-timeout 180

# Остановить сервисы, сохранив данные
docker compose down
```

Если порты заняты, задайте `API_PORT`/`WEB_PORT` в `.env`. Для smoke-проверки нестандартных портов:

```powershell
powershell -NoProfile -File scripts/smoke.ps1 -ApiUrl http://127.0.0.1:8001 -WebUrl http://127.0.0.1:5174
```

В WSL2 команды Docker выполняются так же, если включена интеграция дистрибутива в Docker Desktop. PowerShell smoke-скрипт запускайте с Windows или через `pwsh`, если он установлен в WSL.

## Локальные проверки и разработка

Для работы вне контейнеров нужны Node.js 24 LTS, `uv` и `prek`. `uv` подбирает Python 3.12. Зависимости зафиксированы в `apps/api/uv.lock`, `apps/api/requirements.txt` (экспорт для Docker) и `apps/web/package-lock.json`.

```powershell
uv sync --locked --project apps/api
uv run --locked --project apps/api pytest apps/api/tests
uv run --locked --project apps/api ruff check apps/api
uv run --locked --project apps/api ruff format --check apps/api
uv run --locked --project apps/api mypy --config-file apps/api/pyproject.toml apps/api/app apps/api/tests apps/api/migrations
npm --prefix apps/web ci
npm --prefix apps/web run lint
npm --prefix apps/web test
npm --prefix apps/web run build
prek run --all-files
```

При изменении Python-зависимостей обновляйте lock и экспорт вместе:

```powershell
cd apps/api
uv lock
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt --output-file requirements.txt
```

Для frontend с hot reload при запущенном Compose: `npm --prefix apps/web run dev`. Откройте адрес, напечатанный Vite (если 5173 занят, он выберет следующий порт). `/healthz` проксируется к API на `127.0.0.1:8000`; при смене API-порта измените локальную настройку `apps/web/vite.config.ts`.

## CI и проверки перед коммитом

`.github/workflows/ci.yml` запускается при push в любую ветку, PR в `main` и вручную через GitHub Actions. Job `Checks` выполняет одни и те же prek-проверки на Ubuntu и Windows (Python 3.12, Node.js 24, uv 0.13.1, prek 0.5.4), проверяет соответствие Docker requirements lock-файлу и собирает frontend. Job `Compose smoke` на Ubuntu собирает контейнеры, применяет миграции, ждёт готовности сервисов, проверяет HTTP и запускает интеграционные тесты БД. При ошибке сохраняет диагностику в логах job, затем удаляет тестовое окружение. Внешние LLM/банковские ключи не нужны.

`prek run --all-files` запускает Ruff lint/format, строгий mypy для API/миграций/тестов, pytest без БД, ESLint с правилами React Hooks, TypeScript и frontend unit/API-тесты с mock-ответами. Ubuntu CI дополнительно выполняет mock-сценарий в Chromium. Зависимости сначала установите командами выше. Для установки автоматической проверки перед каждым коммитом:

```powershell
# Если prek ещё не установлен
uv tool install prek==0.5.4
prek install
```

В CI используется закреплённый `uv tool run --from prek==0.5.4 prek run --all-files`. Полная сборка и Compose smoke выполняются отдельно от commit hook. Проверки Actions сами по себе не настраивают защиту ветки или обязательность checks для merge.

## Структура и продолжение

- `apps/api`: API, проверка БД, тесты, зависимости и Dockerfile.
- `apps/web`: React/TypeScript, Vite и nginx-конфигурация.
- `infra/docker`: многоэтапная сборка frontend.
- `scripts/smoke.ps1`: проверка API, PostGIS и собранной страницы через HTTP.
- `data/synthetic`, `docs/adr`: места для будущих данных и решений.

Контракты `BusinessProfile`, `MetricWithProvenance`, `AnalysisRun` и первая Alembic-ревизия описаны в [docs/DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md). Compose выполняет `migrate` до старта API. Интеграционные тесты миграций и ограничений запускаются отдельно:

```powershell
docker compose --profile test run --build --rm db-tests
```

Обычный pytest не требует БД и пропускает эти integration tests. Тестовый профиль создаёт отдельные временные базы; основная БД приложения не откатывается.

API беседы описан в [docs/CONVERSATION_API.md](docs/CONVERSATION_API.md): создание гостевой беседы, multi-turn сообщения, PATCH профиля, подтверждение и история. BA-005 добавляет извлечение свободного русского текста локальной Qwen. API доступен через `/api/` на веб-порту. BA-012 требует отдельное действующее согласие `assistant` перед записью сообщений/профиля; см. CONSENT_LEADS.md. Токен доступа возвращается один раз при создании; последующие запросы требуют `X-Conversation-Token`, записи — `expected_version`.

Решения о состояниях, подтверждении и защите от конфликтующих правок: [ADR-0001](docs/adr/ADR-0001-conversation-state.md). Новая ревизия `0002_conversations` сохраняет ранее созданные профили и добавляет историю/сообщения.

## Геоданные OpenStreetMap/PostGIS (BA-006)

Настоящие POI и административные границы загружаются ограниченным snapshot через
Overpass, сохраняются в PostGIS и читаются через `/api/v1/geo/` без LLM и внешних
запросов. Есть категории, bbox, радиус в метрах, районные фильтры и версии для пагинации.

Пошаговые команды Windows/Docker для загрузки, повторного импорта и обновления,
источники, лицензия, примеры API и реальные измерения:
**[docs/GEO_DATA.md](docs/GEO_DATA.md)**. Решения: [ADR-0003](docs/adr/ADR-0003-osm-snapshots.md).
Импорт выполняется отдельно от старта Compose, поэтому чистый запуск/CI не зависят
от Overpass. Без импорта список `/api/v1/geo/datasets` пуст; координаты не подставляются.

Кеш содержит точный запрос, SHA256, дату OSM и загрузки. Обновление атомарное,
старые версии сохраняются. Геослои включают ODbL/© OpenStreetMap contributors
и ограничения покрытия. Коммерческих метрик, трафика или спроса здесь нет.

## Локальная Qwen через Ollama (BA-005)

Облачные LLM API, ключи и обучение не требуются. Выбран точный тег
`qwen3:4b-instruct-2507-q4_K_M` (4.02B, Q4_K_M, около 2.5 GB весов, Apache 2.0).
Веса хранятся в Ollama, не в репозитории. Контекст по умолчанию 4096, ответ до 384 токенов.
Реальные результаты на RTX 3050 Ti 4 GB: [LLM_EVALUATION](docs/LLM_EVALUATION.md).

Вариант 1 — Ollama в Windows: установите [официальный Ollama](https://ollama.com/download/windows),
затем загрузите **одну** модель:

```powershell
ollama pull qwen3:4b-instruct-2507-q4_K_M
ollama list
```

Для доступа из Docker закройте Ollama в tray и запустите сервер в отдельном PowerShell:

```powershell
$env:OLLAMA_HOST = '0.0.0.0:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
ollama serve
```

Переменные здесь действуют только в этом окне. Не открывайте порт Ollama в интернет:
у API нет авторизации. Не меняйте firewall автоматически; доступ к серверу должен
быть ограничен локальной машиной/Docker. Если Windows блокирует соединение,
можно использовать контейнерный вариант ниже с привязкой порта к loopback.

Вариант 2 — Ollama в отдельном контейнере Docker Desktop/WSL2 с NVIDIA GPU
(именно этот вариант используется для локальной проверки BA-005):

```powershell
docker run -d --name business-ai-ollama --gpus all -p 127.0.0.1:11434:11434 -e OLLAMA_NO_CLOUD=1 -e OLLAMA_NUM_PARALLEL=1 -e OLLAMA_MAX_LOADED_MODELS=1 -v business-ai_ollama_data:/root/.ollama ollama/ollama:0.40.11@sha256:dea72d1e22270fe095b68fdf756d2b489d615643c5a2eaebbc5f569181e322d8
docker exec business-ai-ollama ollama pull qwen3:4b-instruct-2507-q4_K_M
# При следующем запуске существующего контейнера:
docker start business-ai-ollama
```

Не запускайте оба варианта одновременно на одном порту. Не удаляйте volume с весами.
Для контейнерного варианта нужны рабочий NVIDIA driver и GPU support Docker Desktop.

Настройки API в `.env` (пример в `.env.example`):

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:4b-instruct-2507-q4_K_M
LLM_TIMEOUT_SECONDS=120
OLLAMA_NUM_CTX=4096
```

Для API вне Docker используйте `OLLAMA_BASE_URL=http://127.0.0.1:11434`.
После изменения `.env` пересоздайте API командой `docker compose up --build --detach --wait`.
Затем выполните:

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/tags
docker compose up --build --detach --wait
# Пример API с сообщениями, токеном и подтверждением — docs/CONVERSATION_API.md
uv run --locked --project apps/api python scripts/eval_local_llm.py --consent-to-local-evaluation --output local-llm-eval.json
# GPU-размещение после реального сообщения:
docker exec business-ai-ollama ollama ps
```

Eval создаёт анонимные тестовые беседы в БД приложения и проверяет сохранение
профиля/истории; его JSON не содержит токенов. Не добавляйте личные переписки в Git.
`/healthz` проверяет БД/PostGIS, а не загруженную модель. Проверка Ollama — реальный
POST `/messages` и `extraction_mode=ollama`; доступный `/api/tags` сам по себе недостаточен.

Для CI/демо без модели явно задайте `LLM_PROVIDER=stub`. Интеграционный test-профиль
Compose уже использует stub: GPU, Ollama и веса ему не нужны. В stub понимаются
только правила BA-004; это не настоящая LLM. При сбое Ollama скрытого fallback нет:
503 — недоступность/конфигурация, 504 — таймаут, 502 — некорректный ответ;
профиль и история не меняются. PATCH и явное подтверждение доступны без LLM.

Решение и границы инструментов: [ADR-0002](docs/adr/ADR-0002-local-llm.md).
Перед разработкой прочитайте `docs/HANDOFF.md` и релевантный раздел плана.
Генерация географических зон BA-007: `POST /api/v1/geo/{slug}/candidates`.
Контракт, ограничения, команды проверки и реальные примеры кофейни в Казани —
[CANDIDATE_ZONES.md](docs/CANDIDATE_ZONES.md), решение —
[ADR-0004](docs/adr/ADR-0004-candidate-zones.md).
Зоны не являются объявлениями о свободных помещениях; коммерческого scoring пока нет.
Ранжирование BA-008: `POST /api/v1/geo/{slug}/rankings`. Метрики, веса,
нормализация, пропуски и реальные сравнения — [ZONE_RANKING.md](docs/ZONE_RANKING.md).
Это сравнительный рейтинг картированного окружения, не прогноз прибыльности.
Без полного радиуса наблюдения или необходимых данных балл не выдаётся.
Финансовое ядро BA-009: `POST /api/v1/finance/calculate` — Decimal, три сценария,
безубыточность, бюджет и чувствительность. Все демо-расходы/продажи — явные
редактируемые допущения. Контракт, формулы и пример кофейни с бюджетом 2 млн ₽ —
[FINANCE_ENGINE.md](docs/FINANCE_ENGINE.md). OSM-score не влияет на финансовые числа.
Следующая задача после принятия BA-009 — BA-010, только по разрешению владельца.

## Источники и демонстрационные показатели (BA-014)

Панель «Источники и происхождение показателей» на карте показывает версионированные
OSM-агрегаты и отдельно — явно выбранный синтетический сценарий. Demo по умолчанию
отключён (`DATA_DEMO_ENABLED=false`); включение требует серверного флага, отдельного
импорта `data/synthetic/coffee-kazan-v1.json` и выбора demo в интерфейсе.
GHSL/коммерческие адаптеры пока не подключены. Пропуски не заменяются синтетикой,
рейтинги BA-008/013 и финансы BA-009 не меняются автоматически.
Команды запуска, импорта/обновления, API и ограничения: [DATA_PROVIDERS.md](docs/DATA_PROVIDERS.md).
Для полного реального e2e теперь нужен также импортированный demo-набор и явный флаг.

## Аналитический отчёт (BA-015)

Панель «Скачать отчёт» формирует PDF и JSON из одного проверенного снимка с версиями,
источниками и ограничениями. Экспорт не отправляет заявку в банк. После изменения
вводных нужно пересчитать анализ и обновить отчёт. Пропуски и синтетика явно отмечены.
API, ограничения и воспроизводимость: [REPORT_EXPORT.md](docs/REPORT_EXPORT.md).
Примеры: [PDF](docs/examples/BA-015-kazan-coffee.pdf),
[JSON](docs/examples/BA-015-kazan-coffee.json). PDF работает офлайн, со встроенным шрифтом.

## Проверки качества и стабильное демо (BA-016)

[TEST_MATRIX](docs/TEST_MATRIX.md) — покрытие и команды отдельных групп;
[LLM_EVALUATION](docs/LLM_EVALUATION.md) — настоящая Qwen и оставшиеся ошибки;
[E2E_REPORT](docs/E2E_REPORT.md), [SECURITY_TEST_REPORT](docs/SECURITY_TEST_REPORT.md),
[PERFORMANCE](docs/PERFORMANCE.md), [DEMO_GUIDE](docs/DEMO_GUIDE.md).

```powershell
uv tool run --from prek==0.5.4 prek run --all-files
uv run --locked --project apps/api pytest apps/api/tests -m extended --hypothesis-show-statistics
uv run --locked --project apps/api python scripts/demo_ready.py --require-demo-data
```

Extended: pairwise12отраслей/6городов/6бюджетов и1550Hypothesis examples с фиксированными
seed. CI не запускает live LLM. Для массовой live-оценки используйте отдельный
localhost:8016/тестовую БД по DEMO_GUIDE, `scripts/eval_product_llm.py`, корпус
`tests/evaluation/qwen-v2.json`; не рабочие пользовательские диалоги.
Readiness сверяет `data/demo-manifest.json`, но наличие модели не заменяет реальный
ответ с extraction_mode=ollama. Источники заранее загружены; Overpass в демо не нужен.
Отрицательная/противоречащая цифровой цитате сумма вызывает уточнение; пользователь
всё равно должен проверить город/сумму до подтверждения. Финансовый demo-template —
пример кофейни, не отраслевая модель произвольного бизнеса.
