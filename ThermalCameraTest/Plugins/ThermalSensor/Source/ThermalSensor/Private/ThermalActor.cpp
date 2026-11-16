#include "ThermalActor.h"

#include "ThermalBodyComponent.h"
#include "Components/StaticMeshComponent.h"

AThermalActor::AThermalActor()
{
	PrimaryActorTick.bCanEverTick = false;

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	Mesh = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Mesh"));
	Mesh->SetupAttachment(Root);
	Mesh->SetRenderCustomDepth(true);

	ThermalBody = CreateDefaultSubobject<UThermalBodyComponent>(TEXT("ThermalBody"));
}
