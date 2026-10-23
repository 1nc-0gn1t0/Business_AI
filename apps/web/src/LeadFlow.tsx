import { useEffect, useRef, useState } from "react";
import { ApiError, errorText, request, rub } from "./api";
import type { Conversation, Credential, Schemas } from "./api";

type Fields = Schemas["LeadFields-Input"];
const purposeNames = {
  assistant: "Использование ассистента",
  marketing: "Маркетинговые рекомендации",
  demo_lead: "Подготовка и демонстрационная передача",
};
const fieldNames: Record<keyof Fields, string> = {
  city: "Город заявки",
  category: "Бизнес заявки",
  budget: "Бюджет заявки",
  funding: "Средства заявки",
  format: "Формат заявки",
};
const statusNames = {
  not_given: "Не предоставлено",
  granted: "Предоставлено",
  declined: "Отказ",
  withdrawn: "Отозвано",
};
function initialFields(conversation: Conversation): Fields {
  return {
    city: conversation.profile.city || "",
    category: conversation.profile.category || "",
    budget: conversation.profile.budget,
    funding: conversation.profile.funding,
    format: conversation.profile.preferences?.format,
  };
}

export default function LeadFlow({
  conversation,
  credential,
  catalogue,
  active,
}: {
  conversation: Conversation;
  credential: Credential;
  catalogue: Schemas["CatalogueView"];
  active: boolean;
}) {
  const base = `/api/v1/conversations/${credential.id}`;
  const [consents, setConsents] = useState<Schemas["ConsentState"] | null>(
    null,
  );
  const [draft, setDraft] = useState<Schemas["LeadDraft"] | null>(null);
  const [receipts, setReceipts] = useState<Schemas["LeadReceipt"][]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [fields, setFields] = useState<Fields>(() =>
    initialFields(conversation),
  );
  const [dirty, setDirty] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const submitting = useRef(false);
  const replayKey = useRef<string | null>(null);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (!active) return;
    const c = new AbortController();
    Promise.all([
      request<Schemas["ConsentState"]>(base + "/consents", {
        credential,
        signal: c.signal,
      }),
      request<Schemas["LeadWorkspace"]>(base + "/leads", {
        credential,
        signal: c.signal,
      }),
    ])
      .then(([state, workspace]) => {
        setConsents(state);
        setReceipts(workspace.receipts);
        const latest = [...workspace.drafts].sort((a, b) =>
          b.updated_at.localeCompare(a.updated_at),
        )[0];
        setDraft(latest || null);
        if (latest) {
          setFields(latest.payload.fields);
          setSelected(latest.payload.products.map((p) => p.product.id));
        }
        setDirty(false);
        setReviewed(false);
        setConfirmed(false);
        setLoaded(true);
        setError("");
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setError(errorText(e));
          setLoaded(false);
        }
      });
    return () => c.abort();
  }, [active, base, credential, reload]);
  async function work(callback: () => Promise<void>) {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await callback();
    } catch (e) {
      setError(errorText(e));
      if (e instanceof ApiError && e.status === 409) {
        setReviewed(false);
        setConfirmed(false);
      }
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  function changed() {
    setDirty(true);
    setReviewed(false);
    setConfirmed(false);
    replayKey.current = null;
  }
  async function consent(
    purpose: Schemas["ConsentText"]["purpose"],
    decision: "grant" | "decline" | "withdraw",
  ) {
    if (!consents) return;
    const current = consents.consents.find((c) => c.purpose === purpose)!;
    const text = consents.texts.find((t) => t.purpose === purpose)!;
    setConsents(
      await request<Schemas["ConsentState"]>(base + "/consents/" + purpose, {
        credential,
        method: "PUT",
        body: {
          expected_revision: current.revision,
          text_version: text.version,
          decision,
        },
      }),
    );
    setReviewed(false);
    setConfirmed(false);
  }
  const activeConsent = (purpose: string) =>
    consents?.consents.some(
      (c) =>
        c.purpose === purpose &&
        c.status === "granted" &&
        c.text_version ===
          consents.texts.find((t) => t.purpose === purpose)?.version,
    );
  const allowed = activeConsent("assistant") && activeConsent("demo_lead");
  const currentReceipt = draft && receipts.find((r) => r.draft_id === draft.id);
  const immutable = draft?.state === "submitted";
  const stale =
    draft?.stale || (draft && draft.profile_version !== conversation.version);
  const action = draft && {
    expected_revision: draft.revision,
    confirmed: true,
    payload_fingerprint: draft.payload_fingerprint,
  };
  return (
    <section className="lead-flow" aria-label="Демонстрационная заявка">
      <div className="section-heading">
        <div>
          <span className="eyebrow">CONSENT · LOCAL MOCK</span>
          <h2>Последний шаг — только демонстрация</h2>
          <p>
            Выберите продукты и проверьте состав заявки. Никакие данные не
            покидают наш сервис и не передаются в ВТБ.
          </p>
        </div>
        <span className="tag amber">Без банковской интеграции</span>
      </div>
      {error && (
        <div role="alert" className="alert">
          {error}{" "}
          <button
            className="text-button"
            onClick={() => setReload((n) => n + 1)}
            disabled={busy}
          >
            Обновить согласия и заявки
          </button>
        </div>
      )}
      {!loaded && !error && (
        <p role="status">Загружаем согласия и историю заявок…</p>
      )}
      {loaded && (
        <>
          <div className="lead-steps">
            <span>01 · Продукты</span>
            <span>02 · Состав данных</span>
            <span>03 · Согласия</span>
            <span>04 · Квитанция</span>
          </div>
          <div className="lead-columns">
            <div className="lead-card">
              <h3>1. Интересующие продукты</h3>
              <p className="subtle">
                Это ваш выбор для демо, а не банковское одобрение. Условия
                каталога остаются неподтверждёнными.
              </p>
              {catalogue.products.map((p) => (
                <label className="check-line" key={p.product.id}>
                  <input
                    type="checkbox"
                    disabled={busy || immutable || p.availability === "blocked"}
                    checked={selected.includes(p.product.id)}
                    onChange={(e) => {
                      setSelected(
                        e.target.checked
                          ? [...selected, p.product.id]
                          : selected.filter((id) => id !== p.product.id),
                      );
                      changed();
                    }}
                  />
                  <span>
                    {p.product.name}
                    <small>
                      {p.availability === "blocked"
                        ? "Недоступен"
                        : p.availability === "demonstration_only"
                          ? "Демо-карточка"
                          : "Справочная информация"}
                    </small>
                  </span>
                </label>
              ))}
            </div>
            <div className="lead-card">
              <h3>2. Данные заявки</h3>
              <p className="subtle">
                Источник — подтверждённый профиль v{conversation.version}.
                Изменения здесь относятся только к заявке и будут отмечены
                отдельно. Бюджет, средства и формат можно исключить.
              </p>
              {(Object.keys(fieldNames) as (keyof Fields)[]).map((key) => (
                <label className="lead-field" key={key}>
                  {fieldNames[key]}
                  {key === "funding" ? (
                    <select
                      value={fields.funding || ""}
                      disabled={busy || immutable}
                      onChange={(e) => {
                        setFields({
                          ...fields,
                          funding: (e.target.value ||
                            null) as Fields["funding"],
                        });
                        changed();
                      }}
                    >
                      <option value="">Не включать</option>
                      <option value="own_funds">Свои средства</option>
                      <option value="loan">Кредит</option>
                      <option value="mixed">Смешанные</option>
                      <option value="undecided">Не определено</option>
                    </select>
                  ) : (
                    <input
                      value={fields[key] == null ? "" : String(fields[key])}
                      maxLength={key === "budget" ? 18 : 100}
                      inputMode={key === "budget" ? "decimal" : "text"}
                      disabled={busy || immutable}
                      placeholder={
                        key === "city" || key === "category"
                          ? "Обязательно"
                          : "Не включать"
                      }
                      onChange={(e) => {
                        setFields({
                          ...fields,
                          [key]:
                            e.target.value ||
                            (key === "city" || key === "category" ? "" : null),
                        });
                        changed();
                      }}
                    />
                  )}
                </label>
              ))}
              <p className="subtle">
                Паспорт, контакты, переписка, георейтинг и финансовые допущения
                в заявку не включаются.
              </p>
              {stale && (
                <div className="alert">
                  Профиль изменился. Подтвердите его в чате, затем явно обновите
                  черновик.
                </div>
              )}
              <button
                className="button secondary"
                disabled={busy || immutable}
                onClick={() => {
                  setFields(initialFields(conversation));
                  changed();
                }}
              >
                Взять текущие поля профиля
              </button>
            </div>
          </div>
          <div className="lead-card">
            <h3>3. Отдельные цели согласия</h3>
            <p className="subtle">
              Демонстрационные тексты Business AI не утверждены ВТБ. Перед
              пилотом необходима правовая проверка. Отказ от маркетинга не
              блокирует карту, финансы или подбор по вашему запросу.
            </p>
            {consents?.texts.map((text) => {
              const c = consents.consents.find(
                (s) => s.purpose === text.purpose,
              )!;
              return (
                <div className="consent-row" key={text.purpose}>
                  <div>
                    <strong>{purposeNames[text.purpose]}</strong>
                    <span
                      className={`tag ${c.status === "granted" ? "mint" : ""}`}
                    >
                      {statusNames[c.status]}
                    </span>
                    <details>
                      <summary>
                        Текст {text.version} · получатель и даты
                      </summary>
                      <p>{text.text}</p>
                      <p>{text.recipient}</p>
                      <p>
                        Предоставлено:{" "}
                        {c.given_at
                          ? new Date(c.given_at).toLocaleString("ru-RU")
                          : "—"}
                        ; отозвано:{" "}
                        {c.withdrawn_at
                          ? new Date(c.withdrawn_at).toLocaleString("ru-RU")
                          : "—"}
                        . Решение v{c.revision}.
                      </p>
                    </details>
                  </div>
                  <div className="button-row">
                    {c.status === "granted" ? (
                      <button
                        className="button secondary"
                        disabled={busy}
                        onClick={() =>
                          void work(() => consent(text.purpose, "withdraw"))
                        }
                      >
                        Отозвать: {purposeNames[text.purpose]}
                      </button>
                    ) : (
                      <>
                        <button
                          className="button secondary"
                          disabled={busy}
                          onClick={() =>
                            void work(() => consent(text.purpose, "grant"))
                          }
                        >
                          Согласиться: {purposeNames[text.purpose]}
                        </button>
                        <button
                          className="text-button"
                          disabled={busy || c.status === "declined"}
                          onClick={() =>
                            void work(() => consent(text.purpose, "decline"))
                          }
                        >
                          Отказаться: {purposeNames[text.purpose]}
                        </button>
                      </>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {!immutable && (
            <button
              className="button"
              disabled={
                busy ||
                !allowed ||
                selected.length === 0 ||
                conversation.profile.confirmation_state !== "confirmed"
              }
              onClick={() =>
                void work(async () => {
                  const next = await request<Schemas["LeadDraft"]>(
                    base + "/leads/drafts" + (draft ? "/" + draft.id : ""),
                    {
                      credential,
                      method: draft ? "PUT" : "POST",
                      body: {
                        expected_profile_version: conversation.version,
                        catalogue_fingerprint: catalogue.fingerprint,
                        product_ids: selected,
                        fields,
                        ...(draft ? { expected_revision: draft.revision } : {}),
                      },
                    },
                  );
                  setDraft(next);
                  setDirty(false);
                  setReviewed(false);
                  setConfirmed(false);
                  replayKey.current = null;
                })
              }
            >
              {draft
                ? "Сохранить новую версию черновика"
                : "Подготовить демо-черновик →"}
            </button>
          )}
          {!allowed && (
            <p className="subtle">
              Для подготовки нужны отдельные действующие согласия на сервис и
              демо-заявку.
            </p>
          )}
          {draft && (
            <div className="lead-card preview" aria-label="Предпросмотр заявки">
              <div className="row">
                <h3>Полный состав демо-заявки</h3>
                <span className="tag">
                  v{draft.revision} · {draft.state}
                </span>
              </div>
              <p>
                Город: {draft.payload.fields.city} ·{" "}
                {draft.payload.fields.category} · бюджет:{" "}
                {rub(draft.payload.fields.budget)}
              </p>
              <p className="subtle">
                Профиль v{draft.profile_version}. Получатель: локальный mock.
                ВТБ ничего не получает. Ниже — точный payload с продуктами,
                источниками и происхождением полей.
              </p>
              <details>
                <summary>Все передаваемые поля и источники (JSON)</summary>
                <pre>{JSON.stringify(draft.payload, null, 2)}</pre>
              </details>
              <small>Контрольная сумма: {draft.payload_fingerprint}</small>
              {dirty && (
                <p className="alert">
                  Есть несохранённые изменения. Сначала сохраните новую версию.
                </p>
              )}
              {!immutable && (
                <>
                  <label className="check-line">
                    <input
                      type="checkbox"
                      checked={reviewed}
                      disabled={busy || dirty || !!stale}
                      onChange={(e) => setReviewed(e.target.checked)}
                    />
                    Я проверил все поля и выбранные продукты
                  </label>
                  <button
                    className="button secondary"
                    disabled={
                      busy ||
                      !allowed ||
                      !reviewed ||
                      dirty ||
                      !!stale ||
                      draft.state === "confirmed"
                    }
                    onClick={() =>
                      void work(async () => {
                        setDraft(
                          await request<Schemas["LeadDraft"]>(
                            base + `/leads/drafts/${draft.id}/confirm`,
                            { credential, method: "POST", body: action },
                          ),
                        );
                      })
                    }
                  >
                    Подтвердить состав заявки
                  </button>
                  <label className="check-line">
                    <input
                      type="checkbox"
                      checked={confirmed}
                      disabled={
                        busy || dirty || !!stale || draft.state !== "confirmed"
                      }
                      onChange={(e) => setConfirmed(e.target.checked)}
                    />
                    Подтверждаю создание демонстрационной заявки без отправки в
                    банк
                  </label>
                  <button
                    className="button"
                    disabled={
                      busy ||
                      !allowed ||
                      !confirmed ||
                      dirty ||
                      !!stale ||
                      draft.state !== "confirmed"
                    }
                    onClick={() =>
                      void work(async () => {
                        replayKey.current ||= crypto.randomUUID();
                        const receipt = await request<Schemas["LeadReceipt"]>(
                          base + `/leads/drafts/${draft.id}/submit`,
                          {
                            credential,
                            method: "POST",
                            body: {
                              ...action,
                              idempotency_key: replayKey.current,
                            },
                          },
                        );
                        setReceipts((old) => [
                          ...old.filter((r) => r.id !== receipt.id),
                          receipt,
                        ]);
                        setDraft({ ...draft, state: "submitted" });
                      })
                    }
                  >
                    Создать демонстрационную заявку →
                  </button>
                </>
              )}
            </div>
          )}
          {currentReceipt && (
            <div
              className="lead-receipt"
              role="status"
              aria-label="Демо-квитанция"
            >
              <span className="eyebrow">LOCAL DEMO RECEIPT</span>
              <h2>{currentReceipt.message}</h2>
              <p>Локальная квитанция {currentReceipt.id}</p>
              <p>
                {new Date(currentReceipt.created_at).toLocaleString("ru-RU")} ·
                профиль v{currentReceipt.profile_version}
              </p>
              <p>
                Это внутренний идентификатор Business AI. Банковского номера,
                рассмотрения и решения нет.
              </p>
              <details>
                <summary>Квитанция, версии согласий и состав заявки</summary>
                <pre>{JSON.stringify(currentReceipt, null, 2)}</pre>
              </details>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() => {
                  setDraft(null);
                  setSelected([]);
                  setFields(initialFields(conversation));
                  setReviewed(false);
                  setConfirmed(false);
                  replayKey.current = null;
                }}
              >
                Начать новый демо-черновик
              </button>
            </div>
          )}
          {receipts.length > 0 && (
            <details className="provenance">
              <summary>История локальных квитанций · {receipts.length}</summary>
              {receipts.map((r) => (
                <p key={r.id}>
                  {r.message} · {new Date(r.created_at).toLocaleString("ru-RU")}{" "}
                  · {r.id}
                </p>
              ))}
            </details>
          )}
        </>
      )}
    </section>
  );
}
