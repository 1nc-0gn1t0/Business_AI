import type { Schemas } from "./api";
import type { ViEmotion } from "./Vi";

export function financialVi(
  view: Schemas["FinancialView"] | null,
  pending: "propose" | "calculate" | null,
  error: string,
): { emotion: ViEmotion; text: string } {
  if (error) return { emotion: "error", text: error };
  const operation = view?.operation;
  if (pending || operation?.state === "running") {
    const proposal = (pending || operation?.kind) === "propose";
    return {
      emotion: proposal ? "thinking" : "working",
      text: proposal
        ? "Готовлю сценарные предположения…"
        : "Рассчитываю экономику…",
    };
  }
  if (operation?.state === "cancelled")
    return {
      emotion: "support",
      text: "Операция отменена. Подтверждённые вводные сохранены.",
    };
  if (operation?.state === "interrupted")
    return {
      emotion: "uncertain",
      text: "Запрос прерван. Проверьте состояние перед безопасным повтором.",
    };
  if (operation?.state === "failed")
    return {
      emotion: "error",
      text: "Не получилось завершить запрос. Можно ввести параметры вручную.",
    };
  if (view?.needs_review.length)
    return {
      emotion: "curious",
      text: "Проверьте и подтвердите предложенные параметры.",
    };
  const result = view?.current ? view.result?.result : null;
  if (result?.status === "calculated") {
    const loss = result.scenarios.some((s) => Number(s.operating_result) < 0);
    return {
      emotion: loss ? "neutral" : "idea",
      text: loss
        ? "Расчёт готов. В сценариях есть убыток — сравните вводные и ограничения."
        : "Расчёт готов для выбранных вводных. Это не гарантия дохода.",
    };
  }
  return {
    emotion: "uncertain",
    text: "Не хватает подтверждённых данных для полного расчёта.",
  };
}
