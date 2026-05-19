# PRICING_STRATEGY.md - Estrategia de pricing EntrenadorAX V2

## Tabla de contenidos

1. [Planes](#1-planes)
2. [Features por tier](#2-features-por-tier)
3. [Pago por comprobante](#3-pago-por-comprobante)
4. [Promociones de launch](#4-promociones-de-launch)
5. [Unit economics](#5-unit-economics)
6. [Escenarios target post-launch](#6-escenarios-target-post-launch)
7. [KPIs a monitorear](#7-kpis-a-monitorear)
8. [Cómo cambiar precios](#8-cómo-cambiar-precios)
9. [Refunds](#9-refunds)

## 1. Planes

| Plan | Mensual COP | USD aprox | Anual COP (20% off) | Posición |
|---|---|---|---|---|
| Free | 0 | 0 | 0 | Hook de entrada |
| **Starter** | **5.000** | 1.20 | 48.000 | Anti-fricción |
| Pro | 14.990 | 3.50 | 144.000 | Plan flagship |
| Elite | 39.990 | 9.50 | 384.000 | Power users + voz ilimitada |
| Lifetime | 399.000 único | 95 | n/a | FOMO launch |

> Se puede ajustar con env vars: `PRECIO_STARTER_COP`, `PRECIO_PRO_COP`, `PRECIO_ELITE_COP`, `PRECIO_LIFETIME_COP`.

## 2. Features por tier (`plan_definicion.features` JSONB)

| Feature | Free | Starter | Pro | Elite | Lifetime |
|---|---|---|---|---|---|
| `realtime_min_mes` | 0 | 5 | 30 | 120 | 120 |
| `fotos_dia` | 3 | -1 | -1 | -1 | -1 |
| `wearables_max` | 0 | 1 | 1 | -1 | -1 |
| `voz_tts` | false | false | true | true | true |
| `plan_generator` | false | false | true | true | true |
| `pdf_mensual` | false | true | true | true | true |
| `pdf_ilimitado` | false | false | false | true | true |
| `charts_avanzados` | false | true | true | true | true |
| `miniapp` | true | true | true | true | true |
| `export_csv_dias` | 30 | 90 | -1 | -1 | -1 |
| `stickers_exclusivos` | false | false | true | true | true |
| `beta_features` | false | false | false | true | true |
| `priority_support` | false | false | false | true | true |
| `kudos_x3` | false | false | false | true | true |

> `-1` = ilimitado.

## 3. Pago por comprobante

No usamos pasarela ni Stars. El flujo es:

1. Usuario elige plan y duración (`Mensual` / `Anual` / `Lifetime`) en `/pagar`.
2. Bot muestra cuenta destino: Bre-B + Bancolombia alternativa.
3. Usuario transfiere y sube foto del comprobante.
4. Vision API extrae monto, fecha, hora, referencia y cuentas.
5. Detectamos duplicados con SHA-256 y similaridad.
6. Si monto coincide (+/- 500 COP), se activa provisionalmente.
7. Admin valida humanamente en <24h.
8. Bot notifica al usuario vía Redis pubsub.

### Ventajas

- 0% comisión pasarela.
- 0% comisión Apple/Google.
- Pago directo, sensación P2P.
- Compatible con métodos CO (Bre-B, Nequi, Daviplata, Bancolombia).

### Riesgos

- Mayor fricción por subir comprobante.
- Riesgo de fraude, mitigado con validación humana y bloqueo.

## 4. Promociones de launch

- **Lifetime 199.000 COP** (50% off) para los primeros 50 cupos.
- **Referral**: 30 días Pro gratis para el invitador cuando el invitado paga su primer mes.
- **Anual**: 20% descuento (~2 meses gratis).
- **Estudiantes `.edu.co`**: 50% off permanente en Starter/Pro (verificar email).

## 5. Unit economics

| Tier | Precio USD | Costo marginal USD/mes | Margen | Break-even N |
|---|---|---|---|---|
| Free | 0 | 0.30 | -0.30 | n/a |
| Starter | 1.20 | 0.40 | 0.80 (67%) | 750 |
| Pro | 3.57 | 1.50 | 2.07 (58%) | 290 |
| Elite | 9.52 | 4.00 | 5.52 (58%) | 110 |
| Lifetime | 95 | 5/mes amortizado | recovery en 17 meses | n/a |

## 6. Escenarios target post-launch

### Mes 3 (conservador)

- 200 Free
- 30 Starter
- 8 Pro
- 1 Elite
- 10 Lifetime
- MRR estimado: **310K COP** (~$74 USD)

### Mes 6 (operativo)

- 1000 Free
- 200 Starter
- 70 Pro
- 15 Elite
- 30 Lifetime
- MRR estimado: **2.65M COP** (~$630 USD)

## 7. KPIs a monitorear

- Free → Starter: target > 8%
- Starter → Pro: target > 25%
- Churn mensual Pro: < 8%
- ARPU blended: > $3 USD
- Uso Realtime en Pro: > 60%
- Cupos Lifetime: 100/100 en 90 días

## 8. Cómo cambiar precios

1. Actualiza env vars en Railway.
2. Si cambias features, edita `plan_definicion.features` en DB o admin web `/operaciones`.
3. La cache de features en Redis se refresca cada 5 minutos.

## 9. Refunds

- 100% si < 72h tras aprobación admin.
- Prorrateado por día restante después de 72h.
- Lifetime: 30 días money-back.
- El admin marca refund en `/admin/pagos/<id>` con motivo `refund`.
EOF