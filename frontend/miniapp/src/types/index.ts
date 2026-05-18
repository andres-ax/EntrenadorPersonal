export interface Perfil {
  telegram_id: number;
  nombre: string | null;
  edad: number | null;
  peso_kg: number | null;
  altura_cm: number | null;
  objetivo: string | null;
  nivel: string | null;
  deporte_principal: string | null;
  tono: string;
  onboarding_completo: boolean;
}

export interface DashboardData {
  reporte_semanal: {
    dias_entrenados: number;
    volumen_total_kg: number;
    total_ejercicios: number;
    nuevos_prs: Array<{ ejercicio: string; peso_kg: number; reps: number }>;
    sueno: { promedio_horas: number; promedio_calidad: number; dias_registrados: number };
    periodo: string;
  };
  streak_entreno: {
    dias_actuales: number;
    max_historico: number;
    freezes_disponibles: number;
  };
  nutricion_hoy: {
    total_calorias: number;
    total_proteinas: number;
    total_carbs: number;
    total_grasas: number;
  };
  peso_recientes: Array<{ fecha: string; peso_kg: number }>;
}

export interface PR {
  ejercicio: string;
  peso_kg: number;
  reps: number;
}

export interface PlanInfo {
  plan: string;
  mensual_cop: number;
  mensual_formato: string;
  anual_cop: number;
  anual_formato: string | null;
  lifetime_cop: number;
  lifetime_formato: string | null;
  descripcion: string;
}

export interface PreciosResponse {
  planes: PlanInfo[];
  descuento_anual_pct: number;
  cupos_lifetime_total: number;
}
