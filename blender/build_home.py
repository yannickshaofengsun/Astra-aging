"""Build the synthetic Astra Aging household using Blender's bundled Python.

blender --background --python blender/build_home.py -- --glb
python3 blender/build_home.py --check-layout  # no Blender required

Dimensions are illustrative metres. This is a coordination demo, not a
scanned home, accessibility assessment, navigation planner, or safety model.
"""

import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets"
ROOMS = [
    ("BEDROOM", (-2.4, 1.55), (3.2, 2.9), "sand"),
    ("LIVING", (-2.4, -1.45), (3.2, 3.1), "warm"),
    ("HALL", (0.2, 0), (2.0, 6.0), "cream"),
    ("BATHROOM", (2.6, 1.85), (2.8, 2.3), "pale_teal"),
    ("ENTRANCE", (2.6, -1.15), (2.8, 3.7), "sand"),
]
# (name, centre xyz, dimensions xyz, material)
WALLS = [
    ("Back wall", (0, 3.04, 1.1), (8.16, 0.16, 2.2), "cream"),
    ("West wall", (-4.04, 0, 1.1), (0.16, 6.0, 2.2), "cream"),
    ("Bedroom partition west", (-3.45, 0.1, 0.55), (1.1, 0.12, 1.1), "cream"),
    ("Bedroom partition east", (-1.22, 0.1, 0.55), (0.84, 0.12, 1.1), "cream"),
    ("Bedroom hall wall north", (-0.8, 2.66, 0.55), (0.12, 0.68, 1.1), "cream"),
    ("Bedroom hall wall south", (-0.8, 0.6, 0.55), (0.12, 1.0, 1.1), "cream"),
    ("Bathroom hall wall north", (1.2, 2.66, 0.55), (0.12, 0.68, 1.1), "cream"),
    ("Bathroom hall wall south", (1.2, 0.91, 0.55), (0.12, 0.42, 1.1), "cream"),
    ("Bathroom front wall", (2.6, 0.7, 0.40), (2.8, 0.12, 0.80), "cream"),
]
FURNITURE = [
    ("Bed frame", (-2.7, 1.78, 0.24), (1.45, 2.12, 0.38), "wood"),
    ("Mattress", (-2.7, 1.78, 0.49), (1.39, 2.05, 0.22), "linen"),
    ("Duvet", (-2.7, 1.50, 0.62), (1.4, 1.5, 0.13), "teal"),
    ("Pillow", (-2.7, 2.52, 0.67), (0.88, 0.4, 0.18), "linen"),
    ("Bedside table", (-3.65, 2.44, 0.35), (0.42, 0.5, 0.7), "wood"),
    ("Sofa base", (-2.8, -1.16, 0.32), (1.92, 0.78, 0.48), "clay"),
    ("Sofa back", (-2.8, -0.85, 0.65), (1.92, 0.18, 0.64), "clay"),
    ("Sofa left arm", (-3.67, -1.16, 0.54), (0.2, 0.76, 0.42), "clay"),
    ("Sofa right arm", (-1.93, -1.16, 0.54), (0.2, 0.76, 0.42), "clay"),
    ("Rug", (-2.6, -2.10, 0.055), (2.18, 1.34, 0.025), "linen"),
    ("Coffee table", (-2.6, -2.05, 0.36), (1.05, 0.62, 0.12), "wood"),
    ("Table pedestal", (-2.6, -2.05, 0.19), (0.28, 0.28, 0.32), "wood"),
    ("Shower tray", (3.25, 2.26, 0.1), (1.15, 1.25, 0.16), "linen"),
    ("Shower divider", (2.64, 2.32, 0.77), (0.06, 1.23, 1.45), "pale_teal"),
    ("Basin cabinet", (1.83, 2.55, 0.42), (0.82, 0.56, 0.8), "wood"),
    ("Basin top", (1.83, 2.55, 0.85), (0.87, 0.61, 0.09), "linen"),
    ("Toilet cistern", (3.45, 1.13, 0.62), (0.40, 0.22, 0.55), "linen"),
    ("Toilet base", (3.45, 1.36, 0.29), (0.35, 0.46, 0.48), "linen"),
    ("Document shelf", (0.93, -1.48, 0.43), (1.28, 0.42, 0.82), "wood"),
    ("Shelf lower divider", (0.93, -1.5, 0.42), (1.2, 0.44, 0.06), "cream"),
    ("Appointment folder", (0.73, -1.45, 0.88), (0.44, 0.31, 0.035), "orange"),
    ("Ready bag", (1.30, -1.45, 0.96), (0.3, 0.22, 0.20), "teal"),
    ("Entry bench", (3.30, -1.91, 0.39), (0.62, 1.16, 0.14), "wood"),
    ("Bench support front", (3.30, -2.32, 0.21), (0.44, 0.1, 0.35), "wood"),
    ("Bench support back", (3.30, -1.50, 0.21), (0.44, 0.1, 0.35), "wood"),
    ("Door mat", (3.46, -0.55, 0.055), (0.88, 1.15, 0.028), "clay"),
]
ROUTE = [(-1.65, 1.70), (0.20, 1.70), (0.20, -0.55), (2.80, -0.55), (3.75, -0.55)]


def check_layout():
    """Catch malformed dimensions and a route drawn through solid furniture."""
    names = [item[0] for item in WALLS + FURNITURE]
    assert len(names) == len(set(names)), "Object names must be unique"
    assert sum(w * d for _, _, (w, d), _ in ROOMS) == 48, "Room areas must total 48 m²"
    for name, (x, y, z), dims, _ in WALLS + FURNITURE:
        assert all(math.isfinite(v) and v > 0 for v in dims), name
        assert all(math.isfinite(v) for v in (x, y, z)), name
    # ponytail: schematic centreline only; use measured geometry and swept-volume
    # collision checks before making any real mobility or safety claims.
    solids = [item for item in WALLS + FURNITURE if item[1][2] + item[2][2] / 2 > 0.15]
    for a, b in zip(ROUTE, ROUTE[1:]):
        for step in range(101):
            x, y = (a[i] + (b[i] - a[i]) * step / 100 for i in (0, 1))
            assert -4 < x < 4 and -3 < y < 3
            for name, (cx, cy, _), (width, depth, _), _ in solids:
                assert not (abs(x - cx) < width / 2 and abs(y - cy) < depth / 2), f"Route intersects {name}"
    print("PASS: 48 m² illustrative layout, positive dimensions, unique objects, departure centreline clear")


def build():
    import bpy
    from mathutils import Vector

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    palette = {
        "cream": "F5EEDD", "sand": "DEC7A7", "warm": "E7D7BE", "wood": "B98454",
        "linen": "FFF8E9", "teal": "236D6B", "pale_teal": "BAD6CD", "clay": "B97861",
        "orange": "ED9B4D", "ink": "253F3E", "ground": "E8E4DA", "white": "FFFFFF",
    }
    materials = {}
    for name, color in palette.items():
        mat = bpy.data.materials.new(name)
        rgb = tuple(int(color[i:i + 2], 16) / 255 for i in (0, 2, 4))
        rgb = tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb)
        mat.diffuse_color = (*rgb, 1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*rgb, 1)
        shader.inputs["Roughness"].default_value = 0.78
        materials[name] = mat

    def cube(name, location, dimensions, material, bevel=0.035):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(materials[material])
        if bevel:
            mod = obj.modifiers.new("Soft edges", "BEVEL")
            mod.width = min(bevel, min(dimensions) / 4)
            mod.segments = 3
            obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return obj

    def cylinder(name, location, radius, depth, material):
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=radius, depth=depth, location=location)
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(materials[material])
        mod = obj.modifiers.new("Soft edges", "BEVEL")
        mod.width = 0.015
        mod.segments = 3
        return obj

    def text(name, body, location, size=0.2, material="ink", facing=False):
        curve = bpy.data.curves.new(name, "FONT")
        curve.body = body
        curve.size = size
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        curve.extrude = 0.001
        obj = bpy.data.objects.new(name, curve)
        scene.collection.objects.link(obj)
        obj.location = location
        obj.data.materials.append(materials[material])
        if facing:
            obj.rotation_euler = scene.camera.rotation_euler
        return obj

    cube("Apartment base", (0, 0, -0.14), (8.28, 6.28, 0.3), "linen", 0.08)
    for name, (x, y), (w, d), material in ROOMS:
        cube(name + " floor", (x, y, 0.025), (w - 0.025, d - 0.025, 0.04), material, 0.005)
    for spec in WALLS + FURNITURE:
        cube(*spec)
    cube("Window frame", (-2.35, 2.93, 1.50), (1.65, 0.09, 0.87), "wood")
    cube("Window glass", (-2.35, 2.87, 1.50), (1.48, 0.05, 0.70), "pale_teal")
    cube("Window mullion", (-2.35, 2.82, 1.50), (0.055, 0.06, 0.72), "linen")
    cube("Basin mirror", (1.84, 2.91, 1.43), (0.7, 0.035, 0.73), "pale_teal")
    cylinder("Toilet seat", (3.45, 1.36, 0.54), 0.245, 0.07, "linen")
    cylinder("Bedside lamp base", (-3.65, 2.44, 0.73), 0.13, 0.05, "orange")
    cylinder("Bedside lamp stem", (-3.65, 2.44, 0.85), 0.025, 0.23, "wood")
    cylinder("Bedside lamp shade", (-3.65, 2.44, 1.02), 0.17, 0.22, "linen")
    cylinder("Plant pot", (-3.62, -2.51, 0.23), 0.20, 0.38, "clay")
    for i in range(5):
        angle = i * math.tau / 5
        bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, location=(-3.62 + 0.14 * math.cos(angle), -2.51 + 0.14 * math.sin(angle), 0.64))
        leaf = bpy.context.object
        leaf.name = "Plant leaf"
        leaf.scale = (0.13, 0.13, 0.33)
        leaf.rotation_euler = (0.35 * math.sin(angle), 0.35 * math.cos(angle), 0)
        leaf.data.materials.append(materials["teal"])

    for index, (a, b) in enumerate(zip(ROUTE, ROUTE[1:])):
        length = math.dist(a, b)
        for step in range(max(1, int(length / 0.28))):
            t = (step + 0.5) / max(1, int(length / 0.28))
            point = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, 0.072)
            obj = cube(f"Route {index} dash {step}", point, (0.14, 0.052, 0.013), "teal", 0.01)
            obj.rotation_euler.z = math.atan2(b[1] - a[1], b[0] - a[0])
    for index, position in enumerate([ROUTE[1], (1.7, -0.55), ROUTE[-1]], start=1):
        cylinder(f"Departure step {index}", (*position, 0.083), 0.17, 0.025, "orange")
        text(f"Step {index} number", str(index), (*position, 0.101), 0.19, "ink")
    text("Bedroom label", "BEDROOM", (-2.60, 0.46, 0.07), 0.22)
    text("Living label", "LIVING", (-2.62, -2.89, 0.07), 0.22)
    text("Hall label", "HALL", (0.17, 2.72, 0.07), 0.20)
    text("Entrance label", "ENTRANCE", (2.40, -2.77, 0.07), 0.22)
    text("Shelf label", "DOCUMENTS", (0.89, -1.98, 0.075), 0.17)

    cube("Backdrop", (0, 0, -0.40), (200, 200, 0.20), "ground", 0)
    bpy.ops.object.camera_add(location=(10, -13, 13))
    camera = bpy.context.object
    camera.name = "Home overview"
    camera.rotation_euler = (Vector((0, 0, 0.5)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 13.0
    scene.camera = camera
    text("Appointment folder annotation", "APPOINTMENT FOLDER", (0.84, -1.46, 1.35), 0.16, "ink", True)
    text("Bathroom label", "BATHROOM", (2.75, 0.76, 1.06), 0.18, "ink", True)
    text("Exit annotation", "PICKUP", (3.72, -0.57, 0.71), 0.19, "ink", True)

    for name, location, energy, size in [
        ("Large soft key", (1, -4, 10), 1400, 7),
        ("Window fill", (-6, 1, 7), 950, 5),
        ("Back fill", (3, 6, 8), 1000, 5),
    ]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.color = (0.6, 0.6, 0.6)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
    scene["purpose"] = "Synthetic family coordination demo; not validated for real household safety"
    scene["floor_area_m2"] = 48.0
    scene["departure_route"] = str(ROUTE)
    bpy.context.view_layer.update()
    assert "Appointment folder" in bpy.data.objects
    assert "Document shelf" in bpy.data.objects
    assert abs(bpy.data.objects["Bed frame"].dimensions.y - 2.12) < 0.01
    assert scene.unit_settings.system == "METRIC"
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.color_type = "MATERIAL"
                area.spaces.active.overlay.show_overlays = False
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.context.preferences.filepaths.save_version = 0
    OUTPUT.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUTPUT / "home.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "home.blend"))
    if "--glb" in sys.argv:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in scene.objects:
            if obj.type in {"MESH", "FONT"} and obj.name != "Backdrop":
                obj.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "home.glb"), export_format="GLB", use_selection=True, export_apply=True, export_cameras=False, export_lights=False)
    bpy.ops.render.render(write_still=True)
    print(f"PASS: {len(scene.objects)} scene objects; saved {OUTPUT / 'home.blend'} and {OUTPUT / 'home.png'}")


if __name__ == "__main__":
    check_layout()
    if not {"--check-layout", "--check"}.intersection(sys.argv):
        build()
