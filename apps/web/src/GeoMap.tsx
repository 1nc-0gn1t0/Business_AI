import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapInstance } from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { Dataset, Ranking, Schemas } from "./api";

type Props = {
  dataset: Dataset;
  districts: Schemas["DistrictCollection"] | null;
  pois: Schemas["POICollection"] | null;
  ranking: Ranking | null;
  selected: string | null;
  onSelect: (id: string) => void;
};
const empty = { type: "FeatureCollection" as const, features: [] };
maplibregl.setWorkerUrl(workerUrl);
export default function GeoMap(props: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapInstance | null>(null);
  const latest = useRef(props);
  const [problem, setProblem] = useState("");
  useEffect(() => {
    latest.current = props;
  });
  useEffect(() => {
    if (!container.current) return;
    let instance: MapInstance;
    try {
      instance = new maplibregl.Map({
        container: container.current,
        style: {
          version: 8,
          sources: {
            osm: {
              type: "raster",
              tiles: [
                import.meta.env.VITE_MAP_TILE_URL ||
                  "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
              ],
              tileSize: 256,
              attribution:
                '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap contributors</a>',
            },
          },
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#142737" },
            },
            {
              id: "osm",
              type: "raster",
              source: "osm",
              paint: { "raster-opacity": 0.68, "raster-saturation": -0.7 },
            },
          ],
        },
        center: [49.15, 55.78],
        zoom: 11,
        maxZoom: 18,
        attributionControl: { compact: false },
      });
    } catch {
      queueMicrotask(() =>
        setProblem(
          "Карта недоступна: браузеру необходим WebGL. Зоны и показатели доступны в списке.",
        ),
      );
      return;
    }
    map.current = instance;
    instance.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );
    instance.addControl(new maplibregl.ScaleControl({ unit: "metric" }));
    const update = () => {
      const p = latest.current;
      const b = p.dataset.bbox;
      const coverage = {
        type: "FeatureCollection" as const,
        features: [
          {
            type: "Feature" as const,
            properties: {},
            geometry: {
              type: "Polygon" as const,
              coordinates: [
                [
                  [b.west, b.south],
                  [b.east, b.south],
                  [b.east, b.north],
                  [b.west, b.north],
                  [b.west, b.south],
                ],
              ],
            },
          },
        ],
      };
      const data = {
        districts: p.districts || empty,
        pois: p.pois || empty,
        zones: p.ranking?.candidates || empty,
        coverage,
      };
      for (const [id, value] of Object.entries(data))
        (instance.getSource(id) as GeoJSONSource | undefined)?.setData(value);
      if (instance.getLayer("selected"))
        instance.setFilter("selected", ["==", ["id"], p.selected || ""]);
    };
    instance.on("load", () => {
      for (const id of ["districts", "pois", "zones", "coverage"])
        instance.addSource(id, { type: "geojson", data: empty });
      instance.addLayer({
        id: "district-lines",
        type: "line",
        source: "districts",
        paint: {
          "line-color": "#506879",
          "line-width": 1,
          "line-opacity": 0.5,
        },
      });
      instance.addLayer({
        id: "coverage-lines",
        type: "line",
        source: "coverage",
        paint: {
          "line-color": "#f2bf70",
          "line-width": 2,
          "line-dasharray": [4, 3],
        },
      });
      instance.addLayer({
        id: "zone-fill",
        type: "fill",
        source: "zones",
        paint: { "fill-color": "#25d5bc", "fill-opacity": 0.23 },
      });
      instance.addLayer({
        id: "zone-lines",
        type: "line",
        source: "zones",
        paint: { "line-color": "#13bda7", "line-width": 2 },
      });
      instance.addLayer({
        id: "selected",
        type: "line",
        source: "zones",
        filter: ["==", ["id"], ""],
        paint: { "line-color": "#f5b953", "line-width": 4 },
      });
      instance.addLayer({
        id: "poi-points",
        type: "circle",
        source: "pois",
        paint: {
          "circle-radius": 4,
          "circle-color": "#5272d9",
          "circle-stroke-color": "#e6ecff",
          "circle-stroke-width": 1,
        },
      });
      instance.on("click", "zone-fill", (e) => {
        const id = e.features?.[0]?.id;
        if (id) latest.current.onSelect(String(id));
      });
      instance.on("click", "poi-points", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const node = document.createElement("div");
        node.textContent = `${f.properties?.name || "Объект без названия"} · OSM ${f.properties?.osm_type}/${f.properties?.osm_id}`;
        new maplibregl.Popup()
          .setLngLat(e.lngLat)
          .setDOMContent(node)
          .addTo(instance);
      });
      instance.on("mouseenter", "zone-fill", () => {
        instance.getCanvas().style.cursor = "pointer";
      });
      instance.on("mouseleave", "zone-fill", () => {
        instance.getCanvas().style.cursor = "";
      });
      update();
      const b = latest.current.dataset.bbox;
      instance.fitBounds(
        [
          [b.west, b.south],
          [b.east, b.north],
        ],
        { padding: 32, duration: 0 },
      );
    });
    instance.on("error", () =>
      setProblem(
        "Часть карты не загрузилась. Подложка OSM предоставляется без SLA; проверьте сеть. Результаты доступны в списке.",
      ),
    );
    const resize = new ResizeObserver(() => instance.resize());
    resize.observe(container.current);
    return () => {
      resize.disconnect();
      instance.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current;
    if (!m?.getSource("zones")) return;
    (m.getSource("zones") as GeoJSONSource).setData(
      props.ranking?.candidates || empty,
    );
    (m.getSource("pois") as GeoJSONSource).setData(props.pois || empty);
    (m.getSource("districts") as GeoJSONSource).setData(
      props.districts || empty,
    );
    m.setFilter("selected", ["==", ["id"], props.selected || ""]);
  }, [props.ranking, props.pois, props.districts, props.selected]);
  useEffect(() => {
    const m = map.current;
    if (!m || !props.ranking) return;
    const markers = props.ranking.candidates.features.map((f) => {
      const rank = props.ranking!.evaluations.find(
        (e) => e.candidate_id === f.id,
      )?.rank;
      const button = document.createElement("button");
      button.type = "button";
      button.className = `zone-marker ${f.id === props.selected ? "selected" : ""}`;
      button.textContent = rank ? String(rank) : "?";
      button.setAttribute(
        "aria-label",
        `Выбрать зону на карте: ${rank || "без оценки"}`,
      );
      button.setAttribute("aria-pressed", String(f.id === props.selected));
      button.onclick = (event) => {
        event.stopPropagation();
        latest.current.onSelect(f.id);
      };
      return new maplibregl.Marker({ element: button })
        .setLngLat(f.properties.representative_point.coordinates)
        .addTo(m);
    });
    return () => markers.forEach((marker) => marker.remove());
  }, [props.ranking, props.selected]);
  return (
    <div className="map-wrap">
      <div
        ref={container}
        className="map-canvas"
        aria-label="Карта зон Казани"
      />
      {problem && (
        <p className="map-problem" role="status">
          {problem}
        </p>
      )}
      <div className="map-legend">
        <span>
          <i className="dot mint-dot" />
          Зоны-кандидаты
        </span>
        <span>
          <i className="dot blue-dot" />
          OSM POI
        </span>
        <span>┄ Граница покрытия</span>
      </div>
    </div>
  );
}
