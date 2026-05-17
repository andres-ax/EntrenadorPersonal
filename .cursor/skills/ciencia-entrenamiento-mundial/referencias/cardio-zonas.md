# Cardio y Zonas de Entrenamiento

Base: Jack Daniels (Running Formula 4ta ed), Stephen Seiler (Polarized training), Phil Maffetone (MAF), Andrew Coggan (Power zones cycling), Joel Jamieson (work capacity).

## 1. Zonas por frecuencia cardiaca (5-zone Coggan/Friel)

### Calculo de FCmax

| Formula | Ecuacion | Error |
|---|---|---|
| Tanaka (mejor consenso) | FCmax = 208 - 0.7 * edad | +-7 ppm |
| Fox/Haskell (clasica, sesgada) | FCmax = 220 - edad | +-12 ppm |
| Test de campo (mejor) | Despues de 10 min al maximo en cuesta | +-3 ppm |

### Zonas % FCmax

| Zona | % FCmax | % FC reserva | RPE | Combustible | Tipo entrenamiento |
|---|---|---|---|---|---|
| Z1 (Recovery) | 50-60 | 35-55 | 2-3 | 90% grasa | Activa, calentamiento |
| Z2 (Aerobic base) | 60-70 | 55-75 | 4-5 | 70-80% grasa | Base aerobica, mitocondrial |
| Z3 (Tempo) | 70-80 | 75-85 | 6-7 | 50% mix | Threshold inferior |
| Z4 (Threshold) | 80-90 | 85-95 | 8-9 | Glucogeno | Lactate threshold |
| Z5 (VO2max) | 90-100 | 95-100 | 10 | Glucogeno + anaerobico | Intervalos cortos |

### Calculo FC objetivo (Karvonen, mas preciso que % directo)

```
FC_objetivo = ((FCmax - FC_reposo) * %intensidad) + FC_reposo
```

Ejemplo: 30 anos, FC reposo 60, %intensidad 70% para Z2:
FCmax = 208 - 0.7*30 = 187
FC_obj = ((187 - 60) * 0.70) + 60 = 89 + 60 = 149 ppm

## 2. Zone 2: el zorro silencioso

Por que Z2 es la mas importante para 80% de los deportes:

1. **Densidad mitocondrial**: estimula biogenesis mitocondrial (PGC-1alpha), mejorando capacidad oxidativa.
2. **Eficiencia de grasa**: aprende a oxidar grasa, ahorrando glucogeno para esfuerzos altos.
3. **Recuperacion**: trabajo aerobico sin acumular fatiga sistemica.
4. **Base para todo**: capacidades altas (Z4, Z5) dependen de base Z2.

### MAF Method (Phil Maffetone)

Para entrenamiento aerobico de bajo estres, especialmente endurance:

```
FC_MAF = 180 - edad
```

Ajustes:
- Resta 10 si: enfermedad cronica, recuperandose de lesion mayor, tomando medicacion regular
- Resta 5 si: lesionado, sobreentrenamiento, mas de 2 resfriados/ano, alergias
- Suma 5 si: atleta competitivo entrenando >2 anos sin lesion + progreso continuo

Hacer TODO el aerobico abajo de esta FC durante 3-6 meses construye base masiva.

### MAF Test

Mismo recorrido (ej: 5 km llano) corriendo justo bajo FC_MAF cada 2-4 sem. Mejora del pace = mejora de eficiencia aerobica.

## 3. Threshold (anaerobico/lactato)

### Lactate threshold (LT) y critical power

- **LT1 (~Z3 alto)**: punto donde lactato sube por encima de basal (~2 mmol/L). Tempo sostenible 60+ min.
- **LT2 / OBLA (~Z4)**: lactato 4 mmol/L. Pace sostenible ~30-60 min (~10 km a 10 mile race pace).

### Test de campo: 30-min tempo

Calienta 15 min. Corre/pedalea 30 min al maximo sostenible. FC promedio de los ultimos 20 min ~ FC threshold.

### Workouts threshold

| Tipo | Volumen | Descanso | Frecuencia |
|---|---|---|---|
| Cruise intervals | 5-8 x 1000 m @ T-pace | 1 min | 1x/sem |
| Tempo continuo | 20-40 min @ T-pace | - | 1x/sem |
| Tempo run | 30 min al 80-85% FCmax | - | 1x/sem |

## 4. VO2max

### Que es

Maximo volumen de oxigeno consumido por minuto. Predictor #1 de salud cardiovascular y longevidad (Mandsager 2018).

### Como medir

| Metodo | Precision |
|---|---|
| Laboratorio (analizador gases) | Gold standard |
| Cooper test (correr 12 min, distancia max) | +-10% |
| Beep test (course-navette) | +-10% |
| Garmin/Apple Watch estimacion | +-15% |

### Cooper test formula

```
VO2max (ml/kg/min) = (distancia_m - 504.9) / 44.73
```

### Categorias por edad y sexo (referencia ACSM)

Hombre 20-29:

| VO2max | Categoria |
|---|---|
| <38 | Muy bajo |
| 38-42 | Bajo |
| 43-47 | Promedio |
| 48-52 | Bueno |
| 53-58 | Excelente |
| >58 | Atleta |

Mujer 20-29:

| VO2max | Categoria |
|---|---|
| <32 | Muy bajo |
| 32-36 | Bajo |
| 37-41 | Promedio |
| 42-46 | Bueno |
| 47-52 | Excelente |
| >52 | Atleta |

### Workouts para VO2max

| Tipo | Detalle | Por que funciona |
|---|---|---|
| Norwegian 4x4 | 4x(4 min @ 90-95% FCmax + 3 min Z1) | Maximiza tiempo en VO2max zone |
| Tabata | 8x(20s al maximo + 10s descanso) | Tope anaerobico + aerobico |
| 30/30 | 30s rapido / 30s lento, 20-30 min total | Volumen alto cerca de VO2 |
| Hill repeats | 6-10x(60-90s cuesta empinada + bajar) | Fuerza + VO2max combinado |

Frecuencia: 1-2x/sem MAX. Muy demandante.

## 5. Polarized vs Threshold training (Seiler)

### Polarized 80/20

> Los atletas de elite distribuyen 75-85% del volumen en Z1-Z2 (facil) y 15-25% en Z4-Z5 (duro), evitando casi por completo la "zona gris" Z3.
> Seiler S, Int J Sports Physiol Perform, 2010.

| Modelo | Z1-Z2 | Z3 | Z4-Z5 |
|---|---|---|---|
| Polarized | 80% | <5% | 15-20% |
| Threshold | 50% | 30% | 20% |
| Piramidal | 70% | 20% | 10% |

Evidencia: polarized > threshold para mejorar VO2max y rendimiento sostenido en endurance recreativo a elite (Stoggl 2014, meta-analisis Foster 2022).

## 6. Jack Daniels: VDOT y paces

VDOT es un VO2max ajustado a rendimiento real en carrera. Tablas de Daniels predicen pace para cada zona y cada distancia.

Categorias de entrenamiento (Daniels):

| Zona | % VO2max | % FCmax | Ejemplo objetivo |
|---|---|---|---|
| E (Easy) | 59-74% | 65-78% | 80% del kilometraje semanal |
| M (Marathon) | 75-84% | 80-89% | Long runs |
| T (Threshold) | 83-88% | 88-92% | Cruise intervals, tempo |
| I (Interval / VO2max) | 95-100% | 97-100% | 3-5 min repeats |
| R (Repetition / Speed) | >100% | - | 200-400m fast |

Ejemplo: corredor con VDOT 50 (10 km en ~43 min):
- E pace: 5:00-5:35/km
- T pace: 4:00/km
- I pace: 3:38/km

Usar la VDOT calculator (Run SMART project / VDOTo2) o las tablas del libro.

## 7. Cardio en programa de fuerza/hipertrofia (concurrent training)

### El problema de interferencia (Hickson 1980, Wilson 2012 meta)

Demasiado cardio reduce ganancias de fuerza/hipertrofia (efecto AMPK vs mTOR).

### Reglas para no interferir

1. **Separar al menos 6 h** entre sesion de pesas y cardio intenso.
2. **Si no se puede separar**: pesas PRIMERO, cardio despues (orden importa).
3. **Maximo 2-3 sesiones de 20-30 min Z2** / semana durante bulk.
4. **Evitar Z4-Z5 grandes volumenes** si meta primaria es hipertrofia.
5. **Modalidades de menor impacto**: ciclismo, eliptica, remo > correr para preservar piernas.

### Cardio recomendado en cuts (deficit)

- 3-5 sesiones de 30-45 min Z2 + 1-2 sesiones HIIT cortas (10-15 min)
- Mantener pesas como prioridad para preservar masa magra

## 8. HIIT vs LISS para perdida de grasa

Meta-analisis Wewege 2017: HIIT y LISS producen perdida de grasa equivalente cuando el gasto calorico es igual. HIIT es mas eficiente en tiempo; LISS es mas sostenible y menos estresante.

Recomendacion practica:

- 60-70% del cardio en Z2 (base, recovery, sostenible)
- 20-30% en threshold/HIIT (eficiente, estimula VO2max)
- Variar segun temporada (mas Z2 en off-season, mas HIIT en preparacion)

## 9. Casos especiales por deporte

| Deporte | Distribucion ideal |
|---|---|
| Maraton/ultra | 80% Z1-Z2, 10% Z3, 10% Z4 + 1 long run/sem |
| 5K/10K | 75% Z1-Z2, 10% Z3, 15% Z4-Z5 |
| Fuerza/Powerlifting | 2-3 caminatas Z2 (45 min) /sem |
| Hipertrofia (bulk) | 2x 20-30 min Z2 /sem |
| Hipertrofia (cut) | 4-5x 30-45 min Z2 + 1-2 HIIT /sem |
| CrossFit | Z2 1-2x + ya hay metcons que cubren HIIT |
| Futbol/team sports | Z2 base 2x/sem + intervalos sport-specific |
| Salud general | 150 min/sem Z2-Z3 + 2 HIIT cortos (OMS 2020) |

## Citas

- Daniels J. *Daniels' Running Formula*, 4ta ed. Human Kinetics, 2022.
- Seiler S. *What is best practice for training intensity and duration distribution in endurance athletes?*. Int J Sports Physiol Perform, 2010.
- Stoggl T, Sperlich B. *Polarized training has greater impact on key endurance variables than threshold, high intensity, or high volume training*. Front Physiol, 2014.
- Foster C et al. *The effects of polarized vs. threshold training on endurance performance: a meta-analysis*. JSCR, 2022.
- Coggan AR, Allen H. *Training and Racing with a Power Meter*, 3ra ed. VeloPress, 2019.
- Maffetone P. *The Big Book of Endurance Training and Racing*. Skyhorse, 2010.
- Tanaka H, Monahan KD, Seals DR. *Age-predicted maximal heart rate revisited*. J Am Coll Cardiol, 2001.
- Mandsager K et al. *Association of Cardiorespiratory Fitness With Long-term Mortality Among Adults Undergoing Exercise Treadmill Testing*. JAMA Netw Open, 2018.
- Wilson JM et al. *Concurrent training: a meta-analysis examining interference of aerobic and resistance exercises*. JSCR, 2012.
- Wewege M et al. *The effects of high-intensity interval training vs. moderate-intensity continuous training on body composition in overweight and obese adults: a systematic review and meta-analysis*. Obes Rev, 2017.
- Hickson RC. *Interference of strength development by simultaneously training for strength and endurance*. Eur J Appl Physiol, 1980.
- Norwegian University of Science and Technology. *4x4 minute interval protocol* (Helgerud 2007). Med Sci Sports Exerc.
- OMS. *WHO Guidelines on Physical Activity and Sedentary Behaviour*, 2020.
