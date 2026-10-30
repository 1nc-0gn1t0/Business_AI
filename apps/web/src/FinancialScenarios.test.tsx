import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import fixture from "../e2e/fixtures/financial-scenarios.json" with { type: "json" };
import FinancialScenarios, { FinancialResults } from "./FinancialScenarios";
import type { Schemas } from "./api";

type View = Schemas["FinancialView"];
const value = () => structuredClone(fixture) as unknown as View;
const credential = {
  id: "explicit-test-owner",
  token: crypto.randomUUID() + crypto.randomUUID(),
};
afterEach(() => vi.unstubAllGlobals());

describe("U-05 financial review and what-if", () => {
  it("renders three scenarios and explains a negative result without claiming net profit", () => {
    const result = value().result!.result;
    result.scenarios[0].operating_result = "-100000";
    render(<FinancialResults value={result} />);
    expect(
      screen.getByRole("heading", { name: "Пессимистичный" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Базовый" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Оптимистичный" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/-100/)).toBeInTheDocument();
  });
  it("requires an explicit review request and never sends client provenance", async () => {
    const view = value();
    view.result = null;
    const rent = view.document.entries!.rent;
    view.needs_review = ["rent"];
    rent.review = "proposed";
    rent.epistemic = "assumed";
    rent.source.origin = "synthetic";
    const fetch = vi
      .fn()
      .mockResolvedValue(new Response(JSON.stringify(view), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    render(
      <FinancialScenarios
        credential={credential}
        profileRevision={2}
        onEdit={vi.fn()}
      />,
    );
    const checkbox = await screen.findByRole("checkbox", {
      name: "Проверено: Аренда",
    });
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(checkbox);
    fireEvent.click(
      screen.getByRole("button", { name: "Использовать выбранные значения" }),
    );
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const body = JSON.parse(fetch.mock.calls[1][1].body);
    expect(body.confirm).toEqual(["rent"]);
    expect(body).not.toHaveProperty("source");
    expect(screen.getByText(/Подтверждение разрешает/)).toBeInTheDocument();
  });
  it("does not save a draft what-if or keep showing an old result as current", async () => {
    const view = value();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(view), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            persisted: false,
            input_revision: 2,
            result: view.result!.result,
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    render(
      <FinancialScenarios
        credential={credential}
        profileRevision={2}
        onEdit={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByText("Ввести или проверить параметры"));
    const rent = await screen.findByRole("textbox", { name: /^Аренда$/ });
    fireEvent.change(rent, { target: { value: "110000" } });
    expect(
      screen.queryByText("При заданных параметрах"),
    ).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Проверить без сохранения" }),
    );
    await screen.findByText("Пробный расчёт · не сохранён");
    expect(fetch.mock.calls[1][0]).toContain("/what-if");
    expect(JSON.parse(fetch.mock.calls[1][1].body).updates[0].base).toBe(
      "110000",
    );
  });
  it("clears financial output when the backend reports a version conflict", async () => {
    const view = value();
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(view), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: { code: "financial_input_conflict" } }),
          { status: 409 },
        ),
      );
    vi.stubGlobal("fetch", fetch);
    render(
      <FinancialScenarios
        credential={credential}
        profileRevision={2}
        onEdit={vi.fn()}
      />,
    );
    await screen.findByText("При заданных параметрах");
    fireEvent.click(
      screen.getByRole("button", { name: "Рассчитать три сценария" }),
    );
    await screen.findByRole("alert");
    expect(
      screen.queryByText("При заданных параметрах"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Обновить вводные" }),
    ).toBeInTheDocument();
  });
});
