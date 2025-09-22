# SSH采集器部署指南

## 概述

SSH采集器支持多种部署方式，包括Docker、Docker Compose和传统服务器部署。本文档提供详细的部署步骤和配置说明。

## 部署前准备

### 系统要求

- **操作系统**: Linux (推荐 Ubuntu 20.04+, CentOS 8+)
- **内存**: 最小 512MB，推荐 2GB+
- **存储**: 最小 1GB 可用空间
- **网络**: 能够访问目标设备的SSH端口

### 依赖软件

#### Docker部署
- Docker 20.10+
- Docker Compose 2.0+ (可选)

#### 传统部署
- Python 3.8+
- pip
- systemd (用于服务管理)

## 部署方式

### 1. Docker部署 (推荐)

#### 快速部署
```bash
# 克隆项目
git clone <repository-url>
cd SSHCollector

# 使用部署脚本
./deploy.sh docker
```

#### 手动部署
```bash
# 构建镜像
docker build -t ssh-collector:latest .

# 创建数据目录
mkdir -p data logs

# 运行容器
docker run -d \
  --name ssh-collector \
  --restart unless-stopped \
  -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -e DEBUG=false \
  -e LOG_LEVEL=INFO \
  ssh-collector:latest
```

### 2. Docker Compose部署

#### 基础部署
```bash
# 启动服务
docker-compose up -d

# 查看状态
docker-compose ps

# 查看日志
docker-compose logs -f ssh-collector
```

#### 完整部署 (包含Nginx和RabbitMQ)
```bash
# 启动所有服务
docker-compose --profile with-nginx --profile with-mq up -d

# 访问管理界面
# RabbitMQ: http://localhost:15672 (admin/admin123)
# 应用: https://localhost (需要配置SSL证书)
```

### 3. 传统服务器部署

#### 使用部署脚本
```bash
./deploy.sh traditional
```

#### 手动部署
```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 创建必要目录
mkdir -p data logs

# 启动服务
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
```

#### 配置systemd服务
```bash
# 创建服务文件
sudo tee /etc/systemd/system/ssh-collector.service > /dev/null <<EOF
[Unit]
Description=SSH Collector Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable ssh-collector
sudo systemctl start ssh-collector
```

## 配置说明

### 环境变量配置

复制 `.env.example` 为 `.env` 并根据需要修改：

```bash
cp .env.example .env
```

主要配置项：

- `SERVICE_PORT`: 服务端口 (默认: 8000)
- `LOG_LEVEL`: 日志级别 (DEBUG/INFO/WARNING/ERROR)
- `MAX_CONNECTIONS`: 最大并发连接数
- `CONNECTION_TIMEOUT`: 连接超时时间
- `COMMAND_TIMEOUT`: 命令执行超时时间

### SSL证书配置 (Nginx)

如果使用Nginx反向代理，需要配置SSL证书：

```bash
# 创建自签名证书 (仅用于测试)
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/key.pem \
  -out nginx/ssl/cert.pem \
  -subj "/C=CN/ST=State/L=City/O=Organization/CN=localhost"

# 或使用Let's Encrypt证书
# certbot certonly --standalone -d your-domain.com
# cp /etc/letsencrypt/live/your-domain.com/fullchain.pem nginx/ssl/cert.pem
# cp /etc/letsencrypt/live/your-domain.com/privkey.pem nginx/ssl/key.pem
```

## 部署验证

### 健康检查

```bash
# 检查服务状态
curl http://localhost:8000/health

# 检查服务信息
curl http://localhost:8000/

# 测试连接功能
curl -X POST http://localhost:8000/test-connection \
  -H "Content-Type: application/json" \
  -d '{
    "host": "192.168.1.1",
    "username": "admin",
    "password": "password",
    "device_type": "huawei"
  }'
```

### 性能测试

```bash
# 使用ab进行压力测试
ab -n 100 -c 10 http://localhost:8000/health

# 使用wrk进行性能测试
wrk -t12 -c400 -d30s http://localhost:8000/health
```

## 监控和日志

### 日志查看

#### Docker部署
```bash
# 查看容器日志
docker logs -f ssh-collector

# 查看应用日志文件
docker exec ssh-collector tail -f /app/logs/collector.log
```

#### 传统部署
```bash
# 查看systemd日志
sudo journalctl -u ssh-collector -f

# 查看应用日志文件
tail -f logs/collector.log
```

### 监控指标

服务提供以下监控端点：

- `/health`: 健康检查
- `/metrics`: Prometheus指标 (如果启用)
- `/`: 服务信息

### 日志轮转配置

```bash
# 创建logrotate配置
sudo tee /etc/logrotate.d/ssh-collector > /dev/null <<EOF
/path/to/SSHCollector/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $USER $USER
    postrotate
        docker kill -s USR1 ssh-collector 2>/dev/null || true
    endscript
}
EOF
```

## 故障排除

### 常见问题

1. **端口被占用**
   ```bash
   # 查看端口占用
   sudo netstat -tlnp | grep :8000
   
   # 修改端口配置
   export SERVICE_PORT=8001
   ```

2. **权限问题**
   ```bash
   # 检查文件权限
   ls -la data/ logs/
   
   # 修复权限
   sudo chown -R $USER:$USER data/ logs/
   ```

3. **内存不足**
   ```bash
   # 查看内存使用
   free -h
   
   # 调整Docker内存限制
   docker run --memory=1g ...
   ```

4. **网络连接问题**
   ```bash
   # 测试网络连通性
   telnet target-host 22
   
   # 检查防火墙设置
   sudo ufw status
   ```

### 调试模式

启用调试模式获取更详细的日志：

```bash
# 设置环境变量
export DEBUG=true
export LOG_LEVEL=DEBUG

# 重启服务
./deploy.sh stop
./deploy.sh docker
```

## 安全建议

1. **网络安全**
   - 使用防火墙限制访问
   - 配置SSL/TLS加密
   - 定期更新证书

2. **认证安全**
   - 使用强密码或密钥认证
   - 定期轮换凭据
   - 限制SSH用户权限

3. **系统安全**
   - 定期更新系统和依赖
   - 监控异常访问
   - 备份重要数据

## 备份和恢复

### 数据备份

```bash
# 备份数据目录
tar -czf backup-$(date +%Y%m%d).tar.gz data/ logs/

# 备份到远程服务器
rsync -av data/ user@backup-server:/backup/ssh-collector/
```

### 服务恢复

```bash
# 恢复数据
tar -xzf backup-20240101.tar.gz

# 重启服务
./deploy.sh stop
./deploy.sh docker
```

## 升级指南

### Docker部署升级

```bash
# 拉取最新代码
git pull

# 重新构建和部署
./deploy.sh stop
./deploy.sh docker
```

### 传统部署升级

```bash
# 停止服务
sudo systemctl stop ssh-collector

# 更新代码
git pull

# 更新依赖
source venv/bin/activate
pip install -r requirements.txt

# 启动服务
sudo systemctl start ssh-collector
```

## 支持和联系

如有问题，请：

1. 查看日志文件获取错误信息
2. 检查配置文件是否正确
3. 参考故障排除章节
4. 提交Issue到项目仓库