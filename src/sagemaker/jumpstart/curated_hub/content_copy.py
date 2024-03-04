# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
#     http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
"""This module contains utilities to help copy hub content dependencies."""
from __future__ import absolute_import
import traceback
from typing import List, Set, Optional

from concurrent import futures
from dataclasses import dataclass
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from sagemaker.jumpstart.curated_hub.utils import (
    find_objects_under_prefix,
)
from sagemaker.jumpstart.types import JumpStartModelSpecs
from sagemaker.jumpstart.curated_hub.accessors.model_dependency_s3_accessor import (
    ModelDependencyS3Accessor,
)
from sagemaker.jumpstart.curated_hub.accessors.s3_object_reference import (
    S3ObjectLocation,
)
from sagemaker.jumpstart.curated_hub.accessors.constants import (
    UNCOMPRESSED_ARTIFACTS_VALUE
)


EXTRA_S3_COPY_ARGS = {"ACL": "bucket-owner-full-control", "Tagging": "SageMaker=true"}


@dataclass
class CopyContentConfig:
    """Property class to assist S3 copy"""

    src: S3ObjectLocation
    dst: S3ObjectLocation
    logging_name: str


class ContentCopier:
    """Copies content from JS source bucket to hub bucket."""

    def __init__(
        self,
        region: str,
        s3_client: BaseClient,
        src_s3_accessor: ModelDependencyS3Accessor,
        dst_s3_accessor: ModelDependencyS3Accessor,
        thread_pool_size: int = 20,
    ) -> None:
        """Sets up basic info."""
        self._region = region
        self._s3_client = s3_client
        self._thread_pool_size = thread_pool_size

        self._src_s3_accessor = src_s3_accessor
        self._dst_s3_accessor = dst_s3_accessor

    def copy_hub_content_dependencies_to_hub_bucket(self, model_specs: JumpStartModelSpecs) -> None:
        """Copies all hub content dependencies into the hub bucket.

        This copy is multi-threaded.
        """
        copy_configs: List[CopyContentConfig] = []

        copy_configs.extend(self._get_copy_configs_for_inference_dependencies(model_specs))
        copy_configs.extend(self._get_copy_configs_for_demo_notebook_dependencies(model_specs))
        copy_configs.extend(self._get_copy_configs_for_markdown_dependencies(model_specs))

        if model_specs.training_supported:
            copy_configs.extend(self._get_copy_configs_for_training_dependencies(model_specs))

        self._parallel_execute_copy_configs(copy_configs)

    def _get_copy_configs_for_inference_dependencies(
        self, model_specs: JumpStartModelSpecs
    ) -> List[CopyContentConfig]:
        """Creates copy configs for inference dependencies"""
        copy_configs: List[CopyContentConfig] = []

        print(f"Pulling hosting_artifact_s3_data_type: {model_specs.hosting_artifact_s3_data_type}")

        if model_specs.hosting_artifact_s3_data_type == UNCOMPRESSED_ARTIFACTS_VALUE:
          src_uncompressed_inference_prefix = self._src_s3_accessor.get_uncompresssed_inference_artifact_s3_reference(
              model_specs
          )
          dst_uncompressed_inference_prefix = self._dst_s3_accessor.get_uncompresssed_inference_artifact_s3_reference(
              model_specs
          )
          copy_configs.extend(self._get_s3_dir_copy_configs(src_uncompressed_inference_prefix, dst_uncompressed_inference_prefix))
        else:
          src_inference_artifact_location = self._src_s3_accessor.get_inference_artifact_s3_reference(
              model_specs
          )
          dst_artifact_reference = self._dst_s3_accessor.get_inference_artifact_s3_reference(
              model_specs
          )
          copy_configs.append(
              CopyContentConfig(
                  src=src_inference_artifact_location,
                  dst=dst_artifact_reference,
                  logging_name="inference artifact",
              )
          )

        if not model_specs.supports_prepacked_inference():
            # Need to also copy script if prepack not enabled
            src_inference_script_location = self._src_s3_accessor.get_inference_script_s3_reference(
                model_specs
            )
            dst_inference_script_reference = (
                self._dst_s3_accessor.get_inference_script_s3_reference(model_specs)
            )

            copy_configs.append(
                CopyContentConfig(
                    src=src_inference_script_location,
                    dst=dst_inference_script_reference,
                    logging_name="inference script",
                )
            )

        return copy_configs

    def _get_copy_configs_for_training_dependencies(
        self, model_specs: JumpStartModelSpecs
    ) -> List[CopyContentConfig]:
        """Creates copy configurations for training dependencies"""
        copy_configs: List[CopyContentConfig] = []

        print(f"Pulling training_artifact_s3_data_type: {model_specs.training_artifact_s3_data_type}")

        if model_specs.training_artifact_s3_data_type == UNCOMPRESSED_ARTIFACTS_VALUE:
          src_uncompressed_training_prefix = self._src_s3_accessor.get_uncompresssed_training_artifact_s3_reference(
              model_specs
          )
          dst_uncompressed_training_prefix = self._dst_s3_accessor.get_uncompresssed_training_artifact_s3_reference(
              model_specs
          )
          copy_configs.extend(self._get_s3_dir_copy_configs(src_uncompressed_training_prefix, dst_uncompressed_training_prefix))
        else:
          src_training_artifact_location = self._src_s3_accessor.get_training_artifact_s3_reference(
              model_specs
          )
          dst_artifact_reference = self._dst_s3_accessor.get_training_artifact_s3_reference(
              model_specs
          )            
          copy_configs.append(
              CopyContentConfig(
                  src=src_training_artifact_location,
                  dst=dst_artifact_reference,
                  logging_name="training artifact",
              )
          )

        src_training_script_location = self._src_s3_accessor.get_training_script_s3_reference(
            model_specs
        )
        dst_training_script_reference = self._dst_s3_accessor.get_training_script_s3_reference(
            model_specs
        )
        copy_configs.append(
            CopyContentConfig(
                src=src_training_script_location,
                dst=dst_training_script_reference,
                logging_name="training script",
            )
        )

        copy_configs.extend(self._get_copy_configs_for_training_dataset(model_specs))

        return copy_configs
    
    def _get_s3_dir_copy_configs(self, src_prefix: S3ObjectLocation, dst_prefix: S3ObjectLocation) -> List[CopyContentConfig]:
        keys_in_src_dir = self._get_s3_object_keys_under_prefix(src_prefix)
        copy_configs: List[CopyContentConfig] = []
        
        for full_src_key in keys_in_src_dir:
            src_reference = S3ObjectLocation(src_prefix.bucket, full_src_key)
            dst_key = f'{dst_prefix.key}{src_reference.get_filename()}' if dst_prefix.is_directory() else f'{dst_prefix.key}/{src_reference.get_filename()}'
            dst_reference = S3ObjectLocation(dst_prefix.bucket, dst_key)
            copy_configs.append(
                CopyContentConfig(
                    src=src_reference, dst=dst_reference, logging_name=f"uncompressed artifact {src_reference.get_filename()}"
                )
            )

        return copy_configs

    def _get_copy_configs_for_training_dataset(
        self, model_specs: JumpStartModelSpecs
    ) -> List[CopyContentConfig]:
        """Creates copy configuration for training dataset"""
        src_prefix = self._src_s3_accessor.get_default_training_dataset_s3_reference(model_specs)
        dst_prefix = self._dst_s3_accessor.get_default_training_dataset_s3_reference(model_specs)

        keys_in_src_dir = self._get_s3_object_keys_under_prefix(src_prefix)

        copy_configs: List[CopyContentConfig] = []
        for full_key in keys_in_src_dir:
            src_reference = S3ObjectLocation(src_prefix.bucket, full_key)
            dst_reference = S3ObjectLocation(
                dst_prefix.bucket, full_key.replace(src_prefix.key, dst_prefix.key, 1)
            )  # Replacing s3 key prefix with expected destination prefix

            copy_configs.append(
                CopyContentConfig(
                    src=src_reference, dst=dst_reference, logging_name="training dataset"
                )
            )

        return copy_configs

    def _get_s3_object_keys_under_prefix(self, prefix_reference: S3ObjectLocation) -> Set[str]:
        """Get all s3 keys under a s3 folder"""
        try:
            return find_objects_under_prefix(
                bucket=prefix_reference.bucket,
                prefix=prefix_reference.key,
                s3_client=self._s3_client,
            )
        except Exception as ex:
            print(
                "ERROR: encountered an exception when finding objects"
                + f" under prefix {prefix_reference.bucket}/{prefix_reference.key}: {str(ex)}"
            )
            raise

    def _get_copy_configs_for_demo_notebook_dependencies(
        self, model_specs: JumpStartModelSpecs
    ) -> List[CopyContentConfig]:
        """Returns copy configs for demo notebooks"""
        copy_configs: List[CopyContentConfig] = []

        notebook_s3_reference = self._src_s3_accessor.get_demo_notebook_s3_reference(model_specs)
        notebook_s3_reference_dst = self._dst_s3_accessor.get_demo_notebook_s3_reference(
            model_specs
        )
        copy_configs.append(
            CopyContentConfig(
                src=notebook_s3_reference,
                dst=notebook_s3_reference_dst,
                logging_name="demo notebook",
            )
        )

        return copy_configs

    def _get_copy_configs_for_markdown_dependencies(
        self, model_specs: JumpStartModelSpecs
    ) -> List[CopyContentConfig]:
        """Generates a list of copy configurations for hub content markdown dependencies."""
        copy_configs: List[CopyContentConfig] = []

        markdown_s3_reference = self._src_s3_accessor.get_markdown_s3_reference(model_specs)
        markdown_s3_reference_dst = self._dst_s3_accessor.get_markdown_s3_reference(model_specs)
        copy_configs.append(
            CopyContentConfig(
                src=markdown_s3_reference, dst=markdown_s3_reference_dst, logging_name="markdown"
            )
        )

        return copy_configs

    def _parallel_execute_copy_configs(self, copy_configs: List[CopyContentConfig]) -> None:
        """Runs all copy configurations in parallel.

        This utility makes s3:CopyObject calls in a ThreadPoolExecutor. All copy configurations
        are run before any errors are raised.

        Raises:
          RuntimeError if any copy configuration fails.
        """
        tasks = []
        with futures.ThreadPoolExecutor(
            max_workers=self._thread_pool_size, thread_name_prefix="import-models-to-curated-hub"
        ) as deploy_executor:
            for copy_config in copy_configs:
                tasks.append(
                    deploy_executor.submit(
                        self._copy_s3_reference,
                        copy_config.logging_name,
                        copy_config.src,
                        copy_config.dst,
                    )
                )

        results = futures.wait(tasks)
        failed_copies: List[BaseException] = []
        for result in results.done:
            exception = result.exception()
            if exception:
                failed_copies.append(
                    {
                        "Exception": exception,
                        "Traceback": "".join(
                            traceback.TracebackException.from_exception(exception).format()
                        ),
                    }
                )
        if failed_copies:
            raise RuntimeError(
                f"Failures when importing models to curated hub in parallel: {failed_copies}"
            )

    def _copy_s3_reference(
        self, resource_name: str, src: S3ObjectLocation, dst: S3ObjectLocation
    ) -> None:
        """Copies src S3ObjectReference to dst S3ObjectReference.

        This utility calls s3:CopyObject.

        Raises:
          Exception when s3:CopyObject raises an exception
        """
        if not self.is_s3_object_etag_different(src, dst):
            print(
                f"Detected that {resource_name} is the same in destination bucket. Skipping copy."
            )
            return

        print(f"Copying {resource_name} from {src.bucket}/{src.key} to {dst.bucket}/{dst.key}...")
        try:
            self._s3_client.copy(
                src.format_for_s3_copy(),
                dst.bucket,
                dst.key,
                ExtraArgs=EXTRA_S3_COPY_ARGS,
            )
        except Exception as ex:
            print(
                "ERROR: encountered an exception when calling s3:CopyObject from"
                + f" {src.bucket}/{src.key} to {dst.bucket}/{dst.key}: {str(ex)}"
            )
            raise

        print(
            f"Copying {resource_name} from"
            f" {src.bucket}/{src.key} to {dst.bucket}/{dst.key} complete!"
        )

    def is_s3_object_etag_different(self, src: S3ObjectLocation, dst: S3ObjectLocation) -> bool:
        """Compares S3 object ETag value to determine if the objects are the same"""
        src_etag = self._get_s3_object_etag(src)
        dst_etag = self._get_s3_object_etag(dst)

        return src_etag != dst_etag

    def _get_s3_object_etag(self, s3_object: S3ObjectLocation) -> Optional[str]:
        """Calls S3:HeadObject on the S3 object, returns the ETag value.

        If the object is not found, the ETag is set to None.

        Raises:
          Any exception that is not a s3:NoSuchKey error.
        """
        try:
            response = self._s3_client.head_object(Bucket=s3_object.bucket, Key=s3_object.key)
            return response.pop("ETag")
        except ClientError as ce:
            if ce.response["Error"]["Code"] != "404":
                print(
                    "ERROR: Received error when calling HeadObject for "
                    f"s3://{s3_object.bucket}/{s3_object.key}: {ce.response['Error']}"
                )
                raise
            return None