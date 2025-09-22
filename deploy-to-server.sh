#!/bin/bash

# SSH采集器服务器部署脚本
# 目标服务器: 115.190.80.219
# 用户: eccom123
# 部署版本: Alpine

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 服务器配置
SERVER_IP="115.190.80.219"
SERVER_USER="eccom123"
SERVER_PASSWORD="Eccom@12345"
DEPLOY_DIR="/home/eccom123/ssh-collector"
APP_PORT="8000"

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

# 检查本地环境
check_local_env() {
    log_info "检查本地环境..."
    
    # 检查必要文件
    local required_files=(
        "Dockerfile.multi-stage"
        "docker-compose.multi-stage.yml"
        "requirements.txt"
        "src/"
        "healthcheck.sh"
        ".env.example"
    )
    
    for file in "${required_files[@]}"; do
        if [ ! -e "$file" ]; then
            log_error "缺少必要文件: $file"
            exit 1
        fi
    done
    
    log_success "本地环境检查完成"
}

# 创建部署包
create_deploy_package() {
    log_info "创建部署包..."
    
    local package_name="ssh-collector-deploy.tar.gz"
    
    # 创建临时目录
    local temp_dir=$(mktemp -d)
    local deploy_temp="$temp_dir/ssh-collector"
    
    mkdir -p "$deploy_temp"
    
    # 复制必要文件
    cp -r src/ "$deploy_temp/"
    cp Dockerfile.multi-stage "$deploy_temp/"
    cp docker-compose.multi-stage.yml "$deploy_temp/"
    cp requirements.txt "$deploy_temp/"
    cp healthcheck.sh "$deploy_temp/"
    cp .env.example "$deploy_temp/"
    
    # 创建服务器专用的docker-compose文件
    cat > "$deploy_temp/docker-compose.yml" << 'EOF'
version: '3.8'

services:
  ssh-collector:
    build:
      context: .
      dockerfile: Dockerfile.multi-stage
      target: runtime
    container_name: ssh-collector-alpine
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - APP_NAME=SSH采集器-生产环境
      - APP_VERSION=1.0.0-alpine
      - DEBUG=false
      - LOG_LEVEL=INFO
      - SERVICE_HOST=0.0.0.0
      - SERVICE_PORT=8000
      - COLLECTOR_ID=collector-prod-001
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    networks:
      - ssh-collector-network
    healthcheck:
      test: ["CMD", "./healthcheck.sh"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  ssh-collector-network:
    driver: bridge

volumes:
  ssh-collector-data:
  ssh-collector-logs:
EOF

    # 创建服务器部署脚本
    cat > "$deploy_temp/server-deploy.sh" << 'EOF'
#!/bin/bash

# 服务器端部署脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查Docker是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_info "安装Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo usermod -aG docker $USER
        log_success "Docker安装完成"
    else
        log_info "Docker已安装"
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_info "安装Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/download/v2.20.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        log_success "Docker Compose安装完成"
    else
        log_info "Docker Compose已安装"
    fi
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."
    mkdir -p data logs
    chmod 755 data logs
    log_success "目录创建完成"
}

# 配置环境变量
setup_env() {
    log_info "配置环境变量..."
    if [ ! -f .env ]; then
        cp .env.example .env
        log_info "请根据需要修改 .env 文件中的配置"
    fi
}

# 构建和启动服务
deploy_service() {
    log_info "构建和启动SSH采集器服务..."
    
    # 停止现有服务
    docker-compose down 2>/dev/null || true
    
    # 构建镜像
    docker-compose build --no-cache
    
    # 启动服务
    docker-compose up -d
    
    log_success "服务启动完成"
}

# 验证部署
verify_deployment() {
    log_info "验证部署结果..."
    
    # 等待服务启动
    sleep 10
    
    # 检查容器状态
    if docker-compose ps | grep -q "Up"; then
        log_success "容器运行正常"
    else
        log_error "容器启动失败"
        docker-compose logs
        exit 1
    fi
    
    # 检查健康状态
    local retries=5
    for i in $(seq 1 $retries); do
        if curl -f http://localhost:8000/health &>/dev/null; then
            log_success "服务健康检查通过"
            break
        else
            if [ $i -eq $retries ]; then
                log_error "服务健康检查失败"
                exit 1
            fi
            log_info "等待服务就绪... ($i/$retries)"
            sleep 5
        fi
    done
}

# 显示部署信息
show_deployment_info() {
    echo "========================================"
    log_success "SSH采集器部署完成！"
    echo "========================================"
    echo "服务地址: http://$(hostname -I | awk '{print $1}'):8000"
    echo "健康检查: http://$(hostname -I | awk '{print $1}'):8000/health"
    echo "========================================"
    echo "常用命令:"
    echo "  查看服务状态: docker-compose ps"
    echo "  查看日志: docker-compose logs -f"
    echo "  重启服务: docker-compose restart"
    echo "  停止服务: docker-compose down"
    echo "========================================"
}

# 主函数
main() {
    log_info "开始部署SSH采集器..."
    
    check_docker
    create_directories
    setup_env
    deploy_service
    verify_deployment
    show_deployment_info
    
    log_success "部署流程完成！"
}

# 执行主函数
main "$@"
EOF

    chmod +x "$deploy_temp/server-deploy.sh"
    
    # 打包
    cd "$temp_dir"
    tar -czf "$package_name" ssh-collector/
    mv "$package_name" "$OLDPWD/"
    
    # 清理临时目录
    rm -rf "$temp_dir"
    
    log_success "部署包创建完成: $package_name"
}

# 上传部署包到服务器
upload_to_server() {
    log_info "上传部署包到服务器..."
    
    local package_name="ssh-collector-deploy.tar.gz"
    
    # 使用scp上传文件
    log_info "正在上传文件到服务器..."
    echo "请输入服务器密码: $SERVER_PASSWORD"
    scp -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$package_name" "$SERVER_USER@$SERVER_IP:~/"
    
    log_success "文件上传完成"
}

# 在服务器上执行部署
deploy_on_server() {
    log_info "在服务器上执行部署..."
    
    echo "请输入服务器密码: $SERVER_PASSWORD"
    ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no "$SERVER_USER@$SERVER_IP" << 'ENDSSH'
        # 解压部署包
        tar -xzf ssh-collector-deploy.tar.gz
        cd ssh-collector
        
        # 执行部署脚本
        chmod +x server-deploy.sh
        ./server-deploy.sh
ENDSSH
    
    log_success "服务器部署完成"
}

# 显示帮助信息
show_help() {
    cat << EOF
SSH采集器服务器部署脚本

用法: $0 [选项]

选项:
    --package-only    只创建部署包，不上传
    --upload-only     只上传文件，不执行部署
    --deploy-only     只执行部署，假设文件已上传
    -h, --help        显示帮助信息

示例:
    $0                # 完整部署流程
    $0 --package-only # 只创建部署包
EOF
}

# 主函数
main() {
    local action="full"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            --package-only)
                action="package"
                shift
                ;;
            --upload-only)
                action="upload"
                shift
                ;;
            --deploy-only)
                action="deploy"
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            *)
                log_error "未知参数: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    log_info "SSH采集器服务器部署开始"
    log_info "目标服务器: $SERVER_IP"
    log_info "用户: $SERVER_USER"
    
    case $action in
        "package")
            check_local_env
            create_deploy_package
            ;;
        "upload")
            upload_to_server
            ;;
        "deploy")
            deploy_on_server
            ;;
        "full")
            check_local_env
            create_deploy_package
            upload_to_server
            deploy_on_server
            ;;
    esac
    
    log_success "操作完成！"
}

# 执行主函数
main "$@"