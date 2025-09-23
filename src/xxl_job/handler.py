"""
XXL-Job任务处理器
封装SSH采集任务的具体执行逻辑
"""

import json
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime

from ..ssh_core import SSHCollector, SSHCredentials, SSHCommand, CollectionTask
from ..utils import logger


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
        执行批量采集任务
        
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
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return {
                "success": success_count > 0,
                "data": {
                    "total_hosts": len(hosts),
                    "success_count": success_count,
                    "failed_count": len(hosts) - success_count,
                    "results": results
                },
                "execution_time": execution_time,
                "task_info": {
                    "task_type": "batch",
                    "host_count": len(hosts)
                }
            }
            
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