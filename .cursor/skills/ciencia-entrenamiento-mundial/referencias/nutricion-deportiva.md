# Nutricion Deportiva

Base: ISSN Position Stands, Eric Helms (Muscle and Strength Pyramid Vol 2), Layne Norton, Renaissance Periodization, ACSM/ADA Joint Position Stand 2016.

## 1. Energia: TMB y TDEE

### Tasa Metabolica Basal (TMB)

**Mifflin-St Jeor** (preferida segun ADA, error +-10%):

```
Hombre: TMB = (10 * peso_kg) + (6.25 * altura_cm) - (5 * edad) + 5
Mujer:  TMB = (10 * peso_kg) + (6.25 * altura_cm) - (5 * edad) - 161
```

**Katch-McArdle** (mejor si conoces %grasa real):

```
TMB = 370 + (21.6 * masa_magra_kg)
```

### Total Daily Energy Expenditure (TDEE)

```
TDEE = TMB * factor_actividad
```

Factor de actividad (NEAT + EAT + TEF):

| Estilo de vida | Factor |
|---|---|
| Sedentario (oficina, no entrena) | 1.2 |
| Ligero (camina, 1-2 entrenos/sem) | 1.375 |
| Moderado (3-5 entrenos/sem) | 1.55 |
| Alto (6-7 entrenos/sem + trabajo activo) | 1.725 |
| Atleta (2x dia o trabajo fisico pesado) | 1.9 |

## 2. Calorias objetivo

### Mantenimiento

= TDEE. Confirmar empiricamente: comer kcal estimadas durante 2 sem y medir peso. Si cambia >0.5%/sem, ajustar +-100-200 kcal.

### Superavit (hipertrofia)

| Tipo | Surplus | Ganancia /sem | Para quien |
|---|---|---|---|
| Lean bulk | +5-10% (~+150-300 kcal) | 0.2-0.4 kg | Intermedio/avanzado |
| Bulk moderado | +10-15% (~+300-500 kcal) | 0.4-0.7 kg | Principiante o recomp |
| Dirty bulk | +20%+ | >0.7 kg | NUNCA recomendar; >50% sera grasa |

Principiantes con peso saludable: pueden ganar musculo en mantenimiento o ligero deficit (newbie gains).

### Deficit (perdida de grasa)

| Tipo | Deficit | Perdida /sem | Para quien |
|---|---|---|---|
| Conservador | -10-15% | 0.5% peso corporal | Cuerpo lean (>15% grasa hombre) |
| Moderado | -15-20% | 0.7-1% peso corporal | Sobrepeso, prioriza musculo |
| Agresivo | -20-25% | 1% peso corporal | Atletas con monitoreo, corto plazo (<8 sem) |
| Extremo | -25%+ | >1% peso corporal | NUNCA - perdida muscular, energia, ciclo (mujeres) |

> Regla dura EntrenadorAX: nunca recomendar deficit > 25% TDEE (REGLA #1 del SKILL).

### Refeeds y dietary breaks

- **Refeed**: 1-2 dias/sem a mantenimiento o leve surplus (+ carbs), solo durante cortes >6 sem.
- **Diet break**: 7-14 dias a mantenimiento cada 6-12 sem de deficit. Reduce adaptaciones metabolicas (Trexler 2014).

## 3. Macronutrientes (ISSN consensus)

### Proteina

> Para hipertrofia maxima en personas que entrenan: 1.6-2.2 g/kg de peso corporal/dia, distribuida en 4-6 comidas con 0.4 g/kg por comida.
> Jager R et al, ISSN Position Stand: Protein and Exercise. JISSN, 2017.

| Situacion | g/kg | Por que |
|---|---|---|
| Sedentario | 0.8-1.2 | RDA cubre |
| Resistencia | 1.2-1.4 | Recuperacion |
| Hipertrofia | 1.6-2.2 | Sintesis proteica maxima |
| Deficit calorico | 2.2-2.7 | Preservar masa magra |
| Atleta de fuerza/potencia | 1.6-2.0 | Recuperacion neural + muscular |
| Adulto mayor | 1.2-1.5 | Combatir sarcopenia |

Por comida: 0.4 g/kg cada 3-5 h optimiza MPS (Schoenfeld 2018).

Fuentes con leucina alta (>2.5 g/dosis dispara MPS): carne magra, lacteos, huevo, suero (whey).

### Carbohidratos

| Modalidad | g/kg/dia |
|---|---|
| Sedentario | 2-3 |
| Resistencia recreativa | 3-5 |
| Resistencia moderada | 5-7 |
| Resistencia alta/competitiva | 6-10 |
| Ultra-resistencia | 8-12 |
| Fuerza/hipertrofia | 4-7 |

Timing: 1-4 g/kg 1-4 h pre-entreno; 1-1.2 g/kg/h en ventana de 4 h post-entreno si entrena 2x dia o competencia.

### Grasas

Minimo 0.6-0.8 g/kg para funcion hormonal (testosterona, estrogenos). Idealmente 20-35% de las calorias totales.

Distribucion:
- Saturadas: <10% del total
- Mono-insaturadas: 10-20% (aceite oliva, aguacate, frutos secos)
- Omega-6 / Omega-3: ratio 4:1 o mejor (suplementar omega-3 1-3 g EPA+DHA/dia)

## 4. Nutrient timing (ISSN 2017)

> La "ventana anabolica" post-entreno es mas amplia de lo que se pensaba (~3-5 horas), pero consumir proteina cerca del entrenamiento (1-2 h antes o despues) sigue siendo beneficioso, especialmente si hubo ayuno previo.
> Kerksick CM et al, JISSN 2017.

Reglas practicas:

1. **Pre-entreno (1-3 h)**: mezcla carb + proteina, baja en grasa/fibra. Ejemplo: avena + suero + platano.
2. **Intra-entreno (>60 min intenso)**: 30-60 g carbs / h (bebida deportiva o gel).
3. **Post-entreno (0-2 h)**: 0.4-0.5 g/kg proteina + carbs segun el resto del dia.
4. **Antes de dormir**: 30-40 g proteina lenta (caseina, queso cottage) si entrenas duro.

## 5. Hidratacion (ACSM + ISSN)

### Baseline

30-40 ml/kg/dia + 500-1000 ml extra por hora de ejercicio.

### Sweat rate test

```
sudor_l_h = (peso_pre_kg - peso_post_kg + liquido_bebido_l) / horas_entreno
```

Reponer 100-150% del peso perdido en las 4-6 h post-entreno.

### Electrolitos

- Sodio: 500-700 mg/L de bebida si entrenas >90 min o sudas mucho
- Potasio, magnesio, calcio: cubrir con dieta variada

Sintomas de hiponatremia (sodio bajo por exceso de agua): nausea, confusion, edema. Pasa en eventos largos (maraton, ultra) cuando solo bebes agua.

## 6. Suplementos basados en evidencia

Solo recomendar los con consenso ISSN/IOC:

| Suplemento | Dosis | Cuando | Evidencia |
|---|---|---|---|
| Creatina monohidrato | 3-5 g/dia | Cualquier momento, diario | A+ (Kreider 2017) |
| Cafeina | 3-6 mg/kg | 30-60 min pre-entreno | A+ (Guest 2021) |
| Proteina en polvo | Para cerrar gap | Conveniencia | A |
| Beta-alanina | 3.2-6.4 g/dia (split) | Continuo, 4-12 sem para saturar | A (esfuerzos 60-240s) |
| Citrulina malato | 6-8 g | 30-60 min pre-entreno | B+ (bombeo, repeticiones) |
| Omega-3 (EPA+DHA) | 1-3 g/dia | Con comida | A (antiinflamatorio, salud) |
| Vitamina D3 | 1000-4000 UI/dia | Si nivel <30 ng/ml | A (deficit comun) |
| Bicarbonato Na+ | 0.2-0.3 g/kg | 60-180 min pre, esfuerzos 1-7 min | B (riesgo GI) |
| Beta-hidroxi-beta-metil-butirato (HMB) | 3 g/dia | Principiantes o atletas en deficit | C |
| Glutamina | - | NO recomendar a sanos | F (sin efecto) |
| Quemadores | - | NO recomendar | F (riesgo + sin efecto) |

## 7. Plantilla de calculo (uso en futura tool de EntrenadorAX)

```
Usuario: 75 kg, 175 cm, 30 anos, hombre, intermedio, 4 entrenos/sem, objetivo recomposicion

TMB (Mifflin) = 10*75 + 6.25*175 - 5*30 + 5 = 750 + 1093.75 - 150 + 5 = 1698.75 kcal
TDEE = 1698.75 * 1.55 = 2632 kcal

Objetivo recomposicion = TDEE - 10% = 2369 kcal

Proteina: 2.0 g/kg = 150 g (600 kcal, 25%)
Grasa:    0.9 g/kg = 67 g  (603 kcal, 25%)
Carbs:    (2369 - 600 - 603) / 4 = 291 g (1166 kcal, 50%)

Reparto: 4 comidas x 37 g proteina ; carbs ponderados pre/post entreno
```

## 8. Senales de alarma (REGLA #6 del SKILL: derivar a profesional)

- Perdida de peso >1.5% / semana sostenida
- Amenorrea u oligomenorrea (mujeres en deficit)
- Caida persistente de libido (RED-S en ambos sexos)
- Mareos, hipotension ortostatica
- Antecedente de TCA -> NUNCA prescribir deficit sin profesional
- T3 baja sostenida (hipotiroidismo por deficit cronico)

## Citas

- Jager R, Kerksick CM, Campbell BI, et al. *International Society of Sports Nutrition Position Stand: protein and exercise*. JISSN, 2017.
- Kerksick CM, Arent S, Schoenfeld BJ, et al. *ISSN Position Stand: nutrient timing*. JISSN, 2017.
- Kerksick CM, Wilborn CD, Roberts MD, et al. *ISSN exercise & sports nutrition review update: research & recommendations*. JISSN, 2018.
- Guest NS, VanDusseldorp TA, Nelson MT, et al. *ISSN Position Stand: caffeine and exercise performance*. JISSN, 2021.
- Kreider RB, Kalman DS, Antonio J, et al. *ISSN Position Stand: safety and efficacy of creatine supplementation*. JISSN, 2017.
- Helms ER, Aragon AA, Fitschen PJ. *Evidence-based recommendations for natural bodybuilding contest preparation: nutrition and supplementation*. JISSN, 2014.
- Helms ER, Valdez A, Morgan A. *The Muscle and Strength Pyramid: Nutrition*, 2da ed. 2019.
- Schoenfeld BJ, Aragon AA. *How much protein can the body use in a single meal for muscle-building? Implications for daily protein distribution*. JISSN, 2018.
- Trexler ET, Smith-Ryan AE, Norton LE. *Metabolic adaptation to weight loss: implications for the athlete*. JISSN, 2014.
- Thomas DT, Erdman KA, Burke LM. *Position of the Academy of Nutrition and Dietetics, Dietitians of Canada, and the American College of Sports Medicine: Nutrition and Athletic Performance*. J Acad Nutr Diet, 2016.
- Mountjoy M et al. *IOC consensus statement on Relative Energy Deficiency in Sport (RED-S)*. Br J Sports Med, 2018.
