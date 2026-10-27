import { useState, type ReactNode } from "react";
import type { Conversation, Ranking, Schemas } from "./api";
import { rub } from "./api";

export type Screen =
  | "home"
  | "chat"
  | "map"
  | "compare"
  | "finance"
  | "bank"
  | "report";
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    home: (
      <>
        <path d="m3 10 9-7 9 7v10H3z" />
        <path d="M9 20v-7h6v7" />
      </>
    ),
    chat: (
      <>
        <path d="M21 11a9 9 0 0 1-9 9H4l-2 2V11a9 9 0 0 1 19 0Z" />
        <path d="M7 9h9M7 13h6" />
      </>
    ),
    map: (
      <>
        <path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2zM9 3v16M15 5v16" />
      </>
    ),
    compare: (
      <>
        <path d="M4 20V9h4v11M10 20V4h4v16M16 20V12h4v8" />
      </>
    ),
    finance: (
      <>
        <path d="M3 3v18h18M7 15l5-5 4 3 5-7" />
        <path d="M16 6h5v5" />
      </>
    ),
    bank: (
      <>
        <path d="m3 8 9-5 9 5H3ZM5 11v7M10 11v7M15 11v7M20 11v7M3 21h18" />
      </>
    ),
    report: (
      <>
        <path d="M5 3h9l5 5v13H5zM14 3v6h5M9 13h6M9 17h6" />
      </>
    ),
    arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
    spark: (
      <path d="m12 2 2.8 7.2L22 12l-7.2 2.8L12 22l-2.8-7.2L2 12l7.2-2.8Z" />
    ),
    check: <path d="m5 12 4 4L19 6" />,
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.spark}
    </svg>
  );
}

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "info";
}) {
  return <span className={`status-badge ${tone}`}>{children}</span>;
}

export const screens: {
  id: Screen;
  name: string;
  accessible?: string;
  note: string;
}[] = [
  { id: "home", name: "Обзор проекта", note: "С чего начнём" },
  { id: "chat", name: "AI-помощник", note: "Идея и профиль" },
  {
    id: "map",
    name: "Локации",
    accessible: "⌖ Карта и локации",
    note: "Карта и окружение",
  },
  {
    id: "compare",
    name: "Сравнение зон",
    accessible: "▥ Сравнение зон",
    note: "Понятные факторы",
  },
  {
    id: "finance",
    name: "Финансы",
    accessible: "↗ Финансовая модель",
    note: "Три сценария",
  },
  {
    id: "bank",
    name: "Возможности ВТБ",
    accessible: "◇ Продукты ВТБ",
    note: "Добровольный подбор",
  },
  { id: "report", name: "Отчёт", note: "PDF и JSON" },
];

export function Home({
  conversation,
  draft,
  onDraft,
  onSend,
  busy,
  consent,
  onResume,
}: {
  conversation: Conversation | null;
  draft: string;
  onDraft: (value: string) => void;
  onSend: (value: string) => Promise<void>;
  busy: boolean;
  consent: ReactNode;
  onResume: () => void;
}) {
  const [waiting, setWaiting] = useState(false);
  return (
    <section className="home-view" aria-label="Начало работы">
      <div className="home-heading">
        <StatusBadge tone="info">
          <Icon name="spark" size={14} /> Помощник предпринимателя
        </StatusBadge>
        <h1>
          От идеи —<br />к <span>своему бизнесу.</span>
        </h1>
        <p>
          Разберитесь с локацией, оцените экономику и спланируйте следующие
          шаги. Начните с того, что хотите открыть.
        </p>
      </div>
      <div className="home-layout">
        <div>
          <form
            className="idea-form"
            onSubmit={async (event) => {
              event.preventDefault();
              if (!draft.trim() || busy || waiting) return;
              setWaiting(true);
              try {
                await onSend(draft);
                onDraft("");
              } catch {
                /* Preserve the idea on a safe API failure. */
              } finally {
                setWaiting(false);
              }
            }}
          >
            <label htmlFor="idea">Ваша бизнес-идея</label>
            <textarea
              id="idea"
              aria-label="Сообщение помощнику"
              value={draft}
              onChange={(event) => onDraft(event.target.value)}
              maxLength={4000}
              rows={4}
              placeholder="Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей"
              disabled={busy}
            />
            <div className="idea-form-footer">
              <span>
                <Icon name="chat" size={16} /> Можно своими словами
              </span>
              <button
                className="button"
                aria-label="Отправить сообщение"
                disabled={busy || waiting || !draft.trim()}
              >
                {busy || waiting ? "Обрабатываем идею…" : "Разобрать идею"}
                <Icon name="arrow" size={18} />
              </button>
            </div>
          </form>
          <div className="idea-examples">
            <span>Или начните с примера</span>
            {[
              [
                "Кофейня",
                "Хочу открыть кофейню в Казани. Бюджет — 2 миллиона рублей",
              ],
              [
                "Пекарня",
                "Планирую пекарню в Казани. Бюджет 3 миллиона рублей",
              ],
              [
                "Другой город",
                "Хочу открыть магазин в Самаре. Какие данные доступны?",
              ],
            ].map(([label, text]) => (
              <button key={label} onClick={() => onDraft(text)} disabled={busy}>
                {label}
                <span aria-hidden="true">↗</span>
              </button>
            ))}
          </div>
          {consent}
          {conversation && (
            <button className="resume-project" onClick={onResume}>
              <span className="resume-icon">
                <Icon name="report" />
              </span>
              <span>
                <strong>Продолжить проект</strong>
                <small>
                  {conversation.profile.category || "Новая идея"} ·{" "}
                  {conversation.profile.city || "Город уточняется"} ·{" "}
                  {rub(conversation.profile.budget)}
                </small>
              </span>
              <Icon name="arrow" />
            </button>
          )}
        </div>
        <aside
          className="journey-preview"
          aria-label="Как работает Business AI"
        >
          <div className="journey-label">ИЗ ИДЕИ В ПОНЯТНЫЙ ПЛАН</div>
          <h2>
            Один проект.
            <br />
            Вся картина.
          </h2>
          <ol>
            {[
              [
                "chat",
                "Уточним главное",
                "Тип бизнеса, город, бюджет и формат",
              ],
              [
                "map",
                "Изучим окружение",
                "Зоны, инфраструктура и источники OSM",
              ],
              [
                "finance",
                "Посчитаем сценарии",
                "Редактируемые допущения и ограничения",
              ],
              [
                "report",
                "Соберём результат",
                "Аналитический отчёт для вашего решения",
              ],
            ].map(([icon, title, text], i) => (
              <li key={title}>
                <span className="journey-icon">
                  <Icon name={icon} />
                </span>
                <div>
                  <span className="journey-step">0{i + 1}</span>
                  <h3>{title}</h3>
                  <p>{text}</p>
                </div>
              </li>
            ))}
          </ol>
        </aside>
      </div>
      <div className="home-principles">
        <span>
          <Icon name="check" size={16} /> Локальная Qwen
        </span>
        <span>
          <Icon name="check" size={16} /> Проверяемые источники
        </span>
        <span>
          <Icon name="check" size={16} /> Расчёты на сервере
        </span>
      </div>
      <p className="home-limits">
        Хакатонный MVP. Геоанализ зависит от загруженного покрытия — первый
        сценарий в части Казани. Рыночные цены и спрос не измерены. Банковские
        процессы — демонстрационные.
      </p>
    </section>
  );
}

export function ProjectOverview({
  conversation,
  ranking,
  finance,
  bank,
  onOpen,
}: {
  conversation: Conversation | null;
  ranking: Ranking | null;
  finance: Schemas["FinanceResult"] | null;
  bank: Schemas["MatchResult"] | null;
  onOpen: (screen: Screen) => void;
}) {
  return (
    <section className="report-overview">
      <div className="section-heading">
        <div>
          <span className="eyebrow">ВАША ИДЕЯ В ДЕТАЛЯХ</span>
          <h1>От анализа — к решению</h1>
          <p>
            Соберите выполненные расчёты в один документ. Недостающие разделы
            будут обозначены.
          </p>
        </div>
        <StatusBadge>Без отправки в банк</StatusBadge>
      </div>
      <div className="report-project">
        <span className="project-initial">
          <Icon name="spark" size={28} />
        </span>
        <div>
          <h2>{conversation?.profile.category || "Новая бизнес-идея"}</h2>
          <p>
            {conversation?.profile.city || "Город не указан"} · Бюджет{" "}
            {rub(conversation?.profile.budget)}
          </p>
        </div>
        <StatusBadge
          tone={
            conversation?.profile.confirmation_state === "confirmed"
              ? "success"
              : "neutral"
          }
        >
          {conversation?.profile.confirmation_state === "confirmed"
            ? "Профиль подтверждён"
            : "Профиль не подтверждён"}
        </StatusBadge>
      </div>
      <div className="report-sections">
        {[
          {
            screen: "map" as const,
            title: "География",
            ready: !!ranking,
            value: ranking
              ? `${ranking.candidates.features.length} зон-кандидатов`
              : "Анализ ещё не выполнен",
            text: "Географические признаки — не прогноз прибыльности",
          },
          {
            screen: "finance" as const,
            title: "Экономика",
            ready: !!finance,
            value: finance
              ? `${finance.scenarios.length} финансовых сценария`
              : "Нужен расчёт вводных",
            text: "Сценарные допущения отмечены как синтетические",
          },
          {
            screen: "bank" as const,
            title: "Возможности ВТБ",
            ready: !!bank,
            value: bank
              ? "Подбор по явным правилам"
              : "Можно добавить по желанию",
            text: "Демо-каталог, без кредитного одобрения",
          },
        ].map((item) => (
          <button
            className="report-section-card"
            key={item.screen}
            onClick={() => onOpen(item.screen)}
          >
            <Icon name={item.screen} size={24} />
            <h3>{item.title}</h3>
            <strong>{item.value}</strong>
            <p>{item.text}</p>
            <span>
              {item.ready ? "Открыть результат" : "Перейти к разделу"} →
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
