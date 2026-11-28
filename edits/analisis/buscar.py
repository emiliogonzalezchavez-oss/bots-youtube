"""Busca edits de coches en YouTube (API Data v3) y junta stats + subs del canal.
Uso: python buscar.py videos_previos.json salida.json [max_busquedas]
Cuota: search=100 unidades, videos/channels=1 por cada 50. Gratis = 10,000/día -> ~90 búsquedas.
"""
import json, os, random, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

KEY = os.environ["YT_API_KEY"]
prev_f, out_f = sys.argv[1], sys.argv[2]
MAX_B = int(sys.argv[3]) if len(sys.argv) > 3 else 85

COCHES = ["supra", "gtr", "r34", "rx7", "silvia s15", "ae86", "nsx", "civic type r", "e30", "bmw m4", "bmw m3", "m5",
          "porsche 911", "gt3 rs", "lamborghini", "huracan", "aventador", "ferrari", "sf90", "mclaren", "koenigsegg",
          "bugatti", "mustang", "corvette", "dodge challenger", "amg", "audi rs6", "r8", "golf gti", "evo", "subaru wrx"]
GENERAL = ["car edit", "car edit 4k", "car edit phonk", "jdm edit", "car edits", "cgi car edit", "blender car edit",
           "3d car edit", "car edit slowed", "drift edit", "hypercar edit", "car edit capcut", "car edit after effects",
           "car cinematic edit", "car edit night", "car edit sad", "supercar edit", "car edit shorts", "car edit 2026",
           "car edit 2025", "car edit velocity", "car edit transition"]


def api(path, **p):
    p["key"] = KEY
    url = f"https://www.googleapis.com/youtube/v3/{path}?" + urllib.parse.urlencode(p)
    for i in range(3):
        try:
            return json.load(urllib.request.urlopen(url, timeout=30))
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if "quota" in msg.lower():
                raise SystemExit("CUOTA")
            print("ERR", e.code, msg); time.sleep(2)
        except Exception as e:
            print("ERR", e); time.sleep(2)
    return {}


prev = json.load(open(prev_f)) if os.path.exists(prev_f) else {}
consultas = [(q, o) for q in GENERAL for o in ("viewCount", "relevance")]
consultas += [(f"{c} edit", o) for c in COCHES for o in ("viewCount",)]
random.shuffle(consultas)
ids = {}
hechas = 0
try:
    for q, orden in consultas[:MAX_B]:
        d = api("search", part="id", q=q, type="video", videoDuration="short", order=orden, maxResults=50)
        hechas += 1
        for it in d.get("items", []):
            ids.setdefault(it["id"]["videoId"], q)
except SystemExit as e:
    print("parado:", e)
print("búsquedas", hechas, "ids", len(ids))

nuevos = [i for i in ids if i not in prev]
todos = list(set(nuevos) | set(prev))   # refrescar stats de todos (barato)
vids = {}
for k in range(0, len(todos), 50):
    d = api("videos", part="snippet,statistics,contentDetails", id=",".join(todos[k:k + 50]))
    for v in d.get("items", []):
        s, sn = v.get("statistics", {}), v["snippet"]
        vids[v["id"]] = {"id": v["id"], "titulo": sn["title"], "canal": sn["channelId"], "canal_nombre": sn["channelTitle"],
                         "publicado": sn["publishedAt"], "duracion": v["contentDetails"]["duration"],
                         "vistas": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0) or 0),
                         "comentarios": int(s.get("commentCount", 0) or 0), "tags": sn.get("tags", [])[:15],
                         "consulta": ids.get(v["id"]) or prev.get(v["id"], {}).get("consulta")}
canales = list({v["canal"] for v in vids.values()})
subs = {}
for k in range(0, len(canales), 50):
    d = api("channels", part="statistics", id=",".join(canales[k:k + 50]))
    for c in d.get("items", []):
        st = c["statistics"]
        subs[c["id"]] = (int(st["subscriberCount"]) if not st.get("hiddenSubscriberCount") else None, int(st.get("videoCount", 0)))
ahora = datetime.now(timezone.utc)
for v in vids.values():
    v["subs"], v["videos_canal"] = subs.get(v["canal"], (None, None))
    dias = max(1.0, (ahora - datetime.fromisoformat(v["publicado"].replace("Z", "+00:00"))).total_seconds() / 86400)
    v["dias"] = round(dias, 1)
    v["vistas_dia"] = round(v["vistas"] / dias, 1)
    v["viral"] = round(v["vistas"] / max(v["subs"] or 1000, 1000), 3)   # vistas vs. tamaño del canal
for k, v in prev.items():
    vids.setdefault(k, v)
json.dump(vids, open(out_f, "w"), ensure_ascii=False)
print("total videos", len(vids), "nuevos", len(nuevos))
