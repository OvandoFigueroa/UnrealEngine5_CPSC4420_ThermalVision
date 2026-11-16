#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ThermalSensorTypes.h"
#include "ThermalActor.generated.h"

class UStaticMeshComponent;
class UThermalBodyComponent;

/**
 * Ready-made heat object (Team 5's thermal actor types): a mesh plus a Thermal Body.
 * The BP_Thermal_* Blueprints are children of this class with the type and a
 * placeholder mesh filled in. Swap the mesh for a real model any time.
 */
UCLASS(Blueprintable, BlueprintType)
class THERMALSENSOR_API AThermalActor : public AActor
{
	GENERATED_BODY()

public:
	AThermalActor();

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Thermal")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Thermal")
	TObjectPtr<UStaticMeshComponent> Mesh;

	UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Thermal")
	TObjectPtr<UThermalBodyComponent> ThermalBody;
};
