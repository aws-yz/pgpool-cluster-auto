# Pgpool-II Aurora PostgreSQL High Availability Architecture

This project implements a high availability Pgpool-II with Aurora PostgreSQL architecture, deployed using AWS CDK for infrastructure as code.

## Project Documentation

This project contains three README files:
- **Root directory README.md**: Provides project overview, architecture description, and complete process guide (Chinese version)
- **This file (README_EN.md)**: English version of the project documentation
- **[pgpool_aurora_cdk/README.md](pgpool_aurora_cdk/README.md)**: Provides detailed steps and technical details for CDK deployment (Chinese version)

## Getting the Project Code

You can get the project code through the following methods:

### Using Git Clone

```bash
git clone https://github.com/yourusername/pgpool-cluster-auto.git
cd pgpool-cluster-auto
```

### Direct Download

1. Visit the project GitHub page: https://github.com/yourusername/pgpool-cluster-auto
2. Click the "Code" button, then select "Download ZIP"
3. Extract the downloaded ZIP file
4. Enter the extracted directory
   ```bash
   cd pgpool-cluster-auto-main
   ```

## Project Components

1. **AMI Creation Tool**: `create_pgpool_AMI.py` - Used to create pre-configured Pgpool-II and pgdoctor AMI
2. **CDK Deployment Code**: `pgpool_aurora_cdk/` - CDK code for deploying the complete architecture

## Architecture Overview

![Pgpool-Aurora Architecture](pgpool-aurora-architecture.png)

The architecture includes:
- Aurora PostgreSQL cluster (1 writer node, configurable number of reader nodes)
- Auto Scaling Group for Pgpool-II using pre-created AMI
- Network Load Balancer (NLB) that checks pgpool health status via pgdoctor (port 8071)
- Appropriate security group configurations and IAM roles

## Usage Instructions

### 1. Create Pgpool-II AMI

First, use the `create_pgpool_AMI.py` script to create an AMI containing Pgpool-II and pgdoctor:

```bash
# Install required dependencies
pip install boto3

# Execute AMI creation script
python create_pgpool_AMI.py <region_name> [cluster_endpoint] [reader_endpoint] [db_user] [db_password] [instance_type]
```

Parameter description:
- `region_name`: AWS region
- `cluster_endpoint`: Aurora cluster writer endpoint (optional, default is 'your-aurora-cluster-endpoint')
- `reader_endpoint`: Aurora cluster reader endpoint (optional, default is 'your-aurora-reader-endpoint')
- `db_user`: Database username (optional, default is 'pdadmin')
- `db_password`: Database password (optional, default is '1qaz2wsx')
- `instance_type`: Instance type for building AMI (optional, default is 't3.micro')

### 2. Deploy Complete Architecture

Use CDK to deploy the complete architecture:

```bash
cd pgpool_aurora_cdk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Deployment Parameter Description

Various options can be configured through context parameters during CDK deployment:

| Parameter | Description | Default Value | Required |
|------|------|--------|----------|
| ami_id | Pgpool-II AMI ID | - | Yes |
| vpc_id | Existing VPC ID | - | No, a new VPC will be created if not provided |
| subnet_ids | List of subnet IDs, comma-separated | - | No, default VPC subnets will be used if not provided |
| instance_type | Pgpool-II instance type | t3.medium | No |
| disk_size | Pgpool-II instance disk size (GB) | 20 | No |
| min_capacity | Auto Scaling Group minimum capacity | 2 | No |
| max_capacity | Auto Scaling Group maximum capacity | 4 | No |
| desired_capacity | Auto Scaling Group desired capacity | 2 | No |
| db_instance_class | Aurora instance type | db.t3.medium | No |
| db_replica_count | Number of Aurora read replicas | 1 | No |

#### Deployment Command Examples

Basic deployment (providing only required parameters):
```bash
cdk deploy -c ami_id=ami-0123456789abcdef0
```

Full parameter deployment example:
```bash
cdk deploy -c ami_id=ami-0123456789abcdef0 \
           -c vpc_id=vpc-0123456789abcdef0 \
           -c subnet_ids=subnet-0123456789abcdef0,subnet-0123456789abcdef1 \
           -c instance_type=t3.large \
           -c disk_size=50 \
           -c min_capacity=2 \
           -c max_capacity=6 \
           -c desired_capacity=3 \
           -c db_instance_class=db.r5.large \
           -c db_replica_count=2
```

#### Deployment Process

1. **Check CDK Environment**:
   First, check if the CDK environment has been initialized in the target region:
   ```bash
   aws cloudformation describe-stacks --stack-name CDKToolkit
   ```
   If the command returns an error "Stack with id CDKToolkit does not exist", initialization is required.

2. **Initialize Deployment** (if needed):
   ```bash
   # Execute bootstrap command outside the project directory
   cd ~
   npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
   ```
   
   **Important Notes**:
   - The bootstrap command should be executed outside the project directory to avoid project configuration interference
   - If executed within the project directory, the ami_id parameter needs to be provided: `cdk bootstrap aws://ACCOUNT-NUMBER/REGION -c ami_id=dummy-value`
   - If bootstrap fails with a `ROLLBACK_COMPLETE` status, you need to delete the failed stack before retrying:
     ```bash
     aws cloudformation delete-stack --stack-name CDKToolkit
     aws cloudformation wait stack-delete-complete --stack-name CDKToolkit
     npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
     ```

3. **View Changes**:
   ```bash
   cdk diff -c ami_id=ami-0123456789abcdef0
   ```
   This will display the resources that will be created, but won't actually deploy them

4. **Execute Deployment**:
   ```bash
   cdk deploy -c ami_id=ami-0123456789abcdef0 [other parameters]
   ```

5. **View Outputs**:
   After deployment is complete, CDK will output important resource information, such as NLB endpoint and Aurora cluster endpoint

For detailed deployment instructions, please refer to [pgpool_aurora_cdk/README.md](pgpool_aurora_cdk/README.md).

## Architecture Features

1. **High Availability**:
   - Pgpool-II instances deployed across multiple availability zones
   - Aurora cluster deployed across multiple availability zones
   - Automatic failover

2. **Load Balancing**:
   - Pgpool-II provides connection pooling and load balancing functionality
   - Read/write splitting, optimizing query performance

3. **Auto Scaling**:
   - Automatically adjusts the number of Pgpool-II instances based on load

4. **Health Checks**:
   - Uses pgdoctor to monitor Pgpool-II instance health status
   - NLB automatically removes unhealthy instances based on health checks

5. **Security**:
   - Uses Secrets Manager to store database credentials
   - Fine-grained security group rules
   - Encrypted data storage

## Best Practices

1. **Network Configuration**:
   - Deploy Pgpool-II instances in private subnets
   - Deploy NLB in public subnets (if public access is required)
   - Deploy Aurora cluster in isolated subnets

2. **Security**:
   - Rotate database credentials regularly
   - Limit security group rule scope
   - Enable audit logging

3. **Monitoring**:
   - Set up CloudWatch alarms to monitor key metrics
   - Configure SNS notification mechanisms

4. **Backup**:
   - Configure Aurora automatic backup policy
   - Consider using cross-region backups

## Troubleshooting

For common issues and solutions, please refer to the troubleshooting section in [pgpool_aurora_cdk/README.md](pgpool_aurora_cdk/README.md).