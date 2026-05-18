import { useEffect, useState } from "react";
import { apiClient } from "../lib/api";
import type { DashboardData } from "../types";

export function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<DashboardData>("/api/me/dashboard")
      .then((r) => setData(r.data))
      .catch((e) => {
        console.error(e);
        setError("No pude cargar el dashboard");
      });
  }, []);

  if (error) return <div className="text-red-600">{error}</div>;
  if (!data) return <div className="text-slate-500">Cargando...</div>;

  const r = data.reporte_semanal;
  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Tu semana</h1>
      <div className="grid grid-cols-2 gap-3">
        <Card title="Dias entrenados" value={r.dias_entrenados} />
        <Card title="Volumen (kg)" value={Math.round(r.volumen_total_kg)} />
        <Card title="Streak entreno" value={data.streak_entreno.dias_actuales} />
        <Card title="Freezes" value={data.streak_entreno.freezes_disponibles} />
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-slate-500">Nutricion hoy</h2>
        <div className="mt-2 grid grid-cols-4 text-center">
          <Macro label="Kcal" value={data.nutricion_hoy.total_calorias} />
          <Macro label="P" value={Math.round(data.nutricion_hoy.total_proteinas)} unit="g" />
          <Macro label="C" value={Math.round(data.nutricion_hoy.total_carbs)} unit="g" />
          <Macro label="G" value={Math.round(data.nutricion_hoy.total_grasas)} unit="g" />
        </div>
      </div>

      <div className="card">
        <h2 className="text-sm font-semibold text-slate-500">Graficos</h2>
        <ImgChart src="/api/me/charts/peso.png" alt="Peso historico" />
        <ImgChart src="/api/me/charts/volumen.png" alt="Volumen semanal" />
        <ImgChart src="/api/me/charts/streak.png" alt="Streak calendario" />
        <ImgChart src="/api/me/charts/macros.png" alt="Macros del dia" />
      </div>

      {r.nuevos_prs.length > 0 && (
        <div className="card">
          <h2 className="text-sm font-semibold text-slate-500">Nuevos PRs esta semana</h2>
          <ul className="mt-2 space-y-1">
            {r.nuevos_prs.map((pr, i) => (
              <li key={i} className="text-sm">
                <b>{pr.ejercicio}</b>: {pr.peso_kg}kg x{pr.reps}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Card({ title, value }: { title: string; value: number | string }) {
  return (
    <div className="card text-center">
      <div className="text-xs text-slate-500">{title}</div>
      <div className="mt-1 text-2xl font-bold">{value}</div>
    </div>
  );
}

function Macro({ label, value, unit = "" }: { label: string; value: number; unit?: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-lg font-semibold">
        {value}
        {unit}
      </div>
    </div>
  );
}

function ImgChart({ src, alt }: { src: string; alt: string }) {
  const [hidden, setHidden] = useState(false);
  if (hidden) return null;
  return (
    <img
      src={src}
      alt={alt}
      className="mt-3 w-full rounded-md border border-slate-200"
      onError={() => setHidden(true)}
    />
  );
}
