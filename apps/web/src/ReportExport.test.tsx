import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ReportExport from "./ReportExport";
import type { Conversation, Schemas } from "./api";
import actual from "../../../docs/examples/BA-009-coffee-result.json";

// Explicit mock adapter. The actual full-stack/browser download is tested separately.
const finance = actual.response as unknown as Schemas["FinanceResult"];
const conversation = {
  id: finance.request_snapshot.profile.conversation_id,
  version: 2,
  profile: finance.request_snapshot.profile,
} as Conversation;
const credential = { id: conversation.id, token: "test-guest-key-not-real" };
const props = {
  conversation,
  credential,
  finance,
  ranking: null,
  selected: null,
  bank: null,
  walking: null,
  provider: null,
};
const metadata = {
  id: "00000000-0000-0000-0000-000000000015",
  created_at: "2026-10-25T00:00:00Z",
  profile_version: 2,
  snapshot_sha256: "a".repeat(64),
  pdf_sha256: "b".repeat(64),
  status: "current",
  reasons: [],
  missing_sections: ["geo", "walking", "bank"],
  json_bytes: 1000,
  pdf_bytes: 2000,
};
const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status });

describe("report export (mock API)", () => {
  it("prepares checked inputs, downloads without credentials in URLs and invalidates edits", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (path) =>
        String(path).includes("/file?")
          ? new Response("%PDF-mock")
          : json(metadata),
      );
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:report"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const { rerender } = render(<ReportExport {...props} />);
    expect(screen.getByRole("button", { name: "Скачать PDF" })).toBeEnabled();
    expect(
      screen.queryByText("Готово! Ваш предварительный план подготовлен."),
    ).toBeNull();
    fireEvent.click(screen.getByText("Состав и источники отчёта"));
    fireEvent.click(screen.getByRole("button", { name: "Подготовить отчёт" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Скачать PDF" })).toBeEnabled(),
    );
    expect(
      screen.getByText("Готово! Ваш предварительный план подготовлен."),
    ).toBeVisible();
    const body = JSON.parse(String(fetch.mock.calls[0][1]?.body));
    expect(body.finance.fingerprint).toBe(finance.request_fingerprint);
    expect(body.expected_version).toBe(2);
    expect(body).not.toHaveProperty("snapshot");
    fireEvent.click(screen.getByRole("button", { name: "Скачать PDF" }));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    for (const [url, init] of fetch.mock.calls) {
      expect(String(url)).not.toContain(credential.token);
      expect(init?.headers).toMatchObject({
        "X-Conversation-Token": credential.token,
      });
    }
    rerender(<ReportExport {...props} finance={null} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Требуется обновить отчёт",
    );
    expect(screen.getByRole("button", { name: "Скачать JSON" })).toBeDisabled();
  });
  it("blocks a snapshot marked outdated by the server", async () => {
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(json(metadata))
      .mockResolvedValueOnce(
        json({ ...metadata, status: "outdated", reasons: ["Changed profile"] }),
      );
    render(<ReportExport {...props} />);
    fireEvent.click(screen.getByText("Состав и источники отчёта"));
    fireEvent.click(screen.getByRole("button", { name: "Подготовить отчёт" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Скачать JSON" }),
      ).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Скачать JSON" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Обновите отчёт",
    );
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it("shows preparation errors and permits explicit retry without downloading a file", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      json({ detail: { code: "report_results_changed" } }, 409),
    );
    render(<ReportExport {...props} />);
    fireEvent.click(screen.getByText("Состав и источники отчёта"));
    fireEvent.click(screen.getByRole("button", { name: "Подготовить отчёт" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Результаты анализа изменились",
    );
    expect(screen.getByRole("button", { name: "Скачать PDF" })).toBeEnabled();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
  it("prepares on the first PDF click and reuses that snapshot after a failed file transfer", async () => {
    let fileCalls = 0;
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(async (path) => {
        if (String(path).includes("/file?")) {
          fileCalls++;
          return fileCalls === 1 ? json({}, 503) : new Response("%PDF-test");
        }
        return json(metadata);
      });
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:report"),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    render(<ReportExport {...props} />);
    fireEvent.click(screen.getByRole("button", { name: "Скачать PDF" }));
    await screen.findByRole("alert");
    expect(click).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Скачать PDF" }));
    await waitFor(() => expect(click).toHaveBeenCalledOnce());
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(1);
    expect(fileCalls).toBe(2);
  });
});
