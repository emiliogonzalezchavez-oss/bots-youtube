"""Sube un video a YouTube con tus propios tokens (sin Composio).
Uso: python subir.py <canal> <ruta_del_json>
Lee CLIENT_SECRET_JSON y TOKEN_<CANAL> de las variables de entorno (GitHub Secrets).
"""
import json, os, sys
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

CANALES = {  # alias -> channelId esperado (nunca sube a otro canal)
    "dolarhoymx": "UCKoqNNGZPbReqU7yCY8x-jA",
    "dolarhoycol": "UCfIOeg7MLqIQfg3A10vvmnw",
    "dolarblue": "UC0MfhaJEYXbz2igDjmKCrmQ",
    "nisabias": "UCJ3ze5dn2wKYw5ElTFfCJQA",
    "factbomb": "UC6GXUQtQ-lVfBJMBwoRAPDw",
    "clipazo": "UCEByNmppUaShrbgg-cAhAMg",
}


def cliente(canal):
    cs = json.loads(os.environ["CLIENT_SECRET_JSON"])
    cs = cs.get("installed") or cs.get("web")
    cred = Credentials(None, refresh_token=os.environ["TOKEN_" + canal.upper()].strip(),
                       token_uri="https://oauth2.googleapis.com/token",
                       client_id=cs["client_id"], client_secret=cs["client_secret"])
    return build("youtube", "v3", credentials=cred, cache_discovery=False)


def recientes(canal, n=50):
    """Últimos videos del canal: [{titulo, descripcion, fecha (UTC ISO)}]. Usa el permiso de solo lectura."""
    yt = cliente(canal)
    up = "UU" + CANALES[canal][2:]
    r = yt.playlistItems().list(part="snippet", playlistId=up, maxResults=min(n, 50)).execute()
    return [{"titulo": i["snippet"]["title"], "descripcion": i["snippet"].get("description", ""),
             "fecha": i["snippet"].get("publishedAt", "")} for i in r.get("items", [])]


def subidos_hoy(canal, tz_horas=-6):
    """Cuántos videos subió hoy el canal (día según hora de México por defecto)."""
    import datetime as dt
    hoy = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=tz_horas)).date()
    n = 0
    for v in recientes(canal, 15):
        try:
            f = dt.datetime.fromisoformat(v["fecha"].replace("Z", "+00:00")) + dt.timedelta(hours=tz_horas)
            n += f.date() == hoy
        except Exception:
            pass
    return n


def subir(canal, info_path, categoria="25"):
    yt = cliente(canal)
    mio = yt.channels().list(part="id,snippet", mine=True).execute()["items"][0]
    if mio["id"] != CANALES[canal]:
        raise SystemExit(f"ERROR: el token de {canal} es del canal '{mio['snippet']['title']}', no subo nada.")
    info = json.load(open(info_path))
    body = {"snippet": {"title": info["titulo"][:100], "description": info["descripcion"],
                        "tags": info.get("tags", []), "categoryId": categoria},
            "status": {"privacyStatus": os.environ.get("PRIVACY", "public"), "selfDeclaredMadeForKids": False}}
    media = MediaFileUpload(info["ruta"], mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    print(f"SUBIDO {mio['snippet']['title']}: https://youtube.com/shorts/{vid} — {info['titulo']} "
          f"(estado: {resp['status']['privacyStatus']})")
    return vid


if __name__ == "__main__":
    if sys.argv[1] == "hoy":  # python subir.py hoy <canal> <maximo>: imprime "seguir" o "listo"
        n = subidos_hoy(sys.argv[2])
        print("listo" if n >= int(sys.argv[3]) else "seguir")
        print(f"{sys.argv[2]}: {n} subidos hoy", file=sys.stderr)
    else:
        subir(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "25")
