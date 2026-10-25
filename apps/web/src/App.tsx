import { useEffect, useRef, useState } from "react";
import Chat from "./Chat";
import Locations from "./Locations";
import Finance from "./Finance";
import BankProducts from "./BankProducts";
import ReportExport from "./ReportExport";
import {
  ApiError,
  errorText,
  history,
  readCredential,
  request,
  rub,
  saveCredential,
} from "./api";
import type { Conversation, Credential, Ranking, Schemas } from "./api";

export default function App() {
  const [credential, setCredential] = useState<Credential | null>(
    readCredential,
  );
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Schemas["MessageView"][]>([]);
  const [busy, setBusy] = useState(() => Boolean(readCredential()));
  const [error, setError] = useState("");
  const [health, setHealth] = useState("Проверка API");
  const [tab, setTab] = useState<"map" | "compare" | "finance" | "bank">("map");
  const [ranking, setRanking] = useState<Ranking | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [reportFinance, setReportFinance] = useState<
    Schemas["FinanceResult"] | null
  >(null);
  const [reportBank, setReportBank] = useState<Schemas["MatchResult"] | null>(
    null,
  );
  const [reportWalking, setReportWalking] = useState<
    Schemas["CatchmentResult"] | null
  >(null);
  const [reportProvider, setReportProvider] = useState<
    Schemas["IndicatorResult"] | null
  >(null);
  const [financeContext, setFinanceContext] = useState(0);
  const [assistantConsent, setAssistantConsent] = useState(false);
  const [consentText, setConsentText] = useState<Schemas["ConsentText"] | null>(
    null,
  );
  useEffect(() => {
    const c = new AbortController();
    request<Schemas["ConsentText"][]>("/api/v1/consent-texts", {
      signal: c.signal,
    })
      .then((texts) =>
        setConsentText(texts.find((t) => t.purpose === "assistant") || null),
      )
      .catch(() => {
        /* A missing text never implies consent. */
      });
    return () => c.abort();
  }, []);
  async function ensureAssistant(key: Credential) {
    const state = await request<Schemas["ConsentState"]>(
      `/api/v1/conversations/${key.id}/consents`,
      { credential: key },
    );
    const current = state.consents.find((c) => c.purpose === "assistant")!;
    if (
      current.status === "granted" &&
      current.text_version === consentText?.version
    )
      return;
    if (!assistantConsent || !consentText || current.status !== "not_given")
      throw new Error(
        "Нужно отдельное согласие на использование ассистента. После отзыва включите его заново в разделе продуктов и согласий.",
      );
    await request(`/api/v1/conversations/${key.id}/consents/assistant`, {
      credential: key,
      method: "PUT",
      body: {
        expected_revision: current.revision,
        text_version: consentText.version,
        decision: "grant",
      },
    });
  }
  const lock = useRef(false);
  useEffect(() => {
    const c = new AbortController();
    request<Schemas["HealthResponse"]>("/healthz", { signal: c.signal })
      .then(() => setHealth("API и PostGIS доступны"))
      .catch(() => {
        if (!c.signal.aborted) setHealth("API недоступен");
      });
    return () => c.abort();
  }, []);
  useEffect(() => {
    const credential = readCredential();
    if (!credential) return;
    const c = new AbortController();
    Promise.all([
      request<Conversation>(`/api/v1/conversations/${credential.id}`, {
        credential,
        signal: c.signal,
      }),
      history(credential, c.signal),
    ])
      .then(([view, items]) => {
        setConversation(view);
        setMessages(items);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(errorText(e));
      })
      .finally(() => {
        if (!c.signal.aborted) setBusy(false);
      });
    return () => c.abort();
  }, []);
  async function refresh(key = credential) {
    if (!key) return;
    const [view, items] = await Promise.all([
      request<Conversation>(`/api/v1/conversations/${key.id}`, {
        credential: key,
      }),
      history(key),
    ]);
    setConversation(view);
    setMessages(items);
    setRanking(null);
    setSelected(null);
    setFinanceContext((n) => n + 1);
  }
  async function create() {
    const created = await request<Schemas["ConversationCreated"]>(
      "/api/v1/conversations",
      { method: "POST" },
    );
    const key = { id: created.id, token: created.access_token };
    if (!saveCredential(key))
      setError(
        "Браузер запретил сохранение ключа. Не закрывайте и не перезагружайте вкладку: доступ к этой беседе будет утрачен.",
      );
    setCredential(key);
    setConversation(created);
    setMessages([]);
    setRanking(null);
    setSelected(null);
    setFinanceContext((n) => n + 1);
    return { key, view: created };
  }
  async function action(work: () => Promise<void>, propagate = false) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      if (
        e instanceof ApiError &&
        (e.code === "version_conflict" || e.code === "network")
      ) {
        try {
          await refresh();
        } catch {
          /* Preserve the original action error. */
        }
      }
      setError(errorText(e));
      if (propagate) throw e;
    } finally {
      setBusy(false);
      lock.current = false;
    }
  }
  async function mutate(
    path: string,
    method: string,
    body: unknown,
    key: Credential,
  ) {
    const view = await request<Conversation>(
      `/api/v1/conversations/${key.id}${path}`,
      { method, body, credential: key },
    );
    setConversation(view);
    setRanking(null);
    setSelected(null);
    setFinanceContext((n) => n + 1);
    setMessages(await history(key));
  }
  const zone =
    ranking && selected
      ? {
          dataset_slug: ranking.candidates.dataset.slug,
          data_version: ranking.candidates.dataset.data_version,
          candidate_id: selected,
          ranking_fingerprint: ranking.request_fingerprint,
        }
      : null;
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-icon">
            b<span>·</span>
          </span>
          <span>
            Business<span className="brand-ai">AI</span>
          </span>
        </a>
        <span className="brand-divider" />
        <span className="brand-caption">Ваш бизнес начинается с решения</span>
        <div className="topbar-right">
          <span className="health">
            <i
              className={`dot ${health === "API и PostGIS доступны" ? "mint-dot" : "amber-dot"}`}
            />
            {health}
          </span>
          <span className="tag">MVP</span>
          <span className="avatar">S</span>
        </div>
      </header>
      <div className="workspace">
        <Chat
          consentControl={
            <details className="assistant-consent">
              <summary>Использование ассистента · отдельное согласие</summary>
              <p>
                {consentText?.text ||
                  "Текст согласия загружается. При ошибке обновите страницу."}
              </p>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={assistantConsent}
                  disabled={!consentText || busy}
                  onChange={(e) => setAssistantConsent(e.target.checked)}
                />
                Согласен на использование ассистента
              </label>
              <small>
                Демо-текст, не документ ВТБ. Нужна правовая проверка до пилота.
                Это не согласие на маркетинг или заявку. Управление и отзыв — в
                разделе продуктов.
              </small>
            </details>
          }
          conversation={conversation}
          messages={messages}
          busy={busy}
          onNew={() => {
            void action(async () => {
              await create();
              setAssistantConsent(false);
            });
          }}
          onRefresh={() => {
            void action(refresh);
          }}
          onSend={(content) =>
            action(async () => {
              const current =
                credential && conversation
                  ? { key: credential, view: conversation }
                  : await create();
              await ensureAssistant(current.key);
              await mutate(
                "/messages",
                "POST",
                { content, expected_version: current.view.version },
                current.key,
              );
            }, true)
          }
          onPatch={(patch) =>
            action(async () => {
              if (credential && conversation) {
                await ensureAssistant(credential);
                await mutate(
                  "/profile",
                  "PATCH",
                  { patch, expected_version: conversation.version },
                  credential,
                );
              }
            })
          }
          onConfirm={() => {
            void action(async () => {
              if (credential && conversation) {
                await ensureAssistant(credential);
                await mutate(
                  "/profile/confirm",
                  "POST",
                  { expected_version: conversation.version },
                  credential,
                );
              }
            });
          }}
        />
        <main className="main-panel">
          <div className="workspace-top">
            <div className="breadcrumb">
              Рабочее пространство <span>/</span>{" "}
              {conversation?.profile.category || "Новая бизнес-идея"}
            </div>
            <span className="subtle">{rub(conversation?.profile.budget)}</span>
          </div>
          <nav className="tabs" aria-label="Разделы анализа">
            <button
              className={tab === "map" ? "active" : ""}
              onClick={() => setTab("map")}
            >
              <span>⌖</span> Карта и локации
            </button>
            <button
              className={tab === "compare" ? "active" : ""}
              onClick={() => setTab("compare")}
            >
              <span>▥</span> Сравнение зон
            </button>
            <button
              className={tab === "finance" ? "active" : ""}
              onClick={() => setTab("finance")}
            >
              <span>↗</span> Финансовая модель
            </button>
            <button
              className={tab === "bank" ? "active" : ""}
              onClick={() => setTab("bank")}
            >
              <span>◇</span> Продукты ВТБ
            </button>
          </nav>
          {error && (
            <div className="alert global-alert" role="alert">
              {error}
              <button className="text-button" onClick={() => setError("")}>
                Закрыть
              </button>
            </div>
          )}
          <div className="main-content">
            <ReportExport
              key={conversation?.id || "none"}
              conversation={conversation}
              credential={credential}
              ranking={ranking}
              selected={selected}
              finance={reportFinance}
              bank={reportBank}
              walking={reportWalking}
              provider={reportProvider}
            />
            <div hidden={tab === "finance" || tab === "bank"}>
              <Locations
                key={`${conversation?.id || "none"}:${conversation?.version ?? 0}`}
                profile={conversation?.profile || null}
                ranking={ranking}
                onRanking={setRanking}
                selected={selected}
                onSelect={setSelected}
                comparison={tab === "compare"}
                onFinance={() => setTab("finance")}
                onWalkingReport={setReportWalking}
                onProviderReport={setReportProvider}
              />
            </div>
            <div hidden={tab !== "finance"}>
              <Finance
                key={`${financeContext}:${selected || "none"}`}
                profile={conversation?.profile || null}
                zone={zone}
                onReport={setReportFinance}
              />
            </div>
            <div hidden={tab !== "bank"}>
              <BankProducts
                key={`${conversation?.id || "none"}:${conversation?.version ?? 0}`}
                active={tab === "bank"}
                conversation={conversation}
                credential={credential}
                onReport={setReportBank}
                onProfileConflict={() => {
                  void action(async () => {
                    await refresh();
                    setError(
                      "Профиль изменился. Проверьте актуальные параметры и повторите банковский подбор.",
                    );
                  });
                }}
              />
            </div>
          </div>
          <footer className="product-footer">
            <span>Sab0tage · Business AI</span>
            <span>Данные → контекст → осознанное решение</span>
            <span>Подбор продуктов — демо · заявки не отправляются</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
