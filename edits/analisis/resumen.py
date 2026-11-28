"""Cruza las medidas de cada edit con vistas/subs y saca la fórmula.
Uso: python resumen.py videos.json feat_dir salida_dir
"""
import json, os, sys
from collections import Counter
import numpy as np
import pandas as pd

vids = json.load(open(sys.argv[1]))
FD, OUT = sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
rows, errores = [], Counter()
for f in os.listdir(FD):
    if not f.endswith(".json"):
        continue
    ft = json.load(open(os.path.join(FD, f)))
    if "error" in ft:
        errores[ft["error"][:80]] += 1
        continue
    v = vids.get(ft["id"])
    if v:
        r = {**v, **ft}
        r.pop("cortes_t", None); r.pop("tags", None)
        rows.append(r)
df = pd.DataFrame(rows)
if df.empty:
    open(os.path.join(OUT, "resumen.md"), "w").write(f"# Sin datos\nErrores: {dict(errores.most_common(10))}\n")
    sys.exit()
df = df[df["duracion_s"] <= 180]
df["log_vistas"] = np.log10(df["vistas"] + 1)
df["log_viral"] = np.log10(df["viral"] + 1e-3)
df["log_vistas_dia"] = np.log10(df["vistas_dia"] + 1)
df["likes_por_vista"] = df["likes"] / df["vistas"].clip(lower=1)
df["coment_por_vista"] = df["comentarios"] / df["vistas"].clip(lower=1)
df.to_csv(os.path.join(OUT, "datos.csv"), index=False)

FEATS = ["duracion_s", "cortes", "cortes_por_seg", "toma_media", "toma_mediana", "toma_min", "toma_max", "variedad_ritmo",
         "primer_corte_s", "cortes_1s", "cortes_3s", "brillo", "brillo_std", "saturacion", "temperatura", "movimiento",
         "movimiento_p90", "flashes_por_seg", "negros_pct", "loop_similitud", "tempo", "drop_t", "drop_pct", "drop_salto",
         "cortes_en_beat", "cortes_en_onset", "energia_inicio", "corte_en_drop", "toma_media_antes_drop",
         "toma_media_despues_drop", "res"]
FEATS = [f for f in FEATS if f in df]
for f in FEATS:
    df[f] = pd.to_numeric(df[f], errors="coerce")
L = [f"# Fórmula de edits de coches — {len(df)} edits analizados\n",
     f"Errores de descarga: {sum(errores.values())} ({dict(errores.most_common(3))})\n",
     "Correlación de Spearman (−1 a 1). viral = vistas ÷ subs del canal (quita el efecto de canales grandes).\n",
     "| medida | vistas | viral | vistas/día | likes/vista |", "|---|---|---|---|---|"]
cor = []
for f in FEATS:
    c = [df[f].corr(df[t], method="spearman") for t in ("log_vistas", "log_viral", "log_vistas_dia", "likes_por_vista")]
    cor.append((f, c))
cor.sort(key=lambda x: -abs(np.nan_to_num(x[1][1])))
for f, c in cor:
    L.append(f"| {f} | " + " | ".join(f"{x:+.2f}" if pd.notna(x) else "—" for x in c) + " |")

top = df[df["viral"] >= df["viral"].quantile(0.9)]
mal = df[df["viral"] <= df["viral"].quantile(0.5)]
L += ["\n## Top 10% más virales vs. mitad de abajo (medianas)\n", f"Top: {len(top)} edits · Abajo: {len(mal)} edits\n",
      "| medida | top 10% | mitad baja | todos |", "|---|---|---|---|"]
for f in FEATS:
    L.append(f"| {f} | {top[f].median():.3g} | {mal[f].median():.3g} | {df[f].median():.3g} |")

L.append("\n## Canciones más usadas en el top 10%\n")
canc = Counter(f"{a} — {t}" for a, t in zip(top["artist"].fillna("?"), top["track"].fillna("?")) if t != "?")
for k, n in canc.most_common(25):
    L.append(f"- {k}: {n}")
L.append("\n## Canciones más usadas en general\n")
for k, n in Counter(f"{a} — {t}" for a, t in zip(df["artist"].fillna("?"), df["track"].fillna("?")) if t != "?").most_common(25):
    L.append(f"- {k}: {n}")

L.append("\n## Top 40 por viralidad\n")
L.append("| vistas | subs | viral | dur | cortes/s | en beat | drop % | loop | canción | link |")
L.append("|---|---|---|---|---|---|---|---|---|---|")
for _, r in df.sort_values("viral", ascending=False).head(40).iterrows():
    L.append(f"| {r['vistas']:,} | {r['subs'] if pd.notna(r['subs']) else '?'} | {r['viral']:.1f} | {r['duracion_s']:.0f} | "
             f"{r['cortes_por_seg']:.2f} | {r.get('cortes_en_beat', float('nan')):.2f} | {r.get('drop_pct', float('nan')):.2f} | "
             f"{r['loop_similitud']:.2f} | {(r['track'] or '')[:30]} | https://youtu.be/{r['id']} |")
open(os.path.join(OUT, "resumen.md"), "w").write("\n".join(L) + "\n")
print("\n".join(L[:60]))
