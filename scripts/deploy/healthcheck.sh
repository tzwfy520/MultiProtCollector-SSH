#!/bin/bash

# SSH采集器健康检查脚本
# 用于Docker容器健康检查

set -e

# 配置
HEALTH_URL="http://localhost:${SERVICE_PORT:-8000}/health"
TIMEOUT=10
MAX_RETRIES=3

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查HTTP服务
check_http_service() {
    local retry=0
    
    while [ $retry -lt $MAX_RETRIES ]; do
        if curl -f -s --connect-timeout $TIMEOUT "$HEALTH_URL" > /dev/null 2>&1; then
            log_info "HTTP服务健康检查通过"
            return 0
        fi
        
        retry=$((retry + 1))
        if [ $retry -lt $MAX_RETRIES ]; then
            log_warn "HTTP服务检查失败，重试 $retry/$MAX_RETRIES"
            sleep 2
        fi
    done
    
    log_error "HTTP服务健康检查失败"
    return 1
}

# 检查进程
check_process() {
    if pgrep -f "python.*main.py" > /dev/null; then
        log_info "采集器进程运行正常"
        return 0
    else
        log_error "采集器进程未运行"
        return 1
    fi
}

# 检查内存使用率
check_memory() {
    local memory_usage
    memory_usage=$(free | grep Mem | awk '{printf "%.1f", $3/$2 * 100.0}')
    
    if (( $(echo "$memory_usage > 90" | bc -l) )); then
        log_warn "内存使用率过高: ${memory_usage}%"
        return 1
    else
        log_info "内存使用率正常: ${memory_usage}%"
        return 0
    fi
}

# 检查磁盘使用率
check_disk() {
    local disk_usage
    disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [ "$disk_usage" -gt 90 ]; then
        log_warn "磁盘使用率过高: ${disk_usage}%"
        return 1
    else
        log_info "磁盘使用率正常: ${disk_usage}%"
        return 0
    fi
}

# 主健康检查函数
main() {
    local exit_code=0
    
    echo "=========================================="
    echo "SSH采集器健康检查开始"
    echo "时间: $(date)"
    echo "=========================================="
    
    # 检查进程
    if ! check_process; then
        exit_code=1
    fi
    
    # 检查HTTP服务
    if ! check_http_service; then
        exit_code=1
    fi
    
    # 检查系统资源
    if ! check_memory; then
        log_warn "内存使用率检查警告"
    fi
    
    if ! check_disk; then
        log_warn "磁盘使用率检查警告"
    fi
    
    echo "=========================================="
    if [ $exit_code -eq 0 ]; then
        log_info "健康检查通过"
    else
        log_error "健康检查失败"
    fi
    echo "=========================================="
    
    exit $exit_code
}

# 执行主函数
main "$@"