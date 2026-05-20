"""RedisSession subclase que NUNCA deja `function_call_output` huerfanos.

Problema que resuelve
---------------------

`agents.extensions.memory.RedisSession.get_items(limit=N)` simplemente lee los
ultimos N items de Redis (LRANGE -N -1). Si en esos N items hay un
`function_call_output` cuyo `function_call` correspondiente (matching por
`call_id`) quedo fuera del rango, la OpenAI Responses API rechaza el request
con:

    400 Bad Request: No tool call found for function call output with
    call_id call_<id>

En produccion lo vimos con `session_limit=60` cuando el coach hace varias
tools en paralelo (cancelar_recordatorio + cancelar_recordatorio +
programar_recordatorio = 6 items en un mismo turno) y al siguiente mensaje
el truncamiento corta el grupo a mitad.

Estrategia
----------

Override `get_items(limit)` para:

1. Leer los ultimos `limit` items (comportamiento original).
2. Identificar `function_call`s presentes (set de call_ids).
3. Filtrar los `function_call_output` que NO tengan su call en el set.
4. Devolver la lista limpia. Si quedan menos items que `limit`, esta bien.

Esto se ejecuta solo en lectura, sin tocar la data en Redis. El siguiente
escrito (al final del turno via `add_items`) seguira agregando items
normalmente; los items huerfanos quedan en Redis pero el LLM nunca los ve.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from agents.extensions.memory import RedisSession
from agents.items import TResponseInputItem

logger = logging.getLogger(__name__)


class SafeRedisSession(RedisSession):
    """RedisSession que filtra `function_call_output` huerfanos al leer y comprime reportes.

    El metodo `pop_item`, `clear_session` y el resto siguen delegando al padre.
    `get_items` filtra los outputs huerfanos, y `add_items` comprime los reportes.
    """

    async def add_items(self, items: list[TResponseInputItem]) -> None:
        """Agrega ítems a la sesión comprimiendo reportes y resúmenes de forma no-bloqueante."""
        from src.services.summary_compression import compress_summary_text

        nuevos_items: list[TResponseInputItem] = []
        for it in items:
            if isinstance(it, dict) and it.get("type") == "function_call_output":
                output_val = it.get("output")
                # Si es un output de herramienta y es extenso, comprobar si es un reporte o resumen
                if isinstance(output_val, str) and len(output_val) > 400:
                    lowered = output_val.lower()
                    # Identificar reportes de comida, nutrición, progreso o resúmenes semanales
                    es_reporte = any(
                        keyword in lowered
                        for keyword in ["reporte", "resumen", "comida", "nutricional", "progreso", "semanal"]
                    )
                    if es_reporte:
                        try:
                            # Compresión no-bloqueante en un hilo de fondo (CPU bound)
                            compressed_val = await asyncio.to_thread(compress_summary_text, output_val)
                            it = dict(it)  # Clonar diccionario para evitar mutaciones directas colaterales
                            it["output"] = compressed_val
                            logger.info(
                                "SafeRedisSession session_id=%s comprimió reporte largo de %d a %d caracteres de forma no-bloqueante",
                                self.session_id,
                                len(output_val),
                                len(compressed_val),
                            )
                        except Exception:
                            logger.exception("Error al intentar comprimir reporte en SafeRedisSession")
            nuevos_items.append(it)

        await super().add_items(nuevos_items)

    async def get_items(self, limit: int | None = None) -> list[TResponseInputItem]:
        items = await super().get_items(limit=limit)
        if not items:
            return items

        # Recopila call_ids de los function_call presentes en la ventana.
        call_ids_presentes: set[str] = set()
        for it in items:
            if not isinstance(it, dict):
                continue
            tipo = it.get("type")
            if tipo == "function_call":
                call_id = it.get("call_id") or it.get("id")
                if call_id:
                    call_ids_presentes.add(str(call_id))

        # Filtra outputs huerfanos.
        limpios: list[TResponseInputItem] = []
        huerfanos = 0
        for it in items:
            if isinstance(it, dict) and it.get("type") == "function_call_output":
                call_id = it.get("call_id")
                if call_id and str(call_id) not in call_ids_presentes:
                    huerfanos += 1
                    continue
            limpios.append(it)

        if huerfanos:
            logger.warning(
                "SafeRedisSession session_id=%s descarto %d "
                "function_call_output huerfanos (ventana=%d items)",
                self.session_id,
                huerfanos,
                len(items),
            )
        return limpios

    @classmethod
    def from_url(
        cls,
        session_id: str,
        *,
        url: str,
        redis_kwargs: dict[str, Any] | None = None,
        session_settings: Any | None = None,
        **kwargs: Any,
    ) -> SafeRedisSession:
        """Forwarder a RedisSession.from_url que devuelve nuestra subclase.

        Necesario porque el `from_url` del padre hace `cls(...)`, pero queremos
        ser explicitos en el tipo de retorno.
        """
        session = super().from_url(
            session_id,
            url=url,
            redis_kwargs=redis_kwargs,
            session_settings=session_settings,
            **kwargs,
        )
        return session  # type: ignore[return-value]
