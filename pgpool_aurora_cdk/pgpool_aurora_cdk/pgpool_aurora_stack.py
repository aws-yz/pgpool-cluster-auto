from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_rds as rds,
    aws_autoscaling as autoscaling,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as elbv2_targets,
    aws_iam as iam,
    aws_secretsmanager as secretsmanager,
    aws_cloudwatch as cloudwatch,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Tags
)
from constructs import Construct
import json

class PgpoolAuroraStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, 
                 vpc_id: str = None,
                 subnet_ids: list = None,
                 ami_id: str = None,
                 instance_type: str = "t3.medium",
                 disk_size: int = 20,
                 min_capacity: int = 2,
                 max_capacity: int = 4,
                 desired_capacity: int = 2,
                 db_instance_class: str = "db.t3.medium",
                 db_replica_count: int = 1,
                 **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import VPC if provided, otherwise create a new one
        if vpc_id:
            vpc = ec2.Vpc.from_lookup(self, "ImportedVPC", vpc_id=vpc_id)
        else:
            vpc = ec2.Vpc(self, "PgpoolVPC",
                max_azs=3,
                subnet_configuration=[
                    ec2.SubnetConfiguration(
                        name="Public",
                        subnet_type=ec2.SubnetType.PUBLIC,
                        cidr_mask=24
                    ),
                    ec2.SubnetConfiguration(
                        name="Private",
                        subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                        cidr_mask=24
                    ),
                    ec2.SubnetConfiguration(
                        name="Isolated",
                        subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                        cidr_mask=24
                    )
                ]
            )

        # Import subnets if provided
        if subnet_ids:
            selected_subnets = []
            for subnet_id in subnet_ids:
                selected_subnets.append(ec2.Subnet.from_subnet_id(
                    self, f"ImportedSubnet-{subnet_id}", subnet_id))
            subnet_selection = ec2.SubnetSelection(subnets=selected_subnets)
        else:
            # Use private subnets for the resources
            subnet_selection = ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )

        # Create security groups
        aurora_sg = ec2.SecurityGroup(
            self, "AuroraSecurityGroup",
            vpc=vpc,
            description="Security group for Aurora PostgreSQL",
            allow_all_outbound=True
        )

        pgpool_sg = ec2.SecurityGroup(
            self, "PgpoolSecurityGroup",
            vpc=vpc,
            description="Security group for Pgpool instances",
            allow_all_outbound=True
        )

        nlb_sg = ec2.SecurityGroup(
            self, "NLBSecurityGroup",
            vpc=vpc,
            description="Security group for Network Load Balancer",
            allow_all_outbound=True
        )
        
        # Allow incoming PostgreSQL traffic from internet to NLB
        nlb_sg.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(5432),
            "Allow PostgreSQL traffic from internet"
        )

        # Allow pgpool to access Aurora
        aurora_sg.add_ingress_rule(
            pgpool_sg,
            ec2.Port.tcp(5432),
            "Allow Pgpool to access Aurora"
        )

        # Allow NLB to access Pgpool
        pgpool_sg.add_ingress_rule(
            nlb_sg,
            ec2.Port.tcp(9999),
            "Allow NLB to access Pgpool on port 9999"
        )

        # Allow NLB to access pgdoctor health check
        pgpool_sg.add_ingress_rule(
            nlb_sg,
            ec2.Port.tcp(8071),
            "Allow NLB to access pgdoctor health check on port 8071"
        )

        # Create database credentials in Secrets Manager
        db_credentials = secretsmanager.Secret(
            self, "AuroraCredentials",
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template=json.dumps({"username": "pdadmin"}),
                generate_string_key="password",
                exclude_characters="\"@/\\'",  # Exclude single quotes to avoid escaping issues
                exclude_punctuation=False,
                include_space=False
            )
        )

        # Create Aurora PostgreSQL cluster
        aurora_cluster = rds.DatabaseCluster(
            self, "AuroraPostgreSQLCluster",
            engine=rds.DatabaseClusterEngine.aurora_postgres(
                version=rds.AuroraPostgresEngineVersion.VER_15_4
            ),
            instance_props=rds.InstanceProps(
                vpc=vpc,
                vpc_subnets=subnet_selection,
                # 直接使用db_instance_class，不需要再包装到InstanceType中，避免双重"db."前缀
                instance_type=ec2.InstanceType.of(
                    ec2.InstanceClass.BURSTABLE3, 
                    ec2.InstanceSize.MEDIUM
                ) if db_instance_class == "db.t3.medium" else ec2.InstanceType.of(
                    ec2.InstanceClass.MEMORY5, 
                    ec2.InstanceSize.LARGE
                ),
                security_groups=[aurora_sg],
                allow_major_version_upgrade=False,
                auto_minor_version_upgrade=True,
            ),
            instances=1 + db_replica_count,  # 1 writer + N readers
            credentials=rds.Credentials.from_secret(db_credentials),
            parameter_group=rds.ParameterGroup.from_parameter_group_name(
                self, "ParameterGroup",
                parameter_group_name="default.aurora-postgresql15"
            ),
            backup=rds.BackupProps(
                retention=Duration.days(7),
                preferred_window="03:00-04:00"
            ),
            storage_encrypted=True,
            removal_policy=RemovalPolicy.SNAPSHOT,
            cloudwatch_logs_exports=["postgresql"]
        )

        # Create IAM role for EC2 instances
        pgpool_role = iam.Role(
            self, "PgpoolRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
            ]
        )

        # Grant read access to the database credentials
        db_credentials.grant_read(pgpool_role)

        # Create launch template for Pgpool instances
        user_data = ec2.UserData.for_linux()
        
        # Add user data script to configure Pgpool with Aurora endpoints
        user_data.add_commands(f"""
#!/bin/bash
# Get database credentials from Secrets Manager
DB_CREDS=$(aws secretsmanager get-secret-value --secret-id {db_credentials.secret_arn} --query SecretString --output text)
DB_USERNAME=$(echo $DB_CREDS | jq -r '.username')
DB_PASSWORD=$(echo $DB_CREDS | jq -r '.password')

# Properly escape the password for use in pgpool.conf and pgdoctor.cfg
# Replace single quotes with doubled single quotes for PostgreSQL-style configs
ESCAPED_PASSWORD=$(echo "$DB_PASSWORD" | sed "s/'/''/g")

# Update Pgpool configuration with Aurora endpoints
sed -i "s/backend_hostname0 = '.*'/backend_hostname0 = '{aurora_cluster.cluster_endpoint.hostname}'/" /usr/local/etc/pgpool.conf
sed -i "s/backend_hostname1 = '.*'/backend_hostname1 = '{aurora_cluster.cluster_read_endpoint.hostname}'/" /usr/local/etc/pgpool.conf
sed -i "s/sr_check_user = '.*'/sr_check_user = '$DB_USERNAME'/" /usr/local/etc/pgpool.conf

# Use perl for more reliable handling of special characters in passwords
perl -i -pe "s/^sr_check_password = .*/sr_check_password = '$ESCAPED_PASSWORD'/" /usr/local/etc/pgpool.conf
sed -i "s/health_check_user = '.*'/health_check_user = '$DB_USERNAME'/" /usr/local/etc/pgpool.conf
perl -i -pe "s/^health_check_password = .*/health_check_password = '$ESCAPED_PASSWORD'/" /usr/local/etc/pgpool.conf

# Update pgdoctor configuration - also using single quotes with proper escaping
sed -i "s/^pg_user = '.*'/pg_user = '$DB_USERNAME'/" /etc/pgdoctor.cfg
perl -i -pe "s/^pg_password = .*/pg_password = '$ESCAPED_PASSWORD'/" /etc/pgdoctor.cfg

# Update pool_passwd file with database credentials
echo "$DB_USERNAME:$DB_PASSWORD" > /usr/local/etc/pool_passwd
chmod 600 /usr/local/etc/pool_passwd
chown pgpool:pgpool /usr/local/etc/pool_passwd

# Restart services
systemctl restart pgpool
systemctl restart pgdoctor
        """)

        # Create launch template
        launch_template = ec2.LaunchTemplate(
            self, "PgpoolLaunchTemplate",
            launch_template_name="PgpoolLaunchTemplate",
            instance_type=ec2.InstanceType(instance_type),
            machine_image=ec2.MachineImage.generic_linux({
                self.region: ami_id
            }),
            user_data=user_data,
            role=pgpool_role,
            security_group=pgpool_sg,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=disk_size,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        delete_on_termination=True
                    )
                )
            ]
        )

        # Create Auto Scaling Group
        asg = autoscaling.AutoScalingGroup(
            self, "PgpoolASG",
            vpc=vpc,
            vpc_subnets=subnet_selection,
            launch_template=launch_template,
            min_capacity=min_capacity,
            max_capacity=max_capacity,
            desired_capacity=desired_capacity,
            health_check=autoscaling.HealthCheck.elb(
                grace=Duration.minutes(5)
            ),
            update_policy=autoscaling.UpdatePolicy.rolling_update(
                min_instances_in_service=1,
                max_batch_size=1,
                pause_time=Duration.minutes(5)
            )
        )

        # Add CloudWatch alarms for the ASG
        asg.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            cooldown=Duration.minutes(5)
        )

        # Create Network Load Balancer
        nlb = elbv2.NetworkLoadBalancer(
            self, "PgpoolNLB",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC
            ),
            internet_facing=True,
            cross_zone_enabled=True,
            security_groups=[nlb_sg]  # Attach security group directly to NLB
        )

        # Add listener for Pgpool
        pgpool_listener = nlb.add_listener(
            "PgpoolListener",
            port=5432,
            protocol=elbv2.Protocol.TCP
        )

        # Add target group for Pgpool
        pgpool_target_group = pgpool_listener.add_targets(
            "PgpoolTargets",
            port=9999,
            protocol=elbv2.Protocol.TCP,
            targets=[asg],
            health_check=elbv2.HealthCheck(
                port="8071",
                protocol=elbv2.Protocol.HTTP,
                path="/",
                healthy_threshold_count=2,
                unhealthy_threshold_count=2,
                timeout=Duration.seconds(5),
                interval=Duration.seconds(30)
            ),
            deregistration_delay=Duration.seconds(60)
        )

        # Add tags
        Tags.of(self).add("Project", "PgpoolAurora")
        Tags.of(asg).add("Name", "Pgpool-Instance")
        Tags.of(aurora_cluster).add("Name", "Aurora-PostgreSQL-Cluster")

        # Outputs
        CfnOutput(
            self, "NLBEndpoint",
            value=nlb.load_balancer_dns_name,
            description="Network Load Balancer endpoint for Pgpool"
        )

        CfnOutput(
            self, "AuroraClusterEndpoint",
            value=aurora_cluster.cluster_endpoint.hostname,
            description="Aurora PostgreSQL cluster endpoint"
        )

        CfnOutput(
            self, "AuroraReaderEndpoint",
            value=aurora_cluster.cluster_read_endpoint.hostname,
            description="Aurora PostgreSQL reader endpoint"
        )

        CfnOutput(
            self, "DatabaseSecretArn",
            value=db_credentials.secret_arn,
            description="ARN of the database credentials secret"
        )
