import { useState } from "react";
import { apiClient } from "../lib/api";
import { haptic, notifyHaptic } from "../lib/telegram";

interface EjercicioPlan {
  nombre: string;
  series: number;
  reps_min: number;
  reps_max: number;
  rpe_objetivo: number;
  descanso_seg: number;
}
interface DiaPlan {
  dia_semana: number;
  tipo: string;
  duracion_min: number;
  ejercicios: EjercicioPlan[];
}
interface PlanSemanalResp {
  plan: {
    semana_inicio: string;
    dias: DiaPlan[];
    volumen_total: number;
    deload: boolean;
  } | null;
}

const DIAS_LABEL = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"];

export function Plan() {
  const [plan, setPlan] = useState<PlanSemanalResp["plan"] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generar() {
    setLoading(true);
    setError(null);
    haptic("medium");
    try {
      const { data } = await apiClient.post<PlanSemanalResp>("/api/me/plan/generar");
      setPlan(data.plan);
      notifyHaptic("success");
    } catch (e: any) {
      console.error(e);
      const status = e?.response?.status;
      if (status === 402 || status === 403) {
        setError("Necesitas plan Pro o superior para generar planes. Ve a Pagar.");
      } else {
        setError("No pude generar el plan. Intenta de nuevo.");
      }
      notifyHaptic("error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Plan semanal</h1>
      <button className="btn-primary w-full" onClick={generar} disabled={loading}>
        {loading ? "Generando..." : plan ? "Regenerar" : "Generar plan semanal"}
      </button>
      {error && <p className="text-red-600 text-sm">{error}</p>}

      {plan && (
        <>
          <p className="text-sm text-slate-500">
            Semana del {plan.semana_inicio} · Volumen total: <b>{plan.volumen_total}</b> sets
            {plan.deload && " · DELOAD"}
          </p>
          {plan.dias.map((d) => (
            <div key={d.dia_semana} className="card">
              <h3 className="text-sm font-semibold">
                {DIAS_LABEL[d.dia_semana] ?? "?"} - {d.tipo} ({d.duracion_min} min)
              </h3>
              <ul className="mt-2 space-y-1">
                {d.ejercicios.map((e, i) => (
                  <li key={i} className="text-sm">
                    <b>{e.nombre}</b>: {e.series}x{e.reps_min}-{e.reps_max} @ RPE {e.rpe_objetivo}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </>
      )}
    </div>
  );
}
