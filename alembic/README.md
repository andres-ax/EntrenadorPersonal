# Alembic - Migraciones de schema

## Comandos comunes

```bash
# Aplicar todas las migraciones pendientes
alembic upgrade head

# Marcar la DB actual como "ya en head" sin ejecutar migraciones
# (usar UNA vez si vienes de la version anterior que usaba create_all)
alembic stamp head

# Crear una nueva migracion autodetectada desde los cambios en models.py
alembic revision --autogenerate -m "agregar columna X"

# Ver historial
alembic history --verbose

# Bajar una migracion
alembic downgrade -1
```

## Estrategia EntrenadorAX

- `init_db()` en `src/db/connection.py` queda solo para tests / desarrollo
  local rapido (sqlite en memoria).
- En produccion (Railway) el contenedor ejecuta `alembic upgrade head`
  antes de iniciar uvicorn. Se agrega al comando de arranque del Dockerfile
  o railway.toml.

## Variables de entorno

`alembic/env.py` lee `settings.database_url_str` (normaliza
`postgresql://` -> `postgresql+asyncpg://`) desde `src/config.py`. No
hace falta definir `sqlalchemy.url` en `alembic.ini`.
