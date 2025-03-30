# Pgpool-II Aurora PostgreSQL Architecture

这个项目使用AWS CDK实现了一个高可用的Pgpool-II与Aurora PostgreSQL架构。该架构包括：

- Aurora PostgreSQL集群（1个写入节点，可配置数量的读取节点）
- 使用预先创建的AMI部署Pgpool-II的Auto Scaling Group
- 网络负载均衡器(NLB)，通过pgdoctor(8071端口)检查pgpool健康状态
- 适当的安全组配置和IAM角色

## 架构概述

![Pgpool-Aurora架构](../pgpool-aurora-architecture.png)

该架构提供以下功能：
- 高可用性：通过在多个可用区部署Pgpool-II实例和Aurora节点
- 负载均衡：Pgpool-II提供连接池和负载均衡功能
- 自动扩展：根据负载自动调整Pgpool-II实例数量
- 健康检查：使用pgdoctor监控Pgpool-II实例健康状态

## 前提条件

1. 已创建包含pgpool和pgdoctor的AMI（使用`create_pgpool_AMI.py`脚本）
2. 安装了AWS CDK CLI
3. 配置了AWS凭证

## 部署说明

### 1. 安装依赖

```bash
# 创建并激活虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置参数

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

### 参数说明

| 参数 | 描述 | 默认值 |
|------|------|--------|
| ami_id | Pgpool-II AMI ID（必需） | - |
| vpc_id | 现有VPC ID（可选，如不提供将创建新VPC） | - |
| subnet_ids | 子网ID列表，逗号分隔（可选） | - |
| instance_type | Pgpool-II实例类型 | t3.medium |
| disk_size | Pgpool-II实例磁盘大小(GB) | 20 |
| min_capacity | Auto Scaling Group最小容量 | 2 |
| max_capacity | Auto Scaling Group最大容量 | 4 |
| desired_capacity | Auto Scaling Group期望容量 | 2 |
| db_instance_class | Aurora实例类型 | db.t3.medium |
| db_replica_count | Aurora只读副本数量 | 1 |

## 最佳实践

1. **高可用性**：
   - 确保Pgpool-II实例部署在至少两个可用区
   - Aurora集群也应跨多个可用区部署

2. **安全性**：
   - 使用密钥管理服务(KMS)加密Aurora数据
   - 实现精细的安全组规则
   - 使用Secrets Manager存储数据库凭证

3. **监控**：
   - 设置CloudWatch告警监控关键指标
   - 配置SNS通知机制

4. **备份**：
   - 配置Aurora自动备份策略

## 部署后验证

部署完成后，您可以通过以下方式验证架构：

1. 连接到NLB端点（输出中的`NLBEndpoint`）
2. 使用PostgreSQL客户端工具连接（端口5432）
3. 验证连接池和负载均衡功能

## 清理资源

要删除所有创建的资源，运行：

```bash
cdk destroy
```

## 故障排除

1. **连接问题**：
   - 检查安全组规则
   - 验证NLB健康检查配置
   - 检查Pgpool-II和pgdoctor服务状态

2. **扩展问题**：
   - 检查Auto Scaling Group配置
   - 查看CloudWatch指标和告警
