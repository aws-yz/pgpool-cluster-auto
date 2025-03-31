# CDK Bootstrap 问题总结

## 问题描述

在使用AWS CDK部署Pgpool-II与Aurora PostgreSQL高可用架构时，执行`cdk bootstrap`命令可能会遇到以下问题：

1. 在项目目录内执行`cdk bootstrap aws://ACCOUNT-NUMBER/REGION`命令失败
2. 错误信息显示：`ValueError: ami_id is required. Please provide it using -c ami_id=<AMI_ID>`
3. 即使提供了ami_id参数，bootstrap过程可能仍然失败并进入`ROLLBACK_COMPLETE`状态

## 原因分析

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

## 解决方案

### 方法1：在项目目录外执行bootstrap命令（推荐）

```bash
# 切换到用户主目录或任何非项目目录
cd ~

# 使用npx执行bootstrap命令
npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

这种方法的优点：
- 避免加载项目特定的配置和验证
- 提供"干净"的bootstrap环境
- 不需要提供项目特定的参数

### 方法2：在项目目录内执行bootstrap并提供必要参数

```bash
cdk bootstrap aws://ACCOUNT-NUMBER/REGION -c ami_id=dummy-value
```

注意：
- 使用的dummy-value仅用于通过验证检查
- 实际bootstrap过程不会使用这个值

### 处理失败的bootstrap堆栈

如果bootstrap过程失败并显示`ROLLBACK_COMPLETE`状态，需要先删除失败的堆栈，然后重新尝试：

```bash
aws cloudformation delete-stack --stack-name CDKToolkit
aws cloudformation wait stack-delete-complete --stack-name CDKToolkit
npx cdk bootstrap aws://ACCOUNT-NUMBER/REGION
```

## 最佳实践

1. CDK bootstrap是一次性操作，为AWS账户和区域设置必要的资源
2. 建议在项目目录外执行bootstrap命令，避免项目特定的配置干扰
3. 确保拥有足够的权限执行bootstrap操作（通常需要管理员权限）
4. 每个AWS账户和区域只需执行一次bootstrap操作

## 参考资源

- [AWS CDK 官方文档 - Bootstrapping](https://docs.aws.amazon.com/cdk/latest/guide/bootstrapping.html)
- [AWS CDK CLI 命令参考](https://docs.aws.amazon.com/cdk/latest/guide/cli.html)
