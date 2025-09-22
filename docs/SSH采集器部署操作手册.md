# SSH采集器部署操作手册

## 概述

SSH采集器是一个基于FastAPI的网络设备信息采集系统，支持通过SSH协议连接各种网络设备（华为、思科、H3C等）并执行命令采集信息。

## 系统要求

### 服务器要求
- **操作系统**: Linux (推荐Ubuntu 20.04+/CentOS 7+)
- **内存**: 最小2GB，推荐4GB+
- **存储**: 最小10GB可用空间
- **网络**: 能够访问目标网络设备的SSH端口(22)

### 软件依赖
- Docker 20.10+
- Docker Compose 2.0+
- Python 3.11+ (如果选择传统部署)

## 部署方式

### 方式一：自动化脚本部署（推荐）

#### 1. SSH密钥部署（最安全）
```bash
# 使用SSH密钥自动部署
./deploy-ssh-key.sh

# 脚本特点：
# - 使用SSH密钥认证，无需输入密码
# - 自动检查服务器环境
# - 自动安装Docker和Docker Compose
# - 完整的部署验证
```

#### 2. 密码认证部署
```bash
# 使用密码认证部署（需要sshpass）
./deploy-to-server.sh

# 脚本特点：
# - 自动安装sshpass依赖
# - 密码自动输入
# - 完整的部署流程
```

#### 3. 简化部署
```bash
# 生成部署包并上传
./deploy-simple.sh

# 脚本特点：
# - 生成独立部署包
# - 减少网络传输
# - 适合网络环境较差的情况
```

### 方式二：手动部署

#### 1. 准备部署文件
```bash
# 在本地准备部署文件
mkdir -p /tmp/ssh-collector-deploy
cd /tmp/ssh-collector-deploy

# 复制必要文件
cp -r /path/to/project/src .
cp /path/to/project/requirements.txt .
cp /path/to/project/Dockerfile.alpine Dockerfile
cp /path/to/project/docker-compose.alpine.yml docker-compose.yml
cp /path/to/project/healthcheck.sh .
```

#### 2. 上传到服务器
```bash
# 上传文件到服务器
scp -r /tmp/ssh-collector-deploy/* user@server:/opt/ssh-collector/
```

#### 3. 服务器端部署
```bash
# 登录服务器
ssh user@server

# 进入部署目录
cd /opt/ssh-collector

# 创建必要目录
mkdir -p data logs

# 构建并启动服务
docker-compose build --no-cache
docker-compose up -d
```

## 关键配置修改

### 1. SSH连接参数优化
在部署过程中，对`src/ssh_core.py`进行了关键修改：

```python
# 第146行附近的netmiko连接参数
device_params = {
    'device_type': device_type,
    'host': host,
    'username': username,
    'password': password,
    'port': port,
    'timeout': 30,
    'session_timeout': 60,
    'auth_timeout': 30,
    'banner_timeout': 15,
    'conn_timeout': 10,
    'global_delay_factor': 2,
    'fast_cli': False,
    'session_log': f'logs/session_{host}_{int(time.time())}.log'
}
```

**修改说明**：
- 增加了`global_delay_factor`: 2 - 提高命令执行稳定性
- 设置`fast_cli`: False - 确保命令完整执行
- 添加了详细的超时参数配置
- 增加了会话日志记录

### 2. 环境变量配置
```bash
# docker-compose.alpine.yml中的关键环境变量
environment:
  - APP_NAME=SSH采集器
  - SERVICE_PORT=8000
  - LOG_LEVEL=INFO
  - MAX_CONNECTIONS=100
  - CONNECTION_TIMEOUT=30
  - COMMAND_TIMEOUT=300
```

### 3. 健康检查配置
```bash
# 健康检查参数
healthcheck:
  test: ["CMD", "./healthcheck.sh"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## 部署验证

### 1. 容器状态检查
```bash
# 检查容器运行状态
docker-compose ps

# 预期输出：
# NAME            COMMAND                  SERVICE         STATUS          PORTS
# ssh-collector   "python -m uvicorn s…"   ssh-collector   Up 2 minutes    0.0.0.0:8000->8000/tcp
```

### 2. 服务健康检查
```bash
# 本地健康检查
curl http://localhost:8000/health

# 预期输出：
# {"service":"SSH采集器","version":"1.0.0","status":"运行中"}
```

### 3. API功能测试
```bash
# 测试设备采集接口
curl -X POST "http://localhost:8000/api/collect" \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.1",
    "username": "admin",
    "password": "password",
    "device_type": "huawei",
    "commands": ["display version"]
  }'
```

### 4. 端口监听检查
```bash
# 检查端口监听状态
netstat -tlnp | grep 8000
# 或
ss -tlnp | grep 8000

# 预期输出：
# tcp6  0  0  :::8000  :::*  LISTEN  1234/docker-proxy
```

## 网络访问配置

### 1. 防火墙配置
```bash
# Ubuntu/Debian
sudo ufw allow 8000/tcp

# CentOS/RHEL
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 2. 云服务器安全组
如果使用云服务器，需要在安全组中开放8000端口：
- 协议：TCP
- 端口：8000
- 源：0.0.0.0/0（或指定IP段）

## 故障排除

### 1. 容器启动失败
```bash
# 查看容器日志
docker-compose logs ssh-collector

# 常见问题：
# - 端口被占用：修改docker-compose.yml中的端口映射
# - 权限问题：检查data和logs目录权限
# - 依赖缺失：重新构建镜像
```

### 2. 健康检查失败
```bash
# 检查健康检查脚本
docker-compose exec ssh-collector ./healthcheck.sh

# 常见问题：
# - SystemMonitor缺少get_uptime方法（已修复）
# - 网络连接问题
# - 服务启动时间过长
```

### 3. SSH连接失败
```bash
# 查看SSH连接日志
tail -f logs/session_*.log

# 常见问题：
# - 网络不通：检查网络连接和防火墙
# - 认证失败：检查用户名密码
# - 超时问题：调整timeout参数
# - 提示符匹配：调整global_delay_factor
```

### 4. API调用失败
```bash
# 检查API日志
docker-compose logs ssh-collector | grep ERROR

# 常见问题：
# - 参数格式错误：检查JSON格式
# - 设备类型不支持：使用正确的device_type
# - 命令执行超时：增加timeout值
```

## 性能优化

### 1. 并发连接数调整
```yaml
# docker-compose.alpine.yml
environment:
  - MAX_CONNECTIONS=200  # 根据服务器性能调整
```

### 2. 超时参数优化
```python
# src/ssh_core.py中的超时参数
'timeout': 30,           # 连接超时
'session_timeout': 60,   # 会话超时
'auth_timeout': 30,      # 认证超时
'banner_timeout': 15,    # Banner超时
'conn_timeout': 10,      # 连接建立超时
```

### 3. 日志级别调整
```yaml
# 生产环境建议使用INFO或WARNING
environment:
  - LOG_LEVEL=INFO
```

## 安全建议

### 1. 网络安全
- 使用VPN或专用网络访问
- 限制API访问IP范围
- 定期更换设备访问凭据

### 2. 系统安全
- 定期更新Docker镜像
- 使用非root用户运行容器
- 定期备份配置和日志

### 3. 访问控制
- 实施API认证机制
- 记录访问日志
- 监控异常访问

## 维护操作

### 1. 日志管理
```bash
# 查看实时日志
docker-compose logs -f ssh-collector

# 清理旧日志
find logs/ -name "*.log" -mtime +7 -delete
```

### 2. 数据备份
```bash
# 备份数据目录
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/

# 恢复数据
tar -xzf backup-20240101.tar.gz
```

### 3. 服务重启
```bash
# 重启服务
docker-compose restart ssh-collector

# 重新构建并重启
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### 4. 更新部署
```bash
# 拉取最新代码
git pull

# 重新部署
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

## 监控和告警

### 1. 健康监控
```bash
# 定期健康检查脚本
#!/bin/bash
if ! curl -f http://localhost:8000/health > /dev/null 2>&1; then
    echo "SSH采集器服务异常" | mail -s "服务告警" admin@company.com
fi
```

### 2. 资源监控
```bash
# 监控容器资源使用
docker stats ssh-collector

# 监控磁盘空间
df -h /opt/ssh-collector
```

## 联系支持

如遇到问题，请：
1. 查看本手册的故障排除章节
2. 检查日志文件获取详细错误信息
3. 联系技术支持团队

---

**版本**: 1.0.0  
**更新日期**: 2024-01-22  
**适用环境**: 生产环境/测试环境