import { ViFloatingButton } from "./Vi";

export default function Landing({ onStart }: { onStart: () => void }) {
  return (
    <div className="promo-page">
      <a className="skip-link" href="#promo-content">
        Перейти к содержимому
      </a>
      <section className="promo-hero">
        <header className="promo-header">
          <span className="promo-wordmark">
            Business <b>AI</b>
            <small>ХАКАТОННЫЙ КОНЦЕПТ</small>
          </span>
          <div className="promo-segments" aria-label="Декоративная навигация">
            <span>Частным лицам</span>
            <span>Бизнесу</span>
          </div>
          <span className="promo-header-note">
            Новые идеи. Новые возможности.
          </span>
        </header>
        <main id="promo-content" tabIndex={-1} className="promo-content">
          <div className="promo-copy">
            <p className="promo-eyebrow">
              Маленький помощник для больших бизнес-идей
            </p>
            <h1>
              Ваш бизнес.
              <br />С первой идеи.
            </h1>
            <p className="promo-subtitle">
              Всё большое начинается с разговора.
            </p>
            <span className="promo-white-plate">Ви · ваш AI-помощник</span>
          </div>
          <div className="promo-sculpture" aria-hidden="true">
            <div className="promo-orbit" />
            <div className="promo-sphere" />
            <div className="promo-idea-card">
              <span>Ваша идея</span>
              <i />
              <i />
              <i />
              <strong>
                Большое
                <br />
                начинается
                <br />с малого.
              </strong>
              <span className="promo-card-dot">↗</span>
            </div>
            <div className="promo-fold fold-one" />
            <div className="promo-fold fold-two" />
          </div>
        </main>
        <p className="promo-concept">
          Хакатонный концепт · Неофициальный прототип
        </p>
      </section>
      <footer className="promo-footer">
        Ви — ваш маленький помощник для больших бизнес-идей.
        <span>Не официальный сервис ВТБ.</span>
      </footer>
      <ViFloatingButton onStart={onStart} />
    </div>
  );
}
