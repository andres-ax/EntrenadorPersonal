#!/usr/bin/env bash
# afterFileEdit hook: ejecuta `ruff check --fix` y `ruff format` sobre archivos .py
# editados por el agente. Devuelve additional_context con resumen si hubo cambios.
# Fail open: si ruff no esta instalado o falla, no bloquea la edicion.

set -euo pipefail

input=$(cat)

# Soft-fallback si jq no esta disponible: no rompemos el flujo.
if ! command -v jq >/dev/null 2>&1; then
  echo '{}'
  exit 0
fi

file_path=$(echo "$input" | jq -r '.file_path // .filePath // .file // empty')

if [[ -z "$file_path" || ! -f "$file_path" ]]; then
  echo '{}'
  exit 0
fi

if [[ "$file_path" != *.py ]]; then
  echo '{}'
  exit 0
fi

if ! command -v ruff >/dev/null 2>&1; then
  echo '{"additional_context":"ruff no esta instalado en este entorno; se omitio el auto-format. Instala con `pip install ruff` o `pip install -r requirements-dev.txt`."}'
  exit 0
fi

# Hash antes/despues para detectar si ruff modifico el archivo.
hash_before=$(sha256sum "$file_path" | awk '{print $1}')

ruff_check_out=$(ruff check --fix --quiet "$file_path" 2>&1 || true)
ruff_fmt_out=$(ruff format --quiet "$file_path" 2>&1 || true)

hash_after=$(sha256sum "$file_path" | awk '{print $1}')

if [[ "$hash_before" == "$hash_after" ]]; then
  echo '{}'
  exit 0
fi

resumen="ruff auto-formateo $file_path"
if [[ -n "$ruff_check_out" ]]; then
  resumen="$resumen | check: $(echo "$ruff_check_out" | head -3 | tr '\n' ' ')"
fi
if [[ -n "$ruff_fmt_out" ]]; then
  resumen="$resumen | format: $(echo "$ruff_fmt_out" | head -3 | tr '\n' ' ')"
fi

jq -n --arg ctx "$resumen" '{additional_context: $ctx}'
exit 0
