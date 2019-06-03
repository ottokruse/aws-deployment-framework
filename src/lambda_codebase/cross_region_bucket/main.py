# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
The Cross Region S3 Bucket main that is called when ADF is installed to create the bucket in the master account in the deployment region
"""


from typing import Mapping, Any, Tuple, MutableMapping
from dataclasses import dataclass, asdict
import logging
import json
import secrets
import string
import boto3
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
Region = str
S3Client = Any

# Globals:
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)
S3CLIENTS: MutableMapping[Region, S3Client] = {}


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
    policy = event["ResourceProperties"].get("PolicyDocument")
    bucket_name_prefix = event["ResourceProperties"]["BucketNamePrefix"]
    bucket_name, created = ensure_bucket(region, bucket_name_prefix)
    ensure_bucket_encryption(bucket_name, region)
    if policy:
        ensure_bucket_policy(bucket_name, region, policy)
    return PhysicalResource(region, bucket_name, created).as_cfn_response()


@update()
def update_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    region = event["ResourceProperties"]["Region"]
    policy = event["ResourceProperties"].get("PolicyDocument")
    bucket_name_prefix = event["ResourceProperties"]["BucketNamePrefix"]
    bucket_name, created = ensure_bucket(region, bucket_name_prefix)
    ensure_bucket_encryption(bucket_name, region)
    if policy:
        ensure_bucket_policy(bucket_name, region, policy)
    return PhysicalResource(region, bucket_name, created).as_cfn_response()


@delete()
def delete_(event: Mapping[str, Any], _context: Any) -> None:
    try:
        physical_resource = PhysicalResource.from_json(event["PhysicalResourceId"])
    except InvalidPhysicalResourceId:
        raw_physical_resource = event["PhysicalResourceId"]
        LOGGER.info(
            "Unrecognized physical resource: %s. Assuming no delete necessary",
            raw_physical_resource
        )
    else:
        if physical_resource.created:
            s3_client = boto3.client("s3", region_name=physical_resource.region)
            try:
                s3_client.delete_bucket(Bucket=physical_resource.bucket_name)
                LOGGER.info("Deleted bucket %s", physical_resource.bucket_name)
            except s3_client.exceptions.NoSuchBucket:
                LOGGER.info(
                    "Bucket %s does not exist (already deleted?)",
                    physical_resource.bucket_name
                )


def ensure_bucket(region: str, bucket_name_prefix: str) -> Tuple[BucketName, Created]:
    s3_client = get_s3_client(region)
    while True:
        bucket_name_suffix = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(6))
        bucket_name = "{0}-{1}".format(bucket_name_prefix, bucket_name_suffix)
        try:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
            LOGGER.info("Bucket created: %s", bucket_name)
            return bucket_name, True
        except s3_client.exceptions.BucketAlreadyExists:
            LOGGER.info(
                "Bucket name %s already taken, trying another one ...",
                bucket_name
            )


def ensure_bucket_encryption(bucket_name: str, region: str) -> None:
    s3_client = get_s3_client(region)
    s3_client.put_bucket_encryption(
        Bucket=bucket_name,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
            ]
        },
    )


def ensure_bucket_policy(bucket_name: str, region: str, policy: MutableMapping) -> None:
    s3_client = get_s3_client(region)
    for action in policy["Statement"]:
        action["Resource"] = [
            "arn:aws:s3:::{0}".format(bucket_name), "arn:aws:s3:::{0}/*".format(bucket_name)
        ]
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))


def get_s3_client(region: str) -> S3Client:
    if region in S3CLIENTS:
        return S3CLIENTS[region]
    s3_client = boto3.client("s3", region_name=region)
    S3CLIENTS[region] = s3_client
    return s3_client
