import axios, { AxiosInstance } from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "https://api.entrenadorax.com";

let _jwt: string | null = null;
let _expira: number = 0;

export function setJwt(jwt: string, ttlSeconds: number) {
  _jwt = jwt;
  _expira = Date.now() + ttlSeconds * 1000 - 30_000; // renueva 30s antes
  try {
    sessionStorage.setItem("entax_jwt", jwt);
    sessionStorage.setItem("entax_jwt_expira", String(_expira));
  } catch {}
}

export function getJwt(): string | null {
  if (_jwt && Date.now() < _expira) return _jwt;
  try {
    const stored = sessionStorage.getItem("entax_jwt");
    const expira = Number(sessionStorage.getItem("entax_jwt_expira") || "0");
    if (stored && Date.now() < expira) {
      _jwt = stored;
      _expira = expira;
      return stored;
    }
  } catch {}
  return null;
}

export function jwtExpiringSoon(): boolean {
  return !_jwt || Date.now() > _expira - 5 * 60 * 1000;
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE,
  timeout: 15000,
});

apiClient.interceptors.request.use((config) => {
  const token = getJwt();
  if (token) {
    config.headers.set("Authorization", `Bearer ${token}`);
  }
  return config;
});

apiClient.interceptors.response.use(
  (r) => r,
  async (error) => {
    if (error?.response?.status === 401) {
      _jwt = null;
      _expira = 0;
      try {
        sessionStorage.removeItem("entax_jwt");
      } catch {}
    }
    return Promise.reject(error);
  }
);

export interface InitDataResponse {
  jwt: string;
  uid: number;
  expira_en: number;
}

export async function loginConInitData(initData: string): Promise<InitDataResponse> {
  const { data } = await apiClient.post<InitDataResponse>(
    "/api/auth/initdata",
    { init_data: initData }
  );
  setJwt(data.jwt, data.expira_en);
  return data;
}
