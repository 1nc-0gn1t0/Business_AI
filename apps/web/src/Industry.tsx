import { useState } from "react";
import type { Schemas } from "./api";
import { ViAvatar } from "./Vi";

export type IndustryView = Schemas["UniversalView"];
export type IndustryEdit = Partial<Schemas["UniversalPatch"]> & {
  expected_version: number;
};

export function IndustryReview({
  view,
  industries,
  busy,
  onSave,
  onConfirm,
  onChat,
}: {
  view: IndustryView;
  busy: boolean;
  industries: Schemas["IndustryDefinition"][];
  onSave: (patch: Omit<IndustryEdit, "expected_version">) => Promise<void>;
  onConfirm: () => void;
  onChat: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const p = view.profile;
  const values = { ...p.values, ...p.extensions?.[p.industry] };
  const fields = view.field_definitions;
  return (
    <section className="review-screen">
      <h1>Ваш проект</h1>
      <h2>{p.raw_industry || view.configuration.label}</h2>
      <p>{p.idea}</p>
      <dl>
        {fields
          .filter((f) => values[f.id])
          .map((f) => (
            <div key={f.id}>
              <dt>{f.label}</dt>
              <dd>
                {String(
                  values[f.id].value === true
                    ? "Да"
                    : values[f.id].value === false
                      ? "Нет"
                      : values[f.id].value,
                )}
              </dd>
            </div>
          ))}
      </dl>
      <p>
        {p.confirmed_revision === p.revision
          ? "Параметры подтверждены"
          : "Проверьте параметры"}
      </p>
      {view.plan.next_question && (
        <p role="status">{view.plan.next_question}</p>
      )}
      {view.plan.next_question &&
        view.plan.missing_fields[0] !== "industry" && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => {
              void onSave({
                updates: [],
                defer_fields: [
                  view.plan.missing_fields.find(
                    (k) => !p.deferred_fields?.includes(k),
                  )!,
                ],
              }).catch(() => {});
            }}
          >
            Пока не знаю
          </button>
        )}
      <button
        className="text-button"
        onClick={() => setEditing(!editing)}
        disabled={busy}
      >
        Изменить параметры
      </button>
      {editing && (
        <form
          className="profile-form"
          key={`${p.revision}:${p.industry}`}
          onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            const industry = String(form.get("industry"));
            if (industry !== p.industry) {
              await onSave({ industry, updates: [] }).catch(() => {});
              return;
            }
            const updates = fields
              .filter((f) => form.has(f.id))
              .map((f) => {
                const raw = String(form.get(f.id) || "").trim();
                return {
                  field: f.id,
                  value:
                    raw === ""
                      ? null
                      : f.kind === "boolean"
                        ? raw === "true"
                        : raw,
                };
              });
            await onSave({ updates }).then(
              () => setEditing(false),
              () => {},
            );
          }}
        >
          <label>
            Тип бизнеса
            <select name="industry" defaultValue={p.industry}>
              {industries.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          {fields
            .filter(
              (f) => view.configuration.required.includes(f.id) || values[f.id],
            )
            .map((f) => (
              <label key={f.id}>
                {f.label}
                {f.kind === "boolean" || f.kind === "choice" ? (
                  <select
                    name={f.id}
                    defaultValue={
                      values[f.id] ? String(values[f.id].value) : ""
                    }
                  >
                    <option value="">Не указано</option>
                    {f.kind === "boolean" ? (
                      <>
                        <option value="true">Да</option>
                        <option value="false">Нет</option>
                      </>
                    ) : (
                      f.choices.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))
                    )}
                  </select>
                ) : (
                  <input
                    name={f.id}
                    maxLength={200}
                    defaultValue={
                      values[f.id] ? String(values[f.id].value) : ""
                    }
                  />
                )}
              </label>
            ))}
          <button className="button" disabled={busy}>
            Сохранить параметры
          </button>
          <small>
            Смена типа бизнеса обновит вопросы. Прежние отраслевые вводные
            сохранятся.
          </small>
        </form>
      )}
      <div className="actions">
        <button
          className="button"
          onClick={onConfirm}
          disabled={busy || !!view.plan.next_question}
        >
          Продолжить
        </button>
        <button className="text-button" onClick={onChat} disabled={busy}>
          Вернуться в диалог
        </button>
      </div>
      <details>
        <summary>Доступные методы</summary>
        <IndustryCapabilities view={view} />
      </details>
    </section>
  );
}

function IndustryCapabilities({ view }: { view: IndustryView }) {
  return (
    <>
      {view.plan.capabilities
        .filter((c) => ["geo.analysis", "finance.analysis"].includes(c.id))
        .map((c) => (
          <p key={c.id}>{c.reason}</p>
        ))}
      {view.plan.coverage && (
        <ul>
          {view.plan.coverage.assessments.map((a) => (
            <li key={a.category}>
              {a.category}: {a.local_status}
            </li>
          ))}
        </ul>
      )}
      <p>
        Полнота рыночных данных не подтверждена. Неизвестные показатели не
        заменяются нулями.
      </p>
    </>
  );
}

export function IndustryResult({
  view,
  onEdit,
  onDownload,
  busy,
}: {
  view: IndustryView;
  onEdit: () => void;
  onDownload: () => void;
  busy: boolean;
}) {
  return (
    <section className="summary-screen">
      <ViAvatar emotion="neutral" size={56} />
      <h1>Вводные готовы</h1>
      <p>{view.profile.raw_industry || view.configuration.label}</p>
      <p>
        {view.plan.geo_required === false
          ? "Геоанализ не требуется. Можно работать без карты."
          : "География учтена в проверке доступности данных."}
      </p>
      <dl className="industry-inputs">
        {view.configuration.required.map((key) => {
          const entry =
            view.profile.values?.[key] ||
            view.profile.extensions?.[view.profile.industry]?.[key];
          const definition = view.field_definitions.find((f) => f.id === key);
          return entry && definition ? (
            <div key={key}>
              <dt>{definition.label}</dt>
              <dd>
                {typeof entry.value === "boolean"
                  ? entry.value
                    ? "Да"
                    : "Нет"
                  : String(entry.value)}
              </dd>
            </div>
          ) : null;
        })}
      </dl>
      <p>
        Частичный результат: прибыль и отраслевой рейтинг пока не рассчитаны.
      </p>
      <details>
        <summary>Возможности и ограничения</summary>
        <p>Исходная идея: {view.profile.idea}</p>
        <IndustryCapabilities view={view} />
      </details>
      <div className="actions">
        <button className="button" onClick={onDownload} disabled={busy}>
          Скачать вводные JSON
        </button>
        <button className="text-button" onClick={onEdit} disabled={busy}>
          Изменить проект
        </button>
      </div>
    </section>
  );
}
