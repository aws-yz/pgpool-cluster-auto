import aws_cdk as core
import aws_cdk.assertions as assertions

from pgpool_aurora_cdk.pgpool_aurora_cdk_stack import PgpoolAuroraCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in pgpool_aurora_cdk/pgpool_aurora_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = PgpoolAuroraCdkStack(app, "pgpool-aurora-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
