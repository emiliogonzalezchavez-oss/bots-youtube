"""Reconoce una canción con Shazam (shazamio). Lo usan analizar.py y pc_runner.py."""
import asyncio, time


def reconocer(clip, intentos=1, espera=20):
    """Devuelve {"shazam_titulo", "shazam_artista"}; {"shazam_titulo": None, "shazam_sin_match": True} si Shazam no la conoce;
    o None si Shazam falló (frenado, sin internet...) para reintentar luego."""
    from shazamio import Shazam
    for i in range(intentos):
        try:
            sh = Shazam()
            fn = getattr(sh, "recognize", None) or getattr(sh, "recognize_song")
            r = asyncio.run(asyncio.wait_for(fn(clip), 40))
            t = (r or {}).get("track") or {}
            if t:
                return {"shazam_titulo": t.get("title"), "shazam_artista": t.get("subtitle")}
            if isinstance(r, dict) and "matches" in r:
                return {"shazam_titulo": None, "shazam_sin_match": True}
        except Exception:
            pass
        if i < intentos - 1:
            time.sleep(espera * (i + 1))
    return None
