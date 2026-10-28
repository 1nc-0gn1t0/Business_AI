import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { Conversation, Profile, Ranking } from "./api";
import Chat from "./Chat";
import { ProjectReview } from "./FlowUI";
import Finance from "./Finance";
import Locations from "./Locations";
vi.mock("./Walking", () => ({ default: () => null }));
vi.mock("./DataSources", () => ({ default: () => null }));
import BusinessFlow from "./BusinessFlow";
import { saveCredential } from "./api";
import geoExample from "../../../docs/examples/BA-008-kazan-coffee.json";
import financeExample from "../../../docs/examples/BA-009-coffee-result.json";

// Explicit recorded fixtures only for tests. Production never imports result fixtures.
vi.mock("./GeoMap", () => ({
  default: () => (
    <div aria-label="Mock map">Mock MapLibre — no WebGL verification</div>
  ),
}));
const ranking = geoExample.scenarios.covered_BA007_zones
  .response as unknown as Ranking;
const profile = financeExample.response.request_snapshot.profile as Profile;
const view: Conversation = {
  id: profile.conversation_id,
  profile,
  version: 2,
  state: "confirmed",
  missing_fields: [],
  assistant_message: "Подтвердите профиль",
  extraction_mode: "ollama",
  created_at: "2026-10-23T00:00:00Z",
  updated_at: "2026-10-23T00:00:00Z",
};
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status });
const callbacks = () => ({
  onNew: vi.fn(),
  onRefresh: vi.fn(),
  onSend: vi.fn().mockResolvedValue(undefined),
  onPatch: vi.fn().mockResolvedValue(undefined),
  onConfirm: vi.fn(),
});

describe("critical UI components with explicit API mocks", () => {
  it("edits and confirms a draft profile using existing patch contract", async () => {
    const cb = callbacks();
    render(
      <ProjectReview
        onChat={vi.fn()}
        conversation={{
          ...view,
          state: "awaiting_confirmation",
          profile: { ...profile, confirmation_state: "draft" },
        }}
        busy={false}
        {...cb}
      />,
    );
    fireEvent.click(screen.getByText("Изменить"));
    fireEvent.change(screen.getByLabelText("Формат"), {
      target: { value: "навынос" },
    });
    fireEvent.click(screen.getByText("Сохранить профиль"));
    await waitFor(() =>
      expect(cb.onPatch).toHaveBeenCalledWith(
        expect.objectContaining({
          preferences: expect.objectContaining({ format: "навынос" }),
          budget: "2000000.00",
        }),
      ),
    );
    fireEvent.click(screen.getByText("Продолжить"));
    expect(cb.onConfirm).toHaveBeenCalled();
  });
  it("keeps failed message drafts and labels stub mode honestly", async () => {
    const cb = callbacks();
    cb.onSend.mockRejectedValue(new Error("unavailable"));
    render(
      <Chat
        conversation={{ ...view, extraction_mode: "stub" }}
        messages={[]}
        busy={false}
        {...cb}
      />,
    );
    fireEvent.change(screen.getByLabelText("Сообщение помощнику"), {
      target: { value: "Кофейня в Казани" },
    });
    fireEvent.click(screen.getByLabelText("Отправить сообщение"));
    await waitFor(() => expect(cb.onSend).toHaveBeenCalled());
    expect(screen.getByLabelText("Сообщение помощнику")).toHaveValue(
      "Кофейня в Казани",
    );
    expect(screen.getByText("Ответ без AI-модели")).toBeVisible();
  });
  it("does not allow confirmation with missing fields", () => {
    render(
      <ProjectReview
        onChat={vi.fn()}
        conversation={{
          ...view,
          profile: { ...profile, confirmation_state: "draft" },
          missing_fields: ["format"],
        }}
        busy={false}
        {...callbacks()}
      />,
    );
    expect(screen.getByText("Продолжить")).toBeDisabled();
  });
  it("sends edited synthetic assumptions to real finance endpoint and marks old results stale", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(json(financeExample.response));
    render(<Finance profile={profile} zone={null} />);
    fireEvent.click(screen.getByText("Рассчитать сценарии"));
    await screen.findByLabelText("Результат финансового расчёта");
    fireEvent.change(screen.getByLabelText("Аренда"), {
      target: { value: "90000" },
    });
    fireEvent.click(screen.getByText("Пересчитать модель →"));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const body = JSON.parse(String(fetch.mock.calls[1][1]?.body));
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/finance/calculate");
    expect(body.monthly_fixed_costs.rent.value).toBe("90000");
    expect(body.monthly_fixed_costs.rent.source.origin).toBe("synthetic");
    expect(body.selected_zone).toBeNull();
    fireEvent.click(screen.getByText("Как рассчитано?"));
    expect(
      screen.getByText(/Операционный результат — не чистая прибыль/),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Аренда"), {
      target: { value: "100000" },
    });
    expect(screen.getByText(/Предыдущий расчёт/)).toBeVisible();
  });
  it("shows finance API validation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 422));
    render(<Finance profile={profile} zone={null} />);
    fireEvent.click(screen.getByText("Рассчитать сценарии"));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "сервер отклонил",
    );
  });
  it("handles empty datasets honestly", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json([]));
    render(
      <Locations
        profile={profile}
        ranking={null}
        onRanking={vi.fn()}
        selected={null}
        onSelect={vi.fn()}
        comparison={false}
        onFinance={vi.fn()}
      />,
    );
    expect(await screen.findByText("Нет загруженных геоданных")).toBeVisible();
  });
  it("preserves null ratings for insufficient coverage and pins dataset version", async () => {
    const dataset = ranking.candidates.dataset;
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (path) =>
        String(path).endsWith("/datasets")
          ? json([dataset])
          : String(path).includes("/rankings")
            ? json(ranking)
            : String(path).includes("/pois?")
              ? json({
                  type: "FeatureCollection",
                  features: [],
                  returned_count: 0,
                  next_offset: null,
                  dataset,
                })
              : json({
                  type: "FeatureCollection",
                  features: [],
                  dataset,
                  truncated: false,
                }),
      );
    const partial = structuredClone(ranking);
    partial.evaluations[0].score = null;
    partial.evaluations[0].rank = null;
    partial.evaluations[0].status = "outside_coverage";
    const onRanking = vi.fn();
    render(
      <Locations
        profile={profile}
        ranking={partial}
        onRanking={onRanking}
        selected={null}
        onSelect={vi.fn()}
        comparison={true}
        onFinance={vi.fn()}
      />,
    );
    await screen.findByText(/Недостаточно данных для оценки/);
    fireEvent.click(screen.getByText("Подробнее о зоне и анализе"));
    fireEvent.click(screen.getByText("Настройки анализа"));
    fireEvent.click(screen.getByText("Пересчитать зоны ↗"));
    await waitFor(() => expect(onRanking).toHaveBeenCalledWith(ranking));
    const call = fetch.mock.calls.find(([path]) =>
      String(path).endsWith("/rankings"),
    )!;
    const body = JSON.parse(String(call[1]?.body));
    expect(body.candidates.profile).toEqual(profile);
    expect(body.candidates.data_version).toBe(dataset.data_version);
  });
  it("restores private history on reload and refreshes on concurrent changes", async () => {
    saveCredential({ id: view.id, token: "test-key" });
    let conflicted = false;
    vi.spyOn(globalThis, "fetch").mockImplementation(async (path, options) => {
      if (String(path).endsWith("/consent-texts"))
        return json([{ purpose: "assistant", version: "assistant-demo-v1" }]);
      if (String(path).endsWith("/consents"))
        return json({
          consents: [
            {
              purpose: "assistant",
              status: "granted",
              text_version: "assistant-demo-v1",
            },
          ],
        });
      if (String(path).includes("/messages?"))
        return json([
          {
            id: "m1",
            version: 1,
            role: "user",
            content: "Сохранённая история",
            created_at: view.created_at,
          },
        ]);
      if (options?.method === "POST") {
        conflicted = true;
        return json({ detail: { code: "version_conflict" } }, 409);
      }
      if (String(path).includes("/conversations/"))
        return json({ ...view, version: conflicted ? 3 : 2 });
      return String(path).endsWith("/datasets")
        ? json([])
        : json({ status: "ok", database: "ok" });
    });
    render(<BusinessFlow onHome={vi.fn()} />);
    await screen.findByRole("heading", { name: /Где лучше открыть/ });
    fireEvent.click(screen.getByRole("button", { name: "← Назад" }));
    fireEvent.click(screen.getByRole("button", { name: "Вернуться в диалог" }));
    await screen.findByText("Сохранённая история");
    fireEvent.change(screen.getByLabelText("Сообщение помощнику"), {
      target: { value: "Уточнение" },
    });
    fireEvent.click(screen.getByLabelText("Отправить сообщение"));
    await waitFor(() =>
      expect(
        within(screen.getByRole("alert")).getByText(/Профиль изменён/),
      ).toBeVisible(),
    );
    expect(screen.getByLabelText("Сообщение помощнику")).toHaveValue(
      "Уточнение",
    );
  });
  it("does not create a replacement guest session when restoring a project fails", async () => {
    saveCredential({ id: view.id, token: "test-key" });
    let available = false;
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (path) => {
        if (String(path).endsWith("/consent-texts")) return json([]);
        if (!available)
          return json({ detail: { code: "database_unavailable" } }, 503);
        if (String(path).includes("/messages?")) return json([]);
        return json(view);
      });
    render(<BusinessFlow onHome={vi.fn()} />);
    await screen.findByRole("heading", { name: "Не удалось открыть проект" });
    expect(screen.queryByLabelText("Сообщение помощнику")).toBeNull();
    expect(
      fetch.mock.calls.every(
        ([, init]) => !init?.method || init.method === "GET",
      ),
    ).toBe(true);
    available = true;
    fireEvent.click(screen.getByRole("button", { name: "Повторить загрузку" }));
    await screen.findByLabelText("Сообщение помощнику");
    expect(
      screen.queryByRole("heading", { name: "Не удалось открыть проект" }),
    ).toBeNull();
    expect(
      fetch.mock.calls.every(
        ([, init]) => !init?.method || init.method === "GET",
      ),
    ).toBe(true);
  });
});
