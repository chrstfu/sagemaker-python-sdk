from __future__ import absolute_import

from dataclasses import dataclass
from typing import Optional, List, Mapping
from enum import Enum

@dataclass
class Origin:
    OriginTrainingJobArn: Optional[str]
    OriginEndpointArn: Optional[str]


@dataclass
class Dependency:
    DependencyOriginPath: str
    DependencyCopyPath: str
    DependencyType: str  # enum?


@dataclass
class DatasetConfig:
    TrainingDatasetLocation: Optional[str]  # S3 validation?
    ValidationDatasetLocation: Optional[str]  # S3 validation?
    DataFormatLocation: Optional[str]  # S3 validation?
    PredictColumn: Optional[str]


@dataclass
class Metric:
    Name: str
    Regex: str


@dataclass
class SdkEstimatorArgs:
    EntryPoint: Optional[str]
    EnableNetworkIsolation: Optional[bool]
    Environment: Mapping[str, str]
    Metrics: List[Metric]
    OutputPath: Optional[str]


@dataclass
class DefaultTrainingSdkArgs:
    MinSdkVersion: Optional[str]
    SdkEstimatorArgs: Optional[SdkEstimatorArgs]


@dataclass
class DefaultDeploymentSdkArgs:
    MinSdkVersion: Optional[str]
    SdkModelArgs: Optional[SdkEstimatorArgs]


@dataclass
class CustomImageConfig:
    ImageLocation: str  # ecr address


@dataclass
class FrameworkImageConfig:
    Framework: str
    FrameworkVersion: str
    PythonVersion: str
    TransformersVersion: Optional[str]
    BaseFramework: Optional[str]


@dataclass
class ModelArtifactConfig:
    ArtifactLocation: str  # s3 address


@dataclass
class ScriptConfig:
    ScriptLocation: str  # s3 address


@dataclass
class InstanceConfig:
    DefaultInstanceType: str
    InstanceTypeOptions: List[str]


@dataclass
class Hyperparameters:
    Name: str
    DefaultValue: Optional[str]
    Type: str  # enum
    Options: List[Optional[str]]
    Label: Optional[str]
    Description: Optional[str]
    Regex: Optional[str]
    Min: Optional[str]
    Max: Optional[str]


@dataclass
class ExtraChannels:
    ChannelName: str
    ChannelDataLocation: str  # s3 uri (prefix or key)


@dataclass
class DefaultTrainingConfig:
    SdkArgs: Optional[DefaultTrainingSdkArgs]
    CustomImageConfig: Optional[CustomImageConfig]
    FrameworkImageConfig: Optional[FrameworkImageConfig]
    ModelArtifactConfig: Optional[ModelArtifactConfig]
    ScriptConfig: Optional[ScriptConfig]
    InstanceConfig: Optional[InstanceConfig]
    Hyperparameters: List[Hyperparameters]
    ExtraChannels: List[ExtraChannels]


@dataclass
class InferenceNotebookConfig:
    NotebookLocation: str  # s3 uri,


@dataclass
class DefaultDeploymentConfig:
    SdkArgs: Optional[DefaultDeploymentSdkArgs]
    CustomImageConfig: Optional[CustomImageConfig]
    FrameworkImageConfig: Optional[FrameworkImageConfig]
    ModelArtifactConfig: Optional[ModelArtifactConfig]
    ScriptConfig: Optional[ScriptConfig]
    InstanceConfig: Optional[InstanceConfig]
    InferenceNotebookConfig: Optional[InferenceNotebookConfig]


class ModelCapabilities(str, Enum):
    TRAINING = "Training"
    INCREMENTAL_TRAINING = "IncrementalTraining"
    VALIDATION = "Validation"


@dataclass
class HubModelSpec_v1_0_0:
    Capabilities: List[ModelCapabilities]  # enum?
    DataType: str
    MlTask: str
    Framework: Optional[str]
    Origin: Optional[Origin]
    Dependencies: List[Dependency]
    DatasetConfig: Optional[DatasetConfig]
    DefaultTrainingConfig: Optional[DefaultTrainingConfig]
    DefaultDeploymentConfig: Optional[DefaultDeploymentConfig]