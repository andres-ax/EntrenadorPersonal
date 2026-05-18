import { useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";

import { Dashboard } from "./pages/Dashboard";
import { Calendario } from "./pages/Calendario";
import { Plan } from "./pages/Plan";
import { PRs } from "./pages/PRs";
import { Settings } from "./pages/Settings";
import { Pagar } from "./pages/Pagar";
import { Llamar } from "./pages/Llamar";
import { Wearables } from "./pages/Wearables";
import { loginConInitData } from "./lib/api";
import { getTg, inTelegram } from "./lib/telegram";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const tg = getTg();
    if (tg) {
      tg.ready();
      tg.expand();
    }
    if (!inTelegram()) {
      setError("Esta app debe abrirse desde Telegram. En el bot escribe /start.");
      return;
    }
    loginConInitData(tg!.initData)
      .then(() => setReady(true))
      .catch((e) => {
        console.error(e);
        setError("No pude autenticarte. Cierra y vuelve a abrir desde Telegram.");
      });
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <div className="card max-w-sm text-center">
          <h1 className="mb-2 text-lg font-bold">EntrenadorAX</h1>
          <p className="text-sm text-slate-600">{error}</p>
        </div>
      </div>
    );
  }

  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-slate-500">Cargando tu sesion...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full pb-16">
      <main className="flex-1 overflow-y-auto p-4">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/calendario" element={<Calendario />} />
          <Route path="/plan" element={<Plan />} />
          <Route path="/prs" element={<PRs />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/pagar" element={<Pagar />} />
          <Route path="/llamar" element={<Llamar />} />
          <Route path="/wearables" element={<Wearables />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <BottomNav />
    </div>
  );
}

function BottomNav() {
  const items: Array<{ to: string; label: string }> = [
    { to: "/", label: "Inicio" },
    { to: "/calendario", label: "Cal" },
    { to: "/plan", label: "Plan" },
    { to: "/prs", label: "PRs" },
    { to: "/settings", label: "Ajustes" },
  ];
  return (
    <nav className="fixed bottom-0 left-0 right-0 grid grid-cols-5 border-t border-slate-200 bg-white dark:bg-slate-900 dark:border-slate-700">
      {items.map((it) => (
        <NavLink
          key={it.to}
          to={it.to}
          end={it.to === "/"}
          className={({ isActive }) =>
            `flex items-center justify-center py-3 text-xs ${
              isActive ? "text-teal-600 font-semibold" : "text-slate-500"
            }`
          }
        >
          {it.label}
        </NavLink>
      ))}
    </nav>
  );
}
