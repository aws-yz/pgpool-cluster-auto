# Pgpool-II Aurora PostgreSQL 高可用架构

这个项目实现了一个高可用的Pgpool-II与Aurora PostgreSQL架构，使用AWS CDK进行基础设施即代码部署。

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
cdk deploy -c ami_id=<AMI_ID> [其他参数]
```

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
