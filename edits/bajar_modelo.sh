#!/usr/bin/env bash
# Baja un modelo de Sketchfab (necesita el secret SKETCHFAB_TOKEN). Uso: bash bajar_modelo.sh <uid> <carpeta>
set -euo pipefail
UID_M=$1; DIR=$2; mkdir -p "$DIR"
J=$(curl -sf -H "Authorization: Token $SKETCHFAB_TOKEN" "https://api.sketchfab.com/v3/models/$UID_M/download")
GLB=$(echo "$J" | python3 -c "import sys,json;d=json.load(sys.stdin);print((d.get('glb') or {}).get('url',''))")
if [ -n "$GLB" ]; then
  curl -sfL "$GLB" -o "$DIR/modelo.glb"; echo "$DIR/modelo.glb"
else
  URL=$(echo "$J" | python3 -c "import sys,json;print(json.load(sys.stdin)['gltf']['url'])")
  curl -sfL "$URL" -o "$DIR/m.zip"; unzip -q -o "$DIR/m.zip" -d "$DIR"; ls "$DIR"/*.gltf | head -1
fi
