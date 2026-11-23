"""Arma el plan del edit: elige el tramo más intenso de la canción y corta las tomas en los beats.
Uso: python plan.py musica.mp3 plan.json [segundos]"""
import json, sys
import librosa
import numpy as np

mp3, out = sys.argv[1], sys.argv[2]
DUR = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0
FPS = 30
y, sr = librosa.load(mp3, sr=22050, mono=True)
tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
tempo = float(np.atleast_1d(tempo)[0])
rms = librosa.feature.rms(y=y)[0]
t_rms = librosa.times_like(rms, sr=sr)
# tramo de DUR segundos con más energía, que empiece en un beat
best, t0 = -1, beats[0]
for b in beats:
    if b + DUR > len(y) / sr - 0.5:
        break
    e = rms[(t_rms >= b) & (t_rms < b + DUR)].mean()
    if e > best:
        best, t0 = e, b
bs = [b - t0 for b in beats if t0 <= b <= t0 + DUR + 0.01]
# cada toma dura 4 beats (o 2 si la canción es lenta), la primera 8 para el reveal
per = 4 if tempo >= 110 else 2
cuts = [0.0]
i = 8 if len(bs) > 12 else per
while i < len(bs):
    cuts.append(bs[i]); i += per
if cuts[-1] < DUR - 0.5:
    cuts.append(min(DUR, bs[-1]))
orden = ["trasera", "faro", "frente34", "perfil", "rueda", "calavera", "cenital", "frente", "faro", "perfil"]
shots = []
for k in range(len(cuts) - 1):
    n = round((cuts[k + 1] - cuts[k]) * FPS)
    if n >= 12:
        shots.append({"name": orden[k % len(orden)], "frames": n})
plan = {"fps": FPS, "music": mp3, "start": round(float(t0), 3), "tempo": round(tempo, 1),
        "shots": shots}
json.dump(plan, open(out, "w"), indent=1)
print(json.dumps(plan))
