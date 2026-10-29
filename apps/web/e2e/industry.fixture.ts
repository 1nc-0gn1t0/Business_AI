// Explicit browser fixtures, seeded from recorded QA DTOs. No production import.
import live from "../../../docs/qa/u-04/live-qwen.json" with { type: "json" };
import type { IndustryView } from "../src/Industry";

export const caseNames = {
  coffee_shop: "coffee",
  auto_repair: "auto",
  online_school: "school",
  generic: "unknown",
};
export const industryCatalog = Object.keys(caseNames).map(
  (id) => industryFixture(id).configuration,
);

export function industryFixture(
  industry = "online_school",
  ready = false,
  confirmed = false,
): IndustryView {
  const entry = live.cases.find(
    (c) => c.case === caseNames[industry as keyof typeof caseNames],
  )!;
  const view = structuredClone(entry.response) as unknown as IndustryView;
  const revision = confirmed ? 3 : ready ? 2 : 1;
  view.conversation.id = "design02-explicit-mock-session";
  view.conversation.version = revision;
  view.profile.conversation_id = view.conversation.id;
  view.profile.revision = revision;
  view.profile.confirmed_revision = confirmed ? revision : null;
  view.profile.extensions ||= {};
  view.profile.values ||= {};
  const inputs: Record<string, string | number | boolean> = {
    budget: "1500000",
    city: "Казань",
    format: "онлайн",
    funding: "own_funds",
    audience: "взрослые",
    payment_model: "за курс",
    students: 20,
    specialization: "ремонт",
    service_bays: 4,
    physical_premises: industry !== "online_school",
    business_model: "service",
    revenue_streams: "оплата услуг",
  };
  if (ready || confirmed) {
    for (const key of view.configuration.required) {
      const definition = view.field_definitions.find((f) => f.id === key)!;
      const target = view.configuration.fields.some((f) => f.id === key)
        ? (view.profile.extensions[industry] ||= {})
        : view.profile.values;
      target[key] = {
        value: inputs[key],
        unit: definition.unit,
        origin: "user_input",
        epistemic: "user_provided",
        review: confirmed ? "confirmed" : "proposed",
        evidence: "explicit browser fixture",
        lineage: "user_edit",
      };
    }
    view.plan.missing_fields = [];
    view.plan.next_question = null;
  }
  view.plan.profile_revision = revision;
  view.plan.stages = confirmed
    ? industry === "coffee_shop"
      ? ["location", "finance", "partial_result"]
      : ["partial_result"]
    : ready
      ? ["confirm"]
      : ["clarify"];
  if (confirmed) {
    view.conversation.profile.confirmation_state =
      industry === "coffee_shop" ? "confirmed" : "draft";
    view.plan.capabilities = view.plan.capabilities.map((c) =>
      c.id === "geo.analysis" && industry === "coffee_shop"
        ? { ...c, status: "partial" }
        : c,
    );
  }
  view.conversation.assistant_message =
    view.plan.next_question || "Проверьте параметры проекта.";
  return view;
}
