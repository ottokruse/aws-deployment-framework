sam build && \
sam package --s3-bucket us-east-1.4.sam.otto-aws.com --output-template-file packaged.yaml && \
aws cloudformation deploy --template-file packaged.yaml --stack-name adf-base-ensure --region us-east-1 \
                          --parameter-overrides DeploymentAccountMainRegion=eu-west-1 DeploymentAccountEmailAddress=ottokruse+xx@gmail.com \
                          --capabilities CAPABILITY_NAMED_IAM
