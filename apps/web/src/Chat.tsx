import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Conversation, Schemas } from "./api";

export type ChatProps = {
  conversation: Conversation | null;
  messages: Schemas["MessageView"][];
  busy: boolean;
  onNew: () => void;
  onRefresh: () => void;
  onSend: (content: string) => Promise<void>;
  onPatch: (patch: Schemas["ProfilePatch"]) => Promise<void>;
  onConfirm?: () => void;
  onReview?: () => void;
  consentControl?: ReactNode;
  draft?: string;
  onDraft?: (value: string) => void;
};
export function ProfileEditor({
  conversation,
  busy,
  onPatch,
}: Pick<ChatProps, "busy" | "onPatch"> & { conversation: Conversation }) {
  const p = conversation.profile;
  const [editing, setEditing] = useState(false);
  return (
    <section className="profile-box">
      <button
        className="text-button"
        onClick={() => setEditing(!editing)}
        disabled={busy}
      >
        {editing ? "Скрыть редактор" : "Изменить"}
      </button>
      {editing && (
        <form
          className="profile-form"
          onSubmit={async (event) => {
            event.preventDefault();
            const form = new FormData(event.currentTarget);
            const text = (key: string) => String(form.get(key) || "").trim();
            await onPatch({
              city: text("city") || null,
              category: text("category") || null,
              budget: text("budget") || null,
              funding: (text("funding") ||
                null) as Schemas["ProfilePatch"]["funding"],
              preferences: {
                format: text("format") || null,
                preferred_districts: text("districts")
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean),
                constraints: text("constraints")
                  .split("\n")
                  .map((s) => s.trim())
                  .filter(Boolean),
              },
            });
          }}
        >
          <label>
            Город
            <input name="city" defaultValue={p.city || ""} maxLength={200} />
          </label>
          <label>
            Тип бизнеса
            <input
              name="category"
              defaultValue={p.category || ""}
              maxLength={200}
            />
          </label>
          <label>
            Бюджет, ₽
            <input
              name="budget"
              type="number"
              min="0"
              step="0.01"
              defaultValue={p.budget || ""}
            />
          </label>
          <label>
            Формат
            <input
              name="format"
              defaultValue={p.preferences?.format || ""}
              placeholder="Кофейня с посадочными местами"
              maxLength={200}
            />
          </label>
          <label>
            Источник средств
            <select name="funding" defaultValue={p.funding || ""}>
              <option value="">Выберите</option>
              <option value="own_funds">Собственные средства</option>
              <option value="loan">Кредит</option>
              <option value="mixed">Смешанное финансирование</option>
              <option value="undecided">Пока не определён</option>
            </select>
          </label>
          <label>
            Районы через запятую
            <input
              name="districts"
              defaultValue={p.preferences?.preferred_districts?.join(", ")}
            />
          </label>
          <label>
            Ограничения, по одному в строке
            <textarea
              name="constraints"
              defaultValue={p.preferences?.constraints?.join("\n")}
            />
          </label>
          <button className="button secondary" disabled={busy}>
            Сохранить профиль
          </button>
          <small>Изменение снимает подтверждение и сбрасывает анализ.</small>
        </form>
      )}
    </section>
  );
}

export default function Chat(props: ChatProps) {
  const scroll = useRef<HTMLDivElement>(null);
  const [localText, setLocalText] = useState("");
  const text = props.draft ?? localText;
  const setText = props.onDraft ?? setLocalText;
  useEffect(() => {
    if (scroll.current) scroll.current.scrollTop = scroll.current.scrollHeight;
  }, [props.messages, props.busy]);
  return (
    <section className="chat-screen" aria-label="AI-помощник">
      <h1 className="sr-only">Ваша бизнес-идея</h1>
      <div className="chat-scroll" ref={scroll}>
        <div
          className="messages"
          role="log"
          aria-label="История диалога"
          aria-live="polite"
        >
          {props.messages.map((m) => (
            <div key={m.id} className={`message ${m.role}`}>
              <span className="sr-only">
                {m.role === "user" ? "Вы" : "Business AI"}
              </span>
              <p>{m.content}</p>
            </div>
          ))}
        </div>
        {props.busy && (
          <p className="thinking" role="status">
            <span aria-hidden="true">●</span> Обдумываю…
          </p>
        )}
        {props.conversation && (
          <button
            className="text-button review-link"
            disabled={props.busy}
            onClick={props.onReview}
          >
            Проверить параметры проекта
          </button>
        )}
      </div>
      <form
        className="composer"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!text.trim() || props.busy) return;
          try {
            await props.onSend(text);
            setText("");
          } catch {
            /* Keep unsent text. */
          }
        }}
      >
        <label className="sr-only" htmlFor="message">
          Сообщение помощнику
        </label>
        <textarea
          id="message"
          placeholder="Напишите ответ…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={4000}
          rows={2}
          disabled={props.busy}
        />
        <button
          className="send-button"
          aria-label="Отправить сообщение"
          disabled={props.busy || !text.trim()}
        >
          ↑
        </button>
      </form>
      <div className="chat-meta">
        {props.conversation?.extraction_mode &&
          props.conversation.extraction_mode !== "ollama" && (
            <span className="test-mode">
              Тестовый режим {props.conversation.extraction_mode} · не Qwen
            </span>
          )}
        <details>
          <summary>О диалоге</summary>
          <p>
            Локальная Qwen через Ollama, если включён режим модели. Не сообщайте
            личные и банковские данные. Доступ к беседе сохраняется в этой
            вкладке.
          </p>
          <button
            className="text-button"
            onClick={props.onRefresh}
            disabled={props.busy}
          >
            Обновить беседу
          </button>
          {props.consentControl}
        </details>
      </div>
    </section>
  );
}
