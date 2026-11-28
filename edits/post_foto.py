"""Acabado de foto real para los stills: aberración cromática radial, viñeteo, grano de sensor y EXIF de cámara.
Uso: python3 post_foto.py foto1.jpg [foto2.jpg ...]   (sobrescribe cada JPG)
"""
import sys, datetime, io
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
    # se trabaja en flotante desde un PNG de 16 bits si existe (sin escalones ni bloques en los negros)
    a = None
    try:
        import cv2
        b16 = cv2.imread(ruta, cv2.IMREAD_UNCHANGED)
        if b16 is not None and b16.dtype == np.uint16:
            a = cv2.cvtColor(b16, cv2.COLOR_BGR2RGB).astype(np.float32) / 257.0
            if max(a.shape[:2]) > 2600:   # supermuestreo: al doble -> mitad con Lanczos
                a = cv2.resize(a, (a.shape[1] // 2, a.shape[0] // 2), interpolation=cv2.INTER_LANCZOS4)
            bl = cv2.GaussianBlur(a, (0, 0), 0.8)
            dif = a - bl
            a = a + 0.4 * dif * (np.abs(dif) > 2)             # unsharp mask 0.8 px, 40 %, umbral 2
    except ImportError:
        pass
    if a is None:
        im = Image.open(ruta).convert("RGB")
        if max(im.size) > 2600:
            im = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
        from PIL import ImageFilter
        im = im.filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=2))
        a = np.asarray(im).astype(np.float32)
    h, w, _ = a.shape
    # aberración cromática: rojo un poco más grande, azul un poco más chico (se nota solo en las orillas)
    r = escalar_canal(a[..., 0].astype(np.uint8), 1.0012).astype(np.float32)
    b = escalar_canal(a[..., 2].astype(np.uint8), 0.9988).astype(np.float32)
    yy0, xx0 = np.mgrid[0:h, 0:w]
    rad = np.sqrt(((xx0 - w / 2) / (w / 2)) ** 2 + ((yy0 - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
    mk = np.clip((rad - 0.5) / 0.5, 0, 1) ** 2          # 0 en el centro, solo aparece en las orillas
    a = np.stack([a[..., 0] * (1 - mk) + r * mk, a[..., 1], a[..., 2] * (1 - mk) + b * mk], -1)
    # viñeteo suave de lente
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) / np.sqrt(2)
    a *= (1 - 0.28 * d ** 2.2)[..., None]
    # nivel de negro de sensor real: el negro nunca es 0 (sube un poco), así el grano no se "pega" en 0
    a = a * 0.955 + 11.0
    # grano de sensor: más fuerte en sombras, con algo de color
    rng = np.random.default_rng(seed)
    lum = a.mean(-1, keepdims=True) / 255.0
    amp = 1.7 * (1.2 - lum) ** 1.2      # grano bajo, solo de luminancia (sin motitas de color en el negro)
    g = rng.normal(0, 1, (h, w)).astype(np.float32)
    k = np.array([0.25, 0.5, 0.25], np.float32)        # grano suave como sensor real tras demosaico, no pixel duro
    g = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 1, g)
    g = np.apply_along_axis(lambda v: np.convolve(v, k, "same"), 0, g) * 1.6
    a = a + g[..., None] * amp
    a = a + rng.uniform(-0.5, 0.5, a.shape)            # dither para cuantizar a 8 bits sin escalones
    out = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    kw = {"quality": 97, "subsampling": 0}
    if piexif:
        ahora = datetime.datetime.now()
        f = ahora.strftime("%Y:%m:%d %H:%M:%S").encode()
        f_toma = (ahora - datetime.timedelta(minutes=37)).strftime("%Y:%m:%d %H:%M:%S").encode()
        mini = io.BytesIO(); t = out.copy(); t.thumbnail((160, 120)); t.save(mini, "JPEG", quality=80)
        I, E = piexif.ImageIFD, piexif.ExifIFD
        exif = {
            "0th": {I.Make: b"SONY", I.Model: b"ILCE-7RM4", I.Orientation: 1, I.XResolution: (240, 1), I.YResolution: (240, 1),
                    I.ResolutionUnit: 2, I.Software: b"Adobe Lightroom Classic 13.1 (Windows)", I.DateTime: f},
            "Exif": {E.ExposureTime: (1, 125), E.FNumber: (28, 10), E.ExposureProgram: 1, E.ISOSpeedRatings: 200,
                     E.SensitivityType: 2, E.RecommendedExposureIndex: 200, E.ExifVersion: b"0231",
                     E.DateTimeOriginal: f_toma, E.DateTimeDigitized: f_toma, E.OffsetTime: b"+00:00",
                     E.OffsetTimeOriginal: b"+00:00", E.OffsetTimeDigitized: b"+00:00",
                     E.ShutterSpeedValue: (6965784, 1000000), E.ApertureValue: (2970854, 1000000),
                     E.BrightnessValue: (-1, 100), E.ExposureBiasValue: (0, 10), E.MaxApertureValue: (970854, 1000000),
                     E.MeteringMode: 5, E.LightSource: 0, E.Flash: 16, E.FocalLength: (85, 1),
                     E.ColorSpace: 1, E.PixelXDimension: out.width, E.PixelYDimension: out.height,
                     E.FileSource: b"\x03", E.SceneType: b"\x01", E.CustomRendered: 0, E.ExposureMode: 1,
                     E.WhiteBalance: 1, E.DigitalZoomRatio: (1, 1), E.FocalLengthIn35mmFilm: 85, E.SceneCaptureType: 0,
                     E.Contrast: 0, E.Saturation: 0, E.Sharpness: 0,
                     E.LensSpecification: ((85, 1), (85, 1), (14, 10), (14, 10)), E.LensModel: b"FE 85mm F1.4 GM"},
            "1st": {I.Compression: 6, I.XResolution: (72, 1), I.YResolution: (72, 1), I.ResolutionUnit: 2},
            "thumbnail": mini.getvalue()}
        kw["exif"] = piexif.dump(exif)
    ruta = ruta.rsplit(".", 1)[0] + ".jpg"
    out.save(ruta, "JPEG", **kw)
    print("acabado", ruta)


for i, f in enumerate(sys.argv[1:]):
    acabado(f, i)
