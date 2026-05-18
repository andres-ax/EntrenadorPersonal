# PRICING_STRATEGY.md - Estrategia de pricing EntrenadorAX V2

## Tiers (vigentes desde launch)

| Plan | Mensual COP | USD aprox | Anual COP (20% off) | Posicion |
|---|---|---|---|---|
| Free | 0 | 0 | 0 | Hook de entrada |
| **Starter** | **5.000** | 1.20 | 48.000 | Anti-friccion, mata el "no pago" |
| Pro | 14.990 | 3.50 | 144.000 | Plan flagship (mas margen) |
| Elite | 39.990 | 9.50 | 384.000 | Power users + voz ilimitada |
| Lifetime | 399.000 unico | 95 | n/a | FOMO launch (100 cupos) |

Override via env vars: `PRECIO_STARTER_COP`, `PRECIO_PRO_COP`, etc.

## Features por tier (`plan_definicion.features` JSONB)

| Feature | Free | Starter | Pro | Elite | Lifetime |
|---|---|---|---|---|---|
| `realtime_min_mes` | 0 | 5 | 30 | 120 | 120 |
| `fotos_dia` | 3 | -1 (inf) | -1 | -1 | -1 |
| `wearables_max` | 0 | 1 | 1 | -1 | -1 |
| `voz_tts` (escalation) | false | false | true | true | true |
| `plan_generator` (LLM) | false | false | true | true | true |
| `pdf_mensual` | false | true (1/mes) | true | true | true |
| `pdf_ilimitado` | false | false | false | true | true |
| `charts_avanzados` | false | true | true | true | true |
| `miniapp` | true | true | true | true | true |
| `export_csv_dias` | 30 | 90 | -1 | -1 | -1 |
| `stickers_exclusivos` | false | false | true | true | true |
| `beta_features` | false | false | false | true | true |
| `priority_support` | false | false | false | true | true |
| `kudos_x3` (comunidad) | false | false | false | true | true |

`-1` = ilimitado.

## Pago por comprobante (innovacion clave)

NO usamos pasarela. NO usamos Stars. Flow:

1. Usuario en `/pagar` elige plan + duracion (Mensual / Anual / Lifetime).
2. Bot muestra cuenta destino (Bre-B + Bancolombia alternativa).
3. Usuario transfiere y manda foto del comprobante.
4. Vision API extrae monto, fecha, hora, referencia, cuentas.
5. SHA-256 + similaridad detectan duplicados (mismo monto + fecha + ref).
6. Si monto coincide (+/- 500 COP), **activacion provisional inmediata**.
7. Admin valida humanamente en `<24h`. Aprueba o rechaza.
8. Bot notifica al usuario via Redis pubsub.

Ventajas:
- 0% comision pasarela (vs 3-5% EBANX/Wompi).
- 0% comision Apple/Google (vs ~30% Stars en app).
- Cliente paga "directo" -> sensacion P2P (no enterprise).
- Compatible con cualquier metodo CO (Bre-B, Nequi, Daviplata, Bancolombia).

Riesgos:
- Friccion alta (debe subir foto). Tradeoff acceptable para nuestra demo.
- Posible fraude (mitigado por validacion humana + bloqueo).

## Promociones de launch (primeros 90 dias)

- **Lifetime $199.000** (50% off) - solo primeros 50 cupos.
- **Referral**: 30 dias Pro gratis al invitador cuando el invitado paga su primer mes.
- **Anual con 20% descuento** (~2 meses gratis).
- **Estudiantes .edu.co**: 50% off permanente en Starter/Pro (verificar email).

## Unit economics (tasa 4.200 COP/USD)

| Tier | Precio USD | Costo marginal USD/mes | Margen | Break-even N |
|---|---|---|---|---|
| Free | 0 | 0.30 | -0.30 | n/a (perdida controlada) |
| Starter $5K | 1.20 | 0.40 | 0.80 (67%) | 750 cubren $600/mes infra |
| Pro $14.990 | 3.57 | 1.50 | 2.07 (58%) | 290 cubren $600 infra |
| Elite $39.990 | 9.52 | 4.00 | 5.52 (58%) | 110 cubren $600 infra |
| Lifetime $399K (unico) | 95 | 5/mes amortizado | recovery en 17 meses | n/a |

## Escenarios target post-launch

**Mes 3** (conservador):
- 200 Free
- 30 Starter (15%)
- 8 Pro (4%)
- 1 Elite
- 10 Lifetime
- MRR: 150K + 120K + 40K + 0 = **310K COP** (~$74 USD)
- Cubre infra basica.

**Mes 6** (target operativo):
- 1000 Free
- 200 Starter
- 70 Pro
- 15 Elite
- 30 Lifetime
- MRR: 1M + 1.05M + 600K = **2.65M COP** (~$630 USD)
- Cubre infra + Realtime + sueldos parciales.

## KPIs a monitorear

- Conversion Free -> Starter: target >8%
- Conversion Starter -> Pro: target >25%
- Churn mensual Pro: target <8%
- ARPU blended: target >$3 USD
- Realtime usage en Pro: target >60% (stickiness)
- Cupos Lifetime: target 100/100 en 90 dias (FOMO)

## Como cambiar precios

1. Update env vars en Railway (sin redeploy).
2. Si quieres cambiar features de un tier, edita `plan_definicion.features`
   en DB (admin web `/operaciones`) o directo SQL.
3. Cache de features en Redis se refresca cada 5 min.

## Refunds

Solicitar via `entrenadorax@axsoftware.codes` o WhatsApp +57 304 409 3197. Politica:
- 100% si <72h post-aprobacion del admin.
- Pro-rateado por dia restante despues de 72h.
- Lifetime: 30 dias money-back. Despues no.
- Admin marca refund en `/admin/pagos/<id>` -> "rechazar" con motivo "refund".
