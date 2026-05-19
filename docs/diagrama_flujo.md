# Diagrama de flujo - EntrenadorAX

A continuación hay un diagrama de flujo en Mermaid que describe el flujo principal del sistema.

```mermaid
flowchart LR
  subgraph Clientes
    U_TG[Usuario (Telegram)]
    U_WEB[Usuario (Web / Browser)]
  end

  subgraph Backend
    API[FastAPI (src/main.py)]
    TB[Bot Telegram / Handlers (src/telegram/)]
    AG[OpenAI Agent (src/coach.py)]
    TO[Herramientas (src/tools.py)]
    WS[WebSocket Realtime (src/realtime/)]
  end

  subgraph Servicios
    PG[(Postgres DB)]
    RD[(Redis)]
    OAI[(OpenAI API / Realtime)]
  end

  U_TG -->|mensajes| TB
  U_WEB -->|HTTP / WebSocket| API

  TB -->|llama handlers| AG
  API -->|llama rutas / handlers| AG

  AG -->|usa herramientas| TO
  TO --> PG
  TO --> RD

  AG -->|consulta/ejecuta| OAI

  AG -->|respuesta| TB
  TB -->|envía mensaje| U_TG

  API -->|abre WS| WS
  WS -->|audio/stream| OAI

  PG -.->|almacena| API
  RD -.->|cache / pubsub| TB

  classDef infra fill:#f9f,stroke:#333,stroke-width:1px;
  class PG,RD,OAI infra;
```

Leyenda:
- `Usuario (Telegram)` y `Usuario (Web)` muestran los puntos de entrada.
- `Bot Telegram` maneja el polling/webhook y enruta a los handlers.
- `OpenAI Agent` es el agente de coaching que decide acciones y llama a `src/tools.py`.
- `Herramientas` leen/escriben en `Postgres` y `Redis`.
- `WebSocket Realtime` se usa para llamadas de voz que pueden pasar audio a OpenAI Realtime.

Si quieres, puedo:
- renderizarlo y exportarlo a PNG/SVG;
- insertar el diagrama en `README.md`;
- ajustar el diagrama con más detalle (secuencias internas, scheduler, jobs, etc.).
