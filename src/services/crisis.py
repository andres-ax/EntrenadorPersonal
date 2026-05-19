"""Clasificador de crisis basado en keywords. INDEPENDIENTE del LLM principal.

Basado en research/tough-love-coaching-framework.md seccion 6 y
research/deportes-colombia-expansion.md (red flags deportes urbanos + combate).

Niveles:
- 1 = URGENTE: ideacion suicida, autolesion, 2da concusion <30d, apnea solo.
      Respuesta inmediata + pausa total 7 dias + log + notificar admin.
- 2 = ALTA PREOCUPACION: TCA, depresion, trauma craneal sospechado, cut
      extremo en combate. Tono empatico + derivar a profesional.
- 3 = VIGILANCIA: sobreentrenamiento, amenorrea, trauma ortopedico agudo,
      dolor agudo persistente. Sugerir consulta sin bloquear conversacion.

Citas principales:
- McCrory P et al. Consensus statement on concussion in sport, Amsterdam 2022.
  Br J Sports Med, 2023. GRTP 6 etapas.
- Cantu RC. Second-impact syndrome. Clin Sports Med, 1998. (mortal en jovenes)
- Reale R, Slater G, Burke LM. Acute-weight-loss strategies for combat sports.
  Int J Sports Physiol Perform, 2017.
- Mountjoy M et al. IOC consensus on Relative Energy Deficiency in Sport
  (RED-S). Br J Sports Med, 2018.
- Meeusen R et al. ECSS/ACSM consensus overtraining syndrome. MSSE, 2013.
- Schweizer A. Sport climbing from a medical point of view. Swiss Med Wkly, 2012.
- DAN (Divers Alert Network) 2023 - shallow water blackout causa #1 muertes
  freediving.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


_NIVEL_1 = re.compile(
    r"\b(quiero\s+morir|me\s+quiero\s+matar|no\s+aguanto\s+m[aá]s|no\s+puedo\s+m[aá]s|"
    r"me\s+voy\s+a\s+matar|suicid|autolesion|me\s+corto|me\s+lastimo|"
    r"no\s+tiene\s+sentido\s+seguir|no\s+vale\s+la\s+pena\s+vivir|"
    r"acabar\s+con\s+todo|terminar\s+con\s+mi\s+vida)\b",
    re.IGNORECASE,
)

_NIVEL_1_CONCUSION_RECIENTE = re.compile(
    r"\b(otra\s+(conmocion|concusion|conmoci[oó]n|concussion)|"
    r"ya\s+me\s+habia\s+pasado\s+(esto|igual)\s+(este\s+mes|hace\s+(dos|2|tres|3|cuatro|4)\s+semanas)|"
    r"segunda\s+(caida|golpe|conmocion|concussion).{0,20}(mes|semana))\b",
    re.IGNORECASE,
)

_NIVEL_1_APNEA_SOLO = re.compile(
    r"\b(apnea\s+sol[oa]|practicar\s+apnea\s+sin\s+buddy|"
    r"entreno\s+apnea\s+(en\s+(la\s+piscina|el\s+mar)\s+)?sol[oa]|"
    r"hiperventilo\s+antes\s+de\s+(meter|sumergir|apnea|bucear)|"
    r"perd[ií]\s+(el|la)\s+conciencia\s+(buceando|en\s+el\s+agua|en\s+apnea))\b",
    re.IGNORECASE,
)

_NIVEL_2_TCA = re.compile(
    r"\b(vomit[eé]|provoqu[eé]\s+vomit|laxantes|diuretico|atracon|atraqu[eé]|"
    r"no\s+he\s+comido\s+(en|hace)\s+\d|llevo\s+\d+\s+dias\s+sin\s+comer|"
    r"ayuno\s+de\s+\d+\s+horas|comi\s+a\s+escondidas|comer\s+en\s+secreto|"
    r"me\s+da\s+asco\s+comer|odio\s+mi\s+cuerpo|me\s+veo\s+gord|"
    r"contar\s+cada\s+caloria\s+me\s+obsesi|tengo\s+anorexia|tengo\s+bulimia)\b",
    re.IGNORECASE,
)

_NIVEL_2_DEPRE = re.compile(
    r"\b(estoy\s+deprimid[oa]?|me\s+siento\s+deprimid[oa]?|no\s+tengo\s+ganas\s+de\s+nada|"
    r"llevo\s+semanas\s+sin\s+salir|todo\s+me\s+da\s+igual|me\s+siento\s+vacio|"
    r"no\s+veo\s+salida|crisis\s+de\s+ansiedad|ataque\s+de\s+panico|panic\s+attack)\b",
    re.IGNORECASE,
)

_NIVEL_2_TRAUMA_CRANEAL = re.compile(
    r"\b(no\s+me\s+acuerdo\s+(del|de\s+la)\s+(golpe|cai|caida)|"
    r"todo\s+(se\s+ve|esta)\s+borroso|vi\s+todo\s+brillante|vi\s+estrellas|"
    r"vomit[eé]\s+(despues|tras|luego).{0,15}(sparring|caida|golpe|entreno|pelea|combate|sesion)|"
    r"perd[ií]\s+(el|la)\s+(conciencia|conocimiento)|me\s+desmay[eé]|"
    r"qued[eé]\s+(noqueado|grogui|aturdido)|"
    r"dolor\s+(de\s+)?cabeza\s+(fuerte|raro).{0,15}(sparring|caida|golpe|entreno|pelea)|"
    r"me\s+dieron\s+(duro|fuerte)\s+en\s+la\s+cabeza|qued[eé]\s+timbrado)\b",
    re.IGNORECASE,
)

# Captura "voy a cortar X kilos en Y dias", "bajar X kg en Y dias", "corto X kilos para la pelea".
# El parser numerico (_extraer_cut_numerico) procesa el match para confirmar severidad.
_NIVEL_2_CUT_EXTREMO_TEXT = re.compile(
    r"\b(sauna\s+(toda\s+la\s+noche|todo\s+el\s+dia|\d{2,}\s*(min|h|horas?))|"
    r"dejar\s+de\s+tomar\s+agua\s+(\d+\s+d[ií]as?|completamente|hasta\s+el\s+pesaje)|"
    r"tomo\s+(diuretico|laxante)\s+para\s+(pesar|pesaje|bajar))\b",
    re.IGNORECASE,
)

_CUT_NUMERICO_RE = re.compile(
    r"(?:voy\s+a\s+)?(?:cortar|bajar|corto|cut)\s+(\d{1,2}(?:[.,]\d)?)\s*"
    r"(?:kilos?|kg|libras?|lb)\s+(?:en\s+|para\s+(?:la\s+|el\s+)?(?:pelea|combate|pesaje)\s+en\s+)"
    r"(\d{1,2})\s*(d[ií]as?|hrs?|horas?|sem(?:ana)?s?)",
    re.IGNORECASE,
)

_NIVEL_3 = re.compile(
    r"\b(amenorrea|sin\s+regla\s+(hace|desde)|fractura\s+por\s+estres|"
    r"me\s+lastim[eé]\s+entrenando|dolor\s+(fuerte|agudo)\s+(en|de)|"
    r"entren[oó]\s+(\d{3}|m[aá]s\s+de\s+\d{2})\s+horas|"
    r"no\s+puedo\s+dejar\s+de\s+entrenar)\b",
    re.IGNORECASE,
)

_NIVEL_3_OTS = re.compile(
    r"\b(entreno\s+(\d{2,})\s+(horas?|h)\s+(a\s+la\s+|por\s+)?semana|"
    r"llevo\s+(\d+)\s+(semanas?|meses?)\s+sin\s+(d[ií]a\s+(off|libre)|descansar|deload|parar)|"
    r"siento\s+(las\s+piernas|el\s+cuerpo)\s+pesad[oa]s?\s+(siempre|todos\s+los\s+dias)|"
    r"mi\s+(ritmo|FTP|VDOT|pace)\s+(bajo|cayo|empeoro)\s+y\s+(entreno|sigo)\s+(mas|igual)|"
    r"resting\s+(HR|frecuencia)\s+subio\s+\d+|HRV\s+(bajo|cayo)\s+(hace|por|desde)\s+\d+\s+(d[ií]as|semanas)|"
    r"se\s+me\s+(fue|corto)\s+(la\s+regla|el\s+ciclo)\s+(hace|desde)\s+(\d+|varios)\s+(meses|semanas))\b",
    re.IGNORECASE,
)

_NIVEL_3_TRAUMA_ORTOPEDICO = re.compile(
    r"\b(no\s+puedo\s+(mover|apoyar)\s+(la|el)\s+(muneca|tobillo|hombro|rodilla|brazo|pierna)|"
    r"(se\s+me\s+)?sali[oó]\s+(el\s+hombro|la\s+rodilla|la\s+rotula)|"
    r"escuche\s+un\s+(crack|chasquido|tronido)\s+(en|al)\s+(caer|aterrizar|saltar)|"
    r"clavicula\s+(rota|fracturada|deformada|chueca|partida)|"
    r"deformidad\s+(en|de)\s+(la|el)\s+(muneca|tobillo|brazo|pierna)|"
    r"no\s+puedo\s+apoyar\s+(el\s+pie|el\s+peso|la\s+pierna)|"
    r"muneca\s+(morada|hinchada|deformada)|"
    r"el\s+pulgar\s+no\s+me\s+(responde|funciona|mueve)|"
    r"la\s+rodilla\s+(se\s+(suelta|abre|dobla)|me\s+(falla|traiciona)|esta\s+suelta))\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CrisisDetected:
    nivel: int
    keywords: list[str]
    mensaje_contenedor: str
    lineas_crisis: str
    subcategoria: str = "general"


LINEAS_POR_PAIS: dict[str, str] = {
    "CO": (
        "<b>Lineas en Colombia:</b>\n"
        "- 192 MinSalud (nacional)\n"
        "- 106 Bogota / WhatsApp 300 754 8933\n"
        "- 123 emergencias"
    ),
    "MX": ("<b>Lineas en Mexico:</b>\n" "- 800 911 2000 SAPTEL\n" "- 911 emergencias"),
    "AR": (
        "<b>Lineas en Argentina:</b>\n"
        "- 135 (CABA) / 0800-345-1435 (nacional)\n"
        "- 911 emergencias"
    ),
    "ES": (
        "<b>Lineas en Espana:</b>\n"
        "- 024 (oficial MinSalud, gratuito 24/7)\n"
        "- 717 003 717 (Telefono Esperanza)\n"
        "- 112 emergencias"
    ),
    "PE": ("<b>Lineas en Peru:</b>\n" "- 113 opcion 5 MinSal\n" "- ANAR 0800-2-2210"),
    "CL": (
        "<b>Lineas en Chile:</b>\n"
        "- *4141 Salud Responde\n"
        "- 600 360 7777 Linea Libre"
    ),
    "US": (
        "<b>Lineas en US (espanol disponible):</b>\n" "- 988 Suicide & Crisis Lifeline"
    ),
}

_LINEAS_FALLBACK = (
    "Por favor marca el numero nacional de emergencias de tu pais o busca "
    "'linea de crisis [tu pais]' en internet."
)


def _lineas_pais(pais: str | None) -> str:
    if not pais:
        return _LINEAS_FALLBACK
    return LINEAS_POR_PAIS.get(pais.upper(), _LINEAS_FALLBACK)


def _mensaje_nivel_1(pais: str | None) -> str:
    return (
        "Lo que me cuentas es muy importante. <b>No estas solo/a</b> y aqui hay "
        "ayuda profesional disponible las 24 horas:\n\n"
        f"{_lineas_pais(pais)}\n\n"
        "Voy a pausar los recordatorios <b>7 dias</b>. Mientras tanto, "
        "por favor contacta a alguien de tu red cercana o llama a una de "
        "esas lineas. Volvemos cuando estes mejor."
    )


def _mensaje_concusion_reciente(pais: str | None) -> str:
    return (
        "<b>Atencion: esto es importante.</b>\n\n"
        "Una segunda conmocion antes de recuperarte de la primera tiene riesgo "
        "de <b>second-impact syndrome</b>, una emergencia poco frecuente pero "
        "grave (Cantu, Clin Sports Med 1998). \n\n"
        "Pausa total hoy. Urgencias o neurologia esta misma semana. Marca al "
        "123 si tienes mareo, confusion o vomito ahora.\n\n"
        f"{_lineas_pais(pais)}\n\n"
        "Compromiso pausado <b>21 dias minimo</b> o hasta alta medica."
    )


def _mensaje_apnea_solo(pais: str | None) -> str:
    return (
        "<b>Para. Esto puede matarte.</b>\n\n"
        "Apnea en solitario es la causa principal de muertes en freediving "
        "(DAN 2023). El <i>shallow water blackout (SWB)</i> ocurre sin aviso "
        "y la persona no recupera consciencia bajo agua = ahogamiento.\n\n"
        "Reglas no negociables (AIDA/PADI/CMAS):\n"
        "- <b>NUNCA</b> apnea sin un buddy entrenado en superficie.\n"
        "- <b>NUNCA</b> hiperventilar antes de apnea (suprime urge to breathe "
        "sin aumentar O2 disponible).\n"
        "- Cursos formales con instructor certificado antes de profundizar.\n"
        "- Si perdiste consciencia: medico hoy + reevaluacion antes de volver.\n\n"
        "Pausa apnea hasta que tengas buddy y curso formal. Lineas de salud:\n"
        f"{_lineas_pais(pais)}"
    )


def _mensaje_nivel_2(pais: str | None) -> str:
    return (
        "Gracias por contarmelo. Esto que vives merece <b>acompanamiento "
        "profesional</b> (psicologia, nutricion clinica o medico segun el caso). "
        "Yo soy un coach de habitos, no puedo tratar esto, pero quiero ayudarte "
        "a dar el siguiente paso:\n\n"
        f"{_lineas_pais(pais)}\n\n"
        "Sigo aqui para acompanarte en lo cotidiano con respeto. Si quieres, "
        "pausa mis recordatorios con /pausa 7."
    )


def _mensaje_trauma_craneal(pais: str | None) -> str:
    return (
        "<b>Pausa total ahora mismo</b> para todo deporte de contacto/skill.\n\n"
        "Lo que describes puede ser <b>conmocion cerebral</b> (concussion). "
        "Reglas no negociables:\n"
        "- Cero patines/tabla/bici/sparring por <b>minimo 7-10 dias</b>.\n"
        "- Consulta hoy con medico (idealmente deportivo o neurologia).\n"
        "- NO conduzcas si tienes mareos.\n"
        "- Si vomitas mas de una vez, no recuerdas eventos recientes o "
        "empeoras: <b>urgencias YA</b> (123 en CO).\n"
        "- Si has tenido OTRA conmocion en el ultimo mes: emergencia, riesgo "
        "de second-impact syndrome.\n\n"
        "Despues del alta, retorno por protocolo escalonado de 6 etapas "
        "(McCrory 2023, Amsterdam consensus). Compromiso pausado hasta entonces.\n\n"
        f"{_lineas_pais(pais)}"
    )


def _mensaje_cut_extremo(
    pais: str | None, kg_cut: float | None = None, dias: int | None = None
) -> str:
    cifras = ""
    if kg_cut is not None and dias is not None:
        cifras = f"(<i>{kg_cut} kg en {dias} dia(s)</i>) "
    return (
        f"Lo que planeas {cifras}es <b>cut agresivo</b> y la literatura es clara "
        "sobre los riesgos (Reale et al 2017, IOC consensus 2019): rabdomiolisis, "
        "deshidratacion &gt;3% degrada cognicion y poder, arritmia.\n\n"
        "Recomendacion CSCS:\n"
        "- <b>Cronico</b> (peso real): 0.5-0.7% peso corporal/sem.\n"
        "- <b>Agudo</b> (fluidos+glucogeno+fibra): max 3-5% en 24-48h y solo si "
        "rehidratacion garantizada &gt;12h antes de pelea.\n"
        "- <b>NUNCA</b>: diureticos, sauna prolongada, ayuno + sauna combinado.\n\n"
        "Antes de seguir, valida con nutricionista deportivo. La pelea se gana "
        "con cabeza, no perdiendo el corner. Sigo aqui para planificar un cut "
        "responsable.\n\n"
        f"{_lineas_pais(pais)}"
    )


def _mensaje_nivel_3(pais: str | None) -> str:
    return (
        "Lo que mencionas merece evaluacion <b>profesional</b> antes de seguir "
        "presionando con entrenamiento. Por favor consulta con tu medico/fisio/"
        "ginecologa/o nutricionista. Mientras tanto bajamos la intensidad."
    )


def _mensaje_ots(pais: str | None) -> str:
    return (
        "Lo que describes encaja con sintomas de <b>sobreentrenamiento (OTS)</b> "
        "o RED-S (Meeusen 2013, Mountjoy IOC 2018). Indicadores: performance "
        "plateau/drop sostenido, sueno alterado, HRV bajo, perdida de motivacion, "
        "lesiones recurrentes, alteracion menstrual.\n\n"
        "<b>NO se resuelve entrenando con mas ganas.</b> Se resuelve con:\n"
        "- Evaluacion medica/deportiva (panel hormonal, ferritina, vitD).\n"
        "- Deload obligatorio: <b>2-4 semanas al 40-60% volumen</b>, intensidad baja.\n"
        "- 9-10h sueno objetivo.\n"
        "- Si amenorrea &gt;3 meses: ginecologa + nutricionista deportiva.\n\n"
        "Compromiso ajustado a deload. Te acompano en ese reset.\n\n"
        f"{_lineas_pais(pais)}"
    )


def _mensaje_trauma_ortopedico(pais: str | None) -> str:
    return (
        "Lo que describes es senal clasica de lesion que necesita evaluacion "
        "<b>ortopedica hoy</b>:\n"
        "- Hinchazon + deformidad + dolor = posible fractura (clavicula, "
        "escafoides, Colles).\n"
        "- Chasquido + inestabilidad articular = posible ligamento (ACL/MCL, AC joint).\n"
        "- Hombro fuera de lugar = luxacion, <b>NO se reduce solo</b>, urgencias.\n\n"
        "NO vuelvas a montar/rodar/entrenar hasta diagnostico. La fractura de "
        "escafoides (muneca) tiene mal pronostico si se trata tarde (Schweizer 2012).\n\n"
        "Hielo + inmovilizacion improvisada + urgencias. Compromiso pausado.\n\n"
        f"{_lineas_pais(pais)}"
    )


def _extraer_cut_numerico(
    texto: str, peso_actual_kg: float | None = None
) -> tuple[float, int] | None:
    """Extrae (kg_cut, dias) si el texto menciona 'cortar X kg en Y dias'.

    Activa red flag solo si X/peso > 5% AND dias <= 7.
    Si peso_actual_kg es None, activa por defecto si kg >= 3 AND dias <= 5
    (umbral conservador sin saber peso).
    """
    m = _CUT_NUMERICO_RE.search(texto)
    if not m:
        return None
    try:
        kg = float(m.group(1).replace(",", "."))
        dias_num = int(m.group(2))
        unidad = m.group(3).lower()
        if unidad.startswith(("h", "hr")):
            dias_efectivos = max(1, dias_num // 24)
        elif unidad.startswith("sem"):
            dias_efectivos = dias_num * 7
        else:
            dias_efectivos = dias_num
    except (ValueError, IndexError):
        return None

    if peso_actual_kg and peso_actual_kg > 0:
        pct = (kg / peso_actual_kg) * 100
        if pct >= 5.0 and dias_efectivos <= 7:
            return (kg, dias_efectivos)
        return None
    if kg >= 3 and dias_efectivos <= 5:
        return (kg, dias_efectivos)
    return None


def detectar(
    texto: str, pais: str | None = "CO", peso_actual_kg: float | None = None
) -> CrisisDetected | None:
    """Analiza texto. Devuelve CrisisDetected si encuentra red flag.

    Args:
        texto: mensaje del usuario.
        pais: codigo ISO-2 para lineas locales.
        peso_actual_kg: peso del usuario para evaluar cut numerico (opcional).

    """
    resultado = _detectar_inner(texto, pais, peso_actual_kg)
    if resultado is not None:
        logger.warning(
            "Crisis detectada nivel=%s subcat=%s keywords=%s pais=%s",
            resultado.nivel,
            resultado.subcategoria,
            resultado.keywords[:5],
            pais,
        )
    return resultado


def _detectar_inner(
    texto: str, pais: str | None = "CO", peso_actual_kg: float | None = None
) -> CrisisDetected | None:
    if not texto:
        return None

    nivel_1_match = _NIVEL_1.findall(texto)
    if nivel_1_match:
        return CrisisDetected(
            nivel=1,
            keywords=list(set(nivel_1_match)),
            mensaje_contenedor=_mensaje_nivel_1(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="ideacion_suicida",
        )

    if _NIVEL_1_CONCUSION_RECIENTE.search(texto):
        return CrisisDetected(
            nivel=1,
            keywords=["segunda_concusion_reciente"],
            mensaje_contenedor=_mensaje_concusion_reciente(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="concusion_repetida",
        )

    if _NIVEL_1_APNEA_SOLO.search(texto):
        return CrisisDetected(
            nivel=1,
            keywords=["apnea_solo"],
            mensaje_contenedor=_mensaje_apnea_solo(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="apnea_riesgo_swb",
        )

    cut_num = _extraer_cut_numerico(texto, peso_actual_kg)
    if cut_num is not None:
        kg, dias = cut_num
        return CrisisDetected(
            nivel=2,
            keywords=[f"cut_{kg}kg_{dias}dias"],
            mensaje_contenedor=_mensaje_cut_extremo(pais, kg, dias),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="cut_extremo_combate",
        )

    if _NIVEL_2_CUT_EXTREMO_TEXT.search(texto):
        return CrisisDetected(
            nivel=2,
            keywords=["cut_extremo_practica_riesgosa"],
            mensaje_contenedor=_mensaje_cut_extremo(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="cut_extremo_combate",
        )

    if _NIVEL_2_TRAUMA_CRANEAL.search(texto):
        return CrisisDetected(
            nivel=2,
            keywords=["trauma_craneal_sospechado"],
            mensaje_contenedor=_mensaje_trauma_craneal(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="trauma_craneal",
        )

    nivel_2_tca = _NIVEL_2_TCA.findall(texto)
    nivel_2_dep = _NIVEL_2_DEPRE.findall(texto)
    if nivel_2_tca or nivel_2_dep:
        keys = [k for k in (nivel_2_tca + nivel_2_dep) if k]
        return CrisisDetected(
            nivel=2,
            keywords=list({str(k) for k in keys}),
            mensaje_contenedor=_mensaje_nivel_2(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="tca_depresion",
        )

    if _NIVEL_3_TRAUMA_ORTOPEDICO.search(texto):
        return CrisisDetected(
            nivel=3,
            keywords=["trauma_ortopedico_agudo"],
            mensaje_contenedor=_mensaje_trauma_ortopedico(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="trauma_ortopedico",
        )

    if _NIVEL_3_OTS.search(texto):
        return CrisisDetected(
            nivel=3,
            keywords=["overtraining_sospechado"],
            mensaje_contenedor=_mensaje_ots(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="sobreentrenamiento",
        )

    nivel_3_match = _NIVEL_3.findall(texto)
    if nivel_3_match:
        keys = [k for k in nivel_3_match if k]
        return CrisisDetected(
            nivel=3,
            keywords=list({str(k) for k in keys}),
            mensaje_contenedor=_mensaje_nivel_3(pais),
            lineas_crisis=_lineas_pais(pais),
            subcategoria="vigilancia_general",
        )

    return None


_DIAGNOSTICOS_PROHIBIDOS = re.compile(
    r"\b(tienes\s+(anorexia|bulimia|atracon|depresion|diabetes|hipertension|"
    r"obesidad|trastorno|tdah|ansiedad\s+generalizada|TOC|PTSD|concusion|"
    r"conmocion\s+cerebral)|"
    r"sufres\s+de\s+(anorexia|bulimia|depresion|diabetes|concusion)|"
    r"estas\s+(deprimid|enferm)|"
    r"diagnostico\s+(de|es)\s+(anorexia|bulimia|depresion|concusion))\b",
    re.IGNORECASE,
)


def detectar_diagnostico_output(texto: str) -> list[str]:
    """Anti-diagnostico en el output del agente. Devuelve frases ofensoras."""
    if not texto:
        return []
    return _DIAGNOSTICOS_PROHIBIDOS.findall(texto)
