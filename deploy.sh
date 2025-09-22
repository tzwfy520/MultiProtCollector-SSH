#!/bin/bash

# SSH采集器部署脚本
# 支持Docker和传统部署方式

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
PROJECT_NAME="ssh-collector"
IMAGE_NAME="ssh-collector:latest"
CONTAINER_NAME="ssh-collector"
SERVICE_PORT=8000

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查依赖
check_dependencies() {
    log_info "检查系统依赖..."
    
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_warning "docker-compose未安装，将使用docker compose"
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    log_success "依赖检查完成"
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    
    mkdir -p data logs nginx/ssl
    
    # 设置权限
    chmod 755 data logs
    
    log_success "目录创建完成"
}

# 构建Docker镜像
build_image() {
    log_info "构建Docker镜像..."
    
    docker build -t $IMAGE_NAME .
    
    log_success "镜像构建完成"
}

# Docker部署
deploy_docker() {
    log_info "开始Docker部署..."
    
    # 停止现有容器
    if docker ps -a --format 'table {{.Names}}' | grep -q $CONTAINER_NAME; then
        log_info "停止现有容器..."
        docker stop $CONTAINER_NAME || true
        docker rm $CONTAINER_NAME || true
    fi
    
    # 启动新容器
    log_info "启动新容器..."
    docker run -d \
        --name $CONTAINER_NAME \
        --restart unless-stopped \
        -p $SERVICE_PORT:8000 \
        -v $(pwd)/data:/app/data \
        -v $(pwd)/logs:/app/logs \
        -e DEBUG=false \
        -e LOG_LEVEL=INFO \
        $IMAGE_NAME
    
    log_success "Docker部署完成"
}

# Docker Compose部署
deploy_compose() {
    log_info "开始Docker Compose部署..."
    
    # 停止现有服务
    $COMPOSE_CMD down || true
    
    # 启动服务
    $COMPOSE_CMD up -d
    
    log_success "Docker Compose部署完成"
}

# 传统部署
deploy_traditional() {
    log_info "开始传统部署..."
    
    # 检查Python
    if ! command -v python3 &> /dev/null; then
        log_error "Python3未安装"
        exit 1
    fi
    
    # 创建虚拟环境
    if [ ! -d "venv" ]; then
        log_info "创建Python虚拟环境..."
        python3 -m venv venv
    fi
    
    # 激活虚拟环境
    source venv/bin/activate
    
    # 安装依赖
    log_info "安装Python依赖..."
    pip install -r requirements.txt
    
    # 创建systemd服务文件
    create_systemd_service
    
    log_success "传统部署完成"
}

# 创建systemd服务
create_systemd_service() {
    log_info "创建systemd服务..."
    
    SERVICE_FILE="/etc/systemd/system/ssh-collector.service"
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=SSH Collector Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port $SERVICE_PORT
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # 重载systemd并启动服务
    sudo systemctl daemon-reload
    sudo systemctl enable ssh-collector
    sudo systemctl start ssh-collector
    
    log_success "systemd服务创建完成"
}

# 健康检查
health_check() {
    log_info "执行健康检查..."
    
    # 等待服务启动
    sleep 10
    
    # 检查服务状态
    if curl -f -s http://localhost:$SERVICE_PORT/health > /dev/null; then
        log_success "服务健康检查通过"
        
        # 显示服务信息
        echo
        log_info "服务信息:"
        curl -s http://localhost:$SERVICE_PORT/ | python3 -m json.tool
        
    else
        log_error "服务健康检查失败"
        exit 1
    fi
}

# 显示帮助信息
show_help() {
    echo "SSH采集器部署脚本"
    echo
    echo "用法: $0 [选项]"
    echo
    echo "选项:"
    echo "  docker          使用Docker部署"
    echo "  compose         使用Docker Compose部署"
    echo "  traditional     使用传统方式部署"
    echo "  build           仅构建Docker镜像"
    echo "  health          执行健康检查"
    echo "  stop            停止服务"
    echo "  logs            查看日志"
    echo "  help            显示此帮助信息"
    echo
}

# 停止服务
stop_service() {
    log_info "停止服务..."
    
    # 停止Docker容器
    if docker ps --format 'table {{.Names}}' | grep -q $CONTAINER_NAME; then
        docker stop $CONTAINER_NAME
        log_success "Docker容器已停止"
    fi
    
    # 停止Docker Compose
    if [ -f "docker-compose.yml" ]; then
        $COMPOSE_CMD down
        log_success "Docker Compose服务已停止"
    fi
    
    # 停止systemd服务
    if systemctl is-active --quiet ssh-collector; then
        sudo systemctl stop ssh-collector
        log_success "systemd服务已停止"
    fi
}

# 查看日志
show_logs() {
    log_info "查看服务日志..."
    
    if docker ps --format 'table {{.Names}}' | grep -q $CONTAINER_NAME; then
        docker logs -f $CONTAINER_NAME
    elif systemctl is-active --quiet ssh-collector; then
        sudo journalctl -u ssh-collector -f
    else
        log_warning "未找到运行中的服务"
    fi
}

# 主函数
main() {
    case "${1:-help}" in
        docker)
            check_dependencies
            create_directories
            build_image
            deploy_docker
            health_check
            ;;
        compose)
            check_dependencies
            create_directories
            deploy_compose
            health_check
            ;;
        traditional)
            create_directories
            deploy_traditional
            health_check
            ;;
        build)
            check_dependencies
            build_image
            ;;
        health)
            health_check
            ;;
        stop)
            stop_service
            ;;
        logs)
            show_logs
            ;;
        help|*)
            show_help
            ;;
    esac
}

# 执行主函数
main "$@"