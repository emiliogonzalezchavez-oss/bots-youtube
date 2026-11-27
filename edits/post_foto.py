"""Acabado de foto real para los stills: aberración cromática radial, viñeteo, grano de sensor y EXIF de cámara.
Uso: python3 post_foto.py foto1.jpg [foto2.jpg ...]   (sobrescribe cada JPG)
"""
import sys, datetime
import numpy as np
from PIL import Image
try:
    import piexif
except ImportError:
    piexif = None


def escalar_canal(c, k):
    """amplía un canal k veces desde el centro (aberración cromática lateral)"""
    h, w = c.shape
    im = Image.fromarray(c).resize((round(w * k), round(h * k)), Image.BICUBIC)
    x0 = (im.width - w) // 2; y0 = (im.height - h) // 2
    return np.asarray(im.crop((x0, y0, x0 + w, y0 + h)))


def acabado(ruta, seed=0):
    im = Image.open(ruta).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    h, w, _ = a.shape
    # aberración cromática: rojo un poco más grande, azul un poco más chico (se nota solo en las orillas)
    r = escalar_canal(a[..., 0].astype(np.uint8), 1.0012).astype(np.float32)
    b = escalar_canal(a[..., 2].astype(np.uint8), 0.9988).astype(np.float32)
    a = np.stack([r, a[..., 1], b], -1)
    # viñeteo suave de lente
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
    a *= (1 - 0.28 * d ** 2.2)[..., None]
    # nivel de negro de sensor real: el negro nunca es 0 (sube un poco), así el grano no se "pega" en 0
    a = a * 0.945 + 14.0
    # grano de sensor: más fuerte en sombras, con algo de color
    rng = np.random.default_rng(seed)
    lum = a.mean(-1, keepdims=True) / 255.0
    amp = 3.4 * (1.2 - lum) ** 1.5
    g = rng.normal(0, 1, (h, w, 1)) * amp + rng.normal(0, 0.35, (h, w, 3)) * amp
    a = a + g
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    kw = {"quality": 93, "subsampling": 0}
    if piexif:
        ahora = datetime.datetime.now().strftime("%Y:%m:%d %H:%M:%S")
        exif = {"0th": {piexif.ImageIFD.Make: b"SONY", piexif.ImageIFD.Model: b"ILCE-7RM4", piexif.ImageIFD.Software: b"ILCE-7RM4 v2.00"},
                "Exif": {piexif.ExifIFD.DateTimeOriginal: ahora.encode(), piexif.ExifIFD.FNumber: (28, 10),
                         piexif.ExifIFD.ExposureTime: (1, 125), piexif.ExifIFD.ISOSpeedRatings: 200,
                         piexif.ExifIFD.FocalLength: (85, 1), piexif.ExifIFD.LensModel: b"FE 85mm F1.4 GM"}}
        kw["exif"] = piexif.dump(exif)
    out.save(ruta, "JPEG", **kw)
    print("acabado", ruta)


for i, f in enumerate(sys.argv[1:]):
    acabado(f, i)
