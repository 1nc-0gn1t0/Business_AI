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
import Finance from "./Finance";
import Locations from "./Locations";
vi.mock("./Walking", () => ({ default: () => null }));
import App from "./App";
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
      <Chat
        conversation={{
          ...view,
          state: "awaiting_confirmation",
          profile: { ...profile, confirmation_state: "draft" },
        }}
        messages={[]}
        busy={false}
        {...cb}
      />,
    );
    fireEvent.click(screen.getByText("Редактировать профиль ↗"));
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
    fireEvent.click(screen.getByText("Подтвердить профиль →"));
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
    expect(screen.getByText("Режим stub · не LLM")).toBeVisible();
  });
  it("does not allow confirmation with missing fields", () => {
    render(
      <Chat
        conversation={{
          ...view,
          profile: { ...profile, confirmation_state: "draft" },
          missing_fields: ["format"],
        }}
        messages={[]}
        busy={false}
        {...callbacks()}
      />,
    );
    expect(screen.getByText("Подтвердить профиль →")).toBeDisabled();
  });
  it("sends edited synthetic assumptions to real finance endpoint and marks old results stale", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(json(financeExample.response));
    render(<Finance profile={profile} zone={null} />);
    fireEvent.click(screen.getByText("Загрузить демо-допущения"));
    fireEvent.change(screen.getByLabelText("Аренда"), {
      target: { value: "90000" },
    });
    fireEvent.click(screen.getByText("Пересчитать модель →"));
    await screen.findByLabelText("Результат финансового расчёта");
    const body = JSON.parse(String(fetch.mock.calls[0][1]?.body));
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/finance/calculate");
    expect(body.monthly_fixed_costs.rent.value).toBe("90000");
    expect(body.monthly_fixed_costs.rent.source.origin).toBe("synthetic");
    expect(body.selected_zone).toBeNull();
    expect(
      screen.getByText(
        "Операционный результат — до неучтённых налогов, амортизации, процентов и кредитных платежей. Это не чистая прибыль и не денежный поток. Нет расчёта окупаемости и подтверждения доступности помещения.",
      ),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Аренда"), {
      target: { value: "100000" },
    });
    expect(
      screen.getByText(
        "Ниже предыдущий расчёт. Он не учитывает изменённые вводные.",
      ),
    ).toBeVisible();
  });
  it("shows finance API validation failure", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json({}, 422));
    render(<Finance profile={profile} zone={null} />);
    fireEvent.click(screen.getByText("Загрузить демо-допущения"));
    fireEvent.click(screen.getByText("Пересчитать модель →"));
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
    await screen.findByText("Нет оценки");
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
    render(<App />);
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
});
