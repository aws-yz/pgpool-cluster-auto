#!/usr/bin/env python3
import os
import sys
import aws_cdk as cdk
from pgpool_aurora_cdk.pgpool_aurora_stack import PgpoolAuroraStack

app = cdk.App()

# Skip ami_id validation for bootstrap command
is_bootstrap = len(sys.argv) > 1 and sys.argv[1] == "bootstrap"

# Get parameters from context or use defaults
vpc_id = app.node.try_get_context("vpc_id")
subnet_ids = app.node.try_get_context("subnet_ids")
ami_id = app.node.try_get_context("ami_id")
instance_type = app.node.try_get_context("instance_type") or "t3.medium"
disk_size = int(app.node.try_get_context("disk_size") or "20")
min_capacity = int(app.node.try_get_context("min_capacity") or "2")
max_capacity = int(app.node.try_get_context("max_capacity") or "4")
desired_capacity = int(app.node.try_get_context("desired_capacity") or "2")
db_instance_class = app.node.try_get_context("db_instance_class") or "db.t3.medium"
db_replica_count = int(app.node.try_get_context("db_replica_count") or "1")

# Validate required parameters - skip for bootstrap
if not ami_id and not is_bootstrap:
    raise ValueError("ami_id is required. Please provide it using -c ami_id=<AMI_ID>")

# Use a dummy AMI ID for bootstrap if none provided
if is_bootstrap and not ami_id:
    ami_id = "ami-dummy-for-bootstrap"

# Create the stack
PgpoolAuroraStack(app, "PgpoolAuroraStack",
    vpc_id=vpc_id,
    subnet_ids=subnet_ids.split(",") if subnet_ids else None,
    ami_id=ami_id,
    instance_type=instance_type,
    disk_size=disk_size,
    min_capacity=min_capacity,
    max_capacity=max_capacity,
    desired_capacity=desired_capacity,
    db_instance_class=db_instance_class,
    db_replica_count=db_replica_count,
    env=cdk.Environment(
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region=os.environ.get("CDK_DEFAULT_REGION")
    )
)

app.synth()
