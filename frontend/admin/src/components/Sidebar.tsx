"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { getAdminEmail, getAdminRol, isAuthed, logout } from "@/lib/api";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/usuarios", label: "Usuarios" },
  { href: "/pagos", label: "Pagos" },
  { href: "/crisis", label: "Crisis" },
  { href: "/finanzas", label: "Finanzas" },
  { href: "/operaciones", label: "Operaciones" },
  { href: "/admins", label: "Admins", soloSuper: true },
];

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState("");

  useEffect(() => {
    setEmail(getAdminEmail());
    setRol(getAdminRol());
    if (!isAuthed() && pathname !== "/login") {
      router.push("/login");
    }
  }, [pathname, router]);

  if (pathname === "/login") return null;

  return (
    <aside className="w-56 bg-slate-900 text-white flex flex-col">
      <div className="p-4 border-b border-slate-700">
        <h1 className="text-lg font-bold">EntrenadorAX</h1>
        <p className="text-xs text-slate-400">Admin</p>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {NAV.filter((n) => !n.soloSuper || rol === "super").map((n) => {
          const active = pathname === n.href || (n.href !== "/" && pathname.startsWith(n.href));
          return (
            <Link
              key={n.href}
              href={n.href}
              className={`block rounded px-3 py-2 text-sm ${
                active ? "bg-teal-600" : "hover:bg-slate-800"
              }`}
            >
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-slate-700 text-xs">
        <p>{email}</p>
        <p className="text-slate-400">{rol}</p>
        <button onClick={logout} className="mt-2 text-red-400 underline">
          Cerrar sesion
        </button>
      </div>
    </aside>
  );
}
