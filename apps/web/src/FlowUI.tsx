import { Component, useEffect, useRef, type ReactNode } from "react";
import type { Conversation, Ranking, Schemas } from "./api";
import { rub } from "./api";
import { ProfileEditor } from "./Chat";
import { ViAvatar } from "./Vi";

export function Idea({
  draft,
  onDraft,
  onSend,
  busy,
}: {
  draft: string;
  onDraft: (value: string) => void;
  onSend: () => void;
  busy: boolean;
}) {
  return (
    <section className="idea-screen">
      <div className="vi-intro">
        <ViAvatar emotion="greeting" size={64} />
      </div>
      <h1>
        Какой бизнес <br />
        вы хотите открыть?
      </h1>
      <form
        className="idea-composer"
        onSubmit={(e) => {
          e.preventDefault();
          if (draft.trim() && !busy) onSend();
        }}
      >
        <label className="sr-only" htmlFor="idea">
          Сообщение помощнику
        </label>
        <textarea
          id="idea"
          placeholder="Например, хочу открыть кофейню в Казани…"
          value={draft}
          maxLength={4000}
          rows={2}
          onChange={(e) => onDraft(e.target.value)}
          disabled={busy}
        />
        <button
          className="button"
          aria-label="Отправить сообщение"
          disabled={busy || !draft.trim()}
        >
          {busy ? "Подождите…" : "Начать"}
          <span aria-hidden="true">↗</span>
        </button>
      </form>
    </section>
  );
}

export function ConsentDialog({
  text,
  checked,
  onCheck,
  onContinue,
  onClose,
  busy,
}: {
  text: Schemas["ConsentText"] | null;
  checked: boolean;
  onCheck: (v: boolean) => void;
  onContinue: () => void;
  onClose: () => void;
  busy: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="consent-dialog"
      aria-labelledby="consent-title"
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onClose();
      }}
    >
      <h2 id="consent-title">Перед началом</h2>
      <p>{text?.text || "Загружаем текст согласия…"}</p>
      <label className="check-line">
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onCheck(e.target.checked)}
          disabled={busy || !text}
        />
        Согласен на использование ассистента
      </label>
      <p className="fine-print">
        Демонстрационный текст Business AI, не юридический документ ВТБ.
        Маркетинг и демо-заявка — отдельный выбор.
      </p>
      <div className="actions">
        <button
          className="button"
          onClick={onContinue}
          disabled={!text || !checked || busy}
        >
          Продолжить
        </button>
        <button className="text-button" disabled={busy} onClick={onClose}>
          Назад
        </button>
      </div>
    </dialog>
  );
}

export function ProjectReview({
  conversation,
  busy,
  onPatch,
  onConfirm,
  onChat,
}: {
  conversation: Conversation;
  busy: boolean;
  onPatch: (patch: Schemas["ProfilePatch"]) => Promise<void>;
  onConfirm: () => void;
  onChat: () => void;
}) {
  return (
    <section className="review-screen">
      <span className="kicker">ВАШ ПРОЕКТ</span>
      <h1>Всё верно?</h1>
      <div className="project-title">
        <h2>{conversation.profile.category || "Бизнес уточняется"}</h2>
        <p>
          {conversation.profile.city || "Город не указан"} <span>·</span>{" "}
          {rub(conversation.profile.budget)}
        </p>
      </div>
      <p className="profile-status">
        {conversation.profile.confirmation_state === "confirmed"
          ? "Подтверждён"
          : "Черновик"}
      </p>
      <ProfileEditor
        key={`${conversation.id}:${conversation.version}`}
        conversation={conversation}
        busy={busy}
        onPatch={onPatch}
      />
      {conversation.missing_fields.length > 0 && (
        <p className="notice">
          Нужно уточнить ещё несколько параметров. Можно изменить их здесь или
          продолжить диалог.
        </p>
      )}
      <div className="actions">
        <button
          className="button"
          disabled={busy || conversation.missing_fields.length > 0}
          onClick={onConfirm}
        >
          Продолжить
        </button>
        <button className="text-button" onClick={onChat}>
          Вернуться в диалог
        </button>
      </div>
    </section>
  );
}

export function Summary({
  conversation,
  ranking,
  selected,
  finance,
  bank,
  onEdit,
}: {
  conversation: Conversation;
  ranking: Ranking | null;
  selected: string | null;
  finance: Schemas["FinanceResult"] | null;
  bank: Schemas["MatchResult"] | null;
  onEdit: () => void;
}) {
  const zone = ranking?.candidates.features.find((f) => f.id === selected);
  const base = finance?.scenarios.find((s) => s.name === "base");
  return (
    <section className="summary-screen">
      <span className="kicker">ОТ ИДЕИ К РЕШЕНИЮ</span>
      <h1>Ваш бизнес-план готов</h1>
      <p className="summary-intro">
        {conversation.profile.category} · {conversation.profile.city} · бюджет{" "}
        {rub(conversation.profile.budget)}
      </p>
      <dl className="summary-list">
        <div>
          <dt>Локация</dt>
          <dd>
            {zone?.properties.anchor.properties.name ||
              (zone ? "Выбранная зона-кандидат" : "Не выбрана")}
          </dd>
        </div>
        <div>
          <dt>Стартовые вложения по модели</dt>
          <dd>{rub(finance?.startup.total_initial_funding)}</dd>
        </div>
        <div>
          <dt>Операционный результат · базовый сценарий</dt>
          <dd>{rub(base?.metrics.operating_result.value)} / мес.</dd>
        </div>
        <div>
          <dt>Банковские возможности</dt>
          <dd>
            {bank
              ? "Подбор по вашим потребностям"
              : "Не включены — по вашему выбору"}
          </dd>
        </div>
      </dl>
      <p className="fine-print">
        Аналитический план, не гарантия результата. Локация — зона, не свободное
        помещение. Финансы основаны на синтетических допущениях; операционный
        результат до неучтённых налогов и платежей. Продукты банка —
        демонстрационные.
      </p>
      <button className="text-button" onClick={onEdit}>
        Вернуться к проекту
      </button>
    </section>
  );
}

export class ModuleBoundary extends Component<
  { children: ReactNode; onBack: () => void },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="alert" role="alert">
        Не удалось загрузить этот шаг. Проверьте подключение.
        <div className="actions">
          <button className="text-button" onClick={this.props.onBack}>
            Назад к профилю
          </button>
          <button
            className="text-button"
            onClick={() => window.location.reload()}
          >
            Обновить страницу
          </button>
        </div>
      </div>
    ) : (
      this.props.children
    );
  }
}
