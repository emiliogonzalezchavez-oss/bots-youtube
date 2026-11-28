"""¿Una canción es libre para monetizar? Busca en el catálogo de NCS (ncs.io) y en musica.json (Pixabay).
Si no aparece en ninguno: "con copyright (probable)". Guarda caché para no repetir búsquedas."""
import json, os, re, time, unicodedata, urllib.parse, urllib.request

AQUI = os.path.dirname(os.path.abspath(__file__))


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[\(\[].*?[\)\]]", " ", s)                    # quita (Slowed), [Remix], (feat. X)...
    s = re.sub(r"\b(feat|ft|slowed|reverb|sped up|super|ultra|remix|edit|version)\b.*", " ", s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def artistas(s):
    partes = re.split(r"\s*(?:,|&|\bx\b|\bfeat\b\.?|\bft\b\.?|\band\b)\s*", norm_artist(s))
    return {re.sub(r"[^a-z0-9 ]+", "", a).strip() for a in partes if a.strip()}


def norm_artist(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9,&. ]+", " ", s)


def buscar_ncs(titulo):
    url = "https://ncs.io/music-search?q=" + urllib.parse.quote(titulo)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    filas = []
    for m in re.finditer(r'class="lrow-m"><a[^>]*class="t"[^>]*href="(/[^"]+)">([^<]+)</a><span class="a">(.*?)</span></span></span>', html):
        arts = re.findall(r'href="/artist/[^"]+">([^<]+)</a>', m.group(3))
        filas.append({"titulo": m.group(2), "artistas": arts, "url": "https://ncs.io" + m.group(1)})
    return filas


def es_libre(artista, titulo, cache):
    """Devuelve (tipo, fuente): ("libre", "NCS: url") / ("libre", "Pixabay") / ("copyright", None)."""
    clave = f"{artista} — {titulo}"
    if clave in cache:
        return tuple(cache[clave])
    res = ("copyright", None)
    try:   # canciones que ya usamos (musica.json: "Artista - Título")
        musica = json.load(open(os.path.join(AQUI, "..", "musica.json"), encoding="utf-8"))
        for m in (musica if isinstance(musica, list) else musica.values()):
            nombre = m.get("titulo") or m.get("nombre") or m.get("title") or ""
            a_m, _, t = nombre.rpartition(" - ")
            mismo_artista = not artista or not a_m or (artistas(artista) & artistas(a_m))
            if norm(titulo) and norm(t) == norm(titulo) and mismo_artista:
                res = ("libre", ("NCS: " if "ncs.io" in str(m.get("pagina", "")) else "musica.json: ") + str(m.get("pagina", nombre)))
                break
    except Exception:
        pass
    if res[0] != "libre":
        try:
            a_q = artistas(artista)
            for f in buscar_ncs(norm(titulo) or titulo):
                if norm(f["titulo"]) == norm(titulo) and (not a_q or a_q & set().union(*[artistas(x) for x in f["artistas"]])):
                    res = ("libre", "NCS: " + f["url"]); break
            time.sleep(1)
        except Exception as e:
            return ("sin_verificar", str(e)[:80])   # sin internet: no se guarda en caché
    cache[clave] = list(res)
    return res
