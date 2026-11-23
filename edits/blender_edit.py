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
ap.add_argument("--samples", type=int, default=128)
ap.add_argument("--still", action="store_true", help="1 frame a resolución completa (revisión de calidad)")
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
BASURA = ("plane", "ground", "floor", "shadow", "backdrop", "background", "studio", "cyc", "sky", "piso")
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
mn, mx = bbox(objs)
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
ang = {"+X": 0, "-X": math.pi, "+Y": math.pi / 2, "-Y": -math.pi / 2}[front]
center = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
car.matrix_world = Matrix.Rotation(-ang, 4, "Z") @ Matrix.Translation(-center)
bpy.context.view_layer.update()
mn, mx = bbox(objs)
k = LARGO / (mx.x - mn.x)
car.matrix_world = Matrix.Scale(k, 4) @ car.matrix_world
bpy.context.view_layer.update()
mn, mx = bbox(objs)
L, W, H = mx.x - mn.x, mx.y - mn.y, mx.z - mn.z
print(f"COCHE L={L:.2f} W={W:.2f} H={H:.2f} frente={front} objetos={len(objs)}")

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
    es = p.inputs["Emission Strength"]
    ec = p.inputs["Emission Color"]
    emits = ec.is_linked or sum(ec.default_value[:3]) > 0.05
    if any(k in nm for k in ("headl", "drl", "angel", "light_w", "lightwhite")):
        if not ec.is_linked:
            ec.default_value = (1, 0.96, 0.9, 1)
        es.default_value = max(es.default_value, 15)
    elif any(k in nm for k in ("tail", "brake", "stop", "calavera")):
        if not ec.is_linked:
            ec.default_value = (1, 0.05, 0.02, 1)
        es.default_value = max(es.default_value, 10)
    elif emits and es.default_value > 0:
        es.default_value = max(es.default_value, 6)

# ------------------------------------------------------------------ estudio
world = bpy.data.worlds.new("Estudio")
sc.world = world
world.use_nodes = True
wn, wl = world.node_tree.nodes, world.node_tree.links
wn.clear()
bg = wn.new("ShaderNodeBackground"); bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1)
fill = wn.new("ShaderNodeBackground"); fill.inputs["Color"].default_value = (0.6, 0.62, 0.66, 1)
fill.inputs["Strength"].default_value = 0.04
lp = wn.new("ShaderNodeLightPath"); mix = wn.new("ShaderNodeMixShader"); out = wn.new("ShaderNodeOutputWorld")
wl.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wl.new(fill.outputs["Background"], mix.inputs[1])   # relleno tenue para que nada quede 100% negro
wl.new(bg.outputs["Background"], mix.inputs[2])     # la cámara ve negro
wl.new(mix.outputs["Shader"], out.inputs["Surface"])

# Piso: oscuro, semibrillante, se pierde a negro con la distancia (ciclorama infinito)
piso = bpy.data.materials.new("Piso"); piso.use_nodes = True
nt = piso.node_tree; P = nt.nodes["Principled BSDF"]
P.inputs["Base Color"].default_value = (0.018, 0.018, 0.02, 1)
P.inputs["Roughness"].default_value = 0.32
tc = nt.nodes.new("ShaderNodeTexCoord"); vl = nt.nodes.new("ShaderNodeVectorMath"); vl.operation = "LENGTH"
mr = nt.nodes.new("ShaderNodeMapRange"); mr.inputs["From Min"].default_value = 4; mr.inputs["From Max"].default_value = 14
blk = nt.nodes.new("ShaderNodeBsdfDiffuse"); blk.inputs["Color"].default_value = (0, 0, 0, 1)
ms = nt.nodes.new("ShaderNodeMixShader"); outm = nt.nodes["Material Output"]
nt.links.new(tc.outputs["Object"], vl.inputs[0]); nt.links.new(vl.outputs["Value"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ms.inputs["Fac"])
nt.links.new(P.outputs["BSDF"], ms.inputs[1]); nt.links.new(blk.outputs["BSDF"], ms.inputs[2])
nt.links.new(ms.outputs["Shader"], outm.inputs["Surface"])
bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
bpy.context.object.data.materials.append(piso)


def softbox(name, loc, size, size_y, energy, target=(0, 0, 0.6), color=(1, 1, 1)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"; ld.size = size; ld.size_y = size_y
    ld.energy, ld.color = energy, color
    ob = link(bpy.data.objects.new(name, ld))
    ob.location = loc
    ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    ob.visible_camera = False
    return ob


# Iluminación de estudio de autos: cenital grande + tiras laterales + contraluz + relleno frontal
softbox("Cenital", (0.3, 0, H + 3.2), 2.2, L * 1.25, 1400, (0.3, 0, 0))
softbox("TiraIzq", (L * 0.55, W * 2.2, 1.6), 0.5, 3.2, 420, (0, 0, 0.7))
softbox("TiraDer", (-L * 0.55, -W * 2.2, 1.6), 0.5, 3.2, 420, (0, 0, 0.7))
softbox("Contra", (-L * 1.6, 0, 2.2), 3.0, 1.2, 380, (0, 0, 0.6))
softbox("Frente", (L * 1.7, -W * 0.8, 1.2), 1.6, 0.9, 160, (0, 0, 0.6))

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
CALAVERA = (B + 0.25, -Y * 0.72, Z * 0.58)
RUEDA = (F - L * 0.2, -Y, Z * 0.27)


def toma(c0, c1, m0, m1, lens=(85, 85), f=2.8):
    for fr, cl, ml in ((1, c0, m0), (N, c1, m1)):
        cam.location = cl; cam.keyframe_insert("location", frame=fr)
        mira.location = ml; mira.keyframe_insert("location", frame=fr)
    cd.lens = lens[0]; cd.keyframe_insert("lens", frame=1)
    cd.lens = lens[1]; cd.keyframe_insert("lens", frame=N)
    cd.dof.aperture_fstop = f
    for ob in (cam, mira, cd):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.easing = "EASE_IN_OUT"


t = SHOT["name"]
if t == "trasera":        # 3/4 trasero bajo, sube despacio, calaveras encendidas
    toma((B - 3.2, -Y - 2.6, 0.45), (B - 2.8, -Y - 2.2, 1.1), (B + 0.4, -Y * 0.4, 0.6), (B + 0.5, -Y * 0.3, 0.75), (55, 60), 3.5)
elif t == "faro":         # detalle del faro, deslizamiento lento
    toma((F + 1.5, -Y - 0.9, FARO[2] + 0.05), (F + 1.1, -Y - 1.4, FARO[2] + 0.12), FARO, (FARO[0] - 0.05, FARO[1], FARO[2]), (100, 100), 2.8)
elif t == "frente34":     # 3/4 frontal desde arriba, empuje lento
    toma((F + 3.8, -Y - 3.4, 2.4), (F + 3.0, -Y - 2.6, 2.0), (L * 0.15, 0, 0.6), (L * 0.18, 0, 0.6), (50, 55), 4)
elif t == "perfil":       # perfil lateral bajo, dolly a lo largo
    toma((F - 0.3, -Y - 4.6, 0.55), (B + 0.6, -Y - 4.6, 0.6), (F - 1.2, 0, 0.55), (B + 1.2, 0, 0.6), (70, 70), 3.5)
elif t == "rueda":        # rin delantero, arco lento
    toma((RUEDA[0] + 1.4, -Y - 1.3, 0.35), (RUEDA[0] - 0.3, -Y - 1.6, 0.5), RUEDA, RUEDA, (85, 85), 2.8)
elif t == "calavera":     # detalle de calavera
    toma((B - 1.2, -Y - 1.0, CALAVERA[2] + 0.1), (B - 1.4, -Y - 0.4, CALAVERA[2] + 0.05), CALAVERA, CALAVERA, (100, 100), 2.8)
elif t == "cenital":      # desde arriba girando despacio
    toma((0.4, -0.6, H + 6.5), (-0.4, 0.6, H + 6.0), (0, 0, 0.3), (0, 0, 0.3), (40, 45), 5.6)
elif t == "frente":       # de frente, bajo, faros encendidos
    toma((F + 4.0, 0.6, 0.5), (F + 3.4, -0.5, 0.6), (F - 0.5, 0, 0.55), (F - 0.5, 0, 0.6), (70, 75), 3.5)
else:                     # hero 3/4 frontal (still de revisión de modelo)
    toma((F + 3.4, -Y - 3.0, 1.1), (F + 3.3, -Y - 3.0, 1.1), (0.2, 0, 0.62), (0.2, 0, 0.62), (60, 60), 4)

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
r.use_motion_blur = True; r.motion_blur_shutter = 0.3
r.resolution_x, r.resolution_y, r.resolution_percentage = 1080, 1920, 100
vs = sc.view_settings
vs.view_transform = "AgX"
for look in ("AgX - Medium High Contrast", "Medium High Contrast", "AgX - Base Contrast"):
    try:
        vs.look = look
        break
    except TypeError:
        pass
vs.exposure = PLAN.get("exposure", 0.0)

os.makedirs(A.out, exist_ok=True)
if A.still:
    sc.frame_set(max(1, N // 2))
    r.image_settings.file_format = "JPEG"; r.image_settings.quality = 92
    r.filepath = os.path.join(A.out, f"still_{PLAN.get('id', 'x')}_{A.shot:02d}_{t}.jpg")
    bpy.ops.render.render(write_still=True)
else:
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"; r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"; r.ffmpeg.ffmpeg_preset = "GOOD"
    r.filepath = os.path.join(A.out, f"toma_{A.shot:02d}_")
    bpy.ops.render.render(animation=True)
print("LISTO", t, N)
