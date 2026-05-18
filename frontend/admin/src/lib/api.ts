"use client";

import axios, { AxiosInstance } from "axios";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "https://api.entrenadorax.com";

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 20000,
});

apiClient.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("admin_jwt");
    if (token) config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err?.response?.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("admin_jwt");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

export interface LoginResp {
  jwt: string;
  admin_id: number;
  email: string;
  rol: string;
  expira_en: number;
}

export async function loginAdmin(email: string, password: string): Promise<LoginResp> {
  const { data } = await apiClient.post<LoginResp>("/admin/auth/login", {
    email,
    password,
  });
  if (typeof window !== "undefined") {
    localStorage.setItem("admin_jwt", data.jwt);
    localStorage.setItem("admin_email", data.email);
    localStorage.setItem("admin_rol", data.rol);
  }
  return data;
}

export function logout() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("admin_jwt");
    localStorage.removeItem("admin_email");
    localStorage.removeItem("admin_rol");
    window.location.href = "/login";
  }
}

export function getAdminEmail(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("admin_email") || "";
}

export function getAdminRol(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("admin_rol") || "";
}

export function isAuthed(): boolean {
  if (typeof window === "undefined") return false;
  return !!localStorage.getItem("admin_jwt");
}
