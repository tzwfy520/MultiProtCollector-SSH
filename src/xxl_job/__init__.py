"""
XXL-Job模块
提供与XXL-Job调度中心的集成功能
"""

from .client import xxl_job_client
from .executor import xxl_job_executor
from .handler import ssh_collection_handler

__all__ = [
    'xxl_job_client',
    'xxl_job_executor', 
    'ssh_collection_handler'
]