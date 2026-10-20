# Business AI — Sab0tage

**AI-ассистент для запуска малого бизнеса и персонального подбора банковских сервисов ВТБ.** Пользователь описывает бизнес-идею, система уточняет вводные, сравнивает геолокации, показывает финансовые сценарии и предлагает релевантные услуги банка. Заявка передаётся только по отдельному согласию.

**Текущее состояние:** создан технический скелет `BA-001`: React → FastAPI `/healthz` → PostgreSQL/PostGIS. Бизнес-функции, AI-диалог, карта и банковские интеграции ещё не реализованы.

## Главные документы

- **[Краткий постоянный контекст для агента](docs/PROJECT_CONTEXT.md)** — этот файл + HANDOFF можно загружать в следующую модель без расхода токенов на полную спецификацию.
- **[Полный план продукта и архитектуры](docs/PROJECT_PLAN.md)** — согласованный замысел, требования, этапы до промышленного продукта, риски, технические контракты и backlog.
- **[Актуальная передача работы](docs/HANDOFF.md)** — что сделано, где остановились, первая следующая задача.
- **[Протокол AI-разработчиков](docs/AGENT_WORKFLOW.md)** — как начинать, завершать и передавать сеанс между Codex/Claude/людьми.

## Важно

- LLM **не придумывает** данные о локации, аренде, спросе или кредитном рейтинге; она вызывает проверяемые сервисы.
- Недоступные коммерческие данные в MVP можно заменить **только явно помеченными синтетическими**.
- Оценка потребностей клиента не равна банковскому кредитному скорингу.
- До доступа к ВТБ реальные заявки и банковские интеграции не заявляются как работающие.

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

- Веб-страница: http://localhost:5173 — показывает результат проверки API и PostGIS.
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

`prek run --all-files` запускает Ruff lint/format, строгий mypy для API/миграций/тестов, pytest без БД, ESLint с правилами React Hooks и TypeScript. Зависимости сначала установите командами выше. Для установки автоматической проверки перед каждым коммитом:

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

Перед разработкой прочитайте `docs/HANDOFF.md` и соответствующие разделы `docs/PROJECT_PLAN.md`. Следующая задача после проверки и слияния `BA-003` — `BA-004` (состояние диалога и извлечение профиля). Переход — только по разрешению владельца проекта.
