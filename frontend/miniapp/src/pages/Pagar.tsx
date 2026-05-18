import { useEffect, useState } from "react";
import { apiClient } from "../lib/api";
import { haptic, getTg } from "../lib/telegram";
import type { PreciosResponse, PlanInfo } from "../types";

const BOT_USERNAME = import.meta.env.VITE_BOT_USERNAME || "entrenadorax_bot";

export function Pagar() {
  const [data, setData] = useState<PreciosResponse | null>(null);
  const [anual, setAnual] = useState(false);

  useEffect(() => {
    apiClient
      .get<PreciosResponse>("/api/public/precios")
      .then((r) => setData(r.data))
      .catch(console.error);
  }, []);

  function elegirPlan(p: PlanInfo) {
    haptic("medium");
    const isLifetime = p.plan === "lifetime";
    const duracion = isLifetime ? "lifetime" : anual ? "anual" : "mensual";
    const url = `https://t.me/${BOT_USERNAME}?start=pagar_${p.plan}_${duracion}`;
    const tg = getTg();
    if (tg) {
      tg.openTelegramLink(url);
    } else {
      window.location.href = url;
    }
  }

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Mejora tu plan</h1>
      <p className="text-sm text-slate-500">
        Pagos por Bre-B, Nequi, Daviplata, Bancolombia. Activacion automatica
        al subir el comprobante.
      </p>

      <div className="card flex items-center justify-between">
        <span className="text-sm">Facturacion</span>
        <div className="flex rounded-md border border-slate-300 overflow-hidden">
          <button
            onClick={() => setAnual(false)}
            className={`px-3 py-1 text-sm ${
              !anual ? "bg-teal-600 text-white" : "bg-white text-slate-700"
            }`}
          >
            Mensual
          </button>
          <button
            onClick={() => setAnual(true)}
            className={`px-3 py-1 text-sm ${
              anual ? "bg-teal-600 text-white" : "bg-white text-slate-700"
            }`}
          >
            Anual ({data?.descuento_anual_pct ?? 20}% off)
          </button>
        </div>
      </div>

      {data?.planes
        .filter((p) => p.plan !== "free")
        .map((p) => {
          const monto = p.plan === "lifetime" ? p.lifetime_formato : anual ? p.anual_formato : p.mensual_formato;
          const periodo = p.plan === "lifetime" ? "unico" : anual ? "/ano" : "/mes";
          return (
            <div key={p.plan} className="card">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold capitalize">{p.plan}</h3>
                <span className="text-2xl font-bold text-teal-600">
                  {monto} <span className="text-xs text-slate-500">{periodo}</span>
                </span>
              </div>
              <p className="mt-2 text-sm text-slate-600">{p.descripcion}</p>
              <button
                className="btn-primary mt-3 w-full"
                onClick={() => elegirPlan(p)}
              >
                Pagar plan {p.plan}
              </button>
            </div>
          );
        })}

      <p className="text-xs text-slate-400">
        Al continuar abriras el bot para elegir metodo de pago y subir el comprobante.
        Cupos Lifetime: {data?.cupos_lifetime_total ?? 100} en launch.
      </p>
    </div>
  );
}
