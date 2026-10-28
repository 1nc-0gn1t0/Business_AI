import { useEffect, useRef, useState } from "react";
import avatar from "./assets/vi/avatar.webp";
import greeting from "./assets/vi/greeting.webp";
import curious from "./assets/vi/curious.webp";
import thinking from "./assets/vi/thinking.webp";
import working from "./assets/vi/working.webp";
import search from "./assets/vi/search.webp";
import idea from "./assets/vi/idea.webp";
import confident from "./assets/vi/confident.webp";
import neutral from "./assets/vi/neutral.webp";
import ready from "./assets/vi/ready.webp";
import success from "./assets/vi/success.webp";
import error from "./assets/vi/error.webp";
import uncertain from "./assets/vi/uncertain.webp";
import support from "./assets/vi/support.webp";

// URL imports do not fetch these images until an <img> actually uses them.
export const viImages = {
  avatar,
  greeting,
  curious,
  thinking,
  working,
  search,
  idea,
  confident,
  neutral,
  ready,
  success,
  error,
  uncertain,
  support,
} as const;
export type ViEmotion = keyof typeof viImages;

export function ViAvatar({
  emotion = "avatar",
  size = 52,
}: {
  emotion?: ViEmotion;
  size?: number;
}) {
  return (
    <img
      className={`vi-avatar vi-${emotion}`}
      src={viImages[emotion]}
      alt=""
      aria-hidden="true"
      width={size}
      height={size}
      decoding="async"
    />
  );
}

export function ViStatus({
  emotion,
  children,
}: {
  emotion: ViEmotion;
  children: React.ReactNode;
}) {
  return (
    <div className="vi-status" data-emotion={emotion}>
      <ViAvatar emotion={emotion} size={64} />
      <p>{children}</p>
    </div>
  );
}

export function ViWelcomePanel({
  onClose,
  onStart,
}: {
  onClose: () => void;
  onStart: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  function dismiss() {
    dialog.current?.close();
    onClose();
  }
  return (
    <dialog
      ref={dialog}
      id="vi-welcome"
      className="vi-welcome"
      aria-labelledby="vi-welcome-title"
      onCancel={(e) => {
        e.preventDefault();
        dismiss();
      }}
      onClick={(e) => {
        if (e.target === dialog.current) {
          const rect = dialog.current.getBoundingClientRect();
          if (
            e.clientX < rect.left ||
            e.clientX > rect.right ||
            e.clientY < rect.top ||
            e.clientY > rect.bottom
          )
            dismiss();
        }
      }}
    >
      <button
        className="vi-close"
        aria-label="Закрыть приветствие Ви"
        onClick={dismiss}
      >
        ×
      </button>
      <ViAvatar emotion="greeting" size={180} />
      <h2 id="vi-welcome-title">
        Привет! Я Ви <span aria-hidden="true">💙</span>
      </h2>
      <p>Помогу разобраться, с чего начать свой бизнес.</p>
      <button
        className="button"
        onClick={() => {
          dialog.current?.close();
          onStart();
        }}
      >
        Начать с Ви
      </button>
      <small>Business AI · хакатонный помощник</small>
    </dialog>
  );
}

export function ViFloatingButton({ onStart }: { onStart: () => void }) {
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  function close() {
    setOpen(false);
    trigger.current?.focus();
  }
  return (
    <>
      <div
        className="vi-dock"
        aria-label="Демонстрационные элементы и помощник Ви"
      >
        <span
          className="promo-bubble"
          role="img"
          aria-label="Реакция — декоративный элемент"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M8 10l4-7c2 0 2 2 1 6h5a2 2 0 0 1 2 2l-2 8H8M4 10h4v10H4z" />
          </svg>
        </span>
        <span
          className="promo-bubble"
          role="img"
          aria-label="Сообщение — декоративный элемент"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            aria-hidden="true"
          >
            <path d="M4 4h16v12H10l-5 4v-4H4z" />
          </svg>
        </span>
        <button
          ref={trigger}
          className="vi-floating"
          aria-label="Познакомьтесь с Ви"
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open ? "vi-welcome" : undefined}
          onClick={() => setOpen(true)}
        >
          <ViAvatar size={56} />
          <span className="vi-tooltip" aria-hidden="true">
            Познакомьтесь с Ви
          </span>
        </button>
      </div>
      {open && (
        <ViWelcomePanel
          onClose={close}
          onStart={() => {
            setOpen(false);
            onStart();
          }}
        />
      )}
    </>
  );
}
