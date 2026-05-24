"""Endpoints administrativos: usuarios, pagos, crisis, finanzas, eventos, broadcast.

Auth via X-Admin-Token (root) o Authorization: Bearer JWT (login email+password).
Las notificaciones bidireccionales con el bot van por Redis pubsub canal
`pagos_actualizados` para que el bot envie mensaje al usuario.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, or_

from src.config import settings
from src.api.admin_auth import (
    LoginRequest,
    LoginResponse,
    autenticar_admin,
    get_admin_from_token,
    hash_password,
    require_super,
)
from src.cache import get_redis
from src.db.connection import async_session_factory
from src.db.models import (
    Admin,
    CrisisLog,
    EscalacionState,
    EstadoPago,
    EventoBot,
    MetodoPago,
    PagoComprobante,
    PlanSuscripcion,
    RolAdmin,
    Suscripcion,
    Usuario,
    UsuarioBloqueado,
)
from src.db.repository import (
    activar_plan,
    aprobar_comprobante,
    bloquear_usuario,
    desbloquear_usuario,
    eliminar_usuario,
    listar_comprobantes_admin,
    obtener_comprobante,
    pausar_recordatorios,
    rechazar_comprobante,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])

CANAL_PAGOS = "pagos_actualizados"


# --- Auth ---


@router.post("/auth/login", response_model=LoginResponse)
async def admin_login(req: LoginRequest) -> LoginResponse:
    return await autenticar_admin(req)


@router.get("/auth/me")
async def admin_me(admin: dict = Depends(get_admin_from_token)) -> dict:
    return admin


class CrearAdminReq(BaseModel):
    email: str
    password: str
    rol: str = "soporte"


@router.post("/admins")
async def crear_admin(
    req: CrearAdminReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    await require_super(admin)
    try:
        rol_enum = RolAdmin(req.rol)
    except ValueError:
        raise HTTPException(400, "rol invalido")
    async with async_session_factory() as session:
        existente = await session.execute(
            select(Admin).where(Admin.email == req.email.lower())
        )
        if existente.scalar_one_or_none() is not None:
            raise HTTPException(409, "Email ya registrado")
        nuevo = Admin(
            email=req.email.lower(),
            password_hash=hash_password(req.password),
            rol=rol_enum,
            activo=True,
        )
        session.add(nuevo)
        await session.commit()
        await session.refresh(nuevo)
    return {"id": nuevo.id, "email": nuevo.email, "rol": nuevo.rol.value}


@router.get("/admins")
async def listar_admins(admin: dict = Depends(get_admin_from_token)) -> list[dict]:
    await require_super(admin)
    async with async_session_factory() as session:
        result = await session.execute(select(Admin).order_by(Admin.created_at.desc()))
        admins = list(result.scalars().all())
    return [
        {
            "id": a.id,
            "email": a.email,
            "rol": a.rol.value,
            "activo": a.activo,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "last_login_at": a.last_login_at.isoformat() if a.last_login_at else None,
        }
        for a in admins
    ]


# --- Usuarios ---


def _usuario_dict(u: Usuario) -> dict:
    return {
        "id": u.id,
        "telegram_id": u.telegram_id,
        "nombre": u.nombre,
        "email": u.email,
        "pais": u.pais,
        "tono": u.tono.value if u.tono else "firme",
        "idioma": u.idioma,
        "plan_actual": u.plan_actual.value if u.plan_actual else "free",
        "plan_expira_en": u.plan_expira_en.isoformat() if u.plan_expira_en else None,
        "bot_bloqueado": u.bot_bloqueado,
        "pausado_hasta": u.pausado_hasta.isoformat() if u.pausado_hasta else None,
        "onboarding_completo": u.onboarding_completo,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("/usuarios")
async def listar_usuarios(
    admin: dict = Depends(get_admin_from_token),
    q: str = "",
    plan: Optional[str] = None,
    pais: Optional[str] = None,
    bloqueado: Optional[bool] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    async with async_session_factory() as session:
        query = select(Usuario)
        if q:
            like = f"%{q.lower()}%"
            query = query.where(
                or_(
                    func.lower(Usuario.nombre).like(like),
                    func.lower(Usuario.email).like(like),
                    Usuario.codigo_referido == q,
                )
            )
        if plan:
            try:
                query = query.where(Usuario.plan_actual == PlanSuscripcion(plan))
            except ValueError:
                raise HTTPException(400, "plan invalido")
        if pais:
            query = query.where(Usuario.pais == pais)
        if bloqueado is True:
            sub = select(UsuarioBloqueado.usuario_id)
            query = query.where(Usuario.id.in_(sub))
        elif bloqueado is False:
            sub = select(UsuarioBloqueado.usuario_id)
            query = query.where(~Usuario.id.in_(sub))
        total_q = await session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = total_q.scalar() or 0
        query = query.order_by(Usuario.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        usuarios = list(result.scalars().all())
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_usuario_dict(u) for u in usuarios],
    }


@router.get("/usuarios/{uid}")
async def detalle_usuario(
    uid: int, admin: dict = Depends(get_admin_from_token)
) -> dict:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == uid)
        )
        u = result.scalar_one_or_none()
        if u is None:
            raise HTTPException(404, "Usuario no encontrado")
        suscripciones_q = await session.execute(
            select(Suscripcion)
            .where(Suscripcion.usuario_id == u.id)
            .order_by(Suscripcion.iniciada_en.desc())
            .limit(20)
        )
        suscripciones = list(suscripciones_q.scalars().all())
        pagos_q = await session.execute(
            select(PagoComprobante)
            .where(PagoComprobante.usuario_id == u.id)
            .order_by(PagoComprobante.creado_en.desc())
            .limit(20)
        )
        pagos = list(pagos_q.scalars().all())
        crisis_q = await session.execute(
            select(CrisisLog)
            .where(CrisisLog.usuario_id == u.id)
            .order_by(CrisisLog.creado_en.desc())
            .limit(10)
        )
        crisis = list(crisis_q.scalars().all())
        eventos_q = await session.execute(
            select(EventoBot)
            .where(EventoBot.usuario_id == u.id)
            .order_by(EventoBot.creado_en.desc())
            .limit(30)
        )
        eventos = list(eventos_q.scalars().all())
        bloqueado_q = await session.execute(
            select(UsuarioBloqueado).where(UsuarioBloqueado.usuario_id == u.id)
        )
        bloqueado = bloqueado_q.scalar_one_or_none()
    return {
        "usuario": _usuario_dict(u),
        "bloqueado": (
            {
                "motivo": bloqueado.motivo,
                "por": bloqueado.bloqueado_por,
                "en": bloqueado.bloqueado_en.isoformat(),
            }
            if bloqueado
            else None
        ),
        "suscripciones": [
            {
                "id": s.id,
                "plan": s.plan.value if s.plan else "free",
                "metodo": s.metodo_pago.value if s.metodo_pago else "manual_admin",
                "monto_cop": s.monto_cop,
                "iniciada_en": s.iniciada_en.isoformat() if s.iniciada_en else None,
                "expira_en": s.expira_en.isoformat() if s.expira_en else None,
                "activa": s.activa,
            }
            for s in suscripciones
        ],
        "pagos": [
            {
                "id": p.id,
                "monto_cop": p.monto_cop,
                "monto_esperado_cop": p.monto_esperado_cop,
                "monto_match": p.monto_match,
                "plan_solicitado": p.plan_solicitado.value if p.plan_solicitado else "starter",
                "duracion": p.duracion_solicitada.value if p.duracion_solicitada else "mensual",
                "estado": p.estado.value if p.estado else "pendiente_humano",
                "metodo": p.metodo.value if p.metodo else "otro",
                "referencia": p.referencia,
                "creado_en": p.creado_en.isoformat() if p.creado_en else None,
            }
            for p in pagos
        ],
        "crisis": [
            {
                "id": c.id,
                "nivel": c.nivel,
                "keywords": c.keywords_detectadas,
                "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            }
            for c in crisis
        ],
        "eventos_recientes": [
            {
                "tipo": e.tipo_evento,
                "payload": e.payload,
                "en": e.creado_en.isoformat() if e.creado_en else None,
            }
            for e in eventos
        ],
    }


class AsignarPlanReq(BaseModel):
    plan: str
    dias: int = 30


@router.post("/usuarios/{uid}/asignar_plan")
async def asignar_plan_manual(
    uid: int,
    req: AsignarPlanReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    try:
        plan_enum = PlanSuscripcion(req.plan)
    except ValueError:
        raise HTTPException(400, "plan invalido")
    sus = await activar_plan(
        telegram_id=uid,
        plan=plan_enum,
        dias=req.dias,
        metodo=MetodoPago.MANUAL_ADMIN,
    )
    await _publicar_evento_pago(
        uid, "plan_asignado_admin", {"plan": plan_enum.value, "dias": req.dias, "por": admin["email"]}
    )
    return {"ok": True, "suscripcion_id": sus.id}


class PausarReq(BaseModel):
    dias: int = 7


@router.post("/usuarios/{uid}/pausar")
async def pausar_usuario(
    uid: int, req: PausarReq, admin: dict = Depends(get_admin_from_token)
) -> dict:
    user = await pausar_recordatorios(uid, req.dias)
    if user is None:
        raise HTTPException(404, "Usuario no encontrado")
    return {"ok": True, "pausado_hasta": user.pausado_hasta.isoformat()}


class BloquearReq(BaseModel):
    motivo: str


@router.post("/usuarios/{uid}/bloquear")
async def bloquear_endpoint(
    uid: int, req: BloquearReq, admin: dict = Depends(get_admin_from_token)
) -> dict:
    ok = await bloquear_usuario(uid, admin["email"], req.motivo)
    return {"ok": ok}


@router.delete("/usuarios/{uid}/bloquear")
async def desbloquear_endpoint(
    uid: int, admin: dict = Depends(get_admin_from_token)
) -> dict:
    ok = await desbloquear_usuario(uid)
    return {"ok": ok}


@router.delete("/usuarios/{uid}")
async def eliminar_endpoint(
    uid: int, admin: dict = Depends(get_admin_from_token)
) -> dict:
    await require_super(admin)
    ok = await eliminar_usuario(uid)
    return {"ok": ok}


# --- Pagos ---


def _comprobante_dict(p: PagoComprobante) -> dict:
    return {
        "id": p.id,
        "usuario_id": p.usuario_id,
        "foto_file_id": p.foto_file_id,
        "monto_cop": p.monto_cop,
        "monto_esperado_cop": p.monto_esperado_cop,
        "monto_match": p.monto_match,
        "referencia": p.referencia,
        "cuenta_origen": p.cuenta_origen,
        "cuenta_destino": p.cuenta_destino,
        "fecha_pago": p.fecha_pago.isoformat() if p.fecha_pago else None,
        "metodo": p.metodo.value if p.metodo else "otro",
        "plan_solicitado": p.plan_solicitado.value if p.plan_solicitado else "starter",
        "duracion": p.duracion_solicitada.value if p.duracion_solicitada else "mensual",
        "dias_otorgados": p.dias_otorgados,
        "estado": p.estado.value if p.estado else "pendiente_humano",
        "motivo_rechazo": p.motivo_rechazo,
        "vision_payload": p.vision_payload,
        "revisado_por": p.revisado_por,
        "revisado_en": p.revisado_en.isoformat() if p.revisado_en else None,
        "creado_en": p.creado_en.isoformat() if p.creado_en else None,
        "notas_admin": p.notas_admin,
    }


@router.get("/pagos")
async def listar_pagos(
    admin: dict = Depends(get_admin_from_token),
    estado: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    estado_enum = None
    if estado:
        try:
            estado_enum = EstadoPago(estado)
        except ValueError:
            raise HTTPException(400, "estado invalido")
    pagos = await listar_comprobantes_admin(estado=estado_enum, limit=limit, offset=offset)
    async with async_session_factory() as session:
        q_total = select(func.count(PagoComprobante.id))
        if estado_enum:
            q_total = q_total.where(PagoComprobante.estado == estado_enum)
        total = (await session.execute(q_total)).scalar() or 0
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_comprobante_dict(p) for p in pagos],
    }


@router.get("/pagos/{comp_id}/foto")
async def descargar_foto_comprobante(
    comp_id: int,
    admin: dict = Depends(get_admin_from_token),
):
    """Proxy a Telegram para descargar la foto del comprobante."""
    from fastapi.responses import Response
    import httpx

    from src.config import settings as _settings

    comp = await obtener_comprobante(comp_id)
    if comp is None or not comp.foto_file_id:
        raise HTTPException(404, "Comprobante o foto no encontrada")

    token = _settings.telegram_token.get_secret_value()
    async with httpx.AsyncClient(timeout=10.0) as client:
        info = await client.get(
            f"https://api.telegram.org/bot{token}/getFile",
            params={"file_id": comp.foto_file_id},
        )
        info.raise_for_status()
        data = info.json()
        if not data.get("ok"):
            raise HTTPException(502, "getFile fallo")
        file_path = data["result"]["file_path"]
        download = await client.get(
            f"https://api.telegram.org/file/bot{token}/{file_path}"
        )
        download.raise_for_status()
    media_type = "image/jpeg"
    return Response(content=download.content, media_type=media_type)


@router.get("/pagos/{comp_id}")
async def detalle_pago(
    comp_id: int, admin: dict = Depends(get_admin_from_token)
) -> dict:
    comp = await obtener_comprobante(comp_id)
    if comp is None:
        raise HTTPException(404, "Comprobante no encontrado")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.id == comp.usuario_id)
        )
        u = result.scalar_one()
    return {
        "comprobante": _comprobante_dict(comp),
        "usuario": _usuario_dict(u),
    }


class AprobarReq(BaseModel):
    notas: str = ""


@router.post("/pagos/{comp_id}/aprobar")
async def aprobar(
    comp_id: int,
    req: AprobarReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    comp = await aprobar_comprobante(comp_id, admin["email"], req.notas)
    if comp is None:
        raise HTTPException(404, "No encontrado o ya aprobado")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.telegram_id).where(Usuario.id == comp.usuario_id)
        )
        uid_telegram = result.scalar_one()
    await _publicar_evento_pago(
        uid_telegram,
        "pago_aprobado",
        {
            "comp_id": comp.id,
            "plan": comp.plan_solicitado.value,
            "monto_cop": comp.monto_cop,
            "por": admin["email"],
        },
    )
    return {"ok": True, "comprobante": _comprobante_dict(comp)}


class RechazarReq(BaseModel):
    motivo: str
    bloquear: bool = False


@router.post("/pagos/{comp_id}/rechazar")
async def rechazar(
    comp_id: int,
    req: RechazarReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    comp = await rechazar_comprobante(
        comp_id, admin["email"], req.motivo, bloquear=req.bloquear
    )
    if comp is None:
        raise HTTPException(404, "No encontrado")
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario.telegram_id).where(Usuario.id == comp.usuario_id)
        )
        uid_telegram = result.scalar_one()
    await _publicar_evento_pago(
        uid_telegram,
        "pago_rechazado",
        {
            "comp_id": comp.id,
            "motivo": req.motivo,
            "bloqueado": req.bloquear,
            "por": admin["email"],
        },
    )
    return {"ok": True, "comprobante": _comprobante_dict(comp)}


# --- Crisis / Operaciones ---


@router.get("/crisis")
async def listar_crisis(
    admin: dict = Depends(get_admin_from_token),
    nivel: Optional[int] = None,
    dias: int = 30,
    limit: int = Query(100, le=500),
) -> dict:
    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        q = select(CrisisLog).where(CrisisLog.creado_en >= desde)
        if nivel is not None:
            q = q.where(CrisisLog.nivel == nivel)
        q = q.order_by(CrisisLog.creado_en.desc()).limit(limit)
        result = await session.execute(q)
        items = list(result.scalars().all())
    return {
        "total": len(items),
        "items": [
            {
                "id": c.id,
                "usuario_id": c.usuario_id,
                "nivel": c.nivel,
                "keywords": c.keywords_detectadas,
                "derivado_a": c.derivado_a,
                "mensaje_usuario": c.mensaje_usuario,
                "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            }
            for c in items
        ],
    }


@router.get("/escalation/{uid}")
async def estado_escalation(
    uid: int, admin: dict = Depends(get_admin_from_token)
) -> dict:
    async with async_session_factory() as session:
        result = await session.execute(
            select(Usuario).where(Usuario.telegram_id == uid)
        )
        u = result.scalar_one_or_none()
        if u is None:
            raise HTTPException(404, "Usuario no encontrado")
        hoy = date.today()
        estados_q = await session.execute(
            select(EscalacionState).where(
                EscalacionState.usuario_id == u.id,
                EscalacionState.fecha == hoy,
            )
        )
        estados = list(estados_q.scalars().all())
    return {
        "uid": uid,
        "fecha": hoy.isoformat(),
        "estados": [
            {
                "tipo_accion": e.tipo_accion.value if e.tipo_accion else "entreno",
                "level": e.level,
                "mensajes_enviados_hoy": e.mensajes_enviados_hoy,
                "ultimo_envio": e.ultimo_envio.isoformat() if e.ultimo_envio else None,
            }
            for e in estados
        ],
    }


@router.get("/eventos")
async def listar_eventos(
    admin: dict = Depends(get_admin_from_token),
    tipo: Optional[str] = None,
    dias: int = 7,
    limit: int = Query(100, le=500),
) -> dict:
    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        q = select(EventoBot).where(EventoBot.creado_en >= desde)
        if tipo:
            q = q.where(EventoBot.tipo_evento == tipo)
        q = q.order_by(EventoBot.creado_en.desc()).limit(limit)
        result = await session.execute(q)
        items = list(result.scalars().all())
    return {
        "total": len(items),
        "items": [
            {
                "id": e.id,
                "usuario_id": e.usuario_id,
                "tipo": e.tipo_evento,
                "payload": e.payload,
                "creado_en": e.creado_en.isoformat() if e.creado_en else None,
            }
            for e in items
        ],
    }


# --- Finanzas ---


@router.get("/finanzas")
async def finanzas(
    admin: dict = Depends(get_admin_from_token),
    dias: int = 30,
) -> dict:
    """MRR, ingresos por metodo, conversiones del periodo."""
    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        plan_breakdown_q = await session.execute(
            select(Usuario.plan_actual, func.count(Usuario.id))
            .where(Usuario.plan_actual.is_not(None))
            .group_by(Usuario.plan_actual)
        )
        plan_breakdown = {p.value if p else "free": c for p, c in plan_breakdown_q}
        ingresos_q = await session.execute(
            select(
                Suscripcion.metodo_pago,
                func.sum(Suscripcion.monto_cop),
                func.count(Suscripcion.id),
            )
            .where(
                Suscripcion.iniciada_en >= desde,
                Suscripcion.monto_cop.is_not(None),
            )
            .group_by(Suscripcion.metodo_pago)
        )
        ingresos_por_metodo = {
            (m.value if m else "otro"): {"total_cop": int(total or 0), "n": n}
            for m, total, n in ingresos_q
        }
        pagos_pendientes = (
            await session.execute(
                select(func.count(PagoComprobante.id)).where(
                    PagoComprobante.estado == EstadoPago.PENDIENTE_HUMANO
                )
            )
        ).scalar() or 0
    total_cop = sum(d["total_cop"] for d in ingresos_por_metodo.values())
    return {
        "fecha": datetime.utcnow().isoformat(),
        "periodo_dias": dias,
        "usuarios_por_plan": plan_breakdown,
        "ingresos_periodo_cop": total_cop,
        "ingresos_por_metodo": ingresos_por_metodo,
        "pagos_pendientes_revision": pagos_pendientes,
    }


# --- Broadcast ---


class BroadcastReq(BaseModel):
    mensaje: str
    plan_minimo: Optional[str] = None
    pais: Optional[str] = None
    silent: bool = True
    gm_nombre: Optional[str] = None


@router.post("/broadcast")
async def broadcast(
    req: BroadcastReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    """Encola broadcast via Redis pubsub. El bot escucha y envia."""
    await require_super(admin)
    payload = {
        "mensaje": req.mensaje,
        "plan_minimo": req.plan_minimo,
        "pais": req.pais,
        "silent": req.silent,
        "por": admin["email"],
        "gm_nombre": req.gm_nombre,
    }
    try:
        client = await get_redis()
        await client.publish("broadcast_admin", json.dumps(payload))
    except Exception:
        logger.exception("Error publicando broadcast admin")
        raise HTTPException(500, "Error publicando broadcast")
    return {"ok": True, "encolado": True}


# --- Notificacion al bot ---


@router.get("/health/all")
async def health_all(admin: dict = Depends(get_admin_from_token)) -> dict:
    """Health agregado: bot-api, realtime-ws, worker, postgres, redis."""
    import httpx as _h
    from src.cache import ping as _ping_r
    from src.db.connection import ping as _ping_d

    out = {
        "bot_api": {"db": False, "redis": False},
        "realtime_ws": {"ok": False},
    }
    try:
        out["bot_api"]["db"] = await _ping_d()
        out["bot_api"]["redis"] = await _ping_r()
    except Exception:
        pass
    realtime_url = settings.realtime_ws_url
    if realtime_url:
        http_url = (
            realtime_url.replace("wss://", "https://")
            .replace("ws://", "http://")
            .rsplit("/ws/", 1)[0]
            + "/health"
        )
        try:
            async with _h.AsyncClient(timeout=3.0) as client:
                r = await client.get(http_url)
                out["realtime_ws"] = r.json()
        except Exception:
            pass
    return out


@router.get("/auditoria")
async def listar_auditoria(
    admin: dict = Depends(get_admin_from_token),
    telegram_id: Optional[int] = Query(None),
    request_id: Optional[str] = Query(None),
    con_error: Optional[bool] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    from src.db.models import AuditoriaTurno

    async with async_session_factory() as session:
        query = select(AuditoriaTurno)
        if telegram_id is not None:
            query = query.where(AuditoriaTurno.telegram_id == telegram_id)
        if request_id is not None:
            query = query.where(AuditoriaTurno.request_id == request_id)
        if con_error is True:
            query = query.where(AuditoriaTurno.error.is_not(None))
        elif con_error is False:
            query = query.where(AuditoriaTurno.error.is_(None))

        # Contamos el total para paginación
        total_q = await session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = total_q.scalar() or 0

        # Ordenamos por creado_en desc
        query = query.order_by(AuditoriaTurno.creado_en.desc()).limit(limit).offset(offset)
        result = await session.execute(query)
        items = list(result.scalars().all())

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": row.id,
                "telegram_id": row.telegram_id,
                "usuario_id": row.usuario_id,
                "request_id": row.request_id,
                "prompt_usuario": row.prompt_usuario,
                "respuesta_bot": row.respuesta_bot,
                "tokens_input": row.tokens_input,
                "tokens_output": row.tokens_output,
                "costo_estimado_usd": row.costo_estimado_usd,
                "duracion_ms": row.duracion_ms,
                "con_error": row.error is not None,
                "error": row.error,
                "creado_en": row.creado_en.isoformat() if row.creado_en else None,
            }
            for row in items
        ],
    }


@router.get("/tasks/audit")
async def listar_task_audit(
    admin: dict = Depends(get_admin_from_token),
    telegram_id: Optional[int] = Query(None),
    task_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    offset: int = 0,
) -> dict:
    from src.db.models import TaskAuditLog

    async with async_session_factory() as session:
        query = select(TaskAuditLog)
        if telegram_id is not None:
            query = query.where(TaskAuditLog.telegram_id == telegram_id)
        if task_type:
            query = query.where(TaskAuditLog.task_type == task_type)
        if action:
            query = query.where(TaskAuditLog.action == action)
        total_q = await session.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = total_q.scalar() or 0
        result = await session.execute(
            query.order_by(TaskAuditLog.creado_en.desc()).offset(offset).limit(limit)
        )
        items = list(result.scalars().all())
    return {
        "total": total,
        "items": [
            {
                "id": r.id,
                "task_id": r.task_id,
                "telegram_id": r.telegram_id,
                "task_type": r.task_type,
                "action": r.action,
                "payload_snapshot": r.payload_snapshot,
                "error": r.error,
                "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            }
            for r in items
        ],
    }


@router.get("/metrics/proactivos")
async def metricas_proactivos(
    admin: dict = Depends(get_admin_from_token),
    dias: int = Query(7, ge=1, le=30),
) -> dict:
    from datetime import datetime, timedelta

    from src.db.models import TaskAuditLog

    desde = datetime.utcnow() - timedelta(days=dias)
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                TaskAuditLog.telegram_id,
                func.count(TaskAuditLog.id),
            )
            .where(
                TaskAuditLog.action == "sent",
                TaskAuditLog.creado_en >= desde,
            )
            .group_by(TaskAuditLog.telegram_id)
        )
        rows = list(result.all())
    return {
        "dias": dias,
        "usuarios": [
            {"telegram_id": uid, "mensajes_proactivos": int(cnt)}
            for uid, cnt in rows
        ],
    }


@router.get("/auditoria/{request_id}")
async def detalle_auditoria(
    request_id: str,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    from src.db.models import AuditoriaTurno

    async with async_session_factory() as session:
        result = await session.execute(
            select(AuditoriaTurno).where(AuditoriaTurno.request_id == request_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Registro de auditoría no encontrado")

    return {
        "id": row.id,
        "telegram_id": row.telegram_id,
        "usuario_id": row.usuario_id,
        "request_id": row.request_id,
        "prompt_usuario": row.prompt_usuario,
        "respuesta_bot": row.respuesta_bot,
        "tools_invocadas": row.tools_invocadas,
        "tokens_input": row.tokens_input,
        "tokens_output": row.tokens_output,
        "costo_estimado_usd": row.costo_estimado_usd,
        "duracion_ms": row.duracion_ms,
        "error": row.error,
        "creado_en": row.creado_en.isoformat() if row.creado_en else None,
    }


@router.get("/desafios")
async def admin_desafios(
    fecha: str | None = None,
    _admin=Depends(get_admin_from_token),
) -> dict:
    from datetime import date as date_cls

    from src.services.comunidad import (
        contar_desafios_opt_in,
        contar_participantes_desafio,
        contar_usuarios_activos_onboarding,
        listar_desafios_por_fecha,
        ranking_desafio,
    )

    target = date_cls.fromisoformat(fecha) if fecha else date_cls.today()
    desafios = await listar_desafios_por_fecha(target)
    opt_in = await contar_desafios_opt_in()
    activos = await contar_usuarios_activos_onboarding()
    out = []
    for d in desafios:
        top = await ranking_desafio(d.slug, top=3)
        participantes = await contar_participantes_desafio(d.id)
        out.append(
            {
                "id": d.id,
                "slug": d.slug,
                "titulo": d.titulo,
                "cohorte_key": d.cohorte_key,
                "metrica": d.metrica,
                "meta_valor": d.meta_valor,
                "estado": d.estado,
                "participantes": participantes,
                "top3": top,
            }
        )
    return {
        "fecha": target.isoformat(),
        "opt_in_usuarios": opt_in,
        "usuarios_activos": activos,
        "desafios": out,
    }


class DesafioGenerarReq(BaseModel):
    fecha: Optional[str] = None
    solo_opt_in: bool = False


@router.post("/desafios/generar")
async def admin_desafios_generar(
    req: DesafioGenerarReq,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    from datetime import date as date_cls

    from src.services.desafios.generador import generar_desafios_del_dia
    from src.tasks.scheduling import schedule_desafio_cierre

    await require_super(admin)
    target = date_cls.fromisoformat(req.fecha) if req.fecha else date_cls.today()
    resultado = await generar_desafios_del_dia(target, solo_opt_in=req.solo_opt_in)
    for des in resultado.desafios:
        await schedule_desafio_cierre(des.id, des.fecha_fin)
    return {
        "ok": True,
        "fecha": target.isoformat(),
        "generados": len(resultado.desafios),
        "slugs": [d.slug for d in resultado.desafios],
        "usuarios_considerados": resultado.usuarios_considerados,
        "cohortes_detectadas": resultado.cohortes_detectadas,
        "cohortes_omitidas_minimo": resultado.cohortes_omitidas_minimo,
        "solo_opt_in": resultado.solo_opt_in,
    }


@router.post("/desafios/{desafio_id}/cerrar")
async def admin_desafios_cerrar(
    desafio_id: int,
    admin: dict = Depends(get_admin_from_token),
) -> dict:
    from src.tasks.scheduling import schedule_desafio_cierre_ahora

    await require_super(admin)
    task_id = await schedule_desafio_cierre_ahora(desafio_id)
    if task_id is None:
        from src.services.desafios.premios import cerrar_desafio_y_premiar

        resumen = await cerrar_desafio_y_premiar(desafio_id)
        return {"ok": True, "modo": "directo", "premios": len(resumen.get("premios", []))}
    return {"ok": True, "modo": "cola", "task_id": task_id}


async def _publicar_evento_pago(
    telegram_id: int, tipo: str, payload: dict
) -> None:
    """Notifica al bot via Redis pubsub que un pago cambio de estado."""
    try:
        client = await get_redis()
        await client.publish(
            CANAL_PAGOS,
            json.dumps(
                {"telegram_id": telegram_id, "tipo": tipo, "payload": payload}
            ),
        )
    except Exception:
        logger.exception("Error publicando evento pago a Redis pubsub")
