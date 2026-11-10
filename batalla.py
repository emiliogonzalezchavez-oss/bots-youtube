"""Batalla de las Monedas: Short con ranking semanal de monedas latinas vs dólar. Uso: python3 batalla.py [dolar|colombia|blue]"""
import json, os, sys, tempfile
import bot_nube as B
from PIL import ImageDraw

MONEDAS = [("USDMXN=X", "peso mexicano", "México"), ("USDBRL=X", "real brasileño", "Brasil"),
           ("USDCOP=X", "peso colombiano", "Colombia"), ("USDCLP=X", "peso chileno", "Chile"),
           ("USDARS=X", "peso argentino", "Argentina"), ("USDPEN=X", "sol peruano", "Perú"),
           ("USDUYU=X", "peso uruguayo", "Uruguay")]
W, H = 1080, 1920
AMARILLO = (241, 196, 15)
KEY = sys.argv[1] if len(sys.argv) > 1 else "dolar"
CANAL = B.ACT[KEY]["canal"]
VOZ = B.ACT[KEY]["voz"]
EXTRA = {"dolar": ("#pesomexicano", "peso mexicano"), "colombia": ("#pesocolombiano", "peso colombiano"),
         "blue": ("#pesoargentino", "peso argentino")}[KEY]


def datos(dias=5):
    import yfinance as yf
    out = []
    for t, nom, pais in MONEDAS:
        try:
            s = yf.Ticker(t).history(period="1mo")["Close"].dropna()
            fuerza = -(s.iloc[-1] / s.iloc[-1 - dias] - 1) * 100   # si el dólar sube, la moneda pierde
            if abs(fuerza) <= 8:                                     # filtro de datos raros
                out.append({"nombre": nom, "pais": pais, "pct": round(float(fuerza), 2)})
        except Exception:
            pass
    return sorted(out, key=lambda x: -x["pct"])


def mov(p):
    if abs(p) < 0.05:
        return "se mantuvo prácticamente igual"
    return ("ganó " if p > 0 else "perdió ") + f"{abs(p):.1f} por ciento".replace(".0 ", " ")


def guion(rk):
    g, u = rk[0], rk[-1]
    intro = "¿Qué moneda de Latinoamérica le ganó al dólar esta semana? Esta es la batalla de las monedas."
    medio = [f"En el lugar {i}, el {m['nombre']}, que {mov(m['pct'])}." for i, m in enumerate(rk[1:-1], start=2)]
    gan = f"se fortaleció {abs(g['pct']):.1f} por ciento" if g["pct"] >= 0.05 else mov(g["pct"])
    res = (f"En el último lugar quedó el {u['nombre']}, que {mov(u['pct'])} frente al dólar. " + " ".join(medio[::-1]) +
           f" Y el ganador de la semana es el {g['nombre']}, que {gan}.")
    return intro, res, "¿Tu moneda ganó o perdió? Sígueme para la batalla de la próxima semana."


def cuadro(base, rk, t, fase, revelados):
    img = base.copy(); d = ImageDraw.Draw(img); F = B.fuente
    B.cen(d, W, 90, "BATALLA DE LAS", F(70), B.BLANCO)
    B.cen(d, W, 170, "MONEDAS", F(110), AMARILLO)
    B.cen(d, W, 310, "Cambio frente al dólar · última semana", F(36, False), B.GRIS)
    n = len(rk); y0, alto, cx = 440, 165, W / 2
    mx = max(abs(m["pct"]) for m in rk) or 1
    grow = B.suave(t / 2.0) if fase == "barras" else 1.0
    d.line([(cx, y0 - 20), (cx, y0 + n * alto - 20)], fill=(70, 80, 100), width=3)
    for i, m in enumerate(rk):
        y = y0 + i * alto
        if (n - 1 - i) >= revelados:
            d.rounded_rectangle([60, y, W - 60, y + 110], radius=20, outline=(40, 50, 70), width=3)
            B.cen(d, W, y + 30, "?", F(52), (60, 70, 90)); continue
        L = (W / 2 - 240) * abs(m["pct"]) / mx * grow
        col = B.VERDE if m["pct"] >= 0 else B.ROJO
        lab, vt, f = f"{i + 1}. {m['pais']}", f"{m['pct'] * grow:+.1f}%", F(44)
        if m["pct"] >= 0:
            d.rounded_rectangle([cx, y + 20, cx + max(L, 8), y + 90], radius=14, fill=col)
            d.text((cx - 20 - d.textlength(lab, font=f), y + 30), lab, font=f, fill=B.BLANCO)
            d.text((cx + max(L, 8) + 15, y + 30), vt, font=f, fill=col)
        else:
            d.rounded_rectangle([cx - max(L, 8), y + 20, cx, y + 90], radius=14, fill=col)
            d.text((cx + 20, y + 30), lab, font=f, fill=B.BLANCO)
            d.text((cx - max(L, 8) - 15 - d.textlength(vt, font=f), y + 30), vt, font=f, fill=col)
    if revelados >= n:
        B.cen(d, W, y0 + n * alto + 20, f"Ganador: {rk[0]['nombre'].capitalize()}", F(56), AMARILLO)
    B.cen(d, W, H - 120, CANAL, F(40), B.GRIS)
    B.cen(d, W, H - 60, "Datos de mercado · No es recomendación de inversión", F(26, False), (90, 100, 120))
    return img


def generar():
    rk = datos(); textos = guion(rk); n = len(rk)
    tmp = tempfile.mkdtemp(); segs = []
    for i, txt in enumerate(textos):
        p = os.path.join(tmp, f"{i}.mp3"); segs.append({"audio": p, "frames": int((B.narrar(txt, p, VOZ) + 0.4) * B.FPS)})

    def fn(i, sg, t, dur, base):
        if i == 0: return cuadro(base, rk, t, "intro", 0)
        if i == 1: return cuadro(base, rk, t, "barras", min(n, int(t / (dur / n)) + 1))
        return cuadro(base, rk, t, "fin", n)

    os.makedirs(B.OUT, exist_ok=True)
    hoy = B.hoy_local(KEY); out = f"{B.OUT}/{hoy}_{KEY}_batalla.mp4"
    B.render(segs, out, W, H, fn)
    g = rk[0]
    tit = f"¿Qué moneda latina le ganó al dólar esta semana? 🏆 {g['pais']} | Batalla de las Monedas"
    desc = ("Ranking semanal de monedas de Latinoamérica frente al dólar con datos reales: " +
            ", ".join(f"{m['pais']} {m['pct']:+.1f}%" for m in rk) +
            ".\n\nDatos de mercado con fines informativos. No es recomendación de inversión.\n\n"
            f"#dolar #monedas #latinoamerica {EXTRA[0]} #shorts")
    info = {"ruta": out, "titulo": tit[:100], "descripcion": desc,
            "tags": ["monedas latinoamérica", "dólar hoy", EXTRA[1], "ranking monedas", "tipo de cambio"],
            "guion": list(textos), "ranking": rk}
    json.dump(info, open(out.replace(".mp4", ".json"), "w"), ensure_ascii=False)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    generar()
