"""
Team 3 - Full-scale thermal test village (post-disaster search & rescue scenario)

Creates the map /Game/Maps/ThermalVillage (its own sun, sky, clouds, fog and ground)
and builds a real-scale village around a plaza:

  * 8 houses (3 m walls, pitched tile roofs, doors, glass windows, warm chimneys)
  * 1 house on fire: half-collapsed roof, flames in the windows and doorway, smoke,
    heated walls, a survivor trapped under rubble beside it
  * a campfire on the plaza with villagers around it, a stone well, a flood puddle
  * animated people (Epic's mannequin, idle animation) - one carrying a stick that
    warms where it is held
  * a parked car with a hot engine and exhaust, a dog, a cow in a pen,
    trees, bushes, fences, barrels, crates
  * BP_ThermalCamera moved up to a drone-style view over the village

Every piece carries a Heat_N tag (team 0-6 scale) so the ThermalSensor plugin turns it
into a ThermoForge heat source at Play; fires, faces, chimneys, engines and hand grips
use ThermalHotSpot actors for per-pixel heat gradients.

Run:  py "<project>/Scripts/BuildThermalVillage.py"   (safe to re-run; rebuilds everything)
"""

import math
import random
import unreal

LEVEL = "/Game/Maps/ThermalVillage"
FOLDER = "Village"
MAT_DIR = "/Game/ThermalVillage/Materials"

CUBE = "/Engine/BasicShapes/Cube"
CYL = "/Engine/BasicShapes/Cylinder"
SPHERE = "/Engine/BasicShapes/Sphere"
CONE = "/Engine/BasicShapes/Cone"
PLANE = "/Engine/BasicShapes/Plane"
PERSON_MESH = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/TutorialTPP"
ANIM_IDLE = "/Engine/Tutorial/SubEditors/TutorialAssets/Character/Tutorial_Idle"

CENTER = unreal.Vector(0, 2500, 0)   # plaza center (cm)
ROOF_SIGN = -1                       # flip the sign if roof slabs form a V instead of a peak
STREET_Y = 2500

random.seed(42)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EAL = unreal.EditorAssetLibrary
MEL = unreal.MaterialEditingLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
_mesh_cache = {}
_count = {"actors": 0, "hotspots": 0, "people": 0}


def log(msg):
    unreal.log("[Village] " + str(msg))


def mesh(path):
    if path not in _mesh_cache:
        _mesh_cache[path] = unreal.load_asset(path)
    return _mesh_cache[path]


# ===========================================================================
# Materials (procedural, no textures needed)
# ===========================================================================
SURFACE_HLSL = r"""
float3 an = abs(N);
float2 uv;
if (an.z > 0.7)        uv = P.xy;
else if (an.x > an.y)  uv = P.yz;
else                   uv = P.xz;
uv /= max(TileSize, 1.0);

// value noise (2 octaves)
float2 g = uv * 3.0;
float2 i0 = floor(g); float2 f0 = frac(g); float2 s0 = f0 * f0 * (3.0 - 2.0 * f0);
float a = frac(sin(dot(i0,                 float2(127.1, 311.7))) * 43758.5453);
float b = frac(sin(dot(i0 + float2(1, 0),  float2(127.1, 311.7))) * 43758.5453);
float c = frac(sin(dot(i0 + float2(0, 1),  float2(127.1, 311.7))) * 43758.5453);
float d = frac(sin(dot(i0 + float2(1, 1),  float2(127.1, 311.7))) * 43758.5453);
float n = lerp(lerp(a, b, s0.x), lerp(c, d, s0.x), s0.y);
float2 g2 = uv * 11.0;
float2 i1 = floor(g2); float2 f1 = frac(g2); float2 s1 = f1 * f1 * (3.0 - 2.0 * f1);
float a1 = frac(sin(dot(i1,                float2(269.5, 183.3))) * 43758.5453);
float b1 = frac(sin(dot(i1 + float2(1, 0), float2(269.5, 183.3))) * 43758.5453);
float c1 = frac(sin(dot(i1 + float2(0, 1), float2(269.5, 183.3))) * 43758.5453);
float d1 = frac(sin(dot(i1 + float2(1, 1), float2(269.5, 183.3))) * 43758.5453);
float n2 = lerp(lerp(a1, b1, s1.x), lerp(c1, d1, s1.x), s1.y);
float noise = n * 0.65 + n2 * 0.35;

float m = noise;
if (Pattern > 0.5 && Pattern < 1.5) {            // bricks / stone blocks
    float2 bb = uv * float2(2.0, 4.0);
    bb.x += 0.5 * fmod(floor(bb.y), 2.0);
    float2 fb = frac(bb);
    float id = frac(sin(dot(floor(bb), float2(12.9898, 78.233))) * 43758.5453);
    m = (fb.x < 0.05 || fb.y < 0.1) ? 1.0 : id * 0.55 + noise * 0.25;
} else if (Pattern > 1.5 && Pattern < 2.5) {     // wood planks
    float pl = frac(uv.y * 5.0);
    float id = frac(sin(floor(uv.y * 5.0) * 91.7) * 4375.85);
    float grain = frac(sin(uv.x * 40.0 + id * 10.0) * 2.0) * 0.15;
    m = (pl < 0.06) ? 1.0 : id * 0.4 + grain + noise * 0.2;
} else if (Pattern > 2.5 && Pattern < 3.5) {     // roof tiles
    float2 t = uv * float2(4.0, 6.0);
    t.x += 0.5 * fmod(floor(t.y), 2.0);
    float2 ft = frac(t);
    float id = frac(sin(dot(floor(t), float2(41.3, 17.1))) * 43758.5453);
    m = (ft.y < 0.15 || ft.x < 0.03) ? 1.0 : ft.y * 0.35 + id * 0.3 + noise * 0.15;
} else if (Pattern > 3.5) {                       // cobbles
    float2 cc = uv * 5.0;
    float2 fc = frac(cc) - 0.5;
    float id = frac(sin(dot(floor(cc), float2(63.7, 157.3))) * 43758.5453);
    m = (length(fc) > 0.45) ? 1.0 : id * 0.5 + noise * 0.3;
}
return lerp(ColorA.rgb, ColorB.rgb, saturate(m));
"""

FIRE_HLSL = r"""
float2 uv = UV.xy;
if (FlipV > 0.5) uv.y = 1.0 - uv.y;
float x = (uv.x - 0.5) * 2.0;
float y = uv.y;                                   // 0 = base of the flame, 1 = tip
float t = TimeSec * Speed + Seed * 13.0;

float2 g = float2(uv.x * 5.0 + Seed, y * 3.5 - t);
float2 i0 = floor(g); float2 f0 = frac(g); float2 s0 = f0 * f0 * (3.0 - 2.0 * f0);
float a = frac(sin(dot(i0,                 float2(127.1, 311.7))) * 43758.5453);
float b = frac(sin(dot(i0 + float2(1, 0),  float2(127.1, 311.7))) * 43758.5453);
float c = frac(sin(dot(i0 + float2(0, 1),  float2(127.1, 311.7))) * 43758.5453);
float d = frac(sin(dot(i0 + float2(1, 1),  float2(127.1, 311.7))) * 43758.5453);
float n = lerp(lerp(a, b, s0.x), lerp(c, d, s0.x), s0.y);
float2 g2 = float2(uv.x * 11.0 - Seed, y * 7.0 - t * 1.7);
float2 i1 = floor(g2); float2 f1 = frac(g2); float2 s1 = f1 * f1 * (3.0 - 2.0 * f1);
float a1 = frac(sin(dot(i1,                float2(269.5, 183.3))) * 43758.5453);
float b1 = frac(sin(dot(i1 + float2(1, 0), float2(269.5, 183.3))) * 43758.5453);
float c1 = frac(sin(dot(i1 + float2(0, 1), float2(269.5, 183.3))) * 43758.5453);
float d1 = frac(sin(dot(i1 + float2(1, 1), float2(269.5, 183.3))) * 43758.5453);
float n2 = lerp(lerp(a1, b1, s1.x), lerp(c1, d1, s1.x), s1.y);
float turb = n * 0.6 + n2 * 0.4;

float width = (1.0 - y) * 0.9 + 0.05;
float shape = saturate(1.0 - abs(x + (turb - 0.5) * 0.35 * y) / width);
float flame = saturate(shape * 1.5 + (turb - 0.5) * 1.1 - y * 0.75);
flame = smoothstep(0.12, 0.65, flame) * saturate(y * 12.0);

float3 deep = float3(0.9, 0.12, 0.01);
float3 mid  = float3(1.0, 0.45, 0.05);
float3 core = float3(1.0, 0.85, 0.45);
float3 col = lerp(deep, mid, saturate(flame * 1.6));
col = lerp(col, core, saturate((flame - 0.65) * 3.0));
return col * flame * Intensity;
"""

SMOKE_COLOR_HLSL = r"""
return Tint.rgb;
"""

SMOKE_OPACITY_HLSL = r"""
float2 uv = UV.xy;
if (FlipV > 0.5) uv.y = 1.0 - uv.y;
float x = (uv.x - 0.5) * 2.0;
float y = uv.y;
float t = TimeSec * 0.25 + Seed * 7.0;
float2 g = float2(uv.x * 3.0 + Seed, y * 2.5 - t);
float2 i0 = floor(g); float2 f0 = frac(g); float2 s0 = f0 * f0 * (3.0 - 2.0 * f0);
float a = frac(sin(dot(i0,                 float2(127.1, 311.7))) * 43758.5453);
float b = frac(sin(dot(i0 + float2(1, 0),  float2(127.1, 311.7))) * 43758.5453);
float c = frac(sin(dot(i0 + float2(0, 1),  float2(127.1, 311.7))) * 43758.5453);
float d = frac(sin(dot(i0 + float2(1, 1),  float2(127.1, 311.7))) * 43758.5453);
float n = lerp(lerp(a, b, s0.x), lerp(c, d, s0.x), s0.y);
float width = 0.35 + y * 0.6;
float shape = saturate(1.0 - abs(x) / width) * saturate(y * 4.0) * saturate((1.0 - y) * 2.0);
return saturate(shape * (n * 1.4 - 0.2)) * Density;
"""


def _scalar(mat, name, val, x, y):
    e = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", val)
    return e


def _vector(mat, name, val, x, y):
    e = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", unreal.LinearColor(*val))
    return e


def _custom(mat, code, inputs, out_type, x, y, desc):
    c = MEL.create_material_expression(mat, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("code", code)
    c.set_editor_property("output_type", out_type)
    c.set_editor_property("description", desc)
    lst = []
    for n in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        lst.append(ci)
    c.set_editor_property("inputs", lst)
    return c


def _new_material(name):
    path = MAT_DIR + "/" + name
    if EAL.does_asset_exist(path):
        mat = unreal.load_asset(path)
        MEL.delete_all_material_expressions(mat)
    else:
        EAL.make_directory(MAT_DIR)
        mat = asset_tools.create_asset(name, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())
    return mat


def build_surface_material():
    mat = _new_material("M_VillageSurface")
    wp = MEL.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -900, -200)
    nrm = MEL.create_material_expression(mat, unreal.MaterialExpressionVertexNormalWS, -900, -100)
    ca = _vector(mat, "ColorA", (0.6, 0.55, 0.5, 1), -900, 0)
    cb = _vector(mat, "ColorB", (0.4, 0.35, 0.3, 1), -900, 150)
    pat = _scalar(mat, "Pattern", 0.0, -900, 300)
    ts = _scalar(mat, "TileSize", 100.0, -900, 380)
    rough = _scalar(mat, "Roughness", 0.85, -500, 300)
    metal = _scalar(mat, "Metallic", 0.0, -500, 380)
    cust = _custom(mat, SURFACE_HLSL, ["P", "N", "ColorA", "ColorB", "Pattern", "TileSize"],
                   unreal.CustomMaterialOutputType.CMOT_FLOAT3, -500, 0, "VillageSurface")
    MEL.connect_material_expressions(wp, "", cust, "P")
    MEL.connect_material_expressions(nrm, "", cust, "N")
    MEL.connect_material_expressions(ca, "", cust, "ColorA")
    MEL.connect_material_expressions(cb, "", cust, "ColorB")
    MEL.connect_material_expressions(pat, "", cust, "Pattern")
    MEL.connect_material_expressions(ts, "", cust, "TileSize")
    MEL.connect_material_property(cust, "", unreal.MaterialProperty.MP_BASE_COLOR)
    MEL.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    MEL.connect_material_property(metal, "", unreal.MaterialProperty.MP_METALLIC)
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    return mat


def build_fire_material():
    mat = _new_material("M_VillageFire")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    uv = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -900, -200)
    tm = MEL.create_material_expression(mat, unreal.MaterialExpressionTime, -900, -100)
    params = [("Intensity", 12.0), ("Speed", 1.6), ("Seed", 0.0), ("FlipV", 1.0)]
    nodes = {n: _scalar(mat, n, v, -900, 0 + 80 * i) for i, (n, v) in enumerate(params)}
    cust = _custom(mat, FIRE_HLSL, ["UV", "TimeSec"] + [n for n, _ in params],
                   unreal.CustomMaterialOutputType.CMOT_FLOAT3, -450, 0, "Flame")
    MEL.connect_material_expressions(uv, "", cust, "UV")
    MEL.connect_material_expressions(tm, "", cust, "TimeSec")
    for n, node in nodes.items():
        MEL.connect_material_expressions(node, "", cust, n)
    MEL.connect_material_property(cust, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    return mat


def build_smoke_material():
    mat = _new_material("M_VillageSmoke")
    mat.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    mat.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    mat.set_editor_property("two_sided", True)
    uv = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -900, -200)
    tm = MEL.create_material_expression(mat, unreal.MaterialExpressionTime, -900, -100)
    tint = _vector(mat, "Tint", (0.06, 0.06, 0.06, 1), -900, 0)
    params = [("Density", 0.7), ("Seed", 0.0), ("FlipV", 1.0)]
    nodes = {n: _scalar(mat, n, v, -900, 150 + 80 * i) for i, (n, v) in enumerate(params)}
    col = _custom(mat, SMOKE_COLOR_HLSL, ["Tint"], unreal.CustomMaterialOutputType.CMOT_FLOAT3, -450, -100, "SmokeColor")
    opa = _custom(mat, SMOKE_OPACITY_HLSL, ["UV", "TimeSec"] + [n for n, _ in params],
                  unreal.CustomMaterialOutputType.CMOT_FLOAT1, -450, 100, "SmokeOpacity")
    MEL.connect_material_expressions(tint, "", col, "Tint")
    MEL.connect_material_expressions(uv, "", opa, "UV")
    MEL.connect_material_expressions(tm, "", opa, "TimeSec")
    for n, node in nodes.items():
        MEL.connect_material_expressions(node, "", opa, n)
    MEL.connect_material_property(col, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    MEL.connect_material_property(opa, "", unreal.MaterialProperty.MP_OPACITY)
    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    return mat


# name: (ColorA, ColorB, Pattern, TileSize, Roughness, Metallic)
SURFACES = {
    "Plaster":    ((0.78, 0.72, 0.60), (0.62, 0.56, 0.46), 0, 120, 0.9, 0),
    "PlasterB":   ((0.80, 0.78, 0.70), (0.66, 0.63, 0.56), 0, 120, 0.9, 0),
    "Brick":      ((0.42, 0.17, 0.10), (0.75, 0.70, 0.62), 1, 60, 0.85, 0),
    "Stone":      ((0.48, 0.47, 0.44), (0.30, 0.29, 0.27), 1, 90, 0.9, 0),
    "Timber":     ((0.33, 0.20, 0.10), (0.16, 0.09, 0.05), 2, 120, 0.8, 0),
    "RoofTile":   ((0.45, 0.13, 0.08), (0.18, 0.06, 0.04), 3, 90, 0.75, 0),
    "RoofSlate":  ((0.22, 0.23, 0.26), (0.10, 0.10, 0.12), 3, 80, 0.7, 0),
    "Charred":    ((0.07, 0.06, 0.05), (0.20, 0.17, 0.14), 0, 60, 0.95, 0),
    "Dirt":       ((0.36, 0.27, 0.17), (0.25, 0.19, 0.12), 0, 300, 0.95, 0),
    "Cobble":     ((0.42, 0.40, 0.37), (0.18, 0.17, 0.16), 4, 80, 0.9, 0),
    "Grass":      ((0.22, 0.34, 0.10), (0.12, 0.22, 0.06), 0, 200, 0.95, 0),
    "Leaves":     ((0.16, 0.32, 0.08), (0.07, 0.17, 0.04), 0, 60, 0.9, 0),
    "Bark":       ((0.25, 0.17, 0.10), (0.12, 0.08, 0.05), 2, 40, 0.95, 0),
    "Glass":      ((0.10, 0.16, 0.22), (0.05, 0.08, 0.12), 0, 400, 0.05, 0.6),
    "Door":       ((0.30, 0.16, 0.07), (0.14, 0.07, 0.03), 2, 60, 0.7, 0),
    "CarPaint":   ((0.55, 0.05, 0.04), (0.45, 0.04, 0.03), 0, 500, 0.3, 0.6),
    "Tire":       ((0.03, 0.03, 0.03), (0.06, 0.06, 0.06), 0, 50, 0.9, 0),
    "Metal":      ((0.45, 0.46, 0.48), (0.30, 0.31, 0.33), 0, 100, 0.4, 0.9),
    "Water":      ((0.05, 0.12, 0.16), (0.03, 0.08, 0.10), 0, 500, 0.05, 0.3),
    "Fur":        ((0.40, 0.25, 0.12), (0.25, 0.15, 0.07), 0, 20, 0.95, 0),
    "CowHide":    ((0.85, 0.83, 0.80), (0.10, 0.09, 0.08), 0, 70, 0.9, 0),
    "Hay":        ((0.78, 0.66, 0.32), (0.60, 0.48, 0.20), 2, 30, 0.95, 0),
    "ClothRed":   ((0.55, 0.08, 0.06), (0.40, 0.05, 0.04), 0, 30, 0.9, 0),
    "ClothBlue":  ((0.10, 0.18, 0.45), (0.06, 0.12, 0.30), 0, 30, 0.9, 0),
    "ClothGreen": ((0.15, 0.35, 0.15), (0.10, 0.24, 0.10), 0, 30, 0.9, 0),
    "ClothBrown": ((0.40, 0.28, 0.16), (0.28, 0.19, 0.10), 0, 30, 0.9, 0),
    "ClothGray":  ((0.45, 0.45, 0.47), (0.32, 0.32, 0.34), 0, 30, 0.9, 0),
}
MI = {}


def build_materials():
    base = build_surface_material()
    for name, (ca, cb, pat, ts, rough, met) in SURFACES.items():
        path = MAT_DIR + "/MI_V_" + name
        if EAL.does_asset_exist(path):
            mi = unreal.load_asset(path)
        else:
            mi = asset_tools.create_asset("MI_V_" + name, MAT_DIR, unreal.MaterialInstanceConstant,
                                          unreal.MaterialInstanceConstantFactoryNew())
        MEL.set_material_instance_parent(mi, base)
        MEL.set_material_instance_vector_parameter_value(mi, "ColorA", unreal.LinearColor(ca[0], ca[1], ca[2], 1))
        MEL.set_material_instance_vector_parameter_value(mi, "ColorB", unreal.LinearColor(cb[0], cb[1], cb[2], 1))
        MEL.set_material_instance_scalar_parameter_value(mi, "Pattern", float(pat))
        MEL.set_material_instance_scalar_parameter_value(mi, "TileSize", float(ts))
        MEL.set_material_instance_scalar_parameter_value(mi, "Roughness", float(rough))
        MEL.set_material_instance_scalar_parameter_value(mi, "Metallic", float(met))
        EAL.save_loaded_asset(mi)
        MI[name] = mi
    MI["Fire"] = build_fire_material()
    MI["Smoke"] = build_smoke_material()
    log("materials ready (%d)" % len(MI))


# ===========================================================================
# Spawning helpers
# ===========================================================================
def rot_xy(x, y, yaw_deg):
    r = math.radians(yaw_deg)
    return x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)


def tag_list(heat, ttype, extra=()):
    tags = ["VillageBuild"]
    if heat is not None:
        tags += ["Heat_%d" % heat, "ThermalType_" + ttype]
    return [unreal.Name(t) for t in list(tags) + list(extra)]


def spawn_mesh(label, mesh_path, loc, scale, rot=(0, 0, 0), mat=None, heat=1, ttype="Debris",
               folder="Props", collision=True, shadows=True, main_pass=True):
    """rot = (roll, pitch, yaw) in degrees; loc in world cm."""
    a = eas.spawn_actor_from_object(mesh(mesh_path), unreal.Vector(*loc),
                                    unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
    a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_actor_label(label)
    a.set_folder_path(unreal.Name("%s/%s" % (FOLDER, folder)))
    a.set_editor_property("tags", tag_list(heat, ttype))
    smc = a.static_mesh_component
    if mat is not None:
        smc.set_material(0, MI[mat] if isinstance(mat, str) else mat)
    if not collision:
        smc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    if not shadows:
        smc.set_editor_property("cast_shadow", False)
    if not main_pass:
        smc.set_editor_property("render_in_main_pass", False)
    _count["actors"] += 1
    return a


def box(label, center, size, yaw=0, mat="Plaster", heat=2, ttype="Building", folder="Houses", rot=None, **kw):
    """Axis box of size (x, y, z) cm centered at center, rotated by yaw (or full rot)."""
    r = rot if rot is not None else (0, 0, yaw)
    return spawn_mesh(label, CUBE, center, (size[0] / 100.0, size[1] / 100.0, size[2] / 100.0), r,
                      mat, heat, ttype, folder, **kw)


def hotspot(label, loc, intensity, radius, exponent=1.5, attach=None, socket="", folder="HeatSpots",
            start_full=True, warm_up=4.0, cool_down=25.0):
    if not hasattr(unreal, "ThermalHotSpot"):
        return None
    a = eas.spawn_actor_from_class(unreal.ThermalHotSpot, unreal.Vector(*loc), unreal.Rotator())
    a.set_actor_label(label)
    a.set_folder_path(unreal.Name("%s/%s" % (FOLDER, folder)))
    a.set_editor_property("tags", tag_list(None, "", ["HotSpot"]))
    hs = a.get_editor_property("hot_spot")
    hs.set_editor_property("intensity_celsius", float(intensity))
    hs.set_editor_property("radius_cm", float(radius))
    hs.set_editor_property("falloff_exponent", float(exponent))
    hs.set_editor_property("start_at_full_heat", bool(start_full))
    hs.set_editor_property("warm_up_seconds", float(warm_up))
    hs.set_editor_property("cool_down_seconds", float(cool_down))
    if attach is not None:
        rule = unreal.AttachmentRule.KEEP_WORLD
        if isinstance(attach, unreal.SceneComponent):
            a.attach_to_component(attach, unreal.Name(socket), rule, rule, rule, False)
        else:
            a.attach_to_actor(attach, unreal.Name(socket), rule, rule, rule, False)
    _count["hotspots"] += 1
    return a


def light(label, loc, color, intensity, radius, folder="Lights"):
    a = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(*loc), unreal.Rotator())
    a.set_actor_label(label)
    a.set_folder_path(unreal.Name("%s/%s" % (FOLDER, folder)))
    a.set_editor_property("tags", tag_list(None, ""))
    c = a.get_component_by_class(unreal.PointLightComponent)
    try:
        c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    except Exception:
        pass
    c.set_light_color(unreal.LinearColor(*color))
    c.set_intensity(float(intensity))
    c.set_attenuation_radius(float(radius))
    return a


# ===========================================================================
# Fire, smoke
# ===========================================================================
def fire(label, loc, height=150, width=90, intensity_c=150, heat_radius=220, smoke=True, folder="Fires",
         light_intensity=6000):
    """Visible animated flames + invisible thermal flame core + radiant heat + light + smoke."""
    x, y, z = loc
    EAL.make_directory(MAT_DIR + "/Flames")
    for i, yaw in enumerate((0, 60, 120)):
        f = spawn_mesh("%s_Flame%d" % (label, i), PLANE, (x, y, z + height / 2.0),
                       (width / 100.0, height / 100.0, 1), (90, 0, yaw), None, None, "", folder,
                       collision=False, shadows=False)
        mi = asset_tools.create_asset("MI_Flame_%s_%d" % (label, i), MAT_DIR + "/Flames",
                                      unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew()) \
            if not EAL.does_asset_exist(MAT_DIR + "/Flames/MI_Flame_%s_%d" % (label, i)) \
            else unreal.load_asset(MAT_DIR + "/Flames/MI_Flame_%s_%d" % (label, i))
        MEL.set_material_instance_parent(mi, MI["Fire"])
        MEL.set_material_instance_scalar_parameter_value(mi, "Seed", random.uniform(0, 10))
        MEL.set_material_instance_scalar_parameter_value(mi, "Speed", random.uniform(1.3, 2.0))
        EAL.save_loaded_asset(mi)
        f.static_mesh_component.set_material(0, mi)
    # thermal flame core: invisible to the RGB camera, white-hot to the thermal camera
    spawn_mesh(label + "_ThermalCore", CONE, (x, y, z + height * 0.38), (width / 140.0, width / 140.0, height / 130.0),
               (0, 0, 0), None, 5, "Fire", folder, collision=False, shadows=False, main_pass=False)
    hotspot(label + "_RadiantHeat", (x, y, z + 40), intensity_c, heat_radius, exponent=1.8, folder=folder)
    light(label + "_Light", (x, y, z + height * 0.6), (1.0, 0.45, 0.12, 1), light_intensity, heat_radius * 6, folder)
    if smoke:
        for i, yaw in enumerate((20, 110)):
            s = spawn_mesh("%s_Smoke%d" % (label, i), PLANE, (x, y, z + height + 350),
                           (2.6, 7.0, 1), (90, 0, yaw), None, None, "", folder, collision=False, shadows=False)
            mi_path = MAT_DIR + "/Flames/MI_Smoke_%s_%d" % (label, i)
            smi = unreal.load_asset(mi_path) if EAL.does_asset_exist(mi_path) else asset_tools.create_asset(
                "MI_Smoke_%s_%d" % (label, i), MAT_DIR + "/Flames", unreal.MaterialInstanceConstant,
                unreal.MaterialInstanceConstantFactoryNew())
            MEL.set_material_instance_parent(smi, MI["Smoke"])
            MEL.set_material_instance_scalar_parameter_value(smi, "Seed", random.uniform(0, 10))
            EAL.save_loaded_asset(smi)
            s.static_mesh_component.set_material(0, smi)


# ===========================================================================
# People and animals
# ===========================================================================
def person(label, loc, face_yaw, cloth="ClothBlue", lying=False, folder="People"):
    """Epic mannequin with idle animation. face_yaw = direction the person looks (deg)."""
    sk = unreal.load_asset(PERSON_MESH)
    rot = unreal.Rotator(roll=0, pitch=(-90 if lying else 0), yaw=face_yaw - 90)
    a = eas.spawn_actor_from_object(sk, unreal.Vector(*loc), rot)
    a.set_actor_label(label)
    a.set_folder_path(unreal.Name("%s/%s" % (FOLDER, folder)))
    a.set_editor_property("tags", tag_list(4, "Human"))
    comp = a.get_component_by_class(unreal.SkeletalMeshComponent)
    try:
        comp.set_material(0, MI[cloth])
    except Exception:
        pass
    anim = unreal.load_asset(ANIM_IDLE)
    if anim and not lying:
        try:
            comp.set_editor_property("animation_mode", unreal.AnimationMode.ANIMATION_SINGLE_NODE)
            comp.override_animation_data(anim, True, True, random.uniform(0, 2.0), random.uniform(0.85, 1.15))
        except Exception as e:
            unreal.log_warning("[Village] animation skipped on %s: %s" % (label, e))
    # face and hands are the warmest skin (clothing insulates the rest of the body)
    try:
        head = comp.get_socket_location("head")
        hotspot(label + "_FaceHeat", (head.x, head.y, head.z), 6, 22, 1.4, attach=comp, socket="head", folder=folder)
    except Exception:
        pass
    _count["people"] += 1
    return a, comp


def quadruped(label, loc, yaw, size, mat, heat, ttype, folder="Animals"):
    """Simple box animal: size = (length, width, height of body) in cm."""
    L, W, H = size
    x, y, z = loc
    leg_h = H * 0.9
    body_z = z + leg_h + H / 2
    parts = []
    parts.append(box(label + "_Body", (x, y, body_z), (L, W, H), yaw, mat, heat, ttype, folder))
    hx, hy = rot_xy(L * 0.58, 0, yaw)
    parts.append(box(label + "_Head", (x + hx, y + hy, body_z + H * 0.35), (L * 0.32, W * 0.75, H * 0.75), yaw, mat,
                     heat, ttype, folder))
    for i, (lx, ly) in enumerate(((L * 0.38, W * 0.3), (L * 0.38, -W * 0.3), (-L * 0.38, W * 0.3), (-L * 0.38, -W * 0.3))):
        dx, dy = rot_xy(lx, ly, yaw)
        parts.append(spawn_mesh("%s_Leg%d" % (label, i), CYL, (x + dx, y + dy, z + leg_h / 2),
                                (W * 0.004, W * 0.004, leg_h / 100.0), (0, 0, 0), mat, heat, ttype, folder))
    # nose / eyes are the warmest spot on an animal's fur-covered head
    hotspot(label + "_NoseHeat", (x + hx * 1.25, y + hy * 1.25, body_z + H * 0.3), 5, max(W * 0.5, 15), 1.5,
            attach=parts[1], folder=folder)
    return parts


# ===========================================================================
# Buildings
# ===========================================================================
def house(label, cx, cy, yaw, wall_mat="Plaster", roof_mat="RoofTile", width=800, depth=600, wall_h=300,
          burning=False, chimney=True):
    """Front of the house faces local -Y (toward the street after rotation)."""
    T = 25.0
    folder = "Houses/" + label
    wall_heat = 3 if burning else 2
    wmat = "Charred" if burning else wall_mat

    def W(name, lx, ly, lz, sx, sy, sz, mat=None, heat=None, ttype="Building", rot_extra=(0, 0, 0)):
        dx, dy = rot_xy(lx, ly, yaw)
        return box("%s_%s" % (label, name), (cx + dx, cy + dy, lz), (sx, sy, sz),
                   rot=(rot_extra[0], rot_extra[1], yaw + rot_extra[2]), mat=mat or wmat,
                   heat=wall_heat if heat is None else heat, ttype=ttype, folder=folder)

    hw, hd = width / 2.0, depth / 2.0
    # foundation
    W("Foundation", 0, 0, 10, width + 40, depth + 40, 20, mat="Stone", heat=1)
    # front wall with a door (1.1 m) and two windows (1.0 x 1.1 m)
    door_w, win_w, win_h, sill = 110, 100, 110, 100
    front_y = -hd + T / 2
    seg = [(-hw, -hw + 120), (-hw + 120 + win_w, -door_w / 2), (door_w / 2, hw - 120 - win_w), (hw - 120, hw)]
    for i, (a, b) in enumerate(seg):
        W("Front%d" % i, (a + b) / 2, front_y, wall_h / 2, b - a, T, wall_h)
    W("DoorLintel", 0, front_y, (220 + wall_h) / 2, door_w, T, wall_h - 220)
    for side, wx in (("L", -hw + 120 + win_w / 2), ("R", hw - 120 - win_w / 2)):
        W("Win%sBelow" % side, wx, front_y, sill / 2, win_w, T, sill)
        W("Win%sAbove" % side, wx, front_y, (sill + win_h + wall_h) / 2, win_w, T, wall_h - sill - win_h)
        # glass reflects the cold sky: windows read cold on a thermal camera
        W("Win%sGlass" % side, wx, front_y + 3, sill + win_h / 2, win_w, 4, win_h, mat="Glass", heat=0, ttype="Glass")
    # door (slightly open on the burning house so flames show through)
    if burning:
        W("Door", -door_w / 2 + 8, front_y - 45, 110, 8, 90, 220, mat="Charred", heat=3, rot_extra=(0, 0, 0))
    else:
        W("Door", 0, front_y + 5, 110, door_w - 6, 8, 220, mat="Door", heat=2)
    # back wall with one window
    back_y = hd - T / 2
    W("BackL", (-hw + -60) / 2, back_y, wall_h / 2, hw - 60, T, wall_h)
    W("BackR", (60 + hw) / 2, back_y, wall_h / 2, hw - 60, T, wall_h)
    W("BackWinBelow", 0, back_y, sill / 2, 120, T, sill)
    W("BackWinAbove", 0, back_y, (sill + win_h + wall_h) / 2, 120, T, wall_h - sill - win_h)
    W("BackGlass", 0, back_y - 3, sill + win_h / 2, 120, 4, win_h, mat="Glass", heat=0, ttype="Glass")
    # side walls + gables (45 degree roof: gable is half of a diamond)
    gable = depth / math.sqrt(2.0)
    for side, sx in (("L", -hw + T / 2), ("R", hw - T / 2)):
        if burning and side == "R":
            # collapsed side wall: only a stub remains
            W("Side%s" % side, sx, 0, 70, T, depth, 140)
            continue
        W("Side%s" % side, sx, 0, wall_h / 2, T, depth, wall_h)
        W("Gable%s" % side, sx, 0, wall_h, T, gable, gable, rot_extra=(45, 0, 0))
    # roof: two 45 degree slabs (one fallen in on the burning house)
    slope = hd / math.cos(math.radians(45)) + 45
    rmat = "Charred" if burning else roof_mat
    for side, sgn in (("Front", -1), ("Back", 1)):
        if burning and side == "Front":
            W("RoofFallen", 80, -40, 120, width * 0.7, slope, 18, mat="Charred", heat=3, rot_extra=(-20, 8, 0))
            continue
        W("Roof%s" % side, 0, sgn * hd / 2, wall_h + hd / 2 + 12, width + 70, slope, 18,
          mat=rmat, heat=wall_heat, rot_extra=(-45 * sgn * ROOF_SIGN, 0, 0))
    W("Ridge", 0, 0, wall_h + hd + 18, width + 70, 26, 22, mat=rmat, heat=wall_heat)
    if chimney and not burning:
        c = W("Chimney", hw * 0.55, hd * 0.35, wall_h + hd * 0.9, 60, 60, 260, mat="Brick", heat=2)
        top = c.get_actor_location()
        # warm flue gases: hottest at the chimney top, fading down the brick
        hotspot(label + "_ChimneyHeat", (top.x, top.y, top.z + 120), 35, 110, 1.6, attach=c, folder=folder)
    if burning:
        # fires inside, at the doorway and in both windows, heating the walls from inside
        fx, fy = rot_xy(0, -40, yaw)
        fire(label + "_FireMain", (cx + fx, cy + fy, 0), height=330, width=260, intensity_c=260, heat_radius=520,
             smoke=True, folder=folder, light_intensity=20000)
        for side, wx in (("L", -hw + 120 + win_w / 2), ("R", hw - 120 - win_w / 2)):
            dx, dy = rot_xy(wx, -hd + 30, yaw)
            fire("%s_FireWin%s" % (label, side), (cx + dx, cy + dy, sill), height=170, width=95, intensity_c=180,
                 heat_radius=200, smoke=False, folder=folder, light_intensity=6000)
        dx, dy = rot_xy(0, -hd + 30, yaw)
        fire(label + "_FireDoor", (cx + dx, cy + dy, 0), height=240, width=110, intensity_c=200, heat_radius=240,
             smoke=False, folder=folder, light_intensity=20000)


def tree(label, x, y, h=None):
    h = h or random.uniform(650, 950)
    folder = "Nature"
    spawn_mesh(label + "_Trunk", CYL, (x, y, h * 0.3), (0.38, 0.38, h * 0.6 / 100.0), (0, 0, 0), "Bark", 1, "Vegetation", folder)
    for i in range(3):
        ox, oy = random.uniform(-90, 90), random.uniform(-90, 90)
        s = random.uniform(2.6, 3.6)
        # leaves cool themselves by evaporation: a touch below ambient
        spawn_mesh("%s_Canopy%d" % (label, i), SPHERE, (x + ox, y + oy, h * (0.65 + 0.12 * i)), (s, s, s * 0.85),
                   (0, 0, random.uniform(0, 360)), "Leaves", 1, "Vegetation", folder)


def bush(label, x, y):
    s = random.uniform(0.8, 1.4)
    spawn_mesh(label, SPHERE, (x, y, 40 * s), (1.4 * s, 1.2 * s, 0.9 * s), (0, 0, random.uniform(0, 360)),
               "Leaves", 1, "Vegetation", "Nature")


def fence(label, x0, y0, x1, y1, folder="Fences"):
    L = math.hypot(x1 - x0, y1 - y0)
    yaw = math.degrees(math.atan2(y1 - y0, x1 - x0))
    n = max(int(L / 250), 1)
    for i in range(n + 1):
        t = i / float(n)
        spawn_mesh("%s_Post%d" % (label, i), CUBE, (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 55),
                   (0.12, 0.12, 1.1), (0, 0, yaw), "Timber", 1, "Debris", folder)
    for k, z in enumerate((45, 90)):
        box("%s_Rail%d" % (label, k), ((x0 + x1) / 2, (y0 + y1) / 2, z), (L, 6, 10), yaw, "Timber", 1, "Debris", folder)


def car(label, x, y, yaw):
    folder = "Vehicles"

    def P(name, lx, ly, lz, sx, sy, sz, mat, heat=3, rot=(0, 0, 0), mesh_path=CUBE):
        dx, dy = rot_xy(lx, ly, yaw)
        return spawn_mesh("%s_%s" % (label, name), mesh_path, (x + dx, y + dy, lz), (sx / 100.0, sy / 100.0, sz / 100.0),
                          (rot[0], rot[1], yaw + rot[2]), mat, heat, "Vehicle", folder)

    body = P("Body", 0, 0, 70, 430, 180, 70, "CarPaint")
    hood = P("Hood", 155, 0, 108, 120, 176, 6, "CarPaint")
    P("Cabin", -40, 0, 140, 220, 165, 70, "CarPaint")
    P("Windshield", 72, 0, 140, 6, 150, 60, "Glass", 0, rot=(0, -30, 0))
    P("RearGlass", -152, 0, 140, 6, 150, 55, "Glass", 0, rot=(0, 30, 0))
    for side in (-1, 1):
        P("SideGlass%d" % side, -40, side * 83, 145, 190, 4, 45, "Glass", 0)
    for i, (lx, ly) in enumerate(((140, -88), (140, 88), (-140, -88), (-140, 88))):
        P("Tire%d" % i, lx, ly, 35, 70, 70, 24, "Tire", 3, rot=(90, 0, 0), mesh_path=CYL)
    pipe = P("Exhaust", -222, 55, 32, 30, 8, 8, "Metal", 3, rot=(0, 90, 0), mesh_path=CYL)
    # the engine was running: hood hottest over the block, fading to the paint; hot exhaust tip
    hl = hood.get_actor_location()
    hotspot(label + "_EngineHeat", (hl.x, hl.y, hl.z - 20), 60, 150, 1.2, attach=hood, folder=folder)
    pl = pipe.get_actor_location()
    ex, ey = rot_xy(-18, 0, yaw)
    hotspot(label + "_ExhaustHeat", (pl.x + ex, pl.y + ey, pl.z), 85, 45, 1.5, attach=pipe, folder=folder)
    # the grille/radiator at the front is warm too
    gx, gy = rot_xy(216, 0, yaw)
    hotspot(label + "_RadiatorHeat", (x + gx, y + gy, 75), 30, 70, 1.5, attach=body, folder=folder)


# ===========================================================================
# Level setup
# ===========================================================================
CAMERA_BP = "/Game/SimBlank/Blueprints/BP_ThermalCamera"


def prepare_level():
    """Open (or create) the village map and clear everything a previous run built."""
    if EAL.does_asset_exist(LEVEL):
        les.load_level(LEVEL)
    else:
        EAL.make_directory("/Game/Maps")
        if not les.new_level(LEVEL):
            raise RuntimeError("could not create %s" % LEVEL)
        log("created new map %s" % LEVEL)
    removed = 0
    for a in eas.get_all_level_actors():
        if a.actor_has_tag("VillageBuild") or str(a.get_folder_path()).startswith(FOLDER):
            eas.destroy_actor(a)
            removed += 1
    log("cleared %d actors from the previous build" % removed)


def env_actor(cls, label, loc=(0, 0, 0), rot=(0, 0, 0)):
    a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc), unreal.Rotator(roll=rot[0], pitch=rot[1], yaw=rot[2]))
    a.set_actor_label(label)
    a.set_folder_path(unreal.Name(FOLDER + "/Environment"))
    a.set_editor_property("tags", tag_list(None, ""))
    return a


def build_environment():
    """Sun, sky, clouds, fog and a large ground plane (afternoon, clear sky)."""
    sun = env_actor(unreal.DirectionalLight, "Sun", (0, 0, 2000), (0, -38, 35))
    try:
        sc = sun.get_component_by_class(unreal.DirectionalLightComponent)
        sc.set_editor_property("atmosphere_sun_light", True)
        sc.set_editor_property("intensity", 8.0)
    except Exception as e:
        unreal.log_warning("[Village] sun settings: %s" % e)
    env_actor(unreal.SkyAtmosphere, "SkyAtmosphere")
    sky = env_actor(unreal.SkyLight, "SkyLight", (0, 0, 1000))
    try:
        slc = sky.get_component_by_class(unreal.SkyLightComponent)
        slc.set_editor_property("real_time_capture", True)
        slc.set_mobility(unreal.ComponentMobility.MOVABLE)
    except Exception as e:
        unreal.log_warning("[Village] skylight settings: %s" % e)
    env_actor(unreal.ExponentialHeightFog, "HeightFog")
    if hasattr(unreal, "VolumetricCloud"):
        env_actor(unreal.VolumetricCloud, "Clouds")
    # 600 m x 600 m ground; the village sits in the middle
    box("Ground", (CENTER.x, CENTER.y, -50), (60000, 60000, 100), 0, "Grass", 1, "Ground", "Environment")
    # where the player (free camera) starts in Play mode
    env_actor(unreal.PlayerStart, "PlayerStart", (CENTER.x - 900, CENTER.y - 3200, 600), (0, -12, 80))


ROTATOR_BP = "/Game/CameraRotator_Blueprint"


def place_camera():
    """Drone-style thermal camera: 18 m up, 40 m back, looking down ~24 degrees.

    Like CameraTest1, the camera is attached to Obeth's CameraRotator_Blueprint, which
    turns left/right on the I and P keys (it rotates, the camera follows)."""
    bp = unreal.load_asset(CAMERA_BP)
    if bp is None:
        unreal.log_warning("[Village] BP_ThermalCamera not found")
        return
    target = (CENTER.x, CENTER.y - 4000, 1800)
    cam = env_actor(bp.generated_class(), "ThermalCamera_Drone", target, (0, -24, 90))
    cam.set_folder_path(unreal.Name(FOLDER + "/Camera"))
    rot_bp = unreal.load_asset(ROTATOR_BP)
    if rot_bp is not None:
        rotator = env_actor(rot_bp.generated_class(), "CameraRotator_Drone", target, (0, 0, 90))
        rotator.set_folder_path(unreal.Name(FOLDER + "/Camera"))
        # it must be Movable or AddActorLocalRotation (I / P) does nothing
        try:
            rotator.get_component_by_class(unreal.StaticMeshComponent).set_mobility(unreal.ComponentMobility.MOVABLE)
        except Exception as e:
            unreal.log_warning("[Village] rotator mobility: %s" % e)
        # keep the rotator's disc out of the camera images; its I/P rotation logic still runs
        try:
            rotator.set_actor_hidden_in_game(True)
            rotator.set_actor_enable_collision(False)
        except Exception:
            pass
        rule = unreal.AttachmentRule.KEEP_WORLD
        cam.attach_to_actor(rotator, unreal.Name(""), rule, rule, rule, False)
        log("thermal camera attached to CameraRotator (I / P rotate it)")
    else:
        unreal.log_warning("[Village] CameraRotator_Blueprint not found - camera will not rotate with I/P")
    log("thermal camera placed at %s" % (target,))


def resize_thermo_volume():
    if not hasattr(unreal, "ThermoForgeVolume"):
        return
    vol = next((a for a in eas.get_all_level_actors() if a.get_class().get_name() == "ThermoForgeVolume"), None)
    if vol is None:
        vol = eas.spawn_actor_from_class(unreal.ThermoForgeVolume, unreal.Vector(CENTER.x, CENTER.y, 500), unreal.Rotator())
        vol.set_actor_label("ThermoForgeVolume_Village")
        vol.set_folder_path(unreal.Name("ThermoForge"))
    vol.set_actor_location(unreal.Vector(CENTER.x, CENTER.y, 500), False, False)
    vol.set_editor_property("box_extent", unreal.Vector(3500, 2500, 900))


# ===========================================================================
# The village
# ===========================================================================
def build_village():
    cx, cy = CENTER.x, CENTER.y

    # ground: dirt street, cobbled plaza, grass behind the houses
    box("Street", (cx, cy, 1), (7000, 900, 2), 0, "Dirt", 1, "Ground", "Ground", collision=False)
    spawn_mesh("Plaza", CYL, (cx, cy, 2), (13.0, 13.0, 0.03), (0, 0, 0), "Cobble", 1, "Ground", "Ground", collision=False)
    for side in (-1, 1):
        box("Yard%d" % side, (cx, cy + side * 1900, 1), (7600, 2600, 2), 0, "Grass", 1, "Ground", "Ground", collision=False)

    # houses: north row faces south (yaw 180), south row faces north (yaw 0)
    # (the lot at south +15 m is left empty so the drone camera can see the burning house across the street)
    north = [(-2600, "Plaster", "RoofTile"), (-1500, "Brick", "RoofSlate"), (1500, "PlasterB", "RoofTile"),
             (2600, "Stone", "RoofSlate")]
    south = [(-2600, "Stone", "RoofTile"), (-1500, "PlasterB", "RoofSlate"), (2600, "Plaster", "RoofSlate")]
    for i, (x, wm, rm) in enumerate(north):
        house("House_N%d" % i, cx + x, cy + 1050, 0, wm, rm, burning=(x == 1500))
    for i, (x, wm, rm) in enumerate(south):
        house("House_S%d" % i, cx + x, cy - 1050, 180, wm, rm)
    fence("EmptyLot", cx + 1100, cy - 600, cx + 1900, cy - 600)

    # collapsed rubble in front of the burning house (street side) with a trapped survivor
    bx, by = cx + 1500, cy + 1050
    for i in range(10):
        box("Rubble%d" % i, (bx + random.uniform(-380, 380), by - 430 + random.uniform(-90, 90), random.uniform(15, 50)),
            (random.uniform(60, 150), random.uniform(40, 110), random.uniform(25, 60)),
            rot=(random.uniform(-25, 25), random.uniform(-25, 25), random.uniform(0, 360)),
            mat=random.choice(["Charred", "Stone", "Brick"]), heat=1, ttype="Debris", folder="Rubble")
    person("Survivor_Trapped", (bx - 150, by - 520, 18), 180, "ClothGray", lying=True)
    for i in range(4):  # beams over the legs
        box("Beam%d" % i, (bx - 70 + i * 35, by - 520 + random.uniform(-25, 25), 45 + i * 8), (260, 22, 22),
            rot=(0, random.uniform(-10, 10), 75 + i * 9), mat="Charred", heat=2, ttype="Debris", folder="Rubble")

    # plaza: campfire with villagers around it, a stone well, a flood puddle
    fx, fy = cx + 350, cy - 150
    for i in range(8):
        a = i * 45
        box("FireRing%d" % i, (fx + 70 * math.cos(math.radians(a)), fy + 70 * math.sin(math.radians(a)), 12),
            (30, 25, 22), a, "Stone", 2, "Debris", "Campfire")
    for i, a in enumerate((0, 60, 120)):
        spawn_mesh("CampfireLog%d" % i, CYL, (fx, fy, 12), (0.18, 0.18, 1.1), (0, 90, a), "Charred", 5, "Fire", "Campfire")
    fire("Campfire", (fx, fy, 10), height=140, width=80, intensity_c=170, heat_radius=180, smoke=True,
         folder="Campfire", light_intensity=6000)
    clothes = ["ClothRed", "ClothBlue", "ClothGreen", "ClothBrown", "ClothGray"]
    for i, a in enumerate((20, 110, 200, 290)):
        r = 230
        px, py = fx + r * math.cos(math.radians(a)), fy + r * math.sin(math.radians(a))
        person("Villager_Fire%d" % i, (px, py, 0), a + 180, clothes[i % 5])

    wx, wy = cx - 450, cy + 150
    spawn_mesh("Well_Wall", CYL, (wx, wy, 45), (1.6, 1.6, 0.9), (0, 0, 0), "Stone", 1, "Building", "Well")
    spawn_mesh("Well_Water", CYL, (wx, wy, 88), (1.35, 1.35, 0.02), (0, 0, 0), "Water", 0, "Water", "Well", collision=False)
    for i, a in enumerate((0, 180)):
        spawn_mesh("Well_Post%d" % i, CUBE, (wx + 75 * math.cos(math.radians(a)), wy, 150), (0.12, 0.12, 2.1),
                   (0, 0, 0), "Timber", 1, "Building", "Well")
    box("Well_Roof", (wx, wy, 265), (210, 120, 12), 0, "RoofTile", 2, "Building", "Well")
    spawn_mesh("FloodPuddle", CYL, (cx - 1900, cy - 250, 3), (6.0, 3.5, 0.02), (0, 0, 15), "Water", 0, "Water", "Ground",
               collision=False)

    # people around the village
    person("Villager_Talk0", (cx - 1200, cy + 120, 0), 10, "ClothRed")
    person("Villager_Talk1", (cx - 1050, cy + 150, 0), 190, "ClothBrown")
    person("Villager_Talk2", (cx - 1120, cy + 260, 0), 260, "ClothGreen")
    person("Villager_Door", (cx - 1500, cy + 640, 0), 270, "ClothBlue")
    person("Villager_Car", (cx + 2050, cy + 330, 0), 200, "ClothGray")
    person("Villager_Rescuer0", (cx + 1200, cy + 420, 0), 60, "ClothRed")
    person("Villager_Rescuer1", (cx + 1000, cy + 470, 0), 30, "ClothBlue")
    person("Villager_Yard", (cx - 2600, cy + 1900, 0), 180, "ClothBrown")

    # the stick carrier: warm where the hand grips it, cold at both ends
    p, comp = person("Villager_Stick", (cx - 700, cy - 250, 0), 80, "ClothGreen")
    try:
        hand = comp.get_socket_location("hand_r")
        stick = spawn_mesh("WalkingStick", CYL, (hand.x, hand.y, hand.z - 25), (0.05, 0.05, 1.5), (0, 0, 0),
                           "Timber", 1, "Debris", "People", collision=False)
        rule = unreal.AttachmentRule.KEEP_WORLD
        stick.attach_to_component(comp, unreal.Name("hand_r"), rule, rule, rule, False)
        hotspot("WalkingStick_GripHeat", (hand.x, hand.y, hand.z), 12, 35, 1.3, attach=stick, folder="People",
                start_full=False, warm_up=5.0, cool_down=30.0)
    except Exception as e:
        unreal.log_warning("[Village] stick skipped: %s" % e)

    # car parked on the street, recently driven
    car("Car", cx + 2200, cy + 250, 180)

    # animals: a dog near the talkers, a cow in a pen behind the north houses
    quadruped("Dog", (cx - 900, cy + 30, 0), 140, (80, 30, 32), "Fur", 3, "Animal")
    pen = (cx + 2000, cy + 2300)
    fence("Pen_S", pen[0] - 500, pen[1] - 350, pen[0] + 500, pen[1] - 350)
    fence("Pen_N", pen[0] - 500, pen[1] + 350, pen[0] + 500, pen[1] + 350)
    fence("Pen_W", pen[0] - 500, pen[1] - 350, pen[0] - 500, pen[1] + 350)
    fence("Pen_E", pen[0] + 500, pen[1] - 350, pen[0] + 500, pen[1] + 350)
    quadruped("Cow", (pen[0] - 100, pen[1], 0), 20, (200, 70, 85), "CowHide", 3, "Animal")
    box("HayBale", (pen[0] + 300, pen[1] + 150, 45), (120, 80, 90), 15, "Hay", 1, "Debris", "Props")

    # trees, bushes, fences, barrels, crates
    for i, (x, y) in enumerate(((-3400, 3600), (-1000, 3700), (300, 3900), (3300, 3500), (-3500, 300),
                                (3500, -200), (-3300, -1900), (-500, -2300), (3200, -2200), (900, 4300))):
        tree("Tree%d" % i, cx + x, cy + y)
    for i in range(16):
        side = 1 if i % 2 else -1
        bush("Bush%d" % i, cx + random.uniform(-3300, 3300), cy + side * random.uniform(620, 700))
    fence("Fence_N", cx - 3300, cy + 1550, cx - 900, cy + 1550)
    fence("Fence_S", cx - 3300, cy - 1550, cx - 900, cy - 1550)
    for i, (x, y) in enumerate(((-2100, -560), (-2050, -620), (2050, 560), (-950, 560), (950, -560))):
        spawn_mesh("Barrel%d" % i, CYL, (cx + x, cy + y, 45), (0.6, 0.6, 0.9), (0, 0, 0), "Metal", 0, "ColdObject", "Props")
    for i, (x, y) in enumerate(((-1950, 600), (-1880, 640), (1100, -620))):
        box("Crate%d" % i, (cx + x, cy + y, 35), (70, 70, 70), random.uniform(0, 40), "Timber", 1, "Debris", "Props")
    # a hand cart near the well
    box("Cart_Bed", (cx - 250, cy + 450, 70), (220, 120, 15), 30, "Timber", 1, "Debris", "Props")
    for i, s in enumerate((-1, 1)):
        dx, dy = rot_xy(0, s * 68, 30)
        spawn_mesh("Cart_Wheel%d" % i, CYL, (cx - 250 + dx, cy + 450 + dy, 45), (0.9, 0.9, 0.08), (90, 0, 30),
                   "Timber", 1, "Debris", "Props")


def main():
    if not hasattr(unreal, "ThermalHotSpot"):
        unreal.log_error("[Village] ThermalSensor plugin is not loaded - compile it first.")
        return
    prepare_level()
    build_materials()
    with unreal.ScopedEditorTransaction("Build Thermal Village"):
        build_environment()
        build_village()
        place_camera()
        resize_thermo_volume()
    les.save_current_level()
    log("Done: %d meshes, %d people, %d heat spots. Map saved: %s" % (
        _count["actors"], _count["people"], _count["hotspots"], LEVEL))


if __name__ != "BuildThermalVillage":   # importing it as a helper module does not rebuild the old village
    main()
