"use client";

import { useState } from "react";
import { apiClient } from "@/lib/api";

export default function OperacionesPage() {
  const [mensaje, setMensaje] = useState("");
  const [planMinimo, setPlanMinimo] = useState("");
  const [pais, setPais] = useState("");
  const [resultado, setResultado] = useState<string | null>(null);

  async function enviarBroadcast() {
    setResultado("Enviando...");
    try {
      await apiClient.post("/admin/broadcast", {
        mensaje,
        plan_minimo: planMinimo || undefined,
        pais: pais || undefined,
        silent: true,
      });
      setResultado("Encolado correctamente.");
      setMensaje("");
    } catch (e: any) {
      setResultado(`Error: ${e?.response?.data?.detail || e.message}`);
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Operaciones</h1>

      <div className="card space-y-2">
        <h2 className="font-semibold">Broadcast a usuarios</h2>
        <textarea
          className="input w-full h-32"
          placeholder="Mensaje HTML al usuario..."
          value={mensaje}
          onChange={(e) => setMensaje(e.target.value)}
        />
        <div className="flex gap-2">
          <select
            className="input"
            value={planMinimo}
            onChange={(e) => setPlanMinimo(e.target.value)}
          >
            <option value="">Todos los planes</option>
            <option value="starter">Starter+</option>
            <option value="pro">Pro+</option>
            <option value="elite">Elite+</option>
          </select>
          <input
            className="input"
            placeholder="pais (ej: CO)"
            value={pais}
            onChange={(e) => setPais(e.target.value)}
          />
          <button
            className="btn-danger"
            onClick={enviarBroadcast}
            disabled={!mensaje}
          >
            Enviar broadcast
          </button>
        </div>
        {resultado && <p className="text-sm">{resultado}</p>}
      </div>

      <div className="card text-sm text-slate-500">
        <p>Aqui irian editor de copies de escalation, kill switch global, etc. (V2.1)</p>
      </div>
    </div>
  );
}
