# CDK Bootstrap 和 pgdoctor 配置问题总结

## 问题1: CDK Bootstrap 问题

### 问题描述

在使用AWS CDK部署Pgpool-II与Aurora PostgreSQL高可用架构时，执行`cdk bootstrap`命令可能会遇到以下问题：

1. 在项目目录内执行`cdk bootstrap aws://ACCOUNT-NUMBER/REGION`命令失败
2. 错误信息显示：`ValueError: ami_id is required. Please provide it using -c ami_id=<AMI_ID>`
3. 即使提供了ami_id参数，bootstrap过程可能仍然失败并进入`ROLLBACK_COMPLETE`状态

### 原因分析

当在项目目录内执行`cdk bootstrap`命令时，CDK CLI会：

1. 加载项目的`app.py`文件
2. 处理CDK应用程序
3. 然后执行bootstrap操作

问题出在项目的`app.py`文件中包含以下验证检查：
```python
if not ami_id:
    raise ValueError("ami_id is required. Please provide it using -c ami_id=<AMI_ID>")
```

这个检查在bootstrap操作期间也会运行，导致过程失败。

### 解决方案

我们已经修改了`app.py`文件，添加了对bootstrap命令的特殊处理：

```python
# Skip ami_id validation for bootstrap command
is_bootstrap = len(sys.argv) > 1 and sys.argv[1] == "bootstrap"

# Validate required parameters - skip for bootstrap
if not ami_id and not is_bootstrap:
    raise ValueError("ami_id is required. Please provide it using -c ami_id=<AMI_ID>")

# Use a dummy AMI ID for bootstrap if none provided
if is_bootstrap and not ami_id:
    ami_id = "ami-dummy-for-bootstrap"
```

现在可以直接在项目目录中执行bootstrap命令，无需提供ami_id参数：

```bash
cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

### 处理失败的bootstrap堆栈

如果bootstrap过程失败并显示`ROLLBACK_COMPLETE`状态，您需要先删除失败的堆栈，然后重新尝试：

```bash
aws cloudformation delete-stack --stack-name CDKToolkit
aws cloudformation wait stack-delete-complete --stack-name CDKToolkit
cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

## 问题2: pgdoctor 配置问题

### 问题描述

部署后，pgdoctor服务无法正常工作，报错：
```
Health check result: 500 unterminated quoted string in connection info string
```

### 原因分析

pgdoctor配置文件中的连接参数使用了单引号，导致PostgreSQL连接字符串解析错误。例如：

```
pg_host = '127.0.0.1'
pg_user = 'pdadmin'
pg_password = '<password>'
pg_database = 'postgres'
```

### 解决方案

我们已经修改了以下两个位置的代码，移除了参数值周围的单引号：

1. **CDK堆栈中的用户数据脚本**：
```bash
# Update pgdoctor configuration - removing quotes to fix connection string issues
cat > /etc/pgdoctor.cfg << EOF
# Runtime settings
http_port = 8071
syslog_facility = local7

# PostgreSQL connection settings
pg_host = 127.0.0.1
pg_port = 9999
pg_user = $DB_USERNAME
pg_password = $DB_PASSWORD
pg_database = postgres
pg_connection_timeout = 3

# Health check queries through pgpool to Aurora
"SELECT 1"
EOF

chmod 644 /etc/pgdoctor.cfg
```

2. **AMI创建脚本中的pgdoctor配置**：
```bash
# 配置pgdoctor - 不使用引号以避免连接字符串解析错误
cat > /etc/pgdoctor.cfg << EOF
# Runtime settings
http_port = 8071
syslog_facility = local7

# PostgreSQL connection settings
pg_host = 127.0.0.1
pg_port = 9999
pg_user = {db_user}
pg_password = {db_password}
pg_database = postgres
pg_connection_timeout = 3

# Health check queries through pgpool to Aurora
"SELECT 1"
EOF
```

这样配置后，pgdoctor应该能够正确解析连接字符串并连接到PostgreSQL。

## 最佳实践

1. CDK bootstrap是一次性操作，为AWS账户和区域设置必要的资源
2. 确保拥有足够的权限执行bootstrap操作（通常需要管理员权限）
3. 每个AWS账户和区域只需执行一次bootstrap操作
4. 配置PostgreSQL连接参数时，避免在值周围使用不必要的引号

## 参考资源

- [AWS CDK 官方文档 - Bootstrapping](https://docs.aws.amazon.com/cdk/latest/guide/bootstrapping.html)
- [AWS CDK CLI 命令参考](https://docs.aws.amazon.com/cdk/latest/guide/cli.html)
- [pgdoctor 文档](https://github.com/thumbtack/pgdoctor)
