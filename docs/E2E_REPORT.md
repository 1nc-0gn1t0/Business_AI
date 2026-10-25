# BA-016 · browser и интеграционные проверки

25.10.2026. Chromium/Playwright, Windows. GPU-приложение и browser renderer различаются:
карта проверяется через SwiftShader, Qwen работает на настоящей GPU/CPU.

## Offline browser

18 PASS, 0 FAIL. Три прежних сценария оставлены: общий flow, банковские потребности/
mock lead, ошибка Ollama. Добавлены REL-01…15:

- Восстановление профиля/истории без token в URL.
- 503, 504, invalid 502: сохранение текста и состояния, возможность повторить.
- Пустые геоданные без выдуманных зон; health outage; чужая сессия.
- 409 с обновлением состояния и сохранением сообщения.
- Отказ от assistant consent: POST к модели не выполняется.
- Ограничение длинного сообщения, правка профиля/повторное подтверждение, новая беседа.
- Ошибка каталога без предложений; синтетические финвводные и отказ расчёта API.
- Мобильная навигация 390px без горизонтального overflow.

Mock routes явно отделены от real; они не доказывают качество модели или БД.
Проверки `.pageerror` ловят необработанные ошибки JS; ожидаемые HTTP errors намеренные.
Первый прогон выявил неразличимые сообщения 502/504, они теперь объясняют причину.

## Настоящие сервисы

Отдельная БД `business_ai_eval_ba016`, отдельный API 8016 и Vite 4174.
Скопированы **только** geo_datasets/geo_pois/geo_districts/walk_graphs/walk_edges/
provider_datasets. Рабочие беседы, согласия, заявки, отчёты не копировались/не удалялись.
Новые E2E-сессии независимы и содержат вымышленные данные.

Сценарии: пекарня/Казань/500 тыс; автосервис/Самара/10 млн (геоданных нет);
кофейня/Казань/2 млн, полный прежний flow с walking, provider demo, пересчётом,
PDF/JSON, stale edits, отдельным согласием и локальной mock-квитанцией.
**3 PASS, 0 FAIL, 133.63 с**. Каждый путь дошёл до настоящего JSON download;
кофейня также скачала PDF, проверила stale edit/block и mock-квитанцию.
Скачанный PDF структурно прочитан pypdf:12 страниц, кириллица/маркировка synthetic;
JSON502162 bytes, без access_token/token_hash/guest_token. Полная повторная визуальная
проверка каждой страницы PDF в BA-016 не выполнялась (renderer не менялся).
Скриншоты: [desktop](screenshots/BA-016-report-export.png),
[mobile](screenshots/BA-016-report-export-mobile.png). Остальные артефакты — ignored
`apps/web/test-results/ba016-real`, исторические примеры BA-015 сохранены.

```powershell
$env:BA_TEST_API_URL='http://127.0.0.1:8016'
npm --prefix apps/web run dev -- --port 4174
# В другом терминале
$env:BA010_REAL='1'
$env:BA_TEST_WEB_URL='http://127.0.0.1:4174'
$env:BA010_ARTIFACT_DIR='test-results/ba016-real'
npm --prefix apps/web run test:e2e
```

Финансы в разных отраслях используют **явно выбранный** пример допущений кофейни,
а не отраслевые рыночные модели. UI теперь прямо сообщает об этом до загрузки.
Артефакты BA-015 больше не перезаписываются повторным real E2E.

## PostGIS и остальная регрессия

- 72 PostgreSQL/PostGIS PASS, 92.18 с, временные UUID-БД; предыдущий базовый прогон
  70 PASS/103.06 с. Новые 2 теста: отрицательный бюджет не заменяет ни None, ни старую
  положительную сумму, вопрос/история сохраняются транзакционно.
- 352 API PASS без DB; 72 SKIP затем отдельно PASS в Docker. 35 Vitest PASS.
- prek: Ruff, format, strict mypy, быстрый pytest, ESLint, TS, Vitest PASS.
- Docker Compose build/healthy db/api/web и HTTP smoke API/web/PostGIS PASS.
- Пропуск не считается PASS: Firefox/WebKit, многосуточные сессии, реальные банковские
  API, внешние провайдеры не проверялись.
