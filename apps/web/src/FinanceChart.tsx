import type { Schemas } from "./api";
import { rub } from "./api";

export default function FinanceChart({
  scenarios,
}: {
  scenarios: Schemas["ScenarioResult"][];
}) {
  // Only scales API values for display; no financial formulas run in the browser.
  const max = Math.max(
    1,
    ...scenarios.map((s) => Math.abs(Number(s.metrics.operating_result.value))),
  );
  const names = {
    conservative: "Консервативный",
    base: "Базовый",
    optimistic: "Оптимистичный",
  };
  return (
    <section
      className="detail-panel operating-chart"
      aria-label="График операционных результатов"
    >
      <span className="eyebrow">СРАВНЕНИЕ СЦЕНАРИЕВ</span>
      <h2>Операционный результат в месяц</h2>
      <p className="subtle">
        Расчёт по сценарным допущениям. Нулевая линия разделяет отрицательный и
        положительный результат.
      </p>
      {scenarios.map((s) => {
        const value = Number(s.metrics.operating_result.value);
        return (
          <div className="chart-row" key={s.name}>
            <span>{names[s.name]}</span>
            <div className="chart-track">
              <i
                className={value < 0 ? "loss" : "gain"}
                style={{
                  width: `${(Math.abs(value) / max) * 48}%`,
                  left: value < 0 ? undefined : "50%",
                  right: value < 0 ? "50%" : undefined,
                }}
              />
            </div>
            <strong className={value < 0 ? "negative" : "positive"}>
              {rub(s.metrics.operating_result.value)}
            </strong>
          </div>
        );
      })}
      <h3 className="chart-heading">Продажи в день и точка безубыточности</h3>
      <p className="subtle">
        Бирюзовый — продажи по допущению, отметка — порог безубыточности из API.
        Не прогноз спроса.
      </p>
      {scenarios.map((s) => {
        const sales = s.inputs.sales_per_day.value;
        const threshold = Number(s.metrics.break_even_sales_per_day.value);
        const extent = Math.max(
          1,
          ...scenarios.flatMap((v) => [
            v.inputs.sales_per_day.value,
            Number(v.metrics.break_even_sales_per_day.value),
          ]),
        );
        return (
          <div className="chart-row" key={`break-even:${s.name}`}>
            <span>{names[s.name]}</span>
            <div className="sales-track">
              <i style={{ width: `${(sales / extent) * 100}%` }} />
              <b style={{ left: `${(threshold / extent) * 100}%` }} />
            </div>
            <strong>
              {sales} / {threshold}
            </strong>
          </div>
        );
      })}
    </section>
  );
}
