"""Agente demo para el widget de chat en la landing page.

Verion "light" del coach: prompt corto, sin tools, sin acceso a DB.
Despues de 3 mensajes del visitante, inyecta CTA a Telegram.

Flujo:
1. Visitante abre widget en la landing.
2. POST /api/public/chat-demo con {mensaje, session_id?}.
3. Este modulo crea/reanuda sesion Redis (TTL 10 min, max 5 msgs).
4. Runner.run con demo_coach (gpt-4o-mini, prompt corto, tools=[]).
5. Retorna respuesta + session_id + restantes + cta si aplica.

Costos: ~$0.001-0.01 USD por visitante (3 turnos con gpt-4o-mini).
"""

from __future__ import annotations

import logging
import uuid

from agents import Agent, Runner

from src.cache import get_redis
from src.config import settings
from src.telegram.safe_session import SafeRedisSession

logger = logging.getLogger(__name__)

DEMO_TTL_SECONDS = 600
DEMO_MAX_MESSAGES = 5
DEMO_SESSION_PREFIX = "demo_chat"
DEMO_COUNTER_KEY = "demo_chat:count:{session_id}"

DEMO_INSTRUCTIONS = """Eres EntrenadorAX, un coach deportivo IA colombiano.

REGLAS ESTRICTAS:
1. Eres amigable, motivador y directo. Hablas en espanol colombiano informal.
2. En el PRIMER mensaje: presentate brevemente y pregunta que deporte practica y cual es su objetivo.
3. En el SEGUNDO mensaje: dale un tip personalizado basado en lo que dijo. Menciona que puedes registrar entrenos, comida, sueno y peso.
4. Del TERCER mensaje en adelante: dale un consejo mas y di EXACTAMENTE:

"Para guardar tu progreso y que te persiga de verdad, abre el bot en Telegram: t.me/EntrenadorAX_bot - Es gratis!"

5. NUNCA des consejos medicos. Si preguntan algo de salud, di "consulta tu medico".
6. Maximo 3 oraciones por respuesta. Se conciso.
7. NO inventes datos, metricas ni planes. Solo conversa y motiva.
8. Si preguntan por precios: "Starter desde $5.000 COP/mes. Mira los planes en la pagina."
"""

demo_coach = Agent(
    name="EntrenadorAX Demo",
    instructions=DEMO_INSTRUCTIONS,
    tools=[],
    model="gpt-4o-mini",
)


async def chat_demo(session_id: str | None, mensaje: str) -> dict:
    """Procesa un mensaje del widget demo.

    Returns
    -------
        dict con keys: respuesta, session_id, restantes, cta_url (o None).

    """
    client = await get_redis()

    if not session_id:
        session_id = str(uuid.uuid4())

    counter_key = DEMO_COUNTER_KEY.format(session_id=session_id)
    count = await client.incr(counter_key)
    if count == 1:
        await client.expire(counter_key, DEMO_TTL_SECONDS)

    if count > DEMO_MAX_MESSAGES:
        return {
            "respuesta": (
                "Ya hablamos bastante por aca! Para seguir entrenando conmigo "
                "de verdad, abre el bot en Telegram. Es gratis y guardo todo "
                "tu progreso. Nos vemos alla!"
            ),
            "session_id": session_id,
            "restantes": 0,
            "cta_url": "https://t.me/EntrenadorAX_bot",
        }

    session = SafeRedisSession.from_url(
        f"{DEMO_SESSION_PREFIX}:{session_id}",
        url=settings.redis_url_str,
        ttl=DEMO_TTL_SECONDS,
    )

    try:
        result = await Runner.run(demo_coach, mensaje, session=session)
        respuesta = result.final_output or "Hmm, no entendi. Intenta de nuevo!"
    except Exception:
        logger.exception("Error en chat_demo session=%s", session_id)
        respuesta = "Tuve un saltico tecnico. Intenta de nuevo!"
    finally:
        try:
            await session.close()
        except Exception:
            pass

    restantes = max(0, DEMO_MAX_MESSAGES - count)
    cta_url = "https://t.me/EntrenadorAX_bot" if count >= 3 else None

    return {
        "respuesta": respuesta,
        "session_id": session_id,
        "restantes": restantes,
        "cta_url": cta_url,
    }
