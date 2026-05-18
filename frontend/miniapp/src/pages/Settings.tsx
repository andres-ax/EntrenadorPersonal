import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiClient } from "../lib/api";
import type { Perfil } from "../types";

export function Settings() {
  const [perfil, setPerfil] = useState<Perfil | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<Perfil>("/api/me/perfil")
      .then((r) => setPerfil(r.data))
      .catch(() => setError("No pude cargar tu perfil"));
  }, []);

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Ajustes</h1>
      {error && <p className="text-red-600">{error}</p>}
      {perfil && (
        <div className="card">
          <p><b>Nombre:</b> {perfil.nombre || "—"}</p>
          <p><b>Tono:</b> {perfil.tono}</p>
          <p><b>Objetivo:</b> {perfil.objetivo || "—"}</p>
          <p><b>Deporte:</b> {perfil.deporte_principal || "—"}</p>
          <p className="mt-2 text-sm text-slate-500">
            Para cambiar tono / quiet hours / idioma usa el bot:
            <br />
            <code>/tono</code>, <code>/quiet_hours HH:MM HH:MM</code>
          </p>
        </div>
      )}
      <Link to="/pagar" className="btn-primary block text-center">
        Mejorar mi plan
      </Link>
      <Link to="/wearables" className="btn-secondary block text-center">
        Conectar wearables
      </Link>
      <Link to="/llamar" className="btn-secondary block text-center">
        Llamar al coach
      </Link>
    </div>
  );
}
