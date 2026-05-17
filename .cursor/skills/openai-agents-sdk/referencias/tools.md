# Tools con `@function_tool`

Doc oficial: https://openai.github.io/openai-agents-python/tools/

## Como funciona internamente

```
1. Decorador @function_tool inspecciona la firma de la funcion.
2. Construye un schema JSON desde type hints + docstring (Google-style preferido).
3. El schema se envia al LLM en cada llamada como una "tool disponible".
4. Cuando el LLM decide invocarla, el SDK la llama con los args parseados.
5. El return value (debe ser str) se inyecta como tool message al modelo.
```

Implicacion: la calidad del docstring DETERMINA cuando el LLM usa la tool.

## Anatomia de una tool buena

```python
from agents import function_tool
import json

@function_tool
async def registrar_entreno(
    telegram_id: int,
    fecha: str,
    tipo: str,
    duracion_min: int = 60,
    ejercicios_json: str = "[]",
    rpe: float = 0,
    notas: str = "",
) -> str:
    """Registra un entrenamiento completo.

    Args:
        telegram_id: ID de Telegram del usuario
        fecha: formato YYYY-MM-DD
        tipo: DEBE ser uno de: fuerza, cardio, movilidad, deporte
        duracion_min: duracion en minutos
        ejercicios_json: JSON array de ejercicios, ej: [{"nombre":"sentadilla","series":4,"reps":8,"peso_kg":80}]
        rpe: esfuerzo percibido 1-10 (0 si no se sabe)
        notas: notas adicionales
    """
    fecha = _validar_fecha(fecha)
    tipo = tipo.lower().strip()
    if tipo not in TIPOS_ENTRENO_VALIDOS:
        return json.dumps({"ok": False, "error": f"tipo invalido: {tipo}"})

    ejercicios = _safe_json_loads(ejercicios_json, [])
    sesion = await repo_guardar_sesion(...)
    return json.dumps({"ok": True, "sesion_id": sesion.id})
```

Checklist:

- [ ] `async def`
- [ ] Type hints SIMPLES en todos los args (`int`, `float`, `str`, `bool`)
- [ ] Docstring Google-style con seccion `Args:`
- [ ] Defaults seguros (0 para opcionales numericos, "" para strings, "[]" para JSON)
- [ ] Validacion enum / rangos al inicio
- [ ] Devuelve `str` JSON-serializable
- [ ] Try/except interno (no levantar excepciones)
- [ ] No tiene side effects mas alla del proposito (1 tool = 1 cosa)

## Tipos complejos: workaround

El SDK genera schemas claros con tipos primitivos. Para listas/dicts anidados, mejor recibir `str` JSON y parsear:

```python
# MAL: tipo complejo que confunde al LLM
@function_tool
async def registrar(ejercicios: list[dict]) -> str: ...

# BIEN: JSON string, parsear dentro
@function_tool
async def registrar(ejercicios_json: str = "[]") -> str:
    """...
    Args:
        ejercicios_json: JSON array, ej: [{"nombre":"X","reps":8}]
    """
    ejercicios = _safe_json_loads(ejercicios_json, [])
```

Helper:

```python
def _safe_json_loads(raw: str, fallback=None):
    if not raw or raw.strip() == "":
        return fallback if fallback is not None else []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback if fallback is not None else []
```

## Manejo de errores

### Regla: NUNCA levantar excepciones desde una tool

```python
# MAL
@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    pr = await repo.get_pr(telegram_id, ejercicio)  # puede lanzar
    return json.dumps({"peso_kg": pr.peso_kg})  # crash si pr es None

# BIEN
@function_tool
async def obtener_pr(telegram_id: int, ejercicio: str) -> str:
    try:
        pr = await repo.get_pr(telegram_id, ejercicio)
        if pr is None:
            return json.dumps({"mensaje": f"No hay PR para '{ejercicio}'"})
        return json.dumps({"peso_kg": pr.peso_kg, "reps": pr.reps})
    except Exception as e:
        logger.exception("Error en obtener_pr")
        return json.dumps({"ok": False, "error": "error consultando PR"})
```

El LLM puede decidir reintentar la tool con args distintos si recibe `{"ok": False}`. Si lanzaras una excepcion, el RUN entero falla.

## Tool factories (parametrizar tools por contexto)

Si necesitas inyectar dependencias (ej: tenant_id, feature flags):

```python
def build_logger_tool(tenant_id: str):
    @function_tool
    async def log_evento(mensaje: str) -> str:
        """Registra un evento.
        Args:
            mensaje: texto del evento
        """
        await audit_log.write(tenant_id, mensaje)
        return json.dumps({"ok": True})
    return log_evento

agent = Agent(tools=[build_logger_tool(tenant_id="ax")])
```

## Tools sincronas vs async

El SDK soporta ambas, pero **siempre preferir async** en EntrenadorAX (todo el stack es async). Bloquear el event loop con I/O sync degrada throughput.

```python
# MAL en EntrenadorAX
@function_tool
def obtener_perfil(telegram_id: int) -> str:
    user = repo.get_user_sync(telegram_id)  # bloqueante

# BIEN
@function_tool
async def obtener_perfil(telegram_id: int) -> str:
    user = await repo.get_user(telegram_id)
```

## Cantidad y curacion de tools

| # de tools | Comportamiento del LLM |
|---|---|
| 1-5 | Excelente discriminacion, casi nunca confunde |
| 6-12 | Buena (EntrenadorAX esta aqui con 12) |
| 13-20 | El LLM puede equivocarse de tool; mejorar docstrings |
| 21+ | Considerar handoffs / agentes especialistas |

EntrenadorAX tiene 12 tools (ver `ALL_TOOLS` en [src/coach.py](../../../../src/coach.py)). Llegar a 15+ implica dividir en agentes (handoffs).

## Validacion de input antes de la tool

Para validacion compleja, mejor usar **input guardrails** (ver [handoffs-guardrails.md](handoffs-guardrails.md)) en lugar de checks dentro de la tool. Esto:

- Centraliza la logica de validacion
- Permite abortar el run completo si el input es invalido
- No gasta tokens en tool calls que van a fallar

## Como saber si tu tool es invocada

Activa tracing (default en SDK) y consulta https://platform.openai.com/traces. Veras:

- Cuales tools llamo el agente
- Argumentos exactos
- Output que devolvio
- Tiempo de cada tool

Es la mejor herramienta para debuggear "por que el agente no usa mi tool".

## Tools de OpenAI built-in

Ademas de `@function_tool`, hay tools hosted (web search, code interpreter, computer use, file search). EntrenadorAX no las usa hoy, pero relevantes si en el futuro:

- `WebSearchTool()`: el agente puede consultar la web
- `CodeInterpreterTool()`: ejecuta Python en sandbox
- `FileSearchTool(vector_store_ids=[...])`: RAG sobre Vector Stores de OpenAI

Costo: cada una factura aparte del LLM. Para casos como "el agente busca informacion nutricional actualizada", `WebSearchTool` podria ser util.
