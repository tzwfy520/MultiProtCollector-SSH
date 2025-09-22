#!/bin/bash

# SSH采集器镜像测试脚本
# 用于测试和对比不同版本镜像的性能和兼容性

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# 测试配置
TEST_TIMEOUT=30
HEALTH_CHECK_RETRIES=5
HEALTH_CHECK_INTERVAL=2

# 镜像配置
declare -A IMAGES=(
    ["alpine"]="ssh-collector:alpine"
    ["distroless"]="ssh-collector:distroless"
    ["original"]="ssh-collector:original"
)

declare -A PORTS=(
    ["alpine"]="8000"
    ["distroless"]="8001"
    ["original"]="8002"
)

# 检查镜像是否存在
check_image_exists() {
    local image=$1
    if docker images --format "{{.Repository}}:{{.Tag}}" | grep -q "^$image$"; then
        return 0
    else
        return 1
    fi
}

# 启动容器
start_container() {
    local type=$1
    local image=${IMAGES[$type]}
    local port=${PORTS[$type]}
    local container_name="test-$type"
    
    log_info "启动 $type 版本容器..."
    
    # 停止并删除已存在的容器
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true
    
    # 启动新容器
    if docker run -d \
        --name "$container_name" \
        -p "$port:8000" \
        -e APP_NAME="SSH采集器-$type" \
        -e DEBUG=false \
        -e LOG_LEVEL=INFO \
        "$image"; then
        log_success "$type 版本容器启动成功"
        return 0
    else
        log_error "$type 版本容器启动失败"
        return 1
    fi
}

# 等待服务就绪
wait_for_service() {
    local type=$1
    local port=${PORTS[$type]}
    local container_name="test-$type"
    
    log_info "等待 $type 版本服务就绪..."
    
    for i in $(seq 1 $HEALTH_CHECK_RETRIES); do
        if docker exec "$container_name" sh -c "command -v curl >/dev/null 2>&1" 2>/dev/null; then
            # 容器内有curl命令
            if docker exec "$container_name" curl -f http://localhost:8000/health 2>/dev/null; then
                log_success "$type 版本服务就绪"
                return 0
            fi
        else
            # 容器内没有curl，使用外部测试
            if command -v curl >/dev/null 2>&1; then
                if curl -f "http://localhost:$port/health" 2>/dev/null; then
                    log_success "$type 版本服务就绪"
                    return 0
                fi
            else
                # 使用Python测试
                if python3 -c "
import urllib.request
import sys
try:
    urllib.request.urlopen('http://localhost:$port/health', timeout=5)
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
                    log_success "$type 版本服务就绪"
                    return 0
                fi
            fi
        fi
        
        log_info "等待中... ($i/$HEALTH_CHECK_RETRIES)"
        sleep $HEALTH_CHECK_INTERVAL
    done
    
    log_error "$type 版本服务未能就绪"
    return 1
}

# 性能测试
performance_test() {
    local type=$1
    local port=${PORTS[$type]}
    
    log_info "执行 $type 版本性能测试..."
    
    # 测试响应时间
    local start_time=$(date +%s%N)
    if command -v curl >/dev/null 2>&1; then
        curl -s "http://localhost:$port/health" > /dev/null
    else
        python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:$port/health')" 2>/dev/null
    fi
    local end_time=$(date +%s%N)
    local response_time=$(( (end_time - start_time) / 1000000 ))
    
    echo "  响应时间: ${response_time}ms"
    
    # 获取容器资源使用情况
    local stats=$(docker stats "test-$type" --no-stream --format "{{.CPUPerc}}\t{{.MemUsage}}")
    local cpu_usage=$(echo "$stats" | cut -f1)
    local mem_usage=$(echo "$stats" | cut -f2)
    
    echo "  CPU使用率: $cpu_usage"
    echo "  内存使用: $mem_usage"
}

# 获取镜像大小
get_image_size() {
    local type=$1
    local image=${IMAGES[$type]}
    
    local size=$(docker images "$image" --format "{{.Size}}")
    echo "  镜像大小: $size"
}

# 功能测试
functional_test() {
    local type=$1
    local port=${PORTS[$type]}
    
    log_info "执行 $type 版本功能测试..."
    
    # 测试健康检查端点
    if command -v curl >/dev/null 2>&1; then
        local health_response=$(curl -s "http://localhost:$port/health")
    else
        local health_response=$(python3 -c "
import urllib.request
import json
response = urllib.request.urlopen('http://localhost:$port/health')
print(response.read().decode())
" 2>/dev/null)
    fi
    
    if echo "$health_response" | grep -q "status"; then
        log_success "$type 版本健康检查通过"
    else
        log_error "$type 版本健康检查失败"
        return 1
    fi
    
    # 测试其他端点（如果存在）
    # 这里可以添加更多的功能测试
    
    return 0
}

# 停止容器
stop_container() {
    local type=$1
    local container_name="test-$type"
    
    log_info "停止 $type 版本容器..."
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true
}

# 测试单个镜像
test_single_image() {
    local type=$1
    local image=${IMAGES[$type]}
    
    echo "========================================"
    log_info "测试 $type 版本镜像"
    echo "========================================"
    
    # 检查镜像是否存在
    if ! check_image_exists "$image"; then
        log_error "镜像 $image 不存在，跳过测试"
        return 1
    fi
    
    # 显示镜像信息
    get_image_size "$type"
    
    # 启动容器
    if ! start_container "$type"; then
        return 1
    fi
    
    # 等待服务就绪
    if ! wait_for_service "$type"; then
        stop_container "$type"
        return 1
    fi
    
    # 执行功能测试
    if ! functional_test "$type"; then
        stop_container "$type"
        return 1
    fi
    
    # 执行性能测试
    performance_test "$type"
    
    # 停止容器
    stop_container "$type"
    
    log_success "$type 版本测试完成"
    return 0
}

# 对比测试结果
compare_results() {
    log_info "镜像大小对比:"
    echo "----------------------------------------"
    for type in "${!IMAGES[@]}"; do
        local image=${IMAGES[$type]}
        if check_image_exists "$image"; then
            local size=$(docker images "$image" --format "{{.Size}}")
            printf "%-12s %s\n" "$type:" "$size"
        fi
    done
    echo "----------------------------------------"
}

# 清理测试环境
cleanup() {
    log_info "清理测试环境..."
    for type in "${!IMAGES[@]}"; do
        stop_container "$type"
    done
    log_success "清理完成"
}

# 主函数
main() {
    local test_type="${1:-all}"
    
    log_info "SSH采集器镜像测试开始"
    
    # 设置清理陷阱
    trap cleanup EXIT
    
    case "$test_type" in
        "all")
            local failed=0
            for type in "${!IMAGES[@]}"; do
                if ! test_single_image "$type"; then
                    failed=$((failed + 1))
                fi
                echo
            done
            
            compare_results
            
            if [ $failed -eq 0 ]; then
                log_success "所有镜像测试通过"
            else
                log_error "$failed 个镜像测试失败"
                exit 1
            fi
            ;;
        *)
            if [[ -n "${IMAGES[$test_type]}" ]]; then
                test_single_image "$test_type"
            else
                log_error "不支持的测试类型: $test_type"
                echo "支持的类型: ${!IMAGES[*]}"
                exit 1
            fi
            ;;
    esac
    
    log_success "测试流程完成"
}

# 显示帮助信息
show_help() {
    cat << EOF
SSH采集器镜像测试脚本

用法: $0 [类型]

参数:
    类型    测试的镜像类型 (alpine|distroless|original|all)
            默认为 all

示例:
    $0              # 测试所有镜像
    $0 alpine       # 只测试Alpine版本
    $0 distroless   # 只测试Distroless版本
EOF
}

# 检查参数
if [[ "$1" == "-h" || "$1" == "--help" ]]; then
    show_help
    exit 0
fi

# 执行主函数
main "$@"