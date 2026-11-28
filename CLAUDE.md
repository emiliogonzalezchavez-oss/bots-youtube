# bots-youtube — contexto para Claude

El dueño es "sorbepenes" (español, respuestas cortas y claras; cuando pida aprender algo, muchos pasos detallados).
Nada de pagar servicios; todo corre 100% en la nube (GitHub Actions, repo público = minutos ilimitados).

## Edits de coches (edits/)
Edits verticales 1080x1920 de coches renderizados en Blender 4.2 (Cycles CPU) que deben ser **indistinguibles de la realidad**.
Regla del dueño: si un modelo no es lo bastante bueno para verse real, NO se usa. NUNCA texto ni emojis en el edit.

- `blender_edit.py`: escena (estudio negro con piso pulido + HDRI de estudio solo para reflejos, o exterior con HDRI).
  Livery (`LIVERIES`), luces del coche (`luz_mat`), tomas (`toma()`), llantas apoyadas en el piso.
- `plan.py`: corta la música en el tramo con más energía y arma tomas al ritmo (ráfagas, flashes, punch).
- `montar.sh`: une tomas, grade (teal/calido/mono), viñeta, grano; final < 100 MB.
- `modelos.json`: modelos de Sketchfab aprobados/rechazados (solo CC BY / CC BY-SA, crédito en la descripción),
  `girar`, overrides `mats` y `estilos` (versiones modificadas investigadas de cada coche).
- Workflows: `edits.yml` (edit completo, render en paralelo por pedazos de 12 frames, ~2 h), `revisar_modelos.yml`
  (stills de revisión; inputs `tomas`, `livery=variado`, `variantes` JSON o `dump`), `remontar.yml` (re-montar sin re-renderizar).
- Resultados en la rama huérfana `renders`.

## Reglas aprendidas (no repetir errores)
- Antes de usar un coche nuevo: investigar cómo se ve modificado/deportivo y llenar `estilos` en modelos.json.
- Revisar SIEMPRE de cerca: faros/calaveras (micas = vidrio transparente, solo brillan LEDs/DRL, direccionales y reversa
  apagadas, rojo puro sin rosa), reflejos de la pintura (no plástico, no lavada), llantas tocando el piso, cámara nunca dentro del coche.
- Realismo obligatorio (pedido del dueño): ciclorama curvo (sin línea de horizonte), softboxes con forma/degradado en los
  reflejos (tarjetas), orange peel + swirls en la laca, polvo en llantas y brake dust, huellas en el piso, ventanas que dejan
  ver el interior, llantas aplastadas con sombra de contacto (AO), ruedas delanteras giradas, DOF real, sin brillos quemados
  planos, acabado con grano + aberración cromática + viñeteo (post_foto.py en stills, montar.sh en video), JPG con EXIF.
- Look estudio: exposición -0.5, luces x0.6, HDRI de estudio fuerza 1.0, AgX Punchy con livery.
- No meter contraseñas/tokens en webs; el dueño pega los secretos él mismo.

## Canal
Los edits van al canal **Nightshift Garage** (@nightshiftgaragecars, antes The Fact Bomb, channelId UC6GXUQtQ-lVfBJMBwoRAPDw).
Se sube con `subir.py factbomb ...` del repo privado bot-youtube (secret TOKEN_FACTBOMB). Logo y banner en `marca/`.
Crédito CC BY de cada modelo en la descripción de cada video. Las llantas reales vienen de "[FREE] Sport Tire Pack - by SDC"
(Sketchfab 07ffafa14c0348738edff992999511f9, CC BY): también va en el crédito.
- Llantas: `cambiar_llantas()` reemplaza las llantas del modelo por la del pack (ajuste radial talón→exterior + ancho);
  `ruedas_reales()` pone pasarruedas, calipers de color, disco de acero y los 4 rines iguales.
