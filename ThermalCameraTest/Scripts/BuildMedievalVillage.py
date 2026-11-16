"""
Team 3 - Medieval thermal test village (built from Blender-made meshes, no Fab download)

Imports the village meshes made by SourceArt/MedievalVillage/build_village_assets.py
(timber-frame and stone houses, a church with a bell tower, terrain with hills, a lake
and mountains, a winding road, market stalls, trees, carts, fences ...) and builds the
map /Game/Maps/MedievalVillage from layout.json:

  * every building / prop carries a Heat_N tag (team 0-6 scale) -> ThermoForge source
  * window glass and water are drawn as cold surfaces in the thermal image
  * one house is burning (fire in the windows, door and roof, smoke, charred walls)
    with a survivor trapped under rubble in front of it and rescuers nearby
  * villagers at the market, the campfire, the church and the tavern (Renderpeople
    scanned people if that pack is in the project, otherwise Epic's mannequin)
  * a car with a hot engine, a dog, a horse and cows (the Fab animal pack is used
    automatically if it is in the project)
  * warm chimneys on every house
  * BP_ThermalCamera on Obeth's CameraRotator (I / P rotate it) looking over the village

Run in the editor console:  py "<project>/Scripts/BuildMedievalVillage.py"
Safe to re-run: meshes are re-imported only when the FBX files change.
"""

import json
import math
import os
import random
import sys

import unreal

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# Reuse the helpers (materials, fire, people, hot spots, car ...) from the first village.
import importlib
import BuildThermalVillage as bv  # noqa: E402  (importing it does NOT build the old village: see the guard there)
importlib.reload(bv)

PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
SRC_DIR = os.path.join(os.path.dirname(PROJECT_DIR), "SourceArt", "MedievalVillage")
MESH_DIR = "/Game/ThermalVillage/Medieval/Meshes"
LEVEL = "/Game/Maps/MedievalVillage"

bv.FOLDER = "Medieval"
bv.LEVEL = LEVEL
bv.CENTER = unreal.Vector(0, 0, 0)

eas, les, EAL = bv.eas, bv.les, bv.EAL
random.seed(7)

# extra procedural surfaces used by the Blender meshes
bv.SURFACES.update({
    "Planks":      ((0.40, 0.27, 0.15), (0.24, 0.15, 0.08), 2, 60, 0.85, 0),
    "StoneDark":   ((0.30, 0.29, 0.27), (0.18, 0.17, 0.16), 1, 70, 0.9, 0),
    "RoofShingle": ((0.27, 0.24, 0.22), (0.14, 0.12, 0.11), 3, 50, 0.85, 0),
    "Thatch":      ((0.62, 0.50, 0.26), (0.40, 0.31, 0.15), 2, 25, 0.95, 0),
    "Rock":        ((0.42, 0.41, 0.39), (0.25, 0.24, 0.23), 0, 120, 0.9, 0),
    "LeavesDark":  ((0.09, 0.22, 0.06), (0.04, 0.12, 0.03), 0, 60, 0.9, 0),
    "ClothCream":  ((0.84, 0.80, 0.68), (0.66, 0.62, 0.52), 0, 30, 0.9, 0),
})

# thermal stencil for cold surfaces that are not heat sources (glass reflects the cold sky)
COLD_STENCIL = 12          # ~ ambient - 6 C with the camera's default range
WATER_STENCIL = 8          # ~ ambient - 7 C


def log(msg):
    unreal.log("[Medieval] " + str(msg))


# ===========================================================================
# Coordinates: Blender meters (right-handed) -> Unreal centimeters (left-handed)
# ===========================================================================
FLIP = -1.0  # Y sign; verified against the church mesh after import


def to_ue(x, y, z=0.0):
    return (x * 100.0, FLIP * y * 100.0, z * 100.0)


def yaw_ue(yaw):
    return yaw if FLIP > 0 else -yaw


class Heights:
    def __init__(self, path):
        d = json.load(open(path))
        self.o, self.s, self.n, self.g = d["origin"], d["step"], d["n"], d["rows_y_cols_x"]

    def __call__(self, x, y):
        fx = min(max((x - self.o) / self.s, 0), self.n - 1.001)
        fy = min(max((y - self.o) / self.s, 0), self.n - 1.001)
        i, j = int(fx), int(fy)
        tx, ty = fx - i, fy - j
        g = self.g
        a = g[j][i] * (1 - tx) + g[j][i + 1] * tx
        b = g[j + 1][i] * (1 - tx) + g[j + 1][i + 1] * tx
        return max(a * (1 - ty) + b * ty, 0.0)


# ===========================================================================
# Import the Blender meshes
# ===========================================================================
def import_meshes(names):
    """Import <name>.fbx for every name (only when the FBX is newer than the asset)."""
    EAL.make_directory(MESH_DIR)
    stamp_path = os.path.join(PROJECT_DIR, "Saved", "MedievalImport.json")
    stamps = json.load(open(stamp_path)) if os.path.exists(stamp_path) else {}
    tasks = []
    for n in names:
        fbx = os.path.join(SRC_DIR, n + ".fbx")
        mt = os.path.getmtime(fbx)
        if EAL.does_asset_exist(MESH_DIR + "/" + n) and stamps.get(n) == mt:
            continue
        t = unreal.AssetImportTask()
        t.filename = fbx
        t.destination_path = MESH_DIR
        t.destination_name = n
        t.automated = True
        t.replace_existing = True
        t.save = True
        ui = unreal.FbxImportUI()
        ui.import_mesh = True
        ui.import_as_skeletal = False
        ui.import_materials = False
        ui.import_textures = False
        ui.import_animations = False
        for prop, val in (("combine_meshes", True), ("auto_generate_collision", False),
                          ("generate_lightmap_u_vs", False)):
            try:
                ui.static_mesh_import_data.set_editor_property(prop, val)
            except Exception:
                pass
        t.options = ui
        tasks.append((n, mt, t))
    if tasks:
        log("importing %d meshes ..." % len(tasks))
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t for _, _, t in tasks])
        for n, mt, t in tasks:
            stamps[n] = mt
        json.dump(stamps, open(stamp_path, "w"))
    meshes = {}
    for n in names:
        m = find_mesh(n)
        if m is None:
            unreal.log_warning("[Medieval] mesh %s did not import" % n)
            continue
        meshes[n] = m
    return meshes


def find_mesh(n):
    for cand in (MESH_DIR + "/" + n, MESH_DIR + "/SM_" + n, MESH_DIR + "/" + n + "/" + n):
        if EAL.does_asset_exist(cand):
            a = unreal.load_asset(cand)
            if isinstance(a, unreal.StaticMesh):
                return a
    # Interchange may name it differently: search the folder
    for p in EAL.list_assets(MESH_DIR, recursive=True, include_folder=False):
        base = p.split(".")[-1]
        if base in (n, "SM_" + n):
            a = unreal.load_asset(p)
            if isinstance(a, unreal.StaticMesh):
                return a
    return None


def _slot_key(name):
    s = str(name)
    for pre in ("MI_", "M_"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.split(".")[0]
    while s and (s[-1].isdigit() or s[-1] == "_"):
        s = s[:-1]
    return s


def assign_materials(mesh):
    """Give each material slot the procedural village material with the same name."""
    changed = False
    mats = mesh.get_editor_property("static_materials")
    for i, sm in enumerate(mats):
        key = _slot_key(sm.get_editor_property("material_slot_name"))
        if key not in bv.MI:
            mi_now = sm.get_editor_property("material_interface")
            key = _slot_key(mi_now.get_name()) if mi_now else key
        if key in bv.MI:
            if sm.get_editor_property("material_interface") != bv.MI[key]:
                mesh.set_material(i, bv.MI[key])
                changed = True
        else:
            unreal.log_warning("[Medieval] %s slot %d (%s): no material" % (mesh.get_name(), i, key))
    if changed:
        EAL.save_loaded_asset(mesh)


def slot_index(mesh, wanted):
    for i, sm in enumerate(mesh.get_editor_property("static_materials")):
        if _slot_key(sm.get_editor_property("material_slot_name")) == wanted:
            return i
        mi = sm.get_editor_property("material_interface")
        if mi and _slot_key(mi.get_name()) == wanted:
            return i
    return -1


def detect_flip(meshes):
    """The church tower is at -Y in Blender; find where it ended up."""
    global FLIP
    m = meshes.get("Church")
    if m is None:
        return
    b = m.get_bounding_box()
    FLIP = -1.0 if abs(b.max.y) > abs(b.min.y) else 1.0
    log("church bounds %s .. %s  -> Y flip %s, height %.0f cm" % (b.min, b.max, FLIP, b.max.z))


# ===========================================================================
# Placing things
# ===========================================================================
def place(item, meshes, H):
    name = item["asset"]
    m = meshes.get(name)
    if m is None:
        return None
    loc = to_ue(item["x"], item["y"], item["z"])
    a = eas.spawn_actor_from_object(m, unreal.Vector(*loc), unreal.Rotator(roll=0, pitch=0, yaw=yaw_ue(item["yaw"])))
    a.set_actor_label(item["label"])
    group = {"Building": "Buildings", "Glass": "Buildings", "Vegetation": "Nature", "Ground": "Ground",
             "Water": "Ground"}.get(item["type"], "Props")
    a.set_folder_path(unreal.Name("%s/%s" % (bv.FOLDER, group)))
    smc = a.static_mesh_component
    if item["type"] in ("Glass", "Water"):
        # cold surface: no heat source, fixed cold value in the thermal image
        a.set_editor_property("tags", [unreal.Name("VillageBuild"), unreal.Name("ThermalType_" + item["type"])])
        smc.set_editor_property("render_custom_depth", True)
        smc.set_editor_property("custom_depth_stencil_value", WATER_STENCIL if item["type"] == "Water" else COLD_STENCIL)
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        if name.endswith("_Glass"):
            smc.set_editor_property("cast_shadow", False)
    else:
        ttype = {"Vegetation": "Ground", "Debris": "Custom"}.get(item["type"], item["type"])
        a.set_editor_property("tags", bv.tag_list(item["heat"], ttype, item.get("tags", [])))
    if item["type"] in ("Ground",) or name.startswith(("Tree", "Bush")):
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    bv._count["actors"] += 1
    return a


def local_to_world(item, lx, ly, lz=0.0):
    """Blender local offset of an asset -> Blender world (meters)."""
    r = math.radians(item["yaw"])
    return (item["x"] + lx * math.cos(r) - ly * math.sin(r),
            item["y"] + lx * math.sin(r) + ly * math.cos(r),
            item["z"] + lz)


def front_dir(item):
    r = math.radians(item["yaw"])
    return (math.sin(r), -math.cos(r))   # local -Y rotated


def facing_yaw_ue(dx, dy):
    """Unreal yaw (deg) of a direction given in Blender XY."""
    return math.degrees(math.atan2(FLIP * dy, dx))


# ===========================================================================
# Optional Fab packs (people / animals) - used automatically when present
# ===========================================================================
def find_skeletal(keywords, exclude=("Tutorial", "Mannequin_Simple")):
    out = []
    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    flt = unreal.ARFilter(class_paths=[unreal.TopLevelAssetPath("/Script/Engine", "SkeletalMesh")],
                          package_paths=["/Game"], recursive_paths=True)
    for ad in ar.get_assets(flt):
        p = str(ad.package_name)
        low = p.lower()
        if any(e.lower() in low for e in exclude):
            continue
        if any(k in low for k in keywords):
            out.append(p)
    return sorted(out)


SCANNED_PEOPLE = []
ANIMALS = {}


def discover_packs():
    global SCANNED_PEOPLE
    SCANNED_PEOPLE = find_skeletal(("renderpeople", "/rp_", "scanned"))
    for kind, keys in (("Dog", ("dog", "wolf", "husky", "shepherd")), ("Cow", ("cow", "bull", "cattle")),
                       ("Horse", ("horse",)), ("Deer", ("deer", "stag")), ("Sheep", ("sheep",)),
                       ("Pig", ("pig", "boar"))):
        hits = find_skeletal(keys)
        if hits:
            ANIMALS[kind] = hits[0]
    log("scanned people found: %d, animals found: %s" % (len(SCANNED_PEOPLE), list(ANIMALS)))


def person(label, bx, by, H, face_dx, face_dy, cloth="ClothBlue", lying=False):
    """Villager standing on the terrain at Blender (bx, by), facing direction (face_dx, face_dy)."""
    z = H(bx, by)
    loc = to_ue(bx, by, z)
    face = facing_yaw_ue(face_dx, face_dy)
    if SCANNED_PEOPLE:
        sk = unreal.load_asset(random.choice(SCANNED_PEOPLE))
        rot = unreal.Rotator(roll=0, pitch=(-90 if lying else 0), yaw=face - 90)
        a = eas.spawn_actor_from_object(sk, unreal.Vector(loc[0], loc[1], loc[2] + (18 if lying else 0)), rot)
        a.set_actor_label(label)
        a.set_folder_path(unreal.Name("%s/People" % bv.FOLDER))
        a.set_editor_property("tags", bv.tag_list(4, "Human"))
        comp = a.get_component_by_class(unreal.SkeletalMeshComponent)
        anim = unreal.load_asset(bv.ANIM_IDLE)
        if anim and not lying:
            try:
                if anim.get_editor_property("skeleton") == sk.get_editor_property("skeleton"):
                    comp.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                    comp.override_animation_data(anim, True, True, random.uniform(0, 2), random.uniform(0.85, 1.15))
            except Exception:
                pass
        try:
            head = comp.get_socket_location("head")
            bv.hotspot(label + "_FaceHeat", (head.x, head.y, head.z), 6, 22, 1.4, attach=comp, socket="head",
                       folder="People")
        except Exception:
            pass
        bv._count["people"] += 1
        return a, comp
    return bv.person(label, (loc[0], loc[1], loc[2] + (18 if lying else 0)), face, cloth, lying=lying)


def animal(kind, label, bx, by, H, yaw_deg, size, mat):
    z = H(bx, by)
    loc = to_ue(bx, by, z)
    if kind in ANIMALS:
        a = eas.spawn_actor_from_object(unreal.load_asset(ANIMALS[kind]), unreal.Vector(*loc),
                                        unreal.Rotator(roll=0, pitch=0, yaw=yaw_deg))
        a.set_actor_label(label)
        a.set_folder_path(unreal.Name("%s/Animals" % bv.FOLDER))
        a.set_editor_property("tags", bv.tag_list(3, "Animal"))
        bv.hotspot(label + "_BodyHeat", (loc[0], loc[1], loc[2] + size[2] * 1.4), 4, max(size[0] * 0.5, 30), 1.5,
                   attach=a, folder="Animals")
        return a
    return bv.quadruped(label, loc, yaw_deg, size, mat, 3, "Animal")


# ===========================================================================
# Environment
# ===========================================================================
def prepare_level():
    if EAL.does_asset_exist(LEVEL):
        les.load_level(LEVEL)
    else:
        EAL.make_directory("/Game/Maps")
        if not les.new_level(LEVEL):
            raise RuntimeError("could not create " + LEVEL)
        log("created new map " + LEVEL)
    removed = 0
    for a in eas.get_all_level_actors():
        if a.actor_has_tag("VillageBuild") or str(a.get_folder_path()).startswith(bv.FOLDER):
            eas.destroy_actor(a)
            removed += 1
    log("cleared %d actors from the previous build" % removed)


def build_environment():
    sun = bv.env_actor(unreal.DirectionalLight, "Sun", (0, 0, 3000), (0, -32, 145))
    try:
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("atmosphere_sun_light", True)
        sc.set_editor_property("intensity", 8.0)
    except Exception as e:
        unreal.log_warning("[Medieval] sun: %s" % e)
    bv.env_actor(unreal.SkyAtmosphere, "SkyAtmosphere")
    sky = bv.env_actor(unreal.SkyLight, "SkyLight", (0, 0, 1500))
    try:
        slc = sky.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("real_time_capture", True)
        slc.set_mobility(unreal.ComponentMobility.MOVABLE)
    except Exception as e:
        unreal.log_warning("[Medieval] skylight: %s" % e)
    fog = bv.env_actor(unreal.ExponentialHeightFog, "HeightFog", (0, 0, -200))
    try:
        fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
        fc.set_editor_property("fog_density", 0.008)
        fc.set_editor_property("fog_height_falloff", 0.05)
    except Exception:
        pass
    if hasattr(unreal, "VolumetricCloud"):
        bv.env_actor(unreal.VolumetricCloud, "Clouds")
    for a in eas.get_all_level_actors():
        if a.get_class().get_name() == "PlayerStart":
            eas.destroy_actor(a)
    bv.env_actor(unreal.PlayerStart, "PlayerStart", to_ue(-10, -60, 3), (0, -10, facing_yaw_ue(0.2, 1)))


def place_camera():
    """Drone view from the south edge of the village, 30 m up, on Obeth's I/P rotator."""
    bp = unreal.load_asset(bv.CAMERA_BP)
    if bp is None:
        unreal.log_warning("[Medieval] BP_ThermalCamera not found")
        return
    target = to_ue(5, -62, 28)
    yaw = facing_yaw_ue(0, 1)
    cam = bv.env_actor(bp.generated_class(), "ThermalCamera_Drone", target, (0, -24, yaw))
    cam.set_folder_path(unreal.Name(bv.FOLDER + "/Camera"))
    rot_bp = unreal.load_asset(bv.ROTATOR_BP)
    if rot_bp is not None:
        rotator = bv.env_actor(rot_bp.generated_class(), "CameraRotator_Drone", target, (0, 0, yaw))
        rotator.set_folder_path(unreal.Name(bv.FOLDER + "/Camera"))
        try:
            rotator.get_component_by_class(unreal.StaticMeshComponent).set_mobility(unreal.ComponentMobility.MOVABLE)
        except Exception as e:
            unreal.log_warning("[Medieval] rotator mobility: %s" % e)
        try:
            rotator.set_actor_hidden_in_game(True)
            rotator.set_actor_enable_collision(False)
        except Exception:
            pass
        rule = unreal.AttachmentRule.KEEP_WORLD
        cam.attach_to_actor(rotator, unreal.Name(""), rule, rule, rule, False)
        log("thermal camera attached to CameraRotator (I / P rotate it)")


def resize_thermo_volume():
    if not hasattr(unreal, "ThermoForgeVolume"):
        return
    vol = next((a for a in eas.get_all_level_actors() if a.get_class().get_name() == "ThermoForgeVolume"), None)
    if vol is None:
        vol = eas.spawn_actor_from_class(unreal.ThermoForgeVolume, unreal.Vector(0, 0, 800), unreal.Rotator())
        vol.set_actor_label("ThermoForgeVolume_Village")
        vol.set_folder_path(unreal.Name("ThermoForge"))
    vol.set_actor_location(unreal.Vector(0, 0, 800), False, False)
    vol.set_editor_property("box_extent", unreal.Vector(11000, 10000, 2000))


# ===========================================================================
# The scenario on top of the village
# ===========================================================================
def chimneys(houses, manifest):
    for it in houses:
        meta = manifest.get(it["asset"], {})
        if "chimney_top" not in meta:
            continue
        cx, cy, cz = meta["chimney_top"]
        wx, wy, wz = local_to_world(it, cx, cy, cz)
        burning = "Burning" in it["label"]
        bv.hotspot(it["label"] + "_ChimneyHeat", to_ue(wx, wy, wz - 0.3), 45 if burning else 22, 70, 1.4,
                   folder="HeatSpots")


def burning_house(it, actor, mesh, manifest, H):
    meta = manifest[it["asset"]]
    # scorched walls and roof
    smc = actor.static_mesh_component
    for slot in ("Plaster", "PlasterB", "RoofShingle", "RoofTile", "Thatch", "Planks", "Door"):
        i = slot_index(mesh, slot)
        if i >= 0:
            smc.set_material(i, bv.MI["Charred"])
    fdx, fdy = front_dir(it)
    fires = 0
    for k, (wx, wy, wz) in enumerate(meta["windows"]):
        gx, gy, gz = local_to_world(it, wx, wy - 0.15, wz - 0.55)
        bv.fire("%s_FireWin%d" % (it["label"], k), to_ue(gx, gy, gz), height=130, width=75, intensity_c=170,
                heat_radius=160, smoke=False, folder="BurningHouse", light_intensity=5000)
        fires += 1
    dx, dy, dz = meta["doors"][0]
    gx, gy, gz = local_to_world(it, dx, dy - 0.3, dz)
    bv.fire(it["label"] + "_FireDoor", to_ue(gx, gy, gz), height=230, width=110, intensity_c=210, heat_radius=240,
            smoke=False, folder="BurningHouse", light_intensity=15000)
    # the roof is burning through
    for k, lx in enumerate((-2.0, 1.2)):
        gx, gy, gz = local_to_world(it, lx, 0.6 * (k - 0.5), meta["ridge"] - 1.6)
        bv.fire("%s_FireRoof%d" % (it["label"], k), to_ue(gx, gy, gz), height=420, width=260, intensity_c=260,
                heat_radius=420, smoke=True, folder="BurningHouse", light_intensity=30000)
    # interior heat glows through the walls
    gx, gy, gz = local_to_world(it, 0, 0, 2.5)
    bv.hotspot(it["label"] + "_InteriorHeat", to_ue(gx, gy, gz), 45, 520, 1.1, folder="BurningHouse")

    # collapsed rubble in front, a trapped survivor and rescuers
    hd = meta["size"][1] / 2
    fx, fy = it["x"] + fdx * (hd + 3.2), it["y"] + fdy * (hd + 3.2)
    for i in range(12):
        rx, ry = fx + random.uniform(-3.5, 3.5), fy + random.uniform(-1.2, 1.2)
        l = to_ue(rx, ry, H(rx, ry) + random.uniform(0.15, 0.45))
        bv.box("Rubble%d" % i, l, (random.uniform(60, 150), random.uniform(40, 110), random.uniform(25, 60)),
               rot=(random.uniform(-25, 25), random.uniform(-25, 25), random.uniform(0, 360)),
               mat=random.choice(["Charred", "Stone", "Planks"]), heat=1, ttype="Debris", folder="Rubble")
    sx, sy = fx - 1.2, fy
    person("Survivor_Trapped", sx, sy, H, fdx, fdy, "ClothGray", lying=True)
    for i in range(4):
        l = to_ue(sx + 0.7 + i * 0.35, sy + random.uniform(-0.25, 0.25), H(sx, sy) + 0.45 + i * 0.08)
        bv.box("Beam%d" % i, l, (260, 22, 22), rot=(0, random.uniform(-10, 10), facing_yaw_ue(fdx, fdy) + 75 + i * 9),
               mat="Charred", heat=2, ttype="Debris", folder="Rubble")
    for k, (ox, oy) in enumerate(((3.5, 2.0), (5.0, 3.2), (-4.0, 2.6))):
        px, py = fx + ox * fdy + oy * fdx, fy - ox * fdx + oy * fdy
        person("Rescuer%d" % k, px, py, H, sx - px, sy - py, ["ClothRed", "ClothBlue", "ClothBrown"][k])
    log("burning house: %s (%d window fires)" % (it["label"], fires))


def scenario(layout, manifest, actors, meshes, H):
    houses = [it for it in layout if it["asset"].startswith("House_") and not it["asset"].endswith("_Glass")]
    chimneys(houses, manifest)
    for it in houses:
        if "Burning" in it["label"]:
            burning_house(it, actors[it["label"]], meshes[it["asset"]], manifest, H)

    # campfire on the plaza with villagers around it
    cfx, cfy = 4.5, 5.0
    for i in range(8):
        a = i * 45
        bv.box("FireRing%d" % i, to_ue(cfx + 0.7 * math.cos(math.radians(a)), cfy + 0.7 * math.sin(math.radians(a)), 0.12),
               (30, 25, 22), a, "Stone", 2, "Debris", "Campfire")
    for i, a in enumerate((0, 60, 120)):
        bv.spawn_mesh("CampfireLog%d" % i, bv.CYL, to_ue(cfx, cfy, 0.14), (0.18, 0.18, 1.1), (0, 90, a), "Charred", 5,
                      "Fire", "Campfire")
    bv.fire("Campfire", to_ue(cfx, cfy, 0.1), height=140, width=80, intensity_c=170, heat_radius=180, smoke=True,
            folder="Campfire", light_intensity=6000)
    clothes = ["ClothRed", "ClothBlue", "ClothGreen", "ClothBrown", "ClothGray", "ClothCream"]
    for i, a in enumerate((20, 110, 200, 290)):
        px, py = cfx + 2.3 * math.cos(math.radians(a)), cfy + 2.3 * math.sin(math.radians(a))
        person("Villager_Fire%d" % i, px, py, H, cfx - px, cfy - py, clothes[i])

    # market shoppers and sellers
    for i, (px, py, fx, fy) in enumerate(((5.0, -4.0, 6, -6), (8.0, -0.2, 9, 2), (-6.5, -4.6, -8, -7),
                                         (-9.0, -9.0, -8, -7), (10.8, 3.8, 9, 2))):
        person("Villager_Market%d" % i, px, py, H, fx - px, fy - py, clothes[i % 6])

    # people at the church door, along the road, at the tavern
    church = next((it for it in layout if it["asset"] == "Church"), None)
    if church:
        dx, dy, _ = manifest["Church"]["doors"][0]
        gx, gy, _ = local_to_world(church, dx, dy - 7.0, 0)
        person("Villager_Church0", gx - 0.6, gy, H, 1, 0, "ClothCream")
        person("Villager_Church1", gx + 0.6, gy, H, -1, 0, "ClothBlue")
    for i, (px, py, fx, fy) in enumerate(((-30, -5.5, 1, 0.2), (24, 5.5, -1, -0.2), (-52, -13, 1, 0.4))):
        person("Villager_Road%d" % i, px, py, H, fx, fy, clothes[(i + 2) % 6])
    tav = next((it for it in houses if it["asset"] == "House_Tavern"), None)
    if tav:
        dx, dy, _ = manifest["House_Tavern"]["doors"][0]
        fdx, fdy = front_dir(tav)
        gx, gy, _ = local_to_world(tav, dx, dy, 0)
        person("Villager_Tavern0", gx + fdx * 2.0 - fdy * 0.5, gy + fdy * 2.0 + fdx * 0.5, H, -fdx, -fdy, "ClothBrown")
        person("Villager_Tavern1", gx + fdx * 2.6 + fdy * 0.6, gy + fdy * 2.6 - fdx * 0.6, H, -fdx, -fdy, "ClothGreen")

    # the stick carrier by the well: warm where the hand grips the stick, cold at both ends
    p, comp = person("Villager_Stick", -2.0, 1.0, H, -1, 0.3, "ClothGreen")
    try:
        hand = comp.get_socket_location("hand_r")
        stick = bv.spawn_mesh("WalkingStick", bv.CYL, (hand.x, hand.y, hand.z - 25), (0.05, 0.05, 1.5), (0, 0, 0),
                              "Timber", 1, "Debris", "People", collision=False)
        rule = unreal.AttachmentRule.KEEP_WORLD
        stick.attach_to_component(comp, unreal.Name("hand_r"), rule, rule, rule, False)
        bv.hotspot("WalkingStick_GripHeat", (hand.x, hand.y, hand.z), 12, 35, 1.3, attach=stick, folder="People",
                   start_full=False, warm_up=5.0, cool_down=30.0)
    except Exception as e:
        unreal.log_warning("[Medieval] stick skipped: %s" % e)

    # a car that was just driven in (hot engine, exhaust, radiator)
    cx, cy = 33.0, 7.0
    l = to_ue(cx, cy, H(cx, cy))
    bv.car("Car", l[0], l[1], facing_yaw_ue(-1, -0.15))

    # animals
    animal("Dog", "Dog", 2.5, -6.5, H, facing_yaw_ue(1, 0.3), (80, 30, 32), "Fur")
    animal("Horse", "Horse", -11.5, 8.5, H, facing_yaw_ue(0.7, -0.7), (190, 55, 95), "Fur")
    for i, (ax, ay) in enumerate(((36, -38), (44, -42), (48, -36))):
        animal("Cow", "Cow%d" % i, ax, ay, H, random.uniform(0, 360), (200, 70, 85), "CowHide")
    animal("Sheep", "Sheep0", -30, 70, H, 30, (110, 45, 55), "CowHide")


# ===========================================================================
def main():
    if not hasattr(unreal, "ThermalHotSpot"):
        unreal.log_error("[Medieval] ThermalSensor plugin is not loaded - compile it first.")
        return
    if not os.path.isdir(SRC_DIR):
        unreal.log_error("[Medieval] missing " + SRC_DIR)
        return
    manifest = json.load(open(os.path.join(SRC_DIR, "manifest.json")))
    layout = json.load(open(os.path.join(SRC_DIR, "layout.json")))
    H = Heights(os.path.join(SRC_DIR, "heights.json"))

    bv.build_materials()
    meshes = import_meshes(sorted(manifest.keys()))
    for m in meshes.values():
        assign_materials(m)
    detect_flip(meshes)
    discover_packs()

    prepare_level()
    actors = {}
    with unreal.ScopedEditorTransaction("Build Medieval Village"):
        build_environment()
        for it in layout:
            a = place(it, meshes, H)
            if a is not None:
                actors[it["label"]] = a
        scenario(layout, manifest, actors, meshes, H)
        place_camera()
        resize_thermo_volume()
    les.save_current_level()
    log("Done: %d meshes, %d people, %d heat spots. Map saved: %s" % (
        bv._count["actors"], bv._count["people"], bv._count["hotspots"], LEVEL))


main()
