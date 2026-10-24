import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Walking from "./Walking";
import type { Dataset, Schemas } from "./api";
import actual from "../../../docs/examples/BA-013-kazan-catchments.json";

// Explicit recorded API excerpt: counts are full, geometries/POI intentionally sampled.
const result = actual.cases[0]
  .response_excerpt as unknown as Schemas["CatchmentResult"];
const dataset = {
  slug: "kazan-centre",
  data_version: result.poi_data_version,
} as Dataset;
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
function Harness() {
  const [point, setPoint] = useState<[number, number]>([49.119, 55.788]);
  const [data, setData] = useState<Schemas["CatchmentResult"] | null>(null);
  return (
    <Walking
      dataset={dataset}
      point={point}
      ranking={null}
      result={data}
      onPoint={setPoint}
      onResult={setData}
    />
  );
}

describe("walking UI, explicit mocked API", () => {
  it("does not replace a missing graph with straight-line results", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(json(null));
    render(<Harness />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(
      screen.getByText(/Прямые расстояния не подставляются/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Рассчитать пешую доступность →" }),
    ).toBeDisabled();
  });
  it("pins graph/POI versions and displays server counts and distinct distances", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (_p, init) =>
        json(init?.method === "POST" ? result : result.graph),
      );
    render(<Harness />);
    const button = screen.getByRole("button", {
      name: "Рассчитать пешую доступность →",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await screen.findByLabelText("Результат пешеходного анализа");
    expect(
      screen.getByText(String(result.reachable_poi_count), { exact: true }),
    ).toBeVisible();
    const call = fetch.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(call[1]?.body))).toMatchObject({
      longitude: 49.119,
      latitude: 55.788,
      distance_m: 600,
      max_snap_m: 30,
      graph_version: result.graph!.graph_version,
      data_version: dataset.data_version,
    });
    expect(
      screen.getByText(/не доказательство физической недоступности/),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Пешеходный бюджет, м"), {
      target: { value: "800" },
    });
    expect(
      screen.queryByLabelText("Результат пешеходного анализа"),
    ).not.toBeInTheDocument();
  });
  it("accepts explicit coordinates and handles an API error without invented output", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_p, init) =>
      init?.method === "POST"
        ? json({ detail: { code: "walking_graph_version_not_found" } }, 409)
        : json(result.graph),
    );
    render(<Harness />);
    fireEvent.change(screen.getByLabelText("Долгота точки"), {
      target: { value: "49.155" },
    });
    fireEvent.change(screen.getByLabelText("Широта точки"), {
      target: { value: "55.788" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Использовать координаты" }),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Рассчитать пешую доступность →" }),
      ).toBeEnabled(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Рассчитать пешую доступность →" }),
    );
    await screen.findByRole("alert");
    expect(
      screen.queryByLabelText("Результат пешеходного анализа"),
    ).not.toBeInTheDocument();
  });
});
