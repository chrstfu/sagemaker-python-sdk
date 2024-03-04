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
"""This module contains utilities related to SageMaker JumpStart."""
from __future__ import absolute_import
import unittest

from mock.mock import Mock

from sagemaker.jumpstart.curated_hub.hub_client import CuratedHubClient
from sagemaker.jumpstart.curated_hub.constants import (
    CURATED_HUB_DEFAULT_DESCRIPTION,
    HubContentType,
)
from sagemaker.jumpstart.curated_hub.accessors.s3_object_reference import (
    S3ObjectLocation,
)


class HubClientTest(unittest.TestCase):
    def setUp(self):
        self.mock_curated_hub_client = CuratedHubClient("mock_hub_name", "us-west-2")

    def test_create_hub(self):
        hub_name = "hub_name"
        mock_s3_config = S3ObjectLocation(bucket="hub_bucket_name", key="")
        self.mock_curated_hub_client._sm_client = Mock()

        self.mock_curated_hub_client.create_hub(hub_name, mock_s3_config)

        self.mock_curated_hub_client._sm_client.create_hub.assert_called_with(
            HubName=hub_name,
            HubDescription=CURATED_HUB_DEFAULT_DESCRIPTION,  # TODO verify description
            HubDisplayName=hub_name,
            HubSearchKeywords=[],
            S3StorageConfig={
                "S3OutputPath": mock_s3_config.get_uri(),
            },
            Tags=[],
        )

    def test_describe_model(self):
        model_specs = Mock()
        model_specs.model_id = "model_id"
        model_specs.version = "version"
        self.mock_curated_hub_client._sm_client = Mock()

        self.mock_curated_hub_client.describe_model_version(model_specs)

        self.mock_curated_hub_client._sm_client.describe_hub_content.assert_called_with(
            HubName=self.mock_curated_hub_client.curated_hub_name,
            HubContentName=model_specs.model_id,
            HubContentType=HubContentType.MODEL,
            HubContentVersion=model_specs.version,
        )

    def test_delete_version_of_model(self):
        model_id = "model_id"
        version = "version"
        self.mock_curated_hub_client._sm_client = Mock()

        self.mock_curated_hub_client.delete_version_of_model(model_id, version)

        self.mock_curated_hub_client._sm_client.delete_hub_content.assert_called_with(
            HubName=self.mock_curated_hub_client.curated_hub_name,
            HubContentName=model_id,
            HubContentType=HubContentType.MODEL,
            HubContentVersion=version,
        )

    def test_list_hub_content_versions_no_content_noop(self):
        hub_content_name = "hub_content_name"
        mock_sm_client = Mock()
        self.mock_curated_hub_client._sm_client = mock_sm_client
        mock_sm_client.list_hub_content_versions.return_value = {"HubContentSummaries": []}

        self.mock_curated_hub_client._list_hub_content_versions_no_content_noop(hub_content_name)

        self.mock_curated_hub_client._sm_client.list_hub_content_versions.assert_called_with(
            HubName=self.mock_curated_hub_client.curated_hub_name,
            HubContentName=hub_content_name,
            HubContentType=HubContentType.MODEL,
        )