#!/usr/bin/env bash
# Baja un HDRI de estudio fotográfico (Poly Haven, CC0) solo para los REFLEJOS de la pintura en el look estudio.
# Uso: bash bajar_estudio.sh salida.hdr
set -uo pipefail
for H in $(python3 -c "import random;l=['studio_small_08','studio_small_02','studio_small_09','studio_small_03','studio_small_05'];random.shuffle(l);print(' '.join(l))"); do
  if curl -sfL "https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/${H}_2k.hdr" -o "$1" && [ -s "$1" ]; then echo "Estudio HDRI: $H"; exit 0; fi
done
echo "sin HDRI de estudio"; exit 1
