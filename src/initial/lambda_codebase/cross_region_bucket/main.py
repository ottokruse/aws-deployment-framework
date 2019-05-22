from typing import Mapping, Any, Tuple
from dataclasses import dataclass, asdict
import logging
import json
import boto3
import secrets
from cfn_custom_resource import (  # pylint: disable=unused-import
    lambda_handler,
    create,
    update,
    delete,
)

# Type aliases:
BucketName = str
Data = Mapping[str, str]
PhysicalResourceId = str
Created = bool
CloudFormationResponse = Tuple[PhysicalResourceId, Data]

# Globals:
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class InvalidPhysicalResourceId(Exception):
    pass


@dataclass
class PhysicalResource:
    region: str
    bucket_name: str
    created: bool

    @classmethod
    def from_json(cls, json_string: PhysicalResourceId) -> "PhysicalResource":
        try:
            return cls(**json.loads(json_string))
        except json.JSONDecodeError as err:
            raise InvalidPhysicalResourceId from err

    def as_cfn_response(self) -> CloudFormationResponse:
        physical_resource_id = json.dumps(asdict(self))
        data = {
            "Region": self.region,
            "BucketName": self.bucket_name,
            "Created": json.dumps(self.created),
        }
        return physical_resource_id, data


@create()
def create_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    region = event["ResourceProperties"]["Region"]
    bucket_name_prefix = event["ResourceProperties"]["BucketNamePrefix"]
    bucket_name, created = ensure_bucket(region, bucket_name_prefix)
    return PhysicalResource(region, bucket_name, created).as_cfn_response()


@update()
def update_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    region = event["ResourceProperties"]["Region"]
    bucket_name_prefix = event["ResourceProperties"]["BucketNamePrefix"]
    bucket_name, created = ensure_bucket(region, bucket_name_prefix)
    return PhysicalResource(region, bucket_name, created).as_cfn_response()


@delete()
def delete_(event: Mapping[str, Any], _context: Any) -> None:
    try:
        physical_resource = PhysicalResource.from_json(event["PhysicalResourceId"])
    except InvalidPhysicalResourceId:
        raw_physical_resource = event["PhysicalResourceId"]
        LOGGER.info(
            f"Unrecognized physical resource: {raw_physical_resource}. Assuming no delete necessary"
        )
    else:
        if physical_resource.created:
            s3_client = boto3.client("s3", region_name=physical_resource.region)
            try:
                s3_client.delete_bucket(Bucket=physical_resource.bucket_name)
                LOGGER.info(f"Deleted bucket {physical_resource.bucket_name}")
            except s3_client.exceptions.NoSuchBucket:
                LOGGER.info(
                    f"Bucket {physical_resource.bucket_name} does not exist (already deleted?)"
                )


def ensure_bucket(region: str, bucket_name_prefix: str) -> Tuple[BucketName, Created]:
    s3_client = boto3.client("s3", region_name=region)
    while True:
        bucket_name_suffix = secrets.token_hex(4)
        bucket_name = f"{bucket_name_prefix}-{bucket_name_suffix}"
        try:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
            LOGGER.info(f"Bucket created: {bucket_name}")
            return bucket_name, True
        except s3_client.exceptions.BucketAlreadyOwnedByYou:
            LOGGER.info(f"Bucket already exists: {bucket_name}")
            return bucket_name, False
        except s3_client.exceptions.BucketAlreadyExists:
            LOGGER.info(
                f"Bucket name {bucket_name} already taken, trying another one ..."
            )
