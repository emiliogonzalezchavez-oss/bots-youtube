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
best, t0 = -1, beats[0]
for b in beats:
    if b + DUR > len(y) / sr - 0.5:
        break
    e = rms[(t_rms >= b) & (t_rms < b + DUR)].mean()
    if e > best:
        best, t0 = e, b
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

plan = {"fps": FPS, "music": mp3, "start": round(float(t0), 3), "tempo": round(tempo, 1),
        "escenario": ESC, "color": COLOR, "exposure": -0.5 if ESC == "estudio" else 0.0,
        "hdri_rot": rnd.randint(0, 359), "shots": shots,
        "livery": (sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else
                   rnd.choice(["gt3_blanco", "guards_red", "miami_blue", "gulf", "negro_oro", "verde_python", "amarillo", "rojo_blanco", "morado", "naranja"]))}
json.dump(plan, open(out, "w"), indent=1)
print(json.dumps(plan))
