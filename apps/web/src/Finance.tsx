import { ViStatus } from "./Vi";
import { useEffect, useRef, useState } from "react";
import template from "./finance-template.json";
import type { Profile, Schemas } from "./api";
import { errorText, request, rub } from "./api";
import { readable } from "./labels";
import FinanceChart from "./FinanceChart";

type FinanceInput = Schemas["FinanceRequest-Input"];
type Scenario = "conservative" | "base" | "optimistic";
const scenarioNames = {
  conservative: "Пессимистичный",
  base: "Базовый",
  optimistic: "Оптимистичный",
};
const startupLabels = {
  equipment: "Оборудование",
  renovation: "Ремонт",
  rent_deposit: "Депозит по аренде",
  initial_inventory: "Первоначальный запас",
  registration: "Регистрация",
  other: "Прочие стартовые",
  working_capital_reserve: "Оборотный резерв",
};
const fixedLabels = {
  rent: "Аренда",
  payroll: "Зарплаты",
  utilities: "Коммунальные",
  other: "Прочие постоянные",
};
const scenarioLabels = {
  average_check: "Средний чек, ₽",
  sales_per_day: "Продаж в день",
  variable_cost_ratio: "Доля переменных затрат (0–1)",
};
const driverLabels: Record<string, string> = {
  average_check: "Средний чек",
  sales_per_day: "Продажи в день",
  rent: "Аренда",
  variable_cost_ratio: "Доля переменных затрат",
};
export function demoInput(
  profile: Profile,
  zone: Schemas["ZoneReference"] | null,
): FinanceInput {
  // Only editable inputs are bundled. Every result is calculated by the API.
  return {
    ...structuredClone(template),
    profile,
    selected_zone: zone,
  } as FinanceInput;
}
export default function Finance({
  profile,
  zone,
  onReport,
}: {
  profile: Profile | null;
  zone: Schemas["ZoneReference"] | null;
  onReport?: (value: Schemas["FinanceResult"] | null) => void;
}) {
  const [input, setInput] = useState<FinanceInput | null>(null);
  const [result, setResult] = useState<Schemas["FinanceResult"] | null>(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const resultPanel = useRef<HTMLElement>(null);
  useEffect(() => {
    if (result) {
      resultPanel.current?.scrollIntoView?.({ block: "start" });
      resultPanel.current?.focus({ preventScroll: true });
    }
  }, [result]);
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    onReport?.(dirty ? null : result);
  }, [result, dirty, onReport]);
  useEffect(() => () => onReport?.(null), [onReport]);
  useEffect(() => () => active.current?.abort(), []);
  function edit(
    group:
      "startup" | "monthly_fixed_costs" | "working_days_per_month" | Scenario,
    key: string,
    value: string,
  ) {
    if (!input) return;
    const next = structuredClone(input);
    let target;
    if (group === "startup")
      target = next.startup[key as keyof typeof next.startup];
    else if (group === "monthly_fixed_costs")
      target =
        next.monthly_fixed_costs[key as keyof typeof next.monthly_fixed_costs];
    else if (group === "working_days_per_month")
      target = next.working_days_per_month;
    else target = next.scenarios[group][key as keyof typeof scenarioLabels];
    target.value =
      key === "sales_per_day" || group === "working_days_per_month"
        ? Number(value)
        : value;
    target.source = {
      ...target.source,
      origin: "synthetic",
      source_name:
        "Редактируемое пользователем сценарное допущение; не рыночный факт",
      data_version: "ui-assumptions-v1",
      confidence: "not_applicable",
    };
    active.current?.abort();
    setBusy(false);
    setInput(next);
    setDirty(true);
  }
  async function calculate(
    event: React.SubmitEvent<HTMLFormElement> | null,
    candidate = input,
  ) {
    event?.preventDefault();
    if (!candidate || !profile) return;
    active.current?.abort();
    const c = new AbortController();
    active.current = c;
    setBusy(true);
    setError("");
    try {
      const r = await request<Schemas["FinanceResult"]>(
        "/api/v1/finance/calculate",
        {
          method: "POST",
          body: { ...candidate, profile, selected_zone: zone },
          signal: c.signal,
        },
      );
      setResult(r);
      setDirty(false);
    } catch (e) {
      if (!c.signal.aborted) setError(errorText(e));
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  const base = result?.scenarios.find((s) => s.name === "base");
  return (
    <section className="finance">
      <div className="section-heading">
        <h1>
          Сколько может приносить <br />
          ваш бизнес?
        </h1>
        <p>Сравните три сценария и проверьте свои предположения.</p>
      </div>
      {(busy || error || result) && (
        <ViStatus
          emotion={
            error ? "error" : busy ? "thinking" : dirty ? "uncertain" : "idea"
          }
        >
          {error
            ? "Не получилось выполнить расчёт. Проверьте вводные и попробуйте ещё раз."
            : busy
              ? "Рассчитываю сценарии…"
              : dirty
                ? "Вводные изменены. Пересчитайте модель."
                : "Сценарии рассчитаны. Проверьте допущения."}
        </ViStatus>
      )}
      <p className="model-note">
        Синтетические редактируемые допущения кофейни — не реальные цены или
        спрос. Расчёт не зависит от георейтинга.
      </p>
      {!input ? (
        <div className="finance-start">
          <p>
            Начните с демонстрационного сценария кофейни. Все вводные можно
            изменить.
          </p>
          <button
            className="button"
            disabled={!profile || busy}
            onClick={() => {
              if (profile) {
                const next = demoInput(profile, zone);
                setInput(next);
                setDirty(true);
                void calculate(null, next);
              }
            }}
          >
            Рассчитать сценарии
          </button>
        </div>
      ) : (
        <form className="finance-form" onSubmit={calculate}>
          <div className="quick-assumptions">
            <label>
              Аренда, ₽ / мес.
              <input
                aria-label="Аренда"
                type="number"
                min="0"
                step="0.01"
                required
                value={input.monthly_fixed_costs.rent.value}
                onChange={(e) =>
                  edit("monthly_fixed_costs", "rent", e.target.value)
                }
              />
            </label>
            <label>
              Продаж в день · базовый
              <input
                aria-label="Базовый: Продаж в день"
                type="number"
                min="0"
                step="1"
                required
                value={input.scenarios.base.sales_per_day.value}
                onChange={(e) => edit("base", "sales_per_day", e.target.value)}
              />
            </label>
            <label>
              Средний чек, ₽ · базовый
              <input
                aria-label="Базовый: Средний чек, ₽"
                type="number"
                min="0.01"
                step="0.01"
                required
                value={input.scenarios.base.average_check.value}
                onChange={(e) => edit("base", "average_check", e.target.value)}
              />
            </label>
          </div>
          <details className="assumptions">
            <summary>Все допущения и структура затрат</summary>
            <div className="input-columns">
              <fieldset>
                <legend>Стартовые вложения, ₽</legend>
                {Object.entries(startupLabels).map(([key, title]) => (
                  <label key={key}>
                    {title}
                    <input
                      aria-label={title}
                      type="number"
                      min="0"
                      step="0.01"
                      required
                      value={
                        input.startup[key as keyof typeof startupLabels].value
                      }
                      onChange={(e) => edit("startup", key, e.target.value)}
                    />
                  </label>
                ))}
              </fieldset>
              <fieldset>
                <legend>Постоянные расходы, ₽ / мес.</legend>
                {Object.entries(fixedLabels)
                  .filter(([key]) => key !== "rent")
                  .map(([key, title]) => (
                    <label key={key}>
                      {title}
                      <input
                        aria-label={title}
                        type="number"
                        min="0"
                        step="0.01"
                        required
                        value={
                          input.monthly_fixed_costs[
                            key as keyof typeof fixedLabels
                          ].value
                        }
                        onChange={(e) =>
                          edit("monthly_fixed_costs", key, e.target.value)
                        }
                      />
                    </label>
                  ))}
                <label>
                  Рабочих дней в месяц
                  <input
                    aria-label="Рабочих дней в месяц"
                    type="number"
                    min="1"
                    max="31"
                    step="1"
                    required
                    value={input.working_days_per_month.value}
                    onChange={(e) =>
                      edit("working_days_per_month", "", e.target.value)
                    }
                  />
                </label>
              </fieldset>
            </div>
            <div className="scenario-inputs">
              {(Object.keys(scenarioNames) as Scenario[]).map((s) => (
                <fieldset key={s}>
                  <legend>{scenarioNames[s]}</legend>
                  {Object.entries(scenarioLabels)
                    .filter(
                      ([key]) => s !== "base" || key === "variable_cost_ratio",
                    )
                    .map(([key, title]) => (
                      <label key={key}>
                        {title}
                        <input
                          aria-label={`${scenarioNames[s]}: ${title}`}
                          type="number"
                          required
                          min={key === "average_check" ? "0.01" : "0"}
                          max={
                            key === "variable_cost_ratio"
                              ? "0.999999"
                              : undefined
                          }
                          step={
                            key === "sales_per_day"
                              ? "1"
                              : key === "variable_cost_ratio"
                                ? "0.01"
                                : "0.01"
                          }
                          value={
                            input.scenarios[s][
                              key as keyof typeof scenarioLabels
                            ].value
                          }
                          onChange={(e) => edit(s, key, e.target.value)}
                        />
                      </label>
                    ))}
                </fieldset>
              ))}
            </div>
            <p className="subtle">
              Каждое поле: synthetic · coffee-finance-demo-v1; после
              редактирования — ui-assumptions-v1. Источник и значения передаются
              серверу и входят в снимок расчёта.
            </p>
          </details>
          {(dirty || busy || error) && (
            <div className="calculation-controls">
              <p className="fine-print" role="status">
                {busy ? "Рассчитываем…" : "Изменённые вводные ещё не учтены."}
              </p>
              <button className="button" disabled={busy}>
                {busy ? "Рассчитываем…" : "Пересчитать модель →"}
              </button>
            </div>
          )}
        </form>
      )}
      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}
      {result && (
        <section
          ref={resultPanel}
          tabIndex={-1}
          className={dirty ? "stale-result" : ""}
          aria-label="Результат финансового расчёта"
        >
          {dirty && (
            <p className="notice">
              Предыдущий расчёт. Измените вводные и пересчитайте модель перед
              продолжением.
            </p>
          )}
          <div className="capital-grid">
            <div>
              <small>Стартовые вложения</small>
              <strong>{rub(result.startup.total_initial_funding)}</strong>
            </div>
            <div>
              <small>Постоянные расходы / мес.</small>
              <strong>{rub(base?.metrics.monthly_fixed_cost.value)}</strong>
            </div>
            <div>
              <small>Ваш бюджет</small>
              <strong>{rub(profile?.budget)}</strong>
            </div>
          </div>
          {result.budget.status === "model_budget_shortfall" && (
            <p className="notice">
              Для модели не хватает {rub(result.budget.funding_gap)}. Это оценка
              по допущениям.
            </p>
          )}
          <h2 className="result-title">Операционный результат в месяц</h2>
          <div className="scenario-results">
            {result.scenarios.map((s) => (
              <article
                className={`scenario-card ${s.name === "base" ? "base" : ""}`}
                key={s.name}
              >
                <h3>{scenarioNames[s.name]}</h3>
                <strong
                  className={
                    Number(s.metrics.operating_result.value) < 0
                      ? "negative"
                      : "positive"
                  }
                >
                  {rub(s.metrics.operating_result.value)}
                </strong>
                <p>
                  {Number(s.metrics.operating_result.value) < 0
                    ? "Отрицательный результат"
                    : "По выбранным допущениям"}
                </p>
                <details>
                  <summary>Показатели сценария</summary>
                  <dl>
                    {[
                      ["monthly_revenue", "Выручка"],
                      ["monthly_variable_cost", "Переменные расходы"],
                      ["monthly_fixed_cost", "Постоянные расходы"],
                    ].map(([key, label]) => (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>
                          {rub(s.metrics[key as keyof typeof s.metrics].value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                  <p>
                    Безубыточность: {s.metrics.break_even_sales_per_day.value}{" "}
                    продаж / день
                  </p>
                  {s.warnings.map((t) => (
                    <p key={t}>{readable(t)}</p>
                  ))}
                </details>
              </article>
            ))}
          </div>
          <FinanceChart scenarios={result.scenarios} />
          <p className="fine-print">
            Операционный результат — не чистая прибыль и не денежный поток:
            налоги, амортизация и кредитные платежи могут быть не учтены. Это не
            прогноз спроса и не обещание окупаемости.
          </p>
          <details className="finance-details">
            <summary>Чувствительность, источники и ограничения</summary>
            <h2>Чувствительность базового сценария</h2>
            <p>
              Один фактор за раз, ±10%. Математическое изменение, не рыночный
              прогноз.
            </p>
            <div className="sensitivity-table">
              <table>
                <thead>
                  <tr>
                    <th>Фактор</th>
                    <th>Изменение</th>
                    <th>Опер. результат</th>
                    <th>Разница с базовым</th>
                    <th>Безубыточность, продаж/день</th>
                  </tr>
                </thead>
                <tbody>
                  {result.sensitivity.map((s) => (
                    <tr key={`${s.driver}:${s.relative_change}`}>
                      <td>{driverLabels[s.driver] || s.driver}</td>
                      <td>{(Number(s.relative_change) * 100).toFixed(0)}%</td>
                      <td>{rub(s.operating_result)}</td>
                      <td>
                        <span className="sensitivity-value">
                          <i
                            className={
                              Number(s.difference_from_base) < 0
                                ? "loss"
                                : "gain"
                            }
                            style={{
                              width: `${(Math.abs(Number(s.difference_from_base)) / Math.max(1, ...result.sensitivity.map((p) => Math.abs(Number(p.difference_from_base))))) * 100}%`,
                            }}
                          />
                          {rub(s.difference_from_base)}
                        </span>
                      </td>
                      <td>
                        {s.break_even_sales_per_day ??
                          "Вне допустимого диапазона"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p>
              Алгоритм: {result.algorithm_version}. Результат: modelled.
              Округление: {result.rounding}.
            </p>
            <ul>
              {[...result.limitations, ...result.warnings].map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
            <details>
              <summary>Формулы и происхождение вводных</summary>
              <pre>
                {JSON.stringify(
                  {
                    formulas: result.formulas,
                    inputs: result.request_snapshot,
                    fingerprint: result.request_fingerprint,
                    comparison: result.comparison,
                  },
                  null,
                  2,
                )}
              </pre>
            </details>
          </details>
        </section>
      )}
    </section>
  );
}
