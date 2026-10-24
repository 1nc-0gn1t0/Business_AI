import { useEffect, useState } from "react";
import type { Dataset, Profile, Ranking, Schemas } from "./api";
import { date, errorText, request } from "./api";
import GeoMap from "./GeoMap";
import Walking from "./Walking";
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
};
export default function Locations(props: Props) {
  const [walkPoint, setWalkPoint] = useState<[number, number] | null>(null);
  function selectZone(id: string | null) {
    setWalkPoint(null);
    setWalking(null);
    props.onSelect(id);
  }
  const [walking, setWalking] = useState<Schemas["CatchmentResult"] | null>(
    null,
  );
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
  return (
    <div className="locations">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ГЕОГРАФИЯ ВАШЕГО БИЗНЕСА</span>
          <h1>
            {props.comparison ? "Сравнение локаций" : "Найдите место для идеи"}
          </h1>
          <p>Исследуйте зоны по проверяемым географическим признакам.</p>
        </div>
        <span className="tag outline">Казань · MVP</span>
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
        <div className="empty" role="status">
          Загружаем геоданные…
        </div>
      ) : !dataset ? (
        <div className="empty">
          <h2>Нет загруженных геоданных</h2>
          <p>
            Импортируйте набор OSM по инструкции README. Отсутствие объектов не
            означает отсутствие бизнеса.
          </p>
        </div>
      ) : (
        <>
          <div className="geo-toolbar">
            <label>
              Набор данных
              <select
                value={dataset.slug}
                disabled={busy}
                onChange={(e) => {
                  setDataset(datasets.find((d) => d.slug === e.target.value)!);
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
                    onChange={(e) =>
                      setWeights({ ...weights, [key]: Number(e.target.value) })
                    }
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
                onChange={(e) => setInterior(e.target.checked)}
              />
              Внутренняя область Казани: 49.065, 55.71 — 49.235, 55.84
            </label>
            <p>
              Ячейки 500 м, интервал 1000 м, радиус оценки 500 м по прямой. Веса
              по умолчанию равные; конкуренты нейтральны. Изменения применятся
              после «Пересчитать». Это сравнительная оценка OSM, не спрос и не
              прибыльность.
            </p>
          </details>
          {!props.comparison && (
            <Walking
              dataset={dataset}
              ranking={props.ranking}
              point={
                walkPoint ||
                (props.ranking?.candidates.features.find(
                  (f) => f.id === props.selected,
                )?.properties.representative_point.coordinates as
                  | [number, number]
                  | undefined) ||
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
          )}
          {!props.comparison && (
            <GeoMap
              key={`${dataset.slug}:${dataset.data_version}`}
              dataset={dataset}
              pois={pois}
              districts={districts}
              ranking={props.ranking}
              selected={props.selected}
              onSelect={selectZone}
              walking={walking}
              onPoint={(p) => {
                setWalking(null);
                setWalkPoint(p);
              }}
            />
          )}
          <div className="row source-strip">
            <span>
              <i className="dot mint-dot" /> OSM · {date(dataset.osm_base)}
              {dataset.stale ? " · данные устарели" : ""}
            </span>
            <span>
              {pois
                ? `${pois.returned_count} POI на карте${pois.next_offset != null ? " · выборка ограничена 500" : ""}`
                : "POI загружаются / недоступны"}{" "}
              · {dataset.poi_count.toLocaleString("ru-RU")} в наборе
            </span>
          </div>
          {!props.ranking && (
            <div className="empty compact">
              <span className="empty-symbol">⌖</span>
              <h3>Локация начинается с контекста</h3>
              <p>
                Подтвердите идею и запустите поиск. Здесь появятся
                зоны-кандидаты и прозрачное сравнение.
              </p>
            </div>
          )}
          {props.ranking && (
            <>
              <div className="row results-heading">
                <h2>
                  Зоны-кандидаты{" "}
                  <span className="count">
                    {props.ranking.candidates.features.length}
                  </span>
                </h2>
                <span className="subtle">
                  {props.ranking.status === "ok"
                    ? "Оценка рассчитана"
                    : "Данные ограничены"}{" "}
                  · не свободные помещения
                </span>
              </div>
              {(props.ranking.reasons.length > 0 ||
                props.ranking.candidates.reasons.length > 0) && (
                <div className="notice">
                  {[
                    ...props.ranking.reasons,
                    ...props.ranking.candidates.reasons,
                  ]
                    .map(readable)
                    .join(" · ")}
                </div>
              )}
              <div className="zone-grid">
                {features.map((f, i) => {
                  const e = props.ranking!.evaluations.find(
                    (v) => v.candidate_id === f.id,
                  );
                  return (
                    <button
                      className={`zone-card ${props.selected === f.id ? "chosen" : ""}`}
                      key={f.id}
                      onClick={() => selectZone(f.id)}
                      aria-pressed={props.selected === f.id}
                    >
                      <div className="row">
                        <span className="zone-number">
                          {e?.rank ? `#${e.rank}` : `Зона ${i + 1}`}
                        </span>
                        <strong className="score">
                          {e?.score == null
                            ? "Нет оценки"
                            : `${e.score.toFixed(1)}`}
                          <small>{e?.score != null ? "/ 100" : ""}</small>
                        </strong>
                      </div>
                      <h3>
                        {f.properties.anchor.properties.name ||
                          `Зона ${f.properties.grid_i} / ${f.properties.grid_j}`}
                      </h3>
                      <p>
                        {f.properties.representative_point.coordinates
                          .map((n) => n.toFixed(4))
                          .join(", ")}{" "}
                        · {(f.properties.area_m2 / 10000).toFixed(1)} га
                      </p>
                      {e && (
                        <div className="factor-list">
                          {e.components.map((c) => (
                            <div key={c.criterion}>
                              <span>{criteria[c.criterion]}</span>
                              <div className="bar">
                                <i
                                  style={{
                                    width: `${c.normalized == null ? 0 : c.normalized * 100}%`,
                                  }}
                                />
                              </div>
                              <b>
                                {c.normalized == null
                                  ? "—"
                                  : (c.normalized * 100).toFixed(0)}
                              </b>
                            </div>
                          ))}
                        </div>
                      )}
                      <span className="card-link">
                        {props.selected === f.id
                          ? "✓ Выбрана"
                          : "Подробнее о зоне →"}
                      </span>
                    </button>
                  );
                })}
              </div>
              {selected && (
                <section className="detail-panel">
                  <div className="row">
                    <div>
                      <span className="eyebrow">
                        ВЫБРАННАЯ ЗОНА · НЕ ПОМЕЩЕНИЕ
                      </span>
                      <h2>
                        {selected.properties.anchor.properties.name ||
                          selected.id.slice(0, 12)}
                      </h2>
                    </div>
                    <button
                      className="button secondary"
                      onClick={props.onFinance}
                    >
                      К финансовой модели →
                    </button>
                  </div>
                  {props.ranking.evaluations
                    .filter((e) => e.candidate_id === selected.id)
                    .map((e) => (
                      <div key={e.candidate_id}>
                        <div className="metrics-row">
                          <div>
                            <small>Остановки в 500 м</small>
                            <strong>{e.raw.transit_count}</strong>
                          </div>
                          <div>
                            <small>Ближайшая остановка</small>
                            <strong>
                              {e.raw.nearest_transit_m == null
                                ? "Нет данных"
                                : `${Math.round(e.raw.nearest_transit_m)} м`}
                            </strong>
                          </div>
                          <div>
                            <small>Конкуренты OSM</small>
                            <strong>{e.raw.competitor_count}</strong>
                          </div>
                          <div>
                            <small>Объекты окружения</small>
                            <strong>{e.raw.complementary_count}</strong>
                          </div>
                        </div>
                        <p className="subtle">
                          Расстояния по прямой. Неполнота OSM не равна
                          отсутствию объектов на местности.
                        </p>
                        <ul className="explanations">
                          {e.explanations.map((x) => (
                            <li key={x.criterion} className={x.effect}>
                              {x.text}
                            </li>
                          ))}
                        </ul>
                        <details>
                          <summary>
                            Исходные показатели, нормализация и происхождение
                          </summary>
                          <pre>
                            {JSON.stringify(
                              {
                                raw: e.raw,
                                components: e.components,
                                provenance: e.provenance,
                                missing_data: e.missing_data,
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </details>
                      </div>
                    ))}
                </section>
              )}
              <details className="provenance">
                <summary>Методология и ограничения результата</summary>
                <p>
                  Алгоритм: {props.ranking.algorithm_version}. Политика:{" "}
                  {props.ranking.policy.version}. Порядок: балл ↓, ID ↑ при
                  равенстве.
                </p>
                <p>{props.ranking.policy.weight_rationale}</p>
                <ul>
                  {props.ranking.limitations.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
                <pre>
                  {JSON.stringify(
                    {
                      fingerprint: props.ranking.request_fingerprint,
                      policy: props.ranking.policy,
                      request: props.ranking.candidates.request_snapshot,
                    },
                    null,
                    2,
                  )}
                </pre>
              </details>
            </>
          )}
          <details className="provenance">
            <summary>Источник и фактическое покрытие</summary>
            <p>
              <a
                href="https://www.openstreetmap.org/copyright"
                target="_blank"
                rel="noreferrer"
              >
                {dataset.attribution}
              </a>{" "}
              · {dataset.license}. Источник:{" "}
              <a href={dataset.source_url} target="_blank" rel="noreferrer">
                {dataset.source_name}
              </a>
            </p>
            <p>
              OSM: {date(dataset.osm_base)} · импорт:{" "}
              {date(dataset.imported_at)} · районов/полигонов:{" "}
              {dataset.district_count}
              {districts?.truncated ? " (показаны не все)" : ""}.
            </p>
            <p>
              Версия: <code>{dataset.data_version}</code>. Жёлтый контур —
              граница сохранённой выборки, а не всего города.
            </p>
            <ul>
              {dataset.limitations.map((t) => (
                <li key={t}>{t}</li>
              ))}
            </ul>
          </details>
        </>
      )}
    </div>
  );
}
