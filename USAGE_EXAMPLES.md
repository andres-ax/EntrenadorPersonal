# Ejemplos de uso de EntrenadorAX

Este archivo documenta ejemplos completos del uso de la aplicación, tanto en instalación como en interacción con el bot y despliegue.

## Flujo de uso principal

```mermaid
flowchart TD
    A[Crear .env y entorno virtual] --> B[Instalar dependencias]
    B --> C[Ejecutar run_bot.py o uvicorn]
    C --> D[Telegram recibe mensaje / comandos]
    D --> E[Handler transforma mensaje]
    E --> F[Agente procesa prompt con perfil]
    F --> G[Herramientas registran datos / consultan DB]
    G --> H[Respuesta enviada al usuario]
```

---

## 1. Configuración del entorno

### 1.1. Crear el entorno virtual

```bash
cd /home/jhonpuli/Documentos/AndresZuliaga/EntrenadorPersonal
python3 -m venv .venv
source .venv/bin/activate
```

### 1.2. Instalar dependencias

```bash
python3 -m pip install --upgrade pip
python3 -m pip install -e .
```

### 1.3. Archivo de variables de entorno (`.env`)

Ejemplo completo de `.env`:

```env
TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpQRs_tUvWXyZ
DATABASE_URL=postgresql+asyncpg://usuario:password@localhost:5432/entrenadorax
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
WEBHOOK_BASE_URL=https://mi-dominio.com
```

Explicación:
- `TELEGRAM_TOKEN`: token del bot de Telegram.
- `DATABASE_URL`: conexión PostgreSQL para guardar perfil, entrenos, comidas, sueño y métricas.
- `REDIS_URL`: URL de Redis para memoria de conversaciones y rate limit.
- `OPENAI_API_KEY`: clave de OpenAI para el agente.
- `WEBHOOK_BASE_URL`: dirección pública donde se expondrá el webhook si usas FastAPI.

---

## 2. Ejecutar la aplicación

### 2.1. Modo local (polling)

Esta es la forma más sencilla de arrancar el bot durante desarrollo:

```bash
python3 run_bot.py
```

Qué hace:
- carga `.env`
- inicializa la base de datos
- crea el bot de Telegram
- comienza a recibir mensajes en modo polling
- registra jobs de recordatorios automáticos


### 2.2. Modo webhook (FastAPI)

Para ejecutar la app como servicio HTTP:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

Endpoints disponibles:
- `GET /health` — verifica que la aplicación está viva.
- `GET /webhook-info` — devuelve la URL y el secret que debes usar en Telegram.
- `POST /webhook` — recibe actualizaciones de Telegram.

Ejemplo para configurar webhook desde Telegram:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=https://mi-dominio.com/webhook&secret_token=EL_SECRET_DEL_ENDPOINT"
```

El secret se obtiene desde `GET /webhook-info`.

---

## 3. Comandos de Telegram y botones

### 3.1. Comandos válidos

- `/start` — inicia la conversación y onboarding.
- `/menu` — muestra botones rápidos.
- `/reset` — reinicia la sesión de Redis del usuario.
- `/borrar_datos` — elimina todos los datos del usuario.

### 3.2. Botones del menú

- `Registrar entreno`
- `Registrar comida`
- `Como dormí`
- `Mi peso actual`
- `Reporte semanal`
- `Historial de peso`

---

## 4. Ejemplos de conversación y flujo

### 4.1. Onboarding inicial

El primer paso es completar el perfil si `onboarding_completo` es `no`.

Ejemplo:

- Usuario: `Hola`
- Bot: `¡Hola! Soy tu coach. ¿Cuál es tu nombre?` (puede preguntar nombre + edad + peso en varios mensajes)
- Usuario: `Me llamo Diego`
- Bot: `Perfecto, ¿cuántos años tienes?`
- Usuario: `28`
- Bot: `¿Cuánto pesas actualmente en kg?`
- Usuario: `78`
- Bot: `¿Cuál es tu altura en cm?`
- Usuario: `176`
- Bot: `¿Cuál es tu objetivo?` (ganar músculo / perder grasa / mantenerse / mejorar rendimiento)
- Usuario: `Ganar músculo`
- Bot: `¿Cuál es tu nivel?` (principiante / intermedio / avanzado)
- Usuario: `Intermedio`
- Bot: `¿Cuántos días por semana puedes entrenar?`
- Usuario: `4`
- Bot: `¿Cuál es tu deporte principal?` (gimnasio / crossfit / running / futbol / calistenia / natación)
- Usuario: `Gimnasio`

Después de esto, el bot guarda el perfil con `guardar_perfil` y marca el onboarding como completo.

### 4.2. Registrar un entrenamiento

Ejemplo de mensaje natural:

- Usuario: `Hoy hice piernas: sentadillas 4x8 con 80kg, peso muerto 3x6, curl femoral 3x12.`

Qué sucede:
- el bot extrae el tipo de entrenamiento.
- el bot usa `registrar_entreno` con `tipo=fuerza`.
- guarda ejercicios, series, repeticiones y pesos.

Ejemplo de datos registrados internamente:

```json
{
  "fecha": "2026-05-15",
  "tipo": "fuerza",
  "duracion_min": 60,
  "ejercicios": [
    {"nombre": "sentadilla", "series": 4, "reps": 8, "peso_kg": 80},
    {"nombre": "peso muerto", "series": 3, "reps": 6, "peso_kg": 100},
    {"nombre": "curl femoral", "series": 3, "reps": 12}
  ]
}
```

### 4.3. Registrar una comida

Ejemplo natural:

- Usuario: `Comí ensalada, pollo y arroz, unas 700 calorías.`

Qué sucede:
- el bot detecta tipo de comida.
- usa `registrar_comida` con `tipo=almuerzo` o `tipo=cena` según contexto.
- guarda alimentos y calorías.

Datos internos:

```json
{
  "fecha": "2026-05-15",
  "tipo": "almuerzo",
  "alimentos": ["ensalada", "pollo", "arroz"],
  "calorias": 700
}
```

### 4.4. Registrar sueño

Ejemplo natural:

- Usuario: `Dormí 7.5 horas y la calidad fue 4 de 5.`

Qué sucede:
- el bot usa `registrar_sueno`.
- guarda horas y calidad.

Datos internos:

```json
{
  "fecha": "2026-05-15",
  "horas": 7.5,
  "calidad": 4,
  "notas": ""
}
```

### 4.5. Registrar peso

Ejemplo natural:

- Usuario: `Peso 82.1` o `Mi peso actual es 83 kg.`

Qué sucede:
- el bot usa `registrar_peso`.
- guarda un registro histórico de peso.

Datos internos:

```json
{
  "peso_kg": 82.1,
  "fecha": "2026-05-15"
}
```

### 4.6. Preguntar progreso y reportes

Ejemplo:

- Usuario: `¿Cómo voy esta semana?`
- Usuario: `Dame mi reporte semanal.`
- Usuario: `Muestra mi historial de peso.`

Qué hace el bot:
- llama a `reporte_progreso`.
- devuelve días entrenados, volumen de entrenamiento, nuevos PRs y resumen de sueño.
- para historial de peso, usa `consultar_historial_peso`.

### 4.7. Usar el menú

En cualquier momento, el usuario puede escribir `/menu` y seleccionar botones:

- `Registrar entreno` → envía un texto que el bot interpreta como registro de entrenamiento.
- `Registrar comida` → inicia el flujo de registro de nutrición.
- `Como dormí` → inicia el registro de sueño.
- `Mi peso actual` → inicia el registro de peso.
- `Reporte semanal` → genera el resumen de la semana.
- `Historial de peso` → devuelve la historia de peso.

### 4.8. Reiniciar sesión y borrar datos

- `/reset` — elimina la sesión conversacional de Redis, pero conserva el perfil y datos.
- `/borrar_datos` — borra todo el perfil, entrenos, comidas, sueño, PRs y datos del usuario.

---

## 5. Ejemplos de datos y herramientas internas

### 5.1. Herramientas (`tools.py`)

El agente puede usar estas funciones:

- `obtener_perfil` — obtiene perfil completo del usuario.
- `guardar_perfil` — actualiza datos de usuario.
- `registrar_entreno` — guarda una sesión de entrenamiento.
- `obtener_pr` — consulta un PR de ejercicio.
- `guardar_pr` — guarda un nuevo PR.
- `listar_todos_prs` — lista todos los PRs.
- `registrar_comida` — guarda comida.
- `resumen_nutricional` — obtiene totales del día.
- `registrar_sueno` — guarda el registro de sueño.
- `reporte_progreso` — genera el reporte semanal.
- `registrar_peso` — guarda el peso actual.
- `consultar_historial_peso` — devuelve historial de peso.

### 5.2. Mensajes del bot y reglas de conversación

El agente está diseñado para:
- hacer onboarding conversacional si faltan datos.
- ser proactivo en registrar entrenos, comidas y sueño.
- proponer entrenamiento según objetivo y nivel.
- responder corto, directo y motivacional.
- usar datos concretos del perfil cuando están disponibles.
- no pedir el Telegram ID al usuario.

Ejemplo de respuestas esperadas:
- `Perfecto, entonces vamos a entrenar 3 veces por semana con una rutina de fuerza enfocada en piernas y pecho.`
- `Genial, registré tu comida de hoy: pollo, arroz, ensalada. Sigue así.`
- `Buen trabajo! Bajaste 1.5 kg en las últimas dos semanas.`

---

## 6. Ejemplos de despliegue

### 6.1. Ejecutar con Docker

```bash
docker build -t entrenadorax .
docker run -d -p 8000:8000 \
  -e TELEGRAM_TOKEN="123..." \
  -e DATABASE_URL="postgresql+asyncpg://..." \
  -e REDIS_URL="redis://..." \
  -e OPENAI_API_KEY="sk-..." \
  -e WEBHOOK_BASE_URL="https://mi-dominio.com" \
  entrenadorax
```

### 6.2. Configurar webhook tras dockerizar

1. Arranca la app en el contenedor.
2. Busca el secret en `GET /webhook-info`.
3. Ejecuta:

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_TOKEN}/setWebhook?url=https://mi-dominio.com/webhook&secret_token=EL_SECRET_DEL_ENDPOINT"
```

---

## 7. Ejemplos de errores comunes y soluciones

### 7.1. No puede importar `dotenv`

Significa que falta `python-dotenv`. Dentro del entorno virtual, instala:

```bash
python3 -m pip install python-dotenv
```

### 7.2. Error `externally-managed-environment`

Debes usar un entorno virtual o instalar paquetes del sistema con `apt`. La opción recomendada es:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
```

### 7.3. `python3 -m venv .venv` falla por `ensurepip`

Instala el paquete de venv:

```bash
sudo apt install python3.13-venv
```

### 7.4. Redis o PostgreSQL no configurados

Esta aplicación necesita ambos servicios:
- Redis (`REDIS_URL`) para memoria y rate limit.
- PostgreSQL (`DATABASE_URL`) para datos de usuario.

---

## 8. Resumen de interacción completa

1. Iniciar `run_bot.py`.
2. En Telegram, escribe `/start`.
3. El bot hace preguntas de onboarding.
4. Responde con datos: nombre, edad, peso, altura, objetivo, nivel, días por semana.
5. El bot aprende tu perfil y comienza a proponer acciones.
6. Usar `/menu` para ver opciones rápidas.
7. Registrar entrenos, comidas, sueño y peso en conversaciones naturales.
8. Consultar progreso con mensajes como `¿Cómo voy esta semana?`.
9. Usar `/reset` si quieres reiniciar la conversación.
10. Usar `/borrar_datos` para eliminar todo el historial.

---

## 9. Qué se guarda en la base de datos

Tablas principales:
- `usuarios`
- `sesiones_entrenamiento`
- `ejercicios_realizados`
- `comidas`
- `personal_records`
- `metricas_sueno`
- `metricas_corporales`

Cada mensaje del bot puede terminar en una llamada a las funciones del repositorio, lo que convierte la conversación en datos estructurados.

---

## 10. Consejos para profundizar

- Revisa `src/coax.py` y `src/tools.py` para entender cómo el agente usa el perfil y llama a las herramientas.
- Revisa `src/telegram/handlers.py` para ver cómo se transforma cada mensaje de Telegram en una pregunta para el agente.
- Revisa `src/telegram/scheduler.py` para ver qué recordatorios se envían y cuándo.
- Revisa `src/db/repository.py` para ver el modelo de datos y cómo se guardan los registros.
