import { useEffect, useRef, useState } from "react";
import { ApiError, date, errorText, request } from "./api";
import type { Dataset, Ranking, Schemas } from "./api";

type Result = Schemas["CatchmentResult"];
export default function Walking({
  dataset,
  point,
  ranking,
  result,
  onPoint,
  onResult,
  onSearchBounds,
}: {
  dataset: Dataset;
  point: [number, number] | null;
  ranking: Ranking | null;
  result: Result | null;
  onPoint: (p: [number, number]) => void;
  onResult: (r: Result | null) => void;
  onSearchBounds?: (bbox: Schemas["Bounds"]) => void;
}) {
  const [graph, setGraph] = useState<Schemas["WalkGraphView"] | null>(null);
  const [distance, setDistance] = useState(600);
  const [snap, setSnap] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");
  const [comparison, setComparison] = useState<
    Schemas["WalkingRankingResult"] | null
  >(null);
  useEffect(() => {
    const c = new AbortController();
    request<Schemas["WalkGraphView"] | null>(
      `/api/v1/geo/${dataset.slug}/walking-graph`,
      { signal: c.signal },
    )
      .then(setGraph)
      .catch((e) => {
        if (!c.signal.aborted) setError(errorText(e));
      });
    return () => c.abort();
  }, [dataset.slug]);
  const latestPoint = useRef(point);
  useEffect(() => {
    latestPoint.current = point;
  });
  async function calculate(compare = false) {
    if (!point && !compare) return;
    setBusy(true);
    setError("");
    try {
      if (compare && ranking) {
        setComparison(null);
        const response = await request<Schemas["WalkingRankingResult"]>(
          `/api/v1/geo/${dataset.slug}/walking-rankings`,
          {
            method: "POST",
            body: {
              ranking: {
                candidates: ranking.candidates.request_snapshot,
                scoring: ranking.policy.config,
              },
              max_snap_m: snap,
              graph_version: graph?.graph_version,
            },
          },
        );
        setComparison(response);
      } else if (point) {
        onResult(null);
        const response = await request<Result>(
          `/api/v1/geo/${dataset.slug}/catchment`,
          {
            method: "POST",
            body: {
              longitude: point[0],
              latitude: point[1],
              distance_m: distance,
              max_snap_m: snap,
              data_version: dataset.data_version,
              graph_version: graph?.graph_version,
            },
          },
        );
        if (
          latestPoint.current?.[0] === point[0] &&
          latestPoint.current?.[1] === point[1]
        )
          onResult(response);
      }
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 422
          ? "Проверьте вводные: бюджет — целое число 50–2000 м, соединитель — 0–100 м; координаты WGS84 должны быть допустимыми."
          : errorText(e),
      );
    } finally {
      setBusy(false);
    }
  }
  const stale =
    result &&
    (result.request_snapshot.longitude !== point?.[0] ||
      result.request_snapshot.latitude !== point?.[1] ||
      result.request_snapshot.distance_m !== distance ||
      result.request_snapshot.max_snap_m !== snap);
  const calculated = result?.status === "ok" || result?.status === "partial";
  const statusText: Record<Result["status"], string> = {
    ok: "Бюджет внутри границ выгрузки; полнота картирования неизвестна.",
    partial: "Доступна только ограниченная оценка по загруженным данным.",
    graph_unavailable: "Дорожный граф не загружен.",
    outside_coverage: "Начальная точка вне загруженного дорожного покрытия.",
    no_network_access:
      "Не найдена подходящая дорога в пределах лимита привязки.",
    resource_limit:
      "Для этого бюджета превышен лимит объёма расчёта. Уменьшите расстояние.",
  };
  return (
    <section className="walking-panel" aria-label="Пешеходная доступность">
      <div className="row">
        <div>
          <span className="eyebrow">WALKING NETWORK · OSM</span>
          <h2>Пешком по дорожной сети</h2>
        </div>
        <span className="tag">BA-013</span>
      </div>
      <p>
        Выберите зону или нажмите на свободное место карты. Расчёт от
        представительной точки, а не от всех мест зоны. Фиолетовые линии —
        достижимые отрезки; бирюзовые точки — POI в сетевом бюджете.
      </p>
      {!graph && (
        <p className="notice">
          Дорожный граф не загружен или недоступен. Прежняя карта и рейтинг по
          прямой продолжают работать. Прямые расстояния не подставляются вместо
          маршрутов.
        </p>
      )}
      {graph && (
        <p className="subtle">
          {graph.edge_count.toLocaleString("ru-RU")} отрезков ·{" "}
          {graph.component_count} компонентов · OSM{" "}
          {date(graph.manifest.osm_base)} · покрытие только{" "}
          {graph.manifest.bbox.west}, {graph.manifest.bbox.south} —{" "}
          {graph.manifest.bbox.east}, {graph.manifest.bbox.north}
        </p>
      )}
      <div className="walking-controls">
        {onSearchBounds && (
          <button
            className="button secondary"
            disabled={busy || !graph}
            onClick={() => {
              if (!graph) return;
              const b = graph.manifest.bbox;
              const x = (b.east - b.west) / 6,
                y = (b.north - b.south) / 6;
              onSearchBounds({
                west: b.west + x,
                south: b.south + y,
                east: b.east - x,
                north: b.north - y,
              });
            }}
          >
            Найти зоны во внутренней области графа
          </button>
        )}
        <label>
          Пешеходный бюджет, м
          <input
            type="number"
            min="50"
            max="2000"
            step="50"
            value={distance}
            disabled={busy}
            onChange={(e) => {
              setDistance(Number(e.target.value));
              onResult(null);
            }}
          />
        </label>
        <label>
          Максимальный соединитель, м
          <input
            type="number"
            min="0"
            max="100"
            value={snap}
            disabled={busy}
            onChange={(e) => {
              setSnap(Number(e.target.value));
              onResult(null);
              setComparison(null);
            }}
          />
        </label>
        <button
          className="button secondary"
          disabled={busy || !graph}
          onClick={() => {
            if (graph) {
              const b = graph.manifest.bbox;
              onResult(null);
              onPoint([(b.west + b.east) / 2, (b.south + b.north) / 2]);
            }
          }}
        >
          Точка в центре дорожного покрытия
        </button>
        <button
          className="button"
          disabled={busy || !point || !graph}
          onClick={() => void calculate()}
        >
          {busy ? "Расчёт…" : "Рассчитать пешую доступность →"}
        </button>
      </div>
      <p className="subtle">
        Начальная точка:{" "}
        {point
          ? `${point[0].toFixed(6)}, ${point[1].toFixed(6)}`
          : "не выбрана"}
        . Соединители — отрезки по прямой к сети, а не проверенные входы или
        проходы через ограждения. Уменьшите лимит до 0 для точки точно на сети.
      </p>
      <details>
        <summary>Задать точку координатами WGS84</summary>
        <div className="walking-controls">
          <label>
            Долгота точки
            <input
              type="number"
              step="any"
              value={lon}
              onChange={(e) => setLon(e.target.value)}
            />
          </label>
          <label>
            Широта точки
            <input
              type="number"
              step="any"
              value={lat}
              onChange={(e) => setLat(e.target.value)}
            />
          </label>
          <button
            className="button secondary"
            disabled={
              busy ||
              !lon ||
              !lat ||
              !Number.isFinite(Number(lon)) ||
              !Number.isFinite(Number(lat))
            }
            onClick={() => {
              onResult(null);
              onPoint([Number(lon), Number(lat)]);
            }}
          >
            Использовать координаты
          </button>
        </div>
      </details>
      {error && (
        <div role="alert" className="alert">
          {error}
        </div>
      )}
      {result && !stale && (
        <div aria-label="Результат пешеходного анализа">
          <div className="walking-stats">
            <div>
              <strong>{calculated ? result.reachable_poi_count : "—"}</strong>
              <small>POI по сети + соединители</small>
            </div>
            <div>
              <strong>
                {calculated ? result.straight_line_poi_count : "—"}
              </strong>
              <small>POI в радиусе по прямой</small>
            </div>
            <div>
              <strong>{calculated ? result.unsnapped_poi_count : "—"}</strong>
              <small>Не удалось привязать к сети</small>
            </div>
            <div>
              <strong>{result.runtime_ms.toFixed(0)} мс</strong>
              <small>Серверный расчёт</small>
            </div>
          </div>
          <p className="notice">
            {statusText[result.status]}{" "}
            {result.on_largest_component === false &&
              `Привязка к отдельной компоненте (${result.source_component_nodes ?? "неизвестно"} узлов); численный рейтинг для неё отключён. `}
            {!result.fully_covered &&
              calculated &&
              "Часть бюджета выходит за покрытие; количества являются нижними границами. "}
            Нет маршрута в загруженном графе — не доказательство физической
            недоступности. Привязка старта: {result.source_snap_m ?? "—"} м.
            Маршрут в пределах бюджета не найден в выгрузке до{" "}
            {calculated
              ? result.no_route_in_loaded_graph_count
              : "неизвестного числа"}{" "}
            POI.
          </p>
          <details>
            <summary>Категории доступных POI · расстояния · источники</summary>
            <div className="walking-counts">
              {Object.entries(result.category_counts || {}).map(([k, v]) => (
                <span className="tag" key={k}>
                  {k}: {v}
                </span>
              ))}
            </div>
            <table>
              <thead>
                <tr>
                  <th>Объект OSM</th>
                  <th>По прямой</th>
                  <th>По сети + соединители</th>
                </tr>
              </thead>
              <tbody>
                {(result.pois?.features || []).slice(0, 20).map((p) => (
                  <tr key={p.id}>
                    <td>{String(p.properties.name || p.id)}</td>
                    <td>
                      {Number(p.properties.straight_line_distance_m).toFixed(1)}{" "}
                      м
                    </td>
                    <td>
                      {Number(p.properties.network_distance_m).toFixed(1)} м
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <small>
              Первые 20 объектов; полный набор отрисован на карте. Это POI, не
              измеренные аудитория или спрос.
            </small>
            <pre>
              {JSON.stringify(
                {
                  algorithm: result.algorithm_version,
                  graph: result.graph,
                  poi_data_version: result.poi_data_version,
                  fingerprint: result.request_fingerprint,
                  limitations: result.limitations,
                },
                null,
                2,
              )}
            </pre>
          </details>
        </div>
      )}
      {ranking && (
        <details className="walking-comparison">
          <summary>Сравнить рейтинг BA-008: по прямой и по сети</summary>
          <p>
            Отдельный режим, исходный рейтинг не изменяется. Те же веса и радиус{" "}
            {ranking.policy.config.radius_m} м; новый алгоритм отбора POI. Без
            покрытия или достаточных сигналов баллы не выдаются.
          </p>
          <button
            className="button secondary"
            disabled={busy || !graph}
            onClick={() => void calculate(true)}
          >
            Сравнить сетевой рейтинг
          </button>
          {comparison &&
            comparison.baseline.request_fingerprint ===
              ranking.request_fingerprint && (
              <>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Зона</th>
                        <th>По прямой</th>
                        <th>По сети</th>
                        <th>POI: сеть / радиус</th>
                      </tr>
                    </thead>
                    <tbody>
                      {comparison.baseline.candidates.features.map((f, i) => {
                        const a = comparison.baseline.evaluations.find(
                          (e) => e.candidate_id === f.id,
                        );
                        const b = comparison.network.evaluations.find(
                          (e) => e.candidate_id === f.id,
                        );
                        const c = comparison.catchments[f.id];
                        return (
                          <tr key={f.id}>
                            <td>Зона {i + 1}</td>
                            <td>{a?.score?.toFixed(1) ?? "Нет оценки"}</td>
                            <td>
                              {b?.score?.toFixed(1) ?? "Недостаточно данных"}
                            </td>
                            <td>
                              {c
                                ? `${c.reachable_poi_count} / ${c.straight_line_poi_count}`
                                : "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <p>
                  Разница вызвана обходом по дорогам, связностью и привязкой
                  POI. Это не изменение спроса или прогноз прибыльности. Баллы
                  относительны внутри каждой сопоставимой группы.
                </p>
                <details>
                  <summary>
                    Компоненты, объяснения и версии сетевого рейтинга
                  </summary>
                  <pre>{JSON.stringify(comparison.network, null, 2)}</pre>
                </details>
              </>
            )}
        </details>
      )}
    </section>
  );
}
