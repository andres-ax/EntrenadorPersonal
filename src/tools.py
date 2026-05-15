import json
from datetime import date

from agents import function_tool

from src.db.repository import (
    actualizar_usuario,
    guardar_comida as repo_guardar_comida,
    guardar_metrica_corporal,
    guardar_pr as repo_guardar_pr,
    guardar_sesion as repo_guardar_sesion,
    guardar_sueno as repo_guardar_sueno,
    historial_peso as repo_historial_peso,
    listar_prs,
    obtener_o_crear_usuario,
    obtener_pr_ejercicio,
    reporte_semanal,
    resumen_nutricional_dia,
)

TIPOS_ENTRENO_VALIDOS = {"fuerza", "cardio", "movilidad", "deporte"}
TIPOS_COMIDA_VALIDOS = {"desayuno", "almuerzo", "cena", "snack", "post_entreno"}


def _safe_json_loads(raw: str, fallback=None):
    """Parse JSON string safely, returning fallback on failure."""
    if not raw or raw.strip() == "":
        return fallback if fallback is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else []


def _validar_fecha(fecha: str) -> str:
    """Valida y normaliza fecha YYYY-MM-DD. Devuelve hoy si es invalida."""
    try:
        date.fromisoformat(fecha)
        return fecha
    except (ValueError, TypeError):
        return date.today().isoformat()


@function_tool
async def obtener_perfil(telegram_id: int) -> str:
    """Obtiene el perfil completo del usuario. USALA SIEMPRE al inicio para saber que datos faltan."""
    u = await obtener_o_crear_usuario(telegram_id)
    return json.dumps({
        "nombre": u.nombre or "",
        "edad": u.edad,
        "peso_kg": u.peso_kg,
        "altura_cm": u.altura_cm,
        "objetivo": u.objetivo or "",
        "nivel": u.nivel or "",
        "dias_entreno": u.dias_entreno,
        "deporte_principal": u.deporte_principal or "",
        "onboarding_completo": u.onboarding_completo or False,
    })


@function_tool
async def guardar_perfil(
    telegram_id: int,
    nombre: str = "",
    edad: int = 0,
    peso_kg: float = 0,
    altura_cm: float = 0,
    objetivo: str = "",
    nivel: str = "",
    dias_entreno: int = 0,
    deporte_principal: str = "",
    onboarding_completo: bool = False,
) -> str:
    """Actualiza el perfil del usuario. Solo envia los campos que tengas datos concretos.

    Args:
        telegram_id: ID de Telegram del usuario
        nombre: nombre del usuario
        edad: edad en anos
        peso_kg: peso en kilogramos
        altura_cm: altura en centimetros
        objetivo: ganar musculo, perder grasa, mantenerse, mejorar rendimiento
        nivel: principiante, intermedio, avanzado
        dias_entreno: dias por semana que entrena (1-7)
        deporte_principal: gimnasio, crossfit, running, futbol, calistenia, natacion
        onboarding_completo: True cuando tengas peso, altura, objetivo, nivel y dias_entreno
    """
    kwargs = {}
    if nombre:
        kwargs["nombre"] = nombre
    if edad > 0:
        kwargs["edad"] = edad
    if peso_kg > 0:
        kwargs["peso_kg"] = peso_kg
    if altura_cm > 0:
        kwargs["altura_cm"] = altura_cm
    if objetivo:
        kwargs["objetivo"] = objetivo
    if nivel:
        kwargs["nivel"] = nivel
    if dias_entreno > 0:
        kwargs["dias_entreno"] = dias_entreno
    if deporte_principal:
        kwargs["deporte_principal"] = deporte_principal
    if onboarding_completo:
        kwargs["onboarding_completo"] = True

    if not kwargs:
        return json.dumps({"ok": False, "error": "No se proporcionaron campos para actualizar"})

    await actualizar_usuario(telegram_id, **kwargs)
    return json.dumps({"ok": True, "campos_actualizados": list(kwargs.keys())})


@function_tool
async def registrar_entreno(
    telegram_id: int,
    fecha: str,
    tipo: str,
    duracion_min: int = 60,
    ejercicios_json: str = "[]",
    rpe: float = 0,
    notas: str = "",
) -> str:
    """Registra un entrenamiento completo.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD
        tipo: DEBE ser uno de: fuerza, cardio, movilidad, deporte
        duracion_min: duracion en minutos
        ejercicios_json: JSON array de ejercicios, ej: [{"nombre":"sentadilla","series":4,"reps":8,"peso_kg":80}]
        rpe: esfuerzo percibido 1-10 (0 si no se sabe)
        notas: notas adicionales
    """
    fecha = _validar_fecha(fecha)
    tipo = tipo.lower().strip()
    if tipo not in TIPOS_ENTRENO_VALIDOS:
        return json.dumps({"ok": False, "error": f"tipo invalido: {tipo}. Validos: {list(TIPOS_ENTRENO_VALIDOS)}"})

    ejercicios = _safe_json_loads(ejercicios_json, [])
    sesion = await repo_guardar_sesion(
        telegram_id, fecha, tipo, ejercicios, duracion_min,
        rpe if rpe > 0 else None, notas
    )
    return json.dumps({"ok": True, "sesion_id": sesion.id, "ejercicios_registrados": len(ejercicios)})


@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    """Consulta el Personal Record de un ejercicio especifico.

    Args:
        telegram_id: ID de Telegram del usuario
        ejercicio: nombre del ejercicio (ej: sentadilla, press banca, peso muerto)
    """
    pr = await obtener_pr_ejercicio(telegram_id, ejercicio)
    if pr:
        return json.dumps({"ejercicio": pr.ejercicio, "peso_kg": pr.peso_kg, "reps": pr.reps, "fecha": str(pr.fecha)})
    return json.dumps({"mensaje": f"No hay PR registrado para '{ejercicio}'"})


@function_tool
async def guardar_pr(
    telegram_id: int,
    ejercicio: str,
    peso_kg: float,
    reps: int = 1,
    fecha: str = "",
) -> str:
    """Registra un nuevo Personal Record para un ejercicio.

    Args:
        telegram_id: ID de Telegram del usuario
        ejercicio: nombre del ejercicio (ej: sentadilla, press banca, peso muerto)
        peso_kg: peso levantado en kg
        reps: repeticiones realizadas con ese peso
        fecha: formato YYYY-MM-DD (si vacio usa hoy)
    """
    fecha_obj = date.fromisoformat(_validar_fecha(fecha)) if fecha else date.today()
    pr = await repo_guardar_pr(telegram_id, ejercicio, peso_kg, reps, fecha_obj)
    return json.dumps({"ok": True, "ejercicio": pr.ejercicio, "peso_kg": pr.peso_kg, "reps": pr.reps})


@function_tool
async def listar_todos_prs(telegram_id: int) -> str:
    """Lista todos los Personal Records del usuario."""
    prs = await listar_prs(telegram_id)
    if not prs:
        return json.dumps({"mensaje": "Aun no tienes PRs registrados"})
    return json.dumps([{"ejercicio": p.ejercicio, "peso_kg": p.peso_kg, "reps": p.reps} for p in prs])


@function_tool
async def registrar_comida(
    telegram_id: int,
    fecha: str,
    tipo: str,
    alimentos_json: str = "[]",
    calorias: int = 0,
    proteinas: float = 0,
    carbs: float = 0,
    grasas: float = 0,
) -> str:
    """Registra una comida del usuario.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD
        tipo: DEBE ser uno de: desayuno, almuerzo, cena, snack, post_entreno
        alimentos_json: JSON array de strings con alimentos, ej: ["avena","platano","leche"]
        calorias: calorias estimadas totales
        proteinas: gramos de proteina
        carbs: gramos de carbohidratos
        grasas: gramos de grasa
    """
    fecha = _validar_fecha(fecha)
    tipo = tipo.lower().strip()
    if tipo not in TIPOS_COMIDA_VALIDOS:
        return json.dumps({"ok": False, "error": f"tipo invalido: {tipo}. Validos: {list(TIPOS_COMIDA_VALIDOS)}"})

    alimentos = _safe_json_loads(alimentos_json, [])
    await repo_guardar_comida(telegram_id, fecha, tipo, alimentos, calorias, proteinas, carbs, grasas)
    return json.dumps({"ok": True, "tipo": tipo, "alimentos": alimentos})


@function_tool
async def resumen_nutricional(telegram_id: int, fecha: str = "") -> str:
    """Resumen de calorias y macros de un dia especifico.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD (si vacio usa hoy)
    """
    fecha_obj = date.fromisoformat(_validar_fecha(fecha)) if fecha else date.today()
    resumen = await resumen_nutricional_dia(telegram_id, fecha_obj)
    return json.dumps(resumen)


@function_tool
async def registrar_sueno(
    telegram_id: int,
    fecha: str,
    horas: float,
    calidad: int,
    notas: str = "",
) -> str:
    """Registra horas y calidad de sueno de una noche.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD (la fecha en que se desperto)
        horas: horas de sueno (ej: 7.5)
        calidad: 1=pesimo, 2=malo, 3=normal, 4=bueno, 5=excelente
        notas: notas opcionales (ej: "me desperte a las 3am")
    """
    fecha = _validar_fecha(fecha)
    calidad = max(1, min(5, calidad))
    await repo_guardar_sueno(telegram_id, fecha, horas, calidad, notas)
    return json.dumps({"ok": True, "horas": horas, "calidad": calidad})


@function_tool
async def reporte_progreso(telegram_id: int) -> str:
    """Genera reporte semanal completo con sesiones, volumen, PRs y sueno de los ultimos 7 dias."""
    data = await reporte_semanal(telegram_id)
    return json.dumps(data)


@function_tool
async def registrar_peso(
    telegram_id: int,
    peso_kg: float,
    grasa_pct: float = 0,
    cintura_cm: float = 0,
) -> str:
    """Registra peso corporal actual (y opcionalmente grasa% y cintura). Guarda un punto historico.

    Args:
        telegram_id: ID de Telegram del usuario
        peso_kg: peso actual en kilogramos
        grasa_pct: porcentaje de grasa corporal (0 si no se sabe)
        cintura_cm: medida de cintura en cm (0 si no se sabe)
    """
    metrica = await guardar_metrica_corporal(
        telegram_id, peso_kg,
        grasa_pct if grasa_pct > 0 else None,
        cintura_cm if cintura_cm > 0 else None,
    )
    return json.dumps({
        "ok": True,
        "peso_kg": metrica.peso_kg,
        "fecha": str(metrica.fecha),
        "grasa_pct": metrica.grasa_pct,
        "cintura_cm": metrica.cintura_cm,
    })


@function_tool
async def consultar_historial_peso(telegram_id: int, limit: int = 10) -> str:
    """Devuelve los ultimos registros de peso para ver tendencia y progreso.

    Args:
        telegram_id: ID de Telegram del usuario
        limit: cantidad maxima de registros a devolver (default 10)
    """
    registros = await repo_historial_peso(telegram_id, limit)
    if not registros:
        return json.dumps({"mensaje": "Aun no hay registros de peso"})
    return json.dumps([
        {
            "fecha": str(r.fecha),
            "peso_kg": r.peso_kg,
            "grasa_pct": r.grasa_pct,
            "cintura_cm": r.cintura_cm,
        }
        for r in registros
    ])
