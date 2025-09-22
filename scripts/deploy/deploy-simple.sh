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
    
    # 创建部署包
    DEPLOY_PACKAGE="ssh-collector-deploy.tar.gz"
    
    # 创建临时目录
    TEMP_DIR=$(mktemp -d)
    PACKAGE_DIR="$TEMP_DIR/ssh-collector"
    mkdir -p "$PACKAGE_DIR"
    
    # 复制必要文件
    cp -r src/ "$PACKAGE_DIR/"
    cp requirements.txt "$PACKAGE_DIR/"
    cp healthcheck.sh "$PACKAGE_DIR/"
    cp Dockerfile.alpine "$PACKAGE_DIR/Dockerfile"
    cp docker-compose.alpine.yml "$PACKAGE_DIR/docker-compose.yml"
    
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
    
    # 停止现有服务
    docker-compose down || true
    
    # 构建并启动服务
    docker-compose build --no-cache
    docker-compose up -d
    
    # 等待服务启动
    sleep 15
    
    log_success "应用部署完成"
}

# 验证部署
verify_deployment() {
    log_info "验证部署..."
    
    cd $DEPLOY_DIR
    
    # 检查容器状态
    docker-compose ps
    
    # 检查健康状态
    if docker-compose exec -T ssh-collector curl -f http://localhost:8000/health; then
        log_success "健康检查通过"
    else
        log_warning "健康检查失败，查看日志:"
        docker-compose logs --tail=20 ssh-collector
    fi
    
    log_success "验证完成"
}

main() {
    log_info "开始远程部署..."
    check_docker
    create_directories
    deploy_app
    verify_deployment
    log_success "部署完成！访问地址: http://$(hostname -I | awk '{print $1}'):8000"
}

main "$@"
EOF
    
    chmod +x "$PACKAGE_DIR/remote-deploy.sh"
    
    # 打包
    cd "$TEMP_DIR"
    tar -czf "$DEPLOY_PACKAGE" ssh-collector/
    mv "$DEPLOY_PACKAGE" "/Users/wangfuyu/PythonCode/SSHCollector/"
    
    # 清理
    rm -rf "$TEMP_DIR"
    
    log_success "部署包创建完成: $DEPLOY_PACKAGE"
}

# 上传并执行部署
upload_and_deploy() {
    log_info "上传部署包到服务器..."
    log_warning "请输入SSH密码: Eccom@12345"
    
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
        echo '=== 端口监听 ==='
        ss -tlnp | grep :8000 || echo '端口8000未监听'
        echo
        echo '=== 服务测试 ==='
        curl -s http://localhost:8000/health || echo '健康检查失败'
    "
    
    log_success "部署验证完成！"
    log_info "访问地址: http://$SERVER_IP:8000"
    log_info "API文档: http://$SERVER_IP:8000/docs"
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