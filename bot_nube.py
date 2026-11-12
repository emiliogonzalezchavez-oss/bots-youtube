"""Bot Dólar Hoy (nube): Short diario. Uso: python3 bot_nube.py dolar|colombia|blue"""
import asyncio, datetime as dt, json, os, random, re, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

CANAL = "Dólar Hoy MX"
VOZ, VEL, FPS = "es-MX-JorgeNeural", "+8%", 30
OUT = os.environ.get("BOT_OUT", "/home/user/bot/videos")
ACT = {
    "dolar": {"di": "el dólar", "ticker": "USDMXN=X", "nombre": "Dólar", "unidad": "pesos", "prefijo": "$", "dec": 2, "color": (46, 204, 113),
              "canal": "Dólar Hoy MX", "voz": "es-MX-JorgeNeural", "utc": -6, "pais": "México",
              "hashtags": "#dolarhoy #preciodeldolar #tipodecambio #pesomexicano",
              "tags": ["precio del dólar hoy", "dólar hoy", "tipo de cambio", "dolar hoy mexico", "precio del dolar", "peso mexicano"]},
    "colombia": {"di": "el dólar", "ticker": "USDCOP=X", "nombre": "Dólar", "unidad": "pesos colombianos", "prefijo": "$", "dec": 0, "color": (241, 196, 15),
                 "canal": "Dólar Hoy Colombia", "voz": "es-CO-GonzaloNeural", "utc": -5, "pais": "Colombia",
                 "hashtags": "#dolarhoy #dolarcolombia #trm #pesocolombiano",
                 "tags": ["precio del dólar hoy colombia", "dólar hoy colombia", "trm hoy", "dolar en colombia", "peso colombiano"]},
    "blue": {"di": "el dólar blue", "ticker": "BLUE", "nombre": "Dólar Blue", "unidad": "pesos", "prefijo": "$", "dec": 0, "color": (52, 152, 219),
             "canal": "Dólar Blue Hoy", "voz": "es-AR-TomasNeural", "utc": -3, "pais": "Argentina",
             "hashtags": "#dolarblue #dolarhoy #argentina #dolar",
             "tags": ["dólar blue hoy", "dolar blue", "cotización dólar blue", "dolar hoy argentina", "precio del dólar blue"]},
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
BG1, BG2 = (10, 14, 24), (22, 30, 48)
BLANCO, GRIS, VERDE, ROJO = (240, 244, 250), (140, 150, 170), (46, 204, 113), (231, 76, 60)


def hoy_local(key):
    return (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=ACT[key]["utc"])).date()


def fecha_texto(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]} de {d.year}"


def serie(key):
    if ACT[key]["ticker"] == "BLUE":
        import urllib.request
        get = lambda u: json.load(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))
        pr = [float(x["venta"]) for x in get("https://api.argentinadatos.com/v1/cotizaciones/dolares/blue")][-35:]
        try:
            pr[-1] = float(get("https://dolarapi.com/v1/dolares/blue")["venta"])
        except Exception:
            pass
        return pr
    import yfinance as yf
    df = yf.Ticker(ACT[key]["ticker"]).history(period="3mo", interval="1d")
    return [float(v) for v in df["Close"].dropna()][-35:]


def datos(key):
    pr = serie(key)
    h, a, s, m = pr[-1], pr[-2], pr[-6], pr[-22]
    return {"hoy": h, "pct_dia": (h / a - 1) * 100, "pct_semana": (h / s - 1) * 100, "pct_mes": (h / m - 1) * 100,
            "max_mes": max(pr[-22:]), "min_mes": min(pr[-22:]), "max_semana": max(pr[-5:]), "min_semana": min(pr[-5:]),
            "precios": pr[-22:], "fecha": hoy_local(key)}


def precio_h(key, v):
    a = ACT[key]
    if a["unidad"] == "pesos" and a["dec"] == 2:
        p = int(v); c = round((v - p) * 100)
        if c == 100: p, c = p + 1, 0
        if c == 0: return f"{p} pesos exactos"
        if c == 1: return f"{p} pesos con un centavo"
        return f"{p} pesos con {c} centavos"
    if a["dec"] == 0:
        return f"{round(v)} {a['unidad']}"
    return f"{v:,.{a['dec']}f} {a['unidad']}"


def mov(p, suj):
    if abs(p) < 0.05:
        return f"{suj} se mantuvo prácticamente sin cambios"
    v = random.choice(["subió", "avanzó", "ganó"]) if p > 0 else random.choice(["bajó", "retrocedió", "perdió"])
    return f"{suj} {v} {abs(p):.2f} por ciento"


def guion(key, r):
    di = ACT[key]["di"]
    intro = random.choice([f"Así amaneció {di} este {fecha_texto(r['fecha'])}.",
                           f"Precio de {di} hoy, {fecha_texto(r['fecha'])}.".replace("de el ", "del ")])
    t = " ".join([intro,
                  random.choice([f"{di[0].upper() + di[1:]} cotiza hoy en {precio_h(key, r['hoy'])}.",
                                 f"Hoy {di} se ubica en {precio_h(key, r['hoy'])}."]),
                  mov(r["pct_dia"], "Respecto al cierre anterior,") + ".",
                  mov(r["pct_mes"], "En el último mes") + ".",
                  f"Su nivel más alto del mes fue de {precio_h(key, r['max_mes'])}, y el más bajo de {precio_h(key, r['min_mes'])}."])
    return t, f"Suscríbete y te digo el precio de {di} cada mañana.".replace("de el ", "del ")


def narrar(texto, ruta, voz=VOZ):
    import edge_tts
    asyncio.run(edge_tts.Communicate(texto, voz, rate=VEL).save(ruta))
    p = subprocess.run(["ffmpeg", "-i", ruta], capture_output=True, text=True)
    h, mi, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", p.stderr).groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


_fc = {}
def fuente(t, b=True):
    k = (t, b)
    if k not in _fc:
        _fc[k] = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if b else ""), t)
    return _fc[k]


def fondo(W, H):
    img = Image.new("RGB", (W, H)); d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(BG1[i] + (BG2[i] - BG1[i]) * t) for i in range(3)))
    return img


def cen(d, W, y, txt, f, col):
    d.text(((W - d.textlength(txt, font=f)) / 2, y), txt, font=f, fill=col)


def suave(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def fmt(key, v):
    a = ACT[key]; return f"{a['prefijo']}{v:,.{a['dec']}f}"


def cuadro_titulo(base, W, H, tit, sub, t, canal=CANAL):
    img = base.copy(); d = ImageDraw.Draw(img); a = suave(t * 2); s = min(W, H) / 1080
    cen(d, W, H * 0.38, tit, fuente(int(90 * s)), tuple(int(c * a) for c in BLANCO))
    cen(d, W, H * 0.38 + 125 * s, sub, fuente(int(44 * s), False), tuple(int(c * a) for c in GRIS))
    cen(d, W, H - 110 * s, canal, fuente(int(40 * s)), GRIS)
    return img


def cuadro_activo(base, W, H, key, r, t, dur, canal=None):
    """Vertical (Short) u horizontal (semanal) según W>H."""
    a = ACT[key]; img = base.copy(); d = ImageDraw.Draw(img)
    vert = H > W; col = a["color"]
    cen(d, W, 70, f"{canal or a['canal']}  ·  {fecha_texto(r['fecha'])}", fuente(34, False), GRIS)
    cen(d, W, 150, a["nombre"].upper(), fuente(88), col)
    v = r["min_mes"] + (r["hoy"] - r["min_mes"]) * suave(t / 1.2)
    cen(d, W, 270, fmt(key, v), fuente(150), BLANCO)
    cen(d, W, 440, a["unidad"], fuente(40, False), GRIS)
    pk, et = ("pct_dia", "hoy") if vert else ("pct_semana", "semana")
    if t > 0.8:
        p = r[pk]; cm = VERDE if p >= 0 else ROJO
        txt = f"{'▲' if p >= 0 else '▼'} {p:+.2f}% {et}"; f = fuente(52); w = d.textlength(txt, font=f)
        x0, y0 = (W - w) / 2 - 30, 510
        d.rounded_rectangle([x0, y0, x0 + w + 60, y0 + 80], radius=40, fill=tuple(int(c * 0.25) for c in cm))
        d.text((x0 + 30, y0 + 10), txt, font=f, fill=cm)
    pr = r["precios"]; gx0, gx1 = W * 0.08, W * 0.92
    gy0, gy1 = (700, 1450) if vert else (650, 1000)
    lo, hi = min(pr), max(pr); rg = (hi - lo) or 1
    pts = [(gx0 + (gx1 - gx0) * i / (len(pr) - 1), gy1 - (gy1 - gy0) * (x - lo) / rg) for i, x in enumerate(pr)]
    for i in range(5):
        y = gy0 + (gy1 - gy0) * i / 4; d.line([(gx0, y), (gx1, y)], fill=(35, 45, 65), width=2)
    prog = suave(t / max(1.5, dur * 0.55)) * (len(pts) - 1); n = int(prog); vis = pts[:n + 1]
    if n < len(pts) - 1:
        fr = prog - n; (xa, ya), (xb, yb) = pts[n], pts[n + 1]; vis.append((xa + (xb - xa) * fr, ya + (yb - ya) * fr))
    if len(vis) >= 2:
        d.polygon(vis + [(vis[-1][0], gy1), (vis[0][0], gy1)], fill=tuple(int(BG2[i] * 0.6 + col[i] * 0.22) for i in range(3)))
        d.line(vis, fill=col, width=8, joint="curve")
        x, y = vis[-1]; rad = 14 + 4 * abs(((t * 2) % 2) - 1)
        d.ellipse([x - rad, y - rad, x + rad, y + rad], fill=BLANCO)
    fe = fuente(32, False)
    d.text((gx0, gy0 - 50), f"Máx {fmt(key, hi)}", font=fe, fill=GRIS)
    d.text((gx0, gy1 + 15), f"Mín {fmt(key, lo)}", font=fe, fill=GRIS)
    d.text((gx1 - d.textlength("Últimos 30 días", font=fe), gy1 + 15), "Últimos 30 días", font=fe, fill=GRIS)
    if t > 1.5:
        fb = fuente(46)
        if vert:
            if t > 2.0:
                fc = fuente(44); tc = "SUSCRÍBETE: PRECIO DIARIO"
                wc = d.textlength(tc, font=fc); xc = (W - wc) / 2 - 40
                d.rounded_rectangle([xc, 1505, xc + wc + 80, 1585], radius=40, fill=(230, 0, 0))
                cen(d, W, 1520, tc, fc, (255, 255, 255))
            yb = 1615
            for e, val in (("Semana", r["pct_semana"]), ("Mes", r["pct_mes"])):
                cen(d, W, yb, f"{e}: {val:+.2f}%", fb, VERDE if val >= 0 else ROJO); yb += 75
        else:
            d.text((W * 0.08, 380), f"Hoy {r['pct_dia']:+.2f}%", font=fb, fill=VERDE if r["pct_dia"] >= 0 else ROJO)
            tm = f"Mes {r['pct_mes']:+.2f}%"
            d.text((W * 0.92 - d.textlength(tm, font=fb), 380), tm, font=fb, fill=VERDE if r["pct_mes"] >= 0 else ROJO)
    cen(d, W, H - 60, "Información de mercado · No es recomendación de inversión", fuente(26, False), (90, 100, 120))
    return img


def render(segs, out, W, H, frame_fn):
    """segs: [{'audio','frames',...}]; frame_fn(seg_index, seg, t, dur, base) -> PIL image."""
    base = fondo(W, H); aud = out + ".m4a"; ent, fil = [], []
    for i, sg in enumerate(segs):
        ent += ["-i", sg["audio"]]
        fil.append(f"[{i}:a]aresample=44100,apad,atrim=0:{sg['frames'] / FPS:.4f},asetpts=PTS-STARTPTS[a{i}]")
    fil.append("".join(f"[a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=0:a=1[voz]")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ent, "-filter_complex", ";".join(fil), "-map", "[voz]",
                    "-c:a", "aac", "-b:a", "192k", aud], check=True)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", aud, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", "-movflags", "+faststart", out], stdin=subprocess.PIPE)
    for i, sg in enumerate(segs):
        dur = sg["frames"] / FPS
        for f in range(sg["frames"]):
            p.stdin.write(frame_fn(i, sg, f / FPS, dur, base).tobytes())
    p.stdin.close(); p.wait(); os.remove(aud)
    if p.returncode != 0:
        raise RuntimeError("ffmpeg falló")


def metadatos(key, r):
    a = ACT[key]; d = r["fecha"]; n = a["nombre"]
    pais = f" en {a['pais']}" if key != "dolar" else ""
    tit = f"Precio del {n.upper()} HOY{pais.upper()} {d.day} de {MESES[d.month - 1]} {d.year} | {fmt(key, r['hoy'])}"
    desc = (f"Precio de {a['di']}{pais} hoy {fecha_texto(d)}: {fmt(key, r['hoy'])} {a['unidad']}.\n"
            f"Cambio del día: {r['pct_dia']:+.2f}% | Cambio del mes: {r['pct_mes']:+.2f}%\n\n"
            f"🔔 Suscríbete a {a['canal']} y recibe el precio cada mañana.\n\n"
            "Datos de mercado con fines informativos. No es recomendación de inversión.\n\n"
            f"{a['hashtags']} #shorts").replace("de el ", "del ")
    return tit[:100], desc, a["tags"]


def generar(key="dolar"):
    r = datos(key); txt, cierre = guion(key, r); a = ACT[key]
    tmp = tempfile.mkdtemp(); a1, a2 = os.path.join(tmp, "a.mp3"), os.path.join(tmp, "c.mp3")
    segs = [{"tipo": "activo", "audio": a1, "frames": int((narrar(txt, a1, a["voz"]) + 0.4) * FPS)},
            {"tipo": "titulo", "audio": a2, "frames": int((narrar(cierre, a2, a["voz"]) + 0.4) * FPS)}]
    sub = f"Precio de {a['di']} todos los días".replace("de el ", "del ")
    fn = lambda i, sg, t, dur, base: (cuadro_activo(base, 1080, 1920, key, r, t, dur) if sg["tipo"] == "activo"
                                      else cuadro_titulo(base, 1080, 1920, "Suscríbete", sub, t, a["canal"]))
    os.makedirs(OUT, exist_ok=True)
    out = f"{OUT}/{r['fecha']}_{key}_short.mp4"
    render(segs, out, 1080, 1920, fn)
    tit, desc, tags = metadatos(key, r)
    info = {"ruta": out, "titulo": tit, "descripcion": desc, "tags": tags, "guion": txt}
    json.dump(info, open(out.replace(".mp4", ".json"), "w"), ensure_ascii=False)
    return info


if __name__ == "__main__":
    print(json.dumps(generar(sys.argv[1] if len(sys.argv) > 1 else "dolar"), ensure_ascii=False))
