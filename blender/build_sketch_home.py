"""Illustrative reconstruction of the user-provided hand sketch.

python3 blender/build_sketch_home.py --check-layout
.runtime/blender/Blender.app/Contents/MacOS/Blender --background \
    --python blender/build_sketch_home.py

Coordinates are normalized sketch units, never metres. Beds and openings are
symbols; their dimensions and real-world clearances have not been supplied.
The source photo is read by the author only and is not copied into the assets.
"""

import json
import math
from pathlib import Path
import sys


OUTPUT = Path(__file__).resolve().parents[1] / "assets"
# bounds: left, bottom, right, top in a normalized 100 × 58 sketch frame.
ROOMS = [
    ("bedroom_upper_left", "R1", [0, 27, 32, 58], "sand", "bedroom", "user-confirmed"),
    ("toilet_left", "LEFT TOILET", [0, 17, 15, 27], "pale_teal", "toilet; number unclear", "earlier fixture label; latest number ambiguous"),
    ("laundry", "STORAGE / WASHING", [0, 9, 31, 17], "warm", "storage and washing", "observed-label in earlier detailed sketch"),
    ("living2", "LIVING 2", [32, 33, 56, 58], "cream", "living room", "observed-label"),
    ("storage", "STORAGE 2", [32, 17, 56, 33], "warm", "storage", "observed-label"),
    ("bedroom_lower_center", "LOWER BEDROOM", [32, 0, 56, 17], "sand", "bedroom", "user-confirmed; number unresolved"),
    ("bedroom_upper_right", "UPPER-RIGHT BEDROOM", [56, 37, 84, 58], "sand", "bedroom", "user-confirmed; number unresolved"),
    ("living1", "LIVING 1", [56, 17, 84, 37], "cream", "living room", "observed-label"),
    ("outside", "OUTSIDE", [56, 0, 84, 17], "ground", "outside cutout; exact entrance and corridor connection unknown", "observed-label"),
    ("kitchen", "KITCHEN", [84, 26, 100, 58], "pale_teal", "kitchen", "latest K label and earlier sink, fridge, stove labels"),
    ("bathroom", "T1 / SHOWER", [84, 4, 100, 26], "pale_teal", "bathroom", "latest T1 label and earlier shower, sink, toilet labels"),
]
RAW_LABELS = {"bedroom_upper_left": "r3 drawn, superseded by explicit user correction: upper left is r1", "bedroom_upper_right": "r2 (conflicts with lower room2 label)", "bedroom_lower_center": "room2 (conflicts with upper-right r2 label)", "toilet_left": "t3? (ambiguous; earlier sketch said toilet2)", "storage": "Storage 2", "outside": "Outside", "kitchen": "K", "bathroom": "T1"}
# Wall segments are display partitions, not measured or verified doorways.
WALLS = [
    ((0, 58), (100, 58), 0.85), ((0, 17), (0, 58), 0.85),
    ((32, 38), (32, 58), 0.52), ((32, 27), (32, 31), 0.52),
    ((0, 27), (15, 27), 0.45), ((15, 21), (15, 27), 0.45),
    ((0, 17), (22, 17), 0.38), ((32, 33), (48, 33), 0.40),
    ((40, 17), (56, 17), 0.40), ((32, 0), (32, 17), 0.42),
    ((56, 0), (56, 10), 0.42), ((56, 37), (56, 58), 0.52),
    ((56, 37), (62, 37), 0.45), ((73, 37), (84, 37), 0.45),
    ((84, 37), (84, 58), 0.65), ((100, 26), (100, 58), 0.65),
    ((84, 26), (100, 26), 0.42), ((100, 4), (100, 26), 0.42),
    ((84, 4), (84, 18), 0.40), ((56, 17), (70, 17), 0.35),
]
CONNECTIONS = [
    ("bedroom_upper_left", "living2"), ("bedroom_upper_left", "toilet_left"), ("bedroom_upper_left", "laundry"),
    ("living2", "storage"), ("storage", "bedroom_lower_center"), ("living2", "living1"),
    ("living1", "bedroom_upper_right"), ("living1", "outside"), ("living1", "kitchen"),
    ("living1", "bathroom"),
]


def layout():
    return {
        "label": "Your home: approximate sketch reconstruction",
        "source": "User-provided hand sketch",
        "version": 2,
        "interpretation": "Latest refined interior hand sketch governs approximate relative geometry, viewed 90 degrees counterclockwise; earlier sketch supplies fixture details",
        "coordinate_system": {"units": "normalized sketch units", "bounds": [0, 0, 100, 58], "origin": "lower left", "real_world_scale": None},
        "confirmed": [
            "There are three bedrooms; each contains a queen bed",
            "The upper-left bedroom is R1, following the user's explicit correction; the other bedroom numbers remain unresolved",
            "The building has eight apartments per floor",
            "This home combines two apartments; the numbers 1 and 2 on the building diagram identify apartments, not bedrooms",
            "The annotated building diagram places apartment 1 upper/right and apartment 2 left/lower, with a shared corridor at their inner elbow",
            "The annotated entrance is on the lower boundary of apartment 1, opening to the shared corridor",
        ],
        "assumptions": [
            "Room positions and proportions approximate the latest refined hand sketch, with no known physical scale; furniture details come from the earlier sketch",
            "Upper-right and lower-central bedrooms use neutral location labels because both appear numbered r2 or room2; no R3 location is inferred",
            "The left toilet's latest label appears t3, but this number is ambiguous and differs from the earlier toilet2 label",
            "Bed dimensions, furniture placement, wall segments and door gaps are illustrative",
            "Outside is an explicit cutout, not a confirmed entrance or corridor; the game's nearby departure point is fictional",
            "Thick pen strokes do not establish wall thickness, structural status or openings",
            "Building diagrams provide context only; the other six apartments and shared corridor are not reconstructed",
            "The precise division and internal joining opening between the two combined apartments are not established by the interior sketch",
        ],
        "confirmations": [
            {"fact": "Three bedrooms; upper-left bedroom is R1", "provenance": "User clarification, including exact correction: upper left is r1", "other_bedroom_numbers": None},
            {"fact": "Each bedroom contains a queen bed", "provenance": "User clarification relayed by interface task", "bed_dimensions": None},
            {"fact": "Eight apartments per floor; this home combines two apartments", "provenance": "User clarification relayed by root"},
            {"fact": "Apartment 1 upper/right, apartment 2 left/lower; shared corridor at the inner elbow; entrance below apartment 1", "provenance": "User-annotated building diagram, inspected locally", "internal_joining_opening": None},
        ],
        "rooms": [
            {"id": id_, "label": label, "bounds": bounds, "approximate_position": [round((bounds[0] + bounds[2]) / 2, 2), round((bounds[1] + bounds[3]) / 2, 2)],
             "use": use, "use_evidence": evidence, "geometry_evidence": "approximate visual interpretation of latest refined sketch", "measured_dimensions": None,
             "observed_raw_label": RAW_LABELS.get(id_, label),
             "queen_bed": True if use == "bedroom" else None}
            for id_, label, bounds, _, use, evidence in ROOMS
        ],
        "observed_fixture_labels": {"living2": ["sofa", "TV", "table"], "living1": ["table", "TV", "storage", "sofa"], "laundry": ["storage", "washing"], "kitchen": ["sink", "fridge", "stove"], "bathroom": ["shower", "sink", "toilet"]},
        "connections": [{"between": list(pair), "evidence": "inferred from rough adjacency and openings in sketch", "confirmed": False, "traversable": None, "clearance": None} for pair in CONNECTIONS],
        "unknowns": ["All real dimensions and scale", "Queen bed dimensions", "Bedroom numbering for upper-right and lower-central bedrooms; R3 location is not assigned", "Left toilet number: latest t3? versus earlier toilet2", "Meaning of thick pen strokes", "Exact wall thickness, lengths and room shapes", "Door locations, swings and clear widths", "Exact entrance and relationship of Outside cutout to shared corridor", "Confirmed circulation between rooms", "Exact internal joining opening and boundary between the combined apartments", "Household belongings locations and current state"],
        "limitations": "Illustrative reconstruction only. Do not infer navigation, accessibility, renovation quantities or safety from this geometry. Kitchen and bathroom uses are inferred from fixture labels. Furniture placement and door gaps are approximate symbols.",
    }


def check_layout():
    ids = {r[0] for r in ROOMS}
    assert len(ids) == len(ROOMS) == 11
    for _, _, (left, bottom, right, top), _, _, _ in ROOMS:
        assert 0 <= left < right <= 100 and 0 <= bottom < top <= 58
    assert all(a in ids and b in ids for a, b in CONNECTIONS)
    data = layout()
    assert data["coordinate_system"]["real_world_scale"] is None
    assert sum(r["queen_bed"] is True for r in data["rooms"]) == 3
    assert next(r for r in data["rooms"] if r["id"] == "bedroom_upper_left")["label"] == "R1"
    assert all("R3" not in r["label"] for r in data["rooms"])
    assert all(c["confirmed"] is False and c["traversable"] is None for c in data["connections"])
    print("PASS: 11 sketch zones, 3 user-confirmed queen bedrooms, unmeasured scale, connections explicitly unconfirmed")


def build():
    import bpy
    from mathutils import Vector

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "NONE"
    scene["source"] = "User-provided hand sketch"
    scene["units"] = "Normalized sketch units; no known real-world scale"
    scene["limitations"] = layout()["limitations"]
    palette = {"cream": "F5EEDD", "sand": "DEC7A7", "warm": "E7D7BE", "wood": "B98454", "linen": "FFF8E9", "teal": "236D6B", "pale_teal": "BAD6CD", "clay": "B97861", "orange": "ED9B4D", "ink": "253F3E", "ground": "E8E4DA"}
    materials = {}
    for name, color in palette.items():
        mat = bpy.data.materials.new(name)
        rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        mat.diffuse_color = (*rgb, 1)
        mat.use_nodes = True
        shader = mat.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (*rgb, 1)
        shader.inputs["Roughness"].default_value = 0.8
        materials[name] = mat

    def xy(x, y):
        return (x / 10 - 5, y / 10 - 2.9)

    def box(name, x, y, z, w, d, h, material, bevel=0.025):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(*xy(x, y), z))
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = (w / 10, d / 10, h)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(materials[material])
        if bevel:
            mod = obj.modifiers.new("Soft edges", "BEVEL")
            mod.width = min(bevel, min(obj.dimensions) / 4)
            mod.segments = 3
            obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
        return obj

    def disc(name, x, y, z, radius, depth, material):
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=(*xy(x, y), z))
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(materials[material])
        return obj

    def label(name, body, x, y, z=0.063, size=0.14, facing=False):
        curve = bpy.data.curves.new(name, "FONT")
        curve.body = body
        curve.size = size
        curve.align_x = "CENTER"
        curve.align_y = "CENTER"
        obj = bpy.data.objects.new(name, curve)
        scene.collection.objects.link(obj)
        obj.location = (*xy(x, y), z)
        obj.data.materials.append(materials["ink"])
        if facing:
            obj.rotation_euler = scene.camera.rotation_euler
        return obj

    # ponytail: flat symbolic regions preserve the sketch's adjacencies; replace
    # these bounds with measured geometry before evaluating physical movement.
    outline = [(0, 9), (32, 9), (32, 0), (56, 0), (56, 17), (84, 17), (84, 4), (100, 4), (100, 58), (0, 58)]
    mesh = bpy.data.meshes.new("Sketch footprint")
    mesh.from_pydata([(*xy(x, y), -0.01) for x, y in outline], [], [tuple(range(len(outline)))])
    base = bpy.data.objects.new("Approximate sketch footprint", mesh)
    scene.collection.objects.link(base)
    base.data.materials.append(materials["linen"])
    solid = base.modifiers.new("Display plinth", "SOLIDIFY")
    solid.thickness = 0.16
    for id_, name, (left, bottom, right, top), material, _, _ in ROOMS:
        if id_ == "outside":
            continue
        obj = box(id_ + " floor", (left + right) / 2, (bottom + top) / 2, 0.025, right - left - 0.12, top - bottom - 0.12, 0.035, material)
        obj["sketch_zone"] = id_
        obj["dimensions_known"] = False
    for i, ((x1, y1), (x2, y2), height) in enumerate(WALLS):
        box(f"Illustrative partition {i}", (x1 + x2) / 2, (y1 + y2) / 2, height / 2, max(abs(x2 - x1), 0.9), max(abs(y2 - y1), 0.9), height, "cream")

    def bed(name, x, y, turned=False):
        w, d = (12, 9) if turned else (9, 12)
        obj = box(name + " queen bed", x, y, 0.18, w, d, 0.24, "wood")
        obj["presence"] = "user-confirmed"
        obj["size"] = "Queen; actual dimensions unknown"
        box(name + " mattress", x, y, 0.33, w - 0.2, d - 0.2, 0.13, "linen")
        box(name + " duvet", x - (1.4 if turned else 0), y - (0 if turned else 1.4), 0.41, w - (3 if turned else 0), d - (0 if turned else 3), 0.07, "teal")
        box(name + " pillow", x + (4.2 if turned else 0), y + (0 if turned else 4.2), 0.43, 2.3 if turned else 6.2, 6.2 if turned else 2.3, 0.10, "linen")

    bed("Upper-left", 14.0, 44)
    bed("Lower-central", 44.0, 8.5, True)
    bed("Upper-right", 69.5, 47)
    box("Upper-left bedside table", 21.5, 47.5, 0.18, 3.1, 3.5, 0.34, "wood")
    box("Upper-right bedside table", 77.0, 50, 0.18, 3, 3.5, 0.34, "wood")
    disc("Upper-left lamp", 21.5, 47.5, 0.43, 0.105, 0.17, "orange")
    disc("Upper-right lamp", 77.0, 50, 0.43, 0.105, 0.17, "orange")

    box("Living 2 sofa seat", 36.3, 46.5, 0.21, 5.3, 12.6, 0.32, "clay")
    box("Living 2 sofa back", 34.0, 46.5, 0.40, 1.3, 12.2, 0.51, "clay")
    box("Living 2 table", 45.5, 53.3, 0.30, 9.2, 4.9, 0.12, "wood")
    box("Living 2 table leg", 45.5, 53.3, 0.16, 2.1, 2.1, 0.27, "wood")
    box("Living 2 TV stand", 53.2, 40.0, 0.20, 3.0, 6.3, 0.33, "wood")
    box("Living 2 TV", 53.7, 40.0, 0.56, 0.55, 6.2, 0.39, "ink")
    box("Storage 2 cabinet", 44.8, 29.0, 0.24, 14.5, 3.1, 0.43, "wood")
    box("Storage 2 doors", 44.8, 27.35, 0.24, 13.2, 0.15, 0.32, "cream")
    box("Laundry cupboard", 10.0, 13.1, 0.23, 13.0, 4.1, 0.42, "wood")
    box("Washing machine", 23.5, 13.1, 0.24, 4.8, 4.4, 0.44, "linen")
    box("Washer front", 23.5, 10.86, 0.24, 2.8, 0.12, 0.27, "teal")
    box("Left toilet cistern", 4.5, 24.7, 0.29, 2.6, 1.6, 0.4, "linen")
    disc("Left toilet seat", 4.5, 22.8, 0.22, 0.17, 0.15, "linen")

    box("Living 1 table", 63.0, 31.0, 0.30, 8.2, 5.4, 0.12, "wood")
    box("Living 1 table pedestal", 63.0, 31.0, 0.16, 2.1, 2.1, 0.27, "wood")
    box("Living 1 media cabinet", 62.8, 19.7, 0.20, 10.5, 2.8, 0.33, "wood")
    box("Living 1 TV", 60.3, 19.7, 0.53, 4.4, 0.45, 0.34, "ink")
    box("Living 1 sofa", 80.0, 26.7, 0.21, 4.4, 8.5, 0.32, "clay")
    box("Living 1 sofa back", 82.0, 26.7, 0.38, 1.1, 8.1, 0.45, "clay")

    box("Kitchen fridge", 87.0, 45.6, 0.55, 3.4, 6.4, 1.03, "linen")
    box("Kitchen back counter", 92.0, 55.8, 0.33, 13.0, 3.2, 0.60, "wood")
    box("Kitchen sink", 92.0, 55.8, 0.642, 3.3, 2.2, 0.05, "pale_teal")
    box("Kitchen stove", 97.0, 43.5, 0.33, 3.5, 6.0, 0.60, "linen")
    for x in [96.2, 97.7]:
        for y in [42.3, 44.6]:
            disc("Stove burner", x, y, 0.641, 0.047, 0.014, "ink")
    box("Shower tray", 90.5, 8.1, 0.09, 10.8, 5.6, 0.10, "linen")
    box("Bathroom sink cabinet", 96.5, 22.6, 0.28, 4.5, 3.2, 0.52, "wood")
    box("Bathroom basin", 96.5, 22.6, 0.56, 4.7, 3.4, 0.05, "linen")
    box("Bathroom toilet cistern", 97, 16.3, 0.29, 2.6, 1.7, 0.40, "linen")
    disc("Bathroom toilet seat", 97, 14.5, 0.22, 0.17, 0.15, "linen")

    for id_, name, x, y in [
        ("bedroom_upper_left", "R1", 15, 32), ("bedroom_lower_center", "LOWER BEDROOM", 44.0, 2.0),
        ("living2", "LIVING 2", 44.0, 37.6), ("living1", "LIVING 1", 72.0, 21.0),
        ("laundry", "STORAGE / WASHING", 15, 10.0), ("storage", "STORAGE 2", 43.0, 22.0),
    ]:
        label(id_ + " label", name, x, y, size=0.125 if len(name) > 9 else 0.15)

    box("Backdrop", 50, 29, -0.28, 2000, 2000, 0.10, "ground", 0)
    label("Outside label", "OUTSIDE", 70.0, 8.8, -0.218, 0.19)
    bpy.ops.object.camera_add(location=(3.2, -9.5, 13.5))
    camera = bpy.context.object
    camera.name = "Sketch home overview"
    camera.rotation_euler = (Vector((0, 0, 0.15)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 14.2
    scene.camera = camera
    label("Upper-right bedroom label", "UPPER-RIGHT BEDROOM", 69.5, 38.5, 0.68, 0.12, True)
    label("Left toilet label", "LEFT TOILET", 7.3, 18.6, 0.58, 0.13, True)
    label("Kitchen use label", "KITCHEN", 92.0, 31.0, 0.18, 0.14, True)
    label("Bathroom use label", "T1 / SHOWER", 89.0, 18.8, 0.46, 0.12, True)
    for name, location, energy, size in [("Soft key", (0, -5, 10), 1500, 8), ("Left fill", (-7, 2, 6), 1000, 5), ("Back fill", (5, 5, 8), 1100, 5)]:
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
    scene.render.resolution_x = 1800
    scene.render.resolution_y = 1100
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "AgX"
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
    assert all(name + " queen bed" in scene.objects for name in ["Upper-left", "Lower-central", "Upper-right"])
    assert "outside floor" not in scene.objects and "Entrance mat" not in scene.objects
    assert scene.unit_settings.system == "NONE"
    scene.render.filepath = str(OUTPUT / "sketch-home.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT / "sketch-home.blend"))
    for obj in scene.objects:
        if obj.type in {"MESH", "FONT"} and obj.name != "Backdrop":
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUTPUT / "sketch-home.glb"), export_format="GLB", use_selection=True, export_apply=True, export_cameras=False, export_lights=False)
    bpy.ops.render.render(write_still=True)
    (OUTPUT / "sketch-layout.json").write_text(json.dumps(layout(), indent=2) + "\n")
    print(f"PASS: {len(scene.objects)} objects; saved sketch-home.blend/png/glb and sketch-layout.json")


if __name__ == "__main__":
    check_layout()
    if not {"--check-layout", "--check"}.intersection(sys.argv):
        build()
