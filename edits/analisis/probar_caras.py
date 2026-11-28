"""Prueba del detector de caras YuNet: filas 0 y 3 de prueba_hojas.jpg tienen gente, fila 2 es un McLaren (manos, sin caras)."""
import os, sys
import cv2, numpy as np
M = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yunet.onnx")


def detectar(img, det):
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, f = det.detect(img)
    return [] if f is None else [x for x in f if x[2] >= 0.05 * w]


det = cv2.FaceDetectorYN.create(M, "", (360, 640), 0.7, 0.3, 50)
im = cv2.imread(os.path.join(os.path.dirname(M), "prueba_hojas.jpg"))
for r in range(4):
    n = sum(len(detectar(cv2.resize(im[r*160:(r+1)*160, k*90:(k+1)*90], (360, 640)), det)) > 0 for k in range(8))
    print("fila", r, "cuadros con cara", n, "/ 8")
if len(sys.argv) > 1:
    foto = cv2.imread(sys.argv[1]); print("foto con cara:", len(detectar(foto, det)))
