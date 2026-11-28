"""Plan del edit con la FÓRMULA medida en 1,933 edits de coches (463 puros, edits/analisis/):
- el DROP cae tarde: ~40% del video y nunca antes de 7 s (5x más vistas que drop antes de 4 s)
- antes del drop: construcción lenta, tomas de ~2 s, cámara tranquila
- ritmo total 0.5-1 corte/s (tomas de 1-2 s), SIN ráfagas de micro-tomas (2.7x más viral)
- CERO flashes (2x más viral)
- cortes en el beat solo 30-50% (más de 60% se ve robótico: 5x menos vistas); el corte del drop sí cae exacto
- duración 16-45 s (por defecto 20 s)
- sin color frío/teal (3x menos vistas): neutro o cálido
- sin loop perfecto: el final no repite el inicio
Uso: python plan.py musica.mp3 plan.json [segundos] [escenario] [color] [livery]
     python plan.py --puntaje musica.mp3 [segundos]   -> imprime qué tan buena es la canción para la fórmula
"""
import json, random, sys
import librosa
import numpy as np

PUNTAJE = sys.argv[1] == "--puntaje"
args = sys.argv[2:] if PUNTAJE else sys.argv[1:]
mp3 = args[0]
out = None if PUNTAJE else args[1]
rest = args[1:] if PUNTAJE else args[2:]
DUR = float(rest[0]) if len(rest) > 0 and rest[0] else 20.0
ESC = rest[1] if len(rest) > 1 and rest[1] else "estudio"
COLOR = rest[2] if len(rest) > 2 and rest[2] else random.choice(["neutro", "calido"])
if COLOR == "teal":   # la fórmula: el color frío baja las vistas
    COLOR = "neutro"
FPS = 30
DROP_FRAC = 0.40
DROP_MIN = 7.0
rnd = random.Random()

y, sr = librosa.load(mp3, sr=22050, mono=True)
dur_total = len(y) / sr
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
tempo = float(np.atleast_1d(tempo)[0])
beats = np.array(beats, dtype=float)
rms = librosa.feature.rms(y=y)[0]
t_rms = librosa.times_like(rms, sr=sr)
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
graves = S[librosa.fft_frequencies(sr=sr, n_fft=2048) < 150].sum(axis=0)
t_g = librosa.times_like(graves, sr=sr, hop_length=512)
bl0 = 60 / max(tempo, 60)
VENT = 4 * bl0


def media(arr, t, a, b):
    m = (t >= a) & (t < b)
    return float(arr[m].mean()) if m.any() else 0.0


# rejilla de puntos de corte: cada beat (en el beat) y la mitad entre beats (fuera del beat)
grid, en_beat = [], []
for i, b in enumerate(beats):
    grid.append(float(b)); en_beat.append(True)
    if i + 1 < len(beats):
        grid.append(float((b + beats[i + 1]) / 2)); en_beat.append(False)
grid = np.array(grid)
DROP_AT = max(DROP_MIN, DROP_FRAC * DUR)

# DROP: el beat con el salto de graves más grande que deje construir ~DROP_AT s antes y tenga energía después
mejor = None
for b in beats:
    ini, fin = b - DROP_AT, b - DROP_AT + DUR
    if ini < 0.3 or fin > dur_total - 0.3:
        continue
    antes = media(graves, t_g, b - VENT, b) + 1e-6
    salto = media(graves, t_g, b, b + VENT) / antes
    energia_despues = media(rms, t_rms, b, b + (DUR - DROP_AT))
    energia_antes = media(rms, t_rms, ini, b) + 1e-6
    p = salto * energia_despues * min(energia_despues / energia_antes, 3.0)
    if mejor is None or p > mejor[0]:
        mejor = (p, float(b), salto, energia_despues / energia_antes)
if mejor is None:
    sys.exit(f"La canción ({dur_total:.0f} s) no deja poner el drop a {DROP_AT:.0f} s con {DUR:.0f} s de edit")
puntaje, t_drop, salto, contraste = mejor
if PUNTAJE:
    print(json.dumps({"puntaje": round(puntaje, 4), "drop_s": round(t_drop, 2), "salto_graves": round(salto, 2),
                      "contraste": round(contraste, 2), "tempo": round(tempo, 1)}))
    sys.exit()

i_drop = int(np.argmin(np.abs(grid - t_drop)))
paso = float(np.median(np.diff(grid)))          # medio beat
n_pre = int(round(DROP_AT / paso))
i0 = i_drop - n_pre
t0 = float(grid[i0])
t_fin = t0 + DUR

DETALLE = ["faro", "rueda", "calavera", "perfil"]
if ESC == "estudio":
    DROP_SHOT = "manejo_frente"
    POST = ["manejo_lado", "frente34", "rueda_gira", "empuje", "perfil", "frente", "cenital", "barrido", "calavera", "faro"]
else:
    DROP_SHOT = "frente"
    POST = ["frente34", "rueda", "empuje", "perfil", "cenital", "barrido", "calavera", "faro"]
FINAL = "trasera"


def armar():
    """Elige los puntos de corte en la rejilla. Antes del drop: tomas de ~2 s; después: ~1-1.5 s.
    Repite hasta que 30-50% de los cortes caigan en el beat (el del drop siempre en el beat)."""
    for _ in range(4000):
        cortes = []
        i = i0
        # construcción: tomas largas que terminan EXACTO en el drop
        while True:
            k = rnd.choice([7, 8, 9])                       # ~2 s
            if i + k >= i_drop - 4:
                cortes.append(i_drop); i = i_drop; break
            i += k; cortes.append(i)
        # después del drop: más rápido pero sin ráfagas
        while True:
            k = rnd.choice([3, 4, 5, 6])                    # ~0.8-1.6 s
            t_sig = grid[i + k] if i + k < len(grid) else 1e9
            if t_sig >= t_fin - 0.8:
                break
            i += k; cortes.append(i)
        tiempos = [grid[c] - t0 for c in cortes]
        n_cortes = len(cortes)
        cps = n_cortes / DUR
        on = np.mean([en_beat[c] for c in cortes])
        largos = np.diff([0.0] + tiempos + [DUR])
        if 0.30 <= on <= 0.50 and 0.5 <= cps <= 1.0 and largos.min() >= 0.7:
            return cortes, tiempos, float(on), cps
    raise SystemExit("no encontré una combinación de cortes que cumpla la fórmula")


cortes, tiempos, frac_beat, cps = armar()
bordes = [0.0] + tiempos + [DUR]
frames = [round(b * FPS) for b in bordes]
shots = []
n_pre_shots = cortes.index(i_drop) + 1                # tomas antes del drop (la siguiente empieza EN el drop)
pre = rnd.sample(DETALLE, k=min(len(DETALLE), n_pre_shots))
while len(pre) < n_pre_shots:
    pre.append(rnd.choice(DETALLE))
post = POST[:]
rnd.shuffle(post)
for j in range(len(bordes) - 1):
    fr = frames[j + 1] - frames[j]
    if j < n_pre_shots:                                  # construcción: cámara tranquila
        shots.append({"name": pre[j], "frames": fr, "fx": [], "mov": 0.9, "sacudida": 0.004, "vel": 18.0})
    elif j == n_pre_shots:                               # EL DROP: corte exacto + golpe de zoom (sin flash)
        shots.append({"name": DROP_SHOT, "frames": fr, "fx": ["punch"], "mov": 1.6, "sacudida": 0.02, "vel": 26.0})
    elif j == len(bordes) - 2:                           # final distinto del inicio (sin loop perfecto)
        shots.append({"name": FINAL, "frames": fr, "fx": [], "mov": 1.1, "sacudida": 0.008, "vel": 22.0})
    else:
        nm = post.pop() if post else rnd.choice(POST)
        if shots and nm == shots[-1]["name"]:
            nm = post.pop() if post else rnd.choice([x for x in POST if x != nm])
        shots.append({"name": nm, "frames": fr, "fx": [], "mov": 1.5, "sacudida": 0.015, "vel": 24.0})

formula = {"duracion_s": DUR, "drop_t": round(t_drop - t0, 2), "drop_pct": round((t_drop - t0) / DUR, 3),
           "cortes": len(cortes), "cortes_por_seg": round(cps, 3), "cortes_en_beat": round(frac_beat, 3),
           "toma_min_s": round(min(np.diff(bordes)), 2), "toma_max_s": round(max(np.diff(bordes)), 2),
           "flashes": sum("flash" in s["fx"] for s in shots), "color": COLOR,
           "loop": shots[0]["name"] == shots[-1]["name"], "tempo": round(tempo, 1)}
plan = {"fps": FPS, "music": mp3, "start": round(t0, 3), "tempo": round(tempo, 1), "drop": formula["drop_t"],
        "escenario": ESC, "color": COLOR, "exposure": -0.5 if ESC == "estudio" else 0.0,
        "hdri_rot": rnd.randint(0, 359), "shots": shots, "formula": formula,
        "livery": (rest[3] if len(rest) > 3 and rest[3] else
                   rnd.choice(["gt3_blanco", "guards_red", "miami_blue", "gulf", "negro_oro", "verde_python", "amarillo", "rojo_blanco", "morado", "naranja"]))}
json.dump(plan, open(out, "w"), indent=1)
print(json.dumps(formula))
print(" | ".join(f"{s['name']}:{s['frames'] / FPS:.2f}s{'*' if s['fx'] else ''}" for s in shots))
