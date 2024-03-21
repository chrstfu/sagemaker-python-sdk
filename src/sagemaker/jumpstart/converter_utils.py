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
"""This module stores CuratedHub converter utilities for JumpStart."""
from __future__ import absolute_import

import re
from typing import Any, Dict, List
from sagemaker.jumpstart.enums import ModelSpecKwargType, NamingConventionType


def camel_to_snake(camel_case_string: str) -> str:
    """Converts camelCaseString or UpperCamelCaseString to snake_case_string."""
    snake_case_string = re.sub("(.)([A-Z][a-z]+)", r"\1_\2", camel_case_string)
    return re.sub("([a-z0-9])([A-Z])", r"\1_\2", snake_case_string).lower()


def snake_to_upper_camel(snake_case_string: str) -> str:
    """Converts snake_case_string to UpperCamelCaseString."""
    upper_camel_case_string = "".join(word.title() for word in snake_case_string.split("_"))
    return upper_camel_case_string


def walk_and_apply_json(json_obj: Dict[Any, Any], apply):
    """Recursively walks a json object and applies a given function to the keys."""

    def _walk_and_apply_json(json_obj, new):
        if isinstance(json_obj, dict):
            if isinstance(new, dict):
                for key, value in json_obj.items():
                    new_key = apply(key)
                    if isinstance(value, dict):
                        new[new_key] = {}
                        _walk_and_apply_json(value, new=new[new_key])
                    elif isinstance(value, list):
                        new[new_key] = []
                        for item in value:
                            _walk_and_apply_json(item, new=new[new_key])
                    else:
                        new[new_key] = value
            elif isinstance(new, list):
                new.append(_walk_and_apply_json(json_obj, new={}))
        else:
            new.append(json_obj)
        return new

    return _walk_and_apply_json(json_obj, new={})


def get_model_spec_arg_keys(
    arg_type: ModelSpecKwargType,
    naming_convention: NamingConventionType = NamingConventionType.DEFAULT,
) -> List[str]:
    """Returns a list of arg keys for a specific model spec arg type.

    Args:
        arg_type (ModelSpecKwargType): Type of the model spec's kwarg.
        naming_convention (NamingConventionType): Type of naming convention to return.

    Raises:
        ValueError: If the naming convention is not valid.

    """
    arg_keys = []
    if arg_type == ModelSpecKwargType.DEPLOY:
        arg_keys = ["ModelDataDownloadTimeout", "ContainerStartupHealthCheckTimeout"]
    elif arg_type == ModelSpecKwargType.ESTIMATOR:
        arg_keys = [
            "EncryptInterContainerTraffic",
            "MaxRuntimeInSeconds",
            "DisableOutputCompression",
        ]
    elif arg_type == ModelSpecKwargType.MODEL:
        arg_keys = []
    elif arg_type == ModelSpecKwargType.FIT:
        arg_keys = []
    if naming_convention == NamingConventionType.SNAKE_CASE:
        return camel_to_snake(arg_keys)
    elif naming_convention == NamingConventionType.UPPER_CAMEL_CASE:
        return arg_keys
    else:
        raise ValueError("Please provide a valid naming convention.")


def get_model_spec_kwargs_from_hub_content_document(
    arg_type: "ModelSpecKwargType",
    hub_content_document: Dict[str, Any],
    naming_convention: NamingConventionType = NamingConventionType.UPPER_CAMEL_CASE,
) -> Dict[str, Any]:
    kwargs = dict()
    keys = get_model_spec_arg_keys(arg_type, naming_convention=naming_convention)
    for k in keys:
        kwarg_value = hub_content_document.get(k, None)
        if kwarg_value is not None:
            kwargs[k] = kwarg_value
    return kwargs
