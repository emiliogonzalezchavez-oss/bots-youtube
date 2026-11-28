"""Corre en la PC: baja la lista de edits encontrados (rama renders), mide los que faltan con tu internet de casa
y deja todo en resultados.zip para que Claude lo suba. Se puede cerrar y volver a abrir: sigue donde se quedó.
"""
import json, os, subprocess, sys, time, urllib.request, zipfile

try:
    import cv2  # noqa
except ImportError:   # scenedetect nuevo ya no trae opencv
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "opencv-python-headless"], check=True)
try:
    import shazamio  # noqa
except ImportError:
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "shazamio"])
    print("shazamio:", "instalado" if r.returncode == 0 else "no se pudo instalar (sigo sin reconocer canciones)")
AQUI = os.path.dirname(os.path.abspath(__file__))
for _f in ("reconocer.py", "yunet.onnx"):   # módulo de Shazam y detector de caras
    if _f == "yunet.onnx" and os.path.exists(os.path.join(AQUI, _f)):
        continue
    try:
        urllib.request.urlretrieve("https://raw.githubusercontent.com/emiliogonzalezchavez-oss/bots-youtube/main/edits/analisis/" + _f,
                                   os.path.join(AQUI, _f))
    except Exception as e:
        print("no pude bajar", _f, e)
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
for f in os.listdir(FEAT):   # borrar resultados rotos (de una corrida que falló)
    if f.endswith(".json"):
        try:
            d = json.load(open(os.path.join(FEAT, f), encoding="utf-8"))
            borrar = d.get("etapa") == "analisis"   # falló por bug del analizador: reintentar
            borrar |= "error" not in d and "caras_pct" not in d and os.path.exists(os.path.join(AQUI, "yunet.onnx"))   # medir de nuevo con caras
            borrar |= "shazam_error" in d and not d.get("shazam_titulo")   # Shazam falló sin guardar el audio: medir de nuevo
        except Exception:
            borrar = True
        if borrar:
            os.remove(os.path.join(FEAT, f))
hechos |= {f[:-5] for f in os.listdir(FEAT) if f.endswith(".json")}
import re


def segs(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 999


COCHE_KW = ("car", "cars", "jdm", "supra", "gtr", "r34", "skyline", "rx7", "silvia", "ae86", "nsx", "civic", "bmw", "e30", "m3", "m4", "m5",
            "porsche", "911", "gt3", "ferrari", "lambo", "lamborghini", "huracan", "aventador", "mclaren", "bugatti", "koenigsegg",
            "pagani", "mustang", "corvette", "camaro", "dodge", "challenger", "charger", "hellcat", "amg", "mercedes", "audi", "rs6",
            "r8", "nissan", "toyota", "honda", "subaru", "wrx", "evo", "mazda", "golf", "gti", "drift", "supercar", "hypercar",
            "stance", "rolls", "bentley", "aston", "turbo", "v8", "v10", "v12", "racing", "motorsport", "f1", "tuning", "jdm")


def texto(v):
    return re.findall(r"[a-z0-9]+", (v.get("titulo", "") + " " + " ".join(v.get("tags") or [])).lower())


def es_edit(v):
    return any(w.startswith("edit") for w in texto(v))


def es_coche(v):
    return any(w in COCHE_KW for w in texto(v))


# solo Shorts de coches de hasta 70 s; primero los que dicen "edit", de más a menos vistas
cand = [(k, v) for k, v in vids.items() if k not in hechos and segs(v.get("duracion")) <= 70 and es_coche(v)]
cand.sort(key=lambda kv: (not es_edit(kv[1]), -kv[1].get("vistas", 0)))
pend = [k for k, _ in cand][:int(os.environ.get("LIMITE", "1000000"))]
print(f"\n{len(vids)} edits encontrados, {len(hechos)} ya medidos, {len(pend)} por medir con {PROCESOS} procesos.\n")
procs = []
for i in range(PROCESOS):
    f = os.path.join(AQUI, f"ids_{i}.txt")
    open(f, "w", encoding="utf-8").write("\n".join(pend[i::PROCESOS]))
    env = dict(os.environ, PAUSA="2", PYTHONIOENCODING="utf-8", PYTHONUTF8="1", SHAZAM="1")
    procs.append(subprocess.Popen([sys.executable, os.path.join(AQUI, "analizar.py"), os.path.join(AQUI, "videos.json"),
                                   f, FEAT, "100000"], env=env))


def empacar():
    zp = os.path.join(AQUI, "resultados.zip")
    n = 0
    with zipfile.ZipFile(zp + ".tmp", "w", zipfile.ZIP_DEFLATED) as z:
        for f in os.listdir(FEAT):
            z.write(os.path.join(FEAT, f), f); n += f.endswith(".json")
    os.replace(zp + ".tmp", zp)
    return n


import threading
CLIPS = os.path.join(AQUI, "clips")


def canciones_pendientes(final=False):
    """Reintenta Shazam de uno en uno (sin saturarlo) con los clips guardados y actualiza cada resultado.
    En segundo plano corre mientras haya procesos midiendo; con final=True hace una última pasada."""
    try:
        sys.path.insert(0, AQUI)
        from reconocer import reconocer
    except Exception as e:
        print("Shazam no disponible:", e); return
    while True:
        clips = sorted(os.listdir(CLIPS)) if os.path.isdir(CLIPS) else []
        for c in clips:
            if not final and all(p.poll() is not None for p in procs):
                return
            try:
                vid = c[:-4]; jf = os.path.join(FEAT, vid + ".json")
                r = reconocer(os.path.join(CLIPS, c), intentos=2, espera=15)
                if r is None:
                    time.sleep(60)   # Shazam está frenando: esperar
                    continue
                if not os.path.exists(jf):   # el análisis de ese video todavía no termina: luego
                    continue
                d = json.load(open(jf, encoding="utf-8")); d.pop("shazam_pendiente", None); d.update(r)
                open(jf, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False))
                os.remove(os.path.join(CLIPS, c))
                time.sleep(3)
            except Exception as e:
                print("error con canción", c, e)
        if final or all(p.poll() is not None for p in procs):
            return
        time.sleep(30)


hilo = threading.Thread(target=canciones_pendientes, daemon=True)
hilo.start()
t_zip = time.time()
try:
    while any(p.poll() is None for p in procs):
        time.sleep(20)
        if time.time() - t_zip > 600:   # cada 10 min: así aunque cierres la ventana ya hay resultados
            n = empacar(); t_zip = time.time()
            print(f"\n=== {n} de {len(vids)} edits medidos (resultados.zip actualizado) ===\n", flush=True)
except KeyboardInterrupt:
    print("\nParando...")
    for p in procs:
        p.terminate()
finally:
    hilo.join(timeout=120)
    if os.path.isdir(CLIPS) and os.listdir(CLIPS):
        print(f"Reconociendo {len(os.listdir(CLIPS))} canciones pendientes con Shazam...")
        canciones_pendientes(final=True)
    n = empacar()
    print(f"\nListo: {n} edits medidos en resultados.zip. Avísale a Claude.")
