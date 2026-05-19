# Infraestructura y Despliegue - EntrenadorAX

Este documento detalla la arquitectura de infraestructura, los servicios externos, el entorno de ejecución y los detalles de despliegue del proyecto **EntrenadorAX**.

## Tecnologías Base

El proyecto está construido utilizando un stack moderno, asíncrono y orientado a microservicios:

- **Python 3.12**: Lenguaje base del proyecto (definido como `>=3.11` en `pyproject.toml`, pero contenedorizado con `3.12-slim`).
- **FastAPI** (`>=0.115`): Framework web ultrarrápido utilizado para exponer los endpoints de salud (`/health`) y manejar el Webhook de Telegram.
- **Uvicorn** (`>=0.34`): Servidor ASGI para la ejecución en producción de FastAPI.
- **SQLAlchemy Asyncio** (`>=2.0`): ORM asíncrono utilizado para la persistencia de datos.
- **OpenAI Agents SDK** (`>=0.14`): Librería utilizada para la integración del agente conversacional inteligente.
- **Python-Telegram-Bot** (`>=22.7`): Framework asíncrono para la conexión con la API de Telegram.

## Servicios Externos Requeridos

El proyecto depende de los siguientes servicios externos y bases de datos para su correcto funcionamiento:

1. **PostgreSQL**: 
   - Base de datos relacional principal.
   - Conexión gestionada mediante el driver asíncrono `asyncpg`.
2. **Redis**:
   - Almacenamiento clave-valor utilizado principalmente por el `openai-agents[redis]` para la gestión de memoria/sesión del agente y cachés temporales.
3. **OpenAI API**:
   - Proveedor del LLM y capacidades inteligentes del agente.
4. **Telegram Bot API**:
   - Interfaz con el usuario final a través de la aplicación de mensajería Telegram.

## Containerización

La aplicación está completamente dockerizada, facilitando un entorno reproducible entre desarrollo y producción.

### Detalles del `Dockerfile`
- **Imagen Base**: `python:3.12-slim` para mantener la imagen liviana mientras conserva las funcionalidades necesarias.
- **Dependencias del Sistema**: Instala `gcc` para permitir la compilación de paquetes de Python (como drivers de bases de datos o extensiones C), limpiando posteriormente el caché de `apt` para optimizar el tamaño.
- **Gestión de Paquetes**: Las dependencias se instalan a través de `pip` leyendo directamente desde `pyproject.toml`.
- **Estrategia de Caché**: Se copian y procesan las dependencias en una capa independiente (sin el código fuente completo) antes de hacer `COPY . .`. Esto mejora dramáticamente los tiempos de compilación posteriores si el código cambia pero las dependencias no.
- **Puerto Expuesto**: `8000`.

## Despliegue

La plataforma de despliegue configurada es **Railway**, como se evidencia en el archivo `railway.toml`.

### Configuración en Railway
- **Builder**: Se especifica explicitamente que se use el `Dockerfile` (`builder = "DOCKERFILE"`).
- **Comando de Inicio**: Se sobrescribe el comando de Docker con la integración de la variable dinámica `$PORT` provista por Railway:
  `uvicorn src.main:app --host 0.0.0.0 --port $PORT`
- **Healthcheck**: Configurado en la ruta `/health`. Railway utiliza este endpoint para verificar si la aplicación está lista para recibir tráfico.
- **Políticas de Reinicio**: `ON_FAILURE`, indicando que el servicio se debe reiniciar automáticamente ante un cierre inesperado o falla crítica.

## Variables de Entorno

La configuración de la aplicación está gestionada por `pydantic-settings`. Para poder ejecutar el proyecto, se requiere definir las siguientes variables en un archivo `.env` en la raíz (para desarrollo local) o configurarlas directamente en el entorno de despliegue (ej: en las variables de Railway):

- `TELEGRAM_TOKEN`: Token proporcionado por el BotFather de Telegram.
- `DATABASE_URL`: Cadena de conexión asíncrona a PostgreSQL (ej: `postgresql+asyncpg://user:pass@host:port/dbname`).
- `REDIS_URL`: Cadena de conexión a Redis (ej: `redis://user:pass@host:port`).
- `OPENAI_API_KEY`: Clave de API de OpenAI para habilitar el agente LLM.
- `WEBHOOK_BASE_URL`: URL pública (HTTPS) del proyecto desplegado. Es obligatoria para configurar el Webhook de Telegram (ej: `https://tu-proyecto.up.railway.app`).

## Flujo de Trabajo (Workflow)

El ciclo de vida de un mensaje dentro de la infraestructura de **EntrenadorAX** opera de forma completamente asíncrona. El siguiente diagrama de secuencia ilustra cómo interactúan los distintos componentes de la arquitectura cuando un usuario envía un mensaje:

```mermaid
sequenceDiagram
    participant U as Usuario
    participant T as Telegram API
    participant F as FastAPI (Webhook)
    participant R as Redis (Memoria)
    participant A as OpenAI Agent
    participant P as PostgreSQL (Datos)

    U->>T: Envía mensaje (ej: "Anotar entreno")
    T->>F: HTTP POST al Webhook (/webhook)
    F->>R: Verifica Rate Limit e inicia/recupera sesión
    F->>A: Envía Prompt + Perfil del usuario
    A-->>A: Evalúa intención (LLM)
    opt Requiere persistencia/consulta
        A->>F: Invocación de Tool (ej: registrar_entreno)
        F->>P: Operación DB (SQLAlchemy asíncrono)
        P-->>F: Confirma guardado o devuelve datos
        F-->>A: Retorna el resultado de la Tool
    end
    A-->>F: Genera respuesta final de texto
    F->>R: Actualiza y guarda estado de la sesión
    F->>T: HTTP POST (sendMessage)
    T->>U: Muestra respuesta al usuario
```

### Descripción Detallada de los Pasos:

1. **Recepción (Telegram -> FastAPI)**: El usuario escribe en la aplicación de Telegram. Los servidores de Telegram realizan un POST HTTP al endpoint configurado como Webhook en nuestra aplicación (servida por FastAPI/Uvicorn).
2. **Contexto (Redis)**: `python-telegram-bot` toma la petición. Antes de procesarla, se verifica el rate limit en Redis para prevenir spam. Luego se levanta o inicializa la sesión conversacional específica del usuario almacenada en Redis (`RedisSession`).
3. **Agente Inteligente (OpenAI Agent)**: Se construye un prompt que inyecta en el contexto el perfil actual del usuario y su estado. Este prompt se envía de forma asíncrona a la API de OpenAI.
4. **Ejecución de Herramientas (PostgreSQL)**: Si el agente LLM determina que necesita guardar un dato (ej: registrar comida, sueño) o buscar información del usuario (ej: progreso semanal), realiza una llamada a función (Tool Call). Nuestra aplicación ejecuta esa herramienta en el backend, la cual se comunica con la base de datos PostgreSQL mediante `asyncpg` y el ORM de SQLAlchemy.
5. **Retorno de Respuesta (FastAPI -> Telegram)**: Finalmente, el agente toma los resultados de la DB y compone un mensaje en lenguaje natural. FastAPI actualiza la memoria en Redis y envía un POST asíncrono a la API de Telegram con la respuesta, la cual es entregada inmediatamente al usuario.
