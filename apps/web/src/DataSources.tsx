import { useEffect, useState } from "react";
import { date, errorText, request } from "./api";
import type { Schemas } from "./api";

type Mode = "real" | "demo";
type Provider = Schemas["ProviderInfo"];
type Dataset = Schemas["ProviderDataset"];
const metrics = [
  "mapped_poi_count",
  "mapped_cafe_count",
  "pedestrian_flow_daily",
  "rent_monthly_rub",
  "purchases_daily",
];
export default function DataSources() {
  const [mode, setMode] = useState<Mode>("real");
  const [policy, setPolicy] = useState<Schemas["DataPolicy"] | null>(null);
  const [sources, setSources] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("osm");
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState("");
  const [result, setResult] = useState<Schemas["IndicatorResult"] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const c = new AbortController();
    Promise.all([
      request<Schemas["DataPolicy"]>("/api/v1/data-providers/policy", {
        signal: c.signal,
      }),
      request<Provider[]>("/api/v1/data-providers/sources", {
        signal: c.signal,
      }),
    ])
      .then(([p, s]) => {
        if (c.signal.aborted) return;
        setPolicy(p);
        setSources(s);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(errorText(e));
      });
    return () => c.abort();
  }, [reload]);
  useEffect(() => {
    const c = new AbortController();
    request<Dataset[]>(`/api/v1/data-providers/${provider}/datasets`, {
      signal: c.signal,
    })
      .then((items) => {
        if (c.signal.aborted) return;
        setDatasets(items);
        setSelected(items.find((d) => d.active)?.data_version || "");
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(errorText(e));
      });
    return () => c.abort();
  }, [provider, mode, reload]);
  async function changeMode(next: Mode) {
    setResult(null);
    setDatasets([]);
    setSelected("");
    setError("");
    setBusy(true);
    try {
      const p = await request<Schemas["DataPolicy"]>(
        "/api/v1/data-providers/selection",
        { method: "POST", body: { mode: next } },
      );
      setPolicy(p);
      setMode(next);
      setProvider("osm");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  async function load() {
    const dataset = datasets.find((d) => d.data_version === selected);
    if (!dataset) return;
    setBusy(true);
    setResult(null);
    setError("");
    try {
      setResult(
        await request<Schemas["IndicatorResult"]>(
          "/api/v1/data-providers/indicators",
          {
            method: "POST",
            body: {
              provider,
              dataset: dataset.slug,
              data_version: selected,
              mode,
              metrics,
            },
          },
        ),
      );
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="panel data-sources">
      <summary>Источники и происхождение показателей</summary>
      <p>
        Отдельный просмотр источников. Выбор здесь не изменяет карту, георейтинг
        или финансовые вводные. Значения разных наборов не объединяются.
      </p>
      {error && (
        <div role="alert" className="alert">
          {error}
        </div>
      )}
      <div className="source-controls">
        <label>
          Режим данных
          <select
            aria-label="Режим данных"
            value={mode}
            disabled={busy || !policy}
            onChange={(e) => void changeMode(e.target.value as Mode)}
          >
            <option value="real">Реальные источники</option>
            <option value="demo" disabled={!policy?.demo_enabled}>
              Демо: разрешить синтетические данные
            </option>
          </select>
        </label>
        <label>
          Источник показателей
          <select
            aria-label="Источник показателей"
            value={provider}
            disabled={busy}
            onChange={(e) => {
              setProvider(e.target.value);
              setDatasets([]);
              setSelected("");
              setResult(null);
              setError("");
            }}
          >
            {sources.map((s) => (
              <option
                key={s.id}
                value={s.id}
                disabled={
                  s.id === "synthetic" &&
                  (mode !== "demo" || s.status !== "ready")
                }
              >
                {s.name}
                {s.status !== "ready" ? " · не подключён" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          Версия источника
          <select
            aria-label="Версия источника"
            value={selected}
            disabled={busy || !datasets.length}
            onChange={(e) => {
              setSelected(e.target.value);
              setResult(null);
            }}
          >
            {!datasets.length && (
              <option value="">Нет загруженных наборов</option>
            )}
            {datasets.map((d) => (
              <option
                key={`${d.slug}:${d.data_version}`}
                value={d.data_version}
              >
                {d.slug} · {d.data_version.slice(0, 8)}
                {d.active ? " · текущая" : " · история"}
                {d.stale ? " · устарела" : ""}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p>{sources.find((s) => s.id === provider)?.limitations.join(" ")}</p>
      {!policy?.demo_enabled && (
        <p>Демонстрационные данные отключены сервером.</p>
      )}
      <button
        className="button secondary"
        disabled={busy || !selected}
        onClick={() => void load()}
      >
        {busy ? "Загрузка…" : "Показать показатели источника"}
      </button>
      <button
        className="text-button"
        disabled={busy}
        onClick={() => {
          setResult(null);
          setError("");
          setReload((v) => v + 1);
        }}
      >
        Обновить список источников
      </button>
      {result && (
        <div className="source-result">
          <p className="tag outline">
            {result.dataset.origin === "synthetic"
              ? "СИНТЕТИЧЕСКИЕ ДАННЫЕ · НЕ РЫНОК КАЗАНИ"
              : "ОТКРЫТЫЕ ДАННЫЕ OSM · ПОЛНОТА НЕИЗВЕСТНА"}
          </p>
          <p>
            {result.dataset.source_name} · {result.dataset.license} ·{" "}
            {result.dataset.attribution}
          </p>
          <p>
            {result.dataset.observed_at
              ? "Срез OSM (не полевая проверка)"
              : "Сгенерировано"}
            : {date(result.dataset.observed_at || result.dataset.generated_at)}
            {result.dataset.stale ? " · УСТАРЕЛО" : ""}
          </p>
          <p className="source-scroll-hint">
            Прокрутите таблицу вправо, чтобы увидеть значения и происхождение →
          </p>
          <div
            className="table-scroll"
            role="region"
            aria-label="Показатели и происхождение"
            tabIndex={0}
          >
            <table>
              <thead>
                <tr>
                  <th>Показатель</th>
                  <th>Значение</th>
                  <th>Происхождение</th>
                </tr>
              </thead>
              <tbody>
                {result.indicators.map((i) => (
                  <tr key={i.metric}>
                    <td>
                      {i.name}
                      <small>{i.reason}</small>
                    </td>
                    <td>
                      {i.measurement
                        ? `${i.measurement.value.toLocaleString("ru-RU")} ${i.unit}`
                        : "Нет данных"}
                      {i.status === "stale" && " · устарело"}
                    </td>
                    <td>
                      {i.measurement?.origin || "отсутствует"}
                      {i.measurement?.origin === "synthetic" && (
                        <strong> · ДОПУЩЕНИЕ</strong>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details>
            <summary>Provenance, область, версии и ограничения</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
          <p>{result.limitations.join(" ")}</p>
        </div>
      )}
    </details>
  );
}
