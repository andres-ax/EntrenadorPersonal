import { useEffect, useState } from "react";
import { apiClient } from "../lib/api";
import type { PR } from "../types";

interface PRsResp {
  prs: PR[];
}

export function PRs() {
  const [prs, setPrs] = useState<PR[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiClient
      .get<PRsResp>("/api/me/prs")
      .then((r) => setPrs(r.data.prs))
      .catch(() => setError("No pude cargar tus PRs"));
  }, []);

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Personal Records</h1>
      {error && <p className="text-red-600">{error}</p>}
      {prs.length === 0 ? (
        <p className="text-slate-500">Aun no tienes PRs registrados.</p>
      ) : (
        <ul className="space-y-2">
          {prs.map((pr, i) => (
            <li key={i} className="card flex items-center justify-between">
              <span className="font-semibold">{pr.ejercicio}</span>
              <span className="text-teal-600">
                {pr.peso_kg}kg x{pr.reps}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
