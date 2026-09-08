"""Author an illustrative meal room, human poses and camera-matched overlays.

.runtime/blender/Blender.app/Contents/MacOS/Blender --background \
    --python blender/build_meal_scene.py

This separate room supports an ordinary fictional routine; its proportions,
paths and timings are authored, not measured from the user's home or a person.
"""

import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ASSETS = Path(__file__).resolve().parents[1] / "assets"
SPRITES = ASSETS / "meal-sprites"
ROOM_SIZE = (1800, 1125)
SPRITE_SIZE = (320, 448)
SPRITE_SCALE = 2.2
ANCHORS = {
    "resident_start": (.8, -1.8, .045), "entry": (-3.4, -2.5, .045),
    "kitchen_entry": (.2, .6, .045), "pantry": (-3.2, 1.65, .045),
    "preparation": (-1.2, 1.65, .045), "table_approach": (1.35, .7, .045),
    "table_seat": (2.25, .7, .045), "sink": (-2.1, 1.65, .045),
}
EDGES = [("resident_start", "kitchen_entry"), ("entry", "kitchen_entry"),
         ("kitchen_entry", "pantry"), ("pantry", "preparation"),
         ("preparation", "kitchen_entry"), ("kitchen_entry", "table_approach"),
         ("table_approach", "table_seat"), ("kitchen_entry", "sink")]
OBSTACLES = {
    "south partition": (-.08, -3.1, .08, 0), "north partition": (-.08, 1.2, .08, 3.1),
    "counter": (-2.55, 2.3, -.45, 3.08), "pantry": (-3.6, 2.3, -2.85, 3.08),
    "table": (1.4, -1.0, 3.1, .1), "reading chair": (2.3, -2.8, 3.5, -1.65),
}
DIRECTIONS = {"south": 0, "east": math.pi / 2, "north": math.pi, "west": math.pi * 1.5}


def check_paths():
    for a, b in EDGES:
        start, end = Vector(ANCHORS[a]), Vector(ANCHORS[b])
        for step in range(501):
            x, y, _ = start.lerp(end, step / 500)
            assert -3.8 <= x <= 3.8 and -2.9 <= y <= 2.9
            for name, (left, bottom, right, top) in OBSTACLES.items():
                distance = math.hypot(max(left - x, 0, x - right), max(bottom - y, 0, y - top))
                assert distance > .20, f"Authored path {a}->{b} intersects {name}"
    print("PASS: all authored route segments clear display furniture/partitions at illustrative radius .20; not real navigation")


def build():
    preserved = {p: hashlib.sha256(p.read_bytes()).digest() for p in ASSETS.iterdir()
                 if p.suffix in {".blend", ".png", ".glb"} and p.stem in {"home", "sketch-home", "sketch-adapted"}}
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.unit_settings.system = "NONE"
    scene["purpose"] = "Illustrative meal-room inset; not measured supplied-sketch geometry, clinical observation or robotics validation"
    palette = {"cream": "F4EFE2", "wood": "B98454", "linen": "FFF8EB", "teal": "2D7370",
               "pale_teal": "B9D0C5", "clay": "BE7D66", "orange": "D89950", "ink": "273E3C",
               "floor": "DEC7A8", "skin": "C38D70", "silver": "C1BBB0", "trousers": "49565A",
               "shoes": "69544A", "helper_skin": "966948", "helper_hair": "3C3731", "food": "CEBA8A"}
    materials = {}
    for name, color in palette.items():
        mat = bpy.data.materials.new("Meal " + name)
        rgb = [int(color[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        mat.diffuse_color = (*rgb, 1)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*rgb, 1)
        bsdf.inputs["Roughness"].default_value = .82
        materials[name] = mat

    def finish(obj, name, material):
        obj.name = name
        obj.data.materials.append(materials[material])
        return obj

    def box(name, location, dimensions, material, bevel=.025):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = finish(bpy.context.object, name, material)
        obj.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if bevel:
            mod = obj.modifiers.new("Soft edges", "BEVEL")
            mod.width = min(bevel, min(dimensions) / 4)
            mod.segments = 3
        return obj

    def sphere(name, location, scale, material):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, location=location)
        obj = finish(bpy.context.object, name, material)
        obj.scale = scale
        for face in obj.data.polygons:
            face.use_smooth = True
        return obj

    def cylinder(name, location, radius, depth, material):
        bpy.ops.mesh.primitive_cylinder_add(vertices=40, radius=radius, depth=depth, location=location)
        return finish(bpy.context.object, name, material)

    box("Meal room base", (0, 0, -.10), (8.2, 6.4, .23), "linen", .06)
    box("Meal wood floor", (0, 0, .025), (8, 6.2, .04), "floor")
    for x in range(-7, 8):
        box("Floor joint", (x * .5, 0, .047), (.008, 6.16, .002), "wood", 0)
    box("Back wall", (0, 3.13, 1.0), (8.2, .16, 2.0), "cream")
    box("Left cutaway wall", (-4.08, 0, .48), (.16, 6.2, .96), "cream")
    box("Kitchen upper partition", (0, 2.15, .5), (.16, 1.9, 1), "cream")
    box("Kitchen lower cutaway partition", (0, -1.55, .07), (.16, 3.1, .14), "cream")
    box("Doorway threshold", (0, .6, .055), (.16, 1.2, .018), "wood")
    box("Pantry cabinet", (-3.225, 2.69, .93), (.75, .78, 1.77), "wood")
    for z in [.42, .90, 1.39]:
        box("Pantry shelf front", (-3.225, 2.275, z), (.66, .08, .055), "linen")
    box("Counter cabinet", (-1.5, 2.69, .46), (2.1, .78, .83), "pale_teal")
    box("Preparation worktop", (-1.5, 2.69, .9), (2.14, .83, .075), "linen")
    box("Sink basin", (-2.10, 2.65, .943), (.53, .43, .018), "ink")
    box("Sink interior", (-2.1, 2.65, .954), (.43, .34, .012), "pale_teal")
    cylinder("Sink tap", (-2.1, 2.94, 1.04), .025, .20, "wood")
    box("Preparation board", (-1.18, 2.59, .957), (.57, .39, .035), "wood")
    box("Small reheating appliance", (-.85, 2.80, 1.13), (.56, .41, .38), "cream")
    box("Appliance window", (-.85, 2.578, 1.13), (.39, .012, .24), "ink")
    box("Kitchen window frame", (-1.65, 3.025, 1.51), (1.75, .05, .68), "wood")
    box("Kitchen window", (-1.65, 2.990, 1.51), (1.62, .022, .56), "pale_teal")
    box("Window divider", (-1.65, 2.973, 1.51), (.04, .02, .57), "linen")
    table_objects = []
    table_objects.append(box("Dining tabletop foreground", (2.25, -.45, .77), (1.7, 1.1, .09), "wood", .055))
    for x in [1.54, 2.96]:
        for y in [-.87, -.03]:
            table_objects.append(box("Dining table leg foreground", (x, y, .39), (.085, .085, .71), "wood"))
    box("Usual chair seat", (2.25, .70, .47), (.52, .48, .085), "teal")
    box("Usual chair back", (2.25, .955, .77), (.52, .07, .59), "teal")
    for x in [2.045, 2.455]:
        for y in [.515, .89]:
            box("Chair leg", (x, y, .26), (.06, .06, .43), "wood")
    box("Reading chair seat", (2.9, -2.20, .35), (1.0, .93, .55), "clay", .10)
    box("Reading chair back", (2.9, -2.61, .72), (1.0, .18, .82), "clay", .08)
    for x in [2.44, 3.36]:
        box("Reading chair arm", (x, -2.18, .57), (.14, .85, .29), "clay", .06)
    cylinder("Plant pot", (3.53, 2.59, .26), .22, .43, "clay")
    for angle in [0, 1.4, 2.8, 4.2, 5.6]:
        leaf = sphere("Plant leaf", (3.53 + .15 * math.cos(angle), 2.59 + .15 * math.sin(angle), .66), (.12, .10, .29), "teal")
        leaf.rotation_euler = (.4 * math.sin(angle), .4 * math.cos(angle), angle)
    box("Reading rug", (2.8, -2.1, .06), (1.9, 1.75, .014), "linen")
    box("Entry mat", (-3.4, -2.5, .06), (.88, .72, .02), "pale_teal")
    room_objects = [obj for obj in scene.objects if obj.type == "MESH"]
    backdrop = box("Meal backdrop", (0, 0, -.30), (200, 200, .12), "cream", 0)

    bpy.ops.object.camera_add(location=(9, -13, 16))
    camera = bpy.context.object
    camera.name = "Meal room camera"
    camera.rotation_euler = (Vector((0, 0, .30)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    rotation = camera.rotation_euler.copy()
    camera.data.type = "ORTHO"
    scene.camera = camera
    for name, location, energy, size in [("Meal soft key", (1, -5, 10), 1400, 8), ("Meal fill", (-6, 2, 7), 900, 5), ("Meal backfill", (5, 5, 7), 1000, 5)]:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy, light.data.size = energy, size
        light.rotation_euler = (Vector((0, 0, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
    scene.world.color = (.5, .5, .5)
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = True
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "AgX"
    bpy.context.preferences.filepaths.save_version = 0
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_perspective = "CAMERA"
                area.spaces.active.shading.color_type = "MATERIAL"
                area.spaces.active.overlay.show_overlays = False

    def project(point):
        p = world_to_camera_view(scene, camera, Vector(point))
        return {"x": round(p.x, 6), "y": round(1 - p.y, 6)}

    def render(path, size):
        scene.render.resolution_x, scene.render.resolution_y = size
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)

    scene.render.resolution_x, scene.render.resolution_y = ROOM_SIZE
    bpy.context.view_layer.update()
    local = [camera.matrix_world.inverted() @ (obj.matrix_world @ Vector(corner)) for obj in room_objects for corner in obj.bound_box]
    lo = [min(point[i] for point in local) for i in (0, 1)]
    hi = [max(point[i] for point in local) for i in (0, 1)]
    camera.location += camera.rotation_euler.to_quaternion() @ Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0))
    camera.data.ortho_scale = max(hi[0] - lo[0], (hi[1] - lo[1]) * ROOM_SIZE[0] / ROOM_SIZE[1]) / .90
    bpy.context.view_layer.update()
    room_frame = camera.data.view_frame(scene=scene)
    room_span = [max(p[i] for p in room_frame) - min(p[i] for p in room_frame) for i in (0, 1)]
    metadata = {
        "label": "Illustrative meal room", "version": 1,
        "background": "/assets/meal-room.png", "foreground": "/assets/meal-foreground.png",
        "width": ROOM_SIZE[0], "height": ROOM_SIZE[1],
        "anchors": {key: {**project(value), "world": list(value)} for key, value in ANCHORS.items()},
        "edges": [list(pair) for pair in EDGES],
        "object_anchors": {key: project(value) for key, value in {"pantry": (-3.225, 2.22, 1.00), "preparation": (-1.18, 2.57, .99), "table_seat": (2.25, -.04, .83), "sink": (-2.10, 2.65, .98)}.items()},
        "directions": {}, "actors": {}, "props": {},
        "limitations": "Separate authored meal-room inset, not measured supplied-sketch geometry. Paths avoid display obstacles only. Actor actions and objects depict server-authorized fictional facts, not observed real eating or physical capability.",
        "foreground_contract": "Layer background, actors/carried props, dining-table foreground, then stationary table/counter props. Authored table paths approach from north/left; seated upper body remains above tabletop. Preserve full image aspect and normalized root pivots.",
    }
    metadata["object_anchors"]["table_approach"] = metadata["object_anchors"]["table_seat"].copy()
    base_projection = project((0, 0, .045))
    for direction, angle in DIRECTIONS.items():
        vector = Vector((math.sin(angle), -math.cos(angle), 0))
        projected = project(vector + Vector((0, 0, .045)))
        metadata["directions"][direction] = {axis: round(projected[axis] - base_projection[axis], 6) for axis in ["x", "y"]}
    metadata["carried_offset"] = {}
    for direction, angle in DIRECTIONS.items():
        offset = Vector((math.sin(angle) * .36, -math.cos(angle) * .36, 1.045))
        projected = project(offset)
        metadata["carried_offset"][direction] = {axis: round(projected[axis] - base_projection[axis], 6) for axis in ["x", "y"]}
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSETS / "meal-room.blend"))
    render(ASSETS / "meal-room.png", ROOM_SIZE)
    scene.render.film_transparent = True
    for obj in room_objects + [backdrop]:
        obj.visible_camera = obj in table_objects
    render(ASSETS / "meal-foreground.png", ROOM_SIZE)
    for obj in room_objects + [backdrop]:
        obj.hide_render = True
        obj.visible_camera = True

    actor_objects = []
    def person(kind, pose, angle):
        nonlocal actor_objects
        for obj in actor_objects:
            bpy.data.objects.remove(obj, do_unlink=True)
        actor_objects = []
        bpy.ops.object.empty_add()
        root = bpy.context.object
        root.name = "Meal human root"
        root.rotation_euler.z = angle
        actor_objects.append(root)
        skin = "skin" if kind == "resident" else "helper_skin"
        shirt = "teal" if kind == "resident" else "clay"
        hair = "silver" if kind == "resident" else "helper_hair"
        seated = pose in {"seated", "eating"}
        drop = .22 if seated else 0
        def part(name, location, scale, material):
            obj = sphere("Meal person " + name, location, scale, material)
            obj.parent = root
            actor_objects.append(obj)
            return obj
        def limb(name, a, b, radius, material):
            a, b = Vector(a), Vector(b)
            obj = part(name, (a + b) / 2, (radius, radius, (a - b).length / 2 + radius * .55), material)
            obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
        part("hips", (0, 0, .81 - drop), (.165, .12, .135), "trousers")
        part("cardigan", (0, -.025 if seated else 0, 1.10 - drop), (.22, .125, .29), shirt)
        shirt_front = box("Meal person shirt front", (0, -.125, 1.12 - drop), (.13, .025, .37), "linen", .012)
        shirt_front.parent = root
        actor_objects.append(shirt_front)
        part("neck", (0, -.012, 1.37 - drop), (.055, .055, .075), skin)
        part("head", (0, -.014, 1.535 - drop), (.125, .117, .158), skin)
        part("hair", (0, .008, 1.643 - drop), (.125, .115, .064), hair)
        for side in [-1, 1]:
            part("temple", (side * .115, .012, 1.561 - drop), (.022, .087, .077), hair)
            part("ear", (side * .128, -.006, 1.525 - drop), (.024, .021, .038), skin)
            part("eye", (side * .044, -.121, 1.559 - drop), (.009, .006, .010), "ink")
        part("nose", (0, -.133, 1.515 - drop), (.027, .032, .035), skin)
        stride = .145 if pose.endswith("a") else -.145 if pose.endswith("b") else 0
        carrying = pose.startswith("carry")
        for side in [-1, 1]:
            hip = (side * .096, 0, .78 - drop)
            knee = (side * .10, -.41 if seated else side * stride * .55, .44)
            ankle = (side * .105, -.45 if seated else side * stride, .105)
            limb("thigh", hip, knee, .085, "trousers")
            limb("shin", knee, ankle, .066, "trousers")
            part("shoe", (ankle[0], ankle[1] - .048, .075), (.079, .13, .065), "shoes")
            shoulder = (side * .20, 0, 1.29 - drop)
            if carrying:
                elbow, wrist = (side * .245, -.13, 1.08), (side * .137, -.36, 1.035)
            elif seated:
                elbow = (side * .22, -.18, .91)
                wrist = (side * .10, -.23, 1.15) if pose == "eating" and side == 1 else (side * .15, -.43, .80)
            else:
                elbow = (side * .245, -side * stride * .55, 1.04)
                wrist = (side * .25, -side * stride, .83)
            limb("upper sleeve", shoulder, elbow, .062, shirt)
            limb("lower sleeve", elbow, wrist, .049, shirt)
            part("hand", wrist, (.047, .043, .061), skin)
            if pose == "eating" and side == 1:
                limb("spoon", wrist, (.08, -.14, 1.24), .007, "wood")
                part("spoon bowl", (.08, -.14, 1.24), (.014, .023, .006), "wood")
        return root

    # Render all poses against the same camera orientation and root pivot.
    SPRITES.mkdir(parents=True, exist_ok=True)
    camera.rotation_euler = rotation
    camera.data.ortho_scale = SPRITE_SCALE
    forward = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    camera.location = Vector((0, 0, .82)) - forward * 20
    scene.render.resolution_x, scene.render.resolution_y = SPRITE_SIZE
    scene.cycles.samples = 12
    bpy.context.view_layer.update()
    pivot = project((0, 0, .045))
    sprite_frame = camera.data.view_frame(scene=scene)
    sprite_span = [max(p[i] for p in sprite_frame) - min(p[i] for p in sprite_frame) for i in (0, 1)]
    sprite_width, sprite_height = [sprite_span[i] / room_span[i] for i in (0, 1)]
    for kind in ["resident", "helper"]:
        poses = {}
        for pose in ["idle", "walk_a", "walk_b", "carry", "carry_walk_a", "carry_walk_b"] + (["seated", "eating"] if kind == "resident" else []):
            poses[pose] = {}
            for direction, angle in ([("south", 0)] if pose in {"seated", "eating"} else DIRECTIONS.items()):
                person(kind, pose, angle)
                filename = f"{kind}-{pose}-{direction}.png"
                render(SPRITES / filename, SPRITE_SIZE)
                poses[pose][direction] = "/assets/meal-sprites/" + filename
        metadata["actors"][kind] = {"width": round(sprite_width, 6), "height": round(sprite_height, 6), "pivot": pivot, "poses": poses}
    for obj in actor_objects:
        bpy.data.objects.remove(obj, do_unlink=True)

    camera.data.ortho_scale = .65
    camera.location = -forward * 20
    scene.render.resolution_x, scene.render.resolution_y = (256, 192)
    bpy.context.view_layer.update()
    dish_pivot = project((0, 0, 0))
    dish_frame = camera.data.view_frame(scene=scene)
    dish_span = [max(p[i] for p in dish_frame) - min(p[i] for p in dish_frame) for i in (0, 1)]
    cylinder("Meal dish", (0, 0, .022), .165, .035, "linen")
    cylinder("Meal dish rim", (0, 0, .04), .143, .018, "linen")
    food = sphere("Chosen food symbol", (0, 0, .069), (.117, .107, .032), "food")
    for state in ["full", "used"]:
        food.hide_render = state == "used"
        filename = "meal-dish-" + state + ".png"
        render(ASSETS / filename, (256, 192))
        metadata["props"][state] = {"image": "/assets/" + filename, "width": round(dish_span[0] / room_span[0], 6), "height": round(dish_span[1] / room_span[1], 6), "pivot": dish_pivot}
    assert all(0 < point["x"] < 1 and 0 < point["y"] < 1 for point in metadata["anchors"].values())
    assert all(hashlib.sha256(path.read_bytes()).digest() == digest for path, digest in preserved.items())
    (ASSETS / "meal-scene.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("PASS: meal background, foreground, 50 human poses, 2 dish states and authored camera metadata; original assets unchanged")


if __name__ == "__main__":
    check_paths()
    if "--check-paths" not in sys.argv:
        build()
