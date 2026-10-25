import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import DataSources from "./DataSources";
import demo from "../../../data/synthetic/coffee-kazan-v1.json";

// Explicit mock API contract; no market claims or production fixture substitution.
const version = "a".repeat(64);
const metadata = {
  provider: "synthetic",
  slug: demo.slug,
  revision: demo.revision,
  data_version: version,
  active: true,
  bbox: demo.bbox,
  origin: "synthetic",
  source_name: demo.source_name,
  generated_at: demo.generated_at,
  observed_at: null,
  license: demo.license,
  attribution: demo.attribution,
  limitations: demo.limitations,
};
const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status });
function mock(enabled = true) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (path, init) => {
      const url = String(path);
      if (url.endsWith("/policy") || url.endsWith("/selection"))
        return json({
          mode: "real",
          demo_enabled: enabled,
          allowed_providers: ["osm"],
        });
      if (url.endsWith("/sources"))
        return json([
          { id: "osm", name: "OSM", status: "ready", limitations: [] },
          {
            id: "synthetic",
            name: "Синтетический сценарий",
            status: enabled ? "ready" : "disabled",
            limitations: demo.limitations,
          },
          {
            id: "ghsl",
            name: "GHSL",
            status: "not_integrated",
            limitations: ["Нет набора"],
          },
        ]);
      if (url.endsWith("/datasets"))
        return json(
          url.includes("/ghsl/")
            ? []
            : [
                {
                  ...metadata,
                  provider: url.includes("/osm/") ? "osm" : "synthetic",
                },
              ],
        );
      if (url.endsWith("/indicators")) {
        const body = JSON.parse(String(init?.body));
        return json({
          dataset: {
            ...metadata,
            origin: body.provider === "osm" ? "open_data" : "synthetic",
          },
          indicators:
            body.provider === "osm"
              ? [
                  {
                    metric: "rent_monthly_rub",
                    name: "Аренда",
                    status: "missing",
                    measurement: null,
                    reason: "Не измерено",
                  },
                ]
              : [
                  {
                    metric: "rent_monthly_rub",
                    name: "Аренда",
                    unit: "RUB_per_month",
                    status: "available",
                    measurement: demo.measurements[1],
                    reason: null,
                  },
                ],
          limitations: demo.limitations,
        });
      }
      return json({ detail: { code: "provider_not_integrated" } }, 503);
    });
}
describe("provider source selection (mock API)", () => {
  it("requires demo selection and clears previous values when switching", async () => {
    const fetch = mock();
    render(<DataSources />);
    fireEvent.click(screen.getByText("Источники и происхождение показателей"));
    const button = screen.getByRole("button", {
      name: "Показать показатели источника",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(await screen.findByText("Нет данных")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Режим данных"), {
      target: { value: "demo" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Режим данных")).toHaveValue("demo"),
    );
    expect(screen.queryByText("Нет данных")).toBeNull();
    fireEvent.change(screen.getByLabelText("Источник показателей"), {
      target: { value: "synthetic" },
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    expect(
      await screen.findByText(/СИНТЕТИЧЕСКИЕ ДАННЫЕ · НЕ РЫНОК/),
    ).toBeVisible();
    expect(screen.getByText(/ДОПУЩЕНИЕ/)).toBeVisible();
    const calls = fetch.mock.calls.filter(([p]) =>
      String(p).endsWith("/indicators"),
    );
    expect(JSON.parse(String(calls.at(-1)?.[1]?.body))).toMatchObject({
      provider: "synthetic",
      mode: "demo",
      data_version: version,
    });
    fireEvent.change(screen.getByLabelText("Режим данных"), {
      target: { value: "real" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Режим данных")).toHaveValue("real"),
    );
    expect(screen.queryByText(/ДОПУЩЕНИЕ/)).toBeNull();
  });
  it("keeps demo disabled by server and unavailable providers empty", async () => {
    mock(false);
    render(<DataSources />);
    fireEvent.click(screen.getByText("Источники и происхождение показателей"));
    await waitFor(() =>
      expect(screen.getByLabelText("Режим данных")).toBeEnabled(),
    );
    expect(
      screen.getByRole("option", {
        name: "Демо: разрешить синтетические данные",
      }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Источник показателей"), {
      target: { value: "ghsl" },
    });
    expect(await screen.findByText("Нет набора")).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Показать показатели источника" }),
    ).toBeDisabled();
  });
  it("shows source errors without generated replacement", async () => {
    const fetch = mock();
    render(<DataSources />);
    fireEvent.click(screen.getByText("Источники и происхождение показателей"));
    const button = screen.getByRole("button", {
      name: "Показать показатели источника",
    });
    await waitFor(() => expect(button).toBeEnabled());
    fetch.mockResolvedValueOnce(
      json({ detail: { code: "provider_dataset_invalid" } }, 503),
    );
    fireEvent.click(button);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "не прошёл проверку целостности",
    );
    expect(screen.queryByText(/ДОПУЩЕНИЕ/)).toBeNull();
  });
});
