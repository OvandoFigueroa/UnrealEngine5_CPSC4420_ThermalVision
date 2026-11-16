"""
Team 3 - ThermoForge thermal camera setup (run once after the plugins compile).

Creates / updates:
  /Game/ThermalSensor/M_ThermalSensorPP           thermal post-process material (white-hot / black-hot / ironbow)
  /Game/ThermalSensor/Actors/BP_Thermal_<Type>    the six thermal actor types (Team 5's deliverable)
  BP_ThermalCamera                                gets a "ThermalSensor" component
  CameraTest1                                     gets a ThermoForge volume around the test area

Run: Tools > Execute Python Script... (or the console: py "<path>/SetupThermoForge.py")
Safe to re-run.
"""

import unreal

MAT_DIR = "/Game/ThermalSensor"
MAT_NAME = "M_ThermalSensorPP"
ACTOR_DIR = "/Game/ThermalSensor/Actors"
CAMERA_BP = "/Game/SimBlank/Blueprints/BP_ThermalCamera"
LEVEL = "/Game/CameraTest1"

MEL = unreal.MaterialEditingLibrary
EAL = unreal.EditorAssetLibrary
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()


def log(msg):
    unreal.log("[ThermalSetup] " + str(msg))


def warn(msg):
    unreal.log_warning("[ThermalSetup] " + str(msg))


# ---------------------------------------------------------------------------
# 1. Thermal post-process material
# ---------------------------------------------------------------------------
HLSL = r"""
// ---- 1. base temperature of the surface (degrees C) ----
float s = Stencil.r;
float d = Depth.r;
if (DebugView > 0.5) return float3(saturate(s / 64.0), (s > 0.5) ? 1.0 : 0.0, saturate(d / 5000.0));
float T;
if (s > 0.5)            T = TMin + (s - 1.0) / 254.0 * TRange;  // thermal body (written by the sensor)
else if (d > SkyDepth)  T = SkyC;                                // open sky reads cold
else                    T = AmbientC;                            // untagged geometry = ambient

// ---- 2. localized heat, evaluated per pixel ----
// Hand on a stick, face, engine block, fire radiating onto the ground, fading heat prints...
// Each point pulls nearby surfaces toward (ambient + intensity * falloff), never past it.
float3 P = WorldPos.xyz - HeatOrigin.xyz;
int N = (int)NumSources;
float W = max(SourceTexWidth, 1.0);
[loop]
for (int i = 0; i < 64; ++i)
{
    if (i >= N) break;
    float u = (i + 0.5) / W;
    float4 a = Texture2DSampleLevel(HeatSources, HeatSourcesSampler, float2(u, 0.25), 0);
    float4 b = Texture2DSampleLevel(HeatSources, HeatSourcesSampler, float2(u, 0.75), 0);
    float dist = distance(P, a.xyz);
    float w = pow(saturate(1.0 - dist / max(b.x, 1.0)), max(b.z, 0.1));
    if (w > 0.0)
    {
        float target = AmbientC + b.y * w;
        T = (b.y >= 0.0) ? max(T, target) : min(T, target);
    }
}

// ---- 3. temperature -> brightness ----
float v = pow(saturate((T - TMin) / max(TRange, 0.001)), max(Gamma, 0.05));

// a little surface shading + sensor noise so it reads like a real thermal camera
float lum = dot(Scene.rgb, float3(0.299, 0.587, 0.114));
v = saturate(v + Detail * (lum - 0.5));
float2 p = UV.xy * 1000.0 + frac(TimeSec * 7.0) * 37.0;
float n = frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453);
v = saturate(v + Noise * (n - 0.5));

// ---- 4. palette ----
float3 c;
if (Mode < 0.5) {
    c = float3(v, v, v);                         // white hot
} else if (Mode < 1.5) {
    c = float3(1.0 - v, 1.0 - v, 1.0 - v);       // black hot
} else {                                         // ironbow false color
    float3 k0 = float3(0.00, 0.00, 0.00);
    float3 k1 = float3(0.12, 0.00, 0.45);
    float3 k2 = float3(0.55, 0.00, 0.60);
    float3 k3 = float3(0.90, 0.25, 0.05);
    float3 k4 = float3(1.00, 0.70, 0.00);
    float3 k5 = float3(1.00, 1.00, 0.85);
    float x = v * 5.0;
    if (x < 1.0)      c = lerp(k0, k1, x);
    else if (x < 2.0) c = lerp(k1, k2, x - 1.0);
    else if (x < 3.0) c = lerp(k2, k3, x - 2.0);
    else if (x < 4.0) c = lerp(k3, k4, x - 3.0);
    else              c = lerp(k4, k5, saturate(x - 4.0));
}
// The capture's render target is shown with an sRGB curve, so pre-compensate to keep the
// brightness proportional to temperature (set OutputGamma to 1 to disable).
return pow(saturate(c), max(OutputGamma, 0.1));
"""


def scene_texture(mat, tex_id, x, y):
    e = MEL.create_material_expression(mat, unreal.MaterialExpressionSceneTexture, x, y)
    e.set_editor_property("scene_texture_id", tex_id)
    return e


def scalar(mat, name, default, x, y):
    e = MEL.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property("parameter_name", name)
    e.set_editor_property("default_value", default)
    return e


def build_material():
    path = MAT_DIR + "/" + MAT_NAME
    if EAL.does_asset_exist(path):
        mat = unreal.load_asset(path)
        MEL.delete_all_material_expressions(mat)
    else:
        EAL.make_directory(MAT_DIR)
        mat = asset_tools.create_asset(MAT_NAME, MAT_DIR, unreal.Material, unreal.MaterialFactoryNew())

    mat.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    for name in ("BL_SCENE_COLOR_AFTER_TONEMAPPING", "BL_AFTER_TONEMAPPING"):
        loc = getattr(unreal.BlendableLocation, name, None)
        if loc is not None:
            mat.set_editor_property("blendable_location", loc)
            break

    sid = unreal.SceneTextureId
    stencil = scene_texture(mat, sid.PPI_CUSTOM_STENCIL, -1100, -400)
    depth = scene_texture(mat, sid.PPI_SCENE_DEPTH, -1100, -250)
    scene = scene_texture(mat, sid.PPI_POST_PROCESS_INPUT0, -1100, -100)
    uv = MEL.create_material_expression(mat, unreal.MaterialExpressionScreenPosition, -1100, 50)
    time = MEL.create_material_expression(mat, unreal.MaterialExpressionTime, -1100, 150)
    world_pos = MEL.create_material_expression(mat, unreal.MaterialExpressionWorldPosition, -1100, 250)

    heat_tex = MEL.create_material_expression(mat, unreal.MaterialExpressionTextureObjectParameter, -1100, 350)
    heat_tex.set_editor_property("parameter_name", "HeatSources")
    black = unreal.load_asset("/Engine/EngineResources/Black")
    if black:
        heat_tex.set_editor_property("texture", black)

    origin = MEL.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, -1100, 500)
    origin.set_editor_property("parameter_name", "HeatOrigin")
    origin.set_editor_property("default_value", unreal.LinearColor(0, 0, 0, 0))

    params = [("Mode", 0.0), ("AmbientC", 22.0), ("SkyC", 5.0), ("TMin", 7.0), ("TRange", 90.0),
              ("Gamma", 0.5), ("Detail", 0.08), ("Noise", 0.02), ("SkyDepth", 50000.0),
              ("NumSources", 0.0), ("SourceTexWidth", 64.0), ("DebugView", 0.0), ("OutputGamma", 2.2)]
    param_nodes = {n: scalar(mat, n, v, -1100, 650 + 90 * i) for i, (n, v) in enumerate(params)}

    custom = MEL.create_material_expression(mat, unreal.MaterialExpressionCustom, -400, 0)
    custom.set_editor_property("code", HLSL)
    custom.set_editor_property("output_type", unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    custom.set_editor_property("description", "ThermalImage")
    input_names = (["Stencil", "Depth", "Scene", "UV", "TimeSec", "WorldPos", "HeatSources", "HeatOrigin"]
                   + [n for n, _ in params])
    inputs = []
    for n in input_names:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", n)
        inputs.append(ci)
    custom.set_editor_property("inputs", inputs)

    MEL.connect_material_expressions(stencil, "Color", custom, "Stencil")
    MEL.connect_material_expressions(depth, "Color", custom, "Depth")
    MEL.connect_material_expressions(scene, "Color", custom, "Scene")
    MEL.connect_material_expressions(uv, "ViewportUV", custom, "UV")
    MEL.connect_material_expressions(time, "", custom, "TimeSec")
    MEL.connect_material_expressions(world_pos, "", custom, "WorldPos")
    MEL.connect_material_expressions(heat_tex, "", custom, "HeatSources")
    MEL.connect_material_expressions(origin, "", custom, "HeatOrigin")
    for n, node in param_nodes.items():
        MEL.connect_material_expressions(node, "", custom, n)
    MEL.connect_material_property(custom, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)

    MEL.recompile_material(mat)
    EAL.save_loaded_asset(mat)
    log("material ready: " + path)


# ---------------------------------------------------------------------------
# 2. Six thermal actor Blueprints (Team 5's actor types)
# ---------------------------------------------------------------------------
# name, type enum name, placeholder mesh, mesh scale, mesh offset (pivot at the feet)
ACTOR_TYPES = [
    ("Human",    "HUMAN",    "/Engine/BasicShapes/Cylinder", (0.45, 0.35, 1.75), (0, 0, 87.5)),
    ("Animal",   "ANIMAL",   "/Engine/BasicShapes/Cube",     (0.80, 0.30, 0.45), (0, 0, 40)),
    ("Vehicle",  "VEHICLE",  "/Engine/BasicShapes/Cube",     (4.50, 1.80, 1.40), (0, 0, 70)),
    ("Fire",     "FIRE",     "/Engine/BasicShapes/Cone",     (0.80, 0.80, 1.20), (0, 0, 60)),
    ("Building", "BUILDING", "/Engine/BasicShapes/Cube",     (0.40, 6.00, 3.50), (0, 0, 175)),
    ("Ground",   "GROUND",   "/Engine/BasicShapes/Cube",     (10.0, 10.0, 0.10), (0, 0, 5)),
]


def build_actor_blueprints():
    if not hasattr(unreal, "ThermalActor"):
        warn("ThermalActor class not found - is the ThermalSensor plugin compiled and enabled?")
        return
    EAL.make_directory(ACTOR_DIR)
    for name, type_name, mesh_path, scale, offset in ACTOR_TYPES:
        bp_name = "BP_Thermal_" + name
        path = ACTOR_DIR + "/" + bp_name
        if EAL.does_asset_exist(path):
            bp = unreal.load_asset(path)
        else:
            factory = unreal.BlueprintFactory()
            factory.set_editor_property("parent_class", unreal.ThermalActor)
            bp = asset_tools.create_asset(bp_name, ACTOR_DIR, unreal.Blueprint, factory)
        cdo = unreal.get_default_object(bp.generated_class())
        body = cdo.get_editor_property("thermal_body")
        body.set_editor_property("thermal_type", getattr(unreal.ThermalObjectType, type_name))
        mesh = cdo.get_editor_property("mesh")
        mesh.set_editor_property("static_mesh", unreal.load_asset(mesh_path))
        mesh.set_editor_property("relative_scale3d", unreal.Vector(*scale))
        mesh.set_editor_property("relative_location", unreal.Vector(*offset))
        unreal.BlueprintEditorLibrary.compile_blueprint(bp)
        EAL.save_loaded_asset(bp)
        log("actor type ready: " + path)


# ---------------------------------------------------------------------------
# 3. Thermal Sensor component on BP_ThermalCamera
# ---------------------------------------------------------------------------
def add_sensor_to_camera():
    if not hasattr(unreal, "ThermalSensorComponent"):
        warn("ThermalSensorComponent not found - is the ThermalSensor plugin compiled?")
        return
    bp = unreal.load_asset(CAMERA_BP)
    if bp is None:
        warn("BP_ThermalCamera not found at " + CAMERA_BP)
        return
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    lib = unreal.SubobjectDataBlueprintFunctionLibrary
    handles = sds.k2_gather_subobject_data_for_blueprint(bp)
    for h in handles:
        obj = lib.get_object(lib.get_data(h))
        if obj is not None and isinstance(obj, unreal.ThermalSensorComponent):
            log("BP_ThermalCamera already has a ThermalSensor component")
            return
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0],
                                          new_class=unreal.ThermalSensorComponent,
                                          blueprint_context=bp)
    result = sds.add_new_subobject(params)
    new_handle = result[0] if isinstance(result, tuple) else result
    try:
        sds.rename_subobject(new_handle, unreal.Text("ThermalSensor"))
    except Exception as e:
        warn("rename skipped: %s" % e)
    unreal.BlueprintEditorLibrary.compile_blueprint(bp)
    EAL.save_loaded_asset(bp)
    log("added ThermalSensor component to BP_ThermalCamera")


# ---------------------------------------------------------------------------
# 4. ThermoForge volume around the test area
# ---------------------------------------------------------------------------
def add_thermo_volume():
    if not hasattr(unreal, "ThermoForgeVolume"):
        warn("ThermoForgeVolume class not found - is ThermoForge compiled?")
        return
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    les.load_level(LEVEL)
    actors = eas.get_all_level_actors()
    if any(a.get_class().get_name() == "ThermoForgeVolume" for a in actors):
        log("level already has a ThermoForge volume")
        return
    cam = next((a for a in actors if "BP_ThermalCamera" in a.get_class().get_name()), None)
    center = unreal.Vector(0, 0, 300)
    if cam:
        loc = cam.get_actor_location()
        fwd = cam.get_actor_forward_vector()
        center = unreal.Vector(loc.x + fwd.x * 1000, loc.y + fwd.y * 1000, 300)
    vol = eas.spawn_actor_from_class(unreal.ThermoForgeVolume, center, unreal.Rotator())
    vol.set_actor_label("ThermoForgeVolume_TestArea")
    vol.set_editor_property("box_extent", unreal.Vector(2000, 2000, 600))
    vol.set_folder_path(unreal.Name("ThermoForge"))
    les.save_current_level()
    log("added ThermoForge volume (bake it from Tools > Thermo Forge > Kickstart Sampling)")


def main():
    for step in (build_material, build_actor_blueprints, add_sensor_to_camera, add_thermo_volume):
        try:
            step()
        except Exception as e:
            unreal.log_error("[ThermalSetup] %s failed: %s" % (step.__name__, e))
    log("Setup finished.")


main()
