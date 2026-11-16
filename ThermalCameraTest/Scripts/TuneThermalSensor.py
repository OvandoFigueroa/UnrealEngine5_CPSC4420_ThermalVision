"""Set the thermal camera's display range on BP_ThermalCamera's ThermalSensor component (auto-gain like a real camera)."""
import unreal

SETTINGS = {
    "range_below_ambient_c": 8.0,    # coldest shown = ambient - 8 C (water, shaded metal, sky go black)
    "range_above_ambient_c": 28.0,   # hottest shown = ambient + 28 C (skin is bright, engines/fire saturate)
    "display_gamma": 0.85,
    "detail_amount": 0.06,
    "noise_amount": 0.02,
}

bp = unreal.load_asset("/Game/SimBlank/Blueprints/BP_ThermalCamera")
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
lib = unreal.SubobjectDataBlueprintFunctionLibrary
done = False
for h in sds.k2_gather_subobject_data_for_blueprint(bp):
    data = lib.get_data(h)
    obj = lib.get_object(data)
    if obj is not None and isinstance(obj, unreal.ThermalSensorComponent):
        for k, v in SETTINGS.items():
            obj.set_editor_property(k, v)
        done = True
unreal.BlueprintEditorLibrary.compile_blueprint(bp)
unreal.EditorAssetLibrary.save_loaded_asset(bp)
unreal.log("[ThermalTune] %s" % ("updated ThermalSensor settings" if done else "ThermalSensor component not found"))
