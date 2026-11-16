#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "ThermalSensorSubsystem.generated.h"

class UThermalHotSpotComponent;
class USceneComponent;

/** One localized heat point the thermal shader evaluates per pixel. */
USTRUCT(BlueprintType)
struct FThermalHeatPoint
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadWrite, Category="Thermal")
	FVector Location = FVector::ZeroVector;

	/** °C above (+) or below (-) ambient at the center. */
	UPROPERTY(BlueprintReadWrite, Category="Thermal")
	float IntensityCelsius = 0.f;

	UPROPERTY(BlueprintReadWrite, Category="Thermal")
	float RadiusCm = 25.f;

	UPROPERTY(BlueprintReadWrite, Category="Thermal")
	float FalloffExponent = 1.f;
};

/** A heat print left behind by contact (e.g. a hand that let go of a stick or touched a wall). */
USTRUCT()
struct FThermalHeatPrint
{
	GENERATED_BODY()

	TWeakObjectPtr<USceneComponent> AttachTo;
	bool bAttached = false;
	FVector Location = FVector::ZeroVector;   // component space if attached, else world
	float IntensityCelsius = 10.f;
	float RadiusCm = 12.f;
	float FalloffExponent = 1.5f;
	double StartTime = 0.0;
	float CoolDownSeconds = 30.f;
};

/** Keeps track of localized heat (hot spots, heat prints, ThermoForge point sources) for thermal sensors. */
UCLASS()
class THERMALSENSOR_API UThermalSensorSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	static UThermalSensorSubsystem* Get(const UObject* WorldContext);

	void RegisterHotSpot(UThermalHotSpotComponent* HotSpot);
	void UnregisterHotSpot(UThermalHotSpotComponent* HotSpot);

	/**
	 * Leave a fading heat print where something warm touched a surface.
	 * Pass AttachTo (e.g. the stick's mesh) so the print moves with the object.
	 */
	UFUNCTION(BlueprintCallable, Category="Thermal", meta=(AdvancedDisplay="RadiusCm,CoolDownSeconds"))
	void AddHeatPrint(FVector WorldLocation, USceneComponent* AttachTo, float IntensityCelsius = 10.f,
		float RadiusCm = 12.f, float CoolDownSeconds = 30.f);

	/** All localized heat points currently in the world. */
	UFUNCTION(BlueprintCallable, Category="Thermal")
	void GatherHeatPoints(TArray<FThermalHeatPoint>& OutPoints, bool bIncludeThermoForgePointSources = true);

private:
	TArray<TWeakObjectPtr<UThermalHotSpotComponent>> HotSpots;
	TArray<FThermalHeatPrint> Prints;
};
