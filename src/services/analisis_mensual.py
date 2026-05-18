"""Genera PDF de analisis mensual del usuario usando fpdf2 + LLM.

Compone una narrativa basada en datos del mes (entrenos, comidas, sueno, peso)
y devuelve un PDF bytes listo para enviar via Telegram send_document.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from io import BytesIO
from typing import Optional

from openai import AsyncOpenAI
from sqlalchemy import func, select

from src.config import settings
from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    MetricaCorporal,
    MetricaSueno,
    PersonalRecord,
    SesionEntrenamiento,
    Usuario,
)

logger = logging.getLogger(__name__)

_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    return _client


async def _datos_del_mes(telegram_id: int, ano: int, mes: int) -> dict:
    inicio = date(ano, mes, 1)
    if mes == 12:
        fin = date(ano + 1, 1, 1)
    else:
        fin = date(ano, mes + 1, 1)
    async with async_session_factory() as session:
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == telegram_id)
        )
        usuario = user_q.scalar_one_or_none()
        if usuario is None:
            return {}

        sesiones_q = await session.execute(
            select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == usuario.id,
                SesionEntrenamiento.fecha >= inicio,
                SesionEntrenamiento.fecha < fin,
            )
        )
        sesiones = list(sesiones_q.scalars().all())

        comidas_q = await session.execute(
            select(
                func.count(Comida.id),
                func.avg(Comida.calorias),
                func.avg(Comida.proteinas_g),
            ).where(
                Comida.usuario_id == usuario.id,
                Comida.fecha >= inicio,
                Comida.fecha < fin,
            )
        )
        n_com, avg_kcal, avg_prot = comidas_q.one()

        sueno_q = await session.execute(
            select(
                func.count(MetricaSueno.id),
                func.avg(MetricaSueno.horas),
                func.avg(MetricaSueno.calidad),
            ).where(
                MetricaSueno.usuario_id == usuario.id,
                MetricaSueno.fecha >= inicio,
                MetricaSueno.fecha < fin,
            )
        )
        n_su, avg_h, avg_cal = sueno_q.one()

        peso_q = await session.execute(
            select(MetricaCorporal)
            .where(
                MetricaCorporal.usuario_id == usuario.id,
                MetricaCorporal.fecha >= inicio,
                MetricaCorporal.fecha < fin,
            )
            .order_by(MetricaCorporal.fecha)
        )
        pesos = list(peso_q.scalars().all())
        peso_inicio = pesos[0].peso_kg if pesos else None
        peso_fin = pesos[-1].peso_kg if pesos else None

        prs_q = await session.execute(
            select(PersonalRecord).where(
                PersonalRecord.usuario_id == usuario.id,
                PersonalRecord.fecha >= inicio,
                PersonalRecord.fecha < fin,
            )
        )
        prs = list(prs_q.scalars().all())

    return {
        "nombre": usuario.nombre or "atleta",
        "objetivo": usuario.objetivo or "—",
        "tono": usuario.tono.value if usuario.tono else "firme",
        "periodo": f"{inicio.isoformat()} a {(fin).isoformat()}",
        "n_entrenos": len(sesiones),
        "dias_entrenados": len({s.fecha for s in sesiones}),
        "minutos_total": sum(s.duracion_min or 0 for s in sesiones),
        "comidas_registradas": n_com or 0,
        "kcal_promedio": int(avg_kcal or 0),
        "proteina_promedio_g": float(avg_prot or 0),
        "noches_registradas": n_su or 0,
        "horas_sueno_promedio": float(avg_h or 0),
        "calidad_sueno_promedio": float(avg_cal or 0),
        "peso_inicio": peso_inicio,
        "peso_fin": peso_fin,
        "delta_peso": (peso_fin - peso_inicio) if peso_inicio and peso_fin else None,
        "n_prs_nuevos": len(prs),
        "prs_nuevos": [
            {"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps}
            for p in prs
        ],
    }


PROMPT_NARRATIVA = (
    "Eres EntrenadorAX. Escribe una narrativa breve (3 secciones cortas) sobre el mes "
    "del atleta basada en los datos JSON. Tono firme pero empatico. Sin shaming. "
    "Secciones:\n"
    "1) Highlights (3 bullets concretos con numeros)\n"
    "2) Adherencia (que falto, que sobro)\n"
    "3) Recomendacion para el proximo mes (3 acciones concretas)\n"
    "Devuelve texto plano. Max 350 palabras."
)


async def _generar_narrativa(datos: dict) -> str:
    try:
        response = await _get_client().chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": PROMPT_NARRATIVA},
                {"role": "user", "content": json.dumps(datos, ensure_ascii=False)},
            ],
            max_tokens=600,
            temperature=0.5,
        )
        return response.choices[0].message.content or ""
    except Exception:
        logger.exception("Error generando narrativa mensual")
        return "Resumen mensual no disponible por error temporal."


def _render_pdf(datos: dict, narrativa: str, ano: int, mes: int) -> bytes:
    """Genera PDF simple con datos + narrativa. Usa fpdf2."""
    try:
        from fpdf import FPDF
    except ImportError:
        logger.error("fpdf2 no instalado. Instala con: pip install fpdf2")
        return b""

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, f"Tu mes en EntrenadorAX", ln=True)
    pdf.set_font("Helvetica", "", 12)
    pdf.cell(0, 8, f"{datos.get('nombre', '?')} - {mes:02d}/{ano}", ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Resumen ejecutivo", ln=True)
    pdf.set_font("Helvetica", "", 11)
    delta_peso = datos.get("delta_peso")
    delta_str = (
        f"{delta_peso:+.1f} kg" if delta_peso is not None else "sin medidas"
    )
    resumen = [
        f"Entrenos: {datos.get('n_entrenos', 0)} sesiones, {datos.get('dias_entrenados', 0)} dias activos.",
        f"Minutos entrenados: {datos.get('minutos_total', 0)} min.",
        f"Cambio de peso: {delta_str}.",
        f"Sueno promedio: {datos.get('horas_sueno_promedio', 0):.1f}h (calidad {datos.get('calidad_sueno_promedio', 0):.1f}/5).",
        f"Comidas registradas: {datos.get('comidas_registradas', 0)} (kcal promedio {datos.get('kcal_promedio', 0)}).",
        f"Nuevos PRs: {datos.get('n_prs_nuevos', 0)}.",
    ]
    for r in resumen:
        pdf.cell(0, 6, r.encode("latin-1", "ignore").decode("latin-1"), ln=True)
    pdf.ln(4)

    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "Analisis del mes", ln=True)
    pdf.set_font("Helvetica", "", 11)
    safe_narrativa = narrativa.encode("latin-1", "ignore").decode("latin-1")
    pdf.multi_cell(0, 6, safe_narrativa)
    pdf.ln(4)

    if datos.get("prs_nuevos"):
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "Nuevos PRs", ln=True)
        pdf.set_font("Helvetica", "", 11)
        for pr in datos["prs_nuevos"][:10]:
            line = f"- {pr['ejercicio']}: {pr['peso_kg']}kg x{pr['reps']}"
            pdf.cell(0, 6, line.encode("latin-1", "ignore").decode("latin-1"), ln=True)

    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(
        0,
        6,
        f"Generado por EntrenadorAX el {datetime.utcnow().date().isoformat()}",
        ln=True,
    )

    out = pdf.output(dest="S")
    if isinstance(out, str):
        return out.encode("latin-1")
    return bytes(out)


async def generar_pdf_mensual(telegram_id: int, ano: int, mes: int) -> bytes:
    """Genera el PDF mensual completo (datos + narrativa LLM)."""
    datos = await _datos_del_mes(telegram_id, ano, mes)
    if not datos:
        return b""
    narrativa = await _generar_narrativa(datos)
    return _render_pdf(datos, narrativa, ano, mes)
