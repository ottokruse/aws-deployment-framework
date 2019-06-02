# Copyright 2019 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
The Account main that is called when ADF is installed to initially create the deployment account if required
"""

from typing import Mapping, Any, Tuple
from dataclasses import dataclass, asdict
import logging
import time
import json
import boto3
from cfn_custom_resource import (  # pylint: disable=unused-import
    lambda_handler,
    create,
    update,
    delete,
)

# Type aliases:
Data = Mapping[str, str]
PhysicalResourceId = str
AccountId = str
CloudFormationResponse = Tuple[PhysicalResourceId, Data]

# Globals:
ORGANIZATION_CLIENT = boto3.client("organizations")
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class InvalidPhysicalResourceId(Exception):
    pass


@dataclass
class PhysicalResource:
    account_id: str
    account_name: str
    account_email: str

    @classmethod
    def from_json(cls, json_string: PhysicalResourceId) -> "PhysicalResource":
        try:
            return cls(**json.loads(json_string))
        except json.JSONDecodeError as err:
            raise InvalidPhysicalResourceId from err

    def as_cfn_response(self) -> CloudFormationResponse:
        physical_resource_id = json.dumps(asdict(self))
        data = {
            "AccountId": self.account_id,
            "AccountName": self.account_name,
            "AccountEmail": self.account_email,
        }
        return physical_resource_id, data


@create()
def create_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    account_name = event["ResourceProperties"]["AccountName"]
    account_email = event["ResourceProperties"]["AccountEmailAddress"]
    cross_account_access_role_name = event["ResourceProperties"][
        "CrossAccountAccessRoleName"
    ]
    account_id = ensure_account(
        account_name, account_email, cross_account_access_role_name
    )
    return PhysicalResource(account_id, account_name, account_email).as_cfn_response()


@update()
def update_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    account_name = event["ResourceProperties"]["AccountName"]
    account_email = event["ResourceProperties"]["AccountEmailAddress"]
    cross_account_access_role_name = event["ResourceProperties"][
        "CrossAccountAccessRoleName"
    ]
    account_id = ensure_account(
        account_name, account_email, cross_account_access_role_name
    )
    return PhysicalResource(account_id, account_name, account_email).as_cfn_response()


@delete()
def delete_(event, _context):
    try:
        physical_resource = PhysicalResource.from_json(event["PhysicalResourceId"])
    except InvalidPhysicalResourceId:
        raw_physical_resource = event["PhysicalResourceId"]
        LOGGER.info(
            "Unrecognized physical resource: %s. Assuming no delete necessary", raw_physical_resource
        )
        return

    raise NotImplementedError(
        "Cannot delete account %s (%s). This is a manual process",
        physical_resource.account_id,
        physical_resource.account_name
    )


def ensure_account(
        account_name: str, account_email: str, cross_account_access_role_name: str
    ) -> AccountId:
    LOGGER.info("Creating account ...")
    create_account = ORGANIZATION_CLIENT.create_account(
        Email=account_email,
        AccountName=account_name,
        RoleName=cross_account_access_role_name,
        IamUserAccessToBilling="ALLOW",
    )
    request_id = create_account["CreateAccountStatus"]["Id"]
    LOGGER.info("Account creation requested, request ID: %s", request_id)

    while True:
        account_status = ORGANIZATION_CLIENT.describe_create_account_status(
            CreateAccountRequestId=request_id
        )
        if account_status["CreateAccountStatus"]["State"] == "FAILED":
            reason = account_status["CreateAccountStatus"]["FailureReason"]
            raise Exception("Failed to create account because %s", reason)
        if account_status["CreateAccountStatus"]["State"] == "IN_PROGRESS":
            LOGGER.info("Account creation still in progress, waiting ...")
            time.sleep(5)
        else:
            account_id = account_status["CreateAccountStatus"]["AccountId"]
            LOGGER.info("Account created: %s", account_id)
            return account_id
