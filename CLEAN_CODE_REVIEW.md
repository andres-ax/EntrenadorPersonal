# Evaluación de Clean Code — EntrenadorAX

**Fecha:** 2026-05-19

## Resumen

He revisado la base de código del proyecto `EntrenadorAX` para evaluar su nivel de "clean code". El proyecto está bien estructurado y funcional, pero todavía requiere mejoras para alcanzar un estándar profesional de limpieza de código.

## Lo bueno

- Arquitectura modular y separada por responsabilidades (`src/web`, `src/api`, `src/telegram`, `src/db`, `src/services`, `src/realtime`).
- `main.py` bien organizado: lifespan, inicialización de DB/Redis y setup del bot.
- Capa de persistencia centralizada en `src/db/repository.py`.
- Plantillas Jinja con `base.html` y layouts reutilizables.
- Logging centralizado con inyección de `request_id` y `telegram_id` (ContextVars).
- Soporte básico de SEO y generación dinámica de `sitemap.xml` y `robots.txt`.
- Código Python sin errores de sintaxis (validado con `python3 -m py_compile src/**/*.py`).

## Problemas detectados (prioridad)

1. Uso extensivo de `except Exception: pass` o `except Exception:` sin re-raise ni log detallado.
   - Archivos con múltiples `pass` silenciando errores: `src/main.py`, `src/tools.py`, `src/telegram/handlers.py`, `src/telegram/pubsub_listener.py`, `src/api/admin.py`, `src/db/repository.py`, etc.
   - Riesgo: oculta bugs y dificulta diagnosis en producción.

2. Módulos largos y con muchas responsabilidades.
   - `src/tools.py`, `src/telegram/handlers.py` y `src/db/repository.py` son candidatos a refactor para dividir en submódulos más pequeños.

3. Uso de globals/singletons impresos en varios módulos.
   - Ejemplos: `telegram_app`, `pubsub_task`, `_client` en `src/cache.py`, flags en `log_setup.py`.
   - Recomendación: encapsular en fábricas o clases singleton con tests.

4. Falta de linting/formatting y pruebas automatizadas en el entorno.
   - `ruff`/`black`/`isort` no están configurados en este entorno; agregarlos y un workflow de CI.

5. Cobertura de tests ausente o no verificada.
   - Añadir tests unitarios para `tools` y rutas críticas, y tests de integración para endpoints importantes.

## Estado general: ¿Es clean code?

- Estado actual: Parcialmente limpio. El layout, separación y estilo general son buenos, pero hay prácticas que impiden considerar el repo como "clean code" en nivel profesional.
- Para alcanzar el objetivo profesional es necesario remediar los puntos listados.

## Recomendaciones concretas (pasos prácticos)

1. Reemplazar `except Exception: pass` por manejos específicos y logging explícito.
   - Si la excepción puede ignorarse justificadamente, añadir un comentario que explique por qué.
2. Configurar linter y formateador:
   - Añadir a `pyproject.toml` o `requirements-dev.txt`:
     - `ruff`, `black`, `isort`, `mypy` (opcional).
   - Crear un workflow de CI (GitHub Actions) que ejecute lint + tests.
3. Dividir módulos grandes:
   - Extraer helpers y validaciones de `src/tools.py` a `src/tools/*.py`.
   - Separar handlers por grupos funcionales (`pagos`, `usuario`, `interacciones`).
4. Encapsular singletons:
   - Crear factories o clases para inicializar `Redis`, `TelegramApp`, `DB engine`.
   - Evitar modificar globals fuera de un módulo de bootstrap.
5. Añadir tests automatizados:
   - Unit tests para transformaciones en `tools.py`.
   - Tests para endpoints críticos (`/health`, `/webhook`, `/webhook-info`).
6. Mejorar mensajes de log y eliminar `pass` silenciosos.
7. Documentar el estilo de código y convenciones en `CONTRIBUTING.md`.

## Comandos útiles (rápidos)

```bash
# Instalar herramientas de linting / formateo
python3 -m pip install ruff black isort mypy

# Ejecutar ruff
ruff src/ --fix

# Formatear con black
black .

# Ejecutar pruebas (si existe carpeta tests/)
pytest -q
```

## Checklist sugerida para el sprint "Clean Code"

- [ ] Añadir `pyproject.toml` con configuración de `black` y `isort`.
- [ ] Configurar `ruff` y reglas personalizadas.
- [ ] Añadir `pre-commit` con `black` + `ruff`.
- [ ] Reemplazar los `except: pass` más críticos por handlers explícitos.
- [ ] Dividir 2 módulos grandes en submódulos (prioridad: `tools.py` y `handlers.py`).
- [ ] Implementar tests unitarios iniciales (objetivo: 60% de cobertura en módulos core).
- [ ] Añadir GitHub Actions para lint + tests.

---

Si quieres, puedo:
- Crear los archivos de configuración (`pyproject.toml`, `.github/workflows/ci.yml`, `.pre-commit-config.yaml`).
- Aplicar un primer pase automático de `ruff --fix` y `black` (si autorizas instalar herramientas en tu entorno).
- Refactorizar uno de los módulos largos como ejemplo (p. ej. dividir `src/tools.py`).

Dime qué prefieres y lo hago en la rama `clean_code` que ya creaste.
