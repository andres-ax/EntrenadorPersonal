"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Usuario {
  id: number;
  telegram_id: number;
  nombre: string | null;
  email: string | null;
  pais: string;
  tono: string;
  plan_actual: string;
  plan_expira_en: string | null;
  bot_bloqueado: boolean;
  onboarding_completo: boolean;
}

interface ListResp {
  total: number;
  limit: number;
  offset: number;
  items: Usuario[];
}

export default function UsuariosPage() {
  const [q, setQ] = useState("");
  const [plan, setPlan] = useState("");
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["usuarios", q, plan],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (q) params.set("q", q);
      if (plan) params.set("plan", plan);
      params.set("limit", "50");
      return (await apiClient.get<ListResp>(`/admin/usuarios?${params}`)).data;
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Usuarios</h1>
      <div className="flex gap-2 items-center">
        <input
          className="input"
          placeholder="buscar nombre/email/codigo..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && refetch()}
        />
        <select
          className="input"
          value={plan}
          onChange={(e) => setPlan(e.target.value)}
        >
          <option value="">Todos planes</option>
          <option value="free">Free</option>
          <option value="starter">Starter</option>
          <option value="pro">Pro</option>
          <option value="elite">Elite</option>
          <option value="lifetime">Lifetime</option>
        </select>
        <button className="btn-primary" onClick={() => refetch()}>
          Buscar
        </button>
      </div>

      <div className="card overflow-x-auto">
        <p className="text-sm text-slate-500">
          Total: {data?.total ?? "—"} {isFetching && "(cargando...)"}
        </p>
        <table className="admin mt-2">
          <thead>
            <tr>
              <th>Telegram ID</th>
              <th>Nombre</th>
              <th>Pais</th>
              <th>Plan</th>
              <th>Expira</th>
              <th>Estado</th>
              <th>Accion</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((u) => (
              <tr key={u.id}>
                <td className="font-mono text-xs">{u.telegram_id}</td>
                <td>{u.nombre || "—"}</td>
                <td>{u.pais}</td>
                <td className="capitalize">{u.plan_actual}</td>
                <td className="text-xs">
                  {u.plan_expira_en?.slice(0, 10) || "—"}
                </td>
                <td className="text-xs">
                  {u.bot_bloqueado ? "bloqueado bot" : u.onboarding_completo ? "OK" : "onboarding"}
                </td>
                <td>
                  <Link href={`/usuarios/${u.telegram_id}`} className="text-teal-600 underline">
                    Ver
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
