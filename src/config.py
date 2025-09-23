"""
配置管理模块
通过环境变量加载配置信息
"""
from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    """应用配置类"""
    
    # 基础配置
    app_name: str = "SSH Collector"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    service_port: int = 8000  # 添加service_port配置
    
    # 采集器配置
    collector_id: Optional[str] = None
    collector_name: str = "ssh-collector"
    
    # 控制器配置
    controller_host: str = "localhost"
    controller_port: int = 9000
    controller_register_url: str = "/api/v1/collectors/register"
    controller_heartbeat_url: str = "/api/v1/collectors/heartbeat"
    
    # 心跳配置
    heartbeat_interval: int = 3  # 秒
    heartbeat_timeout: int = 9   # 连续3次未收到心跳认为离线
    
    # XXL-Job配置
    xxl_job_admin_addresses: str = "http://localhost:8080/xxl-job-admin"
    xxl_job_access_token: str = ""
    xxl_job_executor_app_name: str = "ssh-collector-executor"
    xxl_job_executor_address: str = ""  # 自动获取
    xxl_job_executor_ip: str = ""       # 自动获取
    xxl_job_executor_port: int = 9999
    xxl_job_executor_log_path: str = "logs/xxl-job"
    xxl_job_executor_log_retention_days: int = 30
    
    # SSH配置
    ssh_timeout: int = 30
    ssh_max_retries: int = 3
    ssh_retry_delay: int = 1
    
    # 多线程采集配置
    max_concurrent_threads: int = 2  # 最大并发采集线程数
    thread_pool_timeout: int = 300   # 线程池任务超时时间（秒）
    enable_threading: bool = True    # 是否启用多线程采集
    
    # 数据库配置
    database_path: str = "data/collector.db"
    DATABASE_PATH: str = "data/collector.db"  # 添加大写版本以保持兼容性
    
    # 日志配置
    log_level: str = "INFO"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


# 全局配置实例
settings = Settings()

# 生成采集器ID（如果未设置）
if not settings.collector_id:
    import uuid
    settings.collector_id = str(uuid.uuid4())