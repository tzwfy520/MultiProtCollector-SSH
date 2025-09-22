"""
工具函数模块
包含日志配置、异常处理、系统监控等通用功能
"""
import logging
import psutil
import traceback
from typing import Dict, Any, Optional
from datetime import datetime
from .config import settings


class CollectorLogger:
    """采集器日志管理类"""
    
    def __init__(self, name: str = "ssh_collector"):
        self.logger = logging.getLogger(name)
        self._setup_logger()
    
    def _setup_logger(self):
        """配置日志"""
        # 设置日志级别
        level = getattr(logging, settings.log_level.upper(), logging.INFO)
        self.logger.setLevel(level)
        
        # 避免重复添加handler
        if not self.logger.handlers:
            # 创建控制台处理器
            console_handler = logging.StreamHandler()
            console_handler.setLevel(level)
            
            # 创建格式化器
            formatter = logging.Formatter(settings.log_format)
            console_handler.setFormatter(formatter)
            
            # 添加处理器
            self.logger.addHandler(console_handler)
    
    def info(self, message: str, **kwargs):
        """记录信息日志"""
        self.logger.info(message, extra=kwargs)
    
    def error(self, message: str, **kwargs):
        """记录错误日志"""
        self.logger.error(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs):
        """记录警告日志"""
        self.logger.warning(message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        """记录调试日志"""
        self.logger.debug(message, extra=kwargs)


class CollectorException(Exception):
    """采集器自定义异常基类"""
    
    def __init__(self, message: str, error_code: str = "COLLECTOR_ERROR", details: Optional[Dict] = None):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class SSHConnectionException(CollectorException):
    """SSH连接异常"""
    
    def __init__(self, message: str, host: str = "", details: Optional[Dict] = None):
        super().__init__(message, "SSH_CONNECTION_ERROR", details)
        self.host = host


class TaskExecutionException(CollectorException):
    """任务执行异常"""
    
    def __init__(self, message: str, task_id: str = "", details: Optional[Dict] = None):
        super().__init__(message, "TASK_EXECUTION_ERROR", details)
        self.task_id = task_id


class SystemMonitor:
    """系统监控类"""
    
    @staticmethod
    def get_system_info() -> Dict[str, Any]:
        """获取系统信息"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # 网络统计
            network = psutil.net_io_counters()
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "disk_percent": disk_percent,
                "memory_total": memory.total,
                "memory_available": memory.available,
                "disk_total": disk.total,
                "disk_free": disk.free,
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"获取系统信息失败: {str(e)}")
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    @staticmethod
    def get_collector_status() -> Dict[str, Any]:
        """获取采集器状态信息"""
        system_info = SystemMonitor.get_system_info()
        
        return {
            "collector_id": settings.collector_id,
            "collector_name": settings.collector_name,
            "version": settings.app_version,
            "status": "running",
            "system_info": system_info
        }


def handle_exception(func):
    """异常处理装饰器"""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except CollectorException:
            # 重新抛出自定义异常
            raise
        except Exception as e:
            # 包装其他异常
            logger.error(f"未处理的异常: {str(e)}")
            logger.debug(f"异常堆栈: {traceback.format_exc()}")
            raise CollectorException(
                message=f"执行函数 {func.__name__} 时发生未知错误: {str(e)}",
                error_code="UNKNOWN_ERROR",
                details={"function": func.__name__, "traceback": traceback.format_exc()}
            )
    return wrapper


def format_ssh_result(success: bool, data: Any = None, error: str = None) -> Dict[str, Any]:
    """格式化SSH执行结果"""
    result = {
        "success": success,
        "timestamp": datetime.now().isoformat(),
        "collector_id": settings.collector_id
    }
    
    if success and data is not None:
        result["data"] = data
    
    if not success and error:
        result["error"] = error
    
    return result


def validate_ssh_params(host: str, username: str, password: str = None, private_key: str = None) -> bool:
    """验证SSH连接参数"""
    if not host or not username:
        return False
    
    if not password and not private_key:
        return False
    
    return True


# 全局实例
logger = CollectorLogger()
system_monitor = SystemMonitor()