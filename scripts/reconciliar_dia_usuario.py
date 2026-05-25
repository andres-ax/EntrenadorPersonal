"""Reconciliar datos basura de un usuario para una fecha especifica.

Caso de uso: durante el dia, antes de los fixes de validacion dura, el coach
registro comidas duplicadas/vacias y sesiones de entrenamiento repetidas
(una por cada mensaje del usuario). Este script consolida todo a un estado
limpio basandose en lo que sabemos de la conversacion real.

Uso:
    # Dry run (por defecto): muestra lo que haria sin tocar nada.
    python scripts/reconciliar_dia_usuario.py --uid 8324604749 --fecha 2026-05-18

    # Aplicar cambios:
    python scripts/reconciliar_dia_usuario.py --uid 8324604749 --fecha 2026-05-18 --apply

Hace para cada (uid, fecha):
- Comidas:
    * Borra comidas con alimentos=[] (claramente placeholder de pregunta).
    * Detecta y borra duplicados (mismo tipo + alimentos solapados >=50%),
      conservando la fila con calorias>0; si todas estan en 0, conserva la
      mas reciente.
    * Comidas con kcal=0 pero alimentos no vacios:
        - Si esta dentro de un grupo con duplicado-con-datos, borra la
          vacia.
        - Si esta huerfana (no hay version con datos), la deja como esta
          (el coach puede pedirselas).
- Sesiones de entrenamiento:
    * Si hay >1 sesion del mismo deporte el mismo dia, las consolida en
      la primera (la mas antigua): max(duracion), suma de trucos/caidas,
      ultima sensacion, concatena notas, y borra el resto.
    * Marca la consolidada como cerrada=True.
- Backup en tabla `reconciliacion_backup` (creada si no existe) con la fila
  original antes de borrar/actualizar.

Idempotente: si se ejecuta dos veces, la segunda no hace nada (no quedan
duplicados ni placeholders).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text, update  # noqa: E402

from src.db.connection import async_session_factory  # noqa: E402
from src.db.models import Comida, SesionEntrenamiento, Usuario  # noqa: E402
from src.db.repository import _alimentos_set, incrementar_streak  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
# Silencia el eco de SQLAlchemy que en dev sale por config (echo=true).
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.pool").setLevel(logging.WARNING)
log = logging.getLogger("reconciliar")


# ============================================================================
# Backup
# ============================================================================


CREATE_BACKUP_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS reconciliacion_backup (
    id BIGSERIAL PRIMARY KEY,
    ejecutado_en TIMESTAMP NOT NULL DEFAULT NOW(),
    telegram_id BIGINT NOT NULL,
    fecha DATE,
    tabla_origen VARCHAR(64) NOT NULL,
    fila_id BIGINT NOT NULL,
    accion VARCHAR(32) NOT NULL,
    payload JSONB
)
"""


async def _ensure_backup_table(session) -> None:
    await session.execute(text(CREATE_BACKUP_TABLE_SQL))


async def _backup_row(
    session,
    telegram_id: int,
    fecha: date | None,
    tabla: str,
    fila_id: int,
    accion: str,
    payload: dict,
) -> None:
    await session.execute(
        text(
            "INSERT INTO reconciliacion_backup "
            "(telegram_id, fecha, tabla_origen, fila_id, accion, payload) "
            "VALUES (:tg, :f, :t, :id, :a, CAST(:p AS JSONB))"
        ),
        {
            "tg": telegram_id,
            "f": fecha,
            "t": tabla,
            "id": fila_id,
            "a": accion,
            "p": json.dumps(payload, default=str),
        },
    )


def _comida_a_dict(c: Comida) -> dict:
    return {
        "id": c.id,
        "usuario_id": c.usuario_id,
        "fecha": str(c.fecha) if c.fecha else None,
        "tipo": c.tipo.value if c.tipo else None,
        "alimentos": c.alimentos,
        "calorias": c.calorias,
        "proteinas_g": c.proteinas_g,
        "carbohidratos_g": c.carbohidratos_g,
        "grasas_g": c.grasas_g,
    }


def _sesion_a_dict(s: SesionEntrenamiento) -> dict:
    return {
        "id": s.id,
        "usuario_id": s.usuario_id,
        "fecha": str(s.fecha) if s.fecha else None,
        "tipo": s.tipo.value if s.tipo else None,
        "subtipo": s.subtipo.value if s.subtipo else None,
        "deporte_slug": s.deporte_slug,
        "duracion_min": s.duracion_min,
        "trucos_intentados": s.trucos_intentados,
        "trucos_aterrizados": s.trucos_aterrizados,
        "num_caidas": s.num_caidas,
        "sensacion_1_5": s.sensacion_1_5,
        "foco_sesion": s.foco_sesion,
        "spot": s.spot,
        "notas": s.notas,
        "cerrada": s.cerrada,
        "updated_at": str(s.updated_at) if s.updated_at else None,
    }


# ============================================================================
# Logica de reconciliacion: COMIDAS
# ============================================================================


def _comida_tiene_macros(c: Comida) -> bool:
    return (c.calorias or 0) > 0 or (
        (c.proteinas_g or 0) + (c.carbohidratos_g or 0) + (c.grasas_g or 0) > 0
    )


def _alimentos_vacios(c: Comida) -> bool:
    return not _alimentos_set(c.alimentos)


# Palabras vacias en strings de alimentos. Ignoramos cantidades, articulos y
# modificadores para que "2 huevos cocidos" y "huevo" se consideren mismo
# alimento.
_STOPWORDS_ALIMENTO = {
    "de",
    "del",
    "la",
    "las",
    "el",
    "los",
    "un",
    "una",
    "unos",
    "unas",
    "con",
    "sin",
    "y",
    "o",
    "al",
    "a",
    "en",
    "para",
    "por",
    "vaso",
    "vasos",
    "plato",
    "platos",
    "porcion",
    "porciones",
    "porción",
    "porciones",
    "taza",
    "tazas",
    "cucharada",
    "cucharadas",
    "cucharadita",
    "cucharaditas",
    "medio",
    "media",
    "medios",
    "medias",
    "pequeño",
    "pequena",
    "pequeño",
    "pequeña",
    "grande",
    "grandes",
    "cocido",
    "cocida",
    "cocidos",
    "cocidas",
    "frito",
    "frita",
    "fritos",
    "fritas",
    "hervido",
    "hervida",
    "hervidos",
    "hervidas",
    "crudo",
    "cruda",
    "crudos",
    "crudas",
    "a",
    "al",
    "la",
    "horno",
    "plancha",
    "casero",
    "casera",
}


def _stem_alimento(token: str) -> str:
    """Lematizacion ligera: normaliza plurales y diminutivos comunes."""
    t = token.lower().strip()
    # Quita acentos manualmente sobre vocales comunes.
    t = (
        t.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    if len(t) < 4:
        return t
    # plural -> singular
    if t.endswith("ces"):
        t = t[:-3] + "z"
    elif t.endswith("es"):
        t = t[:-2]
    elif t.endswith("s"):
        t = t[:-1]
    # diminutivos comunes: "pedacito" -> "pedaz", "huevito" -> "huev"
    if t.endswith("cito"):
        t = t[:-4]
    elif t.endswith("ito"):
        t = t[:-3]
    return t


def _palabras_clave(alimentos: list[str]) -> set[str]:
    """Extrae set de palabras clave normalizadas de una lista de alimentos.

    Ej: ["2 huevos cocidos", "medio aguacate"] -> {"huev", "aguacat"}
    Ej: ["huevo", "aguacate"] -> {"huev", "aguacat"}
    El set resultante permite que strings literalmente distintos pero
    semanticamente iguales tengan solapamiento alto.
    """
    out: set[str] = set()
    for item in alimentos:
        if not isinstance(item, str):
            continue
        for raw in item.split():
            tok = "".join(ch for ch in raw if ch.isalpha())
            if not tok or len(tok) < 3:
                continue
            stem = _stem_alimento(tok)
            if stem in _STOPWORDS_ALIMENTO:
                continue
            if len(stem) >= 3:
                out.add(stem)
    return out


def _comida_palabras(c: Comida) -> set[str]:
    """Aplica _palabras_clave a los alimentos de una Comida."""
    raw = c.alimentos
    if isinstance(raw, str):
        try:
            lst = json.loads(raw)
        except Exception:
            lst = []
    else:
        lst = raw or []
    return _palabras_clave(lst)


def _solapamiento(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / max(len(a), len(b))


async def reconciliar_comidas(
    session,
    usuario_id: int,
    telegram_id: int,
    fecha: date,
    apply: bool,
) -> tuple[int, int]:
    """Borra placeholders y duplicados de comidas del dia.

    Retorna (n_borradas_placeholder, n_borradas_duplicadas).
    """
    result = await session.execute(
        select(Comida)
        .where(Comida.usuario_id == usuario_id, Comida.fecha == fecha)
        .order_by(Comida.id)
    )
    comidas = list(result.scalars().all())
    if not comidas:
        log.info("comidas: ninguna en %s para uid=%s", fecha, telegram_id)
        return 0, 0

    log.info("comidas: %d filas en %s (uid=%s)", len(comidas), fecha, telegram_id)

    a_borrar_placeholder: list[Comida] = []
    a_borrar_duplicado: list[Comida] = []
    conservadas: list[Comida] = []

    # Paso 1: filas con alimentos=[] siempre son placeholder.
    for c in comidas:
        if _alimentos_vacios(c):
            a_borrar_placeholder.append(c)
        else:
            conservadas.append(c)

    # Paso 2: agrupa conservadas comparando tokens lematizados.
    # "2 huevos cocidos" -> {"huev"} y "huevo" -> {"huev"} se agrupan juntos.
    grupos_consolidados: list[list[Comida]] = []
    for c in conservadas:
        c_pal = _comida_palabras(c)
        c_tipo = c.tipo.value if c.tipo else "otro"
        agrupado = False
        for grupo in grupos_consolidados:
            ref = grupo[0]
            ref_tipo = ref.tipo.value if ref.tipo else "otro"
            if ref_tipo != c_tipo:
                continue
            ref_pal = _comida_palabras(ref)
            if _solapamiento(ref_pal, c_pal) >= 0.5:
                grupo.append(c)
                agrupado = True
                break
        if not agrupado:
            grupos_consolidados.append([c])

    final_conservadas: list[Comida] = []
    for grupo in grupos_consolidados:
        if len(grupo) == 1:
            final_conservadas.append(grupo[0])
            continue
        # Hay duplicados: escoge la fila con macros; si ninguna tiene, la mas
        # reciente (id mayor).
        with_macros = [c for c in grupo if _comida_tiene_macros(c)]
        if with_macros:
            ganadora = max(with_macros, key=lambda c: (c.calorias or 0, c.id))
        else:
            ganadora = max(grupo, key=lambda c: c.id)
        for c in grupo:
            if c.id != ganadora.id:
                a_borrar_duplicado.append(c)
        final_conservadas.append(ganadora)

    # Reporta
    log.info("  placeholder (alimentos=[]): %d", len(a_borrar_placeholder))
    for c in a_borrar_placeholder:
        log.info(
            "    DEL id=%d tipo=%s kcal=%s alim=%r",
            c.id,
            c.tipo.value if c.tipo else "?",
            c.calorias,
            c.alimentos,
        )
    log.info("  duplicados: %d", len(a_borrar_duplicado))
    for c in a_borrar_duplicado:
        log.info(
            "    DEL id=%d tipo=%s kcal=%s alim=%s",
            c.id,
            c.tipo.value if c.tipo else "?",
            c.calorias,
            (c.alimentos or "")[:60],
        )
    log.info("  conservadas finales: %d", len(final_conservadas))
    for c in final_conservadas:
        log.info(
            "    KEEP id=%d tipo=%s kcal=%s P=%s C=%s G=%s alim=%s",
            c.id,
            c.tipo.value if c.tipo else "?",
            c.calorias,
            c.proteinas_g,
            c.carbohidratos_g,
            c.grasas_g,
            (c.alimentos or "")[:80],
        )

    if apply:
        for c in a_borrar_placeholder + a_borrar_duplicado:
            await _backup_row(
                session,
                telegram_id,
                fecha,
                "comidas",
                c.id,
                "delete_reconciliacion",
                _comida_a_dict(c),
            )
        ids = [c.id for c in (a_borrar_placeholder + a_borrar_duplicado)]
        if ids:
            await session.execute(delete(Comida).where(Comida.id.in_(ids)))
            await session.commit()
            log.info("  comidas: %d filas borradas en DB", len(ids))

    return len(a_borrar_placeholder), len(a_borrar_duplicado)


# ============================================================================
# Logica de reconciliacion: SESIONES_ENTRENAMIENTO
# ============================================================================


async def reconciliar_sesiones(
    session,
    usuario_id: int,
    telegram_id: int,
    fecha: date,
    apply: bool,
) -> int:
    """Consolida multiples sesiones del mismo dia+deporte en una sola.

    Retorna numero de filas borradas (las consolidadas se mantienen).
    """
    result = await session.execute(
        select(SesionEntrenamiento)
        .where(
            SesionEntrenamiento.usuario_id == usuario_id,
            SesionEntrenamiento.fecha == fecha,
        )
        .order_by(SesionEntrenamiento.id)
    )
    sesiones = list(result.scalars().all())
    if not sesiones:
        log.info("sesiones: ninguna en %s para uid=%s", fecha, telegram_id)
        return 0

    log.info("sesiones: %d filas en %s (uid=%s)", len(sesiones), fecha, telegram_id)

    # Agrupa por (tipo, deporte_slug or '<sin>')
    grupos: dict[tuple, list[SesionEntrenamiento]] = defaultdict(list)
    for s in sesiones:
        clave = (
            s.tipo.value if s.tipo else "otro",
            s.deporte_slug or "",
        )
        grupos[clave].append(s)

    n_borradas = 0
    for clave, lst in grupos.items():
        if len(lst) <= 1:
            log.info("  grupo %s: 1 sesion (sin cambios)", clave)
            continue
        # Consolidar en la primera (id menor). Mas antigua = la "original".
        ganadora = lst[0]
        descartar = lst[1:]
        max_duracion = max(s.duracion_min or 0 for s in lst)
        suma_intentados = sum(s.trucos_intentados or 0 for s in lst)
        suma_aterrizados = sum(s.trucos_aterrizados or 0 for s in lst)
        suma_caidas = sum(s.num_caidas or 0 for s in lst)
        ultima_sens = next(
            (s.sensacion_1_5 for s in reversed(lst) if s.sensacion_1_5),
            ganadora.sensacion_1_5,
        )
        # Foco: mejor el de la sesion mas detallada (la ultima en general).
        foco = next(
            (s.foco_sesion for s in reversed(lst) if s.foco_sesion),
            ganadora.foco_sesion,
        )
        spot = next((s.spot for s in lst if s.spot), ganadora.spot)
        co_riders = next((s.co_riders for s in lst if s.co_riders), ganadora.co_riders)
        # Notas concatenadas en orden cronologico, deduplicadas.
        notas_chunks: list[str] = []
        vistos: set[str] = set()
        for s in lst:
            if s.notas and s.notas.strip() not in vistos:
                notas_chunks.append(s.notas.strip())
                vistos.add(s.notas.strip())
        notas_final = "\n[+] ".join(notas_chunks) if notas_chunks else None

        log.info(
            "  grupo %s: %d sesiones -> consolidar en id=%d",
            clave,
            len(lst),
            ganadora.id,
        )
        log.info(
            "    KEEP id=%d duracion=%s trucos_int=%s ater=%s caidas=%s sens=%s",
            ganadora.id,
            max_duracion,
            suma_intentados,
            suma_aterrizados,
            suma_caidas,
            ultima_sens,
        )
        for s in descartar:
            log.info(
                "    DEL id=%d duracion=%s notas=%r",
                s.id,
                s.duracion_min,
                (s.notas or "")[:80],
            )

        n_borradas += len(descartar)
        if apply:
            await _backup_row(
                session,
                telegram_id,
                fecha,
                "sesiones_entrenamiento",
                ganadora.id,
                "update_consolidacion",
                _sesion_a_dict(ganadora),
            )
            for s in descartar:
                await _backup_row(
                    session,
                    telegram_id,
                    fecha,
                    "sesiones_entrenamiento",
                    s.id,
                    "delete_consolidacion",
                    _sesion_a_dict(s),
                )
            # Actualiza la ganadora
            await session.execute(
                update(SesionEntrenamiento)
                .where(SesionEntrenamiento.id == ganadora.id)
                .values(
                    duracion_min=max_duracion,
                    trucos_intentados=suma_intentados,
                    trucos_aterrizados=suma_aterrizados,
                    num_caidas=suma_caidas,
                    sensacion_1_5=ultima_sens,
                    foco_sesion=foco,
                    spot=spot,
                    co_riders=co_riders,
                    notas=notas_final,
                    cerrada=True,
                    updated_at=datetime.utcnow(),
                )
            )
            ids_borrar = [s.id for s in descartar]
            await session.execute(
                delete(SesionEntrenamiento).where(SesionEntrenamiento.id.in_(ids_borrar))
            )
            await session.commit()

    return n_borradas


# ============================================================================
# Streaks
# ============================================================================


async def reconciliar_streaks(telegram_id: int, fecha: date, apply: bool) -> None:
    """Asegura streaks=1 para tipos donde haya registros validos del dia.

    Por ejemplo: si Andy registro sueno hoy pero el streak quedo en 0 porque
    el auto-streak no estaba activo cuando se inserto.
    """
    from src.db.models import Comida, MetricaSueno, SesionEntrenamiento
    from src.db.repository import async_session_factory as _asf

    async with _asf() as session:
        u = await session.execute(select(Usuario).where(Usuario.telegram_id == telegram_id))
        usuario = u.scalar_one_or_none()
        if usuario is None:
            log.warning("streaks: usuario no existe uid=%s", telegram_id)
            return

        chequeos = [
            ("entreno", SesionEntrenamiento),
            ("comida", Comida),
            ("sueno", MetricaSueno),
        ]
        for tipo, modelo in chequeos:
            q = await session.execute(
                select(modelo).where(
                    modelo.usuario_id == usuario.id,
                    modelo.fecha == fecha,
                )
            )
            tiene = q.first() is not None
            log.info("  streak %s: registros=%s", tipo, tiene)
            if tiene and apply:
                # incrementar_streak es idempotente por dia (si ultima_fecha
                # == hoy: pass), asi que llamarlo no rompe.
                try:
                    await incrementar_streak(telegram_id, tipo)
                except Exception:
                    log.exception("  streak %s: error incrementando", tipo)


# ============================================================================
# Main
# ============================================================================


async def reconciliar(uid: int, fecha: date, apply: bool) -> None:
    label = "APPLY" if apply else "DRY-RUN"
    log.info("=== Reconciliacion %s uid=%s fecha=%s ===", label, uid, fecha)

    async with async_session_factory() as session:
        if apply:
            await _ensure_backup_table(session)
            await session.commit()

        result = await session.execute(select(Usuario).where(Usuario.telegram_id == uid))
        usuario = result.scalar_one_or_none()
        if usuario is None:
            log.error("uid=%s no existe en usuarios", uid)
            return
        log.info("Usuario encontrado: id_db=%s nombre=%r", usuario.id, usuario.nombre)

        log.info("--- Comidas ---")
        n_ph, n_dup = await reconciliar_comidas(session, usuario.id, uid, fecha, apply)
        log.info("--- Sesiones de entrenamiento ---")
        n_ses = await reconciliar_sesiones(session, usuario.id, uid, fecha, apply)

    log.info("--- Streaks ---")
    await reconciliar_streaks(uid, fecha, apply)

    log.info("=== Resumen %s ===", label)
    log.info("  comidas placeholder borradas: %d", n_ph)
    log.info("  comidas duplicadas borradas: %d", n_dup)
    log.info("  sesiones consolidadas: %d", n_ses)
    if not apply:
        log.info("Dry run completo. Para aplicar, repite con --apply.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reconcilia comidas/sesiones duplicadas o vacias de un usuario."
    )
    parser.add_argument(
        "--uid",
        type=int,
        required=True,
        help="telegram_id del usuario (ej: 8324604749)",
    )
    parser.add_argument(
        "--fecha",
        type=str,
        required=True,
        help="fecha YYYY-MM-DD a reconciliar",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="aplicar cambios. Sin esta flag, solo muestra plan (dry run).",
    )
    args = parser.parse_args()

    try:
        fecha = date.fromisoformat(args.fecha)
    except ValueError:
        log.error("fecha invalida: %s. Usa YYYY-MM-DD", args.fecha)
        sys.exit(1)

    asyncio.run(reconciliar(args.uid, fecha, args.apply))


if __name__ == "__main__":
    main()
