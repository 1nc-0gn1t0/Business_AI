# BA-004: беседа и профиль

OpenAPI: http://localhost:8000/docs. API prefix: /api/v1/conversations.
Compose nginx и Vite проксируют /api/ через веб-порт. Чат реализован в BA-010.
BA-012 требует отдельное действующее согласие assistant для POST messages/PATCH/confirm.
GET истории и базовые расчёты не блокируются. Контракт: [CONSENT_LEADS.md](CONSENT_LEADS.md).
Решения: adr/ADR-0001-conversation-state.md.

| Метод | Путь относительно prefix | Назначение |
|---|---|---|
| POST | пустой | Создать беседу и профиль; access_token возвращается один раз |
| GET | /{id} или /{id}/profile | Профиль, версия, состояние, недостающие поля и ответ |
| POST | /{id}/messages | Сообщение {content, expected_version} |
| PATCH | /{id}/profile | Правка {patch, expected_version} |
| POST | /{id}/profile/confirm | Подтверждение {expected_version} |
| GET | /{id}/messages | Сообщения; offset=0, limit=50, максимум 100 |
| GET | /{id}/history | Снимки и источники изменений; та же пагинация |

Все обращения к существующей беседе требуют X-Conversation-Token с access_token.
Не передавайте его в URL, логах и публикациях. Ответ содержит profile, version,
state, missing_fields, assistant_message, extraction_mode=rules и даты. Токен/хеш
не возвращаются повторно. Версия начинается с 0, увеличивается на каждое принятое
сообщение, PATCH и подтверждение, даже без распознанной правки.

collecting — не хватает вводных; awaiting_confirmation — все пять основных полей
заполнены; confirmed — пользователь подтвердил. Изменение снимает подтверждение.
Null очищает скалярное поле; preferences=null сбрасывает предпочтения целиком.
Вложенный PATCH сохраняет неуказанные поля; списки заменяются, [] очищает их.
Идентификаторы и confirmation_state через PATCH менять нельзя.

## PowerShell-пример

```powershell
$base = 'http://localhost:8000/api/v1/conversations'
$view = Invoke-RestMethod -Method Post -Uri $base
$headers = @{ 'X-Conversation-Token' = $view.access_token }
$url = "$base/$($view.id)"
# Прочитайте текст и получите явное согласие пользователя перед PUT:
$consents = Invoke-RestMethod -Uri "$url/consents" -Headers $headers
$text = $consents.texts | Where-Object purpose -eq 'assistant'
$text.text
# Следующий запрос выполняется только после отдельного согласия:
$consentBody = @{ expected_revision = 0; text_version = $text.version; decision = 'grant' } | ConvertTo-Json
Invoke-RestMethod -Method Put -Uri "$url/consents/assistant" -Headers $headers -ContentType 'application/json' -Body $consentBody
foreach ($text in @('Хочу кофейню в Казани с бюджетом 2 млн', 'навынос', 'свои средства', 'Подтверждаю')) {
    $body = @{ content = $text; expected_version = $view.version } | ConvertTo-Json
    $view = Invoke-RestMethod -Method Post -Uri "$url/messages" -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
    $view.assistant_message
}
$body = @{ expected_version = $view.version; patch = @{ city = 'Тверь' } } | ConvertTo-Json -Depth 5
$view = Invoke-RestMethod -Method Patch -Uri "$url/profile" -Headers $headers -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
# Подтверждение снято: проверьте изменённый профиль и подтвердите его заново.
Invoke-RestMethod -Uri "$url/history" -Headers $headers
```

## Ограничения и ошибки

В BA-005 по умолчанию используется локальная Qwen через Ollama (`extraction_mode=ollama`).
Модель извлекает новые вводные/исправления из свободного русского текста и выбирает
поле для уточнения неоднозначности; сервер валидирует значения и формирует безопасный ответ.
Ни подтверждение профиля, ни аналитические инструменты моделью не исполняются.
GET возвращает сохранённый ответ, включая уточнение. PATCH сохраняет прежний контракт.

`LLM_PROVIDER=stub` включает правила BA-004 с `extraction_mode=stub`; это не LLM.
Исторические беседы до первого сообщения новой модели имеют режим `rules`.
Stub поддерживает несколько распространённых
городских словоформ/категорий, бюджет с меткой или коротким ответом на вопрос,
формат «навынос», явные фразы финансирования. Только рубли, без конвертации валют.
Для произвольных данных: «город: Тверь; бизнес: студия йоги; формат: студия» или PATCH.
Сложные отрицания/свободные исправления не гарантируются; для всех полей надёжен PATCH.
Город/категория — вводные пользователя, а не геокодирование или факты о территории.

Текстовое подтверждение: «подтверждаю», «всё верно», «все верно», «да, всё верно»
(без учёта регистра). Для незавершённого профиля вместо подтверждения — следующий вопрос.

Ошибки: 401 conversation_token_required; 404 conversation_not_found; 409 version_conflict
с current_version или profile_incomplete с missing_fields; 422 неверная схема/правка;
503 database_unavailable. BA-005 добавляет 503 llm_unavailable/llm_configuration_error,
504 llm_timeout, 502 llm_invalid_response (код + trace_id, без сырого ответа модели).
Ошибка не сохраняет сообщения/снимки/новую версию. При 409 после долгого inference
перечитайте профиль перед повтором. При ошибке Ollama нет скрытого перехода в stub.
SQL, токены, переписка и реквизиты подключения не раскрываются в ошибках БД.

Unit tests не требуют БД. Профиль `docker compose --profile test run --build --rm db-tests`
проверяет настоящий HTTP multi-turn, изоляцию, историю/пагинацию, атомарный rollback,
конкурентные правки, FK и сохранность старых профилей при миграции. Все откаты выполняются
в отдельных временных БД, не в БД приложения.
