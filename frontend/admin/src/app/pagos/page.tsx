"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Pago {
  id: number;
  usuario_id: number;
  monto_cop: number;
  monto_esperado_cop: number;
  monto_match: boolean;
  plan_solicitado: string;
  duracion: string;
  metodo: string;
  estado: string;
  referencia: string;
  creado_en: string | null;
}
interface ListResp {
  total: number;
  items: Pago[];
}

const ESTADOS = ["pendiente_humano", "aprobado", "rechazado", "duplicado"];

export default function PagosPage() {
  const [estado, setEstado] = useState("pendiente_humano");
  const { data, isFetching } = useQuery({
    queryKey: ["pagos", estado],
    queryFn: async () =>
      (await apiClient.get<ListResp>(`/admin/pagos?estado=${estado}&limit=100`)).data,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Pagos por comprobante</h1>
      <div className="flex gap-2">
        {ESTADOS.map((e) => (
          <button
            key={e}
            className={`btn-secondary ${
              estado === e ? "bg-teal-600 text-white border-teal-600" : ""
            }`}
            onClick={() => setEstado(e)}
          >
            {e}
          </button>
        ))}
      </div>
      <div className="card overflow-x-auto">
        <p className="text-sm text-slate-500">
          Total: {data?.total ?? "—"} {isFetching && "(cargando...)"}
        </p>
        <table className="admin mt-2">
          <thead>
            <tr>
              <th>ID</th>
              <th>Usuario</th>
              <th>Monto</th>
              <th>Esperado</th>
              <th>Match</th>
              <th>Plan</th>
              <th>Metodo</th>
              <th>Ref</th>
              <th>Creado</th>
              <th>Accion</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((p) => (
              <tr key={p.id} className={p.monto_match ? "" : "bg-amber-50"}>
                <td>{p.id}</td>
                <td className="font-mono text-xs">{p.usuario_id}</td>
                <td>${p.monto_cop?.toLocaleString("es-CO")}</td>
                <td>${p.monto_esperado_cop?.toLocaleString("es-CO")}</td>
                <td>{p.monto_match ? "OK" : "NO"}</td>
                <td className="capitalize">{p.plan_solicitado}</td>
                <td>{p.metodo}</td>
                <td className="text-xs">{p.referencia}</td>
                <td className="text-xs">{p.creado_en?.slice(0, 16)}</td>
                <td>
                  <Link href={`/pagos/${p.id}`} className="text-teal-600 underline">
                    Revisar
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
