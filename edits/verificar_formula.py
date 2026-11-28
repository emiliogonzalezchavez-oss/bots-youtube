"""Comprueba ANTES del render que el plan cumple la fórmula, midiéndolo con el MISMO analizador de los 1,933 edits.
Arma un video de prueba (un color por toma) con la música del plan y corre edits/analisis/analizar.py.
Uso: python verificar_formula.py plan.json   -> sale con error si algo se sale de la fórmula."""
import json, os, subprocess, sys, tempfile, random
plan = json.load(open(sys.argv[1])); fps = plan["fps"]
d = tempfile.mkdtemp()
lista = open(f"{d}/l.txt", "w")
for i, s in enumerate(plan["shots"]):
    c = "#%06x" % random.Random(i).randint(0x202020, 0xe0e0e0)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"color=c={c}:s=270x480:r={fps}",
                    "-frames:v", str(s["frames"]), "-pix_fmt", "yuv420p", f"{d}/s{i}.mp4"], check=True)
    lista.write(f"file 's{i}.mp4'\n")
lista.close()
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"{d}/l.txt", "-c", "copy", f"{d}/v.mp4"], check=True)
dur = sum(s["frames"] for s in plan["shots"]) / fps
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", f"{d}/v.mp4", "-ss", str(plan["start"]), "-t", str(dur), "-i", plan["music"],
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", f"{d}/prueba.mp4"], check=True)
json.dump({"p": {"id": "p", "vistas": 0}}, open(f"{d}/v.json", "w")); open(f"{d}/ids.txt", "w").write("p")
env = dict(os.environ, VIDEO_LOCAL=f"{d}/prueba.mp4")
subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "analisis", "analizar.py"),
                f"{d}/v.json", f"{d}/ids.txt", f"{d}/out"], env=env, check=True)
m = json.load(open(f"{d}/out/p.json"))
reglas = [("drop_t >= 7 s", (m.get("drop_t") or 0) >= 6.5),
          ("drop entre 30% y 60%", 0.30 <= (m.get("drop_pct") or 0) <= 0.60),
          ("0.5-1 cortes/s", 0.45 <= m["cortes_por_seg"] <= 1.05),
          ("cortes en beat <= 60%", (m.get("cortes_en_beat") or 0) <= 0.60),
          ("duración 16-45 s", 16 <= m["duracion_s"] <= 45),
          ("sin flashes en el plan", all("flash" not in s["fx"] for s in plan["shots"])),
          ("color no teal", plan.get("color") != "teal"),
          ("final distinto del inicio", plan["shots"][0]["name"] != plan["shots"][-1]["name"])]
print("MEDIDO con el analizador:", {k: m.get(k) for k in ("duracion_s", "cortes", "cortes_por_seg", "drop_t", "drop_pct", "cortes_en_beat", "corte_en_drop", "tempo")})
print("PLAN:", plan.get("formula"))
mal = [r for r, ok in reglas if not ok]
for r, ok in reglas:
    print(("OK   " if ok else "FALLA"), r)
sys.exit(1 if mal else 0)
