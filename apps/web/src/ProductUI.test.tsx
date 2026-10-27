import { useState } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Home, ProjectOverview } from "./ProductUI";

function Idea({ send = vi.fn().mockResolvedValue(undefined) }) {
  const [draft, onDraft] = useState("");
  return (
    <Home
      conversation={null}
      draft={draft}
      onDraft={onDraft}
      onSend={send}
      busy={false}
      consent={<p>Отдельное согласие</p>}
      onResume={vi.fn()}
    />
  );
}

describe("DESIGN-01 product journey", () => {
  it("prefills examples without making a request or inventing coverage", () => {
    const send = vi.fn();
    render(<Idea send={send} />);
    fireEvent.click(screen.getByRole("button", { name: "Другой город" }));
    expect(screen.getByLabelText("Сообщение помощнику")).toHaveValue(
      "Хочу открыть магазин в Самаре. Какие данные доступны?",
    );
    expect(send).not.toHaveBeenCalled();
    expect(
      screen.getByText(/Геоанализ зависит от загруженного покрытия/),
    ).toBeVisible();
  });
  it("preserves a failed idea and allows a successful explicit retry", async () => {
    const send = vi
      .fn()
      .mockRejectedValueOnce(new Error("API unavailable"))
      .mockResolvedValueOnce(undefined);
    render(<Idea send={send} />);
    fireEvent.change(screen.getByLabelText("Сообщение помощнику"), {
      target: { value: "Моя идея" },
    });
    fireEvent.click(screen.getByLabelText("Отправить сообщение"));
    await waitFor(() =>
      expect(screen.getByLabelText("Отправить сообщение")).toBeEnabled(),
    );
    expect(screen.getByLabelText("Сообщение помощнику")).toHaveValue(
      "Моя идея",
    );
    fireEvent.click(screen.getByLabelText("Отправить сообщение"));
    await waitFor(() =>
      expect(screen.getByLabelText("Сообщение помощнику")).toHaveValue(""),
    );
    expect(send).toHaveBeenCalledTimes(2);
  });
  it("shows absent results honestly and routes to the chosen stage", () => {
    const open = vi.fn();
    render(
      <ProjectOverview
        conversation={null}
        ranking={null}
        finance={null}
        bank={null}
        onOpen={open}
      />,
    );
    expect(screen.getByText("Анализ ещё не выполнен")).toBeVisible();
    expect(screen.getByText("Профиль не подтверждён")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /Экономика/ }));
    expect(open).toHaveBeenCalledWith("finance");
    expect(screen.getByText("Без отправки в банк")).toBeVisible();
  });
});
