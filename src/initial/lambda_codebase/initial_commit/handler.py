try:
    from initial_commit import lambda_handler # pylint: disable=unused-import
except Exception as e:  # pylint: disable=broad-except
    from urllib.request import Request, urlopen
    import json

    def lambda_handler(event, _context, e=e):
        response = dict(
            LogicalResourceId=event["LogicalResourceId"],
            PhysicalResourceId=event.get("PhysicalResourceId", "NOT_YET_CREATED"),
            Status="FAILED",
            RequestId=event["RequestId"],
            StackId=event["StackId"],
            Reason=str(e),
        )
        urlopen(
            Request(
                event["ResponseURL"],
                data=json.dumps(response).encode(),
                headers={"content-type": ""},
                method="PUT",
            )
        )
