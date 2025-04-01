import boto3
import time
import sys

def create_pgpool_ami(region_name, cluster_endpoint, reader_endpoint, db_user='pdadmin', db_password='1qaz2wsx', instance_type='t3.micro'):
    # 初始化EC2客户端
    ec2 = boto3.client('ec2', region_name=region_name)
    
    # 查找最新的Amazon Linux 2023 AMI
    response = ec2.describe_images(
        Owners=['amazon'],
        Filters=[
            {'Name': 'name', 'Values': ['al2023-ami-2023*-x86_64']},
            {'Name': 'state', 'Values': ['available']}
        ]
    )
    
    # 按创建日期排序，获取最新的AMI
    amis = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
    if not amis:
        print("未找到Amazon Linux 2023 AMI")
        return None
    
    base_ami_id = amis[0]['ImageId']
    print(f"使用基础AMI: {base_ami_id}")
    
    # 创建安全组
    try:
        sg_response = ec2.create_security_group(
            GroupName=f'pgpool-build-sg-{int(time.time())}',
            Description='Security group for Pgpool AMI building'
        )
        security_group_id = sg_response['GroupId']
        
        # 添加SSH访问规则
        ec2.authorize_security_group_ingress(
            GroupId=security_group_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
    except Exception as e:
        print(f"创建安全组时出错: {str(e)}")
        security_group_id = 'sg-default'  # 使用默认安全组
    
    # 准备用户数据脚本
    user_data = fr'''#!/bin/bash
# 更新系统
dnf update -y

# 安装必要的依赖
# Install required packages for pgdoctor and pgpool
dnf install -y gcc make wget git postgresql15 libpq-devel openssl-devel pam-devel readline-devel systemd-devel
dnf install -y libmicrohttpd-devel check-devel

# 下载并解压Pgpool
cd /tmp
wget "https://www.pgpool.net/mediawiki/download.php?f=pgpool-II-4.5.6.tar.gz" -O pgpool-II-4.5.6.tar.gz
tar xzf pgpool-II-4.5.6.tar.gz
sudo dnf install libtool
cd pgpool-II-4.5.6
autoreconf -fi


# 创建pgpool系统用户和家目录
useradd -r -m -s /sbin/nologin pgpool

# 编译和安装Pgpool
./configure --prefix=/usr/local --with-openssl
echo "Configure完成，检查配置结果..."
cat config.log | grep "binary dir"

make
sudo make install

# 配置共享库
echo "/usr/local/lib" > /etc/ld.so.conf.d/pgpool.conf
ldconfig

# 创建必要的目录
mkdir -p /run/pgpool
mkdir -p /var/log/pgpool
mkdir -p /var/run/pgdoctor
mkdir -p /var/log/pgdoctor

# 设置目录权限
chown -R pgpool:pgpool /run/pgpool
chown -R pgpool:pgpool /var/log/pgpool
chown -R pgpool:pgpool /var/run/pgdoctor
chown -R pgpool:pgpool /var/log/pgdoctor
chmod 755 /run/pgpool
chmod 755 /var/log/pgpool
chmod 755 /var/log/pgdoctor

# 创建符号链接以保持兼容性
ln -sf /run/pgpool /var/run/pgpool

# 创建默认配置文件
cat > /usr/local/etc/pgpool.conf << EOF
listen_addresses = '*'
port = 9999
socket_dir = '/run/pgpool'
pcp_socket_dir = '/run/pgpool'
pid_file_name = '/run/pgpool/pgpool.pid'
logdir = '/var/log/pgpool'
#log配置
#log_destination = 'syslog,stderr'
log_destination = 'stderr'
log_line_prefix = '%t: pid %p: '   # printf-style string to output at beginning of each log line.
log_connections = off
log_disconnections = off
log_hostname = on
log_statement = on
#log_error_verbosity = VERBOSE
#log_min_messages = debug5
#client_min_messages = debug5
log_per_node_statement = on
log_client_messages = off
log_standby_delay = 'if_over_threshold'
syslog_facility = 'LOCAL0'
syslog_ident = 'pgpool'
logging_collector = on
log_directory = '/var/log/pgpool'
log_filename = 'pgpool-%Y-%m-%d_%H%M%S.log'
log_truncate_on_rotation = on
log_rotation_age = 1d
log_rotation_size = 10MB

#load balance配置
load_balance_mode = on
statement_level_load_balance = on
ignore_leading_white_space = on
read_only_function_list = ''
write_function_list = ''
primary_routing_query_pattern_list = ''
database_redirect_preference_list = ''
app_name_redirect_preference_list = ''
allow_sql_comments = off
disable_load_balance_on_write = 'transaction'

# Aurora streaming replication settings
backend_clustering_mode = 'streaming_replication'
sr_check_period = 0
enable_pool_hba = on
pool_hba_file = '/usr/local/etc/pool_hba.conf'
pool_passwd = '/usr/local/etc/pool_passwd'
health_check_period = 0
failover_on_backend_error = off

# Backend settings
backend_hostname0 = '{cluster_endpoint}'
backend_port0 = 5432
backend_weight0 = 1
backend_flag0 = 'ALWAYS_PRIMARY|DISALLOW_TO_FAILOVER'
backend_data_directory0 = '/tmp'
backend_application_name0 = 'main'

backend_hostname1 = '{reader_endpoint}'
backend_port1 = 5432
backend_weight1 = 1
backend_flag1 = 'DISALLOW_TO_FAILOVER'
backend_data_directory1 = '/tmp'
backend_application_name1 = 'replica'

# Aurora connection settings
sr_check_user = '{db_user}'
sr_check_password = '{db_password}'
health_check_user = '{db_user}'
health_check_password = '{db_password}'

# Connection settings
num_init_children = 32
max_pool = 4
authentication_timeout = 60

# SSL settings
ssl = off
EOF

# 创建pool_hba.conf
cat > /usr/local/etc/pool_hba.conf << "EOF"
# TYPE  DATABASE    USER        CIDR-ADDRESS          METHOD
local   all         all                               trust
host    all         all         127.0.0.1/32          trust
host    all         all         ::1/128               trust
host    all         all         0.0.0.0/0             scram-sha-256
EOF

# 创建pool_passwd文件
echo "{db_user}:{db_password}" > /usr/local/etc/pool_passwd

# 设置配置文件权限
chown pgpool:pgpool /usr/local/etc/pgpool.conf
chmod 600 /usr/local/etc/pgpool.conf
chown pgpool:pgpool /usr/local/etc/pool_hba.conf
chmod 600 /usr/local/etc/pool_hba.conf
chown pgpool:pgpool /usr/local/etc/pool_passwd
chmod 600 /usr/local/etc/pool_passwd

# 创建Pgpool服务
cat > /etc/systemd/system/pgpool.service << "EOF"
[Unit]
Description=Pgpool-II
After=network.target

[Service]
Type=forking
User=pgpool
Group=pgpool
ExecStart=/usr/local/bin/pgpool -f /usr/local/etc/pgpool.conf
ExecStop=/usr/local/bin/pgpool -f /usr/local/etc/pgpool.conf -m fast stop
ExecReload=/usr/local/bin/pgpool -f /usr/local/etc/pgpool.conf reload
PIDFile=/run/pgpool/pgpool.pid
RuntimeDirectory=pgpool
RuntimeDirectoryMode=0755
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF


# 安装pgdoctor健康检查服务
cd /tmp
git clone https://github.com/WangYunzhang/pgdoctor.git
cd pgdoctor

# 编译和安装pgdoctor
make
sudo make install

# 确保pgdoctor相关目录和文件的所有权正确
chown pgpool:pgpool /usr/local/bin/pgdoctor
chmod 755 /usr/local/bin/pgdoctor

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

# 设置配置文件权限
chown pgpool:pgpool /etc/pgdoctor.cfg
chmod 600 /etc/pgdoctor.cfg

# 更新pgdoctor服务配置
cat > /etc/systemd/system/pgdoctor.service << "EOF"
[Unit]
Description=PostgreSQL Health Check Service
After=pgpool.service
Requires=pgpool.service

[Service]
TimeoutStartSec=0
Type=simple
ExecStart=/usr/local/bin/pgdoctor
Restart=on-failure
RestartSec=5
User=pgpool
Group=pgpool
RuntimeDirectory=pgdoctor
LogsDirectory=pgdoctor
RuntimeDirectoryMode=0755
LogsDirectoryMode=0755

[Install]
WantedBy=multi-user.target
EOF

# 启用服务
systemctl daemon-reload
systemctl enable pgpool.service
systemctl enable pgdoctor.service

# 清理
rm -rf /tmp/pgpool-II-4.5.6*
rm -rf /tmp/pgdoctor

# 通知AMI创建脚本实例已准备好
touch /tmp/ami_ready
'''
    
    # 启动EC2实例
    instance_response = ec2.run_instances(
        ImageId=base_ami_id,
        InstanceType=instance_type,
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=[security_group_id],
        UserData=user_data,
        InstanceInitiatedShutdownBehavior='stop'
    )
    
    instance_id = instance_response['Instances'][0]['InstanceId']
    print(f"已启动EC2实例: {instance_id}")
    
    # 等待实例状态为running
    print("等待实例启动...")
    waiter = ec2.get_waiter('instance_running')
    waiter.wait(InstanceIds=[instance_id])
    
    # 等待实例状态检查通过
    print("等待实例状态检查通过...")
    waiter = ec2.get_waiter('instance_status_ok')
    waiter.wait(InstanceIds=[instance_id])
    
    # 等待用户数据脚本完成
    print("等待安装脚本完成...")
    # 这里可以使用SSM或SSH检查/tmp/ami_ready文件是否存在
    # 为简化，我们只等待固定时间
    time.sleep(300)  # 等待5分钟让脚本完成
    
    # 停止实例
    print("停止实例...")
    ec2.stop_instances(InstanceIds=[instance_id])
    
    # 等待实例停止
    waiter = ec2.get_waiter('instance_stopped')
    waiter.wait(InstanceIds=[instance_id])
    
    # 创建AMI
    ami_name = f"pgpool-II-4.5.6-{int(time.time())}"
    print(f"创建AMI: {ami_name}")
    ami_response = ec2.create_image(
        InstanceId=instance_id,
        Name=ami_name,
        Description='Pgpool-II 4.5.6 on Amazon Linux 2023 with health check'
    )
    
    ami_id = ami_response['ImageId']
    
    # 等待AMI可用
    print(f"等待AMI {ami_id} 可用...")
    waiter = ec2.get_waiter('image_available')
    waiter.wait(ImageIds=[ami_id])
    
    # 清理资源
    print("清理资源...")
    ec2.terminate_instances(InstanceIds=[instance_id])
    
    # 等待实例终止
    waiter = ec2.get_waiter('instance_terminated')
    waiter.wait(InstanceIds=[instance_id])
    
    try:
        ec2.delete_security_group(GroupId=security_group_id)
    except Exception as e:
        print(f"删除安全组时出错: {str(e)}")
    
    print(f"AMI创建完成: {ami_id}")
    return ami_id

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python create_pgpool_ami.py <region_name> <cluster_endpoint> <reader_endpoint> [db_user] [db_password] [instance_type]")
        sys.exit(1)
    
    region = sys.argv[1]
    cluster_endpoint = sys.argv[2]
    reader_endpoint = sys.argv[3]
    db_user = sys.argv[4] if len(sys.argv) > 4 else 'pdadmin'
    db_password = sys.argv[5] if len(sys.argv) > 5 else '1qaz2wsx'
    instance_type = sys.argv[6] if len(sys.argv) > 6 else 't3.micro'
    
    ami_id = create_pgpool_ami(region, cluster_endpoint, reader_endpoint, db_user, db_password, instance_type)
    if ami_id:
        print(f"成功创建AMI: {ami_id}")
    else:
        print("AMI创建失败")
        sys.exit(1)
