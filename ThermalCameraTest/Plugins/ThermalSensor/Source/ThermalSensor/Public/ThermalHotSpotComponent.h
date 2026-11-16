#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "GameFramework/Actor.h"
#include "ThermalHotSpotComponent.generated.h"

/**
 * A spot of heat that is rendered per pixel by the thermal camera, fading out with distance.
 *
 * Use it for anything that is hot in one place and cool elsewhere:
 *  - a hand gripping a stick (attach to the hand socket or to the stick at the grip):
 *    the stick is warm at the grip and cold at both ends
 *  - an engine block, exhaust pipe, a face, a radiator, a hot pipe joint
 *
 * Heat builds up over WarmUpSeconds while heating and fades over CoolDownSeconds after
 * SetHeating(false), the way real objects warm up and cool down. A spot never makes a
 * surface hotter than its own temperature (contact heat can't exceed the hand's temperature).
 * Negative intensity makes a cold spot (ice, evaporating water).
 */
UCLASS(ClassGroup=(Thermal), BlueprintType, Blueprintable, meta=(BlueprintSpawnableComponent, DisplayName="Thermal Hot Spot"))
class THERMALSENSOR_API UThermalHotSpotComponent : public USceneComponent
{
	GENERATED_BODY()

public:
	UThermalHotSpotComponent();

	/** Temperature at the center of the spot, °C above ambient (skin contact ~ +12, engine ~ +60). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot")
	float IntensityCelsius = 12.f;

	/** Distance at which the heat has faded to ambient (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot", meta=(ClampMin="1"))
	float RadiusCm = 25.f;

	/** Shape of the fade: 1 = linear, >1 = concentrated near the center, <1 = broad. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot", meta=(ClampMin="0.1", ClampMax="8"))
	float FalloffExponent = 1.5f;

	/** Is the spot currently being heated (hand gripping, engine running)? */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Hot Spot")
	bool bHeating = true;

	/** Start at full temperature instead of warming up from ambient. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot")
	bool bStartAtFullHeat = true;

	/** Time to reach ~63% of full heat while heating (s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot", meta=(ClampMin="0"))
	float WarmUpSeconds = 4.f;

	/** Time to lose ~63% of the heat after heating stops (s). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Hot Spot", meta=(ClampMin="0"))
	float CoolDownSeconds = 25.f;

	/** Current temperature above ambient at the center (°C). */
	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal Hot Spot")
	float CurrentIntensityCelsius = 0.f;

	/** Start or stop heating (e.g. grab / release). */
	UFUNCTION(BlueprintCallable, Category="Thermal Hot Spot")
	void SetHeating(bool bNewHeating);

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
};

/** Placeable hot spot (drop it in the level or attach it to an object, e.g. at a hand grip). */
UCLASS(Blueprintable, BlueprintType)
class THERMALSENSOR_API AThermalHotSpot : public AActor
{
	GENERATED_BODY()

public:
	AThermalHotSpot();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Thermal")
	TObjectPtr<UThermalHotSpotComponent> HotSpot;
};
