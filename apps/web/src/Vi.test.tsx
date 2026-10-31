import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import App from "./App";
import Chat from "./Chat";
import provenance from "./assets/vi/provenance.json";

describe("Vi and the real workspace boundary", () => {
  it("does not create a guest, fetch consent or show a bank login on the landing", () => {
    window.history.replaceState(null, "", "/");
    const fetch = vi.spyOn(globalThis, "fetch");
    render(<App />);
    expect(screen.getByRole("heading", { name: /Ваш бизнес/ })).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Познакомьтесь с Ви" }),
    ).toHaveAttribute("aria-expanded", "false");
    expect(screen.getAllByRole("button")).toHaveLength(2);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.queryByLabelText("Сообщение помощнику")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });
  it("opens the existing service only after the explicit Vi action", async () => {
    window.history.replaceState(null, "", "/");
    // jsdom has no native dialog API; real focus/Escape/backdrop are verified in Chromium.
    Object.defineProperties(HTMLDialogElement.prototype, {
      showModal: {
        configurable: true,
        value: function (this: HTMLDialogElement) {
          this.open = true;
        },
      },
      close: {
        configurable: true,
        value: function (this: HTMLDialogElement) {
          this.open = false;
        },
      },
    });
    const fetch = vi
      .spyOn(globalThis, "fetch")
      .mockImplementation(
        async (path) =>
          new Response(
            JSON.stringify(
              String(path).endsWith("/industry-capabilities")
                ? { enabled: false, industries: [] }
                : [],
            ),
            { status: 200 },
          ),
      );
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Познакомьтесь с Ви" }));
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Начать с Ви" }));
    await screen.findByRole("heading", {
      name: "Какой бизнес вы хотите открыть?",
    });
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(fetch.mock.calls.map(([path]) => String(path)).sort()).toEqual([
      "/api/v1/consent-texts",
      "/api/v2/industry-capabilities",
    ]);
    expect(screen.queryByRole("dialog")).toBeNull();
  });
  it("distinguishes restoring the project from actually waiting for a reply", () => {
    const props = {
      conversation: null,
      messages: [],
      busy: true,
      onNew: vi.fn(),
      onRefresh: vi.fn(),
      onSend: vi.fn(),
      onPatch: vi.fn(),
    };
    const { container, rerender } = render(
      <Chat {...props} waitingForReply={false} />,
    );
    expect(container.querySelector(".vi-chat")).toHaveAttribute(
      "data-emotion",
      "neutral",
    );
    expect(screen.queryByText("Обдумываю…")).toBeNull();
    rerender(<Chat {...props} waitingForReply />);
    expect(container.querySelector(".vi-chat")).toHaveAttribute(
      "data-emotion",
      "thinking",
    );
    expect(screen.getByRole("status")).toHaveTextContent("Обдумываю…");
    rerender(<Chat {...props} busy={false} waitingForReply={false} />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(container.querySelector(".vi-chat")).toHaveAttribute(
      "data-emotion",
      "greeting",
    );
  });
  it("documents the actual22 sheet labels and exact original crop provenance", () => {
    expect(provenance.sheet_labels).toHaveLength(22);
    expect(new Set(provenance.sheet_labels).size).toBe(22);
    expect(provenance.sheet_labels).toContain("Печатает / Обрабатывает");
    expect(Object.keys(provenance.assets)).toHaveLength(14);
    for (const asset of Object.values(provenance.assets)) {
      expect(provenance.sources).toHaveProperty(asset.source);
      expect(asset.sha256).toMatch(/^[a-f0-9]{64}$/);
      expect(asset.bytes).toBeLessThan(50000);
    }
  });
});
