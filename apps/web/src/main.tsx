import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";

type ConnectionState =
  | { status: "loading" }
  | { status: "ready"; postgisVersion: string }
  | { status: "error" };

function App() {
  const [connection, setConnection] = useState<ConnectionState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 10000);
    let active = true;

    async function checkHealth() {
      try {
        const response = await fetch("/healthz", { signal: controller.signal });
        if (!response.ok) throw new Error("API is unavailable");
        const health: unknown = await response.json();
        if (
          typeof health !== "object" || health === null ||
          !("status" in health) || health.status !== "ok" ||
          !("database" in health) || health.database !== "ok" ||
          !("postgis_version" in health) || typeof health.postgis_version !== "string"
        ) throw new Error("Invalid health response");
        if (active) setConnection({ status: "ready", postgisVersion: health.postgis_version });
      } catch {
        if (active) setConnection({ status: "error" });
      } finally {
        window.clearTimeout(timeout);
      }
    }

    void checkHealth();
    return () => {
      active = false;
      window.clearTimeout(timeout);
      controller.abort();
    };
  }, []);

  return (
    <main>
      <p className="eyebrow">Sab0tage / BA-001</p>
      <h1>Business AI</h1>
      <p className="intro">От бизнес-идеи к обоснованному плану запуска.</p>
      <section aria-labelledby="environment-title">
        <h2 id="environment-title">Рабочее окружение</h2>
        <div role="status" aria-live="polite">
          {connection.status === "loading" && <p>Проверяем API и базу данных…</p>}
          {connection.status === "ready" && (
            <>
              <p className="success">API и PostgreSQL/PostGIS доступны</p>
              <p className="version">PostGIS: {connection.postgisVersion}</p>
            </>
          )}
          {connection.status === "error" && (
            <p className="error">API или база данных недоступны. Проверьте docker compose ps и обновите страницу.</p>
          )}
        </div>
      </section>
      <p className="note">Стартовый технический экран. Аналитика, AI-диалог и банковские интеграции ещё не реализованы.</p>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
