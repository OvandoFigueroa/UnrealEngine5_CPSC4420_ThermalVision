#pragma once

#include "CoreMinimal.h"
#include "ThermalSensorTypes.generated.h"

/** What kind of object a thermal body is. Picks a default heat level (team 0-6 scale). */
UENUM(BlueprintType)
enum class EThermalObjectType : uint8
{
	Custom      UMETA(DisplayName="Custom (use Heat Level)"),
	Human       UMETA(DisplayName="Human"),
	Animal      UMETA(DisplayName="Animal"),
	Vehicle     UMETA(DisplayName="Vehicle"),
	Fire        UMETA(DisplayName="Fire"),
	Building    UMETA(DisplayName="Building / Wall"),
	Ground      UMETA(DisplayName="Ground / Background"),
	Water       UMETA(DisplayName="Water"),
	ColdObject  UMETA(DisplayName="Cold Object")
};

/** How the thermal image is colored. */
UENUM(BlueprintType)
enum class EThermalDisplayMode : uint8
{
	WhiteHot          UMETA(DisplayName="White Hot"),
	BlackHot          UMETA(DisplayName="Black Hot"),
	Ironbow           UMETA(DisplayName="False Color (Ironbow)"),
	ThermoForgeField  UMETA(DisplayName="ThermoForge Heat Field (experimental)")
};
