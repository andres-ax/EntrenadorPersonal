import enum
from datetime import date

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
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
    created_at = Column(DateTime, server_default=func.now())

    sesiones = relationship("SesionEntrenamiento", back_populates="usuario", cascade="all, delete-orphan")
    comidas = relationship("Comida", back_populates="usuario", cascade="all, delete-orphan")
    prs = relationship("PersonalRecord", back_populates="usuario", cascade="all, delete-orphan")
    sueno = relationship("MetricaSueno", back_populates="usuario", cascade="all, delete-orphan")
    metricas_corporales = relationship("MetricaCorporal", back_populates="usuario", cascade="all, delete-orphan")


class SesionEntrenamiento(Base):
    __tablename__ = "sesiones_entrenamiento"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
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
    sesion_id = Column(Integer, ForeignKey("sesiones_entrenamiento.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(String(100), nullable=False)
    series = Column(Integer)
    reps = Column(Integer)
    peso_kg = Column(Float)
    rpe = Column(Float)

    sesion = relationship("SesionEntrenamiento", back_populates="ejercicios")


class Comida(Base):
    __tablename__ = "comidas"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
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
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    ejercicio = Column(String(100), nullable=False)
    peso_kg = Column(Float, nullable=False)
    reps = Column(Integer)
    fecha = Column(Date, default=date.today)

    usuario = relationship("Usuario", back_populates="prs")


class MetricaSueno(Base):
    __tablename__ = "metricas_sueno"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    horas = Column(Float)
    calidad = Column(Integer)
    notas = Column(String(300))

    usuario = relationship("Usuario", back_populates="sueno")


class MetricaCorporal(Base):
    __tablename__ = "metricas_corporales"

    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False)
    fecha = Column(Date, nullable=False, default=date.today)
    peso_kg = Column(Float)
    grasa_pct = Column(Float)
    cintura_cm = Column(Float)

    usuario = relationship("Usuario", back_populates="metricas_corporales")
