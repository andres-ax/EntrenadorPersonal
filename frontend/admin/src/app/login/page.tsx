"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { loginAdmin } from "@/lib/api";

export default function Login() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await loginAdmin(email, password);
      router.push("/");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Credenciales invalidas");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-slate-900 fixed inset-0">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-3 bg-white">
        <h1 className="text-2xl font-bold">EntrenadorAX Admin</h1>
        {error && <p className="text-red-600 text-sm">{error}</p>}
        <input
          type="email"
          className="input w-full"
          placeholder="admin@entrenadorax.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <input
          type="password"
          className="input w-full"
          placeholder="Contrasena"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <button className="btn-primary w-full" disabled={loading} type="submit">
          {loading ? "Ingresando..." : "Ingresar"}
        </button>
      </form>
    </div>
  );
}
