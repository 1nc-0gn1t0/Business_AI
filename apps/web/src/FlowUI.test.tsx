import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Idea, Summary } from "./FlowUI";
import { canEnter, restoredStage, type Stage } from "./flow";
import type { Conversation, Ranking, Schemas } from "./api";
import finance from "../../../docs/examples/BA-009-coffee-result.json";
import geo from "../../../docs/examples/BA-008-kazan-coffee.json";
const view = {
  profile: finance.response.request_snapshot.profile,
  missing_fields: [],
} as unknown as Conversation;
const ranking = geo.scenarios.covered_BA007_zones
  .response as unknown as Ranking;
const state = {
  conversation: view,
  ranking,
  selected: ranking.candidates.features[0].id,
  finance: finance.response as unknown as Schemas["FinanceResult"],
};

describe("DESIGN-02 guarded journey", () => {
  it("starts with one question and one action without a dashboard or a request on typing", () => {
    const send = vi.fn();
    const edit = vi.fn();
    render(<Idea draft="" onDraft={edit} onSend={send} busy={false} />);
    expect(
      screen.getByRole("heading", { name: "Какой бизнес вы хотите открыть?" }),
    ).toBeVisible();
    expect(screen.getAllByRole("button")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Сообщение помощнику"), {
      target: { value: "Кофейня" },
    });
    expect(edit).toHaveBeenCalledWith("Кофейня");
    expect(send).not.toHaveBeenCalled();
  });
  for (const stage of [
    "location",
    "finance",
    "banking",
    "summary",
  ] as Stage[]) {
    it(`blocks ${stage} without a server-confirmed profile`, () =>
      expect(
        canEnter(stage, {
          ...state,
          conversation: {
            ...view,
            profile: { ...view.profile, confirmation_state: "draft" },
          },
        }),
      ).toBe(false));
  }
  for (const stage of ["finance", "banking", "summary"] as Stage[]) {
    it(`blocks ${stage} with a substituted zone identifier`, () =>
      expect(canEnter(stage, { ...state, selected: "foreign-zone" })).toBe(
        false,
      ));
  }
  it("requires a current finance result for banking and summary", () => {
    expect(canEnter("finance", state)).toBe(true);
    expect(canEnter("banking", { ...state, finance: null })).toBe(false);
    expect(canEnter("summary", { ...state, finance: null })).toBe(false);
    expect(canEnter("summary", state)).toBe(true);
  });
  it("restores only what the server actually knows", () => {
    expect(restoredStage(view)).toBe("location");
    expect(
      restoredStage({
        ...view,
        profile: { ...view.profile, confirmation_state: "draft" },
      }),
    ).toBe("review");
    expect(
      restoredStage({
        ...view,
        missing_fields: ["city"],
        profile: { ...view.profile, confirmation_state: "draft" },
      }),
    ).toBe("chat");
  });
  it("summarizes actual results and honestly omits optional bank matching", () => {
    render(
      <Summary
        conversation={view}
        ranking={ranking}
        selected={state.selected}
        finance={state.finance}
        bank={null}
        onEdit={vi.fn()}
      />,
    );
    expect(screen.getByText("Не включены — по вашему выбору")).toBeVisible();
    fireEvent.click(screen.getByText("Об ограничениях"));
    expect(screen.getByText(/синтетических допущениях/)).toBeVisible();
    expect(
      screen.getByText("285 000 ₽ / мес.", { exact: false }),
    ).toBeVisible();
  });
});
