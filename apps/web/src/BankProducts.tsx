import { useEffect, useRef, useState } from "react";
import { ApiError, date, errorText, request } from "./api";
import type { Conversation, Credential, Schemas } from "./api";

type Needs = Schemas["BankingNeeds"];
const fields: {
  key: keyof Needs;
  title: string;
  options?: [string, string][];
}[] = [
  {
    key: "launch_stage",
    title: "Стадия бизнеса",
    options: [
      ["idea", "Идея"],
      ["preparing", "Подготовка запуска"],
      ["operating", "Бизнес работает"],
    ],
  },
  {
    key: "registration_status",
    title: "Регистрация бизнеса",
    options: [
      ["not_registered", "Пока не зарегистрирован"],
      ["ip", "ИП"],
      ["legal_entity", "Юридическое лицо"],
    ],
  },
  {
    key: "sales_channel",
    title: "Канал продаж",
    options: [
      ["offline", "Физическая точка"],
      ["online", "Онлайн"],
      ["both", "Офлайн и онлайн"],
    ],
  },
  { key: "needs_settlement_account", title: "Нужен расчётный счёт" },
  { key: "needs_registration_help", title: "Нужна помощь с регистрацией" },
  {
    key: "accepts_card_payments",
    title: "Планируете принимать оплату картами",
  },
  { key: "needs_expense_card", title: "Нужна дебетовая карта для расходов" },
  {
    key: "financing_interest",
    title: "Интересует информация о финансировании",
  },
];
const statusText: Record<Schemas["ProductDecision"]["status"], string> = {
  potential_match: "Соответствует заявленной потребности",
  information_only: "Только информация о финансировании",
  demo_match: "Демо-совпадение потребности",
  demo_information: "Демо: информация о финансировании",
  needs_clarification: "Нужно уточнить",
  not_matched: "Нет совпадения потребности",
  unavailable: "Не используется в подборе",
};
const fieldName = (key: string) =>
  fields.find((f) => f.key === key)?.title || key;

export default function BankProducts({
  active,
  conversation,
  credential,
  onProfileConflict,
}: {
  active: boolean;
  conversation: Conversation | null;
  credential: Credential | null;
  onProfileConflict: () => void;
}) {
  const [catalogue, setCatalogue] = useState<Schemas["CatalogueView"] | null>(
    null,
  );
  const [needs, setNeeds] = useState<Needs>({});
  const [result, setResult] = useState<Schemas["MatchResult"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    request<Schemas["CatalogueView"]>("/api/v1/bank-products", {
      signal: controller.signal,
    })
      .then((next) => {
        setCatalogue(next);
        setResult((previous) =>
          previous &&
          (previous.catalogue.fingerprint !== next.fingerprint ||
            previous.catalogue.as_of !== next.as_of)
            ? null
            : previous,
        );
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setCatalogue(null);
          setResult(null);
        }
      });
    return () => controller.abort();
  }, [active, retry]);
  useEffect(() => () => pending.current?.abort(), []);
  async function calculate(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!conversation || !credential || !catalogue) return;
    pending.current?.abort();
    const c = new AbortController();
    pending.current = c;
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const response = await request<Schemas["MatchResult"]>(
        `/api/v1/conversations/${credential.id}/bank-products/matches`,
        {
          method: "POST",
          credential,
          signal: c.signal,
          body: {
            expected_version: conversation.version,
            needs,
            catalogue_fingerprint: catalogue.fingerprint,
          },
        },
      );
      setResult(response);
    } catch (e) {
      if (!c.signal.aborted) {
        setError(errorText(e));
        if (e instanceof ApiError && e.code === "version_conflict")
          onProfileConflict();
        if (
          e instanceof ApiError &&
          e.code === "bank_catalogue_version_conflict"
        )
          setRetry((v) => v + 1);
      }
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  return (
    <div className="bank-products">
      <div className="section-heading">
        <div>
          <span className="eyebrow">БАНКОВСКИЕ ПОТРЕБНОСТИ БИЗНЕСА</span>
          <h1>Продукты ВТБ</h1>
          <p>Понятное соответствие потребностей назначению продукта.</p>
        </div>
        <span className="tag amber">Прототип · без интеграции с банком</span>
      </div>
      <div className="notice">
        Это информационный подбор, не решение банка и не заявка. Тарифы,
        доступность и требования проверяются в ВТБ. Персональные данные в банк
        не отправляются.
      </div>
      {error && (
        <div className="alert" role="alert">
          {error}
          <button
            className="text-button"
            onClick={() => {
              setError("");
              setRetry((v) => v + 1);
            }}
          >
            Обновить каталог
          </button>
        </div>
      )}
      {!catalogue && !error && (
        <div className="empty" role="status">
          Загружаем каталог…
        </div>
      )}
      {catalogue && (
        <>
          <div className="row bank-catalogue-heading">
            <h2>Каталог и проверяемые источники</h2>
            <span className="subtle">
              {catalogue.products.length} позиций · {date(catalogue.as_of)}
            </span>
          </div>
          {catalogue.products.some(
            (p) => p.availability === "demonstration_only",
          ) && (
            <div className="bank-demo-banner">
              <span className="tag amber">Демо-каталог</span>
              <p>
                Сведения основаны на индексированных копиях официальных страниц
                ВТБ. Прямую актуальность подтвердить не удалось. Демо-совпадения
                не являются действующими предложениями; ставки и комиссии не
                подставляются.
              </p>
            </div>
          )}
          <form className="detail-panel bank-needs" onSubmit={calculate}>
            <h2>Что нужно вашему бизнесу?</h2>
            <p className="subtle">
              Ответы добровольны. «Не указано» не считается выполненным
              условием. Город, бюджет и формат не доказывают регистрацию, канал
              продаж или право на продукт.
            </p>
            <div className="bank-needs-grid">
              {fields.map((f) => (
                <label key={f.key}>
                  {f.title}
                  <select
                    aria-label={f.title}
                    value={needs[f.key] == null ? "" : String(needs[f.key])}
                    disabled={busy}
                    onChange={(event) => {
                      const raw = event.target.value;
                      const value =
                        raw === "" ? null : f.options ? raw : raw === "true";
                      setNeeds((n) => ({ ...n, [f.key]: value }));
                      setResult(null);
                    }}
                  >
                    <option value="">Не указано</option>
                    {(
                      f.options || [
                        ["true", "Да"],
                        ["false", "Нет"],
                      ]
                    ).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <p className="subtle">
              Если интерес к финансированию не указан, учитывается только явный
              выбор «кредит» или «смешанное» в подтверждённом профиле. Явный
              ответ в этой форме имеет приоритет.
            </p>
            <div className="row calculation-controls">
              <span className="subtle">
                {conversation?.profile.confirmation_state === "confirmed"
                  ? "Используется подтверждённый профиль беседы."
                  : "Сначала подтвердите профиль в чате. Каталог можно изучать без подтверждения."}
              </span>
              <button
                className="button"
                disabled={
                  busy ||
                  !credential ||
                  conversation?.profile.confirmation_state !== "confirmed"
                }
              >
                {busy ? "Подбираем…" : "Подобрать по потребностям →"}
              </button>
            </div>
          </form>
          {result && (
            <div className="bank-result-summary" role="status">
              <h2>
                {result.status === "needs_confirmation"
                  ? "Требуется подтверждение профиля"
                  : result.status === "catalogue_unavailable"
                    ? "Нет актуальных записей для подбора"
                    : "Подбор выполнен по явным правилам"}
              </h2>
              <p>
                Потенциальные соответствия по проверенным источникам:{" "}
                {result.recommended_ids.length}. Демо-совпадения:{" "}
                {result.demonstration_ids.length}.
              </p>
              {result.missing_fields.length > 0 && (
                <p>
                  Чтобы уточнить подбор:{" "}
                  {result.missing_fields.map(fieldName).join("; ")}.
                </p>
              )}
              <p className="subtle">
                Кредитоспособность и одобрение не оцениваются.
              </p>
            </div>
          )}
          {catalogue.products.length === 0 && (
            <div className="empty">
              В каталоге нет продуктов. Действующие предложения не подставляются
              автоматически.
            </div>
          )}
          <div className="bank-product-grid">
            {(result?.catalogue || catalogue).products.map((entry) => {
              const p = entry.product;
              const decision = result?.decisions.find(
                (d) => d.entry.product.id === p.id,
              );
              return (
                <article
                  className={`bank-product-card ${decision?.status === "not_matched" || entry.availability === "blocked" ? "muted-card" : ""}`}
                  key={p.id}
                >
                  <div className="row">
                    <span
                      className={`tag ${entry.availability === "demonstration_only" ? "amber" : ""}`}
                    >
                      {entry.availability === "demonstration_only"
                        ? "Демонстрационная карточка"
                        : entry.availability === "blocked"
                          ? "Заблокирована для подбора"
                          : "Публичная информация"}
                    </span>
                  </div>
                  <h2>{p.name}</h2>
                  <p>{p.description}</p>
                  {decision && (
                    <section className="bank-decision">
                      <h3>{statusText[decision.status]}</h3>
                      <ul>
                        {decision.reasons.map((reason, i) => (
                          <li key={i}>{reason}</li>
                        ))}
                      </ul>
                    </section>
                  )}
                  <h3>Что ещё нужно проверить</h3>
                  <ul>
                    {p.unknown_conditions.map((t) => (
                      <li key={t}>{t}</li>
                    ))}
                  </ul>
                  <details>
                    <summary>Условия и ограничения карточки</summary>
                    <ul>
                      {[
                        ...entry.availability_reasons,
                        ...p.applicable_conditions,
                        ...p.limitations,
                      ].map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </details>
                  <div className="bank-sources">
                    {entry.sources.map((source) => (
                      <div key={source.id}>
                        <a href={source.url} target="_blank" rel="noreferrer">
                          Официальная страница ВТБ ↗
                        </a>
                        <p>{source.title}</p>
                        <small>
                          {source.verification === "verified" &&
                          source.last_verified_at
                            ? `Прямая проверка: ${date(source.last_verified_at)}`
                            : `Просмотр копии / попытка проверки: ${date(source.reviewed_at)} · актуальность не подтверждена`}
                        </small>
                      </div>
                    ))}
                  </div>
                  <details>
                    <summary>Применённые правила и происхождение</summary>
                    <pre>
                      {JSON.stringify(
                        {
                          product_version: p.version,
                          source: entry.sources,
                          rules: decision?.evaluations || p.rules,
                        },
                        null,
                        2,
                      )}
                    </pre>
                  </details>
                </article>
              );
            })}
          </div>
          <details className="provenance">
            <summary>Версия каталога, методология и воспроизводимость</summary>
            <p>
              Каталог: {catalogue.version}; срок пересмотра —{" "}
              {catalogue.review_window_days} дней. Просроченные, снятые или
              недоступные записи блокируются.
            </p>
            <ul>
              {catalogue.limitations.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <pre>
              {JSON.stringify(
                {
                  catalogue_fingerprint: catalogue.fingerprint,
                  algorithm_version: result?.algorithm_version,
                  request_fingerprint: result?.request_fingerprint,
                  needs_snapshot: result?.needs_snapshot,
                  profile_version: result?.profile_version,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
    </div>
  );
}
