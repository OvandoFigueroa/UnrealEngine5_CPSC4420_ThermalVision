#include "ThermalHotSpotComponent.h"

#include "ThermalSensorSubsystem.h"
#include "Engine/World.h"

UThermalHotSpotComponent::UThermalHotSpotComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
}

void UThermalHotSpotComponent::BeginPlay()
{
	Super::BeginPlay();
	CurrentIntensityCelsius = (bHeating && bStartAtFullHeat) ? IntensityCelsius : 0.f;
	if (UThermalSensorSubsystem* Sub = UThermalSensorSubsystem::Get(this))
	{
		Sub->RegisterHotSpot(this);
	}
}

void UThermalHotSpotComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (UThermalSensorSubsystem* Sub = UThermalSensorSubsystem::Get(this))
	{
		Sub->UnregisterHotSpot(this);
	}
	Super::EndPlay(EndPlayReason);
}

void UThermalHotSpotComponent::SetHeating(bool bNewHeating)
{
	bHeating = bNewHeating;
}

void UThermalHotSpotComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	// First-order (Newtonian) heating / cooling toward the target temperature.
	const float Target = bHeating ? IntensityCelsius : 0.f;
	const float Tau = bHeating ? WarmUpSeconds : CoolDownSeconds;
	if (Tau <= KINDA_SMALL_NUMBER)
	{
		CurrentIntensityCelsius = Target;
	}
	else
	{
		const float Alpha = 1.f - FMath::Exp(-DeltaTime / Tau);
		CurrentIntensityCelsius = FMath::Lerp(CurrentIntensityCelsius, Target, Alpha);
	}
}

AThermalHotSpot::AThermalHotSpot()
{
	PrimaryActorTick.bCanEverTick = false;
	HotSpot = CreateDefaultSubobject<UThermalHotSpotComponent>(TEXT("HotSpot"));
	RootComponent = HotSpot;
}
