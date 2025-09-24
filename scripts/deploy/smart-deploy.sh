#!/bin/bash

# SSH Collector 智能化部署脚本
# 功能：自动检测可用端口并部署容器
# 作者：AI Assistant
# 版本：1.0

set -e

# 配置变量
DEFAULT_PORT=8000
CONTAINER_NAME="ssh-collector"
IMAGE_ID="cc12b8437b73"
MAX_PORT_SCAN=8100

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

# 检查端口是否被占用
check_port_available() {
    local port=$1
    if netstat -tuln | grep -q ":${port} "; then
        return 1  # 端口被占用
    else
        return 0  # 端口可用
    fi
}

# 查找可用端口
find_available_port() {
    local start_port=$DEFAULT_PORT
    local current_port=$start_port
    
    log_info "开始检测可用端口，从 $start_port 开始..." >&2
    
    while [ $current_port -le $MAX_PORT_SCAN ]; do
        if check_port_available $current_port; then
            log_success "找到可用端口: $current_port" >&2
            echo $current_port
            return 0
        else
            log_warning "端口 $current_port 已被占用，尝试下一个端口..." >&2
            current_port=$((current_port + 1))
        fi
    done
    
    log_error "在范围 $start_port-$MAX_PORT_SCAN 内未找到可用端口" >&2
    return 1
}

# 停止并删除现有容器
cleanup_existing_container() {
    log_info "清理现有容器..."
    
    if docker ps -a --format "table {{.Names}}" | grep -q "^${CONTAINER_NAME}$"; then
        log_info "停止现有容器: $CONTAINER_NAME"
        docker stop $CONTAINER_NAME 2>/dev/null || true
        
        log_info "删除现有容器: $CONTAINER_NAME"
        docker rm $CONTAINER_NAME 2>/dev/null || true
        
        log_success "现有容器已清理完成"
    else
        log_info "未发现现有容器，跳过清理步骤"
    fi
}

# 启动新容器
start_container() {
    local host_port=$1
    
    log_info "使用镜像 $IMAGE_ID 启动新容器..."
    log_info "端口映射: $host_port:8000"
    
    docker run -d \
        --name $CONTAINER_NAME \
        -p $host_port:8000 \
        --restart unless-stopped \
        $IMAGE_ID
    
    if [ $? -eq 0 ]; then
        log_success "容器启动成功！"
        log_success "容器名称: $CONTAINER_NAME"
        log_success "访问地址: http://localhost:$host_port"
        return 0
    else
        log_error "容器启动失败"
        return 1
    fi
}

# 验证容器状态
verify_container() {
    local host_port=$1
    
    log_info "验证容器状态..."
    
    # 等待容器启动
    sleep 3
    
    # 检查容器是否运行
    if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "^${CONTAINER_NAME}.*Up"; then
        log_success "容器运行状态正常"
        
        # 检查端口监听
        if netstat -tuln | grep -q ":${host_port} "; then
            log_success "端口 $host_port 监听正常"
            return 0
        else
            log_warning "端口 $host_port 未检测到监听，容器可能需要更多时间启动"
            return 0
        fi
    else
        log_error "容器未正常运行"
        docker logs $CONTAINER_NAME 2>/dev/null || true
        return 1
    fi
}

# 显示部署信息
show_deployment_info() {
    local host_port=$1
    
    echo ""
    echo "=========================================="
    echo -e "${GREEN}SSH Collector 部署完成${NC}"
    echo "=========================================="
    echo "容器名称: $CONTAINER_NAME"
    echo "镜像ID: $IMAGE_ID"
    echo "主机端口: $host_port"
    echo "容器端口: 8000"
    echo "访问地址: http://localhost:$host_port"
    echo "=========================================="
    echo ""
    
    # 显示容器状态
    log_info "当前容器状态:"
    docker ps --filter "name=$CONTAINER_NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

# 主函数
main() {
    echo ""
    echo "=========================================="
    echo -e "${BLUE}SSH Collector 智能化部署脚本${NC}"
    echo "=========================================="
    echo ""
    
    # 检查Docker是否运行
    if ! docker info >/dev/null 2>&1; then
        log_error "Docker 未运行或无法访问，请检查Docker服务状态"
        exit 1
    fi
    
    # 检查镜像是否存在
    if ! docker images --format "table {{.ID}}" | grep -q "^${IMAGE_ID}"; then
        log_error "镜像 $IMAGE_ID 不存在，请先构建镜像"
        exit 1
    fi
    
    # 查找可用端口
    AVAILABLE_PORT=$(find_available_port)
    if [ $? -ne 0 ]; then
        log_error "无法找到可用端口，部署失败"
        exit 1
    fi
    
    # 清理现有容器
    cleanup_existing_container
    
    # 启动新容器
    if start_container $AVAILABLE_PORT; then
        # 验证容器状态
        verify_container $AVAILABLE_PORT
        
        # 显示部署信息
        show_deployment_info $AVAILABLE_PORT
        
        log_success "SSH Collector 智能化部署完成！"
        exit 0
    else
        log_error "部署失败，请检查错误信息"
        exit 1
    fi
}

# 脚本入口
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi