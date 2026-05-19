# Diagrama de flujo - EntrenadorAX

A continuación hay un diagrama de flujo en Mermaid que describe el flujo principal del sistema.

```mermaid
graph LR
  %% Nodos principales (nombres simples para compatibilidad con GitHub)
  U_TG[Usuario-Telegram]
  U_WEB[Usuario-Web]
  API[FastAPI]
  TB[Bot-Telegram]
  AG[OpenAI-Agent]
  TO[Herramientas]
  WS[WebSocket-Realtime]
  PG[(Postgres DB)]
  RD[(Redis)]
  OAI[(OpenAI API)]

  %% Flujo
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

  %% estilos
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
