"""Corre en la PC: baja la lista de edits encontrados (rama renders), mide los que faltan con tu internet de casa
y deja todo en resultados.zip para que Claude lo suba. Se puede cerrar y volver a abrir: sigue donde se quedó.
"""
import json, os, subprocess, sys, time, urllib.request, zipfile

try:
    import cv2  # noqa
except ImportError:   # scenedetect nuevo ya no trae opencv
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "opencv-python-headless"], check=True)
AQUI = os.path.dirname(os.path.abspath(__file__))
FEAT = os.path.join(AQUI, "feat")
RAW = "https://raw.githubusercontent.com/emiliogonzalezchavez-oss/bots-youtube/renders/analisis/"
PROCESOS = int(os.environ.get("PROCESOS", "4"))
os.makedirs(FEAT, exist_ok=True)


def bajar(nombre):
    try:
        return urllib.request.urlopen(RAW + nombre + f"?t={int(time.time())}", timeout=60).read().decode()
    except Exception as e:
        print("no pude bajar", nombre, e)
        return None


txt = bajar("videos.json")
if not txt:
    sys.exit("No hay lista de videos todavía.")
open(os.path.join(AQUI, "videos.json"), "w", encoding="utf-8").write(txt)
vids = json.loads(txt)
hechos = set((bajar("hechos.txt") or "").split())
hechos |= {f[:-5] for f in os.listdir(FEAT) if f.endswith(".json")}
pend = [k for k, v in sorted(vids.items(), key=lambda kv: -kv[1].get("vistas", 0)) if k not in hechos]
print(f"\n{len(vids)} edits encontrados, {len(hechos)} ya medidos, {len(pend)} por medir con {PROCESOS} procesos.\n")
procs = []
for i in range(PROCESOS):
    f = os.path.join(AQUI, f"ids_{i}.txt")
    open(f, "w").write("\n".join(pend[i::PROCESOS]))
    env = dict(os.environ, PAUSA="2", PYTHONIOENCODING="utf-8")
    procs.append(subprocess.Popen([sys.executable, os.path.join(AQUI, "analizar.py"), os.path.join(AQUI, "videos.json"),
                                   f, FEAT, "100000"], env=env))
try:
    for p in procs:
        p.wait()
except KeyboardInterrupt:
    print("\nParando...")
    for p in procs:
        p.terminate()
finally:
    zp = os.path.join(AQUI, "resultados.zip")
    n = 0
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(FEAT):
            z.write(os.path.join(FEAT, f), f); n += f.endswith(".json")
    print(f"\nListo: {n} edits medidos en resultados.zip. Avísale a Claude.")
