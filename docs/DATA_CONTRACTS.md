# BA-003: контракты данных и начальная схема

Канонический замысел — `PROJECT_PLAN.md`, разделы 6.1 и 11. Контракты реализованы
в `apps/api/app/api/schemas.py`, enum — в `app/domain/enums.py`, ORM — в
`app/db/models.py`. Это основание для следующих модулей; новых HTTP endpoints,
состояния диалога и вычисления аналитики BA-003 не добавляет.

## DTO

Все DTO запрещают неизвестные поля (`extra=forbid`) и присваивание полей после
создания (`frozen=True`). Вложенные JSON-словари не являются глубоко неизменяемыми:
снимки необходимо сериализовать при сохранении, а внешние данные всегда проверять
через `model_validate`/`model_validate_json`. Не использовать обходящие проверку
`model_construct`/`model_copy(update=...)` для недоверенного ввода.

- `BusinessProfile`: UUID профиля и беседы, необязательные город/категория,
  бюджет, финансирование, предпочтения и статус подтверждения. Незавершённый профиль
  допустим; полнота для запуска аналитики определяется будущим диалоговым модулем.
  Бюджет — конечный неотрицательный Decimal, до 18 цифр, 2 знака после запятой;
  JSON представляет его строкой для сохранения точности.
- `BusinessPreferences`: формат, предпочитаемые районы и ограничения. Только
  параметры бизнес-идеи, без контактных/банковских данных.
- `MetricWithProvenance`: все поля из примера ниже обязательны. `observed_at`
  допускает явный null, остальные сведения о происхождении не подставляются по
  умолчанию. Значение — конечное JSON-число, не строка/boolean. Даты должны содержать
  часовой пояс; дата наблюдения не позже даты формирования.
- `AnalysisRun`: UUID, подтверждённый типами снимок профиля, непустой словарь
  версий наборов, версия алгоритма, UUID трассировки и время создания. Этот DTO
  фиксирует входные данные, но сам не запускает анализ и не обещает его готовность.

```json
{
  "metric": "pedestrian_flow_daily",
  "value": 1800,
  "unit": "people_per_day",
  "origin": "synthetic",
  "source_name": "example_seed",
  "observed_at": null,
  "generated_at": "2026-10-20T00:00:00Z",
  "data_version": "example-1",
  "confidence": "not_applicable",
  "limitations": ["Демонстрационное значение, не измеренный трафик"]
}
```

Пример синтетический; это не сведения о конкретном городе.

`origin`: `open_data | licensed | modelled | synthetic | user_input | bank_internal`.
Никаких синонимов `real` и автоматического определения происхождения.
`confidence`: `low | medium | high | not_applicable`; это категориальная отметка,
а не измеренная вероятность. Для synthetic обязательны `not_applicable` и непустой
список ограничений. JSON round trip сохраняет метку synthetic. Название источника,
версия и ограничения должны сохраняться при дальнейшей передаче/экспорте.

`funding`: `own_funds | loan | mixed | undecided`; отсутствие ответа — null.
`confirmation_state`: `draft | confirmed`; это подтверждение вводных, а не
кредитное решение или признак полноты профиля.

## PostgreSQL и миграции

Первая ревизия Alembic — `0001_contracts`:

- `business_profiles`: типизированные основные поля и JSONB предпочтений;
  уникальный `conversation_id`.
- `analysis_runs`: независимый JSONB-снимок профиля, версии данных/алгоритма,
  трассировка и дата. Обновление живого профиля не меняет сохранённый снимок.
- `location_metrics`: ссылка на анализ (FK с каскадным удалением), UUID кандидата,
  значение и полный provenance. Origin и confidence — native PostgreSQL enums;
  NOT NULL и CHECK запрещают отсутствующий/пустой источник, неизвестный origin,
  NaN/Infinity, противоречивые даты и synthetic без ограничений.

Пока provenance хранится непосредственно с метрикой: это самодостаточная запись.
Нормализованный справочник `SourceRecord` и геосущности появятся вместе с
провайдерами/геоданными. BA-004 добавляет FK `conversation_id` к беседе в ревизии
`0002_conversations`; `candidate_id` пока без FK до появления таблицы геокандидатов.
Существующий FK метрики на анализ уже проверяется.
JSONB-снимки должны создаваться из проверенных DTO (`model_dump(mode="json")`);
БД проверяет базовый тип JSON, но не заменяет вложенную Pydantic-валидацию.

Compose сначала запускает БД, затем одноразовый `migrate` (`alembic upgrade head`),
и только после его успешного завершения — API. Обычный `docker compose up --build`
обновляет и ранее созданный volume без удаления данных. Ошибка миграции блокирует
запуск новой API-конфигурации.

```powershell
# Из корня репозитория, с работающим Compose
docker compose run --rm migrate alembic current
docker compose run --rm migrate alembic check

# Без Docker: сначала настройте PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD
uv run --locked --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --locked --project apps/api alembic -c apps/api/alembic.ini check
```

Пароли не включаются в URL или alembic.ini: используется тот же libpq PG*-контур,
что и healthcheck. Миграция обеспечивает наличие PostGIS; downgrade удаляет только
созданные таблицы и enum, сохраняя общее расширение PostGIS. Откат ревизии удаляет
прикладные данные этих таблиц, поэтому для проверки отката используются отдельные БД.

## Проверки

```powershell
uv run --locked --project apps/api pytest apps/api/tests
docker compose --profile test run --build --rm db-tests
```

Обычный pytest запускает unit/API-contract tests без БД; PostgreSQL-тесты помечаются
skip. Профиль `test` строит отдельную test-стадию Dockerfile с зависимостями из
uv.lock и запускает интеграционные проверки. Они создают случайные временные БД
с префиксом `business_ai_test_` (ранние lifecycle tests также `ba003_test_`),
удаляют только их и не откатывают БД приложения.
Локальная роль PostgreSQL из Compose имеет необходимые CREATE DATABASE/EXTENSION
права; это проверка окружения разработки, не конфигурация production-прав.

Проверяются повторный upgrade, downgrade → upgrade, `alembic check`, сохранение
PostGIS, ORM/JSON round trip всех шести origin и точность бюджета. Прямые SQL-вставки
обходят DTO, чтобы независимо проверить NOT NULL, enum, CHECK и FK в PostgreSQL.
Те же тесты выполняются в job Compose smoke в GitHub Actions.
