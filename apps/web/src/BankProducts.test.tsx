import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import BankProducts from "./BankProducts";
import type { Conversation, Schemas } from "./api";
import example from "../../../docs/examples/BA-011-coffee.json";
vi.mock("./LeadFlow", () => ({ default: () => null }));

// Recorded deterministic demonstration responses, never real bank offers.
const result = example.response as unknown as Schemas["MatchResult"];
const conversation: Conversation = {
  id: result.profile_snapshot.conversation_id,
  version: 2,
  profile: result.profile_snapshot,
  missing_fields: [],
  state: "confirmed",
  assistant_message: "",
  extraction_mode: "ollama",
  created_at: "2026-10-23T00:00:00Z",
  updated_at: "2026-10-23T00:00:00Z",
};
const credential = { id: conversation.id, token: "explicit-test-credential" };
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });

describe("bank product interface with explicit mocked APIs", () => {
  it("does not celebrate an unavailable catalogue returned with HTTP 200", async () => {
    const unavailable = {
      ...result,
      status: "catalogue_unavailable",
      decisions: [],
      missing_fields: [],
      recommended_ids: [],
      demonstration_ids: [],
    };
    vi.spyOn(globalThis, "fetch").mockImplementation(async (_path, options) =>
      json(options?.method === "POST" ? unavailable : result.catalogue),
    );
    render(
      <BankProducts
        active
        conversation={conversation}
        credential={credential}
        onProfileConflict={vi.fn()}
      />,
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Показать варианты по этим ответам",
      }),
    );
    await screen.findByText(
      "Нет подтверждённых доступных предложений в текущем каталоге.",
    );
    expect(
      screen
        .getByText(
          "Нет подтверждённых доступных предложений в текущем каталоге.",
        )
        .closest(".vi-status"),
    ).toHaveAttribute("data-emotion", "uncertain");
    expect(
      screen.queryByText("Подбор завершён. Это не решение банка."),
    ).not.toBeInTheDocument();
  });
  it("does not request catalogue until the section is opened", () => {
    const fetch = vi.spyOn(globalThis, "fetch");
    render(
      <BankProducts
        active={false}
        conversation={conversation}
        credential={credential}
        onProfileConflict={vi.fn()}
      />,
    );
    expect(fetch).not.toHaveBeenCalled();
  });
  it("labels unconfirmed catalogue and sends only explicit needs with protected version", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (_path, options) =>
        json(options?.method === "POST" ? result : result.catalogue),
      );
    render(
      <BankProducts
        active
        conversation={conversation}
        credential={credential}
        onProfileConflict={vi.fn()}
      />,
    );
    await screen.findByText(/Демонстрационный подбор/);
    fireEvent.click(screen.getByText("Изменить или дополнить потребности"));
    fireEvent.change(screen.getByLabelText("Регистрация бизнеса"), {
      target: { value: "ip" },
    });
    fireEvent.change(screen.getByLabelText("Нужен расчётный счёт"), {
      target: { value: "true" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Подобрать по потребностям →" }),
    );
    await screen.findByText("Возможности для вашего проекта");
    const call = fetch.mock.calls.find(
      ([, options]) => options?.method === "POST",
    )!;
    expect(String(call[0])).not.toContain(credential.token);
    expect(call[1]?.headers).toHaveProperty(
      "X-Conversation-Token",
      credential.token,
    );
    const body = JSON.parse(String(call[1]?.body));
    expect(body.expected_version).toBe(2);
    expect(body.catalogue_fingerprint).toBe(result.catalogue.fingerprint);
    expect(body.needs).toEqual({
      registration_status: "ip",
      needs_settlement_account: true,
    });
    expect(body).not.toHaveProperty("profile");
    fireEvent.click(screen.getByText("Все продукты, источники и ограничения"));
    expect(
      screen.getByText(/Подтверждённых действующих предложений: 0/),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Нужен расчётный счёт"), {
      target: { value: "false" },
    });
    expect(
      screen.queryByText("Возможности для вашего проекта"),
    ).not.toBeInTheDocument();
  });
  it("requires confirmed profile and shows catalogue load failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(json(result.catalogue));
    render(
      <BankProducts
        active
        conversation={{
          ...conversation,
          profile: { ...conversation.profile, confirmation_state: "draft" },
        }}
        credential={credential}
        onProfileConflict={vi.fn()}
      />,
    );
    await screen.findByText(/Демонстрационный подбор/);
    fireEvent.click(screen.getByText("Изменить или дополнить потребности"));
    expect(
      screen.getByRole("button", { name: "Подобрать по потребностям →" }),
    ).toBeDisabled();
  });
  it("handles profile version conflict without silently repeating a match", async () => {
    const conflict = vi.fn();
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (_path, options) =>
        options?.method === "POST"
          ? json({ detail: { code: "version_conflict" } }, 409)
          : json(result.catalogue),
      );
    render(
      <BankProducts
        active
        conversation={conversation}
        credential={credential}
        onProfileConflict={conflict}
      />,
    );
    await screen.findByText(/Демонстрационный подбор/);
    fireEvent.click(screen.getByText("Изменить или дополнить потребности"));
    fireEvent.click(
      screen.getByRole("button", { name: "Подобрать по потребностям →" }),
    );
    await waitFor(() => expect(conflict).toHaveBeenCalledOnce());
    expect(
      fetch.mock.calls.filter(([, o]) => o?.method === "POST"),
    ).toHaveLength(1);
  });
  it("does not replace a broken catalogue with made-up offers", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ detail: { code: "bank_catalogue_unavailable" } }, 503),
    );
    render(
      <BankProducts
        active
        conversation={conversation}
        credential={credential}
        onProfileConflict={vi.fn()}
      />,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Каталог временно недоступен",
    );
    expect(
      screen.queryByText("Расчётно-кассовое обслуживание ВТБ"),
    ).not.toBeInTheDocument();
  });
});
