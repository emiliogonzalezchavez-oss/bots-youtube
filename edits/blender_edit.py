"""Edit de coche en Blender (headless). Uso:
blender -b -P edits/blender_edit.py -- --plan plan.json --shot 0 --car CarConcept.gltf --hdri cielo.hdr --out salida/
Renderiza UNA toma del plan (cada toma corre en su propio job de GitHub Actions, en paralelo).
Reglas de calidad: nunca modelar el coche con primitivas; siempre un modelo real importado,
luz HDRI + luces de estudio, motion blur, profundidad de campo y cámara con vibración leve.
"""
import argparse, json, math, os, sys
import bpy
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--plan", required=True)
ap.add_argument("--shot", type=int, required=True)
ap.add_argument("--car", required=True)
ap.add_argument("--hdri", required=True)
ap.add_argument("--out", required=True)
ap.add_argument("--samples", type=int, default=48)
ap.add_argument("--preview", action="store_true", help="render rápido de 1 frame a baja resolución")
A = ap.parse_args(argv)
PLAN = json.load(open(A.plan))
SHOT = PLAN["shots"][A.shot]
FPS = PLAN.get("fps", 30)
N = SHOT["frames"]
SPEED = SHOT.get("speed", 24.0)          # m/s en tomas en movimiento
PAINT = PLAN.get("paint", "Carmine")        # Carmine / Pearl / Graphite (variantes del modelo)

# ---------------------------------------------------------------- escena limpia
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.fps = FPS
sc.frame_start, sc.frame_end = 1, N


def mat(name, color=(0.05, 0.05, 0.05), rough=0.3, metal=0.0, emit=None, emit_str=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    if emit:
        p.inputs["Emission Color"].default_value = (*emit, 1)
        p.inputs["Emission Strength"].default_value = emit_str
    return m


def link(ob):
    bpy.context.scene.collection.objects.link(ob)
    return ob


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    e.location = loc
    link(e)
    if parent:
        e.parent = parent
    return e


def plane(name, sx, sy, loc, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=loc, rotation=rot)
    o = bpy.context.object
    o.name = name
    o.scale = (sx, sy, 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    o.data.materials.append(material)
    return o


# ---------------------------------------------------------------- coche real (importado)
bpy.ops.import_scene.gltf(filepath=A.car)
imported = [o for o in bpy.context.scene.objects]
# Quitar el logo de Khronos (marca registrada, no entra en la licencia CC-BY)
for img in bpy.data.images:
    if "khronos" in img.name.lower():
        img.pixels[:] = [0.0, 0.0, 0.0, 1.0] * (len(img.pixels) // 4)
        img.update()
# Variante de pintura
try:
    bpy.ops.scene.gltf2_display_variant(variant_index=0)
except Exception:
    pass
for o in imported:
    for slot in getattr(o, "material_slots", []):
        m = slot.material
        if m and m.name.startswith("Paint") and PAINT not in m.name:
            alt = bpy.data.materials.get(m.name.rsplit(" ", 1)[0] + " " + PAINT)
            if alt:
                slot.material = alt

car = empty("CarRig")
bpy.context.view_layer.update()
for o in imported:
    if o.parent is None:
        mw = o.matrix_world.copy()
        o.parent = car
        o.matrix_world = mw
bpy.context.view_layer.update()


def bbox(objs):
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


mn, mx = bbox(imported)
center = (mn + mx) / 2
heads = [o for o in imported if "Headlight" in o.name]
hc = sum((bbox([h])[0] + bbox([h])[1] for h in heads), Vector()) / (2 * max(1, len(heads))) if heads else center + Vector((1, 0, 0))
d = hc - center
ang = math.atan2(d.y, d.x)                      # dirección del frente
for o in imported:
    if o.parent == car:
        o.location -= Vector((center.x, center.y, mn.z))
bpy.context.view_layer.update()
# aplicar la rotación a los hijos para que CarRig quede limpio (frente +X, izquierda +Y, arriba +Z)
R = Matrix.Rotation(-ang, 4, "Z")
for o in imported:
    if o.parent == car:
        o.matrix_basis = R @ o.matrix_basis
bpy.context.view_layer.update()
mn, mx = bbox(imported)
L, W, H = mx.x - mn.x, mx.y - mn.y, mx.z - mn.z

# Ruedas que giran: un pivote por rueda, rin + llanta giran, la pinza de freno no
wheels = []
for o in imported:
    if o.name.startswith("Wheel") and o.type == "EMPTY":
        wmn, wmx = bbox([c for c in o.children_recursive if c.type == "MESH"])
        wc = (wmn + wmx) / 2
        piv = empty(o.name + "_spin", parent=car)
        piv.matrix_world = Matrix.Translation(wc)
        bpy.context.view_layer.update()
        for c in list(o.children):
            if "BrakePad" in c.name:
                continue
            mw = c.matrix_world.copy()
            c.parent = piv
            c.matrix_world = mw
        wheels.append((piv, max(0.2, (wmx.z - wmn.z) / 2)))
bpy.context.view_layer.update()

# Faros y calaveras encendidos
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    p = m.node_tree.nodes.get("Principled BSDF")
    if not p:
        continue
    n = m.name.lower()
    if "headlight" in n:
        p.inputs["Emission Color"].default_value = (1.0, 0.95, 0.85, 1)
        p.inputs["Emission Strength"].default_value = 25
    elif "brakelight" in n or "taillight" in n:
        p.inputs["Emission Color"].default_value = (1.0, 0.02, 0.01, 1)
        p.inputs["Emission Strength"].default_value = 12

# ---------------------------------------------------------------- mundo: carretera nocturna tipo túnel
world = bpy.data.worlds.new("Mundo")
sc.world = world
world.use_nodes = True
wn, wl = world.node_tree.nodes, world.node_tree.links
wn.clear()
env = wn.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(A.hdri)
bg = wn.new("ShaderNodeBackground")
bg.inputs["Strength"].default_value = 0.35
dark = wn.new("ShaderNodeBackground")
dark.inputs["Color"].default_value = (0.004, 0.005, 0.009, 1)
lp = wn.new("ShaderNodeLightPath")
mix = wn.new("ShaderNodeMixShader")
out = wn.new("ShaderNodeOutputWorld")
wl.new(env.outputs["Color"], bg.inputs["Color"])
wl.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wl.new(bg.outputs["Background"], mix.inputs[1])     # reflejos: HDRI
wl.new(dark.outputs["Background"], mix.inputs[2])   # lo que ve la cámara: noche
wl.new(mix.outputs["Shader"], out.inputs["Surface"])

# Asfalto mojado procedural (charcos = reflejos)
asf = bpy.data.materials.new("Asfalto")
asf.use_nodes = True
nt = asf.node_tree
p = nt.nodes["Principled BSDF"]
tc = nt.nodes.new("ShaderNodeTexCoord")
n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.inputs["Scale"].default_value = 0.35; n1.inputs["Detail"].default_value = 6
n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.inputs["Scale"].default_value = 60; n2.inputs["Detail"].default_value = 2
ramp = nt.nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].position, ramp.color_ramp.elements[1].position = 0.45, 0.6
ramp.color_ramp.elements[0].color = (0.04, 0.04, 0.04, 1)     # charco: casi espejo
ramp.color_ramp.elements[1].color = (0.55, 0.55, 0.55, 1)     # asfalto seco
bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.15
nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], p.inputs["Roughness"])
nt.links.new(n2.outputs["Fac"], bump.inputs["Height"])
nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
p.inputs["Base Color"].default_value = (0.012, 0.012, 0.013, 1)
plane("Carretera", 3000, 40, (500, 0, 0), asf)

# Líneas de carril discontinuas (dan sensación de velocidad)
linea = plane("Linea", 3.0, 0.14, (-1000, -1.9, 0.004), mat("Pintura", (0.8, 0.8, 0.75), 0.6))
arr = linea.modifiers.new("arr", "ARRAY"); arr.count = 330; arr.relative_offset_displace = (2.0, 0, 0)
linea2 = plane("Linea2", 3.0, 0.14, (-1000, 1.9, 0.004), linea.data.materials[0])
arr = linea2.modifiers.new("arr", "ARRAY"); arr.count = 330; arr.relative_offset_displace = (2.0, 0, 0)

# Lámparas de túnel en el techo cada 9 m: barren la pintura cuando el coche avanza
lamp = plane("Lampara", 0.35, 5.0, (-1000, 0, 7.5), mat("LuzTunel", (0, 0, 0), 1, emit=(1.0, 0.86, 0.65), emit_str=45))
arr = lamp.modifiers.new("arr", "ARRAY"); arr.use_relative_offset = False; arr.use_constant_offset = True
arr.constant_offset_displace = (9.0, 0, 0); arr.count = 330
lamp.visible_shadow = False
# Paredes laterales oscuras con franja de neón
pared = mat("Pared", (0.02, 0.02, 0.025), 0.45)
plane("ParedI", 3000, 9, (500, 9, 4.5), pared, rot=(math.radians(90), 0, 0))
plane("ParedD", 3000, 9, (500, -9, 4.5), pared, rot=(math.radians(90), 0, 0))
neon = mat("Neon", (0, 0, 0), 1, emit=(0.1, 0.45, 1.0), emit_str=18)
plane("NeonI", 3000, 0.08, (500, 8.95, 1.2), neon, rot=(math.radians(90), 0, 0))
plane("NeonD", 3000, 0.08, (500, -8.95, 1.2), mat("NeonR", (0, 0, 0), 1, emit=(1.0, 0.05, 0.2), emit_str=18), rot=(math.radians(90), 0, 0))

# ---------------------------------------------------------------- luces que siguen al coche
def area(name, loc, rot, size, energy, color, parent=car, shape="RECTANGLE", sy=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.color, ld.shape = energy, color, shape
    ld.size = size
    if sy:
        ld.size_y = sy
    ob = bpy.data.objects.new(name, ld)
    ob.location, ob.rotation_euler = loc, rot
    link(ob)
    ob.parent = parent
    return ob

area("Key", (0, 0, H + 3.2), (0, 0, 0), 2.5, 600, (1, 0.97, 0.92), shape="RECTANGLE", sy=L * 1.2)
area("RimRojo", (-L * 0.7, W * 1.6, 0.8), (math.radians(80), 0, math.radians(-140)), 1.5, 350, (1, 0.1, 0.15))
area("RimAzul", (L * 0.7, -W * 1.6, 0.9), (math.radians(80), 0, math.radians(40)), 1.5, 350, (0.15, 0.45, 1))
for s in (-1, 1):  # haces de los faros sobre el piso
    sd = bpy.data.lights.new("Faro", "SPOT")
    sd.energy, sd.spot_size, sd.spot_blend, sd.color = 900, math.radians(55), 0.6, (1, 0.95, 0.85)
    so = bpy.data.objects.new("Faro", sd)
    so.location = (mx.x - 0.2, s * W * 0.32, 0.65)
    so.rotation_euler = (0, math.radians(-82), 0)   # apunta al frente (+X) y un poco abajo
    link(so); so.parent = car

# ---------------------------------------------------------------- animación del coche
def drive(speed, x0=0.0):
    dist = speed * (N - 1) / FPS
    car.location = (x0, 0, 0); car.keyframe_insert("location", frame=1)
    car.location = (x0 + dist, 0, 0); car.keyframe_insert("location", frame=N)
    for piv, r in wheels:
        piv.rotation_euler.y = 0; piv.keyframe_insert("rotation_euler", frame=1)
        piv.rotation_euler.y = dist / r; piv.keyframe_insert("rotation_euler", frame=N)
    for ob in [car] + [p for p, _ in wheels]:
        for fc in ob.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"

# ---------------------------------------------------------------- cámara
cd = bpy.data.cameras.new("Cam")
cam = bpy.data.objects.new("Cam", cd)
link(cam)
sc.camera = cam
cd.dof.use_dof = True
cd.dof.aperture_fstop = SHOT.get("fstop", 2.8)
cd.sensor_width = 36
target = empty("Mira", (0, 0, H * 0.45), parent=car)
cd.dof.focus_object = target
tt = cam.constraints.new("TRACK_TO")
tt.target, tt.track_axis, tt.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"


def cam_path(points, lens=(35, 35), parent=car, world=False):
    """points: [(frame_rel 0..1, (x,y,z))] en coords locales del coche (o del mundo)"""
    if not world:
        cam.parent = parent
    for f, loc in points:
        cam.location = loc
        cam.keyframe_insert("location", frame=1 + round(f * (N - 1)))
    cd.lens = lens[0]; cd.keyframe_insert("lens", frame=1)
    cd.lens = lens[1]; cd.keyframe_insert("lens", frame=N)
    for fc in list(cam.animation_data.action.fcurves) + list(cd.animation_data.action.fcurves):
        for k in fc.keyframe_points:
            k.interpolation = "BEZIER"
            k.easing = "EASE_IN_OUT"


def shake(strength=0.004, scale=12):
    """vibración tipo cámara en mano sobre la mira"""
    for i in range(3):
        target.keyframe_insert("location", index=i, frame=1)
        fc = target.animation_data.action.fcurves.find("location", index=i)
        nm = fc.modifiers.new("NOISE")
        nm.strength, nm.scale, nm.phase = strength * 20, scale, 10 * i + A.shot * 7


tipo = SHOT["name"]
if tipo == "reveal":                       # coche quieto, la cámara se acerca desde abajo con faros encendidos
    target.location = (L * 0.15, 0, H * 0.45)
    cam_path([(0, (L * 1.7, -W * 2.4, 0.35)), (1, (L * 1.05, -W * 1.35, 0.45))], lens=(28, 35))
    shake(0.002)
elif tipo == "rueda":                      # rueda delantera girando, cámara pegada al coche
    drive(SPEED)
    fw = max(wheels, key=lambda w: (w[0].location.x, -w[0].location.y))[0] if wheels else target
    target.parent = car
    target.location = fw.location if wheels else (L * 0.3, -W / 2, 0.35)
    cd.dof.focus_object = target
    cam_path([(0, (fw.location.x + 1.4, -W * 1.5, 0.25)), (1, (fw.location.x + 0.4, -W * 1.25, 0.3))], lens=(24, 30))
    shake(0.003, 6)
elif tipo == "lateral":                    # toma lateral siguiendo al coche
    drive(SPEED)
    cam_path([(0, (L * 0.35, -W * 3.0, 0.7)), (1, (-L * 0.25, -W * 2.6, 0.9))], lens=(45, 40))
    shake(0.004, 8)
elif tipo == "trasera":                    # baja, detrás, con las calaveras rojas
    drive(SPEED)
    target.location = (-L * 0.2, 0, H * 0.4)
    cam_path([(0, (-L * 1.6, -W * 0.6, 0.35)), (1, (-L * 1.25, W * 0.4, 0.45))], lens=(30, 26))
    shake(0.005, 5)
elif tipo == "cenital":                    # pasa por encima del coche
    drive(SPEED)
    cam_path([(0, (-L * 0.8, 0.01, H + 4.5)), (0.5, (0, 0.01, H + 3.2)), (1, (L * 1.3, 0.01, H + 1.4))], lens=(22, 26))
    shake(0.003, 10)
elif tipo == "pasada":                     # cámara fija en el piso, el coche pasa volando
    x0 = -SPEED * (N - 1) / FPS * 0.55
    drive(SPEED * 1.4, x0)
    cam.parent = None
    cam.location = (0, -W * 1.4, 0.3)
    cd.lens = 18
    shake(0.006, 4)
elif tipo == "orbita":                     # vuelta alrededor del coche quieto
    pts = []
    for i in range(5):
        a = math.radians(-70 + i * 45)
        pts.append((i / 4, (math.cos(a) * L * 1.15, math.sin(a) * L * 1.15, 0.6 + 0.3 * math.sin(i))))
    cam_path(pts, lens=(30, 30))
    shake(0.002)

# ---------------------------------------------------------------- render
r = sc.render
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 8 if A.preview else A.samples
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.04
sc.cycles.use_denoising = True
sc.cycles.denoiser = "OPENIMAGEDENOISE"
sc.cycles.max_bounces = 6
sc.cycles.glossy_bounces = 3
sc.cycles.transmission_bounces = 4
sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
sc.render.use_persistent_data = True
r.use_motion_blur = True
r.motion_blur_shutter = 0.5
r.resolution_x, r.resolution_y = 1080, 1920
r.resolution_percentage = 30 if A.preview else 100
r.film_transparent = False
vs = sc.view_settings
vs.view_transform = "AgX"
for look in ("AgX - Punchy", "Punchy", "AgX - High Contrast"):
    try:
        vs.look = look
        break
    except TypeError:
        continue
vs.exposure = SHOT.get("exposure", 0.0)

os.makedirs(A.out, exist_ok=True)
if A.preview:
    sc.frame_set(N // 2)
    r.image_settings.file_format = "JPEG"
    r.filepath = os.path.join(A.out, f"preview_{A.shot}_{tipo}.jpg")
    bpy.ops.render.render(write_still=True)
else:
    r.image_settings.file_format = "FFMPEG"
    r.ffmpeg.format = "MPEG4"
    r.ffmpeg.codec = "H264"
    r.ffmpeg.constant_rate_factor = "PERC_LOSSLESS"
    r.ffmpeg.ffmpeg_preset = "GOOD"
    r.filepath = os.path.join(A.out, f"toma_{A.shot:02d}_")
    bpy.ops.render.render(animation=True)
print("LISTO", tipo, N, "frames", f"L={L:.2f} W={W:.2f} H={H:.2f}", "ruedas", len(wheels))
