"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api";

interface Finanzas {
  fecha: string;
  periodo_dias: number;
  usuarios_por_plan: Record<string, number>;
  ingresos_periodo_cop: number;
  ingresos_por_metodo: Record<string, { total_cop: number; n: number }>;
  pagos_pendientes_revision: number;
}

export default function FinanzasPage() {
  const { data } = useQuery({
    queryKey: ["finanzas-30"],
    queryFn: async () =>
      (await apiClient.get<Finanzas>("/admin/finanzas?dias=30")).data,
  });

  if (!data) return <p>Cargando...</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Finanzas</h1>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="card">
          <div className="text-xs uppercase text-slate-500">Ingresos 30d</div>
          <div className="text-3xl font-bold">
            ${data.ingresos_periodo_cop.toLocaleString("es-CO")}
          </div>
        </div>
        <div className="card">
          <div className="text-xs uppercase text-slate-500">Pagos pendientes revision</div>
          <div className="text-3xl font-bold">{data.pagos_pendientes_revision}</div>
        </div>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2">Ingresos por metodo de pago</h2>
        <table className="admin">
          <thead>
            <tr>
              <th>Metodo</th>
              <th>Transacciones</th>
              <th>Total COP</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.ingresos_por_metodo).map(([m, v]) => (
              <tr key={m}>
                <td>{m}</td>
                <td>{v.n}</td>
                <td>${v.total_cop.toLocaleString("es-CO")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h2 className="font-semibold mb-2">Usuarios por plan</h2>
        <table className="admin">
          <thead>
            <tr>
              <th>Plan</th>
              <th>Usuarios</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(data.usuarios_por_plan).map(([p, n]) => (
              <tr key={p}>
                <td className="capitalize">{p}</td>
                <td>{n}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
