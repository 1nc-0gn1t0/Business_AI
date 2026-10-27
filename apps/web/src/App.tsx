import { useEffect, useRef, useState } from "react";
import Chat, { BusinessProfilePanel } from "./Chat";
import { Home, Icon, ProjectOverview, screens, type Screen } from "./ProductUI";
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
  const [tab, setTab] = useState<Screen>(() =>
    readCredential() ? "chat" : "home",
  );
  useEffect(() => {
    const main = document.getElementById("main-content");
    main?.scrollIntoView?.({ block: "start" });
    main?.focus({ preventScroll: true });
  }, [tab]);
  const [draft, setDraft] = useState("");
  const [locationsVisited, setLocationsVisited] = useState(false);
  function navigate(screen: Screen) {
    if (screen === "map" || screen === "compare") setLocationsVisited(true);
    setTab(screen);
  }
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
  function patchProfile(patch: Schemas["ProfilePatch"]) {
    return action(async () => {
      if (credential && conversation) {
        await ensureAssistant(credential);
        await mutate(
          "/profile",
          "PATCH",
          { patch, expected_version: conversation.version },
          credential,
        );
      }
    });
  }
  function confirmProfile() {
    void action(async () => {
      if (credential && conversation) {
        await ensureAssistant(credential);
        await mutate(
          "/profile/confirm",
          "POST",
          { expected_version: conversation.version },
          credential,
        );
        navigate("map");
      }
    });
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
  async function sendIdea(content: string) {
    await action(async () => {
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
      navigate("chat");
    }, true);
  }
  function newConversation() {
    void action(async () => {
      await create();
      setAssistantConsent(false);
      setDraft("");
      navigate("home");
    });
  }
  const consentControl = (
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
        Демо-текст, не документ ВТБ. Нужна правовая проверка до пилота. Это не
        согласие на маркетинг или заявку. Управление и отзыв — в разделе
        продуктов.
      </small>
    </details>
  );
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <aside className="app-sidebar">
        <button
          className="brand"
          onClick={() => navigate("home")}
          aria-label="Business AI · обзор"
        >
          <span className="brand-icon">
            <Icon name="spark" size={22} />
          </span>
          <span>
            Business<span className="brand-ai">AI</span>
            <small>ОТ ИДЕИ К РЕШЕНИЮ</small>
          </span>
        </button>
        <div className="nav-caption">ВАШ ПРОЕКТ</div>
        <nav className="product-nav" aria-label="Разделы анализа">
          {screens.map((screen) => (
            <button
              key={screen.id}
              aria-label={screen.accessible || screen.name}
              aria-current={tab === screen.id ? "step" : undefined}
              className={tab === screen.id ? "active" : ""}
              onClick={() => navigate(screen.id)}
            >
              <Icon name={screen.id} />
              <span>
                {screen.name}
                <small>{screen.note}</small>
              </span>
              {screen.id === "chat" &&
                conversation?.profile.confirmation_state === "confirmed" && (
                  <span className="nav-check">
                    <Icon name="check" size={14} />
                  </span>
                )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="new-project"
            onClick={newConversation}
            disabled={busy}
            aria-label="Новая беседа"
          >
            <span aria-hidden="true">＋</span> Новый проект
          </button>
          <div className="sidebar-note">
            <span className="tag">Хакатонный MVP</span>
            <p>
              Независимый прототип.
              <br />
              Не официальный сервис ВТБ.
            </p>
          </div>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumb">
            Рабочее пространство <span>/</span>{" "}
            <strong>{screens.find((s) => s.id === tab)?.name}</strong>
          </div>
          <div className="topbar-right">
            <span
              className="health"
              title="Проверка API и базы. Готовность модели проверяется отдельно при запросе."
            >
              <i
                className={`dot ${health === "API и PostGIS доступны" ? "mint-dot" : "amber-dot"}`}
              />
              {health}
            </span>
            <span className="avatar" aria-label="Гостевой проект">
              Г
            </span>
          </div>
        </header>
        <main
          id="main-content"
          tabIndex={-1}
          className={`main-panel screen-${tab}`}
        >
          {error && (
            <div className="alert global-alert" role="alert">
              {error}
              <button className="text-button" onClick={() => setError("")}>
                Закрыть
              </button>
            </div>
          )}
          {tab === "home" && (
            <Home
              conversation={conversation}
              draft={draft}
              onDraft={setDraft}
              onSend={sendIdea}
              busy={busy}
              consent={consentControl}
              onResume={() => navigate("chat")}
            />
          )}
          {tab === "chat" && (
            <>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">НАЧИНАЕМ С ВАШЕЙ ИДЕИ</span>
                  <h1>Давайте соберём ваш проект</h1>
                  <p>
                    Расскажите о задумке. AI уточнит детали, а вы проверите
                    параметры.
                  </p>
                </div>
                <span className="tag outline">
                  {conversation?.profile.confirmation_state === "confirmed"
                    ? "Профиль подтверждён"
                    : "Шаг 1 · идея и профиль"}
                </span>
              </div>
              <div className="ai-workspace">
                <Chat
                  consentControl={consentControl}
                  showProfile={false}
                  draft={draft}
                  onDraft={setDraft}
                  conversation={conversation}
                  messages={messages}
                  busy={busy}
                  onNew={newConversation}
                  onRefresh={() => {
                    void action(refresh);
                  }}
                  onSend={sendIdea}
                  onPatch={patchProfile}
                  onConfirm={confirmProfile}
                />
                <aside className="context-panel" aria-label="Контекст проекта">
                  {conversation ? (
                    <BusinessProfilePanel
                      conversation={conversation}
                      busy={busy}
                      onPatch={patchProfile}
                      onConfirm={confirmProfile}
                    />
                  ) : (
                    <div className="empty">
                      <Icon name="report" size={28} />
                      <h2>Здесь появится профиль</h2>
                      <p>
                        Напишите, какой бизнес хотите открыть. Город, бюджет и
                        формат появятся после ответа сервера.
                      </p>
                    </div>
                  )}
                </aside>
              </div>
            </>
          )}
          <div className="main-content">
            {locationsVisited && (
              <div hidden={tab !== "map" && tab !== "compare"}>
                <Locations
                  key={`${conversation?.id || "none"}:${conversation?.version ?? 0}`}
                  profile={conversation?.profile || null}
                  ranking={ranking}
                  onRanking={setRanking}
                  selected={selected}
                  onSelect={setSelected}
                  comparison={tab === "compare"}
                  onFinance={() => navigate("finance")}
                  onWalkingReport={setReportWalking}
                  onProviderReport={setReportProvider}
                />
              </div>
            )}
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
          {tab === "report" && (
            <ProjectOverview
              conversation={conversation}
              ranking={ranking}
              finance={reportFinance}
              bank={reportBank}
              onOpen={navigate}
            />
          )}
          <div
            className={tab === "report" ? "report-page-actions" : "report-dock"}
            hidden={tab === "home" || tab === "chat"}
          >
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
          </div>
          {tab !== "home" && tab !== "chat" && tab !== "report" && (
            <div className="next-step">
              <span>Сохраните выводы и источники в одном документе</span>
              <button
                className="text-button"
                onClick={() => navigate("report")}
              >
                К итогам проекта <Icon name="arrow" size={16} />
              </button>
            </div>
          )}
        </main>
        <footer className="product-footer">
          <span>Business AI · хакатонный прототип</span>
          <span>Источники видны. Допущения обозначены. Решение — за вами.</span>
        </footer>
      </div>
    </div>
  );
}
