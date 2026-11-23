#!/usr/bin/env bash
# Une las tomas, mete la música (cortada en el tramo del plan) y le da el look de edit.
# Uso: bash montar.sh plan.json carpeta_tomas salida.mp4
set -euo pipefail
PLAN=$1; DIR=$2; OUT=$3
MUSIC=$(python3 -c "import json;print(json.load(open('$PLAN'))['music'])")
START=$(python3 -c "import json;print(json.load(open('$PLAN'))['start'])")
ls "$DIR"/toma_*.mp4 | sort | sed "s/^/file '/; s/$/'/" > lista.txt
ffmpeg -y -loglevel error -f concat -safe 0 -i lista.txt -c copy tomas.mp4
DUR=$(ffprobe -v error -show_entries format=duration -of csv=p=0 tomas.mp4)
FADE=$(python3 -c "print(max(0, $DUR - 0.8))")
# Look: contraste, un poco más de saturación, viñeta y grano fino
ffmpeg -y -loglevel error -i tomas.mp4 -ss "$START" -i "$MUSIC" \
  -filter_complex "[0:v]eq=contrast=1.08:saturation=1.12,vignette=PI/5,noise=alls=5:allf=t,format=yuv420p[v];[1:a]atrim=0:$DUR,afade=t=out:st=$FADE:d=0.8[a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -c:a aac -b:a 192k -movflags +faststart -shortest "$OUT"
# Hoja de contacto para revisar rápido
ffmpeg -y -loglevel error -i "$OUT" -vf "fps=2,scale=216:-1,tile=8x4" -frames:v 1 "${OUT%.mp4}_hoja.jpg"
echo "LISTO $OUT ($DUR s)"
