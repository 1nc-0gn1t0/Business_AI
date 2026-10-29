import type { Conversation, Ranking, Schemas } from "./api";
import type { IndustryView } from "./Industry";

export type Stage =
  | "idea"
  | "chat"
  | "review"
  | "location"
  | "finance"
  | "banking"
  | "summary"
  | "partial";
export type FlowState = {
  conversation: Conversation | null;
  ranking: Ranking | null;
  selected: string | null;
  finance: Schemas["FinanceResult"] | null;
  universal?: IndustryView | null;
};
export function canEnter(stage: Stage, state: FlowState) {
  if (stage === "idea" || stage === "chat") return true;
  if (stage === "review") return !!state.conversation;
  if (state.universal) {
    const u = state.universal;
    if (
      u.profile.revision !== state.conversation?.version ||
      u.profile.confirmed_revision !== u.profile.revision
    )
      return false;
    if (stage === "partial") return u.plan.stages.includes("partial_result");
    if (stage === "location") return u.plan.stages.includes("location");
    if (
      stage === "finance" &&
      u.plan.stages.includes("finance") &&
      !u.plan.stages.includes("location")
    )
      return true;
    if (
      (stage === "banking" || stage === "summary") &&
      u.plan.stages.includes("finance") &&
      !u.plan.stages.includes("location")
    )
      return !!state.finance;
    if (stage === "finance" && !u.plan.stages.includes("finance")) return false;
  }
  if (stage === "partial") return false;
  if (state.conversation?.profile.confirmation_state !== "confirmed")
    return false;
  if (stage === "location") return true;
  if (!state.ranking?.candidates.features.some((f) => f.id === state.selected))
    return false;
  if (stage === "finance") return true;
  return !!state.finance;
}
export function restoredStage(view: Conversation): Stage {
  if (view.profile.confirmation_state === "confirmed") return "location";
  return view.missing_fields.length ? "chat" : "review";
}
export const stepFor: Record<Stage, number> = {
  idea: 1,
  chat: 1,
  review: 1,
  location: 2,
  finance: 3,
  banking: 4,
  summary: 5,
  partial: 2,
};

export function industryStage(view: IndustryView): Stage {
  if (view.profile.confirmed_revision !== view.profile.revision)
    return view.plan.next_question ? "chat" : "review";
  if (view.plan.stages.includes("location")) return "location";
  if (view.plan.stages.includes("finance")) return "finance";
  return "partial";
}
