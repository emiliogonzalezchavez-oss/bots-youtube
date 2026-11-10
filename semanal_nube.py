"""Video largo semanal (horizontal) por país.
  python3 semanal_nube.py datos  [dolar|colombia|blue]  -> imprime datos reales (para escribir el guion)
  python3 semanal_nube.py render [dolar|colombia|blue]  -> usa $BOT_OUT/guion_semanal.json (o plantilla) y genera el mp4
"""
import json, os, sys, tempfile, datetime as dt
import bot_nube as B


def _a(di, ticker, nombre, unidad, prefijo, dec, color, canal, utc):
    return {"di": di, "ticker": ticker, "nombre": nombre, "unidad": unidad, "prefijo": prefijo, "dec": dec,
            "color": color, "canal": canal, "utc": utc}


MX, CO, AR = "Dólar Hoy MX", "Dólar Hoy Colombia", "Dólar Blue Hoy"
B.ACT.update({
    "euro": _a("el euro", "EURMXN=X", "Euro", "pesos", "$", 2, (52, 152, 219), MX, -6),
    "bitcoin": _a("el bitcoin", "BTC-USD", "Bitcoin", "dólares", "$", 0, (247, 147, 26), MX, -6),
    "bolsa": _a("la Bolsa Mexicana", "^MXX", "Bolsa Mexicana", "puntos", "", 0, (155, 89, 182), MX, -6),
    "oro": _a("el oro", "GC=F", "Oro", "dólares por onza", "$", 0, (241, 196, 15), MX, -6),
    "petroleo": _a("el petróleo", "CL=F", "Petróleo WTI", "dólares por barril", "$", 2, (149, 165, 166), MX, -6),
    # Colombia
    "euro_co": _a("el euro", "EURCOP=X", "Euro", "pesos colombianos", "$", 0, (52, 152, 219), CO, -5),
    "bitcoin_co": _a("el bitcoin", "BTC-USD", "Bitcoin", "dólares", "$", 0, (247, 147, 26), CO, -5),
    "bolsa_co": _a("el iColcap", "ICOLCAP.CL", "iColcap (Bolsa de Colombia)", "pesos colombianos", "$", 0, (155, 89, 182), CO, -5),
    "oro_co": _a("el oro", "GC=F", "Oro", "dólares por onza", "$", 0, (230, 126, 34), CO, -5),
    "petroleo_co": _a("el petróleo Brent", "BZ=F", "Petróleo Brent", "dólares por barril", "$", 2, (149, 165, 166), CO, -5),
    # Argentina
    "oficial_ar": _a("el dólar oficial", "USDARS=X", "Dólar Oficial", "pesos", "$", 0, (46, 204, 113), AR, -3),
    "euro_ar": _a("el euro", "EURARS=X", "Euro", "pesos", "$", 0, (155, 89, 182), AR, -3),
    "bitcoin_ar": _a("el bitcoin", "BTC-USD", "Bitcoin", "dólares", "$", 0, (247, 147, 26), AR, -3),
    "merval": _a("el Merval", "^MERV", "Merval", "puntos", "", 0, (231, 76, 60), AR, -3),
    "oro_ar": _a("el oro", "GC=F", "Oro", "dólares por onza", "$", 0, (241, 196, 15), AR, -3),
})
PAISES = {
    "dolar": {"canal": MX, "keys": ["dolar", "euro", "bitcoin", "bolsa", "oro", "petroleo"], "voz": "es-MX-JorgeNeural",
              "titulo": "Resumen financiero de la semana: dólar, bitcoin, Bolsa y oro",
              "desc": "Resumen semanal del dólar, euro, bitcoin, Bolsa Mexicana (IPC), oro y petróleo con datos reales.",
              "hashtags": "#dolar #bitcoin #finanzas #bolsamexicana #tipodecambio",
              "tags": ["resumen financiero", "dolar hoy", "bitcoin hoy", "bolsa mexicana", "precio del oro", "tipo de cambio", "finanzas mexico"],
              "repaso": "el dólar, el euro, el bitcoin, la Bolsa Mexicana, el oro y el petróleo"},
    "colombia": {"canal": CO, "keys": ["colombia", "euro_co", "bitcoin_co", "bolsa_co", "oro_co", "petroleo_co"], "voz": "es-CO-GonzaloNeural",
                 "titulo": "Resumen financiero de la semana en Colombia: dólar, euro, bitcoin y petróleo",
                 "desc": "Resumen semanal del dólar, euro, bitcoin, iColcap (Bolsa de Colombia), oro y petróleo Brent con datos reales.",
                 "hashtags": "#dolar #colombia #trm #finanzas #petroleo",
                 "tags": ["resumen financiero colombia", "dolar hoy colombia", "trm", "bitcoin hoy", "colcap", "precio del petróleo", "finanzas colombia"],
                 "repaso": "el dólar, el euro, el bitcoin, la Bolsa de Colombia, el oro y el petróleo Brent"},
    "blue": {"canal": AR, "keys": ["blue", "oficial_ar", "euro_ar", "bitcoin_ar", "merval", "oro_ar"], "voz": "es-AR-TomasNeural",
             "titulo": "Resumen financiero de la semana en Argentina: dólar blue, oficial, Merval y bitcoin",
             "desc": "Resumen semanal del dólar blue, dólar oficial, euro, bitcoin, Merval y oro con datos reales.",
             "hashtags": "#dolarblue #argentina #merval #finanzas #dolar",
             "tags": ["resumen financiero argentina", "dolar blue hoy", "dolar oficial", "merval", "bitcoin hoy", "finanzas argentina"],
             "repaso": "el dólar blue, el dólar oficial, el euro, el bitcoin, el Merval y el oro"},
}
PAIS = sys.argv[2] if len(sys.argv) > 2 else "dolar"
P = PAISES[PAIS]
KEYS = P["keys"]
B.FPS = 24
W, H = 1920, 1080


def cargar():
    res = {}
    for k in KEYS:
        try:
            res[k] = B.datos(k)
        except Exception as e:
            print("salto", k, e, file=sys.stderr)
    return res


def datos():
    res = cargar()
    print(json.dumps({k: {"nombre": B.ACT[k]["nombre"], "unidad": B.ACT[k]["unidad"],
                          **{x: round(v[x], 4) for x in ("hoy", "pct_dia", "pct_semana", "pct_mes", "max_mes", "min_mes", "max_semana", "min_semana")}}
                      for k, v in res.items()}, ensure_ascii=False))


def plantilla(res):
    g = {"intro": f"Este es el resumen financiero de la semana, al {B.fecha_texto(B.hoy_local(KEYS[0]))}. Repasamos {P['repaso']}.",
         "activos": {}, "cierre": f"Ese fue el resumen de la semana. Esto es solo información, no es recomendación de inversión. Suscríbete a {P['canal']} para no perderte el siguiente."}
    for k, r in res.items():
        di = B.ACT[k]["di"]
        g["activos"][k] = " ".join([f"{di[0].upper() + di[1:]} cerró en {B.precio_h(k, r['hoy'])}.",
                                    B.mov(r["pct_semana"], "En la semana") + ".", B.mov(r["pct_mes"], "En el último mes") + ".",
                                    f"Durante la semana se movió entre {B.precio_h(k, r['min_semana'])} y {B.precio_h(k, r['max_semana'])}."])
    return g


def render():
    res = cargar()
    gp = f"{B.OUT}/guion_semanal.json"
    g = json.load(open(gp)) if os.path.exists(gp) else plantilla(res)
    if not set(res) <= set(g.get("activos", {})):
        g = plantilla(res)
    tmp = tempfile.mkdtemp(); segs = []; canal = P["canal"]

    def seg(nombre, texto, **kw):
        p = os.path.join(tmp, nombre + ".mp3")
        segs.append({"audio": p, "frames": int((B.narrar(texto, p, P["voz"]) + 0.5) * B.FPS), **kw})

    hoy = B.hoy_local(KEYS[0])
    seg("intro", g["intro"], tipo="titulo", tit="Resumen financiero de la semana", sub=B.fecha_texto(hoy))
    for k in res:
        seg(k, g["activos"][k], tipo="activo", key=k)
    seg("cierre", g["cierre"], tipo="titulo", tit="Suscríbete", sub=canal)
    fn = lambda i, sg, t, dur, base: (B.cuadro_activo(base, W, H, sg["key"], res[sg["key"]], t, dur, canal) if sg["tipo"] == "activo"
                                      else B.cuadro_titulo(base, W, H, sg["tit"], sg["sub"], t, canal))
    os.makedirs(B.OUT, exist_ok=True)
    out = f"{B.OUT}/{hoy}_{PAIS}_semanal.mp4"
    B.render(segs, out, W, H, fn)
    info = {"ruta": out,
            "titulo": f"{P['titulo']} ({hoy.day} {B.MESES[hoy.month - 1]} {hoy.year})"[:100],
            "descripcion": (P["desc"] + "\n\nDatos de mercado con fines informativos. No es recomendación de inversión.\n\n" + P["hashtags"]),
            "tags": P["tags"]}
    json.dump(info, open(out.replace(".mp4", ".json"), "w"), ensure_ascii=False)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    {"datos": datos, "render": render}[sys.argv[1]]()
