#include "ThermalSensorSubsystem.h"

#include "ThermalBodyComponent.h"
#include "ThermalHotSpotComponent.h"
#include "ThermoForgeSourceComponent.h"
#include "ThermoForgeSubsystem.h"

#include "Components/SceneComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"

UThermalSensorSubsystem* UThermalSensorSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = GEngine ? GEngine->GetWorldFromContextObject(WorldContext, EGetWorldErrorMode::ReturnNull) : nullptr;
	return World ? World->GetSubsystem<UThermalSensorSubsystem>() : nullptr;
}

void UThermalSensorSubsystem::RegisterHotSpot(UThermalHotSpotComponent* HotSpot)
{
	HotSpots.RemoveAll([](const TWeakObjectPtr<UThermalHotSpotComponent>& W) { return !W.IsValid(); });
	HotSpots.AddUnique(HotSpot);
}

void UThermalSensorSubsystem::UnregisterHotSpot(UThermalHotSpotComponent* HotSpot)
{
	HotSpots.RemoveAll([HotSpot](const TWeakObjectPtr<UThermalHotSpotComponent>& W) { return !W.IsValid() || W.Get() == HotSpot; });
}

void UThermalSensorSubsystem::AddHeatPrint(FVector WorldLocation, USceneComponent* AttachTo, float IntensityCelsius,
	float RadiusCm, float CoolDownSeconds)
{
	FThermalHeatPrint Print;
	Print.IntensityCelsius = IntensityCelsius;
	Print.RadiusCm = FMath::Max(RadiusCm, 1.f);
	Print.CoolDownSeconds = FMath::Max(CoolDownSeconds, 0.1f);
	Print.StartTime = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0;
	if (AttachTo)
	{
		Print.AttachTo = AttachTo;
		Print.bAttached = true;
		Print.Location = AttachTo->GetComponentTransform().InverseTransformPosition(WorldLocation);
	}
	else
	{
		Print.Location = WorldLocation;
	}
	Prints.Add(Print);
}

static float TF_FalloffToExponent(EThermoSourceFalloff Falloff)
{
	switch (Falloff)
	{
	case EThermoSourceFalloff::None:          return 0.1f;  // nearly flat out to the radius
	case EThermoSourceFalloff::InverseSquare: return 2.f;
	default:                                  return 1.f;
	}
}

void UThermalSensorSubsystem::GatherHeatPoints(TArray<FThermalHeatPoint>& OutPoints, bool bIncludeThermoForgePointSources)
{
	OutPoints.Reset();
	const UWorld* World = GetWorld();
	const double Now = World ? World->GetTimeSeconds() : 0.0;

	// Hot spots (hands, faces, engines, ...)
	HotSpots.RemoveAll([](const TWeakObjectPtr<UThermalHotSpotComponent>& W) { return !W.IsValid(); });
	for (const TWeakObjectPtr<UThermalHotSpotComponent>& W : HotSpots)
	{
		const UThermalHotSpotComponent* Spot = W.Get();
		if (!Spot || FMath::Abs(Spot->CurrentIntensityCelsius) < 0.05f) continue;
		FThermalHeatPoint& P = OutPoints.AddDefaulted_GetRef();
		P.Location = Spot->GetComponentLocation();
		P.IntensityCelsius = Spot->CurrentIntensityCelsius;
		P.RadiusCm = Spot->RadiusCm;
		P.FalloffExponent = Spot->FalloffExponent;
	}

	// Heat prints cool off exponentially and are dropped once they are gone.
	Prints.RemoveAll([Now](const FThermalHeatPrint& Pr)
	{
		const float Age = static_cast<float>(Now - Pr.StartTime);
		return (Pr.bAttached && !Pr.AttachTo.IsValid()) || Age > Pr.CoolDownSeconds * 5.f;
	});
	for (const FThermalHeatPrint& Pr : Prints)
	{
		const float Age = static_cast<float>(Now - Pr.StartTime);
		const float Intensity = Pr.IntensityCelsius * FMath::Exp(-Age / Pr.CoolDownSeconds);
		if (FMath::Abs(Intensity) < 0.05f) continue;
		FThermalHeatPoint& P = OutPoints.AddDefaulted_GetRef();
		P.Location = Pr.bAttached ? Pr.AttachTo->GetComponentTransform().TransformPosition(Pr.Location) : Pr.Location;
		P.IntensityCelsius = Intensity;
		P.RadiusCm = Pr.RadiusCm;
		P.FalloffExponent = Pr.FalloffExponent;
	}

	// ThermoForge point sources (fires etc.) radiate onto nearby surfaces.
	if (bIncludeThermoForgePointSources && World)
	{
		if (UThermoForgeSubsystem* Thermo = World->GetSubsystem<UThermoForgeSubsystem>())
		{
			TArray<UThermoForgeSourceComponent*> Sources;
			Thermo->GetAllSources(Sources);
			for (const UThermoForgeSourceComponent* Src : Sources)
			{
				if (!Src || !Src->bEnabled || Src->Shape != EThermoSourceShape::Point) continue;
				const AActor* Owner = Src->GetOwner();
				float Intensity = Src->IntensityCelsius;
				if (const UThermalBodyComponent* Body = Owner ? Owner->FindComponentByClass<UThermalBodyComponent>() : nullptr)
				{
					if (Body->FlickerCelsius > 0.f)
					{
						Intensity += FMath::FRandRange(-0.5f, 0.5f) * Body->FlickerCelsius;
					}
				}
				const float Scale = (Src->bAffectByOwnerScale && Owner) ? Owner->GetActorScale3D().GetMax() : 1.f;
				FThermalHeatPoint& P = OutPoints.AddDefaulted_GetRef();
				P.Location = Src->GetOwnerLocationSafe();
				P.IntensityCelsius = Intensity;
				P.RadiusCm = Src->RadiusCm * Scale;
				P.FalloffExponent = TF_FalloffToExponent(Src->Falloff);
			}
		}
	}
}
