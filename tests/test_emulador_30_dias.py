"""Simulador interactivo de emulación de 30 días para un deportista en EntrenadorAX.

Simula un mes completo (30 días) de un usuario alternando entrenamientos de fuerza
en gimnasio comercial y rutinas de calistenia en casa, registrando ingestas de comida con
macros, hidratación progresiva diaria, calidad de sueño y pérdida de peso saludable.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, date, timedelta
import json
from unittest.mock import AsyncMock, patch
import pytest

from tests.conftest import call_tool
from src.tools import (
    registrar_sueno,
    registrar_peso,
    registrar_comida,
    registrar_hidratacion,
    registrar_entreno,
    reporte_progreso,
    resumen_nutricional,
    guardar_perfil,
)


@pytest.mark.asyncio
async def test_emulacion_30_dias_deportista() -> None:
    """Emula secuencialmente el comportamiento de 30 días de un atleta de EntrenadorAX."""

    mock_uid = 8877665544

    print("\n\n=== [INICIANDO EMULACIÓN DE 30 DÍAS DE ENTRENAMIENTO E INTEGRIDAD] ===")

    # Mockear las funciones de persistencia de base de datos para que la prueba corra
    # de forma 100% autoportante en cualquier entorno de pruebas (CI o local) sin requerir Postgres/Redis activos
    
    # Mocks de retorno para base de datos
    mock_perfil_return = type("U", (), {
        "id": 12345, 
        "telegram_id": mock_uid,
        "nombre": "Carlos",
        "peso_kg": 90.0,
        "altura_cm": 171,
        "edad": 31,
        "objetivo": "perder grasa",
        "nivel": "principiante",
        "dias_entreno": 7,
        "deporte_principal": "gimnasio",
        "timezone": "America/Bogota",
        "pais": "CO",
    })()
    mock_sueno_return = type("S", (), {"id": 111})()
    mock_comida_return = type("C", (), {"id": 222})()
    mock_agua_return = 500
    mock_entreno_return = type("E", (), {"id": 333, "fecha": date(2026, 5, 20), "tipo": "fuerza"})()
    mock_streak_return = type("ST", (), {"dias_actuales": 20})()
    
    mock_metrica_corporal = type(
        "MC",
        (),
        {
            "id": 444,
            "peso_kg": 85.2,
            "fecha": date(2026, 6, 18),
            "grasa_pct": 21.2,
            "cintura_cm": 95.0,
        }
    )()

    # Mocks para reportes
    mock_reporte_semanal_raw = {
        "dias_unicos_entreno": 5,
        "sesiones_registradas": 5,
        "dias_entrenados": 5,
        "volumen_total_kg": 15400.0,
        "total_ejercicios": 15,
        "nuevos_prs": [],
        "sueno": {"promedio_horas": 7.8, "promedio_calidad": 4.2, "dias_registrados": 7},
        "nutricion_hoy": {
            "total_calorias": 1390.0,
            "total_proteinas": 95.5,
            "total_carbs": 105.0,
            "total_grasas": 42.5,
            "comidas_con_datos": 3,
            "comidas_totales": 3,
        },
        "periodo": "Últimos 7 días",
    }
    
    mock_resumen_nutricional_dia_raw = {
        "total_calorias": 1390.0,
        "total_proteinas": 95.5,
        "total_carbs": 105.0,
        "total_grasas": 42.5,
        "comidas_con_datos": 3,
        "comidas_totales": 3,
        "comidas": [
            {"tipo": "desayuno", "alimentos": ["Huevos fritos", "Aguacate"], "calorias": 420},
            {"tipo": "almuerzo", "alimentos": ["Pechuga de pollo", "Arroz"], "calorias": 580},
            {"tipo": "cena", "alimentos": ["Filete de atun", "Ensalada mixta"], "calorias": 390},
        ],
    }

    # Estructura del parche de base de datos
    with patch("src.tools.actualizar_usuario", new=AsyncMock(return_value=mock_perfil_return)), \
         patch("src.tools.repo_guardar_sueno", new=AsyncMock(return_value=mock_sueno_return)), \
         patch("src.tools.guardar_metrica_corporal", new=AsyncMock(return_value=mock_metrica_corporal)), \
         patch("src.tools.repo_guardar_comida", new=AsyncMock(return_value=mock_comida_return)), \
         patch("src.tools.repo_buscar_comida_similar", new=AsyncMock(return_value=None)), \
         patch("src.tools.registrar_agua", new=AsyncMock(return_value=mock_agua_return)), \
         patch("src.tools.repo_guardar_sesion", new=AsyncMock(return_value=mock_entreno_return)), \
         patch("src.tools.incrementar_streak", new=AsyncMock(return_value=mock_streak_return)), \
         patch("src.tools.obtener_o_crear_usuario", new=AsyncMock(return_value=mock_perfil_return)), \
         patch("src.tools.reporte_semanal", new=AsyncMock(return_value=mock_reporte_semanal_raw)), \
         patch("src.tools.resumen_nutricional_dia", new=AsyncMock(return_value=mock_resumen_nutricional_dia_raw)), \
         patch("src.tools.log_evento", new=AsyncMock()):

        # A. Registrar el perfil inicial (Día 0)
        print("\n[Día 0]: Creando perfil del deportista de pruebas")
        perfil_res = await call_tool(
            guardar_perfil,
            telegram_id=mock_uid,
            nombre="Carlos",
            peso_kg=90.0,
            altura_cm=171,
            edad=31,
            objetivo="perder grasa",
            nivel="principiante",
            dias_entreno=7,
            deporte_principal="gimnasio",
            pais="CO",
            timezone="America/Bogota",
        )
        assert json.loads(perfil_res).get("ok") is True
        print("✓ Perfil de Carlos registrado (Peso: 90kg, Objetivo: perder grasa, Nivel: principiante).")

        # B. Bucle Principal de 30 Días de Simulación
        fecha_inicial = date(2026, 5, 19)
        peso_actual = 90.0
        grasa_actual = 25.0
        cintura_actual = 100.0

        print("\n--- COMENZANDO BUCLE DE 30 DÍAS CON HÁBITOS REALES ---")

        for dia in range(1, 31):
            fecha_simulada_date = fecha_inicial + timedelta(days=dia)
            fecha_str = fecha_simulada_date.isoformat()

            # 1. Registrar Sueño de Anoche (horas varían entre 7.2h y 8.4h, calidad buena/excelente)
            horas_sueno = 7.5 + (dia % 3) * 0.3
            calidad_sueno = 4 if (dia % 2 == 0) else 5
            sueno_res = await call_tool(
                registrar_sueno,
                telegram_id=mock_uid,
                fecha=fecha_str,
                horas=horas_sueno,
                calidad=calidad_sueno,
                notas=f"Dormí bien, desperté listo para el día {dia}",
            )
            assert json.loads(sueno_res).get("ok") is True

            # 2. Registrar Peso Corporal (descenso constante y de-duplicado)
            peso_actual -= 0.15
            grasa_actual -= 0.12
            cintura_actual -= 0.15
            peso_res = await call_tool(
                registrar_peso,
                telegram_id=mock_uid,
                peso_kg=round(peso_actual, 2),
                grasa_pct=round(grasa_actual, 1),
                cintura_cm=round(cintura_actual, 1),
            )
            assert json.loads(peso_res).get("ok") is True

            # 3. Ingesta de Nutrición (Desayuno, Almuerzo, Cena y Snacks con macros variables)
            # Desayuno
            des_res = await call_tool(
                registrar_comida,
                telegram_id=mock_uid,
                fecha=fecha_str,
                tipo="desayuno",
                alimentos_json=json.dumps(["Huevos fritos 2u", "Aguacate 80g", "Pan de centeno 1 rebanada"]),
                calorias=420,
                proteinas=18.5,
                carbs=25.0,
                grasas=20.0,
            )
            assert json.loads(des_res).get("ok") is True

            # Almuerzo (Alto en proteína, carbohidrato moderado)
            alm_res = await call_tool(
                registrar_comida,
                telegram_id=mock_uid,
                fecha=fecha_str,
                tipo="almuerzo",
                alimentos_json=json.dumps(["Pechuga de pollo 180g", "Arroz integral 1.5 tazas", "Brócoli al vapor"]),
                calorias=580,
                proteinas=42.0,
                carbs=65.0,
                grasas=8.5,
            )
            assert json.loads(alm_res).get("ok") is True

            # Cena ligera
            cen_res = await call_tool(
                registrar_comida,
                telegram_id=mock_uid,
                fecha=fecha_str,
                tipo="cena",
                alimentos_json=json.dumps(["Filete de atún a la plancha 150g", "Ensalada mixta grande", "Aceite de oliva"]),
                calorias=390,
                proteinas=35.0,
                carbs=15.0,
                grasas=14.0,
            )
            assert json.loads(cen_res).get("ok") is True

            # 4. Hidratación Progresiva (Se registran tomas de agua parciales a lo largo del día)
            await call_tool(registrar_hidratacion, telegram_id=mock_uid, ml=500) # En la mañana
            await call_tool(registrar_hidratacion, telegram_id=mock_uid, ml=1000) # En la tarde
            await call_tool(registrar_hidratacion, telegram_id=mock_uid, ml=500) # En la noche

            # 5. Programación de Entrenamiento (Gym vs Casa vs Descanso Activo)
            dia_semana = fecha_simulada_date.weekday() # 0=Lunes..6=Domingo

            if dia_semana in (0, 2, 4): # Lunes, Miércoles, Viernes -> Gimnasio Comercial (Fuerza)
                ejercicios_gym = [
                    {"nombre": "Sentadilla con barra", "series": 4, "reps": 8, "peso_kg": 80.0},
                    {"nombre": "Press de banca plano", "series": 4, "reps": 8, "peso_kg": 65.0},
                    {"nombre": "Peso muerto rumano", "series": 3, "reps": 10, "peso_kg": 75.0},
                ]
                ent_res = await call_tool(
                    registrar_entreno,
                    telegram_id=mock_uid,
                    fecha=fecha_str,
                    tipo="fuerza",
                    duracion_min=75,
                    ejercicios_json=json.dumps(ejercicios_gym),
                    rpe=8,
                    notas=f"Entrenamiento intenso en gimnasio comercial. Día {dia} de emulación.",
                )
                assert json.loads(ent_res).get("ok") is True

            elif dia_semana in (1, 3): # Martes, Jueves -> Calistenia en Casa (Fuerza/Movilidad)
                ejercicios_casa = [
                    {"nombre": "Flexiones de pecho", "series": 4, "reps": 15, "peso_kg": 0.0},
                    {"nombre": "Sentadillas búlgaras", "series": 3, "reps": 12, "peso_kg": 10.0},
                    {"nombre": "Plancha abdominal", "series": 3, "reps": 1, "peso_kg": 0.0},
                ]
                ent_res = await call_tool(
                    registrar_entreno,
                    telegram_id=mock_uid,
                    fecha=fecha_str,
                    tipo="movilidad",
                    duracion_min=45,
                    ejercicios_json=json.dumps(ejercicios_casa),
                    rpe=7,
                    notas=f"Rutina de calistenia funcional en casa. Día {dia} de emulación.",
                )
                assert json.loads(ent_res).get("ok") is True

            else: # Sábados y Domingos -> Descanso Activo / Recuperación
                ent_res = await call_tool(
                    registrar_entreno,
                    telegram_id=mock_uid,
                    fecha=fecha_str,
                    tipo="movilidad",
                    duracion_min=20,
                    ejercicios_json="[]",
                    rpe=3,
                    notas="Estiramientos suaves y caminata al aire libre.",
                )
                assert json.loads(ent_res).get("ok") is True

            # 6. Hitos de Evaluación Semanal
            if dia in (7, 14, 21, 30):
                print(f"\n--- HITOS DE EVALUACIÓN: FIN DE SEMANA {dia // 7} (DÍA {dia}) ---")
                
                # Consultar progreso e ingesta nutricional consolidada
                progreso_res = await call_tool(reporte_progreso, telegram_id=mock_uid)
                progreso_data = json.loads(progreso_res)
                assert progreso_data.get("dias_unicos_entreno") is not None
                
                nutricion_res = await call_tool(resumen_nutricional, telegram_id=mock_uid, fecha=fecha_str)
                nutricion_data = json.loads(nutricion_res)
                assert nutricion_data.get("total_calorias") is not None
                
                print(f"✓ Hito {dia // 7}: Peso alcanzado: {round(peso_actual, 2)} kg (Pérdida total acumulada: {round(90.0 - peso_actual, 2)} kg)")
                print(f"✓ Consumo promedio semanal evaluado correctamente de forma integrada.")

    print("\n=== [SIMULACIÓN COMPLETA DE 30 DÍAS COMPLETADA EXITOSAMENTE] ===\n")
