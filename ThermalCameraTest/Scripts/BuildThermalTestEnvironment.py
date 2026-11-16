"""
Team 3 (Thermal Vision Sensor) - Thermal test environment builder
Author: Neel Patel

Builds the thermal test environment in CameraTest1: one placeholder object
for every heat case Team 5 is standardizing (human, animal, vehicle, fire,
building/wall, ground) plus a trapped-survivor case, flood water and a cold
object. Every object is tagged with its heat value on the team's 0-6 scale so
the thermal material / Team 5's heat component can read it.

HOW TO RUN (Unreal Editor 5.8):
  1. Open ThermalCameraTest.uproject (Python Editor Script Plugin must be on;
     it is listed in the .uproject).
  2. Tools > Execute Python Script... > pick this file.
     (or type in the Output Log's Python console:
      py "<path>/Scripts/BuildThermalTestEnvironment.py")
  3. File > Save All, then commit.

Running it again is safe: it deletes everything it made last time (World
Outliner folder "ThermalTest") and rebuilds. Objects are placed relative to
the BP_ThermalCamera in the level, so they always land in front of the lens.

Tags added to every actor:
  Heat_<0-6>           heat value (see HEAT_SCALE below / Docs/ThermalHeatValues.csv)
  ThermalType_<Type>   Human, Animal, Vehicle, Fire, Building, Ground, Water, ColdObject, Debris
  ThermalTest          marks it as part of this test environment
"""

import math
import unreal

LEVEL_PATH = "/Game/CameraTest1"
FOLDER = "ThermalTest"
MATERIAL_DIR = "/Game/ThermalTest/Materials"
BASE_MATERIAL = "/Engine/BasicShapes/BasicShapeMaterial"

CUBE = "/Engine/BasicShapes/Cube"
CYLINDER = "/Engine/BasicShapes/Cylinder"
SPHERE = "/Engine/BasicShapes/Sphere"
CONE = "/Engine/BasicShapes/Cone"

# Multiply every placement distance (useful if the camera FOV changes).
DISTANCE_SCALE = 1.0
# Set to a number to force the ground height; None = use the Landscape's Z.
GROUND_Z_OVERRIDE = None
# Floating name labels above each object (editor only, hidden in game/captures).
ADD_LABELS = True

# --------------------------------------------------------------------------
# Heat scale (0-6). Single source of truth - keep in sync with the CSV/README.
# --------------------------------------------------------------------------
HEAT_SCALE = {
    0: "Cold - below ambient (flood water, shaded metal, sky)      ~<15 C",
    1: "Ambient background (ground, dirt, rubble, trees)           ~15-22 C",
    2: "Sun-warmed structures (building walls, pavement)           ~22-30 C",
    3: "Warm (animal fur surface, vehicle body, warm tires)         ~28-40 C",
    4: "Human body (exposed skin / clothing over skin)             ~32-37 C",
    5: "Hot machinery (running engine hood, exhaust, embers)        ~60-150 C",
    6: "Fire / open flame                                          >300 C",
}

# Colors only affect the normal RGB view (so objects are easy to tell apart).
COLORS = {
    "Skin":     (0.80, 0.55, 0.40),
    "Jacket":   (0.70, 0.08, 0.05),
    "Fur":      (0.35, 0.20, 0.08),
    "CarBody":  (0.15, 0.25, 0.45),
    "CarHood":  (0.12, 0.20, 0.38),
    "Tire":     (0.02, 0.02, 0.02),
    "Flame":    (1.00, 0.35, 0.02),
    "Log":      (0.20, 0.10, 0.04),
    "Concrete": (0.60, 0.57, 0.50),
    "Rubble":   (0.40, 0.38, 0.35),
    "Water":    (0.05, 0.15, 0.30),
    "Steel":    (0.45, 0.47, 0.50),
}

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
_material_cache = {}


def log(msg):
    unreal.log("[ThermalTest] " + msg)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def get_material(color_name):
    """Color material instance of the engine BasicShapeMaterial."""
    if color_name in _material_cache:
        return _material_cache[color_name]
    name = "MI_TT_" + color_name
    path = MATERIAL_DIR + "/" + name
    mi = None
    try:
        if unreal.EditorAssetLibrary.does_asset_exist(path):
            mi = unreal.load_asset(path)
        else:
            unreal.EditorAssetLibrary.make_directory(MATERIAL_DIR)
            mi = asset_tools.create_asset(name, MATERIAL_DIR, unreal.MaterialInstanceConstant,
                                          unreal.MaterialInstanceConstantFactoryNew())
            unreal.MaterialEditingLibrary.set_material_instance_parent(mi, unreal.load_asset(BASE_MATERIAL))
        r, g, b = COLORS[color_name]
        unreal.MaterialEditingLibrary.set_material_instance_vector_parameter_value(
            mi, "Color", unreal.LinearColor(r, g, b, 1.0))
        unreal.EditorAssetLibrary.save_loaded_asset(mi)
    except Exception as e:  # colors are cosmetic - never fail the build over them
        unreal.log_warning("[ThermalTest] could not make material %s: %s" % (name, e))
        mi = None
    _material_cache[color_name] = mi
    return mi


class Frame:
    """Placement frame: X = straight out from the camera, Y = camera-right, Z = up from the ground."""

    def __init__(self, cam_actor, ground_z):
        loc = cam_actor.get_actor_location()
        self.yaw = cam_actor.get_actor_rotation().yaw
        rad = math.radians(self.yaw)
        self.ox, self.oy, self.gz = loc.x, loc.y, ground_z
        self.fwd = (math.cos(rad), math.sin(rad))
        self.right = (-math.sin(rad), math.cos(rad))

    def world(self, fwd, right, up):
        return unreal.Vector(self.ox + self.fwd[0] * fwd + self.right[0] * right,
                             self.oy + self.fwd[1] * fwd + self.right[1] * right,
                             self.gz + up)


class ThermalObject:
    """One logical test object made of several basic-shape parts.
    Parts are given in the object's own frame (X forward, Y right, Z up from ground)."""

    def __init__(self, frame, label, thermal_type, heat, fwd, right, yaw_offset=0.0):
        self.frame, self.label, self.type, self.heat = frame, label, thermal_type, heat
        self.fwd, self.right = fwd * DISTANCE_SCALE, right * DISTANCE_SCALE
        self.yaw = frame.yaw + yaw_offset
        self.root = None
        self.actors = []

    def _to_world(self, lx, ly, lz):
        rad = math.radians(self.yaw - self.frame.yaw)
        f = self.fwd + lx * math.cos(rad) - ly * math.sin(rad)
        r = self.right + lx * math.sin(rad) + ly * math.cos(rad)
        return self.frame.world(f, r, lz)

    def part(self, name, mesh_path, scale, local=(0, 0, 0), rot=(0, 0, 0), color=None, heat=None):
        """rot = (roll, pitch, yaw) relative to the object."""
        heat = self.heat if heat is None else heat
        mesh = unreal.load_asset(mesh_path)
        rotator = unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=self.yaw + rot[2])
        actor = eas.spawn_actor_from_object(mesh, self._to_world(*local), rotator)
        actor.set_actor_scale3d(unreal.Vector(*scale))
        actor.set_actor_label("TT_%s_%s" % (self.label, name))
        actor.set_folder_path(unreal.Name("%s/%s" % (FOLDER, self.label)))
        actor.set_editor_property("tags", [unreal.Name("Heat_%d" % heat),
                                           unreal.Name("ThermalType_" + self.type),
                                           unreal.Name("ThermalTest")])
        if color:
            mi = get_material(color)
            if mi:
                actor.static_mesh_component.set_material(0, mi)
        if self.root is None:
            self.root = actor
        else:
            actor.attach_to_actor(self.root, unreal.Name(""), unreal.AttachmentRule.KEEP_WORLD,
                                  unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        self.actors.append((actor, heat))
        return actor

    def hotspot(self, name, local, intensity, radius, exponent=1.5, attach_to=None,
                start_full=True, warm_up=4.0, cool_down=25.0):
        """Localized heat drawn per pixel (needs the ThermalSensor plugin)."""
        if not hasattr(unreal, "ThermalHotSpot"):
            unreal.log_warning("[ThermalTest] ThermalSensor plugin not compiled - skipped hot spot %s" % name)
            return None
        actor = eas.spawn_actor_from_class(unreal.ThermalHotSpot, self._to_world(*local),
                                           unreal.Rotator(roll=0, pitch=0, yaw=self.yaw))
        actor.set_actor_label("TT_%s_%s" % (self.label, name))
        actor.set_folder_path(unreal.Name("%s/%s" % (FOLDER, self.label)))
        actor.set_editor_property("tags", [unreal.Name("ThermalTest"), unreal.Name("HotSpot")])
        hs = actor.get_editor_property("hot_spot")
        hs.set_editor_property("intensity_celsius", float(intensity))
        hs.set_editor_property("radius_cm", float(radius))
        hs.set_editor_property("falloff_exponent", float(exponent))
        hs.set_editor_property("start_at_full_heat", bool(start_full))
        hs.set_editor_property("warm_up_seconds", float(warm_up))
        hs.set_editor_property("cool_down_seconds", float(cool_down))
        parent = attach_to or self.root
        if parent:
            actor.attach_to_actor(parent, unreal.Name(""), unreal.AttachmentRule.KEEP_WORLD,
                                  unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        self.actors.append((actor, intensity))
        return actor

    def label_text(self, height):
        if not ADD_LABELS:
            return
        text_actor = eas.spawn_actor_from_class(unreal.TextRenderActor, self._to_world(0, 0, height),
                                                unreal.Rotator(roll=0, pitch=0, yaw=self.frame.yaw + 180))
        text_actor.set_actor_label("TT_%s_Label" % self.label)
        text_actor.set_folder_path(unreal.Name(FOLDER + "/_Labels"))
        text_actor.set_actor_hidden_in_game(True)  # never shows up in RGB/thermal captures
        comp = text_actor.get_component_by_class(unreal.TextRenderComponent)
        text = "%s  (heat %d)" % (self.label, self.heat)
        for setter in (lambda: comp.set_editor_property("text", unreal.Text(text)),
                       lambda: comp.k2_set_text(unreal.Text(text))):
            try:
                setter()
                break
            except Exception:
                pass
        for prop, value in (("world_size", 28.0),
                            ("horizontal_alignment", getattr(getattr(unreal, "HorizTextAligment", None), "EHTA_CENTER", None)),
                            ("text_render_color", unreal.Color(255, 255, 255, 255))):
            try:
                if value is not None:
                    comp.set_editor_property(prop, value)
            except Exception:
                pass


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def clear_previous():
    removed = 0
    for actor in eas.get_all_level_actors():
        path = str(actor.get_folder_path())
        if path == FOLDER or path.startswith(FOLDER + "/") or actor.actor_has_tag("ThermalTest"):
            eas.destroy_actor(actor)
            removed += 1
    if removed:
        log("removed %d actors from the previous build" % removed)


def find_camera_and_ground():
    camera, ground_z, ground_actors = None, None, []
    for actor in eas.get_all_level_actors():
        cls = actor.get_class().get_name()
        if camera is None and "BP_ThermalCamera" in cls:
            camera = actor
        if cls == "Landscape" or actor.get_actor_label() == "Floor":
            ground_actors.append(actor)
            if cls == "Landscape" and ground_z is None:
                ground_z = actor.get_actor_location().z
    if GROUND_Z_OVERRIDE is not None:
        ground_z = GROUND_Z_OVERRIDE
    return camera, (0.0 if ground_z is None else ground_z), ground_actors


def tag_ground(ground_actors):
    """Ground/background = heat 1. Adds tags without touching anything else on the actor."""
    for actor in ground_actors:
        tags = [t for t in actor.get_editor_property("tags")
                if not str(t).startswith("Heat_") and not str(t).startswith("ThermalType_")]
        tags += [unreal.Name("Heat_1"), unreal.Name("ThermalType_Ground")]
        actor.set_editor_property("tags", tags)
        log("tagged %s as Ground (heat 1)" % actor.get_actor_label())


def build(frame):
    objects = []

    # 1. Standing survivor - HUMAN (heat 4)
    # Clothing insulates (heat 3); exposed skin - face, arms - is warmest (heat 4).
    o = ThermalObject(frame, "Human_Standing", "Human", 4, fwd=750, right=-250)
    o.part("Torso", CYLINDER, (0.45, 0.35, 0.75), local=(0, 0, 122), color="Jacket", heat=3)
    o.part("Legs", CYLINDER, (0.40, 0.30, 0.85), local=(0, 0, 42), color="Jacket", heat=3)
    o.part("Head", SPHERE, (0.25, 0.25, 0.28), local=(0, 0, 175), color="Skin")
    o.part("ArmL", CYLINDER, (0.12, 0.12, 0.65), local=(0, -30, 118), color="Skin")
    o.part("ArmR", CYLINDER, (0.12, 0.12, 0.65), local=(0, 30, 118), color="Skin")
    o.label_text(215)
    objects.append(o)

    # 2. Trapped survivor half-buried by debris - HUMAN (4) + DEBRIS (1)
    o = ThermalObject(frame, "Human_Trapped", "Human", 4, fwd=1150, right=-180, yaw_offset=-90)
    o.part("Body", CYLINDER, (0.45, 0.35, 1.30), local=(0, 0, 20), rot=(0, 90, 0), color="Jacket", heat=3)
    o.part("Head", SPHERE, (0.25, 0.25, 0.25), local=(78, 0, 18), color="Skin")
    debris = [((-40, -25, 30), (25, 10, 15), (1.1, 0.8, 0.6)),
              ((-15, 30, 35), (-10, 30, 40), (0.9, 1.0, 0.7)),
              ((-60, 15, 55), (40, -15, 70), (1.2, 0.6, 0.5)),
              ((5, -10, 60), (-30, 20, 10), (0.7, 1.3, 0.4)),
              ((-85, -20, 25), (15, 5, 55), (0.8, 0.8, 0.5))]
    for i, (pos, rot, scl) in enumerate(debris):
        o.part("Debris%d" % i, CUBE, scl, local=pos, rot=rot, color="Rubble", heat=1)
    o.label_text(140)
    objects.append(o)

    # 3. Dog - ANIMAL (heat 3)
    o = ThermalObject(frame, "Animal_Dog", "Animal", 3, fwd=700, right=200, yaw_offset=90)
    o.part("Body", CUBE, (0.80, 0.30, 0.32), local=(0, 0, 52), color="Fur")
    o.part("Head", CUBE, (0.28, 0.22, 0.22), local=(48, 0, 72), color="Fur")
    for i, (lx, ly) in enumerate(((30, -10), (30, 10), (-30, -10), (-30, 10))):
        o.part("Leg%d" % i, CYLINDER, (0.08, 0.08, 0.38), local=(lx, ly, 19), color="Fur")
    o.part("Tail", CYLINDER, (0.05, 0.05, 0.30), local=(-48, 0, 68), rot=(0, 50, 0), color="Fur")
    o.label_text(120)
    objects.append(o)

    # 4. Car with a hot engine - VEHICLE (body 3, hood 5, tires 3)
    o = ThermalObject(frame, "Vehicle_Car", "Vehicle", 3, fwd=1000, right=-650, yaw_offset=90)
    o.part("Body", CUBE, (3.0, 1.8, 0.9), local=(-60, 0, 75), color="CarBody")
    hood = o.part("Hood_Engine", CUBE, (1.2, 1.8, 0.8), local=(150, 0, 70), color="CarHood", heat=3)
    o.part("Cabin", CUBE, (2.0, 1.6, 0.7), local=(-60, 0, 155), color="CarBody")
    for i, (lx, ly) in enumerate(((140, -95), (140, 95), (-140, -95), (-140, 95))):
        o.part("Tire%d" % i, CYLINDER, (0.65, 0.65, 0.25), local=(lx, ly, 32), rot=(90, 0, 0), color="Tire")
    pipe = o.part("Exhaust", CYLINDER, (0.08, 0.08, 0.30), local=(-215, 60, 30), rot=(0, 90, 0), color="Steel", heat=3)
    # Engine heat is strongest over the engine block and fades across the hood and into the body;
    # the exhaust is hottest at the tip.
    o.hotspot("EngineHeat", local=(160, 0, 100), intensity=65, radius=140, exponent=1.2, attach_to=hood)
    o.hotspot("ExhaustHeat", local=(-232, 60, 30), intensity=80, radius=45, exponent=1.5, attach_to=pipe)
    o.label_text(230)
    objects.append(o)

    # 4b. Survivor holding a stick - contact heat: warm at the grip, cold at both ends.
    # The grip warms up over a few seconds after Play (bStartAtFullHeat off) like real conduction.
    o = ThermalObject(frame, "Human_HoldingStick", "Human", 4, fwd=820, right=-470)
    o.part("Torso", CYLINDER, (0.45, 0.35, 0.75), local=(0, 0, 122), color="Jacket", heat=3)
    o.part("Legs", CYLINDER, (0.40, 0.30, 0.85), local=(0, 0, 42), color="Jacket", heat=3)
    o.part("Head", SPHERE, (0.25, 0.25, 0.28), local=(0, 0, 175), color="Skin")
    o.part("ArmL", CYLINDER, (0.12, 0.12, 0.65), local=(0, -30, 118), color="Skin")
    o.part("ArmR", CYLINDER, (0.12, 0.12, 0.65), local=(0, 30, 118), color="Skin")
    o.part("HandR", SPHERE, (0.11, 0.11, 0.13), local=(-8, 30, 82), color="Skin")
    stick_part = o.part("Stick", CYLINDER, (0.05, 0.05, 1.40), local=(-14, 30, 82), color="Log", heat=1)
    o.hotspot("GripHeat", local=(-14, 30, 82), intensity=12, radius=32, exponent=1.3,
              attach_to=stick_part, start_full=False, warm_up=5.0, cool_down=30.0)
    o.label_text(215)
    objects.append(o)

    # 5. Campfire / burning debris - FIRE (flame 6, logs 5)
    o = ThermalObject(frame, "Fire", "Fire", 6, fwd=1000, right=600)
    o.part("Flame", CONE, (0.70, 0.70, 1.10), local=(0, 0, 70), color="Flame")
    for i, yaw in enumerate((0, 60, 120)):
        o.part("Log%d" % i, CYLINDER, (0.15, 0.15, 1.0), local=(0, 0, 10), rot=(0, 90, yaw), color="Log", heat=5)
    o.label_text(170)
    try:  # orange glow so the fire also reads as fire in the RGB view
        light = eas.spawn_actor_from_class(unreal.PointLight, o._to_world(0, 0, 90), unreal.Rotator())
        light.set_actor_label("TT_Fire_Light")
        light.set_folder_path(unreal.Name(FOLDER + "/Fire"))
        light.set_editor_property("tags", [unreal.Name("ThermalTest")])
        comp = light.get_component_by_class(unreal.PointLightComponent)
        comp.set_light_color(unreal.LinearColor(1.0, 0.45, 0.1, 1.0))
        comp.set_intensity(8000.0)
        comp.set_attenuation_radius(600.0)
    except Exception as e:
        unreal.log_warning("[ThermalTest] fire light skipped: %s" % e)
    objects.append(o)

    # 6. Damaged building wall - BUILDING (heat 2)
    o = ThermalObject(frame, "Building_Wall", "Building", 2, fwd=1500, right=0)
    o.part("Wall", CUBE, (0.4, 8.0, 3.5), local=(0, 0, 175), color="Concrete")
    o.part("BrokenTop", CUBE, (0.4, 2.5, 1.0), local=(0, -250, 400), rot=(12, 0, 0), color="Concrete")
    o.label_text(470)
    objects.append(o)

    # 7. Flood water puddle - WATER / cold (heat 0)
    o = ThermalObject(frame, "Water_Puddle", "Water", 0, fwd=420, right=-300)
    o.part("Water", CYLINDER, (2.5, 1.6, 0.02), local=(0, 0, 1), color="Water")
    o.label_text(60)
    objects.append(o)

    # 8. Steel barrel in the shade - COLD OBJECT (heat 0)
    o = ThermalObject(frame, "Cold_MetalBarrel", "ColdObject", 0, fwd=550, right=400)
    o.part("Barrel", CYLINDER, (0.6, 0.6, 0.9), local=(0, 0, 45), color="Steel")
    o.label_text(120)
    objects.append(o)

    return objects


def main():
    if not les.load_level(LEVEL_PATH):
        unreal.log_error("[ThermalTest] could not open %s" % LEVEL_PATH)
        return
    camera, ground_z, ground_actors = find_camera_and_ground()
    if camera is None:
        unreal.log_error("[ThermalTest] no BP_ThermalCamera in the level - place one first.")
        return

    with unreal.ScopedEditorTransaction("Build Thermal Test Environment"):
        clear_previous()
        tag_ground(ground_actors)
        objects = build(Frame(camera, ground_z))

    les.save_current_level()

    log("camera '%s' at %s, ground Z = %.1f" % (camera.get_actor_label(), camera.get_actor_location(), ground_z))
    log("Heat scale:")
    for h in sorted(HEAT_SCALE):
        log("  %d  %s" % (h, HEAT_SCALE[h]))
    log("Built %d test objects:" % len(objects))
    for o in objects:
        parts = ", ".join("%s=%d" % (a.get_actor_label().replace("TT_%s_" % o.label, ""), h) for a, h in o.actors)
        log("  %-18s %-10s %s" % (o.label, o.type, parts))
    log("Done. Level saved. Objects are in the World Outliner folder '%s'." % FOLDER)


main()
