using UnrealBuildTool;

public class ThermalSensor : ModuleRules
{
	public ThermalSensor(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"ThermoForge"
		});
	}
}
