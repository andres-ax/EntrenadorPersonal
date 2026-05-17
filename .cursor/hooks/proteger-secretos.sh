#!/usr/bin/env bash
# beforeShellExecution hook: bloquea `git commit|push|add` si detecta secretos
# (TELEGRAM_TOKEN, OPENAI_API_KEY, DATABASE_URL, REDIS_URL) en:
#   1. el comando mismo (ej: `git add .env`)
#   2. el diff staged actual
#   3. archivos que el comando intenta agregar
# Fail closed: si jq/git fallan, denegamos por seguridad.

set -euo pipefail

input=$(cat)

if ! command -v jq >/dev/null 2>&1; then
  echo '{"permission":"deny","agent_message":"Hook proteger-secretos requiere jq.","user_message":"Instala jq para que el hook de proteccion de secretos pueda funcionar."}'
  exit 0
fi

command_str=$(echo "$input" | jq -r '.command // empty')

if [[ -z "$command_str" ]]; then
  echo '{"permission":"allow"}'
  exit 0
fi

# Patrones de secretos reales (no placeholders tipo "tu_token_aqui" o "xxx").
patron_telegram='TELEGRAM_TOKEN[[:space:]]*=[[:space:]]*["'\'']?[0-9]{6,}:[A-Za-z0-9_-]{30,}'
patron_openai='OPENAI_API_KEY[[:space:]]*=[[:space:]]*["'\'']?(sk-|sk-proj-)[A-Za-z0-9_-]{20,}'
patron_pg='DATABASE_URL[[:space:]]*=[[:space:]]*["'\'']?postgres(ql)?(\+asyncpg)?://[^:]+:[^@]+@'
patron_redis='REDIS_URL[[:space:]]*=[[:space:]]*["'\'']?redis(s)?://[^:]*:[^@]+@'

todos_los_patrones="$patron_telegram|$patron_openai|$patron_pg|$patron_redis"

denegar() {
  local razon="$1"
  jq -n --arg r "$razon" '{
    permission: "deny",
    agent_message: ("Hook bloqueo el comando: " + $r + ". Revisa que .env no se este commiteando y que ningun secreto este pegado en codigo trackeado."),
    user_message: ("Se detecto un posible secreto sensible: " + $r + ". El commit/push fue bloqueado. Revisa los archivos staged.")
  }'
  exit 0
}

# Verificacion 1: el comando mismo contiene el secreto en plano
# (ej: alguien pega la cadena de conexion completa dentro del mensaje de commit).
if echo "$command_str" | grep -qE "$todos_los_patrones"; then
  denegar "secreto detectado dentro del comando ejecutado"
fi

# Verificacion 2: el comando intenta agregar .env directamente
if echo "$command_str" | grep -qE '\bgit\s+add\b.*\.env(\b|/)' ; then
  denegar "comando intenta agregar .env al staging"
fi

# Verificacion 3: hay un diff staged con secretos
if command -v git >/dev/null 2>&1 && git rev-parse --git-dir >/dev/null 2>&1; then
  diff_staged=$(git diff --cached 2>/dev/null || true)
  if [[ -n "$diff_staged" ]]; then
    if echo "$diff_staged" | grep -qE "$todos_los_patrones"; then
      denegar "se encontraron credenciales en el diff staged actual"
    fi
  fi

  # Verificacion 4: archivos sin trackear nombrados explicitamente en el comando
  # que contienen secretos (ej: `git add archivo_temporal.txt`).
  if echo "$command_str" | grep -qE '\bgit\s+add\b'; then
    while IFS= read -r posible_archivo; do
      [[ -z "$posible_archivo" || ! -f "$posible_archivo" ]] && continue
      if grep -qE "$todos_los_patrones" "$posible_archivo" 2>/dev/null; then
        denegar "el archivo $posible_archivo contiene secretos"
      fi
    done < <(echo "$command_str" | grep -oE '[^[:space:]]+' | tail -n +3)
  fi
fi

echo '{"permission":"allow"}'
exit 0
