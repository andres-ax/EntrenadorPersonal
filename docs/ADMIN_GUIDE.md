# ADMIN_GUIDE.md - Guía del administrador

Guía rápida para operar el panel admin de EntrenadorAX.

- URL de acceso: `https://entrenadorax.axsoftware.codes/admin/login`
- Arquitectura: server-rendered con Jinja2 + HTMX, servido desde el mismo proceso FastAPI que el bot.
- Autenticación: cookie HttpOnly `admin_jwt`.

## Tabla de contenidos

1. [Login](#login)
2. [Flujo diario recomendado](#flujo-diario-recomendado)
3. [Validar pagos por comprobante](#validar-pagos-por-comprobante)
4. [Fraude y banderas rojas](#fraude-y-banderas-rojas)
5. [Asignar planes manualmente](#asignar-planes-manualmente)
6. [Bloquear / desbloquear usuarios](#bloquear--desbloquear-usuarios)
7. [Crisis log](#crisis-log)
8. [Broadcasts](#broadcasts)
9. [Crear nuevos admins](#crear-nuevos-admins)
10. [Finanzas](#finanzas)
11. [Investigar un usuario](#investigar-un-usuario)
12. [Soporte técnico al usuario](#soporte-técnico-al-usuario)
13. [Casos éticos delicados](#casos-éticos-delicados)

---

## Login

- Accede con email y contraseña de un admin.
- El admin puede crearse con `scripts/crear_admin.py` o crear desde el panel si tienes rol `super`.

## Flujo diario recomendado

1. **Dashboard** (`/`) — revisa KPIs del día: DAU, MAU, pagos pendientes, crisis.
2. **Pagos** (`/pagos?estado=pendiente_humano`) — valida comprobantes.
3. **Crisis** (`/crisis`) — revisa alertas de riesgo y toma decisiones.

## Validar pagos por comprobante

1. Filtra `/pagos` por `pendiente_humano`.
2. Pulsa **Revisar** en cada pago.
3. Comprueba:
   - Foto del comprobante (renderizada vía proxy API).
   - Monto detectado vs monto esperado.
   - Referencia, cuenta origen y fecha.
   - Datos extraídos por Vision (payload completo disponible).
4. Decisión:
   - **Aprobar**: monto coincide y comprobante válido.
   - **Rechazar**: fraude, duplicado o monto incorrecto.
     - Opcional: bloquear al usuario.
5. El bot notifica automáticamente al usuario vía Redis pubsub.

## Fraude y banderas rojas

- Mismo comprobante (sha256) repetido en usuarios distintos.
- Monto muy diferente al esperado (>500 COP de gap).
- Imagen editada o de mala calidad.
- Múltiples comprobantes en pocos minutos del mismo usuario.
- Cuenta origen diferente a nombres habituales.

## Asignar planes manualmente

- Ruta: `/usuarios/<uid>`.
- Selecciona plan, asigna días y confirma.

Casos válidos:
- Cliente VIP o beta tester.
- Reembolso aprobado pero plan expirado.
- Compensar con días gratis por soporte.

## Bloquear / desbloquear usuarios

- Ruta: `/usuarios/<uid>`.
- El bloqueo fuerza `plan_actual = FREE` y detiene futuros pagos.
- No borra datos.
- Para borrado total usa GDPR delete o `DELETE /admin/usuarios/<uid>`.

## Crisis log

- Ruta: `/crisis`.
- Muestra eventos de detección de riesgo.

### Recomendaciones por nivel

- **Nivel 1**: contacta al usuario fuera del bot y ofrece pausa si es necesario.
- **Nivel 2**: monitoreo pasivo; escalar a humano si se repite.
- **Nivel 3**: vigila; normalmente se resuelve solo.

## Broadcasts

Desde `/operaciones` puedes enviar mensajes masivos.

- Filtra por plan mínimo, país o segmento.
- Mensajes HTML simples (sin imágenes).
- Usa `silent=True`.
- Límites Telegram: 30 msg/segundo.
- Para 500+ usuarios, usa la API estándar (~17 s).

## Crear nuevos admins

- Solo `super` puede crear admins.
- Ruta: `/admins`.

Roles:
- **super**: acceso total, puede crear admins y eliminar usuarios.
- **soporte**: validar pagos, pausar usuarios, asignar planes y ver crisis. No puede crear admins ni borrar usuarios.

## Finanzas

En `/finanzas` revisa:
- MRR estimado (30 días) por método de pago.
- Conversiones recientes.
- Pagos pendientes acumulados.
- Usuarios por plan: free, starter, pro, elite, lifetime.

## Investigar un usuario

En `/usuarios/<uid>` consulta:
- Perfil completo: plan, expiración, país, tono.
- Historial de suscripciones.
- Historial de pagos.
- Eventos del bot (timeline último mes).
- Crisis asociadas.
- Estado de bloqueo.

## Soporte técnico al usuario

1. Pide el Telegram ID (puede obtenerlo con @userinfobot).
2. Busca en `/usuarios?q=<id>`.
3. Revisa eventos y pagos.
4. Acciones típicas:
   - Plan no activado: revisar pago en `/pagos`.
   - Bot no responde: pausar y reactivar.
   - Comprobante rechazado por error: reabrir y asignar plan.

## Casos éticos delicados

- **Usuario en crisis**: no uses el panel para conversar con él. Contacta fuera del bot y sugiere ayuda profesional.
- **Datos sensibles**: no copies/pegues mensajes del usuario fuera del panel.
- **GDPR delete**: si pide borrar todo, usa `/borrar_datos` desde su sesión o `DELETE /admin/usuarios/<uid>`. Es irreversible.
EOF