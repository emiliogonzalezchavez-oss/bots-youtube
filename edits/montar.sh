#!/usr/bin/env bash
# Une las tomas (cada una partida en pedazos), aplica flashes y golpes de zoom en los drops,
# el color del plan, viñeta y grano, y mete la música. Uso: bash montar.sh plan.json carpeta_tomas salida.mp4
set -euo pipefail
PLAN=$1; DIR=$2; OUT=$3
python3 - "$PLAN" "$DIR" <<'PY'
import json, os, subprocess, sys, glob
plan = json.load(open(sys.argv[1])); d = sys.argv[2]; fps = plan["fps"]
lista = open("lista.txt", "w")
for i, s in enumerate(plan["shots"]):
    partes = sorted(glob.glob(f"{d}/toma_{i:02d}_*.mp4"))
    if not partes:
        print("falta toma", i); continue
    with open(f"p{i}.txt", "w") as f:
        f.writelines(f"file '{p}'\n" for p in partes)
    vf = []
    if "punch" in s.get("fx", []):   # golpe de zoom: entra al 112% y regresa al 100% en 6 frames
        vf.append("zoompan=z='if(lte(on,6),1.12-0.02*on,1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1080x1920:fps=%d" % fps)
    if "flash" in s.get("fx", []):   # flash blanco que se desvanece en 3 frames
        vf.append("fade=t=in:st=0:d=0.1:color=white")
    vf.append("format=yuv420p")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", f"p{i}.txt",
                    "-vf", ",".join(vf), "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "14", f"s{i:02d}.mp4"], check=True)
    lista.write(f"file 's{i:02d}.mp4'\n")
lista.close()
PY
ffmpeg -y -loglevel error -f concat -safe 0 -i lista.txt -c copy tomas.mp4
MUSIC=$(python3 -c "import json;print(json.load(open('$PLAN'))['music'])")
START=$(python3 -c "import json;print(json.load(open('$PLAN'))['start'])")
COLOR=$(python3 -c "import json;print(json.load(open('$PLAN')).get('color','neutro'))")
case "$COLOR" in
  teal)   GRADE="colorbalance=rs=-0.08:gs=0.02:bs=0.10:rm=-0.05:gm=0.01:bm=0.05:rh=0.05:bh=-0.03,eq=contrast=1.12:saturation=1.20" ;;
  calido) GRADE="colorbalance=rm=0.05:bm=-0.04:rh=0.08:bh=-0.06,eq=contrast=1.10:brightness=0.03:saturation=1.15" ;;
  mono)   GRADE="hue=s=0,eq=contrast=1.20:brightness=0.02" ;;
  *)      GRADE="eq=contrast=1.08:saturation=1.12" ;;
esac
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 tomas.mp4)
FADE=$(python3 -c "print(max(0, $DUR - 0.6))")
ffmpeg -y -loglevel error -i tomas.mp4 -ss "$START" -i "$MUSIC" \
  -filter_complex "[0:v]$GRADE,rgbashift=rh=-2:bh=2,vignette=PI/5,curves=all='0/0.025 1/1',noise=alls=9:allf=t+u,format=yuv420p[v];[1:a]atrim=0:$DUR,afade=t=out:st=$FADE:d=0.6[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -maxrate 14M -bufsize 28M -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT"
ffmpeg -y -loglevel error -i "$OUT" -vf "fps=2,scale=216:-1,tile=8x4" -frames:v 1 "${OUT%.mp4}_hoja.jpg"
echo "LISTO $OUT ($DUR s, color $COLOR)"
