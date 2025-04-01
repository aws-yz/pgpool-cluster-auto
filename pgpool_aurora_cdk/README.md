# Pgpool-II Aurora PostgreSQL CDK部署指南

本文档提供了使用AWS CDK部署Pgpool-II与Aurora PostgreSQL高可用架构的详细步骤。这是项目的CDK部署部分，关于整体项目架构和AMI创建，请参考[根目录README](../README.md)。

## 架构概述

![Pgpool-Aurora架构](../pgpool-aurora-architecture.png)

该架构提供以下功能：
- 高可用性：通过在多个可用区部署Pgpool-II实例和Aurora节点
- 负载均衡：Pgpool-II提供连接池和负载均衡功能
- 自动扩展：根据负载自动调整Pgpool-II实例数量
- 健康检查：使用pgdoctor监控Pgpool-II实例健康状态

## 网络配置详情

当不指定VPC和子网参数时，CDK会自动创建和配置网络资源：

### 默认VPC和子网配置

1. **VPC创建**：
   - 当不提供`vpc_id`参数时，CDK会创建一个新的VPC
   - 默认CIDR通常为10.0.0.0/16

2. **子网配置**：
   - 在每个可用区创建2种类型的子网：公有子网和私有子网
   - 通常使用账户中可用的所有可用区（一般为3个可用区）
   - 默认情况下会创建6个子网（3个公有 + 3个私有）

3. **NAT网关**：
   - 在每个公有子网中创建一个NAT网关
   - 私有子网通过NAT网关访问互联网

### 组件部署位置与子网选择

#### 默认部署情况（不指定VPC和子网）

1. **NLB部署**：
   - 默认部署在**公有子网**中
   - 配置为面向互联网（`internet_facing=True`）
   - 自动在每个可用区选择一个公有子网，确保跨可用区高可用性
   - 如需内部NLB（不可从互联网访问），需修改代码指定`internet_facing=False`

2. **Pgpool-II实例**：
   - 默认部署在**私有子网**中（`PRIVATE_WITH_EGRESS`类型）
   - 通过Auto Scaling Group跨多个可用区部署
   - 实例可以通过NAT网关访问互联网进行更新
   - 每个可用区至少部署一个实例，确保高可用性

3. **Aurora PostgreSQL**：
   - 默认部署在**私有子网**中（`PRIVATE_WITH_EGRESS`类型）
   - 写入节点和读取节点分布在不同可用区的私有子网中
   - 不需要直接访问互联网
   - 自动跨可用区部署以确保高可用性

#### 使用`subnet_ids`参数的子网选择

当使用`-c subnet_ids=subnet-1,subnet-2,subnet-3`参数时：

1. **指定子网的用途**：
   - 指定的子网**仅用于Pgpool-II实例和Aurora数据库集群**
   - 这些子网应该是私有子网（`PRIVATE_WITH_EGRESS`类型）
   - 至少需要提供两个不同可用区的子网以确保高可用性

2. **NLB子网选择**：
   - **重要**：即使指定了`subnet_ids`，NLB仍然会部署在**公有子网**中
   - NLB的子网选择不受`subnet_ids`参数影响
   - 如果指定的VPC没有公有子网，部署将失败

3. **子网数量建议**：
   - 建议至少提供3个不同可用区的子网
   - 这样可以确保Aurora和Pgpool-II实例能够跨多个可用区部署

### 自定义网络配置

如果需要更精细地控制网络配置，建议：

1. **使用现有VPC和子网**：
   ```bash
   cdk deploy -c ami_id=ami-xxx -c vpc_id=vpc-xxx -c subnet_ids=subnet-1,subnet-2,subnet-3
   ```

2. **内部NLB部署**：
   如果需要将NLB部署为内部负载均衡器（不可从互联网访问），需要修改代码：
   ```python
   # 修改NLB配置为内部NLB
   nlb = elbv2.NetworkLoadBalancer(
       self, "PgpoolNLB",
       vpc=vpc,
       vpc_subnets=subnet_selection,  # 使用与Pgpool相同的子网选择
       internet_facing=False,  # 设置为内部NLB
       cross_zone_enabled=True
   )
   ```

3. **遵循最佳实践**：
   - Pgpool-II实例应部署在私有子网中
   - NLB根据访问需求部署在公有子网（面向互联网）或私有子网（内部访问）
   - Aurora集群应部署在私有或隔离子网中

## 前提条件

1. 已创建包含pgpool和pgdoctor的AMI（使用`create_pgpool_AMI.py`脚本）
2. 安装了AWS CDK CLI
3. 配置了AWS凭证

## 获取和准备项目

### 1. 获取项目代码

如果您还没有获取项目代码，可以通过以下方式获取：

```bash
# 使用Git克隆
git clone https://github.com/wangyunzhang/pgpool-cluster-auto.git
cd pgpool-cluster-auto/pgpool_aurora_cdk

# 或者，如果您已下载并解压ZIP文件
cd pgpool-cluster-auto-main/pgpool_aurora_cdk
```

### 2. 安装依赖

```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 安装AWS CDK CLI（如果尚未安装）
npm install -g aws-cdk
```

### 3. 初始化CDK环境（首次使用）

首先，检查是否已在目标区域初始化CDK环境：

```bash
aws cloudformation describe-stacks --stack-name CDKToolkit
```

如果命令返回错误"Stack with id CDKToolkit does not exist"，则表示需要执行初始化。

如果是首次在AWS账户/区域使用CDK，需要执行bootstrap命令。**注意：bootstrap命令应在项目目录外执行，以避免项目配置干扰**：

```bash
# 切换到用户主目录或任何非项目目录
cd ~

# 使用npx执行bootstrap命令
npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

替换`ACCOUNT-NUMBER`为您的AWS账户ID，`REGION`为您要部署的区域。

如果您在项目目录中执行bootstrap命令，可能会遇到错误，因为项目的app.py要求提供ami_id参数。在这种情况下，您可以：

1. 在项目目录外执行bootstrap命令（推荐方法），或
2. 在执行bootstrap时提供必要的参数：
   ```bash
   cdk bootstrap aws://ACCOUNT-NUMBER/REGION -c ami_id=dummy-value
   ```

bootstrap过程会在您的账户中创建必要的资源，包括S3存储桶和IAM角色，以支持CDK部署。这是一次性操作，每个区域只需执行一次。

如果bootstrap过程失败并显示`ROLLBACK_COMPLETE`状态，您需要先删除失败的堆栈，然后重新尝试：

```bash
aws cloudformation delete-stack --stack-name CDKToolkit
aws cloudformation wait stack-delete-complete --stack-name CDKToolkit
npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

### 4. 配置参数

可以通过CDK上下文参数配置部署选项：

```bash
cdk deploy -c ami_id=ami-xxxxxxxxxx \
           -c vpc_id=vpc-xxxxxxxxxx \
           -c subnet_ids=subnet-xxxx,subnet-yyyy,subnet-zzzz \
           -c instance_type=t3.medium \
           -c disk_size=20 \
           -c min_capacity=2 \
           -c max_capacity=4 \
           -c desired_capacity=2 \
           -c db_instance_class=db.t3.medium \
           -c db_replica_count=1
```

### 5. 部署前验证

在执行部署前，可以使用以下命令查看将要创建的资源：

```bash
cdk diff -c ami_id=ami-xxxxxxxxxx [其他参数]
```

这将显示CloudFormation将要执行的变更，但不会实际部署资源。

### 参数说明

| 参数 | 描述 | 默认值 | 是否必需 |
|------|------|--------|----------|
| ami_id | Pgpool-II AMI ID | - | 是 |
| vpc_id | 现有VPC ID | - | 否，不提供将创建新VPC |
| subnet_ids | 子网ID列表，逗号分隔 | - | 否，不提供将使用VPC默认子网 |
| instance_type | Pgpool-II实例类型 | t3.medium | 否 |
| disk_size | Pgpool-II实例磁盘大小(GB) | 20 | 否 |
| min_capacity | Auto Scaling Group最小容量 | 2 | 否 |
| max_capacity | Auto Scaling Group最大容量 | 4 | 否 |
| desired_capacity | Auto Scaling Group期望容量 | 2 | 否 |
| db_instance_class | Aurora实例类型 | db.t3.medium | 否 |
| db_replica_count | Aurora只读副本数量 | 1 | 否 |

### 6. 执行部署

执行以下命令开始部署：

```bash
cdk deploy -c ami_id=ami-xxxxxxxxxx [其他参数]
```

部署过程中，CDK会显示将要创建的IAM权限，需要确认后继续。

### 7. 部署输出

部署成功后，CDK会输出重要的资源信息：

- **NLBEndpoint**: 网络负载均衡器端点，用于连接Pgpool
- **AuroraClusterEndpoint**: Aurora集群写入端点
- **AuroraReaderEndpoint**: Aurora集群读取端点
- **DatabaseSecretArn**: 数据库凭证密钥ARN

这些输出值可以在AWS控制台的CloudFormation服务中查看，或通过以下命令获取：

```bash
aws cloudformation describe-stacks --stack-name PgpoolAuroraStack --query "Stacks[0].Outputs"
```

## 部署后验证

部署完成后，您可以通过以下方式验证架构：

1. **连接到NLB端点**：
   ```bash
   psql -h <NLB_ENDPOINT> -p 5432 -U pdadmin -d postgres
   ```
   NLB端点可以从CloudFormation输出中获取。

2. **验证连接池和负载均衡功能**：
   在psql中执行以下查询，验证连接是否正常：
   ```sql
   SELECT current_database(), current_user;
   ```

3. **验证读写分离**：
   执行以下查询，观察是否在不同的节点上执行：
   ```sql
   -- 写入查询会路由到主节点
   CREATE TABLE test_table (id serial, name text);
   INSERT INTO test_table (name) VALUES ('test');
   
   -- 读取查询可能会路由到读取节点
   SELECT * FROM test_table;
   ```

4. **验证Auto Scaling**：
   可以通过AWS控制台监控Auto Scaling Group的状态，或者通过以下命令：
   ```bash
   aws autoscaling describe-auto-scaling-groups --auto-scaling-group-name <ASG_NAME>
   ```

5. **验证健康检查**：
   可以通过以下命令检查NLB目标组的健康状态：
   ```bash
   aws elbv2 describe-target-health --target-group-arn <TARGET_GROUP_ARN>
   ```

## 最佳实践

### 高可用性

1. **多可用区部署**：
   - 确保Pgpool-II实例部署在至少两个可用区
   - Aurora集群应跨多个可用区部署
   - 设置Auto Scaling Group的最小容量为2，确保始终有多个Pgpool实例运行

2. **故障转移配置**：
   - 配置适当的健康检查参数，确保快速检测故障
   - 设置合理的冷却时间，避免频繁的扩展和收缩

### 安全性

1. **数据加密**：
   - 使用密钥管理服务(KMS)加密Aurora数据
   - 启用传输中加密(SSL/TLS)

2. **访问控制**：
   - 实现精细的安全组规则，限制最小必要的访问
   - 使用Secrets Manager存储和轮换数据库凭证
   - 定期轮换数据库凭证，建议设置自动轮换

3. **网络隔离**：
   - 将Pgpool-II实例部署在私有子网中
   - 将Aurora集群部署在隔离子网中
   - 只允许必要的网络流量

4. **审计和日志**：
   - 启用Aurora审计日志
   - 配置CloudTrail跟踪API调用
   - 启用VPC流日志监控网络流量

### 监控

1. **CloudWatch告警**：
   - 设置CPU、内存和连接数的告警
   - 监控Aurora的复制延迟
   - 配置磁盘空间使用率告警

2. **通知机制**：
   - 配置SNS通知接收关键告警
   - 设置自动扩展事件通知

3. **仪表板**：
   - 创建综合性CloudWatch仪表板监控整个架构
   - 包括Pgpool实例、NLB和Aurora集群的关键指标

### 备份和恢复

1. **自动备份**：
   - 配置Aurora自动备份策略，默认保留期为7天
   - 考虑创建手动快照用于长期保留

2. **灾难恢复**：
   - 考虑使用跨区域备份
   - 定期测试恢复过程

3. **时间点恢复**：
   - 启用Aurora的时间点恢复功能
   - 记录关键变更的时间点，便于恢复

## 故障排除

### 连接问题

1. **无法连接到NLB端点**：
   - 检查安全组规则是否允许从您的IP地址到NLB的流量
   - 验证NLB健康检查配置是否正确
   - 检查目标组中是否有健康的目标

   ```bash
   # 检查目标组健康状态
   aws elbv2 describe-target-health --target-group-arn <TARGET_GROUP_ARN>
   
   # 检查Pgpool实例的状态
   aws ec2 describe-instance-status --instance-ids <INSTANCE_ID>
   ```

2. **Pgpool服务未运行**：
   - 连接到EC2实例并检查服务状态
   
   ```bash
   # 使用SSM连接到实例
   aws ssm start-session --target <INSTANCE_ID>
   
   # 检查服务状态
   sudo systemctl status pgpool
   sudo systemctl status pgdoctor
   
   # 检查日志
   sudo journalctl -u pgpool
   sudo journalctl -u pgdoctor
   ```

3. **数据库连接失败**：
   - 验证Secrets Manager中的凭证是否正确
   - 检查Aurora集群状态
   
   ```bash
   # 检查Aurora集群状态
   aws rds describe-db-clusters --db-cluster-identifier <CLUSTER_ID>
   
   # 获取数据库凭证
   aws secretsmanager get-secret-value --secret-id <SECRET_ARN> --query SecretString --output text
   ```

4. **pgdoctor健康检查失败**：
   - 如果遇到错误 `Health check result: 500 unterminated quoted string in connection info string`
   - 检查pgdoctor配置文件中的连接参数是否使用了引号
   
   ```bash
   # 查看pgdoctor配置
   cat /etc/pgdoctor.cfg
   
   # 正确的配置应该不包含引号，例如：
   # pg_host = 127.0.0.1
   # pg_user = pdadmin
   # 而不是：
   # pg_host = '127.0.0.1'
   # pg_user = 'pdadmin'
   ```
   
   - 如需修复，移除配置文件中参数值周围的单引号：
   
   ```bash
   sudo sed -i "s/'127.0.0.1'/127.0.0.1/g" /etc/pgdoctor.cfg
   sudo sed -i "s/'pdadmin'/pdadmin/g" /etc/pgdoctor.cfg
   sudo sed -i "s/'postgres'/postgres/g" /etc/pgdoctor.cfg
   sudo systemctl restart pgdoctor
   ```

### 扩展问题

1. **Auto Scaling Group未正确扩展**：
   - 检查Auto Scaling Group配置
   - 查看CloudWatch指标和告警
   
   ```bash
   # 检查Auto Scaling Group配置
   aws autoscaling describe-auto-scaling-groups --auto-scaling-group-name <ASG_NAME>
   
   # 检查扩展策略
   aws autoscaling describe-policies --auto-scaling-group-name <ASG_NAME>
   ```

2. **启动模板问题**：
   - 检查启动模板配置
   - 验证AMI是否可用
   
   ```bash
   # 检查启动模板
   aws ec2 describe-launch-templates --launch-template-ids <TEMPLATE_ID>
   
   # 验证AMI状态
   aws ec2 describe-images --image-ids <AMI_ID>
   ```

### CDK部署问题

1. **CDK Bootstrap问题**：
   - 如果在项目目录内执行`cdk bootstrap`命令失败，错误信息显示：`ValueError: ami_id is required`
   - 原因：项目的`app.py`文件中的验证检查在bootstrap操作期间也会运行
   
   解决方案：
   - 在项目目录外执行bootstrap命令（推荐方法）：
     ```bash
     cd ~
     npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
     ```
   - 或在执行bootstrap时提供必要的参数：
     ```bash
     cdk bootstrap aws://ACCOUNT-NUMBER/REGION -c ami_id=dummy-value
     ```
   
   如果bootstrap过程失败并显示`ROLLBACK_COMPLETE`状态：
   ```bash
   aws cloudformation delete-stack --stack-name CDKToolkit
   aws cloudformation wait stack-delete-complete --stack-name CDKToolkit
   npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
   ```

2. **Aurora PostgreSQL密码限制问题**：
   - 如果部署过程中Aurora PostgreSQL集群创建失败，错误信息为：
     ```
     The parameter MasterUserPassword is not a valid password. Only printable ASCII characters besides '/', '@', '"', ' ' may be used.
     ```
   - 原因：Aurora PostgreSQL对密码有特定的字符限制，不允许使用斜杠(/)、邮箱符号(@)、双引号(")和空格( )
   
   解决方案：
   - 确保密码生成策略只排除Aurora PostgreSQL明确不允许的四个字符
   - 如果您自定义了CDK代码，请确保密码生成配置类似于：
     ```python
     secretsmanager.SecretStringGenerator(
         secret_string_template=json.dumps({"username": "pdadmin"}),
         generate_string_key="password",
         password_length=12,
         exclude_characters="\"/ @",  # 只排除Aurora PostgreSQL不允许的字符
         exclude_punctuation=False,
         include_space=False,
         require_each_included_type=True
     )
     ```

### 更新和修改

1. **更新堆栈**：
   要更新已部署的堆栈，使用相同的`cdk deploy`命令，但更改参数值：
   
   ```bash
   cdk deploy -c ami_id=<NEW_AMI_ID> -c desired_capacity=4
   ```

2. **删除堆栈**：
   要删除所有资源，运行：
   
   ```bash
   cdk destroy -c ami_id=<AMI_ID>
   ```
   
   注意：
   - 删除堆栈会删除所有相关资源，包括数据库。默认情况下，Aurora集群会创建最终快照。
   - 必须提供`ami_id`参数，因为app.py中的验证检查在destroy操作期间也会运行。
   - 可以使用任何有效的AMI ID，因为destroy操作不会实际使用该值。

## IAM角色和权限说明

在CDK部署中，我们为EC2实例创建了以下IAM角色和权限：

```python
# Create IAM role for EC2 instances
pgpool_role = iam.Role(
    self, "PgpoolRole",
    assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
    managed_policies=[
        iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
        iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchAgentServerPolicy")
    ]
)
```

这些策略的作用如下：

1. **AmazonSSMManagedInstanceCore**:
   - 允许EC2实例与AWS Systems Manager (SSM)服务进行通信
   - 使管理员能够通过SSM Session Manager安全地连接到EC2实例，无需开放SSH端口或管理SSH密钥
   - 允许实例接收SSM命令、参数和文档
   - 支持远程管理、补丁管理和自动化操作

2. **CloudWatchAgentServerPolicy**:
   - 允许EC2实例将日志和指标数据发送到Amazon CloudWatch
   - 支持CloudWatch Agent的完整功能，包括收集系统指标、应用程序日志和自定义指标
   - 允许实例读取和写入CloudWatch Logs
   - 支持创建和管理CloudWatch告警

这两个策略的组合使Pgpool-II实例能够：
- 被远程管理，无需直接SSH访问（提高安全性）
- 发送日志和指标到CloudWatch进行监控
- 支持自动化操作和问题排查
- 实现集中化的日志管理和监控

## 最佳实践总结

1. **CDK Bootstrap**:
   - CDK bootstrap是一次性操作，为AWS账户和区域设置必要的资源
   - 确保拥有足够的权限执行bootstrap操作（通常需要管理员权限）
   - 每个AWS账户和区域只需执行一次bootstrap操作

2. **PostgreSQL配置**:
   - 配置PostgreSQL连接参数时，避免在值周围使用不必要的引号
   - 使用符合数据库系统要求的密码生成策略，了解特定数据库系统的密码限制
   - 在故障排除时，先测试直接连接到数据库，确认凭证有效性

3. **安全性**:
   - 使用SSM Session Manager而不是SSH密钥进行实例管理
   - 将所有组件部署在适当的子网中（公有/私有）
   - 实施最小权限原则配置安全组和IAM策略
   - 使用Secrets Manager管理和轮换数据库凭证

4. **监控和告警**:
   - 配置全面的CloudWatch告警以监控关键指标
   - 设置自动通知机制以便及时响应问题
   - 定期审查日志和性能指标
