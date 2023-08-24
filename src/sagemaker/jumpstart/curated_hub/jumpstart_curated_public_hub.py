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
"""This module provides the JumpStart Curated Hub class."""
from __future__ import absolute_import

import json
import uuid
import logging
import traceback
from concurrent import futures
from typing import List, Optional, Tuple, Dict, Any

import boto3
from botocore.client import ClientError

from sagemaker.jumpstart.curated_hub.content_copy import ContentCopier
from sagemaker.jumpstart.curated_hub.hub_client import CuratedHubClient
from sagemaker.jumpstart.curated_hub.model_document import ModelDocumentCreator
from sagemaker.jumpstart.curated_hub.hub_model_specs.hub_model_specs import Dependency
from sagemaker.jumpstart.curated_hub.accessors.public_hub_s3_accessor import (
    PublicHubS3Accessor,
)
from sagemaker.jumpstart.curated_hub.accessors.curated_hub_s3_accessor import (
    CuratedHubS3Accessor,
)
from sagemaker.jumpstart.curated_hub.utils import (
    PublicHubModel,
    get_studio_model_metadata_map_from_region,
)
from sagemaker.jumpstart.enums import (
    JumpStartScriptScope,
)
from sagemaker.jumpstart.types import JumpStartModelSpecs
from sagemaker.jumpstart.utils import (
    verify_model_region_and_return_specs,
)
from sagemaker.jumpstart.curated_hub.accessors.s3_object_reference import (
    create_s3_object_reference_from_uri,
)
from sagemaker.jumpstart.curated_hub.utils import (
    find_objects_under_prefix,
)
from sagemaker.jumpstart.constants import JUMPSTART_DEFAULT_REGION_NAME
from sagemaker.jumpstart.curated_hub.accessors.s3_object_reference import (
    S3ObjectLocation, create_s3_object_reference_from_uri
)
from sagemaker.jumpstart.curated_hub.constants import CURATED_HUB_DEFAULT_DOCUMENT_SCHEMA_VERSION, CURATED_HUB_CONTENT_TYPE


class JumpStartCuratedPublicHub:
    """JumpStartCuratedPublicHub class.

    This class helps users create a new curated hub.
    If a hub already exists on the account, it will attempt to use that hub.
    """

    def __init__(
        self,
        curated_hub_name: str,
        region: str = JUMPSTART_DEFAULT_REGION_NAME,
    ):
        self._region = region
        self._s3_client = self._get_s3_client()
        self._sm_client = self._get_sm_client()
        self._default_thread_pool_size = 20

        self.curated_hub_name = curated_hub_name
        curated_hub_s3_config = self._get_hub_s3_config(curated_hub_name)
        self.curated_hub_s3_bucket_name = curated_hub_s3_config.bucket
        self.curated_hub_s3_key_prefix = curated_hub_s3_config.key

        logging.info(f"HUB_NAME={self.curated_hub_name}")
        logging.info(f"HUB_BUCKET_NAME={self.curated_hub_s3_bucket_name}")

        self.studio_metadata_map = get_studio_model_metadata_map_from_region(self._region)
        self._init_dependencies()   

    def _get_s3_client(self) -> Any:
        return boto3.client("s3", region_name=self._region)
    
    def _get_sm_client(self) -> Any:
        return boto3.client("sagemaker", region_name=self._region)

    def _get_hub_s3_config(self, hub_name: str) -> S3ObjectLocation:
        """Returns an S3ObjectLocation that references the Private Hub S3 location.
        
        If it exists, this will take the S3 configuration of the pre-existing hub.
        If it does not, it will create a unique S3 configuration for a new hub.
        Raises:
          ClientError if any error outside of the cases above occurs.
        """
        try:
          hub_res = self._sm_client.describe_hub(HubName=hub_name)              
          s3_config = hub_res["S3StorageConfig"]["S3OutputPath"]
          return create_s3_object_reference_from_uri(s3_config)
        except ClientError as ex:
            if ex.response["Error"]["Code"] != "ResourceNotFound":
              raise

        return S3ObjectLocation(
            bucket=self._create_unique_s3_bucket_name(hub_name, self._region),
            key=""
        )

    def _init_dependencies(self):
        """Creates all dependencies to run the Curated Hub."""
        self._curated_hub_client = CuratedHubClient(
            curated_hub_name=self.curated_hub_name, region=self._region
        )

        self._src_s3_accessor = PublicHubS3Accessor(self._region)
        self._dst_s3_filesystem = CuratedHubS3Accessor(
            self._region, self.curated_hub_s3_bucket_name, self.curated_hub_s3_key_prefix
        )

        self._content_copier = ContentCopier(
            region=self._region,
            s3_client=self._s3_client,
            src_s3_accessor=self._src_s3_accessor,
            dst_s3_accessor=self._dst_s3_filesystem,
        )
        self._document_creator = ModelDocumentCreator(
            region=self._region,
            src_s3_accessor=self._src_s3_accessor,
            hub_s3_accessor=self._dst_s3_filesystem,
            studio_metadata_map=self.studio_metadata_map,
        )

    def _create_unique_s3_bucket_name(self, bucket_name: str, region: str) -> str:
        """Creates a unique s3 bucket name."""
        unique_bucket_name = f"{bucket_name}-{region}-{uuid.uuid4()}"
        return unique_bucket_name[:63]  # S3 bucket name size is limited to 63 characters

    def create(self, import_into_preexisting: bool = False):
        """Creates a Curated Hub and corresponding S3 bucket in the caller AWS account.
        
        If import_into_preexisting is set to true, it will skip creation of the Private hub and hub S3 bucket.
        Raises:
          ClientError if any error outside of the above case occurs.
        """
        try:
          location_constraint = None
          if self._region != "us-east-1":
            location_constraint = {"LocationConstraint": self._region}
          self._s3_client.create_bucket(
              Bucket=self.curated_hub_s3_bucket_name,
              CreateBucketConfiguration=location_constraint,
          )
        except ClientError as ex:
            if not (ex.response["Error"]["Code"] in ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"] and import_into_preexisting):
                raise
            logging.warn(f"Skipping hub bucket creation as S3 bucket {self.curated_hub_s3_bucket_name} already exists.")

        try:
          self._curated_hub_client.create_hub(self.curated_hub_name, self.curated_hub_s3_bucket_name)
        except ClientError as ex:
            if not (ex.response["Error"]["Code"] in ["ResourceInUse"] and import_into_preexisting):
                raise
            logging.warn(f"Skipping hub creation as hub {self.curated_hub_name} already exists.")

    def sync(self, model_ids: List[PublicHubModel], force_update: bool = False):
        """Syncs Curated Hub with the JumpStart Public Hub.

        This will compare the models in the hub to the corresponding models in the JumpStart Public Hub.
        If there is a difference, this will add/update the model in the hub. For each model, this will perform a s3:CopyObject for all model dependencies into the hub.
        This will then import the metadata as a HubContent entry. This copy is performed in parallel using a thread pool.

        If the model already exists in the curated hub,
          it will skip the update.
        If `force_update` is set to true or if a new version is passed in,
          it will remove the version and replace it with the new version.
        """

        model_specs = self._get_model_specs_for_list(model_ids)

        if not force_update:
            logging.info(
                "Filtering out models that are already in hub."
                " If you still wish to update these models, set `force_update` to True"
            )
            model_specs = list(filter(self._model_needs_update, model_specs))

        self._import_models(model_specs)

    def _get_model_specs_for_list(
        self, model_ids: List[PublicHubModel]
    ) -> List[JumpStartModelSpecs]:
        """Converts a list of PublicHubModel to JumpStartModelSpecs"""
        return list(map(self._get_model_specs, model_ids))

    def _get_model_specs(self, model_id: PublicHubModel) -> JumpStartModelSpecs:
        """Converts PublicHubModel to JumpStartModelSpecs."""
        return verify_model_region_and_return_specs(
            model_id=model_id.id,
            version=model_id.version,
            scope=JumpStartScriptScope.INFERENCE,
            region=self._region,
        )

    def _model_needs_update(self, model_specs: JumpStartModelSpecs) -> bool:
        """Checks if a new upload is necessary."""
        try:
            self._curated_hub_client.describe_model_version(model_specs)
            logging.info(f"Model {model_specs.model_id} found in hub.")
            return False
        except ClientError as ex:
            if ex.response["Error"]["Code"] != "ResourceNotFound":
                raise
            return True

    def _import_models(self, model_specs: List[JumpStartModelSpecs]):
        """Imports a list of models to a hub."""
        logging.info(f"Importing {len(model_specs)} models to curated private hub...")
        tasks: List[futures.Future] = []
        with futures.ThreadPoolExecutor(
            max_workers=self._default_thread_pool_size,
            thread_name_prefix="import-models-to-curated-hub",
        ) as deploy_executor:
            for model_spec in model_specs:
                task = deploy_executor.submit(self._import_model, model_spec)
                tasks.append(task)

        results = futures.wait(tasks)
        failed_imports: List[Dict[str, Any]] = []
        for result in results.done:
            exception = result.exception()
            if exception:
                failed_imports.append(
                    {
                        "Exception": exception,
                        "Traceback": "".join(
                            traceback.TracebackException.from_exception(exception).format()
                        ),
                    }
                )
        if failed_imports:
            raise RuntimeError(
                f"Failures when importing models to curated hub in parallel: {failed_imports}"
            )

    def _import_model(self, public_js_model_specs: JumpStartModelSpecs) -> None:
        """Imports a model to a hub."""
        print(
            f"Importing model {public_js_model_specs.model_id}"
            f" version {public_js_model_specs.version} to curated private hub..."
        )
        # Currently only able to support a single version of HubContent
        self._curated_hub_client.delete_all_versions_of_model(model_specs=public_js_model_specs)

        self._content_copier.copy_hub_content_dependencies_to_hub_bucket(
            model_specs=public_js_model_specs
        )
        self._import_public_model_to_hub(model_specs=public_js_model_specs)
        print(
            f"Importing model {public_js_model_specs.model_id}"
            f" version {public_js_model_specs.version} to curated private hub complete!"
        )

    def _import_public_model_to_hub(self, model_specs: JumpStartModelSpecs):
        """Imports a public JumpStart model to a hub."""
        hub_content_display_name = self.studio_metadata_map[model_specs.model_id]["name"]
        hub_content_description = (
            "This is a curated model based "
            f"off the public JumpStart model {hub_content_display_name}"
        )
        hub_content_markdown = self._dst_s3_filesystem.get_markdown_s3_reference(
            model_specs
        ).get_uri()

        hub_content_document = self._document_creator.make_hub_content_document(
            model_specs=model_specs
        )

        self._sm_client.import_hub_content(
            HubName=self.curated_hub_name,
            HubContentName=model_specs.model_id,
            HubContentVersion=model_specs.version,
            HubContentType=CURATED_HUB_CONTENT_TYPE,
            DocumentSchemaVersion=CURATED_HUB_DEFAULT_DOCUMENT_SCHEMA_VERSION,
            HubContentDisplayName=hub_content_display_name,
            HubContentDescription=hub_content_description,
            HubContentMarkdown=hub_content_markdown,
            HubContentDocument=hub_content_document,
        )

    def delete_models(self, model_ids: List[PublicHubModel]):
        """Deletes all versions of each model"""
        # TODO: Add to flags when multiple versions per upload is possible
        delete_all_versions = True
        model_specs = self._get_model_specs_for_list(model_ids)
        for model_spec in model_specs:
            self._delete_model_from_curated_hub(model_spec, delete_all_versions)

    def _delete_model_from_curated_hub(
        self,
        model_specs: JumpStartModelSpecs,
        delete_all_versions: bool,
        delete_dependencies: bool = True,
    ):
        """Deletes a hub model content"""
        if delete_dependencies:
            self._delete_model_dependencies_no_content_noop(model_specs)

        if delete_all_versions:
            self._curated_hub_client.delete_all_versions_of_model(model_specs)
        else:
            self._curated_hub_client.delete_version_of_model(
                model_specs.model_id, model_specs.version
            )

    def _delete_model_dependencies_no_content_noop(self, model_specs: JumpStartModelSpecs):
        """Deletes hub content dependencies. If there are no dependencies, it succeeds."""
        try:
            hub_content = self._curated_hub_client.describe_model_version(model_specs)
        except ClientError as ce:
            if ce.response["Error"]["Code"] != "ResourceNotFound":
                raise
            return

        dependencies = self._get_hub_content_dependencies_from_model_document(
            hub_content["HubContentDocument"]
        )
        dependency_s3_keys: List[Dict[str, str]] = []
        for dependency in dependencies:
            dependency_s3_keys.extend(
                self._format_dependency_dst_uris_for_delete_objects(dependency)
            )
        print(f"Deleting HubContent dependencies for {model_specs.model_id}: {dependency_s3_keys}")
        delete_response = self._s3_client.delete_objects(
            Bucket=self.curated_hub_s3_bucket_name,
            Delete={"Objects": dependency_s3_keys, "Quiet": True},
        )

        if "Errors" in delete_response:
            raise Exception(
                "Failed to delete all dependencies"
                f" of model {model_specs.model_id} : {delete_response['Errors']}"
            )

    def _get_hub_content_dependencies_from_model_document(
        self, hub_content_document: str
    ) -> List[Dependency]:
        """Creates dependency list from hub content document"""
        hub_content_document_json = json.loads(hub_content_document)
        return list(map(self._cast_dict_to_dependency, hub_content_document_json["Dependencies"]))

    def _cast_dict_to_dependency(self, dependency: Dict[str, str]) -> Dependency:
        """Converts a dictionary to a HubContent dependency"""
        return Dependency(
            DependencyOriginPath=dependency["DependencyOriginPath"],
            DependencyCopyPath=dependency["DependencyCopyPath"],
            DependencyType=dependency["DependencyType"],
        )

    def _format_dependency_dst_uris_for_delete_objects(
        self, dependency: Dependency
    ) -> List[Dict[str, str]]:
        """Formats hub content dependency s3 keys"""
        s3_keys = []
        s3_object_reference = create_s3_object_reference_from_uri(dependency.DependencyCopyPath)

        if self._is_s3_key_a_prefix(s3_object_reference.key):
            keys = find_objects_under_prefix(
                bucket=s3_object_reference.bucket,
                prefix=s3_object_reference.key,
                s3_client=self._s3_client,
            )
            s3_keys.extend(keys)
        else:
            s3_keys.append(s3_object_reference.key)

        formatted_keys = []
        for key in s3_keys:
            formatted_keys.append({"Key": key})

        return formatted_keys

    def _is_s3_key_a_prefix(self, s3_key: str) -> bool:
        """Checks of s3 key is a directory"""
        return s3_key.endswith("/")
