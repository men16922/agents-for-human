#!/usr/bin/env python3
"""Generate the serverless application CloudFormation template (no AWS calls)."""

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def ref(name):
    return {"Ref": name}


def arn(name):
    return {"Fn::GetAtt": [name, "Arn"]}


def sub(value):
    return {"Fn::Sub": value}


def statement(actions, resources):
    return {"Effect": "Allow", "Action": actions, "Resource": resources}


def template():
    resources = {}
    result = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Rehearsal: on-demand AgentCore, Lambda, DynamoDB, Step Functions and CDN",
        "Parameters": {
            k: {"Type": "String"}
            for k in [
                "ArtifactsBucket",
                "SiteBucket",
                "CommerceTable",
                "ControlTable",
                "CodeKey",
                "CodeVersion",
            ]
        },
        "Resources": resources,
    }
    commerce_arn = sub(
        "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${CommerceTable}"
    )
    control_arn = sub(
        "arn:${AWS::Partition}:dynamodb:${AWS::Region}:${AWS::AccountId}:table/${ControlTable}"
    )
    read_db = ["dynamodb:GetItem", "dynamodb:Query"]
    write_db = read_db + ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:TransactWriteItems"]
    logs = statement(
        ["logs:CreateLogStream", "logs:PutLogEvents"],
        sub(
            "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/rehearsal-serverless-*:log-stream:*"
        ),
    )

    def role(name, service, policies):
        resources[name] = {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": service},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "Policies": [
                    {
                        "PolicyName": "ScopedRehearsal",
                        "PolicyDocument": {"Version": "2012-10-17", "Statement": policies},
                    }
                ],
                "Tags": [{"Key": "Project", "Value": "rehearsal-serverless"}],
            },
        }

    role(
        "CommerceRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(write_db, commerce_arn),
            statement(["dynamodb:GetItem", "dynamodb:ConditionCheckItem"], control_arn),
        ],
    )
    role(
        "SellerRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(write_db, commerce_arn),
            statement(["dynamodb:GetItem", "dynamodb:ConditionCheckItem"], control_arn),
        ],
    )
    role(
        "ApiRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(read_db, commerce_arn),
            statement(write_db, control_arn),
            statement(["states:StartExecution"], ref("Workflow")),
        ],
    )
    runtime_arn = {"Fn::GetAtt": ["Runtime", "AgentRuntimeArn"]}
    role(
        "InvokeRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(["dynamodb:GetItem"], control_arn),
            statement(
                ["bedrock-agentcore:InvokeAgentRuntime"],
                [runtime_arn, sub("${Runtime.AgentRuntimeArn}/*")],
            ),
        ],
    )
    role(
        "FinalizeRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(read_db, commerce_arn),
            statement(write_db, control_arn),
            statement(
                ["s3:PutObject"],
                sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/*/commerce-evidence.json"),
            ),
            statement(
                ["bedrock-agentcore:StopRuntimeSession"],
                [runtime_arn, sub("${Runtime.AgentRuntimeArn}/*")],
            ),
        ],
    )
    role(
        "AgentRole",
        "bedrock-agentcore.amazonaws.com",
        [
            statement(["lambda:InvokeFunction"], arn("CommerceFunction")),
            {
                **statement(["dynamodb:GetItem", "dynamodb:UpdateItem"], control_arn),
                "Condition": {
                    "ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["RUN#rehearsal-*"]}
                },
            },
            statement(
                ["s3:PutObject"],
                [
                    sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/*/" + suffix)
                    for suffix in ["usage.sqlite3", "tools.json", "runtime/*"]
                ],
            ),
            statement(
                ["s3:GetObject", "s3:GetObjectVersion"],
                sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/packages/*"),
            ),
            statement(["s3:ListBucket"], sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}")),
            statement(
                ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                [
                    sub(
                        "arn:${AWS::Partition}:bedrock:*::foundation-model/amazon.nova-2-lite-v1:0"
                    ),
                    sub(
                        "arn:${AWS::Partition}:bedrock:${AWS::Region}:${AWS::AccountId}:inference-profile/global.amazon.nova-2-lite-v1:0"
                    ),
                ],
            ),
            statement(
                [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                sub(
                    "arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/bedrock-agentcore/runtimes/rehearsal_serverless*"
                ),
            ),
        ],
    )
    resources["Runtime"] = {
        "Type": "AWS::BedrockAgentCore::Runtime",
        "Properties": {
            "AgentRuntimeName": "rehearsal_serverless",
            "AgentRuntimeArtifact": {
                "CodeConfiguration": {
                    "Code": {
                        "S3": {
                            "Bucket": ref("ArtifactsBucket"),
                            "Prefix": ref("CodeKey"),
                            "VersionId": ref("CodeVersion"),
                        }
                    },
                    "Runtime": "PYTHON_3_12",
                    "EntryPoint": ["main.py"],
                }
            },
            "RoleArn": arn("AgentRole"),
            "NetworkConfiguration": {"NetworkMode": "PUBLIC"},
            "ProtocolConfiguration": "HTTP",
            "LifecycleConfiguration": {"IdleRuntimeSessionTimeout": 60, "MaxLifetime": 420},
            "EnvironmentVariables": {
                "AWS_REGION": ref("AWS::Region"),
                "CONTROL_TABLE": ref("ControlTable"),
                "ARTIFACTS_BUCKET": ref("ArtifactsBucket"),
                "COMMERCE_FUNCTION": ref("CommerceFunction"),
                "MODEL_ID": "global.amazon.nova-2-lite-v1:0",
                "RATE_SOURCE": "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/us-west-2/index.json",
            },
            "Tags": {"Project": "rehearsal-serverless"},
        },
    }
    for kind in ["Api", "Commerce", "Seller", "Invoke", "Finalize"]:
        name = "rehearsal-serverless-" + kind.lower()
        resources[kind + "Logs"] = {
            "Type": "AWS::Logs::LogGroup",
            "Properties": {"LogGroupName": "/aws/lambda/" + name, "RetentionInDays": 7},
        }
        environment = {
            "FUNCTION_ROLE": kind.lower(),
            "COMMERCE_TABLE": ref("CommerceTable"),
            "CONTROL_TABLE": ref("ControlTable"),
            "ARTIFACTS_BUCKET": ref("ArtifactsBucket"),
        }
        if kind == "Api":
            environment["WORKFLOW_ARN"] = ref("Workflow")
        if kind in {"Invoke", "Finalize"}:
            environment["RUNTIME_ARN"] = runtime_arn
        resources[kind + "Function"] = {
            "Type": "AWS::Lambda::Function",
            "DependsOn": [kind + "Logs"],
            "Properties": {
                "FunctionName": name,
                "Role": arn(kind + "Role"),
                "Runtime": "python3.12",
                "Architectures": ["arm64"],
                "Handler": "main.handler",
                "MemorySize": 512,
                "Timeout": 480 if kind == "Invoke" else 30,
                "Code": {
                    "S3Bucket": ref("ArtifactsBucket"),
                    "S3Key": ref("CodeKey"),
                    "S3ObjectVersion": ref("CodeVersion"),
                },
                "Environment": {"Variables": environment},
                "Tags": [{"Key": "Project", "Value": "rehearsal-serverless"}],
            },
        }
    role(
        "WorkflowRole",
        "states.amazonaws.com",
        [
            statement(
                ["lambda:InvokeFunction"],
                [arn(k + "Function") for k in ["Seller", "Invoke", "Finalize"]],
            )
        ],
    )

    def task(function, payload, **kwargs):
        return {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {"FunctionName": arn(function), "Payload": payload},
            "OutputPath": "$.Payload",
            **kwargs,
        }

    definition = {
        "StartAt": "Bootstrap",
        "TimeoutSeconds": 660,
        "States": {
            "Bootstrap": task(
                "SellerFunction",
                {"run_id.$": "$.run_id", "operation": "bootstrap"},
                Next="Execute",
                Catch=[
                    {"ErrorEquals": ["States.ALL"], "ResultPath": "$.failure", "Next": "Finalize"}
                ],
            ),
            "Execute": {
                "Type": "Parallel",
                "ResultPath": "$.branches",
                "Next": "Finalize",
                "Catch": [
                    {"ErrorEquals": ["States.ALL"], "ResultPath": "$.failure", "Next": "Finalize"}
                ],
                "Branches": [
                    {
                        "StartAt": "Invoke",
                        "States": {
                            "Invoke": task("InvokeFunction", {"run_id.$": "$.run_id"}, End=True)
                        },
                    },
                    {
                        "StartAt": "Tick",
                        "States": {
                            "Tick": task("SellerFunction", {"run_id.$": "$.run_id"}, Next="Done"),
                            "Done": {
                                "Type": "Choice",
                                "Choices": [
                                    {
                                        "Variable": "$.done",
                                        "BooleanEquals": True,
                                        "Next": "SellerFinished",
                                    }
                                ],
                                "Default": "Wait",
                            },
                            "Wait": {"Type": "Wait", "Seconds": 2, "Next": "Tick"},
                            "SellerFinished": {"Type": "Succeed"},
                        },
                    },
                ],
            },
            "Finalize": task(
                "FinalizeFunction",
                {"run_id.$": "$.run_id", "workflow.$": "$"},
                End=True,
                Retry=[
                    {"ErrorEquals": ["States.TaskFailed"], "IntervalSeconds": 3, "MaxAttempts": 3}
                ],
            ),
        },
    }
    resources["Workflow"] = {
        "Type": "AWS::StepFunctions::StateMachine",
        "Properties": {
            "StateMachineName": "rehearsal-serverless-demo",
            "StateMachineType": "STANDARD",
            "RoleArn": arn("WorkflowRole"),
            "Definition": definition,
            "Tags": [{"Key": "Project", "Value": "rehearsal-serverless"}],
        },
    }
    resources["Api"] = {
        "Type": "AWS::ApiGatewayV2::Api",
        "Properties": {"Name": "rehearsal-serverless", "ProtocolType": "HTTP"},
    }
    resources["ApiIntegration"] = {
        "Type": "AWS::ApiGatewayV2::Integration",
        "Properties": {
            "ApiId": ref("Api"),
            "IntegrationType": "AWS_PROXY",
            "IntegrationUri": arn("ApiFunction"),
            "PayloadFormatVersion": "2.0",
            "TimeoutInMillis": 29000,
        },
    }
    resources["ApiRoute"] = {
        "Type": "AWS::ApiGatewayV2::Route",
        "Properties": {
            "ApiId": ref("Api"),
            "RouteKey": "$default",
            "Target": sub("integrations/${ApiIntegration}"),
        },
    }
    resources["ApiStage"] = {
        "Type": "AWS::ApiGatewayV2::Stage",
        "Properties": {
            "ApiId": ref("Api"),
            "StageName": "$default",
            "AutoDeploy": True,
            "DefaultRouteSettings": {"ThrottlingBurstLimit": 10, "ThrottlingRateLimit": 5},
        },
    }
    resources["ApiPermission"] = {
        "Type": "AWS::Lambda::Permission",
        "Properties": {
            "Action": "lambda:InvokeFunction",
            "FunctionName": ref("ApiFunction"),
            "Principal": "apigateway.amazonaws.com",
            "SourceArn": sub(
                "arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${Api}/*"
            ),
        },
    }
    resources["SiteAccess"] = {
        "Type": "AWS::CloudFront::OriginAccessControl",
        "Properties": {
            "OriginAccessControlConfig": {
                "Name": "rehearsal-serverless-site",
                "OriginAccessControlOriginType": "s3",
                "SigningBehavior": "always",
                "SigningProtocol": "sigv4",
            }
        },
    }
    resources["Distribution"] = {
        "Type": "AWS::CloudFront::Distribution",
        "Properties": {
            "DistributionConfig": {
                "Enabled": True,
                "DefaultRootObject": "index.html",
                "PriceClass": "PriceClass_100",
                "Origins": [
                    {
                        "Id": "site",
                        "DomainName": sub("${SiteBucket}.s3.${AWS::Region}.amazonaws.com"),
                        "S3OriginConfig": {"OriginAccessIdentity": ""},
                        "OriginAccessControlId": ref("SiteAccess"),
                    },
                    {
                        "Id": "api",
                        "DomainName": sub("${Api}.execute-api.${AWS::Region}.amazonaws.com"),
                        "CustomOriginConfig": {
                            "OriginProtocolPolicy": "https-only",
                            "OriginSSLProtocols": ["TLSv1.2"],
                        },
                    },
                ],
                "DefaultCacheBehavior": {
                    "TargetOriginId": "site",
                    "ViewerProtocolPolicy": "redirect-to-https",
                    "AllowedMethods": ["GET", "HEAD"],
                    "CachedMethods": ["GET", "HEAD"],
                    "Compress": True,
                    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
                },
                "CacheBehaviors": [
                    {
                        "PathPattern": "/api/*",
                        "TargetOriginId": "api",
                        "ViewerProtocolPolicy": "https-only",
                        "AllowedMethods": [
                            "GET",
                            "HEAD",
                            "OPTIONS",
                            "PUT",
                            "PATCH",
                            "POST",
                            "DELETE",
                        ],
                        "CachedMethods": ["GET", "HEAD"],
                        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
                        "OriginRequestPolicyId": "b689b0a8-53d0-40ab-baf2-68738e2966ac",
                    }
                ],
            },
            "Tags": [{"Key": "Project", "Value": "rehearsal-serverless"}],
        },
    }
    resources["SitePolicy"] = {
        "Type": "AWS::S3::BucketPolicy",
        "Properties": {
            "Bucket": ref("SiteBucket"),
            "PolicyDocument": {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"Service": "cloudfront.amazonaws.com"},
                        "Action": "s3:GetObject",
                        "Resource": sub("arn:${AWS::Partition}:s3:::${SiteBucket}/*"),
                        "Condition": {
                            "StringEquals": {
                                "AWS:SourceArn": sub(
                                    "arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}"
                                )
                            }
                        },
                    }
                ],
            },
        },
    }
    # A separate preview runtime has no Lambda invoke or commerce-table authority.
    preview_arn = {"Fn::GetAtt": ["PreviewRuntime", "AgentRuntimeArn"]}
    agent_policies = copy.deepcopy(
        resources["AgentRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"][1:]
    )
    agent_policies[0]["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] = [
        "RUN#preview-*"
    ]
    agent_policies[1]["Resource"] = [
        sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/" + suffix)
        for suffix in ["usage.sqlite3", "runtime/*"]
    ]
    agent_policies.append(
        statement(
            ["s3:GetObject"],
            sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/input.json"),
        )
    )
    role("PreviewAgentRole", "bedrock-agentcore.amazonaws.com", agent_policies)
    preview = copy.deepcopy(resources["Runtime"])
    preview["Properties"].update(
        AgentRuntimeName="rehearsal_serverless_preflight", RoleArn=arn("PreviewAgentRole")
    )
    preview_env = preview["Properties"]["EnvironmentVariables"]
    preview_env.pop("COMMERCE_FUNCTION")
    preview_env["RUNTIME_MODE"] = "preflight"
    resources["PreviewRuntime"] = preview
    role(
        "PreviewInvokeRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(["dynamodb:GetItem"], control_arn),
            statement(
                ["bedrock-agentcore:InvokeAgentRuntime"],
                [preview_arn, sub("${PreviewRuntime.AgentRuntimeArn}/*")],
            ),
        ],
    )
    role(
        "PreviewFinalizeRole",
        "lambda.amazonaws.com",
        [
            logs,
            statement(write_db, control_arn),
            statement(
                ["s3:GetObject"],
                [
                    sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/" + suffix)
                    for suffix in ["input.json", "runtime/preflight.json"]
                ],
            ),
            statement(
                ["s3:PutObject"],
                [
                    sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/" + suffix)
                    for suffix in ["impact-report.json", "impact-evidence.json"]
                ],
            ),
            statement(
                ["bedrock-agentcore:StopRuntimeSession"],
                [preview_arn, sub("${PreviewRuntime.AgentRuntimeArn}/*")],
            ),
        ],
    )
    for kind, original in [("PreviewInvoke", "Invoke"), ("PreviewFinalize", "Finalize")]:
        function = copy.deepcopy(resources[original + "Function"])
        name = "rehearsal-serverless-" + kind.lower()
        function["DependsOn"] = [kind + "Logs"]
        function["Properties"].update(FunctionName=name, Role=arn(kind + "Role"))
        function["Properties"]["Environment"]["Variables"].update(
            FUNCTION_ROLE=kind.lower(), RUNTIME_ARN=preview_arn
        )
        resources[kind + "Function"] = function
        resources[kind + "Logs"] = {
            "Type": "AWS::Logs::LogGroup",
            "Properties": {"LogGroupName": "/aws/lambda/" + name, "RetentionInDays": 7},
        }
    role(
        "PreviewWorkflowRole",
        "states.amazonaws.com",
        [
            statement(
                ["lambda:InvokeFunction"],
                [arn("PreviewInvokeFunction"), arn("PreviewFinalizeFunction")],
            )
        ],
    )
    resources["PreviewWorkflow"] = {
        "Type": "AWS::StepFunctions::StateMachine",
        "Properties": {
            "StateMachineName": "rehearsal-serverless-preflight",
            "StateMachineType": "STANDARD",
            "RoleArn": arn("PreviewWorkflowRole"),
            "Definition": {
                "StartAt": "Simulate",
                "TimeoutSeconds": 660,
                "States": {
                    "Simulate": task(
                        "PreviewInvokeFunction",
                        {"run_id.$": "$.run_id"},
                        Next="Report",
                        Catch=[
                            {
                                "ErrorEquals": ["States.ALL"],
                                "ResultPath": "$.failure",
                                "Next": "Report",
                            }
                        ],
                    ),
                    "Report": task(
                        "PreviewFinalizeFunction",
                        {"run_id.$": "$.run_id", "workflow.$": "$"},
                        End=True,
                        Retry=[
                            {
                                "ErrorEquals": ["States.TaskFailed"],
                                "IntervalSeconds": 3,
                                "MaxAttempts": 3,
                            }
                        ],
                    ),
                },
            },
            "Tags": [{"Key": "Project", "Value": "rehearsal-serverless"}],
        },
    }
    api_policies = resources["ApiRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    api_policies.extend(
        [
            statement(["states:StartExecution"], ref("PreviewWorkflow")),
            statement(["dynamodb:ConditionCheckItem"], control_arn),
            statement(
                ["s3:PutObject"],
                sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/input.json"),
            ),
            statement(
                ["s3:GetObject"],
                [
                    sub("arn:${AWS::Partition}:s3:::${ArtifactsBucket}/runs/preview-*/" + suffix)
                    for suffix in ["impact-report.json", "impact-evidence.json"]
                ],
            ),
        ]
    )
    resources["ApiFunction"]["Properties"]["Environment"]["Variables"]["PREVIEW_WORKFLOW_ARN"] = (
        ref("PreviewWorkflow")
    )
    result["Outputs"] = {
        "PreviewRuntimeArn": {"Value": preview_arn},
        "PreviewWorkflowArn": {"Value": ref("PreviewWorkflow")},
        "Url": {"Value": sub("https://${Distribution.DomainName}")},
        "DistributionId": {"Value": ref("Distribution")},
        "RuntimeArn": {"Value": runtime_arn},
        "WorkflowArn": {"Value": ref("Workflow")},
        "ApiUrl": {"Value": {"Fn::GetAtt": ["Api", "ApiEndpoint"]}},
    }
    return result


if __name__ == "__main__":
    path = ROOT / "infra/serverless/application.json"
    path.write_text(json.dumps(template(), indent=2) + "\n")
    print(path)
