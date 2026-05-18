# Deportes en Colombia — Expansion EntrenadorAX

> Investigacion exhaustiva para expandir el bot de 10 deportes a 60+, con foco en deportes urbanos/accion (BMX, skate, rollers) que NO se trackean con peso x reps.
> Estado actual del bot: `deporte_principal` es `String(100)` libre. Onboarding sugiere 10 deportes (gimnasio, crossfit, running, futbol, calistenia, natacion, ciclismo, yoga, boxeo, tenis). `registrar_entreno` solo acepta `fuerza | cardio | movilidad | deporte`. `PersonalRecord` solo tiene `peso_kg + reps`. Esto NO sirve para BMX/skate/rollers/surf/climbing.

---

## 0. Resumen ejecutivo

- Colombia tiene escena viva en **60+ deportes** organizados, con **federaciones reconocidas por Mindeporte** en al menos 35 de ellos. Esta investigacion mapea 67 deportes practicables en Colombia con info accionable para el bot.
- **3 deportes urbanos prioritarios** (BMX, skate, rollers) son el foco del usuario. Los tres requieren un modelo distinto al fitness tradicional: skill > volumen, trucos como PR (no peso x reps), sesiones medidas en horas/intentos, plataformas Instagram Reels/YouTube/Discord (no Strava).
- Colombia es **potencia mundial verificada** en: BMX racing (Mariana Pajon, 2 oros olimpicos), patinaje de carrera (14 mundiales consecutivos hasta 2024, 21 totales), halterofilia (campeon mundial absoluto 2022), ciclismo de ruta (Egan Bernal, Nairo Quintana), boxeo (Yuberjen Martinez plata Rio 2016) y judo (Yuri Alvear, doble medallista olimpica).
- **Boom 2023-2026**: padel paso de 0 a 687 pistas en menos de 3 anos, con federacion oficial (FCP) constituida en 2025.
- El bot necesita **5 cambios estructurales** para soportar estos deportes (detalle en seccion 4): taxonomia jerarquica, `PersonalRecord` polimorfico, nuevos `TipoEjercicio`, prompts deporte-aware en el coach, integraciones con plataformas distintas a Strava.

---

## 1. Tabla maestra de deportes en Colombia

Leyenda:
- **Cat**: categoria taxonomica propuesta (ver seccion 3).
- **Escena CO**: ciudades con escena activa relevante.
- **Metrica**: que registrar PRINCIPALMENTE en el bot (lo que reemplaza a "peso x reps").
- **Plataforma**: donde la escena vive online (no Strava por defecto).

### 1.1 Deportes urbanos / accion (foco maximo del proyecto)

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento minimo | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|---------------------|-----------|
| 1 | **BMX** | urbano | Racing (olimpico), Freestyle Park, Street, Dirt, Vert, Flatland | Bogota (Pista Carlos Ramirez El Salitre), Medellin, Cali (Pance William Jimenez), Armenia, Barranquilla (Malecon) | Sesiones (min), trucos aterrizados, alturas (m), gates ganadas, vueltas, lineas filmadas | bunny hop, manual, 180/360, tabletop, x-up, no foot can-can, tailwhip, barspin, flair, backflip, peg grind | bici BMX (20" race / 20.5-21" freestyle), casco full-face (race) o open-face (freestyle), guantes, rodilleras, shin guards | Instagram Reels, YouTube, Vital BMX (foro) |
| 2 | **Skate** | urbano | Street, Park/Bowl, Vert, Longboard cruising, Longboard downhill, Slalom, Freestyle | Bogota (Fontanar, Salitre, Suba), Medellin (Aranjuez, Ciudad del Rio, 11 parks intervenidos 2026), Cali (Pance), Envigado | Sesiones (min), trucos aterrizados, lineas filmadas, NBD ("never been done"), make rate (aterrizados/intentos) | ollie, kickflip, heelflip, varial, shuvit, manual, nose manual, grind (50/50, 5-0, smith, feeble, crooked, salad, willy), slide (boardslide, lipslide, noseslide, tailslide), drop in, fakie, switch, nollie, revert, primo | tabla (deck 7.75"-8.5"), trucks, ruedas (52-58mm street), rodamientos, casco, munequeras, rodilleras | Instagram Reels, YouTube, The Berrics, Thrasher |
| 3 | **Patinaje rollers** | urbano | Velocidad/carrera (potencia mundial CO), Artistico, Agresivo (inline), Freestyle slalom, Hockey en linea, Roller derby, Danza | Bogota (Patinodromo El Salitre, Simon Bolivar), Medellin, Cali (cuna), Pereira, Barranquilla (Malecon) | Speed: tiempos por vuelta + records personales en distancia (200m, 500m, 1000m, 10k, maraton). Freestyle/agresivo: trucos aterrizados, lineas. Slalom: figuras por config de conos | Speed: drafting, pelotonneo, paso doble, paso cruzado, contrarreloj, eliminacion, puntos, americana. Agresivo: soul, royale, mizou, makio, unity, fishbrain, alleyoop, topside, grab. Slalom: cross over, snake, sun, eagle, footgun, criss cross | Speed: patines inline 4x100mm o 4x110mm carbono, traje aerodinamico, casco aero. Agresivo: patines anti-rocker con grind plate, rodilleras, casco. Slalom: patines 4x80mm | IG, YouTube, World Skate TV, Patinesychuecas.com |
| 4 | **Scooter freestyle** | urbano | Park, Street | Bogota, Cali, Medellin (Federacion Colombiana de Patinaje regula) | Sesiones (min), trucos aterrizados | bunnyhop, tailwhip, barspin, hellwhip, manual, nose manual, hang 5, smith grind, feeble grind | scooter freestyle (deck reforzado), casco, guantes | IG Reels, YouTube |
| 5 | **Parkour / Freerunning** | urbano | Speed, Style, Combat, Trickz | Bogota (Parkour Usaquen, Casona de la Danza), Medellin (Liga Antioquena Gimnasia), Cali | Sesiones (min), spots (lugares), lineas (line runs), saltos maximos (m), traceurs entrenados | precision, monkey vault, kong, dash, lazy, speed vault, wall run, cat leap, palm spin, swan dive, flip, backflip, sideflip | calzado minimalista, manos libres (sin guantes), opcional rodilleras | IG, YouTube (Storror, Movement Culture), Discord parkour-co |
| 6 | **Slacklining / Highline** | urbano | Trickline, Longline, Highline, Waterline, Yoga | Bogota (Hacienda Santa Barbara Usaquen, antes Parkway), Envigado (Soul Line - 1er slack park CO), Sutatausa (highlines hasta 70m) | Sesiones (min), longitud caminada (m), altura highline (m), trucos | line, anchor, leash, butt bounce, chest bounce, surfing, foot drag, full man, exposure | slackline + anchors + trees/anchors. Highline: arnes, casco, leash de seguridad | IG, Centro de Slackline Colombia (centroslackline.com), grupos FB |
| 7 | **Climbing / Escalada** | urbano | Boulder (V0-V17), Deportiva (5.5-5.15), Trad, Big wall, Velocidad | Suesca (Cundinamarca, 300+ vias - capital climbing CO), San Gil (Santander), Macheta, Mongui (Boyaca), Tatacoa, El Penol, Canoas Soacha (boulder), Chusaca (boulder), La Calera, Manizales, Mongui, Toluviejo | Vias enviadas + grado max, sesiones (h), pico de fuerza (hangboard), proyectos en curso | flash, on sight, redpoint, beta, crux, send, project, sloper, crimp, jug, pinch, undercling, gaston, dyno, heel hook, drop knee, smear, flag | pies de gato, magnesio + bolsa, arnes, cuerda, casco, expres, asegurador (Grigri/ATC), boulder: crash pad | IG, theCrag, Mountain Project, Monodedo, grupos FB "Escaladores Colombia" |
| 8 | **Surf** | urbano | Shortboard, Longboard, Bodyboard, SUP surf | Nuqui/Termales/Tribuga/Pico de Loro (Pacifico Choco), Cabo de la Vela (Guajira Caribe), Palomino, Santa Veronica (Atlantico), San Andres | Sesiones (h), olas surfeadas, swell maximo (ft), maniobras (cutback, off the lip, tube), spot conocido | take off, paddle, duck dive, bottom turn, cutback, off the lip, snap, floater, tube, barrel, drop, switch foot, regular, goofy | tabla (shortboard 5'8-6'4, longboard 9'+), leash, traje (no necesario en CO), wax | IG Reels, YouTube, Surfline app, grupos FB "Surf Colombia" |
| 9 | **Kitesurf / Windsurf** | urbano | Twin tip, Foil, Big air, Wave riding, Wing foil | Cabo de la Vela (25 nudos all year, TAWI Kite Center), Cartagena/La Boquilla (ene-abr), Santa Veronica | Sesiones (h), viento minimo/maximo navegado (nudos), trucos (altura, rotaciones), foils | edging, jibe, transition, upwind, downwind, kite loop, board off, raley, handle pass, foil pop | kite + barra, tabla, arnes, traje (no necesario CO), leash. Foil: tabla foil + ala | IG, YouTube, kitetrip-planner.com |
| 10 | **Wakeboard / Esqui acuatico** | urbano | Wakeboard cable, Wakeboard boat, Esqui slalom, Knee, Flyboard | Guatape (epicentro, Vikingos Club Nautico), Lago Calima, Tota | Sesiones (h), trucos aterrizados (raley, S-bend), salto maximo (ft) | tail, nose, surface 360, raley, S-bend, indy, mute, KGB, scarecrow, glide | tabla wake con bindings, chaleco, casco (opcional), guantes esqui | Fedesqui Colombia, IG |
| 11 | **SUP (stand-up paddle)** | urbano | Race, Touring, Surf, SUP yoga, Whitewater | Cartagena, Guatape, San Andres, Cabo Corrientes, Tayrona | Sesiones (h), distancia (km), trucos (cross step, pivot turn) | paddle, J-stroke, sweep stroke, pivot turn, cross step, back step, bracing | tabla SUP (inflable o rigida), remo, leash, chaleco | IG, FB groups SUP CO |
| 12 | **Snowboard / Esqui** | urbano | Freestyle park, Backcountry, Race, Carving | Colombianos viajan: Valle Nevado/Portillo (Chile), Bariloche/Cerro Catedral/Chapelco/Cerro Bayo (Argentina). Temporada jun-sep | Dias en nieve, descensos, trucos (en park), gradiente max | toe edge, heel edge, carve, ollie, butter, grind, grab (indy, mute, melon), 180/360/540, rail, jib, switch | tabla snowboard + bindings + botas O esquis + bastones, casco, antiparras, traje impermeable | IG, mountains.com, Snowboarder Mag |

### 1.2 Artes marciales / combate

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 13 | **Boxeo** | combate | Amateur, Profesional, Sparring, Tecnica | Yuberjen Martinez (plata Rio 2016), federaciones por departamento, gyms en todo el pais (Striking Fitness Cali) | Sesiones (min), rounds, sparring, peleas, peso peleado, golpes/min (mide en saco) | jab, cross, hook, uppercut, slip, bob and weave, parry, clinch, footwork, southpaw, orthodox, double end bag, heavy bag | guantes (12-16oz training, 8-10oz pelea), wraps, protector bucal, careta sparring | IG, YouTube, Mindeporte |
| 14 | **Muay Thai** | combate | K1, Thai tradicional, Sparring | Academias en Bogota (JM Team), Medellin (Zona de Combate, MMA Colombia), Cali | Sesiones, rounds, peleas, lineas de combo | jab, cross, teep, roundhouse kick, push kick, knee, elbow, clinch, sweep | guantes thai, shin guards, protector bucal, copa, wraps | IG, WAKO Colombia |
| 15 | **BJJ Jiu-Jitsu brasileno** | combate | Gi, No-gi, ADCC, Submission only | Medellin (Gracie Colombia, Gracie Barra), Bogota (multiple academias), Affinity Studios | Rolls (sparring), tiempo en cinturon, sumisiones aterrizadas, torneos | guard, mount, side control, back, sweep, submission (kimura, armbar, triangle, omoplata, RNC), guard pass, takedown, escape, frame, grip | gi (kimono), faja por cinturon (blanca, azul, morada, marron, negra), rashguard, spats, protector bucal | IG, BJJ Heroes, FloGrappling, Smoothcomp |
| 16 | **MMA** | combate | Amateur, Profesional | OCAMM (Asociacion Colombiana MMA), academias en Medellin (Zona de Combate, MMA Colombia), Bogota (JM Team, AnimalFit) | Rounds sparring, peleas, sumisiones, KOs, weight cuts | striking, grappling, ground and pound, takedown defense, sprawl, double leg, clinch break, transition | guantes 4oz (pelea) / 7oz (training), shin guards, protector bucal, copa, rashguard | IG, MMA Junkie, OCAMM |
| 17 | **Karate** | combate | Shotokan, Kyokushin, Goju-Ryu, Wado-Ryu, Sport karate (WKF) | Academias en Bogota, Medellin, Cali; Federacion Colombiana de Karate | Katas dominadas, kumite, grado de cinturon, torneos | gi, kata, kumite, kihon, oi-zuki, gyaku-zuki, mae-geri, mawashi-geri, yoko-geri, age-uke, gedan-barai, kiai | gi karate, cinturon, protectores WKF (manos, pies, espinilla, peto) | IG, WKF, Mindeporte |
| 18 | **Taekwondo** | combate | WT (olimpico), ITF, Poomsae | Colombia con escenas activas, medallistas internacionales | Patadas dominadas, poomsae, sparring, grado | dolyo chagi, naeryeo chagi, dwit chagi, momtong jireugi, ap chagi, poomsae taegeuk, jorum jaseh | dobok, cinturon, peto electronico (sport), casco, protector bucal, espinilleras | IG, World Taekwondo, Fedecoltkd |
| 19 | **Judo** | combate | IJF reglas | Yuri Alvear (doble medallista olimpica, ahora entrenadora seleccion), Fecoljudo | Tatami time, ippons, randori, grado, torneos | seoi nage, uchi mata, osoto gari, harai goshi, kesa gatame, juji gatame, kuzushi, tsukuri, kake, rei | judogi, cinturon, descalzo en tatami | IG, fecoljudo.org.co, JudoInside |
| 20 | **Kickboxing / K-1** | combate | K1, Sanda, Full contact, Light contact | WAKO Colombia (federacion oficial), academias en todas las ciudades | Rounds, peleas, combos dominados | jab-cross-hook, low kick, middle kick, high kick, switch kick, push kick, knee, sweep, clinch | guantes 10oz, shin guards, protector bucal, copa | IG, WAKO Colombia |
| 21 | **Wrestling / Lucha** | combate | Libre, Grecorromana, Folkstyle | Federacion Colombiana de Lucha, John Tacha (entrenador Cundinamarca) | Tatami time, takedowns, escapes, torneos | double leg, single leg, sprawl, takedown, granby roll, pinning, escape, ride, half nelson, gut wrench | singlet, zapatos lucha, protector orejas | IG, UnitedWorldWrestling, Flowrestling |
| 22 | **Capoeira** | combate | Regional, Angola, Contemporanea | Bogota, Medellin (Capoeira Mangalot), Cali, Barranquilla (Capoeira Nago, Grupo Nativos, Oficina, Ave Branca) | Rodas asistidas, cordoes ganados, tiempo en grupo | ginga, au, queixada, armada, meia lua, martelo, esquiva, negativa, role, chamada, jogo, mestre | abada (pantalon), cordao por nivel, descalzo o calzado liviano | IG, capoeiranativos.org, FB groups |
| 23 | **Krav Maga** | combate | Self-defense, Civil, Tactico | Academia Krav Maga Colombia (Bogota), academias en grandes ciudades | Sesiones, tecnicas dominadas, simulacros | retsev (estallido), trapping, choke defense, knife defense, gun defense, soft skills awareness | ropa comoda, protector bucal, copa (sparring) | IG, KMG, IKMF |
| 24 | **Esgrima** | combate | Florete, Espada, Sable | Saskia Loretta (Valle, San Sebastian club), federacion oficial, clubes en Valle/Bogota/Antioquia/Caldas/Risaralda/Tolima | Tocados ganados, torneos, ranking | en garde, advance, retreat, lunge, fleche, parry (1-8), riposte, attack, counter-attack, beat, fleche, balestra, derobement | uniforme blanco (chaqueta, knickers, plastron), careta, guante, arma (florete/espada/sable), conexion electrica | IG, FIE, fedesgrimacolombia.com |

### 1.3 Deportes de equipo

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 25 | **Baloncesto / Basquetbol** | equipo | 5x5, 3x3 (olimpico), Streetball | Liga Profesional Baloncesto (Liga BetPlay): Paisas Medellin (campeon 2025-I), Piratas Bogota, Caimanes Llano, Toros Valle, Cimarrones, Caribbean Storm, Motilones, Sabios. FIBA format. | Partidos, puntos/asistencias/rebotes, posicion, tiros, free throw % | layup, jump shot, three-pointer, dunk, pick and roll, screen, fadeaway, crossover, behind the back, pull up, isolation, fast break | tenis basket, mediasr, pantaloneta, balon (size 7 hombre, 6 mujer) | IG, FIBA, ESPN, Liga BetPlay |
| 26 | **Voleibol** | equipo | Sala 6x6, Playa 2x2 | Cartagena (Nacional Playa), Cali, Antioquia (campeon U15/U17), federacion oficial, Liga femenina sala | Sets, puntos, aces, bloqueos, recepciones positivas | service, ace, pass (forearm/overhand), set, spike/attack, block, dig, rotation, libero, opposite, outside hitter, middle blocker | tenis voley, mediasr, rodilleras, balon Mikasa | IG, FIVB, Federacion Colombiana Voleibol |
| 27 | **Beisbol** | equipo | LPBC profesional, amateur | Liga Profesional 2025-26 (50a edicion): Caimanes Barranquilla (campeon), Tigres Cartagena (subcampeon), Vaqueros Monteria, Toros Sincelejo. Caribe colombiano. | Partidos, AVG (bateo), OBP, HR, RBI, ERA (pitcher), strikeouts, innings pitched | strike, ball, walk, single, double, triple, home run, RBI, ERA, K, fielding error, double play, bunt, steal, slider, curveball, fastball, change-up | bate, guante, mascara catcher, casco, spikes, uniforme | IG, MLB, LPBC |
| 28 | **Softbol** | equipo | Femenino fastpitch, Slowpitch | Federacion Colombiana, escenas Cundinamarca, Atlantico | Similar al beisbol con AVG, OBP, ERA | similar al beisbol + windmill pitch, riser, drop ball | bate softbol, guante (mas grande que beisbol), uniforme | IG, WBSC |
| 29 | **Rugby** | equipo | Union (XV), Sevens (7s), Tag, Touch | "Los Tucanes" seleccion CO, sede federacion Medellin, Liga Bogota (10+ clubes: Alianza, Barbarians, Cachacas, Carneros, Coyotes, Jaguares, Magnificos, Manoba, Minotauros, Salamandras) | Partidos, tries, conversiones, scrum tecnicas, posicion | try, conversion, penalty, drop goal, scrum, lineout, ruck, maul, knock-on, offside, tackle, breakdown, fly half, scrum half, prop, hooker | botines rugby, protector bucal (obligatorio), opcional headgear, balon rugby (oval) | IG, World Rugby, colombia.rugby |
| 30 | **Hockey** | equipo | Campo, Sala, En linea | Hockey linea: Liga Nacional + 18 equipos 9 ligas (Arauca, Bolivar, Boyaca, Bogota, Casanare, Cundinamarca, Santander, Tolima, Valle). Campo emergente. | Partidos, goles, asistencias, posicion | drag flick, scoop, push pass, dribble, tackle, slap shot, slot, power play, penalty corner | stick, espinilleras, protector bucal, balon (campo) / disco (linea), patines (en linea) | IG, FIH, lnhc.hockeyshift.com |
| 31 | **Football americano** | equipo | Tackle, Flag, Touch | Escena pequena, ligas universitarias y amateur en Bogota/Medellin | Yards, completions, touchdowns, sacks, tackles | rush, pass, touchdown, field goal, interception, sack, blitz, audible, route, down (1st-4th), red zone | casco, hombreras, pantalones con almohadillas, cleats, balon | IG, NFL, CFA Colombia |
| 32 | **Polo** | equipo | 4 jugadores | Clubes en Sabana (Cundinamarca), Llanos (Casanare/Meta), Cali; competiciones esporadicas. Argentina referente mundial. | Goles, handicap personal, partidos, chuckers (periodos) | chukker, nearside, offside, ride off, hook, mallet, neckshot, tailshot, foul, line of the ball | caballo (mas de 1), mallet, casco con careta, faceguard, rodilleras, botas, kneepads, espuelas | IG, AAPolo, USPA |
| 33 | **Ultimate Frisbee** | equipo | Open, Mixed, Women, Beach, Indoor | FECODV federacion, Comunidad El Oso/Aerosoul/Euforia (Bogota), Macana/Academia/Instinto (Antioquia), Aloha (Valle). Liga Estelar Bogota | Partidos, points (anotados/asistidos), turnovers, posicion (handler/cutter) | huck, dump, swing, scoober, hammer, IO/OI flick, stall count, marker, force, zone defense, man defense, layout, callahan | disco Discraft 175g, cleats (igual futbol), camiseta equipo | IG, fecodv.ultimatecentral.com, USAU |
| 34 | **Padel** | equipo | Singles, Dobles | BOOM: 687 pistas, 233 clubes, 53 ciudades, 8000+ jugadores activos (ene 2026). Federacion Colombiana Padel (FCP) constituida 2025, sede Barranquilla. Primera seleccion nacional 2026 | Partidos, sets/games, golpes maestrados, ranking nacional | volea, bandeja, vibora, smash, globo, dejada, salida pared, contrapared, chiquita, x3 (saque) | pala padel, mediasr, tenis padel (suela espina pez), botellas agua | IG, FIP, FCP, Padel Magazine |

### 1.4 Deportes individuales outdoor

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 35 | **Trail running / Ultrarunning** | individual_outdoor | 5K-21K trail, 42K (maraton), Ultra (50K, 100K, 100mi) | Columbia Trail Challenge Choachi, Cordillera Trail Futuro Tequendama, Ultra Trail Cordillera Oriental Duitama (42K), Ultra Valle de Tenza Boyaca (55K ultra). El Cocuy, Los Nevados, paramo | Distancia (km), desnivel (m+), tiempo, ritmo (min/km), elevation max, frecuencia cardiaca | desnivel positivo (D+), desnivel negativo (D-), elevation gain, single track, switchback, scree, paso, refugio, cut-off, drop bag, gel, peso de mochila | zapatillas trail (suela agresiva), mochila hidratacion 5-15L, frontal, bastones (opcional), capa impermeable, gels/comida | Strava, IG, ITRA, UTMB, itra.run |
| 36 | **Triatlon** | individual_outdoor | Sprint, Olimpico, 70.3, Ironman, Cross-tri | Ironman 70.3 Cartagena (nov, 9a edicion 2025), Carlos Quinchara (olimpico 2012), Federacion Colombiana Triatlon | Tiempos por segmento (swim/bike/run), T1/T2 (transiciones), volumen semanal por disciplina | brick workout, T1, T2, drafting, aero, OWS (open water swimming), trichoot, age group, qualification slot | bici aero/TT o ruta, casco aero, traje neopreno (en frio), gorro silicona, gafas swim, tenis run, transition belt | Strava, IG, TrainingPeaks, IRONMAN.com |
| 37 | **Duatlon** | individual_outdoor | Sprint, Estandar | Federacion Colombiana de Triatlon, eventos en Bogota/Medellin/Cali | Tiempos run-bike-run, total | run-bike-run, transition, drafting prohibido (legal en duatlon CO depende), age group | bici ruta, casco, tenis run | Strava, IG |
| 38 | **OCR / Spartan Race** | individual_outdoor | Sprint 5K, Super 12K, Beast 21K, Ultra 50K+, Trifecta | OCR Colombia (federacion oficial recognized FISO), Michel Esquier (Mundial Spartan 2024 Grecia), eventos en Bogota/Pereira | Distancia, obstaculos completados (sin penalty), penaltis burpees, tiempo total | rig, monkey bars, atlas carry, spear throw, rope climb, sandbag, bucket, A-frame, sandbag carry, burpee penalty | tenis trail con drenaje, ropa que seca rapido, guantes (opcional), reloj GPS | IG, Spartan.com, app.ocrcolombia.com |
| 39 | **Orientacion deportiva** | individual_outdoor | Sprint, Middle, Long, Night-O, Score | Federacion Colombiana de Orientacion, Campeonato Nacional Sprint Bogota nov 2025 | Tiempos, postes correctos, puntos, ruta elegida | control, baliza, mapa, tarjeta SI, ruta, attack point, contour, depression, knoll, brujula | mapa, brujula, tarjeta SI, ropa correr, gafas | IG, orientacion.co, IOF |
| 40 | **Mountain bike** | individual_outdoor | XC (cross country), Marathon, Enduro, Downhill, Trail, BMX dirt (cruza) | Panamericano Downhill Temuco 2025 (CO sub-campeon Sebastian Holguin, Valentina Roa), Gran Fondo Egan Bernal Zipaquira (14-16 nov 2025, 6000+ ciclistas), MTB Racing en Boyaca, Cundinamarca, Antioquia | Distancia, desnivel, ritmo, tiempos en segmentos Strava, tecnica (rock garden cleaned) | clipless, flat pedals, dropper post, switchback, berm, rock garden, drop, table top, send it, sketchy, rooty | bici MTB (hardtail XC, full sus enduro/DH), casco (open face XC, full face DH), gafas, guantes, rodilleras enduro/DH | Strava, IG, mtb.racing, Federacion CO Ciclismo |
| 41 | **Ciclismo de ruta / pista** | individual_outdoor | Ruta GC, Sprinter, Crono ITT, Pista (omnium, scratch, persecucion, keirin, sprint) | Egan Bernal (Tour 2019, Giro 2021), Nairo Quintana, Walter Vargas (6x crono panam), Harold Tejada, Brandon Rivera. Mundial Ruta 2025 Kigali. Federacion Colombiana Ciclismo | Distancia, FTP (watts), desnivel, KOM Strava, tiempo en zonas, kg de bici | peloton, breakaway, cresting, attack, sprint, lead-out, GC contender, climber, sprinter, rouleur, watts, FTP, NP, IF | bici ruta carbono, casco, gafas, kit (jersey+bib), guantes, cleats, ciclocomputador con potenciometro | Strava, IG, ciclismo21.com |
| 42 | **Atletismo** | individual_outdoor | Velocidad (100m, 200m, 400m), medio fondo (800, 1500), fondo (5K, 10K, maraton), saltos (largo, alto, triple, pertiga), lanzamientos (bala, disco, martillo, jabalina), pruebas combinadas (decatlon/heptatlon), marcha, vallas | Anthony Zambrano (plata 400m Tokio 2020), Caterine Ibarguen (oro triple Rio 2016), Yuberjen, Federacion Atletismo. Campeonatos Nacionales en Ibague/Bogota | Tiempos por prueba, marcas (m), records personales, frecuencia entrenos | sprint, blocks de salida, baton (relevos), false start, photo finish, lane assignment, take-off board (salto largo), put (bala), spin (disco), follow through | spikes pista (uno por prueba), uniforme, bala/disco/jabalina (lanzamientos), bastones (pertiga), pertiga | IG, World Athletics, fecodatle.com |
| 43 | **Halterofilia / Levantamiento olimpico** | individual_outdoor* | Snatch (arranque), Clean & Jerk (envion) | Campeon Mundial Absoluto 2022 (Colombia hizo historia con 24 medallas), Francisco Mosquera, Mabel Mosquera. Federacion Colombiana Levantamiento Pesas. Maria Isabel Urrutia (1er oro olimpico CO Sidney 2000) | Snatch max (kg), C&J max (kg), Total (kg), peso corporal categoria | snatch, clean, jerk, split jerk, push press, hang clean, drop snatch, OHS (overhead squat), positioning, hook grip, mobility (T-spine, ankles) | levantadoras (suela rigida), cinturon, munequeras, knee sleeves, magnesia | IG, IWF, fedepesascol.com |
| 44 | **Powerlifting** | individual_outdoor* | Raw, Equipped, Push pull, Bench only | Jorge Solano (campeon mundial 75kg Atenas), Federacion Colombiana Powerlifting (powerliftingcol.com) | Squat/Bench/Deadlift max (kg), Total, Wilks/IPF GL points | squat, bench press, deadlift (conventional/sumo), low bar, high bar, raw, equipped, RPE, attempts (1-3), board press, paused squat | rodilleras, muniequeras, cinturon, suela plana o talon (squat), straps (deadlift training) | IG, IPF, USAPL, powerliftingcol.com |

*Halterofilia/powerlifting tecnicamente individual_indoor pero categorizo por tradicion competitiva fuera de gym corporativo.

### 1.5 Deportes indoor / recreativos / fitness

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 45 | **Gimnasia artistica y ritmica** | indoor | Artistica F (suelo, barra equilibrio, viga, asimetricas, salto, paralelas, anillas, barra fija), Ritmica F (cuerda, aro, pelota, mazas, cinta) | Liga Antioquena Gimnasia, Federacion Colombiana Gimnasia, Angel Barajas (plata olimpica Paris 2024, 17 anos, 1a medalla CO gimnasia) | Aparatos dominados, dificultad ejercicios (codigo D), nota artistica E, sesiones, lesiones | dificultad D, ejecucion E, dismount, mount, pirouette, somersault, salto, tour, leap, bridge, leotard, podium training | leotardo, calceta (gimnastas), magnesia, equipo competencia (cinta, aro, etc.) | IG, FIG, fedecolgim.co |
| 46 | **Patinaje sobre hielo / hockey hielo** | indoor | Artistico, Velocidad, Hockey hielo, Patinaje recreativo | Escasos rinks: Plaza Mayorca/Plaza Imperial Bogota (estacionales), Pedro Causil compitio en Pyongchang 2018 (transicion desde inline) | Sesiones, jumps aterrizados, programas | edge, glide, jump (axel, lutz, flip, loop, salchow, toe loop), spin (camel, layback, sit), spiral, footwork | patines hielo (artistico/hockey/speed), traje, guantes (hockey) | IG, ISU, Olympic Channel |
| 47 | **Pole dance / Pole sport** | indoor | Sport (deportivo), Exotic, Lyrical | Power Pole Bogota, Pole Sport Medellin, multiples estudios mayorca | Figuras dominadas, hold time (segundos), grado, secuencias coreografiadas | invert, hold, climb, spin (fireman, chair, attitude), pose (gemini, scorpion, brass monkey, butterfly, layback), drop, deadlift, ayesha | top sport (top/short), grip aid (no aceites), tubo acero inoxidable o bronce 3.5m+ | IG, IPSF (International Pole Sports Federation) |
| 48 | **Aerial silks / lyra / acrobacias aereas** | indoor | Telas (silks), Lyra (aro), Cuerda lisa, Trapecio | Volare Danza Aerea Envigado, Aerial Dance Bogota, VERTIGO cirKo, MADWOLF Stunt | Figuras dominadas, dropp (caidas), secuencias, fuerza pull-up | hip key, foot lock, single star, double star, scorpion, mermaid, hammock drop, angel, splits, beats, rolls (lyra) | tela (poliester o lycra), arnes (lyra), magnesia o griptape, ropa cubre piel | IG, Cirque (cirque-du-soleil) |
| 49 | **Pilates** | indoor | Mat, Reformer, Tower, Cadillac, Chair, Stott, Clinical | Estudios Pilates en Bogota/Medellin/Cali; mayoria Polestar/Stott/Balanced Body certified | Sesiones, ejercicios dominados, control postural (assessment) | neutral spine, imprint, scoop, C-curve, articulation, powerhouse, controlled, breath, lengthening | Mat (esterilla, magic circle, foam roller), Reformer (carro + resortes + footbar) | IG, PMA, Balanced Body, polestar.education |
| 50 | **Spinning / cycling indoor** | indoor | Spinning resistance, Tabata, Hills, Endurance | Cadenas (Smart Fit, Bodytech, Stark) en todas las ciudades, eventos masivos | Watts promedio, FTP, cadencia (rpm), kcal, distancia simulada | climb, jump, surge, recovery, cadence, resistance, RPE, FTP, hill, sprint | bici spinning estatica, zapatillas SPD (recomendado), botella, toalla | Peloton, IG, Apple Fitness+ |
| 51 | **Funcional / HIIT** | indoor | AMRAP, EMOM, Tabata, Circuit | Estudios funcionales en todas las ciudades, derivado de CrossFit | Sesiones, AMRAP rounds, max reps, peso, conditioning score | AMRAP, EMOM, RFT (rounds for time), thruster, burpee, kettlebell swing, box jump, double under, wall ball | kettlebell, barra, discos, box, comba, balon medicinal, anillas, soga | IG, Train Heroic, Beyond the Whiteboard |
| 52 | **CrossFit** | indoor | Programado WOD diario, Open, Quarterfinals, Games | Boxes en Bogota/Medellin/Cali/Monteria. Colombia Championship 2025 Monteria, Fitland Fitness Festival 2025 Bogota. Brayan Fajardo (CrossFit Games), Camila Quintero, Maria Camila Quintero, Carlos Giraldo, Maria Jose Vargas | Workouts firmados (Murph, Fran, etc.), 1RM (squat, deadlift, press), gimnastica (muscle-up, HSPU), AMRAP | benchmark, AMRAP, EMOM, RFT, RX/scaled, CrossFit Games Open, 1RM, hero WOD, the Girls, snatch complex, BMU (bar muscle-up), ring MU | bota o zapato funcional (Nano/Metcon), wrap, knee sleeves, soga doble under, agarradera | IG, BTWB, SugarWOD, CrossFit Games |

### 1.6 Deportes tradicionales colombianos / culturales

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 53 | **Tejo** | tradicional_co | Tejo profesional (Fedetejo), recreativo, mini-tejo | Deporte nacional (Ley 613/2000), patrimonio cultural inmaterial (Ley 1947/2019). Boyaca/Cundinamarca cuna (Turmeque). Canchas en Bogota | Partidos, puntos (mano 1, mecha 3, embocinada 6, monona 9), embocinadas | tejo (disco 680g), bocin, mecha, mano, embocinada, monona, cancha (19.5m x 2.5m) | tejo de plomo, cerveza fria (cultural pero NO recomendable bajo bot militar) | IG, fedetejo.org.co |
| 54 | **Coleo** | tradicional_co | Tradicional, deportivo formalizado | Llanos Orientales (Meta, Casanare, Arauca, Vichada, Guaviare, Cundinamarca via Fedecoleo), patrimonio cultural llanero (Ley 1907/2018) | Vueltas (250m pista), tiempos por coleada, vacas derribadas | manga, tubazo, mocho, coleada, vaquero, mosqueta, pista, cuadrilla | caballo, soga (opcional), atuendo llanero (sombrero, alpargatas) | IG, fedecoleo.com |
| 55 | **Cabalgata / Caballo paso fino** | ecuestre | Paso fino, Trocha, Trote y galope | Federacion Colombiana Asociaciones Equinas (Fedequinas), 28 ferias/ano en Cundinamarca, Exposicion Nacional Equina (feb) | Exposiciones, juzgamientos (paso, tipo, energia, docilidad), criaderos | paso fino, trocha, galope, brio, andadura, tipo, conformacion, monta, lazos | montura, freno, riendas, casco, botas, sombrero | IG, fedequinas.org, suscaballos.com |
| 56 | **Bolos criollos / Mini-tejo** | tradicional_co | Recreativo | Boyaca, Cundinamarca, Caldas | Partidas, puntos | similar tejo escala menor | bolos madera, tejo pequeno | informal |

### 1.7 Deportes ecuestres

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 57 | **Equitacion** | ecuestre | Salto, Doma clasica, Concurso completo, Volteo, Reining | Fedequinas y Federacion Colombiana de Equitacion, clubes en Sabana de Bogota, Cali, Medellin | Saltos limpios, faltas, tiempo recorrido, doma puntuacion, niveles | trote, galope, paso, parada, transitions, half-halt, leg yield, shoulder-in, flying change, salto, oxer, vertical, combinacion | montura inglesa, casco, fusta (riding crop), botas altas, pantalon equitacion (jodhpur), guantes | IG, FEI, fedequinas |
| 58 | **Polo** | ecuestre | (ya cubierto en equipo) | Sabana Bogota, Llanos, Cali | (ver #32) | (ver #32) | (ver #32) | IG |
| 59 | **Endurance ecuestre** | ecuestre | 40K, 80K, 120K, 160K | Llanos, Sabana, eventos esporadicos | Distancia, tiempos por loop, vet check pass, frecuencia cardiaca caballo | loop, vet gate, hold time, recovery time, heart rate, pulse criteria, pace | montura comoda, herraduras tipo trail, cintilla pulso caballo | IG, FEI Endurance |

### 1.8 Acuaticos (incluye natacion especializada)

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 60 | **Natacion deportiva** | acuatico | Libre, Espalda, Pecho, Mariposa, Combinado, Aguas abiertas | Federacion Colombiana Natacion (fecna), PanAm Aquatics Medellin 2025 (CO 84 medallas, sub-campeon) | Tiempos por prueba (50/100/200/400/800/1500), splits, SWOLF, distancia semanal | streamline, flip turn, open turn, catch, pull, kick, breath pattern, drag, SWOLF, set, intervals, descend, broken swim | gorro silicona, gafas, traje (jammer/slip o body), aletas (training), pull buoy, tabla, snorkel frontal | Strava, IG, FINA, fecna.com.co |
| 61 | **Waterpolo** | acuatico | 7v7 | Seleccion CO clasifico U18 Mundial 2026, Juan Areiza mejor arquero PanAm 2025. Liga FECNA | Partidos, goles, asistencias, posicion (centro, ala, defensa, arquero) | egg beater, sculling, dry pass, lob, skip shot, set, drive, kick out, 5m penalty | speedo + reforzado de waterpolo, gorro waterpolo (numerado), balon waterpolo | IG, World Aquatics |
| 62 | **Nado sincronizado / artistico** | acuatico | Solo, Dueto, Equipo, Combo, Highlight, Mixto | CO 6 medallas PanAm 2025 (Melisa Ceballos, Sara Castaneda, Estefania Roa), 5a posicion mundial dueto mixto Singapur 2025 (Emily Minante, Gustavo Sanchez) | Rutinas memorizadas, ejecucion (E), dificultad (D), sincronizacion | egg beater, ballet leg, vertical, walkout, lift, throw, hybrid, transition, expression | banador artistico (lentejuelas), gorro, gelatina pelo, gafas (training), pinza nariz | IG, World Aquatics |
| 63 | **Buceo libre / Apnea** | acuatico | CWT, FIM, CNF, STA (apnea estatica), DYN (dinamica), Spearfishing | Freedive Colombia San Andres (Cristian Castano Villa), Casa de Buceo Santa Marta, Bahia Magdalena, Providencia. Certificaciones AIDA, PADI, CMAS, FII | Profundidad max (m), tiempo apnea (min:seg), distancia DYN (m) | mouthfill, equalization (Frenzel, Mouthfill), pack, residual lung volume, narcosis, LMC, blackout, mammalian dive reflex, packing | mascarilla low volume, snorkel, traje neopreno 3-5mm, aletas largas, plomos, computador apnea | IG, AIDA, freedivecolombia.com |
| 64 | **Buceo deportivo (con tanque)** | acuatico | Recreational (PADI Open Water, AOW, Rescue), Tecnico (Nitrox, Trimix, Cave, Wreck) | Santa Marta (Casa de Buceo PADI), San Andres y Providencia, Cartagena, Capurgana | Inmersiones (numero), profundidad max, tiempo fondo, certificaciones | regulator, BCD, octopus, SPG, depth gauge, dive computer, neutral buoyancy, deco stop, NDL, surface interval | regulador + octopus + SPG, BCD, tanque (aire/EAN32), traje neopreno, mascarilla, snorkel, aletas, computador buceo | IG, PADI, SSI |
| 65 | **Aguas abiertas** | acuatico | 5K, 10K (olimpico), 25K, 36K | Eventos en Cartagena, Santa Marta, San Andres | Distancia (km), tiempo, frecuencia cardiaca, ritmo (min/100m) | sighting, drafting, navigation, wetsuit legal/illegal, feed station, current, swell, chop | gorro, gafas espejadas, traje neopreno (5mm si <18 grados), gel feed | Strava, IG, World Aquatics |

### 1.9 Deportes motorizados

| # | Deporte | Cat | Modalidades | Escena CO | Metrica clave | Vocabulario base | Equipamiento | Plataforma |
|---|---------|-----|-------------|-----------|---------------|------------------|--------------|-----------|
| 66 | **Karting** | motor | Rotax, KZ, Mini, Junior, Senior | Rotax Max Challenge Colombia (rotaxcolombia.com.co), Fedekart, Escuela Colombiana de Karts | Vueltas en pista (tiempos), pole position, podios, licencia | apex, racing line, late apex, draft, slip stream, blocking, kerb, drift, oversteer, understeer | kart, casco con HANS, traje karting, guantes, botas, costillera | IG, Fedekart |
| 67 | **Motocross / Enduro / Velotierra / Motovelocidad** | motor | MX, Enduro, Velotierra, Motovelocidad | Fedemoto, Pista MX Tocancipa, Pista Yamaha Guillermo Escobar (Girardota), validas en Cundinamarca/Tolima/Antioquia/Quindio | Vueltas, podios, tiempos, validas ganadas | start gate, holeshot, whoops, table top, double, triple, scrub, jump face, rut | moto MX/enduro, casco MX, gafas, peto, rodilleras, botas MX, guantes, body armor | IG, fedemoto.org |
| 68 | **Rally** | motor | Rally raid, Rally regularidad, RallyCross | Rally Dakar (colombianos historicos), eventos amateur en CO | Etapas, tiempos, navegacion, abandonos | tripy, road book, special stage, liaison, service, recce, pace notes | auto rally (4x4 o turismo), casco, HANS, road book, GPS Tripy | IG, FIA WRC, Dakar.com |

---

## 2. PROFUNDIZACION: BMX, Skate y Rollers (los 3 deportes urbanos prioritarios)

### 2.1 BMX en Colombia

**Historia y referentes**:
- **Mariana Pajon Londono** (Medellin, 10 oct 1991): la deportista mas condecorada en olimpiadas CO. Oro Londres 2012, oro Rio 2016, plata Tokyo 2020, 9o lugar Paris 2024. 18 mundiales BMX racing, unica sudamericana con 2 oros olimpicos individuales. Empezo a los 4 anos. Esposa de Vincent Pelluard (cicros frances). marianapajon.com
- **Carlos Ramirez Yepes** (Antioquia): 2x bronce olimpico BMX racing (Rio 2016, Tokyo 2020). Cuarto en Mundial Glasgow 2023.

**Modalidades en CO** (Federacion Colombiana de Ciclismo regula):
1. **BMX Racing (olimpico)**: 8 corredores, pista 350-400m con rampas, obstaculos, paralelas. Tiempos 35-45 seg.
2. **BMX Freestyle Park (olimpico desde Tokyo 2020)**: trucos en park de cemento con bowls, rampas, hubbas.
3. **BMX Freestyle Street**: trucos en calle (escaleras, bancos, rampas urbanas).
4. **BMX Freestyle Dirt**: saltos en pista de tierra con trucos en el aire.
5. **BMX Vert**: half-pipe vertical, trucos en aire (asociado X-Games).
6. **BMX Flatland**: en superficie plana, manuales, pivots, rolling tricks (Hexagon, Funky Chicken).

**Pistas oficiales BMX Racing CO**:
- **Bogota**: Pista Carlos Ramirez en Parque Recreo Deportivo El Salitre (sede Panamericano BMX 2026).
- **Cali**: Pista William Jimenez en Pance (sede Copa Nacional GW Shimano 2026, recibe 990 deportistas de 17 ligas).
- **Medellin**: pista oficial (Copa Nacional BMX Racing 2026 regresa despues de 4 anos).
- **Otras ligas BMX**: 17 ligas departamentales activas.

**Skateparks/Freestyle**:
- **Barranquilla**: Skatepark Gran Malecon (nuevo, 2.400 m2, BMX freestyle + skate + roller freestyle).
- **Armenia**: Villa Deportiva Ancizar Lopez (sede Sudamericano BMX Freestyle 2025).

**Calendario 2026**:
- Copa Nacional GW Shimano BMX Racing 2026 (multiples validas: Cali, Medellin, Bogota, etc.)
- Campeonato Panamericano BMX Bogota 30 abr - 3 may 2026 (16 paises).
- Sudamericano BMX Freestyle (sede rotativa).
- Calendario UCI BMX World Cup (Pajon historicamente participa).

**Trick progression BMX freestyle (orden tipico de aprendizaje)**:
1. Manual (rodada en una rueda)
2. Bunny hop (salto sin pedales)
3. 180/360 spin
4. Tabletop (bici horizontal en el aire)
5. X-up (manubrio cruzado 180)
6. No-foot can-can (pierna fuera)
7. Tailwhip (cuadro gira 360)
8. Barspin (manubrio gira 360)
9. Flair (backflip 180)
10. Backflip / Frontflip

**Lesiones BMX (citadas de Scoping Review PMC11556568, 2024)**:
- **Mas comun**: abrasiones/road rash (subreportadas).
- **Fracturas**: clavicula (6-8 sem recuperacion), escafoides muneca (puede requerir cirugia por mal riego sanguineo).
- **Conmoción/TBI**: prevalentes incluso con casco. Fuerzas rotacionales causan dano cerebral sin fractura craneal.
- **AC joint separation** + dislocacion hombro.
- **ACL/MCL** ligamentos (mecanismos no-contacto: torsion, hiperextension).
- **Tobillo/rodilla** esguinces.
- **Contusiones/hematomas** por componentes rigidos de la bici.

**Prevencion BMX**:
- Casco certificado (full-face para racing y high-impact).
- Guantes acolchados, rodilleras + coderas con shell duro.
- Tobilleras (riders con inestabilidad).
- Protector bucal.
- Mangas largas/tela durable.
- Master fundamentals antes de trucos avanzados.
- Mantenimiento bici (frenos, llantas, cadena, tornillos).
- Aprender a caer.

**Influencers/creadores BMX colombianos (referenciar a usuarios)**:
- @marianapajon (Mariana Pajon - oficial)
- @carlosramirezbmx (Carlos Ramirez - cuando esta activo)
- Cuentas de la Federacion Colombiana de Ciclismo @fedeciclismo_col
- Riders freestyle locales con presencia en Reels (mover dentro de la comunidad reels CO via #BMXCO #BMXcolombia)

**Plataformas donde la escena BMX vive**:
- Instagram Reels (#BMX, #BMXLife, #BMXcolombia, #BMXfreestyle)
- YouTube (canales BMX globales y locales)
- TikTok (BMX trick videos)
- Vital BMX (foro y videos internacional)
- Red Bull BMX content
- App Trick Book (tracking trucos)
- Web Federacion Colombiana de Ciclismo: federacioncolombianadeciclismo.com

### 2.2 Skate en Colombia

**Historia y referentes**:
- **Jhancarlos Gonzalez** "Jhanka" (Bogota, 14 mar 1997): skater profesional CO mas exitoso. Stance regular. Compitio en olimpiadas Tokyo 2020 (15o) y Paris 2024 (22o). Oro Dew Tour Street, bronce Mundial Roma 2024, bronce PanAm Santiago 2023, plata Bolivarianos Lima 2025, bronce X Games Ventura 2024. Sponsors: Monster Energy, Vans, Mob Grip, Creature Skateboards, Independent, Bones Wheels.
- **Lourdes Escobar** (femenina destacada Bogota).
- **Mai Alfonso** (skater historica colombiana - Gravedad Zero).
- **Skaters envigadenos** (clase 2026): Jazmin Alvarez Bedoya, Mateo Moreno Martinez, Juan Esteban Garces Perez (club Viga Skateboarding, compiten Mundial Park y Street Sao Paulo 2026).

**Skateparks principales CO**:
- **Medellin** (11 escenarios intervenidos 2026 con $1.610M): Barichara 3, Limonar 1-2, Parque Republica-San Pedro, Ciudad del Rio, Unidad Deportiva Juanes de la Paz, La Floresta, Quintas San Javier, Atanasio Girardot, Francisco Antonio Zea, Santa Lucia. Aranjuez tambien.
- **Bogota**: Fontanar del Rio (festival talento 2025), Salitre, Suba.
- **Cali**: Pance.
- **Barranquilla**: Skatepark Gran Malecon (2.400 m2, bowl tecnica + partidores + 3 zonas modalidad libre).
- **Envigado**: zonas con club Viga.

**Marcas locales colombianas** (citado de Cartel Urbano):
- **Natural Skateboards Co.** (Oscar Rubio Lowenthal "Fresa" - Bogota, 2006, 1a marca CO de tablas).
- **Manual Skateboards** (zapatos y accesorios hechos en CO).
- **Clop Shoes** (2014, planta de 19 trabajadores, patrocina Sebastian Gonzalez).
- **Pleasure** (Mosquera Cundinamarca, zapatos).
- **Flow Griptape** (lijas, 2014).
- **Bumarango** (mencion adicional - skate gear local).

**Modalidades olimpicas**:
- **Street**: trucos sobre obstaculos urbanos (escaleras, bancos, rails, manny pads).
- **Park**: bowls/transition, lineas continuas.

**Trick progression skate (orden tipico)**:
1. Push/cruise + manual
2. Tic-tac, kickturn
3. Ollie (truco fundacional)
4. Shove-it (180 horizontal de la tabla)
5. Pop-shove-it (con ollie)
6. Kickflip (rotacion vertical de la tabla por el toe)
7. Heelflip (rotacion vertical por el heel)
8. Varial kickflip / varial heelflip
9. 180 ollie (frontside / backside)
10. Grind 50/50 (sobre un rail/curb)
11. 5-0 grind (sobre back trucks)
12. Smith grind / Feeble grind
13. Boardslide / Lipslide
14. Tre flip (360 flip)
15. Hardflip / Inward heel

**Lesiones skate** (citado de University of Utah Health):
- **Mas comun**: fracturas de muneca y tobillo.
- Upper extremity (munecas, manos, antebrazos, codos) por caidas.
- Pie/tobillo (esguinces, fracturas).
- **Cabeza**: lesiones por caer hacia atras (esencial casco).
- Esguinces, strain, contusiones, abrasiones.
- US: ~330.000 lesiones combinadas skate+inline/ano (2014), $9B/ano en tratamiento medico.

**Prevencion skate**:
- Casco (esencial para back falls).
- Munequeras (wrist guards) previenen fracturas munequa.
- Rodilleras + coderas reducen severidad.
- Tecnica de caida: rodar, no estirar brazos rectos.
- Calentamiento dinamico 5-10 min.
- Progresion gradual.
- Inspeccionar equipo (rachas, tornillos, ruedas).
- Skateparks > calle/spots inseguros.

**Influencers/creadores skate colombianos**:
- @jhancarlos_gonzalez (Jhanka oficial - presencia X Games / Vans).
- @lourdes_escobar (Lourdes Escobar - femenina referente).
- @vigaskateboarding (club Envigado).
- Marcas locales: @naturalskateboards.co, @manualskateboards, @clopshoes, @pleasureshoes, @flowgriptape.
- Cartel Urbano (revista urbana colombiana cubre skate).

**Plataformas skate**:
- Instagram Reels (#SkateColombia, #SkateboardingColombia, #SkaterCO).
- YouTube (The Berrics, Thrasher, ESPN X Games, locales).
- TikTok (#SkateTricks).
- App Bltz (tracker de trucos con confianza 0-10 y video clips 8 seg).
- App The Trick Book (social network + Trickipedia + spots map).
- Grind Wallet Pro (trick analysis + practice logging).
- Skateboarding Tricks Tracker (web).
- Federacion Colombiana de Patinaje (regula skate post-olimpiadas Tokyo 2020): fedepatin.org.co

### 2.3 Rollers / Patinaje en Colombia

**Colombia es POTENCIA MUNDIAL VERIFICADA en patinaje de carrera** (no es marketing):
- **21 coronas mundiales totales en patinaje de velocidad** (1990-2024).
- **14 mundiales CONSECUTIVOS** (record vigente).
- **240+ medallas de oro** historicas en patinaje (1er deporte CO en medalleria mundial).
- World Skate Games 2024 Italia: 36 medallas patinaje velocidad (20 oro, 10 plata, 6 bronce).

**Glorias colombianas del patinaje** (citado de Radio Nacional + ABC Color + El Tiempo):
- **Cecilia Baena** (Cartagena): icono historico. Primera con 4 titulos mundiales a los 13 anos.
- **Andres Felipe Munoz**: 27 titulos mundiales (mayor medallista masculino en historia patinaje CO).
- **Pedro Causil** (Cartagena): 18 oros mundiales + Panam Lima 2019 (contrarreloj y 500m). Despues compitio en hielo en Olimpiadas Invierno Pyongchang 2018.

**Modalidades** (Federacion Colombiana de Patinaje, fedepatin.org.co):
1. **Patinaje de velocidad/carrera** (potencia CO): pista, ruta, montana. Pruebas: 200m crono, 500m+D, 1000m, 10000m, 15000m, eliminacion, puntos, americana, maraton, contrarreloj.
2. **Patinaje artistico**: figuras, libre, danza, parejas, show.
3. **Patinaje agresivo (inline aggressive)**: tipo skate park con patines. Trucos: soul, royale, mizou, makio, unity, fishbrain.
4. **Roller freestyle skatepark**: jumps + tricks en park.
5. **Freestyle slalom**: figuras con conos (Speed, Classic, Battle, Free Jump).
6. **Hockey en linea** (incluido en Federacion): Liga Nacional + 18 equipos 9 ligas.
7. **Roller derby** (femenino contacto): escena en Bogota/Medellin.
8. **Danza inline**.

**Escenas principales**:
- **Cali**: cuna del patinaje colombiano.
- **Bogota**: Patinodromo El Salitre (epicentro), Parque Simon Bolivar.
- **Medellin**: pista patinaje.
- **Pereira**, **Manizales**, **Guarne** (Antioquia, sede Interligas 2026).
- **Barranquilla**: Malecon (skatepark BMX/skate/roller freestyle).

**Calendario velocidad 2026** (Fedepatin oficial):
- 4-8 feb: 5a Valida Nacional Interclubes mayores Bogota Salitre.
- 19-23 mar: 6a Valida Manizales.
- 24-26 abr: V Torneo Nacional de Transicion Bogota.
- 30 abr - 3 may: VII Valida Interclubes Cali.
- 7-14 jun: Campeonato Nacional Interligas 2026 Guarne Antioquia.
- World Skate Games Asuncion 2026 (clasificatorios).

**Calendario otras modalidades**:
- Hockey linea Interligas 31 jul - 3 ago.
- Roller freestyle nacional (fechas via Fedepatin).
- Inline freestyle continental Chile fines junio (200 puntos ranking internacional).

**Trick progression patinaje agresivo (orden tipico)**:
1. Forward/backward skate, parar
2. Manual / heel-toe manual
3. 180/360 air
4. Grind frontside (soul grind = bota soul slide)
5. Royale grind
6. Mizou
7. Makio
8. Unity (avanzado)
9. Fishbrain (avanzado)
10. Variantes: alleyoop, fakie, topside, grab, switch

**Trick progression freestyle slalom**:
1. One-foot rotations
2. Cross over
3. Snake
4. Sun
5. Eagle
6. Footgun
7. Criss cross

**Metricas speed skating**:
- 200m crono (en patinodromo).
- 500m+D, 1000m, 10000m, maraton.
- Tiempos por vuelta + velocidad media.
- VAM (velocidad ascensional, en montana).

**Lesiones rollers** (Healthy Children + AAOS):
- **MAS COMUN: muneca** (Colles fracture en caidas hacia adelante).
- Cabeza, codos, rodillas, tobillos.
- ACL en agresivo/park.
- Road rash en velocidad (caidas a 50+ km/h).

**Prevencion rollers**:
- Munequeras (esenciales, evitan 80% de fracturas muneca).
- Casco.
- Rodilleras + coderas (agresivo/park).
- Velocidad: traje aerodinamico cubre piel, casco aero.
- Tecnica de caida.

**Influencers/creadores patinaje colombianos**:
- @marianapajon (BMX pero referente cruzado motiva).
- Cuentas Federacion Colombiana Patinaje (@fedepatincol).
- Patinesychuecas.com (medio especializado).
- LS Patina (lspatina.com - tienda + comunidad agresivo).

**Plataformas rollers**:
- Instagram Reels (#PatinajeColombia, #PatinajeVelocidad, #InlineSkating, #AggressiveInline).
- YouTube (World Skate TV, canales locales).
- TikTok.
- Book of Grinds (checklist trucos agresivo).
- Toxboe Trickguide (web grinds variations).
- Centro Slackline Colombia tipo platform (no aplica pero modelo).
- App The Trick Book.

---

## 3. Taxonomia propuesta para `deporte_principal` en la DB

### 3.1 Problema actual

`deporte_principal` es `String(100)` libre. Onboarding sugiere 10 strings: `gimnasio, crossfit, running, futbol, calistenia, natacion, ciclismo, yoga, boxeo, tenis`. No hay enum, no hay validacion, no hay modalidad. Imposible adaptar el prompt del coach a la realidad del deporte.

### 3.2 Solucion propuesta: modelo JSONB jerarquico

Cambiar `deporte_principal` de `String(100)` a `JSONB` (PostgreSQL nativo, soportado por SQLAlchemy via `JSON` column type) con estructura:

```json
{
  "categoria": "urbano",
  "deporte": "bmx",
  "modalidad": "park",
  "nivel": "intermedio",
  "anos_practica": 2,
  "competitivo": false
}
```

**Razon de no usar enum estricto**:
- 67 deportes × ~5 modalidades = 200+ combinaciones. Inmanejable como enum.
- Nuevos deportes apareceran (ej: padel paso de 0 a boom en 3 anos).
- Categoria + deporte como strings validados contra catalog (tabla `deportes_catalog`) permite extension dinamica.

### 3.3 Categorias (enum estricto, son pocas)

```python
class CategoriaDeporte(str, enum.Enum):
    URBANO = "urbano"               # BMX, skate, rollers, parkour, climbing, surf, kite, etc.
    COMBATE = "combate"             # boxeo, BJJ, MMA, muay thai, karate, TKD, judo, etc.
    EQUIPO = "equipo"               # futbol, basket, voley, rugby, beis, ultimate, padel, etc.
    INDIVIDUAL_OUTDOOR = "individual_outdoor"  # trail, triatlon, MTB, ciclismo, atletismo
    INDOOR = "indoor"               # gimnasia, pilates, pole, aerial, spinning, funcional, crossfit
    ECUESTRE = "ecuestre"           # equitacion, polo, endurance, paso fino, coleo
    ACUATICO = "acuatico"           # natacion, waterpolo, sincronizada, apnea, buceo
    MOTOR = "motor"                 # karting, motocross, enduro, rally
    TRADICIONAL_CO = "tradicional_co"  # tejo, bolos criollos
    FUERZA = "fuerza"               # halterofilia, powerlifting (separado por modelo entrenamiento)
    OTRO = "otro"                   # escape hatch para nuevos
```

### 3.4 Tabla `deportes_catalog` (catalogo de referencia)

```sql
CREATE TABLE deportes_catalog (
    id SERIAL PRIMARY KEY,
    slug VARCHAR(64) UNIQUE NOT NULL,  -- "bmx", "skate", "patinaje_velocidad"
    nombre_es VARCHAR(100) NOT NULL,   -- "BMX", "Skateboarding", "Patinaje de velocidad"
    categoria categoria_deporte_enum NOT NULL,
    modalidades JSONB NOT NULL,        -- ["racing", "park", "street", "dirt", "vert", "flatland"]
    metricas_clave JSONB NOT NULL,     -- ["trucos_aterrizados", "sesiones_min", "alturas_m"]
    vocabulario JSONB NOT NULL,        -- {"trucos_basicos": ["bunny_hop","manual"], "avanzados": [...]}
    federacion_url VARCHAR(255),
    plataformas_principales JSONB,     -- ["instagram", "youtube", "vital_bmx"]
    activo BOOLEAN DEFAULT TRUE
);
```

Seed inicial con los 67 deportes de la tabla maestra (seccion 1).

### 3.5 Migracion sugerida (sin perder data existente)

```python
# alembic migration 0003_deporte_jsonb
def upgrade():
    # 1. Crear nuevo campo
    op.add_column("usuarios", sa.Column("deporte_principal_v2", postgresql.JSONB, nullable=True))
    
    # 2. Migrar valores antiguos al nuevo schema
    op.execute("""
    UPDATE usuarios SET deporte_principal_v2 = jsonb_build_object(
        'categoria', CASE deporte_principal
            WHEN 'gimnasio' THEN 'indoor'
            WHEN 'crossfit' THEN 'indoor'
            WHEN 'running' THEN 'individual_outdoor'
            WHEN 'futbol' THEN 'equipo'
            WHEN 'calistenia' THEN 'indoor'
            WHEN 'natacion' THEN 'acuatico'
            WHEN 'ciclismo' THEN 'individual_outdoor'
            WHEN 'yoga' THEN 'indoor'
            WHEN 'boxeo' THEN 'combate'
            WHEN 'tenis' THEN 'equipo'
            ELSE 'otro'
        END,
        'deporte', COALESCE(deporte_principal, 'otro'),
        'modalidad', NULL,
        'nivel', COALESCE(nivel, 'principiante'),
        'competitivo', FALSE
    );
    """)
    
    # 3. Crear catalog
    op.create_table("deportes_catalog", ...)
    # ... seed con los 67 deportes
    
    # 4. (Opcional fase 2) drop columna antigua
    # op.drop_column("usuarios", "deporte_principal")
```

---

## 4. Top 5 adaptaciones TECNICAS necesarias en el bot

### 4.1 PersonalRecord polimorfico (NO solo peso x reps)

**Problema actual**:
```python
class PersonalRecord(Base):
    ejercicio = Column(String(100))
    peso_kg = Column(Float, nullable=False)  # <-- forzosamente peso!
    reps = Column(Integer)
```

Esto no captura: trucos aterrizados (BMX/skate/rollers), altura saltada (parkour), profundidad apnea, grado de via (climbing 5.13a), tiempo (running/swim), distancia (ultras), watts (ciclismo).

**Solucion**: PR polimorfico con campo `tipo_pr` + JSON con metricas tipadas.

```python
class TipoPR(str, enum.Enum):
    PESO_REPS = "peso_reps"           # gym/crossfit/powerlifting (squat 120kg x 5)
    TIEMPO = "tiempo"                 # natacion/running (5K en 22:30)
    DISTANCIA = "distancia"           # ultras (longest run, swim)
    TRUCO = "truco"                   # urbano (1er kickflip aterrizado)
    GRADO = "grado"                   # climbing (1er 5.12a, 1er V5 boulder)
    PROFUNDIDAD = "profundidad"       # apnea (CWT max -22m)
    ALTURA = "altura"                 # parkour/highjump (precision 2m, bunny hop 80cm)
    WATTS = "watts"                   # ciclismo FTP, sprint peak
    VELOCIDAD = "velocidad"           # running pace, skate speed test
    RONDAS = "rondas"                 # AMRAPs CrossFit (Fran 3:45)
    CINTURON = "cinturon"             # BJJ/karate/TKD/judo promociones

class PersonalRecord(Base):
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo_pr = Column(Enum(TipoPR), nullable=False)
    nombre = Column(String(100), nullable=False)  # "kickflip", "squat", "5K", "Suesca via XYZ"
    
    # Metricas (uno o varios, segun tipo_pr)
    peso_kg = Column(Float)        # peso_reps, powerlifting
    reps = Column(Integer)         # peso_reps
    tiempo_seg = Column(Integer)   # tiempo, AMRAPs
    distancia_m = Column(Float)    # distancia, ultras
    grado = Column(String(16))     # climbing "5.12a", "V5", BJJ "azul"
    profundidad_m = Column(Float)  # apnea
    altura_cm = Column(Float)      # bunny hop, salto vertical
    watts = Column(Integer)        # FTP, sprint
    velocidad_kmh = Column(Float)  # speed test
    rondas = Column(Integer)       # AMRAP
    
    # Metadata
    fecha = Column(Date, default=date.today)
    notas = Column(Text)
    video_url = Column(String(500))  # IG reel link o S3 (foto/video del PR)
    spot = Column(String(200))       # "Skatepark Salitre", "Suesca", "Patinodromo Cali"
```

**Logica del coach en `obtener_pr` / `guardar_pr`**:
- Si `deporte.categoria == "urbano"` y user reporta "aterrice mi primer kickflip": guarda `tipo_pr=TRUCO, nombre="kickflip", fecha=hoy, video_url=opcional`.
- Si `deporte.categoria == "fuerza"` y user reporta "squat 120 x 5": `tipo_pr=PESO_REPS, peso_kg=120, reps=5`.
- Si climbing y reporta "envie mi primera 5.12a": `tipo_pr=GRADO, grado="5.12a", spot="Suesca"`.

### 4.2 Nuevos `TipoEjercicio` y SesionEntrenamiento extensible

**Problema actual**:
```python
class TipoEjercicio(str, enum.Enum):
    FUERZA = "fuerza"
    CARDIO = "cardio"
    MOVILIDAD = "movilidad"
    DEPORTE = "deporte"
```

Solo 4 tipos, "deporte" como catch-all es muy pobre. Una sesion de skate de 2h no es "deporte" generico; el bot deberia entender que fueron 2h en park, 4 trucos nuevos intentados, 2 aterrizados, 0 lesiones.

**Solucion**: anadir tipos urbanos + extender `SesionEntrenamiento` con campos opcionales.

```python
class TipoEjercicio(str, enum.Enum):
    FUERZA = "fuerza"
    CARDIO = "cardio"
    MOVILIDAD = "movilidad"
    SKILL = "skill"                # NEW: sesion enfocada en habilidad (truco, tecnica)
    DEPORTE_EQUIPO = "deporte_equipo"  # NEW: partido futbol/basket/voley/etc.
    DEPORTE_COMBATE = "deporte_combate"  # NEW: sparring, randori
    DEPORTE_URBANO = "deporte_urbano"  # NEW: sesion skate/BMX/rollers
    DEPORTE_OUTDOOR = "deporte_outdoor"  # NEW: trail, MTB, climbing
    DEPORTE_ACUATICO = "deporte_acuatico"
    DEPORTE = "deporte"             # mantener para retrocompat

class SesionEntrenamiento(Base):
    # ... existing fields ...
    
    # Nuevos campos opcionales para tracking urbano/skill
    trucos_intentados = Column(Integer)        # 12 intentos de kickflip
    trucos_aterrizados = Column(Integer)       # 3 aterrizados
    trucos_nuevos_logrados = Column(JSON)      # ["kickflip", "shuvit"]
    spot = Column(String(200))                  # "Skatepark Aranjuez"
    
    # Para climbing
    vias_enviadas = Column(JSON)                # [{"nombre": "X", "grado": "5.11a", "estilo": "on_sight"}]
    
    # Para outdoor (trail, MTB, ciclismo)
    distancia_km = Column(Float)
    desnivel_m = Column(Integer)
    velocidad_promedio_kmh = Column(Float)
    
    # Para combate
    rounds_sparring = Column(Integer)
    
    # Comunes
    co_riders = Column(String(200))             # "@usuario1, @usuario2" (social)
    video_session_url = Column(String(500))
```

### 4.3 Coach prompt deporte-aware (REGLA #15 nueva)

Anadir nueva REGLA al system prompt de `src/coach.py` que cambie copy y comportamiento segun `deporte.categoria`:

```
## REGLA #15: COACH DEPORTE-AWARE

Adapta el copy y la metrica que pides segun deporte.categoria del contexto:

**categoria=urbano (BMX, skate, rollers, parkour, climbing, surf, kite)**:
- NO preguntes "cuanto pesaste hoy?" como metrica principal.
- Pregunta: "cuanto rodaste hoy?" (minutos), "que truco lograste?", "filmaste algo?".
- Vocabulario: usa terminos correctos (ollie, kickflip, soul grind, send, bunny hop, manual).
- PR = truco aterrizado por primera vez. Celebra con energia.
- Spot importa: pregunta "donde rodaste?".
- Citation: "vi @marianapajon hacer X" como referente positivo.
- Plataforma: sugiere subir clip a IG Reels, no Strava.

**categoria=combate (boxeo, BJJ, MMA, muay thai, karate, TKD, judo)**:
- Pregunta: "cuantos rounds?", "sparring?", "como sentiste tu cardio?".
- PR puede ser: peso de pelea, nuevo cinturon, sumision aterrizada, primer KO.
- Recovery es CRITICA: trauma cumulativo. Si reporta dolor de cabeza tras sparring duro -> REGLA #13 (TBI screening).

**categoria=equipo (futbol, basket, voley, rugby, beis, ultimate, padel)**:
- Pregunta: "ganaron?", "como jugaste?", "minutos en cancha?".
- PR = goles/asistencias/aces/sets ganados, MVP, primer torneo.
- Volumen = partidos + entrenos por separado.

**categoria=individual_outdoor (trail, triatlon, MTB, ciclismo, atletismo)**:
- Pregunta: "distancia, ritmo, desnivel?".
- PR = nueva distancia, nuevo tiempo, nuevo FTP.
- Strava-like vocabulary. Volumen semanal en horas o km.

**categoria=indoor (CrossFit, gym, pilates, pole, aerial, spinning, funcional)**:
- Mantener el modelo actual del bot: peso x reps, AMRAP rounds, RPE.
- Aqui SI funciona "cuanto squat hiciste?".

**categoria=fuerza (halterofilia, powerlifting)**:
- Pregunta: snatch, clean and jerk, total, attempts (1-3).
- PR = nuevo total, nueva categoria.

**categoria=ecuestre / motor / tradicional_co**:
- Tono mas suave (deportes con menos data, menos dogmatismo).
- Preguntar especificamente: "salieron las exposiciones?", "validas?".
```

### 4.4 Tools nuevas para deportes urbanos

```python
@function_tool
async def registrar_truco_aterrizado(
    telegram_id: int,
    truco: str,             # "kickflip", "bunny_hop", "soul_grind"
    deporte: str,           # "skate", "bmx", "rollers"
    spot: str = "",
    video_url: str = "",
    es_primer_aterrizaje: bool = True,
) -> str:
    """Registra un truco aterrizado por primera vez (NUEVO PR truco).

    Para skate/BMX/rollers, este reemplaza a guardar_pr cuando el PR es de tipo truco.
    Si es_primer_aterrizaje=True, crea un PersonalRecord con tipo_pr=TRUCO.
    Si es repeticion, solo registra el truco en la sesion del dia.
    """
    # ...

@function_tool
async def listar_trucos_dominados(telegram_id: int, deporte: str) -> str:
    """Lista los trucos que el usuario ha aterrizado al menos una vez, agrupados por nivel
    (basico, intermedio, avanzado). Util para coach decir 'te falta intentar tailwhip'."""
    # ...

@function_tool
async def registrar_sesion_urbana(
    telegram_id: int,
    deporte: str,
    duracion_min: int,
    spot: str = "",
    trucos_intentados: int = 0,
    trucos_aterrizados: int = 0,
    co_riders: str = "",
    notas: str = "",
) -> str:
    """Registra una sesion de skate/BMX/rollers/parkour con metricas urbanas."""
    # ...

@function_tool
async def registrar_via_enviada(
    telegram_id: int,
    nombre_via: str,
    grado: str,             # "5.11a", "V4"
    estilo: str,            # "on_sight", "flash", "redpoint", "boulder"
    spot: str,              # "Suesca", "San Gil"
    intentos: int = 1,
) -> str:
    """Registra una via de climbing enviada."""
    # ...
```

### 4.5 Plataforma-aware: integrar IG Reels en lugar de Strava

El bot hoy asume Strava/MyFitnessPal mentality. Para deportes urbanos, la metrica social = IG Reels views, no kudos Strava.

**Implementacion sugerida**:
- En `registrar_truco_aterrizado` aceptar `video_url` (puede ser file_id Telegram, link IG Reels, o S3).
- Tool `compartir_clip_truco` que use `copyMessage` + `KeyboardButton.request_chat` (ya implementado en fase5_copy_pr) para compartir a grupo/chat de su community urbana.
- Sugerir hashtags: `#BMXColombia #SkateColombia #PatinajeCO`.
- Coach copy: en lugar de "subi a Strava", decir "filma y subelo, te lo veo".

---

## 5. Plantillas de mensajes "coach molesto" para BMX, skate y rollers (3 tonos)

Estas plantillas asumen `compromiso='rodar 4 sesiones por semana'` y que el user fallo dia 3.

### 5.1 BMX

**Tono amigable**:
```
Hola Diego, vi que llevas 3 dias sin subir nada al park. Todo bien? 
La bici no se va a entrenar sola para el nuevo bunny hop que dijiste 
que querias clavar este mes. Vamos por una sesion corta hoy, asi sea 
30 min en el patinodromo del Salitre?
```

**Tono firme**:
```
Diego. 3 dias sin rodar. Tu compromiso era 4 sesiones/sem para clavar 
el tailwhip antes del Sudamericano. Hoy es la 4a oportunidad de la 
semana. Pista Carlos Ramirez abre hasta las 8pm. Que hacemos?
```

**Tono militar**:
```
Diego. 3 dias. Cero ruedas. Compromiso roto: 4 sesiones/sem para 
tailwhip. Hoy 5pm, El Salitre. Llevas casco full-face. Filma 10 
intentos. Confirma asistencia. Sin excusas.
```

### 5.2 Skate

**Tono amigable**:
```
Hola Sebas, te he extranado en el park. Hace 3 dias no me cuentas de 
sesion. El kickflip que estabas trabajando se enfria si no le metes 
horas. Que tal hoy en Aranjuez o Ciudad del Rio, asi sean 45 min?
```

**Tono firme**:
```
Sebas, 3 dias sin pisar la tabla. Tu meta era 4 sesiones/sem y 
clavar el tre flip antes del Festival Talento Fontanar. Skatepark 
Salitre abre. Vas o no vas?
```

**Tono militar**:
```
Sebas. 4to dia. Tabla en el closet. Compromiso: 4 sesiones/sem para 
tre flip. Hoy: Salitre, 4pm. 20 intentos minimo, 3 aterrizados o no 
te vas. Confirma.
```

### 5.3 Rollers / Patinaje

**Tono amigable** (speed):
```
Hola Camila, no veo sesion en 3 dias. Sabes que para el 200m por 
debajo de 18s necesitas 4 dias/sem en el patinodromo, no? Hoy en 
El Salitre te toca tecnica de salida + 2 series de 200m. Vamos?
```

**Tono firme** (speed):
```
Camila, 3 dias sin patines. Tu compromiso: 4 sesiones/sem en pista 
para bajar de 18s en 200m antes del Interligas Guarne. La pista no 
viene a tu casa. Hoy 5pm Patinodromo. Que dices?
```

**Tono militar** (speed):
```
Camila. 4to dia parqueada. Compromiso: 4 sesiones/sem, 200m bajo 18s. 
Guarne en 3 semanas. Hoy: Salitre, 5pm. Calientas 15min, 4x200m, 
descanso 3 min. Crono y mandame splits. Confirma.
```

**Tono amigable** (agresivo):
```
Hola Mateo, 3 dias sin spot. El royale a backside soul que estabas 
trabajando necesita horas. Skatepark Malecon en Barranquilla te queda 
cerca o vamos al Salitre? 1h y la armamos.
```

**Tono firme** (agresivo):
```
Mateo, 3 dias sin grindear. Tu compromiso: 4 sesiones/sem para soul 
a royale. Hoy te espero rolando. Confirma spot.
```

**Tono militar** (agresivo):
```
Mateo. 4to dia. Patines secos. Compromiso roto. Hoy: spot, 5pm. 
30 intentos royale + 30 soul. Filma. Cero excusas.
```

---

## 6. Lesiones criticas por deporte urbano (clasificador de crisis del bot)

El clasificador de crisis actual del bot (REGLA #13) detecta TCA, ideacion suicida, RED-S, overtraining. Para deportes urbanos debe ANADIR estas heuristicas:

### 6.1 BMX (alto riesgo concussion + ortopedicos)

**Keywords red-flag** (activar derivacion):
- "me parti la clavicula", "fractura clavicula", "tengo el hombro fuera de lugar"
- "no me acuerdo del golpe", "vi todo borroso", "vomite despues de la caida" -> CONMOCION CEREBRAL
- "no me carga la pierna", "rodilla suelta", "se me dobla la rodilla" -> ACL/MCL
- "muneca rara", "no puedo mover el pulgar" -> ESCAFOIDES (medico ASAP, mal pronostico sin cirugia)

**Mensaje coach (independiente del tono)**:
```
Para. Lo que describes (vomito + dolor de cabeza post-caida) puede 
ser conmocion cerebral. NO vuelvas a montar 7-10 dias minimo. 
Consulta urgencias o medico deportivo hoy. Si pierdes la consciencia 
otra vez, llama al 123. Casco full-face es obligatorio en la 
siguiente sesion.
```

### 6.2 Skate (muneca + tobillo + cabeza)

**Keywords**:
- "muneca rara", "me cai con la mano", "no puedo apoyar la mano" -> COLLES FRACTURE
- "tobillo hinchado", "no puedo caminar", "tobillo morado" -> ESGUINCE GRADO 2-3 o FX
- "me golpee la cabeza", "vi todo brillante", "estuve mareado" -> POSIBLE CONCUSSION
- "no levanto el brazo", "se me salio el hombro" -> LUXACION

**Mensaje coach**:
```
Pausa skate inmediato. Lo de la muneca + caer con la mano 
extendida es señal clasica de fractura. Hielo, inmoviliza con 
algo, urgencias. NO intentes ollie hasta que te vea un ortopedista. 
Compromiso pausado, salud primero.
```

### 6.3 Rollers (muneca extrema, ACL agresivo)

**Keywords**:
- "muneca", "me cai patinando", "tengo la muneca morada" -> MUY FRECUENTE FX MUNECA
- "rodilla", "se solto", "torcida en grind" -> ACL/MCL (agresivo)
- "caderas", "cai en bajada", "rasguno enorme" -> ROAD RASH (speed)

**Mensaje coach**:
```
Las munecas en rollers son la lesion #1. Si no la puedes mover sin 
dolor, es fractura hasta que un medico diga lo contrario. Urgencias. 
Y la proxima sesion: NO MAS PATINES SIN MUNEQUERAS. Te las consigo 
en la Federacion o en LS Patina.
```

### 6.4 Implementacion en codigo

Anadir a `src/coach.py` o nueva tool `clasificar_lesion_urbana`:

```python
LESIONES_URBANAS_RED_FLAG = {
    "bmx": {
        "concussion": ["no me acuerdo", "borroso", "vomite", "perdi la conciencia", "dolor cabeza"],
        "clavicula": ["clavicula", "no puedo levantar el brazo", "fractura"],
        "acl": ["rodilla suelta", "se me dobla", "se solto la rodilla"],
        "escafoides": ["muneca", "no muevo el pulgar", "escafoides"],
    },
    "skate": {
        "muneca": ["muneca", "cai con la mano", "no apoyo la mano"],
        "tobillo": ["tobillo hinchado", "no camino", "tobillo morado"],
        "concussion": ["golpee la cabeza", "brillante", "mareado"],
        "hombro": ["no levanto el brazo", "se salio el hombro"],
    },
    "rollers": {
        "muneca_fx": ["muneca morada", "muneca dolor", "no muevo la mano"],
        "acl": ["rodilla se solto", "torcida en grind"],
        "road_rash": ["raspon", "rasguno grande", "morado en cadera"],
    },
}
```

---

## 7. Comunidades digitales colombianas por deporte (evangelizacion futura)

### 7.1 BMX

- **Instagram** (oficiales): @fedeciclismo_col (Federacion), @marianapajon, @carlosramirezbmx.
- **Hashtags**: #BMXcolombia, #BMXracing, #BMXfreestyle, #BMXCO.
- **FB groups**: buscar "BMX Colombia", "BMX Bogota", "BMX Medellin".
- **Discord**: pequenos servers regionales (Cali, Bogota).
- **Web oficial**: federacioncolombianadeciclismo.com.

### 7.2 Skate

- **Instagram**: @jhancarlos_gonzalez, @vigaskateboarding, @naturalskateboards.co, @manualskateboards, @clopshoes, @cartelurbanocol.
- **Hashtags**: #SkateColombia, #SkateboardingCO, #SkateCO, #ColombiaSkate.
- **YouTube**: canales locales, Cartel Urbano.
- **FB groups**: "Skate Colombia", "Skaters Bogota", "Skate Medellin".
- **App**: Bltz, The Trick Book (internacionales pero adoptables por scene CO).
- **Web Federacion**: fedepatin.org.co (skateboarding desde 2020 cuando entro a olimpiadas).

### 7.3 Rollers / Patinaje

- **Instagram**: @fedepatincol, @lspatina (agresivo).
- **Hashtags**: #PatinajeColombia, #PatinajeVelocidad, #PatinajeAgresivoCO, #InlineSkatingColombia.
- **Web**: fedepatin.org.co (oficial), patinesychuecas.com (medio).
- **Tiendas activadas**: LS Patina, otras.
- **FB groups**: "Patinaje Colombia", "Patinaje Velocidad", "Inline Aggressive Colombia".

### 7.4 Otros deportes urbanos

| Deporte | Comunidades clave |
|---------|-------------------|
| Climbing | IG #escaladacolombia, Monodedo Colombia (monodedo.com), grupos FB "Escaladores Colombia", "Boulder Bogota", theCrag.com Suesca |
| Surf | IG #surfcolombia, Club del Surf del Choco, surfparaiso.com (CO blog), grupos FB "Surf Nuqui" |
| Parkour | IG @parkourusaquen, Parkour Usaquen academy, Liga Antioquena Gimnasia |
| Slacklining | centroslackline.com, IG @soulline_envigado, FB grupos "Slackline Colombia" |
| Kitesurf | IG @tawikitecabo, TAWI Kite Center (WhatsApp +573104904578) |

### 7.5 Otros deportes (resumen rapido)

| Deporte | Plataformas |
|---------|-------------|
| Padel | IG @fcp_colombia, fcpadel.co (cuando lance), grupos FB "Padel Colombia" |
| BJJ | IG academias (Gracie Colombia, Gracie Barra Colombia, Affinity Studios), Smoothcomp para torneos |
| MMA | IG @ocammcolombia, OCAMM events |
| Trail | Strava clubs Colombia, IG #trailcolombia, ITRA.run |
| Ciclismo | Strava clubs Egan/Nairo fans, IG ciclismo21.com |
| CrossFit | IG boxes locales, Beyond the Whiteboard, SugarWOD |
| Tejo | IG @fedetejo, FB grupos canchas locales (mayoria offline) |
| Coleo | IG @fedecoleo, ferias locales en Llanos |

---

## 8. Calendario tentativo de eventos clave 2026 (para que el bot recuerde al usuario)

### 8.1 Urbanos prioritarios

| Evento | Deporte | Fecha 2026 | Lugar | Importancia |
|--------|---------|------------|-------|-------------|
| Copa Nacional GW Shimano BMX Racing | BMX racing | Multiples validas | Cali (ene), Medellin, Bogota | Nacional |
| Campeonato Panamericano BMX | BMX racing | 30 abr - 3 may | Bogota El Salitre | Continental |
| Sudamericano BMX Freestyle | BMX freestyle | Por anunciar | Sede rotativa | Sudamericano |
| Vans BMX Pro Cup | BMX freestyle | Calendar global | Internacional | Pro tour |
| Mundial Park y Street | Skate | Mar 2026 | Sao Paulo | Mundial |
| World Skateboarding Tour | Skate | Multiples (Italia, Paraguay, Japon) | Internacional | Ruta LA28 |
| Festival Talento Deportivo | Skate | Oct (proyectado) | Bogota Fontanar | Local |
| 5a Valida Nacional Interclubes velocidad | Patinaje velocidad | 4-8 feb | Bogota Salitre | Nacional |
| 6a Valida Nacional | Patinaje velocidad | 19-23 mar | Manizales | Nacional |
| V Torneo Nacional Transicion | Patinaje velocidad | 24-26 abr | Bogota | Nacional |
| VII Valida Interclubes | Patinaje velocidad | 30 abr - 3 may | Cali | Nacional |
| Campeonato Nacional Interligas | Patinaje velocidad | 7-14 jun | Guarne, Antioquia | Nacional |
| World Skate Games | Patinaje velocidad | Por anunciar | Asuncion 2026 | Mundial |
| Interligas Hockey Linea | Hockey linea | 31 jul - 3 ago | Por confirmar | Nacional |

### 8.2 Otros deportes destacados

| Evento | Deporte | Fecha 2026 | Lugar |
|--------|---------|------------|-------|
| Mundial Ciclismo Ruta | Ciclismo | Sep 2026 | Por confirmar |
| Vuelta a Colombia | Ciclismo | Calendario UCI | CO |
| Gran Fondo Egan Bernal | Ciclismo MTB | nov | Zipaquira |
| Columbia Trail Challenge | Trail | nov | Choachi |
| Cordillera Trail Futuro | Trail | feb | Tequendama |
| Ultra Trail Cordillera Oriental | Trail | 2 ago | Duitama (42K) |
| Ultra Valle de Tenza | Trail | oct | Boyaca (55K ultra) |
| Ironman 70.3 Cartagena | Triatlon | 30 nov | Cartagena |
| Colombia Championship CrossFit | CrossFit | abr | Monteria |
| Fitland Fitness Festival | CrossFit | 15-18 ago | Bogota |
| Calendario Fedemoto | MX/Enduro | Multiples | CO |
| Ironman 70.3 LATAM tour | Triatlon | Multiples | LATAM |
| Liga Profesional Beisbol | Beisbol | nov 2025 - ene 2026 | Caribe CO |
| Liga BetPlay Baloncesto | Basket | 2 semestres | CO |
| Liga BetPlay Futbol | Futbol | 2 torneos (Apertura/Finalizacion) | CO |
| Spartan Mundial | OCR | Por anunciar | Internacional |

### 8.3 Tradicionales colombianos

| Evento | Deporte | Fecha |
|--------|---------|-------|
| Festival Tejo | Tejo | Calendario Fedetejo |
| Exposicion Nacional Equina | Paso fino | feb (Girardot, Pereira) |
| Festival Internacional Joropo | Coleo | jun-jul (Villavicencio) |
| Encuentro Anual Criaderos Paso Fino | Caballo paso fino | feb |

---

## 9. Fuentes y referencias

### 9.1 Federaciones y entes oficiales

- **Ministerio del Deporte Colombia**: mindeporte.gov.co
- **BMX**: Federacion Colombiana de Ciclismo - federacioncolombianadeciclismo.com
- **Skate**: Federacion Colombiana de Patinaje - fedepatin.org.co (rama skateboarding)
- **Patinaje**: Federacion Colombiana de Patinaje - fedepatin.org.co
- **Atletismo**: Federacion Colombiana de Atletismo - fecodatle.com
- **Natacion**: Federacion Colombiana de Natacion - fecna.com.co
- **Pesas**: Federacion Colombiana de Levantamiento de Pesas - fedepesascol.com
- **Powerlifting**: Federacion Colombiana de Powerlifting - powerliftingcol.com
- **Triatlon**: Federacion Colombiana de Triatlon
- **Rugby**: colombia.rugby - Liga Bogota ligarugbybogota.com.co
- **Padel**: Federacion Colombiana de Padel (FCP, 2025+) - sede Barranquilla
- **Tejo**: Fedetejo - fedetejo.org.co (Ley 613/2000 deporte nacional)
- **Coleo**: Fedecoleo - fedecoleo.com (Ley 1907/2018 patrimonio llanero)
- **Esgrima**: Federacion Colombiana - fedesgrimacolombia.com
- **Karate, TKD, Judo**: Federaciones nacionales
- **Equitacion**: Federacion Colombiana de Equitacion, Fedequinas (paso fino)
- **Gimnasia**: Federacion Colombiana de Gimnasia - fedecolgim.co
- **Disco Volador (Ultimate)**: FECODV - fecodv.ultimatecentral.com
- **Orientacion**: Federacion Colombiana de Orientacion - orientacion.co
- **OCR**: OCR Colombia - app.ocrcolombia.com, ocrlatam.com
- **MMA**: OCAMM (Asociacion Colombiana de Artes Marciales Mixtas) - ocamm.org
- **Kickboxing**: WAKO Colombia - wako-colombia.org
- **Motociclismo**: Fedemoto - fedemoto.org
- **Karts**: Fedekart, Rotax Max Challenge Colombia - rotaxcolombia.com.co
- **Esqui y Wakeboard**: Fedesqui Colombia - fedesqui.com.co

### 9.2 Atletas referentes (vinculos verificados)

- Mariana Pajon: marianapajon.com, olympics.com/es/atletas/mariana-pajon, olympedia.org/athletes/125006
- Carlos Ramirez: olympics.com (BMX bronze x2)
- Jhancarlos Gonzalez: en.wikipedia.org/wiki/Jhancarlos_Gonz%C3%A1lez, xgames.com/athletes/jhancarlos-gonzalez
- Egan Bernal, Nairo Quintana: olympics.com, infobae.com seleccion CO ruta 2025
- Yuri Alvear: fecoljudo.org.co/yuri-alvear-doble-medallista-olimpica
- Yuberjen Martinez: cobertura medios CO (El Colombiano, El Tiempo)
- Anthony Zambrano: infobae.com (plata 400m Tokio)
- Caterine Ibarguen: oro triple Rio 2016 (historica)
- Maria Isabel Urrutia: primera oro olimpico CO (Sidney 2000, halterofilia)
- Francisco Mosquera: fedepesascol.com
- Pedro Causil, Cecilia Baena, Andres Felipe Munoz (patinaje): radionacional.co/cultura/cinco-glorias-colombianas-del-patinaje-mundial
- Angel Barajas: primer medallista olimpico gimnasia CO (plata Paris 2024)

### 9.3 Medios y blogs especializados Colombia

- **Cartel Urbano**: cartelurbano.com (urbanos, skate, BMX, rave)
- **Gravedad Zero TV**: gravedadzero.tv (skate, BMX, urbanos)
- **Street Art Latam**: streetartlatam.com (urbanos LATAM)
- **MTB Racing**: mtb.racing
- **Match Tenis**: matchtenis.com
- **Pelecanus**: pelecanus.com.co (escalada CO)
- **theCrag**: thecrag.com (escalada global, Suesca)
- **Monodedo**: monodedo.com (escalada CO oficial)

### 9.4 Investigacion academica y prevencion

- BMX Injuries Scoping Review (PMC, 2024): pmc.ncbi.nlm.nih.gov/articles/PMC11556568/
- Skateboarding Epidemiology of Injuries (PMC): pmc.ncbi.nlm.nih.gov/articles/PMC4824795/
- University of Utah Health - Skateboarding Safety
- AAOS - In-line skating and skateboarding safety guidelines
- HealthyChildren.org - Skateboarding and In-Line Skating Safety
- NSC.org - Skateboarding Safety

### 9.5 Apps de tracking (para inspirar diseno del bot)

- **Bltz** (iOS) - skate trick tracker con confianza 0-10 + video clips 8s
- **The Trick Book App** (iOS) - action sports social + Trickipedia + spots map
- **Grind Wallet Pro** - trick analysis + practice logging + equipment cost
- **Skateboarding Tricks Tracker** - web tool jwvbremen.nl/tricks
- **BMX Fitness** - BMX racing especifico, gate starts, lap analytics
- **Book of Grinds** - bookofgrinds.com checklist agresivo
- **Toxboe Trickguide** - toxboe.net/tricks variations
- **Strava** - referencia para outdoor (trail, ciclismo, MTB, triatlon)
- **TrainingPeaks** - triatlon, ciclismo serio
- **Smoothcomp** - BJJ torneos
- **Apple Fitness+** - spinning, funcional
- **Peloton** - spinning indoor

---

## 10. Recomendaciones de implementacion prioritaria para el bot

Si tienes que hacer SOLO 3 cambios para soportar BMX/skate/rollers, son estos:

1. **Cambiar `deporte_principal` a JSONB + catalogo de 67 deportes** (seccion 3). Sin esto, no puedes saber si el usuario es de BMX o de gym, y el coach habla generico.

2. **PR polimorfico** (seccion 4.1). Un truco aterrizado NO es peso x reps. Sin esto, el bot no celebra el PR real del usuario.

3. **REGLA #15 en el coach prompt** (seccion 4.3). Cambiar el copy, vocabulario y metricas que pide segun la categoria del deporte. Sin esto, el bot le habla a un skater con jerga de gym y suena absurdo.

Cambios 4 y 5 (tools urbanas + IG Reels integration) son aditivos y se pueden hacer en una segunda fase.

---

## 11. Apendice: deportes NO listados encontrados durante la investigacion

Deportes practicados en Colombia que vale la pena ANADIR al catalog y no estaban en la lista original:

- **Roller derby** (femenino contacto en patines, escena Bogota/Medellin)
- **Cheerleading deportivo** (competitivo, no solo show)
- **Trampolin** (Liga Antioquena Gimnasia)
- **Ajedrez** (deporte mental, Federacion Colombiana de Ajedrez, escenas activas)
- **Bowling** (Liga Colombiana de Bolos, formato deportivo)
- **Billar** (3 bandas, pool, Federacion Colombiana de Billar)
- **Squash** (clubes en Bogota y Medellin)
- **Racquetball** (escenas pequenas)
- **Bicicross / Pumptrack** (variacion BMX pumptrack)
- **Pelota vasca / Fronton** (escena pequena pero existe)
- **Patinaje en linea downhill** (extremo, escena de aventura)
- **Aquathlon** (corre + nada, mas chico que triatlon)
- **Pickleball** (boom emergente 2024-2026, mezcla tenis+ping pong)
- **Microfutbol / Futbol 5** (deporte recreativo masivo en CO, federacion oficial)
- **Bici crit / Criterium urbano** (eventos ciclismo urbano en Bogota)
- **Mountain board** (skate todo terreno, nicho)
- **Sandboard** (en Tatacoa, La Tatacoa Desert)
- **Hovercraft / drones racing** (deportes esports/RC, emergente)

Total deportes mapeados: **67 base + 18 adicionales = 85 deportes practicables en Colombia**.

---

## 12. ACTUALIZACION 2025-2026 — Datos frescos (refresh investigativo)

> Esta seccion compila informacion adicional verificada en investigacion web mayo 2026 que complementa o precisa la data de las secciones 1-11. Util para mantener el catalog de deportes y los prompts del coach con info al dia.

### 12.1 BMX — Mariana Pajon pista Medellin (detalle tecnico)

La pista que lleva el nombre de Mariana Pajon en Medellin (inaugurada/construida por Alcaldia + INDER, mas de $14.000M COP de inversion) tiene especificaciones tecnicas confirmadas:

- 8.500 m² de ocupacion total.
- Recorrido: 420 m (varones), 380 m (mujeres).
- Rampa de salida: 8 m de altura.
- Diseno: Thomas Ritzenthaler (avalado UCI).

Esto sirve como contexto cuando el bot mencione la pista al usuario antioqueno. Fuente: metropol.gov.co (Area Metropolitana del Valle de Aburra).

### 12.2 BMX Freestyle — Nuevos atletas referentes Colombia (2025-2026)

El BMX Freestyle en Colombia tuvo su primera Copa Nacional oficial organizada por la Federacion Colombiana de Ciclismo en Armenia, Quindio (21 sep 2025), con 68 participantes. Atletas a referenciar en mensajes del coach:

- **Luis Rincon** (Bogota): gano Best Trick en Urban Sessions BMX Brussels (jul 2025) con doble flip aterrizando en rueda delantera. Compite Red Bull Rodando Bogota.
- **Juan Caicedo**: representante CO en Urban Sessions Brussels, 14° lugar; tambien FISE World Series Montpellier (mayo 2025).
- **Queen Villegas y Lizsurley Villegas** (hermanas): lideres femeninas freestyle CO. Queen 10° clasificacion FISE Montpellier (72.45 pts) + plata X Games park freestyle. Lizsurley 12° (68 pts).

Hashtags y referencias para coach: #BMXFreestyleColombia, #LuisRincon, #VillegasSisters.

Fuentes: streetartlatam.com, deportecolombiano.com.co, fatbmx.com, revistamundociclistico.com.

### 12.3 Skate — Datos 2025

- **Campeonato Nacional 2025** (Mosquera, Cundinamarca, mar 2025): Bogota domino con 14 medallas (6 oro, 3 plata, 5 bronce). Jhancarlos Gonzalez y Lourdes Escobar destacaron en open.
- **Festival Talento Deportivo 2025**: Bogota en Parque Fontanar del Rio (Suba), evento que fortalece semilleros.
- **Cali Bowl Pump Track**: nuevo bowl en barrio San Joaquin (Comuna 17), inaugurado sep 2025; epicentro de skate + parkour + breaking.
- **Roma 2025**: Colombia participo en Copa del Mundo WST Roma como parte de la ruta clasificatoria a LA28.

Fuentes: bogota.gov.co, cali.gov.co, fedepatin.org.co/noticias-skateboarding.

### 12.4 Patinaje velocidad — Dominio mundial 2025

- **Mundial Beidaihe China 2025**: Colombia LIDERO el medallero con **50 medallas (28 oro, 9 plata, 13 bronce)**. Italia 2°.
- **World Games Chengdu 2025**: primera medalla oro para CO via **Maria Fernanda Timms Ariza** (vuelta al circuito). Tambien Gabriela Rueda y Jhon Tascon con plata.
- **Atletas a citar como referentes**: Geiny Pajaro (oro 100m carriles mayores fem, 10.612s), Kollin Castro (oro 1000m sprint individual + bronce 100m).

Esto refuerza la frase "Colombia es POTENCIA MUNDIAL verificada en patinaje" en el bot. Fuentes: fedepatin.org.co/resultados-mundiales-de-velocidad, elcolombiano.com, elespectador.com.

### 12.5 Padel — Cifras 2024 actualizadas

Refinamiento de las cifras de la seccion 1.3:

- **2024 reservas pagadas**: $55.000+ millones COP (crecimiento 265% vs 2023).
- **2023 vs 2022**: 870% de crecimiento en alquiler de canchas.
- **Infraestructura actual**: ~500 canchas, 100-160 clubes activos, top 5 Sudamerica.
- **Jugadores activos**: ~70.000 personas regularmente.
- **Medellin**: ~17 canchas en 2022, crecimiento sostenido.
- **Bogota**: saturacion del mercado (algunos cierres) — la oferta supera la demanda en zonas premium.
- **Modelo de negocio**: club 4 canchas factura $90-120M COP/mes con rentabilidad 30-35% (info para evangelistas-emprendedores que usen el bot).
- **Federacion Colombiana de Padel (FCP)**: con personeria juridica oficial 2025, presidida por Daniel Bernal Ricaurte (Alejandro Falla Ramirez como VP).
- **Fabrice Pastor Cup**: Medellin sera parada del A1 Padel Tour mayo 2026.

Fuentes: forbes.co, elcolombiano.com, elinformador.com.co, eltiempo.com.

### 12.6 Trail Running — UTMB Quindio 2025 (distancias confirmadas)

El **Quindio Trail Colombia by UTMB** (Salento, may 2-4, 2025 — y proyectado anual) tiene 5 distancias verificadas:

| Codigo | Nombre | Distancia | D+ |
|--------|--------|-----------|----|
| UBS | Buenavista | 122 km | 6.300 m |
| DCS | Cordoba | 84 km | 4.000 m |
| RCS | Cocora | 53 km | 2.300 m |
| TSS | Santa Rita | 23-24 km | 1.200 m |
| CSS | Salento | 14 km | 550-560 m |

Salento Trail Challenge 2025 (alternativo no UTMB): 2 nov 2025, 42 km, 2.204 m D+.

Esto es importante porque trail/ultra ya es ruta UTMB World Series oficial en Colombia. Fuentes: quindio.utmb.world, werun.world, itra.run.

### 12.7 Halterofilia — Mundial Forde 2025

Colombia en Mundial Halterofilia Forde Noruega 2025 (2-11 oct):

**Delegacion 9 atletas:**
- **Masculino**: Francisco Mosquera (65), Sebastian Olivares (71), Jeison Lopez (88), Jokser Albornoz (94), Marcos Bonilla (94).
- **Femenino**: Yenny Sinisterra (63), Julieth Rodriguez (69), Mari Leivis Sanchez (77), Valeria Rivas (86).

**Resultado total: 12 medallas, 5 en total olimpico**:
- **Oro**: Yeison Lopez (88 kg).
- **Plata**: Julieth Rodriguez (69 kg).
- **Bronce**: Yenny Sinisterra (63 kg), Mari Leivis Sanchez (77 kg), Jokser Albornoz (94 kg).

Antecedentes: Jeison Lopez y Mari Leivis Sanchez son **subcampeones olimpicos Paris 2024**. Sinisterra, Olivares y Bonilla son **campeones panamericanos**. En el Panamericano Cali 2025 se batieron 2 records mundiales con Lopez y Olivares.

Fuentes: poder.com.co, olympics.com, antena2.com.

### 12.8 Muay Thai — FCMT con personeria juridica (NUEVO)

**Federacion Colombiana de Muay Thai (FCMT)** obtuvo personeria juridica del Ministerio del Deporte en **junio 2024**, formalmente reconocida como organismo rector.

**Calendario 2025 verificado**:
- 2a Fecha Nacional: Pereira (Coliseo Cuba), 4-6 jul 2025 — 148 atletas, 13 delegaciones.
- 3a Fecha Nacional: Ibague (Tolima), 31 oct 2025.
- Nacional Juvenil: Caldas, 5-7 sep 2025.

**Selecciones**:
- Categoria Elite 2 convocada para representar CO internacionalmente.
- Panamericano IFMA 2025 Mexico (26-29 sep): CO con 10 atletas, apoyo Mindeporte, preparacion en CAR Bogota.

**Top ligas departamentales** (resultados Pereira 2025): 1° LMTC Caqueta, 2° Vallecaucana, 3° Risaraldense.

Fuente: federacioncolombianademuaythai.com.

### 12.9 BJJ — Datos academia + torneo Medellin Pro 5

- **Checkmat Colombia (Medellin)**: dirigida por Prof. **Alessandro Nagaishi**, cinturon negro 3 grados, 26+ anos experiencia, campeon mundial IBJJF, panam y europeo.
- Ubicacion: Cl. 42 #70-11. Clases gi/no-gi en espanol e ingles.
- Otras academias Medellin: **Affinity Jiu Jitsu** (Poblado), **MMA Colombia** (Comuna 15), **Freestyle Fight Club** (Comuna 7), **Hardcore Family** (Comuna 12).

**Torneo principal 2025**: **Medellin Pro 5 BJJ** (21-22 jun 2025), 385 atletas, transmision Smoothcomp.

**Precio referencia**: $80.000 - $200.000 COP/mes academia. Clases de prueba gratis usualmente disponibles.

Fuentes: co.fitfit.fitness, jiujitsublog.com, heymedellin.com, smoothcomp.com.

### 12.10 Boxeo profesional CO 2025 — Yuberjen Martinez ruta titulo

- **Yuberjen Martinez** (34 anos, Antioquia, plata Rio 2016):
  - Record profesional: **6-0 (6 KOs)** tras vencer en KO 2do round al dominicano Juan "Maravilla" Aguero (Convencion Mundial Boxeo Bogota, oct 2025).
  - **Nov 2025**: firma con **All Star Boxing**, promotora le promete pelea por titulo mundial corto plazo. Primer combate 2026 en serie ESPN Knockout LATAM con titulo regional en juego.
  - **Dual career**: amateur (Juegos Nacionales CO) + profesional simultaneo (legal desde Rio 2016).
  - Liga Antioquena Boxeo: tecnico Abelardo Parra.
  - Nota: **excluido de apoyos Mindeporte desde Suramericanos 2022** (relevante para tono del coach con usuarios de boxeo amateur que enfrentan precariedad).

Fuentes: elcolombiano.com, boxingscene.com, ringmagazine.com.

### 12.11 MTB — Calendario 2025 verificado (Federacion Colombiana Ciclismo)

- **Festival del Ruiz DH1 Manizales** (14-16 feb 2025): el mayor evento downhill de LATAM. 300+ atletas incluyendo top internacionales.
- **Campeonato Nacional Downhill 2025**: 13-16 mar 2025, Caldas (Antioquia).
- **Campeonato Nacional MTB 2025**: 16-20 jul 2025, Zipaquira (Cundinamarca) — XCO, XCC, XCR, XCM, Gymkanas.
- **Copa Nacional MTB 4a Valida**: Manizales (Bosque Popular) — 244 participantes, 6 paises.
- **Panamericano Downhill Temuco 2025**: balance CO oficial publicado por Federacion.

Eventos a integrar en el calendario del bot para usuarios MTB. Fuente: federacioncolombianadeciclismo.com.

### 12.12 Triatlon — Calendario Fedecoltri 2025

| Fecha | Evento | Lugar | Modalidades |
|-------|--------|-------|-------------|
| 28 feb | Morgan Challenge | San Andres | Sprint, Estandar |
| 21-22 mar | Triatlon de la Cana | Palmira | Sprint, Supersprint |
| 25 abr | Reto Opita | Palermo | Duatlon, Sprint, Supersprint |
| 29 may - 1 jun | Panamericano | Darien | Continental |
| 7 jun | Ironman 70.3 | Barranquilla | 70.3 |
| 10-13 jul | Panamericano Duatlon | Cali | Continental |
| 29-30 ago | Triatlon de Verano | Bogota | Duatlon |
| 4-7 sep | Copa Continental | Santa Marta | International |
| 6 sep | Ironman 5150 | Cartagena | 5150 |
| 30 nov | **Ironman 70.3 Cartagena** | Cartagena | 70.3 (9a edicion, ~2.500 competidores 49 paises, USD 441.61) |

Fuente: fedecoltri.com.

### 12.13 Beisbol — Liga Profesional 2025-26 (50a edicion)

- **Equipos (4)**: Caimanes de Barranquilla (campeon), Tigres de Cartagena (subcampeon), Vaqueros de Monteria, Toros de Sincelejo.
- **Calendario**: 28 nov 2025 - 18 ene 2026; 30 juegos/equipo.
- **MVP**: Diego Contreras.
- **Cambio formato**: sin Round Robin tradicional este ano (calendario ajustado por preparacion Seleccion CO Copa Americas, evento que no se realizo).
- **Internacional**: campeon va a **Serie de las Americas 2026** en lugar de Serie del Caribe (problemas economicos).

Fuente: diariodeportes.com.co, elcolombiano.com.

### 12.14 Rugby — Nacional Clubes XVs 2025

- **Sede**: Ibague (13-14 sep 2025).
- **10 clubes, 7+ ligas representadas**: Carneros RC (Bogota), Gatos RC (Medellin), Espartanos RC (Antioquia), Sultanes RC + Juglares RC (Valle), Kaamash RC (Atlantico), Santos Reyes RC (Cesar), Arrieros RC (Risaralda), Boga RC + Halcones RC (Tolima).
- **Premios**: 1° $2.000.000 COP + uniformes + equipo. 2°-3° kits.
- **Campeon 2025**: Gatos de Medellin (citado tolimaonline.com).
- **Federacion Colombiana Rugby (FCR)**: fundada 2010 sede Medellin, 15 ligas regionales, presidida por **Lucas Marroquin Oliveira** (Liga Bogota).

Fuentes: colombia.rugby, ligarugbybogota.com.co, es.wikipedia.org/wiki/Federacion_Colombiana_de_Rugby.

### 12.15 Pole Sport — Nacional 2025 + clasificacion mundial

- **Campeonato Nacional Pole Sport y Aereos IPSF Colombia 2025**: Bogota, 4-6 jul 2025, 140+ presentaciones.
- **Disciplinas**: pole artistico, pole aereo artistico, telas aereas, aro aereo, pole sport.
- **Top academia 2025**: **Unlimited Aerial Sports (Bucaramanga)** — 5 anos consecutivos en Nacional, 6 oros 2025.
- **Atleta destacada**: **Luisana Gamez** (Bucaramanga) — oro Elite Division Junior Pole Sport, clasifico a **Mundial Pole Sport Buenos Aires oct 2025**.
- **Pole Art Colombia 2025** (Medellin): Teatro Comfama, 8-9 ago, comunidad mas inclusiva.
- **Estudio Bogota referente**: Power Pole Studio (acero inoxidable y bronce, polos 3.5m+).

Fuente: ipsfsports.org, vanguardia.com, qhubomedellin.com.

### 12.16 Highline / Slacklining — Urban HighlineFest 2025

- **Urban HighlineFest Col 2025**: PRIMER festival urbano de highline en Colombia.
- Fechas: 17-19 oct 2025.
- Lugar: centro Bogota (entre edificios NEOS y Banco de la Costa).
- Specs: linea de 100 m a 45 m de altura.
- Organizadores: Centro de Slackline Colombia + Slako Colombia (colectivo desde 2012).

**Torneo Pacto del Viento Slackline**: 27-28 sep 2025, Parque Recreo Deportivo El Salitre, modalidades speedline y contactline (novicios e intermedios).

**Spots highline confirmados**: **Farallones de Sutatausa** (rutas "Entre Nativos", "La Ruta del Suta", "El Monstruo", "Sin Excusas" — hasta 70 m drop). **Suesca** (eventos como Curifest). **Teusaquillo** (urbano + Rio Arzobispo).

Fuente: centroslackline.com, vavel.com, cartelurbano.com.

### 12.17 Capoeira — Datos detallados de grupos

- **Grupo de Capoeira Nativos**: 35+ anos en Colombia, primera academia capoeira en Bogota bajo Mestre Aranha, **sedes en 9 paises**. Sitio: capoeiranativos.org.
- **Capoeira Mangalot Medellin** (afiliada Cordao de Ouro): Cl. 45 #79-193, clases todos los grupos etarios, sedes en Sabaneta, Envigado, Bello, Itagui.
- **Instituto de Capoeira Angola Alagbede (ICAA)**: Bogota, direccion CM Fabricio y Mestre Valmir, rodas en Parques Timiza y San Luis.
- **Eventos 2025**: rodas en Plaza Tadeo (feb), clases abiertas conmemoracion Mestre Pastinha (abr), sesiones gratuitas CEFE Chapinero (6 abr).

Fuentes: capoeira-angola-bogota.info, capoeiramedellin.com, capoeiranativos.org, culturarecreacionydeporte.gov.co.

### 12.18 Esgrima — Datos federacion + tradicional afrocolombiana

- **Federacion Colombiana de Esgrima**: clubes activos en Valle (incluido **San Sebastian Club** de Saskia Loretta), Bogota, Antioquia, Caldas, Risaralda, Tolima.
- **Modalidades olimpicas**: florete, espada, sable.
- **Esgrima tradicional**: **machete y bordon** del Valle del Cauca — arte marcial ancestral de comunidades negras colombianas (NO olimpico, patrimonio cultural). Citar como deporte cultural alternativo.

Fuentes: fedesgrimacolombia.com, publico.es.

### 12.19 Karting — Infraestructura Tocancipa actualizada

**Autodromo Tocancipa** (Cundinamarca, via Cajica-Zipaquira) — instalaciones:

| Pista | Specs |
|-------|-------|
| Kartodromo Juan Pablo Montoya | Inaugurado 2002 |
| Pista MX (motocross) | 1.260+ m (reglamento LATAM) |
| Pista 4x4 | 1.220 m |
| Circuito principal | 2.725 m (anti-horario y horario) |

**Eventos**: CNA Automovilismo, San Diego, TC 2000 Colombia, Nacional Motovelocidad, **Rotax Max Challenge Colombia** (con participacion internacional, rotaxcolombia.com.co).

**Escuelas**:
- Escuela de Karts Kartodromo JPM (desde 2011).
- Escuela Colombiana de Karts.
- Escuela ACC (Automovil Club Colombia, representante FIA) — proximo curso 21 mar 2026, $760.000.

**Federacion**: Fedekart Colombia.

Fuente: autodromodetocancipa.com.

### 12.20 Hockey en linea — Domino Bolivar 2025

- **4 anos consecutivos** Bolivar campeon Nacional Interligas Hockey Linea (2022-2025).
- **2025 podio**: 1° Bolivar (2 oro 1 plata), 2° Tolima (1 oro 1 plata), 3° Bogota (1 oro 3 bronce).
- **Sede 2026**: Cali (13-15 jun).
- **Calendario adicional**: Copa Nacional + Copa Futuras Estrellas multiples fechas.

Fuente: fedepatin.org.co/noticias-hockey-linea.

### 12.21 Ultimate Frisbee — Calendario FECODV 2025

- **VI Torneo Nacional Interligas Mayores**: Bogota, 1-4 may 2025. Equipos Bogota, Antioquia, Tolima.
- **Torneo Nacional Interclubes 2025** (categoria femenina): liderado por Macana (6-0), seguido de Aerosoul, Revolution, Bamboo.
- **Modalidades**: open, mixed, women, beach.
- **Federacion**: **Federacion Colombiana de Disco Volador (FECODV)** reconocida por WFDF.

Fuente: fecodv.ultimatecentral.com, polideportes.poligran.edu.co.

### 12.22 Coleo — Reglamento puntual + caballo cuarto de milla

**Federacion Colombiana de Coleo (Fedecoleo)**: 6 ligas (Meta, Cundinamarca, Casanare, Arauca, Vichada, Guaviare). Reconocida por Coldeportes desde 2000.

**Sistema de puntuacion (Copa America 2024)**:
| Tecnica | 1a zona | 2a zona |
|---------|---------|---------|
| Caida de costado | 10 pts | 5 pts |
| Vuelta de campana | 20 pts | 10 pts |
| Vuelta de campanilla | 30 pts | 15 pts |
| **Remolino** (mejor coleada) | 40 pts | 20 pts |

**Caballos**: raza **cuarto de milla** (agilidad/velocidad), recorridos max 250 m. Novillos con microchips y certificados ICA obligatorios.

Fuentes: copaamericadecoleo.com, fedecoleo.com, llanera.com.

### 12.23 Paso Fino Colombiano — Feria Equina Manizales 69 (2025)

- **Feria Equina de Manizales 2025 (69a edicion)**: 19-22 mar 2025, Expoferias, **384 caballos, 174 criaderos**.
- **3 ferias Grado Doble A en Colombia**: Cali, Medellin, Manizales.
- **Gran Campeon 2025**: "Bandido de Santa Maria" (Jorge Hernan Valencia Ulloa).
- **Gran Campeona 2025**: "Culpable de Yerbabuena" (Lucio Barreto Maceto).
- **Juzgamiento**: 3 etapas (calentamiento, prueba individual, recorrido conjunto). Tabla 0-100 (tamano, forma, adiestramiento, movimiento).
- **Paso Fino Colombiano**: declarado **patrimonio genetico nacional** por Congreso CO.

Fuente: lapatria.com, eje21.com.co.

### 12.24 Tejo — Sistema puntuacion detallado

**Reglamento Fedetejo**:
- **Cancha**: 19.5 m de largo × 2.5 m de ancho.
- **Disco (tejo)**: 680 g aprox.
- **Origen**: Muiscas, 500+ anos. Boyaca cuna (Turmeque, Ley 1947/2019).
- **Estados**: deporte nacional CO (Ley 613/2000).

**Puntuacion**:
| Jugada | Puntos |
|--------|--------|
| Mano | 1 |
| Mecha | 3 |
| Embocinada | 6 |
| **Monona** | 9 |

**Modalidades**: individual, duplas, equipos × femenino/masculino/mixto. Variantes: **mini-tejo** (proporciones reducidas), **tecnotejo** (tableros electronicos).

**Expansion internacional**: Venezuela, Ecuador, Peru, Espana, Mexico, USA.

Fuente: es.wikipedia.org/wiki/Tejo_(deporte), encolombia.com.

### 12.25 Buceo deportivo y apnea — Mapa de spots actualizado

**Hubs principales Colombia**:
- **San Andres y Providencia**: islas con visibilidad 25-30m+, comunidad freedive activa (Freedive Colombia, Cristian Castano Villa).
- **Santa Marta** (Magdalena): Casa de Buceo PADI, escuelas multiples.
- **Cartagena**: clubes recreativos, accesible para certificaciones Open Water.
- **Capurgana** (Choco / Caribe): destino emergente.
- **Bahia Solano + Nuqui** (Pacifico): biodiversidad alta, dificultad alta (corrientes).

**Certificaciones reconocidas**: PADI, SSI, NAUI (rec), AIDA, FII, CMAS (apnea).

**Disciplinas apnea**: CWT (constant weight), FIM (free immersion), CNF (constant no fins), STA (estatica), DYN (dinamica), Spearfishing.

### 12.26 Lesiones — Refuerzo cuantitativo investigacion academica

**Estadisticas verificadas para clasificador de crisis** (seccion 6):

**BMX** (Scoping Review PMC, BJSM Suppl 2024):
- **Incidencia**: 4.59 lesiones / 365 dias — **MAYOR de todos los ciclismos**.
- **Distribucion**: 65.21% miembro superior (vs 48.32% ruta, 44.18% pista).
- **Tipos comunes**: fracturas, laceraciones, abrasiones, contusiones.
- **Freestyle especifico** (ScienceDirect): 100% experimentaron lesiones/over-use en 1 ano (n=28). 100% skin/contusiones, 32% distorsiones, 14% fracturas, 7% dislocaciones.
- **Prevencion con neck brace**: reduce aceleraciones rotacionales (efecto cabeza) — relevante en caidas.

**Skate** (1990-2008 US ED data, 10-Year Australian Centre):
- **1.2M ninos/adolescentes** atendidos ED USA en 18 anos, **~64.572 casos/ano**.
- **Demografia**: 89% masculino, 44.9% adolescentes 11-14 anos.
- **Distribucion**: 44.1% extremidad superior, 31.7% extremidad inferior, 32.1% fracturas/dislocaciones.
- **Tobillo/pie**: esguinces #1 en pediatricos.
- **Cabeza**: decrece con edad, **lower extremity INCREMENTA con edad**.
- **Lugar**: 37.3% en casa, 29.3% calles/highways.

**Inline/roller** (PMC 10510356, 20-year retrospective):
- **Muneca**: **1 de cada 4 lesiones es fractura de muneca** (Colles).
- **Demografia**: edad pico 10-14 anos.
- **Mecanismo**: caida frontal con manos extendidas como reflejo.
- **Severidad**: hay muertes reportadas (raras pero existen).
- **Prevencion**: munequeras + casco + rodilleras + coderas — **80% reduccion estimada en lesiones muneca con munequeras** segun BJSM 1999.

**Implicacion para el bot**: el clasificador de crisis (REGLA #13) debe activarse FUERTEMENTE en deportes urbanos con keywords de muneca/cabeza/clavicula porque la base estadistica de incidencia es ALTA y la edad pico (10-14) coincide con usuarios menores que requieren auto-downgrade pedagogico.

Fuentes:
- pmc.ncbi.nlm.nih.gov/articles/PMC11556568 (BMX Scoping Review 2024)
- bjsm.bmj.com/content/55/Suppl_1/A81.1 (BMX BJSM)
- pubmed.ncbi.nlm.nih.gov/40692620 (Cycling injury meta-analysis 2024)
- link.springer.com/article/10.1186/s40621-016-0075-6 (Skate ED 1990-2008)
- pmc.ncbi.nlm.nih.gov/articles/PMC10995764 (Skate 10-year Australian)
- pmc.ncbi.nlm.nih.gov/articles/PMC10510356 (Inline/Roller 20-year)
- bjsm.bmj.com/content/21/3/125 (Roller skating dangerous?)
- pubmed.ncbi.nlm.nih.gov/10593645 (Inline injury prevention)

### 12.27 Otras escenas urbanas — Scooter freestyle + parkour Bogota

**Scooter freestyle Bogota** (IDRD oficial):
- 10 localidades con escenarios administrados IDRD.
- Spots: El Tunal, Unidad Deportiva El Salitre, San Cristobal, Villas de Granada, Fontanar del Rio.
- Trucos basicos (Street Art Latam): Ollie, Nollie, Body spins (180-720), Grinds, Barspin, Tailwhip, Manual, Nose Manual, Hellwhip.

**Parkour Bogota** (Cartel Urbano):
- **40+ grupos** activos en la ciudad.
- Grupos referencia: Les Chats, Familia Aire (Engativa), Tamashikaze (Kennedy), Plus Parkour (la 80), Estilo Urbano.
- Spots: Parque Lago Timiza, Simon Bolivar, Parque Nacional, Parque la Independencia, Universidad Nacional.

**Parkour Medellin**: Parkour Crew Medellin (Juan David Vargas Cardona, 10+ anos).

Fuentes: cartelurbano.com, idrd.gov.co, streetartlatam.com.

### 12.28 SUP / Wakeboard — Spots Colombia (Calima como hub)

**Lago Calima** (Valle, 2h de Cali, 45 min Buga):
- 70 km², 19°C agua, vientos consistentes 15-25 nudos.
- "El brujo" (viento PM intenso): mananas SUP ideales, tardes kite.
- Escuelas: Calima Kitesurf School, Turismo Calima Colombia.
- SUP, foiling, wing foil, kite (entre mejores del mundo).

**Cartagena (La Boquilla)**:
- Agua 27-29°C, side-shore winds.
- Escuelas IKO: En Colombia Kitesurf ($25 USD/h), **Nomad Kitesurf Colombia** (Lvl 3 instructor — anunciada cierre 2025).

**Temporada kite Caribe CO**: dic-mayo principal, jul-ago bueno en Guajira.

Fuentes: tomplanmytrip.com, encolombiakitesurf.com, calimakitesurf.com, kitesurfinghome.com.

### 12.29 CrossFit boxes Colombia — Mapa actualizado

**Bogota** (primeras affiliated):
- **CrossFit Bogota** (Cra 13 86A-51): **PRIMERA box afiliada CO**, fundada 2008. Drop-in $50K, mensual unlimited $430K COP.
- **Mapana CrossFit** (Cra 16 #90-47): "NO EGO JUST FLOW", fundada 2011, head coach TABO.
- **ETDC Box CrossFit** (Av Cl 68 #58-22).

**Medellin**:
- **BullBox Mde CrossFit** (Cra 43G #25A-50).

Multiples atletas CO registrados **CrossFit Games Open 2026** en open/age groups, masculino/femenino.

Fuentes: games.crossfit.com/affiliate/{16103,30189,652,29712}.

### 12.30 Calistenia / Street Workout Bogota — Parques verificados

**Parques con barras instaladas (Calisthenics Parks)**:
1. **Parque Metropolitano Simon Bolivar** (Spot 8177): dominadas + horizontal + paralelas + abdominales.
2. **Parque Zonal Fontanar del Rio** (Spot 1974): completo, iluminado, cerca pista atletica.
3. **Rio Negro Cl 87** (Spot 1979): tranquilo, torneos street workout, iluminado.
4. **Biblioteca Julio Mario Santo Domingo** (Spot 8180).

No hay federacion oficial CO de calistenia (escenas autoorganizadas).

Fuente: calisthenics-parks.com.

### 12.31 Nado sincronizado + Waterpolo — Calendario FECNA 2026

**Natacion artistica calendario 2026**:
- Nacional Interligas: 24-26 abr, Pereira.
- Nacional Interclubes I: 26-28 jun, Cali.
- Festival Nacional Novatos: 1-3 nov, Ibague.
- Campeonato Nacional Interclubes II: 4-8 nov, Ibague.

**Waterpolo**: Nacional Interligas 31 jul - 3 ago 2025 Cali (Sub-15 y Sub-18, clasificatorio Suramericano Rio 2025).

**Club referente sincronizado**: **Club de Nado Sincronizado Ciudad de Cali** — 40+ anos (fundado 1979), ~100 deportistas 6-25 anos, campeon Nacional Interclubes vigente.

**Infraestructura Bogota**: **Complejo Acuatico Simon Bolivar** — 1.500 espectadores, piscinas olimpica + semiolimpica + clavados + recreativa.

Fuentes: fecna.com.co, synchrocali.com.

### 12.32 Resumen de actualizaciones criticas para el bot

**Cambios MAYORES recomendados al catalogo de deportes** tras este refresh:
1. **BMX**: anadir Copa Nacional Freestyle como evento valido (no solo racing). Atletas freestyle Villegas y Rincon como referentes.
2. **Patinaje**: actualizar "21 mundiales totales" a "21 mundiales totales + dominio reciente 2025 con 50 medallas en Beidaihe China".
3. **Padel**: federacion oficial **constituida 2025** (FCP) — antes era informal.
4. **Muay Thai**: federacion **oficializada 2024** (FCMT). Es nuevo en el sistema deportivo nacional.
5. **Halterofilia**: medallas oficiales Forde 2025 — citar a Yeison Lopez, Sinisterra como referentes recientes.
6. **Trail**: integrar UTMB Quindio como evento internacional de Colombia.
7. **Lesiones urbanas**: actualizar el clasificador de crisis con keywords/estadisticas frescas de revisiones 2024.

**Cambios sin impacto en catalogo, solo data fresca**:
- Equipos beisbol 2025-26.
- Calendarios MTB/Triatlon/Hockey linea 2026.
- Atletas individuales referentes (Yuberjen Martinez 6-0, Caicedo, Villegas, Rincon, Causil, etc.).

### 12.33 Fuentes adicionales investigacion 2025-2026

| Tema | URL clave |
|------|-----------|
| BMX Pista Mariana Pajon | metropol.gov.co/Paginas/Noticias/mariana-pajon-reconocio-la-pista-que-llevara-su-nombre.aspx |
| BMX Panamericano 2026 | federacioncolombianadeciclismo.com/bogota-lista-para-recibir-el-campeonato-panamericano-de-bmx-2026 |
| Patinaje Mundial 2025 China | elespectador.com/deportes/mas-deportes/asi-va-el-medallero-del-mundial-de-patinaje-2025 |
| Skate Festival 2025 | bogota.gov.co/mi-ciudad/cultura-recreacion-y-deporte/bogota-impulsa-el-skateboard-con-el-festival-talento-deportivo-2025 |
| Skate Mundial Roma 2025 | fedepatin.org.co/noticias-skateboarding/colombia-lista-para-la-copa-del-mundo-de-skateboarding-roma-2025 |
| Padel Boom 2024 | forbes.co/2025/04/08/negocios/asi-avanza-la-expansion-del-negocio-del-padel-en-colombia |
| FCP Padel oficial | elinformador.com.co/index.php/deportes/118-deportes-nacional/345116-el-padel-se-suma-oficialmente-al-sistema-nacional-del-deporte |
| Muay Thai FCMT | federacioncolombianademuaythai.com |
| BJJ Medellin Pro 5 | smoothcomp.com/en/event/22529 |
| Trail UTMB Quindio | quindio.utmb.world/races/CSS |
| Halterofilia Mundial 2025 | olympics.com/es/noticias/mundial-levantamiento-pesas-2025-medallero-podios-resultados |
| Yuberjen All Star Boxing | boxingscene.com/articles/yuberjen-martinez-2-time-olympian-signs-with-all-star-boxing-eyes-title-run-in-2026 |
| Rugby Nacional 2025 | colombia.rugby/ibague-recibe-el-nacional-de-clubes-xvs-masculino-2025 |
| Pole Sport 2025 | vanguardia.com/deportes/otros-deportes/2025/07/08/el-talento-santandereano-brilla-en-el-nacional-de-pole-sport-y-aereos-y-asegura-presencia-en-el-mundial |
| Slackline Urban HighlineFest | vavel.com/mx/polideportivo-mx/2025/10/21/1238491-el-urban-highlinefest-col-2025-sorprendio-desde-las-alturas-a-los-bogotanos |
| Ultimate FECODV 2025 | polideportes.poligran.edu.co/2025/05/19/ultimate-frisbee-colombia |
| Tejo reglamento | es.wikipedia.org/wiki/Tejo_(deporte) |
| Coleo reglamento | copaamericadecoleo.com/reglamento |
| Paso Fino Manizales 2025 | lapatria.com/entretenimiento/ellos-son-los-campeones-de-la-69-feria-equina-de-manizales-participaron-384 |
| Hockey Linea 2025 | fedepatin.org.co/noticias-hockey-linea |
| BMX Freestyle riders CO | streetartlatam.com/articulo/villegas-caicedo-y-rincon-pusieron-a-colombia-en-lo-mas-alto-del-bmx-freestyle/1017 |
| Calistenia Bogota spots | calisthenics-parks.com/spots/8177-es-gimnasio-al-aire-libre-bogota-barras-parque-metropolitano-simon-bolivar |
| BJJ skill injury research | pmc.ncbi.nlm.nih.gov/articles/PMC11556568 (BMX), PMC10510356 (rollers), PMC10995764 (skate) |

---

*Seccion 12 anadida en refresh investigativo mayo 2026. Triangulada con fuentes oficiales (federaciones, alcaldias) + medios deportivos colombianos + research academica.*
