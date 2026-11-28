"""Plan del edit con ritmo de Shorts virales (medido en edits de 1M-112M vistas):
- gancho en el primer medio segundo: ráfaga de 4-6 micro-tomas de ~0.13 s
- ritmo irregular: ráfagas cortas + tomas largas para lucir el coche
- movimiento en cada toma (cámara más rápida, sacudida, coche "manejando")
- flashes y golpes de zoom en los drops (se aplican al montar)
- cierre con el mismo plano general del inicio (loop)
Uso: python plan.py musica.mp3 plan.json [segundos] [escenario] [color] [livery]
"""
import json, random, sys
import librosa
import numpy as np

mp3, out = sys.argv[1], sys.argv[2]
DUR = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
ESC = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else random.choice(["estudio", "exterior"])
COLOR = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else random.choice(["teal", "calido", "mono"])
FPS = 30
rnd = random.Random()

y, sr = librosa.load(mp3, sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
tempo = float(np.atleast_1d(tempo)[0])
rms = librosa.feature.rms(y=y)[0]
t_rms = librosa.times_like(rms, sr=sr)
# DROP: el beat donde el bajo/energía salta más (antes vs después). El edit arranca 4 beats antes
# para que el drop caiga justo en la primera toma larga (flash + punch).
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
graves = S[librosa.fft_frequencies(sr=sr, n_fft=2048) < 150].sum(axis=0)
t_g = librosa.times_like(graves, sr=sr, hop_length=512)
dur_total = len(y) / sr
bl0 = 60 / max(tempo, 60)
VENT = 4 * bl0


def media(arr, t, a, b):
    m = (t >= a) & (t < b)
    return arr[m].mean() if m.any() else 0.0


DROP_BEATS = 4   # rafaga(2) + abre(2) antes de la primera larga
best, t0, t_drop = -1, beats[0], None
for b in beats:
    ini = b - DROP_BEATS * bl0
    if ini < 0 or ini + DUR > dur_total - 0.5:
        continue
    antes = media(graves, t_g, b - VENT, b) + 1e-6
    despues = media(graves, t_g, b, b + VENT)
    salto = (despues / antes) * media(rms, t_rms, b, b + VENT)   # salto fuerte Y que después pegue duro
    if salto > best:
        best, t0, t_drop = salto, min(beats, key=lambda x: abs(x - ini)), b
if t_drop is None:   # canción sin drop claro: tramo con más energía
    for b in beats:
        if b + DUR > dur_total - 0.5:
            break
        e = media(rms, t_rms, b, b + DUR)
        if e > best:
            best, t0 = e, b
print(f"drop en {t_drop}s, edit desde {t0:.2f}s" if t_drop else "sin drop claro", file=sys.stderr)
bs = [b - t0 for b in beats if t0 <= b <= t0 + DUR + 0.01]
bl = float(np.median(np.diff(bs))) if len(bs) > 2 else 60 / max(tempo, 60)

DETALLE = ["faro", "rueda", "calavera", "faro", "rueda_gira"]
LARGAS_E = ["manejo_lado", "trasera", "manejo_frente", "perfil", "frente34", "cenital"]   # estudio
LARGAS_X = ["trasera", "perfil", "frente34", "cenital", "frente", "barrido"]             # exterior
CORTAS = ["empuje", "barrido", "rueda_gira", "frente", "calavera", "faro"]
if ESC == "exterior":
    DETALLE = [d if d != "rueda_gira" else "rueda" for d in DETALLE]
    CORTAS = [c if c != "rueda_gira" else "rueda" for c in CORTAS]
largas = LARGAS_E if ESC == "estudio" else LARGAS_X

shots = []


def add(name, frames, fx=(), mov=1.0, sac=0.0, vel=22.0):
    if frames >= 3:
        shots.append({"name": name, "frames": int(frames), "fx": list(fx), "mov": mov, "sacudida": sac, "vel": vel})


def rafaga(beats_):
    """beats_ beats repartidos en micro-tomas de ~4 frames, la primera con flash"""
    total = round(beats_ * bl * FPS)
    n = max(3, min(6, total // 4))
    tipos = rnd.sample(DETALLE + CORTAS, n)
    for i, tp in enumerate(tipos):
        f = total // n + (1 if i < total % n else 0)
        add(tp, f, fx=["flash"] if i == 0 else [], mov=2.2, sac=0.03)


# Patrón: ráfaga gancho -> plano que abre -> larga (drop con flash+zoom) -> cortas -> ráfaga -> larga -> cortas -> cierre
usado = 0.0
patron = [("rafaga", 2), ("abre", 2), ("larga", 4), ("corta", 1), ("corta", 1), ("rafaga", 1),
          ("larga", 4), ("corta", 2), ("corta", 1), ("corta", 1), ("rafaga", 1), ("larga", 2), ("cierre", 2)]
li = ci = 0
for kind, nb in patron:
    if usado + nb * bl > DUR + 0.01:
        break
    fr = round(nb * bl * FPS)
    if kind == "rafaga":
        rafaga(nb)
    elif kind == "abre":
        add("abre", fr, fx=["punch"], mov=1.0, sac=0.015)
    elif kind == "larga":
        add(largas[li % len(largas)], fr, fx=["flash", "punch"] if li == 0 else ["punch"], mov=1.6, sac=0.02); li += 1
    elif kind == "corta":
        add(CORTAS[ci % len(CORTAS)], fr, fx=["punch"], mov=2.0, sac=0.035); ci += 1
    elif kind == "cierre":
        add("abre", fr, mov=1.0, sac=0.01)
    usado += nb * bl

plan = {"fps": FPS, "music": mp3, "start": round(float(t0), 3), "tempo": round(tempo, 1), "drop": round(float(t_drop - t0), 3) if t_drop else None,
        "escenario": ESC, "color": COLOR, "exposure": -0.5 if ESC == "estudio" else 0.0,
        "hdri_rot": rnd.randint(0, 359), "shots": shots,
        "livery": (sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else
                   rnd.choice(["gt3_blanco", "guards_red", "miami_blue", "gulf", "negro_oro", "verde_python", "amarillo", "rojo_blanco", "morado", "naranja"]))}
json.dump(plan, open(out, "w"), indent=1)
print(json.dumps(plan))
