# ADR-0002: локальная LLM через Ollama

Дата: 22.10.2026. Решение принято владельцем проекта в задании BA-005.

MVP использует открытую Qwen локально, без платных API, облачного inference,
обучения и дообучения. Веса не входят в Git или Docker-образ приложения.

## Модель и запуск

Выбран точный тег `qwen3:4b-instruct-2507-q4_K_M`: 4.02B, Q4_K_M,
около 2.5 GB весов, Apache 2.0. Это немного больше ориентира 3B, зато
Qwen2.5 3B распространяется под отдельной Qwen Research License.
Контекст 4096, максимум 384 выходных токена, temperature=0, один inference
одновременно на Ollama. Фактические память, задержки и ограничения — в
`../LLM_EVALUATION.md`; размер весов сам по себе не доказывает размещение на GPU.

Ollama может работать в Windows или отдельном GPU-контейнере на той же машине.
FastAPI в Compose обращается к `host.docker.internal:11434`. Для другого
inference-сервера реализуется `DialogueLLM`, для другой модели меняется конфигурация.
`LLM_PROVIDER=stub` — явный детерминированный режим для CI и демонстрации.
Автоматического переключения с неисправной модели на stub нет.

## Граница модели и домена

Модель получает компактный профиль (пять основных полей), последний вопрос ассистента
(до 500 символов) и текущее сообщение как отдельные поля JSON. Она возвращает
JSON-вызов единственного разрешённого инструмента `extract_business_profile`:
список изменений с цитатой из текущего сообщения, поле неоднозначности и намерение
`profile/analytics/unrelated`. Адаптер преобразует результат в `ProfilePatch`;
JSON Schema отправляется в Ollama, ответ повторно проверяется Pydantic и правилами
BusinessProfile на сервере. Цитаты реальных изменений проверяются на вхождение
в текущий ввод, неизменившиеся повторы состояния игнорируются. Неоднозначное поле
не записывается. Цитата не доказывает смысловую правильность нормализации моделью.
Списки предпочтений/ограничений по-прежнему доступны через PATCH; LLM пока извлекает
город, категорию, бюджет, формат и финансирование.
Дальнейшие инструменты добавляются в whitelist с собственными DTO, только в своих задачах.
SQL, shell, произвольные HTTP-вызовы и выполнение инструментов по имени из текста запрещены.

LLM понимает свободный ввод и определяет, что уточнить. Пользовательский ответ
собирается сервером из проверенного профиля/шаблонов. Это осознанное ограничение:
свободный текст модели не выводится как источник аренды, прибыли, спроса или условий ВТБ.
Аналитические сервисы BA-006 и далее не реализуются здесь. Подтверждение профиля
по-прежнему выполняет сервер: отдельный endpoint или точная фраза BA-004, не модель.
Любое реальное изменение снимает подтверждение. PATCH не требует доступной LLM.

## Состояние, ошибки и совместимость

С H-03 используются разные короткие read/write транзакции; во время inference нет
Session/connection/cursor/row lock PostgreSQL. Перед записью повторяются owner/CAS/
consent revision checks: stale inference получает409, revoked consent —403.
Все записи шага остаются одной финальной транзакцией. Ошибка модели не пишет
сообщение, профиль или историю; повтор возможен с актуальной версией.

503 `llm_unavailable`/`llm_configuration_error`, 504 `llm_timeout`,
502 `llm_invalid_response`: только код и trace_id, без текста запроса/ответа/URL.
Одна повторная попытка с задержкой 250 ms допустима для временной недоступности;
таймаут, невалидный JSON и значения не повторяются. Ответ ограничен 64 KiB,
перенаправления HTTP запрещены. Endpoint и модель задаёт администратор, не пользователь.

Ревизия `0003_llm_mode` добавляет режим извлечения в беседу: старые строки получают
`rules`. `extraction_mode` API расширяется значениями `stub` и `ollama`;
остальные endpoint/поля BA-004 сохраняются. GET возвращает последний сохранённый
ответ ассистента, включая уточнение неоднозначности, а не генерирует новый текст.

Ограничения: типовая валидация не доказывает смысловую верность извлечения;
пользователь должен проверить и подтвердить вводные. Контекст ограничен, модель
может ошибаться в сложных исправлениях/отрицаниях. Seed и temperature=0 не дают
гарантии одинаковых ответов между версиями inference runtime.

Источники: [Ollama model tag](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M),
[Chat API](https://docs.ollama.com/api/chat), [Windows](https://docs.ollama.com/windows).

## H-03 · изоляция и очередь · 26.10.2026

`message_input` читает владельца, версию, assistant consent revision, профиль и четыре
последних сообщения под короткой owner row lock. Immutable dataclass содержит только
frozen DTO/tuple, без ORM объектов/токенов. `sessionmaker.begin()` закрывает Session
до ожидания очереди/модели. Новая Session перед записью повторяет auth/CAS/consent/
quota checks и читает актуальный профиль. Даже withdraw→grant во время inference
делает старый snapshot непригодным (revision conflict). Значения повторно валидируются.

FIFO: один активный вызов и default один ожидающий, wait≤10s; конфигурация через
BA_API_LIMITS_JSON. Один процесс/asyncio loop, без Redis/Celery. POST messages сохраняет
heavy frequency budget H-02 и общий active cap8; модель ограничивается своей очередью,
не занимает два аналитических active_heavy slots. Analytics сохраняет active_heavy=2.
Queue overflow/wait timeout →429 без вымышленного Retry-After; frontend сохраняет текст.

Async capability `aextract` реализована Ollama через httpx2 **2.14.0**, уже имевшийся
в lock/dev (BSD-3-Clause), теперь runtime. Lock versions не обновлялись. Async и прежний
sync `extract` используют одни payload/schema/grounding/parser; prompt и доменные
правила не изменялись. Async stream ограничен64KiB до накопления, redirects запрещены,
environment proxy не используется. LLM_TIMEOUT_SECONDS (default120,1…180) охватывает
попытки и retry delay; cancellation закрывает клиент/HTTP stream. Sync интерфейс
оставлен для offline adapters/evaluation без БД.

HTTP disconnect отменяет ожидание/async inference и предотвращает дальнейшую запись.
Короткий DB worker получает cancellation flag; вызывающий код дожидается rollback/close.
Проверка есть до записи и после flush перед commit. Если disconnect пришёл **после
commit**, успех мог сохраниться без доставленного ответа — нужно перечитать версию;
CAS защищает повтор, exactly-once HTTP delivery не обещается. Локальный ASGI probe
получает safe499 request_cancelled; отключённый сетевой клиент обычно уже не читает ответ.

Произвольный sync adapter thread нельзя безопасно убить: результат отменённого шага
отбрасывается, но lease занят до завершения worker. Это предотвращает скрытый второй
inference; cancellable inference-server adapter должен реализовать async capability.
В штатном Ollama API path sync inference не используется. Мгновенная остановка GPU
внутри Ollama после закрытия socket не сертифицируется.

Proxy240s/browser250s учитывают queue≤30s + model≤180s + запас коротким DB phases,
не являются hard wall-clock SLA всех SQL операций. `WEB_CONCURRENCY!=1` по-прежнему
запрещён; CLI workers/replicas и прямые клиенты Ollama не координируются. Новых
таблиц/миграций/сервисов/public DTO нет. Результаты: [PERFORMANCE](../PERFORMANCE.md),
[API_LIMITS](../API_LIMITS.md).

API основания: [SQLAlchemy sessionmaker.begin](https://docs.sqlalchemy.org/en/20/orm/session_api.html#sqlalchemy.orm.sessionmaker.begin),
[HTTPX async lifecycle](https://www.python-httpx.org/async/); сигнатуры установленного
httpx2 сверены локально. Полная supply-chain проверка остаётся H-06.
