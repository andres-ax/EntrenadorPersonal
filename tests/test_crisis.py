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
