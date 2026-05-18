"""Tests del clasificador de crisis."""
from src.services.crisis import detectar, detectar_diagnostico_output


def test_nivel_1_ideacion_suicida():
    c = detectar("quiero morir, no aguanto mas", "CO")
    assert c is not None
    assert c.nivel == 1
    assert any("morir" in k for k in c.keywords)


def test_nivel_2_tca():
    c = detectar("vomite todo lo que comi hoy", "MX")
    assert c is not None
    assert c.nivel == 2


def test_nivel_2_depresion():
    c = detectar("estoy deprimido todo me da igual", "AR")
    assert c is not None
    assert c.nivel == 2


def test_sin_crisis_no_falla():
    c = detectar("hoy entrene pecho y me sente bien", "ES")
    assert c is None


def test_lineas_pais_correctas():
    c = detectar("quiero morir", "ES")
    assert "024" in c.lineas_crisis
    c = detectar("quiero morir", "MX")
    assert "SAPTEL" in c.lineas_crisis or "800 911 2000" in c.lineas_crisis


def test_diagnostico_output_bloqueado():
    matches = detectar_diagnostico_output("Diego, tienes anorexia clara.")
    assert len(matches) > 0


def test_output_clean_no_falsos_positivos():
    matches = detectar_diagnostico_output("Sigue asi Diego, vamos por mas reps manana.")
    assert len(matches) == 0


def test_pais_desconocido_fallback():
    c = detectar("quiero morir", "ZZ")
    assert "linea" in c.lineas_crisis.lower() or "emergencias" in c.lineas_crisis.lower()


# ============================================================================
# PR1 - Nuevos red flags para deportes urbanos + combate
# ============================================================================


def test_trauma_craneal_basico_nivel_2():
    c = detectar("Me cai del BMX y no me acuerdo del golpe", "CO")
    assert c is not None
    assert c.nivel == 2
    assert c.subcategoria == "trauma_craneal"
    msg = c.mensaje_contenedor.lower()
    assert "conmocion" in msg or "concusion" in msg or "concussion" in msg


def test_trauma_craneal_post_sparring():
    c = detectar("Vomite tras el sparring de hoy", "MX")
    assert c is not None
    assert c.nivel == 2
    assert "GRTP" in c.mensaje_contenedor or "Amsterdam" in c.mensaje_contenedor


def test_trauma_craneal_no_falso_positivo():
    # "borroso" sin contexto no debe activar (regex pide combinacion)
    c = detectar("Tengo la vista borrosa al levantarme rapido", "CO")
    assert c is None or c.subcategoria != "trauma_craneal"


def test_segunda_concusion_nivel_1_urgente():
    c = detectar("Tuve otra conmocion en menos de 3 semanas", "CO")
    assert c is not None
    assert c.nivel == 1
    assert c.subcategoria == "concusion_repetida"
    assert "21 dias" in c.mensaje_contenedor or "second-impact" in c.mensaje_contenedor


def test_segunda_caida_este_mes():
    c = detectar("Es la segunda caida en este mes con sintomas", "CO")
    assert c is not None
    assert c.nivel == 1


def test_apnea_solo_nivel_1():
    c = detectar("Voy a practicar apnea sola en la piscina", "CO")
    assert c is not None
    assert c.nivel == 1
    assert c.subcategoria == "apnea_riesgo_swb"
    assert "buddy" in c.mensaje_contenedor.lower()


def test_hiperventilo_antes_apnea():
    c = detectar("hiperventilo antes de sumergir para aguantar mas", "ES")
    assert c is not None
    assert c.nivel == 1
    assert "shallow water blackout" in c.mensaje_contenedor.lower() or "SWB" in c.mensaje_contenedor


def test_apnea_grupo_no_falso_positivo():
    c = detectar("Tomamos un curso de apnea con instructor", "CO")
    assert c is None or c.subcategoria != "apnea_riesgo_swb"


def test_cut_extremo_numerico_con_peso():
    # 8 kg en 5 dias para alguien de 70 kg = 11.4% en 5d => red flag
    c = detectar("voy a cortar 8 kg en 5 dias", "CO", peso_actual_kg=70)
    assert c is not None
    assert c.nivel == 2
    assert c.subcategoria == "cut_extremo_combate"
    assert "Reale" in c.mensaje_contenedor or "0.5-0.7" in c.mensaje_contenedor


def test_cut_moderado_no_activa_con_peso_grande():
    # 3 kg en 7 dias para alguien de 100 kg = 3% en 7d => NO red flag
    c = detectar("voy a cortar 3 kilos en 7 dias", "CO", peso_actual_kg=100)
    assert c is None


def test_cut_extremo_texto_sauna_toda_la_noche():
    c = detectar("voy a meterme a sauna toda la noche para pesar", "MX")
    assert c is not None
    assert c.nivel == 2
    assert c.subcategoria == "cut_extremo_combate"


def test_cut_extremo_diuretico():
    c = detectar("tomo diuretico para pesaje del sabado", "CO")
    assert c is not None
    assert c.nivel == 2


def test_ots_horas_excesivas():
    c = detectar("entreno 28 horas a la semana sin descanso", "CO")
    assert c is not None
    assert c.nivel == 3
    assert c.subcategoria == "sobreentrenamiento"
    assert "deload" in c.mensaje_contenedor.lower() or "OTS" in c.mensaje_contenedor


def test_ots_amenorrea_sostenida():
    c = detectar("se me fue la regla hace 4 meses", "CO")
    assert c is not None
    assert c.nivel == 3
    assert c.subcategoria == "sobreentrenamiento"


def test_ots_sin_deload():
    c = detectar("llevo 6 semanas sin deload y mi FTP bajo", "ES")
    assert c is not None
    assert c.nivel == 3


def test_trauma_ortopedico_clavicula():
    c = detectar("creo que tengo la clavicula rota tras la caida del BMX", "CO")
    assert c is not None
    assert c.nivel == 3
    assert c.subcategoria == "trauma_ortopedico"
    assert "escafoides" in c.mensaje_contenedor or "clavicula" in c.mensaje_contenedor


def test_trauma_ortopedico_hombro_dislocado():
    c = detectar("se me salio el hombro al caer del rail", "MX")
    assert c is not None
    assert c.nivel == 3


def test_trauma_ortopedico_muneca_morada_skate():
    c = detectar("la muneca esta morada y no puedo apoyar el peso", "CO")
    assert c is not None
    assert c.nivel == 3


def test_trauma_ortopedico_rodilla_se_suelta():
    c = detectar("la rodilla se suelta cada que freno fuerte", "ES")
    assert c is not None
    assert c.nivel == 3


def test_prioridad_concusion_sobre_apnea():
    """Si hay ambos, gana el primero detectado (apnea solo es nivel 1)."""
    c = detectar("voy a practicar apnea solo y tuve otra conmocion", "CO")
    assert c is not None
    assert c.nivel == 1


def test_subcategoria_atributo_existe_en_todos():
    """Aseguro que todos los CrisisDetected tienen subcategoria."""
    casos = [
        ("quiero morir", "CO"),
        ("estoy deprimido", "CO"),
        ("vomite tras el atracon", "CO"),
        ("entreno 30 horas semana", "CO"),
        ("clavicula rota", "CO"),
    ]
    for texto, pais in casos:
        c = detectar(texto, pais)
        assert c is not None
        assert hasattr(c, "subcategoria")
        assert c.subcategoria != ""


def test_diagnostico_output_bloquea_concusion():
    matches = detectar_diagnostico_output("Diego, tienes concusion cerebral grado 2.")
    assert len(matches) > 0

