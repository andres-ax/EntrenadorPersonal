"""Control de seguridad por modos y enforcer de permisos para ejecución de herramientas.

Define las políticas de acceso de las herramientas basadas en la intención semántica de
las mismas (READ, WRITE, DESTRUCTIVE, MEDICAL, SYSTEM), asegurando validaciones de
Ownership de datos basadas en el ID del usuario de Telegram y modos estrictos como READ_ONLY.
"""
from __future__ import annotations

import contextvars
import functools
import json
import logging
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Variable de contexto asíncrona segura e inmune a manipulación del LLM.
# Almacena el ID de Telegram real del usuario activo en la tarea asíncrona actual.
current_session_uid: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_session_uid", default=None
)


class ToolIntent(Enum):
    """Clasificación de intención semántica de ejecución de una herramienta."""
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "delete"
    MEDICAL = "medical"
    SYSTEM = "system"


class PermissionMode(Enum):
    """Modos de control de permisos del sistema."""
    READ_ONLY = "read_only"
    USER_WRITE = "user_write"
    ELEVATED = "elevated"
    PROMPT = "prompt"


# Clasificación estática detallada de las herramientas existentes en el sistema
TOOL_INTENTS: dict[str, ToolIntent] = {
    # Consultas (READ)
    "obtener_perfil": ToolIntent.READ,
    "consultar_hidratacion_hoy": ToolIntent.READ,
    "consultar_historial_peso": ToolIntent.READ,
    "consultar_compromiso": ToolIntent.READ,
    "listar_recordatorios": ToolIntent.READ,
    "consultar_streak": ToolIntent.READ,
    "consultar_progreso_skill": ToolIntent.READ,
    "consultar_ultima_sesion_skill": ToolIntent.READ,
    "resumen_nutricional": ToolIntent.READ,
    "reporte_progreso": ToolIntent.READ,
    "verificar_logros": ToolIntent.READ,
    "consultar_resumen_visual": ToolIntent.READ,
    "listar_todos_prs": ToolIntent.READ,
    "obtener_pr": ToolIntent.READ,

    # Registros y modificaciones básicas (WRITE)
    "registrar_entreno": ToolIntent.WRITE,
    "guardar_perfil": ToolIntent.WRITE,
    "guardar_pr": ToolIntent.WRITE,
    "registrar_comida": ToolIntent.WRITE,
    "registrar_hidratacion": ToolIntent.WRITE,
    "registrar_sueno": ToolIntent.WRITE,
    "registrar_peso": ToolIntent.WRITE,
    "firmar_compromiso": ToolIntent.WRITE,
    "registrar_truco_aterrizado": ToolIntent.WRITE,
    "registrar_sesion_skill": ToolIntent.WRITE,
    "registrar_via_escalada": ToolIntent.WRITE,
    "registrar_sparring": ToolIntent.WRITE,
    "registrar_pelea": ToolIntent.WRITE,
    "programar_recordatorio": ToolIntent.WRITE,
    "editar_sesion_reciente": ToolIntent.WRITE,

    # Configuración de sistema o preferencias del usuario (SYSTEM)
    "cambiar_tono": ToolIntent.SYSTEM,
    "confirmar_modo_militar": ToolIntent.SYSTEM,
    "configurar_quiet_hours": ToolIntent.SYSTEM,
    "pausar": ToolIntent.SYSTEM,
    "usar_dia_libre": ToolIntent.SYSTEM,

    # Herramientas destructivas o de borrado (DESTRUCTIVE)
    "eliminar_comida_reciente": ToolIntent.DESTRUCTIVE,
    "cancelar_recordatorio": ToolIntent.DESTRUCTIVE,

    # Herramientas de dominio médico o diagnóstico (MEDICAL)
    "evaluar_concusion_simplificado": ToolIntent.MEDICAL,
}


class ToolPermissionEnforcer:
    """Clasifica herramientas y valida reglas de negocio de seguridad en caliente."""

    def __init__(self, mode: PermissionMode = PermissionMode.USER_WRITE):
        self.mode = mode

    def check(
        self, tool_name: str, telegram_id: int | None, kwargs: dict[str, Any], session_uid: int | None
    ) -> tuple[bool, str | None]:
        """Evalúa si la herramienta puede ejecutarse según las políticas vigentes.

        Args:
            tool_name: Nombre de la herramienta que se quiere ejecutar.
            telegram_id: El ID de Telegram pasado en los parámetros de la herramienta.
            kwargs: Los argumentos provistos a la herramienta.
            session_uid: El ID real de Telegram de la sesión de usuario que realiza la petición.

        Returns:
            Una tupla (permitido: bool, razon_de_rechazo: str | None).
        """
        # 1. Validación estricta de Ownership de datos
        if telegram_id is not None and session_uid is not None:
            if telegram_id != session_uid:
                logger.warning(
                    "Fallo de Ownership en %s: Sesión %s intentó actuar sobre datos del id %s",
                    tool_name,
                    session_uid,
                    telegram_id,
                )
                return (
                    False,
                    f"Fallo de Ownership: No tienes autorización para modificar datos de la sesión {telegram_id}.",
                )

        # 2. Validación según la intención de la herramienta y el modo de permisos actual
        intent = TOOL_INTENTS.get(tool_name, ToolIntent.WRITE)

        # Modo READ_ONLY bloquea todas las mutaciones (WRITE, DESTRUCTIVE, SYSTEM, MEDICAL)
        if self.mode == PermissionMode.READ_ONLY and intent != ToolIntent.READ:
            logger.info("Bloqueo de mutación %s en modo READ_ONLY", tool_name)
            return False, f"La herramienta '{tool_name}' está bloqueada bajo el modo de solo lectura."

        # Regla estricta para acciones destructivas en modo USER_WRITE normal
        if intent == ToolIntent.DESTRUCTIVE and self.mode == PermissionMode.USER_WRITE:
            logger.info("Bloqueo preventivo de acción destructiva %s sin confirmación explícita", tool_name)
            # Para fines de demostración de gating de seguridad y confirmación
            return (
                False,
                "La operación de eliminación ha sido bloqueada de forma segura por el enforcer. "
                "Para proceder con operaciones destructivas, el sistema requiere confirmación interactiva "
                "explícita por parte del usuario de Telegram.",
            )

        # Restricción adicional para herramientas médicas complejas si no estamos en el modo adecuado
        if intent == ToolIntent.MEDICAL and self.mode in (PermissionMode.READ_ONLY, PermissionMode.USER_WRITE):
            logger.warning("Intento de acceso a funcionalidad médica %s con permisos normales", tool_name)
            return (
                False,
                "Esta es una funcionalidad médica/diagnóstica protegida. "
                "Para garantizar tu seguridad física, este diagnóstico solo puede ser evaluado "
                "bajo la guía y supervisión directa de profesionales de la salud capacitados.",
            )

        return True, None


def enforce_permissions(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorador asíncrono para gating de seguridad y validación de permisos en herramientas.

    Se asegura de verificar el Ownership del ID del usuario y los modos de seguridad
    asociados a la herramienta antes de dar paso a su ejecución.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        # Obtener telegram_id de los argumentos por nombre o por posición
        telegram_id = kwargs.get("telegram_id")
        if telegram_id is None and args:
            telegram_id = args[0]

        # El session_uid real proviene de la variable de contexto asíncrona segura (o fallback a telegram_id)
        session_uid = current_session_uid.get() or telegram_id

        # Para propósitos de flexibilidad de demostración de este gating, determinamos el modo
        # En producción real este modo se recuperaría de la configuración de sesión del usuario en Redis
        mode = PermissionMode.USER_WRITE

        # Si el usuario o las pruebas definen un modo en los parámetros de la herramienta de forma interna
        # (ej: para forzar de forma controlada el modo READ_ONLY)
        if "permission_mode" in kwargs:
            mode_arg = kwargs.pop("permission_mode")
            if isinstance(mode_arg, PermissionMode):
                mode = mode_arg
            elif isinstance(mode_arg, str):
                try:
                    mode = PermissionMode(mode_arg)
                except ValueError:
                    pass

        enforcer = ToolPermissionEnforcer(mode)
        allowed, reason = enforcer.check(fn.__name__, telegram_id, kwargs, session_uid)

        if not allowed:
            # Retorna una respuesta JSON-serializada estructurada en lugar de lanzar una excepción
            return json.dumps({"ok": False, "error": reason})

        return await fn(*args, **kwargs)

    return wrapper
