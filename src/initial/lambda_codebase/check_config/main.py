from typing import Mapping, Any, Tuple, Union
from dataclasses import dataclass, asdict
import logging
import json
import boto3
from cfn_custom_resource import (  # pylint: disable=unused-import
    lambda_handler,
    create,
    update,
    delete,
    ResourceError,
)

# Type aliases:
Data = Mapping[str, str]
PhysicalResourceId = Union[None, str]
Created = bool
OrgUnitId = str
CloudFormationResponse = Tuple[PhysicalResourceId, Data]

# Globals:
ORGANIZATION_CLIENT = boto3.client("organizations")
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


class InvalidPhysicalResourceId(Exception):
    pass


@dataclass
class PhysicalResource:
    deployment_account_id: str

    @classmethod
    def from_json(cls, json_string: PhysicalResourceId) -> "PhysicalResource":
        try:
            return cls(**json.loads(json_string))
        except json.JSONDecodeError as err:
            raise InvalidPhysicalResourceId from err

    def as_cfn_response(self) -> Tuple[PhysicalResourceId, Data]:
        physical_resource_id = None
        data = {
            "DeploymentAccountId": self.deployment_account_id,
        }
        return physical_resource_id, data


@create()
def create_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    deployment_org_unit_id = event["ResourceProperties"]["DeploymentOrgUnitId"]
    deployment_account_id = check_existing_deployment_account(deployment_org_unit_id)
    return PhysicalResource(deployment_account_id).as_cfn_response()


@update()
def update_(event: Mapping[str, Any], _context: Any) -> CloudFormationResponse:
    deployment_org_unit_id = event["ResourceProperties"]["DeploymentOrgUnitId"]
    deployment_account_id = check_existing_deployment_account(deployment_org_unit_id)
    return PhysicalResource(deployment_account_id).as_cfn_response()


@delete()
def delete_(event: Mapping[str, Any], _context: Any):
    pass

def check_existing_deployment_account(deployment_org_unit_id) -> str:
    params = {"ParentId": deployment_org_unit_id}
    while True:
        accounts = ORGANIZATION_CLIENT.list_accounts_for_parent(**params)
        if "Accounts" in accounts and accounts["Accounts"]:
            if len(accounts["Accounts"]) > 1:
                raise ResourceError(f"Deployment ORG unit {deployment_org_unit_id} ontains multiple accounts")
            account_id = accounts["Accounts"][0]["Id"]
            LOGGER.info(f"Deployment account found: {account_id}")
            return account_id
        if not "NextToken" in accounts:
            raise ResourceError(f"Deployment account not found in Deployment ORG unit {deployment_org_unit_id}")
        params["NextToken"] = accounts["NextToken"]
