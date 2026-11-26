"""Arma título, descripción y tags del edit (con créditos del modelo 3D y la música).
Uso: python edits/publicar.py plan.json edit.mp4 salida.json"""
import json, os, random, sys

plan = json.load(open(sys.argv[1]))
mods = {m["uid"]: m for m in json.load(open(os.path.join(os.path.dirname(__file__), "modelos.json")))}
musica = {m["mp3"]: m for m in json.load(open(os.path.join(os.path.dirname(__file__), "musica.json")))}
m = mods.get(plan.get("modelo_uid"), {})
coche = m.get("nombre", "Supercar")
mu = musica.get(plan.get("musica_url"), {})
emoji = random.choice(["🔥", "🏁", "😮‍💨", "⚡", "🖤"])
marca = coche.split()[1] if coche[:4].isdigit() and len(coche.split()) > 1 else coche.split()[0]
tags = [coche, marca, "car edit", "phonk", "cars", "car edits", "supercar", "shorts", "edit"]
desc = (f"{coche} {emoji}\n\n🔔 Suscríbete para un edit nuevo cada día.\n\n"
        f"Modelo 3D: \"{coche}\" de {m.get('autor', '?')} (https://sketchfab.com/3d-models/{plan.get('modelo_uid', '')}), "
        f"licencia {m.get('licencia', '?')}. Render y edición propios.\n"
        f"Música: {mu.get('nombre', 'phonk libre de derechos')} (Pixabay{', ' + mu['pagina'] if mu.get('pagina') else ''}).\n\n"
        f"#{marca.lower()} #caredit #phonk #cars #shorts")
info = {"ruta": sys.argv[2], "titulo": f"{coche} {emoji} #shorts"[:100], "descripcion": desc, "tags": tags}
json.dump(info, open(sys.argv[3], "w"), ensure_ascii=False)
print(json.dumps(info, ensure_ascii=False, indent=1))
