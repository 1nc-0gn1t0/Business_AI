# Business AI — Sab0tage

**AI-ассистент для запуска малого бизнеса и персонального подбора банковских сервисов ВТБ.** Пользователь описывает бизнес-идею, система уточняет вводные, сравнивает геолокации, показывает финансовые сценарии и предлагает релевантные услуги банка. Заявка передаётся только по отдельному согласию.

**Текущее состояние:** единый React-интерфейс → FastAPI → PostgreSQL/PostGIS: чат с локальной Qwen через Ollama, редактируемый и подтверждаемый профиль, интерактивная карта настоящих OSM-данных, зоны и их сравнение, финансовые сценарии и rule-based подбор продуктов ВТБ по явно демонстрационному каталогу. Действующие банковские условия не подтверждены; заявок и интеграции с банком нет.

## Главные документы

- **[Краткий постоянный контекст для агента](docs/PROJECT_CONTEXT.md)** — этот файл + HANDOFF можно загружать в следующую модель без расхода токенов на полную спецификацию.
- **[Полный план продукта и архитектуры](docs/PROJECT_PLAN.md)** — согласованный замысел, требования, этапы до промышленного продукта, риски, технические контракты и backlog.
- **[Актуальная передача работы](docs/HANDOFF.md)** — что сделано, где остановились, первая следующая задача.
- **[Протокол AI-разработчиков](docs/AGENT_WORKFLOW.md)** — как начинать, завершать и передавать сеанс между Codex/Claude/людьми.
- **[Пользовательский интерфейс BA-010](docs/USER_INTERFACE.md)** — сценарий в браузере, API, карта, безопасность гостевого доступа, реальные и mock-проверки, скриншоты.
- **[Каталог и подбор ВТБ BA-011](docs/BANK_CATALOGUE.md)** — источники, статус проверки, обновление, правила, защищённый API и ограничения.

## Важно

- LLM **не придумывает** данные о локации, аренде, спросе или кредитном рейтинге; она вызывает проверяемые сервисы.
- Недоступные коммерческие данные в MVP можно заменить **только явно помеченными синтетическими**.
- Оценка потребностей клиента не равна банковскому кредитному скорингу.
- До доступа к ВТБ реальные заявки и банковские интеграции не заявляются как работающие.

## Пользовательский сценарий BA-010

В браузере опишите кофейню в Казани с бюджетом 2 млн ₽. Ответьте Qwen на уточнения
или отредактируйте профиль, подтвердите его и нажмите «Найти зоны».
Карта показывает реальные OSM-объекты и модельные зоны; сравнение — серверный
рейтинг с объяснениями. Выберите зону, откройте финансовую модель, явно загрузите
демо-допущения и выполните расчёт. Изменение аренды/продаж пересчитывается API.
Демо-допущения не являются реальными ценами/спросом; оценка OSM не прогнозирует прибыль.
История беседы сохраняется после reload в той же вкладке; финансовый черновик — только в памяти.

В разделе «Продукты ВТБ» укажите добровольные потребности и выполните подбор после
подтверждения профиля. Шесть карточек охватывают РКО, регистрацию, торговый/онлайн-эквайринг,
дебетовую бизнес-карту и информацию о финансировании. Начальный каталог — **демонстрационный**:
23.10.2026 доступны индексированные официальные страницы, но прямая TLS-проверка не удалась.
Нет выдуманных тарифов или обещаний открытия/кредита. Неизвестные ответы требуют уточнения,
просроченные записи блокируются; действующие рекомендации отделены от демо-совпадений.
Каталог обновляется локальным JSON без переписывания матчера; подробности — BANK_CATALOGUE.md.

## Запуск на Windows / PowerShell

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

API беседы описан в [docs/CONVERSATION_API.md](docs/CONVERSATION_API.md): создание гостевой беседы, multi-turn сообщения, PATCH профиля, подтверждение и история. BA-005 добавляет извлечение свободного русского текста локальной Qwen. API доступен также через `/api/` на веб-порту; отдельный frontend-чат ещё не реализован. Токен доступа возвращается один раз при создании; последующие запросы требуют `X-Conversation-Token`, записи — `expected_version`.

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
docker run -d --name business-ai-ollama --gpus all -p 127.0.0.1:11434:11434 -e OLLAMA_NO_CLOUD=1 -e OLLAMA_NUM_PARALLEL=1 -e OLLAMA_MAX_LOADED_MODELS=1 -v business-ai_ollama_data:/root/.ollama ollama/ollama:0.40.8
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
uv run --locked --project apps/api python scripts/eval_local_llm.py --output local-llm-eval.json
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
