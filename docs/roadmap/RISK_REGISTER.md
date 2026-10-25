# Post-MVP · реестр дефектов, рисков и внешних зависимостей

25.10.2026. Реестр утверждённого roadmap, обновлён результатами F-00;
остальные исправления не начаты. Ответственный — владелец проекта, единственный разработчик.
`Подтверждено` означает код/артефакт, не новую эксплуатационную сертификацию.
P0-дефектов, **доказанных этим документационным исследованием**, не заявлено.

Обновление F-00, 25.10.2026: roadmap утверждён владельцем; подготовлен
[baseline](../baselines/F-00_BASELINE.md). Выполнен базовый backup/restore drill,
но H-01/H-04 не закрыты: нет полного DR/previous-version upgrade/encryption policy.
Ниже исторические evidence сохранены; D-04 добавлен по фактической проверке F-00.

| ID | Тип / состояние и доказательство | Последствие / приоритет | Задача и проверяемое закрытие |
|---|---|---|---|
| D-01 | Дефект модели, открыт: LLM-022 в [raw](../evals/BA-016-qwen-final.json) и repeats | Город теряется при иностранной валюте; P1 | U-04: независимые field deltas, RUB-only policy/clarification, regression + holdout + 3 real repeats |
| D-02 | Дефект модели, открыт: LLM-028 «Козани» | Ненормализованный город, пустой анализ; P1 | U-03: city registry/предложение подтверждения, no silent fuzzy match; 3 repeats |
| D-03 | Функциональный пробел, подтверждён: Finance useState, App/ReportExport lifecycle | Потеря черновика/выбора после reload/смены зоны; P1 | U-10/11: owner workspace resume и invalidation tests; отчёты BA-015 уже сохраняются, весь сценарий — нет |
| D-04 | F-00: default Alembic check exit 255, отражает extension-owned TIGER tables; scoped public check PASS | Небезопасное autogenerate-предложение удаления extension tables, P1 для миграций | H-04: фильтр extension-owned objects + TIGER fixture, не скрывающий настоящий app schema drift; до исправления проверять public scope и вручную diff, ничего не удалять |
| R-01 | Эксплуатационный риск: глобальных quotas/rate limits/semaphore в app/compose нет | Истощение ресурсов при расширении доступа; P0 при подтверждённом DoS/публичной экспозиции, сейчас P1 | H-01→H-02: bounded controlled reproducer, caps/429; до gate только loopback |
| R-02 | Код подтверждает Session.begin + DB reads → LLM → final lock; impact не измерен | Connection pool занят во время inference; P1 | H-03: отдельные read snapshot/inference/write UoW, race tests и pool measurement |
| R-03 | Partial: ProfilePatch ограничен, общий BusinessProfile/NonEmptyText без аналогичных max; body bound только reports | Неравномерные API resource limits; P1 | H-02: каждый публичный DTO/body имеет budget и negative tests, no breaking v1 без решения |
| R-04 | Поздние report checkpoints мягкие, renderer в запросе/owner transaction | Долгий запрос/lock; P1 | H-01/H-02/Q-04: измерение, bounds/cancel semantics; worker вводить лишь по доказательству |
| R-05 | Текущая нормализация/банк/гео имеют независимые версии, отраслевые refs в профиле отсутствуют | Смешение старых/новых алгоритмов после расширения; P1 | U-00/02/12: pinned bindings, immutable v1 read, explicit stale |
| R-06 | 5 geo policy groups hardcoded, finance-template один; поддержка не равна валидации отрасли | Универсальность на словах, ложные цены/рекомендации; P1 | U-01/05/06/07: capabilities + разные template inputs/limitations; unsupported честно |
| R-07 | Один реально загруженный POI dataset, частичная Казань; graph уже bbox меньше | Обещание полного города/ложное отсутствие POI; P1 | U-08/09 + Q-01: layer coverage/date compatibility; второй bounded city, не «все города» |
| R-08 | OSM полнота физически неизвестна; proxies не ground truth | Рейтинг принят за спрос/прибыль; P1 | UX-01/UI-03: explanation comprehension test, expert field review отдельно; score ≠ forecast |
| R-09 | Guest bearer token в sessionStorage, accounts/expiry/recovery отсутствуют | Потеря доступа/XSS impact; P1 для local RC, blocker public pilot | H-01/H-02, P-01/BA-020: threat model, expiry/retention decision, auth design; не переносить в localStorage автоматически |
| R-10 | Consent/audit append-only на уровне приложения, не WORM; тексты demo | Нет юридически утверждённого основания пилота; внешний blocker | P-01/BA-020/021: legal/security review и approved texts; не удалять аудит без policy |
| R-11 | Six bank products demonstration/unconfirmed/cached_only | Восприятие как действующих условий ВТБ; P1 | U-12/UI-05: demo/blocked display; действующие условия только после проверки источника/владельца |
| R-12 | Supply-chain/secret scanning не настроены CI; F-00 basic restore PASS (19 public tables/5 reports/12 receipts), без encryption/cluster DR | Неизвестные CVE; неполная recovery policy; P1 | H-04/H-06 + Q-06: scanners, populated previous-version upgrade/DR/encryption policy; F-00 не закрывает весь риск |
| R-13 | BA-016 Chromium/3 real paths; нет Firefox/WebKit/полной a11y оценки | Потеря функций на других браузерах/для screen reader; P1 | Q-02 + UI PR gates; реальные iOS/Safari проверки требуют устройства |
| R-14 | Нет soak/load/fault-restart evidence; BA-016 — небольшой serial benchmark | Неизвестные пределы, leaks/recovery; P1 | Q-04/06: 2 ч→8 ч isolated load, no external tile/Overpass load |
| R-15 | Нет реальных интервью/маржи/конверсий банка, BA-017/018 не реализованы | Недоказанный product-market/value case, дедлайн 31.10; P0 бизнес-приоритет | BA-017-* /018-*; честные evidence gaps, реальные действия владельца |
| R-16 | Визуальный live-аудит ВТБ заблокирован TLS; официального brand kit/right clearance нет | Выдуманные стандарты/ложная аффилиация; P1 | UX-03: approved references/rights; свои токены/шрифты, без bank logo до разрешения |
| R-17 | Один разработчик/4 ГБ VRAM/16 ГБ RAM, личная доступность неизвестна | Завышенный scope/сорванный срок; P1 | Лимит WIP=1, 25% reserve, scope caps, BA-017 recruitment early; RC estimate пересчитывать |
| R-18 | Overpass/public tiles best effort, лицензия не SLA; обновления надо делать заранее | Демо/импорт зависит от внешней сети; P1 | F-00/H-05/U-08: pinned snapshot + vector fallback, OSM policies; не prefetch чужие тайлы |

## Триаж и жизненный цикл записи

Новая запись: ID → reproducer/source → observed vs expected → severity → affected
version → owner/task → regression test → evidence → closed/accepted-until-date.
Исторические D-01/02 сохраняются и после исправления; не переписывать raw FAIL в PASS.
Если риск принят, указать разрешённый scope (например loopback demo), срок/условие
пересмотра и владельца. «Решим позже» без scope не закрывает P0.

На старте каждого PR проверить связанные записи; при контрольной версии — весь реестр.
Порог закрытия определяется [QUALITY_GATES](QUALITY_GATES.md), а не количеством тестов.
