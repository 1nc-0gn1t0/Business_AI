import { useState } from "react";
import type { Conversation, Schemas } from "./api";
import { rub } from "./api";

export type ChatProps = {
  conversation: Conversation | null;
  messages: Schemas["MessageView"][];
  busy: boolean;
  onNew: () => void;
  onRefresh: () => void;
  onSend: (content: string) => Promise<void>;
  onPatch: (patch: Schemas["ProfilePatch"]) => Promise<void>;
  onConfirm: () => void;
};
const fields: Record<string, string> = {
  city: "город",
  category: "тип бизнеса",
  budget: "бюджет",
  format: "формат",
  "preferences.format": "формат",
  funding: "источник средств",
};
function ProfileEditor({
  conversation,
  busy,
  onPatch,
}: Pick<ChatProps, "busy" | "onPatch"> & { conversation: Conversation }) {
  const p = conversation.profile;
  const [editing, setEditing] = useState(false);
  return (
    <section className="profile-box">
      <div className="row">
        <h3>Профиль бизнеса</h3>
        <span
          className={`tag ${p.confirmation_state === "confirmed" ? "mint" : ""}`}
        >
          {p.confirmation_state === "confirmed" ? "Подтверждён" : "Черновик"}
        </span>
      </div>
      <dl className="profile-summary">
        <div>
          <dt>Направление</dt>
          <dd>{p.category || "Не указано"}</dd>
        </div>
        <div>
          <dt>Город</dt>
          <dd>{p.city || "Не указан"}</dd>
        </div>
        <div>
          <dt>Бюджет</dt>
          <dd>{rub(p.budget)}</dd>
        </div>
        <div>
          <dt>Формат</dt>
          <dd>{p.preferences?.format || "Уточняется"}</dd>
        </div>
      </dl>
      <button
        className="text-button"
        onClick={() => setEditing(!editing)}
        disabled={busy}
      >
        {editing ? "Скрыть редактор" : "Редактировать профиль ↗"}
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
  const { conversation: c, messages, busy } = props;
  const [text, setText] = useState("");
  return (
    <aside className="chat-panel" aria-label="AI-помощник">
      <div className="chat-heading">
        <div>
          <span className="eyebrow">BUSINESS ASSISTANT</span>
          <h2>
            <span className="spark">✦</span> От идеи к решению
          </h2>
        </div>
        <button
          className="icon-button"
          title="Новая беседа"
          aria-label="Новая беседа"
          onClick={props.onNew}
          disabled={busy}
        >
          ＋
        </button>
      </div>
      <div className="chat-scroll">
        <div className="assistant-intro">
          <span className="assistant-avatar">✦</span>
          <p>
            Расскажите о вашей идее.
            <br />
            <span>Разберём профиль, географию и экономику — шаг за шагом.</span>
          </p>
        </div>
        {!c && (
          <button
            className="prompt-card"
            disabled={busy}
            onClick={() =>
              setText(
                "Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей",
              )
            }
          >
            Открыть кофейню в Казани <span>↗</span>
            <small>Начать с бизнес-идеи</small>
          </button>
        )}
        <div
          className="messages"
          role="log"
          aria-label="История диалога"
          aria-live="polite"
        >
          {messages.map((m) => (
            <div key={m.id} className={`message ${m.role}`}>
              <span className="message-author">
                {m.role === "user" ? "Вы" : "Business AI"}
              </span>
              <p>{m.content}</p>
            </div>
          ))}
        </div>
        {busy && (
          <div className="loading" role="status">
            Обрабатываем запрос…
          </div>
        )}
        {c && (
          <>
            <div className="row subtle">
              <span>
                {c.extraction_mode === "ollama"
                  ? "Локальная Qwen · Ollama"
                  : `Режим ${c.extraction_mode} · не LLM`}
              </span>
              <button
                className="text-button"
                disabled={busy}
                onClick={props.onRefresh}
              >
                Обновить
              </button>
            </div>
            <ProfileEditor
              key={`${c.id}:${c.version}`}
              conversation={c}
              busy={busy}
              onPatch={props.onPatch}
            />
            {c.profile.confirmation_state !== "confirmed" && (
              <>
                <p className="subtle">
                  {c.missing_fields.length
                    ? `Нужно уточнить: ${c.missing_fields.map((f) => fields[f] || f).join(", ")}.`
                    : "Проверьте параметры и подтвердите профиль для геоанализа."}
                </p>
                <button
                  className="button full"
                  disabled={busy || c.missing_fields.length > 0}
                  onClick={props.onConfirm}
                >
                  Подтвердить профиль →
                </button>
              </>
            )}
          </>
        )}
      </div>
      <form
        className="composer"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!text.trim()) return;
          const sent = text;
          try {
            await props.onSend(sent);
            setText("");
          } catch {
            /* Keep draft when delivery fails. */
          }
        }}
      >
        <label className="sr-only" htmlFor="message">
          Сообщение помощнику
        </label>
        <textarea
          id="message"
          placeholder="Опишите бизнес или уточните параметры…"
          value={text}
          onChange={(e) => setText(e.target.value)}
          maxLength={4000}
          rows={2}
          disabled={busy}
        />
        <div className="row">
          <small>Локальная модель. Данные проверяет сервер.</small>
          <button
            className="send-button"
            aria-label="Отправить сообщение"
            disabled={busy || !text.trim()}
          >
            ↑
          </button>
        </div>
      </form>
      <p className="privacy">
        Ключ гостевого доступа хранится в этой вкладке браузера.
      </p>
    </aside>
  );
}
