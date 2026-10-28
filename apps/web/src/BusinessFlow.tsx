import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react";
import Chat from "./Chat";
import { ViAvatar } from "./Vi";
import {
  ConsentDialog,
  Idea,
  ModuleBoundary,
  ProjectReview,
  Summary,
} from "./FlowUI";
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
import { canEnter, restoredStage, stepFor, type Stage } from "./flow";

const Locations = lazy(() => import("./Locations"));
class ConsentRequired extends Error {}

export default function BusinessFlow({
  onHome,
  active = true,
}: {
  onHome: () => void;
  active?: boolean;
}) {
  const [credential, setCredential] = useState<Credential | null>(
    readCredential,
  );
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Schemas["MessageView"][]>([]);
  const [waitingForReply, setWaitingForReply] = useState(false);
  const [busy, setBusy] = useState(() => Boolean(readCredential()));
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [accessLost, setAccessLost] = useState(false);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const [stage, setStage] = useState<Stage>(() =>
    readCredential() ? "chat" : "idea",
  );
  const [draft, setDraft] = useState("");
  const [locationsVisited, setLocationsVisited] = useState(false);
  const [financeVisited, setFinanceVisited] = useState(false);
  const [bankVisited, setBankVisited] = useState(false);
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
  const [consentDialog, setConsentDialog] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [consentReady, setConsentReady] = useState(false);
  const [consentText, setConsentText] = useState<Schemas["ConsentText"] | null>(
    null,
  );
  const lock = useRef(false);
  const flow = { conversation, ranking, selected, finance: reportFinance };

  function navigate(next: Stage) {
    if (!canEnter(next, flow)) return;
    if (next === "location") setLocationsVisited(true);
    if (next === "finance") setFinanceVisited(true);
    if (next === "banking") setBankVisited(true);
    setNotice("");
    setStage(next);
  }
  function invalidate() {
    setRanking(null);
    setSelected(null);
    setReportFinance(null);
    setReportBank(null);
    setReportWalking(null);
    setReportProvider(null);
    setFinanceContext((n) => n + 1);
  }
  const focusedStage = useRef(stage);
  useEffect(() => {
    if (focusedStage.current === stage) return;
    focusedStage.current = stage;
    const main = document.getElementById("main-content");
    document.documentElement.scrollTop = 0;
    main?.focus({ preventScroll: true });
  }, [stage]);
  useEffect(() => {
    const c = new AbortController();
    request<Schemas["ConsentText"][]>("/api/v1/consent-texts", {
      signal: c.signal,
    })
      .then((texts) =>
        setConsentText(texts.find((t) => t.purpose === "assistant") || null),
      )
      .catch(() => {
        /* A missing consent text never implies permission. */
      });
    return () => c.abort();
  }, []);
  useEffect(() => {
    const key = readCredential();
    if (!key) return;
    const c = new AbortController();
    Promise.all([
      request<Conversation>(`/api/v1/conversations/${key.id}`, {
        credential: key,
        signal: c.signal,
      }),
      history(key, c.signal),
      request<Schemas["ConsentState"]>(
        `/api/v1/conversations/${key.id}/consents`,
        { credential: key, signal: c.signal },
      ),
    ])
      .then(([view, items, consents]) => {
        if (c.signal.aborted) return;
        setConversation(view);
        setMessages(items);
        setConsentReady(
          consents.consents.some(
            (s) => s.purpose === "assistant" && s.status === "granted",
          ),
        );
        const next = restoredStage(view);
        setStage(next);
        if (next === "location") {
          setLocationsVisited(true);
          setNotice(
            "Профиль восстановлен. Запустите поиск локаций — расчёты после перезагрузки нужно выполнить заново.",
          );
        }
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setError(errorText(e));
          setRestoreFailed(true);
          if (e instanceof ApiError && [401, 404].includes(e.status))
            setAccessLost(true);
        }
      })
      .finally(() => {
        if (!c.signal.aborted) setBusy(false);
      });
    return () => c.abort();
  }, []);
  const receiveFinance = useCallback(
    (value: Schemas["FinanceResult"] | null) => {
      setReportFinance(value);
      if (!value)
        setStage((current) =>
          current === "banking" || current === "summary" ? "finance" : current,
        );
    },
    [],
  );
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
    setRestoreFailed(false);
    invalidate();
    setStage("chat");
    setNotice(
      "Получены актуальные параметры. Проверьте их и повторите анализ.",
    );
  }
  async function create() {
    const created = await request<Schemas["ConversationCreated"]>(
      "/api/v1/conversations",
      { method: "POST" },
    );
    const key = { id: created.id, token: created.access_token };
    if (!saveCredential(key))
      setNotice(
        "Доступ сохранён только до закрытия страницы: браузер запретил хранение ключа.",
      );
    setCredential(key);
    setConversation(created);
    setMessages([]);
    invalidate();
    setAccessLost(false);
    setRestoreFailed(false);
    return { key, view: created };
  }
  async function ensureAssistant(key: Credential, explicitGrant = false) {
    const state = await request<Schemas["ConsentState"]>(
      `/api/v1/conversations/${key.id}/consents`,
      { credential: key },
    );
    const current = state.consents.find((c) => c.purpose === "assistant");
    if (
      current?.status === "granted" &&
      current.text_version === consentText?.version
    ) {
      setConsentReady(true);
      return;
    }
    if (!explicitGrant || !consentChecked || !consentText || !current)
      throw new ConsentRequired(
        "Нужно отдельное согласие на использование ассистента.",
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
    setConsentReady(true);
  }
  async function action(work: () => Promise<void>, propagate = false) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      if (e instanceof ConsentRequired) {
        setConsentReady(false);
        setConsentChecked(false);
        setConsentDialog(true);
      } else {
        if (
          e instanceof ApiError &&
          (e.code === "version_conflict" || e.code === "network")
        ) {
          try {
            await refresh();
          } catch {
            /* Keep the original failure. */
          }
        }
        if (
          e instanceof ApiError &&
          [401, 404].includes(e.status) &&
          e.code !== "consent_required"
        )
          setAccessLost(true);
        setError(errorText(e));
      }
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
    invalidate();
    setMessages(await history(key));
    return view;
  }
  async function sendIdea(content: string, explicitGrant = false) {
    if (accessLost) return;
    await action(async () => {
      const current =
        credential && conversation
          ? { key: credential, view: conversation }
          : await create();
      await ensureAssistant(current.key, explicitGrant);
      setConsentDialog(false);
      setStage("chat");
      setWaitingForReply(true);
      try {
        const view = await mutate(
          "/messages",
          "POST",
          { content, expected_version: current.view.version },
          current.key,
        );
        setDraft("");
        if (!view.missing_fields.length) setStage("review");
      } finally {
        setWaitingForReply(false);
      }
    }, true);
  }
  function beginIdea() {
    if (!consentReady) {
      setConsentDialog(true);
      return;
    }
    void sendIdea(draft).catch(() => {});
  }
  function patchProfile(patch: Schemas["ProfilePatch"]) {
    return action(async () => {
      if (!credential || !conversation) return;
      await ensureAssistant(credential);
      await mutate(
        "/profile",
        "PATCH",
        { patch, expected_version: conversation.version },
        credential,
      );
      setStage("review");
    }, true);
  }
  function confirmProfile() {
    void action(async () => {
      if (!credential || !conversation) return;
      await ensureAssistant(credential);
      const view =
        conversation.profile.confirmation_state === "confirmed"
          ? conversation
          : await mutate(
              "/profile/confirm",
              "POST",
              { expected_version: conversation.version },
              credential,
            );
      if (view.profile.confirmation_state === "confirmed") {
        setLocationsVisited(true);
        setStage("location");
      }
    });
  }
  function newConversation() {
    void action(async () => {
      await create();
      setConsentChecked(false);
      setConsentReady(false);
      setConsentDialog(false);
      setDraft("");
      setStage("idea");
      setNotice("");
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
  const previous: Stage | null =
    stage === "idea"
      ? null
      : stage === "chat"
        ? "idea"
        : stage === "review"
          ? "chat"
          : stage === "location"
            ? "review"
            : stage === "finance"
              ? "location"
              : stage === "banking"
                ? "finance"
                : "banking";
  return (
    <div className="flow-app">
      <a className="skip-link" href="#main-content">
        Перейти к содержимому
      </a>
      <header className="flow-header">
        <button
          className="wordmark"
          onClick={onHome}
          aria-label="Business AI · главная"
        >
          Business <span>AI</span>
        </button>
        {stage !== "idea" && (
          <span className="progress" aria-label="Прогресс">
            Шаг {stepFor[stage]} из 5
          </span>
        )}
        {stage !== "idea" && (
          <button
            className="text-button new-conversation"
            onClick={newConversation}
            disabled={busy}
          >
            Новый проект
          </button>
        )}
      </header>
      <main
        id="main-content"
        tabIndex={-1}
        className={`flow-main stage-${stage}`}
      >
        {previous && (
          <button
            className="back-button"
            onClick={() => navigate(previous)}
            disabled={busy}
          >
            ← Назад
          </button>
        )}
        {notice && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        {error && (
          <div className="alert vi-inline" role="alert">
            <ViAvatar emotion="error" />
            {error}
            <button className="text-button" onClick={() => setError("")}>
              Закрыть
            </button>
          </div>
        )}
        {accessLost || restoreFailed ? (
          <section className="empty">
            <h1>Не удалось открыть проект</h1>
            <p>
              Проверьте доступ к этой гостевой беседе или начните новый проект.
            </p>
            {!accessLost && (
              <button
                className="button"
                onClick={() => {
                  void action(refresh);
                }}
                disabled={busy}
              >
                Повторить загрузку
              </button>
            )}
            <button className="button" onClick={newConversation}>
              Начать новый проект
            </button>
          </section>
        ) : (
          <>
            {stage === "idea" && (
              <Idea
                draft={draft}
                onDraft={setDraft}
                onSend={beginIdea}
                busy={busy}
              />
            )}
            {stage === "chat" && (
              <Chat
                conversation={conversation}
                messages={messages}
                busy={busy}
                waitingForReply={waitingForReply}
                draft={draft}
                onDraft={setDraft}
                onSend={(text) => sendIdea(text)}
                onNew={newConversation}
                onRefresh={() => {
                  void action(refresh);
                }}
                onPatch={patchProfile}
                onReview={() => navigate("review")}
                consentControl={
                  <button
                    className="text-button"
                    onClick={() => setConsentDialog(true)}
                  >
                    Согласие на ассистента
                  </button>
                }
              />
            )}
            {stage === "review" && conversation && (
              <ProjectReview
                conversation={conversation}
                busy={busy}
                onPatch={patchProfile}
                onConfirm={confirmProfile}
                onChat={() => navigate("chat")}
              />
            )}
            {locationsVisited && (
              <div hidden={stage !== "location"}>
                <ModuleBoundary onBack={() => navigate("review")}>
                  <Suspense fallback={<p role="status">Загружаем карту…</p>}>
                    <Locations
                      key={`${conversation?.id}:${conversation?.version}`}
                      profile={conversation?.profile || null}
                      ranking={ranking}
                      onRanking={setRanking}
                      selected={selected}
                      onSelect={setSelected}
                      comparison={false}
                      onFinance={() => navigate("finance")}
                      onWalkingReport={setReportWalking}
                      onProviderReport={setReportProvider}
                    />
                  </Suspense>
                </ModuleBoundary>
                <div className="step-action">
                  <button
                    className="button"
                    disabled={!canEnter("finance", flow)}
                    onClick={() => navigate("finance")}
                  >
                    Продолжить к расчётам
                  </button>
                </div>
              </div>
            )}
            {financeVisited && (
              <div hidden={stage !== "finance"}>
                <Finance
                  key={`${financeContext}:${ranking?.request_fingerprint}:${selected}`}
                  profile={conversation?.profile || null}
                  zone={zone}
                  onReport={receiveFinance}
                />
                <div className="step-action">
                  <button
                    className="button"
                    disabled={!canEnter("banking", flow)}
                    onClick={() => navigate("banking")}
                  >
                    Продолжить
                  </button>
                </div>
              </div>
            )}
            {bankVisited && (
              <div hidden={stage !== "banking"}>
                <BankProducts
                  key={`${conversation?.id}:${conversation?.version}`}
                  active={stage === "banking"}
                  conversation={conversation}
                  credential={credential}
                  onReport={setReportBank}
                  onProfileConflict={() => {
                    void action(refresh);
                  }}
                />
                <div className="step-action">
                  <button
                    className={reportBank ? "button" : "text-button"}
                    disabled={!canEnter("summary", flow)}
                    onClick={() => navigate("summary")}
                  >
                    {reportBank ? "К результату" : "Продолжить без подбора"}
                  </button>
                </div>
              </div>
            )}
            {stage === "summary" && conversation && (
              <Summary
                conversation={conversation}
                ranking={ranking}
                selected={selected}
                finance={reportFinance}
                bank={reportBank}
                onEdit={() => navigate("review")}
              />
            )}
            {financeVisited && (
              <div hidden={stage !== "summary"}>
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
            )}
          </>
        )}
      </main>
      <footer className="flow-footer">
        Независимый хакатонный прототип. Не официальный сервис ВТБ.
      </footer>
      {active && consentDialog && (
        <ConsentDialog
          text={consentText}
          checked={consentChecked}
          onCheck={setConsentChecked}
          busy={busy}
          onClose={() => setConsentDialog(false)}
          onContinue={() => {
            void sendIdea(draft, true).catch(() => {});
          }}
        />
      )}
    </div>
  );
}
