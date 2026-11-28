"""Inspecciona un modelo cualquiera (p.ej. un pack de llantas): lista objetos y renderiza una vista general.
blender -b -P inspeccionar.py -- modelo.glb salida.jpg"""
import bpy, sys, math
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
bpy.ops.wm.read_factory_settings(use_empty=True)
ext = a[0].lower().rsplit(".", 1)[-1]
if ext in ("glb", "gltf"):
    bpy.ops.import_scene.gltf(filepath=a[0])
elif ext == "fbx":
    bpy.ops.import_scene.fbx(filepath=a[0])
obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.context.view_layer.update()
pts = [o.matrix_world @ Vector(c) for o in obs for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
print("TOTAL", len(obs), "objetos; bbox", tuple(round(v, 3) for v in mn), tuple(round(v, 3) for v in mx))
for o in sorted(obs, key=lambda o: o.name):
    b = [o.matrix_world @ Vector(c) for c in o.bound_box]
    d = Vector((max(p.x for p in b) - min(p.x for p in b), max(p.y for p in b) - min(p.y for p in b), max(p.z for p in b) - min(p.z for p in b)))
    c = sum(b, Vector()) / 8
    print(f"OBJ {o.name[:50]:50s} polys={len(o.data.polygons):7d} dim=({d.x:.3f},{d.y:.3f},{d.z:.3f}) centro=({c.x:.2f},{c.y:.2f},{c.z:.2f}) mats={[s.material.name for s in o.material_slots if s.material][:4]}")
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 64; sc.cycles.device = "CPU"
sc.render.resolution_x, sc.render.resolution_y = 1920, 1080
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True; w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
w.node_tree.nodes["Background"].inputs[0].default_value = (0.6, 0.6, 0.62, 1)
cen = (mn + mx) / 2; r = (mx - mn).length
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.location = cen + Vector((r * 0.9, -r * 1.1, r * 0.6))
cam.rotation_euler = (cen - cam.location).to_track_quat("-Z", "Y").to_euler(); cam.data.lens = 40
sun = bpy.data.objects.new("sol", bpy.data.lights.new("sol", "SUN")); sc.collection.objects.link(sun)
sun.rotation_euler = (0.8, 0.2, 0.6); sun.data.energy = 3
sc.render.image_settings.file_format = "JPEG"; sc.render.filepath = a[1]
bpy.ops.render.render(write_still=True)
