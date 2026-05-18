import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "./providers";
import { Sidebar } from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "EntrenadorAX Admin",
  description: "Panel administrativo",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body>
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-6 overflow-y-auto">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
