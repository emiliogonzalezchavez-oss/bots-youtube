"""Edit de coche estilo comercial de estudio (Blender, headless, Cycles CPU).

Uso:
  blender -b -P edits/blender_edit.py -- --car modelo.glb --plan plan.json --shot 0 --out salida/ [--still]

REGLAS DE CALIDAD (no negociables):
- Nunca modelar el coche con primitivas. Solo modelos profesionales importados que pasaron la revisión
  (ver edits/modelos.json, campo "aprobado"). Si un modelo no se ve real en el still de prueba, NO se usa.
- Look de estudio: fondo negro infinito, piso oscuro semibrillante, softboxes grandes que dibujan
  las líneas de la carrocería, luces del coche encendidas.
- Cámara lenta y cinematográfica (50-100 mm, f/2.8-4, desenfoque), tomas de detalle; el coche quieto.
- Render: 1080x1920, Cycles con muchos samples + OpenImageDenoise, AgX.
"""
import argparse, json, math, os, sys
import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--car", required=True)
ap.add_argument("--plan", required=True)
ap.add_argument("--shot", type=int, default=0)
ap.add_argument("--out", required=True)
ap.add_argument("--front", default="auto", help="+X -X +Y -Y o auto")
ap.add_argument("--girar", action="store_true", help="girar 180° (frente detectado al revés)")
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--still", action="store_true", help="1 frame a resolución completa (revisión de calidad)")
ap.add_argument("--uid", default="", help="uid de Sketchfab (para los overrides de materiales en modelos.json)")
ap.add_argument("--dump", action="store_true", help="solo lista materiales de luces/vidrios y sale")
ap.add_argument("--rango", default="", help="frames a renderizar, ej. 13-24 (para repartir una toma en varios servidores)")
A = ap.parse_args(argv)
PLAN = json.load(open(A.plan))
SHOT = PLAN["shots"][A.shot]
FPS = PLAN.get("fps", 30)
N = SHOT["frames"]
LARGO = 4.6  # todos los coches se escalan a 4.6 m de largo

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N


def link(ob):
    sc.collection.objects.link(ob)
    return ob


def empty(name, loc=(0, 0, 0), parent=None):
    e = link(bpy.data.objects.new(name, None))
    e.location = loc
    e.parent = parent
    return e


def meshes(objs):
    return [o for o in objs if o.type == "MESH"]


def bbox_robusto(objs, q=0.4):
    """bbox ignorando antenas, espejos sueltos y basura: percentiles de los vértices"""
    import numpy as np
    pts = []
    for o in meshes(objs):
        n = len(o.data.vertices)
        if n == 0:
            continue
        co = np.empty(n * 3, dtype=np.float32); o.data.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        if n > 20000:
            co = co[np.random.default_rng(0).choice(n, 20000, replace=False)]
        M = np.array(o.matrix_world)
        pts.append(co @ M[:3, :3].T + M[:3, 3])
    P = np.concatenate(pts)
    lo, hi = np.percentile(P, q, axis=0), np.percentile(P, 100 - q, axis=0)
    return Vector(lo.tolist()), Vector(hi.tolist())


def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in meshes(objs) for c in o.bound_box]
    return (Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))),
            Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts))))


# ------------------------------------------------------------------ importar el coche
ext = os.path.splitext(A.car)[1].lower()
if ext in (".glb", ".gltf"):
    bpy.ops.import_scene.gltf(filepath=A.car)
elif ext == ".fbx":
    bpy.ops.import_scene.fbx(filepath=A.car)
objs = list(sc.objects)

# Quitar lo que no es el coche: pisos, sombras falsas, fondos, cámaras y luces del autor
BASURA = ("ground", "floor", "shadow", "backdrop", "background", "studio", "cyclorama", "skydome", "piso")
for o in list(objs):
    if o.type in ("CAMERA", "LIGHT") or (o.type == "MESH" and any(b in o.name.lower() for b in BASURA)):
        objs.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)
bpy.context.view_layer.update()
mn, mx = bbox(objs)
big = max(mx - mn)
for o in list(meshes(objs)):  # placas enormes y planas = piso del autor
    a, b = bbox([o])
    d = b - a
    if d.z < 0.01 * max(d.x, d.y) and max(d.x, d.y) > 0.8 * big:
        objs.remove(o)
        bpy.data.objects.remove(o, do_unlink=True)

car = empty("CarRig")
bpy.context.view_layer.update()
for o in objs:
    if o.parent is None:
        mw = o.matrix_world.copy()
        o.parent = car
        o.matrix_parent_inverse = Matrix()
        o.matrix_world = mw
bpy.context.view_layer.update()

# Orientación: el largo es el eje horizontal más grande; el frente se detecta por los faros
mn, mx = bbox_robusto(objs)
dims = mx - mn
eje = "X" if dims.x >= dims.y else "Y"
front = A.front
if front == "auto":
    c = (mn + mx) / 2
    def txt(o):
        return (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()
    heads = [o for o in meshes(objs) if any(k in txt(o) for k in ("headl", "head_l", "headlight", "head light", "faro"))]
    if heads:
        a, b = bbox(heads)
        hv = (a + b) / 2 - c
        front = ("+" if (hv.x if eje == "X" else hv.y) > 0 else "-") + eje
    else:
        front = "+" + eje
ang = {"+X": 0, "-X": math.pi, "+Y": math.pi / 2, "-Y": -math.pi / 2}[front] + (math.pi if A.girar else 0)
center = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
car.matrix_world = Matrix.Rotation(-ang, 4, "Z") @ Matrix.Translation(-center)
bpy.context.view_layer.update()
mn, mx = bbox_robusto(objs)
k = LARGO / (mx.x - mn.x)
car.matrix_world = Matrix.Scale(k, 4) @ car.matrix_world
bpy.context.view_layer.update()
mn, mx = bbox_robusto(objs)
# Llantas apoyadas en el piso: se usa lo más bajo de las LLANTAS (no de cualquier pieza que cuelgue)
# y se hunden 1.2 cm para que se aplaste el contacto como en una llanta real.
_ll = [o for o in meshes(objs) if any(k in (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()
                                      for k in ("tire", "tyre", "rubber", "llanta", "neum", "reifen", "wheel"))]
_zl = min((o.matrix_world @ v.co).z for o in _ll for v in o.data.vertices) if _ll else bbox(objs)[0].z
car.location.z -= _zl + 0.025
print(f"APOYO llantas={len(_ll)} z_llanta={_zl:.3f} z_min_total={bbox(objs)[0].z:.3f}")
bpy.context.view_layer.update()
MANEJO_SHOT = SHOT["name"].startswith("manejo") or SHOT["name"] == "rueda_gira"


def aplastar_llantas():
    """llanta con peso: la parte que toca se aplana (parche de contacto) y el costado se abomba un poco"""
    n = 0
    for o in _ll:
        nm = txt_(o)
        if not any(k in nm for k in ("tire", "tyre", "rubber", "llanta", "neum", "reifen")):
            continue
        if o.data.users > 1:
            o.data = o.data.copy()
        mw = o.matrix_world; inv = mw.inverted()
        cy = (mw @ Vector(o.bound_box[0]).lerp(Vector(o.bound_box[6]), 0.5)).y
        for v in o.data.vertices:
            w = mw @ v.co
            if w.z < 0.12:
                if w.z < 0.003:
                    w.z = 0.003                                    # parche plano pegado al piso
                bulge = ((0.12 - max(w.z, 0.0)) / 0.12) ** 1.5 * 0.026   # costado abombado (hasta 2.6 cm)
                w.y += bulge if w.y > cy else -bulge
                v.co = inv @ w
                n += 1
    print("LLANTAS aplastadas, vertices:", n)


def txt_(o):
    return (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()


if not MANEJO_SHOT:
    aplastar_llantas()
    bpy.context.view_layer.update()
mn, mx = bbox_robusto(objs)
L, W, H = mx.x - mn.x, mx.y - mn.y, mx.z - mn.z
print(f"COCHE L={L:.2f} W={W:.2f} H={H:.2f} frente={front} objetos={len(objs)}")

# ---------------- luces del coche, como en uno real:
#  - mica/cover/lente = vidrio transparente (se ve el proyector y el reflector cromado), NUNCA brilla entera
#  - brillan solo los emisores (LED/foco/DRL); direccionales y reversa APAGADAS; marcos y carcasas nunca brillan
#  - si el modelo no trae emisor de calavera, la mica roja brilla poquito (rojo puro, nada de rosa)
K_COVER = ("cover", "lens", "glass", "lampcover", "refraction", "clear", "mica")
K_LUZ = ("light", "lamp", "headl", "tail", "brake_l", "stop", "led", "bulb", "drl", "daylight", "angel", "blinker", "indicator", "faro", "calavera")
K_DRL = ("daylight", "drl", "angel", "led_strip", "ledstrip")
K_APAGADA = ("orange", "amber", "blinker", "indicator", "turn", "signal", "side_reflector", "reverse", "white_cover", "fog")
K_NUNCA = ("frame", "housing", "trim", "chrome", "reflector", "reflec", "carcasa", "window", "windshield")
K_COLA = ("tail", "brake_l", "stop", "rear_l", "calavera")

def _transp(p):
    return p.inputs["Transmission Weight"].default_value > 0.5 or (not p.inputs["Alpha"].is_linked and p.inputs["Alpha"].default_value < 0.6)

def _rojo(p, nm):
    bc = p.inputs["Base Color"].default_value
    return "red" in nm or (not p.inputs["Base Color"].is_linked and bc[0] > 0.15 and bc[0] > 4 * bc[1])

def _es_cola_emisor(m):
    p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes else None
    nm = m.name.lower()
    return bool(p) and any(k in nm for k in K_COLA) and not any(k in nm for k in K_COVER + K_NUNCA + K_APAGADA) and not _transp(p)

HAY_EMISOR_COLA = any(_es_cola_emisor(m) for m in bpy.data.materials)

def luz_mat(m, p, nm):
    es, ec = p.inputs["Emission Strength"], p.inputs["Emission Color"]
    if any(k in nm for k in ("rim", "wheel", "brake_disc", "caliper", "disc", "rin_", "rueda", "freno")) and "light" not in nm:
        es.default_value = 0.0; return
    if not any(k in nm for k in K_LUZ + ("lens", "lampcover", "refraction", "cover", "mica")):
        return   # ventanas y demás vidrios no se tocan
    cover = any(k in nm for k in K_COVER) or _transp(p)
    drl = any(k in nm for k in K_DRL)
    def sin_tex():
        for l in list(ec.links): m.node_tree.links.remove(l)
    # 1) cuánto brilla
    if drl:   # tira DRL: difusor que brilla blanco frío
        sin_tex(); ec.default_value = (0.92, 0.96, 1.0, 1); es.default_value = 5.0
        if not p.inputs["Alpha"].is_linked: p.inputs["Alpha"].default_value = 1.0
    elif any(k in nm for k in K_APAGADA + K_NUNCA):
        es.default_value = 0.0
    elif cover:
        es.default_value = 0.0
        if _rojo(p, nm) and not HAY_EMISOR_COLA:   # sin LEDs de calavera en el modelo: la mica roja brilla poquito
            sin_tex(); ec.default_value = (1.0, 0.0, 0.0, 1); es.default_value = 1.3   # más fuerte se va a rosa con AgX
    elif any(k in nm for k in K_COLA):   # LEDs de calavera
        if not ec.is_linked: ec.default_value = (1.0, 0.004, 0.002, 1)
        es.default_value = 4.0
    elif nm.endswith("lights") and p.inputs["Base Color"].is_linked:
        es.default_value = 0.0   # atlas con todas las luces en una textura: no se puede separar faro/calavera -> apagado
    else:   # emisor de faro (LED/proyector)
        if not ec.is_linked: ec.default_value = (0.95, 0.97, 1.0, 1)
        es.default_value = 4.0
    # 2) las micas son vidrio físico: reflejan y dejan ver el interior (no fantasma semitransparente)
    if cover and not drl and not p.inputs["Alpha"].is_linked:
        bc = p.inputs["Base Color"]
        if not bc.is_linked and sum(bc.default_value[:3]) < 0.3 and p.inputs["Metallic"].default_value > 0.5 \
                and not any(k in nm for k in ("black", "balck", "tint", "smoke", "spoiler")):
            bc.default_value = (1, 1, 1, 1)   # mica "negra" de exportación = en realidad transparente
        p.inputs["Alpha"].default_value = 1.0
        p.inputs["Transmission Weight"].default_value = 1.0
        p.inputs["Roughness"].default_value = min(p.inputs["Roughness"].default_value, 0.05)
        p.inputs["Metallic"].default_value = 0.0
        p.inputs["IOR"].default_value = 1.5
    print(f"LUZFIX {m.name}: emis={es.default_value} cover={cover} drl={drl}")

# Pintura con laca (clearcoat) y luces del coche encendidas
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    p = next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if not p:
        continue
    nm = m.name.lower()
    if any(k in nm for k in ("paint", "body", "carpaint", "car_paint", "pintura", "exterior")):
        p.inputs["Coat Weight"].default_value = 1.0
        p.inputs["Coat Roughness"].default_value = 0.03
        for l in list(p.inputs["Emission Color"].links):   # pintura nunca emite luz
            m.node_tree.links.remove(l)
        p.inputs["Emission Strength"].default_value = 0.0
        continue
    luz_mat(m, p, nm)

# ------------------------------------------------------------------ decoración (livery)
# Colores de fábrica reales + rines/calipers + franjas; nada de texto ni logos inventados.
LIVERIES = {
    "gt3_blanco":   dict(pintura=(0.80, 0.81, 0.82), metal=0.0, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.6, 0.01, 0.01), franjas="lateral", franja=(0.01, 0.01, 0.01), techo=True),
    "guards_red":   dict(pintura=(0.50, 0.012, 0.008), metal=0.0, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.75, 0.55, 0.02), franjas="ninguna", techo=False),
    "miami_blue":   dict(pintura=(0.015, 0.22, 0.50), metal=0.25, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.6, 0.01, 0.01), franjas="ninguna", techo=True),
    "gulf":         dict(pintura=(0.30, 0.58, 0.78), metal=0.0, rin=(0.55, 0.56, 0.58), rin_metal=1.0, caliper=(0.6, 0.01, 0.01), franjas="racing", franja=(0.85, 0.22, 0.01), techo=False),
    "negro_oro":    dict(pintura=(0.008, 0.008, 0.009), metal=0.5, rin=(0.62, 0.42, 0.11), rin_metal=1.0, caliper=(0.62, 0.42, 0.11), franjas="ninguna", techo=False),
    "verde_python": dict(pintura=(0.10, 0.42, 0.04), metal=0.15, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.75, 0.55, 0.02), franjas="lateral", franja=(0.01, 0.01, 0.01), techo=True),
    "amarillo":     dict(pintura=(0.85, 0.42, 0.0), metal=0.0, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.01, 0.01, 0.01), franjas="racing", franja=(0.01, 0.01, 0.01), techo=False),
    "rojo_blanco":  dict(pintura=(0.45, 0.01, 0.01), metal=0.2, rin=(0.55, 0.56, 0.58), rin_metal=1.0, caliper=(0.01, 0.01, 0.01), franjas="racing", franja=(0.82, 0.82, 0.82), techo=False),
    "morado":       dict(pintura=(0.12, 0.02, 0.30), metal=0.45, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.75, 0.55, 0.02), franjas="ninguna", techo=True),
    "panda":        dict(pintura=(0.80, 0.81, 0.82), metal=0.0, rin=(0.42, 0.26, 0.07), rin_metal=1.0, caliper=(0.6, 0.01, 0.01), franjas="bajo", franja=(0.008, 0.008, 0.008), techo=False),
    "negro_mate":   dict(pintura=(0.006, 0.006, 0.007), metal=0.0, mate=True, rin=(0.015, 0.015, 0.015), rin_metal=0.3, caliper=(0.6, 0.01, 0.01), franjas="ninguna", techo=False),
    "morado_oro":   dict(pintura=(0.10, 0.015, 0.28), metal=0.5, rin=(0.62, 0.42, 0.11), rin_metal=1.0, caliper=(0.62, 0.42, 0.11), franjas="ninguna", techo=False),
    "oro":          dict(pintura=(0.50, 0.33, 0.08), metal=0.8, rin=(0.62, 0.42, 0.11), rin_metal=1.0, caliper=(0.01, 0.01, 0.01), franjas="ninguna", techo=False),
    "naranja_bronce": dict(pintura=(0.85, 0.22, 0.0), metal=0.1, rin=(0.42, 0.26, 0.07), rin_metal=1.0, caliper=(0.01, 0.01, 0.01), franjas="ninguna", techo=False),
    "blanco_bronce": dict(pintura=(0.80, 0.81, 0.82), metal=0.0, rin=(0.42, 0.26, 0.07), rin_metal=1.0, caliper=(0.6, 0.01, 0.01), franjas="ninguna", techo=False),
    "naranja":      dict(pintura=(0.90, 0.13, 0.0), metal=0.1, rin=(0.08, 0.08, 0.09), rin_metal=1.0, caliper=(0.01, 0.01, 0.01), franjas="lateral", franja=(0.01, 0.01, 0.01), techo=True),
}
LIV = PLAN.get("livery") or ""
OVR = {}
try:
    OVR = next((x.get("mats", {}) for x in json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modelos.json"))) if x["uid"] == A.uid), {})
except Exception as e:
    print("sin overrides", e)

area = {}
for o in meshes(objs):
    sx, sy, sz = o.matrix_world.to_scale()
    f = abs(sx * sy)
    for pg in o.data.polygons:
        if pg.material_index < len(o.material_slots) and o.material_slots[pg.material_index].material:
            mt = o.material_slots[pg.material_index].material
            area[mt.name] = area.get(mt.name, 0) + pg.area * f
for nm_, a_ in sorted(area.items(), key=lambda x: -x[1])[:25]:
    _m = bpy.data.materials.get(nm_); _p = next((n for n in _m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if _m and _m.use_nodes else None
    _e = f"emis={_p.inputs['Emission Strength'].default_value:.1f}{'(tex)' if _p.inputs['Emission Color'].is_linked else ''} rough={_p.inputs['Roughness'].default_value:.2f}{'(tex)' if _p.inputs['Roughness'].is_linked else ''} normal={'si' if _p.inputs['Normal'].is_linked else 'no'}" if _p else "sin principled"
    print(f"MAT {a_:7.3f} m2  {nm_}  {_e}")

import re
def tiene(nm, ks):   # "rim" solo como palabra/prefijo (no "trim" ni "primary")
    return any(re.search(r"(^|[^a-z])rim", nm) if k == "rim" else (k in nm) for k in ks)
NO_PINTURA = ("glass", "window", "vidrio", "cristal", "tire", "tyre", "rubber", "llanta", "interior", "seat", "chrome", "light", "lamp", "plate",
              "placa", "rim", "wheel", "brake", "caliper", "disc", "grill", "grille", "mesh", "carbon", "black", "trim", "badge", "logo", "emblem",
              "exhaust", "mirror_glass", "dash", "leather", "fabric", "under", "chassis", "engine", "shadow", "decal", "lens")
pintura = set(OVR.get("pintura", [])) or {m for m in area if tiene(m.lower(), ("paint", "carpaint", "car_paint", "pintura", "body", "exterior")) and not tiene(m.lower(), NO_PINTURA)}
if not pintura and area:   # sin nombres útiles: el material más grande que no sea vidrio/llanta/etc.
    cand = [m for m in sorted(area, key=lambda x: -area[x]) if not tiene(m.lower(), NO_PINTURA)]
    pintura = set(cand[:1])
rines = set(OVR.get("rin", [])) or {m for m in area if tiene(m.lower(), ("rim", "wheel", "rin_", "felge")) and not tiene(m.lower(), ("tire", "tyre", "rubber", "llanta", "brake", "caliper", "disc", "steer", "volante", "bolt", "nut"))}
if not OVR.get("rin"):
    _NO_RIN = ("tire", "tyre", "rubber", "llanta", "brake", "caliper", "disc", "steer", "volante", "bolt", "nut", "glass", "light", "paint", "interior")
    for o in meshes(objs):
        if tiene(o.name.lower(), ("rim", "wheel", "felge")) and not any(k in o.name.lower() for k in ("steer", "volante", "spare", "arch")):
            for sl in o.material_slots:
                if sl.material and not tiene(sl.material.name.lower(), _NO_RIN):
                    rines.add(sl.material.name)
calipers = set(OVR.get("caliper", [])) or {m for m in area if tiene(m.lower(), ("caliper", "brake_c", "pinza", "bremssattel"))}
print("PINTURA", sorted(pintura), "RINES", sorted(rines), "CALIPERS", sorted(calipers), "LIVERY", LIV)

F, B = mx.x, mn.x
ref = empty("RefMundo")   # coordenadas de mundo para las franjas (el coche ya está normalizado)

def bsdf(m):
    return next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None) if m.use_nodes else None

def color_fijo(p, col, metal, rough):
    nt = p.id_data
    for k in ("Base Color", "Metallic", "Roughness"):
        for l in list(p.inputs[k].links):
            nt.links.remove(l)
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Metallic"].default_value = metal
    p.inputs["Roughness"].default_value = rough
    # sin brillo propio: algunos modelos traen emisión horneada en la pintura y se ve plana como plástico
    for l in list(p.inputs["Emission Color"].links):
        nt.links.remove(l)
    p.inputs["Emission Strength"].default_value = 0.0

def mascara_pintura(nt, cfg):
    """devuelve un socket 0..1: 1 = franja/techo (color secundario), 0 = pintura"""
    N_ = nt.nodes; Lk = nt.links.new
    tc = N_.new("ShaderNodeTexCoord"); tc.object = ref
    xyz = N_.new("ShaderNodeSeparateXYZ"); Lk(tc.outputs["Object"], xyz.inputs[0])
    geo = N_.new("ShaderNodeNewGeometry"); nrm = N_.new("ShaderNodeSeparateXYZ"); Lk(geo.outputs["Normal"], nrm.inputs[0])
    def op(o, a, b=None, clamp=True):
        n = N_.new("ShaderNodeMath"); n.operation = o; n.use_clamp = clamp
        for i, v in enumerate((a, b)):
            if v is None: continue
            if isinstance(v, (int, float)): n.inputs[i].default_value = v
            else: Lk(v, n.inputs[i])
        return n.outputs[0]
    def banda(v, lo, hi, s=0.006):   # 1 entre lo y hi con borde suave
        return op("MULTIPLY", op("GREATER_THAN", v, lo), op("LESS_THAN", v, hi))
    franja = techo = None
    ay = op("ABSOLUTE", xyz.outputs["Y"], None, False)
    any_ = op("ABSOLUTE", nrm.outputs["Y"], None, False)
    if cfg.get("franjas") == "racing":   # dos franjas por el centro, cofre-techo-cajuela
        franja = op("MULTIPLY", banda(ay, 0.06, 0.24), op("LESS_THAN", any_, 0.85))
    elif cfg.get("franjas") == "lateral":   # franja baja a lo largo del costado
        z = xyz.outputs["Z"]; x = xyz.outputs["X"]
        franja = op("MULTIPLY", op("MULTIPLY", banda(z, 0.27, 0.36), op("GREATER_THAN", any_, 0.45)), banda(x, B + 0.95, F - 1.05))
    elif cfg.get("franjas") == "bajo":   # dos tonos: parte baja de otro color (estilo panda)
        franja = op("LESS_THAN", xyz.outputs["Z"], H * 0.36)
    if cfg.get("techo"):   # techo negro brillante
        techo = op("MULTIPLY", op("GREATER_THAN", xyz.outputs["Z"], H - 0.2), op("GREATER_THAN", nrm.outputs["Z"], 0.25))
    return franja, techo

MASCARA_FRANJA = {}
if LIV in LIVERIES:
    cfg = LIVERIES[LIV]
    for m in bpy.data.materials:
        p = bsdf(m)
        if not p:
            continue
        if m.name in pintura:
            color_fijo(p, cfg["pintura"], cfg["metal"], 0.28 if cfg["metal"] else 0.2)
            p.inputs["Coat Weight"].default_value = 0.0 if cfg.get("mate") else 1.0; p.inputs["Coat Roughness"].default_value = 0.03
            if cfg.get("mate"):
                p.inputs["Roughness"].default_value = 0.38
            nt = m.node_tree
            franja, techo = mascara_pintura(nt, cfg)
            sock = None; mk_total = None
            for mk, col in ((franja, cfg.get("franja", (0.01, 0.01, 0.01))), (techo, (0.008, 0.008, 0.008))):
                if mk is None:
                    continue
                mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
                nt.links.new(mk, mix.inputs["Factor"])
                if sock is None: mix.inputs[6].default_value = (*cfg["pintura"], 1)
                else: nt.links.new(sock, mix.inputs[6])
                mix.inputs[7].default_value = (*col, 1)
                sock = mix.outputs[2]
                if mk_total is None: mk_total = mk
                else:
                    mxn = nt.nodes.new("ShaderNodeMath"); mxn.operation = "MAXIMUM"
                    nt.links.new(mk_total, mxn.inputs[0]); nt.links.new(mk, mxn.inputs[1]); mk_total = mxn.outputs[0]
            if sock is not None:
                MASCARA_FRANJA[m.name] = mk_total
                nt.links.new(sock, p.inputs["Base Color"])
                if cfg["metal"]:   # franjas y techo sin metalizado
                    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
                    nt.links.new(mk_total, inv.inputs[1])
                    mm = nt.nodes.new("ShaderNodeMath"); mm.operation = "MULTIPLY"; mm.inputs[1].default_value = cfg["metal"]
                    nt.links.new(inv.outputs[0], mm.inputs[0]); nt.links.new(mm.outputs[0], p.inputs["Metallic"])
        elif m.name in rines:
            oscuro = sum(cfg["rin"]) < 0.1
            color_fijo(p, (0.045, 0.045, 0.05) if oscuro else cfg["rin"], 1.0 if oscuro else max(cfg["rin_metal"], 0.6), 0.16 if oscuro else 0.12)
            p.inputs["Coat Weight"].default_value = 1.0; p.inputs["Coat Roughness"].default_value = 0.03
        elif m.name in calipers:
            color_fijo(p, cfg["caliper"], 0.0, 0.35)

# ------------------------------------------------------------------ realismo de materiales
def _n(nt, tipo, **kw):
    n = nt.nodes.new(tipo)
    for k, v in kw.items():
        if k.startswith("i_"):
            n.inputs[k[2:].replace("_", " ")].default_value = v
        else:
            setattr(n, k, v)
    return n


def pintura_real(m, p):
    """laca MUY brillante (coat 0.03) con orange peel; swirls finos en el relieve; polvo en la parte baja"""
    nt = m.node_tree; L_ = nt.links.new
    tc = _n(nt, "ShaderNodeTexCoord", object=ref)   # metros reales (el objeto importado puede estar en cm)
    peel = _n(nt, "ShaderNodeTexNoise", i_Scale=420.0, i_Detail=1.0, i_Roughness=0.5)
    L_(tc.outputs["Object"], peel.inputs["Vector"])
    vor = _n(nt, "ShaderNodeTexVoronoi", feature="DISTANCE_TO_EDGE", i_Scale=45.0)
    L_(tc.outputs["Object"], vor.inputs["Vector"])
    sw = _n(nt, "ShaderNodeMapRange", i_From_Min=0.0, i_From_Max=0.004, i_To_Min=1.0, i_To_Max=0.0)
    L_(vor.outputs["Distance"], sw.inputs["Value"])
    alt = _n(nt, "ShaderNodeMath", operation="MULTIPLY_ADD"); alt.inputs[1].default_value = 0.15   # peel + swirls como relieve
    L_(sw.outputs["Result"], alt.inputs[0]); L_(peel.outputs["Fac"], alt.inputs[2])
    bump = _n(nt, "ShaderNodeBump", i_Strength=0.025, i_Distance=0.0002)
    L_(alt.outputs[0], bump.inputs["Height"])
    L_(bump.outputs["Normal"], p.inputs["Coat Normal"])
    # polvo en estribos/defensas (abajo de 35 cm): ahí la laca se ve un poco más opaca
    sep = _n(nt, "ShaderNodeSeparateXYZ"); L_(tc.outputs["Object"], sep.inputs[0])
    baja = _n(nt, "ShaderNodeMapRange", i_From_Min=0.35, i_From_Max=0.08, i_To_Min=0.0, i_To_Max=1.0)
    L_(sep.outputs["Z"], baja.inputs["Value"])
    nz = _n(nt, "ShaderNodeTexNoise", i_Scale=7.0, i_Detail=8.0); L_(tc.outputs["Object"], nz.inputs["Vector"])
    md = _n(nt, "ShaderNodeMath", operation="MULTIPLY"); L_(baja.outputs["Result"], md.inputs[0]); L_(nz.outputs["Fac"], md.inputs[1])
    cr = _n(nt, "ShaderNodeMapRange", i_From_Min=0.0, i_From_Max=1.0, i_To_Min=0.03, i_To_Max=0.22)
    L_(md.outputs[0], cr.inputs["Value"])
    salida = cr.outputs["Result"]
    if m.name in MASCARA_FRANJA:   # franjas de vinil satinado: no reflejan como espejo (evita los bordes grises)
        fm = _n(nt, "ShaderNodeMath", operation="MULTIPLY"); fm.inputs[1].default_value = 0.32
        L_(MASCARA_FRANJA[m.name], fm.inputs[0])
        mxr = _n(nt, "ShaderNodeMath", operation="MAXIMUM"); L_(salida, mxr.inputs[0]); L_(fm.outputs[0], mxr.inputs[1])
        salida = mxr.outputs[0]
    L_(salida, p.inputs["Coat Roughness"])
    p.inputs["Coat Weight"].default_value = 1.0
    p.inputs["Coat IOR"].default_value = 1.5
    p.inputs["Specular IOR Level"].default_value = 0.12   # el brillo lo da la laca, no la base (quita la neblina gris)


def ensuciar(m, p, color, cantidad, rough_add, escala=6.0):
    """mezcla polvo/brake dust en manchas suaves"""
    nt = m.node_tree; L_ = nt.links.new
    tc = _n(nt, "ShaderNodeTexCoord", object=ref)
    nz = _n(nt, "ShaderNodeTexNoise", i_Scale=escala, i_Detail=6.0)
    L_(tc.outputs["Object"], nz.inputs["Vector"])
    mr = _n(nt, "ShaderNodeMapRange", i_From_Min=0.35, i_From_Max=0.65, i_To_Min=0.0, i_To_Max=cantidad)
    L_(nz.outputs["Fac"], mr.inputs["Value"])
    mix = _n(nt, "ShaderNodeMix", data_type="RGBA")
    L_(mr.outputs["Result"], mix.inputs["Factor"])
    bc = p.inputs["Base Color"]
    if bc.is_linked:
        L_(bc.links[0].from_socket, mix.inputs[6])
    else:
        mix.inputs[6].default_value = bc.default_value
    mix.inputs[7].default_value = (*color, 1)
    L_(mix.outputs[2], bc)
    rg = p.inputs["Roughness"]
    if not rg.is_linked:
        rg.default_value = min(1.0, rg.default_value + rough_add)


for m in bpy.data.materials:
    p_ = bsdf(m)
    if p_ and "reflector" in m.name.lower() and not p_.inputs["Base Color"].is_linked:
        p_.inputs["Base Color"].default_value = (0.22, 0.22, 0.23, 1); p_.inputs["Roughness"].default_value = 0.18

K_VENT = ("glass", "window", "windshield", "windscreen", "vidrio", "cristal", "parabrisas")
for m in bpy.data.materials:
    p = bsdf(m)
    if not p:
        continue
    nm = m.name.lower()
    es_pintura = m.name in pintura or (any(k in nm for k in ("paint", "carpaint", "car_paint", "pintura")) and not tiene(nm, NO_PINTURA))
    if es_pintura:
        pintura_real(m, p)
    elif any(k in nm for k in ("tire", "tyre", "rubber", "llanta", "neum", "reifen")) and not tiene(nm, ("rim",)):
        ensuciar(m, p, (0.24, 0.22, 0.19), 0.6, 0.2, 9.0)          # polvo gris en la goma
    elif m.name in rines or (tiene(nm, ("rim", "wheel")) and not any(k in nm for k in ("tire", "tyre", "rubber"))):
        ensuciar(m, p, (0.13, 0.11, 0.09), 0.7, 0.05, 14.0)        # brake dust en los rines
    elif any(k in nm for k in ("disc", "rotor")):
        ensuciar(m, p, (0.12, 0.07, 0.04), 0.5, 0.2, 20.0)           # discos con óxido ligero
    elif any(k in nm for k in K_VENT) and not any(k in nm for k in K_LUZ):
        # ventanas de vidrio real: se ve el volante y los asientos (antes casi negras/espejo)
        oscuro = any(k in nm for k in ("tint", "black", "balck", "dark", "smoke"))
        for k_ in ("Base Color", "Alpha", "Metallic", "Transmission Weight", "Roughness"):
            for l in list(p.inputs[k_].links):
                m.node_tree.links.remove(l)
        p.inputs["Base Color"].default_value = (0.30, 0.32, 0.33, 1) if oscuro else (0.80, 0.83, 0.83, 1)
        p.inputs["Alpha"].default_value = 1.0; p.inputs["Metallic"].default_value = 0.0
        p.inputs["Transmission Weight"].default_value = 1.0; p.inputs["Roughness"].default_value = 0.0
        p.inputs["IOR"].default_value = 1.45
        print("VENTANA", m.name, "oscura" if oscuro else "clara")

# ------------------------------------------------------------------ escenario
ESC = PLAN.get("escenario", "estudio")       # estudio (fondo negro) | exterior (HDRI real visible)
TOMA_FX = SHOT.get("mov", 1.0)                # multiplicador de recorrido de cámara (más = más rápido)
world = bpy.data.worlds.new("Mundo")
sc.world = world
world.use_nodes = True
wn, wl = world.node_tree.nodes, world.node_tree.links
wn.clear()
out = wn.new("ShaderNodeOutputWorld")
if ESC == "exterior" and PLAN.get("hdri") and os.path.exists(PLAN["hdri"]):
    tcw = wn.new("ShaderNodeTexCoord"); mp_ = wn.new("ShaderNodeMapping")
    mp_.inputs["Rotation"].default_value[2] = math.radians(PLAN.get("hdri_rot", 0))
    env = wn.new("ShaderNodeTexEnvironment"); env.image = bpy.data.images.load(PLAN["hdri"])
    bgw = wn.new("ShaderNodeBackground"); bgw.inputs["Strength"].default_value = PLAN.get("hdri_fuerza", 1.0)
    wl.new(tcw.outputs["Generated"], mp_.inputs["Vector"]); wl.new(mp_.outputs["Vector"], env.inputs["Vector"])
    wl.new(env.outputs["Color"], bgw.inputs["Color"]); wl.new(bgw.outputs["Background"], out.inputs["Surface"])
else:
    ESC = "estudio"
    bg = wn.new("ShaderNodeBackground"); bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
    fill = wn.new("ShaderNodeBackground"); fill.inputs["Color"].default_value = (0.6, 0.62, 0.66, 1)
    fill.inputs["Strength"].default_value = 0.04
    if PLAN.get("hdri_estudio") and os.path.exists(PLAN["hdri_estudio"]):
        # reflejos reales: la pintura refleja un estudio fotográfico de verdad (softboxes, paredes, techo),
        # pero la cámara sigue viendo negro. Sin esto la pintura se ve como plástico.
        envs = wn.new("ShaderNodeTexEnvironment"); envs.image = bpy.data.images.load(PLAN["hdri_estudio"])
        tcs = wn.new("ShaderNodeTexCoord"); mps = wn.new("ShaderNodeMapping")
        mps.inputs["Rotation"].default_value[2] = math.radians(PLAN.get("hdri_rot", 0))
        wl.new(tcs.outputs["Generated"], mps.inputs["Vector"]); wl.new(mps.outputs["Vector"], envs.inputs["Vector"])
        wl.new(envs.outputs["Color"], fill.inputs["Color"])
        fill.inputs["Strength"].default_value = PLAN.get("hdri_estudio_fuerza", 1.0)
        print("HDRI estudio para reflejos:", PLAN["hdri_estudio"])
    if PLAN.get("hdri_estudio") and os.path.exists(PLAN["hdri_estudio"]):
        refl = wn.new("ShaderNodeBackground"); wl.new(envs.outputs["Color"], refl.inputs["Color"])
        refl.inputs["Strength"].default_value = PLAN.get("hdri_reflejo_fuerza", 3.0)
        lpg = wn.new("ShaderNodeLightPath"); mg = wn.new("ShaderNodeMixShader")
        wl.new(lpg.outputs["Is Glossy Ray"], mg.inputs["Fac"])
        wl.new(fill.outputs["Background"], mg.inputs[1]); wl.new(refl.outputs["Background"], mg.inputs[2])
        fill = type("F", (), {"outputs": {"Background": mg.outputs["Shader"]}})()
    lp = wn.new("ShaderNodeLightPath"); mix = wn.new("ShaderNodeMixShader")
    wl.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
    wl.new(fill.outputs["Background"], mix.inputs[1])   # relleno tenue para que nada quede 100% negro
    wl.new(bg.outputs["Background"], mix.inputs[2])     # la cámara ve negro
    wl.new(mix.outputs["Shader"], out.inputs["Surface"])

# Piso: en estudio oscuro y satinado que se pierde a negro; en exterior atrapa-sombras invisible
piso = bpy.data.materials.new("Piso"); piso.use_nodes = True
nt = piso.node_tree; P = nt.nodes["Principled BSDF"]
# piso de estudio pulido (epóxico): refleja el coche nítido pero un poco difuso -> el coche "pisa" su reflejo
P.inputs["Base Color"].default_value = (0.006, 0.006, 0.007, 1)
P.inputs["Roughness"].default_value = 0.2
P.inputs["Specular IOR Level"].default_value = 0.5
tc = nt.nodes.new("ShaderNodeTexCoord")
# textura sutil del piso que se desplaza en las tomas "manejando" (da sensación de velocidad en los reflejos)
mpf = nt.nodes.new("ShaderNodeMapping"); nz = nt.nodes.new("ShaderNodeTexNoise")
nz.inputs["Scale"].default_value = 1.6; nz.inputs["Detail"].default_value = 8
rr = nt.nodes.new("ShaderNodeMapRange"); rr.inputs["To Min"].default_value = 0.24; rr.inputs["To Max"].default_value = 0.40
nt.links.new(tc.outputs["Object"], mpf.inputs["Vector"]); nt.links.new(mpf.outputs["Vector"], nz.inputs["Vector"])
nt.links.new(nz.outputs["Fac"], rr.inputs["Value"]); nt.links.new(rr.outputs["Result"], P.inputs["Roughness"])
vl = nt.nodes.new("ShaderNodeVectorMath"); vl.operation = "LENGTH"
mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 3; mr.inputs["From Max"].default_value = 10
blk = nt.nodes.new("ShaderNodeBsdfDiffuse"); blk.inputs["Color"].default_value = (0, 0, 0, 1)
ms = nt.nodes.new("ShaderNodeMixShader"); outm = nt.nodes["Material Output"]
nt.links.new(tc.outputs["Object"], vl.inputs[0]); nt.links.new(vl.outputs["Value"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ms.inputs["Fac"])
nt.links.new(P.outputs["BSDF"], ms.inputs[1]); nt.links.new(blk.outputs["BSDF"], ms.inputs[2])
nt.links.new(ms.outputs["Shader"], outm.inputs["Surface"])
# contacto: oclusión ambiental oscurece y quita brillo justo debajo de las llantas y el coche
ao = nt.nodes.new("ShaderNodeAmbientOcclusion"); ao.inputs["Distance"].default_value = 0.35; ao.samples = 16
inv_ao = nt.nodes.new("ShaderNodeMath"); inv_ao.operation = "SUBTRACT"; inv_ao.inputs[0].default_value = 1.0
nt.links.new(ao.outputs["AO"], inv_ao.inputs[1])
mx_ao = nt.nodes.new("ShaderNodeMath"); mx_ao.operation = "MAXIMUM"
nt.links.new(inv_ao.outputs[0], mx_ao.inputs[0]); nt.links.new(mr.outputs["Result"], mx_ao.inputs[1])
nt.links.new(mx_ao.outputs[0], ms.inputs["Fac"])
# manchas/huellas cerca del coche: zonas más mate en el piso pulido
smg = nt.nodes.new("ShaderNodeTexNoise"); smg.inputs["Scale"].default_value = 1.2; smg.inputs["Detail"].default_value = 10
nt.links.new(tc.outputs["Object"], smg.inputs["Vector"])
smr = nt.nodes.new("ShaderNodeMapRange"); smr.inputs["From Min"].default_value = 0.55; smr.inputs["From Max"].default_value = 0.75
smr.inputs["To Min"].default_value = 0.0; smr.inputs["To Max"].default_value = 0.18
nt.links.new(smg.outputs["Fac"], smr.inputs["Value"])
near = nt.nodes.new("ShaderNodeMapRange"); near.inputs["From Min"].default_value = 2.0; near.inputs["From Max"].default_value = 4.5
near.inputs["To Min"].default_value = 1.0; near.inputs["To Max"].default_value = 0.0
nt.links.new(vl.outputs["Value"], near.inputs["Value"])
smm = nt.nodes.new("ShaderNodeMath"); smm.operation = "MULTIPLY"
nt.links.new(smr.outputs["Result"], smm.inputs[0]); nt.links.new(near.outputs["Result"], smm.inputs[1])
rsum = nt.nodes.new("ShaderNodeMath"); rsum.operation = "ADD"
nt.links.new(rr.outputs["Result"], rsum.inputs[0]); nt.links.new(smm.outputs[0], rsum.inputs[1])
nt.links.new(rsum.outputs[0], P.inputs["Roughness"])
P.inputs["Specular IOR Level"].default_value = 0.22


def ciclorama(R0=7.0, Rc=4.5, Hw=14.0, seg=128):
    """estudio infinito: el piso se curva hacia la pared (sin línea de horizonte)"""
    import bmesh
    prof = [(r, 0.0) for r in (0.4, 1, 2, 3, 4, 5, 6, R0)]
    for i in range(1, 17):
        a = math.radians(90 * i / 16)
        prof.append((R0 + Rc * math.sin(a), Rc * (1 - math.cos(a))))
    prof.append((R0 + Rc, Hw))
    def malla(nombre, desde, hasta, centro):
        bm = bmesh.new()
        cen = bm.verts.new((0, 0, 0)) if centro else None
        sub = prof[desde:hasta + 1]
        rings = [[bm.verts.new((r * math.cos(2 * math.pi * j / seg), r * math.sin(2 * math.pi * j / seg), z)) for r, z in sub] for j in range(seg)]
        for j in range(seg):
            a_, b_ = rings[j], rings[(j + 1) % seg]
            if centro:
                bm.faces.new((cen, a_[0], b_[0]))
            for i in range(len(sub) - 1):
                bm.faces.new((a_[i], a_[i + 1], b_[i + 1], b_[i]))
        me = bpy.data.meshes.new(nombre); bm.to_mesh(me); bm.free()
        for pg in me.polygons:   # normales hacia adentro/arriba
            c = pg.center
            if Vector((-c.x, -c.y, 3.0 - c.z)).dot(pg.normal) < 0:
                pg.flip()
            pg.use_smooth = True
        return link(bpy.data.objects.new(nombre, me))
    i0 = len([1 for r, z in prof if z == 0.0]) - 1
    piso_o = malla("Piso", 0, i0, True)
    cur = malla("Curva", i0, len(prof) - 1, False)
    # la curva/pared la ve la cámara, pero NO tapa el HDRI de estudio en los reflejos de la pintura
    cur.visible_glossy = False; cur.visible_diffuse = False
    return piso_o, cur


if ESC == "exterior":
    bpy.ops.mesh.primitive_plane_add(size=200, location=(0, 0, 0))
    suelo = bpy.context.object
else:
    suelo, curva = ciclorama()
    curva.data.materials.append(piso)
    # oscurece gradual con distancia + altura: piso -> curva -> pared, sin corte
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); nt.links.new(tc.outputs["Object"], sep.inputs[0])
    zz = nt.nodes.new("ShaderNodeMath"); zz.operation = "MULTIPLY_ADD"
    nt.links.new(sep.outputs["Z"], zz.inputs[0]); zz.inputs[1].default_value = 1.6; nt.links.new(vl.outputs["Value"], zz.inputs[2])
    nt.links.new(zz.outputs[0], mr.inputs["Value"])
    mr.inputs["From Min"].default_value = 4.0; mr.inputs["From Max"].default_value = 17.0
    mr.inputs["To Max"].default_value = 0.96
suelo.data.materials.append(piso)
if ESC == "exterior":
    suelo.is_shadow_catcher = True


def softbox(name, loc, size, size_y, energy, target=(0, 0, 0.6), color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"; ld.size = size; ld.size_y = size_y
    ld.energy, ld.color = energy * (0.25 if ESC == "exterior" else 1.0) * PLAN.get("luz", 0.6 if PLAN.get("hdri_estudio") else 1.0), color
    ob = link(bpy.data.objects.new(name, ld))
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    ob.visible_camera = False
    ob.visible_glossy = False   # el reflejo lo da la tarjeta con forma (abajo), no un rectángulo plano quemado
    tarjeta(name, loc, size, size_y, ld.energy, target, color, tiras=PLAN.get("tiras_" + name, 1))
    return ob


_tarjeta_mats = {}


def tarjeta(name, loc, sx, sy, energy, target, color, tiras=1):
    """softbox visible solo en reflejos: centro caliente, bordes que caen, costuras del difusor"""
    mt = bpy.data.materials.new("Tarjeta_" + name); mt.use_nodes = True
    tn = mt.node_tree; tn.nodes.clear(); L_ = tn.links.new
    o_ = tn.nodes.new("ShaderNodeOutputMaterial"); em = tn.nodes.new("ShaderNodeEmission")
    tc_ = tn.nodes.new("ShaderNodeTexCoord"); sp = tn.nodes.new("ShaderNodeSeparateXYZ")
    L_(tc_.outputs["UV"], sp.inputs[0])
    def borde(sock, pot):   # 1 en el centro, cae a 0 en los bordes
        a = tn.nodes.new("ShaderNodeMath"); a.operation = "MULTIPLY_ADD"; a.inputs[1].default_value = 2; a.inputs[2].default_value = -1
        L_(sock, a.inputs[0])
        b = tn.nodes.new("ShaderNodeMath"); b.operation = "POWER"; b.inputs[1].default_value = pot; L_(a.outputs[0], b.inputs[0])
        b2 = tn.nodes.new("ShaderNodeMath"); b2.operation = "ABSOLUTE"; L_(b.outputs[0], b2.inputs[0])
        c = tn.nodes.new("ShaderNodeMath"); c.operation = "SUBTRACT"; c.inputs[0].default_value = 1; L_(b2.outputs[0], c.inputs[1])
        return c.outputs[0]
    fx_ = borde(sp.outputs["X"], 18.0); fy_ = borde(sp.outputs["Y"], 10.0)
    m1 = tn.nodes.new("ShaderNodeMath"); m1.operation = "MULTIPLY"; L_(fx_, m1.inputs[0]); L_(fy_, m1.inputs[1])
    sock = m1.outputs[0]
    if tiras > 1:   # varias tiras separadas por huecos oscuros (como un techo de tubos de luz)
        w_ = tn.nodes.new("ShaderNodeMath"); w_.operation = "MULTIPLY"; w_.inputs[1].default_value = tiras; L_(sp.outputs["X"], w_.inputs[0])
        fr = tn.nodes.new("ShaderNodeMath"); fr.operation = "FRACT"; L_(w_.outputs[0], fr.inputs[0])
        st = borde(fr.outputs[0], 8.0)
        m2 = tn.nodes.new("ShaderNodeMath"); m2.operation = "MULTIPLY"; L_(sock, m2.inputs[0]); L_(st, m2.inputs[1]); sock = m2.outputs[0]
    k_ = tn.nodes.new("ShaderNodeMath"); k_.operation = "MULTIPLY"
    k_.inputs[1].default_value = energy / (math.pi * sx * sy) * 1.6   # misma brillantez que la luz de área
    L_(sock, k_.inputs[0]); L_(k_.outputs[0], em.inputs["Strength"])
    em.inputs["Color"].default_value = (*color, 1)
    L_(em.outputs["Emission"], o_.inputs["Surface"])
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
    pl = bpy.context.object; pl.name = "Tarjeta_" + name
    pl.scale = (sx, sy, 1); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    pl.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("Z", "Y").to_euler()
    pl.data.materials.append(mt)
    pl.visible_camera = False; pl.visible_diffuse = False; pl.visible_shadow = False
    try:
        rc = bpy.data.collections.get("Receptores")
        if rc is None:
            rc = bpy.data.collections.new("Receptores")
            for o_ in meshes(objs):
                rc.objects.link(o_)
        pl.light_linking.receiver_collection = rc
    except Exception as e:
        print("sin light linking:", e)
    pl.visible_volume_scatter = False; pl.visible_transmission = True
    return pl


# Iluminación de estudio de autos: cenital grande + tiras laterales + contraluz + relleno frontal
PLAN.setdefault("tiras_Cenital", 3)
softbox("Cenital", (0.3, 0, H + 3.2), 2.2, L * 1.25, 1100, (0.3, 0, 0))
# luz tenue dentro de la cabina: por las ventanas se distingue el volante y los asientos
_li = bpy.data.lights.new("Cabina", "POINT"); _li.energy = 2 * PLAN.get("luz", 0.6 if PLAN.get("hdri_estudio") else 1.0); _li.shadow_soft_size = 0.6
_lo = link(bpy.data.objects.new("Cabina", _li)); _lo.location = ((mn.x + mx.x) / 2 - L * 0.08, 0, H * 0.7)
_lo.visible_glossy = False; _lo.visible_camera = False
softbox("TiraIzq", (L * 0.55, W * 2.2, 1.6), 0.5, 3.2, 420, (0, 0, 0.7))
softbox("TiraDer", (-L * 0.55, -W * 2.2, 1.6), 0.5, 3.2, 420, (0, 0, 0.7))
softbox("Contra", (-L * 1.6, 0, 3.0), 3.0, 1.2, 380, (0, 0, 0.6))
softbox("Frente", (L * 1.7, -W * 0.8, 2.6), 1.6, 0.9, 160, (0, 0, 0.6))   # alto: su reflejo no se cuela bajo el coche

# ------------------------------------------------------------------ ruedas que giran (tomas "manejando")
def txt(o):
    return (o.name + " " + " ".join(s.material.name for s in o.material_slots if s.material)).lower()


RUEDAS = []
for o in meshes(objs):
    tt_ = txt(o)
    if any(k in tt_ for k in ("wheel", "tire", "tyre", "rim", "rueda", "llanta", "disc")) and \
            not any(k in tt_ for k in ("caliper", "brake_c", "steer", "volante", "arch", "well", "fender", "cover", "spare")):
        a, b = bbox([o]); d = b - a
        if d.x < L * 0.3 and d.y < W * 0.45 and 0.2 < d.z < H * 0.75:
            RUEDAS.append(o)


def _reparent(o, piv):
    mw = o.matrix_world.copy(); o.parent = piv; o.matrix_parent_inverse = Matrix(); o.matrix_world = mw


def dirigir_ruedas(grados):
    """ruedas delanteras giradas (pose natural, no 'modelo 3D'); calipers/discos de esa rueda giran con ella"""
    if not grados:
        return
    cx = (mn.x + mx.x) / 2
    frente = [o for o in RUEDAS if (sum(bbox([o]), Vector()) / 2).x > cx]
    if not frente:
        return
    grupos = []
    for o in frente:
        c = sum(bbox([o]), Vector()) / 2
        g = next((g_ for g_ in grupos if (g_[0] - c).length < 0.35), None)
        if g: g[1].append(o)
        else: grupos.append([c, [o]])
    for c, obs in grupos:
        extra = [o for o in meshes(objs) if o not in RUEDAS and any(k in txt(o) for k in ("caliper", "brake", "disc", "rotor", "freno"))
                 and (sum(bbox([o]), Vector()) / 2 - c).length < 0.4]
        piv = empty("Direccion", parent=car); piv.matrix_world = Matrix.Translation(Vector((c.x, c.y, c.z)))
        bpy.context.view_layer.update()
        for o in obs + extra:
            _reparent(o, piv)
        piv.rotation_euler.z += math.radians(grados)   # += : conserva la compensación de giro del coche
    bpy.context.view_layer.update()
    print("DIRECCION", grados, "grados,", len(grupos), "ruedas")


def girar_ruedas(vel):
    dist = vel * (N - 1) / FPS
    for o in RUEDAS:
        a, b = bbox([o]); c = (a + b) / 2; rad = max(0.2, (b.z - a.z) / 2)
        piv = empty(o.name + "_giro", parent=car)
        piv.matrix_world = Matrix.Translation(c)
        bpy.context.view_layer.update()
        _reparent(o, piv)
        piv.rotation_euler.y = 0; piv.keyframe_insert("rotation_euler", frame=1)
        piv.rotation_euler.y = dist / rad; piv.keyframe_insert("rotation_euler", frame=N)
        for fc in piv.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def tiras_en_movimiento(vel):
    """luces de techo que pasan hacia atrás: sus reflejos corren por la carrocería como si el coche avanzara"""
    tira = bpy.data.materials.new("TiraLuz"); tira.use_nodes = True
    pt = tira.node_tree.nodes["Principled BSDF"]
    pt.inputs["Base Color"].default_value = (0, 0, 0, 1)
    pt.inputs["Emission Color"].default_value = (1, 1, 1, 1); pt.inputs["Emission Strength"].default_value = 22
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, H + 2.6))
    o = bpy.context.object; o.scale = (0.35, W * 2.6, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(tira); o.visible_camera = False
    arr = o.modifiers.new("arr", "ARRAY"); arr.use_relative_offset = False; arr.use_constant_offset = True
    arr.constant_offset_displace = (4.0, 0, 0); arr.count = 60
    dist = vel * (N - 1) / FPS
    o.location.x = 60; o.keyframe_insert("location", index=0, frame=1)
    o.location.x = 60 - dist; o.keyframe_insert("location", index=0, frame=N)
    mpf.inputs["Location"].default_value[0] = 0; mpf.inputs["Location"].keyframe_insert("default_value", frame=1)
    mpf.inputs["Location"].default_value[0] = dist; mpf.inputs["Location"].keyframe_insert("default_value", frame=N)
    for ob_ in (o,):
        for fc in ob_.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    for fc in piso.node_tree.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"


# ------------------------------------------------------------------ cámara y tomas
cd = bpy.data.cameras.new("Cam"); cam = link(bpy.data.objects.new("Cam", cd)); sc.camera = cam
cd.sensor_width = 36
cd.dof.use_dof = True
mira = empty("Mira", (0, 0, H * 0.45))
cd.dof.focus_object = mira
tt = cam.constraints.new("TRACK_TO"); tt.target = mira; tt.track_axis = "TRACK_NEGATIVE_Z"; tt.up_axis = "UP_Y"

# puntos clave del coche (frente en +X, lado derecho en -Y)
F, B, Y, Z = mx.x, mn.x, W / 2, H
FARO = (F - 0.35, -Y * 0.72, Z * 0.48)
_heads = [o for o in meshes(objs) if any(k in o.name.lower() for k in ("headl", "head_l", "headlight", "faro"))]
if _heads:
    _a, _b = bbox(_heads)
    FARO = (_b.x - 0.15, -Y * 0.7, (_a.z + _b.z) / 2)
CALAVERA = (B + 0.25, -Y * 0.72, Z * 0.58)
RUEDA = (F - L * 0.2, -Y, Z * 0.27)


def lerp(a, b, k):
    return tuple(a[i] + (b[i] - a[i]) * k for i in range(3))


def toma(c0, c1, m0, m1, lens=(85, 85), f=2.8, ease=True):
    k = TOMA_FX                  # mov>1 = recorrido más largo en el mismo tiempo = cámara más rápida
    dentro = lambda p: B - 0.35 < p[0] < F + 0.35 and abs(p[1]) < Y + 0.35 and p[2] < H + 0.35
    while k > 1.0 and dentro(lerp(c0, c1, k)):   # nunca meter la cámara dentro del coche (sale negro)
        k -= 0.05
    c1 = lerp(c0, c1, k)
    dz = PLAN.get("mira_dz", 0.0)   # mover el punto de mira (p.ej. banner: el coche sube en el cuadro sin estirar nada)
    m0 = (m0[0], m0[1], m0[2] + dz); m1 = (m1[0], m1[1], m1[2] + dz)
    for fr, cl, ml in ((1, c0, m0), (N, c1, m1)):
        cam.location = cl; cam.keyframe_insert("location", frame=fr)
        mira.location = ml; mira.keyframe_insert("location", frame=fr)
    lm = PLAN.get("lente_mult", 1.0)   # <1 = más abierto (p.ej. banner con el coche chico y el piso desvaneciéndose)
    cd.lens = lens[0] * lm; cd.keyframe_insert("lens", frame=1)
    cd.lens = lens[1] * lm; cd.keyframe_insert("lens", frame=N)
    cd.dof.aperture_fstop = f
    for ob in (cam, mira, cd):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER" if ease else "LINEAR"
                kp.easing = "EASE_IN_OUT"


def sacudida(amp):
    """cámara en mano: ruido suave en la posición (amp en metros)"""
    if amp <= 0:
        return
    for i in range(3):
        fc = cam.animation_data.action.fcurves.find("location", index=i)
        m = fc.modifiers.new("NOISE"); m.scale = 9 + 3 * i; m.strength = amp * (0.6 if i == 2 else 1); m.phase = 7 * i + A.shot * 3


def orbita(r, z, a0, a1, mira_, lens, f):
    """recorrido circular alrededor del coche (de a0 a a1 grados), con keyframes intermedios"""
    k = 6
    for j in range(k + 1):
        a = math.radians(a0 + (a1 - a0) * TOMA_FX * j / k)
        cam.location = (math.cos(a) * r, math.sin(a) * r, z); cam.keyframe_insert("location", frame=1 + round((N - 1) * j / k))
    mira.location = mira_; mira.keyframe_insert("location", frame=1)
    cd.lens = lens; cd.dof.aperture_fstop = f


t = SHOT["name"]
VEL = SHOT.get("vel", 22.0)
manejo = t.startswith("manejo") or t == "rueda_gira"
if manejo and ESC == "estudio":
    girar_ruedas(VEL)
    tiras_en_movimiento(VEL)
elif not manejo:
    dirigir_ruedas(PLAN.get("direccion", -24))
if t == "trasera":        # 3/4 trasero bajo, sube, calaveras encendidas
    toma((B - 3.2, -Y - 2.6, 0.45), (B - 2.8, -Y - 2.2, 1.1), (B + 0.4, -Y * 0.4, 0.6), (B + 0.5, -Y * 0.3, 0.75), (55, 60), 3.5)
elif t == "faro":         # detalle del faro, deslizamiento
    toma((F + 1.5, -Y - 0.9, FARO[2] + 0.05), (F + 1.1, -Y - 1.4, FARO[2] + 0.12), FARO, (FARO[0] - 0.05, FARO[1], FARO[2]), (100, 100), 2.8)
elif t == "frente34":     # 3/4 frontal desde arriba, empuje
    toma((F + 3.8, -Y - 3.4, 2.4), (F + 3.0, -Y - 2.6, 2.0), (L * 0.15, 0, 0.6), (L * 0.18, 0, 0.6), (50, 55), 4)
elif t == "perfil":       # perfil lateral bajo, dolly a lo largo
    toma((F - 0.3, -Y - 4.6, 0.55), (B + 0.6, -Y - 4.6, 0.6), (F - 1.2, 0, 0.55), (B + 1.2, 0, 0.6), (70, 70), 3.5)
elif t == "rueda":        # rin delantero, arco
    toma((RUEDA[0] + 1.4, -Y - 1.3, 0.35), (RUEDA[0] - 0.3, -Y - 1.6, 0.5), RUEDA, RUEDA, (85, 85), 2.8)
elif t == "calavera":     # detalle de calavera
    toma((B - 1.2, -Y - 1.0, CALAVERA[2] + 0.1), (B - 1.4, -Y - 0.4, CALAVERA[2] + 0.05), CALAVERA, CALAVERA, (100, 100), 2.8)
elif t == "cenital":      # desde arriba girando
    toma((0.4, -0.6, H + 6.5), (-0.4, 0.6, H + 6.0), (0, 0, 0.3), (0, 0, 0.3), (40, 45), 5.6)
elif t == "frente":       # de frente, bajo, faros encendidos
    toma((F + 4.0, 0.6, 0.5), (F + 3.4, -0.5, 0.6), (F - 0.5, 0, 0.55), (F - 0.5, 0, 0.6), (70, 75), 3.5)
elif t == "barrido":      # órbita rápida de 3/4 frontal a perfil (transición con movimiento)
    orbita(L * 1.05, 0.7, -35, -100, (0, 0, 0.6), 35, 4)
elif t == "empuje":       # empuje rápido hacia el frente (golpe)
    toma((F + 6.0, -Y - 2.0, 0.6), (F + 2.2, -Y - 0.9, 0.55), (F - 0.6, 0, 0.55), (F - 0.6, 0, 0.55), (45, 60), 3.5, ease=False)
elif t == "abre":         # plano general que se abre (inicio/cierre en loop)
    toma((F + 2.0, -Y - 1.6, 0.5), (F + 5.5, -Y - 5.0, 1.6), (0.3, 0, 0.6), (0, 0, 0.6), (35, 32), 5.6)
elif t == "manejo_lado":  # lado bajo, "manejando": ruedas giran y los reflejos corren
    toma((0.2, -Y - 3.4, 0.45), (-0.4, -Y - 3.1, 0.5), (0, 0, 0.5), (-0.1, 0, 0.5), (40, 42), 3.5)
elif t == "manejo_frente":  # frente bajo "manejando"
    toma((F + 3.2, -Y - 1.2, 0.35), (F + 2.8, -Y - 0.6, 0.4), (F - 0.8, 0, 0.5), (F - 0.8, 0, 0.5), (32, 35), 3.5)
elif t == "rueda_gira":   # rin girando de cerca
    toma((RUEDA[0] + 0.9, -Y - 1.4, 0.3), (RUEDA[0] + 0.2, -Y - 1.5, 0.35), RUEDA, RUEDA, (70, 75), 2.8)
else:                     # hero 3/4 frontal (still de revisión de modelo)
    toma((F + 3.4, -Y - 3.0, 1.1), (F + 3.3, -Y - 3.0, 1.1), (0.2, 0, 0.62), (0.2, 0, 0.62), (60, 60), 4)
sacudida(SHOT.get("sacudida", 0.0))
# profundidad de campo de foto real
FM = PLAN.get("fstop_mult", 0.5)
if t in ("faro", "calavera", "rueda", "rueda_gira"):
    cd.dof.aperture_fstop = max(1.4, cd.dof.aperture_fstop * 0.7)
else:
    foco = empty("Foco", (F - 0.55, -Y * 0.95, 0.55) if t not in ("trasera",) else (B + 0.5, -Y * 0.95, 0.6))
    if t in ("perfil", "manejo_lado"):
        foco.location = (0, -Y, 0.55)
    cd.dof.focus_object = foco
    cd.dof.aperture_fstop = max(1.4, cd.dof.aperture_fstop * FM)
print("DOF f/", round(cd.dof.aperture_fstop, 1))

# ------------------------------------------------------------------ render
r = sc.render
r.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = A.samples
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.015
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 8; sc.cycles.glossy_bounces = 4; sc.cycles.transmission_bounces = 8
sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 0.5
r.use_persistent_data = True
r.use_motion_blur = True; r.motion_blur_shutter = 0.6 if manejo else 0.35
r.resolution_x, r.resolution_y, r.resolution_percentage = *PLAN.get("res", (1080, 1920)), 100
vs = sc.view_settings
vs.view_transform = "AgX"
for look in (("AgX - Punchy", "Punchy") if LIV else ()) + ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Base Contrast"):
    try:
        vs.look = look
        break
    except TypeError:
        pass
vs.exposure = PLAN.get("exposure", -0.5 if ESC == "estudio" else 0.0)   # -0.5: la pintura no se lava a crema

os.makedirs(A.out, exist_ok=True)
if A.still:
    sc.frame_set(max(1, N // 2))
    r.image_settings.file_format = "JPEG"; r.image_settings.quality = 97
    r.filepath = os.path.join(A.out, f"still_{PLAN.get('id', 'x')}_{A.shot:02d}_{t}.jpg")
    bpy.ops.render.render(write_still=True)
else:
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"; r.ffmpeg.ffmpeg_preset = "GOOD"
    if A.rango:
        a, b = (int(x) for x in A.rango.split("-"))
        sc.frame_start, sc.frame_end = a, min(b, N)
    r.filepath = os.path.join(A.out, f"toma_{A.shot:02d}_")
    bpy.ops.render.render(animation=True)
print("LISTO", t, N)
