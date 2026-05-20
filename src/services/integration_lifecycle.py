"""Servicio de ciclo de vida de integración y control de resiliencia mediante Circuit Breakers.

Implementa un Circuit Breaker asíncrono que previene bloqueos del event loop del bot de Telegram
ante la latencia o indisponibilidad de APIs externas de terceros y servicios de base de datos.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


class CircuitBreakerOpenException(Exception):
    """Excepción lanzada cuando el circuito está ABIERTO y el servicio no debe ser invocado."""
    pass


class IntegrationCircuitBreaker:
    """Implementa el patrón de Circuit Breaker asíncrono con control de timeouts.

    Gestiona tres estados lógicos:
    - CLOSED: Todo funciona normalmente. Las solicitudes se envían de forma directa.
    - OPEN: El servicio está fallando constantemente. Se descartan llamadas de inmediato (Fail-fast).
    - HALF-OPEN: El tiempo de enfriamiento ha vencido; se realiza una prueba única para verificar sanidad.
    """

    def __init__(self, name: str, threshold: int = 3, cooldown_seconds: int = 60):
        """Inicializa el Circuit Breaker.

        Args:
            name: Nombre de la integración (ej: 'openai_comprobantes_vision').
            threshold: Número de fallas consecutivas permitidas antes de abrir el circuito.
            cooldown_seconds: Tiempo en segundos que el circuito permanecerá abierto antes de pasar a HALF-OPEN.
        """
        self.name = name
        self.threshold = threshold
        self.cooldown = cooldown_seconds
        self.failures = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_failure_time: float = 0.0

    async def call(
        self, func: Callable[..., Any], *args: Any, timeout_seconds: float = 10.0, **kwargs: Any
    ) -> Any:
        """Invoca la función provista asíncronamente a través del Circuit Breaker.

        Args:
            func: Función asíncrona a invocar.
            args: Argumentos posicionales de la función.
            timeout_seconds: Límite estricto de ejecución en segundos (asynchronous timeout).
            kwargs: Argumentos de palabra clave de la función.

        Returns:
            El valor retornado por la función.

        Raises:
            CircuitBreakerOpenException: Si el circuito está OPEN y el cooldown no ha vencido.
            asyncio.TimeoutError: Si la función supera el tiempo de espera.
            Exception: Si la función eleva cualquier otro tipo de error.
        """
        ahora = time.time()

        # Si el circuito está abierto, verificar si ha pasado el tiempo de enfriamiento
        if self.state == "OPEN":
            if ahora - self.last_failure_time > self.cooldown:
                self.state = "HALF-OPEN"
                logger.info(
                    "Circuit breaker %s ha entrado en estado HALF-OPEN tras expirar el cooldown",
                    self.name,
                )
            else:
                logger.warning(
                    "Circuit breaker %s rechazó solicitud en estado OPEN (le quedan %ds de enfriamiento)",
                    self.name,
                    int(self.cooldown - (ahora - self.last_failure_time)),
                )
                raise CircuitBreakerOpenException(
                    f"El servicio externo '{self.name}' está temporalmente indisponible (Circuito ABIERTO)."
                )

        try:
            # Ejecución con límite estricto de tiempo para proteger el event loop
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)

            # Si funciona con éxito en estado HALF-OPEN, cerramos el circuito
            if self.state == "HALF-OPEN":
                self.state = "CLOSED"
                self.failures = 0
                logger.info(
                    "Circuit breaker %s ha vuelto a CLOSED con éxito tras prueba satisfactoria",
                    self.name,
                )

            return result

        except asyncio.TimeoutError as e:
            logger.error(
                "Circuit breaker %s registró falla de TIMEOUT (umbral=%d, fallas=%d)",
                self.name,
                self.threshold,
                self.failures + 1,
            )
            self._handle_failure()
            raise e

        except Exception as e:
            logger.error(
                "Circuit breaker %s registró falla de EXCEPCIÓN (%s: %s)",
                self.name,
                type(e).__name__,
                str(e),
            )
            self._handle_failure()
            raise e

    def _handle_failure(self) -> None:
        """Registra un fallo consecutivo y abre el circuito si supera el umbral."""
        self.failures += 1
        self.last_failure_time = time.time()

        if self.failures >= self.threshold:
            self.state = "OPEN"
            logger.critical(
                "Circuit breaker %s se ha ABIERTO tras %d fallas consecutivas. cooldown=%ds",
                self.name,
                self.failures,
                self.cooldown,
            )
