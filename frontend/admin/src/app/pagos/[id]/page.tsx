"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api";

interface DetallePago {
  comprobante: any;
  usuario: any;
}

export default function DetallePagoPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const id = params.id;
  const [notas, setNotas] = useState("");
  const [motivo, setMotivo] = useState("");
  const [bloquear, setBloquear] = useState(false);

  const { data } = useQuery({
    queryKey: ["pago", id],
    queryFn: async () =>
      (await apiClient.get<DetallePago>(`/admin/pagos/${id}`)).data,
  });

  const aprobar = useMutation({
    mutationFn: () => apiClient.post(`/admin/pagos/${id}/aprobar`, { notas }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pago", id] });
      router.push("/pagos");
    },
  });

  const rechazar = useMutation({
    mutationFn: () =>
      apiClient.post(`/admin/pagos/${id}/rechazar`, { motivo, bloquear }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["pago", id] });
      router.push("/pagos");
    },
  });

  const [fotoBlob, setFotoBlob] = useState<string | null>(null);

  useEffect(() => {
    if (!data?.comprobante?.foto_file_id) return;
    let cancelled = false;
    apiClient
      .get(`/admin/pagos/${id}/foto`, { responseType: "blob" })
      .then((r) => {
        if (cancelled) return;
        const url = URL.createObjectURL(r.data);
        setFotoBlob(url);
      })
      .catch(() => setFotoBlob(null));
    return () => {
      cancelled = true;
      if (fotoBlob) URL.revokeObjectURL(fotoBlob);
    };
  }, [data?.comprobante?.foto_file_id, id]);

  if (!data) return <p>Cargando...</p>;
  const c = data.comprobante;
  const u = data.usuario;
  const fotoUrl = fotoBlob;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Comprobante #{c.id}</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card">
          <h3 className="font-semibold mb-2">Foto del comprobante</h3>
          {fotoUrl ? (
            <img src={fotoUrl} alt="comprobante" className="w-full border rounded" />
          ) : (
            <p className="text-slate-500">Sin foto (file_id: {c.foto_file_id})</p>
          )}
          <p className="text-xs text-slate-500 mt-2">
            file_id: <code>{c.foto_file_id}</code>
          </p>
        </div>

        <div className="space-y-3">
          <div className="card">
            <h3 className="font-semibold">Datos extraidos por Vision</h3>
            <p>Monto detectado: <b>${c.monto_cop?.toLocaleString("es-CO")}</b></p>
            <p>Monto esperado: <b>${c.monto_esperado_cop?.toLocaleString("es-CO")}</b></p>
            <p className={c.monto_match ? "text-green-600" : "text-red-600"}>
              Match: {c.monto_match ? "SI" : "NO"}
            </p>
            <p>Referencia: <code>{c.referencia}</code></p>
            <p>Cuenta origen: {c.cuenta_origen}</p>
            <p>Cuenta destino: {c.cuenta_destino}</p>
            <p>Fecha pago: {c.fecha_pago?.slice(0, 16)}</p>
            <p>Metodo: {c.metodo}</p>
            <p>Plan solicitado: {c.plan_solicitado} ({c.duracion})</p>
            <p>Estado: <b>{c.estado}</b></p>
          </div>

          <div className="card">
            <h3 className="font-semibold">Usuario</h3>
            <p>{u.nombre} <span className="text-xs">(#{u.telegram_id})</span></p>
            <p>Plan actual: <b>{u.plan_actual}</b></p>
            <p>Pais: {u.pais}</p>
          </div>

          {c.estado === "pendiente_humano" && (
            <>
              <div className="card border-green-200">
                <h3 className="font-semibold text-green-700">Aprobar</h3>
                <textarea
                  className="input w-full"
                  placeholder="notas (opcional)"
                  value={notas}
                  onChange={(e) => setNotas(e.target.value)}
                />
                <button
                  className="btn-primary mt-2"
                  onClick={() => aprobar.mutate()}
                  disabled={aprobar.isPending}
                >
                  Aprobar y activar plan
                </button>
              </div>

              <div className="card border-red-200">
                <h3 className="font-semibold text-red-700">Rechazar</h3>
                <input
                  className="input w-full"
                  placeholder="motivo del rechazo"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                />
                <label className="text-sm flex items-center gap-2 mt-2">
                  <input
                    type="checkbox"
                    checked={bloquear}
                    onChange={(e) => setBloquear(e.target.checked)}
                  />
                  Bloquear usuario (fraude/abuso)
                </label>
                <button
                  className="btn-danger mt-2"
                  onClick={() => motivo && rechazar.mutate()}
                  disabled={rechazar.isPending}
                >
                  Rechazar
                </button>
              </div>
            </>
          )}

          {c.vision_payload && (
            <details className="card">
              <summary className="cursor-pointer text-sm font-semibold">Vision raw payload</summary>
              <pre className="text-xs overflow-x-auto">
                {JSON.stringify(c.vision_payload, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
