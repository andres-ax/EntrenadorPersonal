"""Modelos SQLAlchemy de EntrenadorAX."""
import enum
from datetime import date, time

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class TipoEjercicio(str, enum.Enum):
    FUERZA = "fuerza"
    CARDIO = "cardio"
    MOVILIDAD = "movilidad"
    DEPORTE = "deporte"


class TipoComida(str, enum.Enum):
    DESAYUNO = "desayuno"
    ALMUERZO = "almuerzo"
    CENA = "cena"
    SNACK = "snack"
    POST_ENTRENO = "post_entreno"


class TonoCoach(str, enum.Enum):
    AMIGABLE = "amigable"
    FIRME = "firme"
    MILITAR = "militar"


class TipoCompromiso(str, enum.Enum):
    ENTRENO = "entreno"
    COMIDA = "comida"
    PESO = "peso"
    GENERAL = "general"


class TipoStreak(str, enum.Enum):
    ENTRENO = "entreno"
    COMIDA = "comida"
    SUENO = "sueno"
    PESO = "peso"
    TODOS = "todos"


class TipoAccionEscalacion(str, enum.Enum):
    ENTRENO = "entreno"
    COMIDA = "comida"
    SUENO = "sueno"
    PESO = "peso"


class PlanSuscripcion(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ELITE = "elite"
    LIFETIME = "lifetime"


class MetodoPago(str, enum.Enum):
    BRE_B = "bre_b"
    NEQUI = "nequi"
    DAVIPLATA = "daviplata"
    BANCOLOMBIA = "bancolombia"
    MANUAL_ADMIN = "manual_admin"
    TELEGRAM_STARS = "telegram_stars"
    OTRO = "otro"


class DuracionPago(str, enum.Enum):
    MENSUAL = "mensual"
    ANUAL = "anual"
    LIFETIME = "lifetime"


class EstadoPago(str, enum.Enum):
    PENDIENTE_HUMANO = "pendiente_humano"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    DUPLICADO = "duplicado"


class RolAdmin(str, enum.Enum):
    SUPER = "super"
    SOPORTE = "soporte"


class CategoriaDeporte(str, enum.Enum):
    """Categoria del deporte que determina el modelo de coaching aplicado.

    Cada categoria tiene un sub-prompt en REGLA #11 del coach con vocabulario
    nativo, metricas correctas y framework de periodizacion adecuado.
    """
    URBANO = "urbano"
    COMBATE = "combate"
    ESCALADA = "escalada"
    ACUATICO = "acuatico"
    EQUIPO = "equipo"
    OUTDOOR_ENDURANCE = "outdoor_endurance"
    INDOOR_FUERZA = "indoor_fuerza"
    ECUESTRE = "ecuestre"
    MOTOR = "motor"
    TRADICIONAL_CO = "tradicional_co"
    OTRO = "otro"


class TipoPR(str, enum.Enum):
    """Tipo de Personal Record. Default PESO_REPS para back-compat fuerza."""
    PESO_REPS = "peso_reps"
    TIEMPO = "tiempo"
    TRUCO = "truco"
    GRADO = "grado"
    PROFUNDIDAD = "profundidad"
    ALTURA = "altura"
    WATTS = "watts"
    VELOCIDAD = "velocidad"
    RONDAS = "rondas"
    CINTURON = "cinturon"
    DISTANCIA = "distancia"


class SubtipoSesion(str, enum.Enum):
    """Subtipo de sesion para deportes que no son fuerza pura."""
    SETS = "sets"
    SKILL = "skill"
    SPARRING = "sparring"
    DRILLING = "drilling"
    COMPETENCIA = "competencia"
    LONG_RUN = "long_run"
    INTERVALOS = "intervalos"
    DESCANSO_ACTIVO = "descanso_activo"
    OTRO = "otro"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    nombre = Column(String(100))
    edad = Column(Integer)
    peso_kg = Column(Float)
    altura_cm = Column(Float)
    objetivo = Column(String(200))
    nivel = Column(String(50))
    dias_entreno = Column(Integer)
    deporte_principal = Column(String(100))
    onboarding_completo = Column(Boolean, default=False)

    timezone = Column(String(64), default="America/Bogota", nullable=False)
    tono = Column(Enum(TonoCoach), default=TonoCoach.FIRME, nullable=False)
    idioma = Column(String(8), default="es", nullable=False)
    categoria_deporte = Column(
        Enum(CategoriaDeporte),
        default=CategoriaDeporte.INDOOR_FUERZA,
        nullable=False,
        index=True,
    )
    modalidad_deporte = Column(String(64), nullable=True)
    anos_practica = Column(Integer, nullable=True)
    es_competitivo = Column(Boolean, default=False, nullable=False)
    modo_militar_aceptado_en = Column(DateTime)
    bot_bloqueado = Column(Boolean, default=False, nullable=False)
    pausado_hasta = Column(Date)
    quiet_hours_inicio = Column(Time, default=time(22, 0), nullable=False)
    quiet_hours_fin = Column(Time, default=time(7, 0), nullable=False)
    pais = Column(String(8), default="CO", nullable=False)

    plan_actual = Column(
        Enum(PlanSuscripcion), default=PlanSuscripcion.FREE, nullable=False, index=True
    )
    plan_expira_en = Column(DateTime, nullable=True)
    referido_por = Column(BigInteger, nullable=True, index=True)
    codigo_referido = Column(String(32), unique=True, nullable=True)

    email = Column(String(180), unique=True, nullable=True, index=True)
    email_verified_at = Column(DateTime, nullable=True)
    auth_method = Column(String(16), default="telegram", nullable=False)

    created_at = Column(DateTime, server_default=func.now())

    sesiones = relationship(
        "SesionEntrenamiento", back_populates="usuario", cascade="all, delete-orphan"
    )
    comidas = relationship("Comida", back_populates="usuario", cascade="all, delete-orphan")
    prs = relationship("PersonalRecord", back_populates="usuario", cascade="all, delete-orphan")
    sueno = relationship("MetricaSueno", back_populates="usuario", cascade="all, delete-orphan")
    metricas_corporales = relationship(
        "MetricaCorporal", back_populates="usuario", cascade="all, delete-orphan"
    )
    compromisos = relationship(
        "Compromiso", back_populates="usuario", cascade="all, delete-orphan"
    )
    estados_escalacion = relationship(
        "EscalacionState", back_populates="usuario", cascade="all, delete-orphan"
    )
    streaks = relationship("Streak", back_populates="usuario", cascade="all, delete-orphan")
    checkins = relationship(
        "CheckinNocturno", back_populates="usuario", cascade="all, delete-orphan"
    )
    eventos = relationship("EventoBot", back_populates="usuario", cascade="all, delete-orphan")
    crisis = relationship("CrisisLog", back_populates="usuario", cascade="all, delete-orphan")
    feedbacks_comida = relationship(
        "FeedbackComida", back_populates="usuario", cascade="all, delete-orphan"
    )
    suscripciones = relationship(
        "Suscripcion", back_populates="usuario", cascade="all, delete-orphan"
    )


class SesionEntrenamiento(Base):
    __tablename__ = "sesiones_entrenamiento"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    tipo = Column(Enum(TipoEjercicio))
    subtipo = Column(Enum(SubtipoSesion), default=SubtipoSesion.SETS, nullable=False)
    duracion_min = Column(Integer)
    rpe_promedio = Column(Float)
    intensidad_1_10 = Column(Integer, nullable=True)
    num_caidas = Column(Integer, default=0)
    sensacion_1_5 = Column(Integer, nullable=True)
    spot = Column(String(120), nullable=True)
    deporte_slug = Column(String(48), nullable=True, index=True)
    trucos_intentados = Column(Integer, default=0)
    trucos_aterrizados = Column(Integer, default=0)
    rounds = Column(Integer, nullable=True)
    co_riders = Column(String(200), nullable=True)
    foco_sesion = Column(String(120), nullable=True)
    notas = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="sesiones")
    ejercicios = relationship(
        "EjercicioRealizado", back_populates="sesion", cascade="all, delete-orphan"
    )


class EjercicioRealizado(Base):
    __tablename__ = "ejercicios_realizados"

    id = Column(Integer, primary_key=True)
    sesion_id = Column(
        Integer, ForeignKey("sesiones_entrenamiento.id", ondelete="CASCADE"), nullable=False
    )
    nombre = Column(String(100), nullable=False)
    series = Column(Integer)
    reps = Column(Integer)
    peso_kg = Column(Float)
    rpe = Column(Float)

    sesion = relationship("SesionEntrenamiento", back_populates="ejercicios")


class Comida(Base):
    __tablename__ = "comidas"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    tipo = Column(Enum(TipoComida))
    alimentos = Column(Text)
    calorias = Column(Integer)
    proteinas_g = Column(Float)
    carbohidratos_g = Column(Float)
    grasas_g = Column(Float)

    usuario = relationship("Usuario", back_populates="comidas")


class PersonalRecord(Base):
    """PR polimorfico. Soporta:
    - PESO_REPS (gimnasio/powerlifting/halterofilia) - default back-compat
    - TIEMPO (running, natacion: ej PR de 5K en 22:15)
    - TRUCO (skate/BMX/rollers/parkour: ej "primer kickflip aterrizado")
    - GRADO (escalada: ej V6 boulder, 5.12a sport)
    - PROFUNDIDAD (apnea/buceo: ej 35m CWT)
    - WATTS (ciclismo: ej FTP 320w)
    - VELOCIDAD (patinaje velocidad, MTB)
    - RONDAS (combate: ej "primer KO en round 2")
    - CINTURON (BJJ/karate/TKD/judo: ej "purple belt BJJ")
    - DISTANCIA (running/ciclismo PR de distancia nueva)
    """

    __tablename__ = "personal_records"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    tipo_pr = Column(
        Enum(TipoPR), default=TipoPR.PESO_REPS, nullable=False, index=True
    )
    ejercicio = Column(String(100), nullable=False)
    peso_kg = Column(Float)
    reps = Column(Integer)
    fecha = Column(Date, default=date.today, index=True)
    deporte = Column(String(48), nullable=True, index=True)
    video_url = Column(String(300), nullable=True)
    spot = Column(String(120), nullable=True)
    grado = Column(String(16), nullable=True)
    tiempo_seg = Column(Float, nullable=True)
    profundidad_m = Column(Float, nullable=True)
    watts = Column(Integer, nullable=True)
    velocidad_kmh = Column(Float, nullable=True)
    rondas = Column(Integer, nullable=True)
    cinturon = Column(String(32), nullable=True)
    distancia_m = Column(Float, nullable=True)
    notas = Column(Text, nullable=True)

    usuario = relationship("Usuario", back_populates="prs")


class MetricaSueno(Base):
    __tablename__ = "metricas_sueno"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    horas = Column(Float)
    calidad = Column(Integer)
    notas = Column(String(300))

    usuario = relationship("Usuario", back_populates="sueno")


class MetricaCorporal(Base):
    __tablename__ = "metricas_corporales"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    peso_kg = Column(Float)
    grasa_pct = Column(Float)
    cintura_cm = Column(Float)

    usuario = relationship("Usuario", back_populates="metricas_corporales")


class Compromiso(Base):
    __tablename__ = "compromisos"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    objetivo_texto = Column(Text, nullable=False)
    fecha_firma = Column(Date, nullable=False, default=date.today)
    deadline = Column(Date, nullable=False)
    frecuencia_semanal = Column(Integer, nullable=False, default=3)
    tipo_compromiso = Column(Enum(TipoCompromiso), nullable=False, default=TipoCompromiso.GENERAL)
    stake_simbolico = Column(String(300), default="")
    activo = Column(Boolean, default=True, nullable=False, index=True)
    citado_veces = Column(Integer, default=0, nullable=False)
    pinned_message_id = Column(BigInteger)
    created_at = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="compromisos")


class EscalacionState(Base):
    __tablename__ = "escalacion_state"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    tipo_accion = Column(
        Enum(TipoAccionEscalacion), nullable=False, default=TipoAccionEscalacion.ENTRENO
    )
    level = Column(Integer, default=0, nullable=False)
    max_per_day = Column(Integer, default=4, nullable=False)
    mensajes_enviados_hoy = Column(Integer, default=0, nullable=False)
    ultimo_mensaje_id = Column(BigInteger)
    ultimo_envio = Column(DateTime)
    ultima_actualizacion = Column(DateTime, server_default=func.now(), onupdate=func.now())

    usuario = relationship("Usuario", back_populates="estados_escalacion")


class Streak(Base):
    __tablename__ = "streaks"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_streak = Column(Enum(TipoStreak), nullable=False, default=TipoStreak.ENTRENO)
    dias_actuales = Column(Integer, default=0, nullable=False)
    max_historico = Column(Integer, default=0, nullable=False)
    ultima_fecha = Column(Date)
    freezes_disponibles = Column(Integer, default=2, nullable=False)
    freezes_usados = Column(Integer, default=0, nullable=False)
    ultimo_freeze_regen = Column(Date, default=date.today)

    usuario = relationship("Usuario", back_populates="streaks")


class CheckinNocturno(Base):
    __tablename__ = "checkins_nocturnos"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    opcion_id = Column(Integer, nullable=False)
    respondido_via = Column(String(16), default="poll")
    creado_en = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="checkins")


class EventoBot(Base):
    __tablename__ = "eventos_bot"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    tipo_evento = Column(String(64), nullable=False, index=True)
    payload = Column(JSON)
    creado_en = Column(DateTime, server_default=func.now(), index=True)

    usuario = relationship("Usuario", back_populates="eventos")


class CrisisLog(Base):
    __tablename__ = "crisis_log"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    keywords_detectadas = Column(JSON)
    nivel = Column(Integer, nullable=False)
    mensaje_usuario = Column(Text)
    mensaje_enviado_id = Column(BigInteger)
    derivado_a = Column(String(120))
    creado_en = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="crisis")


class FeedbackComida(Base):
    __tablename__ = "feedback_comida"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fecha = Column(Date, nullable=False, default=date.today, index=True)
    foto_file_id = Column(String(256))
    alimentos_detectados = Column(JSON)
    calorias_estimadas = Column(Integer)
    proteinas_g = Column(Float)
    carbs_g = Column(Float)
    grasas_g = Column(Float)
    feedback_texto = Column(Text)
    creado_en = Column(DateTime, server_default=func.now())

    usuario = relationship("Usuario", back_populates="feedbacks_comida")


class Suscripcion(Base):
    __tablename__ = "suscripciones"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan = Column(Enum(PlanSuscripcion), default=PlanSuscripcion.FREE, nullable=False)
    telegram_payment_charge_id = Column(String(128), unique=True)
    star_amount = Column(Integer)
    iniciada_en = Column(DateTime, server_default=func.now())
    expira_en = Column(DateTime)
    activa = Column(Boolean, default=True, nullable=False)

    metodo_pago = Column(Enum(MetodoPago), default=MetodoPago.MANUAL_ADMIN, nullable=False)
    monto_cop = Column(Integer, nullable=True)
    comprobante_id = Column(
        Integer, ForeignKey("pagos_comprobantes.id", ondelete="SET NULL"), nullable=True
    )
    referido_aplicado = Column(Boolean, default=False, nullable=False)

    usuario = relationship("Usuario", back_populates="suscripciones")


class PlanDefinicion(Base):
    """Configuracion dinamica de planes (precios + features)."""

    __tablename__ = "plan_definicion"

    id = Column(Integer, primary_key=True)
    plan = Column(Enum(PlanSuscripcion), unique=True, nullable=False)
    precio_cop_mensual = Column(Integer, nullable=False, default=0)
    precio_cop_anual = Column(Integer, nullable=False, default=0)
    features = Column(JSON, nullable=False, default=dict)
    activo = Column(Boolean, default=True, nullable=False)
    actualizado_en = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PagoComprobante(Base):
    """Comprobante de pago subido por el usuario, validado por admin."""

    __tablename__ = "pagos_comprobantes"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    foto_file_id = Column(String(256))
    foto_sha256 = Column(String(64), unique=True, index=True)

    monto_cop = Column(Integer, nullable=True)
    monto_extraido_raw = Column(String(64), default="")
    monto_esperado_cop = Column(Integer, nullable=False, default=0)
    monto_match = Column(Boolean, default=False, nullable=False)
    referencia = Column(String(120), default="")
    cuenta_origen = Column(String(120), default="")
    cuenta_destino = Column(String(120), default="")

    fecha_pago = Column(DateTime, nullable=True)
    hora_pago = Column(Time, nullable=True)
    metodo = Column(Enum(MetodoPago), default=MetodoPago.OTRO, nullable=False)

    plan_solicitado = Column(
        Enum(PlanSuscripcion), default=PlanSuscripcion.STARTER, nullable=False
    )
    duracion_solicitada = Column(
        Enum(DuracionPago), default=DuracionPago.MENSUAL, nullable=False
    )
    dias_otorgados = Column(Integer, default=30, nullable=False)

    estado = Column(
        Enum(EstadoPago), default=EstadoPago.PENDIENTE_HUMANO, nullable=False, index=True
    )
    motivo_rechazo = Column(Text, nullable=True)

    vision_payload = Column(JSON, default=dict)
    revisado_por = Column(String(180), nullable=True)
    revisado_en = Column(DateTime, nullable=True)
    notas_admin = Column(Text, default="")
    referido_codigo = Column(String(32), nullable=True)

    creado_en = Column(DateTime, server_default=func.now(), index=True)


class UsuarioBloqueado(Base):
    """Usuario bloqueado por admin (fraude, comportamiento abusivo, etc)."""

    __tablename__ = "usuarios_bloqueados"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    motivo = Column(Text, nullable=False)
    bloqueado_por = Column(String(180), nullable=False)
    bloqueado_en = Column(DateTime, server_default=func.now(), nullable=False)


class Admin(Base):
    """Cuenta administrativa con acceso al panel web."""

    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    email = Column(String(180), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    rol = Column(Enum(RolAdmin), default=RolAdmin.SOPORTE, nullable=False)
    activo = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_login_at = Column(DateTime, nullable=True)


class IntegracionWearable(Base):
    """Conexion OAuth con un wearable (Whoop, Garmin, Strava, etc)."""

    __tablename__ = "integraciones_wearables"
    __table_args__ = ()

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proveedor = Column(String(32), nullable=False)
    access_token = Column(Text)
    refresh_token = Column(Text)
    expires_at = Column(DateTime, nullable=True)
    external_user_id = Column(String(120), default="")
    last_sync_at = Column(DateTime, nullable=True)
    sync_status = Column(String(32), default="pendiente")
    error_msg = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class DatosWearableRaw(Base):
    """Cada workout/sleep/etc descargado de un wearable."""

    __tablename__ = "datos_wearables_raw"

    id = Column(Integer, primary_key=True)
    integracion_id = Column(
        Integer, ForeignKey("integraciones_wearables.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    tipo = Column(String(32), nullable=False)
    external_id = Column(String(120), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    payload = Column(JSON, default=dict)
    procesado = Column(Boolean, default=False, nullable=False)
    procesado_en = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class PlanSemanal(Base):
    """Plan semanal generado por LLM o manual."""

    __tablename__ = "planes_semanales"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    semana_inicio = Column(Date, nullable=False, index=True)
    plan_json = Column(JSON, nullable=False, default=dict)
    generado_por = Column(String(16), default="llm")
    creado_en = Column(DateTime, server_default=func.now())


class ConsumoAgua(Base):
    """Registro de hidratacion."""

    __tablename__ = "consumo_agua"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ml = Column(Integer, nullable=False)
    registrado_en = Column(DateTime, server_default=func.now(), index=True)


class Desafio(Base):
    """Desafios semanales/mensuales de la comunidad."""

    __tablename__ = "desafios"

    id = Column(Integer, primary_key=True)
    slug = Column(String(64), unique=True, nullable=False)
    titulo = Column(String(180), nullable=False)
    descripcion = Column(Text, default="")
    fecha_inicio = Column(Date, nullable=False)
    fecha_fin = Column(Date, nullable=False)
    tipo = Column(String(32), default="dias")
    creado_en = Column(DateTime, server_default=func.now())


class DesafioParticipante(Base):
    __tablename__ = "desafios_participantes"

    id = Column(Integer, primary_key=True)
    desafio_id = Column(
        Integer, ForeignKey("desafios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    valor_actual = Column(Float, default=0.0, nullable=False)
    posicion = Column(Integer, nullable=True)
    inscripto_en = Column(DateTime, server_default=func.now())


class Kudos(Base):
    """Kudos entre usuarios (PR, streak, etc)."""

    __tablename__ = "kudos"

    id = Column(Integer, primary_key=True)
    usuario_origen = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    usuario_destino = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo = Column(String(32), default="pr")
    creado_en = Column(DateTime, server_default=func.now(), index=True)


class MagicLink(Base):
    """Magic links para auth web (Fase 9)."""

    __tablename__ = "magic_links"

    id = Column(Integer, primary_key=True)
    token = Column(String(128), unique=True, nullable=False, index=True)
    email = Column(String(180), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class RealtimeSesion(Base):
    """Sesion de llamada con coach via OpenAI Realtime API."""

    __tablename__ = "realtime_sesiones"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    iniciada_en = Column(DateTime, server_default=func.now(), index=True)
    terminada_en = Column(DateTime, nullable=True)
    duracion_segundos = Column(Integer, default=0)
    tono_usado = Column(String(16), default="firme")
    tokens_input = Column(Integer, default=0)
    tokens_output = Column(Integer, default=0)
    costo_estimado_usd = Column(Float, default=0.0)
    transcript = Column(Text, default="")


class DeporteCatalogo(Base):
    """Catalogo maestro de los 67+ deportes soportados en Colombia.

    Seed inicial via alembic 0005. Permite agregar deportes nuevos sin
    redeploys (admin via /admin/stats o script). Cada deporte mapea a
    una CategoriaDeporte que determina el sub-prompt del coach (REGLA #11).
    """

    __tablename__ = "deportes_catalogo"

    id = Column(Integer, primary_key=True)
    slug = Column(String(48), unique=True, nullable=False, index=True)
    nombre_es = Column(String(80), nullable=False)
    nombre_en = Column(String(80), default="")
    categoria = Column(String(32), nullable=False, index=True)
    escena_co = Column(String(200), default="")
    plataforma_externa = Column(String(32), default="")
    vocabulario = Column(JSON, default=list)
    metricas = Column(JSON, default=list)
    equipamiento = Column(JSON, default=list)
    spots_colombia = Column(JSON, default=list)
    referentes_colombia = Column(JSON, default=list)
    federacion = Column(String(120), default="")
    activo = Column(Boolean, default=True, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
