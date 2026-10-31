import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { industryFixture } from "../e2e/industry.fixture";
import fixture from "../e2e/fixtures/financial-scenarios.json" with { type: "json" };
import AnalysisResult from "./AnalysisResult";
import type { Schemas } from "./api";

afterEach(() => vi.unstubAllGlobals());
const props = {
  credential: { id: "fixture", token: "not-a-real-token" },
  profileRevision: 3,
  onEdit: vi.fn(),
  onFinance: vi.fn(),
  onBank: vi.fn(),
};
function result() {
  const profile = industryFixture("online_school", true, true);
  return {
    schema_version: "analysis-result-v2",
    conversation_id: "fixture",
    profile_revision: 3,
    assessed_at: "2026-10-31T00:00:00Z",
    state: "completed",
    profile: profile.profile,
    plan: profile.plan,
    sections: [],
    limitations: ["Explicit test fixture"],
    financial: structuredClone(fixture.result),
  } as unknown as Schemas["AnalysisResult"];
}
describe("integrated current result", () => {
  it("renders the stored scenarios and preserves neutral losses", async () => {
    const view = result();
    view.financial!.result.scenarios[1].operating_result = "-1.00";
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(view))),
    );
    render(<AnalysisResult {...props} />);
    await screen.findByRole("heading", { name: "Базовый" });
    expect(screen.getByRole("status")).toHaveAttribute(
      "data-emotion",
      "neutral",
    );
    expect(
      screen.getByText(/PDF для новых отраслей пока недоступен/),
    ).toBeInTheDocument();
  });
  it("hides mismatched profile results instead of treating stale inputs as zero", async () => {
    const view = result();
    view.profile_revision = 4;
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(view))),
    );
    render(<AnalysisResult {...props} />);
    await screen.findByText(/Профиль изменился/);
    expect(
      screen.queryByRole("heading", { name: "Базовый" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Скачать итоговый JSON" }),
    ).not.toBeInTheDocument();
  });
  it("does not retain financial content after consent withdrawal", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(result())))
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: { code: "consent_required" } }), {
          status: 403,
        }),
      );
    vi.stubGlobal("fetch", fetch);
    render(<AnalysisResult {...props} />);
    await screen.findByRole("heading", { name: "Базовый" });
    fireEvent(window, new Event("focus"));
    await screen.findByRole("button", { name: "Повторить проверку" });
    expect(
      screen.queryByRole("heading", { name: "Базовый" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveAttribute("data-emotion", "error");
  });
});
