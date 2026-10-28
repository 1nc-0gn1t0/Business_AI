import { useState } from "react";
import { ViAvatar, ViFloatingButton } from "./Vi";
import "./landing.css";

export default function Landing({ onStart }: { onStart: () => void }) {
  const [welcome, setWelcome] = useState(false);
  return (
    <div className="bank-landing">
      <a className="skip-link" href="#promo-content">
        Перейти к содержимому
      </a>
      <section className="bank-hero">
        <header className="bank-header">
          <span className="bank-wordmark">
            Business <b>AI</b>
          </span>
          <div className="bank-segments" aria-hidden="true">
            <span>Частным лицам</span>
            <span>Бизнесу</span>
          </div>
          <div className="bank-header-icons" aria-hidden="true">
            <span>⌕</span>
            <span>Для ваших идей</span>
            <span>☰</span>
          </div>
        </header>
        <main id="promo-content" tabIndex={-1} className="bank-content">
          <div className="bank-copy">
            <h1>
              Ваш бизнес
              <br />
              начинается с идеи
            </h1>
            <button className="bank-cta" onClick={() => setWelcome(true)}>
              Познакомиться с Ви
            </button>
          </div>
          <div className="bank-character">
            <ViAvatar emotion="greeting" motion="none" size={720} />
          </div>
          <div className="bank-promos" aria-hidden="true">
            <div>
              <span>
                От первой идеи
                <br />к своему делу
              </span>
              <i className="bank-thumb thumb-one" />
            </div>
            <div className="current">
              <span>
                Маленький помощник
                <br />
                для больших идей
              </span>
              <i className="bank-thumb thumb-two" />
            </div>
            <div>
              <span>
                Ваш план
                <br />в одном месте
              </span>
              <i className="bank-thumb thumb-three" />
            </div>
            <span className="bank-promo-dots">● ● ● ● ●</span>
          </div>
        </main>
      </section>
      <footer className="bank-footer">
        Business AI — независимый проект. Не официальный сервис ВТБ.
      </footer>
      <ViFloatingButton
        onStart={onStart}
        open={welcome}
        onOpen={() => setWelcome(true)}
        onClose={() => setWelcome(false)}
      />
    </div>
  );
}
