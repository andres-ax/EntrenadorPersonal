"""Plan generator semanal con LLM estructurado.

Genera un plan basado en perfil del usuario (nivel, dias disponibles, deporte,
objetivo, lesiones). Persiste en tabla planes_semanales.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.config import settings
from src.db.repository import log_llm_usage, obtener_usuario

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


class EjercicioPlan(BaseModel):
    nombre: str
    series: int
    reps_min: int
    reps_max: int
    rpe_objetivo: float
    descanso_seg: int


class DiaPlan(BaseModel):
    dia_semana: int
    tipo: str
    duracion_min: int
    ejercicios: list[EjercicioPlan]


class PlanSemanal(BaseModel):
    semana_inicio: str
    dias: list[DiaPlan]
    volumen_total: int
    deload: bool = False


PROMPT_PLAN = (
    "Eres un coach NSCA-CSCS senior. Genera un plan semanal estructurado "
    "respetando rangos cientificos de Schoenfeld 2017: principiante 8-12 sets/musculo/sem, "
    "intermedio 12-18, avanzado 16-22. Maximo 6 dias/semana. "
    "Devuelve SOLO JSON con la forma: "
    '{"semana_inicio": "YYYY-MM-DD", "dias": [{"dia_semana": 0-6, "tipo": "fuerza|cardio|movilidad", '
    '"duracion_min": int, "ejercicios": [{"nombre": str, "series": int, "reps_min": int, '
    '"reps_max": int, "rpe_objetivo": float, "descanso_seg": int}]}], "volumen_total": int, "deload": bool}'
)


async def generar_plan_semanal_para(telegram_id: int) -> dict:
    """Llama LLM para generar plan semanal estructurado.

    Returns:
        dict con la forma PlanSemanal (validado pydantic).

    """
    user = await obtener_usuario(telegram_id)
    if user is None:
        raise ValueError("Usuario no existe")

    perfil = {
        "objetivo": user.objetivo or "mantenerse",
        "nivel": user.nivel or "principiante",
        "dias_entreno": user.dias_entreno or 3,
        "deporte_principal": user.deporte_principal or "gimnasio",
        "peso_kg": user.peso_kg,
        "altura_cm": user.altura_cm,
    }
    inicio_semana = date.today() + timedelta(days=(7 - date.today().weekday()) % 7)

    user_msg = (
        f"Perfil del atleta: {json.dumps(perfil, ensure_ascii=False)}. "
        f"Genera el plan para la semana del {inicio_semana.isoformat()}."
    )

    try:
        response = await _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PROMPT_PLAN},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            max_tokens=2000,
            temperature=0.4,
        )
        if response.usage:
            try:
                await log_llm_usage(
                    telegram_id,
                    "plan",
                    "gpt-4o-mini",
                    response.usage.prompt_tokens,
                    response.usage.completion_tokens,
                )
            except Exception:
                pass
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception:
        logger.exception("Error generando plan uid=%s", telegram_id)
        return {
            "semana_inicio": inicio_semana.isoformat(),
            "dias": [],
            "volumen_total": 0,
            "deload": False,
            "error": "no_pude_generar",
        }
    try:
        plan = PlanSemanal.model_validate(data)
        return plan.model_dump()
    except Exception:
        logger.exception("Plan invalido devuelto por LLM uid=%s", telegram_id)
        return data
