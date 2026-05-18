# ADMIN_GUIDE.md - Guia del administrador

Como operar el panel admin de EntrenadorAX. URL: `entrenadorpersonal-production.up.railway.app/admin/login`.

El panel es server-rendered con Jinja2 + HTMX (sin SPA). Se sirve desde el
mismo proceso FastAPI que el bot. Auth via cookie HttpOnly `admin_jwt`.

## Login

Email + password de un admin creado via `scripts/crear_admin.py` o creado
desde el panel (rol super requerido).

## Flujo diario recomendado

1. **Dashboard** (`/`) - revisa KPIs del dia (DAU, MAU, pagos pendientes, crisis).
2. **Pagos** (`/pagos?estado=pendiente_humano`) - cola de validaciones.
3. **Crisis** (`/crisis`) - revisa cualquier crisis nivel 1-2 de las ultimas 24h.

## Validar pagos por comprobante

1. Ir a `/pagos` filtrado por `pendiente_humano`.
2. Tap "Revisar" en cada uno.
3. Compara:
   - Foto del comprobante (renderizada via API proxy).
   - Monto detectado vs monto esperado.
   - Referencia, cuenta origen, fecha.
   - Datos extraidos por Vision (full payload disponible).
4. Decision:
   - **Aprobar**: si monto coincide y comprobante valido. Plan activado.
   - **Rechazar**: si fraude, duplicado evidente, monto incorrecto.
     Opcionalmente bloquear al usuario.
5. El bot notifica al usuario automaticamente via Redis pubsub.

## Banderas rojas que indican fraude

- Mismo comprobante (sha256) repetido en distintos usuarios.
- Monto muy diferente al esperado (mas de 500 COP de gap).
- Imagen claramente editada o de baja calidad.
- Multiples comprobantes seguidos en pocos minutos del mismo usuario.
- Cuenta origen muy diferente a los nombres ya vistos.

## Asignar plan manual

`/usuarios/<uid>` -> seleccionar plan + dias -> "Asignar plan".

Casos validos:
- Cliente VIP / beta tester.
- Reembolso aprobado pero plan ya expiro.
- Soporte: usuario reporta problema y compensas con N dias gratis.

## Bloquear/desbloquear usuario

`/usuarios/<uid>` -> motivo -> "Bloquear".

Bloqueo:
- Forza `plan_actual = FREE` (downgrade inmediato).
- Bloquea futuros pagos.
- NO borra datos (usa GDPR delete para eso).

## Crisis log

`/crisis` muestra eventos de deteccion de red flags. Acciones recomendadas:

- **Nivel 1**: contacta al usuario fuera del bot. Confirma que tiene linea
  de crisis activa. Ofrece pausa permanente si lo necesita.
- **Nivel 2**: monitoreo pasivo. Si se repite, escalar a contacto humano.
- **Nivel 3**: vigilar. Generalmente se resuelve solo (sobreentrenamiento).

## Broadcasts

Desde `/operaciones`:
- Filtra por plan minimo y/o pais.
- Mensaje HTML simple (sin imagenes).
- Siempre va con `silent=True`.
- Casos: anuncio de nueva feature, mensaje motivacional masivo, encuesta.

Limites Telegram: 30 msg/seg. Para 500+ usuarios usa la API estandar (~17s).

## Crear nuevos admins

Solo super-admin. Desde `/admins` -> email + password + rol.

Roles:
- **super**: full acceso, puede crear admins y borrar usuarios.
- **soporte**: validar pagos, pausar, asignar planes, ver crisis. No puede
  crear admins ni eliminar usuarios.

## Finanzas

`/finanzas` muestra:
- MRR estimado (30 dias) por metodo de pago.
- Conversiones recientes.
- Pagos pendientes acumulados.
- Usuarios por plan (free/starter/pro/elite/lifetime).

## Investigar un usuario

`/usuarios/<uid>` muestra:
- Perfil completo (tono, plan, expiracion, pais).
- Historial de suscripciones.
- Historial de pagos.
- Eventos del bot (timeline ultimo mes).
- Crisis si las hubo.
- Estado de bloqueo.

## Soporte tecnico al usuario

Si un usuario reporta problema:
1. Pidele su Telegram ID (puede obtenerlo con @userinfobot).
2. Busca en `/usuarios?q=<id>`.
3. Revisa eventos para entender que paso.
4. Acciones tipicas:
   - Plan no activado: revisar pago en `/pagos`.
   - Bot no responde: pausar y reactivar.
   - Comprobante rechazado erroneamente: reaprobar manualmente con asignar_plan.

## Casos eticos delicados

- **Usuario en crisis**: NO usar el panel para conversar con el. Contactalo
  fuera (email, telefono si lo dio). Recomienda terapia profesional.
- **Datos sensibles en eventos**: no copiar/pegar mensajes del usuario fuera
  del panel. Esta info es estrictamente confidencial.
- **GDPR delete**: si un usuario pide borrar todo, ejecutar `/borrar_datos`
  desde su lado o desde admin con `DELETE /admin/usuarios/<uid>`. Es
  irreversible.
