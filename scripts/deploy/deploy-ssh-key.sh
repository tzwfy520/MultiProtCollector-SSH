#!/bin/bash

# SSH采集器自动部署脚本 - 使用SSH密钥认证
# 避免使用sshpass，更安全的部署方式

set -e

# 配置变量
SERVER_IP="115.190.80.219"
USERNAME="eccom123"
PASSWORD="Eccom@12345"
DEPLOY_DIR="/opt/ssh-collector"
PROJECT_NAME="ssh-collector"
SSH_KEY_PATH="$HOME/.ssh/id_rsa"

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

# 生成SSH密钥对
generate_ssh_key() {
    log_info "检查SSH密钥..."
    
    if [[ ! -f "$SSH_KEY_PATH" ]]; then
        log_info "生成SSH密钥对..."
        ssh-keygen -t rsa -b 4096 -f "$SSH_KEY_PATH" -N "" -C "deploy@$(hostname)"
        log_success "SSH密钥生成完成"
    else
        log_success "SSH密钥已存在"
    fi
}

# 使用expect脚本复制SSH密钥到服务器
copy_ssh_key() {
    log_info "复制SSH密钥到服务器..."
    
    # 检查expect是否安装
    if ! command -v expect &> /dev/null; then
        log_warning "expect未安装，正在安装..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install expect
            else
                log_error "请先安装Homebrew或手动安装expect"
                exit 1
            fi
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            # Linux
            if command -v apt-get &> /dev/null; then
                sudo apt-get update && sudo apt-get install -y expect
            elif command -v yum &> /dev/null; then
                sudo yum install -y expect
            else
                log_error "无法自动安装expect，请手动安装"
                exit 1
            fi
        fi
    fi
    
    # 创建expect脚本
    cat > /tmp/ssh-copy-id.exp << EOF
#!/usr/bin/expect -f
set timeout 30
spawn ssh-copy-id -i $SSH_KEY_PATH.pub $USERNAME@$SERVER_IP
expect {
    "yes/no" { send "yes\r"; exp_continue }
    "password:" { send "$PASSWORD\r" }
}
expect eof
EOF
    
    chmod +x /tmp/ssh-copy-id.exp
    
    # 执行expect脚本
    if /tmp/ssh-copy-id.exp; then
        log_success "SSH密钥复制成功"
    else
        log_error "SSH密钥复制失败"
        exit 1
    fi
    
    # 清理临时文件
    rm -f /tmp/ssh-copy-id.exp
}

# SSH执行命令函数（使用密钥认证）
ssh_exec() {
    local cmd="$1"
    local show_output="${2:-true}"
    
    if [[ "$show_output" == "true" ]]; then
        ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$SSH_KEY_PATH" "$USERNAME@$SERVER_IP" "$cmd"
    else
        ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 -i "$SSH_KEY_PATH" "$USERNAME@$SERVER_IP" "$cmd" >/dev/null 2>&1
    fi
}

# 测试SSH连接
test_ssh_connection() {
    log_info "测试SSH密钥连接到 $SERVER_IP..."
    
    if ssh_exec "echo 'SSH密钥连接成功'" false; then
        log_success "SSH密钥连接测试成功"
    else
        log_error "SSH密钥连接失败，请检查密钥配置"
        exit 1
    fi
}

# 检查服务器环境
check_server_environment() {
    log_info "检查服务器环境..."
    
    # 检查操作系统
    OS_INFO=$(ssh_exec "cat /etc/os-release | grep PRETTY_NAME" false)
    log_info "服务器操作系统: $OS_INFO"
    
    # 检查sudo权限
    if ssh_exec "sudo -n true" false; then
        log_success "sudo权限验证成功"
    else
        log_warning "需要sudo密码，将在需要时提示"
    fi
    
    # 检查Docker
    if ssh_exec "command -v docker" false; then
        log_success "Docker已安装"
    else
        log_warning "Docker未安装，将自动安装"
        install_docker
    fi
    
    # 检查Docker Compose
    if ssh_exec "command -v docker-compose" false; then
        log_success "Docker Compose已安装"
    else
        log_warning "Docker Compose未安装，将自动安装"
        install_docker_compose
    fi
}

# 安装Docker
install_docker() {
    log_info "在服务器上安装Docker..."
    
    ssh_exec "
        # 更新包管理器
        sudo apt-get update
        
        # 安装必要的包
        sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release
        
        # 添加Docker官方GPG密钥
        curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
        
        # 添加Docker仓库
        echo \"deb [arch=\$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
        
        # 安装Docker
        sudo apt-get update
        sudo apt-get install -y docker-ce docker-ce-cli containerd.io
        
        # 启动Docker服务
        sudo systemctl start docker
        sudo systemctl enable docker
        
        # 将用户添加到docker组
        sudo usermod -aG docker $USER
    "
    
    log_success "Docker安装完成"
}

# 安装Docker Compose
install_docker_compose() {
    log_info "在服务器上安装Docker Compose..."
    
    ssh_exec "
        # 下载Docker Compose
        sudo curl -L \"https://github.com/docker/compose/releases/latest/download/docker-compose-\$(uname -s)-\$(uname -m)\" -o /usr/local/bin/docker-compose
        
        # 设置执行权限
        sudo chmod +x /usr/local/bin/docker-compose
        
        # 创建软链接
        sudo ln -sf /usr/local/bin/docker-compose /usr/bin/docker-compose
    "
    
    log_success "Docker Compose安装完成"
}

# 创建部署目录
create_deploy_directory() {
    log_info "创建部署目录 $DEPLOY_DIR..."
    
    ssh_exec "
        # 创建部署目录
        sudo mkdir -p $DEPLOY_DIR
        sudo chown $USERNAME:$USERNAME $DEPLOY_DIR
        
        # 创建子目录
        mkdir -p $DEPLOY_DIR/{data,logs,nginx}
    "
    
    log_success "部署目录创建完成"
}

# 上传项目文件
upload_project_files() {
    log_info "上传项目文件到服务器..."
    
    # 创建临时目录用于准备文件
    TEMP_DIR=$(mktemp -d)
    
    # 复制项目文件到临时目录
    cp -r src/ "$TEMP_DIR/"
    cp requirements.txt "$TEMP_DIR/"
    cp healthcheck.sh "$TEMP_DIR/"
    
    # 检查nginx配置文件是否存在
    if [[ -f "nginx/nginx.conf" ]]; then
        cp nginx/nginx.conf "$TEMP_DIR/"
    fi
    
    # 复制Alpine版本的Dockerfile
    cp Dockerfile.alpine "$TEMP_DIR/Dockerfile"
    
    # 复制docker-compose文件
    cp docker-compose.alpine.yml "$TEMP_DIR/docker-compose.yml"
    
    # 使用rsync上传文件
    rsync -avz --delete -e "ssh -o StrictHostKeyChecking=no -i $SSH_KEY_PATH" \
        "$TEMP_DIR/" "$USERNAME@$SERVER_IP:$DEPLOY_DIR/"
    
    # 清理临时目录
    rm -rf "$TEMP_DIR"
    
    log_success "项目文件上传完成"
}

# 构建和启动服务
build_and_start_service() {
    log_info "构建Docker镜像并启动服务..."
    
    ssh_exec "
        cd $DEPLOY_DIR
        
        # 停止现有服务
        docker-compose down || true
        
        # 构建镜像
        docker-compose build --no-cache
        
        # 启动服务
        docker-compose up -d
        
        # 等待服务启动
        sleep 10
    "
    
    log_success "服务启动完成"
}

# 验证部署
verify_deployment() {
    log_info "验证部署结果..."
    
    # 检查容器状态
    log_info "容器状态:"
    ssh_exec "cd $DEPLOY_DIR && docker-compose ps"
    
    # 检查服务健康状态
    if ssh_exec "cd $DEPLOY_DIR && docker-compose exec -T ssh-collector curl -f http://localhost:8000/health" false; then
        log_success "服务健康检查通过"
    else
        log_warning "服务健康检查失败，检查日志..."
        ssh_exec "cd $DEPLOY_DIR && docker-compose logs --tail=20 ssh-collector"
    fi
    
    # 检查端口监听
    if ssh_exec "ss -tlnp | grep :8000" false; then
        log_success "端口8000正在监听"
    else
        log_error "端口8000未在监听"
    fi
    
    # 显示访问信息
    log_success "部署完成！"
    log_info "访问地址: http://$SERVER_IP:8000"
    log_info "健康检查: http://$SERVER_IP:8000/health"
    log_info "API文档: http://$SERVER_IP:8000/docs"
}

# 显示日志
show_logs() {
    log_info "显示服务日志..."
    ssh_exec "cd $DEPLOY_DIR && docker-compose logs --tail=50 ssh-collector"
}

# 主函数
main() {
    log_info "开始SSH采集器自动部署（使用SSH密钥认证）..."
    log_info "目标服务器: $SERVER_IP"
    log_info "部署目录: $DEPLOY_DIR"
    
    # 执行部署步骤
    generate_ssh_key
    copy_ssh_key
    test_ssh_connection
    check_server_environment
    create_deploy_directory
    upload_project_files
    build_and_start_service
    verify_deployment
    
    log_success "部署完成！"
    
    # 询问是否查看日志
    read -p "是否查看服务日志？(y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        show_logs
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi