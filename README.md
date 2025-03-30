# Pgpool-II Aurora PostgreSQL 高可用架构

这个项目实现了一个高可用的Pgpool-II与Aurora PostgreSQL架构，使用AWS CDK进行基础设施即代码部署。

## 获取项目代码

您可以通过以下方式获取项目代码：

### 使用Git克隆

```bash
git clone https://github.com/yourusername/pgpool-cluster-auto.git
cd pgpool-cluster-auto
```

### 直接下载

1. 访问项目GitHub页面: https://github.com/yourusername/pgpool-cluster-auto
2. 点击"Code"按钮，然后选择"Download ZIP"
3. 解压下载的ZIP文件
4. 进入解压后的目录
   ```bash
   cd pgpool-cluster-auto-main
   ```

## 项目组件

1. **AMI创建工具**：`create_pgpool_AMI.py` - 用于创建预配置的Pgpool-II和pgdoctor AMI
2. **CDK部署代码**：`pgpool_aurora_cdk/` - 用于部署完整架构的CDK代码

## 架构概述

![Pgpool-Aurora架构](pgpool-aurora-architecture.png)

该架构包括：
- Aurora PostgreSQL集群（1个写入节点，可配置数量的读取节点）
- 使用预先创建的AMI部署Pgpool-II的Auto Scaling Group
- 网络负载均衡器(NLB)，通过pgdoctor(8071端口)检查pgpool健康状态
- 适当的安全组配置和IAM角色

## 使用说明

### 1. 创建Pgpool-II AMI

首先，使用`create_pgpool_AMI.py`脚本创建包含Pgpool-II和pgdoctor的AMI：

```bash
# 安装所需的依赖
pip install boto3

# 执行AMI创建脚本
python create_pgpool_AMI.py <region_name> <cluster_endpoint> <reader_endpoint> [db_user] [db_password] [instance_type]
```

参数说明：
- `region_name`: AWS区域
- `cluster_endpoint`: Aurora集群写入端点（用于测试配置）
- `reader_endpoint`: Aurora集群读取端点（用于测试配置）
- `db_user`: 数据库用户名（可选，默认为'pdadmin'）
- `db_password`: 数据库密码（可选，默认为'1qaz2wsx'）
- `instance_type`: 用于构建AMI的实例类型（可选，默认为't3.micro'）

### 2. 部署完整架构

使用CDK部署完整架构：

```bash
cd pgpool_aurora_cdk
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 部署参数说明

CDK部署时可以通过上下文参数配置多种选项：

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

#### 部署命令示例

基本部署（仅提供必需参数）：
```bash
cdk deploy -c ami_id=ami-0123456789abcdef0
```

完整参数部署示例：
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

#### 部署流程

1. **检查CDK环境**：
   首先，检查是否已在目标区域初始化CDK环境：
   ```bash
   aws cloudformation describe-stacks --stack-name CDKToolkit
   ```
   如果命令返回错误"Stack with id CDKToolkit does not exist"，则需要执行初始化。

2. **初始化部署**（如果需要）：
   ```bash
   cdk bootstrap aws://ACCOUNT-NUMBER/REGION
   ```
   注意：如果是首次在账户/区域使用CDK，需要执行此命令

3. **查看变更**：
   ```bash
   cdk diff -c ami_id=ami-0123456789abcdef0
   ```
   这将显示将要创建的资源，但不会实际部署

4. **执行部署**：
   ```bash
   cdk deploy -c ami_id=ami-0123456789abcdef0 [其他参数]
   ```

5. **查看输出**：
   部署完成后，CDK会输出重要的资源信息，如NLB端点和Aurora集群端点

详细的部署说明请参考 [pgpool_aurora_cdk/README.md](pgpool_aurora_cdk/README.md)。

## 架构特点

1. **高可用性**：
   - Pgpool-II实例部署在多个可用区
   - Aurora集群跨多个可用区部署
   - 自动故障转移

2. **负载均衡**：
   - Pgpool-II提供连接池和负载均衡功能
   - 读写分离，优化查询性能

3. **自动扩展**：
   - 根据负载自动调整Pgpool-II实例数量

4. **健康检查**：
   - 使用pgdoctor监控Pgpool-II实例健康状态
   - NLB通过健康检查自动移除不健康的实例

5. **安全性**：
   - 使用Secrets Manager存储数据库凭证
   - 精细的安全组规则
   - 加密的数据存储

## 最佳实践

1. **网络配置**：
   - 将Pgpool-II实例部署在私有子网中
   - 将NLB部署在公共子网中（如果需要公共访问）
   - 将Aurora集群部署在隔离子网中

2. **安全性**：
   - 定期轮换数据库凭证
   - 限制安全组规则范围
   - 启用审计日志

3. **监控**：
   - 设置CloudWatch告警监控关键指标
   - 配置SNS通知机制

4. **备份**：
   - 配置Aurora自动备份策略
   - 考虑使用跨区域备份

## 故障排除

常见问题及解决方案请参考 [pgpool_aurora_cdk/README.md](pgpool_aurora_cdk/README.md) 中的故障排除部分。
