#!/bin/bash
# Video de prueba: 12 s, 120 BPM (beat cada 0.5 s). Cortes de color en cada beat hasta 4 s, luego cada 0.25 s.
# Audio: tono suave 0-4 s y bombo + bajo fuerte desde 4 s (drop en 4.0 s). Se espera: drop_t≈4, cortes_en_beat alto.
set -e
cd "$(mktemp -d)"
i=0; : > lista.txt
for t in $(python3 -c "print(' '.join(str(x) for x in [0.5]*8+[0.25]*16))"); do
  c=$(python3 -c "import random;print('#%06x'%random.randint(0,0xffffff))")
  ffmpeg -loglevel error -y -f lavfi -i "color=c=$c:s=540x960:r=30:d=$t" -vf "drawbox=x=$((i*20%400)):y=300:w=120:h=120:c=white:t=fill" seg$i.mp4
  echo "file seg$i.mp4" >> lista.txt; i=$((i+1))
done
ffmpeg -loglevel error -y -f concat -i lista.txt -c copy v.mp4
ffmpeg -loglevel error -y -f lavfi -i "sine=f=440:d=4" -af "volume=0.05" a1.wav
ffmpeg -loglevel error -y -f lavfi -i "aevalsrc='0.9*sin(2*PI*55*t)*exp(-8*mod(t,0.5))':d=8:s=22050" a2.wav
ffmpeg -loglevel error -y -i a1.wav -i a2.wav -filter_complex "[0][1]concat=n=2:v=0:a=1" a.wav
ffmpeg -loglevel error -y -i v.mp4 -i a.wav -shortest -c:v copy -c:a aac prueba.mp4
echo '{"x": {"id": "x", "vistas": 1}}' > vids.json; echo x > ids.txt
VIDEO_LOCAL=$PWD/prueba.mp4 python3 "$1/analizar.py" vids.json ids.txt out
python3 -c "import json;d=json.load(open('out/x.json'));[print(k,'=',v) for k,v in d.items() if k!='cortes_t'];print('cortes_t', d.get('cortes_t'))"
# --- prueba 2: Shazam con una canción real (ejemplo de librosa) ---
python3 -c "import librosa,soundfile as sf;y,sr=librosa.load(librosa.ex('nutcracker'),duration=40);sf.write('musica.wav',y,sr)"
ffmpeg -loglevel error -y -i v.mp4 -stream_loop 4 -i v.mp4 -i musica.wav -map 1:v -map 2:a -t 30 -c:v libx264 -c:a aac prueba2.mp4 2>/dev/null || ffmpeg -loglevel error -y -stream_loop 4 -i v.mp4 -i musica.wav -map 0:v -map 1:a -t 30 -c:v libx264 -c:a aac prueba2.mp4
echo '{"y": {"id": "y", "vistas": 1}}' > vids2.json; echo y > ids2.txt
SHAZAM=1 SHAZAM_DIRECTO=1 VIDEO_LOCAL=$PWD/prueba2.mp4 python3 "$1/analizar.py" vids2.json ids2.txt out2
python3 -c "import json;d=json.load(open('out2/y.json'));print({k:d.get(k) for k in ('shazam_titulo','shazam_artista','shazam_error','error','drop_t','tempo')})"
# --- prueba 3: pc_runner completo (lista real de GitHub, filtro, 2 procesos, zip) con video local ---
mkdir -p pc && cp "$1/analizar.py" "$1/pc_runner.py" pc/
LIMITE=4 PROCESOS=2 VIDEO_LOCAL=$PWD/prueba.mp4 python3 pc/pc_runner.py
python3 -c "import zipfile;z=zipfile.ZipFile('pc/resultados.zip');n=z.namelist();print('zip:',len(n),'archivos',n[:4])"
python3 -c "import json,glob;[print(f, json.load(open(f)).get('caras_pct')) for f in glob.glob('pc/feat/*.json')]"; ls -la pc/yunet.onnx
# --- prueba 4: Shazam falla -> guarda clip -> el hilo de pc_runner lo reconoce después ---
mkdir -p pc2 && cp "$1/analizar.py" "$1/pc_runner.py" "$1/reconocer.py" "$1/yunet.onnx" pc2/
LIMITE=3 PROCESOS=2 VIDEO_LOCAL=$PWD/prueba2.mp4 python3 pc2/pc_runner.py
cat pc2/shazam_log.txt; python3 -c "import json,glob;[print('CANCION', f[-16:], json.load(open(f)).get('shazam_titulo'), json.load(open(f)).get('shazam_pendiente')) for f in glob.glob('pc2/feat/*.json')]"; ls pc2/clips 2>/dev/null | wc -l
# --- prueba 5: solo_canciones.txt -> no baja nada y termina las canciones pendientes ---
rm -f pc2/shazam_log.txt; touch pc2/solo_canciones.txt
cp "$1/pc_runner.py" pc2/ && PROCESOS=2 VIDEO_LOCAL=$PWD/prueba2.mp4 python3 pc2/pc_runner.py | grep -E "solo_canciones|por medir|Medición|Listo"
