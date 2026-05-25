"""Endpoints REST para el Mini App. Auth via JWT del initData."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel
from sqlalchemy import func, select

from src.api.auth import get_uid_from_token
from src.db.connection import async_session_factory
from src.db.models import (
    Comida,
    MetricaCorporal,
    MetricaSueno,
    SesionEntrenamiento,
    Usuario,
)
from src.db.repository import (
    actualizar_usuario,
    guardar_comida,
    guardar_metrica_corporal,
    guardar_sesion,
    guardar_sueno,
    historial_peso,
    listar_prs,
    obtener_o_crear_streak,
    obtener_usuario,
    reporte_semanal,
    resumen_nutricional_dia,
    set_quiet_hours,
)
from src.services.charts import (
    chart_macros_dia,
    chart_peso,
    chart_streak_calendario,
    chart_volumen_semanal,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/me", tags=["me"])


@router.get("/perfil")
async def perfil(uid: int = Depends(get_uid_from_token)) -> dict:
    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado")
    return {
        "telegram_id": u.telegram_id,
        "nombre": u.nombre,
        "edad": u.edad,
        "peso_kg": u.peso_kg,
        "altura_cm": u.altura_cm,
        "objetivo": u.objetivo,
        "nivel": u.nivel,
        "deporte_principal": u.deporte_principal,
        "tono": u.tono.value if u.tono else "firme",
        "onboarding_completo": u.onboarding_completo,
    }


@router.get("/dashboard")
async def dashboard(uid: int = Depends(get_uid_from_token)) -> dict:
    reporte = await reporte_semanal(uid)
    streak = await obtener_o_crear_streak(uid, "entreno")
    nutricion = await resumen_nutricional_dia(uid)
    historial = await historial_peso(uid, limit=10)
    return {
        "reporte_semanal": reporte,
        "streak_entreno": {
            "dias_actuales": streak.dias_actuales,
            "max_historico": streak.max_historico,
            "freezes_disponibles": streak.freezes_disponibles,
        },
        "nutricion_hoy": nutricion,
        "peso_recientes": [
            {"fecha": str(r.fecha), "peso_kg": r.peso_kg} for r in historial
        ],
    }


@router.get("/prs")
async def prs(uid: int = Depends(get_uid_from_token)) -> dict:
    items = await listar_prs(uid)
    return {
        "prs": [
            {"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps}
            for p in items
        ]
    }


@router.get("/charts/peso.png")
async def chart_peso_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_peso(uid)
    if img is None:
        return Response(status_code=204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/volumen.png")
async def chart_volumen_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_volumen_semanal(uid)
    if img is None:
        return Response(status_code=204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/macros.png")
async def chart_macros_png(
    uid: int = Depends(get_uid_from_token), fecha: str | None = None
) -> Response:
    fecha_obj = date.fromisoformat(fecha) if fecha else None
    img = await chart_macros_dia(uid, fecha_obj)
    if img is None:
        return Response(status_code=204)
    return Response(content=img.getvalue(), media_type="image/png")


@router.get("/charts/streak.png")
async def chart_streak_png(uid: int = Depends(get_uid_from_token)) -> Response:
    img = await chart_streak_calendario(uid)
    if img is None:
        return Response(status_code=204)
    return Response(content=img.getvalue(), media_type="image/png")


# --- Calendario semanal ---


@router.get("/calendar")
async def calendario(
    uid: int = Depends(get_uid_from_token), semana: str | None = None
) -> dict:
    """Devuelve los 7 dias de la semana con entrenos realizados."""
    inicio = date.today() - timedelta(days=date.today().weekday())
    if semana:
        try:
            ano, num = semana.split("-W")
            ano_i = int(ano)
            num_i = int(num)
            inicio = date.fromisocalendar(ano_i, num_i, 1)
        except (ValueError, IndexError):
            pass

    async with async_session_factory() as session:
        usuario_q = await session.execute(
            select(Usuario.id).where(Usuario.telegram_id == uid)
        )
        usuario_id = usuario_q.scalar_one_or_none()
        if usuario_id is None:
            raise HTTPException(404, "Usuario no encontrado")
        sesiones_q = await session.execute(
            select(SesionEntrenamiento).where(
                SesionEntrenamiento.usuario_id == usuario_id,
                SesionEntrenamiento.fecha >= inicio,
                SesionEntrenamiento.fecha < inicio + timedelta(days=7),
            )
        )
        sesiones = list(sesiones_q.scalars().all())
        by_fecha = {s.fecha: s for s in sesiones}

    dias = []
    for i in range(7):
        f = inicio + timedelta(days=i)
        s = by_fecha.get(f)
        dias.append(
            {
                "fecha": f.isoformat(),
                "realizado": s is not None,
                "planeado": False,
                "tipo": s.tipo.value if s and s.tipo else None,
                "resumen": s.notas if s and s.notas else "",
            }
        )
    return {"semana_inicio": inicio.isoformat(), "dias": dias}


# --- Logs (Mini App envia datos al bot) ---


class LogEntrenoReq(BaseModel):
    fecha: str
    tipo: str = "fuerza"
    duracion_min: int = 60
    ejercicios: list[dict] = []
    rpe: float | None = None
    notas: str = ""


@router.post("/log/entreno")
async def log_entreno(
    req: LogEntrenoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    try:
        sesion = await guardar_sesion(
            telegram_id=uid,
            fecha_str=req.fecha,
            tipo=req.tipo,
            ejercicios=req.ejercicios,
            duracion_min=req.duracion_min,
            rpe=req.rpe,
            notas=req.notas,
        )
        return {"ok": True, "sesion_id": sesion.id}
    except Exception:
        logger.exception("Error log_entreno uid=%s", uid)
        raise HTTPException(400, "Error registrando entreno")


class LogPesoReq(BaseModel):
    peso_kg: float
    grasa_pct: float | None = None
    cintura_cm: float | None = None


@router.post("/log/peso")
async def log_peso(
    req: LogPesoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    m = await guardar_metrica_corporal(
        telegram_id=uid,
        peso_kg=req.peso_kg,
        grasa_pct=req.grasa_pct,
        cintura_cm=req.cintura_cm,
    )
    return {"ok": True, "id": m.id}


class LogComidaReq(BaseModel):
    fecha: str
    tipo: str = "almuerzo"
    alimentos: list[str]
    calorias: int = 0
    proteinas: float = 0
    carbs: float = 0
    grasas: float = 0


@router.post("/log/comida")
async def log_comida(
    req: LogComidaReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    c = await guardar_comida(
        telegram_id=uid,
        fecha_str=req.fecha,
        tipo=req.tipo,
        alimentos=req.alimentos,
        calorias=req.calorias,
        proteinas=req.proteinas,
        carbs=req.carbs,
        grasas=req.grasas,
    )
    return {"ok": True, "id": c.id}


class LogSuenoReq(BaseModel):
    fecha: str
    horas: float
    calidad: int
    notas: str = ""


@router.post("/log/sueno")
async def log_sueno(
    req: LogSuenoReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    s = await guardar_sueno(
        telegram_id=uid,
        fecha_str=req.fecha,
        horas=req.horas,
        calidad=req.calidad,
        notas=req.notas,
    )
    return {"ok": True, "id": s.id}


# --- Settings ---


class SettingsPatchReq(BaseModel):
    tono: str | None = None
    idioma: str | None = None
    pais: str | None = None
    quiet_hours_inicio: str | None = None
    quiet_hours_fin: str | None = None


@router.get("/settings")
async def get_settings(uid: int = Depends(get_uid_from_token)) -> dict:
    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404)
    return {
        "tono": u.tono.value if u.tono else "firme",
        "idioma": u.idioma,
        "pais": u.pais,
        "quiet_hours_inicio": (
            u.quiet_hours_inicio.strftime("%H:%M") if u.quiet_hours_inicio else "22:00"
        ),
        "quiet_hours_fin": (
            u.quiet_hours_fin.strftime("%H:%M") if u.quiet_hours_fin else "07:00"
        ),
        "plan_actual": u.plan_actual.value if u.plan_actual else "free",
        "plan_expira_en": u.plan_expira_en.isoformat() if u.plan_expira_en else None,
    }


@router.patch("/settings")
async def patch_settings(
    req: SettingsPatchReq, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.db.models import TonoCoach

    updates = {}
    if req.tono:
        try:
            updates["tono"] = TonoCoach(req.tono)
        except ValueError:
            raise HTTPException(400, "tono invalido")
    if req.idioma:
        updates["idioma"] = req.idioma[:8]
    if req.pais:
        updates["pais"] = req.pais[:8]
    if updates:
        await actualizar_usuario(uid, **updates)
    if req.quiet_hours_inicio and req.quiet_hours_fin:
        try:
            await set_quiet_hours(uid, req.quiet_hours_inicio, req.quiet_hours_fin)
        except Exception:
            raise HTTPException(400, "quiet_hours invalidas")
    return {"ok": True}


# --- Plan generator stub (real impl en Fase 7) ---


@router.post("/plan/generar")
async def generar_plan(uid: int = Depends(get_uid_from_token)) -> dict:
    """Genera plan semanal con LLM. Requiere Pro o superior."""
    from src.db.models import PlanSuscripcion
    from src.db.repository import es_plan_minimo

    if not await es_plan_minimo(uid, PlanSuscripcion.PRO):
        raise HTTPException(
            402, "Requiere plan Pro o superior. Mejora con /pagar en el bot."
        )
    from src.services.plan_generator import generar_plan_semanal_para

    plan = await generar_plan_semanal_para(uid)
    return {"plan": plan}


# --- Wearables (impl real en Fase 6, devuelve estructura vacia por ahora) ---


@router.get("/wearables")
async def listar_wearables(uid: int = Depends(get_uid_from_token)) -> dict:
    from src.services.wearables import listar_para_usuario, PROVEEDORES_DISPONIBLES

    items = await listar_para_usuario(uid)
    return {
        "integraciones": items,
        "proveedores_disponibles": PROVEEDORES_DISPONIBLES,
    }


@router.post("/wearables/{proveedor}/connect")
async def connect_wearable(
    proveedor: str, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.services.wearables import construir_url_oauth

    url = await construir_url_oauth(uid, proveedor)
    return {"url": url}


@router.post("/wearables/{proveedor}/sync")
async def sync_wearable(
    proveedor: str, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.services.wearables import sync_proveedor

    n = await sync_proveedor(uid, proveedor)
    return {"ok": True, "items_sincronizados": n}


class HealthConnectRecord(BaseModel):
    tipo: str  # "pasos", "sueno", "ritmo_cardiaco", etc.
    external_id: str
    fecha: str  # YYYY-MM-DD
    payload: dict


class HealthConnectSyncReq(BaseModel):
    records: list[HealthConnectRecord]


@router.post("/wearables/health-connect/sync")
async def sync_health_connect(
    req: HealthConnectSyncReq,
    uid: int = Depends(get_uid_from_token)
) -> dict:
    """Recibe lotes de datos biométricos desde Android (Health Connect) y los sincroniza.

    Crea una integración para 'health_connect' si no existe y guarda los registros.
    """
    from src.db.connection import async_session_factory
    from src.db.models import Usuario, IntegracionWearable, DatosWearableRaw
    from datetime import date, datetime
    from sqlalchemy import select

    async with async_session_factory() as session:
        # 1. Obtener usuario
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == uid)
        )
        user = user_q.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuario no encontrado")

        # 2. Buscar o crear IntegracionWearable para "health_connect"
        integracion_q = await session.execute(
            select(IntegracionWearable).where(
                IntegracionWearable.usuario_id == user.id,
                IntegracionWearable.proveedor == "health_connect"
            )
        )
        integracion = integracion_q.scalar_one_or_none()
        if not integracion:
            integracion = IntegracionWearable(
                usuario_id=user.id,
                proveedor="health_connect",
                sync_status="activo"
            )
            session.add(integracion)
            await session.commit()
            await session.refresh(integracion)

        # 3. Guardar lotes de datos
        sincronizados = 0
        for record in req.records:
            # Validar si ya existe el external_id para esta integración
            dup_q = await session.execute(
                select(DatosWearableRaw).where(
                    DatosWearableRaw.integracion_id == integracion.id,
                    DatosWearableRaw.external_id == record.external_id
                )
            )
            dup = dup_q.scalar_one_or_none()
            if dup:
                dup.payload = record.payload
                dup.fecha = date.fromisoformat(record.fecha)
                session.add(dup)
            else:
                nuevo_dato = DatosWearableRaw(
                    integracion_id=integracion.id,
                    tipo=record.tipo[:32],
                    external_id=record.external_id[:120],
                    fecha=date.fromisoformat(record.fecha),
                    payload=record.payload,
                    procesado=False
                )
                session.add(nuevo_dato)
                sincronizados += 1

        integracion.last_sync_at = datetime.utcnow()
        session.add(integracion)
        await session.commit()

    return {"ok": True, "sincronizados": sincronizados}


@router.get("/novedades", response_model=None)
async def novedades(
    request: Request,
    uid: int = Depends(get_uid_from_token),
):
    """Devuelve las novedades de la comunidad.

    Dual: si se solicita application/json retorna datos estructurados,
    de lo contrario renderiza la plantilla HTML para WebView.
    """
    noticias = [
        {
            "id": 1,
            "titulo": "Soporte para Wearables & Health Connect",
            "contenido": "¡Ya puedes sincronizar tus pasos, sueño y ritmo cardíaco directamente desde tu celular Android a través de Health Connect! Nuestro Coach IA analizará estos datos biométricos para darte recomendaciones de entrenamiento súper precisas.",
            "fecha": "Hace 2 días",
            "categoria": "Tecnología"
        },
        {
            "id": 2,
            "titulo": "Mejoras en el Coach IA",
            "contenido": "Hemos optimizado el motor de razonamiento del coach. Ahora entiende mejor la fatiga acumulada basándose en tu RPE (esfuerzo percibido) y ajustará el volumen semanal automáticamente si estás al borde del sobreentrenamiento.",
            "fecha": "Hace 5 días",
            "categoria": "Inteligencia Artificial"
        },
        {
            "id": 3,
            "titulo": "Nuevas voces y tonos para tu Coach",
            "contenido": "Prueba el 'Tono Militar' en la sección de configuración si necesitas un empujón de disciplina pura y dura, o el 'Tono Amigable' si prefieres una guía más empática para tus sesiones.",
            "fecha": "Hace 1 semana",
            "categoria": "Mejoras"
        }
    ]

    desafios = [
        {
            "id": 1,
            "titulo": "Racha de Hidratación Colombiana",
            "descripcion": "Consumir al menos 2L (o 4 termos) de agua al día por 7 días seguidos. ¡Reporta cada termo en el bot!",
            "recompensa": "Insignia de Acuaman / Racha de 7 días",
            "participantes": 1240,
            "activo": True
        },
        {
            "id": 2,
            "titulo": "Semana de Fuerza Pura",
            "descripcion": "Registra un mínimo de 3 entrenos de fuerza (pesas, calistenia, etc.) con RPE >= 7.",
            "recompensa": "Puntos de experiencia multiplicados x1.5",
            "participantes": 850,
            "activo": True
        }
    ]

    comunidad = {
        "records": [
            {"ejercicio": "Sentadilla", "usuario": "@mateo_gym", "peso": "240 kg", "ciudad": "Medellín"},
            {"ejercicio": "Press de Banca", "usuario": "@santiago_fit", "peso": "180 kg", "ciudad": "Bogotá"},
            {"ejercicio": "Peso Muerto", "usuario": "@camila_power", "peso": "210 kg", "ciudad": "Cali"}
        ],
        "total_activos_hoy": 4350,
        "tips_coach": "En climas cálidos como Cali o Barranquilla, aumenta tu ingesta de sodio y potasio si tus entrenos de cardio o fuerza duran más de 60 minutos."
    }

    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header and "text/html" not in accept_header:
        return {
            "noticias": noticias,
            "desafios": desafios,
            "comunidad": comunidad
        }

    from src.web.templates import render
    u = await obtener_usuario(uid)
    return render(
        request,
        "app/novedades.html",
        {
            "user": {"uid": uid, "perfil": u},
            "active": "novedades",
            "page_title": "Novedades & Comunidad",
            "page_subtitle": "Noticias, desafíos y récords activos en Colombia",
            "noticias": noticias,
            "desafios": desafios,
            "comunidad": comunidad,
        }
    )


@router.post("/telegram/pair-token")
async def get_telegram_pair_token(uid: int = Depends(get_uid_from_token)) -> dict:
    """Genera codigo /vincular + deep link temporal para asociar Telegram."""
    from src.db.repository import obtener_usuario
    from src.services.telegram_pair import crear_solicitud_vinculacion

    user = await obtener_usuario(uid)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")

    data = await crear_solicitud_vinculacion(user.id, uid)
    bot_username = "EntrenadorAX_bot"
    pair_token = data["pair_token"]
    return {
        **data,
        "bot_username": bot_username,
        "telegram_url": f"https://t.me/{bot_username}?start={pair_token}",
        "vincular_command": f"/vincular {data['pair_code']}",
    }


@router.post("/telegram/finish-pair")
async def finish_telegram_pair(
    response: Response,
    uid: int = Depends(get_uid_from_token),
) -> dict:
    """Tras vincular en el bot, refresca JWT si el subject cambio (app -> Telegram real)."""
    from src.api.jwt_app import token_resp_app
    from src.db.repository import obtener_usuario
    from src.services.telegram_pair import consumir_refresh_jwt

    new_uid = await consumir_refresh_jwt(uid)
    if new_uid is not None:
        user = await obtener_usuario(new_uid)
        profile_complete = None
        if user is not None:
            profile_complete = bool(user.telefono and user.email and user.phone_verified_at)
        token = token_resp_app(new_uid, response, profile_complete=profile_complete)
        return {
            "ok": True,
            "telegram_linked": True,
            "jwt": token.jwt,
            "uid": token.uid,
            "expira_en": token.expira_en,
            "profile_complete": token.profile_complete,
        }

    user = await obtener_usuario(uid)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")

    telegram_linked = user.telegram_id is not None and user.telegram_id > 0
    if telegram_linked and uid != user.telegram_id:
        profile_complete = bool(user.telefono and user.email and user.phone_verified_at)
        token = token_resp_app(user.telegram_id, response, profile_complete=profile_complete)
        return {
            "ok": True,
            "telegram_linked": True,
            "jwt": token.jwt,
            "uid": token.uid,
            "expira_en": token.expira_en,
            "profile_complete": token.profile_complete,
        }

    if telegram_linked:
        return {"ok": True, "telegram_linked": True, "already_synced": True}

    raise HTTPException(
        400,
        detail={
            "message": "Aún no vinculaste Telegram. Abre el bot y envía /vincular con tu código.",
            "code": "TELEGRAM_NOT_LINKED",
        },
    )


class CompleteProfileRequest(BaseModel):
    telefono: str
    email: str


class CompleteProfileConfirm(BaseModel):
    telefono: str
    codigo: str


@router.get("/cuenta")
async def get_cuenta(uid: int = Depends(get_uid_from_token)) -> dict:
    from src.db.repository import obtener_usuario
    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado")
    
    # telegram_linked is True if u.telegram_id is positive (and not None)
    telegram_linked = u.telegram_id is not None and u.telegram_id > 0
    profile_complete = bool(u.telefono and u.email and u.phone_verified_at)

    return {
        "telefono": u.telefono,
        "email": u.email,
        "phone_verified": u.phone_verified_at is not None,
        "telegram_linked": telegram_linked,
        "auth_method": u.auth_method,
        "plan_actual": u.plan_actual.value if u.plan_actual else "free",
        "profile_complete": profile_complete,
    }


@router.post("/cuenta/solicitar-otp")
async def cuenta_solicitar_otp(
    req: CompleteProfileRequest, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.db.repository import obtener_usuario
    from src.db.connection import async_session_factory
    from src.db.models import Usuario
    from sqlalchemy import select
    from src.services.identity import normalize_phone

    u = await obtener_usuario(uid)
    if u is None:
        raise HTTPException(404, "Usuario no encontrado")

    telefono_raw = req.telefono.strip()
    email = req.email.strip().lower()

    if not telefono_raw or not email:
        raise HTTPException(400, "Teléfono y email son requeridos")

    telefono = normalize_phone(telefono_raw)

    # Validar que ningún otro usuario tenga este teléfono
    async with async_session_factory() as session:
        dup_tel_q = await session.execute(
            select(Usuario).where(Usuario.telefono == telefono, Usuario.id != u.id)
        )
        if dup_tel_q.scalar_one_or_none():
            raise HTTPException(
                400,
                detail={
                    "message": "Este número de teléfono ya está registrado con otra cuenta.",
                    "code": "DUPLICATE_PHONE"
                }
            )

        # Validar que ningún otro usuario tenga este email
        dup_email_q = await session.execute(
            select(Usuario).where(Usuario.email == email, Usuario.id != u.id)
        )
        if dup_email_q.scalar_one_or_none():
            raise HTTPException(
                400,
                detail={
                    "message": "Este correo electrónico ya está registrado con otra cuenta.",
                    "code": "DUPLICATE_EMAIL"
                }
            )

    # Generar OTP de 6 dígitos
    import random
    codigo = f"{random.randint(100000, 999995)}"

    # Guardar en Redis
    from src.cache import get_redis
    redis_client = await get_redis()
    
    # otp para completar perfil: guardamos codigo -> (telefono, email)
    await redis_client.set(f"otp:complete:{uid}", codigo, ex=300)
    await redis_client.set(f"otp:complete:data:{uid}", f"{telefono}:{email}", ex=300)

    # Enviar correo
    from src.services.email import otp_complete_profile_html, send_email

    sent = await send_email(
        email,
        f"Tu código de confirmación: {codigo}",
        otp_complete_profile_html(codigo),
    )
    if not sent:
        logger.info(
            "OTP de completado generado para %s (%s): %s (email no enviado)",
            telefono,
            email,
            codigo,
        )

    return {"ok": True, "message": "Código de confirmación enviado a tu correo."}


@router.post("/cuenta/confirmar-otp")
async def cuenta_confirmar_otp(
    req: CompleteProfileConfirm, uid: int = Depends(get_uid_from_token)
) -> dict:
    from src.db.connection import async_session_factory
    from src.db.models import Usuario
    from sqlalchemy import select
    from datetime import datetime
    from src.services.identity import normalize_phone

    telefono_raw = req.telefono.strip()
    codigo = req.codigo.strip()

    if not telefono_raw or not codigo:
        raise HTTPException(400, "Teléfono y código son requeridos")

    telefono = normalize_phone(telefono_raw)

    from src.cache import get_redis
    redis_client = await get_redis()

    codigo_guardado = await redis_client.get(f"otp:complete:{uid}")
    if not codigo_guardado or codigo_guardado != codigo:
        raise HTTPException(
            401,
            detail={
                "message": "Código inválido o expirado",
                "code": "INVALID_OTP"
            }
        )

    pending_data = await redis_client.get(f"otp:complete:data:{uid}")
    if not pending_data or not pending_data.startswith(telefono + ":"):
        raise HTTPException(
            400,
            detail={
                "message": "Los datos de verificación no coinciden o han expirado.",
                "code": "REGISTRATION_EXPIRED"
            }
        )

    _, email = pending_data.split(":", 1)

    await redis_client.delete(f"otp:complete:{uid}")
    await redis_client.delete(f"otp:complete:data:{uid}")

    async with async_session_factory() as session:
        # Aquí uid es el telegram_id actual del usuario
        user_q = await session.execute(
            select(Usuario).where(Usuario.telegram_id == uid)
        )
        user = user_q.scalar_one_or_none()
        if not user:
            raise HTTPException(404, "Usuario no encontrado")

        user.telefono = telefono
        user.email = email
        user.phone_verified_at = datetime.utcnow()
        if user.auth_method == "telegram":
            user.auth_method = "both"

        session.add(user)
        await session.commit()

    return {"ok": True, "message": "Perfil completado exitosamente."}
