"""Servicio de compresión de contexto y de-duplicación para reportes extensos.

Permite colapsar espacios y de-duplicar líneas redundantes, garantizando que el
historial guardado en la sesión de Redis no cause desbordamiento de tokens ni de caracteres.
"""
from __future__ import annotations

import re


def compress_summary_text(text: str, max_chars: int = 1200, max_lines: int = 24) -> str:
    """Comprime textos de reportes largos colapsando espacios y reduciendo líneas.

    Preserva las cabeceras y pies del reporte original proporcionando un aviso semántico
    de las líneas omitidas.

    Args:
        text: El texto del reporte o resumen a comprimir.
        max_chars: El límite presupuestado de caracteres permitidos.
        max_lines: El número máximo de líneas del reporte.

    Returns:
        El texto comprimido y formateado de forma compacta.
    """
    if not text:
        return ""

    # Normalizar líneas eliminando espacios múltiples y líneas vacías superfluas
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]

    # De-duplicación sintáctica respetando mayúsculas y minúsculas
    seen = set()
    unique_lines = []
    for line in lines:
        normalized = line.lower()
        if normalized not in seen:
            seen.add(normalized)
            unique_lines.append(line)

    # Si ya cumple con las restricciones de líneas y caracteres, retornar como está
    total_length = sum(len(line) for line in unique_lines) + len(unique_lines) - 1
    if len(unique_lines) <= max_lines and total_length <= max_chars:
        return "\n".join(unique_lines)

    # Si se sobrepasan los límites, truncar preservando cabecera y pie con aviso semántico
    half = max_lines // 2
    if half < 1:
        half = 1

    top_part = unique_lines[:half]
    bottom_part = unique_lines[-half:]
    omitted = len(unique_lines) - (len(top_part) + len(bottom_part))

    # Asegurar que no hay solapamiento
    if omitted <= 0:
        # En caso de que max_lines sea muy cercano a len(unique_lines), simplemente tomamos la parte superior
        top_part = unique_lines[:max_lines - 1]
        bottom_part = [unique_lines[-1]] if len(unique_lines) > max_lines else []
        omitted = len(unique_lines) - (len(top_part) + len(bottom_part))

    aviso = f"\n[... {omitted} líneas omitidas por presupuesto de contexto ...]\n"
    compressed_lines = top_part + [aviso] + bottom_part
    compressed_text = "\n".join(compressed_lines)

    # Truncar por caracteres si aún supera el presupuesto estricto
    if len(compressed_text) > max_chars:
        compressed_text = compressed_text[:max_chars - 3] + "..."

    return compressed_text
