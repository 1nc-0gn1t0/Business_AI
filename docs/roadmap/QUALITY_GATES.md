# Post-MVP · критерии качества

Статус: **критерии утверждённого roadmap**. 25.10.2026.
Это критерии будущих задач, а не заявление об уже выполненных проверках.
Основной план: [POST_MVP_ROADMAP](POST_MVP_ROADMAP.md). Исходные результаты:
[BA-016](../TEST_MATRIX.md), [безопасность](../SECURITY_TEST_REPORT.md).

## QG-PR · минимальный PR

1. Один ID задачи, одна проверяемая цель, ссылка на риск и критерии приёмки.
2. Детерминированные тесты изменённого поведения; для дефекта — воспроизведение и
   regression assertion. Тест действительно падает при возврате дефекта, если это практически проверяемо.
3. `prek run --all-files`: Ruff/format/mypy, быстрый pytest, ESLint/TS/Vitest.
   Extended property/pairwise выполняется отдельным существующим CI-шагом.
4. Изменение SQL/ORM/транзакций → изолированные Postgres/PostGIS tests;
   миграция → upgrade с предыдущей версии на заполненной фикстуре, `alembic check`,
   повторный upgrade, совместимость предыдущего приложения на expand-стадии.
   Down-to-base на пустой БД **не заменяет** проверку сохранности данных при обновлении.
5. API → строгие DTO, стабильные error codes, negative/owner tests, генерация и diff
   OpenAPI/TS; отсутствие удалённых/переименованных v1-полей без отдельно принятой политики.
6. UI → component/API tests, изменённый путь в Chromium, клавиатура и ширина 390px;
   общие navigation/forms/download изменения → дополнительно Firefox/WebKit.
7. LLM/prompt/normalization → deterministic transport tests и выбранный live regression
   на установленной Qwen отдельно от CI; результаты нельзя заменить stub-прогоном.
8. Docs/HANDOFF, отсутствие секретов/PII в diff и артефактах, правила лицензий,
   ручная проверка diff владельцем, push, CI exact HEAD. Никакого automatic merge.

Для docs-only PR: проверка относительных ссылок, ID/зависимостей/критериев,
`git diff --check`, scope diff и обязательный prek. Повторять GPU/E2E/нагрузку ради
документации не нужно. Commit hook может выполнять более широкий быстрый набор.

Размер: желательно до 300 изменённых строк исполняемого кода, до 500 с обоснованием;
тесты/генерируемые DTO считаются отдельно, но просматриваются. Это ориентир, не повод
разбивать атомарную миграцию опасным способом. Если ревью требует более 60 минут,
разделить цель до начала реализации. Большие planning-документы — отдельное исключение.

## QG-SAFE · ранний аудит

H-01 ограничен 2 часами triage, не обещает полный pentest. Приоритеты:

| Уровень | Что означает | Правило |
|---|---|---|
| P0-дефект | подтверждённая межсессионная утечка, обход consent, потеря/подмена данных, ложная банковская отправка | остановить затронутый release; минимальный fix + regression немедленно |
| P1 | восстановление/совместимость/эксплуатация, плохой ответ без безопасного recovery | закрыть до соответствующей Beta/RC-вехи |
| P2 | локальные улучшения без нарушения инвариантов | очередь; косметика не вытесняет BA-017/018 |

Приоритет задачи в roadmap не утверждает наличие одноимённого дефекта.
Неподтверждённое подозрение сначала получает reproducer/вывод «не воспроизведено».
Результат H-01: нет открытого доказанного P0 на разрешённых сценариях **либо**
затронутая возможность выключена/ограничена локальным demo с явным blocker.
Исследовательские документы могут продолжаться независимо; небезопасное приложение
не выпускается ради даты. Не ослаблять проверки, чтобы объявить gate выполненным.

## QG-DOMAIN · данные и вычисления

- Все существенные показатели имеют source/origin/unit/version/date/limitations;
  missing отличается от 0. Synthetic confidence остаётся not_applicable.
- Нет скрытого synthetic fallback. Нельзя включать новый признак в старый score.
- Геометрии валидны; GeoJSON WGS84; метры считаются в явно заданной geography/UTM.
  Тестовые сравнения с независимыми PostGIS запросами и маленькими ручными графами.
- Недостаточное покрытие/сигнал → score/rank=null с причиной; ties стабильны.
  OSM-score сопоставим только внутри объявленной группы, не между городами/версиями.
- Сеть: bridge/crossing без общего node не соединяется; направления/access/barriers,
  disconnected components, snap connectors, разные даты POI/graph проверяются явно.
- Финансы: Decimal/единицы/округление, independent Fraction oracle, budget gap,
  ноль продаж, близкая к 1 доля затрат, отрицательный результат, sensitive inputs.
  Все v1 golden результаты остаются прежними. Никаких обещаний спроса/прибыли.
- Пользовательское source attestation не становится независимой верификацией факта.
  Банковские продукты не влияют на рейтинг или финансовую выручку.

## QG-LLM · измеримое качество диалога

Новый эталон делится на development/regression и закрытый от prompt-tuning holdout
с фиксированными IDs, отраслью/языком/валютой/городом/ambiguity strata. Нельзя просто
добавлять все неудачи в prompt и измерять качество на том же наборе.

Предлагаемые RC-пороги, утверждаемые в U-00:

- 100% критических safety cases: нет финансовых/геофактов/кредитного одобрения от LLM,
  нет неразрешённых tools, нет неподтверждённой отправки/подтверждения профиля.
- На поддержанных **однозначных** вводных holdout: ≥95% правильных новых полей,
  отдельно по city/category/budget/format/funding; не смешивать извлечение с сохранением
  уже известного значения. На критичных суммах — ни одной неверно применённой правки
  в тестовом корпусе; при неуверенности допустимо уточнение, отдельно считать его долю.
- Для ambiguity/corrections: ≥95% правильных state transitions; отсутствие безопасного
  уточнения и ложный факт считаются разными ошибками. На малой группе показывать n/N,
  не скрывать провал отрасли общей средней. Недостаточный n → «недостаточно оценки».
- LLM-022 и LLM-028 проходят явные регрессии и 3 повтора. Предлагать city-кандидата
  допустимо; автоматически менять неоднозначный город на Казань нельзя.
- Кандидатный объём: 60–100 разных диалогов/≥25 multi-turn, 15–20 новых holdout,
  минимальная полезная страта 5 случаев; это ресурсный ориентир, не quota ради PASS.
- Конфигурация/модель/prompt hash/corpus hash, per-step expectations, observed state,
  failure class, p50/p95 и повторения сохранены без credentials. Confirmation-only
  шаги не считаются новыми вызовами LLM. Stub и real публикуются раздельно.

Обычный CI остаётся без GPU/весов. Live запускается последовательно локально,
ориентировочно 2–4 часа на полный цикл с разбором, не параллельно тяжёлому импорту.
Снижение coverage/порогов ради принятия нестабильной модели требует явного решения владельца.

## QG-UX · три движка и доступность

- 3–5 основных маршрутов проходят в Chromium, Firefox и Playwright WebKit на Linux;
  без Chromium-only launch args для других движков. WebKit не доказывает работу
  настоящего Safari/iOS: отдельный ручной smoke на доступном устройстве, иначе SKIP.
- Desktop 1440, tablet 768, mobile 390, reflow 320 CSS px и zoom 200%/400% по применимым
  критериям; ни потери кнопок подтверждения, ни скрытых ошибок/согласий.
- Ориентир [WCAG 2.2 AA](https://www.w3.org/TR/WCAG22/): keyboard/focus order,
  visible/unobscured focus, contrast 4.5:1 для обычного текста, 3:1 для большого текста
  и применимых UI границ; ошибки привязаны к полю, status announcements,
  reduced-motion, names/roles, target size по 2.5.8 с учётом исключений.
- Карта имеет list/table alternative: зона выбирается, сравнивается и открывается
  без drag/hover и без интерпретации одного цвета. Графики имеют таблицу значений.
- Автоматический axe scan: 0 serious/critical на основных экранах; ручная проверка
  оставшихся правил, NVDA на Windows, клавиатура. Axe не доказывает WCAG-conformance.
- UX validation: минимум 3 реальных участника на ключевые задачи; предложенный
  критерий «≥80% задач без подсказки» считается по заданиям с n/N и наблюдениями,
  не как статистическая оценка рынка. Непонимание synthetic/score/mock — blocker UX.

## QG-QA · глубокая проверка после расширения

| Область | Метод / обязательное доказательство |
|---|---|
| DTO/API fuzz | Hypothesis valid/invalid JSON, Unicode, boundaries, nested size; fixed seeds и сохранённые shrunk cases; только isolated API |
| Mutation | mutmut в WSL/Linux, только finance/scoring/consent policy; ≥85% killed среди применимых неэквивалентных мутантов; каждый survivor классифицирован; 0 surviving critical invariant mutants |
| Integrity/concurrency | 2 owner сессии, 2 вкладки, edit/inference/revoke/submit/export races; atomic commit/replay, DB uniqueness, no partial writes |
| Sources | corrupt/hash/stale/license/version conflicts и changing active; исторические снимки не перемаркируются; no network fallback |
| Export | один snapshot в PDF/JSON, integrity/size/timeout/auth/stale; extract Cyrillic/₽; render и visual review всех страниц representative отчётов/длинных таблиц |
| Faults | остановка только isolated PostgreSQL/Ollama, timeout/invalid adapter, restart mid-operation; documented safe status + recovery, без потерь committed history |
| Supply chain | pinned dependency audit, npm audit + выбранный Python scanner, secret scan staged/full history; CVE review/исключения с владельцем и сроком; не слать .env в scanner API |
| Long-running | 2 ч сначала, 8 ч RC soak, ограниченные 1 LLM active и 5 локальных аналитических клиентов; baseline vs end memory, DB connections, recovery; не нагрузка публичных OSM/банка |

Mutation denominator/exclusions фиксируются до улучшений; `timeout`/`suspicious`
не считать killed. Новые расширения не обязаны давать «тысячи тестов»: каждый
новый класс риска должен иметь проверку и результат, повторы IDs не суммируются.

## QG-OPS · ресурсы, backup и rollback

Это **проектные цели**, не уже измеренные SLA. H-03/H-05 фиксируют методику,
Q-04 измеряет на неизменной машине/данных; при изменении окружения baseline новый.

- Warm Qwen p95 ≤15 с на коротких поддержанных запросах; cold ≤120 с или честный timeout,
  без потери текста. Одна активная inference, ограниченная очередь; overflow →429/503
  + понятный retry. Не обещать параллельную GPU-обработку на 4 ГБ.
- Geo/ranking/catchment p95 ≤2 с и finance ≤250 мс при одном клиенте на закреплённом
  Kazan snapshot; тяжёлый report ≤30 с/существующие size/page limits.
  Не сравнивать эти цели с BA-016 медианами как с измеренными p95.
- 5 небольших аналитических клиентов + 1 LLM не истощают connection pool;
  0 failed committed writes, очередь ограничена; health/диагностика доступны.
- На 8 ч soak: 0 OOM/deadlock/необработанных 5xx/целостностных ошибок; после прогрева
  нет монотонного роста working set >20% без объяснения; Docker VM сохраняет ≥1 GiB
  запаса относительно настроенного лимита, иначе уменьшить поддержанный профиль.
- Локальная RC-цель: зашифрованный backup перед миграцией/контрольной версией,
  плановый RPO ≤24 ч, проверенный RTO ≤60 мин на тестовом наборе. Это policy target,
  не обещание работы во время выключенного компьютера. Оффсайт/ключи/план пилота — отдельно.
- Restore в **новую временную БД**, Alembic head + FK/counts/hashes + чтение report/lead,
  owner isolation и smoke. Никогда не испытывать восстановление поверх рабочего volume.
- Expand/contract, предыдущий app image, immutable release digest, backup/restore fallback.
  Auto-downgrade рабочей БД запрещён; технический downgrade на фикстуре не является
  планом отката пользовательских данных. Развёртывание/rollback решает владелец.

## QG-RC · выпуск локального Release Candidate

QG-PR, SAFE, DOMAIN, LLM, UX, QA, OPS должны иметь фактические результаты на одном
release manifest. Нет доказанных открытых P0; P1 закрыты либо приняты владельцем
с ограниченным scope/сроком, без исключений из ownership/consent/provenance/mock инвариантов.
Clean install, populated migration/restore и откат приложения проверены; immutable
версии данных/образов/модели и ограничения опубликованы. Последний commit имеет
успешный CI; tag/release — отдельное решение владельца. RC не означает production-ready.
Pilot Ready требует внешних согласований, выполненного согласованного пилотного scope
BA-019/020/021 и готовности протокола/измерений BA-022. Подтверждение эффективности
самим экспериментом происходит после старта пилота, не является условием его начала.

## Источники инструментов и пределы

Проверены 25.10.2026: [Playwright browsers](https://playwright.dev/docs/browsers),
[accessibility](https://playwright.dev/docs/accessibility-testing),
[mutmut/WSL](https://mutmut.readthedocs.io/en/latest/),
[OSM tiles](https://operations.osmfoundation.org/policies/tiles/),
[Nominatim](https://operations.osmfoundation.org/policies/nominatim/).
Не вводить новые зависимости сейчас. При будущей установке проверить lock, лицензию,
совместимость Python 3.12/Node 24 и стоимость сопровождения. Hosted scanners необязательны;
функции GitHub не считать бесплатными/доступными без проверки настроек конкретного репозитория.
