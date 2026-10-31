import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  useCallback,
  useMemo,
} from "react";
import Chat from "./Chat";
import {
  IndustryReview,
  IndustryResult,
  type IndustryView,
  type IndustryEdit,
} from "./Industry";
import { ViAvatar } from "./Vi";
import {
  ConsentDialog,
  Idea,
  ModuleBoundary,
  ProjectReview,
  Summary,
} from "./FlowUI";
import Finance from "./Finance";
import FinancialScenarios from "./FinancialScenarios";
import AnalysisResult from "./AnalysisResult";
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
import {
  canEnter,
  industryStage,
  restoredStage,
  stepFor,
  type Stage,
} from "./flow";

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
  const [industryEnabled, setIndustryEnabled] = useState<boolean | null>(null);
  const [universal, setUniversal] = useState<IndustryView | null>(null);
  const [industries, setIndustries] = useState<Schemas["IndustryDefinition"][]>(
    [],
  );
  const [messages, setMessages] = useState<Schemas["MessageView"][]>([]);
  const [waitingForReply, setWaitingForReply] = useState(false);
  const [checkingData, setCheckingData] = useState(false);
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
  const flow = useMemo(
    () => ({
      conversation,
      ranking,
      selected,
      finance: reportFinance,
      universal,
    }),
    [conversation, ranking, selected, reportFinance, universal],
  );

  useEffect(() => {
    const controller = new AbortController();
    request<{ enabled: boolean; industries: Schemas["IndustryDefinition"][] }>(
      "/api/v2/industry-capabilities",
      { signal: controller.signal },
    )
      .then((c) => {
        setIndustryEnabled(c.enabled);
        setIndustries(c.industries || []);
      })
      .catch((e) => {
        if (!controller.signal.aborted) {
          if (e instanceof ApiError && e.status === 404)
            setIndustryEnabled(false);
          else {
            setError(errorText(e));
            setRestoreFailed(!!readCredential());
            setBusy(false);
          }
        }
      });
    return () => controller.abort();
  }, []);

  function acceptIndustry(view: IndustryView) {
    setUniversal(view);
    setConversation(view.conversation);
  }
  function enterIndustry(view: IndustryView) {
    const next = industryStage(view);
    if (next === "location") setLocationsVisited(true);
    if (next === "finance") setFinanceVisited(true);
    setStage(next);
  }

  function navigate(next: Stage) {
    if (!canEnter(next, flow)) return;
    if (next === "location") setLocationsVisited(true);
    if (next === "finance") setFinanceVisited(true);
    if (next === "banking") setBankVisited(true);
    setNotice("");
    window.history.pushState({ businessAI: credential?.id, stage: next }, "");
    setStage(next);
  }
  useEffect(() => {
    function back() {
      const preferred = window.history.state as {
        businessAI?: string;
        stage?: Stage;
      } | null;
      if (
        preferred?.businessAI === credential?.id &&
        preferred?.stage &&
        canEnter(preferred.stage, flow)
      ) {
        if (preferred.stage === "banking") setBankVisited(true);
        if (preferred.stage === "finance") setFinanceVisited(true);
        setStage(preferred.stage);
      }
    }
    window.addEventListener("popstate", back);
    return () => window.removeEventListener("popstate", back);
  }, [flow, credential]);
  function invalidate() {
    if (industryEnabled) {
      setLocationsVisited(false);
      setFinanceVisited(false);
      setBankVisited(false);
    }
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
    if (industryEnabled === null) return;
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
      .then(async ([view, items, consents]) => {
        const industry = industryEnabled
          ? await request<IndustryView>(
              `/api/v2/conversations/${key.id}/industry-profile`,
              { credential: key, signal: c.signal },
            )
          : null;
        if (c.signal.aborted) return;
        setConversation(view);
        setMessages(items);
        setConsentReady(
          consents.consents.some(
            (s) => s.purpose === "assistant" && s.status === "granted",
          ),
        );
        const next = industry ? industryStage(industry) : restoredStage(view);
        if (industry) {
          acceptIndustry(industry);
          enterIndustry(industry);
          const preferred = window.history.state as {
            businessAI?: string;
            stage?: Stage;
          } | null;
          if (
            preferred?.businessAI === industry.conversation.id &&
            preferred.stage &&
            canEnter(preferred.stage, {
              conversation: industry.conversation,
              universal: industry,
              ranking: null,
              selected: null,
              finance: null,
            })
          ) {
            if (preferred.stage === "banking") setBankVisited(true);
            if (preferred.stage === "finance") setFinanceVisited(true);
            setStage(preferred.stage);
          }
        } else setStage(next);
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
  }, [industryEnabled]);
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
    let enabled = industryEnabled;
    if (enabled === null) {
      const catalog = await request<Schemas["IndustryCatalog"]>(
        "/api/v2/industry-capabilities",
      );
      enabled = catalog.enabled;
      setIndustryEnabled(enabled);
      setIndustries(catalog.industries);
    }
    const [view, items] = await Promise.all([
      request<Conversation>(`/api/v1/conversations/${key.id}`, {
        credential: key,
      }),
      history(key),
    ]);
    setConversation(view);
    if (enabled)
      acceptIndustry(
        await request<IndustryView>(
          `/api/v2/conversations/${key.id}/industry-profile`,
          { credential: key },
        ),
      );
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
    setUniversal(null);
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
    if (industryEnabled && path === "/messages") {
      const view = await request<IndustryView>(
        `/api/v2/conversations/${key.id}/industry-profile/messages`,
        { method, body, credential: key },
      );
      acceptIndustry(view);
      invalidate();
      setMessages(await history(key));
      return { ...view.conversation, missing_fields: view.plan.missing_fields };
    }
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
      if (industryEnabled && !universal)
        acceptIndustry(
          await request<IndustryView>(
            `/api/v2/conversations/${current.key.id}/industry-profile`,
            { credential: current.key },
          ),
        );
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
      if (universal) {
        setCheckingData(true);
        let view: IndustryView;
        try {
          view = await request<IndustryView>(
            `/api/v2/conversations/${credential.id}/industry-profile/confirm`,
            {
              credential,
              method: "POST",
              body: { expected_version: conversation.version },
            },
          );
        } finally {
          setCheckingData(false);
        }
        acceptIndustry(view);
        invalidate();
        setMessages(await history(credential));
        enterIndustry(view);
        return;
      }
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
  function editIndustry(patch: Omit<IndustryEdit, "expected_version">) {
    return action(async () => {
      if (!credential || !conversation) return;
      const view = await request<IndustryView>(
        `/api/v2/conversations/${credential.id}/industry-profile`,
        {
          credential,
          method: "PATCH",
          body: { ...patch, expected_version: conversation.version },
        },
      );
      acceptIndustry(view);
      invalidate();
      setMessages(await history(credential));
      setStage("review");
    }, true);
  }
  function reviewCurrentProfile() {
    void action(async () => {
      if (!credential) return;
      const latest = await request<IndustryView>(
        `/api/v2/conversations/${credential.id}/industry-profile`,
        { credential },
      );
      acceptIndustry(latest);
      invalidate();
      setStage("review");
    });
  }
  function downloadInputs() {
    void action(async () => {
      if (!credential || !universal) return;
      const latest = await request<IndustryView>(
        `/api/v2/conversations/${credential.id}/industry-profile`,
        { credential },
      );
      acceptIndustry(latest);
      if (
        latest.profile.revision !== universal.profile.revision ||
        latest.profile.confirmed_revision !== latest.profile.revision
      ) {
        invalidate();
        enterIndustry(latest);
        return;
      }
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(latest, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "business-inputs.json";
      a.click();
      URL.revokeObjectURL(url);
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
              ? universal && !universal.plan.stages.includes("location")
                ? "review"
                : "location"
              : stage === "partial"
                ? "review"
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
        {stage !== "idea" && !universal && (
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
            {industryEnabled === null && (
              <button
                className="text-button"
                disabled={busy}
                onClick={() => {
                  void action(async () => {
                    const catalog = await request<Schemas["IndustryCatalog"]>(
                      "/api/v2/industry-capabilities",
                    );
                    setIndustryEnabled(catalog.enabled);
                    setIndustries(catalog.industries);
                  });
                }}
              >
                Повторить загрузку возможностей
              </button>
            )}
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
            {!accessLost && credential && !consentReady && (
              <button
                className="text-button"
                onClick={() => setConsentDialog(true)}
                disabled={busy}
              >
                Согласие на работу ассистента
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
                busy={busy || industryEnabled === null}
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
            {stage === "review" && universal && (
              <>
                {checkingData && (
                  <div className="vi-status" role="status">
                    <ViAvatar emotion="search" />
                    Проверяю вводные и доступность данных…
                  </div>
                )}
                <IndustryReview
                  key={universal.profile.revision}
                  view={universal}
                  industries={industries}
                  busy={busy}
                  onSave={editIndustry}
                  onConfirm={confirmProfile}
                  onChat={() => navigate("chat")}
                />
              </>
            )}
            {stage === "partial" &&
              universal &&
              (universal.profile.industry !== "coffee_shop" && credential ? (
                <AnalysisResult
                  credential={credential}
                  profileRevision={universal.profile.revision}
                  onEdit={reviewCurrentProfile}
                  onFinance={() => navigate("finance")}
                  onBank={() => navigate("banking")}
                />
              ) : (
                <IndustryResult
                  view={universal}
                  busy={busy}
                  onEdit={() => navigate("review")}
                  onDownload={downloadInputs}
                />
              ))}
            {stage === "review" && conversation && !universal && (
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
                {universal &&
                credential &&
                universal.plan.capabilities.some(
                  (c) =>
                    c.id === "finance.analysis" &&
                    c.method?.startsWith("financial_v2."),
                ) ? (
                  <FinancialScenarios
                    key={`${credential.id}:${conversation?.version}`}
                    credential={credential}
                    profileRevision={conversation!.version}
                    onEdit={reviewCurrentProfile}
                    onContinue={() => navigate("banking")}
                  />
                ) : (
                  <>
                    <Finance
                      key={`${financeContext}:${ranking?.request_fingerprint}:${selected}`}
                      profile={conversation?.profile || null}
                      zone={zone}
                      confirmedDrivers={universal?.coffee_inputs}
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
                  </>
                )}
              </div>
            )}
            {bankVisited && (
              <div hidden={stage !== "banking"}>
                <BankProducts
                  key={`${conversation?.id}:${conversation?.version}`}
                  active={stage === "banking"}
                  conversation={conversation}
                  credential={credential}
                  universal={
                    !!universal && universal.profile.industry !== "coffee_shop"
                  }
                  onReport={setReportBank}
                  onProfileConflict={() => {
                    void action(refresh);
                  }}
                />
                <div className="step-action">
                  <button
                    className={reportBank ? "button" : "text-button"}
                    disabled={
                      !canEnter(
                        universal?.plan.stages.includes("banking")
                          ? "partial"
                          : "summary",
                        flow,
                      )
                    }
                    onClick={() =>
                      navigate(
                        universal?.plan.stages.includes("banking")
                          ? "partial"
                          : "summary",
                      )
                    }
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
            {financeVisited && !universal?.plan.stages.includes("banking") && (
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
        Business AI — независимый проект. Не официальный сервис ВТБ.
      </footer>
      {active && consentDialog && (
        <ConsentDialog
          text={consentText}
          checked={consentChecked}
          onCheck={setConsentChecked}
          busy={busy}
          onClose={() => setConsentDialog(false)}
          onContinue={() => {
            if (restoreFailed && credential) {
              void action(async () => {
                await ensureAssistant(credential, true);
                setConsentDialog(false);
                await refresh(credential);
              });
              return;
            }
            void sendIdea(draft, true).catch(() => {});
          }}
        />
      )}
    </div>
  );
}
