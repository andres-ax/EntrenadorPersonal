"""Charts en PNG via matplotlib headless. Devuelven BytesIO listo para sendPhoto."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from src.db.repository import (
    historial_peso,  # noqa: E402
    obtener_ultimas_sesiones,
    reporte_semanal,
    resumen_nutricional_dia,
)

logger = logging.getLogger(__name__)

plt.rcParams["figure.figsize"] = (8, 4)
plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False


def _to_png(fig) -> BytesIO:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf


async def chart_peso(telegram_id: int, limit: int = 30) -> BytesIO | None:
    """Linea de peso historico. Devuelve None si no hay datos."""
    try:
        registros = await historial_peso(telegram_id, limit)
        if not registros:
            return None
        registros = sorted(registros, key=lambda r: r.fecha)
        fechas = [r.fecha for r in registros]
        pesos = [r.peso_kg for r in registros if r.peso_kg]
        fechas = fechas[: len(pesos)]
        fig, ax = plt.subplots()
        ax.plot(fechas, pesos, marker="o", linewidth=2)
        ax.set_title("Peso historico")
        ax.set_ylabel("kg")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        fig.autofmt_xdate()
        return _to_png(fig)
    except Exception:
        logger.exception("Error chart_peso uid=%s", telegram_id)
        return None


async def chart_volumen_semanal(telegram_id: int) -> BytesIO | None:
    """Barras de volumen semanal (ultimas 8 semanas)."""
    try:
        sesiones = await obtener_ultimas_sesiones(telegram_id, limite=200)
        if not sesiones:
            return None
        hoy = date.today()
        semanas: dict[int, float] = {}
        for s in sesiones:
            if (hoy - s.fecha).days > 56:
                continue
            iso = s.fecha.isocalendar()
            key = (iso[0], iso[1])
            volumen = sum(
                (e.peso_kg or 0) * (e.series or 0) * (e.reps or 0) for e in s.ejercicios
            )
            semanas[key] = semanas.get(key, 0) + volumen
        if not semanas:
            return None
        keys = sorted(semanas.keys())
        labels = [f"S{k[1]}" for k in keys]
        valores = [semanas[k] for k in keys]
        fig, ax = plt.subplots()
        ax.bar(labels, valores)
        ax.set_title("Volumen semanal (kg)")
        ax.set_ylabel("kg")
        ax.grid(True, axis="y", alpha=0.3)
        return _to_png(fig)
    except Exception:
        logger.exception("Error chart_volumen_semanal uid=%s", telegram_id)
        return None


async def chart_macros_dia(
    telegram_id: int, fecha: date | None = None
) -> BytesIO | None:
    """Pie chart de macros del dia."""
    try:
        resumen = await resumen_nutricional_dia(telegram_id, fecha)
        prot = resumen.get("total_proteinas", 0) or 0
        carb = resumen.get("total_carbs", 0) or 0
        grasa = resumen.get("total_grasas", 0) or 0
        if (prot + carb + grasa) <= 0:
            return None
        labels = [f"Proteina {prot:.0f}g", f"Carbs {carb:.0f}g", f"Grasa {grasa:.0f}g"]
        sizes = [prot * 4, carb * 4, grasa * 9]
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.pie(sizes, labels=labels, autopct="%1.0f%%", startangle=90)
        ax.set_title(f"Macros del dia ({resumen.get('total_calorias', 0)} kcal)")
        return _to_png(fig)
    except Exception:
        logger.exception("Error chart_macros uid=%s", telegram_id)
        return None


async def chart_streak_calendario(telegram_id: int, dias: int = 84) -> BytesIO | None:
    """GitHub-style heatmap: cada dia con entreno = celda llena, sin entreno = vacia."""
    try:
        sesiones = await obtener_ultimas_sesiones(telegram_id, limite=200)
        if not sesiones:
            return None
        fechas_entrenadas = {s.fecha for s in sesiones}
        hoy = date.today()
        dias_atras = [hoy - timedelta(days=i) for i in range(dias - 1, -1, -1)]
        cells = [1 if d in fechas_entrenadas else 0 for d in dias_atras]
        weeks = dias // 7
        cells = cells[: weeks * 7]
        grid = [cells[i * 7 : (i + 1) * 7] for i in range(weeks)]
        transposed = [[grid[w][d] for w in range(weeks)] for d in range(7)]
        fig, ax = plt.subplots(figsize=(weeks * 0.3, 2))
        ax.imshow(transposed, aspect="auto", cmap="Greens", vmin=0, vmax=1)
        ax.set_yticks(range(7))
        ax.set_yticklabels(["L", "M", "X", "J", "V", "S", "D"])
        ax.set_xticks([])
        ax.set_title(f"Adherencia entreno ({weeks} semanas)")
        return _to_png(fig)
    except Exception:
        logger.exception("Error chart_streak uid=%s", telegram_id)
        return None


async def chart_reporte_semanal(telegram_id: int) -> BytesIO | None:
    """Cards visuales del reporte semanal: dias entrenados, volumen, PRs, sueno."""
    try:
        r = await reporte_semanal(telegram_id)
        fig, axes = plt.subplots(1, 4, figsize=(10, 2.5))
        valores = [
            ("Dias", r.get("dias_entrenados", 0)),
            ("Vol kg", int(r.get("volumen_total_kg", 0))),
            ("PRs", len(r.get("nuevos_prs", []))),
            ("Sueno h", r.get("sueno", {}).get("promedio_horas", 0)),
        ]
        for ax, (label, valor) in zip(axes, valores):
            ax.text(
                0.5,
                0.6,
                str(valor),
                ha="center",
                va="center",
                fontsize=22,
                fontweight="bold",
            )
            ax.text(0.5, 0.25, label, ha="center", va="center", fontsize=10)
            ax.axis("off")
        fig.suptitle("Resumen semanal", fontsize=12)
        return _to_png(fig)
    except Exception:
        logger.exception("Error chart_reporte_semanal uid=%s", telegram_id)
        return None
