"""Cloud tools (AWS) for Hermes agent."""
import asyncio
import json
import os
import pathlib
import time

TOOLS = [
    {
        "name": "list_s3_buckets",
        "description": "List all S3 buckets in the AWS account",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "AWS region filter (optional)"},
            },
            "required": [],
        },
    },
    {
        "name": "upload_s3",
        "description": "Upload a file to an S3 bucket",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "S3 bucket name"},
                "key": {"type": "string", "description": "Object key (path in bucket)"},
                "file_path": {"type": "string", "description": "Local file path to upload"},
                "content_type": {"type": "string", "description": "MIME type (optional)"},
            },
            "required": ["bucket", "key", "file_path"],
        },
    },
    {
        "name": "download_s3",
        "description": "Download a file from an S3 bucket",
        "parameters": {
            "type": "object",
            "properties": {
                "bucket": {"type": "string", "description": "S3 bucket name"},
                "key": {"type": "string", "description": "Object key (path in bucket)"},
                "output_path": {"type": "string", "description": "Local output path"},
            },
            "required": ["bucket", "key", "output_path"],
        },
    },
    {
        "name": "list_ec2",
        "description": "List EC2 instances with their states",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
                "filters": {"type": "string", "description": "Filter by instance state (running, stopped, terminated)"},
            },
            "required": [],
        },
    },
    {
        "name": "start_ec2",
        "description": "Start an EC2 instance",
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string", "description": "EC2 instance ID"},
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
            },
            "required": ["instance_id"],
        },
    },
    {
        "name": "stop_ec2",
        "description": "Stop an EC2 instance",
        "parameters": {
            "type": "object",
            "properties": {
                "instance_id": {"type": "string", "description": "EC2 instance ID"},
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
            },
            "required": ["instance_id"],
        },
    },
    {
        "name": "list_sqs",
        "description": "List SQS queues",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
                "prefix": {"type": "string", "description": "Queue name prefix filter"},
            },
            "required": [],
        },
    },
    {
        "name": "send_sqs",
        "description": "Send a message to an SQS queue",
        "parameters": {
            "type": "object",
            "properties": {
                "queue_url": {"type": "string", "description": "SQS queue URL"},
                "message": {"type": "string", "description": "Message body"},
                "delay_seconds": {"type": "integer", "description": "Delivery delay in seconds", "default": 0},
            },
            "required": ["queue_url", "message"],
        },
    },
    {
        "name": "invoke_lambda",
        "description": "Invoke an AWS Lambda function",
        "parameters": {
            "type": "object",
            "properties": {
                "function_name": {"type": "string", "description": "Lambda function name or ARN"},
                "payload": {"type": "string", "description": "JSON payload (optional)"},
                "invocation_type": {"type": "string", "enum": ["RequestResponse", "Event", "DryRun"], "default": "RequestResponse"},
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
            },
            "required": ["function_name"],
        },
    },
    {
        "name": "list_rds",
        "description": "List RDS database instances",
        "parameters": {
            "type": "object",
            "properties": {
                "region": {"type": "string", "description": "AWS region", "default": "us-east-1"},
            },
            "required": [],
        },
    },
]

functions = {}


async def _run_aws_cli(cmd: list, timeout: int = 30) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        stdout_str = stdout.decode("utf-8", errors="replace").strip()
        stderr_str = stderr.decode("utf-8", errors="replace").strip()
        return {
            "success": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout_str,
            "stderr": stderr_str,
        }
    except asyncio.TimeoutError:
        return {"error": f"Command timed out after {timeout}s", "success": False}
    except FileNotFoundError:
        return {"error": "AWS CLI not found. Install from https://aws.amazon.com/cli/", "success": False}
    except Exception as e:
        return {"error": str(e), "success": False}


def _parse_json_output(stdout: str):
    try:
        return json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return None


async def list_s3_buckets(args):
    region = args.get("region", "")
    cmd = ["aws", "s3", "ls", "--query", "Buckets[].{Name:Name,CreationDate:CreationDate}", "--output", "json"]
    if region:
        cmd.extend(["--region", region])

    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "AWS CLI failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    if data is None:
        return {"error": f"Failed to parse AWS output: {result['stdout'][:200]}", "success": False}

    return {"success": True, "buckets": data, "count": len(data)}


async def upload_s3(args):
    bucket = args["bucket"]
    key = args["key"]
    file_path = args["file_path"]
    content_type = args.get("content_type", "")

    if not os.path.exists(file_path):
        return {"error": f"File not found: {file_path}", "success": False}

    cmd = ["aws", "s3", "cp", file_path, f"s3://{bucket}/{key}"]
    if content_type:
        cmd.extend(["--content-type", content_type])

    result = await _run_aws_cli(cmd, timeout=120)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Upload failed"), "success": False}

    file_size = os.path.getsize(file_path)
    return {"success": True, "bucket": bucket, "key": key, "size_bytes": file_size, "source": file_path}


async def download_s3(args):
    bucket = args["bucket"]
    key = args["key"]
    output_path = args["output_path"]

    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    cmd = ["aws", "s3", "cp", f"s3://{bucket}/{key}", output_path]

    result = await _run_aws_cli(cmd, timeout=120)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Download failed"), "success": False}

    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return {"success": True, "bucket": bucket, "key": key, "output": output_path, "size_bytes": size}


async def list_ec2(args):
    region = args.get("region", "us-east-1")
    state_filter = args.get("filters", "")

    cmd = [
        "aws", "ec2", "describe-instances",
        "--region", region,
        "--query", "Reservations[].Instances[].{InstanceId:InstanceId,State:State.Name,Type:InstanceType,Name:Tags[?Key=='Name']|[0].Value,PrivateIp:PrivateIpAddress,PublicIp:PublicIpAddress,LaunchTime:LaunchTime}",
        "--output", "json",
    ]
    if state_filter:
        cmd.extend(["--filters", f"Name=instance-state-name,Values={state_filter}"])

    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "AWS CLI failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    if data is None:
        return {"error": f"Failed to parse output: {result['stdout'][:200]}", "success": False}

    instances = []
    for reservation in data:
        instances.extend(reservation)

    return {"success": True, "instances": instances, "count": len(instances), "region": region}


async def start_ec2(args):
    instance_id = args["instance_id"]
    region = args.get("region", "us-east-1")

    cmd = ["aws", "ec2", "start-instances", "--instance-ids", instance_id, "--region", region, "--output", "json"]
    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Start failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    previous_state = data["StartingInstances"][0]["PreviousState"]["Name"] if data else "unknown"
    current_state = data["StartingInstances"][0]["CurrentState"]["Name"] if data else "unknown"

    return {"success": True, "instance_id": instance_id, "previous_state": previous_state, "current_state": current_state}


async def stop_ec2(args):
    instance_id = args["instance_id"]
    region = args.get("region", "us-east-1")

    cmd = ["aws", "ec2", "stop-instances", "--instance-ids", instance_id, "--region", region, "--output", "json"]
    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Stop failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    previous_state = data["StoppingInstances"][0]["PreviousState"]["Name"] if data else "unknown"
    current_state = data["StoppingInstances"][0]["CurrentState"]["Name"] if data else "unknown"

    return {"success": True, "instance_id": instance_id, "previous_state": previous_state, "current_state": current_state}


async def list_sqs(args):
    region = args.get("region", "us-east-1")
    prefix = args.get("prefix", "")

    cmd = ["aws", "sqs", "list-queues", "--region", region, "--output", "json"]
    if prefix:
        cmd.extend(["--queue-name-prefix", prefix])

    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "AWS CLI failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    queues = data.get("QueueUrls", []) if data else []
    return {"success": True, "queues": queues, "count": len(queues), "region": region}


async def send_sqs(args):
    queue_url = args["queue_url"]
    message = args["message"]
    delay = args.get("delay_seconds", 0)

    cmd = [
        "aws", "sqs", "send-message",
        "--queue-url", queue_url,
        "--message-body", message,
        "--output", "json",
    ]
    if delay > 0:
        cmd.extend(["--delay-seconds", str(delay)])

    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Send failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    return {"success": True, "message_id": data.get("MessageId", ""), "md5": data.get("MD5OfMessageBody", ""), "queue": queue_url}


async def invoke_lambda(args):
    function_name = args["function_name"]
    payload = args.get("payload", "{}")
    invocation_type = args.get("invocation_type", "RequestResponse")
    region = args.get("region", "us-east-1")

    cmd = [
        "aws", "lambda", "invoke",
        "--function-name", function_name,
        "--invocation-type", invocation_type,
        "--region", region,
        "--cli-binary-format", "raw-in-base64-out",
        "--payload", payload,
        "--output", "json",
    ]

    result = await _run_aws_cli(cmd, timeout=60)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "Invoke failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    status_code = data.get("StatusCode", 0) if data else 0
    return {
        "success": True,
        "function_name": function_name,
        "status_code": status_code,
        "invocation_type": invocation_type,
    }


async def list_rds(args):
    region = args.get("region", "us-east-1")

    cmd = [
        "aws", "rds", "describe-db-instances",
        "--region", region,
        "--query", "DBInstances[].{DBInstanceIdentifier:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine,EngineVersion:EngineVersion,AllocatedStorage:AllocatedStorage,InstanceClass:DBInstanceClass,Endpoint:Endpoint.Address,MultiAZ:MultiAZ}",
        "--output", "json",
    ]

    result = await _run_aws_cli(cmd)
    if not result["success"]:
        return {"error": result.get("stderr") or result.get("error", "AWS CLI failed"), "success": False}

    data = _parse_json_output(result["stdout"])
    instances = data if data else []
    return {"success": True, "instances": instances, "count": len(instances), "region": region}


functions = {
    "list_s3_buckets": list_s3_buckets,
    "upload_s3": upload_s3,
    "download_s3": download_s3,
    "list_ec2": list_ec2,
    "start_ec2": start_ec2,
    "stop_ec2": stop_ec2,
    "list_sqs": list_sqs,
    "send_sqs": send_sqs,
    "invoke_lambda": invoke_lambda,
    "list_rds": list_rds,
}
