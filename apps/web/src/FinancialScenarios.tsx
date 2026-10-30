import { useEffect, useRef, useState } from "react";
import {
  ApiError,
  errorText,
  request,
  type Credential,
  type Schemas,
} from "./api";
import { ViAvatar } from "./Vi";

type View = Schemas["FinancialView"];
type Calculation = Schemas["FinancialCalculation"];
type Update = Schemas["ParameterUpdate"];
type Billing = NonNullable<Schemas["FinancialDocument"]["billing_model"]>;
type Draft = {
  base: string;
  low: string;
  high: string;
  kind: "user_input" | "user_assumption";
};
const names = {
  conservative: "Пессимистичный",
  base: "Базовый",
  optimistic: "Оптимистичный",
};
const unitLabels: Record<string, string> = {
  "RUB/month": "₽/мес.",
  "RUB/order": "₽/заказ",
  "RUB/unit": "₽/ед.",
  "units/month": "ед./мес.",
  "days/month": "дней/мес.",
  "orders/bay/day": "заказов/пост/день",
  "RUB/student/payment": "₽/ученика за период оплаты",
  students: "учеников",
  bays: "постов",
  months: "мес.",
  ratio: "доля от 0 до 1",
};
const rub = (value: string | number) =>
  new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    maximumFractionDigits: 2,
  }).format(Number(value));

export default function FinancialScenarios({
  credential,
  profileRevision,
  onEdit,
}: {
  credential: Credential;
  profileRevision: number;
  onEdit: () => void;
}) {
  const [view, setView] = useState<View | null>(null);
  const [draft, setDraft] = useState<Record<string, Draft>>({});
  const [billing, setBilling] = useState<Billing | "">("");
  const [selected, setSelected] = useState<string[]>([]);
  const [preview, setPreview] = useState<Calculation | null>(null);
  const [busy, setBusy] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState("");
  const lock = useRef(false);
  const alive = useRef(true);
  const base = `/api/v2/conversations/${credential.id}/financial-scenarios`;
  const dirty =
    Object.keys(draft).length > 0 ||
    (!!view && billing !== (view.document.billing_model || ""));
  function accept(next: View) {
    setView(next);
    setDraft({});
    setSelected([]);
    setPreview(null);
    setBilling(next.document.billing_model || "");
  }
  useEffect(() => {
    const controller = new AbortController();
    alive.current = true;
    request<View>(base, { credential, signal: controller.signal })
      .then(accept)
      .catch((e) => {
        if (!controller.signal.aborted) setError(errorText(e));
      });
    return () => {
      alive.current = false;
      controller.abort();
    };
  }, [base, credential]);
  async function run(work: () => Promise<void>, model = false) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setThinking(model);
    setError("");
    try {
      await work();
    } catch (e) {
      if (alive.current) {
        setError(errorText(e));
        if (e instanceof ApiError && [401, 403, 404, 409].includes(e.status)) {
          setView(null);
          setPreview(null);
        }
      }
    } finally {
      lock.current = false;
      if (alive.current) {
        setBusy(false);
        setThinking(false);
      }
    }
  }
  function command() {
    return {
      request_id: crypto.randomUUID(),
      expected_profile_revision: profileRevision,
      expected_input_revision: view?.document.revision || 0,
    };
  }
  function updates(): Update[] {
    if (!view) return [];
    return Object.entries(draft).map(([key, value]) => ({
      parameter: key,
      unit: view.configuration.parameters.find((p) => p.id === key)!.unit,
      base: value.base.replace(",", "."),
      low: value.low.replace(",", "."),
      high: value.high.replace(",", "."),
      kind: value.kind,
      basis: "Редактирование пользователем",
    }));
  }
  async function send(path: string, body: unknown, method = "POST") {
    const next = await request<View>(base + path, { method, credential, body });
    if (alive.current) accept(next);
  }
  function field(key: string): Draft {
    const e = view?.document.entries?.[key];
    return (
      draft[key] || {
        base: String(e?.base ?? ""),
        low: String(e?.low ?? ""),
        high: String(e?.high ?? ""),
        kind: e?.epistemic === "assumed" ? "user_assumption" : "user_input",
      }
    );
  }
  function change(key: string, part: keyof Draft, value: string) {
    const old = field(key);
    const next = { ...old, [part]: value };
    if (part === "base" && old.low === old.base && old.high === old.base)
      next.low = next.high = value;
    setDraft((d) => ({ ...d, [key]: next }));
    setPreview(null);
  }
  const current =
    !!view?.current && view.document.profile_revision === profileRevision;
  const calculated =
    preview || (!dirty && current ? view?.result?.result : null);
  return (
    <section className="financial-scenarios">
      <div className="vi-inline">
        <ViAvatar
          emotion={
            error
              ? "error"
              : thinking
                ? "thinking"
                : calculated?.status === "calculated"
                  ? "idea"
                  : "neutral"
          }
        />
        {thinking && (
          <span role="status">Готовлю сценарные предположения…</span>
        )}
      </div>
      <h1>Сколько может приносить ваш бизнес?</h1>
      <p>
        Предварительный сценарный расчёт. Все существенные вводные выбираете вы.
      </p>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {(!view || !current) && (
        <>
          <p>
            Подтвердите текущий профиль. После изменения проекта прежние расчёты
            требуют проверки.
          </p>
          <button className="button" onClick={onEdit}>
            К параметрам проекта
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const next = await request<View>(base, { credential });
                if (alive.current) accept(next);
              })
            }
          >
            Обновить вводные
          </button>
          {view && !current && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                void run(() =>
                  send(
                    "",
                    {
                      ...command(),
                      reset_for_profile: true,
                      updates: [],
                    },
                    "PATCH",
                  ),
                )
              }
            >
              Начать расчёт для подтверждённого профиля
            </button>
          )}
        </>
      )}
      {view && current && (
        <>
          {view.document.model === "online_school" && (
            <label className="field">
              Как оплачивают обучение?
              <select
                aria-label="Модель оплаты обучения"
                value={billing}
                disabled={busy}
                onChange={(e) => {
                  setBilling(e.target.value as Billing);
                  setPreview(null);
                }}
              >
                <option value="">Выберите</option>
                <option value="monthly">Помесячно</option>
                <option value="subscription">Месячная подписка</option>
                <option value="course">Один раз за весь курс</option>
              </select>
            </label>
          )}
          <p>
            {view.missing.length
              ? `Нужны вводные или подтверждение: ${view.missing.length}.`
              : "Вводные подтверждены."}
          </p>
          {view.configuration.parameters.some(
            (p) =>
              (p.id !== "course_months" || billing === "course") &&
              (!view.document.entries?.[p.id] ||
                view.document.entries[p.id].review === "rejected"),
          ) && (
            <button
              className="button"
              disabled={
                busy ||
                !!dirty ||
                (view.document.model === "online_school" && !billing)
              }
              onClick={() => void run(() => send("/propose", command()), true)}
            >
              Предложить допущения с Ви
            </button>
          )}
          {view.proposal_status === "failed" && (
            <p role="status">
              Не удалось подготовить предложения. Можно ввести значения
              самостоятельно.
            </p>
          )}
          {view.proposal_status === "interrupted" && (
            <p role="status">
              Предыдущий запрос прерван. Проверьте вводные перед повтором.
            </p>
          )}
          <details open={view.needs_review.length > 0 || !!dirty}>
            <summary>Ввести или проверить параметры</summary>
            <p>
              Неизвестное значение оставьте пустым. Ноль означает, что этот
              расход явно не учитывается. Диапазоны — исследовательские
              допущения, не статистика рынка.
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void run(() =>
                  send(
                    "",
                    {
                      ...command(),
                      updates: updates(),
                      ...(billing ? { billing_model: billing } : {}),
                    },
                    "PATCH",
                  ),
                );
              }}
            >
              {view.configuration.parameters
                .filter((p) => p.id !== "course_months" || billing === "course")
                .map((p) => {
                  const value = field(p.id),
                    entry = view.document.entries?.[p.id];
                  return (
                    <fieldset
                      key={p.id}
                      className="financial-input"
                      disabled={busy}
                    >
                      <legend>
                        {p.label}{" "}
                        <small>· {unitLabels[p.unit] || p.unit}</small>
                      </legend>
                      <label>
                        Значение
                        <input
                          aria-label={p.label}
                          inputMode="decimal"
                          value={value.base}
                          onChange={(e) => change(p.id, "base", e.target.value)}
                        />
                      </label>
                      {p.direction !== "context" && (
                        <details>
                          <summary>Сценарный диапазон</summary>
                          <div className="financial-range">
                            <label>
                              Нижняя граница
                              <input
                                inputMode="decimal"
                                aria-label={`${p.label}: минимум`}
                                value={value.low}
                                onChange={(e) =>
                                  change(p.id, "low", e.target.value)
                                }
                              />
                            </label>
                            <label>
                              Верхняя граница
                              <input
                                inputMode="decimal"
                                aria-label={`${p.label}: максимум`}
                                value={value.high}
                                onChange={(e) =>
                                  change(p.id, "high", e.target.value)
                                }
                              />
                            </label>
                          </div>
                        </details>
                      )}
                      <label>
                        Основание
                        <select
                          value={value.kind}
                          aria-label={`${p.label}: происхождение`}
                          onChange={(e) => change(p.id, "kind", e.target.value)}
                        >
                          <option value="user_input">Моя вводная</option>
                          <option value="user_assumption">
                            Моё сценарное допущение
                          </option>
                        </select>
                      </label>
                      {entry && (
                        <>
                          <p>
                            {entry.epistemic === "assumed"
                              ? "Сценарная гипотеза"
                              : "Пользовательская вводная"}
                            {entry.method === "qwen_exploratory"
                              ? " · предложена Ви"
                              : ""}
                            {entry.review === "confirmed"
                              ? " · подтверждено для расчёта"
                              : entry.review === "rejected"
                                ? " · отклонено"
                                : " · требует проверки"}
                          </p>
                          <small>{entry.basis}</small>
                          <label>
                            <input
                              type="checkbox"
                              checked={selected.includes(p.id)}
                              disabled={!!dirty}
                              onChange={(e) =>
                                setSelected((s) =>
                                  e.target.checked
                                    ? [...s, p.id]
                                    : s.filter((k) => k !== p.id),
                                )
                              }
                            />
                            Проверено: {p.label}
                          </label>
                        </>
                      )}
                    </fieldset>
                  );
                })}
              <button className="button" disabled={busy || !dirty}>
                Сохранить вводные для проверки
              </button>
            </form>
          </details>
          {selected.length > 0 && (
            <div className="actions">
              <button
                className="button"
                disabled={busy || !!dirty}
                onClick={() =>
                  void run(() =>
                    send("/review", {
                      ...command(),
                      confirm: selected,
                      reject: [],
                    }),
                  )
                }
              >
                Использовать выбранные значения
              </button>
              <button
                className="text-button"
                disabled={busy || !!dirty}
                onClick={() =>
                  void run(() =>
                    send("/review", {
                      ...command(),
                      confirm: [],
                      reject: selected,
                    }),
                  )
                }
              >
                Отклонить выбранные
              </button>
            </div>
          )}
          <p>
            Подтверждение разрешает использовать гипотезу в расчёте и не делает
            её рыночным фактом.
          </p>
          <div className="actions">
            <button
              className="button"
              disabled={busy || !!dirty}
              onClick={() => void run(() => send("/calculate", command()))}
            >
              {view.missing.length
                ? "Получить частичный результат"
                : "Рассчитать три сценария"}
            </button>
            {Object.keys(draft).length > 0 && (
              <button
                className="text-button"
                disabled={
                  busy ||
                  (billing !== view.document.billing_model &&
                    view.document.model === "online_school")
                }
                onClick={() =>
                  void run(async () => {
                    const result = await request<Schemas["WhatIfResult"]>(
                      base + "/what-if",
                      {
                        method: "POST",
                        credential,
                        body: { ...command(), updates: updates() },
                      },
                    );
                    if (alive.current) setPreview(result.result);
                  })
                }
              >
                Проверить без сохранения
              </button>
            )}
          </div>
          {calculated && (
            <FinancialResults
              value={calculated}
              preview={!!preview}
              parameters={view.configuration.parameters}
            />
          )}
          {current && view.result && !dirty && (
            <button
              className="text-button"
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const latest = await request<View>(base, { credential });
                  if (
                    !latest.current ||
                    latest.result?.id !== view.result?.id
                  ) {
                    accept(latest);
                    return;
                  }
                  const url = URL.createObjectURL(
                    new Blob([JSON.stringify(latest.result, null, 2)], {
                      type: "application/json",
                    }),
                  );
                  const a = document.createElement("a");
                  a.href = url;
                  a.download = "business-scenarios.json";
                  a.click();
                  URL.revokeObjectURL(url);
                })
              }
            >
              Скачать сценарный JSON
            </button>
          )}
          <details>
            <summary>Как рассчитано?</summary>
            <ul>
              {view.configuration.limitations.map((l) => (
                <li key={l}>{l}</li>
              ))}
            </ul>
            <p>
              Модель: {view.configuration.id}, версия{" "}
              {view.configuration.version}. Наблюдаемые цены аренды и спрос
              автоматически не загружаются.
            </p>
          </details>
        </>
      )}
    </section>
  );
}

export function FinancialResults({
  value,
  preview = false,
  parameters = [],
}: {
  value: Calculation;
  preview?: boolean;
  parameters?: Schemas["FinancialParameter"][];
}) {
  const label = (key: string) =>
    parameters.find((p) => p.id === key)?.label || key;
  return (
    <section aria-label="Результаты сценариев" aria-live="polite">
      <h2>
        {preview ? "Пробный расчёт · не сохранён" : "При заданных параметрах"}
      </h2>
      {value.warnings?.includes(
        "scenario_labels_not_ordered_by_operating_result",
      ) && (
        <p>
          При отрицательной марже рост продаж может увеличивать убыток. Названия
          сценариев описывают вводные и не гарантируют порядок прибыли.
        </p>
      )}
      {value.scenarios.length > 0 &&
        new Set(value.scenarios.map((s) => JSON.stringify(s.drivers))).size ===
          1 && (
          <p>
            Сценарии совпадают: заданы одинаковые значения. Измените диапазоны,
            чтобы сравнить варианты.
          </p>
        )}
      {value.status === "partial" ? (
        <p>
          Недостаточно подтверждённых вводных. Неизвестные параметры:{" "}
          {value.missing.join(", ")}.
        </p>
      ) : (
        <>
          <div className="financial-comparison">
            {value.scenarios.map((s) => (
              <article key={s.name}>
                <h3>{names[s.name]}</h3>
                <p>
                  {s.period === "month"
                    ? "За выбранный месяц"
                    : `Одна когорта · ${s.months} мес.`}
                </p>
                <dl>
                  <dt>Выручка</dt>
                  <dd>{rub(s.revenue)}</dd>
                  <dt>Переменные расходы</dt>
                  <dd>{rub(s.variable_costs)}</dd>
                  <dt>Постоянные расходы</dt>
                  <dd>{rub(s.fixed_costs)}</dd>
                  <dt>Операционный результат</dt>
                  <dd>{rub(s.operating_result)}</dd>
                </dl>
                <p>
                  Безубыточность: {s.break_even.units ?? "не определена"}{" "}
                  {s.period === "course_cohort"
                    ? "учеников за курс"
                    : s.volume_unit === "orders"
                      ? "заказов/мес."
                      : s.volume_unit === "students"
                        ? "учеников/мес."
                        : "ед./мес."}
                  .
                  {s.break_even.status === "above_capacity" &&
                    " Порог превышает доступную мощность."}
                  {s.break_even.status === "nonpositive_margin" &&
                    " Маржа на единицу неположительна."}
                </p>
                <details>
                  <summary>Драйверы сценария</summary>
                  <dl>
                    {Object.entries(s.drivers).map(([k, v]) => (
                      <div key={k}>
                        <dt>{label(k)}</dt>
                        <dd>{v}</dd>
                      </div>
                    ))}
                  </dl>
                </details>
              </article>
            ))}
          </div>
          <details>
            <summary>Что сильнее влияет на результат?</summary>
            <p>
              Каждый драйвер изменён отдельно на ±10%. Другие вводные сохранены.
              Это не вероятностный прогноз.
            </p>
            <ul>
              {value.sensitivity.map((s, i) => (
                <li key={`${s.parameter}-${i}`}>
                  {label(s.parameter)}: {s.value} {unitLabels[s.unit] || s.unit}{" "}
                  →{" "}
                  {s.status === "calculated"
                    ? `изменение результата ${rub(s.difference_from_base!)}`
                    : "вне допустимых границ"}
                </li>
              ))}
            </ul>
          </details>
          {value.contains_assumptions && (
            <p>Результат включает сценарные гипотезы.</p>
          )}
        </>
      )}
    </section>
  );
}
