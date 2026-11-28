@echo off
chcp 65001 >nul
title Analizador de edits - Nightshift Garage
cd /d "%~dp0"
echo === Analizador de edits ===
py -3 --version >nul 2>nul && set "PY=py -3" && goto ok
python --version >nul 2>nul && set "PY=python" && goto ok
echo Instalando Python (una sola vez)...
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
echo.
echo Python instalado. CIERRA esta ventana y vuelve a abrir el .bat
pause
exit /b
:ok
if not exist venv\Scripts\python.exe (
  echo Creando entorno...
  %PY% -m venv venv
)
echo Instalando/actualizando herramientas (la primera vez tarda unos minutos)...
venv\Scripts\python.exe -m pip install -q --upgrade pip
venv\Scripts\python.exe -m pip install -q -U yt-dlp "scenedetect[opencv-headless]" librosa numpy imageio-ffmpeg
curl -sL -o analizar.py https://raw.githubusercontent.com/emiliogonzalezchavez-oss/bots-youtube/main/edits/analisis/analizar.py
curl -sL -o pc_runner.py https://raw.githubusercontent.com/emiliogonzalezchavez-oss/bots-youtube/main/edits/analisis/pc_runner.py
venv\Scripts\python.exe pc_runner.py
pause
