"""Clipazo bot. Uso:
  python3 clip_bot.py listar                      -> JSON con los mejores clips de las últimas 24 h (Twitch)
  python3 clip_bot.py bajar <url_clip>            -> descarga clip.mp4 y transcribe a palabras.json (imprime palabras con índice)
  python3 clip_bot.py editar <gancho> <streamer>  -> aplica correcciones.json (opcional) y genera final.mp4
"""
import json, os, re, subprocess, sys
W, H = 1080, 1920
F = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
STREAMERS = ["ibai", "auronplay", "rubius", "elmariana", "juansguarnizo", "rivers_gg", "illojuan", "elxokas"]
DIR = "/home/user/clips"


def sh(*a, **k):
    return subprocess.run(list(a), capture_output=True, text=True, **k)


def listar():
    out = []
    for c in STREAMERS:
        r = sh("yt-dlp", "--no-update", "--flat-playlist", "-J", f"https://www.twitch.tv/{c}/clips?filter=clips&range=24hr", timeout=40)
        try:
            for e in json.loads(r.stdout).get("entries", [])[:15]:
                d = e.get("duration") or 0
                if 8 <= d <= 45:
                    out.append({"streamer": c, "titulo": e.get("title"), "vistas": e.get("view_count") or 0,
                                "duracion": d, "url": e["url"]})
        except Exception as ex:
            print("aviso", c, ex, file=sys.stderr)
    out.sort(key=lambda x: -x["vistas"])
    print(json.dumps(out[:25], ensure_ascii=False, indent=0))


def bajar(url):
    os.chdir(DIR)
    for f in ("clip.mp4", "palabras.json", "correcciones.json", "final.mp4"):
        if os.path.exists(f):
            os.remove(f)
    r = sh("yt-dlp", "--no-update", "-f", "best[height<=720]/best", "-o", "clip.mp4", url, timeout=150)
    if not os.path.exists("clip.mp4"):
        raise RuntimeError("no se pudo descargar: " + r.stderr[-400:])
    import numpy as np
    from faster_whisper import WhisperModel
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "clip.mp4", "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True).stdout
    m = WhisperModel("base", device="cpu", compute_type="int8", cpu_threads=1)
    segs, _ = m.transcribe(np.frombuffer(raw, np.float32), language="es", word_timestamps=True, vad_filter=True)
    pal = [[w.start, w.end, w.word.strip()] for s in segs for w in s.words]
    json.dump(pal, open("palabras.json", "w"), ensure_ascii=False)
    print("PALABRAS:", " | ".join(f"{i}:{w}" for i, (_, _, w) in enumerate(pal)))
    print("LISTO")


def editar(gancho, streamer):
    from PIL import Image, ImageDraw, ImageFont
    os.chdir(DIR)
    pal = json.load(open("palabras.json"))
    if os.path.exists("correcciones.json"):  # {"indice": "palabra corregida"}  ("" = borrar)
        for i, w in json.load(open("correcciones.json")).items():
            if int(i) < len(pal):
                pal[int(i)][2] = w
        pal = [p for p in pal if p[2].strip()]
    # cartel del gancho + crédito
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    f = ImageFont.truetype(F, 72); lineas, cur = [], ""
    for w in gancho.upper().split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) > W - 160:
            lineas.append(cur); cur = w
        else:
            cur = t
    lineas.append(cur)
    y = 250
    for ln in lineas[:3]:
        tw = d.textlength(ln, font=f)
        d.rounded_rectangle([(W - tw) / 2 - 30, y - 12, (W + tw) / 2 + 30, y + 92], radius=22, fill=(255, 214, 0, 255))
        d.text((W / 2, y + 40), ln, font=f, fill=(15, 15, 15, 255), anchor="mm"); y += 112
    fc = ImageFont.truetype(F, 36)
    d.text((W / 2, 1620), "Clip: twitch.tv/" + streamer, font=fc, fill=(255, 255, 255, 220), anchor="mm",
           stroke_width=3, stroke_fill=(0, 0, 0, 200))
    im.save("overlay.png")
    # botón "SUSCRÍBETE" (arriba de la zona que tapa la interfaz de Shorts; aparece a los 1.5 s)
    cta = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dc = ImageDraw.Draw(cta)
    fb = ImageFont.truetype(F, 48); txt = "SUSCRÍBETE PARA MÁS CLIPS"
    tw = dc.textlength(txt, font=fb); x0, y0 = (W - tw) / 2 - 40, 1500
    dc.rounded_rectangle([x0, y0, x0 + tw + 80, y0 + 90], radius=45, fill=(230, 0, 0, 245))
    dc.text((W / 2, y0 + 45), txt, font=fb, fill=(255, 255, 255, 255), anchor="mm")
    cta.save("cta.png")
    # subtítulos
    def ts(t): return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"
    cab = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[V4+ Styles]\n"
           "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           "Style: S,DejaVu Sans,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1\n\n[Events]\n"
           "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
    grupos, g = [], []
    for p in pal:
        g.append(p)
        if len(g) == 3 or re.search(r"[.,!?]$", p[2]):
            grupos.append(g); g = []
    if g:
        grupos.append(g)
    lin = []
    for gi, g in enumerate(grupos):
        fin_g = min(grupos[gi + 1][0][0], g[-1][1] + 0.6) if gi + 1 < len(grupos) else g[-1][1] + 0.4
        for i, (a, b, _) in enumerate(g):
            fin = g[i + 1][0] if i + 1 < len(g) else fin_g
            txt = " ".join(("{\\c&H0000D6FF&}" + w.upper() + "{\\c&H00FFFFFF&}") if j == i else w.upper()
                           for j, (_, _, w) in enumerate(g))
            lin.append(f"Dialogue: 0,{ts(max(0, a - 0.1))},{ts(max(fin - 0.1, a))},S,,0,0,0,,{{\\pos(540,1400)}}{txt}")
    open("subs.ass", "w").write(cab + "\n".join(lin) + "\n")
    fcx = ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:4,eq=brightness=-0.25[bg];"
           "[0:v]scale=1400:-2,crop=1080:ih[fg];"
           "[bg][fg]overlay=0:(H-h)/2-60[v1];[v1][1:v]overlay=0:0[v2];"
           "[v2][2:v]overlay=0:0:enable='gte(t,1.5)',subtitles=subs.ass[v]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", "clip.mp4", "-i", "overlay.png", "-i", "cta.png",
                    "-filter_complex", fcx,
                    "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-threads", "1",
                    "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "final.mp4"],
                   check=True)
    print("LISTO", os.path.join(DIR, "final.mp4"))


if __name__ == "__main__":
    os.makedirs(DIR, exist_ok=True)
    a = sys.argv
    {"listar": lambda: listar(), "bajar": lambda: bajar(a[2]), "editar": lambda: editar(a[2], a[3])}[a[1]]()
