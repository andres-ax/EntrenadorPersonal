"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { apiClient } from "@/lib/api";

interface AdminStats {
  fecha: string;
  usuarios: {
    total: number;
    onboarded: number;
    bloqueados: number;
    pro_activos: number;
  };
  eventos_30d: Record<string, number>;
  crisis_30d_por_nivel: Record<string, number>;
}

interface Finanzas {
  ingresos_periodo_cop: number;
  usuarios_por_plan: Record<string, number>;
  ingresos_por_metodo: Record<string, { total_cop: number; n: number }>;
  pagos_pendientes_revision: number;
}

export default function Dashboard() {
  const { data: stats } = useQuery({
    queryKey: ["stats"],
    queryFn: async () => (await apiClient.get<AdminStats>("/admin/stats")).data,
  });
  const { data: fin } = useQuery({
    queryKey: ["finanzas"],
    queryFn: async () => (await apiClient.get<Finanzas>("/admin/finanzas?dias=30")).data,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <KPI label="Usuarios totales" value={stats?.usuarios.total} />
        <KPI label="Onboarded" value={stats?.usuarios.onboarded} />
        <KPI label="Pro activos" value={stats?.usuarios.pro_activos} />
        <KPI label="Bloqueados" value={stats?.usuarios.bloqueados} />
        <KPI
          label="MRR estimado (COP)"
          value={fin?.ingresos_periodo_cop?.toLocaleString("es-CO") ?? "—"}
        />
        <KPI
          label="Pagos pendientes"
          value={fin?.pagos_pendientes_revision}
          href="/pagos?estado=pendiente_humano"
        />
        <KPI
          label="Crisis ultimo 30d"
          value={Object.values(stats?.crisis_30d_por_nivel ?? {}).reduce(
            (a, b) => a + b,
            0
          )}
          href="/crisis"
        />
        <KPI label="Hoy" value={stats?.fecha?.split("T")[0]} />
      </div>

      {fin?.usuarios_por_plan && (
        <div className="card">
          <h2 className="font-semibold mb-2">Usuarios por plan</h2>
          <table className="admin">
            <thead>
              <tr>
                <th>Plan</th>
                <th>Cantidad</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(fin.usuarios_por_plan).map(([p, n]) => (
                <tr key={p}>
                  <td className="capitalize">{p}</td>
                  <td>{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function KPI({
  label,
  value,
  href,
}: {
  label: string;
  value: any;
  href?: string;
}) {
  const card = (
    <div className="card hover:border-teal-500 cursor-pointer transition">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="text-2xl font-bold mt-1">{value ?? "—"}</div>
    </div>
  );
  return href ? <Link href={href}>{card}</Link> : card;
}
