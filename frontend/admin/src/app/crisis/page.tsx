"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface CrisisItem {
  id: number;
  usuario_id: number;
  nivel: number;
  keywords: string[];
  derivado_a: string;
  mensaje_usuario: string;
  creado_en: string;
}

export default function CrisisPage() {
  const [nivel, setNivel] = useState<number | "">("");
  const [dias, setDias] = useState(30);
  const { data } = useQuery({
    queryKey: ["crisis", nivel, dias],
    queryFn: async () => {
      const params = new URLSearchParams({ dias: String(dias) });
      if (nivel) params.set("nivel", String(nivel));
      return (
        await apiClient.get<{ total: number; items: CrisisItem[] }>(
          `/admin/crisis?${params}`
        )
      ).data;
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold text-red-700">Crisis Log</h1>
      <div className="flex gap-2">
        <select
          className="input"
          value={nivel}
          onChange={(e) => setNivel(e.target.value ? Number(e.target.value) : "")}
        >
          <option value="">Todos niveles</option>
          <option value={1}>Nivel 1 (urgente)</option>
          <option value={2}>Nivel 2 (alta)</option>
          <option value={3}>Nivel 3 (vigilancia)</option>
        </select>
        <input
          type="number"
          className="input w-20"
          value={dias}
          onChange={(e) => setDias(Number(e.target.value))}
        />
        <span className="text-sm self-center text-slate-500">dias atras</span>
      </div>
      <div className="card">
        <p>Total: {data?.total ?? "—"}</p>
        <table className="admin mt-2">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>UID</th>
              <th>Nivel</th>
              <th>Keywords</th>
              <th>Derivado a</th>
              <th>Mensaje (truncado)</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((c) => (
              <tr key={c.id} className={c.nivel === 1 ? "bg-red-50" : ""}>
                <td className="text-xs">{c.creado_en?.slice(0, 16)}</td>
                <td className="font-mono text-xs">{c.usuario_id}</td>
                <td>{c.nivel}</td>
                <td className="text-xs">{(c.keywords || []).join(", ")}</td>
                <td className="text-xs">{c.derivado_a}</td>
                <td className="text-xs max-w-md">
                  {c.mensaje_usuario?.slice(0, 200)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
