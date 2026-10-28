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
    conservative: "Пессимистичный",
    base: "Базовый",
    optimistic: "Оптимистичный",
  };
  return (
    <section
      className="detail-panel operating-chart"
      aria-label="График операционных результатов"
    >
      <h2 className="sr-only">Сравнение сценариев</h2>
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
    </section>
  );
}
