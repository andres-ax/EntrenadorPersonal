"""Tabla deportes_catalogo + columnas categoria_deporte en usuarios + seed 67 deportes.

Basado en research/deportes-colombia-expansion.md (1613 lineas).

Revision ID: 0005_seed_deportes
Revises: 0004_wearables_comunidad
Create Date: 2026-05-17

Cambios:
- CREATE TABLE deportes_catalogo con metadata por deporte.
- ALTER TABLE usuarios: +categoria_deporte, +modalidad_deporte, +anos_practica,
  +es_competitivo.
- INSERT 67 deportes con vocabulario, metricas, spots Colombia, referentes.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_seed_deportes"
down_revision: Union[str, None] = "0004_wearables_comunidad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CATEGORIAS = (
    "urbano combate escalada acuatico equipo outdoor_endurance "
    "indoor_fuerza ecuestre motor tradicional_co otro"
).split()


DEPORTES_SEED = [
    # ===== URBANO (BMX, skate, rollers, parkour, surf, kite, sup) =====
    {
        "slug": "bmx", "nombre_es": "BMX", "nombre_en": "BMX",
        "categoria": "urbano",
        "escena_co": "Bogota (Salitre), Cali (Pance), Medellin (Aranjuez)",
        "plataforma_externa": "instagram",
        "vocabulario": ["bunny hop", "manual", "tabletop", "x-up", "tailwhip", "barspin", "flair", "180", "360", "backflip"],
        "metricas": ["trucos_aterrizados", "sesion_min", "spots", "competencias"],
        "equipamiento": ["bmx_completa", "casco_full_face", "rodilleras", "guantes", "gafas"],
        "spots_colombia": ["Salitre BMX Bogota", "Pista Pance Cali", "Skatepark Aranjuez Medellin"],
        "referentes_colombia": ["Mariana Pajon", "Carlos Ramirez", "Luis Rincon", "Juan Caicedo"],
        "federacion": "Federacion Colombiana de Ciclismo (rama BMX)",
    },
    {
        "slug": "skate", "nombre_es": "Skate", "nombre_en": "Skateboarding",
        "categoria": "urbano",
        "escena_co": "Bogota (Fontanar, Salitre), Medellin (11 skateparks 2026), Cali, Barranquilla",
        "plataforma_externa": "instagram",
        "vocabulario": ["ollie", "kickflip", "heelflip", "varial", "shuvit", "manual", "grind 50-50", "5-0", "smith", "boardslide", "lipslide", "drop in"],
        "metricas": ["trucos_aterrizados", "sesion_min", "spots", "linea_completada"],
        "equipamiento": ["skate", "casco", "rodilleras", "muniqueras", "coderas"],
        "spots_colombia": ["Skatepark Fontanar Bogota", "Salitre Bogota", "Aranjuez Medellin", "Malecon Barranquilla"],
        "referentes_colombia": ["Jhancarlos Gonzalez", "Lourdes Escobar"],
        "federacion": "Fedepatin (rama skate desde Tokyo 2020)",
    },
    {
        "slug": "rollers", "nombre_es": "Patinaje agresivo / rollers",
        "nombre_en": "Aggressive inline skating",
        "categoria": "urbano",
        "escena_co": "Bogota (Simon Bolivar, Salitre), Medellin (Ingravity), Cali (cuna del patinaje)",
        "plataforma_externa": "instagram",
        "vocabulario": ["soul grind", "royale", "fishbrain", "topsoul", "alley-oop", "180", "360"],
        "metricas": ["trucos_aterrizados", "sesion_min", "spots"],
        "equipamiento": ["patines_agresivos", "casco", "rodilleras", "muniqueras"],
        "spots_colombia": ["Simon Bolivar Bogota", "Ingravity Roller Medellin"],
        "referentes_colombia": ["Escena LS Patina", "Solidos Roller Shop"],
        "federacion": "Fedepatin",
    },
    {
        "slug": "patinaje_velocidad", "nombre_es": "Patinaje de velocidad",
        "nombre_en": "Speed skating", "categoria": "urbano",
        "escena_co": "Cali, Medellin, Pereira, Bogota",
        "plataforma_externa": "strava",
        "vocabulario": ["pista", "ruta", "vuelta", "drafting", "salida", "punto"],
        "metricas": ["tiempo_distancia", "velocidad_promedio", "podios"],
        "equipamiento": ["patines_speed", "casco", "lycra"],
        "spots_colombia": ["Velodromo Alberto Galindo Cali", "Pista San Carlos Medellin"],
        "referentes_colombia": ["Cecilia Baena", "Pedro Causil", "Geiny Pajaro", "Andres Felipe Munoz", "Kollin Castro"],
        "federacion": "Fedepatin (21 mundiales totales)",
    },
    {
        "slug": "patinaje_artistico", "nombre_es": "Patinaje artistico",
        "nombre_en": "Artistic skating", "categoria": "urbano",
        "escena_co": "Cali, Medellin, Bogota, Pereira",
        "plataforma_externa": "instagram",
        "vocabulario": ["axel", "loop", "salchow", "flip", "lutz", "spiral", "spin"],
        "metricas": ["coreografia_min", "saltos_aterrizados", "competencias"],
        "equipamiento": ["patines_artisticos", "vestuario"],
        "spots_colombia": ["Pista cubierta Cali", "Coliseo Iván de Bedout Medellin"],
        "referentes_colombia": ["Selección Colombia patinaje artistico"],
        "federacion": "Fedepatin",
    },
    {
        "slug": "scooter", "nombre_es": "Scooter freestyle",
        "nombre_en": "Scooter freestyle", "categoria": "urbano",
        "escena_co": "Bogota, Medellin", "plataforma_externa": "instagram",
        "vocabulario": ["tailwhip", "barspin", "bri flip", "no hander", "manual"],
        "metricas": ["trucos_aterrizados", "sesion_min"],
        "equipamiento": ["scooter", "casco", "rodilleras"],
        "spots_colombia": ["Skateparks compartidos con BMX/skate"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "parkour", "nombre_es": "Parkour / Freerunning",
        "nombre_en": "Parkour / Freerunning", "categoria": "urbano",
        "escena_co": "Bogota, Medellin", "plataforma_externa": "instagram",
        "vocabulario": ["wallrun", "vault", "precision", "kong", "dash", "lazy", "speed"],
        "metricas": ["distancia_run", "spots", "sesion_min"],
        "equipamiento": ["zapatillas_parkour", "ropa_libre"],
        "spots_colombia": ["Parque Simon Bolivar", "Universidad Nacional Bogota"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "surf", "nombre_es": "Surf", "nombre_en": "Surf",
        "categoria": "urbano",
        "escena_co": "Pacifico (Nuqui, Pizarro, Juanchaco), Caribe (Palomino, Cabo de la Vela)",
        "plataforma_externa": "instagram",
        "vocabulario": ["take off", "drop", "cutback", "bottom turn", "tubo", "ola"],
        "metricas": ["sesiones", "olas_cogidas", "tubos"],
        "equipamiento": ["tabla_surf", "leash", "lycra_protectora"],
        "spots_colombia": ["Nuqui Choco", "Palomino Guajira", "Pizarro Choco"],
        "referentes_colombia": ["Giorgio Gomez"],
        "federacion": "Federacion Colombiana de Surf",
    },
    {
        "slug": "kitesurf", "nombre_es": "Kitesurf", "nombre_en": "Kitesurfing",
        "categoria": "urbano",
        "escena_co": "Cabo de la Vela (Guajira), Cartagena, Salgar",
        "plataforma_externa": "instagram",
        "vocabulario": ["edge", "loop", "kiteloop", "jump", "transitions"],
        "metricas": ["horas_agua", "sesiones", "vientos"],
        "equipamiento": ["kite", "barra", "tabla", "arnes", "casco"],
        "spots_colombia": ["Cabo de la Vela", "Salgar Bolivar", "Cartagena"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "sup", "nombre_es": "Stand-up Paddle (SUP)",
        "nombre_en": "Stand-up Paddle", "categoria": "urbano",
        "escena_co": "Cartagena, Santa Marta, Guatape, Tominé",
        "plataforma_externa": "strava",
        "vocabulario": ["stroke", "pivot turn", "race", "downwind"],
        "metricas": ["km_remados", "tiempo"],
        "equipamiento": ["tabla_sup", "remo", "leash", "chaleco"],
        "spots_colombia": ["Bahia Cartagena", "Embalse Tomine"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "slacklining", "nombre_es": "Slacklining / Highline",
        "nombre_en": "Slacklining", "categoria": "urbano",
        "escena_co": "Suesca, Bogota, San Gil", "plataforma_externa": "instagram",
        "vocabulario": ["chest bounce", "buttbounce", "leash fall", "exposure"],
        "metricas": ["metros_caminados", "altura_max", "sends"],
        "equipamiento": ["slackline", "anclajes", "leash"],
        "spots_colombia": ["Suesca", "Cerros Bogota"],
        "referentes_colombia": [],
        "federacion": "",
    },

    # ===== ESCALADA =====
    {
        "slug": "climbing", "nombre_es": "Escalada deportiva / boulder",
        "nombre_en": "Sport climbing / bouldering", "categoria": "escalada",
        "escena_co": "Suesca (5.5 a 5.13), San Gil (La Mojarra), Macheta, Penol, Tatacoa",
        "plataforma_externa": "instagram",
        "vocabulario": ["on sight", "flash", "redpoint", "boulder", "crimper", "sloper", "drop knee", "heel hook"],
        "metricas": ["vias_enviadas", "grado_max", "horas_pared", "lesiones_dedos"],
        "equipamiento": ["pies_de_gato", "magnesio", "arnes", "cuerda", "cintas_exprés", "casco"],
        "spots_colombia": ["Suesca", "La Mojarra San Gil", "Macheta Cundinamarca", "El Penol Antioquia", "Toluviejo Sucre", "Tatacoa Huila"],
        "referentes_colombia": ["Manuel Knott", "Comunidad Escalada CO"],
        "federacion": "Federacion Colombiana de Escalada (FECODE)",
    },

    # ===== COMBATE =====
    {
        "slug": "boxeo", "nombre_es": "Boxeo", "nombre_en": "Boxing",
        "categoria": "combate", "escena_co": "Todo el pais (Yuberjen Martinez, Ceiber Avila)",
        "plataforma_externa": "instagram",
        "vocabulario": ["jab", "cross", "hook", "uppercut", "slip", "weave", "round", "sparring", "drilling", "footwork"],
        "metricas": ["rounds_sparring", "intensidad", "peleas", "cinturones"],
        "equipamiento": ["guantes", "vendas", "protector_bucal", "saco", "ring"],
        "spots_colombia": ["Coliseo del Salitre Bogota", "Gimnasios Cali"],
        "referentes_colombia": ["Yuberjen Martinez", "Ceiber Avila", "Ingrit Valencia"],
        "federacion": "Federacion Colombiana de Boxeo",
    },
    {
        "slug": "muay_thai", "nombre_es": "Muay Thai", "nombre_en": "Muay Thai",
        "categoria": "combate", "escena_co": "Bogota, Medellin, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["jab", "low kick", "round kick", "teep", "clinch", "elbow", "knee", "sweep"],
        "metricas": ["rounds_sparring", "intensidad", "peleas", "cinturones"],
        "equipamiento": ["guantes", "shin_guards", "vendas", "protector_bucal", "saco"],
        "spots_colombia": ["Gimnasios MT Bogota", "Medellin", "Cali"],
        "referentes_colombia": [],
        "federacion": "Federacion Colombiana de Muay Thai (FCMT, junio 2024)",
    },
    {
        "slug": "bjj", "nombre_es": "Brazilian Jiu-Jitsu",
        "nombre_en": "Brazilian Jiu-Jitsu", "categoria": "combate",
        "escena_co": "Medellin (escena fuerte), Bogota, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["guard", "mount", "side control", "back take", "armbar", "triangle", "rear naked choke", "kimura", "rolls"],
        "metricas": ["rolls_min", "sumisiones", "grado_cinturon", "campeonatos"],
        "equipamiento": ["gi", "no_gi_rashguard", "protector_bucal"],
        "spots_colombia": ["Gimnasios Medellin BJJ", "Bogota academias"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "mma", "nombre_es": "MMA", "nombre_en": "MMA",
        "categoria": "combate", "escena_co": "Medellin, Bogota",
        "plataforma_externa": "instagram",
        "vocabulario": ["sprawl", "ground and pound", "takedown", "transition", "guard pull", "cage work"],
        "metricas": ["sesiones_sparring", "peleas", "peso_pesaje_vs_dia", "round_kos"],
        "equipamiento": ["guantes_mma", "shinguards", "boca", "rashguard"],
        "spots_colombia": ["Gimnasios MMA Medellin, Bogota"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "karate", "nombre_es": "Karate", "nombre_en": "Karate",
        "categoria": "combate", "escena_co": "Todo el pais",
        "plataforma_externa": "instagram",
        "vocabulario": ["kata", "kumite", "kihon", "mae geri", "mawashi geri", "gyaku zuki", "obi"],
        "metricas": ["katas_dominados", "kumite_rounds", "grado_obi", "campeonatos"],
        "equipamiento": ["gi_karate", "obi", "protector_bucal", "protector_genital"],
        "spots_colombia": ["Dojos en todo el pais"],
        "referentes_colombia": [],
        "federacion": "Federacion Colombiana de Karate",
    },
    {
        "slug": "taekwondo", "nombre_es": "Taekwondo", "nombre_en": "Taekwondo",
        "categoria": "combate", "escena_co": "Todo el pais (Yuri Alvear medalla olimpica)",
        "plataforma_externa": "instagram",
        "vocabulario": ["dolyo chagi", "naeryeo chagi", "yop chagi", "hwechook", "poomsae", "kyorugi"],
        "metricas": ["poomsae_dominados", "rounds_sparring", "grado_dan", "campeonatos"],
        "equipamiento": ["dobok", "peto", "casco", "protectores"],
        "spots_colombia": ["Coliseo El Salitre Bogota", "Dojos por pais"],
        "referentes_colombia": ["Yuri Alvear", "Maria del Rosario Espinoza"],
        "federacion": "Federacion Colombiana de Taekwondo",
    },
    {
        "slug": "judo", "nombre_es": "Judo", "nombre_en": "Judo",
        "categoria": "combate", "escena_co": "Cali, Bogota",
        "plataforma_externa": "instagram",
        "vocabulario": ["uchi mata", "o soto gari", "ippon seoi nage", "tai otoshi", "newaza", "tachi waza"],
        "metricas": ["ippones", "randori", "grado_dan", "campeonatos"],
        "equipamiento": ["judogi", "obi"],
        "spots_colombia": ["Dojos por pais"],
        "referentes_colombia": ["Yuri Alvear (multi medallista)"],
        "federacion": "Federacion Colombiana de Judo",
    },
    {
        "slug": "kickboxing", "nombre_es": "Kickboxing / K-1",
        "nombre_en": "Kickboxing", "categoria": "combate",
        "escena_co": "Bogota, Medellin", "plataforma_externa": "instagram",
        "vocabulario": ["jab", "cross", "hook", "round kick", "low kick", "teep", "switch kick"],
        "metricas": ["rounds_sparring", "peleas", "cinturones"],
        "equipamiento": ["guantes", "shinguards", "vendas", "boca"],
        "spots_colombia": ["Gimnasios"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "wrestling", "nombre_es": "Lucha (libre/grecorromana)",
        "nombre_en": "Wrestling", "categoria": "combate",
        "escena_co": "Bolivar, Cundinamarca, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["takedown", "single leg", "double leg", "sprawl", "pin", "escape"],
        "metricas": ["pins", "rounds", "peso_categoria"],
        "equipamiento": ["singlet", "headgear", "zapatillas_wrestling"],
        "spots_colombia": [],
        "referentes_colombia": ["Yackeline Renteria"],
        "federacion": "Federacion Colombiana de Lucha",
    },
    {
        "slug": "capoeira", "nombre_es": "Capoeira", "nombre_en": "Capoeira",
        "categoria": "combate", "escena_co": "Bogota, Medellin, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["ginga", "au", "meia lua", "armada", "esquiva", "roda", "corda"],
        "metricas": ["movimentos", "rodas", "corda"],
        "equipamiento": ["abada_blanco", "corda"],
        "spots_colombia": ["Grupos en Bogota"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "krav_maga", "nombre_es": "Krav Maga", "nombre_en": "Krav Maga",
        "categoria": "combate", "escena_co": "Bogota, Medellin",
        "plataforma_externa": "instagram",
        "vocabulario": ["defensa", "control", "tomas", "drills"],
        "metricas": ["niveles", "sesiones"],
        "equipamiento": ["sparring_gear"],
        "spots_colombia": [],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "esgrima", "nombre_es": "Esgrima",
        "nombre_en": "Fencing", "categoria": "combate",
        "escena_co": "Bogota, Cali", "plataforma_externa": "",
        "vocabulario": ["estocada", "parada", "riposte", "lunge", "fleche", "florete", "espada", "sable"],
        "metricas": ["touches", "asaltos", "ranking"],
        "equipamiento": ["chaqueta_electrica", "mascara", "guante", "florete_espada_sable"],
        "spots_colombia": ["Liga de Esgrima Bogota"],
        "referentes_colombia": ["Saskia van Erven"],
        "federacion": "Federacion Colombiana de Esgrima",
    },

    # ===== EQUIPO =====
    {
        "slug": "futbol", "nombre_es": "Futbol", "nombre_en": "Soccer",
        "categoria": "equipo", "escena_co": "Todo el pais (deporte rey)",
        "plataforma_externa": "instagram",
        "vocabulario": ["gol", "asistencia", "regate", "pase", "presion", "linea", "centro", "tiro"],
        "metricas": ["partidos", "minutos_jugados", "goles", "asistencias"],
        "equipamiento": ["guayos", "canilleras", "uniforme"],
        "spots_colombia": ["Canchas barrio + ligas profesionales"],
        "referentes_colombia": ["James Rodriguez", "Luis Diaz", "Linda Caicedo"],
        "federacion": "Federacion Colombiana de Futbol",
    },
    {
        "slug": "baloncesto", "nombre_es": "Baloncesto",
        "nombre_en": "Basketball", "categoria": "equipo",
        "escena_co": "Medellin, Bogota, Cartagena",
        "plataforma_externa": "instagram",
        "vocabulario": ["dribbling", "crossover", "step back", "fade away", "rebound", "block", "alley oop"],
        "metricas": ["partidos", "puntos", "rebotes", "asistencias"],
        "equipamiento": ["tenis_basket", "uniforme", "balon"],
        "spots_colombia": ["Coliseo El Pueblo Cali", "Bogota"],
        "referentes_colombia": ["Liga Profesional Baloncesto Colombia"],
        "federacion": "Federacion Colombiana de Baloncesto",
    },
    {
        "slug": "voley", "nombre_es": "Voleibol",
        "nombre_en": "Volleyball", "categoria": "equipo",
        "escena_co": "Cartagena, Cali, Medellin",
        "plataforma_externa": "instagram",
        "vocabulario": ["saque", "remate", "bloqueo", "recepcion", "set", "ace"],
        "metricas": ["partidos", "sets", "aces", "bloqueos"],
        "equipamiento": ["rodilleras", "tenis_voley", "uniforme"],
        "spots_colombia": ["Playa Cartagena", "Coliseos pais"],
        "referentes_colombia": ["Seleccion CO voley playa"],
        "federacion": "Federacion Colombiana de Voleibol",
    },
    {
        "slug": "voley_playa", "nombre_es": "Voleibol playa",
        "nombre_en": "Beach volleyball", "categoria": "equipo",
        "escena_co": "Cartagena, Santa Marta, San Andres",
        "plataforma_externa": "instagram",
        "vocabulario": ["saque", "remate", "bloqueo", "defensa", "set"],
        "metricas": ["partidos", "torneos"],
        "equipamiento": ["bikini_uniforme", "balon"],
        "spots_colombia": ["Playas Caribe"],
        "referentes_colombia": [],
        "federacion": "Fecvolleyball",
    },
    {
        "slug": "beisbol", "nombre_es": "Beisbol", "nombre_en": "Baseball",
        "categoria": "equipo", "escena_co": "Costa Caribe (Cartagena, Barranquilla)",
        "plataforma_externa": "instagram",
        "vocabulario": ["bate", "strike", "ball", "home run", "doble", "robo", "pitcheo", "swing"],
        "metricas": ["partidos", "AVG", "HR", "RBI"],
        "equipamiento": ["bate", "guante", "casco", "spikes"],
        "spots_colombia": ["Cartagena (Caimanes)", "Barranquilla", "Sincelejo"],
        "referentes_colombia": ["Caimanes Cartagena (50a edicion LCBP)", "Diego Contreras"],
        "federacion": "Federacion Colombiana de Beisbol",
    },
    {
        "slug": "softbol", "nombre_es": "Softbol",
        "nombre_en": "Softball", "categoria": "equipo",
        "escena_co": "Caribe + interior", "plataforma_externa": "",
        "vocabulario": ["pitcheo", "swing", "robo", "strike"],
        "metricas": ["partidos", "AVG"],
        "equipamiento": ["bate", "guante", "casco"],
        "spots_colombia": [], "referentes_colombia": [], "federacion": "",
    },
    {
        "slug": "rugby", "nombre_es": "Rugby (XVs/7s)",
        "nombre_en": "Rugby", "categoria": "equipo",
        "escena_co": "Bogota, Medellin (Gatos Medellin)",
        "plataforma_externa": "instagram",
        "vocabulario": ["scrum", "lineout", "ruck", "maul", "try", "convert"],
        "metricas": ["partidos", "trys", "campeonatos"],
        "equipamiento": ["bucal", "boots", "uniforme"],
        "spots_colombia": ["Parques Bogota", "Medellin"],
        "referentes_colombia": ["Gatos de Medellin", "Tucanes"],
        "federacion": "Federacion Colombiana de Rugby",
    },
    {
        "slug": "hockey", "nombre_es": "Hockey (campo/sala/linea)",
        "nombre_en": "Hockey", "categoria": "equipo",
        "escena_co": "Bogota, Bolivar (4to titulo consecutivo BMX Hockey 2025)",
        "plataforma_externa": "",
        "vocabulario": ["hit", "drag flick", "pase", "tiro", "corner"],
        "metricas": ["partidos", "goles", "asistencias"],
        "equipamiento": ["stick", "espinilleras", "uniforme"],
        "spots_colombia": ["Bolivar"],
        "referentes_colombia": [],
        "federacion": "Federacion Colombiana de Hockey",
    },
    {
        "slug": "ultimate", "nombre_es": "Ultimate Frisbee",
        "nombre_en": "Ultimate", "categoria": "equipo",
        "escena_co": "Bogota, Medellin, Cali", "plataforma_externa": "instagram",
        "vocabulario": ["forehand", "backhand", "huck", "stack", "cut", "layout"],
        "metricas": ["partidos", "goles", "torneos"],
        "equipamiento": ["disco", "cleats"],
        "spots_colombia": ["Parques universidades"],
        "referentes_colombia": ["Revolution (mujeres)", "Otros equipos pais"],
        "federacion": "Asociacion Colombiana de Ultimate",
    },
    {
        "slug": "padel", "nombre_es": "Padel", "nombre_en": "Padel",
        "categoria": "equipo", "escena_co": "Bogota, Medellin, Cali (500+ canchas 2025, FCP oficializada)",
        "plataforma_externa": "instagram",
        "vocabulario": ["bandeja", "vibora", "remate", "globo", "salida pared"],
        "metricas": ["partidos", "torneos", "ranking"],
        "equipamiento": ["pala", "pelotas", "tenis_padel"],
        "spots_colombia": ["Clubes Bogota", "Medellin", "Cali"],
        "referentes_colombia": ["Federacion Colombiana de Padel (2025)"],
        "federacion": "Federacion Colombiana de Padel",
    },
    {
        "slug": "tenis", "nombre_es": "Tenis", "nombre_en": "Tennis",
        "categoria": "equipo", "escena_co": "Bogota, Medellin, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["forehand", "backhand", "saque", "volea", "smash", "drop shot"],
        "metricas": ["partidos", "sets", "ranking"],
        "equipamiento": ["raqueta", "pelotas", "tenis_tenis"],
        "spots_colombia": ["Clubes"],
        "referentes_colombia": ["Daniel Galan", "Camila Osorio"],
        "federacion": "Federacion Colombiana de Tenis",
    },

    # ===== OUTDOOR ENDURANCE =====
    {
        "slug": "running", "nombre_es": "Running de calle",
        "nombre_en": "Road running", "categoria": "outdoor_endurance",
        "escena_co": "Bogota (Media Maraton de Bogota), Medellin, Cali",
        "plataforma_externa": "strava",
        "vocabulario": ["fartlek", "tempo", "long run", "intervalos", "split", "pacing"],
        "metricas": ["km_semana", "pace_min_km", "PRs_5k_10k_21k_42k"],
        "equipamiento": ["zapatillas_running", "ropa_tecnica", "reloj_gps"],
        "spots_colombia": ["Ciclovia Bogota", "Cerros"],
        "referentes_colombia": ["Carlos Sanmartín", "Angie Orjuela"],
        "federacion": "Federacion Colombiana de Atletismo",
    },
    {
        "slug": "trail", "nombre_es": "Trail running / Ultra",
        "nombre_en": "Trail running", "categoria": "outdoor_endurance",
        "escena_co": "Cundinamarca (Sumapaz), Antioquia (Belmira), Nevados, Cocuy. UTMB Quindio 2025 (5 distancias)",
        "plataforma_externa": "strava",
        "vocabulario": ["d+", "downhill", "uphill", "aid station", "drop bag", "pacing"],
        "metricas": ["km_semana", "d+", "ultra_completed", "FKT"],
        "equipamiento": ["zapatillas_trail", "chaleco_hidratacion", "bastones"],
        "spots_colombia": ["UTMB Quindio", "Trail El Cocuy", "Nevados", "Belmira"],
        "referentes_colombia": ["Ana Maria Espinosa"],
        "federacion": "Asociacion Colombiana Trail Running",
    },
    {
        "slug": "triatlon", "nombre_es": "Triatlon",
        "nombre_en": "Triathlon", "categoria": "outdoor_endurance",
        "escena_co": "Cartagena (IronMan 70.3), Bogota, Medellin",
        "plataforma_externa": "strava",
        "vocabulario": ["transicion", "drafting", "T1", "T2", "draft legal", "olimpico", "sprint", "70.3", "IM"],
        "metricas": ["semanas_entreno", "TSS", "PRs_distancia"],
        "equipamiento": ["bike_TT_o_route", "wetsuit", "casco_aero", "zapatillas_running"],
        "spots_colombia": ["Cartagena 70.3", "Salida embalse Neusa"],
        "referentes_colombia": ["Carlos Quinchara"],
        "federacion": "Federacion Colombiana de Triatlon",
    },
    {
        "slug": "duatlon", "nombre_es": "Duatlon",
        "nombre_en": "Duathlon", "categoria": "outdoor_endurance",
        "escena_co": "Pereira, Bogota", "plataforma_externa": "strava",
        "vocabulario": ["transicion", "split bike", "split run"],
        "metricas": ["PRs", "tiempos"],
        "equipamiento": ["bike", "zapatillas"],
        "spots_colombia": [], "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "ocr", "nombre_es": "OCR / Spartan / carrera obstaculos",
        "nombre_en": "OCR", "categoria": "outdoor_endurance",
        "escena_co": "Bogota (Spartan), Pereira", "plataforma_externa": "instagram",
        "vocabulario": ["obstaculo", "spear throw", "burpees", "monkey bars", "rope climb"],
        "metricas": ["carreras_completadas", "obstaculos_pasados"],
        "equipamiento": ["zapatillas_OCR", "guantes_grip"],
        "spots_colombia": ["Spartan Bogota"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "mtb", "nombre_es": "Mountain bike (XC/DH/enduro)",
        "nombre_en": "Mountain bike", "categoria": "outdoor_endurance",
        "escena_co": "Boyaca, Antioquia, Eje Cafetero",
        "plataforma_externa": "strava",
        "vocabulario": ["singletrack", "drop", "berm", "switchback", "PR Strava"],
        "metricas": ["km_semana", "d+", "PRs_segmentos"],
        "equipamiento": ["MTB", "casco_DH_o_XC", "guantes", "pads"],
        "spots_colombia": ["Belmira", "Salento", "Tabio"],
        "referentes_colombia": ["Hector Paez", "Marcela Gomez"],
        "federacion": "Federacion Colombiana de Ciclismo",
    },
    {
        "slug": "ciclismo", "nombre_es": "Ciclismo de ruta / pista",
        "nombre_en": "Road cycling", "categoria": "outdoor_endurance",
        "escena_co": "Boyaca (Carapaz, Bernal, Quintana), Antioquia, Eje cafetero",
        "plataforma_externa": "strava",
        "vocabulario": ["watts", "FTP", "drafting", "ataque", "sprint", "GC", "polka dot"],
        "metricas": ["km_semana", "TSS", "FTP_w", "PRs_segmentos"],
        "equipamiento": ["bici_ruta", "casco_aero", "pedalines_clip"],
        "spots_colombia": ["Alto de Letras", "La Linea", "Mesitas"],
        "referentes_colombia": ["Egan Bernal", "Nairo Quintana", "Rigoberto Uran"],
        "federacion": "Federacion Colombiana de Ciclismo",
    },
    {
        "slug": "atletismo", "nombre_es": "Atletismo (pista/campo)",
        "nombre_en": "Athletics", "categoria": "outdoor_endurance",
        "escena_co": "Cali (Atanasio Girardot), Medellin, Ibague",
        "plataforma_externa": "instagram",
        "vocabulario": ["salida", "split", "PB", "salto largo", "altura", "lanzamiento"],
        "metricas": ["PBs_distancia", "marcas"],
        "equipamiento": ["spikes", "uniforme"],
        "spots_colombia": ["Pista Ibague", "Cali"],
        "referentes_colombia": ["Caterine Ibargüen", "Mauricio Ortega", "Anthony Zambrano"],
        "federacion": "Federacion Colombiana de Atletismo",
    },

    # ===== INDOOR FUERZA =====
    {
        "slug": "gimnasio", "nombre_es": "Gimnasio (musculacion general)",
        "nombre_en": "Gym (strength)", "categoria": "indoor_fuerza",
        "escena_co": "Todo el pais", "plataforma_externa": "",
        "vocabulario": ["sets", "reps", "RPE", "RIR", "1RM", "drop set", "rest pause", "hipertrofia", "fuerza"],
        "metricas": ["1RM", "volumen_kg", "sets_musculo_semana"],
        "equipamiento": ["pesas", "maquinas", "cinturon", "rodilleras"],
        "spots_colombia": ["Cualquier gym"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "crossfit", "nombre_es": "CrossFit", "nombre_en": "CrossFit",
        "categoria": "indoor_fuerza",
        "escena_co": "Bogota, Medellin, Cali (CrossFit boxes 50+)",
        "plataforma_externa": "instagram",
        "vocabulario": ["WOD", "AMRAP", "EMOM", "Rx", "Murph", "Fran", "Cindy", "muscle up", "double under"],
        "metricas": ["WOD_PRs", "1RM_oly", "benchmark_times"],
        "equipamiento": ["zapatos_lifting", "muniqueras", "rodilleras", "ropa_movilidad"],
        "spots_colombia": ["CrossFit Bogota Centro", "CrossFit Poblado Medellin"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "calistenia", "nombre_es": "Calistenia",
        "nombre_en": "Calisthenics", "categoria": "indoor_fuerza",
        "escena_co": "Parques (Simon Bolivar, Pereira)", "plataforma_externa": "instagram",
        "vocabulario": ["muscle up", "front lever", "back lever", "human flag", "planche", "handstand", "pistol squat"],
        "metricas": ["skill_holds_sec", "reps_max", "skills_dominados"],
        "equipamiento": ["barras_parque", "anillas", "elasticos"],
        "spots_colombia": ["Parque Simon Bolivar", "Coliseos"],
        "referentes_colombia": [],
        "federacion": "",
    },
    {
        "slug": "powerlifting", "nombre_es": "Powerlifting",
        "nombre_en": "Powerlifting", "categoria": "indoor_fuerza",
        "escena_co": "Todo el pais (escena emergente)", "plataforma_externa": "instagram",
        "vocabulario": ["squat", "bench", "deadlift", "total", "wilks", "DOTS", "RPE 8/9/10", "openers"],
        "metricas": ["1RM_squat", "1RM_bench", "1RM_deadlift", "total_wilks"],
        "equipamiento": ["cinturon", "rodilleras", "muniqueras", "knee_sleeves"],
        "spots_colombia": ["Strength gyms Bogota, Medellin"],
        "referentes_colombia": [],
        "federacion": "Federacion Colombiana de Powerlifting",
    },
    {
        "slug": "halterofilia", "nombre_es": "Halterofilia / Olympic lifting",
        "nombre_en": "Olympic weightlifting", "categoria": "indoor_fuerza",
        "escena_co": "Calarca, Manizales, Pereira, Cali",
        "plataforma_externa": "instagram",
        "vocabulario": ["snatch", "clean", "jerk", "split jerk", "power clean", "OHP", "front squat"],
        "metricas": ["1RM_snatch", "1RM_clean_jerk", "total"],
        "equipamiento": ["zapatos_oly", "cinturon", "muniqueras"],
        "spots_colombia": ["Calarca (cuna del Olympic CO)", "Manizales"],
        "referentes_colombia": ["Mariana Pajon", "Mercedes Perez", "Yeison Lopez", "Habib de las Salas"],
        "federacion": "Federacion Colombiana de Levantamiento de Pesas",
    },
    {
        "slug": "funcional", "nombre_es": "Funcional / HIIT",
        "nombre_en": "Functional / HIIT", "categoria": "indoor_fuerza",
        "escena_co": "Todo el pais", "plataforma_externa": "instagram",
        "vocabulario": ["circuito", "tabata", "AMRAP", "burpee", "kettlebell swing", "battle ropes"],
        "metricas": ["circuitos_completados", "sesiones"],
        "equipamiento": ["kettlebells", "TRX", "battle ropes"],
        "spots_colombia": [], "referentes_colombia": [], "federacion": "",
    },
    {
        "slug": "pilates", "nombre_es": "Pilates",
        "nombre_en": "Pilates", "categoria": "indoor_fuerza",
        "escena_co": "Bogota, Medellin, Cali", "plataforma_externa": "instagram",
        "vocabulario": ["roll up", "teaser", "hundred", "footwork", "reformer", "cadillac"],
        "metricas": ["sesiones_semana", "ejercicios_dominados"],
        "equipamiento": ["mat", "reformer", "magic_circle"],
        "spots_colombia": ["Estudios Bogota"], "referentes_colombia": [], "federacion": "",
    },
    {
        "slug": "yoga", "nombre_es": "Yoga", "nombre_en": "Yoga",
        "categoria": "indoor_fuerza", "escena_co": "Todo el pais",
        "plataforma_externa": "instagram",
        "vocabulario": ["asana", "vinyasa", "ashtanga", "yin", "pranayama", "savasana", "namaste"],
        "metricas": ["sesiones_semana", "hold_min_max", "estilos"],
        "equipamiento": ["mat", "bloques", "correa"],
        "spots_colombia": [], "referentes_colombia": [], "federacion": "",
    },
    {
        "slug": "pole", "nombre_es": "Pole dance / pole sport",
        "nombre_en": "Pole dance", "categoria": "indoor_fuerza",
        "escena_co": "Bogota, Medellin, Cali", "plataforma_externa": "instagram",
        "vocabulario": ["invertido", "spin", "climb", "split", "deadlift en pole", "ayesha"],
        "metricas": ["trucos_aterrizados", "rutinas_completadas", "niveles"],
        "equipamiento": ["tubo", "shorts", "magnesio"],
        "spots_colombia": ["Estudios pole Bogota"], "referentes_colombia": [], "federacion": "",
    },
    {
        "slug": "aerial", "nombre_es": "Aerial silks / lyra",
        "nombre_en": "Aerial arts", "categoria": "indoor_fuerza",
        "escena_co": "Bogota, Medellin", "plataforma_externa": "instagram",
        "vocabulario": ["hip key", "wheel down", "split", "drop", "single foot lock"],
        "metricas": ["trucos_aterrizados", "rutinas"],
        "equipamiento": ["tela", "lyra", "trapecio"],
        "spots_colombia": ["Circo del Sol Bogota"], "referentes_colombia": [], "federacion": "",
    },

    # ===== ACUATICO =====
    {
        "slug": "natacion", "nombre_es": "Natacion", "nombre_en": "Swimming",
        "categoria": "acuatico", "escena_co": "Medellin, Cali, Bogota",
        "plataforma_externa": "strava",
        "vocabulario": ["crawl", "espalda", "pecho", "mariposa", "split", "interval", "SWOLF"],
        "metricas": ["m_semana", "T-pace_100m", "PRs_distancia"],
        "equipamiento": ["traje_bano", "gafas", "gorro", "aletas", "pull buoy"],
        "spots_colombia": ["Piscina Olimpica Cali", "Coldeportes Bogota"],
        "referentes_colombia": ["Omar Pinzon"],
        "federacion": "Federacion Colombiana de Natacion (Fecna)",
    },
    {
        "slug": "waterpolo", "nombre_es": "Waterpolo",
        "nombre_en": "Water polo", "categoria": "acuatico",
        "escena_co": "Bogota, Cali", "plataforma_externa": "",
        "vocabulario": ["egg beater", "shot", "block", "drive"],
        "metricas": ["partidos", "goles"],
        "equipamiento": ["gorro", "uniforme"],
        "spots_colombia": ["Piscinas"], "referentes_colombia": [],
        "federacion": "Fecna",
    },
    {
        "slug": "apnea", "nombre_es": "Buceo libre / Apnea",
        "nombre_en": "Freediving", "categoria": "acuatico",
        "escena_co": "San Andres, Santa Marta, Cartagena",
        "plataforma_externa": "instagram",
        "vocabulario": ["constant weight", "static apnea", "dynamic", "equalization", "frenzel", "mouthfill"],
        "metricas": ["profundidad_m", "tiempo_apnea_static"],
        "equipamiento": ["traje_neopreno", "mascara", "snorkel", "aletas_largas", "cuerda"],
        "spots_colombia": ["San Andres", "Santa Marta"],
        "referentes_colombia": [],
        "federacion": "AIDA / CMAS Colombia",
    },
    {
        "slug": "buceo", "nombre_es": "Buceo con tanque (scuba)",
        "nombre_en": "Scuba diving", "categoria": "acuatico",
        "escena_co": "San Andres, Santa Marta, Cartagena",
        "plataforma_externa": "instagram",
        "vocabulario": ["regulator", "BCD", "octopus", "nitrox", "deco stop", "DCS"],
        "metricas": ["inmersiones", "profundidad_max", "horas_log"],
        "equipamiento": ["tanque", "BCD", "regulador", "traje", "computador_buceo"],
        "spots_colombia": ["San Andres", "Providencia", "Taganga"],
        "referentes_colombia": [], "federacion": "Acolam",
    },

    # ===== ECUESTRE =====
    {
        "slug": "equitacion", "nombre_es": "Equitacion (salto/doma/CC)",
        "nombre_en": "Equestrian", "categoria": "ecuestre",
        "escena_co": "Bogota (Hipico Los Andes), Medellin",
        "plataforma_externa": "instagram",
        "vocabulario": ["medio paso", "trote", "galope", "salto", "hilera", "spread"],
        "metricas": ["competencias", "rankings", "alturas_saltadas"],
        "equipamiento": ["casco", "fusta", "botas", "silla"],
        "spots_colombia": ["Hipico Los Andes Bogota"],
        "referentes_colombia": ["Mark Bluman", "Daniel Bluman"],
        "federacion": "Federacion Ecuestre de Colombia",
    },
    {
        "slug": "polo", "nombre_es": "Polo", "nombre_en": "Polo",
        "categoria": "ecuestre", "escena_co": "Bogota",
        "plataforma_externa": "",
        "vocabulario": ["chukka", "tiro", "marca", "back"],
        "metricas": ["chukkas", "handicap"],
        "equipamiento": ["taco", "casco", "botas"],
        "spots_colombia": ["Polo Club Bogota"],
        "referentes_colombia": [],
        "federacion": "Polo Colombia",
    },
    {
        "slug": "caballo_paso", "nombre_es": "Caballo de paso fino colombiano",
        "nombre_en": "Paso Fino", "categoria": "ecuestre",
        "escena_co": "Antioquia, Caldas, Tolima",
        "plataforma_externa": "instagram",
        "vocabulario": ["paso fino", "trocha", "trote y galope"],
        "metricas": ["competencias", "rankings"],
        "equipamiento": ["silla criolla", "frenos"],
        "spots_colombia": ["Manizales", "Medellin"],
        "referentes_colombia": [],
        "federacion": "Fedequinas",
    },

    # ===== MOTOR =====
    {
        "slug": "karting", "nombre_es": "Karting", "nombre_en": "Karting",
        "categoria": "motor", "escena_co": "Bogota, Medellin",
        "plataforma_externa": "instagram",
        "vocabulario": ["apex", "brake point", "racing line", "pole position"],
        "metricas": ["best lap", "carreras"],
        "equipamiento": ["casco", "buzo", "guantes", "botas"],
        "spots_colombia": ["Autodromo Tocancipa"], "referentes_colombia": [],
        "federacion": "Federacion Colombiana de Automovilismo",
    },
    {
        "slug": "motocross", "nombre_es": "Motocross",
        "nombre_en": "Motocross", "categoria": "motor",
        "escena_co": "Tocancipa, Girardota, Pereira",
        "plataforma_externa": "instagram",
        "vocabulario": ["whip", "scrub", "berm", "jump"],
        "metricas": ["carreras", "lap times"],
        "equipamiento": ["moto", "casco_MX", "botas", "rodilleras", "neck brace"],
        "spots_colombia": ["Tocancipa", "Girardota"],
        "referentes_colombia": [],
        "federacion": "Fedemoto",
    },
    {
        "slug": "enduro_moto", "nombre_es": "Enduro moto",
        "nombre_en": "Enduro motorcycle", "categoria": "motor",
        "escena_co": "Antioquia, Cundinamarca",
        "plataforma_externa": "instagram",
        "vocabulario": ["timing", "checkpoint", "section", "lakes"],
        "metricas": ["carreras", "tiempo_total"],
        "equipamiento": ["moto_enduro", "casco", "rodilleras"],
        "spots_colombia": [], "referentes_colombia": [],
        "federacion": "Fedemoto",
    },

    # ===== TRADICIONAL COLOMBIANO =====
    {
        "slug": "tejo", "nombre_es": "Tejo (deporte nacional)",
        "nombre_en": "Tejo", "categoria": "tradicional_co",
        "escena_co": "Cundinamarca, Boyaca, Bogota, todo el pais",
        "plataforma_externa": "",
        "vocabulario": ["mecha", "moneda", "embocinada", "mano", "bocin"],
        "metricas": ["partidas_jugadas", "puntos_total"],
        "equipamiento": ["tejos", "cancha", "cerveza"],
        "spots_colombia": ["Canchas tejo todo el pais"],
        "referentes_colombia": [], "federacion": "Federacion Colombiana de Tejo",
    },
    {
        "slug": "coleo", "nombre_es": "Coleo (llanos orientales)",
        "nombre_en": "Coleo", "categoria": "tradicional_co",
        "escena_co": "Llanos Orientales (Meta, Casanare)",
        "plataforma_externa": "",
        "vocabulario": ["coleadura", "caballo de coleo", "manga"],
        "metricas": ["coleaduras", "competencias"],
        "equipamiento": ["caballo", "sombrero"],
        "spots_colombia": ["Llanos Orientales"],
        "referentes_colombia": [],
        "federacion": "Fedecoleo",
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columnas_usuario = {c["name"] for c in inspector.get_columns("usuarios")}

    nuevas_columnas: list[tuple[str, sa.Column]] = []
    if "categoria_deporte" not in columnas_usuario:
        nuevas_columnas.append((
            "categoria_deporte",
            sa.Column(
                "categoria_deporte",
                sa.String(32),
                server_default="indoor_fuerza",
                nullable=False,
            ),
        ))
    if "modalidad_deporte" not in columnas_usuario:
        nuevas_columnas.append((
            "modalidad_deporte",
            sa.Column("modalidad_deporte", sa.String(64), nullable=True),
        ))
    if "anos_practica" not in columnas_usuario:
        nuevas_columnas.append((
            "anos_practica",
            sa.Column("anos_practica", sa.Integer, nullable=True),
        ))
    if "es_competitivo" not in columnas_usuario:
        nuevas_columnas.append((
            "es_competitivo",
            sa.Column(
                "es_competitivo",
                sa.Boolean,
                server_default=sa.text("false"),
                nullable=False,
            ),
        ))
    for _, col in nuevas_columnas:
        op.add_column("usuarios", col)
    if any(name == "categoria_deporte" for name, _ in nuevas_columnas):
        op.create_index(
            "ix_usuarios_categoria_deporte", "usuarios", ["categoria_deporte"]
        )

    tabla_existe = inspector.has_table("deportes_catalogo")
    if not tabla_existe:
        op.create_table(
            "deportes_catalogo",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("slug", sa.String(48), unique=True, nullable=False, index=True),
            sa.Column("nombre_es", sa.String(80), nullable=False),
            sa.Column("nombre_en", sa.String(80), server_default=""),
            sa.Column("categoria", sa.String(32), nullable=False, index=True),
            sa.Column("escena_co", sa.String(200), server_default=""),
            sa.Column("plataforma_externa", sa.String(32), server_default=""),
            sa.Column("vocabulario", sa.JSON, server_default="[]"),
            sa.Column("metricas", sa.JSON, server_default="[]"),
            sa.Column("equipamiento", sa.JSON, server_default="[]"),
            sa.Column("spots_colombia", sa.JSON, server_default="[]"),
            sa.Column("referentes_colombia", sa.JSON, server_default="[]"),
            sa.Column("federacion", sa.String(120), server_default=""),
            sa.Column(
                "activo", sa.Boolean, server_default=sa.text("true"), nullable=False
            ),
            sa.Column("creado_en", sa.DateTime, server_default=sa.func.now()),
        )

    import json as _json
    is_pg = bind.dialect.name == "postgresql"
    insert_sql = (
        "INSERT INTO deportes_catalogo "
        "(slug, nombre_es, nombre_en, categoria, escena_co, plataforma_externa, "
        "vocabulario, metricas, equipamiento, spots_colombia, referentes_colombia, "
        "federacion) VALUES "
        + ("(%(slug)s, %(nes)s, %(nen)s, %(cat)s, %(esc)s, %(plat)s, "
           "%(voc)s::jsonb, %(met)s::jsonb, %(eq)s::jsonb, %(sp)s::jsonb, "
           "%(ref)s::jsonb, %(fed)s) "
           "ON CONFLICT (slug) DO NOTHING"
           if is_pg
           else "(:slug, :nes, :nen, :cat, :esc, :plat, :voc, :met, :eq, :sp, :ref, :fed)")
    )
    if not is_pg:
        insert_sql = "INSERT OR IGNORE INTO " + insert_sql.split("INSERT INTO ", 1)[1]
    for d in DEPORTES_SEED:
        bind.exec_driver_sql(
            insert_sql,
            {
                "slug": d["slug"],
                "nes": d["nombre_es"],
                "nen": d.get("nombre_en", ""),
                "cat": d["categoria"],
                "esc": d.get("escena_co", ""),
                "plat": d.get("plataforma_externa", ""),
                "voc": _json.dumps(d.get("vocabulario", [])),
                "met": _json.dumps(d.get("metricas", [])),
                "eq": _json.dumps(d.get("equipamiento", [])),
                "sp": _json.dumps(d.get("spots_colombia", [])),
                "ref": _json.dumps(d.get("referentes_colombia", [])),
                "fed": d.get("federacion", ""),
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("deportes_catalogo"):
        op.drop_table("deportes_catalogo")
    columnas_usuario = {c["name"] for c in inspector.get_columns("usuarios")}
    if "categoria_deporte" in columnas_usuario:
        try:
            op.drop_index("ix_usuarios_categoria_deporte", table_name="usuarios")
        except Exception:
            pass
        op.drop_column("usuarios", "categoria_deporte")
    if "modalidad_deporte" in columnas_usuario:
        op.drop_column("usuarios", "modalidad_deporte")
    if "anos_practica" in columnas_usuario:
        op.drop_column("usuarios", "anos_practica")
    if "es_competitivo" in columnas_usuario:
        op.drop_column("usuarios", "es_competitivo")
