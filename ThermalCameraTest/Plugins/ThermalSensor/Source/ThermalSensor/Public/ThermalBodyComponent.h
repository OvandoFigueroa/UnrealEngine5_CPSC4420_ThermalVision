#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "ThermalSensorTypes.h"
#include "ThermalBodyComponent.generated.h"

class UThermoForgeSourceComponent;

/**
 * Makes an actor show up on the thermal camera.
 *
 * On BeginPlay it gives the actor a ThermoForge heat source (box around the actor's
 * meshes, or a falloff sphere for fire) using the team's 0-6 heat scale, and turns on
 * Custom Depth so the thermal sensor can paint the object with its temperature.
 *
 * Heat level priority: actor tag "Heat_N" (if bReadHeatTag) > Thermal Type default > Heat Level.
 * Set bOverrideIntensity to type an exact temperature offset in °C instead.
 */
UCLASS(ClassGroup=(Thermal), BlueprintType, Blueprintable, meta=(BlueprintSpawnableComponent, DisplayName="Thermal Body"))
class THERMALSENSOR_API UThermalBodyComponent : public UActorComponent
{
	GENERATED_BODY()

public:
	UThermalBodyComponent();

	/** What this object is. Anything but Custom picks the default heat level for that type. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal")
	EThermalObjectType ThermalType = EThermalObjectType::Custom;

	/** Team heat scale: 0 cold (water) .. 1 ambient .. 4 human .. 6 fire. Used when Thermal Type is Custom. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal", meta=(ClampMin="0", ClampMax="6", UIMin="0", UIMax="6"))
	int32 HeatLevel = 4;

	/** If the actor has a tag like "Heat_5", use that number (lets level designers tag objects). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal")
	bool bReadHeatTag = true;

	/** Use IntensityCelsius directly instead of the 0-6 scale. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal|Advanced")
	bool bOverrideIntensity = false;

	/** Degrees °C above (+) or below (-) the surrounding air at the center of the object. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal|Advanced", meta=(EditCondition="bOverrideIntensity"))
	float IntensityCelsius = 16.f;

	/** Random temperature flicker (°C), e.g. for flames. 0 = steady. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal|Advanced", meta=(ClampMin="0"))
	float FlickerCelsius = 0.f;

	/** Temperature the sensor last measured for this object (°C). */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Category="Thermal|Runtime")
	float CurrentTemperatureC = 0.f;

	/** The ThermoForge source this body uses (created at BeginPlay if the actor has none). */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal|Runtime")
	TObjectPtr<UThermoForgeSourceComponent> HeatSource;

	/** Final heat level after tags/type are applied (0-6). */
	UFUNCTION(BlueprintPure, Category="Thermal")
	int32 GetEffectiveHeatLevel() const;

	/** °C offset this body adds on top of ambient. */
	UFUNCTION(BlueprintPure, Category="Thermal")
	float GetEffectiveIntensityCelsius() const;

	/** Change heat at runtime (e.g. a fire being put out). Updates the ThermoForge source. */
	UFUNCTION(BlueprintCallable, Category="Thermal")
	void SetHeatLevel(int32 NewLevel);

	/** 0-6 scale -> °C above ambient. */
	UFUNCTION(BlueprintPure, Category="Thermal")
	static float HeatLevelToCelsius(int32 Level);

	/** Default 0-6 level for an object type. */
	UFUNCTION(BlueprintPure, Category="Thermal")
	static int32 DefaultHeatLevelFor(EThermalObjectType Type);

	/** Called by the thermal sensor: writes the display value into Custom Depth Stencil. */
	void ApplyStencilValue(int32 Value);

	/** Point the sensor samples the temperature at. */
	FVector GetSampleLocation() const;

	/** All thermal bodies alive in a world. */
	static void GetBodiesInWorld(const UWorld* World, TArray<UThermalBodyComponent*>& OutBodies);

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void SetupHeatSource();
	void ConfigureHeatSource();
	int32 ParseHeatTag() const;

	int32 LastStencil = -1;

	static TArray<TWeakObjectPtr<UThermalBodyComponent>> AllBodies;
};
