#include "ThermalSensorComponent.h"

#include "ThermalBodyComponent.h"
#include "ThermalSensorSubsystem.h"
#include "ThermoForgeSourceComponent.h"
#include "ThermoForgeSubsystem.h"
#include "ThermoForgeProjectSettings.h"

#include "Components/SceneCaptureComponent2D.h"
#include "Engine/Texture2D.h"
#include "Engine/TextureRenderTarget2D.h"
#include "TextureResource.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Actor.h"
#include "HAL/FileManager.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/Paths.h"

UThermalSensorComponent::UThermalSensorComponent()
{
	PrimaryComponentTick.bCanEverTick = true;
	PrimaryComponentTick.bStartWithTickEnabled = true;
	PrimaryComponentTick.TickGroup = TG_PostUpdateWork;

	ThermalMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/Game/ThermalSensor/M_ThermalSensorPP.M_ThermalSensorPP")));
	ThermoForgeFieldMaterial = TSoftObjectPtr<UMaterialInterface>(FSoftObjectPath(TEXT("/ThermoForge/ThermoForgeVisionPP_M.ThermoForgeVisionPP_M")));
}

UThermoForgeSubsystem* UThermalSensorComponent::GetThermo() const
{
	const UWorld* World = GetWorld();
	return World ? World->GetSubsystem<UThermoForgeSubsystem>() : nullptr;
}

void UThermalSensorComponent::BeginPlay()
{
	Super::BeginPlay();

	FindOrCreateCaptures();

	if (UMaterialInterface* Mat = ThermalMaterial.LoadSynchronous())
	{
		ThermalMID = UMaterialInstanceDynamic::Create(Mat, this);
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ThermalSensor: thermal material %s not found - run Scripts/SetupThermoForge.py"), *ThermalMaterial.ToString());
	}

	if (UMaterialInterface* FieldMat = ThermoForgeFieldMaterial.LoadSynchronous())
	{
		FieldMID = UMaterialInstanceDynamic::Create(FieldMat, this);
	}

	if (bAutoAddBodiesFromTags)
	{
		AutoAddBodies();
	}

	ApplyBlendables();
	UpdateTemperatures();
}

USceneCaptureComponent2D* UThermalSensorComponent::MakeCapture(const TCHAR* Name, bool /*bThermal*/)
{
	AActor* Owner = GetOwner();
	USceneCaptureComponent2D* Capture = NewObject<USceneCaptureComponent2D>(Owner, Name);
	Capture->SetupAttachment(this);
	Capture->FOVAngle = FieldOfView;
	Capture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
	Capture->bCaptureEveryFrame = true;
	Capture->bCaptureOnMovement = true;
	Capture->TextureTarget = UKismetRenderingLibrary::CreateRenderTarget2D(this, ResolutionX, ResolutionY, RTF_RGBA8);
	Capture->RegisterComponent();
	Owner->AddInstanceComponent(Capture);
	return Capture;
}

void UThermalSensorComponent::FindOrCreateCaptures()
{
	AActor* Owner = GetOwner();
	if (!Owner) return;

	TArray<USceneCaptureComponent2D*> Captures;
	Owner->GetComponents<USceneCaptureComponent2D>(Captures);
	for (USceneCaptureComponent2D* C : Captures)
	{
		if (!C) continue;
		const FString N = C->GetName();
		if (!ThermalCapture && (C->GetFName() == ThermalCaptureName || N.StartsWith(ThermalCaptureName.ToString())))
		{
			ThermalCapture = C;
		}
		else if (!RGBCapture && (C->GetFName() == RGBCaptureName || N.StartsWith(RGBCaptureName.ToString())))
		{
			RGBCapture = C;
		}
	}

	if (!ThermalCapture && bCreateCapturesIfMissing)
	{
		ThermalCapture = MakeCapture(TEXT("ThermalSensor_ThermalCapture"), true);
	}
	if (!RGBCapture && bCreateCapturesIfMissing)
	{
		RGBCapture = MakeCapture(TEXT("ThermalSensor_RGBCapture"), false);
	}

	if (ThermalCapture)
	{
		// Post-process materials only run on the final-color capture modes.
		if (ThermalCapture->CaptureSource != ESceneCaptureSource::SCS_FinalColorLDR &&
			ThermalCapture->CaptureSource != ESceneCaptureSource::SCS_FinalColorHDR &&
			ThermalCapture->CaptureSource != ESceneCaptureSource::SCS_FinalToneCurveHDR)
		{
			ThermalCapture->CaptureSource = ESceneCaptureSource::SCS_FinalColorLDR;
		}
		ThermalCapture->PostProcessBlendWeight = 1.f;
	}
	else
	{
		UE_LOG(LogTemp, Warning, TEXT("ThermalSensor on %s: no thermal capture found or created."), *GetNameSafe(Owner));
	}
}

void UThermalSensorComponent::AutoAddBodies()
{
	UWorld* World = GetWorld();
	if (!World) return;

	for (TActorIterator<AActor> It(World); It; ++It)
	{
		AActor* Actor = *It;
		if (!Actor || Actor->FindComponentByClass<UThermalBodyComponent>()) continue;

		bool bTagged = false;
		for (const FName& Tag : Actor->Tags)
		{
			if (Tag.ToString().StartsWith(TEXT("Heat_")))
			{
				bTagged = true;
				break;
			}
		}
		if (!bTagged) continue;

		UThermalBodyComponent* Body = NewObject<UThermalBodyComponent>(Actor, TEXT("ThermalBody"));
		Body->RegisterComponent();
		Actor->AddInstanceComponent(Body);
	}
}

void UThermalSensorComponent::ApplyBlendables()
{
	if (!ThermalCapture) return;

	TArray<FWeightedBlendable>& Array = ThermalCapture->PostProcessSettings.WeightedBlendables.Array;
	UMaterialInterface* BaseThermal = ThermalMaterial.Get();
	UMaterialInterface* BaseField = ThermoForgeFieldMaterial.Get();
	const UObject* OurThermal = ThermalMID.Get();
	const UObject* OurField = FieldMID.Get();
	Array.RemoveAll([&](const FWeightedBlendable& B)
	{
		const UObject* Obj = B.Object.Get();
		return Obj == nullptr || Obj == OurThermal || Obj == OurField ||
			(BaseThermal && Obj == BaseThermal) || (BaseField && Obj == BaseField);
	});

	UMaterialInstanceDynamic* Active = (DisplayMode == EThermalDisplayMode::ThermoForgeField && FieldMID) ? FieldMID.Get() : ThermalMID.Get();
	if (Active)
	{
		Array.Add(FWeightedBlendable(1.f, Active));
	}

	AppliedMode = DisplayMode;
	bBlendablesApplied = true;
}

int32 UThermalSensorComponent::EncodeStencil(float TempC) const
{
	// Stencil 0 is reserved for "no thermal body" (ambient / sky), so bodies use 1..255.
	const float Min = AmbientC - RangeBelowAmbientC;
	const float Range = FMath::Max(RangeBelowAmbientC + RangeAboveAmbientC, 1.f);
	const float T = FMath::Clamp((TempC - Min) / Range, 0.f, 1.f);
	return 1 + FMath::RoundToInt(T * 254.f);
}

void UThermalSensorComponent::UploadHeatPoints(const FVector& Origin)
{
	TArray<FThermalHeatPoint> Points;
	if (UThermalSensorSubsystem* Sub = UThermalSensorSubsystem::Get(this))
	{
		Sub->GatherHeatPoints(Points, true);
	}

	// Keep the points closest to the sensor if there are more than the shader handles.
	if (Points.Num() > MaxHeatPoints)
	{
		Points.Sort([&Origin](const FThermalHeatPoint& A, const FThermalHeatPoint& B)
		{
			return FVector::DistSquared(A.Location, Origin) < FVector::DistSquared(B.Location, Origin);
		});
		Points.SetNum(MaxHeatPoints);
	}
	NumHeatPoints = Points.Num();

	if (!HeatPointsTex)
	{
		HeatPointsTex = UTexture2D::CreateTransient(MaxHeatPoints, 2, PF_A32B32G32R32F);
		HeatPointsTex->Filter = TF_Nearest;
		HeatPointsTex->SRGB = false;
		HeatPointsTex->CompressionSettings = TC_HDR;
		HeatPointsTex->AddressX = TA_Clamp;
		HeatPointsTex->AddressY = TA_Clamp;
		HeatPointsTex->NeverStream = true;
		HeatPointsTex->UpdateResource();
	}

	// Row 0: position relative to the sensor (cm). Row 1: radius, intensity, falloff exponent.
	TArray<FLinearColor> Pixels;
	Pixels.SetNumZeroed(MaxHeatPoints * 2);
	for (int32 i = 0; i < NumHeatPoints; ++i)
	{
		const FThermalHeatPoint& P = Points[i];
		const FVector Rel = P.Location - Origin;
		Pixels[i] = FLinearColor(Rel.X, Rel.Y, Rel.Z, 1.f);
		Pixels[MaxHeatPoints + i] = FLinearColor(FMath::Max(P.RadiusCm, 1.f), P.IntensityCelsius, P.FalloffExponent, 0.f);
	}

	// Copy straight to the GPU texture on the render thread (the reliable way to stream
	// small per-frame data into a transient texture).
	const uint32 Pitch = MaxHeatPoints * sizeof(FLinearColor);
	const SIZE_T Bytes = Pixels.Num() * sizeof(FLinearColor);
	uint8* Copy = static_cast<uint8*>(FMemory::Malloc(Bytes));
	FMemory::Memcpy(Copy, Pixels.GetData(), Bytes);
	FUpdateTextureRegion2D* Region = new FUpdateTextureRegion2D(0, 0, 0, 0, MaxHeatPoints, 2);
	HeatPointsTex->UpdateTextureRegions(0, 1, Region, Pitch, sizeof(FLinearColor), Copy,
		[](uint8* SrcData, const FUpdateTextureRegion2D* Regions)
		{
			FMemory::Free(SrcData);
			delete Regions;
		});
}

float UThermalSensorComponent::GetTemperatureAt(const FVector& WorldLocation) const
{
	if (const UThermoForgeSubsystem* Thermo = GetThermo())
	{
		return Thermo->ComputeCurrentTemperatureAt(WorldLocation, bWinter, TimeOfDayHours, WeatherAlpha);
	}
	return 0.f;
}

void UThermalSensorComponent::UpdateTemperatures()
{
	UThermoForgeSubsystem* Thermo = GetThermo();
	if (!Thermo) return;

	const FVector SensorLoc = ThermalCapture ? ThermalCapture->GetComponentLocation() : GetComponentLocation();
	const FVector SensorFwd = ThermalCapture ? ThermalCapture->GetForwardVector() : GetForwardVector();

	const UThermoForgeProjectSettings* Settings = Thermo->GetSettings();
	AmbientC = Settings ? Settings->GetAmbientCelsiusAt(bWinter, TimeOfDayHours, SensorLoc.Z) : 20.f;

	TArray<UThermalBodyComponent*> Bodies;
	UThermalBodyComponent::GetBodiesInWorld(GetWorld(), Bodies);
	TrackedBodies = Bodies.Num();

	// Point sources (fire etc.) are drawn per pixel by the shader, so leave them out of the
	// object's base temperature to avoid counting them twice.
	TArray<UThermoForgeSourceComponent*> Sources;
	Thermo->GetAllSources(Sources);
	Sources.RemoveAll([](const UThermoForgeSourceComponent* S) { return !S || !S->bEnabled || S->Shape != EThermoSourceShape::Point; });

	for (UThermalBodyComponent* Body : Bodies)
	{
		const FVector Loc = Body->GetSampleLocation();
		float TempC = Thermo->ComputeCurrentTemperatureAt(Loc, bWinter, TimeOfDayHours, WeatherAlpha);
		for (const UThermoForgeSourceComponent* Src : Sources)
		{
			TempC -= Src->SampleAt(Loc);
		}
		Body->CurrentTemperatureC = TempC;
		Body->ApplyStencilValue(EncodeStencil(TempC));
	}

	UploadHeatPoints(SensorLoc);

	if (ThermalMID)
	{
		const float ModeValue = DisplayMode == EThermalDisplayMode::BlackHot ? 1.f :
			(DisplayMode == EThermalDisplayMode::Ironbow ? 2.f : 0.f);
		ThermalMID->SetScalarParameterValue(TEXT("Mode"), ModeValue);
		ThermalMID->SetScalarParameterValue(TEXT("AmbientC"), AmbientC);
		ThermalMID->SetScalarParameterValue(TEXT("SkyC"), AmbientC - SkyBelowAmbientC);
		ThermalMID->SetScalarParameterValue(TEXT("TMin"), AmbientC - RangeBelowAmbientC);
		ThermalMID->SetScalarParameterValue(TEXT("TRange"), FMath::Max(RangeBelowAmbientC + RangeAboveAmbientC, 1.f));
		ThermalMID->SetScalarParameterValue(TEXT("Gamma"), FMath::Max(DisplayGamma, 0.05f));
		ThermalMID->SetScalarParameterValue(TEXT("Detail"), DetailAmount);
		ThermalMID->SetScalarParameterValue(TEXT("Noise"), NoiseAmount);
		ThermalMID->SetScalarParameterValue(TEXT("NumSources"), static_cast<float>(NumHeatPoints));
		ThermalMID->SetScalarParameterValue(TEXT("SourceTexWidth"), static_cast<float>(MaxHeatPoints));
		ThermalMID->SetVectorParameterValue(TEXT("HeatOrigin"), FLinearColor(SensorLoc));
		if (HeatPointsTex)
		{
			ThermalMID->SetTextureParameterValue(TEXT("HeatSources"), HeatPointsTex);
		}
	}

	if (DisplayMode == EThermalDisplayMode::ThermoForgeField && FieldMID)
	{
		const bool bRadiusChanged = !FMath::IsNearlyEqual(Thermo->ProbeRadiusCm, FieldProbeRadiusCm);
		Thermo->MaxProbes = 512; // the ThermoForge vision shader reads at most 512 probes
		Thermo->ProbeRadiusCm = FieldProbeRadiusCm;
		const FVector Center = SensorLoc + SensorFwd * FieldCenterDistanceCm;
		Thermo->UpdateThermalProbesAndUpload(Center, bRadiusChanged);

		FieldMID->SetTextureParameterValue(TEXT("TF_ProbesTex"), Thermo->ProbesTex);
		FieldMID->SetScalarParameterValue(TEXT("TF_NumProbes"), static_cast<float>(Thermo->NumProbes));
		FieldMID->SetScalarParameterValue(TEXT("TF_KernelRadiusCm"), Thermo->KernelRadiusCm);
		FieldMID->SetScalarParameterValue(TEXT("TF_TempMin"), AmbientC - RangeBelowAmbientC);
		FieldMID->SetScalarParameterValue(TEXT("TF_TempMax"), AmbientC + RangeAboveAmbientC);
		FieldMID->SetScalarParameterValue(TEXT("TF_AnimMaxRadiusCm"), FieldProbeRadiusCm);
		FieldMID->SetVectorParameterValue(TEXT("TF_CenterWS"), FLinearColor(Center));
	}
}

void UThermalSensorComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
	Super::TickComponent(DeltaTime, TickType, ThisTickFunction);

	if (!bBlendablesApplied || AppliedMode != DisplayMode)
	{
		ApplyBlendables();
	}

	// The heat-field view does hundreds of ThermoForge queries per update, so it runs slower.
	const float Rate = (DisplayMode == EThermalDisplayMode::ThermoForgeField) ? FMath::Min(UpdateRateHz, 4.f) : UpdateRateHz;
	TimeSinceUpdate += DeltaTime;
	if (TimeSinceUpdate >= 1.f / FMath::Max(Rate, 1.f))
	{
		TimeSinceUpdate = 0.f;
		UpdateTemperatures();
	}
}

void UThermalSensorComponent::SetDisplayMode(EThermalDisplayMode NewMode)
{
	DisplayMode = NewMode;
	ApplyBlendables();
	UpdateTemperatures();
}

void UThermalSensorComponent::CycleDisplayMode()
{
	const uint8 Next = (static_cast<uint8>(DisplayMode) + 1) % 4;
	SetDisplayMode(static_cast<EThermalDisplayMode>(Next));
}

UTextureRenderTarget2D* UThermalSensorComponent::GetThermalTarget() const
{
	return ThermalCapture ? ThermalCapture->TextureTarget.Get() : nullptr;
}

UTextureRenderTarget2D* UThermalSensorComponent::GetRGBTarget() const
{
	return RGBCapture ? RGBCapture->TextureTarget.Get() : nullptr;
}

static bool TS_Export(UObject* Context, USceneCaptureComponent2D* Capture, const FString& Dir, const FString& BaseName, FString& OutFile)
{
	if (!Capture || !Capture->TextureTarget) return false;
	UTextureRenderTarget2D* RT = Capture->TextureTarget;
	if (!Capture->bCaptureEveryFrame)
	{
		Capture->CaptureScene();
	}
	const bool bLDR = RT->RenderTargetFormat == RTF_RGBA8 || RT->RenderTargetFormat == RTF_RGBA8_SRGB;
	const FString FileName = BaseName + (bLDR ? TEXT(".png") : TEXT(".exr"));
	UKismetRenderingLibrary::ExportRenderTarget(Context, RT, Dir, FileName);
	OutFile = FPaths::Combine(Dir, FileName);
	return true;
}

bool UThermalSensorComponent::SaveImagePair(const FString& Folder, const FString& Prefix, FString& OutRGBFile, FString& OutThermalFile)
{
	const FString Dir = FPaths::ConvertRelativePathToFull(FPaths::Combine(FPaths::ProjectSavedDir(), Folder.IsEmpty() ? TEXT("ThermalCaptures") : Folder));
	IFileManager::Get().MakeDirectory(*Dir, true);

	const FString Base = FString::Printf(TEXT("%s_%03d"), Prefix.IsEmpty() ? *GetNameSafe(GetOwner()) : *Prefix, SavedPairCount++);
	const bool bRGB = TS_Export(this, RGBCapture, Dir, Base + TEXT("_RGB"), OutRGBFile);
	const bool bThermal = TS_Export(this, ThermalCapture, Dir, Base + TEXT("_Thermal"), OutThermalFile);
	return bRGB && bThermal;
}
