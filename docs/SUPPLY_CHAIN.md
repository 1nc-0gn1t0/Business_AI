# H-06 · воспроизводимый аудит зависимостей

H-06-FU: [обновление контейнеров](CONTAINER_UPGRADE.md),
[новые сканы и перенос](qa/H-06-FU_CONTAINER_REPORT.md). Старые H-06 результаты
ниже исторические; оставшиеся native Critical/High не приняты автоматически.

[Отчёт/открытые блокеры](qa/H-06_SUPPLY_CHAIN_REPORT.md),
[лицензии и obligations](../THIRD_PARTY_NOTICES.md),
[машинная инвентаризация](qa/H-06-dependencies.json).

Проверки выполняются локально или в read-only-permissions CI; никаких платных API.
Python/npm advisory services получают package names/versions. Не передавать им .env,
исходники, пользовательские данные или архивы. Secret/image сканеры работают локально.

## Package audit и чистая установка

```powershell
uv sync --locked --project apps/api
npm --prefix apps/web ci
$auditRequirements = Join-Path $env:TEMP 'business-ai-audit-requirements.txt'
uv export --locked --project apps/api --no-emit-project --format requirements-txt --output-file $auditRequirements
uv tool run --from pip-audit==2.10.1 pip-audit --require-hashes --no-deps --disable-pip --strict -r $auditRequirements
npm --prefix apps/web audit --audit-level=low --registry=https://registry.npmjs.org
```

Full export включает dev packages; platform markers соблюдаются. Не добавлять
--ignore-vuln/--omit=dev ради зелёной проверки. Ошибка сети/невозможность разрешить
package не считается0 vulnerabilities. Запись исключения требует ID, версии,
конкретной достижимости, владельца, явного approval и даты окончания; сейчас
**одобренных исключений нет**. Image findings не игнорируются package-командами:
они остаются отдельным непринятым release baseline в отчёте.

Для настоящего clean install используйте новый UV_PROJECT_ENVIRONMENT вне repo и
новую папку npm с копиями package.json/package-lock.json, затем те же locked install.
Не удалять рабочие node_modules/.venv/volumes ради проверки. Условия lifecycle scripts
npm фиксировать отдельно; Vite/Compose build подтверждает фактическую сборку.

## Secret scan и positive fixture

```powershell
$gitleaks = ./scripts/install_gitleaks.ps1 -Directory (Join-Path $env:TEMP ('gitleaks-'+[guid]::NewGuid().ToString('N')))
uv run --locked --project apps/api python scripts/check_secret_scanner.py --binary $gitleaks
& $gitleaks git . --log-opts='--all --full-history' --config .gitleaks.toml --ignore-gitleaks-allow --redact=100 --no-banner
& $gitleaks dir . --config .gitleaks-dir.toml --ignore-gitleaks-allow --redact=100 --no-banner
```

История должна быть non-shallow; для CI fetch-depth0. Strict Git policy не исключает
никакие пути. Directory policy исключает только установленную .venv/node_modules и
Git object storage; dist/.env/fixtures сканируются. Не подменять Git policy directory
policy: случайно закоммиченный секрет внутри dependency path тоже должен обнаружиться.
Self-test создаёт только временные синтетические, неработоспособные PAT/age/DSN;
проверяет detection и redaction без печати marker values. Он не создаёт реальные keys.
Inline gitleaks:allow не разрешает пропуск: --ignore-gitleaks-allow проверяется fixture.
Не добавлять .gitleaksignore без отдельной политики/approval; regression gate его запрещает.

### U02-FP-001 · 29.10.2026

Первый U-02 commit `c704abbd107e649f4e7c558deb982a3228ba19f0` вызвал
`generic-api-key` на фиксированном синтетическом pytest-токене в
`apps/api/tests/integration/test_acquisition.py`. Значение устанавливалось только
временным monkeypatch в тестовом процессе; рабочим credential оно не являлось.
Новые тесты используют случайный временный токен. История не переписывалась.

В `.gitleaks.toml` зарегистрировано rule-scoped AND-исключение для точных commit,
пути и значения; default detector сохранён. Это не исключение файла, всего commit
или всех тестовых ключей. Владелец: repository maintainer; повторная проверка до
28.11.2026. `.gitleaksignore` и глобальные исключения истории не добавлены.
`scripts/check_secret_scanner.py` в изолированном Git fixture проверяет, что другое
значение в том же файле, то же значение в другом файле и другом commit остаются
находками, а вывод полностью редактируется. Pinned Gitleaks8.30.1: self-test,
reachable history и directory scan PASS локально; exact-HEAD CI — в отчёте PR.

Результаты с находками не публиковать: сначала вывести только rule/file/line, проверить
секрет в контролируемой среде, сообщить владельцу о ротации при реальной утечке.
Удаление строки не отзывает ключ; не переписывать Git history/force push автоматически.
Raw reports, identity files, docker inspect environment и verbose registry errors не
должны становиться CI artifacts. Сканер не является OCR/полной проверкой бинарных данных.

## Image audit

В H-06 использован официальный Trivy0.76.1 Windows x64 ZIP с SHA256
`1051f49cb22d5284f43425f72aad9cda63ca12ceb92e7caa06903490c82dc9bf`.
Проверить checksum до запуска; при обновлении инструмента обновить evidence.
Без Docker socket/cloud upload сохранить только **образы**, не контейнеры с данными:

```powershell
# privateAudit — созданная оператором приватная папка, trivy — проверенный binary.
docker image save -o (Join-Path $privateAudit 'api.tar') business-ai-h06-api
& $trivy image --input (Join-Path $privateAudit 'api.tar') --scanners vuln `
  --severity CRITICAL,HIGH --exit-code 1 --timeout 10m
# Secret JSON может быть чувствительным: только private directory, без artifacts.
& $trivy image --input (Join-Path $privateAudit 'api.tar') --scanners secret `
  --format json --output (Join-Path $privateAudit 'private-image-secrets.json')
```

Повторить для web, точного DB image ID/digest и внешнего Ollama image. Первый scan
обновляет advisory DB; --skip-db-update допустим только для остальных образов того же
прогона после проверки UpdatedAt. Недоступная/устаревшая DB означает неполный аудит.
Никогда не сохранять рабочий container export вместе с пользовательскими volumes.

Команда --exit-code1 сейчас **должна отказать** для API/DB/Ollama HIGH/CRITICAL;
green scoped package CI не означает принятие этих image рисков. Trivy reports содержат
vendor severities и повторения CVE по package/binary: приводить отдельно raw occurrence
и deduplicated IDs. Сверять native/core security lists: scanner не гарантирует покрытие
PGDG PostgreSQL/libpq/CUDA/модельного parser. Не запускать exploit/DoS на рабочей БД.

## Лицензии и закрепление

`scripts/inventory_dependencies.py` создаёт inventory и предоставленные runtime notices
из установленного lock-набора; SHA license files позволяют проверить evidence.
Conditional/uninstalled packages, системные библиотеки и GPU image требуют отдельной
оценки. Отсутствующий текст лицензии не маркировать проверенным по одному SPDX field.

Docker runtime hashes/digests, Actions commits и age/Gitleaks release hashes закреплены.
Текущий контейнерный baseline — Linux amd64: закреплённый Brotli APK относится к
x86_64. ARM64-сборки не проверены и требуют отдельного artifact/checksum и smoke.
`apps/api/requirements.txt` экспортировать из apps/api ровно CI-командой:

```powershell
Push-Location apps/api
uv export --locked --no-dev --no-emit-project --format requirements-txt --output-file requirements.txt
Pop-Location
```

--require-hashes запрещает подмену package artifacts. Полный npm lock/integrity
проверяется npm ci. Смена pins требует triage/регрессии и review; не применять массовый
upgrade всего стека. CI Python/Node patch selection, scanner tool transitive dependencies,
timestamps/registry availability остаются переменными — побитовая сборка не гарантирована.
Ожидаемый Qwen manifest digest задан в data/demo-manifest.json v2; demo_ready проверяет
его без inference. Наличие лицензии базовой модели не заменяет evidence конкретного GGUF.

Никаких automatic volume cleanup. Для оставшегося H-05 QA volume использовать только
owner-reviewed точные имена/labels из отчёта. H-06 smoke использует tmpfs DB и не создаёт
новый persistent volume. Пересканировать перед внешним релизом, а не полагаться на дату
этого baseline. Следующая задача — только по указанию владельца.
