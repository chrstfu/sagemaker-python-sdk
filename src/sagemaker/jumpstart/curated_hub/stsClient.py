from typing import Any
from typing import Match
from typing import Optional
from datetime import datetime

import boto3

def convert_iso_to_yyyymmdd_hhmm(iso_time: str) -> str:
    """Convert iso time string (generated from assign_timestamp) to 'YYYYMMDD-HHMM'-formatted time."""
    return datetime.fromisoformat(iso_time.rstrip("Z")).strftime("%Y%m%d-%H%M")

def assign_timestamp() -> str:
    """Return the current UTC timestamp in ISO Format."""
    return datetime.utcnow().isoformat() + "Z"


class StsClient:
    """Boto3 client to access STS."""

    def __init__(self) -> None:
        """Creates the boto3 client for STS."""
        self._client = boto3.client(service_name="sts")

    def get_region(self) -> str:
        """Return the AWS region from the client meta information."""
        return self._client.meta.region_name

    def get_account_id(self) -> str: # TODO: Verify this works in all cases
        """Returns the AWS account id associated with the caller identity."""
        identity = self._client.get_caller_identity()
        caller_arn = identity["Arn"]
        role_arn_components = caller_arn.split(":")
        return role_arn_components[4]
    
    def get_boto3_session_from_role_arn(self, role_arn: str, **assume_role_kwargs: Any) -> boto3.Session:
        """Return boto3 session using sts.assume_role.

        kwarg arguments are passed to `assume_role` boto3 call.
        See: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/sts.html#STS.Client.assume_role
        """

        kwargs = {
            "RoleArn": role_arn,
            "RoleSessionName": "JumpStartModelHub-" + convert_iso_to_yyyymmdd_hhmm(assign_timestamp()),
        }
        kwargs.update(assume_role_kwargs)

        assumed_role_object = self._client.assume_role(**kwargs)

        credentials = assumed_role_object["Credentials"]

        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
        )




