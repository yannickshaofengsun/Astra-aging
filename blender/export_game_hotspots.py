"""Project fictional game prop markers through the preserved render cameras.

.runtime/blender/Blender.app/Contents/MacOS/Blender --background \
    --python blender/export_game_hotspots.py

The invitation and tote are fictional game props, not actual belongings.
Scene files and source photos are never modified. Coordinates use the top-left
of each complete rendered image; overlays must match the contained image bounds.
"""

import json
from pathlib import Path

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


ASSETS = Path(__file__).resolve().parents[1] / "assets"
# Preserved scene coordinates. The sketch positions correspond to normalized
# sketch coordinates (72, 28), (25, 44), and (76, 18.5), with no physical scale.
# The last point sits inside Living 1 beside Outside; it is not a real entrance.
POINTS = {
    "demo": ("home.blend", [
        ("invitation", "Living room", (-1.55, -1.80, 0.08)),
        ("bag", "Bedroom", (-1.55, 2.35, 0.08)),
        ("entrance", "Entrance", (2.50, -1.50, 0.08)),
    ]),
    "sketch": ("sketch-home.blend", [
        ("invitation", "Living 1", (2.20, -0.10, 0.08)),
        ("bag", "R1", (-2.50, 1.50, 0.08)),
        ("entrance", "Departure point (illustrative)", (2.60, -1.05, 0.08)),
    ]),
}


def export():
    result = {}
    for mode, (filename, points) in POINTS.items():
        bpy.ops.wm.open_mainfile(filepath=str(ASSETS / filename))
        scene = bpy.context.scene
        camera = scene.camera
        assert camera and camera.data.type == "ORTHO", "Visibility check assumes the saved orthographic cameras"
        direction = camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
        depsgraph = bpy.context.evaluated_depsgraph_get()
        result[mode] = []
        for id_, label, coordinates in points:
            point = Vector(coordinates)
            position = world_to_camera_view(scene, camera, point)
            assert position.z > 0 and 0 < position.x < 1 and 0 < position.y < 1, (mode, id_, position)
            # An orthographic ray through each anchor must reach it before
            # hitting furniture or a wall. This checks marker visibility only.
            origin = point - direction * 50
            hit, location, _, _, obj, _ = scene.ray_cast(depsgraph, origin, direction, distance=51)
            assert not hit or (location - origin).length >= 49.98, f"{mode}/{id_} hidden by {obj.name}"
            marker = {"id": id_, "label": label, "x": round(position.x, 6), "y": round(1 - position.y, 6)}
            result[mode].append(marker)
            width, height = scene.render.resolution_x, scene.render.resolution_y
            print(f"{mode}/{id_}: world={coordinates}, image=({marker['x']:.6f}, {marker['y']:.6f}), pixels=({round(marker['x'] * width)}, {round(marker['y'] * height)})")
        assert [marker["id"] for marker in result[mode]] == ["invitation", "bag", "entrance"]
    (ASSETS / "game-hotspots.json").write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: six visible in-frame fictional game anchors; preserved scenes were opened without saving")


if __name__ == "__main__":
    export()
