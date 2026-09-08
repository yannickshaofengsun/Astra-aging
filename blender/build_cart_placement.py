"""Place an illustrative IKEA NISSAFORS cart in a copy of the sketch home.

.runtime/blender/Blender.app/Contents/MacOS/Blender --background \
    --python blender/build_cart_placement.py

Product overall dimensions are sourced facts. Its displayed size and location
in the unmeasured house are authored illustration, never a physical fit check.
The model is a simplified visual reconstruction, not manufacturer CAD.
"""

import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


ASSETS = Path(__file__).resolve().parents[1] / "assets"
PREFIX = "IKEA NISSAFORS "
SOURCE_URL = "https://www.ikea.com/us/en/p/nissafors-utility-cart-black-20399777/"
SOURCE_DATE = "2026-09-08"
LENGTH, WIDTH, HEIGHT = .504825, .29845, .828675
DISPLAY_SCALE = .85  # Arbitrary scene units per product metre; house has no scale.
POSITION = (-2.86, 1.14, .0425)


def bounds(objects):
    corners = [obj.matrix_world @ Vector(point) for obj in objects for point in obj.bound_box]
    return tuple(min(p[i] for p in corners) for i in range(3)), tuple(max(p[i] for p in corners) for i in range(3))


def build():
    originals = [ASSETS / name for stem in ("home", "sketch-home", "sketch-adapted")
                 for suffix in ("blend", "png", "glb")
                 if (ASSETS / (name := f"{stem}.{suffix}")).exists()]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in originals}
    bpy.ops.wm.open_mainfile(filepath=str(ASSETS / "sketch-home.blend"))
    scene = bpy.context.scene
    assert scene.unit_settings.system == "NONE", "The source house must stay unmeasured"
    original_names = set(scene.objects.keys())
    original_transforms = {obj.name: tuple(v for row in obj.matrix_world for v in row) for obj in scene.objects}
    framing = (scene.camera.data.ortho_scale, scene.render.resolution_x,
               scene.render.resolution_y, scene.render.resolution_percentage)
    assert framing[1:] == (1800, 1100, 100)
    assert not any(name.startswith("Fictional caddy") for name in original_names)

    cart = bpy.data.collections.new("IKEA NISSAFORS 203.997.77 illustrative placement")
    scene.collection.children.link(cart)
    materials = {}
    for name, value, roughness in [("Black powder-coated steel", .008, .44),
                                   ("Black caster rubber", .004, .82),
                                   ("Dark caster hub", .022, .48)]:
        material = bpy.data.materials.new(PREFIX + name)
        material.diffuse_color = (value, value, value, 1)
        material.use_nodes = True
        shader = material.node_tree.nodes.get("Principled BSDF")
        shader.inputs["Base Color"].default_value = (value, value, value, 1)
        shader.inputs["Roughness"].default_value = roughness
        materials[name] = material

    def world(point):
        return tuple(POSITION[i] + point[i] * DISPLAY_SCALE for i in range(3))

    def finish(obj, name, material="Black powder-coated steel"):
        obj.name = PREFIX + name
        for collection in list(obj.users_collection):
            collection.objects.unlink(obj)
        cart.objects.link(obj)
        obj.data.materials.append(materials[material])
        obj["option_id"] = "ikea_nissafors"
        obj["product_sku"] = "20399777"
        obj["room_id"] = "bedroom_upper_left"
        obj["fit"] = "unknown"
        obj["model_provenance"] = "Simplified reconstruction; sourced overall product dimensions; arbitrary display scale in unmeasured house"
        return obj

    def box(name, point, size, bevel=.001):
        bpy.ops.mesh.primitive_cube_add(size=1, location=world(point))
        obj = finish(bpy.context.object, name)
        obj.dimensions = tuple(d * DISPLAY_SCALE for d in size)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        if bevel:
            modifier = obj.modifiers.new("Powder coat edge", "BEVEL")
            modifier.width = min(bevel, min(size) / 4) * DISPLAY_SCALE
            modifier.segments = 2
        return obj

    def cylinder(name, point, radius, depth, material, rotation=(0, 0, 0)):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=radius * DISPLAY_SCALE,
                                          depth=depth * DISPLAY_SCALE,
                                          location=world(point), rotation=rotation)
        obj = finish(bpy.context.object, name, material)
        for face in obj.data.polygons:
            face.use_smooth = True
        return obj

    # Four corner uprights and the two short-end handle bars match NISSAFORS's
    # characteristic open frame. Detail dimensions are authored approximations.
    frame_bottom = .080
    for end, x in [("left", -LENGTH / 2 + .006), ("right", LENGTH / 2 - .006)]:
        for side, y in [("front", -WIDTH / 2 + .009), ("back", WIDTH / 2 - .009)]:
            box(f"{end} {side} frame upright", (x, y, (frame_bottom + HEIGHT) / 2),
                (.012, .018, HEIGHT - frame_bottom), .002)
        box(f"{end} top handle", (x, 0, HEIGHT - .009), (.012, WIDTH, .018), .002)

    # Each shelf is visibly open between levels; the floors use real mesh bars,
    # not painted texture. Perforation spacing and lip heights are illustrative.
    tray_length, tray_width = LENGTH - .024, WIDTH - .018
    for tier, z in enumerate((.145, .428, .711), start=1):
        vertices, faces = [], []

        def add_bar(point, size):
            start = len(vertices)
            vertices.extend(world(tuple(point[i] + delta[i] * size[i] / 2 for i in range(3)))
                            for delta in [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
                                          (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)])
            faces.extend(tuple(start + index for index in face)
                         for face in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                                      (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)])

        for i in range(29):
            add_bar((-tray_length / 2 + .004 + i * (tray_length - .008) / 28, 0, z),
                    (.003, tray_width, .003))
        for i in range(17):
            add_bar((0, -tray_width / 2 + .004 + i * (tray_width - .008) / 16, z),
                    (tray_length, .003, .003))
        mesh = bpy.data.meshes.new(PREFIX + f"tier {tier} perforated steel mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(PREFIX + f"tier {tier} mesh shelf", mesh)
        scene.collection.objects.link(obj)
        finish(obj, f"tier {tier} mesh shelf")
        obj["tier"] = tier
        for side, y in [("front", -tray_width / 2), ("back", tray_width / 2)]:
            box(f"tier {tier} {side} tray lip", (0, y, z + .023),
                (tray_length, .004, .048))
        for end, x in [("left", -tray_length / 2), ("right", tray_length / 2)]:
            box(f"tier {tier} {end} tray lip", (x, 0, z + .023),
                (.004, tray_width, .048))

    for index, (x, y) in enumerate([(x, y) for x in (-LENGTH / 2 + .036, LENGTH / 2 - .036)
                                  for y in (-WIDTH / 2 + .024, WIDTH / 2 - .024)], start=1):
        cylinder(f"caster {index} wheel", (x, y, .028), .028, .022,
                 "Black caster rubber", (math.pi / 2, 0, 0))
        cylinder(f"caster {index} axle hub", (x, y, .028), .012, .025,
                 "Dark caster hub", (math.pi / 2, 0, 0))
        cylinder(f"caster {index} swivel stem", (x, y, .071), .008, .037,
                 "Black powder-coated steel")
        box(f"caster {index} fork", (x, y, .050), (.014, .031, .035))

    bpy.context.view_layer.update()
    lo, hi = bounds(list(cart.objects))
    display_dimensions = [hi[i] - lo[i] for i in range(3)]
    for actual, expected in zip(display_dimensions, (LENGTH, WIDTH, HEIGHT)):
        assert abs(actual - expected * DISPLAY_SCALE) < 1e-6
    floor_lo, floor_hi = bounds([scene.objects["bedroom_upper_left floor"]])
    assert all(floor_lo[i] < lo[i] < hi[i] < floor_hi[i] for i in (0, 1))
    for name in ("Upper-left queen bed", "Upper-left bedside table"):
        obstacle_lo, obstacle_hi = bounds([scene.objects[name]])
        assert any(hi[i] <= obstacle_lo[i] or lo[i] >= obstacle_hi[i] for i in (0, 1)), name
    assert original_names == set(scene.objects.keys()) - set(cart.objects.keys())
    assert all(original_transforms[obj.name] == tuple(v for row in obj.matrix_world for v in row)
               for obj in scene.objects if obj.name in original_names)
    assert framing == (scene.camera.data.ortho_scale, scene.render.resolution_x,
                       scene.render.resolution_y, scene.render.resolution_percentage)

    caption = "IKEA NISSAFORS black cart beside R1's bed. Illustrative placement only; house scale, fit and clearances are unknown."
    metadata = {
        "option_id": "ikea_nissafors",
        "sku": "20399777", "article_number": "203.997.77",
        "name": "IKEA NISSAFORS utility cart, black", "tiers": 3, "casters": 4,
        "source_url": SOURCE_URL, "source_date": SOURCE_DATE,
        "known_product_dimensions": {
            "inches": {"length": 19.875, "width": 11.75, "height": 32.625},
            "metres": {"length": LENGTH, "width": WIDTH, "height": HEIGHT},
            "source": "IKEA US product measurements; metres converted from listed inches",
        },
        "price": {"amount": 29.99, "currency": "USD", "kind": "regular listed price",
                  "source_date": SOURCE_DATE, "source_url": SOURCE_URL,
                  "tax_delivery_availability": "not checked", "purchase_made": False},
        "conditional_offer_observed": {
            "amount": 19.99, "currency": "USD", "condition": "In-store only; IKEA Family offer",
            "starts": "2026-09-08", "ends": "2026-12-24",
            "availability_and_eligibility_confirmed": False,
        },
        "room_id": "bedroom_upper_left", "room_label": "R1",
        "cart_world_position": list(POSITION), "cart_world_position_anchor": "footprint centre at floor contact",
        "display_scale": {
            "scene_units_per_product_metre": DISPLAY_SCALE, "arbitrary_illustrative": True,
            "house_real_world_scale": None, "scene_unit_system": "NONE",
            "display_dimensions_scene_units": [round(value, 8) for value in display_dimensions],
            "assumption": "Product proportions are preserved but display scale relative to the symbolic house is arbitrary. No physical fit, clearance, reach or navigation is established.",
        },
        "model_provenance": "Authored simplified visual reconstruction; not manufacturer CAD. Overall product dimensions sourced; component details approximate.",
        "fit": "unknown", "clearance": "unknown", "caption": caption,
        "assets": {"blend": "/assets/sketch-cart.blend", "image": "/assets/sketch-cart.png", "glb": "/assets/sketch-cart.glb"},
        "render": {"width": 1800, "height": 1100, "camera_matches_source": True},
        "source_assets_sha256": {path.name: digest for path, digest in hashes.items()},
        "verification": {"cart_mesh_objects": len(cart.objects), "shelf_count": 3, "wheel_count": 4,
                         "display_mesh_inside_R1": True, "display_mesh_overlaps_bed_or_table": False,
                         "physical_fit_checked": False},
    }
    scene["cart_preview"] = caption
    scene["cart_option_id"] = "ikea_nissafors"
    scene["cart_product_sku"] = "20399777"
    scene["cart_display_scale"] = DISPLAY_SCALE
    scene["cart_fit"] = "unknown"
    scene["cart_metadata"] = json.dumps(metadata)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = None
    bpy.context.preferences.filepaths.save_version = 0
    scene.render.filepath = str(ASSETS / "sketch-cart.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(ASSETS / "sketch-cart.blend"))
    for obj in scene.objects:
        if obj.type in {"MESH", "FONT"} and obj.name != "Backdrop":
            obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(ASSETS / "sketch-cart.glb"), export_format="GLB",
                              use_selection=True, export_apply=True, export_cameras=False,
                              export_lights=False, export_extras=True)
    bpy.ops.render.render(write_still=True)
    assert all(hashlib.sha256(path.read_bytes()).hexdigest() == digest for path, digest in hashes.items())
    (ASSETS / "sketch-cart.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(f"PASS: {len(cart.objects)} cart meshes; three mesh shelves, four wheels; source camera/aspect and {len(hashes)} original assets unchanged; physical fit unknown")


if __name__ == "__main__":
    build()
