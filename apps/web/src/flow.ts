import type { Conversation, Ranking, Schemas } from "./api";

export type Stage =
  "idea" | "chat" | "review" | "location" | "finance" | "banking" | "summary";
export type FlowState = {
  conversation: Conversation | null;
  ranking: Ranking | null;
  selected: string | null;
  finance: Schemas["FinanceResult"] | null;
};
export function canEnter(stage: Stage, state: FlowState) {
  if (stage === "idea" || stage === "chat") return true;
  if (stage === "review") return !!state.conversation;
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
};
