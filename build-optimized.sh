#!/bin/bash

# SSH采集器优化构建脚本
# 支持多种构建策略和缓存优化

set -e

# 颜色定义
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

# 显示帮助信息
show_help() {
    cat << EOF
SSH采集器优化构建脚本

用法: $0 [选项]

选项:
    -t, --type TYPE         构建类型 (alpine|distroless|original|all)
    -c, --cache             启用Docker构建缓存
    -p, --push              构建后推送到镜像仓库
    -r, --registry URL      镜像仓库地址
    --no-cache              禁用Docker缓存
    --parallel              并行构建多个镜像
    --test                  构建后运行测试
    -h, --help              显示此帮助信息

示例:
    $0 -t alpine -c                    # 构建Alpine版本并启用缓存
    $0 -t all --parallel               # 并行构建所有版本
    $0 -t distroless -p -r my-registry # 构建Distroless版本并推送
EOF
}

# 默认参数
BUILD_TYPE="alpine"
USE_CACHE=false
PUSH_IMAGE=false
REGISTRY=""
PARALLEL=false
RUN_TEST=false
DOCKER_BUILDKIT=1

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        -t|--type)
            BUILD_TYPE="$2"
            shift 2
            ;;
        -c|--cache)
            USE_CACHE=true
            shift
            ;;
        -p|--push)
            PUSH_IMAGE=true
            shift
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        --no-cache)
            USE_CACHE=false
            shift
            ;;
        --parallel)
            PARALLEL=true
            shift
            ;;
        --test)
            RUN_TEST=true
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

# 检查Docker是否可用
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装或不可用"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker守护进程未运行"
        exit 1
    fi
}

# 启用BuildKit
enable_buildkit() {
    export DOCKER_BUILDKIT=1
    export COMPOSE_DOCKER_CLI_BUILD=1
    log_info "已启用Docker BuildKit"
}

# 构建单个镜像
build_image() {
    local type=$1
    local dockerfile=""
    local tag=""
    local cache_args=""
    
    case $type in
        "alpine")
            dockerfile="Dockerfile.multi-stage"
            tag="ssh-collector:alpine"
            ;;
        "distroless")
            dockerfile="Dockerfile.distroless"
            tag="ssh-collector:distroless"
            ;;
        "original")
            dockerfile="Dockerfile"
            tag="ssh-collector:original"
            ;;
        *)
            log_error "不支持的构建类型: $type"
            return 1
            ;;
    esac
    
    # 设置缓存参数
    if [ "$USE_CACHE" = true ]; then
        cache_args="--cache-from $tag"
    else
        cache_args="--no-cache"
    fi
    
    # 添加注册表前缀
    if [ -n "$REGISTRY" ]; then
        tag="$REGISTRY/$tag"
    fi
    
    log_info "开始构建 $type 版本镜像..."
    log_info "Dockerfile: $dockerfile"
    log_info "标签: $tag"
    
    # 构建镜像
    if docker build \
        -f "$dockerfile" \
        -t "$tag" \
        $cache_args \
        --build-arg BUILDKIT_INLINE_CACHE=1 \
        .; then
        log_success "$type 版本构建完成"
        
        # 显示镜像信息
        docker images "$tag" --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        
        # 推送镜像
        if [ "$PUSH_IMAGE" = true ]; then
            log_info "推送镜像到仓库..."
            docker push "$tag"
            log_success "镜像推送完成"
        fi
        
        return 0
    else
        log_error "$type 版本构建失败"
        return 1
    fi
}

# 并行构建
build_parallel() {
    local types=("alpine" "distroless" "original")
    local pids=()
    
    log_info "开始并行构建..."
    
    for type in "${types[@]}"; do
        build_image "$type" &
        pids+=($!)
    done
    
    # 等待所有构建完成
    local failed=0
    for pid in "${pids[@]}"; do
        if ! wait "$pid"; then
            failed=$((failed + 1))
        fi
    done
    
    if [ $failed -eq 0 ]; then
        log_success "所有镜像构建完成"
    else
        log_error "$failed 个镜像构建失败"
        return 1
    fi
}

# 运行测试
run_tests() {
    log_info "运行镜像测试..."
    
    # 测试Alpine版本
    if docker run --rm -d --name test-alpine -p 8000:8000 ssh-collector:alpine; then
        sleep 10
        if curl -f http://localhost:8000/health &> /dev/null; then
            log_success "Alpine版本测试通过"
        else
            log_error "Alpine版本测试失败"
        fi
        docker stop test-alpine
    fi
    
    # 测试Distroless版本
    if docker run --rm -d --name test-distroless -p 8001:8000 ssh-collector:distroless; then
        sleep 10
        if curl -f http://localhost:8001/health &> /dev/null; then
            log_success "Distroless版本测试通过"
        else
            log_error "Distroless版本测试失败"
        fi
        docker stop test-distroless
    fi
}

# 清理构建缓存
cleanup_cache() {
    log_info "清理Docker构建缓存..."
    docker builder prune -f
    log_success "缓存清理完成"
}

# 显示镜像大小对比
show_size_comparison() {
    log_info "镜像大小对比:"
    echo "----------------------------------------"
    docker images ssh-collector --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"
    echo "----------------------------------------"
}

# 主函数
main() {
    log_info "SSH采集器优化构建开始"
    log_info "构建类型: $BUILD_TYPE"
    log_info "使用缓存: $USE_CACHE"
    log_info "并行构建: $PARALLEL"
    
    # 检查环境
    check_docker
    enable_buildkit
    
    # 执行构建
    case $BUILD_TYPE in
        "all")
            if [ "$PARALLEL" = true ]; then
                build_parallel
            else
                build_image "alpine"
                build_image "distroless"
                build_image "original"
            fi
            ;;
        *)
            build_image "$BUILD_TYPE"
            ;;
    esac
    
    # 运行测试
    if [ "$RUN_TEST" = true ]; then
        run_tests
    fi
    
    # 显示结果
    show_size_comparison
    
    log_success "构建流程完成"
}

# 执行主函数
main "$@"