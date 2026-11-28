"""Baja y mide cada edit: cortes, ritmo vs beat, drop, gancho, movimiento, flashes, color, loop, canción.
Uso: python analizar.py videos.json ids.txt salida_dir [minutos_max]
Escribe salida_dir/<id>.json y salida_dir/<id>.jpg (hoja de 8 cuadros).
"""
import json, os, subprocess, sys, tempfile, time, traceback
import cv2
import numpy as np

vids = json.load(open(sys.argv[1], encoding="utf-8"))
ids = [l.strip() for l in open(sys.argv[2], encoding="utf-8") if l.strip()]
OUT = sys.argv[3]
MIN_MAX = float(sys.argv[4]) if len(sys.argv) > 4 else 300
os.makedirs(OUT, exist_ok=True)
t_ini = time.time()
PAUSA = float(os.environ.get("PAUSA", "0"))   # segundos entre descargas (en la PC, para no ser bloqueado)
import shutil
try:
    FFMPEG = shutil.which("ffmpeg") or __import__("imageio_ffmpeg").get_ffmpeg_exe()
except Exception:
    FFMPEG = "ffmpeg"


def bajar(vid, d):
    if os.environ.get("VIDEO_LOCAL"):   # para pruebas: no baja nada
        return os.environ["VIDEO_LOCAL"], {"track": "prueba", "artist": "yo", "fps": 30, "ancho": 1080, "alto": 1920, "descripcion": ""}
    import yt_dlp
    opts = {"format": "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/b", "merge_output_format": "mp4",
            "outtmpl": os.path.join(d, "v.%(ext)s"), "quiet": True, "no_warnings": True, "noplaylist": True,
            "retries": 2, "socket_timeout": 30, "ffmpeg_location": FFMPEG}
    if os.environ.get("YTDLP_COOKIES") and os.path.exists(os.environ["YTDLP_COOKIES"]):
        opts["cookiefile"] = os.environ["YTDLP_COOKIES"]
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(f"https://www.youtube.com/shorts/{vid}", download=True)
    f = next(os.path.join(d, x) for x in os.listdir(d) if x.startswith("v."))
    return f, {"track": info.get("track"), "artist": info.get("artist") or info.get("creator"),
               "fps": info.get("fps"), "ancho": info.get("width"), "alto": info.get("height"),
               "descripcion": (info.get("description") or "")[:500]}


def cortes(path):
    from scenedetect import detect, AdaptiveDetector
    sc = detect(path, AdaptiveDetector(adaptive_threshold=2.6, min_scene_len=3), show_progress=False)
    return [float(s[0].seconds) if hasattr(type(s[0]), "seconds") else s[0].get_seconds() for s in sc[1:]]


def visual(path):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    br, sat, mov, temp, frames = [], [], [], [], []
    prev = None
    while True:
        ok, f = cap.read()
        if not ok:
            break
        s = cv2.resize(f, (90, 160), interpolation=cv2.INTER_AREA)
        hsv = cv2.cvtColor(s, cv2.COLOR_BGR2HSV)
        g = cv2.cvtColor(s, cv2.COLOR_BGR2GRAY).astype(np.float32)
        br.append(float(hsv[..., 2].mean())); sat.append(float(hsv[..., 1].mean()))
        temp.append(float(s[..., 2].mean() - s[..., 0].mean()))   # rojo - azul (+ cálido, - frío/teal)
        mov.append(0.0 if prev is None else float(np.abs(g - prev).mean()))
        prev = g
        frames.append(s)
    cap.release()
    br, mov = np.array(br), np.array(mov)
    n = len(br)
    flashes = 0
    for i in range(1, n - 1):   # pico de brillo corto
        if br[i] - br[i - 1] > 35 and br[i] - br[min(n - 1, i + 3)] > 20:
            flashes += 1
    loop = 0.0
    if n > 2:
        a = cv2.cvtColor(frames[0], cv2.COLOR_BGR2GRAY).flatten().astype(float)
        b = cv2.cvtColor(frames[-1], cv2.COLOR_BGR2GRAY).flatten().astype(float)
        loop = float(np.corrcoef(a, b)[0, 1]) if a.std() > 1 and b.std() > 1 else 0.0
    idx = np.linspace(0, n - 1, 8).astype(int) if n else []
    hoja = np.hstack([frames[i] for i in idx]) if n else None
    return {"fps": fps, "frames": n, "brillo": round(float(br.mean()), 1), "brillo_std": round(float(br.std()), 1),
            "saturacion": round(float(np.mean(sat)), 1), "temperatura": round(float(np.mean(temp)), 1),
            "movimiento": round(float(mov.mean()), 2), "movimiento_p90": round(float(np.percentile(mov, 90)), 2),
            "flashes": flashes, "flashes_por_seg": round(flashes / max(n / fps, 1), 3),
            "negros_pct": round(float((br < 18).mean()), 3), "loop_similitud": round(loop, 3)}, hoja


YUNET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yunet.onnx")


def caras(path):
    """% de cuadros (12 muestras) con una cara visible. Los edits casi no muestran gente; bromas/vlogs sí."""
    if not os.path.exists(YUNET):
        return {}
    det = cv2.FaceDetectorYN.create(YUNET, "", (360, 640), 0.7, 0.3, 50)
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    con = tot = 0
    for i in np.linspace(0, max(n - 1, 0), 12).astype(int):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(i))
        ok, f = cap.read()
        if not ok:
            continue
        h, w = f.shape[:2]
        esc = 640 / max(h, w)
        f = cv2.resize(f, (int(w * esc), int(h * esc)))
        det.setInputSize((f.shape[1], f.shape[0]))
        _, d = det.detect(f)
        tot += 1
        con += d is not None and any(x[2] >= 0.05 * f.shape[1] for x in d)
    cap.release()
    return {"caras_pct": round(con / tot, 3) if tot else None}


def audio(path, cuts, dur):
    import librosa
    wav = path + ".wav"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "22050", wav], check=True)
    y, sr = librosa.load(wav, sr=22050, mono=True)
    if len(y) < sr:
        return {}
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    tempo = float(np.atleast_1d(tempo)[0])
    onsets = librosa.onset.onset_detect(y=y, sr=sr, units="time")
    rms = librosa.feature.rms(y=y)[0]; t_r = librosa.times_like(rms, sr=sr)
    S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
    gr = S[librosa.fft_frequencies(sr=sr, n_fft=2048) < 150].sum(axis=0); t_g = librosa.times_like(gr, sr=sr, hop_length=512)
    V = 4 * 60 / max(tempo, 60)

    def m(a, t, x, z):
        k = (t >= x) & (t < z)
        return float(a[k].mean()) if k.any() else 0.0
    drop, best = None, 0
    for b in beats:
        if b < V * 0.5 or b > dur - 1:
            continue
        s = (m(gr, t_g, b, b + V) / (m(gr, t_g, b - V, b) + 1e-6)) * m(rms, t_r, b, b + V)
        if s > best:
            best, drop = s, float(b)
    salto = (m(gr, t_g, drop, drop + V) / (m(gr, t_g, drop - V, drop) + 1e-6)) if drop is not None else 0

    def cerca(ts, ref, tol):
        if not len(ts) or not len(ref):
            return 0.0
        ref = np.array(ref)
        return float(np.mean([np.min(np.abs(ref - t)) <= tol for t in ts]))
    r = {"tempo": round(tempo, 1), "drop_t": round(drop, 2) if drop is not None else None, "drop_salto": round(salto, 2),
         "drop_pct": round(drop / dur, 3) if drop is not None and dur else None,
         "cortes_en_beat": round(cerca(cuts, beats, 0.08), 3), "cortes_en_onset": round(cerca(cuts, onsets, 0.05), 3),
         "energia_inicio": round(float(m(rms, t_r, 0, 1.5) / (float(rms.mean()) + 1e-6)), 2),
         "corte_en_drop": bool(drop is not None and any(abs(c - drop) < 0.12 for c in cuts))}
    if drop is not None and cuts:
        c = np.array(cuts)
        antes, desp = np.diff(c[c < drop]), np.diff(c[c >= drop])
        r["toma_media_antes_drop"] = round(float(antes.mean()), 3) if len(antes) else None
        r["toma_media_despues_drop"] = round(float(desp.mean()), 3) if len(desp) else None
    return r


seguidos = bugs = 0
CLIPS = os.path.join(os.path.dirname(os.path.abspath(OUT)), "clips")


def shazam(path, drop, dur, vid):
    """Reconoce la canción (12 s alrededor del drop). Si Shazam falla, guarda el clip para reintentar después."""
    try:
        ini = max(0.0, (drop if drop else dur * 0.3) - 2)
        clip = path + ".clip.wav"
        subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", str(ini), "-t", "12", "-i", path, "-ac", "1", "-ar", "16000", clip], check=True)
        if os.environ.get("SHAZAM_DIRECTO") == "1" and os.environ.get("SHAZAM_FALLA") != "1":   # normal: lo reconoce el hilo de pc_runner
            from reconocer import reconocer
            r = reconocer(clip)
            if r:
                return r
        os.makedirs(CLIPS, exist_ok=True)
        shutil.copy(clip, os.path.join(CLIPS, vid + ".wav"))
        return {"shazam_pendiente": True}
    except Exception as e:
        return {"shazam_error": repr(e)[:150]}


for n, vid in enumerate(ids):
    if (time.time() - t_ini) / 60 > MIN_MAX:
        print("tiempo agotado"); break
    if os.path.exists(os.path.join(OUT, vid + ".json")):
        continue
    t0 = time.time()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:   # en Windows a veces el archivo sigue abierto
        etapa = "descarga"
        try:
            path, meta = bajar(vid, d)
            etapa = "analisis"
            cap = cv2.VideoCapture(path)
            dur = cap.get(cv2.CAP_PROP_FRAME_COUNT) / (cap.get(cv2.CAP_PROP_FPS) or 30)
            cap.release()
            cuts = cortes(path)
            vis, hoja = visual(path)
            tomas = np.diff([0.0] + cuts + [dur]) if dur else np.array([])
            feat = {"id": vid, "duracion_s": round(dur, 2), "vertical": bool(meta["alto"] and meta["ancho"] and meta["alto"] > meta["ancho"]),
                    "cortes": len(cuts), "cortes_por_seg": round(len(cuts) / max(dur, 1), 3),
                    "toma_media": round(float(tomas.mean()), 3) if len(tomas) else None,
                    "toma_mediana": round(float(np.median(tomas)), 3) if len(tomas) else None,
                    "toma_min": round(float(tomas.min()), 3) if len(tomas) else None,
                    "toma_max": round(float(tomas.max()), 3) if len(tomas) else None,
                    "variedad_ritmo": round(float(tomas.std() / (tomas.mean() + 1e-6)), 3) if len(tomas) > 1 else 0,
                    "primer_corte_s": round(cuts[0], 3) if cuts else None,
                    "cortes_1s": sum(c < 1 for c in cuts), "cortes_3s": sum(c < 3 for c in cuts),
                    "track": meta["track"], "artist": meta["artist"], "res": meta["alto"], "fps_video": meta["fps"],
                    "descripcion": meta.get("descripcion", "")[:300],
                    "cortes_t": [round(c, 2) for c in cuts][:300]}
            feat.update(vis)
            try:
                feat.update(caras(path))
            except Exception as e:
                feat["caras_error"] = str(e)[:150]
            try:
                feat.update(audio(path, cuts, dur))
            except Exception as e:
                feat["audio_error"] = str(e)[:200]
            if os.environ.get("SHAZAM") == "1":
                feat.update(shazam(path, feat.get("drop_t"), dur, vid))
            if hoja is not None:
                cv2.imwrite(os.path.join(OUT, vid + ".jpg"), hoja, [cv2.IMWRITE_JPEG_QUALITY, 70])
        except Exception as e:
            msg = str(e)[:300]
            feat = {"id": vid, "error": msg, "etapa": etapa}
            if "Traceback" not in msg:
                traceback.print_exc(limit=1)
    if "error" in feat and any(x in feat["error"] for x in ("not a bot", "429", "Too Many")):
        seguidos += 1
        if seguidos >= 8:
            print("YouTube está bloqueando las descargas; paro este proceso"); break
        time.sleep(30 * seguidos)
        continue   # no guardar: se reintenta en la próxima corrida
    seguidos = 0
    if feat.get("etapa") == "analisis":
        bugs += 1
        if bugs >= 5:
            print("5 errores de análisis seguidos (bug del analizador); paro"); break
    else:
        bugs = 0
    txt = json.dumps(feat, ensure_ascii=False, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    open(os.path.join(OUT, vid + ".json"), "w", encoding="utf-8").write(txt)
    if PAUSA:
        time.sleep(PAUSA)
    print(n, vid, "ERROR " + feat["error"][:120] if "error" in feat else f"ok {time.time() - t0:.0f}s cortes={feat['cortes']}", flush=True)
