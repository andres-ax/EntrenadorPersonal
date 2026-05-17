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
    PRO = "pro"


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
    modo_militar_aceptado_en = Column(DateTime)
    bot_bloqueado = Column(Boolean, default=False, nullable=False)
    pausado_hasta = Column(Date)
    quiet_hours_inicio = Column(Time, default=time(22, 0), nullable=False)
    quiet_hours_fin = Column(Time, default=time(7, 0), nullable=False)
    pais = Column(String(8), default="CO", nullable=False)

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
    duracion_min = Column(Integer)
    rpe_promedio = Column(Float)
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
    __tablename__ = "personal_records"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(
        Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    ejercicio = Column(String(100), nullable=False)
    peso_kg = Column(Float, nullable=False)
    reps = Column(Integer)
    fecha = Column(Date, default=date.today)

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

    usuario = relationship("Usuario", back_populates="suscripciones")
