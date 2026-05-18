import { useEffect, useState } from "react";
import { apiClient } from "../lib/api";

interface DiaEntreno {
  fecha: string;
  realizado: boolean;
  planeado: boolean;
  tipo: string | null;
  resumen: string;
}

interface CalendarResp {
  semana_inicio: string;
  dias: DiaEntreno[];
}

export function Calendario() {
  const [data, setData] = useState<CalendarResp | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<CalendarResp>("/api/me/calendar")
      .then((r) => setData(r.data))
      .catch(() => setError("No pude cargar el calendario"));
  }, []);

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Calendario semanal</h1>
      {error && <p className="text-red-600">{error}</p>}
      {!data && !error && <p className="text-slate-500">Cargando...</p>}
      {data && (
        <div className="grid grid-cols-7 gap-2">
          {data.dias.map((d) => (
            <div
              key={d.fecha}
              className={`card text-center ${
                d.realizado
                  ? "border-teal-500"
                  : d.planeado
                  ? "border-amber-400"
                  : ""
              }`}
            >
              <div className="text-xs text-slate-500">
                {new Date(d.fecha).toLocaleDateString("es", {
                  weekday: "short",
                  day: "numeric",
                })}
              </div>
              <div className="mt-1 text-2xl">
                {d.realizado ? "OK" : d.planeado ? "..." : "-"}
              </div>
              {d.tipo && (
                <div className="mt-1 text-[10px] text-slate-400">{d.tipo}</div>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-slate-500">
        Verde = entrenaste. Naranja = planeado. Tap para detalle (proximamente).
      </p>
    </div>
  );
}
