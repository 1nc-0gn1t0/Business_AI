import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { industryCatalog, industryFixture } from "../e2e/industry.fixture";
import { IndustryResult, IndustryReview } from "./Industry";
import { canEnter, industryStage } from "./flow";
import { demoInput } from "./Finance";

describe("U-04 backend-driven stages", () => {
  it("projects confirmed coffee inputs only into the base scenario", () => {
    const profile = industryFixture("coffee_shop", true, true).conversation
      .profile;
    const before = demoInput(profile, null);
    const source = {
      origin: "user_input" as const,
      source_name: "fixture",
      data_version: "v2-3",
      confidence: "low" as const,
      limitations: ["fixture, not market evidence"],
      observed_at: null,
      evidence_ref: null,
      source_attested: false,
    };
    const after = demoInput(profile, null, {
      average_check: { value: "450", source },
      sales_per_day: { value: 88, source },
    });
    expect(after.scenarios.base.average_check.value).toBe("450");
    expect(after.scenarios.base.sales_per_day.value).toBe(88);
    expect(after.scenarios.conservative).toEqual(before.scenarios.conservative);
    expect(after.scenarios.optimistic).toEqual(before.scenarios.optimistic);
  });
  it("restores school to a no-map partial result and rejects finance without adapter", () => {
    const view = industryFixture("online_school", true, true);
    expect(industryStage(view)).toBe("partial");
    const state = {
      conversation: view.conversation,
      universal: view,
      ranking: null,
      selected: null,
      finance: null,
    };
    expect(canEnter("partial", state)).toBe(true);
    expect(canEnter("location", state)).toBe(false);
    expect(canEnter("finance", state)).toBe(false);
    expect(
      canEnter("partial", {
        ...state,
        conversation: { ...view.conversation, version: 99 },
      }),
    ).toBe(false);
  });
  it("shows unknowns and requires server confirmation", () => {
    const view = industryFixture("online_school");
    const save = vi.fn().mockResolvedValue(undefined);
    render(
      <IndustryReview
        view={view}
        industries={industryCatalog}
        busy={false}
        onSave={save}
        onConfirm={vi.fn()}
        onChat={vi.fn()}
      />,
    );
    expect(screen.getByRole("button", { name: "Продолжить" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Пока не знаю" }));
    expect(save).toHaveBeenCalledWith({
      updates: [],
      defer_fields: [view.plan.missing_fields[0]],
    });
  });
  it("does not fabricate financial KPIs or a PDF for an unsupported industry", () => {
    render(
      <IndustryResult
        view={industryFixture("online_school", true, true)}
        busy={false}
        onEdit={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(screen.getByText(/без карты/)).toBeVisible();
    expect(
      screen.getByText(/прибыль и отраслевой рейтинг пока не рассчитаны/),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Скачать вводные JSON" }),
    ).toBeVisible();
    expect(screen.queryByText("Скачать PDF")).toBeNull();
  });
});
