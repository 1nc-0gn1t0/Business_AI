import { useEffect, useRef, useState } from "react";
import template from "./finance-template.json";
import type { Profile, Schemas } from "./api";
import { errorText, request, rub } from "./api";
import { readable } from "./labels";
import FinanceChart from "./FinanceChart";

type FinanceInput = Schemas["FinanceRequest-Input"];
type Scenario = "conservative" | "base" | "optimistic";
const scenarioNames = {
  conservative: "Консервативный",
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
  const active = useRef<AbortController | null>(null);
  useEffect(() => {
    onReport?.(dirty ? null : result);
  }, [result, dirty, onReport]);
  useEffect(() => () => onReport?.(null), [onReport]);
  useEffect(() => () => active.current?.abort(), []);
  function edit(
    group:
      | "startup"
      | "monthly_fixed_costs"
      | "working_days_per_month"
      | Scenario,
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
  async function calculate(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!input || !profile) return;
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
          body: { ...input, profile, selected_zone: zone },
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
  return (
    <div className="finance">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ЭКОНОМИКА ВАШЕЙ ИДЕИ</span>
          <h1>Финансовая модель</h1>
          <p>Три сценария. Прозрачные вводные. Расчёты на сервере.</p>
        </div>
        <span className="tag amber">Сценарное моделирование</span>
      </div>
      <div className="finance-context">
        <div>
          <small>Бюджет пользователя</small>
          <strong>{rub(profile?.budget)}</strong>
        </div>
        <div>
          <small>Контекст</small>
          <strong>
            {profile?.category || "Бизнес не указан"} ·{" "}
            {profile?.city || "Город не указан"}
          </strong>
        </div>
        <div>
          <small>Зона-кандидат</small>
          <strong>
            {zone ? zone.candidate_id.slice(0, 12) : "Не выбрана"}
          </strong>
        </div>
      </div>
      <p className="notice">
        Все экономические вводные ниже —{" "}
        <b>синтетические редактируемые допущения</b>, а не реальные цены или
        спрос Казани. OSM-рейтинг не влияет на выручку. Выбранная зона — только
        контекст.
      </p>
      {!input ? (
        <div className="empty">
          <span className="empty-symbol">↗</span>
          <h2>Проверьте экономику идеи</h2>
          <p>
            Загрузите открытый набор допущений BA-009 и замените их своими
            значениями. Расчёт выполняется только после отправки на сервер.
          </p>
          <button
            className="button"
            disabled={!profile}
            onClick={() => {
              setDirty(true);
              if (profile) setInput(demoInput(profile, zone));
            }}
          >
            Загрузить демо-допущения
          </button>
        </div>
      ) : (
        <form onSubmit={calculate}>
          <details className="assumptions" open>
            <summary>
              Вводные и допущения{" "}
              <span className="tag amber">Синтетические</span>
            </summary>
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
                {Object.entries(fixedLabels).map(([key, title]) => (
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
                  {Object.entries(scenarioLabels).map(([key, title]) => (
                    <label key={key}>
                      {title}
                      <input
                        aria-label={`${scenarioNames[s]}: ${title}`}
                        type="number"
                        required
                        min={key === "average_check" ? "0.01" : "0"}
                        max={
                          key === "variable_cost_ratio" ? "0.999999" : undefined
                        }
                        step={
                          key === "sales_per_day"
                            ? "1"
                            : key === "variable_cost_ratio"
                              ? "0.01"
                              : "0.01"
                        }
                        value={
                          input.scenarios[s][key as keyof typeof scenarioLabels]
                            .value
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
          <div className="row calculation-controls">
            <p className="subtle">
              {dirty
                ? "Вводные изменены. Нужен пересчёт."
                : result
                  ? "Результат соответствует отправленным вводным."
                  : "Проверьте вводные и запустите расчёт."}
            </p>
            <button className="button" disabled={busy}>
              {busy ? "Рассчитываем…" : "Пересчитать модель →"}
            </button>
          </div>
        </form>
      )}
      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}
      {result && (
        <section
          className={dirty ? "stale-result" : ""}
          aria-label="Результат финансового расчёта"
        >
          {dirty && (
            <div className="notice">
              Ниже предыдущий расчёт. Он не учитывает изменённые вводные.
            </div>
          )}
          <div className="capital-grid">
            <div className="stat-card">
              <small>Старт без оборотного резерва</small>
              <strong>
                {rub(result.startup.launch_uses_excluding_reserve)}
              </strong>
            </div>
            <div className="stat-card">
              <small>Оборотный резерв</small>
              <strong>{rub(result.startup.working_capital_reserve)}</strong>
            </div>
            <div className="stat-card accent">
              <small>Общая потребность в капитале</small>
              <strong>{rub(result.startup.total_initial_funding)}</strong>
            </div>
            <div className="stat-card">
              <small>
                {result.budget.status === "model_budget_shortfall"
                  ? "Дефицит бюджета модели"
                  : "Остаток бюджета модели"}
              </small>
              <strong>
                {rub(
                  result.budget.status === "model_budget_shortfall"
                    ? result.budget.funding_gap
                    : result.budget.remaining,
                )}
              </strong>
            </div>
          </div>
          <div className="scenario-results">
            {result.scenarios.map((s) => (
              <article
                className={`scenario-card ${s.name === "base" ? "base" : ""}`}
                key={s.name}
              >
                <span className="eyebrow">{scenarioNames[s.name]}</span>
                <small>Операционный результат / месяц</small>
                <strong
                  className={
                    Number(s.metrics.operating_result.value) < 0
                      ? "negative"
                      : "positive"
                  }
                >
                  {rub(s.metrics.operating_result.value)}
                </strong>
                <dl>
                  {[
                    ["monthly_revenue", "Выручка"],
                    ["monthly_variable_cost", "Переменные расходы"],
                    ["monthly_fixed_cost", "Постоянные расходы"],
                    ["monthly_contribution", "Маржинальный доход"],
                  ].map(([key, label]) => (
                    <div key={key}>
                      <dt>{label}</dt>
                      <dd>
                        {rub(s.metrics[key as keyof typeof s.metrics].value)}
                      </dd>
                    </div>
                  ))}
                </dl>
                <div className="break-even">
                  <span>Безубыточность</span>
                  <b>
                    {s.metrics.break_even_sales_per_day.value}{" "}
                    <small>продаж / день</small>
                  </b>
                </div>
                {s.warnings.length > 0 && (
                  <p className="subtle">
                    {s.warnings.map(readable).join(" · ")}
                  </p>
                )}
              </article>
            ))}
          </div>
          <FinanceChart scenarios={result.scenarios} />
          <section className="detail-panel">
            <span className="eyebrow">ЧТО ЕСЛИ ИЗМЕНИТЬ ВВОДНЫЕ?</span>
            <h2>Чувствительность базового сценария</h2>
            <p className="subtle">
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
          </section>
          <details className="provenance">
            <summary>Формулы, происхождение и воспроизводимость</summary>
            <p>
              Алгоритм: {result.algorithm_version} · результат: modelled.
              Округление: {result.rounding}.
            </p>
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
          <div className="notice">
            Операционный результат — до неучтённых налогов, амортизации,
            процентов и кредитных платежей. Это не чистая прибыль и не денежный
            поток. Нет расчёта окупаемости и подтверждения доступности
            помещения.
          </div>
          <details className="provenance">
            <summary>Полные ограничения финансовой модели</summary>
            <ul>
              {[...result.limitations, ...result.warnings].map((t, i) => (
                <li key={i}>{t}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
    </div>
  );
}
