import { describe, expect, it } from "vitest";
import fixture from "../e2e/fixtures/financial-scenarios.json" with { type: "json" };
import type { Schemas } from "./api";
import { financialVi } from "./viState";

const value = () =>
  structuredClone(fixture) as unknown as Schemas["FinancialView"];
describe("Vi business state, not HTTP success", () => {
  it("keeps losses neutral and missing values uncertain", () => {
    const v = value();
    v.needs_review = [];
    v.result!.result.scenarios[1].operating_result = "-1.00";
    expect(financialVi(v, null, "").emotion).toBe("neutral");
    v.current = false;
    expect(financialVi(v, null, "").emotion).toBe("uncertain");
  });
  it("maps review, execution, errors and cancellation independently", () => {
    const v = value();
    v.needs_review = ["rent"];
    expect(financialVi(v, null, "").emotion).toBe("curious");
    expect(financialVi(v, "propose", "").emotion).toBe("thinking");
    expect(financialVi(v, "calculate", "").emotion).toBe("working");
    expect(financialVi(v, "calculate", "network unavailable").emotion).toBe(
      "error",
    );
    for (const [state, emotion] of [
      ["cancelled", "support"],
      ["interrupted", "uncertain"],
      ["failed", "error"],
    ] as const) {
      v.operation = {
        state,
        kind: "propose",
        request_id: "fixture",
        profile_revision: 2,
        input_revision: 2,
        created_at: "2026-10-31T00:00:00Z",
        deadline_at: "2026-10-31T00:03:00Z",
      };
      expect(financialVi(v, null, "").emotion).toBe(emotion);
    }
  });
});
