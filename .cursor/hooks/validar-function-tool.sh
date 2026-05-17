#!/usr/bin/env bash
# afterFileEdit hook: cuando se edita src/tools.py (o cualquier .py con
# @function_tool), valida con python3 que cada funcion decorada tenga:
#   1. docstring no vacio
#   2. seccion "Args:" en el docstring
#   3. type hint de retorno explicito a `str` (firma del SDK)
#
# Devuelve `additional_context` con la lista de violaciones encontradas, sin bloquear.
# Solo aplica a archivos con `@function_tool` para no procesar todo el codebase.

set -euo pipefail

input=$(cat)

if ! command -v jq >/dev/null 2>&1; then
  echo '{}'
  exit 0
fi

file_path=$(echo "$input" | jq -r '.file_path // .filePath // .file // empty')

if [[ -z "$file_path" || ! -f "$file_path" || "$file_path" != *.py ]]; then
  echo '{}'
  exit 0
fi

if ! grep -q '@function_tool' "$file_path" 2>/dev/null; then
  echo '{}'
  exit 0
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo '{}'
  exit 0
fi

violaciones=$(python3 - "$file_path" <<'PY'
import ast
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
except SyntaxError:
    sys.exit(0)

violaciones: list[str] = []


def es_function_tool(deco: ast.expr) -> bool:
    if isinstance(deco, ast.Name) and deco.id == "function_tool":
        return True
    if isinstance(deco, ast.Attribute) and deco.attr == "function_tool":
        return True
    if isinstance(deco, ast.Call):
        return es_function_tool(deco.func)
    return False


def returns_str(node: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    r = node.returns
    if r is None:
        return False
    if isinstance(r, ast.Name) and r.id == "str":
        return True
    if isinstance(r, ast.Constant) and r.value == "str":
        return True
    return False


for node in ast.walk(tree):
    if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
        continue
    if not any(es_function_tool(d) for d in node.decorator_list):
        continue

    nombre = node.name
    linea = node.lineno

    docstring = ast.get_docstring(node)
    if not docstring or not docstring.strip():
        violaciones.append(f"L{linea} {nombre}: falta docstring (el SDK lo usa para schema del LLM)")
        continue

    if "Args:" not in docstring and "args:" not in docstring.lower():
        violaciones.append(f"L{linea} {nombre}: docstring sin seccion 'Args:' (formato Google-style)")

    if not returns_str(node):
        violaciones.append(
            f"L{linea} {nombre}: falta `-> str` en la firma (las tools deben devolver str JSON)"
        )

    if not isinstance(node, ast.AsyncFunctionDef):
        violaciones.append(f"L{linea} {nombre}: debe ser `async def` (EntrenadorAX es async-first)")

if violaciones:
    print("\n".join(violaciones))
PY
)

if [[ -z "$violaciones" ]]; then
  echo '{}'
  exit 0
fi

mensaje="validar-function-tool encontro issues en $file_path:
$violaciones

Skills relevantes: .cursor/skills/openai-agents-sdk/referencias/tools.md y la rule openai-agents-sdk-patterns.mdc."

jq -n --arg ctx "$mensaje" '{additional_context: $ctx}'
exit 0
