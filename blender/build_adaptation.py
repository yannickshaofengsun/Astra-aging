"""Add one fictional low bedside caddy to a copy of the current sketch home.

.runtime/blender/Blender.app/Contents/MacOS/Blender --background \
    --python blender/build_adaptation.py

An illustrative storage possibility only. Dimensions, load, fit and reach are
unmeasured; this image makes no safety or accessibility claim. No product,
vendor, price, purchase or confirmed real household change is represented.
"""

import hashlib
from pathlib import Path

import bpy
from mathutils import Vector


ASSETS = Path(__file__).resolve().parents[1] / "assets"


def build():
    originals = [ASSETS / name for name in ("home.blend", "home.png", "home.glb", "sketch-home.blend", "sketch-home.png", "sketch-home.glb")]
    hashes = {p: hashlib.sha256(p.read_bytes()).digest() for p in originals}
    bpy.ops.wm.open_mainfile(filepath=str(ASSETS / "sketch-home.blend"))
    scene = bpy.context.scene
    camera = tuple(value for row in scene.camera.matrix_world for value in row)
    framing = (scene.camera.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
    assert scene.unit_settings.system == "NONE", "The sketch must remain unmeasured"

    def bounds(obj):
        points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        return tuple(min(p[i] for p in points) for i in (0, 1)), tuple(max(p[i] for p in points) for i in (0, 1))

    # Display-space proportions only; normalized sketch centre is (21.4, 40.4).
    x, y = -2.86, 1.14
    caddy_min, caddy_max = (x - .22, y - .17), (x + .22, y + .17)
    floor_min, floor_max = bounds(scene.objects["bedroom_upper_left floor"])
    assert all(floor_min[i] < caddy_min[i] < caddy_max[i] < floor_max[i] for i in (0, 1))
    for name in ("Upper-left queen bed", "Upper-left bedside table"):
        lo, hi = bounds(scene.objects[name])
        assert any(caddy_max[i] <= lo[i] or caddy_min[i] >= hi[i] for i in (0, 1)), f"Caddy overlaps {name}"

    def box(name, location, size, material):
        bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        obj = bpy.context.object
        obj.name = "Fictional caddy " + name
        obj.dimensions = size
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(bpy.data.materials[material])
        bevel = obj.modifiers.new("Soft edges", "BEVEL")
        bevel.width = .006
        bevel.segments = 3
        obj["provenance"] = "Fictional adaptation preview; dimensions, load, fit and reach unmeasured"
        return obj

    box("bottom", (x, y, .13), (.44, .34, .045), "orange")
    box("interior", (x, y, .158), (.39, .29, .012), "linen")
    for dx in (-.2075, .2075):
        box("side", (x + dx, y, .23), (.025, .34, .20), "orange")
    for dy in (-.1575, .1575):
        box("end", (x, y + dy, .21), (.415, .025, .16), "orange")
    box("divider", (x, y, .21), (.025, .29, .14), "orange")
    for dx in (-.17, .17):
        for dy in (-.12, .12):
            box("foot", (x + dx, y + dy, .078), (.04, .04, .055), "wood")

    bpy.context.view_layer.update()
    direction = scene.camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
    anchor = Vector((x, y, .34))
    origin = anchor - direction * 50
    hit, location, _, _, obj, _ = scene.ray_cast(bpy.context.evaluated_depsgraph_get(), origin, direction, distance=51)
    assert not hit or (location - origin).length >= 49.98 or obj.name.startswith("Fictional caddy"), "Caddy is hidden by other furniture"
    assert camera == tuple(value for row in scene.camera.matrix_world for value in row)
    assert framing == (scene.camera.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage)
    scene["adaptation_preview"] = "Fictional low bedside caddy beside R1; storage possibility only. Dimensions, load, fit and reach unmeasured. No safety or accessibility claim."
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.context.preferences.filepaths.save_version = 0
    scene.render.filepath = str(ASSETS / "sketch-adapted.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSETS / "sketch-adapted.blend"))
    bpy.ops.render.render(write_still=True)
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in hashes.items())
    print("PASS: caddy inside R1, no bed/table overlap, visible, identical camera/aspect; six original assets preserved by SHA-256")


if __name__ == "__main__":
    build()
