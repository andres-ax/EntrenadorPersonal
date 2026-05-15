# Instalación y ejecución de EntrenadorAX

## Flujo de instalación

```mermaid
graph TD
    A["Instalar dependencias del sistema"] --> B["Crear entorno virtual"]
    B --> C["Activar entorno virtual"]
    C --> D["Actualizar pip"]
    D --> E["Instalar proyecto con pip"]
    E --> F["Crear archivo .env"]
    F --> G["Ejecutar bot con python3 run_bot.py"]
    G --> H["Detener con Ctrl+C"]
    H --> I["Salir con deactivate"]
```

## Requisitos previos
- Python 3.11 o superior
- `python3-pip` instalado en el sistema
- `python3.13-venv` (o el paquete de `venv` correspondiente a tu versión de Python)

## Pasos de instalación
1. Abre una terminal en la raíz del proyecto:
   ```bash
   cd /home/jhonpuli/Documentos/AndresZuliaga/EntrenadorPersonal
   ```

2. Crea un entorno virtual:
   ```bash
   python3 -m venv .venv
   ```

3. Activa el entorno virtual:
   ```bash
   source .venv/bin/activate
   ```

4. Actualiza `pip` dentro del entorno virtual:
   ```bash
   python3 -m pip install --upgrade pip
   ```

5. Instala el proyecto y sus dependencias:
   ```bash
   python3 -m pip install -e .
   ```

## Configuración de variables de entorno
Crea un archivo `.env` en la raíz del proyecto con al menos estas variables:

```env
TELEGRAM_TOKEN=tu_token_de_telegram
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/dbname
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=tu_api_key_openai
WEBHOOK_BASE_URL=https://tu-dominio.com
```

## Ejecutar el bot en modo local (polling)
Dentro del entorno virtual activado, ejecuta:

```bash
python3 run_bot.py
```

## Detener el bot
Presiona `Ctrl+C` en la terminal donde se está ejecutando el bot.

## Salir del entorno virtual
Después de detener el bot, ejecuta:

```bash
deactivate
```

## Notas adicionales
- Si no tienes `python3-pip`, instala primero el paquete del sistema:
  ```bash
  sudo apt update
  sudo apt install python3-pip
  ```
- Si `python3 -m venv .venv` falla, instala el paquete de venv:
  ```bash
  sudo apt install python3.13-venv
  ```
