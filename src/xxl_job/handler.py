"""
XXL-Job任务处理器
封装SSH采集任务的具体执行逻辑
支持多线程并发采集
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..ssh_core import SSHCollector, SSHCredentials, SSHCommand, CollectionTask, MultiThreadSSHCollector
from ..utils import logger
from ..config import settings


class SSHCollectionHandler:
    """SSH采集任务处理器"""
    
    def __init__(self):
        self.collector = SSHCollector()
    
    async def execute_ssh_collection(self, job_param: str) -> Dict[str, Any]:
        """
        执行SSH采集任务
        
        Args:
            job_param: XXL-Job传递的任务参数（JSON字符串）
            
        Returns:
            Dict[str, Any]: 任务执行结果
        """
        try:
            logger.info(f"开始执行SSH采集任务，参数: {job_param}")
            
            # 解析任务参数
            task_params = self.parse_job_parameters(job_param)
            
            # 验证必要参数
            if not self._validate_task_params(task_params):
                return self.format_execution_result({
                    "success": False,
                    "error": "任务参数验证失败",
                    "data": None
                })
            
            # 根据任务类型执行不同的采集逻辑
            task_type = task_params.get("task_type", "simple")
            
            if task_type == "simple":
                result = await self._execute_simple_collection(task_params)
            elif task_type == "batch":
                result = await self._execute_batch_collection(task_params)
            elif task_type == "scheduled":
                result = await self._execute_scheduled_collection(task_params)
            else:
                result = {
                    "success": False,
                    "error": f"不支持的任务类型: {task_type}",
                    "data": None
                }
            
            logger.info(f"SSH采集任务执行完成，成功: {result.get('success', False)}")
            return self.format_execution_result(result)
            
        except Exception as e:
            logger.error(f"SSH采集任务执行失败: {e}")
            return self.format_execution_result({
                "success": False,
                "error": str(e),
                "data": None
            })
    
    def parse_job_parameters(self, job_param: str) -> Dict[str, Any]:
        """
        解析XXL-Job任务参数
        
        Args:
            job_param: 任务参数字符串
            
        Returns:
            Dict[str, Any]: 解析后的参数字典
        """
        try:
            if not job_param or job_param.strip() == "":
                return {}
            
            # 尝试解析JSON格式参数
            if job_param.strip().startswith('{'):
                return json.loads(job_param)
            
            # 解析键值对格式参数 (key1=value1,key2=value2)
            params = {}
            for pair in job_param.split(','):
                if '=' in pair:
                    key, value = pair.split('=', 1)
                    params[key.strip()] = value.strip()
            
            return params
            
        except json.JSONDecodeError as e:
            logger.error(f"解析JSON参数失败: {e}")
            return {"raw_param": job_param}
        except Exception as e:
            logger.error(f"解析任务参数失败: {e}")
            return {"raw_param": job_param}
    
    def format_execution_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        格式化任务执行结果
        
        Args:
            result: 原始执行结果
            
        Returns:
            Dict[str, Any]: 格式化后的结果
        """
        return {
            "success": result.get("success", False),
            "timestamp": datetime.now().isoformat(),
            "data": result.get("data"),
            "error": result.get("error"),
            "execution_time": result.get("execution_time"),
            "task_info": result.get("task_info", {})
        }
    
    def _validate_task_params(self, params: Dict[str, Any]) -> bool:
        """
        验证任务参数
        
        Args:
            params: 任务参数
            
        Returns:
            bool: 验证是否通过
        """
        try:
            # 检查基本参数
            if "host" not in params:
                logger.error("缺少必要参数: host")
                return False
            
            if "username" not in params:
                logger.error("缺少必要参数: username")
                return False
            
            # 检查认证参数（密码或私钥至少有一个）
            if not params.get("password") and not params.get("private_key"):
                logger.error("缺少认证参数: password 或 private_key")
                return False
            
            # 检查命令参数
            if not params.get("commands") and not params.get("command"):
                logger.error("缺少命令参数: commands 或 command")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"参数验证失败: {e}")
            return False
    
    async def _execute_simple_collection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行简单采集任务
        
        Args:
            params: 任务参数
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now()
        
        try:
            # 构建SSH凭据
            credentials = SSHCredentials(
                host=params["host"],
                port=params.get("port", 22),
                username=params["username"],
                password=params.get("password"),
                private_key=params.get("private_key"),
                device_type=params.get("device_type", "linux"),
                timeout=params.get("connection_timeout", 30)
            )
            
            # 构建命令列表
            commands = []
            if "commands" in params:
                # 多命令模式
                if isinstance(params["commands"], str):
                    # 字符串格式，按分号分割
                    command_list = [cmd.strip() for cmd in params["commands"].split(';') if cmd.strip()]
                else:
                    # 列表格式
                    command_list = params["commands"]
                
                for cmd in command_list:
                    if isinstance(cmd, str):
                        commands.append(SSHCommand(command=cmd))
                    elif isinstance(cmd, dict):
                        commands.append(SSHCommand(**cmd))
            else:
                # 单命令模式
                commands.append(SSHCommand(command=params["command"]))
            
            # 执行采集任务
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                SSHCollector.execute_commands,
                credentials,
                commands,
                params.get("timeout", 300)
            )
            
            # 计算执行时间
            execution_time = (datetime.now() - start_time).total_seconds()
            result["execution_time"] = execution_time
            result["task_info"] = {
                "host": params["host"],
                "command_count": len(commands),
                "device_type": params.get("device_type", "linux")
            }
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "execution_time": execution_time,
                "task_info": {
                    "host": params.get("host", "unknown"),
                    "error_type": type(e).__name__
                }
            }
    
    async def _execute_batch_collection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行批量采集任务（支持多线程）
        
        Args:
            params: 任务参数
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now()
        
        try:
            hosts = params.get("hosts", [])
            if not hosts:
                return {
                    "success": False,
                    "error": "批量任务缺少主机列表",
                    "data": None
                }
            
            # 检查是否启用多线程
            enable_threading = params.get("enable_threading", settings.enable_threading)
            max_workers = params.get("max_workers", settings.max_concurrent_threads)
            
            logger.info(f"批量采集任务 - 主机数: {len(hosts)}, 多线程: {enable_threading}, 最大并发: {max_workers}")
            
            if enable_threading and len(hosts) > 1:
                # 使用多线程批量执行
                result = await self._execute_multi_thread_batch(params, hosts, max_workers)
            else:
                # 使用串行执行
                result = await self._execute_serial_batch(params, hosts)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            result["execution_time"] = execution_time
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "execution_time": execution_time,
                "task_info": {
                    "task_type": "batch",
                    "error_type": type(e).__name__
                }
            }
    
    async def _execute_multi_thread_batch(self, params: Dict[str, Any], 
                                        hosts: List[Dict[str, Any]], 
                                        max_workers: int) -> Dict[str, Any]:
        """
        使用多线程执行批量采集任务
        
        Args:
            params: 基础任务参数
            hosts: 主机配置列表
            max_workers: 最大并发线程数
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        try:
            # 构建任务列表
            tasks = []
            for i, host_config in enumerate(hosts):
                # 创建SSH凭据
                credentials_data = {
                    "host": host_config.get("host"),
                    "port": host_config.get("port", 22),
                    "username": host_config.get("username"),
                    "password": host_config.get("password"),
                    "private_key": host_config.get("private_key"),
                    "device_type": host_config.get("device_type", "linux"),
                    "timeout": host_config.get("timeout", 30)
                }
                
                # 创建命令列表
                commands_data = []
                for cmd in params.get("commands", []):
                    if isinstance(cmd, str):
                        commands_data.append({"command": cmd})
                    else:
                        commands_data.append(cmd)
                
                # 构建任务数据
                task_data = {
                    "task_id": f"batch_task_{i}_{host_config.get('host')}_{int(datetime.now().timestamp())}",
                    "credentials": credentials_data,
                    "commands": commands_data,
                    "timeout": params.get("timeout", 300),
                    "retry_count": params.get("retry_count", 3)
                }
                tasks.append(task_data)
            
            # 在线程池中执行批量任务
            loop = asyncio.get_event_loop()
            batch_result = await loop.run_in_executor(
                None,
                lambda: MultiThreadSSHCollector.execute_batch_tasks(
                    tasks=tasks,
                    max_workers=max_workers,
                    enable_threading=True
                )
            )
            
            # 转换结果格式以匹配原有接口
            results = []
            success_count = 0
            
            for task_result in batch_result.get("task_results", []):
                host = task_result.get("host", "unknown")
                success = task_result.get("success", False)
                
                results.append({
                    "host": host,
                    "result": {
                        "success": success,
                        "data": task_result.get("results", []) if success else None,
                        "error": task_result.get("error") if not success else None,
                        "execution_time": task_result.get("execution_time", 0),
                        "total_commands": task_result.get("total_commands", 0),
                        "success_commands": task_result.get("success_commands", 0),
                        "failed_commands": task_result.get("failed_commands", 0)
                    }
                })
                
                if success:
                    success_count += 1
            
            return {
                "success": success_count > 0,
                "data": {
                    "total_hosts": len(hosts),
                    "success_count": success_count,
                    "failed_count": len(hosts) - success_count,
                    "results": results,
                    "threading_info": {
                        "enabled": True,
                        "max_workers": max_workers,
                        "batch_execution_time": batch_result.get("execution_time", 0)
                    }
                },
                "task_info": {
                    "task_type": "batch_multithread",
                    "host_count": len(hosts)
                }
            }
            
        except Exception as e:
            logger.error(f"多线程批量采集执行失败: {e}")
            return {
                "success": False,
                "error": f"多线程执行失败: {str(e)}",
                "data": None,
                "task_info": {
                    "task_type": "batch_multithread",
                    "error_type": type(e).__name__
                }
            }
    
    async def _execute_serial_batch(self, params: Dict[str, Any], 
                                  hosts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        使用串行方式执行批量采集任务
        
        Args:
            params: 基础任务参数
            hosts: 主机配置列表
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        results = []
        success_count = 0
        
        for host_config in hosts:
            try:
                # 为每个主机创建单独的参数
                host_params = params.copy()
                host_params.update(host_config)
                
                # 执行单个主机的采集
                host_result = await self._execute_simple_collection(host_params)
                results.append({
                    "host": host_config.get("host", "unknown"),
                    "result": host_result
                })
                
                if host_result.get("success", False):
                    success_count += 1
                    
            except Exception as e:
                results.append({
                    "host": host_config.get("host", "unknown"),
                    "result": {
                        "success": False,
                        "error": str(e),
                        "data": None
                    }
                })
        
        return {
            "success": success_count > 0,
            "data": {
                "total_hosts": len(hosts),
                "success_count": success_count,
                "failed_count": len(hosts) - success_count,
                "results": results,
                "threading_info": {
                    "enabled": False,
                    "max_workers": 1
                }
            },
            "task_info": {
                "task_type": "batch_serial",
                "host_count": len(hosts)
            }
        }
    
    async def _execute_scheduled_collection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行定时采集任务
        
        Args:
            params: 任务参数
            
        Returns:
            Dict[str, Any]: 执行结果
        """
        start_time = datetime.now()
        
        try:
            # 定时任务可能需要特殊的处理逻辑
            # 比如检查上次执行时间、处理增量数据等
            
            # 获取任务配置
            task_config = params.get("task_config", {})
            
            # 执行基本采集
            result = await self._execute_simple_collection(params)
            
            # 添加定时任务特有的信息
            if result.get("success", False):
                result["task_info"].update({
                    "task_type": "scheduled",
                    "schedule_time": start_time.isoformat(),
                    "next_run": task_config.get("next_run"),
                    "cron_expression": task_config.get("cron_expression")
                })
            
            return result
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            return {
                "success": False,
                "error": str(e),
                "data": None,
                "execution_time": execution_time,
                "task_info": {
                    "task_type": "scheduled",
                    "error_type": type(e).__name__
                }
            }


# 全局处理器实例
ssh_collection_handler = SSHCollectionHandler()