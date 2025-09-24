#!/bin/bash

# SSH采集器简化部署脚本
# 使用原生SSH，手动输入密码

set -e

# 配置变量
SERVER_IP="115.190.80.219"
USERNAME="eccom123"
DEPLOY_DIR="/opt/ssh-collector"
PROJECT_NAME="ssh-collector"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# SSH执行命令函数
ssh_exec() {
    local cmd="$1"
    ssh -o StrictHostKeyChecking=no "$USERNAME@$SERVER_IP" "$cmd"
}

# 测试SSH连接
test_ssh_connection() {
    log_info "测试SSH连接到 $SERVER_IP..."
    log_warning "请输入SSH密码: Eccom@12345"
    
    if ssh_exec "echo 'SSH连接成功'"; then
        log_success "SSH连接测试成功"
    else
        log_error "SSH连接失败"
        exit 1
    fi
}

# 准备部署文件
prepare_deployment_files() {
    log_info "准备部署文件..."
    
    # 切换到项目根目录
    cd "$(dirname "$0")/../.."
    
    # 创建部署包
    DEPLOY_PACKAGE="ssh-collector-deploy.tar.gz"
    
    # 创建临时目录
    TEMP_DIR=$(mktemp -d)
    PACKAGE_DIR="$TEMP_DIR/ssh-collector"
    mkdir -p "$PACKAGE_DIR"
    
    # 复制必要文件
    cp -r src/ "$PACKAGE_DIR/"
    cp requirements.txt "$PACKAGE_DIR/"
    cp scripts/deploy/healthcheck.sh "$PACKAGE_DIR/"
    cp scripts/deploy/Dockerfile.alpine "$PACKAGE_DIR/Dockerfile"
    cp scripts/deploy/docker-compose.alpine.yml "$PACKAGE_DIR/docker-compose.yml"
    
    # 检查nginx配置文件
    if [[ -f "nginx/nginx.conf" ]]; then
        mkdir -p "$PACKAGE_DIR/nginx"
        cp nginx/nginx.conf "$PACKAGE_DIR/nginx/"
    fi
    
    # 创建部署脚本
    cat > "$PACKAGE_DIR/remote-deploy.sh" << 'EOF'
#!/bin/bash

set -e

DEPLOY_DIR="/opt/ssh-collector"
USERNAME="eccom123"
CONTAINER_PORT=8000
DEFAULT_HOST_PORT=8000

# 颜色输出
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

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查端口是否被占用
check_port_available() {
    local port=$1
    if ss -tlnp | grep -q ":${port} "; then
        return 1  # 端口被占用
    else
        return 0  # 端口可用
    fi
}

# 查找可用端口
find_available_port() {
    local start_port=$1
    local max_attempts=100
    local current_port=$start_port
    
    echo "[INFO] 检查端口可用性，起始端口: $start_port" >&2
    
    for ((i=0; i<max_attempts; i++)); do
        if check_port_available $current_port; then
            echo "[SUCCESS] 找到可用端口: $current_port" >&2
            echo $current_port
            return 0
        else
            echo "[WARNING] 端口 $current_port 已被占用，尝试下一个端口" >&2
            current_port=$((current_port + 1))
        fi
    done
    
    echo "[ERROR] 无法找到可用端口（尝试了 $max_attempts 个端口）" >&2
    return 1
}

# 更新docker-compose.yml文件中的端口映射
update_port_mapping() {
    local host_port=$1
    local compose_file="docker-compose.yml"
    
    echo "[INFO] 更新端口映射: $host_port:$CONTAINER_PORT"
    
    # 备份原文件
    cp "$compose_file" "${compose_file}.backup"
    
    # 使用sed替换端口映射，确保格式正确
    sed -i "s/- \"[^\"]*:8000\"/- \"${host_port}:8000\"/" "$compose_file"
    
    echo "[SUCCESS] 端口映射已更新"
}

# 更新docker-compose.yml文件中的端口映射
update_port_mapping() {
    local host_port=$1
    local compose_file="docker-compose.yml"
    
    echo "[INFO] 更新端口映射: $host_port:$CONTAINER_PORT"
    
    # 备份原文件
    cp "$compose_file" "${compose_file}.backup"
    
    # 使用sed替换端口映射，匹配任何非引号字符
    sed -i "s/- \"[^\"]*:8000\"/- \"${host_port}:8000\"/" "$compose_file"
    
    echo "[SUCCESS] 端口映射已更新"
}

# 检查Docker
check_docker() {
    log_info "检查Docker环境..."
    
    if ! command -v docker &> /dev/null; then
        log_info "安装Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh
        sudo sh get-docker.sh
        sudo systemctl start docker
        sudo systemctl enable docker
        sudo usermod -aG docker $USER
        rm get-docker.sh
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        log_info "安装Docker Compose..."
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
        sudo chmod +x /usr/local/bin/docker-compose
        sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    fi
    
    log_success "Docker环境检查完成"
}

# 创建部署目录
create_directories() {
    log_info "创建部署目录..."
    mkdir -p data logs
    log_success "目录创建完成"
}

# 部署应用
deploy_app() {
    log_info "部署应用..."
    
    cd $DEPLOY_DIR
    
    # 查找可用端口
    AVAILABLE_PORT=$(find_available_port $DEFAULT_HOST_PORT)
    if [ $? -ne 0 ]; then
        log_error "无法找到可用端口，部署失败"
        exit 1
    fi
    
    # 更新端口映射
    update_port_mapping $AVAILABLE_PORT
    
    # 停止现有服务
    docker-compose down || true
    
    # 构建并启动服务
    docker-compose build --no-cache
    docker-compose up -d
    
    # 等待服务启动
    sleep 15
    
    # 保存端口信息到文件
    echo "HOST_PORT=$AVAILABLE_PORT" > .env.port
    echo "CONTAINER_PORT=$CONTAINER_PORT" >> .env.port
    
    log_success "应用部署完成，外部访问端口: $AVAILABLE_PORT"
}

# 验证部署
verify_deployment() {
    log_info "验证部署..."
    
    cd $DEPLOY_DIR
    
    # 读取端口信息
    if [ -f ".env.port" ]; then
        source .env.port
        log_info "使用端口: $HOST_PORT"
    else
        HOST_PORT=$DEFAULT_HOST_PORT
        log_warning "端口信息文件不存在，使用默认端口: $HOST_PORT"
    fi
    
    # 检查容器状态
    docker-compose ps
    
    # 检查健康状态
    if docker-compose exec -T ssh-collector curl -f http://localhost:8000/health; then
        log_success "健康检查通过"
    else
        log_warning "健康检查失败，查看日志:"
        docker-compose logs --tail=20 ssh-collector
    fi
    
    # 检查外部端口访问
    log_info "检查外部端口访问..."
    if curl -f -m 10 http://localhost:$HOST_PORT/health 2>/dev/null; then
        log_success "外部端口访问正常"
    else
        log_warning "外部端口访问失败，请检查防火墙设置"
    fi
    
    log_success "验证完成"
}

main() {
    log_info "开始远程部署..."
    check_docker
    create_directories
    deploy_app
    verify_deployment
    
    # 读取最终端口信息
    if [ -f ".env.port" ]; then
        source .env.port
        FINAL_PORT=$HOST_PORT
    else
        FINAL_PORT=$DEFAULT_HOST_PORT
    fi
    
    log_success "部署完成！访问地址: http://$(hostname -I | awk '{print $1}'):$FINAL_PORT"
    log_info "API文档地址: http://$(hostname -I | awk '{print $1}'):$FINAL_PORT/docs"
    log_info "健康检查地址: http://$(hostname -I | awk '{print $1}'):$FINAL_PORT/health"
}

main "$@"
EOF
    
    chmod +x "$PACKAGE_DIR/remote-deploy.sh"
    
    # 打包
    cd "$TEMP_DIR"
    tar -czf "$DEPLOY_PACKAGE" ssh-collector/
    
    # 移动到项目根目录
    PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
    cp "$DEPLOY_PACKAGE" "$PROJECT_ROOT/"
    
    # 清理
    rm -rf "$TEMP_DIR"
    
    log_success "部署包创建完成: $DEPLOY_PACKAGE"
}

# 上传并执行部署
upload_and_deploy() {
    log_info "上传部署包到服务器..."
    log_warning "请输入SSH密码: Eccom@12345"
    
    # 切换到项目根目录确保能找到部署包
    cd "$(dirname "$0")/../.."
    
    # 上传部署包
    scp -o StrictHostKeyChecking=no ssh-collector-deploy.tar.gz "$USERNAME@$SERVER_IP:/tmp/"
    
    log_info "在服务器上执行部署..."
    log_warning "请输入SSH密码: Eccom@12345"
    
    ssh_exec "
        cd /tmp
        tar -xzf ssh-collector-deploy.tar.gz
        cd ssh-collector
        cp -r * $DEPLOY_DIR/
        cd $DEPLOY_DIR
        chmod +x remote-deploy.sh
        ./remote-deploy.sh
    "
}

# 验证最终结果
final_verification() {
    log_info "最终验证..."
    log_warning "请输入SSH密码: Eccom@12345"
    
    ssh_exec "
        cd $DEPLOY_DIR
        echo '=== 容器状态 ==='
        docker-compose ps
        echo
        
        # 读取端口信息
        if [ -f '.env.port' ]; then
            source .env.port
            FINAL_PORT=\$HOST_PORT
        else
            FINAL_PORT=8000
        fi
        
        echo '=== 端口信息 ==='
        echo \"容器内部端口: 8000\"
        echo \"服务器外部端口: \$FINAL_PORT\"
        echo
        
        echo '=== 端口监听状态 ==='
        ss -tlnp | grep \":\$FINAL_PORT \" || echo \"端口 \$FINAL_PORT 未监听\"
        echo
        
        echo '=== 服务健康检查 ==='
        curl -s http://localhost:8000/health || echo '容器内部健康检查失败'
        echo
        curl -s http://localhost:\$FINAL_PORT/health || echo '外部端口健康检查失败'
    "
    
    # 获取服务器IP和端口信息
    FINAL_PORT=$(ssh_exec "cd $DEPLOY_DIR && [ -f '.env.port' ] && source .env.port && echo \$HOST_PORT || echo 8000")
    
    log_success "部署验证完成！"
    log_info "访问地址: http://$SERVER_IP:$FINAL_PORT"
    log_info "API文档: http://$SERVER_IP:$FINAL_PORT/docs"
    log_info "健康检查: http://$SERVER_IP:$FINAL_PORT/health"
}

# 主函数
main() {
    log_info "开始SSH采集器简化部署..."
    log_info "目标服务器: $SERVER_IP"
    log_info "部署目录: $DEPLOY_DIR"
    log_warning "此脚本需要手动输入SSH密码3次"
    
    read -p "按Enter继续，或Ctrl+C取消..."
    
    test_ssh_connection
    prepare_deployment_files
    upload_and_deploy
    final_verification
    
    # 清理本地文件
    rm -f ssh-collector-deploy.tar.gz
    
    log_success "部署完成！"
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi