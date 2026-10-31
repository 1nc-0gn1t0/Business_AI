import { useEffect, useRef, useState } from "react";
import { errorText, request, type Credential, type Schemas } from "./api";
import { ViStatus } from "./Vi";
import { FinancialResults } from "./FinancialScenarios";

type Result = Schemas["AnalysisResult"];
const labels: Record<string, string> = {
  profile: "Вводные",
  geography: "География",
  finance: "Финансы",
  banking: "Банковские возможности",
  completed: "Готово",
  partial: "Частично",
  not_required: "Не требуется",
  unsupported: "Метод недоступен",
  missing: "Нет данных",
  needs_review: "Нужно подтверждение",
  "geo.mapped_poi": "Объекты на карте",
  "geo.vehicle_network": "Автомобильная дорожная сеть",
  available: "Есть в заявленных границах",
  stale: "Требуется обновление",
  unknown: "Покрытие неизвестно",
};

export default function AnalysisResult({
  credential,
  profileRevision,
  onEdit,
  onFinance,
  onBank,
}: {
  credential: Credential;
  profileRevision: number;
  onEdit: () => void;
  onFinance: () => void;
  onBank: () => void;
}) {
  const [view, setView] = useState<Result | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  const latestRequest = useRef<symbol | null>(null);
  const url = `/api/v2/conversations/${credential.id}/analysis-result`;
  useEffect(() => {
    const controller = new AbortController();
    function refresh() {
      const marker = Symbol();
      latestRequest.current = marker;
      setBusy(true);
      request<Result>(url, { credential, signal: controller.signal })
        .then((next) => {
          if (!controller.signal.aborted && marker === latestRequest.current) {
            setView(next);
            setError("");
          }
        })
        .catch((e) => {
          if (!controller.signal.aborted && marker === latestRequest.current) {
            setView(null);
            setError(errorText(e));
          }
        })
        .finally(() => {
          if (!controller.signal.aborted && marker === latestRequest.current)
            setBusy(false);
        });
    }
    refresh();
    window.addEventListener("focus", refresh);
    window.addEventListener("online", refresh);
    return () => {
      latestRequest.current = null;
      controller.abort();
      window.removeEventListener("focus", refresh);
      window.removeEventListener("online", refresh);
    };
  }, [url, credential, retry]);
  const current =
    view?.profile_revision === profileRevision &&
    view.profile.confirmed_revision === profileRevision;
  const loss = view?.financial?.result.scenarios.some(
    (s) => Number(s.operating_result) < 0,
  );
  async function download() {
    const marker = Symbol();
    latestRequest.current = marker;
    setBusy(true);
    try {
      const next = await request<Result>(url, { credential });
      if (marker !== latestRequest.current) return;
      setView(next);
      if (
        next.profile_revision !== profileRevision ||
        next.profile.confirmed_revision !== profileRevision
      )
        return;
      const blob = URL.createObjectURL(
        new Blob([JSON.stringify(next, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = blob;
      a.download = "business-analysis-v2.json";
      a.click();
      URL.revokeObjectURL(blob);
    } catch (e) {
      if (marker === latestRequest.current) {
        setView(null);
        setError(errorText(e));
      }
    } finally {
      if (marker === latestRequest.current) setBusy(false);
    }
  }
  return (
    <section className="summary-screen">
      <h1>Предварительный результат</h1>
      <ViStatus
        announce
        emotion={
          error
            ? "error"
            : busy
              ? "search"
              : !current || view?.state !== "completed"
                ? "uncertain"
                : loss
                  ? "neutral"
                  : "success"
        }
      >
        {error ||
          (busy
            ? "Проверяю сохранённый результат…"
            : !current
              ? "Профиль изменился или требует подтверждения. Прежний результат не показан как актуальный."
              : view.state === "completed"
                ? loss
                  ? "Расчёт готов. В сценариях есть убыток."
                  : "Расчёт подготовлен по выбранным вводным."
                : "Доступен частичный результат. Ограничения перечислены ниже.")}
      </ViStatus>
      {error && (
        <button className="button" onClick={() => setRetry((r) => r + 1)}>
          Повторить проверку
        </button>
      )}
      {current && view && (
        <>
          <p>Исходная идея: {view.profile.idea}</p>
          <dl>
            {view.sections.map((section) => (
              <div key={section.id}>
                <dt>
                  {labels[section.id]} · {labels[section.state]}
                </dt>
                <dd>{section.explanation}</dd>
              </div>
            ))}
          </dl>
          {view.plan.coverage && (
            <details>
              <summary>Покрытие и источники данных</summary>
              <ul>
                {view.plan.coverage.assessments.map((a) => (
                  <li key={a.category}>
                    {labels[a.category] || a.category}:{" "}
                    {labels[a.local_status] || a.local_status}.
                  </li>
                ))}
              </ul>
              <p>
                Оценка metadata на {view.assessed_at}. Это не подтверждение
                полного покрытия города или отсутствия организаций.
              </p>
            </details>
          )}
          {view.financial && (
            <FinancialResults
              value={view.financial.result}
              parameters={view.financial.configuration.parameters}
            />
          )}
          <details>
            <summary>Вводные, происхождение и формулы</summary>
            {view.financial && (
              <>
                <p>
                  Snapshot {view.financial.id} · {view.financial.created_at} ·
                  версия вводных {view.financial.inputs.revision}.
                </p>
                <ul>
                  {Object.entries(view.financial.inputs.entries || {}).map(
                    ([key, entry]) => (
                      <li key={key}>
                        {key}: {String(entry.base)} {entry.unit} ·{" "}
                        {entry.source.origin}/{entry.epistemic} · {entry.review}{" "}
                        · {entry.basis}
                      </li>
                    ),
                  )}
                </ul>
                <pre>
                  {JSON.stringify(view.financial.result.formulas, null, 2)}
                </pre>
              </>
            )}
            <ul>
              {view.limitations.map((text) => (
                <li key={text}>{text}</li>
              ))}
            </ul>
          </details>
          <button
            className="button"
            disabled={busy}
            onClick={() => void download()}
          >
            Скачать итоговый JSON
          </button>
          <p>PDF для новых отраслей пока недоступен.</p>
        </>
      )}
      <div className="actions">
        <button className="text-button" onClick={onEdit}>
          Изменить проект
        </button>
        {current && view?.plan.stages.includes("finance") && (
          <button className="text-button" onClick={onFinance}>
            К финансовым вводным
          </button>
        )}
        {current && view?.plan.stages.includes("banking") && (
          <button className="text-button" onClick={onBank}>
            Банковские возможности
          </button>
        )}
      </div>
    </section>
  );
}
