#include "ThermalBodyComponent.h"

#include "ThermoForgeSourceComponent.h"
#include "Components/PrimitiveComponent.h"
#include "GameFramework/Actor.h"
#include "Engine/World.h"

TArray<TWeakObjectPtr<UThermalBodyComponent>> UThermalBodyComponent::AllBodies;

UThermalBodyComponent::UThermalBodyComponent()
{
	PrimaryComponentTick.bCanEverTick = false;
}

float UThermalBodyComponent::HeatLevelToCelsius(int32 Level)
{
	// Degrees above ambient (~20-28 C air). See Docs/ThermalHeatValues.csv.
	switch (FMath::Clamp(Level, 0, 6))
	{
	case 0:  return -8.f;   // flood water, shaded metal
	case 1:  return 0.f;    // ground, rubble (ambient)
	case 2:  return 6.f;    // sun-warmed walls
	case 3:  return 10.f;   // animal fur, vehicle body, tires
	case 4:  return 16.f;   // human skin
	case 5:  return 60.f;   // engine hood, exhaust, embers
	default: return 400.f;  // open flame
	}
}

int32 UThermalBodyComponent::DefaultHeatLevelFor(EThermalObjectType Type)
{
	switch (Type)
	{
	case EThermalObjectType::Human:      return 4;
	case EThermalObjectType::Animal:     return 3;
	case EThermalObjectType::Vehicle:    return 3;
	case EThermalObjectType::Fire:       return 6;
	case EThermalObjectType::Building:   return 2;
	case EThermalObjectType::Ground:     return 1;
	case EThermalObjectType::Water:      return 0;
	case EThermalObjectType::ColdObject: return 0;
	default:                             return -1;
	}
}

int32 UThermalBodyComponent::ParseHeatTag() const
{
	if (const AActor* Owner = GetOwner())
	{
		for (const FName& Tag : Owner->Tags)
		{
			const FString S = Tag.ToString();
			if (S.StartsWith(TEXT("Heat_")))
			{
				const FString Num = S.RightChop(5);
				if (Num.IsNumeric())
				{
					return FMath::Clamp(FCString::Atoi(*Num), 0, 6);
				}
			}
		}
	}
	return -1;
}

int32 UThermalBodyComponent::GetEffectiveHeatLevel() const
{
	if (bReadHeatTag)
	{
		const int32 FromTag = ParseHeatTag();
		if (FromTag >= 0) return FromTag;
	}
	const int32 FromType = DefaultHeatLevelFor(ThermalType);
	if (FromType >= 0) return FromType;
	return FMath::Clamp(HeatLevel, 0, 6);
}

float UThermalBodyComponent::GetEffectiveIntensityCelsius() const
{
	return bOverrideIntensity ? IntensityCelsius : HeatLevelToCelsius(GetEffectiveHeatLevel());
}

void UThermalBodyComponent::SetHeatLevel(int32 NewLevel)
{
	HeatLevel = FMath::Clamp(NewLevel, 0, 6);
	bReadHeatTag = false;
	ThermalType = EThermalObjectType::Custom;
	bOverrideIntensity = false;
	ConfigureHeatSource();
}

FVector UThermalBodyComponent::GetSampleLocation() const
{
	const AActor* Owner = GetOwner();
	return Owner ? Owner->GetActorLocation() : FVector::ZeroVector;
}

void UThermalBodyComponent::BeginPlay()
{
	Super::BeginPlay();

	AllBodies.RemoveAll([](const TWeakObjectPtr<UThermalBodyComponent>& W) { return !W.IsValid(); });
	AllBodies.AddUnique(this);

	if (AActor* Owner = GetOwner())
	{
		TArray<UPrimitiveComponent*> Prims;
		Owner->GetComponents<UPrimitiveComponent>(Prims);
		for (UPrimitiveComponent* Prim : Prims)
		{
			if (Prim)
			{
				Prim->SetRenderCustomDepth(true);
			}
		}
	}

	SetupHeatSource();
}

void UThermalBodyComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	AllBodies.RemoveAll([this](const TWeakObjectPtr<UThermalBodyComponent>& W) { return !W.IsValid() || W.Get() == this; });
	Super::EndPlay(EndPlayReason);
}

void UThermalBodyComponent::SetupHeatSource()
{
	AActor* Owner = GetOwner();
	if (!Owner) return;

	HeatSource = Owner->FindComponentByClass<UThermoForgeSourceComponent>();
	if (HeatSource)
	{
		// The actor already has a hand-tuned ThermoForge source: respect it.
		return;
	}

	HeatSource = NewObject<UThermoForgeSourceComponent>(Owner, TEXT("ThermalBody_HeatSource"));
	ConfigureHeatSource();
	HeatSource->RegisterComponent();
	Owner->AddInstanceComponent(HeatSource);
}

void UThermalBodyComponent::ConfigureHeatSource()
{
	AActor* Owner = GetOwner();
	if (!Owner || !HeatSource) return;

	const float Intensity = GetEffectiveIntensityCelsius();
	HeatSource->IntensityCelsius = Intensity;
	HeatSource->bEnabled = !FMath::IsNearlyZero(Intensity);
	HeatSource->bAffectByOwnerScale = false;

	// Bounds of the actor's meshes in actor space (unscaled), which is the space
	// ThermoForge tests box sources in.
	const FBox LocalBox = Owner->CalculateComponentsBoundingBoxInLocalSpace(/*bNonColliding*/ true);
	FVector Extent(50.f);
	if (LocalBox.IsValid)
	{
		Extent = LocalBox.Min.GetAbs().ComponentMax(LocalBox.Max.GetAbs());
		Extent = Extent.ComponentMax(FVector(5.f));
	}

	const bool bIsFire = (ThermalType == EThermalObjectType::Fire) || GetEffectiveHeatLevel() >= 6;
	if (bIsFire)
	{
		// Fire radiates: a sphere that warms its surroundings.
		const float WorldRadius = (Extent * Owner->GetActorScale3D().GetAbs()).GetMax();
		HeatSource->Shape = EThermoSourceShape::Point;
		HeatSource->Falloff = EThermoSourceFalloff::Linear;
		HeatSource->RadiusCm = FMath::Max(WorldRadius * 3.f, 150.f);
		if (FlickerCelsius <= 0.f)
		{
			FlickerCelsius = 40.f;
		}
	}
	else
	{
		HeatSource->Shape = EThermoSourceShape::Box;
		HeatSource->BoxExtent = Extent;
	}
}

void UThermalBodyComponent::ApplyStencilValue(int32 Value)
{
	Value = FMath::Clamp(Value, 0, 255);
	if (Value == LastStencil) return;
	LastStencil = Value;

	if (AActor* Owner = GetOwner())
	{
		TArray<UPrimitiveComponent*> Prims;
		Owner->GetComponents<UPrimitiveComponent>(Prims);
		for (UPrimitiveComponent* Prim : Prims)
		{
			if (Prim)
			{
				Prim->SetRenderCustomDepth(true);
				Prim->SetCustomDepthStencilValue(Value);
			}
		}
	}
}

void UThermalBodyComponent::GetBodiesInWorld(const UWorld* World, TArray<UThermalBodyComponent*>& OutBodies)
{
	OutBodies.Reset();
	for (const TWeakObjectPtr<UThermalBodyComponent>& W : AllBodies)
	{
		UThermalBodyComponent* Body = W.Get();
		if (Body && Body->GetWorld() == World)
		{
			OutBodies.Add(Body);
		}
	}
}
