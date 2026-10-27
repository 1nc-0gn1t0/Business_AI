import { useEffect, useState } from "react";
import type { Dataset, Profile, Ranking, Schemas } from "./api";
import { date, errorText, request } from "./api";
import GeoMap from "./GeoMap";
import Walking from "./Walking";
import DataSources from "./DataSources";
import { readable } from "./labels";

export const criteria: Record<string, string> = {
  transit: "Транспорт",
  infrastructure: "Инфраструктура",
  complementary: "Окружение",
  competitors: "Конкуренты",
};
type Props = {
  profile: Profile | null;
  ranking: Ranking | null;
  onRanking: (r: Ranking | null) => void;
  selected: string | null;
  onSelect: (id: string | null) => void;
  comparison: boolean;
  onFinance: () => void;
  onWalkingReport?: (value: Schemas["CatchmentResult"] | null) => void;
  onProviderReport?: (value: Schemas["IndicatorResult"] | null) => void;
};
export default function Locations(props: Props) {
  function invalidateAnalysis() {
    props.onRanking(null);
    props.onSelect(null);
    setWalking(null);
    setWalkPoint(null);
  }
  const [walkPoint, setWalkPoint] = useState<[number, number] | null>(null);
  function selectZone(id: string | null) {
    setWalkPoint(null);
    setWalking(null);
    props.onSelect(id);
  }
  const [walking, setWalking] = useState<Schemas["CatchmentResult"] | null>(
    null,
  );
  const onWalkingReport = props.onWalkingReport;
  useEffect(() => {
    onWalkingReport?.(walking);
  }, [walking, onWalkingReport]);
  useEffect(() => () => onWalkingReport?.(null), [onWalkingReport]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [pois, setPois] = useState<Schemas["POICollection"] | null>(null);
  const [districts, setDistricts] = useState<
    Schemas["DistrictCollection"] | null
  >(null);
  const [category, setCategory] = useState("amenity:cafe");
  const [weights, setWeights] = useState({
    transit: 1,
    infrastructure: 1,
    complementary: 1,
    competitors: 0,
  });
  const [mode, setMode] = useState<"neutral" | "cluster" | "separation">(
    "neutral",
  );
  const [interior, setInterior] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    request<Dataset[]>("/api/v1/geo/datasets", { signal: controller.signal })
      .then((items) => {
        setDatasets(items);
        setDataset(
          items.find((d) => d.slug === "kazan-centre") || items[0] || null,
        );
        setLoading(false);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setLoading(false);
        }
      });
    return () => controller.abort();
  }, [reload]);
  useEffect(() => {
    if (!dataset) return;
    const controller = new AbortController();
    const base = `/api/v1/geo/${dataset.slug}`;
    const b = dataset.bbox;
    request<Schemas["POICollection"]>(
      `${base}/pois?bbox=${b.west},${b.south},${b.east},${b.north}&category=${encodeURIComponent(category)}&limit=500&data_version=${dataset.data_version}`,
      { signal: controller.signal },
    )
      .then(setPois)
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setPois(null);
        }
      });
    request<Schemas["DistrictCollection"]>(
      `${base}/districts?data_version=${dataset.data_version}`,
      { signal: controller.signal },
    )
      .then(setDistricts)
      .catch((e) => {
        if (!controller.signal.aborted) {
          setError(errorText(e));
          setDistricts(null);
        }
      });
    return () => controller.abort();
  }, [dataset, category]);
  const [operation, setOperation] = useState<AbortController | null>(null);
  useEffect(() => () => operation?.abort(), [operation]);
  async function analyze(searchBounds?: Schemas["Bounds"]) {
    if (!dataset || !props.profile) return;
    const controller = new AbortController();
    setOperation(controller);
    setBusy(true);
    setError("");
    props.onRanking(null);
    setWalking(null);
    setWalkPoint(null);
    props.onSelect(null);
    try {
      const result = await request<Ranking>(
        `/api/v1/geo/${dataset.slug}/rankings`,
        {
          method: "POST",
          signal: controller.signal,
          body: {
            candidates: {
              profile: props.profile,
              data_version: dataset.data_version,
              limit: 5,
              cell_size_m: 500,
              min_separation_m: 1000,
              ...(searchBounds
                ? { search_bbox: searchBounds }
                : interior && dataset.slug === "kazan-centre"
                  ? {
                      search_bbox: {
                        west: 49.065,
                        south: 55.71,
                        east: 49.235,
                        north: 55.84,
                      },
                    }
                  : {}),
            },
            scoring: {
              version: "osm-relative-v1",
              radius_m: 500,
              weights,
              competitor_mode: mode,
            },
          },
        },
      );
      props.onRanking(result);
      props.onSelect(
        result.evaluations.find((e) => e.rank === 1)?.candidate_id ||
          result.candidates.features[0]?.id ||
          null,
      );
    } catch (e) {
      if (!controller.signal.aborted) setError(errorText(e));
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  }
  const selected = props.ranking?.candidates.features.find(
    (f) => f.id === props.selected,
  );
  const features = [...(props.ranking?.candidates.features || [])].sort(
    (a, b) => {
      const rank = (id: string) =>
        props.ranking?.evaluations.find((e) => e.candidate_id === id)?.rank ??
        Infinity;
      return rank(a.id) - rank(b.id) || a.id.localeCompare(b.id);
    },
  );
  const evaluation = props.ranking?.evaluations.find(
    (e) => e.candidate_id === props.selected,
  );
  return (
    <section className="locations">
      <div className="section-heading">
        <h1>
          Где лучше открыть <br />
          ваш бизнес?
        </h1>
        <p>
          Выберите зону для исследования. Это не предложение свободного
          помещения.
        </p>
      </div>
      {error && (
        <div className="alert" role="alert">
          {error}
          <button
            className="text-button"
            onClick={() => {
              setError("");
              setReload((v) => v + 1);
            }}
          >
            Повторить загрузку
          </button>
        </div>
      )}
      {loading ? (
        <p role="status">Загружаем локации…</p>
      ) : !dataset ? (
        <div className="empty">
          <h2>Нет загруженных геоданных</h2>
          <p>
            Для этой территории анализ пока недоступен. Вернитесь к профилю,
            чтобы проверить город.
          </p>
        </div>
      ) : (
        <>
          <div className="location-toolbar">
            <p>
              {dataset.city} · покрытие части города
              {dataset.stale ? " · данные устарели" : ""}
            </p>
            {!props.ranking && (
              <button
                className="button"
                disabled={
                  busy || props.profile?.confirmation_state !== "confirmed"
                }
                onClick={() => void analyze()}
              >
                {busy ? "Ищем локации…" : "Найти локации"}
              </button>
            )}
            {props.ranking && (
              <span>
                {features.length
                  ? `${features.length} зон для сравнения`
                  : "Подходящие зоны не найдены"}
              </span>
            )}
          </div>
          <div className="location-layout">
            <GeoMap
              key={`${dataset.slug}:${dataset.data_version}`}
              dataset={dataset}
              pois={pois}
              districts={districts}
              ranking={props.ranking}
              selected={props.selected}
              onSelect={selectZone}
              walking={walking}
              onPoint={(point) => {
                setWalking(null);
                setWalkPoint(point);
              }}
            />
            {features.length > 0 && (
              <div className="zone-list" aria-label="Зоны-кандидаты">
                {features.map((f, i) => {
                  const e = props.ranking?.evaluations.find(
                    (v) => v.candidate_id === f.id,
                  );
                  return (
                    <button
                      className={`zone-card ${props.selected === f.id ? "chosen" : ""}`}
                      key={f.id}
                      onClick={() => selectZone(f.id)}
                      aria-pressed={props.selected === f.id}
                    >
                      <span className="zone-number">
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      <div>
                        <h2>
                          {f.properties.anchor.properties.name ||
                            `Зона ${i + 1}`}
                        </h2>
                        <p>
                          {(f.properties.area_m2 / 10000).toFixed(1)} га ·{" "}
                          {e?.score == null
                            ? "Недостаточно данных для оценки"
                            : `${e.score.toFixed(1)} / 100 по геопризнакам`}
                        </p>
                        <span className="selection-label">
                          {props.selected === f.id
                            ? "✓ Выбрана"
                            : "Выбрать зону"}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
          <p className="fine-print">
            OpenStreetMap · {date(dataset.osm_base)}. Сравнительная геооценка,
            не прогноз спроса или прибыльности.
            {pois?.next_offset != null ? " На карте показаны не все POI." : ""}
            {props.ranking?.status && props.ranking.status !== "ok"
              ? " Покрытие данных ограничено."
              : ""}
          </p>
          <details className="analysis-options">
            <summary>Подробнее о зоне и анализе</summary>
            {selected && evaluation && (
              <section className="zone-detail">
                <h2>
                  {selected.properties.anchor.properties.name ||
                    "Выбранная зона"}
                </h2>
                <dl className="metrics-row">
                  <div>
                    <dt>Остановки в 500 м</dt>
                    <dd>{evaluation.raw.transit_count}</dd>
                  </div>
                  <div>
                    <dt>Ближайшая остановка</dt>
                    <dd>
                      {evaluation.raw.nearest_transit_m == null
                        ? "Нет данных"
                        : `${Math.round(evaluation.raw.nearest_transit_m)} м`}
                    </dd>
                  </div>
                  <div>
                    <dt>Конкуренты OSM</dt>
                    <dd>{evaluation.raw.competitor_count}</dd>
                  </div>
                  <div>
                    <dt>Объекты окружения</dt>
                    <dd>{evaluation.raw.complementary_count}</dd>
                  </div>
                </dl>
                <p className="fine-print">
                  Расстояния по прямой. Неполнота OSM не означает отсутствия
                  объектов.
                </p>
                <ul>
                  {evaluation.explanations.map((x) => (
                    <li key={x.criterion}>{x.text}</li>
                  ))}
                </ul>
                <div className="factor-list">
                  {evaluation.components.map((c) => (
                    <p key={c.criterion}>
                      {criteria[c.criterion]}:{" "}
                      {c.normalized == null
                        ? "Нет данных"
                        : (c.normalized * 100).toFixed(0)}
                    </p>
                  ))}
                </div>
                <details>
                  <summary>Исходные показатели и происхождение</summary>
                  <pre>
                    {JSON.stringify(
                      {
                        raw: evaluation.raw,
                        components: evaluation.components,
                        provenance: evaluation.provenance,
                        missing_data: evaluation.missing_data,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </details>
              </section>
            )}
            {props.ranking && (
              <>
                <h2>Как сравниваются зоны</h2>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Зона</th>
                        <th>Оценка</th>
                        {Object.values(criteria).map((c) => (
                          <th key={c}>{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {features.map((f, i) => {
                        const e = props.ranking?.evaluations.find(
                          (v) => v.candidate_id === f.id,
                        );
                        return (
                          <tr key={f.id}>
                            <td>
                              {f.properties.anchor.properties.name ||
                                `Зона ${i + 1}`}
                            </td>
                            <td>{e?.score?.toFixed(1) ?? "Нет данных"}</td>
                            {Object.keys(criteria).map((key) => (
                              <td key={key}>
                                {e?.components.find((c) => c.criterion === key)
                                  ?.normalized == null
                                  ? "—"
                                  : (
                                      e!.components.find(
                                        (c) => c.criterion === key,
                                      )!.normalized! * 100
                                    ).toFixed(0)}
                              </td>
                            ))}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <ul>
                  {[
                    ...props.ranking.reasons,
                    ...props.ranking.candidates.reasons,
                  ].map((t, i) => (
                    <li key={i}>{readable(t)}</li>
                  ))}
                </ul>
                <ul>
                  {props.ranking.limitations.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
                <p>
                  Алгоритм: {props.ranking.algorithm_version}.{" "}
                  {props.ranking.policy.weight_rationale}
                </p>
              </>
            )}
            <details>
              <summary>Настройки анализа</summary>
              <div className="geo-toolbar">
                <label>
                  Набор данных
                  <select
                    value={dataset.slug}
                    disabled={busy}
                    onChange={(e) => {
                      setDataset(
                        datasets.find((d) => d.slug === e.target.value)!,
                      );
                      setWalking(null);
                      setWalkPoint(null);
                      setPois(null);
                      setDistricts(null);
                      props.onRanking(null);
                      props.onSelect(null);
                    }}
                  >
                    {datasets.map((d) => (
                      <option key={d.slug} value={d.slug}>
                        {d.city} · {d.slug}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Объекты на карте
                  <select
                    value={category}
                    onChange={(e) => {
                      setPois(null);
                      setCategory(e.target.value);
                    }}
                  >
                    <option value="amenity:cafe">Кафе</option>
                    <option value="highway:bus_stop">Остановки</option>
                    <option value="shop:supermarket">Супермаркеты</option>
                    <option value="amenity:pharmacy">Аптеки</option>
                  </select>
                </label>
                <button
                  className="button"
                  disabled={
                    busy || props.profile?.confirmation_state !== "confirmed"
                  }
                  onClick={() => void analyze()}
                >
                  {busy
                    ? "Анализируем…"
                    : props.ranking
                      ? "Пересчитать зоны ↗"
                      : "Найти зоны →"}
                </button>
              </div>
              {props.profile?.confirmation_state !== "confirmed" && (
                <p className="notice">
                  Сначала заполните и подтвердите профиль в AI-чате.
                </p>
              )}
              <details className="settings">
                <summary>Параметры поиска и веса оценки</summary>
                <div className="settings-grid">
                  {Object.entries(weights).map(([key, value]) => (
                    <label key={key}>
                      {criteria[key]}
                      <input
                        aria-label={`Вес: ${criteria[key]}`}
                        type="number"
                        min="0"
                        max="100"
                        step="0.1"
                        value={value}
                        disabled={
                          busy || (key === "competitors" && mode === "neutral")
                        }
                        onChange={(e) => {
                          invalidateAnalysis();
                          setWeights({
                            ...weights,
                            [key]: Number(e.target.value),
                          });
                        }}
                      />
                    </label>
                  ))}
                  <label>
                    Роль конкурентов
                    <select
                      value={mode}
                      disabled={busy}
                      onChange={(e) => {
                        const m = e.target.value as typeof mode;
                        invalidateAnalysis();
                        setMode(m);
                        setWeights((w) => ({
                          ...w,
                          competitors: m === "neutral" ? 0 : 1,
                        }));
                      }}
                    >
                      <option value="neutral">Без влияния на балл</option>
                      <option value="cluster">Признак кластера</option>
                      <option value="separation">Меньше конкурентов</option>
                    </select>
                  </label>
                </div>
                <label className="check-label">
                  <input
                    type="checkbox"
                    checked={interior}
                    disabled={busy}
                    onChange={(e) => {
                      invalidateAnalysis();
                      setInterior(e.target.checked);
                    }}
                  />
                  Внутренняя область Казани: 49.065, 55.71 — 49.235, 55.84
                </label>
                <p>
                  Ячейки 500 м, интервал 1000 м, радиус оценки 500 м по прямой.
                  Веса по умолчанию равные; конкуренты нейтральны. Изменения
                  применятся после «Пересчитать». Это сравнительная оценка OSM,
                  не спрос и не прибыльность.
                </p>
              </details>
              {
                <details className="walking-disclosure">
                  <summary>Пешеходная доступность по дорожной сети</summary>
                  <Walking
                    dataset={dataset}
                    ranking={props.ranking}
                    point={
                      walkPoint ||
                      (props.ranking?.candidates.features.find(
                        (f) => f.id === props.selected,
                      )?.properties.representative_point.coordinates as
                        [number, number] | undefined) ||
                      null
                    }
                    result={walking}
                    onSearchBounds={
                      props.profile?.confirmation_state === "confirmed" && !busy
                        ? (b) => {
                            void analyze(b);
                          }
                        : undefined
                    }
                    onPoint={setWalkPoint}
                    onResult={setWalking}
                  />
                </details>
              }
            </details>
            <details>
              <summary>Источник и фактическое покрытие</summary>
              <p>
                <a
                  href="https://www.openstreetmap.org/copyright"
                  target="_blank"
                  rel="noreferrer"
                >
                  {dataset.attribution}
                </a>{" "}
                · {dataset.license}
              </p>
              <p>
                <a href={dataset.source_url} target="_blank" rel="noreferrer">
                  {dataset.source_name}
                </a>{" "}
                · {dataset.data_version} · импорт {date(dataset.imported_at)}
              </p>
              <p>
                {dataset.poi_count.toLocaleString("ru-RU")} POI в наборе,{" "}
                {pois?.returned_count ?? 0} в выборке карты. Граница сохранённой
                выборки не равна границе всего города.
              </p>
              <ul>
                {dataset.limitations.map((t) => (
                  <li key={t}>{t}</li>
                ))}
              </ul>
            </details>
            <DataSources onReport={props.onProviderReport} />
          </details>
        </>
      )}
    </section>
  );
}
