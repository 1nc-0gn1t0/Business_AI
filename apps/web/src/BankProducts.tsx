import { ViStatus } from "./Vi";
import { useEffect, useRef, useState } from "react";
import { ApiError, date, errorText, request } from "./api";
import type { Conversation, Credential, Schemas } from "./api";
import LeadFlow from "./LeadFlow";

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
  demo_match: "Совпадение по потребностям",
  demo_information: "Справочная информация о финансировании",
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
  onReport,
  universal = false,
}: {
  active: boolean;
  conversation: Conversation | null;
  credential: Credential | null;
  onProfileConflict: () => void;
  onReport?: (value: Schemas["MatchResult"] | null) => void;
  universal?: boolean;
}) {
  const [catalogue, setCatalogue] = useState<Schemas["CatalogueView"] | null>(
    null,
  );
  const [answered, setAnswered] = useState<(keyof Needs)[]>([]);
  const [needs, setNeeds] = useState<Needs>({});
  const [result, setResult] = useState<Schemas["MatchResult"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const pending = useRef<AbortController | null>(null);
  useEffect(() => {
    onReport?.(result);
  }, [result, onReport]);
  useEffect(() => () => onReport?.(null), [onReport]);
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
        `/api/${universal ? "v2" : "v1"}/conversations/${credential.id}/bank-products/matches`,
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
  const questions: (keyof Needs)[] = [
    "needs_settlement_account",
    "registration_status",
    ...(needs.registration_status === "not_registered"
      ? [
          "needs_registration_help" as const,
          ...(needs.needs_registration_help ? ["launch_stage" as const] : []),
        ]
      : []),
    "accepts_card_payments",
    ...(needs.accepts_card_payments ? ["sales_channel" as const] : []),
    ...(["loan", "mixed"].includes(conversation?.profile.funding || "")
      ? []
      : ["financing_interest" as const]),
  ];
  const question = fields.find(
    (f) => f.key === questions.find((key) => !answered.includes(key)),
  );
  function answer(key: keyof Needs, value: string) {
    setNeeds((current) => ({
      ...current,
      [key]:
        value === ""
          ? null
          : fields.find((f) => f.key === key)?.options
            ? value
            : value === "true",
    }));
    setAnswered((current) => [...current.filter((k) => k !== key), key]);
    setResult(null);
  }
  const prompts: Partial<Record<keyof Needs, string>> = {
    needs_settlement_account: "Вам нужен расчётный счёт?",
    registration_status: "Бизнес уже зарегистрирован?",
    needs_registration_help: "Нужна помощь с регистрацией?",
    accepts_card_payments: "Будете принимать оплату картами?",
    sales_channel: "Где будете продавать?",
    financing_interest: "Рассматриваете финансирование?",
    launch_stage: "На каком этапе ваш бизнес?",
  };
  function productCards(entries: Schemas["CatalogueView"]["products"]) {
    return (
      <div className="bank-product-grid">
        {entries.map((entry) => {
          const p = entry.product;
          const decision = result?.decisions.find(
            (d) => d.entry.product.id === p.id,
          );
          return (
            <article
              className={`bank-product-card ${decision?.status === "not_matched" || entry.availability === "blocked" ? "muted-card" : ""}`}
              key={p.id}
            >
              {entry.availability === "blocked" && (
                <p className="fine-print">Недоступно для подбора</p>
              )}
              <h2>{p.name}</h2>
              <p>{p.description}</p>
              {decision && (
                <p className="match-reason">
                  {statusText[decision.status]}
                  {decision.reasons[0] ? `: ${decision.reasons[0]}` : ""}
                </p>
              )}
              <details className="product-more">
                <summary>Почему подходит и что проверить</summary>
                <p>
                  {entry.availability === "demonstration_only"
                    ? "Демонстрационная карточка. Действующие условия не подтверждены; это не кредитное одобрение."
                    : entry.availability === "blocked"
                      ? "Заблокирована для подбора"
                      : "Публичная информация"}
                </p>
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
              </details>
            </article>
          );
        })}
      </div>
    );
  }
  const matched =
    result?.decisions
      .filter((d) => !["not_matched", "unavailable"].includes(d.status))
      .map((d) => d.entry) || [];
  return (
    <section className="bank-products">
      <div className="section-heading">
        <h1>
          Что поможет <br />
          вашему бизнесу?
        </h1>
        <p>Несколько вопросов — и подходящие банковские возможности.</p>
      </div>
      {(busy || error || result) && (
        <ViStatus
          emotion={
            error
              ? "error"
              : busy
                ? "thinking"
                : result?.status !== "evaluated" || result.missing_fields.length
                  ? "uncertain"
                  : "confident"
          }
        >
          {error
            ? "Не удалось получить варианты. Попробуйте обновить каталог."
            : busy
              ? "Сопоставляю ваши потребности…"
              : result?.status === "catalogue_unavailable"
                ? "Нет подтверждённых доступных предложений в текущем каталоге."
                : result?.status === "needs_confirmation"
                  ? "Сначала подтвердите текущие параметры проекта."
                  : result?.missing_fields.length
                    ? "Для точного подбора нужны уточнения."
                    : "Подбор завершён. Это не решение банка."}
        </ViStatus>
      )}
      <p className="model-note">Демонстрационный подбор. Не решение банка.</p>
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
      {!catalogue && !error && <p role="status">Загружаем варианты…</p>}
      {catalogue && (
        <>
          {!result && (
            <form className="bank-question" onSubmit={calculate}>
              {question ? (
                <>
                  <h2>{prompts[question.key] || question.title}</h2>
                  <div className="answer-options">
                    {[
                      ...(question.options || [
                        ["true", "Да"],
                        ["false", "Нет"],
                      ]),
                      ["", "Пока не знаю"],
                    ].map(([value, label]) => (
                      <button
                        type="button"
                        key={value}
                        className="answer-button"
                        disabled={busy}
                        onClick={() => answer(question.key, value)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    className="text-button"
                    type="submit"
                    disabled={
                      busy ||
                      (!universal &&
                        conversation?.profile.confirmation_state !==
                          "confirmed")
                    }
                  >
                    {busy ? "Подбираем…" : "Показать варианты по этим ответам"}
                  </button>
                </>
              ) : (
                <>
                  <h2>Посмотрим, что подходит?</h2>
                  <p>
                    Неизвестные условия останутся отмеченными — они не считаются
                    выполненными.
                  </p>
                  <button
                    className="button"
                    disabled={
                      busy ||
                      !credential ||
                      (!universal &&
                        conversation?.profile.confirmation_state !==
                          "confirmed")
                    }
                  >
                    {busy ? "Подбираем…" : "Подобрать по потребностям →"}
                  </button>
                </>
              )}
            </form>
          )}
          {result && (
            <>
              <div className="bank-result-summary" role="status">
                <h2>
                  {result.status === "needs_confirmation"
                    ? "Требуется подтверждение профиля"
                    : result.status === "catalogue_unavailable"
                      ? "Нет актуальных записей для подбора"
                      : "Возможности для вашего проекта"}
                </h2>
                <p>
                  {result.demonstration_ids.length
                    ? `Демо-совпадений: ${result.demonstration_ids.length}.`
                    : "Совпадений пока нет."}{" "}
                  {result.missing_fields.length
                    ? `Для точного подбора нужно уточнить: ${result.missing_fields.map(fieldName).join(", ")}.`
                    : ""}
                </p>
              </div>
              {productCards(matched)}
            </>
          )}
          <details className="bank-needs-edit">
            <summary>Изменить или дополнить потребности</summary>
            <p>
              Ответы добровольны. «Не указано» не считается выполненным
              условием. Интерес к финансированию из профиля учитывается
              сервером; явный выбор здесь имеет приоритет.
            </p>
            <form onSubmit={calculate}>
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

              <button
                className="button"
                disabled={
                  busy ||
                  !credential ||
                  (!universal &&
                    conversation?.profile.confirmation_state !== "confirmed")
                }
              >
                Подобрать по потребностям →
              </button>
            </form>
          </details>
          <details className="catalogue-more">
            <summary>Все продукты, источники и ограничения</summary>
            <p>
              Подтверждённых действующих предложений:{" "}
              {result?.recommended_ids.length ?? 0}. Всего позиций:{" "}
              {catalogue.products.length}. Каталог {catalogue.version}, проверка{" "}
              {date(catalogue.as_of)}.
            </p>
            {productCards(
              catalogue.products.filter(
                (e) => !matched.some((m) => m.product.id === e.product.id),
              ),
            )}
            <ul>
              {catalogue.limitations.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
            <p>Алгоритм: {result?.algorithm_version || "Подбор не выполнен"}</p>
            <details>
              <summary>Правила и воспроизводимость</summary>
              <pre>
                {JSON.stringify(
                  {
                    catalogue_fingerprint: catalogue.fingerprint,
                    request_fingerprint: result?.request_fingerprint,
                    needs_snapshot: result?.needs_snapshot,
                    profile_version: result?.profile_version,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </details>
          {universal && (
            <p>
              Подбор носит информационный характер. Для новых отраслей
              mock-заявка пока недоступна; данные никуда не отправлены.
            </p>
          )}
          {conversation && credential && !universal && (
            <details className="mock-flow">
              <summary>Демонстрационная заявка и согласия</summary>
              <LeadFlow
                conversation={conversation}
                credential={credential}
                catalogue={catalogue}
                active={active}
              />
            </details>
          )}
        </>
      )}
    </section>
  );
}
