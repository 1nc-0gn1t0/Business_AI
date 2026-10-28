import { ViStatus } from "./Vi";
import { useEffect, useRef, useState } from "react";
import { errorText, request, requestFile } from "./api";
import type { Conversation, Credential, Ranking, Schemas } from "./api";

type Props = {
  conversation: Conversation | null;
  credential: Credential | null;
  ranking: Ranking | null;
  selected: string | null;
  finance: Schemas["FinanceResult"] | null;
  bank: Schemas["MatchResult"] | null;
  walking: Schemas["CatchmentResult"] | null;
  provider: Schemas["IndicatorResult"] | null;
};
export function reportRequest(p: Props): Schemas["ReportRequest"] | null {
  if (!p.conversation) return null;
  return {
    expected_version: p.conversation.version,
    geo: p.ranking
      ? {
          dataset: p.ranking.candidates.dataset.slug,
          request: {
            candidates: p.ranking.candidates.request_snapshot,
            scoring: p.ranking.policy.config,
          },
          fingerprint: p.ranking.request_fingerprint,
        }
      : null,
    selected_zone: p.selected,
    finance: p.finance
      ? {
          request: p.finance.request_snapshot,
          fingerprint: p.finance.request_fingerprint,
        }
      : null,
    bank: p.bank
      ? {
          request: {
            expected_version: p.bank.profile_version,
            needs: p.bank.needs_snapshot,
            catalogue_fingerprint: p.bank.catalogue.fingerprint,
          },
          fingerprint: p.bank.request_fingerprint,
        }
      : null,
    walking:
      p.walking && p.ranking
        ? {
            dataset: p.ranking.candidates.dataset.slug,
            request: p.walking.request_snapshot,
            fingerprint: p.walking.request_fingerprint,
          }
        : null,
    providers: p.provider
      ? [
          {
            request: {
              provider: p.provider.dataset.provider,
              dataset: p.provider.dataset.slug,
              data_version: p.provider.dataset.data_version,
              mode: p.provider.selection.mode,
              bbox: p.provider.bbox,
              metrics: p.provider.indicators.map((i) => i.metric),
            },
            fingerprint: p.provider.request_fingerprint,
          },
        ]
      : [],
  };
}

export default function ReportExport(props: Props) {
  const [prepared, setPrepared] = useState<{
    context: string;
    value: Schemas["ReportView"];
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  const context = JSON.stringify([
    props.conversation?.version,
    props.ranking?.request_fingerprint,
    props.selected,
    props.finance?.request_fingerprint,
    props.bank?.request_fingerprint,
    props.walking?.request_fingerprint,
    props.provider?.request_fingerprint,
  ]);
  const outdated =
    prepared &&
    (prepared.context !== context || prepared.value.status === "outdated");
  const base = `/api/v1/conversations/${props.conversation?.id}/reports`;
  async function prepare() {
    const body = reportRequest(props);
    if (!body || !props.credential) return;
    controller.current?.abort();
    const c = new AbortController();
    controller.current = c;
    setBusy(true);
    setError("");
    try {
      const value = await request<Schemas["ReportView"]>(base, {
        method: "POST",
        credential: props.credential,
        body,
        signal: c.signal,
      });
      setPrepared({ context, value });
    } catch (e) {
      if (!c.signal.aborted) setError(errorText(e));
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  async function download(format: "pdf" | "json") {
    if (
      outdated ||
      !props.credential ||
      props.conversation?.profile.confirmation_state !== "confirmed" ||
      (!props.ranking && !props.finance)
    )
      return;
    const c = new AbortController();
    controller.current = c;
    setBusy(true);
    setError("");
    try {
      let snapshot = prepared?.value;
      if (!snapshot) {
        const body = reportRequest(props);
        if (!body) return;
        snapshot = await request<Schemas["ReportView"]>(base, {
          method: "POST",
          credential: props.credential,
          body,
          signal: c.signal,
        });
        setPrepared({ context, value: snapshot });
      }
      const current = await request<Schemas["ReportView"]>(
        `${base}/${snapshot.id}`,
        { credential: props.credential, signal: c.signal },
      );
      setPrepared({ context: prepared?.context || context, value: current });
      if (current.status === "outdated")
        throw new Error("Источники или профиль изменились. Обновите отчёт.");
      const blob = await requestFile(
        `${base}/${current.id}/file?format=${format}`,
        props.credential,
        c.signal,
      );
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `BusinessAI-report-${current.id}.${format}`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      setTimeout(() => URL.revokeObjectURL(href), 10_000);
    } catch (e) {
      if (!c.signal.aborted) setError(errorText(e));
    } finally {
      if (!c.signal.aborted) setBusy(false);
    }
  }
  const unavailable =
    busy ||
    !props.credential ||
    props.conversation?.profile.confirmation_state !== "confirmed" ||
    (!props.ranking && !props.finance);
  return (
    <section
      className="report-export"
      aria-label="Экспорт аналитического отчёта"
    >
      {(busy || error || prepared) && (
        <ViStatus
          emotion={
            error
              ? "error"
              : busy
                ? "working"
                : outdated
                  ? "uncertain"
                  : "success"
          }
        >
          {error
            ? "Документ не удалось получить. Можно повторить попытку."
            : busy
              ? "Готовлю документ…"
              : outdated
                ? "Данные изменились. Обновите отчёт."
                : "Готово! Ваш предварительный план подготовлен."}
        </ViStatus>
      )}
      {error && (
        <div className="alert" role="alert">
          {error}
        </div>
      )}
      {outdated && (
        <p className="notice" role="status">
          Вводные, профиль или источники изменились. Требуется обновить отчёт;
          старый снимок не выдаётся за актуальный.
        </p>
      )}
      <div className="report-actions">
        {outdated && (
          <button
            className="button"
            disabled={unavailable}
            onClick={() => void prepare()}
          >
            Обновить отчёт
          </button>
        )}
        <button
          className={`button ${outdated ? "secondary" : ""}`}
          disabled={unavailable || !!outdated}
          onClick={() => void download("pdf")}
        >
          {busy ? "Готовим документ…" : "Скачать PDF"}
        </button>
        <button
          className="text-button"
          disabled={unavailable || !!outdated}
          onClick={() => void download("json")}
        >
          Скачать JSON
        </button>
      </div>
      <p className="fine-print">
        Оба формата — из одного проверенного снимка. Ничего не отправляется в
        банк.
      </p>
      <details className="report-composition">
        <summary>Состав и источники отчёта</summary>
        <p>
          {props.ranking ? "Геоанализ ✓" : "Геоанализ не включён"} ·{" "}
          {props.finance
            ? "Финансы ✓"
            : "Финансы не рассчитаны / вводные изменены"}{" "}
          · {props.bank ? "Подбор продуктов ✓" : "Подбор продуктов не включён"}
          {props.provider?.dataset.origin === "synthetic"
            ? " · СИНТЕТИЧЕСКИЙ ПРОВАЙДЕР"
            : ""}
        </p>
        {!outdated && (
          <button
            className="text-button"
            disabled={unavailable}
            onClick={() => void prepare()}
          >
            {prepared ? "Обновить отчёт" : "Подготовить отчёт"}
          </button>
        )}
        {prepared && (
          <p>
            Снимок {prepared.value.id.slice(0, 8)} · профиль v
            {prepared.value.profile_version} · SHA{" "}
            {prepared.value.snapshot_sha256.slice(0, 12)}
            {prepared.value.missing_sections.length
              ? ` · Не включены: ${prepared.value.missing_sections.join(", ")}`
              : ""}
          </p>
        )}
      </details>
    </section>
  );
}
