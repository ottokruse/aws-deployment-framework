from typing import Mapping, Optional, Union, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import os
import boto3
import jinja2
from cfn_custom_resource import lambda_handler, create, update, delete # pylint: disable=unused-import


PhysicalResourceId = str
Data = Mapping[str, str]

HERE = Path(__file__).parent
NOT_YET_CREATED = "NOT_YET_CREATED"


@dataclass
class CustomResourceProperties:
    ServiceToken: str
    RepositoryArn: str
    DirectoryName: str
    DeploymentAccountRegion: str
    TargetRegions: List[str]
    NotificationEmailAddress: str

    def __post_init__(self):
        self.TargetRegions = [
            region.strip() for region in self.TargetRegions.split(",")
        ]


@dataclass
class Event:
    RequestType: str
    ServiceToken: str
    ResponseURL: str
    StackId: str
    RequestId: str
    ResourceType: str
    LogicalResourceId: str
    ResourceProperties: CustomResourceProperties

    def __post_init__(self):
        self.ResourceProperties = CustomResourceProperties(
            **self.ResourceProperties  # pylint: disable=not-a-mapping
        )


class FileMode(Enum):
    EXECUTABLE = "EXECUTABLE"
    NORMAL = "NORMAL"
    SYMLINK = "SYMLINK"


@dataclass
class FileToCommit:
    filePath: str
    fileMode: FileMode
    fileContent: bytes

    def as_dict(self) -> Dict[str, Union[str, bytes]]:
        return {
            "filePath": self.filePath,
            "fileMode": self.fileMode.value,
            "fileContent": self.fileContent,
        }


@dataclass
class CreateEvent(Event):
    pass


@dataclass
class UpdateEvent(Event):
    PhysicalResourceId: str
    OldResourceProperties: CustomResourceProperties

    def __post_init__(self):
        self.OldResourceProperties = CustomResourceProperties(
            **self.OldResourceProperties  # pylint: disable=not-a-mapping
        )


cc_client = boto3.client("codecommit")


@create()
def create_(event: Mapping[str, Any], _context: Any) -> Tuple[PhysicalResourceId, Data]:
    create_event = CreateEvent(**event)
    repo_name = repo_arn_to_name(create_event.ResourceProperties.RepositoryArn)
    directory = create_event.ResourceProperties.DirectoryName
    adf_config = create_adf_config_file(create_event.ResourceProperties)
    files_to_commit = [adf_config, *get_files_to_commit(directory)]
    print(f"Will commit these files: {[f.filePath for f in files_to_commit]}")
    commit_response = cc_client.create_commit(
        repositoryName=repo_name,
        branchName="master",
        authorName="AWS ADF Builders Team",
        email="adf-builders@amazon.com",
        commitMessage="Initial commit",
        putFiles=[f.as_dict() for f in files_to_commit],
    )

    return commit_response["commitId"], {}


@update()
def update_(event: Mapping[str, Any], _context: Any) -> Tuple[PhysicalResourceId, Data]:
    return event["PhysicalResourceId"], {}


@delete()
def delete_(_event, _context):
    pass


def repo_arn_to_name(repo_arn: str) -> str:
    return repo_arn.split(":")[-1]


def get_files_to_commit(directoryName: str) -> List[FileToCommit]:
    path = HERE / directoryName
    return [
        FileToCommit(
            str(get_relative_name(entry, directoryName)),
            FileMode.NORMAL if not os.access(entry, os.X_OK) else FileMode.EXECUTABLE,
            entry.read_bytes(),
        )
        for entry in path.glob("**/*")
        if not entry.is_dir()
    ]


def get_relative_name(path: Path, directoryName: str) -> Path:
    """
    Search for the last occurance of <directoryName> in <path> and return only the trailing part of <path>

    >>> get_relative_name(Path('/foo/test/bar/test/xyz/abc.py') ,'test')
    Path('xyz/abc.py')
    """
    index = list(reversed(path.parts)).index(directoryName)
    return Path(*path.parts[-index:])


def create_adf_config_file(props: CustomResourceProperties) -> FileToCommit:
    template = HERE / "adf-config.yml.j2"
    adf_config = jinja2.Template(template.read_text()).render(vars(props)).encode()

    with open("/tmp/adf-config.yml", "wb") as f:
        f.write(adf_config)
    return FileToCommit("adf-config.yml", FileMode.NORMAL, adf_config)
