"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { apiClient } from "@/lib/api";

interface Admin {
  id: number;
  email: string;
  rol: string;
  activo: boolean;
  created_at: string | null;
  last_login_at: string | null;
}

export default function AdminsPage() {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rol, setRol] = useState("soporte");

  const { data } = useQuery({
    queryKey: ["admins"],
    queryFn: async () =>
      (await apiClient.get<Admin[]>("/admin/admins")).data,
  });

  const crear = useMutation({
    mutationFn: () =>
      apiClient.post("/admin/admins", { email, password, rol }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admins"] });
      setEmail("");
      setPassword("");
    },
  });

  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-bold">Admins</h1>
      <div className="card">
        <h2 className="font-semibold mb-2">Crear admin</h2>
        <div className="flex gap-2">
          <input
            className="input flex-1"
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="input flex-1"
            placeholder="contrasena"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <select className="input" value={rol} onChange={(e) => setRol(e.target.value)}>
            <option value="super">super</option>
            <option value="soporte">soporte</option>
          </select>
          <button
            className="btn-primary"
            onClick={() => email && password && crear.mutate()}
          >
            Crear
          </button>
        </div>
      </div>

      <div className="card">
        <table className="admin">
          <thead>
            <tr>
              <th>Email</th>
              <th>Rol</th>
              <th>Activo</th>
              <th>Ultimo login</th>
            </tr>
          </thead>
          <tbody>
            {data?.map((a) => (
              <tr key={a.id}>
                <td>{a.email}</td>
                <td>{a.rol}</td>
                <td>{a.activo ? "si" : "no"}</td>
                <td className="text-xs">{a.last_login_at?.slice(0, 16) || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
