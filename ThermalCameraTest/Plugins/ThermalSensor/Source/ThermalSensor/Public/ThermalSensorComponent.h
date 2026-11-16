#pragma once

#include "CoreMinimal.h"
#include "Components/SceneComponent.h"
#include "ThermalSensorTypes.h"
#include "ThermalSensorComponent.generated.h"

class USceneCaptureComponent2D;
class UTextureRenderTarget2D;
class UMaterialInterface;
class UMaterialInstanceDynamic;
class UThermoForgeSubsystem;
class UTexture2D;

/**
 * Reusable thermal camera sensor. Attach it to any actor (drone, rover, stationary camera).
 *
 * - If the actor already has scene captures named ThermalCaptureName / RGBCaptureName
 *   (like BP_ThermalCamera), the sensor drives those.
 * - Otherwise it creates its own RGB + thermal captures at this component's location,
 *   so both images always come from the same position.
 *
 * Every update it asks ThermoForge for the temperature of each Thermal Body in the world,
 * converts it to a display value and writes it to Custom Depth Stencil. The thermal
 * post-process material turns that into a white-hot / black-hot / ironbow image.
 * Objects without a Thermal Body read as ambient, the sky reads as cold.
 *
 * Any actor tagged "Heat_0".."Heat_6" automatically gets a Thermal Body.
 */
UCLASS(ClassGroup=(Thermal), BlueprintType, Blueprintable, meta=(BlueprintSpawnableComponent, DisplayName="Thermal Sensor"))
class THERMALSENSOR_API UThermalSensorComponent : public USceneComponent
{
	GENERATED_BODY()

public:
	UThermalSensorComponent();

	// ---------------- Setup ----------------

	/** Existing thermal scene capture on the owner to drive (by component name). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	FName ThermalCaptureName = TEXT("Thermal_Capture");

	/** Existing RGB scene capture on the owner (by component name). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	FName RGBCaptureName = TEXT("RGB_Capture");

	/** Create RGB + thermal captures on this component if the owner has none. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	bool bCreateCapturesIfMissing = true;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup", meta=(ClampMin="64", ClampMax="4096"))
	int32 ResolutionX = 1024;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup", meta=(ClampMin="64", ClampMax="4096"))
	int32 ResolutionY = 768;

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup", meta=(ClampMin="5", ClampMax="170"))
	float FieldOfView = 90.f;

	/** Give every actor tagged Heat_N a Thermal Body at BeginPlay. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	bool bAutoAddBodiesFromTags = true;

	/** Post-process material that turns the stencil heat values into an image. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	TSoftObjectPtr<UMaterialInterface> ThermalMaterial;

	/** ThermoForge's own probe-based heat-field material (experimental view). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category="Thermal Sensor|Setup")
	TSoftObjectPtr<UMaterialInterface> ThermoForgeFieldMaterial;

	// ---------------- Image ----------------

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image")
	EThermalDisplayMode DisplayMode = EThermalDisplayMode::WhiteHot;

	/** Coldest temperature shown = ambient minus this (°C). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="1"))
	float RangeBelowAmbientC = 15.f;

	/** Hottest temperature shown = ambient plus this (°C). Hotter saturates to full white. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="1"))
	float RangeAboveAmbientC = 75.f;

	/** < 1 brightens warm objects (more like a real camera's auto gain). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="0.1", ClampMax="3"))
	float DisplayGamma = 0.5f;

	/** How much surface shading from the scene shows through (0 = flat silhouettes). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="0", ClampMax="0.5"))
	float DetailAmount = 0.08f;

	/** Sensor noise. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="0", ClampMax="0.3"))
	float NoiseAmount = 0.02f;

	/** How cold the open sky reads, in °C below ambient. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="0"))
	float SkyBelowAmbientC = 15.f;

	/** Temperature updates per second. */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Image", meta=(ClampMin="1", ClampMax="60"))
	float UpdateRateHz = 15.f;

	// ---------------- ThermoForge climate ----------------

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Climate")
	bool bWinter = false;

	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Climate", meta=(ClampMin="0", ClampMax="24"))
	float TimeOfDayHours = 12.f;

	/** 0 clear sky .. 1 heavy overcast (less solar heating). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Climate", meta=(ClampMin="0", ClampMax="1"))
	float WeatherAlpha = 0.2f;

	/** Radius of ThermoForge probes for the experimental heat-field view (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Climate", meta=(ClampMin="100", ClampMax="50000"))
	float FieldProbeRadiusCm = 2000.f;

	/** Probe cloud is centered this far in front of the sensor (cm). */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Thermal Sensor|Climate", meta=(ClampMin="0"))
	float FieldCenterDistanceCm = 1000.f;

	// ---------------- Runtime ----------------

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal Sensor|Runtime")
	TObjectPtr<USceneCaptureComponent2D> ThermalCapture;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal Sensor|Runtime")
	TObjectPtr<USceneCaptureComponent2D> RGBCapture;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal Sensor|Runtime")
	float AmbientC = 0.f;

	UPROPERTY(VisibleInstanceOnly, BlueprintReadOnly, Transient, Category="Thermal Sensor|Runtime")
	int32 TrackedBodies = 0;

	// ---------------- API ----------------

	UFUNCTION(BlueprintCallable, Category="Thermal Sensor")
	void SetDisplayMode(EThermalDisplayMode NewMode);

	/** Cycle White Hot -> Black Hot -> Ironbow -> ThermoForge Field. */
	UFUNCTION(BlueprintCallable, Category="Thermal Sensor")
	void CycleDisplayMode();

	/** Temperature (°C) ThermoForge reports at a world position. */
	UFUNCTION(BlueprintPure, Category="Thermal Sensor")
	float GetTemperatureAt(const FVector& WorldLocation) const;

	UFUNCTION(BlueprintPure, Category="Thermal Sensor")
	UTextureRenderTarget2D* GetThermalTarget() const;

	UFUNCTION(BlueprintPure, Category="Thermal Sensor")
	UTextureRenderTarget2D* GetRGBTarget() const;

	/**
	 * Save the current RGB and thermal images as a matching pair of PNGs into
	 * <Project>/Saved/<Folder>/<Prefix>_<N>_RGB.png and _Thermal.png.
	 */
	UFUNCTION(BlueprintCallable, Category="Thermal Sensor")
	bool SaveImagePair(const FString& Folder, const FString& Prefix, FString& OutRGBFile, FString& OutThermalFile);

	virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

protected:
	virtual void BeginPlay() override;

private:
	void FindOrCreateCaptures();
	USceneCaptureComponent2D* MakeCapture(const TCHAR* Name, bool bThermal);
	void ApplyBlendables();
	void AutoAddBodies();
	void UpdateTemperatures();
	int32 EncodeStencil(float TempC) const;
	void UploadHeatPoints(const FVector& Origin);
	UThermoForgeSubsystem* GetThermo() const;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> ThermalMID;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> FieldMID;

	/** Localized heat points (hot spots, heat prints, fires) packed for the thermal shader. */
	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> HeatPointsTex;

	static constexpr int32 MaxHeatPoints = 64;
	int32 NumHeatPoints = 0;

	float TimeSinceUpdate = 0.f;
	int32 SavedPairCount = 0;
	EThermalDisplayMode AppliedMode = EThermalDisplayMode::WhiteHot;
	bool bBlendablesApplied = false;
};
