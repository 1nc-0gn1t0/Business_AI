import { describe, expect, it, vi } from "vitest";
import {
  ApiError,
  history,
  readCredential,
  request,
  requestFile,
  saveCredential,
} from "./api";

describe("same-origin API client (explicit fetch mocks)", () => {
  it("sanitizes download transport failures without retry", async () => {
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("SYNTHETIC_SECRET"));
    await expect(
      requestFile("/api/v1/conversations/id/reports/r/file?format=pdf", {
        id: "id",
        token: "private",
      }),
    ).rejects.toThrow("Файл не получен");
    expect(mock).toHaveBeenCalledTimes(1);
  });
  it("shows a valid correlation ID, rejects arbitrary header text", async () => {
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { code: "llm_model_missing" } }),
          { status: 503, headers: { "X-Request-ID": "a".repeat(32) } },
        ),
      );
    await expect(request("/api/v1/conversations")).rejects.toThrow(
      "Код диагностики: " + "a".repeat(32),
    );
    mock.mockResolvedValue(
      new Response("{}", {
        status: 500,
        headers: { "X-Request-ID": "SYNTHETIC_SECRET" },
      }),
    );
    await expect(request("/api/v1/conversations")).rejects.not.toThrow(
      "SYNTHETIC_SECRET",
    );
    expect(mock).toHaveBeenCalledTimes(2);
  });
  it.each([
    [413, "request_body_too_large", "Сократите"],
    [422, "request_text_too_long", "длинный"],
    [429, "resource_quota_exceeded", "не сбросит"],
    [429, "report_limit_reached", "остаются доступны"],
    [429, "request_capacity_busy", "Сервис занят"],
    [429, "llm_queue_full", "Очередь"],
    [429, "llm_queue_timeout", "ожидания"],
  ])(
    "handles limits without automatic retries: %s %s",
    async (status, code, expected) => {
      const mock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ detail: { code } }), {
          status: Number(status),
        }),
      );
      await expect(
        request("/api/v1/conversations/id/messages"),
      ).rejects.toThrow(String(expected));
      expect(mock).toHaveBeenCalledTimes(1);
    },
  );
  it("shows only a server-provided retry time, including report downloads", async () => {
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({ detail: { code: "request_rate_limited" } }),
            { status: 429, headers: { "Retry-After": "7" } },
          ),
      );
    await expect(request("/api/v1/geo/datasets")).rejects.toThrow("через 7 с.");
    await expect(
      requestFile("/api/v1/conversations/id/reports/r/file?format=pdf", {
        id: "id",
        token: "fixture",
      }),
    ).rejects.toThrow("через 7 с.");
    mock.mockImplementation(
      async () =>
        new Response(
          JSON.stringify({ detail: { code: "request_capacity_busy" } }),
          { status: 429 },
        ),
    );
    await expect(request("/api/v1/geo/datasets")).rejects.not.toThrow("через");
  });
  it("keeps guest credentials in session storage, never in URLs", async () => {
    const key = { id: "test-conversation", token: "test-secret-not-real" };
    expect(saveCredential(key)).toBe(true);
    expect(readCredential()).toEqual(key);
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async () => new Response("{}"));
    await request("/api/v1/conversations/test-conversation", {
      credential: key,
    });
    expect(mock.mock.calls[0][0]).not.toContain(key.token);
    expect(mock.mock.calls[0][1]?.headers).toHaveProperty(
      "X-Conversation-Token",
      key.token,
    );
    await request("/api/v1/geo/datasets", { credential: key });
    expect(mock.mock.calls[1][1]?.headers).not.toHaveProperty(
      "X-Conversation-Token",
    );
    await expect(
      request("https://other.example/", { credential: key }),
    ).rejects.toThrow("Unsupported API path");
  });
  it("handles corrupted or unavailable browser storage", () => {
    sessionStorage.setItem("business-ai.guest.v1", "invalid");
    expect(readCredential()).toBeNull();
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(saveCredential({ id: "id", token: "token" })).toBe(false);
  });
  it("paginates full history instead of dropping older messages", async () => {
    const mock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify(Array.from({ length: 100 }, (_, id) => ({ id }))),
        ),
      )
      .mockResolvedValueOnce(new Response(JSON.stringify([{ id: 100 }])));
    expect(await history({ id: "id", token: "key" })).toHaveLength(101);
    expect(mock.mock.calls[1][0]).toContain("offset=100");
  });
  it.each([502, 503, 504])(
    "shows local LLM/service unavailability for %s",
    async (status) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "llm_unavailable" } }), {
          status,
        }),
      );
      await expect(
        request("/api/v1/conversations/id/messages"),
      ).rejects.toThrow("Ollama");
    },
  );
  it("preserves version conflict code and gives useful validation errors", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            detail: { code: "version_conflict", current_version: 2 },
          }),
          { status: 409 },
        ),
      )
      .mockResolvedValueOnce(new Response("{}", { status: 422 }));
    await expect(request("/api/v1/conversations/id")).rejects.toMatchObject({
      code: "version_conflict",
      status: 409,
    });
    await expect(request("/api/v1/finance/calculate")).rejects.toThrow(
      "сервер отклонил",
    );
  });
  it("turns network errors into safe messages without raw credentials", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(
      new Error("sensitive raw network detail"),
    );
    await expect(request("/api/v1/geo/datasets")).rejects.toBeInstanceOf(
      ApiError,
    );
    await expect(request("/api/v1/geo/datasets")).rejects.not.toThrow(
      "sensitive",
    );
  });
});
