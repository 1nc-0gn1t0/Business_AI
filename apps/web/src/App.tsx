import { lazy, Suspense, useEffect, useState } from "react";
import Landing from "./Landing";
import "./vi.css";
const BusinessFlow = lazy(() => import("./BusinessFlow"));
const inWorkspace = () =>
  ["#business-ai", "#main-content"].includes(window.location.hash);

export default function App() {
  const [workspace, setWorkspace] = useState(inWorkspace);
  const [started, setStarted] = useState(inWorkspace);
  useEffect(() => {
    function sync() {
      const next = inWorkspace();
      setWorkspace(next);
      if (next) setStarted(true);
    }
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  function start() {
    setStarted(true);
    setWorkspace(true);
    window.location.hash = "business-ai";
  }
  function home() {
    setWorkspace(false);
    window.location.hash = "";
  }
  // Keep an already opened project mounted when returning to the landing.
  return (
    <>
      {!workspace && <Landing onStart={start} />}
      {started && (
        <div hidden={!workspace}>
          <Suspense fallback={<p role="status">Открываем Business AI…</p>}>
            <BusinessFlow onHome={home} active={workspace} />
          </Suspense>
        </div>
      )}
    </>
  );
}
