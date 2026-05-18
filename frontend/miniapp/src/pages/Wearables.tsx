import { useEffect, useState } from "react";
import { apiClient } from "../lib/api";
import { getTg } from "../lib/telegram";

interface IntegracionInfo {
  proveedor: string;
  conectado: boolean;
  last_sync_at: string | null;
  status: string;
  oauth_url?: string;
}

interface ListResp {
  integraciones: IntegracionInfo[];
  proveedores_disponibles: string[];
}

export function Wearables() {
  const [data, setData] = useState<ListResp | null>(null);
  const [loading, setLoading] = useState(false);

  function cargar() {
    apiClient
      .get<ListResp>("/api/me/wearables")
      .then((r) => setData(r.data))
      .catch(console.error);
  }

  useEffect(cargar, []);

  async function conectar(prov: string) {
    setLoading(true);
    try {
      const { data: r } = await apiClient.post<{ url: string }>(
        `/api/me/wearables/${prov}/connect`
      );
      const tg = getTg();
      if (tg) tg.openLink(r.url);
      else window.open(r.url, "_blank");
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  async function sincronizar(prov: string) {
    setLoading(true);
    try {
      await apiClient.post(`/api/me/wearables/${prov}/sync`);
      cargar();
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-3">
      <h1 className="text-2xl font-bold">Wearables</h1>
      <p className="text-sm text-slate-500">
        Conecta tu Whoop, Garmin, Strava o Google Fit y los entrenos se importan
        automaticamente.
      </p>
      {!data && <p>Cargando...</p>}
      {data &&
        data.proveedores_disponibles.map((prov) => {
          const conectado = data.integraciones.find((i) => i.proveedor === prov);
          return (
            <div key={prov} className="card flex items-center justify-between">
              <div>
                <h3 className="capitalize font-semibold">{prov}</h3>
                {conectado ? (
                  <p className="text-xs text-slate-500">
                    Ultimo sync:{" "}
                    {conectado.last_sync_at
                      ? new Date(conectado.last_sync_at).toLocaleString()
                      : "—"}
                  </p>
                ) : (
                  <p className="text-xs text-slate-400">No conectado</p>
                )}
              </div>
              {conectado ? (
                <button
                  className="btn-secondary"
                  onClick={() => sincronizar(prov)}
                  disabled={loading}
                >
                  Sincronizar
                </button>
              ) : (
                <button
                  className="btn-primary"
                  onClick={() => conectar(prov)}
                  disabled={loading}
                >
                  Conectar
                </button>
              )}
            </div>
          );
        })}
    </div>
  );
}
