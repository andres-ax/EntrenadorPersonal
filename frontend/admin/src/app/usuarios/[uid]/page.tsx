"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface DetalleResp {
  usuario: any;
  bloqueado: any;
  suscripciones: any[];
  pagos: any[];
  crisis: any[];
  eventos_recientes: any[];
}

export default function DetalleUsuario() {
  const params = useParams<{ uid: string }>();
  const uid = params.uid;
  const qc = useQueryClient();
  const [planAsignar, setPlanAsignar] = useState("starter");
  const [diasAsignar, setDiasAsignar] = useState(30);
  const [motivoBloqueo, setMotivoBloqueo] = useState("");

  const { data } = useQuery({
    queryKey: ["detalle", uid],
    queryFn: async () =>
      (await apiClient.get<DetalleResp>(`/admin/usuarios/${uid}`)).data,
  });

  const asignar = useMutation({
    mutationFn: async () =>
      apiClient.post(`/admin/usuarios/${uid}/asignar_plan`, {
        plan: planAsignar,
        dias: diasAsignar,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detalle", uid] }),
  });

  const bloquear = useMutation({
    mutationFn: async () =>
      apiClient.post(`/admin/usuarios/${uid}/bloquear`, { motivo: motivoBloqueo }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detalle", uid] }),
  });

  const desbloquear = useMutation({
    mutationFn: async () => apiClient.delete(`/admin/usuarios/${uid}/bloquear`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detalle", uid] }),
  });

  const pausar = useMutation({
    mutationFn: async () =>
      apiClient.post(`/admin/usuarios/${uid}/pausar`, { dias: 7 }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["detalle", uid] }),
  });

  if (!data) return <p>Cargando...</p>;
  const u = data.usuario;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">
        {u.nombre || "Sin nombre"} <span className="text-xs text-slate-500">#{u.telegram_id}</span>
      </h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="card">
          <h3 className="font-semibold">Perfil</h3>
          <p>Email: {u.email || "—"}</p>
          <p>Pais: {u.pais}</p>
          <p>Tono: {u.tono}</p>
          <p>Plan: <b>{u.plan_actual}</b></p>
          <p>Expira: {u.plan_expira_en?.slice(0, 10) || "—"}</p>
          <p>Onboarding: {u.onboarding_completo ? "completo" : "incompleto"}</p>
          <p>Bot bloqueado por user: {u.bot_bloqueado ? "si" : "no"}</p>
          {data.bloqueado && (
            <div className="bg-red-50 border border-red-200 p-2 mt-2 rounded">
              <b>Bloqueado:</b> {data.bloqueado.motivo}
              <p className="text-xs">por {data.bloqueado.por} en {data.bloqueado.en?.slice(0, 16)}</p>
            </div>
          )}
        </div>

        <div className="card space-y-2">
          <h3 className="font-semibold">Acciones rapidas</h3>

          <div className="flex gap-2">
            <select
              className="input"
              value={planAsignar}
              onChange={(e) => setPlanAsignar(e.target.value)}
            >
              <option value="starter">Starter</option>
              <option value="pro">Pro</option>
              <option value="elite">Elite</option>
              <option value="lifetime">Lifetime</option>
            </select>
            <input
              type="number"
              className="input w-20"
              value={diasAsignar}
              onChange={(e) => setDiasAsignar(Number(e.target.value))}
            />
            <button className="btn-primary" onClick={() => asignar.mutate()}>
              Asignar plan
            </button>
          </div>

          <button className="btn-secondary" onClick={() => pausar.mutate()}>
            Pausar 7 dias
          </button>

          {data.bloqueado ? (
            <button className="btn-secondary" onClick={() => desbloquear.mutate()}>
              Desbloquear
            </button>
          ) : (
            <div className="flex gap-2">
              <input
                className="input flex-1"
                placeholder="motivo bloqueo"
                value={motivoBloqueo}
                onChange={(e) => setMotivoBloqueo(e.target.value)}
              />
              <button
                className="btn-danger"
                onClick={() => motivoBloqueo && bloquear.mutate()}
              >
                Bloquear
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h3 className="font-semibold mb-2">Pagos ({data.pagos.length})</h3>
        <table className="admin">
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Monto</th>
              <th>Plan</th>
              <th>Metodo</th>
              <th>Estado</th>
            </tr>
          </thead>
          <tbody>
            {data.pagos.map((p) => (
              <tr key={p.id}>
                <td>{p.creado_en?.slice(0, 16)}</td>
                <td>${p.monto_cop?.toLocaleString("es-CO")}</td>
                <td>{p.plan_solicitado}</td>
                <td>{p.metodo}</td>
                <td>{p.estado}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3 className="font-semibold mb-2">Eventos recientes</h3>
        <ul className="text-xs space-y-1">
          {data.eventos_recientes.slice(0, 20).map((e: any, i) => (
            <li key={i}>
              <span className="text-slate-500">{e.en?.slice(0, 16)}</span> · <b>{e.tipo}</b>{" "}
              {JSON.stringify(e.payload)}
            </li>
          ))}
        </ul>
      </div>

      {data.crisis.length > 0 && (
        <div className="card border-red-200">
          <h3 className="font-semibold mb-2 text-red-700">Crisis</h3>
          {data.crisis.map((c: any) => (
            <div key={c.id} className="text-sm">
              <b>Nivel {c.nivel}</b> · {c.creado_en?.slice(0, 16)} ·{" "}
              {(c.keywords || []).join(", ")}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
