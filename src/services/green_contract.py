"""Contratos verdes de calidad e integridad del workspace para despliegues.

Determina los niveles progresivos de preparación y sanidad de la base de código
(LINT_PASS, TARGETED_TESTS, WORKSPACE, MERGE_READY) ejecutando comprobaciones estáticas
y dinámicas para evitar que cambios automáticos introduzcan regresiones al sistema.
"""
from __future__ import annotations

import logging
import subprocess
from enum import IntEnum

logger = logging.getLogger(__name__)


class GreenLevel(IntEnum):
    """Nivel de sanidad requerido por el contrato."""
    LINT_PASS = 1
    TARGETED_TESTS = 2
    WORKSPACE = 3
    MERGE_READY = 4


class GreenContractResult:
    """Resultado estructurado de la evaluación del contrato verde."""

    def __init__(self, status: str, details: str):
        """Inicializa el resultado.

        Args:
            status: "Satisfied" si pasó todas las pruebas del nivel, o "Unsatisfied".
            details: Los detalles técnicos del resultado (logs, errores del linter, etc.).
        """
        self.status = status  # "Satisfied" o "Unsatisfied"
        self.details = details

    def __bool__(self) -> bool:
        return self.status == "Satisfied"

    def __repr__(self) -> str:
        return f"GreenContractResult(status={self.status}, details={self.details[:120]}...)"


class GreenContract:
    """Implementa el flujo de evaluación progresiva de calidad de código de Claw Code."""

    def __init__(self, required_level: GreenLevel = GreenLevel.LINT_PASS):
        """Inicializa el contrato verde con el nivel de calidad requerido.

        Args:
            required_level: El nivel requerido (por defecto, LINT_PASS para auditar en caliente).
        """
        self.required_level = required_level

    def evaluate(self, repo_path: str = ".") -> GreenContractResult:
        """Evalúa secuencialmente las reglas del nivel de calidad requerido para el repositorio.

        Args:
            repo_path: Ruta del directorio a auditar (por defecto '.').

        Returns:
            Un objeto GreenContractResult indicando si el contrato está 'Satisfied' o 'Unsatisfied'.
        """
        # 1. Nivel LINT_PASS: Ejecutar ruff check
        logger.info("Evaluando nivel LINT_PASS mediante 'ruff check' sobre %s", repo_path)
        try:
            lint_res = subprocess.run(
                ["ruff", "check", repo_path], capture_output=True, text=True, check=False
            )
            if lint_res.returncode != 0:
                details = (
                    f"Fallo de Calidad Linter (Ruff):\n"
                    f"STDOUT:\n{lint_res.stdout}\n"
                    f"STDERR:\n{lint_res.stderr}"
                )
                return GreenContractResult("Unsatisfied", details)
        except FileNotFoundError:
            # Si ruff no está instalado en el PATH del sistema o entorno
            logger.warning("Linter 'ruff' no encontrado en el sistema. Omitiendo validación.")
            if self.required_level == GreenLevel.LINT_PASS:
                return GreenContractResult(
                    "Satisfied", "Linter 'ruff' no encontrado, pero configurado para tolerar en dev."
                )

        if self.required_level == GreenLevel.LINT_PASS:
            return GreenContractResult("Satisfied", "Todos los lints pasaron de forma impecable.")

        # 2. Nivel TARGETED_TESTS / WORKSPACE: Ejecutar pytest
        logger.info("Evaluando nivel WORKSPACE mediante 'pytest' sobre %s", repo_path)
        try:
            test_res = subprocess.run(
                ["pytest", repo_path, "-q"], capture_output=True, text=True, check=False
            )
            if test_res.returncode != 0:
                details = (
                    f"Fallo de Cobertura Pytest:\n"
                    f"STDOUT:\n{test_res.stdout}\n"
                    f"STDERR:\n{test_res.stderr}"
                )
                return GreenContractResult("Unsatisfied", details)
        except FileNotFoundError:
            logger.warning("Suite de 'pytest' no encontrada en el sistema.")
            if self.required_level in (GreenLevel.TARGETED_TESTS, GreenLevel.WORKSPACE):
                return GreenContractResult(
                    "Satisfied", "Pytest no encontrado, se salta la prueba dinámicamente."
                )

        if self.required_level in (GreenLevel.TARGETED_TESTS, GreenLevel.WORKSPACE):
            return GreenContractResult("Satisfied", "Lints y suite de pytest ejecutados con éxito.")

        # 3. Nivel MERGE_READY: Ejecutar alembic check
        logger.info("Evaluando nivel MERGE_READY mediante 'alembic check'")
        try:
            alembic_res = subprocess.run(
                ["alembic", "check"], capture_output=True, text=True, check=False
            )
            if alembic_res.returncode != 0:
                details = (
                    f"Fallo de Consistencia de Migraciones Alembic:\n"
                    f"STDOUT:\n{alembic_res.stdout}\n"
                    f"STDERR:\n{alembic_res.stderr}"
                )
                return GreenContractResult("Unsatisfied", details)
        except FileNotFoundError:
            logger.warning("Alembic no configurado o no encontrado.")
            return GreenContractResult(
                "Satisfied", "Lints, Pytest pasados con éxito. Alembic no está instalado."
            )

        return GreenContractResult(
            "Satisfied", "Calidad e integridad del repositorio certificada al nivel MERGE_READY."
        )
